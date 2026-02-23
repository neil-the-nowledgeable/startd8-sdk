"""Externalized prompt templates for workflow prompt builders.

YAML files in this directory store prompt templates with ``str.format()``-style
``{placeholders}``.  Use :func:`get_template` / :func:`format_prompt` for the
``prompts:`` section, and :func:`get_section_template` /
:func:`format_section` / :func:`get_list_section` for other named sections
(e.g. ``iteration_context:``, ``design_principles:``).
"""

from pathlib import Path
from functools import lru_cache
from typing import Any

import yaml

_PROMPTS_DIR = Path(__file__).parent


@lru_cache(maxsize=8)
def _load_file(name: str) -> dict[str, Any]:
    """Load and cache a YAML prompt file by *name* (without extension)."""
    path = _PROMPTS_DIR / f"{name}.yaml"
    try:
        with path.open(encoding="utf-8") as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        raise FileNotFoundError(
            f"Prompt YAML file not found for phase '{name}': {path}"
        ) from None


def get_template(phase: str, prompt_name: str) -> str:
    """Return raw template string with {placeholders} intact."""
    data = _load_file(phase)
    prompts = data.get("prompts")
    if not isinstance(prompts, dict):
        raise KeyError(
            f"YAML file '{phase}' has no 'prompts' mapping "
            f"(got {type(prompts).__name__})"
        )
    if prompt_name not in prompts:
        raise KeyError(
            f"Prompt '{prompt_name}' not found in '{phase}'. "
            f"Available: {sorted(prompts)}"
        )
    return prompts[prompt_name]["template"]


def format_prompt(phase: str, prompt_name: str, **kwargs: Any) -> str:
    """Return formatted prompt with placeholders filled."""
    template = get_template(phase, prompt_name)
    return template.format(**kwargs)


# ---------------------------------------------------------------------------
# Generic section accessors (iteration_context, focus_lines, etc.)
# ---------------------------------------------------------------------------

def get_section_template(phase: str, section: str, key: str) -> str:
    """Return raw template string from a named YAML section.

    For example, ``get_section_template("architectural_review",
    "iteration_context", "first_round")`` returns the template for the
    first-round iteration context block.
    """
    data = _load_file(phase)
    sec = data.get(section)
    if not isinstance(sec, dict):
        raise KeyError(
            f"YAML file '{phase}' has no '{section}' mapping "
            f"(got {type(sec).__name__ if sec is not None else 'None'})"
        )
    if key not in sec:
        raise KeyError(
            f"Key '{key}' not found in '{phase}.{section}'. "
            f"Available: {sorted(sec)}"
        )
    entry = sec[key]
    if isinstance(entry, dict):
        template = entry.get("template")
        if template is None:
            raise KeyError(
                f"Entry '{key}' in '{phase}.{section}' is a dict but has no "
                f"'template' key. Available keys: {sorted(entry)}"
            )
        return template
    return str(entry)


def format_section(phase: str, section: str, key: str, **kwargs: Any) -> str:
    """Load and format a template from a named YAML section."""
    template = get_section_template(phase, section, key)
    try:
        return template.format(**kwargs)
    except KeyError as exc:
        raise KeyError(
            f"Missing placeholder {exc} in template '{phase}.{section}.{key}'. "
            f"Provided keys: {sorted(kwargs)}"
        ) from exc


def get_list_section(phase: str, section: str) -> list:
    """Return a list-valued section from a YAML prompt file.

    Used for structured data like ``design_principles`` and
    ``gap_hunting_lenses`` that are rendered into prompt text by
    caller-supplied helpers.
    """
    data = _load_file(phase)
    result = data.get(section)
    if not isinstance(result, list):
        raise KeyError(
            f"YAML file '{phase}' has no '{section}' list "
            f"(got {type(result).__name__ if result is not None else 'None'})"
        )
    return list(result)  # shallow copy to protect lru_cache'd data
