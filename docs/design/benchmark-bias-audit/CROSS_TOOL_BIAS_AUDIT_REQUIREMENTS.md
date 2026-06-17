# Cross-Tool Differential Bias Audit — Requirements

**Version:** 0.4 (Review-integrated, trimmed for pilot density)  
**Date:** 2026-06-17  
**Status:** Draft (planning-corrected; pre-implementation)  
**Plan:** `CROSS_TOOL_BIAS_AUDIT_PLAN.md`  
**Scope:** Detect and quantify Anthropic-authorship bias in the Summer-2026 benchmark **inputs**, by
independently re-authoring them with OpenAI **Codex** and Google **Antigravity** and running two
differential tests. Pilot on the Liferay-derived **pricing seed**.

---

## 0. Planning Insights (Self-Reflective Update)

> What changed between v0.1 and v0.2 after planning the experiment. The planning pass produced 6
> corrections; two reshape the experimental design.

| v0.1 Assumption | Planning Discovery | Impact |
|---|---|---|
| Re-author all 3 artifacts at once, then diff | **Conflates spec-bias and suite-bias** (the suite's values depend on the spec's choices). | **FR-2 refactored to a *factored* design** (Exp-A: fix spec, vary suite; Exp-B: fix behavior, vary spec). New FR-2a/2b. |
| Equivalence = suites agree on the correct oracle | A correct oracle barely discriminates — almost any plausible suite passes. | **FR-4 now uses a mutant battery** (new FR-4 + FR-12). Resolves OQ-3. |
| Score-impact = does swapping spec change scores | Confounded by spec *quality* (uniform shifts ≠ bias). | **FR-6 now tests the model×spec *interaction*** (each vendor's model relatively favored by its own vendor's spec). |
| One sample per tool | Agents are non-deterministic; 1 sample conflates bias with run-variance. | **New FR-11: N samples per tool**, statistical divergence. Resolves OQ-5. |
| "Neutral brief" is straightforward | The brief is the crux; deriving it from Claude's doc pre-injects bias. | **FR-1 sharpened**: derive from Liferay source + bare contract schema; tag each item FIXED vs OPEN. |
| Triangulation: agree=neutral, diverge=bias | 2-vs-1 splits are ambiguous (could be Claude-bias or a shared non-Claude convention). | **FR-7 now requires unanimity** for a neutrality verdict; majority is a flag, not proof. |

**Resolved open questions:**
- **OQ-3 → mutant battery** (FR-12): equivalence is measured against the oracle *plus* K deliberately-buggy servers.
- **OQ-5 → sample, don't force determinism** (FR-11): N samples per tool; treat divergence statistically.
- **OQ-1 / OQ-2 / OQ-4** remain open as implementation/calibration items (auth wiring, brief neutrality review, score-impact spend) — see §4.

---

## 1. Problem Statement

