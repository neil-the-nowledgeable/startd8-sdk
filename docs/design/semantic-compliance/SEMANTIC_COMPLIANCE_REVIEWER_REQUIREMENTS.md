# Semantic Compliance Reviewer — Requirements

**Version:** 0.4 (Field-driven — run-029: FR-17 missing-required-symbol backstop)
**Date:** 2026-06-03
**Status:** Draft
**Owner:** neil-the-nowledgeable
**Related:** `docs/design/service-assistant/` (the Service Assistant orchestrates this reviewer post-run)

---

## 0. Planning Insights (Self-Reflective Update)

> What changed between v0.1 (pre-planning) and v0.2. The planning pass mapped each requirement
> to real seams and revealed 5 material corrections; all 8 open questions are resolved or
> reduced, and 1 new wrinkle (altitude) surfaced.

| v0.1 Assumption | Planning Discovery | Impact |
|-----------------|-------------------|--------|
| Requirement text is available at review time (FR-1) | The post-mortem only uses seed tasks **when explicitly passed**; nothing reads `prime-context-seed.json` back, and there's no auto-discovery (unlike `kaizen-suggestions.json`). The seed file **is** written to the run dir, though, with `tasks[].config.{requirements_text,task_description}`. | **FR-1 sharpened.** The SCR must **load+parse `prime-context-seed*.json` itself** and map feature→seed task (by id). Requirement text is recoverable, but only via explicit seed-file loading — not from the post-mortem report. |
| The `SemanticVerificationResult` socket is purely dormant (FR-6) | It's dormant **and so is its config**: `MicroPrimeConfig` already declares `semantic_verification_enabled` / `semantic_verification_agent_spec` / `semantic_verification_fn` — unwired, at the **element** (micro_prime) level. The contract's `element_fqn` field is element-scoped. | **FR-13 sharpened + new altitude note.** The Phase-2 in-run hoist has a pre-existing home (those flags). But post-run review is **feature/file-scoped** while the contract+config are **element-scoped** — an altitude mismatch the contract must bridge (OQ-9). |
| Confidence comes "for free" from the verdict (FR-6) | The review path (`PrimeReviewAdapter._review_task`) is **single-shot**; there is **no self-consistency/voting** anywhere to reuse. Multi-sample confidence is net-new N× token cost. | **FR-6 revised.** Default to single-shot using the contract's own `confidence` field; **multi-sample voting is opt-in** (for gating-readiness), not v1 default. |
| One generic Kaizen hint per cause suffices (FR-10) | Hints flow as a **single newline-joined bullet list** (`generate_kaizen_suggestions` → `kaizen-suggestions.json` → `_apply_kaizen_hints` → `gen_context["kaizen_hints"]`), not per-phase at that layer. A static `CAUSE_TO_SUGGESTION` entry is generic; requirement-*specific* hints need per-feature emission. | **FR-10 refined.** The SCR emits **requirement-anchored hint strings** (templated from each issue's `suggested_fix`) directly into the suggestions pipeline, **plus** a generic `requirement_semantic_gap` fallback in `CAUSE_TO_SUGGESTION`. |
| Reviewer model tier is an open choice (FR-15) | `model_catalog.py` already defines `Models.SEMANTIC_VALIDATOR` (Haiku) and `Models.CODE_REVIEW` (Sonnet). | **FR-15 sharpened.** Escalation = a **model-tier escalation**: cheap Haiku review on flagged features → Sonnet re-review only on low-confidence/`fail`. Reuse `semantic_verification_agent_spec` config name. |

**Resolved open questions:**
- **OQ-1 → RESOLVED.** SCR loads `prime-context-seed*.json` from the run dir and maps feature→task by id (FR-1). Confirm presence + add a graceful "requirement text unavailable → mark `inconclusive`" path.
- **OQ-2 → RESOLVED.** Triage signals are all readable post-run from `FeaturePostMortem`: `requirement_score`, `assembly_delta`, `disk_quality_score`, `semantic_error_count`, `semantic_issue_summary`, `verdict`, `root_cause`, and `target/generated/missing_files`. No cheap-LLM pre-filter tier needed for ranking.
- **OQ-3 → REDUCED to a decision.** False-PASS sampling stays in scope: deep-review a small bounded sample of structurally-clean PASS features (FR-5a) so the run-018 trap is covered without full-run cost.
- **OQ-4 → RESOLVED.** No voting to reuse; single-shot default, opt-in multi-sample (FR-6).
- **OQ-5 → RESOLVED.** `semantic_issues` are `{category|check, severity, message, line}` dicts (`SemanticIssue` / dict form). SCR **consumes** them as triage input and only adds *requirement-intent* findings — dedup by category (FR-8).
- **OQ-6 → RESOLVED.** Emit templated per-feature hints into `kaizen-suggestions.json`'s `prompt_hints` + register a generic `requirement_semantic_gap` `{phase, hint}` entry (FR-10).
- **OQ-7 → RESOLVED.** SCR lives in a new `semantic_compliance/` package; the producer fills `SemanticVerificationResult` via `from_json`/`validate_semantic_verification_json`. It composes with `PrimeReviewAdapter` for the Phase-2 in-run path but does not require modifying it for post-run v1.
- **OQ-8 → carried (gating deferred).** Schema carries `verdict` + `confidence` so a future `STARTD8_SEMANTIC_GATE` can gate on `verdict=="fail" AND confidence>=θ`; θ tuned in Phase 2.

---

## 1. Problem Statement

The Prime Contractor pipeline can mark a feature **PASS** while the generated code does not
actually satisfy the *requirement that was provided as input*. Today's compliance signals are
**structural and shallow**:

- `FeaturePostMortem.requirement_score` is **keyword/substring matching** of the seed task
  description against the feature description + error text (`prime_postmortem.py` `_score_requirements`).
  It cannot tell whether the code *means* what the requirement asked for.
- The deterministic semantic checks (`validators/semantic_checks.py`, the 10 disk-compliance
  layers in `forward_manifest_validator.py`) catch *code smells* (stubs, dupes, fake-work,
  bad imports) — not *requirement intent*.
- The one **agent-driven** semantic contract — `SemanticVerificationResult` (Keiyaku K-7,
  `micro_prime/models.py`) — is **fully defined but never wired in.** It's a dormant socket.

**Illustrative failure mode (observed, run-018):** 6 features failed with the *same* root cause
(`cross_file_contract`), yet the post-mortem emitted **zero `cross_feature_patterns`** — it saw
six isolated structural faults, not one systemic problem. *Caveat (R1-F1-ADV):* run-018 is a
**true FAIL** the structural system already caught; its only miss was *grouping* shared root
causes, which is achievable cheaply by clustering `root_cause` in the post-mortem (no agent). So
run-018 motivates better **grouping**, not necessarily an agent. The SCR's genuinely **unique**
value is **false-PASS detection** — a structurally-clean PASS that does not satisfy the
requirement — for which a deterministic check has no signal. v1 SHALL carry a **worked false-PASS
example** as its primary acceptance anchor (FR-5a), and the question of whether *structural*
cross-feature grouping belongs in the post-mortem rather than the SCR is tracked as OQ-10.

We need a capability that performs **deeper, agent-driven analysis of whether generated
outputs semantically comply with the original input requirements**, and routes that analysis
back into the generation loop so the *next* run produces more compliant code — at controlled cost.

### Gap table

| Compliance dimension | Today | Gap |
|----------------------|-------|-----|
| Requirement intent vs output | keyword match (`requirement_score`) | No semantic judgment of "does this do what was asked" |
| Agent-driven semantic verdict | `SemanticVerificationResult` defined, **unwired** | No producer fills the socket |
| False-PASS detection | `check_fake_work_stub` (structural only) | Semantically-empty-but-structurally-valid PASS slips through |
| Cross-feature semantic patterns | structural root-cause grouping | Shared *intent* violations not recognized (run-018) |
| Feedback to next run | Kaizen Phase C (`CAUSE_TO_SUGGESTION`) | No `requirement_semantic_gap` cause feeding it |
| Cost control on deep review | n/a (no deep review exists) | Must not deep-review every feature every run |

---

## 2. Goals & Non-Goals (summary)

**Goal:** A **Semantic Compliance Reviewer (SCR)** — an agent-driven worker that, for selected
features, compares the *generated output* against the *original requirement* (+ design intent)
and emits a structured `SemanticVerificationResult`, scored and routed into the Kaizen feedback
loop. The **Service Assistant orchestrates it post-run**; the same reviewer contract is designed
so it can later be **hoisted into the in-run pre-merge gate** (phased).

**Decided shape (from product forks):**
- **Timing — phased.** Post-run / SA-orchestrated **first**; contract designed for later in-run gate reuse.
- **Selectivity — tiered.** A cheap deterministic triage flags suspect features; the **expensive
  agent review fires only on flagged features** (cost discipline per the cheap-model strategy).
- **Authority — advisory now, gating opt-in later.** v1 emits suggestions + triage signal only;
  a future flag can make a failing verdict gate.
- **Language scope (v1).** Python-only. The rubric and `element_fqn` convention are language-shaped;
  Go/Node/Java/C# are deferred behind a per-language rubric (a non-Python feature is marked
  `inconclusive: language_unsupported`, never mis-verdicted) *(R2-F1/R2-S1)*.

