# Next-Recommendation Unification — Requirements

**Version:** 0.3 (Post-CRP R1)
**Date:** 2026-07-02
**Status:** Draft
**Owner:** neil-the-nowledgeable
**Plan:** `NEXT_RECOMMENDATION_UNIFICATION_PLAN.md`
**Context:** deferred backlog item #5 from `RED_CARPET_ADVISOR_BACKLOG.md`.

> **What this is.** The kickoff experience now has **three** "what should I do next" recommenders that
> can silently disagree. This consolidates them onto **one canonical recommendation model + one shared
> Tier-1 formatter**, so the surfaces agree where they overlap — *without* forcing three legitimately
> different recommenders (field-level, package-level, build-level) to become one function.

---

## 0. Planning Insights (Self-Reflective Update)

> Planning shrank this from a risky type-merge to a **surgical shared-formatter extraction** — the >30%
> revision heuristic firing (the loop working). Two corrections stand out: the unification is a shared
> *formatter*, not a merged *type*; and cross-recommender agreement is at the *subject* level, not
> byte-identical titles.

| v0.1 Assumption | Planning Discovery | Impact |
|-----------------|-------------------|--------|
| Merge `NextAction` + `NextStep` into one type (FR-NU-1) | Different payloads / different consumers (serve, `field_states`, CLI, TUI, `test_chat_and_ranking` pin `NextAction`; the advisor `to_dict` rides `NextStep`). Merging churns both wire shapes for no gain. | **FR-NU-1 reframed → shared FORMATTER, not merged type.** Keep both types distinct. |
| All three agree on an **identical title** (FR-NU-4) | `next_action` emits a *resolve-blocker* CTA; the playbook rank-1 emits a *build-action* step (`"Author the data-model contract"`) — same subject, different register. Identical strings would break the playbook wording. | **FR-NU-4 corrected → agreement at the SUBJECT level** (both reference the data model), verified via a normalization helper. |
| Concierge CTA becomes the canonical type (FR-NU-3) | Concierge has package-level kinds (`instantiate`/`ready`) outside `NextAction`'s set; `test_concierge_mode` pins `["kind"]=="instantiate"`. | **FR-NU-3 narrowed → the concierge *blocker branch* uses the shared formatter**; package branches + dict shape stay. |
| Import-cycle risk (OQ-E) | `ranking.py` imports only readiness/state; advisor + concierge import neither `ranking` nor each other. | **OQ-E → put `blocker_cta` in `ranking.py`** (one-directional, no cycle). |
| Consumers may assert exact key sets (OQ-C/D) | Consumers read only `kind`/`title`/`detail`(/`value_path`); the test pins the section name is *in* the title, not the exact title. | **OQ-C/D → additive-only, keep section in the blocker title** → all green. |

**Resolved open questions:** OQ-A → **don't merge types** (shared formatter). OQ-B → concierge CTA needs
no `value_path`. OQ-C/D → backward-compatible; only additive. OQ-E → formatter in `ranking.py`.

---

## 1. Problem Statement

Three recommenders, three shapes, one shared source they already read (`readiness.blockers`) — but each
formats it differently, so the same underlying gap is phrased inconsistently (or, below Tier-1, points
somewhere else):

| Recommender | Input | Output shape | Surfaces | Tier-1 source |
|-------------|-------|--------------|----------|---------------|
| `ranking.next_action` | `KickoffState` (fields) + `ReadinessView` | `NextAction{kind, title, detail, value_path}` | `field_states` chat tool, `serve.py`, CLI `kickoff chat`, TUI (via serve payload) | `readiness.blockers[0]` |
| `concierge_view._next_action` | `package_state` + `readiness` dict | ad-hoc `dict{kind, title, detail}` | Concierge view (`build_concierge_view`), `tui_concierge` | `(readiness).blockers[0]` |
| `red_carpet_advisor.build_playbook` | `RedCarpetState` (gates) + advisories | `Tuple[NextStep{rank, stage, title, detail, command}]` | Red Carpet advisor (CLI/agent/web/MCP) | unmet gates + cascade advisories (derived from `readiness.blockers`) |

**The drift:** all three consult `readiness.blockers` for their top item, but each **re-phrases** it
independently (`f"Resolve readiness blocker: {section}"` in two places with *different* detail text; the
playbook derives its own wording). And the **types are near-duplicates** (`NextAction` and the concierge
dict differ only in that one is typed; `NextStep` is a superset adding `rank`/`stage`/`command`). A
change to how a readiness blocker should be surfaced must be made in three places, and nothing tests that
they agree.

**What should exist:** one canonical recommendation type, one shared "top blocker → CTA" formatter that
all three use for Tier-1, the concierge CTA returning the canonical type, and a parity test proving the
surfaces agree on the top recommendation for the same project.

