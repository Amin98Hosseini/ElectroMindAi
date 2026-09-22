"""Embedding functions.

- "fast" mode (default): stateless hash embeddings, ~1000x faster than MiniLM
  on CPU and fully offline.
- "accurate" mode: MiniLM via onnx (slow on CPU, better semantic matches;
  one-time model download).

The active mode is persisted in chroma_db/ef_name.txt so retrieval reuses the
same function that built the index.
"""
import hashlib
import math
import re

from core.config import CHROMA_DB_PATH

DB_PATH = CHROMA_DB_PATH
EF_FLAG = DB_PATH / "ef_name.txt"


class HashEmbeddingFunction:
    """Fast offline embeddings: stateless hashed term-frequency (L2 normalized)."""

    def __init__(self, dim: int = 384):
        self.dim = dim

    def __call__(self, input):
        out = []
        for text in input:
            vec = [0.0] * self.dim
            for m in re.findall(r"[a-z0-9_]+", str(text).lower()):
                # index the full token plus letter/digit sub-parts so that
                # part numbers match partially: query "stm32f103" hits
                # document token "stm32f103vgt6" via shared "stm32"/"103"
                toks = [m] + re.findall(r"[a-z]+|[0-9]+", m)
                for tok in toks:
                    h = int(hashlib.md5(tok.encode()).hexdigest(), 16) % self.dim
                    vec[h] += 1.0
            norm = math.sqrt(sum(v * v for v in vec)) or 1.0
            out.append([v / norm for v in vec])
        return out

    def embed_documents(self, input):
        return self(input)

    def embed_query(self, input):
        return self(input)

    def name(self):
        return "hash-tf-384"


def _write_ef_flag(name: str):
    DB_PATH.mkdir(exist_ok=True)
    EF_FLAG.write_text(name, encoding="utf-8")


def get_embedding_function(mode: str = "fast"):
    """mode='fast' -> instant hash embeddings.
    mode='accurate' -> MiniLM (one-time download), falls back to hash."""
    if mode == "fast":
        _write_ef_flag("hash")
        return HashEmbeddingFunction(), "hash"
    try:
        from chromadb.utils import embedding_functions
        ef = embedding_functions.DefaultEmbeddingFunction()
        ef(["ping"])  # force model download/load now so errors surface here
        _write_ef_flag("default")
        return ef, "default"
    except Exception:
        _write_ef_flag("hash")
        return HashEmbeddingFunction(), "hash"


def load_embedding_function():
    """Load the embedding function matching the flag saved at index time."""
    flag = EF_FLAG.read_text(encoding="utf-8").strip() if EF_FLAG.exists() else "hash"
    if flag == "hash":
        return HashEmbeddingFunction(), "hash"
    return get_embedding_function("accurate")
