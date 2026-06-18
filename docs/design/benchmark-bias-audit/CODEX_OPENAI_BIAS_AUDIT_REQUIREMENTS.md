# OpenAI/Codex Differential Bias Audit — Requirements

**Version:** 0.1 (Codex/OpenAI-specific adaptation of the cross-tool audit)  
**Date:** 2026-06-18  
**Status:** Draft (pre-implementation)  
**Plan:** `CODEX_OPENAI_BIAS_AUDIT_PLAN.md`  
**Source review:** `CROSS_TOOL_BIAS_AUDIT_REQUIREMENTS.md` v0.6 and
`CROSS_TOOL_BIAS_AUDIT_PLAN.md` v1.3  
**Scope:** Detect and quantify **OpenAI/Codex-authorship bias** in benchmark input artifacts by
making Codex the treatment authoring surface, using non-OpenAI authoring tools as comparators, and
measuring whether OpenAI evaluated models receive a same-vendor advantage from Codex-authored specs,
contracts, or suites. Pilot on the Liferay-derived pricing seed.

---

## 0. Source Review and Adaptation Delta

The cross-tool requirements and plan are structurally sound and should not be simplified. This
OpenAI/Codex-specific version keeps the same experimental controls: neutral source brief,
FIXED/OPEN tagging, factored suite/spec experiments, mutant battery, frozen canonical proto for the
primary score-impact run, N samples, model×spec interaction analysis, adjudication, remediation, and
pilot go/no-go gates.

The required adaptation is **orientation**, not methodology.

| Cross-tool / Claude-bias audit | OpenAI/Codex-specific audit |
|---|---|
| Primary bias surface is Claude-authored benchmark inputs. | Primary bias surface is Codex/OpenAI-authored benchmark inputs. |
| Codex is an independent comparator against Claude-authored artifacts. | Codex is the treatment authoring surface under audit. Claude Code and Gemini CLI are comparators. |
| Honesty control searches for Claude-idiom leakage in the neutral brief. | Honesty control searches for OpenAI/Codex-idiom leakage, and still rejects Claude leakage from existing seed artifacts. |
| FR-6 reports all own-vendor advantages. | FR-6 still reports all own-vendor advantages, but `OVA_openai` is the primary predeclared endpoint. |
| Codex automation is one authoring lane among several. | Codex automation has its own gate: CLI installation, auth mode, sandbox, ambient instruction control, JSONL capture, model/version lock, and failure policy. |

Current Codex source assumptions were checked against the official Codex manual fetched on
2026-06-18. Relevant documented facts for this audit: `codex exec` is the non-interactive interface;
JSONL output is available for automation; `codex exec` defaults to a read-only sandbox; `CODEX_API_KEY`
is supported for `codex exec`; Codex supports ChatGPT and API-key authentication; and current Codex
model guidance names `gpt-5.5` as the recommended default for most Codex tasks. The pilot must still
pin and record the actual model selected at kickoff.

---

## 1. Problem Statement

A benchmark can become invalid if its inputs are authored through the same vendor surface being
evaluated. For an OpenAI/Codex-focused audit, the attackable claim is:

> "OpenAI/Codex authored the benchmark inputs, and those inputs may favor OpenAI models."

The risk is not that Codex is uniquely biased. The risk is that any agentic authoring surface brings
stable conventions: preferred phrasing, API/contract shapes, error taxonomies, testing idioms,
tool-use assumptions, and implementation scaffolds. If those conventions make OpenAI models perform
relatively better than Anthropic or Google models under the same scoring harness, the benchmark has an
OpenAI/Codex-authorship bias signal.

| Input artifact (pricing seed) | OpenAI/Codex bias risk |
|---|---|
| `pricing.proto` (contract) | Contract shape, field names, enum names, and validation defaults may follow OpenAI/Codex idioms. |
| `requirements_text` (spec) | Phrasing, decomposition, and instruction style may be easier for OpenAI models to follow. |
| `pricing_suite.py` (ground truth) | Test emphasis and expected values may encode Codex's interpretation of ambiguous behavior. |

**Mitigation:** generate Codex-authored artifacts from a neutral, source-traced brief; generate
comparator artifacts with non-OpenAI tools from the same brief; and measure input-equivalence,
semantic divergence, and score-impact. A same-vendor score advantage is a candidate bias signal only
when it survives the predeclared statistical and adjudication gates.

