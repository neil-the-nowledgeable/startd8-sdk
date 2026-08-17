# Byte-Identity Revise Applier (closes REQ-21's guard seam) — Requirements

**Project:** startd8-sdk   **Criticality:** high
**Version:** 0.2 (Post-planning — self-reflective update)   **Date:** 2026-08-16
**Format:** det-req/0.1
**Backend:** python-cli-surface
**Pairs with:** *(plan deferred — spec-only; delivered via the Spec Delivery Loop)* · **`REQ-21` (the `auto_apply_revise` seam this FILLS — the caller-supplied `guard`)** · `REQ-20` (the Lesson + `revises` edge) · `REQ-19` (the `$0` product whose byte-identity is the gate) · `feedback_zero_risk_autonomous` (grounding-is-what-makes-it-safe)
**Inherits standards:** det-req-kit · NODE-SCHEMA v0.4.0 · NAMING_CONVENTION · REQ-06 (govern) · the byte-identity guard (`test_golden_tree_byte_identity` / `render_backend`)
**Audience:** operator / SDK contributors
**Trust boundary:** local repo; **auto-applies ONLY a revise the guard PROVES byte-identical on the `$0` product; every product-changing revise stays human-gated**
**Data classification:** internal

> **Readable handle:** `feature/sdk-navigator-applies-a-revise-through-a-real-byte-identity-guard`
> **Semantic name:** *SDK navigator applies a revise's concrete contract edit through a REAL byte-identity guard that regenerates the deterministic $0 product and hash-compares it, auto-applying only when the product is proven unchanged and failing safe to a human proposal on any diff, so REQ-21's auto-tier acts against the actual product instead of a mock guard.*
> **Canonical ref:** `cc:intent:requirements-visualization:feature:req-24`

## 0. Planning Insights (Self-Reflective Update)

> The planning pass (exploring `backend_codegen.render_backend`, the golden-tree hash guard, and the
> REQ-20/21 revise structure) revealed **3 corrections** to the pre-planning draft. The biggest reframed
> what the increment even is.

| v0.1 Assumption | Planning Discovery | Impact |
|-----------------|--------------------|--------|
| The spec must **pre-define a "safe revise class"** (description edits, additive fields) that is auto-eligible | The guard **proves** byte-identity *per revise* by regenerating + comparing — so there is NO need to enumerate safe classes. Enforce-don't-declare (REQ-21 FR-2): a "description" edit that *does* reach the product is caught by the guard and downgraded; a class-based allowlist would be accidental complexity that erodes. | **Deleted the safe-class enumeration** (would have been FR-1 v0.1). The gate is the guard's regenerate-and-compare, not a taxonomy. (Kagami / anti-accidental-complexity.) |
| The applier consumes the **determinism-regression Lessons** (REQ-20) as its fuel | Those Lessons propose *"re-examine the generation path"* — a **consequential** change with no concrete edit payload; they are NOT byte-identity-provable and NOT this tier's fuel. A revise needs a **concrete `edit` payload** (a specific contract mutation) for the guard to apply + prove. | **New FR-1:** a revise carries a concrete `edit` (target + before→after contract text). The regression-Lesson fuel-source stays a **noted dependency** (NR-3), not this increment. |
| A new byte-identity guard must be built | `render_backend(schema)` already yields the `(path, content)` `$0` product and `test_golden_tree_byte_identity` already hashes `{path: sha256}`. The guard is `hash(render_backend(before)) == hash(render_backend(after))` — **reuse, don't rebuild** (Mottainai). | **FR-2** builds on `render_backend`; no parallel generation path. The guard lives in an **applier module that imports `backend_codegen`** — construction-aware, OUTSIDE the navigator firewall (the navigator only exposes `auto_apply_revise`). |

| The guard compares the product **byte-for-byte** | **Build-time discovery:** every generated file carries a `# schema-sha256:` provenance header that fingerprints the SOURCE — so ANY schema edit changes the stamp on every file, and STRICT byte-identity can NEVER pass for a schema edit (the safe class would be empty). Verified: a comment edit changes ONLY the stamp lines; a field rename changes 10 files of real content. | **FR-2 refined:** compare the product **modulo the source-fingerprint stamp** (strip `schema-sha256:`/`contract-sha256:` lines). Principled, not eroded — it excludes provenance metadata (like a build timestamp), never behaviour. A comment/description edit → identical → auto; a rename → diff → human. |

