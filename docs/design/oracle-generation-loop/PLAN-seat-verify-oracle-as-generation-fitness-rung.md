# Implementation Plan — Seat the Verify Oracle as the Generation Fitness Rung

**Project:** startd8-sdk   **Pairs with:** `REQ-seat-verify-oracle-as-generation-fitness-rung.md`
**Version:** 1.0   **Date:** 2026-08-16
**Semantic name:** *Plan for wiring the spec's Verify oracle into the generation loop via a sandboxed runner, a spec-derived ladder rung, and Prime regenerate-with-feedback.*
**Canonical ref:** `cc:intent:oracle-generation-loop:plan:seat-verify-oracle-fitness-rung`

> Produced by the `/reflective-requirements` loop. Every seam is cited at real `file:line` from the
> grounding exploration; the discoveries are folded into REQ §0 (v0.2). This file is the how.

## Seam map (what exists, from reading the code)

| Seam | file:line | What it means |
|------|-----------|---------------|
| Oracle classify (**do NOT reuse for generated-app clauses — R1-F2**) | `verify_oracle.py:144` `classify()` — `_classify_clause` promotes only `startd8`-verb spans (`_ALLOWED_VERBS`, `:38`) | A `pytest`/`curl` clause → `assertion`; FR-1 needs **FR-2's OWN parser**, not `classify()`. |
| Oracle evaluate (**do NOT reuse**) | `verify_oracle.py:227` `evaluate` + `:183` `_is_readonly_allowlisted` (hard `argv[1]=="navigator"`) | Structurally navigator-locked, no injectable policy → FR-1 needs a fresh runner. |
| One-shot sandbox | `sandbox.py:123` `run_sandboxed(cmd, workspace, cfg, *, file_path)` → `SandboxResult` | For `pytest`/CLI Verify clauses (egress-deny, rlimits, pgroup kill, secret-scrub, timeout). |
| Service sandbox | `sandbox.py:276` `run_service_sandboxed(server_cmd, workspace, port, client, *, readiness_mode, health_path)` → `ServiceResult` | For app+HTTP Verify clauses; loopback-allowed/egress-denied; guaranteed teardown. `violation` = env-failure → **degrade, not fail** (`sandbox.py:188`). |
| Deploy ladder (extend) | `ladder.py:21` `Stage` enum · `ladder.py:97` `LadderResult` · `smoke.py:70` generic-CRUD SMOKE | Reuse the skeleton; add the ORACLE rung (spec-derived) after SMOKE. `deploy.py:45` `deploy_app_local(app_root,…)`. |
| Prime generation | `prime_contractor.py:438` `PrimeContractorWorkflow` · `:5856` `run(max_features,stop_on_failure,max_cost_usd)` · seed via `queue.py:229` `add_features_from_seed` | Input = context-seed→FeatureQueue (NOT a raw det-req doc). |
| Prime regen-with-feedback (the wire) | `prime_contractor.py:2564` `process_feature` re-develops carrying `feature.error_message` (`:2608/:3764`), cap `max_retries=6` (`:606`) | FR-4's inner loop — feed the oracle FAIL here, NOT repair. |
| Repair (**not for this**) | `orchestrator.py:519` `run_file_repair(files,diagnostics,…)`; `diagnostics.py:157` classifies syntax/import/lint only | An oracle/logic failure has no repair route (`diagnostics.py:216-230` bare pass-through). |
| Budget | `prime_contractor.py:5856` `run(max_cost_usd=…)` (cheap ceiling) · `budget.py:196` `check_budget` raises `BudgetExceededError` | FR-5 termination. |
| Cycle/stall guard | `queue.py:360/369` `_detect_and_break_cycles`/`_find_cycles` | FR-5 stall detection idea. |

## Per-FR implementation

