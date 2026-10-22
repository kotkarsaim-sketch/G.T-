"""Unit tests for the token-bucket rate limiter."""

import time

from civic.ratelimit import RateLimiter, TokenBucket


def test_bucket_allows_burst_then_blocks():
    t0 = time.monotonic()
    b = TokenBucket(per_minute=60, burst=3, now=t0)
    assert [b.take(t0) for _ in range(3)] == [True, True, True]
    assert b.take(t0) is False


def test_bucket_refills_over_time():
    t0 = time.monotonic()
    b = TokenBucket(per_minute=60, burst=1, now=t0)  # 1 token per second
    assert b.take(t0) is True
    assert b.take(t0 + 0.5) is False
    assert b.take(t0 + 1.1) is True


def test_retry_after_is_positive_seconds():
    t0 = time.monotonic()
    b = TokenBucket(per_minute=6, burst=1, now=t0)  # 0.1 tokens per second
    b.take(t0)
    assert b.take(t0) is False
    assert b.retry_after() >= 1


def test_limiter_isolates_clients_and_routes():
    rl = RateLimiter()
    ok1, _, _ = rl.check("ip1", "/v1/chat", per_minute=1, burst=1)
    ok2, _, _ = rl.check("ip1", "/v1/search", per_minute=1, burst=1)
    ok3, retry, _ = rl.check("ip1", "/v1/chat", per_minute=1, burst=1)
    ok4, _, _ = rl.check("ip2", "/v1/chat", per_minute=1, burst=1)
    assert ok1 and ok2 and ok4
    assert not ok3 and retry >= 1


def test_prune_drops_stale_buckets():
    rl = RateLimiter(stale_after_s=0.0)
    a1, _, _ = rl.check("ip1", "/v1/chat", per_minute=1, burst=1)
    a2, _, _ = rl.check("ip1", "/v1/chat", per_minute=1, burst=1)
    assert a1 and a2  # stale entry pruned between checks, fresh burst granted