**Resolved open questions:**
- **OQ-1 → the guard is the arbiter, not a classifier.** No "auto-eligible class" list; the guard's regenerate-and-compare decides, per revise.
- **OQ-4 (discovered at build) → the gate is product-content identity, modulo the source-fingerprint stamp.** The `schema-sha256:` header is provenance, not product behaviour; excluding it is the reproducibility-check norm, and keeps the gate objective (a real content change still fails).
- **OQ-2 → the applier lives outside the navigator firewall.** It imports `backend_codegen` (to regenerate) + calls the navigator's `auto_apply_revise` seam. The navigator stays construction-free (REQ-19 firewall preserved).
- **OQ-3 → the revise's concrete edit is the payload, not the Lesson's prose.** This increment applies a concrete edit; producing concrete-edit revises from a Lesson class is the follow-on (NR-3).

### 0.1 Lessons-Learned Hardening (v0.3)

> Applied the recurring design-doc lessons before review:
- **Phantom-reference audit** — grep-confirmed the symbols the spec names EXIST: `render_backend` (`backend_codegen/assembler.py`), `auto_apply_revise`/`ReviseAudit`/`ReviseEligibility` (`revise_tier.py`), the `{path: sha256}` golden hash (`test_deployment_mode_consume.py`). No phantom refs → the guard is a reuse, not a build.
- **Prune phantom scope** — the Lesson→concrete-edit *producer* was pruned to NR-3 (wrong provenance tier: the regression Lessons are consequential; a byte-identity-provable edit is a different, undrafted source).
- **Single-source vocabulary** — the eligibility vocabulary (`auto`/`human`, `CONFIDENCE_FLOOR`) stays OWNED by `revise_tier.py` (REQ-21); this REQ cites it, adds no parallel tier vocabulary.

### 0.2 Design-Principle Hardening (v0.3.1)

> Checked against the design principles:
- **Mottainai (don't regenerate what exists)** — the guard reuses `render_backend`; no parallel `$0` generation path. (FR-2.)
- **Kagami (edit the source, not the mirror)** — the revise edits the CONTRACT (schema, the source), then regenerates; it never hand-edits the generated product (the mirror). The guard's regenerate-and-compare IS the hash-parity check Kagami mandates. (FR-2/FR-4.)
- **Accidental-complexity anti-principle** — deleted the "auto-eligible class" allowlist (v0.1 FR-1); one objective guard replaces an enumerated special-case list that would erode. (§0 OQ-1 / Appendix B.)
- **Genchi Genbutsu (bind to the real artifact)** — the gate is byte-identity of the REAL `$0` product (`render_backend` output), not a proxy for "is it safe".
- **Firewall (REQ-19)** — construction coupling quarantined to the applier layer (`revise_apply.py`); the navigator core stays construction-free, AST-checked (FR-6).

*v0.3.1 — Post lessons + principle hardening. No further changes needed (§0 already applied Mottainai/Kagami/anti-complexity during planning). Ready for build.*

## Overview

Define a concrete `revise edit` (a target contract node + a before→after contract text mutation); build a
**real byte-identity guard** — `snapshot the $0 product → apply the edit to the contract → regenerate →
hash-compare` — that reuses `backend_codegen.render_backend`; and a **CLI applier** (`navigator revise
apply`) that runs the guard **through** REQ-21's `auto_apply_revise` (fail-closed: any product diff →
`human`) and writes the git-tracked, reversible `ReviseAudit`. Additive over REQ-21 — it FILLS its `guard`
seam with a real guard; the default stays human; every product-changing revise is unchanged.

## Objectives

- **O-1:** A revise with a concrete edit auto-applies iff a REAL guard proves the `$0` product unchanged — target: the applier regenerates + hash-compares via `render_backend` and auto-applies only on a byte-identical result.
- **O-2:** Fail-closed + fail-safe, firewall-preserving — target: any product diff (or guard error) → `human`; the guard imports `backend_codegen` at the applier layer, never inside the navigator.
- **O-3:** Autonomy with a trail; consequential loop untouched — target: every auto-apply writes a git-revertible `ReviseAudit`; a product-changing edit is never auto-applied.

## Risks

