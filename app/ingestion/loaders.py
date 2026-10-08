"""
loaders.py - Step 1 of ingestion: LOAD documents (PDF / TXT / MD).

WHY a loader at all: every file format stores text differently. A loader
turns each one into the same shape - LangChain `Document(page_content, metadata)` -
so every later stage can ignore the file format completely.

Two safety rules learned the hard way:
  * Text files are read with errors="replace": one odd byte (a stray Windows-1252
    character in a pasted article) must not crash the whole ingestion.
  * `limit_text` caps how much of a huge file we ingest (see MAX_INGEST_CHARS).
    A 22 MB file would be ~56,000 chunks: minutes of embedding, a flooded browser
    and a Search lens with 56,000 tiles. A classroom does not need that.

Demo:  python -m app.ingestion.loaders
"""
from pathlib import Path

from langchain_community.document_loaders import PyPDFLoader
from langchain_core.documents import Document

SUPPORTED_TYPES = {".pdf": "pdf", ".txt": "txt", ".md": "md"}


def load_document(path: Path) -> list[Document]:
    """Load one file into LangChain Documents (a PDF gives one Document per page)."""
    suffix = path.suffix.lower()
    if suffix not in SUPPORTED_TYPES:
        raise ValueError(f"Unsupported file type '{suffix}'. Use PDF, TXT or MD.")

    if suffix == ".pdf":
        docs = PyPDFLoader(str(path)).load()
    else:
        # Markdown is plain text; we keep the '#' headings because the
        # markdown-aware chunking strategy uses them as split points.
        text = path.read_text(encoding="utf-8", errors="replace")
        docs = [Document(page_content=text)]

    # Start every Document with the same two metadata keys, whatever the format.
    for doc in docs:
        doc.metadata["source"] = path.name
        doc.metadata["doc_type"] = SUPPORTED_TYPES[suffix]
    return docs


def limit_text(text: str, max_chars: int) -> tuple[str, bool]:
    """Cut `text` to at most `max_chars`, at a paragraph break so no passage is cut in half.
    Returns (text, was_cut)."""
    if len(text) <= max_chars:
        return text, False
    cut = text.rfind("\n\n", 0, max_chars)
    return text[:cut if cut > max_chars * 0.5 else max_chars], True


def estimate_ingest(chars: int) -> dict:
    """Rough cost of ingesting `chars` characters, from measurements on a real 22 MB file
    (default chunking: ~278 characters per chunk; ~35 ms per chunk for embedding + Pinecone;
    ~4 characters per token at $0.02 per million tokens)."""
    chunks = max(1, round(chars / 278))
    return {"chunks": chunks, "minutes": round(chunks * 0.035 / 60, 1), "cost_usd": round(chars / 4 / 1e6 * 0.02, 3)}


def load_as_single_text(path: Path) -> str:
    """Join all pages into one string - handy for chunking a document as a whole."""
    return "\n\n".join(doc.page_content for doc in load_document(path))


if __name__ == "__main__":
    from app.config import SAMPLE_DOCS_DIR

    for file in sorted(SAMPLE_DOCS_DIR.iterdir()):
        docs = load_document(file)
        chars = sum(len(d.page_content) for d in docs)
        print(f"{file.name:<32} pages={len(docs):<3} chars={chars}")
