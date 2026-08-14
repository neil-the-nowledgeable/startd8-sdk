# `onboarding:` Second Cascade Consumer — Plan

**Pairs with:** [`ONBOARDING_SECOND_CONSUMER_REQUIREMENTS.md`](./ONBOARDING_SECOND_CONSUMER_REQUIREMENTS.md) **v0.4 (post-CRP-lite R1)** · **Date:** 2026-08-14
**Selected consumer:** **navig8** (`~/Documents/dev/navig8`) · **Fallback:** strtd8-v2-cascade
**Status:** planned — not executed. No step below has been run as a write.
**Sync:** synced to REQ v0.4 on 2026-08-14 — `R1-S1`–`R1-S3` and focus asks A1/A3/A4 merged (Appendix A).

---

## Why this plan is bracketed rather than linear

navig8's `app/` is **one SDK generation behind** — measured, not assumed. All 12 drifted artifacts read
`tampered`, but the cause is staleness, not hand-editing: `app/web.py` contains **0** occurrences of
`_form_errors` where household's contains **15**, and the entity `form.html` templates predate the
FR-FH-11 layout. So navig8's baseline drift *is* PR #463's shipped surface — the very change set that
made `onboarding:` possible. Regenerating navig8 pulls it forward rather than fighting local edits,
which is what makes it a low-risk pilot; but it also means a single regeneration would fuse the
archetype delta into a 12-file catch-up. Hence S3 and S5a: two `--check` transcripts bracketing the
declaration itself — the second taken **before** the regeneration write, so the onboarding delta is
attributable (FR-3, O-2). S5b's post-write run is a third transcript that proves the result green (FR-5);
it is not part of the bracket, because after a write everything is in sync and nothing is attributable.

### The predicted added-drift set (R1-S1) — declare it before you run it

