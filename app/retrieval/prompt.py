"""
prompt.py - PROMPT RENDERING: put the retrieved context and the question into one prompt.

WHY show it: this rendered text is *exactly* what the LLM sees. Most RAG
"mysteries" (wrong answer, made-up facts) become obvious once you read it.

The chunks are numbered [1], [2], ... so the answer can cite its sources and
the reflection step can check each claim against them.

Demo:  python -m app.retrieval.prompt
"""
from langchain_core.prompts import PromptTemplate

from app.schemas import RetrievalResult

SYSTEM_PROMPT = (
    "You answer questions for employees using ONLY the numbered context passages. "
    "Cite passages like [1] or [2] after each fact. "
    "If the context does not contain the answer, say you don't know - do not guess."
)

RAG_TEMPLATE = PromptTemplate.from_template(
    "Context passages:\n"
    "{context}\n\n"
    "Question: {question}\n\n"
    "Answer in 2-4 sentences with citations."
)


def format_context(results: list[RetrievalResult]) -> str:
    return "\n\n".join(
        f"[{i}] (source: {r.chunk.source})\n{r.chunk.text}" for i, r in enumerate(results, start=1)
    )


def render_prompt(question: str, results: list[RetrievalResult]) -> str:
    return RAG_TEMPLATE.format(context=format_context(results), question=question)


if __name__ == "__main__":
    from app.schemas import Chunk

    chunk = Chunk(id="1", text="Employees receive 24 days of paid leave.", source="hr_leave_policy.md",
                  doc_type="md", department="hr", chunk_index=0, char_count=40, strategy="recursive")
    print(SYSTEM_PROMPT, "\n---")
    print(render_prompt("How much leave do I get?", [RetrievalResult(chunk=chunk, dense_score=0.7)]))
