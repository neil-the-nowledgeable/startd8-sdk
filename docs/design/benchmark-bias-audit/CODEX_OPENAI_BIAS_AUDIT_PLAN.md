# OpenAI/Codex Differential Bias Audit — Implementation Plan

**Version:** 0.1 (Codex/OpenAI-specific pilot plan)  
**Date:** 2026-06-18  
**Requirements:** `CODEX_OPENAI_BIAS_AUDIT_REQUIREMENTS.md`  
**Source review:** `CROSS_TOOL_BIAS_AUDIT_REQUIREMENTS.md` v0.6 and
`CROSS_TOOL_BIAS_AUDIT_PLAN.md` v1.3  

Maps the OpenAI/Codex-specific audit to concrete steps over the pricing-seed artifacts:
`pricing.proto`, `requirements_text` in `seed-pricingservice.json`, `pricing_suite.py`, and
`scripts/run_flagship_benchmark.py`.

---

## Review Takeaways Applied

The cross-tool plan already contains the important scientific controls. This plan keeps them and adds
the OpenAI/Codex controls that were implicit or unnecessary in the Claude-oriented version:

| Area | Carry forward from cross-tool plan | OpenAI/Codex-specific addition |
|---|---|---|
| Experimental design | Factored suite-author and spec-author experiments. | Codex CLI is the treatment surface; Claude Code and Gemini CLI are comparators. |
| Neutral brief | Source-derived FIXED/OPEN matrix. | Anti-OpenAI/Codex leakage review; Codex cannot be the sole neutrality reviewer. |
| Automation | External CLIs by subprocess, not SDK authoring. | `codex exec` readiness/auth/sandbox/JSONL capture gate. |
| Reproducibility | Locked runtimes, manifests, immutable artifacts. | Record Codex auth mode, `CODEX_API_KEY` scoping, model alias/version, user config/rules/MCP/skill/plugin exposure. |
| Score impact | Model×spec interaction with own-vendor advantage. | `OVA_openai` is the primary endpoint; other OVAs remain required controls. |
| Security | Secret scan and publication controls. | Additional quarantine for Codex JSONL, stderr, auth cache paths, and any `~/.codex` metadata. |

---

## Step-by-Step

The audit is gated. No downstream step may consume artifacts until the upstream gate marks them
accepted or explicitly provisional. All gates emit human-readable records and machine-readable manifest
rows in the OpenAI audit store.

**S0 — Tool readiness and baseline snapshot.**
- Snapshot the reviewed source docs, repo commit, pricing seed paths, and current local authoring-tool
  status.
- Confirm the Codex CLI is runnable in the pilot image:
  - `codex --version`
  - `codex exec --help`
  - `codex debug models --bundled` when available
  - `npm list -g @openai/codex --depth=0` if installed through npm
- Current local finding from this review: npm reports `@openai/codex@0.49.0`, but `codex --version`
  fails because the bundled binary path is missing. Treat this as a blocking readiness gate, not as a
  benchmark result.
- Record comparator tool readiness for Claude Code and Gemini CLI with equivalent version/help checks.
- **Gate:** S0 passes only when Codex and comparator CLIs run inside the locked pilot environment, or
  failures are documented and the pilot is marked blocked.

**S1 — Neutral pricing brief** (`bias_audit_openai/brief/pricing-task-brief.md`).
- Draft from upstream Liferay evidence plus the bare seed-contract schema, not from existing
  Claude-authored artifacts and not from Codex/OpenAI output.
- Produce:
  - neutral brief
  - source-to-brief traceability matrix (`.md` and `.csv`)
  - source bibliography
  - OpenAI/Codex leakage checklist
  - existing-artifact leakage checklist
  - human + non-OpenAI reviewer sign-off
- Non-OpenAI cross-review uses Claude Code and Gemini CLI when available. Codex may run a separate
  target-vendor sanity pass, but its approval does not satisfy the neutrality gate.
- **Gate:** no S2/S3 prompt may render until the brief, matrix, bibliography, and sign-offs are complete.

**S2 — Prompt package and workspace isolation** (`bias_audit_openai/prompts/`).
- Create semantically versioned prompt templates for:
  - suite-author experiment
  - spec-author experiment
  - optional proto collection
  - artifact self-manifest output
