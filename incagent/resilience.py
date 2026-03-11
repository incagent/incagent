"""Self-healing infrastructure: retry, circuit breaker, fallback."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable, Coroutine
from enum import Enum
from typing import Any, TypeVar

from incagent.config import ResilienceConfig

logger = logging.getLogger("incagent.resilience")
T = TypeVar("T")


class CircuitState(str, Enum):
    CLOSED = "closed"       # Normal operation
    OPEN = "open"           # Failing, reject calls
    HALF_OPEN = "half_open" # Testing recovery


class CircuitBreaker:
    """Stops calling failing services, auto-recovers after cooldown."""

    def __init__(self, threshold: int = 3, reset_seconds: float = 30.0) -> None:
        self.threshold = threshold
        self.reset_seconds = reset_seconds
        self.state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time = 0.0

    def record_success(self) -> None:
        self._failure_count = 0
        self.state = CircuitState.CLOSED

    def record_failure(self) -> None:
        self._failure_count += 1
        self._last_failure_time = time.monotonic()
        if self._failure_count >= self.threshold:
            self.state = CircuitState.OPEN
            logger.warning("Circuit breaker OPEN after %d failures", self._failure_count)

    def can_proceed(self) -> bool:
        if self.state == CircuitState.CLOSED:
            return True
        if self.state == CircuitState.OPEN:
            elapsed = time.monotonic() - self._last_failure_time
            if elapsed >= self.reset_seconds:
                self.state = CircuitState.HALF_OPEN
                logger.info("Circuit breaker HALF_OPEN, testing recovery")
                return True
            return False
        # HALF_OPEN: allow one attempt
        return True


class RetryWithBackoff:
    """Exponential backoff retry handler."""

    def __init__(self, max_retries: int = 5, base: float = 2.0, max_delay: float = 60.0) -> None:
        self.max_retries = max_retries
        self.base = base
        self.max_delay = max_delay

    async def execute(
        self,
        func: Callable[..., Coroutine[Any, Any, T]],
        *args: Any,
        **kwargs: Any,
    ) -> T:
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                last_error = e
                if attempt < self.max_retries:
                    delay = min(self.base ** attempt, self.max_delay)
                    logger.warning(
                        "Attempt %d/%d failed: %s. Retrying in %.1fs",
                        attempt + 1, self.max_retries, e, delay,
                    )
                    await asyncio.sleep(delay)
        raise last_error  # type: ignore[misc]


class FallbackChain:
    """Try a primary action, fall back to alternatives on failure."""

    def __init__(self) -> None:
        self._strategies: list[tuple[str, Callable[..., Coroutine[Any, Any, Any]]]] = []

    def add(self, name: str, func: Callable[..., Coroutine[Any, Any, Any]]) -> FallbackChain:
        self._strategies.append((name, func))
        return self

    async def execute(self, *args: Any, **kwargs: Any) -> Any:
        errors: list[tuple[str, Exception]] = []
        for name, func in self._strategies:
            try:
                result = await func(*args, **kwargs)
                logger.info("Fallback strategy '%s' succeeded", name)
                return result
            except Exception as e:
                logger.warning("Fallback strategy '%s' failed: %s", name, e)
                errors.append((name, e))
        raise RuntimeError(f"All fallback strategies failed: {errors}")


class HealthCheck:
    """Periodic self-diagnosis."""

    def __init__(self) -> None:
        self._checks: dict[str, Callable[[], Coroutine[Any, Any, bool]]] = {}
        self._results: dict[str, bool] = {}

    def register(self, name: str, check: Callable[[], Coroutine[Any, Any, bool]]) -> None:
        self._checks[name] = check

    async def run_all(self) -> dict[str, bool]:
        for name, check in self._checks.items():
            try:
                self._results[name] = await check()
            except Exception:
                self._results[name] = False
        return dict(self._results)

    @property
    def is_healthy(self) -> bool:
        return all(self._results.values()) if self._results else True


class ResilientExecutor:
    """Combines retry, circuit breaker, and fallback for resilient execution."""

    def __init__(self, config: ResilienceConfig | None = None) -> None:
        cfg = config or ResilienceConfig()
        self.retry = RetryWithBackoff(
            max_retries=cfg.max_retries,
            base=cfg.backoff_base,
            max_delay=cfg.backoff_max,
        )
        self.circuit = CircuitBreaker(
            threshold=cfg.circuit_breaker_threshold,
            reset_seconds=cfg.circuit_breaker_reset_seconds,
        )
        self.health = HealthCheck()

    async def execute(
        self,
        func: Callable[..., Coroutine[Any, Any, T]],
        *args: Any,
        fallback: Callable[..., Coroutine[Any, Any, T]] | None = None,
        **kwargs: Any,
    ) -> T:
        if not self.circuit.can_proceed():
            if fallback:
                logger.info("Circuit open, using fallback")
                return await fallback(*args, **kwargs)
            raise RuntimeError("Circuit breaker is OPEN and no fallback provided")

        try:
            result = await self.retry.execute(func, *args, **kwargs)
            self.circuit.record_success()
            return result
        except Exception as e:
            self.circuit.record_failure()
            if fallback:
                logger.warning("Primary failed, using fallback: %s", e)
                return await fallback(*args, **kwargs)
            raise
