# S4 Run 27 Disposition and Next Steps

**Updated:** 2026-06-29  
**Working branch:** `codex/s4-audit-store-intake`  
**Promoted batch:** `/Users/neilyashinsky/Documents/dev/startd8-resolved-pricing-adapter/.startd8/bias-audit-store/pricing-cross-tool-authoring-v1`

## Bottom line

Reconciliation is accepted for the promoted 30-run batch, but S4 should still
fail closed because intake accepts only 14 of 15 `suite_author` artifacts.

The only rejected artifact is:

- `pricing-cross-tool-authoring-v1-run-27`
- experiment: `suite_author`
- tool: `gemini-cli`
- author vendor: `google`
- disposition: `rejected_with_reason`
- reason: `forbidden_import`
- detail: `google.protobuf.json_format`

The rejection is valid under the current intake policy. The generated suite
imports a third-party protobuf helper:

```python
from google.protobuf.json_format import MessageToDict
```

Generated suite artifacts are currently admitted only when they use stdlib plus
`pytest`. Do not edit raw evidence to make this pass.

## Current gate state

| Gate | State | Evidence |
|---|---|---|
| Reconciliation | accepted | `30/30` runs, no missing ordinals, no reconciliation errors |
| Intake | blocked for S4 | `29/30` accepted overall; `14/15` `suite_author` accepted |
| Run 27 disposition | rejected | real forbidden import in raw `suite.py` |
| S4 execution | blocked | missing one accepted Gemini `suite_author` artifact |

## Files to inspect

Promoted batch files:

- `reconciliation-report.json`
- `intake-ledger.json`
- `authoring-schedule.json`
- `raw/run_27_suite_author_gemini-cli_sample_2/suite.py`
- `raw/run_27_suite_author_gemini-cli_sample_2/metadata.json`
- `raw/run_27_suite_author_gemini-cli_sample_2/authoring_manifest.json`
- `raw/run_27_suite_author_gemini-cli_sample_2/suite_manifest.json`

Repo-side scripts:

- `scripts/intake_and_normalize_artifacts.py`
- `scripts/reconcile_cross_tool_bias_runs.py`
- `scripts/run_cross_tool_bias_s4.py`

## Reproduce the current status

Run these from a clean SDK worktree:

```bash
export PROMOTED_STORE=/Users/neilyashinsky/Documents/dev/startd8-resolved-pricing-adapter/.startd8/bias-audit-store
export BATCH_ID=pricing-cross-tool-authoring-v1
export BATCH_ROOT="$PROMOTED_STORE/$BATCH_ID"

PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src \
  python3 scripts/intake_and_normalize_artifacts.py \
  --store-root "$PROMOTED_STORE" \
  --batch-id "$BATCH_ID"

PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src \
  python3 scripts/reconcile_cross_tool_bias_runs.py \
  --raw-root "$BATCH_ROOT/raw" \
  --schedule "$BATCH_ROOT/authoring-schedule.json"
```

Expected result:

- intake: `29/30 accepted`
- reconciliation: `accepted (30/30 runs)`
- run 27 remains rejected with `forbidden_import:
  google.protobuf.json_format`

Use this quick readback to verify:

```bash
python3 - <<'PY'
import collections
import json
import pathlib

root = pathlib.Path(
    "/Users/neilyashinsky/Documents/dev/startd8-resolved-pricing-adapter"
    "/.startd8/bias-audit-store/pricing-cross-tool-authoring-v1"
)
report = json.loads((root / "reconciliation-report.json").read_text())
ledger = json.loads((root / "intake-ledger.json").read_text())

print("reconciliation", report["status"], report["observed_runs"], "/", report["expected_runs"])
print("reconciliation_errors", collections.Counter(
    error for run in report["runs"] for error in run.get("errors", [])
))
print("intake", ledger["accepted"], "/", ledger["total"], "rejected", ledger["rejected"])
print("rejected", [
    (run["run_id"], run["experiment"], run["tool_id"], run["reason_code"], run["detail"])
    for run in ledger["runs"]
    if run["status"] != "accepted"
])
PY
```

## Disposition options

### Option A: keep run 27 rejected and keep S4 blocked

Use this if the audit requires a complete 15-suite intake set before S4.

Required actions:

