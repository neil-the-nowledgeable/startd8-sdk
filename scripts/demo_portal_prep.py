#!/usr/bin/env python3
"""Generate onboarding portal dashboards from online-boutique-demo pipeline data.

Reads onboarding-metadata.json + observability artifacts from a pipeline run,
builds portal specs for each persona, and routes through DashboardCreatorWorkflow
for Jsonnet → Grafana JSON compilation + optional provisioning.

Usage:
  # Default: latest run from online-boutique-demo, all personas
  python3 scripts/demo_portal_prep.py

  # Specific run
  python3 scripts/demo_portal_prep.py --run-dir /path/to/run-101-...

  # Single persona
  python3 scripts/demo_portal_prep.py --persona operator

  # With Grafana provisioning
  python3 scripts/demo_portal_prep.py --provision http://localhost:3000

  # Dry run (print specs, don't generate)
  python3 scripts/demo_portal_prep.py --dry-run

  # Use wayfinder-demo-retail pre-baked artifacts instead
  python3 scripts/demo_portal_prep.py --wayfinder

See docs/design/DEMO_PLANNING_HARBOR_TOUR.md for context.
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
    ArtifactResult,
    BusinessContext,
    GenerationReport,
    ServiceHints,
    ConventionMetric,
    load_onboarding_metadata,
    extract_service_hints,
    load_business_context,
)
from startd8.observability.portal_spec_builder import (
    build_portal_spec,
    build_all_portal_specs,
    fixup_portal_json,
    _PERSONA_SECTIONS,
)

# ---------------------------------------------------------------------------
# Default paths
# ---------------------------------------------------------------------------

_ONLINE_BOUTIQUE_DEMO = Path.home() / "Documents/dev/online-boutique-demo"
_PIPELINE_OUTPUT = _ONLINE_BOUTIQUE_DEMO / ".cap-dev-pipe/pipeline-output/online-boutique"

_WAYFINDER_DEMO = Path.home() / "Documents/dev/wayfinder-demo-retail"
_WAYFINDER_OUTPUT = _WAYFINDER_DEMO / "output/observability"


def _find_latest_run() -> Path:
    """Resolve the 'latest' symlink or find the most recent run directory."""
    latest = _PIPELINE_OUTPUT / "latest"
    if latest.is_symlink() or latest.is_dir():
        return latest.resolve()

    # Fallback: find highest-numbered run directory
    runs = sorted(_PIPELINE_OUTPUT.glob("run-*"), reverse=True)
    if runs:
        return runs[0]

    raise FileNotFoundError(
        f"No pipeline runs found in {_PIPELINE_OUTPUT}. "
        f"Run the capability delivery pipeline first."
    )


def _find_richest_run() -> Path:
    """Find the run with the most observability artifacts (best for demo)."""
    best_run = None
    best_count = 0

    for run_dir in _PIPELINE_OUTPUT.glob("run-*"):
        obs_dir = run_dir / "observability"
        if not obs_dir.is_dir():
            continue
        count = sum(1 for _ in obs_dir.rglob("*.yaml"))
        if count > best_count:
            best_count = count
            best_run = run_dir

    if best_run is None:
        raise FileNotFoundError(f"No runs with observability artifacts in {_PIPELINE_OUTPUT}")

    return best_run


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------


def _load_run_data(run_dir: Path) -> tuple:
    """Load onboarding metadata, services, business context, and report from a run."""
    onboarding_path = run_dir / "onboarding-metadata.json"
    if not onboarding_path.is_file():
        raise FileNotFoundError(f"onboarding-metadata.json not found in {run_dir}")

    metadata = load_onboarding_metadata(onboarding_path)
    services = extract_service_hints(metadata)

    # Try to load business context from manifest
    manifest_candidates = [
        run_dir / ".contextcore.yaml",
        run_dir / "project-context.yaml",
        _ONLINE_BOUTIQUE_DEMO / ".contextcore.yaml",
    ]
    manifest_path = None
    for c in manifest_candidates:
        if c.is_file():
            manifest_path = c
            break

    business = load_business_context(manifest_path, metadata)
    # Override project_id to be clean
    if not business.project_id or "/" in (business.project_id or ""):
        business.project_id = "online-boutique"
    if not business.project_name:
        business.project_name = "Online Boutique"

    # Build report from observability manifest
    report = _build_report_from_run(run_dir, business)

    return business, services, report, metadata


def _build_report_from_run(run_dir: Path, business: BusinessContext) -> GenerationReport:
    """Reconstruct a GenerationReport from a pipeline run's observability artifacts."""
    import yaml as _yaml

    obs_dir = run_dir / "observability"
    manifest_path = obs_dir / "observability-manifest.yaml"

    artifacts = []

    if manifest_path.is_file():
        with open(manifest_path) as f:
            manifest = _yaml.safe_load(f)

        for entry in manifest.get("artifacts", []):
            artifact_path = obs_dir / entry["path"]
            content = ""
            if artifact_path.is_file():
                content = artifact_path.read_text()

            quality = None
            score = entry.get("quality_score")
            if score is not None:
                quality = {"score": score, "issues": [], "repairs_applied": []}

            artifacts.append(ArtifactResult(
                artifact_type=entry["type"],
                service_id=entry["service"],
                output_path=entry["path"],
                status=entry.get("status", "generated"),
                content=content,
                quality=quality,
            ))

        generated_at = manifest.get("generated_at", "unknown")
        services_processed = manifest.get("summary", {}).get("services_processed", 0)
    else:
        # Fallback: scan artifact directories
        generated_at = "unknown"
        services_processed = 0

        for subdir, artifact_type in [
            ("alerts", "alert_rule"),
            ("dashboards", "dashboard_spec"),
            ("slos", "slo_definition"),
        ]:
            artifact_dir = obs_dir / subdir
            if not artifact_dir.is_dir():
                continue
            for f in sorted(artifact_dir.glob("*.yaml")):
                svc_id = f.stem.replace("-alerts", "").replace("-dashboard-spec", "").replace("-slo", "")
                artifacts.append(ArtifactResult(
                    artifact_type=artifact_type,
                    service_id=svc_id,
                    output_path=f"{subdir}/{f.name}",
                    status="generated",
                    content=f.read_text(),
                ))

    # Add quality summary if available
    quality_path = obs_dir / "observability-quality.json"
    if quality_path.is_file():
        try:
            quality_data = json.loads(quality_path.read_text())
            # Could enrich artifact quality from this
        except (json.JSONDecodeError, OSError):
            pass

    return GenerationReport(
        project_id=business.project_id,
        generated_at=generated_at,
        artifacts=artifacts,
        services_processed=services_processed,
    )


