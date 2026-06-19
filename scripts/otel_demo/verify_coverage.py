#!/usr/bin/env python3
"""Tier 0 — S6 coverage verifier (FR-6).

Validates ``coverage-attestation.json`` schema (FR-5a), freshness (FR-9), then
re-runs live §4 queries. Does NOT reuse ``scripts/verify_otel_trace.py`` (Artisan/Tempo).

Exit codes:
  0  schema valid + fresh + all sections pass live re-check
  1  attestation read but one or more sections fail
  2  schema/freshness/infra error

Usage:
  python3 scripts/otel_demo/verify_coverage.py \\
      docs/design/otel-demo-corpus/coverage-attestation.json
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from scripts.otel_demo import attest_coverage  # noqa: E402
from scripts.otel_demo.coverage_sections import validate_schema_version  # noqa: E402


def _parse_ts(raw: str) -> datetime:
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    return datetime.fromisoformat(raw)


def _freshness_ok(attestation: dict[str, Any], manifest: dict[str, Any], max_age_hours: float) -> tuple[bool, str]:
    gen = attestation.get("generated_at")
    if not gen:
        return False, "missing generated_at"
    try:
        gen_dt = _parse_ts(gen)
    except ValueError as exc:
        return False, f"invalid generated_at: {exc}"

    now = datetime.now(timezone.utc)
    if gen_dt.tzinfo is None:
        gen_dt = gen_dt.replace(tzinfo=timezone.utc)
    age_h = (now - gen_dt).total_seconds() / 3600.0
    if age_h > max_age_hours:
        return False, f"attestation stale ({age_h:.1f}h > {max_age_hours}h)"

    bringup_at = manifest.get("generated_at")
    if bringup_at:
        try:
            bring_dt = _parse_ts(bringup_at)
            if bring_dt.tzinfo is None:
                bring_dt = bring_dt.replace(tzinfo=timezone.utc)
            if gen_dt < bring_dt:
                return False, "attestation older than bringup-manifest (re-run attest after bring-up)"
        except ValueError:
            pass
    return True, f"fresh ({age_h:.1f}h)"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("attestation", nargs="?", default="docs/design/otel-demo-corpus/coverage-attestation.json")
    ap.add_argument("--jaeger", default=None)
    ap.add_argument("--prometheus", default=None)
    ap.add_argument("--pyroscope", default=None)
    ap.add_argument("--workdir", default=str(_REPO / ".otel-demo"))
    ap.add_argument("--max-age-hours", type=float, default=24.0)
    ap.add_argument("--skip-live", action="store_true", help="Only validate schema + freshness")
    args = ap.parse_args(argv)

    path = Path(args.attestation)
    if not path.is_file() and not path.is_absolute():
        path = _REPO / path
    if not path.is_file():
        print(f"ERROR: attestation not found: {path}", file=sys.stderr)
        return 2

    attestation = json.loads(path.read_text(encoding="utf-8"))
    try:
        validate_schema_version(str(attestation.get("schema_version", "")))
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    manifest_path = path.parent / "bringup-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.is_file() else {}
    ok, msg = _freshness_ok(attestation, manifest, args.max_age_hours)
    if not ok:
        print(f"ERROR: freshness gate failed: {msg}", file=sys.stderr)
        return 2
    print(f"freshness: {msg}")

    if args.skip_live:
        stored_pass = all(s.get("evidence_status") == "pass" for s in attestation.get("sections", []))
        return 0 if stored_pass else 1

    backends = attestation.get("backends") or {}
    tier = attestation.get("tier", "observe")
    code = attest_coverage.main(
        [
            "--tier",
            tier,
            "--out",
            str(path.with_suffix(".verify-tmp.json")),
            "--jaeger",
            args.jaeger or backends.get("jaeger", "http://localhost:16686"),
            "--prometheus",
            args.prometheus or backends.get("prometheus", "http://localhost:9090"),
            "--pyroscope",
            args.pyroscope or backends.get("pyroscope", "http://localhost:4040"),
            "--workdir",
            args.workdir,
        ]
    )
    tmp = path.with_suffix(".verify-tmp.json")
    if tmp.is_file():
        tmp.unlink()
    return code


if __name__ == "__main__":
    sys.exit(main())
