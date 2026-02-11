# Prime Contractor Framework

The Prime Contractor framework provides continuous integration for code generation workflows. It ensures code is integrated immediately after each feature is generated, preventing the "backlog integration nightmare" where multiple features developed in isolation create merge conflicts.

## Why This Exists

### The Problem

Before this consolidation, the code generation ecosystem was fragmented across three overlapping packages:

```
ContextCore/scripts/prime_contractor/  →  Workflow scripts (ContextCore-coupled)
startd8-sdk/                           →  LLM abstraction (partial integration)
contextcore-startd8/                   →  Bridge package (583 LOC, redundant)
```

This caused several issues:
1. **Tight coupling**: Prime Contractor couldn't run without ContextCore installed
2. **Code duplication**: Similar functionality in multiple places
3. **Import complexity**: Users had to understand the relationship between packages
4. **Testing difficulty**: Hard to test workflows in isolation

### The Solution

Consolidate into a clean two-layer architecture:

```
startd8-sdk/src/startd8/contractors/   →  Prime Contractor framework (standalone)
ContextCore/                           →  Provides observability adapters when available
```

**Key insight**: The Prime Contractor pattern (generate → integrate → validate → repeat) is independent of observability. It should work standalone, with observability as an optional enhancement.

## Architecture

### Protocol-Based Design

The framework uses Python protocols (interfaces) to enable dependency injection:

```
┌─────────────────────────────────────────────────────────────────┐
│                    PrimeContractorWorkflow                      │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐            │
│  │CodeGenerator │ │ Instrumentor │ │ MergeStrategy│            │
│  │  (Protocol)  │ │  (Protocol)  │ │  (Protocol)  │            │
│  └──────┬───────┘ └──────┬───────┘ └──────┬───────┘            │
│         │                │                │                     │
│  ┌──────┴───────┐ ┌──────┴───────┐ ┌──────┴───────┐            │
│  │LeadContractor│ │   Logging    │ │    Simple    │ ← Standalone│
│  │  Generator   │ │ Instrumentor │ │ MergeStrategy│            │
│  └──────────────┘ └──────────────┘ └──────────────┘            │
│                   ┌──────┴───────┐ ┌──────┴───────┐            │
│                   │ ContextCore  │ │     AST      │ ← Enhanced │
│                   │ Instrumentor │ │ MergeStrategy│            │
│                   └──────────────┘ └──────────────┘            │
└─────────────────────────────────────────────────────────────────┘
```

### Four Protocols

1. **CodeGenerator**: Generates code from task descriptions
   ```python
   class CodeGenerator(Protocol):
       def generate(self, task: str, context: Dict, target_files: List[str]) -> GenerationResult
   ```

2. **Instrumentor**: Emits telemetry (spans, events, metrics, insights)
   ```python
   class Instrumentor(Protocol):
       def emit_span(self, name: str, attributes: Dict) -> SpanContext
       def emit_event(self, event_type: str, data: Dict) -> None
       def emit_metric(self, name: str, value: float, labels: Dict) -> None
       def emit_insight(self, insight_type: str, summary: str, **context) -> None
   ```

3. **SizeEstimator**: Estimates output size before generation (truncation prevention)
   ```python
   class SizeEstimator(Protocol):
       def estimate(self, task: str, inputs: Dict) -> SizeEstimate
   ```

4. **MergeStrategy**: Merges generated code with existing files
   ```python
   class MergeStrategy(Protocol):
       def can_merge(self, source: Path, target: Path) -> bool
       def merge(self, source: Path, target: Path) -> MergeResult
   ```

### Adapters

| Adapter | Type | Description |
|---------|------|-------------|
| `LoggingInstrumentor` | Standalone | Python logging, no external deps |
| `HeuristicSizeEstimator` | Standalone | Rule-based size estimation |
| `SimpleMergeStrategy` | Standalone | Overwrite with backup |
| `ContextCoreInstrumentor` | Enhanced | OTel spans to Tempo |
| `ASTMergeStrategy` | Enhanced | Python AST-aware merge |

## Usage

### Standalone (No ContextCore)

```python
from startd8.contractors import PrimeContractorWorkflow

workflow = PrimeContractorWorkflow()
workflow.queue.add_feature("auth", "Add OAuth2 authentication")
workflow.queue.add_feature("logout", "Add logout endpoint", dependencies=["auth"])

result = workflow.run()
print(f"Processed: {result['processed']}, Succeeded: {result['succeeded']}")
```

### With ContextCore (Enhanced Observability)

