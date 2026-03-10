# Micro Prime Capability Audit — Unwired Features, Quick Wins, and Tuning Opportunities

**Date:** 2026-03-09
**Source:** Deep audit of `src/startd8/micro_prime/`, `src/startd8/complexity/`,
`src/startd8/element_registry.py`, and associated test suites
**Design Principle Review:** All items pass the [Ichigo Ichie test](../../design-princples/ICHIGO_ICHIE_DESIGN_PRINCIPLE.md) —
each improves first-run quality for any project, not just calibration re-runs.

---

## Overview

The Micro Prime subsystem is ~85% wired. The core tiers (TRIVIAL/SIMPLE/MODERATE/COMPLEX),
template registry, Ollama generation, repair pipeline, splicing, and circuit breaker are
all operational. This audit identifies capabilities that are **built but not connected**,
config flags that gate **fully implemented features**, and small changes that would
**measurably improve output quality or reduce cost**.

### Architecture Snapshot

```
          ┌─────────────────────────────────────────────────┐
          │              MicroPrimeEngine                    │
          │                                                  │
          │  process_element()                               │
          │       │                                          │
          │       ▼                                          │
          │  classify_tier() ──→ (tier, reason)              │
          │       │                ↑                         │
          │       │          TaskComplexitySignals            │
          │       │          (DISCARDED after classify) ← D1 │
          │       ▼                                          │
          │  ┌──────────────────────────────────────┐       │
          │  │ TRIVIAL → _handle_trivial()          │       │
          │  │   └─ TemplateRegistry.match()        │       │
          │  │                                      │       │
          │  │ SIMPLE → _handle_simple()            │       │
          │  │   ├─ FunctionBodyDecomposer ← A3     │       │
          │  │   ├─ _generate_ollama()              │       │
          │  │   ├─ run_repair_pipeline()           │       │
          │  │   └─ _semantic_verify() ← A2         │       │
          │  │                                      │       │
          │  │ MODERATE → _handle_moderate()        │       │
          │  │   ├─ ClassDecomposeStrategy  ✅       │       │
          │  │   └─ FunctionChainStrategy  ← D1     │       │
          │  │                                      │       │
          │  │ COMPLEX → immediate escalation       │       │
          │  └──────────────────────────────────────┘       │
          └─────────────────────────────────────────────────┘
                    │
                    ▼
          MicroPrimeCodeGenerator (prime_adapter.py)
                    │
                    ├─ DeterministicFileAssembler ← A1
                    ├─ _delegate_to_fallback()
                    │     └─ ComplexityRouter.select_agent_spec() ← D3
                    └─ ElementRegistry
                          ├─ write_run_metrics() ← D4
                          ├─ elements_by_status() ← F1
                          └─ element_lineage() ← F2
```

Items marked with `←` are the improvement opportunities documented below.

---

## Category A: Near-Ready Capabilities (Config Flip / Minimal Wiring)

### A1: Wire DFA Pre-Fill to Element Registry

**Effort:** ~5 lines across 5 call sites | **Impact:** HIGH

**Problem:** `DeterministicFileAssembler` accepts an `element_registry` constructor
parameter and has pre-fill logic (REQ-MP-1106) that uses cached implementations
to populate skeletons instead of `raise NotImplementedError`. But none of the
5 instantiation sites pass a registry:

| Call Site | File | Line |
|-----------|------|------|
| 1 | `micro_prime/prime_adapter.py` | 1256 |
| 2 | `micro_prime/repair.py` | 696 |
| 3 | `micro_prime/engine.py` | 2017 |
| 4 | `contractors/context_seed/phases/scaffold.py` | 189 |
| 5 | `workflows/builtin/plan_ingestion_workflow.py` | 4040 |

**Fix:** Pass `element_registry=self._element_registry` at each call site
where a registry is available. Sites 1-3 are in the micro_prime package
where the registry is already instantiated. Sites 4-5 may not have a
registry in scope — pass `None` (the parameter is already optional).

```python
# prime_adapter.py:1256
assembler = DeterministicFileAssembler(element_registry=self._element_registry)

# engine.py:2017
assembler = DeterministicFileAssembler(element_registry=self._element_registry)

# repair.py:696 — registry may not be in scope
assembler = DeterministicFileAssembler(element_registry=None)
```

