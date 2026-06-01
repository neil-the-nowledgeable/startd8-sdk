# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""workflow CLI command group (extracted from cli.py, Pass E)."""

from typing import Optional, List
from typing import Optional, List
from rich.panel import Panel
from pathlib import Path
from rich.table import Table
import typer
from .cli_shared import console, logger


workflow_app = typer.Typer(
    name="workflow",
    help="Workflow discovery and execution commands"
)


def _load_workflow_registry():
    """Load workflow registry module"""
    try:
        from .workflows import WorkflowRegistry
        return WorkflowRegistry
    except ImportError as e:
        console.print(f"[red]Workflow system not available: {e}[/red]")
        raise typer.Exit(1)


@workflow_app.command("list")
def workflow_list(
    capability: Optional[str] = typer.Option(None, help="Filter by capability (partial match)"),
    tag: Optional[str] = typer.Option(None, help="Filter by tag"),
    search: Optional[str] = typer.Option(None, help="Search name and description"),
):
    """List all available workflows, with optional filters."""
    WorkflowRegistry = _load_workflow_registry()
    WorkflowRegistry.discover()

    # Start with all workflows (FR-210, FR-211, FR-212)
    all_workflows = WorkflowRegistry.list_workflow_metadata()
    all_ids = {m.workflow_id for m in all_workflows}

    # Apply filters as intersection
    if capability:
        cap_matches = WorkflowRegistry.find_workflows_by_capability(capability)
        all_ids &= {w.metadata.workflow_id for w in cap_matches}
    if tag:
        tag_matches = WorkflowRegistry.find_workflows_by_tag(tag)
        all_ids &= {w.metadata.workflow_id for w in tag_matches}
    if search:
        search_matches = WorkflowRegistry.search_workflows(search)
        all_ids &= {w.metadata.workflow_id for w in search_matches}

    workflows = [m for m in all_workflows if m.workflow_id in all_ids]

    if not workflows:
        console.print("[yellow]No workflows match the given filters.[/yellow]")
        return

    table = Table(title="Available Workflows")
    table.add_column("ID", style="cyan")
    table.add_column("Name", style="green")
    table.add_column("Description")
    table.add_column("Capabilities", style="dim")

    for meta in workflows:
        table.add_row(
            meta.workflow_id,
            meta.name,
            meta.description[:50] + "..." if len(meta.description) > 50 else meta.description,
            ", ".join(meta.capabilities[:3])
        )

    console.print(table)


@workflow_app.command("describe")
def workflow_describe(
    workflow_id: str = typer.Argument(..., help="Workflow ID to describe")
):
    """Show detailed information about a workflow"""
    WorkflowRegistry = _load_workflow_registry()
    WorkflowRegistry.discover()

    info = WorkflowRegistry.get_workflow_info(workflow_id)
    if not info:
        available = WorkflowRegistry.list_workflows()
        console.print(f"[red]Unknown workflow: {workflow_id}[/red]")
        console.print(f"[dim]Available workflows: {', '.join(available)}[/dim]")
        raise typer.Exit(1)

    # Build info panel
    content = f"""[bold]ID:[/bold] {info['workflow_id']}
[bold]Name:[/bold] {info['name']}
[bold]Version:[/bold] {info['version']}
[bold]Description:[/bold] {info['description']}

[bold]Capabilities:[/bold] {', '.join(info['capabilities'])}
[bold]Tags:[/bold] {', '.join(info['tags'])}

[bold]Agent Requirements:[/bold]
  Requires agents: {info['requires_agents']}
  Agent count: {info['agent_count']}
  Min agents: {info['min_agents']}
  Max agents: {info['max_agents'] or 'unlimited'}

[bold]Input Schema:[/bold]"""

    console.print(Panel(content, title=f"Workflow: {info['name']}"))

    # Print input schema
    schema = info.get('input_schema', {})
    if schema.get('properties'):
        table = Table(title="Inputs")
        table.add_column("Name", style="cyan")
        table.add_column("Type")
        table.add_column("Required")
        table.add_column("Description")

        required = schema.get('required', [])
        for name, prop in schema['properties'].items():
            table.add_row(
                name,
                prop.get('type', '?'),
                "✓" if name in required else "",
                prop.get('description', '')[:40]
            )

        console.print(table)


