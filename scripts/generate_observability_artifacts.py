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

from startd8.observability.affordance_map_consume import (
    EXIT_ALL_SKIPPED,
    EXIT_MALFORMED,
    EXIT_OK,
    apply_affordance_actions,
    exit_code_for_apply,
    exit_code_for_plan,
    format_plan_for_dry_run,
    load_affordance_map,
    merge_and_write_reports,
    merge_needed_where_into_entries,
    plan_affordance_actions,
    write_affordance_actions_report,
    write_apply_actions_report,
)
from startd8.observability.artifact_generator import (
    check_drift,
    extract_service_hints,
    generate_observability_artifacts,
    load_business_context,
    load_onboarding_metadata,
    _append_to_provenance,
)
from startd8.observability.metric_descriptor import resolve_descriptor


def _run_affordance_map_mode(args, onboarding: Path, output: Path) -> int:
    """AffordanceMap mode: plan (dry-run) or targeted apply + merge (WP-B1)."""
    load = load_affordance_map(Path(args.affordance_map))
    if load.error:
        print(f"error: AffordanceMap {load.error}", file=sys.stderr)
        return EXIT_MALFORMED

    if getattr(args, "needed_where", None):
        load.entries = merge_needed_where_into_entries(
            load.entries, Path(args.needed_where)
        )

    if load.source_truncated:
        print(
            "warning: AffordanceMap appears history-truncated "
            "(source_truncated=true); repairs may be incomplete.",
            file=sys.stderr,
        )

    metadata = load_onboarding_metadata(onboarding)
    services = extract_service_hints(metadata)
    known_ids = [s.service_id for s in services]
    manifest = Path(args.manifest) if args.manifest else None
    business = load_business_context(manifest, metadata)

    service_filter = None
    empty_intersection = False
    if args.services:
        service_filter = [s.strip() for s in args.services.split(",") if s.strip()]
        if not set(service_filter) & set(known_ids):
            empty_intersection = True

    plan = plan_affordance_actions(
        load.entries,
        known_ids,
        service_filter=service_filter,
    )
    if service_filter is not None and not plan.actions and not plan.skips:
        empty_intersection = True

    print(format_plan_for_dry_run(plan))
    if load.source_truncated:
        print("  note: source_truncated=true")

    if args.dry_run:
        print("\n[DRY RUN] AffordanceMap mode — no artifact files written.")
        return exit_code_for_plan(
            load, plan, empty_intersection=empty_intersection
        )

    if empty_intersection:
        write_affordance_actions_report(
            output, plan=plan, load=load, dry_run=False
        )
        return EXIT_OK

    descriptors = {
        s.service_id: resolve_descriptor(
            profile=s.metric_profile or None,
            kinds=s.kinds,
            transport=s.transport,
            overrides=s.descriptor_overrides,
        )
        for s in services
    }
    apply = apply_affordance_actions(
        plan,
        services=services,
        business=business,
        output_dir=output,
        descriptors=descriptors,
        contracts=metadata.get("expected_output_contracts") or {},
    )
    merge_and_write_reports(output, apply)
    write_apply_actions_report(output, load=load, apply=apply)
    print(
        f"Applied: "
        f"{sum(1 for e in apply.entries if e.outcome.value == 'applied')} "
        f"changed, "
        f"{sum(1 for e in apply.entries if e.outcome.value == 'applied_no_change')} "
        f"no-change, "
        f"{sum(1 for e in apply.entries if e.outcome.value == 'skipped')} skipped"
    )
    print(f"Wrote {output / 'affordance_actions.json'}")
    return exit_code_for_apply(load, apply)


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
        "--observability-yaml",
        default=None,
        metavar="PATH",
        help=(
            "Path to an authored observability.yaml (FR-H5). ADDITIVE + opt-in: when "
            "present, its alerting.metric_thresholds / service_levels render EXTRA domain "
            "alert + dashboard artifacts; absent = no new artifact (never overrides the "
            "manifest). Closes the doc-vs-mechanism gap where authored thresholds were "
            "silently dropped because this flag was never wired."
        ),
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
        "--provision",
        default=None,
        metavar="URL",
        help=(
            "Provision per-service dashboards to Grafana at URL (idempotent upsert "
            "by uid; auth via GRAFANA_API_TOKEN). Warn-don't-fail. Opt-in."
        ),
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
    parser.add_argument(
        "--affordance-map",
        default=None,
        metavar="PATH",
        help=(
            "Optional AffordanceMap JSON (slim array or scorecard-json with "
            "affordance_map). Enables targeted gen.* repair mode (REQ Affordance-Map "
            "Consume). Replaces full-tree generate when present."
        ),
    )
    parser.add_argument(
        "--affordance-map-export",
        default=None,
        metavar="PATH",
        help=(
            "Optional AffordanceMap JSON used ONLY to widen the metric-coverage "
            "expected set (product-gap Step 1 evaluator union). Does not enable "
            "repair mode; may be combined with full-tree generate."
        ),
    )
    parser.add_argument(
        "--needed-where",
        default=None,
        metavar="PATH",
        help=(
            "Optional needed-where.json to merge loci onto AffordanceMap rows "
            "(transitional; AffordanceMap-native loci win on conflict)."
        ),
    )
    parser.add_argument(
        "--services",
        default=None,
        metavar="LIST",
        help=(
            "Optional comma-separated service ids. When used with --affordance-map, "
            "intersects the map (FR-B8)."
        ),
    )
    args = parser.parse_args()

    onboarding = Path(args.onboarding_metadata)
    output = Path(args.output_dir)
    manifest = Path(args.manifest) if args.manifest else None
    obs_yaml = Path(args.observability_yaml) if args.observability_yaml else None

    if args.affordance_map and args.check:
        print(
            "error: --check cannot be combined with --affordance-map "
            "(NR-G8); refuse.",
            file=sys.stderr,
        )
        return 1

    if args.affordance_map and (
        args.min_metric_coverage is not None
        or args.min_artifact_type_coverage is not None
    ):
        print(
            "error: --min-*-coverage cannot be combined with --affordance-map "
            "(FR-B9); refuse.",
            file=sys.stderr,
        )
        return 1

    if args.affordance_map:
        return _run_affordance_map_mode(args, onboarding, output)

    if args.check:
        return check_drift(onboarding, output, manifest)

    affordance_export = (
        Path(args.affordance_map_export) if args.affordance_map_export else None
    )

    # Handle --portal-persona all: generate one run per persona
    if args.portal and args.portal_persona == "all":
        # Generate base artifacts once, then add each persona portal
        report = generate_observability_artifacts(
            onboarding_metadata_path=onboarding,
            output_dir=output,
            manifest_path=manifest,
            observability_yaml_path=obs_yaml,
            dry_run=args.dry_run,
            portal=False,  # We'll generate portals individually below
            dashboard_provision_url=args.provision,
            affordance_map=affordance_export,
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
            observability_yaml_path=obs_yaml,
            dry_run=args.dry_run,
            portal=args.portal,
            portal_persona=args.portal_persona,
            portal_provision_url=args.portal_provision,
            dashboard_provision_url=args.provision,
            affordance_map=affordance_export,
        )

    # Print summary
    generated = sum(1 for a in report.artifacts if a.status == "generated")
    skipped = sum(1 for a in report.artifacts if a.status == "skipped")
    errored = sum(1 for a in report.artifacts if a.status == "error")

    print(f"Services processed: {report.services_processed}")
    print(f"Services skipped:   {report.services_skipped}")
    print(f"Artifacts: {generated} generated, {skipped} skipped, {errored} errors")

    # Quality summary (REQ-KZ-OBS-730c). Gate on the `score` key, not truthiness:
    # functional-SLO artifacts carry a scoreless coverage dict (#226 FR-5 / #254), which
    # would otherwise KeyError on a.quality["score"] below once functional SLOs emit.
    scored = [a for a in report.artifacts if a.quality and "score" in a.quality]
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

    # P2 (#226 FR-9): surface the coverage GAPS the manifest records, so a human running
    # the pipe sees them here instead of grepping observability-manifest.yaml.
    gap_lines = format_coverage_gaps(getattr(report, "fr_coverage", None))
    if gap_lines:
        print()
        for _line in gap_lines:
            print(_line)

    # Write kaizen-metrics.json observability section (REQ-KZ-OBS-500)
    if not args.dry_run and scored:
        _write_quality_to_kaizen_metrics(output, scored)

    if args.dry_run:
        print("\n[DRY RUN] No files written. Artifacts that would be generated:")
        for a in report.artifacts:
            marker = {"generated": "+", "skipped": "~", "error": "!"}[a.status]
            score_str = f" score={a.quality['score']:.0%}" if a.quality else ""
            print(f"  {marker} {a.output_path} ({a.status}{score_str})")

    # Deployable Grafana JSON (Gap 4): dashboards are now compiled directly to
    # grafana/dashboards/{service}-dashboard.json — no separate /dbrd-cr8r step.
    grafana_dashboards = [
        a for a in report.artifacts if a.artifact_type == "dashboard"
    ]
    if grafana_dashboards and not args.dry_run:
        produced = [d for d in grafana_dashboards if d.status == "generated"]
        skipped_dash = [d for d in grafana_dashboards if d.status != "generated"]
        print("\n  Grafana dashboards (deployable JSON):")
        for d in produced:
            print(f"    + {output / d.output_path}")
        for d in skipped_dash:
            print(f"    ~ {d.service_id}: not compiled ({d.error_message})")
        if args.provision:
            print(f"  Provisioned to Grafana at {args.provision} "
                  f"(idempotent upsert; see logs for per-dashboard status).")
        elif produced:
            print("  To deploy: import the JSON above, commit it for GitOps, or "
                  "re-run with --provision <grafana-url>.")
        if skipped_dash:
            print("  (Dashboards skipped when the jsonnet toolchain / startd8-mixin "
                  "is unavailable; the YAML specs remain under dashboards/.)")

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


