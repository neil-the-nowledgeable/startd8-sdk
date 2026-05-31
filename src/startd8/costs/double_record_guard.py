"""
Guard against double-recording one call's cost via both cost APIs (REQ-AAO-002).

The SDK has two *distinct, non-redundant* cost signal families:

  - ``startd8.cost.*``    — global/automatic, emitted by ``CostTracker.record_cost()``
                            on the standard ``generate()`` path.
  - ``startd8_cost_total`` — per-session, emitted by ``SessionTracker.record_request()``
                            via the explicit session API.

They answer different questions and do **not** both fire in standard usage, so this is
NOT deduplication. But a caller that feeds the *same call's* cost to both APIs
double-counts. This guard detects that misuse — keyed on a shared ``correlation_id``
recorded from more than one source — and emits a single WARN (it never drops or raises;
the families are legitimately distinct).
"""

import threading
from collections import OrderedDict

from ..logging_config import get_logger

logger = get_logger(__name__)

# Bound the tracking map so a long-running process can't grow it unboundedly;
# correlation_ids are per-request and only matter near-simultaneously.
_MAX_TRACKED = 4096

_lock = threading.Lock()
# correlation_id -> set of source labels that recorded a cost for it.
_seen: "OrderedDict[str, set]" = OrderedDict()
# correlation_ids already warned about, so the WARN fires at most once each.
_warned: "OrderedDict[str, bool]" = OrderedDict()


def note_cost_recorded(source: str, correlation_id: object) -> None:
    """Record that ``source`` emitted a cost for ``correlation_id``; WARN once if a
    second distinct source also did (likely double-counting).

    Args:
        source: A short label for the emitting API (e.g. ``"cost_tracker"`` or
            ``"session_tracker"``).
        correlation_id: The current request correlation id, or a falsy value
            (ignored — without a correlation id the two emissions can't be linked).
    """
    if not correlation_id:
        return
    cid = str(correlation_id)
    with _lock:
        sources = _seen.get(cid)
        if sources is None:
            sources = set()
            _seen[cid] = sources
            _seen.move_to_end(cid)
            while len(_seen) > _MAX_TRACKED:
                _seen.popitem(last=False)
        sources.add(source)

        if len(sources) > 1 and cid not in _warned:
            _warned[cid] = True
            while len(_warned) > _MAX_TRACKED:
                _warned.popitem(last=False)
            logger.warning(
                "Cost for correlation_id=%s recorded via multiple APIs (%s): "
                "startd8.cost.* (global, CostTracker) and startd8_cost_total "
                "(per-session, SessionTracker) are distinct families — recording the "
                "same call's cost through both double-counts. Use one per call "
                "(REQ-AAO-002).",
                cid,
                sorted(sources),
            )


def _reset_for_tests() -> None:
    """Clear guard state (test-only)."""
    with _lock:
        _seen.clear()
        _warned.clear()