**What this unlocks:** Within a single multi-feature run, elements generated
for earlier features pre-fill skeletons for later features. The first feature
still generates from scratch, but subsequent features that share elements
(e.g., shared utility classes, common patterns) get pre-filled bodies instead
of `raise NotImplementedError` stubs.

---

### A2: Enable Semantic Verification

**Effort:** Config toggle | **Impact:** MEDIUM

**Problem:** A complete semantic verification engine exists in
`engine.py:1881-1954` (REQ-MP-512). Two modes:

1. **Custom function hook** — `semantic_verification_fn` callback
2. **LLM-based verification** — Uses a separate agent to verify generated
   code against element contracts and binding constraints

On failure, the element is escalated to cloud with
`EscalationReason.SEMANTIC_FAILURE`. Fully implemented but gated behind
`semantic_verification_enabled: false` in `MicroPrimeConfig` (`models.py:181`).

**Configuration:**
```json
{
    "semantic_verification_enabled": true,
    "semantic_verification_agent_spec": "anthropic:claude-sonnet-4-20250514",
    "semantic_verification_max_tokens": 256,
    "semantic_verification_temperature": 0.0,
    "semantic_verification_prompt_max_chars": 4000
}
```

**Trade-off:** Adds one LLM call per element (~$0.003-0.01 at Sonnet pricing).
For projects where correctness matters more than cost, this catches hallucinated
APIs, wrong method signatures, and contract violations before they reach output.

**Keiyaku note (K-7):** `SemanticVerificationResult` contract is now defined in `micro_prime/models.py` as the typed boundary contract for LLM verification output. When wiring A2, use this contract for LLM output validation instead of ad-hoc parsing. See [KEIYAKU_DESIGN_PRINCIPLE.md](../../design-princples/KEIYAKU_DESIGN_PRINCIPLE.md).

**Recommendation:** Enable by default with a CLI flag to disable
(`--no-semantic-verify`) for cost-sensitive runs.

---

### A3: Enable Simple-to-Trivial Decomposer

**Effort:** Config toggle | **Impact:** HIGH

**Problem:** `FunctionBodyDecomposer` in `clause_mapper.py` decomposes
SIMPLE function bodies into template-renderable clauses — generating code
with **zero LLM calls**. Gated behind `enable_simple_decomposer: false`
in `MicroPrimeConfig` (`models.py:204`).

**How it works** (`engine.py:1535-1575`):
1. Before calling Ollama for a SIMPLE element, tries `decomposer.try_decompose()`
2. If confidence exceeds threshold (default 0.6): code assembled from templates
   (0 LLM calls, deterministic)
3. If decomposition fails: falls through to Ollama as normal

**Configuration:**
```json
{
    "enable_simple_decomposer": true,
    "simple_decomposer_confidence_threshold": 0.7
}
```

**Important:** The decomposer does NOT fall back to Ollama on bad output.
`try_decompose()` returns `None` (rejected) or code (accepted). If it
returns code, that code is used directly. The confidence threshold is the
primary quality gate — start at 0.7 to be conservative.

---

## Category D: Unwired Capabilities

### D1: Plumb Classification Signals to FunctionChainStrategy

**Effort:** ~15 lines | **Impact:** HIGH
**Status:** PARTIALLY RESOLVED — `ClassificationResult` now carries `TaskComplexitySignals`; `complexity_signals` parameter added to decomposer. Strategy consumption of structured signals pending.

**Problem:** `FunctionChainStrategy` (REQ-MP-902) in `decomposer.py:635-677`
is fully implemented but `can_handle()` falls back to reason-string substring
matching because `classification_signals` is never passed. The TODO at
`engine.py:1064-1066` explicitly documents this gap:

```
Note: Phase 3 (FunctionChainStrategy) will need to add
classification_signals plumbing from the classifier through
_process_element_with_tier into this method.
```

**Keiyaku update (D-1):** `classify_tier()` now returns `ClassificationResult` (dataclass in `complexity/classifier.py`) instead of a bare `(tier, reason_string)` tuple. The `ClassificationResult.signals` field carries the full `TaskComplexitySignals`. The remaining work is wiring `ClassificationResult.signals` through to `FunctionChainStrategy.can_handle()` so it uses structured signals instead of reason-string parsing.

