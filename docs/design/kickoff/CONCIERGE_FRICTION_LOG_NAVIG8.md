# Concierge Friction Log — navig8 Onboarding (Instantiation #2)

**Version:** 0.3 (living — append per session)
**Date started:** 2026-06-07 · **Reconstructed + committed:** 2026-06-11 · **Last updated:** 2026-07-10 (F-11..F-13: first `generate backend` run defects)
**Status:** Active
**Purpose:** Raw material for a future **Concierge role/command** definition (candidate HITM
role 3.11 / Group-J extension): the role that ensures projects start off right by preparing
them for SDK onboarding — architectural choices for supportability, requirements/plan
formatting, test users, and all other kickoff concerns. Per the 2026-06-07 decision: the role
is *performed manually first* on a real second instantiation (navig8) and *defined from the
observed friction*, mirroring the docs-first→CLI pattern (role kits v1→v2). No `concierge`
symbol exists in the SDK yet (verified by full-repo grep, 2026-06-07).

> **Provenance note (2026-06-11):** v0.1 of this file was written 2026-06-07 but left
> **uncommitted**; the SDK working tree moved on (new commits + a stash/clean) and the untracked
> file was wiped. Reconstructed from session context and **committed** this time. This loss is
> itself friction item **F-10**.

**Onboarded project:** navig8 (`~/Documents/dev/navig8/`) — Michigan legal intake framework
(estate / business-launch / trademark), carved out of `startd8-work/work/legal/` 2026-06-07.
Framework-wide scope, estate-first pilot slice, prototype/solo posture, tier-R stack confirmed.

---

## Friction items