The benchmark compares models across vendors, but its **inputs and infrastructure** were authored
largely by Claude via Claude Code: the seed `.proto` contracts, the `requirements_text` spec, and the
SDK-authored ground-truth suites. This is a systematic-bias surface — Claude-authored phrasing,
contract shapes, or ground-truth interpretations could subtly favor Anthropic models — and it is the
single most attackable validity claim for a published cross-vendor benchmark ("the author used one
vendor's tool to build the test").

**Mitigation:** independently re-author the same inputs with Codex (OpenAI) and Antigravity (Google)
from a neutral source, then measure (a) whether the independently-authored artifacts *agree*
(input-equivalence) and (b) whether swapping them changes model *rankings* (score-impact). Where all
three independent authors agree, the input is likely neutral; where they diverge, that is where
author-bias or genuine source-ambiguity lives.

| Input artifact (pricing seed) | Authored by | Bias risk |
|---|---|---|
| `pricing.proto` (contract) | Claude | shape/field choices favor Claude idioms |
| `requirements_text` (spec) | Claude | phrasing/structure easier for Claude to satisfy |
| `pricing_suite.py` (ground truth) | Claude | the *interpretation* of correct behavior is Claude's |

### 1.1 Terminology

To avoid conflating authoring systems, evaluated systems, and vendors:

| Term | Meaning in this audit |
|---|---|
| **Vendor** | The organization associated with an authoring tool or evaluated model family: Anthropic, OpenAI, or Google. |
| **Authoring tool** | The tool/agent used to generate benchmark input artifacts: Claude Code, OpenAI Codex, or Google Antigravity. |
| **Author** | A concrete authoring run: `{tool, model/version, prompt template, parameters, timestamp, sample index}`. “Claude-authored,” “Codex-authored,” and “Antigravity-authored” refer to artifact provenance, not necessarily to the evaluated model. |
| **Evaluated model** | A model being scored on the benchmark task in FR-6. The evaluated model may share a vendor with an authoring tool, but is a distinct experimental subject. |
| **Author-vendor** | The vendor associated with the tool that generated a spec, proto, or suite artifact. |
| **Model-vendor** | The vendor associated with the evaluated model whose benchmark score is measured. |
| **Vendor-authorship bias signal** | Evidence that artifacts authored by a vendor’s tool systematically favor evaluated models from that same vendor, after accounting for artifact quality and run variance. |
| **Tool-capability difference** | Divergence caused by a tool failing to follow instructions, compile artifacts, use required formats, or complete the task, rather than by a stable semantic preference attributable to vendor authorship. |

FR-2, FR-6, FR-7, and FR-11 use **author-vendor** for generated artifacts and **model-vendor** for scored models.

---

## 2. Requirements

**FR-1 — Neutral task brief (FIXED/OPEN tagged).** Author a vendor-agnostic brief describing the
reproduction task from the *upstream source* (the Liferay pricing capability + the bare benchmark
seed-contract schema), NOT from Claude's existing artifacts. Tag each requirement **FIXED**
(a true contract constraint — single RPC, decimal-string money, gRPC, the seed JSON shape) or
**OPEN** (a semantic choice under test — rounding default, chain-vs-addition, fixed-amount basis,
tax/discount ordering, error taxonomy, field naming). The brief must not leak Claude's resolution of
any OPEN item. Human-reviewed for Claude-idiom leakage (the honesty control).

The brief must include a **source-to-brief traceability matrix** recording, per item: brief ID;
FIXED/OPEN; the upstream Liferay evidence / seed-schema constraint / human judgment supporting the tag
with exact citation (URL, commit, path, or schema field); why a FIXED item isn't an author choice; why
an OPEN item isn't pre-resolved by Claude; and any residual ambiguity to route to FR-5/FR-8/FR-9.
Admissibility: a FIXED item must trace to upstream evidence or a seed-schema constraint; an OPEN item
must be one the source permits multiple plausible implementations for, or an intentional design choice
under test.

**FR-1b — Standardized prompt template.** All authoring tools receive prompts from a single controlled,
versioned template that cleanly separates: the FR-1 neutral brief; experiment-specific (suite vs spec)
instructions; allowed/forbidden deps; output-file requirements; tool invocation mechanics; parameters;
and any few-shot/scaffolding. Few-shot examples (if used) are vendor-neutral, encode no OPEN resolution,
and are identical across tools except for unavoidable API/CLI mechanics. Template, rendered prompt, and
per-tool substitutions are captured under FR-3.

**FR-2 — Factored re-authoring (not all-at-once).** Re-authoring decomposes into two isolated
experiments so spec-bias and suite-bias don't conflate:
- **FR-2a — Suite-author experiment:** hold the spec FIXED (Claude's), have each authoring tool author
  only the **ground-truth suite**.
- **FR-2b — Spec-author experiment:** hold the *behavior/oracle* fixed, have each authoring tool author
  only the **spec** from the neutral brief. Proto generation is collected as a secondary artifact but is
  not automatically used in FR-6 score-impact runs.

Each experiment runs with a Claude control for symmetry. Each authoring run is labeled by author-vendor,
tool, model/version, sample index, prompt-template version, and timestamp.

Proto variation in FR-2b: the **primary FR-6 score-impact run freezes the canonical proto and harness**
so score changes attribute to spec wording, not contract shape. Vendor-authored proto variants are kept
for FR-5 divergence and may run only in a separately-labeled **contract-shape sensitivity analysis** when
adapters preserve task semantics. Field-name / RPC-shape / validation-semantics / incompatible-message
differences are never silently normalized into the primary run — they are cataloged as divergences. If a
spec can't be expressed against the frozen proto without resolving an OPEN choice, log the adaptation and
route it to FR-7 adjudication before scoring.

**FR-3 — Automatable, reproducible runs.** Drive Codex and Antigravity via CLI/API. Capture prompt,
tool+model version, parameters, raw output, and timestamp per run so the audit is re-runnable. Verify
each tool's headless path at the start; if Antigravity has no headless mode, fall back to documented
manual capture and flag the asymmetry.

Reproducibility baseline (each item is required, detail in the plan): locked runtimes/containers
(Python/Node/gRPC/protobuf/package managers/test runners); dependency lockfiles + checksum/commit
pinning; recorded API parameters (temperature, top-p, max tokens, tool-use, retries, seeds where
available) with explicit nondeterminism handling; rate-limit/retry logs; OS/arch/env/secrets-handling;
an artifact store holding immutable raw + normalized outputs, repair/compile/run logs, suite + mutant
results, and analysis scripts; and a machine-readable manifest linking every artifact to its run metadata.

Model/version update policy: prefer version-locked models or dated aliases for the whole pilot; finish an
active batch on update only if the provider guarantees the same version, else restart it; if locking is
impossible, record provider-reported version+timestamp per call, analyze pre/post-update separately, and
flag cross-version comparisons as lower-confidence; never mix versions within an FR-11 sample group or
FR-6 cell unless the mix is explicitly modeled.

**FR-3a — Artifact acceptance criteria.** Artifacts pass consistent intake rules before entering
FR-4/5/6. **Specs:** Markdown/text + run-metadata header, sufficient to implement the server against the
canonical proto, no private-Claude dependency (except where the experiment fixes it), not code-only
unless the prompt requested it. **Protos:** valid `.proto`, compile under the locked toolchain, define
the requested service/messages (else cataloged as failure), no nonstandard plugins unless allowed.
**Suites:** locked-harness-compatible test file, run under the locked runtime against the oracle + mutant
battery via the standard adapter within timeout, allowed deps only. **Common rules:** normalize only
mechanical formatting/filenames/imports/adapter-paths via a predeclared script (record all diffs); never
silently repair semantics/expected-values/rounding/API-behavior; reject artifacts needing unapproved
deps, network, or manual interpretation; apply identical timeouts/resource limits across tools.

**FR-3b — Catastrophic generation failure policy.** A generation is catastrophic if it is syntactically
invalid, non-compiling, non-running, missing required files, or fails a majority of the brief. Policy:
allow ≤1 automated retry (same prompt/params) for truncation/formatting/file-boundary failures; mechanical
repair only per FR-3a; no human semantic repair for inclusion in any analysis; log raw output + category
+ retry status + exclusion reason; count catastrophic failures in tool-capability reporting + FR-11
within-tool variance; exclude them from semantic bias calls unless the failures are themselves consistent,
vendor-specific, and adjudicated as authorship-relevant.

**FR-4 — Input-equivalence via mutant battery.** Cross-validate the FR-2a suites against the
known-correct Node oracle **plus a battery of mutant servers** (FR-12). Two suites are equivalent iff
they produce the same pass/fail vector across the whole battery. A suite that misses a mutant the
others catch reveals an author blind spot — localize it to the missing assertion.

The Node oracle must have documented provenance and independent validation before it can anchor FR-4:
record authorship (tool/human provenance, commits, any Claude-derived portion) and require independent
non-Claude review/reimplementation for any Claude-derived behavior before it serves as the sole anchor;
validate against the FR-1 matrix + upstream Liferay evidence (not Claude's spec alone); keep an evidence
log (expected behavior / citation / reviewer sign-off / tests) per FIXED + adjudicated OPEN behavior; run
property/metamorphic checks where applicable (decimal precision, monotonicity, caps, stable rounding); and
require ≥2 reviewers (one blinded where practical) to confirm it doesn't merely encode Claude's choices.

FR-4 results are not trusted until the oracle validation gate and FR-12 mutant adequacy gate both pass.

**FR-5 — Spec/contract divergence catalog.** Diff the FR-2b specs and protos for semantic divergences
(rounding default, strategy default, fixed-amount basis, tax ordering, error taxonomy, field naming).
Classify each as legitimate source-ambiguity vs author-specific choice.

The catalog records per divergence: exact location/snippet; affected FIXED/OPEN item; upstream evidence
(or its absence); divergence type (behavior / wording-only / contract-shape / validation-semantics /
harness-compat); FR-6 primary-run eligibility under the frozen-proto policy; any FR-12 mutant that
exercises it; and FR-11 cross-sample consistency.

Classification rubric: **legitimate source-ambiguity** (source admits multiple behaviors, item was OPEN,
no sole reliance on Claude wording) · **author-specific choice** (resolves an OPEN item not compelled by
source, esp. if stable across a tool's samples) · **schema/contract constraint** (required by the seed
schema, should have been FIXED — correct FR-1) · **tool-capability artifact** (malformed/incomplete output,
not a coherent choice) · **human-adjudicated correction** (reviewers pin the behavior).

Any significant FR-4 suite divergence or FR-6 interaction must trace back to ≥1 OPEN item in FR-1. If no
OPEN item explains the signal, either revise the FR-1 matrix or classify it as a tool/harness artifact,
not semantic bias.

**FR-6 — Score-impact via model×spec interaction.** Run the same 3-flagship roster against each spec
variant (Claude/Codex/Antigravity), holding everything else constant. The bias signal is **not** a
marginal score shift (that is spec *quality*, which moves all models together) but the **interaction**:
a vendor's model scoring *relatively* higher under its own vendor's spec. Report the interaction, not
just per-spec means.

Primary FR-6 design. **Unit:** one evaluated-model implementation attempt for one spec variant under the
frozen canonical proto/harness. **Cells:** evaluated model-vendor × spec author-vendor. **N:** ≥5/cell for
the pilot unless OQ-4 power/cost calibration approves otherwise before running. **Pairing:** by run index
across spec variants for the same model, identical harness/budget/scoring. **Outcome:** benchmark score
(pass rate or normalized points on one scale across specs). **Primary model:** two-way interaction via a
linear mixed-effects model (continuous scores) or generalized mixed-effects (binary/test-level), fixed
effects = model-vendor + spec author-vendor + interaction, random effects = run index (+ test case when
test-level). **Non-parametric check:** paired bootstrap/permutation over run indices. **Interaction
metric:** for vendor `v`, an own-vendor advantage —

  `OVA_v = [S(model_v, spec_v) - mean_a≠v S(model_v, spec_a)] - mean_u≠v [S(model_u, spec_v) - mean_a≠v S(model_u, spec_a)]`

  where `S(model, spec)` is the mean cell score; this subtracts `spec_v`'s general difficulty/quality from
the same-vendor gain. **Uncertainty:** report 95% CIs / credible intervals per `OVA_v` + the overall
interaction term. **Bias threshold:** a candidate signal only if the interval excludes zero and |`OVA_v`|
≥ 5 pts or ≥ 0.5 pooled within-cell SD (whichever is larger). **Multiplicity:** Holm (or equivalent
predeclared) over the three vendor tests. **Robustness:** report whether conclusions hold under both the
mixed-effects model and the bootstrap/permutation check.

Proto handling: the primary analysis uses the frozen canonical proto and excludes generated proto
variants; any contract-shape sensitivity analysis is separately labeled and never merged with the primary
spec-wording interaction; any adapter needed to express a generated spec against the canonical proto is
logged and adjudicated if it resolves an OPEN item.

**FR-7 — Attribution via unanimity rule.** **Unanimous** agreement across all three independent authors
→ input deemed neutral (the only strong signal). Any divergence — including a 2-vs-1 split, which is
ambiguous (Claude-bias vs a shared non-Claude convention) — is a **flag for human adjudication**, not an
automatic bias verdict. Distinguish vendor-author bias from tool-capability differences.

Adjudication protocol: ≥2 reviewers with benchmark/domain expertise, blinded to author-vendor labels where
practical, given the FR-1 matrix + upstream evidence + seed constraints + FR-4 vectors + FR-5 entries +
FR-6 summaries. Each assigns one label: **neutral/unanimous** (all tools converge, no material
interaction) · **legitimate source-ambiguity** (source supports multiple choices; pin/document one) ·
**vendor-author bias candidate** (stable author-vendor choice / suite blind spot aligned with a same-vendor
advantage) · **tool-capability difference** (invalid/incomplete/format-fail/unsupported tooling) ·
**harness/proto confound** (contract-shape/adapter incompatibility) · **insufficient evidence**. Resolve
disagreement by discussion, then a third reviewer; keep an adjudication evidence log (reviewer IDs/roles,
blinding, label, rationale, citations, remediation recommendation).

Bias-vs-capability rubric: prefer **vendor-author bias candidate** when the divergence is coherent, maps to
an OPEN item, recurs across a vendor's samples, and is separable from compile/run failure; prefer
**tool-capability** when output is malformed/incomplete, contradicts FIXED requirements, fails acceptance,
or varies idiosyncratically; prefer **ambiguous/source-driven** when multiple tools converge on a non-Claude
choice or the source can't choose among plausible behaviors.

**FR-8 — Bias-audit report.** Per seed: equivalence matrix, divergence catalog, score-impact deltas,
OPEN-item tracebacks, statistical uncertainty, adjudication decisions, and a verdict
(neutral / biased-and-corrected / ambiguous-flagged).

Verdict criteria. **Neutral** (all required): FR-1 matrix passes; oracle + mutant gates pass; FR-4 vectors
unanimously equivalent across accepted samples (or differences adjudicated non-semantic/tool-capability);
no unresolved material FR-5 divergence (or all adjudicated harmless); no FR-6 own-vendor advantage meeting
threshold; FR-11 cross-tool ≤ within-tool variance for material OPEN items; FR-7 neutral/harmless for all
flags. **Biased-and-corrected** (all required): ≥1 material divergence/interaction adjudicated as
vendor-author bias, traced to OPEN item(s)/Claude assumptions, FR-9 pins/neutralizes it, and re-audit meets
Neutral for the remediated scope (no significant remaining own-vendor advantage). **Ambiguous-flagged:**
evidence insufficient to classify; unpinned source-ambiguity; FR-4/5/6/11 disagree materially; failures
prevent comparable evidence; or contract-shape differences unnormalizable without changing semantics. A
2-vs-1 split is never alone sufficient for a bias verdict — report it as an adjudication flag with evidence.

The report must include raw artifacts, manifests, prompts, run logs, statistical scripts, CIs/credible
intervals, mutant kill matrices, and all adjudication logs needed for external scrutiny.

**FR-9 — Remediation loop.** When bias is found, the fix (neutralize phrasing, pin an ambiguous
semantic in the spec, repair the canonical proto/harness boundary, or update mutant coverage) feeds back
into the seed; re-audit.

Remediation requirements: each remediation identifies the source issue, affected OPEN/FIXED item, affected
artifacts, reviewer label, and concrete patch. By class — source-ambiguity → pin behavior in the spec +
mark the FR-1 matrix human-adjudicated; vendor-author bias → remove/rewrite the biased phrasing/shape + add
a regression mutant/assertion; tool-capability or harness/proto confound → update prompts/acceptance/
adapters/exclusions, not benchmark semantics. All remediated artifacts retain provenance linking original
issue → patch → re-audit result.

Exit criteria: success = re-audit shows no material FR-4 inequivalence, no unresolved FR-5 divergence, and
no threshold-meeting FR-6 own-vendor advantage for the remediated behavior. Run **at most two remediation
loops per seed**; after two failures, classify **ambiguous-flagged / unresolvable-within-pilot**, document
residual risk, and require explicit approval before publishing or expanding that seed.

**FR-10 — Honest provenance.** Record that Codex (OpenAI) and Antigravity (Google) carry their own
vendor bias; the method is triangulation, not bias-free authorship. Publish methodology + raw artifacts
for external scrutiny.

**FR-11 — Sampling for non-determinism.** Take **N samples per tool per artifact** (N ≥ 3 to start).
Treat cross-tool divergence statistically: a difference counts as author-bias only if it is consistent
across a tool's samples and separable from within-tool variance — not a one-off draw.

Statistical decision rules. **Unit:** one accepted artifact sample from one authoring run. **N:** ≥3/tool/
type for pilot feasibility, ≥5 preferred for any final claim. **Suite metric:** pairwise Hamming/Jaccard
between mutant-battery pass/fail vectors + per-mutant kill/miss. **Spec/proto metric:** categorical coding
of each OPEN item + contract-shape dimension, with missing/invalid separated from semantic choices.
**Primary test:** permutation/bootstrap comparing between-tool vs within-tool distance per artifact type;
categorical OPEN choices via Fisher exact or multinomial/hierarchical by N. **Consistency:** a tool-level
choice is stable only at ≥80% of that tool's accepted samples (≥5 preferred for final claims).
**Bias-candidate threshold** (all): the vendor's stable choice differs from ≥1 other vendor's; between>within
distance with 95% CI excluding zero or p<0.05 after multiplicity; maps to an OPEN item / assertion gap; and
isn't explained by catastrophic/tool-capability failures. **Reporting:** CIs, p-values/credible intervals,
raw coded choices, invalid-sample counts, and catastrophic-exclusion sensitivity.

FR-11 does not by itself prove bias; it determines whether divergence is stable enough to route through
FR-5/FR-7 and, where applicable, FR-6.

**FR-12 — Mutant reference battery.** Maintain a battery = the known-correct Node oracle + K mutant
servers, each injecting one semantic error (wrong rounding mode, addition-when-chain, tax-before-discount,
ignored cap, float arithmetic, promo-min inverted, …). Each mutant targets one OPEN choice from FR-1, so a
suite's pass/fail vector reveals which behaviors it actually pins. The battery is the discrimination
instrument for FR-4.

Mutant battery adequacy criteria: cover every material OPEN dimension from FR-1 with ≥1 mutant (≥2 for
high-risk: rounding, ordering, caps, decimal arithmetic, error handling); single-fault only unless flagged
as interaction mutants; keep a manifest per mutant (ID, targeted OPEN item, injected fault, expected
behavior, source rationale, diff, expected kill condition); validate each against the oracle + ≥1
hand-authored smoke suite; exclude/rewrite **equivalent** mutants (indistinguishable from the oracle) and
**invalid** mutants (crash / violate the contract / fail unrelated FIXED constraints); document redundant
mutants (identical kill vectors — allowed for robustness, no coverage credit); and produce an expected-kill
matrix before running generated suites. **Minimum discriminatory power before trusting FR-4:** each material
OPEN dimension has ≥1 valid non-equivalent mutant; the battery separates ≥1 intentionally-weak calibration
suite from the oracle; the oracle passes all tests while each mutant differs from it on ≥1 targeted probe;
no mutant's kill is due solely to harness incompatibility. If the adequacy gate fails, FR-4 conclusions are
provisional and the battery is expanded before final verdicts.

Oracle validation from FR-4 applies to the battery baseline. Mutants follow the same provenance discipline:
record authoring method, tool/human involvement, source evidence, and review sign-off.

**FR-13 — Pilot success criteria and go/no-go for expansion.** The pricing-seed pilot determines whether
to extend the audit to the full Summer-2026 benchmark.

Expansion to additional seeds is allowed only if all hold: FR-1 brief + traceability are feasible without
Claude artifacts; FR-3 automation/storage/manifests work for all tools (or Antigravity manual-capture
asymmetry is documented + acceptable); FR-3a/3b yield comparable artifact sets without excessive manual
work; FR-4 oracle + FR-12 mutant gates pass; FR-5/7 adjudication produces interpretable decisions; FR-6
runs complete within budget with estimable intervals; FR-11 separates within- from cross-tool variance; and
the pilot reaches a **definitive FR-8 verdict** (neutral / biased-and-corrected / ambiguous-flagged with
bounded, acceptable residual risk) — process feasibility alone is not sufficient.

No-go / redesign if: the brief can't be traced to upstream evidence; the oracle/mutants can't be
independently validated; failure rates prevent comparable analysis; proto/harness incompatibility dominates;
FR-6 uncertainty is too large to interpret within feasible N/cost; or adjudication can't distinguish
source-ambiguity / vendor bias / tool-capability.

## 3. Non-Requirements

- **Not** reproducing the SDK code, scoring, or harness — inputs only (per scope decision).
- **Not** a bias-free oracle — triangulation across three biased authors, not purity.
- **Not** auto-correcting — divergences go to human adjudication.
- **Not** the OB seeds in the pilot — pricing seed first.

## 4. Open Questions

- **OQ-1** Exact Codex / Antigravity CLI/API invocation + auth (Doppler-managed keys; verify Antigravity headless path — FR-3).
- **OQ-2** Calibrating FR-1 brief neutrality: FIXED/OPEN tagging + human review is the mechanism, but how loose is too loose? (Resolved in approach; needs a review pass on the actual brief.)
- **OQ-4** Score-impact spend (~3 spec variants × pricing-only × 3 flagships × N=5 ≈ $8) and the interaction-model statistics (FR-6) — calibrate N for power.
- **OQ-3 → resolved** (FR-12 mutant battery). **OQ-5 → resolved** (FR-11 sampling).

---

*v0.4 — review-integrated then trimmed for pilot density. Retains the v0.3 additions (terminology,
traceability, prompt control, artifact intake/failure policy, oracle validation, proto-freezing for
score-impact, statistical decision rules, mutant adequacy gates, adjudication protocol, verdict rubric,
remediation exit criteria, pilot go/no-go, model-update handling) over the factored v0.2 design;
enumerations compressed and verbose prose tightened without dropping any requirement.*

## Appendix: Iterative Review Log (Applied / Rejected Suggestions)

This appendix is intentionally **append-only**. New reviewers (human or model) should add suggestions to Appendix C, and then once validated, record the final disposition in Appendix A (applied) or Appendix B (rejected with rationale).

### Reviewer Instructions (for humans + models)

- **Before suggesting changes**: Scan Appendix A and Appendix B first. Do **not** re-suggest items already applied or explicitly rejected.
- **When proposing changes**: Append them to Appendix C using a unique suggestion ID (`R{round}-S{n}`).
- **When endorsing prior suggestions**: If you agree with an untriaged suggestion from a prior round, list it in an **Endorsements** section after your suggestion table. This builds consensus signal — suggestions endorsed by multiple reviewers should be prioritized during triage.
- **When validating**: For each suggestion, append a row to Appendix A (if applied) or Appendix B (if rejected) referencing the suggestion ID. Endorsement counts inform priority but do not auto-apply suggestions.
- **If rejecting**: Record **why** (specific rationale) so future models don't re-propose the same idea.

### Areas Substantially Addressed

- **completeness**: 5 suggestions applied (R1-S7, R2-S7, R1-S2, R2-S2, R2-S6)
- **feasibility**: 4 suggestions applied (R1-S4, R1-S9, R2-S5, R2-S8)
- **testability**: 6 suggestions applied (R1-S1, R1-S6, R1-S10, R2-S2, R2-S4, R2-S6)
- **traceability**: 3 suggestions applied (R1-S2, R1-S3, R2-S3)

### Areas Needing Further Review

- **ambiguity**: 2 accepted (R1-S8, R2-S1) — needs 1 more to reach threshold of 3
- **consistency**: 1 accepted (R1-S5) — needs 2 more to reach threshold of 3
- **traceability**: 2 accepted (R1-S3, R2-S3) — needs 1 more to reach threshold of 3

### Appendix A: Applied Suggestions

| ID | Suggestion | Source | Implementation / Validation Notes | Date |
|----|------------|--------|----------------------------------|------|
| R1-S1 | Define explicit statistical decision rules for FR-6 and FR-11. | gpt5.5 (gpt-5.5) | Pre-specified experimental units, interaction metrics, uncertainty intervals, sample sizes, and bias thresholds are necessary to make the audit objective, reproducible, and resistant to post-hoc interpretation. | 2026-06-17 20:28:23 UTC |
| R1-S2 | Specify provenance and independent validation for the known-correct Node oracle. | gpt5.5 (gpt-5.5) | Because FR-4 and FR-12 anchor correctness on the oracle, its authorship, independence from Claude-derived assumptions, and evidence trail must be documented to avoid inheriting the very bias being audited. | 2026-06-17 20:28:23 UTC |
| R1-S3 | Require a source-to-brief traceability matrix for every FIXED and OPEN item. | gpt5.5 (gpt-5.5) | The neutral brief is central to the design, and traceability is needed to prove that FIXED constraints come from upstream evidence or schema constraints while OPEN items are not pre-resolved by Claude-authored artifacts. | 2026-06-17 20:28:23 UTC |
| R1-S4 | Define acceptance criteria for generated specs, protos, and suites. | gpt5.5 (gpt-5.5) | Clear intake rules for formats, compile/run checks, dependencies, timeouts, normalization, and repair are needed to avoid inconsistent exclusion or manual correction of generated artifacts. | 2026-06-17 20:28:23 UTC |
| R1-S5 | Clarify how proto variation is handled in FR-2b and FR-6. | gpt5.5 (gpt-5.5) | Allowing proto changes while comparing model scores can confound specification wording with contract shape and harness compatibility, so the design must state whether protos are frozen, normalized, adapted, or analyzed separately. | 2026-06-17 20:28:23 UTC |
| R1-S6 | Define adequacy criteria for the mutant battery. | gpt5.5 (gpt-5.5) | FR-4 depends on the mutant battery's discriminatory power, so the audit needs validation gates for mutant coverage, validity, non-equivalence, expected kills, and redundancy. | 2026-06-17 20:28:23 UTC |
| R1-S7 | Define the human adjudication protocol for divergences. | gpt5.5 (gpt-5.5) | Since FR-7 routes all divergences to human adjudication, reviewer roles, blinding, conflict resolution, labels, evidence logs, and remediation handoff must be specified to control adjudicator bias. | 2026-06-17 20:28:23 UTC |
| R1-S8 | Disambiguate tool, author, vendor, and model terminology. | gpt5.5 (gpt-5.5) | The design attributes effects to vendor authorship while using distinct authoring tools and evaluated models, so precise terminology is needed for valid causal interpretation and run records. | 2026-06-17 20:28:23 UTC |
| R1-S9 | Add an environment and reproducibility baseline. | gpt5.5 (gpt-5.5) | Prompt and output capture alone is insufficient; containers or locked runtimes, dependencies, seeds, API settings, rate-limit handling, and artifact layout are needed to rerun suites and mutants reliably. | 2026-06-17 20:28:23 UTC |
| R1-S10 | Define concrete verdict criteria for neutral, biased-and-corrected, and ambiguous-flagged outcomes. | gpt5.5 (gpt-5.5) | FR-8 requires final verdicts, and a decision rubric is necessary to combine FR-4, FR-5, FR-6, FR-7, and FR-11 evidence consistently across seeds. | 2026-06-17 20:28:23 UTC |
| R2-S1 | Create objective criteria for classifying divergences and distinguishing ambiguity, author choice, vendor bias, and tool capability differences. | gemini-2.5 (gemini-2.5-pro) | These classifications are central to the audit's conclusions and need a documented rubric to prevent subjective auditor bias from replacing authoring-tool bias. | 2026-06-17 20:28:23 UTC |
| R2-S2 | Use a standardized prompt template for all three authoring tools. | gemini-2.5 (gemini-2.5-pro) | Prompt framing is itself an experimental input, so a controlled template separating neutral brief content from tool-specific mechanics is needed to avoid prompt-engineering confounds. | 2026-06-17 20:28:23 UTC |
| R2-S3 | Trace significant bias signals back to specific OPEN requirements. | gemini-2.5 (gemini-2.5-pro) | Linking FR-4 or FR-6 findings to the OPEN choices that enabled them makes the audit actionable and directly supports the remediation loop. | 2026-06-17 20:28:23 UTC |
| R2-S4 | Explicitly name the statistical methods for FR-6 and FR-11. | gemini-2.5 (gemini-2.5-pro) | This complements R1-S1 by requiring concrete analysis methods, such as an interaction model and divergence test, which are needed for power planning and reproducible interpretation. | 2026-06-17 20:28:23 UTC |
| R2-S5 | Define a policy for catastrophic tool generation failures. | gemini-2.5 (gemini-2.5-pro) | Non-compiling, syntactically invalid, or severely incomplete artifacts are likely in practice, and consistent retry, repair, exclusion, and logging rules are required to preserve comparability. | 2026-06-17 20:28:23 UTC |
| R2-S6 | Define exit criteria for the remediation loop. | gemini-2.5 (gemini-2.5-pro) | FR-9 needs finite success and escalation conditions so remediation is neither endless nor prematurely stopped after unresolved bias remains. | 2026-06-17 20:28:23 UTC |
| R2-S7 | Define pilot success criteria and go/no-go conditions for extending beyond the pricing seed. | gemini-2.5 (gemini-2.5-pro) | Because the pilot validates the methodology, pre-agreed feasibility, interpretability, cost, and quality criteria are needed to justify expansion to the full benchmark. | 2026-06-17 20:28:23 UTC |
| R2-S8 | Establish a policy for generator model updates during the audit. | gemini-2.5 (gemini-2.5-pro) | Model updates can change generation behavior mid-study, so version locking, restart, or update-handling rules are needed to maintain valid comparisons over time. | 2026-06-17 20:28:23 UTC |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none yet) |  |  |  |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1

- **Reviewer**: gpt5.5 (gpt-5.5)
- **Date**: 2026-06-17 20:26:33 UTC
- **Scope**: Architecture-focused review

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-S1 | Testability | High | Define explicit statistical decision rules for FR-6 and FR-11, including the experimental unit, minimum N, paired comparisons, interaction metric, confidence/credible interval, and threshold for calling a vendor-authorship bias signal. | The document correctly identifies interaction effects and sampling, but without pre-specified decision criteria the audit can still become subjective or underpowered. | Add to FR-6 and FR-11, or as a new subsection under Requirements. | Before running the audit, produce a mock analysis on synthetic data showing how neutral, uniformly harder, and vendor-favoring outcomes would be classified. |
| R1-S2 | Completeness | High | Specify the provenance and validation process for the 'known-correct Node oracle,' including who authored it, whether it is Claude-derived, and how its correctness is independently established. | FR-4 and FR-12 rely on the oracle as the anchor for correctness; if the oracle itself encodes Claude-authored assumptions, the differential audit inherits the bias it is intended to detect. | Expand FR-4 and FR-12 with an oracle-validation requirement. | Require traceability from each oracle behavior to upstream Liferay source or a human-adjudicated FIXED decision, plus independent review sign-off. |
| R1-S3 | Traceability | High | Require a source-to-brief traceability matrix mapping each FIXED and OPEN item in FR-1 to specific upstream Liferay evidence, benchmark seed-schema constraints, or explicit human judgment. | The neutral brief is the central control against leakage; traceability is needed to prove that FIXED constraints are not smuggling in Claude's prior choices and that OPEN items are genuinely left unresolved. | Add to FR-1. | Reviewers should be able to audit every brief statement against a source citation or an explicit adjudication record. |
| R1-S4 | Feasibility | Medium | Define artifact acceptance criteria for generated specs, protos, and suites: required file formats, compile/run checks, allowed dependencies, timeout limits, post-processing rules, and whether human repair is allowed. | Generated artifacts may be incomplete, non-runnable, or require manual interpretation. Without acceptance rules, failures may be inconsistently excluded or repaired, biasing the comparison. | Add to FR-3 or as a new requirement after FR-3. | Run each artifact through an automated intake checklist and record pass/fail plus any permitted normalization steps. |
| R1-S5 | Consistency | High | Clarify how proto variation in FR-2b is handled during FR-6 score-impact runs, especially when field names, RPC shapes, or validation semantics differ across vendor-authored contracts. | FR-2b permits tools to author the proto, but FR-6 requires comparable model scoring under spec variants. Contract changes can alter task difficulty, harness compatibility, and implementation surface independently of spec wording. | Revise FR-2b, FR-5, and FR-6 to state whether proto is frozen, normalized, adapted, or analyzed separately. | Demonstrate that each spec/contract variant can be run through the same scoring harness or document the adapter layer and its invariants. |
| R1-S6 | Testability | Medium | Define adequacy criteria for the mutant battery, including minimum mutants per OPEN semantic dimension, handling of equivalent/invalid mutants, expected kill matrix, and minimum discriminatory power before FR-4 results are trusted. | A weak or redundant mutant set may falsely indicate suite equivalence. Mutant quality needs its own validation gate. | Expand FR-12. | For each mutant, document the targeted semantic error, expected failing assertion class, and confirmation that at least one reference suite kills it while the oracle passes. |
| R1-S7 | Completeness | Medium | Define the human adjudication protocol for divergences, including reviewer roles, blinding expectations, conflict resolution, decision labels, and how adjudicated decisions feed the remediation loop. | FR-7 relies on human adjudication for all divergences, but the current document does not specify how to prevent adjudication from becoming another source of untracked bias. | Add to FR-7 and FR-9. | Maintain an adjudication log with reviewer identities or roles, evidence considered, final decision, and remediation action. |
| R1-S8 | Ambiguity | Medium | Disambiguate 'tool,' 'author,' 'vendor,' and 'model' throughout the design, especially where Codex/Antigravity/Claude author artifacts but flagship models are later scored. | The audit attributes effects to vendor authorship, but tools and evaluated models may not be the same product, version, or capability class; unclear terminology weakens causal interpretation. | Add a terminology subsection before Requirements and align FR-2, FR-6, FR-7, and FR-11 to it. | Each run record should identify authoring tool, underlying model/version if known, vendor, evaluated model, and role in the experiment. |
| R1-S9 | Feasibility | Medium | Add an environment and reproducibility baseline covering containers or locked runtimes, dependency versions, random seeds where available, API parameter defaults, rate-limit handling, and artifact storage layout. | FR-3 captures prompts and outputs, but reproducibility also depends on execution environment and operational controls, especially for suites and mutant servers. | Expand FR-3. | A fresh checkout in a clean environment should be able to replay artifact generation metadata where possible and rerun all suites against the oracle and mutants. |
| R1-S10 | Testability | Medium | Define concrete verdict criteria for 'neutral,' 'biased-and-corrected,' and 'ambiguous-flagged' using FR-4 equivalence, FR-5 divergence, FR-6 interaction, FR-7 unanimity, and FR-11 sampling outcomes. | FR-8 requires a verdict, but the current requirements do not specify how evidence is combined into that verdict, creating room for inconsistent reporting across seeds. | Expand FR-8. | Create a decision rubric and apply it to at least three hypothetical cases: unanimous equivalence, persistent 2-vs-1 divergence, and significant model-by-spec interaction. |

#### Review Round R2

- **Reviewer**: gemini-2.5 (gemini-2.5-pro)
- **Date**: 2026-06-17 20:27:10 UTC
- **Scope**: Architecture-focused review

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R2-S1 | Ambiguity | High | Define objective criteria for classifying divergences found in FR-5 and FR-7. Specifically, provide a rubric to distinguish between (a) legitimate source-ambiguity vs. author-specific choice, and (b) vendor-author bias vs. tool-capability differences. | These classifications are central to the audit's conclusion but are currently subjective. Undefined criteria risk introducing auditor bias into the very process designed to detect authorship bias, undermining the validity of the findings. | New sub-requirements or clarifying notes for FR-5 and FR-7. | The classification rubric is documented and reviewed for clarity and objectivity before the audit begins. |
| R2-S2 | Completeness | High | Add a requirement to create and use a standardized, templated prompt structure for all three tools. The template should clearly separate the neutral brief content (from FR-1) from tool-specific instructions, parameter settings, and any few-shot examples. | The prompt is a significant part of the input. Without a controlled structure, variations in prompt engineering for each tool could introduce a confounding variable, where observed differences are due to the prompt frame rather than the tool's intrinsic bias. | New requirement, perhaps FR-1b, linked to FR-3. | The prompt template is committed to the repository and reviewed for neutrality and consistency. |
| R2-S3 | Traceability | High | Require that any significant bias signal (e.g., a score-impact interaction from FR-6 or a consistent suite divergence from FR-4) be traced back to the specific 'OPEN' requirement(s) in the neutral brief (FR-1) that enabled the divergence. | Simply identifying bias is insufficient; understanding its source is critical for effective remediation (FR-9). This traceability makes the audit's findings actionable and provides deeper insight into which parts of a specification are most susceptible to interpretation bias. | Add as a required component of the 'divergence catalog' in FR-5 and the final report in FR-8. | The final audit report for the pilot must demonstrate this traceability for at least one significant finding. |
| R2-S4 | Testability | High | Explicitly name the statistical methods to be used for FR-6 and FR-11. For example, specify a two-way ANOVA or mixed-effects model for the model×spec interaction (FR-6) and a specific divergence metric or non-parametric test for cross-tool differences (FR-11). | Stating 'test the interaction' or 'treat statistically' is ambiguous. Specifying the statistical model makes the requirement concrete, testable, and informs the experimental design, including the sample size `N` needed to achieve adequate statistical power (OQ-4). | Sharpen the text of FR-6 and FR-11. | The chosen statistical tests are documented in the implementation plan (`CROSS_TOOL_BIAS_AUDIT_PLAN.md`). |
| R2-S5 | Feasibility | Medium | Define a policy for handling catastrophic tool generation failures, such as producing non-compiling code, syntactically invalid artifacts, or failing to address a majority of the brief. | The current requirements assume successful or near-successful generation. In practice, tools may fail completely. A policy is needed to ensure consistent handling of such cases (e.g., number of retries, criteria for manual intervention, or logging as a capability gap) to maintain reproducibility. | New requirement, perhaps FR-3b. | The failure-handling policy is documented before implementation begins. |
| R2-S6 | Completeness | Medium | Define the exit criteria for the remediation loop (FR-9). Specify what constitutes a successful remediation (e.g., a re-audit showing no statistically significant interaction) and the maximum number of loops before an issue is escalated or documented as unresolvable. | Without exit criteria, the remediation loop could continue indefinitely or be stopped prematurely. Clear criteria ensure the process is finite, goal-oriented, and produces a definitive outcome for each identified bias. | Sharpen the text of FR-9. | The exit criteria are documented as part of the audit process in the plan. |
| R2-S7 | Completeness | High | Add a requirement to define the success criteria for the pilot phase. These criteria should determine the go/no-go decision for extending the audit from the pricing seed to the full Summer-2026 benchmark. | The pilot's purpose is to validate the methodology. Defining success criteria up front (e.g., methodology is feasible, produces interpretable results, cost is within budget) ensures the pilot has a clear objective and provides a rational basis for future investment in the full audit. | Update to the Scope section or a new requirement in Section 2. | The success criteria are documented and approved before the pilot begins. |
| R2-S8 | Feasibility | Medium | Add a requirement to establish a policy for handling updates to the underlying generator models (Claude, Codex, Antigravity) during the audit. | These models are updated frequently. An update could change a model's behavior, invalidating comparisons across different time points. The policy should specify whether to lock versions for the duration of the audit, restart on updates, or other handling strategies. | New requirement, linked to FR-3 (which already requires capturing version info). | The versioning and update policy is documented in the audit plan. |

#### Review Round R2

- **Reviewer**: gemini-2.5 (gemini-2.5-pro)
- **Date**: 2026-06-17 20:33:10 UTC
- **Scope**: Architecture-focused review (Feature Requirements)

#### Feature Requirements Suggestions
\n\n| ID | Req | Severity | Suggestion |\n|---|---|---|---|\n| R2-F1 | FR-6 | Low | Add a plain-English explanation or a small, illustrative example for the `OVA_v` (Own-Vendor Advantage) formula. The current statistical definition is precise but not intuitive, making the results harder for a broader audience to interpret. |\n| R2-F2 | FR-2b | Medium | Clarify the policy for generated specs that are semantically inseparable from their co-generated (non-canonical) protos. If these are excluded from the FR-6 score-impact analysis, the audit may be blind to a significant form of author-bias expressed through contract shape. The requirement should specify if/how such specs can be adapted or analyzed. |\n| R2-F3 | FR-9 | Medium | Define the \"escalation\" process. If remediation fails after two loops, the requirement states the issue is escalated, but it does not specify to whom, what the expected outcome is, or how that process is managed. |\n| R2-F4 | FR-13 | High | Add a *results-oriented* pilot success criterion. The current criteria are process-focused (e.g., \"is it feasible\"). A criterion like \"The pilot produces a definitive verdict (Neutral, Biased-and-corrected, or Ambiguous-flagged with specific, bounded risks) for the pricing seed\" would ensure the process is not just runnable but also conclusive. |\n| R2-F5 | FR-3b | Medium | The policy on catastrophic failures should specify how these failures are weighted in the overall verdict. For example, if one tool consistently fails to generate a valid suite, is that just a tool-capability issue, or is it a form of bias (i.e., the task is structured in a way only some tools can handle)? The attribution rubric in FR-7 should explicitly address this. |\n\n<br>\n\n#### Requirements Coverage\n\n| Feature Requirement | Plan Step(s) | Coverage | Gaps & Comments |\n|---|---|---|---|\n| FR-1 (Brief) | S1 | Full | The plan correctly identifies this as the foundational first step. |\n| FR-2 (Factored Exp) | S4, S5 | Full | The plan correctly separates the experiments into suite-author (S4) and spec-author (S5) biases. |\n| FR-3 (Reproducibility) | S2 | Partial | S2 sets up the harness, but the plan lacks explicit handling for the artifact acceptance/failure policies from FR-3a/3b. |\n| FR-4 (Equivalence) | S4 | Partial | The plan uses the mutant battery but lacks the explicit, upfront *oracle validation* step required by FR-4 before the battery can be trusted. |\n| FR-5 (Divergence) | S6 | Full | S6 directly implements the divergence catalog requirement. |\n| FR-6 (Score-impact) | S5 | Full | S5 correctly plans for the model×spec interaction analysis. |\n| FR-7 (Attribution) | S6, S7 | Partial | The plan creates the inputs for adjudication (S6) and reports on it (S7), but the crucial *process* of human adjudication is implicit. An explicit analysis/adjudication step is needed. |\n| FR-8 (Report) | S7 | Full | S7 is dedicated to producing the final report. |\n| FR-9 (Remediation) | S7 | Partial | The plan mentions 're-audit' in S7 but lacks an explicit step for the remediation loop itself. The current plan flow is linear. |\n| FR-10 (Provenance) | S7 | Partial | S7 implies a report, but doesn't explicitly commit to publishing methodology and raw artifacts for scrutiny as required. |\n| FR-11 (Sampling) | S2, S4, S5 | Full | The plan correctly incorporates the need for N samples in the core experiment steps. |\n| FR-12 (Mutant Battery) | S3, S4 | Partial | S3 creates the mutants, but the plan lacks an explicit step for the *mutant adequacy* gate from FR-12 to ensure the battery is sufficiently discriminating. |\n| FR-13 (Go/No-Go) | None | None | The plan produces a report but lacks a final step to evaluate the pilot's success and make the strategic go/no-go decision for expansion. |",
      "rationale": "This meta-suggestion provides the required feature requirement feedback and coverage matrix, which do not fit elsewhere in the structured JSON format. It addresses meta-level review completeness by linking the implementation plan back to the requirements document.",
      "proposed_placement": "N/A"
    }
  ],
  "endorsements": []
}
```

