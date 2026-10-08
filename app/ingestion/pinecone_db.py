"""
pinecone_db.py - every call to Pinecone lives here (the only database in this project).

Pinecone is a managed "serverless" vector database. We use ONE index (default
"retrieval-lab-dense") and keep our data in its own *namespace*, so deleting
our knowledge base can never touch anything else stored in that index.

Facts worth teaching:
  * An index has a fixed number of dimensions - it must equal the embedding size.
  * Metadata (department, source, the chunk text...) is stored next to each vector,
    which is what makes pre-filtering possible.
  * Pinecone is *eventually consistent*: a fresh upsert becomes searchable a moment later.

Demo:  python -m app.ingestion.pinecone_db
"""
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from typing import Optional

from pinecone import Pinecone, ServerlessSpec
from pinecone.exceptions import NotFoundException

from app.config import (EMBEDDING_BACKEND, EMBEDDING_DIM, PINECONE_API_KEY, PINECONE_CLOUD, PINECONE_INDEX,
                        PINECONE_NAMESPACE, PINECONE_REGION)
from app.schemas import Chunk

FETCH_BATCH = 100   # ids per fetch request (the ids travel in the URL, so keep it modest)


@lru_cache(maxsize=1)
def get_index():
    """Connect to the index (creating it if it does not exist) and check its size."""
    if not PINECONE_API_KEY:
        raise RuntimeError("PINECONE_API_KEY is missing - add it to .env")
    pc = Pinecone(api_key=PINECONE_API_KEY)
    if not pc.has_index(PINECONE_INDEX):
        pc.create_index(name=PINECONE_INDEX, dimension=EMBEDDING_DIM, metric="cosine",
                        spec=ServerlessSpec(cloud=PINECONE_CLOUD, region=PINECONE_REGION))
    description = pc.describe_index(PINECONE_INDEX)
    if description.dimension != EMBEDDING_DIM:
        raise RuntimeError(
            f"Pinecone index '{PINECONE_INDEX}' has {description.dimension} dimensions, but the "
            f"'{EMBEDDING_BACKEND}' embedding model makes {EMBEDDING_DIM}. Point PINECONE_INDEX at a "
            f"{EMBEDDING_DIM}-dimension index, or change EMBEDDING_BACKEND in .env.")
    return pc.Index(host=description.host)


@lru_cache(maxsize=1)
def _grpc_index():
    """The same index through Pinecone's gRPC client: numbers travel as 4-byte binary floats instead of
    ~8-character JSON text, so uploads are ~3.5x faster on a slow connection (measured: 200 vectors,
    10 s over REST vs 2.8 s over gRPC)."""
    from pinecone.grpc import PineconeGRPC
    pc = PineconeGRPC(api_key=PINECONE_API_KEY)
    return pc.Index(host=pc.describe_index(PINECONE_INDEX).host)


def upsert(chunks: list[Chunk], vectors: list[list[float]]) -> None:
    get_index()  # connect + check the dimensions first, so a mismatch is reported clearly
    items = [(c.id, v, c.model_dump(exclude={"id"})) for c, v in zip(chunks, vectors)]  # text travels as metadata
    try:
        _grpc_index().upsert(vectors=items, namespace=PINECONE_NAMESPACE)
    except Exception:
        # gRPC can be blocked by a firewall or proxy: fall back to plain HTTPS (slower but always works).
        get_index().upsert(vectors=[{"id": i, "values": [round(x, 5) for x in v], "metadata": m} for i, v, m in items],
                           namespace=PINECONE_NAMESPACE, show_progress=False)


def query(vector: list[float], top_k: int, metadata_filter: Optional[dict] = None, include_values: bool = False):
    return get_index().query(vector=vector, top_k=top_k, filter=metadata_filter, include_metadata=True,
                             include_values=include_values, namespace=PINECONE_NAMESPACE).matches


def delete_ids(ids: list[str]) -> None:
    for start in range(0, len(ids), 1000):   # Pinecone deletes at most 1000 ids per request
        get_index().delete(ids=ids[start:start + 1000], namespace=PINECONE_NAMESPACE)


def clear_namespace() -> None:
    try:
        get_index().delete(delete_all=True, namespace=PINECONE_NAMESPACE)
    except NotFoundException:
        pass  # the namespace did not exist yet - already empty


def count() -> int:
    namespace = get_index().describe_index_stats().namespaces.get(PINECONE_NAMESPACE)
    return namespace.vector_count if namespace else 0


def list_ids() -> list[str]:
    ids: list[str] = []
    for page in get_index().list(namespace=PINECONE_NAMESPACE):  # a generator of pages
        ids.extend(item.id if hasattr(item, "id") else item for item in page)  # SDK v10 gives objects, older ones strings
    return ids


def fetch(ids: list[str]) -> dict:
    """id -> Pinecone vector object (.metadata and .values). Several requests run at once."""
    index = get_index()
    batches = [ids[start:start + FETCH_BATCH] for start in range(0, len(ids), FETCH_BATCH)]
    with ThreadPoolExecutor(6) as pool:
        pages = pool.map(lambda batch: index.fetch(ids=batch, namespace=PINECONE_NAMESPACE).vectors, batches)
        return {cid: vector for page in pages for cid, vector in page.items()}


if __name__ == "__main__":
    index = get_index()
    print(f"connected to '{PINECONE_INDEX}' ({EMBEDDING_DIM} dimensions), namespace '{PINECONE_NAMESPACE}'")
    print(f"vectors in our namespace: {count()}")
    print("whole index:", index.describe_index_stats().total_vector_count, "vectors in total")
