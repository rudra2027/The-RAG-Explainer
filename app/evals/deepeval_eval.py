"""
deepeval_eval.py - DeepEval: RAG evaluation written like unit tests.

WHY DeepEval next to RAGAS: RAGAS gives scores; DeepEval wraps the same ideas in
*test cases* with a threshold, so each metric is a clear PASS / FAIL - the
way you would guard a RAG app in CI ("faithfulness must stay above 0.7").

Each LLMTestCase holds:  input (question), actual_output (our answer),
expected_output (reference answer), retrieval_context (the chunks we used).

The judge is the cheap OpenAI model (FAST_LLM_MODEL via OpenRouter), plugged in
through DeepEval's DeepEvalBaseLLM interface.

Demo:  python -m app.evals.deepeval_eval     (needs OPENROUTER_API_KEY + ingested docs)
"""
import json
import time

from deepeval.metrics import (AnswerRelevancyMetric, ContextualPrecisionMetric,
                              ContextualRecallMetric, FaithfulnessMetric)
from deepeval.models import DeepEvalBaseLLM
from deepeval.test_case import LLMTestCase

from app.config import EVAL_SET_PATH, FAST_LLM_MODEL
from app.generation.llm import chat, structured
from app.pipeline import run_question
from app.schemas import EvalScore, StageEvent

THRESHOLD = 0.7  # a metric below this counts as FAIL
JUDGE_SYSTEM = "You are an evaluation judge. Follow the instructions in the prompt exactly."


class OpenRouterJudge(DeepEvalBaseLLM):
    """Adapter so DeepEval can use our OpenRouter model as its judge."""

    def __init__(self):
        self.model_name = FAST_LLM_MODEL

    def load_model(self):
        return self

    def generate(self, prompt: str, schema=None):
        # DeepEval passes a Pydantic `schema` when it needs structured JSON back.
        if schema is not None:
            return structured(JUDGE_SYSTEM, prompt, schema, model=self.model_name)
        return chat(JUDGE_SYSTEM, [{"role": "user", "content": prompt}], model=self.model_name).content

    async def a_generate(self, prompt: str, schema=None):
        return self.generate(prompt, schema)

    def get_model_name(self) -> str:
        return self.model_name


def build_metrics(judge: OpenRouterJudge) -> list:
    common = {"threshold": THRESHOLD, "model": judge, "include_reason": True, "async_mode": False}
    return [FaithfulnessMetric(**common), AnswerRelevancyMetric(**common),
            ContextualPrecisionMetric(**common), ContextualRecallMetric(**common)]


def run_deepeval_events(strategy: str = "hybrid", expansion: str = "mqe"):
    """Generator of StageEvents (for one search strategy) so the UI can show each test case as it finishes."""
    eval_set = json.loads(EVAL_SET_PATH.read_text(encoding="utf-8"))
    judge = OpenRouterJudge()
    all_scores: list[EvalScore] = []

    for i, item in enumerate(eval_set, start=1):
        yield StageEvent(stage="eval", status="running", message=f"[{i}/{len(eval_set)}] {item['question']}")
        start = time.perf_counter()
        result = run_question(item["question"], strategy, expansion)  # full pipeline with the chosen search strategy
        test_case = LLMTestCase(
            input=item["question"],
            actual_output=result["answer"],
            expected_output=item["reference"],
            retrieval_context=result["contexts"],
        )
        scores = []
        for metric in build_metrics(judge):
            metric.measure(test_case)
            scores.append(EvalScore(framework="deepeval", question=item["question"],
                                    metric=metric.__class__.__name__.replace("Metric", ""),
                                    score=float(metric.score), threshold=THRESHOLD,
                                    passed=metric.is_successful(), reason=metric.reason))
        all_scores += scores
        yield StageEvent(stage="eval", status="done", ms=round((time.perf_counter() - start) * 1000),
                         data={"question": item["question"], "answer": result["answer"],
                               "scores": [s.model_dump() for s in scores]})

    yield StageEvent(stage="eval_summary", status="done", data=summarise(all_scores))


def summarise(scores: list[EvalScore]) -> dict:
    metrics = sorted({s.metric for s in scores})
    averages = {m: sum(s.score for s in scores if s.metric == m) / sum(1 for s in scores if s.metric == m)
                for m in metrics}
    passed = [s.passed for s in scores if s.passed is not None]
    return {"averages": averages, "pass_rate": (sum(passed) / len(passed)) if passed else None}


if __name__ == "__main__":
    for event in run_deepeval_events():
        if event.stage == "eval" and event.status == "done":
            for s in event.data["scores"]:
                print(f"{'PASS' if s['passed'] else 'FAIL'}  {s['score']:.2f}  {s['metric']:<20} {s['question']}")
        elif event.stage == "eval_summary":
            print("summary:", event.data)
