"""
YAML prompt loader for the implementation engine.

Loads from the consolidated ``contractor_prompts.yaml``.
Falls back to inline strings if the YAML file is unavailable.
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
        "You are a senior software architect creating an implementation specification.\n\n"
        "## Task\n{task_description}\n{requirements_section}\n"
        "{context_sections}\n{critical_parameters_section}\n"
        "{forward_contracts_section}\n## Constraints\n{domain_constraints}\n\n"
        "Provide an 8-section specification: Task Summary, Requirements, "
        "Technical Approach, Code Structure, Acceptance Criteria, Edge Cases, "
        "Constraints, Examples."
    ),
    "spec_from_design": (
        "You are expanding an approved design document into a full specification.\n\n"
        "## Design Document (AUTHORITATIVE)\n{design_document}\n\n"
        "## Task\n{task_description}\n{requirements_section}\n"
        "{context_sections}\n{critical_parameters_section}\n"
        "{forward_contracts_section}\n## Constraints\n{domain_constraints}\n\n"
        "Forward design content verbatim. ADD: Technical Approach, Code Structure, "
        "Acceptance Criteria, Edge Cases, Examples."
    ),
    "draft": (
        "Implement the following specification.\n\n"
        "## Specification\n{spec}\n\n"
        "## Feedback\n{feedback}\n\n"
        "{existing_files_section}\n\n"
        "{supplementary_sections}\n\n"
        "## Output Format\n{output_format}"
    ),
    "draft_edit": (
        "Modify the existing code per the specification below.\n\n"
        "{existing_files_section}\n\n"
        "## Specification (changes to apply)\n{spec}\n\n"
        "## Feedback\n{feedback}\n\n"
        "{supplementary_sections}\n\n"
        "## Output Format\n{output_format}"
    ),
    "draft_system_create": (
        "You are an expert Python engineer. Implement the spec exactly. "
        "Complete implementations only — no stubs, TODOs, or pass bodies. "
        "Use parameter names from upstream documents verbatim. "
        "Ruff: no single-letter vars l/O/I; define helpers before use."
    ),
    "draft_system_edit": (
        "You are an expert Python engineer editing existing source code. "
        "PRESERVE all unchanged code. Output the COMPLETE modified file. "
        "Use parameter names from upstream documents verbatim. "
        "Ruff: no single-letter vars l/O/I; define helpers before use."
    ),
    "draft_system_search_replace": (
        "You are an expert Python engineer making targeted edits to large files. "
        "Minimal changes only. Output the COMPLETE modified file — every line. "
        "Use parameter names from upstream documents verbatim. "
        "Ruff: no single-letter vars l/O/I; define helpers before use."
    ),
    "draft_system_skeleton_fill": (
        "You are an expert Python engineer filling method bodies in pre-assembled skeleton files. "
        "Implement ONLY methods marked with `raise NotImplementedError`. Do not modify pre-filled elements. "
        "Use parameter names from upstream documents verbatim. Do not rename them. "
        "Preserve all imports, class structure, and pre-filled method bodies exactly as provided. "
        "Ruff: no single-letter vars l/O/I; define helpers before use; stdlib-only imports unless listed."
    ),
    "draft_skeleton_fill": (
        "Fill the unfilled method bodies in the pre-assembled skeleton file below.\n\n"
        "## Existing Skeleton\n"
        "The following file already exists with correct imports, class structure, "
        "and some method bodies pre-filled. Implement ONLY the method bodies "
        "marked with `raise NotImplementedError`.\n\n"
        "{skeleton_section}\n\n"
        "{pre_assembly_status}\n\n"
        "## Specification (scope: unfilled elements only)\n{spec}\n\n"
        "## Feedback\n{feedback}\n\n"
        "{supplementary_sections}\n\n"
        "## Output Format\n{output_format}"
    ),
    "review": (
        "Review this implementation against the specification.\n\n"
        "## Task\n{task_description}\n\n"
        "## Specification\n{spec}\n\n"
        "{enrichment_sections}\n\n"
        "{prior_issues_section}\n\n"
        "## Implementation\n{implementation}\n\n"
        "{convergence_instructions}\n\n"
        "## Output Format\n"
        "### Score: [0-100]\n### Verdict: [PASS/FAIL]\n"
        "### Strengths\n### Issues\n### Suggestions\n"
        "### Blocking Issues\n\n"
        "Pass threshold: {pass_threshold}"
    ),
    "review_system": (
        "You are a senior engineer reviewing code for correctness and completeness. "
        "Severity: BLOCKING (must fix), MAJOR (should fix), MINOR (nice to fix). "
        "Verify parameter names match upstream documents exactly. "
        "Convergence: state RESOLVED or STILL OUTSTANDING for prior issues."
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

    Loads from the consolidated YAML file first; falls back to inline
    strings if the YAML file is unavailable.

    Args:
        prompt_name: Template key (e.g. ``spec``, ``draft``, ``review``).

    Returns:
        Template string with ``{placeholder}`` markers.
    """
    try:
        data = _load_file("contractor_prompts")
        prompts = data.get("prompts", {})
        entry = prompts.get(prompt_name, {})
        template = entry.get("template") if isinstance(entry, dict) else None
        if template:
            return template
    except (FileNotFoundError, KeyError, TypeError, yaml.YAMLError):
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
    try:
        return template.format(**kwargs)
    except KeyError as e:
        raise KeyError(
            f"Template '{prompt_name}' missing placeholder: {e}"
        ) from e