| # | Friction | What happened | Concierge implication |
|---|----------|---------------|----------------------|
| F-1 | **No matching observability industry dataset** | Only `end_user_application` exists; navig8 is a legal-selfhelp tool with domain-critical signals (acknowledgment-gate bypass, citation/index coverage) the generic dataset doesn't carry. Instantiated against the closest dataset + hand-added domain thresholds. | Concierge maintains the dataset library; "new industry ⇒ new dataset doc" needs an owner and a template. Candidate: `OBSERVABILITY_DEFAULTS_LEGAL_SELFHELP.md`. |
| F-2 | **Project-boundary hygiene** | The source dir (`work/legal/`) mixed the product with personal/client files (paystubs, client matters). Resolved by carving a clean product root. | Concierge intake checklist: *establish the product boundary first* — what is the repo, what is explicitly out. Personal/PII material adjacent to a future git/cascade target is a real risk class. |
| F-3 | **Brownfield path couplings** | 13 code references (runner scripts, tester builder, one test) pointed at the old doc paths; moving docs would have silently broken them. Caught by pre-move grep; rewrote to `../navig8/`, test suite re-verified (34 passed). | Concierge carve protocol: `grep -rn "<old-path>"` across all consuming repos BEFORE moving anything; re-run coupled tests after. (Same lesson class as the SDK's module-split checklist.) |
| F-4 | **Existing PRDs ≠ extraction format** | navig8 has 4 mature PRDs (FR/SS/F numbering, v0.2–v0.3, CRP-reviewed) — but none follow `requirements-and-plan-format v0.1` (the exact `Entities`/`AI assists`/`Owned fields`/`Coverage` headings the deterministic parser anchors on). strtd8 authored fresh from templates; navig8 is the first *brownfield docs migration*. | Templates assume blank-page authoring. The Concierge needs a **reformat/translate path** (PRD → extraction-format REQUIREMENTS), not just templates. Biggest unscoped work item. |
| F-5 | **Contract direction is reversed** | Kickoff assumes the contract (`schema.prisma`) is designed fresh as the front bookend. navig8's entities already exist as stable, validated Pydantic models (`tree_models.py`, `register_models.py`, `models.py`). The contract must be *derived from code*, the reverse of `generate backend`'s direction. | Concierge needs a **models→prisma derivation** step (or the SDK does — candidate small tool). Risk if skipped: a hand-authored contract drifts from the proven models. |
| F-6 | **Domain invariants don't fit the conventions schema** | navig8's highest-stakes conventions are not stack/naming but *invariants*: two-phase build/run split (no LLM on runtime path), citation hard-fail discipline, UPL zone enum + structural REFERRAL_TRIGGER check, no-storage posture. Squeezed into `architecture_notes` free-text. | `conventions.yaml` may need a first-class `invariants:` block (machine-checkable claims a generator must not violate), distinct from style conventions. Feeds the Group-H injection-reach work. |
| F-7 | **Bucket-2 carve-out for regulated content** | The bucket rule says placeholder content is fine and never graded. navig8's legal copy can NEVER be placeholder-grade — it rides the verification pipeline (SS-14) + attorney gate regardless of stage. Recorded as an explicit exception in `ASSEMBLY_INPUTS.md`. | The bucket model needs a **regulated-content carve-out** concept: content that is bucket-4-grade from day one. Likely recurs in medical/financial domains. |
| F-8 | **An external human gate the posture model doesn't name** | Prototype/solo posture says "the team plays all roles" — but attorney validation is a real external gate that cannot be played (UPL is law, not process). Documented as a posture exception in `KICKOFF_INTRO.md`. | The HITM role map's solo mode needs a notion of **non-playable roles** (external licensed validators). Relates to FR-J7 promotion tiers. |
| F-9 | **Test users exist but in engine-native form** | `ProfileResponder` profiles + `PACKET_*.md` representative cases + `expected_path` replay data are exactly bucket-2 fixtures — but not in `TEST_USERS_TEMPLATE.md` shape (entity-row tables paired to REQUIREMENTS vocabulary). | Concierge translate-don't-invent rule: existing fixtures are the source of truth; the template is the projection. |
| F-10 | **Uncommitted onboarding artifacts get wiped** | This very log (the role-spec source) was left untracked in the SDK tree and lost to a stash/clean before reconstruction 2026-06-11. | A Concierge that writes artifacts into the SDK or a consuming repo MUST persist durably (commit, or write into the consuming project which the team owns) — never leave the only copy untracked. Argues for Concierge outputs landing in the **consuming project** (navig8), not the SDK working tree. |
| F-11 | **[P0 BLOCKER] Generated app doesn't import — `Json?` fields have no SQLAlchemy type** | First `startd8 generate backend` run (from `schema.prisma` v0.1 + `human_inputs.yaml`) produced an app that fails at import: `app/tables.py` raises `ValueError: typing.Any has no matching SQLAlchemy type` on the first table (`DecisionTree.factVocab`), so nothing boots and no tables can be created. Repro: `DATABASE_URL="sqlite:///./t.db" python -c "import app.main"` → traceback through `app/db.py` → `app/tables.py` ~line 62. Every Prisma `Json?` field was emitted as bare `Optional[Any]` with **no** SQLAlchemy column type; SQLModel can't map `Any` (needs `sa_column=Column(JSON)` or a concrete dict/list type). Affected: `DecisionTree.factVocab`; `TreeNode.branches`, `TreeNode.answerFacts`; `LandmineEntry.caseAuthority`; `SequenceConfig.framingCopy`/`narrowingReasons`/`limitationCopy`/`boundaryFallbacks`/`syntheticWalk`. Note: `python -m py_compile` **passes** (syntax is valid) — the failure only surfaces at import/runtime, so a compile-only smoke check misses it entirely. Artifact: `sqlmodel-tables` (from `prisma/schema.prisma`). | The generator's `Json` → SQLModel mapping is unsound: mapping `Json?` to `Optional[Any]` yields a module that cannot be imported. Concierge implication for the SDK validation gate: **the generator's own validation must actually import the generated module**, not just `py_compile` it — a green compile is not a green boot. Suggested direction (SDK owns the fix): give `Json`/`Json?` fields a concrete SQLAlchemy column type. This is a hard blocker for navig8's first cascade run (NEXT_STEPS Step 4). |
| F-12 | **[P1] Owned-field policy (`human_inputs.yaml`) only half-enforced — attorney-gate / verification fields are user-writable** | `prisma/human_inputs.yaml` declares 5 owned fields the AI edge must never write: `TreeNode.confidence`, `TreeNode.attorneyNote`, `LandmineEntry.confidence` (verification-pipeline-owned), `DecisionTree.validationStatus`, `SequenceConfig.validationStatus` (attorney-gate-owned); NEXT_STEPS Step 5 expects "no form/AI surface" for these. **Correct:** the `*Create` Pydantic models *do* exclude the owned fields (the policy is wired into that one path). **Defect:** the policy was not applied to three other generated surfaces — (1) `*Update` models (`app/tables.py`) include the owned fields, so the JSON `PATCH /{entity}/{id}` API (`app/routers.py`, blind `setattr` loop) accepts and writes them; (2) `app/web.py` per-entity `_rules` dicts include the owned fields, so the HTMX UI writes them on **both** create and update handlers; (3) form templates (`app/templates/decisiontree/form.html`, `treenode/form.html`, `landmineentry/form.html`, `sequenceconfig/form.html`) render them as editable inputs and mark `validationStatus`/`confidence`/`attorneyNote` `required`. Concretely the generated `/ui/decisiontree` create form **forces** a human to set `validationStatus` at creation — defeating the "candidate, not attorney-validated until an attorney signs" invariant — and a generic API/UI edit can forge verification-pipeline conclusions (`confidence`/`attorneyNote`). This is a structural UPL-boundary property, not cosmetic. Artifacts: `sqlmodel-tables`, `fastapi-routers`, `htmx-form`. | The owned-field policy is applied at exactly one of four write surfaces. For a regulated domain this is a correctness defect, not a nicety: the generated app lets any operator forge an attorney-gate / verification-pipeline state the `human_inputs` contract explicitly reserves. Ties to F-6 (invariants belong in the contract) and F-8 (non-playable external gate). Suggested direction (SDK owns the fix): apply the `human_inputs` owned-field filter **uniformly** across `*Update` models, web `_rules`, and form templates — not just `*Create`. |
| F-13 | **[P2] Composite `@@unique` constraints dropped from generated tables** | None of the schema's composite unique constraints survive into `app/tables.py` — there is no `__table_args__` / `UniqueConstraint` anywhere in the generated tables. Dropped: `DecisionTree`/`TreeNode` `@@unique([treeId, nodeKey])`; `Perspective` `@@unique([treeId, perspectiveKey])`; `LandmineEntry` `@@unique([registerId, entryKey])`; `ScreeningLink` `@@unique([treeNodeId, landmineEntryId])`; `SequenceConfig` `@@unique([treeId, areaName])`. So the DB won't enforce e.g. nodeKey-uniqueness-per-tree, which the Step 6 tree-JSON loader and `validate_tree`/`validate_trace` semantics rely on for FK/trace integrity. Artifact: `sqlmodel-tables`. | Block-level `@@unique([...])` constraints are silently discarded by the generator, so an integrity property the contract states is not enforced by the generated schema (it degrades to application-only, or nothing). Note this is the *same* class as the derivation win recorded in the 2026-06-07 second pass (`@@unique([parent,key])`) — the constraint was authored correctly but does not round-trip through generation. Suggested direction (SDK owns the fix): emit block-level `@@unique([...])` as SQLAlchemy `UniqueConstraint` in `__table_args__`. **RESOLVED 2026-07-10:** already fixed upstream in SDK commit `ed148eaa` ("F3b") — the current generator parses `@@unique` and emits `__table_args__ = (UniqueConstraint(...),)`; the shipped `app/tables.py` was produced by a pre-`ed148eaa` build. Remedy: regenerate navig8's backend with the current SDK — no generator change needed. |
| F-14 | **[lesson] Owned-field policy expansion couples to the drift subsystem** | Fixing F-12 (applying `human_inputs.yaml` owned fields to the API DTOs + web `_rules` + form templates) made three previously schema-only artifacts — `sqlmodel-tables`, `htmx-form`, and web.py (`fastapi-web`/`fastapi-web-forms`) — newly **`human_inputs`-dependent**. But the drift subsystem (`drift.py::_renderers` + the owned-file skip-hook) had no `human_inputs_text` input and these artifacts embedded no `human-inputs-sha256` header, so `startd8 generate backend --check` re-rendered them WITHOUT the policy and reported 6 false `tampered` drifts even though the generator was idempotent (a fresh render equalled on-disk). | An artifact's drift-input set must expand in lockstep with its render-input set — otherwise a correct generator change silently breaks `--check`. Fixed 2026-07-10 by mirroring the AI-kind pattern: thread `human_inputs_text` into the drift re-render for those kinds and embed a `# human-inputs-sha256:` header (empty-policy sha stays backward-compatible). Regression guard added: a `human_inputs` change without regen now correctly reports `stale`. **RESOLVED 2026-07-10** (same effort as F-12). Broader implication: the SDK's fidelity gate should assert render-inputs ⊆ drift-inputs so this class can't recur. |

## Onboarding state (as of 2026-07-10)

**Done (first pass, 2026-06-07):** clean product root (`navig8/`, git-initialized, commit
`1d468c3`) · path couplings fixed + tests green · kickoff package instantiated
(`docs/kickoff/` — intro, explained, 4 input YAMLs, honest provenance) · assembly inventory
(`docs/ASSEMBLY_INPUTS.md` + machine-readable `.yaml`) · PRD OQ-1 resolved (code name = navig8).

**Done (second pass, 2026-06-07):** `prisma/schema.prisma` v0.1 derived from the Pydantic
models (F-5 resolved for navig8 — by hand; the models→prisma derivation *tool* gap stands) +
`prisma/human_inputs.yaml` (verification-pipeline-owned + attorney-gate-owned fields).
Wireframe: 8 entities / 40 CRUD routes / 0 invalid; **cascade backend: ready**. Commit
`a197e63`. Derivation notes worth keeping: semantic string ids → `nodeKey`/`entryKey` +
`@@unique([parent,key])` with cuid row PKs; `Dict`/`List` fields → `Json`; cross-list trace →
explicit join model (`ScreeningLink`); hyphenated Python enum values (`at-formation`) are
illegal Prisma identifiers → underscore values + loader normalization; `type` field renamed
`nodeType` (builtin shadowing); computed fields (`full_reference`) stay computed, never stored.

**Done (third pass, 2026-06-07):** team runbook `navig8/docs/kickoff/NEXT_STEPS.md` (commit
`1975510`) — 8 sequenced steps, Concierge-assists framing.

**Done (first cascade run, 2026-07-10):** first `startd8 generate backend` run against
`prisma/schema.prisma` v0.1 + `prisma/human_inputs.yaml` (NEXT_STEPS Step 4). Generated app
**inspected, does not yet boot** — three generator defects logged from navig8's side: **F-11**
(P0 blocker — `Json?` fields have no SQLAlchemy type, app fails at import), **F-12** (P1 —
owned-field policy enforced only on `*Create`, leaving `*Update`/web/templates writable), **F-13**
(P2 — composite `@@unique` constraints dropped from generated tables). Filed to the SDK team,
who own the fixes.

**Next (team-performed, Concierge-assisted):**
1. Reformat estate REQUIREMENTS + PLAN into extraction format from the existing PRDs (F-4)
2. Translate `ProfileResponder`/PACKET fixtures into `TEST_USERS.md` (F-9)
3. Author `app.yaml` scaffold manifest + `prisma/views.yaml` (unblocks `views` cascade)
4. First `$0` cascade run (`startd8 generate backend`) against the contract
5. Decide the full code carve (engine package → navig8) — deferred, entry-point migration required

## Concierge role sketch (accumulating)

Mission: own the *project-side* of SDK adoption — everything between "we want to build with the
SDK" and "the first cascade/pipeline run starts from honest inputs."

**Operating posture (operator decision, 2026-06-07): ASSIST, not operate or orchestrate.**
The consuming team performs the steps; the Concierge prepares the ground (surveys, instantiates
packages, derives starters), hands over a self-serve runbook, and stays on call (explain
choices, review drafts, draft-to-react-to on request, triage SDK defects). Implication for the
HITM map: the Concierge holds no validation gate of its own — every gate stays with the
delivery role that owns it (Architect ratifies the contract the Concierge derived, etc.).
First handoff artifact of this shape: `navig8/docs/kickoff/NEXT_STEPS.md`.

Observed activities this engagement (the candidate command surface): existence-check + asset
survey (brownfield triage) · product-boundary establishment (F-2) · carve protocol with
coupling greps (F-3) · posture + scope + stack intake (structured decisions) · kickoff package
instantiation with provenance discipline · contract derivation from existing models (F-5) ·
exception documentation where the project doesn't fit the machinery (F-6/F-7/F-8) ·
wireframe-based validation · friction logging back to the SDK (this file) · self-serve runbook
handoff.
