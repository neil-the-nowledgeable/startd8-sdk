# Next-Recommendation Unification — Requirements

**Version:** 0.2 (Post-planning — self-reflective update)
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
  into a CTA (title + detail + kind). `ranking.next_action` (Tier-1), `concierge_view._next_action`, and
  the advisor's playbook rank-1 all call it, so a readiness blocker is phrased **identically** on every
  surface. One place to change the wording.
- **FR-NU-3 — Concierge blocker branch uses the shared formatter** *(narrowed by planning)*. The
  `blockers` branch of `concierge_view._next_action` produces its CTA via the shared formatter (so a
  readiness blocker reads identically in the Concierge view and the `field_states`/serve CTA). Its
  package-level branches (`instantiate`/`ready`, kinds outside `NextAction`'s set) and its
  `{kind,title,detail}` dict shape are **unchanged**.
- **FR-NU-4 — Cross-recommender agreement at the SUBJECT level** *(corrected by planning)*. When both a
  `KickoffState` and a `RedCarpetState` are computable and the top gap is a **readiness blocker**,
  `next_action` and the playbook's rank-1 reference the **same subject** (e.g. both the data model) —
  verified via a normalization helper, **not** byte-identical titles (the CTA uses *resolve* wording, the
  playbook uses *build-action* wording — legitimately different registers). Below Tier-1 they may differ.
- **FR-NU-5 — Parity / consistency test.** A test proves: (a) the shared formatter is the sole producer
  of the readiness-blocker CTA; (b) `next_action` and playbook rank-1 agree on the top blocker for a
  fixture project; (c) no surface emits a contradictory top recommendation.
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
