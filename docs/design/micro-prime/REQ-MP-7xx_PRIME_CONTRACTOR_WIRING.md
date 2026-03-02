# REQ-MP-7xx: Prime Contractor ↔ Micro Prime Wiring

Wire `MicroPrimeCodeGenerator` into `PrimeContractorWorkflow` as a selectable code generation backend, enabling local-first generation for TRIVIAL/SIMPLE elements with automatic fallback to cloud-based `LeadContractorCodeGenerator` for MODERATE/COMPLEX elements.

> **Parent:** [MICRO_PRIME_REQUIREMENTS.md](./MICRO_PRIME_REQUIREMENTS.md)
> **Status:** ACTIVE — core wiring DONE (REQ-MP-700–703, 710, 711), cost tracking and observability outstanding
> **Depends on:** REQ-MP-8xx (Shared Complexity Router) — **DONE** (commit 0538aaa)
> **Modifies:** `prime_contractor.py`, `micro_prime/prime_adapter.py`, `scripts/run_prime_workflow.py`

---

## Current State

| Component | Status | Evidence |
|-----------|--------|----------|
| `MicroPrimeCodeGenerator` | Built, implements `CodeGenerator` protocol | `micro_prime/prime_adapter.py` |
| `MicroPrimeEngine` | Production | `micro_prime/engine.py` |
| `ComplexityRouter` | Built + wired into Prime Contractor | `complexity/router.py`, `prime_contractor.py:1941` |
| `classify_tier()` shared classifier | Production | `complexity/classifier.py` |
| `extract_signals_from_feature()` | Production | `complexity/signals.py` |
| `DeterministicFileAssembler` | Production (Artisan only) | `utils/file_assembler.py` |
| `ForwardManifest` deserialization | Available | `forward_manifest.py` |
| Artisan → Micro Prime wiring | **ACTIVE** | `context_seed_handlers.py:7959` |
| Prime → Micro Prime wiring | **ACTIVE** (REQ-MP-710) | `prime_contractor.py:enable_micro_prime()` |
| CLI `--micro-prime` flag | **DONE** | `run_prime_workflow.py` |

**Architecture constraint:** `PrimeContractorWorkflow` does not select generators internally. The CLI script (`run_prime_workflow.py`) instantiates the generator and injects it. All wiring changes happen at the CLI/config layer, not in the workflow core.

---

## Gap Analysis

Four gaps were identified in the initial design. All four are now resolved (REQ-MP-700–703 DONE).

### Gap 1: Context Key Mismatch (REQ-MP-701)

`PrimeContractorWorkflow.develop_feature()` injects the manifest as:
```python
# prime_contractor.py:1871
seed_data = { "forward_manifest": self.seed_forward_manifest }  # raw dict
```

But `MicroPrimeCodeGenerator.generate()` reads:
```python
# prime_adapter.py:68
manifest = context.get("manifest") or self._manifest  # expects ForwardManifest object
```

**Two mismatches:** wrong key name (`forward_manifest` vs `manifest`), wrong type (raw `dict` vs deserialized `ForwardManifest`).

### Gap 2: No Skeleton Generation (REQ-MP-702)

Micro Prime operates on skeleton files produced by `DeterministicFileAssembler` in Artisan's SCAFFOLD phase. Prime Contractor has no SCAFFOLD phase and never produces skeletons. Without skeletons, the splicer (`splice_body_into_skeleton`) has nothing to splice into.

### Gap 3: No File Writing (REQ-MP-703)

`MicroPrimeCodeGenerator.generate()` returns `Path` objects in `generated_files` but **never writes files to disk**. The `LeadContractorCodeGenerator` writes to `self.output_dir / target_file`; the Micro Prime adapter does not.

### Gap 4: No CLI Entry Point (REQ-MP-700)

`scripts/run_prime_workflow.py` always creates `LeadContractorCodeGenerator`. There is no code path that substitutes or wraps it with `MicroPrimeCodeGenerator`.

---

## Requirements

### REQ-MP-700: CLI Flags for Micro Prime Selection

**Status:** DONE
**Priority:** P1
**Depends on:** REQ-MP-701, REQ-MP-702, REQ-MP-703