### 1.1 Terminology

| Term | Meaning in this audit |
|---|---|
| **Vendor** | The organization associated with an authoring tool or evaluated model family: OpenAI, Anthropic, or Google. |
| **Target vendor** | OpenAI. The audit is specifically asking whether Codex/OpenAI-authored artifacts favor OpenAI evaluated models. |
| **Authoring surface** | The product/API layer used to create benchmark artifacts. Primary OpenAI surface: Codex CLI non-interactive mode (`codex exec`). Optional surfaces, such as Codex app/cloud/IDE or direct OpenAI API authoring, are separate sensitivity strata and must not be pooled with Codex CLI. |
| **Authoring run** | A concrete generation attempt: `{vendor, surface, tool, model/version, prompt-template version, params, auth mode, sandbox mode, timestamp, sample index}`. |
| **Codex-authored** | Authored by Codex CLI under the controlled `codex exec` profile. Do not use this label for direct OpenAI API calls, ChatGPT web output, or Codex app/cloud output unless a separate stratum explicitly says so. |
| **Comparator-authored** | Authored by non-OpenAI tools, initially Claude Code and Gemini CLI. |
| **Evaluated model** | A model scored by the benchmark runner in FR-6. The OpenAI evaluated model is distinct from Codex as an authoring surface. |
| **Author-vendor** | The vendor associated with the artifact-generating tool. |
| **Model-vendor** | The vendor associated with the evaluated model being scored. |
| **OpenAI own-vendor advantage (`OVA_openai`)** | The predeclared primary FR-6 interaction metric: the OpenAI evaluated model's relative gain under Codex/OpenAI-authored specs, net of the general quality/difficulty of those specs. |
| **OpenAI/Codex-idiom leakage** | Neutral-brief or prompt content that smuggles in Codex/OpenAI conventions: Responses/API/tool-call framing, OpenAI role vocabulary, JSON-schema-first phrasing, Codex file-edit workflow cues, AGENTS.md-derived guidance, or characteristic Codex output structure. |
| **Tool-capability difference** | Failure caused by CLI installation, auth, sandbox, output format, compile/runtime issues, or inability to follow the prompt, rather than a stable semantic preference attributable to vendor authorship. |
| **Material** | Meeting a predeclared threshold: an FR-6 own-vendor advantage >= 5 pts / >= 0.5 pooled SD, or an FR-11 tool-level choice stable at >= 80% of accepted samples. |
| **Spec / Proto / Oracle-harness** | The prose task description, gRPC contract, and known-correct reference server + runner. These are kept separate throughout. |
| **Reviewer sign-off** | A record carrying reviewer ID/role, blinding status, evidence reviewed, decision/label, rationale, and date. |

FR-2, FR-6, FR-7, and FR-11 use **author-vendor** for generated artifacts and
**model-vendor** for scored models.

---

## 2. Requirements

**FR-1 — Neutral source brief with anti-OpenAI controls.** Author the pricing task brief from the
upstream Liferay evidence and the bare benchmark seed-contract schema, not from Codex/OpenAI output
and not from the existing Claude-authored seed artifacts. Tag each item **FIXED** or **OPEN**.
FIXED items must trace to source evidence or schema constraints. OPEN items must remain unresolved by
the brief and represent legitimate semantic choices under test.

The brief must include a source-to-brief traceability matrix with: brief ID; FIXED/OPEN tag;
decision-owner (`source-evidence`, `schema-constraint`, or `human-adjudication`); exact citation
(URL, commit, path, or schema field); why a FIXED item is not an author choice; why an OPEN item is
not pre-resolved by OpenAI/Codex or Claude artifacts; and residual ambiguity routed to FR-5/FR-7/FR-9.

The brief must pass two leakage reviews:
- **OpenAI/Codex leakage review:** no Codex/OpenAI-specific framing, terminology, default behavior, file
  workflow, JSON-schema shape, or instruction style that could make the task unusually natural for
  OpenAI models.
- **Existing-artifact leakage review:** no verbatim field names, default resolutions, section ordering,
  or characteristic phrasing copied from the current Claude-authored seed except where the seed schema
  itself makes the item FIXED.

Because Codex is the target authoring surface, Codex/OpenAI must not be the sole reviewer of the
neutral brief. The neutrality gate requires human review plus non-OpenAI cross-review (Claude Code and
Gemini CLI, when available). Codex may provide a target-vendor sanity review, but that review is not
sufficient for sign-off.

