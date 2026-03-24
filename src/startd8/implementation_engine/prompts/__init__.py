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
        "Forward design content (preserve structure and semantics). "
        "If the design already covers a section, use its version. "
        "ADD sections only for gaps: Technical Approach, Code Structure, "
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
        "You are {language_role}. Implement the spec exactly. "
        "Output raw file content exactly as it should appear on disk. "
        "Do NOT wrap content in a script, generator, or any other meta-program. "
        "Complete implementations only — no stubs, TODOs, or pass bodies. "
        "Use parameter names from upstream documents verbatim. "
        "{coding_standards} "
        "{import_instruction}"
    ),
    "draft_system_edit": (
        "You are {language_role} editing existing source code. "
        "Output raw file content exactly as it should appear on disk. "
        "Do NOT wrap content in a script, generator, or any other meta-program. "
        "PRESERVE all unchanged code. Output the COMPLETE modified file. "
        "Use parameter names from upstream documents verbatim. "
        "{coding_standards} "
        "{import_instruction}"
    ),
    "draft_system_search_replace": (
        "You are {language_role} making targeted edits to large files. "
        "Output raw file content exactly as it should appear on disk. "
        "Do NOT wrap content in a script, generator, or any other meta-program. "
        "Minimal changes only. Output the COMPLETE modified file — every line. "
        "Use parameter names from upstream documents verbatim. "
        "{coding_standards} "
        "{import_instruction}"
    ),
    "draft_system_skeleton_fill": (
        "You are {language_role} filling method bodies in pre-assembled skeleton files. "
        "Output raw file content exactly as it should appear on disk. "
        "Do NOT wrap content in a script, generator, or any other meta-program. "
        "Implement ONLY methods marked with {stub_marker}. Do not modify pre-filled elements. "
        "Use parameter names from upstream documents verbatim. Do not rename them. "
        "Preserve all imports, class structure, and pre-filled method bodies exactly as provided. "
        "{coding_standards} "
        "{import_instruction}"
    ),
    "draft_skeleton_fill": (
        "Fill the unfilled method bodies in the pre-assembled skeleton file below.\n\n"
        "## Existing Skeleton\n"
        "The following file already exists with correct imports, class structure, "
        "and some method bodies pre-filled. Implement ONLY the method bodies "
        "marked as stubs.\n\n"
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
        "### Score: [0-100]\n"
        "### Verdict: [PASS/FAIL] (PASS if score >= {pass_threshold} AND no BLOCKING issues)\n"
        "### Strengths\n"
        "### Issues\nList each issue as: - [BLOCKING] / [MAJOR] / [MINOR] description\n"
        "### Suggestions"
    ),
    "review_system": (
        "You are a senior engineer reviewing code for correctness and completeness. "
        "Severity: BLOCKING (must fix), MAJOR (should fix), MINOR (nice to fix). "
        "Verify parameter names match upstream documents exactly. "
        "Cross-check: if the implementation follows the spec but violates language "
        "coding standards (e.g. wildcard imports in Java, bare except in Python, "
        "unused imports in Go, Console.Write instead of ILogger in C#, "
        "var instead of const in Node.js), flag as MAJOR with a note that the "
        "coding standard takes precedence over the spec. "
        "Convergence: state RESOLVED or STILL OUTSTANDING for prior issues."
    ),
    # --- Integration ---
    "integration": (
        "Finalize this implementation for production.\n\n"
        "## Task\n{task_description}\n\n"
        "## Implementation\n{implementation}\n\n"
        "## Review History\n{review_history}\n\n"
        "## Instructions\n{integration_instructions}\n{multi_file_directive}\n\n"
        "Make final polish, then output the production-ready code in a fenced block."
    ),
    # --- Framing templates ---
    "plan_context_edit_framing": (
        "The following plan describes CHANGES to existing code. Do NOT treat as greenfield.\n"
    ),
    "plan_context_create_framing": (
        "The following plan provides context. The design document (if present) is authoritative.\n"
    ),
    "arch_context_edit_framing": (
        "Apply these architectural constraints to the existing file(s). Do not redesign.\n"
    ),
    "spec_edit_preamble_base": (
        "## EDIT MODE\n"
        "**Task type: {task_verb}** existing code.\n"
        "Describe ONLY additions and modifications. List unchanged functions/classes.\n"
        "Specify exact insertion points.\n"
    ),
    "spec_edit_quantitative_constraint": (
        "**Existing file(s): {total_lines} lines.** "
        "Draft must be >= {min_lines} lines ({edit_min_pct}%).\n"
    ),
    "spec_create_preamble": (
        "## CREATE MODE — New Implementation\n"
        "**Task type: Implement** this specification from scratch.\n\n"
    ),
    "available_imports": (
        "## Available Imports\n\n"
        "The following packages are installed and available for import:\n\n"
        "{available_packages}\n\n"
        "{import_syntax}\n"
    ),
    "spec_completeness_warning": (
        "## Spec Completeness Warning\n"
        "These parameters from requirements are NOT in the spec — include them:\n"
        "{missing_lines}\n"
    ),
    # --- Context section templates (R0-2) ---
    "required_output_files": (
        "## Required Output Files\n"
        "This task produces MULTIPLE files. Your spec MUST describe the "
        "role and expected contents of EACH file:\n{file_manifest}\n\n"
        "In your Code Structure section, list each file separately with its "
        "classes/functions."
    ),
    "exemplar_reference": (
        "## Verified Reference (from {run_id}, score: {score})\n"
        "The following implementation was generated by this pipeline for a "
        "structurally similar task ({fingerprint}) and scored {score} with "
        "full contract compliance. Use the same patterns, import structure, "
        "and architectural approach."
    ),
    "sibling_imports": (
        "## Imports Used by Sibling Files in This Directory\n"
        "The following imports are used by other files in this "
        "service. Use the same packages and import patterns "
        "where applicable:\n\n"
        "```{fence_lang}\n{import_list}\n```"
    ),
    "local_modules": (
        "## Available Local Modules\n"
        "These files exist in the SAME directory as the file you are generating. "
        "Import from them using their module name (bare import, NOT qualified):\n\n"
        "{module_list}\n\n"
        "Do NOT use qualified imports like `from servicename.module import X`. "
        "Use bare `from module import X` since these are sibling files."
    ),
    # --- Output format templates ---
    "single_file_output": (
        "Provide the COMPLETE file content in a single fenced code block "
        "— not a program that generates it.\n"
    ),
    "multi_file_output": (
        "Produce a SEPARATE fenced code block for each file. "
        "First line comment = file path.\n\n"
        "REQUIRED files:\n{file_list}\n\n"
        "Format per file:\n```\n# <full path>\n<implementation>\n```\n\n"
        "Checklist — verify each file has a block:\n{file_checklist}\n\n"
        "Rules: Every file gets its own block. No skipping. "
        "Each block contains raw file content — not a program that generates it."
    ),
    "single_file_edit_output": (
        "Output the COMPLETE modified file ({existing_line_count} lines original).\n"
        "Your draft must be AT LEAST {min_output_lines} lines ({min_pct}% of existing).\n"
        "Do NOT omit or abbreviate existing code."
    ),
    "multi_file_edit_output": (
        "Output COMPLETE modified files — every line of original plus changes.\n"
        "{existing_line_summary}\n\n"
        "REQUIRED files:\n{file_list}\n\n"
        "Format per file:\n```\n# <full path>\n<complete modified file>\n```\n\n"
        "Checklist:\n{file_checklist}\n\n"
        "Rules: every file gets its own block. Preserve all existing code."
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