- **FR-2 — runnable-Verify grammar (BUILD FIRST, OQ-1).** New `docs/…/VERIFY-GRAMMAR.md` + `oracle_loop/grammar.py`: a closed convention — one-shot clauses (first token a runnable verb like `pytest`/`python -m`/a generated console script) → `run_sandboxed`; service clauses (an HTTP method+path probe) → `run_service_sandboxed` with a `client(port)` built from the clause. Greenfield (D-4) — the corpus proves the *shape* (`pytest`/`curl` spans exist) but never targeted a generated app. Deps: none.
- **FR-1 — sandboxed runner.** New `oracle_loop/runner.py`: `run_oracle(spec_path, app_root, *, cfg) -> List[OracleVerdict]`. Reuse `verify_oracle.classify()` for extraction; map each command-shaped descriptor via FR-2 grammar to `run_sandboxed`/`run_service_sandboxed`; translate `SandboxResult.returncode`/`ServiceResult.client_outcome` → `pass|fail`, `violation` → `error` (env-failure, degrade), non-command → `skip`. Carry `isolation_level`. Deps: FR-2.
- **FR-3 — ORACLE rung.** Edit `deploy_harness/ladder.py`: add `Stage.ORACLE` after SMOKE; a rung handler calling FR-1's `run_oracle` on the booted app; fold per-FR verdicts into `LadderResult`; rung pass iff every runnable FR passed. Existing rungs untouched (byte-check). Deps: FR-1.
- **FR-4 — regen-with-feedback wire.** New `oracle_loop/loop.py`: on an ORACLE-rung FAIL, format failing verdicts (`fr_id` + `command_argv` + stderr tail) into `feature.error_message`, re-invoke Prime's `process_feature` retry (NOT `run_file_repair`). Deps: FR-3 + Prime.
- **FR-5 — termination.** In `loop.py`: bound = first of {all runnable pass · `max_cost_usd` via `run()`/`check_budget` · max-iterations · stall (identical failing-FR-set N rounds — a small set-equality tracker, cf. `queue._find_cycles`)}; emit terminal cause. Deps: FR-4.
- **FR-6/FR-7 — coverage + Goodhart.** New `oracle_loop/report.py`: coverage = runnable/total from `classify()` kinds; residue = the `assertion`/`manual` FRs; every `pass` row carries `assertion_text`; the terminal status string is "runnable fitness passed" and there is NO code path emitting "spec satisfied" without a recorded human confirm. Deps: FR-5.
- **FR-8 — CLI.** Edit `cli.py`: `startd8 build-to-spec --spec --max-cost-usd --max-iterations --out`; drives seed→`run()`→ladder(ORACLE)→loop→report; exit 0 iff runnable-fitness-passed-in-budget. Deps: FR-4..7.
- **FR-9 — seam preservation.** New `tests/unit/oracle_loop/test_seam_preservation.py`: assert `verify_oracle._READONLY_NAV_SUBCOMMANDS` + its goldens unedited; assert `oracle_loop` imports the sandbox/ladder/Prime seams (import inspection). Deps: all.

## Build order

```
FR-2 (grammar) → FR-1 (runner) → FR-3 (ORACLE rung) → FR-4 (regen wire) → FR-5 (terminate)
                                                    → FR-6/FR-7 (coverage+Goodhart) → FR-8 (CLI) → FR-9 (guards, last)
```
A thin end-to-end demo is possible after FR-4 on a small hand-authored generated-app spec (one `pytest` clause).

## Discoveries fed back to REQ §0 (v0.2)

| # | v0.1 assumed | Planning found | Impact |
|---|--------------|----------------|--------|
| D-1 | feed failure to `repair/` | repair = syntax/import/lint only; behavioral fix = Prime `error_message` regen | FR-4 rewired; feature renamed (repair→regenerate) |
| D-2 | reuse `verify_oracle.evaluate` | navigator-locked, no injectable policy | FR-1 = separate sandboxed runner reusing `classify()` |
| D-3 | build a deploy+grade harness | `deploy_harness` ladder already exists; SMOKE is generic CRUD | FR-3 = one new spec-derived ORACLE rung |
| D-4 | spec Verify clauses are ready | ~5% runnable; zero target a generated app | FR-2 greenfield, sequenced first |
| D-5 | oracle-pass ≈ satisfied | D-3 honesty boundary; residue preserved, uncompared | FR-6/FR-7 coverage + Goodhart gate |

*v1.0 — every FR mapped to a real seam; the loop's novel core is FR-1 (sandboxed runner) + FR-2 (greenfield grammar) + FR-3 (spec-derived rung), wiring FR-4 into Prime's existing regen. Reuses sandbox/ladder/Prime/classify; forks nothing.*
*v1.1 — Post-CRP R1 (see REQ Appendix A). Seam-map corrected: `classify()` is verb-gated → FR-1 uses FR-2's own parser (R1-F2). FR-2 service clauses are a data-only probe schema (the `client(port)` runs host-side — R1-F3). FR-3 appends ORACLE last + adds `oracle_verdicts` (R1-S3/S4). FR-4 honors Prime regen preconditions + structured feedback (R1-S5/F7). FR-5 cumulative budget + monotone stall (R1-S6/F4). Build order adds a passing + a failing-then-fixable fixture app (R1-S7) and the FR-10 telemetry line (R1-S8). Novel-core unchanged; the reuse claims are now accurate.*

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
| (none yet) |  |  |  |  |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none yet) |  |  |  |  |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — claude-opus-4-8-1m — 2026-08-16

