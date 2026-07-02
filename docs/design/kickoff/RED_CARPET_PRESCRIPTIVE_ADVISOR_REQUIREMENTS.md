# Red Carpet Prescriptive Advisor — Requirements

**Version:** 0.2 (Post-planning — self-reflective update)
**Date:** 2026-07-02
**Status:** Draft
**Owner:** neil-the-nowledgeable
**Plan:** `RED_CARPET_PRESCRIPTIVE_ADVISOR_PLAN.md`
**Extends (reuse, inherit boundaries — do not re-litigate):**
`RED_CARPET_TREATMENT_REQUIREMENTS.md` (v0.3) + `_PLAN.md`, `WELCOME_MAT_2.0_REQUIREMENTS.md`,
`WELCOME_MAT_CONCIERGE_MODE_REQUIREMENTS.md`; the **four-bucket separation** + **two-generation-paths**
framing in `CLAUDE.md`.

> **What this adds.** Today the Red Carpet experience is *descriptive*: `build_red_carpet_state()`
> reports which stage is `done`/`pending` plus one terse `detail` string per stage, `reflection_text()`
> gives a short retrospective, and `ranking.next_action()` returns exactly **one** next action. This
> feature adds a **deterministic ($0, read-only, no-LLM) prescriptive advisor layer** on top of that
> spine: it (a) derives **insights** about the project (schema shape, missing relations, domain hints),
> (b) **diagnoses the readiness** of each kickoff input (*why* it's not ready + *exactly what to do*),
> and (c) emits a **ranked, concrete next-step playbook** — each step carrying the command that advances
> it. The agentic chat loop reasons **on top of** this deterministic layer (deterministic-first); the
> agent narrates and interviews, but the suggestions themselves are computed, testable, and free.

---

## 0. Planning Insights (Self-Reflective Update)

> What changed between v0.1 (pre-planning) and v0.2. The planning pass confronted the draft with the
> real code. The headline holds — this is a **pure projection** of already-computed state — and planning
> resolved the three feasibility questions (parser, schema source, distribution point) in the advisor's
> favor, so it builds cleanly on the RCT spine with no new engine.

| v0.1 Assumption | Planning Discovery | Impact |
|-----------------|-------------------|--------|
| A reusable Prisma parser might exist (OQ-A) | **Yes** — `languages/prisma_parser.parse_prisma_schema` exposes `.models`, `is_relation_field`, `scalar_fields`, `PrismaField.is_id/has_relation_attr` — exactly FR-RCA-5's surface. | **OQ-A resolved.** FR-RCA-5 reuses it; P1 (no new parser) holds. |
| Schema-text source unknown (OQ-F) | `live_schema_text(project_root)` already reads the on-disk schema (used in `chat.py`). | **OQ-F resolved.** Reuse it; absent → the "no schema yet" advisory. |
| Attach to `to_dict()` vs a separate call (OQ-B) | `to_dict()` is the **single** path consumed by `/red-carpet.json`, the `red_carpet_state` chat tool, and CLI `--json` — attaching there fans out to 3 of 4 surfaces for free; the MCP tool wraps the same. | **OQ-B resolved → attach** (additive keys). Distribution is one point, not four. |
| `red_carpet_state` is a new tool | It **already exists** as a chat read tool (`handle_kickoff_read`, returns `to_dict()`). Only the **MCP** exposure is new. | FR-RCA-12 (MCP tool) is the sole genuinely-new surface wiring; FR-RCA-10/11 are prompt/render-only. |
| Reuse `ranking.next_action` for the playbook | It returns **one** `NextAction` (4-tier). The playbook needs an **ordered list** with `rank`/`stage`/`command`. | FR-RCA-3: `NextStep` is a **new sibling** type; don't overload `NextAction`. Reuse its tier *intent*, not its shape. |
| `build_assess` exposes enough to diagnose inputs | Confirmed: cascade `{shape, status_counts, readiness, blockers:{section,status,consequence}}` + per-domain `{status, provenance_default}` + validated `stakeholders{authored,consumable,note}`. | FR-RCA-6/7 read `build_assess` directly; no new assess code. Fetch `build_assess` **once** and pass it to both `preview` and the advisor (avoid a double scan). |

**Resolved open questions:**
- **OQ-A → RESOLVED.** Reuse `languages/prisma_parser.parse_prisma_schema` (no new parser).
- **OQ-B → RESOLVED → attach to `RedCarpetState.to_dict()`** (additive keys); the MCP tool wraps the same.
- **OQ-C → RESOLVED → dedupe by `(kind-family, subject)`;** when a cascade blocker and a value-input gap
  name the same subject, keep the **cascade-blocker** (higher leverage, matches `ranking` Tier 1). Now a
  stated rule in FR-RCA-7.
- **OQ-D → RESOLVED → island rule:** flag relation-islands only when `len(models) > 1` **and** ≥1 model
  has zero relation fields; severity `warn` (never `error`/gate). Now stated in FR-RCA-5 acceptance.
- **OQ-E → RESOLVED → top-N caps** in the state builder (advisories and next_steps each capped, N≈7) so
  the per-turn chat tool result stays bounded. Now stated in FR-RCA-4.
- **OQ-F → RESOLVED → reuse `live_schema_text`** (absent → "no schema yet" advisory).

---

## 1. Problem Statement

The Red Carpet spine already computes everything needed to *know* what's wrong — it just doesn't say
much about it. A greenfield user (or the conducting agent) sees "manifests: pending" but not *why*,
*what specifically to author*, or *which command produces it*. The prescriptive knowledge lives in the
maintainers' heads and the design docs, not in the tool output.

| Component | Current State | Gap |
|-----------|--------------|-----|
| **Insights about the project** | None. `RedCarpetState` reports stage status + a `preview` (shape/counts) only when already offerable. | No derived observations — e.g. "schema has 15 entities but 0 relations → likely missing FKs", "you have pages but no views → a dashboard is probably intended", "conventions is `estimate`-defaulted → confirm it". |
| **Per-input readiness diagnosis** | `build_assess` returns per-domain `status` (absent/invalid/present) + `provenance_default`, and `cascade.blockers` (section/status/consequence). RCT collapses these to one `detail` string per stage. | No per-input *diagnosis*: why a domain is not ready, what the invalid-YAML error was, and the exact authoring action to fix it. |
| **Next steps** | `ranking.next_action()` returns a single `NextAction`; RCT's per-stage `detail` strings are generic. | No **ranked playbook** of concrete steps, and no step carries the **command** that advances it. |
| **Agentic conductor** | `RED_CARPET_SYSTEM_PROMPT` tells the agent to find "the next gap" and propose a kind. | The agent re-derives guidance ad hoc per turn (paid, non-deterministic) instead of citing a computed, $0 advisory. |
| **Surfaces** | CLI panel, `/red-carpet.json` + web rail, and the `red_carpet_state` chat read tool render the thin state. No RCT-specific MCP tool exists (`startd8_kickoff_state` omits the staged map). | The richer prescriptive output must reach all four: CLI, agent loop, web rail, and a new read-only MCP tool. |

**What should exist:** a `$0` deterministic advisor that turns the state RCT already computes into
**insights + a per-input readiness diagnosis + a ranked, command-bearing next-step playbook**, attached
to `RedCarpetState` (so every surface gets it through the existing `to_dict()` path), with the agentic
loop citing it rather than re-deriving it.

---

## 2. Guiding Principles

- **P1 — Orchestrate, don't re-implement (inherited).** The advisor is a **pure projection** of data
  the SDK already computes: `build_assess` (cascade shape/counts/blockers + per-domain provenance),
  `build_readiness`, the on-disk `schema.prisma` parsed by the **existing** `languages/prisma_parser`,
  and the RCT stage map. It introduces **no new** readiness computation, **no new** parser, and **no new**
  write path.
- **P2 — Deterministic-first; the agent reasons on top.** The suggestions are computed by a pure `$0`
  function (testable, byte-stable). The chat agent consumes them and adds narrative/interview, but the
  advisory content is not an LLM artifact. The `$0` surfaces (CLI/web/MCP) get the full benefit with no
  token cost.
- **P3 — Advisory, never a gate (inherited from FR-RCT-12).** Insights and next steps are recommendations.
  They never block a stage, never fail a build, and never gate the cascade offer (that stays FR-RCT-10's
  `cascade_offerable` predicate). A false-positive insight must be *ignorable*, not *blocking*.
- **P4 — Read-only, bounded, leak-free.** The advisor never writes. Its output carries only bounded,
  structured fields — no interview text, no absolute host paths, bounded error strings — so it is safe to
  emit over telemetry, the web rail, and MCP (which stays read-only, NR-3).
- **P5 — Stable ordering.** Advisories and next steps are emitted in a **deterministic, byte-stable**
  order (canonical stage order + severity), so surfaces are idempotent and the output is unit-testable.

---

## 3. Requirements

### A. The deterministic advisor core

- **FR-RCA-1 — A pure `$0` advisor module.** A new `red_carpet_advisor.py` (or advisor functions in
  `red_carpet.py`) exposes pure, read-only, no-LLM functions that take the already-computed inputs
  (`RedCarpetState`, the `build_assess` result, and the on-disk schema text) and return
  `(advisories, next_steps)`. No I/O beyond reading files the RCT spine already reads.
- **FR-RCA-2 — Insight/advisory data model.** Define a frozen `Advisory{kind, severity, title, detail,
  action, command?}`:
  - `kind ∈ {schema-shape, input-gap, input-invalid, cascade-blocker, provenance-review, stakeholder,
    bucket-boundary}` (closed set),
  - `severity ∈ {info, warn, error}` (advisory only — `error` still never blocks, per P3),
  - `title` (short), `detail` (the *why*), `action` (the *what to do*), optional `command` (the exact CLI
    invocation, relative paths only).
- **FR-RCA-3 — Ranked next-step playbook data model.** Define a frozen `NextStep{rank, stage, title,
  detail, command?}` and return an **ordered** tuple (rank 1..N). This generalizes `ranking.next_action`
  (one action) into the RCT stage playbook; each step names its stage and, where one exists, the command
  that advances it.
- **FR-RCA-4 — Attach to `RedCarpetState`.** `build_red_carpet_state()` computes and attaches
  `advisories` and `next_steps`; `to_dict()` serializes them. This is the single distribution point — all
  four surfaces read the same computed output. Backward compatible: existing keys unchanged; new keys
  additive. `build_assess(root)` is fetched **once** and passed to both the `preview` computation and the
  advisor (no double scan). **Top-N caps (OQ-E):** advisories and `next_steps` are each capped (N≈7) in
  the state builder so the per-turn chat tool result stays bounded.

### B. The insight derivations (what the advisor knows how to see)

- **FR-RCA-5 — Schema-shape insights.** Read the on-disk `schema.prisma` via the **existing**
  `live_schema_text` (OQ-F) and parse it with the **existing** `parse_prisma_schema` (OQ-A). Wrap the
  parse in try/except → an unparseable schema yields one bounded `schema-shape` `info` ("the cascade's own
  gate is authoritative"), never raises. Derive at least:
  - **no schema yet** → `info`, action "start with the data model" + the `brief`/`schema` path;
  - **relation islands** — when >1 model exists and one or more models have **zero relation fields**
    (`is_relation_field` over the model's fields) → `warn`, "N models are unlinked; likely missing
    foreign keys/relations", action "add relations then re-promote the contract";
  - **entity count** (`info`) as a project-scale signal.
  - **Acceptance:** a single-entity app produces **no** relation-island `warn` (a legitimately relationless
    schema is not flagged as broken — P3/false-positive guard); a 15-entity/0-relation schema produces the
    island `warn` naming the count. *Verify:* unit tests over fixture schemas.
- **FR-RCA-6 — Per-input readiness diagnosis.** From `assess.kickoff_inputs.domains`, per value-input
  domain emit a diagnosis:
  - `absent` → `input-gap` `warn`: "author `<domain>`", command = the authoring/capture path;
  - `invalid` → `input-invalid` `error`: surface the **bounded** YAML error + "fix the file";
  - `present` with `provenance_default ∈ {estimate, config-default}` → `provenance-review` `info`:
    "value is defaulted — confirm or change" (mirrors `ranking.next_action` Tier 3);
  - stakeholders `authored` but not `consumable` → `stakeholder` `info` (carry the existing note).
- **FR-RCA-7 — Cascade-blocker translation.** From `assess.cascade.blockers` (each `{section, status,
  consequence}`), emit one `cascade-blocker` advisory per blocker with the section title, the consequence
  as `detail`, and the command that resolves that section where determinable. **Dedupe rule (OQ-C):**
  advisories are keyed by `(kind-family, subject)`; when a cascade blocker and a value-input gap
  (FR-RCA-6) name the same subject, keep the **cascade-blocker** (higher leverage, matches `ranking`
  Tier 1) and drop the duplicate.
- **FR-RCA-8 — Ranked playbook assembly.** Assemble `next_steps` in canonical dependency order: (1) the
  data-model gate if the schema is absent; (2) unmet cascade gates in `app → pages → views` order
  (FR-RCT-10's `_CASCADE_GATE_KEYS`); (3) value-input gaps; (4) provenance reviews; (5) when
  `cascade_offerable`, the "review the wireframe, then run `startd8 generate backend`" step. Each step
  carries a `command` where one exists. Ordering is byte-stable.

### C. Surfaces (all four)

- **FR-RCA-9 — CLI read-only panel.** `_render_red_carpet_state` renders an **Insights** section
  (advisories grouped/sorted by severity) and a **Next steps** section (the ranked playbook with
  commands). `--json` carries both via `to_dict()`.
- **FR-RCA-10 — Agentic chat loop.** Update `RED_CARPET_SYSTEM_PROMPT` so the conductor **reads
  `red_carpet_state.advisories` / `.next_steps` and prescribes them** — surfacing the top insights and
  citing the top next step (with its command) each turn — rather than re-deriving guidance. The
  deterministic layer is the source of truth; the agent adds interview + narrative. The loop stays
  **propose-only** (unchanged; no new write path).
- **FR-RCA-11 — Web stage rail.** `/red-carpet.json` already serializes `to_dict()`; the
  `/concierge/chat` build-progress rail (`web.py`) renders the advisories + next steps alongside the
  stages (read-only, refreshed per turn).
- **FR-RCA-12 — New read-only MCP tool.** Add `startd8_red_carpet_state` (`readOnlyHint: true`) to the
  MCP server(s), wrapping `build_red_carpet_state().to_dict()` — the staged map + advisories + next steps.
  Inherits NR-3: **read-only, never a write**, not a loop-reachable apply.

### D. Retrospective integration

- **FR-RCA-13 — Prescriptive reflection.** Extend `reflection_text` to fold in the **top advisory** and
  the **top 1–3 next steps** (with commands), so the per-increment RETROSPECTIVE (FR-RCT-12) is
  prescriptive, not just descriptive. Still advisory, never a gate.

---

## 4. Non-Requirements

- **NR-1 — No new readiness/assess/parser.** The advisor derives from `build_assess`, `build_readiness`,
  and `parse_prisma_schema`; it computes no new provisioning/readiness state and adds no new parser.
- **NR-2 — Advisory only; never a gate.** Nothing here blocks a stage, fails a build, or changes the
  `cascade_offerable` predicate (FR-RCT-10). Removing the advisor would not change what the cascade does.
- **NR-3 — No writes; MCP stays read-only.** No new proposal kind, no new write seam. The MCP tool and the
  agent loop are read/propose-only, unchanged.
- **NR-4 — No LLM in the deterministic layer.** Insight derivation is `$0`. The only paid surface remains
  the existing chat interview (FR-RCT-13), which merely *cites* the free advisory.
- **NR-5 — Not a linter/validator.** Insights are onboarding guidance, not a schema-correctness gate; they
  never claim authority the cascade's own gates hold.
- **NR-6 — Not polyglot / not real content.** Targets the deterministic Python cascade path; never
  authors bucket-4 content.

---

## 5. Open Questions

*All 6 resolved by the planning pass — see §0. Retained for the record.*

- **OQ-A — RESOLVED → reuse `languages/prisma_parser.parse_prisma_schema`** (no new parser).
- **OQ-B — RESOLVED → attach to `RedCarpetState.to_dict()`** (additive keys); the MCP tool wraps the same.
- **OQ-C — RESOLVED → dedupe by `(kind-family, subject)`**, keep the cascade-blocker (FR-RCA-7).
- **OQ-D — RESOLVED → island rule:** flag only when `>1` model AND ≥1 model has zero relation fields;
  severity `warn`, never a gate (FR-RCA-5).
- **OQ-E — RESOLVED → top-N caps** (N≈7) in the state builder (FR-RCA-4).
- **OQ-F — RESOLVED → reuse `live_schema_text`** (FR-RCA-5).

---

*v0.2 — Post-planning self-reflective update. P1 ("pure projection, no new engine") **confirmed** — the
advisor reuses `parse_prisma_schema`, `live_schema_text`, `build_assess`, and the `to_dict()`
distribution path; the only genuinely-new surface wiring is the `startd8_red_carpet_state` MCP tool
(FR-RCA-12). All 6 open questions resolved by planning: parser + schema-source + distribution-point
confirmed feasible; the schema-island false-positive guard (OQ-D), the dedupe rule (OQ-C), and the
payload caps (OQ-E) are now stated acceptance details. `NextStep` is a new sibling of `NextAction` (not
an overload). Ready for CRP review before implementation.*
