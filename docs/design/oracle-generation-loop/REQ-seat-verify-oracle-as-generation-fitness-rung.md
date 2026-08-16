# Seat the Spec's Verify Oracle as the Generation Fitness Rung — Requirements

**Project:** startd8-sdk   **Criticality:** high
**Version:** 0.3.1 (Post lessons + principle hardening — ready for CRP)   **Date:** 2026-08-16
**Format:** det-req/0.1
**Backend:** python-cli-surface
**Pairs with:** `PLAN-seat-verify-oracle-as-generation-fitness-rung.md`
**Inherits standards:** det-req-kit · DIDL · REQ-08 (the executable `Verify:` oracle) · the SDK cheap-model strategy (richer spec → cheaper model)

> **Semantic name:** *Seat the spec's own `Verify:` clauses as a graded fitness rung on the deploy-harness ladder, and feed a rung failure back as regeneration feedback into the Prime retry loop — executed in the benchmark sandbox, with the un-runnable prose majority held as an explicit human-gate residue.*
> **Readable handle:** `feature/seat-verify-oracle-as-generation-fitness-rung`
> **Canonical ref:** `cc:intent:oracle-generation-loop:feature:seat-verify-oracle-fitness-rung`

---

## 0. Planning Insights (Self-Reflective Update)

> The planning pass ground every assumption against the real seams (`verify_oracle.py`, `benchmark_matrix/sandbox.py`, `contractors/prime_contractor.py`, `repair/`, `costs/`, `deploy_harness/`). It overturned **five** load-bearing v0.1 assumptions — including the feature's own name. This is a >30% revision: the loop working.

