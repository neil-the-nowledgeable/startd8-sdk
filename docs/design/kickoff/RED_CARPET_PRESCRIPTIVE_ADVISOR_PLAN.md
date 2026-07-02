# Red Carpet Prescriptive Advisor — Implementation Plan

**Version:** 0.2 (Post-CRP R1)
**Date:** 2026-07-02
**Requirements:** `RED_CARPET_PRESCRIPTIVE_ADVISOR_REQUIREMENTS.md` (v0.3)
**Branch:** `feat/red-carpet-advisor` (worktree off `origin/main` at
`~/Documents/dev/startd8-red-carpet-advisor` — the RCT spine lives on `origin/main`).

---

## Planning discoveries (feed the reflection pass)

| What v0.1 assumed | What planning (code read) revealed | Impact |
|-------------------|-----------------------------------|--------|
| A reusable Prisma parser might exist (OQ-A) | **Yes** — `src/startd8/languages/prisma_parser.py::parse_prisma_schema(text) -> PrismaSchema` with `.models: Dict[str, PrismaModel]`, `is_relation_field(field)`, `scalar_fields(model)`, `PrismaField.is_id/has_relation_attr`. Exactly the relation/field surface FR-RCA-5 needs. | **OQ-A resolved.** Schema-shape insights reuse it; no new parser. |
| Schema text source unknown (OQ-F) | `chat.py:124` already calls `live_schema_text(project_root)` to read the on-disk schema; RCT reads `prisma/schema.prisma` via `_present`/`CONVENTION_PATHS`. | **OQ-F resolved.** Reuse `live_schema_text`; if absent, emit the "no schema yet" advisory (FR-RCA-5). |
| Attach to `RedCarpetState.to_dict()` (OQ-B) | `to_dict()` is the **single** serialization path consumed by `/red-carpet.json` (web.py:783), the `red_carpet_state` chat tool (chat.py:154-156), and the CLI `--json`. Attaching there fans out to 3 of 4 surfaces for free. | **OQ-B resolved → attach.** Keep new keys additive; the MCP tool (FR-RCA-12) wraps the same `to_dict()`. |
| `build_assess` exposes enough to diagnose inputs | Confirmed: `_assess_cascade` returns `shape`, `status_counts`, `readiness` (per-stage map), `blockers` (`{section,status,consequence}`); `_assess_kickoff_inputs` returns per-domain `{status, provenance_default}` + a structurally-validated `stakeholders` entry with `authored`/`consumable`/`note`. | FR-RCA-6/7 feasible directly off `build_assess`; no new assess code. |
| `ranking.next_action` returns one action | Confirmed — 4-tier single `NextAction`. The playbook (FR-RCA-3/8) **generalizes** it; reuse its tier logic/ordering intent but emit the full ordered list scoped to RCT stages. | `NextStep` is a new sibling type (adds `rank`, `stage`, `command`); do not overload `NextAction`. |
| `red_carpet_state` tool is new | It **already exists** as a read tool in the kickoff registry (`chat.py:154`, `handle_kickoff_read`). Only the **MCP** exposure is new (server has `startd8_kickoff_state` but no `red_carpet_state`). | FR-RCA-12 is the only genuinely-new surface wiring; the chat tool already returns `to_dict()`. |

---

## Approach & step map

### Step 1 — Advisor data model + core module (FR-RCA-1/2/3)
- New `src/startd8/kickoff_experience/red_carpet_advisor.py`, pure/`$0`/read-only:
  - `@dataclass(frozen=True) Advisory{kind, severity, title, detail, action, command: Optional[str]}` + `to_dict`.
    Closed `kind` set **excludes `bucket-boundary`** (CRP R1-F3 — dead spec).
  - `@dataclass(frozen=True) NextStep{rank, stage, title, detail, command: Optional[str]}` + `to_dict`.
  - `derive_advisories(root, state, assess, schema_text) -> Tuple[Advisory, ...]`.
  - `build_playbook(root, state, advisories) -> Tuple[NextStep, ...]`.
  - Severity/kind constants; byte-stable sort key = **`(severity_rank, kind, title)`** — **not stage**
    (CRP R1-F4 — `Advisory` has no `stage` field; only `NextStep` does).
  - **Command constants (CRP R1-S6):** module-level constants for every suggested command
    (`CMD_GENERATE_CONTRACT_PROMOTE = "startd8 generate contract --promote"`, `CMD_WIREFRAME`,
    `CMD_GENERATE_BACKEND`, `CMD_RED_CARPET_AGENT`, …) referenced by Steps 4/6 and the Step-11 validation
    test — one source of truth so the playbook, reflection text, and the command-drift test can't diverge.

