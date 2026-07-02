# Next-Recommendation Unification — Implementation Plan

**Version:** 0.2 (Post-CRP R1)
**Date:** 2026-07-02
**Requirements:** `NEXT_RECOMMENDATION_UNIFICATION_REQUIREMENTS.md` (v0.3)
**Branch:** `feat/red-carpet-next-unification` (worktree off `origin/main`).

---

## Planning discoveries (feed the reflection pass)

| What v0.1 assumed | What planning (code read) revealed | Impact |
|-------------------|-----------------------------------|--------|
| Consolidate `NextAction` + `NextStep` into one type (FR-NU-1) | They serve **different payloads** with **different consumers**: `NextAction.to_dict()` (`kind/title/detail/value_path`) is read by `serve`, the `field_states` tool, CLI (`na['title']`), TUI (`na['title']`+`na['detail']`), and pinned by `test_chat_and_ranking` (`.kind`==KIND_*, `.value_path`, `.to_dict()`); `NextStep` (`rank/stage/command`) rides the advisor's `to_dict()`. Merging adds a pile of optional fields and **churns both wire shapes** for no functional gain. | **FR-NU-1 reframed: the unification is a shared FORMATTER, not a merged TYPE.** Keep `NextAction` and `NextStep` distinct (correct abstraction); share the Tier-1 blocker→CTA logic. |
| All three should agree on an **identical title** for the top blocker (FR-NU-4) | `next_action` blocker title = `"Resolve readiness blocker: {section}"` (a *resolve* CTA); the playbook rank-1 for the same schema-absent project = `"Author the data-model contract"` (a *build-action* step). Same **subject** (the data model), legitimately **different register**. Forcing identical strings would break the playbook's action wording. | **FR-NU-4 corrected: agreement is at the SUBJECT level, not byte-identical titles.** The two *CTA* recommenders (`next_action` + concierge) share wording via the formatter; the playbook agrees on *subject*, tested via a small normalization. |
| Concierge CTA becomes the canonical type (FR-NU-3) | Concierge has **package-level kinds** (`instantiate`/`ready`) outside `NextAction`'s `KIND_*` set, and `test_concierge_mode` reads `view["next_action"]["kind"] == "instantiate"`. | **FR-NU-3 narrowed:** the concierge **blocker branch** uses the shared formatter (matching wording); its package-level branches + `{kind,title,detail}` dict shape stay. |
| Import-cycle risk for a shared formatter (OQ-E) | `ranking.py` imports only `.readiness` + `.state`; `red_carpet_advisor.py` and `concierge_view.py` import neither each other nor `ranking`. A formatter in `ranking.py` is importable by both **one-directionally** — no cycle. | **OQ-E resolved:** put `blocker_cta` in `ranking.py`. |
| Consumers might assert an exact key set (OQ-C/D) | Consumers read only `kind`/`title`/`detail`(/`value_path`); `test_chat_and_ranking` pins `.kind`/`.value_path`/`.to_dict()` idempotence and that the section name is *in* the title (`"Data model" in action.title`). | Additive-only + keep the section in the blocker title → all green. **OQ-C/D resolved.** |

**Net:** the loop shrank the change from a risky type-merge to a **small, surgical shared-formatter extraction** (the >30% revision heuristic firing = the loop working).

---

## Approach & step map

### Step 1 — The shared Tier-1 formatter + subject vocabulary (FR-NU-2, CRP R1-S2/S3/S6)
- In `ranking.py`, add `blocker_cta(readiness) -> Optional[NextAction]`:
  - **Normalization contract (R1-S6):** accepts a `ReadinessView` (`.blockers` tuple of Mapping), a raw
    `{"blockers": [...]}` Mapping, **or `None`**; returns `None` for `None`/empty-blockers (callers map
    `None → their "ready"/no-blocker branch`, never crash). `build_concierge_view` passes `readiness=None`
    on its `build_readiness(...)` exception path — must not `AttributeError`.
  - Body = `next_action`'s current Tier-1 (kind=`KIND_BLOCKER`, `title=f"Resolve readiness blocker:
    {section}"`).
  - **Non-empty detail (R1-S3):** `detail = consequence | status | <generic fallback>` — reuse concierge's
    current `"Fill the kickoff inputs the cascade still needs."` when both are empty (concierge never shows
    a blank detail today). Unify the missing-`section` default to `"unknown"`.