**Fix:** Carry the signals through classification → routing → decomposition:

1. Add a helper that extracts trigger signal names from `TaskComplexitySignals`:

```python
# classifier.py
def _extract_trigger_signals(
    signals: TaskComplexitySignals,
    config: ComplexityRoutingConfig,
) -> set[str]:
    """Extract signal names that contributed to MODERATE+ classification."""
    triggers: set[str] = set()
    if signals.blast_radius >= config.blast_radius_complex_threshold:
        triggers.add("blast_radius")
    if signals.has_dynamic_dispatch:
        triggers.add("dynamic_dispatch")
    if signals.unresolved_call_count >= config.unresolved_calls_complex_threshold:
        triggers.add("unresolved_calls")
    if signals.mro_depth >= config.mro_depth_complex_threshold:
        triggers.add("mro_depth")
    if signals.caller_count >= config.caller_count_complex_threshold:
        triggers.add("caller_count")
    if signals.has_cross_file_edges:
        triggers.add("cross_file_edges")
    return triggers
```

2. In `_process_element_with_tier()`, store signals alongside tier and reasoning

3. In `_handle_moderate()`, pass signals to `decompose()`:

```python
# engine.py — _handle_moderate() line 1131
# Current:
plan = self._decomposer.decompose(element, file_spec, manifest, reasoning)
# Fixed:
plan = self._decomposer.decompose(
    element, file_spec, manifest, reasoning,
    classification_signals=self._current_signals,
)
```

`ModerateDecomposer.decompose()` already accepts and forwards
`classification_signals` — it just never receives a non-None value.

**What this unlocks:** MODERATE functions with 2+ responsibility clauses in
their docstring can be decomposed into SIMPLE helpers + a dispatch body.
Each helper is generated independently via Ollama. Cheaper than cloud
escalation and produces more maintainable code.

**Why it was blocked:** The original design called for a `ClassificationSignal`
enum, but `TaskComplexitySignals` dataclass fields serve the same purpose.
Extract field names that triggered MODERATE classification as a `set[str]`
instead of waiting for a separate enum.

**Tests:** `tests/unit/micro_prime/test_decomposer.py` — extend existing
FunctionChainStrategy tests:
- `test_function_chain_with_api_signal_excluded` — `{"external_api"}` → can_handle=False
- `test_function_chain_without_signals_uses_reason_fallback` — existing behavior preserved
- `test_function_chain_with_non_disqualifying_signals` — `{"blast_radius"}` → can_handle=True

---

### D2: Wire Binding Constraints into Element Prompt

**Effort:** ~10 lines | **Impact:** MEDIUM

**Problem:** `MicroPrimeContext.binding_constraints` is populated from two sources:
- Artisan adapter: `artisan_adapter.py:113` (currently hardcoded to `[]`)
- Prime adapter: `context.py:56` (reads `domain_constraints` from generation context)

But the engine (`engine.py`) never reads `binding_constraints`. The constraints
are loaded into context, carried through the pipeline, and silently discarded.

**Fix:** Include binding constraints in the Ollama prompt for SIMPLE elements:

```python
# In the prompt construction path (engine.py, _handle_simple or prompt builder)
if context_constraints := getattr(self._current_context, "binding_constraints", []):
    prompt_parts.append(
        "\n## Constraints\n"
        + "\n".join(f"- {c}" for c in context_constraints)
    )
```

Also fix the Artisan adapter to forward actual constraints:

```python
# artisan_adapter.py:113 — currently:
"binding_constraints": [],
# Should be:
"binding_constraints": phase_data.get("domain_constraints", []),
```

**What this unlocks:** Domain constraints (e.g., "must use async I/O",
"must not call external APIs directly") flow from plan ingestion through
to element-level code generation. The LLM sees the same constraints that
the review phase will validate against.

**Tests:**
- `test_binding_constraints_in_prompt` — constraints appear in generated prompt
- `test_empty_constraints_no_section` — no constraints → no section added
- `test_artisan_adapter_forwards_constraints` — constraints from phase_data flow through

---

### D3: Wire Agent Spec Routing in PrimeContractor

**Effort:** ~5 lines | **Impact:** MEDIUM

