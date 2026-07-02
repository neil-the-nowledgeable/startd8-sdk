# Red Carpet Prescriptive Advisor — Enhancement Backlog

**Date:** 2026-07-02
**Owner:** neil-the-nowledgeable
**Specs:** `RED_CARPET_PRESCRIPTIVE_ADVISOR_REQUIREMENTS.md` / `_PLAN.md`
**Purpose:** track the enhancement ideas surfaced by the post-implementation value review, their
status, and which batch each lands in. All stay inside the advisor's boundaries: `$0`/read-only/
advisory-only, pure projection (P1), never a gate (P3).

---

## Status legend

- ✅ **Shipped** — implemented + tested on `feat/red-carpet-advisor`.
- 🎯 **Batch 2** — the next batch (this cycle): requirements FR-RCA-18..23.
- 🕰 **Backlog** — deferred; each notes why + the trigger to pick it up.

---

## Shipped (do-now batch #1–#4 — FR-RCA-14..17)

| Item | FR | Status |
|------|-----|--------|
| Richer schema-shape insights (no-PK, likely-FK-without-relation, empty-enum) | FR-RCA-14 | ✅ |
| `startd8 kickoff red-carpet --check` (advisory CI exit code) | FR-RCA-15 | ✅ |
| Advisory telemetry summary (`red_carpet_advice`, bounded counts) | FR-RCA-16 | ✅ |
| Payload `schema_version` + stable advisory `code` | FR-RCA-17 | ✅ |
| *(bonus)* Curated kind-priority sort + same-consequence cascade collapse | — | ✅ |

> Note: "missing `createdAt`/`updatedAt`" from the original idea was **dropped** as too noisy (many
> models legitimately lack audit timestamps); the high-signal three (no-PK / likely-FK / empty-enum)
> shipped instead.

---

## Batch 2 — Sharper, consistent guidance (this cycle) 🎯

Theme: make the guidance the end user *feels* sharper, and prove the four surfaces stay consistent.
All Small except where noted. Requirements: **FR-RCA-18..23** (see the requirements doc §I).

| # | Item | Value | Effort | FR |
|---|------|-------|--------|-----|
| B2-1 | **Specific remediation for value-input gaps** — name the exact fields to fill (from the kickoff config's `writable_fields()` grouped by domain), not just "author it" | end-user | S–M | FR-RCA-18 |
| B2-2 | **Never cap out the headline schema insight** — reserve one top-N slot for the highest-severity schema-shape advisory so a wall of cascade-blockers can't bury "no data model yet" / islands | end-user | S | FR-RCA-19 |
| B2-3 | **Weave the wireframe preview into the run step** — put entity/page/view counts (already fetched) into the "Run the $0 cascade" next-step detail | end-user | S | FR-RCA-20 |
| B2-4 | **Proactive REPL banner** — seed the agent loop's turn-0 banner with the top insight + top next step (via `reflection_text`) instead of a silent prompt | end-user | S | FR-RCA-21 |
| B2-5 | **`--json` summary header** — a bounded `summary {errors, warns, infos, next_steps}` block for scripting/CI (complements `--check`) | functional | S | FR-RCA-22 |
| B2-6 | **Cross-surface parity test** — assert CLI panel / `/red-carpet.json` / chat tool / MCP tool all derive from one `to_dict()` (guards FR-RCA-4's "one source of truth") | operational | S | FR-RCA-23 |

---

## Backlog (deferred) 🕰

| Item | Why deferred | Trigger to pick up |
|------|--------------|--------------------|
| **#5 — Unify `next_action` ↔ `next_steps`** | There are **two** recommenders with **different inputs**: `ranking.next_action` (per-field `KickoffState`, surfaced in `field_states`/`concierge_view`/`serve`/TUI) and our gate-based `next_steps` playbook. A true merge is semantically subtle (field-level vs build-level) and **M** effort — it deserves its **own reflective-requirements + CRP cycle**, not a quick bundle, to avoid forcing two legitimately-different recommenders to be equal. Batch 2 adds the **parity test** (B2-6) which at least guards the surfaces that *do* share `to_dict()`. | Its own cycle after Batch 2; or a bug report showing the two recommenders disagreeing in a way that confuses users. |
| **Typed contract for advisory kinds/severity** (Keiyaku-style enum shared by CLI/web/MCP/tests) | Refactor, not a feature; the string constants + closed-set coverage test already prevent most drift. | When a 2nd consumer hardens against the stringly-typed kinds, or a Keiyaku sweep of `kickoff_experience/`. |
| **Register the capability** (`/capability-index` → manifest + agent card + MCP-tools artifact) | Skill-driven task (belongs to the `/capability-index` workflow), not advisor code. Genuinely important for **discoverability** of the new advisor + `startd8_red_carpet_state` MCP tool. | Run `/capability-index` once Batch 2 lands and the branch merges. |
| **Golden-snapshot test on a realistic multi-model fixture** (`tests/fixtures/wireframe/.startd8/`) | Test hygiene; the current unit + integration tests already lock behavior per-derivation. | When the advisor output shape stabilizes post-Batch-2. |
| **Memoize the per-turn scan** (`build_assess` + `parse_prisma_schema` cached by schema/inputs mtime) | Perf optimization; the `PerfSample`/`over_budget` signal exists but no real freeze has been observed yet. | A measured `over_budget` on a large real schema, or the web rail refresh becoming a hotspot. |

---

## Ordering rationale

Batch 2 is the **end-user-value cluster + the parity guard** — cohesive, low-risk, mostly Small, and
directly advances the stated goal ("improve value to the end user"). The one **M**/architectural item
(#5 unification) is deferred to its own reflective+CRP cycle precisely because it is subtle enough to
warrant the full loop rather than a quick bundle. Capability-index registration is a separate
skill-driven step to run once the branch merges.
