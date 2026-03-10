# Keiyaku Design Principle

Purpose: establish a cross-cutting design principle for agent-to-agent communications in the startd8-sdk pipeline — every message between agents must be a typed, validated contract, not unstructured prose.

This document is intentionally living guidance. Update it as new A2A boundaries are identified.

---

## The Principle

**Keiyaku** (契約) — "contract" or "binding agreement." In Japanese business culture, a keiyaku is not merely a handshake or verbal understanding — it is a formal, written agreement with explicit terms that both parties can independently verify. Ambiguity in a keiyaku is a defect, not a feature.

Applied to the pipeline: **every message passed from one agent to another must conform to a typed schema that the receiving agent can validate before acting on it. Unstructured text — markdown tables, prose paragraphs, or implicit formatting conventions — is not a contract. When agents communicate through text that "looks right" but has no enforceable structure, the pipeline is one LLM mood swing away from a silent failure.**

---

## Relationship to Other Principles

| Principle | Focus | Keiyaku Interaction |
|-----------|-------|---------------------|
| **Mottainai** | Don't discard artifacts (within a run) | Keiyaku ensures forwarded artifacts have a schema the receiver can consume — forwarding without a contract is forwarding noise |
| **Kaizen** | Don't discard lessons (across runs) | Keiyaku failures produce structured diagnostics (`reason` + `next_action`) that feed Kaizen's observation loop — unstructured failures produce grep-worthy strings at best |
| **Warm Up** | Don't discard context (across toolchain transitions) | Keiyaku schemas are the portable context — a backup tool can validate and produce the same contract shape without needing the primary tool's session memory |
| **Ichigo Ichie** | First-run quality | Keiyaku validation catches malformed agent output on the first run, not after a human notices the markdown table was silently mangled |

Together the five principles form a complete anti-waste strategy:
- **Mottainai** — don't waste artifacts (within a run)
- **Kaizen** — don't waste lessons (across runs)
- **Warm Up** — don't waste context (across tool transitions)
- **Ichigo Ichie** — don't waste first-run quality on memorized fixes
- **Keiyaku** — don't waste agent output on ambiguous communication

---

## Why This Matters

The startd8-sdk pipeline involves multiple agents communicating at phase boundaries: plan ingestion hands off to architectural review, review hands off to design, design hands off to implementation. At each boundary, one agent produces output that another agent must consume and act on.

When that communication happens through unstructured text, three failure modes emerge:

### 1. Silent Format Mutation

LLMs are not deterministic text formatters. A prompt that says "output a markdown table with these exact column headers" works 90% of the time. The other 10%:
- Column names are synonyms (`Suggestion` vs `Description` vs `Recommendation`)
- Columns are reordered
- Bold/italic formatting is added to headers
- The table is wrapped in a code fence
- The output is valid but uses a different structure entirely

**Run-019 evidence:** `claude-opus-4-6` produced a review table where, after alias mapping against 30+ synonyms, 3 of 5 core columns were still unrecognized. Both the initial attempt and the retry failed identically. The entire reviewer was skipped — zero suggestions produced from a multi-dollar LLM call.

### 2. Invisible Contract Drift

When the contract between agents is defined only in prompt instructions, changes to the prompt silently change the contract. There is no schema version, no validation, and no way for the consuming agent to detect that the producing agent's output shape has changed.

### 3. Validation by Regex

Consuming agents that parse unstructured text end up with increasingly complex regex/alias-map/positional-fallback logic. This validation code is brittle, hard to test exhaustively, and silently permissive — it tends to accept malformed input rather than reject it, because the alternative is rejecting valid output that happens to use unexpected formatting.

---

## The Keiyaku Contract

Every agent-to-agent boundary in the pipeline MUST follow these rules:

### Rule 1: Schema-First Communication

The producing agent is prompted to output a typed data structure (JSON wrapped in fences). The schema is defined once and shared between the prompt template, the validator, and the consumer.