**Problem:** `ComplexityRouter.select_agent_spec()` (`router.py:54-59`) exists
and works, but is never called. `PrimeContractor.develop_feature()` calls
`self._complexity_router.select(tier)` to pick the *generator* but ignores the
*agent spec*. All tiers use the same cloud model when escalating.

**Fix:**

```python
# prime_contractor.py — develop_feature()
tier, reason = classify_tier(signals, self._complexity_config)
generator = self._complexity_router.select(tier) or generator
agent_spec = self._complexity_router.select_agent_spec(tier)
if agent_spec:
    gen_context["agent_spec"] = agent_spec
```

**What this unlocks:** Different tiers use different cloud models.
SIMPLE escalations could use Haiku (cheaper). COMPLEX tasks could use Opus
(more capable). Configured via:

```python
router = ComplexityRouter(
    simple_agent_spec="anthropic:claude-haiku-4-5-20251001",
    moderate_agent_spec="anthropic:claude-sonnet-4-20250514",
    complex_agent_spec="anthropic:claude-opus-4-6",
)
```

**Trade-off:** Fallback (all tiers → MODERATE spec) is safe and unchanged.

**Tests:** `tests/unit/contractors/test_prime_complexity_routing.py` — extend:
- `test_agent_spec_forwarded_to_context` — spec appears in gen_context
- `test_agent_spec_fallback_to_moderate` — no tier-specific spec → MODERATE used

---

### D4: Wire Element Registry Run Metrics

**Effort:** ~5 lines | **Impact:** MEDIUM

**Problem:** `ElementRegistry.write_run_metrics(run_id)` and
`compare_runs(run_a, run_b)` are fully implemented and tested
(`tests/integration/test_element_registry_phase3.py:146-169`) but never
called from production code.

**Fix:** Call `write_run_metrics()` at postmortem generation:

```python
# prime_contractor.py — after all features processed
if self._element_registry is not None:
    try:
        self._element_registry.write_run_metrics(run_id)
    except Exception:
        logger.warning("Failed to write element registry run metrics")
```

**What this unlocks:** Kaizen trend analysis can compare element-level
metrics across runs — hit rates, tier distributions, escalation patterns —
without manual inspection.

---

### D5: Expose Dry-Run Mode via Pipeline CLI

**Effort:** ~10 lines | **Impact:** MEDIUM

**Problem:** `MicroPrimeConfig.dry_run` is fully wired in the engine and
`prime_adapter.py` (`_dry_run_classify()`). It classifies all elements by
tier without generating code, producing a report of:
- Elements per tier (TRIVIAL/SIMPLE/MODERATE/COMPLEX)
- Which would be handled locally vs escalated to cloud
- Estimated token costs

No way to trigger from CLI. Users must manually edit `.startd8/micro_prime.json`.

**Fix:** Add `--dry-run` flag to the pipeline runner scripts, passing through
to `MicroPrimeConfig(dry_run=True)`.

**What this unlocks:** Pre-run cost estimation. Before spending $1.31 on a
17-feature run, see the tier breakdown. Validates complexity classification
without committing to generation.

---

### D6: Skeleton Enrichment for Standalone Element Path

**Effort:** ~5 lines | **Impact:** LOW

**Problem:** `_enrich_file_spec_from_skeleton()` discovers methods in skeleton
files that aren't in the manifest (e.g., gRPC service methods from proto
compilation). Runs in `process_file()` but NOT in `process_element()`.

Elements processed via `process_element()` directly (e.g., Artisan adapter)
miss skeleton-derived method discovery.

**Fix:**
```python
# engine.py — process_element()
if element.kind == ElementKind.CLASS and skeleton:
    file_spec = self._enrich_file_spec_from_skeleton(file_spec, skeleton)
```

---

## Category E: Tuning and Observability

### E1: Circuit Breaker Scope Expansion

**Effort:** ~15 lines | **Impact:** MEDIUM

**Problem:** Circuit breaker is 3 consecutive failures, scoped per-file
(`reset_circuit_breaker()` at `process_file()` entry). Processing file B
resets the breaker even if Ollama is systemically down.

For multi-file features with consistent Ollama failure, the breaker trips
and resets repeatedly — 3 wasted attempts per file.

**Fix:** Add a per-run breaker that persists across files:

