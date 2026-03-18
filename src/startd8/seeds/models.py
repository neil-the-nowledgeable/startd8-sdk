"""
Seed data models — contractor-agnostic envelope and parsed task.

* ``ContextSeed`` — renamed from ``ArtisanContextSeed``, adds ``route`` field.
* ``SeedTask`` — parsed task with ``from_seed_entry()`` factory.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ..logging_config import get_logger
from .schema_versions import SEED_SCHEMA_VERSION

logger = get_logger(__name__)

__all__ = ["ContextSeed", "SeedTask"]

# Duplicated from artisan_contractor to avoid heavyweight import
_SAFE_TASK_ID_RE = re.compile(r"^[A-Za-z0-9._-]+$")

# Confidence scores for dependency source provenance
_DEPS_SOURCE_CONFIDENCE: Dict[str, float] = {
    "pyproject": 1.0,
    "requirements_txt": 0.85,
    "setup_cfg": 0.85,
    "venv_only": 0.5,
    "stdlib_only": 0.2,
}


@dataclass
class ContextSeed:
    """Contractor-agnostic context seed envelope."""

    version: str = "1.0.0"
    schema_version: str = SEED_SCHEMA_VERSION
    generated_at: str = ""
    source_checksum: Optional[str] = None
    generator: str = "plan-ingestion"
    plan: Optional[Dict[str, Any]] = None
    complexity: Optional[Dict[str, Any]] = None
    tasks: List[Dict[str, Any]] = field(default_factory=list)
    artifacts: Dict[str, Any] = field(default_factory=dict)
    ingestion_metrics: Dict[str, Any] = field(default_factory=dict)
    onboarding: Optional[Dict[str, Any]] = None
    architectural_context: Optional[Dict[str, Any]] = None
    design_calibration: Optional[Dict[str, Dict[str, Any]]] = None
    context_files: Optional[List[Dict[str, Any]]] = None
    service_metadata: Optional[Dict[str, Any]] = None
    service_communication_graph: Optional[Dict[str, Any]] = None  # REQ-SIG-200
    wave_metadata: Optional[Dict[str, Any]] = None
    lane_assignments: Optional[Dict[str, int]] = None
    project_metadata: Optional[Dict[str, Any]] = None
    forward_manifest: Optional[Dict[str, Any]] = None
    route: Optional[str] = None
    generation_profile: Optional[str] = None  # REQ-GPC-400
    capability_coverage_map: Optional[Dict[str, List[str]]] = None  # OI-005

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "version": self.version,
            "schema_version": self.schema_version,
            "generated_at": self.generated_at,
            "source_checksum": self.source_checksum,
            "generator": self.generator,
            "plan": self.plan,
            "complexity": self.complexity,
            "tasks": list(self.tasks),
            "artifacts": dict(self.artifacts),
            "ingestion_metrics": dict(self.ingestion_metrics),
        }
        if self.architectural_context is not None:
            d["architectural_context"] = self.architectural_context
        if self.design_calibration is not None:
            d["design_calibration"] = self.design_calibration
        if self.onboarding is not None:
            d["onboarding"] = self.onboarding
        if self.context_files is not None:
            d["context_files"] = self.context_files
        if self.service_metadata is not None:
            d["service_metadata"] = self.service_metadata
        if self.service_communication_graph is not None:
            d["service_communication_graph"] = self.service_communication_graph
        if self.wave_metadata is not None:
            d["wave_metadata"] = self.wave_metadata
        if self.lane_assignments is not None:
            d["lane_assignments"] = self.lane_assignments
        if self.project_metadata is not None:
            d["project_metadata"] = self.project_metadata
        if self.forward_manifest is not None:
            d["forward_manifest"] = self.forward_manifest
        if self.route is not None:
            d["route"] = self.route
        if self.generation_profile is not None:
            d["generation_profile"] = self.generation_profile
        if self.capability_coverage_map is not None:
            d["capability_coverage_map"] = self.capability_coverage_map
        return d


@dataclass
class SeedTask:
    """Parsed task from an enriched context seed."""

    task_id: str
    title: str
    task_type: str
    story_points: int
    priority: str
    labels: list[str]
    depends_on: list[str]
    description: str
    target_files: list[str]
    estimated_loc: int
    feature_id: str
    domain: str
    domain_reasoning: str
    environment_checks: list[dict[str, Any]]
    prompt_constraints: list[str]
    post_generation_validators: list[str]
    available_siblings: list[str]
    existing_content_hash: Optional[str]
    design_doc_sections: list[str]
    artifact_types_addressed: list[str]
    file_scope: dict[str, str]
    deps_source: Optional[str] = None
    deps_confidence: float = 1.0
    requirements_text: str = ""
    api_signatures: list[str] = field(default_factory=list)
    protocol: str = ""
    runtime_dependencies: list[str] = field(default_factory=list)
    negative_scope: list[str] = field(default_factory=list)
    mode: str = "create"  # OI-001: "create" or "edit"
    module_path: str = ""  # Go: module path for go.mod
    service_name: str = ""  # Go: service directory name
    java_package: str = ""   # Java: base package
    build_system: str = ""   # Java: "gradle" or "maven"
    java_version: str = ""   # Java: version e.g. "21"
    module_system: str = ""  # Node.js: "commonjs" or "esm"
    node_version: str = ""   # Node.js: version e.g. "20"
    spring_boot: bool = False  # Java: Spring Boot project indicator
    csharp_namespace: str = ""  # C#: root namespace e.g. "MyApp.Services"
    target_framework: str = ""  # C#: .NET target framework e.g. "net8.0"
    wave_index: Optional[int] = None
    complexity_tier_override: Optional[str] = None

    @classmethod
    def from_seed_entry(cls, entry: dict[str, Any]) -> SeedTask:
        """Parse a task entry from the enriched context seed JSON."""
        config = entry.get("config", {})
        context = config.get("context", {})
        enrichment = entry.get("_enrichment", {})

        constraints = list(enrichment.get("prompt_constraints", []))
        for hint in context.get("prompt_hints", []):
            if hint not in constraints:
                constraints.append(hint)

        domain = enrichment.get("domain", "unknown")
        if domain == "unknown":
            try:
                from opentelemetry import trace

                span = trace.get_current_span()
                if span and span.is_recording():
                    span.add_event(
                        "context.defaulted",
                        attributes={
                            "context.field": "domain",
                            "context.default_value": "unknown",
                            "context.expected_source": "domain_preflight._enrichment",
                            "context.task_id": entry.get("task_id", ""),
                        },
                    )
            except Exception:
                logger.debug("OTel span event failed", exc_info=True)
            logger.debug(
                "SeedTask %s: domain defaulted to 'unknown'",
                entry.get("task_id", "?"),
            )

        deps_source = enrichment.get("deps_source")
        deps_confidence = (
            _DEPS_SOURCE_CONFIDENCE.get(deps_source, 1.0) if deps_source else 1.0
        )

        raw_task_id = entry.get("task_id", "")
        if raw_task_id and not _SAFE_TASK_ID_RE.match(raw_task_id):
            logger.warning(
                "Task ID %r contains unsafe characters (must match %s)",
                raw_task_id,
                _SAFE_TASK_ID_RE.pattern,
            )

        raw_depends = entry.get("depends_on") or []
        for dep_id in raw_depends:
            if (
                isinstance(dep_id, str)
                and dep_id
                and not _SAFE_TASK_ID_RE.match(dep_id)
            ):
                logger.warning(
                    "Task %s: depends_on reference %r contains unsafe characters",
                    raw_task_id,
                    dep_id,
                )

        raw_wave = entry.get("wave_index")
        if raw_wave is not None:
            if not isinstance(raw_wave, int) or isinstance(raw_wave, bool):
                logger.warning(
                    "Task %s: wave_index=%r is not an integer — ignoring",
                    entry.get("task_id"),
                    raw_wave,
                )
                raw_wave = None
            elif raw_wave < 0:
                logger.warning(
                    "Task %s: wave_index=%d is negative — ignoring",
                    entry.get("task_id"),
                    raw_wave,
                )
                raw_wave = None
        wave_index = raw_wave

        _override_raw = (
            context.get("complexity_tier_override")
            or config.get("complexity_tier_override")
            or entry.get("complexity_tier_override")
        )
        complexity_tier_override: Optional[str] = None
        if isinstance(_override_raw, str):
            _normalized = _override_raw.strip().lower()
            if _normalized in {"tier_1", "tier_2", "tier_3"}:
                complexity_tier_override = _normalized
            elif _normalized:
                logger.warning(
                    "Task %s: invalid complexity_tier_override %r — ignoring",
                    entry.get("task_id", "?"),
                    _override_raw,
                )

        task = cls(
            task_id=entry.get("task_id", ""),
            title=entry.get("title", ""),
            task_type=entry.get("task_type", "task"),
            story_points=entry.get("story_points", 0),
            priority=entry.get("priority", "medium"),
            labels=entry.get("labels", []),
            depends_on=entry.get("depends_on", []),
            description=config.get("task_description", ""),
            target_files=context.get("target_files", []),
            estimated_loc=context.get("estimated_loc", 0),
            feature_id=context.get("feature_id", ""),
            domain=domain,
            domain_reasoning=enrichment.get("domain_reasoning", ""),
            environment_checks=enrichment.get("environment_checks", []),
            prompt_constraints=constraints,
            post_generation_validators=enrichment.get(
                "post_generation_validators", []
            ),
            available_siblings=enrichment.get("available_siblings", []),
            existing_content_hash=enrichment.get("existing_content_hash"),
            design_doc_sections=context.get("design_doc_sections", []),
            artifact_types_addressed=context.get("artifact_types_addressed", []),
            file_scope=context.get("_file_scope", {}),
            deps_source=deps_source,
            deps_confidence=deps_confidence,
            requirements_text=config.get("requirements_text", ""),
            api_signatures=context.get("api_signatures", []),
            protocol=context.get("protocol", ""),
            runtime_dependencies=context.get("runtime_dependencies", []),
            negative_scope=context.get("negative_scope", []),
            mode=context.get("mode", "create"),
            module_path=context.get("module_path", ""),
            service_name=context.get("service_name", ""),
            java_package=context.get("java_package", ""),
            build_system=context.get("build_system", ""),
            java_version=context.get("java_version", ""),
            module_system=context.get("module_system", ""),
            node_version=context.get("node_version", ""),
            spring_boot=bool(context.get("spring_boot", False)),
            csharp_namespace=context.get("csharp_namespace", ""),
            target_framework=context.get("target_framework", ""),
            wave_index=wave_index,
            complexity_tier_override=complexity_tier_override,
        )
        if not task.task_id:
            raise ValueError(
                f"Seed entry missing required field 'task_id': {entry}"
            )
        if not task.title:
            raise ValueError(
                f"Seed entry missing required field 'title': {entry}"
            )
        return task
