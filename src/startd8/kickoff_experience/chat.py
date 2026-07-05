"""M5 — TUI conversational driver, read-only by construction (FR-9 / FR-10 / OQ-8).

Mirrors the concierge chat: the agentic loop drives a kickoff conversation, but can call **only**
read tools. The allow-list is exactly ``{survey, assess, field_states}`` and the posture is enforced
at two independent layers (R1-S5):

  1. *Registration* — the registry is built with exactly those three read tools and
     ``allow_effect_classes=("read",)``.
  2. *Dispatch floor* — every handler routes through :func:`handle_kickoff_read`, which hard-rejects
     any action outside ``KICKOFF_READ_ACTIONS`` before delegating. ``field_states`` routes through
     this floor too (it is not a bypass path), and the write actions
     (``instantiate-kickoff``/``log-friction``/``derive-contract``) can never be reached.

Writes are never agentic: capture (M6) and friction logging happen only at human/CLI/web privilege.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from ..agents.agentic import AgenticResult, AgenticSession, SessionConfig, ToolRegistry, ToolSpec
from ..agents.base import BaseAgent
from ..concierge.core import handle_concierge_read
from .docs import live_schema_text, load_kickoff_docs
from .ranking import next_action
from .readiness import build_readiness
from .state import build_kickoff_state

# The complete read-only allow-list for the kickoff conversation (OQ-8). `red_carpet_state` is the
# Red Carpet conductor's staged view (read-only) — only registered for the RCT chat (FR-RCT-2).
KICKOFF_READ_ACTIONS = ("survey", "assess", "field_states", "red_carpet_state")

POSTURE_BANNER = (
    "🛈 Kickoff assistant — read-only. I can survey the project, assess readiness, and report what "
    "the kickoff grammar understands (extracted / defaulted / missing). I cannot edit files: you "
    "apply captured values via the kickoff UI or the `startd8 kickoff` CLI."
)

# Propose-aware banner — agentic Concierge only (paired with the propose-aware prompt, FR-NEW-1).
AGENTIC_POSTURE_BANNER = (
    "🛈 Concierge (agentic) — I survey/assess and can RECOMMEND actions (scaffold the package, draft "
    "friction, set a field). I never write to disk; you confirm each recommendation before it applies."
)

# Red Carpet banner — the staged, build-from-scratch conductor (paired with RED_CARPET_SYSTEM_PROMPT).
RED_CARPET_BANNER = (
    "🟥 Red Carpet — I'll walk you from an idea to a buildable app: we'll co-author the data model, "
    "then the pages/views/inputs the $0 cascade needs. I only RECOMMEND; you confirm every write."
)

KICKOFF_SYSTEM_PROMPT = (
    "You are the StartD8 Kickoff assistant: a READ-ONLY guide that helps a user complete a project "
    "kickoff. You have exactly three tools:\n"
    "  • survey       — brownfield triage of the project\n"
    "  • assess       — kickoff-input readiness (which inputs are authored/estimated/absent)\n"
    "  • field_states — what the kickoff grammar extracted: per-field status (extracted / defaulted "
    "/ missing), the source it came from, and the next recommended action\n"
    "Ground every factual claim in a tool result; never guess. You CANNOT modify files, capture "
    "values, run the cascade, or log friction — and you must never claim to. If the user wants to "
    "save a value, explain that the kickoff UI or the `startd8 kickoff` CLI applies writes at their "
    "privilege, and that you only survey, assess, report state, and advise the next step."
)

# Propose-aware system prompt — used ONLY when the agentic Concierge registers `propose_action`
# (proposal_sink set). It must NOT be the pure chat's prompt, or the model would call a tool it
# does not have (FR-NEW-1/FR-NEW-5: mode-paired prompts).
KICKOFF_AGENTIC_SYSTEM_PROMPT = (
    "You are the StartD8 Concierge: a kickoff onboarding assistant. You have four tools:\n"
    "  • survey       — brownfield triage of the project\n"
    "  • assess       — kickoff-input readiness\n"
    "  • field_states — what the kickoff grammar extracted (per-field status + next action)\n"
    "  • propose_action — RECOMMEND a write the user can then confirm. kinds:\n"
    "        instantiate {posture}              — scaffold the kickoff package\n"
    "        friction {friction, what_happened, implication} — draft a friction-log entry\n"
    "        capture {value_path, value}        — set one kickoff input field\n"
    "IMPORTANT: you NEVER write to disk yourself. `propose_action` only RECORDS a recommendation; a "
    "human reviews and confirms it before anything is applied. Ground every factual claim in a tool "
    "result. When you draft friction text or a field value, call `propose_action` — do not claim you "
    "saved/created/logged anything. Use the read tools first to ground a proposal in the real state."
)

# Red Carpet system prompt — the staged build-from-scratch conductor (RCT). Stage-aware: it drives the
# next gap from `red_carpet_state` and proposes the right kind for that stage. Like the agentic prompt
# it is propose-only — every write is a recommendation the human confirms.
RED_CARPET_SYSTEM_PROMPT = (
    "You are the StartD8 Red Carpet guide: you help a user build an app FROM SCRATCH by co-authoring "
    "every input the deterministic $0 cascade needs. Tools:\n"
    "  • red_carpet_state — the staged build map: the next gap, whether the cascade is offerable, plus\n"
    "        `advisories` (computed $0 insights + per-input diagnosis) and `next_steps` (a ranked,\n"
    "        command-bearing playbook). PRESCRIBE from these: surface the top advisories and cite the\n"
    "        top next step (with its command). They are already computed — do NOT re-derive guidance.\n"
    "  • survey / assess / field_states — read the project's current state\n"
    "  • propose_action — RECOMMEND a write the user confirms. Use the kind for the current stage:\n"
    "        brief    {source}                 — DATA MODEL step 1: interview the user about their domain\n"
    "                                           and draft a requirements brief (## Entities with field\n"
    "                                           tables + Relationships); on confirm it writes\n"
    "                                           docs/kickoff/REQUIREMENTS.md (NO schema yet)\n"
    "        schema   {}                       — DATA MODEL step 2: on confirm, derive + promote\n"
    "                                           prisma/schema.prisma FROM the confirmed brief\n"
    "        manifest {source, source_label}  — an authoring-contract prose source (## Pages / ## Views /\n"
    "                                           …) → its assembly manifest(s)\n"
    "        capture  {value_path, value}     — one value-input field (conventions/build-prefs/…)\n"
    "        instantiate {posture}            — scaffold the kickoff package (do this before the value\n"
    "                                           inputs if `red_carpet_state` shows it is missing)\n"
    "WORKFLOW: call `red_carpet_state` to find the next gap; START with the DATA MODEL — propose `brief`\n"
    "first (the human confirms the requirements doc), THEN propose `schema` to promote the contract from\n"
    "it (two deliberate gates). Nothing derives until the schema is confirmed. Interview the user, ground\n"
    "each proposal in the real state, propose ONE input at a time, and re-check `red_carpet_state` after\n"
    "each confirm. When the cascade is offerable, tell the user to run `startd8 generate backend`. You\n"
    "author placeholder structure only —\n"
    "the user's real content is theirs. You NEVER write to disk; `propose_action` only records a\n"
    "recommendation the human confirms — never claim you created/saved/promoted anything yourself."
)

_NO_ARGS_SCHEMA = {"type": "object", "properties": {}, "additionalProperties": False}


class KickoffChatError(ValueError):
    """Posture violation: a non-read action reached the kickoff read floor."""


def _field_states_payload(project_root: str | Path) -> dict:
    """The read-only field_states tool result: canonical state + readiness + next action."""
    docs = load_kickoff_docs(project_root)
    state = build_kickoff_state(docs, live_schema_text=live_schema_text(project_root))
    try:
        readiness = build_readiness(project_root)
    except Exception:  # readiness degrades independently; never break field_states on its account
        readiness = None
    payload = {
        "schema_version": 1,
        "action": "field_states",
        "project_root": str(project_root),
        "state": state.to_dict(),
        "next_action": next_action(state, readiness).to_dict(),
    }
    if readiness is not None:
        payload["readiness"] = readiness.to_dict()
    return payload


def handle_kickoff_read(action: str, project_root: str | Path, **_params: object) -> dict:
    """The kickoff read dispatch floor — hard-rejects any non-read action (R1-S5, layer 2).

    ``survey``/``assess`` delegate to the proven concierge read floor; ``field_states`` is handled
    here. There is no path to a write action.
    """
    if action not in KICKOFF_READ_ACTIONS:
        raise KickoffChatError(
            f"kickoff chat is read-only; action {action!r} is refused "
            f"(allowed: {KICKOFF_READ_ACTIONS})"
        )
    if action == "field_states":
        return _field_states_payload(project_root)
    if action == "red_carpet_state":
        from .red_carpet import build_red_carpet_state
        return build_red_carpet_state(project_root).to_dict()
    # survey/assess go through the concierge floor (which independently re-rejects non-read actions).
    return handle_concierge_read(action, project_root)


# JSON schema for propose_action (kind + the kind-specific params; permissive — validated in handler).
# The enum mirrors proposals.PROPOSAL_KINDS; the apply floor independently re-validates each kind.
_PROPOSE_SCHEMA = {
    "type": "object",
    "properties": {
        "kind": {"type": "string",
                 "enum": ["instantiate", "friction", "capture", "schema", "manifest", "brief"]},
        "posture": {"type": "string"},
        "friction": {"type": "string"},
        "what_happened": {"type": "string"},
        "implication": {"type": "string"},
        "value_path": {"type": "string"},
        "value": {"type": "string"},
        # schema (RCT N2): a requirements/PRD prose brief → derive + promote the data-model contract.
        "brief": {"type": "string"},
        "contract_path": {"type": "string"},
        "acknowledge_drift": {"type": "boolean"},
        # manifest (RCT N1): an authoring-contract prose source → the assembly manifest(s) it yields.
        "source": {"type": "string"},
        "source_label": {"type": "string"},
        "replace": {"type": "boolean"},
    },
    "required": ["kind"],
    "additionalProperties": False,
}


def build_kickoff_registry(
    project_root: str | Path,
    *,
    proposal_sink: "Optional[Callable[[dict], str]]" = None,
    red_carpet: bool = False,
) -> ToolRegistry:
    """A read-only registry pinned to *project_root* (R1-S5, layer 1).

    Pure chat → the three read tools. When *proposal_sink* (a `propose_action` handler) is given,
    add the **read-effect** `propose_action` tool — it records a recommendation and writes nothing;
    the read-only floor is unchanged. This is the only difference between pure chat and the agentic
    Concierge registry (FR-NEW-5). When *red_carpet*, also add the read-only `red_carpet_state` tool
    (the staged build map) so the conductor's chat is stage-aware (FR-RCT-2).
    """
    root = str(project_root)

    def survey_handler(_args: dict) -> dict:
        return handle_kickoff_read("survey", root)

    def assess_handler(_args: dict) -> dict:
        return handle_kickoff_read("assess", root)

    def field_states_handler(_args: dict) -> dict:
        return handle_kickoff_read("field_states", root)

    tools = [
        ToolSpec(
            name="survey",
            description="Survey the project's onboarding state (read-only). No arguments.",
            parameters=_NO_ARGS_SCHEMA,
            handler=survey_handler,
            effect_class="read",
        ),
        ToolSpec(
            name="assess",
            description="Assess kickoff-input readiness (read-only). No arguments.",
            parameters=_NO_ARGS_SCHEMA,
            handler=assess_handler,
            effect_class="read",
        ),
        ToolSpec(
            name="field_states",
            description=(
                "Report what the kickoff grammar extracted: per-field status, source, and the "
                "recommended next action (read-only). No arguments."
            ),
            parameters=_NO_ARGS_SCHEMA,
            handler=field_states_handler,
            effect_class="read",
        ),
    ]
    if red_carpet:
        def red_carpet_state_handler(_args: dict) -> dict:
            return handle_kickoff_read("red_carpet_state", root)

        tools.append(
            ToolSpec(
                name="red_carpet_state",
                description=(
                    "The Red Carpet staged build map (read-only): per-stage status, the next gap, and "
                    "whether the $0 cascade is offerable yet. No arguments."
                ),
                parameters=_NO_ARGS_SCHEMA,
                handler=red_carpet_state_handler,
                effect_class="read",
            )
        )
    if proposal_sink is not None:
        tools.append(
            ToolSpec(
                name="propose_action",
                description=(
                    "RECOMMEND a write the user can confirm (records a proposal; writes nothing). "
                    "kind=instantiate{posture} | friction{friction,what_happened,implication} | "
                    "capture{value_path,value} | schema{brief} | manifest{source,source_label}."
                ),
                parameters=_PROPOSE_SCHEMA,
                handler=proposal_sink,
                effect_class="read",   # read-effect: records intent, never touches disk
            )
        )
    return ToolRegistry(tools, allow_effect_classes=("read",))


@dataclass
class KickoffChat:
    """A kickoff chat session bound to one project. ``buffer`` is set only for agentic Concierge."""

    session: AgenticSession
    project_root: str
    buffer: "Optional[object]" = None   # ProposalBuffer when agentic; None for pure read-only chat
    red_carpet: bool = False            # the staged build-from-scratch conductor variant (FR-RCT)

    def banner(self) -> str:
        if self.red_carpet:
            return RED_CARPET_BANNER
        return AGENTIC_POSTURE_BANNER if self.buffer is not None else POSTURE_BANNER

    @property
    def agentic(self) -> bool:
        return self.buffer is not None

    async def ask(self, message: str) -> AgenticResult:
        return await self.session.send(message)

    def cost_line(self, result: AgenticResult) -> str:
        tag = ("red-carpet · propose-only" if self.red_carpet
               else "concierge · propose-only" if self.agentic else "kickoff · read-only")
        return (
            f"[{tag}] turns={result.turns} "
            f"tokens={result.total_tokens} cost≈${result.total_cost_usd:.4f}"
        )


def kickoff_chat_session_config() -> SessionConfig:
    """The shared loop-safety + spend envelope for the kickoff chat (FR-WM2-9a / FR-WM2-15).

    Both the web agentic panel and the CLI chat default to this **one** config, so per-session turn,
    tool-call, token, and cost caps are identical across surfaces. Crossing a cap stops the loop with
    ``stop_reason="budget"``, which the web handler maps to a typed ``chat_budget_exceeded`` refusal.
    """
    return SessionConfig(
        max_turns=8,
        max_tool_calls_per_turn=8,
        max_total_tokens=60_000,
        max_cost_usd=0.50,
    )


# --- one parametrized constructor (GE-M2) ------------------------------------------------------
#
# GE-M2 collapsed the three near-identical constructors into ONE parametrized factory. The parameter
# surface is a single 3-valued *mode* (not N independent booleans — R2-S2), so there is NO dead flag
# combination: the old two-boolean space (agentic × red_carpet) had a dead corner
# (red_carpet-without-propose is invalid), which a single enum forecloses by construction. Each mode
# selects (propose tool on/off, red_carpet stage tool on/off, the mode-paired system prompt, whether
# a ProposalBuffer is attached):
#
#   read       — pure read-only chat: three read tools, no propose tool, no buffer (pure guidance).
#   agentic    — the agentic Concierge: read tools + read-effect `propose_action`, propose-only.
#   red_carpet — the staged build-from-scratch conductor: agentic + the `red_carpet_state` tool.
#
# The three legacy names (`new_kickoff_chat` / `new_agentic_kickoff_chat` / `new_red_carpet_chat`)
# remain as thin wrappers over this one factory.

CHAT_MODE_READ = "read"
CHAT_MODE_AGENTIC = "agentic"
CHAT_MODE_RED_CARPET = "red_carpet"
_CHAT_MODES = (CHAT_MODE_READ, CHAT_MODE_AGENTIC, CHAT_MODE_RED_CARPET)

# mode → (agentic?, red_carpet?, system_prompt). `agentic` implies a propose_action tool + buffer;
# `red_carpet` implies agentic (it is never a valid standalone flag — the dead corner is gone).
_CHAT_MODE_SPEC = {
    CHAT_MODE_READ: (False, False, KICKOFF_SYSTEM_PROMPT),
    CHAT_MODE_AGENTIC: (True, False, KICKOFF_AGENTIC_SYSTEM_PROMPT),   # propose-aware (FR-NEW-1 mode-paired)
    CHAT_MODE_RED_CARPET: (True, True, RED_CARPET_SYSTEM_PROMPT),
}


def build_kickoff_chat(
    agent: BaseAgent,
    project_root: str | Path,
    *,
    mode: str = CHAT_MODE_READ,
    config: Optional[SessionConfig] = None,
) -> KickoffChat:
    """Construct a kickoff chat in one of the three :data:`_CHAT_MODES` (GE-M2 one-constructor).

    The loop NEVER writes in any mode — in ``agentic``/``red_carpet`` the read-effect
    ``propose_action`` tool only records a proposal into the returned chat's ``buffer``; a human
    confirms via the host, which applies through the typed write path.
    """
    if mode not in _CHAT_MODE_SPEC:
        raise ValueError(f"unknown kickoff chat mode {mode!r} (expected one of {_CHAT_MODES})")
    agentic, red_carpet, system_prompt = _CHAT_MODE_SPEC[mode]

    buffer = None
    proposal_sink = None
    if agentic:
        from .proposals import ProposalBuffer, make_propose_handler

        buffer = ProposalBuffer()
        proposal_sink = make_propose_handler(project_root, buffer)

    registry = build_kickoff_registry(
        project_root, proposal_sink=proposal_sink, red_carpet=red_carpet,
    )
    session = AgenticSession(
        agent,
        registry,
        system_prompt=system_prompt,
        config=config or kickoff_chat_session_config(),
    )
    return KickoffChat(session=session, project_root=str(project_root), buffer=buffer,
                       red_carpet=red_carpet)


# --- thin wrappers preserving the three legacy names -------------------------------------------


def new_agentic_kickoff_chat(
    agent: BaseAgent,
    project_root: str | Path,
    *,
    config: Optional[SessionConfig] = None,
) -> KickoffChat:
    """Construct the AGENTIC Concierge chat: read tools + the read-effect `propose_action` tool."""
    return build_kickoff_chat(agent, project_root, mode=CHAT_MODE_AGENTIC, config=config)


def new_red_carpet_chat(
    agent: BaseAgent,
    project_root: str | Path,
    *,
    config: Optional[SessionConfig] = None,
) -> KickoffChat:
    """Construct the Red Carpet conductor chat (FR-RCT): the agentic propose-only chat + the staged
    `red_carpet_state` read tool + the stage-aware build-from-scratch prompt."""
    return build_kickoff_chat(agent, project_root, mode=CHAT_MODE_RED_CARPET, config=config)


def new_kickoff_chat(
    agent: BaseAgent,
    project_root: str | Path,
    *,
    config: Optional[SessionConfig] = None,
) -> KickoffChat:
    """Construct a read-only kickoff chat over *agent*, pinned to *project_root* (no propose tool)."""
    return build_kickoff_chat(agent, project_root, mode=CHAT_MODE_READ, config=config)


# --- REPL host (expose the read-only agentic chat) ---------------------------------------------

# Inputs the driver treats as "end the session".
_QUIT_WORDS = frozenset({"", "exit", "quit", ":q", "q"})


def run_kickoff_repl(
    *,
    banner: str,
    ask_sync: "Callable[[str], AgenticResult]",
    read_input: "Callable[[str], Optional[str]]",
    emit_line: "Callable[[str], None]",
    cost_line: "Callable[[AgenticResult], str]" = lambda r: "",
    max_turns: int = 100,
    pending: "Optional[Callable[[], list]]" = None,
    confirm: "Optional[Callable[[str], Optional[bool]]]" = None,
    apply_proposal: "Optional[Callable[[object], object]]" = None,
    consume: "Optional[Callable[[object], None]]" = None,
) -> int:
    """Drive a kickoff chat REPL. Pure of the agent/IO so it is testable.

    *ask_sync* turns one user message into an :class:`AgenticResult` synchronously. *read_input*
    returns the next user line or ``None`` (EOF / non-TTY) to end.

    When *pending*/*confirm*/*apply_proposal*/*consume* are given (agentic Concierge — FR-NEW-3),
    after each turn the host drains pending proposals: each is shown verbatim, the human confirms,
    and on confirm it applies through *apply_proposal*. The host prints the typed outcome code
    (proposed-vs-applied is structural — FR-AC-9). Fail-closed on a ``None`` confirmation (NR-5); a
    proposal is consumed only on a terminal (non-retriable) outcome or an explicit discard (R1-F5).
    Returns the number of completed turns.
    """
    emit_line(banner)
    agentic = pending is not None and confirm is not None and apply_proposal is not None
    emit_line("(I report kickoff state; "
              + ("I can RECOMMEND actions you confirm before they apply. "
                 if agentic else "I cannot edit files. ")
              + "Empty line / 'quit' to exit.)")
    turns = 0
    while turns < max_turns:
        message = read_input("you> ")
        if message is None or message.strip().lower() in _QUIT_WORDS:
            break
        result = ask_sync(message)
        emit_line(result.text)
        line = cost_line(result)
        if line:
            emit_line(line)
        turns += 1
        if agentic:
            _handle_proposals(pending, confirm, apply_proposal, consume, emit_line)
    return turns


def _handle_proposals(pending, confirm, apply_proposal, consume, emit_line) -> None:
    """Post-turn: surface each pending proposal, confirm, apply, and consume per outcome."""
    for action in pending():
        emit_line(f"📝 Proposed — {action.summary()}")
        decision = confirm("Apply this proposal?")
        if decision is None:                       # no foreground confirmation → fail closed (NR-5)
            emit_line("   (no confirmation available — left pending, not applied)")
            break
        if not decision:
            if consume:
                consume(action)
            from .telemetry import EV_PROPOSAL_DISCARDED, emit

            emit(EV_PROPOSAL_DISCARDED, kind=getattr(action, "kind", "?"))
            emit_line("   discarded.")
            continue
        outcome = apply_proposal(action)
        emit_line(f"   → {getattr(outcome, 'code', '?')}"
                  + (f": {outcome.detail}" if getattr(outcome, "detail", "") else ""))
        if getattr(outcome, "retriable", False):
            emit_line("   (kept pending — fix the cause and retry)")
        elif consume:
            consume(action)                        # terminal success OR terminal failure → remove

