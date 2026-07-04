"""Roster construction for a consultation (FR-MMC-4).

Turns a list of ``provider:model`` specs into a ``{model_id: BaseAgent}`` roster, filtering
to vision-capable models (only vision models can take the images this workflow sends) and
recording which specs were unavailable (unknown provider, missing API key) instead of
crashing the whole run. Shared by the TUI and the CLI.
"""

from __future__ import annotations

from typing import Optional

from ..agents.base import BaseAgent
from ..agents.multimodal import model_supports_vision
from ..logging_config import get_logger
from ..model_catalog import Models

logger = get_logger(__name__)

# Default cross-vendor "council" (FR-MMC-4 / OQ-1) — one flagship per vendor, all vision-capable.
DEFAULT_COUNCIL: list[str] = [
    Models.CLAUDE_OPUS_LATEST,   # anthropic:claude-opus-4-8
    Models.GPT_FLAGSHIP_LATEST,  # openai:gpt-5.5
    Models.GEMINI_PRO_LATEST,    # gemini:gemini-2.5-pro
]


def build_roster(
    specs: "Optional[list[str]]" = None,
    *,
    require_vision: bool = True,
    validate: bool = True,
) -> "tuple[dict[str, BaseAgent], list[tuple[str, str]]]":
    """Build ``({model_id: agent}, unavailable)`` from model specs.

    ``unavailable`` is a list of ``(spec, reason)`` for specs that were skipped: non-vision
    models (when ``require_vision``) or specs that failed to resolve (missing key / unknown
    provider). Deferred import of :func:`resolve_agent_spec` keeps this module import-light.
    """
    from ..utils.agent_resolution import resolve_agent_spec

    specs = list(specs) if specs else list(DEFAULT_COUNCIL)
    roster: dict[str, BaseAgent] = {}
    unavailable: list[tuple[str, str]] = []

    for spec in specs:
        if require_vision and not model_supports_vision(spec):
            unavailable.append((spec, "not vision-capable"))
            continue
        try:
            roster[spec] = resolve_agent_spec(spec, name=spec, validate=validate)
        except Exception as exc:  # noqa: BLE001 — one bad spec must not sink the roster
            logger.info("consultation roster: %s unavailable (%s)", spec, exc)
            unavailable.append((spec, str(exc)))

    return roster, unavailable
