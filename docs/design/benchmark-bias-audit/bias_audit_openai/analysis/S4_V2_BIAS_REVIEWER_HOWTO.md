# S4 v2 Bias Reviewer How-To

Date: 2026-07-05
Batch: `pricing-cross-tool-authoring-v2-evidence-1200s`

Use this guide to review the S4 v2 evidence from the perspective of identifying
evidence of benchmark bias first, then deciding whether that evidence has been
explained, mitigated, or remains unresolved.

The review is not an inquiry into author intent. The benchmark goal is neutral
evaluation for R&D and academic understanding. The question is whether accidental
vendor-favoring assumptions appear in the benchmark, prompts, oracle, bridge, or
analysis process.

## Review objective

Primary objective:

Identify evidence that the benchmark or audit process favors or disadvantages
Claude Code, Codex/OpenAI, Gemini/Google, or any vendor-specific authoring style.

Secondary objective:

Determine whether each identified bias signal has been:

- explained by non-benchmark causes,
- mitigated by a neutral mechanical fix,
- accepted as a reviewed limitation, or
- left unresolved.

Do not require proof that all possible bias has been eliminated. That is a much
higher bar than this evidence review. The correct standard is: actively seek
bias evidence, classify it rigorously, and avoid overstating the conclusion.

## Materials to review

Read these first:

- `analysis/S4_V2_EVIDENCE_1200S_BIAS_ANALYSIS.md`
- `analysis/S4_V2_REFERENCE_ORACLE_FAILURE_DISPOSITION.md`
- `analysis/s4-suite-dispositions-v2-evidence-1200s.json`
- `analysis/s4-pre-registration-v2-evidence-1200s.json`
- `analysis/s4-bridge-manifest.json`

Optional supporting artifacts:

- `.startd8/bias-audit-store/pricing-cross-tool-authoring-v2-evidence-1200s/reconciliation-report.json`
- `.startd8/bias-audit-store/pricing-cross-tool-authoring-v2-evidence-1200s/intake-ledger.json`
- `/private/tmp/startd8-cross-tool-bias/pricing-cross-tool-authoring-v2-evidence-1200s/s4-results-flattened-seam/s4-preflight.json`
- `/private/tmp/startd8-cross-tool-bias/pricing-cross-tool-authoring-v2-evidence-1200s/s4-results-flattened-seam/mutant_kill_matrix.csv`

## Expected terminal evidence

The terminal S4 result should show:

- S4 status: `complete`
- S4 errors: `[]`
- reference pass: 13
- reviewed exclusions: 2
- reference failures: 0

Final reference status by vendor:

| Vendor | Pass | Excluded | Fail |
|---|---:|---:|---:|
| Anthropic / Claude Code | 5/5 | 0/5 | 0/5 |
| Google / Gemini | 4/5 | 1/5 | 0/5 |
| OpenAI / Codex | 4/5 | 1/5 | 0/5 |

If your local evidence differs, stop and resolve the artifact mismatch before
making a bias finding.

## Bias-first review procedure

### 1. Start with candidate bias signals

Do not start from the final “complete” result. Start by identifying the strongest
signals that could indicate bias:

1. Initial S4 showed 9 reference-oracle failures.
2. Initial S4 appeared to show OpenAI/Codex at 0/5 reference-passing suites.
3. Anthropic ultimately has 5/5 reference-passing suites while OpenAI and Google
   each have one reviewed exclusion.
4. The bridge required multiple mechanical adaptations to execute the v2 suites.
5. Some mutant classes remain weakly detected.

For each signal, decide whether it is durable bias evidence or whether the
disposition evidence adequately explains it.

### 2. Review the initial OpenAI/Codex 0/5 signal

Question:

Was the initial OpenAI/Codex 0/5 reference-admission result evidence of
benchmark bias?

Required checks:

- Confirm the initial result existed and was treated as a serious candidate
  signal.
- Review why 6 of the 9 original failures were classified as bridge-harness
  artifacts.
- Confirm the `run_all` harness correction is mechanical and not vendor-specific.
- Confirm OpenAI/Codex rows pass after the corrected callable seam.

Reviewer finding options:

- `explained`: the 0/5 signal was bridge-harness caused, not durable benchmark
  bias evidence.
- `partially_unresolved`: the harness correction may have over-normalized vendor
  differences.
- `bias_evidence`: the original signal remains credible despite the correction.

### 3. Review bridge neutrality

Question:

Did the bridge changes neutrally support declared suite contracts, or did they
preferentially rescue one vendor?

Required checks:

- v2 callable alias support must only admit declared bridge contract shapes.
- The `run_all` correction must use the callable/bound-invoker seam rather than
  a vendor-specific path.
- Flattened decimal-string support must only activate when the admitted
  `bridge_contract` declares that seam.
- Short enum alias normalization must map aliases to canonical enum names without
  changing benchmark semantics.
- Dict-shaped `{"decimal": "..."}` suites must remain supported.

Reviewer finding options:

- `neutral_mechanical_support`
- `acceptable_with_caveat`
- `potential_bridge_bias`
- `reject`

### 4. Review the two exclusions

Question:

