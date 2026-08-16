"""Unify Tier-1 coverage + Tier-2 precision into one per-domain view.

Coverage says *does this repo touch §5 domain X?* (imports). Precision says *which operations?*
(contract IDLs). This joins them on the semconv_domain so one report answers both — e.g.
"http: covered (55 files import http libs) → 192 precise endpoints (from openapi.yml)".

Join key: the coverage report already carries ``pattern_domains`` ({pattern_id: semconv_domain}).
Precision is keyed on domain directly. Four states per domain make the picture honest:

  covered+precise  — touches it AND its IDL enumerates the operations (full picture)
  covered-only     — touches it (imports) but no contract IDL in the repo → coverage-only
  precise-only     — has an IDL but no source imports it (spec-only, or coverage corpus is a subset)
  absent           — neither

Pattern: dev-os/LANGUAGE-DOMAIN-COVERAGE-MAP.md (§ three-tier stack).
"""

from __future__ import annotations

from typing import Any


def _pattern_total(report: dict[str, Any], pid: str) -> int:
    """Per-pattern file count — handles the flat (Go/Node) and signal-split (Java) report shapes."""
    flat = report.get("per_pattern_file_counts") or {}
    if pid in flat:
        return flat[pid]
    sig = report.get("per_pattern_signal_counts") or {}
    if pid in sig:
        return sum(sig[pid].values())
    return 0


def unify(coverage_report: dict[str, Any], precision_by_domain: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Join a coverage report with per-domain precision results → one per-domain view."""
    pattern_domains: dict[str, str] = coverage_report.get("pattern_domains") or {}
    detected = set(coverage_report.get("detected") or [])

    domains: dict[str, Any] = {}
    all_domains = set(pattern_domains.values()) | set(precision_by_domain)
    for dom in sorted(all_domains):
        dom_patterns = [pid for pid, d in pattern_domains.items() if d == dom]
        covered = any(pid in detected for pid in dom_patterns)
        coverage_files = sum(_pattern_total(coverage_report, pid) for pid in dom_patterns if pid in detected)

        prec = precision_by_domain.get(dom) or {}
        precision_available = bool(prec.get("precision_available"))
        precise_operations = int(prec.get("total_operations", 0))
        idl_files = [f["path"] for f in (prec.get("idl_files") or [])]
        idl_type = prec.get("idl_type")

        if covered and precision_available:
            state = "covered+precise"
        elif covered:
            state = "covered-only"
        elif precision_available:
            state = "precise-only"
        else:
            state = "absent"

        domains[dom] = {
            "state": state,
            "covered": covered,
            "coverage_files": coverage_files,
            "precision_available": precision_available,
            "precise_operations": precise_operations,
            "idl_type": idl_type,
            "idl_files": idl_files,
        }

    states = [d["state"] for d in domains.values()]
    return {
        "domains": domains,
        "summary": {
            "covered_and_precise": states.count("covered+precise"),
            "covered_only": states.count("covered-only"),
            "precise_only": states.count("precise-only"),
        },
    }
