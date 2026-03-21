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
import json
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

    # Quality summary (REQ-KZ-OBS-730c)
    scored = [a for a in report.artifacts if a.quality]
    if scored:
        scores_by_type: dict = {}
        for a in scored:
            scores_by_type.setdefault(a.artifact_type, []).append(a.quality["score"])

        print(f"\n  Quality scores:")
        for atype, scores in sorted(scores_by_type.items()):
            avg = sum(scores) / len(scores)
            print(f"    {atype}: {avg:.0%} avg ({len(scores)} artifacts)")

        all_scores = [a.quality["score"] for a in scored]
        composite = sum(all_scores) / len(all_scores)
        total_issues = sum(len(a.quality.get("issues", [])) for a in scored)
        total_repairs = sum(len(a.quality.get("repairs_applied", [])) for a in scored)
        print(f"    composite: {composite:.0%}")
        print(f"    issues: {total_issues}, repairs applied: {total_repairs}")

    # Write kaizen-metrics.json observability section (REQ-KZ-OBS-500)
    if not args.dry_run and scored:
        _write_quality_to_kaizen_metrics(output, scored)

    if args.dry_run:
        print("\n[DRY RUN] No files written. Artifacts that would be generated:")
        for a in report.artifacts:
            marker = {"generated": "+", "skipped": "~", "error": "!"}[a.status]
            score_str = f" score={a.quality['score']:.0%}" if a.quality else ""
            print(f"  {marker} {a.output_path} ({a.status}{score_str})")

    # Best-effort provenance append
    if not args.dry_run and generated > 0:
        provenance_path = onboarding.parent / "run-provenance.json"
        _append_to_provenance(provenance_path, output)

    return 1 if errored > 0 else 0


def _write_quality_to_kaizen_metrics(
    output_dir: Path,
    scored_artifacts: list,
) -> None:
    """Append observability_artifacts section to kaizen-metrics.json (REQ-KZ-OBS-500)."""
    # Find kaizen-metrics.json — look in parent dirs (plan-ingestion level)
    candidates = [
        output_dir.parent / "kaizen-metrics.json",
        output_dir.parent.parent / "kaizen-metrics.json",
        output_dir / "kaizen-metrics.json",
    ]
    metrics_path = None
    for c in candidates:
        if c.is_file():
            metrics_path = c
            break

    if metrics_path is None:
        # Write alongside artifacts
        metrics_path = output_dir / "observability-quality.json"

    # Load existing
    existing: dict = {}
    if metrics_path.is_file() and metrics_path.suffix == ".json":
        try:
            existing = json.loads(metrics_path.read_text())
        except (json.JSONDecodeError, OSError):
            pass

    # Build observability section
    scores_by_type: dict = {}
    for a in scored_artifacts:
        scores_by_type.setdefault(a.artifact_type, []).append(a.quality["score"])

    obs_section: dict = {
        "artifacts_scored": len(scored_artifacts),
        "total_issues": sum(len(a.quality.get("issues", [])) for a in scored_artifacts),
        "total_repairs": sum(len(a.quality.get("repairs_applied", [])) for a in scored_artifacts),
    }
    for atype, scores in scores_by_type.items():
        obs_section[f"avg_{atype}_score"] = round(sum(scores) / len(scores), 4)

    all_scores = [a.quality["score"] for a in scored_artifacts]
    obs_section["avg_composite_score"] = round(sum(all_scores) / len(all_scores), 4)

    existing["observability_artifacts"] = obs_section

    try:
        metrics_path.write_text(json.dumps(existing, indent=2) + "\n")
        print(f"  Quality metrics: {metrics_path}")
    except OSError as exc:
        print(f"  WARNING: Failed to write quality metrics: {exc}")


if __name__ == "__main__":
    sys.exit(main())