---

## 2. Requirements

- **FR-NU-1 — Shared Tier-1 formatter, not a merged type** *(reframed by planning)*. The unification is a
  **shared blocker→CTA formatter**, not a consolidated type. `NextAction` (CTA payload: `kind, title,
  detail, value_path?`) and `NextStep` (playbook payload: `rank, stage, title, detail, command`) stay
  **distinct** — they serve different `to_dict()` wire shapes with different consumers (merging would
  churn both for no gain). What is shared is the *logic that turns a readiness blocker into a CTA*.
- **FR-NU-2 — One shared Tier-1 formatter.** A single function turns the top `readiness.blockers` entry
  into a CTA (title + detail + kind). **The two CTA recommenders — `ranking.next_action` (Tier-1) and the
  `concierge_view._next_action` blocker branch — call it** (CRP R1-F1: the advisor's playbook does **not**
  call it; it agrees at the *subject* level per FR-NU-4, preserving its build-action wording). A readiness
  blocker is thus phrased **identically** across the `field_states`/serve/CLI CTA and the Concierge
  blocker CTA — one place to change the wording. Concierge imports it **module-qualified**
  (`ranking.blocker_cta`), not by name, so the single-source parity monkeypatch is effective (CRP R1-S1).
- **FR-NU-3 — Concierge blocker branch uses the shared formatter** *(narrowed by planning)*. The
  `blockers` branch of `concierge_view._next_action` produces its CTA via the shared formatter. Only the
  **dict shape** (`{kind,title,detail}`) is unchanged; the blocker **`detail` TEXT changes** from the
  fixed `"Fill the kickoff inputs the cascade still needs."` to the blocker's `consequence|status`
  (CRP R1-F3/S3 — a user-visible copy change, note it in the changelog), with a **non-empty fallback**
  guaranteed (FR/plan). Package-level branches (`instantiate`/`ready`) are unchanged. **Precondition
  (CRP R1-F4):** concierge shows the shared blocker CTA only when `package_state == complete`; when the
  package is missing/partial it (correctly) shows `instantiate` and diverges from the ungated
  `field_states`/serve CTA — an expected divergence, so "identical" means *when the same Tier-1 blocker is
  the active recommendation*, not unconditionally.
- **FR-NU-4 — Cross-recommender agreement at the SUBJECT level** *(corrected by planning)*. When the top
  gap is a **readiness blocker AND the schema gate is the top unmet gate** (CRP R1-S5 — the only case they
  coincide), `next_action` and the playbook's rank-1 reference the **same subject** (`data_model`),
  verified via a **shared subject vocabulary** (CRP R1-S2 — one `section→subject` + `stage→subject` table
  both helpers consume, no second hand-rolled map), **not** byte-identical titles (resolve vs
  build-action registers). When rank-1 is not a blocker / there is no unmet gate, the subject helper
  returns `None` and the equality assert is skipped (not falsely matched). A schema-present +
  downstream-blocker fixture legitimately yields **different** subjects.
- **FR-NU-5 — Parity / consistency test.** A test proves: (a) `blocker_cta` is the **sole producer** of
  the readiness-blocker CTA — a monkeypatch of `ranking.blocker_cta` changes **both** surfaces (negative
  control: an un-routed branch must FAIL the test, CRP R1-S1), **plus** a source-scan asserting the literal
  `"Resolve readiness blocker:"` occurs **exactly once** in `kickoff_experience/` (CRP R1-S4); (b) on a
  **schema-absent** fixture, `blocker_subject(next_action) == playbook_top_subject` (both `data_model`);
  (c) *(operationalized, CRP R1-F2 — replaces "no contradictory recommendation")* the concierge blocker
  CTA equals `next_action`'s `{kind,title,detail}` on a package-complete-with-blocker fixture, and a
  schema-present-downstream-blocker fixture yields distinct-but-valid subjects.
- **FR-NU-6 — Backward-compatible serialization.** The `to_dict()` payloads consumed by `serve.py`,
  the `field_states` chat tool, the CLI, and the TUI must not break. New fields are additive; existing
  keys (`kind`/`title`/`detail`/`value_path`) keep their meaning.

---

## 3. Non-Requirements

- **NR-1 — Not one function.** The three recommenders consume different state (fields / package / gates)
  and stay separate functions for their separate surfaces; this unifies the **type + Tier-1 wording**,
  not the call sites.
- **NR-2 — No behavior change below Tier-1.** Field-level fill/review tiers and build-level stage steps
  keep their distinct logic; only the shared readiness-blocker CTA is centralized.
