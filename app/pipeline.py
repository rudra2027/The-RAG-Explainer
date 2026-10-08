"""
pipeline.py - wires the small modules into the two flows the UI animates.

    ingest_file()     Load > Chunk > Embed > Store
    answer_question() Query > Tool call > Expand > Pre-filter > Dense > BM25 > Fuse >
                      Post-filter > Re-rank > Prompt > Answer > Reflect (> one retry)

Which stages run depends on the UI:
    strategy  = "dense" | "bm25" | "hybrid" | "hybrid_expansion"
    expansion = "mqe" | "hyde"           (only used by hybrid_expansion)
    features  = which optional stages are on: tool_call, postfilter, rerank, reflect
                (a RAG "architecture" is just a preset of these - see architectures.py)

Both flows are *generators*: after each stage they `yield` a StageEvent.
The server forwards each event to the browser immediately (and, in step-by-step
mode, waits for the "Next step" click before asking for the next one).

Demo:  python -m app.pipeline
"""
import time
from pathlib import Path

from app.architectures import ALL_ON
from app.config import (CHUNK_OVERLAP, CHUNK_SIZE, DEFAULT_STRATEGY, EMBED_GROUP, LLM_ENABLED, MAX_CARDS_IN_EVENT,
                        MAP_MAX_POINTS, MAX_INGEST_CHARS, POST_FILTER_MAX, RERANK_TOP_N, STAGE_DELAY_SECONDS, UPSERT_GROUP)
from app.evals.tracing import traceable
from app.generation.answer import generate_answer
from app.generation.reflection import check_grounding
from app.generation.tools import plan_search
from app.ingestion import corpus, vector_store
from app.ingestion.chunking import describe_chunks, split_text
from app.ingestion.loaders import estimate_ingest, limit_text, load_document
from app.ingestion.metadata import tag_chunks
from app.latency import StageTimer
from app.retrieval.bm25 import bm25_search, tokenize
from app.retrieval.dense import dense_search
from app.retrieval.expansion import hypothetical_document, multi_query
from app.retrieval.fusion import reciprocal_rank_fusion
from app.retrieval.postfilter import post_filter
from app.retrieval.prefilter import build_metadata_filter
from app.retrieval.prompt import SYSTEM_PROMPT, render_prompt
from app.retrieval.rerank import rerank
from app.retrieval.vector_map import project
from app.schemas import GroundingCheck, RetrievalResult, StageEvent, ToolArgs

# Each step becomes a child span in the LangSmith trace (no-op when tracing is off).
plan_search = traceable(name="tool_call", run_type="llm")(plan_search)
dense_search = traceable(name="dense_search", run_type="retriever")(dense_search)
bm25_search = traceable(name="bm25_search", run_type="retriever")(bm25_search)
rerank = traceable(name="rerank")(rerank)
generate_answer = traceable(name="answer")(generate_answer)
check_grounding = traceable(name="reflection")(check_grounding)

STRATEGY_LABELS = {"dense": "Dense", "bm25": "BM25", "hybrid": "Hybrid (RRF)",
                   "hybrid_expansion": "Hybrid + expansion"}


def _pause(slow: bool) -> None:
    """Auto-play teaching aid: a short pause so each stage is visible on screen."""
    if slow:
        time.sleep(STAGE_DELAY_SECONDS)


def _card(r: RetrievalResult) -> dict:
    """The compact shape the UI draws as a 'retrieved chunk' card."""
    c = r.chunk
    return {"id": c.id, "source": c.source, "department": c.department, "doc_type": c.doc_type,
            "chunk_index": c.chunk_index, "text": c.text,
            "dense_score": r.dense_score, "dense_rank": r.dense_rank,
            "bm25_score": r.bm25_score, "bm25_rank": r.bm25_rank, "matched_terms": r.matched_terms,
            "fused_score": r.fused_score, "rerank_score": r.rerank_score, "found_by": r.found_by}


