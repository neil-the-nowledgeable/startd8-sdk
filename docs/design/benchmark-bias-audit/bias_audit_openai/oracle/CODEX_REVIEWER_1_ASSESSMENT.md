# Reviewer 1 Assessment — Codex (OpenAI)

**Date:** 2026-06-26
**Decision:** ACCEPT
**Scope:** Phase 3 oracle and mutant admission readiness
**Reviewer:** Codex (OpenAI), affiliation disclosed

## Reviewer identity and limitation

This assessment was performed by Codex (OpenAI), acting as a non-Claude
reviewer at the user's direction. Codex is OpenAI-affiliated and unblinded, so
this assessment is sufficient only as one disclosed non-Claude review. The
second non-Claude review is recorded separately in `reviewer-signoffs.json`.

This is an admission assessment for the oracle and mutant battery only. It is
not a review of model-generated suites, author-vendor outputs, raw cohort
artifacts, or a semantic bias verdict.

## Current gate state

This file supersedes the earlier blocked readiness note. The evidence artifacts
now record accepted oracle provenance, accepted FIXED/OPEN evidence mapping,
accepted reviewer signoffs, and accepted mutant adequacy.

Current validation from a fresh branch based on `origin/main`:

```bash
python3 scripts/validate_cross_tool_oracle_gate.py
```

Result: accepted, with no validation errors.

```bash
PYTHONDONTWRITEBYTECODE=1 pytest -q -p no:cacheprovider \
  docs/design/benchmark-bias-audit/bias_audit_openai/oracle/test_oracle.py
```

Result: 38 oracle tests passed.

## Materials reviewed

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

## Findings

| Area | Result | Evidence |
|---|---|---|
| Canonical contract | Accepted | The specification and proto define the pricing semantics used by the oracle fixture cases. |
| Fixture independence | Accepted | `test_oracle.py` imports `VALID_CASES` and `INVALID_CASES` from `oracle/canonical_cases.py`, not from measured cohort outputs. |
| Oracle validation | Accepted | Current reference oracle test run collected 38 tests and passed all 38. |
| Mutant adequacy | Accepted | `mutants/manifest.json`, `mutants/expected-kill-matrix.csv`, and `mutants/adequacy-report.json` record ten validated semantic mutants, all expected to be killed against the independent fixture suite. |
| Reviewer evidence | Accepted | `reviewer-signoffs.json` contains accepting OpenAI/Codex and Google/Gemini non-Claude reviews; `validation-gate.json` is accepted. |

## Decision rationale

The oracle instrument is admissible for the next audit stage because the
current gate validates as accepted, the oracle suite passes, fixtures are
derived from canonical sources rather than cohort outputs, and the mutant
battery is recorded as calibrated against the same independent fixture source.

This acceptance admits the oracle and mutant instrument only. It does not admit
unpromoted authoring artifacts, does not bypass reconciliation/intake controls,
and does not authorize executing generated suites outside the separate isolated
S4 bridge.

## Next required controls

1. Preserve the accepted oracle gate without hand-editing derived status.
2. Promote only reconciled and intake-admitted authoring artifacts.
3. Execute S4 only through the fail-closed isolated no-egress bridge described
   in the S4 plan.