- The rendered prompts differ only in declared tool mechanics. Diff all rendered prompts before runs.
- Build a clean authoring workspace template:
  - no uncontrolled `CLAUDE.md`, `AGENTS.md`, `AGENTS.override.md`, Gemini-specific files, local MCP
    config, user memories, or repository rules
  - only the neutral brief, allowed schema/source excerpts, prompt template, and output directories
  - deterministic package/runtime lockfiles
- If ambient files must be present, include them as versioned experimental inputs and mirror their
  contents across tools as much as each tool permits.
- **Gate:** at least one dry render per experiment/tool; prompt diffs show only approved mechanics; clean
  workspace manifest is complete.

**S3 — Codex authoring runner** (`scripts/run_openai_codex_bias_authoring.py`).
- Drive Codex only through `codex exec` for the primary sample group.
- Use dry-run-by-default. A real run requires explicit `--run`.
- Preferred command profile:
  - `codex exec --json --ephemeral`
  - `--sandbox workspace-write` when artifacts must be written; read-only for pure review/check steps
  - `--ask-for-approval never` in the isolated runner
  - `--ignore-user-config` and `--ignore-rules` for controlled automation, with any unsupported flags
    caught in S0 compatibility checks
  - `--model <locked-openai-model>`
  - optional `--output-schema` for final self-manifest JSON
- Authentication:
  - prefer `CODEX_API_KEY` scoped to the single `codex exec` invocation through Doppler or the runner's
    secret manager
  - do not export OpenAI credentials at job scope
  - ChatGPT/access-token auth is allowed only for trusted private runners and must be a separate
    run-stratum because workspace policy and entitlements differ from API-key auth
- Capture stdout JSONL, stderr, exit code, rendered prompt, file tree before/after, final message,
  generated artifacts, checksums, environment metadata, and redacted auth-mode metadata.
- Write raw output first to quarantine, scan for secrets/PII/license issues, then promote to the
  immutable audit store.
- **Gate:** one Codex dry run and one Codex non-spending format test produce valid JSONL capture,
  self-manifest, and no uncontrolled file access.

**S3b — Comparator authoring runners.**
- Implement equivalent subprocess runners for Claude Code and Gemini CLI.
- Match the Codex runner's prompt version, workspace isolation, retry policy, timeout, output
  requirements, quarantine, and manifest fields.
- Tool-specific auth mechanics are recorded but not embedded in the prompt.
- **Gate:** each comparator completes a dry run with valid rendered prompt, raw capture, and manifest.

**S4 — Artifact intake and normalization.**
- Apply one predeclared intake policy to all authoring outputs:
  - specs: text/Markdown, metadata header, sufficient to implement against canonical proto
  - protos: valid `.proto`, compile under locked toolchain, define requested service/messages
  - suites: compatible with locked harness, run against oracle + mutant battery within timeout
  - common: allowed deps only, no network, no manual semantic interpretation
- Normalize only mechanical differences through a versioned script. Record every diff and checksum.
- Catastrophic failures get at most one automated retry for truncation/formatting/file-boundary issues.
- **Gate:** every artifact is `accepted`, `rejected_with_reason`, or `provisional_debug_only`.
  Only accepted artifacts enter S6/S7/S8 final analyses.

**S5 — Oracle and mutant battery validation** (`bias_audit_openai/oracle/`, `bias_audit_openai/mutants/`).
- Build or reuse the known-correct Node oracle only after provenance is recorded.
- Validate oracle behavior against the S1 matrix and upstream evidence, not Codex, Claude, or Gemini
  generated specs alone.
- Require at least two reviewer sign-offs. Any Codex-authored oracle behavior must receive non-OpenAI
  review or reimplementation.
- Build K single-fault mutants covering every material OPEN dimension:
  rounding, discount strategy, fixed-amount basis, tax ordering, caps, decimal arithmetic, and error
  handling.
- Produce mutant manifest, expected-kill matrix, calibration weak suite, and adequacy report.
- **Gate:** S5 passes only when oracle provenance, oracle validation, and mutant adequacy all pass.
  S6 may run provisionally for debugging, but no final conclusion may cite provisional S5 evidence.

**S6 — Experiment A: suite-author bias.**
- Hold the spec fixed and have Codex CLI, Claude Code, and Gemini CLI author only the suite, N samples
  per tool.
