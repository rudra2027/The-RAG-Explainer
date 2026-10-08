"""
prefilter.py - PRE-FILTERING: narrow the search space with metadata *before* searching.

WHY: if the question is clearly about HR, there is no point comparing it with
IT or finance chunks. Filtering first is cheaper and stops a "similar sounding"
chunk from the wrong department sneaking into the results.

The same filter is expressed twice, because we search in two places:
  * Pinecone (dense search) understands a filter dict:  {"department": {"$eq": "hr"}}
  * BM25 runs in Python over the local registry, so it uses a plain function.

Contrast with post-filtering (postfilter.py), which cleans up *after* the search.

Demo:  python -m app.retrieval.prefilter
"""
from typing import Optional

from app.schemas import Chunk, ToolArgs


def build_metadata_filter(args: ToolArgs) -> Optional[dict]:
    """Translate the tool arguments into a Pinecone filter (None = search everything)."""
    conditions = []
    if args.department:
        conditions.append({"department": {"$eq": args.department}})
    if args.doc_type:
        conditions.append({"doc_type": {"$eq": args.doc_type}})

    if not conditions:
        return None
    if len(conditions) == 1:
        return conditions[0]
    return {"$and": conditions}


def chunk_passes(chunk: Chunk, args: ToolArgs) -> bool:
    """The same rule for BM25's in-memory corpus."""
    if args.department and chunk.department != args.department:
        return False
    if args.doc_type and chunk.doc_type != args.doc_type:
        return False
    return True


if __name__ == "__main__":
    print(build_metadata_filter(ToolArgs(query="leave days")))
    print(build_metadata_filter(ToolArgs(query="leave days", department="hr")))
    print(build_metadata_filter(ToolArgs(query="leave days", department="hr", doc_type="md")))
