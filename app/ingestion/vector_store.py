"""
vector_store.py - Steps 3 + 4 of ingestion: EMBED chunks and STORE them in Pinecone.

WHY embeddings: an embedding model turns text into a list of numbers where
"similar meaning" = "vectors point the same way". Texts are embedded in
groups so a big file shows progress instead of freezing.

WHY we wait after storing: Pinecone is eventually consistent. An upsert returns
at once, but the vectors become searchable a moment later. `wait_until_searchable`
proves it by searching for the last chunk we stored, so the delay is measured
instead of hidden.

Demo:  python -m app.ingestion.vector_store
"""
import time

from app.ingestion import corpus, pinecone_db
from app.ingestion.embedder import get_embedder
from app.schemas import Chunk


def embed_texts(texts: list[str]) -> list[list[float]]:
    return get_embedder().embed_documents(texts)


def embed_query(text: str) -> list[float]:
    return get_embedder().embed_query(text)


def delete_source(source: str) -> None:
    """Re-ingesting a file replaces its old chunks instead of duplicating them."""
    ids = corpus.remove_source(source)
    if ids:
        pinecone_db.delete_ids(ids)


def store_group(chunks: list[Chunk], vectors: list[list[float]]) -> None:
    pinecone_db.upsert(chunks, vectors)
    corpus.add(chunks)


def wait_until_searchable(chunk: Chunk, vector: list[float], timeout_s: float = 30.0) -> float:
    """Search for a chunk we just stored until Pinecone returns it. Returns seconds waited."""
    start = time.perf_counter()
    while time.perf_counter() - start < timeout_s:
        matches = pinecone_db.query(vector, top_k=1)
        if matches and matches[0].id == chunk.id:
            break
        time.sleep(0.4)
    return round(time.perf_counter() - start, 2)


def clear_all() -> int:
    """Empty the knowledge base: every vector in our namespace (and the in-memory texts)."""
    removed = pinecone_db.count()      # ask Pinecone itself, so the number is right even from a fresh process
    pinecone_db.clear_namespace()
    corpus.clear()
    return removed


def knowledge_base_summary() -> dict:
    return corpus.summary()


if __name__ == "__main__":
    vectors = embed_texts(["How many leave days do I get?", "Annual paid leave is 24 days."])
    print(f"vector length = {len(vectors[0])}, first 5 numbers = {[round(v, 3) for v in vectors[0][:5]]}")
    print(f"cosine similarity of the two sentences = {sum(a * b for a, b in zip(*vectors)):.3f}")
    print(f"Pinecone holds {pinecone_db.count()} vectors in our namespace")
    print(knowledge_base_summary())
