"""Text extraction: project file discovery and content readers (txt/pdf/docx)."""
import re
from pathlib import Path

TEXT_EXTS = {
    ".txt", ".md", ".markdown", ".rst",
    ".py", ".c", ".h", ".hpp", ".cpp", ".cc", ".cxx",
    ".js", ".ts", ".jsx", ".tsx", ".java", ".go", ".rs",
    ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg",
    ".html", ".css", ".xml", ".sql", ".sh", ".bat", ".ps1",
    ".csv", ".log",
}
# Native Altium/CAD binaries carry no extractable text layer -> reported as skipped
BINARY_NO_TEXT = {".schdoc", ".pcbdoc", ".prjpcd", ".prjpcb", ".cmpcb",
                  ".brd", ".sch", ".dsn", ".exe", ".dll", ".zip", ".rar", ".7z"}
PDF_EXTS = {".pdf"}
DOC_EXTS = {".docx"}
SUPPORTED = TEXT_EXTS | PDF_EXTS | DOC_EXTS

SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv", "venv",
             "build", "dist", ".idea", ".vscode", "chroma_db"}
MAX_FILE_MB = 5


def iter_files(root: Path):
    """Walk root recursively (all folders/subfolders).

    Returns (found, skipped) where skipped is a list of (path, reason):
    'unsupported' (no text extractor, e.g. .SchDoc/.PcbDoc binaries) or
    'too-big'. Junk directories are silently ignored.
    """
    root = Path(root)
    found, skipped = [], []
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        if any(part in SKIP_DIRS for part in p.parts):
            continue
        ext = p.suffix.lower()
        if ext not in SUPPORTED:
            if ext:  # files without extension are ignored silently
                skipped.append((p, "unsupported"))
            continue
        try:
            if p.stat().st_size > MAX_FILE_MB * 1024 * 1024:
                skipped.append((p, "too-big"))
                continue
        except OSError:
            continue
        found.append(p)
    return found, skipped


def read_text_file(path: Path) -> str:
    for enc in ("utf-8", "utf-8-sig", "cp1252", "latin-1"):
        try:
            return path.read_text(encoding=enc)
        except (UnicodeError, OSError):
            continue
    return ""


def _normalize_pdf_text(txt: str) -> str:
    """Clean up CAD/schematic PDF text: Altium exports place every glyph
    separately, so raw extraction is full of stray line breaks and spaces."""
    lines = [ln.strip() for ln in txt.splitlines()]
    lines = [ln for ln in lines if ln]  # drop empty visual lines
    txt = "\n".join(lines)
    # rejoin word endings broken across lines in CAD exports:
    # e.g. "Titl e" -> "Title", "Siz e" -> "Size"
    # (requires 2+ letters before the space so "a test" is untouched)
    txt = re.sub(r"([A-Za-z]{2,}) ([a-z])\b", r"\1\2", txt)
    txt = re.sub(r"\n{3,}", "\n\n", txt)
    return txt.strip()


def read_pdf(path: Path) -> str:
    """Extract text from a PDF, page by page. Tries layout mode first
    (much better for schematics/CAD exports), falls back to plain mode."""
    from pypdf import PdfReader
    try:
        reader = PdfReader(str(path))
    except Exception:
        return ""
    parts = []
    for i, page in enumerate(reader.pages, 1):
        txt = ""
        for mode in ("layout", "plain"):
            try:
                if mode == "layout":
                    txt = page.extract_text(extraction_mode="layout") or ""
                else:
                    txt = page.extract_text() or ""
            except Exception:
                txt = ""
            if txt and len(txt.strip()) >= 20:
                break
        txt = _normalize_pdf_text(txt)
        if txt:
            parts.append(f"[page {i}]\n{txt}")
    return "\n\n".join(parts)


def read_docx(path: Path) -> str:
    import docx
    doc = docx.Document(str(path))
    parts = [p.text for p in doc.paragraphs if p.text.strip()]
    for table in doc.tables:
        for row in table.rows:
            parts.append(" | ".join(c.text.strip() for c in row.cells if c.text.strip()))
    return "\n".join(parts)


def load_file(path: Path) -> str:
    ext = path.suffix.lower()
    if ext in PDF_EXTS:
        return read_pdf(path)
    if ext in DOC_EXTS:
        return read_docx(path)
    return read_text_file(path)
