# Cross-Tool Differential Bias Audit — Implementation Plan

**Version:** 1.1  
**Date:** 2026-06-17  
**Tracks:** `CROSS_TOOL_BIAS_AUDIT_REQUIREMENTS.md` (drove this plan; updated to v0.3 by it)

Maps the audit to concrete steps over the pricing-seed artifacts (`pricing.proto`,
`requirements_text` in `seed-pricingservice.json`, `pricing_suite.py`) and the flagship runner
(`scripts/run_flagship_benchmark.py`), and records what planning revealed.

---

## Discoveries (feed the reflection pass)

| What v0.1 assumed | What planning revealed |
|---|---|
| Re-author all 3 artifacts at once, then diff (FR-2/FR-4/FR-5) | **CONFLATED.** The suite's expected values depend on the spec's semantic choices. If a tool authors a different spec AND suite, suite-disagreement can't be told apart from a consequence of its different spec. The experiment must be **factored**: (i) fix the spec → vary only the suite (isolates *suite*-author bias); (ii) fix the behavior/oracle → vary only the spec (isolates *spec*-author bias). |
| Equivalence = suites agree on the correct oracle (FR-4) | A correct oracle is passed by almost any plausible suite → it barely discriminates. Need a **battery of mutant (deliberately-buggy) reference servers**; a biased/weak suite fails to catch mutants a good suite catches. Equivalence = suites produce the same pass/fail vector across the whole battery. (Resolves OQ-3.) |
| Score-impact: does swapping spec change scores (FR-6) | **Confounded by spec quality.** A clearer/vaguer spec shifts *all* models uniformly — that's quality, not bias. The bias signal is an **interaction**: each vendor's model scoring *relatively* higher under its own vendor's spec. Analyze model×spec interaction, not marginal score change. |
| One sample per tool per artifact | These agents are **non-deterministic**; one sample conflates author-bias with run-variance. Need **N samples per tool per artifact**; treat divergence statistically (does Claude consistently differ, or is it within-tool noise?). (Resolves OQ-5 — can't force determinism; sample instead.) |
| "Neutral brief" is straightforward (FR-1) | The brief is the crux and the hardest artifact. Derived from Claude's requirements doc → bias pre-injected. Must derive from the **Liferay source + the bare seed-contract schema**, and explicitly enumerate which constraints are *fixed* (single RPC, decimal money, gRPC) vs which semantic choices are *left open* (rounding default, chain/addition, fixed-amount basis, tax ordering) — the open ones are exactly what's under test. |
| Triangulation: agree=neutral, diverge=biased (FR-7) | 2-vs-1 splits are ambiguous: Claude-vs-(Codex+Antigravity) could be Claude bias OR the other two sharing a non-Claude convention. Only **unanimous agreement** is a strong neutrality signal; majority is a flag, not proof. Needs explicit decision rules. |
| Tool access is uniformly automatable | Verify per-tool at plan time: Codex needs `OPENAI_API_KEY`, Antigravity needs Google auth (both via Doppler); Antigravity has historically been IDE-interactive — confirm a headless/CLI path exists or fall back to scripted-capture. Capture tool+model version per run (FR-3). |

## Workflow gates and deliverables

The audit is organized as a gated workflow. Later analyses may not consume upstream artifacts until the relevant gate passes. Each gate produces both human-readable artifacts and machine-readable metadata in the audit data store.

| Phase | Step(s) | Primary owner(s) | Inputs | Outputs | Gate / blocking dependency |
|---|---|---|---|---|---|
| Brief foundation | S1 | Audit lead + domain reviewer(s) | Liferay source, bare seed-contract schema, seed JSON shape | `brief/pricing-task-brief.md`, source-to-brief traceability matrix, leakage-review checklist, reviewer sign-off | Blocks all authoring prompts. The brief must contain only admissible FIXED/OPEN items with citations and reviewed leakage controls. |
| Prompting + execution substrate | S2 | Harness owner + tool-integration owner | Neutral brief, tool credentials, locked runtimes | `scripts/run_bias_reproduction.py`, prompt-template package, run manifests, queryable result store, raw outputs, transcripts, retry logs | Blocks generated-artifact use. Each authoring run must have prompt/version/parameter/tool metadata and immutable raw capture. |
| Intake + normalization | S2b | Harness owner + audit lead | Raw generated artifacts | Accepted/rejected artifact records, normalization diffs, compile/run logs, failure classifications | Blocks S4/S5/S6. Only accepted artifacts, or explicitly logged failures for capability reporting, can enter analysis. |
| Oracle + mutant validity | S2.5/S3 | Oracle owner + mutant owner + reviewers | Neutral brief traceability matrix, upstream evidence, canonical proto/harness | Known-correct Node oracle, mutant battery, oracle evidence log, mutant manifest, adequacy report | Blocks S4. Equivalence conclusions are provisional until oracle provenance/validation and mutant adequacy gates pass. |
| Suite-author experiment | S4 | Analysis owner + harness owner | Accepted suites, validated oracle/mutants | Suite×target pass/fail vectors, mutant kill matrix, equivalence matrix | Requires accepted suites and validated battery. |
| Spec-author experiment | S5/S6 | Analysis owner + flagship-runner owner | Accepted specs, canonical proto/harness, flagship roster | Divergence catalog, adapted spec variants, score-impact dataset, model×spec interaction estimates | Requires canonical-proto adaptation decisions logged and adjudicated when they resolve OPEN items. |
| Attribution + reporting | S6/S7 | Audit lead + blinded reviewers | FR-4/FR-5/FR-6/FR-11 outputs | Adjudication evidence log, verdict, report, publication bundle | Requires reviewer protocol, decision labels, and redaction/secrets scan before publication. |
| Remediation loop | S8 | Audit lead + seed owner + reviewers | Reported bias/ambiguity/confound | Seed patches, prompt/harness/oracle/mutant updates, re-audit scope | Blocks final pilot verdict when material issues are remediable. At most two loops before escalation. |
| Pilot expansion decision | S9 | Benchmark owner + audit lead | Final report, remediation results, residual risks | Go/no-go decision for additional seeds | Expansion blocked if FR-13 criteria fail. |

## Step-by-step

**S1 — Neutral brief** (`brief/pricing-task-brief.md`). Author the FR-1 brief from Liferay source +
the seed-contract schema; tag each requirement `FIXED` or `OPEN`. Reviewed by a human for Claude-idiom leakage.

Deliverables:
- `brief/pricing-task-brief.md`: vendor-agnostic task brief.
- `brief/pricing-traceability-matrix.{md,csv}`: source-to-brief traceability matrix.
- `brief/leakage-review-checklist.md`: human review checklist and sign-off.
- `brief/source-bibliography.md`: source citations, URLs, commits, file paths, and schema fields used.

Traceability matrix requirements:
- For every brief requirement, record:
  - requirement ID;
  - `FIXED` or `OPEN` tag;
  - upstream Liferay evidence, bare seed-schema constraint, or explicit human judgment supporting the tag;
  - exact source citation, URL, commit, file path, line/range when available, or schema field;
  - why a `FIXED` item is not an author-specific choice;
  - why an `OPEN` item is not pre-resolved by Claude-authored artifacts;
  - unresolved ambiguity to map later into FR-5 divergence entries, FR-7 adjudication, and FR-9 remediation.
- A `FIXED` item is admissible only if it traces to upstream evidence or an explicit seed-schema constraint.
- An `OPEN` item is admissible only if the source evidence permits multiple plausible implementations or if the item is an intentional benchmark-design choice under test.
- Claude-authored artifacts may be used only as objects of comparison after the brief is drafted, not as source evidence for resolving `OPEN` items.

Human leakage-review checklist:
- reviewer confirms the brief was drafted from Liferay source + seed schema, not from Claude’s existing requirements text;
- reviewer checks for Claude-specific phrasing, structure, examples, default assumptions, and semantic resolutions;
- reviewer checks that examples or edge cases do not encode answers to `OPEN` items unless explicitly labeled as open;
- reviewer verifies each `FIXED` item has admissible source evidence;
- reviewer verifies each `OPEN` item remains genuinely open and is not implicitly resolved by wording;
- reviewer signs off with reviewer ID/role, date, source set reviewed, and any dissent or residual ambiguity.

Gate:
- S1 passes only when the brief, traceability matrix, bibliography, and leakage-review checklist are complete and signed off.
- S2 prompts may not be rendered until S1 passes.

**S2 — Reproduction harness** (`scripts/run_bias_reproduction.py`). Drive Codex + Antigravity (+ Claude
control) via CLI/API, N samples each, capturing prompt/version/output/timestamp to a durable, queryable audit store.
Dry-run-by-default; keys via `doppler run`.

The harness must support:
- per-tool execution adapters for Claude Code, Codex, and Antigravity;
- headless CLI/API invocation where available;
- documented scripted manual capture if Antigravity has no headless mode, with the asymmetry flagged;
- N-sample execution per tool/artifact type;
- dry-run prompt rendering without API calls;
- immutable raw-output capture before any normalization;
- retry logging for transient provider/tool failures;
- machine-readable manifests linking every artifact to authoring run metadata.

Prompt template and run configuration deliverable:
- Store prompt templates under `bias_audit/prompts/` with semantic versions, for example:
  - `suite_authoring.v1.md`;
  - `spec_authoring.v1.md`;
  - optional `proto_authoring.v1.md` if proto variants are collected.
- Each rendered prompt must clearly separate:
  - neutral brief content from S1;
  - experiment-specific instructions for suite authoring or spec authoring;
  - allowed and forbidden dependencies;
  - output file requirements and file-boundary conventions;
  - tool-specific invocation mechanics;
  - parameter settings;
  - any few-shot examples or scaffolding.
- Few-shot examples, if used:
  - must be vendor-neutral;
  - must be identical across tools except unavoidable API/CLI mechanics;
  - must not encode a resolution of any `OPEN` pricing item;
  - must be versioned and captured as part of the rendered prompt.
- Capture for every run:
  - prompt-template version;
  - rendered prompt;
  - tool-specific substitutions;
  - authoring tool and provider;
  - model/version identifier;
  - temperature, top-p, max tokens, tool-use settings, retry settings, random seed where available;
  - timestamp, sample index, run group, and experiment ID;
  - CLI/API command line or request metadata.

Reproducibility baseline:
- Lock runtime substrate:
  - Python version and package lockfile;
  - Node version and package lockfile;
  - gRPC/protobuf compiler and plugin versions;
  - package manager versions;
  - container images or equivalent pinned runtime environments.
- Record execution environment:
  - OS, architecture, container digest where applicable;
  - required environment variables;
  - secrets-handling method (`doppler run`, no secret persistence);
  - network access policy;
  - resource limits and timeouts.
- Record dependency provenance:
  - lockfile checksums;
  - source commits;
  - generated-artifact execution dependencies;
  - checksum policy for raw and normalized artifacts.
- Record provider behavior:
  - model aliases and provider-reported concrete versions;
  - rate limits, retries, transient errors, and backoff decisions;
  - unavailable seed handling or nondeterministic hosted-model limitations.
- Model-version update policy:
  - prefer dated/version-locked models for the full pilot;
  - if a model updates during an active batch and the provider cannot guarantee continuity, restart the affected batch;
  - if version locking is impossible, record provider-reported model identifier and timestamp for every call, analyze pre/post update runs separately, and flag cross-version comparisons as lower-confidence;
  - do not mix model versions within the same FR-11 sample group or FR-6 interaction cell unless explicitly modeled and reported.

Structured audit data store:
- Replace ad hoc batch-only storage with a structured, queryable store:
  - SQLite for manifests and normalized result tables, or
  - versioned Parquet files plus manifest-indexed raw artifact directories.
- Minimum tables/files:
  - `authoring_runs`;
  - `prompts`;
  - `raw_outputs`;
  - `normalized_artifacts`;
  - `intake_results`;
  - `suite_runs`;
  - `mutant_results`;
  - `divergence_codes`;
  - `flagship_runs`;
  - `statistical_results`;
  - `adjudications`;
  - `remediations`.
- Raw artifacts remain immutable files addressed by checksum; database rows point to file paths and checksums.
- Analysis notebooks/scripts read from the structured store, not from hand-curated batch directories.

Publication and secrets-safety controls:
- No raw prompt, transcript, environment dump, or artifact bundle may be published until it passes:
  - secret scanning;
  - API key/token redaction;
  - environment-variable allowlist filtering;
  - provider account/project identifier redaction where needed;
  - third-party source excerpt/license review;
  - personal data scan for reviewer/tool transcripts.
- Redactions must be logged as reproducibility-preserving diffs: what class of content was removed, where, and why.
- Prefer publishing checksums and reproducible retrieval instructions for third-party source excerpts when licenses discourage verbatim redistribution.
- Preserve unredacted artifacts in restricted internal storage only when necessary for audit reproducibility.

Gate:
- S2 passes when at least one dry run renders valid prompts for each experiment/tool, the data store schema is initialized, runtime locks are recorded, and tool invocation/auth status is documented.

**S2b — Artifact intake and normalization.** Before any generated artifact enters S4, S5, or S6, apply a
single predeclared intake, normalization, repair, retry, and rejection policy.

Acceptance criteria:
- Specs:
  - Markdown or plain text with structured metadata header identifying authoring run;
  - sufficient task description for implementing the server against the canonical proto;
  - no dependency on private Claude-authored artifacts except where the experiment explicitly fixes them;
  - not executable code as the only specification unless requested by the prompt.
- Protos:
  - valid `.proto` syntax;
  - compile with locked protobuf/gRPC tooling;
  - define requested service and messages unless cataloged as a failure;
  - no nonstandard protoc plugins unless allowed by prompt.
- Suites:
  - Python test file compatible with the locked harness unless otherwise specified;
  - runs under the locked runtime;
  - executes against the known-correct oracle and mutant battery through the standard adapter;
  - completes within configured timeout;
  - uses only allowed dependencies.

Normalization policy:
- Allow only mechanical normalization:
  - filenames;
  - formatting;
  - import paths;
  - harness adapter paths;
  - file-boundary extraction;
  - metadata header insertion when all fields are already known from the run manifest.
- Never silently repair:
  - semantic assertions;
  - expected values;
  - rounding choices;
  - API behavior;
  - validation semantics;
  - edge-case coverage.
- Record all normalization diffs and checksums.

Retry and repair policy:
- A generation is a catastrophic failure if it produces syntactically invalid artifacts, non-compiling code, non-running suites, missing required files, or content that fails to address a majority of the brief.
- Allow at most one automated retry using the same prompt template and parameters when failure is due to truncation, formatting, or missing file boundaries.
- Allow mechanical repair only under the normalization policy above.
- Do not allow human semantic repair for inclusion in equivalence, divergence, or score-impact analysis.
- Log raw failed output, failure category, retry status, and exclusion reason.
- Count catastrophic failures in tool-capability reporting and FR-11 variance.
- Exclude catastrophic failures from semantic bias calls unless failures are consistent, vendor-specific, and adjudicated as relevant to benchmark-input authorship.

Gate:
- S2b passes for an artifact only when intake status is `accepted` or `rejected_with_reason`.
- Only accepted artifacts enter FR-4/FR-5/FR-6 semantic analyses.
- Rejected artifacts remain in capability/failure reporting.

**S2.5 — Oracle and mutant validation plan.** Before S3 construction is treated as usable for FR-4, define
the validation protocol, reviewers, and adequacy gates for the known-correct oracle and mutant battery.

Deliverables:
- `bias_audit/oracle/VALIDATION_PLAN.md`;
- `bias_audit/mutants/ADEQUACY_PLAN.md`;
- reviewer assignment and blinding plan where practical;
- expected oracle evidence log schema;
- expected mutant manifest schema;
- expected kill-matrix template.

Gate definition:
- FR-4 equivalence conclusions are not trusted until:
  - the oracle provenance gate passes;
  - the oracle validation gate passes;
  - the mutant adequacy gate passes;
  - all validation artifacts are recorded in the structured audit store.
- If any gate fails, S4 may run for debugging, but results are labeled provisional and cannot support final verdicts.

**S3 — Mutant reference battery** (`bias_audit/mutants/`). The known-correct Node oracle + K deliberately-buggy
mutants (wrong rounding mode, addition-when-chain, tax-before-discount, off-by-cap, float arithmetic, ...).
Each mutant targets one semantic choice.

Construction deliverables:
- `bias_audit/oracle/`: known-correct Node oracle and smoke tests.
- `bias_audit/oracle/evidence-log.md`: behavior-by-behavior evidence and review sign-off.
- `bias_audit/mutants/`: runnable mutant servers.
- `bias_audit/mutants/manifest.{md,csv,json}`: mutant ID, targeted `OPEN` item, injected fault, expected behavior, source rationale, implementation diff, and expected kill condition.
- `bias_audit/mutants/expected-kill-matrix.{md,csv}`: which probes should kill which mutants and why.
- `bias_audit/mutants/adequacy-report.md`: validation outcome and adequacy gate result.

Oracle provenance gate:
- Record who authored the oracle:
  - human/tool provenance;
  - commits;
  - source files;
  - whether any portion was derived from Claude-authored artifacts.
- If any portion is Claude-derived:
  - label the affected behavior;
  - require independent non-Claude review or reimplementation before using it as sole correctness anchor.
- Validate oracle behavior against:
  - S1 traceability matrix;
  - upstream Liferay evidence;
  - seed-schema constraints;
  - adjudicated `OPEN` decisions where applicable.
- Do not validate solely against Claude’s existing spec.
- Require at least two reviewers, one blinded to the original Claude artifact where practical.
- Record reviewer IDs/roles, blinding status, evidence checked, and sign-off.

Oracle validation gate:
- Maintain behavior-level evidence:
  - expected behavior;
  - source citation;
  - test case(s);
  - reviewer sign-off.
- Run property/metamorphic checks where applicable:
  - decimal precision invariants;
  - monotonicity under quantity increases;
  - cap behavior;
  - stable rounding;
  - discount/tax ordering probes;
  - error handling probes.
- Oracle must:
  - pass all oracle tests;
  - satisfy FIXED seed-schema constraints;
  - be runnable under locked runtime;
  - expose failures with deterministic logs.

Mutant adequacy gate:
- Cover every material `OPEN` semantic dimension from S1 with at least one mutant.
- Use at least two mutants for high-risk dimensions when feasible:
  - rounding;
  - ordering;
  - caps;
  - decimal arithmetic;
  - error handling.
- Include only single-fault mutants unless explicitly marked as interaction mutants.
- Validate each mutant against the oracle and at least one hand-authored smoke/calibration suite.
- Exclude or rewrite equivalent mutants that cannot be distinguished from the oracle under the chosen input domain.
- Exclude or rewrite invalid mutants that crash, violate the proto/harness contract, fail unrelated `FIXED` constraints, or cannot serve as runnable targets.
- Detect redundant mutants whose kill vectors are identical across calibration suites; redundancy is allowed but does not count toward semantic coverage.
- Require minimum discriminatory power:
  - each material `OPEN` dimension has at least one valid non-equivalent mutant;
  - the battery distinguishes at least one intentionally weak calibration suite from the oracle;
  - each mutant differs from the oracle on at least one targeted probe;
  - no mutant’s failure is due solely to harness incompatibility or catastrophic server failure.

Gate:
- S3 passes only when the oracle provenance/validation gates and mutant adequacy gate pass.
- If S3 fails, expand/rewrite the battery before trusting FR-4 results.

**S4 — Factored experiment A (suite-author bias).** Fix the Claude spec; have each tool author only the
**suite** (N samples). Run every suite against the mutant battery → pass/fail vectors → equivalence matrix.
A suite that misses a mutant the others catch reveals an author blind spot.

Execution:
- Inputs:
  - fixed Claude spec;
  - accepted generated suites from S2b;
  - validated oracle and mutant battery from S3.
- For each suite sample:
  - run against the known-correct oracle;
  - run against each mutant;
  - capture pass/fail vector, logs, timeout status, and failure localization;
  - store results in `mutant_results` and `suite_runs`.
- Localize missed mutants to missing or weak assertions where possible without semantically repairing the suite.

Outputs:
- `bias_audit/results/suite_equivalence_matrix.md`;
- `bias_audit/results/mutant_kill_matrix.{csv,parquet}`;
- per-suite logs and failure summaries;
- invalid/rejected sample counts from S2b.

Gate:
- S4 conclusions require S3 gates to pass.
- If S3 was provisional, S4 output must be labeled provisional and excluded from final verdicts until battery adequacy is restored.

**S5 — Factored experiment B (spec-author bias).** Each tool authors only the **spec** (N samples) from the
brief. Build a seed variant per spec; run the 3 flagships against each via the flagship runner; analyze the
**model×spec interaction** for the bias signal. (~3 variants × pricing-only N=5 ≈ $8.)

Canonical proto and adapter policy:
- The primary FR-6 score-impact analysis freezes the canonical benchmark proto and harness.
- Generated proto variants are collected as secondary artifacts but are not automatically used in score-impact runs.
- Spec variants must be expressed against the frozen canonical proto for the primary analysis.
- Field-name changes, RPC-shape changes, validation-semantics changes, or incompatible message shapes are not silently normalized into the primary score-impact run.
- If a generated spec cannot be expressed against the frozen canonical proto without resolving an `OPEN` semantic choice:
  - log the adaptation issue;
  - create an FR-5 divergence entry;
  - route the adaptation decision to FR-7 adjudication before scoring.
- Mechanical adapter changes may be allowed only when they do not change semantics:
  - path wiring;
  - metadata headers;
  - canonical proto references;
  - file packaging.
- Any adapter or normalization diff must be recorded with checksum and rationale.

Contract-shape sensitivity analysis:
- Vendor-authored proto variants are retained for FR-5 divergence analysis.
- Optional contract-shape sensitivity analysis may run only if adapters can be built without changing task semantics.
- It must be separately labeled and reported.
- It must not be combined with the primary spec-wording interaction analysis.
- Contract/proto effects are classified separately from spec-wording effects.

Execution:
- Inputs:
  - accepted generated specs from S2b;
  - optional generated protos for divergence catalog only;
  - canonical proto/harness;
  - flagship runner.
- For each accepted spec sample:
  - create a seed variant using canonical proto;
  - record any adaptation decisions;
  - assign variant metadata: author-vendor, tool, model/version, sample index, prompt-template version, timestamp.
- Select representative variants for FR-6 according to the analysis plan:
  - all accepted variants if budget permits;
  - otherwise predeclared sampling/aggregation without cherry-picking based on score.

Outputs:
- `bias_audit/spec_variants/`;
- `bias_audit/adapters/`;
- `bias_audit/divergences.md`;
- structured divergence coding table;
- canonical-proto adaptation log.

**S6 — Divergence catalog + attribution** (`bias_audit/divergences.md`). Catalog proto/spec semantic
divergences; classify source-ambiguity vs author-choice; apply the unanimity/triangulation rules.

Divergence catalog fields:
- artifact location and snippet;
- authoring run metadata;
- affected `FIXED` or `OPEN` item from S1;
- upstream evidence or absence of evidence;
- divergence type:
  - behavior;
  - wording only;
  - contract shape;
  - validation semantics;
  - harness compatibility;
  - tool-capability artifact;
- eligibility for FR-6 primary score-impact analysis under frozen-proto policy;
- adapter decision, if any;
- mutant(s) in S3 exercising the divergence;
- consistency across FR-11 samples;
- downstream FR-4 or FR-6 impact, if observed.

Classification rubric:
- **Legitimate source-ambiguity**: upstream evidence or seed-schema constraints admit multiple plausible behaviors; the item was tagged `OPEN`; no artifact relies solely on Claude-derived wording.
- **Author-specific choice**: the generated artifact resolves an `OPEN` item in a way not compelled by source, especially if stable across samples for the same authoring tool.
- **Schema/contract constraint**: the divergence is required by bare seed-contract schema and should have been `FIXED`; if omitted, S1 must be corrected.
- **Tool-capability artifact**: malformed output, missing instructions, incomplete generation, or format failure rather than coherent semantic choice.
- **Harness/proto confound**: contract-shape or adapter incompatibility, not spec wording or semantic interpretation.
- **Human-adjudicated correction**: reviewers decide the neutral brief or canonical seed should pin the behavior.

Human adjudication workflow:
- Use at least two reviewers with benchmark/domain expertise.
- Where practical, blind reviewers to author-vendor labels and present anonymized variants.
- Provide reviewers with:
  - S1 traceability matrix;
  - upstream Liferay evidence;
  - seed-schema constraints;
  - S4 pass/fail vectors;
  - S5/S6 divergence entries;
  - S6/FR-6 interaction summaries;
  - FR-11 variance summaries.
- Reviewers assign one label:
  - **Neutral/unanimous**;
  - **Legitimate source-ambiguity**;
  - **Vendor-author bias candidate**;
  - **Tool-capability difference**;
  - **Harness/proto confound**;
  - **Insufficient evidence**.
- Resolve disagreement by discussion.
- If disagreement persists, add a third reviewer and report all opinions plus the final decision rule.
- Preserve an adjudication evidence log:
  - reviewer IDs/roles;
  - blinding status;
  - decision labels;
  - rationale;
  - source citations;
  - remediation recommendation.

Attribution rules:
- Unanimous agreement across all three independent authors is the only strong neutrality signal.
- Any divergence, including 2-vs-1 splits, is a flag for adjudication, not an automatic bias verdict.
- Prefer **vendor-author bias candidate** only when:
  - divergence is semantically coherent;
  - maps to an `OPEN` item or suite assertion gap;
  - recurs across samples for the same author-vendor;
  - is separable from compile/run failures;
  - aligns with directional FR-4 blind spot or FR-6 own-vendor advantage where available.
- Prefer **tool-capability difference** when the artifact is malformed, incomplete, contradicts explicit `FIXED` requirements, fails acceptance criteria, or varies idiosyncratically across samples.
- Prefer **ambiguous/source-driven** when multiple authoring tools converge on a non-Claude choice or upstream source lacks enough evidence.

**Analysis plan — pre-registered before final S4/S5/S6/S7 analyses.** The statistical analysis plan must be
written and frozen before consuming final results for bias verdicts.

Deliverables:
- `bias_audit/analysis/ANALYSIS_PLAN.md`;
- `bias_audit/analysis/statistical_scripts/`;
- `bias_audit/analysis/pre_registration_manifest.json`.

FR-4 suite-equivalence analysis:
- Experimental unit: one accepted generated suite sample.
- Outcome: pass/fail vector over oracle + K mutants.
- Metrics:
  - pairwise Hamming distance between vectors;
  - Jaccard distance over killed mutants;
  - per-mutant kill/miss indicators.
- Equivalence:
  - two suites are equivalent iff their pass/fail vectors are identical across the validated battery;
  - tool-level equivalence summarized across samples.
- Uncertainty:
  - bootstrap over accepted suite samples where N permits;
  - exact/binomial intervals for per-mutant kill rates.
- Decision:
  - a suite blind spot is a candidate only if it misses a valid mutant that comparable accepted suites catch and the miss maps to an `OPEN` item or assertion gap.
  - final bias classification still requires FR-7 adjudication.

FR-5 divergence analysis:
- Experimental unit: one accepted generated spec/proto sample.
- Metrics:
  - categorical coding of each S1 `OPEN` item;
  - contract-shape dimensions;
  - validation-semantics dimensions;
  - missing/invalid separated from semantic choices.
- Stability:
  - stable tool-level semantic choice requires at least 80% of accepted samples for that tool to make the same coded choice;
  - N ≥ 5 preferred for final claims.
- Tests:
  - Fisher exact test or multinomial/hierarchical model over coded `OPEN` choices depending on sample size;
  - multiplicity handling across coded dimensions.
- Output:
  - raw coded choices;
  - confidence/credible intervals;
  - p-values where used;
  - invalid sample counts;
  - sensitivity excluding catastrophic failures.

FR-6 score-impact analysis:
- Experimental unit: one evaluated-model implementation attempt for one spec variant under frozen canonical proto/harness.
- Cells: evaluated model-vendor × spec author-vendor.
- Minimum N:
  - N ≥ 5 implementation attempts per cell for pilot score-impact unless power/cost calibration approves another N before running.
- Pairing:
  - pair attempts by run index across spec variants for the same evaluated model where possible.
- Outcome:
  - benchmark score as pass rate or normalized points on the same scale across specs.
- Primary model:
  - linear mixed-effects model for approximately continuous scores, or generalized mixed-effects model for binary/test-level pass-fail data;
  - fixed effects: evaluated model-vendor, spec author-vendor, and interaction;
  - random effects: replicate/run index and test case when modeling test-level data.
- Non-parametric check:
  - paired bootstrap or permutation test over run indices.
- Interaction metric:
  - for vendor `v`, compute own-vendor advantage:

    `OVA_v = [S(model_v, spec_v) - mean_a≠v S(model_v, spec_a)] - mean_u≠v [S(model_u, spec_v) - mean_a≠v S(model_u, spec_a)]`

    where `S(model, spec)` is the mean score for that cell.
- Uncertainty:
  - 95% confidence intervals or Bayesian credible intervals for each `OVA_v`;
  - overall model×spec interaction interval.
- Bias-signal threshold:
  - candidate signal only if interval excludes zero and absolute `OVA_v` is at least 5 percentage points or at least 0.5 pooled within-cell standard deviations, whichever is larger.
- Multiplicity:
  - Holm correction or equivalent predeclared method for the three vendor-specific `OVA_v` tests.
- Robustness:
  - report whether conclusions hold under both mixed-effects and paired bootstrap/permutation analyses.

FR-11 non-determinism and variance analysis:
- Experimental unit: one accepted generated artifact sample.
- Minimum N:
  - N ≥ 3 per tool per artifact type for pilot;
  - N ≥ 5 preferred for final bias claims.
- Within-tool variance:
  - dispersion of divergence metrics among samples from the same authoring tool.
- Between-tool variance:
  - dispersion between samples from different authoring tools.
- Primary test:
  - permutation test or bootstrap comparing between-tool distances to within-tool distances.
- Bias-candidate threshold:
  - author-vendor stable choice differs from at least one other author-vendor stable choice;
  - between-tool distance exceeds within-tool distance with 95% interval excluding zero or p < 0.05 after multiplicity handling;
  - divergence maps to an `OPEN` item or suite assertion gap;
  - catastrophic failures/tool-capability artifacts do not explain the pattern.
- Reporting:
  - confidence intervals;
  - p-values or credible intervals;
  - raw coded choices;
  - invalid-sample counts;
  - sensitivity to excluding catastrophic failures.

Gate:
- Final S4/S5/S6/S7 conclusions may not be issued until the analysis plan is frozen and committed.
- Post hoc analyses are allowed only if labeled exploratory.

**S7 — Report + remediation** (`bias_audit/REPORT-pricing.md`). Equivalence matrix, interaction deltas,
divergence verdicts; for each confirmed bias, the corrective seed edit + re-audit.

Report contents:
- executive verdict:
  - neutral;
  - biased-and-corrected;
  - ambiguous-flagged;
  - unresolvable within pilot constraints, if applicable.
- S1 brief and traceability review summary.
- S2 reproducibility summary:
  - tool invocation;
  - model versions;
  - prompt-template versions;
  - runtime/container/dependency locks;
  - data-store manifest;
  - rejected/failed sample counts.
- S3 oracle and mutant validation summary:
  - oracle provenance;
  - reviewer sign-off;
  - mutant manifest;
  - adequacy gate result.
- S4 suite-equivalence matrix and mutant kill matrix.
- S5/S6 divergence catalog and canonical-proto adaptation log.
- FR-6 score-impact results:
  - model×spec interaction;
  - `OVA_v` estimates;
  - uncertainty intervals;
  - multiplicity handling;
  - robustness checks.
- FR-11 sampling/variance results.
- FR-7 adjudication evidence log:
  - reviewer roles;
  - blinding status;
  - labels;
  - rationales;
  - unresolved disagreements.
- OPEN-item tracebacks for all material findings.
- Remediation recommendations and required re-audit scope.
- Raw artifact index and publication bundle manifest.

Verdict criteria:
- **Neutral** requires:
  - S1 traceability matrix passes review;
  - oracle validation and mutant adequacy gates pass;
  - S4 suite pass/fail vectors are unanimously equivalent across accepted samples or differences are adjudicated as non-semantic/tool-capability artifacts;
  - S5/S6 find no unresolved material semantic or contract divergence, or all divergences are adjudicated harmless;
  - FR-6 shows no vendor-specific own-vendor advantage meeting the pre-specified threshold;
  - FR-11 shows cross-tool divergence no greater than within-tool run variance for material `OPEN` items;
  - adjudication reaches neutral/unanimous or harmless labels for all material flags.
- **Biased-and-corrected** requires:
  - at least one material divergence or score-impact interaction adjudicated as vendor-author bias candidate;
  - affected behavior traced to `OPEN` item(s) or Claude-derived assumptions;
  - remediation pins or neutralizes the issue;
  - re-audit satisfies neutral criteria for the remediated scope.
- **Ambiguous-flagged** applies when:
  - evidence is insufficient;
  - reviewers classify issue as legitimate source ambiguity but remediation has not pinned it;
  - S4/S5/S6/FR-11 disagree materially;
  - model/tool failures prevent comparable evidence;
  - contract-shape differences cannot be normalized without changing semantics.
- A 2-vs-1 split is never sufficient by itself for a bias verdict.

Publication and secrets-safety:
- Publish methodology, prompts, raw artifacts, manifests, logs, statistical scripts, and adjudication summaries subject to redaction controls from S2.
- Before publication:
  - run secret scans over all prompts, transcripts, environment metadata, logs, and artifacts;
  - redact API keys, tokens, account IDs, private paths, and accidental personal data;
  - check third-party source excerpt licensing;
  - publish checksums for redacted and unredacted internal originals;
  - document all redactions.
- Do not publish unredacted provider transcripts if they contain secrets, private account data, or license-restricted source excerpts.
- Ensure redaction does not alter statistical reproducibility: numeric results, checksums for internal verification, and run metadata needed for external scrutiny must remain available where safe.

Gate:
- S7 report is final only when:
  - all required gates have passed or provisional status is explicitly labeled;
  - adjudication logs are complete;
  - publication bundle passes secrets/licensing scan;
  - remediation decisions are routed to S8 where needed.

**S8 — Remediation & re-run decision.** When bias, ambiguity, or harness/tool confound is found, patch the
seed or audit machinery and re-run the minimal affected scope.

Remediation inputs:
- S7 report;
- adjudication evidence log;
- affected `OPEN`/`FIXED` items;
- affected artifacts;
- FR-4/FR-5/FR-6/FR-11 evidence;
- reviewer remediation recommendation.

Remediation actions:
- If legitimate source ambiguity:
  - explicitly pin the behavior in the spec;
  - update S1 traceability matrix as human-adjudicated;
  - add or update mutants/assertions where applicable.
- If vendor-author bias:
  - neutralize biased phrasing or contract shape;
  - patch canonical seed/spec/harness boundary as needed;
  - add regression mutant or suite assertion where applicable.
- If tool-capability difference:
  - update prompt templates, acceptance criteria, adapters, or exclusion rules;
  - do not change benchmark semantics unless separately adjudicated.
- If harness/proto confound:
  - repair adapter policy or canonical proto boundary;
  - separate contract-shape sensitivity from primary spec-wording analysis.

Re-run scope:
- Re-run only affected gates/experiments unless the patch invalidates upstream assumptions.
- Examples:
  - brief wording patch → re-render prompts and rerun affected authoring samples;
  - mutant addition → rerun S4 suite battery;
  - canonical spec pinning → rerun affected FR-6 cells;
  - prompt-template repair → rerun affected tool/artifact sample groups.
- All remediated artifacts retain provenance linking:
  - original issue;
  - patch;
  - reviewer decision;
  - re-audit result.

Exit criteria:
- Successful remediation requires:
  - no material S4 inequivalence for remediated behavior;
  - no unresolved S5/S6 divergence for remediated behavior;
  - no FR-6 own-vendor advantage meeting the pre-specified threshold for remediated behavior;
  - reviewer sign-off.
- Run at most two remediation loops per seed.
- After two unsuccessful loops:
  - classify as ambiguous-flagged or unresolvable within pilot constraints;
  - document residual risk;
  - require explicit approval before publishing or expanding that seed.

Gate:
- S8 closes when either:
  - remediation succeeds and updated S7 verdict is issued; or
  - escalation/residual-risk decision is recorded.

**S9 — Pilot review & go/no-go decision.** Conclude the pricing-seed pilot with an explicit decision on
whether to expand the audit to additional Summer-2026 benchmark seeds.

Inputs:
- final S7 report;
- S8 remediation outcomes if any;
- residual-risk register;
- cost/time summary;
- tool-access summary;
- reviewer/adjudication summary.

Go criteria:
- S1 neutral brief creation and traceability review are feasible without relying on Claude-authored artifacts.
- S2 automation, artifact storage, and reproducibility manifests work for all authoring tools, or Antigravity manual-capture asymmetry is documented and acceptable.
- S2b acceptance/failure policies produce comparable artifact sets without excessive manual intervention.
- S3 oracle validation and mutant adequacy gates pass.
- S5/S6/S7 adjudication produces interpretable decisions with reviewer agreement or documented conflict resolution.
- FR-6 score-impact runs complete within approved cost/time budget and yield estimable interaction intervals.
- FR-11 sampling separates within-tool variance from cross-tool divergence for material artifacts.
- Final verdict is neutral, biased-and-corrected, or ambiguous-flagged with documented residual risk acceptable for expansion.

No-go / redesign triggers:
- neutral brief cannot be traced to upstream evidence;
- oracle or mutant battery cannot be independently validated;
- artifact failure rates prevent comparable analysis;
- proto/harness incompatibility dominates findings;
- FR-6 interaction uncertainty is too large for feasible interpretation;
- adjudication cannot distinguish source ambiguity, vendor-authorship bias, and tool-capability failure;
- publication/secrets/licensing constraints prevent sufficient external scrutiny.

Output:
- `bias_audit/PILOT-GO-NOGO.md` with:
  - decision;
  - rationale;
  - required changes before expansion;
  - residual risks;
  - approval owner(s);
  - next-seed readiness checklist.

## Risks

- Antigravity headless automation may not exist → fall back to documented manual capture (still reproducible
  via captured transcripts), but flag the asymmetry vs Codex.
- N must be large enough to separate author-bias from agent variance; small N → inconclusive. Budget samples.
- The brief can never be perfectly neutral; its FIXED/OPEN tagging + human review is the honesty control.
- Prompt drift can become a confound → freeze prompt-template versions, capture rendered prompts, and rerun any affected batch if the template changes midstream.
- Manual or semantic artifact repair can contaminate the experiment → only mechanical normalization is allowed; semantic fixes require rejection or remediation-loop re-run.
- Oracle or mutant weakness can create false equivalence → FR-4 conclusions are provisional until oracle validation and mutant adequacy gates pass.
- Generated proto variation can confound score-impact → primary FR-6 freezes the canonical proto; contract-shape sensitivity, if run, is separately labeled.
- Hosted model version updates can invalidate sample grouping → prefer version-locked models; otherwise split analysis by provider-reported version/timestamp and lower confidence.
- Queryable storage adds implementation overhead, but ad hoc batch directories will not scale to N-sample, mutant, remediation, and future-seed analyses.
- Raw artifact publication can leak secrets or violate source/transcript licensing → publication bundles require secret scanning, redaction logs, and third-party source excerpt review before release.
- Statistical thresholds may be underpowered in the pilot → pre-register the analysis plan, report uncertainty, and classify underpowered findings as ambiguous rather than neutral or biased.

## Appendix: Iterative Review Log (Applied / Rejected Suggestions)

This appendix is intentionally **append-only**. New reviewers (human or model) should add suggestions to Appendix C, and then once validated, record the final disposition in Appendix A (applied) or Appendix B (rejected with rationale).

### Reviewer Instructions (for humans + models)

- **Before suggesting changes**: Scan Appendix A and Appendix B first. Do **not** re-suggest items already applied or explicitly rejected.
- **When proposing changes**: Append them to Appendix C using a unique suggestion ID (`R{round}-S{n}`).
- **When endorsing prior suggestions**: If you agree with an untriaged suggestion from a prior round, list it in an **Endorsements** section after your suggestion table. This builds consensus signal — suggestions endorsed by multiple reviewers should be prioritized during triage.
- **When validating**: For each suggestion, append a row to Appendix A (if applied) or Appendix B (if rejected) referencing the suggestion ID. Endorsement counts inform priority but do not auto-apply suggestions.
- **If rejecting**: Record **why** (specific rationale) so future models don't re-propose the same idea.

### Areas Substantially Addressed

- **architecture**: 4 suggestions applied (R1-S1, R1-S4, R1-S8, R2-S2)
- **completeness**: 5 suggestions applied (R1-S9, R2-S3, R1-S2, R1-S7, R2-S2)
- **testability**: 5 suggestions applied (R1-S2, R1-S3, R1-S6, R1-S7, R2-S1)

### Areas Needing Further Review

- **architecture**: 2 accepted (R1-S1, R1-S8) — needs 1 more to reach threshold of 3
- **clarity**: 1 accepted (R1-S9) — needs 2 more to reach threshold of 3
- **maintainability**: 2 accepted (R1-S4, R2-S4) — needs 1 more to reach threshold of 3
- **scalability**: 1 accepted (R1-S5) — needs 2 more to reach threshold of 3
- **security**: 1 accepted (R1-S10) — needs 2 more to reach threshold of 3

### Appendix A: Applied Suggestions

| ID | Suggestion | Source | Implementation / Validation Notes | Date |
|----|------------|--------|----------------------------------|------|
| R1-S1 | Add an explicit workflow architecture with phase gates, deliverables, owners, dependencies, and downstream consumers for S1 through S7. | gpt5.5 (gpt-5.5) | The plan currently lists activities but not gating criteria, and the requirements demand validated briefs, artifacts, oracles, mutants, and manifests before later analyses consume them. | 2026-06-17 20:33:41 UTC |
| R1-S2 | Expand S1 with the FR-1 source-to-brief traceability matrix, citation requirements, admissibility rationale, reviewer sign-off, and leakage checklist. | gpt5.5 (gpt-5.5) | The neutral brief is the root of trust for the audit, and the plan must explicitly cover the traceability and human-review controls required by FR-1. | 2026-06-17 20:33:41 UTC |
| R1-S3 | Add a standardized prompt-template package with versioning, rendered-prompt capture, parameter capture, and few-shot/scaffolding policy. | gpt5.5 (gpt-5.5) | Equivalent prompting is necessary to avoid prompt drift as a confound, and FR-1b requires prompt-template control and capture across tools. | 2026-06-17 20:33:41 UTC |
| R1-S4 | Define artifact intake, normalization, repair, retry, and rejection policies before generated artifacts enter downstream analyses. | gpt5.5 (gpt-5.5) | Without consistent intake rules, malformed or manually repaired artifacts could contaminate FR-4, FR-5, and FR-6; this directly implements FR-3a and FR-3b. | 2026-06-17 20:33:41 UTC |
| R1-S5 | Specify the reproducibility substrate, including locked runtimes, storage layout, manifests, checksum policy, retry logs, and model-version update policy. | gpt5.5 (gpt-5.5) | The plan’s durable-capture language is insufficient for reproducibility and external scrutiny, while FR-3 requires concrete runtime, dependency, manifest, retry, and model-version controls. | 2026-06-17 20:33:41 UTC |
| R1-S6 | Add explicit oracle validation and mutant adequacy gates before FR-4 equivalence results are trusted. | gpt5.5 (gpt-5.5) | The suite-bias experiment depends on a correct oracle and discriminating mutants, so FR-4 and FR-12 gates must be explicit before any equivalence conclusions are accepted. | 2026-06-17 20:33:41 UTC |
| R1-S7 | Pre-register the statistical analysis plan for FR-4, FR-5, FR-6, and FR-11, including metrics, sample sizes, uncertainty, multiplicity, and bias thresholds. | gpt5.5 (gpt-5.5) | The plan references statistical concepts but lacks decision rules; pre-registration is required to distinguish bias from run variance and to satisfy FR-6 and FR-11. | 2026-06-17 20:33:41 UTC |
| R1-S8 | Make the frozen canonical proto policy and adapter workflow explicit, separating primary spec-wording score-impact from optional contract-shape sensitivity analysis. | gpt5.5 (gpt-5.5) | Generated proto differences would confound FR-6 unless the canonical-proto policy, adaptation logging, and contract-shape sensitivity separation are made explicit. | 2026-06-17 20:33:41 UTC |
| R1-S9 | Define the human adjudication workflow, blinding protocol, reviewer roles, decision labels, verdict criteria, and remediation exit criteria. | gpt5.5 (gpt-5.5) | The plan mentions attribution and remediation but does not operationalize FR-7, FR-8, or FR-9 decision-making, which is necessary for credible bias classification. | 2026-06-17 20:33:41 UTC |
| R1-S10 | Add a publication and secrets-safety policy for raw prompts, outputs, transcripts, environment metadata, and source excerpts. | gpt5.5 (gpt-5.5) | The plan’s raw artifact publication goal creates leakage and licensing risks, so a redaction and scanning policy is needed without weakening reproducibility. | 2026-06-17 20:33:41 UTC |
| R2-S1 | Add explicit validation steps for the oracle and mutant battery as a dedicated gate before downstream FR-4 use. | gemini-2.5 (gemini-2.5-pro) | Although the exact placement should follow artifact construction rather than precede it, the core requirement is valid and duplicates the need to budget and gate oracle and mutant validation explicitly. | 2026-06-17 20:33:41 UTC |
| R2-S2 | Add an explicit remediation and re-run decision step to model the FR-9 loop. | gemini-2.5 (gemini-2.5-pro) | S7 currently treats re-audit as a report outcome rather than a workflow branch, while FR-9 requires explicit patching, re-running, exit criteria, and escalation behavior. | 2026-06-17 20:33:41 UTC |
| R2-S3 | Add a final pilot review and go/no-go decision step for expansion beyond the pricing seed. | gemini-2.5 (gemini-2.5-pro) | FR-13 requires the pilot to conclude with an explicit expansion decision, and the current plan stops at reporting without formal go/no-go criteria. | 2026-06-17 20:33:41 UTC |
| R2-S4 | Use a structured, queryable result store or equivalent indexed manifest system for raw and processed audit data. | gemini-2.5 (gemini-2.5-pro) | N-sample runs, mutant matrices, remediation loops, and future seed expansion will be difficult to analyze from an ad hoc batch directory alone; the implementation can remain flexible between SQLite, Parquet, or manifest-indexed files. | 2026-06-17 20:33:41 UTC |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| R2-S5 | Formalize all audit tooling into a single modular CLI application. | gemini-2.5 (gemini-2.5-pro) | A unified CLI could improve ergonomics later, but it is not required to satisfy the audit requirements and risks over-scoping the pilot compared with modular scripts plus shared libraries and manifests. | 2026-06-17 20:33:41 UTC |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1

- **Reviewer**: gpt5.5 (gpt-5.5)
- **Date**: 2026-06-17 20:30:37 UTC
- **Scope**: Architecture-focused review

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-S1 | Architecture | High | Add an explicit audit workflow architecture with phase gates, inputs, outputs, owners, and blocking dependencies for S1 through S7. | The plan lists steps, but it does not define which artifacts must be accepted before downstream work can proceed. Without gates, FR-4, FR-6, and FR-8 can accidentally consume unvalidated briefs, oracles, mutants, or generated artifacts. | Add a short 'Workflow gates and deliverables' section before 'Step-by-step'. | Verify every step has declared input artifacts, output artifacts, acceptance gates, and downstream consumers in a machine-checkable manifest. |
| R1-S2 | Completeness | High | Expand S1 to require the FR-1 source-to-brief traceability matrix, including citations, FIXED/OPEN admissibility rationale, and a human leakage-review checklist. | The plan mentions FIXED/OPEN tagging and human review but omits the traceability mechanism that makes the neutral brief auditable. This is central because the brief is the experiment's root of trust. | Under S1, add sub-bullets for traceability matrix fields, citation requirements, reviewer sign-off, and leakage checklist. | Sample each FIXED and OPEN brief item and confirm it traces to upstream Liferay evidence, seed-schema constraints, or an explicit human judgment. |
| R1-S3 | Testability | High | Add a standardized prompt-template package with versioning, rendered-prompt capture, parameter capture, and few-shot/scaffolding policy. | S2 captures prompts but does not ensure all tools receive equivalent instructions. Prompt drift is an experimental confound and directly affects reproducibility and author-vendor attribution. | Extend S2 with a 'prompt template and run configuration' deliverable. | Diff rendered prompts across Claude, Codex, and Antigravity and confirm differences are limited to declared invocation mechanics. |
| R1-S4 | Maintainability | High | Define artifact intake, normalization, repair, retry, and rejection policy before generated artifacts enter S4, S5, or S6. | The plan does not state how malformed specs, non-running suites, non-compiling protos, or partial outputs are handled. Inconsistent human repair would contaminate bias conclusions. | Add a new step between S2 and S3, or expand S2 as 'S2b — Artifact intake and normalization'. | Run seeded invalid artifacts through the intake pipeline and confirm semantic repairs are rejected while mechanical formatting fixes are logged. |
| R1-S5 | Scalability | Medium | Specify the reproducibility substrate: container images, locked dependency versions, storage layout, run manifests, checksum policy, retry logs, and model-version update policy. | The plan says runs are durable and reproducible but omits the concrete infrastructure needed to scale beyond the pricing pilot and to support external scrutiny. | Expand S2 and Risks with a 'reproducibility baseline' subsection. | Re-run one full authoring sample and one mutant-suite execution from only the manifest and stored artifacts on a clean machine. |
| R1-S6 | Testability | Critical | Add explicit oracle validation and mutant adequacy gates before FR-4 equivalence results are trusted. | S3 proposes a known-correct oracle and mutants, but if the oracle encodes Claude choices or the mutant battery has equivalent/invalid mutants, the main suite-bias experiment can produce false confidence. | Expand S3 with 'oracle provenance gate' and 'mutant adequacy gate'. | Require oracle evidence logs, reviewer sign-off, mutant manifests, expected kill matrix, calibration weak suite, and proof each mutant differs from the oracle on at least one targeted probe. |
| R1-S7 | Completeness | High | Pre-register the statistical analysis plan for FR-4, FR-5, FR-6, and FR-11, including metrics, N, uncertainty estimates, multiplicity handling, and bias-call thresholds. | The plan references pass/fail vectors, equivalence matrices, N samples, and model×spec interactions, but does not define the statistical decision rules needed to separate author bias from run variance. | Add a new 'Analysis plan' section after S6 or before S7. | Use synthetic data with known injected suite blind spots and own-vendor advantages to confirm the analysis scripts recover expected decisions. |
| R1-S8 | Architecture | High | Make the frozen canonical proto policy and adaptation workflow explicit in S5, and separate primary spec-wording score-impact from optional contract-shape sensitivity analysis. | The plan says spec-author bias is isolated, but it still mentions proto/spec divergences without defining how generated protos are prevented from confounding FR-6. | Expand S5 and S6 with a 'canonical proto and adapter policy' subsection. | For each generated spec/proto pair, confirm whether it is scored against the frozen proto, cataloged only as a divergence, or routed to separately labeled contract-shape sensitivity analysis. |
| R1-S9 | Clarity | Medium | Define the human adjudication workflow, blinding protocol, reviewer roles, decision labels, verdict criteria, and remediation exit criteria. | S6 and S7 mention attribution, verdicts, and remediation, but the plan does not specify how reviewers decide between source ambiguity, tool-capability failure, and vendor-author bias. | Expand S6 and S7 with adjudication and remediation sub-bullets. | Dry-run adjudication on at least three mock divergences: one source ambiguity, one malformed artifact, and one stable semantic author choice. |
| R1-S10 | Security | Medium | Add a publication and secrets-safety policy for raw prompts, outputs, transcripts, environment metadata, and third-party source excerpts. | The plan emphasizes durable raw capture and external scrutiny, but raw artifacts may contain API metadata, secrets, proprietary paths, credentials, or licensed source snippets. A redaction policy is needed without undermining reproducibility. | Add to S2 and S7, with cross-reference from Risks. | Run an automated secret scan and license/source-disclosure review on the batch directory before report publication. |

#### Review Round R2

- **Reviewer**: gemini-2.5 (gemini-2.5-pro)
- **Date**: 2026-06-17 20:32:06 UTC
- **Scope**: Architecture-focused review

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R2-S1 | Testability | Critical | Add explicit validation steps for the oracle and mutant battery. Before S3, insert a new step `S2.5 — Oracle and Mutant Validation`. | The entire audit's validity hinges on a correct oracle and a discriminating mutant battery (FR-4, FR-12). The current plan creates these artifacts (S3) but does not explicitly budget time or process for validating them. An invalid oracle or a weak mutant set would invalidate all subsequent findings. This step should explicitly implement the oracle validation and mutant adequacy gates defined in FR-4 and FR-12. | Between S2 and S3 | N/A |
| R2-S2 | Completeness | High | The plan's flow is linear (S1-S7), but FR-9 requires a remediation loop. Add a new step `S8 — Remediation & Re-run Decision` to explicitly model this loop. | The current S7 mentions 're-audit' as an afterthought. A key part of the process is deciding *what* to do based on the findings. This new step would formalize the decision gate: based on the divergence catalog (S6) and adjudication, does the process terminate (report neutral/ambiguous) or loop back to S4/S5 with a patched seed/brief? This makes the plan's workflow accurate and directly implements FR-9. | After S7 | N/A |
| R2-S3 | Completeness | High | Add a final step `S9 — Pilot Review & Go/No-Go Decision` to explicitly address FR-13. | The plan successfully executes the audit but stops at reporting (S7). The strategic purpose of the pilot is to decide whether to expand the audit. This step ensures the project concludes by formally evaluating the pilot against the success criteria in FR-13, producing the go/no-go decision as a key deliverable. | After S8 (or S7 if no remediation is needed) | N/A |
| R2-S4 | Maintainability | Medium | Instead of a 'durable batch dir' (S2), specify a structured, queryable data store (e.g., SQLite database or a set of versioned Parquet files) for all raw and processed results. | While a directory structure is sufficient for a single pilot run, it does not scale. A structured data store will be essential for managing N samples, multiple remediation loops, and future expansion to other seeds. It simplifies programmatic analysis (S5, S6), ensures traceability between prompts, artifacts, and results, and makes the entire process more robust and maintainable. | In S2 — Reproduction harness | N/A |
| R2-S5 | Architecture | Medium | Formalize the tooling described in the plan into a single, modular CLI application. | The plan implies a series of standalone scripts (`run_bias_reproduction.py`, etc.). This can lead to code duplication and operational complexity. A unified CLI (e.g., `bias-audit run-authoring`, `bias-audit analyze`, `bias-audit report`) would provide a consistent interface, simplify configuration management (like Doppler keys), and make the overall process more robust, testable, and easier to integrate into CI/CD. | In S2 — Reproduction harness | N/A |
| R2-S6 | Completeness | High | This meta-suggestion provides the required feature requirement feedback and coverage matrix, which do not fit elsewhere in the structured JSON format, to satisfy the dual-document review prompt.

#### Feature Requirements Suggestions

\| ID \| Req \| Severity \| Suggestion \|
\|---\|---\|---\|---\|
\| R2-F1 \| FR-6 \| Low \| Add a plain-English explanation or a small, illustrative example for the `OVA_v` (Own-Vendor Advantage) formula. The current statistical definition is precise but not intuitive, making the results harder for a broader audience to interpret. \|
\| R2-F2 \| FR-2b \| Medium \| Clarify the policy for generated specs that are semantically inseparable from their co-generated (non-canonical) protos. If these are excluded from the FR-6 score-impact analysis, the audit may be blind to a significant form of author-bias expressed through contract shape. The requirement should specify if/how such specs can be adapted or analyzed. \|
\| R2-F3 \| FR-9 \| Medium \| Define the "escalation" process. If remediation fails after two loops, the requirement states the issue is escalated, but it does not specify to whom, what the expected outcome is, or how that process is managed. \|
\| R2-F4 \| FR-13 \| High \| Add a *results-oriented* pilot success criterion. The current criteria are process-focused (e.g., "is it feasible"). A criterion like "The pilot produces a definitive verdict (Neutral, Biased-and-corrected, or Ambiguous-flagged with specific, bounded risks) for the pricing seed" would ensure the process is not just runnable but also conclusive. \|
\| R2-F5 \| FR-3b \| Medium \| The policy on catastrophic failures should specify how these failures are weighted in the overall verdict. For example, if one tool consistently fails to generate a valid suite, is that just a tool-capability issue, or is it a form of bias (i.e., the task is structured in a way only some tools can handle)? The attribution rubric in FR-7 should explicitly address this. \|

<br>

#### Requirements Coverage

\| Feature Requirement \| Plan Step(s) \| Coverage \| Gaps & Comments \|
\|---\|---\|---\|---\|
\| FR-1 (Brief) \| S1 \| Full \| The plan correctly identifies this as the foundational first step. \|
\| FR-2 (Factored Exp) \| S4, S5 \| Full \| The plan correctly separates the experiments into suite-author (S4) and spec-author (S5) biases. \|
\| FR-3 (Reproducibility) \| S2 \| Partial \| S2 sets up the harness, but the plan lacks explicit handling for the artifact acceptance/failure policies from FR-3a/3b. \|
\| FR-4 (Equivalence) \| S4 \| Partial \| The plan uses the mutant battery but lacks the explicit, upfront *oracle validation* step required by FR-4 before the battery can be trusted. \|
\| FR-5 (Divergence) \| S6 \| Full \| S6 directly implements the divergence catalog requirement. \|
\| FR-6 (Score-impact) \| S5 \| Full \| S5 correctly plans for the model×spec interaction analysis. \|
\| FR-7 (Attribution) \| S6, S7 \| Partial \| The plan creates the inputs for adjudication (S6) and reports on it (S7), but the crucial *process* of human adjudication is implicit. An explicit analysis/adjudication step is needed. \|
\| FR-8 (Report) \| S7 \| Full \| S7 is dedicated to producing the final report. \|
\| FR-9 (Remediation) \| S7 \| Partial \| The plan mentions 're-audit' in S7 but lacks an explicit step for the remediation loop itself. The current plan flow is linear. \|
\| FR-10 (Provenance) \| S7 \| Partial \| S7 implies a report, but doesn't explicitly commit to publishing methodology and raw artifacts for scrutiny as required. \|
\| FR-11 (Sampling) \| S2, S4, S5 \| Full \| The plan correctly incorporates the need for N samples in the core experiment steps. \|
\| FR-12 (Mutant Battery) \| S3, S4 \| Partial \| S3 creates the mutants, but the plan lacks an explicit step for the *mutant adequacy* gate from FR-12 to ensure the battery is sufficiently discriminating. \|
\| FR-13 (Go/No-Go) \| None \| None \| The plan produces a report but lacks a final step to evaluate the pilot's success and make the strategic go/no-go decision for expansion. \| | This meta-suggestion provides the required feature requirement feedback and coverage matrix, which do not fit elsewhere in the structured JSON format. It addresses meta-level review completeness by linking the implementation plan back to the requirements document. | N/A | N/A |
