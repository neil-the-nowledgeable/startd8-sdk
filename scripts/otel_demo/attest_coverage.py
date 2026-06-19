#!/usr/bin/env python3
"""Tier 0 — S5 coverage attestation (FR-5).

Runs the §4 acceptance queries against live demo backends and writes
``coverage-attestation.json``. Stdlib only.

Exit codes:
  0  all sections passed
  1  one or more sections below threshold (attestation still written)
  2  infrastructure error (backend unreachable / workdir missing)

Usage:
  python3 scripts/otel_demo/attest_coverage.py \\
      --tier observe \\
      --out docs/design/otel-demo-corpus/coverage-attestation.json
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from scripts.otel_demo.adapters import collector, jaeger, prometheus, pyroscope  # noqa: E402
from scripts.otel_demo.coverage_sections import (  # noqa: E402
    SCHEMA_VERSION,
    CoverageSection,
    default_sections,
)


def _run_section(
    section: CoverageSection,
    *,
    jaeger_base: str,
    prom_base: str,
    pyro_base: str,
    workdir: Path,
) -> dict[str, Any]:
    params = section.params
    try:
        if section.check_type == "jaeger_services_with_traces":
            result = jaeger.services_with_traces(
                jaeger_base, lookback=section.window, min_count=section.threshold
            )
        elif section.check_type == "jaeger_distinct_process_tag":
            result = jaeger.distinct_process_tag(
                jaeger_base,
                tag_key=params["tag_key"],
                lookback=section.window,
                min_count=section.threshold,
            )
        elif section.check_type == "jaeger_span_tag":
            result = jaeger.span_tag_count(
                jaeger_base,
                tag_key=params["tag_key"],
                tag_value=params.get("tag_value"),
                lookback=section.window,
                min_count=section.threshold,
            )
        elif section.check_type == "jaeger_span_tag_any":
            result = jaeger.span_tag_count(
                jaeger_base,
                tag_key=params["tag_key"],
                tag_values=params.get("tag_values"),
                lookback=section.window,
                min_count=section.threshold,
            )
        elif section.check_type == "jaeger_messaging_kafka":
            result = jaeger.messaging_kafka_count(
                jaeger_base,
                lookback=section.window,
                min_count=section.threshold,
                messaging_key=params.get("messaging_key", "messaging.system"),
                messaging_value=params.get("messaging_value", "kafka"),
            )
        elif section.check_type == "prometheus_metric_patterns":
            result = prometheus.count_matching_patterns(
                prom_base, params["patterns"], min_count=section.threshold
            )
        elif section.check_type == "collector_otlp_receivers":
            result = collector.check_otlp_receivers(
                workdir, required=params.get("required", ["grpc", "http"])
            )
        elif section.check_type == "pyroscope_apps":
            result = pyroscope.count_profile_apps(pyro_base, min_count=section.threshold)
        else:
            result = {
                "observed": 0,
                "passed": False,
                "detail": f"unknown check_type {section.check_type}",
                "observed_names": [],
            }
    except (urllib.error.URLError, OSError, json.JSONDecodeError) as exc:
        result = {
            "observed": 0,
            "passed": False,
            "detail": f"backend error: {exc}",
            "observed_names": [],
            "error": str(exc),
        }

    observed_names = params.get("observed_names") or []
    from_result = result.get("observed_names") or []
    if from_result:
        observed_names = sorted(set(observed_names) | set(from_result))
    row: dict[str, Any] = {
        "section_id": section.section_id,
        "landscape_ref": section.landscape_ref,
        "signal": section.signal,
        "backend": section.backend,
        "query": section.query,
        "threshold": section.threshold,
        "window": section.window,
        "observed": result.get("observed", 0),
        "evidence_status": "pass" if result.get("passed") else "fail",
        "detail": result.get("detail", ""),
        "observed_names": list(observed_names),
    }
    if result.get("error"):
        row["error"] = result["error"]
    return row


def _load_manifest(out_dir: Path) -> dict[str, Any]:
    path = out_dir / "bringup-manifest.json"
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--jaeger", default="http://localhost:16686")
    ap.add_argument("--prometheus", default="http://localhost:9090")
    ap.add_argument("--pyroscope", default="http://localhost:4040")
    ap.add_argument(
        "--workdir",
        default=str(_REPO / ".otel-demo"),
        help="Pinned OTel Demo clone (for collector static parse)",
    )
    ap.add_argument("--tier", default="observe", choices=("core", "observe", "profile"))
    ap.add_argument(
        "--out",
        default=str(_REPO / "docs/design/otel-demo-corpus/coverage-attestation.json"),
    )
    args = ap.parse_args(argv)

    workdir = Path(args.workdir)
    if not workdir.is_dir() and args.tier != "core":
        print(f"ERROR: workdir {workdir} missing — run bring_up.sh first", file=sys.stderr)
        return 2

    sections = default_sections(include_profiles=(args.tier == "profile"))
    out_dir = Path(args.out).parent
    manifest = _load_manifest(out_dir)

    rows: list[dict[str, Any]] = []
    infra_errors = 0
    for section in sections:
        if section.tier_required and section.tier_required != args.tier:
            continue
        row = _run_section(
            section,
            jaeger_base=args.jaeger,
            prom_base=args.prometheus,
            pyro_base=args.pyroscope,
            workdir=workdir,
        )
        rows.append(row)
        if "error" in row:
            infra_errors += 1

    all_pass = all(r["evidence_status"] == "pass" for r in rows)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    attestation = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": now,
        "demo_ref": manifest.get("demo_ref", "unknown"),
        "git_sha": manifest.get("git_sha", "unknown"),
        "tier": args.tier,
        "backends": {
            "jaeger": args.jaeger,
            "prometheus": args.prometheus,
            "pyroscope": args.pyroscope,
        },
        "sections": rows,
        "summary": {
            "total": len(rows),
            "passed": sum(1 for r in rows if r["evidence_status"] == "pass"),
            "failed": sum(1 for r in rows if r["evidence_status"] != "pass"),
        },
    }

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(attestation, fh, indent=2, sort_keys=True)
        fh.write("\n")

    print(f"wrote {out_path}  passed={attestation['summary']['passed']}/{attestation['summary']['total']}")
    for row in rows:
        mark = "OK" if row["evidence_status"] == "pass" else "FAIL"
        print(f"  [{mark}] {row['section_id']}: {row['detail']}")

    if infra_errors and not rows:
        return 2
    if infra_errors and not any(r["evidence_status"] == "pass" for r in rows):
        return 2
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
