"""llama-server process management: launching, health checks, cleanup.

Used by both the GUI (ui/) and the terminal client (run_llama.py).
"""
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from core.config import LLAMA_SERVER
from core.http_utils import http_open, port_open


def build_server_cmd(model, port, ctx=4096, n_gpu_layers=0):
    """Command line to start llama-server with the given model."""
    return [str(LLAMA_SERVER), "-m", str(model), "--port", str(int(port)),
            "-c", str(int(ctx)), "-ngl", str(int(n_gpu_layers))]


def start_server_process(model, port, ctx=4096, n_gpu_layers=0, log_path=None):
    """Launch llama-server with output redirected to log_path.

    Returns (process, log_file). Raises OSError if the log file can't be opened.
    """
    log_file = open(log_path, "w", encoding="utf-8", errors="replace")
    flags = subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0
    process = subprocess.Popen(build_server_cmd(model, port, ctx, n_gpu_layers),
                               stdout=log_file, stderr=subprocess.STDOUT,
                               creationflags=flags)
    return process, log_file


def server_healthy(port, timeout=5):
    """True if /health answers (503 = still loading model -> False)."""
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{int(port)}/health")
        with http_open(req, timeout=timeout) as resp:
            return resp.status == 200
    except Exception:
        return False


def wait_for_server(process, port, log_path=None, timeout=180, log=print):
    """Block until /health returns 200. 503 / disconnects = still loading, keep waiting."""
    port = int(port)
    start = time.time()
    log("Waiting for server to be ready...")
    while time.time() - start < timeout:
        if process.poll() is not None:
            log(f"\nServer process exited with code {process.returncode}.")
            if log_path and Path(log_path).exists():
                log("--- server log tail ---")
                try:
                    for line in Path(log_path).read_text(errors="replace").splitlines()[-30:]:
                        log(line)
                except Exception:
                    pass
            return False

        tcp = port_open(port)
        http_code = None
        if tcp:
            try:
                req = urllib.request.Request(f"http://127.0.0.1:{port}/health")
                with http_open(req, timeout=5) as resp:
                    http_code = resp.status
                    if resp.status == 200:
                        log("Health check: 200 OK")
                        return True
            except Exception as e:
                code = getattr(e, "code", None)
                http_code = code if code is not None else type(e).__name__
                if code == 503:
                    pass  # still loading, keep waiting
                else:
                    log(f"Health check: HTTP {http_code} (treating as ready)")
                    return True
        else:
            http_code = "port-closed"

        log(f"  [{int(time.time() - start)}s] tcp={'open' if tcp else 'closed'} http={http_code}")
        time.sleep(1)

    log("Timeout waiting for /health 200. Check llama_server.log")
    return False


def stop_process(process, log_file=None):
    """Terminate (then kill) a server process and close its log file."""
    if process is not None:
        try:
            process.terminate()
            process.wait(timeout=10)
        except Exception:
            try:
                process.kill()
            except Exception:
                pass
    if log_file is not None:
        try:
            log_file.close()
        except Exception:
            pass


def kill_all_servers():
    """Force-kill any leftover llama-server processes (orphans from crashes)."""
    try:
        if sys.platform == "win32":
            subprocess.run(["taskkill", "/IM", "llama-server.exe", "/F"],
                           capture_output=True, timeout=10)
        else:
            subprocess.run(["pkill", "-f", "llama-server"],
                           capture_output=True, timeout=10)
    except Exception:
        pass
