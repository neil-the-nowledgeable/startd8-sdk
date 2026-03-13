# TUI Shared Workflow Access Plan

## Goal
- Ensure **all agents** (built-in, custom, skill-based) can launch and monitor the **same workflows** inside the TUI with consistent UX, validation, and output handling.
- Provide a **single source of truth** for workflow metadata so menus, job queue, and API clients present identical options.
- Keep changes **incremental**: new registry + adapters without breaking existing CLI or job queue behaviors.

## Non-Goals
- No runtime implementation in this doc (design and code sketches only).
- No UI restyle; reuse existing Rich patterns from `tui_improved.py`.
- No new workflow types; we expose existing ones (iterative dev, skill-aware, document enhancement chain, prompt builder, job queue) via a shared surface.

## Current Gaps (observed)
- Each TUI flow wires its own agent discovery and readiness checks.
- Workflows are scattered across helpers (`tui_improved.py`, `tui_workflow_help.py`, `iterative_workflow.py`, `skill_aware_workflow.py`) without a shared catalog.
- Output folders and response storage vary per flow; no canonical destination hints for multi-agent runs.

## Design Principles
- **Single registry:** workflows described once, consumed everywhere.
- **Deterministic eligibility:** same agent readiness gating for every workflow.
- **Composable runners:** same runner primitives usable from TUI, job queue, or tests.
- **Safe defaults:** mock agent available, dry-run and output preview paths optional.

---

## Feature Group 1 — Workflow Catalog & Metadata
Create a canonical registry that describes workflows, their inputs, and supported capabilities. Stored in `startd8/workflows/registry.py`.

```python
# startd8/workflows/registry.py (new)
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional

WorkflowFn = Callable[..., "WorkflowResultLike"]

@dataclass
class WorkflowDescriptor:
    id: str
    title: str
    summary: str
    runner: WorkflowFn
    inputs: List[str]            # required fields e.g. ["prompt", "context_path"]
    supports_multi_agent: bool
    default_output_dir: Optional[str] = None
    tags: List[str] = None

WORKFLOW_CATALOG: Dict[str, WorkflowDescriptor] = {
    "iterative-dev": WorkflowDescriptor(
        id="iterative-dev",
        title="Iterative Dev",
        summary="Dev+review loop using IterativeDevWorkflow.",
        runner=run_iterative_dev,                 # wrapper defined below
        inputs=["task_description"],
        supports_multi_agent=False,
        default_output_dir="~/startd8/iterative",
        tags=["code", "single-agent"],
    ),
    "skill-aware": WorkflowDescriptor(
        id="skill-aware",
        title="Skill-Aware Dev+Review",
        summary="SkillAwareWorkflow with metrics and circuit handling.",
        runner=run_skill_aware,
        inputs=["task_description"],
        supports_multi_agent=True,
        default_output_dir="~/startd8/skill",
        tags=["code", "skills", "multi-agent"],
    ),
    "doc-enhancement-chain": WorkflowDescriptor(
        id="doc-enhancement-chain",
        title="Document Enhancement Chain",
        summary="Draft → review → polish pipeline for markdown documents.",
        runner=run_doc_chain,
        inputs=["source_path", "instructions"],
        supports_multi_agent=True,
        default_output_dir="~/startd8/docs",
        tags=["docs", "chain"],
    ),
    "prompt-builder": WorkflowDescriptor(
        id="prompt-builder",
        title="Prompt Builder",
        summary="Template-driven prompt assembly.",
        runner=run_prompt_builder,
        inputs=["template_name", "variables"],
        supports_multi_agent=False,
        tags=["prompting"],
    ),
}
```

### Wrapper functions (sketched only)
```python
# startd8/workflows/registry.py (continued)
from startd8 import AgentFramework
from startd8.iterative_workflow import IterativeDevWorkflow
from startd8.workflows.skill_aware_workflow import SkillAwareWorkflow

def run_iterative_dev(agent_name: str, task_description: str, *, framework: AgentFramework):
    agent = framework.get_agent(agent_name)
    workflow = IterativeDevWorkflow(developer_agent=agent, reviewer_agent=agent)
    return workflow.run(task_description)

def run_skill_aware(developer: str, reviewer: str, task_description: str, *, framework: AgentFramework):
    dev = framework.get_agent(developer)
    rev = framework.get_agent(reviewer)
    workflow = SkillAwareWorkflow(developer_agent=dev, reviewer_agent=rev)
    return workflow.run(task_description)
```

