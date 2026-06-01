# RUN-009 Gap A — Plan-Scope-Aware Seed Emission & Cleanup — Requirements

**Version:** 0.3 (OQs resolved — ready for implementation)
**Date:** 2026-06-01
**Status:** Approved for implementation (no CRP — small conventional plumbing; reflective loop covered the falsification)
**Source incident:** `docs/design/RUN_009_POSTMORTEM.md` Gap A — `run-prime-contractor.sh --fresh` wiped the entire 9-file M1 ship set the plan declared **out of scope / immutable** (`package.json`, `tsconfig.json`, `next.config.mjs`, `.env.example`, `lib/env.ts`, `lib/db.ts`, `prisma/schema.prisma`, `app/layout.tsx`, `app/page.tsx`). 0-of-13 functional delivery; the anchors were never git-tracked, so unrecoverable.
**Scope:** Gap A only — make seed emission + `--fresh` cleanup honor plan-declared immutable/upstream anchors, and make anchors durable. **Gap B (Mode-B inheritance)** is the *consumer* of the same signal and is **out of scope here** (cross-referenced in FR-6).

---

## 0. Planning Insights (Self-Reflective Update)

> The planning pass read `forward_manifest.py` (`ForwardFileSpec`/`ConventionProvenance`), `workflows/builtin/plan_ingestion_workflow.py` (scope extraction), `seeds/builder.py` + `element_deriver.py` (manifest enrichment), and `clean-prior-run.sh`. It falsified two assumptions from the postmortem-derived v0.1 framing:

| v0.1 Assumption | Planning Discovery | Impact |
|-----------------|--------------------|--------|
| "Nothing parses the plan's Non-Goals / out-of-scope" → we must add parsing. | **Plan-ingestion ALREADY extracts it:** `plan_ingestion_workflow.py:541/567` pulls per-feature `negative_scope` ("items the plan LITERALLY says are out of scope") + `scope_boundary`, aggregated into run-level `metadata["negative_scope"]` (`:946`). **But it is free-text *categories* ("Kubernetes manifests"), NOT file paths**, stored as metadata, and **never linked to `file_specs` or `clean-prior-run.sh`.** | **FR-1 reframed:** the gap is *structuring* the out-of-scope signal into **file paths** and *connecting* it to cleanup — not adding Non-Goals parsing. |
| "Add a target-vs-anchor flag to `ForwardFileSpec` (set from a new plan marker)." | `ForwardFileSpec` has `convention_provenance` (provenance precedent) but its `source` is pinned to `"framework-conventions"` — registry origin, **not** a target/anchor role. `file_specs` is a flat `path→spec` dict; **tasks carry no `target_files`** (verified), so cleanup cannot derive "which entries are this batch's regen targets." | **FR-2 reframed:** emit a **separate structured `upstream_anchors` list** in the seed (lower-risk than overloading `file_specs`/`ForwardFileSpec`); a per-spec flag is an alternative (OQ-1). |
| `--fresh` (run-009's seed) wiped the anchors. | run-009's seed `file_specs` had **only the 13 M2/M3 targets** (no anchors); the anchors were wiped by an **earlier** `--fresh` (run-003/004 seeds listed them) and, **never git-tracked**, never restored. | **FR-5 added:** anchor *durability* (git-tracking) is an independent failure axis — the schema fix prevents future wipes; git discipline prevents data loss from already-emitted bad seeds. |

**Resolved open questions (from planning):**
- **"Does the pipeline see the plan's out-of-scope section?" → YES** (`negative_scope`/`scope_boundary`), but unstructured and disconnected. The fix builds on it, not around it.
- **"Is there an existing immutable/scope concept on the file spec?" → NO** usable one (`convention_provenance` is registry-source only). A new structured anchor signal is required.

---

## 1. Problem Statement

The pipeline conflates two kinds of files and treats them identically: **regeneration targets** (files this batch produces) and **pre-existing upstream anchors** (prior-milestone ship-set files the plan declares immutable). `clean-prior-run.sh --fresh` `rm`s every key in the seed's `forward_manifest.file_specs`; the seed has no field marking a path as an anchor; and the plan's out-of-scope declaration — though *captured* at ingestion as free-text `negative_scope` — is never structured into file paths or propagated to cleanup. Result: any incremental batch (M3 on M2, M4 on M3, …) can wipe its own foundation, and because anchors are typically untracked, the loss is unrecoverable. **No multi-batch milestone delivery is possible until this is fixed.**

| Component | Current state | Gap |
|-----------|--------------|-----|
| plan-ingestion scope extraction | extracts free-text `negative_scope`/`scope_boundary` → run-level `metadata` (`plan_ingestion_workflow.py:541,946`) | not file-path-structured; not linked to `file_specs`/cleanup |
| `ForwardFileSpec` | `convention_provenance` (registry source), no target/anchor role (`forward_manifest.py:317`) | cannot mark a path as immutable anchor vs regen target |
| seed `file_specs` | flat `path→spec`; all treated as wipeable targets | no do-not-regenerate subset; tasks carry no `target_files` to derive it |
| `clean-prior-run.sh` | `rm`s every `file_specs` key (two loops, `:87-130`) | no do-not-wipe list honored |
| M1 anchors on disk | never git-tracked (`git ls-files` → none) | wiped = unrecoverable |

---

## 2. Requirements

### FR-1 — Structure the out-of-scope signal into file paths
Plan-ingestion MUST emit a **structured list of immutable/upstream file paths** the plan declares out-of-scope, distinct from the existing free-text `negative_scope` categories. Source options (OQ-2): (a) an explicit plan marker block (e.g. `<!-- cap-dev-pipe: upstream-anchors -->` listing paths), or (b) path-extraction from the plan's Non-Goals/out-of-scope section. The list MUST contain resolvable project-relative paths (`prisma/schema.prisma`, `package.json`, …), not categories.
*Acceptance:* the run-009 `typescript-plan.md` Non-Goals block yields a structured anchor list of the 9 M1 paths; `negative_scope` free-text categories are unaffected.

### FR-2 — Emit a structured `upstream_anchors` set in the seed
The seed-emitter MUST write the FR-1 paths as a **dedicated `upstream_anchors` (do-not-regenerate) field** in the seed artifact — separate from `forward_manifest.file_specs` (lower-risk than overloading the flat path→spec map; per-spec `role` flag is the alternative, OQ-1). Anchor paths MUST NOT appear in the **wipeable** target set.
*Acceptance:* the emitted seed has `upstream_anchors` listing the 9 M1 paths; none of them is treated as a regen target.

### FR-3 — `clean-prior-run.sh` honors the do-not-wipe set
`clean-prior-run.sh --fresh` MUST NOT remove any path in the anchor/do-not-wipe set. It reads the set from the seed (or a sibling artifact emitted alongside it — OQ-3) and skips those paths in both `rm` loops (`:87-130`).
*Acceptance:* re-running `--fresh` against the run-009 seed + anchor list leaves all 9 M1 files on disk untouched; a path not in the set is still cleaned.

### FR-4 — The wipeable set excludes anchors *(reframed v0.3 / OQ-5)*
The `--fresh` wipeable set MUST be **`file_specs` keys − `upstream_anchors`**. Anchors are **NOT removed from `file_specs`** (so Gap-B Mode-B inheritance can read their `elements`/`imports` contracts, FR-6); they are excluded from *wiping*. This is defense-in-depth alongside FR-3: even computing the wipe set from `file_specs` directly, subtracting `upstream_anchors` protects the anchors.
*Acceptance:* the computed wipe set for the run-009 seed contains the 13 M2/M3 targets and **none** of the anchor paths; anchors retain their `file_specs` entries.

### FR-5 — Anchor durability (untracked = unrecoverable)
Because wiped anchors that were never git-committed are unrecoverable, the pipeline MUST make anchor loss recoverable: at minimum **warn loudly when a declared anchor is untracked by git** before any `--fresh` cleanup; ideally the pipeline (or the runbook) ensures anchors are committed. This is an independent backstop to FR-1..FR-4 (which prevent future wipes but don't restore already-lost untracked files).
*Acceptance:* `--fresh` against a seed whose anchor list includes an untracked file emits a clear warning naming the untracked anchor(s); a tracked anchor produces no warning.

### FR-6 — The anchor signal is the shared input for Gap B (Mode-B inheritance) — *cross-reference, out of scope here*
The FR-2 `upstream_anchors` set MUST be defined so that Gap B (Mode-B inheritance — propagating pre-existing-upstream file contents into a feature's design context, per `RUN_009_POSTMORTEM.md` Fix 2) can consume the **same** signal. The files cleanup must NOT wipe (anchors) are exactly the files Mode-B should read from. This requirement only mandates the signal's shape is Gap-B-consumable; **implementing Mode-B inheritance is out of scope** (separate requirements).
*Acceptance:* the `upstream_anchors` schema is documented as the shared contract; a note in the Gap-B requirements references it.

---

## 3. Non-Requirements
- **Does NOT implement Gap B (Mode-B inheritance).** This spec only *emits* the anchor signal Gap B will consume (FR-6).
- **Does NOT change the `forward_manifest.file_specs` schema** if a separate `upstream_anchors` list suffices (OQ-1). The flat path→spec map stays as-is.
- **Does NOT add general plan-section parsing** beyond out-of-scope/anchor file paths.
- **Does NOT alter the default behavior for plans without anchor markers** — those still get full `--fresh` cleanup (FR-3 negative case).
- **Does NOT restore already-lost anchors** — recovery of run-009's wiped ship set is a separate direct-fix task (postmortem §5); FR-5 only prevents future unrecoverable loss.

---

## 4. Open Questions — RESOLVED (v0.3)
- **OQ-1 → RESOLVED: separate seed-level `upstream_anchors: [paths]` list.** Not a `ForwardFileSpec` flag — avoids a frozen-model schema change consumed pipeline-wide; FR-6/Gap-B only needs the path set, and contracts are read from `file_specs` separately (see OQ-5). Lowest blast radius.
- **OQ-2 → RESOLVED: explicit author-controlled source, not LLM extraction.** Anchors come from an explicit list, not fragile prose extraction (`negative_scope` proves prose yields categories, not paths). **Two interoperable sources:** (a) a `.cap-dev-pipe/upstream-anchors.txt` (or `pipeline.env UPSTREAM_ANCHORS`) the author/pipeline maintains — robust, no LLM dependency, protects cleanup immediately; and (b) a plan marker block (`<!-- cap-dev-pipe: upstream-anchors -->`) parsed by ingestion into the seed's `upstream_anchors`. The cleanup guard (FR-3) honors the **union**; (a) is the reliable floor, (b) is the ingestion-driven enrichment.
- **OQ-3 → RESOLVED: cleanup reads the seed JSON `upstream_anchors`** (via the same inline `python3` it already uses to read `file_specs`) **∪ the `.cap-dev-pipe` config source.** One guard, two inputs.
- **OQ-4 → RESOLVED: soft (warn + proceed).** Untracked-anchor → loud warning naming the file(s); do not block `--fresh` (hard-block disrupts iterative dev, and FR-1..FR-4 already prevent the wipe). Durability is a backstop, not a gate.
- **OQ-5 → RESOLVED: anchors REMAIN in `file_specs`; the wipeable set = `file_specs` keys − `upstream_anchors`.** Anchors are not removed from `file_specs` (so Gap-B Mode-B inheritance can read their `elements`/`imports` contracts); they are merely excluded from wiping via the `upstream_anchors` list. This supersedes the v0.2 FR-4 "omit anchors from file_specs" phrasing.

---

## 5. Implementation Plan
A companion plan lives at **`docs/design/RUN_009_GAP_A_PLAN.md`**.

---

## Appendix A — Accepted Suggestions
*(empty — populated after CRP triage)*

## Appendix B — Rejected / Narrowed Suggestions (with rationale)
*(empty — populated after CRP triage)*

## Appendix C — Incoming Suggestions (Untriaged, append-only)
*(CRP review rounds append here)*

---

*v0.2 — Post-planning self-reflective update. Falsified 2 assumptions (Non-Goals IS parsed but unstructured/disconnected; no usable target-vs-anchor field exists — provenance is registry-only). Reframed FR-1 (structure, don't add parsing) + FR-2 (separate `upstream_anchors` list); added FR-5 (anchor git-durability as an independent axis) and FR-6 (shared signal with Gap B). Scope: Gap A seed/cleanup/durability; Gap B inheritance deferred.*