```
WRONG:  "Output a markdown table with columns: ID, Area, Severity, Suggestion, Rationale"
RIGHT:  "Return a JSON object wrapped in ```json fences with this structure: { ... }"
```

### Rule 2: Validate Before Consume

The receiving agent validates the incoming message against the schema before acting on it. Invalid messages are rejected with a structured error that includes:
- **What failed** — which field, what was expected
- **Why it matters** — the downstream consequence of the malformed field
- **What to do** — actionable remediation (retry prompt, fallback, escalate)

This follows ContextCore's A2A pattern: every `GateResult` includes `reason`, `next_action`, and `evidence`.

### Rule 3: Render for Humans, Validate for Machines

Structured data is validated programmatically, then rendered into human-readable format (markdown, tables, prose) for document output. The rendering is a **display concern** — it never participates in the validation chain.

```
Producer → JSON → Schema Validate → Structured Dict → Consumer
                                   ↓
                              Render Markdown → Document (display only)
```

### Rule 4: Dual-Format Transition

When migrating an existing boundary from unstructured to structured communication:
1. Accept both formats (JSON-first, legacy fallback)
2. Log which format was used (for Kaizen metrics)
3. Set a deprecation timeline for the legacy format
4. Rendered output from the new format MUST pass the old validator (round-trip safety)

### Rule 5: Fail-Open on Format, Fail-Closed on Content

Accept any reasonable serialization (JSON, YAML, even markdown if it parses correctly). Reject when required fields are missing or values are outside the allowed set. Auto-correct when the fix is unambiguous (e.g., wrong round number in suggestion ID). Warn — but don't reject — on non-standard values that don't break downstream processing.

### Rule 6: ContextCore Alignment Without Coupling

Align enum values, field semantics, and error patterns with ContextCore's A2A contract types (`GateResult`, `HandoffContract`, `ValidationErrorEnvelope`) where applicable. Do NOT create import-time dependencies on `contextcore.contracts`. The alignment is conceptual — shared vocabulary, compatible severity enums, analogous field names — not a package dependency.

| Keiyaku Field | ContextCore Equivalent | Alignment |
|---------------|----------------------|-----------|
| `severity` | `GateSeverity` enum | Values match: `critical`, `high`, `medium`, `low` |
| `rationale` / `reason` | `GateResult.reason` | Same purpose: why this matters |
| `next_action` | `GateResult.next_action` | Same purpose: what to do about it |
| `evidence` | `GateResult.evidence[]` | Same purpose: proof of the claim |
| error codes | `ValidationErrorEnvelope.error_code` | Same pattern: enumerated, actionable |

---

## Existing Violations (Baseline)

### Violation 1: Architectural Review Suggestions — RESOLVED (RV-9xx)

**Boundary:** Reviewer LLM → Validation Layer → Document

**Before:** Prompt instructed LLM to produce markdown table with exact column headers. Validator used 30+ alias mappings and positional fallback to parse columns. Failed when LLM used unrecognized synonyms.

**After (RV-9xx):** Prompt instructs LLM to produce JSON object with typed fields. Dual-format validator tries JSON first, falls back to markdown. JSON is schema-validated, then rendered to markdown for document append. Rendered markdown passes the legacy validator (round-trip safe).

**Evidence:** Run-019 produced zero suggestions due to column header mismatch. Post-RV-9xx, the same reviewer output parses correctly via JSON path.

### Violation 2: Triage Classification

**Boundary:** Reviewer LLM → Triage Validator

**Status:** Already uses JSON (pre-Keiyaku). The triage step was implemented with structured output from the start. This is the positive example that motivated extending the pattern to the review step.

### Violation 3: DESIGN Phase Handoff

**Boundary:** Design LLM → Implementation Seed

**Status:** Partially structured. The `HandoffConfig` model provides schema, but design output is serialized as markdown prose within the handoff file. The implementation agent parses this prose to extract architectural decisions, component lists, and interface contracts.

**Risk:** Same class of failure as Violation 1 — the design LLM may produce valid architectural content in an unparseable format.

### Violation 4: Complexity Classification Signals

**Boundary:** Signal Extractor → Classifier

**Status:** Structured (uses `TaskComplexitySignals` dataclass). Not a violation — included as a positive example.

### Violation 5: Forward Manifest Contracts

**Boundary:** Extractor → Validator → Review Phase

**Status:** Structured (uses `ForwardManifest`, `InterfaceContract` Pydantic models). Not a violation — included as a positive example.

### Violation 6: Escalation Context — RESOLVED (K-6, REQ-MP-513)

**Boundary:** Local Ollama → Cloud model escalation

**Before:** Prose `## Prior Local Model Attempt` injection — cloud model received unstructured failure context.

**After:** `EscalationHandoff.to_prompt_section()` produces JSON + summary; `prime_adapter.py` uses structured handoff when present, prose fallback otherwise.

