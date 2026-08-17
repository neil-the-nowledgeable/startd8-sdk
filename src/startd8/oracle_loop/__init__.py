"""Oracle-generation loop (REQ v0.4.1) — seat a det-req spec's own ``Verify:`` clauses as a graded
generation fitness rung and feed a rung failure back as Prime regeneration feedback.

The public surface:

  - :class:`OracleVerdict` — the NEW Pydantic per-FR verdict this loop carries (distinct from the
    navigator's frozen dataclass ``OracleVerdict``; reuses only the navigator VERDICT_* string
    constants). Home of the FR-7 stateful ``assertion_confirmed`` disposition token.
  - :func:`grammar.parse_verify_clause` / :func:`grammar.parse_spec` — the FR-2 runnable-Verify parser.
  - :func:`runner.run_oracle` — the FR-1 sandboxed runner (the ORACLE rung's fitness).
  - :func:`loop.run_build_to_spec_loop` — the FR-4/5/6/7/8 closed loop.
  - config gate :func:`oracle_loop_enabled` (FR-11, default OFF).

Everything is inert and byte-identical until ``oracle_loop.enabled`` is flipped (FR-11).
"""

from __future__ import annotations

from pydantic import BaseModel

# Reuse the navigator's verdict-string constants — do NOT reuse its dataclass or its allow-list.
from ..navigator.verify_oracle import (
    VERDICT_ERROR,
    VERDICT_FAIL,
    VERDICT_PASS,
    VERDICT_SKIP,
)

__all__ = [
    "OracleVerdict",
    "VERDICT_PASS",
    "VERDICT_FAIL",
    "VERDICT_SKIP",
    "VERDICT_ERROR",
    "ASSERTION_UNREVIEWED",
    "ASSERTION_CONFIRMED_TRUE",
    "ASSERTION_CONFIRMED_FALSE",
]

# FR-7 disposition tokens for the per-pass prose assertion (default unreviewed).
ASSERTION_UNREVIEWED = "unreviewed"
ASSERTION_CONFIRMED_TRUE = "true"
ASSERTION_CONFIRMED_FALSE = "false"


class OracleVerdict(BaseModel):
    """A per-FR oracle verdict (FR-1/FR-3/FR-7). New Pydantic model — NOT the navigator dataclass.

    ``verdict`` reuses the navigator VERDICT_* strings. ``kind`` is the FR-2 grammar kind
    (one-shot | service | assertion | manual). ``assertion_confirmed`` (FR-7) is a stateful,
    defaulted-``unreviewed`` disposition on the prose residue — a positive auditable token, not the
    mere absence of a satisfied verdict.
    """

    fr_id: str
    kind: str
    verdict: str  # pass | fail | skip | error
    reason: str = ""
    assertion_text: str = ""
    # The exact one-shot argv or a human-readable probe descriptor (``GET /health -> 200``).
    command_or_probe: str = ""
    isolation_level: str = ""
    # FR-7: only meaningful on a ``pass``; defaults ``unreviewed`` so a passing pass never reads as
    # human-confirmed until an operator dispositions it.
    assertion_confirmed: str = ASSERTION_UNREVIEWED

    @property
    def is_runnable_verdict(self) -> bool:
        """A verdict that came from actually running (pass/fail/error), not a skipped residue."""
        return self.verdict in (VERDICT_PASS, VERDICT_FAIL, VERDICT_ERROR)


def oracle_loop_enabled() -> bool:
    """FR-11 capability gate. Default **false**; env ``STARTD8_ORACLE_LOOP_ENABLED`` overrides.

    Thin, self-contained (does not couple to ConfigManager). Truthy env values: ``1/true/yes/on``
    (case-insensitive). Everything else — including unset — is disabled.
    """
    import os

    raw = os.environ.get("STARTD8_ORACLE_LOOP_ENABLED", "").strip().lower()
    return raw in ("1", "true", "yes", "on")
