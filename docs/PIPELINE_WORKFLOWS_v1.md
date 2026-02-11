# Startd8 Pipeline Workflows Guide

**Version:** 0.4.0
**Document Version:** v1.2
**Last Updated:** 2026-02-11

> **See also:** [Capability Manifest](capability-index/startd8.workflow.capabilities.yaml) for the full capability inventory and roadmap.

## Overview

Startd8 provides a powerful pipeline orchestration system for chaining multiple LLM agents in sequential workflows. This enables complex multi-step processes where each agent's output feeds into the next agent's input.

### Available Workflows

| Workflow | ID | Pattern | Agents |
|----------|----|---------|--------|
| Pipeline | `pipeline` | Sequential multi-agent | Configurable (1+) |
| Document Enhancement | `doc-enhancement` | Sequential refinement | Multi-agent |
| Iterative Development | `iterative-dev` | Dev-review-fix loop | Multi-agent |
| Design Polish | `design-polish` | 3-stage refinement | Multi-agent |
| Critical Review | `critical-review` | Multi-agent review | Multi-agent |
| Lead Contractor | `lead-contractor` | Spec-driven iteration | Config-based |
| Lead Contractor + ContextCore | `lead-contractor-contextcore` | Spec-driven + tracking | Config-based |
| **Artisan Contractor** | `artisan-contractor` | **7-phase design+implement** | **3-tier (Haiku/Sonnet/Opus)** |
| Policy Analysis | `policy-analysis` | Parallel critical analysis | 2-5 agents |
| Plain Language | `plain-language` | Content simplification | 1-5 agents |

Discover workflows via CLI:

```bash
startd8 workflow list              # List all workflows
startd8 workflow describe pipeline # Show workflow details
startd8 workflow export            # Export YAML definitions
```

## Core Concepts

### Pipeline

A pipeline is a sequence of steps, where each step:
1. Receives input (from previous step or initial input)
2. Optionally transforms the input
3. Sends to an agent for processing
4. Passes output to the next step

```
┌─────────┐     ┌─────────┐     ┌─────────┐
│ Input   │ ──▶ │ Agent 1 │ ──▶ │ Agent 2 │ ──▶ ... ──▶ Output
└─────────┘     └─────────┘     └─────────┘
                     │               │
                     ▼               ▼
                  Transform      Transform
                  (optional)     (optional)
```

### Pipeline Step

Each step consists of:
- **Name**: Identifier for the step
- **Agent**: The LLM agent to use
- **Transform**: Optional function to modify input
- **Metadata**: Optional step-specific data

### Pipeline Result

After execution, a pipeline returns:
- Step-by-step outputs
- Final combined output
- Total time and tokens
- Cost estimates

## Creating Pipelines

### Manual Pipeline Creation

```python
from startd8 import Pipeline
from startd8.providers import ProviderRegistry

ProviderRegistry.discover()
anthropic = ProviderRegistry.get_provider("anthropic")
openai = ProviderRegistry.get_provider("openai")
anthropic.validate_config({})
openai.validate_config({})

# Create pipeline
pipeline = Pipeline(name="design-implement")

# Add steps
pipeline.add_step(
    name="designer",
    agent=anthropic.create_agent("claude-opus-4-5-20251101", name="anthropic:claude-opus-4-5-20251101")
)

pipeline.add_step(
    name="implementer",
    agent=openai.create_agent("gpt-4o", name="openai:gpt-4o"),
    transform=lambda design: f"Implement this design:\n\n{design}"
)

# Run pipeline
result = pipeline.run("Design a user authentication system")

print(f"Final output: {result.final_output}")
print(f"Total time: {result.total_time_ms}ms")
print(f"Total cost: ${result.total_cost:.4f}")
```

### Using Workflow Templates

Startd8 provides pre-built templates for common workflows:

#### Planner-Implementer

Two-step workflow: plan then implement.

```python
from startd8 import WorkflowTemplates
from startd8.providers import ProviderRegistry

ProviderRegistry.discover()
anthropic = ProviderRegistry.get_provider("anthropic")
openai = ProviderRegistry.get_provider("openai")
anthropic.validate_config({})
openai.validate_config({})

pipeline = WorkflowTemplates.planner_implementer(
    planner_agent=anthropic.create_agent("claude-sonnet-4-20250514"),
    implementer_agent=openai.create_agent("gpt-4o"),
)

result = pipeline.run("Create a REST API for user management")
```