**Success criteria (measurable — F-R1-2):** the SCR is judged working only if, on a fixed replay
set, (a) **SCR-sourced Kaizen hints raise the next run's mean compliance / `requirement_score` by
≥X** and (b) **false-PASS detection rate ≥Y** on a labeled set. The report SHALL carry the inputs
needed to compute both. (X/Y to be set with the replay set in Phase 2.)

**Not a goal (v1):** gating/blocking runs by default; replacing the deterministic checks;
re-generating code itself; deep-reviewing every feature; non-Python languages.

---

## 3. Requirements

### Input assembly (output ↔ requirement comparison)

- **FR-1 — Requirement retrieval.** For a feature under review, the SCR SHALL **load and parse
  `prime-context-seed*.json` from the run dir itself** (the post-mortem does not persist or
  auto-discover it) and map the feature to its seed task by id, recovering the original
  requirement text (`tasks[].config.{requirements_text, task_description}` + any acceptance
  criteria / `prompt_constraints`). The join SHALL name the exact key (`FeaturePostMortem.feature_id`
  ↔ seed `tasks[].id`) and **corroborate** it — the mapped task's `target_files` must overlap the
  feature's `generated_files`; on ambiguous/empty overlap the SCR SHALL mark the feature
  `inconclusive` with reason `requirement_join_ambiguous` rather than reviewing against a
  possibly-wrong requirement *(R1-F3/S-R1-4)*. When **multiple** `prime-context-seed*.json` match
  (multi-batch runs), selection SHALL be deterministic and documented (latest by mtime), with
  feature-id collisions across seeds resolved to `inconclusive` *(R1-S5)*. When the seed file or
  mapping is unavailable, the SCR SHALL mark the feature `inconclusive` with reason
  `requirement_text_unavailable` rather than guessing.

- **FR-2 — Design-intent enrichment.** The SCR SHALL attach available design-intent context to
  the review: forward-manifest `InterfaceContract.binding_text` for the task, and CKG
  `ProjectKnowledge` authorities (`field_sets`, `negatives` — "invent X, use Y") when present.

- **FR-3 — Generated-output retrieval.** The SCR SHALL load the generated code for the feature
  (the files it produced on disk) as the artifact under semantic review. It SHALL **exclude known
  third-party / boilerplate files** from the payload *(R3-F1/R3-S1)* and enforce a
  `max_input_tokens` budget with a truncation strategy that degrades to `inconclusive` rather than
  overflowing the context window or spiking cost *(R3-S1)*. Reviewed code and requirement text
  SHALL pass through the existing `security.py` redaction before prompt assembly so secrets are not
  sent to the reviewing model *(F-R1-5)*.

### Tiered selection (cost discipline)

