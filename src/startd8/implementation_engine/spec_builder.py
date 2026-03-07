"""
Spec builder for the implementation engine.

Extracted from ``LeadContractorWorkflow._build_spec_prompt`` and ``_create_spec``.
Produces an 8-section implementation specification from a task description and context.
"""

import json
import uuid
from typing import Any, Dict, List, Optional

from ..logging_config import get_logger
from ..costs.pricing import PricingService
from .budget import (
    ARCH_CONTEXT_MAX_CHARS,
    PLAN_CONTEXT_MAX_CHARS,
    SPEC_CONTEXT_BUDGET_CHARS,
    TRUNCATION_MARKER,
    truncate_arch_context,
    truncate_with_marker,
)
from .models import SpecResult
from .parsers import parse_list_section, parse_section_content
from .prompts import get_template


__all__ = [
    "build_spec",
    "build_spec_prompt",
    "build_spec_context_section",
    "build_spec_plan_section",
    "build_spec_arch_section",
    "build_spec_objectives_section",
    "build_spec_conventions_section",
    "format_context_value",
]

logger = get_logger(__name__)

_pricing = PricingService()


# ---------------------------------------------------------------------------
# Section builders (composable, independently callable)
# ---------------------------------------------------------------------------


def safe_json_dumps(obj: Any, indent: int = 2) -> str:
    """JSON dumps that handles non-serializable objects gracefully."""
    def default(o: Any) -> Any:
        if hasattr(o, "dict"):
            return o.dict()
        if hasattr(o, "model_dump"):
            return o.model_dump()
        return str(o)
    return json.dumps(obj, indent=indent, default=default)


def format_context_value(value: Any) -> str:
    """Format a context value as a bullet list or string."""
    if isinstance(value, list):
        return "\n".join(f"- {item}" for item in value)
    if isinstance(value, dict):
        return "\n".join(f"- **{k}**: {v}" for k, v in value.items())
    return str(value)


def build_spec_context_section(
    context: Dict[str, Any],
    output_format: Optional[str],
    target_files: Optional[List[str]],
) -> str:
    """Build general context section. File manifest + remaining keys."""
    parts: List[str] = []
    if target_files and len(target_files) > 1:
        file_manifest = "\n".join(f"  - `{f}`" for f in target_files)
        # Use inline template to avoid cross-package dependency on prime_context.yaml
        parts.append(
            f"## Required Output Files\n"
            f"This task produces MULTIPLE files. Your spec MUST describe the "
            f"role and expected contents of EACH file:\n{file_manifest}\n\n"
            f"In your Code Structure section, list each file separately with its "
            f"classes/functions."
        )

    # REQ-SPEC-102: Context budget management. 
    # If context is massive, we should avoid dumping everything.
    # However, for now, we just ensure it doesn't crash.
    context_str = (
        safe_json_dumps(context) if context else "No additional context provided."
    )
    if output_format:
        context_str += f"\n\nExpected Output Format:\n{output_format}"
    parts.append(f"## Context\n{context_str}")
    return "\n\n".join(parts)


def _format_lead_prompt(template_name: str, fallback: str, **kwargs: Any) -> str:
    """Format prompt from YAML template; use fallback when YAML missing."""
    try:
        from startd8.workflows.builtin.prompts import get_template as _get_prime_template
        template = _get_prime_template("lead_contractor", template_name)
        return template.format(**kwargs)
    except (FileNotFoundError, KeyError, ImportError):
        try:
            return fallback.format(**kwargs)
        except KeyError:
            return fallback


