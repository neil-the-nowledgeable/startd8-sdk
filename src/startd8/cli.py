# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0
# See LICENSE.md for complete terms. Government agencies, fossil fuel companies,
# military contractors, and organizations using forced ranking are subject to Maximum Fee.

"""
Command-line interface for StartDate Agent Framework
"""

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

app = typer.Typer(
    name="startd8",
    help="StartDate (startd8) Agent Framework CLI - Multi-LLM benchmarking and development tools"
)
console = Console()
logger = get_logger(__name__)

# Global framework instance
_framework: Optional[AgentFramework] = None


def get_framework(storage_dir: Optional[Path] = None) -> AgentFramework:
    """Get or create framework instance"""
    global _framework
    if _framework is None:
        _framework = AgentFramework(storage_dir)
    return _framework


def _resolve_agent(spec: str, *, name: Optional[str] = None) -> BaseAgent:
    """
    Resolve an agent spec (provider name or model id) into a BaseAgent.

    This is a thin wrapper around the shared utility for backwards compatibility.
    See startd8.utils.agent_resolution.resolve_agent_spec for full documentation.
    """
    return _resolve_agent_impl(spec, name=name)


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

queue_app = typer.Typer(
    name="queue",
    help="Job queue management commands"
)
app.add_typer(queue_app, name="queue")


def _get_queue_config_path(storage_dir: Optional[Path] = None) -> Path:
    """Get path to queue config file"""
    # Decision C: queue is project-scoped (store config alongside project data).
    base = storage_dir or Path.cwd() / ".startd8"
    return base / "queue" / "config.json"


def _load_queue():
    """Load job queue module"""
    try:
        from .job_queue import (
            JobQueue, JobQueueConfig, create_job_file,
            load_queue_config, save_queue_config
        )
        from .models import JobStatus
        return JobQueue, JobQueueConfig, create_job_file, load_queue_config, save_queue_config, JobStatus
    except ImportError as e:
        console.print(f"[red]Job Queue not available: {e}[/red]")
        raise typer.Exit(1)


@queue_app.command("status")
def queue_status(
    storage_dir: Optional[Path] = typer.Option(None, "--dir", "-d", help="Storage directory")
):
    """Show queue status"""
    JobQueue, JobQueueConfig, _, load_queue_config, _, JobStatus = _load_queue()
    
    config_path = _get_queue_config_path(storage_dir)
    
    if not config_path.exists():
        console.print("[yellow]Queue not configured.[/yellow]")
        console.print("[dim]Run 'startd8 queue configure' to set up the queue.[/dim]")
        return
    
    config = load_queue_config(config_path)
    framework = get_framework(storage_dir)
    queue = JobQueue(config, framework)
    
    status = queue.get_queue_status()
    
    console.print(Panel(
        f"[bold]Watch Folder:[/bold] {status['watch_folder']}\n\n"
        f"[bold]Total Jobs:[/bold] {status['total_jobs']}\n"
        f"  • [green]Pending:[/green] {status['status_counts']['pending']}\n"
        f"  • [cyan]Processing:[/cyan] {status['status_counts']['processing']}\n"
        f"  • [blue]Completed:[/blue] {status['status_counts']['completed']}\n"
        f"  • [red]Failed:[/red] {status['status_counts']['failed']}\n\n"
        f"[bold]Running:[/bold] {'Yes' if status['is_running'] else 'No'}",
        title="Queue Status",
        border_style="cyan"
    ))


@queue_app.command("run")
def queue_run(
    once: bool = typer.Option(False, "--once", help="Process only one job and exit"),
    storage_dir: Optional[Path] = typer.Option(None, "--dir", "-d", help="Storage directory")
):
    """Process pending jobs in the queue"""
    JobQueue, JobQueueConfig, _, load_queue_config, _, JobStatus = _load_queue()
    
    config_path = _get_queue_config_path(storage_dir)
    
    if not config_path.exists():
        console.print("[red]Queue not configured. Run 'startd8 queue configure' first.[/red]")
        raise typer.Exit(1)
    
    config = load_queue_config(config_path)
    framework = get_framework(storage_dir)
    queue = JobQueue(config, framework)
    
    pending = queue.get_pending_jobs()
    
    if not pending:
        console.print("[dim]No pending jobs.[/dim]")
        return
    
    if once:
        console.print(f"[cyan]Processing 1 job...[/cyan]\n")
        result = queue.process_next()
        if result:
            status_color = "green" if result.status == JobStatus.COMPLETED else "red"
            console.print(f"[{status_color}]{result.status.value}[/{status_color}] - Job {result.job_id}")
            if result.response_ids:
                console.print(f"[dim]Responses: {len(result.response_ids)}[/dim]")
    else:
        console.print(f"[cyan]Processing {len(pending)} pending job(s)...[/cyan]\n")
        
        def on_progress(current, total, job, result):
            status_color = "green" if result.status == JobStatus.COMPLETED else "red"
            icon = "✓" if result.status == JobStatus.COMPLETED else "✗"
            console.print(f"[{status_color}]{icon}[/{status_color}] [{current}/{total}] {job.job_id[:12]}... - {result.status.value}")
        
        results = queue.process_all(on_progress=on_progress)
        
        success = sum(1 for r in results if r.status == JobStatus.COMPLETED)
        console.print(f"\n[green]✓ Completed {success}/{len(results)} jobs[/green]")
        logger.info(
            "Batch job processing completed",
            extra={
                "total_jobs": len(results),
                "successful": success,
                "failed": len(results) - success
            }
        )


