"""Lightweight Prometheus metrics exporter — pure Python, no external deps."""

from __future__ import annotations

import math
import threading
from typing import Dict, Optional, Tuple


# ---------------------------------------------------------------------------
# Label helpers
# ---------------------------------------------------------------------------

LabelSet = Optional[Dict[str, str]]


def _label_key(labels: LabelSet) -> Tuple[Tuple[str, str], ...]:
    """Return a hashable, sorted tuple of label pairs."""
    if not labels:
        return ()
    return tuple(sorted(labels.items()))


def _format_labels(labels: LabelSet) -> str:
    """Format labels as Prometheus label string (e.g. {status="agreed"})."""
    if not labels:
        return ""
    inner = ",".join(f'{k}="{v}"' for k, v in sorted(labels.items()))
    return "{" + inner + "}"


# ---------------------------------------------------------------------------
# Metric types
# ---------------------------------------------------------------------------


class Counter:
    """Monotonically increasing counter with optional labels."""

    def __init__(self, name: str, help_text: str = "") -> None:
        self.name = name
        self.help_text = help_text
        self._lock = threading.Lock()
        self._values: Dict[Tuple[Tuple[str, str], ...], float] = {}

    def inc(self, amount: float = 1.0, labels: LabelSet = None) -> None:
        if amount < 0:
            raise ValueError("Counter can only be incremented by non-negative amounts")
        key = _label_key(labels)
        with self._lock:
            self._values[key] = self._values.get(key, 0.0) + amount

    def get(self, labels: LabelSet = None) -> float:
        key = _label_key(labels)
        with self._lock:
            return self._values.get(key, 0.0)

    def render(self) -> str:
        lines: list[str] = []
        lines.append(f"# HELP {self.name} {self.help_text}")
        lines.append(f"# TYPE {self.name} counter")
        with self._lock:
            for key, value in sorted(self._values.items()):
                lbl = _format_labels(dict(key) if key else None)
                lines.append(f"{self.name}{lbl} {_fmt_value(value)}")
        return "\n".join(lines)


class Gauge:
    """Gauge metric — can go up and down, with optional labels."""

    def __init__(self, name: str, help_text: str = "") -> None:
        self.name = name
        self.help_text = help_text
        self._lock = threading.Lock()
        self._values: Dict[Tuple[Tuple[str, str], ...], float] = {}

    def set(self, value: float, labels: LabelSet = None) -> None:
        key = _label_key(labels)
        with self._lock:
            self._values[key] = value

    def inc(self, amount: float = 1.0, labels: LabelSet = None) -> None:
        key = _label_key(labels)
        with self._lock:
            self._values[key] = self._values.get(key, 0.0) + amount

    def dec(self, amount: float = 1.0, labels: LabelSet = None) -> None:
        key = _label_key(labels)
        with self._lock:
            self._values[key] = self._values.get(key, 0.0) - amount

    def get(self, labels: LabelSet = None) -> float:
        key = _label_key(labels)
        with self._lock:
            return self._values.get(key, 0.0)

    def render(self) -> str:
        lines: list[str] = []
        lines.append(f"# HELP {self.name} {self.help_text}")
        lines.append(f"# TYPE {self.name} gauge")
        with self._lock:
            for key, value in sorted(self._values.items()):
                lbl = _format_labels(dict(key) if key else None)
                lines.append(f"{self.name}{lbl} {_fmt_value(value)}")
        return "\n".join(lines)


