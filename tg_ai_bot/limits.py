"""In-memory sliding-window rate limiter (single instance)."""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from .config import WINDOW_SECONDS


@dataclass(frozen=True)
class LimitResult:
    allowed: bool
    retry_seconds: int  # > 0 only when not allowed


class RateLimiter:
    """Sliding-window limiter keyed by user id. Admins bypass at the handler level."""

    def __init__(self, max_per_window: int, window_seconds: int = WINDOW_SECONDS) -> None:
        self._max = max_per_window
        self._window = window_seconds
        self._hits: dict[int, deque[float]] = {}

    def check(self, user_id: int, now: float) -> LimitResult:
        dq = self._hits.setdefault(user_id, deque())
        cutoff = now - self._window
        while dq and dq[0] <= cutoff:
            dq.popleft()
        if len(dq) >= self._max:
            retry = int(self._window - (now - dq[0])) + 1
            return LimitResult(allowed=False, retry_seconds=max(retry, 1))
        dq.append(now)
        return LimitResult(allowed=True, retry_seconds=0)
