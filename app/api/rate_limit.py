"""Per-API-key rate limiting (in-memory sliding window; single-process deployments only)."""
import hashlib
import threading
import time
from collections import defaultdict, deque

from fastapi import Header, HTTPException, status

import config
from app.api.auth import API_KEY_HEADER

_WINDOW_S = 60.0


class RateLimiter:
    """Allows `limit` calls per key within any 60-second window."""

    def __init__(self, limit: int):
        self.limit = limit
        self._calls: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str) -> float | None:
        """Record a call; returns seconds to wait if the key is over its limit, else None."""
        # Keys are stored hashed so raw API keys are never kept in memory structures.
        bucket_id = hashlib.sha256(key.encode()).hexdigest()
        now = time.monotonic()
        with self._lock:
            calls = self._calls[bucket_id]
            while calls and now - calls[0] >= _WINDOW_S:  # forget calls older than the window
                calls.popleft()
            if len(calls) >= self.limit:
                return _WINDOW_S - (now - calls[0])
            calls.append(now)
        return None

    def reset(self) -> None:
        with self._lock:
            self._calls.clear()


limiter = RateLimiter(config.RATE_LIMIT_PER_MINUTE)


def enforce_rate_limit(x_api_key: str | None = Header(default=None, alias=API_KEY_HEADER)) -> None:
    """FastAPI dependency: 429 with Retry-After when the caller's key exceeds its limit."""
    wait = limiter.check(x_api_key or "")
    if wait is not None:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Rate limit exceeded",
                            headers={"Retry-After": str(int(wait) + 1)})
