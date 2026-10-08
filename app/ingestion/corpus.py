"""
corpus.py - an in-memory copy of the chunk TEXTS (never written to disk).

WHY: Pinecone answers "which vectors are nearest?", but BM25 needs the words of
every chunk (how rare is "SIM-swap" across the collection?), and the Search
lens needs to list what is stored. So after a restart we read the texts back
from Pinecone, and after that we only add / remove what we ingest ourselves.

Reading back is slow for a big knowledge base (Pinecone sends the 1536 numbers of
every chunk even though we only want the text: ~13 minutes for 56,000 chunks), so
it happens in a BACKGROUND thread. While it runs the app stays usable, `progress()`
reports how far it is, and anything that needs the full corpus raises
`KnowledgeBaseLoading` with a friendly message instead of silently using half the data.

`version` goes up on every change, so caches (BM25, the 3D map) know when to rebuild.

Demo:  python -m app.ingestion.corpus
"""
import threading

from app.ingestion import pinecone_db
from app.schemas import Chunk

READ_GROUP = 600    # chunks fetched per progress step (fetched 100 per request, 6 requests at once)

_chunks: dict[str, Chunk] = {}
_loaded = False
_loading = {"active": False, "done": 0, "total": 0, "error": None}
_lock = threading.Lock()
version = 0


class KnowledgeBaseLoading(RuntimeError):
    """Raised while the chunk texts are still being read back from Pinecone."""


def _bump() -> None:
    global version
    version += 1


def progress() -> dict:
    return dict(_loading)


def load_from_pinecone() -> int:
    """Read every chunk of our namespace back from Pinecone (blocking). Prefer `start_background_load`."""
    global _loaded
    _loading.update(active=True, done=0, total=0, error=None)
    try:
        ids = pinecone_db.list_ids()
        _loading["total"] = len(ids)
        loaded: dict[str, Chunk] = {}
        for start in range(0, len(ids), READ_GROUP):
            for cid, vector in pinecone_db.fetch(ids[start:start + READ_GROUP]).items():
                loaded[cid] = Chunk(id=cid, **vector.metadata)
            _loading["done"] = min(start + READ_GROUP, len(ids))
        with _lock:
            _chunks.clear()
            _chunks.update(loaded)
            _loaded = True
            _bump()
        return len(_chunks)
    except Exception as exc:
        _loading["error"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        _loading["active"] = False


def start_background_load() -> None:
    """Start reading the chunk texts without blocking the server's start-up."""
    def work():
        try:
            n = load_from_pinecone()
            print(f"Loaded {n:,} chunks from Pinecone")
        except Exception as exc:
            print(f"WARNING: could not read Pinecone at start-up: {exc}")
    _loading.update(active=True, done=0, total=0, error=None)   # visible immediately, before the thread runs
    threading.Thread(target=work, daemon=True, name="corpus-loader").start()


def _ready() -> None:
    if _loading["active"]:
        raise KnowledgeBaseLoading(
            f"Still reading your knowledge base back from Pinecone ({_loading['done']:,} of {_loading['total'] or '?'} chunks). "
            "This only happens after a restart; please try again in a moment.")
    if not _loaded:
        load_from_pinecone()


def all_chunks() -> list[Chunk]:
    _ready()
    return list(_chunks.values())


def size() -> int:
    _ready()
    return len(_chunks)


def add(chunks: list[Chunk]) -> None:
    with _lock:
        for chunk in chunks:
            _chunks[chunk.id] = chunk
        _bump()


def remove_source(source: str) -> list[str]:
    """Forget one file's chunks; returns their ids so Pinecone can delete them too."""
    _ready()
    with _lock:
        ids = [cid for cid, c in _chunks.items() if c.source == source]
        for cid in ids:
            del _chunks[cid]
        _bump()
    return ids


def clear() -> int:
    global _loaded
    with _lock:
        removed = len(_chunks)
        _chunks.clear()
        _loaded = True   # we know it is empty - no need to ask Pinecone
        _loading["active"] = False
        _bump()
    return removed


def summary() -> dict:
    """Chunks per file - shown in the 'Knowledge base' panel (partial while still loading)."""
    per_source: dict[str, dict] = {}
    for c in list(_chunks.values()):
        entry = per_source.setdefault(c.source, {"source": c.source, "chunks": 0, "department": c.department,
                                                 "doc_type": c.doc_type, "strategy": c.strategy})
        entry["chunks"] += 1
    return {"total_chunks": sum(d["chunks"] for d in per_source.values()),
            "documents": sorted(per_source.values(), key=lambda d: d["source"])}


if __name__ == "__main__":
    print(f"{load_from_pinecone()} chunks loaded from Pinecone")
    for c in all_chunks()[:3]:
        print(f"  {c.source:<30} #{c.chunk_index}  {c.text[:60]!r}")
