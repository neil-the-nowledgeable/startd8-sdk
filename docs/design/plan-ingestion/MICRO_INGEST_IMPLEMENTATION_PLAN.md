# Micro-Ingest — Implementation Plan

> **Version:** 0.1.0
> **Date:** 2026-03-10
> **Requirements:** [MICRO_INGEST_REQUIREMENTS.md](./MICRO_INGEST_REQUIREMENTS.md)
> **Delivery:** 3 phases, each independently shippable and testable

---

## Execution Order Summary

```
Phase 1: Classifier + Route Report         ~200 LOC + ~180 LOC tests
Phase 2: Deterministic Stub Assembly        ~250 LOC + ~220 LOC tests
Phase 3: Ollama Code Example Generation     ~150 LOC + ~160 LOC tests
                                            ─────────────────────────
                                    Total:  ~600 LOC + ~560 LOC tests
```

---

## Critical Design Correction

The requirements doc (§2.1) placed Micro-Ingest **after** Option A enrichment in the pipeline diagram:

```
REFINE → [ENRICH-A] → [MICRO-INGEST] → EMIT
```

Investigation of `_phase_emit()` reveals the actual internal ordering:

```
_phase_emit():
  1. ForwardManifest construction          (line 4107-4150)
  2. DFA skeleton validation               (line 4162-4200)
  3. _derive_tasks_from_features()         (line 4200-4340)
  4. enrich_tasks_deterministic()          (line 4354) ← Option A
  5. [MICRO-INGEST insertion point]        ← NEW
  6. _build_seed_artifacts()               (line 4367)
  7. compute_seed_quality()                (line 4476)
```

**Key finding:** `forward_manifest` (with real `ForwardFileSpec` data) IS available at the insertion point. This means Tier 0 can use real file specs — not just synthetic specs from `api_signatures`. The requirements doc's assumption that ForwardManifest is unavailable during enrichment was wrong.

**Updated Tier 0 priority:**

1. Use `forward_manifest.file_specs[target_file]` when available (real spec, highest fidelity)
2. Fall back to synthetic spec from `api_signatures` when ForwardManifest is absent or has no entry for the target file

---

## Phase 1: Classifier + Route Report

**Goal:** Classify each task's enrichment tier and produce a diagnostic report. No code generation. Ships as a dry-run that validates routing logic before any generation runs.

### Step 1.1: Create `plan_ingestion_micro_ingest.py`

**File:** `src/startd8/workflows/builtin/plan_ingestion_micro_ingest.py`

**Contents:**

```python
"""Micro-Ingest: local-first per-task code example enrichment.

Three-tier pipeline mirroring Micro Prime's routing pattern:
  Tier 0: DFA stub rendering (deterministic, zero LLM)
  Tier 1: Template rendering (deterministic, zero LLM)
  Tier 2: Ollama generation (local LLM, opt-in)
"""

@dataclass
class EnrichmentRoute:
    task_id: str
    needs_code_example: bool
    tier: int                       # 0, 1, 2, or -1 (skip)
    tier_reason: str
    elements: list[str]             # Element names that would be generated
    estimated_tokens: int = 0       # Estimated output token count (R1-S1)
    has_forward_spec: bool = False
    has_api_signatures: bool = False
    template_matches: list[str] = field(default_factory=list)

@dataclass
class EnrichmentRouteReport:
    total_tasks: int
    already_enriched: int
    tier_0_count: int
    tier_1_count: int
    tier_2_count: int
    skip_count: int
    routes: list[EnrichmentRoute]
    estimated_ollama_time_s: float = 0.0  # tier_2_count * avg_inference_time (R1-S2)


def classify_enrichment_routes(
    tasks: list[dict],
    features: list,                         # list[ParsedFeature]
    forward_manifest: Optional[ForwardManifest] = None,
) -> EnrichmentRouteReport:
    """Classify each task into an enrichment tier."""
    ...


def _parse_api_signature(sig: str) -> Optional[ForwardElementSpec]:
    """Parse a single api_signature string into a ForwardElementSpec."""
    ...


def _build_synthetic_file_spec(
    target_file: str,
    elements: list[ForwardElementSpec],
    runtime_dependencies: list[str],
    protocol: str,
) -> ForwardFileSpec:
    """Build a synthetic ForwardFileSpec from parsed signatures."""
    ...
```

**Classification logic** (in `classify_enrichment_routes`):

```python
for task in tasks:
    # 1. Already has code example?
    desc = task.get("config", {}).get("task_description", "")
    if "```" in desc:
        route = EnrichmentRoute(tier=-1, tier_reason="already has code block", ...)
        continue

    ctx = task.get("config", {}).get("context", {})
    target_files = ctx.get("target_files", [])
    feature_id = ctx.get("feature_id", "")
    feat = feature_index.get(feature_id)

    # 2. Has ForwardFileSpec?
    target = _select_target_file(target_files, forward_manifest)  # first manifest match, or ""
    fwd_spec = (forward_manifest.file_specs.get(target)
                if forward_manifest and target else None)
    if fwd_spec and fwd_spec.elements:
        route = EnrichmentRoute(tier=0, tier_reason="ForwardFileSpec available", ...)
        continue

    # 3. Has parseable api_signatures?
    api_sigs = (feat.api_signatures if feat else []) or ctx.get("api_signatures", [])
    parsed_elements = [e for s in api_sigs if (e := _parse_api_signature(s))]
    if parsed_elements:
        # 3a. Attempt synthetic ForwardFileSpec → Tier 0 (R1-S3: REQ-MI-100 rule 3)
        if len(parsed_elements) == len(api_sigs):  # all parse cleanly
            synthetic_spec = _build_synthetic_file_spec(target, parsed_elements, ...)
            if synthetic_spec:
                route = EnrichmentRoute(tier=0, tier_reason="synthetic ForwardFileSpec (all sigs parsed)", ...)
                continue

        # 3b. Check if any match templates → Tier 1
        template_matches = _check_template_matches(parsed_elements)
        if template_matches:
            route = EnrichmentRoute(tier=1, tier_reason="template matches available", ...)
            continue

        # 3c. Check SIMPLE viability → Tier 2
        simple_elements = _filter_simple_viable(parsed_elements)
        if simple_elements:
            route = EnrichmentRoute(tier=2, tier_reason="SIMPLE-viable elements", ...)
        else:
            route = EnrichmentRoute(tier=-1, tier_reason="no viable elements", ...)
        continue

    # 4. No structural data → skip
    route = EnrichmentRoute(tier=-1, tier_reason="no structural data", ...)
