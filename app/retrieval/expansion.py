"""
expansion.py - QUERY EXPANSION: give the search more than one shot at the question.

  MQE (Multi-Query Expansion)
      The LLM rewrites the question several ways ("time off after having a baby",
      "parental leave weeks", ...). Each version is searched (dense + BM25) and
      all the lists are fused with RRF. Different words reach different chunks,
      so recall goes up - at the cost of more searches.

  HyDE (Hypothetical Document Embeddings)
      Questions and answers are phrased differently ("How many days...?" vs
      "Employees receive 24 days..."). HyDE asks the LLM to WRITE a plausible
      answer passage first, then searches with the embedding of that passage -
      answer-shaped text lands closer to answer-shaped chunks. The passage may
      contain wrong facts: that's fine, it is only used to search, never shown
      as the answer.

Both use the cheap FAST_LLM_MODEL - expansion is a small writing task.

Demo:  python -m app.retrieval.expansion     (needs OPENROUTER_API_KEY)
"""
from app.config import FAST_LLM_MODEL, LLM_ENABLED, MQE_VARIANTS
from app.generation.llm import structured
from app.schemas import HypotheticalDoc, MultiQuery


def multi_query(question: str, n: int = MQE_VARIANTS) -> list[str]:
    if not LLM_ENABLED:
        return []
    result = structured(
        "You help a search engine. Rewrite the user's question in different ways: use synonyms, "
        "the formal policy wording a company document would use, and a short keyword version. "
        f"Return exactly {n} queries.",
        question, MultiQuery, model=FAST_LLM_MODEL,
    )
    return [q for q in result.queries if q.strip()][:n]


def hypothetical_document(question: str) -> str:
    if not LLM_ENABLED:
        return question
    result = structured(
        "Write a short passage (2-3 sentences) that could appear in an internal company policy "
        "document and answers the question. Write it as a confident policy statement. "
        "Invent plausible details if you must - it is only used for searching.",
        question, HypotheticalDoc, model=FAST_LLM_MODEL,
    )
    return result.passage


if __name__ == "__main__":
    q = "how much time off can I take after my kid is born?"
    print("MQE :", multi_query(q))
    print("HyDE:", hypothetical_document(q))
