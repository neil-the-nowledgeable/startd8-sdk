# Google Gemini & Antigravity Differential Bias Audit — Requirements

**Version:** 1.0 (Google/Antigravity Bias Focus)  
**Date:** 2026-06-18  
**Status:** Draft (customized for Gemini & Antigravity ecosystem)  
**Plan:** `ANTIGRAVITY_GEMINI_BIAS_AUDIT_PLAN.md`  
**Scope:** Detect and quantify Google Gemini & Antigravity-authorship bias in the Summer-2026 benchmark **inputs**, by
independently re-authoring them with Anthropic **Claude Code** and OpenAI **Codex CLI** and running two
differential tests. Pilot on the Liferay-derived **pricing seed**.

---

## 0. Strategic Context (Google & Antigravity Focus)

This document establishes the requirements for auditing systemic bias introduced when benchmark artifacts are authored using Google's suite of developer agent tools—specifically, the **Google Gemini CLI** (headless automation) and the **Antigravity IDE Agent** (interactive pair-programming assistant). 

As benchmarks are increasingly constructed with the aid of agentic coding tools, there is a substantial risk that the generated specifications, schema contracts, and validation test suites inherit vendor-specific idiosyncrasies, default behaviors, and stylistic structures. If a benchmark's inputs are inherently tailored to one vendor's model characteristics, the benchmark results are compromised. This audit seeks to isolate, measure, and remediate Google-authorship bias to ensure cross-vendor evaluation integrity.

---

## 1. Problem Statement

The benchmark compares models across multiple vendors (Anthropic, OpenAI, Google), but its initial input artifacts and infrastructure for the evaluated capabilities are authored primarily using Google's models and developer tools (Gemini and Antigravity): the seed `.proto` contracts, the `requirements_text` spec, and the ground-truth validation suites. This creates a systematic-bias surface:
* **Gemini/Antigravity-authored phrasing** in requirements prose may be structurally and syntactically easier for Google models to parse and satisfy.
* **gRPC contract shapes** (`pricing.proto`) may align with Google-specific code generation patterns.
* **Suite expectations** (`pricing_suite.py`) may reflect Gemini/Antigravity's specific interpretations of ambiguous upstream business logic.

This is the most critical threat to the validity of the published benchmark ("the benchmark authors used Google tools to write the tests, favoring Google models").

**Mitigation:** Independently re-author the same input artifacts using Anthropic **Claude Code** and OpenAI **Codex CLI** starting from a strictly neutral source brief. By comparing these independent artifacts, we measure:
1. **Input-Equivalence (FR-4):** Do the independently-authored suites agree on behavior?
2. **Score-Impact (FR-6):** Does swapping the authoring specs change evaluated model rankings via a vendor-model-by-spec interaction?

| Input artifact (pricing seed) | Primary Author | Bias risk |
|---|---|---|
| `pricing.proto` (contract) | Google Gemini / Antigravity | Shape, type, or package choices favor Gemini/Antigravity idioms |
| `requirements_text` (spec) | Google Gemini / Antigravity | Prose phrasing/structure easier for Google models to satisfy |
| `pricing_suite.py` (ground truth) | Google Gemini / Antigravity | Interpretation of edge cases (rounding, precedence) is Google-specific |

### 1.1 Terminology

| Term | Meaning in this audit |
|---|---|
| **Vendor** | The organization associated with an authoring tool or evaluated model family: Google, Anthropic, or OpenAI. |
| **Authoring tool** | The tool/agent used to generate benchmark input artifacts: Google Gemini CLI, Google Antigravity IDE, Anthropic Claude Code, or OpenAI Codex CLI. |
| **Author** | A concrete authoring run: `{tool, model/version, prompt template, parameters, timestamp, sample index}`. “Gemini-authored” or “Antigravity-authored” refers to Google provenance. |
| **Evaluated model** | A model scored on the benchmark task in FR-6. The evaluated model may share a vendor with an authoring tool (e.g., scoring Gemini 1.5 Pro on Gemini-authored specs), but remains a distinct experimental subject. |
| **Author-vendor** | The vendor associated with the tool that generated a spec, proto, or suite artifact (e.g., Google for Gemini-authored specs). |
| **Model-vendor** | The vendor associated with the evaluated model whose benchmark score is measured. |
| **Vendor-authorship bias signal** | Evidence that artifacts authored by a vendor’s tool systematically favor evaluated models from that same vendor, after accounting for artifact quality and run variance. |
| **Tool-capability difference** | Divergence caused by a tool failing to follow instructions, compile artifacts, use required formats, or complete the task, rather than by a stable semantic preference attributable to vendor authorship. |
| **Material** | Meeting a pre-declared threshold: an FR-6 own-vendor advantage ≥ 5 pts / ≥ 0.5 pooled SD, or an FR-11 tool-level choice stable at ≥ 80% of accepted samples. |
| **Spec / Proto / Oracle-harness** | Three distinct artifacts kept separate throughout: the *spec* (prose task description), the *proto* (gRPC contract), and the *oracle/harness* (known-correct reference server + runner). Never abbreviate in a way that blurs them. |
| **Reviewer sign-off** | A record carrying reviewer ID/role, blinding status, evidence reviewed, decision/label, rationale, and date — the common shape used by FR-4 oracle validation, FR-7 adjudication, FR-9 remediation, and FR-12 mutant review. |