1. Record the disposition as final: run 27 is rejected because it imports
   `google.protobuf.json_format`.
2. Do not run S4 semantic scoring.
3. Produce a replacement artifact through a documented replacement path before
   reopening S4.

This is the strictest and safest interpretation of the current controls.

### Option B: generate a replacement Gemini suite artifact

Use this if the audit still requires balanced `suite_author` coverage across
OpenAI, Google, and Anthropic.

Required controls:

1. Preserve run 27 raw evidence unchanged.
2. Generate a new Gemini `suite_author` attempt in a separate raw run directory.
3. Assign a new ordinal or replacement identifier that does not overwrite run 27.
4. Record the replacement relationship explicitly:
   - rejected source run: `pricing-cross-tool-authoring-v1-run-27`
   - replacement run ID
   - reason: `forbidden_import`
   - reviewer/approver
   - timestamp
5. Re-run reconciliation and intake.
6. Proceed to S4 only if intake has 15 accepted `suite_author` artifacts and
   reconciliation remains accepted.

Do not hand-edit the generated suite to remove the import unless the audit
methodology is updated to allow mechanical or reviewer-approved repair. The
current intake script only performs whitespace normalization.

### Option C: change S4 admission to allow 14 accepted suites

Use this only if reviewers explicitly accept an unbalanced suite set.

Required controls:

1. Document the statistical and audit impact of dropping one Gemini
   `suite_author` artifact.
2. Update S4 pre-registration to state that run 27 is excluded before semantic
   results are inspected.
3. Keep vendor/tool counts visible in the S4 output.
4. Do not present the result as the original balanced 15-suite design.

This changes the analysis population and should require reviewer sign-off.

### Option D: widen the intake allow-list for `google.protobuf`

Do not do this as a quick fix.

The current import policy is simple and auditable: stdlib plus `pytest`.
Allowing `google.protobuf` may be defensible for protobuf-message comparison,
but it broadens the suite dependency surface and should be handled as a policy
change with tests, reviewer rationale, and explicit S4 implications.

If this path is chosen, require at least:

1. A written rationale for why protobuf JSON conversion is part of the allowed
   neutral harness surface.
2. A test proving the import checker accepts only the intended protobuf helper,
   not arbitrary third-party dependencies.
3. A reviewer sign-off before reclassifying run 27.
4. A rerun of intake and S4 preflight.

## Recommended next step

Take Option B if the goal remains the original balanced cross-tool audit:
replace the rejected Gemini suite artifact without mutating run 27.

The next implementation task should be narrowly scoped:

1. Add a documented replacement/disposition mechanism for rejected intake rows.
2. Generate or register one replacement Gemini `suite_author` artifact.
3. Re-run reconciliation and intake.
4. Confirm intake has 15 accepted `suite_author` artifacts.
5. Only then run S4 preflight.

## S4 preflight guard

Before running S4, verify the gate explicitly:

```bash
python3 - <<'PY'
import collections
import json
import pathlib

root = pathlib.Path(
    "/Users/neilyashinsky/Documents/dev/startd8-resolved-pricing-adapter"
    "/.startd8/bias-audit-store/pricing-cross-tool-authoring-v1"
)
ledger = json.loads((root / "intake-ledger.json").read_text())
counts = collections.Counter(
    (run["experiment"], run["status"])
    for run in ledger["runs"]
)
print(counts)
suite_accepted = sum(
    1 for run in ledger["runs"]
    if run["experiment"] == "suite_author" and run["status"] == "accepted"
)
if suite_accepted != 15:
    raise SystemExit(f"S4 blocked: expected 15 accepted suite_author artifacts, got {suite_accepted}")
print("S4 intake gate accepted")
PY
```

Expected current output is a failure:

```text
S4 blocked: expected 15 accepted suite_author artifacts, got 14
```

That failure is correct until run 27 is replaced or the S4 admission rules are
formally changed.

## Stop conditions

Stop and do not run S4 semantic scoring if any of these are true:

- `reconciliation-report.json` is not `accepted`.
- `intake-ledger.json` has fewer than 15 accepted `suite_author` artifacts.
- run 27 is reclassified without reviewer-approved policy change or replacement
  evidence.
- raw evidence under `raw/` has been edited.
- the S4 pre-registration has not been updated for any population change.

