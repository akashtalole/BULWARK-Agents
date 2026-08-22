"""HTTP-caller auth: API key + per-key rate limiting for the Agent Gateway
ingress. Distinct from platform/identity.py, which governs what each
*agent* (not each HTTP caller) may touch internally."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass

from bulwark.config import settings


class AuthenticationError(Exception):
    pass


class RateLimitExceeded(Exception):
    pass


def authenticate(api_key: str | None) -> str:
    if not api_key or api_key not in settings.api_keys:
        raise AuthenticationError("missing or unrecognized API key")
    return api_key


@dataclass
class _Bucket:
    count: int
    window_started_at: float


class RateLimiter:
    def __init__(self, max_requests: int | None = None, window_seconds: int | None = None) -> None:
        self.max_requests = max_requests or settings.rate_limit_requests
        self.window_seconds = window_seconds or settings.rate_limit_window_seconds
        self._buckets: dict[str, _Bucket] = {}
        self._lock = threading.Lock()

    def check(self, key: str) -> None:
        now = time.monotonic()
        with self._lock:
            bucket = self._buckets.get(key)
            if bucket is None or (now - bucket.window_started_at) >= self.window_seconds:
                self._buckets[key] = _Bucket(count=1, window_started_at=now)
                return
            if bucket.count >= self.max_requests:
                raise RateLimitExceeded(
                    f"rate limit exceeded: {self.max_requests} requests / {self.window_seconds}s"
                )
            bucket.count += 1

    def reset(self) -> None:
        with self._lock:
            self._buckets.clear()


rate_limiter = RateLimiter()
