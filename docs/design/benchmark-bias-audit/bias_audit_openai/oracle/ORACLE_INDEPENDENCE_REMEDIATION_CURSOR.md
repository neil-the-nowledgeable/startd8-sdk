# Oracle Independence Remediation — Cursor Run-Book

**Tool:** Cursor Composer (e.g. Composer 2.5)
**Role:** Independent, **non-measured** oracle implementer
**Status of gate this unblocks:** `oracle/validation-gate.json` → currently `blocked`
**Owner:** neil-the-nowledgeable
**Date issued:** 2026-06-22

---

## 0. Why you (Cursor) and not Codex / Gemini / Claude

This audit measures whether benchmark **inputs** authored with Claude Code, **OpenAI Codex**, and
**Google Gemini / Antigravity** are biased toward their own vendor's models. The oracle is the
**scoring instrument** that decides what "correct" means.

> **Hard rule:** the scoring instrument may **not** be authored from, or depend on, any artifact
> produced by a *measured* tool (Claude, Codex, Gemini, Antigravity). If it did, the instrument
> would inherit the very bias the audit is trying to detect.

Cursor Composer is **not** one of the measured authoring surfaces, so you are the legitimate
implementer. **Do not** copy, import, or paraphrase content from:

- `runs/**` (any cohort authoring run — these are the *subjects* of the audit)
- any Claude-, Codex-, Gemini-, or Antigravity-authored suite/spec/proto

You may derive **only** from the canonical, neutral sources in §2.

---

## 1. The defect to fix (verified on disk)

`oracle/test_oracle.py` builds its truth table by importing a **measured Codex cohort artifact**:

```python
# oracle/test_oracle.py  (lines 14–29 — REMOVE THIS)
AUDIT_ROOT = Path(__file__).resolve().parents[1]
SUITE_PATH = (
    AUDIT_ROOT
    / "runs/s2-codex-suite-clean-20260618T215301Z/suite.py"   # <-- Codex cohort output
)

def _load_suite_cases():
    spec = importlib.util.spec_from_file_location("codex_suite", SUITE_PATH)
    ...
    return module.VALID_CASES, module.INVALID_CASES

VALID_CASES, INVALID_CASES = _load_suite_cases()
```

Because `VALID_CASES` / `INVALID_CASES` (the expected responses the oracle and every mutant are
graded against) come from a Codex run, the oracle's calibration is **vendor-dependent**. Both the
Codex and Gemini reviewers correctly **blocked** the gate on this.

Secondary defects to close in the same change:
- `oracle/oracle-provenance.json` → `authorship[0].commits` is `[]` and
  `independent_non_claude_review` is `[]`. Provenance is unfinished.

---

## 2. Canonical sources you MAY derive from (and nothing else)

All under `docs/design/benchmark-bias-audit/bias_audit_openai/`:

| File | Use |
|---|---|
| `canonical/spec.md` | Behavioral specification — the authority for FIXED/OPEN behavior |
| `canonical/pricing.proto` | Contract field names & message shapes (`Amount{decimal}`, totals, lines) |
| `canonical/canonicalization_decisions.md` | Resolved decisions for every adjudicated-OPEN dimension |
| `brief/pricing-task-brief.md` | Neutral task brief |
| `brief/source-bibliography.md`, `brief/source-to-brief-traceability.*` | Source grounding (Liferay-derived) |
| `oracle/fixed-open-evidence.json` | FIXED/OPEN item IDs each probe must map to |

The reference implementation already exists and is **not** the problem:
`oracle/reference_oracle.py` (authored by Cursor Composer 2.5 — keep it). Only the **fixtures**
feeding `test_oracle.py` are contaminated.

---

## 3. Deliverables

### D1 — Independent canonical fixtures
Create **`oracle/canonical_cases.py`** containing `VALID_CASES` and `INVALID_CASES`, authored from
§2 only. Match the existing case schema (so the rest of `test_oracle.py` needs no rewrite):

```python
VALID_CASES = [
    {
        "name": "default_cascade_selects_lower_positive_candidate",
        "behavior_ids": ["B_PROMOTION_SELECTION", "B_DEFAULTS", "B_CASCADE_PERCENT", "B_TOTALS"],
        "request": { ... },            # RPC-shaped dict, proto field names
        "expected_response": { ... },  # canonical expected output
    },
    ...
]
INVALID_CASES = [
    {"name": "rejects_fixed_reduction_overrun_after_percent", "request": { ... }},
    {"name": "rejects_empty_lines", "request": { ... }},
    ...
]
```

**Coverage requirement — every `name` referenced in `test_oracle.py` must exist**, because the
named probes (FIXED-001/008, OPEN-001..012) look cases up by `name`. At minimum:

- `default_cascade_selects_lower_positive_candidate`
- `half_even_is_default_rounding_mode`
- `sum_strategy_adds_percent_levels_once`
- `candidate_must_be_positive_and_lower_than_unit`
- `fixed_reductions_apply_after_all_percent_reductions`
- `exact_intermediate_arithmetic_precedes_output_quantization`
- `price_on_request_lines_are_excluded_from_numeric_totals`
- INVALID: `rejects_fixed_reduction_overrun_after_percent`, `rejects_empty_lines`

Derive each `expected_response` **by hand from `canonical/spec.md` + `canonicalization_decisions.md`**,
NOT by running `reference_oracle.py` and copying its output (that would make the test tautological).
The reference oracle and the fixtures must be **two independent derivations of the spec** that agree.

