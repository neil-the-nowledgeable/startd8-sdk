"""
Spec builder for the implementation engine.

Produces an 8-section implementation specification from a task description
and context.
"""

import ast
import json
import os
import uuid
from typing import Any, Dict, List, Optional

from ..logging_config import get_logger
from ..costs.pricing import PricingService
from .budget import (
    ARCH_CONTEXT_MAX_CHARS,
    PLAN_CONTEXT_MAX_CHARS,
    SPEC_CONTEXT_BUDGET_CHARS,
    TOTAL_SPEC_BUDGET_TOKENS,
    TRUNCATION_MARKER,
    enforce_prompt_budget,
    estimate_tokens,
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
    "build_constraint_block",
    "extract_spec_constraints",
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
    """Format prompt from consolidated YAML; use fallback when YAML missing."""
    try:
        template = get_template(template_name)
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


def _build_available_imports_section(context: Dict[str, Any]) -> str:
    """Build the available imports section from task dependencies.

    Strips version pins (e.g. ``grpcio==1.76.0`` → ``grpcio``) and formats
    as a bullet list.  Returns empty string when no dependencies are present.
    """
    deps = context.get("runtime_dependencies", [])
    if not deps:
        return ""
    package_lines = []
    for dep in sorted(deps):
        # Strip version pins: "grpcio==1.76.0" → "grpcio"
        pkg = dep
        for sep in ("==", ">=", "<=", "~=", "!=", "<", ">"):
            pkg = pkg.split(sep)[0]
        pkg = pkg.strip()
        if pkg:
            package_lines.append(f"- {pkg}")
    if not package_lines:
        return ""
    packages_str = "\n".join(package_lines)
    try:
        template = get_template("available_imports")
        return template.format(available_packages=packages_str)
    except (FileNotFoundError, KeyError, ImportError):
        return (
            "## Available Imports\n\n"
            "The following packages are installed and available for import:\n\n"
            f"{packages_str}\n\n"
            "Use ONLY these packages plus Python stdlib. Every non-stdlib symbol you\n"
            "reference MUST have a corresponding import statement at the top of the file.\n"
            "Do NOT import packages not listed above.\n"
        )


def _build_sibling_imports_section(context: Dict[str, Any]) -> str:
    """Extract imports from existing sibling files in the same directory.

    When generating a new file, knowing what its neighbors import
    provides project-specific framework context that no hardcoded
    template can match (e.g. the exact proto module names, the
    project's logging pattern, the OTel setup convention).

    Returns empty string if no Python siblings with imports are found.
    """
    existing_files = context.get("existing_files_content", {})
    if not existing_files:
        return ""

    # Determine the target directory from target_files
    target_files = context.get("target_files", [])
    if not target_files:
        return ""

    # Use the directory of the first target file
    target_dir = os.path.dirname(target_files[0]) if target_files else ""

    sibling_imports: set[str] = set()
    for path, content in existing_files.items():
        if not isinstance(content, str) or not path.endswith(".py"):
            continue
        if os.path.dirname(path) != target_dir:
            continue
        try:
            tree = ast.parse(content)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                try:
                    sibling_imports.add(ast.unparse(node))
                except (AttributeError, ValueError):
                    pass

    if not sibling_imports:
        return ""

    lines = [
        "## Imports Used by Sibling Files in This Directory\n",
        "The following imports are used by other files in this",
        "service. Use the same packages and import patterns",
        "where applicable:\n",
        "```python",
    ]
    lines.extend(sorted(sibling_imports))
    lines.append("```")
    return "\n".join(lines)


def extract_spec_constraints(spec_text: str) -> List[Dict[str, str]]:
    """Extract MUST and MUST NOT assertions from a spec document.

    Scans for patterns like:
    - ``MUST ...`` / ``must ...``
    - ``MUST NOT ...`` / ``Do NOT ...`` / ``MUST not ...``
    - ``Required: ...``
    - ``Constraint: ...``

    Returns:
        List of dicts: ``[{"type": "MUST"|"MUST_NOT", "text": "...", "source": "spec"}]``
    """
    import re

    constraints: List[Dict[str, str]] = []
    seen_texts: set = set()

    # Pattern 1: MUST NOT / must not / MUST not / Do NOT
    for match in re.finditer(
        r"(?:MUST\s+NOT|must\s+not|Do\s+NOT|do\s+not|SHOULD\s+NOT)\s+(.+?)(?:\.|$)",
        spec_text,
        re.MULTILINE,
    ):
        text = match.group(1).strip()
        if text and text not in seen_texts:
            seen_texts.add(text)
            constraints.append({"type": "MUST_NOT", "text": text, "source": "spec"})

    # Pattern 2: MUST / Required
    for match in re.finditer(
        r"(?:MUST|must|Required:?|REQUIRED:?)\s+(.+?)(?:\.|$)",
        spec_text,
        re.MULTILINE,
    ):
        text = match.group(1).strip()
        # Skip if already captured as MUST_NOT
        if text and text not in seen_texts and not text.upper().startswith("NOT"):
            seen_texts.add(text)
            constraints.append({"type": "MUST", "text": text, "source": "spec"})

    # Pattern 3: Constraint: ... (explicit constraint labels)
    for match in re.finditer(
        r"Constraint:?\s+(.+?)(?:\.|$)",
        spec_text,
        re.MULTILINE | re.IGNORECASE,
    ):
        text = match.group(1).strip()
        if text and text not in seen_texts:
            seen_texts.add(text)
            ctype = "MUST_NOT" if "not" in text.lower()[:10] else "MUST"
            constraints.append({"type": ctype, "text": text, "source": "spec"})

    return constraints


def build_constraint_block(context: Dict[str, Any]) -> tuple[str, List[Dict[str, str]]]:
    """Build a structured constraint block for the spec AND a machine-readable
    list for the review phase.

    Returns ``(spec_section_text, constraint_list)`` where
    ``constraint_list`` is stored in the task context for review.

    Sources checked (in order):
    - ``critical_parameters``: always MUST constraints
    - ``domain_constraints``: MUST_NOT if starts with "Do not"/"Never"
    - ``prompt_constraints``: MUST_NOT if starts with "Do not"/"Never"
    """
    constraints: List[Dict[str, str]] = []

    for param in context.get("critical_parameters", []):
        if isinstance(param, str) and param.strip():
            constraints.append({
                "type": "MUST",
                "text": param.strip(),
                "source": "critical_parameters",
            })

    for dc in context.get("domain_constraints", []):
        if isinstance(dc, str) and dc.strip():
            text = dc.strip()
            ctype = "MUST_NOT" if text.lower().startswith(("do not", "never")) else "MUST"
            constraints.append({"type": ctype, "text": text, "source": "domain_constraints"})

    for pc in context.get("prompt_constraints", []):
        if isinstance(pc, str) and pc.strip():
            text = pc.strip()
            ctype = "MUST_NOT" if text.lower().startswith(("do not", "never")) else "MUST"
            constraints.append({"type": ctype, "text": text, "source": "prompt_constraints"})

    if not constraints:
        return "", []

    lines = ["## Constraints\n"]
    for i, c in enumerate(constraints, 1):
        lines.append(f"{i}. **[{c['type']}]** {c['text']}")
    spec_text = "\n".join(lines)

    return spec_text, constraints


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

    # --- FR-MPA-005: Pre-assembly scope narrowing ---
    # When element tiers are available, narrow the spec to unfilled elements only.
    # This reduces W-3 waste (30-50% input token reduction).
    element_tiers = context.pop("element_tiers", None)
    if not element_tiers:
        artifacts = context.get("artifacts")
        if isinstance(artifacts, dict):
            element_tiers = artifacts.pop("element_tiers", None)

    pre_assembly_preamble = ""
    if element_tiers and isinstance(element_tiers, dict):
        pre_filled_names: list = []
        unfilled_names: list = []
        for file_path, file_tiers in element_tiers.items():
            if not isinstance(file_tiers, dict):
                continue
            for elem_name, info in file_tiers.items():
                if not isinstance(info, dict):
                    continue
                is_filled = info.get("pre_filled", False) or (
                    info.get("fill_source", "none") != "none"
                )
                if is_filled:
                    fill_src = info.get("fill_source", "pre-filled")
                    pre_filled_names.append(f"  - `{elem_name}` ({fill_src})")
                else:
                    tier = info.get("tier", "UNKNOWN")
                    unfilled_names.append(f"  - `{elem_name}` (tier: {tier})")

        if pre_filled_names:
            preamble_parts = [
                "## Pre-Assembly Scope (Mottainai)\n",
                "The following elements are already implemented deterministically "
                "and do NOT need specification:\n",
                "\n".join(pre_filled_names),
                "",
            ]
            if unfilled_names:
                preamble_parts.extend([
                    "Scope your specification to ONLY these unfilled elements:\n",
                    "\n".join(unfilled_names),
                    "",
                ])
            pre_assembly_preamble = "\n".join(preamble_parts) + "\n"
            logger.info(
                "Spec builder: pre-assembly narrowing — %d pre-filled, %d unfilled elements",
                len(pre_filled_names), len(unfilled_names),
            )

    if pre_assembly_preamble:
        task_description = pre_assembly_preamble + task_description

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

    # --- Design doc sections (A5: parity with Micro Prime REQ-DDS-001) ---
    design_doc_sections = context.pop("design_doc_sections", None)
    design_doc_section = ""
    if design_doc_sections and isinstance(design_doc_sections, list):
        dds_items = "\n".join(f"- {s}" for s in design_doc_sections)
        design_doc_section = (
            "\n## Implementation Context (design emphasis)\n"
            f"{dds_items}\n"
        )

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
    if design_doc_section:
        forward_contracts_section += design_doc_section

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

    # REQ-MP-1003: Reference implementation from copy-and-modify predecessor.
    reference_implementation = context.pop("reference_implementation", None)

    arch_ctx = context.pop("architectural_context", None)
    plan_ctx = context.pop("plan_context", None)
    project_obj = context.pop("project_objectives", None)
    sem_conv = context.pop("semantic_conventions", None)
    requirements_context = context.pop("requirements_context", None)
    protocol_guidance = context.pop("protocol_guidance", None)
    scope_boundary = context.pop("scope_boundary", None)
    manifest_obj = context.pop("manifest", None)
    raw_manifest = context.pop("forward_manifest", None)

    # --- Build prioritized sections (P0=never drop, P3=drop first) ---
    target_files = context.get("target_files")

    # P0: Core context (always kept)
    ctx_section = build_spec_context_section(context, output_format, target_files)
    prioritized: List[tuple] = [(0, "context", ctx_section)]

    # P1: Available imports (L1 — reduces import repair rate)
    available_imports_section = _build_available_imports_section(context)
    if available_imports_section:
        prioritized.append((1, "available_imports", available_imports_section))

    # P1: Sibling-file imports (L5+ — project-specific, preferred)
    sibling_section = _build_sibling_imports_section(context)
    if sibling_section:
        prioritized.append((1, "sibling_imports", sibling_section))

    # P1: Requirements and protocol guidance
    if requirements_context:
        prioritized.append((1, "requirements_ctx", f"## Requirements Context\n{requirements_context}"))
    if protocol_guidance:
        prioritized.append((1, "protocol", f"## Protocol Guidance\n{protocol_guidance}"))

    # P2: Architecture and plan context
    obj_section = build_spec_objectives_section(project_obj)
    if obj_section:
        prioritized.append((2, "objectives", obj_section))
    conv_section = build_spec_conventions_section(sem_conv)
    if conv_section:
        prioritized.append((2, "conventions", conv_section))
    arch_section = build_spec_arch_section(arch_ctx, is_edit=is_edit)
    if arch_section:
        prioritized.append((2, "arch", arch_section))
    plan_section = build_spec_plan_section(plan_ctx, is_edit=is_edit)
    if plan_section:
        prioritized.append((2, "plan", plan_section))

    # P3: Reference implementation, scope boundary (drop first)
    if scope_boundary:
        prioritized.append((3, "scope", f"## Scope Boundary\n{scope_boundary}"))
    if reference_implementation:
        prioritized.append((3, "reference", (
            "## Reference Implementation (predecessor — adapt, do not copy verbatim)\n"
            "```python\n"
            f"{reference_implementation}\n"
            "```"
        )))

    context_sections = enforce_prompt_budget(
        prioritized, TOTAL_SPEC_BUDGET_TOKENS, logger=logger,
    )

    template = get_template(selected_key)

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

    prompt = template.format(**format_kwargs)

    tokens = estimate_tokens(prompt)
    if tokens > TOTAL_SPEC_BUDGET_TOKENS:
        logger.info(
            "Spec prompt: %d tokens exceeds budget %d (template chrome + P0)",
            tokens, TOTAL_SPEC_BUDGET_TOKENS,
        )

    return prompt


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

    # CR-C2: Extract machine-readable MUST/MUST_NOT constraints from the
    # spec text for downstream review-phase enforcement.
    machine_constraints = extract_spec_constraints(response_text)

    spec = SpecResult(
        spec_id=spec_id,
        task_summary=task_description,
        requirements=requirements,
        technical_approach=technical_approach,
        acceptance_criteria=acceptance_criteria,
        code_structure=code_structure if code_structure else None,
        edge_cases=edge_cases,
        constraints=constraints,
        spec_constraints=machine_constraints,
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
