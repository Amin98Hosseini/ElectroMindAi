"""Llama.cpp GUI - beautiful PyQt6 chat app for local GGUF models.

Thin launcher: the implementation lives in the ui/ package.
Run with:  python gui.py
"""
import sys
from pathlib import Path

# Allow running from anywhere: make the project root importable.
sys.path.insert(0, str(Path(__file__).parent))

# CRITICAL: onnxruntime MUST be imported BEFORE any Qt module.
# Importing it after QApplication is created segfaults the process
# (DLL initialization conflict between onnxruntime/OpenMP and Qt6).
# The "Accurate" RAG embedding mode uses onnxruntime, so we force the
# import here, at the very start, while the process is still "clean".
try:
    import onnxruntime  # noqa: F401
except Exception:
    pass  # not installed / broken -> rag falls back to fast hash embeddings

from ui.main_window import run_app

if __name__ == "__main__":
    run_app()
