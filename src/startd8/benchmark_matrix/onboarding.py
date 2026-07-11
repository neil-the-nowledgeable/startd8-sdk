# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""Generate the benchmark's per-persona onboarding portal, $0 (P3 / FR-7/8).

Reuse path (the SDK has no `role_views` renderer — that's the deferred FR-12 gap): drive the existing
`observability/portal_spec_builder.build_all_portal_specs()` with the benchmark's `BusinessContext`
(from `benchmark.contextcore.yaml`) + a minimal report/metadata, then compile each persona spec to
Grafana JSON via the shared `compile_or_spec` (jsonnet/startd8-mixin), degrading to spec-YAML offline.

The builder's four built-in personas (operator/engineer/manager/executive) are the nearest fit to the
benchmark's roles (SRE/PM/eng-leader/compliance) until the role_views renderer exists.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..logging_config import get_logger
from .observability import compile_or_spec

logger = get_logger(__name__)


def _benchmark_objectives() -> List[Dict[str, Any]]:
    """Onboarding objectives (keys match _build_objectives_panels: description/metricKey/target/unit — FR-16)."""
    return [
        {"description": "Measure model skill on a real build", "metricKey": "composite_quality_median",
         "target": "report, don't gate", "unit": "score"},
        {"description": "Find the cost differentiator", "metricKey": "cost_per_service_usd",
         "target": "lowest at equal quality", "unit": "USD"},
        {"description": "Credible, reproducible publication", "metricKey": "prereg_and_raw_release",
         "target": "100%", "unit": "%"},
    ]


def generate_onboarding_portal(
    manifest_path: Path,
    output_dir: Path,
    *,
    run_dir: Optional[Path] = None,
    provision: bool = False,
) -> List[Dict[str, Any]]:
    """Build + compile the per-persona onboarding portal from the benchmark ContextManifest.

    ``run_dir`` (optional): a finished run dir whose ``aggregate.json``/``run-spec.json`` feed the
    analyst persona's analytical sections (A3). Personas are resolved declaratively from the
    manifest's ``personas[]`` (A1/A2), so ``analyst`` renders from data with no persona code.
    """
    import yaml

    from ..observability.artifact_generator_context import load_business_context
    from ..observability.artifact_generator_models import GenerationReport, ServiceHints
    from ..observability.portal_spec_builder import build_all_portal_specs

    manifest_path = Path(manifest_path)
    business = load_business_context(manifest_path, {})
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    generated_at = manifest.get("metadata", {}).get("lastUpdated", "")

    # Synthetic "service" representing the benchmark harness (the portal's service-inventory section).
    services = [
        ServiceHints(
            service_id="benchmark-harness", transport="http", language="python",
            detected_databases=[], convention_metrics=[], declared_metrics=[],
        )
    ]
    # The portal reads report.{project_id, generated_at, artifacts, services_processed}.
    report = GenerationReport(
        project_id=business.project_id, generated_at=generated_at,
        artifacts=[], services_processed=len(services),
    )
    metadata: Dict[str, Any] = {
        "objectives": _benchmark_objectives(),
        # A1/A2: declarative personas drive which portals render (incl. the data-only `analyst`).
        "personas": manifest.get("personas") or manifest.get("spec", {}).get("personas") or [],
    }
    # A3: feed the analyst's analytical sections from the run's scoring artifacts.
    if run_dir is not None:
        run_dir = Path(run_dir)
        agg = run_dir / "aggregate.json"
        if agg.exists():
            metadata["aggregate"] = json.loads(agg.read_text(encoding="utf-8"))
        run_spec = run_dir / "run-spec.json"
        if run_spec.exists():
            metadata["scoring"] = json.loads(run_spec.read_text(encoding="utf-8"))

    specs = build_all_portal_specs(business, services, report, metadata)
    results: List[Dict[str, Any]] = []
    for spec in specs:
        res = compile_or_spec(spec, output_dir, provision=provision)
        results.append(res)
    logger.info("Generated %d persona portals → %s", len(results), output_dir)
    return results