---

## Feature Group 2 — Agent Eligibility & Capability Gating
Define a single helper that every TUI menu uses to list valid agents per workflow.

```python
# startd8/tui_agents.py (new helper or reused module)
from typing import List, Dict
from startd8.agent_registry import AgentConfigTester
from startd8.workflows.registry import WorkflowDescriptor

def get_ready_agents_for_workflow(desc: WorkflowDescriptor) -> List[Dict]:
    """Return agents that can run this workflow with reasons when excluded."""
    tester = AgentConfigTester()
    readiness = tester.test_all()

    ready = []
    for name, report in readiness.items():
        if not report.is_ready:
            continue
        ready.append({
            "id": name,
            "model": report.model,
            "provider": report.provider,
            "supports_stream": report.supports_stream,
        })
    return ready
```

### Capability checks example
```python
def validate_agent_support(desc: WorkflowDescriptor, agent_info: Dict) -> None:
    if desc.supports_multi_agent is False and agent_info.get("mode") == "multi":
        raise ValueError(f"{desc.id} does not support multi-agent runs")
```

---

## Feature Group 3 — TUI Surfacing & Navigation
Expose the registry inside the TUI so each workflow appears once, and agents see the same list.

```python
# startd8/tui_improved.py (sketch)
from startd8.workflows.registry import WORKFLOW_CATALOG
from startd8.tui_agents import get_ready_agents_for_workflow

class ImprovedTUI:
    def show_workflow_catalog(self) -> None:
        table = Table(title="Available Workflows")
        table.add_column("ID"); table.add_column("Title"); table.add_column("Tags")
        for desc in WORKFLOW_CATALOG.values():
            table.add_row(desc.id, desc.title, ", ".join(desc.tags or []))
        console.print(table)

    def launch_workflow(self, workflow_id: str) -> None:
        desc = WORKFLOW_CATALOG[workflow_id]
        agents = get_ready_agents_for_workflow(desc)
        agent = self.prompt_for_agent(agents)           # reuse existing prompt helper
        inputs = self.prompt_for_inputs(desc.inputs)    # generic input collector
        result = desc.runner(agent_name=agent["id"], framework=self.framework, **inputs)
        self._render_result(result, desc)
```

### Menu wiring example
```python
# startd8/tui.py (pseudocode hook)
def _workflow_menu(self):
    self.improved_tui.show_workflow_catalog()
    choice = Prompt.ask("Select workflow id")
    self.improved_tui.launch_workflow(choice)
```

---

## Feature Group 4 — Shared Runner Primitives (Single & Multi-Agent)
Standardize how workflows execute for one or many agents so TUI, CLI, and job queue reuse the same code.

```python
# startd8/workflows/runner.py (new)
from typing import Iterable
from startd8.workflows.registry import WorkflowDescriptor

def run_for_agents(desc: WorkflowDescriptor, agents: Iterable[str], *, framework, **kwargs):
    results = []
    for agent_name in agents:
        result = desc.runner(agent_name=agent_name, framework=framework, **kwargs)
        results.append({"agent": agent_name, "result": result})
    return results
```

### Multi-agent document chain example
```python
# inside TUI flow
desc = WORKFLOW_CATALOG["doc-enhancement-chain"]
agents = [a["id"] for a in get_ready_agents_for_workflow(desc)]
results = run_for_agents(
    desc,
    agents,
    framework=self.framework,
    source_path=path,
    instructions=question,
)
for r in results:
    console.print(f"[bold]{r['agent']}[/bold] → {r['result'].output_path}")
```

---

## Feature Group 5 — Output Routing & Storage
Normalize where results go so every workflow exposes predictable destinations.