- **Reviewer**: claude-opus-4-8 (1M context)
- **Date**: 2026-08-16 21:20:00 UTC
- **Scope**: Plan review (S-prefix) — seam-map API/reuse validation against real code + sponsor-weighted scrutiny (sandbox boundary, ladder rung integration, regen wire, termination/budget). Targeted reads: `verify_oracle.py`, `benchmark_matrix/sandbox.py`, `deploy_harness/ladder.py`, `contractors/prime_contractor.py`, `costs/budget.py`.

**Executive summary (top risks / gaps):**

- **Blocking reuse defect (S1):** the seam map's "Oracle classify (reuse)" row is over-claimed — `classify()` only promotes `startd8`-verb spans to `command` (`_ALLOWED_VERBS={"startd8"}`, `verify_oracle.py:38`), so it returns `assertion` for the `pytest`/`curl` clauses FR-1 must run. FR-1's extraction cannot reuse `classify()` unchanged; the plan must pick a resolution (see S1) or the whole build stalls at FR-1.
- **Host-side exec escape (S2):** `run_service_sandboxed` calls `client(port)` in the host process (`sandbox.py:334`); FR-2 building a client from clause text is an un-sandboxed path. Constrain the service grammar to a data-only probe.
- **Ladder integration under-specified (S3, S4):** `Stage` order is a hardcoded `_STAGE_ORDER` dict (`ladder.py:36`) and inserting ORACLE renumbers CONTEXT_SMOKE — so "existing rungs untouched (byte-check)" is not literally true; and `StageResult` is scalar (`ladder.py:53`) with no per-FR verdict field, so "fold per-FR verdicts into `LadderResult`" needs a named home.
- **Prime regen preconditions (S5):** the `error_message` regen path only fires when `feature.status==GENERATED` and `self.code_generator` is set (`prime_contractor.py:2604`), and a `_seam_marked_targets` write-guard can reject a regen loud (`:2582`). The FR-4 wire must set feature state and classify a guard-reject distinctly.
- **Budget double-counting (S6):** `run(max_cost_usd=)` is a *per-invocation* ceiling; the outer loop re-invokes Prime, so a fresh ceiling each iteration means the effective spend is `max_cost_usd × iterations × (inner max_retries=6)`. The plan must thread a *cumulative* remaining budget or the fail-closed claim is per-invocation only.

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-S1 | Interfaces | critical | The seam map row "Oracle classify (reuse) … Reuse for span extraction" is over-claimed: `_classify_clause` returns `KIND_COMMAND` only when `argv[0] in _ALLOWED_VERBS` and `_ALLOWED_VERBS = frozenset({"startd8"})` (`verify_oracle.py:38,127`). A generated-app `pytest`/`curl` clause → `KIND_ASSERTION`. Add a plan step under FR-1/FR-2 that resolves this: either (a) FR-2 clauses are `startd8`-verb wrappers, or (b) FR-2's `grammar.py` owns a **generated-app classifier** and FR-1 extracts via it, reusing only `OracleDescriptor` as the data shape — not `classify()`. | Every FR downstream (FR-3 rung, FR-4 wire) depends on FR-1 producing runnable descriptors; on a real FR-2 spec `classify()` yields zero, so the loop silently grades nothing. Cannot be fixed by editing `_ALLOWED_VERBS` — that breaks FR-9/NR-2's byte-identity guard on the navigator oracle. | Seam map "Oracle classify" row; "Per-FR implementation" FR-1/FR-2 | Unit test: `classify()` over a fixture FR-2 spec's `pytest` clause returns `kind!="command"` — proving reuse-as-extraction fails; the chosen resolution returns a command descriptor. |
| R1-S2 | Security | high | Seam map "Service sandbox" row omits that `client(port)` runs in the **host process** (`sandbox.py:334`, inside the `finally`-guarded block but not under `sandbox-exec`/`unshare`). Add a note + a FR-2 constraint: the service-clause `client(port)` the runner builds must be a fixed loopback HTTP probe rendered from a **declarative** clause struct (method/path/expected-status), never code derived from clause text. | The Risks table's "route ALL exec through the sandbox" invariant has a hole here; a clause-driven client is untrusted-input→host-code. Only `server_cmd` is network-isolated; the client is not. | Seam map "Service sandbox" row; FR-2 line "a `client(port)` built from the clause" | Assert the runner's client is a parameterized probe over a whitelisted verb set with no `eval`/`exec`/import of clause content; fuzz a malicious clause and confirm no host code path executes it. |
| R1-S3 | Architecture | high | FR-3 says "add `Stage.ORACLE` after SMOKE … Existing rungs untouched (byte-check)." But `_STAGE_ORDER` is a hardcoded int map (`ladder.py:36`) and `highest_stage` advances by `stage.order` (`ladder.py:131`); inserting ORACLE between SMOKE(4) and CONTEXT_SMOKE(5) forces CONTEXT_SMOKE→6. State the plan explicitly: `_STAGE_ORDER` **is** edited (ORACLE=5, CONTEXT_SMOKE=6), and the "byte-check" applies to rung *handlers/behavior*, not the enum table — or append ORACLE at order 6 (after CONTEXT_SMOKE) to leave the table append-only. | The FR-9 seam-preservation test asserts existing rungs unchanged; a reviewer reading "byte-check" will expect `ladder.py` diff-free, which is impossible if ORACLE sits mid-sequence. Ambiguity here will fail FR-9's own gate. | FR-3 "Existing rungs untouched (byte-check)"; FR-9 | Decide insertion order; assert the DISCOVER..SMOKE `StageResult` *outcomes* are identical pre/post, and that `highest_stage` ordering is monotone with ORACLE inserted. |
| R1-S4 | Data | high | FR-3 folds "per-FR verdicts into `LadderResult`", but `StageResult` carries only `status/reason/ms` (`ladder.py:53`) and `LadderResult` has no per-FR container. Specify the home: add a typed `oracle_verdicts: Dict[str, OracleVerdict]` (or reuse the `outbound_context_smoke: Dict[str,StageResult]` pattern at `ladder.py:115`) and say whether this edits `LadderResult` (tension with "forks nothing"). | "Fold per-FR verdicts into LadderResult" is not implementable against the current scalar `StageResult`; without naming the field, FR-3's Verify ("a LadderResult … carries an ORACLE rung with per-FR verdicts") has no schema to assert against, and it silently modifies the shared model. | FR-3 "fold per-FR verdicts into `LadderResult`" | Add the field; assert a round-tripped `LadderResult.model_dump()` carries per-FR ORACLE verdicts and existing consumers of `LadderResult` still validate. |
| R1-S5 | Risks | high | FR-4's "re-invoke Prime's `process_feature` retry" glosses two real preconditions: the regen branch only runs when `feature.status==FeatureStatus.GENERATED` and `self.code_generator` is truthy (`prime_contractor.py:2604`); and `_seam_marked_targets` can reject a feature loud before any regen (`:2582`, returns False, `fail_feature`). The loop must (a) set the feature to GENERATED with `error_message` before re-invoking, and (b) classify a seam-guard/`fail_feature` False as a **loop-fatal** outcome, not another ORACLE FAIL round (else it counts as stall churn). | Feeding `error_message` to a PENDING feature or one with `code_generator=None` silently no-ops the regen; and a seam-guard reject looks like "generation failed" and would burn iterations. Both corrupt FR-5's termination accounting. | FR-4 "re-invoke Prime's `process_feature` retry" | On a fixture, assert the loop sets `status=GENERATED`+`error_message` pre-retry; and a seam-marked target yields terminal cause `regen_rejected`, not a stall. |
| R1-S6 | Ops | high | FR-5 lists `max_cost_usd` as a bound, but `run(max_cost_usd=)` is a **per-`run()` ceiling** (`prime_contractor.py:5856`); the outer loop calls `run()` per iteration, so each iteration gets a *fresh* ceiling. The plan must thread a **cumulative** budget: track total spend across iterations (via `costs/` or the returned summary) and pass `max_cost_usd = remaining` into each inner `run()`, so the ceiling is a whole-loop bound. Note the compounding with inner `max_retries=6`. | Without cumulative threading, "fail-closed on `max_cost_usd`" is only per-invocation; the real worst case is `iterations × max_cost_usd × ≤6 retries`. This is the double-counting the sponsor flagged (focus §5). | FR-5 "`max_cost_usd` via `run()`/`check_budget`"; Budget seam row | Assert across a multi-iteration fixture that cumulative spend never exceeds the operator's `--max-cost-usd`, decrementing the inner ceiling each iteration. |
| R1-S7 | Validation | medium | The "thin end-to-end demo … after FR-4 on a small hand-authored generated-app spec (one `pytest` clause)" needs a concrete fixture committed as part of the build order (both a *passing* app and a *deliberately-failing-then-fixable* app) so FR-4/FR-5 convergence and give-up are demonstrable, not just asserted. | The plan's demo is described but not scheduled as an artifact; FR-5's "never-converging fixture" and FR-4's "first generation fails then regenerates" Verify clauses both need real fixtures, and building them once (Mottainai) serves FR-1/3/4/5/8 tests. | "Build order" demo sentence; add a fixtures step | A committed `tests/.../fixtures/` pair drives the FR-4 convergence test and the FR-5 stall/give-up test. |
| R1-S8 | Ops | medium | Add an observability line: the loop should emit per-iteration structured telemetry (iteration index, coverage, per-FR verdict deltas, cumulative cost, terminal cause) via the SDK's `get_logger`/OTel bridge, so a fail-closed give-up is diagnosable and the cheap-model convergence curve is measurable. | The report is a terminal artifact; without per-iteration telemetry the operator cannot see *why* a loop churned or whether the cheap-model thesis is holding (convergence per dollar). Cheap to add — the SDK already has the OTel log bridge. | New per-FR line under FR-5/FR-6 | Assert each iteration emits a structured log record with the named fields; a give-up run's trace shows the terminal cause and the cost curve. |