# ---------------------------------------------------------------------------
# Portal generation
# ---------------------------------------------------------------------------


def _generate_portals(
    business: BusinessContext,
    services: list,
    report: GenerationReport,
    metadata: dict,
    output_dir: Path,
    *,
    personas: list,
    provision_url: str = None,
    dry_run: bool = False,
) -> list:
    """Generate portal specs and optionally compile via DashboardCreatorWorkflow."""
    results = []

    for persona in personas:
        spec = build_portal_spec(
            business, services, report, metadata, persona=persona,
        )

        if dry_run:
            print(f"\n{'='*60}")
            print(f"Persona: {persona}")
            print(f"UID: {spec['uid']}")
            print(f"Title: {spec['title']}")
            print(f"Panels: {len(spec['panels'])}")
            print(f"Links: {len(spec['links'])}")
            for p in spec["panels"]:
                ptype = p["type"]
                title = p["title"]
                group = p.get("group", "")
                print(f"  [{ptype:10s}] {title:30s} {group}")
            results.append(spec)
            continue

        # Write spec YAML for reference
        import yaml as _yaml
        spec_path = output_dir / f"{spec['uid']}-spec.yaml"
        spec_path.parent.mkdir(parents=True, exist_ok=True)
        spec_path.write_text(_yaml.dump(spec, default_flow_style=False, sort_keys=False))
        print(f"  Spec: {spec_path}")

        # Try DashboardCreatorWorkflow for Jsonnet → JSON compilation
        try:
            from startd8.dashboard_creator.workflow import DashboardCreatorWorkflow

            workflow = DashboardCreatorWorkflow()
            config = {
                "spec": spec,
                "output_dir": str(output_dir),
            }
            if provision_url:
                config["provision"] = True
                config["grafana_url"] = provision_url

            result = workflow.run(config)

            if result.success:
                # Post-process: fix text panel widths to full-width
                json_path = result.output.get("json_path", str(output_dir / f"{spec['uid']}.json"))
                try:
                    jp = Path(json_path)
                    if jp.is_file():
                        dashboard = json.loads(jp.read_text())
                        dashboard = fixup_portal_json(dashboard)
                        jp.write_text(json.dumps(dashboard, indent=2, sort_keys=False))
                except (OSError, json.JSONDecodeError):
                    pass  # Non-fatal — dashboard still works, just half-width text
                print(f"  JSON: {json_path}")
                if provision_url:
                    url = result.output.get("dashboard_url", "")
                    if url:
                        print(f"  Grafana: {url}")
                results.append({"persona": persona, "spec": spec, "result": result})
            else:
                # Extract error details — output may be str, dict, or None
                if isinstance(result.output, dict):
                    error = result.output.get("error", str(result.output))
                elif isinstance(result.output, str):
                    error = result.output
                elif result.steps:
                    error = "; ".join(s.output for s in result.steps if s.output)
                else:
                    error = "Workflow returned failure (no detail)"
                print(f"  Workflow error: {error}")
                print(f"  Spec written to {spec_path} — use /dbrd-cr8r to compile")
                results.append({"persona": persona, "spec": spec, "spec_only": True})

        except ImportError:
            print("  WARNING: DashboardCreatorWorkflow not available")
            print(f"  Spec written to {spec_path} — use /dbrd-cr8r to compile")
            results.append({"persona": persona, "spec": spec, "spec_only": True})

        except Exception as exc:
            print(f"  ERROR: {exc}")
            results.append({"persona": persona, "spec": spec, "error": str(exc)})

    return results


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate onboarding portal dashboards from pipeline run data."
    )
    parser.add_argument(
        "--run-dir",
        default=None,
        help="Path to a specific pipeline run directory (default: richest run)",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Output directory for portal specs + JSON (default: run-dir/portal/)",
    )
    parser.add_argument(
        "--persona",
        default="all",
        choices=list(_PERSONA_SECTIONS.keys()) + ["all"],
        help="Portal persona to generate (default: all)",
    )
    parser.add_argument(
        "--provision",
        default=None,
        metavar="URL",
        help="Provision portals to Grafana (e.g. http://localhost:3000)",
    )
    parser.add_argument(
        "--wayfinder",
        action="store_true",
        help="Use wayfinder-demo-retail artifacts instead of online-boutique-demo",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print portal specs without generating files",
    )
    parser.add_argument(
        "--richest",
        action="store_true",
        default=True,
        help="Use the run with the most observability artifacts (default)",
    )
    args = parser.parse_args()

    # Resolve run directory
    if args.run_dir:
        run_dir = Path(args.run_dir)
    elif args.wayfinder:
        # wayfinder-demo-retail doesn't have onboarding-metadata.json,
        # so we can't use it directly. Point to online-boutique-demo instead.
        print("NOTE: wayfinder-demo-retail lacks onboarding-metadata.json.")
        print("Using online-boutique-demo pipeline data with wayfinder persona narratives.")
        run_dir = _find_richest_run()
    else:
        try:
            run_dir = _find_richest_run()
        except FileNotFoundError:
            run_dir = _find_latest_run()

    print(f"Run: {run_dir.name}")

    # Load data
    try:
        business, services, report, metadata = _load_run_data(run_dir)
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}")
        return 1

    print(f"Project: {business.project_id}")
    print(f"Services: {len(services)} (filtered)")
    print(f"Artifacts: {len(report.artifacts)}")
    print(f"Generated at: {report.generated_at}")

    # Determine personas
    if args.persona == "all":
        personas = list(_PERSONA_SECTIONS.keys())
    else:
        personas = [args.persona]

    print(f"Personas: {', '.join(personas)}")

    # Determine output directory
    if args.output_dir:
        output_dir = Path(args.output_dir)
    else:
        output_dir = run_dir / "portal"

    if not args.dry_run:
        output_dir.mkdir(parents=True, exist_ok=True)
        print(f"Output: {output_dir}")

    print()

    # Generate portals
    results = _generate_portals(
        business, services, report, metadata, output_dir,
        personas=personas,
        provision_url=args.provision,
        dry_run=args.dry_run,
    )

    # Summary
    print(f"\n{'='*60}")
    generated = sum(1 for r in results if isinstance(r, dict) and "result" in r)
    spec_only = sum(1 for r in results if isinstance(r, dict) and r.get("spec_only"))
    errors = sum(1 for r in results if isinstance(r, dict) and "error" in r)

    if args.dry_run:
        print(f"Dry run: {len(results)} portal specs printed")
    else:
        print(f"Generated: {generated} portals")
        if spec_only:
            print(f"Spec-only: {spec_only} (compile with /dbrd-cr8r)")
        if errors:
            print(f"Errors: {errors}")

    if not args.dry_run and generated > 0 and not args.provision:
        print(f"\nTo provision to Grafana:")
        print(f"  python3 scripts/demo_portal_prep.py --provision http://localhost:3000")

    if not args.dry_run:
        print(f"\nPortal files: {output_dir}")

    return 1 if errors > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
