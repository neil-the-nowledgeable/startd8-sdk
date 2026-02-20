"""Externalized prompt templates for prime contractor / lead contractor workflows.

YAML files in this directory store prompt templates with ``str.format()``-style
``{placeholders}``.  Use :func:`get_template` for the raw template and
:func:`format_prompt` to fill placeholders in one call.
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
