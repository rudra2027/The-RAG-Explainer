"""
bm25.py - BM25 (sparse / keyword) search: find chunks that contain the query's WORDS.

How BM25 scores a chunk, in plain words:
  * every query word found in the chunk adds points,
  * RARE words add more points than common ones ("SIM-swap" beats "the"),
  * repeating a word helps, but with diminishing returns,
  * long chunks are slightly penalised so they don't win just by being long.

Strength: exact tokens - names, codes, numbers, jargon.
Weakness: no idea of meaning - "time off" does NOT match "annual leave".

The index is built once per knowledge-base version and reused by every query
(rebuilding it per query would freeze the app on a big file). The metadata
pre-filter is applied to the scores afterwards.

Demo:  python -m app.retrieval.bm25          (ingest the sample docs first)
"""
import re
import threading

from rank_bm25 import BM25Okapi

from app.config import SEARCH_K
from app.ingestion import corpus
from app.retrieval.prefilter import chunk_passes
from app.schemas import Chunk, RetrievalResult, ToolArgs

# Words too common to carry meaning. Keeping the list short and visible is the point.
STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "can", "do", "does", "for", "from", "get", "how",
    "i", "in", "is", "it", "my", "of", "on", "or", "the", "to", "we", "what", "when", "where", "which",
    "who", "why", "will", "with", "you", "your", "our", "much", "many", "there", "this", "that",
}

_cache: dict = {"version": -1, "bm25": None, "chunks": []}
_cache_lock = threading.Lock()


def tokenize(text: str) -> list[str]:
    """lower-case words and numbers, minus stopwords: 'Is SMS ok?' -> ['sms', 'ok']"""
    return [w for w in re.findall(r"[a-z0-9]+(?:-[a-z0-9]+)*", text.lower()) if w not in STOPWORDS]


def _index() -> tuple[BM25Okapi | None, list[Chunk]]:
    with _cache_lock:
        if _cache["version"] != corpus.version or _cache["bm25"] is None:
            chunks = corpus.all_chunks()
            _cache.update(version=corpus.version, chunks=chunks,
                          bm25=BM25Okapi([tokenize(c.text) for c in chunks]) if chunks else None)
        return _cache["bm25"], _cache["chunks"]


def bm25_search(query: str, args: ToolArgs, k: int = SEARCH_K) -> list[RetrievalResult]:
    bm25, chunks = _index()
    if bm25 is None:
        return []
    query_terms = tokenize(query)
    scores = bm25.get_scores(query_terms)

    # Best score first; keep only chunks that pass the metadata filter and share a word with the query.
    ranked = sorted(zip(chunks, scores), key=lambda pair: pair[1], reverse=True)
    results = []
    for chunk, score in ranked:
        if score <= 0 or len(results) == k:
            break
        if not chunk_passes(chunk, args):
            continue
        chunk_terms = set(tokenize(chunk.text))
        results.append(RetrievalResult(
            chunk=chunk, bm25_score=round(float(score), 3), bm25_rank=len(results) + 1,
            matched_terms=[t for t in dict.fromkeys(query_terms) if t in chunk_terms],
        ))
    return results


if __name__ == "__main__":
    print("tokens:", tokenize("Why are SMS codes not allowed for MFA?"))
    for r in bm25_search("Why are SMS codes not allowed for MFA?", ToolArgs(query=""), k=5):
        print(f"#{r.bm25_rank}  bm25={r.bm25_score:<6} matched={r.matched_terms}  {r.chunk.source}")
