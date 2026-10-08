"""
demo.py - the whole story in one command:   python demo.py

  0. Empty the knowledge base (our Pinecone namespace only), so earlier uploads cannot interfere
  1. Ingest the sample documents into Pinecone      (Load > Chunk > Embed > Store)
  2. Same question, four search strategies          (dense vs BM25 vs hybrid vs hybrid + MQE)
  3. Ask something NO document answers yet
  4. Add a new document while running               (dynamic ingestion)
  5. Ask again - now it can answer

Needs PINECONE_API_KEY. Without OPENROUTER_API_KEY it runs in offline mode
(retrieval only, no LLM answer).
"""
import shutil

from app.config import LLM_ENABLED, NEW_DOCS_DIR, SAMPLE_DOCS_DIR, UPLOAD_DIR
from app.ingestion.vector_store import clear_all
from app.pipeline import answer_question, ingest_file

SEARCH_STAGES = ("expand", "dense", "bm25", "fuse", "postfilter", "rerank")


def show(events, stages=None) -> None:
    for e in events:
        if e.status in ("done", "skipped") and (stages is None or e.stage in stages) \
                and e.stage not in ("latency", "final", "query"):
            ms = f"{e.ms:>7.0f} ms" if e.ms is not None else " " * 10
            print(f"  {e.stage:<10} {ms}  {e.message[:110]}")
        if e.stage == "rerank" and e.status == "done":
            print("  top chunks:", [f"{r['source']}#{r['chunk_index']}" for r in e.data["results"]])
        if e.stage == "final":
            print(f"  ANSWER (grounded={e.data['grounded']}): {e.data['answer'][:200]}\n")


def main() -> None:
    print(f"LLM enabled: {LLM_ENABLED}\n")

    print(f"=== 0. Emptied the knowledge base ({clear_all()} chunks removed) ===")
    print("\n=== 1. Ingest sample documents into Pinecone ===")
    for path in sorted(SAMPLE_DOCS_DIR.iterdir()):
        show(ingest_file(path, slow=False), stages=("store",))

    question = "Who do I call on extension 4400?"
    for strategy in ["dense", "bm25", "hybrid", "hybrid_expansion"]:
        print(f"\n=== 2. '{question}' with strategy = {strategy} ===")
        show(answer_question(question, strategy=strategy, expansion="mqe", slow=False), stages=SEARCH_STAGES)

    new_question = "Which floor is the new head office on, and when do we move?"
    print("\n=== 3. Ask something no document covers yet ===")
    show(answer_question(new_question, slow=False), stages=("postfilter",))

    print("=== 4. Upload a new document while running ===")
    shutil.copy(NEW_DOCS_DIR / "general_office_move_2027.md", UPLOAD_DIR)
    show(ingest_file(UPLOAD_DIR / "general_office_move_2027.md", slow=False), stages=("store",))

    print("\n=== 5. Same question again - the new file answers it ===")
    show(answer_question(new_question, slow=False), stages=("postfilter", "rerank"))


if __name__ == "__main__":
    main()