@workflow_app.command("run")
def workflow_run(
    workflow_id: str = typer.Argument(..., help="Workflow ID to run"),
    config_file: Optional[Path] = typer.Option(
        None, "--config", "-c",
        help="JSON config file path"
    ),
    config_stdin: bool = typer.Option(
        False, "--config-stdin",
        help="Read config from stdin"
    ),
    agent: Optional[List[str]] = typer.Option(
        None, "--agent", "-a",
        help="Agent spec (can specify multiple)"
    ),
    input_text: Optional[str] = typer.Option(
        None, "--input", "-i",
        help="Input text (for simple workflows)"
    ),
    output_file: Optional[Path] = typer.Option(
        None, "--output", "-o",
        help="Output file path"
    ),
    max_retries: Optional[int] = typer.Option(
        None, "--max-retries",
        help="Max retries on transient failures (enables retry policy)"
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run",
        help="Simulate without API calls; show execution plan and cost estimate"
    ),
    provenance: Optional[Path] = typer.Option(
        None, "--provenance",
        help="Path to provenance.json for ContextCore Mottainai inventory"
    ),
    onboarding: Optional[Path] = typer.Option(
        None, "--onboarding",
        help="Path to onboarding-metadata.json for Capability injection"
    ),
    seed: Optional[Path] = typer.Option(
        None, "--seed",
        help="Context seed JSON path (prime-contractor)"
    ),
    project_root: Optional[Path] = typer.Option(
        None, "--project-root",
        help="Target project root (prime-contractor)"
    ),
    micro_prime: bool = typer.Option(
        False, "--micro-prime",
        help="Enable micro-prime local generation"
    ),
    micro_prime_model: Optional[str] = typer.Option(
        None, "--micro-prime-model",
        help="Ollama model for micro-prime"
    ),
    micro_prime_max_tokens: Optional[int] = typer.Option(
        None, "--micro-prime-max-tokens",
        help="Max tokens for micro-prime"
    ),
    micro_prime_no_templates: bool = typer.Option(
        False, "--micro-prime-no-templates",
        help="Disable micro-prime templates"
    ),
    micro_prime_no_repair: bool = typer.Option(
        False, "--micro-prime-no-repair",
        help="Disable micro-prime repair"
    ),
    complexity_routing: bool = typer.Option(
        False, "--complexity-routing",
        help="Enable complexity-based routing"
    ),
    cost_budget: Optional[float] = typer.Option(
        None, "--cost-budget",
        help="Max cost in USD"
    ),
    task_filter: Optional[str] = typer.Option(
        None, "--task-filter",
        help="Comma-separated task IDs to process"
    ),
    auto_commit: bool = typer.Option(
        False, "--auto-commit",
        help="Commit each feature after integration"
    ),
    max_features: Optional[int] = typer.Option(
        None, "--max-features",
        help="Max features to process"
    ),
    lead_agent: Optional[str] = typer.Option(
        None, "--lead-agent",
        help="Lead agent spec (provider:model)"
    ),
    drafter_agent: Optional[str] = typer.Option(
        None, "--drafter-agent",
        help="Drafter agent spec (provider:model)"
    ),
    walkthrough: bool = typer.Option(
        False, "--walkthrough",
        help="Persist prompts without LLM calls"
    ),
    force_regenerate: bool = typer.Option(
        False, "--force-regenerate",
        help="Force regeneration ignoring cache"
    ),
):
    """Run a workflow with the given configuration"""
    import json
    import sys

    WorkflowRegistry = _load_workflow_registry()
    WorkflowRegistry.discover()

    # Build config
    config = {}

    # Read from file
    if config_file:
        if not config_file.exists():
            console.print(f"[red]Config file not found: {config_file}[/red]")
            raise typer.Exit(1)
        config = json.loads(config_file.read_text())

    # Read from stdin
    if config_stdin:
        stdin_data = sys.stdin.read()
        config.update(json.loads(stdin_data))

    # Add agents from CLI
    if agent:
        config["agents"] = list(agent)

    # Add input text
    if input_text:
        # Try to set common input field names
        if "initial_input" not in config:
            config["initial_input"] = input_text
        if "document" not in config:
            config["document"] = input_text
        if "task" not in config:
            config["task"] = input_text

    # Inject ContextCore parameters
    if provenance:
        if not provenance.exists():
            console.print(f"[red]Provenance file not found: {provenance}[/red]")
            raise typer.Exit(1)
        config["provenance_path"] = str(provenance)
    
    if onboarding:
        if not onboarding.exists():
            console.print(f"[red]Onboarding metadata file not found: {onboarding}[/red]")
            raise typer.Exit(1)
        config["onboarding_path"] = str(onboarding)

    # Prime-contractor specific flags
    if seed:
        config["seed_path"] = str(seed)
    if project_root:
        config["project_root"] = str(project_root)
    if micro_prime:
        config["micro_prime"] = True
    if micro_prime_model:
        config["micro_prime_model"] = micro_prime_model
    if micro_prime_max_tokens is not None:
        config["micro_prime_max_tokens"] = micro_prime_max_tokens
    if micro_prime_no_templates:
        config["micro_prime_no_templates"] = True
    if micro_prime_no_repair:
        config["micro_prime_no_repair"] = True
    if complexity_routing:
        config["complexity_routing"] = True
    if cost_budget is not None:
        config["cost_budget"] = cost_budget
    if task_filter:
        config["task_filter"] = task_filter
    if auto_commit:
        config["auto_commit"] = True
    if max_features is not None:
        config["max_features"] = max_features
    if lead_agent:
        config["lead_agent"] = lead_agent
    if drafter_agent:
        config["drafter_agent"] = drafter_agent
    if walkthrough:
        config["walkthrough"] = True
    if force_regenerate:
        config["force_regenerate"] = True

    # Progress callback
    def on_progress(current: int, total: int, message: str):
        console.print(f"[dim][{current}/{total}] {message}[/dim]")

    if dry_run:
        console.print(f"[bold]Dry run: {workflow_id}[/bold]")
    else:
        console.print(f"[bold]Running workflow: {workflow_id}[/bold]")

    try:
        result = WorkflowRegistry.run_workflow(
            workflow_id,
            config=config,
            on_progress=on_progress,
            dry_run=dry_run,
        )
    except Exception as e:
        console.print(f"[red]Error running workflow: {e}[/red]")
        logger.error(f"Workflow failed", exc_info=True, extra={"workflow_id": workflow_id})
        raise typer.Exit(1)

    # Display dry run result as Rich table (FR-510)
    if dry_run and result.success and isinstance(result.output, dict):
        plan = result.output
        table = Table(title="Execution Plan")
        table.add_column("#", style="dim")
        table.add_column("Name")
        table.add_column("Type")
        table.add_column("Agent")
        for step in plan.get("execution_plan", []):
            table.add_row(
                str(step.get("step", "")),
                step.get("name", ""),
                step.get("type", ""),
                step.get("agent", ""),
            )
        console.print(table)
        console.print(f"\n[bold]Estimated cost:[/bold] ${plan.get('estimated_cost', 0):.6f}")
        console.print(f"[bold]Step order:[/bold] {' -> '.join(plan.get('step_order', []))}")
        return

    # Display result
    if result.success:
        console.print(f"\n[green]✓ Workflow completed successfully[/green]")
    else:
        console.print(f"\n[red]✗ Workflow failed: {result.error}[/red]")

    # Show metrics
    if result.metrics is not None:
        console.print(Panel(
            f"[bold]Time:[/bold] {result.metrics.total_time_ms}ms\n"
            f"[bold]Tokens:[/bold] {result.metrics.input_tokens + result.metrics.output_tokens}\n"
            f"[bold]Cost:[/bold] ${result.metrics.total_cost:.4f}\n"
            f"[bold]Steps:[/bold] {result.metrics.step_count}",
            title="Metrics"
        ))
    else:
        # Some failures return WorkflowResult.from_error(...) which does not populate metrics.
        console.print(Panel(
            f"[bold]Time:[/bold] n/a\n"
            f"[bold]Tokens:[/bold] n/a\n"
            f"[bold]Cost:[/bold] n/a\n"
            f"[bold]Steps:[/bold] {len(result.steps) if result.steps is not None else 0}",
            title="Metrics"
        ))

    # Write output
    if output_file and result.output:
        output_file.write_text(str(result.output))
        console.print(f"[green]Output written to: {output_file}[/green]")
    elif result.output:
        console.print("\n[bold]Output:[/bold]")
        output_str = str(result.output)
        if len(output_str) > 500:
            console.print(output_str[:500] + "...")
            console.print(f"[dim]({len(output_str)} characters total)[/dim]")
        else:
            console.print(output_str)

    if not result.success:
        raise typer.Exit(1)


