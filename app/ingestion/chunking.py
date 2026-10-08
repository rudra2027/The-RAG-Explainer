"""
chunking.py - Step 2 of ingestion: CHUNK the text, three strategies side by side.

WHY chunk: an embedding squeezes a whole piece of text into one vector. Embed a
whole document and the vector is a blurry average of every topic in it; embed
small focused pieces and each vector means one thing, so search can find it.

The three strategies (same size + overlap, different ideas of where to cut):

  fixed      Cut every N characters, no matter what. Simple, but it slices
             words and sentences in half.
  recursive  Try to cut at paragraph breaks, then lines, then sentences, then
             words - only as small as needed. The usual default.
  markdown   Cut at headings first (# / ## / ###) so each chunk stays inside
             one section, then fall back to recursive if a section is too long.

OVERLAP: neighbouring chunks share a few characters so a fact sitting on a
boundary is not lost in both halves.

Demo:  python -m app.ingestion.chunking
"""
from langchain_text_splitters import (
    CharacterTextSplitter,
    MarkdownHeaderTextSplitter,
    RecursiveCharacterTextSplitter,
)

STRATEGIES = ["fixed", "recursive", "markdown"]


def split_text(text: str, strategy: str, chunk_size: int, chunk_overlap: int) -> list[str]:
    """Return the chunk texts produced by one strategy."""
    if strategy == "fixed":
        # separator="" means "ignore structure, just count characters".
        splitter = CharacterTextSplitter(
            separator="", chunk_size=chunk_size, chunk_overlap=chunk_overlap
        )
        return splitter.split_text(text)

    recursive = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", ". ", " ", ""],  # biggest natural break first
        keep_separator="end",  # the "." stays with its sentence instead of starting the next chunk
    )
    if strategy == "recursive":
        return recursive.split_text(text)

    if strategy == "markdown":
        header_splitter = MarkdownHeaderTextSplitter(
            headers_to_split_on=[("#", "h1"), ("##", "h2"), ("###", "h3")],
            strip_headers=False,  # keep the heading text inside the chunk: it carries meaning
        )
        sections = header_splitter.split_text(text)
        chunks: list[str] = []
        for section in sections:
            # A long section is still split further, but never across two sections.
            chunks.extend(recursive.split_text(section.page_content))
        return chunks

    raise ValueError(f"Unknown strategy '{strategy}'. Choose from {STRATEGIES}.")


def measure_overlap(previous: str, current: str) -> int:
    """How many characters at the start of `current` repeat the end of `previous`.
    Only used for the UI, so students can SEE the overlap on each chunk card."""
    for size in range(min(len(previous), len(current)), 0, -1):
        if previous.endswith(current[:size]):
            return size
    return 0


def describe_chunks(chunks: list[str]) -> list[dict]:
    """Size + overlap for each chunk (what the chunk cards display)."""
    return [
        {
            "index": i,
            "text": text,
            "size": len(text),
            "overlap": measure_overlap(chunks[i - 1], text) if i > 0 else 0,
        }
        for i, text in enumerate(chunks)
    ]


def compare_strategies(text: str, chunk_size: int, chunk_overlap: int) -> dict[str, list[dict]]:
    """Run every strategy on the same text - powers the 'Chunking Lab' view."""
    return {s: describe_chunks(split_text(text, s, chunk_size, chunk_overlap)) for s in STRATEGIES}


if __name__ == "__main__":
    sample = (
        "# Leave policy\n\nEmployees get 24 days of paid leave per year. "
        "Unused days roll over, up to 5 days.\n\n"
        "## Sick leave\n\nSick leave is separate and needs a doctor's note after 3 days."
    )
    for name, chunks in compare_strategies(sample, chunk_size=80, chunk_overlap=15).items():
        print(f"\n=== {name}: {len(chunks)} chunks ===")
        for c in chunks:
            print(f"  [{c['index']}] size={c['size']:<3} overlap={c['overlap']:<2} | {c['text']!r}")
