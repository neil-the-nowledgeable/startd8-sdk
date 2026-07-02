# Stakeholder Panel Implementation Plan

**Version:** 1.0
**Date:** 2026-07-01
**Tracks requirements:** `STAKEHOLDER_PANEL_REQUIREMENTS.md` v0.2
**Status:** Planned (pre-implementation)

---

## 0. Grounding: what the planning pass established

- **VIPP is merged to `origin/main`** (`src/startd8/vipp/`, head `951b0e96`); the old
  `feat/vipp-project-counterpart` branch is gone. Integrate against real code.
- **VIPP's `$0` invariant is structural.** Deterministic core = `evaluate.evaluate_envelope` +
  `compose.render_dispositions` (no LLM import). The *sole* paid surface is
  `compose.enhance_narrative`, invoked only at `assistant.py:138-144` behind
  `if narrative and agent is not None`, with cost flowing back as `report.cost_usd` /
  `report.llm_used`. **The panel must copy this pattern** — a second opt-in paid pass invoked
  *around* the deterministic core, never inside it.
- **FDE labels need no schema change.** `LabeledClaim.qualifier` and `.source` are free-text; the
  FR-21 label gate only checks the OBSERVED/MECHANISM/PREDICTION *prefix*. Synthetic answers →
  `label=OBSERVED, qualifier="synthetic", source="panel:<role_id>"`, rendered
  `"OBSERVED (project, synthetic)"`.
- **Roster is a plain kickoff YAML**, not a manifest-extraction grammar kind. Do not touch
  `manifest_extraction/`.
- **Persona primitive** = thin wrapper over `agenerate(prompt, system_prompt=…)` with manually
  threaded history. `AgenticSession` (tool loop + `ToolRegistry` + `supports_tool_use()` gate) is
  overkill. `acreate_response` drops `system_prompt` on one branch — avoid it.

---

## 1. Module layout