```python
from startd8.contractors import PrimeContractorWorkflow
from startd8.contractors.adapters.contextcore import ContextCoreInstrumentor

workflow = PrimeContractorWorkflow(
    instrumentor=ContextCoreInstrumentor(project_id="myproject"),
)
result = workflow.run()  # Emits spans to Tempo, insights to Loki
```

### With Custom Code Generator

```python
from startd8.contractors import PrimeContractorWorkflow
from startd8.contractors.generators import LeadContractorCodeGenerator

workflow = PrimeContractorWorkflow(
    code_generator=LeadContractorCodeGenerator(
        lead_agent="anthropic:claude-sonnet-4-20250514",
        drafter_agent="gemini:gemini-2.5-flash-lite",
    ),
)
```

### Dry Run Mode

```python
workflow = PrimeContractorWorkflow(dry_run=True)
workflow.queue.add_feature("test", "Test feature")
result = workflow.run()  # Preview without executing
```

## Module Structure

```
src/startd8/contractors/
├── __init__.py               # Main exports
├── protocols.py              # Protocol definitions (interfaces)
├── queue.py                  # FeatureQueue - ordered feature queue with dependencies
├── checkpoint.py             # IntegrationCheckpoint - validates code after integration
├── prime_contractor.py       # PrimeContractorWorkflow - per-feature orchestration
├── artisan_contractor.py     # ArtisanContractorWorkflow - 7-phase orchestrator
├── context_seed_handlers.py  # Phase handlers for artisan workflow
├── handoff.py                # Design handoff persistence (two-half split)
├── registry.py               # Plugin discovery via entry points
├── adapters/
│   ├── __init__.py
│   ├── standalone.py         # LoggingInstrumentor, HeuristicSizeEstimator, SimpleMergeStrategy
│   └── contextcore.py        # ContextCoreInstrumentor, ASTMergeStrategy (optional)
├── generators/
│   ├── __init__.py
│   └── lead_contractor.py    # LeadContractorCodeGenerator
└── artisan_phases/           # Phase implementations (design, testing, development, etc.)
```

## Artisan Contractor

The `ArtisanContractorWorkflow` is a 7-phase orchestrator that separates design from implementation. It consumes an enriched context seed and provides explicit phase gates, checkpoint persistence, cost budget enforcement, and a two-half split execution model.

### Phases

```
PLAN ──▶ SCAFFOLD ──▶ DESIGN ──▶ IMPLEMENT ──▶ TEST ──▶ REVIEW ──▶ FINALIZE
```

### Quick Start

```python
from startd8.contractors.artisan_contractor import (
    ArtisanContractorWorkflow, WorkflowConfig, WorkflowPhase,
)
from startd8.contractors.context_seed_handlers import ContextSeedHandlers

config = WorkflowConfig(dry_run=True, cost_budget=5.0)
workflow = ArtisanContractorWorkflow(config=config)

handlers = ContextSeedHandlers.create_all(
    enriched_seed_path="out/seed.json",
    output_dir="out/results",
)
for phase, handler in handlers.items():
    workflow.register_handler(phase, handler)

result = workflow.execute(context={"enriched_seed_path": "out/seed.json"})
```

### Two-Half Split with Design Handoff

The workflow supports split execution where design and implementation run as separate processes, bridged by a `design-handoff.json` file:

```python
from startd8.contractors.handoff import write_design_handoff, load_design_handoff

# First half writes handoff after DESIGN
write_design_handoff(
    output_dir="out/designs",
    enriched_seed_path="/abs/path/to/seed.json",
    project_root="/abs/path/to/project",
    workflow_id="...",
    design_results=context.get("design_results", {}),
    scaffold=context.get("scaffold", {}),
)

# Second half loads handoff for IMPLEMENT → FINALIZE
handoff = load_design_handoff("out/designs")
```

See [Artisan Workflow Guide](../../docs/ARTISAN_WORKFLOW_GUIDE.md) for full documentation.

## Key Concepts

### Feature Queue

Features are processed in dependency order:

```python
queue = FeatureQueue()
queue.add_feature("base", "Base functionality")
queue.add_feature("feature-a", "Feature A", dependencies=["base"])
queue.add_feature("feature-b", "Feature B", dependencies=["base"])
queue.add_feature("final", "Final integration", dependencies=["feature-a", "feature-b"])
```

Processing order: `base` → `feature-a` / `feature-b` (either order) → `final`

### Integration Checkpoints

After each feature is integrated, checkpoints validate the code:

1. **Syntax Check**: Python files must compile
2. **Import Check**: All imports must resolve
3. **Lint Check**: No fatal lint errors
4. **Test Check**: No test regressions (tests that passed before must still pass)

