# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""FDE orchestrator — ties explain/preflight to write-back, idempotency, and events.

One-shot and idempotent (FR-13/FR-19): a re-invocation on unchanged inputs (same run_id +
consumed-artifact checksums + SDK version) is a no-op that returns the existing report. The
explanation is run-scoped (written into the run output dir beside the SA triage, FR-2); the
preflight report and posting/cursor are project-scoped under ``.startd8/fde/``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence

from ..logging_config import get_logger

from . import assistant_bridge, context, deterministic_compose, explain, notify, sources
from .models import FdeExplanation, FdePreflightReport

logger = get_logger(__name__)

EXPLANATION_MD = "fde-explanation.md"
EXPLANATION_JSON = "fde-explanation.json"
PREFLIGHT_MD = "fde-preflight.md"
PREFLIGHT_JSON = "fde-preflight.json"


def _sdk_version() -> str:
    try:
        from .. import __version__

        return str(__version__)
    except Exception:  # pragma: no cover
        return "0.0.0"


@dataclass
class ExplainOutcome:
    explanation: FdeExplanation
    report_path: Path
    ref_attached: bool
    skipped: bool = False  # idempotent no-op


def run_fde_explain(
    run_output_dir: Path,
    *,
    project_root: Optional[Path] = None,
    feature_ids: Optional[Sequence[str]] = None,
    narrative: bool = False,
    max_cost_usd: Optional[float] = None,
    emit: bool = True,
    write: bool = True,
    force: bool = False,
) -> ExplainOutcome:
    """Produce a composed, source-labeled explanation for a run; write it; attach the SA ref.

    Raises :class:`sources.ArtifactTrustError` if a consumed artifact is present but malformed
    (FR-18) — the CLI maps that to a non-zero exit.
    """
    run_output_dir = Path(run_output_dir)
    project_root = Path(project_root) if project_root else Path.cwd()
    sdk_version = _sdk_version()
    context.ensure_posting(project_root, sdk_version=sdk_version)

    # Idempotency key (FR-19): run_id + consumed-artifact checksums + sdk version.
    run_id = sources.read_triage_run_id(run_output_dir) or run_output_dir.name
    parts = {
        # Exclude fde_explanation — our own write-back must not invalidate the cursor (FR-19).
        "triage": context.checksum_json_excluding(
            run_output_dir / sources.TRIAGE_FILENAME, exclude_keys=("fde_explanation",)
        ),
        "postmortem": context.checksum_file(
            run_output_dir / sources.POSTMORTEM_FILENAME
        ),
        # Raw prime-result*.json carries generation_strategy; a regen must re-explain (R1-F12).
        "mechanism": context.checksum_glob(run_output_dir, sources.RUN_RESULT_GLOB),
        "sdk_version": sdk_version,
        "feature_ids": ",".join(sorted(feature_ids or [])) or None,
    }
    fp = context.fingerprint(parts)
    key = f"explain:{run_id}"
    report_path = run_output_dir / EXPLANATION_MD

    if (
        not force
        and report_path.exists()
        and context.already_processed(project_root, key, fp)
    ):
        logger.info("FDE explain: %s unchanged since last run — no-op", run_id)
        existing = (
            FdeExplanation.from_json(
                (run_output_dir / EXPLANATION_JSON).read_text("utf-8")
            )
            if (run_output_dir / EXPLANATION_JSON).exists()
            else explain.explain_run(
                run_output_dir,
                feature_ids=feature_ids,
                sdk_version=sdk_version,
                run_id=run_id,
            )
        )
        return ExplainOutcome(existing, report_path, ref_attached=True, skipped=True)

    exp = explain.explain_run(
        run_output_dir, feature_ids=feature_ids, sdk_version=sdk_version, run_id=run_id
    )
    deterministic_compose.assert_claims_labeled(exp.all_claims())
    md = deterministic_compose.render_explanation(exp)

    if narrative:
        from . import (
            compose,
        )  # lazy: keeps the LLM import out of the deterministic path

        md = compose.enhance_explanation_narrative(exp, md, max_cost_usd=max_cost_usd)

    deterministic_compose.assert_all_labeled(md)  # FR-21 gate, incl. any narrative

    ref_attached = False
    if write:
        (run_output_dir / EXPLANATION_JSON).write_text(
            json.dumps(exp.to_dict(), indent=2), encoding="utf-8"
        )
        report_path.write_text(md, encoding="utf-8")
        ref_attached = assistant_bridge.attach_fde_ref_to_triage(
            run_output_dir, report_path
        )
        context.record_processed(project_root, key, fp, parts)

    if emit:
        notify.emit_explain_complete(
            run_id,
            str(run_output_dir),
            str(report_path),
            cost_usd=exp.cost_usd,
            evidence_available=exp.evidence_available,
        )
    return ExplainOutcome(exp, report_path, ref_attached=ref_attached)


@dataclass
class PreflightOutcome:
    report: FdePreflightReport
    report_path: Path
    skipped: bool = False


def run_fde_preflight(
    *,
    plan_path: Optional[Path] = None,
    requirements_path: Optional[Path] = None,
    project_root: Optional[Path] = None,
    enable_track2: bool = False,
    max_cost_usd: Optional[float] = None,
    emit: bool = True,
    write: bool = True,
    force: bool = False,
) -> PreflightOutcome:
    """Run two-track preflight; write the project-scoped report under ``.startd8/fde/``."""
    from . import preflight

    project_root = Path(project_root) if project_root else Path.cwd()
    sdk_version = _sdk_version()
    context.ensure_posting(project_root, sdk_version=sdk_version)

    parts = {
        "plan": context.checksum_file(plan_path) if plan_path else None,
        "requirements": (
            context.checksum_file(requirements_path) if requirements_path else None
        ),
        "track2": str(enable_track2),
        "sdk_version": sdk_version,
    }
    fp = context.fingerprint(parts)
    key = "preflight:" + (str(plan_path) or str(requirements_path) or "?")
    out_dir = context.fde_dir(project_root)
    report_path = out_dir / PREFLIGHT_MD

    if (
        not force
        and report_path.exists()
        and context.already_processed(project_root, key, fp)
    ):
        logger.info("FDE preflight: inputs unchanged — no-op")
        existing = (
            FdePreflightReport.from_json((out_dir / PREFLIGHT_JSON).read_text("utf-8"))
            if (out_dir / PREFLIGHT_JSON).exists()
            else preflight.preflight_plan(
                plan_path,
                requirements_path,
                enable_track2=enable_track2,
                project_root=project_root,
                max_cost_usd=max_cost_usd,
            )
        )
        return PreflightOutcome(existing, report_path, skipped=True)

    rep = preflight.preflight_plan(
        plan_path,
        requirements_path,
        enable_track2=enable_track2,
        project_root=project_root,
        max_cost_usd=max_cost_usd,
    )
    md = deterministic_compose.render_preflight(rep)
    deterministic_compose.assert_all_labeled(md)  # FR-21 gate

    if write:
        (out_dir / PREFLIGHT_JSON).write_text(
            json.dumps(rep.to_dict(), indent=2), encoding="utf-8"
        )
        report_path.write_text(md, encoding="utf-8")
        context.record_processed(project_root, key, fp, parts)
    if emit:
        notify.emit_preflight_complete(
            str(out_dir),
            str(report_path),
            landmine_count=len(rep.landmines),
            cost_usd=rep.cost_usd,
            plan_path=str(plan_path) if plan_path else None,
        )
    return PreflightOutcome(rep, report_path)
