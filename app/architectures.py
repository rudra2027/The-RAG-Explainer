"""
architectures.py - eight classic RAG architectures, each one a PRESET of the pipeline stages.

WHY presets: a "RAG architecture" is really just a choice of which building blocks
to switch on. Every block here already exists as a small module (dense.py, bm25.py,
fusion.py, expansion.py, rerank.py, reflection.py ...), so each architecture below is
only a few lines of configuration - and "Run it" executes the real pipeline.

    strategy    which search runs: dense | bm25 | hybrid | hybrid_expansion
    expansion   mqe | hyde  (only used when strategy is hybrid_expansion)
    tool_call   the LLM plans the search (clean query + metadata filters)
    postfilter  drop weak matches / duplicates after the search
    rerank      cross-encoder re-orders the survivors
    reflect     check the answer is grounded, retry once if not

Demo:  python -m app.architectures
"""
ALL_ON = {"tool_call": True, "postfilter": True, "rerank": True, "reflect": True}

ARCHITECTURES = {
    "naive": {
        "name": "Naive RAG",
        "tagline": "Search by meaning, then answer.",
        "kid": "Like asking a librarian for the 4 books that sound closest to your question, then reading them out loud.",
        "good_for": "Quick prototypes and small, clean knowledge bases.",
        "weak_at": "Exact words, numbers and codes; no safety net if the wrong pages come back.",
        "config": {"strategy": "dense", "expansion": "mqe", "tool_call": False, "postfilter": False, "rerank": False, "reflect": False},
        "example": "How much time off after my kid is born?",
    },
    "keyword": {
        "name": "Keyword RAG (BM25)",
        "tagline": "Search by exact words, then answer.",
        "kid": "Like pressing Ctrl+F: the pages that contain your exact words win - rare words count the most.",
        "good_for": "Names, codes, extension numbers, jargon.",
        "weak_at": "Synonyms: 'time off' will not find 'annual leave'.",
        "config": {"strategy": "bm25", "expansion": "mqe", "tool_call": False, "postfilter": False, "rerank": False, "reflect": False},
        "example": "Who do I call on extension 4400?",
    },
    "hybrid": {
        "name": "Hybrid RAG",
        "tagline": "Meaning AND words, merged fairly.",
        "kid": "Two friends search - one by meaning, one by exact words. Pages that BOTH friends like go to the top.",
        "good_for": "Most real-world questions: it covers each method's blind spot.",
        "weak_at": "Still one shot at the question; vague questions can miss.",
        "config": {"strategy": "hybrid", "expansion": "mqe", "tool_call": False, "postfilter": False, "rerank": False, "reflect": False},
        "example": "Can I use SMS codes for MFA?",
    },
    "advanced": {
        "name": "Advanced RAG",
        "tagline": "Hybrid search + cleaning + a careful judge.",
        "kid": "After the two friends pick pages, a helper throws away the weak ones and a strict judge re-reads the rest to rank them.",
        "good_for": "Better precision: the best pages end up first.",
        "weak_at": "Slower and costs a little more (extra judge step).",
        "config": {"strategy": "hybrid", "expansion": "mqe", "tool_call": False, "postfilter": True, "rerank": True, "reflect": False},
        "example": "What is the hotel budget in big cities?",
    },
    "mqe": {
        "name": "Multi-Query RAG (MQE)",
        "tagline": "Ask the question several ways.",
        "kid": "You are not sure how the book words things, so you ask 4 different ways: slang, formal, keywords... and combine the results.",
        "good_for": "Vague or oddly-worded questions (better recall).",
        "weak_at": "More searches = more time and cost.",
        "config": {"strategy": "hybrid_expansion", "expansion": "mqe", "tool_call": False, "postfilter": True, "rerank": True, "reflect": False},
        "example": "hey how much time off can I take after my kid is born??",
    },
    "hyde": {
        "name": "HyDE RAG",
        "tagline": "Imagine the answer, then look for it.",
        "kid": "First the AI writes a pretend answer. Real pages that look like that pretend answer are probably the right ones!",
        "good_for": "Questions phrased very differently from the documents.",
        "weak_at": "The pretend answer can contain wrong facts - it is only used for searching, never shown as the answer.",
        "config": {"strategy": "hybrid_expansion", "expansion": "hyde", "tool_call": False, "postfilter": True, "rerank": True, "reflect": False},
        "example": "Why are SMS codes not allowed for MFA?",
    },
    "agentic": {
        "name": "Agentic RAG",
        "tagline": "The AI plans the search itself.",
        "kid": "The AI is a detective: it rewrites your question, decides which department's shelf to look on, and only then searches.",
        "good_for": "Big knowledge bases with departments / types to filter on.",
        "weak_at": "If the AI picks the wrong shelf, the answer is not on it.",
        "config": {"strategy": "hybrid", "expansion": "mqe", "tool_call": True, "postfilter": True, "rerank": True, "reflect": False},
        "example": "How many days of paid leave do full-time employees get?",
    },
    "reflective": {
        "name": "Self-Reflective RAG",
        "tagline": "Answer, double-check, retry.",
        "kid": "After writing the answer, the AI marks its own homework: is every sentence backed up by the pages? If not, it tries once more.",
        "good_for": "High-trust answers where a made-up fact is costly.",
        "weak_at": "Extra LLM calls, so slower.",
        "config": {"strategy": "hybrid_expansion", "expansion": "mqe", **ALL_ON},
        "example": "Which floor is the new head office on, and when do we move?",
    },
}


def features_of(config: dict) -> dict:
    """The stage switches of a preset (anything not listed is off)."""
    return {key: config.get(key, False) for key in ALL_ON}


def stages_of(config: dict) -> list[str]:
    """The stages that will run, in order - used to draw the flow diagram."""
    s, f = config["strategy"], features_of(config)
    stages = ["query"]
    if f["tool_call"]:
        stages.append("tool_call")
    if s == "hybrid_expansion":
        stages.append("expand")
    stages.append("prefilter")
    if s != "bm25":
        stages.append("dense")
    if s != "dense":
        stages.append("bm25")
    if s in ("hybrid", "hybrid_expansion"):
        stages.append("fuse")
    if f["postfilter"]:
        stages.append("postfilter")
    if f["rerank"]:
        stages.append("rerank")
    stages += ["prompt", "answer"]
    if f["reflect"]:
        stages.append("reflect")
    return stages


def public_view() -> list[dict]:
    """What the browser needs: every preset plus its computed list of stages."""
    return [{"id": key, **{k: v for k, v in arch.items() if k != "config"}, "config": arch["config"],
             "stages": stages_of(arch["config"])} for key, arch in ARCHITECTURES.items()]


if __name__ == "__main__":
    for key, arch in ARCHITECTURES.items():
        print(f"{arch['name']:<24} {' > '.join(stages_of(arch['config']))}")
