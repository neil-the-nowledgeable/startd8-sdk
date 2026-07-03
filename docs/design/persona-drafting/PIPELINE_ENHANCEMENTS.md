# Persona-Drafting Pipeline — Enhancement Suggestions (post-build)

**Date:** 2026-07-03
**Owner:** neil-the-nowledgeable
**State:** All three siblings built + merged to `main` — **Stakeholder Panel** (`startd8 panel`),
**Requirements Panel** (`startd8 requirements`), **Manifest Suggester** (`startd8 screens`) — on the
shared **`persona_drafting`** toolkit, plus the `$0` cascade (`startd8 generate …`) and the Red Carpet
advisor (`build_red_carpet_state` → ranked `next_steps` playbook).

> **Core insight.** The three siblings are **parallel paid islands** that share only a roster: a
> greenfield user runs three separate `--roles` passes, three sessions, three reviews, **three budget
> preflights**. The advisor already computes the ranked path but only *lists* commands. **The biggest
> remaining value is orchestration** — turning the islands into one guided kickoff.

Effort = S/M/L. Status = `backlog` / `building` / `done`.

## Tier 1 — End-user value

| # | Item | Why | Effort | Status |
|---|------|-----|--------|--------|
| 1 | **`startd8 kickoff plan` orchestrator** — one guided, cost-labeled, ordered walkthrough of the whole greenfield path, rendered from `build_red_carpet_state().next_steps`; `next` shows the single immediate action | The advisor *points* at commands (FR-MS-8) but nothing presents the path as one flow. Wiring over existing logic. | M | **building** (FR-KO-1) |
| 2 | **One paid "kickoff session"** — run the requirements + screens role passes against one roster+brief with a **single** budget preflight + one combined review | Each `--roles` pass builds its own `StakeholderPanel` + preflights separately → ~3× cost/latency for one kickoff. | M | backlog |
| 3 | **`review --diff`** for `requirements`/`screens` vs the existing doc/manifest | The one-shot/accumulation lifecycle makes iteration opaque; a diff answers "what would change?". | M | backlog |

## Tier 2 — Functional quick wins (this sweep)

| # | Item | Why | Effort | Status |
|---|------|-----|--------|--------|
| 4 | **`--json` on `synthesize`/`review`/`approve`** (both CLIs) | Confirmed only `elicit`/`suggest` have it — needed for the agentic/MCP surface + CI. | S | **building** (FR-KO-3) |
| 5 | **Wire the toolkit `.gc()` into both CLIs** | Confirmed: `JsonSessionStore.gc()` exists but neither CLI calls it → sessions leak forever. | S | **building** (FR-KO-2) |
| 6 | **MCP tools for the read-only surfaces** (`requirements review`, `screens review`, `$0` baselines) | Confirmed none in `mcp/`. Natural next for the agentic-kickoff story (Concierge precedent). | S–M | backlog |

## Tier 3 — Architectural quick wins

| # | Item | Why | Effort | Status |
|---|------|-----|--------|--------|
| 7 | **Extract the paid-pass boilerplate** (`_run_paid_pass`: load roster → validate → build panel → `asyncio.run` → `close`) into `persona_drafting` | Confirmed duplicated verbatim in `cli_requirements.py` + `cli_screens.py` — a 4th copy the next sibling would add. | S | **building** (FR-KO-4) |
| 8 | **Shared provenance enum** — 3 ad-hoc vocabularies today (`baseline`/`estimate`/`human`; `baseline`/`estimate`; `estimate`/`config-default`/`authored`) | Enables a unified "AI-drafted vs human across my kickoff" view. | S | backlog |
| 9 | **Extract the marker-parse + drafting-prompt pattern** (`_parse_markers`, `TITLE: … \|\| …`) duplicated in `elicit.py`/`suggest.py` | Toolkit DRY. | S | backlog |

## Tier 4 — Operational / low-hanging

| # | Item | Why | Effort | Status |
|---|------|-----|--------|--------|
| 10 | **Capability-index entries** for both new caps | Confirmed neither appears in `docs/capability-index/` → invisible to the manifest/agent card/MCP discovery. `/capability-index` skill exists. | S | **building** (FR-KO-5) |
| 11 | **OTel metrics + a Grafana panel** — both passes emit spans (`requirements.elicit_pass`, `screens.suggest_pass`); surface cost/drafts/flags via `/dbrd-cr8r` | Makes the paid passes observable. | M | backlog |
| 12 | **One end-to-end integration test** (elicit → suggest → generate on a fixture schema) | Each capability is unit-tested; the *chain* isn't. | M | backlog |

## Tier 5 — Build-next (bigger)

| # | Item | Why | Effort | Status |
|---|------|-----|--------|--------|
| 13 | **Wire `elicit` into `reflective-requirements` Phase 1** (seed v0.1) | Closes the P6 dogfood loop. | M | backlog |
| 14 | **Richer `$0` screens baseline** — a dashboard per entity **cluster** (connected components), not just one over the most-connected root | One dashboard is thin for a rich schema. | M | backlog |

## Honest gaps worth a decision

1. **3× cost for one kickoff** — the siblings don't share a panel/session (Tier 1 #2 is the fix).
2. **`init-roster` writes a generic roster** the user must hand-edit; no "derive a roster from my brief" step.
3. **The `$0` screens baseline is a single dashboard** — safe but thin (Tier 5 #14).

---

## This increment

Building the **orchestrator (Tier 1 #1)** + the **quick-win sweep** (#4 `--json`, #5 `.gc()`, #7
paid-pass extraction, #10 capability-index). Specced in
`../kickoff-orchestrator/KICKOFF_ORCHESTRATOR_REQUIREMENTS.md`.
