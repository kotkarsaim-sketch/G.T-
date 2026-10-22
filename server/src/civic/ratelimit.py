"""In-memory token-bucket rate limiting (api-spec §4).

State is per API instance; multi-instance deployments terminate limits at the
reverse proxy or move this to Redis. Kept dependency-free by design.
"""

import time

LIMITS: dict[str, tuple[int, int]] = {
    # route -> (requests per minute, burst)
    "/v1/chat": (20, 40),
    "/v1/search": (60, 120),
}


class TokenBucket:
    __slots__ = ("rate", "capacity", "tokens", "updated")

    def __init__(self, per_minute: int, burst: int, now: float | None = None) -> None:
        self.rate = per_minute / 60.0
        self.capacity = float(burst)
        self.tokens = float(burst)
        self.updated = time.monotonic() if now is None else now

    def take(self, now: float | None = None) -> bool:
        now = time.monotonic() if now is None else now
        self.tokens = min(self.capacity, self.tokens + (now - self.updated) * self.rate)
        self.updated = now
        if self.tokens >= 1.0:
            self.tokens -= 1.0
            return True
        return False

    def retry_after(self) -> int:
        return max(1, int((1.0 - self.tokens) / self.rate) + 1)

    def remaining(self) -> int:
        return int(self.tokens)


class RateLimiter:
    def __init__(self, stale_after_s: float = 600.0) -> None:
        self._buckets: dict[tuple[str, str], TokenBucket] = {}
        self._seen: dict[tuple[str, str], float] = {}
        self._stale = stale_after_s

    def check(self, client: str, route: str, per_minute: int, burst: int) -> tuple[bool, int, int]:
        """Returns (allowed, retry_after_seconds, remaining)."""
        now = time.monotonic()
        self._prune(now)
        key = (client, route)
        bucket = self._buckets.get(key)
        if bucket is None:
            bucket = TokenBucket(per_minute, burst, now=now)
            self._buckets[key] = bucket
        self._seen[key] = now
        allowed = bucket.take(now)
        return allowed, (bucket.retry_after() if not allowed else 0), bucket.remaining()

    def _prune(self, now: float) -> None:
        stale = [k for k, t in self._seen.items() if now - t >= self._stale]
        for k in stale:
            self._buckets.pop(k, None)
            self._seen.pop(k, None)