@workflow_app.command("visualize")
def workflow_visualize(
    workflow_id: str = typer.Argument(..., help="Workflow ID to visualize"),
    output: Optional[Path] = typer.Option(
        None, "--output", "-o",
        help="Output file path (default: print to stdout)"
    ),
):
    """Generate a Mermaid flowchart diagram of a workflow's structure (FR-530)."""
    from .workflows.visualizer import WorkflowVisualizer
    from .orchestration import Pipeline, PipelineStep

    WorkflowRegistry = _load_workflow_registry()
    WorkflowRegistry.discover()

    workflow = WorkflowRegistry.get_workflow(workflow_id)
    if workflow is None:
        available = WorkflowRegistry.list_workflows()
        console.print(f"[red]Unknown workflow: {workflow_id}[/red]")
        console.print(f"[dim]Available: {', '.join(available)}[/dim]")
        raise typer.Exit(1)

    # Build a Pipeline from workflow metadata for visualization
    meta = workflow.metadata
    pipeline = Pipeline(name=meta.name)
    for inp in meta.inputs:
        # Create placeholder steps from input definitions
        mock_agent = type('_Agent', (), {'name': inp.name, 'model': 'n/a'})()
        pipeline.add_step(inp.name, mock_agent)

    diagram = WorkflowVisualizer.to_mermaid(pipeline)

    if output:
        output.write_text(diagram)
        console.print(f"[green]Diagram written to: {output}[/green]")
    else:
        console.print(Panel(diagram, title=f"Mermaid: {workflow_id}"))


