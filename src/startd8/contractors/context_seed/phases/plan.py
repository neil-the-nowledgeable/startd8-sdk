"""PLAN phase handler."""

from __future__ import annotations

import time
from collections import defaultdict
from pathlib import Path
from typing import Any

from startd8.contractors.artisan_contractor import AbstractPhaseHandler, WorkflowPhase
from startd8.contractors.context_schema import PlanPhaseOutput
from startd8.contractors.context_seed.shared import (
    _load_enriched_seed,
    _parse_tasks,
    _topological_sort,
)
from startd8.logging_config import get_logger
from startd8.seeds.utils import KNOWN_GENERATION_PROFILES, safe_onboarding

logger = get_logger("startd8.contractors.context_seed_handlers")


class PlanPhaseHandler(AbstractPhaseHandler):
    """PLAN phase: Load enriched seed, validate, build execution plan.

    Populates context with parsed tasks, dependency order, and domain summary.
    """

    def __init__(self, enriched_seed_path: str) -> None:
        self.enriched_seed_path = enriched_seed_path

    def execute(
        self,
        phase: WorkflowPhase,
        context: dict[str, Any],
        dry_run: bool = False,
    ) -> dict[str, Any]:
        start = time.monotonic()
        logger.info("PLAN phase: loading enriched seed from %s", self.enriched_seed_path)

        # Load and parse
        seed_data = _load_enriched_seed(self.enriched_seed_path)
        tasks = _parse_tasks(seed_data)
        sorted_tasks = _topological_sort(tasks)

        # Apply task filter if provided (e.g. --task-filter PI-001,PI-002).
        # This narrows the execution to a subset of tasks while preserving
        # the full seed's architectural context and calibration data.
        task_filter = context.get("task_filter")
        if task_filter:
            filter_set = set(task_filter)
            all_ids = {t.task_id for t in sorted_tasks}
            all_count = len(sorted_tasks)
            sorted_tasks = [t for t in sorted_tasks if t.task_id in filter_set]
            missing = filter_set - all_ids
            if missing:
                # Show available IDs so the user can spot typos (e.g. P1-001 vs PI-001)
                sample = sorted(all_ids)[:10]
                suffix = f" ... ({all_count} total)" if all_count > 10 else ""
                raise ValueError(
                    f"Task filter IDs not found in seed: {', '.join(sorted(missing))}. "
                    f"Available IDs: {', '.join(sample)}{suffix}"
                )
            logger.info(
                "PLAN phase: task filter applied — %d of %d tasks selected: %s",
                len(sorted_tasks), all_count,
                [t.task_id for t in sorted_tasks],
            )

        # Extract plan metadata
        plan_meta = seed_data.get("plan", {})
        preflight = seed_data.get("_preflight", {})

        # Domain summary (computed over filtered tasks)
        domain_counts: dict[str, int] = defaultdict(int)
        for t in sorted_tasks:
            domain_counts[t.domain] += 1

        # Check summary from preflight
        check_summary = preflight.get("check_summary", {})
        fail_count = check_summary.get("fail", 0)

        # Populate context for downstream phases.
        # Note: we intentionally do NOT store the raw seed_data blob in
        # context — it can be large and is not needed after parsing.  If a
        # checkpoint resume needs it, _ensure_context_loaded re-reads the file.
        context["enriched_seed_path"] = self.enriched_seed_path
        context["tasks"] = sorted_tasks
        context["task_index"] = {t.task_id: t for t in sorted_tasks}
        context["plan_title"] = plan_meta.get("title", "Untitled Plan")
        context["plan_goals"] = plan_meta.get("goals", [])
        context["domain_summary"] = dict(domain_counts)
        context["preflight_summary"] = check_summary
        context["total_estimated_loc"] = sum(t.estimated_loc for t in sorted_tasks)
        context["architectural_context"] = seed_data.get("architectural_context", {})
        context["design_calibration"] = seed_data.get("design_calibration", {})
        # Operational project metadata (criticality, risks, SLOs) from ContextCore manifest
        context["project_metadata"] = seed_data.get("project_metadata", {})
        # Item 9: example artifacts per type for implement phase
        context["example_artifacts"] = (seed_data.get("artifacts") or {}).get(
            "example_artifacts", {}
        )

        # REQ-ICD-106: extract security contract from seed
        _security_contract = seed_data.get("security_contract")
        if _security_contract and isinstance(_security_contract, dict):
            context["security_contract"] = _security_contract
            logger.info(
                "PLAN phase: security contract loaded (%d database(s))",
                len(_security_contract.get("databases", {})),
            )

        # REQ-PD-002: Forward complexity data from seed to context
        _complexity = seed_data.get("complexity") or {}
        context["complexity_dimensions"] = _complexity.get("dimensions", {})
        context["complexity_composite"] = _complexity.get("composite")

        # -- Phase 2 data flow fixes: extract ContextCore enrichment --
        _artifacts = seed_data.get("artifacts") or {}

        # Fix 1a: provenance chain — source_checksum
        source_checksum = _artifacts.get("source_checksum")
        context["source_checksum"] = source_checksum or ""
        if source_checksum:
            logger.info(
                "PLAN phase: source_checksum present — provenance chain active: %s",
                source_checksum[:16],
            )
        else:
            logger.warning(
                "PLAN phase: source_checksum absent in seed — provenance chain broken"
            )

        # Fix 2b: parameter_sources for DESIGN/IMPLEMENT prompt injection
        context["parameter_sources"] = _artifacts.get("parameter_sources", {})

        # Fix 3b: semantic_conventions for DESIGN/IMPLEMENT prompt injection
        context["semantic_conventions"] = _artifacts.get("semantic_conventions", {})

        # Fix 5a: output_conventions for SCAFFOLD extension validation
        context["output_conventions"] = _artifacts.get("output_conventions", {})

        # Mottainai: forward inventory-equivalent fields from onboarding so
        # DESIGN phase can fall back to them when artifact inventory is absent.
        _onboarding = seed_data.get("onboarding") or {}

        # REQ-GPC-200: extract generation profile for downstream awareness
        _raw_profile = _onboarding.get("generation_profile", "full")
        if _raw_profile not in KNOWN_GENERATION_PROFILES:
            logger.warning(
                "PLAN phase: unknown generation_profile %r — defaulting to 'full' behavior. "
                "Known profiles: %s",
                _raw_profile, ", ".join(sorted(KNOWN_GENERATION_PROFILES)),
            )
        context["generation_profile"] = _raw_profile

        # REQ-GPC-201: skip ContextCore profile-omitted markers → None
        # activates existing fallback heuristics (LOC-based, complexity defaults)
        context["onboarding_derivation_rules"] = safe_onboarding(
            _onboarding.get("derivation_rules")
        )
        context["onboarding_resolved_parameters"] = safe_onboarding(
            _onboarding.get("resolved_artifact_parameters")
        )
        context["onboarding_output_contracts"] = safe_onboarding(
            _onboarding.get("expected_output_contracts")
        )
        context["onboarding_calibration_hints"] = safe_onboarding(
            _onboarding.get("design_calibration_hints")
        )
        context["onboarding_open_questions"] = safe_onboarding(
            _onboarding.get("open_questions")
        )
        # B4: artifact dependency graph from ContextCore export
        context["onboarding_dependency_graph"] = safe_onboarding(
            _onboarding.get("artifact_dependency_graph")
        )
        # AR-144/AR-147: service metadata for protocol fidelity validators
        context["service_metadata"] = safe_onboarding(
            _onboarding.get("service_metadata")
        )
        # REQ-EFE-021: schema_features for edit-first enforcement gate
        _raw_sf = (
            _onboarding.get("capabilities", {}).get("schema_features")
            or _onboarding.get("schema_features")
        )
        context["onboarding_schema_features"] = safe_onboarding(_raw_sf)
        _fwd_count = sum(
            1 for k in [
                "onboarding_derivation_rules", "onboarding_resolved_parameters",
                "onboarding_output_contracts", "onboarding_calibration_hints",
                "onboarding_open_questions", "onboarding_dependency_graph",
                "service_metadata", "onboarding_schema_features",
            ] if context.get(k)
        )
        if _fwd_count:
            logger.info(
                "PLAN phase: forwarded %d/8 onboarding inventory fields into context",
                _fwd_count,
            )

        # Mottainai B2+B3: read the plan document (produced by TRANSFORM)
        # directly from the seed's artifacts so DESIGN can use it as fallback
        # when the inventory path (run-provenance.json) is unavailable.
        plan_doc_path_str = _artifacts.get("plan_document_path")
        if plan_doc_path_str:
            plan_doc_path = Path(plan_doc_path_str)
            # Resolve relative to enriched_seed_path parent (same output dir)
            if not plan_doc_path.is_absolute():
                seed_parent = Path(self.enriched_seed_path).parent
                plan_doc_path = seed_parent / plan_doc_path
            if plan_doc_path.exists():
                try:
                    plan_text = plan_doc_path.read_text(encoding="utf-8")
                    context["plan_document_text"] = plan_text
                    logger.info(
                        "PLAN phase: loaded plan document (%d chars) for DESIGN fallback",
                        len(plan_text),
                    )
                except OSError:
                    logger.debug("Could not read file: %s", plan_doc_path, exc_info=True)

        # R2-D7: Extract forward_manifest from seed and deserialize into
        # ForwardManifest model so downstream phases (SCAFFOLD, DESIGN,
        # IMPLEMENT) can access forward interface contracts.
        _fm_dict = seed_data.get("forward_manifest")
        if _fm_dict and isinstance(_fm_dict, dict):
            try:
                from startd8.forward_manifest import ForwardManifest
                _fm = ForwardManifest.model_validate(_fm_dict)
                context["forward_manifest"] = _fm
                _n_contracts = len(_fm.contracts) if _fm.contracts else 0
                _n_file_specs = len(_fm.file_specs) if _fm.file_specs else 0
                logger.info(
                    "PLAN phase: loaded forward_manifest with %d contract(s), "
                    "%d file spec(s)",
                    _n_contracts,
                    _n_file_specs,
                )
            except (ImportError, ValueError, TypeError) as exc:
                logger.warning(
                    "PLAN phase: could not deserialize forward_manifest — "
                    "downstream phases will not have interface contracts: %s",
                    exc,
                )
                # Fall back to raw dict so at least some consumers can use it
                context["forward_manifest"] = _fm_dict
        else:
            logger.debug("PLAN phase: no forward_manifest in seed")

        output = {
            "plan_title": context["plan_title"],
            "task_count": len(sorted_tasks),
            "execution_order": [t.task_id for t in sorted_tasks],
            "domain_summary": dict(domain_counts),
            "preflight_check_summary": check_summary,
            "total_estimated_loc": context["total_estimated_loc"],
            "preflight_failures": fail_count,
            "goals": context["plan_goals"],
        }
        if task_filter:
            output["task_filter"] = task_filter

        duration = time.monotonic() - start
        logger.info(
            "PLAN phase complete: %d tasks, %d domains, %d preflight failures (%.2fs)",
            len(sorted_tasks), len(domain_counts), fail_count, duration,
        )

        if fail_count > 0 and not dry_run:
            logger.warning(
                "PLAN phase: %d preflight failures detected — review before implementing",
                fail_count,
            )
            if context.get("abort_on_preflight_fail"):
                raise ValueError(
                    f"PLAN phase aborted: {fail_count} preflight failure(s) detected. "
                    "Address preflight issues before proceeding, or run without --abort-on-preflight-fail."
                )

        # Context contract: validate PLAN output model
        PlanPhaseOutput(
            enriched_seed_path=context["enriched_seed_path"],
            tasks=context["tasks"],
            task_index=context["task_index"],
            plan_title=context["plan_title"],
            plan_goals=context["plan_goals"],
            domain_summary=context["domain_summary"],
            preflight_summary=context["preflight_summary"],
            total_estimated_loc=context["total_estimated_loc"],
            architectural_context=context.get("architectural_context", {}),
            design_calibration=context.get("design_calibration", {}),
            example_artifacts=context.get("example_artifacts", {}),
            source_checksum=context.get("source_checksum"),
            parameter_sources=context.get("parameter_sources", {}),
            semantic_conventions=context.get("semantic_conventions", {}),
            output_conventions=context.get("output_conventions", {}),
            onboarding_derivation_rules=context.get("onboarding_derivation_rules"),
            onboarding_resolved_parameters=context.get("onboarding_resolved_parameters"),
            onboarding_output_contracts=context.get("onboarding_output_contracts"),
            onboarding_calibration_hints=context.get("onboarding_calibration_hints"),
            onboarding_open_questions=context.get("onboarding_open_questions"),
            onboarding_dependency_graph=context.get("onboarding_dependency_graph"),
            plan_document_text=context.get("plan_document_text"),
        )

        return {"output": output, "cost": 0.0, "metadata": {"duration": duration}}