class SimpleHistogram:
    """Simplified histogram — tracks count, sum, min, max per label set.

    No buckets; emits ``_count``, ``_sum``, ``_min``, ``_max`` suffixed lines.
    """

    def __init__(self, name: str, help_text: str = "") -> None:
        self.name = name
        self.help_text = help_text
        self._lock = threading.Lock()
        # Each entry: (count, sum, min, max)
        self._values: Dict[
            Tuple[Tuple[str, str], ...], Tuple[int, float, float, float]
        ] = {}

    def observe(self, value: float, labels: LabelSet = None) -> None:
        key = _label_key(labels)
        with self._lock:
            if key in self._values:
                count, total, lo, hi = self._values[key]
                self._values[key] = (
                    count + 1,
                    total + value,
                    min(lo, value),
                    max(hi, value),
                )
            else:
                self._values[key] = (1, value, value, value)

    def get(self, labels: LabelSet = None) -> Tuple[int, float, float, float]:
        """Return (count, sum, min, max). Returns (0, 0, inf, -inf) if empty."""
        key = _label_key(labels)
        with self._lock:
            return self._values.get(key, (0, 0.0, math.inf, -math.inf))

    def render(self) -> str:
        lines: list[str] = []
        lines.append(f"# HELP {self.name} {self.help_text}")
        lines.append(f"# TYPE {self.name} histogram")
        with self._lock:
            for key, (count, total, lo, hi) in sorted(self._values.items()):
                lbl = _format_labels(dict(key) if key else None)
                lines.append(f"{self.name}_count{lbl} {count}")
                lines.append(f"{self.name}_sum{lbl} {_fmt_value(total)}")
                lines.append(f"{self.name}_min{lbl} {_fmt_value(lo)}")
                lines.append(f"{self.name}_max{lbl} {_fmt_value(hi)}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Value formatting
# ---------------------------------------------------------------------------


def _fmt_value(v: float) -> str:
    """Format a numeric value for Prometheus output."""
    if v == int(v) and not math.isinf(v):
        return str(int(v))
    return repr(v)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


class MetricsRegistry:
    """Central registry for all metrics. Thread-safe singleton pattern."""

    _instance: Optional["MetricsRegistry"] = None
    _init_lock = threading.Lock()

    def __new__(cls) -> "MetricsRegistry":
        with cls._init_lock:
            if cls._instance is None:
                inst = super().__new__(cls)
                inst._metrics: Dict[str, Counter | Gauge | SimpleHistogram] = {}
                inst._lock = threading.Lock()
                inst._initialized = True
                cls._instance = inst
            return cls._instance

    # -- registration helpers ------------------------------------------------

    def counter(self, name: str, help_text: str = "") -> Counter:
        with self._lock:
            if name not in self._metrics:
                self._metrics[name] = Counter(name, help_text)
            metric = self._metrics[name]
            if not isinstance(metric, Counter):
                raise TypeError(f"{name} is already registered as {type(metric).__name__}")
            return metric

    def gauge(self, name: str, help_text: str = "") -> Gauge:
        with self._lock:
            if name not in self._metrics:
                self._metrics[name] = Gauge(name, help_text)
            metric = self._metrics[name]
            if not isinstance(metric, Gauge):
                raise TypeError(f"{name} is already registered as {type(metric).__name__}")
            return metric

    def histogram(self, name: str, help_text: str = "") -> SimpleHistogram:
        with self._lock:
            if name not in self._metrics:
                self._metrics[name] = SimpleHistogram(name, help_text)
            metric = self._metrics[name]
            if not isinstance(metric, SimpleHistogram):
                raise TypeError(f"{name} is already registered as {type(metric).__name__}")
            return metric

    def get(self, name: str) -> Counter | Gauge | SimpleHistogram | None:
        with self._lock:
            return self._metrics.get(name)

    def render(self) -> str:
        """Render all metrics in Prometheus text exposition format."""
        with self._lock:
            ordered = list(self._metrics.values())
        blocks = [m.render() for m in ordered if self._has_data(m)]
        return "\n\n".join(blocks) + "\n" if blocks else ""

    @staticmethod
    def _has_data(metric: Counter | Gauge | SimpleHistogram) -> bool:
        return bool(metric._values)

    def reset(self) -> None:
        """Clear all metrics (useful for tests)."""
        with self._lock:
            self._metrics.clear()


# ---------------------------------------------------------------------------
# Module-level singleton & pre-registered metrics
# ---------------------------------------------------------------------------

METRICS = MetricsRegistry()

# Counters
_trades_total = METRICS.counter(
    "incagent_trades_total", "Total trades by status"
)
_payments_total = METRICS.counter(
    "incagent_payments_total", "Total payments by status"
)
_negotiations_total = METRICS.counter(
    "incagent_negotiations_total", "Total negotiations started"
)
_tools_executed_total = METRICS.counter(
    "incagent_tools_executed_total", "Total tool executions by tool name"
)
_api_requests_total = METRICS.counter(
    "incagent_api_requests_total", "Total API requests by endpoint and method"
)
_auth_failures_total = METRICS.counter(
    "incagent_auth_failures_total", "Total authentication failures"
)
_disputes_total = METRICS.counter(
    "incagent_disputes_total", "Total disputes by resolution"
)

# Gauges
_agent_state = METRICS.gauge(
    "incagent_agent_state", "Current agent state (1 for active)"
)
_active_settlements = METRICS.gauge(
    "incagent_active_settlements", "Number of active settlements"
)
_known_peers = METRICS.gauge(
    "incagent_known_peers", "Number of known peers"
)
_usdc_balance = METRICS.gauge(
    "incagent_usdc_balance", "Current USDC balance"
)
_circuit_breaker_state = METRICS.gauge(
    "incagent_circuit_breaker_state", "Circuit breaker state (1 for active)"
)

# Histograms
_negotiation_rounds = METRICS.histogram(
    "incagent_negotiation_rounds", "Rounds per negotiation"
)
_negotiation_duration = METRICS.histogram(
    "incagent_negotiation_duration_seconds", "Duration per negotiation in seconds"
)
_payment_amount = METRICS.histogram(
    "incagent_payment_amount_usdc", "Payment amounts in USDC"
)


# ---------------------------------------------------------------------------
# Convenience functions
# ---------------------------------------------------------------------------


def inc_counter(name: str, labels: LabelSet = None, amount: float = 1.0) -> None:
    """Increment a counter by name. Creates it if it doesn't exist."""
    metric = METRICS.get(name)
    if metric is None:
        metric = METRICS.counter(name)
    if not isinstance(metric, Counter):
        raise TypeError(f"{name} is not a Counter")
    metric.inc(amount, labels)


def set_gauge(name: str, value: float, labels: LabelSet = None) -> None:
    """Set a gauge by name. Creates it if it doesn't exist."""
    metric = METRICS.get(name)
    if metric is None:
        metric = METRICS.gauge(name)
    if not isinstance(metric, Gauge):
        raise TypeError(f"{name} is not a Gauge")
    metric.set(value, labels)


def observe(name: str, value: float, labels: LabelSet = None) -> None:
    """Record an observation on a histogram by name. Creates it if it doesn't exist."""
    metric = METRICS.get(name)
    if metric is None:
        metric = METRICS.histogram(name)
    if not isinstance(metric, SimpleHistogram):
        raise TypeError(f"{name} is not a SimpleHistogram")
    metric.observe(value, labels)


def render_metrics() -> str:
    """Render all registered metrics in Prometheus text exposition format."""
    return METRICS.render()
