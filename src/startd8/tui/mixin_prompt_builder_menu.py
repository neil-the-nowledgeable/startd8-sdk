"""PromptBuilderMixin: extracted from tui_improved.py ImprovedTUI (Pass B)."""

from ._shared import *  # noqa: F401,F403


# Relocated lazy-loader state (was module-level in tui_improved.py)
# Prompt Builder imports (lazy loaded to avoid circular imports)
_prompt_builder_loaded = False
TemplateLoader = None
ProjectContext = None
PromptGenerator = None
run_prompt_builder_wizard = None
select_template = None
list_templates_table = None


def _load_prompt_builder():
    """Lazy load prompt builder module"""
    global _prompt_builder_loaded, TemplateLoader, ProjectContext, PromptGenerator
    global run_prompt_builder_wizard, select_template, list_templates_table
    
    if _prompt_builder_loaded:
        return True
    
    try:
        from ..prompt_builder import TemplateLoader as TL, ProjectContext as PC, PromptGenerator as PG
        from ..tui_prompt_builder import run_prompt_builder_wizard as rpbw, select_template as st, list_templates_table as ltt
        
        TemplateLoader = TL
        ProjectContext = PC
        PromptGenerator = PG
        run_prompt_builder_wizard = rpbw
        select_template = st
        list_templates_table = ltt
        _prompt_builder_loaded = True
        return True
    except ImportError as e:
        console.print(f"[yellow]Prompt Builder not available: {e}[/yellow]")
        return False