---

## 2. Requirements

### FR-1 — Neutral Task Brief (FIXED/OPEN tagged)
Author a vendor-agnostic task brief describing the pricing capability from the upstream source (Liferay pricing capability + the bare benchmark seed-contract schema), NOT from Gemini/Antigravity's existing artifacts. Tag each requirement:
* **FIXED:** A true contract constraint (e.g., single RPC, decimal-string representation for money, gRPC transport, seed JSON schema shape).
* **OPEN:** A semantic choice under test (e.g., default rounding modes, chaining vs. additive discount calculations, basis calculation for fixed-amounts, tax/discount ordering, error code taxonomy, field naming conventions).

The neutral brief must not leak Gemini/Antigravity’s resolutions of any OPEN items. Human reviewers must scan the brief for **Google-idiom leakage** (verbatim field names, Google-characteristic phrasing, default resolutions from the seed repository). 

Because a Google/Gemini self-review cannot reliably catch its own idioms, the brief must be cross-reviewed by the non-Google authoring CLIs (**Claude Code** and **Codex CLI**) before driving any authoring run.

The brief must include a **source-to-brief traceability matrix** recording:
1. Brief Item ID
2. FIXED/OPEN status
3. **Decision-owner** (`source-evidence` | `schema-constraint` | `human-adjudication`)
4. Upstream citation / rationale
5. Verification that FIXED items are not author choices, and OPEN items are not pre-resolved by Google.

### FR-1b — Standardized Prompt Template
All authoring tools must receive prompts generated from a single controlled, versioned template that separates:
* The FR-1 neutral brief.
* Experiment-specific instructions (suite-only or spec-only).
* Allowed and forbidden dependencies.
* Output formatting and file conventions.
* Tool-specific invocation mechanics (e.g., path mapping, CLI parameters).
* Few-shot examples (which must be vendor-neutral, encode no OPEN resolutions, and remain identical across tools except for syntax requirements).