# =============================================================================
# 1. INGEST:  Load > Chunk > Embed > Store
# =============================================================================
@traceable(name="ingest_file")
def ingest_file(path: Path, strategy: str = DEFAULT_STRATEGY,
                chunk_size: int = CHUNK_SIZE, chunk_overlap: int = CHUNK_OVERLAP, slow: bool = True,
                max_chars: int | None = MAX_INGEST_CHARS):
    """max_chars=None ingests the WHOLE file (slow for huge files: see estimate_ingest)."""
    timer = StageTimer()

    # --- Load ---------------------------------------------------------------
    yield StageEvent(stage="load", status="running", message=f"Loading {path.name}")
    with timer.measure("load"):
        docs = load_document(path)
        full_text = "\n\n".join(d.page_content for d in docs)
        file_chars = len(full_text)
        full_text, truncated = limit_text(full_text, max_chars) if max_chars else (full_text, False)  # big-file guard
    if not full_text.strip():
        raise ValueError(f"No readable text found in {path.name}")
    doc_type = docs[0].metadata["doc_type"]
    message = f"{path.name}: {len(docs)} page(s), {file_chars:,} characters"
    if truncated:
        message += (f" - only the first {len(full_text):,} are used (the 'first part' option; choose "
                    f"'whole file' to ingest everything)")
    est = estimate_ingest(len(full_text))
    yield StageEvent(stage="load", status="done", ms=timer.last_ms, message=message,
                     data={"source": path.name, "doc_type": doc_type, "pages": len(docs),
                           "file_chars": file_chars, "used_chars": len(full_text), "truncated": truncated,
                           "size_mb": round(path.stat().st_size / 1e6, 2), "estimate": est})
    _pause(slow)

    # --- Chunk + tag metadata -----------------------------------------------
    yield StageEvent(stage="chunk", status="running", message=f"Splitting with '{strategy}' strategy")
    with timer.measure("chunk"):
        texts = split_text(full_text, strategy, chunk_size, chunk_overlap)
        chunks = tag_chunks(texts, path.name, doc_type, full_text, strategy)
    shown = min(len(chunks), MAX_CARDS_IN_EVENT)   # never flood the browser: send a sample of the cards
    cards = describe_chunks(texts[:shown])
    for card, chunk in zip(cards, chunks):          # add metadata to each chunk card
        card.update(department=chunk.department, doc_type=chunk.doc_type, source=chunk.source)
    yield StageEvent(stage="chunk", status="done", ms=timer.last_ms,
                     message=f"{len(chunks):,} chunks (size {chunk_size}, overlap {chunk_overlap})"
                             + (f" - showing the first {shown}" if shown < len(chunks) else ""),
                     data={"source": path.name, "strategy": strategy, "chunks": cards, "total": len(chunks),
                           "avg_size": round(sum(len(t) for t in texts) / len(texts)),
                           "department": chunks[0].department})
    _pause(slow)

    # --- Embed + Store, group by group ---------------------------------------------
    # Each group is embedded and uploaded straight away, then forgotten: memory stays flat even for
    # 56,000 chunks (holding every vector at once would need ~2.7 GB of Python floats).
    n = len(chunks)
    yield StageEvent(stage="embed", status="running", message=f"Embedding {n:,} chunks", data={"done": 0, "total": n})
    vector_store.delete_source(path.name)            # re-uploading a file replaces its old chunks
    preview, last_chunk, last_vector, started, done = [], None, None, time.perf_counter(), 0
    for start in range(0, n, EMBED_GROUP):
        group = chunks[start:start + EMBED_GROUP]
        with timer.measure("embed"):
            vectors = vector_store.embed_texts([c.text for c in group])
        if not preview:
            preview = [[round(x, 3) for x in v[:8]] for v in vectors[:3]]    # a peek at the numbers
        with timer.measure("store"):
            for part in range(0, len(group), UPSERT_GROUP):
                vector_store.store_group(group[part:part + UPSERT_GROUP], vectors[part:part + UPSERT_GROUP])
        done += len(group)
        last_chunk, last_vector, dims = group[-1], vectors[-1], len(vectors[-1])
        eta = (time.perf_counter() - started) / done * (n - done)
        left = f" · about {eta / 60:.0f} min left" if eta > 90 else f" · about {eta:.0f} s left" if eta > 8 else ""
        yield StageEvent(stage="embed", status="running", data={"done": done, "total": n, "eta_s": round(eta)},
                         message=f"Embedded and uploaded {done:,} of {n:,} chunks{left}")
    yield StageEvent(stage="embed", status="done", ms=timer.totals["embed"],
                     message=f"{n:,} vectors x {dims} dimensions",
                     data={"dims": dims, "preview": preview, "total": n})
    _pause(slow)

    # --- Store (Pinecone): confirm the new cards can really be found ---------------
    yield StageEvent(stage="store", status="running", message="Waiting until Pinecone can search the new cards")
    with timer.measure("searchable"):                # Pinecone is eventually consistent - make it visible
        waited = vector_store.wait_until_searchable(last_chunk, last_vector)
    kb = vector_store.knowledge_base_summary()
    yield StageEvent(stage="store", status="done", ms=timer.totals["store"] + timer.last_ms,
                     message=(f"Stored {n:,} vectors in Pinecone; they became searchable after {waited}s. "
                              f"Knowledge base: {kb['total_chunks']:,} chunks."),
                     data={"knowledge_base": kb, "freshness_wait_s": waited, "total": n,
                           "department": chunks[0].department})

    yield StageEvent(stage="latency", status="info",
                     data={"totals": timer.totals, "chunks": len(chunks),
                           "ms_per_chunk": round(sum(timer.totals.values()) / len(chunks), 1)})