Add `--micro-prime` flag and supporting sub-flags to `scripts/run_prime_workflow.py`.

**CLI arguments:**

| Flag | Type | Default | Purpose |
|------|------|---------|---------|
| `--micro-prime` | store_true | `False` | Enable Micro Prime as primary generator with LeadContractor fallback |
| `--micro-prime-model` | str | `startd8-coder` | Ollama model name |
| `--micro-prime-max-tokens` | int | `512` | Max output tokens per element |
| `--micro-prime-no-templates` | store_true | `False` | Disable template registry (force all through Ollama) |
| `--micro-prime-no-repair` | store_true | `False` | Disable repair pipeline |

**Wiring logic (after `LeadContractorCodeGenerator` construction):**

```python
if args.micro_prime:
    from startd8.micro_prime.prime_adapter import MicroPrimeCodeGenerator
    from startd8.micro_prime.models import MicroPrimeConfig

    mp_config = MicroPrimeConfig(
        model=args.micro_prime_model or "startd8-coder",
        max_tokens=args.micro_prime_max_tokens or 512,
        templates_enabled=not args.micro_prime_no_templates,
        repair_enabled=not args.micro_prime_no_repair,
    )
    code_generator = MicroPrimeCodeGenerator(
        config=mp_config,
        fallback=code_generator,  # LeadContractor becomes fallback
        output_dir=output_dir,
    )
```

**Interaction with `--complexity-routing`:**

When both `--micro-prime` and `--complexity-routing` are set, the `ComplexityRouter` should use `MicroPrimeCodeGenerator` for TRIVIAL and SIMPLE tiers:

```python
if args.complexity_routing and args.micro_prime:
    workflow.enable_complexity_routing(
        config=complexity_config,
        tier3_agent=args.tier3_agent,
        trivial_generator=code_generator,   # MicroPrime wrapping LeadContractor
        simple_generator=code_generator,    # same — engine routes internally
    )
```

This is additive — when complexity routing classifies a feature as TRIVIAL or SIMPLE, the Micro Prime adapter handles it locally. MODERATE and COMPLEX features still route to the standard or premium LeadContractor.

**Acceptance criteria:**
- `--micro-prime` is documented in `--help`
- Without the flag, behavior is identical to today (LeadContractor only)
- With the flag, the generator chain is: `MicroPrimeCodeGenerator(fallback=LeadContractorCodeGenerator(...))`
- Sub-flags are silently ignored when `--micro-prime` is not set
- Sub-flag values map 1:1 to `MicroPrimeConfig` fields

---

### REQ-MP-701: Manifest Deserialization and Context Forwarding

**Status:** DONE
**Priority:** P0
**Depends on:** none (uses existing infrastructure)

Fix the manifest handoff between `PrimeContractorWorkflow` and `MicroPrimeCodeGenerator` by (a) deserializing the raw dict to a `ForwardManifest` object and (b) forwarding it under the correct context key.

**Current flow (broken):**

```
seed JSON → load_seed_context() → self.seed_forward_manifest (raw dict)
         → develop_feature() → seed_data["forward_manifest"] (raw dict)
         → context_strategy.resolve_task_context() → gen_context (may or may not include it)
         → MicroPrimeCodeGenerator.generate() → context.get("manifest") → None (key mismatch)
```

**Target flow:**

```
seed JSON → load_seed_context() → self._forward_manifest (ForwardManifest object)
         → develop_feature() → gen_context["manifest"] = self._forward_manifest
         → MicroPrimeCodeGenerator.generate() → context.get("manifest") → ForwardManifest ✓
```

**Changes to `prime_contractor.py`:**

**1. Deserialization in `load_seed_context()`** (after line 1192):

```python
# Deserialize raw dict to ForwardManifest (if available)
self._forward_manifest: Optional[ForwardManifest] = None
if self.seed_forward_manifest:
    try:
        from startd8.forward_manifest import ForwardManifest
        self._forward_manifest = ForwardManifest.model_validate(
            self.seed_forward_manifest
        )
        logger.info(
            "ForwardManifest deserialized: %d file specs, %d contracts",
            len(self._forward_manifest.file_specs),
            len(self._forward_manifest.contracts),
        )
    except Exception as exc:
        logger.warning(
            "Failed to deserialize ForwardManifest, micro-prime will delegate to fallback: %s",
            exc,
        )
```

