"""
dense.py - DENSE search: find chunks whose MEANING is closest to the query (Pinecone).

How it works: the query is embedded into the same space as the chunks, and
Pinecone returns the k nearest vectors by cosine similarity.

Strength: understands synonyms - "time off" finds "annual leave".
Weakness: fuzzy on exact tokens - codes, names and numbers ("extension 4400")
can lose to a chunk that is merely "about the same topic".

Demo:  python -m app.retrieval.dense        (ingest the sample docs first)
"""
from typing import Optional

from app.config import SEARCH_K
from app.ingestion import pinecone_db
from app.ingestion.vector_store import embed_query
from app.schemas import Chunk, RetrievalResult


def dense_search(query_vector: list[float], metadata_filter: Optional[dict], k: int = SEARCH_K,
                 with_vectors: bool = False) -> list[RetrievalResult]:
    # Returning the vectors makes a query ~5x slower, so only ask when the 3D map needs them
    # (a hit outside the map's sample has no position yet).
    matches = pinecone_db.query(query_vector, k, metadata_filter, include_values=with_vectors)
    results = []
    for rank, match in enumerate(matches, start=1):
        chunk = Chunk(id=match.id, **match.metadata)
        results.append(RetrievalResult(chunk=chunk, dense_score=round(match.score, 4), dense_rank=rank,
                                       vector=list(match.values) if with_vectors else None))
    return results


if __name__ == "__main__":
    for r in dense_search(embed_query("How much time off do I get?"), None, k=5):
        print(f"#{r.dense_rank}  cos={r.dense_score:.3f}  {r.chunk.source:<28} {r.chunk.text[:60]!r}")
