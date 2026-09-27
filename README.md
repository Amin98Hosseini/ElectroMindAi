# ⚡ ElectroMind

<p align="center"><img src="assets/icon.png" width="128" alt="ElectroMind icon"/></p>

**Your fully local, offline AI copilot for electronics & embedded projects.**

> 👨‍💻 **Developed by Mohammad Amin Khadel Al Hosseini** — with AI pair-programming assistance.

ElectroMind bundles a [llama.cpp](https://github.com/ggml-org/llama.cpp) inference server with a PyQt6 chat GUI and a RAG (Retrieval-Augmented Generation) engine. It indexes **your** project folder — firmware, schematics PDFs, datasheets, docs — so the model answers questions grounded in *your* schematics, code, and datasheets, with file citations.

> 🔒 **No cloud. No API keys. No telemetry.** Your code, schematics, and chats never leave your machine. Only model downloads touch the internet.

---

## ✨ Features

### 💬 Chat
- **Local GGUF models** via the bundled `llama-server` (Qwen3, Gemma 3, or any `.gguf`)
- **Streaming answers** with chat bubbles + a separate *thinking* bubble for reasoning models (Qwen3)
- **Persistent chat history per project** — multiple named chats, auto-titled from your first question, clickable to reopen and continue
- **Context-window memory management** — very long chats are trimmed automatically before sending (full history stays saved on disk), so old conversations never break
- **Editable system prompt** with an electronics-expert default (circuit design, MCUs, protocols, debugging, safety warnings)
- **Skills** 🛠 — tick one or more *expert roles* (26 built-in: PCB, STM32, ESP32, RF, power, RTOS…) and their instructions are injected into the system prompt for every message — see [Skills](#-skills-1)

### 🤖 Models
- Model list from `./Model` with sizes; **in-app download** from the catalog in `models.json` with progress bar
- Server settings: **port, context size, GPU layers, temperature, max tokens**
- One-click start/stop with health checking; automatic cleanup of orphaned servers

### 📁 Project Knowledge (RAG)
- Indexes source code, config, docs, **PDF** (layout mode, tuned for CAD/schematic exports), and **DOCX**
- Two embedding modes:
  - **⚡ Fast** — instant, offline hash vectors; great for part numbers (`stm32f103` matches `stm32f103vgt6`)
  - **🎯 Accurate** — MiniLM embeddings, better semantic matching (one-time model download)
- **Incremental indexing** — only new/changed files are re-processed
- Answers cite the **source files** used as context

---

## 🚀 Quick Start

```bash
# 1. Install Python dependencies (Python 3.10+, Windows x64)
pip install -r requirements.txt

# 2. Get a model: place a .gguf file into ./Model
#    or download one from inside the app (dropdown, e.g. Qwen3 4B)

# 3. Run
python gui.py
```

In the app:
1. Select a model → **▶ Start server** → wait for `● Ready`
2. **📂 Open** your project folder → **🔍 Analyze** to index it
3. Ask questions — answers cite your project files

**Terminal-only chat** (no GUI): `python run_llama.py`

> 💡 Tip: start with **Qwen3 4B (Q4_K_M)** (~2.5 GB) for a good CPU speed/quality balance. Set **GPU layers > 0** with a GPU-enabled llama.cpp build for speed.

---

## 📂 Project Structure

```
ElectroMind/
├── gui.py              # GUI launcher (imports onnxruntime BEFORE Qt — critical)
├── run_llama.py        # Terminal-only chat client
├── requirements.txt    # Python dependencies
├── models.json         # Catalog of downloadable GGUF models
├── settings.json       # Saved settings (project dir, system prompt, port, skills, RAG)
├── skills/             # Skill definitions — one .md file per expert role
├── core/               # GUI-independent logic
│   ├── config.py       #   central paths (incl. SKILLS_DIR)
│   ├── llama.py        #   llama-server process control
│   ├── http_utils.py   #   proxy-safe localhost HTTP / port checks
│   ├── chat_store.py   #   per-project chat persistence (./chats/)
│   ├── catalog.py      #   models.json loader
│   ├── skills.py       #   skill file parsing, prompt building, CRUD for custom skills
│   └── prompts.py      #   default system prompt
├── rag/                # RAG pipeline
│   ├── files.py        #   file discovery + text/PDF/DOCX extraction
│   ├── chunking.py     #   overlapping text chunking
│   ├── embeddings.py   #   fast (hash) + accurate (MiniLM) embeddings
│   ├── store.py        #   ChromaDB persistence + retrieval
│   └── indexer.py      #   scan → load → chunk → embed → store
├── ui/                 # PyQt6 GUI
│   ├── main_window.py  #   main window (chat, models, RAG, skills indicator, context auto-sizing)
│   ├── settings_dialog.py # tabbed settings window (Server / Models / RAG / Skills / prompt)
│   ├── workers.py      #   background threads (server, index, download, chat)
│   └── theme.py        #   dark theme + chat bubble styles
├── llama-X64/          # Bundled llama.cpp Windows binaries
├── Model/              # Your .gguf models go here
├── chroma_db/          # Vector index (created at runtime)
└── chats/              # Saved chat histories (created at runtime)
```

---

## 🧠 How the RAG works

1. **Scan** — walks the project folder, skipping `.git`, `__pycache__`, `node_modules`, `build`, … (files > 5 MB are reported and skipped)
2. **Load & chunk** — extracts text (PDF via `pypdf` layout mode with CAD-export cleanup; DOCX incl. tables) and splits into ~1500-char overlapping chunks
3. **Embed & store** — chunks go into ChromaDB (`./chroma_db`) with their relative path as metadata
4. **Retrieve** — each question pulls the top-k (default 4) most similar chunks into the prompt as *PROJECT CONTEXT*, and sources are shown under the answer

Switching project folder or embedding mode triggers a re-index; otherwise indexing is incremental.

---

## 🛠 Skills — pick the expert you need

Skills turn the assistant into a **specialist**: tick one or more in **⚙ Settings ▸ 🛠 Skills**
and their instructions are prepended to the system prompt of every message, so you can combine
them freely (e.g. **PCB Designer + STM32 Developer + Power Supply Designer**).

- **26 built-in skills** in five groups:
  | Group | Skills |
  |---|---|
  | Hardware & Power | Schematic & Circuit Designer, Analog & Signal-Conditioning, Power Supply, Battery & BMS, PCB Designer, Motor & Motion Control, Sensor & Instrumentation |
  | RF, Digital & Control | RF & Antenna, FPGA / RTL (Verilog–VHDL), Signal Processing / DSP, Control Systems |
  | Firmware & Microcontrollers | Embedded Developer, STM32, ESP32 / Arduino, AVR / PIC (8-bit), RTOS / FreeRTOS, Bus & Protocol, Linux & Driver, IoT & Cloud |
  | Software | Python Developer, C / C++ Software Engineer |
  | Quality, Safety & Debugging | Debugging & Test, Test & Validation, Safety & Security, PLC & Industrial Automation, Robotics |
- **Every skill is a Markdown file** in `./skills` — edit it and the change is live on the next
  Skills tab open; drop in a new `.md` and it appears automatically. Built-ins ship as files, so
  you can customize even them (keep the `**id:**` field to preserve saved selections).
- **Create your own** in the dialog (name + one-line description + instructions) — it is written
  to `./skills/<name>.md` and can be deleted from the same list.
- **Context-aware**: the app estimates the prompt size of the ticked skills and **auto-sizes the
  context window** (Settings ▸ Server) so everything fits; if a request would still overflow,
  the system message is trimmed (project context first, then skills, then prompt) and you are told
  exactly what was cut.
- The left panel shows the active skills at a glance (`Skills: …`); an **Active:** line inside the
  dialog mirrors your current selection.

### Skill file format

One `./skills/<Skill Name>.md` file per skill:

```markdown
# ⚡ Schematic & Circuit Designer

**id:** schematic
**category:** Hardware & Power
**description:** Topology choice, component values, ratings and full net review.

## Instructions

Act as a senior schematic designer ...
- **Calculate, do not guess**: show the formula and the numbers ...
```

- `# <icon> <Name>` — first line: emoji + display name (no emoji → default ⭐ icon, file name shown)
- `**id:**` — stable identifier saved in `settings.json` (auto-derived from the name if missing)
- `**category:**` — group heading in the dialog; use `⭐ My skills` for your own
- `**description:**` — one-liner shown as a tooltip under the checkbox
- `## Instructions` (or `## Prompt`) — the text injected into the system prompt while ticked

All fields except the name/instructions are optional; files are re-read each time the Skills tab
opens, so no restart is needed. If `./skills` is missing or empty, the app falls back to the
built-in skill set compiled into `core/skills.py`.

---

## ⚙️ Configuration

### `models.json` — add your own downloadable models
```json
{
  "name": "Qwen3 8B (Q4_K_M) — smarter, heavier",
  "filename": "Qwen3-8B-Q4_K_M.gguf",
  "url": "https://huggingface.co/Qwen/Qwen3-8B-GGUF/resolve/main/Qwen3-8B-Q4_K_M.gguf",
  "size": "~5.0 GB",
  "description": "Noticeably smarter than 4B. Needs ~8 GB RAM."
}
```

### Settings window (in-app, saved automatically to `settings.json`)

Everything configurable now lives in one tabbed **⚙ Settings** dialog (Server / Models /
Project-RAG / Skills / System prompt); the left panel keeps a compact model · server · project
view plus a live `Skills:` indicator.

**Server tab**
| Setting | Meaning |
|---|---|
| Port | localhost port for `llama-server` (default 8081) |
| Context | model context window in tokens (longer = more chat memory, more RAM); **auto-sized** to fit system prompt + skills + RAG, clamped to 4096–32768 |
| GPU layers | how many model layers offload to GPU (0 = CPU only) |
| Temperature | creativity (0 = deterministic, 1+ = creative) |
| Max tokens | response length limit (-1 = unlimited) |

**Skills tab** — tick expert roles, create/delete custom ones, open the `./skills` folder.
Selections are stored as skill **ids** in `settings.json` (`"skills": [...]`), so they survive
renames of the file, and unknown ids are dropped silently on load.

---

## 🔧 Troubleshooting

| Problem | Fix |
|---|---|
| App closes instantly / silently crashes after Analyze | Fixed by design: `gui.py` imports `onnxruntime` **before** Qt (a Windows DLL conflict otherwise segfaults). If you ever see it again, delete only `chroma_db\ef_name.txt` and restart. |
| `Port 8081 is already in use` | Pick another port, or stop the other server. The app also kills leftover `llama-server.exe` on start. |
| Server fails to start | Check `llama_server.log` (tailed live in the GUI log panel). |
| `Skipped N unsupported files (.SchDoc …)` | Native CAD binaries have no text layer — export them as PDF and re-Analyze. |
| PDFs reported as "almost no text" | They're scanned images; the model is text-only and can't read images. |
| Model can't view images | Expected — local text-only models have no vision. Describe the image instead. |
| Requests fail behind a system proxy | Already handled — localhost requests bypass the Windows system proxy. |
| My ticked skills vanished after restart | Their `.md` files were renamed/deleted or the `**id:**` field changed — selections are stored by id. Keep ids stable. |
| `⚠️ Context limit …: trimmed skills` in the chat | The system prompt + skills + RAG exceeded the context; the app trims project context → skills → prompt to stay safe. Raise **Context** in Settings ▸ Server and restart the server. |
| A new skill file doesn't appear | It must end in `.md` in `./skills`, be valid UTF-8, and have a `# ` title plus `## Instructions`. The list refreshes when you reopen the Skills tab. |
| Deleted a built-in skill by editing its file | Built-ins can't be deleted in-app; restore the original file content (or delete the file — the built-in definition from `core/skills.py` is used as fallback when no file defines that id). |

---

## 🔒 Privacy & Safety

- Everything runs locally; only **model downloads** (GGUF and the optional MiniLM embedding model) touch the internet.
- The default system prompt includes electrical-safety guidance (mains voltage, Li-ion/LiPo handling, ESD), but always **verify critical values against datasheets** — the assistant can make mistakes.

---

## 👨‍💻 Credits

**ElectroMind** was developed by **Mohammad Amin Khadel Al Hosseini**, with AI pair-programming assistance.

The icon is a **brain-circuit** — a chip at the center with circuit-trace "hemispheres" — representing the union of electronics and a local AI mind.
