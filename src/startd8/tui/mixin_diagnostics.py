"""DiagnosticsMixin: extracted from tui_improved.py ImprovedTUI (Pass B)."""

from ._shared import *  # noqa: F401,F403

class DiagnosticsMixin:
    def analyze_last_error_workflow(self):
        """Analyze the last error from log files"""
        self.show_header("Analyze Last Error")
        
        # Show where logs are searched
        config_dir = default_config_dir()
        data_dir = default_data_dir()
        search_paths = [
            config_dir / "logs",
            data_dir / "logs",
            Path.cwd(),
        ]
        
        error_info = get_last_error_from_logs()
        if not error_info:
            self.console.print(Panel(
                "[yellow]No recent errors found.[/yellow]\n\n"
                f"Searched directories:\n"
                f"  • {config_dir / 'logs'}\n"
                f"  • {data_dir / 'logs'}\n"
                f"  • {Path.cwd()}\n\n"
                "Logs are automatically created when you run workflows.\n"
                "Run a workflow first to generate error logs.",
                title="No Errors Found",
                border_style="yellow",
            ))
            questionary.press_any_key_to_continue().ask()
            return

        # Display structured error information using Rich Table
        formatted = format_error_for_analysis(error_info)
        
        # Create metadata table
        metadata_table = Table(title="Error Metadata", show_header=True, header_style="bold cyan")
        metadata_table.add_column("Field", style="cyan")
        metadata_table.add_column("Value", style="white")
        
        if error_info.get('timestamp'):
            metadata_table.add_row("Timestamp", str(error_info['timestamp']))
        if error_info.get('logger'):
            metadata_table.add_row("Logger", error_info['logger'])
        if error_info.get('source'):
            src = error_info['source']
            source_str = f"{src.get('file', 'Unknown')}:{src.get('line', '?')} in {src.get('function', '?')}"
            metadata_table.add_row("Source", source_str)
        if error_info.get('exception_type'):
            metadata_table.add_row("Exception Type", error_info['exception_type'])
        if error_info.get('correlation_id'):
            metadata_table.add_row("Correlation ID", f"[bold cyan]{error_info['correlation_id']}[/bold cyan]")
        if error_info.get('trace_id'):
            metadata_table.add_row("Trace ID", f"[bold cyan]{error_info['trace_id']}[/bold cyan]")
        
        self.console.print("\n")
        self.console.print(metadata_table)
        self.console.print("\n")
        
        # Show error message panel
        error_message = error_info.get('message', 'No message')
        self.console.print(Panel(
            error_message,
            title="Error Message",
            border_style="red"
        ))
        
        # Show traceback if available
        if error_info.get('exception'):
            self.console.print("\n")
            self.console.print(Panel(
                error_info['exception'],
                title="Exception/Traceback",
                border_style="yellow"
            ))
        
        proceed = questionary.confirm("\nUse this error for analysis?", default=True, style=custom_style).ask()
        if not proceed:
            return
        
        # Allow editing the error text before analysis (requirement #3)
        edit_choice = questionary.select(
            "Would you like to edit the error text before analysis?",
            choices=[
                "Use as-is",
                "Edit error text",
                "← Cancel"
            ],
            default="Use as-is",
            style=custom_style
        ).ask()
        
        if not edit_choice or "Cancel" in edit_choice:
            return
        
        if "Edit" in edit_choice:
            edited_text = questionary.text(
                "Edit the error text (you can modify or add context):",
                default=formatted,
                multiline=True,
                style=custom_style
            ).ask()
            if edited_text:
                formatted = edited_text
            else:
                self.console.print("[yellow]No changes made, using original error text.[/yellow]")

        # Ensure agent status is up to date
        self.agent_status = AgentConfigTester.test_all()
        
        # Select analyzer agent
        analyzer = self._select_ready_agent("Select agent for error analysis")
        if not analyzer:
            return

        # Run pipeline
        try:
            pipeline = WorkflowTemplates.error_analysis_chain(analyzer)
            pipeline.framework = self.framework
            
            with self.console.status("[bold green]Running analysis...[/bold green]"):
                result = pipeline.run(formatted)

            # Display results
            result_panel = Panel(
                f"[bold]Agent:[/bold] {analyzer.name} ({analyzer.model})\n"
                f"[bold]Time:[/bold] {result.total_time_ms}ms\n"
                f"[bold]Tokens:[/bold] {result.total_tokens:,}\n"
                f"[bold]Cost:[/bold] ${result.total_cost:.4f}\n\n"
                f"{result.final_output}",
                title="Error Analysis Summary",
                border_style="green"
            )
            self.console.print("\n")
            self.console.print(result_panel)
            
            # Save option
            saved_path = None
            save = questionary.confirm("\nSave analysis to file?", default=True, style=custom_style).ask()
            if save:
                default_dir = Path.cwd()
                default_filename = f"error_analysis_{result.pipeline_id[:8]}.md"
                filename = questionary.text("Filename:", default=default_filename, style=custom_style).ask()
                
                if filename:
                    filename_path = Path(filename)
                    if not filename_path.is_absolute():
                        filename_path = default_dir / filename_path
                    
                    # Include raw JSON entry if available
                    raw_json = error_info.get('raw_json_entry', '')
                    json_section = ""
                    if raw_json:
                        json_section = f"\n\n---\n\n## Raw JSON Log Entry\n\n```json\n{json.dumps(raw_json, indent=2)}\n```\n"
                    
                    with open(filename_path, 'w', encoding='utf-8') as f:
                        f.write(f"# Error Analysis Report\n\n")
                        f.write(f"**Pipeline ID:** {result.pipeline_id}\n")
                        f.write(f"**Analyzed:** {error_info.get('timestamp', 'Unknown')}\n")
                        f.write(f"**Agent:** {analyzer.name} ({analyzer.model})\n\n")
                        f.write("---\n\n")
                        f.write("## Original Error\n\n")
                        f.write(formatted)
                        f.write("\n\n---\n\n")
                        f.write("## Analysis Result\n\n")
                        f.write(result.final_output)
                        f.write("\n\n---\n\n")
                        f.write("## Pipeline Steps\n\n")
                        for step in result.steps:
                            f.write(f"### {step['step_name']} ({step['agent']})\n\n")
                            f.write(f"{step['output']}\n\n")
                        f.write(json_section)
                    
                    saved_path = str(filename_path)
                    self.console.print(f"[green]✓ Saved to {filename_path}[/green]")
                    
                    # Option to copy to clipboard (requirement #6)
                    try:
                        import pyperclip
                        copy_choice = questionary.confirm(
                            "Copy analysis result to clipboard?",
                            default=False,
                            style=custom_style
                        ).ask()
                        if copy_choice:
                            clipboard_text = f"Error Analysis Result\n\n{result.final_output}\n\nSaved to: {saved_path}"
                            pyperclip.copy(clipboard_text)
                            self.console.print("[green]✓ Copied to clipboard[/green]")
                    except ImportError:
                        # pyperclip not available, skip clipboard option
                        pass
            
            # Option to create queue prompt
            if saved_path:
                create_queue = questionary.confirm(
                    "\nCreate a prompt from this analysis to distribute via job queue?",
                    default=False,
                    style=custom_style
                ).ask()
                if create_queue:
                    error_info_str = formatted
                    self._create_queue_prompt_from_analysis(
                        error_info_str,
                        result.final_output,
                        saved_path
                    )
        except (AgentError, APIError, ConfigurationError) as e:
            self.console.print(f"\n[red]Error analysis failed: {e}[/red]")
            if hasattr(e, 'original_error') and e.original_error:
                self.console.print(f"[dim]Original error: {e.original_error}[/dim]")
        except Exception as e:
            self.console.print(f"\n[red]Unexpected Error: {e}[/red]")
            import traceback
            self.console.print(f"[dim]{traceback.format_exc()}[/dim]")
        
        questionary.press_any_key_to_continue().ask()

    def run_self_diagnostics(self):
        """Run self-diagnostic workflow"""
        self.show_header("Self-Diagnostics")

        self.console.print(Panel(
            "[bold]Self-Diagnostic Workflow[/bold]\n\n"
            "This workflow checks the health of the Startd8 SDK:\n"
            "• Agent connectivity and API keys\n"
            "• Cost database integrity\n"
            "• Storage and file permissions\n"
            "• Framework initialization\n\n"
            "If issues are found, you can:\n"
            "• Get AI-powered analysis\n"
            "• Apply safe auto-fixes",
            border_style="cyan"
        ))

        # Ask for check options
        check_choice = questionary.select(
            "What type of diagnostics do you want to run?",
            choices=[
                "🔍 Quick Checks (no API calls, fast)",
                "🔬 Full Diagnostics (includes API connectivity tests)",
                "📂 Storage Checks Only",
                "🤖 Agent Checks Only",
                "💰 Cost System Checks Only",
                "⚙️  Framework Checks Only",
                "← Back to Menu"
            ],
            style=custom_style
        ).ask()

        if not check_choice or "Back" in check_choice:
            return

        try:
            from startd8.diagnostics import (
                DiagnosticRunner,
                DiagnosticAnalyzer,
                AutoFixer,
                CheckCategory,
            )
        except ImportError as e:
            self.console.print(f"[red]Failed to import diagnostics module: {e}[/red]")
            questionary.press_any_key_to_continue().ask()
            return

        # Run diagnostics
        runner = DiagnosticRunner(framework=self.framework)

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=self.console
        ) as progress:
            task = progress.add_task("Running diagnostics...", total=None)

            if "Quick" in check_choice:
                report = runner.run_quick()
            elif "Full" in check_choice:
                report = runner.run_all(include_api_checks=True)
            elif "Storage" in check_choice:
                report = runner.run_category(CheckCategory.STORAGE)
            elif "Agent" in check_choice:
                report = runner.run_category(CheckCategory.AGENTS)
            elif "Cost" in check_choice:
                report = runner.run_category(CheckCategory.COSTS)
            elif "Framework" in check_choice:
                report = runner.run_category(CheckCategory.FRAMEWORK)
            else:
                report = runner.run_all()

            progress.update(task, completed=True)

        # Display results
        self._display_diagnostic_report(report)

        # If failures, offer options
        if report.has_failures():
            self.console.print("\n[yellow]Issues found![/yellow]\n")

            action = questionary.select(
                "What would you like to do?",
                choices=[
                    "🤖 Analyze with AI agent",
                    "🔧 Apply safe auto-fixes",
                    "📄 Save report to file",
                    "← Continue without action"
                ],
                style=custom_style
            ).ask()

            if action and "Analyze" in action:
                self._analyze_diagnostics_with_agent(report)
            elif action and "auto-fix" in action:
                self._apply_diagnostic_fixes(report)
            elif action and "Save" in action:
                self._save_diagnostic_report(report)
        else:
            self.console.print("\n[green]All diagnostics passed![/green]\n")

        questionary.press_any_key_to_continue().ask()

    def _display_diagnostic_report(self, report):
        """Display diagnostic report with Rich formatting"""
        from startd8.diagnostics import HealthStatus, CheckCategory

        # Summary table
        summary = report.summary
        summary_table = Table(title="Diagnostic Summary", show_header=True, header_style="bold cyan")
        summary_table.add_column("Status", justify="center")
        summary_table.add_column("Count", justify="center")

        status_colors = {
            "healthy": "green",
            "warning": "yellow",
            "critical": "red",
            "unknown": "dim",
            "skipped": "dim",
        }

        for status, count in summary.items():
            if count > 0:
                color = status_colors.get(status, "white")
                summary_table.add_row(f"[{color}]{status.upper()}[/{color}]", str(count))

        self.console.print("\n")
        self.console.print(summary_table)

        # Details by category
        for category in CheckCategory:
            category_checks = report.get_by_category(category)
            if not category_checks:
                continue

            self.console.print(f"\n[bold]{category.value.upper()}[/bold]")

            for check in category_checks:
                icon = {
                    HealthStatus.HEALTHY: "[green]✓[/green]",
                    HealthStatus.WARNING: "[yellow]⚠[/yellow]",
                    HealthStatus.CRITICAL: "[red]✗[/red]",
                    HealthStatus.UNKNOWN: "[dim]?[/dim]",
                    HealthStatus.SKIPPED: "[dim]⏭[/dim]",
                }[check.status]

                self.console.print(f"  {icon} {check.name}: {check.message}")

                if check.details and check.status != HealthStatus.HEALTHY:
                    for key, value in check.details.items():
                        self.console.print(f"      [dim]{key}: {value}[/dim]")

    def _analyze_diagnostics_with_agent(self, report):
        """Analyze diagnostic failures with an AI agent"""
        from startd8.diagnostics import DiagnosticAnalyzer

        # Get ready agents
        ready_agents = self._get_ready_agents()
        if not ready_agents:
            self.console.print("[yellow]No agents available for analysis. Using mock agent.[/yellow]")
            analyzer = DiagnosticAnalyzer()  # Uses MockAgent by default
        else:
            agent_choice = questionary.select(
                "Select agent for analysis:",
                choices=ready_agents + ["← Use Mock Agent (no API cost)"],
                style=custom_style
            ).ask()

            if not agent_choice or "Mock" in agent_choice:
                analyzer = DiagnosticAnalyzer()
            else:
                # Create agent instance
                agent = self._create_agent_from_name(agent_choice)
                if agent:
                    analyzer = DiagnosticAnalyzer(agent=agent)
                else:
                    analyzer = DiagnosticAnalyzer()

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=self.console
        ) as progress:
            task = progress.add_task("Analyzing failures with agent...", total=None)
            analysis = analyzer.analyze_failures(report)
            progress.update(task, completed=True)

        self.console.print("\n")
        self.console.print(Panel(
            Markdown(analysis),
            title="Agent Analysis",
            border_style="cyan"
        ))

    def _apply_diagnostic_fixes(self, report):
        """Apply safe auto-fixes for diagnostic failures"""
        from startd8.diagnostics import AutoFixer

        fixer = AutoFixer()
        available = fixer.get_available_fixes(report)

        if not available:
            self.console.print("[yellow]No auto-fixes available for these issues.[/yellow]")
            return

        self.console.print(f"[cyan]Available fixes: {', '.join(available)}[/cyan]\n")

        confirm = questionary.confirm(
            f"Apply {len(available)} safe auto-fix(es)?",
            default=True,
            style=custom_style
        ).ask()

        if not confirm:
            return

        results = fixer.apply_all(report)

        for fix_hint, result in results:
            self.console.print(f"  • {fix_hint}: {result}")

        self.console.print("\n[green]Auto-fixes applied.[/green]")

    def _save_diagnostic_report(self, report):
        """Save diagnostic report to file"""
        from pathlib import Path
        from datetime import datetime

        default_dir = default_data_dir() / "diagnostics"
        default_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        default_filename = f"diagnostic_report_{timestamp}.md"

        filename = questionary.text(
            "Save report as:",
            default=str(default_dir / default_filename),
            style=custom_style
        ).ask()

        if not filename:
            return

        filepath = Path(filename)
        filepath.parent.mkdir(parents=True, exist_ok=True)

        with open(filepath, 'w') as f:
            f.write(report.to_markdown())

        self.console.print(f"[green]✓ Saved to {filepath}[/green]")

    def configure_resilience(self):
        """Configure resilience and self-healing settings"""
        self.show_header("Resilience Settings")

        # Get current config
        from ..config import get_config_manager
        config_manager = get_config_manager()
        current_level = config_manager.get_resilience_level()

        self.console.print(Panel(
            "[bold]Resilience Configuration[/bold]\n\n"
            "Control self-healing and fault-tolerance features:\n\n"
            "• [cyan]OFF[/cyan] - No resilience (fastest, no overhead)\n"
            "• [cyan]MINIMAL[/cyan] - Basic retry only\n"
            "• [cyan]STANDARD[/cyan] - Retry + Circuit Breaker + Auto-fix (recommended)\n"
            "• [cyan]AGGRESSIVE[/cyan] - All features with higher limits\n"
            "• [cyan]CUSTOM[/cyan] - Fine-grained control\n\n"
            f"Current level: [bold green]{current_level.upper()}[/bold green]",
            border_style="cyan"
        ))

        # Show current settings summary
        try:
            resilience_config = config_manager.load_resilience_config()
            if resilience_config:
                summary_table = Table(title="Current Settings", show_header=True, header_style="bold cyan")
                summary_table.add_column("Feature", style="cyan")
                summary_table.add_column("Status", justify="center")
                summary_table.add_column("Details", style="dim")

                # Retry
                retry_status = "[green]ON[/green]" if resilience_config.retry.enabled else "[red]OFF[/red]"
                retry_detail = f"max_attempts={resilience_config.retry.max_attempts}"
                summary_table.add_row("Retry", retry_status, retry_detail)

                # Circuit Breaker
                cb_status = "[green]ON[/green]" if resilience_config.circuit_breaker.enabled else "[red]OFF[/red]"
                cb_detail = f"threshold={resilience_config.circuit_breaker.failure_threshold}"
                summary_table.add_row("Circuit Breaker", cb_status, cb_detail)

                # Auto-fix
                af_status = "[green]ON[/green]" if resilience_config.auto_fix.enabled else "[red]OFF[/red]"
                af_detail = "safe_only" if resilience_config.auto_fix.safe_only else "all fixes"
                summary_table.add_row("Auto-Fix", af_status, af_detail)

                # Diagnostics
                diag_status = "[green]ON[/green]" if resilience_config.diagnostics.enabled else "[red]OFF[/red]"
                diag_detail = "+API checks" if resilience_config.diagnostics.include_api_checks else "quick only"
                summary_table.add_row("Diagnostics", diag_status, diag_detail)

                # Error Strategy
                strategy = resilience_config.workflow_errors.default_strategy.value
                summary_table.add_row("Error Strategy", strategy.upper(), f"max_iter={resilience_config.workflow_errors.max_iterations}")

                self.console.print("\n")
                self.console.print(summary_table)
        except Exception as e:
            self.console.print(f"[yellow]Could not load current settings: {e}[/yellow]")

        # Menu options
        action = questionary.select(
            "\nWhat would you like to do?",
            choices=[
                "🔄 Change Resilience Level",
                "⚙️  Fine-tune Settings",
                "📊 View Full Configuration",
                "🔙 Reset to Default (STANDARD)",
                "← Back to Menu"
            ],
            style=custom_style
        ).ask()

        if not action or "Back" in action:
            return

        if "Change Resilience Level" in action:
            self._change_resilience_level(config_manager, current_level)
        elif "Fine-tune" in action:
            self._fine_tune_resilience(config_manager)
        elif "View Full" in action:
            self._view_full_resilience_config(config_manager)
        elif "Reset" in action:
            config_manager.set_resilience_level("standard")
            self.console.print("[green]✓ Reset to STANDARD level[/green]")
            # Update framework if available
            if self.framework and hasattr(self.framework, 'resilience_config'):
                self.framework.resilience_config = config_manager.load_resilience_config()

        questionary.press_any_key_to_continue().ask()

    def _change_resilience_level(self, config_manager, current_level):
        """Change resilience level"""
        levels = [
            ("OFF - No resilience features", "off"),
            ("MINIMAL - Basic retry only", "minimal"),
            ("STANDARD - Retry + Circuit Breaker + Auto-fix (Recommended)", "standard"),
            ("AGGRESSIVE - All features, more retries", "aggressive"),
        ]

        choices = []
        for label, value in levels:
            if value == current_level:
                choices.append(f"✓ {label}")
            else:
                choices.append(f"  {label}")

        selected = questionary.select(
            "Select resilience level:",
            choices=choices + ["← Cancel"],
            style=custom_style
        ).ask()

        if not selected or "Cancel" in selected:
            return

        # Extract level from selection
        for label, value in levels:
            if label in selected:
                config_manager.set_resilience_level(value)
                self.console.print(f"[green]✓ Resilience level set to {value.upper()}[/green]")

                # Update framework if available
                if self.framework and hasattr(self.framework, 'resilience_config'):
                    self.framework.resilience_config = config_manager.load_resilience_config()
                break

    def _fine_tune_resilience(self, config_manager):
        """Fine-tune individual resilience settings"""
        try:
            from startd8.resilience import (
                ResilienceConfig, ResilienceLevel, RetrySettings,
                CircuitBreakerSettings, WorkflowErrorSettings,
                AutoFixSettings, DiagnosticsSettings, ErrorStrategy
            )
        except ImportError:
            self.console.print("[red]Resilience module not available[/red]")
            return

        current = config_manager.load_resilience_config()
        if not current:
            self.console.print("[red]Could not load current config[/red]")
            return

        setting = questionary.select(
            "Which setting to adjust?",
            choices=[
                "🔄 Retry - max attempts, delays",
                "⚡ Circuit Breaker - failure threshold, recovery",
                "🔧 Auto-Fix - enable/disable, safe only",
                "🩺 Diagnostics - API checks, auto-analyze",
                "⚠️  Error Strategy - stop/retry/skip",
                "← Cancel"
            ],
            style=custom_style
        ).ask()

        if not setting or "Cancel" in setting:
            return

        if "Retry" in setting:
            max_attempts = questionary.text(
                "Max retry attempts:",
                default=str(current.retry.max_attempts),
                style=custom_style
            ).ask()
            if max_attempts:
                current.retry.max_attempts = int(max_attempts)

        elif "Circuit Breaker" in setting:
            threshold = questionary.text(
                "Failure threshold before opening:",
                default=str(current.circuit_breaker.failure_threshold),
                style=custom_style
            ).ask()
            if threshold:
                current.circuit_breaker.failure_threshold = int(threshold)

        elif "Auto-Fix" in setting:
            enabled = questionary.confirm(
                "Enable auto-fix?",
                default=current.auto_fix.enabled,
                style=custom_style
            ).ask()
            current.auto_fix.enabled = enabled

            if enabled:
                safe_only = questionary.confirm(
                    "Safe fixes only (recommended)?",
                    default=current.auto_fix.safe_only,
                    style=custom_style
                ).ask()
                current.auto_fix.safe_only = safe_only

        elif "Diagnostics" in setting:
            include_api = questionary.confirm(
                "Include API connectivity checks (costs tokens)?",
                default=current.diagnostics.include_api_checks,
                style=custom_style
            ).ask()
            current.diagnostics.include_api_checks = include_api

        elif "Error Strategy" in setting:
            strategy = questionary.select(
                "Default error handling strategy:",
                choices=[
                    "STOP - Stop workflow on first error",
                    "RETRY - Retry failed step",
                    "SKIP - Skip failed step, continue"
                ],
                style=custom_style
            ).ask()
            if strategy:
                if "STOP" in strategy:
                    current.workflow_errors.default_strategy = ErrorStrategy.STOP
                elif "RETRY" in strategy:
                    current.workflow_errors.default_strategy = ErrorStrategy.RETRY
                elif "SKIP" in strategy:
                    current.workflow_errors.default_strategy = ErrorStrategy.SKIP

        # Save changes
        current.level = ResilienceLevel.CUSTOM
        config_manager.save_resilience_config(current)
        self.console.print("[green]✓ Settings saved[/green]")

        # Update framework
        if self.framework and hasattr(self.framework, 'resilience_config'):
            self.framework.resilience_config = current

    def _view_full_resilience_config(self, config_manager):
        """View full resilience configuration as JSON"""
        config = config_manager.get_resilience_config()
        self.console.print("\n")
        self.console.print(Panel(
            json.dumps(config, indent=2),
            title="Full Resilience Configuration",
            border_style="cyan"
        ))

    def run_agent_config_error_analysis(self):
        """Analyze agent configuration errors"""
        self.show_header("Analyze Agent Config Errors")
        
        # Get non-ready agents
        custom_agents = self.agent_manager.list_agents()
        not_ready_agents = []
        
        for agent in custom_agents:
            try:
                instance = self.agent_manager.create_agent_instance(agent)
                if not instance:
                    not_ready_agents.append(agent)
            except Exception as e:
                try:
                    self.agent_manager.capture_agent_error(agent, e, "creation")
                except Exception:
                    pass
                not_ready_agents.append(agent)
        
        if not not_ready_agents:
            self.console.print(Panel(
                "[green]✓ All agents are configured correctly![/green]\n\n"
                "No agent configuration errors found.",
                title="No Errors",
                border_style="green"
            ))
            questionary.press_any_key_to_continue().ask()
            return
        
        # Display agents with errors
        error_table = Table(title="Agents with Configuration Errors", show_header=True)
        error_table.add_column("Agent", style="bold cyan")
        error_table.add_column("Type", style="magenta")
        error_table.add_column("Model", style="blue")
        error_table.add_column("Error", style="red")
        
        error_info_list = []
        for agent in not_ready_agents:
            agent_name = agent.get('name', 'unnamed')
            agent_type = agent.get('type', 'unknown')
            agent_model = agent.get('model', 'unknown')
            
            # Try to get error details
            error_msg = "Invalid configuration"
            try:
                instance = self.agent_manager.create_agent_instance(agent)
                if not instance:
                    error_msg = "Agent creation returned None"
            except Exception as e:
                error_msg = str(e)[:60]
            
            error_table.add_row(agent_name, agent_type, agent_model, error_msg)
            error_info_list.append({
                'agent': agent_name,
                'type': agent_type,
                'model': agent_model,
                'error': error_msg,
                'config': agent
            })
        
        self.console.print("\n")
        self.console.print(error_table)
        
        # Select which agent to analyze
        if len(not_ready_agents) > 1:
            choices = [f"{a.get('name', 'unnamed')} ({a.get('type')}/{a.get('model', 'default')})" for a in not_ready_agents]
            choices.append("All agents")
            choices.append("← Cancel")
            
            selected = questionary.select(
                "\nSelect agent to analyze:",
                choices=choices,
                style=custom_style
            ).ask()
            
            if not selected or "Cancel" in selected:
                return
            
            if "All agents" in selected:
                agents_to_analyze = not_ready_agents
            else:
                idx = choices.index(selected)
                agents_to_analyze = [not_ready_agents[idx]]
        else:
            agents_to_analyze = not_ready_agents
        
        # Format error info for analysis
        error_info_str = "Agent Configuration Errors:\n\n"
        for agent_info in error_info_list:
            if any(a.get('name') == agent_info['agent'] for a in agents_to_analyze):
                error_info_str += f"Agent: {agent_info['agent']}\n"
                error_info_str += f"Type: {agent_info['type']}\n"
                error_info_str += f"Model: {agent_info['model']}\n"
                error_info_str += f"Error: {agent_info['error']}\n"
                error_info_str += f"Config: {json.dumps(agent_info['config'], indent=2)}\n\n"
        
        # Select analyzer agent
        self.agent_status = AgentConfigTester.test_all()
        analyzer = self._select_ready_agent("Select agent for error analysis")
        if not analyzer:
            return
        
        # Run pipeline
        try:
            pipeline = WorkflowTemplates.agent_config_error_analysis_chain(analyzer)
            pipeline.framework = self.framework
            
            with self.console.status("[bold green]Running analysis...[/bold green]"):
                result = pipeline.run(error_info_str)
            
            # Display results
            result_panel = Panel(
                f"[bold]Agent:[/bold] {analyzer.name} ({analyzer.model})\n"
                f"[bold]Time:[/bold] {result.total_time_ms}ms\n"
                f"[bold]Tokens:[/bold] {result.total_tokens:,}\n"
                f"[bold]Cost:[/bold] ${result.total_cost:.4f}\n\n"
                f"{result.final_output}",
                title="Configuration Error Analysis Summary",
                border_style="green"
            )
            self.console.print("\n")
            self.console.print(result_panel)
            
            # Save option
            saved_path = None
            save = questionary.confirm("\nSave analysis to file?", default=True, style=custom_style).ask()
            if save:
                default_dir = Path.cwd()
                default_filename = f"agent_config_analysis_{result.pipeline_id[:8]}.md"
                filename = questionary.text("Filename:", default=default_filename, style=custom_style).ask()
                
                if filename:
                    filename_path = Path(filename)
                    if not filename_path.is_absolute():
                        filename_path = default_dir / filename_path
                    
                    content = f"# Agent Configuration Error Analysis Report\n\n"
                    content += f"**Pipeline ID:** {result.pipeline_id}\n"
                    content += f"**Agent:** {analyzer.name} ({analyzer.model})\n\n"
                    content += "---\n\n"
                    content += "## Configuration Errors\n\n"
                    content += error_info_str
                    content += "\n\n---\n\n"
                    content += "## Analysis Result\n\n"
                    content += result.final_output
                    content += "\n\n---\n\n"
                    content += "## Pipeline Steps\n\n"
                    for step in result.steps:
                        content += f"### {step['step_name']} ({step['agent']})\n\n"
                        content += f"{step['output']}\n\n"
                    
                    saved_path = save_text_file_with_versioning(filename_path, content)
                    self.console.print(f"[green]✓ Saved to {saved_path}[/green]")
            
            # Option to create queue prompt
            if saved_path:
                create_queue = questionary.confirm(
                    "\nCreate a prompt from this analysis to distribute via job queue?",
                    default=False,
                    style=custom_style
                ).ask()
                if create_queue:
                    error_info_str_final = error_info_str if isinstance(error_info_str, str) else json.dumps(error_info_list, indent=2)
                    self._create_queue_prompt_from_analysis(
                        error_info_str_final,
                        result.final_output,
                        saved_path
                    )
        except (AgentError, APIError, ConfigurationError) as e:
            self.console.print(f"\n[red]Error analysis failed: {e}[/red]")
            if hasattr(e, 'original_error') and e.original_error:
                self.console.print(f"[dim]Original error: {e.original_error}[/dim]")
        except Exception as e:
            self.console.print(f"\n[red]Unexpected Error: {e}[/red]")
            import traceback
            self.console.print(f"[dim]{traceback.format_exc()}[/dim]")
        
        questionary.press_any_key_to_continue().ask()