- **Shared subject vocabulary (R1-S2):** module-level constants + a single `section→subject` table AND a
  `stage→subject` table in `ranking.py`. `blocker_subject(section) -> str|None` and (Step 4)
  `playbook_top_subject` both consume **this one table** — no second hand-rolled map. A table-driven test
  fails if a subject constant is duplicated across the two helpers.

### Step 2 — `ranking.next_action` uses it (FR-NU-2)
- Replace the inline Tier-1 block with `cta = blocker_cta(readiness); if cta: return cta`. Behavior
  byte-identical (the extraction is a move, not a change) — `test_chat_and_ranking` stays green.

### Step 3 — Concierge blocker branch uses it (FR-NU-3, CRP R1-S1/S6/F3)
- In `concierge_view._next_action`, the `blockers` branch calls **`ranking.blocker_cta(readiness)`
  module-qualified** (NOT `from .ranking import blocker_cta`) so the parity monkeypatch of
  `ranking.blocker_cta` bites (R1-S1). Return its `.to_dict()` (same `{kind,title,detail}` shape). When
  `readiness is None` (the `build_readiness` exception path) `blocker_cta` returns `None` → fall through to
  the `ready` branch (R1-S6), never crash. `PACKAGE_MISSING`/`PACKAGE_PARTIAL`/`ready` branches unchanged.
- **Copy change (R1-F3/S3):** the blocker `detail` now reads `consequence|status` (non-empty fallback),
  replacing the fixed string — note it in the PR/changelog (user-visible).

### Step 4 — Subject-level agreement for the playbook (FR-NU-4, CRP R1-S2/S5)
- No behavior change to `build_playbook`. Add `playbook_top_subject(state) -> Optional[str]` (in
  `red_carpet.py`, importing the **shared `stage→subject` table from `ranking.py`** — R1-S2) that maps the
  playbook rank-1's stage/gate to a subject. **Returns `None`** when there is no unmet gate / rank-1 is not
  a blocker-derived step (R1-S5) — the agreement assert is then skipped, not falsely matched.
- The playbook does **not** call `blocker_cta` (a test asserts `red_carpet_advisor.py` does not import it,
  and rank-1 title stays `"Author the data-model contract"` — R1-F1).

