# strtd8 Deterministic-First Build — Review for the startd8-sdk Team

**Date:** 2026-06-03 · **Author:** strtd8 build session (Claude) · **Audience:** startd8-sdk maintainers
**Status:** For review — part status report, part design-rationale, with a decision agenda (§3)
**Repos:** consuming app `strtd8` (Python rebuild) · SDK `startd8-sdk`

---

## BLUF

This session built strtd8's **deterministic Pillar-1 "value loop"** by hand and authored the **P2 slice**
as a cap-dev-pipe input. Along the way it **fixed one real SDK generator bug** (the AI edge-schema /
`_persist` datetime crash) and surfaced a coherent set of SDK gaps worth the team's decision: **the SDK
emits the spine + AI passes but not the owned deterministic *views*** (we hand-authored them as the
documented R2-S1 fallback), the **owned/authored composition seam is not regen-safe**, and **two shipped
generators are placeholders** (completeness, export). We want the team's call on whether/how the SDK
should generate these, and how the **no-LLM / micro-prime / large-model** strategy + semantic validation
should encompass them. None of this blocks strtd8 today — it informs SDK roadmap.

---

## 1. The one SDK change we made (action: review + keep)

**Bug:** `backend_codegen/ai_layer.py` `_PROVENANCE_OMIT` was missing `ownerId` / `createdAt` /
`updatedAt`, so they were emitted as **required `str` fields** on every `*Edge` (AI tool-input) schema.
`_persist` then forwarded the model's **string** timestamps straight into the SQLModel `datetime`
columns → **every generated AI pass crashed on commit** (`SQLite DateTime type only accepts Python
datetime…`). As shipped, the enrichment passes could not persist anything the model returned.

**Fix (`startd8-sdk` `17d92aa5`):** dropped those three from `_PROVENANCE_OMIT` (root cause — the table
defaults own them), and hardened `_PERSIST_HELPER` to strip a server-managed set as defense in depth.
Added a generator test asserting the edge schema omits them and `_persist` guards them. Verified by
regenerating strtd8's AI layer and running its offline pass suite green.

**Why it matters to you:** this was a silent, total functional failure of the generated AI layer that
`compileall`/`mypy` could not catch (it only fails at commit-time against a real DB). Worth a regression
fixture in the SDK's own runtime tests, not just the render tests.

---

## 2. What we built in strtd8, and why

### The strategic shift: deterministic-first
We **deferred all LLM generation** and built the user-facing capabilities with **manual data** first.
The trigger: effort was going into *refining the precision of the LLM enrichment* (retarget tests, the
datetime fix, regenerate, then nearly an LLM "linker" to reconstruct value-model edges) while the
**user-facing payoff did not exist or was unreachable** — export had formatters but no route, there was
no value-map view, completeness was computed but wired to nothing. We named this anti-pattern and wrote
it up as a principle in your repo: **`docs/design-princples/ZERO_VALUE_PRECISION_ANTI_PRINCIPLE.md`**
(`b87d3fb2`). Its desire-path corollary is load-bearing here: the value-model link graph is **authored
by the user click-by-click at runtime**, not inferred — so the "linking gap" we almost spent an LLM call
on was illusory; the user creates the edges by using the join CRUD.

### P1 deterministic value loop — shipped, $0 LLM, validated against real data
| Capability | What it is | strtd8 commit |
|---|---|---|
| Export | `build_payload` collector + `GET /export/json|markdown` downloads over the generated formatters | `48282da` |
| Value-map view | `/value-map` traces capability→outcome→proof from the **user-authored** join rows (no inference) | `5348340` |
| Completeness | `/completeness` with the **real FR-9 signal set** (supersedes the placeholder — see D4) | `763ebe5` |
| Import / Résumé / Nav / Migrations | round-trip JSON import, résumé-ready MD, clickable nav, Alembic baseline | `354e3c3` |

All are **owned authored glue** mounted at the `app/server.py` composition seam and anchored; built and
verified (22 tests; live against the real `app.db`) — including the **same datetime round-trip** the SDK
bug was about (import parses ISO strings back to `datetime`).