**2. Context forwarding in `develop_feature()`** (after `gen_context` is built, ~line 1887):

```python
# Forward manifest for Micro Prime consumption (REQ-MP-701)
if self._forward_manifest is not None:
    gen_context["manifest"] = self._forward_manifest
```

**Acceptance criteria:**
- `ForwardManifest` is deserialized once at seed load time, not per-feature
- Deserialization failure logs a warning and continues (graceful degradation — adapter falls back to LeadContractor)
- `gen_context["manifest"]` contains the deserialized `ForwardManifest` object when available
- The raw `self.seed_forward_manifest` dict is preserved for backward compatibility with context strategies
- Existing behavior when no manifest is present: unchanged (adapter delegates to fallback)
- `context.get("manifest")` in `prime_adapter.py:68` resolves successfully

---

### REQ-MP-702: On-the-Fly Skeleton Generation

**Status:** DONE
**Priority:** P0
**Depends on:** REQ-MP-701

When `--micro-prime` is active and skeletons are absent from context, `MicroPrimeCodeGenerator` SHALL auto-generate stub skeletons from the `ForwardManifest` using `DeterministicFileAssembler`.

**Why skeletons are missing:** Prime Contractor has no SCAFFOLD phase. Skeletons are an Artisan artifact. Rather than requiring a prior SCAFFOLD pass, the adapter generates them on demand.

**Skeleton scope:** Prime Contractor processes features one at a time. Each feature targets a subset of files (`feature.target_files`). Skeletons should be generated **per feature** for only the feature's target files, not for the entire manifest.

**Implementation in `MicroPrimeCodeGenerator.generate()`** (replace lines 68-69):

```python
manifest = context.get("manifest") or self._manifest
skeletons = context.get("skeletons") or self._skeletons

# Auto-generate skeletons from manifest when missing (REQ-MP-702)
if manifest is not None and not skeletons:
    skeletons = self._generate_skeletons(manifest, target_files)
```

**New method `_generate_skeletons()`:**

```python
def _generate_skeletons(
    self,
    manifest: ForwardManifest,
    target_files: list[str],
) -> dict[str, str]:
    """Generate stub skeletons from manifest for target files only.

    Uses DeterministicFileAssembler to render ForwardFileSpec elements
    into Python source with raise NotImplementedError stubs.
    """
    from startd8.utils.file_assembler import DeterministicFileAssembler

    assembler = DeterministicFileAssembler()
    skeletons: dict[str, str] = {}
    for file_path in target_files:
        file_spec = manifest.file_specs.get(file_path)
        if file_spec is None:
            logger.debug("No file_spec for %s, skipping skeleton", file_path)
            continue
        try:
            source = assembler.render_file(file_spec)
            skeletons[file_path] = source
            logger.debug("Generated skeleton for %s (%d lines)", file_path, source.count("\n"))
        except Exception as exc:
            logger.warning("Failed to generate skeleton for %s: %s", file_path, exc)
    return skeletons
```

**What a skeleton looks like:**

```python
# [STARTD8-SKELETON]
from __future__ import annotations

from typing import Optional

class MyService:
    """Service for handling requests."""

    def handle_request(self, request: Request) -> Response:
        """Handle an incoming request."""
        raise NotImplementedError

    def validate(self, data: dict) -> bool:
        """Validate input data."""
        raise NotImplementedError

__all__ = ["MyService"]
```

**Acceptance criteria:**
- When manifest is available but skeletons are empty, stubs are auto-generated per target file
- Skeletons contain correct signatures from `ForwardElementSpec`
- Stubs include `raise NotImplementedError` as placeholder body (required by splicer)
- Skeleton generation uses the existing `DeterministicFileAssembler.render_file()` — no reimplementation
- Only target files for the current feature are rendered (not the entire manifest)
- Skeleton generation failure for one file does not block other files
- When both manifest and skeletons are absent, full delegation to fallback (existing behavior)

---

### REQ-MP-703: Output File Writing

