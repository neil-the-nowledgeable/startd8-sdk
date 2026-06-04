# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""Deterministic, zero-LLM report rendering + the FR-6/FR-21 labeling guard.

This module is the **default** explain/preflight rendering path. It MUST NOT import any
provider/agent module (enforced by a Phase-6 guard test) — that is what makes the
"zero-LLM explain path" (FR-15) true by construction rather than by hope. Any LLM narrative
is confined to the separate ``compose.py`` and may only reference claim ids already emitted
here; it cannot mint new load-bearing claims.
"""

from __future__ import annotations

import re
from typing import Iterable, List

from .models import (
    RECOGNIZED_LABEL_PREFIXES,
    FdeExplanation,
    FdePreflightReport,
    LabeledClaim,
)


class UnlabeledClaimError(Exception):
    """Raised by the labeling guard when a load-bearing line carries no recognized tag."""


# A "load-bearing" line is a content bullet that asserts a claim. The renderers always emit
# claims as "- **<TAG>** ...". Structural bullets (metadata, redaction manifest, track-2 skips,
# the paired Assumption line) are exempt — by prefix, or because they live under an exempt
# section. Any *other* bullet under a content section MUST carry a recognized tag, so a plain
# untagged claim ("- something happened") is caught, not just a mis-tagged bold bullet.
_CLAIM_BULLET = re.compile(r"^- \*\*([^*]+)\*\*")
_EXEMPT_BULLET_PREFIXES = (
    "- mode:",
    "- run_output_dir:",
    "- plan_path:",
    "- requirements_path:",
    "- feature_ids:",
    "- sdk_version:",
    "- protocol_version:",
    "- run_id:",
    "- generated_at:",
    "- fde.cost_usd:",
    "- plan:",
    "- track2_ran:",
    "- **Assumption:**",  # the assumption line; its paired mechanism line carries the tag
)
# Sections whose bullets are structural, not claims (lowercased substring match on the heading).
_EXEMPT_SECTION_SUBSTRINGS = ("redaction manifest", "track-2 skipped", "skipped")


def render_explanation(exp: FdeExplanation) -> str:
    """Deterministic markdown for an explanation (no LLM)."""
    return exp.to_markdown()


def render_preflight(rep: FdePreflightReport) -> str:
    """Deterministic markdown for a preflight report (no LLM)."""
    return rep.to_markdown()


def assert_all_labeled(markdown: str) -> None:
    """Labeling guard (FR-21 / R1-S1 / R5-S2).

    Fails if any load-bearing claim bullet lacks a recognized OBSERVED/MECHANISM/PREDICTION
    tag. Used as a post-compose gate (including after any LLM narrative) and in CI.
    """
    current_section = ""
    for raw in markdown.splitlines():
        line = raw.strip()
        if line.startswith("#"):
            current_section = line.lstrip("#").strip().lower()
            continue
        if not line.startswith("- "):
            continue
        if any(sub in current_section for sub in _EXEMPT_SECTION_SUBSTRINGS):
            continue  # structural bullet (manifest / skip list)
        if any(line.startswith(p) for p in _EXEMPT_BULLET_PREFIXES):
            continue
        m = _CLAIM_BULLET.match(line)
        if not m:
            # A content-section bullet with no "- **TAG**" is an untagged load-bearing claim.
            raise UnlabeledClaimError(
                f"untagged load-bearing claim (no source label): {line!r}"
            )
        tag = m.group(1)
        if not any(tag.startswith(prefix) for prefix in RECOGNIZED_LABEL_PREFIXES):
            raise UnlabeledClaimError(
                f"load-bearing claim with unrecognized source label {tag!r}: {line!r}"
            )


def assert_claims_labeled(claims: Iterable[LabeledClaim]) -> None:
    """Structural variant: assert each claim carries a valid label (cheap pre-render check)."""
    bad: List[str] = []
    for c in claims:
        if not any(c.tag().startswith(p) for p in RECOGNIZED_LABEL_PREFIXES):
            bad.append(c.text)
    if bad:
        raise UnlabeledClaimError(
            f"{len(bad)} claim(s) without a recognized label: {bad[:3]}"
        )