# =============================================================================
# 2. RETRIEVE:  Expand > Pre-filter > Dense > BM25 > Fuse > Post-filter > Re-rank
# =============================================================================
def _retrieve(question: str, args: ToolArgs, strategy: str, expansion: str, features: dict,
              timer: StageTimer, attempt: int, slow: bool):
    """Yields events, then *returns* the top results
    (the caller receives them through `top = yield from _retrieve(...)`)."""
    tag = {"attempt": attempt, "strategy": strategy}
    use_dense = strategy in ("dense", "hybrid", "hybrid_expansion")
    use_bm25 = strategy in ("bm25", "hybrid", "hybrid_expansion")
    needs_vectors = corpus.size() > MAP_MAX_POINTS   # big knowledge base: the 3D map only shows a sample

    # --- Expand (MQE or HyDE) - only for "hybrid + expansion" -----------------
    queries = {"original": args.query}   # label -> text; every label gets its own search
    hyde_passage = None
    if strategy == "hybrid_expansion":
        yield StageEvent(stage="expand", status="running", data={**tag, "method": expansion},
                         message="LLM writing extra queries (MQE)" if expansion == "mqe"
                         else "LLM writing a hypothetical answer passage (HyDE)")
        with timer.measure("expand"):
            if expansion == "mqe":
                for i, q in enumerate(multi_query(question), start=1):
                    queries[f"variant {i}"] = q
            else:
                hyde_passage = hypothetical_document(question)
        yield StageEvent(stage="expand", status="done", ms=timer.last_ms,
                         message=(f"MQE: {len(queries)} queries will be searched" if expansion == "mqe"
                                  else "HyDE: dense search will use the passage's embedding"),
                         data={**tag, "method": expansion, "queries": queries, "hyde_passage": hyde_passage})
    else:
        yield StageEvent(stage="expand", status="skipped", data=tag,
                         message=f"No expansion with the {STRATEGY_LABELS[strategy]} strategy")
    _pause(slow)

    # --- Pre-filter (metadata first) ------------------------------------------
    metadata_filter = build_metadata_filter(args)
    yield StageEvent(stage="prefilter", status="done", ms=0.0,
                     message=f"Metadata filter: {metadata_filter or 'none - search everything'}",
                     data={**tag, "filter": metadata_filter})
    _pause(slow)

    ranked_lists: dict[str, list[RetrievalResult]] = {}

    # --- Dense search (Pinecone) --------------------------------------------------
    if use_dense:
        # HyDE searches with the passage; MQE / plain search with every query text.
        dense_inputs = {"HyDE passage": hyde_passage} if hyde_passage else queries
        yield StageEvent(stage="dense", status="running", data=tag,
                         message=f"Embedding {len(dense_inputs)} text(s) and querying Pinecone")
        with timer.measure("dense"):
            vectors = {label: vector_store.embed_query(text) for label, text in dense_inputs.items()}
            dense_lists = {f"dense: {label}": dense_search(vec, metadata_filter, with_vectors=needs_vectors)
                           for label, vec in vectors.items()}
        ranked_lists.update(dense_lists)
        # Points for the 3D map: every searched text, plus the original query for comparison.
        to_plot = dict(vectors)
        if hyde_passage:
            to_plot["original question"] = vector_store.embed_query(args.query)
        points = [{"label": label, "xyz": xyz} for label, xyz in zip(to_plot, project(list(to_plot.values())))]
        hits = {r.chunk.id: r for res in dense_lists.values() for r in res if r.vector}   # where each hit sits in 3D
        hit_points = dict(zip(hits, project([r.vector for r in hits.values()]))) if hits else {}
        yield StageEvent(stage="dense", status="done", ms=timer.last_ms,
                         message=" | ".join(f"{label}: {len(res)} hits" for label, res in dense_lists.items()),
                         data={**tag, "lists": {l: [_card(r) for r in res] for l, res in dense_lists.items()},
                               "query_points": points, "hit_points": hit_points})
    else:
        yield StageEvent(stage="dense", status="skipped", data=tag, message="Dense search not used by BM25 strategy")
    _pause(slow)

    # --- BM25 keyword search (local) ----------------------------------------------
    if use_bm25:
        # HyDE's passage contains invented words, so BM25 keeps the user's real query.
        bm25_inputs = {"original": args.query} if hyde_passage else queries
        yield StageEvent(stage="bm25", status="running", data=tag, message="Scoring every chunk by shared keywords")
        with timer.measure("bm25"):
            bm25_lists = {f"bm25: {label}": bm25_search(text, args) for label, text in bm25_inputs.items()}
        ranked_lists.update(bm25_lists)
        yield StageEvent(stage="bm25", status="done", ms=timer.last_ms,
                         message=" | ".join(f"{label}: {len(res)} hits" for label, res in bm25_lists.items()),
                         data={**tag, "lists": {l: [_card(r) for r in res] for l, res in bm25_lists.items()},
                               "query_terms": {label: tokenize(text) for label, text in bm25_inputs.items()}})
    else:
        yield StageEvent(stage="bm25", status="skipped", data=tag, message="BM25 not used by Dense strategy")
    _pause(slow)

    # --- Fuse (RRF) - hybrid strategies only ----------------------------------------
    if len(ranked_lists) > 1:
        with timer.measure("fuse"):
            candidates = reciprocal_rank_fusion(ranked_lists)
        yield StageEvent(stage="fuse", status="done", ms=timer.last_ms,
                         message=f"RRF merged {len(ranked_lists)} lists into {len(candidates)} candidates",
                         data={**tag, "count": len(candidates), "lists": list(ranked_lists),
                               "results": [_card(r) for r in candidates]})
    else:
        candidates = next(iter(ranked_lists.values()))
        yield StageEvent(stage="fuse", status="skipped", data={**tag, "count": len(candidates),
                                                               "results": [_card(r) for r in candidates]},
                         message=f"Single list - nothing to fuse ({len(candidates)} candidates)")
    _pause(slow)

    # --- Post-filter (after search) -------------------------------------------
    if features["postfilter"]:
        with timer.measure("postfilter"):
            kept, report = post_filter(candidates)
        yield StageEvent(stage="postfilter", status="done", ms=timer.last_ms,
                         message=f"{len(candidates)} > {len(kept)} after filter",
                         data={**tag, "count": len(kept), "report": report, "results": [_card(r) for r in kept],
                               "dropped": [_card(r) for r in candidates if r not in kept][:12]})
    else:
        kept = candidates[:POST_FILTER_MAX]
        yield StageEvent(stage="postfilter", status="skipped",
                         message=f"Not part of this architecture - keeping the first {len(kept)} candidates",
                         data={**tag, "count": len(kept), "results": [_card(r) for r in kept]})
    _pause(slow)

    # --- Re-rank (cross-encoder) ----------------------------------------------
    if features["rerank"]:
        yield StageEvent(stage="rerank", status="running", message="Cross-encoder reading query + chunk pairs", data=tag)
        before = {r.chunk.id: i + 1 for i, r in enumerate(kept)}      # position before re-ranking
        with timer.measure("rerank"):
            scored = rerank(question, kept, top_n=len(kept))           # every survivor gets a score
        top = scored[:RERANK_TOP_N]
        yield StageEvent(stage="rerank", status="done", ms=timer.last_ms,
                         message=f"{len(kept)} > top {len(top)} after re-rank",
                         data={**tag, "count": len(top), "results": [_card(r) for r in top],
                               "ranking": [{**_card(r), "before_rank": before[r.chunk.id]} for r in scored],
                               "keep": len(top)})
    else:
        top = kept[:RERANK_TOP_N]
        yield StageEvent(stage="rerank", status="skipped",
                         message=f"Not part of this architecture - using the first {len(top)} chunks as they are",
                         data={**tag, "count": len(top), "results": [_card(r) for r in top]})
    _pause(slow)
    return top