@workflow_app.command("export")
def workflow_export(
    output_dir: Optional[Path] = typer.Option(
        None, "--output", "-o",
        help="Output directory (default: .startd8/workflows)"
    ),
):
    """
    Export workflows to filesystem for agent discovery.

    Creates YAML files that agents can explore on-demand instead of
    loading all schemas upfront. Follows Anthropic's 'progressive
    disclosure' pattern for token efficiency.

    Example:
        startd8 workflow export
        startd8 workflow export -o ./workflows

    Agents can then:
        1. Read _index.yaml for lightweight workflow listing
        2. Read specific workflow file for full schema when needed
    """
    WorkflowRegistry = _load_workflow_registry()

    output_path = str(output_dir) if output_dir else None

    console.print("[bold]Exporting workflows to filesystem...[/bold]")

    try:
        result = WorkflowRegistry.export_to_filesystem(output_path)
    except Exception as e:
        console.print(f"[red]Error exporting workflows: {e}[/red]")
        raise typer.Exit(1)

    # Display results
    console.print(f"\n[green]✓ Exported to: {result['directory']}[/green]")
    console.print(f"[green]✓ Index file: {result['index']}[/green]")

    console.print("\n[bold]Exported workflows:[/bold]")
    for workflow_id, path in result['files'].items():
        console.print(f"  • {workflow_id}: {path}")

    console.print(f"\n[dim]Agents can now discover workflows by reading the index file,[/dim]")
    console.print(f"[dim]then load full schemas for specific workflows as needed.[/dim]")


