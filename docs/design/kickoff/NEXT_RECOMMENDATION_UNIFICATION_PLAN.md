# Next-Recommendation Unification — Implementation Plan

**Version:** 0.1
**Date:** 2026-07-02
**Requirements:** `NEXT_RECOMMENDATION_UNIFICATION_REQUIREMENTS.md` (v0.1)
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

### Step 1 — The shared Tier-1 formatter (FR-NU-2)
- In `ranking.py`, add `blocker_cta(readiness: ReadinessView | Mapping | None) -> Optional[NextAction]`:
  extract `next_action`'s current Tier-1 block verbatim (kind=`KIND_BLOCKER`, `title=f"Resolve readiness
  blocker: {section}"`, `detail=consequence|status`). Accept either a `ReadinessView` or the raw
  `{blockers: [...]}` dict (concierge passes a dict) — normalize internally. Returns `None` when there
  are no blockers. Add a `subject` helper `blocker_subject(section) -> str` (normalized slug, e.g.
  `"Data model"`→`"data_model"`) for the agreement test.

### Step 2 — `ranking.next_action` uses it (FR-NU-2)
- Replace the inline Tier-1 block with `cta = blocker_cta(readiness); if cta: return cta`. Behavior
  byte-identical (the extraction is a move, not a change) — `test_chat_and_ranking` stays green.

### Step 3 — Concierge blocker branch uses it (FR-NU-3)
- In `concierge_view._next_action`, the `blockers` branch calls `blocker_cta(readiness)` and returns its
  `.to_dict()` (same `{kind,title,detail}` shape). The `PACKAGE_MISSING`/`PACKAGE_PARTIAL`/`ready`
  branches are unchanged (package-level kinds preserved). Now a readiness blocker reads identically in
  the Concierge view and the `field_states`/serve CTA.

### Step 4 — Subject-level agreement for the playbook (FR-NU-4)
- No behavior change to `build_playbook`. Add a `red_carpet.py` (or advisor) helper
  `playbook_top_subject(state) -> Optional[str]` mapping the playbook rank-1's stage/gate to the same
  subject vocabulary (`data_model`/`app`/`pages`/`views`/…). The agreement is asserted in the test, not
  enforced at runtime (they're different registers).

### Step 5 — Parity / consistency test (FR-NU-5)
- New `tests/unit/kickoff_experience/test_next_recommendation_parity.py`:
  - `blocker_cta` is the **sole** producer of the readiness-blocker CTA (grep-style: `next_action` +
    `concierge_view` blocker branches both route through it — assert via monkeypatching `blocker_cta` and
    seeing both surfaces change).
  - For a schema-absent fixture: `next_action` top subject (`blocker_subject`) == the playbook rank-1
    subject (`playbook_top_subject`) — both `data_model`/`schema`.
  - `next_action` and concierge blocker CTA produce **identical** `{kind,title,detail}` for the same
    readiness.

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