#### Code Review

Two-step workflow: review then improve.

```python
from startd8.providers import ProviderRegistry

ProviderRegistry.discover()
anthropic = ProviderRegistry.get_provider("anthropic")
openai = ProviderRegistry.get_provider("openai")
anthropic.validate_config({})
openai.validate_config({})

pipeline = WorkflowTemplates.code_review(
    reviewer_agent=anthropic.create_agent("claude-sonnet-4-20250514"),
    improver_agent=openai.create_agent("gpt-4o"),
)

result = pipeline.run(code_to_review)
```

#### Design Review Chain

Three-step workflow: draft → review → polish.

```python
from startd8.providers import ProviderRegistry

ProviderRegistry.discover()
anthropic = ProviderRegistry.get_provider("anthropic")
openai = ProviderRegistry.get_provider("openai")
anthropic.validate_config({})
openai.validate_config({})

pipeline = WorkflowTemplates.design_review_chain(
    drafter_agent=anthropic.create_agent("claude-sonnet-4-20250514"),
    reviewer_agent=openai.create_agent("gpt-4o"),
    final_reviewer_agent=anthropic.create_agent("claude-opus-4-5-20251101")
)

result = pipeline.run("Design a feature for session management")
```

## Transform Functions

Transforms modify the output from one step before passing to the next:

```python
# Assumes `pipeline` is a Pipeline instance.
from startd8.providers import ProviderRegistry

ProviderRegistry.discover()
anthropic = ProviderRegistry.get_provider("anthropic")
openai = ProviderRegistry.get_provider("openai")
anthropic.validate_config({})
openai.validate_config({})

# Simple transform - add context
pipeline.add_step(
    name="implementer",
    agent=openai.create_agent("gpt-4o"),
    transform=lambda spec: f"Based on this specification:\n\n{spec}\n\nImplement the code."
)

# Complex transform - extract specific section
def extract_requirements(output):
    lines = output.split('\n')
    requirements = []
    in_requirements = False
    for line in lines:
        if 'Requirements:' in line:
            in_requirements = True
        elif in_requirements and line.strip():
            requirements.append(line)
        elif in_requirements and not line.strip():
            break
    return '\n'.join(requirements)

pipeline.add_step(
    name="validator",
    agent=anthropic.create_agent("claude-sonnet-4-20250514"),
    transform=extract_requirements
)
```

## Design Pipeline (TUI)

The TUI provides an interactive Design Pipeline:

### Launching

1. Start TUI: `startd8 tui`
2. Select **🚀 Run Design Pipeline**

### Workflow

1. **Enter Task**: Describe the design task or feature
2. **View Available Agents**: See all agents with Ready status
3. **Select DRAFTER**: Choose agent for initial draft
4. **Select REVIEWER**: Choose agent for critique
5. **Select FINAL POLISH**: Choose agent for polishing
6. **Execute**: Pipeline runs automatically
7. **View Result**: See final design document
8. **Save**: Optionally save to file

### Agent Selection

The pipeline uses modular agent selection:

```python
# Get all ready agents
ready_agents = self._get_ready_agents_for_selection()

# Display in table format
for agent in ready_agents:
    print(f"{agent['icon']} {agent['name']} ({agent['model']})")

# Select for each role
drafter = self._select_ready_agent("Select Agent for DRAFTER")
reviewer = self._select_ready_agent("Select Agent for REVIEWER")
polisher = self._select_ready_agent("Select Agent for FINAL POLISH")
```

## Pipeline Comparison

Compare different pipeline configurations:

```python
from startd8 import PipelineComparison

comparison = PipelineComparison(framework)

# Compare different agent combinations
results = comparison.compare([
    ("anthropic-anthropic", pipeline_anthropic_anthropic),
    ("anthropic-openai", pipeline_anthropic_openai),
    ("openai-openai", pipeline_openai_openai),
])

# View comparison metrics
for name, result in results.items():
    print(f"{name}: {result.total_time_ms}ms, ${result.total_cost:.4f}")
```

## Advanced Patterns

### Conditional Steps

```python
from startd8.providers import ProviderRegistry

def should_refine(output):
    # Check if output needs refinement
    return len(output) < 500 or 'TODO' in output

ProviderRegistry.discover()
anthropic = ProviderRegistry.get_provider("anthropic")
anthropic.validate_config({})

pipeline.add_step(
    name="refiner",
    agent=anthropic.create_agent("claude-sonnet-4-20250514"),
    condition=should_refine  # Only runs if condition is True
)
```