- **FR-4 — Cheap triage pass.** Before any agent call, the SCR SHALL run a **deterministic
  suspicion triage** over each feature using already-computed signals — low `requirement_score`,
  positive `assembly_delta`, `fake_work_stub` / semantic_issues present, failed/PARTIAL verdict,
  shared root cause across siblings — producing a `suspicion` ranking. Because `requirement_score`
  is the shallow keyword signal this capability exists to backstop, the triage **MUST NOT
  down-weight suspicion on a high `requirement_score` alone**; structural-emptiness signals
  (`fake_work_stub`, large positive `assembly_delta`, low `disk_quality_score`) SHALL outrank
  keyword score so a semantically-empty-but-keyword-rich false-PASS still ranks high-suspicion
  *(F-R1-1)*. If `prime-postmortem-report.json` is missing/unparseable, the SCR SHALL degrade
  gracefully (mark features `postmortem_unavailable`, no crash) *(R3-S3)*.

- **FR-5 — Escalation budget.** The SCR SHALL deep-review (agent call) **only features above a
  configurable suspicion threshold**, bounded by a per-run escalation budget. These knobs SHALL
  have documented defaults with units — **suspicion threshold** (default 0.5 on a 0–1 scale),
  **max escalated features** (default 10), and **max token cost** (default a per-run ceiling) —
  sourced from config (env `STARTD8_SCR_*` / `MicroPrimeConfig`) and enforced at a single point
  *(R1-F1/R1-S6)*. Skipped features SHALL be recorded as `not_reviewed` with the reason, never
  silently dropped (no-silent-caps).

- **FR-5a — False-PASS sampling.** To catch structurally-clean-but-semantically-empty PASS
  features (the run-018 trap), the SCR SHALL deep-review a small, bounded **sample of PASS
  features** even when they clear the suspicion threshold — prioritizing those adjacent to
  `fake_work_stub` signals — so false-PASS is detectable without full-run review cost. This sample
  SHALL draw on a **reserved quota independent of the FR-5 suspect budget** (default: 2 features or
  10% of PASS features, whichever is larger) so a suspect-heavy run cannot starve false-PASS
  coverage *(R2-F3/R2-S4)*.

### Agent-driven semantic review

- **FR-6 — Semantic verdict production.** For each escalated feature, the SCR SHALL invoke a
  reviewing agent that returns a **`SemanticVerificationResult`** (the existing K-7 contract:
  `verdict` ∈ pass|fail|inconclusive, `confidence`, `issues[]` with category/severity/
  description/line_hint/suggested_fix, `element_fqn`). The SCR SHALL parse via the contract's
  `from_json` / `validate_semantic_verification_json` (fail-open on format, fail-closed on
  content). It is the **first producer** of this dormant contract. Review is **single-shot by
  default**, using the contract's own `confidence` field; **multi-sample self-consistency voting
  is opt-in** (gating-readiness) since no voting pattern exists to reuse and it multiplies cost.
  "Fail-open on format, fail-closed on content" SHALL be defined concretely: **malformed/unparseable
  output → `inconclusive`** (with one bounded retry), **well-formed but content-invalid → `fail`**
  *(R1-F4/R1-S7)*. Decoding SHALL be **deterministic** (temperature 0 / fixed seed where supported)
  so verdicts are reproducible and cacheable, and the agent call SHALL set an explicit `max_tokens`
  bound *(R2-F2/R2-S5/R3-S4)*.

- **FR-7 — Requirement-anchored rubric.** The review prompt SHALL anchor the agent on
  *requirement satisfaction* (does the code implement the asked-for behavior, honor the named
  contracts/field authorities, avoid inventing forbidden constructs) — distinct from generic
  code-quality. The rubric/prompt SHALL be a versioned, single-source template. It SHALL **delimit
  untrusted reviewed content** (generated files, requirement text) and instruct the agent to ignore
  embedded instructions, resisting prompt-injection that would flip a verdict *(R1-S8)*. The rubric
  SHALL be **language-aware**: per-feature `language` selects the rubric variant and the
  `element_fqn` convention (see FR-13/OQ-9). **v1 language scope** is declared in §2 *(R2-F1/R2-S1)*.

- **FR-17 — Missing required public symbol = critical fail (deterministic backstop).** *Field-driven
  by run-029: PI-001 ("Jobs dashboard router") generated only helper functions — its `jobs.py`
  omitted the entire router and both required handlers (`jobs_dashboard`, `job_workspace` from the
  seed `api_signatures`), which crashed app boot (`from app.jobs import jobs_router` → ImportError).
  The SCR **found** the gap but rated it **low** and **passed** the feature — a calibration miss: the
  code was missing its primary deliverable.* The rubric SHALL instruct the agent that a **named,
  required public symbol** declared in the requirement or the seed `api_signatures` that is **absent**
  from the generated code is a **critical, fail-worthy** violation — never a stylistic low. Because an
  LLM verdict already under-weighted this once, the SCR SHALL ALSO apply a **deterministic backstop**:
  it SHALL extract the symbol names from the seed `api_signatures`, AST-check the generated code for
  each, and if any required symbol is absent **force the verdict to `fail`** with a `critical`
  `missing_required_symbol` issue — **overriding** a more lenient LLM verdict. The backstop runs on
  the **full** (untruncated) code to avoid false positives from input truncation (FR-6/R3-S1).

### Scoring & artifacts

- **FR-8 — Compliance score.** The SCR SHALL derive a per-feature `semantic_compliance_score` in
  **[0.0, 1.0]** from a **documented, deterministic formula** — base from verdict
  (`pass`=1.0 / `fail`=0.0), then subtract a confidence-weighted issue-severity penalty
  (e.g. `score = verdict_base × confidence − Σ severity_weight(issue)`, clamped to [0,1]) — so two
  implementers produce identical scores on identical inputs *(R1-F2)*. `inconclusive` verdicts SHALL
  be **excluded from the run aggregate denominator** (neutral), not scored as 0, so missing-text or
  parse failures do not artificially crash the aggregate *(R3-F3)*. The run-level aggregate is the
  mean over conclusive features, distinct from and complementary to the structural `disk_quality_score`.

- **FR-9 — Persisted artifact.** The SCR SHALL write a structured artifact
  (`semantic-compliance-report.json` + a human `.md`) to the run output dir, holding per-feature
  verdicts, issues, scores, the triage/escalation decisions, and the requirement text reviewed.

### Feedback routing (produce better code next run)

