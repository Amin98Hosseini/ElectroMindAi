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
├── settings.json       # Saved settings (project dir, system prompt)
├── core/               # GUI-independent logic
│   ├── config.py       #   central paths
│   ├── llama.py        #   llama-server process control
│   ├── http_utils.py   #   proxy-safe localhost HTTP / port checks
│   ├── chat_store.py   #   per-project chat persistence (./chats/)
│   ├── catalog.py      #   models.json loader
│   └── prompts.py      #   default system prompt
├── rag/                # RAG pipeline
│   ├── files.py        #   file discovery + text/PDF/DOCX extraction
│   ├── chunking.py     #   overlapping text chunking
│   ├── embeddings.py   #   fast (hash) + accurate (MiniLM) embeddings
│   ├── store.py        #   ChromaDB persistence + retrieval
│   └── indexer.py      #   scan → load → chunk → embed → store
├── ui/                 # PyQt6 GUI
│   ├── main_window.py  #   main window (chat, models, RAG, settings)
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

### Server settings (in-app, saved automatically)
| Setting | Meaning |
|---|---|
| Port | localhost port for `llama-server` (default 8081) |
| Context | model context window in tokens (longer = more chat memory, more RAM) |
| GPU layers | how many model layers offload to GPU (0 = CPU only) |
| Temperature | creativity (0 = deterministic, 1+ = creative) |
| Max tokens | response length limit (-1 = unlimited) |

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

---

## 🔒 Privacy & Safety

- Everything runs locally; only **model downloads** (GGUF and the optional MiniLM embedding model) touch the internet.
- The default system prompt includes electrical-safety guidance (mains voltage, Li-ion/LiPo handling, ESD), but always **verify critical values against datasheets** — the assistant can make mistakes.

---

## 👨‍💻 Credits

**ElectroMind** was developed by **Mohammad Amin Khadel Al Hosseini**, with AI pair-programming assistance.

The icon is a **brain-circuit** — a chip at the center with circuit-trace "hemispheres" — representing the union of electronics and a local AI mind.
