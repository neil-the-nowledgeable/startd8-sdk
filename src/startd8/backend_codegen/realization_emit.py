"""Emit realization-provenance records for the deterministic (`$0`) generation path (REQ-19 FR-2).

The all-Python deterministic assembler owns every file it writes and produces them at ``$0`` — so each is
a ``deterministic``-regime record at full source confidence. This module imports the navigator's
realization **contract** (``make_record``) — the intended firewall direction (construction depends on the
navigator's typed contract, never the reverse) — and emits conforming records for the assembler's owned
files. The navigator later normalizes + joins them (FR-3/FR-4); it never imports this module.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List

from startd8.navigator.realization_contract import make_record


def deterministic_records(owned_paths: Iterable[str]) -> List[Dict[str, Any]]:
    """One conforming ``deterministic``-regime record per owned file, source_confidence ``1.0`` (the
    deterministic path's ownership is certain — the file *is* what it emitted). Deduplicated, order-stable.
    """
    seen: set = set()
    out: List[Dict[str, Any]] = []
    for path in owned_paths:
        p = str(path).strip()
        if not p or p in seen:
            continue
        seen.add(p)
        out.append(make_record(p, "deterministic", 1.0))
    return out
