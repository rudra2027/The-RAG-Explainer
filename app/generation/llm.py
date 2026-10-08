"""
llm.py - the one place that talks to the LLM: OpenAI models through OpenRouter.

WHY OpenRouter: one API key reaches many providers through the standard
OpenAI-compatible API, so we use the official `openai` Python SDK and only
change `base_url`. Model names look like "openai/gpt-5.6-sol".

WHY two models (see config.py):
  LLM_MODEL       writes the final answer - quality matters most there.
  FAST_LLM_MODEL  ~20x cheaper, for the many small jobs (tool call, MQE, HyDE,
                  reflection, eval judging). A common cost pattern in production.

Demo:  python -m app.generation.llm        (needs OPENROUTER_API_KEY)
"""
import json
from functools import lru_cache
from typing import Optional, TypeVar

import openai
from pydantic import BaseModel, ValidationError

from app.config import FAST_LLM_MODEL, LLM_MODEL, OPENROUTER_API_KEY, OPENROUTER_BASE_URL
from app.evals.tracing import traceable

T = TypeVar("T", bound=BaseModel)


@lru_cache(maxsize=1)
def get_client() -> openai.OpenAI:
    return openai.OpenAI(
        base_url=OPENROUTER_BASE_URL,
        api_key=OPENROUTER_API_KEY,
        default_headers={"X-Title": "RAG Learning Visualiser"},  # shows up in your OpenRouter dashboard
    )


# run_type="llm" makes LangSmith show these as LLM calls (inputs, outputs, latency).
@traceable(name="llm_chat", run_type="llm")
def chat(system: str, messages: list[dict], tools: Optional[list[dict]] = None,
         tool_choice: Optional[dict] = None, model: str = LLM_MODEL):
    """One chat request. Returns the assistant message (it may contain tool_calls)."""
    extra = {}
    if tools:
        extra["tools"] = tools
    if tool_choice:
        extra["tool_choice"] = tool_choice
    response = get_client().chat.completions.create(
        model=model,
        messages=[{"role": "system", "content": system}, *messages],
        **extra,
    )
    return response.choices[0].message


@traceable(name="llm_structured", run_type="llm")
def structured(system: str, prompt: str, schema: type[T], model: str = FAST_LLM_MODEL) -> T:
    """Ask for JSON that matches a Pydantic class and get a validated object back.
    Used by MQE, HyDE, reflection and the RAGAS / DeepEval judges."""
    messages = [{"role": "system", "content": system}, {"role": "user", "content": prompt}]
    try:
        # Preferred path: the API enforces the JSON schema generated from the Pydantic class.
        completion = get_client().chat.completions.parse(model=model, messages=messages, response_format=schema)
        parsed = completion.choices[0].message.parsed
        if parsed is not None:
            return parsed
    except (openai.BadRequestError, ValueError, TypeError, ValidationError):
        # Some schemas (e.g. from eval libraries) can't be expressed in "strict" mode.
        pass

    # Fallback: plain JSON mode + the schema in the prompt, validated by Pydantic ourselves.
    schema_hint = json.dumps(schema.model_json_schema())
    messages[0]["content"] += f"\n\nRespond with ONLY a JSON object matching this JSON schema:\n{schema_hint}"
    completion = get_client().chat.completions.create(
        model=model, messages=messages, response_format={"type": "json_object"},
    )
    return schema.model_validate_json(completion.choices[0].message.content)


if __name__ == "__main__":
    print(chat("You are concise.", [{"role": "user", "content": "In one sentence: what is RAG?"}],
               model=FAST_LLM_MODEL).content)
