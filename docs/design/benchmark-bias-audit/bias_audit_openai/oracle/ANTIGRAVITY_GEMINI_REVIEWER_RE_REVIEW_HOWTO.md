# Antigravity/Gemini Reviewer Re-Review How-To

**Audience:** Antigravity / Gemini reviewer  
**Role:** Independent non-Claude admission reviewer; Google/Gemini affiliation disclosed  
**Blinding:** Blinded where practical  
**Current gate status:** Blocked only on `reviewer_signoff`  
**Date prepared:** 2026-06-22

This is the handoff for the Antigravity/Gemini reviewer to re-review the corrected oracle after the independent fixture remediation.

## Your Review Boundary

Your job is to decide whether the oracle and mutant battery are defensible scoring instruments for the bias audit.

This is not a verdict on S4 bias results, not a review of model-generated suites, and not a review of Gemini/Antigravity cohort quality.

Approve only if the scoring instrument is independent, source-traceable, and executable.

## Blinding Instructions

You should be blinded where practical because Gemini/Antigravity is one of the measured authoring surfaces.

Ask the audit operator for a blinded packet if you need to inspect generated outputs or cohort labels. For this oracle re-review, most required files can be reviewed without using cohort outputs:

- canonical contract files
- reference oracle
- independent canonical fixtures
- tests
- mutant definitions
- evidence reports
- provenance

If full blinding is not practical because commit history, file paths, or prior signoff records reveal affiliations, disclose that in your signoff by setting `"blinded": false` or by explaining partial blinding in the rationale.

Do not review or rely on your own measured Gemini/Antigravity cohort outputs when deciding whether the oracle is acceptable.

## What Changed

The earlier review blocked the gate because executable oracle/evidence artifacts were incomplete. A later Codex review also correctly blocked because `oracle/test_oracle.py` imported expected cases from a measured Codex cohort run under `runs/**`.

That contamination has now been remediated.

Review these remediation commits:

- `8cb986422d0e05d000666b7a90d9df28c6d8afd5` — replaces cohort-derived calibration fixtures with `oracle/canonical_cases.py`
- `b453c985` — records independent fixture provenance in `oracle/oracle-provenance.json`

The corrected independent fixture source is:

- `oracle/canonical_cases.py`

## Files To Review

Canonical authority:

- `canonical/spec.md`
- `canonical/pricing.proto`
- `canonical/canonicalization_decisions.md`
- `brief/pricing-task-brief.md`
- `brief/source-bibliography.md`
- `brief/source-to-brief-traceability.md`
- `oracle/fixed-open-evidence.json`

Oracle and fixtures:

- `oracle/reference_oracle.py`
- `oracle/canonical_cases.py`
- `oracle/test_oracle.py`
- `oracle/conftest.py`
- `oracle/oracle-provenance.json`

Mutant battery:

- `mutants/manifest.json`
- `mutants/src/*.py`
- `mutants/expected-kill-matrix.csv`
- `mutants/adequacy-report.json`

Gate and signoff state:

- `oracle/reviewer-signoffs.json`
- `oracle/validation-gate.json`

## Independence Checks

Verify:

1. `oracle/test_oracle.py` imports `VALID_CASES` and `INVALID_CASES` from `canonical_cases`.
2. No oracle Python file imports or loads `runs/**`.
3. `oracle/canonical_cases.py` has explicit request/expected-response fixtures and no cohort-run imports.
4. `oracle/oracle-provenance.json` records the fixture remediation commit:
   `8cb986422d0e05d000666b7a90d9df28c6d8afd5`.
5. `claude_derived_portions` is empty for the recorded authorship entries.
6. The oracle semantics can be derived from the canonical spec and proto without relying on Codex, Claude, Gemini, or Antigravity generated suites.

Useful check:

```bash
rg "runs/s2-codex|runs/" docs/design/benchmark-bias-audit/bias_audit_openai/oracle/*.py
```

Expected result:

```text
No matches
```

## Semantic Spot Checks

Spot-check the reference oracle and independent fixtures for these material behaviors:

- Pure function boundary: no database, network, clock, or hidden state.
- Decimal arithmetic: uses exact decimal handling, not binary float.
- Default strategy: omitted `discount_strategy` means `DISCOUNT_STRATEGY_CASCADE`.
- Strategy distinction: `CASCADE` applies percentage levels sequentially; `SUM` adds levels once.
- Rounding: output-only quantization, default scale `2`, default `HALF_EVEN`.
- Fixed reductions: apply after percentage reductions.
- Fixed overrun: invalid request, not clamp to zero.
- Candidate unit amount: selected only when present, positive, and strictly lower than `unit_amount`.
- Price-on-request: excluded from numeric totals and counted in `price_on_request_count`.
- Validation: invalid inputs raise `ValueError` in the oracle harness.