| Type | Description | Mitigation | Priority |
|------|-------------|------------|----------|
| security/integrity | The guard passes a revise that DOES change the product (a hash collision or an incomplete snapshot) | FR-2: hash the FULL tree (`{path: sha256}` over every owned file) + compare the key SET too (an added/removed file is a diff); sha256 collision is not a practical threat | high |
| integrity | The applier mutates the contract, regenerates, but fails to REVERT on a diff (leaves a dirty tree) | FR-4: apply on a copy / restore-on-any-outcome; the contract edit is only committed to the real tree when the guard proves identical AND the audit is written | high |
| modularity | The navigator gets coupled to `backend_codegen` (firewall break) | FR-6/NR-2: the guard + applier live in an applier module that imports `backend_codegen`; the navigator exposes only `auto_apply_revise` (unchanged) — AST-checked | high |
| scope | Building the Lesson→concrete-edit producer here | NR-3: this increment applies a *given* concrete edit + proves it; producing edits from a Lesson class is the follow-on | medium |
| dependency | Needs REQ-21's `auto_apply_revise` + `ReviseAudit` | NR-6: landed | low |

## Functional requirements

- **FR-1 — A concrete revise edit payload.** Define a typed revise-edit `{target (contract node key), path (contract file), before, after}` carrying the concrete contract mutation to apply, distinct from REQ-20's prose proposal; a malformed edit is rejected with a named error. Name: A typed revise edit carries the concrete target contract path and before to after mutation to apply. Touches: `src/startd8/navigator/revise_tier.py`, `tests/unit/navigator/test_revise_apply.py`. Lives: code src/startd8/navigator/revise_tier.py. Approve?: does a revise edit carry a concrete target path and before-to-after mutation, rejecting malformed input?. Verify: a well-formed edit constructs with target/path/before/after; an edit missing its target or before text is rejected with a named error. Serves: O-1
- **FR-2 — The real byte-identity guard (regenerate + hash-compare).** A guard snapshots the `$0` product (`{path: sha256}` over `render_backend(schema)`), applies the edit to the contract text, regenerates, and returns True only when the full product — key set AND every file hash — is unchanged; it reuses `render_backend` (no parallel generation). Name: A guard regenerates the dollar-zero product before and after the edit and returns identical only when every file hash and the key set match. Touches: `src/startd8/navigator/revise_apply.py`, `tests/unit/navigator/test_revise_apply.py`. Lives: code src/startd8/navigator/revise_apply.py. Approve?: does the guard regenerate via render_backend and prove the whole product unchanged?. Verify: an edit that leaves `render_backend` output identical yields guard True; an edit that changes any file's bytes or the file set yields guard False. Serves: O-1, O-2
- **FR-3 — Apply through REQ-21's seam (enforce, not declare).** The applier calls `auto_apply_revise(lesson, elig, guard=<the FR-2 guard>, …)` so the revise is applied THROUGH the guard; a guard-False (or guard error) result returns no audit and the revise stays `human` — a mis-classification is caught, never shipped. Name: The applier runs the real guard through auto apply revise so a product diff downgrades to human. Touches: `src/startd8/navigator/revise_apply.py`, `tests/unit/navigator/test_revise_apply.py`. Lives: code src/startd8/navigator/revise_apply.py. Approve?: is the revise applied through auto_apply_revise with the real guard, downgrading on any diff?. Verify: a byte-identical edit yields a `ReviseAudit`; a product-changing edit yields `None` (human) via the same call path; a guard that raises is treated as False (fail-closed). Serves: O-1, O-2
- **FR-4 — Reversible apply: commit the edit only on proof.** The applier applies the edit to the real contract file ONLY after the guard proves the product unchanged and the audit is written; on any diff/error the contract is left byte-identical to before (restore-on-fail) — the working tree is never left dirty by a downgraded revise. Name: The contract edit is committed to the tree only after the guard proves unchanged and the audit is written else the tree is restored. Touches: `src/startd8/navigator/revise_apply.py`, `tests/unit/navigator/test_revise_apply.py`. Lives: code src/startd8/navigator/revise_apply.py. Approve?: is the contract left unchanged whenever the revise is not auto-applied?. Verify: after a downgraded (product-changing) revise the contract file bytes equal the pre-run bytes; after an auto-applied revise the contract file carries the edit and the audit names a revert reference. Serves: O-3
- **FR-5 — The CLI applier.** `navigator revise apply --schema <contract> --edit <edit.json> --lesson <lesson.json>` runs FR-1..FR-4 and prints the outcome (`auto-applied` + audit, or `human` + reason); `--dry-run` (default) reports the tier + guard result WITHOUT writing. Name: A CLI applies a revise edit dry-run by default reporting auto-applied with audit or human with reason. Touches: `src/startd8/navigator/cli_navigator.py`, `tests/unit/navigator/test_revise_apply.py`. Lives: code src/startd8/navigator/cli_navigator.py. Approve?: does the CLI report tier and guard result, writing only outside dry-run?. Verify: `navigator revise apply … --dry-run` reports the tier + guard result and writes nothing; without `--dry-run` a byte-identical edit is auto-applied + audited and a product-changing one is reported `human`. Serves: O-3
- **FR-6 — Firewall preserved (AST-checked).** The guard + applier (`revise_apply.py`) may import `backend_codegen`; the navigator core (`revise_tier.py`, `sources_retrospective.py`, `realization*.py`) still imports NO construction subsystem — the coupling is quarantined to the applier layer. Name: The applier layer may import backend_codegen while the navigator core imports no construction subsystem. Touches: `tests/unit/navigator/test_revise_apply.py`, `src/startd8/navigator/revise_apply.py`. Lives: test tests/unit/navigator/test_revise_apply.py. Approve?: is construction coupling quarantined to the applier, leaving the navigator core firewall-clean?. Verify: `revise_apply.py` imports `backend_codegen`; `revise_tier.py`/`realization.py`/`realization_provenance.py` import no `backend_codegen`/`contractors`/`micro_prime` (AST). Serves: O-2
- **FR-7 — Additive; consequential loop untouched; audit reversible.** No new Node field; existing renders byte-identical; a product-changing revise is never auto-applied; and every auto-apply writes a git-revertible `ReviseAudit` (REQ-21 FR-6). Name: The applier is additive with no new Node field leaves the consequential loop human-gated and every auto-apply git-revertible. Touches: `tests/unit/wireframe/test_render_profile.py`, `tests/unit/navigator/test_revise_apply.py`. Lives: test tests/unit/navigator/test_revise_apply.py. Approve?: is the increment additive, byte-identical, and the consequential loop untouched?. Verify: `node_field_names()` unchanged; `test_no_profile_is_byte_identical` passes unedited; a product-changing edit is never auto-applied and any auto-applied edit is git-revertible via its audit revert reference. Serves: O-3

