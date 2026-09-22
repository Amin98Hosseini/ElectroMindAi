"""Indexing pipeline: scan -> load (parallel) -> chunk -> embed -> store.

Incremental: a manifest (size+mtime per file) skips unchanged files on
re-index; switching project or embedding mode triggers a full re-index.
"""
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from rag.chunking import chunk_text
from rag.embeddings import get_embedding_function
from rag.files import iter_files, load_file
from rag.store import get_client, load_manifest, save_manifest, file_sig, COLLECTION

ADD_BATCH = 256
LOAD_WORKERS = 8


def index_directory(root, progress=None, mode: str = "fast"):
    """Scan -> load (parallel) -> chunk -> embed -> store. Incremental via manifest."""
    t0 = time.time()
    root = Path(root).resolve()
    files, unsupported = iter_files(root)
    total = len(files)
    subfolders = len({str(f.parent.relative_to(root)) for f in files})
    if progress:
        progress("scan", total, total)

    ef, ef_name = get_embedding_function(mode)
    manifest = load_manifest()
    same_root = manifest.get("root") == str(root)
    same_ef = manifest.get("ef") == ef_name
    old_files = manifest.get("files", {}) if (same_root and same_ef) else {}

    client, col = get_client(ef)
    if not (same_root and same_ef):
        # different project or embedding mode -> full re-index
        try:
            client.delete_collection(COLLECTION)
        except Exception:
            pass
        client, col = get_client(ef)
        old_files = {}

    # classify files
    current = {}
    to_process, skipped = [], 0
    for f in files:
        rel = str(f.relative_to(root))
        sig = file_sig(f)
        current[rel] = {"size": sig[0], "mtime": sig[1], "chunks": 0}
        old = old_files.get(rel)
        if old and old.get("size") == sig[0] and old.get("mtime") == sig[1]:
            current[rel]["chunks"] = old.get("chunks", 0)
            skipped += 1
        else:
            to_process.append((f, rel))

    removed = [r for r in old_files if r not in current]
    changed = [rel for _, rel in to_process if rel in old_files]
    stale = removed + changed
    if stale:
        try:
            col.delete(where={"path": {"$in": stale}})
        except Exception:
            for rel in stale:  # fallback: one-by-one
                try:
                    col.delete(where={"path": rel})
                except Exception:
                    pass

    # parallel load + chunk only the new/changed files
    ids, docs, metas = [], [], []
    n_new_chunks = 0
    thin_pdfs = []  # PDFs with almost no text layer (scanned images?)

    def _load_one(item):
        f, rel = item
        try:
            text = load_file(f)
        except Exception:
            text = ""
        if not text.strip():
            return rel, [], False
        thin = f.suffix.lower() == ".pdf" and len(text.strip()) < 100
        return rel, chunk_text(text), thin

    if to_process:
        with ThreadPoolExecutor(max_workers=LOAD_WORKERS) as pool:
            for i, (rel, chunks, thin) in enumerate(pool.map(_load_one, to_process), 1):
                current[rel]["chunks"] = len(chunks)
                if thin:
                    thin_pdfs.append(rel)
                for j, ch in enumerate(chunks):
                    ids.append(f"{rel}#{j}")
                    docs.append(f"[{rel}]\n{ch}")
                    metas.append({"path": rel, "chunk": j})
                n_new_chunks += len(chunks)
                if progress and (i % 10 == 0 or i == len(to_process)):
                    progress("load", i, len(to_process))
    if progress:
        progress("load", len(to_process), max(len(to_process), 1))

    for k in range(0, len(ids), ADD_BATCH):
        col.add(ids=ids[k:k + ADD_BATCH], documents=docs[k:k + ADD_BATCH],
                metadatas=metas[k:k + ADD_BATCH])
        if progress:
            progress("embed", min(k + ADD_BATCH, len(ids)), max(len(ids), 1))
    if not ids and progress:
        progress("embed", 1, 1)

    save_manifest({"root": str(root), "ef": ef_name, "files": current})
    n_total = col.count()
    dt = time.time() - t0
    # summarize skipped files by extension so the user knows what was left out
    skip_exts = {}
    for p, reason in unsupported:
        if reason == "unsupported":
            skip_exts[p.suffix.lower()] = skip_exts.get(p.suffix.lower(), 0) + 1
    too_big = sum(1 for _, reason in unsupported if reason == "too-big")
    return {"files": total, "new": len(to_process), "skipped": skipped,
            "chunks": n_total, "new_chunks": n_new_chunks,
            "ef": ef_name, "seconds": round(dt, 1),
            "subfolders": subfolders,
            "unsupported": len([r for _, r in unsupported if r == "unsupported"]),
            "unsupported_exts": skip_exts, "too_big": too_big,
            "thin_pdfs": thin_pdfs}


def check_changes(root):
    """Fast stat-only check: is this dir already indexed, and what is pending?"""
    root = str(Path(root).resolve())
    m = load_manifest()
    if not m or m.get("root") != root:
        return {"indexed": False, "new": 0, "changed": 0, "removed": 0}
    old_files = m.get("files", {})
    try:
        files, _ = iter_files(Path(root))
    except Exception:
        return {"indexed": True, "new": 0, "changed": 0, "removed": 0}
    current, new, changed = set(), 0, 0
    for f in files:
        rel = str(f.relative_to(root))
        current.add(rel)
        sig = file_sig(f)
        old = old_files.get(rel)
        if not old:
            new += 1
        elif old.get("size") != sig[0] or old.get("mtime") != sig[1]:
            changed += 1
    removed = sum(1 for r in old_files if r not in current)
    return {"indexed": True, "new": new, "changed": changed, "removed": removed}
