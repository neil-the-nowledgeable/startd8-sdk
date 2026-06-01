"""IterativeWorkflowMixin: extracted from tui_improved.py ImprovedTUI (Pass B)."""

from ._shared import *  # noqa: F401,F403

class IterativeWorkflowMixin:
    def iterative_workflow_menu(self):
        """Interactive menu for iterative dev-review-fix workflow"""
        self.show_header("Iterative Dev Workflow")
        
        # Show workflow intro with help
        if self.workflow_helper and self.workflow_helper.has_workflow_help("iterative_workflow"):
            self.workflow_helper.show_workflow_intro("iterative_workflow")
        else:
            self._show_iterative_intro_panel()
        
        # Offer to see examples
        show_examples = questionary.confirm(
            "\nWould you like to see workflow examples?",
            default=False,
            style=custom_style
        ).ask()
        
        if show_examples and self.workflow_helper:
            self.workflow_helper.show_workflow_examples("iterative_workflow")
        
        self.console.print()
        if not questionary.confirm("Continue with iterative workflow?", default=True, style=custom_style).ask():
            return
        
        # Step 1: Get task description
        if self.workflow_helper:
            self.workflow_helper.show_step_guidance("iterative_workflow", 1, "Describe the task you want the developer to implement")
        else:
            self.console.print("\n[bold cyan]Step 1 of 5: Describe Task[/bold cyan]")
        task = self._get_task_description()
        if not task:
            return
        
        # Step 2: Select developer agent
        if self.workflow_helper:
            self.workflow_helper.show_step_guidance("iterative_workflow", 2, "Choose the agent that will develop the solution")
        else:
            self.console.print("\n[bold cyan]Step 2 of 5: Select Developer Agent[/bold cyan]")
            self.console.print("[dim]This agent will implement your task[/dim]\n")
        dev_agent = self._select_ready_agent(
            "Choose developer agent",
            default_hint="Claude"
        )
        if not dev_agent:
            self.console.print("[yellow]No developer agent selected. Cancelled.[/yellow]")
            questionary.press_any_key_to_continue().ask()
            return
        
        # Step 3: Select reviewer agent
        self.console.print("\n[bold cyan]Step 2: Select Reviewer Agent[/bold cyan]")
        self.console.print("[dim]This agent will review the code (best to use a different agent)[/dim]\n")
        review_agent = self._select_ready_agent(
            "Choose reviewer agent",
            default_hint="GPT-4"
        )
        if not review_agent:
            self.console.print("[yellow]No reviewer agent selected. Cancelled.[/yellow]")
            questionary.press_any_key_to_continue().ask()
            return
        
        # Step 4: Configure options
        self.console.print("\n[bold cyan]Step 3: Configuration[/bold cyan]\n")
        config = self._configure_iterative_workflow()
        if not config:
            return
        
        # Step 5: Show confirmation
        if not self._confirm_iterative_workflow(task, dev_agent, review_agent, config):
            return
        
        # Step 6: Run workflow with progress display
        result = self._execute_iterative_workflow(task, dev_agent, review_agent, config)
        
        # Step 7: Display results
        if result:
            self._display_iterative_results(result)

    def _show_iterative_intro_panel(self):
        """Show introduction to iterative workflow"""
        self.console.print(Panel(
            "[bold cyan]Iterative Dev-Review-Fix Workflow[/bold cyan]\n\n"
            "This workflow automates the development cycle:\n\n"
            "  1️⃣  [bold]Developer Agent[/bold] implements your task\n"
            "  2️⃣  [bold]Reviewer Agent[/bold] checks the code\n"
            "  3️⃣  If issues found → Developer fixes them\n"
            "  4️⃣  Repeat until code passes review\n\n"
            "[bold]Best Practice:[/bold] Use different agents for dev and review\n"
            "[dim]Example: Claude for development, GPT-4 for review[/dim]",
            title="🔄 Dev → Review → Fix Loop",
            border_style="cyan"
        ))

    def _safe_path_input(self, prompt: str, **kwargs) -> Optional[str]:
        """
        Safely get path input from user, handling cases where questionary.path might not work.
        
        This handles the case where questionary.path() might return a string directly
        instead of a prompt object, which causes "'str' object has no attribute 'ask'" errors.
        
        Args:
            prompt: Prompt text
            **kwargs: Additional arguments for questionary.path or questionary.text
            
        Returns:
            Path string or None if cancelled
        """
        try:
            if hasattr(questionary, 'path'):
                path_prompt = questionary.path(prompt, **kwargs)
                # Check if it's actually a prompt object (has .ask method)
                if hasattr(path_prompt, 'ask'):
                    result = path_prompt.ask()
                    return result if isinstance(result, str) else None
                elif isinstance(path_prompt, str):
                    # If it returned a string directly (some versions do this), return it
                    return path_prompt if path_prompt else None
                else:
                    # Unexpected return type, fallback to text
                    return questionary.text(prompt, **kwargs).ask()
            else:
                # Fallback to text input if path() doesn't exist
                return questionary.text(prompt, **kwargs).ask()
        except (AttributeError, TypeError) as e:
            # If questionary.path fails for any reason, fallback to text input
            return questionary.text(prompt, **kwargs).ask()

    def _get_text_or_file_input(
        self,
        title: str,
        prompt_text: str,
        description: Optional[str] = None,
        example: Optional[str] = None,
        allow_empty: bool = False
    ) -> Optional[str]:
        """
        Reusable helper to get text input from user with option to load from file.
        
        Args:
            title: Title to display (e.g., "Task Description")
            prompt_text: Prompt label for text input (e.g., "Task:")
            description: Optional description/instructions to show
            example: Optional example text to show
            allow_empty: Whether to allow empty input (default: False)
            
        Returns:
            Text content or None if cancelled
        """
        self.console.print(f"\n[bold cyan]{title}[/bold cyan]\n")
        if description:
            self.console.print(f"[dim]{description}[/dim]")
        if example:
            self.console.print(f"[dim]Example: {example}[/dim]\n")
        
        # Ask user for input method
        input_method = questionary.select(
            "Choose input method:",
            choices=[
                "✏️  Enter text directly",
                "📁 Load from file",
                "← Cancel"
            ],
            style=custom_style
        ).ask()
        
        if not input_method or "Cancel" in input_method:
            return None
        
        content = None
        
        if "Enter text" in input_method:
            # Direct text input
            content = questionary.text(
                prompt_text,
                multiline=True,
                style=custom_style
            ).ask()
        
        elif "Load from file" in input_method:
            # File input - use safe path input helper
            file_path = self._safe_path_input(
                "Enter path to file:",
                style=custom_style,
                only_directories=False
            )
            
            if not file_path:
                return None
            
            try:
                from pathlib import Path
                file = Path(file_path).expanduser()
                
                if not file.exists():
                    self.console.print(f"\n[red]❌ File not found: {file}[/red]\n")
                    questionary.press_any_key_to_continue().ask()
                    return None
                
                if not file.is_file():
                    self.console.print(f"\n[red]❌ Not a file: {file}[/red]\n")
                    questionary.press_any_key_to_continue().ask()
                    return None
                
                # Read file content
                content = file.read_text(encoding='utf-8')
                
                # Show preview
                preview = content[:300] + ("..." if len(content) > 300 else "")
                self.console.print(Panel(
                    preview,
                    title=f"[dim]Loaded from {file.name} ({len(content)} chars)[/dim]",
                    border_style="green"
                ))
                
                # Confirm
                confirm = questionary.confirm(
                    "Use this content?",
                    default=True,
                    style=custom_style
                ).ask()
                
                if not confirm:
                    return None
                
            except UnicodeDecodeError:
                self.console.print(f"\n[red]❌ Error: File is not valid UTF-8 text[/red]\n")
                questionary.press_any_key_to_continue().ask()
                return None
            except Exception as e:
                self.console.print(f"\n[red]❌ Error reading file: {e}[/red]\n")
                questionary.press_any_key_to_continue().ask()
                return None
        
        # Validate content
        if not content or not content.strip():
            if not allow_empty:
                self.console.print("[yellow]⚠️  No content provided. Cancelled.[/yellow]")
                questionary.press_any_key_to_continue().ask()
                return None
        
        return content.strip() if content else None

    def _get_task_description(self) -> Optional[str]:
        """Get task description from user (via text input or file)"""
        return self._get_text_or_file_input(
            title="Task Description",
            prompt_text="Task:",
            description="Describe what you want the developer agent to implement.",
            example="Implement a function to validate email addresses with regex",
            allow_empty=False
        )

    def _configure_iterative_workflow(self) -> Optional[Dict[str, Any]]:
        """Configure workflow options"""
        # Max iterations
        max_iter_str = questionary.text(
            "Maximum iterations (1-10):",
            default="3",
            style=custom_style
        ).ask()
        
        if not max_iter_str:
            return None
        
        try:
            max_iterations = int(max_iter_str)
            max_iterations = max(1, min(10, max_iterations))
        except ValueError:
            max_iterations = 3
        
        # Save results
        save_results = questionary.confirm(
            "Save workflow results to file?",
            default=True,
            style=custom_style
        ).ask()
        
        if save_results is None:
            return None
        
        return {
            'max_iterations': max_iterations,
            'save_results': save_results
        }

    def _confirm_iterative_workflow(
        self,
        task: str,
        dev_agent: BaseAgent,
        review_agent: BaseAgent,
        config: Dict[str, Any]
    ) -> bool:
        """Show confirmation and get user approval"""
        
        task_preview = task[:200] + "..." if len(task) > 200 else task
        
        self.console.print("\n")
        self.console.print(Panel(
            f"[bold]Task:[/bold]\n{task_preview}\n\n"
            f"[bold]Developer:[/bold] {dev_agent.agent_name} ({dev_agent.model})\n"
            f"[bold]Reviewer:[/bold] {review_agent.agent_name} ({review_agent.model})\n"
            f"[bold]Max Iterations:[/bold] {config['max_iterations']}\n"
            f"[bold]Save Results:[/bold] {'Yes' if config['save_results'] else 'No'}",
            title="Confirm Workflow",
            border_style="yellow"
        ))
        
        return questionary.confirm(
            "Start workflow?",
            default=True,
            style=custom_style
        ).ask()

    def _execute_iterative_workflow(
        self,
        task: str,
        dev_agent: BaseAgent,
        review_agent: BaseAgent,
        config: Dict[str, Any]
    ) -> Optional[IterativeWorkflowResult]:
        """Execute workflow with progress display"""
        
        self.console.print("\n")
        self.show_header("Running Iterative Workflow")
        
        # Progress callback
        def on_iteration_complete(iteration):
            status = "✓ PASSED" if iteration.feedback and iteration.feedback.passed else "✗ FAILED"
            color = "green" if iteration.feedback and iteration.feedback.passed else "yellow"
            
            self.console.print(
                f"[{color}]Iteration {iteration.iteration_number}: {status}[/{color}]"
            )
            
            if iteration.feedback:
                if iteration.feedback.score is not None:
                    self.console.print(f"  Score: {iteration.feedback.score}/100")
                if iteration.feedback.issues:
                    self.console.print(f"  Issues: {len(iteration.feedback.issues)}")
            
            self.console.print(
                f"  Time: {iteration.dev_time_ms + iteration.review_time_ms}ms"
            )
            self.console.print()
        
        # Create and run workflow
        try:
            workflow = IterativeDevWorkflow(
                developer_agent=dev_agent,
                reviewer_agent=review_agent,
                max_iterations=config['max_iterations'],
                on_iteration_complete=on_iteration_complete
            )
            
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=self.console
            ) as progress:
                progress.add_task("[cyan]Running iterative workflow...", total=None)
                
                result = workflow.run(task)
            
            # Save if requested
            if config.get('save_results') and result:
                output_dir = self.storage_dir / "workflow_results"
                output_dir.mkdir(parents=True, exist_ok=True)
                save_workflow_result(result, output_dir)
                self.console.print(f"[dim]Results saved to {output_dir / result.workflow_id}.json[/dim]\n")
            
            return result
            
        except Exception as e:
            self.console.print(f"[red]Error: {e}[/red]")
            import traceback
            self.console.print(f"[dim]{traceback.format_exc()}[/dim]")
            questionary.press_any_key_to_continue().ask()
            return None

    def _display_iterative_results(self, result: IterativeWorkflowResult):
        """Display workflow results"""
        
        # Status
        status_color = "green" if result.successful else "yellow"
        status_text = "SUCCESS ✓" if result.successful else "INCOMPLETE"
        
        self.console.print(Panel(
            f"[bold {status_color}]{status_text}[/bold {status_color}]",
            border_style=status_color
        ))
        
        # Summary table
        table = Table(title="Workflow Summary")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", justify="right")
        
        table.add_row("Total Iterations", str(result.total_iterations))
        table.add_row("Status", result.status.value if hasattr(result.status, 'value') else str(result.status))
        table.add_row("Total Time", f"{result.total_time_ms / 1000:.2f}s")
        table.add_row("Total Tokens", f"{result.total_dev_tokens + result.total_review_tokens:,}")
        table.add_row("Estimated Cost", f"${result.total_cost:.4f}")
        
        if result.final_review and result.final_review.score is not None:
            table.add_row("Final Score", f"{result.final_review.score}/100")
        
        self.console.print(table)
        self.console.print()
        
        # Final code preview
        if result.final_code:
            code_preview = result.final_code[:500]
            if len(result.final_code) > 500:
                code_preview += "\n... (truncated)"
            
            self.console.print(Panel(
                code_preview,
                title="Final Implementation (Preview)",
                border_style="dim"
            ))
        
        # Actions menu
        while True:
            action = questionary.select(
                "What would you like to do?",
                choices=[
                    "📋 View full code",
                    "📊 View iteration details",
                    "💾 Copy code to clipboard",
                    "← Done"
                ],
                style=custom_style
            ).ask()
            
            if not action or "Done" in action:
                break
            
            if "full code" in action:
                self.console.print(Panel(result.final_code, title="Full Implementation"))
                questionary.press_any_key_to_continue().ask()
            
            elif "iteration details" in action:
                self._show_iteration_details(result)
            
            elif "clipboard" in action:
                try:
                    import pyperclip
                    pyperclip.copy(result.final_code)
                    self.console.print("[green]✓ Code copied to clipboard![/green]")
                except ImportError:
                    self.console.print("[yellow]pyperclip not installed. Install with: pip install pyperclip[/yellow]")
                questionary.press_any_key_to_continue().ask()

    def _show_iteration_details(self, result: IterativeWorkflowResult):
        """Show detailed view of each iteration"""
        for iteration in result.iterations:
            status = "PASSED" if iteration.feedback and iteration.feedback.passed else "FAILED"
            color = "green" if status == "PASSED" else "red"
            
            feedback_score = iteration.feedback.score if iteration.feedback else 'N/A'
            feedback_issues = len(iteration.feedback.issues) if iteration.feedback else 0
            feedback_suggestions = len(iteration.feedback.suggestions) if iteration.feedback else 0
            
            self.console.print(Panel(
                f"[bold]Status:[/bold] [{color}]{status}[/{color}]\n"
                f"[bold]Dev Time:[/bold] {iteration.dev_time_ms}ms\n"
                f"[bold]Review Time:[/bold] {iteration.review_time_ms}ms\n"
                f"[bold]Score:[/bold] {feedback_score}/100\n"
                f"[bold]Issues:[/bold] {feedback_issues}\n"
                f"[bold]Suggestions:[/bold] {feedback_suggestions}",
                title=f"Iteration {iteration.iteration_number}",
                border_style=color
            ))
            
            if iteration.feedback and iteration.feedback.issues:
                self.console.print("[bold]Issues:[/bold]")
                for issue in iteration.feedback.issues:
                    self.console.print(f"  • {issue}")
                self.console.print()
        
        questionary.press_any_key_to_continue().ask()