**Status:** DONE
**Priority:** P0
**Depends on:** REQ-MP-702

`MicroPrimeCodeGenerator.generate()` SHALL write generated files to disk and return their absolute paths in `GenerationResult.generated_files`.

**Current gap:** `prime_adapter.py:95-96` creates `Path` objects but never writes content. `LeadContractorCodeGenerator` writes to `self.output_dir / target_file`.

**Changes to `MicroPrimeCodeGenerator`:**

**1. Accept `output_dir` in constructor:**

```python
def __init__(
    self,
    config: Optional[MicroPrimeConfig] = None,
    fallback: Optional[CodeGenerator] = None,
    manifest: Optional[ForwardManifest] = None,
    skeletons: Optional[dict[str, str]] = None,
    output_dir: Optional[Path] = None,
) -> None:
    ...
    self._output_dir = output_dir or Path(".")
```

**2. Write files after successful processing** (replace lines 93-96):

```python
if file_result.filled_skeleton:
    output_path = self._output_dir / file_path
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(file_result.filled_skeleton, encoding="utf-8")
    generated_files.append(output_path)
    logger.info(
        "Micro Prime wrote %s (%d lines, %d elements filled)",
        file_path,
        file_result.filled_skeleton.count("\n"),
        sum(1 for er in file_result.element_results if er.success),
    )
```

**3. Avoid double-writing for fallback files:**

Files delegated to `self._fallback.generate()` are written by the fallback generator itself. The adapter must not write them again. The current merge logic (`generated_files.extend(fallback_result.generated_files)`) is correct — it just collects paths from both sources.

**4. Partial success handling:**

When some files are processed locally and others are escalated, the adapter must track which files were written locally vs by the fallback:

```python
return GenerationResult(
    success=True,
    generated_files=generated_files,
    ...
    metadata={
        "micro_prime_files_written": local_files_written,
        "fallback_files_written": fallback_files_written,
    },
)
```

**Acceptance criteria:**
- Files processed by Micro Prime engine are written to `output_dir / file_path`
- Parent directories are created automatically (`mkdir(parents=True, exist_ok=True)`)
- `GenerationResult.generated_files` contains absolute `Path` objects to written files
- Fallback-generated files are NOT re-written by the adapter
- `output_dir` defaults to current directory when not specified
- `output_dir` is passed from `run_prime_workflow.py` (same value as `LeadContractorCodeGenerator.output_dir`)

---

### REQ-MP-704: Cost and Token Tracking

**Status:** DONE
**Priority:** P2
**Depends on:** REQ-MP-703

Ensure cost and token metrics flow correctly through the merged generation path.

**Already implemented in `prime_adapter.py:115-125`:**
- Merges local + fallback tokens in `input_tokens` / `output_tokens`
- Sets `model=f"micro-prime+{fallback_result.model}"`

**Remaining work:**

**1. `cost_usd` population:**

Local Ollama generation is free ($0.00). Only fallback (cloud) costs should be reflected:

```python
return GenerationResult(
    ...
    cost_usd=fallback_result.cost_usd if fallback_result else 0.0,
    ...
)
```

The current code does not set `cost_usd` on the Micro Prime–only path (line 127-134). It should be `cost_usd=0.0`.

**2. Metadata breakdown:**

`GenerationResult.metadata` SHALL include a generation breakdown for observability:

```python
metadata = {
    "micro_prime_elements": local_success_count,
    "micro_prime_template_hits": template_count,
    "micro_prime_ollama_generations": ollama_count,
    "fallback_elements": escalated_count,
    "micro_prime_cost_usd": 0.0,
    "fallback_cost_usd": fallback_result.cost_usd if fallback_result else 0.0,
}
```

**3. PrimeContractorWorkflow accumulation (already correct):**

```python
# prime_contractor.py:1974-1979 — existing code, no changes needed
self.total_cost_usd += result.cost_usd
self.total_input_tokens += result.input_tokens
self.total_output_tokens += result.output_tokens
```

This works because `GenerationResult` from the adapter already sums both paths.