### Pre-flight Size Estimation

Before generating code, the framework estimates output size to prevent truncation:

```python
estimator = HeuristicSizeEstimator()
estimate = estimator.estimate(
    task="Implement a rate limiter with token bucket algorithm",
    inputs={"target_files": ["rate_limiter.py"]}
)
# estimate.lines = 120, estimate.complexity = "high"
```

If estimated size exceeds safe limits (150 lines by default), the workflow warns or blocks.

### Git Safety

The workflow includes git safety features:

- **Dirty check**: Refuses to run with uncommitted changes (unless `--allow-dirty`)
- **Auto-stash**: Optionally stashes changes before proceeding (`--auto-stash`)
- **Backup files**: Creates `.backup` files before overwriting
- **Recovery**: Can restore from stash or backup files

## Backwards Compatibility

The ContextCore `scripts/prime_contractor/` module now imports from startd8:

```python
# In ContextCore/scripts/prime_contractor/__init__.py
try:
    from startd8.contractors import PrimeContractorWorkflow
    # ... enhanced version with ContextCore instrumentation
except ImportError:
    # Fallback to local implementation
    from .workflow import PrimeContractorWorkflow
```

Existing scripts continue to work without changes.

## Migration Guide

### From ContextCore scripts

**Before:**
```python
from scripts.prime_contractor import PrimeContractorWorkflow
```

**After (preferred):**
```python
from startd8.contractors import PrimeContractorWorkflow
```

Both work, but the new import is preferred for new code.

### From contextcore-startd8

The `contextcore-startd8` bridge package is deprecated. Its functionality is now in:

- Code generation: `startd8.contractors.generators.LeadContractorCodeGenerator`
- Observability: `startd8.contractors.adapters.contextcore.ContextCoreInstrumentor`

## Testing

Run the contractor tests:

```bash
cd startd8-sdk
python3 -m pytest tests/contractors/ -v
```

## Design Decisions

### Why Protocols Instead of Base Classes?

Protocols (structural subtyping) allow implementations without inheritance:

```python
# This works - no need to inherit from anything
class MyInstrumentor:
    def emit_span(self, name, attributes): ...
    def emit_event(self, event_type, data): ...
    def emit_metric(self, name, value, labels): ...
    def emit_insight(self, insight_type, summary, **context): ...

# Type checker validates it implements Instrumentor
workflow = PrimeContractorWorkflow(instrumentor=MyInstrumentor())
```

### Why Entry Points for Discovery?

Entry points allow third-party packages to register adapters:

```toml
# In some-package/pyproject.toml
[project.entry-points."startd8.contractors.instrumentors"]
datadog = "some_package:DatadogInstrumentor"
```

The registry automatically discovers and loads registered adapters.

### Why Standalone-First?

Making standalone the default ensures:
1. Easy testing without infrastructure
2. Fast startup (no OTel initialization)
3. Works in environments without observability stack
4. Optional enhancement, not mandatory dependency

## Lessons Learned

### Anti-Patterns We Eliminated

| Anti-Pattern | Impact | Solution |
|--------------|--------|----------|
| Workflow embedded in application code | Couldn't test without full stack | Protocol-based design with standalone adapters |
| Bridge package (contextcore-startd8) | 583 LOC of glue code, extra maintenance | Single package with optional adapters |
| Hard dependencies on observability | Slow startup, complex testing | Standalone-first with optional enhancement |
| Script-style imports (`from scripts.xxx`) | Fragile, non-standard | Proper package structure (`from startd8.contractors`) |

### Key Insight

> The Prime Contractor pattern (generate → integrate → validate → repeat) is independent of observability.

This realization enabled the entire consolidation. When we stopped treating telemetry as a requirement and started treating it as an enhancement, the architecture became clear.

## Cost Tracking

The workflow tracks LLM usage costs across all features:

```python
result = workflow.run()
print(f"Total cost: ${result['total_cost_usd']:.4f}")
print(f"Input tokens: {result['total_input_tokens']}")
print(f"Output tokens: {result['total_output_tokens']}")
```

### Cost Attributes in Telemetry

When using ContextCoreInstrumentor, costs are emitted as span attributes:

| Attribute | Description |
|-----------|-------------|
| `gen_ai.usage.input_tokens` | Tokens sent to LLM |
| `gen_ai.usage.output_tokens` | Tokens received from LLM |
| `contextcore.cost.usd` | Cost in USD for this operation |
| `contextcore.cost.cumulative_usd` | Running total across workflow |