New package `src/startd8/stakeholder_panel/` (distinct from `vipp/` to keep VIPP's `$0` core clean):

| File | Responsibility | Requirements |
|------|----------------|--------------|
| `models.py` | `PersonaBrief`, `Roster`, `PanelQuestion`, `PanelAnswer` (frozen dataclasses, `to_dict`/`from_dict`, canonical JSON) | FR-2, FR-10 |
| `roster.py` | Load + validate `docs/kickoff/inputs/stakeholders.yaml` → `Roster`; `validate_roster()` | FR-1, FR-4 |
| `persona.py` | `Persona` — compiles brief → system prompt; `ask(question, history) -> PanelAnswer` via `agenerate(system_prompt=…)`; enforces in-character/defer bound | FR-5, FR-7 |
| `panel.py` | `StakeholderPanel` — instantiates one `Persona` per roster entry; holds live agents + per-persona transcript; `ask(role_id, q)`, `ask_all(q)`; session-scoped | FR-5, FR-6, FR-8 |
| `provenance.py` | Wrap a `PanelAnswer` into a `LabeledClaim(OBSERVED, qualifier="synthetic", source="panel:<role_id>")` | FR-10 |
| `transcript.py` | Persist Q&A to `.startd8/stakeholder-panel/<session>.json` (`0600`, gitignore'd); Mottainai re-read | FR-12 |
| `vipp_bridge.py` | The opt-in VIPP pass (see §3) | FR-9, FR-11 |
| `cli.py` (wire into `cli.py`) | `startd8 panel ask/list/session` commands | FR-8, FR-13 |

Persona identity is baked into the **agent instance** (system prompt set at creation), because
`arun_parallel_agents` sends one shared string with no per-call kwargs — for `ask_all` we write a
small panel-local fan-out (`asyncio.gather` over each persona's own `agenerate(system_prompt=…)`)
rather than reuse `arun_parallel_agents` verbatim.

## 2. Roster authoring surface (FR-1, FR-3, FR-4)

1. **Template** — add `src/startd8/concierge_templates/inputs/stakeholders.yaml` with 1–2 exemplar
   personas + inline authoring guidance.
2. **Projection** — add one tuple to `_KICKOFF_FILES` (`concierge/writes.py:38`):
   `("inputs/stakeholders.yaml", "docs/kickoff/inputs/stakeholders.yaml")`. The read-only download
   manifest derives from this list (`_TEMPLATE_GROUPS`), so no drift.
3. **Readiness** — add `"stakeholders"` to the assessment tuple in `_assess_kickoff_inputs`
   (`concierge/core.py:180`) so `assess`/`ReadinessView` reports present/absent/invalid. Roster
   structural validation (`roster.validate_roster`) is invoked here.

> ⚠️ Two independent hardcoded lists (`writes.py:38` projection, `core.py:180` assessment) — both
> must be edited or projection/readiness drift.

## 3. VIPP integration — the paid pass AROUND the core (FR-9, FR-11)

Mirror `enhance_narrative` exactly. Do **not** add the panel to `build_oracle`/`CompositeOracle`.

1. **Thread routing context into OMIT dispositions.** Small `evaluate.py` change: when `_evaluate_one`
   produces the `source="vipp:omit-default"` accept (`evaluate.py:152-159`), attach the unanswered
   `GroundTruthQuestion`s' `symbol` (value_path) + `claim` so a later pass can route them. (Alt:
   re-derive via `_build_questions` in the bridge — rejected: duplicates logic.)
2. **New opt-in pass.** Add `panel: StakeholderPanel | None = None` (and reuse the existing `agent`)
   to `run_vipp_negotiate` (`assistant.py:52`). After `evaluate_envelope` returns ($0), if
   `panel is not None`: for each disposition flagged `vipp:omit-default`, route its question(s) to
   the panel via `vipp_bridge`, collect `PanelAnswer`s, and attach them to the report as **synthetic
   advisory claims** (`LabeledClaim` per §provenance) — they do **not** mutate the disposition
   verdict.
3. **Ratification handoff (FR-11).** Synthetic answers are rendered in the report as an explicit
   "unratified stakeholder input — requires human confirmation" section. No auto-apply; the human
   ratifies via the normal VIPP/Concierge write path (CLI, human privilege).
4. **Cost** — the pass is cost-tracked; spend flows back on the report like `enhance_narrative`.

## 4. Persona semantics (FR-7)

- System prompt template: role, goals, constraints, known positions, and an explicit **defer rule**
  ("If asked outside your brief, say so; do not invent project facts.").
- Post-generation guard: a lightweight check that flags answers that assert facts clearly outside the
  brief's declared scope (advisory flag on the `PanelAnswer`, not a hard block in v1).

## 5. Surfaces (FR-8)

- **Primary: CLI.** `startd8 panel ask --role <id> "question"`, `panel ask-all "question"`,
  `panel list`. Paid, explicit, cost-reported. CLI is the only spend-authorized path.
- **NOT the Concierge read floor.** `handle_concierge_read`/`READ_ACTIONS` is contractually
  `$0`/no-LLM/deterministic; a live paid query cannot live there. (An MCP surface, if ever added, is
  a separate paid tool — deferred, see requirements NR/OQ.)

## 6. Test plan

- Unit: roster load/validate (valid, missing fields, dupe role_id, empty brief); persona defer
  behavior (mock agent); provenance labeling produces `OBSERVED (project, synthetic)` and passes the
  FR-21 gate; transcript round-trip.
- Integration: `run_vipp_negotiate(panel=…)` with a mock panel — assert (a) `$0` when `panel=None`
  (no LLM), (b) OMIT dispositions get synthetic advisory claims when panel provided, (c) verdicts
  unchanged, (d) cost tracked.
- Golden: `instantiate-kickoff` projects `stakeholders.yaml`; `assess` reports the new domain.

## 7. Sequencing

- **M0** — `models.py` + `roster.py` + template + `instantiate-kickoff`/`assess` wiring (authoring
  surface, `$0`, no LLM). Ship-able alone.
- **M1** — `persona.py` + `panel.py` + `provenance.py` + `transcript.py` + `startd8 panel` CLI (live
  panel, standalone of VIPP).
- **M2** — `evaluate.py` routing-context change + `vipp_bridge.py` + `run_vipp_negotiate(panel=…)`
  (VIPP OMIT fallback + ratification handoff).
- **M3** — persona defer-guard hardening; optional moderator/router (deferred per NR-3).

Each milestone is branch-first, tested, merged before the next.