Are the exclusions fair evidence handling, or do they hide benchmark bias?

Excluded rows:

- OpenAI/Codex run 05:
  `suite_over_specifies_canonical_output_shape`
- Google/Gemini run 12:
  `suite_over_specifies_canonical_output_shape`

Required checks:

- Confirm no generated suite was repaired.
- Confirm exclusions are sha-pinned in
  `analysis/s4-suite-dispositions-v2-evidence-1200s.json`.
- Confirm run 05 really expects price-on-request numeric-line details that the
  reviewed canonical oracle does not require.
- Confirm run 12 really folds fixed reductions into `percent_total`, contrary to
  the reviewed canonical reduction summary semantics.
- Ask whether prompt/spec wording made these mistakes more likely for non-Claude
  tools.

Reviewer finding options:

- `valid_exclusions_no_bias_evidence`
- `valid_exclusions_with_prompt_ambiguity`
- `potential_non_claude_disadvantage`
- `reject_exclusions`

### 5. Review final reference admission

Question:

Does final reference admission show evidence of Claude Code favoritism?

Facts to verify:

- Anthropic: 5/5 pass.
- Google: 4/5 pass, 1/5 excluded.
- OpenAI: 4/5 pass, 1/5 excluded.
- Reference failures: 0.

Interpretation guidance:

- This does not show a Claude-only execution path.
- The Anthropic 5/5 versus OpenAI/Google 4/5 asymmetry is a residual signal to
  disclose, not ignore.
- Because the two exclusions are OpenAI and Google, reviewers should explicitly
  decide whether that asymmetry reflects neutral suite-quality disposition or
  benchmark wording that disadvantaged non-Claude authors.

### 6. Review mutant adequacy

Question:

Is the benchmark strong enough to reveal vendor differences, or could weak
mutants hide bias?

Known weaker detection areas:

- `float-arithmetic`
- `round-intermediate`
- `round-down-for-half-even`
- `round-half-up-for-half-even` for Google-authored suites

Required checks:

- Confirm mutant failures are interpreted only for suites that pass the reference
  oracle.
- Confirm reviewed exclusions are not counted as zero-kill rows.
- Decide whether weak mutant classes require another prompt/template tightening
  pass before final audit acceptance.

Reviewer finding options:

- `adequate_for_current_bias_audit`
- `adequate_with_limitations`
- `needs_additional_mutants_or_prompt_tightening`

### 7. Review final claim language

Acceptable claim:

Current cross-tool S4 evidence did not find durable evidence that the benchmark
structurally favors Claude Code. Initial evidence suggestive of anti-OpenAI bias
was traced to bridge-harness assumptions and corrected. Residual asymmetries and
mutant adequacy limits are disclosed.

Do not claim:

- all possible bias has been eliminated,
- vendor equivalence has been proven,
- the authoring models have equal capability,
- the benchmark can never encode accidental vendor assumptions.

## Optional verification commands

Run from the repository root on the PR branch:

```bash
python3 -m json.tool docs/design/benchmark-bias-audit/bias_audit_openai/analysis/s4-suite-dispositions-v2-evidence-1200s.json
PYTHONDONTWRITEBYTECODE=1 python3 -m py_compile scripts/run_cross_tool_bias_s4.py
ruff check --no-cache scripts/run_cross_tool_bias_s4.py tests/unit/test_run_cross_tool_bias_s4.py
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m pytest -q -p no:cacheprovider tests/unit/test_run_cross_tool_bias_s4.py
```

To rerun S4 locally against the promoted batch:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 scripts/run_cross_tool_bias_s4.py \
  --store-root .startd8/bias-audit-store \
  --batch-id pricing-cross-tool-authoring-v2-evidence-1200s \
  --results-root /private/tmp/startd8-cross-tool-bias/pricing-cross-tool-authoring-v2-evidence-1200s/s4-results-reviewer-rerun \
  --pre-registration-path docs/design/benchmark-bias-audit/bias_audit_openai/analysis/s4-pre-registration-v2-evidence-1200s.json \
  --suite-disposition-path docs/design/benchmark-bias-audit/bias_audit_openai/analysis/s4-suite-dispositions-v2-evidence-1200s.json \
  --execute-reviewed-bridge
```

Expected result:

```json
{
  "status": "complete",
  "errors": []
}
```

## Reviewer signoff template

Use this structure for reviewer notes:

```markdown
# S4 v2 Bias Review Signoff

Reviewer:
Date:
Scope: pricing-cross-tool-authoring-v2-evidence-1200s

## Bias evidence reviewed

- Initial OpenAI/Codex 0/5 signal:
- Bridge-harness correction:
- Flattened-seam bridge support:
- Reviewed exclusions:
- Final reference admission:
- Mutant adequacy:

## Findings

1. Evidence of Claude Code / Anthropic favoritism:
2. Evidence of OpenAI/Codex disadvantage:
3. Evidence of Gemini/Google disadvantage:
4. Evidence explained or mitigated:
5. Residual unresolved concerns:

## Decision

Decision: accept / accept_with_limitations / block

Rationale:

Required follow-up before final public/academic claim:
```
