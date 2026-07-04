"""REVIEW phase handler."""

from __future__ import annotations

import datetime
import json
import re
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Optional

from startd8.contractors.artisan_contractor import (
    AbstractPhaseHandler,
    WorkflowPhase,
)
from startd8.contractors.context_schema import ReviewPhaseOutput
from startd8.contractors.context_seed.shared import (
    SeedTask,
    _ensure_context_loaded,
    _log_context_completeness,
    _track_onboarding_consumption,
)
from startd8.contractors.protocols import GenerationResult
from startd8.contractors.context_seed.handler_support import (
    HandlerConfig,
    _CACHE_SCHEMA_VERSION,
    _build_provenance_links,
    _capture_task_span_context,
    _coerce_optional_float,
    _compute_design_results_hash,
    _compute_gen_file_hash,
    _format_review_prompt,
    _get_review_template,
    _log_task_boundary_complete,
    _log_task_boundary_start,
    _log_task_timing,
)
from startd8.contractors.context_seed.tracing import _HAS_OTEL, _phase_tracer
from startd8.contractors.gate_contracts import GateEmitter
from startd8.logging_config import get_logger
from startd8.utils.file_operations import atomic_write_json
from startd8.utils.retry import (
    RetryConfig,
    _calculate_delay,
    _is_retryable_exception,
)
from startd8.utils.token_usage import (
    token_usage_cost,
    token_usage_input,
    token_usage_output,
)

logger = get_logger("startd8.contractors.context_seed_handlers")