**Acceptance criteria:**
- Local Ollama tokens tracked in `input_tokens` / `output_tokens` (cost = $0.00)
- Fallback (cloud) tokens tracked and summed
- `cost_usd` reflects only cloud costs (Ollama is free)
- `model` string indicates the composition: `"micro-prime+anthropic:claude-sonnet-4-6"`
- `metadata` includes element count breakdown (local vs fallback vs template)
- `PrimeContractorWorkflow.total_cost_usd` is correct at run completion

---

### REQ-MP-705: Observability and Logging

**Status:** DONE
**Priority:** P2
**Depends on:** REQ-MP-700

When `--micro-prime` is active, structured logging and OTel metrics SHALL provide visibility into the local vs cloud generation split.

**Logging requirements:**

| Level | Message | When |
|-------|---------|------|
| INFO | `"Micro Prime enabled: model=%s, templates=%s, repair=%s"` | At startup when `--micro-prime` is set |
| INFO | `"Micro Prime wrote %s (%d lines, %d elements filled)"` | Per file successfully processed locally |
| INFO | `"Micro Prime: %d elements local, %d escalated to fallback"` | Per feature completion |
| DEBUG | `"Classified %s as %s: %s"` | Per element (already exists in `engine.py:103`) |
| DEBUG | `"Generated skeleton for %s (%d lines)"` | Per skeleton generation |
| WARNING | `"MicroPrimeCodeGenerator: no manifest, delegating to fallback"` | Already exists in `prime_adapter.py:73` |

**OTel metrics (behind import guard):**

| Metric | Type | Attributes |
|--------|------|------------|
| `micro_prime.elements_local` | Counter | `tier` (trivial/simple), `file_path` |
| `micro_prime.elements_escalated` | Counter | `reason` (tier_too_high/ast_failure/structural_mismatch) |
| `micro_prime.template_hits` | Counter | `template_name` |

**Acceptance criteria:**
- INFO-level logs provide run-level summary without being noisy
- DEBUG-level logs provide per-element traceability
- OTel metrics are behind `try/except ImportError` guard (no hard dependency)
- Metrics are recorded via `MetricsCollector` (already exists in `micro_prime/metrics.py`)

---

### REQ-MP-706: Entry Point Registration (Deferred)

**Status:** deferred
**Priority:** P3
**Depends on:** REQ-MP-700

Register `MicroPrimeCodeGenerator` as a discoverable code generator via entry points.

**Not required for initial wiring** — direct instantiation in `run_prime_workflow.py` is sufficient. This becomes valuable when config-driven generator selection or third-party generators are needed.

**If implemented:**

```toml
# pyproject.toml
[project.entry-points."startd8.contractors.code_generators"]
lead-contractor = "startd8.contractors.generators.lead_contractor:LeadContractorCodeGenerator"
micro-prime = "startd8.micro_prime.prime_adapter:MicroPrimeCodeGenerator"
```

**Acceptance criteria:**
- Entry point group `startd8.contractors.code_generators` is defined in `pyproject.toml`
- Both generators are registered
- `ContractorRegistry.get_code_generator("micro-prime")` resolves correctly
- `run_prime_workflow.py` can optionally use registry lookup instead of direct import

---

### REQ-MP-710: Workflow-Level Micro Prime Activation API

**Status:** DONE
**Priority:** P1
**Depends on:** REQ-MP-700 (CLI flags), REQ-MP-703 (file writing)

`PrimeContractorWorkflow` SHALL expose `enable_micro_prime()` and `disable_micro_prime()` methods for post-construction activation of local-first code generation, following the existing `enable_complexity_routing()` pattern.

**API:**

```python
def enable_micro_prime(self, config: Optional[MicroPrimeConfig] = None) -> None:
    """Enable local-first generation via Micro Prime.

    Wraps the current code_generator as the fallback for MODERATE/COMPLEX.
    TRIVIAL and SIMPLE elements are handled locally via Ollama.
    """

def disable_micro_prime(self) -> None:
    """Disable Micro Prime, restoring the original code generator."""
```

**Behavior:**
- `enable_micro_prime()` wraps `self.code_generator` with `MicroPrimeCodeGenerator(fallback=self.code_generator)`
- `disable_micro_prime()` unwraps, restoring the original generator
- Uses lazy imports (`from startd8.micro_prime...`) to keep `micro_prime` optional
- Adds `self._micro_prime_enabled: bool = False` and `self._original_code_generator = None` to `__init__()`