## Required Commands

From the repository root:

```bash
cd docs/design/benchmark-bias-audit/bias_audit_openai/oracle

pytest test_oracle.py --oracle-module reference_oracle -q
```

Expected result:

```text
29 passed
```

Run the mutant calibration:

```bash
for m in mutant_round_half_up mutant_round_down mutant_sum_for_cascade \
         mutant_cascade_for_sum mutant_fixed_before_percent mutant_candidate_any_positive \
         mutant_por_total mutant_float_arithmetic mutant_round_intermediate mutant_clamp_overrun; do
  echo "=== $m ==="
  if pytest test_oracle.py --oracle-module "$m" -q --tb=no; then
    echo "SURVIVED $m"
  else
    echo "KILLED $m"
  fi
done
```

Expected result:

- All 10 mutants are killed.
- No mutant survives.
- No kill is merely an import error, syntax error, or harness crash.

Run the derived gate validator:

```bash
cd ..
python3 ../../../../scripts/validate_cross_tool_oracle_gate.py --sync-status
```

Expected before reviewer signoffs are updated:

- `oracle_provenance`: `accepted`
- `evidence_mapping`: `accepted`
- `mutant_adequacy`: `accepted`
- `reviewer_signoff`: `blocked`

## Acceptance Criteria

Change your existing Gemini/Antigravity entry in `oracle/reviewer-signoffs.json` to `accept` only if all of these are true:

1. The scoring instrument no longer imports measured cohort fixtures.
2. The independent fixtures are canonical-source-derived and auditable.
3. The reference oracle passes all 29 tests.
4. All 10 mutants are killed by semantic tests.
5. Mutant evidence matches your local calibration.
6. Provenance records immutable implementation commits and no Claude-derived portions.
7. Your review did not rely on Gemini/Antigravity cohort outputs.

If any check fails, leave the decision `blocked` and name the exact artifact and failure.

## Signoff Template

Update the existing Gemini/Antigravity object in `oracle/reviewer-signoffs.json`; do not add a third reviewer.

Use `google-gemini-3.5-flash` only if that remains the actual reviewing model/tool. Otherwise use the stable reviewer identifier for the Antigravity/Gemini reviewer and disclose it in `role`.

```json
{
  "reviewer_id": "google-gemini-3.5-flash",
  "role": "independent non-Claude reviewer; Google/Gemini affiliation disclosed",
  "blinded": true,
  "evidence_reviewed": [
    "8cb986422d0e05d000666b7a90d9df28c6d8afd5",
    "b453c985",
    "canonical/spec.md",
    "canonical/pricing.proto",
    "canonical/canonicalization_decisions.md",
    "brief/source-bibliography.md",
    "brief/source-to-brief-traceability.md",
    "oracle/reference_oracle.py",
    "oracle/canonical_cases.py",
    "oracle/test_oracle.py",
    "oracle/conftest.py",
    "oracle/oracle-provenance.json",
    "oracle/fixed-open-evidence.json",
    "mutants/manifest.json",
    "mutants/src/*.py",
    "mutants/expected-kill-matrix.csv",
    "mutants/adequacy-report.json"
  ],
  "decision": "accept",
  "rationale": "Independent non-Claude re-review after fixture remediation. Verified oracle tests no longer import measured cohort fixtures; canonical_cases.py is the independent fixture source; reference oracle passes 29/29; all 10 mutants are killed under local pytest calibration; provenance records immutable remediation commit evidence and empty claude_derived_portions. Google/Gemini affiliation disclosed; review did not rely on Gemini/Antigravity cohort outputs.",
  "date": "2026-06-22"
}
```

If blinding was only partial, adjust:

```json
"blinded": false
```

and add a sentence to the rationale explaining what could not be blinded.

## After Both Reviewers Accept

Once both reviewer entries are accepting:

1. Set top-level `"status": "accepted"` in `oracle/reviewer-signoffs.json`.
2. Run:

```bash
cd docs/design/benchmark-bias-audit/bias_audit_openai
python3 ../../../../scripts/validate_cross_tool_oracle_gate.py --sync-status
```

Expected result:

- top-level gate status becomes `accepted`
- `validation_errors` becomes empty

Only after that should S4 semantic bias analysis proceed.
