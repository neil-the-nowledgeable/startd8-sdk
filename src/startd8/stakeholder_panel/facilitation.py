# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""Facilitated multi-round kickoff panel — the "lens" over the panel "mirror".

Promoted (GE-M3a / FR-GE-11a) from ``scripts/run_kickoff_panel.py`` into an importable,
testable, confined module. The orchestration reuses :class:`StakeholderPanel` as the
per-round *mirror* engine and adds a **thin** multi-round / cross-pollination / synthesis
layer above it — **no new panel engine** (OQ-GE-8 resolution).

What is reused vs new:
  * Reused — :meth:`StakeholderPanel.ask` (the primitive :meth:`StakeholderPanel.ask_all`
    is itself built from: a single ``preflight_budget`` gate + a concurrent ``ask`` fan-out).
    Each facilitation round runs exactly that shape via :meth:`KickoffFacilitator._run_round`.
    ``ask_all`` is the *uniform-prompt* convenience case; facilitation needs **per-persona**
    prompts (R1 adversary framing, R3 self-excluded digest), so it drives the same
    ``preflight_budget`` + ``ask`` primitives directly rather than the uniform wrapper.
  * New (thin orchestration only) — the R0 prep passes (grounding / assumptions / outside
    view) and the R5 synthesis run on neutral *facilitator* agents that are not personas,
    plus the round sequencing and transcript assembly.

Transcript persistence (FR-GE-13): every byte rides ``concierge/safe_write.py`` — the
confined, atomic, traversal-safe floor — via **per-round atomic-replace** so the
observability-UX live-follow contract (FR-UX-17: poll-and-diff as rounds land) holds. The
path (``.startd8/kickoff-panel/<session_id>.json``) and §6 schema are preserved byte-for-byte
from the script so the (future) viewer contract stays intact.

