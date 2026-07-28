# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""Cross-vendor CRP reviewer tier presets (FR-23).

Cursor Task model slugs for ``executor=agent-surface`` + ``blind_rotate``.
Vendor order is stable: Anthropic → OpenAI → Google.
"""

from __future__ import annotations

from typing import Dict, List, Literal, Tuple

ReviewerTier = Literal["flagship", "mid_tier"]

#: Anthropic → OpenAI → Google (one slug each).
FLAGSHIP_CURSOR_ROSTER: Tuple[str, ...] = (
    "claude-opus-5-thinking-high",
    "gpt-5.6-luna-medium",
    "gemini-3.1-pro",
)

#: Mid / balanced capability across the same three vendors.
MID_TIER_CURSOR_ROSTER: Tuple[str, ...] = (
    "claude-sonnet-5-thinking-high",
    "gpt-5.6-terra-medium",
    "gemini-3.6-flash-high",
)

REVIEWER_TIER_ROSTERS: Dict[ReviewerTier, Tuple[str, ...]] = {
    "flagship": FLAGSHIP_CURSOR_ROSTER,
    "mid_tier": MID_TIER_CURSOR_ROSTER,
}

VENDOR_ORDER: Tuple[str, ...] = ("anthropic", "openai", "google")


def resolve_reviewer_tier_roster(tier: ReviewerTier) -> List[str]:
    """Return a mutable copy of the Cursor Task roster for *tier*."""
    try:
        return list(REVIEWER_TIER_ROSTERS[tier])
    except KeyError as e:
        raise ValueError(
            f"unknown reviewer_tier={tier!r}; expected flagship|mid_tier"
        ) from e


def list_reviewer_tiers() -> List[Dict[str, object]]:
    """Machine-readable catalog for CLI/docs/tests (FR-23.5)."""
    return [
        {
            "tier": "flagship",
            "description": "Top Anthropic + OpenAI + Google Cursor Task models",
            "vendors": list(VENDOR_ORDER),
            "roster": list(FLAGSHIP_CURSOR_ROSTER),
        },
        {
            "tier": "mid_tier",
            "description": "Mid/balanced Anthropic + OpenAI + Google Cursor Task models",
            "vendors": list(VENDOR_ORDER),
            "roster": list(MID_TIER_CURSOR_ROSTER),
        },
    ]
