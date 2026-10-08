"""
fusion.py - HYBRID search: merge several ranked lists with Reciprocal Rank Fusion (RRF).

Problem: dense scores (cosine, ~0.2-0.8) and BM25 scores (0-15+) live on
different scales, so you cannot simply add them.

RRF ignores the raw scores and uses only the RANK in each list:

        RRF(chunk) = sum over lists of   1 / (k + rank)        with k = 60

A chunk ranked #1 by dense and #3 by BM25 gets 1/61 + 1/63. A chunk found by
only one list still counts, just less. Being near the top of SEVERAL lists
wins - which is exactly "agreement between meaning and keywords".

The same function fuses MQE's many lists (one dense + one BM25 list per query).

Demo:  python -m app.retrieval.fusion
"""
from app.config import RRF_K, SEARCH_K
from app.schemas import RetrievalResult


def reciprocal_rank_fusion(ranked_lists: dict[str, list[RetrievalResult]], k: int = RRF_K,
                           limit: int = SEARCH_K) -> list[RetrievalResult]:
    """`ranked_lists` maps a label (e.g. "dense: original") to a best-first list of results."""
    merged: dict[str, RetrievalResult] = {}
    for label, results in ranked_lists.items():
        for rank, r in enumerate(results, start=1):
            if r.chunk.id not in merged:
                merged[r.chunk.id] = r.model_copy(deep=True)
                merged[r.chunk.id].fused_score = 0.0
                merged[r.chunk.id].found_by = []
            m = merged[r.chunk.id]
            m.fused_score += 1.0 / (k + rank)
            m.found_by.append(f"{label} #{rank}")
            # Keep the best score of each kind so the UI can show both bars.
            if r.dense_score is not None and (m.dense_score is None or r.dense_score > m.dense_score):
                m.dense_score, m.dense_rank = r.dense_score, r.dense_rank
            if r.bm25_score is not None and (m.bm25_score is None or r.bm25_score > m.bm25_score):
                m.bm25_score, m.bm25_rank = r.bm25_score, r.bm25_rank
                m.matched_terms = r.matched_terms

    fused = sorted(merged.values(), key=lambda r: r.fused_score, reverse=True)[:limit]
    for r in fused:
        r.fused_score = round(r.fused_score, 5)
    return fused


if __name__ == "__main__":
    from app.schemas import Chunk

    def fake(cid: str) -> RetrievalResult:
        return RetrievalResult(chunk=Chunk(id=cid, text=cid, source="x.md", doc_type="md", department="hr",
                                           chunk_index=0, char_count=1, strategy="recursive"))

    dense = [fake("A"), fake("B"), fake("C")]
    bm25 = [fake("C"), fake("A"), fake("D")]
    for r in reciprocal_rank_fusion({"dense": dense, "bm25": bm25}):
        print(f"{r.chunk.id}: RRF={r.fused_score}  found by {r.found_by}")
    print("A and C appear in both lists, so they beat B and D.")