- Run every accepted suite against the validated oracle and mutant battery.
- Produce:
  - `suite_equivalence_matrix.md`
  - `mutant_kill_matrix.csv` / `.parquet`
  - per-suite run logs
  - Codex vs comparator blind-spot summary
  - reject/catastrophic counts by tool
- **Gate:** S6 conclusions require S5 gates to pass and enough accepted suites for the predeclared
  FR-11 variance analysis.

**S7 — Experiment B: spec-author bias and score-impact.**
- Have each authoring surface author only the spec from the neutral brief, N samples per tool.
- Collect generated protos as secondary artifacts, but freeze the canonical proto/harness for the
  primary score-impact run.
- For each accepted spec:
  - create a canonical-proto seed variant
  - record adaptation decisions
  - route any semantic adaptation to adjudication before scoring
  - preselect FR-6 variants by the analysis plan, never by observed score
- Run the same flagship evaluated-model roster against each selected spec through
  `scripts/run_flagship_benchmark.py`, holding budget, harness, scoring, runtime, and proto constant.
- Primary endpoint: `OVA_openai`. Required controls: all vendor OVA values, overall interaction, and
  robustness under mixed-effects and paired bootstrap/permutation checks.
- **Gate:** S7 score-impact conclusions require frozen-proto compliance, accepted specs, reproducible
  flagship runs, and estimable uncertainty intervals.

**S8 — Divergence catalog, statistics, and adjudication** (`bias_audit_openai/divergences.md`).
- Catalog every material divergence from S4/S6/S7:
  exact snippet/location, authoring metadata, affected FIXED/OPEN item, source evidence, divergence
  class, FR-6 eligibility, exercising mutant, FR-11 stability, and downstream impact.
- Run the pre-registered analysis:
  - suite vectors: Hamming/Jaccard + per-mutant kill/miss
  - spec/proto choices: categorical coding and stability intervals
  - score-impact: mixed-effects or generalized mixed-effects interaction model
  - non-parametric robustness: paired bootstrap/permutation
  - multiplicity handling: Holm or predeclared equivalent
- Adjudication reviewers receive anonymized packets where practical. If Codex-specific markers cannot
  be removed, record why blinding failed.
- **Gate:** final labels require complete reviewer sign-off and no unresolved conflict; persistent
  reviewer disagreement adds a third reviewer.

**S9 — Report** (`bias_audit_openai/REPORT-pricing.md`).
- Report:
  - executive verdict
  - S1 traceability summary
  - Codex automation/auth/sandbox summary
  - comparator automation summary
  - intake rejects and catastrophic failures
  - oracle/mutant validation
  - suite equivalence and mutant kill matrices
  - divergence catalog and OPEN-item tracebacks
  - `OVA_openai`, all OVA controls, intervals, multiplicity, robustness
  - adjudication decisions
  - remediation-candidate IDs
  - raw artifact/publication bundle index
- Run the publication bundle through secret scan, PII scan, license/source-disclosure review, and
  redaction-diff verification.
- **Gate:** report is final only when all required gates pass or provisional status is clearly labeled.

**S10 — Remediation and re-run decision.**
- Remediate only the affected scope:
  - source ambiguity: pin behavior, promote OPEN to adjudicated-FIXED, add mutant/assertion
  - OpenAI/Codex bias: neutralize phrasing/shape, add regression mutant/assertion, re-run affected
    S6/S7 cells
  - tool capability: fix prompt/output/runner/acceptance without changing benchmark semantics
  - harness/proto confound: repair adapter policy or move to separate contract-shape sensitivity
- Preserve provenance linking original issue, patch, reviewer decision, and re-audit result.
- Stop after at most two remediation loops per seed.
- **Gate:** S10 closes when remediation succeeds or residual risk is recorded as ambiguous-flagged.

**S11 — Pilot go/no-go** (`bias_audit_openai/PILOT-GO-NOGO.md`).
- **Go** if:
  - neutral brief and anti-OpenAI leakage review are feasible
  - Codex CLI and comparator CLIs are reproducible in the locked runner
  - artifact acceptance yields comparable sample sets
  - oracle/mutant gates pass
  - `OVA_openai` is estimable within budget
  - adjudication produces interpretable labels
  - final verdict is neutral, biased-and-corrected, or bounded ambiguous-flagged
