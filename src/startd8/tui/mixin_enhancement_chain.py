"""EnhancementChainMixin: extracted from tui_improved.py ImprovedTUI (Pass B)."""

from ._shared import *  # noqa: F401,F403

class EnhancementChainMixin:
    def document_enhancement_chain_menu(self):
        """Document Enhancement Chain - sequential multi-agent document enhancement"""
        self.show_header("Document Enhancement Chain")
        
        # Show workflow intro with help
        if self.workflow_helper and self.workflow_helper.has_workflow_help("enhancement_chain"):
            self.workflow_helper.show_workflow_intro("enhancement_chain")
        else:
            self.console.print(Panel(
                "[bold cyan]Document Enhancement Chain[/bold cyan]\n\n"
                "Chain multiple AI agents to sequentially enhance a single document.\n"
                "Each agent receives the output from the previous agent, creating a\n"
                "refinement pipeline.\n\n"
                "[bold]Example Flow:[/bold]\n"
                "  Original Document\n"
                "    ↓\n"
                "  GPT-4 Enhancement (adds structure)\n"
                "    ↓\n"
                "  Claude Refinement (improves clarity)\n"
                "    ↓\n"
                "  Composer Polish (final touches)\n\n"
                "[bold]Use Cases:[/bold]\n"
                "  • Progressively refine design documents\n"
                "  • Apply different AI strengths sequentially\n"
                "  • Create high-quality documentation through iteration",
                border_style="cyan"
            ))
        
        # Offer to see examples
        show_examples = questionary.confirm(
            "\nWould you like to see workflow examples?",
            default=False,
            style=custom_style
        ).ask()
        
        if show_examples and self.workflow_helper:
            self.workflow_helper.show_workflow_examples("enhancement_chain")
        
        self.console.print()
        if not questionary.confirm("Continue with enhancement chain?", default=True, style=custom_style).ask():
            return
        
        self._run_document_enhancement_chain()

    def _run_document_enhancement_chain(self):
        """Run the document enhancement chain workflow"""
        
        # Step 1: Select document
        self.console.print("\n[bold cyan]Step 1: Select Document[/bold cyan]\n")
        doc_path = self._select_document_for_enhancement()
        if not doc_path:
            return
        
        # Step 2: Get enhancement instructions (optional)
        self.console.print("\n[bold cyan]Step 2: Enhancement Instructions[/bold cyan]\n")
        instructions = self._get_enhancement_instructions()
        
        # Step 3: Select and order agents
        self.console.print("\n[bold cyan]Step 3: Select Agents[/bold cyan]\n")
        agent_configs = self._select_agents_for_chain()
        if not agent_configs:
            self.console.print("[yellow]No agents selected. Aborting.[/yellow]")
            questionary.press_any_key_to_continue().ask()
            return
        
        # Step 4: Configure error handling
        self.console.print("\n[bold cyan]Step 4: Error Handling[/bold cyan]\n")
        error_handling = self._select_error_handling()
        
        # Step 5: Configure output
        self.console.print("\n[bold cyan]Step 5: Output Configuration[/bold cyan]\n")
        save_intermediate = questionary.confirm(
            "Save intermediate results from each agent?",
            default=True,
            style=custom_style
        ).ask()
        
        # Show summary and confirm
        self.console.print("\n")
        self._show_enhancement_summary(
            doc_path=doc_path,
            instructions=instructions,
            agent_configs=agent_configs,
            error_handling=error_handling,
            save_intermediate=save_intermediate
        )
        
        if not questionary.confirm("\nProceed with enhancement?", default=True, style=custom_style).ask():
            return
        
        # Build configuration
        config = DocumentEnhancementConfig(
            source_document=doc_path,
            enhancement_instructions=instructions,
            agents=agent_configs,
            save_intermediate=save_intermediate,
            on_error=error_handling
        )
        
        # Execute chain
        result = self._execute_enhancement_chain(config)
        
        # Review results
        if result:
            self._review_enhancement_results(result, doc_path)

    def _select_document_for_enhancement(self) -> Optional[Path]:
        """Select a document for enhancement"""
        default_dir = str(Path.home() / "Documents")
        
        self.console.print(Panel(
            "Select a markdown document to enhance.\n"
            "The original file will NOT be modified.",
            border_style="cyan"
        ))
        
        # Use safe path input helper
        doc_path_str = self._safe_path_input(
            "Select document:",
            default=default_dir,
            only_directories=False,
            style=custom_style
        )
        
        if not doc_path_str:
            return None
        
        doc_path = Path(doc_path_str).expanduser().resolve()
        
        if not doc_path.exists():
            self.console.print(f"[red]File not found: {doc_path}[/red]")
            return None
        
        if not doc_path.is_file():
            self.console.print("[red]Please select a file, not a directory[/red]")
            return None
        
        # Preview document
        if questionary.confirm("Preview document?", default=False, style=custom_style).ask():
            self._preview_document(doc_path)
        
        return doc_path

    def _preview_document(self, doc_path: Path):
        """Preview a document (smart preview: metadata + first 50 lines)"""
        try:
            with open(doc_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            lines = content.split('\n')
            num_lines = len(lines)
            file_size = len(content)
            
            # Extract headings
            headings = [line.strip() for line in lines if line.strip().startswith('#')]
            num_headings = len(headings)
            
            # Show metadata
            self.console.print(Panel(
                f"[bold]File:[/bold] {doc_path.name}\n"
                f"[bold]Size:[/bold] {file_size:,} bytes\n"
                f"[bold]Lines:[/bold] {num_lines:,}\n"
                f"[bold]Sections:[/bold] {num_headings}\n\n"
                f"[bold]First {min(num_headings, 5)} headings:[/bold]\n" +
                '\n'.join(f"  {h}" for h in headings[:5]),
                title="Document Preview",
                border_style="cyan"
            ))
            
            # Show first 50 lines
            preview_lines = min(50, num_lines)
            self.console.print(f"\n[dim]First {preview_lines} lines:[/dim]\n")
            self.console.print('\n'.join(lines[:preview_lines]))
            
            if num_lines > preview_lines:
                self.console.print(f"\n[dim]... ({num_lines - preview_lines} more lines)[/dim]")
            
            self.console.print()
            questionary.press_any_key_to_continue().ask()
            
        except Exception as e:
            self.console.print(f"[red]Failed to preview document: {e}[/red]")

    def _get_enhancement_instructions(self) -> Optional[str]:
        """Get optional enhancement instructions from user"""
        self.console.print(Panel(
            "[bold]Enhancement Instructions[/bold]\n\n"
            "Provide instructions on how the document should be enhanced.\n\n"
            "[bold]Examples:[/bold]\n"
            "  • 'Add accessibility section with WCAG guidelines'\n"
            "  • 'Improve CSS animations and add code examples'\n"
            "  • 'Expand the testing section with more detail'\n"
            "  • 'Add API documentation and usage examples'\n\n"
            "[dim]Leave empty to let agents use their own judgment.[/dim]",
            title="Instructions",
            border_style="cyan"
        ))
        
        instructions = questionary.text(
            "Enhancement instructions (optional, press Enter to skip):",
            style=custom_style,
            multiline=True
        ).ask()
        
        return instructions.strip() if instructions else None

    def _select_agents_for_chain(self) -> List[EnhancementAgentConfig]:
        """Interactive agent selection and ordering"""
        
        # Get available agents
        available_agents = self._get_available_agents_for_enhancement()
        
        if not available_agents:
            self.console.print("[red]No agents available. Please configure API keys first.[/red]")
            return []
        
        # Display agents
        agent_table = Table(title="Available Agents")
        agent_table.add_column("Agent", style="cyan")
        agent_table.add_column("Status", style="green")
        agent_table.add_column("Model", style="dim")
        
        for agent_info in available_agents:
            status = "✓ Available" if agent_info['available'] else "✗ Not configured"
            agent_table.add_row(
                agent_info['name'],
                status,
                agent_info.get('model', 'N/A')
            )
        
        self.console.print(agent_table)
        self.console.print()
        
        # Multi-select agents
        available_names = [a['name'] for a in available_agents if a['available']]
        
        if not available_names:
            self.console.print("[red]No agents are available. Please configure API keys.[/red]")
            return []
        
        selected_names = questionary.checkbox(
            "Select agents for enhancement chain (select at least one):",
            choices=available_names,
            style=custom_style
        ).ask()
        
        if not selected_names:
            return []
        
        # Order agents
        self.console.print("\n[bold]Order the selected agents[/bold]")
        self.console.print("[dim]The order determines the sequence of enhancement.[/dim]\n")
        
        ordered_agents = []
        remaining = selected_names.copy()
        
        while remaining:
            if len(remaining) == 1:
                ordered_agents.append(remaining[0])
                break
            
            next_agent = questionary.select(
                f"Select agent #{len(ordered_agents) + 1} (of {len(selected_names)}):",
                choices=remaining,
                style=custom_style
            ).ask()
            
            if not next_agent:
                return []
            
            ordered_agents.append(next_agent)
            remaining.remove(next_agent)
        
        # Show chain preview
        self.console.print("\n[bold green]Enhancement Chain:[/bold green]")
        for i, agent_name in enumerate(ordered_agents, 1):
            arrow = "  ↓" if i < len(ordered_agents) else ""
            self.console.print(f"  {i}. {agent_name}{arrow}")
        self.console.print()
        
        # Create AgentConfig objects
        agent_configs = []
        for order, agent_name in enumerate(ordered_agents):
            agent_instance = self._create_agent_instance(agent_name)
            agent_configs.append(EnhancementAgentConfig(
                agent_name=agent_name,
                agent_instance=agent_instance,
                step_name=f"{agent_name}-enhancement",
                order=order
            ))
        
        return agent_configs

    def _get_available_agents_for_enhancement(self) -> List[Dict[str, Any]]:
        """Get list of available agents for enhancement"""
        agents = []
        
        # Built-in agents
        try:
            claude = ClaudeAgent()
            agents.append({
                'name': 'claude',
                'available': True,
                'model': claude.model,
                'type': 'builtin'
            })
        except:
            agents.append({
                'name': 'claude',
                'available': False,
                'model': 'N/A',
                'type': 'builtin'
            })
        
        try:
            gpt4 = GPT4Agent()
            agents.append({
                'name': 'gpt4',
                'available': True,
                'model': gpt4.model,
                'type': 'builtin'
            })
        except:
            agents.append({
                'name': 'gpt4',
                'available': False,
                'model': 'N/A',
                'type': 'builtin'
            })
        
        try:
            composer = ComposerAgent()
            agents.append({
                'name': 'composer',
                'available': True,
                'model': composer.model,
                'type': 'builtin'
            })
        except:
            agents.append({
                'name': 'composer',
                'available': False,
                'model': 'N/A',
                'type': 'builtin'
            })
        
        # Mock agent (always available)
        agents.append({
            'name': 'mock',
            'available': True,
            'model': 'mock-model',
            'type': 'builtin'
        })
        
        return agents

    def _create_agent_instance(self, agent_name: str) -> BaseAgent:
        """Create an agent instance by name"""
        if agent_name == 'claude':
            return ClaudeAgent()
        elif agent_name == 'gpt4':
            return GPT4Agent()
        elif agent_name == 'composer':
            return ComposerAgent()
        elif agent_name == 'mock':
            return MockAgent()
        else:
            raise ValueError(f"Unknown agent: {agent_name}")

    def _get_ready_agents(self) -> list:
        """Get list of agent IDs that are ready (configured and working)"""
        ready_agents = []

        # Use cached agent status if available, otherwise test
        if hasattr(self, 'agent_status') and self.agent_status:
            statuses = self.agent_status
        else:
            statuses = AgentConfigTester.test_all()

        for agent_id, status in statuses.items():
            if status.get('working'):
                ready_agents.append(agent_id)

        return ready_agents

    def chat_with_agent(self):
        """Interactive chat with a ready agent"""
        self.show_header("Chat with Agent")

        # Get ready agents
        ready_agents = self._get_ready_agents()

        if not ready_agents:
            self.console.print(Panel(
                "[yellow]No agents are currently ready.[/yellow]\n\n"
                "Please configure at least one agent with a valid API key.\n"
                "Use '🔑 Manage API Keys' or '🔧 Fix Agent Configuration Issues' to set up agents.",
                title="⚠️ No Ready Agents",
                border_style="yellow"
            ))
            questionary.press_any_key_to_continue().ask()
            return

        # Build agent choices with model info
        agent_choices = []
        for agent_id in ready_agents:
            status = self.agent_status.get(agent_id, {}) if hasattr(self, 'agent_status') else {}
            model = status.get('model', 'unknown')
            agent_choices.append(f"{agent_id} ({model})")

        agent_choices.append("← Back to Menu")

        # Select agent
        selection = questionary.select(
            "Select an agent to chat with:",
            choices=agent_choices,
            style=custom_style
        ).ask()

        if not selection or "Back" in selection:
            return

        # Extract agent ID from selection
        agent_id = selection.split(" (")[0]

        # Create agent instance
        try:
            agent = self._create_agent_instance(agent_id)
        except ValueError:
            # Try custom agent
            try:
                agent = self.agent_manager.create_agent_instance(agent_id)
            except Exception as e:
                self.console.print(f"[red]Failed to create agent: {e}[/red]")
                questionary.press_any_key_to_continue().ask()
                return

        # FR-10: opt-in agentic mode gives the chat real multi-turn memory (a persistent
        # AgenticSession), vs the legacy stateless single-shot path. Gated on STARTD8_TUI_AGENTIC +
        # the agent supporting tool use; legacy path is retained for everything else.
        from ..tui.agentic_chat import agentic_mode_enabled, cost_suffix, make_chat_session, reply

        use_agentic = agentic_mode_enabled(agent)
        chat_session = make_chat_session(agent) if use_agentic else None
        mode_note = "multi-turn memory" if use_agentic else "single-shot"

        # Chat header
        self.console.print(Panel(
            f"[bold cyan]Chatting with {agent_id}[/bold cyan]  [dim]({mode_note})[/dim]\n\n"
            "[dim]Type 'exit', 'quit', or 'back' to return to menu[/dim]",
            border_style="cyan"
        ))

        # Chat loop
        while True:
            self.console.print()
            user_input = questionary.text(
                "You > ",
                style=custom_style
            ).ask()

            if not user_input:
                continue

            if user_input.lower() in ['exit', 'quit', 'back']:
                break

            # Generate response
            try:
                with self.console.status("[bold cyan]Thinking...[/bold cyan]"):
                    if chat_session is not None:
                        result = reply(chat_session, user_input)  # async session via sync bridge
                        response, subtitle = result.text, cost_suffix(result)
                    else:
                        response, tokens_in, token_usage = agent.generate(user_input)
                        # Extract output tokens (handle both int and TokenUsage object)
                        tokens_out = token_usage.output if hasattr(token_usage, 'output') else token_usage
                        subtitle = f"tokens: {tokens_in} in / {tokens_out} out"

                # Display response with markdown rendering
                self.console.print(Panel(
                    Markdown(response),
                    title=f"[bold]{agent_id}[/bold]",
                    subtitle=f"[dim]{subtitle}[/dim]",
                    border_style="green"
                ))
            except Exception as e:
                self.console.print(Panel(
                    f"[red]Error: {e}[/red]",
                    title="⚠️ Generation Failed",
                    border_style="red"
                ))

        self.console.print("\n[cyan]Chat ended.[/cyan]\n")
        questionary.press_any_key_to_continue().ask()

    def _select_error_handling(self) -> ErrorHandling:
        """Select error handling strategy"""
        self.console.print(Panel(
            "[bold]Error Handling Strategy[/bold]\n\n"
            "If an agent fails during enhancement:\n\n"
            "[bold cyan]STOP:[/bold cyan] Stop the chain immediately and return partial results\n"
            "[bold yellow]RETRY:[/bold yellow] Retry the failed step once before stopping\n"
            "[bold green]SKIP:[/bold green] Skip the failed agent and continue with next one\n\n"
            "[dim]Recommended: STOP (safest option)[/dim]",
            border_style="cyan"
        ))
        
        choice = questionary.select(
            "Error handling strategy:",
            choices=[
                "STOP - Stop on first error (recommended)",
                "RETRY - Retry failed step once",
                "SKIP - Skip failed agents and continue"
            ],
            style=custom_style
        ).ask()
        
        if not choice:
            return ErrorHandling.STOP
        
        if "RETRY" in choice:
            return ErrorHandling.RETRY
        elif "SKIP" in choice:
            return ErrorHandling.SKIP
        else:
            return ErrorHandling.STOP

    def _show_enhancement_summary(
        self,
        doc_path: Path,
        instructions: Optional[str],
        agent_configs: List[EnhancementAgentConfig],
        error_handling: ErrorHandling,
        save_intermediate: bool
    ):
        """Show enhancement configuration summary"""
        
        # Build chain display
        chain_display = ""
        for i, config in enumerate(agent_configs, 1):
            arrow = "\n  ↓\n" if i < len(agent_configs) else ""
            chain_display += f"  {i}. {config.agent_name} ({config.agent_instance.model}){arrow}"
        
        instructions_display = instructions if instructions else "[dim]Let agents use their judgment[/dim]"
        
        self.console.print(Panel(
            f"[bold]Configuration Summary[/bold]\n\n"
            f"[bold]Document:[/bold] {doc_path.name}\n"
            f"[bold]Path:[/bold] {doc_path}\n\n"
            f"[bold]Instructions:[/bold]\n{instructions_display}\n\n"
            f"[bold]Enhancement Chain:[/bold]\n{chain_display}\n\n"
            f"[bold]Error Handling:[/bold] {error_handling.value.upper()}\n"
            f"[bold]Save Intermediate:[/bold] {'Yes' if save_intermediate else 'No'}",
            title="Ready to Enhance",
            border_style="green"
        ))

    def _execute_enhancement_chain(
        self,
        config: DocumentEnhancementConfig
    ) -> Optional:
        """Execute the enhancement chain with progress display"""
        
        self.console.print("\n")
        self.show_header("Executing Enhancement Chain")
        
        # Create chain
        chain = DocumentEnhancementChain(config, self.framework)
        
        # Progress tracking
        current_step = [0]  # Use list for mutable closure
        total_steps = len(config.agents)
        
        def on_step_start(step_num: int, total: int, agent_name: str):
            current_step[0] = step_num
            self.console.print(f"\n[bold cyan]Step {step_num}/{total}: {agent_name}[/bold cyan]")
            self.console.print(f"[dim]Enhancing document...[/dim]")
        
        def on_step_complete(step_num: int, total: int, agent_name: str, result):
            if result.success:
                tokens = result.token_usage.total if result.token_usage else 0
                cost = result.token_usage.cost_estimate if result.token_usage else 0
                self.console.print(
                    f"[green]✓ Complete[/green] "
                    f"({result.response_time_ms}ms, {tokens:,} tokens, ${cost:.4f})"
                )
            else:
                self.console.print(f"[red]✗ Failed: {result.error}[/red]")
        
        # Execute with callbacks
        try:
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=self.console
            ) as progress:
                task = progress.add_task("Running enhancement chain...", total=total_steps)
                
                result = chain.run(
                    on_step_start=on_step_start,
                    on_step_complete=on_step_complete,
                    on_progress=lambda current, total: progress.update(task, completed=current)
                )
            
            return result
            
        except (AgentError, APIError, ConfigurationError) as e:
            # Log user-friendly errors properly for error analysis workflow
            from ..logging_config import get_logger
            logger = get_logger(__name__)
            logger.error(
                f"Document enhancement chain failed: {e}",
                exc_info=False,  # Don't log traceback for user-friendly errors
                extra={
                    "pipeline_name": "document_enhancement_chain",
                    "agent_name": getattr(e, 'agent_name', None),
                    "error_type": type(e).__name__
                }
            )
            self.console.print(f"\n[red]Document enhancement chain failed: {e}[/red]")
            if hasattr(e, 'original_error') and e.original_error:
                self.console.print(f"[dim]Original error: {e.original_error}[/dim]")
            questionary.press_any_key_to_continue().ask()
            return None
        except Exception as e:
            # Log unexpected errors with full traceback for debugging
            from ..logging_config import get_logger
            logger = get_logger(__name__)
            logger.error(
                f"Document enhancement chain failed: {e}",
                exc_info=True,  # Log full traceback for unexpected errors
                extra={
                    "pipeline_name": "document_enhancement_chain",
                    "error_type": type(e).__name__
                }
            )
            self.console.print(f"\n[red]Unexpected Error: {e}[/red]")
            import traceback
            self.console.print(f"[dim]{traceback.format_exc()}[/dim]")
            questionary.press_any_key_to_continue().ask()
            return None

    def _review_enhancement_results(self, result, original_path: Path):
        """Display and review enhancement results"""
        self.console.print("\n")
        self.show_header("Enhancement Results")
        
        # Summary table
        summary_table = Table(title="Enhancement Summary")
        summary_table.add_column("Metric", style="cyan")
        summary_table.add_column("Value", style="green")
        
        summary_table.add_row("Total Steps", str(len(result.steps)))
        summary_table.add_row("Successful", str(result.steps_completed))
        summary_table.add_row("Failed", str(result.steps_failed))
        summary_table.add_row("Total Time", f"{result.total_time_ms:,}ms ({result.total_time_ms/1000:.1f}s)")
        summary_table.add_row("Total Tokens", f"{result.total_tokens:,}")
        summary_table.add_row("Total Cost", f"${result.total_cost:.4f}")
        summary_table.add_row("Overall Status", "✓ Success" if result.success else "✗ Partial/Failed")
        
        self.console.print(summary_table)
        self.console.print()
        
        # Step-by-step results
        steps_table = Table(title="Step Results")
        steps_table.add_column("Step", style="cyan", justify="center")
        steps_table.add_column("Agent", style="green")
        steps_table.add_column("Model", style="dim")
        steps_table.add_column("Time", style="dim", justify="right")
        steps_table.add_column("Tokens", style="dim", justify="right")
        steps_table.add_column("Cost", style="dim", justify="right")
        steps_table.add_column("Status", style="green", justify="center")
        
        for step in result.steps:
            tokens = step.token_usage.total if step.token_usage else 0
            cost = step.token_usage.cost_estimate if step.token_usage else 0
            
            steps_table.add_row(
                str(step.step_number),
                step.agent_name,
                step.model,
                f"{step.response_time_ms:,}ms",
                f"{tokens:,}",
                f"${cost:.4f}",
                "✓" if step.success else "✗"
            )
        
        self.console.print(steps_table)
        self.console.print()
        
        # Output location
        if result.output_path:
            self.console.print(Panel(
                f"[bold green]✓ Enhanced document saved![/bold green]\n\n"
                f"[bold]Final output:[/bold]\n{result.output_path}\n\n"
                f"[bold]Output directory:[/bold]\n{result.output_path.parent}\n\n"
                + (f"[bold]Intermediate results:[/bold]\nSaved in step subdirectories" if result.config.save_intermediate else ""),
                title="Output Location",
                border_style="green"
            ))
        
        self.console.print()
        
        # Actions
        while True:
            action = questionary.select(
                "What would you like to do?",
                choices=[
                    "📄 Preview final document",
                    "📂 Open output directory",
                    "📊 View detailed metrics",
                    "← Done"
                ],
                style=custom_style
            ).ask()
            
            if not action or "Done" in action:
                break
            
            if "Preview" in action:
                self._preview_document_content(result.final_document)
            elif "Open output" in action:
                import subprocess
                subprocess.run(["open", str(result.output_path.parent)])
            elif "detailed metrics" in action:
                self._show_detailed_step_metrics(result)

    def _preview_document_content(self, content: str):
        """Preview document content"""
        lines = content.split('\n')
        num_lines = len(lines)
        preview_lines = min(100, num_lines)
        
        self.console.print(Panel(
            f"[bold]Document Preview[/bold]\n"
            f"[dim]Showing first {preview_lines} of {num_lines} lines[/dim]",
            border_style="cyan"
        ))
        
        self.console.print()
        self.console.print('\n'.join(lines[:preview_lines]))
        
        if num_lines > preview_lines:
            self.console.print(f"\n[dim]... ({num_lines - preview_lines} more lines)[/dim]")
        
        self.console.print()
        questionary.press_any_key_to_continue().ask()

    def _show_detailed_step_metrics(self, result):
        """Show detailed metrics for each step"""
        self.console.print("\n")
        self.show_header("Detailed Step Metrics")
        
        for step in result.steps:
            status_color = "green" if step.success else "red"
            status_text = "SUCCESS" if step.success else f"FAILED: {step.error}"
            
            tokens_text = "N/A"
            cost_text = "N/A"
            
            if step.token_usage:
                tokens_text = (
                    f"Input: {step.token_usage.input:,}, "
                    f"Output: {step.token_usage.output:,}, "
                    f"Total: {step.token_usage.total:,}"
                )
                cost_text = f"${step.token_usage.cost_estimate:.6f}"
            
            self.console.print(Panel(
                f"[bold]Agent:[/bold] {step.agent_name}\n"
                f"[bold]Model:[/bold] {step.model}\n"
                f"[bold]Status:[/bold] [{status_color}]{status_text}[/{status_color}]\n"
                f"[bold]Response Time:[/bold] {step.response_time_ms:,}ms ({step.response_time_ms/1000:.2f}s)\n"
                f"[bold]Tokens:[/bold] {tokens_text}\n"
                f"[bold]Cost:[/bold] {cost_text}\n"
                f"[bold]Timestamp:[/bold] {step.timestamp.strftime('%Y-%m-%d %H:%M:%S')}",
                title=f"Step {step.step_number}",
                border_style=status_color
            ))
            self.console.print()
        
        questionary.press_any_key_to_continue().ask()
