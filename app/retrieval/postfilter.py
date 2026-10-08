"""
postfilter.py - POST-FILTERING: clean up the search results *after* searching.

WHY: a search always returns up to k results, even when some are barely
related, and overlapping chunks often show up as near-duplicates. Post-filtering:
  1. drops weak matches - a chunk survives if its meaning is close enough
     (cosine >= MIN_RELEVANCE) OR it shares real keywords with the query (BM25 > 0),
  2. removes near-duplicates (same opening words from overlapping chunks),
  3. keeps at most N, so the (slower) re-ranker has less work.

The input list is already in the strategy's best-first order, so step 3
keeps the strategy's favourites.

Demo:  python -m app.retrieval.postfilter
"""
from app.config import MIN_RELEVANCE, POST_FILTER_MAX
from app.schemas import RetrievalResult


def is_strong(r: RetrievalResult, min_score: float) -> bool:
    meaning_ok = r.dense_score is not None and r.dense_score >= min_score
    keywords_ok = r.bm25_score is not None and r.bm25_score > 0
    return meaning_ok or keywords_ok


def post_filter(
    results: list[RetrievalResult],
    min_score: float = MIN_RELEVANCE,
    max_keep: int = POST_FILTER_MAX,
) -> tuple[list[RetrievalResult], dict]:
    """Return the kept results plus a small report of what was removed (for the UI)."""
    kept: list[RetrievalResult] = []
    seen_starts: set[str] = set()
    dropped_low_score = dropped_duplicate = 0

    for r in results:
        if not is_strong(r, min_score):
            dropped_low_score += 1
            continue
        start = " ".join(r.chunk.text.lower().split())[:60]  # normalised opening words
        if start in seen_starts:
            dropped_duplicate += 1
            continue
        seen_starts.add(start)
        kept.append(r)

    report = {
        "dropped_low_score": dropped_low_score,
        "dropped_duplicate": dropped_duplicate,
        "dropped_over_limit": max(0, len(kept) - max_keep),
        "min_score": min_score,
    }
    return kept[:max_keep], report


if __name__ == "__main__":
    from app.schemas import Chunk

    def fake(text: str, dense=None, bm25=None) -> RetrievalResult:
        chunk = Chunk(id=text, text=text, source="demo.md", doc_type="md", department="hr",
                      chunk_index=0, char_count=len(text), strategy="recursive")
        return RetrievalResult(chunk=chunk, dense_score=dense, bm25_score=bm25)

    kept, report = post_filter([fake("Leave is 24 days", dense=0.71), fake("Leave is 24 days", dense=0.70),
                                fake("Code 4400", dense=0.05, bm25=3.2), fake("Cafeteria opens at 8", dense=0.05)])
    print([k.chunk.text for k in kept], report)
