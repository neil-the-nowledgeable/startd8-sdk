# `onboarding:` Second Cascade Consumer — Portability Proof (Requirements)

**Project:** startd8-sdk backend_codegen · **Criticality:** medium
**Version:** 0.4 (post-CRP-lite R1) · **Date:** 2026-08-14
**Format:** det-req/0.1
**Backend:** startd8-python-cascade
**Audience:** operator (SDK maintainers running the dogfood gate) · end-user (first-run user of the selected app)
**Trust boundary:** onboarding copy is product prose shown to end users; in a UPL-sensitive consumer the tips stay orientation, never legal advice, and never restate an attorney-gate-owned validationStatus
**Data classification:** internal (pilot evidence); the selected app's own classification governs its content.
**Pairs with:** ONBOARDING_SECOND_CONSUMER_PLAN.md
**Inherits standards:** [`ONBOARDING_ARCHETYPE_REQUIREMENTS.md`](./ONBOARDING_ARCHETYPE_REQUIREMENTS.md)
FR-1..6 (**cite, do not re-spec**) · PC-13 (onboarding is content, not a modal) ·
det-req-kit [`BACKEND_ROUTING.md`](../../../../dev-os/det-req-kit/BACKEND_ROUTING.md) ·
dev-os propagation gate (CL-21: authored ≠ propagated) · `/survivorship-audit` (assume the green is lying)

**Status:** SPECIFIED (v0.4, post-CRP-lite R1) — not implemented. This REQ selects a consumer and defines
the dogfood gate; the dogfood itself is the PLAN's execution, deliberately not run in this pass.
Plan: [`ONBOARDING_SECOND_CONSUMER_PLAN.md`](./ONBOARDING_SECOND_CONSUMER_PLAN.md).
Prior consumers: wireframe fixture harness (`tests/fixtures/wireframe/prisma/views.yaml`) and the
household-o11y lived demo ([`_PILOT_2026-08-14_onboarding-household.md`](./_PILOT_2026-08-14_onboarding-household.md)).

---

## 0. Planning Insights (Self-Reflective Update)

> v0.1 assumed this was a small selection-and-declare errand: pick the best-looking second product
> app, paste an `onboarding:` block, regenerate, done. The planning pass — a whole-tree census plus a
> live `generate backend --check` against every candidate — falsified that at three levels. Every
> non-pilot cascade consumer is **materially drifted** from SDK `main`, so the onboarding delta cannot
> be isolated without a baseline gate first. The most attractive candidate on paper already ships a
> **hand-built onboarding surface**, i.e. the exact shape that made the attorney portal a bad first
> dogfood. And the archetype's existing portability claim rests on one lived consumer whose **recorded
> regeneration recipe fails today**. v0.2 therefore re-centres on the *gate* — baseline-green before
> delta, an explicit disqualification rule, and a recorded negative-capable verdict — and demotes
> "declare the YAML" to one step among eight.

| v0.1 Assumption | Planning Discovery | Impact |
|-----------------|--------------------|--------|
| Declaring `onboarding:` on a third app is a one-line delta | Every candidate is drifted from SDK main: navig8 **12** artifacts, strtd8-v2-cascade **84**, benchmark portal **97** (measured 2026-08-14 via `generate backend … --check`) | New **FR-3**: baseline-green is a *precondition*; the pilot is bracketed by two `--check` runs so the onboarding delta is attributable |
| The benchmark reviewer portal is the natural second consumer (13 entities, `pages.yaml` owns `/`, real reviewers) | It already has hand-built role-aware onboarding — `app/reviewer_intro.py` (48 lines) feeding a `/start` page — plus 97-artifact drift and a live embargoed deployment | **Rejected** and named in Non-goals; retrofitting it repeats the attorney-portal mistake the archetype explicitly avoided |
| "Two proven consumers" means the regeneration path is green today | Consumer #1's recorded recipe **fails**: household `make check` backend leg errors `form_prose.yaml: entry 'Medication' references unknown form field 'dose'` — reproduced on both the PATH binary and the SDK venv | New **FR-8**: prior-consumer re-verification is a blocking pre-flight; the portability claim may not advance on a lying green |
| The transferable asset is the `onboarding:` YAML block | The household pilot's real transferable asset is its **Makefile** — the exact verified flag set plus a documented RESIDUAL drift set. navig8, strtd8-v2-cascade and the portal have **no recorded recipe at all** | FR-3 requires *producing* the recipe; without it "regenerates green" is unfalsifiable |
| The onboarding block is self-contained | FR-4's checklist links to `/ui/<entity>` create forms, and `_writable_fields` (`htmx_generator.py:1407`) strips `human_inputs.yaml`-owned fields from those forms — so an owned field a user must type makes the first-run path dead-end. This is the mechanism behind the household `dose` failure | New **FR-2**: an owned-field × first-run-typed-field collision **disqualifies** a candidate. navig8 passes (its 5 owned fields are pipeline/attorney-gate-owned, never user-typed) |
| `redirect_root_if_empty` is exercisable anywhere | FR-2 of the archetype gates it on a `pages.yaml` page owning `/`; navig8 has **no `pages.yaml`** | Scoped out for this pilot (Non-goals) rather than bolting a pages layer onto the consumer to satisfy an optional flag |
| navig8's own docs describe its state | `navig8/CLAUDE.md` says "no `app/` generated yet" and `docs/ASSEMBLY_INPUTS.yaml` marks `views: absent` — both false; `app/` exists with 40 CRUD routes and `views.yaml` is present | Doc-drift repair folded into the PLAN (S7) as pilot fallout, not a separate loop |

### 0.1 Lessons / Pattern hardening (Phase 4.5 — honest)

Keyed lookup was **run, not skipped**: `python -m contextcore.learning.pattern_catalog recall
"requirement × single-source/no-drift" "requirement × lifecycle/bootstrap"
"code × context-arrival/data-wiring"` → **`(none — browse fallback)`**. No promoted pattern keys to
this draft's decision-classes, so no PC-ID is cited here. Claiming one would be the dormant-path
inflation the catalog exists to prevent. Fell through to the domain browse; the nearest prior art is
the household pilot note itself, which is cited directly rather than laundered into a pattern claim.