- **FR-10 — Kaizen integration.** The SCR SHALL route confirmed semantic gaps into the existing
  Phase C feedback loop by emitting the **structured suggestion-dict schema** that
  `generate_kaizen_suggestions` produces (`pattern_type`, `suggested_action`, `config_key`, `phase`,
  `confidence`, `auto_applicable`) — **not bare hint strings**, which the loop would drop *(R1-F3/R1-S2)*.
  Each requirement-anchored suggestion is templated from the issue's `suggested_fix`, and a generic
  `requirement_semantic_gap` → `{phase, hint}` fallback entry is registered in `CAUSE_TO_SUGGESTION`.
  Hint emission SHALL be **confidence-gated** (only above θ, or only Sonnet-confirmed verdicts) so a
  single-shot cheap-tier false-`fail` cannot poison the next run *(F-R1-4)*, and emitted hints SHALL
  be marked **advisory** so the next generation validates them syntactically rather than blindly
  injecting hallucinated `suggested_fix` syntax *(R3-F2)*. When a feature with a prior hint later
  earns a `pass`, the SCR SHALL prune/tombstone its stale `kaizen-suggestions.json` entry so the
  context loop is not permanently polluted *(R3-S2)*. Reconciles with NR-3 (see NR-3).

- **FR-11 — Cross-feature semantic patterns.** When features share a semantic gap, the SCR SHALL
  emit a **cross-feature semantic pattern** (the signal the structural post-mortem missed on
  run-018), elevated in severity, reusing the existing `CrossFeaturePattern` dataclass rather than a
  parallel store *(R2-S6)*. The grouping key SHALL be concrete — issue `category`, contract id, or
  seed-task id — not the undefined "same requirement/contract" *(R1-F5)*. The trigger SHALL be a
  **relative threshold** (e.g. ≥2 features **and** ≥10% of escalated features), not a bare absolute
  ≥2, so a 200-feature run does not emit noise patterns *(R4-F2)*.

### Orchestration & phasing

- **FR-12 — Service Assistant orchestration (post-run).** The Service Assistant SHALL, on
  detecting a completed run, trigger the SCR (subject to the escalation budget), and SHALL fold
  the SCR's results into its triage artifact + events (new `SEMANTIC_REVIEW_COMPLETE` signal).

- **FR-13 — In-run hoist contract.** The SCR's input/output contract SHALL be defined so the
  same reviewer can later be invoked **in-run pre-merge** without changing its interface — only
  its trigger and authority change. The Phase-2 in-run home is the **pre-existing but unwired
  `MicroPrimeConfig.semantic_verification_{enabled,agent_spec,fn}` hooks** (element-level); the
  SCR SHALL reuse the `semantic_verification_agent_spec` config name and the same
  `SemanticVerificationResult` output so the post-run worker and the in-run hook are the same
  code at different triggers. (In-run wiring deferred to Phase 2; contract compatibility in scope.)

### Authority & cost

- **FR-14 — Advisory by default, gating opt-in.** v1 SHALL treat verdicts as advisory (feed
  Kaizen + triage; never block). The result schema SHALL carry enough (verdict + confidence) for
  a future `STARTD8_SEMANTIC_GATE` flag to gate on `verdict=="fail" AND confidence≥θ`, with **θ
  given a documented default** *(R2-F2)*. The SCR SHALL enforce a **maximum tolerable `inconclusive`
  rate** (default <10% of escalated features); exceeding it emits a `SYSTEM_WARNING` so a systemic
  failure (broken post-mortem parse, missing seeds) cannot silently neutralize the capability and
  let a future gate fail open *(R4-F1)*.

- **FR-15 — Model-tier control / tiered escalation.** The reviewing agent's model SHALL be
  resolved via `model_catalog.py` — not a hardcoded string — reusing `Models.SEMANTIC_VALIDATOR`
  (Haiku) for the cheap first review and `Models.CODE_REVIEW` (Sonnet) for escalation. The
  tiered design (FR-5) SHALL be realized as a **model-tier escalation**: cheap Haiku review on
  flagged features, escalating to Sonnet re-review only on `fail` / low-confidence verdicts.

- **FR-16 — Observability.** The SCR SHALL emit OTel spans/metrics for reviews run, escalations,
  verdict distribution, and token cost, consistent with the SDK's existing event/OTel bridge. The
  metric/span **names and units SHALL be fixed and documented** (e.g. `scr.review_count`,
  `scr.escalations`, `scr.cost_usd` [USD], `scr.avg_confidence`) so dashboards and the OTel bridge
  bind reliably *(R1-F6)*. `scr.cost_usd` SHALL **reuse the existing `CostTracker` / per-feature
  `cost_usd` / `CostSummary` accounting** so it reconciles with run cost rather than being a
  divergent second number *(R2-F4/R2-S2)*.

---

## 4. Non-Requirements

- **NR-1.** No gating/blocking of runs in v1 (advisory only; gating behind a future flag).
- **NR-2.** Does not replace the deterministic semantic checks or disk-compliance layers — it is
  an additive, agent-driven layer that *consumes* their signals for triage.
- **NR-3.** Does not regenerate or edit code — it reviews and recommends. *Clarification (F-R1-4):*
  the SCR does **automatically write** confidence-gated, advisory-flagged hints into
  `kaizen-suggestions.json` (FR-10); this is the one automated write, and it influences only the
  *next* run's prompt — it never edits the current run's code or blocks it. "Advisory" means it does
  not gate or execute remediation, not that it writes nothing.
- **NR-4.** Does not deep-review every feature by default (tiered escalation; full-review is an
  opt-in mode).
- **NR-5.** Not a new classification taxonomy — reuses `SemanticVerificationResult` categories
  and the Kaizen `CAUSE_TO_SUGGESTION` mechanism.
- **NR-6.** In-run pre-merge gating wiring is out of scope for v1 (Phase 2); only contract
  compatibility is in scope.

---

## 5. Open Questions

> OQ-1 through OQ-8 were resolved or reduced by the planning pass — see §0 "Resolved open
> questions." Retained here condensed for traceability; one new question (OQ-9) surfaced.

