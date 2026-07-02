# Run 27 Remediation PR Instructions

**Branch:** `codex/gemini-run27-followup`  
**Base:** `main`  
**PR URL:** <https://github.com/neil-the-nowledgeable/startd8-sdk/pull/new/codex/gemini-run27-followup>

## Purpose

This PR formalizes the replacement path for the rejected Gemini
`suite_author` run 27 artifact without mutating the original raw evidence.

The promoted audit store now contains:

- the original rejected run:
  `pricing-cross-tool-authoring-v1-run-27`
- the accepted replacement run:
  `pricing-cross-tool-authoring-v1-run-27-replacement-1`
- a disposition mapping in `dispositions.json`

The implementation must preserve the audit invariant that the batch has 30
scheduled runs while acknowledging that the raw store contains 31 directories
because one scheduled run has a replacement.

## Open the PR

GitHub auth was expired in the local CLI and connector, so open the PR manually:

<https://github.com/neil-the-nowledgeable/startd8-sdk/pull/new/codex/gemini-run27-followup>

Use this title:

```text
[codex] Validate run 27 replacement disposition for S4 intake
```

Use this body:

```md
## Summary

Adds the run 27 replacement flow and hardens reconciliation/S4 gating so the promoted audit store can represent 31 raw runs as 30 effective scheduled runs only when a valid replacement disposition exists.

## Changes

- Add replacement run generator for the rejected Gemini suite-author artifact.
- Persist intake dispositions into the ledger/SQLite.
- Resolve S4 normalized suite lookup by reconciliation `run_dir`.
- Validate `dispositions.json` during reconciliation.
- Block duplicate ordinals unless covered by a valid replacement disposition.
- Report `raw_observed_runs` and `effective_observed_runs`.
- Ensure S4 ignores a rejected suite row only when its replacement is accepted.
- Update promotion SQLite schema so duplicate ordinals do not break audit storage.

## Validation

- `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m pytest -q -p no:cacheprovider tests/unit/test_reconcile_cross_tool_bias_runs.py tests/unit/test_run_cross_tool_bias_s4.py`
- `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m py_compile scripts/reconcile_cross_tool_bias_runs.py scripts/run_cross_tool_bias_s4.py scripts/intake_and_normalize_artifacts.py scripts/generate_replacement_run.py`
- `git diff --check`

Actual promoted store readback:

- `status: accepted`
- `expected_runs: 30`
- `raw_observed_runs: 31`
- `effective_observed_runs: 30`
- `disposition_errors: []`

## Notes

This should still be reviewed carefully before merge because `generate_replacement_run.py` can use Doppler credentials and write to the promoted audit store.
```

## Review checklist

Before approving or merging, verify these points explicitly:

1. `scripts/generate_replacement_run.py`
   - Does not overwrite an existing replacement directory silently.
   - Records attempt metadata durably.
   - Does not leak secrets in stdout, stderr, metadata, or stored prompt output.
   - Clearly operates as a privileged operator script because it can use Doppler
     credentials and write to the promoted store.

2. `scripts/intake_and_normalize_artifacts.py`
   - Preserves the original rejected run in `intake-ledger.json`.
   - Persists `dispositions.json` into both the ledger and `intake.sqlite`.
   - Does not mutate raw evidence under `raw/`.

3. `scripts/reconcile_cross_tool_bias_runs.py`
   - Blocks duplicate ordinals without a valid disposition.
   - Accepts the run 27 replacement case only because the replacement
     relationship is explicit.
   - Reports both raw and effective run counts.
   - Does not treat `31/30` as ordinary success without replacement metadata.

4. `scripts/run_cross_tool_bias_s4.py`
   - Looks up normalized suite paths by reconciliation `run_dir`.
   - Suppresses rejected run 27 only when the replacement row is accepted.
   - Still refuses semantic S4 execution without the reviewed isolated bridge.

## Required local validation

Run from the PR branch:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m pytest -q -p no:cacheprovider \
  tests/unit/test_reconcile_cross_tool_bias_runs.py \
  tests/unit/test_run_cross_tool_bias_s4.py

PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m py_compile \
  scripts/reconcile_cross_tool_bias_runs.py \
  scripts/run_cross_tool_bias_s4.py \
  scripts/intake_and_normalize_artifacts.py \
  scripts/generate_replacement_run.py

git diff --check
```

Expected focused test result:

```text
18 passed
```

## Required promoted-store readback

Run this as a read-only validation of the current promoted store:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 - <<'PY'
import json
from pathlib import Path
from scripts.reconcile_cross_tool_bias_runs import reconcile

root = Path(
    "/Users/neilyashinsky/Documents/dev/startd8-resolved-pricing-adapter"
    "/.startd8/bias-audit-store/pricing-cross-tool-authoring-v1"
)
report = reconcile(root / "raw", root / "authoring-schedule.json")
print(json.dumps({
    "status": report["status"],
    "expected_runs": report["expected_runs"],
    "raw_observed_runs": report["raw_observed_runs"],
    "effective_observed_runs": report["effective_observed_runs"],
    "missing_ordinals": report["missing_ordinals"],
    "duplicate_ordinals": report["duplicate_ordinals"],
    "disposition_errors": report["dispositions"]["errors"],
    "replacement_pairs": report["dispositions"]["replacement_pairs"],
}, indent=2))
PY
```

Expected key values:

```json
{
  "status": "accepted",
  "expected_runs": 30,
  "raw_observed_runs": 31,
  "effective_observed_runs": 30,
  "missing_ordinals": [],
  "disposition_errors": []
}
```

## Merge criteria

Merge only if all of these are true:

- Focused tests pass.
- Syntax checks pass.
- `git diff --check` passes.
- The promoted-store readback reports `30` effective runs and no disposition
  errors.
- Reviewer is comfortable with the operator-script credential/write surface.
- No unrelated worktree files are included.

## After merge

After this PR is merged:

1. Re-run intake and reconciliation against the promoted store.
2. Confirm intake has 15 accepted `suite_author` rows.
3. Run S4 preflight only.
4. Do not execute S4 semantic scoring until the oracle/mutant gate and reviewed
   isolated bridge are both accepted.

