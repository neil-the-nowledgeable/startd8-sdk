# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""Load WLQ agent-surface prompt templates from package config (or overrides).

Resolution order for each named prompt:

1. Explicit ``configured`` path (caller / LoopQueueConfig later)
2. Environment variable for that prompt (see ``PROMPT_ENV``)
3. Packaged file under ``startd8.workflows.loop_queue.prompts``

``agent_template_path`` on a job envelope still wins at render time and
bypasses these defaults entirely.
"""

from __future__ import annotations

import os
from importlib import resources
from pathlib import Path
from typing import Mapping, Optional

PROMPT_ENV: Mapping[str, str] = {
    "reflective-requirements.md": "STARTD8_WLQ_REFLECTIVE_TEMPLATE",
    "research.md": "STARTD8_WLQ_RESEARCH_TEMPLATE",
    "drain-handoff.md": "STARTD8_WLQ_HANDOFF_TEMPLATE",
    "drain-handoff-do-this-current.md": "STARTD8_WLQ_HANDOFF_DO_THIS_CURRENT",
    "drain-handoff-do-this-blind-rotate.md": (
        "STARTD8_WLQ_HANDOFF_DO_THIS_BLIND_ROTATE"
    ),
    "drain-handoff-reviewer-block.md": "STARTD8_WLQ_HANDOFF_REVIEWER_BLOCK",
    "crp-memory-preamble.md": "STARTD8_WLQ_CRP_MEMORY_PREAMBLE",
}

_PACKAGE = "startd8.workflows.loop_queue"
_PROMPTS_REL = Path(__file__).resolve().parent / "prompts"


def packaged_prompts_dir() -> Path:
    """Filesystem path to packaged prompts (src checkout or installed package)."""
    if _PROMPTS_REL.is_dir():
        return _PROMPTS_REL
    root = resources.files(_PACKAGE)
    return Path(str(root.joinpath("prompts")))


def resolve_prompt_path(
    name: str,
    *,
    configured: Optional[Path] = None,
) -> Path:
    """Resolve a prompt markdown path; fail closed if missing."""
    if configured is not None:
        path = Path(configured).expanduser()
        if not path.is_file():
            raise FileNotFoundError(f"configured WLQ prompt missing: {path}")
        return path.resolve()

    env_key = PROMPT_ENV.get(name)
    if env_key:
        env_val = os.environ.get(env_key)
        if env_val:
            path = Path(env_val).expanduser()
            if not path.is_file():
                raise FileNotFoundError(
                    f"${env_key} points at missing prompt: {path}"
                )
            return path.resolve()

    path = packaged_prompts_dir() / name
    if path.is_file():
        return path.resolve()

    # Wheel / zipimport: confirm resource exists even if Path is opaque.
    traversable = resources.files(_PACKAGE).joinpath("prompts", name)
    try:
        if traversable.is_file():  # type: ignore[attr-defined]
            # Best-effort filesystem path when available.
            candidate = Path(str(traversable))
            if candidate.is_file():
                return candidate.resolve()
    except Exception:
        pass
    raise FileNotFoundError(f"packaged WLQ prompt missing: {name}")


def load_prompt_text(
    name: str,
    *,
    configured: Optional[Path] = None,
) -> str:
    """Read prompt markdown (UTF-8), applying resolution order above."""
    env_key = PROMPT_ENV.get(name)
    if configured is not None or (env_key and os.environ.get(env_key)):
        return resolve_prompt_path(name, configured=configured).read_text(
            encoding="utf-8"
        )
    # Prefer importlib so wheel installs without extracting work.
    try:
        return (
            resources.files(_PACKAGE)
            .joinpath("prompts", name)
            .read_text(encoding="utf-8")
        )
    except (FileNotFoundError, OSError, TypeError):
        return resolve_prompt_path(name, configured=configured).read_text(
            encoding="utf-8"
        )
