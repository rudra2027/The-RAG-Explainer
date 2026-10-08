"""
ragas_eval.py - RAGAS: score the RAG pipeline with four classic metrics.

  faithfulness       Are the answer's claims supported by the retrieved chunks?   (generation quality)
  answer_relevancy   Does the answer actually address the question?              (generation quality)
  context_precision  Are the useful chunks ranked at the top?                    (retrieval quality)
  context_recall     Did retrieval find everything the reference answer needs?   (retrieval quality)

WHY split like this: when an answer is bad, these tell you WHERE to look.
Low recall -> fix chunking/search. Good recall but low faithfulness -> fix the prompt/LLM.

The judge is the cheap OpenAI model (FAST_LLM_MODEL via OpenRouter), plugged in
through a tiny adapter (OpenRouterRagasLLM): RAGAS hands us a prompt + a Pydantic
class, and we return a validated instance.
Embeddings for answer_relevancy use the same local MiniLM model as retrieval.

Demo:  python -m app.evals.ragas_eval        (needs OPENROUTER_API_KEY + ingested docs)
"""
import json
import time

from ragas.embeddings.huggingface_provider import HuggingFaceEmbeddings
from ragas.llms.base import InstructorBaseRagasLLM
from ragas.metrics.collections import AnswerRelevancy, ContextPrecision, ContextRecall, Faithfulness

from app.config import EMBEDDING_MODEL, EVAL_SET_PATH
from app.evals.deepeval_eval import summarise
from app.generation.llm import structured
from app.pipeline import run_question
from app.schemas import EvalScore, StageEvent

JUDGE_SYSTEM = "You are an evaluation judge. Follow the instructions in the prompt exactly."


class OpenRouterRagasLLM(InstructorBaseRagasLLM):
    """Adapter so RAGAS can use our OpenRouter model (via the structured-output helper) as its judge."""

    def generate(self, prompt, response_model):
        return structured(JUDGE_SYSTEM, prompt, response_model)

    async def agenerate(self, prompt, response_model):
        return self.generate(prompt, response_model)


def build_metrics() -> dict:
    llm = OpenRouterRagasLLM()
    embeddings = HuggingFaceEmbeddings(model=EMBEDDING_MODEL)
    return {
        "faithfulness": Faithfulness(llm=llm),
        "answer_relevancy": AnswerRelevancy(llm=llm, embeddings=embeddings),
        "context_precision": ContextPrecision(llm=llm),
        "context_recall": ContextRecall(llm=llm),
    }


def score_one(metrics: dict, question: str, answer: str, contexts: list[str], reference: str) -> list[EvalScore]:
    # Each metric needs slightly different inputs - that difference IS the lesson:
    # generation metrics look at the answer, retrieval metrics look at contexts vs. reference.
    inputs = {
        "faithfulness": dict(user_input=question, response=answer, retrieved_contexts=contexts),
        "answer_relevancy": dict(user_input=question, response=answer),
        "context_precision": dict(user_input=question, reference=reference, retrieved_contexts=contexts),
        "context_recall": dict(user_input=question, retrieved_contexts=contexts, reference=reference),
    }
    scores = []
    for name, metric in metrics.items():
        result = metric.score(**inputs[name])
        scores.append(EvalScore(framework="ragas", question=question, metric=name,
                                score=float(result.value), reason=result.reason))
    return scores


def run_ragas_events(strategy: str = "hybrid", expansion: str = "mqe"):
    """Generator of StageEvents (for one search strategy) so the UI can show each question as it is scored."""
    eval_set = json.loads(EVAL_SET_PATH.read_text(encoding="utf-8"))
    metrics = build_metrics()
    all_scores: list[EvalScore] = []

    for i, item in enumerate(eval_set, start=1):
        yield StageEvent(stage="eval", status="running", message=f"[{i}/{len(eval_set)}] {item['question']}")
        start = time.perf_counter()
        result = run_question(item["question"], strategy, expansion)  # full pipeline with the chosen search strategy
        scores = score_one(metrics, item["question"], result["answer"], result["contexts"], item["reference"])
        all_scores += scores
        yield StageEvent(stage="eval", status="done", ms=round((time.perf_counter() - start) * 1000),
                         data={"question": item["question"], "answer": result["answer"],
                               "scores": [s.model_dump() for s in scores]})

    yield StageEvent(stage="eval_summary", status="done", data=summarise(all_scores))


if __name__ == "__main__":
    for event in run_ragas_events():
        if event.stage == "eval" and event.status == "done":
            for s in event.data["scores"]:
                print(f"{s['score']:.2f}  {s['metric']:<18} {s['question']}")
        elif event.stage == "eval_summary":
            print("averages:", event.data["averages"])
