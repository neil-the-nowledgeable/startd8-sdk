# Copyright 2026 startd8
"""$0 read-only preflight for onboarding-metadata (CEP CH-4).

Lints an ``onboarding-metadata.json`` against the SDK consumer contract *before* a generation pass, so
an author learns — up front, without spending a run — which fields are present vs silently defaulted,
which keys are typos of known keys (did-you-mean), and which present values are malformed and would be
silently dropped. Pure read-only: it loads + inspects, never generates or writes.

The known-key sets mirror what ``extract_service_hints`` / ``load_business_context`` actually read; keep
them in sync when the consumer gains a field (a CH-3 single-sourced key manifest would remove this
duplication — tracked in the contract-health backlog).
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List

from .artifact_generator_context import load_onboarding_metadata

# Keys the consumer recognizes at each level (grounded in artifact_generator_context.py).
_KNOWN_DOC_KEYS = frozenset(
    {"project_id", "schema_version", "instrumentation_hints", "artifact_types", "_note",
     "owned_elsewhere", "owned_elsewhere_types"}
)
_KNOWN_HINT_KEYS = frozenset(
    {"service_id", "service_name", "kind", "transport", "metrics_surface", "traces",
     "language", "detected_databases", "datasources", "business", "metrics"}
)
_KNOWN_METRICS_KEYS = frozenset(
    {"convention_based", "manifest_declared", "declared_emitted_series", "declared_span_signals",
     "declared_probes", "convention_profile", "descriptor_overrides"}
)
# Hint-level dict-typed fields that isinstance-guard to {} in the consumer (a non-dict is silently dropped).
_DICT_TYPED_HINT_KEYS = ("datasources", "business")
_DICT_TYPED_METRICS_KEYS = ("descriptor_overrides",)


@dataclass
class Finding:
    level: str            # "error" | "warning" | "info"
    where: str            # e.g. "instrumentation_hints.web" / "instrumentation_hints.web.metrics"
    message: str


@dataclass
class ValidationReport:
    path: str
    findings: List[Finding] = field(default_factory=list)

    @property
    def errors(self) -> List[Finding]:
        return [f for f in self.findings if f.level == "error"]

    @property
    def warnings(self) -> List[Finding]:
        return [f for f in self.findings if f.level == "warning"]

    @property
    def ok(self) -> bool:
        # exit non-zero when there is anything an author should act on (errors + typos/malformed warnings).
        return not self.errors and not self.warnings

    def to_dict(self) -> Dict[str, Any]:
        return {
            "path": self.path,
            "ok": self.ok,
            "counts": {
                "error": len(self.errors),
                "warning": len(self.warnings),
                "info": len([f for f in self.findings if f.level == "info"]),
            },
            "findings": [{"level": f.level, "where": f.where, "message": f.message} for f in self.findings],
        }


def _did_you_mean(key: str, known: frozenset) -> str:
    hit = difflib.get_close_matches(key, known, n=1, cutoff=0.7)
    return f" — did you mean '{hit[0]}'?" if hit else ""


def _check_unknown_keys(obj: Dict[str, Any], known: frozenset, where: str, out: List[Finding]) -> None:
    for k in obj:
        if k not in known:
            out.append(Finding("warning", where, f"unrecognized key '{k}'{_did_you_mean(k, known)}"))


def validate_onboarding_metadata(path: Path) -> ValidationReport:
    """Load + lint onboarding-metadata; return a ValidationReport (never raises on content problems —
    a malformed doc is reported as an error finding, not an exception)."""
    report = ValidationReport(path=str(path))
    try:
        data = load_onboarding_metadata(path)  # FileNotFoundError propagates; bad JSON → ValueError below
    except FileNotFoundError as e:
        report.findings.append(Finding("error", str(path), str(e)))
        return report
    except ValueError as e:
        report.findings.append(Finding("error", str(path), str(e)))
        return report

    if not isinstance(data, dict):
        report.findings.append(Finding("error", str(path), f"top-level JSON is {type(data).__name__}, expected an object"))
        return report

    _check_unknown_keys(data, _KNOWN_DOC_KEYS, str(path), report.findings)

    hints = data.get("instrumentation_hints")
    if not isinstance(hints, dict) or not hints:
        report.findings.append(
            Finding("error", str(path), "no instrumentation_hints object — zero services would be generated")
        )
        return report

    for svc_id, hint in hints.items():
        where = f"instrumentation_hints.{svc_id}"
        if not isinstance(hint, dict):
            report.findings.append(
                Finding("error", where, f"hint is {type(hint).__name__}, expected an object — this service is skipped")
            )
            continue

        _check_unknown_keys(hint, _KNOWN_HINT_KEYS, where, report.findings)

        # present-vs-defaulted (informational): the load-bearing fields that silently default.
        if not (hint.get("transport") or hint.get("kind")):
            report.findings.append(
                Finding("warning", where, "neither 'transport' nor 'kind' present — service is DROPPED by extract_service_hints")
            )
        if not hint.get("service_name"):
            report.findings.append(
                Finding("info", where, "no 'service_name' — SLI label falls back to the sanitized service id (may not match telemetry)")
            )
        if not hint.get("metrics_surface"):
            report.findings.append(
                Finding("info", where, "no 'metrics_surface' — emission-surface gating (#274/#285) is not applied")
            )

        # malformed dict-typed fields (present but wrong shape → silently dropped by the consumer).
        for k in _DICT_TYPED_HINT_KEYS:
            if k in hint and not isinstance(hint[k], dict):
                report.findings.append(
                    Finding("warning", where, f"'{k}' is {type(hint[k]).__name__}, expected an object — silently dropped by the consumer")
                )

        metrics = hint.get("metrics")
        if metrics is not None and not isinstance(metrics, dict):
            report.findings.append(
                Finding("warning", where, f"'metrics' is {type(metrics).__name__}, expected an object — all declared series/signals ignored")
            )
        elif isinstance(metrics, dict):
            mwhere = f"{where}.metrics"
            _check_unknown_keys(metrics, _KNOWN_METRICS_KEYS, mwhere, report.findings)
            for k in _DICT_TYPED_METRICS_KEYS:
                if k in metrics and not isinstance(metrics[k], dict):
                    report.findings.append(
                        Finding("warning", mwhere, f"'{k}' is {type(metrics[k]).__name__}, expected an object — silently dropped")
                    )

    return report


def render_report(report: ValidationReport) -> str:
    """A compact human-readable rendering of the report."""
    lines = [f"onboarding-metadata: {report.path}"]
    if not report.findings:
        lines.append("  ✅ no issues — every consumed field is present and well-formed.")
        return "\n".join(lines)
    icon = {"error": "❌", "warning": "⚠️ ", "info": "ℹ️ "}
    for f in report.findings:
        lines.append(f"  {icon.get(f.level, '  ')} [{f.where}] {f.message}")
    c = report.to_dict()["counts"]
    verdict = "✅ OK" if report.ok else "❌ issues found"
    lines.append(f"  {verdict} — {c['error']} error(s), {c['warning']} warning(s), {c['info']} info.")
    return "\n".join(lines)