### Step 2 — Schema-shape insights (FR-RCA-5)
- In the advisor: `from ..languages.prisma_parser import parse_prisma_schema`.
- Read schema via `live_schema_text(root)` (reuse). **Emptiness (CRP R1-F5):** treat "schema present" by
  the **`_present` rule (exists AND size>0)**, the same test the data-model gate uses — a zero-byte /
  whitespace-only schema → "no schema yet" `info` (agrees with `data_model: pending`), never
  present-but-unparseable.
- Parse → count models; for each model, count relation fields via `schema.is_relation_field`.
- **False-positive guard (OQ-D):** flag relation-islands only when `len(models) > 1` AND ≥1 model has
  zero relation fields. Single-entity schema → no island warn.
- Wrap `parse_prisma_schema` in try/except → on parse failure, a single bounded `schema-shape` `info`
  ("schema present but unparseable at $0; the cascade's own gate is authoritative"), never raise.
- **Perf-budget fold-in (CRP R1-S3):** the parse + per-model relation scan runs on **every** `to_dict()`
  (the chat tool re-derives each turn). Include the advisor compute in the existing `readiness.py`
  `PerfSample`/`BUDGET_INITIAL_MS` accounting (extend the timed region or add an advisor `PerfSample`) so
  a large schema (e.g. 200 models) can't silently blow the "live surface must not freeze" budget. Add a
  large-schema fixture exercising the `over_budget` path.

### Step 3 — Input diagnosis + cascade-blocker translation (FR-RCA-6/7, OQ-C dedupe)
- Iterate the **value-input** domains of `assess["kickoff_inputs"]["domains"]`; map status→Advisory per
  FR-RCA-6. Bound `invalid` error strings (e.g. first line, ≤200 chars). Provenance-review only for
  `estimate`/`config-default`.
- **Stakeholders carve-out (CRP R1-F1):** `domains["stakeholders"]` has a **different shape**
  (`authored`/`consumable`/`note`, no `provenance_default`) and a wider status set incl. `unavailable`.
  The generic `{absent,invalid,present}` loop **skips `stakeholders`**; a dedicated clause handles it
  (`authored`-not-`consumable`/`unavailable`/`invalid` → `stakeholder` advisory, **never** `input-invalid`
  `error`). Fixtures cover {absent, invalid, unavailable, authored-not-consumable}.
- Iterate `assess["cascade"].get("blockers", [])`; emit `cascade-blocker` advisories. **`inputs_error`
  handling (CRP R1-S2):** when `assess["cascade"]["status"] == "inputs_error"` there is **no `blockers`
  key** — emit **one** bounded advisory carrying the truncated `error` (the most-broken state must still
  yield prescriptive output, no `KeyError`, no silence). Use `.get("blockers", [])` everywhere.
- **Dedupe (OQ-C):** key advisories by `(kind-family, subject)`; when a cascade blocker and a value-input
  gap name the same subject, keep the cascade-blocker (higher-leverage, matches `ranking` Tier 1) and drop
  the duplicate. Document the rule in the module docstring.

### Step 4 — Ranked playbook (FR-RCA-8)
- `build_playbook` orders: data-model gate (if `not gates["schema"]`) → unmet cascade gates in
  `_CASCADE_GATE_KEYS` order (skip schema, already handled) → value-input gaps → provenance reviews →
  offerable⇒wireframe+`generate backend`. Each `NextStep.command` set from the **Step-1 command
  constants** (CRP R1-S6) where one exists — never a bare literal. Cap at top-N (OQ-E; N≈7).

