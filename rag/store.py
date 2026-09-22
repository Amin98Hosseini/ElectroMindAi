"""ChromaDB persistence, manifest bookkeeping, retrieval and context building."""
import json
import os

from core.config import CHROMA_DB_PATH
from rag.embeddings import load_embedding_function

DB_PATH = CHROMA_DB_PATH
MANIFEST = DB_PATH / "manifest.json"
COLLECTION = "project_docs"


def get_client(ef):
    """Open the persistent ChromaDB client + collection.

    If the persisted collection was built with a different embedding function
    (e.g. mode switch), it is dropped and recreated.
    """
    import chromadb
    DB_PATH.mkdir(exist_ok=True)
    client = chromadb.PersistentClient(path=str(DB_PATH))
    try:
        col = client.get_or_create_collection(COLLECTION, embedding_function=ef)
    except ValueError:
        try:
            client.delete_collection(COLLECTION)
        except Exception:
            pass
        col = client.get_or_create_collection(COLLECTION, embedding_function=ef)
    return client, col


# backward-compatible alias used by the indexer
_client = get_client


def load_manifest() -> dict:
    try:
        return json.loads(MANIFEST.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_manifest(data):
    MANIFEST.write_text(json.dumps(data), encoding="utf-8")


def file_sig(f):
    """(size, mtime) signature used for incremental indexing."""
    try:
        st = f.stat()
        return st.st_size, st.st_mtime
    except OSError:
        return -1, -1


def manifest_info():
    m = load_manifest()
    if not m:
        return {"indexed": False}
    return {"indexed": True, "root": m.get("root"), "ef": m.get("ef"),
            "files": len(m.get("files", {}))}


def index_stats():
    if not DB_PATH.exists():
        return {"files": 0, "chunks": 0}
    manifest = load_manifest()
    files = len(manifest.get("files", {}))
    try:
        ef, _ = load_embedding_function()
        _, col = get_client(ef)
        return {"files": files, "chunks": col.count()}
    except Exception:
        return {"files": files, "chunks": 0}


def clear_index():
    try:
        ef, _ = load_embedding_function()
        client, _ = get_client(ef)
        client.delete_collection(COLLECTION)
    except Exception:
        pass
    for p in (MANIFEST, DB_PATH / "ef_name.txt"):
        try:
            if p.exists():
                os.remove(p)
        except OSError:
            pass


def retrieve(query: str, n_results: int = 4):
    ef, _ = load_embedding_function()
    _, col = get_client(ef)
    res = col.query(query_texts=[query], n_results=n_results,
                    include=["documents", "metadatas", "distances"])
    out = []
    docs = res.get("documents", [[]])[0]
    metas = res.get("metadatas", [[]])[0]
    for doc, meta in zip(docs, metas):
        out.append({"text": doc, "path": (meta or {}).get("path", "?")})
    return out


def build_context(snippets, max_chars: int = 6000):
    parts, used = [], 0
    for s in snippets:
        t = s["text"]
        if used + len(t) > max_chars:
            t = t[: max_chars - used]
        parts.append(t)
        used += len(t)
        if used >= max_chars:
            break
    return "\n\n---\n\n".join(parts)