### Violation 7: Repair Diagnostics at Boundary — RESOLVED (K-9, REQ-MP-604)

**Boundary:** Repair pipeline → Escalation context

**Before:** `RepairStepResult` typed internally, serialized as flat `steps_applied: list[str]` at boundary.

**After:** `EscalationRepairOutcome` with per-step `RepairStepOutcome` records, `to_dict()` serialization.

### Violation 8: Classification Signals — RESOLVED (K-10, D-1)

**Boundary:** `classify_tier()` → Decomposer

**Before:** Returns `(ComplexityTier, str)`, signals discarded.

**After:** Returns `ClassificationResult` with `.signals` field; threaded to decomposer via `complexity_signals` parameter.

### Violation 9: Semantic Verification — CONTRACT DEFINED (K-7, REQ-MP-504)

**Boundary:** Semantic verifier LLM → Engine decision

**Status:** `SemanticVerificationResult` contract defined in `models.py`; will be consumed when capability A2 is wired.

---

## Candidate Boundaries for Migration

The following agent-to-agent boundaries currently use unstructured communication and are candidates for Keiyaku migration:

| # | Boundary | Current Format | Risk | Priority |
|---|----------|---------------|------|----------|
| K-1 | DESIGN output → IMPLEMENT seed | Markdown prose in handoff file | High — design decisions lost in parsing | High |
| K-2 | IMPLEMENT output → INTEGRATE validation | File paths + code in generation result | Medium — structured via `GenerationResult` but content is unvalidated | Medium |
| K-3 | REVIEW output → FINALIZE report | Review score + prose feedback | Medium — score is numeric but feedback is unparsed | Medium |
| K-4 | Plan ingestion PARSE → ASSESS | Feature list as dicts | Low — already structured | Low (validation hardening only) |
| K-5 | Multi-file code extraction | Regex + 4-layer heuristic | Medium — battle-tested but fragile on novel formats | Low (Kaizen-triggered) |
| K-6 | Local → Cloud escalation | Prose "## Prior Attempt" injection | Medium — cloud model gets unstructured failure context | Medium |
| K-7 | Semantic verification output | Unwired (A2 in audit) — no contract defined | High — define before wiring | High |
| K-8 | LLM-assisted decomposition | Not yet implemented — no contract defined | Medium — define before building | Medium |
| K-9 | Repair diagnostics at boundary | Typed internally, degrades to prose at escalation boundary | Low-Medium — internal data exists but isn't forwarded structured | Medium |
| K-10 | Classification signals → Decomposer | Tier enum only — signals discarded | High — blocks FunctionChainStrategy | High |

See [Micro Prime Keiyaku Gap Analysis](../design/micro-prime/KEIYAKU_GAP_ANALYSIS.md) for detailed analysis of K-5 through K-10.

---

## Implementation Strategy

### Phase 1: Document and Classify (This Document)

Inventory all agent-to-agent boundaries. Classify each as:
- **Structured** — already uses typed schema (no action needed, verify validation)
- **Semi-structured** — uses typed container with unstructured content fields (extract and schema-validate content)
- **Unstructured** — uses prose/tables/markdown (full Keiyaku migration needed)

### Phase 2: Migrate High-Risk Boundaries

Apply the dual-format transition pattern (Rule 4) to each unstructured boundary, starting with K-1 (DESIGN → IMPLEMENT handoff). Each migration follows:

1. Define the JSON schema for the boundary
2. Update the producer's prompt to request JSON output
3. Implement dual-format validator (JSON-first, legacy fallback)
4. Implement renderer (JSON → human-readable for document output)
5. Add round-trip test (rendered output passes legacy validator)
6. Add Kaizen metric: format used per boundary per run

### Phase 3: Observability

Emit structured telemetry at every validated boundary:
- `a2a.boundary.format` — `json` or `legacy` (for tracking migration progress)
- `a2a.boundary.validation_result` — `pass`, `fail_recovered`, `fail_rejected`
- `a2a.boundary.auto_corrections` — count of fields auto-corrected (for prompt quality feedback)

This aligns with ContextCore's 8-panel A2A Governance Dashboard pattern and feeds the Kaizen improvement loop.

---

## Checklist: Keiyaku Compliance

Before declaring an agent-to-agent boundary "Keiyaku compliant":

