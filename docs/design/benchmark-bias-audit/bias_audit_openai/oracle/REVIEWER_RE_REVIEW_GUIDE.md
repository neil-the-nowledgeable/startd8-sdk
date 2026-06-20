# Re-Review Guide — Codex and Gemini Reviewers

**Date:** 2026-06-20  
**Status:** Ready for re-review  
**Audience:** Codex (Reviewer 1) and Gemini (Reviewer 2)  
**Prerequisite:** Both reviewers previously recorded `blocked` sign-offs on 2026-06-20. Executable evidence now exists.

This document tells each reviewer exactly what changed, what to verify, and how to record an updated sign-off in `oracle/reviewer-signoffs.json`.

---

## What changed since the blocked reviews

An independent non-Claude implementer (**Cursor Composer**, `cursor-composer-2.5`) completed Deliverables 1–4 from `NON_CLAUDE_IMPLEMENTER_GUIDE.md`:

| Artifact | Previous state | Current state |
|---|---|---|
| `oracle/reference_oracle.py` | Missing | **Created** — `assess_lines()` pure-function oracle |
| `oracle/test_oracle.py` | Missing | **Created** — 43 tests + FIXED/OPEN probes |
| `oracle/conftest.py` | Missing | **Created** — `--oracle-module` mutant swap |
| `oracle/oracle-provenance.json` | `pending`, null oracle | `accepted`, authorship recorded |
| `oracle/fixed-open-evidence.json` | `pending`, 0 mappings | `accepted`, **22 mappings** |
| `mutants/manifest.json` | `planned` | `accepted`, source paths added |
| `mutants/src/*.py` | Missing | **10 executable single-fault mutants** |
| `mutants/expected-kill-matrix.csv` | Header only | **10 validated kill rows** |
| `mutants/adequacy-report.json` | `pending` | `accepted`, calibration runs recorded |
| `oracle/reviewer-signoffs.json` | 2 blocked | **Still pending** — awaiting your re-review |

**Gate status today:** 3 of 4 checks pass. Only `reviewer_signoff` remains blocked.

```bash
python3 scripts/validate_cross_tool_oracle_gate.py
# oracle_provenance: accepted
# evidence_mapping: accepted
# reviewer_signoff: blocked
# mutant_adequacy: accepted
```

---

## Reviewer roles

| Reviewer | Affiliation | Blinding | Role |
|---|---|---|---|
| **Codex** | OpenAI / codex-cli cohort | Unblinded | Reviewer 1 — readiness and semantic spot-checks |
| **Gemini** | Google / gemini-cli cohort | Blinded where practical | Reviewer 2 — independent admission control |

Both reviewers are affiliated with tool cohorts under evaluation. Neither affiliation disqualifies review, but both must disclose it in the sign-off. Gemini should request a blinded packet from the audit operator when reviewing generated outputs (see `SECOND_NON_CLAUDE_REVIEWER_HOWTO.md`).

**Do not** accept based on artifact shape alone. Run the verification commands below and confirm results match the recorded kill matrix.

---

## Review sequence

### Step 1 — Canonical contract (unchanged)

Confirm the oracle implements these sources of truth:

- `canonical/spec.md`
- `canonical/pricing.proto`
- `canonical/canonicalization_decisions.md`

### Step 2 — Oracle provenance

Read `oracle/oracle-provenance.json`. Verify:

- [ ] `status` is `accepted`
- [ ] `oracle` points to `oracle/reference_oracle.py`
- [ ] `authorship` identifies implementer, tool assistance, and `claude_derived_portions` (must be empty or fully disclosed)
- [ ] Implementer is not Claude-derived without independent reimplementation

Read `oracle/reference_oracle.py`. Spot-check these behaviors against the spec:

- [ ] Uses `decimal.Decimal` — no `float` in the reference path
- [ ] CASCADE default when `discount_strategy` omitted
- [ ] SUM aggregates percent levels once; CASCADE applies sequentially
- [ ] Fixed reductions after percentages; overrun rejects (no clamp)
- [ ] Candidate used only when present, > 0, and < `unit_amount`
- [ ] Price-on-request lines excluded from numeric totals
- [ ] Output-only rounding (default scale 2, HALF_EVEN)
- [ ] Validation raises `ValueError` for invalid inputs

### Step 3 — FIXED/OPEN evidence mappings

Read `oracle/fixed-open-evidence.json`. Verify:

- [ ] `status` is `accepted`
- [ ] **22 mappings** present (FIXED-001..010 + OPEN-001..012)
- [ ] Each mapping has `source_evidence`, `targeted_probe`, and `expected_behavior`
- [ ] Every `targeted_probe` names a test function in `oracle/test_oracle.py`

