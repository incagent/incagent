"""Prometheus metrics module tests."""

from __future__ import annotations

import pytest

from incagent.metrics import Counter, Gauge, MetricsRegistry, SimpleHistogram


class TestCounter:
    def test_increment(self):
        c = Counter("test_total", "Test counter")
        c.inc()
        c.inc()
        assert c.get() == 2

    def test_increment_by(self):
        c = Counter("test_total", "Test counter")
        c.inc(5)
        assert c.get() == 5

    def test_labels(self):
        c = Counter("test_total", "Test counter")
        c.inc(labels={"status": "ok"})
        c.inc(labels={"status": "ok"})
        c.inc(labels={"status": "error"})
        assert c.get({"status": "ok"}) == 2
        assert c.get({"status": "error"}) == 1

    def test_no_negative(self):
        c = Counter("test_total", "Test counter")
        with pytest.raises(ValueError):
            c.inc(-1)


class TestGauge:
    def test_set(self):
        g = Gauge("test_gauge", "Test gauge")
        g.set(42)
        assert g.get() == 42

    def test_inc_dec(self):
        g = Gauge("test_gauge", "Test gauge")
        g.inc()
        g.inc()
        g.dec()
        assert g.get() == 1

    def test_labels(self):
        g = Gauge("test_gauge", "Test gauge")
        g.set(10, labels={"host": "a"})
        g.set(20, labels={"host": "b"})
        assert g.get({"host": "a"}) == 10
        assert g.get({"host": "b"}) == 20


class TestSimpleHistogram:
    def test_observe(self):
        h = SimpleHistogram("test_duration", "Test histogram")
        h.observe(1.0)
        h.observe(2.0)
        h.observe(3.0)
        count, total, lo, hi = h.get()
        assert count == 3
        assert total == 6.0
        assert lo == 1.0
        assert hi == 3.0

    def test_empty(self):
        h = SimpleHistogram("test_duration", "Test histogram")
        count, total, lo, hi = h.get()
        assert count == 0
        assert total == 0.0

    def test_labels(self):
        h = SimpleHistogram("test_duration", "Test histogram")
        h.observe(1.0, labels={"method": "GET"})
        h.observe(2.0, labels={"method": "POST"})
        count, _, _, _ = h.get({"method": "GET"})
        assert count == 1


class TestMetricsRegistry:
    def test_register_and_render(self):
        reg = MetricsRegistry()
        c = reg.counter("app_requests_total", "Total requests")
        c.inc(labels={"method": "GET"})
        c.inc(labels={"method": "GET"})
        c.inc(labels={"method": "POST"})

        output = reg.render()
        assert "app_requests_total" in output
        assert 'method="GET"' in output
        assert "# HELP" in output
        assert "# TYPE" in output

    def test_gauge_render(self):
        reg = MetricsRegistry()
        g = reg.gauge("app_connections", "Active connections")
        g.set(5)

        output = reg.render()
        assert "app_connections 5" in output

    def test_histogram_render(self):
        reg = MetricsRegistry()
        h = reg.histogram("app_duration_seconds", "Request duration")
        h.observe(0.1)
        h.observe(0.5)

        output = reg.render()
        assert "app_duration_seconds_count" in output
        assert "app_duration_seconds_sum" in output

    def test_multiple_metrics(self):
        reg = MetricsRegistry()
        reg.counter("a_total", "A").inc()
        reg.gauge("b_gauge", "B").set(10)
        reg.histogram("c_hist", "C").observe(1.0)

        output = reg.render()
        assert "a_total" in output
        assert "b_gauge" in output
        assert "c_hist" in output

    def test_singleton(self):
        """MetricsRegistry is a singleton — all instances are the same."""
        reg1 = MetricsRegistry()
        reg2 = MetricsRegistry()
        assert reg1 is reg2
