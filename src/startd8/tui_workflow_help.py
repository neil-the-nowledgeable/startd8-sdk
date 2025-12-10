"""
Workflow Help System for startd8 TUI.

This module provides workflow-specific help functionality including:
- Workflow intro panels with descriptions
- Step-by-step guidance during workflows
- Real-world workflow examples

Module Constants:
    HAS_YAML: bool - Whether PyYAML is available
    HAS_QUESTIONARY: bool - Whether questionary is available

Example:
    >>> from startd8.tui_workflow_help import WorkflowHelper
    >>> helper = WorkflowHelper()
    >>> helper.show_workflow_intro("iterative_workflow")
"""

import logging
from pathlib import Path
from typing import Dict, List, Optional, Any, Final
from dataclasses import dataclass, field

try:
    import yaml
    from yaml import YAMLError
    HAS_YAML = True
except ImportError:
    HAS_YAML = False
    YAMLError = Exception  # Fallback for type checking

try:
    import questionary
    HAS_QUESTIONARY = True
except ImportError:
    HAS_QUESTIONARY = False

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

# Module logger
logger = logging.getLogger(__name__)

# Constants
BACK_OPTION: Final[str] = "← Back"
CONFIG_ENCODING: Final[str] = "utf-8"
MAX_CONTENT_LENGTH: Final[int] = 50000
MAX_EXAMPLES_PER_WORKFLOW: Final[int] = 20

__all__ = [
    "WorkflowHelper",
    "WorkflowHelp",
    "WorkflowExample",
    "HAS_YAML",
    "HAS_QUESTIONARY",
]


def _sanitize_content(text: Optional[str], max_length: int = MAX_CONTENT_LENGTH) -> str:
    """
    Sanitize text for safe display.
    
    Args:
        text: Text to sanitize (may be None)
        max_length: Maximum allowed length
        
    Returns:
        Sanitized text safe for display
    """
    if not text:
        return ""
    if len(text) > max_length:
        text = text[:max_length] + "... [truncated]"
    return text


@dataclass
class WorkflowHelp:
    """
    Represents help for a workflow.
    
    Attributes:
        key: Unique identifier for the workflow
        title: Display title
        icon: Emoji icon
        description: Brief description
        what_it_does: Explanation of workflow purpose
        how_it_works: Step-by-step explanation
        use_cases: When to use this workflow
        requirements: Prerequisites
        tips: Helpful tips
        steps: Number of steps in workflow
        step_names: Names for each step
    """
    key: str
    title: str
    icon: str
    description: str
    what_it_does: str
    how_it_works: str
    use_cases: str
    requirements: str
    tips: str
    steps: int
    step_names: List[str] = field(default_factory=list)


@dataclass
class WorkflowExample:
    """
    Represents an example for a workflow.
    
    Attributes:
        workflow_key: Key of the parent workflow
        title: Example title
        task: Example task description
        why: Why this example is useful
        use_case: When to use this example
        agents: Optional agent recommendations
    """
    workflow_key: str
    title: str
    task: str
    why: str
    use_case: str
    agents: Optional[str] = None


