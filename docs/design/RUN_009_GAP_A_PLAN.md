# RUN-009 Gap A — Plan-Scope-Aware Seed Emission & Cleanup — Implementation Plan

**Version:** 0.3 (OQs resolved; cleanup-side implemented)
**Date:** 2026-06-01
**Status:** Cleanup guard SHIPPED (FR-3/FR-5 + config-source FR-2a); SDK seed-emission (FR-1/FR-2b) remaining
**Requirements:** `docs/design/RUN_009_GAP_A_REQUIREMENTS.md` (v0.3 — FR-1..FR-6)

> **Implementation status (2026-06-01).** The **protective core is shipped**: `clean-prior-run.sh` now honors a do-not-wipe anchor set (union of seed `upstream_anchors` ∪ `$PROJECT_ROOT/.cap-dev-pipe/upstream-anchors.txt` ∪ `UPSTREAM_ANCHORS` env) and warns on untracked anchors (FR-3 + FR-5). Validated: anchor preserved, target wiped, untracked-warning fires only when untracked. A `.cap-dev-pipe/upstream-anchors.txt` listing the 9 M1 anchors was created in the strtd8 project — so the next `--fresh` protects them (once restored + committed, FR-5). **Remaining:** the SDK plan-ingestion marker-block parse → seed `upstream_anchors` (FR-1/FR-2b); the config-file floor makes this non-urgent.

Every FR maps to a step; every step traces to an FR. Smallest-blast-radius-first. Spans the SDK (plan-ingestion + seed-emitter) and cap-dev-pipe (`clean-prior-run.sh`).

---

## Steps

| # | Step | FR | Files | Verify |
|---|------|----|-------|--------|
| **0 ✅ DONE** | **Discovery** — `negative_scope`/`scope_boundary` already extracted (free-text, run-level, unstructured); `ForwardFileSpec` has no target/anchor role; tasks carry no `target_files`; anchors untracked. See requirements §0. | — | (read-only) | ✅ captured |
| **1** | **Anchor source + structured extraction** (FR-1). Define an explicit plan marker block (`<!-- cap-dev-pipe: upstream-anchors -->` listing project-relative paths; OQ-2) and have plan-ingestion parse it into a structured **anchor-path list** (separate from free-text `negative_scope`). | FR-1 | `workflows/builtin/plan_ingestion_workflow.py` (scope extraction ~:541/:946) | unit: run-009 `typescript-plan.md` marker → list of the 9 M1 paths; no marker → empty list |
| **2** | **Seed emits `upstream_anchors`** (FR-2, FR-4). Seed-emitter writes the FR-1 paths as a dedicated `upstream_anchors` seed field; ensures none appears in the wipeable target/`file_specs`-derived set. | FR-2, FR-4 | `seeds/builder.py` + seed schema/emitter | unit: emitted seed has `upstream_anchors` = 9 paths; assert no anchor path in the wipeable target list |
| **3** | **`clean-prior-run.sh` honors do-not-wipe** (FR-3). Read anchors from the seed JSON (or sibling `do-not-wipe.txt`; OQ-3); skip them in both `rm` loops (`:87-130`). **Co-land with Step 2.** | FR-3 | `~/Documents/dev/cap-dev-pipe/clean-prior-run.sh` | integration: `--fresh` on run-009 seed + anchors → all 9 M1 files survive; a non-anchor path still removed |
| **4** | **Anchor durability warning** (FR-5). Before `--fresh` cleanup, `git ls-files` each declared anchor; warn loudly (or block per OQ-4) on any untracked anchor. | FR-5 | `clean-prior-run.sh` (or `run-prime-contractor.sh`) | unit: untracked anchor → warning naming it; tracked → silent |
| **5** | **Document the shared signal for Gap B** (FR-6). Spec the `upstream_anchors` schema as the contract Mode-B inheritance consumes; reference from the (future) Gap-B requirements. Doc-only. | FR-6 | `RUN_009_GAP_A_REQUIREMENTS.md` §FR-6 + Gap-B reqs stub | doc cross-reference present; schema stable |
| **6** | **Regression** — reproduce run-009: `typescript-plan.md` Non-Goals + `--fresh` → 9 M1 files survive; negative test: plan with no marker → full cleanup unchanged. | FR-1..FR-4 | `tests/...` + a cap-dev-pipe fixture | end-to-end: anchors survive `--fresh`; no-marker plan behaves as today |

**Co-landing constraint:** Steps 2 + 3 MUST co-land — emitting `upstream_anchors` without `clean-prior-run` honoring it changes nothing; honoring without emission has no input. Step 1 feeds 2; 4/5/6 follow.

**Cross-repo note:** Steps 1–2 + 6 are SDK; Steps 3–4 are cap-dev-pipe. The seed is the integration contract — define the `upstream_anchors` field once (Step 2) and both repos key off it. Mirrors the RUN-008 ts-verify-gate split (SDK capability + cap-dev-pipe consumer).

**Alignment:** the `upstream_anchors` signal is the shared input for Gap B (Mode-B inheritance) — build it once here, consume it there (FR-6). Same don't-build-twice discipline as RUN-008 OQ-6.

---

## Step 0 — Discovery Findings
See `RUN_009_GAP_A_REQUIREMENTS.md` §0. Net: no blocker. The out-of-scope signal already exists at ingestion (`negative_scope`) but is unstructured/disconnected; the work is structuring it into paths + a dedicated seed field + a cleanup guard + a durability warning. Lowest-risk shape: separate `upstream_anchors` list (not a `ForwardFileSpec` schema change) — pending OQ-1.

---

## Appendix A — Accepted Suggestions
*(empty — populated after CRP triage)*

## Appendix B — Rejected / Narrowed Suggestions (with rationale)
*(empty — populated after CRP triage)*

## Appendix C — Incoming Suggestions (Untriaged, append-only)
*(CRP review rounds append here)*