- **NR-3 — No LLM / no new readiness.** Pure `$0` refactor over existing state; no new provisioning
  computation.
- **NR-4 — Not the advisor's playbook redesign.** `build_playbook` keeps its ranked, command-bearing
  shape; only its rank-1 blocker wording is aligned.

---

## 4. Open Questions

*All 5 resolved by planning — see §0.*

- **OQ-A — RESOLVED → don't merge the types.** The unification is a shared formatter; `NextAction` and
  `NextStep` stay distinct (different payloads/consumers).
- **OQ-B — RESOLVED → no.** The concierge CTA is package/stage level; no `value_path`.
- **OQ-C — RESOLVED → backward-compatible.** Consumers read only `kind`/`title`/`detail`(/`value_path`);
  changes are additive and keep the section in the blocker title.
- **OQ-D — RESOLVED.** `test_chat_and_ranking` (kinds/`value_path`/`to_dict` idempotence, section-in-title)
  and `test_concierge_mode` (`["kind"]=="instantiate"`) are preserved by the surgical extraction.
- **OQ-E — RESOLVED → `blocker_cta` lives in `ranking.py`** (imports only readiness/state; advisor +
  concierge import it one-directionally — no cycle).

---

*v0.2 — Post-planning self-reflective update. The headline correction: this is a **shared Tier-1
formatter extraction**, not a type merge (FR-NU-1 reframed), and agreement is **subject-level**, not
identical-title (FR-NU-4 corrected). FR-NU-3 narrowed to the concierge blocker branch. Scope shrank to a
low-risk surgical change: `blocker_cta` in `ranking.py`, consumed by `next_action` (Tier-1) + the
concierge blocker branch, with a subject-level agreement test vs the playbook. All 5 OQs resolved; the
existing suites stay green (backward compat). Ready for CRP review before implementation.*

*v0.3 — Post-CRP R1 (reviewer claude-opus-4-8-1m; 4 F + 6 S, all code-grounded). **Accept all; none
rejected.** Key fixes: the FR-NU-2↔FR-NU-4 contradiction resolved (only the two CTA recommenders call the
formatter; the playbook agrees at subject level — R1-F1); FR-NU-5(c) operationalized (R1-F2); the
concierge blocker `detail` TEXT change + non-empty fallback + `package_state==complete` precondition made
explicit (R1-F3/F4/S3); module-qualified `ranking.blocker_cta` so the monkeypatch bites + a source-scan
sole-producer guard (R1-S1/S4); ONE shared subject vocabulary for both helpers (R1-S2); the agreement
precondition pinned to schema-absent with `None` handling for the non-coincident case (R1-S5); and
`blocker_cta`'s `ReadinessView|Mapping|None` normalization contract incl. the concierge `readiness==None`
path (R1-S6). Dispositions in Appendix A; R1 verbatim in Appendix C. Ready for implementation.*

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

> Triage R1 (orchestrator, 2026-07-02). **All 4 F + 6 S accepted; none rejected** — each grounded in the
> real `ranking.py`/`concierge_view.py`/`red_carpet_advisor.py` + pinned tests.

| ID | Suggestion | Source | Implementation / Validation Notes | Date |
|----|------------|--------|-----------------------------------|------|
| R1-F1 | FR-NU-2 wrongly says the playbook calls the formatter | CRP R1 | FR-NU-2 reworded: only next_action + concierge call it; playbook = subject-level | 2026-07-02 |
| R1-F2 | FR-NU-5(c) "contradictory" untestable | CRP R1 | FR-NU-5(c) replaced with an operational predicate | 2026-07-02 |
| R1-F3 | Concierge blocker detail TEXT changes / can go empty | CRP R1 | FR-NU-3 states shape-only unchanged + non-empty fallback + changelog note | 2026-07-02 |
| R1-F4 | `package_state==complete` precondition unstated | CRP R1 | FR-NU-3 states the precondition + expected divergence | 2026-07-02 |
| R1-S1 | Module-qualified `ranking.blocker_cta` for monkeypatch | CRP R1 | FR-NU-2/5 + plan Step 3/5; negative control | 2026-07-02 |
| R1-S2 | ONE shared subject vocabulary for both helpers | CRP R1 | FR-NU-4 + plan Step 1/4 (shared table) | 2026-07-02 |
| R1-S3 | Non-empty detail fallback + unify missing-section default | CRP R1 | plan Step 1; FR-NU-3 | 2026-07-02 |
| R1-S4 | Source-scan: blocker wording occurs exactly once | CRP R1 | FR-NU-5(a) + plan Step 5 | 2026-07-02 |
| R1-S5 | Pin schema-absent agreement precondition + None handling | CRP R1 | FR-NU-4 + plan Step 4/5 (two fixtures) | 2026-07-02 |
| R1-S6 | `blocker_cta` normalization contract incl None→ready | CRP R1 | plan Step 1/3 | 2026-07-02 |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| *None.* All R1 suggestions were code-grounded and accepted. |  |  |  |  |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — claude-opus-4-8-1m — 2026-07-02