**Nomination (not a citation):** if this pilot's bracketed-`--check` gate recurs on a third adoption,
it is a promotion candidate under `single-source/no-drift` — *"attribute a delta by bracketing it with
two drift checks, never by inspecting the diff."*

### 0.2 Design-principle hardening (Phase 4.6 — honest)

Keyed against [`PRINCIPLE-INDEX.md`](../../../../dev-os/PRINCIPLE-INDEX.md) §2 on the same tuples:

- **Genchi Genbutsu** (`requirement × single-source/no-drift`) — applied and load-bearing. Every census
  row is a measured `--check` exit, not a doc claim. It is what caught navig8's CLAUDE.md asserting an
  `app/` that exists, and consumer #1's recipe failing while its pilot note reads green. Enforcer named
  (surfacing ≠ enforcement): the `--check` drift path itself is the gate, run twice per FR-3.
- **Mottainai** (`code·plan × idempotency/reuse`) — dominant constraint. This REQ adds **zero** onboarding
  grammar; FR-4 forbids SDK source changes in the pilot commit and makes that machine-checkable
  (`git diff src/startd8/backend_codegen/` must be empty). New keys here would fork the archetype.
- **Context-Correctness-by-Construction** (`code·plan × context-arrival/data-wiring`) — the FR-2
  collision rule is exactly this principle at the manifest seam: the checklist declares a slot
  (`empty_states: Entity`) whose create form may silently arrive without the fields that make the entity
  meaningful. Declared + validated, not assumed.
- **Ichigo Ichie** — the *most* on-point principle and it is **parked in §3**, advisory-only, because
  `lifecycle/bootstrap` names entry-points, not first-run *quality*. Cited as advisory and **not**
  returned by the keyed lookup. This REQ is a second concrete recurrence of that gap; it carries the
  standing extension request for `first-run/cold-start-quality` (the route Mieruka took to §2 in
  2026-07-24). Ratification belongs in `PATTERN-CATALOG.md` §1 first — not asserted here.

### 0.3 Review insights (v0.2 → v0.4, CRP-lite R1 — 2026-08-14)

> R1 attacked the *Verify clauses* rather than the selection, and found two of them non-falsifiable in
> opposite directions. FR-3's "added drift is exclusively the three onboarding kinds" is falsified **by
> construction**: `forms-sha256` hashes the whole `views.yaml`, so declaring `onboarding:` necessarily
> re-stales three non-onboarding artifacts — a *correct* pilot would have failed its own gate, and the
> operator's only escape would have been to narrate the extra rows away, which is precisely the judgement
> call the bracket exists to eliminate. FR-2's second limb failed the other way: it is **vacuously true**
> on the selected consumer (`navig8/prisma/` has no `form_prose.yaml`, so the cited error is unreachable),
> yielding zero signal from a criterion the census leaned on. Both are now re-cut against mechanisms
> rather than symptoms — a predicted-set subset test for FR-3, a required-on-create-scalars intersection
> for FR-2. R1 also found that the first-run dead-end the pilot is actually exposed to is **not** the one
> FR-2 guards: a required scalar FK (`TreeNode.treeId`, no default, not owned) survives `writable_fields`
> and dead-ends the create form, while FK pickers are a Non-goal. The lesson generalizes past this REQ —
> the drafted Verify clauses named the *artifacts* they expected to see rather than the *mechanism* that
> produces them, and only mechanism-level criteria can fail.

| v0.2 Assumption | R1 Discovery | Impact |
|-----------------|--------------|--------|
| The onboarding delta shows up only in the three onboarding artifact kinds | `forms_stale_reason` hashes the whole `views.yaml` (`drift.py:849-870`); navig8's `app/web.py`, `app/nav.py`, `app/index.py` all carry `forms-sha256: 1c4898693fa9…` today, so the declaration re-stales all three, and `app/main.py` reads **tampered** (schema-only hash) when it gains the mount | **FR-3 Verify re-cut** to a *predicted-set subset test* (R1-F2). Carry-alongs are structural and pre-declared; an *unpredicted* member is the defect signal |
| FR-2's `form_prose.yaml` limb tests the collision | Unreachable on navig8 — `prisma/` holds only `schema.prisma`, `views.yaml`, `human_inputs.yaml`. The limb can never fail, so it certified nothing | **FR-2 Verify re-cut** to the mechanism (owned × required-on-create intersection); the `form_prose` sentence stays with **FR-8**, where consumer #1 is the subject (R1-F1) |
| navig8 clears FR-2 because its owned fields are "not user-typed" | True, but for a *checkable* reason the REQ never stated: all five owned targets carry schema defaults, so none is required-on-create once `writable_fields` strips it | FR-2 now records the defaults as its audit trail, making the pass auditable instead of asserted (R1-F1) |
| FR-2 covers the first-run dead-end class | It does not. `TreeNode.treeId` is a required scalar FK with **no default**, not owned, not in `_PROVENANCE_OMIT` — it survives `writable_fields` and asks a first-run user to hand-type a CUID: FR-2's failure *shape* arriving through a mechanism FR-2 does not model | `TreeNode` dropped from the drafted `empty_states` (PLAN S4); the dead-end is named in Non-goals, probed at S7 either way, and counts as FR-7 friction if kept (R1-S2) |
| Three verdicts plus "SDK edits ⇒ NOT-PORTABLE" is a decision procedure | Only the negative case is pinned. With no `PORTABLE` / `PORTABLE-WITH-FRICTION` boundary the middle verdict absorbs unbounded friction, and O-3's falsifiability degrades to a narrative choice | **FR-7 Verify** gains all three definitions plus a requirement to *name the friction items counted* (R1-F3) |
| An empty `git diff` proves no SDK change was needed | On a clean tree the diff is trivially empty — it cannot distinguish "no change needed" from "a change made and committed mid-pilot", which is the pilot's central claim | Sha-anchored: G2 records `rev-parse HEAD`, S6 asserts it unchanged (PLAN S6, R1-S3) |
| FR-8's gate protects this pilot's baseline | It protects the *two-proven-consumers claim* — a lying green upstream — not navig8's regeneration path, which is structurally immune (no `form_prose.yaml`) | FR-8 states its scope explicitly and its ledger gate gets a citable ID, **CL-54** (R1 focus ask A1) |

