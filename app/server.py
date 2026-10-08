"""
server.py - FastAPI backend + live progress events (Server-Sent Events) + step-by-step control.

WHY SSE: the browser opens one long HTTP response and the server writes a
line of JSON every time a pipeline stage finishes. One-directional
(server -> browser), no extra library, perfect for "watch the pipeline run".

STEP-BY-STEP MODE: the pipeline is a generator, so the next stage only runs
when we ask for the next event. After each finished stage the server sends a
"pause" event and simply *waits* until the browser POSTs /api/continue.
Nothing is pre-computed: the next step truly executes after the click.

If the browser tab is closed or reloaded while a run is paused, the server notices
(request.is_disconnected) and stops the run - otherwise every abandoned run would
keep a worker thread busy and the app would slowly freeze.

Run:   uvicorn app.server:app --reload      then open http://127.0.0.1:8000
"""
import asyncio
import shutil
import threading
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Iterator

from fastapi import FastAPI, HTTPException, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from app.architectures import ARCHITECTURES, features_of, public_view
from app.config import (CHUNK_OVERLAP, CHUNK_SIZE, DEFAULT_STRATEGY, EMBEDDING_BACKEND, EMBEDDING_DIM,
                        EMBEDDING_MODEL, FAST_LLM_MODEL, LENS_MAX_TILES, LLM_ENABLED, LLM_MODEL, MAX_INGEST_CHARS,
                        MAX_UPLOAD_MB, NEW_DOCS_DIR, PINECONE_INDEX, PINECONE_NAMESPACE, ROOT, SAMPLE_DOCS_DIR,
                        UPLOAD_DIR)
from app.evals.tracing import tracing_status
from app.ingestion import corpus
from app.ingestion.chunking import STRATEGIES, compare_strategies
from app.ingestion.loaders import SUPPORTED_TYPES, estimate_ingest, limit_text, load_as_single_text
from app.ingestion.vector_store import clear_all, knowledge_base_summary
from app.pipeline import answer_question, ingest_file
from app.retrieval.rerank import get_cross_encoder
from app.retrieval.vector_map import chunk_points
from app.schemas import StageEvent


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Warm up once at start-up so the first question in class does not show a misleading
    # "30 s re-rank" (that would be model loading): the cross-encoder, and the chunk texts
    # that live in Pinecone (in the background). A problem here is reported, not fatal - the UI shows it.
    get_cross_encoder()
    try:
        from app.ingestion import pinecone_db
        pinecone_db._grpc_index()   # open the fast upload channel now, not during the first ingest
    except Exception as exc:
        print(f"WARNING: could not open the Pinecone upload channel: {exc}")
    corpus.start_background_load()   # reading the chunk texts back can take minutes for a big collection
    yield


app = FastAPI(title="RAG Learning Visualiser", lifespan=lifespan)
STATIC_DIR = ROOT / "static"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


# ---- step-by-step gates --------------------------------------------------------
class StepGate:
    """One per run. The stream waits on it; the 'Next step' click releases it."""
    def __init__(self) -> None:
        self.event = threading.Event()
        self.run_to_end = False


GATES: dict[str, StepGate] = {}
PAUSE_AFTER = {"done"}  # pause after a finished stage (never after "running" or a skipped stage)
NO_PAUSE_STAGES = {"latency", "final", "error"}


def _data(event: StageEvent) -> str:
    return f"data: {event.model_dump_json()}\n\n"


def sse(events: Iterator[StageEvent], request: Request | None = None, run_id: str = "",
        step: bool = False) -> StreamingResponse:
    """Turn StageEvents into an SSE response ("data: {...}\\n\\n" per event).

    The pipeline is plain blocking Python, so each `next()` runs in a worker thread
    (run_in_threadpool) while the async loop stays free to notice a closed browser tab."""
    gate = GATES.setdefault(run_id, StepGate()) if step else None

    async def stream():
        try:
            while True:
                event = await run_in_threadpool(next, events, None)   # None = the generator is finished
                if event is None:
                    break
                yield _data(event)
                if gate and not gate.run_to_end and event.status in PAUSE_AFTER and event.stage not in NO_PAUSE_STAGES:
                    yield _data(StageEvent(stage="pause", status="info", data={"after": event.stage, "run": run_id}))
                    while not gate.event.is_set():                     # wait for the "Next step" click...
                        if request is not None and await request.is_disconnected():
                            return                                     # ...or give up if the tab is gone
                        await asyncio.sleep(0.25)
                    gate.event.clear()
        except Exception as exc:  # show the error in the UI instead of a silent hang
            yield _data(StageEvent(stage="error", status="error", message=f"{type(exc).__name__}: {exc}"))
        finally:
            GATES.pop(run_id, None)
            getattr(events, "close", lambda: None)()   # stop the pipeline generator if we left early
        yield _data(StageEvent(stage="end", status="info"))
    return StreamingResponse(stream(), media_type="text/event-stream")