- [ ] Producer prompt requests JSON output with explicit schema example
- [ ] Consumer validates JSON against schema before processing
- [ ] Validation errors include `reason`, `next_action`, and failed field path
- [ ] Human-readable rendering is a separate step (display only, not in validation chain)
- [ ] Legacy format accepted as fallback during transition (if applicable)
- [ ] Rendered output passes legacy validator (round-trip safe)
- [ ] Auto-corrections logged at WARNING level (for Kaizen feedback)
- [ ] Rejections logged at ERROR level with full payload for diagnosis
- [ ] Format used (`json` vs `legacy`) emitted as telemetry attribute
- [ ] Severity/area enums aligned with ContextCore `GateSeverity`/`Phase` where applicable
- [ ] No import-time dependency on `contextcore.contracts`

---

## Anti-Patterns

### Anti-Pattern 1: "The Prompt Is the Contract"

Prompt instructions are suggestions to an LLM, not enforceable contracts. A prompt that says "use these exact column headers" is a hope, not a guarantee. The contract must exist as code (a validator) that runs independently of the prompt.

### Anti-Pattern 2: "Alias Maps Scale"

When a validator needs 30+ synonym mappings to handle LLM output variation, the problem is not insufficient aliases — it is the wrong serialization format. Adding more aliases is treating symptoms while the disease (unstructured communication) persists.

### Anti-Pattern 3: "Positional Fallback"

"If the column names don't match, assume standard order" — this silently accepts malformed output as valid, making debugging impossible. The LLM produced the wrong shape, and the pipeline pretended it didn't.

### Anti-Pattern 4: "Validate in the Renderer"

Mixing validation logic with display rendering makes both untestable and couples format changes to validation changes. Validate the data structure. Then render it. Separately.

### Anti-Pattern 5: "One Schema Fits All Agents"

Different agent boundaries carry different data. Don't force all communication through a single generic schema. Each boundary gets its own contract, sized to what that specific handoff needs.

---

## Reference Implementation: RV-9xx (Architectural Review)

The RV-9xx implementation in `architectural_review_log_helpers.py` serves as the reference Keiyaku migration:

| Component | Location | Purpose |
|-----------|----------|---------|
| JSON schema | `prompts/architectural_review.yaml` `review:` template | Producer prompt with JSON example |
| JSON validator | `_validate_json_review()` | Schema validation with auto-corrections |
| Dual-format dispatcher | `_validate_review_output()` | JSON-first, markdown fallback |
| Renderer | `_render_review_json_to_markdown()` | Validated JSON → markdown table |
| Retry prompt | `architectural_review_log_workflow.py` L668–698 | JSON schema in retry instructions |
| Round-trip test | `test_structured_review_output.py` | Rendered markdown passes `_validate_snippet()` |
| Field defaults | `_SUGGESTION_FIELD_DEFAULTS` dict | Auto-correction for missing optional fields |
| Constants | `architectural_review_log_constants.py` | Shared severity/area enums |

Future Keiyaku migrations should follow this same component structure.

---

## Relationship to ContextCore A2A

ContextCore's A2A governance layer (`contextcore.contracts.a2a`) provides the theoretical foundation for Keiyaku:

| ContextCore Concept | Keiyaku Application |
|---------------------|---------------------|
| 4 contract types (`TaskSpanContract`, `HandoffContract`, `ArtifactIntent`, `GateResult`) | Keiyaku boundaries don't need all 4 — most map to `HandoffContract` (delegation) or `GateResult` (validation outcome) patterns |
| `validate_outbound()` / `validate_inbound()` | Rule 2: validate before consume. Keiyaku applies the same pattern at internal pipeline boundaries, not just cross-system boundaries |
| `ValidationErrorEnvelope` with `error_code`, `failed_path`, `next_action` | Rule 2: structured error with what/why/what-to-do |
| Defense-in-depth (6 principles) | Keiyaku embeds principles 1 (validate at every boundary) and 4 (fail loud, fail early, fail specific) |
| Three Questions diagnostic | Keiyaku failures should be diagnosable by layer: was the prompt wrong (producer), the output malformed (LLM), or the validator too strict (consumer)? |
| Schema versioning (`v1` frozen) | Keiyaku schemas should be versioned and immutable once deployed — additive changes require a new version |

**Key difference:** ContextCore A2A governs **cross-system** boundaries (export → plan-ingestion → contractor). Keiyaku governs **intra-pipeline** boundaries (reviewer → validator, design → implementation) using the same principles at a finer granularity.
