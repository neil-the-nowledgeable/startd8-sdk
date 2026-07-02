# Red Carpet Prescriptive Advisor — Implementation Plan

**Version:** 0.1
**Date:** 2026-07-02
**Requirements:** `RED_CARPET_PRESCRIPTIVE_ADVISOR_REQUIREMENTS.md` (v0.1)
**Branch:** `feat/red-carpet-prescriptive-advisor` (branched from `docs/sync-capability-tours`;
verify against `origin/main` before implementing — the RCT spine lives there).

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
  - `@dataclass(frozen=True) NextStep{rank, stage, title, detail, command: Optional[str]}` + `to_dict`.
  - `derive_advisories(root, state, assess, schema_text) -> Tuple[Advisory, ...]`.
  - `build_playbook(root, state, advisories) -> Tuple[NextStep, ...]`.
  - Severity/kind constants; a byte-stable sort key (severity rank → canonical stage order → title).

### Step 2 — Schema-shape insights (FR-RCA-5)
- In the advisor: `from ..languages.prisma_parser import parse_prisma_schema`.
- Read schema via `live_schema_text(root)` (reuse). Absent/empty → "no schema yet" `info`.
- Parse → count models; for each model, count relation fields via `schema.is_relation_field`.
- **False-positive guard (OQ-D):** flag relation-islands only when `len(models) > 1` AND ≥1 model has
  zero relation fields. Single-entity schema → no island warn.
- Wrap `parse_prisma_schema` in try/except → on parse failure, a single bounded `schema-shape` `info`
  ("schema present but unparseable at $0; the cascade's own gate is authoritative"), never raise.

### Step 3 — Input diagnosis + cascade-blocker translation (FR-RCA-6/7, OQ-C dedupe)
- Iterate `assess["kickoff_inputs"]["domains"]`; map status→Advisory per FR-RCA-6. Bound `invalid` error
  strings (e.g. first line, ≤200 chars). Provenance-review only for `estimate`/`config-default`.
- Iterate `assess["cascade"]["blockers"]`; emit `cascade-blocker` advisories.
- **Dedupe (OQ-C):** key advisories by `(kind-family, subject)`; when a cascade blocker and a value-input
  gap name the same subject, keep the cascade-blocker (higher-leverage, matches `ranking` Tier 1) and drop
  the duplicate. Document the rule in the module docstring.

### Step 4 — Ranked playbook (FR-RCA-8)
- `build_playbook` orders: data-model gate (if `not gates["schema"]`) → unmet cascade gates in
  `_CASCADE_GATE_KEYS` order (skip schema, already handled) → value-input gaps → provenance reviews →
  offerable⇒wireframe+`generate backend`. Each `NextStep.command` set where one exists
  (`startd8 generate contract --promote`, `startd8 kickoff red-carpet --agent`, `startd8 wireframe`,
  `startd8 generate backend`). Cap at top-N (OQ-E; N≈7).

### Step 5 — Wire into `build_red_carpet_state` + `to_dict` (FR-RCA-4)
- In `red_carpet.py::build_red_carpet_state`: after computing `stages`/`offerable`, call the advisor
  (reuse the `build_assess(root)` result already fetched for `preview` — fetch once, pass in) and set
  `advisories` / `next_steps` on `RedCarpetState`.
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

### Step 10 — MCP tool (FR-RCA-12)
- `mcp/startd8-mcp-builder/startd8_mcp.py`: register `startd8_red_carpet_state` (`readOnlyHint: true`,
  no destructive/idempotent write hints) → `build_red_carpet_state(project_root).to_dict()`. Mirror the
  existing `startd8_kickoff_state` registration; pagination not needed (bounded single object).

### Step 11 — Tests
- `tests/unit/kickoff_experience/test_red_carpet_advisor.py`: schema-shape (single-entity no-flag;
  15-entity/0-relation island warn; unparseable → info not raise); input diagnosis (absent/invalid/present
  +provenance); cascade-blocker translation + OQ-C dedupe; playbook ordering byte-stability + command
  presence; count caps.
- Extend `test_red_carpet_*` for `to_dict` additive keys + prescriptive `reflection_text`.
- MCP tool read-only introspection test (no write hint; returns the staged map).

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
- **R3 — Command drift** — a suggested command that no longer exists. Mitigation: commands are drawn from
  the documented CLI surface; a smoke test asserts each suggested command's `startd8` subcommand is
  registered.