### Step 5 — Wire into `build_red_carpet_state` + `to_dict` (FR-RCA-4)
- **Single-fetch refactor (CRP R1-S1/R1-F2 — the "fetch once" claim is NOT already true).** Today
  `build_red_carpet_state` calls `build_readiness` (which internally calls `build_assess` and discards the
  raw dict, `readiness.py:151`) **and** separately calls `build_assess` only inside `if offerable:`
  (`red_carpet.py:121-125`) — so the non-offerable greenfield path has no reusable assess. Refactor:
  - fetch `assess = build_assess(root)` **once at the top** of `build_red_carpet_state`;
  - add an optional `assess: Mapping | None = None` param to `build_readiness(project_root, *, assess=…)` —
    when supplied it skips the internal `build_assess` (still timed into its `PerfSample`);
  - thread the one `assess` into `build_readiness`, the `preview` computation, and the advisor.
  - *Verify:* a test patches/counts `build_assess` and asserts **exactly one** call per state build on
    both offerable and non-offerable roots.
- Call the advisor with the single `assess` + `state` + schema text; set `advisories`/`next_steps` on
  `RedCarpetState`.
- Extend the `RedCarpetState` dataclass (two new tuple fields, default `()`) + `to_dict` (additive keys).
- Cap advisory/next-step counts in the state builder (OQ-E).

### Step 6 — Prescriptive reflection (FR-RCA-13)
- Extend `reflection_text(state)` to append the top advisory + top 1–3 `next_steps` (with commands),
  gated on presence. Advisory framing preserved.

### Step 7 — CLI panel (FR-RCA-9)
- `cli_kickoff.py::_render_red_carpet_state` (line 211): add an **Insights** block (advisories by
  severity) + a **Next steps** block (ranked, with commands). `--json` unchanged (rides `to_dict`).

### Step 8 — Agent prompt (FR-RCA-10)
- `chat.py::RED_CARPET_SYSTEM_PROMPT`: add a line instructing the conductor to read
  `red_carpet_state.advisories`/`.next_steps` and prescribe them (surface top insights, cite the top next
  step + command) instead of re-deriving. No tool/registry change (the tool already returns `to_dict()`).

### Step 9 — Web rail (FR-RCA-11)
- `web.py` `/concierge/chat` build-progress rail (lines ~414-432): render advisories + next_steps from
  `/red-carpet.json`. Read-only, bounded fields only (no raw paths).
- **HTML-escape every field (CRP R1-S4 — security).** The rail renders client-side via `innerHTML`
  (`refreshRail()`, `web.py:430`); an advisory `title`/`detail` can carry the invalid-YAML error string
  (FR-RCA-6 `input-invalid`) — attacker-influenceable on-disk content. Escape each advisory/next-step
  field before injection (JS `escapeHtml`/`textContent`, mirroring any existing rail escaping). *Verify:*
  a `detail` containing `<img onerror=…>`/`<script>` renders escaped (render-fn unit test or DOM assertion).

### Step 10 — MCP tool (FR-RCA-12)
- `mcp/startd8-mcp-builder/startd8_mcp.py`: register `startd8_red_carpet_state` (`readOnlyHint: true`,
  no destructive/idempotent write hints) → `build_red_carpet_state(project_root).to_dict()`. Mirror the
  existing `startd8_kickoff_state` registration; pagination not needed (bounded single object).

### Step 11 — Tests
- `tests/unit/kickoff_experience/test_red_carpet_advisor.py`: schema-shape (single-entity no-flag;
  15-entity/0-relation island warn; unparseable → info not raise; **zero-byte schema agrees with
  data-model gate**, R1-F5); input diagnosis (absent/invalid/present +provenance); **stakeholders states
  {absent, invalid, unavailable, authored-not-consumable} → `stakeholder` advisory, never `input-invalid`**
  (R1-F1); **`inputs_error` cascade → one bounded advisory, no `KeyError`** (R1-S2); cascade-blocker
  translation + OQ-C dedupe; playbook ordering byte-stability + command presence; advisory sort key
  `(severity, kind, title)` (R1-F4); **kind-coverage** (every closed `kind` produced by ≥1 path, R1-F3);
  count caps.