### Step 5 — Parity / consistency test (FR-NU-5, CRP R1-S1/S4/S5/F2)
- New `tests/unit/kickoff_experience/test_next_recommendation_parity.py`:
  - **Sole producer (R1-S1 + R1-S4):** monkeypatch `ranking.blocker_cta` to a sentinel → assert **both**
    `next_action` and the concierge blocker CTA reflect it (negative control: if either branch doesn't
    route through it, the test FAILS). **Plus** a source-scan asserting the literal `"Resolve readiness
    blocker:"` occurs **exactly once** in `src/startd8/kickoff_experience/` (catches a future 3rd copy the
    monkeypatch can't see).
  - **Agreement (R1-S5):** two fixtures — (a) **schema-absent** → `blocker_subject(next_action) ==
    playbook_top_subject` (both `data_model`); (b) **schema-present + downstream blocker** → the helpers
    return **distinct** subjects (assert they MAY differ; no false match) / `playbook_top_subject` handles
    the non-blocker rank-1.
  - **Concierge parity (R1-F2 operational predicate):** on a **package-complete-with-blocker** fixture the
    concierge blocker CTA `{kind,title,detail}` == `next_action`'s, and both details are **non-empty**;
    on **package-missing** the concierge CTA is `instantiate` (expected divergence, R1-F4).
  - **No-import guard (R1-F1):** `blocker_cta` not imported in `red_carpet_advisor.py`.

### Step 6 — Regression sweep
- Run `tests/unit/kickoff_experience/` — especially `test_chat_and_ranking`, `test_concierge_mode`,
  `test_serve_and_cli`, `test_red_carpet_advisor`. All must stay green (FR-NU-6 backward compat).

---

## §7 Validation Strategy
- **No-behavior-change proof:** `test_chat_and_ranking` (the existing Tier-1/2/3/done + to_dict
  idempotence tests) passes unchanged — the extraction is a pure move.
- **Single-source proof:** monkeypatch `blocker_cta` → both `next_action` and the concierge CTA reflect
  the patch (proves neither re-implements the wording).
- **Agreement proof:** subject match between `next_action` and playbook rank-1 on a fixture.
- **Backward-compat:** the full `kickoff_experience` suite stays green.

## Risks
- **R1 — Import cycle** if the formatter is misplaced. Mitigation: it lives in `ranking.py` (imports only
  readiness/state); advisor/concierge import it one-directionally. A smoke import test guards it.
- **R2 — Over-reach back into a type merge.** Mitigation: NR-1/the reframed FR-NU-1 — types stay distinct;
  this PR only shares the Tier-1 formatter + a subject helper.
- **R3 — Patch-where-looked-up (repo gotcha).** The single-source monkeypatch no-ops if concierge binds
  `blocker_cta` at import. Mitigation: concierge calls `ranking.blocker_cta` module-qualified (R1-S1) + a
  source-scan guard (R1-S4).
- **R4 — Two subject crosswalks drift.** Mitigation: one shared `section→subject`/`stage→subject` table
  both helpers consume (R1-S2); a table-driven test.

---

*v0.2 — Post-CRP R1 (all 4 F + 6 S accepted). Hardened: module-qualified `ranking.blocker_cta` +
source-scan sole-producer proof (R1-S1/S4), one shared subject vocabulary (R1-S2), non-empty detail
fallback + missing-section default (R1-S3), pinned schema-absent agreement precondition + `None` handling
(R1-S5), the `ReadinessView|Mapping|None` normalization contract incl. concierge `readiness==None`
(R1-S6), and the no-playbook-call guard (R1-F1). Dispositions in Appendix A; R1 in Appendix C.*

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

> Triage R1 (orchestrator, 2026-07-02). **All 6 S accepted; none rejected.** (F-side dispositions in the
> requirements doc Appendix A.)

| ID | Suggestion | Source | Implementation / Validation Notes | Date |
|----|------------|--------|-----------------------------------|------|
| R1-S1 | Module-qualified `ranking.blocker_cta` so the monkeypatch bites | CRP R1 | Step 3 + Step 5 (negative control) | 2026-07-02 |
| R1-S2 | ONE shared subject vocabulary for both helpers | CRP R1 | Step 1 (tables) + Step 4; table-driven test | 2026-07-02 |
| R1-S3 | Non-empty detail fallback + unify missing-section default | CRP R1 | Step 1; Step 3 copy-change note | 2026-07-02 |
| R1-S4 | Source-scan: blocker wording occurs exactly once | CRP R1 | Step 5 | 2026-07-02 |
| R1-S5 | Pin schema-absent precondition + `None` handling; 2 fixtures | CRP R1 | Step 4 + Step 5 | 2026-07-02 |
| R1-S6 | `blocker_cta` normalization contract incl `None`→ready | CRP R1 | Step 1 + Step 3 | 2026-07-02 |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| *None.* All R1 plan suggestions were code-grounded and accepted. |  |  |  |  |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — claude-opus-4-8-1m — 2026-07-02

- **Reviewer**: claude-opus-4-8-1m
- **Date**: 2026-07-02 20:45:00 UTC
- **Scope**: Dual-document review of the shared blocker→CTA formatter extraction — correctness of the move, subject-level agreement design, backward-compat of `to_dict`, import-cycle safety, and whether the parity test actually proves single-source-of-truth. Grounded in `ranking.py`, `concierge_view.py`, `red_carpet_advisor.py`, `readiness.py`, and the pinned `test_chat_and_ranking` / `test_concierge_mode`.

**Executive summary**

- FR-NU-2 ("`ranking.next_action`, `concierge_view._next_action`, **and** the advisor's playbook rank-1 all call it") contradicts plan Step 4 + FR-NU-4, which keep the playbook OUT of the formatter (subject-agreement only). Top dual-doc inconsistency.
- The single-source monkeypatch proof (Step 5) silently no-ops unless concierge invokes `ranking.blocker_cta(...)` module-qualified — the repo's own patch-where-looked-up gotcha. The parity test can pass while proving nothing.
- `blocker_subject` (section-strings) and `playbook_top_subject` (stages) are two independent crosswalks; if each hand-rolls its own mapping they can drift, re-creating the "disagree in N places" problem one layer lower and untested between them.
- The extraction is NOT byte-identical for concierge: its blocker `detail` changes from the fixed `"Fill the kickoff inputs the cascade still needs."` to `consequence|status` (which can be `""`), and its missing-`section` default changes `"" → "unknown"`. Shape preserved; content changes.
- `blocker_cta` can emit an empty `detail`; concierge today never shows a blank detail. Needs a non-empty fallback.
- FR-NU-4 subject agreement only holds when the top unmet gate is the schema gate; `next_action` Tier-1 (`readiness.blockers[0]`) and `build_playbook` rank-1 (`unmet_gates`, schema-first) are different derivations that can point at different subjects. Pin the fixture precondition; handle `playbook_top_subject == None`.
- Concierge gates the blocker CTA behind `package_state == complete` (`_next_action` checks MISSING/PARTIAL first), so "reads identically on every surface" has an unstated precondition.
- FR-NU-5(c) "no surface emits a contradictory top recommendation" is untestable as worded (registers legitimately differ) — needs an operational predicate.
- `blocker_cta`'s `ReadinessView | Mapping | None` union needs an explicit normalization contract; `build_concierge_view` passes `readiness = None` on the `build_readiness(...)` exception path.
- A cheap source-scan guard (`"Resolve readiness blocker:"` occurs exactly once) is a stronger sole-producer proof than a single-call-site monkeypatch.

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-S1 | Validation | high | Require Step 5 to have `concierge_view._next_action` call the formatter as `ranking.blocker_cta(...)` (module-qualified), NOT `from .ranking import blocker_cta`; the parity test monkeypatches `ranking.blocker_cta` and asserts the patched sentinel appears in BOTH surfaces (fail if either is unchanged). | The single-source proof is a monkeypatch; if concierge binds the name at import, patching `ranking.blocker_cta` no-ops and the test passes while concierge still re-implements the wording — the exact patch-where-looked-up hazard in this repo's CLAUDE.md. | Step 5, bullet "grep-style … assert via monkeypatching `blocker_cta`" | Negative control: an un-routed concierge branch must make the parity test FAIL. |
| R1-S2 | Architecture | high | Define ONE shared subject vocabulary (module-level constants + a `section→subject` and `stage→subject` table) that both `blocker_subject` (Step 1) and `playbook_top_subject` (Step 4) consume; forbid a second hand-rolled mapping. | Step 1 and Step 4 each normalize "to the same subject vocabulary" independently. Two crosswalks re-create the very drift this change exists to kill, one layer lower and untested between them. | Step 1 (`blocker_subject`) + Step 4 (`playbook_top_subject`) | Table-driven test over every emittable `section` and playbook stage; a test fails if a subject constant is duplicated across the two helpers. |
| R1-S3 | Risks | medium | In Step 1 give `blocker_cta` a non-empty `detail` fallback (reuse the concierge's current generic string when `consequence`/`status` are both empty) and unify the missing-`section` default to `"unknown"`; in Step 3, call out that the concierge blocker `detail` TEXT changes. | `next_action` detail can be `""` (both keys absent, `ranking.py:55`) and concierge's section default is `""` vs ranking's `"unknown"`. Step 3 is billed as "same `{kind,title,detail}` shape … unchanged", but shape ≠ content: concierge's detail changes and can go blank — a silent UX regression. | Step 1 (`detail=consequence\|status`) + Step 3 ("same `{kind,title,detail}` shape") | Fixture: blocker lacking both consequence+status → assert both surfaces render a non-empty detail. |

### Stress-test / adversarial pass

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-S4 | Validation | medium | Add a source-scan (grep/AST) guard to Step 5 asserting the literal `"Resolve readiness blocker:"` occurs exactly once in `kickoff_experience/` (inside `blocker_cta`). | Monkeypatching one call site (R1-S1) proves routing but not that no third copy of the wording survives; a static guard catches a future re-introduction the monkeypatch cannot see. | Step 5 (parity test) | CI test greps the package tree; fails if the count != 1. |
| R1-S5 | Risks | high | Pin the agreement-test precondition in Step 4/Step 5: the fixture must be schema-absent so `next_action` Tier-1 and `build_playbook` rank-1 both resolve to `data_model`; specify `playbook_top_subject`'s return when there is no unmet gate / rank-1 is not a blocker (`None`), and skip/xfail the subject-equality assert in that case rather than asserting a false match. | `next_action` Tier-1 keys on `readiness.blockers[0]`; playbook rank-1 keys on `unmet_gates` (schema-gate-first, `red_carpet_advisor.py:458`). They coincide only when the schema gate is the top unmet gate. A schema-present + downstream-blocker fixture makes rank-1 an app/pages step while Tier-1 is the readiness blocker — the "same subject" assert is false in general. | Step 4 (`playbook_top_subject`) + Step 5 bullet 2 | Two fixtures: schema-absent (subjects equal) and schema-present-downstream-blocker (helpers return distinct subjects → assert they MAY differ). |
| R1-S6 | Interfaces | medium | Specify `blocker_cta`'s normalization contract in Step 1: accepts `ReadinessView` (`.blockers` tuple of Mapping), a raw `{"blockers":[...]}` Mapping, or `None`; returns `None` for None/empty; document that `build_concierge_view` passes `readiness == None` on the `build_readiness(...)` exception path, so the concierge blocker branch must map `None → the "ready" branch`, not crash. | Step 1 lists the union type but not the None/empty semantics; concierge already has a `try/except → readiness=None` path (`concierge_view.py:114-117`). Without an explicit contract the integration can `AttributeError` on `.blockers` vs `["blockers"]`. | Step 1 (signature) + Step 3 (concierge integration) | Unit-test `blocker_cta` with `ReadinessView`, dict, `None`, empty-blockers; assert concierge renders "ready" when readiness is `None`. |

**Endorsements**: none (R1 — no prior untriaged suggestions).

**Disagreements**: none (R1).

## Requirements Coverage Matrix — R1

| Requirement | Plan Step(s) | Coverage | Gaps |
| ---- | ---- | ---- | ---- |
| FR-NU-1 — shared formatter, not merged type | Step 1/2, Risk R2 | Full | Types stay distinct; extraction is a move. |
| FR-NU-2 — one shared Tier-1 formatter (who calls it) | Steps 1–3 | Partial | FR-NU-2 says all three "call it"; plan routes only two (next_action + concierge). Playbook agrees at subject level, does not call the formatter — see R1-F1. |
| FR-NU-3 — concierge blocker branch uses formatter | Step 3 | Partial | Detail TEXT change + `package_state==complete` precondition unstated; empty-detail risk — R1-F3/F4/S3. |
| FR-NU-4 — subject-level agreement | Step 4 | Partial | Single-source subject vocabulary (R1-S2) + fixture precondition / `None` handling (R1-S5) missing. |
| FR-NU-5 — parity / consistency test | Step 5 | Partial | Monkeypatch-where-looked-up (R1-S1), sole-producer grep guard (R1-S4), 5(c) untestable (R1-F2). |
| FR-NU-6 — backward-compatible serialization | Step 2, Step 6 | Full | `to_dict` `{kind,title,detail(,value_path)}` preserved; regression sweep covers serve/CLI/TUI. |
| NR-1..NR-4 — non-requirements | Risk R2, Steps 1–4 | Full | Types distinct; call sites separate; playbook shape preserved. |