def sse_error(message: str) -> StreamingResponse:
    """An SSE stream with a single error event (EventSource cannot read a 400 response body)."""
    return sse(iter([StageEvent(stage="error", status="error", message=message)]))


@app.post("/api/continue")
def continue_run(run: str, mode: str = "next"):
    """'Next step' (mode=next) or 'Run to end' (mode=all) for a paused run."""
    gate = GATES.get(run)
    if not gate:
        raise HTTPException(404, "This run is not waiting")
    gate.run_to_end = mode == "all"
    gate.event.set()
    return {"ok": True}


# ---- helpers ---------------------------------------------------------------
def find_file(name: str) -> Path:
    """Look up a document by name in the sample + upload folders (never outside them)."""
    safe_name = Path(name).name  # strips any "../" tricks
    for folder in (UPLOAD_DIR, SAMPLE_DOCS_DIR):
        if (folder / safe_name).exists():
            return folder / safe_name
    raise HTTPException(404, f"File '{safe_name}' not found")


def all_files() -> list[str]:
    return sorted({p.name for folder in (SAMPLE_DOCS_DIR, UPLOAD_DIR) for p in folder.iterdir()
                   if p.suffix.lower() in SUPPORTED_TYPES})


# ---- pages + status ----------------------------------------------------------
@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/status")
def status():
    try:
        kb = knowledge_base_summary()
        problem = None
    except Exception as exc:   # e.g. Pinecone unreachable: tell the UI instead of returning a 500
        kb, problem = {"total_chunks": 0, "documents": []}, f"{type(exc).__name__}: {exc}"
    return {
        "llm_enabled": LLM_ENABLED, "model": LLM_MODEL, "fast_model": FAST_LLM_MODEL,
        "embedding": {"backend": EMBEDDING_BACKEND, "model": EMBEDDING_MODEL, "dims": EMBEDDING_DIM},
        "vector_db": {"name": "Pinecone", "index": PINECONE_INDEX, "namespace": PINECONE_NAMESPACE},
        "limits": {"max_upload_mb": MAX_UPLOAD_MB, "max_ingest_chars": MAX_INGEST_CHARS, "lens_max_tiles": LENS_MAX_TILES},
        "tracing": tracing_status(), "strategies": STRATEGIES, "files": all_files(),
        "defaults": {"strategy": DEFAULT_STRATEGY, "size": CHUNK_SIZE, "overlap": CHUNK_OVERLAP},
        "knowledge_base": kb, "problem": problem, "loading": corpus.progress(),
    }


@app.get("/api/pinecone-check")
def pinecone_check():
    """Prove the Pinecone connection end to end (used by the status chip)."""
    from app.ingestion import pinecone_db
    import time
    start = time.perf_counter()
    try:
        index = pinecone_db.get_index()
        stats = index.describe_index_stats()
        return {"ok": True, "index": PINECONE_INDEX, "dimension": stats.dimension,
                "namespace": PINECONE_NAMESPACE, "vectors_in_namespace": pinecone_db.count(),
                "vectors_in_index": stats.total_vector_count, "ms": round((time.perf_counter() - start) * 1000)}
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


@app.get("/api/architectures")
def architectures():
    return {"architectures": public_view()}


@app.get("/api/suggest-question")
def suggest():
    from app.generation.suggest import suggest_question
    try:
        return {"question": suggest_question()}
    except Exception as exc:
        raise HTTPException(502, f"Could not suggest a question: {exc}")


@app.get("/api/vector-map")
def vector_map():
    """A sample of stored chunks as points in 3D (PCA of their embeddings) for the 3D view."""
    try:
        return chunk_points()
    except corpus.KnowledgeBaseLoading:
        return {"points": [], "total": 0, "sampled": False, "loading": True}


# ---- 1. ingestion ------------------------------------------------------------
@app.get("/api/ingest")
def ingest(request: Request, file: str, strategy: str = DEFAULT_STRATEGY, size: int = CHUNK_SIZE,
           overlap: int = CHUNK_OVERLAP, run: str = "", step: bool = False, whole: bool = False):
    """Ingest one file (sample or uploaded) and stream every stage.
    whole=true ingests the entire file instead of the first MAX_INGEST_CHARS characters."""
    return sse(ingest_file(find_file(file), strategy, size, overlap, slow=not step,
                           max_chars=None if whole else MAX_INGEST_CHARS), request, run, step)