The bracket is the right instrument, but a naive pass condition ("added drift is exactly the three
onboarding kinds") is **falsified by construction**. `forms_stale_reason` hashes the *whole* `views.yaml`
— "The hash covers the whole `views.yaml` … so composite-view edits conservatively re-stamp these files"
(`drift.py:849-870`) — and navig8 already carries the current views hash in three non-onboarding
artifacts. Adding an `onboarding:` block changes that hash, so those three go stale on a *correct* run.
A fully successful S5a would have failed its own gate, and the operator's only way out would be to explain
the extra rows away — the judgement call the bracket exists to remove.

So the set is predicted **in advance** and the pass condition is a subset test:

| Predicted member | Kind | Expected label | Mechanism |
|------------------|------|----------------|-----------|
| `app/onboarding/*`, `app/templates/onboarding/*` | `fastapi-onboarding`, `onboarding-welcome`, `onboarding-aggregator` | new | The onboarding delta proper |
| `app/web.py` | `fastapi-web-forms` | stale | Carries `forms-sha256`; in `_FORMS_KINDS` (`drift.py:83-90`) |
| `app/nav.py` | `nav-registry` | stale **+ real content change** | Carries `forms-sha256`; in `_NAV_KINDS` (`drift.py:114-116`). Gains `NavEntry(key="onboarding:/welcome")` (`nav_generator.py:91-99`) |
| `app/index.py` | `nav-index-router` | stale | Carries `forms-sha256` |
| `app/main.py` | `fastapi-main` | **tampered**, not stale | Its hash is schema-only (not in `_FORMS_KINDS`), so the `views.yaml` edit leaves the hash *matching* while the expected content now carries the `onboarding_routers` mount the file lacks — surfacing as tamper, not staleness |

Verified on disk 2026-08-14: `app/web.py:5`, `app/nav.py:5`, `app/index.py:5` all carry
`forms-sha256: 1c4898693fa93ccdfc24e353b4f37c15193bb3e1a0e6dd6e89979405a705db00`; `app/main.py` carries
no `forms-sha256` header at all. **Pass = observed added drift ⊆ predicted set. Any unpredicted member
stops the pilot** and is investigated as a real defect, never narrated.

## The recipe (FR-3) — navig8's verified flag set

Derived from the census runs on 2026-08-14. navig8 has **no** `pages.yaml`, `form_prose.yaml`,
`display.yaml`, `completeness.yaml`, or `ai_passes.yaml`, and **does** ship the nav layer
(`app/nav.py`, `app/index.py` exist) — so unlike household's recipe there is **no `--no-nav`**.

```bash
SCHEMA=prisma/schema.prisma
VIEWS=prisma/views.yaml
HUMAN_INPUTS=prisma/human_inputs.yaml
BACKEND_FLAGS="--schema $SCHEMA --views $VIEWS --human-inputs $HUMAN_INPUTS"

startd8 generate backend $BACKEND_FLAGS --check    # READ-ONLY
startd8 generate backend $BACKEND_FLAGS --out .    # WRITES
```

Omitting `--human-inputs` inflates the count from 12 to 13 and relabels files `stale` instead of
`tampered` — proof that "drifted" is meaningless without the recorded flag set, which is why FR-3
demands the recipe before the number.

**Baseline RESIDUAL (pre-declaration, measured 2026-08-14 — 12 artifacts):**

`app/main.py` · `app/nav.py` · `app/web.py` · `app/templates/base.html` ·
`app/templates/{citation,decisiontree,landmineentry,landmineregister,perspective,screeninglink,sequenceconfig,treenode}/form.html`

Target after S3: **0**. Unlike household's residual, none of these is expected to survive
regeneration — if any does, it is a genuine hand-edit and S3 stops for review.

## Preconditions (abort gates)

| # | Gate | Check | If it fails |
|---|------|-------|-------------|
| G1 | Prior consumer re-verified (FR-8) | `cd ~/Documents/dev/household/household-o11y && make check` | Currently **FAILS**: `form_prose.yaml: entry 'Medication' references unknown form field 'dose'` (reproduced on `/opt/homebrew/bin/startd8` and the SDK venv; `Medication.dose` exists on the schema and is declared `authored_by: human`, so `writable_fields` strips it from the form). File it as Closure-Ledger gate **`CL-54`** (next free row after CL-53, 2026-08-14 — confirm on filing) and cite that ID verbatim in S8. Do **not** fix it here, and do **not** write a `PORTABLE` verdict while it is open. **Scope (R1-A1) — what this gate does and does not de-risk:** it protects the *two-proven-consumers claim* against a lying green upstream. It does **not** protect navig8's regeneration path, which is structurally immune: `navig8/prisma/` has no `form_prose.yaml`, so this failure class is unreachable here. Do not read G1 as a baseline guard for this pilot |
| G2 | SDK on `origin/main`, clean tree, **sha recorded** | `git -C ~/Documents/dev/startd8-sdk status --short && git rev-parse HEAD` | Rebase before starting; a pilot run against a dirty SDK proves nothing. **Write the `rev-parse HEAD` sha into the S8 note (R1-S3)** — S6 re-asserts it. Without the recorded sha, S6's empty diff cannot distinguish "no SDK change was needed" from "an SDK change was made and committed mid-pilot", which is the pilot's central claim (O-1, FR-4) |
| G3 | Which `startd8` | `which startd8; ls ~/Documents/dev/startd8-sdk/.venv/bin/startd8` | Two binaries exist (`/opt/homebrew/bin/startd8` + the SDK venv). Pin **one** for every transcript and record which — mixing them silently changes what "green" means |
| G4 | navig8 tree clean + backed up | `git -C ~/Documents/dev/navig8 status --short` | S3 overwrites 12 files; commit or stash first so the catch-up is reviewable as its own diff |

## Steps

| # | Action | File(s) / command | FR | Done |
|---|--------|-------------------|-----|------|
| S1 | Re-run the census; confirm the six rows and their drift numbers still reproduce | `generate backend … --check` per consumer (REQ § Candidate census) | FR-1 | ☐ |
| S2 | Confirm the FR-2 collision gate for navig8 **by the v0.4 mechanism criterion**: for each declared `empty_states` entity, owned targets ∩ required-on-create scalars (non-optional, non-list, **no schema default**) = ∅. Record the five defaults as the audit trail. Sanity-check the criterion against household — it **must fail** on `Medication.dose`, or it is too weak to certify navig8 | `navig8/prisma/human_inputs.yaml` × `schema.prisma` defaults × chosen `empty_states` entities | FR-2 | ☐ |
| S3 | **Baseline catch-up.** Run the recipe as a write; re-`--check` to **0**; commit the 12-file catch-up **alone**, no `onboarding:` yet | `navig8/app/**` | FR-3 | ☐ |
| S4 | Declare `onboarding:` in navig8's `views.yaml` using archetype FR-1/FR-2 keys only (draft below) | `navig8/prisma/views.yaml` | FR-4 | ☐ |
| S5a | **Pre-write `--check`** (read-only, straight after the S4 edit): capture the second bracket transcript. **Pass = observed added drift ⊆ the predicted set** (§ The predicted added-drift set); any unpredicted member **stops the pilot**. Expect mixed labels — 3 onboarding kinds new, `web.py`/`nav.py`/`index.py` stale, `main.py` tampered | `generate backend $BACKEND_FLAGS --check` | FR-3 | ☐ |
| S5b | **Regenerate** (write), then a **third `--check`**: the three onboarding kinds in sync and every predicted carry-along resolved. Confirm `app/main.py` gained the `onboarding_routers` try/except mount (absent today) and `app/nav.py` gained the onboarding `NavEntry` | `navig8/app/onboarding/*`, `app/templates/onboarding/*`, `app/main.py`, `app/nav.py` | FR-5 | ☐ |
| S6 | Assert no SDK change was needed — **both** limbs (R1-S3): the diff is empty **and** the sha is unchanged from G2 | `git -C ~/Documents/dev/startd8-sdk diff --stat src/startd8/backend_codegen/` → empty; `git -C … rev-parse HEAD` → **identical to the G2 sha** | FR-4 | ☐ |
| S7 | Runtime smoke on an empty DB; then seed one row and re-check the checklist. **Also probe the required-FK dead-end (R1-S2):** `GET /ui/treenode/new` and record whether any required input has no user-supplyable value — outcome goes in S8 either way, pass or fail. Fold in the navig8 doc-drift repair found while grounding (`CLAUDE.md` claims no `app/`; `docs/ASSEMBLY_INPUTS.yaml` marks `views: absent` — both false) | `run.sh` / `uvicorn app.main:app`; `navig8/CLAUDE.md`, `navig8/docs/ASSEMBLY_INPUTS.yaml` | FR-6 | ☐ |
| S8 | Write `_PILOT_2026-08-NN_onboarding-navig8.md` with **all three** transcripts (S3 residual-0, S5a pre-write, S5b post-write), the G2/S6 sha pair, the `TreeNode` probe result, and one verdict selected by the **FR-7 rule table** — not narrated. **Enumerate the friction items counted.** Cite ledger gate **`CL-54`** by ID | new pilot note beside this plan | FR-7, FR-8 | ☐ |
| S9 | Propagate (CL-21): update the archetype REQ's dogfood line + `_PILOT_…household.md` companions to name the third surface, and record the verdict | `ONBOARDING_ARCHETYPE_REQUIREMENTS.md` | FR-7 | ☐ |

## S4 — draft `onboarding:` block for navig8 (prose is human-owned; this is a starting point)

Uses only archetype FR-1/FR-2 keys. `redirect_root_if_empty` is deliberately **absent** — navig8 has no
`pages.yaml` owning `/`, and adding one to exercise an optional flag is a Non-goal.

**Skipping `pages.yaml` does not make `/welcome` unreachable (R1-A3).** `nav_generator.py:91-99` registers
the onboarding `NavEntry` from `views.yaml` alone, and navig8 ships the nav layer (`app/nav.py`,
`app/index.py`), so the Welcome entry appears regardless. The flag itself defaults to `False`
(`onboarding_manifest.py:40, 86-88`), so omitting it is the documented no-op path, not an untested branch.
This is also why `app/nav.py` re-drifts in S5a — expected, not noise.

```yaml
onboarding:
  route: /welcome
  title: Getting oriented
  nav_label: Welcome
  lead: >
    navig8 walks you through a legal situation with fixed if/then questions — no AI writes
    anything you read here. Trees ship as "candidate — not yet attorney-validated" until a
    licensed attorney signs off; each tree shows its own status.
  continue_href: /ui/decisiontree
  tips:
    - Start with a Decision Tree — nodes, perspectives and citations all hang off one tree
    - A node marked referral_trigger is a hand-off point, not advice
    - Landmine registers are catalogued separately and linked to nodes by screening
  empty_states:
    DecisionTree: Create a decision tree for one area of law to get started.
    LandmineRegister: Start a register if you are cataloguing formation failure modes.
    # TreeNode intentionally omitted — see the required-FK note below (R1-S2)
```

**Why `TreeNode` is *not* an `empty_states` entity (R1-S2).** `TreeNode.treeId` is a required scalar FK
with **no default** (`navig8/prisma/schema.prisma:132`). It is not a relation field, not in
`_PROVENANCE_OMIT`, and not owned, so `writable_fields` keeps it (`htmx_generator.py:106-129`) and the
generated create form asks a first-run user to hand-type a raw CUID. A checklist item pointing at a form
a first-run user cannot complete is FR-2's failure *shape* arriving through a mechanism FR-2 does not
model, and FK picker widgets are an explicit Non-goal — so it cannot be fixed in-pilot. Dropping it keeps
the checklist honest; the entity is still **probed** at S7 (`GET /ui/treenode/new`) and the result recorded
in S8 either way. If a later pass restores `TreeNode`, it is FR-7 friction with this named cause, and the
verdict is `PORTABLE-WITH-FRICTION` at best.

**Copy review before S7** (trust boundary, REQ § Risks): tips must stay navigational. No tip may state,
paraphrase, or reassure about a `validationStatus` — that string is attorney-gate-owned and is rendered
verbatim by the app. Reviewed against navig8's UPL invariant (`nodeType=referral_trigger` requires
`uplClass=must_not_cross`).

