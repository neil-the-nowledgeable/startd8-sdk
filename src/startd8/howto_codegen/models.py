"""Typed models for the det-howto projector (SCHEMA_det-howto-0.1).

A ``Howto`` is the ``$0`` projection of a REQ's declared command surface — the always-current
**command reference** for what a feature ships. Only the mechanical skeleton (commands · flags ·
prerequisites) is a projected field; the ``when``/``why``/``troubleshooting`` narrative is
HUMAN-RESIDUE (SCHEMA §5) and is carried only as an explicit placeholder, never invented prose.

Everything here is a plain typed dataclass — the projector (``projector.py``) returns these, not
dicts (STANDARD Part 1). ``HowtoFinding`` is duck-typed for ``coverage_map/findings_sarif`` — it
exposes ``check``/``severity``/``message``/``file_path`` so ``render_sarif_from_findings`` consumes
it with no adapter (STANDARD Part 3 / SCHEMA §7).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Literal, Optional

#: A projected howto starts at the lowest maturity rung (SCHEMA §4, STANDARD 6b — anti-inflation).
INITIAL_MATURITY = "0.1"

#: The closed conformance vocabulary the render/validator obey (SCHEMA §1 / §7).
FORMAT_VERSION = "det-howto/0.1"
COMPANION_KIND = "HOWTO"

#: Liveness classes (SCHEMA §3) — a prerequisite ref resolved on disk is LIVE or PHANTOM.
LivenessClass = Literal["LIVE", "PHANTOM", "LEGACY", "ABSENT"]


@dataclass(frozen=True)
class Command:
    """One entry in the projected command reference (SCHEMA §2 ``commands[]``).

    Derived from a ``## Contract projection`` row whose ``Kind`` is ``command``/``option``, or
    from a CLI-declaring FR. The projector invents no command and no flag (SCHEMA §5).
    """

    name: str
    kind: str  # "command" | "option"
    note: str = ""
    #: Where this command was derived from (a Contract-projection row or an FR id) — provenance,
    #: so a reader can trace every command back to an authored surface (STANDARD I-1).
    source: str = ""


@dataclass(frozen=True)
class Prerequisite:
    """One reuse/phantom-audit entry (SCHEMA §2 ``prerequisites[]``).

    Each authored ``Touches``/code-``Lives`` ref is resolved on disk: ``LIVE`` when the path
    exists, ``PHANTOM`` when it is named but absent (a howto referencing something that isn't
    there — SCHEMA §3). The projector never invents a prerequisite.
    """

    ref: str
    liveness: LivenessClass
    #: The FR that declared this ref (provenance for the audit).
    declared_by: str = ""


@dataclass(frozen=True)
class Howto:
    """The projected det-howto/0.1 document model (SCHEMA §1 header + §2 reference).

    Narrative fields (``when``/``why``/``troubleshooting``) are HUMAN-RESIDUE placeholders
    (SCHEMA §5) — the projector fills them with a stable placeholder sentinel, never invented
    prose. ``render.py`` stamps them verbatim so byte-identity holds.
    """

    # --- §1 header (core) ---
    version: str
    pairs_with: str  # the source REQ path — MUST resolve LIVE (§3); back-reference (STANDARD 6d)
    title: str
    name: str  # DIDL semantic name
    handle: str  # DIDL readable handle  (naming.name_forms kind="howto")
    ref: str  # DIDL canonical ref
    maturity: str = INITIAL_MATURITY
    format_version: str = FORMAT_VERSION
    companion_kind: str = COMPANION_KIND

    # --- §2 command reference (the projected skeleton) ---
    commands: List[Command] = field(default_factory=list)
    prerequisites: List[Prerequisite] = field(default_factory=list)

    # --- §3 liveness of the paired REQ itself ---
    pairs_with_liveness: LivenessClass = "LIVE"

    #: The human-residue placeholder text (SCHEMA §5). One sentinel so a validator can detect that
    #: the narrative was NOT machine-asserted as derived (SCHEMA §7).
    residue_placeholder: str = (
        "TODO (human-residue — not projected): the when / why / troubleshooting narrative."
    )


@dataclass(frozen=True)
class HowtoFinding:
    """A conformance finding — duck-typed for ``coverage_map/findings_sarif`` (STANDARD Part 3).

    Field names (``check``/``severity``/``message``/``file_path``) match what
    ``render_sarif_from_findings`` reads, so the SARIF renderer is **imported, not vendored**.
    """

    check: str
    severity: str  # "error" | "warning" | "note"
    message: str
    file_path: str
    line: Optional[int] = None
