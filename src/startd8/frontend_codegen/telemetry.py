"""OTel telemetry for deterministic frontend generation (NFR-6).

Mirrors the SDK's ``costs/otel_metrics.py`` convention: a guarded import, lazy meter init,
and every emission wrapped non-fatal. **All functions are no-ops when OTel is unavailable or
unconfigured** (headless / CI), and they never raise.

Telemetry is emitted from the *CLI / pipeline boundary*, never from the pure renderer — so
``render_zod_schema`` stays side-effect-free and byte-deterministic (the renderer's whole
value proposition), and importing it in isolation pulls in nothing here.
"""

from __future__ import annotations

from typing import Any, Dict

try:  # OTel is optional — absence must not break a no-LLM, offline generator.
    from opentelemetry import metrics as _otel_metrics

    _OTEL_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised only when OTel isn't installed
    _otel_metrics = None  # type: ignore[assignment]
    _OTEL_AVAILABLE = False

_METER_NAME = "startd8.frontend_codegen"

_instruments: Dict[str, Any] = {}
_initialized = False


def _ensure() -> bool:
    """Lazy-init the meter + instruments. Returns True iff ready. Never raises."""
    global _initialized
    if _initialized:
        return bool(_instruments)
    _initialized = True
    if not _OTEL_AVAILABLE:
        return False
    try:
        meter = _otel_metrics.get_meter(_METER_NAME)
        _instruments["models"] = meter.create_counter(
            "startd8.frontend_codegen.models_rendered",
            unit="models",
            description="Prisma models rendered to Zod schemas",
        )
        _instruments["fields"] = meter.create_counter(
            "startd8.frontend_codegen.fields_rendered",
            unit="fields",
            description="Scalar fields rendered",
        )
        _instruments["hints"] = meter.create_counter(
            "startd8.frontend_codegen.format_hints_applied",
            unit="hints",
            description="Convention format hints (.email/.url) applied",
        )
        _instruments["unrenderable"] = meter.create_counter(
            "startd8.frontend_codegen.unrenderable_fields",
            unit="fields",
            description="Fields with no deterministic Zod mapping",
        )
        _instruments["drift"] = meter.create_counter(
            "startd8.frontend_codegen.drift_check",
            unit="checks",
            description="Drift checks, labelled by status",
        )
    except Exception:  # pragma: no cover - provider misconfig path
        _instruments.clear()
        return False
    return True


def record_render(result: Any) -> None:
    """Emit counters for one render. No-op if OTel is unavailable; never raises."""
    if not _ensure():
        return
    try:
        _instruments["models"].add(int(result.models_rendered))
        _instruments["fields"].add(int(result.fields_rendered))
        _instruments["hints"].add(int(result.format_hints_applied))
        _instruments["unrenderable"].add(len(result.unrenderable))
    except Exception:  # pragma: no cover
        pass


def record_drift_check(status: str) -> None:
    """Emit a drift-check counter labelled by status. No-op if unavailable; never raises."""
    if not _ensure():
        return
    try:
        _instruments["drift"].add(1, {"status": status})
    except Exception:  # pragma: no cover
        pass
