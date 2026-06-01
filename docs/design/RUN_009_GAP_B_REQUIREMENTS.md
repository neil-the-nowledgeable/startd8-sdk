# RUN-009 Gap B — Mode-B Inheritance (Pre-Existing Upstream Files) — Requirements

**Version:** 0.4 (FR-1/3/4/6 implemented)
**Date:** 2026-06-01
**Status:** FR-1 (Mode-B TS propagation), FR-3 (Prisma field-set inheritance), FR-4 (absent-anchor warning), FR-6 (consume `upstream_anchors`) SHIPPED; FR-2 import-relevance narrowing = refinement (MVP targeting in place)

> **Implementation status (2026-06-01).** **Shipped:** `_collect_upstream_interfaces` feeds **pre-existing on-disk anchors** (seed `upstream_anchors`, loaded in `load_seed_context`) into `build_upstream_interfaces` alongside in-batch producers → a consumer inherits the real `@/lib/db` instead of inventing `@/lib/prisma` (FR-1/FR-6). **FR-3:** for data-model-mirroring features (targeted by file-name/description, `_feature_mirrors_data_model`), `render_prisma_field_sets` (reusing `prisma_parser`) injects the Prisma entity field sets so Zod/TS mirrors use the real names — closing the `bio`-vs-`summary` divergence **at generation time** (complement to the FR-7 symmetry check). **FR-4:** declared-but-absent anchors are warned (inventory incomplete), not silently invented. **Validated end-to-end** against the restored strtd8 `prisma/schema.prisma`: `Profile` renders `summary`/`yearsExp` (no invented `bio`). **Remaining:** FR-2 import-relevance narrowing (MVP injects all on-disk TS/JS anchors + Prisma for mirror-features — fine at the ~9-anchor scale).
**Source incident:** `docs/design/RUN_009_POSTMORTEM.md` Gap B — Fix 1 (RUN-008) cross-feature inheritance covers **Mode A** (intra-batch sibling output — confirmed working: 4 producer/consumer chains inherited correctly) but **not Mode B** (pre-existing upstream files). 5 features independently invented `@/lib/prisma` instead of the project's real `@/lib/db`; the Zod schema invented `bio` instead of the Prisma field set.
**Depends on:** `RUN_009_GAP_A_REQUIREMENTS.md` (the `upstream_anchors` signal — the pre-existing files Mode B reads from are exactly the files Gap A protects from `--fresh`; FR-6 there ↔ FR-6 here). **Gap A must land first** so the anchors survive on disk for Mode B to read.
**Scope:** generation-side propagation of pre-existing on-disk upstream files into a feature's design context. Out of scope: Gap A's seed/cleanup (consumed, not built); inter-batch inheritance (`PLAN_BATCH_ORCHESTRATION` FR-10).

---

## 0. Planning Insights (Self-Reflective Update)

> The planning pass read the merged `contractors/upstream_interface.py`, `prime_contractor._collect_upstream_interfaces`, and `languages/prisma_parser.py`. It found Mode B is **mostly reuse, not new machinery**:

| v0.1 Assumption | Planning Discovery | Impact |
|-----------------|--------------------|--------|
| Mode B needs a new context-injection mechanism. | `upstream_interface.build_upstream_interfaces(producer_files, project_root, …)` **already reads files from disk and extracts their real exports**; `_collect_upstream_interfaces` only restricts its `producer_files` to in-batch `depends_on` producers (`prime_contractor.py`). | **FR-1 is small:** also feed the on-disk **anchor** paths (from Gap A `upstream_anchors`) into the same `build_upstream_interfaces` call. The extractor/renderer are unchanged. |
| Field-shape inheritance (Zod ↔ Prisma) needs new parsing. | `prisma_parser.parse_prisma_schema` (shipped for RUN-008 FR-6/7) already yields the entity→field model. | **FR-3:** for a feature generating a Zod/type mirror of Prisma, inject the parsed Prisma field set — reuses the parser; closes the `bio`-vs-`summary` class **at generation time** (FR-7 symmetry only catches it post-hoc). |
| Mode B is symmetric to Mode A. | Mode A's producer set comes from `depends_on` edges (explicit, in-batch). Pre-existing anchors have **no `depends_on` edge** (they predate the batch) — so selection needs a different signal: the Gap-A anchor list + an import-relevance heuristic. | **FR-2:** anchor *selection* (which anchors to inject for a given feature) is the genuinely new logic, not extraction. |

