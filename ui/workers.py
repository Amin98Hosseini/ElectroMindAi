"""Background QThread workers: server startup, RAG indexing, model download, chat streaming."""
import json
import os
import time
import urllib.request

from PyQt6.QtCore import QThread, pyqtSignal

import rag
from core.config import LOG_PATH
from core.http_utils import http_open, port_open


class ServerStarter(QThread):
    ready = pyqtSignal()
    failed = pyqtSignal(str)

    def __init__(self, process, port):
        super().__init__()
        self.process = process
        self.port = int(port)

    def run(self):
        start = time.time()
        while time.time() - start < 180:
            if self.process.poll() is not None:
                tail = ""
                try:
                    tail = "\n".join(LOG_PATH.read_text(errors="replace").splitlines()[-15:])
                except Exception:
                    pass
                self.failed.emit(f"Server exited (code {self.process.returncode}).\n{tail}")
                return
            if port_open(self.port):
                try:
                    req = urllib.request.Request(f"http://127.0.0.1:{self.port}/health")
                    with http_open(req, timeout=5) as resp:
                        if resp.status == 200:
                            self.ready.emit()
                            return
                except urllib.error.HTTPError as e:
                    if e.code == 503:
                        pass
                    else:
                        self.ready.emit()
                        return
                except Exception:
                    pass
            time.sleep(1)
        self.failed.emit("Timeout waiting for server (/health never returned 200).")


class IndexWorker(QThread):
    """Background project indexing: scan -> load -> chunk -> ChromaDB."""
    progress = pyqtSignal(str, int, int)  # stage, done, total
    done = pyqtSignal(dict)
    error = pyqtSignal(str)

    def __init__(self, root, mode="fast"):
        super().__init__()
        self.root = root
        self.mode = mode

    def run(self):
        try:
            stats = rag.index_directory(
                self.root,
                progress=lambda s, d, t: self.progress.emit(s, d, t),
                mode=self.mode)
            self.done.emit(stats)
        except Exception as e:
            self.error.emit(f"{type(e).__name__}: {e}")


class DownloadWorker(QThread):
    """Download a model file into ./Model with progress. Uses .part temp file."""
    progress = pyqtSignal(int, int)  # downloaded_bytes, total_bytes (0 if unknown)
    done = pyqtSignal(str)           # final path
    error = pyqtSignal(str)

    def __init__(self, url, dest):
        super().__init__()
        self.url = url
        self.dest = dest
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        tmp = self.dest.with_suffix(self.dest.suffix + ".part")
        try:
            self.dest.parent.mkdir(parents=True, exist_ok=True)
            req = urllib.request.Request(self.url, headers={"User-Agent": "llama-gui/1.0"})
            resp = urllib.request.urlopen(req, timeout=30)
            total = int(resp.headers.get("Content-Length", 0) or 0)
            downloaded = 0
            with open(tmp, "wb") as f:
                while True:
                    if self._stop:
                        return  # cancelled: leave .part for resume-like retry (fresh next time)
                    chunk = resp.read(1024 * 256)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    self.progress.emit(downloaded, total)
            if total and downloaded != total:
                self.error.emit(f"Incomplete download ({downloaded}/{total} bytes). Try again.")
                return
            os.replace(tmp, self.dest)
            self.done.emit(str(self.dest))
        except Exception as e:
            self.error.emit(f"{type(e).__name__}: {e}")


class ChatWorker(QThread):
    token = pyqtSignal(str, str)   # (kind, text) kind: 'thinking' | 'content'
    finished = pyqtSignal(str)     # full assistant content
    error = pyqtSignal(str)

    def __init__(self, port, messages, temperature, max_tokens):
        super().__init__()
        self.port = port
        self.messages = messages
        self.temperature = temperature
        self.max_tokens = max_tokens
        self._stop = False

    def stop(self):
        self._stop = True
        # unblock a thread stuck in resp.read()
        try:
            if getattr(self, "_resp", None) is not None:
                self._resp.close()
        except Exception:
            pass

    def run(self):
        url = f"http://127.0.0.1:{self.port}/v1/chat/completions"
        payload = json.dumps({
            "messages": self.messages,
            "stream": True,
            "temperature": self.temperature,
            **({"n_predict": self.max_tokens} if self.max_tokens > 0 else {}),
        }).encode()
        req = urllib.request.Request(url, data=payload,
                                     headers={"Content-Type": "application/json"})
        full = ""
        self._resp = None
        try:
            resp = http_open(req, timeout=300)
            self._resp = resp
            buffer = b""
            while True:
                if self._stop:
                    break
                chunk = resp.read(64)
                if not chunk:
                    break
                buffer += chunk
                while b"\n" in buffer:
                    raw, buffer = buffer.split(b"\n", 1)
                    line = raw.decode("utf-8", errors="replace").strip()
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        self.finished.emit(full)
                        return
                    try:
                        obj = json.loads(data)
                        delta = obj["choices"][0].get("delta", {})
                        reasoning = delta.get("reasoning_content", "")
                        if reasoning:
                            self.token.emit("thinking", reasoning)
                        content = delta.get("content", "")
                        if content:
                            full += content
                            self.token.emit("content", content)
                    except (json.JSONDecodeError, KeyError, IndexError):
                        continue
            self.finished.emit(full)
        except Exception as e:
            self.error.emit(f"{type(e).__name__}: {e}")
