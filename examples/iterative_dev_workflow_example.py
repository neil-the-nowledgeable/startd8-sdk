"""
Example: Iterative Development Workflow

Demonstrates the dev-review-fix loop where a developer agent implements a task,
a reviewer agent checks the code, and if issues are found, the developer fixes them.
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from startd8.providers import ProviderRegistry
from startd8.iterative_workflow import IterativeDevWorkflow, save_workflow_result
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn

console = Console()


def print_iteration_status(iteration):
    """Callback to print status after each iteration"""
    console.print(f"\n[bold cyan]Iteration {iteration.iteration_number} Complete[/bold cyan]")
    
    table = Table(show_header=False, box=None)
    table.add_column("Metric", style="dim")
    table.add_column("Value")
    
    table.add_row("Status", f"[yellow]{iteration.status}[/yellow]")
    table.add_row("Dev Time", f"{iteration.dev_time_ms / 1000:.2f}s")
    table.add_row("Review Time", f"{iteration.review_time_ms / 1000:.2f}s")
    
    if iteration.feedback:
        status_color = "green" if iteration.feedback.passed else "red"
        table.add_row("Review", f"[{status_color}]{'PASSED' if iteration.feedback.passed else 'FAILED'}[/{status_color}]")
        
        if iteration.feedback.score is not None:
            table.add_row("Score", f"{iteration.feedback.score}/100")
        
        if iteration.feedback.issues:
            table.add_row("Issues", f"[red]{len(iteration.feedback.issues)}[/red]")
            for i, issue in enumerate(iteration.feedback.issues[:3], 1):
                table.add_row("", f"  {i}. {issue[:60]}...")
    
    console.print(table)
    console.print()


def example_1_simple_function():
    """Example 1: Implement a simple function with validation"""
    console.print(Panel(
        "[bold cyan]Example 1: Simple Function Implementation[/bold cyan]\n\n"
        "Task: Implement a function to validate email addresses\n"
        "Dev Agent: anthropic:claude-3-5-sonnet-20241022\n"
        "Review Agent: openai:gpt-4-turbo-preview",
        border_style="cyan"
    ))
    
    # Initialize agents
    ProviderRegistry.discover()
    anthropic = ProviderRegistry.get_provider("anthropic")
    openai = ProviderRegistry.get_provider("openai")
    anthropic.validate_config({})
    openai.validate_config({})

    dev_agent = anthropic.create_agent("claude-3-5-sonnet-20241022", name="developer")
    review_agent = openai.create_agent("gpt-4-turbo-preview", name="reviewer")
    
    # Create workflow
    workflow = IterativeDevWorkflow(
        developer_agent=dev_agent,
        reviewer_agent=review_agent,
        max_iterations=3,
        on_iteration_complete=print_iteration_status
    )
    
    # Task description
    task = """
    Implement a Python function called `validate_email(email: str) -> bool` that:
    1. Validates email format using regex
    2. Checks for common issues (missing @, invalid domain, etc.)
    3. Returns True for valid emails, False otherwise
    4. Includes comprehensive docstring
    5. Handles edge cases (None, empty string, whitespace)
    
    Include test cases demonstrating the function works correctly.
    """
    
    # Run workflow
    console.print("\n[bold]Running workflow...[/bold]\n")
    result = workflow.run(task)
    
    # Print results
    print_final_result(result)
    
    # Save result
    output_dir = Path("./workflow_results")
    save_path = save_workflow_result(result, output_dir)
    console.print(f"\n[dim]Result saved to: {save_path}[/dim]")
    
    return result


def example_2_bug_fix():
    """Example 2: Fix a buggy implementation"""
    console.print(Panel(
        "[bold cyan]Example 2: Bug Fix Workflow[/bold cyan]\n\n"
        "Provide buggy code and have the agents fix it",
        border_style="cyan"
    ))
    
    ProviderRegistry.discover()
    anthropic = ProviderRegistry.get_provider("anthropic")
    openai = ProviderRegistry.get_provider("openai")
    anthropic.validate_config({})
    openai.validate_config({})

    dev_agent = anthropic.create_agent("claude-3-5-sonnet-20241022", name="developer")
    review_agent = openai.create_agent("gpt-4-turbo-preview", name="reviewer")
    
    workflow = IterativeDevWorkflow(
        developer_agent=dev_agent,
        reviewer_agent=review_agent,
        max_iterations=5,  # More iterations for bug fixing
        on_iteration_complete=print_iteration_status
    )
    
    task = """
    Fix the bugs in this function:
    
    ```python
    def calculate_average(numbers):
        total = sum(numbers)
        return total / len(numbers)
    ```
    
    Known issues:
    - Doesn't handle empty list
    - Doesn't handle non-numeric values
    - No type hints
    - No docstring
    
    Fix all issues and add comprehensive error handling and tests.
    """
    
    result = workflow.run(task)
    print_final_result(result)
    
    return result


def example_3_mock_agents():
    """Example 3: Using mock agents for testing"""
    console.print(Panel(
        "[bold cyan]Example 3: Mock Agents (No API Keys Required)[/bold cyan]\n\n"
        "Demonstrates workflow with mock agents for testing",
        border_style="cyan"
    ))
    
    # Use mock agents - no API keys required!
    ProviderRegistry.discover()
    mock = ProviderRegistry.get_provider("mock")
    dev_agent = mock.create_agent("mock-model", name="mock-dev")
    review_agent = mock.create_agent("mock-model", name="mock-reviewer")
    
    workflow = IterativeDevWorkflow(
        developer_agent=dev_agent,
        reviewer_agent=review_agent,
        max_iterations=2,
        on_iteration_complete=print_iteration_status
    )
    
    task = "Implement a function to sort a list of numbers"
    
    result = workflow.run(task)
    print_final_result(result)
    
    return result


def example_4_custom_prompts():
    """Example 4: Custom prompt templates"""
    console.print(Panel(
        "[bold cyan]Example 4: Custom Prompt Templates[/bold cyan]\n\n"
        "Use custom prompts for specific coding styles or requirements",
        border_style="cyan"
    ))
    
    # Custom developer prompt emphasizing specific style
    custom_dev_prompt = """You are a Python developer following strict PEP-8 guidelines.