# =============================================================================
# 3. GENERATE:  Query > Tool call > [retrieve] > Prompt > Answer > Reflect
# =============================================================================
@traceable(name="answer_question")
def answer_question(question: str, strategy: str = "hybrid", expansion: str = "mqe", slow: bool = True,
                    features: dict | None = None, architecture: str = ""):
    features = {**ALL_ON, **(features or {})}
    timer = StageTimer()
    yield StageEvent(stage="query", status="done", message=question,
                     data={"question": question, "llm_enabled": LLM_ENABLED, "strategy": strategy,
                           "expansion": expansion, "architecture": architecture, "features": features})
    _pause(slow)

    # --- Tool call: the LLM turns the question into search arguments ----------
    if features["tool_call"]:
        yield StageEvent(stage="tool_call", status="running", message="LLM choosing query + filters")
        with timer.measure("tool_call"):
            args, info = plan_search(question)
        yield StageEvent(stage="tool_call", status="done" if LLM_ENABLED else "skipped", ms=timer.last_ms,
                         message=f"search_knowledge_base({args.model_dump(exclude_none=True)})",
                         data={"args": args.model_dump(), "info": info})
    else:
        args = ToolArgs(query=question)
        yield StageEvent(stage="tool_call", status="skipped", message="Not part of this architecture - searching with your question as written",
                         data={"args": args.model_dump(), "info": {"mode": "off"}})
    _pause(slow)

    attempt = 1
    while True:
        top = yield from _retrieve(question, args, strategy, expansion, features, timer, attempt, slow)

        # --- Prompt rendering ---------------------------------------------------
        rendered = render_prompt(question, top)
        yield StageEvent(stage="prompt", status="done", ms=0.0,
                         message=f"{len(rendered)} characters sent to the LLM",
                         data={"attempt": attempt, "system": SYSTEM_PROMPT, "prompt": rendered,
                               "chunks": [_card(r) for r in top]})
        _pause(slow)

        # --- Answer -------------------------------------------------------------
        yield StageEvent(stage="answer", status="running", message="LLM writing the answer", data={"attempt": attempt})
        with timer.measure("answer"):
            answer = generate_answer(rendered, top)
        yield StageEvent(stage="answer", status="done" if LLM_ENABLED else "skipped", ms=timer.last_ms,
                         message="Answer ready", data={"attempt": attempt, "answer": answer})
        _pause(slow)

        # --- Reflection: is the answer grounded in the chunks? ------------------
        if not features["reflect"]:
            check = GroundingCheck(grounded=True, reason="Reflection is not part of this architecture.",
                                   unsupported_claims=[], rewritten_query=question)
            yield StageEvent(stage="reflect", status="skipped", message="Not part of this architecture",
                             data={"attempt": attempt, "check": check.model_dump()})
            break
        yield StageEvent(stage="reflect", status="running", message="Checking every claim against the chunks",
                         data={"attempt": attempt})
        with timer.measure("reflect"):
            check = check_grounding(question, answer, top)
        yield StageEvent(stage="reflect", status="done" if LLM_ENABLED else "skipped", ms=timer.last_ms,
                         message="Grounded" if check.grounded else "NOT grounded",
                         data={"attempt": attempt, "check": check.model_dump()})

        if check.grounded or attempt == 2:
            break

        # --- Retry once with a rewritten query and no filters -------------------
        attempt = 2
        args = ToolArgs(query=check.rewritten_query)
        yield StageEvent(stage="retry", status="info",
                         message=f"Retrying once with rewritten query: {args.query!r}",
                         data={"attempt": attempt, "rewritten_query": args.query})
        _pause(slow)

    yield StageEvent(stage="latency", status="info", data={"totals": timer.totals})
    yield StageEvent(stage="final", status="done", message=answer,
                     # grounded=None means "not checked" (no LLM, or reflection is off)
                     data={"answer": answer, "grounded": check.grounded if (LLM_ENABLED and features["reflect"]) else None,
                           "attempts": attempt, "contexts": [r.chunk.text for r in top],
                           "sources": [{"source": r.chunk.source, "chunk_index": r.chunk.chunk_index} for r in top]})


def run_question(question: str, strategy: str = "hybrid", expansion: str = "mqe") -> dict:
    """Run the whole flow without the UI and return the final event's data (used by the evals)."""
    final = {}
    for event in answer_question(question, strategy, expansion, slow=False):
        if event.stage == "final":
            final = event.data
    return final


if __name__ == "__main__":
    for strategy in ["dense", "bm25", "hybrid", "hybrid_expansion"]:
        print(f"\n===== {strategy} =====")
        for e in answer_question("Can I use SMS codes for MFA?", strategy=strategy, slow=False):
            if e.status in ("done", "skipped") and e.stage in ("dense", "bm25", "fuse", "postfilter", "rerank"):
                print(f"[{e.stage:>10}] {e.status:<7} {e.message[:100]}")
