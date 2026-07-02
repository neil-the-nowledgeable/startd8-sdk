# Red Carpet Prescriptive Advisor — Requirements

**Version:** 0.4 (Do-now enhancement batch)
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
  - `kind ∈ {schema-shape, input-gap, input-invalid, cascade-blocker, provenance-review, stakeholder}`
    (closed set — **CRP R1-F3:** `bucket-boundary` removed; no derivation emits it, so it would be dead
    spec. If a bucket-4-drift detector is added later, it re-enters the set *with* its derivation),
  - `severity ∈ {info, warn, error}` (advisory only — `error` still never blocks, per P3),
  - `title` (short), `detail` (the *why*), `action` (the *what to do*), optional `command` (the exact CLI
    invocation, relative paths only).
  - **Advisory ordering (CRP R1-F4, P5):** `Advisory` has **no `stage` field**; advisories sort by the
    byte-stable key **`(severity_rank, kind, title)`** — not by stage (only `NextStep` carries a stage).
    A coverage test asserts every `kind` in the closed set is produced by ≥1 derivation.
- **FR-RCA-3 — Ranked next-step playbook data model.** Define a frozen `NextStep{rank, stage, title,
  detail, command?}` and return an **ordered** tuple (rank 1..N). This generalizes `ranking.next_action`
  (one action) into the RCT stage playbook; each step names its stage and, where one exists, the command
  that advances it.
- **FR-RCA-4 — Attach to `RedCarpetState`.** `build_red_carpet_state()` computes and attaches
  `advisories` and `next_steps`; `to_dict()` serializes them. This is the single distribution point — all
  four surfaces read the same computed output. Backward compatible: existing keys unchanged; new keys
  additive.
  - **Single-fetch refactor (CRP R1-F2/R1-S1 — required, not already-true):** today `build_red_carpet_state`
    calls `build_readiness` (which itself calls `build_assess` and discards the raw dict) **and**
    separately calls `build_assess` only inside `if offerable:` — so the non-offerable greenfield path
    (where advisories matter most) has no fetched result to reuse. The acceptance is: `build_assess(root)`
    is fetched **once at the top** of `build_red_carpet_state` and threaded into (a) `build_readiness(root,
    assess=…)` (new optional param), (b) the `preview` computation, and (c) the advisor. *Verify:* a test
    asserts `build_assess` is invoked **exactly once** per state build, on both offerable and
    non-offerable roots.
  - **Top-N caps (OQ-E):** advisories and `next_steps` are each capped (N≈7) in the state builder so the
    per-turn chat tool result stays bounded.

### B. The insight derivations (what the advisor knows how to see)