- **`build_assess` invoked exactly once** per `build_red_carpet_state` on offerable + non-offerable roots
  (R1-S1/F2).
- **Perf:** advisor compute included in a `PerfSample`; large-schema fixture exercises `over_budget` (R1-S3).
- Extend `test_red_carpet_*` for `to_dict` additive keys + prescriptive `reflection_text`.
- MCP tool read-only introspection test (no write hint; returns the staged map) — named server only (R1-F6).
- **Web-rail escaping (R1-S4):** advisory `detail` with `<img onerror>` renders escaped.

---

## §7 Validation Strategy
- **Determinism/stability:** golden-fixture tests assert byte-stable advisory/next-step ordering.
- **False-positive guard:** explicit single-entity and multi-entity-with-relations fixtures assert **no**
  island warn (P3).
- **Boundedness/leak-free:** assert no absolute host paths and bounded error strings in `to_dict()`
  output (safe for telemetry/web/MCP).
- **Advisory-not-a-gate:** assert `cascade_offerable` is byte-identical with and without the advisor
  (NR-2) — removing/adding advisories never changes the offer predicate.
- **Surface parity:** the CLI panel, `/red-carpet.json`, the chat tool, and the MCP tool all derive from
  the same `to_dict()` (one source of truth).

---

## Risks
- **R1 — Schema-shape false positives** (a legit relationless app flagged). Mitigation: OQ-D guard +
  `info`/`warn` severity, never `error`, never a gate (P3).
- **R2 — Payload/token growth** on the per-turn chat tool result (OQ-E). Mitigation: top-N caps in the
  state builder.
- **R3 — Command drift** — a suggested command (or a flag on it) that no longer exists. Mitigation:
  commands live in the Step-1 constants (R1-S6) and are drawn from the documented CLI surface; the smoke
  test asserts the **full token list** (subcommand **+ option names**) resolves in the Typer app — a
  subcommand-only check would miss flag drift (e.g. `--promote` renamed on `generate contract`, which is
  the likelier break). A grep test asserts no bare `startd8 …` literal exists outside the constants module.

---

*v0.2 — Post-CRP R1 (all 6 S accepted). Sequencing unchanged; the corrections harden existing steps:
the single-fetch refactor is now explicit (Step 5, with `build_readiness(assess=…)`), degraded-state
`inputs_error` handling added (Step 3), advisor compute folded into the perf budget (Step 2), web-rail
HTML-escaping added (Step 9), command constants centralized (Step 1) with full-token drift validation
(Risk R3 / Step 11). Dispositions in Appendix A; R1 verbatim in Appendix C. Ready for implementation.*

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

> Triage R1 (orchestrator, 2026-07-02). **All 6 plan suggestions accepted; none rejected** — each was
> verified against the real call graph (`red_carpet.py`/`readiness.py`/`core.py`/`web.py`).

| ID | Suggestion | Source | Implementation / Validation Notes | Date |
|----|------------|--------|-----------------------------------|------|
| R1-S1 | "fetch once" unachievable as written (readiness already calls assess; preview offerable-gated) | CRP R1 | Step 5 single-fetch refactor (`build_readiness(assess=…)`, once-at-top; count test) | 2026-07-02 |
| R1-S2 | `inputs_error` cascade has no `blockers` key | CRP R1 | Step 3 `.get("blockers",[])` + one bounded advisory on `inputs_error`; fixture | 2026-07-02 |
| R1-S3 | advisor compute un-timed vs existing `PerfSample` budget | CRP R1 | Step 2 fold advisor into `PerfSample`; large-schema `over_budget` fixture | 2026-07-02 |
| R1-S4 | web rail `innerHTML` needs escaping (invalid-YAML error string) | CRP R1 | Step 9 HTML-escape every field; `<img onerror>` fixture | 2026-07-02 |
| R1-S5 | command smoke test too weak (subcommand only, misses flag drift) | CRP R1 | Risk R3 + Step 11 full-token (subcommand + flags) Typer resolution | 2026-07-02 |
| R1-S6 | command literals duplicated across steps | CRP R1 | Step 1 command constants; Steps 4/6/11 reference them; grep test | 2026-07-02 |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| *None.* All R1 plan suggestions were code-grounded and accepted. |  |  |  |  |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — claude-opus-4-8-1m — 2026-07-02

