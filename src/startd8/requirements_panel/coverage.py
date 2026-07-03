# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""Advisory readiness / coverage score (FR-RP-11 — resolves OQ-RP-8).

Computed `$0` from the assembled doc, shown in ``review`` alongside the **blocking** readiness gate.
**Advisory only** — it never gates and never promotes; it answers "how done am I?" and makes the paid
pass's value observable (Ask-5). It reports:

* per-area FR counts split by provenance (baseline vs role-drafted vs human);
* the areas a role pass added intent to over the `$0` baseline (the paid-pass value delta);
* unresolved grounding flags by severity, and the unowned-``<needs-owner>`` stub count;
* **near-duplicate** titles — the honest counterpart to synthesis's keep-both dedupe (R1-F3): distinct
  slugs that are *similar* were deliberately kept, so surface them for the human to merge (never auto).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Tuple

from startd8.requirements_panel.models import (
    PROV_BASELINE,
    PROV_ESTIMATE,
    PROV_HUMAN,
    RequirementDoc,
    normalize_slug,
)

__all__ = ["CoverageReport", "coverage_report"]

_NEAR_DUP_JACCARD = (
    0.5  # token-set overlap above which two distinct titles are "near-duplicate"
)


@dataclass
class CoverageReport:
    total_frs: int = 0
    by_area: Dict[str, Dict[str, int]] = field(default_factory=dict)
    flags_by_severity: Dict[str, int] = field(default_factory=dict)
    unowned_stubs: int = 0
    areas_with_role_input: List[str] = field(default_factory=list)
    areas_baseline_only: List[str] = field(default_factory=list)
    near_duplicates: List[Tuple[str, str]] = field(default_factory=list)

    def render(self) -> str:
        lines: List[str] = [
            f"coverage: {self.total_frs} FRs across {len(self.by_area)} areas"
        ]
        for area, counts in self.by_area.items():
            lines.append(
                f"  {area}: {counts['total']} "
                f"(baseline {counts[PROV_BASELINE]}, role {counts[PROV_ESTIMATE]}, human {counts[PROV_HUMAN]})"
            )
        if self.areas_with_role_input:
            lines.append(
                f"  paid-pass value: role input in {', '.join(self.areas_with_role_input)}"
            )
        if self.areas_baseline_only:
            lines.append(
                f"  baseline-only (no role input yet): {', '.join(self.areas_baseline_only)}"
            )
        if self.unowned_stubs:
            lines.append(
                f"  unowned <needs-owner> stubs (block approve): {self.unowned_stubs}"
            )
        if self.flags_by_severity:
            sev = ", ".join(f"{k}={v}" for k, v in self.flags_by_severity.items())
            lines.append(f"  grounding flags: {sev}")
        if self.near_duplicates:
            lines.append(
                f"  near-duplicate titles (consider merging): {len(self.near_duplicates)}"
            )
            for a, b in self.near_duplicates:
                lines.append(f"    - {a!r} ~ {b!r}")
        return "\n".join(lines)


def _severity_of(flag: str) -> str:
    return flag.split(":", 1)[0].strip()


def _tokens(title: str) -> set:
    return set(normalize_slug(title).split("-")) - {""}


def coverage_report(doc: RequirementDoc) -> CoverageReport:
    """Compute the advisory coverage report for an assembled *doc* ($0, never gates)."""
    rep = CoverageReport(total_frs=len(doc.candidates))
    for c in doc.candidates:
        area = rep.by_area.setdefault(
            c.area, {PROV_BASELINE: 0, PROV_ESTIMATE: 0, PROV_HUMAN: 0, "total": 0}
        )
        prov = c.provenance if c.provenance in area else PROV_BASELINE
        area[prov] += 1
        area["total"] += 1
        if c.needs_owner:
            rep.unowned_stubs += 1
        for flag in c.flags:
            sev = _severity_of(flag)
            rep.flags_by_severity[sev] = rep.flags_by_severity.get(sev, 0) + 1

    for area, counts in rep.by_area.items():
        if counts[PROV_ESTIMATE] or counts[PROV_HUMAN]:
            rep.areas_with_role_input.append(area)
        else:
            rep.areas_baseline_only.append(area)

    # near-duplicate titles: distinct slugs with high token overlap (keep-both survivors, R1-F3).
    # Only role-drafted/human FRs are considered — baseline stubs are deterministically one-per-entity
    # (their templated "Manage <Entity> records" titles share tokens but are never real duplicates).
    cands = [c for c in doc.candidates if c.provenance != PROV_BASELINE]
    for i in range(len(cands)):
        for j in range(i + 1, len(cands)):
            a, b = cands[i], cands[j]
            if a.slug == b.slug:
                continue  # exact dupes were already merged by synthesis
            ta, tb = _tokens(a.title), _tokens(b.title)
            if not ta or not tb:
                continue
            jaccard = len(ta & tb) / len(ta | tb)
            if jaccard >= _NEAR_DUP_JACCARD:
                rep.near_duplicates.append((a.title, b.title))
    return rep