- **FR-RCA-5 — Schema-shape insights.** Read the on-disk `schema.prisma` via the **existing**
  `live_schema_text` (OQ-F) and parse it with the **existing** `parse_prisma_schema` (OQ-A). Wrap the
  parse in try/except → an unparseable schema yields one bounded `schema-shape` `info` ("the cascade's own
  gate is authoritative"), never raises. **Emptiness rule (CRP R1-F5):** "schema present" uses the **same
  non-empty test as the data-model gate** — `_present` (exists **AND** `size > 0`), not `live_schema_text`'s
  exists-only read — so a zero-byte/whitespace-only `schema.prisma` reads as "no schema yet" (consistent
  with `data_model: pending`), never as "present-but-unparseable". Derive at least:
  - **no schema yet** (absent or empty per `_present`) → `info`, action "start with the data model" + the
    `brief`/`schema` path;
  - **relation islands** — when >1 model exists and one or more models have **zero relation fields**
    (`is_relation_field` over the model's fields) → `warn`, "N models are unlinked; likely missing
    foreign keys/relations", action "add relations then re-promote the contract";
  - **entity count** (`info`) as a project-scale signal.
  - **Acceptance:** a single-entity app produces **no** relation-island `warn` (a legitimately relationless
    schema is not flagged as broken — P3/false-positive guard); a 15-entity/0-relation schema produces the
    island `warn` naming the count. *Verify:* unit tests over fixture schemas.
- **FR-RCA-6 — Per-input readiness diagnosis.** From `assess.kickoff_inputs.domains`, per **value-input**
  domain (`business-targets`/`observability`/`conventions`/`build-preferences`) emit a diagnosis:
  - `absent` → `input-gap` `warn`: "author `<domain>`", command = the authoring/capture path;
  - `invalid` → `input-invalid` `error`: surface the **bounded** YAML error + "fix the file";
  - `present` with `provenance_default ∈ {estimate, config-default}` → `provenance-review` `info`:
    "value is defaulted — confirm or change" (mirrors `ranking.next_action` Tier 3);
  - **Stakeholders carve-out (CRP R1-F1):** `_assess_kickoff_inputs` injects `domains["stakeholders"]`
    with a **different shape** (`authored`/`consumable`/`note`, no `provenance_default`) and a wider status
    set (`absent`/`invalid`/`present`/`unavailable`). The generic `{absent,invalid,present}` loop above
    **must exclude `stakeholders`**; a **dedicated stakeholder clause** is its only handler — `authored`
    but not `consumable` → `stakeholder` `info` (carry the existing note); `unavailable`/`invalid` →
    `stakeholder` `info`/`warn`, **never** an `input-invalid` `error`. *Verify:* fixtures for roster states
    {absent, invalid, unavailable, authored-not-consumable} each yield the intended `stakeholder` advisory
    (or none) and never an `input-invalid` error.
- **FR-RCA-7 — Cascade-blocker translation.** From `assess.cascade.blockers` (each `{section, status,
  consequence}`), emit one `cascade-blocker` advisory per blocker with the section title, the consequence
  as `detail`, and the command that resolves that section where determinable. **Degraded-state handling
  (CRP R1-S2):** when the assembly inputs fail to resolve, `_assess_cascade` returns `{status:
  "inputs_error", error}` with **no `blockers` key** — the advisor must read blockers via
  `.get("blockers", [])` and, on `cascade.status == "inputs_error"`, emit **one** bounded advisory
  carrying the truncated `error` (the most-broken state must still produce prescriptive output, not an
  exception or silence). *Verify:* a malformed-inputs fixture yields exactly one bounded advisory, no
  raise. **Dedupe rule (OQ-C):**
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
  - **HTML-escaping (CRP R1-S4 — security):** the rail renders client-side via `innerHTML`
    (`refreshRail()`), and an advisory `title`/`detail` can carry the **invalid-YAML error string**
    (FR-RCA-6 `input-invalid`) — attacker-influenceable on-disk content. Every advisory/next-step field
    **must be HTML-escaped** before injection. P4's "bounded/leak-free" covers length/paths but **not**
    markup injection. *Verify:* an advisory whose `detail` contains `<img onerror=…>`/`<script>` renders
    escaped (render-fn unit test or DOM assertion).
- **FR-RCA-12 — New read-only MCP tool.** Add `startd8_red_carpet_state` (`readOnlyHint: true`, no
  write/destructive/idempotent hints) to **`mcp/startd8-mcp-builder/startd8_mcp.py`** (the sole server
  registering `startd8_kickoff_state`; **CRP R1-F6** — named exactly, not "server(s)"), wrapping
  `build_red_carpet_state(project_root).to_dict()` — the staged map + advisories + next steps. Inherits
  NR-3: **read-only, never a write**, not a loop-reachable apply. *Verify:* introspection test asserts the
  named server registers the tool with `readOnlyHint: true` and no write hint.

### D. Retrospective integration

- **FR-RCA-13 — Prescriptive reflection.** Extend `reflection_text` to fold in the **top advisory** and
  the **top 1–3 next steps** (with commands), so the per-increment RETROSPECTIVE (FR-RCT-12) is
  prescriptive, not just descriptive. Still advisory, never a gate.

### H. Do-now enhancement batch (v0.4 — value + quick wins)

> Post-implementation review surfaced four high-value-per-effort enhancements. All stay inside the
> established boundaries: `$0`/read-only/no-LLM, advisory-only (P3), no new parser/readiness (NR-1),
> pure projection (P1). Numbered FR-RCA-14..17.

- **FR-RCA-14 — Expanded schema-shape diagnostics.** Beyond island detection + entity count (FR-RCA-5),
  the advisor derives additional `$0` insights from the **existing** `parse_prisma_schema` (no new
  parser), each `info`/`warn` (never `error`, never a gate — NR-2/P3):
  - **no primary key** — a model with no `@id` field and no `@@id` block attribute → `warn`;
  - **likely foreign key without a relation** — a scalar field named `<name>Id`/`<name>_id` whose
    `<Name>` matches a declared model, when the owning model has **no** relation field to that model →
    `warn` ("`X.userId` looks like a foreign key with no relation to `User`");
  - **empty enum** — a declared enum with zero variants → `warn`.
  - **Acceptance:** each fires on a crafted fixture and does **not** fire on a well-formed schema
    (a model with an `@id`, a real `@relation`, and populated enums produces none of these). All reuse
    the existing parser; a false positive is `warn` at worst, never blocking.
- **FR-RCA-15 — `--check` exit-code mode (advisory CI signal).** `startd8 kickoff red-carpet --check`
  runs the read-only advisor and **exits**: `0` = no `error`-severity advisories; `1` = ≥1 `error`
  advisory (a hard readiness problem — invalid input YAML `input-invalid`, or unresolved assembly inputs
  `inputs_error`); `2` = internal error. Mirrors the existing `kickoff check --strict`
  (`_EXIT_CONFORMANCE`) and `polish check` exit-code precedent. Read-only, `$0`, no LLM.
  - **Boundary (NR-2/NR-5):** `--check` is an **advisory CI convenience**, not a build gate — it never
    changes what the cascade does, and `warn`/`info` advisories never fail it. It gates on advisor
    **`error` severity** (operational readiness), not on schema-correctness (which stays the cascade's
    own gate). *Verify:* a project with an invalid input YAML exits 1; a clean/greenfield project (only
    `warn`/`info`) exits 0.
- **FR-RCA-16 — Advisory telemetry.** Extend FR-RCT-14 with a bounded `red_carpet_advice` event carrying
  **counts only** — `n_advisories`, `n_error`, `n_warn`, `n_info`, `n_next_steps` — plus a per-kind
  count map. **No** titles, details, values, or paths (the bounded-attr allow-list, same discipline as
  the stage funnel). Emitted by the conductor on the same transition hook as the stage funnel
  (`record_red_carpet_progress`), so it rides the interactive loop without making the pure read model
  emit side-effects. Feeds the kickoff-funnel dashboard. *Verify:* the event emits with only numeric
  attrs; no advisory text appears in the trace.
- **FR-RCA-17 — Payload versioning + stable advisory code.** `RedCarpetState.to_dict()` gains a
  `schema_version` (parity with `kickoff_state_tool`, so MCP/web consumers can evolve safely), and each
  `Advisory` gains a **stable `code`** (e.g. `schema-shape:islands`, `input-gap:conventions`,
  `cascade-blocker:<section-slug>`) for telemetry aggregation, web anchoring, and cross-turn dedup.
  Additive/backward-compatible: existing keys unchanged. *Verify:* `to_dict()` carries `schema_version`;
  every advisory carries a non-empty `code`; codes are byte-stable across two builds on the same input.

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

*v0.4 — Do-now enhancement batch (post-implementation value review). Adds FR-RCA-14..17 within the
established boundaries: expanded schema diagnostics (no-PK / likely-FK-without-relation / empty-enum,
FR-RCA-14), a `--check` advisory CI exit-code mode (FR-RCA-15), bounded advisory telemetry
(`red_carpet_advice`, FR-RCA-16), and payload `schema_version` + stable advisory `code` (FR-RCA-17). All
$0/read-only/advisory-only; no new parser or readiness. Implemented alongside this doc update.*

*v0.3 — Post-CRP R1 (reviewer claude-opus-4-8-1m; 6 F + 6 S suggestions, all code-grounded against the
real `build_assess`/`RedCarpetState` shapes). Policy: **accept all; none rejected.** Merged: the
stakeholders carve-out (R1-F1 — the generic loop excludes the differently-shaped `stakeholders` entry),
the single-fetch refactor stated as acceptance rather than an already-true claim (R1-F2/R1-S1 —
`build_readiness` gains an `assess=` param; `build_assess` fetched once at the top), removal of the dead
`bucket-boundary` kind (R1-F3), the `(severity, kind, title)` advisory sort key since `Advisory` has no
`stage` (R1-F4), the `_present` non-empty emptiness rule for "no schema yet" (R1-F5), the exact MCP file
name (R1-F6), `inputs_error` degraded-state handling (R1-S2), and web-rail HTML-escaping (R1-S4).
Dispositions in Appendix A; R1 verbatim in Appendix C. Ready for implementation.*

---

## Appendix: Iterative Review Log (Applied / Rejected Suggestions)

This appendix is intentionally **append-only**. New reviewers (human or model) add suggestions to Appendix C; once validated, the orchestrator records the final disposition in Appendix A (applied) or Appendix B (rejected with rationale). **Do not delete A/B** — they are the cross-model memory that stops later reviewers from re-proposing settled or rejected ideas.

### Reviewer Instructions (for humans + models)

- **Before suggesting changes**: Scan Appendix A and Appendix B first. Do **not** re-suggest items already applied or explicitly rejected.
- **When proposing changes**: Append a `#### Review Round R{n}` block under Appendix C (n = highest existing round + 1, or 1), with unique suggestion IDs `R{n}-S{k}` (plan) / `R{n}-F{k}` (requirements).
- **When endorsing prior suggestions**: If you agree with an untriaged item from a prior round, list it in an **Endorsements** section instead of restating it. Multi-reviewer endorsements raise triage priority.
- **When validating (orchestrator)**: For each suggestion, append a row to Appendix A (applied) or Appendix B (rejected) referencing the suggestion ID.
- **If rejecting**: Record **why** (specific rationale) so future reviewers don't re-propose the same idea.

### Appendix A: Applied Suggestions

> Triage R1 (orchestrator, 2026-07-02). **All 6 requirements suggestions accepted; none rejected** —
> each was grounded in the real `build_assess`/`RedCarpetState`/`core.py` shapes and mutually consistent.

| ID | Suggestion | Source | Implementation / Validation Notes | Date |
|----|------------|--------|-----------------------------------|------|
| R1-F1 | `stakeholders` differently-shaped in `domains` — exclude from generic loop; dedicated clause | CRP R1 | FR-RCA-6 stakeholders carve-out (never `input-invalid` error) | 2026-07-02 |
| R1-F2 | "fetch once" contradicts call graph — state the refactor as acceptance | CRP R1 | FR-RCA-4 single-fetch refactor (`build_readiness(assess=…)`, once-at-top; count test) | 2026-07-02 |
| R1-F3 | `bucket-boundary` kind is dead spec | CRP R1 | FR-RCA-2 closed set trimmed; kind-coverage test | 2026-07-02 |
| R1-F4 | Advisory sort references a non-existent `stage` field | CRP R1 | FR-RCA-2 ordering = `(severity, kind, title)`; `Advisory` has no `stage` | 2026-07-02 |
| R1-F5 | "no schema yet" emptiness ≠ data-model gate emptiness | CRP R1 | FR-RCA-5 pinned to `_present` (size>0); zero-byte fixture | 2026-07-02 |
| R1-F6 | FR-RCA-12 "server(s)" under-specified | CRP R1 | FR-RCA-12 names `startd8-mcp-builder/startd8_mcp.py` exactly | 2026-07-02 |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| *None.* All R1 requirements suggestions were code-grounded and accepted. |  |  |  |  |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — claude-opus-4-8-1m — 2026-07-02

- **Reviewer**: claude-opus-4-8-1m
- **Date**: 2026-07-02 18:10:00 UTC
- **Scope**: Requirements-quality review (ambiguity, missing acceptance criteria, testability) grounded in the real `build_assess`/`RedCarpetState` shapes. Feature Requirements suggestions only (F-prefix).

**Executive summary (top gaps):**
- FR-RCA-6 treats `assess.kickoff_inputs.domains` as uniform value-input domains, but `stakeholders` is mixed into that same dict with a different shape and a fourth status (`unavailable`) — the generic loop will mis-diagnose it.
- FR-RCA-4's "fetched once … no double scan" is not true of the current call graph (`build_readiness` itself calls `build_assess`); the requirement should state the required refactor as acceptance.
- FR-RCA-2's `kind` closed set includes `bucket-boundary`, which no derivation emits — a dead enum value.
- FR-RCA-2's Advisory has no `stage`, yet the ordering rule sorts advisories by stage — an unsatisfiable spec.
- "no schema yet" (FR-RCA-5) and the data-model gate use different emptiness rules and can contradict.
- FR-RCA-12 targets "MCP server(s)" without naming the file(s) — under-specified/untestable.

#### Feature Requirements Suggestions

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F1 | Data | high | FR-RCA-6 says "per value-input domain emit a diagnosis" over `assess.kickoff_inputs.domains`, but `_assess_kickoff_inputs` injects `domains["stakeholders"]` with a **different shape** (`authored`/`consumable`/`note`, no `provenance_default`) and a status set that includes `unavailable`/`present`/`invalid`/`absent` (`core.py:198,202-219`). Specify that the generic `{absent,invalid,present}` loop **excludes** `stakeholders` and that the dedicated stakeholder clause is the only handler for it. | Without the carve-out, an `invalid` or `unavailable` roster would be mapped to an `input-invalid` `error` advisory, and a `present` roster would be treated as a value input it is not. | FR-RCA-6 (4th bullet) | Fixtures for roster states {absent, invalid, unavailable, authored-not-consumable}; assert each yields the intended `stakeholder` advisory (or none) and never an `input-invalid` error. |
| R1-F2 | Risks | high | FR-RCA-4 states `build_assess(root)` is "fetched **once** and passed to both the `preview` computation and the advisor (no double scan)". The code contradicts this: `build_red_carpet_state` calls `build_readiness` (`red_carpet.py:79`), which itself calls `build_assess` (`readiness.py:151`) and discards the raw dict; and the preview `build_assess` runs only under `if offerable`. State the required refactor (single top-level fetch threaded into readiness + preview + advisor) as an acceptance criterion, or soften the "no double scan" claim. | An unqualified "no double scan" claim will be read as already-true and the refactor will be skipped, producing 2–3 tree scans per chat turn. | FR-RCA-4 (last two sentences) | Acceptance: a test counting `build_assess` invocations == 1 per state build (see plan R1-S1). |
| R1-F3 | Interfaces | medium | FR-RCA-2's closed `kind` set lists `bucket-boundary`, but none of FR-RCA-5/6/7 (the derivations) ever emit it. Either add a derivation that produces `bucket-boundary` (e.g. flag when value/content inputs stray toward bucket-4 real content — cf. NR-6) with its own acceptance, or remove it from the closed set. | A closed enum with an unreachable member is dead spec and invites an implementer to guess its trigger. | FR-RCA-2 (`kind ∈ {…}`) | Coverage test: every `kind` in the closed set is produced by at least one advisor code path (or is explicitly documented as reserved). |
| R1-F4 | Interfaces | medium | Plan Step 1 defines the advisory sort key as "severity rank → **canonical stage order** → title", but the FR-RCA-2 `Advisory` model has **no `stage` field** (only FR-RCA-3 `NextStep` does). Reconcile: either add an optional `stage`/order field to `Advisory` (P5 byte-stable ordering needs a stable secondary key) or define the advisory ordering purely on (severity, kind, title). | P5 requires a deterministic, testable order; a sort referencing a non-existent field is ambiguous and will produce implementer-dependent ordering. | FR-RCA-2 (or a new ordering acceptance bullet under P5) | Golden-fixture test asserting a fixed advisory byte-order; fails if the sort key is under-specified. |
| R1-F5 | Validation | medium | FR-RCA-5's "no schema yet → info" reads via `live_schema_text`, which returns the text whenever `prisma/schema.prisma` **exists** (including an empty file → `""`), whereas the data-model gate uses `_present` = exists **AND size > 0** (`red_carpet.py:60-65`). Pin FR-RCA-5 to the same non-empty rule so a zero-byte schema cannot simultaneously read as "data_model: pending" and *not* emit "no schema yet". | Two different emptiness definitions across the same feature produce a contradictory surface (stage says pending, advisor says schema present-but-unparseable/empty). | FR-RCA-5 (first sub-bullet + Acceptance) | Zero-byte and whitespace-only `schema.prisma` fixtures: assert the data-model stage and the schema advisory agree. |
| R1-F6 | Interfaces | low | FR-RCA-12 says "Add `startd8_red_carpet_state` … to the MCP server(s)" but only `mcp/startd8-mcp-builder/startd8_mcp.py` registers `startd8_kickoff_state`. Name the exact target file(s); if a second server exists, require a parity test asserting both expose the tool with identical `readOnlyHint`. | "server(s)" is ambiguous and untestable as written; the plan (Step 10) targets exactly one file. | FR-RCA-12 | Introspection test: the named server(s) register `startd8_red_carpet_state` with `readOnlyHint: true` and no write hint. |

**Endorsements / Disagreements:** none — first round, no prior untriaged items in Appendix C.
