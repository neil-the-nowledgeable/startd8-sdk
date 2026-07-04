"""FINALIZE phase handler."""

from __future__ import annotations

import hashlib
import time
from pathlib import Path
from typing import Any, Optional

from startd8.contractors.artisan_contractor import (
    AbstractPhaseHandler,
    WorkflowPhase,
)
from startd8.contractors.context_schema import FinalizePhaseOutput
from startd8.contractors.context_seed.shared import (
    SeedTask,
    _ensure_context_loaded,
    _log_context_completeness,
)
from startd8.contractors.protocols import GenerationResult
from startd8.contractors.context_seed.handler_support import HandlerConfig
from startd8.logging_config import get_logger
from startd8.utils.file_operations import atomic_write_json

logger = get_logger("startd8.contractors.context_seed_handlers")


class FinalizePhaseHandler(AbstractPhaseHandler):
    """FINALIZE phase: Collect artifacts and write comprehensive execution report.

    Produces a workflow execution report aggregating all phase results,
    lists generated files with checksums and line counts, computes a
    per-task status rollup joining generation/test/review outcomes, and
    writes both a human-readable report and a machine-readable manifest.

    Key outputs written to ``output_dir``:

    * ``workflow-execution-report.json`` — full summary with cost
      breakdown, artifact inventory, and per-phase stats.
    * ``generation-manifest.json`` — machine-readable manifest with
      per-task status, artifact checksums, and cost attribution.
    """

    def __init__(
        self,
        output_dir: Optional[str] = None,
        handler_config: Optional[HandlerConfig] = None,
    ) -> None:
        self.output_dir = output_dir
        self.config = handler_config or HandlerConfig()

    # ------------------------------------------------------------------
    # WCP-004: Propagation completeness validation
    # ------------------------------------------------------------------

    REQUIRED_CONTEXT_FIELDS = ["domain", "domain_reasoning", "prompt_constraints"]

    def _validate_propagation_completeness(
        self, context: dict[str, Any],
    ) -> dict[str, Any]:
        """Check that all tasks received expected context fields.

        Attempts to use the contract-based PropagationTracker for chain
        validation with OTel emission.  Falls back to the original inline
        implementation if contextcore propagation module is not available.

        Args:
            context: Workflow context containing ``tasks`` list.

        Returns:
            Dict with ``total``, ``complete``, ``defaulted``, and
            optionally ``defaulted_tasks`` listing task IDs that fell back.
        """
        # Try contract-based validation first
        try:
            from contextcore.contracts.propagation import (
                ContractLoader,
                PropagationTracker,
                emit_propagation_summary,
            )
            from pathlib import Path

            contract_yaml = Path(__file__).parent / "contracts" / "artisan-pipeline.contract.yaml"
            if contract_yaml.exists():
                contract = ContractLoader().load(contract_yaml)
                tracker = PropagationTracker()
                chain_results = tracker.validate_all_chains(contract, context)
                emit_propagation_summary(chain_results)

                # Convert chain results to legacy format for backward compat
                from contextcore.contracts.types import ChainStatus
                intact = sum(1 for r in chain_results if r.status == ChainStatus.INTACT)
                total = len(chain_results)
                return {
                    "total": total,
                    "complete": intact,
                    "defaulted": total - intact,
                    "defaulted_tasks": [
                        r.chain_id for r in chain_results
                        if r.status != ChainStatus.INTACT
                    ],
                }
        except ImportError:
            logger.debug("contextcore propagation not available", exc_info=True)
        except Exception as exc:
            logger.warning(
                "Contract-based propagation validation failed, using fallback: %s", exc
            )

        # Fallback: original inline implementation
        tasks = context.get("tasks", [])
        results: dict[str, Any] = {
            "total": len(tasks),
            "complete": 0,
            "defaulted": 0,
            "defaulted_tasks": [],
        }

        for task in tasks:
            all_present = True
            for field in self.REQUIRED_CONTEXT_FIELDS:
                value = getattr(task, field, None)
                if value in (None, "", "unknown", []):
                    results["defaulted"] += 1
                    results["defaulted_tasks"].append(
                        getattr(task, "task_id", "?"),
                    )
                    logger.warning(
                        "FINALIZE: context field '%s' not propagated for task %s",
                        field,
                        getattr(task, "task_id", "?"),
                    )
                    all_present = False
                    break
            if all_present:
                results["complete"] += 1

        # Emit span event for propagation summary
        try:
            from opentelemetry import trace
            span = trace.get_current_span()
            if span and span.is_recording():
                span.add_event("context.propagation_summary", attributes={
                    "context.total_tasks": results["total"],
                    "context.complete": results["complete"],
                    "context.defaulted": results["defaulted"],
                    "context.completeness_pct": round(
                        results["complete"] / max(results["total"], 1) * 100, 1
                    ),
                })
        except Exception:
            logger.debug("OTel span not available", exc_info=True)

        return results

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _collect_generated_artifacts(
        self,
        context: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Inventory all files generated during the IMPLEMENT phase.

        Reads ``context["generation_results"]`` and lists output files
        with sizes, hashes, line counts, and domain tags.

        Args:
            context: Shared workflow context.

        Returns:
            List of artifact dicts with keys: ``task_id``, ``path``,
            ``exists``, ``size_bytes``, ``line_count``, ``sha256``,
            ``domain``.
        """
        artifacts: list[dict[str, Any]] = []
        generation_results: dict[str, GenerationResult] = context.get(
            "generation_results", {}
        )

        # Build task_id → SeedTask lookup for domain metadata
        tasks: list[SeedTask] = context.get("tasks", [])
        id_to_task: dict[str, SeedTask] = {t.task_id: t for t in tasks}

        # R2-T7: Collect artifacts from ALL tasks, not just fully successful
        # ones.  Partial-success tasks may have some files generated — track
        # per-artifact source_status so downstream consumers can distinguish.
        for task_id, result in generation_results.items():
            task = id_to_task.get(task_id)
            source_status = "success" if result.success else "partial"
            for fpath in result.generated_files:
                artifact: dict[str, Any] = {
                    "task_id": task_id,
                    "path": str(fpath),
                    "exists": (
                        fpath.exists() if hasattr(fpath, "exists") else False
                    ),
                    "domain": task.domain if task else "unknown",
                    "source_status": source_status,
                }
                if hasattr(fpath, "exists") and fpath.exists():
                    try:
                        raw_bytes = fpath.read_bytes()
                        artifact["size_bytes"] = len(raw_bytes)
                        artifact["sha256"] = hashlib.sha256(raw_bytes).hexdigest()
                        try:
                            text = raw_bytes.decode("utf-8", errors="strict")
                            artifact["line_count"] = len(text.splitlines())
                        except (UnicodeDecodeError, ValueError):
                            # Binary file — line count not applicable
                            artifact["line_count"] = None
                    except OSError as exc:
                        logger.warning(
                            "FINALIZE: could not read artifact %s: %s",
                            fpath, exc,
                        )
                        artifact["read_error"] = str(exc)
                artifacts.append(artifact)

        return artifacts

    def _persist_forensic_artifacts(
        self,
        *,
        context: dict[str, Any],
        output_dir: Path,
        dry_run: bool,
    ) -> dict[str, dict[str, Any]]:
        """AR-166: Persist Prime-style per-task forensic artifacts.

        Stores best-effort artifacts under:
          ``<output_dir>/.artifacts/<task_id>/``
        with deterministic names:
          - ``spec.md``
          - ``draft-<n>.md``
          - ``review-<n>.json``
          - ``integration.json``

        In dry-run mode, records planned paths only.
        """
        tasks: list[SeedTask] = _ensure_context_loaded(context)
        design_results: dict[str, Any] = context.get("design_results", {}) or {}
        integration_results: dict[str, Any] = context.get("integration_results", {}) or {}
        forensic_map: dict[str, dict[str, Any]] = {}

        for task in tasks:
            task_id = task.task_id
            task_dir = output_dir / ".artifacts" / task_id
            task_design = design_results.get(task_id, {}) if isinstance(design_results, dict) else {}
            task_integration = integration_results.get(task_id, {}) if isinstance(integration_results, dict) else {}

            pointers: dict[str, Any] = {
                "spec": str(task_dir / "spec.md"),
                "drafts": [str(task_dir / "draft-1.md")],
                "reviews": [str(task_dir / "review-1.json")],
                "integration": str(task_dir / "integration.json"),
                "planned_only": bool(dry_run),
                "persisted": False,
            }
            forensic_map[task_id] = pointers
            if dry_run:
                continue

            try:
                task_dir.mkdir(parents=True, exist_ok=True)

                spec_text = str(
                    task_design.get("implementation_spec")
                    or task.description
                    or ""
                )
                (task_dir / "spec.md").write_text(spec_text, encoding="utf-8")

                draft_text = str(
                    task_design.get("design_document")
                    or task_design.get("implementation_spec")
                    or ""
                )
                (task_dir / "draft-1.md").write_text(draft_text, encoding="utf-8")

                review_payload = {
                    "reviewer_verdict": task_design.get("reviewer_verdict"),
                    "arbiter_verdict": task_design.get("arbiter_verdict"),
                    "reviewer_summary": task_design.get("reviewer_summary"),
                    "arbiter_summary": task_design.get("arbiter_summary"),
                    "status": task_design.get("status"),
                    "agreed": task_design.get("agreed"),
                    "iterations": task_design.get("iterations"),
                }
                atomic_write_json(
                    task_dir / "review-1.json",
                    review_payload,
                    indent=2,
                    default=str,
                )

                integration_payload = task_integration if isinstance(task_integration, dict) else {}
                atomic_write_json(
                    task_dir / "integration.json",
                    integration_payload,
                    indent=2,
                    default=str,
                )
                pointers["persisted"] = True
            except OSError as exc:
                logger.warning(
                    "FINALIZE: forensic artifact write failed for %s: %s",
                    task_id,
                    exc,
                )
            except Exception as exc:
                logger.warning(
                    "FINALIZE: forensic artifact persistence error for %s: %s",
                    task_id,
                    exc,
                )

        return forensic_map

    @staticmethod
    def _build_cost_summary(context: dict[str, Any]) -> dict[str, Any]:
        """Aggregate costs across all phases.

        Args:
            context: Shared workflow context.

        Returns:
            Dict with per-phase and total cost breakdowns.

        Note:
            PLAN and SCAFFOLD phases are zero-cost (no LLM calls) and
            excluded for clarity.  TEST phase cost is included even
            though current validators are subprocess-based (zero cost);
            this future-proofs for LLM-based test generation.
        """
        implementation = context.get("implementation", {})
        test_results = context.get("test_results", {})
        review_results = context.get("review_results", {})
        design_results = context.get("design_results", {})

        def _safe_cost(d: dict, key: str = "total_cost") -> float:
            try:
                return float(d.get(key, 0.0))
            except (TypeError, ValueError):
                return 0.0

        # Design cost: sum per-task costs from design_results dict
        design_cost = 0.0
        if isinstance(design_results, dict):
            for entry in design_results.values():
                if isinstance(entry, dict):
                    try:
                        design_cost += float(entry.get("cost", 0.0) or 0.0)
                    except (TypeError, ValueError):
                        logger.debug("Cost computation failed", exc_info=True)

        impl_cost = _safe_cost(implementation)
        test_cost = _safe_cost(test_results)
        review_cost = _safe_cost(review_results)
        total = design_cost + impl_cost + test_cost + review_cost

        return {
            "design_cost": design_cost,
            "implementation_cost": impl_cost,
            "test_cost": test_cost,
            "review_cost": review_cost,
            "total_cost": total,
            "currency": "USD",
        }

    def _write_manifest(
        self,
        artifacts: list[dict[str, Any]],
        summary: dict[str, Any],
        context: dict[str, Any],
        output_dir: Path,
    ) -> Optional[Path]:
        """Write a machine-readable manifest of all changes.

        Includes per-task status rollup joining generation results with
        test and review outcomes, artifact checksums (from enriched
        ``_collect_generated_artifacts``), and cost breakdown.

        Args:
            artifacts: List of generated artifact dicts (with ``sha256``).
            summary: The full workflow summary.
            context: Shared workflow context (for test/review joining).
            output_dir: Directory to write the manifest.

        Returns:
            Path to the manifest file, or None if no artifacts.
        """
        if not artifacts:
            return None

        # Per-task status rollup: join generation, test, and review data
        generation_results: dict[str, GenerationResult] = context.get(
            "generation_results", {}
        )
        test_results_ctx: dict[str, Any] = context.get("test_results", {})
        review_results_ctx: dict[str, Any] = context.get("review_results", {})

        test_results_map: dict[str, Any] = dict(
            test_results_ctx.get("per_task", {}) or {}
        )
        if not test_results_map:
            logger.debug("FINALIZE: rebuilding test_results_map from test_plan entries")
            for entry in test_results_ctx.get("test_plan", []):
                if not isinstance(entry, dict):
                    continue
                task_id = entry.get("task_id")
                if not task_id:
                    continue
                status = entry.get("status", "unknown")
                passed = (
                    True if status == "passed"
                    else False if status == "failed"
                    else None
                )
                validators_run = entry.get("validators_run", 0)
                results = entry.get("results", [])
                failures = [
                    r.get("validator", "unknown")
                    for r in results
                    if isinstance(r, dict) and not r.get("passed", True)
                ]
                test_results_map[task_id] = {
                    "status": status,
                    "passed": passed,
                    "validators_run": validators_run,
                    "failures": failures,
                }

        review_results_map: dict[str, Any] = dict(
            review_results_ctx.get("per_task", {}) or {}
        )
        if not review_results_map:
            logger.debug("FINALIZE: rebuilding review_results_map from review_items entries")
            for entry in review_results_ctx.get("review_items", []):
                if not isinstance(entry, dict):
                    continue
                task_id = entry.get("task_id")
                if not task_id:
                    continue
                review_results_map[task_id] = {
                    "status": entry.get("review_status", "unknown"),
                    "passed": entry.get("passed"),
                    "score": entry.get("score"),
                    "verdict": entry.get("verdict"),
                }

        forensic_artifacts_map: dict[str, Any] = context.get("forensic_artifacts", {}) or {}
        all_task_ids: set[str] = set(t.task_id for t in context.get("tasks", []) or [])
        all_task_ids.update(generation_results.keys())
        all_task_ids.update(forensic_artifacts_map.keys())

        task_status: dict[str, dict[str, Any]] = {}
        for task_id in sorted(all_task_ids):
            try:
                gen_result = generation_results.get(task_id)
                test_info = test_results_map.get(task_id, {})
                review_info = review_results_map.get(task_id, {})
                # Surface missing target files if IMPLEMENT flagged them
                _impl_reports = context.get("implementation", {}).get("task_reports", [])
                _task_report = next(
                    (r for r in _impl_reports if r.get("task_id") == task_id),
                    {},
                )
                _entry: dict[str, Any] = {
                    "generated": bool(gen_result.success) if gen_result is not None else False,
                    "files_count": len(gen_result.generated_files) if gen_result is not None else 0,
                    "generation_cost_usd": gen_result.cost_usd if gen_result is not None else 0.0,
                    "tests_passed": test_info.get("passed", None),
                    "review_score": review_info.get("score", None),
                    "review_passed": review_info.get("passed", None),
                }
                if task_id in forensic_artifacts_map:
                    _entry["forensic_artifacts"] = forensic_artifacts_map[task_id]
                _missing = _task_report.get("missing_targets")
                if _missing:
                    _entry["missing_targets"] = _missing
                task_status[task_id] = _entry
            except Exception as exc:
                logger.warning(
                    "FINALIZE: error building status for task %s: %s",
                    task_id, exc, exc_info=True,
                )
                task_status[task_id] = {
                    "generated": False,
                    "error": str(exc),
                }

        manifest = {
            "workflow_version": "0.4.0",
            # Fix 1b: provenance chain — record source_checksum for Gate 3
            "provenance": {
                "source_checksum": context.get("source_checksum"),
                "enriched_seed_path": str(context.get("enriched_seed_path", "")),
            },
            "artifacts": artifacts,
            "task_status": task_status,
            "summary": {
                "plan_title": summary.get("plan_title", ""),
                "task_count": summary.get("task_count", 0),
                "total_cost": summary.get("cost_summary", {}).get(
                    "total_cost", 0.0
                ),
                "status": summary.get("status", "unknown"),
            },
            # CCD-603: Design coherence data at manifest root
            "design_coherence": summary.get(
                "design_coherence", {"status": "NOT_COMPUTED"},
            ),
        }

        manifest_path = output_dir / "generation-manifest.json"
        try:
            manifest_path.parent.mkdir(parents=True, exist_ok=True)
            atomic_write_json(manifest_path, manifest, indent=2, default=str)
            logger.info("Wrote manifest: %s", manifest_path)
        except OSError as exc:
            logger.warning("Failed to write manifest to %s: %s", manifest_path, exc)
            return None
        return manifest_path

    # ------------------------------------------------------------------
    # Gate 3b severity rollup
    # ------------------------------------------------------------------

    @staticmethod
    def _build_design_coherence_summary(
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Build design coherence summary for generation-manifest.json (CCD-603)."""
        lane_conflicts: list[dict[str, Any]] = context.get("lane_conflicts", [])
        lane_to_file_mapping: dict[int, list[str]] = context.get(
            "lane_to_file_mapping", {},
        )
        shared_file_manifest: dict[str, list[str]] = context.get(
            "shared_file_manifest", {},
        )

        if context.get("_design_lane_computation_skipped", False):
            return {
                "status": "NOT_COMPUTED",
                "reason": "lane computation fell back to flat iteration",
            }

        total_lanes = context.get("_design_lane_count", 0)
        shared_file_lanes = len(lane_to_file_mapping)

        coherent_lanes = sum(
            1 for lc in lane_conflicts if lc.get("status") == "COHERENT"
        )
        warning_lanes = sum(
            1 for lc in lane_conflicts if lc.get("status") == "WARNING"
        )
        conflicting_lanes = sum(
            1 for lc in lane_conflicts if lc.get("status") == "CONFLICTING"
        )

        lane_details: list[dict[str, Any]] = []
        for lc in lane_conflicts:
            lane_idx = lc.get("lane_index")
            if lane_idx is None:
                continue
            shared_files = lane_to_file_mapping.get(lane_idx, [])
            lane_details.append({
                "lane_index": lane_idx,
                "task_ids": lc.get("task_ids", []),
                "shared_files": shared_files,
                "status": lc.get("status", "COHERENT"),
            })

        return {
            "total_lanes": total_lanes,
            "shared_file_lanes": shared_file_lanes,
            "coherent_lanes": coherent_lanes,
            "warning_lanes": warning_lanes,
            "conflicting_lanes": conflicting_lanes,
            "shared_file_count": len(shared_file_manifest),
            "lane_details": lane_details,
        }

    @staticmethod
    def _count_gate3b_by_severity(
        gate3b: dict[str, list[dict[str, Any]]],
    ) -> dict[str, int]:
        """Count Gate 3b validation issues grouped by severity.

        Severity is inferred from confidence:
          >= 0.8 -> high
          >= 0.6 -> medium
          < 0.6 -> low
        """
        counts: dict[str, int] = {"high": 0, "medium": 0, "low": 0}
        for task_issues in gate3b.values():
            for issue in task_issues:
                confidence = issue.get("confidence", 0.5)
                if confidence >= 0.8:
                    counts["high"] += 1
                elif confidence >= 0.6:
                    counts["medium"] += 1
                else:
                    counts["low"] += 1
        return counts

    # ------------------------------------------------------------------
    # Public execute
    # ------------------------------------------------------------------

    def execute(
        self,
        phase: WorkflowPhase,
        context: dict[str, Any],
        dry_run: bool = False,
    ) -> dict[str, Any]:
        start = time.monotonic()
        _log_context_completeness("FINALIZE", context)
        logger.info("FINALIZE phase: generating summary (dry_run=%s)", dry_run)

        plan_title = context.get("plan_title", "Untitled")
        tasks: list[SeedTask] = _ensure_context_loaded(context)
        domain_summary = context.get("domain_summary", {})
        preflight_summary = context.get("preflight_summary", {})
        scaffold = context.get("scaffold", {})
        implementation = context.get("implementation", {})
        test_results = context.get("test_results", {})
        review_results = context.get("review_results", {})
        truncation_flags: dict[str, Any] = context.get("truncation_flags", {})

        # Collect artifacts and costs
        artifacts = self._collect_generated_artifacts(context)
        cost_summary = self._build_cost_summary(context)
        forensic_base_dir = Path(self.output_dir) if self.output_dir else Path(
            context.get("project_root", ".")
        )
        forensic_artifacts = self._persist_forensic_artifacts(
            context=context,
            output_dir=forensic_base_dir,
            dry_run=(dry_run or not bool(self.output_dir)),
        )
        context["forensic_artifacts"] = forensic_artifacts

        # Compute overall status rollup
        generation_results: dict[str, GenerationResult] = context.get(
            "generation_results", {}
        )
        total_tasks = len(tasks)
        generated_ok = sum(
            1 for r in generation_results.values() if r.success
        )
        generated_fail = sum(
            1 for r in generation_results.values() if not r.success
        )

        # Consider test/review outcomes in status rollup
        tests_failed = test_results.get("total_failed", 0)
        reviews_failed = review_results.get("total_failed", 0)
        tests_skipped = test_results.get("total_skipped", 0)

        if generated_fail == 0 and generated_ok == total_tasks:
            if tests_failed > 0 or reviews_failed > 0:
                overall_status = "quality_failed"
            elif tests_skipped > 0:
                overall_status = "partial"
            else:
                overall_status = "success"
        elif generated_ok == 0:
            overall_status = "failed"
        else:
            overall_status = "partial"

        summary: dict[str, Any] = {
            "plan_title": plan_title,
            "task_count": total_tasks,
            "status": overall_status,
            "tasks_succeeded": generated_ok,
            "tasks_failed": generated_fail,
            "domain_summary": domain_summary,
            "preflight_summary": preflight_summary,
            "scaffold_summary": {
                "dirs_needed": len(scaffold.get("directories_needed", [])),
                "dirs_created": len(scaffold.get("directories_created", [])),
                "existing_files": len(scaffold.get("existing_target_files", [])),
            },
            "implementation_summary": {
                "tasks_processed": implementation.get("tasks_processed", 0),
                "total_estimated_loc": implementation.get("total_estimated_loc", 0),
                "generation_results": {
                    tid: {
                        "success": r.success,
                        "error": r.error,
                        "cost_usd": r.cost_usd,
                        "files": [str(f) for f in r.generated_files],
                        "model": r.model,
                        "iterations": r.iterations,
                    }
                    for tid, r in generation_results.items()
                },
            },
            "test_summary": {
                "total_validators": test_results.get("total_validators", 0),
                "tasks_with_tests": test_results.get("tasks_with_tests", 0),
                "total_passed": test_results.get("total_passed", 0),
                "total_failed": test_results.get("total_failed", 0),
            },
            "review_summary": {
                "tasks_with_env_issues": review_results.get("tasks_with_env_issues", 0),
                "total_passed": review_results.get("total_passed", 0),
                "total_failed": review_results.get("total_failed", 0),
                "total_cost": review_results.get("total_cost", 0.0),
            },
            "quality_gate": context.get(
                "quality_gate_summary",
                {
                    "policy_mode": "warn",
                    "gate_count": 0,
                    "violation_count": 0,
                    "violations": [],
                },
            ),
            "truncation_summary": {
                "tasks_flagged": len(truncation_flags),
                "tasks_with_syntax_errors": sum(
                    1 for tf in truncation_flags.values()
                    if tf.get("syntax_errors")
                ),
                "max_confidence": max(
                    (tf.get("max_confidence", 0.0) for tf in truncation_flags.values()),
                    default=0.0,
                ),
                "flagged_task_ids": sorted(truncation_flags.keys()),
                "details": truncation_flags,
            } if truncation_flags else {"tasks_flagged": 0},
            "gate3b_validation": {},
            "cost_summary": cost_summary,
            "generated_artifacts": artifacts,
            "forensic_artifacts": forensic_artifacts,
            "artifact_count": len(artifacts),
            "dry_run": dry_run,
        }

        # PCA-402: attach onboarding consumption audit trail to provenance
        _onb_consumption = context.get("_onboarding_consumption")
        if _onb_consumption:
            summary.setdefault("provenance", {})["onboarding_fields_consumed"] = _onb_consumption

        # Task 11a: Gate 3b content validation summary
        gate3b_data: dict[str, Any] = implementation.get("_gate3b_content_validation", {})
        severity_counts: dict[str, int] = {"high": 0, "medium": 0, "low": 0}
        if gate3b_data:
            try:
                severity_counts = FinalizePhaseHandler._count_gate3b_by_severity(gate3b_data)
                total_issues = sum(len(v) for v in gate3b_data.values())
                summary["gate3b_validation"] = {
                    "tasks_with_issues": len(gate3b_data),
                    "total_issues": total_issues,
                    "by_severity": severity_counts,
                    "flagged_task_ids": sorted(gate3b_data.keys()),
                }
                logger.info(
                    "FINALIZE: Gate 3b summary — %d task(s), %d issue(s) (high=%d, medium=%d, low=%d)",
                    len(gate3b_data), total_issues,
                    severity_counts["high"], severity_counts["medium"], severity_counts["low"],
                )
            except Exception as exc:
                logger.warning("FINALIZE: Gate 3b summary failed: %s", exc, exc_info=True)
                summary["gate3b_validation"] = {"error": str(exc)}

        # Task 11b: Strict validation blocking check
        strict_mode = context.get("strict_validation", False)
        if strict_mode and gate3b_data:
            high_count = severity_counts.get("high", 0)
            if high_count > 0:
                error_msg = (
                    f"--strict-validation: {high_count} high-severity Gate 3b issue(s) "
                    f"detected — failing FINALIZE. Review _gate3b_content_validation in "
                    f"implementation output for details."
                )
                logger.error(error_msg)
                summary["status"] = "failed"
                summary["strict_validation_error"] = error_msg

        # CCD-603: Design coherence summary
        summary["design_coherence"] = self._build_design_coherence_summary(context)

        # Write report and manifest
        if self.output_dir and not dry_run:
            output_dir = Path(self.output_dir)
            try:
                output_path = output_dir / "workflow-execution-report.json"
                output_path.parent.mkdir(parents=True, exist_ok=True)
                atomic_write_json(output_path, summary, indent=2, default=str)
                logger.info("Wrote execution report to %s", output_path)
                summary["report_path"] = str(output_path)

                # Write manifest of generated files
                manifest_path = self._write_manifest(
                    artifacts, summary, context, output_dir,
                )
                if manifest_path:
                    summary["manifest_path"] = str(manifest_path)
            except Exception as exc:
                logger.error(
                    "FINALIZE: crash during report/manifest write: %s",
                    exc, exc_info=True,
                )
                # AR-815: Write partial manifest so prior phases' work is not lost
                try:
                    partial = {
                        "workflow_version": "0.4.0",
                        "incomplete": True,
                        "error": str(exc),
                        "artifacts": artifacts,
                        "task_status": {},
                        "summary": {"status": "incomplete"},
                    }
                    partial_path = output_dir / "generation-manifest.json"
                    partial_path.parent.mkdir(parents=True, exist_ok=True)
                    atomic_write_json(partial_path, partial, indent=2, default=str)
                    logger.info("Wrote partial manifest: %s", partial_path)
                    summary["manifest_path"] = str(partial_path)
                    summary["manifest_incomplete"] = True
                except OSError as write_exc:
                    logger.error("Failed to write partial manifest: %s", write_exc)

        context["workflow_summary"] = summary

        # Context contract: validate FINALIZE output model
        # R2-T6: Respect gate mode — block raises, warn flags, skip ignores.
        try:
            FinalizePhaseOutput(workflow_summary=context["workflow_summary"])
        except Exception as _val_exc:
            _gate_mode = context.get("quality_gate_summary", {}).get(
                "policy_mode", "warn",
            )
            if _gate_mode == "block":
                raise RuntimeError(
                    f"FINALIZE output validation failed (block policy): {_val_exc}"
                ) from _val_exc
            logger.warning(
                "FINALIZE output validation failed (continuing per %s policy): %s",
                _gate_mode,
                _val_exc,
            )
            if _gate_mode == "warn":
                summary["_validation_failed"] = True
                summary["_validation_error"] = str(_val_exc)

        duration = time.monotonic() - start

        logger.info(
            "FINALIZE phase complete: %s — %d artifacts, $%.4f total cost (%.2fs)",
            overall_status, len(artifacts),
            cost_summary.get("total_cost", 0.0), duration,
        )

        return {"output": summary, "cost": 0.0, "metadata": {"duration": duration}}