@queue_app.command("watch")
def queue_watch(
    storage_dir: Optional[Path] = typer.Option(None, "--dir", "-d", help="Storage directory")
):
    """Watch folder and process jobs continuously (Ctrl+C to stop)"""
    JobQueue, JobQueueConfig, _, load_queue_config, _, JobStatus = _load_queue()
    
    config_path = _get_queue_config_path(storage_dir)
    
    if not config_path.exists():
        console.print("[red]Queue not configured. Run 'startd8 queue configure' first.[/red]")
        raise typer.Exit(1)
    
    config = load_queue_config(config_path)
    framework = get_framework(storage_dir)
    queue = JobQueue(config, framework)
    
    console.print(f"[cyan]Watching folder: {config.watch_folder}[/cyan]")
    console.print(f"[dim]Poll interval: {config.poll_interval_seconds}s[/dim]")
    console.print(f"[dim]Press Ctrl+C to stop[/dim]\n")
    
    def on_job_start(job):
        console.print(f"[cyan]▶ Starting job {job.job_id}[/cyan]")
        logger.info(f"Starting job: {job.job_id}", extra={"job_id": job.job_id})
    
    def on_job_complete(job, result):
        status_color = "green" if result.status == JobStatus.COMPLETED else "red"
        console.print(f"[{status_color}]✓ Completed job {job.job_id}[/{status_color}]")
        logger.info(f"Job completed: {job.job_id}", extra={"job_id": job.job_id, "status": "completed"})
    
    def on_job_error(job, error):
        console.print(f"[red]✗ Job {job.job_id} failed: {error}[/red]")
    
    queue.set_callbacks(
        on_start=on_job_start,
        on_complete=on_job_complete,
        on_error=on_job_error
    )
    
    try:
        queue.run_watch()
    except KeyboardInterrupt:
        console.print("\n[yellow]Watch stopped.[/yellow]")
        logger.info("Job queue watcher stopped")


@queue_app.command("add")
def queue_add(
    content: str = typer.Argument(..., help="Prompt content for the job"),
    agents: Optional[List[str]] = typer.Option(None, "--agent", "-a", help="Agents to use (can specify multiple)"),
    priority: int = typer.Option(0, "--priority", "-p", help="Job priority (higher = first)"),
    version: str = typer.Option("1.0.0", "--version", "-v", help="Prompt version"),
    name: str = typer.Option("job", "--name", "-n", help="Job file name prefix"),
    storage_dir: Optional[Path] = typer.Option(None, "--dir", "-d", help="Storage directory")
):
    """Add a new job to the queue"""
    _, _, create_job_file, load_queue_config, _, _ = _load_queue()
    
    config_path = _get_queue_config_path(storage_dir)
    
    if not config_path.exists():
        console.print("[red]Queue not configured. Run 'startd8 queue configure' first.[/red]")
        raise typer.Exit(1)
    
    config = load_queue_config(config_path)
    
    # Generate unique filename
    import uuid
    filename = f"{name}_{uuid.uuid4().hex[:8]}"
    
    file_path = create_job_file(
        output_path=config.watch_folder / filename,
        content=content,
        version=version,
        agents=agents,
        priority=priority
    )
    
    console.print(f"[green]✓ Job file created:[/green]")
    console.print(f"[dim]{file_path}[/dim]")


@queue_app.command("configure")
def queue_configure(
    watch_folder: Path = typer.Option(..., "--folder", "-f", help="Folder to watch for job files"),
    poll_interval: float = typer.Option(5.0, "--interval", "-i", help="Poll interval in seconds"),
    archive: bool = typer.Option(False, "--archive", help="Archive completed jobs"),
    default_agents: Optional[List[str]] = typer.Option(None, "--agent", "-a", help="Default agents"),
    storage_dir: Optional[Path] = typer.Option(None, "--dir", "-d", help="Storage directory")
):
    """Configure the job queue"""
    _, JobQueueConfig, _, _, save_queue_config, _ = _load_queue()
    
    watch_path = Path(watch_folder).expanduser().resolve()
    watch_path.mkdir(parents=True, exist_ok=True)
    
    archive_folder = watch_path / "completed" if archive else None
    
    config = JobQueueConfig(
        watch_folder=watch_path,
        poll_interval_seconds=poll_interval,
        archive_completed=archive,
        archive_folder=archive_folder,
        default_agents=default_agents or ["mock"]
    )
    
    config_path = _get_queue_config_path(storage_dir)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    save_queue_config(config, config_path)
    
    console.print(f"[green]✓ Queue configured![/green]")
    console.print(f"[dim]Watch folder: {watch_path}[/dim]")
    console.print(f"[dim]Config saved to: {config_path}[/dim]")
    logger.info(
        "Queue configured",
        extra={
            "watch_folder": str(watch_path),
            "config_path": str(config_path),
            "poll_interval": config.poll_interval_seconds
        }
    )


