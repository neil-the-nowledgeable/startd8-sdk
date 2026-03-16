"""
SeedBuilder — step-by-step builder for unified context seeds.

Usage::

    from startd8.seeds.builder import SeedBuilder

    builder = SeedBuilder()
    builder.set_plan(parsed_plan)
    builder.set_complexity(complexity)
    builder.set_route("artisan")
    builder.derive_tasks(features, dep_graph)
    builder.derive_architectural_context(parsed_plan, manifest_ctx)
    builder.derive_design_calibration()
    builder.set_artifacts(doc_path, config_path, onboarding, review_output, stub_manifest)
    builder.set_context_files(files, base_dir)
    builder.set_service_metadata(features, onboarding)
    builder.set_project_metadata(metadata)
    builder.set_ingestion_metrics(step_costs)

    warnings = builder.validate()
    seed_dict = builder.build()
    builder.write(output_dir / "context-seed.json")
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..logging_config import get_logger
from .derivation import (
    derive_architectural_context,
    derive_design_calibration,
    derive_tasks_from_features,
    extract_refine_suggestions_for_seed,
    infer_service_metadata,
)
from .helpers import (
    context_files_with_checksums,
    ensure_onboarding_in_context_files,
)
from .models import ContextSeed
from .validation import (
    log_seed_coverage,
    validate_context_seed,
    validate_for_route,
    validate_seed_field_coverage,
)

logger = get_logger(__name__)

__all__ = ["SeedBuilder"]


class SeedBuilder:
    """Step-by-step builder for unified context seeds.

    Collects seed data incrementally and produces a single
    ``context-seed.json`` that is consumable by both ArtisanContractor
    and PrimeContractor.
    """

    def __init__(self) -> None:
        self._plan_dict: Optional[Dict[str, Any]] = None
        self._complexity_dict: Optional[Dict[str, Any]] = None
        self._route: Optional[str] = None
        self._tasks: List[Dict[str, Any]] = []
        self._artifacts: Dict[str, Any] = {}
        self._ingestion_metrics: Dict[str, Any] = {}
        self._onboarding: Optional[Dict[str, Any]] = None
        self._architectural_context: Optional[Dict[str, Any]] = None
        self._design_calibration: Optional[Dict[str, Dict[str, Any]]] = None
        self._context_files: Optional[List[Dict[str, Any]]] = None
        self._service_metadata: Optional[Dict[str, Any]] = None
        self._wave_metadata: Optional[Dict[str, Any]] = None
        self._lane_assignments: Optional[Dict[str, int]] = None
        self._project_metadata: Optional[Dict[str, Any]] = None
        self._forward_manifest: Optional[Dict[str, Any]] = None
        self._source_checksum: Optional[str] = None
        self._generation_profile: Optional[str] = None  # REQ-GPC-401
        self._refine_suggestions: List[Dict[str, Any]] = []

    # ------------------------------------------------------------------
    # Builder setters
    # ------------------------------------------------------------------

    def set_plan(self, parsed_plan: Any) -> "SeedBuilder":
        """Set the plan from a ``ParsedPlan`` instance."""
        if not hasattr(parsed_plan, "to_seed_dict"):
            raise TypeError(
                f"parsed_plan must have a to_seed_dict() method, got {type(parsed_plan).__name__}"
            )
        self._plan_dict = parsed_plan.to_seed_dict()
        return self

    def set_complexity(self, complexity: Any) -> "SeedBuilder":
        """Set the complexity from a ``ComplexityScore`` instance."""
        if not hasattr(complexity, "to_seed_dict"):
            raise TypeError(
                f"complexity must have a to_seed_dict() method, got {type(complexity).__name__}"
            )
        self._complexity_dict = complexity.to_seed_dict()
        return self

    def set_route(self, route: str) -> "SeedBuilder":
        """Record which contractor route this seed targets."""
        self._route = route
        return self

    def derive_tasks(
        self,
        features: list,
        dependency_graph: Dict[str, List[str]],
        *,
        requirement_to_feature: Optional[Dict[str, List[str]]] = None,
        artifact_to_feature: Optional[Dict[str, List[str]]] = None,
        requirement_hints: Optional[Dict[str, Dict[str, Any]]] = None,
        output_path_conventions: Optional[Dict[str, Any]] = None,
    ) -> "SeedBuilder":
        """Derive tasks from features using ``seeds.derivation``."""
        self._tasks = derive_tasks_from_features(
            features,
            dependency_graph,
            requirement_to_feature=requirement_to_feature,
            artifact_to_feature=artifact_to_feature,
            requirement_hints=requirement_hints,
            output_path_conventions=output_path_conventions,
        )
        return self

    def set_tasks(self, tasks: List[Dict[str, Any]]) -> "SeedBuilder":
        """Set tasks directly (for pre-derived tasks)."""
        self._tasks = list(tasks)
        return self

    def set_forward_manifest(
        self, manifest_dict: Optional[Dict[str, Any]]
    ) -> "SeedBuilder":
        """Set the forward manifest contracts."""
        self._forward_manifest = manifest_dict
        return self

    def rewrite_forward_manifest_task_ids(self) -> "SeedBuilder":
        """Rewrite ``applicable_task_ids`` in forward manifest contracts.

        Replaces feature IDs with actual derived task IDs (REQ-PC-FM-005).
        Must be called after ``derive_tasks()``.
        """
        if not self._forward_manifest or not self._tasks:
            return self

        actual_fid_to_tids: Dict[str, List[str]] = {}
        for task in self._tasks:
            fid = task.get("config", {}).get("context", {}).get("feature_id", "")
            if fid:
                actual_fid_to_tids.setdefault(fid, []).append(task["task_id"])

        contracts = self._forward_manifest.get("contracts")
        if not isinstance(contracts, list):
            return self

        for contract in contracts:
            if not isinstance(contract, dict):
                continue
            old_ids = contract.get("applicable_task_ids", [])
            if not isinstance(old_ids, list):
                continue
            new_ids: List[str] = []
            for fid in old_ids:
                mapped = actual_fid_to_tids.get(fid, [])
                if mapped:
                    new_ids.extend(mapped)
                else:
                    new_ids.append(fid)
            contract["applicable_task_ids"] = new_ids

        return self

    def derive_architectural_context(
        self,
        parsed_plan: Any,
        manifest_context: Optional[Dict[str, Any]] = None,
    ) -> "SeedBuilder":
        """Derive architectural context from plan + manifest."""
        self._architectural_context = derive_architectural_context(
            parsed_plan, manifest_context or {}
        )
        return self

    def derive_design_calibration(self) -> "SeedBuilder":
        """Derive per-task design depth calibration from tasks."""
        if self._tasks:
            self._design_calibration = derive_design_calibration(self._tasks)
        return self

    def set_artifacts(
        self,
        doc_path: Optional[Path] = None,
        config_path: Optional[Path] = None,
        onboarding: Optional[Dict[str, Any]] = None,
        review_output: Optional[Dict[str, Any]] = None,
        stub_manifest: Optional[list] = None,
    ) -> "SeedBuilder":
        """Build the artifacts dict from paths and onboarding data.

        Args:
            doc_path: Path to the plan document (stored as ``plan_document_path``).
            config_path: Path to review config (stored as ``review_config_path``).
            onboarding: Onboarding metadata dict — keys like
                ``artifact_manifest_path``, ``source_checksum`` are promoted
                into artifacts; the full dict is stored as ``_onboarding``.
            review_output: Review/triage output — refine suggestions are
                extracted and merged into onboarding if present. Must be
                processed *before* onboarding to ensure suggestions are
                available during onboarding assembly.
            stub_manifest: List of stub file entries for the artifacts dict.
        """
        artifacts: Dict[str, Any] = {}
        if doc_path:
            artifacts["plan_document_path"] = str(doc_path)
        if config_path:
            artifacts["review_config_path"] = str(config_path)

        # Extract refine suggestions from review_output FIRST so they are
        # available when assembling onboarding below.
        if review_output:
            self._refine_suggestions = extract_refine_suggestions_for_seed(
                review_output
            )

            triage = review_output.get("triage")
            if isinstance(triage, dict):
                provenance: Dict[str, Any] = {
                    "triage_accepted": triage.get("accepted", 0),
                    "triage_rejected": triage.get("rejected", 0),
                }
                applied_ids = triage.get("applied_suggestion_ids", [])
                if applied_ids:
                    provenance["applied_suggestion_ids"] = applied_ids
                artifacts["refine_provenance"] = provenance

        if onboarding:
            for key in (
                "artifact_manifest_path",
                "project_context_path",
                "example_artifacts",
                "coverage_gaps",
            ):
                val = onboarding.get(key)
                if val:
                    artifacts[key] = val
            self._source_checksum = onboarding.get("source_checksum")

            # REQ-GPC-401: extract generation profile from onboarding
            self._generation_profile = onboarding.get("generation_profile")

            onboarding_var = dict(onboarding)
            if self._refine_suggestions:
                onboarding_var["refine_suggestions"] = self._refine_suggestions
            self._onboarding = onboarding_var

        if stub_manifest:
            artifacts["stub_manifest"] = stub_manifest

        self._artifacts = artifacts
        return self

    def set_context_files(
        self,
        files: Optional[List[str]],
        base_dir: Optional[Path] = None,
        output_dir: Optional[Path] = None,
    ) -> "SeedBuilder":
        """Build context files list with checksums."""
        self._context_files = context_files_with_checksums(files, base_dir)
        if output_dir and self._context_files:
            ensure_onboarding_in_context_files(
                self._context_files, self._onboarding, output_dir
            )
        return self

    def set_service_metadata(
        self,
        features: list,
        onboarding: Optional[Dict[str, Any]] = None,
    ) -> "SeedBuilder":
        """Infer and set service-level metadata."""
        self._service_metadata = infer_service_metadata(features, onboarding)
        return self

    def set_project_metadata(
        self, metadata: Optional[Dict[str, Any]]
    ) -> "SeedBuilder":
        """Set operational project metadata."""
        self._project_metadata = metadata
        return self

    def set_ingestion_metrics(
        self, step_costs: Optional[Dict[str, float]] = None
    ) -> "SeedBuilder":
        """Build ingestion metrics from per-step costs."""
        costs = step_costs or {}
        total_cost = sum(costs.values())
        self._ingestion_metrics = {
            **{f"cost_{k}": v for k, v in costs.items()},
            "total_cost": total_cost,
            "_cost_phases_included": sorted(costs.keys()),
        }
        return self

    def set_wave_metadata(
        self, wave_metadata: Optional[Dict[str, Any]]
    ) -> "SeedBuilder":
        """Set wave computation metadata."""
        self._wave_metadata = wave_metadata
        return self

    def set_lane_assignments(
        self, lane_assignments: Optional[Dict[str, int]]
    ) -> "SeedBuilder":
        """Set lane computation metadata."""
        self._lane_assignments = lane_assignments
        return self

    # ------------------------------------------------------------------
    # Read-only access to intermediate state
    # ------------------------------------------------------------------

    @property
    def tasks(self) -> List[Dict[str, Any]]:
        """Read-only access to derived tasks."""
        return list(self._tasks)

    @property
    def refine_suggestions(self) -> List[Dict[str, Any]]:
        """Read-only access to extracted refine suggestions."""
        return list(self._refine_suggestions)

    # ------------------------------------------------------------------
    # Validate / Build / Write
    # ------------------------------------------------------------------

    def validate(self, route: Optional[str] = None) -> List[str]:
        """Validate the current seed state."""
        seed_dict = self._to_dict()
        effective_route = route or self._route or ""
        if effective_route:
            return validate_for_route(seed_dict, effective_route)
        warnings: List[str] = []
        if not validate_context_seed(seed_dict):
            warnings.append("base schema validation failed")
        warnings.extend(validate_seed_field_coverage(seed_dict))
        return warnings

    def build(self) -> Dict[str, Any]:
        """Build and return the seed dict."""
        return self._to_dict()

    def write(self, path: Path) -> Path:
        """Validate, build, and write the seed to disk."""
        seed_dict = self._to_dict()

        if not validate_context_seed(seed_dict):
            logger.warning("Seed schema validation failed — writing anyway")

        log_seed_coverage(seed_dict, label=self._route or "")

        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            try:
                from ..utils.file_operations import atomic_write_json

                atomic_write_json(path, seed_dict)
            except ImportError:
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(seed_dict, f, indent=2)
        except OSError as e:
            logger.error("Failed to write context seed to %s: %s", path, e)
            raise

        logger.info("Wrote context seed: %s (%d tasks)", path, len(self._tasks))
        return path

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _to_dict(self) -> Dict[str, Any]:
        """Build the seed dictionary from accumulated state."""
        seed = ContextSeed(
            generated_at=datetime.now(timezone.utc).isoformat(),
            source_checksum=self._source_checksum,
            plan=self._plan_dict,
            complexity=self._complexity_dict,
            tasks=list(self._tasks),
            artifacts=dict(self._artifacts),
            ingestion_metrics=dict(self._ingestion_metrics),
            onboarding=self._onboarding,
            architectural_context=self._architectural_context,
            design_calibration=self._design_calibration,
            context_files=self._context_files,
            service_metadata=self._service_metadata,
            wave_metadata=self._wave_metadata,
            lane_assignments=self._lane_assignments,
            project_metadata=self._project_metadata,
            forward_manifest=self._forward_manifest,
            route=self._route,
            generation_profile=self._generation_profile,
        )
        return seed.to_dict()