- **OQ-1 → RESOLVED.** SCR loads/parses `prime-context-seed*.json` itself; `inconclusive` when unavailable.
- **OQ-2 → RESOLVED.** Post-mortem signals suffice for suspicion ranking; no cheap-LLM pre-filter needed.
- **OQ-3 → RESOLVED (decision).** Bounded PASS sampling (FR-5a), `fake_work_stub`-adjacent first.
- **OQ-4 → RESOLVED.** Single-shot default; opt-in multi-sample voting (FR-6).
- **OQ-5 → RESOLVED.** Consume `semantic_issues` as triage input; add only requirement-intent findings, dedup by category.
- **OQ-6 → RESOLVED.** Templated per-feature hints into `prompt_hints` + generic `requirement_semantic_gap` fallback (FR-10).
- **OQ-7 → RESOLVED.** New `semantic_compliance/` package; SCR is the first `SemanticVerificationResult` producer.
- **OQ-8 → CARRIED (gating deferred).** Schema carries `verdict`+`confidence` for a future `STARTD8_SEMANTIC_GATE` (gate on `fail AND confidence≥θ`); θ tuned in Phase 2.

### New open question surfaced during planning

- **OQ-9 — Review altitude (feature vs element).** Post-run review is **feature/file-scoped**,
  but `SemanticVerificationResult` + the `MicroPrimeConfig.semantic_verification_*` hooks are
  **element-scoped** (`element_fqn`). For v1 the SCR reviews at the feature level (feature name →
  `element_fqn`); does requirement compliance need element-granular review for large multi-element
  features, or is feature-level sufficient until the Phase-2 in-run (element-level) hoist? Decide
  the granularity contract so post-run and in-run produce comparable verdicts.

- **OQ-10 — Does structural cross-feature grouping belong in the post-mortem, not the SCR?**
  (Raised by R1-F1-ADV.) FR-11 now scopes to *semantic* grouping; the run-018 symptom was shared
  *structural* `root_cause` with no grouping, which a cheap post-mortem clustering would fix without
  an agent. Decide whether to push structural-cause clustering into `prime_postmortem`.

---

*v0.3 — CRP triage applied (rounds R1–R4, ~21 requirements suggestions; see Appendix A). 12
requirements revised, 1 added (language scope §2), success criteria + OQ-10 added; 0 rejected.
Supersedes v0.2 below.*

*v0.2 — Post-planning self-reflective update. 5 requirements revised (FR-1/6/10/13/15), 1 added
(FR-5a), 8 open questions resolved/reduced, 1 new (OQ-9 altitude). Architecture: a new
`semantic_compliance/` package = the first producer of the dormant `SemanticVerificationResult`
contract; Service Assistant orchestrates post-run; tiered Haiku→Sonnet escalation; advisory→Kaizen.
Ready for optional Convergent Review.*

---

## Appendix: Iterative Review Log (Applied / Rejected Suggestions)

This appendix is intentionally **append-only**. New reviewers (human or model) should add suggestions to Appendix C, and then once validated, record the final disposition in Appendix A (applied) or Appendix B (rejected with rationale).

### Reviewer Instructions (for humans + models)

- **Before suggesting changes**: Scan Appendix A and Appendix B first. Do **not** re-suggest items already applied or explicitly rejected.
- **When proposing changes**: Append them to Appendix C using a unique suggestion ID (`R{round}-F{n}`).
- **When endorsing prior suggestions**: If you agree with an untriaged suggestion from a prior round, list it in an **Endorsements** section after your suggestion table. This builds consensus signal — suggestions endorsed by multiple reviewers should be prioritized during triage.
- **When validating**: For each suggestion, append a row to Appendix A (if applied) or Appendix B (if rejected) referencing the suggestion ID. Endorsement counts inform priority but do not auto-apply suggestions.
- **If rejecting**: Record **why** (specific rationale) so future models don't re-propose the same idea.

### Appendix A: Applied Suggestions

> Triaged by claude-opus-4-8, 2026-06-03 (orchestrator). All 21 requirements suggestions ACCEPTED
> (heavy convergence; none rejected). Applied into the FRs/§1/§2/NR-3/OQ as noted.

| ID | Suggestion | Source | Implementation / Validation Notes | Date |
|----|------------|--------|----------------------------------|------|
| R1-F1 | Quantify FR-5/FR-5a defaults | R1 (table) | FR-5 defaults (threshold 0.5, max 10, token ceiling); FR-5a quota | 2026-06-03 |
| R1-F2 | Define `semantic_compliance_score` formula + range | R1 (table) | FR-8 formula + [0,1] range | 2026-06-03 |
| R1-F3 | FR-10 emit structured suggestion dict, not strings | R1 (table) | FR-10 rewritten (converges S-R1-2/F-R1-4) | 2026-06-03 |
| R1-F4 | Define fail-open/closed verdict semantics | R1 (table) | FR-6: malformed→inconclusive, content-invalid→fail | 2026-06-03 |
| R1-F5 | Concrete FR-11 grouping key | R1 (table) | FR-11: category/contract-id/seed-task-id | 2026-06-03 |
| R1-F6 | Fixed FR-16 metric/span names + units | R1 (table) | FR-16 names/units enumerated | 2026-06-03 |
| F-R1-1 | Triage circularity — structural-emptiness outranks keyword score | R1 (prose) | FR-4 revised | 2026-06-03 |
| F-R1-2 | Capability-level KPI / measurable success | R1 (prose) | §2 Success criteria added | 2026-06-03 |
| F-R1-3 | Feature→seed join key + corroboration | R1 (prose) | FR-1 join key + file-overlap guard | 2026-06-03 |
| F-R1-4 | Advisory vs auto-injection; confidence-gate hints | R1 (prose) | FR-10 confidence-gated; NR-3 clarified | 2026-06-03 |
| F-R1-5 | Secret redaction before prompt assembly | R1 (prose) | FR-3 `security.py` pass-through | 2026-06-03 |
| F-R1-ADV-1 | Re-anchor motivation on false-PASS | R1 (prose) | §1 caveat + OQ-10 (structural grouping → post-mortem) | 2026-06-03 |
| R2-F1 | Declare v1 language scope | R2 | §2: Python-only v1; non-Python→`inconclusive` | 2026-06-03 |
| R2-F2 | Deterministic decoding + default θ | R2 | FR-6 determinism; FR-14 θ default | 2026-06-03 |
| R2-F3 | Reserved PASS-sample quota | R2 | FR-5a reserved quota (anti-starvation) | 2026-06-03 |
| R2-F4 | FR-16 cost reuses CostTracker/CostSummary | R2 | FR-16 reconciliation clause | 2026-06-03 |
| R3-F1 | Exclude third-party/boilerplate from payload | R3 | FR-3 exclusion + max_input_tokens | 2026-06-03 |
| R3-F2 | Flag `suggested_fix` hints advisory; next gen validates | R3 | FR-10 advisory flag | 2026-06-03 |
| R3-F3 | `inconclusive` neutral-excluded from aggregate | R3 | FR-8 denominator exclusion | 2026-06-03 |
| R4-F1 | Max tolerable `inconclusive` rate → SYSTEM_WARNING | R4 | FR-14 <10% bound + warning | 2026-06-03 |
| R4-F2 | FR-11 relative threshold, not absolute ≥2 | R4 | FR-11 ≥2 AND ≥10% | 2026-06-03 |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none yet) |  |  |  |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 (table pass) — claude-opus-4-8 — 2026-06-03

