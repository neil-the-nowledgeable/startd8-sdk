# Gemini Reviewer Re-Review How-To

**Reviewer:** Gemini, with Google/Gemini affiliation disclosed.  
**Scope:** Oracle-instrument admission only; do not assess generated author-vendor artifacts.  
**Current state:** Codex accepted the corrected instrument. Gemini is the remaining signoff gate.

## Review baseline

Review these commits in order:

- `8cb986422d0e05d000666b7a90d9df28c6d8afd5` — independent canonical fixture remediation.
- `b453c985aa0ed361cc23448897795dceb107d93a` — fixture provenance.
- `f81d23cb` — Codex acceptance; verify independently rather than relying on it.

The fixture authority is `oracle/canonical_cases.py`. Reject if calibration data or expected responses
derive from `runs/**`, or from a measured Codex, Gemini, or Claude cohort artifact.

Review `canonical/spec.md`, `canonical/pricing.proto`, `canonical/canonicalization_decisions.md`,
`oracle/reference_oracle.py`, `oracle/canonical_cases.py`, `oracle/test_oracle.py`,
`oracle/oracle-provenance.json`, `oracle/fixed-open-evidence.json`, `mutants/manifest.json`,
`mutants/src/*.py`, `mutants/expected-kill-matrix.csv`, and `mutants/adequacy-report.json`.

## Required checks

1. `test_oracle.py` imports from `canonical_cases`, not `runs/**`.
2. `canonical_cases.py` is canonical-source-derived and not cohort output.
3. Provenance records `8cb986422d0e05d000666b7a90d9df28c6d8afd5`; every
   `claude_derived_portions` entry is empty.
4. The reference behavior uses exact `Decimal`, defaults to CASCADE, HALF_EVEN, and scale 2; SUM is
   distinct; fixed reductions follow percentages; overrun rejects; candidate is positive and strictly
   lower; and price-on-request lines are excluded from numeric totals.
5. The kill matrix and adequacy report name `oracle/canonical_cases.py` and `2026-06-22`.

## Required calibration

From `docs/design/benchmark-bias-audit/bias_audit_openai/oracle`:

```bash
pytest test_oracle.py --oracle-module reference_oracle -q
```

Expected: `29 passed`.

```bash
for m in mutant_round_half_up mutant_round_down mutant_sum_for_cascade \
         mutant_cascade_for_sum mutant_fixed_before_percent mutant_candidate_any_positive \
         mutant_por_total mutant_float_arithmetic mutant_round_intermediate mutant_clamp_overrun; do
  pytest test_oracle.py --oracle-module "$m" -q --tb=no && echo "SURVIVED: $m" || echo "KILLED: $m"
done
```

All ten mutants must be killed by semantic test failures or expected validation mismatches. Import,
collection, or harness failures are not kills. Before editing the signoff, confirm the derived gate is
blocked only on the Gemini review:

```bash
cd ../../../../..
python3 scripts/validate_cross_tool_oracle_gate.py
```

## Signoff

Update the existing `google-gemini-3.5-flash` object in `oracle/reviewer-signoffs.json`; do not add a
third reviewer. Record `decision: "accept"` only if every check passes and include these evidence items:

```json
[
  "8cb986422d0e05d000666b7a90d9df28c6d8afd5",
  "b453c985aa0ed361cc23448897795dceb107d93a",
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
]
```

The rationale must state: cohort-independent fixtures, 29/29 reference tests, ten semantic mutant
kills, empty Claude-derived portions, and disclosed Google/Gemini affiliation. Use `2026-06-22` for
this calibration or the actual rerun date.

If every reviewer entry accepts, set the top-level signoff status to `accepted` and run:

```bash
python3 scripts/validate_cross_tool_oracle_gate.py --sync-status
```

The gate is accepted only when that command reports no errors. That admits the oracle instrument, not
unpromoted authoring artifacts or S4 execution without its separate isolation bridge.