### FR-2 — Factored Re-Authoring (No Conflation)
Re-authoring decomposes into two isolated experiments to prevent the conflation of spec-bias and suite-bias:
* **FR-2a — Suite-author experiment:** Hold the spec FIXED (Google/Gemini's original spec), and have each authoring tool author only the **ground-truth suite**.
* **FR-2b — Spec-author experiment:** Hold the behavior/oracle FIXED, and have each tool author only the **spec** from the neutral brief. Proto generation is collected as a secondary artifact but is not automatically used in FR-6 score-impact runs.

Each experiment includes a Google/Gemini control run for symmetry. Each run is labeled with `author-vendor`, `tool`, `model/version`, `sample index`, `template version`, and `timestamp`.

### FR-3 — Automatable, Reproducible Runs
Authoring runs must drive external agentic CLIs by subprocess: **Google Gemini CLI**, **Anthropic Claude Code**, and **OpenAI Codex CLI** (`codex exec` non-interactive mode). Raw outputs, prompts, parameters, and tool versions must be captured in the audit store.
* **Google Antigravity IDE Integration:** Because Antigravity is an interactive, developer-in-the-loop IDE agent, headless automation is not natively supported. To integrate Antigravity into the audit:
  1. Define a strict, scripted prompting protocol mimicking the CLI templates.
  2. Execute the protocol manually inside the IDE, recording the session.
  3. Export and checksum the raw generated files and interactive transcripts.
  4. Catalog these runs as `tool: antigravity-ide` with manual-capture metadata, and analyze them alongside the automated CLI runs to observe interactive vs. automated bias.

**Reproducibility Baseline:**
* Locked runtimes/containers (Python, Node, gRPC compiler, protobuf version, and locked package managers).
* Dependency lockfiles with checksum/commit pinning.
* API execution parameters (temperature, top-p, max tokens, seeds where available).
* Machine-readable manifest (`schema_version` controlled) mapping source citation → FR-1 matrix row → rendered prompt → raw output → normalized artifact → analysis.
* **Model-update policy:** Lock model versions. If a hosted provider updates a model mid-experiment, restart the batch or separate the data points, flagging cross-version comparisons as low-confidence.

### FR-3a — Artifact Acceptance Criteria
Artifacts must pass automatic intake checks before entering downstream analysis:
* **Specs:** Standard Markdown, sufficient to implement the server against the canonical proto, no Google/Gemini private repository dependencies.
* **Protos:** Valid syntax, compiles under the locked protobuf compiler, defines the required pricing service.
* **Suites:** Harness-compatible, runs under the locked test runner, executes against the reference oracle/mutants within execution timeouts, uses approved dependencies only.
* **Normalization Rules:** Only mechanical formatting, file renaming, or import path alignment are permitted via predefined scripts. Semantic repairs (e.g., expected value adjustments, assertion overrides) are strictly forbidden; failing files are rejected.

### FR-3b — Catastrophic Generation Failure Policy
A generation is catastrophic if it is syntactically invalid, fails to compile/run, or misses the majority of requirements.
* Allow $\le 1$ automated retry for truncation or formatting limits.
* If it still fails, log the raw output and category.
* Exclude from semantic bias comparisons, but count it toward `tool-capability` metrics and FR-11 variance.
* If a failure mode is consistent and vendor-specific (e.g., only Claude Code fails to parse the Google seed constraints), route to FR-7 to adjudicate if the failure is **authorship-relevant** (reflecting a structural task-comprehension gap) rather than a transient tool error.

### FR-4 — Input-Equivalence via Mutant Battery
Cross-validate the FR-2a suites against the known-correct Node oracle **plus a battery of mutant servers** (FR-12). Two suites are equivalent if and only if they produce the same pass/fail vector across the entire mutant battery. A suite that misses a mutant others catch reveals a tool-specific blind spot (localized to the missing assertion).

**Oracle Provenance & Validation:**
* The reference Node oracle must have documented provenance (original author, any Gemini/Antigravity-derived logic).
* Gemini-derived logic must undergo independent, non-Google review and reimplementation before serving as the ground-truth anchor.
* Document validations against the FR-1 matrix and Liferay source (not just Gemini's spec).
* Require sign-off from $\ge 2$ reviewers (one blinded) verifying the oracle does not merely encode Google-specific conventions.

### FR-5 — Spec/Contract Divergence Catalog
Diff the FR-2b specs and protos for semantic divergences (rounding, tax ordering, error codes, naming).
* Classification Rubric:
  1. **Legitimate source-ambiguity:** The source code/brief allows multiple interpretations.
  2. **Author-specific choice:** Resolves an OPEN item not forced by the source, stable across samples.
  3. **Schema constraint:** Required by the seed contract (should have been FIXED).
  4. **Tool-capability artifact:** Incomplete or malformed output.
  5. **Human-adjudicated correction:** Reviewers pin the behavior.
* Traceability: Every material divergence must trace back to at least one OPEN item in the FR-1 matrix. If a divergence appears without an OPEN item, the FR-1 brief must be revised.

### FR-6 — Score-Impact via Model $\times$ Spec Interaction
Evaluate evaluated models (Gemini flagship, Claude flagship, GPT flagship) against each spec variant (Gemini-authored, Claude-authored, Codex-authored), keeping the proto and test harness frozen. The bias signal is **not** a uniform shift in scores (which measures spec clarity/quality), but the **two-way interaction**: a model scoring relatively higher under its own vendor's spec.

**Primary Analysis Model:**
* Linear mixed-effects model (continuous scores) or generalized mixed-effects (binary pass/fail), with fixed effects for `model-vendor` + `spec-author-vendor` + `interaction`, and random effects for `run-index` and `test-case`.
* Paired bootstrap/permutation check over run indices for non-parametric validation.
* **Interaction Metric:** Own-Vendor Advantage ($OVA$) for Google ($OVA_{google}$):
  $$OVA_{google} = [S(\text{model}_{google}, \text{spec}_{google}) - \text{mean}_{a \ne google} S(\text{model}_{google}, \text{spec}_a)] - \text{mean}_{u \ne google} [S(\text{model}_u, \text{spec}_{google}) - \text{mean}_{a \ne google} S(\text{model}_u, \text{spec}_a)]$$
  where $S(m, s)$ is the mean score of model $m$ on spec $s$.
* **Bias Threshold:** $OVA_{google}$ interval must exclude zero, with $|OVA_{google}| \ge 5$ points or $\ge 0.5$ pooled within-cell standard deviation.
* Apply Holm-Bonferroni correction over the three vendor tests.

### FR-7 — Attribution via Unanimity Rule
Unanimous agreement across all three author-vendors' stable choices ($\ge 80\%$ of accepted samples) designates an input as **neutral** (the strongest signal). Any divergence (including a 2-vs-1 split where Claude and Codex agree but Gemini/Antigravity diverges) is a **flag for human adjudication**, not an automatic bias verdict.

**Adjudication Protocol:**
* $\ge 2$ domain experts, blinded to author-vendor labels where practical (impractical if comments, field structures, or formatting identify the tool; record justifications).
* Assign one label: `neutral/unanimous`, `source-ambiguity`, `vendor-author-bias-candidate`, `tool-capability-difference`, `harness/proto-confound`, or `insufficient-evidence`.
* Disagreements are resolved by a third reviewer. Log reviewer IDs, blinding, rationale, and remediation.

### FR-8 — Bias-Audit Report
Generate a report containing:
* Equivalence matrices, divergence catalogs, and score-impact interaction deltas ($OVA$).
* Traceability maps to the FR-1 brief.
* Confidence/credible intervals and statistical significance.
* Machine-readable **remediation-candidate IDs** for the FR-9 loop.
* **Verdict Rubric:**
  * **Neutral:** FR-1 passes; S4 suites equivalent (or differences non-semantic); no unresolved material FR-5 divergences; no $OVA$ exceeding the bias threshold; FR-11 cross-tool variance $\le$ within-tool variance.
  * **Biased-and-corrected:** At least one material divergence/interaction is adjudicated as vendor-author bias, a remediation ID is issued, the fix is applied, and the re-audit meets the Neutral criteria.
  * **Ambiguous-flagged:** Conflict of signals, unpinned source-ambiguity, statistical power insufficient, or unnormalizable confounds. (This is the default when signals conflict).

### FR-9 — Remediation Loop
When bias is identified:
* Issue a remediation (neutralize phrasing, pin behavior in the spec, or update mutant coverage).
* Apply the patch. When a previously-OPEN item is pinned, promote it to **adjudicated-FIXED** in the traceability matrix (preserving the original neutral brief for auditability).
* Run the re-audit. Success is achieved when the re-audited scope shows no material inequivalence and no $OVA$ exceeding the threshold.
* Limit to **at most two remediation loops**. If unresolved after two loops, classify as `ambiguous-flagged / unresolvable-within-pilot`.

### FR-10 — Honest Provenance
Acknowledge that Claude Code and Codex carry their own vendor biases; the method relies on triangulation rather than a bias-free oracle. Publish raw artifacts, manifests, prompts, run logs, and statistical scripts for public review.

### FR-11 — Sampling for Non-Determinism
Take $N$ samples per tool per artifact ($N \ge 3$ for the pilot, $N \ge 5$ preferred for final claims).
* Run permutation tests to compare between-tool divergence against within-tool dispersion.
* A choice is stable only if it appears in $\ge 80\%$ of a tool's accepted samples.
* A difference is a bias candidate only if the tool's stable choice differs from another's, and the between-tool distance CI excludes zero.

### FR-12 — Mutant Reference Battery
Maintain a Node reference oracle plus $K$ mutant servers injecting semantic faults (e.g., inverted caps, wrong rounding, float math bugs, ordering errors).
* Adequacy Criteria: Cover every material OPEN dimension with $\ge 1$ mutant ($\ge 2$ for high-risk rounding/ordering/caps).
* Mutants must be single-fault only.
* Exclude equivalent mutants (indistinguishable from the oracle) and invalid mutants (crashing gRPC channels).
* **Adequacy Gate:** The battery must prove it can kill weak calibration suites while letting the oracle pass all tests. FR-4 results are provisional until this gate passes.

### FR-13 — Pilot Success Criteria & Go/No-Go
The pricing-seed pilot determines whether to expand the audit to the full Summer-2026 benchmark.
* **Go:** If FR-1 brief creation is feasible without Google artifacts; FR-3 subprocess automation + Antigravity manual integration are reliable; intake filters work; S3 gates pass; statistical power is sufficient to isolate $OVA$; and a definitive FR-8 verdict is reached.
* **No-go:** If brief depends on Google source, oracle/mutants fail validation, or model update churn prevents batch consistency.

---

## 3. Non-Requirements

* **No SDK Rewrite:** We are not rewriting the startd8 SDK scoring logic.
* **No SDK-level Authoring:** The subprocess runs do NOT use the SDK provider layer to generate code (which would inject SDK harness bias). The SDK is used strictly as a downstream runner for FR-6 scoring.
* **No Automatic Code Repair:** We do not automatically patch or repair compilation errors in generated suites using another LLM pass; non-compiling artifacts are cataloged as tool-capability failures.

---

## 4. Open Questions

* **OQ-1 → resolved:** The SDK is a readily observable application with a low likelihood of systemic bias. Thus, interactive calibration should be thoughtful without being excessively rigid.
* **OQ-2 → resolved:** Keep model versions strictly locked throughout the audit.
* **OQ-3 → resolved:** Tampering and access risks are low; if needed, isolate credentials and runs in a separate folder/location to minimize risk.