# Inline fallbacks
_PLAN_CONTEXT_EDIT_FRAMING_FALLBACK = (
    "The following plan excerpt describes CHANGES to apply to existing code. "
    "Do NOT treat it as a greenfield specification."
)
_PLAN_CONTEXT_CREATE_FRAMING_FALLBACK = (
    "The following plan excerpt provides context for this task. "
    "The design document (if present) is authoritative."
)
_ARCH_CONTEXT_EDIT_FRAMING_FALLBACK = (
    "Apply these architectural constraints to the existing file(s). "
    "Do not redesign from scratch."
)
_SPEC_EDIT_PREAMBLE_BASE_FALLBACK = (
    "## EDIT MODE — Existing Code Modification\n"
    "**Task type: {task_verb}** existing code.\n\n"
    "This task MODIFIES an existing file. The existing code is shown "
    "below in the task description.\n"
    "Your specification must:\n"
    "- Describe ONLY the additions and modifications needed\n"
    "- List which existing functions/classes to keep unchanged\n"
    "- NOT redesign or restructure existing code\n"
    "- Specify exact insertion points (e.g., 'Add after class X' "
    "or 'Modify method Y')\n"
)
_SPEC_EDIT_QUANTITATIVE_FALLBACK = (
    "\n**The existing file(s) total {total_lines} lines.** "
    "Your spec must result in a draft that is AT LEAST "
    "{min_lines} lines ({edit_min_pct}% of existing).\n"
)


def build_spec_plan_section(
    plan_ctx: Optional[str],
    is_edit: bool = False,
) -> str:
    """Build plan context section with truncation and framing."""
    if not plan_ctx or not plan_ctx.strip():
        return ""
    if is_edit:
        framing = _format_lead_prompt(
            "plan_context_edit_framing",
            _PLAN_CONTEXT_EDIT_FRAMING_FALLBACK,
        ).rstrip() + "\n\n"
    else:
        framing = _format_lead_prompt(
            "plan_context_create_framing",
            _PLAN_CONTEXT_CREATE_FRAMING_FALLBACK,
        ).rstrip() + "\n\n"
    plan_budget = PLAN_CONTEXT_MAX_CHARS - len(framing)
    truncated = truncate_with_marker(plan_ctx.strip(), plan_budget, TRUNCATION_MARKER)
    if len(truncated) < len(plan_ctx.strip()):
        logger.info(
            "Spec prompt: plan context truncated from %d to %d chars",
            len(plan_ctx), len(truncated),
        )
    return f"## Plan Context\n{framing}{truncated}"


def build_spec_arch_section(arch_ctx: Any, is_edit: bool = False) -> str:
    """Build architectural context section with truncation and framing."""
    if not arch_ctx:
        return ""
    truncated = truncate_arch_context(arch_ctx, ARCH_CONTEXT_MAX_CHARS)
    orig_len = len(safe_json_dumps(arch_ctx) if isinstance(arch_ctx, (dict, list)) else str(arch_ctx))
    if len(truncated) < orig_len:
        logger.info(
            "Spec prompt: arch context truncated from %d to %d chars",
            orig_len, len(truncated),
        )
    if is_edit:
        framing = _format_lead_prompt(
            "arch_context_edit_framing",
            _ARCH_CONTEXT_EDIT_FRAMING_FALLBACK,
        ).rstrip() + "\n\n"
        return f"## Project Architecture\n{framing}{truncated}"
    return f"## Project Architecture\n{truncated}"


def build_spec_objectives_section(project_obj: Any) -> str:
    """Build project objectives section."""
    if not project_obj:
        return ""
    return f"## Project Objectives\n{format_context_value(project_obj)}"


def build_spec_conventions_section(sem_conv: Any) -> str:
    """Build semantic conventions section."""
    if not sem_conv:
        return ""
    return f"## Semantic Conventions\n{format_context_value(sem_conv)}"


def _select_template_key(context: Dict[str, Any], override: Optional[str] = None) -> str:
    """Auto-select spec template: ``spec_from_design`` when design doc present.

    Args:
        context: Engine request context.
        override: Explicit template key (bypasses auto-selection).

    Returns:
        Template key string.
    """
    if override:
        return override
    if context.get("design_document"):
        return "spec_from_design"
    return "spec"