@workflow_app.command("new")
def workflow_new(
    name: str = typer.Argument(..., help="Workflow name (e.g., my-workflow)"),
    template: str = typer.Option(
        "basic", "--template", "-t",
        help="Template type: basic, pipeline, multi_agent, async"
    ),
    output_dir: Optional[Path] = typer.Option(
        None, "--output", "-o",
        help="Output directory (default: src/startd8/workflows/builtin/)"
    ),
    description: str = typer.Option(
        "", "--description", "-d",
        help="Workflow description"
    ),
    force: bool = typer.Option(
        False, "--force", "-f",
        help="Overwrite existing file"
    ),
):
    """
    Create a new workflow from a template.

    Templates available:
      basic       - Simple single-agent workflow
      pipeline    - Sequential multi-agent pipeline
      multi_agent - Parallel agent coordination
      async       - Async-first implementation

    Examples:
        startd8 workflow new my-workflow
        startd8 workflow new my-pipeline --template pipeline
        startd8 workflow new custom-flow -t async -d "My async workflow"
    """
    try:
        from .workflows.scaffold import WorkflowScaffolder, ScaffoldConfig
        from .workflows.scaffold_constants import DEFAULT_DESCRIPTION
    except ImportError as e:
        console.print(f"[red]Scaffold module not available: {e}[/red]")
        raise typer.Exit(1)

    # Check Jinja2 availability
    try:
        from .workflows.templates import check_jinja2_available
        if not check_jinja2_available():
            console.print("[red]Jinja2 is required for workflow scaffolding.[/red]")
            console.print("[yellow]Install with: pip install jinja2[/yellow]")
            raise typer.Exit(1)
    except ImportError:
        console.print("[red]Jinja2 is required for workflow scaffolding.[/red]")
        console.print("[yellow]Install with: pip install jinja2[/yellow]")
        raise typer.Exit(1)

    # Use default description if not provided
    if not description:
        description = DEFAULT_DESCRIPTION

    # Build config
    config = ScaffoldConfig(
        name=name,
        template=template,
        output_dir=output_dir,
        description=description,
        force=force,
    )

    # Scaffold the workflow
    scaffolder = WorkflowScaffolder()
    result = scaffolder.scaffold(config)

    if not result.success:
        console.print(f"[red]Error: {result.error}[/red]")
        raise typer.Exit(1)

    # Success output
    console.print(f"[green]✓ Created workflow: {result.file_path}[/green]")
    console.print(f"[dim]  Workflow ID: {result.workflow_id}[/dim]")
    console.print(f"[dim]  Class name: {result.class_name}[/dim]")
    console.print()
    console.print("[bold]Next steps:[/bold]")
    console.print(f"  1. Edit {result.file_path.name} to implement your workflow logic")
    console.print(f"  2. Register the workflow in workflows/builtin/__init__.py")
    console.print(f"  3. Run: startd8 workflow list")
    logger.info(
        "Workflow scaffolded",
        extra={
            "workflow_id": result.workflow_id,
            "class_name": result.class_name,
            "template": template,
            "file_path": str(result.file_path),
        }
    )


@workflow_app.command("templates")
def workflow_templates():
    """List available workflow templates."""
    try:
        from .workflows.scaffold import WorkflowScaffolder
    except ImportError as e:
        console.print(f"[red]Scaffold module not available: {e}[/red]")
        raise typer.Exit(1)

    scaffolder = WorkflowScaffolder()
    templates = scaffolder.list_templates()

    table = Table(title="Available Workflow Templates")
    table.add_column("Template", style="cyan")
    table.add_column("Description")

    for t in templates:
        table.add_row(t["name"], t["description"])

    console.print(table)
    console.print()
    console.print("[dim]Usage: startd8 workflow new <name> --template <template>[/dim]")
