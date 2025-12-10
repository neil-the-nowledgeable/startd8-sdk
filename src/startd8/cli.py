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
from .agents import ClaudeAgent, GPT4Agent, MockAgent
from .benchmark import BenchmarkRunner, ComparisonReport

app = typer.Typer(
    name="startd8",
    help="StartDate (startd8) Agent Framework CLI - Multi-LLM benchmarking and development tools"
)
console = Console()

# Global framework instance
_framework: Optional[AgentFramework] = None


def get_framework(storage_dir: Optional[Path] = None) -> AgentFramework:
    """Get or create framework instance"""
    global _framework
    if _framework is None:
        _framework = AgentFramework(storage_dir)
    return _framework


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
        ["mock"],
        "--agent", "-a",
        help="Agents to test (mock, claude, gpt4)"
    ),
    storage_dir: Optional[Path] = typer.Option(None, "--dir", "-d", help="Storage directory")
):
    """Run a benchmark across multiple agents"""
    framework = get_framework(storage_dir)
    prompt = framework.get_prompt(prompt_id)
    
    if not prompt:
        console.print(f"❌ Prompt {prompt_id} not found", style="red")
        raise typer.Exit(1)
    
    # Initialize agents
    agent_instances = []
    for agent_name in agents:
        if agent_name.lower() == "mock":
            agent_instances.append(MockAgent())
        elif agent_name.lower() == "claude":
            try:
                agent_instances.append(ClaudeAgent())
            except Exception as e:
                console.print(f"⚠️  Failed to initialize Claude agent: {e}", style="yellow")
        elif agent_name.lower() == "gpt4":
            try:
                agent_instances.append(GPT4Agent())
            except Exception as e:
                console.print(f"⚠️  Failed to initialize GPT-4 agent: {e}", style="yellow")
        else:
            console.print(f"⚠️  Unknown agent: {agent_name}", style="yellow")
    
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
        raise typer.Exit(1)
    
    console.print(Panel(
        f"[bold]ID:[/bold] {response.id}\n"
        f"[bold]Agent:[/bold] {response.agent_name}\n"
        f"[bold]Model:[/bold] {response.model}\n"
        f"[bold]Response Time:[/bold] {response.response_time_ms}ms\n"
        f"[bold]Tokens:[/bold] {response.token_usage.total if response.token_usage else 'N/A'}\n"
        f"[bold]Cost:[/bold] ${response.token_usage.cost_estimate:.4f}" if response.token_usage else "" + "\n"
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
    classic: bool = typer.Option(False, "--classic", help="Use classic TUI instead of improved")
):
    """Launch interactive TUI mode (improved by default)"""
    try:
        if classic:
            from .tui import run_tui
            run_tui(storage_dir)
        else:
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
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Output file"),
    storage_dir: Optional[Path] = typer.Option(None, "--dir", "-d", help="Storage directory")
):
    """Run a sequential pipeline workflow"""
    from .orchestration import WorkflowTemplates, Pipeline
    from .agents import MockAgent
    
    framework = get_framework(storage_dir)
    
    console.print(f"🔗 Running {workflow} pipeline...\n", style="cyan")
    
    # Create pipeline with mock agents (real agents require API keys)
    if workflow == "planner-implementer":
        pipe = WorkflowTemplates.planner_implementer(
            MockAgent(name="planner", model="mock-planner"),
            MockAgent(name="implementer", model="mock-implementer")
        )
    elif workflow == "code-review":
        pipe = WorkflowTemplates.code_review(
            MockAgent(name="reviewer", model="mock-reviewer"),
            MockAgent(name="improver", model="mock-improver")
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
    base = storage_dir or Path.home() / ".startd8"
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
    
    def on_job_complete(job, result):
        status_color = "green" if result.status == JobStatus.COMPLETED else "red"
        console.print(f"[{status_color}]✓ Completed job {job.job_id}[/{status_color}]")
    
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


if __name__ == "__main__":
    app()

