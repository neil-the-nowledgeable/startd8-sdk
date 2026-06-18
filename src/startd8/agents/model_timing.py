"""Process-level accumulator for pure model API time (FR-SPEED-1).

Each LLM call's ``GenerateResult.time_ms`` is the time spent in the provider API call itself —
distinct from the pipeline wall-clock (which includes prompt building, parsing, repair, validation,
and process overhead). Summing every call's ``time_ms`` over a run gives the **pure model generation
time**: "how fast is the model itself," harness-independent.

Why a process accumulator rather than threading through the generator layers: ``agenerate`` is
abstract (each agent times itself) and the time crosses several generator delegations before reaching
the contractor. A small, resettable, thread-safe counter that every concrete agent feeds captures
every call regardless of which layer invoked it. The benchmark runs one cell per subprocess, so the
contractor resets at run start and reads the cumulative total at manifest time = that cell's model
time. Library consumers that want per-segment timing call ``reset_model_time_ms`` around the segment.
"""
from __future__ import annotations

import threading

_lock = threading.Lock()
_total_model_time_ms: float = 0.0
_call_count: int = 0


def record_model_time_ms(time_ms: float | int | None) -> None:
    """Add one model call's elapsed time (ms) to the process total. None/invalid is ignored."""
    if time_ms is None:
        return
    try:
        ms = float(time_ms)
    except (TypeError, ValueError):
        return
    if ms < 0:
        return
    global _total_model_time_ms, _call_count
    with _lock:
        _total_model_time_ms += ms
        _call_count += 1


def get_model_time_ms_total() -> float:
    with _lock:
        return _total_model_time_ms


def get_model_call_count() -> int:
    with _lock:
        return _call_count


def reset_model_time_ms() -> None:
    global _total_model_time_ms, _call_count
    with _lock:
        _total_model_time_ms = 0.0
        _call_count = 0
