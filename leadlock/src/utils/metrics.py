"""
Metrics utilities — helpers for calculating dashboard KPIs.
"""
import time
from datetime import datetime
from typing import Optional


class Timer:
    """Simple timer for measuring operation latency."""

    def __init__(self):
        self._start: Optional[float] = None
        self._end: Optional[float] = None

    def start(self) -> "Timer":
        self._start = time.monotonic()
        return self

    def stop(self) -> int:
        """Stop timer and return elapsed milliseconds."""
        self._end = time.monotonic()
        return self.elapsed_ms

    @property
    def elapsed_ms(self) -> int:
        """Return elapsed time in milliseconds."""
        if self._start is None:
            return 0
        end = self._end or time.monotonic()
        return int((end - self._start) * 1000)


def response_time_bucket(ms: int) -> str:
    """Categorize response time into display buckets."""
    if ms < 10000:
        return "0-10s"
    elif ms < 30000:
        return "10-30s"
    elif ms < 60000:
        return "30-60s"
    else:
        return "60s+"
