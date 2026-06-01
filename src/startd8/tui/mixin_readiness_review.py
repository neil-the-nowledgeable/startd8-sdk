"""ReadinessReviewMixin: extracted from tui_improved.py ImprovedTUI (Pass B)."""

from ._shared import *  # noqa: F401,F403

class ReadinessReviewMixin:
    def test_all_agents_readiness(self):
        """Test all available agents by asking a simple question to verify readiness"""
        self.show_header("Test All Agents Readiness")
        
        self.console.print(Panel(
            "🧪 [bold cyan]Agent Readiness Test[/bold cyan]\n\n"
            "This workflow tests all available agents by asking:\n"
            "[bold]'What is the capital of France?'[/bold]\n\n"
            "This verifies that each agent:\n"
            "  • Can be instantiated\n"
            "  • Can connect to its API\n"
            "  • Can generate responses\n"
            "  • Returns expected results",
            border_style="cyan"
        ))
        
        # Confirm before running
        confirm = questionary.confirm(
            "\nThis will test all available agents. Continue?",
            default=True,
            style=custom_style
        ).ask()
        
        if not confirm:
            return
        
        # Get all available agents
        self.console.print("\n[cyan]Gathering available agents...[/cyan]\n")
        
        # Ensure agent status is up to date
        if self.agent_status is None:
            self.agent_status = AgentConfigTester.test_all()
        
        custom_agents = self.agent_manager.list_agents()
        all_agents = self._build_unified_agent_list(custom_agents, set())
        
        # Filter to only Ready agents
        ready_agents = [agent for agent in all_agents if agent.get('available', False)]
        
        if not ready_agents:
            self.console.print("[red]No ready agents available to test.[/red]")
            self.console.print("[yellow]Please configure at least one agent first.[/yellow]")
            questionary.press_any_key_to_continue().ask()
            return
        
        self.console.print(f"[green]Found {len(ready_agents)} agent(s) to test[/green]\n")
        
        # Test prompt
        test_prompt = "What is the capital of France?"
        expected_answer = "Paris"  # For validation
        
        # Results storage
        results = []
        
        # Test each agent
        with self.console.status("[bold green]Testing agents...[/bold green]") as status:
            for idx, agent_info in enumerate(ready_agents, 1):
                agent_name = agent_info.get('name', 'Unknown')
                agent_model = agent_info.get('model', 'unknown')
                agent_type = agent_info.get('type', 'unknown')
                agent_icon = agent_info.get('icon', '🤖')
                
                status.update(f"[bold green]Testing {agent_name} ({idx}/{len(ready_agents)})...[/bold green]")
                
                result = {
                    'name': agent_name,
                    'model': agent_model,
                    'type': agent_type,
                    'icon': agent_icon,
                    'success': False,
                    'response': None,
                    'response_time_ms': None,
                    'error': None,
                    'answer_correct': False
                }
                
                try:
                    # Create agent instance based on agent type
                    agent_instance = None
                    
                    if agent_info.get('type') == 'builtin':
                        # Handle built-in agents
                        builtin_type = agent_info.get('builtin_type')
                        try:
                            if builtin_type == 'mock':
                                agent_instance = MockAgent(name="mock", model="mock-model")
                            elif builtin_type == 'claude':
                                agent_instance = ClaudeAgent()
                            elif builtin_type == 'gpt4':
                                agent_instance = GPT4Agent()
                            else:
                                result['error'] = f"Unknown builtin type: {builtin_type}"
                                results.append(result)
                                continue
                        except Exception as e:
                            result['error'] = f"Failed to create builtin agent ({builtin_type}): {str(e)}"
                            import traceback
                            result['error_traceback'] = traceback.format_exc()
                            results.append(result)
                            continue
                    else:
                        # Handle custom agents - need to get the custom_config
                        custom_config = agent_info.get('custom_config')
                        if not custom_config:
                            # Try to find in custom_agents list
                            for custom_agent in custom_agents:
                                if custom_agent.get('name') == agent_name:
                                    custom_config = custom_agent
                                    break
                        
                        if custom_config:
                            try:
                                agent_instance = self.agent_manager.create_agent_instance(custom_config)
                            except Exception as e:
                                result['error'] = f"Failed to create custom agent: {str(e)}"
                                import traceback
                                result['error_traceback'] = traceback.format_exc()
                                results.append(result)
                                continue
                        else:
                            result['error'] = f"Could not find custom_config for agent '{agent_name}'. Agent info keys: {list(agent_info.keys())}"
                            results.append(result)
                            continue
                    
                    if not agent_instance:
                        result['error'] = "Agent instance creation returned None"
                        results.append(result)
                        continue
                    
                    # Generate response
                    import time
                    start_time = time.time()
                    try:
                        response_tuple = agent_instance.generate(test_prompt)
                    except Exception as e:
                        result['error'] = f"Failed to generate response: {str(e)}"
                        import traceback
                        result['error_traceback'] = traceback.format_exc()
                        results.append(result)
                        continue
                    
                    end_time = time.time()
                    
                    # Extract response text (generate returns tuple: (response_text, response_time_ms, token_usage))
                    if isinstance(response_tuple, tuple) and len(response_tuple) >= 1:
                        response_text = response_tuple[0]
                        # Use agent's reported time if available, otherwise calculate our own
                        if len(response_tuple) >= 2 and response_tuple[1]:
                            result['response_time_ms'] = response_tuple[1]
                        else:
                            result['response_time_ms'] = int((end_time - start_time) * 1000)
                    elif isinstance(response_tuple, str):
                        # Sometimes generate might return just a string
                        response_text = response_tuple
                        result['response_time_ms'] = int((end_time - start_time) * 1000)
                    else:
                        response_text = str(response_tuple)
                        result['response_time_ms'] = int((end_time - start_time) * 1000)
                        result['error'] = f"Unexpected response format: {type(response_tuple)}"
                    
                    result['response'] = response_text
                    result['success'] = True
                    
                    # Check if answer is correct (case-insensitive, check if "Paris" is in response)
                    response_lower = response_text.lower()
                    if 'paris' in response_lower:
                        result['answer_correct'] = True
                    
                except Exception as e:
                    result['error'] = f"Unexpected error: {str(e)}"
                    result['success'] = False
                    # Include traceback in detailed error for debugging
                    import traceback
                    result['error_traceback'] = traceback.format_exc()
                
                results.append(result)
        
        # Display results
        self.console.print("\n[bold cyan]Test Results[/bold cyan]\n")
        
        # Summary table
        summary_table = Table(title="Agent Readiness Test Summary", show_header=True)
        summary_table.add_column("", justify="center", width=3)  # Icon
        summary_table.add_column("Agent", style="bold cyan", width=25)
        summary_table.add_column("Model", style="cyan", width=20)
        summary_table.add_column("Status", justify="center", width=12)
        summary_table.add_column("Time", justify="right", width=10)
        summary_table.add_column("Answer", justify="center", width=10)
        
        passed_count = 0
        failed_count = 0
        
        for result in results:
            if result['success']:
                status_text = "[green]✓ PASS[/green]"
                passed_count += 1
            else:
                status_text = "[red]✗ FAIL[/red]"
                failed_count += 1
            
            time_text = f"{result['response_time_ms']}ms" if result['response_time_ms'] else "N/A"
            
            if result['answer_correct']:
                answer_text = "[green]✓ Correct[/green]"
            elif result['success']:
                answer_text = "[yellow]⚠ Wrong[/yellow]"
            else:
                answer_text = "[dim]N/A[/dim]"
            
            summary_table.add_row(
                result['icon'],
                result['name'],
                result['model'],
                status_text,
                time_text,
                answer_text
            )
        
        self.console.print(summary_table)
        
        # Summary statistics
        self.console.print(f"\n[bold]Summary:[/bold]")
        self.console.print(f"  [green]Passed:[/green] {passed_count}/{len(results)}")
        self.console.print(f"  [red]Failed:[/red] {failed_count}/{len(results)}")
        
        if passed_count > 0:
            avg_time = sum(r['response_time_ms'] for r in results if r['response_time_ms']) / passed_count
            self.console.print(f"  [cyan]Average Response Time:[/cyan] {int(avg_time)}ms")
        
        # Always show errors for failed agents
        failed_results = [r for r in results if not r['success']]
        if failed_results:
            self.console.print(f"\n[yellow]⚠️  {len(failed_results)} agent(s) failed. Showing errors:[/yellow]\n")
            for result in failed_results:
                self.console.print(Panel(
                    f"[bold]Agent:[/bold] {result['name']}\n"
                    f"[bold]Model:[/bold] {result['model']}\n"
                    f"[bold]Type:[/bold] {result['type']}\n"
                    + (f"[bold]Error:[/bold] {result['error']}\n" if result['error'] else "[bold]Error:[/bold] Unknown error\n")
                    + (f"\n[bold]Traceback:[/bold]\n{result.get('error_traceback', '')}\n" if result.get('error_traceback') else ""),
                    title=f"✗ {result['name']} - FAILED",
                    border_style="red"
                ))
                self.console.print()
        
        # Detailed results
        show_details = questionary.confirm(
            "\nShow detailed results for each agent?",
            default=False,
            style=custom_style
        ).ask()
        
        if show_details:
            self.console.print("\n[bold cyan]Detailed Results[/bold cyan]\n")
            
            for result in results:
                status_color = "green" if result['success'] else "red"
                status_icon = "✓" if result['success'] else "✗"
                
                panel_content = (
                    f"[bold]Agent:[/bold] {result['name']}\n"
                    f"[bold]Model:[/bold] {result['model']}\n"
                    f"[bold]Type:[/bold] {result['type']}\n"
                    f"[bold]Status:[/bold] {'[green]SUCCESS[/green]' if result['success'] else '[red]FAILED[/red]'}\n"
                )
                
                if result['success']:
                    panel_content += (
                        (f"[bold]Response Time:[/bold] {result['response_time_ms']}ms\n" if result['response_time_ms'] else "")
                        + (f"[bold]Answer Correct:[/bold] {'[green]Yes[/green]' if result['answer_correct'] else '[yellow]No[/yellow]'}\n")
                        + (f"[bold]Response:[/bold]\n{result['response'][:500]}{'...' if len(result['response']) > 500 else ''}\n" if result['response'] else "")
                    )
                else:
                    panel_content += (
                        (f"[bold]Error:[/bold] {result['error']}\n" if result['error'] else "[bold]Error:[/bold] Unknown error\n")
                        + (f"\n[bold]Traceback:[/bold]\n{result.get('error_traceback', '')}\n" if result.get('error_traceback') else "")
                    )
                
                self.console.print(Panel(
                    panel_content,
                    title=f"{status_icon} {result['name']}",
                    border_style=status_color
                ))
                self.console.print()
        
        questionary.press_any_key_to_continue().ask()

    def critical_review_workflow(self):
        """Critical Review Workflow - Multiple agents review design documents"""
        self.show_header("Critical Review Workflow")
        
        self.console.print(Panel(
            "🔍 [bold cyan]Critical Review Workflow[/bold cyan]\n\n"
            "Multiple agents independently review design documents and create\n"
            "detailed analysis reports.\n\n"
            "Each agent will analyze:\n"
            "  • What is good\n"
            "  • What is bad\n"
            "  • What needs more or less of\n"
            "  • Suggestions for improvement\n\n"
            "Each review is saved as a separate .md file.",
            border_style="cyan"
        ))
        
        # 1. Select input method (file or folder)
        input_method = questionary.select(
            "\nChoose input method:",
            choices=[
                "📄 Single design document",
                "📁 Folder of design documents",
                "← Cancel"
            ],
            style=custom_style
        ).ask()
        
        if not input_method or "Cancel" in input_method:
            return
        
        document_files = []
        
        if "Single" in input_method:
            file_path = self._safe_path_input(
                "Path to design document:",
                only_directories=False,
                style=custom_style
            )
            
            if not file_path:
                return
            
            doc_path = Path(file_path).expanduser()
            if not doc_path.exists():
                self.console.print(f"[red]File not found: {doc_path}[/red]")
                questionary.press_any_key_to_continue().ask()
                return
            
            if not doc_path.is_file():
                self.console.print(f"[red]Path is not a file: {doc_path}[/red]")
                questionary.press_any_key_to_continue().ask()
                return
            
            document_files = [doc_path]
        else:
            # Folder of documents
            folder_path = self._safe_path_input(
                "Path to folder containing design documents:",
                only_directories=True,
                style=custom_style
            )
            
            if not folder_path:
                return
            
            folder = Path(folder_path).expanduser()
            if not folder.exists():
                self.console.print(f"[red]Folder not found: {folder}[/red]")
                questionary.press_any_key_to_continue().ask()
                return
            
            if not folder.is_dir():
                self.console.print(f"[red]Path is not a folder: {folder}[/red]")
                questionary.press_any_key_to_continue().ask()
                return
            
            # Find all .md files in the folder
            document_files = list(folder.rglob("*.md"))
            
            if not document_files:
                self.console.print(f"[yellow]No .md files found in {folder}[/yellow]")
                questionary.press_any_key_to_continue().ask()
                return
            
            # Filter out common non-design files
            exclude_patterns = ["README", "CHANGELOG", "LICENSE", "index", "summary", "consolidated"]
            document_files = [
                f for f in document_files
                if not any(pattern.lower() in f.name.lower() for pattern in exclude_patterns)
            ]
            
            if not document_files:
                self.console.print(f"[yellow]No design documents found (filtered out common files)[/yellow]")
                questionary.press_any_key_to_continue().ask()
                return
        
        self.console.print(f"\n[green]Found {len(document_files)} document(s) to review[/green]\n")
        
        # 2. Select agents for review
        self.console.print("[bold]Select Agents for Critical Review[/bold]\n")
        
        ready_agents = self._get_ready_agents_for_selection()
        if not ready_agents:
            self.console.print("[red]No ready agents available. Please configure agents first.[/red]")
            questionary.press_any_key_to_continue().ask()
            return
        
        # Display ready agents table
        agent_table = Table(title="Available Agents (Ready Status)", show_header=True)
        agent_table.add_column("", justify="center", width=3)
        agent_table.add_column("Agent", style="bold cyan")
        agent_table.add_column("Model", style="cyan")
        agent_table.add_column("Type", style="magenta")
        
        for agent in ready_agents:
            agent_type = "Built-in" if agent['type'] == 'builtin' else "User added"
            agent_table.add_row(
                agent['icon'],
                agent['name'],
                agent['model'],
                agent_type
            )
        
        self.console.print(agent_table)
        self.console.print()
        
        # Build agent choices
        agent_choices = []
        for agent in ready_agents:
            agent_choices.append(f"{agent['icon']} {agent['name']} ({agent['model']})")
        
        self.console.print("[dim]💡 Use SPACE to select/deselect agents, ENTER to confirm[/dim]\n")
        
        selected_agents = None
        while True:
            selected_agents = questionary.checkbox(
                "Select agents to perform critical review:",
                choices=agent_choices,
                style=custom_style,
                instruction="(Press SPACE to select, ENTER to confirm)"
            ).ask()
            
            # Handle cancellation (Ctrl+C)
            if selected_agents is None:
                self.console.print("[yellow]Cancelled.[/yellow]")
                return
            
            # Validate that we got a list (questionary.checkbox should always return a list)
            if not isinstance(selected_agents, list):
                self.console.print(f"[red]Error: Unexpected return type from checkbox: {type(selected_agents)}[/red]")
                questionary.press_any_key_to_continue().ask()
                return
            
            # Check if any agents were selected
            if len(selected_agents) == 0:
                self.console.print("\n[yellow]⚠️  No agents selected. At least one agent must be selected.[/yellow]\n")
                retry = questionary.confirm("Select agents again?", default=True, style=custom_style).ask()
                if not retry:
                    return
                continue
            
            # Extract agent info from selections
            selected_agent_infos = []
            for agent_choice in selected_agents:
                # Parse "Icon Name (model)" format
                name_part = agent_choice.split(" (")[0].strip()
                parts = name_part.split()
                if len(parts) > 1:
                    agent_name = " ".join(parts[1:])
                else:
                    agent_name = name_part
                
                # Find matching agent
                for agent in ready_agents:
                    if agent['name'] == agent_name:
                        selected_agent_infos.append(agent)
                        break
            
            # Validate that we successfully matched at least one agent
            if len(selected_agent_infos) == 0:
                self.console.print("[red]Error: Could not match selected agents. Please try again.[/red]")
                retry = questionary.confirm("Select agents again?", default=True, style=custom_style).ask()
                if not retry:
                    return
                continue
            
            # Successfully selected and matched agents
            break
        
        self.console.print(f"\n[green]✓ Selected {len(selected_agent_infos)} agent(s)[/green]\n")
        
        # 3. Select output directory
        output_dir = questionary.text(
            "Output directory for review files:",
            default=str(Path.cwd() / "critical_reviews"),
            style=custom_style
        ).ask()
        
        if not output_dir:
            output_dir = Path.cwd() / "critical_reviews"
        else:
            output_dir = Path(output_dir).expanduser()
        
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # 4. Review prompt template
        review_prompt_template = """You are an expert technical reviewer and software architect. Your task is to critically review the following design document.

# Design Document

{document_content}

# Review Requirements

Please provide a comprehensive critical review that includes:

## 1. What is Good
Identify and highlight the strengths of this design document. What aspects are well thought out, clear, or innovative?

## 2. What is Bad
Identify weaknesses, gaps, ambiguities, or problematic aspects of the design. Be specific and constructive.

## 3. What Needs More or Less Of
- What areas need more detail, explanation, or coverage?
- What areas are too verbose or could be condensed?
- What topics are missing entirely?

## 4. Suggestions for Improvement
Provide specific, actionable suggestions for how to improve the design document. Include:
- Structural improvements
- Content additions or modifications
- Clarity enhancements
- Technical recommendations

Please be thorough, constructive, and specific in your analysis."""
        
        # 5. Process each document with each agent
        self.console.print(f"\n[cyan]Starting critical reviews...[/cyan]\n")
        self.console.print(f"  Documents: {len(document_files)}\n")
        self.console.print(f"  Agents: {len(selected_agent_infos)}\n")
        self.console.print(f"  Total reviews: {len(document_files) * len(selected_agent_infos)}\n")
        
        all_results = []

        try:
            from ..exceptions import AgentError, APIError, ConfigurationError

            # Pre-create all agent instances
            agent_instances = []
            for agent_info in selected_agent_infos:
                agent_name = agent_info.get('name', 'Unknown')
                agent_instance = None

                if agent_info.get('type') == 'builtin':
                    builtin_type = agent_info.get('builtin_type')
                    if builtin_type == 'mock':
                        agent_instance = MockAgent(name="mock", model="mock-model")
                    elif builtin_type == 'claude':
                        agent_instance = ClaudeAgent()
                    elif builtin_type == 'gpt4':
                        agent_instance = GPT4Agent()
                else:
                    custom_config = agent_info.get('custom_config')
                    if not custom_config:
                        custom_agents = self.agent_manager.list_agents()
                        for custom_agent in custom_agents:
                            if custom_agent.get('name') == agent_name:
                                custom_config = custom_agent
                                break

                    if custom_config:
                        agent_instance = self.agent_manager.create_agent_instance(custom_config)

                if agent_instance:
                    agent_instances.append(agent_instance)
                else:
                    self.console.print(f"[yellow]Warning: Could not create agent instance for {agent_name}[/yellow]")

            if not agent_instances:
                raise Exception("No agent instances could be created")

            # Use extracted workflow class for consistency
            workflow = CriticalReviewWorkflow()

            with self.console.status("[bold green]Processing reviews...[/bold green]") as status:
                def progress_callback(current, total, message):
                    status.update(f"[bold green]{message} ({current}/{total})...[/bold green]")

                workflow_result = workflow.run(
                    config={
                        "documents": [str(doc_file) for doc_file in document_files],
                        "output_dir": str(output_dir),
                        "review_template": review_prompt_template,
                    },
                    agents=agent_instances,
                    on_progress=progress_callback
                )

            # Map workflow result to TUI format
            if workflow_result.success and workflow_result.output:
                reviews = workflow_result.output.get("reviews", [])
                for review in reviews:
                    all_results.append({
                        'document': review.get('document', 'Unknown'),
                        'agent': review.get('agent', 'Unknown'),
                        'model': review.get('model', 'unknown'),
                        'output_path': Path(review.get('output_path', '')) if review.get('output_path') else None,
                        'error': review.get('error'),
                        'success': review.get('success', False)
                    })
            elif not workflow_result.success:
                raise Exception(workflow_result.error or "Critical review workflow failed")
            
            # 6. Display results summary
            self.console.print("\n[bold cyan]Review Complete![/bold cyan]\n")
            
            summary_table = Table(title="Review Results Summary", show_header=True)
            summary_table.add_column("Document", style="cyan", width=30)
            summary_table.add_column("Agent", style="bold cyan", width=25)
            summary_table.add_column("Status", justify="center", width=12)
            summary_table.add_column("Output File", style="green", width=40)
            
            successful_reviews = 0
            failed_reviews = 0
            
            for result in all_results:
                if result['success']:
                    status_text = "[green]✓ SUCCESS[/green]"
                    output_text = str(result['output_path'].name)
                    successful_reviews += 1
                else:
                    status_text = "[red]✗ FAILED[/red]"
                    output_text = f"[red]{result.get('error', 'Unknown error')[:35]}...[/red]"
                    failed_reviews += 1
                
                summary_table.add_row(
                    result['document'],
                    result['agent'],
                    status_text,
                    output_text
                )
            
            self.console.print(summary_table)
            
            self.console.print(f"\n[bold]Summary:[/bold]")
            self.console.print(f"  [green]Successful reviews:[/green] {successful_reviews}/{len(all_results)}")
            if failed_reviews > 0:
                self.console.print(f"  [red]Failed reviews:[/red] {failed_reviews}/{len(all_results)}")
            self.console.print(f"  [cyan]Output directory:[/cyan] {output_dir}")
            
            # Show failed reviews details if any
            failed_results = [r for r in all_results if not r['success']]
            if failed_results:
                self.console.print(f"\n[yellow]⚠️  {len(failed_results)} review(s) failed:[/yellow]\n")
                for result in failed_results:
                    self.console.print(
                        f"  • {result['document']} - {result['agent']}: "
                        f"[red]{result.get('error', 'Unknown error')}[/red]"
                    )
            
        except (AgentError, APIError, ConfigurationError) as e:
            self.console.print(f"\n[red]Critical review workflow failed: {e}[/red]")
            if hasattr(e, 'original_error') and e.original_error:
                self.console.print(f"[dim]Original error: {e.original_error}[/dim]")
        except Exception as e:
            self.console.print(f"\n[red]Unexpected Error: {e}[/red]")
            import traceback
            self.console.print(f"[dim]{traceback.format_exc()}[/dim]")
        
        questionary.press_any_key_to_continue().ask()

    def arc_review_workflow(self) -> None:
        """Architectural Review Log Workflow - Append-only review with triage.

        Supports two modes:
        - Single document: Review one plan/design doc
        - Requirements + Plan (convergent): Review requirements first, then plan with requirements context
        """
        from ..logging_config import get_logger
        logger = get_logger(__name__)

        self.show_header("Architectural Review Log Workflow")

        # Show workflow intro with help
        if self.workflow_helper and self.workflow_helper.has_workflow_help("arc_review_workflow"):
            self.workflow_helper.show_workflow_intro("arc_review_workflow")

        self.console.print(Panel(
            "🏛️ [bold cyan]Architectural Review Log Workflow[/bold cyan]\n\n"
            "High-quality sequential architectural review. Appends structured\n"
            "suggestions to the document's Appendix C in an append-only fashion.\n\n"
            "Features:\n"
            "  • Uses flagship models by default (or select your own)\n"
            "  • Automated triage classifies suggestions (Applied/Rejected)\n"
            "  • Optional apply step to incorporate accepted suggestions\n"
            "  • State persisted for resume and cost tracking\n\n"
            "Modes:\n"
            "  • Single document — Plan, design spec, or architecture doc\n"
            "  • Requirements + Plan — Review requirements, then plan (convergent)",
            border_style="cyan"
        ))

        # 1. Mode selection
        mode_choice = questionary.select(
            "Review mode:",
            choices=[
                "Single document (plan, design spec, or architecture doc)",
                "Requirements + Plan (convergent: requirements first, then plan with context)",
            ],
            style=custom_style,
        ).ask()
        if not mode_choice:
            return

        convergent_mode = "Requirements + Plan" in (mode_choice or "")

        if convergent_mode and self.workflow_helper and self.workflow_helper.has_workflow_help("convergent_review_workflow"):
            self.workflow_helper.show_workflow_intro("convergent_review_workflow")

        # 2. Document path(s)
        if convergent_mode:
            req_path_str = self._safe_path_input(
                "Path to requirements markdown document:",
                only_directories=False,
                style=custom_style,
            )
            if not req_path_str:
                return
            req_path = Path(req_path_str).expanduser().resolve()
            if not req_path.exists() or not req_path.is_file():
                self.console.print(f"[red]File not found: {req_path}[/red]")
                questionary.press_any_key_to_continue().ask()
                return

            plan_path_str = self._safe_path_input(
                "Path to plan/design markdown document:",
                only_directories=False,
                style=custom_style,
            )
            if not plan_path_str:
                return
            plan_path = Path(plan_path_str).expanduser().resolve()
            if not plan_path.exists() or not plan_path.is_file():
                self.console.print(f"[red]File not found: {plan_path}[/red]")
                questionary.press_any_key_to_continue().ask()
                return
            doc_path = plan_path  # For display/metrics; primary output is plan
        else:
            doc_path_str = self._safe_path_input(
                "Path to markdown document to review:",
                only_directories=False,
                style=custom_style,
            )
            if not doc_path_str:
                return
            doc_path = Path(doc_path_str).expanduser().resolve()
            if not doc_path.exists():
                self.console.print(f"[red]File not found: {doc_path}[/red]")
                questionary.press_any_key_to_continue().ask()
                return
            if not doc_path.is_file():
                self.console.print(f"[red]Path is not a file: {doc_path}[/red]")
                questionary.press_any_key_to_continue().ask()
                return

        # 3. Agent selection: use defaults or select
        use_default_agents = questionary.confirm(
            "\nUse default flagship agents? (recommended)",
            default=True,
            style=custom_style
        ).ask()

        agents = None
        selected_agent_infos = []
        if not use_default_agents:
            ready_agents = self._get_ready_agents_for_selection()
            if not ready_agents:
                self.console.print("[red]No ready agents available. Falling back to defaults.[/red]")
            else:
                agent_table = Table(title="Available Agents", show_header=True)
                agent_table.add_column("", justify="center", width=3)
                agent_table.add_column("Agent", style="bold cyan")
                agent_table.add_column("Model", style="cyan")
                for agent in ready_agents:
                    agent_table.add_row(agent['icon'], agent['name'], agent['model'])
                self.console.print(agent_table)
                agent_choices = [f"{a['icon']} {a['name']} ({a['model']})" for a in ready_agents]
                selected = questionary.checkbox(
                    "Select agents for review (SPACE to select, ENTER to confirm):",
                    choices=agent_choices,
                    style=custom_style,
                ).ask()
                if selected:
                    for agent in ready_agents:
                        label = f"{agent['icon']} {agent['name']} ({agent['model']})"
                        if label in selected:
                            selected_agent_infos.append(agent)
                    if selected_agent_infos:
                        agents = self._create_agents_from_infos(selected_agent_infos)
                        if not agents:
                            self.console.print("[yellow]Could not create agents. Falling back to defaults.[/yellow]")
                            agents = None

        # 4. Reviewer count (only when using defaults)
        reviewer_count = 2
        if use_default_agents:
            reviewer_count_str = questionary.text(
                "Number of reviewers (default 2):",
                default="2",
                style=custom_style
            ).ask()
            if reviewer_count_str:
                try:
                    reviewer_count = max(1, min(5, int(reviewer_count_str)))
                except ValueError:
                    reviewer_count = 2

        # 5. Build config and run
        if convergent_mode:
            config = {
                "requirements_path": str(req_path),
                "plan_path": str(plan_path),
                "reviewer_count": reviewer_count,
            }
            workflow_cls = ConvergentReviewWorkflow
            status_msg = "Running convergent review (requirements → plan)..."
        else:
            config = {
                "document_path": str(doc_path),
                "reviewer_count": reviewer_count,
                "init_if_missing": True,
            }
            workflow_cls = ArchitecturalReviewLogWorkflow
            status_msg = "Running architectural review..."

        self.console.print(f"\n[cyan]Starting {status_msg.lower()}[/cyan]\n")
        try:
            workflow = workflow_cls()
            with self.console.status(f"[bold green]{status_msg}[/bold green]") as status:
                def progress_cb(current, total, message):
                    status.update(f"[bold green]{message} ({current}/{total})...[/bold green]")

                result = workflow.run(
                    config=config,
                    agents=agents,
                    on_progress=progress_cb,
                )

            metrics = getattr(result, "metrics", None)
            total_cost = getattr(metrics, "total_cost", 0.0) if metrics else 0.0
            input_tokens = getattr(metrics, "input_tokens", 0) if metrics else 0
            output_tokens = getattr(metrics, "output_tokens", 0) if metrics else 0

            if result.success:
                out = result.output or {}
                if convergent_mode:
                    req_out = out.get("requirements_review") or {}
                    plan_out = out.get("plan_review") or {}
                    summary = (
                        f"[green]✓ Convergent review completed[/green]\n\n"
                        f"Requirements: {req_path.name} — {req_out.get('rounds_appended', 0)} rounds\n"
                        f"Plan: {plan_path.name} — {plan_out.get('rounds_appended', 0)} rounds\n\n"
                        f"Cost: ${total_cost:.4f} | "
                        f"Tokens: {input_tokens} in / {output_tokens} out"
                    )
                    logger.info(
                        "Convergent review completed: req=%s, plan=%s, cost=%.4f",
                        req_path, plan_path, total_cost,
                    )
                else:
                    summary = (
                        f"[green]✓ Architectural review completed[/green]\n\n"
                        f"Document: {out.get('document_path', doc_path)}\n"
                        f"Rounds appended: {out.get('rounds_appended', 0)}\n"
                        f"State: {out.get('state_path', 'N/A')}\n\n"
                        f"Cost: ${total_cost:.4f} | "
                        f"Tokens: {input_tokens} in / {output_tokens} out"
                    )
                    logger.info(
                        "Arc review completed: doc=%s, rounds=%s, cost=%.4f",
                        doc_path, out.get("rounds_appended", 0), total_cost,
                    )
                self.console.print(Panel(summary, title="Review Complete", border_style="green"))
                if result.steps:
                    step_table = Table(title="Steps", show_header=True)
                    step_table.add_column("Step", style="cyan")
                    step_table.add_column("Agent", style="magenta")
                    step_table.add_column("Output", style="white")
                    step_table.add_column("Cost", style="green")
                    for s in result.steps:
                        # Truncate output for table display (60 chars)
                        output_preview = (s.output or "-")[:60]
                        if len(s.output or "") > 60:
                            output_preview += "..."
                        cost_str = f"${s.cost:.4f}" if s.cost is not None else "-"
                        step_table.add_row(
                            s.step_name,
                            s.agent_name or "-",
                            output_preview,
                            cost_str,
                        )
                    self.console.print(step_table)
            else:
                err_msg = result.error or "Unknown error"
                self.console.print(Panel(
                    f"[red]Review did not complete successfully[/red]\n\n{err_msg}",
                    title="Review Incomplete",
                    border_style="red"
                ))
                logger.warning("Arc review incomplete: doc=%s, error=%s", doc_path, err_msg)
                if result.steps:
                    for s in result.steps:
                        if s.error:
                            self.console.print(f"  [red]{s.step_name}: {s.error}[/red]")
        except Exception as e:
            self.console.print(f"\n[red]Architectural review failed: {e}[/red]")
            import traceback
            self.console.print(f"[dim]{traceback.format_exc()}[/dim]")
            logger.exception("Arc review failed: doc=%s", doc_path)

        questionary.press_any_key_to_continue().ask()
