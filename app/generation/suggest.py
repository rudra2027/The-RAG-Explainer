"""
suggest.py - propose a question the uploaded files can actually answer.

WHY: the example questions in the UI fit the sample company documents. When a
student uploads something else (a science paper, a recipe book...) they need a
question that makes sense for THAT file. We show the cheap LLM a few random
chunks and ask for one question whose answer is in them.

Demo:  python -m app.generation.suggest        (needs OPENROUTER_API_KEY + ingested docs)
"""
import random

from app.config import FAST_LLM_MODEL, LLM_ENABLED
from app.generation.llm import structured
from app.ingestion import corpus
from app.schemas import SuggestedQuestion


def suggest_question() -> str:
    chunks = corpus.all_chunks()
    if not chunks:
        return ""
    sample = random.sample(chunks, min(3, len(chunks)))
    if not LLM_ENABLED:   # offline: turn the opening words of a chunk into a question
        return f"What does the text say about: {' '.join(sample[0].text.split()[:8])}...?"
    context = "\n\n".join(c.text for c in sample)
    result = structured(
        "Write ONE specific question that can be answered using only the passages below. "
        "Make it sound like a real person asking, not like an exam. Do not mention 'the passage'.",
        context, SuggestedQuestion, model=FAST_LLM_MODEL)
    return result.question.strip()


if __name__ == "__main__":
    print(suggest_question())