**FR-1b — Standardized prompt template.** All authoring tools receive prompts from one controlled,
versioned template that separates the neutral brief, experiment-specific instructions, allowed deps,
output-file requirements, tool invocation mechanics, parameters, and few-shot/scaffolding. Few-shot
examples, if any, are vendor-neutral and encode no OPEN resolution. Differences in rendered prompts
must be limited to declared tool mechanics.

For Codex specifically, the rendered prompt must be independent of ambient Codex guidance. Any
`AGENTS.md`, Codex skill/plugin, user config, MCP server, memory, or custom rule available to Codex must
be absent from the authoring workspace or explicitly recorded as a controlled experimental input.

**FR-2 — Factored OpenAI/Codex treatment design.** Re-authoring decomposes into two isolated
experiments:
- **FR-2a — Suite-author experiment:** hold the spec fixed and have each authoring surface author only
  the ground-truth suite. The Codex-authored suite is the OpenAI treatment; Claude Code and Gemini CLI
  suites are comparators.
- **FR-2b — Spec-author experiment:** hold the behavior/oracle fixed and have each authoring surface
  author only the spec from the neutral brief. Generated protos are collected as secondary artifacts.

Each experiment includes N samples per authoring surface and labels every run by author-vendor,
surface/tool, model/version, sample index, prompt-template version, auth mode, sandbox mode, and
timestamp.

The primary OpenAI authoring surface is **Codex CLI non-interactive mode** (`codex exec`). Direct
OpenAI API authoring, Codex app, Codex cloud, or Codex IDE output may be run only as separately labeled
sensitivity analyses; they must not be pooled into the primary Codex CLI sample group.

**FR-3 — Codex automation, auth, and provenance.** Codex authoring runs must be automatable and
reproducible through `codex exec`, with JSONL/raw-output capture and immutable provenance. The run
profile must record:
- Codex package and binary version, plus any installation failure.
- Selected model and provider-reported version/alias at run time.
- Auth mode: API key, ChatGPT login, or access token. API-key automation is preferred for repeatable
  local runs; `CODEX_API_KEY` must be scoped to the single `codex exec` invocation via the secret
  manager and never logged.
- Sandbox and approval settings. Use the least permissive mode that can write artifacts; broad access is
  allowed only inside an externally hardened container.
- Whether user config, rules, MCP servers, skills, plugins, memories, or project guidance were loaded.
- Prompt, stdin context, stdout JSONL, stderr, exit code, final message, file diffs, retry logs, and
  checksums.

Codex runs must not rely on the startd8 SDK provider layer for authoring. The SDK can serve the FR-6
scoring step only, where the harness is deliberately held constant. Authoring through the SDK would mix
OpenAI/Codex behavior with the SDK's existing prompts, provider wrappers, and repository guidance.

Model/version update policy: prefer a locked model or dated alias for the entire pilot. If a moving alias
changes mid-batch, finish the active batch only when the provider guarantees continuity; otherwise
restart the batch and analyze pre/post-update samples separately.

**FR-3a — Ambient instruction isolation.** Codex, Claude Code, and Gemini CLI must run in controlled
workspaces that remove or neutralize tool-specific ambient files. This repository currently contains
`CLAUDE.md`; a future Codex authoring workspace may also contain `AGENTS.md` or Codex config. Such files
are experimental confounds unless they are intentionally included, versioned, and mirrored by equivalent
controls for comparator tools.

**FR-3b — Artifact acceptance and catastrophic failures.** Apply the same intake policy to Codex and
comparator artifacts before FR-4/FR-5/FR-6. Specs must be text/Markdown with run metadata and enough
detail to implement against the canonical proto. Protos must compile under the locked toolchain. Suites
must run against the oracle + mutant battery within the locked harness and timeout. Normalize only
mechanical formatting, filenames, imports, and adapter paths via predeclared scripts; never silently
repair semantics, expected values, rounding, or API behavior.

A generation is catastrophic if it is syntactically invalid, non-compiling, non-running, missing required
files, or fails a majority of the brief. Allow at most one automated retry for truncation, formatting, or
file-boundary failure. No human semantic repair is allowed for inclusion in the analysis. Catastrophic
Codex failures count in capability reporting and FR-11 variance, but are excluded from semantic bias
calls unless they are consistent, OpenAI-specific, and adjudicated authorship-relevant.

