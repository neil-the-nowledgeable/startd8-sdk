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
    parser.add_argument(
        "--portal",
        action="store_true",
        help="Generate onboarding portal Grafana dashboard (opt-in, REQ-OBP-103d)",
    )
    parser.add_argument(
        "--portal-persona",
        default="operator",
        choices=["operator", "engineer", "manager", "all"],
        help="Portal persona variant (default: operator)",
    )
    parser.add_argument(
        "--portal-provision",
        default=None,
        metavar="URL",
        help="Provision portal to Grafana at URL (e.g. http://localhost:3000)",
    )
    parser.add_argument(
        "--min-metric-coverage",
        type=float,
        default=None,
        metavar="FRACTION",
        help=(
            "Fail (non-zero exit) when the average semantic metric-coverage "
            "score is below this fraction (0.0-1.0). Opt-in; unset = no gate."
        ),
    )
    parser.add_argument(
        "--min-artifact-type-coverage",
        type=float,
        default=None,
        metavar="FRACTION",
        help=(
            "Fail (non-zero exit) when artifact-type coverage (declared types "
            "produced / declared) is below this fraction. Opt-in; unset = no gate."
        ),
    )
    args = parser.parse_args()

    onboarding = Path(args.onboarding_metadata)
    output = Path(args.output_dir)
    manifest = Path(args.manifest) if args.manifest else None

    if args.check:
        return check_drift(onboarding, output, manifest)

    # Handle --portal-persona all: generate one run per persona
    if args.portal and args.portal_persona == "all":
        # Generate base artifacts once, then add each persona portal
        report = generate_observability_artifacts(
            onboarding_metadata_path=onboarding,
            output_dir=output,
            manifest_path=manifest,
            dry_run=args.dry_run,
            portal=False,  # We'll generate portals individually below
        )
        for persona in ("operator", "engineer", "manager"):
            from startd8.observability.artifact_generator import _generate_portal_artifact
            from startd8.observability.artifact_generator import (
                load_onboarding_metadata,
                extract_service_hints,
                load_business_context,
            )
            metadata = load_onboarding_metadata(onboarding)
            services = extract_service_hints(metadata)
            business = load_business_context(manifest, metadata)
            result = _generate_portal_artifact(
                business, services, report, metadata, output,
                persona=persona,
                provision_url=args.portal_provision,
                dry_run=args.dry_run,
            )
            if result is not None:
                report.artifacts.append(result)
                if result.status == "generated" and result.content and not args.dry_run:
                    dest = output / result.output_path
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_text(result.content)
    else:
        report = generate_observability_artifacts(
            onboarding_metadata_path=onboarding,
            output_dir=output,
            manifest_path=manifest,
            dry_run=args.dry_run,
            portal=args.portal,
            portal_persona=args.portal_persona,
            portal_provision_url=args.portal_provision,
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

    # REQ-OPI-500: Dashboard spec → /dbrd-cr8r handoff details
    dashboards = [
        a for a in report.artifacts
        if a.artifact_type == "dashboard_spec" and a.status == "generated"
    ]
    if dashboards and not args.dry_run:
        print(f"\n  ┌─────────────────────────────────────────────────────────┐")
        print(f"  │  Dashboard Specs Ready for Grafana Compilation          │")
        print(f"  ├─────────────────────────────────────────────────────────┤")
        for d in dashboards:
            spec_path = output / d.output_path
            score_str = f" (quality: {d.quality['score']:.0%})" if d.quality else ""
            print(f"  │  {d.service_id}{score_str}")
            print(f"  │    spec: {spec_path}")
        print(f"  ├─────────────────────────────────────────────────────────┤")
        print(f"  │  To compile to Grafana JSON:                            │")
        print(f"  │    /dbrd-cr8r --spec <path>                             │")
        print(f"  │                                                         │")
        print(f"  │  To compile + provision to Grafana:                     │")
        print(f"  │    /dbrd-cr8r --spec <path> --provision                 │")
        print(f"  │                                                         │")
        print(f"  │  Pipeline: DashboardSpec YAML → Jsonnet → Grafana JSON  │")
        print(f"  │  Requires: jsonnet toolchain (go-jsonnet or jsonnet)     │")
        print(f"  └─────────────────────────────────────────────────────────┘")

    # Best-effort provenance append
    if not args.dry_run and generated > 0:
        provenance_path = onboarding.parent / "run-provenance.json"
        _append_to_provenance(provenance_path, output)

    # Coverage gate (opt-in): fail the run when semantic coverage is too thin.
    gate_failed = _apply_coverage_gate(args, output)

    return 1 if (errored > 0 or gate_failed) else 0


def _apply_coverage_gate(args, output: Path) -> bool:
    """Evaluate the opt-in coverage gate; returns True if the gate FAILED.

    Reads the average metric-coverage from observability-quality.json and the
    artifact-type coverage from observability-manifest.yaml, then checks them
    against the --min-*-coverage thresholds. No thresholds set → no gate.
    """
    if args.min_metric_coverage is None and args.min_artifact_type_coverage is None:
        return False

    if args.dry_run:
        print("\n[coverage gate] skipped in --dry-run (no quality report written)")
        return False

    from startd8.validators.observability_artifact_checks import evaluate_coverage_gate

    metric_coverage = None
    quality_path = output / "observability-quality.json"
    if quality_path.is_file():
        try:
            quality = json.loads(quality_path.read_text())
            metric_coverage = quality.get("aggregate", {}).get("avg_metric_coverage_score")
        except (ValueError, OSError):
            pass

    artifact_type_coverage = None
    manifest_path = output / "observability-manifest.yaml"
    if manifest_path.is_file():
        try:
            import yaml

            idx = yaml.safe_load(manifest_path.read_text()) or {}
            artifact_type_coverage = idx.get("summary", {}).get("artifact_type_coverage")
        except (ValueError, OSError):
            pass

    result = evaluate_coverage_gate(
        metric_coverage=metric_coverage,
        artifact_type_coverage=artifact_type_coverage,
        min_metric_coverage=args.min_metric_coverage,
        min_artifact_type_coverage=args.min_artifact_type_coverage,
    )

    if result.passed:
        print("\n[coverage gate] PASS")
    else:
        print("\n[coverage gate] FAIL")
        for failure in result.failures:
            print(f"  - {failure}")
    return not result.passed


def _write_quality_to_kaizen_metrics(
    output_dir: Path,
    scored_artifacts: list,
) -> None:
    """Append observability_artifacts section to kaizen-metrics.json (REQ-KZ-OBS-500).

    Includes per-type averages, per-service triplet evaluation (REQ-KZ-OBS-501),
    and cross-artifact consistency issues (REQ-KZ-OBS-400–403).
    """
    # Find kaizen-metrics.json — look in sibling and parent dirs.
    # Standard pipeline layout: run-NNN/plan-ingestion/kaizen-metrics.json
    # Observability output:     run-NNN/observability/
    candidates = [
        output_dir.parent / "plan-ingestion" / "kaizen-metrics.json",
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

    # Per-service triplet evaluation (REQ-KZ-OBS-501)
    services: dict = {}
    for a in scored_artifacts:
        svc = services.setdefault(a.service_id, {})
        svc[a.artifact_type] = a.quality["score"]
        svc.setdefault("issues", []).extend(a.quality.get("issues", []))
        svc["content_" + a.artifact_type] = getattr(a, "content", "")

    service_evaluations = []
    for svc_id, svc_data in services.items():
        dash_score = svc_data.get("dashboard_spec", 0.0)
        alert_score = svc_data.get("alert_rule", 0.0)
        slo_score = svc_data.get("slo_definition", 0.0)

        try:
            from startd8.validators.observability_artifact_checks import (
                compute_service_composite,
            )
            composite = compute_service_composite(dash_score, alert_score, slo_score)
        except ImportError:
            composite = (dash_score * 0.35) + (alert_score * 0.35) + (slo_score * 0.30)

        eval_entry = {
            "service_id": svc_id,
            "dashboard_score": round(dash_score, 4),
            "alert_score": round(alert_score, 4),
            "slo_score": round(slo_score, 4),
            "composite_score": round(composite, 4),
            "issues": svc_data.get("issues", []),
        }

        # Cross-artifact consistency (REQ-KZ-OBS-400–403)
        try:
            from startd8.validators.observability_artifact_checks import (
                validate_cross_artifact_consistency,
            )
            cross = validate_cross_artifact_consistency(
                dashboard_content=svc_data.get("content_dashboard_spec"),
                alert_content=svc_data.get("content_alert_rule"),
                slo_content=svc_data.get("content_slo_definition"),
                service_id=svc_id,
            )
            eval_entry["cross_artifact_issues"] = cross.to_dict()
        except ImportError:
            eval_entry["cross_artifact_issues"] = {}

        service_evaluations.append(eval_entry)

    obs_section["services_evaluated"] = len(services)
    complete = sum(
        1 for s in services.values()
        if all(k in s for k in ("dashboard_spec", "alert_rule", "slo_definition"))
    )
    obs_section["services_with_complete_triplet"] = complete
    obs_section["service_evaluations"] = service_evaluations

    # Aggregate cross-artifact issues
    cross_totals = {
        "unvisualized_alerts": 0,
        "unalerted_slos": 0,
        "misaligned_thresholds": 0,
        "unused_derivations": 0,
    }
    for ev in service_evaluations:
        for key in cross_totals:
            cross_totals[key] += ev.get("cross_artifact_issues", {}).get(key, 0)
    obs_section["cross_artifact_issues"] = cross_totals

    existing["observability_artifacts"] = obs_section

    try:
        metrics_path.write_text(json.dumps(existing, indent=2) + "\n")
        print(f"  Quality metrics: {metrics_path}")
    except OSError as exc:
        print(f"  WARNING: Failed to write quality metrics: {exc}")


if __name__ == "__main__":
    sys.exit(main())
