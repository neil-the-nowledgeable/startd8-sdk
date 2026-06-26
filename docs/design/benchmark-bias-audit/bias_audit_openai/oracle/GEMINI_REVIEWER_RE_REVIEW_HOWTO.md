# Gemini Reviewer Re-Review How-To

## Scope

Use this guide when reproducing or refreshing the Gemini non-Claude reviewer
validation for the Phase 3 oracle and mutant admission gate.

The review decides whether the oracle instrument is admissible. It does not
review author-vendor outputs, generated suites, raw cohort captures, S4
execution results, or final bias findings.

## Independence requirements

1. Disclose Google/Gemini affiliation and whether the packet was blinded.
2. Do not rely on Claude-authored oracle logic or Claude-derived calibration
   fixtures.
3. Do not use measured cohort outputs as expected oracle cases.
4. Treat `oracle/canonical_cases.py` as the fixture authority only if it is
   source-derived and not imported from `runs/**` or raw authoring captures.
5. Do not hand-edit `oracle/validation-gate.json`; derive it through the
   validator.

## Review packet

Inspect these artifacts:

- `canonical/spec.md`
- `canonical/pricing.proto`
- `canonical/canonicalization_decisions.md`
- `oracle/reference_oracle.py`
- `oracle/canonical_cases.py`
- `oracle/test_oracle.py`
- `oracle/conftest.py`
- `oracle/oracle-provenance.json`
- `oracle/fixed-open-evidence.json`
- `oracle/reviewer-signoffs.json`
- `oracle/validation-gate.json`
- `mutants/manifest.json`
- `mutants/expected-kill-matrix.csv`
- `mutants/adequacy-report.json`

## Required validation commands

From the repository root:

```bash
python3 scripts/validate_cross_tool_oracle_gate.py
```

Required result: `status` is `accepted`, all checks are `accepted`, and
`errors` is empty.

```bash
PYTHONDONTWRITEBYTECODE=1 pytest -q -p no:cacheprovider \
  docs/design/benchmark-bias-audit/bias_audit_openai/oracle/test_oracle.py
```

Required result on the current accepted surface: 38 tests pass.

## Mutant adequacy review

Confirm that:

- `mutants/manifest.json` status is `accepted`.
- `mutants/expected-kill-matrix.csv` uses `oracle/canonical_cases.py` as the
  fixture source.
- `mutants/adequacy-report.json` records `reference_test_count` as 38.
- All ten listed mutants are validated as kills.
- No import, collection, harness, or environment failure is counted as a
  semantic kill.

## Signoff update rule

If a future Gemini reviewer refreshes this signoff, update the existing Gemini
reviewer object in `oracle/reviewer-signoffs.json`; do not add duplicate Gemini
reviewers for the same admission decision.

Record `decision: "accept"` only when every check above passes. Then run:

```bash
python3 scripts/validate_cross_tool_oracle_gate.py --sync-status
python3 scripts/validate_cross_tool_oracle_gate.py
```

The gate remains accepted only if the validator reports no errors. Acceptance
admits the oracle instrument, not unpromoted artifacts or unsafe generated-suite
execution.