## Non-requirements

- **NR-1:** Does NOT auto-apply any revise the guard cannot prove byte-identical — the guard is the hard gate; every product-changing revise stays human-gated (REQ-21 intact).
- **NR-2:** Does NOT couple the navigator core to `backend_codegen` — the construction-aware guard lives in the applier layer; the navigator exposes only the `auto_apply_revise` seam.
- **NR-3:** Does NOT produce concrete-edit revises FROM a Lesson class — this increment applies a *given* concrete edit + proves it. The Lesson→edit producer (e.g. a description-clarification lesson) is the follow-on; the REQ-20 determinism-regression Lessons are consequential and out of this tier by construction.
- **NR-4:** Does NOT widen REQ-21's eligibility — byte-identity + reversibility + confidence are unchanged; this only supplies the real guard for the byte-identity property.
- **NR-5:** Does NOT batch / auto-discover revises — one edit, one guard run, one audit; discovery/queueing is future.
- **NR-6:** Build-ready — REQ-21 (`auto_apply_revise` + `ReviseAudit`) is on `main`.

## Appendix A — Accepted (with where merged)
*(none yet — pre-CRP)*

## Appendix B — Rejected (with rationale)
- **Enumerate an "auto-eligible revise class"** — REJECTED (§0 OQ-1): the guard proves byte-identity per revise; a class allowlist is accidental complexity that erodes ("just this once"). The objective guard is the gate.

## Appendix C — Incoming review rounds
*(none yet)*

*v0.2 — Post-planning self-reflective update. 1 requirement deleted (safe-class enumeration), 1 reframed (concrete edit payload, not regression-Lessons), 1 grounded in `render_backend` reuse; 3 open questions resolved.*
