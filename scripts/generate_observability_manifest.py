#!/usr/bin/env python3
"""
Drift-detection script for the observability manifest.

Compares code-derived telemetry descriptors against the committed YAML
and reports any drift (new signals not in YAML, removed signals still
listed). Exits non-zero on drift for CI integration.

Usage:
    # Check for drift (CI mode)
    python3 scripts/generate_observability_manifest.py --check

    # Show what the generator produces (debug)
    python3 scripts/generate_observability_manifest.py --show
"""

import argparse
import sys
from pathlib import Path

# Ensure the repo root is importable
_repo_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_repo_root / "src"))

COMMITTED_YAML = _repo_root / "docs" / "capability-index" / "startd8.observability.manifest.yaml"


def main() -> int:
    parser = argparse.ArgumentParser(description="Observability manifest drift detection")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check for drift between generated and committed manifest",
    )
    parser.add_argument(
        "--show",
        action="store_true",
        help="Print the generated manifest YAML to stdout",
    )
    args = parser.parse_args()

    from startd8.observability.manifest import generate_manifest, ObservabilityManifest

    generated = generate_manifest()

    if args.show:
        print(generated.to_yaml())
        return 0

    if args.check:
        if not COMMITTED_YAML.exists():
            print(f"ERROR: Committed manifest not found at {COMMITTED_YAML}")
            return 1

        committed = ObservabilityManifest.from_yaml(str(COMMITTED_YAML))
        return _check_drift(generated, committed)

    # Default: show help
    parser.print_help()
    return 0


def _check_drift(generated: "ObservabilityManifest", committed: "ObservabilityManifest") -> int:
    """Compare code-derived sections and report drift."""
    drift_found = False

    # --- Metrics ---
    gen_metric_names = {m.name for m in generated.metrics}
    com_metric_names = {m.name for m in committed.metrics}

    new_metrics = gen_metric_names - com_metric_names
    removed_metrics = com_metric_names - gen_metric_names

    if new_metrics:
        drift_found = True
        print("DRIFT: New metrics not in committed YAML:")
        for name in sorted(new_metrics):
            print(f"  + {name}")

    if removed_metrics:
        drift_found = True
        print("DRIFT: Metrics in committed YAML no longer in code:")
        for name in sorted(removed_metrics):
            print(f"  - {name}")

    # --- Spans ---
    gen_span_patterns = {s.name_pattern for s in generated.spans}
    com_span_patterns = {s.name_pattern for s in committed.spans}

    new_spans = gen_span_patterns - com_span_patterns
    removed_spans = com_span_patterns - gen_span_patterns

    if new_spans:
        drift_found = True
        print("DRIFT: New span patterns not in committed YAML:")
        for pattern in sorted(new_spans):
            print(f"  + {pattern}")

    if removed_spans:
        drift_found = True
        print("DRIFT: Span patterns in committed YAML no longer in code:")
        for pattern in sorted(removed_spans):
            print(f"  - {pattern}")

    # --- Event types ---
    gen_event_names = {e.name for e in generated.event_types}
    com_event_names = {e.name for e in committed.event_types}

    new_events = gen_event_names - com_event_names
    removed_events = com_event_names - gen_event_names

    if new_events:
        drift_found = True
        print("DRIFT: New event types not in committed YAML:")
        for name in sorted(new_events):
            print(f"  + {name}")

    if removed_events:
        drift_found = True
        print("DRIFT: Event types in committed YAML no longer in code:")
        for name in sorted(removed_events):
            print(f"  - {name}")

    # --- Summary ---
    if drift_found:
        print("\nManifest drift detected! Update the committed YAML or fix the code.")
        return 1
    else:
        print("No drift detected. Committed manifest matches code.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
