"""
vector_map.py - squash embeddings (384 or 1536 numbers) down to 3D so we can SEE them.

WHY: "nearest neighbour in embedding space" is abstract until you see the
query land among the chunks. We use PCA (principal component analysis): it
finds the 3 directions along which the chunk vectors differ the most, and
projects every vector onto them.

For a big knowledge base we fit PCA on a SAMPLE of MAP_MAX_POINTS chunks
(fetched from Pinecone); search hits outside the sample are projected with
the same 3 directions, so they still appear in the right place.

Honest caveat for class: 3D keeps only part of the information, so two points
that look close here may be further apart in the real space. The scores in the
cards are always computed on the full vectors.

Demo:  python -m app.retrieval.vector_map
"""
import threading

import numpy as np

from app.config import MAP_MAX_POINTS
from app.ingestion import corpus, pinecone_db

_fit: dict = {"version": -1, "data": None}
_fit_lock = threading.Lock()


def _fit_projection():
    """Learn the 3 PCA directions from a sample of stored vectors (cached until the corpus changes)."""
    with _fit_lock:
        if _fit["version"] == corpus.version:
            return _fit["data"]
        chunks = corpus.all_chunks()
        _fit.update(version=corpus.version, data=None)
        if len(chunks) < 4:
            return None
        step = max(1, len(chunks) // MAP_MAX_POINTS)            # evenly spaced sample
        sample = chunks[::step][:MAP_MAX_POINTS]
        fetched = pinecone_db.fetch([c.id for c in sample])
        ids = [c.id for c in sample if c.id in fetched]
        if len(ids) < 4:
            return None
        matrix = np.array([fetched[i].values for i in ids])
        mean = matrix.mean(axis=0)
        # SVD of the centred data: the first 3 rows of vt are the top-3 principal directions.
        _, _, vt = np.linalg.svd(matrix - mean, full_matrices=False)
        components = vt[:3]
        coords = (matrix - mean) @ components.T
        scale = float(np.abs(coords).max()) or 1.0                  # fit everything into a -1..1 cube
        _fit["data"] = {"ids": ids, "chunks": {c.id: c for c in sample}, "mean": mean,
                        "components": components, "scale": scale, "coords": coords / scale,
                        "total": len(chunks)}
        return _fit["data"]


def chunk_points() -> dict:
    """One 3D point per sampled chunk (what the UI draws as spheres)."""
    p = _fit_projection()
    if p is None:
        return {"points": [], "total": len(corpus.all_chunks()), "sampled": False}
    points = []
    for cid, xyz in zip(p["ids"], p["coords"]):
        c = p["chunks"][cid]
        points.append({"id": cid, "x": round(float(xyz[0]), 4), "y": round(float(xyz[1]), 4),
                       "z": round(float(xyz[2]), 4), "source": c.source, "department": c.department,
                       "chunk_index": c.chunk_index, "text": c.text[:160]})
    return {"points": points, "total": p["total"], "sampled": p["total"] > len(points)}


def project(vectors: list[list[float]]) -> list[list[float]]:
    """Place any vectors (the query, MQE variants, the HyDE passage, search hits) in the same 3D space."""
    p = _fit_projection()
    if p is None or not vectors:
        return [[0.0, 0.0, 0.0] for _ in vectors]
    coords = (np.array(vectors) - p["mean"]) @ p["components"].T / p["scale"]
    return [[round(float(v), 4) for v in xyz] for xyz in np.clip(coords, -1.3, 1.3)]


if __name__ == "__main__":
    from app.ingestion.vector_store import embed_query

    info = chunk_points()
    print(f"{len(info['points'])} points (of {info['total']} chunks), e.g. {info['points'][:1]}")
    print("query 'paid leave' lands at", project([embed_query("paid leave")])[0])
