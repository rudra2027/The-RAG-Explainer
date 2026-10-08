# The RAG Explainer

> A visualizer of how different RAG architectures and the individual steps of RAG - ingestion, embedding, chunking, pre-filtering, post-filtering, lexical search, semantic search, query enhancement, retrieval, LLM-as-judge - work in an enterprise RAG, along with evaluations. It helps you decide which RAG strategy fits your use case.

**An interactive classroom and lab for Retrieval-Augmented Generation (RAG).**
Upload your own PDF / TXT / Markdown files and *watch* every step happen - a file breaking into chunks, meaning-search vs keyword-search, two ranked lists merging, a judge re-ranking cards - then **measure with RAG evals which chunking and retrieval strategy works best for your documents**.

It is built for learning, not production: small files, one concept per module, comments that explain *why*.

```
1 Ingest            2 Retrieve                                3 Generate                    4 Evaluate
load, chunk,   ->   expand (MQE/HyDE), pre-filter, dense,  -> tool call, render prompt,  ->  RAGAS, DeepEval,
embed, store        BM25, fuse (RRF), post-filter, re-rank    answer, reflect (+retry)      LangSmith traces
```

---

## What it does

| | |
|---|---|
| **Animated step-by-step stage** | Every step opens a centred animation built from *your* data, with a plain-language story (written for an 8th-9th grader) and a **Next step ▶** button. Nothing runs until you click, so you can follow at your own pace. |
| **Ingestion strategies** | Load PDF/TXT/MD, three chunking strategies side by side (fixed, recursive, markdown-heading), adjustable chunk size and overlap, metadata tagging, embeddings, and storage in Pinecone. |
| **Retrieval strategies** | Dense (meaning), BM25 (keywords), Hybrid with Reciprocal Rank Fusion, query expansion with **MQE** (multi-query) or **HyDE** (hypothetical answer), metadata **pre-filtering**, **post-filtering**, and cross-encoder **re-ranking**. |
| **Generation** | LLM **tool calling** plans the search (query + filters), prompt rendering with numbered citations, and a **reflection** step that checks the answer is grounded and retries once. |
| **8 RAG architectures** | One page each (top menu): Naive, Keyword, Hybrid, Advanced, Multi-Query, HyDE, Agentic, Self-Reflective. Each has an animated flow and a **Run** button that executes it on your files. |
| **RAG evals** | **RAGAS** (faithfulness, answer relevancy, context precision, context recall), **DeepEval** (the same ideas as pass/fail tests), and optional **LangSmith** traces of every run. |
| **Decide what is best for you** | Chunking Lab + strategy dropdowns + evals on *your own questions*, per strategy. See [Choosing the best strategy](#choosing-the-best-chunking-and-retrieval-strategy-for-your-use-case). |
| **Live views** | 3D embedding space, a "search lens" showing every chunk's dense / BM25 / fused score, the 20 → 8 → 4 funnel, and per-stage latency bars. |
| **Big-file safe** | A 22 MB file (≈80,000 chunks) will not freeze the app: streaming ingestion, progress with ETA, cost estimate, and a fast "first part only" option. |

---

## Setup

### Prerequisites

- **Python 3.11** (3.10+ should work)
- A **Pinecone** account and API key - <https://www.pinecone.io> (the free tier is enough)
- An **OpenRouter** API key - <https://openrouter.ai> (one key for the LLM *and* the embeddings; a full classroom session costs cents)
- Internet access (the UI loads Three.js, the LottieFiles player and Google Fonts from CDNs)

### 1. Install

```bash
git clone https://github.com/rudra2027/The-RAG-Explainer.git
cd The-RAG-Explainer

python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS / Linux:
source .venv/bin/activate

pip install -r requirements.txt
```

The first run also downloads a small local re-ranker model (~90 MB) from Hugging Face.

### 2. Configure your keys

```bash
# Windows:        copy .env.example .env
# macOS / Linux:  cp .env.example .env
```

Open `.env` and fill in:

```ini
OPENROUTER_API_KEY=sk-or-...        # LLM + embeddings
PINECONE_API_KEY=pcsk_...           # vector database
PINECONE_INDEX=retrieval-lab-dense  # any name; created automatically if it does not exist
```

> `.env` is git-ignored. **Never commit your keys.**

**Pinecone index:** the default embeddings are 1536-dimensional (OpenAI `text-embedding-3-small`). If the index does not exist, the app creates it (cosine, AWS `us-east-1`, serverless). If you point at an existing index it must have **1536 dimensions** - the app checks this and tells you clearly if it does not. Your data lives in its own *namespace* (`knowledge-base`), so other data in the same index is never touched.

**Prefer free local embeddings?** Set `EMBEDDING_BACKEND=local` (MiniLM, 384 dimensions) and use a 384-dimension index.

### 3. Run

```bash
uvicorn app.server:app --reload
```

Open **http://127.0.0.1:8000**. Click the **Pinecone** chip in the header to test the connection.

Prefer the terminal? `python demo.py` runs the whole story (ingest → four search strategies → upload a new file → ask again).

### 4. First five minutes

1. **Ingest sample docs** (left panel) - leave *Step-by-step* on and click **Next step ▶** through Load → Chunk → Embed → Store.
2. Pick a **search strategy**, click an example question, and walk through the retrieval steps.
3. **Drop your own PDF / TXT / MD** into the upload box, then press **✨ Suggest from my files** to get a question your document can answer.
4. Open **Chunking Lab** to compare chunking strategies on your file.
5. Open **RAG Architectures** in the top bar to see and run one architecture at a time.
6. Open **Evals** to score the pipeline.

---

## Choosing the best chunking and retrieval strategy for your use case

There is no universally best strategy - it depends on your documents and questions. The Explainer lets you **look first, then measure**.

### Step 1 - Look at your documents (Chunking Lab)

Open **Chunking Lab**, pick your file, and compare the three chunkers side by side.

| Chunker | Cuts at | Choose it when |
|---|---|---|
| **recursive** (default) | paragraph → line → sentence → word | most prose: articles, policies, manuals |
| **markdown** | headings (`#`, `##`, `###`) first | structured docs with meaningful headings - each chunk stays inside one section |
| **fixed** | every N characters | almost never; it shows what *not* to do (words are cut in half) |

Then tune **chunk size** and **overlap** and watch how the cards change. Rules of thumb: small chunks (200-400 characters) are precise but lose context; large chunks (800+) keep context but blur meaning and add noise to the prompt. Overlap (10-20%) protects sentences that sit on a boundary.

### Step 2 - Look at retrieval (strategy dropdowns)

Ask the **same question** with each strategy and watch the *search lens* and the 3D map:

| Strategy | Wins when | Struggles when |
|---|---|---|
| **Dense** | users paraphrase ("time off" vs "annual leave"); meaning matters | exact codes, names, numbers ("extension 4400") |
| **BM25** | exact terms, IDs, jargon | synonyms and paraphrases |
| **Hybrid (RRF)** | mixed questions - the safe default | very vague questions |
| **Hybrid + MQE** | vague or oddly-worded questions (better recall) | you need low latency / low cost |
| **Hybrid + HyDE** | questions phrased unlike the documents | the invented passage drifts off-topic |

Add **pre-filtering** (the AI picks a department/file type), **post-filtering** and **re-ranking** when you need higher precision. The **RAG Architectures** pages show these combinations as eight ready-made presets.

### Step 3 - Measure (Evals on your own questions)

Looking is not proof. Evals give you numbers:

1. Ingest *your* documents.
2. Edit **`data/eval_set.json`** - 10-20 questions with a short reference answer from your documents:
   ```json
   [
     { "question": "What is the refund window for annual plans?",
       "reference": "Annual plans can be refunded within 30 days of purchase." }
   ]
   ```
3. Open **Evals**, choose a **search strategy**, click **Run RAGAS** (or **Run DeepEval**).
4. **Repeat for each strategy** (and, to compare chunking, re-ingest with a different chunker / size and run again). Compare the summary tables.

### How to read the scores

| Metric (RAGAS) | Question it answers | If it is low... |
|---|---|---|
| **Context recall** | Did retrieval find everything the reference answer needs? | fix *retrieval/chunking*: smaller or markdown chunks, hybrid search, MQE/HyDE |
| **Context precision** | Are the useful chunks ranked first? | add post-filter + **re-rank**, or lower the number of chunks sent to the LLM |
| **Faithfulness** | Are the answer's claims supported by the chunks? | tighten the prompt, enable **reflection**, use a stronger answer model |
| **Answer relevancy** | Does the answer address the question? | improve the query: tool-calling, MQE |

**DeepEval** runs the same checks as unit tests with a threshold (default 0.7) and shows PASS / FAIL, so you can guard a strategy the way you would guard code in CI. **LangSmith** (optional) keeps a searchable trace of every run: set `LANGSMITH_TRACING=true` and `LANGSMITH_API_KEY` in `.env`.

> **Be careful with the numbers.** Scores come from an LLM judge, so they are noisy. Use at least 10-20 questions, write questions your real users would ask, and trust big differences more than small ones. The built-in `eval_set.json` is about the sample company documents - replace it for your own data.

### A sensible starting recipe

| Your content | Start with |
|---|---|
| Policies, FAQs, manuals (prose) | recursive, ~400 chars / 60 overlap, **Hybrid** + re-rank |
| Docs with clear headings (wikis, README-style) | **markdown** chunker, Hybrid |
| Lots of IDs, product codes, names | Hybrid or BM25-heavy; keep chunks small |
| Short, vague user questions | add **MQE**; try **HyDE** if documents are formal |
| High-stakes answers | **Self-Reflective** architecture (grounding check + retry) |
| Large, departmentalised knowledge base | **Agentic** (tool-call filters) + re-rank |

---

## The eight architectures

Each is a *preset of existing stages* (see `app/architectures.py`) - open one from **RAG Architectures** in the top bar, press **▶ Play animated explainer**, then **Run this architecture** on your files.

| Architecture | Stages that run |
|---|---|
| Naive RAG | dense → answer |
| Keyword RAG (BM25) | BM25 → answer |
| Hybrid RAG | dense + BM25 → RRF → answer |
| Advanced RAG | hybrid → post-filter → re-rank → answer |
| Multi-Query RAG (MQE) | LLM writes extra queries → hybrid → post-filter → re-rank |
| HyDE RAG | LLM writes a pretend answer → hybrid → post-filter → re-rank |
| Agentic RAG | LLM tool call picks query + filters → hybrid → post-filter → re-rank |
| Self-Reflective RAG | everything above + grounding check + one retry |

---

## Configuration

Everything lives in `.env` (see `.env.example`); defaults are in `app/config.py`.

| Setting | Default | What it does |
|---|---|---|
| `LLM_MODEL` | `openai/gpt-5.6-sol` | writes the final answer |
| `FAST_LLM_MODEL` | `openai/gpt-6-luna` | cheap model for tool calls, MQE, HyDE, reflection, eval judges |
| `EMBEDDING_BACKEND` | `openrouter` | `openrouter` (1536-dim) or `local` (384-dim) |
| `PINECONE_INDEX` / `PINECONE_NAMESPACE` | `retrieval-lab-dense` / `knowledge-base` | where vectors are stored |
| `CHUNK_SIZE` / `CHUNK_OVERLAP` | `400` / `60` | chunking defaults (also sliders in the UI) |
| `SEARCH_K`, `POST_FILTER_MAX`, `RERANK_TOP_N` | `20`, `8`, `4` | the retrieval funnel |
| `MAX_UPLOAD_MB` / `MAX_INGEST_CHARS` | `60` / `200000` | big-file guards (the *fast* option) |

Model names are OpenRouter ids - check <https://openrouter.ai/models> for current prices.

### Big files

A 22 MB file is about 80,000 chunks. In the **Big files** dropdown choose *First part only* (fast, default) or *The whole file*. The upload note shows the estimate (for 22 MB: ≈47 minutes, ≈$0.11) and asks you to confirm before a long run. Ingestion streams in groups with a progress bar and ETA, so memory stays flat. Keep the tab open while it runs. After a server restart the chunk texts are re-read from Pinecone in the background (progress is shown).

---

## Project structure

```
app/
  config.py               every knob, read from .env
  schemas.py              Pydantic shapes (Chunk, RetrievalResult, ToolArgs, GroundingCheck, EvalScore, ...)
  architectures.py        the eight RAG architectures as presets
  pipeline.py             ingest_file() and answer_question(): generators that yield live events
  server.py               FastAPI + Server-Sent Events + step-by-step gates + uploads
  ingestion/              loaders, chunking, metadata, embedder, pinecone_db, vector_store, corpus
  retrieval/              expansion (MQE/HyDE), prefilter, dense, bm25, fusion (RRF), postfilter, rerank, prompt, vector_map
  generation/             llm (OpenRouter), tools (tool calling), answer, reflection, suggest
  evals/                  ragas_eval, deepeval_eval, tracing (LangSmith)
static/                   index.html, css, js (theater = animated stage, arch = architecture pages, lens, 3D map)
data/                     sample_docs/, new_docs/, eval_set.json
scripts/make_lottie.py    generates the Lottie animation files
demo.py                   one-command terminal demo
```

Every module runs on its own with a short demo, e.g.:

```bash
python -m app.ingestion.chunking     # three chunkers on one paragraph
python -m app.retrieval.bm25         # tokens + BM25 scores
python -m app.retrieval.fusion       # RRF on two tiny lists
python -m app.retrieval.rerank       # cross-encoder vs. the word "leave"
python -m app.architectures          # the stages each architecture runs
python -m app.evals.ragas_eval       # RAGAS scores (needs keys)
```

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| Header chip shows Pinecone problem | check `PINECONE_API_KEY`; click the chip for the exact error |
| "index has N dimensions but ... makes 1536" | use a 1536-dimension index, or set `EMBEDDING_BACKEND=local` with a 384-dim index |
| "Still reading your knowledge base back from Pinecone" | after a restart; wait for the blue progress banner to finish |
| Evals say they need an LLM judge | set `OPENROUTER_API_KEY` |
| Slow ingestion | most time is network (embedding API + Pinecone); chunking itself takes milliseconds |
| Changes made by `demo.py` not visible in the UI | restart the server (the chunk texts are loaded at start-up) |

## Notes and limitations

- **Pinecone is the only store.** Nothing is saved to a local database; "Empty the knowledge base" deletes only your namespace.
- **Evals are slow and approximate**: RAGAS makes many judge calls (~2 minutes per question), and judge scores vary.
- **The 3D map is an approximation** (PCA keeps only part of the information); all scores use the full vectors.
- **The explainers are animated diagrams** generated live in the browser, not video files.
- A tab closed mid-run stops that run; chunks already stored stay in Pinecone and re-uploading the same file replaces them.
