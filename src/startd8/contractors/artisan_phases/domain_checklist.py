"""
Domain Checklist — Thin adapter that loads enrichments from an enriched
seed JSON (produced by DomainPreflightWorkflow) or computes them inline
using the workflow's static methods.

Designed to be injected into DevelopmentPhase so each chunk gets
domain-aware prompt constraints and post-generation validation.
"""

from __future__ import annotations

import ast
import json
import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from startd8.workflows.builtin.domain_preflight_models import (
    AvailableDeps,
    TaskDomain,
    TaskEnrichment,
)
from startd8.workflows.builtin.domain_preflight_workflow import DomainPreflightWorkflow

logger = logging.getLogger(__name__)


# ============================================================================
# POST-VALIDATION DATA CLASSES
# ============================================================================


@dataclass
class PostValidationIssue:
    """A single issue found by a post-generation validator."""

    validator: str
    message: str
    line: Optional[int] = None


@dataclass
class PostValidationResult:
    """Aggregate result of all post-generation validators."""

    passed: bool
    issues: List[PostValidationIssue] = field(default_factory=list)


# ============================================================================
# POST-GENERATION VALIDATORS
# ============================================================================


def _validate_no_relative_imports(
    code: str, enrichment: TaskEnrichment
) -> List[PostValidationIssue]:
    """Flag relative imports in single-module domain."""
    issues: List[PostValidationIssue] = []
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return issues

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.level and node.level > 0:
            issues.append(PostValidationIssue(
                validator="no_relative_imports",
                message=f"Relative import found: from {'.' * node.level}{node.module or ''} import ...",
                line=node.lineno,
            ))
    return issues


def _validate_deps_available(
    code: str, enrichment: TaskEnrichment
) -> List[PostValidationIssue]:
    """Check that imported top-level packages are in available deps."""
    issues: List[PostValidationIssue] = []
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return issues

    # Collect the set of importable names from the enrichment's prompt constraints
    # The constraint line looks like: "Only import from: pkg1, pkg2, ..."
    importable: Optional[set] = None
    for constraint in enrichment.prompt_constraints:
        if constraint.startswith("Only import from:"):
            names_str = constraint.split(":", 1)[1].strip()
            importable = {n.strip() for n in names_str.split(",") if n.strip()}
            break

    if importable is None:
        return issues

    # Always include stdlib — the constraint string may only list public names
    # for readability but all stdlib modules are always importable.
    if hasattr(sys, "stdlib_module_names"):
        importable |= sys.stdlib_module_names

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                top = alias.name.split(".")[0]
                if top not in importable:
                    issues.append(PostValidationIssue(
                        validator="deps_available",
                        message=f"Import '{alias.name}' — top-level '{top}' not in available deps",
                        line=node.lineno,
                    ))
        elif isinstance(node, ast.ImportFrom) and node.module and (not node.level or node.level == 0):
            top = node.module.split(".")[0]
            if top not in importable:
                issues.append(PostValidationIssue(
                    validator="deps_available",
                    message=f"Import from '{node.module}' — top-level '{top}' not in available deps",
                    line=node.lineno,
                ))
    return issues


