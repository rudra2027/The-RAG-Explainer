"""
embedder.py - turn text into vectors ("embeddings").

WHY two backends:
  openrouter  OpenAI's text-embedding-3-small through OpenRouter: 1536 numbers per text.
              Fast for big files (many texts per request, several requests at once)
              and costs about $0.02 per MILLION tokens - a 200,000-character file costs
              a fraction of a cent. Every query pays ~0.3-1 s of network time.
  local       MiniLM on this machine: 384 numbers, free, no network - but slower on
              big files because it runs on the CPU.

Whichever you pick, the Pinecone index must have the same number of dimensions
(checked in pinecone_db.get_index, so a mismatch is a clear message, not a crash).

Demo:  python -m app.ingestion.embedder
"""
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache

import openai

from app.config import (EMBEDDING_BACKEND, EMBEDDING_DIM, EMBEDDING_MODEL, OPENROUTER_API_KEY,
                        OPENROUTER_BASE_URL)

API_BATCH = 64       # texts per API request
API_PARALLEL = 8     # requests in flight at the same time (measured: 2x faster than 4 x 128)


class OpenRouterEmbedder:
    def __init__(self) -> None:
        if not OPENROUTER_API_KEY:
            raise RuntimeError("OPENROUTER_API_KEY is missing - add it to .env "
                               "(or set EMBEDDING_BACKEND=local and use a 384-dimension Pinecone index)")
        self.client = openai.OpenAI(base_url=OPENROUTER_BASE_URL, api_key=OPENROUTER_API_KEY,
                                    max_retries=4, timeout=90)

    def _one_request(self, texts: list[str]) -> list[list[float]]:
        response = self.client.embeddings.create(model=EMBEDDING_MODEL, input=texts)
        return [d.embedding for d in sorted(response.data, key=lambda d: d.index)]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        batches = [texts[i:i + API_BATCH] for i in range(0, len(texts), API_BATCH)]
        with ThreadPoolExecutor(API_PARALLEL) as pool:
            return [vec for batch in pool.map(self._one_request, batches) for vec in batch]  # order is kept

    def embed_query(self, text: str) -> list[float]:
        return self._one_request([text])[0]


class LocalEmbedder:
    def __init__(self) -> None:
        from langchain_huggingface import HuggingFaceEmbeddings  # imported lazily: it is slow to load
        # normalize_embeddings=True makes every vector length 1, so cosine similarity is a dot product.
        self.model = HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL, encode_kwargs={"normalize_embeddings": True})

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self.model.embed_documents(texts)

    def embed_query(self, text: str) -> list[float]:
        return self.model.embed_query(text)


@lru_cache(maxsize=1)
def get_embedder():
    return LocalEmbedder() if EMBEDDING_BACKEND == "local" else OpenRouterEmbedder()


if __name__ == "__main__":
    import time

    start = time.perf_counter()
    vectors = get_embedder().embed_documents(["How many leave days do I get?", "Annual paid leave is 24 days."])
    print(f"backend={EMBEDDING_BACKEND} model={EMBEDDING_MODEL}  vector length={len(vectors[0])} (expected {EMBEDDING_DIM})")
    print(f"first 5 numbers = {[round(v, 3) for v in vectors[0][:5]]}  ({time.perf_counter() - start:.2f}s)")
    print(f"cosine similarity of the two sentences = {sum(a * b for a, b in zip(*vectors)):.3f}")
