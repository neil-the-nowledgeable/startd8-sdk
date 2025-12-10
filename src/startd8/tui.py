"""
Interactive Terminal UI for startd8

Provides a questionary-based interactive interface for
both benchmarking and orchestration workflows.
"""

import sys
from typing import Optional, List
from pathlib import Path

try:
    import questionary
    from questionary import Style
    HAS_QUESTIONARY = True
except ImportError:
    HAS_QUESTIONARY = False
    questionary = None

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import print as rprint

from .framework import AgentFramework
from .agents import MockAgent, ClaudeAgent, GPT4Agent
from .orchestration import Pipeline, WorkflowTemplates, PipelineResult


console = Console()


# Custom style for TUI
custom_style = Style([
    ('qmark', 'fg:#5f87ff bold'),
    ('question', 'bold'),
    ('answer', 'fg:#5fff87 bold'),
    ('pointer', 'fg:#5fff87 bold'),
    ('highlighted', 'fg:#5fff87 bold'),
    ('selected', 'fg:#5fff87'),
    ('separator', 'fg:#555555'),
    ('instruction', 'fg:#888888'),
]) if HAS_QUESTIONARY else None


def hr(char="─", width=80):
    """Horizontal rule"""
    return char * width


def format_result(title: str, content: str) -> str:
    """Format a result block"""
    return Panel(
        content,
        title=title,
        border_style="cyan",
        padding=(1, 2)
    )