@app.get("/api/ingest-samples")
def ingest_samples(request: Request, strategy: str = DEFAULT_STRATEGY, size: int = CHUNK_SIZE,
                   overlap: int = CHUNK_OVERLAP, run: str = "", step: bool = False):
    """Ingest the whole starter knowledge base, one file after another."""
    def all_events():
        for path in sorted(SAMPLE_DOCS_DIR.iterdir()):
            yield from ingest_file(path, strategy, size, overlap, slow=False)
    return sse(all_events(), request, run, step)


@app.post("/api/upload")
async def upload(file: UploadFile):
    """Dynamic ingestion, part 1: save the file. The UI then calls /api/ingest to watch it.
    The file is copied in 1 MB pieces and refused once it passes MAX_UPLOAD_MB."""
    import time
    name = Path(file.filename or "").name
    if Path(name).suffix.lower() not in SUPPORTED_TYPES:
        raise HTTPException(400, "Only PDF, TXT and MD files are supported")
    target, size, start = UPLOAD_DIR / name, 0, time.perf_counter()
    with open(target, "wb") as out:
        while piece := await file.read(1024 * 1024):
            size += len(piece)
            if size > MAX_UPLOAD_MB * 1024 * 1024:
                out.close()
                target.unlink(missing_ok=True)
                raise HTTPException(413, f"{name} is bigger than {MAX_UPLOAD_MB} MB (MAX_UPLOAD_MB in .env)")
            out.write(piece)
    # For text files the size in bytes is close to the number of characters, so we can estimate the cost.
    estimate = estimate_ingest(size) if target.suffix.lower() in (".md", ".txt") else None
    return {"filename": name, "size_mb": round(size / 1e6, 2), "upload_ms": round((time.perf_counter() - start) * 1000),
            "estimate": estimate, "estimate_fast": estimate_ingest(min(size, MAX_INGEST_CHARS)) if estimate else None}


@app.post("/api/upload-demo")
def upload_demo():
    """Shortcut for class: 'upload' the prepared new document from data/new_docs."""
    demo = NEW_DOCS_DIR / "general_office_move_2027.md"
    shutil.copy(demo, UPLOAD_DIR / demo.name)
    return {"filename": demo.name}


@app.post("/api/reset")
def reset():
    """Empty the knowledge base: delete every vector in our Pinecone namespace."""
    removed = clear_all()
    return {"removed": removed, **knowledge_base_summary()}


@app.get("/api/chunk-preview")
def chunk_preview(file: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP):
    """Chunking Lab: the same document split by every strategy, side by side."""
    if overlap >= size:
        raise HTTPException(400, "Overlap must be smaller than chunk size")
    text, _ = limit_text(load_as_single_text(find_file(file)), MAX_INGEST_CHARS // 4)  # a preview needs less
    return compare_strategies(text, size, overlap)


# ---- 2 + 3. retrieval + generation -------------------------------------------
@app.get("/api/ask")
def ask(request: Request, q: str, strategy: str = "hybrid", expansion: str = "mqe", arch: str = "",
        run: str = "", step: bool = False):
    features = {}
    if arch:   # an architecture preset overrides the dropdowns
        if arch not in ARCHITECTURES:
            return sse_error(f"Unknown architecture '{arch}'")
        config = ARCHITECTURES[arch]["config"]
        strategy, expansion, features = config["strategy"], config["expansion"], features_of(config)
    if strategy not in ("dense", "bm25", "hybrid", "hybrid_expansion") or expansion not in ("mqe", "hyde"):
        return sse_error("Unknown strategy or expansion")
    if corpus.progress()["active"]:
        p = corpus.progress()
        return sse_error(f"Still reading your knowledge base back from Pinecone ({p['done']:,} of {p['total'] or '?'} chunks) - try again in a moment.")
    if knowledge_base_summary()["total_chunks"] == 0:
        return sse_error("The knowledge base is empty - click 'Ingest sample docs' first.")
    return sse(answer_question(q, strategy, expansion, slow=not step, features=features, architecture=arch),
               request, run, step)


# ---- 4. evaluation -----------------------------------------------------------
@app.get("/api/eval")
def evaluate(request: Request, framework: str = "ragas", strategy: str = "hybrid", expansion: str = "mqe"):
    if not LLM_ENABLED:
        return sse_error("Evals need an LLM judge - set OPENROUTER_API_KEY in .env")
    if strategy not in ("dense", "bm25", "hybrid", "hybrid_expansion") or expansion not in ("mqe", "hyde"):
        return sse_error("Unknown strategy or expansion")
    if framework == "ragas":
        from app.evals.ragas_eval import run_ragas_events as events
    elif framework == "deepeval":
        from app.evals.deepeval_eval import run_deepeval_events as events
    else:
        return sse_error("framework must be 'ragas' or 'deepeval'")
    return sse(events(strategy, expansion), request)