- **Reviewer**: claude-opus-4-8
- **Date**: 2026-06-03 17:29:00 UTC
- **Scope**: First dual-document pass on the requirements (Feature Requirements) — testability, missing acceptance criteria, and interface fidelity to the real Kaizen / K-7 contract seams.

**Executive summary**

- **Unquantified thresholds (high):** FR-5/FR-5a govern cost and false-PASS coverage but state no numeric defaults (suspicion threshold, max-features/token budget, PASS-sample size) — not independently testable.
- **Undefined score function (high):** FR-8's `semantic_compliance_score` is described as "from verdict + confidence + issue severities" with no formula or range, so it cannot be verified or kept stable across runs.
- **Interface drift (medium):** FR-10 says emit "hint strings ... directly into that `prompt_hints` list", but the real Kaizen loop consumes structured suggestion dicts — the requirement bakes in a shape mismatch.
- **Ambiguous error semantics (medium):** FR-6's "(fail-open on format, fail-closed on content)" is asserted but never defined for a verdict (does fail-closed mean `fail` or `inconclusive`?).
- **Ungroupable pattern key (medium):** FR-11 groups on "same requirement/contract" but no concrete identity/key exists for that, unlike `category`.
- **Unbound observability names (medium):** FR-16 lists OTel attributes generically; without fixed metric/span names and units, dashboards and the SDK OTel bridge cannot reliably bind.
- **Note:** OQ-9 (feature↔element altitude) is still open yet FR-13 depends on it — the corresponding plan-side fix is tracked as R1-S4 in the plan file.

##### First pass

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F1 | Validation | high | Quantify FR-5/FR-5a: give default suspicion threshold, escalation budget (max features and/or max token cost), and PASS-sample size, with units. | "deep-review ... only features above a configurable suspicion threshold, bounded by a per-run escalation budget (max features and/or max token cost)" has no defaults, so neither cost discipline nor coverage is testable. | FR-5, FR-5a | Acceptance test pins defaults and asserts review count respects them. |
| R1-F2 | Data | high | Define the exact `semantic_compliance_score` formula and output range. | FR-8 says the score derives "from verdict + confidence + issue severities" but gives no function — two implementers would produce incomparable scores; the run-level aggregate is also undefined. | FR-8 ("a per-feature `semantic_compliance_score`") | Deterministic unit test: fixed verdict+confidence+issues → fixed score; documented range (e.g. 0.0–1.0). |
| R1-F3 | Interfaces | medium | Restate FR-10 to emit the structured Kaizen suggestion record (pattern_type / suggested_action / config_key / phase / confidence / auto_applicable), not bare "hint strings". | "emit ... hint strings templated from each issue's `suggested_fix` directly into that `prompt_hints` list" mismatches `generate_kaizen_suggestions`, which produces suggestion dicts the loop consumes. | FR-10 | Schema-conformance test against the existing suggestion-dict shape. |
| R1-F4 | Risks | medium | Define FR-6 "fail-open on format, fail-closed on content" concretely: which verdict results on malformed JSON vs on a well-formed but content-invalid response. | "(fail-open on format, fail-closed on content)" is undefined for a verdict; `from_json` auto-corrects unknown verdicts to `inconclusive`, which may contradict "fail-closed". | FR-6 | Two tests: bad format → defined verdict; invalid content → defined verdict (e.g. `inconclusive`/`fail`). |
| R1-F5 | Validation | medium | Specify the grouping key for FR-11's "violate the same requirement/contract" (e.g. issue `category`, contract id, or seed task id). | "≥2 features share a semantic gap category **or violate the same requirement/contract**" — `category` is concrete, but "same requirement/contract" has no defined identity to group on. | FR-11 | Grouping test: two features with the same contract id emit one cross-feature pattern. |
| R1-F6 | Ops | medium | Enumerate FR-16's concrete metric/span names and units (e.g. `scr.cost_usd` unit, span name) and align with the existing OTel bridge conventions. | FR-16 lists attributes generically; without fixed names/units dashboards and the SDK's OTel bridge cannot bind to them reliably. | FR-16 | Test asserts emitted span/metric names match a documented list. |

**Endorsements** (prior untriaged suggestions this reviewer agrees with):
- (none — first review round; no prior suggestions exist.)

#### Review Round R1 (prose pass) — claude-opus-4-8 — 2026-06-03

Requirements-side review (F-prefix). Suggestions are anchored to specific FRs; the orchestrator
triages ACCEPT/REJECT afterward (not done here).

- **F-R1-1 — Triage circularity: the gate signal is the signal under indictment (FR-4/FR-5/FR-5a).**
  FR-4 ranks suspicion partly by `requirement_score`, but §1 says that score is *too shallow to
  trust*. A semantically-empty-but-keyword-rich PASS (the run-018-style false-PASS) scores HIGH on
  `requirement_score` → ranks LOW suspicion → is skipped by FR-5, leaving only FR-5a's bounded
  random sample as the safety net for the capability's core value case. **Fix:** state that the
  triage MUST NOT down-weight suspicion on high `requirement_score` alone; weight structural-
  emptiness signals (`fake_work_stub`, large positive `assembly_delta`, low `disk_quality_score`)
  *above* keyword score. Add a test: a high-`requirement_score` + `fake_work_stub` feature must
  rank high-suspicion.

