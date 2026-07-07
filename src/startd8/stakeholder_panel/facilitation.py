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

Hardening (GE-M3b, on THIS module, per parent FR-13c / FR-GE-10 H1/H2/H3 + FR-GE-12):
  * **H1 artifact-grounding fidelity** — ``_gather_artifact`` grounds on the REAL system via the
    kernel ``survey`` (``concierge.build_survey``), degrading to schema-only WITH an explicit
    in-context warning if the live inventory can't be read (never a silent under-read).
  * **H2 assumptions-as-gate** — after the R0 Key-Assumptions pass, ``>= assumptions_halt_threshold``
    (default 2) high-impact/low-confidence assumptions HALT the run into a first-class
    ``status="halted"`` transcript state ("validate the premise first"), not spending R1–R5.
  * **H3 cost tracking** — per-round ``cost_usd`` + a running session ``cost_total_usd`` ride the
    transcript; a configured ``budget_usd`` ceiling is a hard cumulative-abort at round boundaries.
  * **FR-GE-12 anti-smoothing** — raw-round tensions carry a machine-checkable ``tension_id``
    (``[[tension:T1|label]]``); the synthesis must surface each as an explicit OPEN item, and
    ``check_anti_smoothing`` structurally reports any smoothed away.
"""
from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple
from uuid import uuid4

from startd8.logging_config import get_logger
from startd8.stakeholder_panel.models import PersonaBrief, Roster

logger = get_logger(__name__)


class FacilitationHalt(Exception):
    """Internal signal used to short-circuit a run into a first-class halted transcript state.

    Carries the machine-readable ``halt`` payload the observability-UX viewer renders. Never
    escapes :meth:`KickoffFacilitator.run` — it is converted to a persisted halted session.
    """

    def __init__(self, reason: str, message: str, detail: Optional[dict] = None) -> None:
        super().__init__(message)
        self.reason = reason
        self.message = message
        self.detail = detail or {}

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

# --- domain-NEUTRAL placeholder context (FR-9) --------------------------------
# These carry NO project domain. They are only a last-resort fallback that defers to the live
# project artifact (which ``_gather_artifact`` loads) when a caller supplies no context. The panel's
# run context (desc/objective/strategy) MUST come from the project's kickoff inputs / requirements
# (config-driven — see FR-6/FR-7); a run that facilitates against these placeholders is a
# misconfiguration, not a demo. (Historically these baked the ContextCore "Blue Planet Adventures"
# retail demo, which silently contaminated every run that omitted a domain — removed 2026-07-07.)
DEFAULT_DESC = (
    "the project described by the artifact and kickoff inputs below "
    "(no domain provided — see the grounded context)"
)
DEFAULT_OBJECTIVE = (
    "deliver the project's stated goals as described in its requirements and kickoff inputs below"
)
DEFAULT_STRATEGY = (
    "follow the approach implied by the project's requirements and kickoff inputs below"
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


def _synth_prompt(
    transcript_text: str,
    family_map: Dict[str, str],
    prep: dict,
    tension_ids: Optional[Dict[str, str]] = None,
) -> str:
    fam = "; ".join(f"{r}={f}" for r, f in family_map.items())
    prep_txt = ""
    if prep.get("key_assumptions"):
        prep_txt += f"\n\nKEY ASSUMPTIONS (prep):\n{prep['key_assumptions']}"
    if prep.get("outside_view"):
        prep_txt += f"\n\nOUTSIDE VIEW / base rate (prep):\n{prep['outside_view']}"
    # FR-GE-12: name the machine-checkable tension_ids the raw rounds raised, and REQUIRE each
    # unresolved one to appear as an explicit "Tn ... OPEN" item so anti-smoothing is verifiable.
    if tension_ids:
        listed = "; ".join(f"{tid}={label or '(unlabeled)'}" for tid, label in sorted(tension_ids.items()))
        prep_txt += (
            f"\n\nNAMED RAW-ROUND TENSIONS (FR-GE-12): {listed}\n"
            "Each tension_id that you do NOT genuinely resolve MUST appear verbatim in the "
            "Tensions section marked OPEN (e.g. 'T1 <label> — OPEN'). Never drop or smooth one."
        )
    return (
        f"Model-family assignment (for corroboration strength): {fam}{prep_txt}\n\n"
        f"Full transcript of the facilitated panel:\n\n{transcript_text}\n\n"
        "Produce a structured synthesis:\n"
        "## Risk Register\nEach material risk; which roles flagged it; corroboration = "
        "CROSS-FAMILY if flagged by roles on different model families, else "
        "single-family/single-model.\n"
        "## Adversary Findings\nAbuse/competitive attacks the adversary personas surfaced.\n"
        "## Tensions\nEach real conflict between roles, tagged with its tension_id; RESOLVED "
        "(with the trade-off) or OPEN.\n"
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


def _fmt_inventory(label: str, items: List[str], cap: int = 40) -> str:
    shown = ", ".join(items[:cap]) if items else "(none)"
    return f"{label} ({len(items)}): {shown}"


_ROUTE_MARKER_RE = re.compile(
    r"@\w+\.(?:get|post|put|patch|delete|websocket)\(|"  # FastAPI/Starlette decorators
    r"\bAPIRouter\(|\binclude_router\(|\badd_api_route\(|"  # FastAPI routers
    r"@(?:app|bp|blueprint)\.route\("  # Flask
)
_ENTRYPOINT_NAMES = {"main.py", "app.py", "asgi.py", "wsgi.py", "server.py", "manage.py"}
_SCAN_SKIP_DIRS = {
    ".git", ".venv", "venv", "env", "node_modules", "__pycache__", ".mypy_cache",
    ".pytest_cache", ".startd8", "dist", "build", ".ruff_cache", ".tox", "site-packages",
}


def _scan_built_app(root: Path, *, cap: int = 4000) -> dict:
    """Read-only heuristic inventory of a BUILT application (H1).

    The kernel survey only reports models/docs/fixtures, so a generated FastAPI app reads to the
    panel as "a schema, nothing built yet" — even when routers, auth, an entrypoint, and tests all
    exist on disk. This scans for that build evidence (content/name heuristics only, bounded walk)
    so grounding reflects a *running system*. Never opens more than ``cap`` files.
    """
    modules = test_files = endpoints = migrations = 0
    route_files: List[str] = []
    entrypoints: List[str] = []
    auth_modules: List[str] = []
    for p in root.rglob("*.py"):
        if any(part in _SCAN_SKIP_DIRS for part in p.parts) or not p.is_file():
            continue
        modules += 1
        if modules > cap:
            break
        try:
            rel = str(p.relative_to(root))
        except ValueError:
            rel = p.name
        name = p.name.lower()
        if name.startswith("test_") or name.endswith("_test.py"):
            test_files += 1
        if p.name in _ENTRYPOINT_NAMES:
            entrypoints.append(rel)
        if "auth" in name:
            auth_modules.append(rel)
        if p.parent.name in ("versions", "migrations"):
            migrations += 1
        try:
            hits = len(_ROUTE_MARKER_RE.findall(p.read_text(errors="ignore")))
        except OSError:
            hits = 0
        if hits:
            endpoints += hits
            route_files.append(rel)
    return {
        "py_modules": modules, "test_files": test_files, "endpoints": endpoints,
        "route_files": route_files, "entrypoints": entrypoints,
        "auth_modules": auth_modules, "migrations": migrations,
    }


def _render_built_app(app: dict) -> str:
    """Render the built-application inventory as grounding — the counter to 'nothing is built yet'."""
    n = int(app.get("py_modules", 0) or 0)
    if not n:
        return "### Built application\n(No application code found on disk — data-model/contract only.)"
    lines = ["### Built application (already exists on disk — this is NOT just a schema)",
             f"Python modules: {n}"]
    rf = app.get("route_files", [])
    if rf:
        lines.append(
            f"HTTP route/endpoint files: {len(rf)} (~{app.get('endpoints', 0)} route handlers) — "
            f"e.g. {', '.join(rf[:5])}"
        )
    if app.get("entrypoints"):
        lines.append(f"App entrypoint(s): {', '.join(app['entrypoints'][:4])}")
    if app.get("auth_modules"):
        lines.append(f"Auth module(s): {', '.join(app['auth_modules'][:4])}")
    if app.get("migrations"):
        lines.append(f"DB migration files: {app['migrations']}")
    if app.get("test_files"):
        lines.append(f"Test files: {app['test_files']}")
    return "\n".join(lines)


def _render_survey(survey: dict) -> str:
    """Render the kernel ``survey`` inventory (models/docs/fixtures) as grounding text (H1)."""
    reqs = [d.get("path", "") for d in survey.get("requirement_docs", [])]
    models = list(survey.get("model_files", []))
    fixtures = list(survey.get("fixture_candidates", []))
    return "### Live system inventory (kernel survey)\n" + "\n".join(
        [
            _fmt_inventory("Requirement/PRD docs", reqs),
            _fmt_inventory("Pydantic model files", models),
            _fmt_inventory("Test-fixture candidates", fixtures),
        ]
    )


def _gather_artifact(project) -> Tuple[str, str]:
    """Ground R0 on the REAL system (H1 / FR-13c-1), not the schema alone.

    Reuses the kernel ``survey`` (:func:`startd8.concierge.core.build_survey`) — the shipped
    brownfield inventory of models/docs/fixtures — so grounding reflects what the system
    actually is, then appends the static schema/description excerpts as corroborating detail.

    Returns ``(artifact, warning)``. If the live inventory cannot be read (``build_survey``
    raises), grounding **degrades to schema-only** and returns a non-empty ``warning`` — never a
    silent under-read (R2-S3: degrade-with-explicit-warning path).
    """
    root = Path(project).expanduser()
    parts: List[str] = []
    warning = ""

    # H1: the live-system inventory via the kernel survey — the real system, not the schema.
    try:
        from startd8.concierge.core import build_survey

        parts.append(_render_survey(build_survey(root)))
    except Exception as exc:  # noqa: BLE001 - live artifact unreadable -> degrade, do not crash
        warning = (
            "WARNING (H1 artifact-grounding DEGRADED): could not read the live system "
            f"inventory (survey failed: {exc!r}); grounding fell back to schema/description "
            "files ONLY. Current-state and assumptions-confidence may under-read reality."
        )
        logger.warning("facilitation grounding degraded to schema-only: %s", exc)

    # H1: built-application inventory — routers/auth/entrypoint/tests on disk. Without this the
    # grounding is models+schema only, which the panel reads as "nothing is built yet" even for a
    # fully generated, running app. Independent of build_survey so it still runs if that degrades.
    try:
        parts.append(_render_built_app(_scan_built_app(root)))
    except Exception as exc:  # noqa: BLE001 - grounding must never crash the run
        logger.warning("built-app scan failed: %s", exc)

    # Static schema/description excerpts (kept as corroborating detail under the live inventory).
    picks = ["prisma/schema.prisma", ".contextcore.yaml", "CLAUDE.md", "README.md"]
    file_parts = []
    for rel in picks:
        p = root / rel
        if p.is_file():
            txt = p.read_text(errors="ignore")[:4000]
            file_parts.append(f"### {rel}\n{txt}")
    if file_parts:
        parts.append("\n\n".join(file_parts))
    return ("\n\n".join(parts))[:12000], warning


# ============================ H2: assumptions-as-gate =========================
# The R0 Key-Assumptions pass rates each assumption CONFIDENCE (low/med/high) and IMPACT IF
# WRONG (low/med/high). A deterministic, testable heuristic classifies each line; ``>=THRESHOLD``
# high-impact/low-confidence assumptions HALT the facilitation ("validate the premise first").
_CONF_LOW = re.compile(r"conf(?:idence)?[^\n]{0,24}?\blow\b|\blow[\s-]*conf", re.I)
_IMPACT_HIGH = re.compile(r"impact[^\n]{0,24}?\bhigh\b|\bhigh[\s-]*impact", re.I)


def parse_assumptions(text: str) -> List[dict]:
    """Heuristic, deterministic parse of the Key-Assumptions text into per-line ratings.

    Each returned item = ``{"text", "low_confidence": bool, "high_impact": bool}`` for any line
    carrying at least one rating signal. Simple/regex-based on purpose (testable, no LLM)."""
    out: List[dict] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        low_conf = bool(_CONF_LOW.search(line))
        high_impact = bool(_IMPACT_HIGH.search(line))
        if low_conf or high_impact:
            out.append({"text": line, "low_confidence": low_conf, "high_impact": high_impact})
    return out


def risky_assumptions(text: str) -> List[dict]:
    """The high-impact / low-confidence assumptions — the ones the H2 gate counts."""
    return [a for a in parse_assumptions(text) if a["high_impact"] and a["low_confidence"]]


# ============================ FR-GE-12: anti-smoothing ========================
# A raw-round tension carries a machine-checkable identity so anti-smoothing is *structural*,
# not prose-matched. A persona/round names a tension inline as ``[[tension:T1|<label>]]``; the
# synthesis must surface each such id as an EXPLICIT OPEN item, never smooth it away.
_TENSION_MARKER = re.compile(r"\[\[tension:(T\d+)(?:\|([^\]]*))?\]\]", re.I)
_OPEN_TENSION = re.compile(r"\b(T\d+)\b[^\n]*\bOPEN\b", re.I)


def extract_raw_tensions(rounds: List[dict]) -> Dict[str, str]:
    """Every ``tension_id`` named in the raw R1–R4 entries -> its label (first occurrence)."""
    found: Dict[str, str] = {}
    for rnd in rounds:
        for e in rnd.get("entries", []):
            for m in _TENSION_MARKER.finditer(e.get("text", "")):
                found.setdefault(m.group(1).upper(), (m.group(2) or "").strip())
    return found


def synthesis_open_tensions(synth_text: str) -> set:
    """The ``tension_id``s the synthesis surfaces as EXPLICIT OPEN items (structural, not prose)."""
    return {m.group(1).upper() for m in _OPEN_TENSION.finditer(synth_text)}


def check_anti_smoothing(rounds: List[dict], synth_text: str) -> List[str]:
    """Return the raw ``tension_id``s SMOOTHED away — present in R1–R4 but not OPEN in synthesis.

    Empty list == FR-GE-12 satisfied. A non-empty list is the machine-checkable smoothing failure.
    """
    return sorted(set(extract_raw_tensions(rounds)) - synthesis_open_tensions(synth_text))


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
    # H2 (FR-13c-2 / R2-F4): halt the Deepen rounds when >= this many assumptions are
    # high-impact/low-confidence. Default 2 (tunable via --assumptions-halt-threshold);
    # too low (1) halts on noise, too high (5) lets false premises through.
    assumptions_halt_threshold: int = 2
    # H3 (FR-13c-3 / R2-S1): hard-halt ceiling on cumulative panel spend in USD. 0 = uncapped.
    # Enforced as a cumulative-abort at round boundaries (before the next round's LLM calls).
    budget_usd: float = 0.0

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
        cost_tracker: Optional[object] = None,
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
        self._cost_tracker = cost_tracker
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
            cost_tracker=self._cost_tracker,  # H3: real per-answer cost attribution (FR-13c-3)
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
        entries = list(entries)
        # H3 (FR-13c-3): per-round cost = sum of the panel's per-answer cost_usd attribution.
        round_cost = round(sum(e["cost_usd"] for e in entries), 6)
        return {"round_id": round_id, "title": title, "kind": kind,
                "entries": entries, "cost_usd": round_cost}

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
        # Session scaffold up front so H2/H3 halts are FIRST-CLASS transcript states the
        # observability-UX viewer renders (status="halted", halt={...}), not silent skips.
        prep = {"grounded_context": "", "key_assumptions": "", "outside_view": ""}
        session = {
            "session_id": f"kp-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}-{uuid4().hex[:6]}",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "project": Path(cfg.project).name, "objective": cfg.objective, "strategy": cfg.strategy,
            "prep": prep, "model_assignment": specs, "adversaries": adv_ids,
            "facilitator_model": FACILITATOR_SPEC,
            "status": "in_progress", "halt": None,
            "budget_usd": float(cfg.budget_usd),
            "rounds": [], "synthesis": None, "cost_total_usd": 0.0,
        }
        try:
            # ---- R0 prep (grounding + assumptions + outside view) ----------
            grounded = ""
            if cfg.ground:
                # H1 (FR-13c-1): ground on the REAL system via the kernel `survey`, degrading to
                # schema-only WITH an explicit in-context warning (never silently under-reading).
                artifact, ground_warning = _gather_artifact(cfg.project)
                if artifact:
                    g = self._facilitator_agent(FACILITATOR_SPEC, "facilitator", _NEUTRAL_SYS)
                    r = await g.agenerate(
                        f"Here is the ACTUAL project artifact (live inventory + excerpts):\n\n{artifact}\n\n"
                        f"OBJECTIVE: {cfg.objective}\nSTRATEGY: {cfg.strategy}\n\n"
                        "Produce a concise CURRENT-STATE summary of what this system actually is and does "
                        "today (real entities/services/capabilities). Explicitly flag anything the "
                        "objective/strategy ASSUMES that the artifact does NOT support or contradicts."
                    )
                    grounded = self._agent_text(r)
                if ground_warning:  # degrade-with-warning rides IN the grounded context
                    grounded = f"{ground_warning}\n\n{grounded}".strip()
                prep["grounded_context"] = grounded
                if grounded:
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
                prep["key_assumptions"] = self._agent_text(r)
                self._emit_prep("key_assumptions", FACILITATOR_SPEC, prep["key_assumptions"])
                # H2 (FR-13c-2, spec v0.2.1): assumptions-check-as-GATE. If >= threshold assumptions
                # are high-impact/low-confidence, HALT — "validate the premise first" — rather than
                # spending R1–R5. The halt is an explicit halted-session transcript state, not a skip.
                risky = risky_assumptions(prep["key_assumptions"])
                if len(risky) >= cfg.assumptions_halt_threshold:
                    return self._finish_halt(
                        session,
                        reason="assumptions_gate",
                        message="Validate the premise first — the Key Assumptions Check surfaced "
                                f"{len(risky)} high-impact/low-confidence assumption(s) "
                                f"(threshold {cfg.assumptions_halt_threshold}). The panel rounds "
                                "were NOT spent.",
                        detail={
                            "threshold": cfg.assumptions_halt_threshold,
                            "risky_count": len(risky),
                            "risky_assumptions": [a["text"] for a in risky],
                        },
                    )

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

            # R1 individual means-ends (adversaries get attack framing)
            r1_prompts = {
                b.role_id: (_r1_adversary_prompt(ctx, pname) if _adv(b.role_id) else _r1_prompt(ctx, pname))
                for b in briefs_all
            }
            r1 = await self._run_round(panel, briefs_all, "R1", "Individual analysis (means-ends)",
                                       "individual", r1_prompts, specs, briefs)
            self._land_round(session, r1)

            # R2 pre-mortem (private — before the collision, for independence)
            budget_halt = self._budget_guard(session)  # H3 cumulative-abort before the next round
            if budget_halt is not None:
                return budget_halt
            r2_prompts = {b.role_id: _premortem_prompt(_adv(b.role_id), pname) for b in briefs_all}
            r2 = await self._run_round(panel, briefs_all, "R2", "Pre-mortem (private)",
                                       "premortem", r2_prompts, specs, briefs)
            self._land_round(session, r2)

            # R3 cross-pollination (react to R1 analyses; self-excluded digest)
            budget_halt = self._budget_guard(session)
            if budget_halt is not None:
                return budget_halt
            r3_prompts = {b.role_id: _r3_prompt(_digest(r1["entries"], b.role_id)) for b in briefs_all}
            r3 = await self._run_round(panel, briefs_all, "R3", "Cross-pollination",
                                       "cross_pollination", r3_prompts, specs, briefs)
            self._land_round(session, r3)

            # R4 final private judgment (re-independent-ize) — uniform prompt across all
            if cfg.final_judgment:
                budget_halt = self._budget_guard(session)
                if budget_halt is not None:
                    return budget_halt
                r4_prompts = {b.role_id: _r4_prompt() for b in briefs_all}
                r4 = await self._run_round(panel, briefs_all, "R4", "Final private judgment",
                                           "final_judgment", r4_prompts, specs, briefs)
                self._land_round(session, r4)

            # R5 synthesis (neutral facilitator; preserves open tension)
            transcript_text = "\n\n".join(
                f"[{r['round_id']} {r['title']}]\n" + "\n".join(
                    f"{e['display_name']} ({fams[e['role_id']]}): {e['text']}" for e in r["entries"])
                for r in session["rounds"])
            # FR-GE-12: name the machine-checkable raw-round tension_ids into the synth prompt so
            # the synthesizer must carry each unresolved one as an explicit OPEN item.
            raw_tensions = extract_raw_tensions(session["rounds"])
            synth_agent = self._facilitator_agent(FACILITATOR_SPEC, "facilitator", _SYNTH_SYS)
            result = await synth_agent.agenerate(
                _synth_prompt(transcript_text, fams, prep, raw_tensions), system_prompt=_SYNTH_SYS)
            synth_text = self._agent_text(result)
            # FR-GE-12 anti-smoothing: structurally verify each raw tension_id survives as OPEN.
            smoothed = check_anti_smoothing(session["rounds"], synth_text)
            session["synthesis"] = {
                "model": FACILITATOR_SPEC, "text": synth_text,
                "raw_tension_ids": sorted(raw_tensions),
                "open_tension_ids": sorted(synthesis_open_tensions(synth_text)),
                "smoothed_tension_ids": smoothed,
            }
            if smoothed:  # never silent — the smoothing failure is a first-class transcript flag
                logger.warning("facilitation synthesis smoothed tensions away: %s", smoothed)
            session["status"] = "completed"
            self._recompute_cost(session)  # H3: session-total spend surfaced in the transcript
            self._persist(session)
            self._emit_synthesis(FACILITATOR_SPEC, synth_text)
            return session
        finally:
            panel.close()

    # -- round landing + hardening gates --------------------------------------
    def _land_round(self, session: dict, rnd: dict) -> None:
        """Append a completed round, refresh the running session-total cost, persist, emit."""
        session["rounds"].append(rnd)
        self._recompute_cost(session)
        self._persist(session)
        self._emit_round(rnd)

    @staticmethod
    def _recompute_cost(session: dict) -> None:
        session["cost_total_usd"] = round(
            sum(e["cost_usd"] for r in session["rounds"] for e in r["entries"]), 6)

    def _budget_guard(self, session: dict) -> Optional[dict]:
        """H3 cumulative-abort: if the configured USD ceiling is already met, HALT before the
        next round's LLM calls (real cost is only known post-call, so the honest gate is a
        cumulative check at round boundaries). Returns a halted session or None to proceed."""
        cap = self.config.budget_usd
        if cap and cap > 0:
            self._recompute_cost(session)
            spent = session["cost_total_usd"]
            if spent >= cap:
                return self._finish_halt(
                    session,
                    reason="budget_cap",
                    message=f"Budget cap ${cap:.4f} reached (spent ${spent:.4f}); the remaining "
                            "panel rounds were NOT spent.",
                    detail={"budget_usd": cap, "spent_usd": spent,
                            "rounds_completed": len(session["rounds"])},
                )
        return None

    def _finish_halt(self, session: dict, *, reason: str, message: str, detail: dict) -> dict:
        """Convert the run into a persisted, first-class halted transcript state (H2/H3)."""
        self._recompute_cost(session)
        session["status"] = "halted"
        session["halt"] = {"reason": reason, "message": message, **detail}
        session["synthesis"] = None
        self._persist(session)
        self._emit_synthesis(FACILITATOR_SPEC, f"[HALTED: {reason}] {message}")
        return session

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
    "FacilitationHalt",
    "parse_assumptions",
    "risky_assumptions",
    "extract_raw_tensions",
    "synthesis_open_tensions",
    "check_anti_smoothing",
    "_entry",
    "_adversary_briefs",
]
