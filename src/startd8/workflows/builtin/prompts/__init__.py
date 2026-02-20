"""Externalized prompt templates for prime contractor / lead contractor workflows."""

from pathlib import Path
from functools import lru_cache
from typing import Any

import yaml

_PROMPTS_DIR = Path(__file__).parent


@lru_cache(maxsize=8)
def _load_file(name: str) -> dict[str, Any]:
    """Load and cache a YAML prompt file."""
    path = _PROMPTS_DIR / f"{name}.yaml"
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_template(phase: str, prompt_name: str) -> str:
    """Return raw template string with {placeholders} intact."""
    data = _load_file(phase)
    return data["prompts"][prompt_name]["template"]


def format_prompt(phase: str, prompt_name: str, **kwargs: Any) -> str:
    """Return formatted prompt with placeholders filled."""
    template = get_template(phase, prompt_name)
    return template.format(**kwargs)