```

### Step 1.2: Signature Parsing

**Function:** `_parse_api_signature(sig: str) -> Optional[ForwardElementSpec]`

**Implementation approach:** Normalize the signature string, then use `ast.parse()` to extract fields:

```python
def _parse_api_signature(sig: str) -> Optional[ForwardElementSpec]:
    """Parse 'def foo(x: int) -> str' or 'Class Foo(Base)' into ForwardElementSpec."""
    sig = _normalize_signature(sig)  # strip quotes/backticks, rewrite Class/parented methods, ensure ': pass'

    # Class pattern (normalized): "class ClassName(Base1, Base2): pass"
    if sig.startswith("class "):
        # Parse via regex: Class\s+(\w+)(?:\((.+)\))?
        ...
        return ForwardElementSpec(kind=ElementKind.CLASS, name=name, bases=bases)

    # Function/method: try ast.parse
    # Handle "def ClassName.method(...)" → split parent_class
    try:
        # Add "pass" body so ast.parse works
        source = f"{sig}:\n    pass"
        tree = ast.parse(source)
        func_def = tree.body[0]  # ast.FunctionDef or ast.AsyncFunctionDef
        # Extract name, args, return annotation, async flag
        ...
        return ForwardElementSpec(kind=kind, name=name, signature=sig_obj, parent_class=parent)
    except SyntaxError:
        return None
```

**Normalization rules (per requirements):**

- Rewrite `Class Foo(Base)` → `class Foo(Base): pass`
- Rewrite `def Foo.bar(self, x) -> y` → `def bar(self, x) -> y: pass` and set `parent_class="Foo"`
- Ensure bare `def ...` signatures end with `: pass`
- Strip surrounding backticks or quotes if present

**Edge cases:**

- `"def Cls.method(self, x)"` → split on first `.` → `parent_class="Cls"`, `name="method"`
- `"async def fetch(url: str) -> bytes"` → `ASYNC_FUNCTION`
- `"Class Foo"` (no bases) → `CLASS` with empty `bases`
- Unparseable strings → return `None`, log DEBUG

### Step 1.3: Config Extension

**File:** `src/startd8/workflows/builtin/plan_ingestion_diagnostics.py`

Add fields to `PlanIngestionKaizenConfig`:

```python
# Micro-Ingest
micro_ingest_enabled: bool = True
micro_ingest_tier_0_enabled: bool = True
micro_ingest_tier_1_enabled: bool = True
micro_ingest_tier_2_enabled: bool = False   # Opt-in, ships in Phase 3
micro_ingest_max_lines: int = 80
micro_ingest_ollama_timeout_s: int = 30
micro_ingest_ollama_per_element_s: int = 10
```

No changes to `load_kaizen_config()` needed — the existing `{k: v for k, v in section.items() if k in known}` pattern auto-discovers new dataclass fields.

### Step 1.4: Integration Point

**File:** `src/startd8/workflows/builtin/plan_ingestion_workflow.py`

Insert after `enrich_tasks_deterministic()` call (line ~4365):

```python
        # --- REQ-MI-1xx: Micro-Ingest task enrichment classification
        _mi_report = None
        if tasks and parsed_plan is not None and _kc.micro_ingest_enabled:
            from .plan_ingestion_micro_ingest import classify_enrichment_routes
            _mi_report = classify_enrichment_routes(
                tasks,
                parsed_plan.features,
                forward_manifest=forward_manifest,
            )
            logger.info(
                "micro_ingest.classify: tier_0=%d tier_1=%d tier_2=%d skip=%d",
                _mi_report.tier_0_count,
                _mi_report.tier_1_count,
                _mi_report.tier_2_count,
                _mi_report.skip_count,
            )
```

Phase 1 stops here — classification only, no generation. The report is logged and persisted in diagnostics.

### Step 1.5: Diagnostic Persistence

Add `MicroIngestDiagnostic` dataclass to `plan_ingestion_diagnostics.py`:

```python
@dataclass
class MicroIngestGenerationDiagnostic:
    """Per-tier generation counters matching REQ-MI-500 schema (R1-S4)."""
    tier_0_rendered: int = 0
    tier_0_truncated: int = 0
    tier_1_rendered: int = 0
    tier_2_attempted: int = 0
    tier_2_succeeded: int = 0
    tier_2_failed: int = 0
    tier_2_skipped_signals: int = 0
    tier_2_skipped_timeout: int = 0
    total_time_ms: int = 0
    ollama_time_ms: int = 0

@dataclass
class MicroIngestDiagnostic:
    enabled: bool = False
    total_tasks: int = 0
    already_enriched: int = 0
    tier_0_count: int = 0
    tier_1_count: int = 0
    tier_2_count: int = 0
    skip_count: int = 0
    code_examples_added: int = 0
    time_ms: int = 0
    generation: MicroIngestGenerationDiagnostic = field(
        default_factory=MicroIngestGenerationDiagnostic
    )
```

Wire into the diagnostic report alongside `EnrichmentDiagnostic`.

### Step 1.6: Tests

**File:** `tests/unit/workflows/test_plan_ingestion_micro_ingest.py`

```
TestSignatureParsing (6 tests):
  test_parse_function_signature
  test_parse_async_function
  test_parse_method_with_parent_class
  test_parse_class_with_bases
  test_parse_class_no_bases
  test_parse_invalid_returns_none

TestClassifier (7 tests):
  test_tier_0_forward_spec_available
  test_tier_0_synthetic_from_signatures
  test_tier_1_all_template_matches
  test_tier_2_simple_viable_element
  test_skip_already_has_code_block
  test_skip_no_structural_data
  test_route_report_counts

TestConfig (2 tests):
  test_micro_ingest_config_defaults
  test_micro_ingest_config_from_json