Cross-reference `brief/source-to-brief-traceability.md` if a mapping's source citation looks weak.

### Step 4 — Mutant battery

Read `mutants/manifest.json` and inspect each file under `mutants/src/`. Verify:

- [ ] `status` is `accepted`
- [ ] Each mutant changes **exactly one** module-level flag or behavior
- [ ] No mutant is a harness crash, syntax error, or broad rewrite
- [ ] Each mutant imports `reference_oracle` and overrides one mutation hook

| Mutant ID | Source file | Single fault |
|---|---|---|
| `round-half-up-for-half-even` | `mutant_round_half_up.py` | `DEFAULT_ROUNDING_MODE = ROUND_HALF_UP` |
| `round-down-for-half-even` | `mutant_round_down.py` | `DEFAULT_ROUNDING_MODE = ROUND_DOWN` |
| `sum-for-cascade` | `mutant_sum_for_cascade.py` | `FORCE_SUM_FOR_CASCADE = True` |
| `cascade-for-sum` | `mutant_cascade_for_sum.py` | `FORCE_CASCADE_FOR_SUM = True` |
| `fixed-before-percent` | `mutant_fixed_before_percent.py` | `APPLY_FIXED_BEFORE_PERCENT = True` |
| `candidate-any-positive` | `mutant_candidate_any_positive.py` | `CANDIDATE_REQUIRES_STRICTLY_LOWER = False` |
| `float-arithmetic` | `mutant_float_arithmetic.py` | `USE_FLOAT_ARITHMETIC = True` |
| `round-intermediate` | `mutant_round_intermediate.py` | `ROUND_INTERMEDIATE = True` |
| `clamp-fixed-overrun` | `mutant_clamp_overrun.py` | `CLAMP_FIXED_OVERRUN = True` |
| `price-on-request-total` | `mutant_por_total.py` | `INCLUDE_POR_IN_TOTALS = True` |

### Step 5 — Run verification (required)

From the repository root:

```bash
# 1. Reference oracle must pass all tests
pytest docs/design/benchmark-bias-audit/bias_audit_openai/oracle/test_oracle.py -q

# 2. Each mutant must fail (kill) — example for one mutant
pytest docs/design/benchmark-bias-audit/bias_audit_openai/oracle/test_oracle.py \
  --oracle-module=mutant_round_half_up -q

# 3. Re-run all mutants (copy/paste)
for m in mutant_round_half_up mutant_round_down mutant_sum_for_cascade \
         mutant_cascade_for_sum mutant_fixed_before_percent mutant_candidate_any_positive \
         mutant_float_arithmetic mutant_round_intermediate mutant_clamp_overrun mutant_por_total; do
  pytest docs/design/benchmark-bias-audit/bias_audit_openai/oracle/test_oracle.py \
    --oracle-module="$m" -q --tb=no || echo "KILL: $m"
done
```

**Expected results:**

- Reference oracle: **43 passed**, 0 failed
- Every mutant: **≥1 test failure** (kill), not a harness crash

Compare your results to `mutants/expected-kill-matrix.csv` and `mutants/adequacy-report.json`. If any mutant survives (all tests pass) or crashes on import, record `blocked` and cite the mutant ID.

### Step 6 — Coverage adequacy

Read `mutants/adequacy-report.json`. Verify high-risk dimensions:

| Dimension | Required | Recorded |
|---|---|---|
| Rounding | ≥2 mutants | 2 (`round-half-up-for-half-even`, `round-down-for-half-even`) |
| Ordering | ≥1 mutant | 1 (`fixed-before-percent`) |
| Cap / fixed-overrun | ≥1 mutant | 1 (`clamp-fixed-overrun`) |
| Decimal precision | ≥2 mutants | 2 (`float-arithmetic`, `round-intermediate`) |
| Error behavior | ≥1 mutant | 1 (`clamp-fixed-overrun`) |

Note: ordering and error behavior each have only one dedicated mutant. Accept only if you agree the recorded mutants are material and discriminating on targeted probes.

### Step 7 — Vendor-neutrality check

Answer for your sign-off rationale:

- Does the oracle import assumptions from any single tool vendor's suite or spec wording?
- Are FIXED/OPEN resolutions traceable to Liferay source or canonical contract — not to one vendor's generated artifacts?
- Would a different non-Claude implementer likely reach the same semantics from the canonical contract alone?

---

## Acceptance criteria

Record `"decision": "accept"` only when **all** of the following hold:

1. Reference oracle exists, is independently authored, and provenance is complete.
2. All 22 FIXED/OPEN mappings have source evidence and executable probes.
3. All 10 mutants are executable, single-fault, and kill the test suite.
4. Kill matrix and adequacy report match your independent calibration run.
5. No harness failure is counted as a kill.
6. You can explain why the oracle does not encode author-vendor assumptions.