**Interaction with complexity routing:**
- When both `enable_micro_prime()` and `enable_complexity_routing()` are active, `enable_micro_prime()` should be called FIRST, then `enable_complexity_routing()` receives the wrapped generator as its base.
- `enable_micro_prime()` MUST be called before `enable_complexity_routing()` to ensure the router sees the wrapped generator.

**Acceptance criteria:**
- `enable_micro_prime()` changes `self.code_generator` to a `MicroPrimeCodeGenerator` instance
- `disable_micro_prime()` restores the original `code_generator` exactly
- Calling `enable_micro_prime()` twice is safe (second call is a no-op or re-wraps)
- Config is forwarded to `MicroPrimeConfig` fields (model, templates_enabled, repair_enabled, etc.)
- Lazy imports — no `ImportError` when `micro_prime` package is unavailable
- INFO log emitted on enable/disable

---

### REQ-MP-711: Runtime Ollama Availability Guard

**Status:** DONE
**Priority:** P1
**Depends on:** REQ-MP-503 (Ollama Availability Check — Artisan preflight)
**Refines:** Risk row "Ollama unavailable at runtime" in the wiring doc risk assessment

`MicroPrimeCodeGenerator.generate()` SHALL check Ollama reachability and model availability once per adapter instance before processing any elements. If Ollama is unreachable or the configured model is not pulled, all elements are delegated to the fallback generator immediately.

**Why distinct from REQ-MP-503:** REQ-MP-503 is an Artisan preflight check that runs during the PREFLIGHT phase (before any generation). The Prime Contractor has no preflight phase. The guard runs on the first `generate()` call and caches the result for subsequent calls.

**Implementation:**

```python
def _check_ollama_available(self) -> bool:
    """Check if Ollama is reachable and model is pulled. Cached per instance."""
```

**Check sequence:**
1. `GET {OLLAMA_HOST}/api/tags` with 5s timeout
2. Parse response for model list
3. Check configured model name exists (with/without `:latest` suffix)
4. Cache result on `self._ollama_available`

**Graceful degradation:**
- Ollama unreachable → WARNING log, delegate all to fallback, zero local processing
- Ollama reachable but model missing → WARNING log, delegate all to fallback
- Ollama available and model present → proceed with local processing
- TRIVIAL elements (templates) still work regardless — they don't need Ollama. However, for simplicity, the guard delegates ALL elements to fallback when Ollama is down. Template-only processing without Ollama is a future optimization.

**Pattern follows:** `preflight.py:_check_ollama_model()` (lines 1095–1156) — same endpoint, same error handling, shorter timeout (5s vs 30s).

**Acceptance criteria:**
- Pipeline completes successfully when Ollama is stopped (all elements via fallback)
- Pipeline completes successfully when model is not pulled (all elements via fallback)
- First call to `generate()` performs the check; subsequent calls use cached result
- WARNING logged with `"Ollama not reachable at {url}"` or `"model '{name}' not found"`
- No `ImportError` — uses stdlib `urllib.request` (not httpx/requests)
- Check timeout is 5 seconds (not blocking generation for 30s)

---

## Dependency Map

```
REQ-MP-701 (manifest deserialization + forwarding)
    │
    └──→ REQ-MP-702 (skeleton generation)
              │
              └──→ REQ-MP-703 (file writing)
                        │
                        └──→ REQ-MP-700 (CLI flags) + REQ-MP-704 (sub-flags)
                        │
                        └──→ REQ-MP-710 (workflow activation API)

REQ-MP-503 (Artisan preflight) ──→ REQ-MP-711 (Ollama availability guard)
REQ-MP-704 (cost tracking)  — independent, parallel
REQ-MP-705 (observability)  — after core wiring
REQ-MP-706 (entry points)   — deferred
```

**Implementation order:**