- **Reviewer**: claude-opus-4-8-1m
- **Date**: 2026-07-02 20:45:00 UTC
- **Scope**: Requirements-side review (Feature Requirements) of the shared blocker→CTA formatter — internal consistency of FR-NU-2/3/4/5, testability, and the concierge behavior delta. Grounded in `ranking.py`, `concierge_view.py`, `red_carpet_advisor.py`, and the pinned tests.

**Executive summary**

- FR-NU-2 overclaims: it says the playbook rank-1 "calls" the shared formatter, but FR-NU-4 and plan Step 4 keep the playbook out of it (subject-agreement only). Internal + plan inconsistency.
- FR-NU-5(c) is untestable as worded — "contradictory" is undefined across legitimately different registers.
- FR-NU-3 reads as a pure no-op for concierge, but the concierge blocker `detail` text actually changes (and can go empty).
- "Reads identically in the Concierge view and the `field_states`/serve CTA" omits the `package_state == complete` precondition.

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F1 | Interfaces | high | Reconcile FR-NU-2 with FR-NU-4 and plan Step 4. FR-NU-2 lists `ranking.next_action`, `concierge_view._next_action`, AND "the advisor's playbook rank-1 all call it"; the playbook does NOT call `blocker_cta` (FR-NU-4 + plan Step 4 = subject-agreement only). Reword to: "the two CTA recommenders (`next_action` Tier-1 + concierge blocker branch) call the shared formatter; the playbook agrees at the subject level (FR-NU-4)." | As written FR-NU-2 contradicts FR-NU-4 and the plan. An implementer could route `build_playbook` rank-1 through the formatter, destroying its "Author the data-model contract" build-action wording — the exact register FR-NU-4 protects. | FR-NU-2, sentence "…and the advisor's playbook rank-1 all call it…" | Assert no import of `blocker_cta` in `red_carpet_advisor.py`; playbook rank-1 title stays `"Author the data-model contract"` in `test_red_carpet_advisor`. |
| R1-F2 | Validation | medium | Replace FR-NU-5(c) "no surface emits a contradictory top recommendation" with an operational predicate, e.g. "for a schema-absent fixture, `blocker_subject(next_action) == playbook_top_subject`, and the concierge blocker CTA equals `next_action`'s `{kind,title,detail}`." | "Contradictory" is undefined across a resolve-CTA vs a build-action step (legitimately different registers), so 5(c) is untestable and would be skipped or asserted arbitrarily. | FR-NU-5, bullet (c) | Each clause of the predicate maps to a concrete assertion in the parity test. |

### Stress-test / adversarial pass

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F3 | Risks | medium | FR-NU-3 says the concierge branch "reads identically" with its "`{kind,title,detail}` dict shape … unchanged". State explicitly that only the SHAPE is unchanged; the `detail` TEXT changes from the fixed `"Fill the kickoff inputs the cascade still needs."` to `consequence\|status`, and require a non-empty guarantee (see plan R1-S3). | The requirement reads as a silent refactor; in fact concierge's Tier-1 detail changes for every project and can become empty (`concierge_view.py:83-87` vs `ranking.py:55`). This is a user-visible copy change and belongs in the changelog. | FR-NU-3 ("its `{kind,title,detail}` dict shape are **unchanged**") | Snapshot concierge `next_action.detail` before/after on a package-complete-with-blocker fixture; assert it now equals `next_action`'s and is non-empty. |
| R1-F4 | Architecture | medium | Add the precondition to FR-NU-2/FR-NU-3 that concierge shows the shared blocker CTA only when `package_state == complete`; when missing/partial it (correctly) shows the `instantiate` CTA. Clarify "identical on every surface" means "identical when the same Tier-1 blocker is the active recommendation," not unconditionally. | `concierge_view._next_action` checks `PACKAGE_MISSING`/`PARTIAL` before `blockers`, so serve/`field_states` (no package gate) and concierge diverge whenever the package is incomplete — an expected divergence the requirement should acknowledge so the parity test doesn't over-assert. | FR-NU-2 / FR-NU-3 ("reads identically in the Concierge view and the `field_states`/serve CTA") | package-missing → concierge `kind=="instantiate"` while `next_action kind=="resolve_blocker"`; package-complete-with-blocker → both identical. |

**Endorsements**: none (R1 — no prior untriaged suggestions).

**Disagreements**: none (R1).