```

**Total:** ~15 tests, ~180 LOC

### Phase 1 Delivery Checklist

- [ ] `plan_ingestion_micro_ingest.py` with `classify_enrichment_routes()`, `_parse_api_signature()`, `_build_synthetic_file_spec()`
- [ ] `MicroIngestDiagnostic` dataclass in `plan_ingestion_diagnostics.py`
- [ ] 7 config fields on `PlanIngestionKaizenConfig`
- [ ] Integration in `_phase_emit()` after `enrich_tasks_deterministic()`
- [ ] Diagnostic persistence (logged + JSON)
- [ ] ~15 unit tests
- [ ] All existing plan ingestion tests still pass

---

## Phase 2: Deterministic Stub Assembly

**Goal:** For Tier 0 and Tier 1 tasks, render code examples and append to task descriptions. Zero LLM calls.

**Depends on:** Phase 1 (classifier provides routes)

### Step 2.1: DFA Rendering Function

**File:** `plan_ingestion_micro_ingest.py` (extend)

```python
def _render_code_example_tier_0(
    file_spec: ForwardFileSpec,
    max_lines: int = 80,
    template_snippets: Optional[list[str]] = None,
) -> Optional[str]:
    """Render a ForwardFileSpec as a fenced code block for task enrichment.

    Returns a markdown-formatted code block, or None if rendering fails.
    """
    assembler = DeterministicFileAssembler()
    try:
        source = assembler.render_file(file_spec)
    except Exception:
        return None

    # Validate
    try:
        ast.parse(source)
    except SyntaxError:
        return None

    # Strip DFA sentinel header (not useful in description context)
    lines = source.splitlines()
    if lines and lines[0].startswith("# [STARTD8-SKELETON]"):
        lines = lines[1:]

    # Truncate
    truncated = False
    snippet_budget = 0
    snippets = ""
    if template_snippets:
        snippet_budget = min(20, max(8, max_lines // 4))
    if len(lines) > max_lines:
        if snippet_budget:
            dfa_budget = max_lines - snippet_budget
            lines = lines[:dfa_budget]
            snippets = _render_template_snippets(template_snippets, snippet_budget)
            truncated = True
        else:
            lines = lines[:max_lines]
            truncated = True

    body = "\n".join(lines).strip()
    if snippets:
        body = f"{body}\n\n## Template Snippets\n{snippets}"
    if truncated:
        body += "\n# ... (truncated after 80 lines; see forward manifest for full spec)"

    return f"## Code Example (from forward manifest)\n```python\n{body}\n```"
```

**Key reuse:** `DeterministicFileAssembler.render_file()` does all the heavy lifting — imports, class hierarchy, signatures, stub bodies. We just wrap the output in a fenced block.
**Hybrid behavior:** When `template_snippets` are provided and the DFA output exceeds `max_lines`, the renderer reserves a snippet budget, truncates the DFA skeleton, and appends a compact "Template Snippets" section (within the same line cap).

### Step 2.2: Template Rendering Function

```python
def _render_code_example_tier_1(
    elements: list[ForwardElementSpec],
    template_matches: dict[str, TemplateMatch],
) -> Optional[str]:
    """Render template-matched elements as a fenced code block."""
    parts = []
    for elem in elements:
        match = template_matches.get(elem.name)
        if not match:
            continue
        # Wrap body-only template output in the full def signature
        sig_line = _render_signature_line(elem)
        body = textwrap.indent(match.code, "    ")
        parts.append(f"{sig_line}\n{body}")

    if not parts:
        return None

    body = "\n\n".join(parts)
    return f"## Code Example (from template: {', '.join(m.name for m in template_matches.values())})\n```python\n{body}\n```"
```

**Hybrid helper (snippet budget):**

```python
def _render_template_snippets(
    template_snippets: list[str],
    max_lines: int,
) -> str:
    """Return a compact snippet block for hybrid Tier 0 output."""
    lines: list[str] = []
    for i, snippet in enumerate(template_snippets):
        for line in snippet.splitlines():
            if len(lines) >= max_lines:
                break
            lines.append(line)
        if len(lines) >= max_lines:
            break
        # R1-S9: Only add spacer between snippets, not after the last one
        if i < len(template_snippets) - 1:
            lines.append("")
    return "\n".join(lines).rstrip()
```

```python
def _build_template_snippets(
    route: EnrichmentRoute,
    feature_index: dict,
) -> list[str]:
    """Render template-matched elements into short snippets for hybrid Tier 0."""
    ...
```

### Step 2.3: Enrichment Executor

```python
def enrich_tasks_micro_ingest(
    tasks: list[dict],
    routes: list[EnrichmentRoute],
    features: list,
    forward_manifest: Optional[ForwardManifest] = None,
    *,
    tier_0_enabled: bool = True,
    tier_1_enabled: bool = True,
    tier_2_enabled: bool = False,
    max_lines: int = 80,
    ollama_timeout_s: int = 30,           # R1-S7: shown from Phase 2 onwards
    ollama_per_element_s: int = 10,       # (only used when tier_2_enabled=True)
    micro_prime_engine: Optional[Any] = None,  # Optional MicroPrimeEngine
) -> MicroIngestDiagnostic:
    """Run Micro-Ingest enrichment on tasks (in-place).

    Phase 2: Tier 0 + Tier 1 only (deterministic).
    Phase 3: Tier 2 (Ollama) when tier_2_enabled=True.
    """
    diag = MicroIngestDiagnostic(enabled=True, total_tasks=len(tasks))
    task_index = {t.get("task_id", ""): t for t in tasks}
    feature_index = {f.feature_id: f for f in features}

    for route in routes:
        if route.tier == -1:
            if not route.needs_code_example:
                diag.already_enriched += 1
            else:
                diag.skip_count += 1
            continue

        task = task_index.get(route.task_id)
        if not task:
            continue

        code_block = None

        if route.tier == 0 and tier_0_enabled:
            template_snippets = _build_template_snippets(route, feature_index)
            code_block = _try_tier_0(
                task,
                route,
                feature_index,
                forward_manifest,
                max_lines,
                template_snippets=template_snippets,
            )

        elif route.tier == 1 and tier_1_enabled:
            code_block = _try_tier_1(task, route, feature_index)

        elif route.tier == 2 and tier_2_enabled:
            pass  # Phase 3

        if code_block:
            # Append to task description (no-clobber: already checked in classifier)
            desc = task.get("config", {}).get("task_description", "")
            task["config"]["task_description"] = f"{desc}\n\n{code_block}"
            diag.code_examples_added += 1

    return diag
```

### Step 2.4: Integration

Extend the Phase 1 integration point in `_phase_emit()`:

```python
        _mi_report = None
        _mi_diag = None
        if tasks and parsed_plan is not None and _kc.micro_ingest_enabled:
            from .plan_ingestion_micro_ingest import (
                classify_enrichment_routes,
                enrich_tasks_micro_ingest,
            )
            _mi_report = classify_enrichment_routes(
                tasks, parsed_plan.features, forward_manifest=forward_manifest,
            )
            _mi_diag = enrich_tasks_micro_ingest(
                tasks,
                _mi_report.routes,
                parsed_plan.features,
                forward_manifest=forward_manifest,
                tier_0_enabled=_kc.micro_ingest_tier_0_enabled,
                tier_1_enabled=_kc.micro_ingest_tier_1_enabled,
                tier_2_enabled=_kc.micro_ingest_tier_2_enabled,
                max_lines=_kc.micro_ingest_max_lines,
            )
```

### Step 2.5: Tests

```
TestTier0Rendering (6 tests):
  test_dfa_rendering_from_forward_spec
  test_dfa_rendering_from_synthetic_spec
  test_dfa_rendering_truncation_at_80_lines
  test_dfa_hybrid_truncation_includes_template_snippets
  test_dfa_rendering_strips_sentinel_header
  test_dfa_rendering_syntax_error_returns_none

TestTier1Rendering (3 tests):
  test_template_rendering_dunder_init
  test_template_rendering_property_getter
  test_template_rendering_wraps_in_signature

TestEnrichExecutor (6 tests):
  test_tier_0_appends_code_block
  test_tier_1_appends_code_block
  test_skip_already_enriched
  test_no_clobber_existing_code
  test_all_tiers_disabled_no_changes
  test_diagnostic_counts_correct

TestSyntheticFileSpec (4 tests):
  test_build_from_function_signatures
  test_build_with_grpc_protocol_imports
  test_build_with_runtime_dependencies
  test_build_groups_methods_under_class
```

**Total:** ~19 tests, ~230 LOC

### Phase 2 Delivery Checklist

- [ ] `_render_code_example_tier_0()` using `DeterministicFileAssembler.render_file()`
- [ ] `_render_code_example_tier_1()` using `TemplateRegistry` output
- [ ] `enrich_tasks_micro_ingest()` executor
- [ ] `_build_synthetic_file_spec()` for tasks without ForwardManifest
- [ ] Integration in `_phase_emit()` (extend Phase 1 insertion)
- [ ] ~18 unit tests
- [ ] Run `test_plan_ingestion_enrichment.py` (47 tests) — no regressions
- [ ] Run `test_plan_ingestion_diagnostics.py` (48 tests) — no regressions

---

## Phase 3: Ollama Code Example Generation

**Goal:** For Tier 2 tasks, generate code examples via the SIMPLE pipeline. Opt-in only (`tier_2_enabled=False` by default).

**Depends on:** Phase 2 (executor framework, synthetic specs)

### Step 3.1: Ollama Generation Function

**File:** `plan_ingestion_micro_ingest.py` (extend)

```python
def _try_tier_2(
    task: dict,
    route: EnrichmentRoute,
    feature_index: dict,
    forward_manifest: Optional[ForwardManifest],
    max_lines: int,
    timeout_s: int = 10,
    micro_prime_engine: Optional[Any] = None,
) -> Optional[str]:
    """Generate a code example via Ollama SIMPLE pipeline.

    Returns a fenced code block, or None on failure.
    """
    # Build context: synthetic file spec + DFA skeleton
    file_spec = _get_or_build_file_spec(task, route, feature_index, forward_manifest)
    if not file_spec or not file_spec.elements:
        return None

    # Render DFA skeleton for context
    assembler = DeterministicFileAssembler()
    try:
        skeleton = assembler.render_file(file_spec)
    except Exception:
        skeleton = ""

    # Pick first non-trivial element for Ollama generation
    target_element = _pick_generation_target(file_spec.elements, route)
    if not target_element:
        return None

    # Check skip signals
    classification_signals = _extract_classification_signals(task, feature_index)
    skip_signals = {"external_api", "orchestrator", "app_server_instance"}
    if classification_signals and (classification_signals & skip_signals):
        logger.debug("micro_ingest.tier_2: skip signals %s", classification_signals & skip_signals)
        return None

    if not micro_prime_engine:
        return None

    result = micro_prime_engine._handle_simple(
        element=target_element,
        file_spec=file_spec,
        skeleton=skeleton,
        contracts=[],
        file_path=file_spec.file,
        reasoning="micro_ingest_tier_2",
        task_description=task.get("config", {}).get("task_description", ""),
    )

    if not result.success or not result.code:
        return None

    # Format as code block
    code = result.code.strip()
    lines = code.splitlines()
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        code = "\n".join(lines) + "\n# ... (truncated)"

    return f"## Code Example (generated by Ollama)\n```python\n{code}\n```"
```

### Step 3.2: Time Budget Enforcement

Wrap Tier 2 generation in a time budget:

```python
# In enrich_tasks_micro_ingest(), add time tracking for Tier 2:
import time

t2_start = time.monotonic()
t2_budget = ollama_timeout_s  # default 30s

# R1-S6: Check circuit breaker before entering Tier 2 loop
if (micro_prime_engine and hasattr(micro_prime_engine, 'circuit_breaker')
        and micro_prime_engine.circuit_breaker.is_open):
    tier_2_total = sum(1 for r in routes if r.tier == 2)
    diag.generation.tier_2_skipped_signals += tier_2_total
    logger.warning("micro_ingest.tier_2: circuit breaker open — skipping all %d elements", tier_2_total)
else:
    for i, route in enumerate(routes):
        if route.tier == 2 and tier_2_enabled:
            elapsed = time.monotonic() - t2_start
            if elapsed > t2_budget:
                # R1-S5: compute remaining count from current position
                tier_2_remaining = sum(1 for r in routes[i:] if r.tier == 2)
                diag.generation.tier_2_skipped_timeout += tier_2_remaining
                logger.warning("micro_ingest.tier_2: time budget exhausted (%.1fs > %ds)", elapsed, t2_budget)
                break
            code_block = _try_tier_2(
                task,
                route,
                feature_index,
                forward_manifest,
                max_lines,
                per_element_s,
                micro_prime_engine=micro_prime_engine,
            )
```

### Step 3.3: Engine Reuse Decision

**Recommendation: Option B (accept optional engine instance).**

Rationale:

- `MicroPrimeEngine.__init__()` loads the model, sets up circuit breakers, registers OTel metrics
- Instantiating per-task is wasteful; instantiating once and passing in is cleaner
- If no engine provided, skip Tier 2 entirely (degrade gracefully to Tier 0+1)

```python
def enrich_tasks_micro_ingest(
    tasks: list[dict],
    routes: list[EnrichmentRoute],
    features: list,
    forward_manifest: Optional[ForwardManifest] = None,
    *,
    tier_0_enabled: bool = True,
    tier_1_enabled: bool = True,
    tier_2_enabled: bool = False,
    max_lines: int = 80,
    ollama_timeout_s: int = 30,
    ollama_per_element_s: int = 10,
    micro_prime_engine: Optional[Any] = None,  # Optional MicroPrimeEngine
) -> MicroIngestDiagnostic:
```

In the workflow integration, engine instantiation happens only when Tier 2 is enabled:

```python
_engine = None
if _kc.micro_ingest_tier_2_enabled:
    try:
        from startd8.micro_prime.engine import MicroPrimeEngine
        from startd8.micro_prime.models import MicroPrimeConfig
        _engine = MicroPrimeEngine(MicroPrimeConfig(
            local_max_attempts=1,
            repair_enabled=True,
            semantic_verification_enabled=False,
            max_tokens=512,
            temperature=0.1,  # REQ-MI-302: deterministic output
        ))
    except Exception as exc:
        logger.warning("micro_ingest: Ollama engine init failed: %s — tier_2 disabled", exc)
```

### Step 3.4: Kaizen Prompt Capture

When kaizen prompt capture is active and Tier 2 runs:

```python
# R1-S10: prompt_text is reconstructed from the element spec + skeleton context,
# since _handle_simple() does not expose the rendered prompt on its result object.
# Build it the same way MicroPrimeEngine._build_simple_prompt() does internally.
prompt_text = _reconstruct_enrichment_prompt(target_element, file_spec, skeleton)

if self._kaizen_output_dir and result.success:
    persist_prompt_response(
        self._kaizen_output_dir,
        f"micro_ingest_{task_id}",
        prompt_text,
        result.code or "",
    )
```

### Step 3.5: Tests

```
TestTier2Generation (5 tests):
  test_ollama_success_appends_code_block      (mock engine, success)
  test_ollama_failure_returns_none             (mock engine, failure)
  test_skip_signals_respected                  (external_api → skip)
  test_time_budget_enforced                    (mock slow generation)
  test_tier_2_disabled_by_default              (no engine calls)

TestEngineReuse (2 tests):
  test_no_engine_skips_tier_2
  test_engine_passed_through

TestPromptCapture (1 test):
  test_kaizen_prompt_captured_on_success
```

**Total:** ~8 tests, ~160 LOC

### Phase 3 Delivery Checklist

- [ ] `_try_tier_2()` with Ollama generation via `_handle_simple()`
- [ ] Time budget enforcement in executor loop
- [ ] Engine reuse via optional parameter
- [ ] Kaizen prompt capture
- [ ] ~8 unit tests (all with mocked Ollama — no real LLM calls in tests)
- [ ] Manual validation: enable `tier_2_enabled=True` on a real plan, verify code blocks appear
- [ ] Run full test suite — no regressions

---

## Files Created / Modified

| File | Phase | Action | Purpose |
|------|-------|--------|---------|
| `src/startd8/workflows/builtin/plan_ingestion_micro_ingest.py` | 1 | **CREATE** | Classifier, signature parser, enrichment executor |
| `src/startd8/workflows/builtin/plan_ingestion_diagnostics.py` | 1 | MODIFY | Add `MicroIngestDiagnostic`, extend `PlanIngestionKaizenConfig` |
| `src/startd8/workflows/builtin/plan_ingestion_workflow.py` | 1 | MODIFY | Insert Micro-Ingest call after `enrich_tasks_deterministic()` |
| `tests/unit/workflows/test_plan_ingestion_micro_ingest.py` | 1 | **CREATE** | Unit tests (~41 tests total across all phases) |

**Note:** Only 1 new source file + 1 new test file. All logic lives in `plan_ingestion_micro_ingest.py`. Workflow integration is a ~20-line insertion.

---

## Dependency Map

```
Phase 1 (no dependencies)
  └── plan_ingestion_micro_ingest.py: classify_enrichment_routes()
  └── plan_ingestion_diagnostics.py: MicroIngestDiagnostic, config fields
  └── plan_ingestion_workflow.py: 10-line insertion

Phase 2 (depends on Phase 1)
  └── plan_ingestion_micro_ingest.py: enrich_tasks_micro_ingest(), _render_*()
  └── REUSES: DeterministicFileAssembler.render_file()
  └── REUSES: TemplateRegistry.try_template_match_with_name()
  └── plan_ingestion_workflow.py: extend insertion to call executor

Phase 3 (depends on Phase 2)
  └── plan_ingestion_micro_ingest.py: _try_tier_2()
  └── REUSES: MicroPrimeEngine._handle_simple()
  └── plan_ingestion_workflow.py: add engine instantiation guard
```

---

## Risk Register

| Risk | Impact | Mitigation |
|------|--------|-----------|
| `_parse_api_signature()` fails on unusual formats | Tier 0 degrades to skip | Fail-safe: return None, log DEBUG. Real data from 19 Kaizen runs shows signatures are well-formed. |
| DFA `render_file()` produces invalid Python from synthetic specs | Code block with syntax error in description | AST-validate before appending; skip on SyntaxError. |
| Ollama engine init fails (Tier 2) | No Tier 2 enrichment | Graceful degradation: log warning, Tier 0+1 still run. Default `tier_2_enabled=False`. |
| Enrichment bloats task descriptions | Downstream DESIGN/IMPLEMENT token budget exceeded | 80-line cap (REQ-MI-204). Descriptions typically 500-1000 chars; 80 lines adds ~2000 chars max. |
| `forward_manifest` is None (FLCM extraction failed) | Tier 0 limited to synthetic specs | Synthetic spec fallback from `api_signatures`. If both absent, skip. |
| `_handle_simple()` internal API changes | Tier 2 breaks | Tier 2 is opt-in and behind config flag. Can be disabled immediately via config. |

---

## Validation Criteria

### Phase 1 Gate

- [ ] `classify_enrichment_routes()` returns correct tier for each test case
- [ ] Signature parsing handles all 4 formats (function, async, method, class)
- [ ] Config fields load from JSON without error
- [ ] Diagnostic report logged at INFO level
- [ ] 48 existing `test_plan_ingestion_diagnostics.py` tests still pass
- [ ] 47 existing `test_plan_ingestion_enrichment.py` tests still pass

### Phase 2 Gate

- [ ] Tier 0 renders real ForwardFileSpec as code block in task description
- [ ] Tier 0 renders synthetic spec from api_signatures as code block
- [ ] Tier 1 renders template-matched elements with signature wrapper
- [ ] Tier 0 hybrid truncation correctly reserves snippet budget and template snippets appear in output (R1-S8)
- [ ] 80-line truncation works correctly
- [ ] No-clobber: tasks with existing code blocks unchanged
- [ ] Seed quality score increases (richness component) with micro-ingest enabled

### Phase 3 Gate

- [ ] Tier 2 generates code via mocked `_handle_simple()` in tests
- [ ] Real Ollama generation produces valid Python (manual test on run-019 plan)
- [ ] Time budget prevents runaway inference
- [ ] Skip signals prevent wasted Ollama calls
- [ ] Kaizen prompt capture works when enabled

---

## Estimated Impact (Run-019 Projection)

Based on run-019's 6 features:

| Feature | api_signatures? | ForwardFileSpec? | Expected Tier | Code Example? |
|---------|:-:|:-:|:-:|:-:|
| PI-001 Shared Logger (email) | Yes (2 sigs) | Yes | **Tier 0** | Yes — DFA skeleton |
| PI-002 Shared Logger (rec) | Yes (2 sigs) | Yes | **Tier 0** | Yes — DFA skeleton |
| PI-003 gRPC Server (email) | Yes (5 sigs) | Yes | **Tier 0** | Yes — DFA skeleton |
| PI-004 gRPC Test Client | Yes (1 sig) | Yes | **Tier 0** | Yes — DFA skeleton |
| PI-005 HTML Template | No | No | **Skip** | No (non-Python) |
| PI-006 gRPC Server (rec) | Yes (3 sigs) | Yes | **Tier 0** | Yes — DFA skeleton |

**Projected:** 5/6 tasks get code examples (vs 0-1/6 today). All via Tier 0 — zero LLM cost, zero latency.

The `draft_word_count` correlation (ρ=+0.280) predicts this will improve downstream generation quality by anchoring the LLM to concrete type-correct signatures rather than letting it hallucinate from prose descriptions.

---

## Appendix: Iterative Review Log (Applied / Rejected Suggestions)

This appendix is intentionally **append-only**. New reviewers (human or model) should add suggestions to Appendix C, and then once validated, record the final disposition in Appendix A (applied) or Appendix B (rejected with rationale).

### Reviewer Instructions (for humans + models)

- **Before suggesting changes**: Scan Appendix A and Appendix B first. Do **not** re-suggest items already applied or explicitly rejected.
- **When proposing changes**: Append them to Appendix C using a unique suggestion ID (`R{round}-S{n}`).
- **When endorsing prior suggestions**: If you agree with an untriaged suggestion from a prior round, list it in an **Endorsements** section after your suggestion table. This builds consensus signal — suggestions endorsed by multiple reviewers should be prioritized during triage.
- **When validating**: For each suggestion, append a row to Appendix A (if applied) or Appendix B (if rejected) referencing the suggestion ID. Endorsement counts inform priority but do not auto-apply suggestions.
- **If rejecting**: Record **why** (specific rationale) so future models don't re-propose the same idea.

### Areas Substantially Addressed

- **Risks**: 3 suggestions applied (R1-S3, R1-S5, R1-S6)
- **Interfaces**: 3 suggestions applied (R1-S1, R1-S2, R1-S7)
- **Architecture**: 3 suggestions applied (R1-S4, R1-S8, R1-S9)

### Areas Needing Further Review

- **Data**: 0/3 suggestions accepted (need 3 more)
- **Validation**: 0/3 suggestions accepted (need 3 more)
- **Ops**: 0/3 suggestions accepted (need 3 more)
- **Security**: 0/3 suggestions accepted (need 3 more)

### Appendix A: Applied Suggestions

| ID | Suggestion | Source | Implementation / Validation Notes | Date |
|----|------------|--------|----------------------------------|------|
| R1-S1 | `EnrichmentRoute` is missing the `estimated_tokens` field declared in REQ-MI-100 | Gemini 2.5 Pro (antigravity) | Step 1.1 dataclass omits this field. Accepted — add `estimated_tokens: int = 0` to `EnrichmentRoute` | 2026-03-10 |
| R1-S2 | `EnrichmentRouteReport` is missing the `estimated_ollama_time_s` field declared in REQ-MI-102 | Gemini 2.5 Pro (antigravity) | Step 1.1 dataclass omits this field. Accepted — add `estimated_ollama_time_s: float = 0.0` to `EnrichmentRouteReport` | 2026-03-10 |
| R1-S3 | Classification logic skips the synthetic Tier 0 path for parsed api_signatures — parsed elements go directly to template/SIMPLE check without building a synthetic ForwardFileSpec first | Gemini 2.5 Pro (antigravity) | Step 1.1 code: after `parsed_elements` are extracted, the code tests template matches immediately (→Tier 1). REQ-MI-100 rule 3 requires attempting synthetic DFA first (→Tier 0). Accepted — insert synthetic spec attempt before template match check | 2026-03-10 |
| R1-S4 | `MicroIngestDiagnostic` generation-level fields missing vs REQ-MI-500 schema | Gemini 2.5 Pro (antigravity) | Step 1.5 dataclass has tier counts but is missing `tier_0_rendered`, `tier_0_truncated`, `tier_1_rendered`, `tier_2_attempted`, `tier_2_succeeded`, `tier_2_failed`, `tier_2_skipped_signals`, `tier_2_skipped_timeout`, `total_time_ms`, `ollama_time_ms`. Accepted — expand `MicroIngestDiagnostic` with a nested `generation` sub-object matching REQ-MI-500 | 2026-03-10 |
| R1-S5 | Time budget loop references undefined variable `tier_2_remaining_count` | Gemini 2.5 Pro (antigravity) | Step 3.2: the `break` path includes `diag.tier_2_skipped_timeout += (tier_2_remaining_count)` but `tier_2_remaining_count` is never defined. Accepted — compute it as `sum(1 for r in remaining_routes if r.tier == 2)` before the break | 2026-03-10 |
| R1-S6 | No circuit breaker check before Tier 2 execution despite REQ-MI-305/R1-S8 requiring it | Gemini 2.5 Pro (antigravity) | Step 3.2 time budget wrapper and `_try_tier_2()` have no guard for `micro_prime_engine.circuit_breaker.is_open`. Accepted — add: if engine is provided and circuit breaker is open, skip all Tier 2 and log WARNING | 2026-03-10 |
| R1-S7 | `enrich_tasks_micro_ingest()` signature lacks `ollama_timeout_s` and `ollama_per_element_s` in the Phase 2 definition (Step 2.3) but adds them only in Phase 3 (Step 3.3) | Gemini 2.5 Pro (antigravity) | Step 2.3 shows the Phase 2 version of the executor signature without timeout params, then Step 3.3 shows the final form. This creates a documentation discontinuity. Accepted — show the final complete signature in Step 2.3 with a note that timeout params are only used when `tier_2_enabled=True` | 2026-03-10 |
| R1-S8 | Phase 2 Gate and Phase 3 Gate validation criteria do not reference the hybrid rendering (REQ-MI-203/204) added by the user | Gemini 2.5 Pro (antigravity) | Validation criteria at §Validation Criteria predate the hybrid fallback addition. Accepted — add: "Tier 0 hybrid truncation correctly reserves snippet budget and template snippets appear in output" to Phase 2 Gate | 2026-03-10 |
| R1-S9 | `_render_template_snippets()` truncation logic drops the trailing spacer from the last snippet, which is harmless but inconsistent | Gemini 2.5 Pro (antigravity) | Step 2.2: the loop appends `lines.append("")` after each snippet before checking the budget, so the last snippet's spacer is never appended if the budget is reached. Low impact but accepted — use `lines = lines.rstrip()` before joining, or strip the trailing empty line | 2026-03-10 |
| R1-S10 | Kaizen prompt capture in Step 3.4 does not show how `prompt_text` is obtained — this variable is undefined in the snippet | Gemini 2.5 Pro (antigravity) | The `persist_prompt_response()` call references `prompt_text` which must come from `micro_prime_engine._handle_simple()` result or from constructing the prompt beforehand. Accepted — add a note clarifying that `prompt_text` is extracted from `result.prompt` (if the engine exposes it) or reconstructed from the element spec | 2026-03-10 |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none yet) | | | | |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1

- **Reviewer**: Gemini 2.5 Pro (antigravity)
- **Date**: 2026-03-10 15:20:00 UTC
- **Scope**: Full architectural review (first encounter) + requirements traceability against MICRO_INGEST_REQUIREMENTS.md

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-S1 | Interfaces | high | `EnrichmentRoute` dataclass is missing the `estimated_tokens: int` field declared in REQ-MI-100 | The requirements define this field as part of the public data contract; omitting it silently breaks callers that inspect route diagnostics for token budgeting. | Step 1.1 `EnrichmentRoute` dataclass | Add field; verify unit test `test_route_report_counts` checks `estimated_tokens` is populated |
| R1-S2 | Interfaces | high | `EnrichmentRouteReport` dataclass is missing `estimated_ollama_time_s: float` declared in REQ-MI-102 | REQ-MI-102 requires this field for diagnostic reporting and REQ-MI-500 expects it in the JSON output. Plan Step 1.1 omits it entirely. | Step 1.1 `EnrichmentRouteReport` dataclass | Verify field present and computed as `tier_2_count * 6.0` in the report |
| R1-S3 | Risks | critical | Classification logic in Step 1.1 skips Tier 0 for parsed `api_signatures` — it jumps directly to template match (Tier 1) without first attempting the synthetic ForwardFileSpec path | REQ-MI-100 rule 3 requires synthetic DFA (Tier 0) before template match (Tier 1). Plan code goes `parsed_elements → template_matches → Tier 1` without the intervening `_build_synthetic_file_spec → Tier 0` step. This means all parsed-signature tasks will be Tier 1 instead of Tier 0. | Step 1.1 classification logic (lines after `parsed_elements`) | Unit test: task with parseable signatures, no ForwardSpec → expects `tier==0` not `tier==1` |
| R1-S4 | Architecture | high | `MicroIngestDiagnostic` is missing the `generation` sub-structure required by REQ-MI-500, including `tier_0_rendered`, `tier_0_truncated`, `tier_2_attempted`, `tier_2_succeeded`, `tier_2_failed`, `tier_2_skipped_signals`, `tier_2_skipped_timeout`, `total_time_ms`, `ollama_time_ms` | The plan's Step 1.5 dataclass has only tier counts and `code_examples_added`. The REQ-MI-500 JSON schema has a `generation` sub-object with 10+ fields. Without them the diagnostic output will be schema-incompatible. | Step 1.5 `MicroIngestDiagnostic`, Step 2.3 executor (where these counters must be populated) | Integration test: run pipeline → diagnostic JSON matches REQ-MI-500 schema |
| R1-S5 | Risks | critical | `tier_2_remaining_count` is used in Step 3.2 but never defined | The time-budget break path does `diag.tier_2_skipped_timeout += (tier_2_remaining_count)`. This variable is not initialized before the loop and will raise `NameError` at runtime. | Step 3.2 time budget code | Unit test with slow mock that exhausts budget → verify no `NameError`, `tier_2_skipped_timeout` correct |
| R1-S6 | Risks | high | No circuit breaker check before Tier 2 loop despite REQ-MI-305 (R1-S8 in requirements) requiring it | Neither `_try_tier_2()` nor `enrich_tasks_micro_ingest()` checks if the engine's circuit breaker is open before starting the Tier 2 loop. Per REQ-MI-305, if the breaker is open all Tier 2 must be skipped immediately. | Step 3.2 time budget wrapper; Step 3.3 engine section | Unit test: engine with open circuit breaker → `tier_2_skipped` equals total tier-2 count, elapsed time < 0.1s |
| R1-S7 | Interfaces | medium | `enrich_tasks_micro_ingest()` shown in Step 2.3 (Phase 2) lacks `ollama_timeout_s` and `ollama_per_element_s` parameters, contradicting the final signature shown in Step 3.3 (Phase 3) | Creates a documentation discontinuity — a developer implementing Phase 2 will write a signature that breaks when Phase 3 adds the timeout params. The final signature should be shown from the start with a note that timeout params are unused until Phase 3. | Step 2.3 function signature | Verify the function signature in git history is additive-only between Phase 2 and 3 (no breaking changes) |
| R1-S8 | Architecture | medium | Phase 2 Gate validation criteria omit the hybrid rendering path added to REQ-MI-203/204 | The gate checks (§Validation Criteria) were written before the hybrid Tier 0+Tier 1 fallback was added to the requirements. The gate should verify the hybrid path — specifically that `_render_code_example_tier_0()` with `template_snippets` reserves the snippet budget and outputs both DFA and template content within the line cap. | §Validation Criteria, Phase 2 Gate | Add gate item: hybrid rendering test (`test_dfa_hybrid_truncation_includes_template_snippets`) passes |
| R1-S9 | Architecture | low | `_render_template_snippets()` appends an empty spacer line after the budget check, which can produce a trailing blank line in output | Step 2.2: `lines.append("")` runs before `if len(lines) >= max_lines: break`, so the last snippet always gets its trailing spacer whether or not it fits. Low severity but produces inconsistent whitespace. | Step 2.2 `_render_template_snippets()` | Unit test: exactly at budget → verify no trailing blank line in output |
| R1-S10 | Interfaces | medium | `prompt_text` is undefined in the Kaizen prompt capture snippet (Step 3.4) | `persist_prompt_response()` requires `prompt_text` but the snippet does not show where it comes from. `MicroPrimeEngine._handle_simple()` may not expose the rendered prompt in its result object. This creates an implicit dependency on engine internals that is not documented. | Step 3.4 Kaizen prompt capture code | Verify `result.prompt` exists on `MicroPrimeResult`; add assertion in `test_kaizen_prompt_captured_on_success` |

#### Requirements Coverage

| Requirement Section | Plan Step(s) | Coverage | Gaps |
| ---- | ---- | ---- | ---- |
| REQ-MI-100: Task Enrichment Classifier | Step 1.1 classification logic | **Full** | Fixed: synthetic Tier 0 path added (R1-S3) |
| REQ-MI-101: Signature Parsing | Step 1.2 | Full | — |
| REQ-MI-102: Enrichment Route Report | Step 1.1 `EnrichmentRouteReport` | **Full** | Fixed: `estimated_ollama_time_s` added (R1-S2) |
| REQ-MI-103: Forward Manifest Availability | Step 1.1 classifier, §Critical Design Correction | Full | — |
| REQ-MI-104: Integration Point | Step 1.4 | Full | — |
| REQ-MI-200: DFA Stub Rendering | Step 2.1 | Full | — |
| REQ-MI-201: Synthetic ForwardFileSpec Construction | Step 2.1, Step 1.1 | **Full** | Fixed: synthetic spec used in Tier 0 classifier path (R1-S3) |
| REQ-MI-202: Template Rendering for Enrichment | Step 2.2 | Full | — |
| REQ-MI-203: Mixed Rendering (Hybrid) | Step 2.1, Step 2.2 | Full | — |
| REQ-MI-204: Rendering Budget | Step 2.1 truncation logic | Full | — |
| REQ-MI-205: No-Clobber Extension | Step 2.3 executor | Full | Synthetic spec caching addressed in requirements |
| REQ-MI-300: Per-Element Ollama Generation | Step 3.1 `_try_tier_2()` | Full | — |
| REQ-MI-301: Skeleton Context | Step 3.1 | Full | — |
| REQ-MI-302: Generation Constraints | Step 3.3 `MicroPrimeConfig` args | **Full** | Fixed: `temperature=0.1` explicitly set in config |
| REQ-MI-303: Skip Signals | Step 3.1 skip signals check | Full | — |
| REQ-MI-304: Time Budget | Step 3.2 | **Full** | Fixed: `tier_2_remaining` computed (R1-S5), circuit breaker checked (R1-S6) |
| REQ-MI-305: Engine Reuse Strategy | Step 3.3 | **Full** | Fixed: circuit breaker check added (R1-S6) |
| REQ-MI-400: Kaizen Config Extension | Step 1.3 | Full | — |
| REQ-MI-401: Config-Driven Activation | Step 1.3, Step 1.4 | **Full** | Config-only, no CLI flag — default on with graceful degradation |
| REQ-MI-402: Per-Tier Disable | Step 2.3 executor (`tier_X_enabled` params) | Full | — |
| REQ-MI-500: Micro-Ingest Diagnostic Block | Step 1.5 `MicroIngestDiagnostic` | **Full** | Fixed: generation sub-object added (R1-S4) |
| REQ-MI-501: Kaizen Prompt Capture | Step 3.4 | **Full** | Fixed: `prompt_text` reconstruction documented (R1-S10) |
| REQ-MI-502: Density Score Impact | §Estimated Impact, Phase 2 Gate | Full | — |