class PromptBuilderMixin:
    def prompt_builder_menu(self):
        """Prompt Builder - create prompts from templates"""
        # Lazy load prompt builder
        if not _load_prompt_builder():
            self.console.print("[red]Prompt Builder module not available.[/red]")
            self.console.print("[yellow]Try: pip install pyyaml[/yellow]")
            questionary.press_any_key_to_continue().ask()
            return
        
        first_run = True
        
        while True:
            self.show_header("Prompt Builder")
            
            # Show workflow intro on first run
            if first_run:
                if self.workflow_helper and self.workflow_helper.has_workflow_help("prompt_builder"):
                    self.workflow_helper.show_workflow_intro("prompt_builder")
                    
                    # Offer to see examples
                    show_examples = questionary.confirm(
                        "\nWould you like to see workflow examples?",
                        default=False,
                        style=custom_style
                    ).ask()
                    
                    if show_examples:
                        self.workflow_helper.show_workflow_examples("prompt_builder")
                first_run = False
            
            # Initialize loader with project templates support
            loader = TemplateLoader(project_dir=self.storage_dir)
            
            # Show available templates
            list_templates_table(loader)
            
            # Menu options
            action = questionary.select(
                "What would you like to do?",
                choices=[
                    "📝 Build prompt from template",
                    "📋 View template details",
                    "📁 Open templates folder",
                    "← Back to main menu"
                ],
                style=custom_style
            ).ask()
            
            if not action or "Back" in action:
                return
            
            if "Build prompt" in action:
                self._build_prompt_from_template(loader)
            elif "View template" in action:
                self._view_template_details(loader)
            elif "Open templates" in action:
                self._show_templates_location(loader)

    def _build_prompt_from_template(self, loader):
        """Build a prompt using the wizard"""
        # Select template
        template = select_template(loader)
        
        if not template:
            return
        
        # Determine project path for context
        # Priority: 1) User specified, 2) storage_dir parent, 3) cwd
        project_path_options = [
            f"Current directory: {Path.cwd()}",
        ]
        
        if self.storage_dir and self.storage_dir.parent != Path.cwd():
            project_path_options.insert(0, f"Storage directory parent: {self.storage_dir.parent}")
        
        project_path_options.extend([
            "Enter custom path...",
            "Skip (use defaults only)"
        ])
        
        self.console.print()
        path_choice = questionary.select(
            "Select project path for context auto-fill:",
            choices=project_path_options,
            style=custom_style
        ).ask()
        
        if not path_choice:
            return
        
        if "Current directory" in path_choice:
            project_path = Path.cwd()
        elif "Storage directory" in path_choice:
            project_path = self.storage_dir.parent
        elif "Enter custom" in path_choice:
            custom_path = questionary.text(
                "Enter project path:",
                default=str(Path.cwd()),
                style=custom_style
            ).ask()
            project_path = Path(custom_path) if custom_path else Path.cwd()
        else:
            project_path = None
        
        # Run the wizard
        result = run_prompt_builder_wizard(template, project_path, self.storage_dir)
        
        if result:
            # Save as prompt in framework and offer distribution
            self._save_generated_prompt(result)

    def _save_generated_prompt(self, generated):
        """Save generated prompt to framework and offer distribution"""
        self.console.print(Panel(
            f"[bold]Generated Prompt[/bold]\n\n"
            f"From template: {generated.template_name}\n"
            f"Words: {generated.word_count} | Lines: {generated.line_count}",
            border_style="green"
        ))
        
        action = questionary.select(
            "What would you like to do with this prompt?",
            choices=[
                "💾 Save and distribute to agents",
                "💾 Save only (distribute later)",
                "📋 Copy to clipboard (if available)",
                "👁️  View full content",
                "❌ Discard"
            ],
            style=custom_style
        ).ask()
        
        if not action or "Discard" in action:
            return
        
        if "View full" in action:
            self.console.print(Panel(
                generated.content,
                title="Full Prompt Content",
                border_style="cyan"
            ))
            questionary.press_any_key_to_continue().ask()
            # Ask again
            return self._save_generated_prompt(generated)
        
        if "Copy" in action:
            try:
                import subprocess
                subprocess.run(['pbcopy'], input=generated.content.encode(), check=True)
                self.console.print("[green]✓ Copied to clipboard[/green]")
            except Exception:
                self.console.print("[yellow]Clipboard not available. Showing content instead:[/yellow]")
                self.console.print(Panel(generated.content[:500] + "...", border_style="cyan"))
            questionary.press_any_key_to_continue().ask()
            return
        
        # Save to framework
        tags = [f"template:{generated.template_id}", "prompt-builder"]
        self.current_prompt = self.framework.create_prompt(
            content=generated.content,
            version="1.0.0",
            tags=tags
        )
        
        self.console.print(f"[green]✓ Prompt saved with ID: {self.current_prompt.id[:12]}...[/green]")
        
        if "distribute" in action.lower():
            # Go to distribution
            self.step2_distribute_prompt()
        else:
            questionary.press_any_key_to_continue().ask()

    def _view_template_details(self, loader):
        """View details of a specific template"""
        template = select_template(loader)
        
        if not template:
            return
        
        # Show template details
        self.console.print(Panel(
            f"[bold cyan]{template.name}[/bold cyan]\n\n"
            f"[bold]ID:[/bold] {template.id}\n"
            f"[bold]Category:[/bold] {template.category}\n"
            f"[bold]Version:[/bold] {template.version}\n"
            f"[bold]Source:[/bold] {'Built-in' if template.source == 'builtin' else 'User'}\n\n"
            f"[bold]Description:[/bold]\n{template.description}",
            title="Template Details",
            border_style="cyan"
        ))
        
        # Show variables
        if template.variables:
            var_table = Table(title="Template Variables", show_header=True)
            var_table.add_column("Name", style="cyan")
            var_table.add_column("Type", style="magenta")
            var_table.add_column("Required", justify="center")
            var_table.add_column("Default")
            var_table.add_column("Description")
            
            for var in sorted(template.variables, key=lambda v: v.order):
                var_table.add_row(
                    var.name,
                    var.input_type,
                    "✓" if var.required else "",
                    var.default or "",
                    var.description[:30] + "..." if len(var.description) > 30 else var.description
                )
            
            self.console.print()
            self.console.print(var_table)
        
        # Show content preview
        self.console.print()
        preview_content = template.content[:800] + "..." if len(template.content) > 800 else template.content
        self.console.print(Panel(
            preview_content,
            title="Content Preview (first 800 chars)",
            border_style="dim"
        ))
        
        questionary.press_any_key_to_continue().ask()

    def _show_templates_location(self, loader):
        """Show where templates are stored"""
        self.console.print(Panel(
            f"[bold]Template Locations[/bold]\n\n"
            f"[cyan]Built-in templates:[/cyan]\n  {loader.builtin_dir}\n\n"
            f"[cyan]User templates:[/cyan]\n  {loader.user_dir}\n\n"
            f"[cyan]Project templates:[/cyan]\n  {self.storage_dir / 'templates' if self.storage_dir else 'N/A'}\n\n"
            f"[dim]To add custom templates, create .yaml files in the user templates directory.[/dim]",
            title="Template Locations",
            border_style="cyan"
        ))
        
        # Offer to create user templates directory
        if not loader.user_dir.exists():
            if questionary.confirm("Create user templates directory?", default=True).ask():
                loader.create_user_templates_dir()
                self.console.print(f"[green]✓ Created: {loader.user_dir}[/green]")
        
        questionary.press_any_key_to_continue().ask()