- **Reviewer**: claude-opus-4-8-1m
- **Date**: 2026-07-02 18:10:00 UTC
- **Scope**: Dual-document architectural review of the plan against the RCT spine as actually implemented (`red_carpet.py`, `readiness.py`, `concierge/core.py`, `chat.py`, `web.py`, `prisma_parser.py`, `startd8_mcp.py`). Focus: the "fetch once / pure projection" claims vs the real call graph, degraded-state handling, and the four surfaces.

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-S1 | Architecture | high | Step 5 says "reuse the `build_assess(root)` result already fetched for `preview` — fetch once, pass in". This is not achievable as written: (a) `build_red_carpet_state` gets its `preview` `build_assess` **only inside `if offerable:`** (`red_carpet.py:121-125`), so on the **non-offerable** greenfield path — exactly where advisories matter most — there is no fetched result to reuse; and (b) `build_readiness(root)` (called at `red_carpet.py:79`) **already calls `build_assess` internally** (`readiness.py:151`) and discards the raw dict. Refactor to fetch `build_assess(root)` **once at the top** of `build_red_carpet_state`, then thread it into a `build_readiness(root, assess=...)` param, the preview computation, and the advisor. | Without this the advisor either double/triple-scans the tree per chat turn or has no assess to read when not offerable — contradicting P1 and the perf posture (R5-S3). | Step 5 (and update the Planning-discoveries "fetch once" row) | Add a test asserting `build_assess` is invoked exactly once per `build_red_carpet_state` (patch/counter) across both offerable and non-offerable roots. |
| R1-S2 | Risks | high | Step 3 iterates `assess["cascade"]["blockers"]`, but when the assembly inputs fail to load `_assess_cascade` returns `{"status": "inputs_error", "error": ...}` with **no `blockers` key** (`core.py:237-238`). As written this KeyErrors or silently emits nothing for the single most-broken state. Handle `cascade.status == "inputs_error"` explicitly (emit one bounded `cascade-blocker`/`input-invalid` advisory carrying the truncated `error`) and use `.get("blockers", [])` everywhere. | The most severe project state (inputs won't even resolve) currently produces zero prescriptive output. | Step 3 | Fixture with a malformed `ASSEMBLY_INPUTS.yaml` / broken inputs → assert exactly one bounded advisory naming the failure, no exception. |
| R1-S3 | Ops | medium | Step 2 adds an **un-timed** `parse_prisma_schema` + per-model relation scan on every `to_dict()` call (the chat tool re-derives each turn — `chat.py:154-156`), but `readiness.py` already ships `PerfSample`/`BUDGET_INITIAL_MS` (R5-S3) that time **only** the `build_assess` call. Fold the advisor compute into the same perf sample (or extend the budget) so a large schema can't silently blow the "live surface must not freeze" budget. | Mottainai: the perf-budget infra already exists and currently under-counts the new work; a 200-model schema parsed per turn is a real freeze risk on the live web/chat surface. | Step 2 + §7 Validation Strategy | Assert the advisor's compute is included in a `PerfSample`; add a large-schema fixture that exercises the `over_budget` flag path. |
| R1-S4 | Security | high | Step 9 renders advisories/next_steps through the **client-side `refreshRail()`** path (`web.py:430`, `innerHTML`-based). Advisory `detail`/`title` can carry the **invalid-YAML error string** (FR-RCA-6 `input-invalid`), which is attacker-influenceable file content read off disk. Require HTML-escaping of every advisory/next_step field before injection into the rail. | "Bounded, leak-free" (P4) addresses length/paths but not markup injection; an error string containing `<img onerror=...>` would execute in the web rail. | Step 9 | Fixture advisory whose `detail` contains `<script>`/`<img onerror>`; assert the rendered rail escapes it (unit test on the render fn, or a DOM assertion). |

### Stress-test / adversarial pass

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-S5 | Validation | medium | The R3 mitigation ("a smoke test asserts each suggested command's `startd8` subcommand is registered") is too weak: it checks the subcommand, not the flags/args. `startd8 generate contract --promote` would pass the subcommand check even if `--promote` were renamed/removed. Assert the **full token list** (subcommand + option names) against Typer's registered params, or drive each suggested command with `--help` and assert exit 0. | `generate contract` exists with a `--promote` option today (`cli_generate.py:734,770`), but flag drift is the more likely break and is exactly what a subcommand-only check misses. | Risks R3 + Step 11 | Parametrized test over the command-constant table asserting each token (incl. flags) resolves in the Typer app. |
| R1-S6 | Architecture | low | The suggested commands (`startd8 generate contract --promote`, `startd8 wireframe`, `startd8 generate backend`, `startd8 kickoff red-carpet --agent`) are strings duplicated across Step 4, Step 6 (reflection), and the R3 smoke test. Centralize them as module-level constants so the playbook, the reflection text, and the validation test all reference one source. | DRY/Mottainai: prevents the exact drift R3 warns about and makes the R1-S5 check trivial to write. | Step 1 (constants) referenced by Steps 4/6/11 | Grep test: no bare `startd8 ...` command literal outside the constants module. |

**Endorsements / Disagreements:** none — this is the first round (Appendix C had no prior untriaged items).

---

## Requirements Coverage Matrix — R1

Analysis only (no triage). Maps each requirement to the plan step that addresses it.

| Requirement | Plan Step(s) | Coverage | Gaps |
| ---- | ---- | ---- | ---- |
| FR-RCA-1 (pure $0 advisor module) | Step 1 | Full | — |
| FR-RCA-2 (Advisory data model) | Step 1 | Partial | `bucket-boundary` kind has no derivation (R1-F3); sort key references a `stage` the Advisory lacks (R1-F4). |
| FR-RCA-3 (NextStep data model) | Step 1 | Full | — |
| FR-RCA-4 (attach to RedCarpetState, fetch once, caps) | Step 5 | Partial | "fetched once, no double scan" not achievable as written — `build_readiness` already calls `build_assess` and preview's call is offerable-gated (R1-S1 / R1-F2). Caps (OQ-E) covered. |
| FR-RCA-5 (schema-shape insights) | Step 2 | Partial | "no schema yet" uses `live_schema_text` (empty-string tolerant) vs the `_present` size>0 gate — reconcile emptiness semantics (R1-F5). |
| FR-RCA-6 (per-input diagnosis) | Step 3 | Partial | `stakeholders` is mixed into the same `domains` dict with a different shape/status set (`unavailable`) — generic loop mis-handles it (R1-F1). |
| FR-RCA-7 (cascade-blocker translation + dedupe) | Step 3 | Partial | `inputs_error` cascade has no `blockers` key (R1-S2). Dedupe rule (OQ-C) covered. |
| FR-RCA-8 (ranked playbook) | Step 4 | Full | — |
| FR-RCA-9 (CLI panel) | Step 7 | Full | `_render_red_carpet_state` confirmed at `cli_kickoff.py:211`. |
| FR-RCA-10 (agentic chat loop) | Step 8 | Full | Tool already returns `to_dict()` (`chat.py:154-156`); prompt-only change. |
| FR-RCA-11 (web rail) | Step 9 | Partial | Client-side `innerHTML` render needs field escaping (R1-S4). |
| FR-RCA-12 (MCP tool) | Step 10 | Partial | Only `startd8-mcp-builder/startd8_mcp.py` registers `startd8_kickoff_state`; FR says "server(s)" — pin the exact target(s) (R1-F6). |
| FR-RCA-13 (prescriptive reflection) | Step 6 | Full | — |
