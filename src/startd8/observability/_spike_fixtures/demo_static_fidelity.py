#!/usr/bin/env python3
# SPIKE demo: run static observability-fidelity on a REAL generated observability
# tree (the bpi-astronomy Online-Boutique output) paired with fixture service
# source. Prints emitted set, referenced set, coverage, and unbound metrics per
# service, and shows the profile-mismatch case being caught with zero runtime.

from __future__ import annotations

import sys
from pathlib import Path

from startd8.observability.observability_fidelity_static import (
    extract_emitted_metrics,
    extract_referenced_metrics,
    static_fidelity,
)

HERE = Path(__file__).resolve().parent
SERVICES = HERE / "services"

# The real generated observability artifacts from the bpi-astronomy demo.
ARTIFACTS = Path(
    "/Users/neilyashinsky/Documents/Jobs/job_search_2026/roles/"
    "Sr-Solutions-Eng/Insight-Finder/demo/bpi-astronomy/out/observability"
)

# Which fixture source each generated-observability service is checked against.
# transports=None → sniff from source; explicit override shown where useful.
PAIRS = {
    "checkoutservice": SERVICES / "checkoutservice",          # Go, semconv-grpc
    "paymentservice": SERVICES / "paymentservice-python",     # Python, span-metrics + http
    "adservice": SERVICES / "adservice-node",                 # Node, semconv-grpc
}


def _fmt(names) -> str:
    return "{" + ", ".join(sorted(names)) + "}" if names else "{}"


def main() -> int:
    if not ARTIFACTS.is_dir():
        print(f"ERROR: artifacts dir not found: {ARTIFACTS}", file=sys.stderr)
        return 3

    referenced_by_service = extract_referenced_metrics(ARTIFACTS)

    print("=" * 78)
    print("STATIC OBSERVABILITY-FIDELITY — SPIKE DEMO (zero runtime)")
    print("=" * 78)
    print(f"Artifacts (referenced side): {ARTIFACTS}")
    print(f"Services in artifact tree:   {len(referenced_by_service)}")
    print()

    exit_code = 0
    for service, source_dir in PAIRS.items():
        referenced = referenced_by_service.get(service, set())
        emitted = extract_emitted_metrics(source_dir)
        result = static_fidelity(emitted, referenced)

        print("-" * 78)
        print(f"SERVICE: {service}")
        print(f"  source:      {source_dir.name}")
        print(f"  EMITTED    ({result['emitted_count']}): {_fmt(emitted)}")
        print(f"  REFERENCED ({result['referenced_count']}): {_fmt(referenced)}")
        print(f"  bound:       {_fmt(result['bound'])}")
        print(f"  UNBOUND:     {_fmt(result['unbound'])}")
        print(f"  coverage:    {result['coverage']}   VERDICT: {result['verdict'].upper()}")
        if result["verdict"] in ("fail", "partial"):
            exit_code = 2
        print()

    # Explicit demonstration of the transport-override path: check the SAME real
    # checkoutservice alerts against a source that we FORCE to look span-metrics
    # (i.e. the "matching profile" world) — coverage should jump.
    print("=" * 78)
    print("CONTROL: checkoutservice alerts vs a source that DOES emit calls_total")
    print("=" * 78)
    referenced = referenced_by_service.get("checkoutservice", set())
    # paymentservice-python fixture emits calls_total + duration_milliseconds.
    emitted_matching = extract_emitted_metrics(SERVICES / "paymentservice-python")
    result = static_fidelity(emitted_matching, referenced)
    print(f"  REFERENCED: {_fmt(referenced)}")
    print(f"  EMITTED:    {_fmt(emitted_matching)}")
    print(f"  UNBOUND:    {_fmt(result['unbound'])}")
    print(f"  coverage:   {result['coverage']}   VERDICT: {result['verdict'].upper()}")
    print()
    print("Interpretation: same generated alerts, two service instrumentations.")
    print("The mismatch (rpc_server_duration service vs calls_total alerts) is a")
    print("binding failure caught with NO Prometheus, NO running service.")

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
