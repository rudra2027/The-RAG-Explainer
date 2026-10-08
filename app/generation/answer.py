"""
answer.py - GENERATE the answer from the rendered prompt.

The LLM gets the system prompt (rules: use only the context, cite [n]) and
the rendered prompt (context + question) from retrieval/prompt.py.

Offline mode (no API key) returns the best re-ranked chunk instead, so the
whole pipeline can still be demonstrated in class without an LLM.

Demo:  python -m app.generation.answer      (needs OPENROUTER_API_KEY)
"""
from app.config import LLM_ENABLED
from app.generation.llm import chat
from app.retrieval.prompt import SYSTEM_PROMPT
from app.schemas import RetrievalResult


def generate_answer(rendered_prompt: str, results: list[RetrievalResult]) -> str:
    if not results:
        return "I don't know - no relevant passages were found in the knowledge base."

    if not LLM_ENABLED:
        best = results[0].chunk
        return f"[offline mode - top passage shown instead of an LLM answer]\n{best.text} [1]"

    message = chat(SYSTEM_PROMPT, [{"role": "user", "content": rendered_prompt}])  # LLM_MODEL: quality matters here
    return (message.content or "").strip()


if __name__ == "__main__":
    from app.retrieval.prompt import render_prompt
    from app.schemas import Chunk

    chunk = Chunk(id="1", text="Employees receive 24 days of paid annual leave.", source="hr.md",
                  doc_type="md", department="hr", chunk_index=0, char_count=46, strategy="recursive")
    results = [RetrievalResult(chunk=chunk, dense_score=0.7)]
    print(generate_answer(render_prompt("How much leave do I get?", results), results))
