"""Extract guideline text into citation-ready chunks (workflow step 7).

Official documents (ICAR / UAS / Karnataka Department of Agriculture package of
practices) are NOT bundled in this repository: their licences and sizes vary, so
``guidelines_pdfs/`` is git-ignored for PDFs and a download script is provided instead.
A small clearly-labelled internal demo note is committed so the retrieval pipeline can be
demonstrated end to end without pretending to be an official publication.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

from src.config.settings import project_path

CHUNK_CHARS = 900
CHUNK_OVERLAP = 150
TEXT_SUFFIXES = {".txt", ".md"}


@dataclass
class Chunk:
    """One retrievable passage with its provenance."""

    chunk_id: str
    doc_id: str
    title: str
    page: int
    text: str
    source_file: str


def _clean(text: str) -> str:
    """Collapse whitespace and normalise line endings."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _split(text: str, title: str, doc_id: str, page: int, source_file: str, out: list[Chunk]) -> None:
    """Split one page into overlapping chunks."""
    text = _clean(text)
    if not text:
        return
    start = 0
    index = 0
    while start < len(text):
        end = min(start + CHUNK_CHARS, len(text))
        if end < len(text):
            # Prefer to break on a paragraph boundary near the end of the window.
            boundary = text.rfind("\n\n", start, end)
            if boundary > start + CHUNK_CHARS // 2:
                end = boundary
        piece = text[start:end].strip()
        if piece:
            out.append(
                Chunk(
                    chunk_id=f"{doc_id}-p{page}-c{index}",
                    doc_id=doc_id,
                    title=title,
                    page=page,
                    text=piece,
                    source_file=source_file,
                )
            )
            index += 1
        start = end - CHUNK_OVERLAP if end - CHUNK_OVERLAP > start else end


def _read_pdf(path: Path, out: list[Chunk]) -> bool:
    """Extract a PDF page by page with PyMuPDF. Returns False if PyMuPDF is unavailable."""
    try:
        import fitz  # PyMuPDF
    except ModuleNotFoundError:
        print(f"  PyMuPDF not installed - skipping {path.name} (pip install PyMuPDF)")
        return False
    doc_id = path.stem
    with fitz.open(path) as document:
        for page_number, page in enumerate(document, start=1):
            _split(page.get_text(), document.metadata.get("title") or path.stem, doc_id, page_number, path.name, out)
    return True


def extract_documents(folder: Path | None = None) -> list[Chunk]:
    """Extract every supported document in ``guidelines_pdfs`` into chunks."""
    folder = folder or project_path("guidelines_pdfs")
    chunks: list[Chunk] = []
    if not folder.exists():
        return chunks
    for path in sorted(folder.iterdir()):
        # Folder meta-documentation is not a guideline source.
        if path.stem.lower().startswith("readme"):
            continue
        if path.suffix.lower() == ".pdf":
            _read_pdf(path, chunks)
        elif path.suffix.lower() in TEXT_SUFFIXES:
            text = path.read_text(encoding="utf-8", errors="ignore")
            title = next(
                (line.lstrip("# ").strip() for line in text.splitlines() if line.strip()),
                path.stem,
            )
            _split(text, title, path.stem, 1, path.name, chunks)
    return chunks


def save_chunks(chunks: list[Chunk]) -> Path:
    """Write chunks to ``data/derived/guideline_chunks.json``."""
    out = project_path("data", "derived", "guideline_chunks.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps([asdict(chunk) for chunk in chunks], indent=1), encoding="utf-8")
    return out


def load_chunks() -> list[Chunk]:
    """Load chunks, building the file first if it is missing."""
    path = project_path("data", "derived", "guideline_chunks.json")
    if not path.exists():
        chunks = extract_documents()
        save_chunks(chunks)
        return chunks
    return [Chunk(**row) for row in json.loads(path.read_text(encoding="utf-8"))]


def main() -> None:
    """Extract and report chunk counts per source file."""
    chunks = extract_documents()
    if not chunks:
        print("No documents found in guidelines_pdfs/. Add official PDFs or run the download script.")
        sys.exit(0)
    path = save_chunks(chunks)
    by_file: dict[str, int] = {}
    for chunk in chunks:
        by_file[chunk.source_file] = by_file.get(chunk.source_file, 0) + 1
    for name, count in by_file.items():
        print(f"  {name:40s} {count:4d} chunks")
    print(f"\n{len(chunks)} chunks -> {path.relative_to(project_path())}")


if __name__ == "__main__":
    main()