### Error Recovery

```python
from startd8 import Pipeline, ErrorHandling

pipeline = Pipeline(
    name="robust-pipeline",
    error_handling=ErrorHandling.RETRY,
    max_retries=3
)
```

### Parallel Steps (Roadmap)

Parallel execution is planned via `ParallelStep` in the Pipeline refactor (see [capability manifest](capability-index/startd8.workflow.capabilities.yaml), capability `startd8.workflow.execution.parallel`).

```python
# Planned: Pipeline.add_parallel() for concurrent agent execution
pipeline.add_parallel("analyze", [step_a, step_b, step_c], failure_policy="collect_all")
```

### Conditional Routing (Roadmap)

Conditional branching is planned via `ConditionalStep` (see capability `startd8.workflow.execution.conditional`).

```python
# Planned: Pipeline.add_conditional() for content-based branching
pipeline.add_conditional("route", lambda x: "error" in x, error_handler, normal_agent)
```

### Workflow Composition (Roadmap)

Composing workflows from other workflows is planned via `WorkflowStep` (see capability `startd8.workflow.reusability.compose`).

```python
# Planned: Pipeline.add_workflow() for sub-workflow steps
pipeline.add_workflow("enhance", doc_workflow, lambda out: {"document": out})
```

## Storing Results

### Automatic Storage

When a framework is attached, results are stored automatically:

```python
from startd8 import AgentFramework, Pipeline

framework = AgentFramework()
pipeline = Pipeline(name="my-pipeline", framework=framework)

result = pipeline.run("Task description", store=True)
# Results saved to framework storage
```

### Manual Storage

```python
result = pipeline.run("Task description", store=False)

# Manually save
framework.storage.save_pipeline_result(result)
```

### Retrieving Results

```python
# Get by pipeline ID
result = framework.get_pipeline_result(pipeline_id)

# List all pipeline results
results = framework.list_pipeline_results()
```

## Metrics and Reporting

### Per-Step Metrics

```python
result = pipeline.run("Task")

for step in result.steps:
    print(f"Step: {step['step_name']}")
    print(f"  Agent: {step['agent']}")
    print(f"  Model: {step['model']}")
    print(f"  Time: {step['response_time_ms']}ms")
    print(f"  Tokens: {step['tokens']}")
    print(f"  Cost: ${step['cost']:.4f}")
```

### Total Metrics

```python
print(f"Pipeline: {result.pipeline_id}")
print(f"Total Time: {result.total_time_ms}ms")
print(f"Total Tokens: {result.total_tokens}")
print(f"Total Cost: ${result.total_cost:.4f}")
```

### Generate Report

```python
from startd8 import ComparisonReport

report = ComparisonReport(framework)
markdown = report.generate_pipeline_report(result.pipeline_id)

with open("pipeline_report.md", "w") as f:
    f.write(markdown)
```

## Best Practices

1. **Start Simple**: Begin with 2-step pipelines before adding complexity
2. **Use Transforms**: Clear transforms make pipelines more maintainable
3. **Test with Mock**: Validate pipeline logic with MockAgent first
4. **Monitor Costs**: Track token usage across steps
5. **Save Results**: Always store results for comparison
6. **Name Steps Clearly**: Use descriptive names for debugging
7. **Handle Errors**: Implement error handling for production use

## Example Use Cases

### Feature Design

```python
from startd8.providers import ProviderRegistry

ProviderRegistry.discover()
anthropic = ProviderRegistry.get_provider("anthropic")
openai = ProviderRegistry.get_provider("openai")
anthropic.validate_config({})
openai.validate_config({})

pipeline = WorkflowTemplates.design_review_chain(
    drafter_agent=anthropic.create_agent("claude-sonnet-4-20250514"),
    reviewer_agent=openai.create_agent("gpt-4o"),
    final_reviewer_agent=anthropic.create_agent("claude-opus-4-5-20251101")
)

result = pipeline.run("""
Design a session management system for a multiplayer game:
- High scores per session
- Session persistence
- Multi-platform support
""")
```

### Code Generation