Otherwise record `"decision": "blocked"` or `"reject"` with exact missing evidence. Leave `reviewer-signoffs.json` top-level `status` as `pending` until both reviewers accept.

---

## Recording your sign-off

Update your existing entry in `oracle/reviewer-signoffs.json` (do not add a third reviewer). Change `decision`, `rationale`, `date`, and `evidence_reviewed` to reflect this re-review.

### Codex template (Reviewer 1, unblinded)

```json
{
  "reviewer_id": "openai-codex-gpt-5",
  "role": "non-Claude readiness reviewer; OpenAI/Codex affiliation disclosed",
  "blinded": false,
  "evidence_reviewed": [
    "canonical/spec.md",
    "canonical/pricing.proto",
    "canonical/canonicalization_decisions.md",
    "oracle/reference_oracle.py",
    "oracle/test_oracle.py",
    "oracle/oracle-provenance.json",
    "oracle/fixed-open-evidence.json",
    "mutants/manifest.json",
    "mutants/src/*.py",
    "mutants/expected-kill-matrix.csv",
    "mutants/adequacy-report.json"
  ],
  "decision": "accept",
  "rationale": "Re-reviewed executable oracle, 22 evidence mappings, and 10 calibrated mutants. Independent pytest run: reference oracle 43/43 pass; all mutants kill on targeted probes. Provenance identifies non-Claude implementer with empty claude_derived_portions. Oracle semantics match canonical contract without vendor-specific assumptions.",
  "date": "YYYY-MM-DD"
}
```

### Gemini template (Reviewer 2, blinded where practical)

```json
{
  "reviewer_id": "google-gemini-3.5-flash",
  "role": "independent non-Claude reviewer; Google/Gemini affiliation disclosed",
  "blinded": true,
  "evidence_reviewed": [
    "canonical/spec.md",
    "canonical/pricing.proto",
    "canonical/canonicalization_decisions.md",
    "oracle/reference_oracle.py",
    "oracle/test_oracle.py",
    "oracle/oracle-provenance.json",
    "oracle/fixed-open-evidence.json",
    "mutants/manifest.json",
    "mutants/expected-kill-matrix.csv",
    "mutants/adequacy-report.json"
  ],
  "decision": "accept",
  "rationale": "Independent re-review of executable evidence. Verified provenance, 22 FIXED/OPEN probes, and mutant kill matrix via local pytest calibration. All 10 mutants discriminate on material faults. Oracle derives from canonical contract and Liferay traceability, not from any single vendor suite.",
  "date": "YYYY-MM-DD"
}
```

After **both** reviewers record `accept`:

1. Set top-level `"status": "accepted"` in `reviewer-signoffs.json`.
2. Run the gate validator:

```bash
python3 scripts/validate_cross_tool_oracle_gate.py
python3 scripts/validate_cross_tool_oracle_gate.py --sync-status
```

The validator must report `"status": "accepted"` with zero errors. Do **not** hand-edit `validation-gate.json`.

---

## Quick file checklist

| File | Verify |
|---|---|
| `oracle/reference_oracle.py` | Correct `assess_lines` semantics |
| `oracle/test_oracle.py` | 43 tests; probes match evidence mappings |
| `oracle/conftest.py` | `--oracle-module` loads mutants |
| `oracle/oracle-provenance.json` | `accepted`, authorship complete |
| `oracle/fixed-open-evidence.json` | `accepted`, 22 mappings |
| `mutants/manifest.json` | `accepted`, 10 mutants with `source` |
| `mutants/src/mutant_*.py` | 10 files, one fault each |
| `mutants/expected-kill-matrix.csv` | 10 rows, `validated=true` |
| `mutants/adequacy-report.json` | `accepted`, calibration_runs populated |
| `oracle/reviewer-signoffs.json` | **Your update** — 2 accepting sign-offs |

---

## Related documents

- `NON_CLAUDE_IMPLEMENTER_GUIDE.md` — what the implementer built
- `SECOND_NON_CLAUDE_REVIEWER_HOWTO.md` — general second-reviewer procedure
- `CODEX_REVIEWER_1_ASSESSMENT.md` — Codex's prior blocked assessment (2026-06-20)
- `PHASE3_READINESS.md` — phase context and gate derivation

---

## Anti-patterns (do not accept if observed)

- Oracle uses `float` for arithmetic in the reference path
- Mutant kills due to import error or syntax error (harness failure)
- Equivalent mutant counted as a kill (mutant passes all tests)
- Evidence mapping probe name does not exist in `test_oracle.py`
- `claude_derived_portions` non-empty without independent re-review
- Hand-edited `validation-gate.json` instead of `--sync-status`
