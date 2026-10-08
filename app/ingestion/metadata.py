"""
metadata.py - tag every chunk with metadata so retrieval can FILTER on it.

WHY: vector search only knows "similar meaning". Metadata adds hard facts
(which department, which file type) so we can say "search only HR documents"
*before* the similarity search runs (pre-filtering, see retrieval/prefilter.py).

We tag with a deliberately simple keyword rule so students can read it in
ten seconds. Real systems use document owners, folders, or an LLM classifier.

Demo:  python -m app.ingestion.metadata
"""
import hashlib

from app.schemas import Chunk

# Filename prefix wins (hr_*.md -> hr, general_*.md -> general); otherwise count keywords
# in the text. Keyword rules are fragile: "employees" appears in almost every company
# document, so without a prefix an office-move notice would be tagged "hr".
DEPARTMENT_KEYWORDS = {
    "hr": ["leave", "holiday", "employee", "salary", "parental", "onboarding"],
    "it": ["password", "vpn", "laptop", "security", "phishing", "wifi"],
    "finance": ["expense", "reimburse", "invoice", "budget", "travel"],
    "product": ["release", "feature", "pricing", "customer", "roadmap"],
}


def detect_department(source: str, text: str) -> str:
    prefix = source.split("_")[0].lower()
    if prefix in DEPARTMENT_KEYWORDS or prefix == "general":
        return prefix
    lowered = text.lower()
    counts = {dept: sum(lowered.count(w) for w in words) for dept, words in DEPARTMENT_KEYWORDS.items()}
    best = max(counts, key=counts.get)
    return best if counts[best] > 0 else "general"


def make_chunk_id(source: str, strategy: str, index: int) -> str:
    """Stable id: re-ingesting the same file overwrites instead of duplicating."""
    return hashlib.md5(f"{source}|{strategy}|{index}".encode()).hexdigest()[:12]


def tag_chunks(texts: list[str], source: str, doc_type: str, full_text: str, strategy: str) -> list[Chunk]:
    """Turn raw chunk strings into validated Chunk objects with metadata."""
    department = detect_department(source, full_text)  # decided once per document
    return [
        Chunk(
            id=make_chunk_id(source, strategy, i),
            text=text,
            source=source,
            doc_type=doc_type,
            department=department,
            chunk_index=i,
            char_count=len(text),
            strategy=strategy,
        )
        for i, text in enumerate(texts)
    ]


if __name__ == "__main__":
    chunks = tag_chunks(
        ["Reset your VPN password every 90 days.", "Report phishing to security@."],
        source="security_notes.txt", doc_type="txt",
        full_text="VPN password phishing security", strategy="recursive",
    )
    for c in chunks:
        print(c.model_dump())
