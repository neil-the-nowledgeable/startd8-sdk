# Codex Reviewer Re-Review How-To

**Audience:** OpenAI Codex reviewer  
**Role:** Non-Claude readiness reviewer; OpenAI/Codex affiliation disclosed  
**Blinding:** Unblinded  
**Current gate status:** Blocked only on `reviewer_signoff`  
**Date prepared:** 2026-06-22

This is the handoff for the Codex reviewer to re-review the corrected oracle after the independent fixture remediation.

## What Changed

The prior Codex block was valid: `oracle/test_oracle.py` imported `VALID_CASES` and `INVALID_CASES` from a measured Codex cohort run under `runs/**`.

That contamination has now been removed.

Review these two remediation commits:

- `8cb986422d0e05d000666b7a90d9df28c6d8afd5` — replaces cohort-derived calibration fixtures with `oracle/canonical_cases.py`
- `b453c985` — records independent fixture provenance in `oracle/oracle-provenance.json`

The corrected fixture source is:

- `oracle/canonical_cases.py`

The corrected test module is:

- `oracle/test_oracle.py`

## Independence Rules

You may inspect the corrected oracle artifacts, canonical sources, mutant evidence, and provenance.

Do not accept if any oracle test fixture still derives from:

- `runs/**`
- a measured Codex/Codex IDE cohort artifact
- a Gemini/Antigravity cohort artifact
- a Claude-authored suite/spec/proto

Your review may be unblinded, but your signoff must disclose OpenAI/Codex affiliation.

## Files To Review

Canonical authority:

- `canonical/spec.md`
- `canonical/pricing.proto`
- `canonical/canonicalization_decisions.md`
- `brief/pricing-task-brief.md`
- `oracle/fixed-open-evidence.json`

Oracle and fixture implementation:

- `oracle/reference_oracle.py`
- `oracle/canonical_cases.py`
- `oracle/test_oracle.py`
- `oracle/conftest.py`
- `oracle/oracle-provenance.json`

Mutant evidence:

- `mutants/manifest.json`
- `mutants/src/*.py`
- `mutants/expected-kill-matrix.csv`
- `mutants/adequacy-report.json`

Gate and signoff state:

- `oracle/reviewer-signoffs.json`
- `oracle/validation-gate.json`

## Required Checks

1. Confirm `oracle/test_oracle.py` imports fixtures from `canonical_cases`, not from `runs/**`.
2. Confirm `oracle/canonical_cases.py` is hand-authored from canonical sources and does not import or copy cohort suite output.
3. Confirm `oracle/oracle-provenance.json` records the implementation commit `8cb986422d0e05d000666b7a90d9df28c6d8afd5` and has empty `claude_derived_portions`.
4. Spot-check `oracle/reference_oracle.py` against the canonical contract:
   - exact `Decimal` arithmetic, no `float` in the reference path
   - default `CASCADE`
   - default output rounding `HALF_EVEN`, scale `2`
   - `SUM` and `CASCADE` percentage behavior are distinct
   - fixed reductions apply after percentage reductions
   - fixed overrun rejects instead of clamping
   - candidate unit amount must be positive and strictly lower than `unit_amount`
   - price-on-request lines are excluded from numeric totals
5. Confirm `mutants/expected-kill-matrix.csv` and `mutants/adequacy-report.json` name the new fixture source and 2026-06-22 calibration.

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

Then run every mutant. Each mutant must fail at least one test; a passing mutant means it survived and the gate must remain blocked.

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

- No `SURVIVED` lines.
- All 10 mutants print `KILLED`.
- Failures are semantic assertion failures or expected `ValueError` misses, not import errors or harness crashes.

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

Change your existing Codex entry in `oracle/reviewer-signoffs.json` to `accept` only if all of these are true:

1. The Codex cohort fixture dependency is gone.
2. The independent fixture file is derived from canonical sources, not measured cohort output.
3. The reference oracle passes all 29 tests.
4. All 10 mutants are killed.
5. Mutant evidence files match your local calibration.
6. Provenance records immutable implementation commit evidence.
7. You can explain why the scoring instrument no longer imports OpenAI/Codex-authored calibration assumptions.

If any check fails, leave your decision as `blocked` and explain the exact artifact and failure.

## Signoff Template

Update the existing `openai-codex-gpt-5` object in `oracle/reviewer-signoffs.json`; do not add a third reviewer.

```json
{
  "reviewer_id": "openai-codex-gpt-5",
  "role": "non-Claude readiness reviewer; OpenAI/Codex affiliation disclosed",
  "blinded": false,
  "evidence_reviewed": [
    "8cb986422d0e05d000666b7a90d9df28c6d8afd5",
    "b453c985",
    "canonical/spec.md",
    "canonical/pricing.proto",
    "canonical/canonicalization_decisions.md",
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
  "rationale": "Re-reviewed corrected oracle after independent fixture remediation. Verified test_oracle.py no longer imports measured Codex cohort fixtures; canonical_cases.py is the fixture source; reference oracle passes 29/29; all 10 mutants are killed under local pytest calibration; provenance records the remediation commit and empty claude_derived_portions. OpenAI/Codex affiliation disclosed.",
  "date": "2026-06-22"
}
```

Leave top-level `"status": "pending"` until the Antigravity/Gemini reviewer also accepts. If both reviewer entries are accepting when you update the file, set top-level `"status": "accepted"` and rerun the validator with `--sync-status`.
