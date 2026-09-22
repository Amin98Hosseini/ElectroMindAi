"""Text chunking: split documents into overlapping chunks on line boundaries."""

CHUNK_SIZE = 1500
CHUNK_OVERLAP = 150


def chunk_text(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP):
    """Split text into overlapping chunks on line boundaries."""
    lines = text.splitlines()
    chunks, current = [], []
    cur_len = 0
    for line in lines:
        current.append(line)
        cur_len += len(line) + 1
        if cur_len >= size:
            chunks.append("\n".join(current).strip())
            tail, tail_len = [], 0
            for ln in reversed(current):
                tail.append(ln)
                tail_len += len(ln) + 1
                if tail_len >= overlap:
                    break
            current = list(reversed(tail))
            cur_len = tail_len
    if current and "\n".join(current).strip():
        chunks.append("\n".join(current).strip())
    return [c for c in chunks if c]
