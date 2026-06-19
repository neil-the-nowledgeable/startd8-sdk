"""
TUI Prompt Builder - Interactive wizard for building prompts from templates

Provides:
- Template selection with categories
- Sequential wizard for filling variables
- Project context auto-fill
- Preview before generating
- CLI fallback when questionary not available
"""

import sys
import os
from pathlib import Path
from typing import Optional, Dict, List, Any

try:
    import questionary
    from questionary import Style
    HAS_QUESTIONARY = True
except ImportError:
    HAS_QUESTIONARY = False
    questionary = None
    Style = None

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.syntax import Syntax

from .prompt_builder import (
    TemplateLoader,
    ProjectContext,
    PromptGenerator,
    PromptTemplate,
    TemplateVariable,
    TemplateContext,
    GeneratedPrompt,
)

console = Console()

# Custom style for questionary (only if available)
if HAS_QUESTIONARY and Style:
    custom_style = Style([
        ('qmark', 'fg:cyan bold'),
        ('question', 'bold'),
        ('answer', 'fg:cyan'),
        ('pointer', 'fg:cyan bold'),
        ('highlighted', 'fg:cyan bold'),
        ('selected', 'fg:green'),
    ])
else:
    custom_style = None


class PromptBuilderWizard:
    """Interactive wizard for building prompts from templates"""
    
    def __init__(
        self,
        template: PromptTemplate,
        project_path: Optional[Path] = None,
        tui_dir: Optional[Path] = None,
        policy_override: Optional[str] = None
    ):
        """
        Initialize the wizard.
        
        Args:
            template: The template to fill
            project_path: Path to project for context detection
            tui_dir: The startd8 data directory (for project templates)
            policy_override: CLI-provided policy string to override global defaults
        """
        self.template = template
        self.project_path = project_path or Path.cwd()
        self.tui_dir = tui_dir
        
        self.generator = PromptGenerator()
        self.context = TemplateContext(project_path=self.project_path)
        
        # Get auto-fill suggestions
        self.project_context = ProjectContext(self.project_path)
        self.suggestions = self.project_context.suggest_values()
        
        # Override with explicit CLI policy if provided (Concern 2)
        if policy_override is not None:
            self.suggestions["POLICY_CONSTRAINTS"] = policy_override

        self.context.auto_filled = self.suggestions.copy()
        
        # Get ordered variables
        self.variables = self.generator.get_ordered_variables(template)
        self.current_step = 0
        self.values: Dict[str, str] = {}
    
    def _is_interactive(self) -> bool:
        """Check if running in interactive mode"""
        return HAS_QUESTIONARY and sys.stdin.isatty()
    
    def run(self) -> Optional[GeneratedPrompt]:
        """Run the wizard and return generated prompt"""
        if self._is_interactive():
            return self._run_interactive()
        else:
            return self._run_non_interactive()
    
    def _run_interactive(self) -> Optional[GeneratedPrompt]:
        """Run interactive wizard with questionary"""
        console.clear()
        self._show_header()
        
        # Show template info
        console.print(Panel(
            f"[bold]{self.template.name}[/bold]\n\n"
            f"{self.template.description}\n\n"
            f"[dim]Category: {self.template.category} | Version: {self.template.version}[/dim]",
            title="Selected Template",
            border_style="cyan"
        ))
        
        # Process each variable
        for i, var in enumerate(self.variables):
            self.current_step = i
            
            console.print()
            self._show_progress()
            console.print()
            
            # Get value for this variable
            value = self._prompt_for_variable(var)
            
            if value is None:
                # User cancelled
                if questionary.confirm("Cancel prompt building?", default=False).ask():
                    return None
                # Try again
                i -= 1
                continue
            
            self.values[var.name] = value
        
        # Update context with collected values
        self.context.variable_values = self.values
        
        # Show preview and confirm
        console.print()
        return self._show_preview_and_confirm()
    
    def _run_non_interactive(self) -> Optional[GeneratedPrompt]:
        """Run non-interactive mode using defaults and auto-fill"""
        console.print("[yellow]Running in non-interactive mode (using defaults)[/yellow]\n")
        
        # Use auto-filled values and defaults
        for var in self.variables:
            if var.name in self.suggestions:
                self.values[var.name] = self.suggestions[var.name]
            elif var.default:
                self.values[var.name] = var.default
            elif var.required:
                console.print(f"[red]Missing required variable: {var.name}[/red]")
                return None
        
        self.context.variable_values = self.values
        
        # Generate and return
        result = self.generator.fill_template(self.template, self.context)
        console.print(Panel(
            f"Generated prompt with {result.word_count} words, {result.line_count} lines",
            title="Success",
            border_style="green"
        ))
        
        return result
    
    def _show_header(self):
        """Show wizard header"""
        console.print(Panel(
            "[bold cyan]Prompt Builder Wizard[/bold cyan]",
            border_style="cyan"
        ))
    
    def _show_progress(self):
        """Show progress indicator with completed, current, and future steps"""
        lines = []
        total = len(self.variables)
        
        for i, var in enumerate(self.variables):
            step_num = i + 1
            
            if i < self.current_step:
                # Completed - show with value
                value = self.values.get(var.name, "")
                display_value = value[:40] + "..." if len(str(value)) > 40 else value
                lines.append(f"  [green]✓ {step_num}. {var.name}:[/green] {display_value}")
            
            elif i == self.current_step:
                # Current - highlighted
                lines.append(f"  [cyan bold]▶ {step_num}. {var.name}[/cyan bold] [dim](current)[/dim]")
            
            else:
                # Future - dimmed
                optional = "[dim](optional)[/dim]" if var.is_optional else ""
                lines.append(f"  [dim]○ {step_num}. {var.name} {optional}[/dim]")
        
        progress_text = "\n".join(lines)
        console.print(Panel(
            progress_text,
            title=f"Progress ({self.current_step + 1}/{total})",
            border_style="dim"
        ))
    
    def _prompt_for_variable(self, var: TemplateVariable) -> Optional[str]:
        """Prompt user for a variable value"""
        # Build help text
        help_parts = []
        if var.description:
            help_parts.append(var.description)
        
        # Show default/suggestion
        suggested_value = None
        if var.name in self.suggestions:
            suggested_value = self.suggestions[var.name]
            help_parts.append(f"[cyan]Suggested: {suggested_value}[/cyan]")
        elif var.default:
            suggested_value = var.default
            help_parts.append(f"[dim]Default: {var.default}[/dim]")
        
        if not var.required:
            help_parts.append("[dim](optional - press Enter to skip)[/dim]")
        
        if help_parts:
            console.print(Panel(
                "\n".join(help_parts),
                title=f"Step {self.current_step + 1}: {var.name}",
                border_style="cyan"
            ))
        
        # Prompt based on input type
        if var.input_type == "select" and var.options:
            return self._prompt_select(var, suggested_value)
        elif var.input_type == "path":
            return self._prompt_path(var, suggested_value)
        elif var.input_type == "multiline":
            return self._prompt_multiline(var, suggested_value)
        else:
            return self._prompt_text(var, suggested_value)
    
    def _prompt_text(self, var: TemplateVariable, default: Optional[str]) -> Optional[str]:
        """Prompt for text input"""
        result = questionary.text(
            f"Enter {var.name}:",
            default=default or "",
            style=custom_style
        ).ask()
        
        if result is None:
            return None
        
        # Handle empty input
        if not result.strip():
            if var.required and not default:
                console.print("[red]This field is required.[/red]")
                return self._prompt_text(var, default)
            return default or ""
        
        return result
    
    def _prompt_select(self, var: TemplateVariable, default: Optional[str]) -> Optional[str]:
        """Prompt for selection from options"""
        options = var.options.copy()
        
        # Add "Other" option for flexibility
        options.append("Other (enter custom value)")
        
        result = questionary.select(
            f"Select {var.name}:",
            choices=options,
            default=default if default in var.options else None,
            style=custom_style
        ).ask()
        
        if result is None:
            return None
        
        if "Other" in result:
            return questionary.text(
                f"Enter custom value for {var.name}:",
                style=custom_style
            ).ask()
        
        return result
    
    def _prompt_path(self, var: TemplateVariable, default: Optional[str]) -> Optional[str]:
        """Prompt for path input with validation and browser option"""
        
        # Show current directory for reference
        console.print(f"[dim]Current directory: {Path.cwd()}[/dim]")
        
        # Offer path options
        path_options = []
        
        if default:
            path_options.append(f"Use suggested: {default}")
        
        path_options.extend([
            "Enter path manually",
            "Use current directory",
            "Browse directories..."
        ])
        
        choice = questionary.select(
            f"How to set {var.name}?",
            choices=path_options,
            style=custom_style
        ).ask()
        
        if choice is None:
            return None
        
        if "suggested" in choice:
            return default
        elif "current directory" in choice.lower():
            return str(Path.cwd())
        elif "Browse" in choice:
            return self._browse_directories(default)
        else:
            # Manual entry
            path_str = questionary.text(
                f"Enter path for {var.name}:",
                default=default or str(Path.cwd()),
                style=custom_style
            ).ask()
            
            if path_str:
                # Validate path exists
                path = Path(path_str).expanduser()
                if not path.exists():
                    console.print(f"[yellow]Warning: Path does not exist: {path}[/yellow]")
                    if not questionary.confirm("Use anyway?", default=True).ask():
                        return self._prompt_path(var, default)
                return str(path)
            
            return path_str
    
    def _browse_directories(self, start_path: Optional[str] = None) -> Optional[str]:
        """Simple directory browser"""
        current = Path(start_path or Path.cwd()).resolve()
        
        while True:
            if not current.exists():
                current = Path.cwd()
            
            # List directory contents
            choices = ["📁 [SELECT THIS DIRECTORY]", "📂 ../ (parent)"]
            
            try:
                dirs = sorted([d for d in current.iterdir() if d.is_dir() and not d.name.startswith('.')])
                for d in dirs[:20]:  # Limit to 20 dirs
                    choices.append(f"📂 {d.name}/")
                if len(dirs) > 20:
                    choices.append(f"[dim]... and {len(dirs) - 20} more[/dim]")
            except PermissionError:
                console.print("[red]Permission denied[/red]")
            
            choices.append("← Cancel")
            
            console.print(f"\n[cyan]Current: {current}[/cyan]")
            
            choice = questionary.select(
                "Navigate:",
                choices=choices,
                style=custom_style
            ).ask()
            
            if not choice or "Cancel" in choice:
                return None
            
            if "SELECT THIS" in choice:
                return str(current)
            elif "../" in choice:
                current = current.parent
            else:
                # Extract directory name
                dir_name = choice.replace("📂 ", "").replace("/", "")
                current = current / dir_name
    
    def _prompt_multiline(self, var: TemplateVariable, default: Optional[str]) -> Optional[str]:
        """Prompt for multiline input"""
        console.print("[dim]Enter multiple lines. Press Enter twice to finish.[/dim]")
        
        # Try to use editor for better multiline experience
        use_editor = questionary.confirm(
            "Open text editor for multiline input?",
            default=False
        ).ask()
        
        if use_editor:
            import tempfile
            import subprocess
            
            editor = os.environ.get('EDITOR', os.environ.get('VISUAL', 'nano'))
            
            with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
                if default:
                    f.write(default)
                temp_path = f.name
            
            try:
                subprocess.call([editor, temp_path])
                with open(temp_path, 'r') as f:
                    return f.read().strip()
            finally:
                os.unlink(temp_path)
        else:
            # Simple multiline input
            lines = []
            console.print("[dim]Enter text (empty line to finish):[/dim]")
            
            while True:
                try:
                    line = input()
                    if not line:
                        break
                    lines.append(line)
                except EOFError:
                    break
            
            return "\n".join(lines) if lines else default or ""
    
    def _show_preview_and_confirm(self) -> Optional[GeneratedPrompt]:
        """Show preview of generated prompt and confirm"""
        # Generate preview
        preview, unfilled = self.generator.get_unfilled_preview(
            self.template,
            self.context,
            max_length=1000
        )
        
        if unfilled:
            console.print(Panel(
                f"[yellow]Warning: Some variables are unfilled: {', '.join(unfilled)}[/yellow]",
                border_style="yellow"
            ))
        
        # Show preview
        console.print(Panel(
            preview,
            title="Preview (first 1000 chars)",
            border_style="cyan"
        ))
        
        # Confirm actions
        action = questionary.select(
            "What would you like to do?",
            choices=[
                "✅ Generate prompt",
                "✏️  Edit a variable",
                "👁️  View full preview",
                "❌ Cancel"
            ],
            style=custom_style
        ).ask()
        
        if not action or "Cancel" in action:
            return None
        
        if "Edit" in action:
            return self._edit_variable_and_retry()
        
        if "View full" in action:
            full_result = self.generator.fill_template(self.template, self.context)
            console.print(Panel(
                Syntax(full_result.content, "markdown", theme="monokai"),
                title=f"Full Preview ({full_result.word_count} words)",
                border_style="cyan"
            ))
            questionary.press_any_key_to_continue().ask()
            return self._show_preview_and_confirm()
        
        # Generate final prompt
        result = self.generator.fill_template(self.template, self.context)
        
        console.print(Panel(
            f"[green]✓ Prompt generated successfully![/green]\n\n"
            f"Words: {result.word_count}\n"
            f"Lines: {result.line_count}\n"
            f"Variables filled: {len(result.variables_used)}",
            title="Success",
            border_style="green"
        ))
        
        return result
    
    def _edit_variable_and_retry(self) -> Optional[GeneratedPrompt]:
        """Allow user to edit a variable and retry preview"""
        # Show current values
        var_choices = []
        for var in self.variables:
            current_val = self.values.get(var.name, self.context.auto_filled.get(var.name, "(empty)"))
            display_val = str(current_val)[:30] + "..." if len(str(current_val)) > 30 else current_val
            var_choices.append(f"{var.name}: {display_val}")
        
        var_choices.append("← Back to preview")
        
        choice = questionary.select(
            "Select variable to edit:",
            choices=var_choices,
            style=custom_style
        ).ask()
        
        if not choice or "Back" in choice:
            return self._show_preview_and_confirm()
        
        # Find and edit the variable
        var_name = choice.split(":")[0].strip()
        for var in self.variables:
            if var.name == var_name:
                new_value = self._prompt_for_variable(var)
                if new_value is not None:
                    self.values[var.name] = new_value
                    self.context.variable_values = self.values
                break
        
        return self._show_preview_and_confirm()