**Resolved open questions (from planning):**
- **"Is there extraction machinery to reuse?" → YES** (`build_upstream_interfaces`, `extract_ts_exports`, `prisma_parser`). Mode B is selection + feeding, not extraction.
- **"How does Mode B know which files to read?" → the Gap-A `upstream_anchors` signal** (shared, FR-6) + an import-relevance heuristic (FR-2).

---

## 1. Problem Statement

When a feature imports from a **pre-existing project file** (the M1 ship set: `lib/db.ts`, `prisma/schema.prisma`, `lib/env.ts`) — one not produced by an earlier feature in the same batch — the drafter receives **no signal about the project's existing module inventory** and falls back to a canonical guess (`@/lib/prisma` for a Prisma client the project actually exposes at `@/lib/db`; `bio` for a Prisma column actually named `summary`). The choice is stable across features (not LLM noise), confirming the drafter has zero inventory signal. `_collect_upstream_interfaces` propagates only in-batch `depends_on` producers (Mode A); pre-existing anchors are never read.

| Component | Current state | Gap |
|-----------|--------------|-----|
| `_collect_upstream_interfaces` | feeds `build_upstream_interfaces` only in-batch `depends_on` producer `target_files` | never includes pre-existing on-disk anchors |
| `build_upstream_interfaces` | reads any path from disk + extracts exports | not given anchor paths to read |
| Prisma field inheritance | `prisma_parser` exists; not consulted at generation time | Zod features invent fields instead of mirroring Prisma |
| anchor signal | Gap A emits `upstream_anchors` | not yet consumed by generation context |

---

## 2. Requirements

### FR-1 — Propagate pre-existing on-disk anchors into the design context
`_collect_upstream_interfaces` MUST, in addition to in-batch `depends_on` producers (Mode A), feed **selected pre-existing on-disk anchor files** (FR-2) into `build_upstream_interfaces`, so the drafter sees their **real module path + exported symbols** and imports EXACTLY those. Reuses the existing extractor/renderer.
*Acceptance:* with `lib/db.ts` on disk exporting `db`, a feature importing the Prisma client emits `import { db } from "@/lib/db"`, not `@/lib/prisma`.

### FR-2 — Anchor selection (which anchors a feature inherits)
Selection MUST combine: **(a)** a canonical always-relevant set (e.g. `lib/db.ts`, `prisma/schema.prisma`, `lib/env.ts`) injected when the batch/feature touches the relevant scope; and **(b)** an import-relevance heuristic — an anchor whose exported symbol or module path appears in the feature's task description / declared imports / language-aware import inference. Token cost MUST be bounded (inject content, cap by relevance, let `enforce_prompt_budget` evict low-priority sections).
*Acceptance:* a feature with no plausible use of any anchor receives no anchor context (budget unchanged); a Prisma-client-using feature receives `lib/db.ts`.

### FR-3 — Prisma field-set inheritance at generation time
For a feature generating a Zod schema / TypeScript type that mirrors a Prisma model, the context MUST include the **parsed Prisma entity field set** (reusing `prisma_parser`) so the generated field names/types match Prisma. This closes the RUN-008/009 `bio`-vs-`summary` divergence **at generation** — complementary to the FR-7 Prisma↔Zod symmetry check, which only flags it post-hoc.
*Acceptance:* with `prisma/schema.prisma` on disk, the regenerated `ProfileSchema` field set matches the Prisma `Profile` model (no invented `bio`; includes `summary`, `yearsExp`, …).