TASK:
{task_description}

REQUIREMENTS:
- Use type hints for all functions
- Include comprehensive docstrings (Google style)
- Add inline comments for complex logic
- Use descriptive variable names
- Maximum line length: 88 characters

{iteration_context}

{feedback_section}

Provide your implementation following these strict guidelines."""

    # Custom review prompt for security focus
    custom_review_prompt = """You are a security-focused code reviewer.

TASK:
{task_description}

IMPLEMENTATION:
{implementation}

Review for:
1. Security vulnerabilities (SQL injection, XSS, etc.)
2. Input validation
3. Error handling and information leakage
4. Authentication and authorization issues
5. Sensitive data handling

Format:
PASS/FAIL: [verdict]
SCORE: [0-100]
ISSUES:
- [Security issues]
SUGGESTIONS:
- [Improvements]
REVIEW:
[Detailed security analysis]"""

    ProviderRegistry.discover()
    anthropic = ProviderRegistry.get_provider("anthropic")
    openai = ProviderRegistry.get_provider("openai")
    anthropic.validate_config({})
    openai.validate_config({})

    dev_agent = anthropic.create_agent("claude-3-5-sonnet-20241022", name="developer")
    review_agent = openai.create_agent("gpt-4-turbo-preview", name="reviewer")
    
    workflow = IterativeDevWorkflow(
        developer_agent=dev_agent,
        reviewer_agent=review_agent,
        max_iterations=3,
        dev_prompt_template=custom_dev_prompt,
        review_prompt_template=custom_review_prompt,
        on_iteration_complete=print_iteration_status
    )
    
    task = """
    Implement a user login function that:
    1. Accepts username and password
    2. Validates against a database
    3. Returns a session token
    4. Handles failed login attempts
    """
    
    result = workflow.run(task, context={
        'framework': 'Flask',
        'database': 'PostgreSQL',
        'auth_method': 'JWT'
    })
    
    print_final_result(result)
    
    return result


def print_final_result(result):
    """Print final workflow results"""
    console.print("\n" + "=" * 70)
    console.print("[bold]Workflow Complete![/bold]")
    console.print("=" * 70 + "\n")
    
    # Status panel
    status_color = "green" if result.successful else "yellow" if result.status == "completed_max_iterations" else "red"
    status_text = "✓ SUCCESS" if result.successful else "⚠ MAX ITERATIONS" if result.status == "completed_max_iterations" else "✗ FAILED"
    
    console.print(Panel(
        f"[bold {status_color}]{status_text}[/bold {status_color}]",
        border_style=status_color
    ))
    
    # Summary table
    table = Table(title="Workflow Summary", show_header=True)
    table.add_column("Metric", style="cyan")
    table.add_column("Value", justify="right")
    
    table.add_row("Total Iterations", str(result.total_iterations))
    table.add_row("Total Time", f"{result.total_time_ms / 1000:.2f}s")
    table.add_row("Total Tokens", f"{result.total_dev_tokens + result.total_review_tokens:,}")
    table.add_row("Estimated Cost", f"${result.total_cost:.4f}")
    table.add_row("Status", result.status)
    
    console.print(table)
    console.print()
    
    # Final review
    if result.final_review:
        console.print("[bold]Final Review:[/bold]")
        review_panel = Panel(
            f"[bold]Score:[/bold] {result.final_review.score}/100\n\n"
            f"[bold]Passed:[/bold] {'✓ Yes' if result.final_review.passed else '✗ No'}\n\n"
            f"[bold]Issues:[/bold] {len(result.final_review.issues)}\n\n"
            f"[bold]Suggestions:[/bold] {len(result.final_review.suggestions)}",
            border_style="green" if result.final_review.passed else "yellow"
        )
        console.print(review_panel)
        console.print()
    
    # Final code (truncated)
    if result.final_code:
        code_preview = result.final_code[:500] + ("..." if len(result.final_code) > 500 else "")
        console.print(Panel(
            code_preview,
            title="[bold]Final Implementation (preview)[/bold]",
            border_style="dim"
        ))


def main():
    """Run examples"""
    console.print(Panel(
        "[bold cyan]Iterative Development Workflow Examples[/bold cyan]\n\n"
        "Demonstrates automated dev-review-fix loops",
        title="StartD8 Examples",
        border_style="cyan"
    ))
    
    examples = {
        '1': ('Simple Function', example_1_simple_function),
        '2': ('Bug Fix', example_2_bug_fix),
        '3': ('Mock Agents (No API Keys)', example_3_mock_agents),
        '4': ('Custom Prompts', example_4_custom_prompts),
    }
    
    console.print("\n[bold]Available Examples:[/bold]")
    for key, (name, _) in examples.items():
        console.print(f"  {key}. {name}")
    
    choice = console.input("\n[cyan]Select example (1-4) or 'all': [/cyan]")
    
    if choice.lower() == 'all':
        for name, func in examples.values():
            console.print(f"\n\n{'='*70}")
            console.print(f"Running: {name}")
            console.print('='*70 + "\n")
            func()
    elif choice in examples:
        examples[choice][1]()
    else:
        console.print("[red]Invalid choice[/red]")


if __name__ == "__main__":
    main()