## Observability Flow

When using ContextCoreInstrumentor, telemetry flows to the Grafana stack:

```
┌─────────────────────────────────────────────────────────────────┐
│                    PrimeContractorWorkflow                      │
│                              │                                  │
│                    ContextCoreInstrumentor                      │
│                              │                                  │
└──────────────────────────────┼──────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                      OpenTelemetry SDK                          │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐                │
│  │   Tracer   │  │   Meter    │  │   Logger   │                │
│  └─────┬──────┘  └─────┬──────┘  └─────┬──────┘                │
└────────┼───────────────┼───────────────┼────────────────────────┘
         │               │               │
         ▼               ▼               ▼
    ┌─────────┐    ┌─────────┐    ┌─────────┐
    │  Tempo  │    │  Mimir  │    │  Loki   │
    │ (spans) │    │(metrics)│    │ (logs)  │
    └─────────┘    └─────────┘    └─────────┘
```

### What Gets Emitted

| Signal | Examples |
|--------|----------|
| Spans | `code_generation.preflight`, `code_generation.verify`, `prime_contractor.feature_cost` |
| Events | `feature_selected`, `integration_success`, `integration_failed`, `preflight_decision` |
| Insights | `workflow_started`, `workflow_completed`, `integration_failed` |

## When NOT to Use Prime Contractor

| Scenario | Better Alternative |
|----------|--------------------|
| Single file generation | Use LeadContractorWorkflow directly |
| No integration needed (exploratory) | Use `run_workflow()` from `startd8.workflows` |
| Real-time streaming required | Use Agent SDK with streaming callbacks |
| Human-in-the-loop approval | Consider custom workflow with review steps |

The Prime Contractor is designed for **batch code generation with immediate integration**. If your use case doesn't involve integrating generated code into a source tree, simpler alternatives exist.

## Troubleshooting

### "No files were integrated"

**Cause**: Generated code exists but target paths couldn't be determined.

**Solutions**:
1. Check that `target_files` is set in the feature spec
2. Verify generated files exist in `generated/prime_contractor/{feature_id}/`
3. Run with `dry_run=True` to preview integration paths

### "Validation failed: TRUNCATED"

**Cause**: LLM output was cut off mid-generation.

**Solutions**:
1. Split the feature into smaller tasks (fewer target files per feature)
2. Enable pre-flight estimation: the workflow will warn before generating
3. Use a model with higher output limits

### "Repository has uncommitted changes"

**Cause**: Git safety check preventing integration over dirty files.

**Solutions**:
1. Commit your changes: `git add . && git commit -m "WIP"`
2. Auto-stash: pass `auto_stash=True` to workflow
3. Force proceed: pass `allow_dirty=True` (not recommended)

### ImportError for ContextCore adapters

**Cause**: ContextCore not installed.

**Solutions**:
1. Install ContextCore: `pip install contextcore`
2. Use standalone adapters instead (they work without ContextCore)
3. Check that you're importing from the right place

## Migration Examples

### Migrating a ContextCore Script

**Before** (ContextCore-coupled):
```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from scripts.prime_contractor.workflow import PrimeContractorWorkflow
from scripts.prime_contractor.feature_queue import FeatureQueue

workflow = PrimeContractorWorkflow(
    dry_run=False,
    auto_commit=True,
)
workflow.run()
```

**After** (startd8-native):
```python
from startd8.contractors import PrimeContractorWorkflow
from startd8.contractors.adapters.contextcore import ContextCoreInstrumentor

workflow = PrimeContractorWorkflow(
    instrumentor=ContextCoreInstrumentor(project_id="myproject"),
    dry_run=False,
    auto_commit=True,
)
workflow.run()
```

### Key Differences
- No `sys.path` manipulation
- Explicit instrumentor injection (optional but recommended for observability)
- Same API, cleaner imports

## Changelog

### v0.4.0 (2026-01-27)

- **Consolidated** from ContextCore scripts into startd8-sdk
- **Added** protocol-based design with pluggable adapters
- **Added** pre-flight size estimation (truncation prevention)
- **Added** git safety features (dirty check, auto-stash, backup/recovery)
- **Added** cost tracking (BLC-009)
- **Added** insight emission (BLC-008)
- **Added** LeadContractorCodeGenerator wrapper
- **Deprecated** contextcore-startd8 bridge package

### v0.3.0 (Previous)

- Initial implementation in ContextCore/scripts/prime_contractor/
- Basic feature queue and checkpoint validation
- ContextCore-coupled (required OTel for all operations)
