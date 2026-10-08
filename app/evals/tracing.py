"""
tracing.py - LangSmith traces of every run.

WHY: the live UI shows one run at a time; LangSmith keeps a searchable history
of every run - inputs, outputs, latency and each nested step - so you can compare
yesterday's answer with today's after you change the chunk size.

How it switches on: set LANGSMITH_TRACING=true and LANGSMITH_API_KEY in .env.
Without them, `@traceable` is a no-op and nothing leaves your machine.

    @traceable(name="rerank")             -> one span in the trace tree per call
    @traceable(run_type="llm")            -> shown as an LLM call (used in generation/llm.py)

Demo:  python -m app.evals.tracing
"""
import os

from langsmith import traceable  # re-exported so other modules import it from here

__all__ = ["traceable", "tracing_enabled", "tracing_status"]


def tracing_enabled() -> bool:
    flag = os.getenv("LANGSMITH_TRACING", "").lower() == "true"
    return flag and bool(os.getenv("LANGSMITH_API_KEY"))


def tracing_status() -> dict:
    return {
        "enabled": tracing_enabled(),
        "project": os.getenv("LANGSMITH_PROJECT", "default"),
    }


if __name__ == "__main__":
    @traceable(name="demo_step")
    def add(a: int, b: int) -> int:
        return a + b

    print("tracing:", tracing_status(), "| add(2, 3) =", add(2, 3))