def format_coverage_gaps(fr_coverage: dict) -> list:
    """P2 (#226 FR-9 / #230-233): render the manifest's coverage GAPS as human lines.

    Mirrors the portal Coverage Gaps panel (P1c): ungrounded-kind services (∅-folded +
    a kind-specific next step from ``suggested_signals``), plain observed-by-nothing
    services, and unfulfilled FRs. Returns ``[]`` when there are no gaps, so a fully
    covered project prints nothing (byte-identical to before this surface existed).
    """
    cov = fr_coverage or {}
    ungrounded = cov.get("ungrounded_kinds") or []
    empty = cov.get("empty_services") or []
    unfulfilled = cov.get("unfulfilled") or []
    if not (ungrounded or empty or unfulfilled):
        return []

    lines = [
        f"  Coverage gaps ({len(empty)} observed-by-nothing, "
        f"{len(ungrounded)} ungrounded-kind, {len(unfulfilled)} unfulfilled):"
    ]
    ungrounded_svcs = {u.get("service") for u in ungrounded}
    for u in ungrounded:
        sig = "/".join(u.get("suggested_signals") or []) or "run_success/freshness"
        also = " (observed by nothing)" if u.get("observed_by_nothing") else ""
        lines.append(
            f"    - {u.get('service')}: ungrounded kind '{u.get('kind')}'{also} "
            f"-> declare a {sig} FR + target"
        )
    for svc in empty:
        if svc in ungrounded_svcs:  # already told as the ungrounded story (LH-1) — no dupe
            continue
        lines.append(
            f"    - {svc}: observed by nothing -> declare an FR, or add a request transport"
        )
    for uf in unfulfilled:
        lines.append(
            f"    - FR {uf.get('id', '?')}: declared '{uf.get('signal_kind', '?')}', metric absent"
        )
    return lines


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