## FR-6 smoke (S7)

```bash
cd ~/Documents/dev/navig8 && ./run.sh   # or: uvicorn app.main:app
BASE=http://127.0.0.1:8000

curl -sS -o /dev/null -w "welcome %{http_code}\n" $BASE/welcome              # expect 200
curl -sS $BASE/welcome | grep -c "Create a decision tree"                     # expect >=1 on empty DB
curl -sS $BASE/welcome | grep -ci 'role="dialog"'                             # expect 0 (PC-13: content, not modal)
curl -sS $BASE/welcome | grep -o 'onboarding_tips_dismissed'                  # storage_key present
# then create one DecisionTree via /ui/decisiontree and re-fetch:
curl -sS $BASE/welcome | grep -c "Create a decision tree"                     # expect 0; other items remain

# R1-S2 probe — record the outcome in S8 whether it passes or fails:
curl -sS $BASE/ui/treenode/new | grep -o 'name="treeId"[^>]*required'         # required raw-CUID input?
```

The `treenode` probe is **evidence, not a gate** — `TreeNode` is not a declared `empty_states` entity
(see the S4 note), so a required `treeId` input does not fail FR-6. It is recorded so the FK-picker
Non-goal has a measured cost instead of an assumed one.

## Decision rule if navig8 fails

