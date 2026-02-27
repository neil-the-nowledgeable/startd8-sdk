"""
YAML prompt loader for the implementation engine.

Uses ``lru_cache`` + ``yaml.safe_load`` pattern matching the existing
``workflows/builtin/prompts/__init__.py`` loader.
"""

from functools import lru_cache
from pathlib import Path
from typing import Any, Dict

import yaml


__all__ = ["get_template", "format_prompt"]


_PROMPTS_DIR = Path(__file__).parent


# Inline fallback strings so the engine works without the YAML file installed.
_FALLBACK_TEMPLATES: Dict[str, str] = {
    "spec": (
        "You are a senior software architect acting as the Lead Contractor.\n\n"
        "## Task Description\n{task_description}\n{requirements_section}\n"
        "{context_sections}\n{critical_parameters_section}\n"
        "{forward_contracts_section}\n## Domain Constraints\n{domain_constraints}\n\n"
        "Create a detailed 8-section implementation specification.\n"
        "Sections: Task Summary, Requirements, Technical Approach, Code Structure, "
        "Acceptance Criteria, Edge Cases, Constraints, Examples."
    ),
    "spec_from_design": (
        "You are a senior software architect expanding an approved design document "
        "into a full implementation specification.\n\n"
        "## Design Document (AUTHORITATIVE — include verbatim)\n{design_document}\n\n"
        "## Task Description\n{task_description}\n{requirements_section}\n"
        "{context_sections}\n{critical_parameters_section}\n"
        "{forward_contracts_section}\n## Domain Constraints\n{domain_constraints}\n\n"
        "The design document's sections (What to Build, Files, API Surface, Constraints) "
        "are AUTHORITATIVE. Include them VERBATIM in your spec.\n"
        "ADD these new sections: Technical Approach, Code Structure, "
        "Acceptance Criteria, Edge Cases, Examples.\n"
        "Do NOT paraphrase or re-derive the design document's content."
    ),
    "draft": (
        "You are implementing code based on a detailed specification.\n\n"
        "## Implementation Specification\n{spec}\n\n"
        "## Previous Feedback (if any)\n{feedback}\n\n"
        "{existing_files_section}\n\n"
        "## Output Format\n{output_format}"
    ),
    "draft_edit": (
        "You are modifying an existing codebase based on a specification.\n\n"
        "{existing_files_section}\n\n"
        "## Implementation Specification (changes to apply)\n{spec}\n\n"
        "## Previous Feedback (if any)\n{feedback}\n\n"
        "## Output Format\n{output_format}"
    ),
    "draft_system_create": (
        "You are an expert Python engineer generating production-quality source code "
        "from a specification. Implement the spec exactly. Emit complete implementations "
        "— no stubs or TODO placeholders."
    ),
    "draft_system_edit": (
        "You are an expert Python engineer editing existing source code. "
        "PRESERVE all existing code not being changed. ADD or MODIFY only what the "
        "spec specifies. Your output MUST include the complete modified file — "
        "not just the changed sections."
    ),
    "draft_system_search_replace": (
        "You are an expert Python engineer editing large existing source files. "
        "Make minimal, targeted changes. Preserve all unchanged code. "
        "Your output MUST be the complete modified file — include every line, "
        "changing only what the spec requires."
    ),
    "review": (
        "You are reviewing an implementation as the Lead Contractor.\n\n"
        "## Original Task\n{task_description}\n\n"
        "## Your Specification\n{spec}\n\n"
        "## Implementation to Review\n{implementation}\n\n"
        "## Review Instructions\nEvaluate the implementation against your specification.\n\n"
        "## Required Output Format\n\n"
        "### Score: [0-100]\n### Verdict: [PASS/FAIL]\n"
        "### Strengths\n- [What was done well]\n"
        "### Issues\n- [Problems found]\n"
        "### Suggestions\n- [Specific improvements]\n"
        "### Blocking Issues (if any)\n- [Issues that MUST be fixed]\n"
        "### Full Review\n[Detailed analysis]\n\n"
        "Pass threshold: {pass_threshold}"
    ),
}


@lru_cache(maxsize=4)
def _load_file(name: str) -> Dict[str, Any]:
    """Load and cache a YAML prompt file."""
    path = _PROMPTS_DIR / f"{name}.yaml"
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_template(prompt_name: str) -> str:
    """Get a prompt template by name.

    Loads from the YAML file first; falls back to inline strings if
    the YAML file is unavailable.

    Args:
        prompt_name: Template key (e.g. ``spec``, ``draft``, ``review``).

    Returns:
        Template string with ``{placeholder}`` markers.
    """
    try:
        data = _load_file("implementation_engine")
        prompts = data.get("prompts", {})
        entry = prompts.get(prompt_name, {})
        template = entry.get("template") if isinstance(entry, dict) else None
        if template:
            return template
    except (FileNotFoundError, KeyError, TypeError):
        pass

    fallback = _FALLBACK_TEMPLATES.get(prompt_name)
    if fallback:
        return fallback
    raise KeyError(f"No template found for '{prompt_name}'")


def format_prompt(prompt_name: str, **kwargs: Any) -> str:
    """Load and format a prompt template.

    Args:
        prompt_name: Template key.
        **kwargs: Placeholder values.

    Returns:
        Formatted prompt string.
    """
    template = get_template(prompt_name)
    return template.format(**kwargs)
