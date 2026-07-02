# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""Promote an approved recommendation into its domain YAML (FR-KIR-11, R2-S1/R4-S1/R3-S3/R4-F2).

Reuses the **comment-preserving** ``splice_yaml_value`` primitive from
:mod:`startd8.kickoff_experience.capture` — a targeted line-range splice that preserves comments, key
order, and blank lines (SOTTO), rather than a full-file ``yaml.dump`` rewrite. Note this deliberately
uses the *low-level splice*, not ``apply_capture``: the latter is bound to the kickoff-experience
allow-list + a fixed per-field ``WriteTarget`` map, which cannot cover ``business-targets``' open
vocabulary of author-named metrics. The strict :mod:`startd8.kickoff_inputs` parser is the round-trip
gate; the concierge safe-writer performs the confined write.

Guards (the CRP contract):

* **Composite → sequential scalar splices (R4-S1).** A metric row's ``target``/``why`` are spliced one
  at a time (``capture.py`` is scalar-only). A mid-sequence key error aborts the whole field cleanly.
* **Strict round-trip gate (FR-KIR-11 / R1-F3).** The spliced file must re-parse through the domain's
  strict parser; a rejection surfaces the exact parser error and leaves the file untouched.
* **Stale-edit protection (R3-S3).** If the target field was filled **directly in the YAML** since the
  draft was made (it is no longer unfilled), the write is refused — a stale draft never clobbers a
  human edit — unless ``force``.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from startd8.kickoff_experience.capture import CaptureError, splice_yaml_value
from startd8.stakeholder_panel.input_domains import get_domain, unfilled_fields
from startd8.stakeholder_panel.models import Recommendation, Roster
from startd8.stakeholder_panel.provenance import brief_hash

__all__ = ["ApplyResult", "apply_recommendation", "roster_version_of"]


@dataclass(frozen=True)
class ApplyResult:
    """Outcome of promoting one recommendation. ``code`` mirrors the staged disposition on failure."""

    ok: bool
    code: str  # ok | unsupported | target_file_missing | key_not_found | round_trip_failed | stale | write_refused | noop
    value_path: str
    file: str
    error: str = ""


def roster_version_of(roster: Roster) -> str:
    """The roster version a live panel would pin (matches ``panel._roster_version``) — for drift checks.

    Used by ``review``/``approve`` to compare a staged ``roster_version`` against the live roster
    (R4-F2): a mismatch means the draft was produced under an older persona context.
    """
    joined = "|".join(sorted(brief_hash(b) for b in roster.personas))
    return "sha256:" + hashlib.sha256(joined.encode("utf-8")).hexdigest()[:16]


def apply_recommendation(
    package_root: Path | str, rec: Recommendation, *, force: bool = False
) -> ApplyResult:
    """Splice *rec*'s value(s) into its domain YAML through the strict gate + safe-writer.

    Returns an :class:`ApplyResult`; never raises for an expected refusal (missing key, gate failure,
    stale edit, confinement block) — those come back as a typed ``code`` the CLI maps to an exit code
    and a staged disposition.
    """
    root = Path(package_root).expanduser()
    spec = get_domain(rec.domain)
    if spec is None:
        return ApplyResult(False, "unsupported", rec.value_path, "", f"unknown domain {rec.domain!r}")
    rel = spec.rel_path()
    path = root / rel
    if not path.is_file():
        return ApplyResult(False, "target_file_missing", rec.value_path, rel, f"missing {rel}")

    original = path.read_text(encoding="utf-8")

    # Stale-edit protection (R3-S3): the field must still be unfilled unless forced.
    if not force:
        unfilled = {s.value_path for s in unfilled_fields(spec, original)}
        if rec.value_path not in unfilled:
            return ApplyResult(
                False,
                "stale",
                rec.value_path,
                rel,
                "field was filled directly in the YAML since it was drafted (pass --force to override)",
            )

    # Composite → sequential scalar splices (R4-S1); comment-preserving (R2-S1).
    text = original
    try:
        for dotted_key, value in rec.scalar_writes():
            text = splice_yaml_value(text, dotted_key, value).text
    except CaptureError as exc:
        return ApplyResult(False, "key_not_found", rec.value_path, rel, str(exc))

    # Strict round-trip gate (FR-KIR-11 / R1-F3): surface the exact parser error, write nothing.
    try:
        spec.parse(text)
    except ValueError as exc:
        return ApplyResult(False, "round_trip_failed", rec.value_path, rel, str(exc))

    if text == original:
        return ApplyResult(True, "noop", rec.value_path, rel)

    from startd8.concierge.safe_write import (
        ACTION_OVERWRITE,
        PlannedWrite,
        SafeWriteError,
        apply_write_plan,
    )

    try:
        result = apply_write_plan(
            root, [PlannedWrite(path=rel, content=text, action=ACTION_OVERWRITE)], force=True
        )
    except SafeWriteError as exc:
        return ApplyResult(False, "write_refused", rec.value_path, rel, str(exc))
    if not result.ok:
        detail = (result.blocked or result.errors or [{"reason": "unknown"}])[0]
        return ApplyResult(False, "write_refused", rec.value_path, rel, str(detail))
    return ApplyResult(True, "ok", rec.value_path, rel)


def approvable(recs: List[Recommendation]) -> List[Recommendation]:
    """The recs a batch ``approve --all`` promotes: those still in ``draft`` (idempotent, R1-S2)."""
    return [r for r in recs if r.disposition == "draft"]


def domain_fully_resolved(
    package_root: Path | str, domain: str
) -> Optional[bool]:
    """True iff the domain YAML now has **no unfilled fields** — the cue for the manual-flip hint (R4-S2).

    Returns ``None`` if the domain file is absent/unsupported.
    """
    spec = get_domain(domain)
    if spec is None:
        return None
    path = Path(package_root).expanduser() / spec.rel_path()
    if not path.is_file():
        return None
    return not unfilled_fields(spec, path.read_text(encoding="utf-8"))
