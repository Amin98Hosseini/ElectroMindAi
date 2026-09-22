"""Downloadable-model catalog (models.json)."""
import json

from core.config import MODELS_JSON


def load_catalog():
    """Read models.json -> list of {name, filename, url, size, description}."""
    try:
        data = json.loads(MODELS_JSON.read_text(encoding="utf-8"))
        models = data.get("models", [])
        return [m for m in models if m.get("name") and m.get("url") and m.get("filename")]
    except Exception:
        return []
