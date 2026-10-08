"""
reflection.py - REFLECTION: after answering, check the answer is grounded.

WHY: an LLM can write a confident sentence that is not in the context at all
(a "hallucination"). So we ask the LLM a second, narrower question:
"Is every claim in this answer supported by these passages?"

If the verdict is NOT grounded, the pipeline retries ONCE: it searches again
with the rewritten query the checker suggests, and answers again. One retry
only - unlimited retries would hide a knowledge-base gap behind latency.

Demo:  python -m app.generation.reflection   (needs OPENROUTER_API_KEY)
"""
from app.config import LLM_ENABLED
from app.generation.llm import structured
from app.retrieval.prompt import format_context
from app.schemas import GroundingCheck, RetrievalResult

CHECKER_SYSTEM = (
    "You are a strict fact checker. Compare the ANSWER with the CONTEXT passages. "
    "grounded=true only if every factual claim in the answer is supported by the context. "
    "An answer that honestly says the context does not contain the information counts as grounded. "
    "If not grounded, list the unsupported claims and write a better search query "
    "(rewritten_query) that could find the missing information."
)


def check_grounding(question: str, answer: str, results: list[RetrievalResult]) -> GroundingCheck:
    if not LLM_ENABLED:
        return GroundingCheck(grounded=True, reason="Offline mode: reflection skipped.",
                              unsupported_claims=[], rewritten_query=question)

    prompt = (
        f"QUESTION:\n{question}\n\n"
        f"CONTEXT:\n{format_context(results)}\n\n"
        f"ANSWER:\n{answer}"
    )
    return structured(CHECKER_SYSTEM, prompt, GroundingCheck)  # cheap FAST model is enough


if __name__ == "__main__":
    from app.schemas import Chunk

    chunk = Chunk(id="1", text="Employees receive 24 days of paid annual leave.", source="hr.md",
                  doc_type="md", department="hr", chunk_index=0, char_count=46, strategy="recursive")
    results = [RetrievalResult(chunk=chunk, dense_score=0.7)]
    # The second sentence is invented on purpose - the checker should catch it.
    print(check_grounding("How much leave?", "You get 24 days [1]. Managers get 40 days.", results))