Apply in order; do not improvise a new candidate mid-pilot.

1. **S3 leaves residual drift** (a file survives regeneration ⇒ a real hand-edit): keep navig8, document
   the residual in the recipe exactly as household's Makefile does, and proceed. This is friction, not
   failure — and it is a **named friction item**, so the verdict ceiling drops to
   `PORTABLE-WITH-FRICTION`.
2. **S5a shows an unpredicted added-drift member** (not in § The predicted added-drift set): stop and
   investigate before regenerating. An unpredicted member means either the prediction is wrong (fix the
   prediction, re-derive, re-run — the transcript pair is void) or the declaration touched more than the
   onboarding seam (a real defect). Do **not** proceed by explaining the row away; that is the exact
   judgement call the bracket removes.
3. **S6 fails either limb** — a non-empty `backend_codegen/` diff **or** a sha that moved from G2 (the
   SDK had to change): stop. Verdict is `NOT-PORTABLE`; the archetype's portability status is downgraded
   and the required SDK change becomes its own REQ. Do **not** switch consumers to find a greener one —
   that is the survivorship error this REQ exists to avoid.
4. **S7 fails at runtime with an empty S6** (e.g. `/welcome` 200s but a declared empty-state string is
   absent, or the aggregator errors on an empty DB) — the case v0.2 had no branch for (R1-A4). Classify
   by where the fix must land: fixable in the **consumer** (prose, manifest, seed data) ⇒
   `PORTABLE-WITH-FRICTION` with the defect named and recorded; fixable only under
   `src/startd8/backend_codegen/` ⇒ `NOT-PORTABLE`, whether or not the fix is actually written during
   the pilot. A deferred SDK-side fix is still a required SDK change.
5. **navig8 is structurally unusable** (e.g. its schema cannot support a meaningful checklist): fall
   back to **strtd8-v2-cascade** (16 entities, 84 drifted, no hand-built onboarding) and re-run from S1.
   Its higher drift makes S3 the dominant cost; budget for it.
6. **Never** fall back to the benchmark portal or the attorney portal — both are Non-goals.

### Verdict thresholds (FR-7's rule table, restated for the operator)

Select, do not narrate. `PORTABLE` requires an empty `backend_codegen/` diff, the **unchanged G2 sha**,
and **zero** consumer-specific work beyond human-authored prose. Any single named workaround — surviving
residual drift, a dropped or degraded `empty_states` entity, a manual step, a consumer-side runtime fix —
lands `PORTABLE-WITH-FRICTION`, and the S8 note must **enumerate the items counted**. Any required change
under `src/startd8/backend_codegen/` is `NOT-PORTABLE`. Note that the drafted block already carries one
pre-recorded friction candidate (`TreeNode` dropped from `empty_states`), so `PORTABLE` is not the
default outcome — it must be earned against the dropped entity being judged a *scope choice* rather than a
workaround, and that judgement itself belongs in the note.