Hardening (H1 artifact-grounding fidelity, H2 assumptions-as-gate halt, H3 cost tracking,
FR-GE-12 anti-smoothing) is GE-M3b and applies to THIS module — see the ``# GE-M3b hook``
markers for where those hooks land.
"""
from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple
from uuid import uuid4

from startd8.logging_config import get_logger
from startd8.stakeholder_panel.models import PersonaBrief, Roster

logger = get_logger(__name__)

# --- de-correlation: independent model families (spec §4) ---------------------
FAMILIES = {
    "claude": "anthropic:claude-opus-4-8",
    "gpt": "openai:gpt-5.5",
    "gemini": "gemini:gemini-3.1-pro-preview",
}
FAMILY_ORDER = ["claude", "gpt", "gemini"]
FACILITATOR_SPEC = FAMILIES["claude"]  # facilitator / synthesizer / grounding / assumptions
OUTSIDE_VIEW_SPEC = FAMILIES["gpt"]    # de-correlate the base-rate estimate

ADVERSARY_IDS = {"adversary-exploit", "adversary-discredit"}

# --- default Blue Planet Adventures context (overridable via config) ----------
DEFAULT_DESC = (
    "Blue Planet Adventures is an online store selling outdoor gear (15 SKUs across "
    "jackets, boots, shirts) to adventure-minded consumers in 6 currencies, on a "
    "microservice platform (catalog, cart, checkout, payment, currency, shipping, "
    "email, recommendations, ads)."
)
DEFAULT_OBJECTIVE = (
    "Grow revenue from the existing catalog by lifting average order value AND "
    "conversion rate, WITHOUT adding checkout friction and WITHOUT breaking "
    "multi-currency correctness or PCI compliance."
)
DEFAULT_STRATEGY = (
    "(1) grow basket size via complementary-gear bundling and recommendations; "
    "(2) improve product discovery and trust so browsers convert; "
    "(3) keep the funnel fast and reliable at seasonal peak."
)
DEFAULT_PROJECT_NAME = "the project described above"
_NEUTRAL_SYS = (
    "You are a neutral kickoff analyst. No domain stake, no cheerleading. Be "
    "candid and specific. Do not invent facts, numbers, or dates."
)
_SYNTH_SYS = (
    "You are a neutral kickoff facilitator synthesizing a stakeholder panel. You "
    "have NO domain stake; your job is process quality. CRITICAL: preserve "
    "unresolved disagreement — never smooth real tension into a false consensus. "
    "Everything below is SYNTHETIC, unratified input for a human to judge, not fact."
)

# Transcript contract (FR-UX-1): the exact path the observability-UX viewer polls.
TRANSCRIPT_SUBDIR = ".startd8/kickoff-panel"


# ============================ prompt builders =================================
def _context_block(desc: str, objective: str, strategy: str, grounded: str = "") -> str:
    ctx = (
        f"CONTEXT: {desc}\nWe are in a planning kickoff for the next phase of the "
        f"business.\nOBJECTIVE (this cycle): {objective}\nSTRATEGY (proposed): {strategy}"
    )
    if grounded:
        ctx += f"\n\nCURRENT STATE (grounded in the real system):\n{grounded}"
    return ctx


def _r1_prompt(ctx: str, project_name: str) -> str:
    return (
        f"{ctx}\n\nYOUR TASK, reasoning from this objective and strategy into YOUR "
        "specific role and domain: (1) the 2-3 highest-leverage TACTICS you would "
        "personally drive; (2) the biggest RISK or tension your domain sees that the "
        "rest of the team is probably underestimating; (3) one thing the team is "
        f"likely NOT thinking about. Be concrete and specific to {project_name}, not generic."
    )


def _r1_adversary_prompt(ctx: str, project_name: str) -> str:
    return (
        f"{ctx}\n\nYou are an ADVERSARY, not a team member. Reasoning about how you "
        "would EXPLOIT or BEAT this initiative: (1) the 2-3 concrete ways you would "
        "attack, abuse, or undercut it; (2) the single weakness the team is most "
        "likely to leave open; (3) what they will forget to defend. Be concrete and "
        f"specific to {project_name}."
    )


def _premortem_prompt(is_adv: bool, project_name: str) -> str:
    if is_adv:
        return (
            "PRE-MORTEM (adversary). It is one year later and YOU WON — you "
            "successfully exploited or out-competed this initiative. Tell the short "
            "story of exactly how you did it and the opening they left you. Be concrete."
        )
    return (
        "PRE-MORTEM. It is one year from now and this initiative failed badly. From "
        "YOUR role's vantage, tell the short story of what went wrong: the specific "
        "failure in or adjacent to your domain, and the early warning sign we ignored. "
        f"Be concrete and specific to {project_name}."
    )


def _r3_prompt(digest: str) -> str:
    return (
        "Here is what the other participants said in their first-round analysis:\n\n"
        f"{digest}\n\nReacting from YOUR role: (1) where do you AGREE; (2) where do you "
        "PUSH BACK or see a conflict with your domain; (3) what does someone else's "
        "point imply for YOUR domain that you did NOT already say? Surface tension — "
        "do not just agree."
    )


def _r4_prompt() -> str:
    return (
        "Having heard the others and run a pre-mortem, give your FINAL, INDEPENDENT "
        "judgment from your role: (1) the single highest-priority thing the team must "
        "get right; (2) your biggest remaining worry; (3) one concrete recommendation. "
        "Say what YOU actually conclude now, even if it dissents from the group."
    )


def _digest(entries: List[dict], exclude_role: str, cap_chars: int = 420) -> str:
    lines = []
    for e in entries:
        if e["role_id"] == exclude_role:
            continue
        txt = " ".join(e["text"].split())
        if len(txt) > cap_chars:
            txt = txt[:cap_chars] + "…"
        lines.append(f"- {e['display_name']}: {txt}")
    return "\n".join(lines)


def _synth_prompt(transcript_text: str, family_map: Dict[str, str], prep: dict) -> str:
    fam = "; ".join(f"{r}={f}" for r, f in family_map.items())
    prep_txt = ""
    if prep.get("key_assumptions"):
        prep_txt += f"\n\nKEY ASSUMPTIONS (prep):\n{prep['key_assumptions']}"
    if prep.get("outside_view"):
        prep_txt += f"\n\nOUTSIDE VIEW / base rate (prep):\n{prep['outside_view']}"
    return (
        f"Model-family assignment (for corroboration strength): {fam}{prep_txt}\n\n"
        f"Full transcript of the facilitated panel:\n\n{transcript_text}\n\n"
        "Produce a structured synthesis:\n"
        "## Risk Register\nEach material risk; which roles flagged it; corroboration = "
        "CROSS-FAMILY if flagged by roles on different model families, else "
        "single-family/single-model.\n"
        "## Adversary Findings\nAbuse/competitive attacks the adversary personas surfaced.\n"
        "## Tensions\nEach real conflict between roles; RESOLVED (with the trade-off) or OPEN.\n"
        "## Assumptions At Risk\nWhich prep assumptions the panel's analysis threatens or confirms.\n"
        "## Recommendations\nPrioritized, derived tactics.\n"
        "## Open Questions for the Human\nWhere the panel lacked ground truth or "
        "proprietary knowledge and needs the human's judgment.\n"
        "Be concise and structured. Do not invent specific numbers."
    )


# ============================ adversary briefs ================================
def _adversary_briefs() -> List[PersonaBrief]:
    # Domain-NEUTRAL adversaries: the injected context (objective/strategy/grounding)
    # makes their attacks domain-appropriate, so they work for any kickoff.
    return [
        PersonaBrief(
            role_id="adversary-exploit",
            display_name="Exploiter / Bad Actor (ADVERSARY)",
            goals=["Exploit this initiative's weakest technical or process seam for gain, disruption, or harm."],
            known_positions=[
                "seams: the exploitable weakness is where two systems or steps each assume the other is correct and nobody validates the join",
                "new-surface: every new capability, integration, or automation is a new attack/abuse surface",
            ],
            constraints=["You are an attacker, not a team member — you probe for weakness, you do not help."],
            out_of_scope=[],
            answers_for=["exploit", "abuse", "attack-surface", "integrity"],
        ),
        PersonaBrief(
            role_id="adversary-discredit",
            display_name="Rival / Discreditor (ADVERSARY)",
            goals=["Undermine, discredit, dispute, or out-compete this initiative and take its standing, users, or trust."],
            known_positions=[
                "trust: any error, inconsistency, or unfairness they ship becomes your ammunition",
                "timing: their slowness, complexity, or blind spots are your opening",
            ],
            constraints=["You are an adversary, not a team member — you reason about how to beat or delegitimize them."],
            out_of_scope=[],
            answers_for=["competition", "dispute", "legitimacy", "trust-attack"],
        ),
    ]


# ============================ helpers ========================================
def assign_models(briefs: List[PersonaBrief]) -> Tuple[Dict[str, str], Dict[str, str]]:
    """Round-robin the personas across independent model families (spec §4 de-correlation)."""
    specs, fams = {}, {}
    for i, b in enumerate(briefs):
        fam = FAMILY_ORDER[i % len(FAMILY_ORDER)]
        specs[b.role_id] = FAMILIES[fam]
        fams[b.role_id] = fam
    return specs, fams


def _gather_artifact(project) -> str:
    # GE-M3b hook (H1): today reads static artifacts; hardening reads the live `survey`.
    root = Path(project).expanduser()
    picks = ["prisma/schema.prisma", ".contextcore.yaml", "CLAUDE.md", "README.md"]
    parts = []
    for rel in picks:
        p = root / rel
        if p.is_file():
            txt = p.read_text(errors="ignore")[:4000]
            parts.append(f"### {rel}\n{txt}")
    return ("\n\n".join(parts))[:12000]


def _entry(answer, brief: PersonaBrief, model_spec: str, prompt: str) -> dict:
    """Build one transcript entry — the §6 per-entry schema (preserved byte-for-byte)."""
    return {
        "role_id": answer.role_id, "display_name": brief.display_name, "model": model_spec,
        "prompt": prompt, "text": answer.text,
        "grounding": getattr(answer.grounding, "value", str(answer.grounding)),
        "flags": list(answer.flags), "input_tokens": int(answer.input_tokens),
        "output_tokens": int(answer.output_tokens), "cost_usd": float(answer.cost_usd),
        "created_at": answer.created_at,
    }


def build_briefs(cfg: "FacilitationConfig", roster: Roster) -> List[PersonaBrief]:
    """The participant list: roster (capped) + optional adversaries. Shared by run + CLI plan."""
    briefs_all = list(roster.personas)
    if cfg.cap:
        briefs_all = briefs_all[: cfg.cap]
    if cfg.adversary:
        briefs_all = briefs_all + _adversary_briefs()
    return briefs_all


def projected_calls(cfg: "FacilitationConfig", n_personas: int) -> int:
    """Projected model-call count for the dry-run plan (prep + personas×rounds + synthesis)."""
    prep_calls = int(cfg.ground) + int(cfg.assumptions) + int(cfg.outside_view)
    persona_rounds = 4 if cfg.final_judgment else 3
    return prep_calls + n_personas * persona_rounds + 1


# ============================ configuration ===================================
PersonaAgentFactory = Callable[[PersonaBrief], object]
FacilitatorAgentFactory = Callable[[str, str, str], object]  # (spec, name, system_prompt) -> agent
PrepHook = Callable[[str, str, str], None]                    # (kind, spec, text)
RoundHook = Callable[[dict], None]                            # (round_dict)
SynthHook = Callable[[str, str], None]                        # (spec, text)


@dataclass
class FacilitationConfig:
    """Immutable inputs for one facilitated run (mirrors the script's argparse surface)."""

    project: Path
    objective: str = DEFAULT_OBJECTIVE
    strategy: str = DEFAULT_STRATEGY
    desc: str = DEFAULT_DESC
    project_name: str = ""  # short domain noun threaded into prompts (empty -> generic)
    cap: int = 0
    ground: bool = True
    assumptions: bool = True
    outside_view: bool = True
    adversary: bool = True
    final_judgment: bool = True

    @property
    def resolved_project_name(self) -> str:
        return self.project_name or DEFAULT_PROJECT_NAME


# ============================ orchestrator ====================================
class KickoffFacilitator:
    """Thin multi-round orchestration over :class:`StakeholderPanel` (the mirror engine).

    Inject ``persona_agent_factory`` / ``facilitator_agent_factory`` to run fully offline
    ($0, deterministic) in tests; the production defaults resolve real agents via
    ``resolve_agent_spec``.
    """

    def __init__(
        self,
        config: FacilitationConfig,
        *,
        roster: Roster,
        persona_agent_factory: Optional[PersonaAgentFactory] = None,
        facilitator_agent_factory: Optional[FacilitatorAgentFactory] = None,
        model_assigner: Callable[[List[PersonaBrief]], Tuple[Dict[str, str], Dict[str, str]]] = assign_models,
        budget_preflight: Optional[Callable[[int], None]] = None,
        hydrate: Optional[Callable[[], object]] = None,
        on_prep: Optional[PrepHook] = None,
        on_round: Optional[RoundHook] = None,
        on_synthesis: Optional[SynthHook] = None,
    ) -> None:
        self.config = config
        self._roster = roster
        self._persona_agent_factory = persona_agent_factory
        self._facilitator_agent_factory = facilitator_agent_factory
        self._model_assigner = model_assigner
        self._budget_preflight = budget_preflight
        self._hydrate = hydrate
        self._on_prep = on_prep
        self._on_round = on_round
        self._on_synthesis = on_synthesis
        self._first_write = True

    # -- agent construction ---------------------------------------------------
    def _build_panel(self, briefs_all: List[PersonaBrief], specs: Dict[str, str]):
        from startd8.stakeholder_panel.panel import StakeholderPanel

        roster = Roster(personas=briefs_all)
        if self._persona_agent_factory is not None:
            factory = self._persona_agent_factory
        else:
            from startd8.stakeholder_panel.persona import compile_system_prompt
            from startd8.utils.agent_resolution import resolve_agent_spec

            def factory(brief: PersonaBrief):
                return resolve_agent_spec(
                    specs[brief.role_id],
                    name=f"persona:{brief.role_id}",
                    system_prompt=compile_system_prompt(brief),
                )

        # persist=False: the facilitation transcript (below) is the canonical artifact; we do
        # not also spin up the panel's per-answer TranscriptStore (a different store/schema).
        return StakeholderPanel(
            roster,
            agent_factory=factory,
            persist=False,
            budget_preflight=self._budget_preflight,
        )

    def _facilitator_agent(self, spec: str, name: str, system_prompt: str):
        if self._facilitator_agent_factory is not None:
            return self._facilitator_agent_factory(spec, name, system_prompt)
        from startd8.utils.agent_resolution import resolve_agent_spec

        return resolve_agent_spec(spec, name=name, system_prompt=system_prompt)

    @staticmethod
    def _agent_text(result) -> str:
        return result.text if hasattr(result, "text") else str(result)

    # -- per-round mirror (reuses the panel's ask primitive) ------------------
    async def _run_round(
        self,
        panel,
        briefs_all: List[PersonaBrief],
        round_id: str,
        title: str,
        kind: str,
        prompts: Dict[str, str],
        specs: Dict[str, str],
        briefs: Dict[str, PersonaBrief],
    ) -> dict:
        # Same shape as StakeholderPanel.ask_all: one budget gate, then a concurrent
        # ask() fan-out — but with per-persona prompts the uniform ask_all cannot carry.
        panel.preflight_budget(len(briefs_all))

        async def _one(b: PersonaBrief) -> dict:
            q = prompts[b.role_id]
            ans = await panel.ask(b.role_id, q)
            return _entry(ans, briefs[b.role_id], specs[b.role_id], q)

        entries = await asyncio.gather(*[_one(b) for b in briefs_all])
        return {"round_id": round_id, "title": title, "kind": kind, "entries": list(entries)}

    # -- safe-write persistence (FR-GE-13, per-round atomic-replace) -----------
    def _persist(self, session: dict) -> None:
        """Route the transcript through the confined safe-write floor via per-round
        atomic-replace, preserving the FR-UX-1 path + §6 schema for live-follow."""
        from startd8.concierge.safe_write import (
            ACTION_NEW,
            ACTION_OVERWRITE,
            PlannedWrite,
            SafeWriteError,
            apply_write_plan,
        )

        rel = f"{TRANSCRIPT_SUBDIR}/{session['session_id']}.json"
        content = json.dumps(session, indent=2)
        # First write creates the confined subtree; later rounds atomically replace it.
        action = ACTION_NEW if self._first_write else ACTION_OVERWRITE
        result = apply_write_plan(
            self.config.project, [PlannedWrite(path=rel, action=action, content=content)], force=True
        )
        if action == ACTION_NEW and result.skipped:  # session file already present — overwrite it
            result = apply_write_plan(
                self.config.project,
                [PlannedWrite(path=rel, action=ACTION_OVERWRITE, content=content)],
                force=True,
            )
        if not result.ok:
            raise SafeWriteError(
                f"kickoff transcript write blocked: {result.blocked or result.errors}"
            )
        self._first_write = False

    def transcript_path(self, session_id: str) -> Path:
        return Path(self.config.project).expanduser() / TRANSCRIPT_SUBDIR / f"{session_id}.json"

    # -- the run --------------------------------------------------------------
    async def run(self) -> dict:
        cfg = self.config
        # Only hydrate secrets when using real (production) agents — injected factories are $0.
        if self._persona_agent_factory is None:
            hydrate_fn = self._hydrate
            if hydrate_fn is None:
                from startd8.secrets import hydrate as hydrate_fn
            hydrate_fn()

        pname = cfg.resolved_project_name
        briefs_all = build_briefs(cfg, self._roster)
        specs, fams = self._model_assigner(briefs_all)
        briefs = {b.role_id: b for b in briefs_all}
        adv_ids = [b.role_id for b in briefs_all if b.role_id in ADVERSARY_IDS]

        def _adv(rid: str) -> bool:
            return rid in ADVERSARY_IDS

        panel = self._build_panel(briefs_all, specs)
        try:
            # ---- R0 prep (grounding + assumptions + outside view) ----------
            prep = {"grounded_context": "", "key_assumptions": "", "outside_view": ""}
            grounded = ""
            if cfg.ground:
                # GE-M3b hook (H1): swap _gather_artifact for the live `survey` artifact.
                artifact = _gather_artifact(cfg.project)
                if artifact:
                    g = self._facilitator_agent(FACILITATOR_SPEC, "facilitator", _NEUTRAL_SYS)
                    r = await g.agenerate(
                        f"Here is the ACTUAL project artifact (excerpts):\n\n{artifact}\n\n"
                        f"OBJECTIVE: {cfg.objective}\nSTRATEGY: {cfg.strategy}\n\n"
                        "Produce a concise CURRENT-STATE summary of what this system actually is and does "
                        "today (real entities/services/capabilities). Explicitly flag anything the "
                        "objective/strategy ASSUMES that the artifact does NOT support or contradicts."
                    )
                    grounded = prep["grounded_context"] = self._agent_text(r)
                    self._emit_prep("grounded_context", FACILITATOR_SPEC, grounded)
            ctx = _context_block(cfg.desc, cfg.objective, cfg.strategy, grounded)
            if cfg.assumptions:
                a = self._facilitator_agent(FACILITATOR_SPEC, "assumptions", _NEUTRAL_SYS)
                r = await a.agenerate(
                    f"{ctx}\n\nRun a KEY ASSUMPTIONS CHECK. List the 5-8 load-bearing ASSUMPTIONS this "
                    "objective+strategy silently rests on. For each: state it in one line; rate CONFIDENCE "
                    "(low/med/high) and IMPACT IF WRONG (low/med/high). End by naming the 2-3 high-impact / "
                    "low-confidence assumptions that most need testing."
                )
                # GE-M3b hook (H2): halt the Deepen phase on >=N high-impact/low-confidence here.
                prep["key_assumptions"] = self._agent_text(r)
                self._emit_prep("key_assumptions", FACILITATOR_SPEC, prep["key_assumptions"])
            if cfg.outside_view:
                o = self._facilitator_agent(OUTSIDE_VIEW_SPEC, "outside-view", _NEUTRAL_SYS)
                r = await o.agenerate(
                    "Take the OUTSIDE VIEW (reference-class forecasting). Ignore project specifics. For the "
                    "general class = 'an established multi-currency online retailer adding complementary-"
                    "product bundling + recommendations to lift AOV and conversion', what is the rough BASE "
                    "RATE of such initiatives clearly succeeding, and the 3-4 most COMMON FAILURE MODES for "
                    "initiatives like this? Name the reference class. Be candid about typical disappointment."
                )
                prep["outside_view"] = self._agent_text(r)
                self._emit_prep("outside_view", OUTSIDE_VIEW_SPEC, prep["outside_view"])

            session = {
                "session_id": f"kp-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}-{uuid4().hex[:6]}",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "project": Path(cfg.project).name, "objective": cfg.objective, "strategy": cfg.strategy,
                "prep": prep, "model_assignment": specs, "adversaries": adv_ids,
                "facilitator_model": FACILITATOR_SPEC, "rounds": [], "synthesis": None,
                "cost_total_usd": 0.0,
            }

            # R1 individual means-ends (adversaries get attack framing)
            r1_prompts = {
                b.role_id: (_r1_adversary_prompt(ctx, pname) if _adv(b.role_id) else _r1_prompt(ctx, pname))
                for b in briefs_all
            }
            r1 = await self._run_round(panel, briefs_all, "R1", "Individual analysis (means-ends)",
                                       "individual", r1_prompts, specs, briefs)
            session["rounds"].append(r1); self._persist(session); self._emit_round(r1)

            # R2 pre-mortem (private — before the collision, for independence)
            r2_prompts = {b.role_id: _premortem_prompt(_adv(b.role_id), pname) for b in briefs_all}
            r2 = await self._run_round(panel, briefs_all, "R2", "Pre-mortem (private)",
                                       "premortem", r2_prompts, specs, briefs)
            session["rounds"].append(r2); self._persist(session); self._emit_round(r2)

            # R3 cross-pollination (react to R1 analyses; self-excluded digest)
            r3_prompts = {b.role_id: _r3_prompt(_digest(r1["entries"], b.role_id)) for b in briefs_all}
            r3 = await self._run_round(panel, briefs_all, "R3", "Cross-pollination",
                                       "cross_pollination", r3_prompts, specs, briefs)
            session["rounds"].append(r3); self._persist(session); self._emit_round(r3)

            # R4 final private judgment (re-independent-ize) — uniform prompt across all
            if cfg.final_judgment:
                r4_prompts = {b.role_id: _r4_prompt() for b in briefs_all}
                r4 = await self._run_round(panel, briefs_all, "R4", "Final private judgment",
                                           "final_judgment", r4_prompts, specs, briefs)
                session["rounds"].append(r4); self._persist(session); self._emit_round(r4)

            # R5 synthesis (neutral facilitator; preserves open tension)
            transcript_text = "\n\n".join(
                f"[{r['round_id']} {r['title']}]\n" + "\n".join(
                    f"{e['display_name']} ({fams[e['role_id']]}): {e['text']}" for e in r["entries"])
                for r in session["rounds"])
            synth_agent = self._facilitator_agent(FACILITATOR_SPEC, "facilitator", _SYNTH_SYS)
            result = await synth_agent.agenerate(
                _synth_prompt(transcript_text, fams, prep), system_prompt=_SYNTH_SYS)
            synth_text = self._agent_text(result)
            # GE-M3b hook (FR-GE-12): assert named raw-round tension_ids survive here.
            session["synthesis"] = {"model": FACILITATOR_SPEC, "text": synth_text}
            # GE-M3b hook (H3): surface per-round + session-total cost / budget hard-halt here.
            session["cost_total_usd"] = round(
                sum(e["cost_usd"] for r in session["rounds"] for e in r["entries"]), 6)
            self._persist(session)
            self._emit_synthesis(FACILITATOR_SPEC, synth_text)
            return session
        finally:
            panel.close()

    # -- hooks ----------------------------------------------------------------
    def _emit_prep(self, kind: str, spec: str, text: str) -> None:
        if self._on_prep is not None:
            self._on_prep(kind, spec, text)

    def _emit_round(self, round_dict: dict) -> None:
        if self._on_round is not None:
            self._on_round(round_dict)

    def _emit_synthesis(self, spec: str, text: str) -> None:
        if self._on_synthesis is not None:
            self._on_synthesis(spec, text)


__all__ = [
    "FacilitationConfig",
    "KickoffFacilitator",
    "assign_models",
    "build_briefs",
    "projected_calls",
    "FAMILIES",
    "FAMILY_ORDER",
    "FACILITATOR_SPEC",
    "OUTSIDE_VIEW_SPEC",
    "ADVERSARY_IDS",
    "DEFAULT_DESC",
    "DEFAULT_OBJECTIVE",
    "DEFAULT_STRATEGY",
    "TRANSCRIPT_SUBDIR",
    "_entry",
    "_adversary_briefs",
]
