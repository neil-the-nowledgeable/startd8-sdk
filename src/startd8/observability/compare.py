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
    #: #300 D2 (FR-10): FUNCTIONAL SLIs bound to a declared series (saturation/queue_depth/…). Kept
    #: distinct from `bound` (base RED); a generator-only key would be invisible to this report/dashboards.
    bound_functional: List[Any] = field(default_factory=list)
    #: #307: per-span RED SLIs bound to a declared span via span-metrics (real service.name). A third
    #: positive-binding lane — also dead unless consumed here (mirrors the FR-10 lesson).
    bound_span: List[Any] = field(default_factory=list)
    #: #308 P0: synthetic-probe freshness SLIs recorded PENDING a runner — a positive finding (a derived
    #: SLO the subject has no metric for), NOT a divergence. Does not count toward `total_gaps`.
    pending: List[Any] = field(default_factory=list)

    @property
    def total_gaps(self) -> int:
        return sum(len(v) for v in self.gaps.values())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "emitted": self.emitted,
            "emitted_count": len(self.emitted),
            "bound_declared_series": self.bound,
            "bound_count": len(self.bound),
            "bound_declared_functional": self.bound_functional,
            "bound_functional_count": len(self.bound_functional),
            "bound_declared_span": self.bound_span,
            "bound_span_count": len(self.bound_span),
            "pending_probes": self.pending,
            "pending_count": len(self.pending),
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
    # #300 D2 (FR-10): read the functional-binding key, else it is dead (invisible to report/dashboards).
    bound_functional = list(fr_coverage.get("bound_declared_functional") or [])
    # #307: same for the span-binding key.
    bound_span = list(fr_coverage.get("bound_declared_span") or [])
    # #308 P0: pending synthetic-probe SLIs — a positive-but-pending finding (not a gap, not in _GAP_CLASSES).
    pending = list(fr_coverage.get("pending_probes") or [])
    gaps: Dict[str, List[Any]] = {}
    for key, _label in _GAP_CLASSES:
        entries = fr_coverage.get(key) or []
        if entries:
            gaps[key] = list(entries)
    return ComparisonReport(
        emitted=emitted, gaps=gaps, bound=bound, bound_functional=bound_functional,
        bound_span=bound_span, pending=pending,
    )


def _entry_line(entry: Any) -> str:
    if isinstance(entry, dict):
        who = entry.get("service") or entry.get("id") or "?"
        # #286: declared bound/deferred entries carry kind + series instead of a reason.
        if entry.get("series") and entry.get("kind"):
            # backlog finding 1: surface the enabling flag so a reader knows the bound series is
            # opt-in (dead until the flag is set) — not silently parsed-and-dropped.
            flag = entry.get("enabling_flag")
            suffix = f"  (requires {flag})" if flag else ""
            # #300 D2 (FR-10): a threshold-deferred functional binding carries a GROUNDED query that
            # must reach the reader — the SLI is real, only its target is missing. Surface it so the
            # value FR-4 protects is not dropped at render.
            if entry.get("threshold_deferred") and entry.get("query"):
                suffix += f"  [threshold-deferred; query: {entry['query']}]"
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

    # #300 D2: functional SLIs bound to a declared series (saturation/queue_depth/…), also positive.
    if report.bound_functional:
        lines += ["", f"Bound functional SLIs on declared series (#300 D2): {len(report.bound_functional)}"]
        lines += [_entry_line(b) for b in report.bound_functional]

    # #307: per-span RED SLIs bound via span-metrics (real service.name), also positive.
    if report.bound_span:
        lines += ["", f"Bound span-metrics SLIs on declared spans (#307): {len(report.bound_span)}"]
        lines += [_entry_line(b) for b in report.bound_span]

    # #308 P0: synthetic-probe SLIs recorded PENDING a runner — a positive finding (a derived SLO the
    # subject has no metric for), shown with the bound sections, NOT under "Divergence" (R1-F10).
    if report.pending:
        lines += ["", f"Pending probes — freshness SLIs awaiting a probe runner (#308 P0): {len(report.pending)}"]
        for p in report.pending:
            if isinstance(p, dict):
                who = p.get("service", "?")
                q = p.get("query") or f"(unbindable: {p.get('reason_code', '?')})"
                td = "  [threshold-deferred]" if p.get("threshold_deferred") else ""
                lines.append(f"    - {who}: {p.get('name', '?')} ({p.get('signal_kind', '?')}) → {q}{td}")
            else:
                lines.append(f"    - {p}")

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
