# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""Generate the benchmark's execution-run SRE dashboard, $0 (P1 / FR-3/4b/18).

The **direct DashboardSpec path** (validated by the 2026-06-14 spike): build a project-metric
`DashboardSpec` and run it through `DashboardCreatorWorkflow` → jsonnet/startd8-mixin → Grafana JSON.
This bypasses the service-RED `observability/artifact_generator` (which would synthesize irrelevant
http/grpc panels). Panels are parameterized by the run's `project_id`:

- **Cost** (live today): ``startd8_cost_total`` by model — emitted by the SDK cost tracker.
- **Execution pass/fail** (FR-18a): ``task_count_by_status`` by ``project_id`` — available once the
  run's cell task spans are ingested into ContextCore (``track_benchmark_run.py --install``). Cells
  labelled ``exclusion_reason`` (infra/integrity) map to ``blocked`` and are NOT model failures.

Spike learnings baked in: UID must match ``cc-{pack}-{kebab-name}``; a ``variables`` datasource entry
is required (else JSON validation fails on missing ``templating``); the mixin's ``vendor/`` (grafonnet)
must be present (``jb install``) — absent → emit the spec YAML and warn (don't hard-fail; FR-16).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from ..logging_config import get_logger

logger = get_logger(__name__)

_DEFAULT_DATASOURCE = "prometheus"
# delivery + per-run cost share the startd8-benchmark* project prefix in the cost tracker
_COST_PROJECT_MATCHER = 'startd8-benchmark.*'


def _run_id(run_spec: Dict[str, Any]) -> str:
    return (run_spec.get("spec_hash") or "")[:12] or "unknown"


def build_run_dashboard_spec(
    run_dir: Path, *, datasource: str = _DEFAULT_DATASOURCE
) -> Dict[str, Any]:
    """Build a DashboardSpec dict for a finished benchmark run (pure; no I/O beyond reading run-spec)."""
    run_dir = Path(run_dir)
    run_spec = json.loads((run_dir / "run-spec.json").read_text(encoding="utf-8"))
    run_id = _run_id(run_spec)
    run_name = run_spec.get("name", run_id)
    run_proj = f"startd8-benchmark-run-{run_id}"

    return {
        "title": f"Benchmark Run — {run_name} ({run_id})",
        "uid": f"cc-benchmark-run-{run_id}",  # spike: cc-{pack}-{kebab}
        "description": (
            f"Execution-run SRE dashboard for {run_proj}. Pass/fail panels need the run's cell task "
            f"spans ingested into ContextCore (track_benchmark_run.py --install); cost is live via "
            f"startd8.cost.*. Cells labelled exclusion_reason (infra/integrity) are excluded from "
            f"model pass/fail."
        ),
        "tags": ["generated", "benchmark", "sre", "execution-run"],
        "datasources": {"prometheus": datasource},
        "panels": [
            # --- Execution health (FR-4b / FR-18a) ---
            {"type": "stat", "title": "Cells Done",
             "expr": f'sum(task_count_by_status{{project_id="{run_proj}",task_status="done"}})',
             "unit": "short", "group": "Execution"},
            {"type": "stat", "title": "Cells Blocked / Excluded",
             "expr": f'sum(task_count_by_status{{project_id="{run_proj}",task_status="blocked"}})',
             "unit": "short", "group": "Execution"},
            {"type": "timeseries", "title": "Cells by Status",
             "expr": f'sum(task_count_by_status{{project_id="{run_proj}"}}) by (task_status)',
             "unit": "short", "group": "Execution"},
            # --- Cost (FR-3, live today) ---
            {"type": "stat", "title": "Total Cost (USD)",
             "expr": f'sum(startd8_cost_total{{project=~"{_COST_PROJECT_MATCHER}"}})',
             "unit": "currencyUSD", "group": "Cost"},
            {"type": "timeseries", "title": "Cost by Model",
             "expr": f'sum(startd8_cost_total{{project=~"{_COST_PROJECT_MATCHER}"}}) by (model)',
             "unit": "currencyUSD", "group": "Cost"},
        ],
        "variables": [
            {"type": "prometheusDatasource", "name": "datasource", "label": "Datasource"},
        ],
    }


def _mixin_vendor_present() -> bool:
    """True iff the startd8-mixin grafonnet vendor/ is installed (needed for compilation; FR-16)."""
    try:
        from ..dashboard_creator.discovery import discover_mixin

        return discover_mixin().vendor_dir.is_dir()
    except Exception as exc:  # pragma: no cover - environment-dependent
        logger.warning("mixin discovery failed: %s", type(exc).__name__)
        return False


def generate_run_dashboard(
    run_dir: Path,
    output_dir: Path,
    *,
    datasource: str = _DEFAULT_DATASOURCE,
    provision: bool = False,
) -> Dict[str, Any]:
    """Build + compile the run dashboard. Degrades to spec-YAML if the jsonnet toolchain is absent.

    Returns a summary dict: ``{run_id, uid, mode: "compiled"|"spec_only", json_path|spec_path, panel_count}``.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    spec = build_run_dashboard_spec(run_dir, datasource=datasource)
    run_id = spec["uid"].rsplit("-", 1)[-1]

    if not _mixin_vendor_present():
        # FR-16 graceful degradation: emit the spec YAML, don't hard-fail.
        import yaml

        spec_path = output_dir / f"{spec['uid']}-spec.yaml"
        spec_path.write_text(yaml.safe_dump(spec, sort_keys=False), encoding="utf-8")
        logger.warning(
            "startd8-mixin vendor/ absent (run `jb install` in startd8-mixin) — wrote spec only: %s",
            spec_path,
        )
        return {"run_id": run_id, "uid": spec["uid"], "mode": "spec_only",
                "spec_path": str(spec_path), "panel_count": len(spec["panels"])}

    from ..dashboard_creator.workflow import DashboardCreatorWorkflow

    res = DashboardCreatorWorkflow().run(
        {"spec": spec, "output_dir": str(output_dir), "provision": provision}
    )
    if not res.success:
        raise RuntimeError(f"dashboard generation failed: {getattr(res, 'error', res.output)}")
    out = res.output or {}
    logger.info("Generated run dashboard %s → %s", spec["uid"], out.get("json_path"))
    return {"run_id": run_id, "uid": spec["uid"], "mode": "compiled",
            "json_path": out.get("json_path"), "dashboard_url": out.get("dashboard_url"),
            "panel_count": out.get("panel_count", len(spec["panels"]))}
