# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0
# See LICENSE.md for complete terms. Government agencies, fossil fuel companies,
# military contractors, and organizations using forced ranking are subject to Maximum Fee.

"""
Command-line interface for StartDate Agent Framework
"""

import os
import typer
from typing import Optional, List
from pathlib import Path
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import print as rprint

from .framework import AgentFramework
from .agents import BaseAgent
from .benchmark import BenchmarkRunner, ComparisonReport
from .providers import ProviderRegistry
from .exceptions import ConfigurationError
from .logging_config import get_logger
from .utils.agent_resolution import resolve_agent_spec as _resolve_agent_impl

# Shared helpers + command groups extracted to sibling modules (Pass E).
from .cli_shared import console, logger, get_framework, _resolve_agent
from .cli_queue import queue_app
from .cli_project import project_app
from .cli_workflow import workflow_app
from .cli_manifest import manifest_app
from .cli_dashboard import dashboard_app
from .cli_element_registry import element_registry_app
from .cli_generate import generate_app


app = typer.Typer(
    name="startd8",
    help="StartDate (startd8) Agent Framework CLI - Multi-LLM benchmarking and development tools"
)

# Global framework instance


@app.command()
def init(
    storage_dir: Path = typer.Option(
        Path.cwd() / ".startd8",
        "--dir", "-d",
        help="Storage directory for startd8 data"
    )
):
    """Initialize startd8 framework in current directory"""
    framework = get_framework(storage_dir)
    console.print(f"✅ Initialized startd8 framework at: {storage_dir}", style="green")
    console.print(f"   - Prompts: {framework.storage.prompts_dir}")
    console.print(f"   - Responses: {framework.storage.responses_dir}")
    console.print(f"   - Benchmarks: {framework.storage.benchmarks_dir}")
    logger.info(
        "Framework initialized",
        extra={
            "storage_dir": str(storage_dir),
            "prompts_dir": str(framework.storage.prompts_dir),
            "responses_dir": str(framework.storage.responses_dir),
            "benchmarks_dir": str(framework.storage.benchmarks_dir)
        }
    )


@app.command()
def create_prompt(
    content: str = typer.Argument(..., help="Prompt content"),
    version: str = typer.Option("1.0.0", "--version", "-v", help="Version identifier"),
    tags: Optional[List[str]] = typer.Option(None, "--tag", "-t", help="Tags (can specify multiple)"),
    storage_dir: Optional[Path] = typer.Option(None, "--dir", "-d", help="Storage directory")
):
    """Create a new versioned prompt"""
    framework = get_framework(storage_dir)
    prompt = framework.create_prompt(
        content=content,
        version=version,
        tags=tags or []
    )
    
    console.print(Panel(
        f"[green]✅ Created prompt[/green]\n\n"
        f"[bold]ID:[/bold] {prompt.id}\n"
        f"[bold]Version:[/bold] {prompt.version}\n"
        f"[bold]Tags:[/bold] {', '.join(prompt.tags) if prompt.tags else 'None'}\n\n"
        f"[dim]{prompt.content[:100]}{'...' if len(prompt.content) > 100 else ''}[/dim]",
        title="Prompt Created"
    ))


@app.command()
def list_prompts(
    tags: Optional[List[str]] = typer.Option(None, "--tag", "-t", help="Filter by tags"),
    storage_dir: Optional[Path] = typer.Option(None, "--dir", "-d", help="Storage directory")
):
    """List all prompts"""
    framework = get_framework(storage_dir)
    prompts = framework.list_prompts(tags=tags)
    
    if not prompts:
        console.print("No prompts found.", style="yellow")
        logger.info("No prompts found", extra={"tags": tags, "storage_dir": str(storage_dir) if storage_dir else None})
        return
    
    table = Table(title=f"Prompts ({len(prompts)} total)")
    table.add_column("ID", style="cyan")
    table.add_column("Version", style="magenta")
    table.add_column("Tags", style="green")
    table.add_column("Content Preview", style="white")
    table.add_column("Created", style="dim")
    
    for prompt in prompts:
        table.add_row(
            prompt.id[:12] + "...",
            prompt.version,
            ", ".join(prompt.tags) if prompt.tags else "-",
            prompt.content[:50] + "..." if len(prompt.content) > 50 else prompt.content,
            prompt.timestamp.strftime("%Y-%m-%d %H:%M")
        )
    
    console.print(table)


@app.command()
def show_prompt(
    prompt_id: str = typer.Argument(..., help="Prompt ID"),
    storage_dir: Optional[Path] = typer.Option(None, "--dir", "-d", help="Storage directory")
):
    """Show details of a specific prompt"""
    framework = get_framework(storage_dir)
    prompt = framework.get_prompt(prompt_id)
    
    if not prompt:
        console.print(f"❌ Prompt {prompt_id} not found", style="red")
        raise typer.Exit(1)
    
    console.print(Panel(
        f"[bold]ID:[/bold] {prompt.id}\n"
        f"[bold]Version:[/bold] {prompt.version}\n"
        f"[bold]Tags:[/bold] {', '.join(prompt.tags) if prompt.tags else 'None'}\n"
        f"[bold]Created:[/bold] {prompt.timestamp}\n\n"
        f"[bold]Content:[/bold]\n{prompt.content}",
        title=f"Prompt {prompt.id[:12]}..."
    ))