## Overview

The `onboarding:` archetype ships and is declared by two surfaces: an SDK test fixture and one lived
app that co-evolved with it. Neither is an independent adoption, so "portable" is currently an
untested generalization. This REQ picks a **third surface — a real product consumer that did not
co-evolve with the archetype** — and defines the gate that makes its adoption count as evidence:
baseline-green first, onboarding delta second, runtime smoke third, and a written verdict that is
allowed to say *no*. It invents no onboarding grammar; FR-1..6 of the archetype are cited, not
restated. The deliverable of the pilot is evidence about the archetype, not features for the app.

## Objectives

- O-1: A cascade consumer that never saw the archetype's development declares `onboarding:` and
  regenerates green with **zero SDK source changes**.
- O-2: The onboarding delta is **attributable** — separable from the consumer's pre-existing drift.
- O-3: The portability verdict is falsifiable and may be negative; a pilot that required SDK edits is
  recorded as a failed proof, not quietly repaired into a success.

## Risks

| Type | Description | Mitigation | Priority |
|------|-------------|------------|----------|
| quality | Baseline drift (12–97 artifacts) swamps the onboarding delta, making "green" unattributable | FR-3 brackets the change with two `--check` runs; added drift is tested against a **pre-declared predicted set**, so carry-alongs are expected rather than argued about | high |
| quality | **The operator explains an unexpected drift row away.** The bracket's value is that it removes judgement; a hand-waved row silently restores it | FR-3's subset test is directional: an *unpredicted* member stops the pilot (PLAN decision-rule branch 2). Predicting the set *before* the run is what makes this checkable | high |
| quality | Pilot silently becomes archetype development — SDK edited to make the consumer work, then declared portable | FR-4 requires an empty `git diff` on `backend_codegen/` **and an unchanged SDK sha** (PLAN G2/S6) — an empty diff alone cannot detect a change committed mid-pilot; FR-7 forces a negative verdict if either fails | high |
| quality | Prior-consumer regression (household `dose`) means the baseline claim is already false | FR-8 blocks advancement until re-verified or filed with a dated gate | high |
| safety | UPL-sensitive consumer: orientation prose drifts into legal advice, or restates attorney-gate `validationStatus` | Trust boundary above; tips are navigation-only and reviewed against the UPL invariant; owned copy untouched | high |
| security | Welcome route counts rows across every declared `empty_states` entity | Inherited archetype mitigation — read-only counts, no write surface (cite; not re-specified) | medium |
| cost | Regenerating a 12-artifact-drifted app overwrites hand-tuned files | FR-3's recorded recipe must document the RESIDUAL set before any write; `--check` is read-only and runs first | medium |
| quality | **`PORTABLE-WITH-FRICTION` absorbs unbounded friction**, making the verdict a narrative choice and O-3's falsifiability decorative | FR-7 supplies a selection *rule* for all three verdicts and requires the note to **enumerate the friction items counted**; an unnamed-friction middle verdict is a defect in the note | high |

## Profile

Declared profile: **internal**

## Candidate census (grounded 2026-08-14)

Every cascade consumer on disk — `schema.prisma` + `views.yaml` + a generated `app/`. Drift measured
by `startd8 generate backend --schema … --views … [--pages …] --human-inputs … --check` (read-only).

| Rank | Consumer | Path | Entities | Last commit | Drift today | Hand-built onboarding | Verdict |
|------|----------|------|----------|-------------|-------------|----------------------|---------|
| **1** | **navig8** | `~/Documents/dev/navig8` | 8 | 2026-08-13 `8cf1a22` | **12** | none | **SELECTED** |
| 2 | strtd8-v2-cascade | `~/Documents/dev/strtd8/strtd8-v2-cascade` | 16 | 2026-06-15 `517c4b2` | 84 | none found | fallback |
| 3 | benchmark reviewer portal | `~/Documents/dev/benchmarking/Summer2026/portal/internal` | 13 | 2026-08-12 `fe820e3` | 97 | **yes** — `app/reviewer_intro.py` + `/start` | rejected |
| 4 | strtd8 (v1) | `~/Documents/dev/strtd8/strtd8` | 31 | 2026-07-09 `8dfefb6` | not measured (no recipe; hand-built `control-panel/`) | control-panel | rejected |
| — | attorney portal | `~/Documents/dev/startd8-work/work/legal/attorney-portal` | n/a | — | not a cascade consumer (hand-built ONB v0.4) | yes | rejected — Non-goal |
| — | portal-v2 | `~/Documents/dev/benchmarking/Summer2026/portal-v2` | n/a | — | ineligible: no `prisma/` — its `views.yaml` is pipeline output | — | ineligible |

