# Scaffold Capability Implementation Handoff

**Last Updated:** 2026-01-28
**Status:** Design complete, implementation not started
**Priority:** Phase 1 (highest visibility capability)

## Quick Resume

```bash
# To resume this work, tell Claude:
"Resume implementing the scaffold capability for StartD8 SDK workflows.
Read /Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/scaffold/HANDOFF.md first."
```

## What We're Building

A CLI command `startd8 workflow new` that generates new workflow files from templates:

```bash
startd8 workflow new my-workflow --template pipeline
# Creates: src/startd8/workflows/builtin/my_workflow.py
```

## Current State

### ✅ Completed

1. **Analyzed roadmap** - Selected scaffold as first capability (highest visibility, unblocks others)
2. **Design documents drafted** (in previous session, not persisted)
3. **Lessons learned integrated** - 9 applicable lessons identified
4. **Existing code patterns analyzed** - Understood WorkflowBase, CLI structure, template patterns

### ❌ Not Yet Started

1. Create `scaffold_constants.py`
2. Create Jinja2 templates
3. Create `WorkflowScaffolder` class
4. Add `workflow new` CLI command
5. Write tests

## Key Design Decisions

### 1. Template Types (4 variants)

| Template | Use Case |
|----------|----------|
| `basic` | Simple single-agent workflow |
| `pipeline` | Sequential multi-agent pipeline |
| `multi_agent` | Parallel agent coordination |
| `async` | Async-first implementation |

### 2. File Structure to Create

```
src/startd8/workflows/
├── scaffold_constants.py      # NEW: Centralized strings (per LL-MCP-3-8)
├── scaffold.py                # NEW: WorkflowScaffolder class
└── templates/                 # NEW: Jinja2 templates
    ├── __init__.py
    ├── basic.py.jinja
    ├── pipeline.py.jinja
    ├── multi_agent.py.jinja
    └── async.py.jinja
```

### 3. CLI Command Signature

```python
@workflow_app.command("new")
def workflow_new(
    name: str = typer.Argument(..., help="Workflow name (e.g., my-workflow)"),
    template: str = typer.Option("basic", "--template", "-t", help="Template type"),
    output_dir: Optional[Path] = typer.Option(None, "--output", "-o"),
    description: str = typer.Option("", "--description", "-d"),
    force: bool = typer.Option(False, "--force", "-f", help="Overwrite existing"),
):
```

## Lessons Learned to Apply

| Lesson | Application |
|--------|-------------|
| **SDK Leg 4 #2** | Keep CLI thin, delegate to scaffold.py |
| **SDK Leg 9 #3** | Use `yield` not `return` in test fixtures with temp dirs |
| **SDK Leg 9 #4** | Track mock patch paths if we refactor |
| **SDK Leg 9 #5** | Set explicit mock attrs for Pydantic validation |
| **SDK Leg 10 #1** | Entry points require `pip install -e .` |
| **SDK Leg 12 #2** | Optional imports with graceful fallback for Jinja2 |
| **MCP Leg 3 #8** | Centralize constants in `scaffold_constants.py` |

## Existing Patterns to Follow

### WorkflowBase Pattern (from base.py)

```python
class MyWorkflow(WorkflowBase):
    @property
    def metadata(self) -> WorkflowMetadata:
        return WorkflowMetadata(
            workflow_id="my-workflow",
            name="My Workflow",
            description="...",
            inputs=[WorkflowInput(name="...", type="text", required=True)],
        )

    def _execute(self, config, agents, on_progress) -> WorkflowResult:
        # Implementation
        return WorkflowResult(...)
```

### CLI Pattern (from cli.py)

```python
workflow_app = typer.Typer(name="workflow", help="...")
app.add_typer(workflow_app, name="workflow")

@workflow_app.command("new")  # Add here
def workflow_new(...):
    ...
```

## Implementation Order

1. **scaffold_constants.py** - Error messages, default values, template names
2. **templates/__init__.py** - Template loading utilities with Jinja2 optional import
3. **templates/*.jinja** - The 4 template files
4. **scaffold.py** - WorkflowScaffolder class with ScaffoldConfig, ScaffoldResult
5. **cli.py modification** - Add `workflow new` command
6. **tests/** - Unit tests following lesson patterns

## Reference Files

| File | Purpose |
|------|---------|
| `/Users/neilyashinsky/Documents/dev/startd8-sdk/src/startd8/cli.py` | CLI patterns, workflow_app location |
| `/Users/neilyashinsky/Documents/dev/startd8-sdk/src/startd8/workflows/base.py` | WorkflowBase protocol |
| `/Users/neilyashinsky/Documents/dev/startd8-sdk/src/startd8/workflows/models.py` | WorkflowMetadata, WorkflowInput |
| `/Users/neilyashinsky/Documents/dev/startd8-sdk/src/startd8/workflows/builtin/pipeline_workflow.py` | Example workflow |
| `/Users/neilyashinsky/Documents/craft/Lessons_Learned/sdk/SDK_developer_LESSONS_LEARNED.md` | SDK lessons index |
| `/Users/neilyashinsky/Documents/craft/Lessons_Learned/sdk/lessons/04-cli.md` | CLI-specific lessons |

## Context from Capability Index

This work originated from the capability-index project:
- `/Users/neilyashinsky/Documents/craft/capability-index/` - Benefits/capabilities/roadmap YAMLs
- Scaffold is Phase 1 capability with highest visibility score
- Unblocks: auto_validate, assertions, filter capabilities

## Questions Resolved

1. **Where do generated workflows go?** → `src/startd8/workflows/builtin/` by default
2. **Template engine?** → Jinja2 with optional import fallback
3. **Naming convention?** → kebab-case input → snake_case file → PascalCase class
4. **How to test?** → Golden file tests comparing generated output to expected

## Open Questions

1. Should we support custom template directories?
2. Should templates include test file generation?
3. Interactive mode with prompts for metadata?

---

**To continue:** Read this file, then start with `scaffold_constants.py` implementation.
