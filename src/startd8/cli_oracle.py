"""``startd8 build-to-spec`` — the oracle-generation loop operator CLI (FR-8 / FR-11).

Drives a det-req spec end-to-end: plan-ingest → Prime seed → generate → deploy + ORACLE rung →
regenerate-on-fail → report. Exits 0 iff the runnable fitness passed over a non-empty set meeting
the ``--min-coverage`` floor within the cumulative budget; non-zero otherwise, naming the terminal
cause ∈ {budget, max_iterations, stall, coverage_below_floor, no_fitness, regen_rejected, disabled}.

FR-11: the whole capability is gated by ``oracle_loop.enabled`` (env
``STARTD8_ORACLE_LOOP_ENABLED``), default OFF. While off this command refuses with terminal cause
``disabled`` and spawns NO generation/subprocess.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

import typer

from .cli_shared import console
from .logging_config import get_logger
from .oracle_loop import oracle_loop_enabled
from .oracle_loop.loop import (
    GenFeedback,
    GenOutcome,
    exit_code_for_cause,
    run_build_to_spec_loop,
)

logger = get_logger("startd8.cli_oracle")


def _fr_intent_map(spec_path: Path) -> dict:
    """Map ``fr_id -> intent`` (the FR Name) so regen feedback names a behavioral target (FR-4)."""
    from .navigator.det_req import parse_fr_lines_prefer_kit

    text = spec_path.read_text(encoding="utf-8")
    out: dict = {}
    for fr in parse_fr_lines_prefer_kit(text):
        fid = str(fr.get("id", ""))
        out[fid] = str(fr.get("name") or fr.get("title") or fid)
    return out


def _plan_ingest_to_seed(spec_path: Path, out_dir: Path) -> Path:
    """Plan-ingest a det-req spec into a Prime context-seed in-process (FR-8).

    Copies ``run_prime_workflow.py``'s bridge premise — Prime consumes a seed, not a raw det-req doc
    (``queue.py:229``) — WITHOUT depending on the ``.cap-dev-pipe`` symlink. Uses PlanIngestionWorkflow.
    """
    from .workflows.builtin.plan_ingestion_workflow import PlanIngestionWorkflow

    wf = PlanIngestionWorkflow()
    result = wf.execute(
        {"plan_path": str(spec_path), "output_dir": str(out_dir)}
    )
    seed = (result or {}).get("context_seed_path")
    if not seed:
        raise RuntimeError(
            "plan-ingestion did not emit a context_seed_path — cannot feed Prime"
        )
    return Path(seed)


def _build_generate_fn(seed_path: Path, project_root: Path, max_cost_usd: Optional[float]):
    """Wire the injected ``generate_fn`` to Prime's regenerate-with-feedback path (FR-4).

    Iteration 1 runs a fresh generation. On a subsequent call carrying feedback, the failing FRs'
    structured behavioral target is injected as ``feature.error_message`` on GENERATED features so
    Prime's existing regen branch (``process_feature``, status==GENERATED + code_generator) re-develops
    them — NOT ``repair/``. A ``_seam_marked_targets`` reject surfaces as ``regen_rejected`` (FATAL).
    """
    from .contractors.generators.primary_contractor import LeadContractorCodeGenerator
    from .contractors.prime_contractor import PrimeContractorWorkflow
    from .contractors.queue import FeatureStatus

    workflow = PrimeContractorWorkflow(
        project_root=project_root,
        code_generator=LeadContractorCodeGenerator(),
    )
    workflow.queue.add_features_from_seed(seed_path)
    state = {"cost_before": 0.0}

    def _generate(feedback: Optional[List[GenFeedback]]) -> GenOutcome:
        if feedback:
            # Re-arm GENERATED/COMPLETE features with a structured behavioral target (FR-4).
            rendered = "\n\n".join(fb.render() for fb in feedback)
            for feat in workflow.queue.features.values():
                if feat.status in (FeatureStatus.GENERATED, FeatureStatus.COMPLETE):
                    feat.status = FeatureStatus.GENERATED
                    feat.error_message = (
                        "ORACLE rung failure — regenerate to satisfy the spec's runnable "
                        f"Verify clauses:\n{rendered}"
                    )
        try:
            workflow.run(max_cost_usd=max_cost_usd)
        except Exception as exc:  # noqa: BLE001 — surface a fatal Prime state as regen_rejected
            reason = str(exc)
            if "seam" in reason.lower():
                return GenOutcome(
                    app_root=project_root, regen_rejected=True, reject_reason=reason
                )
            raise
        spent = float(getattr(workflow, "total_cost_usd", 0.0))
        delta = max(0.0, spent - state["cost_before"])
        state["cost_before"] = spent
        return GenOutcome(app_root=project_root, cost_usd=delta)

    return _generate


def _build_deploy_fn(spec_path: Path):
    """Wire the injected ``deploy_fn`` to ``deploy_app_local`` with the ORACLE rung on (FR-3)."""
    from .deploy_harness import deploy_app_local

    def _deploy(app_root: Path):
        result = deploy_app_local(
            app_root, spec_path=spec_path, oracle_enabled=True
        )
        return list(result.oracle_verdicts.values())

    return _deploy


def build_to_spec(
    spec: Path = typer.Option(
        ..., "--spec", help="Path to the target det-req spec (the FRs + their Verify clauses)."
    ),
    max_cost_usd: Optional[float] = typer.Option(
        None, "--max-cost-usd", help="CUMULATIVE budget across all iterations (fail-closed)."
    ),
    max_iterations: int = typer.Option(
        3, "--max-iterations", help="Hard cap on generate→oracle→regenerate rounds."
    ),
    min_coverage: Optional[float] = typer.Option(
        None, "--min-coverage", help="Minimum runnable-coverage floor (0..1); below → non-zero exit."
    ),
    out: Optional[Path] = typer.Option(
        None, "--out", help="Write the JSON report here."
    ),
    project_root: Optional[Path] = typer.Option(
        None, "--project-root", help="Where Prime generates the app (default: a temp dir)."
    ),
) -> None:
    """Run the oracle-driven generation loop for a spec and report pass or the terminal cause."""
    # FR-11 gate: refuse cleanly, spawning no generation/subprocess.
    if not oracle_loop_enabled():
        console.print(
            "[yellow]oracle_loop disabled[/yellow] — set "
            "STARTD8_ORACLE_LOOP_ENABLED=1 to enable build-to-spec (FR-11)."
        )
        raise typer.Exit(code=exit_code_for_cause("disabled"))

    import tempfile

    spec = spec.resolve()
    root = (project_root or Path(tempfile.mkdtemp(prefix="startd8-build-to-spec-"))).resolve()
    root.mkdir(parents=True, exist_ok=True)

    seed_path = _plan_ingest_to_seed(spec, root)
    report = run_build_to_spec_loop(
        spec,
        generate_fn=_build_generate_fn(seed_path, root, max_cost_usd),
        deploy_fn=_build_deploy_fn(spec),
        fr_intent=_fr_intent_map(spec),
        max_iterations=max_iterations,
        max_cost_usd=max_cost_usd,
        min_coverage=min_coverage,
        enabled=True,
    )

    if out is not None:
        out.write_text(report.to_json(), encoding="utf-8")

    console.print(
        f"[bold]build-to-spec[/bold] cause=[cyan]{report.terminal_cause}[/cyan] "
        f"status={report.status} coverage={report.coverage.coverage:.2f} "
        f"iterations={report.iterations} cost=${report.cumulative_cost_usd:.4f}"
    )
    if report.coverage.residue_fr_ids:
        console.print(
            f"[dim]human-gate residue (non-runnable FRs): "
            f"{', '.join(report.coverage.residue_fr_ids)}[/dim]"
        )
    raise typer.Exit(code=exit_code_for_cause(report.terminal_cause))
