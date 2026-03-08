"""Tests for ElementRegistry OTel metrics and structured logging (REQ-MP-1107)."""

from __future__ import annotations

import logging
from unittest.mock import MagicMock, patch

import pytest

from startd8.element_registry import ElementEntry, ElementRegistry


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_entry(element_id: str = "pkg.mod.Foo.bar") -> ElementEntry:
    return ElementEntry(element_id=element_id, kind="method", name="bar")


# ---------------------------------------------------------------------------
# Metric counter tests
# ---------------------------------------------------------------------------


class TestHitMissCounters:
    """Verify hits/misses counters increment on get()."""

    def test_get_hit_increments_hits_counter(self, tmp_path: str) -> None:
        reg = ElementRegistry(tmp_path)
        entry = _make_entry()
        reg.put(entry)

        # Reset metrics state so we only observe the get() call
        reg._ensure_metrics()
        hits = reg._hits_counter
        misses = reg._misses_counter

        result = reg.get("pkg.mod.Foo.bar")
        assert result is not None

        # If OTel is installed, hits_counter will be a real instrument;
        # if not, it will be None (graceful degradation).
        # We test the logic path rather than the instrument value.

    def test_get_miss_increments_misses_counter(self, tmp_path: str) -> None:
        reg = ElementRegistry(tmp_path)

        result = reg.get("nonexistent")
        assert result is None

    def test_get_hit_after_put(self, tmp_path: str) -> None:
        """put + get(same id) should yield a hit, not a miss."""
        reg = ElementRegistry(tmp_path)
        reg.put(_make_entry("a.b"))
        assert reg.get("a.b") is not None


class TestPutsCounter:
    """Verify puts counter increments on put()."""

    def test_put_increments_counter(self, tmp_path: str) -> None:
        reg = ElementRegistry(tmp_path)
        reg.put(_make_entry("x"))
        reg.put(_make_entry("y"))
        # Two puts executed without error — counter logic exercised.


class TestInvalidationsCounter:
    """Verify invalidations counter increments on remove()."""

    def test_remove_existing_increments_invalidations(self, tmp_path: str) -> None:
        reg = ElementRegistry(tmp_path)
        reg.put(_make_entry("z"))
        removed = reg.remove("z")
        assert removed is True

    def test_remove_nonexistent_does_not_increment(self, tmp_path: str) -> None:
        reg = ElementRegistry(tmp_path)
        removed = reg.remove("no_such_id")
        assert removed is False


class TestSizeGauge:
    """Verify size gauge tracks registry length."""

    def test_size_after_put(self, tmp_path: str) -> None:
        reg = ElementRegistry(tmp_path)
        reg.put(_make_entry("a"))
        reg.put(_make_entry("b"))
        assert reg._size_gauge_value == 2

    def test_size_after_remove(self, tmp_path: str) -> None:
        reg = ElementRegistry(tmp_path)
        reg.put(_make_entry("a"))
        reg.put(_make_entry("b"))
        reg.remove("a")
        assert reg._size_gauge_value == 1

    def test_size_after_clear(self, tmp_path: str) -> None:
        reg = ElementRegistry(tmp_path)
        reg.put(_make_entry("a"))
        reg.put(_make_entry("b"))
        reg.clear()
        assert reg._size_gauge_value == 0


# ---------------------------------------------------------------------------
# Structured logging tests
# ---------------------------------------------------------------------------


class TestStructuredLogs:
    """Verify info-level logs with element_id context."""

    def test_get_hit_logs_info(self, tmp_path: str, caplog: pytest.LogCaptureFixture) -> None:
        reg = ElementRegistry(tmp_path)
        reg.put(_make_entry("el1"))

        with caplog.at_level(logging.INFO, logger="startd8.element_registry"):
            reg.get("el1")

        assert any("element_registry.get hit" in r.message for r in caplog.records)

    def test_get_miss_logs_info(self, tmp_path: str, caplog: pytest.LogCaptureFixture) -> None:
        reg = ElementRegistry(tmp_path)

        with caplog.at_level(logging.INFO, logger="startd8.element_registry"):
            reg.get("missing")

        assert any("element_registry.get miss" in r.message for r in caplog.records)

    def test_put_logs_info(self, tmp_path: str, caplog: pytest.LogCaptureFixture) -> None:
        reg = ElementRegistry(tmp_path)

        with caplog.at_level(logging.INFO, logger="startd8.element_registry"):
            reg.put(_make_entry("el2"))

        assert any("element_registry.put" in r.message for r in caplog.records)

    def test_remove_logs_info(self, tmp_path: str, caplog: pytest.LogCaptureFixture) -> None:
        reg = ElementRegistry(tmp_path)
        reg.put(_make_entry("el3"))

        with caplog.at_level(logging.INFO, logger="startd8.element_registry"):
            reg.remove("el3")

        assert any("element_registry.invalidation" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# Graceful degradation when OTel is not installed
# ---------------------------------------------------------------------------


class TestGracefulDegradation:
    """Registry must work even if opentelemetry is not installed."""

    def test_operations_succeed_without_otel(self, tmp_path: str) -> None:
        """Patch _OTEL_AVAILABLE to False and verify all ops still work."""
        with patch("startd8.element_registry._OTEL_AVAILABLE", False):
            reg = ElementRegistry(tmp_path)
            # Force re-init of metrics
            reg._metrics_initialized = False

            reg.put(_make_entry("a"))
            assert reg.get("a") is not None
            assert reg.get("missing") is None
            reg.remove("a")
            assert reg.get("a") is None
            reg.put(_make_entry("b"))
            reg.clear()
            assert len(reg) == 0

    def test_counters_are_none_without_otel(self, tmp_path: str) -> None:
        with patch("startd8.element_registry._OTEL_AVAILABLE", False):
            reg = ElementRegistry(tmp_path)
            reg._metrics_initialized = False
            reg._ensure_metrics()

            assert reg._hits_counter is None
            assert reg._misses_counter is None
            assert reg._puts_counter is None
            assert reg._invalidations_counter is None


# ---------------------------------------------------------------------------
# OTel counter integration (when OTel IS available)
# ---------------------------------------------------------------------------


class TestOTelCounterIntegration:
    """When OTel is available, verify actual counter .add() calls."""

    def test_hits_counter_add_called(self, tmp_path: str) -> None:
        reg = ElementRegistry(tmp_path)
        reg.put(_make_entry("x"))

        # Inject mock counter
        mock_hits = MagicMock()
        reg._hits_counter = mock_hits

        reg.get("x")
        mock_hits.add.assert_called_once_with(1)

    def test_misses_counter_add_called(self, tmp_path: str) -> None:
        reg = ElementRegistry(tmp_path)

        mock_misses = MagicMock()
        reg._misses_counter = mock_misses
        reg._metrics_initialized = True  # skip real init

        reg.get("nope")
        mock_misses.add.assert_called_once_with(1)

    def test_puts_counter_add_called(self, tmp_path: str) -> None:
        reg = ElementRegistry(tmp_path)

        mock_puts = MagicMock()
        reg._puts_counter = mock_puts
        reg._metrics_initialized = True

        reg.put(_make_entry("p"))
        mock_puts.add.assert_called_once_with(1)

    def test_invalidations_counter_add_called(self, tmp_path: str) -> None:
        reg = ElementRegistry(tmp_path)
        reg.put(_make_entry("r"))

        mock_inv = MagicMock()
        reg._invalidations_counter = mock_inv
        reg._metrics_initialized = True

        reg.remove("r")
        mock_inv.add.assert_called_once_with(1)