| Phase | Requirements | What | Est. LOC |
|-------|-------------|------|----------|
| 1 | REQ-MP-701 | Manifest deserialization + context forwarding in `prime_contractor.py` | ~25 |
| 2 | REQ-MP-702 | Skeleton generation in `prime_adapter.py` | ~40 |
| 3 | REQ-MP-703 | File writing in `prime_adapter.py` | ~20 |
| 4 | REQ-MP-700 | CLI flags in `run_prime_workflow.py`, complexity router integration | ~45 |
| 5 | REQ-MP-704 | Cost tracking polish in `prime_adapter.py` | ~15 |
| 6 | REQ-MP-705 | Logging + OTel metrics | ~25 |
| — | REQ-MP-706 | Entry points (deferred) | ~10 |
| **Total** | | | **~180** |

---

## Files to Modify

| File | Changes | Phase |
|------|---------|-------|
| `src/startd8/contractors/prime_contractor.py` | Deserialize `ForwardManifest` in `load_seed_context()`, forward `manifest` in `develop_feature()` `gen_context`; add `enable_micro_prime()` / `disable_micro_prime()` (REQ-MP-710) | 1, 710 |
| `src/startd8/micro_prime/prime_adapter.py` | Add `_generate_skeletons()`, add `output_dir` param, write files to disk, fix `cost_usd`, improve metadata; add `_check_ollama_available()` guard (REQ-MP-711) | 2, 3, 5, 711 |
| `scripts/run_prime_workflow.py` | Add `--micro-prime` flag + sub-flags, use `workflow.enable_micro_prime()` API (REQ-MP-710), complexity router integration | 4, 710 |
| `pyproject.toml` | (Deferred) Add entry point group | — |

---

## Test Plan

| File | Tests | Coverage |
|------|-------|----------|
| `tests/unit/micro_prime/test_prime_adapter.py` | ~12 | Skeleton generation from manifest, file writing, cost merging, fallback delegation, partial success |
| `tests/unit/contractors/test_prime_micro_prime_wiring.py` | ~8 | Manifest deserialization in `load_seed_context`, context key forwarding, graceful degradation on missing manifest |
| `tests/integration/test_prime_micro_prime_e2e.py` | ~5 | End-to-end: seed with manifest → `--micro-prime` → files on disk with correct content |

**Estimated total:** ~25 tests, ~200 LOC test code.

---

## Risk Assessment

| Risk | Impact | Mitigation |
|------|--------|-----------|
| Manifest deserialization fails on production seeds | Micro Prime silently skipped, fallback to LeadContractor | Graceful degradation: `except Exception` with warning log, adapter delegates entirely to fallback |
| Skeleton generation produces invalid Python | Splicer fails, element escalated to cloud | `DeterministicFileAssembler.render_file()` validates via `ast.parse()` internally; per-file try/except in `_generate_skeletons()` |
| Ollama unavailable at runtime | SIMPLE elements can't generate | Existing graceful degradation: `_handle_simple()` catches Ollama errors → escalation to MODERATE |
| Element splice corrupts file | Generated file has syntax errors | Splicer validates final file via `ast.parse()` → returns `None` on failure → element marked escalated |
| Cost tracking double-counts | Budget ceiling hit prematurely | Adapter sets `cost_usd=0.0` for local-only path; cloud costs come only from fallback's `GenerationResult` |
| Feature targets files not in manifest | No skeleton generated for those files | Files without manifest entries are delegated to fallback (existing behavior — `file_spec is None` check at `prime_adapter.py:87`) |

---

## Relationship to REQ-MP-8xx (Shared Complexity Router)

REQ-MP-8xx (Shared Complexity Router) is **DONE** as of commit 0538aaa. It provides:

- `ComplexityTier` enum with TRIVIAL/SIMPLE/MODERATE/COMPLEX
- `classify_tier()` shared classifier wired into `develop_feature()`
- `ComplexityRouter` with per-tier generator slots
- `extract_signals_from_feature()` for Prime Contractor
- `classify_element_shared()` bridge from Micro Prime to shared tier

REQ-MP-7xx builds on this foundation by:
1. Making the adapter functional (REQ-MP-701–703)
2. Registering `MicroPrimeCodeGenerator` as the TRIVIAL/SIMPLE generator in the `ComplexityRouter` (REQ-MP-700)
3. Connecting the end-to-end flow: seed → manifest → skeletons → engine → splice → file → integrate
