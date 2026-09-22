"""RAG package: load project files, chunk them, index into ChromaDB, retrieve context.

Speed design:
- "fast" mode (default): stateless hash embeddings, ~1000x faster than MiniLM on CPU.
- "accurate" mode: MiniLM via onnx (slow on CPU, better semantic matches).
- Incremental: a manifest (size+mtime per file) skips unchanged files on re-index.
- Parallel file loading + large add batches.

Submodules:
    rag.files       -- file discovery + text/PDF/DOCX extraction
    rag.chunking    -- overlapping text chunking
    rag.embeddings  -- fast (hash) and accurate (MiniLM) embedding functions
    rag.store       -- ChromaDB persistence, manifest, retrieval, context building
    rag.indexer     -- the indexing pipeline (scan -> load -> chunk -> embed -> store)
"""
from rag.files import iter_files, read_text_file, read_pdf, read_docx, load_file
from rag.chunking import chunk_text
from rag.embeddings import (HashEmbeddingFunction, get_embedding_function,
                            load_embedding_function)
from rag.store import (retrieve, build_context, index_stats, clear_index,
                        manifest_info)
from rag.indexer import index_directory, check_changes

__all__ = [
    "iter_files", "read_text_file", "read_pdf", "read_docx", "load_file",
    "chunk_text",
    "HashEmbeddingFunction", "get_embedding_function", "load_embedding_function",
    "retrieve", "build_context", "index_stats", "clear_index", "manifest_info",
    "index_directory", "check_changes",
]