### FR-4 — Block loudly on a declared-but-absent anchor (no silent invention)
If an anchor the feature is selected to inherit from is **declared (in `upstream_anchors`) but absent on disk** (e.g. wiped pre-Gap-A), the feature MUST surface it (a `MissingUpstreamArtifact`-style diagnostic, mirroring RUN-008 FR-2) rather than silently inventing — at minimum a logged warning that the inventory is incomplete.
*Acceptance:* a declared anchor missing on disk → surfaced diagnostic, not a silent canonical guess.

### FR-5 — Regression reproduction
Tests MUST reproduce run-009: M1 ship-set anchors on disk + an M2/M3 feature importing the Prisma client → emitted import is `@/lib/db` (not `@/lib/prisma`); + a Zod feature → field set matches `prisma/schema.prisma`. Negative: a feature using no anchor → no anchor context, budget unchanged.

### FR-6 — Consume Gap A's `upstream_anchors` signal (shared contract)
Mode B MUST read the **same `upstream_anchors` signal** Gap A emits (don't build a second anchor-discovery path). The files Gap A protects from `--fresh` are exactly the files Mode B reads from.
*Acceptance:* Mode B's anchor set is derived from the Gap-A signal; no independent anchor enumeration.

---

## 3. Non-Requirements
- **Does NOT implement Gap A** (seed/cleanup/durability) — consumes its `upstream_anchors` signal (FR-6).
- **Does NOT change Mode A** (in-batch sibling inheritance — confirmed working).
- **Does NOT do inter-batch inheritance** — that is `PLAN_BATCH_ORCHESTRATION` FR-10 (same mechanism, different seam).
- **Does NOT add a missing-dependency (`package.json`) signature** — that is the RUN-009 Gap C residual, separate.

---

## 4. Open Questions (for CRP / implementation)
- **OQ-1 — selection heuristic precision.** Canonical-set + import-name match vs a tighter import-graph inference. False positives waste budget; false negatives reinvent. Where's the line, and is the canonical set per-language/per-framework configurable?
- **OQ-2 — token budget.** Injecting full anchor file content (e.g. a 268-line `prisma/schema.prisma`) is costly; inject the parsed *interface* (exports / entity field model) rather than raw content? Confirm `enforce_prompt_budget` priority for anchor sections vs Mode-A sections.
- **OQ-3 — FR-4 strictness.** Block (refuse the feature) on a missing declared anchor vs warn-and-proceed. Interacts with Gap A timing (pre-Gap-A, anchors may legitimately be absent).
- **OQ-4 — Prisma inheritance prompt shape.** Inject the field table as prose, as a synthetic forward-contract, or as a `.d.ts`-style interface? Which yields the most reliable field-name matching?
- **OQ-5 — anchor `file_specs` dependency.** Gap A OQ-5 keeps anchors in `file_specs`; does Mode B read the anchor *contracts* from `file_specs` (elements/imports) or re-extract from disk via `build_upstream_interfaces`? Prefer one source.

---

## 5. Implementation Plan
A companion plan will live at **`docs/design/RUN_009_GAP_B_PLAN.md`** (deferred until Gap A lands — Mode B is untestable without anchors on disk).

---

## Appendix A — Accepted Suggestions
*(empty — populated after CRP triage)*

## Appendix B — Rejected / Narrowed Suggestions (with rationale)
*(empty — populated after CRP triage)*

## Appendix C — Incoming Suggestions (Untriaged, append-only)
*(CRP review rounds append here)*

---

*v0.2 — Post-planning self-reflective update. Key insight: Mode B is mostly reuse (`build_upstream_interfaces` already reads disk + extracts exports; `prisma_parser` yields the field model) — the new logic is anchor *selection* (FR-2), not extraction. Depends on Gap A's `upstream_anchors` (FR-6); plan deferred until Gap A lands (Mode B untestable without anchors on disk). Scope: generation-side pre-existing-upstream inheritance.*