def build_spec_prompt(
    task_description: str,
    context: Dict[str, Any],
    output_format: Optional[str],
    template_key: Optional[str] = None,
    edit_min_pct: Optional[int] = 80,
) -> str:
    """Build the full spec prompt from context.

    Pops structured keys from *context* so the remainder can be JSON-serialized
    as general context. Callers should pass a **copy** of the original context.

    Args:
        task_description: Task description for the spec.
        context: Dict with plan_context, architectural_context, etc.
            Structured keys are popped.
        output_format: Optional output format string.
        template_key: Override template selection (``spec`` or ``spec_from_design``).
        edit_min_pct: Minimum % of existing lines in edit output.

    Returns:
        Formatted spec prompt string.
    """
    from ..contractors.prompt_utils import format_constraints

    selected_key = _select_template_key(context, template_key)
    logger.info("Spec builder: using template '%s'", selected_key)

    # --- Design document forwarding (Mottainai Rule 2) ---
    design_document = context.pop("design_document", None) or ""

    # --- Edit-aware spec framing ---
    existing_files = context.pop("existing_files", None)
    edit_mode = context.pop("edit_mode", None)
    is_edit = bool(existing_files) or (
        isinstance(edit_mode, dict) and edit_mode.get("mode") == "edit"
    )

    if is_edit:
        task_verb = "update"
        edit_preamble = _format_lead_prompt(
            "spec_edit_preamble_base",
            _SPEC_EDIT_PREAMBLE_BASE_FALLBACK,
            task_verb=task_verb.capitalize(),
        )
        if existing_files:
            total_lines = sum(
                len((c or "").splitlines()) for c in existing_files.values()
            )
            min_pct = edit_min_pct or 80
            min_lines = int(total_lines * min_pct / 100)
            edit_preamble += _format_lead_prompt(
                "spec_edit_quantitative_constraint",
                _SPEC_EDIT_QUANTITATIVE_FALLBACK,
                total_lines=total_lines,
                min_lines=min_lines,
                edit_min_pct=min_pct,
            )
        edit_preamble += "\n"
        task_description = edit_preamble + task_description

    # --- Constraint categorization ---
    raw_constraints = context.pop("domain_constraints", None)
    if raw_constraints and isinstance(raw_constraints, list):
        domain_constraints_str = format_constraints(raw_constraints)
    elif raw_constraints and isinstance(raw_constraints, str):
        domain_constraints_str = raw_constraints
    else:
        domain_constraints_str = "(No domain-specific constraints)"

    # --- Requirements text passthrough ---
    requirements_text = context.pop("requirements_text", "")
    requirements_section = ""
    if requirements_text:
        requirements_section = (
            "\n## Requirements (verbatim — authoritative for parameter details)\n"
            f"{requirements_text}\n"
        )

    # --- Forward contracts ---
    forward_contracts = context.pop("forward_contracts", None)
    forward_element_specs = context.pop("forward_element_specs", None)
    forward_contracts_section = ""
    if forward_contracts and isinstance(forward_contracts, str) and forward_contracts.strip():
        forward_contracts_section = (
            "\n## Interface Contract Bindings (must enforce)\n"
            f"{forward_contracts.strip()}\n"
        )
    if forward_element_specs and isinstance(forward_element_specs, str) and forward_element_specs.strip():
        forward_contracts_section += (
            "\n## Expected Code Elements (signatures, classes, bases)\n"
            f"{forward_element_specs.strip()}\n"
        )

    # --- Critical parameters ---
    critical_parameters = context.pop("critical_parameters", None)
    critical_parameters_section = ""
    if critical_parameters:
        if isinstance(critical_parameters, list):
            cp_str = "\n".join(f"- {p}" for p in critical_parameters)
        elif isinstance(critical_parameters, str):
            cp_str = critical_parameters
        else:
            cp_str = safe_json_dumps(critical_parameters, indent=2)
        critical_parameters_section = (
            "\n## Critical Parameters (from requirements — include verbatim in spec)\n"
            f"{cp_str}\n"
        )

    arch_ctx = context.pop("architectural_context", None)
    plan_ctx = context.pop("plan_context", None)
    project_obj = context.pop("project_objectives", None)
    sem_conv = context.pop("semantic_conventions", None)
    requirements_context = context.pop("requirements_context", None)
    protocol_guidance = context.pop("protocol_guidance", None)
    scope_boundary = context.pop("scope_boundary", None)
    manifest_obj = context.pop("manifest", None)
    raw_manifest = context.pop("forward_manifest", None)

    # --- Build sections ---
    target_files = context.get("target_files")
    sections: List[str] = []

    ctx_section = build_spec_context_section(context, output_format, target_files)
    sections.append(ctx_section)

    if requirements_context:
        sections.append(f"## Requirements Context\n{requirements_context}")
    if protocol_guidance:
        sections.append(f"## Protocol Guidance\n{protocol_guidance}")
    if scope_boundary:
        sections.append(f"## Scope Boundary\n{scope_boundary}")

    obj_section = build_spec_objectives_section(project_obj)
    if obj_section:
        sections.append(obj_section)
    conv_section = build_spec_conventions_section(sem_conv)
    if conv_section:
        sections.append(conv_section)
    arch_section = build_spec_arch_section(arch_ctx, is_edit=is_edit)
    if arch_section:
        sections.append(arch_section)
    plan_section = build_spec_plan_section(plan_ctx, is_edit=is_edit)
    if plan_section:
        sections.append(plan_section)

    context_sections = "\n\n".join(sections)

    if len(context_sections) > SPEC_CONTEXT_BUDGET_CHARS:
        logger.info(
            "Spec prompt: context sections %d chars exceeds budget %d",
            len(context_sections), SPEC_CONTEXT_BUDGET_CHARS,
        )

    template = get_template(selected_key)

    # Common placeholders; spec_from_design adds {design_document}
    format_kwargs = {
        "task_description": task_description,
        "requirements_section": requirements_section,
        "context_sections": context_sections,
        "critical_parameters_section": critical_parameters_section,
        "forward_contracts_section": forward_contracts_section,
        "domain_constraints": domain_constraints_str,
    }
    if selected_key == "spec_from_design":
        format_kwargs["design_document"] = design_document
    return template.format(**format_kwargs)