@app.command()
def run_benchmark(
    prompt_id: str = typer.Argument(..., help="Prompt ID to benchmark"),
    name: str = typer.Option(..., "--name", "-n", help="Benchmark name"),
    agents: List[str] = typer.Option(
        ["mock:mock-model"],
        "--agent", "-a",
        help=(
            "Agents to test (provider:model; repeatable). Example: "
            "--agent mock:mock-model --agent anthropic:claude-sonnet-4-6 --agent openai:gpt-4o"
        )
    ),
    storage_dir: Optional[Path] = typer.Option(None, "--dir", "-d", help="Storage directory")
):
    """Run a benchmark across multiple agents"""
    framework = get_framework(storage_dir)
    prompt = framework.get_prompt(prompt_id)
    
    if not prompt:
        console.print(f"❌ Prompt {prompt_id} not found", style="red")
        raise typer.Exit(1)
    
    # Initialize agents via ProviderRegistry (provider name or model id)
    agent_instances: List[BaseAgent] = []
    for agent_spec in agents:
        try:
            agent_instances.append(_resolve_agent(agent_spec))
        except ImportError as e:
            console.print(
                f"⚠️  Failed to initialize '{agent_spec}': {e}",
                style="yellow",
            )
        except ConfigurationError as e:
            console.print(
                f"⚠️  Failed to initialize '{agent_spec}': {e}",
                style="yellow",
            )
        except Exception as e:
            console.print(f"⚠️  Failed to initialize '{agent_spec}': {e}", style="yellow")
    
    if not agent_instances:
        console.print("❌ No valid agents to run", style="red")
        raise typer.Exit(1)
    
    console.print(f"🚀 Running benchmark with {len(agent_instances)} agent(s)...", style="cyan")
    
    # Run benchmark
    runner = BenchmarkRunner(framework)
    results = runner.run_benchmark(
        prompt_content=prompt.content,
        agents=agent_instances,
        benchmark_name=name,
        version=prompt.version,
        tags=prompt.tags
    )
    
    console.print(Panel(
        f"[green]✅ Benchmark completed[/green]\n\n"
        f"[bold]Benchmark ID:[/bold] {results['benchmark']['id']}\n"
        f"[bold]Responses:[/bold] {len(results['responses'])}\n"
        f"[bold]Avg Response Time:[/bold] {results['comparison']['avg_response_time_ms']:.2f}ms",
        title=name
    ))