Worktrees, `tests/fixtures/wireframe/`, and `docs/design/wireframe/spike-*/manifests/` copies are
excluded: they are the harness (consumer #0), not independent adoptions.

**Why navig8.** Lowest drift by a factor of seven; freshest non-pilot commit; a genuinely different
domain (Michigan legal intake) and audience (laypeople) from household, which is the portability
signal we lack; no hand-built onboarding to fight; and its owned-field set clears FR-2 — all five
targets in `prisma/human_inputs.yaml` are verification-pipeline- or attorney-gate-owned
(`TreeNode.confidence`, `TreeNode.attorneyNote`, `LandmineEntry.confidence`,
`DecisionTree.validationStatus`, `SequenceConfig.validationStatus`), none of which a first-run user
types. The *auditable* form of that clearance (R1-F1) is that all five carry schema defaults, so
stripping them leaves no required-on-create hole; the assertion "a user would not type it" is the
intuition, the defaults are the check. First-run orientation is also product-critical there rather than decorative: the app must state
the UPL boundary and its `candidate — not yet attorney-validated` status up front, which is precisely
the content-not-modal shape PC-13 prescribes.

**Why not the portal.** It is the strongest candidate on entity count and is the one to revisit later,
but adopting it now means deleting a working hand-built `/start` in a live embargoed deployment while
reconciling 97 drifted artifacts — the attorney-portal failure mode with a new name.

## Functional requirements

- **FR-1 — The census is an artifact, not a claim.** This REQ carries a ranked table of every cascade
  consumer on disk, each row citing path, entity count, last commit, measured drift, and whether a
  hand-built onboarding surface exists. Touches: census.
  Verify: every drift number reproduces by re-running the command recorded in PLAN S1; a consumer that
  has `schema.prisma` + `views.yaml` + `app/` on disk and no row is a census defect. Serves: O-1

- **FR-2 — Owned-field collision disqualifies a candidate.** A candidate is rejected when any field a
  first-run user must type to create an `empty_states` entity is declared in that consumer's
  `human_inputs.yaml`, because owned fields are stripped from the generated form
  (`writable_fields`, `htmx_generator.py:106-129`; aliased `_writable_fields` at `:135`).
  Touches: human_inputs manifest, empty_states keys.
  Verify (mechanism, not symptom — R1-F1): for **each** declared `empty_states` entity, the intersection
  of that entity's `human_inputs.yaml` targets with its **required-on-create scalars** — non-optional,
  non-list (`_is_required`, `htmx_generator.py:138`), carrying **no schema default** — is empty; and
  every declared entity's create form renders at least one required input. The criterion is calibrated,
  not merely satisfied: it **must fail** on consumer #1 (`Medication.dose` is `authored_by: human` with
  no default) and **must pass** on navig8 — a criterion that passes both is too weak and is itself a
  defect. navig8 passes for a stated, re-checkable reason: all five owned targets carry schema defaults
  (`TreeNode.confidence @default(medium)`, `TreeNode.attorneyNote @default("")`,
  `LandmineEntry.confidence @default(medium)`, `DecisionTree.validationStatus` and
  `SequenceConfig.validationStatus` both `@default("candidate — not yet attorney-validated")`), so none
  is required-on-create once stripped.
  **Scope limit (R1-S2, do not mistake for a pass):** FR-2 models the *owned-field* dead-end only. A
  **required scalar FK with no default** — `TreeNode.treeId` — is not owned, is not in
  `_PROVENANCE_OMIT`, and survives `writable_fields`, so it reaches the create form as a hand-typed
  CUID. That is FR-2's failure *shape* through a mechanism FR-2 does not cover; FK pickers are a
  Non-goal, so it is handled as FR-7 friction, not silently absorbed. Serves: O-1

- **FR-3 — Baseline-green precedes the onboarding delta.** Before `onboarding:` is declared, record the
  consumer's exact regeneration recipe (flag set + a written RESIDUAL drift set) and reconcile baseline
  drift down to that residual. Touches: recipe, drift transcript.
  Verify: two `--check` transcripts bracket the change — a pre-declaration run whose drift equals the
  recorded residual, and a post-declaration run, taken after the `views.yaml` edit but **before the
  regeneration write** (so "added drift" names what the declaration alone changed), whose *added* drift
  is a **subset of the predicted set below, with no unpredicted member**. An unpredicted member is a real
  defect and stops the pilot; narrating an observed row away is forbidden, because removing that
  judgement call is the entire purpose of the bracket.

  **Predicted added-drift set (navig8, R1-F2)** — declared *before* the run, so the test is falsifiable:

  | Predicted member | Kind | Expected label | Why it is in the set |
  |------------------|------|----------------|----------------------|
  | onboarding router / welcome / aggregator artifacts | `fastapi-onboarding`, `onboarding-welcome`, `onboarding-aggregator` | new | The onboarding delta proper |
  | `app/web.py` | `fastapi-web-forms` | stale | Carries `forms-sha256`; `_FORMS_KINDS` (`drift.py:83-90`) |
  | `app/nav.py` | `nav-registry` | stale **+ content change** | Carries `forms-sha256`; `_NAV_KINDS` (`drift.py:114-116`). Also gains a real `NavEntry(key="onboarding:/welcome")` (`nav_generator.py:91-99`) |
  | `app/index.py` | `nav-index-router` | stale | Carries `forms-sha256` |
  | `app/main.py` | `fastapi-main` | **tampered**, not stale | Its hash is schema-only (not in `_FORMS_KINDS`), so the `views.yaml` edit leaves the hash *matching* while the expected content now carries the `onboarding_routers` mount the on-disk file lacks — the difference surfaces as tamper, not staleness |

  The three `forms-sha256` carry-alongs are **structural, not noise**: `forms_stale_reason` hashes the
  *whole* `views.yaml` — "The hash covers the whole `views.yaml` … so composite-view edits conservatively
  re-stamp these files" (`drift.py:849-870`) — and all three carry
  `forms-sha256: 1c4898693fa93ccdfc24e353b4f37c15193bb3e1a0e6dd6e89979405a705db00` on disk today
  (verified 2026-08-14). Any declaration of `onboarding:` therefore re-stales them on a **correct** run;
  the superseded "exclusively the three onboarding kinds" wording would have failed a correct pilot.
  Mirrored in PLAN § *The predicted added-drift set* and step **S5a** (`R1-S1`). Serves: O-2

- **FR-4 — Declare `onboarding:` with existing grammar only.** The consumer's block uses archetype
  FR-1/FR-2 keys and nothing else; the pilot introduces no SDK change. Touches: views.yaml,
  onboarding prose.
  Verify (two limbs, both required — R1-S3): the block parses with no edits under
  `src/startd8/backend_codegen/` — `git diff` on that path is empty for the pilot commit — **and** the
  SDK commit sha is unchanged from the one recorded at PLAN G2. The sha limb is not redundant: on a clean
  tree the diff is trivially empty, so it cannot distinguish "no SDK change was needed" from "a change
  was made and committed mid-pilot". Any needed SDK change converts this pilot into a negative result
  under FR-7. Serves: O-1, O-3