## Deliberately not in this plan

Executing the dogfood (this pass is spec-only), fixing the household `form_prose` regression, any edit
under `src/startd8/backend_codegen/`, FK pickers, per-list CRUD empty-states, `confirm-walk:`, Welcome
Mat / Concierge, and any git commit.

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

**R1 triaged 2026-08-14 — 3 of 3 plan-side suggestions ACCEPTED, 0 rejected; all four focus-ask deltas
applied.** Requirement-side `R1-F1`–`R1-F3` are dispositioned in the paired REQ's Appendix A (v0.4).

| ID | Suggestion | Source | Implementation / Validation Notes | Date |
|----|------------|--------|-----------------------------------|------|
| R1-S1 | Replace S5's "added drift must be exactly the three onboarding kinds" with a **predicted added-drift set** + subset test | Composer R1 | **APPLIED.** New § *The predicted added-drift set* under § Why this plan is bracketed, carrying a 5-row table with expected drift labels and the mechanism for each member; S5 **split into S5a (pre-write `--check`, the subset test) and S5b (regenerate + third `--check`)** because "added drift" is only defined pre-write — the v0.2 single-row S5 conflated the two. Re-verified on disk: `app/web.py:5`, `app/nav.py:5`, `app/index.py:5` all carry `forms-sha256: 1c4898693fa9…`; `app/main.py` has no such header (schema-only ⇒ tampered). Decision-rule branch 2 added for an unpredicted member | 2026-08-14 |
| R1-S2 | Drop `TreeNode` from the S4 draft `empty_states` (or keep it and pre-record it as FR-7 friction with a named cause) | Composer R1 | **APPLIED — dropped**, with the reason recorded inline in the YAML and a full note beneath it. Grounded: `TreeNode.treeId String` at `navig8/prisma/schema.prisma:132` has no `@default`, is not a relation field, not in `_PROVENANCE_OMIT`, not owned ⇒ survives `writable_fields` (`htmx_generator.py:106-129`) as a required raw-CUID input. R1's validation approach kept as well: S7 still probes `GET /ui/treenode/new` and S8 records the outcome either way, so the FK-picker Non-goal has a measured cost. Also surfaced requirement-side as FR-2's Scope limit + a Non-goals consequence | 2026-08-14 |
| R1-S3 | Pin and re-assert the SDK commit sha, not just a clean diff | Composer R1 | **APPLIED** to G2 (record `git rev-parse HEAD`) and S6 (assert **both** limbs: empty diff **and** unchanged sha). Decision-rule branch 3 now reads "fails either limb". Carried into the REQ: `PORTABLE` in FR-7's selection table requires the unchanged sha, not just the empty diff, so the sha anchor is normative rather than procedural | 2026-08-14 |
| A1 | State G1's scope; give the ledger gate a citable ID | Composer R1 (focus ask) | **APPLIED** to G1: added the does/does-not-de-risk sentence (protects the two-proven-consumers claim, **not** navig8's baseline — no `form_prose.yaml` in `navig8/prisma/`, so the class is unreachable) and gate ID **`CL-54`** (next free after CL-53 in `dev-os/CLOSURE-LEDGER.md`; confirm on filing), which S8 must cite verbatim. Mirrored in FR-8 | 2026-08-14 |
| A2 | Bracket is the right instrument but S5's pass condition is falsified by construction | Composer R1 (focus ask) | **APPLIED** via `R1-S1` above. R1's own count of "six artifacts" was not carried over: its enumeration lists **seven** members (3 onboarding + `web.py` + `nav.py` + `index.py` + `main.py`). The plan states the set **by member**, so the subset test is unaffected by the slip | 2026-08-14 |
| A3 | Note that the welcome route stays discoverable without `pages.yaml` | Composer R1 (focus ask) | **APPLIED** as a paragraph under the S4 draft: `nav_generator.py:91-99` registers the `NavEntry` from `views.yaml` alone; `redirect_root_if_empty` defaults `False` (`onboarding_manifest.py:40, 86-88`). Doubles as the explanation for `app/nav.py`'s expected S5a re-drift. Mirrored in the REQ's Non-goals | 2026-08-14 |
| A4 | Add a decision-rule branch for an S7 runtime failure | Composer R1 (focus ask) | **APPLIED** as decision-rule branch 4, classified by *where the fix must land* (consumer ⇒ `PORTABLE-WITH-FRICTION` + named defect; `backend_codegen/` ⇒ `NOT-PORTABLE`, even if deferred). New § *Verdict thresholds* restates FR-7's rule table for the operator and notes that the dropped `TreeNode` entity already puts `PORTABLE` in question | 2026-08-14 |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none) | — | Composer R1 | R1's 3 plan-side suggestions and 4 focus-ask deltas were **all accepted**. Recorded so a later reviewer can distinguish "nothing rejected" from "not yet triaged". The standing rejections (benchmark-portal / attorney-portal retrofit, adding `pages.yaml` to navig8) predate R1 and live in the REQ's Appendix B | 2026-08-14 |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — Composer — 2026-08-14

