"""
PhaseEmitter — Encapsulates the EMIT phase of plan ingestion.

Extracted from ``PlanIngestionWorkflow._phase_emit`` (AC-R4) to reduce
the 645-line monolithic method into focused, testable methods.  The
enrichment pipeline is consolidated here (AC-R5).
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

from ...logging_config import get_logger
from ...seeds.utils import is_omitted
from ...utils.file_operations import atomic_write_json
from .plan_ingestion_diagnostics import (
    EnrichmentDiagnostic,
    PlanIngestionKaizenConfig,
    compute_assess_quality,
    compute_density_warnings,
    compute_parse_quality,
    compute_seed_quality,
    compute_task_density,
)
from .plan_ingestion_models import (
    ArtisanContextSeed,
    ComplexityScore,
    ContractorRoute,
    ParsedFeature,
    ParsedPlan,
    PlanIngestionConfig,
    TaskTrackingConfig,
)

if TYPE_CHECKING:
    from startd8.forward_manifest import ForwardManifest

# Reuse module-level OTel/tracer from the workflow module to avoid
# duplicate tracer instances.
from ...contractors.artisan_contractor import _NoOpSpan, _NoOpTracer

try:
    from opentelemetry import trace as _trace

    _HAS_OTEL = True
    _tracer = _trace.get_tracer("startd8.plan_ingestion.emitter")
except ImportError:
    _HAS_OTEL = False
    _tracer = _NoOpTracer()

logger = get_logger(__name__)

__all__ = ["PhaseEmitter"]


# ---------------------------------------------------------------------------
# PhaseEmitter
# ---------------------------------------------------------------------------


class PhaseEmitter:
    """Encapsulates the EMIT phase of plan ingestion (AC-R4).

    Replaces the 645-line ``PlanIngestionWorkflow._phase_emit`` with
    focused, testable methods.  The constructor receives core state;
    the ``emit()`` method accepts pipeline outputs and returns an
    ``EmitResult``.
    """

    # Back-reference type is string-quoted to avoid circular import.
    def __init__(
        self,
        workflow: "PlanIngestionWorkflow",  # noqa: F821
        cfg: PlanIngestionConfig,
        parsed_plan: Optional[ParsedPlan],
        complexity: ComplexityScore,
        route: ContractorRoute,
        output_dir: Path,
        doc_path: Path,
    ) -> None:
        self._workflow = workflow
        self._cfg = cfg
        self._parsed_plan = parsed_plan
        self._complexity = complexity
        self._route = route
        self._output_dir = output_dir
        self._doc_path = doc_path

    # ------------------------------------------------------------------ #
    # Top-level orchestrator
    # ------------------------------------------------------------------ #

    def emit(
        self,
        *,
        step_costs: Optional[Dict[str, float]] = None,
        manifest_context: Optional[Dict[str, Any]] = None,
        translation_quality: Optional[Dict[str, Any]] = None,
        review_output: Optional[Dict[str, Any]] = None,
        requirement_hints: Optional[Dict[str, Dict[str, Any]]] = None,
        onboarding_metadata: Optional[Dict[str, Any]] = None,
        project_metadata: Optional[Dict[str, Any]] = None,
        project_root: Optional[Path] = None,
        tracking_config: Optional[TaskTrackingConfig] = None,
    ):
        """Top-level orchestrator — replaces ``_phase_emit``.

        Returns a ``plan_ingestion_workflow.EmitResult`` (NamedTuple).
        """
        # Late import to avoid circular dependency
        from .plan_ingestion_workflow import EmitResult

        cfg = self._cfg
        parsed_plan = self._parsed_plan
        route = self._route
        output_dir = self._output_dir
        doc_path = self._doc_path
        complexity = self._complexity

        # Convenience aliases for config-derived params
        review_rounds = cfg.review_rounds
        review_quality_tier = cfg.review_quality_tier
        scope = cfg.scope
        context_files = cfg.context_files
        warn_cost_usd = cfg.warn_cost_usd
        max_cost_usd = cfg.max_cost_usd

        # 1. Forward manifest extraction
        forward_manifest, forward_manifest_dict = self._extract_forward_manifest(
            project_metadata=project_metadata,
            project_root=project_root,
        )

        # 2. Mottainai pre-assembly (skeleton rendering + element tiers)
        stub_manifest, skeleton_sources, element_tiers = self._run_mottainai_pre_assembly(
            forward_manifest=forward_manifest,
            forward_manifest_dict=forward_manifest_dict,
        )

        # 3. Review config construction + persist
        review_config, config_path = self._build_review_config(
            review_rounds=review_rounds,
            review_quality_tier=review_quality_tier,
            scope=scope,
            context_files=context_files,
            warn_cost_usd=warn_cost_usd,
            max_cost_usd=max_cost_usd,
        )

        # 4. Onboarding resolution
        onboarding_resolved = self._resolve_onboarding(
            onboarding_metadata=onboarding_metadata,
            context_files=context_files,
        )

        # 5. Task derivation
        tasks = self._derive_tasks(
            translation_quality=translation_quality,
            requirement_hints=requirement_hints,
            onboarding_resolved=onboarding_resolved,
        )

        # 6. Forward manifest ID rewrite
        if forward_manifest_dict is not None and parsed_plan is not None:
            self._rewrite_forward_manifest_ids(
                forward_manifest_dict=forward_manifest_dict,
                tasks=tasks,
            )

        # 7. Shared derived data
        costs, total_cost, architectural_context, design_calibration, refine_suggestions = (
            self._derive_shared_context(
                step_costs=step_costs,
                manifest_context=manifest_context,
                review_output=review_output,
                tasks=tasks,
            )
        )

        # 8. Enrichment pipeline (R5)
        _enrichment_diag = self._run_enrichment_pipeline(
            tasks=tasks,
            refine_suggestions=refine_suggestions,
            forward_manifest=forward_manifest,
        )

        # 9. Build seed artifacts
        artifacts, onboarding_var, source_checksum_val = self._build_seed_artifacts(
            config_path=config_path,
            onboarding_resolved=onboarding_resolved,
            refine_suggestions=refine_suggestions,
            review_output=review_output,
            stub_manifest=stub_manifest,
            skeleton_sources=skeleton_sources,
            element_tiers=element_tiers,
        )

        # 10. Context files + service metadata
        from .plan_ingestion_workflow import (
            _context_files_with_checksums,
            _ensure_onboarding_in_context_files,
            _infer_service_metadata,
        )

        context_files_list = (
            _context_files_with_checksums(context_files, base_dir=output_dir)
            if context_files
            else None
        )
        _ensure_onboarding_in_context_files(
            context_files_list, onboarding_resolved, output_dir,
        )
        service_metadata = _infer_service_metadata(
            parsed_plan.features if parsed_plan else [], onboarding_resolved,
        )
        ingestion_metrics = {
            **{f"{k}_cost": v for k, v in costs.items()},
            "total_cost": total_cost,
        }

        # 11/12. Route-specific seed construction
        context_seed_path: Optional[Path] = None
        if route == ContractorRoute.ARTISAN and parsed_plan is not None:
            context_seed_path = self._emit_artisan_seed(
                tasks=tasks,
                artifacts=artifacts,
                ingestion_metrics=ingestion_metrics,
                architectural_context=architectural_context,
                design_calibration=design_calibration,
                onboarding_var=onboarding_var,
                context_files_list=context_files_list,
                service_metadata=service_metadata,
                project_metadata=project_metadata,
                forward_manifest_dict=forward_manifest_dict,
                source_checksum_val=source_checksum_val,
                refine_suggestions=refine_suggestions,
                review_output=review_output,
                context_files=context_files,
            )

        if route == ContractorRoute.PRIME and parsed_plan is not None:
            prime_seed_path = self._emit_prime_seed(
                tasks=tasks,
                artifacts=artifacts,
                ingestion_metrics=ingestion_metrics,
                architectural_context=architectural_context,
                design_calibration=design_calibration,
                onboarding_var=onboarding_var,
                context_files_list=context_files_list,
                service_metadata=service_metadata,
                project_metadata=project_metadata,
                forward_manifest_dict=forward_manifest_dict,
                source_checksum_val=source_checksum_val,
                refine_suggestions=refine_suggestions,
                review_output=review_output,
                context_files=context_files,
            )
            if context_seed_path is None:
                context_seed_path = prime_seed_path

        # 13. Task tracking
        tracking_result = self._emit_task_tracking(
            tasks=tasks,
            tracking_config=tracking_config,
        )

        return EmitResult(
            config_path, review_config, context_seed_path,
            tracking_result, tasks, _enrichment_diag,
        )

    # ------------------------------------------------------------------ #
    # 1. Forward manifest extraction
    # ------------------------------------------------------------------ #

    def _extract_forward_manifest(
        self,
        *,
        project_metadata: Optional[Dict[str, Any]],
        project_root: Optional[Path],
    ) -> Tuple[Optional["ForwardManifest"], Optional[Dict[str, Any]]]:
        """Extract forward contracts from parsed plan features."""
        parsed_plan = self._parsed_plan
        output_dir = self._output_dir
        doc_path = self._doc_path

        forward_manifest_dict: Optional[Dict[str, Any]] = None
        forward_manifest = None

        if parsed_plan is None or not parsed_plan.features:
            return forward_manifest, forward_manifest_dict

        try:
            from startd8.forward_manifest_extractor import extract_forward_contracts

            features = parsed_plan.features
            proto_dir: Optional[Path] = None
            for candidate in (output_dir / "proto", output_dir.parent / "proto"):
                if candidate.is_dir() and any(candidate.glob("*.proto")):
                    proto_dir = candidate
                    break

            yaml_text: Optional[str] = None
            if doc_path and doc_path.exists():
                plan_text = doc_path.read_text(encoding="utf-8")
                if "shared_contracts:" in plan_text:
                    yaml_text = plan_text

            # Layer 2: reference files for behavioral AST contracts
            reference_files: Optional[List[Path]] = None
            if project_metadata and project_metadata.get("reference_root"):
                ref_candidate = Path(str(project_metadata["reference_root"]))
                if ref_candidate.is_dir():
                    reference_files = sorted(ref_candidate.rglob("*.py"))

            contracts, file_elements = extract_forward_contracts(
                features,
                yaml_text=yaml_text,
                proto_dir=proto_dir,
                reference_files=reference_files,
                project_root=project_root,
            )

            # Construct ForwardManifest from extractor results
            from startd8.forward_manifest import ForwardFileSpec, ForwardManifest
            from startd8.micro_prime.lang_detect import detect_language
            from .plan_ingestion_parsing import _extract_imports_from_existing

            file_specs: Dict[str, "ForwardFileSpec"] = {}
            for fpath, elems in file_elements.items():
                lang = detect_language(fpath)
                file_imports = _extract_imports_from_existing(fpath, project_root)
                file_specs[fpath] = ForwardFileSpec(
                    file=fpath,
                    elements=elems,
                    imports=file_imports,
                    language=lang if lang != "python" else None,
                )

            forward_manifest = ForwardManifest(
                contracts=contracts,
                file_specs=file_specs,
            )
            forward_manifest_dict = forward_manifest.model_dump()

            if forward_manifest.contracts:
                logger.info(
                    "Forward manifest extracted: %d contract(s) for Prime/Artisan",
                    len(forward_manifest.contracts),
                )
        except Exception as exc:
            logger.warning("Forward manifest extraction failed: %s", exc, exc_info=True)
            forward_manifest_dict = None

        return forward_manifest, forward_manifest_dict

    # ------------------------------------------------------------------ #
    # 2. Mottainai pre-assembly
    # ------------------------------------------------------------------ #

    def _run_mottainai_pre_assembly(
        self,
        *,
        forward_manifest: Optional["ForwardManifest"],
        forward_manifest_dict: Optional[Dict[str, Any]],
    ) -> Tuple[
        Optional[List[Dict[str, Any]]],
        Optional[Dict[str, str]],
        Optional[Dict[str, Dict[str, Any]]],
    ]:
        """Run deterministic file assembly + Mottainai pre-assembly.

        Returns ``(stub_manifest, skeleton_sources, element_tiers)``.
        """
        stub_manifest: Optional[List[Dict[str, Any]]] = None
        skeleton_sources: Optional[Dict[str, str]] = None
        element_tiers: Optional[Dict[str, Dict[str, Any]]] = None

        if forward_manifest_dict is None or forward_manifest is None:
            return stub_manifest, skeleton_sources, element_tiers

        try:
            if hasattr(forward_manifest, "file_specs") and forward_manifest.file_specs:
                from startd8.utils.file_assembler import DeterministicFileAssembler

                assembler = DeterministicFileAssembler(module_inventory=None, element_registry=None)
                render_result = assembler.render_specs(forward_manifest)
                if render_result.metadata:
                    stub_manifest = [entry._asdict() for entry in render_result.metadata]
                    logger.info(
                        "EMIT: deterministic file assembly validated %d skeleton(s) "
                        "from FLCM (%d render failures)",
                        len(stub_manifest),
                        len(render_result.failures),
                    )

                # FR-MPA-001: Persist skeleton source text
                if render_result.specs:
                    skeleton_sources = dict(render_result.specs)

                # FR-MPA-009/010/011 + FR-MPA-002/003: Element registry
                from .plan_ingestion_mottainai import (
                    _apply_pre_fill_to_skeletons,
                    _mottainai_pre_assembly,
                )

                element_tiers = _mottainai_pre_assembly(
                    forward_manifest,
                    skeleton_sources,
                    self._output_dir,
                )
                # FR-MPA-003: Update skeleton_sources with template-filled bodies
                if element_tiers and skeleton_sources:
                    skeleton_sources = _apply_pre_fill_to_skeletons(
                        skeleton_sources, element_tiers, forward_manifest,
                    )
        except Exception as exc:
            logger.warning(
                "EMIT: deterministic file assembly validation failed: %s",
                exc,
                exc_info=True,
            )

        return stub_manifest, skeleton_sources, element_tiers

    # ------------------------------------------------------------------ #
    # 3. Review config construction
    # ------------------------------------------------------------------ #

    def _build_review_config(
        self,
        *,
        review_rounds: int,
        review_quality_tier: str,
        scope: Optional[str],
        context_files: Optional[List[str]],
        warn_cost_usd: Optional[float],
        max_cost_usd: Optional[float],
    ) -> Tuple[Dict[str, Any], Path]:
        """Build review config dict and persist to disk.

        Returns ``(review_config, config_path)``.
        """
        output_dir = self._output_dir
        doc_path = self._doc_path
        route = self._route
        complexity = self._complexity

        review_config: Dict[str, Any] = {
            "document_path": str(doc_path),
            "quality_tier": review_quality_tier,
            "reviewer_count": min(review_rounds, 5),
            "max_suggestions": 10,
            "scope": scope or "",
            "init_if_missing": True,
        }

        if context_files:
            review_config["context_files"] = context_files
        if warn_cost_usd is not None:
            review_config["warn_cost_usd"] = warn_cost_usd
        if max_cost_usd is not None:
            review_config["max_cost_usd"] = max_cost_usd

        review_config["_ingestion_metadata"] = {
            "route": route.value,
            "complexity_score": complexity.composite,
            "complexity_reasoning": complexity.reasoning,
        }

        output_dir.mkdir(parents=True, exist_ok=True)
        config_path = output_dir / "review-config.json"
        with _tracer.start_as_current_span("io.review_config.write") as _io_span:
            atomic_write_json(config_path, review_config, indent=2)
            if _HAS_OTEL and not isinstance(_io_span, _NoOpSpan):
                _io_span.set_attribute("io.path", str(config_path))

        return review_config, config_path

    # ------------------------------------------------------------------ #
    # 4. Onboarding resolution
    # ------------------------------------------------------------------ #

    def _resolve_onboarding(
        self,
        *,
        onboarding_metadata: Optional[Dict[str, Any]],
        context_files: Optional[List[str]],
    ) -> Optional[Dict[str, Any]]:
        """Resolve onboarding metadata once for both routes."""
        if self._parsed_plan is None:
            return None

        if onboarding_metadata:
            return onboarding_metadata
        elif context_files:
            logger.debug("Onboarding not passed from PREFLIGHT — falling back to disk load")
            return self._workflow._load_onboarding_metadata(context_files, self._output_dir)
        return None

    # ------------------------------------------------------------------ #
    # 5. Task derivation
    # ------------------------------------------------------------------ #

    def _derive_tasks(
        self,
        *,
        translation_quality: Optional[Dict[str, Any]],
        requirement_hints: Optional[Dict[str, Dict[str, Any]]],
        onboarding_resolved: Optional[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Derive tasks from parsed plan features."""
        parsed_plan = self._parsed_plan
        if parsed_plan is None:
            return []

        return self._workflow._derive_tasks_from_features(
            parsed_plan.features,
            parsed_plan.dependency_graph,
            requirement_to_feature=(translation_quality or {}).get(
                "requirement_to_feature", {}
            ),
            artifact_to_feature=(translation_quality or {}).get(
                "artifact_to_feature", {}
            ),
            requirement_hints=requirement_hints or {},
            output_path_conventions=(
                onboarding_resolved.get("output_path_conventions")
                if isinstance(onboarding_resolved, dict)
                else None
            ),
        )

    # ------------------------------------------------------------------ #
    # 6. Forward manifest ID rewrite
    # ------------------------------------------------------------------ #

    def _rewrite_forward_manifest_ids(
        self,
        *,
        forward_manifest_dict: Dict[str, Any],
        tasks: List[Dict[str, Any]],
    ) -> None:
        """Rewrite forward manifest applicable_task_ids using actual task IDs.

        Must run AFTER ``_derive_tasks`` so skipped features and split
        sub-tasks are reflected.
        """
        parsed_plan = self._parsed_plan
        if parsed_plan is None:
            return

        # Build feature_id → [task_id, ...] from actual derived tasks
        actual_fid_to_tids: Dict[str, List[str]] = {}
        for t in tasks:
            fid = t.get("config", {}).get("context", {}).get("feature_id", "")
            if fid:
                actual_fid_to_tids.setdefault(fid, []).append(t["task_id"])

        # C-3 fix: all feature IDs (including skipped)
        all_feature_ids = (
            {f.feature_id for f in parsed_plan.features}
            if parsed_plan.features
            else set()
        )

        if actual_fid_to_tids and forward_manifest_dict.get("contracts"):
            rewritten_contracts = []
            for c_dict in forward_manifest_dict["contracts"]:
                old_ids = c_dict.get("applicable_task_ids") or []
                if not old_ids:
                    rewritten_contracts.append(c_dict)
                    continue
                new_ids: List[str] = []
                for aid in old_ids:
                    mapped = actual_fid_to_tids.get(aid)
                    if mapped:
                        new_ids.extend(mapped)
                    elif aid in all_feature_ids:
                        logger.warning(
                            "Forward manifest: dropping stale feature ID %r from "
                            "contract %r (feature was skipped/filtered)",
                            aid, c_dict.get("contract_id", "?"),
                        )
                    else:
                        new_ids.append(aid)
                if not new_ids:
                    logger.warning(
                        "Forward manifest: dropping contract %r — all applicable "
                        "task IDs were invalidated (stale feature references)",
                        c_dict.get("contract_id", "?"),
                    )
                    continue
                if new_ids != old_ids:
                    c_copy = dict(c_dict)
                    c_copy["applicable_task_ids"] = new_ids
                    rewritten_contracts.append(c_copy)
                else:
                    rewritten_contracts.append(c_dict)
            forward_manifest_dict["contracts"] = rewritten_contracts
        elif forward_manifest_dict.get("contracts") and not actual_fid_to_tids:
            logger.warning(
                "Forward manifest: skipping contract rewrite — no feature-to-task "
                "mappings available (all tasks may have empty feature_id)"
            )

    # ------------------------------------------------------------------ #
    # 7. Shared derived data
    # ------------------------------------------------------------------ #

    def _derive_shared_context(
        self,
        *,
        step_costs: Optional[Dict[str, float]],
        manifest_context: Optional[Dict[str, Any]],
        review_output: Optional[Dict[str, Any]],
        tasks: List[Dict[str, Any]],
    ) -> Tuple[
        Dict[str, float],
        float,
        Dict[str, Any],
        Dict[str, Dict[str, Any]],
        List[Dict[str, Any]],
    ]:
        """Derive shared context data used by both routes.

        Returns ``(costs, total_cost, architectural_context, design_calibration, refine_suggestions)``.
        """
        parsed_plan = self._parsed_plan
        costs = step_costs or {}
        total_cost = sum(costs.values())
        m_ctx = manifest_context or {}

        architectural_context = (
            self._workflow._derive_architectural_context(parsed_plan, m_ctx)
            if parsed_plan is not None
            else {}
        )
        design_calibration = self._workflow._derive_design_calibration(tasks) if tasks else {}

        refine_suggestions = (
            self._workflow._extract_refine_suggestions_for_seed(review_output)
            if review_output
            else []
        )

        return costs, total_cost, architectural_context, design_calibration, refine_suggestions

    # ------------------------------------------------------------------ #
    # 8. Enrichment pipeline (R5)
    # ------------------------------------------------------------------ #

    def _run_enrichment_pipeline(
        self,
        *,
        tasks: List[Dict[str, Any]],
        refine_suggestions: List[Dict[str, Any]],
        forward_manifest: Optional["ForwardManifest"],
    ) -> Optional[EnrichmentDiagnostic]:
        """Composable enrichment pipeline — runs all enrichment in declared order.

        Step 1: Deterministic enrichment (REQ-TDE-1xx)
        Step 2: Micro-ingest classification (REQ-MI-1xx)
        Step 3: Micro-ingest generation (REQ-MI-2xx/3xx)

        Returns the enrichment diagnostic (or ``None``).
        """
        parsed_plan = self._parsed_plan
        if not tasks or parsed_plan is None:
            return None

        _kc = getattr(self._workflow, "_kaizen_config", None) or PlanIngestionKaizenConfig()

        # Step 1: Deterministic enrichment
        from .plan_ingestion_enrichment import enrich_tasks_deterministic

        _enrichment_diag = enrich_tasks_deterministic(
            tasks,
            parsed_plan.features,
            plan_text=parsed_plan.raw_text,
            refine_suggestions=refine_suggestions or None,
            enrich_negative_scope=_kc.enrich_negative_scope,
            enrich_requirement_refs=_kc.enrich_requirement_refs,
            enrich_target_files=_kc.enrich_target_files,
            enrich_api_signatures=_kc.enrich_api_signatures,
            enrich_refine_suggestions=_kc.enrich_refine_suggestions,
            enrich_req_proximity_chars=_kc.enrich_req_proximity_chars,
        )

        # Step 2: Micro-ingest classification
        _mi_report = None
        if _kc.micro_ingest_enabled:
            try:
                from .plan_ingestion_micro_ingest import classify_enrichment_routes

                _mi_report = classify_enrichment_routes(
                    tasks,
                    parsed_plan.features,
                    forward_manifest=forward_manifest,
                )
            except Exception:
                logger.warning(
                    "micro_ingest: classification failed — skipping",
                    exc_info=True,
                )

        # Step 3: Micro-ingest generation
        if _mi_report is not None and _mi_report.routes:
            _mi_engine = None
            if _kc.micro_ingest_tier_2_enabled:
                try:
                    from startd8.micro_prime.engine import MicroPrimeEngine
                    from startd8.micro_prime.models import MicroPrimeConfig

                    _mi_engine = MicroPrimeEngine(MicroPrimeConfig(
                        local_max_attempts=1,
                        repair_enabled=True,
                        semantic_verification_enabled=False,
                        max_tokens=512,
                        temperature=0.1,
                        escalation_enabled=False,
                    ))
                except Exception as exc:
                    logger.warning(
                        "micro_ingest: Ollama engine init failed: %s — tier_2 disabled", exc,
                    )

            try:
                from .plan_ingestion_micro_ingest import enrich_tasks_micro_ingest

                enrich_tasks_micro_ingest(
                    tasks,
                    _mi_report.routes,
                    parsed_plan.features,
                    forward_manifest=forward_manifest,
                    tier_0_enabled=_kc.micro_ingest_tier_0_enabled,
                    tier_1_enabled=_kc.micro_ingest_tier_1_enabled,
                    tier_2_enabled=_kc.micro_ingest_tier_2_enabled,
                    max_lines=_kc.micro_ingest_max_lines,
                    ollama_timeout_s=_kc.micro_ingest_ollama_timeout_s,
                    ollama_per_element_s=_kc.micro_ingest_ollama_per_element_s,
                    micro_prime_engine=_mi_engine,
                )
            except Exception:
                logger.warning(
                    "micro_ingest: enrichment failed — skipping",
                    exc_info=True,
                )

        return _enrichment_diag

    # ------------------------------------------------------------------ #
    # 9. Build seed artifacts
    # ------------------------------------------------------------------ #

    def _build_seed_artifacts(
        self,
        *,
        config_path: Path,
        onboarding_resolved: Optional[Dict[str, Any]],
        refine_suggestions: List[Dict[str, Any]],
        review_output: Optional[Dict[str, Any]],
        stub_manifest: Optional[List[Dict[str, Any]]],
        skeleton_sources: Optional[Dict[str, str]],
        element_tiers: Optional[Dict[str, Dict[str, Any]]],
    ) -> Tuple[Dict[str, Any], Optional[Dict[str, Any]], Optional[str]]:
        """Build artifacts dict, onboarding_var, and source_checksum.

        Returns ``(artifacts, onboarding_var, source_checksum_val)``.
        """
        doc_path = self._doc_path

        artifacts_out: Dict[str, Any] = {
            "plan_document_path": str(doc_path),
            "review_config_path": str(config_path),
        }
        ob_var: Optional[Dict[str, Any]] = None
        sc_val: Optional[str] = None

        if onboarding_resolved:
            ob_var = dict(onboarding_resolved)
            amp = onboarding_resolved.get("artifact_manifest_path")
            pcp = onboarding_resolved.get("project_context_path")
            if amp:
                artifacts_out["artifact_manifest_path"] = str(amp)
            if pcp:
                artifacts_out["project_context_path"] = str(pcp)
            ex = onboarding_resolved.get("example_artifacts")
            if ex and isinstance(ex, dict) and not is_omitted(ex):
                artifacts_out["example_artifacts"] = dict(ex)
            cg = onboarding_resolved.get("coverage_gaps")
            if cg and isinstance(cg, list):
                artifacts_out["coverage_gaps"] = list(cg)
            sc = onboarding_resolved.get("source_checksum") or onboarding_resolved.get(
                "export_provenance_checksum"
            )
            if sc and isinstance(sc, str):
                artifacts_out["source_checksum"] = sc
                sc_val = sc

        if ob_var is None:
            ob_var = {}
        ob_var["refine_suggestions"] = refine_suggestions
        if onboarding_resolved:
            artifacts_out["onboarding"] = ob_var

        if review_output:
            apply_data = review_output.get("apply", {})
            triage_data = review_output.get("triage", {})
            artifacts_out["refine_provenance"] = {
                "origin_phase": "ingestion.refine",
                "triage_accepted": triage_data.get("accepted", 0),
                "triage_rejected": triage_data.get("rejected", 0),
                "applied_ids": apply_data.get("applied_ids", []),
                "warning_ids": apply_data.get("warning_ids", []),
                "apply_error": apply_data.get("error"),
                "state_path": review_output.get("state_path"),
            }
        else:
            artifacts_out["refine_provenance"] = {
                "origin_phase": "ingestion.refine",
                "apply_enabled": False,
            }

        if stub_manifest:
            artifacts_out["stub_manifest"] = stub_manifest
        if skeleton_sources:
            artifacts_out["skeleton_sources"] = skeleton_sources
        if element_tiers:
            artifacts_out["element_tiers"] = element_tiers

        return artifacts_out, ob_var, sc_val

    # ------------------------------------------------------------------ #
    # 11. Artisan seed construction + quality
    # ------------------------------------------------------------------ #

    def _emit_artisan_seed(
        self,
        *,
        tasks: List[Dict[str, Any]],
        artifacts: Dict[str, Any],
        ingestion_metrics: Dict[str, Any],
        architectural_context: Dict[str, Any],
        design_calibration: Dict[str, Dict[str, Any]],
        onboarding_var: Optional[Dict[str, Any]],
        context_files_list: Optional[List[Dict[str, Any]]],
        service_metadata: Optional[Dict[str, Any]],
        project_metadata: Optional[Dict[str, Any]],
        forward_manifest_dict: Optional[Dict[str, Any]],
        source_checksum_val: Optional[str],
        refine_suggestions: List[Dict[str, Any]],
        review_output: Optional[Dict[str, Any]],
        context_files: Optional[List[str]],
    ) -> Path:
        """Emit artisan-context-seed.json with quality metadata."""
        from .plan_ingestion_workflow import _validate_context_seed, _log_seed_coverage

        parsed_plan = self._parsed_plan
        complexity = self._complexity
        route = self._route
        output_dir = self._output_dir
        doc_path = self._doc_path

        seed = ArtisanContextSeed(
            generated_at=datetime.now(timezone.utc).isoformat(),
            source_checksum=source_checksum_val,
            plan=parsed_plan.to_seed_dict(),
            complexity=complexity.to_seed_dict(),
            tasks=tasks,
            artifacts=artifacts,
            ingestion_metrics=ingestion_metrics,
            architectural_context=architectural_context,
            design_calibration=design_calibration,
            onboarding=onboarding_var,
            context_files=context_files_list,
            service_metadata=service_metadata or None,
            wave_metadata=None,
            lane_assignments=None,
            project_metadata=project_metadata or None,
            forward_manifest=forward_manifest_dict,
        )

        seed_dict = seed.to_dict()

        # Kaizen Phase 3: inject ingestion quality metadata (REQ-KPI-600)
        _task_density = compute_task_density(seed_dict.get("tasks", []))
        _sq_score, _sq_warnings = compute_seed_quality(
            seed_dict, task_density=_task_density,
        )
        _parse_q = {}
        if parsed_plan is not None:
            _parse_q = compute_parse_quality(
                parsed_plan.features,
                parsed_plan.dependency_graph,
                parsed_plan.mentioned_files,
            )
        _assess_q = {}
        if complexity is not None:
            _dims = [
                complexity.feature_count, complexity.cross_file_deps,
                complexity.api_surface, complexity.test_complexity,
                complexity.integration_depth, complexity.domain_novelty,
                complexity.ambiguity,
            ]
            _assess_q = compute_assess_quality(
                complexity.composite,
                route.value,
                getattr(self._workflow, "_complexity_threshold", 40),
                _dims,
            )
            _margin = _assess_q.get("route_margin", 999)
            if _margin < 10:
                logger.warning(
                    "ASSESS: route_margin=%d (composite=%d, threshold=%d) — "
                    "borderline routing; minor plan changes may flip the route",
                    _margin, complexity.composite,
                    getattr(self._workflow, "_complexity_threshold", 40),
                )
        _density_warnings = compute_density_warnings(_task_density)
        seed_dict["_ingestion_quality"] = {
            "seed_quality_score": _sq_score,
            "features_extracted": _parse_q.get("features_extracted", 0),
            "multi_file_features": _parse_q.get("multi_file_features", 0),
            "route_margin": _assess_q.get("route_margin", 0),
            "field_coverage_warnings": _sq_warnings,
            "density_warnings": _density_warnings,
            "diagnostic_report_path": "plan-ingestion-diagnostic.json",
        }

        if not _validate_context_seed(seed_dict):
            seed_dict["_schema_valid"] = False
        _log_seed_coverage(seed_dict)
        context_seed_path = output_dir / "artisan-context-seed.json"
        with _tracer.start_as_current_span("io.context_seed.write") as _io_span:
            atomic_write_json(context_seed_path, seed_dict, indent=2)
            if _HAS_OTEL and not isinstance(_io_span, _NoOpSpan):
                _io_span.set_attribute("io.path", str(context_seed_path))
                _io_span.set_attribute("io.route", route.value)
                _io_span.set_attribute("io.task_count", len(tasks))

        # Mottainai Rule 6: log propagation chain status
        _triage = review_output.get("triage", {}) if review_output else {}
        if refine_suggestions:
            logger.info(
                "REFINE→seed chain INTACT: %d accepted suggestions forwarded",
                len(refine_suggestions),
            )
        elif _triage.get("accepted", 0) > 0:
            logger.warning(
                "REFINE→seed chain DEGRADED: %d accepted suggestions "
                "available but not forwarded",
                _triage["accepted"],
            )
        else:
            logger.debug("REFINE→seed chain N/A: no accepted suggestions to forward")

        # Mottainai: extend artifact inventory
        self._workflow._extend_inventory_with_ingestion(
            output_dir=output_dir,
            doc_path=doc_path,
            context_seed_path=context_seed_path,
            design_calibration=design_calibration,
            context_files=context_files,
            source_checksum_val=source_checksum_val,
            review_output=review_output,
        )

        return context_seed_path

    # ------------------------------------------------------------------ #
    # 12. Prime seed construction + quality
    # ------------------------------------------------------------------ #

    def _emit_prime_seed(
        self,
        *,
        tasks: List[Dict[str, Any]],
        artifacts: Dict[str, Any],
        ingestion_metrics: Dict[str, Any],
        architectural_context: Dict[str, Any],
        design_calibration: Dict[str, Dict[str, Any]],
        onboarding_var: Optional[Dict[str, Any]],
        context_files_list: Optional[List[Dict[str, Any]]],
        service_metadata: Optional[Dict[str, Any]],
        project_metadata: Optional[Dict[str, Any]],
        forward_manifest_dict: Optional[Dict[str, Any]],
        source_checksum_val: Optional[str],
        refine_suggestions: List[Dict[str, Any]],
        review_output: Optional[Dict[str, Any]],
        context_files: Optional[List[str]],
    ) -> Path:
        """Emit prime-context-seed.json."""
        from .plan_ingestion_workflow import _validate_context_seed, _log_seed_coverage

        parsed_plan = self._parsed_plan
        complexity = self._complexity
        route = self._route
        output_dir = self._output_dir
        doc_path = self._doc_path

        seed_prime = ArtisanContextSeed(
            generated_at=datetime.now(timezone.utc).isoformat(),
            source_checksum=source_checksum_val,
            plan=parsed_plan.to_seed_dict(),
            complexity=complexity.to_seed_dict(),
            tasks=tasks,
            artifacts=artifacts,
            ingestion_metrics=ingestion_metrics,
            architectural_context=architectural_context,
            design_calibration=design_calibration,
            onboarding=onboarding_var,
            context_files=context_files_list,
            service_metadata=service_metadata or None,
            wave_metadata=None,
            lane_assignments=None,
            forward_manifest=forward_manifest_dict,
            project_metadata=project_metadata or None,
        )

        seed_prime_dict = seed_prime.to_dict()
        if not _validate_context_seed(seed_prime_dict):
            seed_prime_dict["_schema_valid"] = False
        _log_seed_coverage(seed_prime_dict, label="prime")
        prime_seed_path = output_dir / "prime-context-seed.json"
        with _tracer.start_as_current_span("io.context_seed.write") as _io_span:
            atomic_write_json(prime_seed_path, seed_prime_dict, indent=2)
            if _HAS_OTEL and not isinstance(_io_span, _NoOpSpan):
                _io_span.set_attribute("io.path", str(prime_seed_path))
                _io_span.set_attribute("io.route", route.value)
                _io_span.set_attribute("io.task_count", len(tasks))

        # Mottainai Rule 6: log propagation chain status (prime)
        _triage_p = review_output.get("triage", {}) if review_output else {}
        if refine_suggestions:
            logger.info(
                "REFINE→prime seed chain INTACT: %d accepted suggestions forwarded",
                len(refine_suggestions),
            )
        elif _triage_p.get("accepted", 0) > 0:
            logger.warning(
                "REFINE→prime seed chain DEGRADED: %d accepted suggestions "
                "available but not forwarded",
                _triage_p["accepted"],
            )
        else:
            logger.debug("REFINE→prime seed chain N/A: no accepted suggestions to forward")

        # Mottainai: extend artifact inventory
        self._workflow._extend_inventory_with_ingestion(
            output_dir=output_dir,
            doc_path=doc_path,
            context_seed_path=prime_seed_path,
            design_calibration=design_calibration,
            context_files=context_files,
            source_checksum_val=source_checksum_val,
            review_output=review_output,
        )

        return prime_seed_path

    # ------------------------------------------------------------------ #
    # 13. Task tracking
    # ------------------------------------------------------------------ #

    def _emit_task_tracking(
        self,
        *,
        tasks: List[Dict[str, Any]],
        tracking_config: Optional[TaskTrackingConfig],
    ) -> Optional[Dict[str, Any]]:
        """Emit task tracking artifacts (opt-in)."""
        parsed_plan = self._parsed_plan
        complexity = self._complexity
        output_dir = self._output_dir

        if tracking_config is None or parsed_plan is None:
            return None

        from .task_tracking_emitter import emit_task_tracking_artifacts

        with _tracer.start_as_current_span("io.task_tracking.write") as _io_span:
            tracking_result = emit_task_tracking_artifacts(
                parsed_plan, complexity, tasks, tracking_config, output_dir,
            )
            if _HAS_OTEL and not isinstance(_io_span, _NoOpSpan):
                _io_span.set_attribute(
                    "io.file_count",
                    tracking_result.get("state_file_count", 0) if tracking_result else 0,
                )

        return tracking_result