**FR-4 — Input-equivalence via validated oracle and mutant battery.** Cross-validate FR-2a suites
against the known-correct Node oracle plus a battery of mutant servers. Two suites are equivalent iff
they produce the same pass/fail vector across the whole battery.

The oracle must have documented provenance and independent validation before it anchors FR-4:
authorship, commits, any Claude/Codex-derived portions, evidence log per FIXED/adjudicated behavior,
property/metamorphic checks, and at least two reviewer sign-offs. Any OpenAI/Codex-derived oracle
behavior requires non-OpenAI review or reimplementation before serving as the sole correctness anchor.

**FR-5 — OpenAI/Codex divergence catalog.** Diff Codex-authored specs/protos/suites against comparator
artifacts for semantic divergences: rounding default, strategy default, fixed-amount basis, tax ordering,
error taxonomy, field naming, prompt-shape assumptions, output formatting, and harness compatibility.

Every divergence record includes exact location/snippet, affected FIXED/OPEN item, upstream evidence
or absence, divergence type, FR-6 primary-run eligibility, exercising mutant, FR-11 consistency, and
whether it appears to be an OpenAI/Codex idiom, source ambiguity, schema constraint, tool-capability
artifact, or human-adjudicated correction.

**FR-6 — Score-impact via model×spec interaction with `OVA_openai` primary.** Run the same flagship
roster against each accepted spec variant while holding the proto, harness, scoring, budgets, and
runtime constant. The primary analysis uses the frozen canonical proto; generated proto variants are
excluded from primary score-impact and may run only in a separately labeled contract-shape sensitivity
analysis.

The bias signal is the interaction, not a marginal score shift. For vendor `v`:

`OVA_v = [S(model_v, spec_v) - mean_a!=v S(model_v, spec_a)] - mean_u!=v [S(model_u, spec_v) - mean_a!=v S(model_u, spec_a)]`

`OVA_openai` is the primary predeclared endpoint. Report all vendors' OVA values to detect comparator
or general benchmark effects. A candidate OpenAI/Codex bias signal requires the `OVA_openai` interval
to exclude zero and `|OVA_openai|` >= 5 pts or >= 0.5 pooled within-cell SD, whichever is larger, after
the predeclared multiplicity and robustness checks.

**FR-7 — Attribution and adjudication.** Unanimous agreement across author-vendors is the only strong
neutrality signal. Any divergence, including a 2-vs-1 split, is an adjudication flag.

Adjudication requires at least two reviewers with benchmark/domain expertise, blinded to author-vendor
labels where practical. Review packets include the FR-1 matrix, upstream evidence, seed constraints,
FR-4 vectors, FR-5 entries, FR-6 summaries, FR-11 variance, and Codex run metadata. Labels:
**neutral/unanimous**, **legitimate source-ambiguity**, **OpenAI/Codex vendor-author bias candidate**,
**non-OpenAI vendor-author bias candidate**, **tool-capability difference**, **harness/proto confound**,
or **insufficient evidence**.

Prefer OpenAI/Codex vendor-author bias only when the divergence is coherent, maps to an OPEN item,
recurs across Codex samples, is separable from Codex installation/auth/sandbox/output failures, and
aligns directionally with FR-4 or `OVA_openai` evidence.

**FR-8 — OpenAI/Codex bias-audit report.** Per seed, report: equivalence matrix, divergence catalog,
`OVA_openai`, all other OVA values, uncertainty intervals, OPEN-item tracebacks, adjudication decisions,
Codex automation/auth/sandbox summary, machine-readable remediation-candidate IDs, and verdict
(neutral / biased-and-corrected / ambiguous-flagged).

Verdict criteria:
- **Neutral:** FR-1 passes; oracle + mutant gates pass; FR-4 vectors are equivalent or adjudicated
  non-semantic/tool-capability; no unresolved material FR-5 divergence; no threshold-meeting
  `OVA_openai`; FR-11 cross-tool variance is not materially greater than within-tool variance for
  OpenAI-relevant OPEN items; all adjudication flags are neutral/harmless.
- **Biased-and-corrected:** at least one material OpenAI/Codex-authorship signal is adjudicated,
  remediated, and re-audited to neutral for the affected scope.
