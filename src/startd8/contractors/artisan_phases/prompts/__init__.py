"""Externalized prompt templates for artisan phases.

Each YAML file contains a ``prompts`` mapping of prompt names to entries
with at least a ``template`` key (str with ``{placeholder}`` syntax for
``str.format()``).  An optional ``depth_tiers`` top-level key holds
calibration tiers (used by plan ingestion).

YAML files live alongside this module — one per source phase:
``design.yaml``, ``plan_ingestion.yaml``, ``test_construction.yaml``,
``review.yaml``, ``implement.yaml``.

The loaded dicts are cached via ``lru_cache``.  Callers **must not**
mutate the returned data; public accessors return only strings or copies.
"""

from __future__ import annotations

import copy
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from ...prompt_utils import format_constraints  # noqa: F401 (re-export)
from ...prompt_utils import format_tiered_context  # noqa: F401 (re-export)

logger = logging.getLogger(__name__)

_PROMPTS_DIR = Path(__file__).parent


@lru_cache(maxsize=8)
def _load_file(name: str) -> dict[str, Any]:
    """Load and cache a YAML prompt file.

    Args:
        name: Phase name corresponding to ``<name>.yaml`` in the prompts dir.

    Returns:
        Parsed YAML dict.  **Do not mutate** — this object is cached.

    Raises:
        FileNotFoundError: If ``<name>.yaml`` does not exist.
        ValueError: If the file is not valid YAML or lacks the expected
            ``prompts`` mapping.
    """
    path = _PROMPTS_DIR / f"{name}.yaml"
    if not path.exists():
        raise FileNotFoundError(
            f"Prompt file for phase '{name}' not found: {path}"
        )

    logger.debug("Loading prompt file: %s", path)
    try:
        with path.open(encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as exc:
        raise ValueError(
            f"Invalid YAML in prompt file '{name}' ({path}): {exc}"
        ) from exc

    if not isinstance(data, dict):
        raise ValueError(
            f"Prompt file '{name}' must contain a YAML mapping, "
            f"got {type(data).__name__}"
        )
    if "prompts" not in data:
        raise ValueError(
            f"Prompt file '{name}' missing required top-level 'prompts' key"
        )

    return data


def get_template(phase: str, prompt_name: str) -> str:
    """Return raw template string with ``{placeholders}`` intact.

    Args:
        phase: Phase name (e.g. ``"design"``, ``"plan_ingestion"``).
        prompt_name: Key within the ``prompts`` mapping.

    Raises:
        KeyError: If *prompt_name* does not exist in the phase file.
        FileNotFoundError: If the phase YAML file does not exist.
    """
    data = _load_file(phase)
    prompts = data["prompts"]
    if prompt_name not in prompts:
        raise KeyError(
            f"Prompt '{prompt_name}' not found in '{phase}.yaml'. "
            f"Available: {', '.join(sorted(prompts))}"
        )
    entry = prompts[prompt_name]
    if not isinstance(entry, dict) or "template" not in entry:
        raise KeyError(
            f"Prompt entry '{prompt_name}' in '{phase}.yaml' must be a "
            f"mapping with a 'template' key"
        )
    return entry["template"]


def format_prompt(phase: str, prompt_name: str, **kwargs: Any) -> str:
    """Return formatted prompt with placeholders filled.

    Loads the template via :func:`get_template` and calls
    ``str.format(**kwargs)`` on it.
    """
    template = get_template(phase, prompt_name)
    return template.format(**kwargs)


def get_depth_tiers() -> dict[str, dict[str, Any]]:
    """Return a *copy* of DEPTH_TIERS from ``plan_ingestion.yaml``.

    Returns a deep copy so callers can safely mutate without corrupting
    the cached YAML data.
    """
    data = _load_file("plan_ingestion")
    return copy.deepcopy(data["depth_tiers"])
