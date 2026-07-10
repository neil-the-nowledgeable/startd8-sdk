"""Read model over the kickoff-panel facilitation transcript (FR-UX-3).

The orchestrator (:mod:`startd8.stakeholder_panel.facilitation`) persists a plain ``dict``
to ``.startd8/kickoff-panel/<session_id>.json`` — see ``KickoffFacilitator.run``. This module
gives the *viewer* a typed, **graceful-optional** read model over that on-disk shape so the
render surfaces never crash on a partial / older / in-progress transcript:

* Every field defaults to an empty/None value — nothing is assumed present (FR-UX-3). Older
  fixtures lack ``prep`` / ``adversaries`` / ``status`` / ``halt`` / ``budget_usd`` and the
  synthesis ``*_tension_ids`` entirely; a mid-round write has fewer entries than the roster.
* ``extra="allow"`` so a forward-compatible orchestrator that adds fields never breaks load.
* The model is **read-only** (Mottainai, FR-UX-2) — this package never writes a transcript.

The structured synthesis arrays (risk register / tensions / recommendations / open questions)
do **not** exist as JSON today — they live as Markdown inside :attr:`PanelSynthesis.text`
(FR-UX-16 is the primary path; FR-UX-15 lights up if the orchestrator later emits structure).
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

# ── model-family derivation (FR-UX-8 / OQ-UX-5: from the provider prefix) ──
_FAMILY_BY_PROVIDER = {
    "anthropic": "Claude",
    "claude": "Claude",
    "openai": "GPT",
    "gpt": "GPT",
    "gemini": "Gemini",
    "google": "Gemini",
    "mistral": "Mistral",
    "ollama": "Ollama",
    "deepseek": "DeepSeek",
}


def model_family(model_spec: str) -> str:
    """Map a ``provider:model`` spec to a flagship family badge (FR-UX-8).

    Derived from the ``provider:`` prefix — the simplest source that covers the three
    flagship de-correlation families (Claude / GPT / Gemini). Unknown providers degrade to
    ``"Other"`` rather than guessing.
    """
    if not model_spec:
        return "Other"
    provider = model_spec.split(":", 1)[0].strip().lower()
    return _FAMILY_BY_PROVIDER.get(provider, "Other")


class PanelEntry(BaseModel):
    """One persona's answer within a round (``facilitation.py:_entry``)."""

    model_config = ConfigDict(extra="allow")

    role_id: str = ""
    display_name: str = ""
    model: str = ""
    prompt: str = ""
    text: str = ""
    grounding: str = ""
    flags: list[str] = Field(default_factory=list)
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    cost_usd: Optional[float] = None
    created_at: Optional[str] = None

    @property
    def family(self) -> str:
        return model_family(self.model)


class PanelRound(BaseModel):
    """One facilitation round (``facilitation.py:_run_round``)."""

    model_config = ConfigDict(extra="allow")

    round_id: str = ""
    title: str = ""
    kind: str = ""
    entries: list[PanelEntry] = Field(default_factory=list)
    cost_usd: Optional[float] = None


class PanelPrep(BaseModel):
    """The R0 prep block — three Markdown strings (``facilitation.py`` ``prep``)."""

    model_config = ConfigDict(extra="allow")

    grounded_context: str = ""
    key_assumptions: str = ""
    outside_view: str = ""

    def is_empty(self) -> bool:
        return not (self.grounded_context or self.key_assumptions or self.outside_view)


class PanelSynthesis(BaseModel):
    """The R5 synthesis — prose-primary today; structured arrays are latent (FR-UX-15/16)."""

    model_config = ConfigDict(extra="allow")

    model: str = ""
    text: str = ""
    raw_tension_ids: list[str] = Field(default_factory=list)
    open_tension_ids: list[str] = Field(default_factory=list)
    smoothed_tension_ids: list[str] = Field(default_factory=list)


class KickoffTranscript(BaseModel):
    """Typed, graceful-optional read model over the on-disk kickoff-panel transcript."""

    model_config = ConfigDict(extra="allow")

    session_id: str = ""
    created_at: Optional[str] = None
    project: str = ""
    objective: str = ""
    strategy: str = ""
    posture: str = "scrutiny"  # FR-8/H-11 — maps the session-JSON key (#174); default covers old transcripts
    tier: str = "premium"  # FR-10 — the model tier (premium|cheap) that produced the transcript
    prep: Optional[PanelPrep] = None
    model_assignment: dict[str, str] = Field(default_factory=dict)
    adversaries: list[str] = Field(default_factory=list)
    facilitator_model: str = ""
    status: Optional[str] = None
    halt: Optional[dict[str, Any]] = None
    budget_usd: Optional[float] = None
    rounds: list[PanelRound] = Field(default_factory=list)
    synthesis: Optional[PanelSynthesis] = None
    cost_total_usd: Optional[float] = None

    # ── derived views used by the render surfaces ──
    @property
    def is_halted(self) -> bool:
        """Halted-after-R0 state (FR-UX-14) — a first-class state, not an error."""
        return self.status == "halted" or bool(self.halt)

    @property
    def roster_size(self) -> int:
        """Roster size from the model assignment (denominator for per-round progress)."""
        return len(self.model_assignment)

    @property
    def is_done(self) -> bool:
        """Terminal state for live-follow (FR-UX-17) — the run won't write again.

        H-6: `cancelled` + `error` are terminal too (a fire-and-poll cancel/crash must not spin forever).
        """
        return self.status in ("completed", "done", "cancelled", "error") or self.is_halted

    def active_round_id(self) -> Optional[str]:
        """The round currently being filled (FR-UX-18), or ``None`` when idle/complete.

        A round is "filling" when it has fewer entries than the roster; otherwise, while the
        run is still ``in_progress`` and no round is short, the *next* round is pending. Returns
        ``None`` once the run is done. Honest about the current orchestrator (which persists
        whole rounds): between landings this reports the pending round id, never a false
        partial bar.
        """
        if self.is_done:
            return None
        for rnd in self.rounds:
            if self.roster_size and len(rnd.entries) < self.roster_size:
                return rnd.round_id
        if self.status == "in_progress":
            return f"R{len(self.rounds) + 1}"
        return None

    def is_adversary(self, role_id: str) -> bool:
        return role_id in self.adversaries

    def family_distribution(self) -> dict[str, int]:
        """Count of roster members per model family (the de-correlation spread, FR-UX-9)."""
        dist: dict[str, int] = {}
        for spec in self.model_assignment.values():
            fam = model_family(spec)
            dist[fam] = dist.get(fam, 0) + 1
        return dist

    def all_entries(self) -> list[tuple[PanelRound, PanelEntry]]:
        """Flat (round, entry) pairs — the shared record set both axes group (FR-UX-5)."""
        return [(rnd, e) for rnd in self.rounds for e in rnd.entries]