class InteractiveTUI:
    """Interactive TUI for startd8"""
    
    def __init__(self, storage_dir: Optional[Path] = None):
        """
        Initialize TUI
        
        Args:
            storage_dir: Storage directory for data
        """
        if not HAS_QUESTIONARY:
            console.print(
                "[red]Error: questionary not installed.[/red]\n"
                "Install with: pip install questionary",
                style="red"
            )
            sys.exit(1)
        
        self.framework = AgentFramework(storage_dir)
        self.console = console
    
    def show_header(self):
        """Show TUI header"""
        self.console.clear()
        self.console.print(hr("="), style="cyan")
        self.console.print(
            "  startd8 Interactive Mode  ".center(80),
            style="bold cyan"
        )
        self.console.print(hr("="), style="cyan")
        self.console.print()
    
    def main_menu(self) -> str:
        """Show main menu"""
        return questionary.select(
            "What would you like to do?",
            choices=[
                "🔗 Run Pipeline (Orchestration)",
                "📊 Benchmark Models",
                "📝 Create Prompt",
                "📋 List Prompts",
                "🔍 Compare Responses",
                "📈 View Statistics",
                "❌ Exit"
            ],
            style=custom_style
        ).ask()
    
    def orchestration_mode(self):
        """Orchestration workflow"""
        self.console.print("\n[bold cyan]Pipeline Orchestration[/bold cyan]\n")
        
        # Choose workflow template
        workflow = questionary.select(
            "Select workflow template:",
            choices=[
                "Planner → Implementer",
                "Code Review → Improvement",
                "Custom Sequential Workflow",
                "← Back"
            ],
            style=custom_style
        ).ask()
        
        if workflow == "← Back":
            return
        
        # Get user input
        user_input = questionary.text(
            "Enter your request:",
            style=custom_style
        ).ask()
        
        if not user_input:
            return
        
        # Choose agents
        self.console.print("\n[cyan]Selecting agents...[/cyan]")
        
        agent_choice = questionary.select(
            "Which agents to use?",
            choices=[
                "Mock (fast, for testing)",
                "Claude + GPT-4 (real models)",
                "← Back"
            ],
            style=custom_style
        ).ask()
        
        if agent_choice == "← Back":
            return
        
        # Create pipeline based on selection
        if workflow == "Planner → Implementer":
            if "Mock" in agent_choice:
                pipeline = WorkflowTemplates.planner_implementer(
                    MockAgent(name="planner", model="mock-planner"),
                    MockAgent(name="implementer", model="mock-implementer")
                )
            else:
                try:
                    pipeline = WorkflowTemplates.planner_implementer(
                        ClaudeAgent(name="planner"),
                        GPT4Agent(name="implementer")
                    )
                except Exception as e:
                    self.console.print(f"\n[red]Error initializing agents: {e}[/red]")
                    self.console.print("[yellow]Falling back to mock agents[/yellow]\n")
                    pipeline = WorkflowTemplates.planner_implementer(
                        MockAgent(name="planner", model="mock-planner"),
                        MockAgent(name="implementer", model="mock-implementer")
                    )
        
        elif workflow == "Code Review → Improvement":
            if "Mock" in agent_choice:
                pipeline = WorkflowTemplates.code_review(
                    MockAgent(name="reviewer", model="mock-reviewer"),
                    MockAgent(name="improver", model="mock-improver")
                )
            else:
                try:
                    pipeline = WorkflowTemplates.code_review(
                        ClaudeAgent(name="reviewer"),
                        GPT4Agent(name="improver")
                    )
                except Exception as e:
                    self.console.print(f"\n[red]Error: {e}[/red]")
                    return
        
        else:
            self.console.print("[yellow]Custom workflows not yet implemented[/yellow]")
            return
        
        # Run pipeline
        pipeline.framework = self.framework
        self.console.print("\n[cyan]Running pipeline...[/cyan]\n")
        
        with self.console.status("[bold cyan]Processing..."):
            result = pipeline.run(user_input)
        
        # Display results
        self.console.print()
        
        for step in result.steps:
            self.console.print(format_result(
                f"Step {step['step_number']}: {step['step_name']} ({step['agent']})",
                step['output']
            ))
        
        # Show metrics
        self.console.print()
        metrics_table = Table(title="Pipeline Metrics", show_header=False)
        metrics_table.add_row("Total Time", f"{result.total_time_ms}ms")
        metrics_table.add_row("Total Tokens", str(result.total_tokens))
        metrics_table.add_row("Total Cost", f"${result.total_cost:.4f}")
        self.console.print(metrics_table)
        
        # Save option
        save = questionary.confirm(
            "\nSave to file?",
            default=False,
            style=custom_style
        ).ask()
        
        if save:
            filename = questionary.text(
                "Filename (e.g., output.md):",
                default="pipeline_output.md",
                style=custom_style
            ).ask()
            
            if filename:
                self._save_pipeline_result(result, filename)
                self.console.print(f"\n[green]✓ Saved to {filename}[/green]")
        
        questionary.press_any_key_to_continue("Press any key to continue...").ask()
    
    def benchmark_mode(self):
        """Benchmarking workflow"""
        self.console.print("\n[bold cyan]Model Benchmarking[/bold cyan]\n")
        
        # Get prompt
        prompt_text = questionary.text(
            "Enter prompt to benchmark:",
            style=custom_style
        ).ask()
        
        if not prompt_text:
            return
        
        # Create prompt
        prompt = self.framework.create_prompt(
            content=prompt_text,
            version="1.0.0",
            tags=["benchmark", "tui"]
        )
        
        self.console.print(f"\n[green]✓ Created prompt: {prompt.id}[/green]\n")
        
        # Select agents
        agents_choice = questionary.checkbox(
            "Select agents to benchmark:",
            choices=[
                "Mock Agent 1",
                "Mock Agent 2",
                "Mock Agent 3"
            ],
            style=custom_style
        ).ask()
        
        if not agents_choice:
            return
        
        # Run benchmark
        self.console.print("\n[cyan]Running benchmark...[/cyan]\n")
        
        agents = [
            MockAgent(name=choice.lower().replace(" ", "-"), model=choice)
            for choice in agents_choice
        ]
        
        for agent in agents:
            with self.console.status(f"[cyan]Testing {agent.name}..."):
                response = agent.create_response(prompt.id, prompt_text)
                self.framework.storage.save_response(response)
        
        # Show comparison
        comparison = self.framework.compare_responses(prompt.id)
        
        self.console.print()
        table = Table(title="Benchmark Results")
        table.add_column("Agent", style="cyan")
        table.add_column("Time (ms)", justify="right", style="green")
        table.add_column("Tokens", justify="right", style="blue")
        
        for resp in comparison['responses']:
            table.add_row(
                resp['agent'],
                str(resp['response_time_ms']),
                str(resp['tokens']) if resp['tokens'] else "-"
            )
        
        self.console.print(table)
        questionary.press_any_key_to_continue("\nPress any key to continue...").ask()
    
    def _save_pipeline_result(self, result: PipelineResult, filename: str):
        """Save pipeline result to markdown file"""
        lines = [
            "# Pipeline Result",
            "",
            f"**Pipeline ID**: {result.pipeline_id}",
            f"**Timestamp**: {result.timestamp.isoformat()}",
            f"**Total Time**: {result.total_time_ms}ms",
            f"**Total Tokens**: {result.total_tokens}",
            f"**Total Cost**: ${result.total_cost:.4f}",
            "",
            "---",
            ""
        ]
        
        for step in result.steps:
            lines.extend([
                f"## Step {step['step_number']}: {step['step_name']}",
                "",
                f"**Agent**: {step['agent']} ({step['model']})",
                f"**Time**: {step['response_time_ms']}ms",
                f"**Tokens**: {step['tokens']}",
                f"**Cost**: ${step['cost']:.4f}",
                "",
                "### Output",
                "",
                step['output'],
                "",
                "---",
                ""
            ])
        
        with open(filename, 'w') as f:
            f.write('\n'.join(lines))
    
    def run(self):
        """Run the TUI"""
        while True:
            self.show_header()
            choice = self.main_menu()
            
            if not choice or choice == "❌ Exit":
                self.console.print("\n[cyan]Goodbye![/cyan]\n")
                break
            
            if "Pipeline" in choice:
                self.orchestration_mode()
            elif "Benchmark" in choice:
                self.benchmark_mode()
            elif "Statistics" in choice:
                self._show_stats()
            else:
                self.console.print("\n[yellow]Feature coming soon![/yellow]\n")
                questionary.press_any_key_to_continue("Press any key...").ask()
    
    def _show_stats(self):
        """Show statistics"""
        prompts = self.framework.list_prompts()
        responses = self.framework.list_responses()
        
        self.console.print()
        stats_panel = Panel(
            f"**Prompts**: {len(prompts)}\n"
            f"**Responses**: {len(responses)}\n"
            f"**Total Tokens**: {sum(r.token_usage.total if r.token_usage else 0 for r in responses):,}",
            title="📊 Statistics",
            border_style="cyan"
        )
        self.console.print(stats_panel)
        questionary.press_any_key_to_continue("\nPress any key...").ask()


def run_tui(storage_dir: Optional[Path] = None):
    """Launch the interactive TUI"""
    tui = InteractiveTUI(storage_dir)
    tui.run()