```python
def __init__(self, ...):
    self._file_consecutive_failures = 0     # existing per-file
    self._run_consecutive_failures = 0      # new per-run
    self._RUN_BREAKER_THRESHOLD = 5

@property
def _circuit_open(self) -> bool:
    return (
        self._file_consecutive_failures >= self._CIRCUIT_BREAKER_THRESHOLD
        or self._run_consecutive_failures >= self._RUN_BREAKER_THRESHOLD
    )
```

Per-file resets between files (fast recovery). Per-run only resets via
`clear_cache()` or new engine instance.

**Tests:**
- `test_run_breaker_trips_across_files` — 5 failures across 3 files → open
- `test_run_breaker_resets_on_success` — success resets run counter
- `test_file_breaker_still_resets` — existing per-file behavior unchanged

---

### E2: Few-Shot Quality Weighting

**Effort:** ~20 lines | **Impact:** MEDIUM

**Problem:** Few-shot examples use most recent successful completions
(`max_few_shot_examples: 2`). Some required 0 repair steps, others 6.
Heavily-repaired code as a few-shot example teaches bad patterns.

**Fix:** Prefer examples that needed fewer repairs:

```python
def find_few_shot_examples(
    ...,
    prefer_low_repair: bool = True,
) -> list[FewShotExample]:
    """Select few-shot examples, preferring fewer repair steps."""
    candidates = self._recent_successes[-10:]
    if prefer_low_repair:
        candidates.sort(key=lambda x: x.repair_count)
    return candidates[:max_examples]
```

Requires storing `repair_count` in success history (partially tracked
via `RepairResult`).

**Tests:**
- `test_few_shot_prefers_low_repair` — 0-repair chosen over 5-repair
- `test_few_shot_fallback_when_no_low_repair` — all high-repair → still returns

---

### E3: Template Coverage Expansion

**Effort:** ~30 lines per template | **Impact:** MEDIUM

**Problem:** Template registry covers 11 patterns. Common additions for
zero-LLM generation:

| Pattern | Trigger | Example |
|---------|---------|---------|
| Property setter | `@x.setter` in skeleton | `self._x = value` |
| Context manager | `__enter__`/`__exit__` | `return self` / cleanup |
| Iterator | `__iter__`/`__next__` | `yield from self._items` |
| Comparison | `__lt__`/`__le__`/`__gt__`/`__ge__` | `return self.x < other.x` |
| Bool | `__bool__`/`__len__` | `return bool(self._items)` |
| String format | `__format__` | `return format(self.value, spec)` |
| Descriptor | `__get__`/`__set__` | Descriptor protocol |

**Priority:** Property setter and context manager are most common.

**Tests per template:**
- `test_template_X_renders` — produces valid Python
- `test_template_X_matches` — correct trigger detection
- `test_template_X_signature_preserved` — parameter names from manifest used

---

### E4: Assembly Time OTel Histogram

**Effort:** ~5 lines | **Impact:** LOW

**Problem:** TODO at `engine.py:1303`:
```
# TODO(Phase 2, REQ-MP-906): Emit assembly_time_ms as OTel histogram
```

Decomposition assembly timing computed but not exported to OTel.

**Fix:**
```python
_record_histogram("micro_prime.assembly_time_ms", assembly_ms, {
    "strategy": plan.strategy,
    "sub_element_count": len(plan.sub_elements),
})
```

---

## Category F: Element Registry Unlocks

### F1: Wire elements_by_status for Kaizen Analysis

**Effort:** ~5 lines | **Impact:** MEDIUM

**Problem:** `registry.elements_by_status(phase, status)` is tested
(`test_element_registry.py:349-392`) but never called in production.

**Fix:** Call in postmortem generation:

```python
if registry:
    local_count = len(registry.elements_by_status("generation", "completed"))
    escalated_count = len(registry.elements_by_status("generation", "escalated"))
    cloud_backfill = len(registry.elements_by_status("cloud_backfill", "validated"))
    metrics["element_registry"] = {
        "local": local_count,
        "escalated": escalated_count,
        "cloud_backfill": cloud_backfill,
        "total": len(registry.all_entries()),
    }
```

