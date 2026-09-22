"""MainWindow: the full PyQt6 chat interface."""
import datetime
import html
import json
import sys
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QTextCursor
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QListWidget, QListWidgetItem, QTextBrowser, QLineEdit, QPushButton,
    QLabel, QSpinBox, QDoubleSpinBox, QSplitter, QGroupBox, QFormLayout,
    QMessageBox, QPlainTextEdit, QCheckBox, QProgressBar, QFileDialog,
    QComboBox,
)

import rag
from core import chat_store
from core.catalog import load_catalog
from core.config import LOG_PATH, MODEL_DIR, SETTINGS_PATH, BASE_DIR
from core.llama import start_server_process, stop_process, kill_all_servers, server_healthy
from core.http_utils import port_open
from core.prompts import DEFAULT_SYSTEM_PROMPT
from ui.theme import DARK, BUBBLE_USER, BUBBLE_AI, BUBBLE_THINK, bubble
from ui.workers import ServerStarter, IndexWorker, DownloadWorker, ChatWorker

APP_ICON = BASE_DIR / "assets" / "icon.ico"
APP_NAME = "ElectroMind"
APP_DEV = "Mohammad Amin Khadel Al Hosseini"


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} — Local Electronics AI Assistant")
        self.resize(1200, 750)
        if APP_ICON.exists():
            from PyQt6.QtGui import QIcon
            self.setWindowIcon(QIcon(str(APP_ICON)))
        self.process = None
        self.starter = None
        self.chat_worker = None
        self.index_worker = None
        self.dl_worker = None
        self.catalog = []
        self.messages = []
        self.server_port = 8081
        self._ai_buffer = ""
        self._thinking_shown = False
        self.project_dir = None
        self._pending_sources = []
        self._auto_quiet = False
        self._current_chat_id = None  # chat id currently shown in the chat view
        self._chat_dirty = False       # unsaved user/assistant messages
        self._suppress_chat_select = False

        self._build_ui()
        self._refresh_models()
        self._refresh_rag_stats()
        self._load_settings()
        self._refresh_chat_list()
        self.log_timer = QTimer(self)
        self.log_timer.timeout.connect(self._tail_log)
        self._log_pos = 0

    # ---------------------------------------------------------- UI
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        root.addWidget(splitter)

        # ---- left panel
        left = QWidget()
        left.setFixedWidth(320)
        lv = QVBoxLayout(left)
        lv.setContentsMargins(4, 4, 4, 4)

        lv.addWidget(QLabel("<b>🤖 Models (./Model)</b>"))
        self.model_list = QListWidget()
        lv.addWidget(self.model_list, 1)
        btn_row = QHBoxLayout()
        self.refresh_btn = QPushButton("⟳")
        self.refresh_btn.setFixedWidth(40)
        self.refresh_btn.setObjectName("ghost")
        self.refresh_btn.clicked.connect(self._refresh_models)
        btn_row.addWidget(self.refresh_btn)
        btn_row.addStretch()
        lv.addLayout(btn_row)

        lv.addWidget(QLabel("<b>⬇ Download model</b>"))
        dl_row = QHBoxLayout()
        self.dl_combo = QComboBox()
        self.dl_combo.setToolTip("Pick a model to download into ./Model")
        dl_row.addWidget(self.dl_combo, 1)
        self.dl_btn = QPushButton("Download")
        self.dl_btn.clicked.connect(self._download_model)
        dl_row.addWidget(self.dl_btn)
        lv.addLayout(dl_row)
        self.dl_progress = QProgressBar()
        self.dl_progress.setValue(0)
        lv.addWidget(self.dl_progress)
        self.dl_status = QLabel("")
        self.dl_status.setObjectName("dim")
        self.dl_status.setWordWrap(True)
        lv.addWidget(self.dl_status)

        settings = QGroupBox("Server settings")
        form = QFormLayout(settings)
        self.port_spin = QSpinBox()
        self.port_spin.setRange(1, 65535)
        self.port_spin.setValue(8081)
        self.ctx_spin = QSpinBox()
        self.ctx_spin.setRange(512, 131072)
        self.ctx_spin.setValue(4096)
        self.ngl_spin = QSpinBox()
        self.ngl_spin.setRange(0, 99)
        self.ngl_spin.setValue(0)
        self.temp_spin = QDoubleSpinBox()
        self.temp_spin.setRange(0.0, 2.0)
        self.temp_spin.setSingleStep(0.1)
        self.temp_spin.setValue(0.7)
        self.maxtok_spin = QSpinBox()
        self.maxtok_spin.setRange(-1, 131072)
        self.maxtok_spin.setValue(-1)
        self.maxtok_spin.setSpecialValueText("inf")
        form.addRow("Port", self.port_spin)
        form.addRow("Context", self.ctx_spin)
        form.addRow("GPU layers", self.ngl_spin)
        form.addRow("Temperature", self.temp_spin)
        form.addRow("Max tokens", self.maxtok_spin)
        lv.addWidget(settings)

        self.status_label = QLabel("● Stopped")
        self.status_label.setStyleSheet("color:#888; font-weight:bold;")
        lv.addWidget(self.status_label)

        self.start_btn = QPushButton("▶ Start server")
        self.start_btn.clicked.connect(self._toggle_server)
        lv.addWidget(self.start_btn)

        rag_box = QGroupBox("📁 Project knowledge (RAG)")
        rag_layout = QVBoxLayout(rag_box)
        self.proj_label = QLabel("No folder selected")
        self.proj_label.setObjectName("dim")
        self.proj_label.setWordWrap(True)
        rag_layout.addWidget(self.proj_label)
        rag_btns = QHBoxLayout()
        self.open_dir_btn = QPushButton("📂 Open")
        self.open_dir_btn.setObjectName("ghost")
        self.open_dir_btn.clicked.connect(self._open_project_dir)
        self.analyze_btn = QPushButton("🔍 Analyze")
        self.analyze_btn.clicked.connect(self._analyze_project)
        rag_btns.addWidget(self.open_dir_btn)
        rag_btns.addWidget(self.analyze_btn)
        rag_layout.addLayout(rag_btns)
        mode_row = QHBoxLayout()
        mode_row.addWidget(QLabel("Embeddings:"))
        self.rag_mode = QComboBox()
        self.rag_mode.addItems(["⚡ Fast (seconds)", "🎯 Accurate (slow)"])
        self.rag_mode.setToolTip("Fast = instant keyword-style vectors.\nAccurate = MiniLM download + slow CPU encoding, better meaning match.")
        mode_row.addWidget(self.rag_mode, 1)
        rag_layout.addLayout(mode_row)
        self.rag_progress = QProgressBar()
        self.rag_progress.setValue(0)
        rag_layout.addWidget(self.rag_progress)
        self.rag_status = QLabel("")
        self.rag_status.setObjectName("dim")
        self.rag_status.setWordWrap(True)
        rag_layout.addWidget(self.rag_status)
        rag_opts = QHBoxLayout()
        self.rag_enabled = QCheckBox("Use in chat")
        self.rag_enabled.setChecked(True)
        self.rag_topk = QSpinBox()
        self.rag_topk.setRange(1, 10)
        self.rag_topk.setValue(4)
        self.rag_topk.setPrefix("top-")
        rag_opts.addWidget(self.rag_enabled)
        rag_opts.addWidget(self.rag_topk)
        rag_clear_btn = QPushButton("Clear index")
        rag_clear_btn.setObjectName("ghost")
        rag_clear_btn.clicked.connect(self._clear_rag_index)
        rag_opts.addWidget(rag_clear_btn)
        rag_layout.addLayout(rag_opts)
        lv.addWidget(rag_box)

        sys_box = QGroupBox("⚙️ System prompt")
        sys_layout = QVBoxLayout(sys_box)
        self.sys_prompt_edit = QPlainTextEdit()
        self.sys_prompt_edit.setPlainText(DEFAULT_SYSTEM_PROMPT)
        self.sys_prompt_edit.setFixedHeight(90)
        self.sys_prompt_edit.setPlaceholderText("Define how the model should behave...")
        self.sys_prompt_edit.textChanged.connect(self._save_settings)
        sys_layout.addWidget(self.sys_prompt_edit)
        sys_btns = QHBoxLayout()
        self.sys_reset_btn = QPushButton("Reset default")
        self.sys_reset_btn.setObjectName("ghost")
        self.sys_reset_btn.clicked.connect(
            lambda: self.sys_prompt_edit.setPlainText(DEFAULT_SYSTEM_PROMPT))
        sys_btns.addStretch()
        sys_btns.addWidget(self.sys_reset_btn)
        sys_layout.addLayout(sys_btns)
        lv.addWidget(sys_box)

        splitter.addWidget(left)

        # ---- right panel
        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(4, 4, 4, 4)

        top = QHBoxLayout()
        self.chat_title = QLabel("<b>💬 Chat</b>")
        top.addWidget(self.chat_title)
        top.addStretch()
        self.clear_btn = QPushButton("Clear")
        self.clear_btn.setObjectName("ghost")
        self.clear_btn.clicked.connect(self._clear_chat)
        self.stop_btn = QPushButton("■ Stop")
        self.stop_btn.setObjectName("danger")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self._stop_generating)
        self.about_btn = QPushButton("ℹ")
        self.about_btn.setObjectName("ghost")
        self.about_btn.setFixedWidth(34)
        self.about_btn.setToolTip(f"About {APP_NAME}")
        self.about_btn.clicked.connect(self._show_about)
        top.addWidget(self.about_btn)
        top.addWidget(self.stop_btn)
        top.addWidget(self.clear_btn)
        rv.addLayout(top)

        # ---- chats (moved to right panel, above the chat view)
        chat_box = QGroupBox("💬 Chats (per project)")
        chat_layout = QVBoxLayout(chat_box)
        self.chat_list = QListWidget()
        self.chat_list.currentItemChanged.connect(self._on_chat_selected)
        # also react to clicking an already-selected item (Qt only emits
        # currentItemChanged when the selection actually changes)
        self.chat_list.itemClicked.connect(self._on_chat_clicked)
        chat_layout.addWidget(self.chat_list)
        chat_btns = QHBoxLayout()
        self.new_chat_btn = QPushButton("＋ New")
        self.new_chat_btn.setObjectName("ghost")
        self.new_chat_btn.clicked.connect(self._new_chat)
        self.del_chat_btn = QPushButton("✕")
        self.del_chat_btn.setObjectName("danger")
        self.del_chat_btn.setFixedWidth(30)
        self.del_chat_btn.clicked.connect(self._delete_chat)
        chat_btns.addWidget(self.new_chat_btn)
        chat_btns.addWidget(self.del_chat_btn)
        chat_layout.addLayout(chat_btns)
        self.chat_status = QLabel("Open a project folder first.")
        self.chat_status.setObjectName("dim")
        self.chat_status.setWordWrap(True)
        chat_layout.addWidget(self.chat_status)
        rv.addWidget(chat_box)

        self.chat_view = QTextBrowser()
        self.chat_view.setOpenExternalLinks(False)
        rv.addWidget(self.chat_view, 1)

        input_row = QHBoxLayout()
        self.input_box = QLineEdit()
        self.input_box.setPlaceholderText("Type a message... (Enter to send)")
        self.input_box.returnPressed.connect(self._send)
        self.send_btn = QPushButton("Send ➤")
        self.send_btn.clicked.connect(self._send)
        input_row.addWidget(self.input_box, 1)
        input_row.addWidget(self.send_btn)
        rv.addLayout(input_row)

        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(300)
        self.log_view.setPlaceholderText("Server log will appear here...")
        self.log_view.setFixedHeight(120)
        rv.addWidget(QLabel("Server log:"))
        rv.addWidget(self.log_view)

        splitter.addWidget(right)
        splitter.setStretchFactor(1, 1)
        self.setStyleSheet(DARK)
        self._update_send_state()

    # ---------------------------------------------------------- models
    def _refresh_models(self):
        self.model_list.clear()
        MODEL_DIR.mkdir(exist_ok=True)
        for f in sorted(MODEL_DIR.glob("*.gguf")):
            # skip half-finished downloads
            if f.suffixes[-2:] == [".gguf", ".part"] or f.name.endswith(".part"):
                continue
            mb = f.stat().st_size / (1024 * 1024)
            item = QListWidgetItem(f"{f.name}\n{mb:,.0f} MB")
            item.setData(Qt.ItemDataRole.UserRole, str(f))
            self.model_list.addItem(item)
        if self.model_list.count():
            self.model_list.setCurrentRow(0)
        self._refresh_catalog()

    def _selected_model(self):
        item = self.model_list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    # ---------------------------------------------------------- model download
    def _refresh_catalog(self):
        """Fill the download dropdown from models.json, flagging installed ones."""
        self.catalog = load_catalog()
        installed = set()
        if MODEL_DIR.exists():
            installed = {f.name for f in MODEL_DIR.glob("*.gguf")}
        self.dl_combo.clear()
        for m in self.catalog:
            label = m["name"]
            if m["filename"] in installed:
                label += "  ✓ installed"
            self.dl_combo.addItem(label)
        if not self.catalog:
            self.dl_status.setText("models.json missing or empty — no downloads available.")

    def _download_model(self):
        if self.dl_worker is not None:
            return  # already downloading
        if not self.catalog or self.dl_combo.currentIndex() < 0:
            QMessageBox.warning(self, "No models", "No downloadable models in models.json.")
            return
        m = self.catalog[self.dl_combo.currentIndex()]
        dest = MODEL_DIR / m["filename"]
        if dest.exists() and dest.stat().st_size > 0:
            # already have it: just select it in the list
            self.dl_status.setText(f"{m['filename']} is already in ./Model.")
            for row in range(self.model_list.count()):
                if Path(self.model_list.item(row).data(Qt.ItemDataRole.UserRole)).name == m["filename"]:
                    self.model_list.setCurrentRow(row)
                    break
            return
        self.dl_btn.setEnabled(False)
        self.dl_combo.setEnabled(False)
        self.dl_progress.setValue(0)
        self.dl_status.setText(f"Downloading {m['filename']} ({m.get('size', '?')})...")
        self.dl_worker = DownloadWorker(m["url"], dest)
        self.dl_worker.progress.connect(self._on_dl_progress)
        self.dl_worker.done.connect(self._on_dl_done)
        self.dl_worker.error.connect(self._on_dl_error)
        self.dl_worker.start()

    def _on_dl_progress(self, done_bytes, total_bytes):
        if total_bytes > 0:
            self.dl_progress.setValue(int(done_bytes / total_bytes * 100))
            self.dl_status.setText(
                f"Downloading... {done_bytes / 1e6:.0f} / {total_bytes / 1e6:.0f} MB")
        else:
            self.dl_status.setText(f"Downloading... {done_bytes / 1e6:.0f} MB")

    def _on_dl_done(self, path):
        self._drop_thread("dl_worker")
        self.dl_btn.setEnabled(True)
        self.dl_combo.setEnabled(True)
        self.dl_progress.setValue(100)
        self.dl_status.setText(f"Saved: {Path(path).name}")
        self._refresh_models()
        # select the freshly downloaded model
        name = Path(path).name
        for row in range(self.model_list.count()):
            if Path(self.model_list.item(row).data(Qt.ItemDataRole.UserRole)).name == name:
                self.model_list.setCurrentRow(row)
                break
        QMessageBox.information(self, "Download complete",
                                f"{name} is now in ./Model and ready to use.")

    def _on_dl_error(self, msg):
        self._drop_thread("dl_worker")
        self.dl_btn.setEnabled(True)
        self.dl_combo.setEnabled(True)
        self.dl_status.setText(f"Download failed: {msg}")
        QMessageBox.critical(self, "Download failed", msg)

    # ---------------------------------------------------------- RAG
    def _load_settings(self):
        try:
            data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
            d = data.get("project_dir")
            if d and Path(d).is_dir():
                self.project_dir = d
                self.proj_label.setText(d)
                self._show_index_availability(auto=False)
                self._refresh_chat_list()
                self._load_last_chat()
            sp = data.get("system_prompt")
            if sp:
                self.sys_prompt_edit.setPlainText(sp)
        except Exception:
            pass

    def _save_settings(self):
        try:
            SETTINGS_PATH.write_text(
                json.dumps({"project_dir": self.project_dir,
                            "system_prompt": self.sys_prompt_edit.toPlainText()}),
                encoding="utf-8")
        except Exception:
            pass

    def _show_index_availability(self, auto=True):
        """Check saved index for the current dir: reuse if fresh, else update incrementally."""
        try:
            chk = rag.check_changes(self.project_dir)
            st = rag.index_stats()
        except Exception:
            return False
        if chk.get("indexed") and st.get("chunks", 0) > 0:
            pending = chk["new"] + chk["changed"] + chk["removed"]
            if pending == 0:
                self.rag_status.setText(
                    f"✅ Index already available: {st['files']} files, "
                    f"{st['chunks']} chunks. No re-analysis needed.")
                return True
            if auto:
                # only new/changed files will be processed (incremental)
                self.rag_status.setText(
                    f"Index found ({st['chunks']} chunks). "
                    f"Updating {chk['new']} new, {chk['changed']} changed, "
                    f"{chk['removed']} removed...")
                self._auto_quiet = True
                self._analyze_project()
                return True
            self.rag_status.setText(
                f"Index available ({st['chunks']} chunks), but "
                f"{chk['new']} new / {chk['changed']} changed / "
                f"{chk['removed']} removed — press Analyze to update.")
            return True
        return False

    def _open_project_dir(self):
        d = QFileDialog.getExistingDirectory(self, "Select project directory")
        if d:
            self.project_dir = d
            self.proj_label.setText(d)
            self._save_settings()
            self._refresh_chat_list()
            if not self._show_index_availability(auto=True):
                self.rag_status.setText("Folder selected. Press Analyze to index.")

    def _analyze_project(self):
        if not self.project_dir:
            QMessageBox.warning(self, "No folder", "Open a project directory first.")
            return
        if self.index_worker is not None:
            return
        self.analyze_btn.setEnabled(False)
        self.open_dir_btn.setEnabled(False)
        self.rag_progress.setValue(0)
        self.rag_status.setText("Starting analysis...")
        mode = "accurate" if self.rag_mode.currentIndex() == 1 else "fast"
        self.index_worker = IndexWorker(self.project_dir, mode)
        self.index_worker.progress.connect(self._on_index_progress)
        self.index_worker.done.connect(self._on_index_done)
        self.index_worker.error.connect(self._on_index_error)
        self.index_worker.start()

    def _on_index_progress(self, stage, done, total):
        names = {"scan": "Scanning files", "load": "Loading & chunking", "embed": "Embedding"}
        label = names.get(stage, stage)
        pct = int(done / max(total, 1) * 100)
        # staged overall progress: scan 0-10%, load 10-60%, embed 60-100%
        offsets = {"scan": (0, 10), "load": (10, 50), "embed": (60, 40)}
        base, span = offsets.get(stage, (0, 100))
        self.rag_progress.setValue(base + int(span * done / max(total, 1)))
        self.rag_status.setText(f"{label}... {done}/{total}")

    def _drop_thread(self, name, timeout=15000):
        """Safely release a QThread: wait for it to finish BEFORE dropping
        the last reference, otherwise Qt aborts with
        'QThread: Destroyed while thread is still running'."""
        w = getattr(self, name, None)
        if w is None:
            return
        try:
            w.wait(timeout)
        except Exception:
            pass
        if w.isRunning():
            # still alive (shouldn't happen): let Qt delete it later, safely
            try:
                w.deleteLater()
            except Exception:
                pass
        setattr(self, name, None)

    def _on_index_done(self, stats):
        self._drop_thread("index_worker")
        self.analyze_btn.setEnabled(True)
        self.open_dir_btn.setEnabled(True)
        self.rag_progress.setValue(100)
        quiet = self._auto_quiet and stats.get("new", 1) == 0
        self._auto_quiet = False
        notes = []
        if stats.get("unsupported"):
            exts = ", ".join(f"{e}×{n}" for e, n in
                             sorted(stats.get("unsupported_exts", {}).items()))
            notes.append(f"Skipped {stats['unsupported']} unsupported files ({exts}) — "
                         "export CAD files (.SchDoc/.PcbDoc) as PDF to include them.")
        if stats.get("too_big"):
            notes.append(f"Skipped {stats['too_big']} oversized files (>5 MB).")
        if stats.get("thin_pdfs"):
            names = ", ".join(stats["thin_pdfs"][:5])
            more = f" +{len(stats['thin_pdfs']) - 5} more" if len(stats["thin_pdfs"]) > 5 else ""
            notes.append(f"{len(stats['thin_pdfs'])} PDFs have almost no text "
                         f"(scanned images?): {names}{more}.")
        summary = (f"Indexed {stats['files']} files in {stats.get('subfolders', '?')} folders "
                   f"({stats.get('skipped', 0)} unchanged skipped), "
                   f"{stats['chunks']} chunks in {stats.get('seconds', '?')}s (mode: {stats['ef']}).")
        self._refresh_rag_stats(summary + (" " + " ".join(notes) if notes else ""))
        if quiet:
            return  # auto-update found nothing new: no popup needed
        QMessageBox.information(self, "Analysis complete",
                                f"Files: {stats['files']} in {stats.get('subfolders', '?')} folders "
                                f"({stats.get('skipped', 0)} skipped, "
                                f"{stats.get('new', '?')} new)\nChunks: {stats['chunks']}\n"
                                f"Time: {stats.get('seconds', '?')}s\n"
                                + ("\n".join(notes) + "\n" if notes else "") +
                                "Saved to ./chroma_db — you can now ask about the project.")

    def _on_index_error(self, msg):
        self._auto_quiet = False
        self._drop_thread("index_worker")
        self.analyze_btn.setEnabled(True)
        self.open_dir_btn.setEnabled(True)
        self.rag_status.setText(f"Indexing failed: {msg}")
        QMessageBox.critical(self, "Analysis failed", msg)

    def _clear_rag_index(self):
        rag.clear_index()
        self._refresh_rag_stats("Index cleared.")

    def _refresh_rag_stats(self, extra=""):
        try:
            st = rag.index_stats()
            base = f"Index: {st['files']} files, {st['chunks']} chunks."
        except Exception:
            base = "Index: unavailable."
        self.rag_status.setText(f"{base} {extra}".strip())

    # ---------------------------------------------------------- chats
    @staticmethod
    def _chat_label(c: dict) -> str:
        """Human-readable list entry: title · date · message count."""
        when = datetime.datetime.fromtimestamp(c.get("updated", 0)).strftime("%d.%m %H:%M")
        n = len(c.get("messages", []))
        return f"{c.get('title', 'New chat')}\n{when}  ·  {n} msg"

    def _refresh_chat_list(self, keep_selection=False):
        """List chats for the current project, newest first.

        keep_selection=True keeps the currently shown chat selected instead of
        jumping to the newest (used while saving during a conversation)."""
        selected = self._current_chat_id if keep_selection else None
        self.chat_list.blockSignals(True)
        self.chat_list.clear()
        if not keep_selection:
            self._current_chat_id = None
        if not self.project_dir:
            self.chat_list.blockSignals(False)
            self.chat_status.setText("Open a project folder first.")
            return
        chats = chat_store.list_chats(self.project_dir)
        if not chats:
            self.chat_list.blockSignals(False)
            self.chat_status.setText("No chats yet for this project.")
            return
        restore_row = 0
        for i, c in enumerate(chats):
            item = QListWidgetItem(self._chat_label(c))
            item.setData(Qt.ItemDataRole.UserRole, c["id"])
            if c["id"] == selected:
                restore_row = i
            self.chat_list.addItem(item)
        self.chat_list.setCurrentRow(restore_row)
        self.chat_list.blockSignals(False)
        self.chat_status.setText(f"{len(chats)} chat(s) saved for this project.")

    def _on_chat_selected(self, current, previous):
        if self._suppress_chat_select or current is None or not self.project_dir:
            return
        chat = chat_store.load_chat(current.data(Qt.ItemDataRole.UserRole))
        if not chat:
            return
        self._switch_chat(chat)

    def _on_chat_clicked(self, item):
        """Clicking a chat name always opens it.

        Switching to a *different* item is handled by currentItemChanged;
        this catches clicking the already-highlighted item — e.g. right after
        pressing 'New', or to reload the conversation view.
        """
        if item is None or self._suppress_chat_select or not self.project_dir:
            return
        cid = item.data(Qt.ItemDataRole.UserRole)
        if cid and cid != self._current_chat_id:
            self._on_chat_selected(item, None)

    def _switch_chat(self, chat):
        """Load chat messages into the chat view and messages list."""
        if self.chat_worker is not None:
            QMessageBox.warning(self, "Busy", "Finish or stop the current response first.")
            self._refresh_chat_list()
            return
        self._suppress_chat_select = True
        cid = chat.get("id")
        for i in range(self.chat_list.count()):
            item = self.chat_list.item(i)
            if item.data(Qt.ItemDataRole.UserRole) == cid:
                self.chat_list.setCurrentItem(item)
                break
        self._suppress_chat_select = False
        self.messages = list(chat.get("messages", []))
        self._current_chat_id = cid
        self.chat_title.setText(f"<b>💬 {chat.get('title', 'New chat')}</b>")
        self.chat_view.clear()
        for m in self.messages:
            role = m.get("role", "user")
            text = m.get("content", "")
            if role == "user":
                self.chat_view.append(bubble(BUBBLE_USER, html.escape(text)))
            elif role == "assistant":
                self.chat_view.append(bubble(BUBBLE_AI, html.escape(text)))
            else:
                self.chat_view.append(bubble(BUBBLE_THINK, html.escape(text)))
        self._ai_buffer = ""
        self._thinking_shown = False
        self._ai_div_started = False
        self._pending_sources = []
        self._chat_dirty = False
        # remember this chat as the last-open one for the project
        if self.project_dir and cid:
            chat_store.set_last(self.project_dir, cid)
        self._update_send_state()

    def _load_last_chat(self):
        """On startup / project open, restore the last chat if one exists."""
        if not self.project_dir:
            return
        last_id = chat_store.last_chat_id(self.project_dir)
        if not last_id:
            return
        for i in range(self.chat_list.count()):
            item = self.chat_list.item(i)
            if item.data(Qt.ItemDataRole.UserRole) == last_id:
                self._suppress_chat_select = True
                self.chat_list.setCurrentItem(item)
                self._suppress_chat_select = False
                self._on_chat_selected(item, None)
                break

    def _new_chat(self):
        if not self.project_dir:
            QMessageBox.warning(self, "No project", "Open a project folder first.")
            return
        if self.chat_worker is not None:
            QMessageBox.warning(self, "Busy", "Finish or stop the current response first.")
            return
        # Lazy creation: don't persist an empty chat file. The chat is only
        # written to disk when the first message is sent (_save_current_chat).
        self._current_chat_id = None
        self.messages = []
        self.chat_title.setText("<b>💬 New chat</b>")
        self.chat_view.clear()
        self._ai_buffer = ""
        self._thinking_shown = False
        self._ai_div_started = False
        self._pending_sources = []
        self._chat_dirty = False
        # deselect the list so the previous chat's name is no longer
        # highlighted — clicking it afterwards re-opens it cleanly
        self.chat_list.setCurrentRow(-1)
        self._update_send_state()

    def _delete_chat(self):
        if not self.project_dir:
            return
        item = self.chat_list.currentItem()
        if item is None:
            return
        chat_id = item.data(Qt.ItemDataRole.UserRole)
        reply = QMessageBox.question(
            self, "Delete chat",
            "Delete this chat? (per-project only, other chats unaffected)")
        if reply == QMessageBox.StandardButton.Yes:
            chat_store.delete_chat(chat_id, self.project_dir)
            self._refresh_chat_list()

    def _save_current_chat(self):
        """Persist the current chat (creates it on the first message)."""
        if not self.project_dir or not self.messages:
            return
        chat_id = self._current_chat_id
        title = chat_store.title_for(self.project_dir, self.messages)
        if not chat_id:
            # first message in a new chat -> create it on disk now
            chat = chat_store.new_chat(self.project_dir, title=title)
            chat_id = chat["id"]
            self._current_chat_id = chat_id
        chat_store.save_chat({
            "id": chat_id,
            "project_dir": self.project_dir,
            "title": title,
            "messages": list(self.messages),
        })
        self.chat_title.setText(f"<b>💬 {title}</b>")
        self._refresh_chat_list(keep_selection=True)
        self._chat_dirty = False

    def _on_chat_finished(self, full):
        self.messages.append({"role": "assistant", "content": full or self._ai_buffer})
        if self._pending_sources:
            seen = list(dict.fromkeys(self._pending_sources))
            src = "<br>".join("📄 " + html.escape(s) for s in seen[:10])
            self.chat_view.append(bubble(BUBBLE_THINK, f"<b>Sources:</b><br>{src}"))
            self._pending_sources = []
        self._finish_worker()
        self._save_current_chat()

    def _on_chat_error(self, msg):
        # friendly message when the model can't read an image
        if "image" in msg.lower() and ("not support" in msg.lower() or "cannot read" in msg.lower()):
            self._append_sys(
                "⚠️ This local model is text-only — it cannot view images. "
                "Describe what you see and I'll answer from the project files.")
        else:
            self._append_sys(f"Request failed: {html.escape(msg)}")
        if self.messages and self.messages[-1]["role"] == "user":
            self.messages.pop()
            self._save_current_chat()  # keep disk in sync after dropping the failed message
        self._finish_worker()

    def _stop_generating(self):
        if getattr(self, "chat_worker", None) is not None:
            self.chat_worker.stop()
        self.stop_btn.setEnabled(False)
        self._update_send_state()

    def _finish_worker(self):
        # drop the reference safely: wait for the thread to finish first,
        # otherwise Qt may abort with 'QThread: Destroyed while thread is running'
        w, self.chat_worker = self.chat_worker, None
        if w is not None:
            try:
                w.wait(15000)
            except Exception:
                pass
        self.stop_btn.setEnabled(False)
        self._update_send_state()

    def _clear_chat(self):
        self._stop_generating()
        self.messages.clear()
        self.chat_view.clear()
        if self._current_chat_id:
            chat_store.delete_chat(self._current_chat_id, self.project_dir)
        self._current_chat_id = None
        self.chat_title.setText("<b>💬 Chat</b>")
        self._chat_dirty = False
        self._update_send_state()

    def _show_about(self):
        QMessageBox.about(
            self, f"About {APP_NAME}",
            f"<h3>⚡ {APP_NAME}</h3>"
            "<p>Local, offline AI assistant for electronics &amp; embedded projects.<br>"
            "Powered by llama.cpp + PyQt6 + ChromaDB (RAG).</p>"
            f"<p>Developed by <b>{APP_DEV}</b><br>"
            "with AI pair-programming assistance.</p>")

    # ---------------------------------------------------------- server
    def _toggle_server(self):
        if self.process is None:
            self._start_server()
        else:
            self._stop_server()

    def _start_server(self):
        model = self._selected_model()
        if not model:
            QMessageBox.warning(self, "No model", "Select a .gguf model first.")
            return
        port = self.port_spin.value()
        if port_open(port):
            QMessageBox.warning(self, "Port busy", f"Port {port} is already in use.")
            return
        self.server_port = port
        try:
            self.process, self._log_file = start_server_process(
                model, port,
                ctx=self.ctx_spin.value(),
                n_gpu_layers=self.ngl_spin.value(),
                log_path=LOG_PATH)
        except OSError as e:
            QMessageBox.critical(self, "Log error", str(e))
            return
        self._log_pos = 0
        self.log_view.clear()
        self._set_status("starting", "● Starting...")
        self.start_btn.setEnabled(False)
        self.starter = ServerStarter(self.process, port)
        self.starter.ready.connect(self._on_server_ready)
        self.starter.failed.connect(self._on_server_failed)
        self.starter.start()
        self.log_timer.start(1000)

    def _on_server_ready(self):
        self._drop_thread("starter")
        self._set_status("ready", f"● Ready on 127.0.0.1:{self.server_port}")
        self.start_btn.setText("■ Stop server")
        self.start_btn.setObjectName("danger")
        self.start_btn.setStyleSheet("")
        self.start_btn.setEnabled(True)
        self._update_send_state()
        self._append_sys(f"Server ready on http://127.0.0.1:{self.server_port}")

    def _on_server_failed(self, msg):
        self._drop_thread("starter")
        QMessageBox.critical(self, "Server failed", msg)
        self._cleanup_process()
        self._set_status("stopped", "● Stopped")
        self.start_btn.setText("▶ Start server")
        self.start_btn.setObjectName("")
        self.start_btn.setEnabled(True)
        self._update_send_state()

    def _stop_server(self):
        self._stop_generating()
        self._cleanup_process()
        self.log_timer.stop()
        self._set_status("stopped", "● Stopped")
        self.start_btn.setText("▶ Start server")
        self.start_btn.setObjectName("")
        self.start_btn.setEnabled(True)
        self._update_send_state()

    def _cleanup_process(self):
        stop_process(self.process, getattr(self, "_log_file", None))
        self.process = None
        self._log_file = None

    def _set_status(self, kind, text):
        colors = {"stopped": "#888", "starting": "#c9a86a", "ready": "#6aca6a", "error": "#e06c6c"}
        self.status_label.setText(text)
        self.status_label.setStyleSheet(f"color:{colors.get(kind, '#888')}; font-weight:bold;")

    def _tail_log(self):
        try:
            data = LOG_PATH.read_bytes()[self._log_pos:]
            self._log_pos += len(data)
            if data:
                self.log_view.appendPlainText(data.decode("utf-8", errors="replace").rstrip())
        except Exception:
            pass

    # ---------------------------------------------------------- chat
    def _server_ready(self):
        return (self.process is not None and self.process.poll() is None
                and port_open(self.server_port))

    def _update_send_state(self):
        ok = self._server_ready() and self.chat_worker is None
        self.send_btn.setEnabled(ok)
        self.input_box.setEnabled(self.chat_worker is None)

    @staticmethod
    def _trimmed_history(messages, ctx_tokens, reserve_tokens=1024):
        """Keep the newest messages whose total text fits the model context.

        Rough estimate: ~4 characters per token. The full history always stays
        saved on disk; only what is SENT to the model is trimmed, so old chats
        can still be continued without the server rejecting the request.
        The system prompt is added separately on top of this.
        """
        budget = max(ctx_tokens - reserve_tokens, 256) * 4  # chars
        kept = []
        used = 0
        for m in reversed(messages):
            if m.get("role") == "system":
                continue
            size = len(m.get("content", ""))
            if used + size > budget and kept:
                break  # older messages no longer fit
            if used + size > budget:
                # even the newest message alone is too big: truncate its text
                m = {**m, "content": m["content"][-budget:]}
                size = budget
            kept.append(m)
            used += size
        kept.reverse()
        return kept

    def _append_sys(self, text):
        self.chat_view.append(bubble(BUBBLE_THINK, html.escape(text)))

    # image extensions that the local text model cannot process
    IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".tiff", ".webp", ".svg"}

    def _send(self):
        text = self.input_box.text().strip()
        if not text or self.chat_worker is not None:
            return
        if not self._server_ready():
            QMessageBox.warning(self, "No server", "Start the server first.")
            return
        # warn if the user referenced an image file (text model has no vision)
        if any(p.strip().lower().endswith(tuple(self.IMAGE_EXTS))
               for p in text.split()):
            reply = QMessageBox.warning(
                self, "Image not supported",
                "This local model is text-only and cannot read images.\n"
                "Describe what the image shows and I'll answer from the project files.\n\n"
                "Cancel to edit your message.",
                QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel)
            if reply == QMessageBox.StandardButton.Cancel:
                return
        safe = html.escape(text).replace("\n", "<br>")
        self.chat_view.append(bubble(BUBBLE_USER, safe))
        self.messages.append({"role": "user", "content": text})
        self._save_current_chat()  # persist immediately: never lose a message on crash/close
        self.input_box.clear()
        self._ai_buffer = ""
        self._thinking_shown = False
        self._ai_div_started = False
        self._pending_sources = []

        # Memory management: trim the oldest history so the prompt fits into
        # the model context (otherwise llama-server rejects long chats).
        outgoing = self._trimmed_history(self.messages, self.ctx_spin.value())

        # System prompt + optional RAG project context, as one system message
        system_prompt = self.sys_prompt_edit.toPlainText().strip()
        rag_block = ""
        if self.rag_enabled.isChecked():
            try:
                st = rag.index_stats()
            except Exception:
                st = {"chunks": 0}
            if st.get("chunks", 0) > 0:
                try:
                    snips = rag.retrieve(text, self.rag_topk.value())
                except Exception as e:
                    self._append_sys(f"RAG retrieval failed: {e}")
                    snips = []
                if snips:
                    ctx = rag.build_context(snips)
                    rag_block = ("\n\nPROJECT CONTEXT (relevant files from the indexed project "
                                 "— ground your answer in it and cite file paths):\n" + ctx)
                    self._pending_sources = [s["path"] for s in snips]
                    self._append_sys(f"📚 Using {len(snips)} context chunks from the project index.")
            else:
                self._append_sys("RAG enabled but index is empty — press Analyze first.")
        system_content = system_prompt + rag_block if system_prompt else rag_block.lstrip("\n")
        if system_content.strip():
            outgoing = [{"role": "system", "content": system_content}] + outgoing
        self.chat_worker = ChatWorker(self.server_port, outgoing,
                                      self.temp_spin.value(), self.maxtok_spin.value())
        self.chat_worker.token.connect(self._on_token)
        self.chat_worker.finished.connect(self._on_chat_finished)
        self.chat_worker.error.connect(self._on_chat_error)
        self.chat_worker.start()
        self.stop_btn.setEnabled(True)
        self._update_send_state()

    def _on_token(self, kind, text):
        if kind == "thinking":
            if not self._thinking_shown:
                self.chat_view.append(bubble(BUBBLE_THINK, "<i>[thinking...]</i>"))
                self._thinking_shown = True
            return
        if not getattr(self, "_ai_div_started", False):
            # start assistant bubble (we append incrementally via cursor)
            self.chat_view.append(bubble(BUBBLE_AI, ""))
            self._ai_div_started = True
        self._ai_buffer += text
        # Append token text at the end of the chat view
        self.chat_view.moveCursor(QTextCursor.MoveOperation.End)
        self.chat_view.insertPlainText(text)
        self.chat_view.ensureCursorVisible()

    def closeEvent(self, event):
        self._stop_generating()
        if self.dl_worker is not None:
            try:
                self.dl_worker.stop()
            except Exception:
                pass
        for name in ("index_worker", "starter", "dl_worker"):
            w = getattr(self, name, None)
            if w is not None:
                try:
                    w.wait(15000)
                except Exception:
                    pass
                if w.isRunning():
                    try:
                        w.deleteLater()
                    except Exception:
                        pass
                setattr(self, name, None)
        self._cleanup_process()
        kill_all_servers()  # also kill any orphans on this port
        super().closeEvent(event)


def run_app():
    import atexit
    import signal

    # Never leave orphan servers: cleanup on normal exit, crash, or signals.
    atexit.register(kill_all_servers)
    try:
        for sig in (signal.SIGINT, signal.SIGTERM):
            signal.signal(sig, lambda *_: (kill_all_servers(), sys.exit(0)))
    except Exception:
        pass

    orig_excepthook = sys.excepthook

    def _excepthook(t, v, tb):
        try:
            kill_all_servers()
        finally:
            orig_excepthook(t, v, tb)

    sys.excepthook = _excepthook

    # Clean orphans from a previous crash before starting
    kill_all_servers()

    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    try:
        sys.exit(app.exec())
    finally:
        try:
            win._stop_generating()
        except Exception:
            pass
        try:
            win._cleanup_process()
        except Exception:
            pass
        kill_all_servers()
