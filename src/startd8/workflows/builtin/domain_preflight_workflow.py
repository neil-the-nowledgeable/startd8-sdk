"""
DomainPreflightWorkflow — Analyze artisan-context-seed.json tasks against
the real project environment and emit an enriched seed with per-task
domain classification, prompt constraints, environment checks, and
post-generation validator specs.

Pipeline:  load → scan → classify → check → enrich

Zero LLM calls — all analysis is deterministic.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from ..base import WorkflowBase, ProgressCallback
from ..models import (
    AgentCount,
    StepResult,
    WorkflowInput,
    WorkflowMetadata,
    WorkflowMetrics,
    WorkflowResult,
)
from ...utils.file_operations import atomic_write_json

from .domain_preflight_models import (
    AvailableDeps,
    CheckStatus,
    DomainClassification,
    EnvironmentCheck,
    PreflightState,
    TaskDomain,
    TaskEnrichment,
)

from .preflight_rules import PreflightRuleRegistry, RuleContext
from .schema_versions import ARTISAN_SCHEMA_VERSION, SUPPORTED_SEED_SCHEMA_VERSIONS
from .preflight_rules._helpers import (
    STDLIB_FALLBACK as _STDLIB_FALLBACK_SET,
    STANDALONE_SCRIPT_DIRS as _STANDALONE_SCRIPT_DIRS_SET,
    LOGGER_RESERVED_FIELDS as _LOGGER_RESERVED_FIELDS_SET,
    parse_relative_imports as _parse_relative_imports_impl,
    file_has_pattern as _file_has_pattern_impl,
    scan_optional_dep_guards as _scan_optional_dep_guards_impl,
    scan_patch_paths as _scan_patch_paths_impl,
    normalize_dep_name as _normalize_dep_name_impl,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Backward-compatible re-exports (existing tests import these names)
# ---------------------------------------------------------------------------

_STDLIB_FALLBACK: Set[str] = _STDLIB_FALLBACK_SET
_STANDALONE_SCRIPT_DIRS: Set[str] = _STANDALONE_SCRIPT_DIRS_SET
_LOGGER_RESERVED_FIELDS: Set[str] = _LOGGER_RESERVED_FIELDS_SET


def _parse_relative_imports(file_path: Path) -> List[str]:
    """Backward-compatible re-export."""
    return _parse_relative_imports_impl(file_path)


def _file_has_pattern(file_path: Path, pattern: str) -> bool:
    """Backward-compatible re-export."""
    return _file_has_pattern_impl(file_path, pattern)


def _scan_optional_dep_guards(file_path: Path) -> List[str]:
    """Backward-compatible re-export."""
    return _scan_optional_dep_guards_impl(file_path)


def _scan_patch_paths(file_path: Path) -> List[str]:
    """Backward-compatible re-export."""
    return _scan_patch_paths_impl(file_path)


def _normalize_dep_name(name: str) -> str:
    """Backward-compatible re-export."""
    return _normalize_dep_name_impl(name)


# ---------------------------------------------------------------------------
# Workflow
# ---------------------------------------------------------------------------

class DomainPreflightWorkflow(WorkflowBase):
    """
    Analyze artisan-context-seed.json tasks against the real project
    environment and emit an enriched seed with per-task domain
    classification, prompt constraints, environment checks, and
    post-generation validator specs.

    Zero LLM calls — all analysis is deterministic.
    """

    @property
    def metadata(self) -> WorkflowMetadata:
        return WorkflowMetadata(
            workflow_id="domain-preflight",
            name="Domain Preflight Workflow",
            description=(
                "Analyze artisan-context-seed tasks against the project "
                "environment and emit an enriched seed with domain "
                "classification, prompt constraints, and validator specs."
            ),
            version="1.2.0",
            capabilities=[
                "domain-classification",
                "environment-analysis",
                "prompt-constraint-generation",
                "preflight-rule-registry",
            ],
            tags=["preflight", "artisan", "domain"],
            requires_agents=False,
            agent_count=AgentCount.NONE,
            min_agents=0,
            max_agents=None,
            inputs=[
                WorkflowInput(
                    name="context_seed_path",
                    type="file",
                    required=True,
                    description="Path to artisan-context-seed.json",
                ),
                WorkflowInput(
                    name="project_root",
                    type="file",
                    required=False,
                    description="Project root directory (default: cwd)",
                ),
            ],
        )

    def _custom_validate(self, config: Dict[str, Any]) -> List[str]:
        errors: List[str] = []
        seed_path = config.get("context_seed_path")
        if seed_path:
            p = Path(str(seed_path)).expanduser()
            if not p.exists() or not p.is_file():
                errors.append(f"context_seed_path does not exist or is not a file: {p}")
        return errors

    # ------------------------------------------------------------------
    # Phase: LOAD
    # ------------------------------------------------------------------

    @staticmethod
    def _phase_load(seed_path: Path) -> Dict[str, Any]:
        """Read and validate the context seed JSON."""
        text = seed_path.read_text(encoding="utf-8")
        data = json.loads(text)

        # Accept schema_version (Item 15) or version for backward compat
        schema_ver = data.get("schema_version") or data.get("version", "")
        if schema_ver not in SUPPORTED_SEED_SCHEMA_VERSIONS:
            raise ValueError(
                f"Unsupported context seed schema version: {schema_ver!r} "
                f"(expected one of {sorted(SUPPORTED_SEED_SCHEMA_VERSIONS)})"
            )

        tasks = data.get("tasks")
        if not isinstance(tasks, list):
            raise ValueError("Context seed missing 'tasks' list")

        return data

    # ------------------------------------------------------------------
    # Phase: SCAN
    # ------------------------------------------------------------------

    @staticmethod
    def _scan_available_deps(project_root: Path) -> AvailableDeps:
        """Scan pyproject.toml + stdlib + project packages."""
        deps = AvailableDeps()

        # Stdlib
        if hasattr(sys, "stdlib_module_names"):
            deps.stdlib = set(sys.stdlib_module_names)
        else:
            deps.stdlib = set(_STDLIB_FALLBACK)

        # pyproject.toml
        pyproject_path = project_root / "pyproject.toml"
        if pyproject_path.exists():
            try:
                # Python 3.11+
                import tomllib
            except ImportError:
                try:
                    import tomli as tomllib  # type: ignore[no-redef]
                except ImportError:
                    tomllib = None  # type: ignore[assignment]

            if tomllib is not None:
                try:
                    with open(pyproject_path, "rb") as f:
                        pyproject = tomllib.load(f)

                    # [project.dependencies]
                    for dep in pyproject.get("project", {}).get("dependencies", []):
                        deps.runtime.add(_normalize_dep_name(dep))

                    # [project.optional-dependencies]
                    for group, group_deps in (
                        pyproject.get("project", {})
                        .get("optional-dependencies", {})
                        .items()
                    ):
                        normalized = set()
                        for dep in group_deps:
                            normalized.add(_normalize_dep_name(dep))
                        deps.optional[group] = normalized

                except Exception as exc:
                    logger.warning("Failed to parse pyproject.toml: %s", exc)

        # Project packages: walk src/ for top-level __init__.py dirs
        src_dir = project_root / "src"
        if src_dir.is_dir():
            for child in src_dir.iterdir():
                if child.is_dir() and (child / "__init__.py").exists():
                    deps.project.add(child.name)

        # Installed packages: scan .venv site-packages
        venv_dir = project_root / ".venv"
        if venv_dir.is_dir():
            for lib_dir in venv_dir.glob("lib/python*/site-packages"):
                if lib_dir.is_dir():
                    for item in lib_dir.iterdir():
                        name = item.name
                        # Skip internal/metadata directories
                        if name.startswith(("_", ".")) or name.endswith(
                            (".dist-info", ".egg-info", ".pth", ".py")
                        ):
                            continue
                        if item.is_dir():
                            # Package directory (has __init__.py or is
                            # namespace package)
                            deps.installed.add(name)
                        elif item.suffix in (".so", ".pyd"):
                            # Single-file extension modules
                            deps.installed.add(item.stem)
                    break  # Only scan the first matching site-packages

        return deps

    # ------------------------------------------------------------------
    # Phase: CLASSIFY
    # ------------------------------------------------------------------

    @staticmethod
    def _classify_domain(
        target_file: str, project_root: Path
    ) -> DomainClassification:
        """Classify the domain for a target file path."""
        p = Path(target_file)
        ext = p.suffix.lower()
        name = p.name.lower()
        parts = p.parts

        # Non-Python files
        if ext != ".py":
            if ext == ".toml":
                return DomainClassification(
                    task_id="", target_file=target_file,
                    domain=TaskDomain.CONFIG_TOML,
                    reasoning=f"File extension is {ext}",
                )
            if ext in (".yaml", ".yml"):
                return DomainClassification(
                    task_id="", target_file=target_file,
                    domain=TaskDomain.CONFIG_YAML,
                    reasoning=f"File extension is {ext}",
                )
            if ext == ".json":
                return DomainClassification(
                    task_id="", target_file=target_file,
                    domain=TaskDomain.CONFIG_JSON,
                    reasoning=f"File extension is {ext}",
                )
            if ext:
                return DomainClassification(
                    task_id="", target_file=target_file,
                    domain=TaskDomain.NON_PYTHON,
                    reasoning=f"Non-Python extension: {ext}",
                )
            return DomainClassification(
                task_id="", target_file=target_file,
                domain=TaskDomain.UNKNOWN,
                reasoning="No file extension",
            )

        # Python test files
        if name.startswith("test_") or "test" in parts or "tests" in parts:
            return DomainClassification(
                task_id="", target_file=target_file,
                domain=TaskDomain.PYTHON_TEST,
                reasoning="Test file (name starts with test_ or path contains test/tests)",
            )

        # Python package module vs single module
        target_dir = (project_root / p).parent
        if target_dir.is_dir():
            has_init = (target_dir / "__init__.py").exists()
            py_siblings = [
                f.name for f in target_dir.iterdir()
                if f.suffix == ".py" and f.name != p.name and f.name != "__init__.py"
            ]

            # Override: conventional standalone script directories
            # (scripts/, bin/, tools/, examples/) are NOT packages
            # even with many .py siblings — they contain executables.
            dir_name = target_dir.name.lower()
            if dir_name in _STANDALONE_SCRIPT_DIRS and not has_init:
                return DomainClassification(
                    task_id="", target_file=target_file,
                    domain=TaskDomain.PYTHON_SINGLE_MODULE,
                    reasoning=(
                        f"Standalone script directory '{dir_name}' "
                        f"(no __init__.py, {len(py_siblings)} siblings)"
                    ),
                )

            if has_init or len(py_siblings) >= 2:
                return DomainClassification(
                    task_id="", target_file=target_file,
                    domain=TaskDomain.PYTHON_PACKAGE_MODULE,
                    reasoning=(
                        f"Package module: dir has __init__.py={has_init}, "
                        f"{len(py_siblings)} .py siblings"
                    ),
                )

        return DomainClassification(
            task_id="", target_file=target_file,
            domain=TaskDomain.PYTHON_SINGLE_MODULE,
            reasoning="Single Python module (no __init__.py, fewer than 2 siblings)",
        )

    # ------------------------------------------------------------------
    # Phase: CHECK  (delegated to PreflightRuleRegistry)
    # ------------------------------------------------------------------

    @staticmethod
    def _run_environment_checks(
        domain: TaskDomain,
        target_file: str,
        project_root: Path,
        available_deps: AvailableDeps,
    ) -> List[EnvironmentCheck]:
        """Run per-domain environment readiness checks via the rule registry."""
        target_path = project_root / target_file
        ctx = RuleContext(
            target_file=target_file,
            target_path=target_path,
            target_dir=target_path.parent,
            project_root=project_root,
            domain=domain,
            available_deps=available_deps,
        )
        contribution = PreflightRuleRegistry.evaluate_all(ctx)
        return contribution.checks

    @staticmethod
    def _multi_file_checks(
        target_files: List[str],
        estimated_loc: Optional[int] = None,
    ) -> List[EnvironmentCheck]:
        """Layer A (defense-in-depth): multi-file risk checks at seed enrichment.

        These fire at the earliest detection point — before any LLM calls —
        so dry-runs and dress-rehearsals surface the risk in their reports.
        Complements Layer B (chunk-building in context_seed_handlers) and
        Layer C (post-generation metadata in lead_contractor).
        """
        checks: List[EnvironmentCheck] = []
        if len(target_files) <= 1:
            return checks

        checks.append(EnvironmentCheck(
            check_name="multi_file_split_risk",
            status=CheckStatus.WARN,
            message=(
                f"Task targets {len(target_files)} files — "
                f"LLM may omit some code blocks"
            ),
            detail=(
                f"Target files: {', '.join(target_files)}. "
                f"Multi-file tasks have higher risk of incomplete output. "
                f"Defense layers: prompt checklist, __init__.py constraint, "
                f"content-heuristic extraction, retry with role hints, "
                f"stub fallback."
            ),
        ))

        init_files = [f for f in target_files if f.endswith("__init__.py")]
        if init_files:
            checks.append(EnvironmentCheck(
                check_name="init_py_in_multi_file",
                status=CheckStatus.WARN,
                message=(
                    f"__init__.py among {len(target_files)} targets — "
                    f"commonly skipped by LLM drafters"
                ),
                detail=(
                    f"Files: {', '.join(init_files)}. "
                    f"Models treat __init__.py as optional because it's "
                    f"'just imports'. Dedicated constraints and extraction "
                    f"heuristics are active."
                ),
            ))

        if estimated_loc and estimated_loc > 200:
            checks.append(EnvironmentCheck(
                check_name="multi_file_high_loc",
                status=CheckStatus.WARN,
                message=(
                    f"Multi-file task with {estimated_loc} estimated LOC — "
                    f"truncation may compound split failure"
                ),
                detail=(
                    "Consider splitting into single-file tasks, or increase "
                    "implement_max_output_tokens in design_calibration."
                ),
            ))

        return checks

    # ------------------------------------------------------------------
    # Phase: ENRICH  (delegated to PreflightRuleRegistry)
    # ------------------------------------------------------------------

    @staticmethod
    def _build_enrichment(
        task_id: str,
        domain: TaskDomain,
        domain_reasoning: str,
        target_file: str,
        project_root: Path,
        available_deps: AvailableDeps,
        checks: List[EnvironmentCheck],
    ) -> TaskEnrichment:
        """Build prompt constraints and validator specs for a task."""
        target_path = project_root / target_file
        ctx = RuleContext(
            target_file=target_file,
            target_path=target_path,
            target_dir=target_path.parent,
            project_root=project_root,
            domain=domain,
            available_deps=available_deps,
        )
        contribution = PreflightRuleRegistry.evaluate_all(ctx)

        enrichment = TaskEnrichment(
            task_id=task_id,
            domain=domain,
            domain_reasoning=domain_reasoning,
            environment_checks=checks,
            prompt_constraints=list(contribution.constraints),
            post_generation_validators=list(contribution.validators),
        )

        # For package-module domain, populate available_siblings from
        # the PackageModuleConstraintsRule's constraint text.
        if domain == TaskDomain.PYTHON_PACKAGE_MODULE:
            target_dir = target_path.parent
            if target_dir.is_dir():
                target_name = Path(target_file).name
                enrichment.available_siblings = sorted([
                    f.stem for f in target_dir.iterdir()
                    if f.suffix == ".py"
                    and f.name != target_name
                    and f.name != "__init__.py"
                ])

        # Hash existing content if target file exists
        if target_path.exists() and target_path.is_file():
            try:
                content = target_path.read_bytes()
                enrichment.existing_content_hash = hashlib.sha256(content).hexdigest()[:16]
            except Exception:
                pass

        return enrichment

    # ------------------------------------------------------------------
    # Main execution
    # ------------------------------------------------------------------

    def _execute(
        self,
        config: Dict[str, Any],
        agents: Optional[List[Any]],
        on_progress: Optional[ProgressCallback],
    ) -> WorkflowResult:
        started_at = datetime.now(timezone.utc)
        steps: List[StepResult] = []
        state = PreflightState()

        seed_path = Path(str(config["context_seed_path"])).expanduser().resolve()
        project_root = Path(
            str(config.get("project_root", "."))
        ).expanduser().resolve()

        state.seed_path = str(seed_path)
        state.project_root = str(project_root)

        total_steps = 5
        current_step = 0

        def progress(msg: str):
            nonlocal current_step
            current_step += 1
            self._emit_progress(on_progress, current_step, total_steps, msg)

        def _fail(error_msg: str) -> WorkflowResult:
            state.current_phase = "failed"
            state.error = error_msg
            return WorkflowResult.from_error(
                self.metadata.workflow_id, error_msg, steps=steps,
            )

        try:
            # --- LOAD ---
            progress("Loading context seed")
            state.current_phase = "load"
            t0 = time.time()

            seed_data = self._phase_load(seed_path)
            tasks = seed_data.get("tasks", [])
            state.task_count = len(tasks)

            load_step = StepResult(
                step_name="load",
                output=f"Loaded {len(tasks)} tasks from {seed_path.name}",
                time_ms=int((time.time() - t0) * 1000),
            )
            steps.append(load_step)

            # --- SCAN ---
            progress("Scanning available dependencies")
            state.current_phase = "scan"
            t0 = time.time()

            available_deps = self._scan_available_deps(project_root)

            scan_step = StepResult(
                step_name="scan",
                output=(
                    f"Found {len(available_deps.runtime)} runtime deps, "
                    f"{len(available_deps.stdlib)} stdlib modules, "
                    f"{len(available_deps.project)} project packages"
                ),
                time_ms=int((time.time() - t0) * 1000),
            )
            steps.append(scan_step)

            # --- CLASSIFY + CHECK + ENRICH (per task) ---
            progress("Classifying task domains")
            state.current_phase = "classify"
            t0_classify = time.time()

            domain_summary: Dict[str, int] = {}
            check_summary: Dict[str, int] = {"pass": 0, "warn": 0, "fail": 0, "skip": 0}
            enrichments: List[TaskEnrichment] = []

            for task in tasks:
                task_id = task.get("task_id", "unknown")
                task_config = task.get("config", {})
                context = task_config.get("context", {})
                target_files = context.get("target_files", [])

                # Use first target file for classification
                target_file = target_files[0] if target_files else ""
                task_title = task.get("title", "")
                task_labels = task.get("labels", [])
                if not target_file:
                    logger.warning(
                        "DOMAIN unclassified: %s (%s) — no target files. "
                        "labels=%s, title=%r",
                        task_id, task_title, task_labels, task_title,
                    )
                    enrichments.append(TaskEnrichment(
                        task_id=task_id,
                        domain=TaskDomain.UNKNOWN,
                        domain_reasoning="No target files specified",
                    ))
                    domain_summary["unknown"] = domain_summary.get("unknown", 0) + 1
                    continue

                # Classify
                classification = self._classify_domain(target_file, project_root)
                classification.task_id = task_id
                domain = classification.domain
                domain_summary[domain.value] = domain_summary.get(domain.value, 0) + 1

                if domain == TaskDomain.UNKNOWN:
                    logger.warning(
                        "DOMAIN unclassified: %s (%s) → unknown. "
                        "target=%s, labels=%s, reasoning=%s",
                        task_id, task_title, target_file,
                        task_labels, classification.reasoning,
                    )
                else:
                    logger.info(
                        "DOMAIN classified: %s (%s) → %s. "
                        "target=%s, reasoning=%s",
                        task_id, task_title, domain.value,
                        target_file, classification.reasoning,
                    )

                # Check — per-file domain checks
                checks = self._run_environment_checks(
                    domain, target_file, project_root, available_deps,
                )

                # Layer A (defense-in-depth): multi-file risk checks.
                # Fires at seed-enrichment time — the earliest detection
                # point, before any LLM calls.
                estimated_loc = task_config.get("context", {}).get(
                    "estimated_loc"
                )
                multi_checks = self._multi_file_checks(
                    target_files, estimated_loc=estimated_loc,
                )
                checks.extend(multi_checks)

                for check in checks:
                    check_summary[check.status.value] = (
                        check_summary.get(check.status.value, 0) + 1
                    )

                # Enrich
                enrichment = self._build_enrichment(
                    task_id, domain, classification.reasoning,
                    target_file, project_root, available_deps, checks,
                )
                enrichments.append(enrichment)
                state.enriched_count += 1

            state.check_summary = check_summary

            classify_step = StepResult(
                step_name="classify_check_enrich",
                output=(
                    f"Classified {len(tasks)} tasks: "
                    f"{json.dumps(domain_summary)}"
                ),
                time_ms=int((time.time() - t0_classify) * 1000),
            )
            steps.append(classify_step)

            # Emit progress for check phase
            progress("Running environment checks")
            state.current_phase = "check"
            # Checks already done above in the loop

            # --- ENRICH (write output) ---
            progress("Writing enriched seed")
            state.current_phase = "enrich"
            t0 = time.time()

            # Build enriched seed: copy original with _enrichment per task
            enriched_seed = dict(seed_data)
            enrichment_by_id = {e.task_id: e for e in enrichments}

            enriched_tasks = []
            for task in enriched_seed.get("tasks", []):
                enriched_task = dict(task)
                task_id = task.get("task_id", "unknown")
                enrich = enrichment_by_id.get(task_id)
                if enrich:
                    enriched_task["_enrichment"] = enrich.to_dict()
                enriched_tasks.append(enriched_task)
            enriched_seed["tasks"] = enriched_tasks

            # Top-level _preflight summary
            enriched_seed["_preflight"] = {
                "workflow_version": self.metadata.version,
                "available_deps_count": len(available_deps.all_importable),
                "check_summary": check_summary,
                "domain_summary": domain_summary,
                "generated_at": datetime.now(timezone.utc).isoformat(),
            }

            # Write enriched seed alongside original
            base_stem = seed_path.stem.removesuffix("-enriched")
            enriched_name = f"{base_stem}-enriched{''.join(seed_path.suffixes)}"
            enriched_path = seed_path.parent / enriched_name
            atomic_write_json(enriched_path, enriched_seed, indent=2)

            enrich_step = StepResult(
                step_name="enrich",
                output=f"Wrote {enriched_path}",
                time_ms=int((time.time() - t0) * 1000),
            )
            steps.append(enrich_step)

            # --- DONE ---
            state.current_phase = "completed"
            completed_at = datetime.now(timezone.utc)
            total_ms = int((completed_at - started_at).total_seconds() * 1000)

            output: Dict[str, Any] = {
                "enriched_seed_path": str(enriched_path),
                "original_seed_path": str(seed_path),
                "project_root": str(project_root),
                "task_count": len(tasks),
                "domain_summary": domain_summary,
                "check_summary": check_summary,
                "available_deps_count": len(available_deps.all_importable),
            }

            return WorkflowResult(
                workflow_id=self.metadata.workflow_id,
                success=True,
                output=output,
                metrics=WorkflowMetrics(
                    total_time_ms=total_ms,
                    step_count=len(steps),
                ),
                steps=steps,
                started_at=started_at,
                completed_at=completed_at,
            )

        except Exception as exc:
            logger.error("Domain preflight failed: %s", exc, exc_info=True)
            return _fail(str(exc))