def _validate_definition_ordering(
    code: str, enrichment: TaskEnrichment
) -> List[PostValidationIssue]:
    """Ensure names used in Field(default_factory=X) are defined before the class."""
    issues: List[PostValidationIssue] = []
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return issues

    # Collect top-level definitions in order
    defined_names: set = set()
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            defined_names.add(node.name)
        elif isinstance(node, ast.ClassDef):
            # Before processing the class, check its field default_factory refs
            for class_node in ast.walk(node):
                if isinstance(class_node, ast.keyword) and class_node.arg == "default_factory":
                    if isinstance(class_node.value, ast.Name):
                        ref_name = class_node.value.id
                        if ref_name not in defined_names:
                            issues.append(PostValidationIssue(
                                validator="definition_ordering",
                                message=f"'{ref_name}' used as default_factory but not defined before class '{node.name}'",
                                line=class_node.value.lineno,
                            ))
            defined_names.add(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    defined_names.add(target.id)

    return issues


def _validate_merge_damage(
    code: str, enrichment: TaskEnrichment
) -> List[PostValidationIssue]:
    """Detect merge damage: duplicate definitions and ordering violations."""
    issues: List[PostValidationIssue] = []
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return issues

    # --- Check 1: Duplicate top-level definitions ---
    seen_names: Dict[str, int] = {}  # name -> first line number
    for node in ast.iter_child_nodes(tree):
        name = None
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            name = node.name
        elif isinstance(node, ast.ClassDef):
            name = node.name

        if name is not None:
            if name in seen_names:
                issues.append(PostValidationIssue(
                    validator="merge_damage",
                    message=(
                        f"Duplicate definition '{name}' "
                        f"(first at line {seen_names[name]}, again at line {node.lineno})"
                    ),
                    line=node.lineno,
                ))
            else:
                seen_names[name] = node.lineno

    # --- Check 2: Definition ordering (default_factory references) ---
    defined_names: set = set()
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            defined_names.add(node.name)
        elif isinstance(node, ast.ClassDef):
            for class_node in ast.walk(node):
                if isinstance(class_node, ast.keyword) and class_node.arg == "default_factory":
                    if isinstance(class_node.value, ast.Name):
                        ref_name = class_node.value.id
                        if ref_name not in defined_names:
                            issues.append(PostValidationIssue(
                                validator="merge_damage",
                                message=(
                                    f"'{ref_name}' used as default_factory but not defined "
                                    f"before class '{node.name}' (possible merge ordering damage)"
                                ),
                                line=class_node.value.lineno,
                            ))
            defined_names.add(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    defined_names.add(target.id)

    return issues


_ValidatorFn = Callable[[str, TaskEnrichment], List[PostValidationIssue]]

_POST_VALIDATORS: Dict[str, _ValidatorFn] = {
    "no_relative_imports": _validate_no_relative_imports,
    "deps_available": _validate_deps_available,
    "definition_ordering": _validate_definition_ordering,
    "merge_damage": _validate_merge_damage,
}


def validate_generated_code(
    code: str, enrichment: TaskEnrichment
) -> PostValidationResult:
    """Run all validators specified in enrichment.post_generation_validators.

    Resolution order per validator name:
    1. Local ``_POST_VALIDATORS`` dict (backward-compatible)
    2. ``PreflightRuleRegistry.get_validator_fn()`` (extensible)
    3. Silently skipped (may be intended for different validation layers)

    Args:
        code: The generated source code string.
        enrichment: The TaskEnrichment with validator specs.

    Returns:
        PostValidationResult indicating pass/fail and any issues found.
    """
    all_issues: List[PostValidationIssue] = []

    for validator_name in enrichment.post_generation_validators:
        fn = _POST_VALIDATORS.get(validator_name)
        if fn is None:
            # Try the registry for externally contributed validators
            try:
                from startd8.workflows.builtin.preflight_rules import (
                    PreflightRuleRegistry,
                )
                fn = PreflightRuleRegistry.get_validator_fn(validator_name)
            except ImportError:
                fn = None
        if fn is None:
            continue
        try:
            issues = fn(code, enrichment)
            all_issues.extend(issues)
        except Exception as exc:
            logger.debug("Validator %s raised: %s", validator_name, exc)

    return PostValidationResult(
        passed=len(all_issues) == 0,
        issues=all_issues,
    )


# ============================================================================
# MAIN ADAPTER CLASS
# ============================================================================


class DomainChecklist:
    """Adapter that provides per-chunk domain enrichments.

    Two modes of operation:
    1. **From enriched seed**: Load a pre-computed enriched seed JSON
       (produced by DomainPreflightWorkflow) and look up enrichments by task_id.
    2. **Inline compute**: Use the workflow's static methods to classify
       and enrich on the fly given a project_root.

    If neither source is available, methods return None gracefully.

    Args:
        project_root: Path to the project root for inline computation.
        enriched_seed_path: Path to the enriched seed JSON file.
    """

    def __init__(
        self,
        project_root: Optional[Path] = None,
        enriched_seed_path: Optional[Path] = None,
    ) -> None:
        self.project_root = project_root
        self.enriched_seed_path = enriched_seed_path
        self._enrichment_map: Optional[Dict[str, TaskEnrichment]] = None
        self._deps_cache: Optional[AvailableDeps] = None
        self._seed_loaded = False
        self.logger = logging.getLogger(__name__)

    def scan_deps(self) -> Optional[AvailableDeps]:
        """Scan project dependencies (cached after first call).

        Returns:
            AvailableDeps if project_root is set, else None.
        """
        if self._deps_cache is not None:
            return self._deps_cache

        if self.project_root is None:
            return None

        self._deps_cache = DomainPreflightWorkflow._scan_available_deps(
            self.project_root
        )
        return self._deps_cache

    def get_enrichment(
        self, chunk_id: str, file_targets: List[str]
    ) -> Optional[TaskEnrichment]:
        """Get domain enrichment for a chunk.

        Resolution order:
        1. Enriched seed lookup by task_id (chunk_id)
        2. Inline computation via static methods (if project_root set)
        3. None

        Args:
            chunk_id: The chunk identifier (maps to task_id in enriched seed).
            file_targets: List of file paths the chunk targets.

        Returns:
            TaskEnrichment or None if no enrichment could be determined.
        """
        # Try enriched seed first
        if self.enriched_seed_path is not None:
            if not self._seed_loaded:
                self._load_enriched_seed()
            if self._enrichment_map is not None and chunk_id in self._enrichment_map:
                return self._enrichment_map[chunk_id]

        # Try inline computation
        if self.project_root is not None and file_targets:
            return self._compute_inline(chunk_id, file_targets[0])

        return None

    def _load_enriched_seed(self) -> None:
        """Parse enriched seed JSON and build task_id -> enrichment map."""
        self._seed_loaded = True

        if self.enriched_seed_path is None or not self.enriched_seed_path.exists():
            self.logger.debug("Enriched seed not found: %s", self.enriched_seed_path)
            return

        try:
            text = self.enriched_seed_path.read_text(encoding="utf-8")
            data = json.loads(text)
        except Exception as exc:
            self.logger.warning("Failed to load enriched seed: %s", exc)
            return

        enrichment_map: Dict[str, TaskEnrichment] = {}
        for task in data.get("tasks", []):
            task_id = task.get("task_id", "")
            enrichment_data = task.get("_enrichment")
            if not enrichment_data or not task_id:
                continue
            try:
                enrichment_map[task_id] = _parse_enrichment(enrichment_data)
            except Exception as exc:
                self.logger.debug(
                    "Skipping enrichment for task %s: %s", task_id, exc
                )

        self._enrichment_map = enrichment_map
        self.logger.debug(
            "Loaded %d enrichments from seed", len(enrichment_map)
        )

    def _compute_inline(
        self, chunk_id: str, target_file: str
    ) -> Optional[TaskEnrichment]:
        """Compute enrichment inline using DomainPreflightWorkflow statics."""
        if self.project_root is None:
            return None

        try:
            classification = DomainPreflightWorkflow._classify_domain(
                target_file, self.project_root
            )
            available_deps = self.scan_deps()
            if available_deps is None:
                available_deps = AvailableDeps()

            checks = DomainPreflightWorkflow._run_environment_checks(
                classification.domain,
                target_file,
                self.project_root,
                available_deps,
            )

            enrichment = DomainPreflightWorkflow._build_enrichment(
                chunk_id,
                classification.domain,
                classification.reasoning,
                target_file,
                self.project_root,
                available_deps,
                checks,
            )
            return enrichment
        except Exception as exc:
            self.logger.debug(
                "Inline enrichment failed for %s: %s", chunk_id, exc
            )
            return None


# ============================================================================
# HELPERS
# ============================================================================


def _parse_enrichment(data: Dict[str, Any]) -> TaskEnrichment:
    """Parse a TaskEnrichment from its dict representation."""
    from startd8.workflows.builtin.domain_preflight_models import (
        CheckStatus,
        EnvironmentCheck,
    )

    checks = []
    for c in data.get("environment_checks", []):
        checks.append(EnvironmentCheck(
            check_name=c["check_name"],
            status=CheckStatus(c["status"]),
            message=c["message"],
            detail=c.get("detail"),
        ))

    return TaskEnrichment(
        task_id=data["task_id"],
        domain=TaskDomain(data["domain"]),
        domain_reasoning=data.get("domain_reasoning", ""),
        environment_checks=checks,
        prompt_constraints=data.get("prompt_constraints", []),
        post_generation_validators=data.get("post_generation_validators", []),
        available_siblings=data.get("available_siblings", []),
        existing_content_hash=data.get("existing_content_hash"),
    )
