"""Central paths and file locations used across the whole application."""
from pathlib import Path

# Project root (this file lives in <root>/core/)
BASE_DIR = Path(__file__).parent.parent

# llama.cpp
LLAMA_SERVER = BASE_DIR / "llama-X64" / "llama-server.exe"
LOG_PATH = BASE_DIR / "llama_server.log"

# User data
MODEL_DIR = BASE_DIR / "Model"
MODELS_JSON = BASE_DIR / "models.json"
SETTINGS_PATH = BASE_DIR / "settings.json"
CHATS_DIR = BASE_DIR / "chats"
CHROMA_DB_PATH = BASE_DIR / "chroma_db"