- **Ambiguous-flagged:** evidence is insufficient, signals conflict, failure rates prevent comparison,
  contract-shape differences cannot be normalized without changing semantics, or remediation fails
  within the loop limit.

**FR-9 — Remediation loop.** When OpenAI/Codex bias or ambiguity is found, patch the seed or audit
machinery and re-run only the minimal affected scope. Source ambiguity pins behavior in the spec and
marks the FR-1 matrix human-adjudicated. OpenAI/Codex bias removes or rewrites biased phrasing/shape and
adds a regression mutant/assertion. Tool-capability and harness/proto confounds update prompts,
acceptance, adapters, exclusions, or environment controls without changing benchmark semantics.

Run at most two remediation loops per seed. After two failures, classify ambiguous-flagged /
unresolvable-within-pilot, document residual risk, and require explicit approval before publishing or
expanding the seed.

**FR-10 — Honest provenance.** Record that Codex/OpenAI, Claude/Anthropic, and Gemini/Google all carry
vendor conventions. The method is triangulation and interaction analysis, not bias-free authorship.
Publish methodology, prompts, manifests, raw artifacts, redaction logs, statistical scripts, and
adjudication logs after secrets/license/PII review.

**FR-11 — Sampling for Codex nondeterminism.** Take N samples per authoring surface and artifact type
(N >= 3 for pilot feasibility, N >= 5 preferred for final claims). A Codex-specific choice counts as
stable only at >= 80% of accepted Codex samples and only when between-tool divergence exceeds within-tool
variance under the predeclared bootstrap/permutation or categorical analysis.

FR-11 does not prove bias by itself. It determines whether a divergence is stable enough to route
through FR-5/FR-7 and, where applicable, FR-6.

**FR-12 — Mutant reference battery.** Maintain a battery of the known-correct Node oracle plus K mutants,
each injecting one semantic error tied to an FR-1 OPEN item. The battery must cover every material OPEN
dimension, validate every mutant against the oracle and a calibration suite, reject equivalent/invalid
mutants, produce an expected-kill matrix, and prove minimum discriminatory power before FR-4 conclusions
are final.

Any mutant authored or edited by Codex/OpenAI requires non-OpenAI review before use in the final
OpenAI/Codex verdict.

**FR-13 — Pilot success and expansion gate.** The pricing-seed pilot may expand only if the method
produces a definitive verdict or bounded ambiguous verdict, Codex automation is reproducible, comparator
automation is comparable, oracle/mutant gates pass, FR-6 intervals are estimable within budget, and
adjudication can distinguish OpenAI/Codex bias from source ambiguity, comparator bias, and tool failure.

No-go/redesign if Codex cannot be run reproducibly, ambient instruction leakage cannot be controlled,
the neutral brief cannot be traced without vendor-authored artifacts, or FR-6 uncertainty is too large to
interpret within feasible N/cost.

---

## 3. Non-Requirements

- Not auditing the whole startd8 SDK provider layer for OpenAI neutrality.
- Not treating Codex app/cloud/IDE, ChatGPT web, and direct OpenAI API calls as interchangeable with
  Codex CLI.
- Not claiming non-OpenAI comparator artifacts are bias-free.
- Not silently repairing generated artifacts to make Codex or any comparator look better.
- Not expanding beyond the pricing seed until FR-13 passes.

---

## 4. Open Questions

- **OQ-OAI-1:** Which OpenAI model is locked for the Codex authoring pilot: current recommended Codex
  default (`gpt-5.5` as of the fetched manual), a dated alias, or a lower-cost model for N-sample
  feasibility?
- **OQ-OAI-2:** Should direct OpenAI API authoring be included as a separate sensitivity stratum, or is
  the pilot Codex CLI only?
- **OQ-OAI-3:** What exact clean-workspace mechanism prevents Codex, Claude Code, and Gemini CLI from
  consuming uncontrolled `AGENTS.md`, `CLAUDE.md`, local config, rules, memories, or MCP state?
- **OQ-OAI-4:** What minimum N gives enough power for `OVA_openai` on the pricing seed under the
  current flagship-runner cost profile?
- **OQ-OAI-5:** Codex package is installed locally as `@openai/codex@0.49.0`, but the binary is missing
  in the current environment. The pilot is blocked until `codex --version` and `codex exec --help`
  succeed under the locked runner image.
