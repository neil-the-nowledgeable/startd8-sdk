# S4 Suite-Authoring Analysis Plan

**Status:** pre-registered before S4 result consumption  
**Applies to:** `pricing-cross-tool-authoring-v1`  
**Scope:** Suite-authoring artifacts only. This plan produces instrument-quality
execution evidence; it does not make a vendor-bias or score-impact claim.

## Locked inputs and admission

- Input batch: the promoted audit-store batch `pricing-cross-tool-authoring-v1`.
- Every input run must be `accepted` in both `reconciliation-report.json` and
  `intake-ledger.json`; raw temporary captures are never an S4 input.
- The oracle gate must be `accepted` according to
  `oracle/validation-gate.json` at execution time.
- Targets are the reference oracle plus every executable mutant listed as
  `accepted` in `mutants/manifest.json` at execution time. Target source
  hashes are recorded in the preflight output.
- The runner records the normalized-suite checksum from the intake ledger and
  refuses to substitute, normalize, or repair a suite.

## Execution eligibility

Generated Python suites are untrusted inputs. A suite is executable only when
all of the following are true:

1. Its normalized artifact is admitted by the intake ledger.
2. It declares a callable adapter/invoker contract that can be satisfied by
   the frozen S4 bridge.
3. The bridge dry-run passes against the reference oracle in an isolated,
   no-egress execution environment with a scrubbed environment.
4. The same named test inventory is observed for the reference oracle and
   every mutant. Import, collection, adapter, timeout, or harness failures are
   execution failures, never mutant kills.

The present repository does not contain the required isolated, standardized
S4 bridge. The initial S4 command therefore emits a provenance preflight and
`not_executed` matrices, then exits non-zero. It must not execute model-made
code in the developer environment. Adding a bridge is a separately reviewed
implementation change; it must preserve this plan's target inventory and
matrix definitions.

## Pre-registered outcomes

For every execution-eligible suite and target, the runner will store one
pass/fail vector in the exact collected-test order.

- **Oracle pass:** every collected test passes against the reference oracle.
- **Mutant kill:** a mutant has one or more semantic test failures while the
  reference oracle passed the identical inventory. A crash, timeout, missing
  test, or adapter error is `invalid_execution`, not a kill.
- **Suite equivalence:** pairwise Jaccard distance of the binary target-outcome
  vectors, including the reference oracle. Distance 0 is identical; an empty
  union is reported as 0 by convention.
- **Mutant kill matrix:** rows are admitted suites and columns are frozen
  targets. Cells are `pass`, `kill`, `survived`, or `invalid_execution`.

Outputs are `s4-preflight.json`, `suite_equivalence_matrix.csv`,
`mutant_kill_matrix.csv`, and per-suite execution logs under
`analysis/s4-results/`. A blocked preflight is an auditable gate result, not a
zero-result matrix and not a reason to change the input cohort.

## Exclusions and interpretation

- Rejected, missing, or non-suite-author artifacts are excluded with their
  ledger reason.
- Self-checks that exercise an in-suite oracle rather than the frozen bridge
  are not evidence about the reference oracle or mutants.
- S4 reports coverage and equivalence only. It does not estimate a vendor
  effect, adjudicate OPEN items, or support an acceptance verdict. Those steps
  remain S6/S7 and require their own pre-registered analysis.
