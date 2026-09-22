"""Per-project chat persistence.

Each project directory (by resolved path hash) gets its own chat list.
Chats are stored as JSON files under ./chats/.

Data model (one file per chat):
    {
      "id": str,
      "project_dir": str,
      "title": str,
      "created": float,
      "updated": float,
      "messages": [{"role": "user"|"assistant"|"system", "content": str}]
    }

An index file maps project_dir_hash -> {"last": chat_id, "chats": [chat_id]}.
"""
import json
import hashlib
import time

from core.config import CHATS_DIR

INDEX_PATH = CHATS_DIR / "index.json"


def _project_key(project_dir: str) -> str:
    return hashlib.sha256(str(project_dir).encode("utf-8")).hexdigest()[:16]


def _ensure_dir():
    CHATS_DIR.mkdir(parents=True, exist_ok=True)


def _index() -> dict:
    _ensure_dir()
    try:
        return json.loads(INDEX_PATH.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}


def _save_index(idx: dict):
    _ensure_dir()
    INDEX_PATH.write_text(json.dumps(idx, indent=2), encoding="utf-8")


def _chat_path(chat_id: str):
    return CHATS_DIR / f"{chat_id}.json"


def list_chats(project_dir: str):
    """Return chats for the project, newest-first."""
    key = _project_key(project_dir)
    idx = _index()
    entry = idx.get(key, {})
    chat_ids = entry.get("chats", [])
    results = []
    for cid in chat_ids:
        try:
            d = json.loads(_chat_path(cid).read_text(encoding="utf-8"))
            results.append(d)
        except Exception:
            continue
    results.sort(key=lambda c: c.get("updated", 0), reverse=True)
    return results


def load_chat(chat_id: str):
    try:
        return json.loads(_chat_path(chat_id).read_text(encoding="utf-8"))
    except Exception:
        return None


def new_chat(project_dir: str, title: str = "") -> dict:
    _ensure_dir()
    chat_id = hashlib.sha256(f"{time.time()}".encode()).hexdigest()[:12]
    now = time.time()
    chat = {
        "id": chat_id,
        "project_dir": str(project_dir),
        "title": title or "New chat",
        "created": now,
        "updated": now,
        "messages": [],
    }
    _chat_path(chat_id).write_text(json.dumps(chat), encoding="utf-8")
    idx = _index()
    key = _project_key(project_dir)
    if key not in idx:
        idx[key] = {"last": chat_id, "chats": []}
    idx[key]["last"] = chat_id
    if chat_id not in idx[key]["chats"]:
        idx[key]["chats"].append(chat_id)
    _save_index(idx)
    return chat


def save_chat(chat: dict):
    """Update a chat file. Merges with the stored copy so a partial dict
    (e.g. only {"id", "project_dir"}) never wipes title or messages."""
    existing = load_chat(chat["id"]) or {}
    existing.update(chat)
    existing["updated"] = time.time()
    _ensure_dir()
    _chat_path(chat["id"]).write_text(json.dumps(existing), encoding="utf-8")
    idx = _index()
    key = _project_key(existing["project_dir"])
    if key not in idx:
        idx[key] = {"last": chat["id"], "chats": []}
    idx[key]["last"] = chat["id"]
    if chat["id"] not in idx[key]["chats"]:
        idx[key]["chats"].append(chat["id"])
    _save_index(idx)


def append_messages(chat_id: str, project_dir: str, messages: list):
    chat = load_chat(chat_id) or new_chat(project_dir)
    chat["messages"] = list(messages)
    chat["project_dir"] = str(project_dir)
    save_chat(chat)


def delete_chat(chat_id: str, project_dir: str):
    try:
        _chat_path(chat_id).unlink()
    except FileNotFoundError:
        pass
    idx = _index()
    key = _project_key(project_dir)
    if key in idx:
        idx[key]["chats"] = [c for c in idx[key]["chats"] if c != chat_id]
        if idx[key]["last"] == chat_id:
            idx[key]["last"] = idx[key]["chats"][-1] if idx[key]["chats"] else None
        if not idx[key]["chats"]:
            idx.pop(key, None)
    _save_index(idx)


def set_last(project_dir: str, chat_id: str | None):
    idx = _index()
    key = _project_key(project_dir)
    if chat_id is None:
        idx.pop(key, None)
    else:
        idx.setdefault(key, {})["last"] = chat_id
    _save_index(idx)


def last_chat_id(project_dir: str) -> str | None:
    idx = _index()
    return idx.get(_project_key(project_dir), {}).get("last")


def title_for(project_dir: str, messages: list) -> str:
    """Derive a title from the first user message."""
    for m in messages:
        if m.get("role") == "user" and m.get("content"):
            t = m["content"].strip().replace("\n", " ").strip()
            return t[:80] + ("…" if len(t) > 80 else "")
    return "New chat"