@queue_app.command("list")
def queue_list(
    all: bool = typer.Option(False, "--all", "-a", help="Include completed jobs"),
    storage_dir: Optional[Path] = typer.Option(None, "--dir", "-d", help="Storage directory")
):
    """List jobs in the queue"""
    JobQueue, JobQueueConfig, _, load_queue_config, _, JobStatus = _load_queue()
    
    config_path = _get_queue_config_path(storage_dir)
    
    if not config_path.exists():
        console.print("[yellow]Queue not configured.[/yellow]")
        return
    
    config = load_queue_config(config_path)
    framework = get_framework(storage_dir)
    queue = JobQueue(config, framework)
    
    jobs = queue.list_jobs(include_completed=all)
    
    if not jobs:
        console.print("[dim]No jobs found.[/dim]")
        logger.info("No jobs found in queue", extra={"status": status.value if status else "all"})
        return
    
    table = Table(title=f"Jobs ({len(jobs)} total)")
    table.add_column("Job ID", style="cyan")
    table.add_column("Status", justify="center")
    table.add_column("Priority", justify="center")
    table.add_column("Agents", style="green")
    table.add_column("Prompt Preview", style="white")
    
    for job in jobs[:30]:
        preview = job.prompt.content[:35] + "..." if len(job.prompt.content) > 35 else job.prompt.content
        agents = ", ".join(job.agents) if job.agents else "(default)"
        
        status_color = {
            JobStatus.PENDING: "yellow",
            JobStatus.PROCESSING: "cyan",
            JobStatus.COMPLETED: "green",
            JobStatus.FAILED: "red"
        }.get(job.status, "white")
        
        table.add_row(
            job.job_id[:12] + "...",
            f"[{status_color}]{job.status.value}[/{status_color}]",
            str(job.priority),
            agents,
            preview.replace("\n", " ")
        )
    
    console.print(table)


@queue_app.command("clear")
def queue_clear(
    storage_dir: Optional[Path] = typer.Option(None, "--dir", "-d", help="Storage directory")
):
    """Clear completed job status files"""
    JobQueue, _, _, load_queue_config, _, _ = _load_queue()
    
    config_path = _get_queue_config_path(storage_dir)
    
    if not config_path.exists():
        console.print("[yellow]Queue not configured.[/yellow]")
        return
    
    config = load_queue_config(config_path)
    framework = get_framework(storage_dir)
    queue = JobQueue(config, framework)
    
    count = queue.clear_completed()
    console.print(f"[green]✓ Cleared {count} status file(s)[/green]")
    logger.info("Cleared completed job status files", extra={"count": count})


# =============================================================================
# Project Scaffolding Commands
# =============================================================================

project_app = typer.Typer(
    name="project",
    help="Project scaffolding and initialization commands"
)
app.add_typer(project_app, name="project")