class ReviewPhaseHandler(AbstractPhaseHandler):
    """REVIEW phase: LLM-based quality review of generated implementations.

    In dry-run mode: reports review checklist (unchanged).
    In real mode: sends generated code to a review agent for
    quality scoring, then aggregates pass/fail verdicts.
    """

    def __init__(self, handler_config: Optional[HandlerConfig] = None) -> None:
        self.config = handler_config or HandlerConfig()
        self._review_agent: Any = None
        self._last_review_prompt_diagnostics: dict[str, Any] = {}

    # ------------------------------------------------------------------
    # Review prompt template — loaded from review.yaml
    # ------------------------------------------------------------------

    # Inline fallback used only when review.yaml is missing (e.g.
    # downstream installs that haven't updated).
    _REVIEW_PROMPT_TEMPLATE_FALLBACK = """You are reviewing generated code for quality and correctness.

## Task
**ID:** {task_id}
**Title:** {title}
**Domain:** {domain}

## Task Description
{description}

## Prompt Constraints
{constraints}

## Generated Code
```
{generated_code}
```

## Test Results
{test_results}

## Review Instructions
Evaluate the implementation against the task description and constraints.

## Required Output Format

### Score: [0-100]

### Verdict: [PASS/FAIL]
PASS if score >= {pass_threshold} and no blocking issues.

### Strengths
- [What was done well]

### Issues
- [severity: BLOCKING/MAJOR/MINOR] [description]

### Suggestions
- [Specific improvements]
"""

    # PAQ-102/502: deterministic REVIEW section budgets and global cap.
    _REVIEW_SECTION_BUDGETS: dict[str, int] = {
        "constraint_checklist": 2000,
        "project_context": 2000,
        "design_compliance": 8000,
        "parameter_sources": 1200,
        "semantic_conventions": 1200,
        "service_metadata": 1200,
        "refine_compliance": 1400,
        "truncation_warning": 800,
        "deps_advisory": 600,
        "call_graph": 2000,
        "forward_contract_violations": 1800,
    }
    _REVIEW_TOTAL_SECTION_BUDGET = 14000

    @staticmethod
    def _get_review_user_template() -> str:
        """Return the review_user template, preferring YAML over fallback."""
        tmpl = _get_review_template("review_user")
        if tmpl is not None:
            return tmpl
        return ReviewPhaseHandler._REVIEW_PROMPT_TEMPLATE_FALLBACK

    def _resolve_review_agent(self) -> Any:
        """Lazily resolve the review agent from config.

        Creates a :class:`BaseAgent` instance using the lead_agent spec
        with low temperature for consistent reviews.

        Returns:
            A BaseAgent instance.
        """
        if self._review_agent is not None:
            return self._review_agent

        from startd8.utils.agent_resolution import resolve_agent_spec

        agent_spec = self.config.review_agent or self.config.lead_agent

        resolve_kwargs: dict[str, Any] = {
            "name": "context-seed-reviewer",
            "temperature": self.config.review_temperature,
            "enable_prompt_caching": self.config.enable_prompt_caching,
        }
        if self.config.max_tokens is not None:
            resolve_kwargs["max_tokens"] = self.config.max_tokens

        self._review_agent = resolve_agent_spec(
            agent_spec,
            **resolve_kwargs,
        )
        return self._review_agent

    def _build_review_prompt(
        self,
        task: SeedTask,
        generated_code: str,
        test_results: dict[str, Any],
        design_document: str | None = None,
        parameter_sources: dict[str, Any] | None = None,
        semantic_conventions: dict[str, Any] | None = None,
        truncation_info: dict[str, Any] | None = None,
        project_context: dict[str, Any] | None = None,
        service_metadata: dict[str, Any] | None = None,
        refine_provenance: dict[str, Any] | None = None,
        forward_contract_violations: list[Any] | None = None,  # GAP1-A
    ) -> str:
        """Build the review prompt for a single task.

        Each logical section is built by a helper method that loads its
        template from ``review.yaml`` (falling back to inline assembly
        when the YAML file is absent).  The orchestrator builds the base
        prompt, then inserts enrichment sections before
        ``## Review Instructions``.

        Insertion order (preserved from the original monolithic method):
          1. project_context  (PCA-302/505)
          2. design_document  (Layer 4 — Gap 17, 19)
          3. parameter_sources + semantic_conventions (Gap 2, 28, 35)
          4. service_metadata (PCA-303, Gap 29)
          5. refine_provenance (IMP-9b)
          6. truncation_info  (Gate 4 — Gap 32)
          7. deps_advisory    (Gate 5)

        Args:
            task: The seed task.
            generated_code: The code that was generated.
            test_results: Test results from the TEST phase.
            design_document: Optional design document from DESIGN phase.
            parameter_sources: Optional parameter source mappings.
            semantic_conventions: Optional semantic convention mappings.
            truncation_info: Optional Gate 4 truncation detection result.
            project_context: Optional project-level context.
            service_metadata: Optional service metadata for protocol checks.
            refine_provenance: Optional REFINE apply provenance.

        Returns:
            Formatted review prompt string.
        """
        # -- Base prompt --
        prompt = self._build_review_base(task, generated_code, test_results)

        # -- Enrichment sections (inserted before "## Review Instructions") --
        # Each helper returns a list of strings.  Empty list = no injection.
        # R2-T10: Sections are ordered by priority (highest first) so that
        # when the total budget overflows, lower-priority sections are
        # dropped first.  FM violations and design compliance are the most
        # actionable and must survive budget trimming.
        named_sections: list[tuple[str, str]] = []

        # L4: Constraint checklist (highest priority — above project context)
        constraint_checklist = self._build_constraint_checklist_section(task)
        if constraint_checklist:
            named_sections.append(("constraint_checklist", constraint_checklist))

        for text in self._build_project_context_section(project_context):
            named_sections.append(("project_context", text))
        for text in self._build_design_compliance_section(design_document):
            named_sections.append(("design_compliance", text))
        # R2-T10: FM violations moved up — they are as important as design
        # compliance and core review score; must not be dropped on overflow.
        for text in self._build_forward_contract_violations_section(forward_contract_violations):
            named_sections.append(("forward_contract_violations", text))
        for text in self._build_parameter_sources_section(parameter_sources):
            named_sections.append(("parameter_sources", text))
        for text in self._build_semantic_conventions_section(semantic_conventions):
            named_sections.append(("semantic_conventions", text))
        for text in self._build_service_metadata_section(service_metadata):
            named_sections.append(("service_metadata", text))
        for text in self._build_refine_compliance_section(refine_provenance):
            named_sections.append(("refine_compliance", text))
        for text in self._build_truncation_warning_section(truncation_info):
            named_sections.append(("truncation_warning", text))
        for text in self._build_deps_advisory_section(task, test_results):
            named_sections.append(("deps_advisory", text))
        for text in self._build_call_graph_section(task, generated_code):
            named_sections.append(("call_graph", text))

        if named_sections:
            budgeted_sections, diagnostics = self._apply_review_section_budgets(
                named_sections
            )
            self._last_review_prompt_diagnostics = diagnostics
            enrichment = "\n".join(budgeted_sections)
            if "## Review Instructions" in prompt:
                prompt = prompt.replace(
                    "## Review Instructions",
                    enrichment + "\n\n## Review Instructions",
                )
            else:
                logger.warning(
                    "'## Review Instructions' heading not found in review "
                    "prompt — appending enrichment sections at end"
                )
                prompt += "\n" + enrichment
        else:
            self._last_review_prompt_diagnostics = {
                "section_budget_total": self._REVIEW_TOTAL_SECTION_BUDGET,
                "section_char_total": 0,
                "section_count": 0,
                "rendered_section_count": 0,
                "dropped_sections": [],
                "dropped_section_count": 0,
                "truncated_sections": {},
                "truncation_count": 0,
            }

        # GAP3-B CG-CR: Inject call graph context for review focus (CG-CR-1..CG-CR-5)
        try:
            _review_registry = None
            if self.config.manifest_consumption_enabled:
                _review_registry = self.config.manifest_registry
            if _review_registry is not None:
                from startd8.contractors.review_call_graph_context import (
                    enrich_review_prompt_with_call_graph,
                )
                prompt = enrich_review_prompt_with_call_graph(
                    prompt,
                    file_paths=list(task.target_files),
                    registry=_review_registry,
                    budget_chars=2000,
                )
        except Exception as _cg_cr_err:
            logger.debug("REVIEW CG-CR: call graph enrichment failed: %s", _cg_cr_err)

        return prompt

    @classmethod
    def _apply_review_section_budgets(
        cls,
        sections: list[tuple[str, str]],
    ) -> tuple[list[str], dict[str, Any]]:
        """Apply deterministic de-dup + overflow budgeting to REVIEW sections."""
        rendered: list[str] = []
        normalized_seen: set[str] = set()
        dropped_sections: list[str] = []
        truncated_sections: dict[str, int] = {}
        total_chars = 0

        for section_name, section_text in sections:
            normalized = re.sub(r"\s+", " ", section_text.strip()).lower()
            if normalized in normalized_seen:
                dropped_sections.append(f"{section_name}:duplicate")
                continue
            normalized_seen.add(normalized)

            budget = cls._REVIEW_SECTION_BUDGETS.get(section_name, 1200)
            text = section_text
            if len(text) > budget:
                truncated_sections[section_name] = len(text) - budget
                text = text[:budget] + (
                    f"\n... [truncated — {len(section_text) - budget} chars omitted] ..."
                )
            if total_chars + len(text) > cls._REVIEW_TOTAL_SECTION_BUDGET:
                dropped_sections.append(f"{section_name}:overflow")
                continue
            rendered.append(text)
            total_chars += len(text)

        overflow_lines: list[str] = []
        if truncated_sections:
            overflow_lines.append(
                "truncated_sections: "
                + ", ".join(
                    f"{name}(-{omitted} chars)"
                    for name, omitted in sorted(truncated_sections.items())
                )
            )
        if dropped_sections:
            overflow_lines.append(
                "dropped_sections: " + ", ".join(sorted(dropped_sections))
            )
        if overflow_lines:
            rendered.append(
                "## Overflow Summary\n"
                + "\n".join(f"- {line}" for line in overflow_lines)
            )

        diagnostics = {
            "section_budget_total": cls._REVIEW_TOTAL_SECTION_BUDGET,
            "section_char_total": total_chars,
            "section_count": len(sections),
            "rendered_section_count": len(rendered),
            "dropped_sections": dropped_sections,
            "dropped_section_count": len(dropped_sections),
            "truncated_sections": truncated_sections,
            "truncation_count": len(truncated_sections),
        }
        return rendered, diagnostics

    # -- helper: constraint checklist (L4) -----------------------------------

    @staticmethod
    def _build_constraint_checklist_section(task: SeedTask) -> str:
        """Build a structured constraint checklist for the reviewer.

        Each constraint is presented as a numbered assertion the reviewer
        must explicitly verify (PASS/FAIL) in their response.  Returns
        empty string when no constraints are available.

        Source: ``task.prompt_constraints`` (from enrichment + plan ingestion).
        """
        constraints = getattr(task, "prompt_constraints", None) or []
        if not constraints:
            return ""

        lines = [
            "## Constraint Checklist (MANDATORY)",
            "",
            "You MUST evaluate each constraint below and report",
            "PASS or FAIL for each. A FAIL on any constraint caps",
            "the maximum score at 85.",
            "",
        ]
        for idx, constraint_text in enumerate(constraints, 1):
            lines.append(f"{idx}. [MUST] {constraint_text}")
        lines.append("")
        lines.append(
            "After the Issues section, add a ## Constraint Verdicts section "
            "listing each numbered constraint as PASS or FAIL."
        )
        return "\n".join(lines)

    @staticmethod
    def _extract_constraint_verdicts(
        review_text: str, constraint_count: int,
    ) -> list[dict[str, str]]:
        """Extract PASS/FAIL verdicts for each numbered constraint.

        Looks for lines like ``1. PASS`` or ``1. FAIL: ...`` in a
        "Constraint Verdicts" section of the review response.

        Returns:
            List of dicts ``[{"index": "1", "verdict": "PASS"|"FAIL", "reason": "..."}]``
        """
        import re

        verdicts: list[dict[str, str]] = []

        # Try to find the Constraint Verdicts section
        section_match = re.search(
            r"##\s*Constraint\s+Verdicts?\s*\n(.*?)(?=\n##\s|\Z)",
            review_text,
            re.DOTALL | re.IGNORECASE,
        )
        search_text = section_match.group(1) if section_match else review_text

        _VERDICT_RE = re.compile(
            r"(\d+)\.\s*\**\s*(PASS|FAIL)\s*\**\s*(?::?\s*(.+))?\s*$",
            re.IGNORECASE,
        )
        for line in search_text.splitlines():
            match = _VERDICT_RE.match(line.strip())
            if match:
                verdicts.append({
                    "index": match.group(1),
                    "verdict": match.group(2).upper(),
                    "reason": (match.group(3) or "").strip(),
                })

        return verdicts

    # -- helper: base prompt ------------------------------------------------

    def _build_review_base(
        self,
        task: SeedTask,
        generated_code: str,
        test_results: dict[str, Any],
    ) -> str:
        """Format the base review prompt with task data.

        Loads the ``review_user`` template from YAML when available,
        falling back to the inline ``_REVIEW_PROMPT_TEMPLATE_FALLBACK``.
        """
        constraints_str = "\n".join(
            f"- {c}" for c in task.prompt_constraints
        ) or "None specified"

        test_str = (
            json.dumps(test_results, indent=2, default=str)
            if test_results
            else "No test results available for this task"
        )

        max_code = self.config.review_max_code_chars
        code_for_prompt = generated_code[:max_code]
        if len(generated_code) > max_code:
            code_for_prompt += (
                f"\n\n# ... [truncated — "
                f"{len(generated_code) - max_code} chars omitted] ..."
            )

        max_test = 2000
        test_for_prompt = test_str[:max_test]
        if len(test_str) > max_test:
            test_for_prompt += (
                f"\n... [truncated — {len(test_str) - max_test} chars omitted] ..."
            )

        template = self._get_review_user_template()
        return template.format(
            task_id=task.task_id,
            title=task.title,
            domain=task.domain,
            description=task.description,
            constraints=constraints_str,
            generated_code=code_for_prompt,
            test_results=test_for_prompt,
            pass_threshold=self.config.pass_threshold,
        )

    # -- helper: project context (PCA-302/505) ------------------------------

    @staticmethod
    def _build_project_context_section(
        project_context: dict[str, Any] | None,
    ) -> list[str]:
        """PCA-302/505: Project-level context for architectural review.

        Returns a list with a single formatted section string, or ``[]``
        if *project_context* is None/empty.
        """
        if not project_context:
            return []

        # Assemble project lines
        project_lines_parts: list[str] = []
        _pn = project_context.get("project_name")
        if _pn:
            project_lines_parts.append(f"**Project:** {_pn}")
        _pt = project_context.get("plan_title")
        if _pt:
            project_lines_parts.append(f"**Plan:** {_pt}")
        _pg = project_context.get("plan_goals", [])
        for g in _pg[:5]:
            project_lines_parts.append(f"- {g}")
        project_lines = "\n".join(project_lines_parts)

        # Architectural objectives
        _arch = project_context.get("architectural_context", {})
        _objs = _arch.get("objectives", [])
        if _objs:
            obj_items = (list(_objs) if isinstance(_objs, list) else [_objs])[:3]
            arch_objectives = (
                "**Architectural Objectives:**\n"
                + "\n".join(f"- {o}" for o in obj_items)
            )
        else:
            arch_objectives = ""

        # Architectural constraints
        _cons = _arch.get("constraints", [])
        if _cons:
            con_items = (list(_cons) if isinstance(_cons, list) else [_cons])[:5]
            arch_constraints = (
                "**Constraints:**\n"
                + "\n".join(f"- {c}" for c in con_items)
            )
        else:
            arch_constraints = ""

        # Edit-first verification
        if project_context.get("had_existing_files"):
            edit_first_block = (
                "\n**Edit-First Verification:**\n"
                "This task modified EXISTING production files. Verify the "
                "implementation preserves existing functionality and does not "
                "remove or break existing code that was not part of the change scope."
            )
        else:
            edit_first_block = ""

        text = _format_review_prompt(
            "project_context",
            project_lines=project_lines,
            arch_objectives=arch_objectives,
            arch_constraints=arch_constraints,
            edit_first_block=edit_first_block,
        )
        if text is None:
            # Inline fallback
            _parts = ["## Project Context"]
            if project_lines:
                _parts.append(project_lines)
            if arch_objectives:
                _parts.append(arch_objectives)
            if arch_constraints:
                _parts.append(arch_constraints)
            if edit_first_block:
                _parts.append(edit_first_block)
            text = "\n".join(_parts)

        if len(text) > 2000:
            text = text[:2000] + "\n... [truncated for prompt budget]"
        return [text]

    # -- helper: design compliance (Layer 4 — Gap 17, 19) -------------------

    @staticmethod
    def _build_design_compliance_section(
        design_document: str | None,
    ) -> list[str]:
        """Inject design document with compliance instructions."""
        if not design_document:
            return []

        max_design = 8000
        design_for_prompt = design_document[:max_design]
        if len(design_document) > max_design:
            design_for_prompt += (
                f"\n\n# ... [{len(design_document) - max_design} chars truncated] ..."
            )
        design_lines = len(design_document.strip().splitlines())
        design_sections = sum(
            1
            for line in design_document.splitlines()
            if line.strip().startswith("##")
        )

        text = _format_review_prompt(
            "design_compliance",
            design_lines=design_lines,
            design_sections=design_sections,
            design_for_prompt=design_for_prompt,
        )
        if text is None:
            text = (
                f"\n## Design Document (from DESIGN phase — {design_lines} lines, "
                f"{design_sections} sections)\n"
                f"The implementation was built from this design specification. "
                f"**You MUST check that the implementation covers ALL sections "
                f"and requirements from this design.** Score lower if major "
                f"sections are missing or only partially implemented.\n\n"
                f"```\n{design_for_prompt}\n```\n"
            )
        return [text]

    # -- helper: parameter sources (Gap 2, 35) ------------------------------

    @staticmethod
    def _build_parameter_sources_section(
        parameter_sources: dict[str, Any] | None,
    ) -> list[str]:
        """Inject parameter source verification section."""
        if not parameter_sources:
            return []

        param_lines = "\n".join(
            f"- **{k}**: {v}" for k, v in parameter_sources.items()
        )
        text = _format_review_prompt(
            "parameter_sources",
            param_lines=param_lines,
        )
        if text is None:
            text = (
                "\n## Parameter Sources\n"
                + param_lines
                + "\nVerify the implementation uses the correct parameter names and sources.\n"
            )
        return [text]

    # -- helper: semantic conventions (Gap 28) ------------------------------

    @staticmethod
    def _build_semantic_conventions_section(
        semantic_conventions: dict[str, Any] | None,
    ) -> list[str]:
        """Inject naming convention compliance section."""
        if not semantic_conventions:
            return []

        convention_lines = "\n".join(
            f"- **{k}**: {v}" for k, v in semantic_conventions.items()
        )
        text = _format_review_prompt(
            "semantic_conventions",
            convention_lines=convention_lines,
        )
        if text is None:
            text = (
                "\n## Semantic Conventions\n"
                + convention_lines
                + "\nVerify the implementation follows these naming conventions.\n"
            )
        return [text]

    # -- helper: service metadata (PCA-303, Gap 29) -------------------------

    @staticmethod
    def _build_service_metadata_section(
        service_metadata: dict[str, Any] | None,
    ) -> list[str]:
        """Inject service metadata compliance check."""
        if not service_metadata:
            return []

        metadata_parts: list[str] = []
        _tp = service_metadata.get("transport_protocol")
        if _tp:
            metadata_parts.append(f"- Expected transport protocol: **{_tp}**")
        _rd = service_metadata.get("runtime_dependencies")
        if _rd and isinstance(_rd, list):
            metadata_parts.append(
                f"- Expected runtime dependencies: {', '.join(str(d) for d in _rd)}"
            )
        metadata_lines = "\n".join(metadata_parts)

        text = _format_review_prompt(
            "service_metadata",
            metadata_lines=metadata_lines,
        )
        if text is None:
            _smc_parts = ["## Service Metadata Compliance"]
            if metadata_lines:
                _smc_parts.append(metadata_lines)
            _smc_parts.append(
                "Check that HEALTHCHECK mechanism matches transport_protocol. "
                "Flag any capabilities added that the service metadata declares as absent."
            )
            text = "\n".join(_smc_parts)
        return [text]

    # -- helper: REFINE compliance (IMP-9b) ---------------------------------

    @staticmethod
    def _build_refine_compliance_section(
        refine_provenance: dict[str, Any] | None,
    ) -> list[str]:
        """Inject REFINE applied/warning IDs section."""
        if not refine_provenance:
            return []

        applied_ids = refine_provenance.get("applied_ids", [])
        if not applied_ids:
            return []

        applied_lines = "\n".join(f"- {aid}" for aid in applied_ids[:20])

        warning_ids = refine_provenance.get("warning_ids", [])
        if warning_ids:
            warning_block = (
                "\nThe following suggestions had apply warnings "
                "(may not be fully integrated):\n"
                + "\n".join(f"- {wid} (verify manually)" for wid in warning_ids[:10])
            )
        else:
            warning_block = ""

        text = _format_review_prompt(
            "refine_compliance",
            applied_lines=applied_lines,
            warning_block=warning_block,
        )
        if text is None:
            _rc_parts = [
                "\n## REFINE Compliance\n",
                "The following REFINE phase suggestions were integrated into "
                "the plan document before code generation. **Verify that the "
                "implementation reflects these applied changes:**",
            ]
            for aid in applied_ids[:20]:
                _rc_parts.append(f"- {aid}")
            if warning_block:
                _rc_parts.append(warning_block)
            _rc_parts.append(
                "\nScore lower if the implementation ignores changes "
                "that were explicitly applied to the plan.\n"
            )
            text = "\n".join(_rc_parts)
        return [text]

    # -- helper: truncation warning (Gate 4) --------------------------------

    @staticmethod
    def _build_truncation_warning_section(
        truncation_info: dict[str, Any] | None,
    ) -> list[str]:
        """Inject Gate 4 truncation detection results."""
        if not truncation_info:
            return []

        source = truncation_info.get("source", "unknown")
        confidence = truncation_info.get("max_confidence", 0.0)
        syntax_errs = truncation_info.get("syntax_errors", [])
        total_lines = truncation_info.get("total_lines", 0)
        estimated = truncation_info.get("estimated_loc", 0)

        syntax_line = (
            f"Syntax errors in: {', '.join(syntax_errs)}."
            if syntax_errs
            else ""
        )
        ratio_line = (
            f"Generated {total_lines} lines vs {estimated} estimated "
            f"({total_lines / estimated:.0%} ratio)."
            if estimated and total_lines
            else ""
        )

        text = _format_review_prompt(
            "truncation_warning",
            source=source,
            confidence=f"{confidence:.2f}",
            syntax_line=syntax_line,
            ratio_line=ratio_line,
        )
        if text is None:
            parts = [
                "\n## TRUNCATION WARNING (Gate 4)\n",
                f"Automated analysis flagged this task's output as potentially truncated "
                f"(source={source}, confidence={confidence:.2f}).",
            ]
            if syntax_line:
                parts.append(syntax_line)
            if ratio_line:
                parts.append(ratio_line)
            parts.append(
                "**Pay special attention to completeness.** "
                "Score lower if the implementation appears incomplete or has syntax errors.\n"
            )
            text = "\n".join(parts)
        return [text]

    # -- helper: call graph blast radius (Phase 6, CG-RV-1,2,3,4,5) --------

    def _build_call_graph_section(
        self,
        task: SeedTask,
        generated_code: str,
    ) -> list[str]:
        """Phase 6: Call graph context for review prompt.

        CG-RV-1: For each target file, list modified functions with caller counts.
        CG-RV-2: Flag generated functions with zero callers (dead code candidates).
        CG-RV-3: Combine signature changes + callers for high-priority review.
        Budget-constrained by ``call_graph_review_budget``.
        """
        if not self.config.manifest_consumption_enabled:
            return []
        registry = self.config.manifest_registry
        if registry is None:
            return []

        try:
            budget = self.config.call_graph_review_budget
            parts: list[str] = ["\n## CALL GRAPH IMPACT (Phase 6)\n"]
            current_len = len(parts[0])

            # CG-RV-1: Caller counts for target files
            for tf in getattr(task, "target_files", []) or []:
                try:
                    callers_map = registry.callers_of_file(tf)
                    if callers_map:
                        section = f"**{tf}** — functions with external callers:\n"
                        for fqn, callers in sorted(callers_map.items()):
                            br = registry.blast_radius(fqn, max_depth=self.config.blast_radius_max_depth)
                            line = f"- `{fqn}`: {len(callers)} direct callers, blast radius {len(br)}\n"
                            if current_len + len(section) + len(line) > budget:
                                break
                            section += line
                        parts.append(section)
                        current_len += len(section)
                except Exception:
                    logger.debug(
                        "REVIEW: CG-RV-1 callers_of_file failed for %s",
                        tf, exc_info=True,
                    )

            # CG-RV-2: Dead code candidates in generated output
            try:
                dead = set(registry.dead_candidates())
                if dead and task.target_files:
                    dead_in_task: list[str] = []
                    for tf in task.target_files:
                        manifest = registry.get(tf)
                        if manifest is None:
                            continue
                        from startd8.utils.manifest_registry import _flatten_elements
                        for elem in _flatten_elements(manifest.elements):
                            if elem.fqn and elem.fqn in dead:
                                dead_in_task.append(elem.fqn)
                    if dead_in_task:
                        dead_section = (
                            "**Dead code candidates** (public, zero callers):\n"
                            + "".join(f"- `{fqn}`\n" for fqn in dead_in_task[:10])
                        )
                        if current_len + len(dead_section) <= budget:
                            parts.append(dead_section)
                            current_len += len(dead_section)
            except Exception:
                logger.debug("REVIEW: CG-RV-2 dead candidates failed", exc_info=True)

            if len(parts) <= 1:
                return []  # Only header, no content
            return parts

        except Exception:
            logger.debug("REVIEW: call graph section failed", exc_info=True)
            return []

    # -- helper: Forward Manifest contract violations (GAP1-A) ---------------

    @staticmethod
    def _build_forward_contract_violations_section(
        violations: list[Any] | None,
    ) -> list[str]:
        """GAP1-A: Inject pre-computed Forward Manifest violations into review prompt.

        When violations are present the reviewer LLM sees them BEFORE evaluating
        the code, enabling it to write a contextual review that explicitly calls
        out each structural defect.

        Args:
            violations: List of ContractViolation instances (or None).

        Returns:
            List of text strings to inject, or empty list when no violations.
        """
        if not violations:
            return []

        error_viols = [v for v in violations if getattr(v, "severity", "error") == "error"]
        warn_viols = [v for v in violations if getattr(v, "severity", "error") == "warning"]

        if not error_viols and not warn_viols:
            return []

        lines = [
            "\n## Forward Manifest Contract Violations\n"
            "The following structural contracts were violated by the generated code.\n"
            "**BLOCKING** entries MUST be explicitly called out in the review score and issues list.\n"
        ]

        for v in error_viols:
            cid = getattr(v, "contract_id", "?")
            vtype = getattr(v, "violation_type", "?")
            expected = getattr(v, "expected", "?")
            actual = getattr(v, "actual", None) or "absent"
            fpath = getattr(v, "file_path", None)
            line = f"- **[BLOCKING]** `{cid}` | {vtype} | expected=`{expected}` | actual=`{actual}`"
            if fpath:
                line += f" | file=`{fpath}`"
            lines.append(line)

        for v in warn_viols:
            cid = getattr(v, "contract_id", "?")
            vtype = getattr(v, "violation_type", "?")
            expected = getattr(v, "expected", "?")
            line = f"- [WARN] `{cid}` | {vtype} | expected=`{expected}`"
            lines.append(line)

        lines.append(
            "\nIf BLOCKING violations are present, the review score MUST be below the pass threshold "
            "and the verdict MUST be FAIL.\n"
        )
        return lines

    # -- helper: deps allowlist advisory (Gate 5) ---------------------------

    @staticmethod
    def _build_deps_advisory_section(
        task: SeedTask,
        test_results: dict[str, Any],
    ) -> list[str]:
        """Inject Gate 5 confidence-stratified dependency guidance."""
        deps_confidence = getattr(task, "deps_confidence", 1.0)
        deps_source = getattr(task, "deps_source", None)

        if deps_confidence >= 0.8 or not test_results:
            return []

        # Check if any deps_available failures exist
        has_deps_issues = any(
            r.get("validator") == "deps_available" and not r.get("passed", True)
            for r in test_results.get("results", [])
        )
        if not has_deps_issues:
            return []

        if deps_confidence <= 0.2:
            confidence_guidance = (
                "Only stdlib modules are known — third-party import "
                "violations are **likely false positives**."
            )
        elif deps_confidence <= 0.5:
            confidence_guidance = (
                "Allowlist was built from venv scan only — some "
                "dependencies may be missing from the known set."
            )
        else:
            confidence_guidance = ""

        text = _format_review_prompt(
            "deps_allowlist_advisory",
            deps_source=repr(deps_source),
            deps_confidence=f"{deps_confidence:.2f}",
            confidence_guidance=confidence_guidance,
        )
        if text is None:
            parts = [
                "\n## DEPENDENCY ALLOWLIST ADVISORY (Gate 5)\n",
                f"The dependency allowlist was built from source={deps_source!r} "
                f"(confidence={deps_confidence:.2f}).",
            ]
            if confidence_guidance:
                parts.append(confidence_guidance)
            parts.append(
                "**Do NOT penalize the score for import violations when "
                "allowlist confidence is low.** Focus review on code "
                "quality, correctness, and design compliance instead.\n"
            )
            text = "\n".join(parts)
        return [text]

    def _parse_review_response(self, response: str) -> dict[str, Any]:
        """Parse score, verdict, and issues from the LLM review response.

        Args:
            response: Raw LLM output.

        Returns:
            Dict with ``score``, ``verdict``, ``strengths``, ``issues``, ``suggestions``.

        """
        import re

        score: int | None = None
        verdict = "FAIL"

        # Extract score — handles bold-wrapped variants like **85**,
        # **Score: 85**, Score: **85**/100
        # R2-T2: \*{0,2} tolerates optional markdown bold around score digits
        score_match = re.search(r"###\s*\*{0,2}Score:\s*\*{0,2}\s*(\d+)", response)
        if score_match:
            score = min(100, max(0, int(score_match.group(1))))
        else:
            # Fallback: try without markdown headers, bold-aware
            score_fallback = re.search(
                r"(?:^|\n)\s*\*{0,2}Score\s*[:=]\s*\*{0,2}\s*(\d+)\s*\*{0,2}\s*(?:/\s*100)?\s*\*{0,2}",
                response, re.IGNORECASE | re.MULTILINE,
            )
            if score_fallback:
                score = min(100, max(0, int(score_fallback.group(1))))
            else:
                # Last resort: standalone bold-wrapped number on its own line
                # e.g. **85** as the score
                score_bold_standalone = re.search(
                    r"(?:^|\n)\s*\*{2}(\d+)\*{2}\s*(?:/\s*100)?\s*$",
                    response, re.MULTILINE,
                )
                if score_bold_standalone:
                    score = min(100, max(0, int(score_bold_standalone.group(1))))
                else:
                    logger.warning(
                        "REVIEW: could not extract score from response (score=None); "
                        "first 200 chars: %s", response[:200],
                    )

        # Extract verdict
        verdict_match = re.search(r"###\s*Verdict:\s*\**\s*(PASS|FAIL)\s*\**", response, re.IGNORECASE)
        if verdict_match:
            verdict = verdict_match.group(1).upper()
        else:
            # Fallback: try without markdown headers
            verdict_fallback = re.search(r"(?:^|\n)\s*Verdict\s*[:=]\s*\**\s*(PASS|FAIL)\s*\**", response, re.IGNORECASE)
            if verdict_fallback:
                verdict = verdict_fallback.group(1).upper()
            else:
                logger.warning(
                    "REVIEW: could not extract verdict from response (defaulting to FAIL)"
                )

        def extract_section(section: str) -> list[str]:
            pattern = rf"###\s*{section}\s*\n(.*?)(?=\n###\s|\Z)"
            match = re.search(pattern, response, re.DOTALL | re.IGNORECASE)
            if not match:
                return []
            items: list[str] = []
            for line in match.group(1).splitlines():
                cleaned = line.strip()
                if cleaned.startswith("- "):
                    items.append(cleaned[2:].strip())
                elif cleaned.startswith("* "):
                    items.append(cleaned[2:].strip())
                elif re.match(r"^\d+\.\s+", cleaned):
                    items.append(re.sub(r"^\d+\.\s+", "", cleaned).strip())
            return items

        # L4: Extract constraint verdicts and cap score on failure
        constraint_verdicts = self._extract_constraint_verdicts(response, 0)
        constraint_failed = any(
            v["verdict"] == "FAIL" for v in constraint_verdicts
        )
        _CONSTRAINT_FAIL_SCORE_CAP = 85
        if constraint_failed and score is not None and score > _CONSTRAINT_FAIL_SCORE_CAP:
            logger.info(
                "REVIEW: constraint violation detected — capping score from %d to %d",
                score, _CONSTRAINT_FAIL_SCORE_CAP,
            )
            score = _CONSTRAINT_FAIL_SCORE_CAP

        result = {
            "score": score,
            "verdict": verdict,
            "passed": verdict == "PASS" and score is not None and score >= self.config.pass_threshold,
            "raw_response": response[:4000],  # truncate for storage
            "strengths": extract_section("Strengths"),
            "issues": extract_section("Issues"),
            "suggestions": extract_section("Suggestions"),
        }
        if constraint_verdicts:
            result["constraint_verdicts"] = constraint_verdicts
        if constraint_failed:
            result["quality_failed"] = True
        return result

    _REVIEW_PHASE_SYSTEM_PROMPT_FALLBACK = (
        "You are an expert code quality reviewer. Evaluate the implementation "
        "against the design document, checking for correctness, completeness, "
        "and adherence to stated constraints."
    )

    @staticmethod
    def _get_review_system_prompt() -> str:
        """Return the review system prompt, preferring YAML over fallback."""
        tmpl = _format_review_prompt("review_system")
        if tmpl is not None:
            return tmpl.strip()
        return ReviewPhaseHandler._REVIEW_PHASE_SYSTEM_PROMPT_FALLBACK

    def _review_task(
        self,
        task: SeedTask,
        generated_code: str,
        test_results: dict[str, Any],
        design_document: str | None = None,
        parameter_sources: dict[str, Any] | None = None,
        semantic_conventions: dict[str, Any] | None = None,
        truncation_info: dict[str, Any] | None = None,
        project_context: dict[str, Any] | None = None,
        service_metadata: dict[str, Any] | None = None,
        refine_provenance: dict[str, Any] | None = None,
        forward_contract_violations: list[Any] | None = None,  # GAP1-A: pre-computed FM violations
    ) -> dict[str, Any]:
        """Conduct LLM review for a single task.

        Args:
            task: The seed task.
            generated_code: Code to review.
            test_results: Test results for context.
            design_document: Optional design document from DESIGN phase
                for compliance checking.
            parameter_sources: Optional parameter source mappings.
            semantic_conventions: Optional semantic convention mappings.
            truncation_info: Optional Gate 4 truncation detection result for
                this task.  When present, a warning section is injected into
                the review prompt so the LLM reviewer can assess completeness.
            refine_provenance: Optional REFINE apply provenance for
                compliance checking against applied suggestions.

        Returns:
            Review result dict with score, verdict, cost.
        """
        _review_retry_config = RetryConfig(
            max_attempts=1,  # Placeholder for API compat — retry orchestration is handled by the outer _max_attempts loop with phase-aware backoff
            base_delay=5.0,
            max_delay=60.0,
            retryable_exceptions=(ConnectionError, TimeoutError, OSError),
            retryable_status_codes=(429, 500, 502, 503, 504, 529),
        )
        _max_attempts = 1 + self.config.review_task_retries

        for _attempt in range(_max_attempts):
            try:
                agent = self._resolve_review_agent()
                prompt = self._build_review_prompt(
                    task, generated_code, test_results,
                    design_document=design_document,
                    parameter_sources=parameter_sources,
                    semantic_conventions=semantic_conventions,
                    truncation_info=truncation_info,
                    project_context=project_context,
                    service_metadata=service_metadata,
                    refine_provenance=refine_provenance,
                    forward_contract_violations=forward_contract_violations,  # GAP1-A
                )
                _prompt_diag = dict(self._last_review_prompt_diagnostics or {})
                _prompt_diag.update(
                    {
                        "prompt_chars": len(prompt),
                        "prompt_tokens_estimate": len(prompt) // 4,
                    }
                )

                # OT-306: review.evaluate span (child of OT-304 task span)
                with _phase_tracer.start_as_current_span(
                    "review.evaluate",
                    attributes={
                        "review.task_id": task.task_id,
                        "review.attempt": _attempt + 1,
                        "review.has_design_doc": design_document is not None,
                        "review.has_parameter_sources": parameter_sources is not None,
                    },
                ) as _eval_span:
                    try:
                        response_text, _time_ms, token_usage = agent.generate(
                            prompt, system_prompt=self._get_review_system_prompt(),
                        )
                        review = self._parse_review_response(response_text)
                        review["task_id"] = task.task_id
                        review["cost"] = token_usage_cost(token_usage)
                        review["tokens"] = {
                            "input": token_usage_input(token_usage),
                            "output": token_usage_output(token_usage),
                        }
                        review["status"] = "reviewed"
                        review["prompt_telemetry"] = _prompt_diag

                        # OT-306 AC-3: set verdict attribute
                        _eval_span.set_attribute(
                            "review.verdict", review.get("verdict", "UNKNOWN"),
                        )

                        # CS7: Forensic log for review.evaluate
                        from startd8.contractors.forensic_log import emit_forensic_log
                        _agent_spec = self.config.review_agent or self.config.lead_agent
                        emit_forensic_log(
                            call_type="review.evaluate",
                            call={
                                "prompt_length": len(prompt),
                                "model_spec": _agent_spec,
                                "response_time_ms": _time_ms,
                                "tokens_input": token_usage_input(token_usage),
                                "tokens_output": token_usage_output(token_usage),
                                "cost_usd": token_usage_cost(token_usage),
                                "attempt": _attempt + 1,
                                "max_attempts": _max_attempts,
                            },
                            task={
                                "task_id": task.task_id,
                                "title": task.title,
                                "domain": task.domain,
                                "phase": "review",
                                "target_files": list(task.file_scope) if task.file_scope else None,
                            },
                            context_propagation={
                                "design_doc_present": design_document is not None,
                                "design_doc_line_count": len(design_document.splitlines()) if design_document else None,
                                "parameter_sources_present": parameter_sources is not None,
                                "prompt_constraints_count": len(task.prompt_constraints) if task.prompt_constraints else 0,
                                "prompt_section_count": _prompt_diag.get("section_count", 0),
                                "prompt_dropped_sections": _prompt_diag.get("dropped_section_count", 0),
                                "prompt_truncation_count": _prompt_diag.get("truncation_count", 0),
                            },
                            forensic_log_level=self.config.forensic_log_level,
                        )

                        return review
                    except Exception as _eval_err:
                        # OT-507: record error on span before re-raising
                        if _HAS_OTEL:
                            from opentelemetry.trace.status import (
                                Status as _OTelStatus,
                                StatusCode as _OTelStatusCode,
                            )
                            _eval_span.record_exception(_eval_err)
                            _eval_span.set_status(
                                _OTelStatus(_OTelStatusCode.ERROR, str(_eval_err))
                            )
                        else:
                            _eval_span.record_exception(_eval_err)
                            _eval_span.set_status("ERROR")
                        raise
            except Exception as exc:
                if (
                    _attempt < _max_attempts - 1
                    and _is_retryable_exception(exc, _review_retry_config)
                ):
                    _delay = _calculate_delay(_attempt, _review_retry_config)
                    logger.warning(
                        "REVIEW: task %s failed (attempt %d/%d), retrying in %.1fs: %s",
                        task.task_id,
                        _attempt + 1,
                        _max_attempts,
                        _delay,
                        exc,
                    )
                    time.sleep(_delay)
                    continue

                # Final attempt or non-retryable — return error
                logger.warning("REVIEW: agent error for %s: %s", task.task_id, exc)
                return {
                    "task_id": task.task_id,
                    "score": None,
                    "verdict": "ERROR",
                    "passed": False,
                    "cost": 0.0,
                    "tokens": {"input": 0, "output": 0},
                    "error": str(exc),
                    "status": "review_error",
                }
        # Unreachable — loop always returns — but satisfies type checker
        return {
            "task_id": task.task_id, "score": None, "verdict": "ERROR",
            "passed": False, "cost": 0.0, "tokens": {"input": 0, "output": 0},
            "error": "retry loop exhausted", "status": "review_error",
        }

    # ------------------------------------------------------------------
    # Review helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _make_error_review_entry(
        task: SeedTask,
        exc: Exception,
        env_fails: list[dict[str, Any]],
        env_warns: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Build a review_items entry for a task that raised during review."""
        return {
            "task_id": task.task_id,
            "title": task.title,
            "domain": task.domain,
            "constraint_count": len(task.prompt_constraints),
            "env_failures": len(env_fails),
            "env_warnings": len(env_warns),
            "review_status": "error",
            "error": str(exc),
            "passed": False,
            "score": None,
            "verdict": "ERROR",
            "cost": 0.0,
            "tokens": {"input": 0, "output": 0},
        }

    # ------------------------------------------------------------------
    # Resume-cache helpers (v2 defense-in-depth)
    # ------------------------------------------------------------------

    @staticmethod
    def _hash_generated_code(gen_result: GenerationResult) -> str | None:
        """Compute SHA-256 of concatenated generated file contents.

        Delegates to the module-level ``_compute_gen_file_hash`` helper
        which sorts files by path for deterministic digests and skips
        oversized files.

        Returns hex digest, or None if no files are readable.
        """
        return _compute_gen_file_hash(gen_result.generated_files)

    def _validate_review_cache(
        self,
        saved: dict[str, Any],
        generation_results: dict[str, GenerationResult],
        source_checksum: str | None,
        design_results: dict[str, Any] | None = None,
    ) -> dict[str, dict[str, Any]]:
        """Validate a saved review cache through 5 ordered layers.

        Returns a dict of task_id → cached review data for entries that
        pass all layers. Empty dict if cache-wide validation fails.

        Layers (cheapest → most expensive):
            0: Schema version — _cache_meta exists, schema_version == _CACHE_SCHEMA_VERSION
            1: Source checksum — _cache_meta.source_checksum matches context
            1.5: Design hash — design_results hash matches context
            2: Per-task status — entry has status == "reviewed"
            3: Per-task code hash — reviewed_code_hash matches current generated code
        """
        # Layer 0: Schema version
        cache_meta = saved.get("_cache_meta")
        if not isinstance(cache_meta, dict):
            logger.warning(
                "REVIEW: cache missing _cache_meta (v1 or corrupt) — ignoring"
            )
            return {}
        schema_version = cache_meta.get("schema_version")
        if schema_version != _CACHE_SCHEMA_VERSION:
            logger.warning(
                "REVIEW: cache schema_version=%s (expected %d) — ignoring",
                schema_version, _CACHE_SCHEMA_VERSION,
            )
            return {}

        # Layer 1: Source checksum
        cached_checksum = cache_meta.get("source_checksum")
        if (
            cached_checksum is not None
            and source_checksum is not None
            and cached_checksum != source_checksum
        ):
            logger.warning(
                "REVIEW: source_checksum mismatch "
                "(cached=%s, current=%s) — ignoring entire cache",
                cached_checksum, source_checksum,
            )
            return {}
        elif cached_checksum is not None or source_checksum is not None:
            # One side has a checksum and the other doesn't — we can't
            # confirm integrity but this is common during the first run
            # after cache creation or after a rebuild.
            logger.warning(
                "REVIEW: only one side has source_checksum "
                "(cached=%s, context=%s) — skipping Layer 1 comparison",
                "present" if cached_checksum else "absent",
                "present" if source_checksum else "absent",
            )
        else:
            # Both checksums are None — Layer 1 integrity check is disabled
            logger.warning(
                "Cache validation: neither cached nor current has source_checksum — "
                "Layer 1 integrity check is disabled"
            )

        # Layer 1.5: Design hash — invalidate when design changes
        cached_design_hash = cache_meta.get("design_hash")
        if cached_design_hash is not None and design_results is not None:
            current_design_hash = _compute_design_results_hash(design_results)
            if (
                current_design_hash is not None
                and current_design_hash != cached_design_hash
            ):
                logger.warning(
                    "REVIEW: design_hash mismatch "
                    "(cached=%s, current=%s) — ignoring entire cache",
                    cached_design_hash[:12], current_design_hash[:12],
                )
                return {}

        tasks_data = saved.get("tasks", {})
        valid: dict[str, dict[str, Any]] = {}

        for tid, entry in tasks_data.items():
            # Layer 2: Per-task status
            if entry.get("status") != "reviewed":
                logger.info(
                    "REVIEW: skipping cached entry %s (status=%s)",
                    tid, entry.get("status"),
                )
                continue

            # Layer 3: Per-task code hash
            cached_hash = entry.get("reviewed_code_hash")
            if cached_hash is not None:
                gen_result = generation_results.get(tid)
                if gen_result is not None:
                    current_hash = self._hash_generated_code(gen_result)
                    if current_hash is not None and current_hash != cached_hash:
                        logger.warning(
                            "REVIEW: code hash mismatch for %s "
                            "(cached=%s, current=%s) — skipping entry",
                            tid, cached_hash[:12], current_hash[:12],
                        )
                        continue

            valid[tid] = entry

        return valid

    # ------------------------------------------------------------------
    # ER-010: Element-level review scoring
    # ------------------------------------------------------------------

    @staticmethod
    def _score_elements_from_review(
        review_items: list[dict[str, Any]],
        tasks: list[SeedTask],
        element_registry: Any,
    ) -> int:
        """Attribute review scores to individual elements (ER-010).

        For each reviewed task, look up its target files in the registry
        and record the review score/verdict as a phase status on each
        matching element.  Advisory — never blocks the REVIEW phase.

        Returns the number of elements scored.
        """
        scored = 0
        task_map = {t.task_id: t for t in tasks}

        for item in review_items:
            tid = item.get("task_id")
            score = item.get("score")
            verdict = item.get("verdict", "")
            passed = item.get("passed")
            if tid is None or score is None:
                continue

            task = task_map.get(tid)
            if task is None:
                continue

            for fpath in (task.target_files or []):
                try:
                    entries = element_registry.elements_for_file(fpath)
                    for entry in entries:
                        element_registry.set_phase_status(
                            entry.element_id,
                            "review",
                            f"{'passed' if passed else 'failed'}:{score}",
                            metadata={
                                "task_id": tid,
                                "score": score,
                                "verdict": verdict,
                                "issues": [
                                    iss for iss in (item.get("issues") or [])
                                    if isinstance(iss, str)
                                ][:5],
                            },
                        )
                        scored += 1
                except Exception as exc:
                    logger.debug(
                        "ER-010: Element scoring failed for %s/%s: %s",
                        fpath, tid, exc,
                    )

        if scored > 0:
            logger.info(
                "ER-010: Scored %d elements from %d review items",
                scored, len(review_items),
            )
        return scored

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
        _log_context_completeness("REVIEW", context)
        tasks: list[SeedTask] = _ensure_context_loaded(context)
        preflight_summary = context.get("preflight_summary", {})
        generation_results: dict[str, GenerationResult] = context.get("generation_results", {})
        test_results_ctx: dict[str, Any] = context.get("test_results", {})
        test_plan = test_results_ctx.get("test_plan", [])
        test_by_task = {t["task_id"]: t for t in test_plan if isinstance(t, dict)}
        integration_results_ctx: dict[str, Any] = context.get("integration_results", {})

        # Gate 2c downstream map — used to exclude downstream stubs from
        # review scoring so they don't unfairly penalize the task.
        downstream_map: dict[str, list[str]] = context.get("_downstream_map", {})
        truncation_flags: dict[str, Any] = context.get("truncation_flags", {})

        logger.info("REVIEW phase: reviewing %d tasks (dry_run=%s)", len(tasks), dry_run)

        review_items: list[dict[str, Any]] = []
        constraint_coverage: dict[str, int] = defaultdict(int)
        total_cost = 0.0
        total_passed = 0
        total_failed = 0
        previous_task_started_mono: Optional[float] = None

        # --- Resume check: load prior review results if available ---
        project_root_str = context.get("project_root")
        review_cache_path = (
            Path(project_root_str) / ".startd8" / "state" / "review_results.json"
            if project_root_str and project_root_str.strip() else None
        )
        cached_reviews: dict[str, dict[str, Any]] = {}

        if (
            review_cache_path
            and review_cache_path.exists()
            and not dry_run
            and not self.config.force_review
        ):
            try:
                with open(review_cache_path, encoding="utf-8") as f:
                    raw_cache = json.load(f)
                cached_reviews = self._validate_review_cache(
                    raw_cache,
                    generation_results,
                    context.get("source_checksum"),
                    context.get("design_results"),
                )
                logger.info(
                    "REVIEW: loaded %d validated cached review result(s) from %s",
                    len(cached_reviews), review_cache_path,
                )
            except (json.JSONDecodeError, OSError, KeyError, TypeError, ValueError, UnicodeDecodeError) as exc:
                logger.warning("REVIEW: failed to load cache from %s: %s", review_cache_path, exc)
                cached_reviews = {}

        for idx, task in enumerate(tasks, start=1):
            _links = _build_provenance_links(task.task_id, context, ["design", "implement"])
            _task_span_cm = _phase_tracer.start_as_current_span(
                f"task.{task.task_id}",
                attributes={
                    "task.id": task.task_id,
                    "task.title": task.title,
                    "task.domain": task.domain or "",
                    "task.phase": "review",
                },
                links=_links,
            )
            _task_span = _task_span_cm.__enter__()
            previous_task_started_mono = _log_task_timing(
                "REVIEW",
                task.task_id,
                idx,
                len(tasks),
                start,
                previous_task_started_mono,
            )
            _log_task_boundary_start(task, phase="review")
            task_status = "unknown"
            task_cost: Optional[float] = None
            # Count constraint types (always, for coverage report)
            for constraint in task.prompt_constraints:
                key = constraint.split("(")[0].strip()[:60]
                constraint_coverage[key] += 1

            env_fails = [
                c for c in task.environment_checks
                if c.get("status") == "fail"
            ]
            env_warns = [
                c for c in task.environment_checks
                if c.get("status") == "warn"
            ]

            if dry_run:
                # --- Dry-run path (unchanged) ---
                review_items.append({
                    "task_id": task.task_id,
                    "title": task.title,
                    "domain": task.domain,
                    "constraint_count": len(task.prompt_constraints),
                    "env_failures": len(env_fails),
                    "env_warnings": len(env_warns),
                    "review_status": "dry_run_pending",
                })
                _task_span.set_attribute("task.status", "dry_run_pending")
                _log_task_boundary_complete(
                    task.task_id,
                    status="dry_run_pending",
                    phase="review",
                )
                _task_span_cm.__exit__(None, None, None)
                continue

            # --- Real-mode path ---
            try:
                gen_result = generation_results.get(task.task_id)

                # Skip tasks that were not generated successfully
                if gen_result is None or not gen_result.success:
                    logger.warning(
                        "REVIEW: skipping task %s (%s) — no successful generation result",
                        task.task_id, task.title,
                    )
                    review_items.append({
                        "task_id": task.task_id,
                        "title": task.title,
                        "domain": task.domain,
                        "constraint_count": len(task.prompt_constraints),
                        "env_failures": len(env_fails),
                        "env_warnings": len(env_warns),
                        "review_status": "skipped_no_generation",
                    })
                    task_status = "skipped_no_generation"
                    continue

                # Skip tasks that failed INTEGRATE (e.g. truncation-blocked)
                _int_result = integration_results_ctx.get(task.task_id, {})
                if isinstance(_int_result, dict) and _int_result.get("success") is False:
                    _int_status = _int_result.get("status", "unknown")
                    logger.warning(
                        "REVIEW: skipping task %s (%s) — integration failed (status=%s)",
                        task.task_id, task.title, _int_status,
                    )
                    review_items.append({
                        "task_id": task.task_id,
                        "title": task.title,
                        "domain": task.domain,
                        "constraint_count": len(task.prompt_constraints),
                        "env_failures": len(env_fails),
                        "env_warnings": len(env_warns),
                        "review_status": "skipped_integration_failed",
                        "integration_status": _int_status,
                    })
                    task_status = "skipped_integration_failed"
                    continue

                # Read generated code for review.
                # Exclude downstream stub files (Gate 2c) from the review body
                # so the reviewer doesn't penalize minimal placeholders that are
                # intentionally deferred to later tasks.
                task_downstream = set(downstream_map.get(task.task_id, []))
                code_parts = []
                excluded_downstream = []
                for fpath in gen_result.generated_files:
                    try:
                        if not fpath.exists():
                            logger.warning(
                                "REVIEW: file %s listed in generated_files "
                                "does not exist on disk — skipping "
                                "(may have been cleaned up before review)",
                                fpath,
                            )
                            continue
                        # Check if this file is a downstream stub
                        rel_path = str(fpath)
                        is_downstream = any(
                            rel_path.endswith(ds) for ds in task_downstream
                        )
                        if is_downstream:
                            excluded_downstream.append(fpath.name)
                            continue

                        content = fpath.read_text(encoding="utf-8")
                        code_parts.append(f"# File: {fpath.name}\n{content}")
                    except (OSError, UnicodeDecodeError) as exc:
                        logger.warning("REVIEW: could not read %s: %s", fpath, exc)
                if excluded_downstream:
                    code_parts.append(
                        f"# NOTE: {len(excluded_downstream)} file(s) excluded from review "
                        f"(downstream stubs for later tasks): {', '.join(excluded_downstream)}"
                    )
                    logger.info(
                        "REVIEW: excluded %d downstream stub(s) from review for %s: %s",
                        len(excluded_downstream), task.task_id, excluded_downstream,
                    )
                generated_code = "\n\n".join(code_parts)
                if not generated_code.strip():
                    logger.warning(
                        "REVIEW: skipping task %s (%s) — generated code is empty",
                        task.task_id, task.title,
                    )
                    review_items.append({
                        "task_id": task.task_id,
                        "title": task.title,
                        "domain": task.domain,
                        "constraint_count": len(task.prompt_constraints),
                        "env_failures": len(env_fails),
                        "env_warnings": len(env_warns),
                        "review_status": "skipped_no_code",
                    })
                    task_status = "skipped_no_code"
                    continue
                task_test = test_by_task.get(task.task_id, {})

                # Warn when a generated task has no test results — the
                # reviewer should be aware that test coverage is absent.
                if not task_test or task_test.get("status") in (
                    "skipped_no_generation", "skipped_integration_failed",
                ):
                    logger.warning(
                        "REVIEW: task %s has no test results (test_status=%s) "
                        "— review will proceed without test coverage signal",
                        task.task_id,
                        task_test.get("status", "missing"),
                    )
                    task_test.setdefault("_no_test_coverage", True)

                # Check pre-validated cache before LLM call
                cached = cached_reviews.get(task.task_id)
                if cached:
                    # R2-T5: Validate cached entry has required fields before
                    # accepting.  If critical fields are missing the entry was
                    # written under an older schema — fall through to fresh review.
                    _REQUIRED_CACHED_FIELDS = {"score", "verdict", "passed", "status"}
                    _missing_fields = _REQUIRED_CACHED_FIELDS - set(cached.keys())
                    if _missing_fields:
                        logger.warning(
                            "REVIEW: cached entry for %s missing fields %s "
                            "(schema drift) — regenerating",
                            task.task_id, sorted(_missing_fields),
                        )
                        cached = None  # fall through to fresh review below
                    else:
                        review = {**cached, "review_status": "cached"}
                        review["title"] = task.title
                        review["domain"] = task.domain
                        review["constraint_count"] = len(task.prompt_constraints)
                        review["env_failures"] = len(env_fails)
                        review["env_warnings"] = len(env_warns)

                        # R2-T8: If cached review has no FM validation data,
                        # run FM validation now and append violations.
                        if (
                            "fm_violations" not in review
                            and self.config.manifest_consumption_enabled
                        ):
                            _registry = self.config.manifest_registry
                            _fwd_manifest = context.get("forward_manifest")
                            if _registry is not None and _fwd_manifest is not None:
                                try:
                                    from startd8.forward_manifest_validator import validate_forward_manifest
                                    _all_fm = validate_forward_manifest(_fwd_manifest, _registry) or []
                                    _task_files = set(task.target_files) if task.target_files else set()
                                    _task_fm = []
                                    for _v in _all_fm:
                                        _vp = getattr(_v, "file_path", None)
                                        if _vp is None:
                                            _task_fm.append(_v)
                                        elif _vp in _task_files or any(
                                            _vp.endswith(tf) or tf.endswith(_vp)
                                            for tf in _task_files
                                        ):
                                            _task_fm.append(_v)
                                    _err_v = [v for v in _task_fm if getattr(v, "severity", "error") == "error"]
                                    _warn_v = [v for v in _task_fm if getattr(v, "severity", "error") == "warning"]
                                    if _err_v:
                                        review["passed"] = False
                                        review["verdict"] = "FAIL"
                                        review.setdefault("issues", []).extend([
                                            f"[BLOCKING] Contract Violation: {v.violation_type} ({v.contract_id}) - Expected: {v.expected}, Actual: {v.actual}"
                                            for v in _err_v
                                        ])
                                    if _warn_v:
                                        review.setdefault("issues", []).extend([
                                            f"[MINOR] Contract Advisory: {v.violation_type} ({v.contract_id}) - {v.expected}"
                                            for v in _warn_v
                                        ])
                                    review["fm_violations"] = {
                                        "error_count": len(_err_v),
                                        "warning_count": len(_warn_v),
                                        "violation_ids": [
                                            getattr(v, "contract_id", "?") for v in _task_fm
                                        ],
                                        "retroactive": True,
                                    }
                                    logger.info(
                                        "REVIEW: retroactively validated FM for cached %s "
                                        "(%d errors, %d warnings)",
                                        task.task_id, len(_err_v), len(_warn_v),
                                    )
                                except Exception as _fm_cache_err:
                                    logger.debug(
                                        "REVIEW: FM validation on cached %s failed: %s",
                                        task.task_id, _fm_cache_err,
                                    )

                        if review.get("passed", False):
                            total_passed += 1
                        else:
                            total_failed += 1
                        review_items.append(review)
                        task_status = "cached"
                        task_cost = _coerce_optional_float(review.get("cost"))
                        logger.info(
                            "REVIEW: using cached result for %s (score=%s, passed=%s)",
                            task.task_id, cached.get("score"), cached.get("passed"),
                        )
                        continue

                # ── Layer 4: Thread design document into REVIEW ────────────
                design_results = context.get("design_results", {})
                task_design = design_results.get(task.task_id, {})
                task_design_doc = (
                    task_design.get("design_document")
                    if task_design.get("status") in ("designed", "adopted", "refined")
                    else None
                )
                # Gate 4: truncation info for this task (if flagged)
                task_truncation = truncation_flags.get(task.task_id)

                # PCA-302/505: assemble project context for review
                _project_name = context.get("plan_title") or (
                    Path(context.get("project_root", ".")).name
                    if context.get("project_root") else None
                )
                # PCA-505: check if this task had existing files during IMPLEMENT
                _gen_meta = getattr(gen_result, "metadata", {}) or {}
                _had_existing = bool(_gen_meta.get("had_existing_files"))
                # Also check generation_results for existing file info
                if not _had_existing:
                    _impl_results = context.get("implementation", {})
                    for _tr in _impl_results.get("task_reports", []):
                        if _tr.get("task_id") == task.task_id and _tr.get("had_existing_files"):
                            _had_existing = True
                            break
                _project_context = {
                    "plan_title": context.get("plan_title"),
                    "plan_goals": context.get("plan_goals", []),
                    "architectural_context": context.get("architectural_context", {}),
                    "project_name": _project_name,
                    "had_existing_files": _had_existing,
                }

                # PCA-402: track onboarding field consumption in REVIEW
                if context.get("service_metadata") is not None:
                    _track_onboarding_consumption(context, "service_metadata", "REVIEW")
                if context.get("architectural_context"):
                    _track_onboarding_consumption(context, "architectural_context", "REVIEW")

                # GAP1-A: Pre-compute FM violations so they appear in the review PROMPT
                # R2-T3: Filter violations to only those affecting this task's files
                _pre_fm_violations: list[Any] = []
                if self.config.manifest_consumption_enabled:
                    _registry = self.config.manifest_registry
                    _fwd_manifest = context.get("forward_manifest")
                    if _registry is not None and _fwd_manifest is not None:
                        try:
                            from startd8.forward_manifest_validator import validate_forward_manifest
                            _all_fm_violations = validate_forward_manifest(_fwd_manifest, _registry) or []
                            # Filter: only include violations whose file_path
                            # matches one of this task's target files
                            _task_files = set(task.target_files) if task.target_files else set()
                            for _v in _all_fm_violations:
                                _vpath = getattr(_v, "file_path", None)
                                if _vpath is None:
                                    # No file_path on violation — include it
                                    # (project-wide structural violation)
                                    _pre_fm_violations.append(_v)
                                elif _vpath in _task_files or any(
                                    _vpath.endswith(tf) or tf.endswith(_vpath)
                                    for tf in _task_files
                                ):
                                    _pre_fm_violations.append(_v)
                        except Exception as _pre_fm_err:
                            logger.debug(
                                "REVIEW: pre-prompt FM validation failed for %s: %s",
                                task.task_id, _pre_fm_err,
                            )

                review = self._review_task(
                    task, generated_code, task_test,
                    design_document=task_design_doc,
                    parameter_sources=context.get("parameter_sources"),
                    semantic_conventions=context.get("semantic_conventions"),
                    truncation_info=task_truncation,
                    project_context=_project_context,
                    service_metadata=context.get("service_metadata"),
                    refine_provenance=context.get("refine_provenance"),
                    forward_contract_violations=_pre_fm_violations or None,  # GAP1-A
                )
                review["title"] = task.title
                review["domain"] = task.domain
                review["constraint_count"] = len(task.prompt_constraints)
                review["env_failures"] = len(env_fails)
                review["env_warnings"] = len(env_warns)
                review["review_status"] = review.get("status", "reviewed")
                if task_truncation is not None:
                    review["truncation_warning"] = True
                    review["truncation_confidence"] = task_truncation.get("max_confidence", 0.0)
                    review["truncation_source"] = task_truncation.get("source", "unknown")

                # Phase 5: FM enforcement gate — reuse pre-computed violations
                # from GAP1-A (above) to avoid redundant validate_forward_manifest call.
                # R2-T4: The pre-prompt computation and this enforcement gate used
                # identical inputs; deduplicating removes the redundant second call.
                # R2-T3: violations are already filtered per-task by target file paths.
                if _pre_fm_violations:
                    try:
                        error_violations = [
                            v for v in _pre_fm_violations
                            if getattr(v, "severity", "error") == "error"
                        ]
                        warning_violations = [
                            v for v in _pre_fm_violations
                            if getattr(v, "severity", "error") == "warning"
                        ]

                        if error_violations:
                            review["passed"] = False
                            review["verdict"] = "FAIL"
                            review.setdefault("issues", []).extend([
                                f"[BLOCKING] Contract Violation: {v.violation_type} ({v.contract_id}) - Expected: {v.expected}, Actual: {v.actual}"
                                for v in error_violations
                            ])
                            logger.warning(
                                "REVIEW: task %s failed ForwardManifest validation with %d error(s)",
                                task.task_id, len(error_violations)
                            )

                        if warning_violations:
                            review.setdefault("issues", []).extend([
                                f"[MINOR] Contract Advisory: {v.violation_type} ({v.contract_id}) - {v.expected}"
                                for v in warning_violations
                            ])

                        # R2-T8: Persist FM violation summary in review for cache consumers
                        review["fm_violations"] = {
                            "error_count": len(error_violations),
                            "warning_count": len(warning_violations),
                            "violation_ids": [
                                getattr(v, "contract_id", "?") for v in _pre_fm_violations
                            ],
                        }
                    except Exception as val_error:
                        logger.error(
                            "REVIEW: ForwardManifest enforcement failed for %s: %s",
                            task.task_id, val_error, exc_info=True
                        )
                
                total_cost += review.get("cost", 0.0)
                if review.get("passed", False):
                    total_passed += 1
                else:
                    total_failed += 1

                review_items.append(review)
                task_status = str(review.get("review_status", "reviewed"))
                task_cost = _coerce_optional_float(review.get("cost"))

                # Emit quality gate result (Item 10)
                try:
                    gate_result = GateEmitter.from_review_result(
                        task_id=task.task_id,
                        review_dict=review,
                        workflow_id=context.get("workflow_id", "unknown"),
                        trace_id=context.get("trace_id"),
                    )
                    GateEmitter.emit(gate_result)
                except Exception as e:
                    logger.warning("Failed to emit review gate result for %s: %s", task.task_id, e)
            except Exception as exc:
                logger.warning(
                    "REVIEW: unexpected error for task %s: %s",
                    task.task_id, exc, exc_info=True,
                )
                review_items.append(
                    self._make_error_review_entry(task, exc, env_fails, env_warns)
                )
                total_failed += 1
                _task_span.set_attribute("task.status", "error")
                task_status = "error"
            finally:
                _sc = _capture_task_span_context(_task_span)
                if _sc and review_items:
                    review_items[-1]["_span_context"] = _sc
                _log_task_boundary_complete(
                    task.task_id,
                    status=task_status,
                    phase="review",
                    cost_usd=task_cost,
                )
                _task_span_cm.__exit__(None, None, None)

        _SKIPPED_STATUSES = {
            "skipped_no_generation",
            "skipped_integration_failed",
            "skipped_no_code",
        }
        per_task: dict[str, Any] = {}
        for item in review_items:
            task_id = item.get("task_id")
            if not task_id:
                continue
            status = item.get("review_status", "unknown")
            if status == "error":
                per_task[task_id] = {
                    "status": "error",
                    "passed": False,
                    "score": None,
                    "verdict": "ERROR",
                    "error": item.get("error", ""),
                }
            elif status in _SKIPPED_STATUSES:
                per_task[task_id] = {
                    "status": "skipped",
                    "passed": None,
                    "score": None,
                    "verdict": "SKIPPED",
                    "skip_reason": status,
                }
            else:
                # R2-T9: Preserve detail fields in per_task rollup so
                # downstream consumers have access to specific issues,
                # reviewed sections, and reviewer feedback.
                _raw_response = item.get("raw_response", "")
                _reviewer_feedback = (
                    _raw_response[:2000] if _raw_response else ""
                )
                per_task[task_id] = {
                    "status": status,
                    "passed": item.get("passed") if status in ("reviewed", "cached") else None,
                    "score": item.get("score"),
                    "verdict": item.get("verdict"),
                    "issues": item.get("issues", []),
                    "strengths": item.get("strengths", []),
                    "suggestions": item.get("suggestions", []),
                    "reviewer_feedback": _reviewer_feedback,
                }

        review_prompt_summary: dict[str, Any] = {
            "tasks_with_telemetry": 0,
            "prompt_chars_total": 0,
            "dropped_sections_total": 0,
            "truncation_count_total": 0,
        }
        _truncated_section_names: set[str] = set()
        _dropped_section_names: set[str] = set()
        for item in review_items:
            telemetry = item.get("prompt_telemetry")
            if not isinstance(telemetry, dict):
                continue
            review_prompt_summary["tasks_with_telemetry"] += 1
            review_prompt_summary["prompt_chars_total"] += int(
                telemetry.get("prompt_chars", 0) or 0
            )
            review_prompt_summary["dropped_sections_total"] += int(
                telemetry.get("dropped_section_count", 0) or 0
            )
            review_prompt_summary["truncation_count_total"] += int(
                telemetry.get("truncation_count", 0) or 0
            )
            # Collect which sections were truncated/dropped across all tasks
            _ts = telemetry.get("truncated_sections")
            if isinstance(_ts, dict):
                _truncated_section_names.update(_ts.keys())
            _ds = telemetry.get("dropped_sections")
            if isinstance(_ds, list):
                _dropped_section_names.update(_ds)
        if _truncated_section_names:
            review_prompt_summary["truncated_section_names"] = sorted(
                _truncated_section_names
            )
        if _dropped_section_names:
            review_prompt_summary["dropped_section_names"] = sorted(
                _dropped_section_names
            )

        output = {
            "review_items": review_items,
            "preflight_summary": preflight_summary,
            "constraint_coverage": dict(constraint_coverage),
            "tasks_with_env_issues": len([
                r for r in review_items
                if r.get("env_failures", 0) > 0 or r.get("env_warnings", 0) > 0
            ]),
            "total_cost": total_cost,
            "total_passed": total_passed,
            "total_failed": total_failed,
            "per_task": per_task,
            "prompt_telemetry": review_prompt_summary,
        }

        context["review_results"] = output

        # ER-010: Score elements in the element registry from review results
        _element_registry = context.get("_element_registry")
        if _element_registry is not None:
            self._score_elements_from_review(
                review_items, tasks, _element_registry,
            )

        # Context contract: validate REVIEW output model.
        # R2-T6: Respect gate mode — block raises, warn flags, skip ignores.
        try:
            ReviewPhaseOutput(review_results=context["review_results"])
        except Exception as _val_exc:
            _gate_mode = context.get("quality_gate_summary", {}).get(
                "policy_mode", "warn",
            )
            if _gate_mode == "block":
                raise RuntimeError(
                    f"REVIEW output validation failed (block policy): {_val_exc}"
                ) from _val_exc
            logger.warning(
                "REVIEW output validation failed (continuing per %s policy): %s",
                _gate_mode,
                _val_exc,
            )
            if _gate_mode == "warn":
                # Flag the output so downstream phases know validation failed
                output["_validation_failed"] = True
                output["_validation_error"] = str(_val_exc)

        # Persist review results for cache on re-run (v2 envelope)
        if review_cache_path and not dry_run:
            try:
                serializable_tasks: dict[str, Any] = {}
                for item in review_items:
                    tid = item.get("task_id")
                    if tid and item.get("review_status") in ("reviewed", "cached"):
                        # Compute code hash for staleness detection on next load
                        code_hash: str | None = None
                        gen_result = generation_results.get(tid)
                        if gen_result is not None:
                            code_hash = self._hash_generated_code(gen_result)
                        _serialized_entry: dict[str, Any] = {
                            "task_id": tid,
                            "score": item.get("score"),
                            "verdict": item.get("verdict"),
                            "passed": item.get("passed"),
                            "cost": item.get("cost", 0.0),
                            "tokens": item.get("tokens", {}),
                            "status": "reviewed",
                            "strengths": item.get("strengths", []),
                            "issues": item.get("issues", []),
                            "suggestions": item.get("suggestions", []),
                            "reviewed_code_hash": code_hash,
                        }
                        # R2-T8: Persist FM validation data so cached reviews
                        # can be loaded without re-running FM validation.
                        _fm_viols = item.get("fm_violations")
                        if _fm_viols is not None:
                            _serialized_entry["fm_violations"] = _fm_viols
                        serializable_tasks[tid] = _serialized_entry
                if serializable_tasks:
                    cache_envelope: dict[str, Any] = {
                        "_cache_meta": {
                            "schema_version": _CACHE_SCHEMA_VERSION,
                            "created_at": datetime.datetime.now(
                                datetime.timezone.utc
                            ).isoformat(),
                            "source_checksum": context.get("source_checksum"),
                            "design_hash": _compute_design_results_hash(
                                context.get("design_results", {})
                            ),
                        },
                        "tasks": serializable_tasks,
                    }
                    review_cache_path.parent.mkdir(parents=True, exist_ok=True)
                    atomic_write_json(review_cache_path, cache_envelope, indent=2)
                    logger.info(
                        "REVIEW: saved %d review results (v2) to %s",
                        len(serializable_tasks), review_cache_path,
                    )
            except Exception as exc:
                logger.warning(
                    "REVIEW: failed to write cache to %s: %s (non-fatal)",
                    review_cache_path, exc, exc_info=True,
                )

        duration = time.monotonic() - start

        logger.info(
            "REVIEW phase complete: %d items, %d passed, %d failed, $%.4f cost (%.2fs)",
            len(review_items), total_passed, total_failed, total_cost, duration,
        )

        # Fix 5: Track per-task cache usage for metadata
        cached_task_count = sum(
            1 for item in review_items
            if item.get("review_status") == "cached"
        )
        fresh_task_count = sum(
            1 for item in review_items
            if item.get("review_status") == "reviewed"
        )
        resumed_any = cached_task_count > 0

        # "cost" is the authoritative phase cost; output["total_cost"] is for reporting
        return {
            "output": output,
            "cost": total_cost,
            "metadata": {
                "duration": duration,
                "resumed": resumed_any,
                "cached_task_count": cached_task_count,
                "fresh_task_count": fresh_task_count,
            },
        }
