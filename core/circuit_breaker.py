"""
Circuit Breaker — Prevents cascading failures from external APIs.
If an API fails N times in a row, the circuit "opens" and skips calls for a cooldown period.
"""

import time
import logging
from typing import Optional, Callable, Any

logger = logging.getLogger(__name__)


class CircuitBreaker:
    """
    States:
      CLOSED  — Normal operation, calls pass through
      OPEN    — Too many failures, calls are skipped
      HALF    — After cooldown, allow one test call
    """

    def __init__(self, name: str, failure_threshold: int = 5,
                 cooldown_seconds: float = 60, half_open_max: int = 1):
        self.name = name
        self.failure_threshold = failure_threshold
        self.cooldown_seconds = cooldown_seconds
        self.half_open_max = half_open_max

        self._state = "CLOSED"
        self._failure_count = 0
        self._last_failure_time = 0
        self._half_open_calls = 0
        self._total_trips = 0

    @property
    def state(self) -> str:
        if self._state == "OPEN":
            if time.time() - self._last_failure_time > self.cooldown_seconds:
                self._state = "HALF_OPEN"
                self._half_open_calls = 0
        return self._state

    @property
    def is_allowed(self) -> bool:
        s = self.state
        if s == "CLOSED":
            return True
        if s == "HALF_OPEN":
            return self._half_open_calls < self.half_open_max
        return False  # OPEN

    def record_success(self):
        if self._state == "HALF_OPEN":
            logger.info(f"Circuit [{self.name}] recovered → CLOSED")
        self._state = "CLOSED"
        self._failure_count = 0
        self._half_open_calls = 0

    def record_failure(self):
        self._failure_count += 1
        self._last_failure_time = time.time()

        if self._state == "HALF_OPEN":
            self._state = "OPEN"
            self._total_trips += 1
            logger.warning(f"Circuit [{self.name}] half-open test failed → OPEN")
        elif self._failure_count >= self.failure_threshold:
            self._state = "OPEN"
            self._total_trips += 1
            logger.warning(f"Circuit [{self.name}] tripped ({self._failure_count} failures) → OPEN for {self.cooldown_seconds}s")

    def execute(self, func: Callable, *args, fallback: Any = None, **kwargs) -> Any:
        """Execute func with circuit breaker protection."""
        if not self.is_allowed:
            logger.debug(f"Circuit [{self.name}] is OPEN — skipping call")
            return fallback

        if self._state == "HALF_OPEN":
            self._half_open_calls += 1

        try:
            result = func(*args, **kwargs)
            self.record_success()
            return result
        except Exception as e:
            self.record_failure()
            logger.warning(f"Circuit [{self.name}] call failed: {e}")
            return fallback

    def status(self) -> dict:
        return {
            "name": self.name,
            "state": self.state,
            "failures": self._failure_count,
            "threshold": self.failure_threshold,
            "cooldown_s": self.cooldown_seconds,
            "total_trips": self._total_trips,
        }


# Pre-configured breakers for external APIs
nse_breaker = CircuitBreaker("NSE", failure_threshold=5, cooldown_seconds=30)
yfinance_breaker = CircuitBreaker("yfinance", failure_threshold=3, cooldown_seconds=60)
llm_breaker = CircuitBreaker("LLM", failure_threshold=3, cooldown_seconds=120)
