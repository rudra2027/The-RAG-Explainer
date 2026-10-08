"""
schemas.py - the typed shapes that flow through the pipeline (Pydantic).

WHY Pydantic: each stage hands the next one a *validated* object instead of a
loose dict. If the LLM returns a bad tool argument, or a chunk is missing its
metadata, we find out at the boundary - not three stages later.

    Chunk            -> produced by ingestion, stored in Pinecone (and kept in memory for BM25)
    RetrievalResult  -> a chunk + every score it collected during retrieval
    ToolArgs         -> what the LLM asks for when it calls the search tool
    MultiQuery       -> MQE: extra phrasings of the question written by the LLM
    HypotheticalDoc  -> HyDE: a fake answer passage written by the LLM
    GroundingCheck   -> the LLM's verdict in the reflection step
    EvalScore        -> one metric from RAGAS / DeepEval
    StageEvent       -> one live update sent to the browser
"""
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

# Metadata values we tag at ingestion and allow the LLM to filter on.
Department = Literal["hr", "it", "finance", "product", "general"]
DocType = Literal["pdf", "txt", "md"]

# The two dropdowns in the UI.
SearchStrategy = Literal["dense", "bm25", "hybrid", "hybrid_expansion"]
Expansion = Literal["mqe", "hyde"]


class Chunk(BaseModel):
    """One piece of a document, ready to be embedded."""
    id: str
    text: str
    source: str                  # file name, e.g. "hr_leave_policy.md"
    doc_type: DocType
    department: Department
    chunk_index: int             # position inside the source document
    char_count: int
    strategy: str                # which chunking strategy produced it


class RetrievalResult(BaseModel):
    """A chunk on its way through the retrieval funnel, with every score it earned."""
    chunk: Chunk
    dense_score: Optional[float] = None     # cosine similarity from Pinecone (meaning)
    dense_rank: Optional[int] = None
    bm25_score: Optional[float] = None      # keyword score from BM25 (exact words)
    bm25_rank: Optional[int] = None
    matched_terms: list[str] = []           # which query words BM25 found in the chunk
    fused_score: Optional[float] = None     # Reciprocal Rank Fusion score (hybrid)
    rerank_score: Optional[float] = None    # cross-encoder score (set by the re-ranker)
    found_by: list[str] = []                # e.g. ["dense: original", "bm25: variant 2"]
    # The chunk's embedding, returned by Pinecone so the 3D map can place it.
    # exclude=True keeps these 1536 numbers out of every JSON payload sent to the browser.
    vector: Optional[list[float]] = Field(default=None, exclude=True)


class ToolArgs(BaseModel):
    """
    Arguments of the `search_knowledge_base` tool.
    Its JSON schema is handed to the LLM, so the field descriptions below are
    literally the instructions the LLM reads when it decides how to search.
    """
    query: str = Field(description="A focused search query rewritten from the user's question.")
    department: Optional[Department] = Field(
        default=None,
        description="Only search documents from this department. Leave empty if unsure.",
    )
    doc_type: Optional[DocType] = Field(
        default=None,
        description="Only search this file type. Leave empty unless the user asks for one.",
    )


class MultiQuery(BaseModel):
    """MQE: different ways to ask the same thing (different words = different BM25/dense hits)."""
    queries: list[str]


class HypotheticalDoc(BaseModel):
    """HyDE: a plausible (possibly wrong!) answer passage. We search with its embedding."""
    passage: str


class SuggestedQuestion(BaseModel):
    """A question the knowledge base can answer (see generation/suggest.py)."""
    question: str


class GroundingCheck(BaseModel):
    """Reflection: is every claim in the answer supported by the retrieved chunks?"""
    grounded: bool
    reason: str
    unsupported_claims: list[str]
    rewritten_query: str  # a better query to try if the answer was not grounded


class EvalScore(BaseModel):
    """One evaluation metric for one question."""
    framework: Literal["ragas", "deepeval"]
    question: str
    metric: str
    score: float
    threshold: Optional[float] = None
    passed: Optional[bool] = None
    reason: Optional[str] = None


class StageEvent(BaseModel):
    """
    One message on the live event stream (Server-Sent Events).
    The UI uses `stage` to pick which step to light up and `data` to draw cards.
    """
    stage: str                                              # e.g. "chunk", "dense", "rerank"
    status: Literal["running", "done", "skipped", "error", "info"]
    message: str = ""
    ms: Optional[float] = None                              # latency of this stage
    data: dict[str, Any] = {}
