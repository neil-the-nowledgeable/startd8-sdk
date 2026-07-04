# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""Stakeholder Panel (codename *Kaigi*) — synthetic stakeholder agents kept available to answer
questions VIPP raises during kickoff preparation.

M0 shipped the authoring surface (roster contract + kickoff wiring). **M1 ships the live panel**:
per-persona agents (:class:`~startd8.stakeholder_panel.persona.Persona`), the session-scoped
:class:`~startd8.stakeholder_panel.panel.StakeholderPanel`, synthetic-claim provenance, transcript
persistence, and the ``startd8 panel`` CLI. With M1, :data:`PANEL_CONSUMABLE` is ``True`` — a roster
is not just *authored* but *consumable*.

The heavy query-time classes (``StakeholderPanel``, ``Persona``) are exposed lazily so importing this
package for the light authoring/assess path (or for ``PANEL_CONSUMABLE``) pulls no agent/LLM deps.

The Teian **point-value drafter** (``panel recommend`` → ``recommend_inputs``) was **dropped** in
project-start M2 (NR-7): an LLM cannot ground specific field values, so its "8%" starters were
industry-generic filler. Its one worth-keeping byproduct — the $0 "which fields are unfilled"
coverage signal (:func:`~startd8.stakeholder_panel.input_domains.unfilled_fields`) — survives as the
FR-13 discovery *trigger*. The passive ``Recommendation`` model / provenance / proposal-store types
remain (reused by ``requirements_panel`` / ``manifest_suggester``).

See ``docs/design/stakeholder-panel/`` for requirements (v0.3) and plan (v1.1).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from startd8.stakeholder_panel.models import (
    PROTOCOL_VERSION,
    Grounding,
    PanelAnswer,
    PanelQuestion,
    PersonaBrief,
    Recommendation,
    Roster,
)
from startd8.stakeholder_panel.input_domains import (
    SUPPORTED_DOMAINS,
    DomainSpec,
    FieldSlot,
    get_domain,
    resolve_owner,
    unfilled_fields,
)
from startd8.stakeholder_panel.proposals import (
    ProposalStore,
    gc_stale_proposals,
    latest_session,
)
from startd8.stakeholder_panel.recommend_provenance import (
    ESTIMATE_PROVENANCE,
    assert_not_authored,
    is_estimate,
    panel_origin,
)
from startd8.stakeholder_panel.provenance import (
    RatificationError,
    assert_ratifiable,
    brief_hash,
    is_synthetic,
    synthetic_claim,
)
from startd8.stakeholder_panel.roster import (
    RosterError,
    assess_roster,
    load_roster,
    parse_roster,
    validate_roster,
)
from startd8.stakeholder_panel.adapters import (
    Adapter,
    AdapterError,
    AdaptResult,
    get_adapter,
)
from startd8.stakeholder_panel.budget import budget_preflight
from startd8.stakeholder_panel.grounding_guard import (
    check_grounding,
    unsupported_specifics,
)
from startd8.stakeholder_panel.ingest import (
    IngestGateError,
    IngestResult,
    ingest,
)
from startd8.stakeholder_panel.routing import route
from startd8.stakeholder_panel.vipp_bridge import Consultation, consult_panel

# M1 ships the live panel, so a validated roster is now consumable (R2-S5). ``assess`` reads this.
PANEL_CONSUMABLE = True

if TYPE_CHECKING:  # import only for type-checkers; runtime access is lazy (below)
    from startd8.stakeholder_panel.panel import (  # noqa: F401
        PanelClosedError,
        PanelError,
        StakeholderPanel,
        UnknownPersonaError,
    )
    from startd8.stakeholder_panel.persona import Persona  # noqa: F401

_LAZY_PANEL = {
    "StakeholderPanel",
    "PanelError",
    "PanelClosedError",
    "UnknownPersonaError",
}


def __getattr__(name: str):
    """Lazily surface the heavy query-time classes (PEP 562) without eager agent/LLM imports."""
    if name in _LAZY_PANEL:
        from startd8.stakeholder_panel import panel as _panel

        return getattr(_panel, name)
    if name == "Persona":
        from startd8.stakeholder_panel.persona import Persona

        return Persona
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "PROTOCOL_VERSION",
    "PANEL_CONSUMABLE",
    "PersonaBrief",
    "Roster",
    "Grounding",
    "PanelQuestion",
    "PanelAnswer",
    "RosterError",
    "assess_roster",
    "load_roster",
    "parse_roster",
    "validate_roster",
    "RatificationError",
    "assert_ratifiable",
    "brief_hash",
    "is_synthetic",
    "synthetic_claim",
    "route",
    "consult_panel",
    "Consultation",
    "check_grounding",
    "unsupported_specifics",
    "budget_preflight",
    "Adapter",
    "AdapterError",
    "AdaptResult",
    "get_adapter",
    "ingest",
    "IngestResult",
    "IngestGateError",
    # Coverage-signal + staging types retained after the Teian drafter was dropped (project-start M2,
    # NR-7): the $0 "which fields are unfilled" enumeration is kept as the FR-13 discovery trigger,
    # and the passive data/provenance types (``Recommendation``, provenance, proposal store) are reused
    # by requirements_panel / manifest_suggester. The point-value *drafting pass* (``recommend_inputs``)
    # and its apply path are removed — no LLM estimates specific field values.
    "Recommendation",
    "SUPPORTED_DOMAINS",
    "DomainSpec",
    "FieldSlot",
    "get_domain",
    "resolve_owner",
    "unfilled_fields",
    "ProposalStore",
    "latest_session",
    "gc_stale_proposals",
    "ESTIMATE_PROVENANCE",
    "is_estimate",
    "panel_origin",
    "assert_not_authored",
    # lazy (via __getattr__):
    "StakeholderPanel",
    "PanelError",
    "PanelClosedError",
    "UnknownPersonaError",
    "Persona",
]