class WorkflowHelper:
    """
    Manages workflow-specific help, intro panels, and examples.
    Extends the base HelpSystem with workflow-specific features.
    """

    def __init__(self, console: Console = None, config_dir: str = None):
        """
        Initialize the WorkflowHelper.
        
        Args:
            console: Rich console for output
            config_dir: Directory containing help YAML files
        """
        self.console = console or Console()
        
        # Determine config directory
        if config_dir is None:
            config_dir = Path(__file__).parent / "help_content"
        else:
            config_dir = Path(config_dir)
        
        self.config_dir = config_dir
        self.workflows: Dict[str, WorkflowHelp] = {}
        self.examples: Dict[str, List[WorkflowExample]] = {}
        
        # Load configurations
        self._load_workflow_help()
        self._load_examples()

    def _load_workflow_help(self) -> None:
        """
        Load workflow help from YAML file with proper error handling.
        
        Handles the following error cases gracefully:
        - Missing PyYAML library
        - Missing configuration file
        - Permission errors
        - Invalid YAML syntax
        - Invalid configuration structure
        """
        if not HAS_YAML:
            logger.warning("PyYAML not installed. Workflow help unavailable.")
            return
        
        config_file = self.config_dir / "workflow_help.yaml"
        
        if not config_file.exists():
            logger.warning(f"Workflow help config not found: {config_file}")
            return
        
        try:
            with open(config_file, "r", encoding=CONFIG_ENCODING) as f:
                data = yaml.safe_load(f)
        except PermissionError:
            logger.error(f"Permission denied reading: {config_file}")
            return
        except YAMLError as e:
            logger.error(f"Invalid YAML syntax in {config_file}: {e}")
            return
        except OSError as e:
            logger.error(f"Error reading {config_file}: {e}")
            return
        
        # Validate data structure
        if not isinstance(data, dict):
            logger.error(f"Invalid config format in {config_file}: expected dict")
            return
        
        workflows_data = data.get("workflows")
        if not isinstance(workflows_data, dict):
            logger.warning("No valid workflows found in configuration")
            return
        
        # Load workflows with validation
        for key, workflow_data in workflows_data.items():
            if not isinstance(workflow_data, dict):
                logger.warning(f"Skipping invalid workflow: {key}")
                continue
            
            try:
                step_names = workflow_data.get("step_names", [])
                if not isinstance(step_names, list):
                    step_names = []
                
                workflow = WorkflowHelp(
                    key=str(key),
                    title=_sanitize_content(workflow_data.get("title", "")),
                    icon=str(workflow_data.get("icon", ""))[:10],
                    description=_sanitize_content(workflow_data.get("description", "")),
                    what_it_does=_sanitize_content(workflow_data.get("what_it_does", "")),
                    how_it_works=_sanitize_content(workflow_data.get("how_it_works", "")),
                    use_cases=_sanitize_content(workflow_data.get("use_cases", "")),
                    requirements=_sanitize_content(workflow_data.get("requirements", "")),
                    tips=_sanitize_content(workflow_data.get("tips", "")),
                    steps=int(workflow_data.get("steps", 0)),
                    step_names=[str(s) for s in step_names]
                )
                self.workflows[key] = workflow
            except (TypeError, ValueError) as e:
                logger.warning(f"Error loading workflow {key}: {e}")
                continue

    def _load_examples(self) -> None:
        """
        Load workflow examples from YAML file with proper error handling.
        
        Note: This reloads the same file as _load_workflow_help to get examples.
        In production, consider caching the loaded data to avoid double I/O.
        """
        if not HAS_YAML:
            return
        
        config_file = self.config_dir / "workflow_help.yaml"
        
        if not config_file.exists():
            return
        
        try:
            with open(config_file, "r", encoding=CONFIG_ENCODING) as f:
                data = yaml.safe_load(f)
        except (PermissionError, YAMLError, OSError) as e:
            logger.error(f"Error loading examples from {config_file}: {e}")
            return
        
        if not isinstance(data, dict):
            return
        
        examples_data = data.get("examples")
        if not isinstance(examples_data, dict):
            return
        
        # Load examples with validation and limits
        for workflow_key, examples_list in examples_data.items():
            if not isinstance(examples_list, list):
                logger.warning(f"Skipping invalid examples for: {workflow_key}")
                continue
            
            self.examples[workflow_key] = []
            
            # Limit examples per workflow to prevent memory issues
            for example_data in examples_list[:MAX_EXAMPLES_PER_WORKFLOW]:
                if not isinstance(example_data, dict):
                    continue
                
                try:
                    example = WorkflowExample(
                        workflow_key=str(workflow_key),
                        title=_sanitize_content(example_data.get("title", "")),
                        task=_sanitize_content(example_data.get("task", "")),
                        why=_sanitize_content(example_data.get("why", "")),
                        use_case=_sanitize_content(example_data.get("use_case", "")),
                        agents=_sanitize_content(example_data.get("agents"))
                    )
                    self.examples[workflow_key].append(example)
                except (TypeError, ValueError) as e:
                    logger.warning(f"Error loading example for {workflow_key}: {e}")
                    continue

    def show_workflow_intro(self, workflow_key: str) -> None:
        """
        Display intro panel for a workflow.
        
        Args:
            workflow_key: Key of the workflow (e.g., 'iterative_workflow')
        """
        if workflow_key not in self.workflows:
            self.console.print(
                f"[yellow]No intro available for this workflow.[/yellow]"
            )
            return
        
        workflow = self.workflows[workflow_key]
        
        # Build intro panel content
        content = f"""[bold cyan]{workflow.title}[/bold cyan]

[bold]What it does:[/bold]
{workflow.what_it_does}

[bold]How it works:[/bold]
{workflow.how_it_works}

[bold]Use Cases:[/bold]
{workflow.use_cases}

[bold]Requirements:[/bold]
{workflow.requirements}

[bold]Tips:[/bold]
{workflow.tips}"""
        
        # Display in panel
        self.console.print(Panel(
            content,
            title=f"{workflow.icon} {workflow.title}",
            border_style="cyan",
            padding=(1, 2)
        ))
        
        # Wait for user to continue
        if HAS_QUESTIONARY:
            questionary.press_any_key_to_continue("\nPress any key to continue...").ask()
        else:
            input("\nPress Enter to continue...")

    def show_step_guidance(self, workflow_key: str, step: int, step_description: str) -> None:
        """
        Display step-by-step guidance for a workflow step.
        
        Args:
            workflow_key: Key of the workflow
            step: Step number (1-indexed)
            step_description: Description of what this step does
        """
        if workflow_key not in self.workflows:
            return
        
        workflow = self.workflows[workflow_key]
        
        if step < 1 or step > workflow.steps:
            return
        
        # Get step name
        step_name = workflow.step_names[step - 1] if step <= len(workflow.step_names) else f"Step {step}"
        
        # Display step guidance
        self.console.print(f"\n[bold cyan]Step {step} of {workflow.steps}: {step_name}[/bold cyan]")
        self.console.print(f"[dim]{step_description}[/dim]\n")

    def show_workflow_examples(self, workflow_key: str) -> None:
        """
        Display examples for a workflow.
        
        Args:
            workflow_key: Key of the workflow
        """
        if workflow_key not in self.examples:
            self.console.print(
                f"[yellow]No examples available for this workflow.[/yellow]"
            )
            return
        
        examples_list = self.examples[workflow_key]
        if not examples_list:
            self.console.print(
                f"[yellow]No examples available for this workflow.[/yellow]"
            )
            return
        
        # Build examples table
        table = Table(title=f"Workflow Examples", show_header=True)
        table.add_column("Example", style="bold cyan")
        table.add_column("Description", style="dim")
        table.add_column("Use Case", style="green")
        
        for example in examples_list:
            table.add_row(
                example.title,
                example.task[:40] + "..." if len(example.task) > 40 else example.task,
                example.use_case
            )
        
        self.console.print(Panel(table, title="📚 Examples", border_style="cyan", padding=(1, 2)))
        
        # Let user view details
        if HAS_QUESTIONARY:
            show_details = questionary.confirm(
                "View example details?",
                default=False
            ).ask()
            
            if show_details:
                self._show_example_details(workflow_key, examples_list)

    def _show_example_details(self, workflow_key: str, examples_list: List[WorkflowExample]) -> None:
        """Show detailed view of examples."""
        while True:
            example_titles = [f"{ex.title}" for ex in examples_list]
            example_titles.append(BACK_OPTION)
            
            selected = questionary.select(
                "Select an example to view details:",
                choices=example_titles,
                use_shortcuts=False
            ).ask()
            
            if not selected or BACK_OPTION in selected:
                break
            
            # Find selected example
            for example in examples_list:
                if example.title == selected:
                    content = f"""[bold]{example.title}[/bold]

[bold]Task:[/bold]
{example.task}

[bold]Use Case:[/bold]
{example.use_case}

[bold]Why This Example:[/bold]
{example.why}"""
                    
                    if example.agents:
                        content += f"\n\n[bold]Agents:[/bold]\n{example.agents}"
                    
                    self.console.print(Panel(
                        content,
                        title="📖 Example Details",
                        border_style="cyan",
                        padding=(1, 2)
                    ))
                    
                    if HAS_QUESTIONARY:
                        questionary.press_any_key_to_continue("\nPress any key to continue...").ask()
                    break

    def get_workflow_list(self) -> List[str]:
        """
        Get list of all available workflows.
        
        Returns:
            List of workflow keys
        """
        return list(self.workflows.keys())

    def has_workflow_help(self, workflow_key: str) -> bool:
        """
        Check if help is available for a workflow.
        
        Args:
            workflow_key: Key of the workflow
        
        Returns:
            True if help is available
        """
        return workflow_key in self.workflows

    def has_examples(self, workflow_key: str) -> bool:
        """
        Check if examples are available for a workflow.
        
        Args:
            workflow_key: Key of the workflow
        
        Returns:
            True if examples are available
        """
        return workflow_key in self.examples and len(self.examples[workflow_key]) > 0

    def validate_configuration(self) -> Dict[str, Any]:
        """
        Validate workflow help configuration.
        
        Returns:
            Dictionary with validation results
        """
        return {
            "workflows_loaded": len(self.workflows) > 0,
            "examples_loaded": len(self.examples) > 0,
            "workflows_count": len(self.workflows),
            "examples_count": sum(len(ex) for ex in self.examples.values()),
            "yaml_available": HAS_YAML,
            "questionary_available": HAS_QUESTIONARY,
            "config_directory": str(self.config_dir),
            "config_directory_exists": self.config_dir.exists()
        }