- **F-R1-2 — No capability-level success metric (FR-8, §2 Goals).** FR-8 defines a per-feature
  `semantic_compliance_score`, but nothing defines what "produces better semantically compliant
  code" (the stated goal) means *measurably*. Without a baseline/target you cannot distinguish a
  working SCR from one that only adds cost. **Fix:** add an FR (or §2 success criteria) defining a
  KPI — e.g. "SCR-sourced Kaizen hints raise the *next* run's mean `requirement_score`/compliance
  by ≥X on a fixed replay set" and "false-PASS detection rate ≥Y on a labeled set" — and require the
  report to carry the inputs to compute it.

- **F-R1-3 — Feature→seed-task join key is unspecified and is a confident-wrong-verdict hazard
  (FR-1).** FR-1 says "map the feature to its seed task by id" but does not name the key. run-018
  features are `PI-00n`; `FeaturePostMortem.feature_id`, seed `tasks[].id`/`task_id`, and the
  `PI-` ids may not be the same namespace. A silent mis-join makes the SCR review code against the
  **wrong requirement** — strictly worse than `requirement_text_unavailable`, because it yields a
  confident verdict on a false premise. **Fix:** name the exact join key; require a corroboration
  guard (e.g. mapped task's `target_files` must overlap the feature's `generated_files`); on
  ambiguous/empty overlap → `inconclusive` with reason `requirement_join_ambiguous`.

- **F-R1-4 — "Advisory" is contradicted by automatic prompt injection (FR-10 vs NR-1/NR-3).**
  FR-14/NR-1/NR-3 frame the SCR as advisory and "never acts," yet FR-10 *automatically* writes
  hints into `kaizen-suggestions.json` that are injected into the next run's prompt. Injecting a
  hint **is** an automated action on the pipeline, and a single-shot cheap-tier false-`fail`
  (FR-6 default) becomes a self-reinforcing prompt poison. **Fix:** gate hint emission on
  confidence (emit only above θ or only Sonnet-confirmed verdicts), and/or tag SCR hints as
  low-priority/removable so a bad hint can't dominate. Reconcile the NR-3 wording with FR-10.

- **F-R1-5 — No redaction of secrets in reviewed code/requirements (FR-3/FR-7).** Generated code
  (FR-3) and requirement text go verbatim into the review prompt, possibly to a hosted model.
  **Fix:** require pass-through of the existing `security.py` redaction before prompt assembly, or
  explicitly scope it out in §4 with a rationale.

##### Stress-test / adversarial pass (R1)

- **F-R1-ADV-1 — The motivating example does not exercise the capability's unique value.** §1 and
  the plan's acceptance anchor lean on run-018, but run-018 is a **true FAIL** (`cross_file_contract`,
  already caught structurally) — the post-mortem's only miss was *grouping* 6 shared-cause failures
  into one pattern. That grouping is achievable far more cheaply by clustering shared `root_cause`
  in the existing post-mortem (no agent). The SCR's genuinely *unique* value is **false-PASS**
  detection (FR-5a) — for which there is currently **no worked example or labeled case**.
  **Challenge:** either (a) re-anchor the motivation on a real false-PASS instance, or (b) justify
  the agent cost when a deterministic root-cause-clustering fix would resolve the run-018 symptom.
  If (b) cannot be met, FR-11's cross-feature grouping may belong in the post-mortem, not the SCR.

#### Review Round R2 — claude-opus-4-8 — 2026-06-03

- **Reviewer**: claude-opus-4-8
- **Date**: 2026-06-03 17:33:00 UTC
- **Scope**: Second pass (fresh reviewer), requirements side. Deduped against both R1 rounds (`R1-F*` and `F-R1-*`). New ground: multi-language scope, decoding determinism + θ default, false-PASS budget reservation, and cost attribution reuse. Endorses prior items rather than restating.

**Executive summary**

