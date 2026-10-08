"""
tools.py - TOOL CALLING: the LLM decides how to search.

WHY: users ask messy questions ("hey, how much time off can I take after my
kid is born??"). Instead of searching with that text as-is, we give the LLM a
`search_knowledge_base` tool. The LLM replies with a *tool call*: a clean
query plus optional metadata filters (department, doc_type). Our code then
runs the real retrieval with those arguments.

The tool's parameter schema is generated from the Pydantic class ToolArgs, and
the LLM's arguments are validated back into ToolArgs - one class, both directions.

Demo:  python -m app.generation.tools        (needs OPENROUTER_API_KEY)
"""
import json

from app.config import FAST_LLM_MODEL, LLM_ENABLED
from app.generation.llm import chat
from app.schemas import ToolArgs

# OpenAI "function" tool format (OpenRouter passes it straight to the model).
SEARCH_TOOL = {
    "type": "function",
    "function": {
        "name": "search_knowledge_base",
        "description": (
            "Search the company knowledge base (HR, IT, finance, product and general documents). "
            "Use a department filter only when the question clearly belongs to one department."
        ),
        "parameters": ToolArgs.model_json_schema(),  # Pydantic -> JSON schema for the LLM
    },
}

PLANNER_SYSTEM = (
    "You plan searches for a retrieval system. Call search_knowledge_base exactly once "
    "with a short, keyword-rich query. Do not answer the question yourself."
)


def plan_search(question: str) -> tuple[ToolArgs, dict]:
    """Return validated ToolArgs and a small dict describing what happened (for the UI)."""
    if not LLM_ENABLED:
        return ToolArgs(query=question), {"mode": "offline", "note": "No API key - using the question as the query."}

    message = chat(
        PLANNER_SYSTEM,
        [{"role": "user", "content": question}],
        tools=[SEARCH_TOOL],
        # Force this exact tool: we always want a search plan, never a direct answer.
        tool_choice={"type": "function", "function": {"name": "search_knowledge_base"}},
        model=FAST_LLM_MODEL,  # routing is easy; use the cheap model
    )
    for call in message.tool_calls or []:
        if call.function.name == "search_knowledge_base":
            raw = json.loads(call.function.arguments)   # the LLM sends arguments as a JSON string
            args = ToolArgs.model_validate(raw)         # rejects anything outside the schema
            return args, {"mode": "llm", "tool": call.function.name, "raw_input": raw}

    return ToolArgs(query=question), {"mode": "llm", "note": "Model did not call the tool; using the question."}


if __name__ == "__main__":
    args, info = plan_search("hey how much time off can I take after my kid is born??")
    print(info)
    print(args.model_dump())
