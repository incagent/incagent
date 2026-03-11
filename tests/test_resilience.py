"""Tests for self-healing resilience infrastructure."""

import asyncio

import pytest

from incagent.resilience import CircuitBreaker, CircuitState, FallbackChain, RetryWithBackoff


def test_circuit_breaker_normal():
    cb = CircuitBreaker(threshold=3)
    assert cb.state == CircuitState.CLOSED
    assert cb.can_proceed()
    cb.record_success()
    assert cb.state == CircuitState.CLOSED


def test_circuit_breaker_opens():
    cb = CircuitBreaker(threshold=3)
    cb.record_failure()
    cb.record_failure()
    assert cb.state == CircuitState.CLOSED
    cb.record_failure()
    assert cb.state == CircuitState.OPEN
    assert not cb.can_proceed()


def test_circuit_breaker_resets():
    cb = CircuitBreaker(threshold=2, reset_seconds=0.1)
    cb.record_failure()
    cb.record_failure()
    assert cb.state == CircuitState.OPEN

    import time
    time.sleep(0.15)

    assert cb.can_proceed()
    assert cb.state == CircuitState.HALF_OPEN


def test_circuit_breaker_recovers():
    cb = CircuitBreaker(threshold=2, reset_seconds=0.1)
    cb.record_failure()
    cb.record_failure()

    import time
    time.sleep(0.15)

    cb.can_proceed()
    cb.record_success()
    assert cb.state == CircuitState.CLOSED


@pytest.mark.asyncio
async def test_retry_success():
    call_count = 0

    async def flaky_func():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise ValueError("Not yet")
        return "success"

    retry = RetryWithBackoff(max_retries=5, base=1.1, max_delay=0.5)
    result = await retry.execute(flaky_func)
    assert result == "success"
    assert call_count == 3


@pytest.mark.asyncio
async def test_retry_exhausted():
    async def always_fail():
        raise ValueError("Always fails")

    retry = RetryWithBackoff(max_retries=2, base=1.1, max_delay=0.1)
    with pytest.raises(ValueError, match="Always fails"):
        await retry.execute(always_fail)


@pytest.mark.asyncio
async def test_fallback_chain():
    async def primary():
        raise RuntimeError("Primary down")

    async def secondary():
        return "fallback_result"

    chain = FallbackChain()
    chain.add("primary", primary)
    chain.add("secondary", secondary)

    result = await chain.execute()
    assert result == "fallback_result"


@pytest.mark.asyncio
async def test_fallback_all_fail():
    async def fail_a():
        raise RuntimeError("A failed")

    async def fail_b():
        raise RuntimeError("B failed")

    chain = FallbackChain()
    chain.add("a", fail_a)
    chain.add("b", fail_b)

    with pytest.raises(RuntimeError, match="All fallback strategies failed"):
        await chain.execute()