- **Multi-language scope undeclared (high, novel):** no FR states whether v1 covers all 6 SDK languages or Python-only; FR-7's rubric and the `element_fqn` convention are language-shaped. Neither R1 round flagged this.
- **Determinism + θ default (medium):** FR-6 leaves decoding nondeterministic and OQ-8's θ undefined; both must be pinned so verdicts are cacheable (S-R1-2) and the gate is calibratable (extends F-R1-4).
- **False-PASS anti-starvation (medium):** FR-5a should mandate a reserved review quota independent of the FR-5 suspect budget (complements F-R1-1's ranking fix).
- **Cost attribution reuse (low):** FR-16's `scr.cost_usd` should reconcile with the run's existing per-feature `cost_usd`/`CostSummary`.

##### First pass

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R2-F1 | Architecture | high | Add a requirement declaring the v1 language scope: either all 6 SDK languages (with per-language rubric + `element_fqn` convention) or explicitly Python-only with the rest deferred. | FR-7's rubric and `element_fqn` (OQ-9) are implicitly Python; the SDK generates Go/Node/Vue/Java/C#. Without a scope statement, implementers will silently build a Python-only reviewer that mis-verdicts other languages. | FR-7; §2 Goals/Non-Goals | Requirement names the in-scope languages; a non-Python fixture has a defined expected behavior. |
| R2-F2 | Validation | medium | Require deterministic reviewer decoding (temperature/seed) and define a default θ for the future `STARTD8_SEMANTIC_GATE`, so advisory verdicts are reproducible and the gate is calibratable. | FR-6 is single-shot but says nothing about determinism; OQ-8 carries θ with no default. Determinism is also a precondition for the proposed verdict cache (S-R1-2). Extends F-R1-4. | FR-6; FR-14 / OQ-8 | Two-run reproducibility test; θ default documented and unit-checked. |
| R2-F3 | Risks | medium | Strengthen FR-5a to mandate a reserved PASS-sample quota independent of the FR-5 suspect escalation budget (anti-starvation). | FR-5a is the only safety net for false-PASS (the capability's unique value per F-R1-ADV-1); if it shares the FR-5 budget, a suspect-heavy run zeroes it. | FR-5a | Test: a budget-saturating suspect set still reviews the reserved PASS quota. |
| R2-F4 | Ops | low | Require FR-16's cost metric to reuse the existing per-feature `cost_usd` / `CostSummary` accounting so `scr.cost_usd` reconciles with run cost rather than being independently estimated. | Avoids a divergent second cost number; the post-mortem already tracks per-feature cost. | FR-16 | Test: SCR cost metric equals the sum debited from the shared cost tracker. |

**Endorsements & Disagreements**

**Endorsements** (untriaged prior items this round agrees with):
- F-R1-1 (triage circularity — don't down-weight suspicion on high `requirement_score`) — core correctness; R2-F3 builds on it.
- F-R1-2 (capability-level KPI / measurable success) — without it the feature is unfalsifiable.
- F-R1-3 (feature→seed join key + corroboration) — highest-value robustness item; a mis-join yields confident-wrong verdicts.
- F-R1-4 (advisory vs auto-injection; gate hint emission on confidence) — R2-F2 extends it with determinism + θ default.
- F-R1-5 (secret redaction before prompt assembly) — agree; reuse existing `security.py`.
- F-R1-ADV-1 (re-anchor motivation on a real false-PASS case) — agree; this is the capability's unique value.
- Convergence: R1-F3 (Kaizen emits structured dicts, not strings) and F-R1-4 (advisory contradiction) both target FR-10 from different angles — prioritize FR-10 in triage.

**Disagreements**: none.

#### Review Round R3 — claude-opus-4-8 — 2026-06-03

- **Reviewer**: claude-opus-4-8
- **Date**: 2026-06-03 17:41:00 UTC
- **Scope**: Third pass (fresh reviewer), requirements side. Focuses on input token economy, robust error impact on scoring, and safeguarding downstream runs from hallucinated syntax in Kaizen hints.

**Executive summary**

- **Context payload optimization (high):** FR-3 lacks exclusion logic for boilerplate and third-party code. Loading un-filtered outputs bloats the prompt and increases cost unnecessarily.
- **Kaizen hint build-breaking hazard (high):** FR-10 emits `suggested_fix` directly as prompt hints. LLM-hallucinated fixes inject invalid syntax into future runs, breaking builds.
- **Scoring ambiguity for neutral verdicts (medium):** FR-8 does not clarify if an `inconclusive` verdict (e.g. from FR-1) degrades the score, penalizes the run, or is gracefully ignored in the compliance denominator.

##### First pass

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R3-F1 | Data | high | Explicitly exclude known third-party and boilerplate code from the generated-output retrieval. | FR-3 says "load the generated code for the feature". Without filtering, the context window is dominated by boilerplate, inflating cost and risking context overflow. | FR-3 | Unit test ensuring known boilerplate files are stripped from the assembly payload. |
| R3-F2 | Validation | high | Mandate that `suggested_fix` hints generated via FR-10 are flagged as "advisory" in the prompt text, instructing the next generation to syntactically validate the hint. | Blindly injecting LLM-generated fixes via `prompt_hints` can break future compilation if the hint contains hallucinated APIs or invalid syntax. | FR-10 | Test: Inject a syntactically invalid Kaizen hint and verify the downstream system warns or corrects rather than breaking the build. |
| R3-F3 | Validation | medium | Specify the scoring treatment of an `inconclusive` verdict in the `semantic_compliance_score` formula. | FR-8 derives the score from verdict, but an `inconclusive` verdict (due to FR-1 missing text or FR-4 parse failure) must have a defined impact (e.g., neutral exclusion) so it doesn't artificially crash the score. | FR-8 | Score calculation test asserts that `inconclusive` verdicts omit the feature from the run's aggregate denominator instead of scoring it as 0. |

**Endorsements & Disagreements**

**Endorsements**:
- R2-F1 (Multi-language scope) — agree. Python-only rubrics limit the SDK.
- R2-F2 (Determinism + default θ) — fully agree. The gateway must be robust and replicable.
- F-R1-3 (Join Key Corroboration) — agree. A silent mis-join is a critical failure.

**Disagreements**: none.

#### Review Round R4 — claude-opus-4-8 — 2026-06-03

- **Reviewer**: claude-opus-4-8
- **Date**: 2026-06-03 17:43:00 UTC
- **Scope**: Fourth pass (fresh reviewer), requirements side. Focuses on preventing silent degradation from `inconclusive` states and scaling cross-feature patterns for large runs.

**Executive summary**

- **Silent gate degradation (high):** FR-14 establishes a future semantic gate based on verdict and confidence. If a high percentage of features return `inconclusive` (e.g. due to FR-1 missing text), the gate silently fails open. A threshold for acceptable `inconclusive` rates is required.
- **Pattern spam at scale (medium):** FR-11 triggers cross-feature patterns at an absolute threshold of "≥2 features". In a run of 200 features, 2 is statistical noise, not a pattern. A dynamic or percentage-based threshold is needed to preserve Kaizen signal quality.

##### First pass

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R4-F1 | Risks | high | Add a requirement setting a maximum tolerable `inconclusive` rate (e.g., <10% of escalated features). Exceeding this rate should trigger a `SYSTEM_WARNING`. | Without an upper bound, systemic failures (e.g. a broken post-mortem parse or missing seed files) will result in 100% `inconclusive` verdicts, silently neutralizing the compliance capability and future gates. | FR-14 | Test: A run where 50% of features map to `inconclusive` emits a `SYSTEM_WARNING` event. |
| R4-F2 | Data | medium | Update the FR-11 cross-feature pattern threshold from a static "≥2 features" to a relative/scaled threshold (e.g., "≥2 features AND ≥10% of escalated features"). | A hardcoded 2 is significant for a 5-feature run but noise for a 200-feature run. Emitting a pattern for 1% of features dilutes the Kaizen feedback loop. | FR-11 | Test: In a run with 100 escalated features, 2 sharing a root cause does not emit a pattern, but 10 does. |

**Endorsements & Disagreements**

**Endorsements**:
- R3-F1 (Filter boilerplate) — agree. Context window saturation is a real risk.
- R3-F2 (Advisory flag for hints) — critical to prevent hallucination poisoning.
- R2-F1 (Declare language scope) — essential context for the reviewing rubric.

**Disagreements**: none.
