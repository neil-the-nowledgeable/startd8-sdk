"""Tier-A derived-vs-declared observability comparison.

Reads a generated ``observability-manifest.yaml``'s ``fr_coverage`` block — the static divergence
the generator already records (where the derived SLIs can't be grounded against the subject's
declared instrumentation surface) — and renders it as a first-class report. **$0, offline** — no
live Prometheus, no subject stand-up. The live twin (Tier B: replay the queries against real
telemetry) is ``startd8 observability validate-promql``.

See ``docs/design/OBSERVABILITY_DERIVED_VS_EMITTED_COMPARISON.md``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Tuple

import yaml

#: The ``fr_coverage`` divergence classes, in report order, each with a human label. The generator
#: (``artifact_generator.py``) populates these; this module only presents them.
_GAP_CLASSES: Tuple[Tuple[str, str], ...] = (
    ("suppressed_base_metrics", "SUPPRESSED base SLIs — declared non-emitting metrics_surface (#274)"),
    ("suppressed_scrape_configs", "SUPPRESSED ServiceMonitors — surface serves no /metrics scrape (#285)"),
    ("unverified_base_metrics", "UNVERIFIED base SLIs — emission surface unknown, advisory (#277)"),
    ("deferred_declared_kinds", "DEFERRED declared kinds — covered but not base-bindable; see each entry's `reason` (availability without an error-selector, or a functional kind like saturation) (#286/#300)"),
    ("unfulfilled", "UNFULFILLED FRs — declared signal_kind, no emitting series"),
    ("ungrounded_kinds", "UNGROUNDED kinds — batch/cron/ml_inference, values pending grounding"),
    ("empty_services", "EMPTY services — observed by nothing"),
)
_LABELS = dict(_GAP_CLASSES)


@dataclass
class ComparisonReport:
    """The Tier-A comparison: what the derived artifacts ground (emitted / bound) vs where they diverge."""

    emitted: List[str]
    gaps: Dict[str, List[Any]]  # class key -> non-empty entries
    #: #286: base SLIs BOUND to an author-declared real emitted series — a positive grounding
    #: (the derived SLI targets a real series, not a convention metric the subject may not emit).
    bound: List[Any] = field(default_factory=list)

    @property
    def total_gaps(self) -> int:
        return sum(len(v) for v in self.gaps.values())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "emitted": self.emitted,
            "emitted_count": len(self.emitted),
            "bound_declared_series": self.bound,
            "bound_count": len(self.bound),
            "gaps": self.gaps,
            "gap_classes": list(self.gaps.keys()),
            "total_gaps": self.total_gaps,
        }


def read_fr_coverage(manifest_path: Path) -> Dict[str, Any]:
    """The ``fr_coverage`` block of a generated manifest, or ``{}`` when absent (a fully-grounded
    run omits it — treated as no divergence)."""
    data = yaml.safe_load(Path(manifest_path).read_text(encoding="utf-8")) or {}
    return data.get("fr_coverage") or {}


def build_comparison_report(fr_coverage: Dict[str, Any]) -> ComparisonReport:
    emitted = list(fr_coverage.get("emitted") or [])
    bound = list(fr_coverage.get("bound_declared_series") or [])
    gaps: Dict[str, List[Any]] = {}
    for key, _label in _GAP_CLASSES:
        entries = fr_coverage.get(key) or []
        if entries:
            gaps[key] = list(entries)
    return ComparisonReport(emitted=emitted, gaps=gaps, bound=bound)


def _entry_line(entry: Any) -> str:
    if isinstance(entry, dict):
        who = entry.get("service") or entry.get("id") or "?"
        # #286: declared bound/deferred entries carry kind + series instead of a reason.
        if entry.get("series") and entry.get("kind"):
            # backlog finding 1: surface the enabling flag so a reader knows the bound series is
            # opt-in (dead until the flag is set) — not silently parsed-and-dropped.
            flag = entry.get("enabling_flag")
            suffix = f"  (requires {flag})" if flag else ""
            return f"    - {who}: {entry['kind']} → {entry['series']}{suffix}"
        reason = " ".join(str(entry.get("reason", "")).split())
        return f"    - {who}: {reason}" if reason else f"    - {who}"
    return f"    - {entry}"


def render_report(report: ComparisonReport) -> str:
    """Human-readable Tier-A report."""
    lines = ["# Observability comparison — derived vs declared (Tier A · static · $0)", ""]
    grounded = (f" — {', '.join(report.emitted)}" if report.emitted else "")
    lines.append(f"Grounded SLIs (emitted): {len(report.emitted)}{grounded}")

    # #286: base SLIs bound to a real author-declared series — a positive grounding, shown up top.
    if report.bound:
        lines += ["", f"Bound to declared emitted series (#286): {len(report.bound)}"]
        lines += [_entry_line(b) for b in report.bound]

    if not report.gaps:
        lines += ["", "No divergence: every derived SLI is grounded in the declared surface. ✓", ""]
        return "\n".join(lines)

    lines.append(
        f"Divergence: {report.total_gaps} across {len(report.gaps)} class(es) — where the derived "
        "artifacts can't be grounded against the subject's declared instrumentation:"
    )
    for key, _label in _GAP_CLASSES:
        entries = report.gaps.get(key)
        if not entries:
            continue
        lines += ["", f"  {_LABELS[key]}  [{len(entries)}]"]
        lines += [_entry_line(e) for e in entries]
    lines += [
        "",
        "Tier B (live fidelity — replay these against real telemetry to confirm empirically):",
        "  startd8 observability validate-promql --artifacts-dir <out> "
        "--onboarding-metadata <md> --prometheus <url>",
        "",
    ]
    return "\n".join(lines)