**Also unused but tested:**
- `get_phase_status()` — individual element phase lookup
- `compare_runs()` — cross-run regression detection
- `reconcile()` — backup reconciliation (REQ-MP-1108)
- `element_lineage()` — full element history timeline

---

### F2: Expose Element Lineage via CLI

**Effort:** ~15 lines | **Impact:** LOW

**Problem:** `registry.element_lineage(element_id)` returns complete
generation history (status transitions, timestamps, run IDs). Tested
but only accessible programmatically.

**Fix:** Add CLI subcommand:

```bash
startd8 element-registry lineage <element_id>
```

---

## Execution Priority

```
Immediate (highest ROI, minimal risk):
  A1  Wire DFA pre-fill               — 5 lines, 5 files
  A3  Enable simple decomposer        — config toggle
  D1  Plumb classification signals     — 15 lines, unlocks FunctionChainStrategy
  D2  Wire binding constraints         — 10 lines, constraints already loaded

Short-term (medium effort, high value):
  D3  Agent spec routing               — 5 lines, tier-appropriate models
  D4  Wire registry run metrics        — 5 lines, methods already tested
  D5  Expose dry-run via CLI           — 10 lines, cost estimation
  E1  Circuit breaker scope            — 15 lines, systemic failure handling
  F1  elements_by_status in postmortem  — 5 lines, enriches Kaizen data

Medium-term (config decision + prompt work):
  A2  Enable semantic verification     — config toggle, cost trade-off
  E2  Few-shot quality weighting       — 20 lines, better example selection
  E3  Template coverage expansion      — 30 lines/template, 0 LLM cost

Low priority (polish):
  D6  Skeleton enrichment standalone   — 5 lines, edge case
  E4  Assembly time histogram          — 5 lines, REQ-MP-906 TODO
  F2  CLI element lineage              — 15 lines, debugging convenience
```

---

## File Manifest

| Item | New Files | Modified Files |
|------|-----------|---------------|
| A1 | — | `prime_adapter.py:1256`, `engine.py:2017`, `repair.py:696`, `scaffold.py:189`, `plan_ingestion_workflow.py:4040` |
| A2 | — | `.startd8/micro_prime.json` (config) |
| A3 | — | `.startd8/micro_prime.json` (config) |
| D1 | — | `engine.py` (~15 lines), `classifier.py` (add `_extract_trigger_signals`) |
| D2 | — | `engine.py` (prompt section), `artisan_adapter.py:113` |
| D3 | — | `prime_contractor.py` (~5 lines) |
| D4 | — | `prime_contractor.py` (~5 lines) |
| D5 | — | `prime_contractor.py` or pipeline runner script |
| D6 | — | `engine.py` (~5 lines) |
| E1 | — | `engine.py` (~15 lines) |
| E2 | — | `engine.py` (few-shot selection), `models.py` (repair_count field) |
| E3 | — | `templates.py` (~30 lines per template) |
| E4 | — | `engine.py` (~5 lines) |
| F1 | — | `prime_contractor.py` (postmortem section) |
| F2 | — | `cli.py` (~15 lines) |

---

## Related Documents

- [MICRO_PRIME_REQUIREMENTS.md](./MICRO_PRIME_REQUIREMENTS.md) — Full requirements (Layers 1-11)
- [REQ-MP-9xx_MODERATE_DECOMPOSER.md](./REQ-MP-9xx_MODERATE_DECOMPOSER.md) — Moderate decomposer requirements
- [REQ-MP-11xx_ELEMENT_REGISTRY.md](./REQ-MP-11xx_ELEMENT_REGISTRY.md) — Element registry requirements
- [SIMPLE_TO_TRIVIAL_DECOMPOSER_IMPLEMENTATION_PLAN.md](./SIMPLE_TO_TRIVIAL_DECOMPOSER_IMPLEMENTATION_PLAN.md) — Phase 3 decomposer plan
- [QUALITY_IMPROVEMENT_PLAN.md](../kaizen/QUALITY_IMPROVEMENT_PLAN.md) — Cross-cutting quality improvements (Addendum 2 covers pipeline-level quick wins)
- [ICHIGO_ICHIE_DESIGN_PRINCIPLE.md](../../design-princples/ICHIGO_ICHIE_DESIGN_PRINCIPLE.md) — Design principle governing calibration bias
