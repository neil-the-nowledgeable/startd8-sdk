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
| Oracle classify (reuse) | `verify_oracle.py:144` `classify()` → `OracleDescriptor{fr_id,kind,command_argv,assertion_text}` | Reuse for span extraction. |
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
