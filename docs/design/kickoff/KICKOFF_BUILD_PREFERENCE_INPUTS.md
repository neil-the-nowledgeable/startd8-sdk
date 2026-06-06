# Kickoff — Build Preference & Orchestration Config Inputs (Group I)

**Version:** 0.2 (post-CRP — 6 suggestions applied, see Appendix A)
**Date:** 2026-06-05
**Status:** Draft
**Parent:** [`../KICKOFF_REQUIREMENTS.md`](../KICKOFF_REQUIREMENTS.md) (master; cross-class
machinery FR-X1–X5)
**Related:** `docs/design/generation-profiles/REQ-GPC_GENERATION_PROFILE_CONSUMER.md` (profile
consumption — cited, not re-spec'd), `cap-dev-pipe/design/pipeline-requirements.md`
(REQ-CDP-INT-010 unattended gates, REQ-CDP-GP-001 profile passthrough)

---

## 1. Scope

How the user steers the *build itself*: spend ceiling, model/tier routing, target language/stack,
generation profile, and the orchestration config files. Planning showed most surfaces **already
exist** — the requirements here are dominated by **provenance** (which precedence tier supplied
each value) plus two genuine gaps (language declaration; default-vs-authored visibility).

**The precedence chain (exists — `cap-dev-pipe/pipeline/config.py:3–7`):**

```
defaults < pipeline.yaml < pipeline.env < CLI args < env vars
```
*(exception: REQ-CDP-INT-010 non-interactive precedence differs)*

---

## 2. Input Inventory (detail)

### 2.1 Cost budget (exists)

- `--cost-budget` on both repos: cap-dev-pipe `pipeline/cli.py:41` (default `"5.00"`) and
  `scripts/run_prime_workflow.py:126` → `workflow.run(max_cost_usd=…)` → enforced as a cumulative
  ceiling (`prime_contractor.py:5503` run-level stop; `:3906` per-feature skip).
- `costs/budget.py` `BudgetManager` (scoped budgets: project/model/tags) exists but is **not
  wired** — out of scope here (master Non-Goals).

### 2.2 Model/tier routing knobs (exist — ~10 flags)

`run_prime_workflow.py:149–240`: `--lead-agent`, `--drafter-agent`, `--tier3-agent`,
`--provider` (role-fill fallback), `--complexity-routing`, plus 5 threshold overrides
(`--complexity-loc-simple-max`, `--complexity-loc-complex-min`,
`--complexity-blast-radius-complex-threshold`, `--complexity-non-python-trivial-loc-max`,
`--complexity-non-python-simple-loc-max`). Routing in `query_prime/router.py`; model defaults via
`model_catalog.py` (never hardcoded strings).

### 2.3 Generation profile (surface exists; consumer designed-only)

- Surface: `GENERATION_PROFILE` env (`pipeline.env:15`, REQ-GPC-801; values
  `source|monitoring|operator|sponsor|practitioner|observability|full`), planned `--profile`
  (REQ-GPC-800); recorded in run-metadata (REQ-CDP-GP-001). Consumed today by cap-dev-pipe's
  `resolve-provenance.py` / `prime-post-run.py` (instrumentation gating).
- SDK-side consumer (PLAN-phase detection, `_omitted` handling): **REQ-GPC designed, zero `src/`
  implementation** — owned there, cited here (FR-I3).

### 2.4 Target language/stack (gap — inferred only)

- `resolve_language(target_files)` (`languages/resolution.py:167–253`): extensions, build files
  (package.json/go.mod/.csproj), directory structure, sibling context; Python fallback. Per-file
  `path_language_hints` exist; **no per-run declaration input.** Greenfield trees and intent are
  invisible to inference.

### 2.5 `.cap-dev-pipe/pipeline.env` (exists)

Knobs today: `CONTEXTCORE_ROOT`, `SDK_ROOT`, `PROJECT_ROOT`, `PROJECT_NAME`,
`GENERATION_PROFILE`, `ENABLE_INSTRUMENTATION` (`auto|true|false`, REQ-TCW-401),
`INSTRUMENTATION_CATEGORIES`. Plus env-var channel: `CDP_NON_INTERACTIVE`,
`CDP_PROCEED_ON_LOW_QUALITY` (`pipeline/config.py:209–217`).

### 2.6 `.cap-dev-pipe/design/question-answers.yaml` (exists — the unattended channel)

Arbitrary `id ↔ answer` pairs applied by RESOLVE (`contextcore manifest fix --answers`,
`pipeline/stages/export.py:137–138`). Pipeline-innate answers shipped (Q-001 traffic profile,
Q-CAP-1..3 contracts/gates). **This is the FR-X2 carrier for every input class** — pre-seed it
and no input ships blank on unattended runs.

### 2.7 `.cap-dev-pipe/explain-content.yaml` (exists — presentation-only)

Explain-mode **educational display copy only** ("single source of truth for all explain-mode
text", REQ-CDP-EDU-009; loaded with built-in fallback — `cap-dev-pipe/explain-pipeline.py:64,
241–258`). It **never influences generated artifacts**. Catalogued as a kickoff input (FR-I5,
path+hash recorded); excluded from build-impact semantics in the FR-X1 report (a `placeholder`
state here implies no generation risk — marking it build-driving would be report noise). Schema
is cap-dev-pipe-owned.

---

## 3. Requirements (Group I detail)

- **FR-I1 — Preference catalog + provenance.** Every build-preference input (§2.1–2.5) is
  recorded in run-metadata with its **provenance tier** — which level of the precedence chain
  supplied it (default / pipeline.yaml / pipeline.env / CLI / env). The FR-X4 pattern applied to
  preferences: a reviewer can distinguish "operator chose Opus lead" from "fell through to
  catalog default." **Delegation marker (resolves former OQ-2):** tier *emission* is a
  **cap-dev-pipe requirement** — `pipeline/config.py:3–7` is where the chain resolves; the SDK
  receives final values only (e.g. `max_cost_usd` arrives as a plain float at
  `prime_contractor.py:5503`) and **cannot re-derive the tier**. The startd8-side requirement is
  consumption: the SDK MUST forward and surface the received tier in FR-X4 output without
  re-deriving it.
- **FR-I2 — Language/stack declaration.** The language/stack declaration rides the
  **ingestion-generated convention manifest** (master OQ-1 resolved 2026-06-05: generated by plan
  ingestion as a tier-G draft, Architect-validated, reused across runs — see conventions slice
  FR-H1). `resolve_language()` becomes the **fallback**; when the validated declaration and
  inference disagree, the mismatch is **flagged at preflight — startd8 `plan_ingestion`, the
  owning surface** (the inference lives SDK-side, so the comparison must too; POLISH may surface
  the flag via report passthrough but does not own it). A declared-Python project with
  inferred-Go target files is a landmine, not a tiebreak; the flag lands in a named artifact
  (the preflight output), not "somewhere."
- **FR-I3 — Generation profile: collect now, consume per REQ-GPC.** The profile value is
  collected + provenance-recorded now (surface exists); SDK-side consumption is owned by
  REQ-GPC-100…803 and NOT re-specified here. The FR-X1 report shows the profile and its
  provenance tier.
- **FR-I4 — Budget default visibility.** The cost budget MUST be distinguishable as `authored`
  vs `config-default` (the silent `"5.00"`). **Determination is provenance-tier-based, never
  value-based:** an explicit `--cost-budget 5.00` (CLI tier) is `authored` even though it equals
  the default; only fall-through to the defaults tier is `config-default` — the precedence chain
  already carries the signal (a value-comparison implementation mislabels a deliberate choice).
  Depends on FR-I1's cap-dev-pipe tier emission. The FR-X1 pre-flight report surfaces a defaulted
  budget so the operator never discovers the ceiling mid-run.
- **FR-I5 — Orchestration config provenance.** `pipeline.env`, `question-answers.yaml`, and
  `explain-content.yaml` are catalogued kickoff inputs: path + hash + status in the per-project
  inventory (FR-X5), provenance-recorded like any other input (`explain-content.yaml` marked
  presentation-only per §2.7). A pre-seeded answers file is the *approved* unattended channel —
  its use is recorded, not hidden: answers consumed from `question-answers.yaml` carry provenance
  **`supplemental:pre-seeded`**, distinct from **`supplemental:interactive`** (RESOLVE prompt) —
  without the sub-type, an unattended run's audit trail is indistinguishable from an interactive
  one. **Secret-class answers:** values answering secret-class questions (receiver targets,
  webhook URLs) MUST use env-var indirection (`${WEBHOOK_URL}`), expanded by RESOLVE at
  collection time; the provenance record shows the env-var reference, never the expanded value
  (otherwise committing the tracked answers file violates the secrets non-goal at the kickoff
  layer).

---

## 4. Acceptance (Group I)

- run-metadata for a strtd8 run shows every §2 preference with provenance tier (FR-I1).
- A run with no `--cost-budget` shows `cost_budget: 5.00 (config-default)` in the FR-X1 report
  (FR-I4); passing the flag flips it to `authored`.
- A declared-language mismatch with inference is flagged at preflight (FR-I2).
- `GENERATION_PROFILE=observability` appears in run-metadata with tier `pipeline.env` (FR-I3).
- An unattended run resolved from `question-answers.yaml` records which answers were consumed
  (FR-I5).

---

## 5. Open Questions (Group I)

1. ~~**Declaration home for language (FR-I2).**~~ **RESOLVED (2026-06-05 operator decision,
   Q1):** same answer as the convention manifest — generated by plan ingestion, rides the same
   reviewable file, Architect-validated.
2. ~~**Provenance emission point (FR-I1).**~~ **RESOLVED (CRP R2):** cap-dev-pipe emits the tier
   (it owns the chain resolution at `pipeline/config.py:3–7`); the SDK forwards without
   re-deriving. Folded into FR-I1 as a delegation marker.
3. **BudgetManager future.** If/when `costs/budget.py` is wired (scoped per-model/tag budgets),
   do scoped budgets become kickoff inputs with their own matrix rows? (Deferred with the wiring.)

---

## Appendix: Iterative Review Log (Applied / Rejected Suggestions)

This appendix is intentionally **append-only**. New reviewers (human or model) should add suggestions to Appendix C, and then once validated, record the final disposition in Appendix A (applied) or Appendix B (rejected with rationale).

### Reviewer Instructions (for humans + models)

- **Before suggesting changes**: Scan Appendix A and Appendix B first. Do **not** re-suggest items already applied or explicitly rejected.
- **When proposing changes**: Append them to Appendix C using a unique suggestion ID (`R{round}-S{n}`).
- **When endorsing prior suggestions**: If you agree with an untriaged suggestion from a prior round, list it in an **Endorsements** section after your suggestion table. This builds consensus signal — suggestions endorsed by multiple reviewers should be prioritized during triage.
- **When validating**: For each suggestion, append a row to Appendix A (if applied) or Appendix B (if rejected) referencing the suggestion ID. Endorsement counts inform priority but do not auto-apply suggestions.
- **If rejecting**: Record **why** (specific rationale) so future models don't re-propose the same idea.

### Appendix A: Applied Suggestions

| ID | Suggestion | Source | Implementation / Validation Notes | Date |
|----|------------|--------|----------------------------------|------|
| R1-F-bp-1 | Reclassify `explain-content.yaml` as presentation-only | R1 (opus); endorsed R2 | §2.7 rewritten; FR-I5 + master §3 row + master FR-X1 exclude it from build-impact semantics | 2026-06-05 |
| R1-F-bp-2 | FR-I4 determination provenance-tier-based, not value-based | R1 (opus); strongly endorsed R2 (+ master endorsement) | FR-I4: explicit `--cost-budget 5.00` = `authored`; fall-through = `config-default` | 2026-06-05 |
| R2-F-bp-1 | Resolve OQ-2: cap-dev-pipe emits the tier; SDK forwards | R2 (sonnet) | FR-I1 delegation marker + SDK consumption requirement; OQ-2 marked resolved | 2026-06-05 |
| R2-F-bp-2 | Name FR-I2's mismatch-flag owner | R2 (sonnet) | FR-I2: preflight (startd8 `plan_ingestion`) owns the flag; POLISH passthrough only; named artifact | 2026-06-05 |
| R2-F-bp-3 | Distinguish pre-seeded vs interactive supplemental provenance | R2 (sonnet) | FR-I5 sub-types `supplemental:pre-seeded` / `supplemental:interactive`; propagated to master FR-X4 enum | 2026-06-05 |
| R2-F-bp-4 | Env-var indirection for secret-class answers in `question-answers.yaml` | R2 (sonnet, adversarial) | FR-I5 secret-class rule: `${VAR}` expansion at RESOLVE; provenance shows the reference, never the value | 2026-06-05 |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none yet) |  |  |  |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — claude-opus-4-8-1m — 2026-06-05

- **Reviewer**: claude-opus-4-8-1m (Claude Opus 4.8, 1M context)
- **Date**: 2026-06-05 (UTC)
- **Scope**: Group I slice review as part of the kickoff doc-set CRP pass; precedence chain and explain-content role spot-verified in cap-dev-pipe source (read-only).

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F-bp-1 | Data | medium | Reclassify `explain-content.yaml` (§2.7) as a catalogued-but-**non-build-driving** input: it is explain-mode educational display copy only ("single source of truth for all explain-mode text", REQ-CDP-EDU-009, loaded with built-in fallback — `cap-dev-pipe/explain-pipeline.py:64, 241–258`) and never influences generated artifacts. Keep the FR-I5 path+hash record, but exclude it from `authored\|placeholder\|absent` impact semantics in the FR-X1 report (or mark its impact "presentation only") | FR-X1 reports "build-driving" inputs with downstream impact; an explain-text file showing `placeholder` would imply generation risk that does not exist — report noise that dilutes the real flags | §2.7 + §3 FR-I5 | FR-X1 report for a run with default explain content carries no build-impact warning for it; the FR-I5 inventory row still records path+hash |
| R1-F-bp-2 | Validation | medium | Specify FR-I4's `authored`-vs-`config-default` determination as **provenance-tier-based, not value-based**: an explicit `--cost-budget 5.00` (CLI tier) is `authored` even though it equals the default; only fall-through to the defaults tier is `config-default` | "Distinguishable as `authored` vs `config-default`" invites a value-comparison implementation, which mislabels a deliberate choice equal to the default; the precedence chain (verified verbatim at `cap-dev-pipe/pipeline/config.py:3`) already carries the needed signal | §3 FR-I4 (+ §4 bullet 2) | Acceptance: `--cost-budget 5.00` passed explicitly reports `authored`; no flag at all reports `config-default` — both at the same value |

**Endorsements / Disagreements:** none — first round for this file.

#### Review Round R2 — claude-sonnet-4-6 — 2026-06-05

- **Reviewer**: claude-sonnet-4-6
- **Date**: 2026-06-05 00:00:00 UTC
- **Scope**: Group I slice review, second pass. Focus on FR-I1 provenance emission point (OQ-2), FR-I2 mismatch behavior, and adversarial pass on the unattended-run channel (FR-I5 / `question-answers.yaml`).

##### Executive summary

- OQ-2 (provenance emission point: cap-dev-pipe vs SDK) has a concrete consequence for FR-I4: if cap-dev-pipe emits the provenance tier and the SDK only receives final values, then the SDK cannot independently determine whether a budget was `authored` or `config-default` — it requires the cap-dev-pipe emission to be present. FR-I4's acceptance condition ("A run with no `--cost-budget` shows `cost_budget: 5.00 (config-default)`") is only achievable if cap-dev-pipe writes the tier, making this a cap-dev-pipe requirement without a delegation marker.
- FR-I2's mismatch behavior ("flagged at POLISH/preflight") inherits the ambiguous-owner problem R1-F-master-2 flagged — both POLISH (ContextCore) and preflight (startd8 `plan_ingestion`) are named without specifying which raises the flag.
- The unattended channel (`question-answers.yaml`) recording requirement (FR-I5) has no acceptance condition that the record distinguishes pre-seeded answers from interactive answers — the provenance value would be the same (`supplemental`) for both.

##### Suggestions

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R2-F-bp-1 | Interfaces | high | Resolve OQ-2 by deciding the emission point and adding a delegation marker: if cap-dev-pipe emits the provenance tier (the technically correct owner per `pipeline/config.py:3`), state that FR-I1 is a **cap-dev-pipe requirement** and add a startd8-side consumption requirement ("SDK MUST forward and surface the tier in FR-X4 output without re-deriving it"). Without this, the SDK has no way to independently assign a provenance tier — it sees final values only | `pipeline/config.py:3–7` resolves the precedence chain; the SDK receives `max_cost_usd` as a plain float at `prime_contractor.py:5503` — no tier attached. FR-I1 + FR-I4 are structurally unimplementable from the SDK side alone without cap-dev-pipe emitting the tier | §5 OQ-2 → resolve to §3 FR-I1 delegation note | FR-I1 test: launch a run with `--cost-budget 5.00` via CLI; the run-metadata shows `cost_budget: 5.00 (tier: CLI)` — verifiable only if the tier was passed through from cap-dev-pipe |
| R2-F-bp-2 | Interfaces | medium | Specify FR-I2's mismatch-flagging owner: name POLISH (ContextCore) or preflight (startd8 `plan_ingestion`) as the single surface that raises the declared-vs-inferred mismatch flag. The §3 FR-I2 text "flagged at POLISH/preflight" and §4 acceptance "flagged at preflight" use both terms; they are different owners (different repos, different invocation points). Align with the FR-X2 delegation split: if the flag logic lives in startd8's `plan_ingestion`, call it preflight; if in ContextCore's POLISH stage, call it POLISH and add a delegation marker | "POLISH/preflight" ambiguity is the same cross-owner gap R1-F-master-2 flagged; for FR-I2 it is also a testability gap — "flagged at POLISH/preflight" cannot be acceptance-tested without knowing which surface to instrument | §3 FR-I2 + §4 bullet 3 | A declared-Python / inferred-Go mismatch produces a flag in a specified, named artifact (POLISH report or preflight output) — not a generic "somewhere" |
| R2-F-bp-3 | Data | medium | Add a provenance sub-type to FR-I5 that distinguishes pre-seeded (`question-answers.yaml`) answers from interactive RESOLVE answers: propose `supplemental:pre-seeded` vs `supplemental:interactive` (or separate provenance values `pre-seeded` and `interactive`). Without this distinction, FR-X4's provenance record for an unattended run looks identical to an interactive one — defeating the "unattended channel use is recorded, not hidden" intent | FR-I5 says "an unattended run resolved from `question-answers.yaml` records which answers were consumed" — but the current FR-X4 provenance enum (`authored \| supplemental \| config-default \| templated/inferred`) has no way to signal pre-seeded vs interactive; both would be `supplemental`. The audit trail loses the distinction | §3 FR-I5 (+ propagate to master §4 FR-X4 provenance enum) | A run with `question-answers.yaml` pre-seeded for Q-CAP-1 shows that answer as `supplemental:pre-seeded`; a run with interactive RESOLVE for the same question shows `supplemental:interactive` |

### Stress-test / adversarial pass

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R2-F-bp-4 | Security | low | The `question-answers.yaml` file is described as the "approved unattended channel" (FR-I5, §2.6). If this file is committed to the repository (strtd8's `design/question-answers.yaml` is tracked per §2.6), and it contains RESOLVE answers for receiver-target questions (e.g. a webhook URL answer), then committing it violates the §7 secrets non-goal indirectly. Specify that `question-answers.yaml` values for secret-class questions MUST use env-var indirection (e.g. `${WEBHOOK_URL}`) and the RESOLVE machinery must expand them at collection time | The secrets non-goal covers "receiver targets etc." but `question-answers.yaml` is explicitly a kickoff input that contains pre-seeded answers — if a secret is pre-seeded as plaintext, the non-goal is violated at the kickoff layer | §3 FR-I5 + §7 non-goal note | A `question-answers.yaml` fixture with `${MY_SECRET}` syntax: RESOLVE expands it to the env var's value; the provenance record shows the env-var reference, not the expanded value |

**Endorsements:**
- R1-F-bp-1: concur — `explain-content.yaml` is display-copy only and should not carry build-impact semantics in FR-X1; the reclassification is correct.
- R1-F-bp-2: strongly concur — provenance-tier-based (not value-based) authored vs config-default is essential and the fix is minimal.