**Endorsements** (prior untriaged suggestions this reviewer agrees with): none — R1 is the first review round; no prior untriaged items exist.

---

## Requirements Coverage Matrix — R1

Analysis only (not triage). Maps each requirement FR/section → plan coverage, with gaps.

| Requirement Section | Plan Step(s) | Coverage | Gaps |
| ---- | ---- | ---- | ---- |
| FR-1 (sandboxed runner) | Per-FR "FR-1 — sandboxed runner"; seam rows classify/one-shot/service | Partial | Reuse of `classify()` for `pytest`/`curl` extraction is incorrect as-is (R1-S1/R1-F2); host-side `client(port)` exec path not addressed (R1-S2/R1-F3). |
| FR-2 (runnable-Verify grammar) | Per-FR "FR-2 — runnable-Verify grammar (BUILD FIRST)" | Partial | No coverage floor / authoring target (R1-F1); no console-script resolution rule; service-form probe schema undefined + un-sandboxed client (R1-F3). |
| FR-3 (ORACLE rung) | Per-FR "FR-3 — ORACLE rung"; ladder seam row | Partial | `_STAGE_ORDER` renumber vs "byte-check" contradiction (R1-S3); no named per-FR verdict home in `LadderResult` (R1-S4). |
| FR-4 (regen-with-feedback wire) | Per-FR "FR-4 — regen-with-feedback wire"; Prime regen seam row | Partial | GENERATED-status + `code_generator` preconditions and seam-guard reject path unaddressed (R1-S5); free-text `error_message` under-structured for cheap model (R1-F7). |
| FR-5 (fail-closed termination + budget) | Per-FR "FR-5 — termination"; budget + cycle/stall seam rows | Partial | Set-equality stall defeated by rotating-failure churn (R1-F4); `max_cost_usd` is per-`run()` not cumulative (R1-S6). |
| FR-6 (fitness coverage + prose residue) | Per-FR "FR-6/FR-7 — coverage + Goodhart" | Partial | Coverage reported but not gated (R1-F1); empty-runnable-set vacuous-pass not handled (R1-F6). |
| FR-7 (Goodhart gate) | Per-FR "FR-6/FR-7 — coverage + Goodhart" | Partial | Confirmation has no persisted per-pass disposition artifact; refusal is negative-only, not defaulted-un-confirmed (R1-F5). |
| FR-8 (`build-to-spec` CLI) | Per-FR "FR-8 — CLI" | Full | Plan-ingestion spec→seed step present; exit-code contract stated. Add `--min-coverage` if R1-F1 accepted. |
| FR-9 (additive / seam-preserving) | Per-FR "FR-9 — seam preservation" | Partial | "byte-check" cannot literally hold if `_STAGE_ORDER`/`StageResult`/`LadderResult` are edited for FR-3 (R1-S3/R1-S4); scope of "unchanged" needs narrowing to behavior. |
