"""OTel telemetry for presentation polish (FR-23).

Mirrors ``frontend_codegen/telemetry.py``: a guarded import, lazy meter init, every emission
non-fatal and a **no-op when OTel is unavailable or unconfigured** (headless / CI). Emitted from the
*CLI boundary* (``cli_polish``), never from the pure engine/renderers — so ``apply_polish`` stays
deterministic and byte-stable, and importing the engine pulls in nothing here.

Descriptors are declared below and the module is registered in
``observability/collector.py:_INSTRUMENTED_MODULES`` so the descriptor↔emission **bijection** holds
(REQ-OBS-SHARED-002): every ``create_counter`` name here has a matching descriptor and vice versa.
"""

from __future__ import annotations

from typing import Any, Dict

try:  # OTel is optional — absence must not break a no-LLM, offline generator.
    from opentelemetry import metrics as _otel_metrics

    _OTEL_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised only when OTel isn't installed
    _otel_metrics = None  # type: ignore[assignment]
    _OTEL_AVAILABLE = False

_METER_NAME = "startd8.presentation_polish"

# Observability manifest descriptor — consumed by the collector/manifest; zero runtime cost.
# Presentation polish is a deterministic $0 generation step (pipeline-innate, like frontend_codegen).
_OTEL_DESCRIPTORS = {
    "category": "pipeline_innate",
    "orientation": "system",
    "metrics": [
        {
            "name": "startd8.presentation_polish.files",
            "instrument": "counter",
            "unit": "files",
            "description": "Polish-owned files, labelled by per-file status + theme",
            "meter": _METER_NAME,
            "labels": ["status", "theme"],
        },
        {
            "name": "startd8.presentation_polish.runs",
            "instrument": "counter",
            "unit": "runs",
            "description": "Polish apply/check runs, labelled by theme + mode + result",
            "meter": _METER_NAME,
            "labels": ["theme", "mode", "result"],
        },
    ],
}

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
        _instruments["files"] = meter.create_counter(
            "startd8.presentation_polish.files",
            unit="files",
            description="Polish-owned files, labelled by per-file status + theme",
        )
        _instruments["runs"] = meter.create_counter(
            "startd8.presentation_polish.runs",
            unit="runs",
            description="Polish apply/check runs, labelled by theme + mode + result",
        )
    except Exception:  # pragma: no cover - provider misconfig path
        _instruments.clear()
        return False
    return True


def record_polish(result: Any, *, check: bool) -> None:
    """Emit counters for one polish apply/check. No-op if OTel is unavailable; never raises."""
    if not _ensure():
        return
    try:
        for _relpath, status in result.files:
            _instruments["files"].add(
                1,
                {
                    "status": getattr(status, "value", str(status)),
                    "theme": result.theme,
                },
            )
        if check:
            outcome = "drift" if result.has_drift else "in_sync"
        else:
            outcome = "wrote" if result.wrote_anything else "unchanged"
        _instruments["runs"].add(
            1,
            {
                "theme": result.theme,
                "mode": "check" if check else "apply",
                "result": outcome,
            },
        )
    except Exception:  # pragma: no cover
        pass
