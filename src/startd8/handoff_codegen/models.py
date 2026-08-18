"""Typed models for the ``$0`` REQ+ledger → det-handoff/0.1 projector.

The second projector in the det-doc-kit family (after ``plan_codegen``), built against
``STANDARD_det-doc-kit-projector-pattern.md``. A :class:`Handoff` is a **pure projection** of a REQ
plus the delivery ledger: the mechanical spine derives; the Gotchas / session framing are
human-residue (``SCHEMA_det-handoff-0.1.md §5``), left as placeholders.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

FORMAT_VERSION = "det-handoff/0.1"
COMPANION_KIND = "HANDOFF"
PROJECTED_MATURITY = "0.1"


@dataclass(frozen=True)
class BuildStep:
    """One entry of the build order — an FR to implement, with its exit criterion (§2)."""

    fr: str
    name: str
    verify: str  # the FR's Verify: clause — the exit criterion


@dataclass(frozen=True)
class Prerequisite:
    """One reuse ref + whether it resolves on disk (§2 prerequisiteStatus / §3 liveness)."""

    ref: str
    resolved: bool


@dataclass(frozen=True)
class Handoff:
    """A projected det-handoff/0.1 document (SCHEMA §1–§5)."""

    version: str
    format_version: str
    pairs_with: str  # the REQ being handed off
    base: str  # main @ <sha> — the git base (from the ledger/repo)
    companion_kind: str
    maturity: str
    name: str
    handle: str
    ref: str
    # §2 the mechanical spine — all derived from REQ + ledger.
    spec: str
    build_order: Tuple[BuildStep, ...]
    prerequisites: Tuple[Prerequisite, ...]
    pointers: Tuple[str, ...]
    hand_back: Tuple[str, ...]
    # §5 human-residue placeholders — NEVER projected content (session-learned).
    gotchas_placeholder: str = (
        "_(human-residue — the handing-off session fills in repo/session-specific hazards; "
        "the projector never invents these)_"
    )
    framing_placeholder: str = (
        "_(human-residue — the strategic why-now / do-these-together framing is the human's to add)_"
    )


@dataclass(frozen=True)
class HandoffFinding:
    """A conformance / liveness finding — duck-typed for ``coverage_map/findings_sarif``."""

    check: str
    severity: str
    message: str
    file_path: str
    line: int = 0