@app.command("compare-models")
def compare_models(
    seed: Path = typer.Option(..., "--seed", help="Shared prime-context-seed.json (same for all models)"),
    models: List[str] = typer.Option(
        ..., "--model", "-m",
        help="Model spec provider:model (repeatable, >=2 required). "
             "Example: -m gemini:gemini-2.5-pro -m openai:gpt-5.5",
    ),
    source_root: Path = typer.Option(Path("."), "--source-root", help="Target project root to copy per model"),
    batch_root: Optional[Path] = typer.Option(None, "--batch-root", help="Output root for the batch"),
    cost_budget: Optional[float] = typer.Option(None, "--cost-budget", help="Per-run cost budget (USD)"),
    per_run_timeout: Optional[float] = typer.Option(
        None, "--per-run-timeout", help="Max seconds per model run (timeout marks it failed, batch continues)"),
    isolation: str = typer.Option("copy", "--isolation", help="copy (incl. dirty files) or worktree (git HEAD only)"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print plan; do not copy or execute"),
):
    """Run the same seed through PrimeContractor across 2+ models in isolated sandboxes, then rank."""
    from .model_comparison import validate_inputs, run_comparison

    deduped = list(dict.fromkeys(models))
    br = batch_root.resolve() if batch_root else None
    err = validate_inputs(deduped, seed.resolve(), source_root.resolve(), br, dry_run)
    if err:
        console.print(f"❌ {err}", style="red")
        raise typer.Exit(2)
    run_comparison(
        seed=seed.resolve(), source_root=source_root.resolve(), models=deduped, batch_root=br,
        cost_budget=cost_budget, per_run_timeout=per_run_timeout, isolation=isolation,
        dry_run=dry_run, log=print,
    )


@app.command()
def compare(
    prompt_id: str = typer.Argument(..., help="Prompt ID to compare responses for"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Output file for markdown report"),
    storage_dir: Optional[Path] = typer.Option(None, "--dir", "-d", help="Storage directory")
):
    """Compare responses for a prompt"""
    framework = get_framework(storage_dir)
    comparison = framework.compare_responses(prompt_id)
    
    # Handle both dict (backward compat) and ResponseComparison model
    if hasattr(comparison, 'model_dump'):
        comparison_dict = comparison.model_dump()
    else:
        comparison_dict = comparison
    
    if comparison_dict['total_responses'] == 0:
        console.print("No responses found for this prompt.", style="yellow")
        logger.info("No responses found for comparison", extra={"prompt_id": prompt_id})
        return
    
    # Show comparison table
    table = Table(title="Response Comparison")
    table.add_column("Agent", style="cyan")
    table.add_column("Model", style="magenta")
    table.add_column("Time (ms)", justify="right", style="green")
    table.add_column("Tokens", justify="right", style="blue")
    table.add_column("Cost ($)", justify="right", style="yellow")
    
    for resp in comparison_dict['responses']:
        table.add_row(
            resp['agent'],
            resp['model'],
            str(resp['response_time_ms']),
            str(resp['tokens']) if resp['tokens'] else "-",
            f"${resp['cost_estimate']:.4f}" if resp['cost_estimate'] else "-"
        )
    
    console.print(table)
    
    # Show rankings
    console.print("\n[bold]🏆 Rankings[/bold]")
    console.print("\n[cyan]By Speed:[/cyan]")
    for i, entry in enumerate(comparison_dict['rankings']['by_speed'][:3], 1):
        console.print(f"  {i}. {entry['agent']} - {entry['time_ms']}ms")
    
    if comparison_dict['rankings']['by_token_efficiency']:
        console.print("\n[cyan]By Token Efficiency:[/cyan]")
        for i, entry in enumerate(comparison_dict['rankings']['by_token_efficiency'][:3], 1):
            console.print(f"  {i}. {entry['agent']} - {entry['tokens']} tokens")
    
    # Generate markdown report if requested
    if output:
        report_gen = ComparisonReport(framework)
        report_gen.generate_markdown_report(prompt_id, output)
        console.print(f"\n✅ Markdown report saved to: {output}", style="green")
        logger.info("Benchmark report saved", extra={"output_file": str(output), "prompt_id": prompt_id})


@app.command()
def list_responses(
    prompt_id: Optional[str] = typer.Option(None, "--prompt", "-p", help="Filter by prompt ID"),
    agent: Optional[str] = typer.Option(None, "--agent", "-a", help="Filter by agent name"),
    storage_dir: Optional[Path] = typer.Option(None, "--dir", "-d", help="Storage directory")
):
    """List all agent responses"""
    framework = get_framework(storage_dir)
    responses = framework.list_responses(prompt_id=prompt_id, agent_name=agent)
    
    if not responses:
        console.print("No responses found.", style="yellow")
        return
    
    table = Table(title=f"Responses ({len(responses)} total)")
    table.add_column("ID", style="cyan")
    table.add_column("Agent", style="magenta")
    table.add_column("Model", style="green")
    table.add_column("Time (ms)", justify="right")
    table.add_column("Tokens", justify="right")
    table.add_column("Created", style="dim")
    
    for response in responses:
        table.add_row(
            response.id[:12] + "...",
            response.agent_name,
            response.model,
            str(response.response_time_ms),
            str(response.token_usage.total) if response.token_usage else "-",
            response.timestamp.strftime("%Y-%m-%d %H:%M")
        )
    
    console.print(table)


@app.command()
def show_response(
    response_id: str = typer.Argument(..., help="Response ID"),
    storage_dir: Optional[Path] = typer.Option(None, "--dir", "-d", help="Storage directory")
):
    """Show details of a specific response"""
    framework = get_framework(storage_dir)
    response = framework.get_response(response_id)
    
    if not response:
        console.print(f"❌ Response {response_id} not found", style="red")
        logger.warning(f"Response not found: {response_id}", extra={"response_id": response_id})
        raise typer.Exit(1)
    
    cost_line = (
        f"[bold]Cost:[/bold] ${response.token_usage.cost_estimate:.4f}\n"
        if response.token_usage
        else ""
    )

    console.print(Panel(
        f"[bold]ID:[/bold] {response.id}\n"
        f"[bold]Agent:[/bold] {response.agent_name}\n"
        f"[bold]Model:[/bold] {response.model}\n"
        f"[bold]Response Time:[/bold] {response.response_time_ms}ms\n"
        f"[bold]Tokens:[/bold] {response.token_usage.total if response.token_usage else 'N/A'}\n"
        f"{cost_line}"
        f"[bold]Created:[/bold] {response.timestamp}\n\n"
        f"[bold]Response:[/bold]\n{response.response}",
        title=f"Response {response.id[:12]}..."
    ))


@app.command()
def stats(
    storage_dir: Optional[Path] = typer.Option(None, "--dir", "-d", help="Storage directory")
):
    """Show overall statistics"""
    framework = get_framework(storage_dir)
    
    prompts = framework.list_prompts()
    responses = framework.list_responses()
    
    total_tokens = sum(r.token_usage.total if r.token_usage else 0 for r in responses)
    total_cost = sum(r.token_usage.cost_estimate if r.token_usage else 0 for r in responses)
    avg_response_time = sum(r.response_time_ms for r in responses) / len(responses) if responses else 0
    
    models_used = set(r.model for r in responses)
    agents_used = set(r.agent_name for r in responses)
    
    console.print(Panel(
        f"[bold cyan]startd8 Framework Statistics[/bold cyan]\n\n"
        f"[bold]Prompts:[/bold] {len(prompts)}\n"
        f"[bold]Responses:[/bold] {len(responses)}\n"
        f"[bold]Total Tokens:[/bold] {total_tokens:,}\n"
        f"[bold]Total Cost:[/bold] ${total_cost:.2f}\n"
        f"[bold]Avg Response Time:[/bold] {avg_response_time:.2f}ms\n\n"
        f"[bold]Models Used:[/bold] {', '.join(models_used) if models_used else 'None'}\n"
        f"[bold]Agents Used:[/bold] {', '.join(agents_used) if agents_used else 'None'}",
        title="📊 Statistics"
    ))


@app.command()
def tui(
    storage_dir: Optional[Path] = typer.Option(None, "--dir", "-d", help="Storage directory"),
):
    """Launch interactive TUI mode"""
    try:
        from .tui_improved import run_improved_tui
        run_improved_tui(storage_dir)
    except ImportError as e:
        # Check if it's specifically questionary missing
        if "questionary" in str(e) and ("No module named" in str(e) or "cannot import" in str(e)):
            console.print(
                "[red]Error: questionary not installed.[/red]\n"
                "Install with: pip install questionary",
                style="red"
            )
        else:
            # Re-raise other ImportErrors (like circular imports)
            console.print(f"[red]Import Error: {e}[/red]", style="red")
            raise typer.Exit(1) from e
    except Exception as e:
        console.print(f"[red]Unexpected Error: {e}[/red]", style="red")
        raise typer.Exit(1) from e


@app.command()
def pipeline(
    prompt_text: str = typer.Argument(..., help="Prompt text"),
    workflow: str = typer.Option("planner-implementer", "--workflow", "-w", help="Workflow template"),
    agents: Optional[List[str]] = typer.Option(
        None,
        "--agent", "-a",
        help="Agents for pipeline steps (provider/model; repeatable). Provide 1 or 2 values.",
    ),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Output file"),
    storage_dir: Optional[Path] = typer.Option(None, "--dir", "-d", help="Storage directory")
):
    """Run a sequential pipeline workflow"""
    from .orchestration import WorkflowTemplates, Pipeline
    
    framework = get_framework(storage_dir)
    
    console.print(f"🔗 Running {workflow} pipeline...\n", style="cyan")
    logger.info(f"Running pipeline workflow: {workflow}", extra={"workflow": workflow, "prompt_length": len(prompt_text)})
    
    # Resolve step agents (default: mock for all steps)
    if not agents:
        step_specs = ["mock", "mock"]
    elif len(agents) == 1:
        step_specs = [agents[0], agents[0]]
    elif len(agents) == 2:
        step_specs = agents
    else:
        console.print("[red]❌ Provide at most 2 --agent values (1 uses the same agent for both steps).[/red]")
        raise typer.Exit(1)

    if workflow == "planner-implementer":
        try:
            planner = _resolve_agent(step_specs[0], name="planner")
            implementer = _resolve_agent(step_specs[1], name="implementer")
        except Exception as e:
            console.print(f"[red]❌ Failed to create pipeline agents: {e}[/red]")
            raise typer.Exit(1)
        pipe = WorkflowTemplates.planner_implementer(
            planner,
            implementer,
        )
    elif workflow == "code-review":
        try:
            reviewer = _resolve_agent(step_specs[0], name="reviewer")
            improver = _resolve_agent(step_specs[1], name="improver")
        except Exception as e:
            console.print(f"[red]❌ Failed to create pipeline agents: {e}[/red]")
            logger.error(
                "Failed to create code-review agents",
                exc_info=True,
                extra={"workflow": workflow, "agent_specs": step_specs, "error": str(e)}
            )
            raise typer.Exit(1)
        pipe = WorkflowTemplates.code_review(
            reviewer,
            improver,
        )
    else:
        console.print(f"❌ Unknown workflow: {workflow}", style="red")
        raise typer.Exit(1)
    
    pipe.framework = framework
    
    with console.status("[cyan]Processing pipeline..."):
        result = pipe.run(prompt_text)
    
    # Display results
    console.print()
    for step in result.steps:
        console.print(Panel(
            f"[bold]{step['agent']}[/bold] ({step['model']})\n\n{step['output']}",
            title=f"Step {step['step_number']}: {step['step_name']}",
            border_style="cyan"
        ))
    
    # Show metrics
    console.print()
    table = Table(title="Pipeline Metrics")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")
    table.add_row("Total Time", f"{result.total_time_ms}ms")
    table.add_row("Total Tokens", str(result.total_tokens))
    table.add_row("Total Cost", f"${result.total_cost:.4f}")
    table.add_row("Pipeline ID", result.pipeline_id)
    console.print(table)
    
    # Log pipeline completion
    logger.info(
        "Pipeline completed",
        extra={
            "workflow": workflow,
            "pipeline_id": result.pipeline_id,
            "total_time_ms": result.total_time_ms,
            "total_tokens": result.total_tokens,
            "total_cost": result.total_cost
        }
    )
    
    # Save if requested
    if output:
        lines = ["# Pipeline Result\n"]
        for step in result.steps:
            lines.append(f"## {step['step_name']}\n")
            lines.append(f"{step['output']}\n")
        
        with open(output, 'w') as f:
            f.write('\n'.join(lines))
        console.print(f"\n✅ Saved to: {output}", style="green")


@app.command()
def templates(
    category: Optional[str] = typer.Option(None, "--category", "-c", help="Filter by category"),
    storage_dir: Optional[Path] = typer.Option(None, "--dir", "-d", help="Storage directory for project templates")
):
    """List available prompt templates"""
    try:
        from .prompt_builder import TemplateLoader
    except ImportError:
        console.print("[red]Prompt Builder not available. Install pyyaml: pip install pyyaml[/red]")
        raise typer.Exit(1)
    
    loader = TemplateLoader(project_dir=storage_dir)
    template_list = loader.list_templates()
    
    if category:
        template_list = [t for t in template_list if t.category == category]
    
    if not template_list:
        console.print("[yellow]No templates found.[/yellow]")
        if category:
            console.print(f"[dim]Filter: category={category}[/dim]")
        return
    
    table = Table(title="Available Prompt Templates")
    table.add_column("ID", style="cyan")
    table.add_column("Name", style="bold")
    table.add_column("Category", style="green")
    table.add_column("Source", style="magenta")
    table.add_column("Variables", justify="right")
    table.add_column("Description")
    
    for template in template_list:
        source_badge = "📦 Built-in" if template.source == "builtin" else "👤 User"
        desc = template.description[:45] + "..." if len(template.description) > 45 else template.description
        
        table.add_row(
            template.id,
            template.name,
            template.category,
            source_badge,
            str(len(template.variables)),
            desc
        )
    
    console.print(table)
    
    # Show template locations
    console.print(f"\n[dim]Built-in: {loader.builtin_dir}[/dim]")
    console.print(f"[dim]User: {loader.user_dir}[/dim]")


@app.command(name="build-prompt")
def build_prompt(
    template_id: str = typer.Argument(..., help="Template ID to use"),
    project_path: Optional[Path] = typer.Option(None, "--project", "-p", help="Project path for context auto-fill"),
    interactive: bool = typer.Option(True, "--interactive/--no-interactive", "-i/-I", help="Use interactive wizard"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Save generated prompt to file"),
    save: bool = typer.Option(True, "--save/--no-save", help="Save prompt to framework"),
    storage_dir: Optional[Path] = typer.Option(None, "--dir", "-d", help="Storage directory")
):
    """Build a prompt from a template"""
    try:
        from .prompt_builder import TemplateLoader, ProjectContext, PromptGenerator, TemplateContext
        from .tui_prompt_builder import run_prompt_builder_wizard
    except ImportError as e:
        console.print(f"[red]Prompt Builder not available: {e}[/red]")
        console.print("[yellow]Install pyyaml: pip install pyyaml[/yellow]")
        raise typer.Exit(1)
    
    loader = TemplateLoader(project_dir=storage_dir)
    template = loader.get_template(template_id)
    
    if not template:
        console.print(f"[red]❌ Template '{template_id}' not found[/red]")
        console.print("\n[yellow]Available templates:[/yellow]")
        for t in loader.list_templates():
            console.print(f"  • {t.id} - {t.name}")
        raise typer.Exit(1)
    
    # Get project context
    context_path = project_path or Path.cwd()
    project_context = ProjectContext(context_path)
    suggestions = project_context.suggest_values()
    
    if interactive:
        # Launch interactive wizard
        import sys
        if not sys.stdin.isatty():
            console.print("[yellow]Non-interactive terminal detected. Using defaults.[/yellow]")
            interactive = False
        else:
            result = run_prompt_builder_wizard(template, context_path, storage_dir)
    
    if not interactive:
        # Use suggestions and defaults non-interactively
        context = TemplateContext(
            project_path=context_path,
            variable_values=suggestions,
            auto_filled=suggestions
        )
        generator = PromptGenerator()
        result = generator.fill_template(template, context)
    
    if not result:
        console.print("[yellow]Prompt building cancelled.[/yellow]")
        raise typer.Exit(0)
    
    # Display result
    console.print(Panel(
        f"[green]✓ Generated prompt from '{template.name}'[/green]\n\n"
        f"Words: {result.word_count} | Lines: {result.line_count}",
        title="Success"
    ))
    
    # Show preview
    preview = result.content[:500] + "..." if len(result.content) > 500 else result.content
    console.print(Panel(preview, title="Preview (first 500 chars)", border_style="dim"))
    
    # Save to file if requested
    if output:
        with open(output, 'w') as f:
            f.write(result.content)
        console.print(f"[green]✅ Saved to {output}[/green]")
    
    # Save to framework if requested
    if save:
        framework = get_framework(storage_dir)
        tags = [f"template:{result.template_id}", "prompt-builder"]
        prompt = framework.create_prompt(
            content=result.content,
            version="1.0.0",
            tags=tags
        )
        console.print(f"[green]✅ Saved to framework with ID: {prompt.id[:12]}...[/green]")


@app.command(name="show-template")
def show_template(
    template_id: str = typer.Argument(..., help="Template ID to show"),
    storage_dir: Optional[Path] = typer.Option(None, "--dir", "-d", help="Storage directory")
):
    """Show details of a specific template"""
    try:
        from .prompt_builder import TemplateLoader
    except ImportError:
        console.print("[red]Prompt Builder not available. Install pyyaml: pip install pyyaml[/red]")
        raise typer.Exit(1)
    
    loader = TemplateLoader(project_dir=storage_dir)
    template = loader.get_template(template_id)
    
    if not template:
        console.print(f"[red]❌ Template '{template_id}' not found[/red]")
        raise typer.Exit(1)
    
    # Show template details
    console.print(Panel(
        f"[bold cyan]{template.name}[/bold cyan]\n\n"
        f"[bold]ID:[/bold] {template.id}\n"
        f"[bold]Category:[/bold] {template.category}\n"
        f"[bold]Version:[/bold] {template.version}\n"
        f"[bold]Source:[/bold] {'📦 Built-in' if template.source == 'builtin' else '👤 User'}\n\n"
        f"[bold]Description:[/bold]\n{template.description}",
        title="Template Details",
        border_style="cyan"
    ))
    
    # Show variables
    if template.variables:
        table = Table(title="Variables", show_header=True)
        table.add_column("Name", style="cyan")
        table.add_column("Type", style="magenta")
        table.add_column("Required", justify="center")
        table.add_column("Default")
        table.add_column("Description")
        
        for var in sorted(template.variables, key=lambda v: v.order):
            table.add_row(
                var.name,
                var.input_type,
                "✓" if var.required else "",
                str(var.default) if var.default else "",
                var.description[:35] + "..." if len(var.description) > 35 else var.description
            )
        
        console.print()
        console.print(table)
    
    # Show content preview
    console.print()
    preview = template.content[:1000] + "\n\n... (truncated)" if len(template.content) > 1000 else template.content
    console.print(Panel(preview, title="Content Preview", border_style="dim"))


# =============================================================================
# Job Queue Commands
# =============================================================================

app.add_typer(queue_app, name="queue")


# =============================================================================
# Project Scaffolding Commands
# =============================================================================

app.add_typer(project_app, name="project")


# =============================================================================
# Workflow Commands
# =============================================================================

app.add_typer(workflow_app, name="workflow")


# ──────────────────────────────────────────────────────────────────────────
# Manifest commands
# ──────────────────────────────────────────────────────────────────────────
app.add_typer(manifest_app, name="manifest")


# ──────────────────────────────────────────────────────────────────────────
# Deterministic frontend code generation (no LLM)
# ──────────────────────────────────────────────────────────────────────────
app.add_typer(generate_app, name="generate")


# =============================================================================
# OTel Telemetry Commands
# =============================================================================


@app.command("otel-status")
def otel_status():
    """Show OpenTelemetry telemetry status and diagnostics."""
    from .otel import get_otel_runtime_state, format_telemetry_banner, OTEL_AVAILABLE

    state = get_otel_runtime_state()
    banner = format_telemetry_banner(state)

    # Determine status color
    if state["will_configure"]:
        status_style = "green"
        status_label = "ACTIVE"
    elif state["severity"] == "error":
        status_style = "red"
        status_label = "ERROR"
    else:
        status_style = "yellow"
        status_label = "INACTIVE"

    # Build detail lines
    import os
    endpoint_env = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "")
    mode_env = os.getenv("STARTD8_OTEL", "")

    # Config file values
    from .otel import _resolve_config_endpoint, _resolve_config_mode
    config_endpoint = _resolve_config_endpoint() or "(not set)"
    config_mode = _resolve_config_mode() or "(not set)"

    lines = [
        f"[bold {status_style}]Status: {status_label}[/bold {status_style}]",
        f"[bold]Banner:[/bold] {banner}",
        "",
        f"[bold]Mode:[/bold]",
        f"  Env (STARTD8_OTEL):       {mode_env or '(not set)'}",
        f"  Config file:              {config_mode}",
        f"  Effective:                {state['mode']}",
        "",
        f"[bold]Endpoint:[/bold]",
        f"  Env (OTEL_EXPORTER_...):  {endpoint_env or '(not set)'}",
        f"  Config file:              {config_endpoint}",
        f"  Effective:                {state['endpoint_effective'] or '(none)'}",
        "",
        f"[bold]OTel packages installed:[/bold] {'Yes' if OTEL_AVAILABLE else 'No'}",
        f"[bold]Endpoint reachable:[/bold]     {state['endpoint_reachable'] if state['endpoint_reachable'] is not None else 'not checked'}",
        f"[bold]Fail-fast:[/bold]              {state['fail_fast']}",
        f"[bold]Reason:[/bold]                 {state['reason']}",
    ]

    # Actionable suggestions
    if not state["will_configure"]:
        lines.append("")
        lines.append("[bold]Suggestions:[/bold]")
        if not OTEL_AVAILABLE:
            lines.append("  - Install OTel: pip install opentelemetry-sdk opentelemetry-exporter-otlp-proto-grpc")
        elif state["reason"] == "disabled_mode":
            lines.append("  - Remove STARTD8_OTEL=disabled or set to 'auto'")
        elif state["reason"] in ("auto_no_collector_found", "auto_endpoint_unreachable", "auto_config_endpoint_unreachable"):
            lines.append("  - Start a collector on localhost:4317 (e.g. Alloy, OTel Collector)")
            lines.append("  - Or persist: startd8 otel-configure --endpoint http://your-collector:4317")
        elif state["reason"] == "enabled_missing_endpoint_fail_fast":
            lines.append("  - Set OTEL_EXPORTER_OTLP_ENDPOINT or run: startd8 otel-configure --endpoint ...")

    console.print(Panel("\n".join(lines), title="OpenTelemetry Status", border_style=status_style))


@app.command("otel-configure")
def otel_configure(
    endpoint: Optional[str] = typer.Option(None, "--endpoint", "-e", help="OTLP endpoint URL (e.g. http://localhost:4317)"),
    mode: Optional[str] = typer.Option(None, "--mode", "-m", help="OTel mode: enabled, auto, or disabled"),
    clear: bool = typer.Option(False, "--clear", help="Clear all OTel config settings"),
):
    """Persist OTel telemetry settings to ~/.startd8/config.json.

    Example:
        startd8 otel-configure --endpoint http://localhost:4317
        startd8 otel-configure --mode enabled
        startd8 otel-configure --clear
    """
    from .config import get_config_manager

    config_mgr = get_config_manager()

    if clear:
        config_mgr.clear_otel_setting("endpoint")
        config_mgr.clear_otel_setting("mode")
        console.print("[green]Cleared OTel config settings.[/green]")
        return

    if endpoint is None and mode is None:
        console.print("[yellow]Provide --endpoint and/or --mode, or --clear.[/yellow]")
        raise typer.Exit(1)

    if mode is not None:
        if mode not in ("enabled", "auto", "disabled"):
            console.print(f"[red]Invalid mode: {mode}. Must be enabled, auto, or disabled.[/red]")
            raise typer.Exit(1)
        config_mgr.set_otel_setting("mode", mode)
        console.print(f"[green]Set otel.mode = {mode}[/green]")

    if endpoint is not None:
        config_mgr.set_otel_setting("endpoint", endpoint)
        console.print(f"[green]Set otel.endpoint = {endpoint}[/green]")

    console.print(f"[dim]Config saved to: {config_mgr.get_config_file_path()}[/dim]")
    console.print("[dim]Run 'startd8 otel-status' to verify.[/dim]")


@app.command("serve")
def serve(
    port: int = typer.Option(8080, "--port", "-p", help="Server port"),
    host: str = typer.Option("0.0.0.0", "--host", help="Bind address"),
    api_key: Optional[str] = typer.Option(
        None, "--api-key", envvar="STARTD8_API_KEY",
        help="API key for mutation endpoints (POST)"
    ),
):
    """Start the HTTP workflow server (FR-522).

    Serves a REST API for listing, triggering, and polling workflows.
    Requires the server extras: pip install startd8[server]

    Example:
        startd8 serve --port 8080
        startd8 serve --api-key secret
    """
    try:
        import uvicorn
        from .server import create_app as _create_server_app
    except ImportError:
        console.print("[red]Server extras required: pip install startd8[server][/red]")
        raise typer.Exit(1)

    server_app = _create_server_app(api_key=api_key)
    console.print(f"[bold]Starting StartD8 server on {host}:{port}[/bold]")
    console.print(f"  GET  http://localhost:{port}/workflows")
    console.print(f"  POST http://localhost:{port}/workflows/{{id}}/run")
    console.print(f"  GET  http://localhost:{port}/workflows/{{id}}/runs/{{run_id}}")
    if api_key:
        console.print(f"  [dim]API key auth enabled for POST endpoints[/dim]")
    uvicorn.run(server_app, host=host, port=port)


# ──────────────────────────────────────────────────────────────────────────
# Dashboard commands (DC-206, DC-208)
# ──────────────────────────────────────────────────────────────────────────
app.add_typer(dashboard_app, name="dashboard")


# ──────────────────────────────────────────────────────────────────────────
# Repair command (REQ-RPL-205)
# ──────────────────────────────────────────────────────────────────────────


@app.command("repair")
def repair(
    files: List[Path] = typer.Argument(..., help="Python files to repair"),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Show what would be repaired without modifying files"
    ),
):
    """Run deterministic repair on local Python files.

    Detects syntax errors (via ast.parse) and lint issues (via ruff) then
    applies the shared repair pipeline to fix them.

    Examples:

        startd8 repair src/mymodule/broken.py

        startd8 repair --dry-run src/mymodule/*.py
    """
    import ast as _ast

    from .repair.config import RepairConfig
    from .repair.models import Diagnostic, SyntaxDiagnostic, LintDiagnostic
    from .repair.orchestrator import run_file_repair

    # Validate files exist
    valid_files: list[Path] = []
    for f in files:
        resolved = f.resolve()
        if not resolved.is_file():
            console.print(f"[yellow]Warning: skipping non-existent file: {f}[/yellow]")
            continue
        if resolved.suffix != ".py":
            console.print(f"[yellow]Warning: skipping non-Python file: {f}[/yellow]")
            continue
        valid_files.append(resolved)

    if not valid_files:
        console.print("[red]No valid Python files to repair.[/red]")
        raise typer.Exit(1)

    # Build file map and diagnostics
    files_map: dict[Path, str] = {}
    diagnostics: list[Diagnostic] = []

    for fpath in valid_files:
        content = fpath.read_text(encoding="utf-8")
        files_map[fpath] = content

        # Detect syntax errors via ast.parse
        try:
            _ast.parse(content)
        except SyntaxError as exc:
            msg = exc.msg or "SyntaxError"
            if exc.lineno:
                msg += f" (line {exc.lineno})"
            diagnostics.append(SyntaxDiagnostic(
                category="syntax",
                file=str(fpath),
                message=msg,
                line=exc.lineno or 0,
                col=exc.offset or 0,
            ))

        # Optionally detect lint issues via ruff
        try:
            import subprocess as _sp
            result = _sp.run(
                ["python3", "-m", "ruff", "check", "--output-format=text", str(fpath)],
                capture_output=True, text=True, timeout=30,
            )
            if result.stdout.strip():
                import re as _re
                for line in result.stdout.strip().splitlines():
                    m = _re.match(
                        r"(?P<file>[^:]+):(?P<line>\d+):(?P<col>\d+):\s*(?P<rule>\w+)\s+(?P<message>.+)",
                        line,
                    )
                    if m:
                        diagnostics.append(LintDiagnostic(
                            category="lint",
                            file=str(fpath),
                            message=m.group("message"),
                            rule=m.group("rule"),
                            line=int(m.group("line")),
                            fixable=True,
                        ))
        except (FileNotFoundError, OSError, _sp.TimeoutExpired):
            pass  # ruff not available — syntax-only repair

    if not diagnostics:
        console.print("[green]All files are clean -- no repairs needed.[/green]")
        return

    config = RepairConfig(repair_enabled=True)
    project_root = Path.cwd()

    outcome = run_file_repair(files_map, diagnostics, config, project_root)

    # Results table
    table = Table(title="Repair Results")
    table.add_column("File", style="cyan")
    table.add_column("Before Valid", justify="center")
    table.add_column("After Valid", justify="center")
    table.add_column("Steps Applied")
    table.add_column("Modified", justify="center")

    for fr in outcome.file_results:
        before = "[green]yes[/green]" if fr.before_valid else "[red]no[/red]"
        after = "[green]yes[/green]" if fr.after_valid else "[red]no[/red]"
        steps = ", ".join(fr.steps_applied) if fr.steps_applied else "[dim]none[/dim]"
        modified = "[green]yes[/green]" if fr.steps_applied else "[dim]no[/dim]"
        table.add_row(fr.file_path.name, before, after, steps, modified)

    console.print(table)

    if dry_run:
        console.print("\n[yellow][DRY RUN] No files were modified.[/yellow]")
        if outcome.repaired_files:
            console.print(f"  Would modify {len(outcome.repaired_files)} file(s):")
            for fpath in outcome.repaired_files:
                console.print(f"    - {fpath}")
        return

    # Write repaired content back
    written = 0
    for fpath, content in outcome.repaired_files.items():
        fpath.write_text(content, encoding="utf-8")
        written += 1

    if written:
        console.print(f"\n[green]Repaired {written} file(s).[/green]")
    else:
        console.print("\n[dim]No files needed modification.[/dim]")


# ──────────────────────────────────────────────────────────────────────────
# Element Registry commands (REQ-MP-1109)
# ──────────────────────────────────────────────────────────────────────────
app.add_typer(element_registry_app, name="element-registry")


if __name__ == "__main__":
    app()