| v0.1 Assumption | Planning Discovery | Impact |
|-----------------|--------------------|--------|
| **D-1** — the loop is *generate → verify → **repair*** (feed the oracle failure to `repair/`). | `repair/` handles **only syntax/import/lint** (`diagnostics.py:157` classifies into those 3); a test/logic/oracle failure has **no repair route** — it becomes a bare pass-through `Diagnostic(file="")` no step fixes. The idiomatic behavioral-fix path is **regenerate-with-feedback**: Prime's `process_feature` re-develops carrying `feature.error_message` (`prime_contractor.py:2608/3764`, capped `max_retries=6`). | **Renamed + rewired.** FR-4 feeds the oracle FAIL back as `error_message` into Prime's existing regen loop, **NOT** `repair/` (NR-3). The "repair" in the feature name was wrong. |
| **D-2** — reuse `verify_oracle.evaluate()` to run the generated app's Verify clauses. | `evaluate()` is **structurally navigator-locked at two layers**: `_classify_clause` only promotes a `startd8`-verb span to `command`, and `_is_readonly_allowlisted` hard-requires `argv[1]=="navigator"`. There is **no injectable allow-policy**. `pytest`/`curl` cannot run through it at all. | FR-1 is a **separate sandboxed runner** that reuses `classify()`'s span extraction but not `evaluate()`; the navigator oracle's read-only allow-list is left untouched (NR-2). |
| **D-3** — the loop needs a new deploy-and-grade harness. | `deploy_harness/` **already** has the graded ladder (DISCOVER→INSTALL→BOOT→HEALTH→SMOKE→CONTEXT_SMOKE, `ladder.py`) + `LadderResult` + `venv_runner`. But its SMOKE rung is a **generic CRUD round-trip** synthesized from `/openapi.json` (`smoke.py:70`), **not spec-derived**. | FR-3 **reuses** the ladder skeleton and adds one novel **ORACLE rung** (the spec's `Verify:` clauses as the fitness) after SMOKE — not a new harness. |
| **D-4** — the spec's `Verify:` clauses are ready to drive generation. | **~5%** of Verify clauses are oracle-runnable (28/510 are `startd8`-command-shaped); the rest are prose. And **zero** existing clauses target a **generated app** — all 28 (+7 pytest, +8 curl) are **SDK-self-referential**. A generated-app runnable-Verify grammar is **essentially greenfield**. | FR-2 (the generated-app runnable-Verify grammar) becomes a **prerequisite dependency**, sequenced before FR-3/4. FR-6 makes fitness partiality explicit + honest. |
| **D-5** — oracle-pass ≈ spec satisfied. | The D-3 honesty boundary is deliberate: a `pass` = "extracted command exited 0", **not** "the prose assertion holds"; every `OracleVerdict` already carries `assertion_text` as the residue, and **nothing compares them**. | FR-7 forbids claiming spec-satisfaction from oracle-pass; the loop surfaces the prose residue as a **human Goodhart gate** (NR-6). |

**Resolved open questions:**
- **OQ-1 → sequence FR-2 first.** The runnable-Verify grammar for generated apps is greenfield; the loop can be built + demoed on a small hand-authored generated-app spec, but FR-2 must precede FR-3/4.
- **OQ-2 → build a fresh sandboxed runner, do not refactor the navigator oracle.** `evaluate()` is structurally locked; a fresh runner that reuses `classify()` avoids destabilizing the shipped, byte-identity-guarded navigator oracle.
- **OQ-3 → per-run `max_cost_usd` is the primary ceiling.** `PrimeContractorWorkflow.run(max_cost_usd=…)` (`prime_contractor.py:5856`) is the cheapest fail-closed budget; `BudgetManager.check_budget` is the pre-iteration guard.

### 0.1 Lessons-Learned Hardening (v0.3)

> Checked the SDK/design-doc + benchmark-harness lessons against the draft. Applied:

- **[phantom-reference audit]** — every seam the spec names was grounded to a real `file:line` by the exploration (`classify`, `run_sandboxed`/`run_service_sandboxed`, ladder `Stage`/`LadderResult`, `process_feature`+`error_message`, `run(max_cost_usd=)`, `check_budget`, `queue._detect_and_break_cycles`); the NEW symbols (`oracle_loop/*`, `Stage.ORACLE`, `build-to-spec`) are marked to-be-created. No phantoms.
- **[benchmark-harness gotchas]** — the runner must degrade env failures (`ServiceResult.violation` = never-ready/launch-error) as `error`, **never** the model's `fail` (FR-1) — the same "missing-key is infra_fail, not a catastrophic 0" rule the benchmark matrix already encodes.
- **[LLM dependency graphs unreliable + queue.py cycle-deadlock]** — FR-5's stall detector guards the loop from the non-convergence that the `queue.py` cycle-detection precedent warns of.
- **[det-req single-line FRs + semantic names]** — every FR is one physical line with a `Name:`; DIDL semantic-kebab filenames used (no integer brand).

### 0.2 Design-Principle Hardening (v0.3.1)

> Checked against the design-principle index. Each changed the draft:

- **[Mottainai — don't regenerate what exists]** — the whole spec is "reuse the four seams": FR-1 reuses `classify()`, FR-3 **extends** the ladder (new rung, not a new harness), FR-4 reuses Prime's `error_message` regen. Nothing is rebuilt.
- **[Accidental-complexity anti-principle]** — D-2 **refused** to refactor the shipped navigator oracle into a general policy-injectable runner (a compensating layer on a byte-identity-guarded surface); a separate runner is cheaper and safer than generalizing `evaluate()`.
- **[Genchi Genbutsu — bind to the real artifact]** — the fitness is the **real spec's** `Verify:` clauses run against the **real generated app** in the **real sandbox**, not a proxy/template.
- **[Context-Correctness-by-Construction]** — **found a gap:** Prime consumes a **context-seed → FeatureQueue** (`queue.py:229`), NOT a raw det-req doc, so the spec must be **plan-ingested into a seed** before generation — an unstated context-arrival step. Folded into FR-8 (the CLI owns the spec→seed plan-ingestion) so the spec cannot silently fail to arrive at Prime.

---

## Overview

Wire the SDK's three existing halves into a closed loop: **generation** (`PrimeContractorWorkflow`, the LLM path), **execution+grading** (the `deploy_harness` ladder, in the `benchmark_matrix` sandbox), and the **spec's own `Verify:` oracle** (REQ-08). The loop turns a det-req spec into a working app by (1) planning the spec into a Prime seed, (2) generating, (3) deploying the output and running the spec's command-shaped `Verify:` clauses as a graded **oracle rung**, (4) on a rung failure, feeding the failure back as `error_message` regeneration feedback and iterating until the runnable fitness passes or a fail-closed budget/iteration/stall bound trips. The un-runnable prose majority of the spec is held as an explicit **human-gate residue** — the loop never claims the spec is *satisfied*, only that its *runnable fitness* passed. This is the enforcement half of the cheap-model strategy: a weak model iterates against a hard, spec-derived pass/fail instead of needing to be right first try.

## Objectives

- **O-1:** Make a det-req spec's command-shaped `Verify:` clauses an **executable fitness function** against generated output, run under real isolation — target: a sandboxed runner reports per-FR pass/fail/skip/error for a generated app.
- **O-2:** **Close the loop** — a rung failure regenerates with feedback and re-grades, converging or stopping fail-closed — target: a `<spec> → passing app | honest give-up` run with a report.
- **O-3:** Keep the loop **honest** — explicit fitness coverage (% runnable), the prose residue surfaced for a human Goodhart gate, and the sandbox `isolation_level` recorded — target: the report states coverage + residue + isolation, and never claims spec-satisfaction from oracle-pass.
- **O-4:** **Reuse, don't rebuild** — the runner reuses `classify()`, execution reuses `benchmark_matrix/sandbox`, grading reuses the `deploy_harness` ladder, regeneration reuses Prime's `error_message` retry; additive, no change to the navigator oracle allow-list.

## Risks

| Type | Description | Mitigation | Priority |
|------|-------------|------------|----------|
| security | Running a **generated** app's `Verify:` commands (pytest/curl/uvicorn) = arbitrary untrusted code execution | Route ALL generated-oracle exec through `benchmark_matrix/sandbox` (`run_sandboxed` / `run_service_sandboxed`) — egress-deny, rlimits, process-group kill, secret-scrub, timeout; **never** through `verify_oracle.evaluate` (navigator-only) nor the host shell (FR-1/NR-2) | high |
| quality | **Goodhart** — the model games the runnable fitness (command exits 0) while missing the prose intent | Bind to the D-3 boundary: `pass` = "command rc0" only; surface `assertion_text` residue for a human gate; the loop's terminal state is "fitness passed", never "spec satisfied" (FR-7/NR-6) | high |
| scope-creep | Fitness is only ~5% of clauses → a "green" loop that ignored 95% of the spec | FR-6 reports coverage (runnable / total) + the human-gate residue list; a low-coverage spec is flagged, not silently passed | high |
| reliability | Infinite regeneration / non-converging loop (the LLM never fixes it) | FR-5 fail-closed termination: all-runnable-pass OR `max_cost_usd` OR max-iterations OR **stall** (same failing FRs N rounds); reuse `queue._detect_and_break_cycles` guard | high |
| quality | Re-implementing generation/exec/grading instead of reusing the four seams (Mottainai) | FR-1 reuses `classify()`; FR-3 extends the `deploy_harness` ladder (new rung, not new harness); FR-4 reuses Prime's `error_message` regen — each extends, none forks | medium |
| quality | Refactoring the shipped navigator oracle to make it general (destabilizing a byte-identity-guarded surface) | Build a **separate** generated-app runner; leave `verify_oracle`'s allow-list + goldens untouched (OQ-2) | medium |

## Profile

Declared profile: **internal**

## Functional requirements

- **FR-1 — Sandboxed generated-app oracle runner.** Add a runner that, given a det-req spec and a generated app root, reuses `verify_oracle.classify()` to extract each FR's command-shaped `Verify:` span and executes the runnable ones **inside `benchmark_matrix/sandbox`** (`run_sandboxed` for one-shot e.g. `pytest`, `run_service_sandboxed` for an app+HTTP probe) — returning per-FR `pass|fail|skip|error` plus the applied `isolation_level`; it does **not** use `verify_oracle.evaluate` (navigator-locked) and does **not** touch the navigator allow-list. Name: SDK runs a generated app's command-shaped Verify clauses as an oracle inside the benchmark sandbox and reports per-requirement verdicts with the isolation level. Touches: src/startd8/oracle_loop/runner.py, src/startd8/navigator/verify_oracle.py. Lives: code src/startd8/oracle_loop/runner.py. Approve?: does the runner reuse classify() + the sandbox (never evaluate() / the host shell), returning per-FR verdicts + isolation_level?. Verify: for a fixture generated app + spec, the runner returns a verdict per command-shaped FR, every subprocess ran via a `benchmark_matrix.sandbox` entry (asserted by patching the sandbox boundary), and a non-command FR yields `skip`. Serves: O-1
- **FR-2 — Generated-app runnable-`Verify:` grammar.** Define a `Verify:`-clause convention for a spec whose target is the **generated app** (not the SDK) — a one-shot form (`pytest <path>` / a CLI invocation run via `run_sandboxed`) and a service form (an HTTP probe against the booted app run via `run_service_sandboxed`) — with a documented mapping from clause shape to sandbox entry, so a spec-to-be-built carries oracles runnable against its own output. Name: SDK defines a runnable Verify-clause grammar targeting a generated app mapping one-shot and service clauses to sandbox execution. Touches: docs/design/oracle-generation-loop/VERIFY-GRAMMAR.md, src/startd8/oracle_loop/grammar.py. Lives: doc docs/design/oracle-generation-loop/VERIFY-GRAMMAR.md. Approve?: is the generated-app Verify grammar a documented closed convention mapping clause-shape → sandbox entry (one-shot vs service)?. Verify: the grammar doc enumerates the one-shot and service clause forms, and a fixture spec written to the grammar classifies each clause to the correct sandbox entry (one-shot → run_sandboxed, service → run_service_sandboxed). Serves: O-1
- **FR-3 — Spec-derived ORACLE rung on the deploy-harness ladder.** Extend the `deploy_harness` ladder with an **ORACLE** rung after SMOKE (DISCOVER→INSTALL→BOOT→HEALTH→SMOKE→**ORACLE**→CONTEXT_SMOKE) whose fitness is the FR-1 runner over the spec's `Verify:` clauses (not the generic CRUD SMOKE), graded into the existing `LadderResult` per-rung status. Name: SDK adds a spec-derived oracle rung to the deploy-harness ladder grading the generated app against its own Verify clauses. Touches: src/startd8/deploy_harness/ladder.py, src/startd8/oracle_loop/runner.py. Lives: code src/startd8/deploy_harness/ladder.py. Approve?: does the ORACLE rung reuse the existing ladder/LadderResult and derive its fitness from the spec (not generic CRUD)?. Verify: a `LadderResult` for a generated app carries an ORACLE rung with per-FR verdicts, the rung status is pass iff every runnable FR passed, and the existing rungs (DISCOVER..SMOKE) are unchanged. Serves: O-1, O-2
- **FR-4 — Regenerate-with-feedback wire (not repair).** On an ORACLE-rung failure, format the failing FRs' verdicts (fr_id, command, stderr tail) into a `feature.error_message` and feed it into Prime's existing regenerate-with-feedback path (`process_feature` retry), iterating generate→deploy→ORACLE, explicitly **not** routing to `repair/` (which handles only syntax/import/lint). Name: SDK feeds an oracle-rung failure back as regeneration feedback into the Prime retry loop rather than the syntax-lint repair pipeline. Touches: src/startd8/oracle_loop/loop.py, src/startd8/contractors/prime_contractor.py. Lives: code src/startd8/oracle_loop/loop.py. Approve?: does an oracle FAIL become a Prime `error_message` regeneration (never a `repair/` call)?. Verify: on a fixture whose first generation fails the ORACLE rung, the loop injects the failure as `feature.error_message` and re-invokes generation (asserted), and `repair.run_file_repair` is never called for the oracle failure. Serves: O-2
- **FR-5 — Fail-closed termination + budget contract.** The loop terminates on the FIRST of: all runnable FRs pass · `max_cost_usd` reached (`run(max_cost_usd=…)` / `BudgetManager.check_budget`) · a max-iterations cap · a **stall** (the identical set of failing FRs recurs for N consecutive rounds) — never unbounded; a give-up emits an honest report naming the terminal cause. Name: SDK loop terminates fail-closed on pass or budget or iteration-cap or a repeated-failure stall and reports the terminal cause. Touches: src/startd8/oracle_loop/loop.py, src/startd8/costs/budget.py. Lives: code src/startd8/oracle_loop/loop.py. Approve?: is the loop provably bounded (pass | budget | max-iters | stall) with the terminal cause reported?. Verify: a never-converging fixture stops within the configured cap emitting a report whose terminal cause is one of {budget, max_iterations, stall}, and a stall (same failing FR-set twice) trips before the iteration cap. Serves: O-2, O-3
- **FR-6 — Explicit fitness coverage + prose residue.** The loop reports, for the target spec, the **coverage** (runnable command-shaped FRs / total FRs) as the fitness denominator and lists the non-runnable (`assertion`/`manual`) FRs as an explicit **human-gate residue** — so a "passing" run is unambiguously "the runnable fitness passed", never "the spec is satisfied". Name: SDK reports the fitness coverage fraction and the non-runnable prose residue so a passing loop never reads as spec-satisfied. Touches: src/startd8/oracle_loop/report.py, src/startd8/oracle_loop/loop.py. Lives: code src/startd8/oracle_loop/report.py. Approve?: does the report state runnable/total coverage AND the residue FR list, distinguishing fitness-passed from spec-satisfied?. Verify: the report for a spec with mixed clause kinds shows `coverage = runnable/total`, lists every `assertion`/`manual` FR as residue, and the terminal status string says "runnable fitness passed" not "spec satisfied". Serves: O-3
- **FR-7 — Goodhart gate on the prose residue.** Every ORACLE `pass` carries its `assertion_text`; the report surfaces a **divergence review** — the human confirms each passed command's prose assertion actually holds — and the loop's API/contract refuses to emit a "spec-satisfied" verdict from oracle-pass alone (bind to the REQ-08 D-3 honesty boundary). Name: SDK surfaces each passed oracle's prose assertion for a human divergence review and refuses a spec-satisfied verdict from oracle-pass alone. Touches: src/startd8/oracle_loop/report.py, src/startd8/oracle_loop/loop.py. Lives: code src/startd8/oracle_loop/report.py. Approve?: does every pass carry its assertion_text for a human gate, with no spec-satisfied verdict derivable from oracle-pass?. Verify: each `pass` row in the report includes its `assertion_text`, and there is no code path that returns a "spec satisfied"/"complete" status without a recorded human confirmation. Serves: O-3
- **FR-8 — `startd8 build-to-spec` operator CLI.** Add a console command that drives the loop end-to-end (spec → Prime seed → generate → deploy+ORACLE rung → regenerate-on-fail → report), with `--spec <det-req.md>`, `--max-cost-usd`, `--max-iterations`, `--out <report>`, exiting 0 iff the runnable fitness passed within budget and non-zero otherwise. Name: SDK exposes a build-to-spec command that runs the oracle-driven generation loop and reports pass or the fail-closed terminal cause. Touches: src/startd8/cli.py, src/startd8/oracle_loop/loop.py. Lives: code src/startd8/oracle_loop/loop.py. Approve?: does one command drive spec→(plan-ingest to a Prime seed)→generate→oracle→regenerate→report with a fail-closed exit code?. Verify: `startd8 build-to-spec --spec <fixture> --max-iterations 1 --out <p>` plan-ingests the spec into a Prime context-seed (Prime consumes a seed, not a raw det-req doc — `queue.py:229`), exits 0 on a passing fixture and non-zero (naming the terminal cause) on a failing one, writing the report to `<p>`. Serves: O-2, O-4
- **FR-9 — Additive / seam-preserving.** The feature is standalone: the navigator oracle's allow-list + goldens are unchanged, `benchmark_matrix/sandbox` and `deploy_harness` are extended (new rung) not forked, and Prime's regen path is called not modified beyond feeding `error_message`. Name: The oracle-generation loop reuses classify sandbox ladder and Prime regen without changing the navigator oracle or forking the harnesses. Touches: tests/unit/oracle_loop/test_seam_preservation.py, src/startd8/navigator/verify_oracle.py. Lives: test tests/unit/oracle_loop/test_seam_preservation.py. Approve?: are the navigator oracle allow-list + goldens untouched and the harnesses extended not forked?. Verify: `verify_oracle`'s `_READONLY_NAV_SUBCOMMANDS` + its byte-identity/reachability tests pass unedited, and the oracle_loop package imports the sandbox/ladder/Prime seams rather than re-implementing them (asserted by import inspection). Serves: O-4

## Non-goals

- **NR-1:** Does **NOT** run or auto-satisfy the `assertion`/`manual` (prose) `Verify:` majority — only command-shaped runnable clauses are the fitness; the rest is human-gate residue (FR-6).
- **NR-2:** Does **NOT** modify `verify_oracle`'s navigator read-only allow-list — that stays a safe self-check gate; the generated-app runner is a separate executor (D-2).
- **NR-3:** Does **NOT** use `repair/` for oracle/behavioral failures (repair = syntax/import/lint only) — behavioral fixes go through Prime regenerate-with-feedback (D-1).
- **NR-4:** Does **NOT** drive the `$0` deterministic cascade (`backend_codegen`) — it needs no repair loop; scope is the **LLM path** (Prime/MicroPrime).
- **NR-5:** Does **NOT** add production kernel-isolation (gVisor/Firecracker/Docker) — reuses the sandbox's current isolation and records `isolation_level` honestly (matches sandbox R3-S2, deferred).
- **NR-6:** Does **NOT** emit a "spec satisfied / complete" verdict from oracle-pass alone — the Goodhart boundary (FR-7).
- **NR-7:** Does **NOT** author the target spec's content — the operator/company provides the det-req spec (CLAUDE.md bucket separation); the loop consumes it.

## Owned fields

Only humans enter: the target det-req spec (the FRs + their `Verify:` clauses), the budget/iteration caps, and the Goodhart residue confirmation (FR-7).

## Contract projection

- **Backend:** python-cli-surface
- **Vocabulary home (cite):** REQ-08 (`verify_oracle`) · `benchmark_matrix/sandbox.py` · `deploy_harness/ladder.py` · `contractors/prime_contractor.py` · the cheap-model strategy memory

| Entry (name) | Kind | Words/Structure | Notes |
|--------------|------|-----------------|-------|
| build-to-spec | command | structure | new: `startd8 build-to-spec --spec … [--max-cost-usd] [--max-iterations] [--out]` |
| oracle-rung | projection | structure | the spec-derived ORACLE rung on the deploy-harness `LadderResult` |
| runnable-verify-grammar | convention | structure | one-shot (`run_sandboxed`) vs service (`run_service_sandboxed`) clause forms |

Library seams (Touches file paths): `src/startd8/oracle_loop/{runner,grammar,loop,report}.py`, `src/startd8/deploy_harness/ladder.py`, `src/startd8/cli.py`.
Read-only reuse (not modified): `src/startd8/navigator/verify_oracle.py` (`classify`), `src/startd8/benchmark_matrix/sandbox.py`, `src/startd8/contractors/prime_contractor.py` (regen), `src/startd8/costs/budget.py`.

## Appendix A — Accepted (with where merged)
## Appendix B — Rejected (with rationale)
## Appendix C — Incoming review rounds

*v0.2 — Post-planning self-reflective update. 5 assumptions overturned (D-1 repair→regenerate, D-2 new runner not evaluate(), D-3 extend the ladder not a new harness, D-4 runnable-Verify is greenfield, D-5 oracle-pass≠satisfied), 3 OQs resolved, 9 FRs grounded to real seams. The feature's own name changed (repair → regenerate-with-feedback).*
*v0.3 — Lessons hardening: phantom-reference audit clean, env-failure-degrades rule (FR-1), stall guard (FR-5), single-line/semantic-name FRs.*
*v0.3.1 — Principle hardening: Mottainai (reuse the 4 seams), accidental-complexity (separate runner, don't generalize the shipped oracle), Genchi Genbutsu (real spec × real app × real sandbox), and Context-Correctness — folded the spec→Prime-seed plan-ingestion step into FR-8. Ready for CRP.*
