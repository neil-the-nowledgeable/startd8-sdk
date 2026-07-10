# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""Render a :class:`FidelityReport` as an inverted-pyramid scorecard (A2).

First consumer of the shared ``verification`` core (verdict vocabulary + scorecard
renderer). Leads with the headline binding number, then per-service leaderboard, per-axis
mismatch, the degrade-honest exclusions (always shown), and the one-line fix. Reads a
persisted ``fidelity-report.json`` (from ``validate-promql --report``) so rendering is
decoupled from running — the CI gate can attach the scorecard as a build artifact.
"""

from __future__ import annotations

from typing import Any, Dict, List

from ..verification import Section, render_scorecard, table


def _pct(x: float) -> str:
    return f"{x * 100:.0f}%"


def _headline(r: Dict[str, Any]) -> List[str]:
    status = r.get("status", "?")
    binding = r.get("binding_coverage", r.get("coverage", 0.0))
    icon = {"pass": "✅", "fail": "❌", "unknown": "⚠️"}.get(status, "•")
    lines = [
        f"**{icon} {status.upper()} — binding fidelity {_pct(binding)}** "
        f"(min {_pct(r.get('min_coverage', 0.0))})",
        "",
        f"- Queries that **bind** to the live metric surface: **{_pct(binding)}**",
        f"- Have live data right now: {_pct(r.get('data_coverage', 0.0))} "
        f"({r.get('bound_no_data', 0)} bind but no data in-window)",
        f"- Replayed {r.get('queries_replayed', 0)} · "
        f"excluded {r.get('queries_excluded', 0)} query · "
        f"{sum((r.get('excluded_artifacts') or {}).values())} non-PromQL artifact",
    ]
    fix = r.get("suggested_metrics_profile")
    if fix:
        lines += ["", f"> **One-line fix:** set `spec.observability.metricsProfile: {fix}` and regenerate."]
    return lines


def _leaderboard(r: Dict[str, Any]) -> Section:
    rows = []
    for svc, d in sorted(
        (r.get("per_service") or {}).items(),
        key=lambda kv: kv[1].get("coverage", 0.0),
        reverse=True,
    ):
        rows.append([svc, _pct(d.get("coverage", 0.0)), f"{d.get('passed', 0)}/{d.get('total', 0)}"])
    return Section("Per-service binding leaderboard", table(["service", "binding", "bound/total"], rows))


def _axes(r: Dict[str, Any]) -> Section:
    counts = r.get("per_axis_mismatch_counts") or {}
    rows = [[axis, n] for axis, n in sorted(counts.items(), key=lambda kv: kv[1], reverse=True)]
    body = table(["mismatched axis", "count"], rows)
    if not rows:
        body = "_No axis mismatches — every failing query's descriptor axes are present live._"
    return Section("Where binding breaks (per axis)", body)


def _exclusions(r: Dict[str, Any]) -> Section:
    """Always present (degrade-honest): what was excluded and why."""
    art = r.get("excluded_artifacts") or {}
    byr = r.get("excluded_by_reason") or {}
    art_body = table(["artifact type", "count", "why"],
                     [[k, v, "not PromQL / not applicable to this backend"] for k, v in sorted(art.items())])
    reason_body = table(["reason", "count"], [[k, v] for k, v in sorted(byr.items())])
    body = (
        "**Non-replayable artifacts (seen, excluded by design — not failures):**\n\n"
        + art_body
        + "\n\n**Queries excluded from the denominator:**\n\n"
        + reason_body
    )
    return Section("Excluded, honestly", body)


def _target_drift(report: Dict[str, Any]) -> Section:
    """Declared-but-absent services — a whole-service gap, distinct from per-query fails."""
    drift = report.get("target_drift") or {}
    absent = drift.get("declared_absent") or []
    if not drift.get("checked"):
        body = "_Not checked (backend label values unavailable)._"
    elif not absent:
        body = "_No drift — every declared service is present in the backend._"
    else:
        body = (
            "The manifest declares these services but the backend has never emitted them "
            "(every one of their queries fails on the same axis). **Deploy them** (a real "
            "gap) or **`--exclude-services`** them (intentionally out of scope here):\n\n"
            + table(["declared-but-absent service"], [[s] for s in absent])
        )
    return Section("Target drift (declared vs deployed)", body)


def build_fidelity_scorecard(report: Dict[str, Any]) -> str:
    """Render a fidelity report dict (``FidelityReport.to_dict()``) as markdown."""
    sections = [
        _leaderboard(report),
        _axes(report),
        _target_drift(report),
        _exclusions(report),
    ]
    footer = (
        f"_{report.get('reason', '')}_\n\n"
        "Verdicts: `pass` = live data · `bound_no_data` = binds, no data in-window · "
        "`fail` = does not bind · `error` = backend rejected · `excluded` = not counted. "
        "binding_coverage = (pass + bound_no_data) / (replayed − excluded)."
    )
    return render_scorecard(
        title="Observability fidelity scorecard",
        headline=_headline(report),
        sections=sections,
        footer=footer,
    )
