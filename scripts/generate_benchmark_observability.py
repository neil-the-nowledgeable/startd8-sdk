#!/usr/bin/env python3
# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""Generate the benchmark's SRE + onboarding artifacts deterministically, $0 (P4 / FR-13).

One regenerable entry point that runs the first dogfood slice from the benchmark ContextManifest:
  - P1 execution-run dashboard (if --run-dir given)   → cc-benchmark-run-<hash>.json
  - P2 harness incident runbook                        → harness-runbook.md
  - P3 per-persona onboarding portal (4 personas)      → cc-portal-startd8-benchmark[-persona].json

Compiles via jsonnet/startd8-mixin → Grafana JSON; degrades to spec-YAML when grafonnet isn't
jb-installed (run `jb install` in startd8-mixin first). Rendering *data* needs a live Prometheus
(cost is live via startd8.cost.*; pass/fail needs the run's cell spans ingested into ContextCore).

Usage::

    python3 scripts/generate_benchmark_observability.py --out out/benchmark-obs
    python3 scripts/generate_benchmark_observability.py --run-dir <run> --out out/ --provision
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from startd8.benchmark_matrix.observability import (  # noqa: E402
    generate_run_dashboard,
    write_harness_runbook,
)
from startd8.benchmark_matrix.onboarding import generate_onboarding_portal  # noqa: E402
from startd8.benchmark_matrix.metrics_export import write_run_metrics  # noqa: E402

_DEFAULT_MANIFEST = (
    Path(__file__).resolve().parent.parent
    / "docs/design/deterministic-sre-onboarding/benchmark.contextcore.yaml"
)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--manifest", type=Path, default=_DEFAULT_MANIFEST, help="benchmark ContextManifest")
    ap.add_argument("--run-dir", type=Path, default=None, help="a finished run dir → execution dashboard")
    ap.add_argument("--out", type=Path, default=Path("./benchmark-obs-out"), help="output dir")
    ap.add_argument("--provision", action="store_true", help="provision dashboards to Grafana")
    args = ap.parse_args()

    print(f"Manifest: {args.manifest}\nOutput:   {args.out}\n")

    if args.run_dir:
        d = generate_run_dashboard(args.run_dir, args.out, provision=args.provision)
        print(f"[SRE] run dashboard: {d['uid']} ({d['mode']}, {d['panel_count']} panels)")
        mx = write_run_metrics(args.run_dir, args.out)
        print(f"[Data] {mx['series']} metric series → {mx['path']} "
              f"(Prometheus textfile; point a scraper at it to render the dashboard)")
    else:
        print("[SRE] run dashboard: skipped (no --run-dir)")

    rb = write_harness_runbook(args.manifest, args.out)
    print(f"[SRE] runbook: {rb['incident_classes']} incident classes → {rb['path']}")

    portals = generate_onboarding_portal(args.manifest, args.out, provision=args.provision)
    modes = {p["mode"] for p in portals}
    print(f"[Onboarding] {len(portals)} persona portals ({'/'.join(sorted(modes))}): "
          + ", ".join(p["uid"].split("startd8-benchmark")[-1] or "operator" for p in portals))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
