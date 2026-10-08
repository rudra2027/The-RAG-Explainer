"""
rerank.py - RE-RANKING with a cross-encoder.

WHY two kinds of model?
  * The embedding model (bi-encoder) encodes the query and each chunk SEPARATELY.
    That is fast enough to search thousands of chunks, but it never actually
    "reads" them together.
  * A cross-encoder reads the query AND one chunk TOGETHER and outputs one
    relevance score. Much more accurate, but too slow to run on everything -
    so we only run it on the few survivors of the post-filter.

Demo:  python -m app.retrieval.rerank
"""
from functools import lru_cache

from sentence_transformers import CrossEncoder

from app.config import RERANK_MODEL, RERANK_TOP_N
from app.schemas import RetrievalResult


@lru_cache(maxsize=1)
def get_cross_encoder() -> CrossEncoder:
    return CrossEncoder(RERANK_MODEL)


def rerank(query: str, results: list[RetrievalResult], top_n: int = RERANK_TOP_N) -> list[RetrievalResult]:
    if not results:
        return []
    pairs = [(query, r.chunk.text) for r in results]       # (question, chunk) read together
    scores = get_cross_encoder().predict(pairs)             # higher = more relevant (raw logits)
    for r, s in zip(results, scores):
        r.rerank_score = round(float(s), 3)
    return sorted(results, key=lambda r: r.rerank_score, reverse=True)[:top_n]


if __name__ == "__main__":
    model = get_cross_encoder()
    query = "How many days of paid leave do I get?"
    for text in ["Employees receive 24 days of paid annual leave.",
                 "Leave the building through the east exit during a fire drill.",
                 "The VPN must be used on public wifi."]:
        print(f"{float(model.predict([(query, text)])[0]):7.2f}  {text}")
    print("Note how the fire-drill sentence shares the word 'leave' but scores low.")