```python
# startd8/workflows/outputs.py (new helper)
from pathlib import Path
from datetime import datetime

def resolve_output_path(desc_id: str, base_dir: str | None, filename: str) -> Path:
    root = Path(base_dir or "~/.startd8/outputs").expanduser()
    dated = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    return root / desc_id / f"{dated}_{filename}"
```

### Applying in a runner
```python
def run_doc_chain(agent_name: str, source_path: str, instructions: str, *, framework):
    output_path = resolve_output_path("doc-enhancement-chain", None, "review.md")
    # existing chain logic writes to output_path
    return DocumentChainResult(output_path=output_path)
```

---

## Feature Group 6 — Job Queue & Batch Alignment
Allow job queue items to reference catalog IDs, guaranteeing TUI parity.

```python
# job payload example (new field)
{
  "workflow_id": "skill-aware",
  "agents": ["claude-opus", "mock-agent"],
  "inputs": { "task_description": "Add retry logic to Foo" }
}
```

```python
# job runner hook (pseudocode)
from startd8.workflows.registry import WORKFLOW_CATALOG
desc = WORKFLOW_CATALOG[job.workflow_id]
results = run_for_agents(desc, job.agents, framework=framework, **job.inputs)
store_results(job.job_id, results)
```

---

## Feature Group 7 — Telemetry, Audit, and Error Surfacing
Emit structured events for every run so agents share the same diagnostics view.

```python
# startd8/workflows/events.py (new helper)
from dataclasses import dataclass
from typing import Dict, Any

@dataclass
class WorkflowEvent:
    workflow_id: str
    agent: str
    status: str
    details: Dict[str, Any]

def log_workflow_event(event: WorkflowEvent) -> None:
    logger.info(
        "workflow_event",
        extra={"workflow_id": event.workflow_id, **event.details, "agent": event.agent, "status": event.status},
    )
```

### TUI consumption example
```python
try:
    result = desc.runner(...)
    log_workflow_event(WorkflowEvent(desc.id, agent["id"], "success", {"duration_ms": result.total_time_ms}))
except Exception as exc:
    log_workflow_event(WorkflowEvent(desc.id, agent["id"], "error", {"error": str(exc)}))
    self.console.print(f"[red]Failed: {exc}[/red]")
```

---

## Feature Group 8 — Testing Hooks & Fixtures
Provide deterministic tests to keep registry and TUI aligned.

```python
# tests/test_workflow_catalog.py (sketch)
from startd8.workflows.registry import WORKFLOW_CATALOG

def test_catalog_ids_are_unique():
    ids = list(WORKFLOW_CATALOG)
    assert len(ids) == len(set(ids))

def test_required_inputs_are_present():
    for desc in WORKFLOW_CATALOG.values():
        assert desc.inputs, f"{desc.id} must declare inputs"
```

```python
# tests/test_tui_workflow_menu.py (sketch)
from startd8.tui_improved import ImprovedTUI

def test_menu_lists_all_catalog_workflows(mocker):
    tui = ImprovedTUI(framework=mocker.Mock())
    tui.console = mocker.Mock()
    tui.show_workflow_catalog()
    tui.console.print.assert_called()  # ensure table rendered
```

---

## Rollout Steps (phased)
1) Add registry + helper modules (`registry.py`, `tui_agents.py`, `runner.py`, `outputs.py`, `events.py`).
2) Wire TUI workflow menu to the catalog; keep legacy menu behind a feature flag.
3) Update job queue runner to accept `workflow_id` and delegate via the catalog.
4) Add telemetry hooks and align output paths.
5) Write the tests above; add fixtures with `MockAgent` for menu exercises.

---

## Risks & Mitigations
- **Drift between catalog and actual implementations** — enforce uniqueness and required fields in unit tests; add CI check that each `runner` is importable.
- **Agent compatibility surprises** — capability gating and explicit error messages in the TUI when an agent is excluded.
- **User confusion on outputs** — print resolved output path before execution and write to a predictable directory.

---

## Open Questions
- Should streaming be allowed for all workflows or only those that opt-in?
- Do we need per-workflow rate limits when running many agents in parallel?
- Should catalog metadata live in YAML for external extension, or stay in code for now?
