"""
config.py - every tunable knob in one place.

WHY: students should be able to change chunk size, top-k or the model
without hunting through files. Values come from .env (see .env.example)
with sensible defaults, so the app runs even with an empty .env.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")  # read keys into os.environ before anything else

# ---- Paths -----------------------------------------------------------------
SAMPLE_DOCS_DIR = ROOT / "data" / "sample_docs"   # the starting knowledge base
NEW_DOCS_DIR = ROOT / "data" / "new_docs"         # a document to upload live in class
UPLOAD_DIR = ROOT / "data" / "uploads"            # files added while the app runs
EVAL_SET_PATH = ROOT / "data" / "eval_set.json"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# ---- LLM: OpenAI models through OpenRouter -----------------------------------
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "openai/gpt-5.6-sol")        # writes the final answer
FAST_LLM_MODEL = os.getenv("FAST_LLM_MODEL", "openai/gpt-6-luna")  # cheap: tool call, MQE, HyDE, judges
# No key = "offline mode": retrieval still runs and is visualised, LLM steps are skipped.
LLM_ENABLED = bool(OPENROUTER_API_KEY)

# ---- Embeddings ----------------------------------------------------------------
# "openrouter": OpenAI text-embedding-3-small, 1536 numbers per text, ~$0.02 per million tokens.
#               Matches the 1536-dimension Pinecone index "retrieval-lab-dense".
# "local":      MiniLM on this machine, 384 numbers, free. Needs a 384-dimension Pinecone index.
EMBEDDING_BACKEND = os.getenv("EMBEDDING_BACKEND", "openrouter")
if EMBEDDING_BACKEND == "local":
    EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
    EMBEDDING_DIM = 384
else:
    EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "openai/text-embedding-3-small")
    EMBEDDING_DIM = 1536
RERANK_MODEL = os.getenv("RERANK_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2")  # always local

# ---- Vector database: Pinecone (the ONLY store - no local database) ----------
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY", "")
PINECONE_INDEX = os.getenv("PINECONE_INDEX", "retrieval-lab-dense")
PINECONE_CLOUD = os.getenv("PINECONE_CLOUD", "aws")
PINECONE_REGION = os.getenv("PINECONE_REGION", "us-east-1")
# A namespace is a private folder inside the index: "Empty the knowledge base" only
# ever deletes THIS namespace, never other data that lives in the same index.
PINECONE_NAMESPACE = os.getenv("PINECONE_NAMESPACE", "knowledge-base")

# ---- Big-file safety ------------------------------------------------------------
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "60"))             # reject bigger uploads outright
MAX_INGEST_CHARS = int(os.getenv("MAX_INGEST_CHARS", "200000"))   # classroom limit per file (~500 chunks)
MAX_CARDS_IN_EVENT = 40       # chunk cards sent to the browser per file (the rest are only counted)
MAP_MAX_POINTS = 150          # chunks drawn in the 3D map (a sample if the knowledge base is bigger)
LENS_MAX_TILES = 120          # above this the search lens shows only the chunks a search touched
EMBED_GROUP = 256             # texts embedded per progress step
UPSERT_GROUP = 200            # vectors sent to Pinecone per progress step

# ---- Chunking defaults -----------------------------------------------------
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "400"))        # characters per chunk
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "60"))   # characters shared by neighbours
DEFAULT_STRATEGY = os.getenv("CHUNK_STRATEGY", "recursive")

# ---- Retrieval funnel: 20 candidates > 8 after filter > top 4 after re-rank -
SEARCH_K = int(os.getenv("SEARCH_K", "20"))        # how many each search returns
POST_FILTER_MAX = int(os.getenv("POST_FILTER_MAX", "8"))
MIN_RELEVANCE = float(os.getenv("MIN_RELEVANCE", "0.20"))  # weakest cosine we keep
RERANK_TOP_N = int(os.getenv("RERANK_TOP_N", "4"))
RRF_K = 60            # Reciprocal Rank Fusion constant (the value from the original paper)
MQE_VARIANTS = 3      # how many extra queries Multi-Query Expansion writes

# ---- Teaching aid ----------------------------------------------------------
# Small pause between stages in auto-play mode so each box visibly lights up.
STAGE_DELAY_SECONDS = float(os.getenv("STAGE_DELAY_SECONDS", "0.35"))