### P2 deterministic slice — authored as a cap-dev-pipe input
`python-requirements-p2.md` + `python-plan-p2.md` (`8ab1d02`) scope the deterministic job-tailoring
workspace (jobs dashboard, per-job workspace resolving the **polymorphic** `TailoredMatch` into a
JD-needs-vs-matched + gap view, per-job export). **Generation strategy is classified per task**: every
feature is SIMPLE/contract-derived → `$0` or **micro-prime** under the semantic-compliance gate; the
genuine LLM-value tasks (JD extraction, match suggestion, asset drafting) are **explicitly deferred**.

---

## 3. Decision agenda (what we want the SDK team to weigh in on)

| # | Gap observed in practice | Decision for the team |
|---|---|---|
| **D1** | SDK emits the spine (CRUD/templates) + AI passes, but **no generator for owned composite *views*** (value-map, completeness display, export routes/collector, per-job workspace). We hand-authored them (R2-S1 fallback). | Should the SDK generate these view types? If so, via a **declarative view/page manifest** analogous to `ai_passes.yaml` (entity-join traversals, read-only render)? |
| **D2** ✅ **RESOLVED** | The owned/authored **composition seam is not regen-safe**: we mount routers by hand-editing generated `app/server.py` and add nav to generated `base.html`; `generate backend` would overwrite both. | **Done (router seam):** `render_main` now emits a tolerant mount of an owned `app/user_routers.py` (a `user_routers` list the generator never writes) — owned routers survive regenerate (verified end-to-end). **Nav** rides `pages.yaml` (content-pages). Consumer adoption = move the 5 P1 mounts into `app/user_routers.py` + put nav in `pages.yaml` (Phase 0 F-002). |
| **D3** | The **no-LLM / micro-prime / large-model** routing held up: deterministic views are SIMPLE → `$0`/micro-prime, never large-model. The P2 slice classifies per task by hand. | Should the SDK make the **per-task generation-strategy classification explicit** (and prefer `$0` emit where a generator exists, route micro-prime where it doesn't, reserve large models for true LLM-value tasks)? |
| **D4** | Generated `completeness.py` is a **placeholder** (fraction of all 15 entities incl. AiCall/joins/P2 — misleading). The real FR-9 signal set is hand-authored. | SDK should generate completeness from a **declared signal manifest** (signals + thresholds + ordered nudges), not a presence rule. |
| **D5** | Generated `export.py` emits formatters but **no collector and no routes** — a user cannot export. We added both by hand (and import). | SDK export generator should emit the **collector + download routes + import**, not just the pure formatters. |
| **D6** | The P1 glue was validated **ad-hoc** (fast capability-validation, outside the semantic-compliance gate, not regen-safe). | Reconcile P1 glue **into the validated process now** (and promote its patterns to generators), or **after** the P2 deterministic round? |

---

## 4. The pattern we'd propose (for discussion)

The session converged on a sequence we think generalizes, and which reframes the hand-building **not as a
bypass of the SDK but as a scouting step within it**:

> **Validate the capability cheaply** (by hand / agents, with manual data) → **then engineer it through
> the process** (requirements → plan → `$0`/micro-prime generation → semantic validation → regen-safe).

Hand-authoring proved *which* capability is right and that it's reachable, fast and at low cost — exactly
what Zero Value Precision endorses (don't perfect a generator before a user has used what it generates).
The **debt** that creates is reconciliation (D6): the validated capability owes a pass back through the
rigorous process. The SDK is the engineering discipline; "build without an LLM where one adds no value"
and "route micro-prime where a small model suffices" are first-class moves **inside** it, not exceptions
to it. This review is itself that reconciliation step for D1–D6.

---

## 5. Artifact index

**startd8-sdk:** `17d92aa5` (edge-schema/`_persist` datetime fix) · `b87d3fb2` (Zero Value Precision
principle) · this doc.
**strtd8 (app):** `b1d915a`/`b66d559` (retarget tests + regen AI layer) · `48282da` (export) ·
`5348340` (value-map) · `763ebe5` (completeness) · `354e3c3` (import/résumé/nav/migrations) ·
`f59c6c7` (value-loop next-round docs) · `8ab1d02` (P2 deterministic reqs + plan).
**Principle:** `startd8-sdk/docs/design-princples/ZERO_VALUE_PRECISION_ANTI_PRINCIPLE.md`.