### D2 — Rewire the test module
In `oracle/test_oracle.py`, delete lines 14–29 (the `SUITE_PATH` / `_load_suite_cases()` block) and
replace with:

```python
from canonical_cases import VALID_CASES, INVALID_CASES
```

Leave every `def test_*` body unchanged. Remove now-unused imports (`importlib.util`, `sys`, the
`AUDIT_ROOT` constant if unreferenced).

### D3 — Re-calibrate oracle + 10 mutants
The conftest swaps the implementation-under-test via `--oracle-module`. Run from the `oracle/` dir.

```bash
cd docs/design/benchmark-bias-audit/bias_audit_openai/oracle

# (a) Oracle must PASS all probes against the new independent fixtures
pytest test_oracle.py --oracle-module reference_oracle -q     # expect: all green

# (b) Each mutant must be KILLED = test_oracle.py must FAIL for it
for m in mutant_round_half_up mutant_round_down mutant_sum_for_cascade \
         mutant_cascade_for_sum mutant_fixed_before_percent mutant_candidate_any_positive \
         mutant_por_total mutant_float_arithmetic mutant_round_intermediate mutant_clamp_overrun; do
  echo "=== $m ==="
  pytest test_oracle.py --oracle-module "$m" -q && echo "!!! SURVIVED (not killed): $m"
done
# Desired: every mutant produces at least one FAILING test (a kill). Any "SURVIVED" line is a
# calibration gap — add/strengthen a probe in canonical_cases.py until that mutant is killed.
```

Then refresh the evidence files to reflect the **new** fixtures:
- `mutants/expected-kill-matrix.csv` — keep header + one row per mutant; `validated=true` only for
  mutants actually killed under the new fixtures; record which named probe kills each.
- `mutants/adequacy-report.json` — update calibration runs/coverage so every material OPEN
  dimension still has a discriminating single-fault mutant.
- Keep `mutants/manifest.json` `status: "accepted"` only if all 10 are killed; otherwise set the
  honest status and list the gap.

### D4 — Complete provenance
In `oracle/oracle-provenance.json`:
- Set `authorship[0].commits` to the **actual commit hash(es)** of this change.
- Confirm `claude_derived_portions` is `[]` and remains true (fixtures are spec-derived, not
  Claude-derived).
- Leave `independent_non_claude_review` as `[]` **for now** — that record is filled by the Codex /
  Antigravity reviewers in a later step, **not by you** (see §5).

---

## 4. Definition of Done

1. `grep -rn "runs/s2-codex" oracle/` returns **nothing** — the cohort dependency is gone.
2. `cd oracle && pytest test_oracle.py --oracle-module reference_oracle -q` → **all pass**.
3. All 10 mutants are **killed** (each produces ≥1 failing test); `expected-kill-matrix.csv` reflects
   reality and has >1 line.
4. `oracle-provenance.json` has a real implementation commit; no measured-cohort content was used.
5. Gate recompute runs clean except for the (expected) pending reviewer sign-offs:

```bash
cd docs/design/benchmark-bias-audit/bias_audit_openai
python3 ../../../../scripts/validate_cross_tool_oracle_gate.py --sync-status
# Expect: oracle_provenance / evidence_mapping / mutant_adequacy = accepted;
#         reviewer_signoff still blocked (that is the NEXT step, owned by Codex + Antigravity).
```

Commit on a branch (this repo is **branch-first** — never commit to `main` directly). Suggested:
`git checkout -b audit/oracle-independence` then commit the fixture file, the test rewrite, the
refreshed mutant evidence, and the provenance update together.

---

## 5. Explicitly OUT of scope for Cursor

- **Do not** edit `oracle/reviewer-signoffs.json` or flip `validation-gate.json` to `accepted`.
  Two independent **non-Claude** reviewers (Codex IDE + Antigravity/Gemini, each disclosed and
  reviewing artifacts outside their own cohort) must re-sign against the corrected SHAs. That is a
  separate run-book.
- **Do not** author authoring samples (suite/spec/proto) — those come from the measured tools.
- **Do not** run the S4 analysis (`scripts/run_cross_tool_bias_s4.py`) — it stays fail-closed until
  the gate is genuinely `accepted`.

---

## 6. One-paragraph brief to paste into Cursor

> You are the independent, non-measured implementer for a vendor-bias audit. The pricing oracle's
> test fixtures are currently imported from a measured OpenAI-Codex run
> (`oracle/test_oracle.py` lines 14–29 load `runs/s2-codex-suite-clean-.../suite.py`), which
> contaminates the scoring instrument. Replace those fixtures with `oracle/canonical_cases.py`
> derived **only** from `canonical/spec.md`, `canonical/pricing.proto`,
> `canonical/canonicalization_decisions.md`, and `brief/`. Do not copy from any file under `runs/`,
> and do not copy the reference oracle's runtime output. Rewire `test_oracle.py` to import from the
> new module, keep all `test_*` bodies, re-run the oracle (must pass) and all 10 mutants via
> `pytest test_oracle.py --oracle-module <module>` (each mutant must fail = be killed), refresh
> `mutants/expected-kill-matrix.csv` + `mutants/adequacy-report.json`, and record the real
> implementation commit in `oracle/oracle-provenance.json`. Work on a branch; do not touch
> `reviewer-signoffs.json` or `validation-gate.json`.