- **No-go/redesign** if:
  - Codex cannot run reliably
  - ambient instruction leakage cannot be controlled
  - failure rates dominate semantic evidence
  - proto/harness incompatibility dominates
  - FR-6 uncertainty remains too high under feasible N/cost
  - reviewers cannot separate OpenAI/Codex bias from source ambiguity or tool capability

---

## Artifact Dependency DAG

```text
S0 tool readiness
  -> S1 neutral brief
  -> S2 prompt/workspace isolation
  -> S3/S3b authoring runners
  -> S4 intake
  -> S5 oracle + mutants
  -> S6 suite experiment
  -> S7 spec/score experiment
  -> S8 divergence + adjudication
  -> S9 report
  -> S10 remediation (loops back only to affected S1/S2/S4/S6/S7 scope)
  -> S11 go/no-go
```

Forbidden edges:
- No Codex prompt rendering before S1 sign-off.
- No accepted artifact analysis before S4 intake.
- No FR-4 final claim before S5 oracle/mutant gates pass.
- No FR-6 score-impact claim before frozen-proto compliance is recorded.
- No final OpenAI/Codex bias verdict before S8 adjudication sign-off.

---

## Store and Manifest Shape

Use a structured audit store, SQLite or versioned Parquet, plus checksum-addressed raw artifact blobs.
Every row includes `audit_schema_version` and immutable provenance links.

Minimum tables:
- `source_docs`
- `brief_items`
- `prompt_templates`
- `rendered_prompts`
- `authoring_runs`
- `raw_artifacts`
- `normalized_artifacts`
- `intake_results`
- `oracle_validation`
- `mutants`
- `suite_results`
- `divergences`
- `flagship_runs`
- `statistical_results`
- `adjudications`
- `remediations`
- `publication_scans`

Critical enums:
- artifact status: `raw`, `normalized`, `accepted`, `rejected_with_reason`, `provisional_debug_only`
- authoring surface: `codex_cli`, `claude_code`, `gemini_cli`, `openai_api_sensitivity`,
  `codex_app_sensitivity`, `codex_cloud_sensitivity`, `codex_ide_sensitivity`
- auth mode: `api_key`, `chatgpt_login`, `access_token`, `provider_key`, `none`
- verdict: `neutral`, `biased_and_corrected`, `ambiguous_flagged`, `blocked`
- adjudication label: `neutral_unanimous`, `source_ambiguity`,
  `openai_codex_vendor_author_bias_candidate`, `non_openai_vendor_author_bias_candidate`,
  `tool_capability`, `harness_proto_confound`, `insufficient_evidence`

---

## Pre-Registered Analysis Notes

The analysis plan must be committed before consuming S6/S7/S8 results.

- **Primary endpoint:** `OVA_openai`.
- **Minimum pilot N:** N >= 3/tool/type for feasibility; N >= 5 preferred for final claims.
- **Suite equivalence:** identical oracle+mutant pass/fail vector, with Hamming/Jaccard diagnostics.
- **Spec divergence:** categorical coding per OPEN item; stable choice threshold >= 80% accepted samples.
- **Score-impact:** model-vendor + spec-author-vendor + interaction, with run-index pairing and
  test-case random effects when test-level data is available.
- **Bias threshold:** interval excludes zero and absolute OVA >= 5 pts or >= 0.5 pooled within-cell SD.
- **Robustness:** mixed-effects result must agree directionally with paired bootstrap/permutation.
- **Multiplicity:** Holm or equivalent over vendor OVA tests.
- **Exclusion sensitivity:** report conclusions with and without catastrophic/tool-capability exclusions
  where enough data exists.

---

## Immediate Implementation Checklist

1. Repair or reinstall Codex in the pilot environment until `codex --version` and `codex exec --help`
   succeed.
2. Create `bias_audit_openai/` store, quarantine, prompt, brief, oracle, mutant, run, and report
   directories.
3. Draft S1 neutral brief and matrix from upstream Liferay + seed schema only.
4. Create prompt templates and rendered-prompt diff checks.
5. Implement dry-run runners for Codex CLI, Claude Code, and Gemini CLI.
6. Implement S4 intake and normalization before any semantic analysis.
7. Validate oracle and mutant adequacy before accepting suite-equivalence results.
8. Commit the analysis plan before running final S6/S7 batches.