def build_spec(
    agent: Any,
    task_description: str,
    context: Dict[str, Any],
    output_format: Optional[str] = None,
    template_key: Optional[str] = None,
    edit_min_pct: Optional[int] = 80,
) -> SpecResult:
    """Create an 8-section implementation specification.

    This is the primary entry point for spec creation, equivalent to
    ``LeadContractorWorkflow._create_spec()``.

    Args:
        agent: Agent to use for spec generation (must have ``.generate()``).
        task_description: What to implement.
        context: Additional context dict. Structured keys are consumed.
        output_format: Optional output format guidance.
        template_key: Override template selection.
        edit_min_pct: Minimum % of existing lines in edit output.

    Returns:
        SpecResult with parsed sections and telemetry.
    """
    spec_id = f"spec-{uuid.uuid4().hex[:8]}"

    # Copy to avoid mutating caller's dict
    context = dict(context)

    prompt = build_spec_prompt(
        task_description, context, output_format,
        template_key=template_key,
        edit_min_pct=edit_min_pct,
    )

    response_text, response_time_ms, token_usage = agent.generate(prompt)

    # Parse structured sections
    requirements = parse_list_section(response_text, "Requirements")
    acceptance_criteria = parse_list_section(response_text, "Acceptance Criteria")
    edge_cases = parse_list_section(response_text, "Edge Cases")
    constraints = parse_list_section(response_text, "Constraints")
    technical_approach = parse_section_content(response_text, "Technical Approach")
    code_structure = parse_section_content(response_text, "Code Structure")

    spec = SpecResult(
        spec_id=spec_id,
        task_summary=task_description,
        requirements=requirements,
        technical_approach=technical_approach,
        acceptance_criteria=acceptance_criteria,
        code_structure=code_structure if code_structure else None,
        edge_cases=edge_cases,
        constraints=constraints,
        raw_spec=response_text,
        input_tokens=token_usage.input if token_usage else 0,
        output_tokens=token_usage.output if token_usage else 0,
        time_ms=response_time_ms,
    )

    spec.cost = _pricing.calculate_total_cost(
        getattr(agent, "model", "unknown"),
        spec.input_tokens,
        spec.output_tokens,
    )

    return spec
