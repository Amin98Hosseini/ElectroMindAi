"""Settings window: every configurable option of the app in one place.

The dialog owns the widgets, MainWindow keeps aliases (self.port_spin, ...)
so the rest of the code does not care where the widgets physically live.
"""
from PyQt6.QtCore import QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDoubleSpinBox, QFormLayout, QGroupBox,
    QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit, QProgressBar, QPushButton,
    QScrollArea, QSpinBox, QTabWidget, QVBoxLayout, QWidget,
    QMessageBox,
)

from core import skills as skill_lib
from core import laya as laya_lib
from core.config import SKILLS_DIR
from core.prompts import DEFAULT_SYSTEM_PROMPT


class SettingsDialog(QDialog):
    def __init__(self, main):
        super().__init__(main)
        self.main = main
        self.setWindowTitle("Settings — ElectroMind")
        self.setMinimumSize(560, 540)
        self._build()
        self._connect()

    # ---------------------------------------------------------- layout
    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        self.tabs = QTabWidget()
        root.addWidget(self.tabs, 1)
        self.tabs.addTab(self._server_tab(), "🖥 Server")
        self.tabs.addTab(self._models_tab(), "⬇ Models")
        self.tabs.addTab(self._rag_tab(), "📁 Project / RAG")
        self.tabs.addTab(self._skills_tab(), "🛠 Skills")
        self.tabs.addTab(self._prompt_tab(), "📝 System prompt")

        foot = QHBoxLayout()
        hint = QLabel("Changes are saved automatically to settings.json.")
        hint.setObjectName("dim")
        foot.addWidget(hint)
        foot.addStretch()
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.close)
        foot.addWidget(close_btn)
        root.addLayout(foot)

    def _server_tab(self):
        w = QWidget()
        form = QFormLayout(w)
        self.port_spin = QSpinBox()
        self.port_spin.setRange(1, 65535)
        self.port_spin.setValue(8081)
        self.ctx_spin = QSpinBox()
        self.ctx_spin.setRange(512, 131072)
        self.ctx_spin.setValue(4096)
        self.ngl_spin = QSpinBox()
        self.ngl_spin.setRange(0, 99)
        self.ngl_spin.setValue(0)
        self.ngl_spin.setToolTip("0 = CPU only. Higher = more layers offloaded to the GPU.")
        self.temp_spin = QDoubleSpinBox()
        self.temp_spin.setRange(0.0, 2.0)
        self.temp_spin.setSingleStep(0.1)
        self.temp_spin.setValue(0.7)
        self.maxtok_spin = QSpinBox()
        self.maxtok_spin.setRange(-1, 131072)
        self.maxtok_spin.setValue(-1)
        self.maxtok_spin.setSpecialValueText("inf")
        form.addRow("Port", self.port_spin)
        form.addRow("Context size", self.ctx_spin)
        form.addRow("GPU layers", self.ngl_spin)
        form.addRow("Temperature", self.temp_spin)
        form.addRow("Max tokens", self.maxtok_spin)
        note = QLabel("Port, context size and GPU layers are applied when the server "
                      "(re)starts.\nTemperature and max tokens are applied to every message.")
        note.setObjectName("dim")
        note.setWordWrap(True)
        form.addRow(note)
        return w

    def _models_tab(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.addWidget(QLabel("<b>Download a GGUF model into ./Model</b>"))
        row = QHBoxLayout()
        self.dl_combo = QComboBox()
        self.dl_combo.setToolTip("Pick a model to download into ./Model")
        row.addWidget(self.dl_combo, 1)
        self.dl_btn = QPushButton("Download")
        row.addWidget(self.dl_btn)
        v.addLayout(row)
        self.dl_progress = QProgressBar()
        self.dl_progress.setValue(0)
        v.addWidget(self.dl_progress)
        self.dl_status = QLabel("")
        self.dl_status.setObjectName("dim")
        self.dl_status.setWordWrap(True)
        v.addWidget(self.dl_status)
        note = QLabel("The list comes from models.json. Installed models show up in the "
                      "Models list on the left panel.")
        note.setObjectName("dim")
        note.setWordWrap(True)
        v.addWidget(note)
        v.addStretch()
        return w

    def _rag_tab(self):
        w = QWidget()
        v = QVBoxLayout(w)

        box = QGroupBox("Retrieval")
        form = QFormLayout(box)
        self.rag_mode = QComboBox()
        self.rag_mode.addItems(["⚡ Fast (seconds)", "🎯 Accurate (slow)"])
        self.rag_mode.setToolTip(
            "Fast = instant keyword-style vectors.\n"
            "Accurate = MiniLM download + slow CPU encoding, better meaning match.")
        form.addRow("Embeddings", self.rag_mode)
        self.rag_topk = QSpinBox()
        self.rag_topk.setRange(1, 10)
        self.rag_topk.setValue(4)
        self.rag_topk.setPrefix("top-")
        self.rag_topk.setToolTip("How many project chunks are injected per question.")
        form.addRow("Chunks / question", self.rag_topk)
        v.addWidget(box)
        self.rag_enabled = QCheckBox("Use indexed project context in chat")
        self.rag_enabled.setChecked(True)
        v.addWidget(self.rag_enabled)

        # ---- Laya Context Intelligence (relevance filtering of RAG results)
        laya_box = QGroupBox("🧠 Laya Context Intelligence (relevance filtering)")
        lv = QVBoxLayout(laya_box)
        self.laya_enabled = QCheckBox("Enable Laya context filtering")
        self.laya_enabled.setChecked(True)
        self.laya_enabled.setToolTip(
            "A local decision model re-ranks the retrieved chunks by relevance "
            "to your question before they are sent to the LLM.\n"
            "Needs 'pip install laya' (Python 3.10+); falls back to plain "
            "ChromaDB ranking when unavailable.")
        lv.addWidget(self.laya_enabled)
        lform = QFormLayout()
        self.laya_initial_k = QSpinBox()
        self.laya_initial_k.setRange(2, 30)
        self.laya_initial_k.setValue(10)
        self.laya_initial_k.setPrefix("top-")
        self.laya_initial_k.setToolTip("Candidates fetched from ChromaDB before Laya re-ranks them.")
        self.laya_final_k = QSpinBox()
        self.laya_final_k.setRange(1, 10)
        self.laya_final_k.setValue(4)
        self.laya_final_k.setPrefix("top-")
        self.laya_final_k.setToolTip("Contexts kept after filtering — at most 'Chunks / question' above.")
        self.laya_threshold = QDoubleSpinBox()
        self.laya_threshold.setRange(0.0, 1.0)
        self.laya_threshold.setSingleStep(0.05)
        self.laya_threshold.setValue(0.70)
        self.laya_threshold.setToolTip(
            "Contexts scoring below this relevance probability are dropped\n"
            "(the best few are still kept as a fallback — never an empty context).")
        self.laya_model = QComboBox()
        self.laya_model.addItems(["auto (detect language)", "english", "multilingual"])
        self.laya_model.setToolTip(
            "auto: English questions use the English checkpoint, everything else "
            "(e.g. Persian, mixed) the multilingual one.")
        lform.addRow("Initial candidates", self.laya_initial_k)
        lform.addRow("Final contexts", self.laya_final_k)
        lform.addRow("Relevance threshold", self.laya_threshold)
        lform.addRow("Model", self.laya_model)
        lv.addLayout(lform)
        self.laya_status = QLabel("")
        self.laya_status.setObjectName("dim")
        self.laya_status.setWordWrap(True)
        lv.addWidget(self.laya_status)
        v.addWidget(laya_box)
        self._update_laya_status()

        idx = QGroupBox("Index")
        iv = QVBoxLayout(idx)
        self.index_stats = QLabel("Index: unavailable.")
        self.index_stats.setObjectName("dim")
        self.index_stats.setWordWrap(True)
        iv.addWidget(self.index_stats)
        ibtns = QHBoxLayout()
        self.clear_index_btn = QPushButton("Clear index")
        self.clear_index_btn.setObjectName("ghost")
        ibtns.addWidget(self.clear_index_btn)
        ibtns.addStretch()
        iv.addLayout(ibtns)
        v.addWidget(idx)

        note = QLabel("Pick the project folder with 📂 Browse and press 🔍 Analyze in the "
                      "left panel to build or update the index.")
        note.setObjectName("dim")
        note.setWordWrap(True)
        v.addWidget(note)
        v.addStretch()
        return w

    def _skills_tab(self):
        """Built-in + custom expert roles. Ticked ones are added to the prompt."""
        self._skill_selected = set()
        self.skill_checks = {}

        inner = QWidget()
        v = QVBoxLayout(inner)
        intro = QLabel("Skills turn the assistant into a specialist. Tick the skills you need — "
                       "they are added to the system prompt for every message, so combine them "
                       "freely (e.g. PCB + STM32).")
        intro.setObjectName("dim")
        intro.setWordWrap(True)
        v.addWidget(intro)

        dir_row = QHBoxLayout()
        self.open_skills_dir_btn = QPushButton("📂 Open skills folder")
        self.open_skills_dir_btn.setObjectName("ghost")
        dir_row.addWidget(self.open_skills_dir_btn)
        dir_row.addStretch()
        v.addLayout(dir_row)
        files_hint = QLabel("Every skill is a .md file in ./skills "
                            "(name, **description:** and ## Instructions). "
                            "Edit a file to change it, or drop a new .md in the folder — "
                            "it appears here automatically.")
        files_hint.setObjectName("dim")
        files_hint.setWordWrap(True)
        v.addWidget(files_hint)

        box = QGroupBox("Available skills")
        bv = QVBoxLayout(box)
        self.skill_list_layout = QVBoxLayout()
        self.skill_list_layout.setSpacing(4)
        bv.addLayout(self.skill_list_layout)
        self.skills_active_label = QLabel("Active: none")
        self.skills_active_label.setObjectName("dim")
        self.skills_active_label.setWordWrap(True)
        bv.addWidget(self.skills_active_label)
        v.addWidget(box)

        create = QGroupBox("Create a skill")
        cv = QVBoxLayout(create)
        form = QFormLayout()
        self.new_skill_name = QLineEdit()
        self.new_skill_name.setPlaceholderText("e.g. RF / Antenna Designer")
        self.new_skill_desc = QLineEdit()
        self.new_skill_desc.setPlaceholderText("One line, shown as a tooltip")
        form.addRow("Name", self.new_skill_name)
        form.addRow("Description", self.new_skill_desc)
        cv.addLayout(form)
        self.new_skill_prompt = QPlainTextEdit()
        self.new_skill_prompt.setPlaceholderText(
            "Instructions added to the system prompt while this skill is ticked...\n"
            "Example: SKILL — RF designer: match 50 ohm traces, pi-matching networks, ...")
        self.new_skill_prompt.setMinimumHeight(90)
        cv.addWidget(self.new_skill_prompt)
        cbtns = QHBoxLayout()
        cbtns.addStretch()
        self.add_skill_btn = QPushButton("＋ Add skill")
        cbtns.addWidget(self.add_skill_btn)
        cv.addLayout(cbtns)
        v.addWidget(create)
        v.addStretch()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(inner)
        wrap = QWidget()
        wl = QVBoxLayout(wrap)
        wl.setContentsMargins(0, 0, 0, 0)
        wl.addWidget(scroll)
        self._skills_page = wrap
        self._rebuild_skill_list()
        return wrap

    def _on_tab_changed(self, index):
        """Re-read ./skills when the Skills tab is opened (files may have changed)."""
        if getattr(self, "_skills_page", None) is not None and \
                self.tabs.widget(index) is self._skills_page:
            self._rebuild_skill_list()

    def _open_skills_folder(self):
        try:
            SKILLS_DIR.mkdir(parents=True, exist_ok=True)
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(SKILLS_DIR)))
        except Exception as exc:
            QMessageBox.warning(self, "Skills folder", f"Cannot open {SKILLS_DIR}:\n{exc}")

    # ---------------------------------------------------------- skills helpers
    def _rebuild_skill_list(self):
        while self.skill_list_layout.count():
            item = self.skill_list_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        self.skill_checks = {}
        for category, items in skill_lib.grouped_skills():
            header = QLabel(category.upper())
            header.setObjectName("section")
            self.skill_list_layout.addWidget(header)
            for s in items:
                self.skill_list_layout.addWidget(self._skill_row(s))
        self._update_active_skills_label()

    def _skill_row(self, s):
        """One selectable skill: checkbox + delete (custom) + description."""
        row = QWidget()
        rv = QVBoxLayout(row)
        rv.setContentsMargins(0, 0, 0, 0)
        rv.setSpacing(2)
        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(6)
        cb = QCheckBox(f"{s['icon']} {s['name']}")
        cb.setToolTip(s.get("description", ""))
        cb.setChecked(s["id"] in self._skill_selected)
        cb.stateChanged.connect(lambda state, sid=s["id"]: self._on_skill_toggled(sid, state))
        top.addWidget(cb, 1)
        if s.get("custom"):
            del_btn = QPushButton("✕")
            del_btn.setObjectName("danger")
            del_btn.setFixedWidth(30)
            del_btn.setToolTip("Delete this custom skill")
            del_btn.clicked.connect(lambda _, sid=s["id"]: self._delete_custom_skill(sid))
            top.addWidget(del_btn)
        else:
            top.addStretch()
        rv.addLayout(top)
        if s.get("description"):
            desc = QLabel(s["description"])
            desc.setObjectName("dim")
            desc.setWordWrap(True)
            rv.addWidget(desc)
        self.skill_checks[s["id"]] = cb
        return row

    def _update_active_skills_label(self):
        names = [f"{s['icon']} {s['name']}"
                 for s in skill_lib.all_skills() if s["id"] in self._skill_selected]
        self.skills_active_label.setText("Active: " + (", ".join(names) if names else "none"))
        self.main._update_skills_indicator()

    def _on_skill_toggled(self, skill_id, state):
        if int(state) != 0:
            self._skill_selected.add(skill_id)
        else:
            self._skill_selected.discard(skill_id)
        self._update_active_skills_label()
        self.main._save_settings()
        self.main._auto_context()   # skills change -> context size follows

    def set_skills(self, skill_ids):
        """Restore the ticked skills (unknown ids are dropped)."""
        known = {s["id"] for s in skill_lib.all_skills()}
        self._skill_selected = {s for s in skill_ids if s in known}
        self._rebuild_skill_list()

    def selected_skills(self):
        return [sid for sid, cb in self.skill_checks.items() if cb.isChecked()]

    def _create_skill(self):
        name = self.new_skill_name.text().strip()
        prompt = self.new_skill_prompt.toPlainText().strip()
        if not name or not prompt:
            QMessageBox.warning(self, "Missing info",
                                "A skill needs at least a name and its prompt text.")
            return
        skill = skill_lib.create_skill(name, self.new_skill_desc.text().strip(), prompt)
        self._skill_selected.add(skill["id"])
        self.new_skill_name.clear()
        self.new_skill_desc.clear()
        self.new_skill_prompt.clear()
        self._rebuild_skill_list()
        self.main._save_settings()

    def _delete_custom_skill(self, skill_id):
        reply = QMessageBox.question(self, "Delete skill",
                                     "Delete this custom skill? (built-in skills cannot be removed)")
        if reply != QMessageBox.StandardButton.Yes:
            return
        skill_lib.delete_skill(skill_id)
        self._skill_selected.discard(skill_id)
        self._rebuild_skill_list()
        self.main._save_settings()

    def _prompt_tab(self):
        w = QWidget()
        v = QVBoxLayout(w)
        self.sys_prompt_edit = QPlainTextEdit()
        self.sys_prompt_edit.setPlainText(DEFAULT_SYSTEM_PROMPT)
        self.sys_prompt_edit.setPlaceholderText("Define how the model should behave...")
        v.addWidget(self.sys_prompt_edit, 1)
        btns = QHBoxLayout()
        btns.addStretch()
        self.sys_reset_btn = QPushButton("Reset default")
        self.sys_reset_btn.setObjectName("ghost")
        btns.addWidget(self.sys_reset_btn)
        v.addLayout(btns)
        return w

    # ---------------------------------------------------------- wiring
    def _update_laya_status(self):
        """Small availability hint under the Laya controls."""
        if laya_lib._import_router() is None:
            self.laya_status.setText("Status: laya package not installed — filtering is "
                                     "off and plain ChromaDB ranking is used. "
                                     "Install with: pip install laya")
        else:
            state = "loaded" if self.main.laya_scorer.loaded else "ready (loads on first use)"
            err = f" Last error: {self.main.laya_scorer.error}" if self.main.laya_scorer.error else ""
            self.laya_status.setText(f"Status: available — {state}.{err}")

    def _connect(self):
        save = self.main._save_settings
        for w in (self.port_spin, self.ctx_spin, self.ngl_spin,
                  self.maxtok_spin, self.rag_topk):
            w.valueChanged.connect(save)
        self.temp_spin.valueChanged.connect(save)
        self.rag_mode.currentIndexChanged.connect(save)
        self.rag_enabled.stateChanged.connect(save)
        for w in (self.laya_initial_k, self.laya_final_k, self.laya_threshold):
            w.valueChanged.connect(save)
        self.laya_enabled.stateChanged.connect(save)
        self.laya_model.currentIndexChanged.connect(save)
        # grey the Laya controls out while filtering is disabled
        for w in (self.laya_initial_k, self.laya_final_k,
                  self.laya_threshold, self.laya_model, self.laya_status):
            self.laya_enabled.toggled.connect(w.setEnabled)
            w.setEnabled(self.laya_enabled.isChecked())
        # retrieval options also change how much has to fit into the context
        self.rag_enabled.stateChanged.connect(self.main._auto_context)
        self.rag_topk.valueChanged.connect(self.main._auto_context)
        self.sys_prompt_edit.textChanged.connect(save)
        self.sys_reset_btn.clicked.connect(
            lambda: self.sys_prompt_edit.setPlainText(DEFAULT_SYSTEM_PROMPT))
        self.dl_btn.clicked.connect(self.main._download_model)
        self.clear_index_btn.clicked.connect(self.main._clear_rag_index)
        self.add_skill_btn.clicked.connect(self._create_skill)
        self.open_skills_dir_btn.clicked.connect(self._open_skills_folder)
        self.tabs.currentChanged.connect(self._on_tab_changed)