- **Reviewer**: Composer
- **Date**: 2026-08-14 16:40:00 UTC
- **Scope**: CRP-lite, 1 round, dual-document. Weighted to the sponsor focus file (FR-8 gate, bracket
  sufficiency, `pages.yaml` scope creep, negative-verdict falsifiability). Targeted grounding in
  `backend_codegen/drift.py`, `onboarding_manifest.py`, `nav_generator.py`, `htmx_generator.py`, and
  navig8's on-disk artifact headers + `prisma/`. Requirements-side items (`R1-F*`) are in the paired REQ.

##### Sponsor focus asks

**A1 — Is the FR-8 household `form_prose` / `human_inputs` pre-flight gate right?**

- **Summary answer:** Right as a *survivorship* gate on consumer #1; mis-framed if read as protecting
  *this* pilot's baseline, and its FR-2 companion verify limb cannot fail on navig8.
- **Rationale:** `navig8/prisma/` contains exactly `schema.prisma`, `views.yaml`, `human_inputs.yaml` —
  there is **no `form_prose.yaml`**, so the household failure class (`form_prose.yaml: entry 'Medication'
  references unknown form field 'dose'`) is structurally unreachable here. Separately, the *mechanism*
  behind it does clear on navig8 for a reason the docs do not yet state: all five owned targets carry
  schema defaults (`TreeNode.confidence @default(medium)`, `TreeNode.attorneyNote @default("")`,
  `DecisionTree.validationStatus` / `SequenceConfig.validationStatus` both defaulted), so none is
  *required on create* after `_writable_fields` strips it (`htmx_generator.py:106-129`). G1 is therefore
  a correct blocking gate on the *portability claim* (a lying green upstream), not on navig8's own run.
- **Assumptions / conditions:** navig8 gains no `form_prose.yaml` before the pilot; household's `dose`
  failure is not repaired mid-pilot (an explicit Non-goal).
- **Suggested improvements:**
  - In G1's "If it fails" cell, say what the gate does **and does not** de-risk: it protects the
    two-proven-consumers claim, not this pilot's regeneration path.
  - Give the Closure-Ledger gate a placeholder **ID** in G1 and require S8 to cite that ID, so FR-8's
    "filed and cited" is checkable rather than narrative.
  - See `R1-F1` for the requirement-side fix to FR-2's unfalsifiable verify limb.

**A2 — Is the baseline-green bracket (two `--check` runs) enough attribution?**

- **Summary answer:** No — the bracket is the right instrument, but S5's pass condition is falsified by
  construction and will read as a failure on a correct run.
- **Rationale:** `forms_stale_reason` hashes the **whole** `views.yaml` into `forms-sha256` ("The hash
  covers the whole `views.yaml` … so composite-view edits conservatively re-stamp these files",
  `drift.py:849-870`). navig8's on-disk headers show three artifacts already carrying
  `forms-sha256: 1c4898693fa9…` — `app/web.py` (`fastapi-web-forms`), `app/nav.py` (`nav-registry`),
  `app/index.py` (`nav-index-router`). The moment S4 adds `onboarding:` to `views.yaml`, that hash
  changes and all three go **stale** alongside the three onboarding kinds. `app/nav.py` additionally
  changes in *content*, not just header: `nav_generator.py:91-99` appends a real
  `NavEntry(key="onboarding:/welcome")`. And `app/main.py` (`fastapi-main`, schema-only hash, not in
  `_FORMS_KINDS`) will read **tampered** rather than stale when it gains the mount. So the predicted S5
  added-drift set is **six** artifacts with mixed labels, not "exactly the three onboarding kinds".
- **Assumptions / conditions:** S3 truly reaches 0 first; the same pinned binary and flag set are used
  for both transcripts (G3).
