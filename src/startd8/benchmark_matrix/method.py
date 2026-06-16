"""Scoring-method identity for a benchmark run (CS-17 — combined-scoreboard prerequisite).

The combined scoreboard merges cells *across* runs into one ranking, and may only merge cells scored
under the **same scoring method** (CS-5). But `run-spec.json`'s `scoring_formula` is byte-identical
across naive and shadow+expose runs, and the repair posture / defect-ledger state were not historically
persisted. This module resolves a run's scoring method, with a chain of decreasing reliability:

1. **stamped** — `run-spec.json` carries `repair_mode` + `expose_defects` (runs produced after CS-17).
2. **inferred** — no stamp: infer the *expose* state from the cells (`defect_total is not None` ⇒ the
   defect ledger ran). The repair posture (shadow vs apply) is **not recoverable** from persisted cells,
   so an inferred signature is deliberately coarse.
3. **none** — neither a usable run-spec nor cells: `unknown`.

The parity gate (M1) compares `MethodSignature.parity_key`. It is **conservative**: an inferred
`expose` does NOT match a stamped `shadow+expose` — re-stamp/re-score to merge them. Over-caution here
yields a false *exclusion* (safe), never a false *merge* (a silently-wrong consolidated board).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from .runner import CellResult

RUN_SPEC_FILE = "run-spec.json"
CELLS_FILE = "cells.json"


def _derive_method(repair_mode: str, expose_defects: bool) -> str:
    """The discrete scoring-method tag (OQ-8 taxonomy) from the raw posture fields."""
    if expose_defects and repair_mode == "shadow":
        return "shadow+expose"
    if expose_defects:
        return "expose"
    if repair_mode == "shadow":
        return "shadow"
    if repair_mode == "off":
        return "raw"
    return "naive"  # apply + no expose — the pre-stamp default posture


@dataclass(frozen=True)
class MethodSignature:
    """How a run scored its cells. `expose` is reliably known (stamped or inferred); `repair_mode` is
    None when inferred (shadow-vs-apply is unrecoverable from persisted cells)."""

    scoring_method: str            # naive | expose | shadow | shadow+expose | raw | unknown
    expose: bool                   # defect ledger folded into the score (reliably known)
    sdk_version: Optional[str]
    scoring_formula: Optional[str]
    source: str                    # stamped | inferred:defect_ledger | inferred:no_ledger | none
    repair_mode: Optional[str] = None  # None ⇒ inferred (unknown repair posture)

    @property
    def parity_key(self) -> tuple:
        """The key the combined-scoreboard merge gate (CS-5) compares. Conservative by design — an
        inferred `expose` will not match a stamped `shadow+expose`; re-stamp to merge."""
        return (self.scoring_method, self.sdk_version, self.scoring_formula)

    @property
    def is_inferred(self) -> bool:
        return self.source.startswith("inferred") or self.source == "none"


def _load_json(path: Path) -> Optional[dict]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 - a missing/malformed file is a degrade, not a crash (CS-16)
        return None


def _load_cells(run_dir: Path) -> List[CellResult]:
    raw = _load_json(run_dir / CELLS_FILE)
    if not isinstance(raw, list):
        return []
    out: List[CellResult] = []
    for d in raw:
        try:
            out.append(CellResult.from_dict(d))
        except Exception:  # noqa: BLE001 - one malformed cell shouldn't sink signature resolution
            continue
    return out


def method_signature(run_dir) -> MethodSignature:
    """Resolve the scoring-method signature of a benchmark run directory (CS-17).

    Tolerant of heterogeneous/partial run dirs (CS-16): missing run-spec, missing cells, extra fields.
    Never raises — an unresolvable dir yields ``scoring_method="unknown"``.
    """
    run_dir = Path(run_dir)
    spec = _load_json(run_dir / RUN_SPEC_FILE) or {}
    sdk = spec.get("sdk_version")
    formula = spec.get("scoring_formula")

    # 1. stamped (post-CS-17): authoritative.
    if "repair_mode" in spec and "expose_defects" in spec:
        rm = spec.get("repair_mode") or "apply"
        ex = bool(spec.get("expose_defects"))
        return MethodSignature(
            scoring_method=_derive_method(rm, ex), expose=ex,
            sdk_version=sdk, scoring_formula=formula, source="stamped", repair_mode=rm,
        )

    # 2. inferred from cells: expose is recoverable (defect ledger), repair posture is not.
    cells = _load_cells(run_dir)
    if cells:
        exposed = any(c.defect_total is not None for c in cells)
        return MethodSignature(
            scoring_method="expose" if exposed else "naive", expose=exposed,
            sdk_version=sdk, scoring_formula=formula,
            source="inferred:defect_ledger" if exposed else "inferred:no_ledger", repair_mode=None,
        )

    # 3. nothing to go on.
    return MethodSignature(
        scoring_method="unknown", expose=False,
        sdk_version=sdk, scoring_formula=formula, source="none", repair_mode=None,
    )
