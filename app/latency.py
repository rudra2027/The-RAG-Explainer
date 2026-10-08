"""
latency.py - minimal latency monitoring.

WHY: in RAG the slow part is rarely where people guess. Timing every stage
and drawing one bar per step in the UI makes that obvious (spoiler: it is
usually the LLM call, then embedding).

Usage:
    timer = StageTimer()
    with timer.measure("search"):
        ...do the search...
    timer.last_ms        # how long that block took
    timer.totals         # {"search": 12.3, ...} for the latency bar chart
"""
import time
from contextlib import contextmanager


class StageTimer:
    def __init__(self) -> None:
        self.totals: dict[str, float] = {}  # stage name -> milliseconds (summed if repeated)
        self.last_ms: float = 0.0

    @contextmanager
    def measure(self, stage: str):
        start = time.perf_counter()
        try:
            yield
        finally:
            self.last_ms = round((time.perf_counter() - start) * 1000, 1)
            # A retry runs some stages twice; summing keeps the bar chart honest.
            self.totals[stage] = round(self.totals.get(stage, 0.0) + self.last_ms, 1)


if __name__ == "__main__":
    # Demo: python -m app.latency
    timer = StageTimer()
    with timer.measure("sleep_a_bit"):
        time.sleep(0.2)
    print(f"took {timer.last_ms} ms, totals = {timer.totals}")