- **FR-5 — Regeneration is green on the onboarding kinds.** After regen, the three onboarding artifact
  kinds are in sync and the tolerant mount is present. Touches: drift transcript, welcome.
  Verify: the **post-write** `--check` (the third transcript, after regeneration — distinct from FR-3's
  pre-write pair) reports the three kinds in sync and the FR-3 carry-alongs resolved, and `app/main.py`
  contains the `onboarding_routers` try/except mount (present in household `app/main.py:129`, **absent**
  in navig8's today — its `main.py` predates FR-5). Serves: O-1, O-2

- **FR-6 — First-run smoke on the running app.** The welcome route works on an empty database and the
  checklist tracks real counts. Touches: welcome, empty_states keys.
  Verify: given an empty DB, GET the declared route returns 200 and its body contains each declared
  empty-state copy string and no `role="dialog"` / modal markup; after inserting one row of one
  declared entity, that entity's checklist item is gone and the others remain. Serves: O-1

- **FR-7 — The verdict is recorded and may be negative.** A short pilot note states what transferred
  unchanged, what needed consumer-specific work, and an explicit portability verdict. Touches: pilot note.
  Verify: the note exists beside this REQ, cites all three `--check` transcripts by command line (FR-3's
  pre-declaration and pre-write pair plus FR-5's post-write run) together with the G2/S6 sha pair, and
  contains exactly one of the three verdicts below, **selected by rule rather than narrated** (R1-F3):

  | Verdict | Selection rule (all conditions) |
  |---------|---------------------------------|
  | `PORTABLE` | Empty `src/startd8/backend_codegen/` diff **and** unchanged SDK sha (PLAN G2/S6) **and** zero consumer-specific work beyond human-authored prose — no residual drift, no dropped `empty_states` entity, no manual step |
  | `PORTABLE-WITH-FRICTION` | Empty SDK diff **and** unchanged sha, **plus at least one named, recorded** consumer-specific workaround: surviving residual drift, an `empty_states` entity dropped or degraded, a manual step, or a runtime defect fixable outside `backend_codegen/` |
  | `NOT-PORTABLE` | **Any** required change under `src/startd8/backend_codegen/` — including a change the pilot needed but deferred |

  The note must **enumerate the friction items it counted**; a `PORTABLE-WITH-FRICTION` verdict with no
  named item is a defect in the note, not a verdict. Two friction candidates are already known and must
  be dispositioned explicitly: the `TreeNode` required-FK dead-end (FR-2 scope limit) and any FR-3
  carry-along that fails to resolve post-write. A pilot that required SDK edits reads `NOT-PORTABLE` and
  the archetype REQ's portability status is downgraded, not amended. Applying these three definitions
  retroactively to the household pilot note must yield an unambiguous classification; if it cannot, the
  definitions are still too loose and this Verify clause is the defect. Serves: O-3

- **FR-8 — Prior-consumer re-verification (survivorship pre-flight).** Consumer #1's recorded recipe is
  re-run before this pilot's verdict is written; the portability claim may not advance while it fails.
  Touches: recipe, drift transcript.
  **Scope — what this gate does and does not de-risk (R1 focus ask A1):** it protects the *two-proven-
  consumers claim* against a lying green upstream. It does **not** protect this pilot's regeneration
  path, which is structurally immune to the household failure class: `navig8/prisma/` contains only
  `schema.prisma`, `views.yaml`, `human_inputs.yaml` — there is no `form_prose.yaml`, so that error is
  unreachable here. Reading G1 as a baseline guard for navig8 would be a category error.
  Verify: household `make check`'s backend leg completes without a manifest error, **or** the current
  failure (`form_prose.yaml: entry 'Medication' references unknown form field 'dose'`, reproduced
  2026-08-14 on both `/opt/homebrew/bin/startd8` and the SDK venv) is filed as a dated Closure-Ledger
  gate under a **citable ID — `CL-54`** (next free row as of 2026-08-14; confirm on filing) and the FR-7
  note cites that ID verbatim. "Filed and cited" is checkable by grepping the ID in both the ledger and
  the pilot note, not by narrative assurance. Serves: O-3

## Non-goals

- **Attorney-portal retrofit** — hand-built ONB v0.4 in `startd8-work/work/legal/attorney-portal/`;
  cited as shape only, never adopted. Re-affirmed from the archetype's Non-goals.
- **Benchmark-portal `/start` retrofit** — replacing `app/reviewer_intro.py` and its role-aware
  onboarding in a live embargoed deployment. A separate REQ if ever wanted.
- New archetype features or grammar keys of any kind (FR-4 makes this machine-checkable).
- FK picker widgets (pilot P1-2) — separate REQ. **Consequence this pilot must own (R1-S2):** with no
  picker, an entity whose create form needs a required scalar FK cannot be completed by a first-run
  user. `TreeNode.treeId` is such a field, so `TreeNode` is dropped from the drafted `empty_states`
  (PLAN S4). It is *observed* at S7 (`GET /ui/treenode/new`) and recorded either way, not assumed away;
  if a later pass keeps `TreeNode` in the checklist, that is FR-7 friction with a named cause.
- Per-list CRUD empty-states (archetype v1 already excludes; separate REQ).
- Multi-step `confirm-walk:` cascade archetype.
- Welcome Mat / Concierge chat, download, or kickoff YAML export.
- `redirect_root_if_empty` exercise — navig8 has no `pages.yaml`; adding a pages layer to satisfy an
  optional flag is out of scope for a portability proof. **This exclusion is cheaper than v0.2 implied
  (R1 focus ask A3):** the flag defaults to `False` (`onboarding_manifest.py:40, 86-88`), so omitting it
  is the documented no-op path rather than an untested branch; and the welcome route stays **discoverable
  without** a pages layer, because `nav_generator.py:91-99` registers the onboarding `NavEntry` from
  `views.yaml` alone and navig8 ships the nav layer. Only the optional root-redirect branch goes
  unexercised — no first-run discoverability is lost.
- **Fixing** the household `form_prose` / owned-field regression. FR-8 requires *observing and filing*
  it; the fix is its own loop.
- Any change under `src/startd8/backend_codegen/` (FR-4).

## Owned fields

Only humans enter: the selected consumer's `views.yaml` `onboarding:` prose — `title`, `lead`, `tips[]`,
`empty_states` copy, `nav_label` — and the FR-7 pilot-note verdict. For navig8 specifically, no
onboarding copy may state or paraphrase a `validationStatus`; that string is attorney-gate-owned per
`navig8/prisma/human_inputs.yaml` and is rendered verbatim by the app.

## Contract projection

- **Backend:** startd8-python-cascade
- **Vocabulary home (cite):** `src/startd8/backend_codegen/onboarding_manifest.py` +
  [`ONBOARDING_ARCHETYPE_REQUIREMENTS.md`](./ONBOARDING_ARCHETYPE_REQUIREMENTS.md) § Contract projection

| Entry (name) | Kind | Words/Structure | Notes |
|--------------|------|-----------------|-------|
| welcome | page | structure | Generated GET orientation route on the selected consumer; kinds `fastapi-onboarding`, `onboarding-welcome`, `onboarding-aggregator` (`drift.py`), mounted by `crud_generator.render_main` |
| empty_states keys | entity | structure | Must exist on the consumer's `schema.prisma` |
| onboarding prose | page | words | Tips / lead / empty-state copy — human-authored, placeholder until reviewed |
| views.yaml | manifest | structure | Carries the `onboarding:` block; parsed by `onboarding_manifest.py`; drift-hashed |
| human_inputs manifest | manifest | structure | FR-2 collision source of truth |
| recipe | manifest | structure | Recorded flag set + RESIDUAL drift (household `Makefile` is the reference shape) |
| drift transcript | doc | structure | The `generate backend … --check` transcripts: FR-3's bracketing pair (pre-declaration, pre-write) plus FR-5's post-write run — three in total, each pinned to one binary (PLAN G3) |
| census | doc | words | The ranked candidate table above (FR-1) |
| pilot note | doc | words | FR-7 verdict artifact |

---

## Appendix A — Accepted (with where merged)

**R1 (CRP-lite, Composer, 2026-08-14) — triaged 2026-08-14. 3 of 3 requirement-side suggestions ACCEPTED;
0 rejected.** Plan-side `R1-S1`–`R1-S3` and focus-ask deltas are dispositioned in the PLAN's Appendix A.

| ID | Accepted suggestion | Merged into |
|----|---------------------|-------------|
| **R1-F1** | Re-cut FR-2's Verify to a mechanism-level criterion (owned targets × required-on-create scalars), drop the vacuous `form_prose.yaml` limb, and state *why* navig8 passes (all five owned targets are defaulted) | **FR-2 Verify** (rewritten, plus the calibration requirement that it must fail on household `Medication.dose`); the `form_prose` sentence stays with **FR-8**, whose subject is consumer #1; defaults reason also added to § Candidate census "Why navig8"; §0.3 row 2–3 |
| **R1-F2** | Amend FR-3's Verify to a **predicted added-drift set** (3 onboarding kinds + the three `forms-sha256` carry-alongs + `app/main.py` tampered) with a subset test, replacing "exclusively the three onboarding kinds" | **FR-3 Verify** (rewritten with the predicted-set table and the `drift.py:849-870` mechanism); clarified that the second `--check` is post-declaration / **pre-write**; **FR-5 Verify** relabelled as the post-write transcript; §0.3 row 1. Mirrored in PLAN § Why bracketed + S5 (`R1-S1`) |
| **R1-F3** | Give FR-7 a verdict-*selection* rule for all three verdicts, not just `NOT-PORTABLE`, and require the note to name the friction items counted | **FR-7 Verify** (three-row selection-rule table + enumerate-the-friction requirement + retroactive-household calibration); §0.3 row 5. Matching branch added to PLAN § Decision rule |

**Accepted from the R1 focus asks (answered on the PLAN, requirement-side deltas here):**

| Focus ask | Delta merged here |
|-----------|-------------------|
| **A1** — is the FR-8 pre-flight gate right? | **FR-8** gains an explicit *scope* paragraph (protects the two-proven-consumers claim, **not** navig8's baseline — the household failure class is unreachable without a `form_prose.yaml`) and a **citable gate ID `CL-54`** the FR-7 note must cite verbatim |
| **A3** — `pages.yaml` scope creep? | No creep confirmed; **Non-goals** now records that the exclusion is *cheaper* than v0.2 implied — `redirect_root_if_empty` defaults `False` (`onboarding_manifest.py:40, 86-88`) and the welcome `NavEntry` is registered from `views.yaml` alone (`nav_generator.py:91-99`), so no discoverability is lost |
| **A2 / A4** | Absorbed by `R1-F2` and `R1-F3` respectively |

**Orchestrator note (grounding, not a rejection).** Every R1 code citation was re-verified on disk before
merge: `forms_stale_reason` / whole-`views.yaml` hash (`drift.py:849-870`), `_FORMS_KINDS` / `_NAV_KINDS`
(`drift.py:83-90, 114-116`), the identical `forms-sha256: 1c4898693fa9…` on `app/web.py`, `app/nav.py`,
`app/index.py`, the absence of a `forms-sha256` header on `app/main.py`, `navig8/prisma/` holding only
three manifests, `TreeNode.treeId String` with no `@default`, and all five owned targets carrying
defaults. Two citation corrections applied silently in merge: the stripping helper is `writable_fields`
(`htmx_generator.py:106-129`, alias `_writable_fields` at `:135`; v0.2 cited the call site `:1407`, now
`:1408`), and required-on-create is decided by `_is_required` at `:138`. One arithmetic slip in R1 was
**not** carried over: focus ask A2 totals the predicted set as "six artifacts" while both A2's own
enumeration and `R1-S1` list seven members (3 onboarding + `web.py` + `nav.py` + `index.py` +
`main.py`). The merged Verify states the **set by member**, not a count, so the subset test is unaffected.

## Appendix B — Rejected (with rationale)

- **Benchmark reviewer portal as the pilot consumer** — rejected during the v0.1→v0.2 planning pass.
  Highest entity count and a `pages.yaml` owning `/`, but 97 drifted artifacts, a live embargoed
  deployment, and an existing hand-built role-aware `/start`. Adopting it is an onboarding *retrofit*,
  which is the failure mode the archetype was defined to avoid. Recorded here so a later reviewer does
  not re-propose it without new evidence.
- **Adding a `pages.yaml` to navig8 to exercise `redirect_root_if_empty`** — rejected: it changes the
  consumer to suit the test, weakening the portability signal the pilot exists to produce. **R1 confirmed
  this rejection costs nothing** and did not re-propose it (see Appendix A, focus ask A3).
- **R1 (2026-08-14): no suggestions rejected.** All of `R1-F1`–`R1-F3` were accepted; recorded here so a
  later reviewer can tell "nothing rejected" from "not yet triaged".

## Appendix C — Incoming review rounds

**R1 — Composer — 2026-08-14 (CRP-lite, dual-document).** Filed in full under
[§ Appendix C: Incoming Suggestions](#appendix-c-incoming-suggestions-untriaged-append-only) below (the
generator-created appendix), left byte-intact per the append-only rule. Triaged: all 3 accepted → Appendix A.

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

| ID | Suggestion | Source | Implementation / Validation Notes | Date |
|----|------------|--------|-----------------------------------|------|
| R1-F1 | Re-cut FR-2's Verify into a mechanism-level criterion (owned targets ∩ required-on-create scalars); drop the unreachable `form_prose.yaml` limb; state that navig8 passes because all five owned targets are defaulted | Composer R1 | **APPLIED** to FR-2 Verify. Added the calibration clause R1 asked for: the criterion must **fail** on household (`Medication.dose`, `authored_by: human`, no default) and **pass** on navig8 — a criterion satisfying both is itself a defect. Grounded on disk: all five navig8 targets carry `@default` (`schema.prisma:106, 141, 142, 259, 321`); `writable_fields` at `htmx_generator.py:106-129`, `_is_required` at `:138`. The `form_prose` sentence was kept with FR-8 (consumer #1's subject), not deleted | 2026-08-14 |
| R1-F2 | Amend FR-3's Verify to a **predicted added-drift set** + subset test, replacing "exclusively the three onboarding kinds" | Composer R1 | **APPLIED** to FR-3 Verify as a 5-row predicted-set table with expected drift labels and the mechanism for each. Re-verified on disk: `app/web.py`, `app/nav.py`, `app/index.py` all carry `forms-sha256: 1c4898693fa9…`; `app/main.py` carries none (schema-only ⇒ tampered). Two clarifications added beyond the suggestion: the second `--check` is explicitly **post-declaration / pre-write** (otherwise "added drift" is undefined), and FR-5's transcript is relabelled the **post-write** one. R1's "six artifacts" count in focus ask A2 conflicts with its own 7-member enumeration; merged as a **set**, not a count | 2026-08-14 |
| R1-F3 | Give FR-7 a verdict-selection rule for all three verdicts; require the note to name its friction items | Composer R1 | **APPLIED** to FR-7 Verify as a 3-row selection-rule table. Strengthened per R1's own validation approach: the two known friction candidates (`TreeNode` required-FK dead-end; any unresolved FR-3 carry-along) must be dispositioned explicitly, and the definitions must classify the household pilot note unambiguously or they are still too loose. `PORTABLE` additionally requires the **unchanged SDK sha** from plan-side `R1-S3`, not just an empty diff | 2026-08-14 |
| A1 (focus ask) | State what the FR-8 gate does and does not de-risk; give the Closure-Ledger gate a citable ID | Composer R1 | **APPLIED** to FR-8 as a Scope paragraph + gate ID **`CL-54`** (next free row after CL-53 in `dev-os/CLOSURE-LEDGER.md`, confirm on filing), which the FR-7 note must cite verbatim so "filed and cited" is greppable. Grounded: `navig8/prisma/` holds only `schema.prisma`, `views.yaml`, `human_inputs.yaml` — the household failure class is unreachable here | 2026-08-14 |
| A3 (focus ask) | Record that the `pages.yaml` exclusion costs no discoverability | Composer R1 | **APPLIED** to Non-goals: `redirect_root_if_empty` defaults `False` (`onboarding_manifest.py:40, 86-88`) so omission is the documented no-op path, and the welcome `NavEntry` is registered from `views.yaml` alone (`nav_generator.py:91-99`). Also noted in Appendix B beside the original rejection | 2026-08-14 |
| R1-S2 (cross-file) | The required-FK dead-end is FR-2's failure shape via a mechanism FR-2 does not model | Composer R1 (plan-side) | **APPLIED** requirement-side as an FR-2 **Scope limit** plus a Non-goals consequence under FK pickers — so the gap is documented where FR-2 is read, not only where S4 is executed. `TreeNode.treeId String` confirmed to have no `@default` (`schema.prisma:132`) | 2026-08-14 |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none) | — | Composer R1 | R1 produced 3 requirement-side suggestions and 3 plan-side; **all 6 accepted**. This row records that triage ran and rejected nothing, so a later reviewer does not read an empty table as "untriaged" | 2026-08-14 |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — Composer — 2026-08-14

- **Reviewer**: Composer
- **Date**: 2026-08-14 16:40:00 UTC
- **Scope**: CRP-lite, 1 round, dual-document (Feature Requirements). Weighted to the sponsor focus file:
  the FR-8 pre-flight gate, sufficiency of the FR-3 two-`--check` bracket, `pages.yaml` scope creep, and
  negative-verdict falsifiability. The four numbered focus asks are answered in full on the **plan**
  file's R1 block (`ONBOARDING_SECOND_CONSUMER_PLAN.md`, Appendix C) to keep one copy; the requirement-side
  deltas they imply are `R1-F1`–`R1-F3` below. Plan-side items are `R1-S1`–`R1-S3` there.

**Executive summary**

- FR-3's Verify is **falsified by construction**: `forms_stale_reason` hashes the *whole* `views.yaml`
  into `forms-sha256` (`backend_codegen/drift.py:849-870`), and navig8's `app/web.py`, `app/nav.py`,
  `app/index.py` all carry `forms-sha256: 1c4898693fa9…` today — so declaring `onboarding:` re-stales
  three artifacts that are not onboarding kinds. "Added drift is exclusively the three onboarding kinds"
  cannot hold on a correct run.
- FR-2's second Verify limb is **unfalsifiable on the selected consumer**: `navig8/prisma/` holds only
  `schema.prisma`, `views.yaml`, `human_inputs.yaml` — there is no `form_prose.yaml`, so the
  `form_prose.yaml: … unknown form field` error can never be raised.
- FR-2's *mechanism* does genuinely clear on navig8, for a reason the REQ does not state: all five owned
  targets carry schema defaults, so none is required-on-create once `_writable_fields` strips it. Saying
  this makes the FR-2 pass auditable instead of asserted.
- The uncovered first-run dead-end is a **required scalar FK**, not an owned field: `TreeNode.treeId` has
  no default and survives `_writable_fields`, so the drafted `empty_states: TreeNode` checklist item
  points at a form needing a hand-typed CUID while FK pickers are a Non-goal (plan-side `R1-S2`).
- FR-7 names three verdicts but supplies a selection rule for only one, leaving
  `PORTABLE-WITH-FRICTION` unfalsifiable.
- Positive grounding, no action needed: the S4 draft block uses only keys present in
  `onboarding_manifest.py:18-24`; the `storage_key` default (`onboarding_tips_dismissed`) matches the
  smoke grep; `continue_href: /ui/decisiontree` is a real navig8 route (`app/web.py:63`); and the
  Appendix-B `pages.yaml` rejection costs no discoverability, since `nav_generator.py:91-99` registers the
  welcome NavEntry from `views.yaml` alone.
- Not re-proposed (settled in Appendix B): benchmark-portal / attorney-portal retrofit, and adding a
  `pages.yaml` to navig8.

**Feature requirements suggestions**

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F1 | Validation | high | Re-cut FR-2's Verify into one limb that can fail on navig8 and one scoped to consumer #1. Replace "and `generate backend … --check` raises no `form_prose.yaml: … unknown form field` error" with a mechanism-level criterion: for each declared `empty_states` entity, the intersection of that entity's `human_inputs.yaml` targets and its required-on-create scalars (no schema default, not optional) is empty — and state that navig8 passes because all five owned targets are defaulted | The `form_prose` limb is vacuously true for the selected consumer: `navig8/prisma/` contains no `form_prose.yaml`, so that error is unreachable and the criterion yields zero signal. The defaults check is the actual generalizable form of the household `dose` failure (`_writable_fields`, `htmx_generator.py:106-129`) and it *can* fail on a future consumer | § Functional requirements, FR-2 Verify clause; keep the `form_prose` sentence in FR-8 where consumer #1 is the subject | Re-run the criterion against household (must fail on `Medication.dose`) and navig8 (must pass) — a criterion that passes both is still too weak |
| R1-F2 | Validation | high | Amend FR-3's Verify: the post-declaration run's added drift must equal a **predicted set** — the three onboarding kinds plus the artifacts that carry `forms-sha256` (`app/web.py`, `app/nav.py`, `app/index.py`, stale) and `app/main.py` (tampered, schema-only hash) — rather than "exclusively the three onboarding kinds" | `forms_stale_reason` states the hash "covers the whole `views.yaml` … so composite-view edits conservatively re-stamp these files" (`drift.py:849-870`); `_FORMS_KINDS` and `_NAV_KINDS` (`drift.py:83-90, 114-116`) put `fastapi-web-forms` and the nav kinds in that dep-set, and navig8's headers confirm all three carry the current views hash. `app/nav.py` also changes in content, gaining a real onboarding `NavEntry` (`nav_generator.py:91-99`). As written the requirement makes a correct pilot look like a failed one — and worse, invites narrating the extra rows away, which is the judgement call the bracket exists to eliminate | § Functional requirements, FR-3 Verify clause; mirrored in plan S5 (`R1-S1`) | Execute the bracket on navig8 and confirm the observed added-drift set is exactly the predicted set; any unpredicted member is a real defect and stops the pilot |
| R1-F3 | Risks | medium | Give FR-7 a verdict-selection rule, not just a verdict vocabulary: define `PORTABLE` as zero consumer-specific work beyond human-authored prose and an empty `backend_codegen/` diff; `PORTABLE-WITH-FRICTION` as an empty SDK diff plus at least one named, recorded consumer-specific workaround (residual drift, a dropped `empty_states` entity, a manual step); `NOT-PORTABLE` as any required change under `src/startd8/backend_codegen/`. Require the note to name the friction items it counted | FR-7's Verify only pins the `NOT-PORTABLE` case ("a pilot that required SDK edits reads `NOT-PORTABLE`"). With no boundary between the other two, the middle verdict absorbs any amount of friction and O-3's falsifiability claim weakens to a narrative choice — the same optimism the REQ's own survivorship framing warns against. Two concrete friction candidates already exist: the `TreeNode` required-FK dead-end and the `R1-F2` carry-along drift | § Functional requirements, FR-7 Verify clause; the plan's § Decision rule if navig8 fails gains the matching branch | Apply all three definitions to the household pilot note retroactively — if it cannot be classified unambiguously, the definitions are still too loose |

**Endorsements & Disagreements:** none — Appendix C had no prior rounds. Note that this document also
carries a native `## Appendix C — Incoming review rounds` section reading `_(none yet)_`; it was left
unmodified under the append-only scope lock, and this round is filed here in the generator-created
Appendix C.