def run_prompt_builder_wizard(
    template: PromptTemplate,
    project_path: Optional[Path] = None,
    tui_dir: Optional[Path] = None,
    policy_override: Optional[str] = None
) -> Optional[GeneratedPrompt]:
    """
    Run the prompt builder wizard.
    
    Args:
        template: The template to fill
        project_path: Path to project for context detection
        tui_dir: The startd8 data directory
        policy_override: Optional policy string override
    
    Returns:
        GeneratedPrompt if successful, None if cancelled
    """
    wizard = PromptBuilderWizard(template, project_path, tui_dir, policy_override=policy_override)
    return wizard.run()


def select_template(
    loader: TemplateLoader,
    category_filter: Optional[str] = None
) -> Optional[PromptTemplate]:
    """
    Interactive template selection.
    
    Returns selected template or None if cancelled.
    """
    if not HAS_QUESTIONARY:
        console.print("[red]questionary not installed. Cannot run interactive selection.[/red]")
        return None
    
    templates = loader.list_templates()
    
    if not templates:
        console.print("[yellow]No templates found.[/yellow]")
        return None
    
    # Filter by category if specified
    if category_filter:
        templates = [t for t in templates if t.category == category_filter]
    
    # Group by category for display
    by_category = loader.get_templates_by_category()
    
    # Build choices with categories
    choices = []
    
    for category, cat_templates in sorted(by_category.items()):
        if category_filter and category != category_filter:
            continue
        
        choices.append(questionary.Separator(f"─── {category.upper()} ───"))
        
        for template in cat_templates:
            source_badge = "📦" if template.source == "builtin" else "👤"
            choices.append(f"{source_badge} {template.name} ({template.id})")
    
    choices.append(questionary.Separator("───────────────────────"))
    choices.append("← Cancel")
    
    choice = questionary.select(
        "Select a template:",
        choices=choices,
        style=custom_style
    ).ask()
    
    if not choice or "Cancel" in choice:
        return None
    
    # Extract template ID from choice
    # Format: "📦 Template Name (template_id)"
    if "(" in choice and ")" in choice:
        template_id = choice.split("(")[-1].rstrip(")")
        return loader.get_template(template_id)
    
    return None


def list_templates_table(loader: TemplateLoader) -> None:
    """Display templates in a rich table"""
    templates = loader.list_templates()
    
    if not templates:
        console.print("[yellow]No templates found.[/yellow]")
        return
    
    table = Table(title="Available Prompt Templates", show_header=True)
    table.add_column("ID", style="cyan")
    table.add_column("Name", style="bold")
    table.add_column("Category", style="magenta")
    table.add_column("Source", style="green")
    table.add_column("Variables", justify="right")
    table.add_column("Description")
    
    for template in templates:
        source_badge = "📦 Built-in" if template.source == "builtin" else "👤 User"
        desc = template.description[:40] + "..." if len(template.description) > 40 else template.description
        
        table.add_row(
            template.id,
            template.name,
            template.category,
            source_badge,
            str(len(template.variables)),
            desc
        )
    
    console.print()
    console.print(table)
    console.print()