- **Suggested improvements:** `R1-S1` (record the predicted set and change the pass condition) and
  `R1-F2` (the normative twin in FR-3's Verify).

**A3 — Scope creep into `pages.yaml` / `redirect_root_if_empty` on navig8?**

- **Summary answer:** No creep, and the exclusion is cheaper than the docs claim — worth saying so.
- **Rationale:** `redirect_root_if_empty` defaults to `False` (`onboarding_manifest.py:40, 86-88`), so
  omitting it is the documented no-op path, not an untested branch. More usefully, the welcome route
  stays **discoverable without** a pages layer: `nav_generator.py:91-99` registers the onboarding
  NavEntry from `views.yaml` alone, independent of `pages.yaml`. navig8 ships the nav layer, so the
  Welcome entry appears in `app/nav.py` regardless. The Appendix-B rejection therefore costs no
  first-run discoverability — only the optional root-redirect branch goes unexercised.
- **Assumptions / conditions:** navig8 keeps shipping `app/nav.py` / `app/index.py` (true today).
- **Suggested improvements:** Add one sentence under the S4 draft noting the nav entry arrives via
  `nav_generator` from `views.yaml`, so a reader does not infer that skipping `pages.yaml` leaves
  `/welcome` unreachable. This also explains the `app/nav.py` re-drift in `R1-S1` as expected, not noise.

**A4 — Pilot-note falsifiability if the verdict is negative?**

- **Summary answer:** Partial — three verdicts are named but only one has a decision procedure.
- **Rationale:** "## Decision rule if navig8 fails" maps S3-residual → friction and S6-non-empty →
  `NOT-PORTABLE`, but nothing maps an **S7 runtime failure** that is neither residual drift nor an SDK
  edit (e.g. `/welcome` 200s yet an empty-state string is absent, or the aggregator errors on an empty
  DB). Nor is there any threshold separating `PORTABLE` from `PORTABLE-WITH-FRICTION`, so the middle
  verdict is currently unfalsifiable — any friction can be narrated either way.
- **Assumptions / conditions:** none.
- **Suggested improvements:** Add a fifth decision-rule branch for S7 failures (runtime failure with an
  empty S6 diff ⇒ `PORTABLE-WITH-FRICTION` plus a named defect, or `NOT-PORTABLE` if the fix must land
  in `backend_codegen/`); and see `R1-F3` for the requirement-side verdict thresholds.

##### Plan suggestions

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-S1 | Validation | high | Replace S5's "Added drift must be exactly the three onboarding kinds" with a **predicted added-drift set** and a subset test: the 3 onboarding kinds (`fastapi-onboarding`, `onboarding-welcome`, `onboarding-aggregator`) plus 3 views-hash carry-alongs `app/web.py`, `app/nav.py`, `app/index.py` (stale) and `app/main.py` (tampered). Pass = added drift is a subset of the predicted set with no unpredicted member | `forms-sha256` covers the whole `views.yaml` (`drift.py:849-870`); navig8's `web.py`, `nav.py`, `index.py` all carry `forms-sha256: 1c4898693fa9…` today, so declaring `onboarding:` re-stales them. As worded, a fully correct S5 fails its own gate and invites the operator to explain the extra rows away — the exact judgement call the bracket exists to remove | § Steps, S5 row; expand § "Why this plan is bracketed rather than linear" with the predicted set | Run S5 on navig8 and diff the observed added-drift set against the predicted set; any unpredicted member stops the pilot |
| R1-S2 | Interfaces | high | Drop `TreeNode` from the S4 draft `empty_states` (or keep it and pre-record it as FR-7 friction with a named cause) | `TreeNode.treeId` is a required scalar FK with no default. It is not a relation field, not in `_PROVENANCE_OMIT`, and not owned, so `_writable_fields` keeps it (`htmx_generator.py:106-129`) — the generated create form asks a first-run user to hand-type a raw CUID. FK picker widgets are an explicit Non-goal, so this cannot be fixed in-pilot. The checklist item "Add the questions and info nodes that make up the tree" therefore points at a form a first-run user cannot complete: FR-2's failure *shape* arriving through a mechanism FR-2 does not cover | § S4 draft block, the `empty_states:` mapping; note the reason beside it | At S7, GET `/ui/treenode/new` and confirm whether any required input has no user-supplyable value; record the outcome in the S8 note either way |
| R1-S3 | Ops | medium | Pin and re-assert the SDK commit sha, not just a clean diff: record `git -C ~/Documents/dev/startd8-sdk rev-parse HEAD` at G2 and require S6 to assert the sha is **unchanged** as well as `git diff --stat src/startd8/backend_codegen/` being empty | On a clean tree `git diff --stat` is trivially empty, so S6 as written cannot distinguish "no SDK change was needed" from "an SDK change was made and committed mid-pilot". Since zero-SDK-change is the pilot's central claim (O-1, FR-4) and the negative verdict hinges on it, the check should be sha-anchored | § Preconditions, G2 row (record) and § Steps, S6 row (assert); carry both shas into the S8 note | Deliberately commit a no-op change under `backend_codegen/` in a scratch clone and confirm the sha assertion catches what `git diff` misses |

**Endorsements / Disagreements:** none — Appendix C was empty before this round, and the paired REQ's
native `## Appendix C — Incoming review rounds` still reads `_(none yet)_` (left untouched per the
append-only scope lock; this round is filed under the generator-created Appendix C in each file).

---

## Requirements Coverage Matrix — R1

Analysis only (no triage). Maps each major section / ID of
[`ONBOARDING_SECOND_CONSUMER_REQUIREMENTS.md`](./ONBOARDING_SECOND_CONSUMER_REQUIREMENTS.md) v0.2 to the
plan step(s) that execute it.

> **Read as of v0.2 (left intact, append-only).** Every `Partial` row below was dispositioned in the
> 2026-08-14 triage — see Appendix A above and the REQ's Appendix A. The step references also predate the
> S5 → **S5a / S5b** split. Gap → resolution: O-1 / FR-4 → `R1-S3` (sha anchor, G2+S6); O-2 / FR-3 / FR-5
> → `R1-S1` + `R1-F2` (predicted-set subset test); O-3 / FR-7 → `R1-F3` (verdict selection rule) and
> focus ask A4 (S7 branch); FR-2 → `R1-F1` (mechanism criterion) + `R1-S2` (`TreeNode` dropped); FR-8 →
> focus ask A1 (scope statement + gate `CL-54`).

| Requirement Section | Plan Step(s) | Coverage | Gaps |
| ---- | ---- | ---- | ---- |
| O-1 — consumer declares `onboarding:`, regenerates green, zero SDK change | S4, S5, S6 | Partial | S6's clean-diff assertion cannot distinguish "no change needed" from "change committed" (`R1-S3`) |
| O-2 — onboarding delta is attributable | § Why this plan is bracketed, S3, S5 | Partial | S5's pass condition excludes the views-hash carry-alongs it will actually observe (`R1-S1`) |
| O-3 — verdict is falsifiable and may be negative | S8, § Decision rule if navig8 fails | Partial | No branch for an S7 runtime failure; no `PORTABLE` vs `PORTABLE-WITH-FRICTION` threshold (focus ask A4, `R1-F3`) |
| Candidate census (grounded 2026-08-14) | S1 | Covered | — |
| FR-1 — census is an artifact, not a claim | S1 | Covered | — |
| FR-2 — owned-field collision disqualifies a candidate | S2 | Partial | Verify's `form_prose.yaml` limb is unreachable on navig8 (`R1-F1`); required-FK dead-end uncovered (`R1-S2`) |
| FR-3 — baseline-green precedes the onboarding delta | § The recipe, § Baseline RESIDUAL, S3, S5 | Partial | Recipe and residual set are recorded well; the *added*-drift criterion is falsified by the views.yaml whole-file hash (`R1-S1`, `R1-F2`) |
| FR-4 — declare with existing grammar only | S4 + § S4 draft block, S6 | Covered | Draft uses only keys in `onboarding_manifest.py:18-24`; grounded as valid |
| FR-5 — regeneration is green on the onboarding kinds | S5 | Partial | `app/main.py` will report **tampered** (schema-only hash), not stale — expected but unstated (`R1-S1`) |
| FR-6 — first-run smoke on the running app | S7 + § FR-6 smoke | Covered | Smoke greps the default `storage_key` (`onboarding_tips_dismissed`) correctly; `continue_href: /ui/decisiontree` verified to be a real route (`app/web.py:63`) |
| FR-7 — verdict is recorded and may be negative | S8, S9 | Partial | Verdict-selection thresholds absent (`R1-F3`) |
| FR-8 — prior-consumer re-verification | G1, S8 | Partial | Gate is correct but its scope is unstated, and the ledger gate has no citable ID (focus ask A1) |
| Risks table (7 rows) | G1–G4, § Copy review before S7, S3 | Covered | UPL / trust-boundary row is executed by the § Copy review paragraph |
| Non-goals (incl. `redirect_root_if_empty`, FK pickers) | § Deliberately not in this plan, § S4 draft note | Covered | Exclusion is sound and cheaper than stated (focus ask A3); note the FK-picker exclusion collides with the `TreeNode` empty-state (`R1-S2`) |
| Owned fields (human-authored prose + verdict) | § S4 draft block, § Copy review before S7 | Covered | — |
| Contract projection (9 entries) | § The recipe, S3, S5, S8 | Covered | All nine entries have an owning step |
