#!/usr/bin/env python3
"""Generate observability artifacts from ContextCore onboarding metadata.

Reads onboarding-metadata.json (from cap-dev-pipe Stage 4 EXPORT) and
optionally .contextcore.yaml, then produces per-service alert rules,
dashboard specs, and SLO definitions.

Usage:
  # Generate artifacts
  python3 scripts/generate_observability_artifacts.py \\
      --onboarding-metadata pipeline-output/run-084/onboarding-metadata.json \\
      --output-dir pipeline-output/run-084/observability

  # With manifest for direct SLO reads
  python3 scripts/generate_observability_artifacts.py \\
      --onboarding-metadata pipeline-output/run-084/onboarding-metadata.json \\
      --manifest .contextcore.yaml \\
      --output-dir pipeline-output/run-084/observability

  # Drift detection
  python3 scripts/generate_observability_artifacts.py \\
      --onboarding-metadata pipeline-output/run-084/onboarding-metadata.json \\
      --output-dir pipeline-output/run-084/observability \\
      --check

  # Dry run
  python3 scripts/generate_observability_artifacts.py \\
      --onboarding-metadata pipeline-output/run-084/onboarding-metadata.json \\
      --output-dir pipeline-output/run-084/observability \\
      --dry-run

See docs/design/UNIFIED_OBSERVABILITY_MANIFEST_REQUIREMENTS.md for design.
"""

import argparse
import sys
from pathlib import Path

# Ensure src/ is importable when running from repo root
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "src"))

from startd8.observability.artifact_generator import (
    check_drift,
    generate_observability_artifacts,
    _append_to_provenance,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Generate observability artifacts (alert rules, dashboard specs, "
            "SLO definitions) from ContextCore onboarding metadata."
        )
    )
    parser.add_argument(
        "--onboarding-metadata",
        required=True,
        help="Path to onboarding-metadata.json from cap-dev-pipe Stage 4 EXPORT",
    )
    parser.add_argument(
        "--manifest",
        default=None,
        help="Path to .contextcore.yaml for direct SLO/criticality reads (optional)",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Directory for generated artifacts",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check for drift against previously generated artifacts",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be generated without writing files",
    )
    args = parser.parse_args()

    onboarding = Path(args.onboarding_metadata)
    output = Path(args.output_dir)
    manifest = Path(args.manifest) if args.manifest else None

    if args.check:
        return check_drift(onboarding, output, manifest)

    report = generate_observability_artifacts(
        onboarding_metadata_path=onboarding,
        output_dir=output,
        manifest_path=manifest,
        dry_run=args.dry_run,
    )

    # Print summary
    generated = sum(1 for a in report.artifacts if a.status == "generated")
    skipped = sum(1 for a in report.artifacts if a.status == "skipped")
    errored = sum(1 for a in report.artifacts if a.status == "error")

    print(f"Services processed: {report.services_processed}")
    print(f"Services skipped:   {report.services_skipped}")
    print(f"Artifacts: {generated} generated, {skipped} skipped, {errored} errors")

    if args.dry_run:
        print("\n[DRY RUN] No files written. Artifacts that would be generated:")
        for a in report.artifacts:
            marker = {"generated": "+", "skipped": "~", "error": "!"}[a.status]
            print(f"  {marker} {a.output_path} ({a.status})")

    # Best-effort provenance append
    if not args.dry_run and generated > 0:
        provenance_path = onboarding.parent / "run-provenance.json"
        _append_to_provenance(provenance_path, output)

    return 1 if errored > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