@project_app.command("new")
def project_new(
    name: str = typer.Argument(..., help="Name of the new project"),
    template: str = typer.Option("basic-python", "--template", "-t", help="Template to use"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Output directory"),
    force: bool = typer.Option(False, "--force", "-f", help="Overwrite conflicting files regardless of hash state")
):
    """Scaffold a new project or safely update an existing one using hybrid manifest tracking."""
    try:
        from .project.scaffolder import scaffold_project
    except ImportError as e:
        console.print(f"[red]Failed to load project scaffolder: {e}[/red]")
        raise typer.Exit(1)

    result = scaffold_project(
        name=name,
        template=template,
        output_dir=output,
        force=force
    )

    if not result.success:
        console.print(f"[red]Scaffolding Failed:[/red] {result.error}")
        raise typer.Exit(1)
        
    console.print(f"\n[green]Scaffolded {result.files_created} new file(s)[/green]")
    if result.files_updated > 0:
        console.print(f"[cyan]Safely updated {result.files_updated} file(s)[/cyan]")
    if result.files_skipped > 0:
        console.print(f"[yellow]Skipped {result.files_skipped} modified file(s) to protect custom logic[/yellow]")


# =============================================================================
# Workflow Commands
# =============================================================================

workflow_app = typer.Typer(
    name="workflow",
    help="Workflow discovery and execution commands"
)
app.add_typer(workflow_app, name="workflow")


# ──────────────────────────────────────────────────────────────────────────
# Manifest commands
# ──────────────────────────────────────────────────────────────────────────
manifest_app = typer.Typer(
    name="manifest",
    help="Code manifest generation and inspection commands"
)
app.add_typer(manifest_app, name="manifest")


@manifest_app.command("generate")
def manifest_generate(
    path: Optional[str] = typer.Argument(None, help="Source path to scan (default: src/)"),
    output_dir: Optional[str] = typer.Option(None, "--output-dir", help="Cache/output directory"),
    fmt: str = typer.Option("json", "--format", help="Output format: json or yaml"),
    mode: str = typer.Option("static", "--mode", help="Analysis mode: ast_only, static, bytecode"),
    check: bool = typer.Option(False, "--check", help="Exit non-zero if manifests are stale"),
    strict: bool = typer.Option(False, "--strict", help="Treat parse errors as hard failures"),
    verbose: bool = typer.Option(False, "--verbose", help="Print per-file status"),
):
    """Generate code manifests for Python files."""
    from pathlib import Path as P
    from rich.console import Console
    from startd8.utils.manifest_cache import generate_project_manifests, check_manifests_fresh

    console = Console()
    project_root = P.cwd()
    source_root = P(path) if path else None
    cache_dir = P(output_dir) if output_dir else None

    if check:
        fresh, stale = check_manifests_fresh(project_root, source_root, cache_dir)
        if fresh:
            console.print("[green]All manifests are up to date.[/green]")
            raise SystemExit(0)
        else:
            console.print(f"[yellow]{len(stale)} stale manifest(s):[/yellow]")
            for f in stale:
                console.print(f"  {f}")
            raise SystemExit(1)

    manifests = generate_project_manifests(project_root, source_root, cache_dir, mode=mode)

    error_count = sum(1 for m in manifests.values() if m.errors)
    if strict and error_count > 0:
        console.print(f"[red]--strict: {error_count} file(s) had parse errors[/red]")
        raise SystemExit(1)

    if verbose:
        for rel_path, m in sorted(manifests.items()):
            status = "[red]ERROR[/red]" if m.errors else "[green]OK[/green]"
            console.print(f"  {status} {rel_path} ({len(m.elements)} elements)")

    console.print(
        f"[green]Generated manifests for {len(manifests)} file(s)[/green]"
        + (f" ({error_count} with errors)" if error_count else "")
    )


@manifest_app.command("check")
def manifest_check(
    path: Optional[str] = typer.Argument(None, help="Source path to check"),
    output_dir: Optional[str] = typer.Option(None, "--output-dir", help="Cache directory"),
):
    """Check if cached manifests are up to date (no regeneration)."""
    from pathlib import Path as P
    from rich.console import Console
    from startd8.utils.manifest_cache import check_manifests_fresh

    console = Console()
    project_root = P.cwd()
    source_root = P(path) if path else None
    cache_dir = P(output_dir) if output_dir else None

    fresh, stale = check_manifests_fresh(project_root, source_root, cache_dir)
    if fresh:
        console.print("[green]All manifests are up to date.[/green]")
        raise SystemExit(0)
    else:
        console.print(f"[yellow]{len(stale)} stale manifest(s):[/yellow]")
        for f in stale:
            console.print(f"  {f}")
        raise SystemExit(1)


@manifest_app.command("show")
def manifest_show(
    file: str = typer.Argument(..., help="Python file to show manifest for"),
    fqn: Optional[str] = typer.Option(None, "--fqn", help="Show specific element by FQN"),
    fmt: str = typer.Option("tree", "--format", help="Output format: json, yaml, or tree"),
):
    """Show the manifest for a single Python file."""
    import json
    from pathlib import Path as P
    from rich.console import Console
    from rich.tree import Tree
    from startd8.utils.code_manifest import generate_file_manifest, lookup_element

    console = Console()
    project_root = P.cwd()
    file_path = P(file)

    if not file_path.exists():
        console.print(f"[red]File not found: {file}[/red]")
        raise SystemExit(1)

    manifest = generate_file_manifest(file_path, project_root)

    if fqn:
        elem = lookup_element(manifest, fqn)
        if elem is None:
            console.print(f"[red]Element not found: {fqn}[/red]")
            raise SystemExit(1)
        console.print_json(json.dumps(elem.model_dump(), indent=2, default=str))
        return

    if fmt == "json":
        console.print_json(json.dumps(manifest.model_dump(), indent=2, default=str))
    elif fmt == "yaml":
        console.print(manifest.to_yaml())
    else:
        # Tree view
        tree = Tree(f"[bold]{manifest.module}[/bold] ({manifest.file})")
        tree.add(f"digest: {manifest.digest[:20]}...")
        tree.add(f"schema: {manifest.schema_version}")

        if manifest.imports:
            imp_branch = tree.add(f"[cyan]imports[/cyan] ({len(manifest.imports)})")
            for imp in manifest.imports:
                flags = []
                if imp.is_conditional:
                    flags.append("conditional")
                if imp.is_reexport:
                    flags.append("reexport")
                flag_str = f" [{', '.join(flags)}]" if flags else ""
                imp_branch.add(f"{imp.module}{flag_str}")

        if manifest.elements:
            elem_branch = tree.add(f"[green]elements[/green] ({len(manifest.elements)})")
            _add_elements_to_tree(elem_branch, manifest.elements)

        if manifest.errors:
            err_branch = tree.add(f"[red]errors[/red] ({len(manifest.errors)})")
            for err in manifest.errors:
                err_branch.add(f"{err.kind.value}: {err.message}")

        console.print(tree)


def _add_elements_to_tree(branch, elements):
    """Recursively add elements to a Rich tree."""
    for elem in elements:
        sig_str = ""
        if elem.signature:
            params = ", ".join(
                f"{p.name}: {p.annotation}" if p.annotation else p.name
                for p in elem.signature.params
            )
            ret = f" -> {elem.signature.return_annotation}" if elem.signature.return_annotation else ""
            sig_str = f"({params}){ret}"

        label = f"[bold]{elem.kind.value}[/bold] {elem.name}{sig_str}"
        if elem.scope_guard:
            label += f" [dim][{elem.scope_guard}][/dim]"

        child_branch = branch.add(label)
        if elem.children:
            _add_elements_to_tree(child_branch, elem.children)


@manifest_app.command("validate-capabilities")
def manifest_validate_capabilities(
    capability_file: str = typer.Argument(
        ..., help="Path to capability index YAML file"
    ),
    enrich: bool = typer.Option(
        False, "--enrich", help="Enrich evidence with manifest data (dry-run by default)"
    ),
    write: bool = typer.Option(
        False, "--write", help="Write enriched YAML (requires --enrich)"
    ),
):
    """Validate capability index evidence refs against manifest data (CI-1..CI-4).

    Checks that each evidence[].ref with type: "code" exists in the manifest registry.
    Reports drift when refs are missing from manifests.

    When --enrich is used, shows a diff of what would change (dry-run default).
    Use --enrich --write to actually modify the file.
    """
    import yaml
    from rich.console import Console
    from startd8.utils.manifest_registry import ManifestRegistry, _flatten_elements

    console = Console()
    project_root = Path.cwd()

    # Load manifest registry
    registry = ManifestRegistry.from_cache(project_root)

    cap_path = Path(capability_file)
    if not cap_path.exists():
        console.print(f"[red]Capability file not found: {capability_file}[/red]")
        raise SystemExit(1)

    try:
        cap_data = yaml.safe_load(cap_path.read_text(encoding="utf-8"))
    except Exception as exc:
        console.print(f"[red]Failed to parse YAML: {exc}[/red]")
        raise SystemExit(1)

    if not isinstance(cap_data, dict):
        console.print("[red]Invalid capability YAML: expected a mapping[/red]")
        raise SystemExit(1)

    errors: list[str] = []
    enrichments: dict[str, int] = {}  # ref → element_count

    capabilities = cap_data.get("capabilities", [])
    if not isinstance(capabilities, list):
        capabilities = []

    for cap in capabilities:
        cap_id = cap.get("id", cap.get("name", "<unknown>"))
        evidence_list = cap.get("evidence", [])
        if not isinstance(evidence_list, list):
            continue

        for ev in evidence_list:
            if not isinstance(ev, dict):
                continue
            if ev.get("type") != "code":
                continue

            ref = ev.get("ref", "")
            if not ref:
                continue

            # Path traversal sanitization (req R1-S8)
            ref_path = Path(ref)
            if ref_path.is_absolute() or ".." in ref_path.parts:
                errors.append(
                    f"SECURITY: {cap_id} evidence ref '{ref}' "
                    f"contains path traversal (absolute path or '..' component)"
                )
                continue

            # Path normalization (plan R1-S9): normalize to POSIX
            normalized_ref = ref.replace("\\", "/")

            if registry is not None:
                # Registry-first validation (plan R2-S7)
                manifest = registry.get(normalized_ref)
                if manifest is None:
                    errors.append(
                        f"DRIFT: {cap_id} evidence ref '{ref}' not found in manifests"
                    )
                else:
                    enrichments[ref] = len(_flatten_elements(manifest.elements))
            else:
                # No registry loaded — fall back to disk check
                full_path = project_root / normalized_ref
                if not full_path.exists():
                    errors.append(
                        f"DRIFT: {cap_id} evidence ref '{ref}' not found on disk"
                    )

    if errors:
        for err in errors:
            if err.startswith("SECURITY"):
                console.print(f"[red]{err}[/red]")
            else:
                console.print(f"[yellow]{err}[/yellow]")
        console.print(f"\n[red]{len(errors)} issue(s) found[/red]")
        raise SystemExit(1)
    else:
        console.print(
            f"[green]All evidence refs validated ({len(enrichments)} code refs checked)[/green]"
        )

    if enrich and enrichments:
        if write:
            # TODO(phase4): implement ruamel.yaml round-trip writing per req R3-S9
            console.print("[yellow]--write: enrichment writing not yet implemented[/yellow]")
        else:
            console.print("\n[cyan]Enrichment preview (--dry-run):[/cyan]")
            for ref, count in sorted(enrichments.items()):
                console.print(f"  {ref}: manifest_element_count={count}")


@manifest_app.command("validate-forward")
def manifest_validate_forward(
    manifest_path: str = typer.Argument(..., help="Path to the ForwardManifest JSON schema or seed"),
    source_path: Optional[str] = typer.Option(None, "--source-path", help="Path to project root (default: cwd)"),
):
    """Validate codebase against a prescribed ForwardManifest contract."""
    import json
    from pathlib import Path as P
    from rich.console import Console
    from rich.table import Table
    from startd8.forward_manifest import ForwardManifest
    from startd8.utils.manifest_registry import ManifestRegistry
    from startd8.forward_manifest_validator import validate_forward_manifest

    console = Console()
    project_root = P(source_path) if source_path else P.cwd()
    manifest_file = P(manifest_path)

    if not manifest_file.exists():
        console.print(f"[red]Manifest file not found: {manifest_file}[/red]")
        raise SystemExit(1)

    try:
        raw_data = json.loads(manifest_file.read_text(encoding="utf-8"))
        
        # Determine if it's a raw ContextSeed or a pure ForwardManifest
        if "forward_manifest" in raw_data:
            manifest_dict = raw_data["forward_manifest"]
        else:
            manifest_dict = raw_data
            
        manifest = ForwardManifest.model_validate(manifest_dict)
    except Exception as exc:
        console.print(f"[red]Failed to parse ForwardManifest: {exc}[/red]")
        raise SystemExit(1)

    # Load manifest registry to scan the current codebase topology
    registry = ManifestRegistry.from_cache(project_root)
    if registry is None:
        console.print("[red]No codebase manifest cache found. Run 'startd8 manifest generate' first.[/red]")
        raise SystemExit(1)

    # Execute validator engine
    violations = validate_forward_manifest(manifest, registry)

    if not violations:
        console.print("[green]✅ ForwardManifest validation passed. Codebase aligns with contracts.[/green]")
        raise SystemExit(0)

    # Summarize and format violations
    table = Table(title=f"Contract Violations ({len(violations)})")
    table.add_column("Severity", style="bold")
    table.add_column("Type", style="cyan")
    table.add_column("Contract ID", style="magenta")
    table.add_column("Expected", style="green")
    table.add_column("Actual", style="red")
    
    error_count = 0
    warning_count = 0

    for v in violations:
        sev_color = "red" if v.severity == "error" else "yellow"
        if v.severity == "error":
            error_count += 1
        else:
            warning_count += 1
            
        table.add_row(
            f"[{sev_color}]{v.severity.upper()}[/{sev_color}]",
            v.violation_type,
            v.contract_id,
            v.expected,
            v.actual or "-"
        )

    console.print(table)
    
    if error_count > 0:
        console.print(f"[red]❌ Validation failed with {error_count} error(s) and {warning_count} warning(s).[/red]")
        raise SystemExit(1)
    else:
        console.print(f"[yellow]⚠️ Validation passed with {warning_count} warning(s).[/yellow]")
        raise SystemExit(0)


@manifest_app.command("calls")
def manifest_calls(
    fqn: str = typer.Argument(..., help="Fully-qualified name to inspect"),
    fmt: str = typer.Option("text", "--format", help="Output format: text or json"),
):
    """Show outbound calls for a specific element."""
    import json as json_mod
    from rich.console import Console
    from startd8.utils.code_manifest import generate_file_manifest, lookup_element
    from startd8.utils.manifest_registry import ManifestRegistry

    console = Console()
    project_root = Path.cwd()

    registry = ManifestRegistry.from_cache(project_root)
    if registry is None:
        console.print("[red]No manifest cache found. Run 'manifest generate --mode bytecode' first.[/red]")
        raise SystemExit(1)

    result = registry.resolve_fqn(fqn)
    if result is None:
        console.print(f"[red]FQN not found: {fqn}[/red]")
        raise SystemExit(1)

    _file_path, element = result
    if element.call_graph is None:
        console.print(f"[yellow]No call graph data for {fqn}. Regenerate with --mode bytecode.[/yellow]")
        raise SystemExit(0)

    cg = element.call_graph
    if fmt == "json":
        console.print_json(json_mod.dumps(cg.model_dump(), indent=2, default=str))
    else:
        console.print(f"[bold]Calls from {fqn}[/bold] ({len(cg.calls)} total)")
        for call in cg.calls:
            status = "[green]resolved[/green]" if call.target_fqn else "[yellow]unresolved[/yellow]"
            receiver = f" on {call.receiver}" if call.receiver else ""
            console.print(f"  {call.target}{receiver} ({call.kind.value}) {status}")
            if call.target_fqn:
                console.print(f"    -> {call.target_fqn}")
        if cg.attribute_reads:
            console.print(f"\n[cyan]Attribute reads:[/cyan] {', '.join(cg.attribute_reads)}")
        if cg.attribute_writes:
            console.print(f"[cyan]Attribute writes:[/cyan] {', '.join(cg.attribute_writes)}")
        if cg.has_dynamic_dispatch:
            console.print("[yellow]Dynamic dispatch detected[/yellow]")


@manifest_app.command("callers")
def manifest_callers(
    fqn: str = typer.Argument(..., help="Fully-qualified name to find callers of"),
    fmt: str = typer.Option("text", "--format", help="Output format: text or json"),
):
    """Show direct callers of a specific element."""
    import json as json_mod
    from rich.console import Console
    from startd8.utils.manifest_registry import ManifestRegistry

    console = Console()
    project_root = Path.cwd()

    registry = ManifestRegistry.from_cache(project_root)
    if registry is None:
        console.print("[red]No manifest cache found. Run 'manifest generate --mode bytecode' first.[/red]")
        raise SystemExit(1)

    callers = registry.callers_of(fqn)
    if fmt == "json":
        console.print_json(json_mod.dumps({"fqn": fqn, "callers": sorted(callers)}, indent=2))
    else:
        console.print(f"[bold]Callers of {fqn}[/bold] ({len(callers)} total)")
        for caller in sorted(callers):
            console.print(f"  {caller}")
        if not callers:
            console.print("  [dim]No callers found[/dim]")


@manifest_app.command("blast-radius")
def manifest_blast_radius(
    fqn: str = typer.Argument(..., help="Fully-qualified name to compute blast radius for"),
    max_depth: int = typer.Option(10, "--max-depth", help="Maximum traversal depth"),
    fmt: str = typer.Option("text", "--format", help="Output format: text or json"),
):
    """Compute transitive callers (blast radius) for a planned change."""
    import json as json_mod
    from rich.console import Console
    from startd8.utils.manifest_registry import ManifestRegistry

    console = Console()
    project_root = Path.cwd()

    registry = ManifestRegistry.from_cache(project_root)
    if registry is None:
        console.print("[red]No manifest cache found. Run 'manifest generate --mode bytecode' first.[/red]")
        raise SystemExit(1)

    radius = registry.blast_radius(fqn, max_depth=max_depth)
    if fmt == "json":
        console.print_json(json_mod.dumps({
            "fqn": fqn, "max_depth": max_depth,
            "blast_radius": sorted(radius), "count": len(radius),
        }, indent=2))
    else:
        console.print(f"[bold]Blast radius for {fqn}[/bold] (depth={max_depth}, {len(radius)} callers)")
        for caller in sorted(radius):
            console.print(f"  {caller}")
        if not radius:
            console.print("  [dim]No transitive callers found[/dim]")


@manifest_app.command("dead-code")
def manifest_dead_code(
    path: Optional[str] = typer.Argument(None, help="Filter by file path prefix"),
    fmt: str = typer.Option("text", "--format", help="Output format: text or json"),
):
    """List public callables with zero inbound call edges (dead code candidates)."""
    import json as json_mod
    from rich.console import Console
    from startd8.utils.manifest_registry import ManifestRegistry

    console = Console()
    project_root = Path.cwd()

    registry = ManifestRegistry.from_cache(project_root)
    if registry is None:
        console.print("[red]No manifest cache found. Run 'manifest generate --mode bytecode' first.[/red]")
        raise SystemExit(1)

    candidates = registry.dead_candidates()
    if path:
        # Filter by file path prefix
        filtered = []
        for fqn in candidates:
            result = registry.resolve_fqn(fqn)
            if result and result[0].startswith(path):
                filtered.append(fqn)
        candidates = filtered

    if fmt == "json":
        console.print_json(json_mod.dumps({
            "dead_candidates": candidates, "count": len(candidates),
        }, indent=2))
    else:
        console.print(f"[bold]Dead code candidates[/bold] ({len(candidates)} total)")
        for fqn in candidates:
            console.print(f"  {fqn}")
        if not candidates:
            console.print("  [dim]No dead code candidates found[/dim]")


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
dashboard_app = typer.Typer(
    name="dashboard",
    help="Dashboard management commands"
)
app.add_typer(dashboard_app, name="dashboard")


_DASHBOARD_TEMPLATE = """\
# Dashboard spec template — see docs/design/dashboard-creator/ for full reference
title: "My Dashboard"
description: "What this dashboard monitors"
tags:
  - startd8
  - observability
panels:
  - type: stat
    title: "Request Rate"
    expr: 'rate(http_requests_total{job="my-service"}[5m])'
    unit: reqps
  - type: timeseries
    title: "Latency"
    targets:
      - expr: 'histogram_quantile(0.99, rate(http_request_duration_seconds_bucket[5m]))'
        legendFormat: "p99"
      - expr: 'histogram_quantile(0.50, rate(http_request_duration_seconds_bucket[5m]))'
        legendFormat: "p50"
    unit: s
variables:
  - type: prometheusDatasource
    name: datasource
    label: "Data Source"
"""


def _print_dashboard_template() -> None:
    """Print a YAML dashboard spec skeleton to stdout."""
    console.print(_DASHBOARD_TEMPLATE)


@dashboard_app.command("create")
def dashboard_create(
    spec_file: Optional[Path] = typer.Argument(
        None, help="Path to dashboard spec YAML/JSON file"
    ),
    provision: bool = typer.Option(
        False, "--provision", help="Push dashboard to Grafana after generation"
    ),
    grafana_url: Optional[str] = typer.Option(
        None, "--grafana-url", help="Grafana instance URL"
    ),
    allow_insecure: bool = typer.Option(
        False, "--allow-insecure", help="Allow plain HTTP connections to Grafana"
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Generate Jsonnet without writing files"
    ),
    check: bool = typer.Option(
        False, "--check", help="Validate and compile only, no write"
    ),
    persist_source: bool = typer.Option(
        False, "--persist-source", help="Write .libsonnet to mixin dir"
    ),
    output_dir: Optional[Path] = typer.Option(
        None, "--output-dir", help="Override output directory"
    ),
    config: Optional[Path] = typer.Option(
        None, "--config", help="Path to config overrides YAML"
    ),
    print_template: bool = typer.Option(
        False, "--print-template", help="Print a YAML spec template and exit"
    ),
    verbose: bool = typer.Option(False, "--verbose", help="Verbose output"),
):
    """Generate a Grafana dashboard from a declarative YAML/JSON spec.

    Examples:

        startd8 dashboard create my-spec.yaml

        startd8 dashboard create my-spec.yaml --provision --grafana-url https://grafana.local

        startd8 dashboard create --print-template > my-spec.yaml
    """
    if print_template:
        _print_dashboard_template()
        return

    if spec_file is None:
        console.print("[red]Error: spec_file argument is required (or use --print-template)[/red]")
        raise typer.Exit(1)

    if not spec_file.is_file():
        console.print(f"[red]Error: spec file not found: {spec_file}[/red]")
        raise typer.Exit(1)

    # Lazy import to avoid circular / heavy imports at CLI startup
    from .dashboard_creator.workflow import DashboardCreatorWorkflow

    workflow = DashboardCreatorWorkflow()

    wf_config: dict = {
        "spec": str(spec_file),
        "dry_run": dry_run,
        "check": check,
        "persist_source": persist_source,
    }
    if output_dir:
        wf_config["output_dir"] = str(output_dir)
    if provision:
        wf_config["provision"] = True
    if grafana_url:
        wf_config["grafana_url"] = grafana_url
    if allow_insecure:
        wf_config["allow_insecure"] = True

    if verbose:
        def _on_progress(current, total, message):
            console.print(f"  [{current}/{total}] {message}")
    else:
        _on_progress = None

    result = workflow.run(wf_config, on_progress=_on_progress)

    if not result.success:
        console.print(f"[red]Dashboard creation failed: {result.error}[/red]")
        raise typer.Exit(1)

    output = result.output or {}
    uid = output.get("uid", "unknown")
    panel_count = output.get("panel_count")

    if dry_run:
        console.print(f"[green]Dry run complete — UID: {uid}[/green]")
    elif check:
        console.print(f"[green]Check passed — UID: {uid}[/green]")
    else:
        json_path = output.get("json_path", "")
        console.print(f"[green]Dashboard created — UID: {uid}[/green]")
        if json_path:
            console.print(f"  Output: {json_path}")
        if panel_count is not None:
            console.print(f"  Panels: {panel_count}")

    dashboard_url = output.get("dashboard_url")
    if dashboard_url:
        console.print(f"  URL: [link={dashboard_url}]{dashboard_url}[/link]")


@dashboard_app.command("from-requirements")
def dashboard_from_requirements(
    path: Path = typer.Argument(..., help="Path to requirements markdown file"),
    output: Optional[Path] = typer.Option(
        None, "--output", "-o", help="Output YAML file path"
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Print YAML to stdout without writing"
    ),
    no_uid_transform: bool = typer.Option(
        False, "--no-uid-transform", help="Keep original UID without cc-govbudget- prefix"
    ),
):
    """Parse a requirements markdown document into a DashboardSpec YAML.

    Examples:

        startd8 dashboard from-requirements design/intro-requirements.md --dry-run

        startd8 dashboard from-requirements design/intro-requirements.md -o dashboards/intro.spec.yaml
    """
    if not path.is_file():
        console.print(f"[red]Error: file not found: {path}[/red]")
        raise typer.Exit(1)

    from .dashboard_creator.requirements_parser import (
        parse_requirements,
        _spec_to_dict,
    )

    spec = parse_requirements(path)

    if no_uid_transform and spec.uid:
        # Restore original UID from the requirements doc header
        import re as _re

        header_text = path.read_text(encoding="utf-8")
        uid_m = _re.search(r"\*\*Dashboard UID\*\*:\s*`([^`]+)`", header_text)
        if uid_m:
            spec = spec.model_copy(update={"uid": uid_m.group(1).strip()})

    import yaml as _yaml

    data = _spec_to_dict(spec)
    yaml_str = _yaml.dump(data, default_flow_style=False, allow_unicode=True, sort_keys=False)

    panel_count = len(spec.panels)
    var_count = len(spec.variables)

    if dry_run:
        console.print(yaml_str)
        console.print(
            f"\n[green]Parsed: {panel_count} panels, {var_count} variables "
            f"— UID: {spec.uid}[/green]"
        )
        return

    out_path = output or path.with_suffix(".spec.yaml")
    out_path.write_text(yaml_str, encoding="utf-8")
    console.print(
        f"[green]Wrote {out_path} — {panel_count} panels, {var_count} variables "
        f"— UID: {spec.uid}[/green]"
    )


@dashboard_app.command("delete")
def dashboard_delete(
    uid: str = typer.Argument(..., help="Dashboard UID to delete"),
    grafana_url: Optional[str] = typer.Option(
        None, "--grafana-url", help="Grafana instance URL"
    ),
    allow_insecure: bool = typer.Option(
        False, "--allow-insecure", help="Allow plain HTTP connections"
    ),
    remove_source: bool = typer.Option(
        False, "--remove-source", help="Also delete .libsonnet source file"
    ),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
):
    """Delete a dashboard from Grafana and/or local files.

    Examples:

        startd8 dashboard delete cc-startd8-my-dashboard

        startd8 dashboard delete cc-startd8-my-dashboard --grafana-url https://grafana.local --yes
    """
    if not yes:
        confirm = typer.confirm(f"Delete dashboard '{uid}'?")
        if not confirm:
            console.print("[yellow]Aborted.[/yellow]")
            raise typer.Exit(0)

    # Best-effort Grafana deletion
    if grafana_url:
        try:
            from .dashboard_creator.grafana_client import GrafanaClient
            from .dashboard_creator.provisioning import deprovision_dashboard

            client = GrafanaClient(grafana_url, allow_insecure=allow_insecure)
            result = deprovision_dashboard(uid, client)
            if result.success:
                console.print(f"[green]Deleted from Grafana: {uid}[/green]")
            else:
                console.print(
                    f"[yellow]Warning: Grafana deletion failed: {result.error}[/yellow]"
                )
        except (ConfigurationError, OSError) as exc:
            console.print(
                f"[yellow]Warning: Could not connect to Grafana: {exc}[/yellow]"
            )

    # Local cleanup always proceeds
    from .dashboard_creator.provisioning import delete_local_artifacts

    artifacts = delete_local_artifacts(uid, remove_source=remove_source)

    deleted_items = [name for name, ok in artifacts.items() if ok]
    if deleted_items:
        console.print(f"[green]Deleted local artifacts: {', '.join(deleted_items)}[/green]")
    else:
        console.print("[dim]No local artifacts found to delete.[/dim]")


if __name__ == "__main__":
    app()