```python
from startd8.providers import ProviderRegistry

ProviderRegistry.discover()
anthropic = ProviderRegistry.get_provider("anthropic")
openai = ProviderRegistry.get_provider("openai")
anthropic.validate_config({})
openai.validate_config({})

pipeline = Pipeline(name="code-gen")

pipeline.add_step(name="architect", agent=anthropic.create_agent("claude-sonnet-4-20250514"))
pipeline.add_step(
    name="coder",
    agent=openai.create_agent("gpt-4o"),
    transform=lambda arch: f"Write code for:\n{arch}"
)
pipeline.add_step(
    name="reviewer",
    agent=anthropic.create_agent("claude-sonnet-4-20250514"),
    transform=lambda code: f"Review and fix:\n{code}"
)

result = pipeline.run("Create a user authentication module")
```

### Documentation

```python
from startd8.providers import ProviderRegistry

ProviderRegistry.discover()
anthropic = ProviderRegistry.get_provider("anthropic")
openai = ProviderRegistry.get_provider("openai")
anthropic.validate_config({})
openai.validate_config({})

pipeline = Pipeline(name="docs")

pipeline.add_step(
    name="outline",
    agent=anthropic.create_agent("claude-sonnet-4-20250514"),
    transform=lambda topic: f"Create outline for: {topic}"
)
pipeline.add_step(
    name="writer",
    agent=openai.create_agent("gpt-4o"),
    transform=lambda outline: f"Write documentation:\n{outline}"
)
pipeline.add_step(
    name="editor",
    agent=anthropic.create_agent("claude-sonnet-4-20250514"),
    transform=lambda doc: f"Edit for clarity:\n{doc}"
)

result = pipeline.run("REST API documentation for user service")
```

## Artisan Contractor Workflow

The Artisan Contractor is a 7-phase orchestrated workflow for batch code generation with explicit design review. Unlike the simpler Pipeline workflows above, it operates on an **enriched context seed** (from PlanIngestion + DomainPreflight) and separates design from implementation.

### Phases

```
PLAN ──▶ SCAFFOLD ──▶ DESIGN ──▶ IMPLEMENT ──▶ TEST ──▶ REVIEW ──▶ FINALIZE
```

### Two-Half Execution

The workflow supports split execution, allowing design and implementation to run as separate processes with a **design handoff file** bridging the two halves:

```bash
# First half: design only (writes design-handoff.json)
python3 scripts/run_artisan_design_only.py \
    --seed out/artisan-context-seed-enriched.json \
    --output-dir out/designs

# Second half: implementation only (reads handoff)
python3 scripts/run_artisan_implement_only.py \
    --handoff out/designs/design-handoff.json
```

### Cost Model

Uses a 3-tier model hierarchy — Haiku (drafter), Sonnet (validator), Opus (reviewer) — following the principle of cheap drafts and expensive validation.

### Key Features

- Phase-level checkpoints with JSON persistence
- Cost budget enforcement across all phases
- OpenTelemetry instrumentation (graceful degradation)
- Dry-run mode for safe preview
- Resume from checkpoint after failure

> **Full documentation:** See [ARTISAN_WORKFLOW_GUIDE.md](ARTISAN_WORKFLOW_GUIDE.md) for the complete reference.

## Optional Dependencies

Install optional extras for advanced workflow capabilities:

```bash
pip install startd8[validation]  # JSON Schema validation (jsonschema)
pip install startd8[otel]        # OpenTelemetry tracing (opentelemetry-api, opentelemetry-sdk)
pip install startd8[server]      # HTTP workflow server (starlette, uvicorn)
```

## Workflow Roadmap

The workflow system roadmap is tracked in the [capability manifest](capability-index/startd8.workflow.capabilities.yaml). Planned capabilities by phase:

| Phase | Capabilities | Key Feature |
|-------|-------------|-------------|
| 1 - Foundation | Auto-validation, search/filter, test assertions, async audit | Zero new dependencies |
| 2 - Core Orchestration | Retry/resilience, mixed steps, conditional, parallel, compose | Pipeline refactor (FR-310) |
| 3 - Observability | Dry-run simulation, OpenTelemetry spans, Mermaid visualization | Optional `otel` dependency |
| 4 - Enterprise | HTTP workflow server | Optional `server` dependency |

See also:
- [Gap Analysis](capability-index/startd8.workflow.gap-analysis.md)
- [Functional Requirements](capability-index/startd8.workflow.functional-requirements.yaml)
- [Benefits Manifest](capability-index/startd8.workflow.benefits.yaml)

