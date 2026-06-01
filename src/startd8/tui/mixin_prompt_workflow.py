"""PromptWorkflowMixin: extracted from tui_improved.py ImprovedTUI (Pass B)."""

from ._shared import *  # noqa: F401,F403

class PromptWorkflowMixin:
    def step1_create_prompt(self):
        """Step 1: Create a prompt"""
        self.show_header("Step 1: Create Prompt")
        
        # Show workflow intro if available
        if self.workflow_helper and self.workflow_helper.has_workflow_help("create_prompt"):
            show_intro = questionary.confirm(
                "\nWould you like to see an overview of this workflow?",
                default=False,
                style=custom_style
            ).ask()
            
            if show_intro:
                self.workflow_helper.show_workflow_intro("create_prompt")
        else:
            # Fallback to simple help
            self.console.print(Panel(
                "[bold]Creating a Prompt[/bold]\n\n"
                "A prompt is the question or task you want to send to LLMs.\n"
                "Example: 'Explain quantum computing in simple terms'\n\n"
                "The prompt will be versioned and stored for tracking.",
                border_style="cyan"
            ))
        
        # Offer contextual help
        show_help = questionary.confirm(
            "\nWould you like help with creating prompts?",
            default=False,
            style=custom_style
        ).ask()
        
        if show_help and self.help_system:
            self.help_system.show_contextual_help("prompt_creation")
        
        # Get prompt text
        prompt_text = questionary.text(
            "\nEnter your prompt:",
            style=custom_style,
            multiline=True
        ).ask()
        
        if not prompt_text:
            return
        
        # Ask if user wants to enhance the prompt with an agent
        enhance_choice = questionary.select(
            "\nWould you like to enhance this prompt with an AI agent?",
            choices=[
                "✅ Yes, enhance with an agent",
                "⏭️  No, use prompt as-is"
            ],
            default="✅ Yes, enhance with an agent",
            style=custom_style
        ).ask()
        
        enhanced_prompt_text = prompt_text
        enhancement_info = None
        
        if "Yes" in enhance_choice or "enhance" in enhance_choice.lower():
            # Get ready agents for enhancement
            ready_agents = self._get_ready_agents_for_selection()
            if not ready_agents:
                self.console.print("[yellow]No ready agents available. Using prompt as-is.[/yellow]")
            else:
                # Display available agents
                agent_table = Table(title="Available Agents for Enhancement", show_header=True)
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
                
                self.console.print("\n")
                self.console.print(agent_table)
                self.console.print()
                
                # Build agent choices
                agent_choices = []
                for agent in ready_agents:
                    agent_choices.append(f"{agent['icon']} {agent['name']} ({agent['model']})")
                agent_choices.append("← Cancel enhancement")
                
                # Select agent for enhancement
                selected_agent_choice = questionary.select(
                    "Select agent to enhance your prompt:",
                    choices=agent_choices,
                    style=custom_style
                ).ask()
                
                if selected_agent_choice and "Cancel" not in selected_agent_choice:
                    # Parse agent name from selection
                    name_part = selected_agent_choice.split(" (")[0].strip()
                    parts = name_part.split()
                    if len(parts) > 1:
                        agent_name = " ".join(parts[1:])
                    else:
                        agent_name = name_part
                    
                    # Find matching agent
                    selected_agent_info = None
                    for agent in ready_agents:
                        if agent['name'] == agent_name:
                            selected_agent_info = agent
                            break
                    
                    if selected_agent_info:
                        # Create agent instance
                        agent_instance = self._create_agent_from_name(agent_name, ready_agents)
                        if agent_instance:
                            # Create enhancement prompt
                            enhancement_prompt = """You are an expert prompt engineer. Your task is to enhance the given prompt to make it more effective for AI agents.

Apply these prompt engineering best practices:

1. **Clarity & Specificity**
   - Make instructions explicit and unambiguous
   - Define technical terms and expected formats
   - Specify the desired output structure

2. **Context & Background**
   - Add relevant context that helps understand the task
   - Include domain-specific information when helpful
   - Specify the target audience or use case

3. **Structure**
   - Use clear sections with headers
   - Add numbered steps for sequential tasks
   - Include examples where helpful

4. **Constraints & Guardrails**
   - Specify what to include AND what to avoid
   - Set length/scope boundaries when appropriate
   - Define quality criteria for the output

5. **Output Format**
   - Specify exact format expected (markdown, JSON, etc.)
   - Include template structures when useful
   - Define sections/headers for the response

IMPORTANT RULES:
- Preserve the core intent of the original prompt
- Don't add unnecessary complexity
- Make the enhanced prompt self-contained
- Output ONLY the enhanced prompt, no explanations

After the enhanced prompt, add a brief "---CHANGES---" section listing key improvements made.

---

Enhance this prompt:

"""
                            enhancement_prompt += prompt_text
                            enhancement_prompt += "\n---"
                            
                            # Send to agent for enhancement
                            self.console.print(f"\n[cyan]🔧 Enhancing prompt with {agent_name}...[/cyan]\n")
                            
                            try:
                                with self.console.status("[bold green]Processing enhancement..."):
                                    response_tuple = agent_instance.generate(enhancement_prompt)
                                    
                                    # Extract response
                                    if isinstance(response_tuple, tuple) and len(response_tuple) >= 1:
                                        enhanced_response = response_tuple[0]
                                    else:
                                        enhanced_response = str(response_tuple)
                                
                                # Parse out the changes summary
                                if "---CHANGES---" in enhanced_response:
                                    parts = enhanced_response.split("---CHANGES---")
                                    enhanced_prompt_text = parts[0].strip()
                                    changes_summary = parts[1].strip() if len(parts) > 1 else ""
                                    enhancement_info = {
                                        'agent': agent_name,
                                        'model': agent_instance.model,
                                        'changes': changes_summary,
                                        'original_length': len(prompt_text),
                                        'enhanced_length': len(enhanced_prompt_text)
                                    }
                                else:
                                    enhanced_prompt_text = enhanced_response.strip()
                                    enhancement_info = {
                                        'agent': agent_name,
                                        'model': agent_instance.model,
                                        'changes': 'No changes summary provided',
                                        'original_length': len(prompt_text),
                                        'enhanced_length': len(enhanced_prompt_text)
                                    }
                                
                                # Show enhancement result
                                self.console.print(Panel(
                                    f"[green]✓ Prompt enhanced successfully![/green]\n\n"
                                    f"[bold]Agent:[/bold] {agent_name} ({agent_instance.model})\n"
                                    f"[bold]Original length:[/bold] {enhancement_info['original_length']} chars\n"
                                    f"[bold]Enhanced length:[/bold] {enhancement_info['enhanced_length']} chars",
                                    title="Enhancement Complete",
                                    border_style="green"
                                ))
                                
                                if enhancement_info.get('changes'):
                                    self.console.print("\n")
                                    self.console.print(Panel(
                                        enhancement_info['changes'],
                                        title="Changes Made",
                                        border_style="blue"
                                    ))
                                
                                # Ask user if they want to use the enhanced version
                                use_enhanced = questionary.select(
                                    "\nWhich version would you like to save?",
                                    choices=[
                                        f"✅ Enhanced version ({enhancement_info['enhanced_length']} chars)",
                                        f"📝 Original version ({enhancement_info['original_length']} chars)"
                                    ],
                                    default=f"✅ Enhanced version ({enhancement_info['enhanced_length']} chars)",
                                    style=custom_style
                                ).ask()
                                
                                if "Original" in use_enhanced:
                                    enhanced_prompt_text = prompt_text
                                    enhancement_info = None
                                
                            except Exception as e:
                                self.console.print(f"\n[red]Enhancement failed: {e}[/red]")
                                self.console.print("[yellow]Using original prompt.[/yellow]\n")
                                enhanced_prompt_text = prompt_text
                                enhancement_info = None
        
        # Get tags (optional)
        tags_input = questionary.text(
            "Add tags (optional, comma-separated):",
            style=custom_style,
        ).ask()
        
        tags = [t.strip() for t in tags_input.split(",")] if tags_input else []
        if enhancement_info:
            tags.append("enhanced")
        
        # Create prompt with enhanced or original content
        self.console.print("\n[cyan]Creating prompt...[/cyan]")
        
        metadata = {}
        if enhancement_info:
            metadata['enhancement'] = enhancement_info
        
        self.current_prompt = self.framework.create_prompt(
            content=enhanced_prompt_text,
            version="1.0.0",
            tags=tags,
            metadata=metadata
        )
        
        self.console.print()
        self.console.print(Panel(
            f"[green]✓ Prompt Created Successfully![/green]\n\n"
            f"[bold]Prompt ID:[/bold] {self.current_prompt.id}\n"
            f"[bold]Version:[/bold] {self.current_prompt.version}\n"
            f"[bold]Tags:[/bold] {', '.join(self.current_prompt.tags) if self.current_prompt.tags else 'None'}\n"
            + (f"[bold]Enhanced by:[/bold] {enhancement_info['agent']} ({enhancement_info['model']})\n" if enhancement_info else "")
            + f"\n[bold]Content:[/bold]\n{self.current_prompt.content[:500]}{'...' if len(self.current_prompt.content) > 500 else ''}",
            title="✅ Prompt Stored",
            border_style="green"
        ))
        
        # Next step suggestion
        next_step = questionary.select(
            "\nWhat next?",
            choices=[
                "2️⃣  Distribute this prompt to agents now",
                "← Back to main menu"
            ],
            style=custom_style
        ).ask()
        
        if "Distribute" in next_step:
            self.step2_distribute_prompt()

    def step2_run_design_review_chain(self):
        """Run the Design Review Chain workflow"""
        self.show_header("Run Design Pipeline")
        
        # Show workflow intro with help
        if self.workflow_helper and self.workflow_helper.has_workflow_help("design_pipeline"):
            self.workflow_helper.show_workflow_intro("design_pipeline")
        else:
            self.console.print(Panel(
                "🚀 [bold cyan]Design Review Pipeline[/bold cyan]\n\n"
                "Sequential workflow:\n"
                "  1. [bold]Draft[/bold] (Sonnet 4.5) - Create initial design\n"
                "  2. [bold]Review[/bold] (OpenAI) - Critique and find gaps\n"
                "  3. [bold]Polish[/bold] (Composer) - Finalize document\n",
                border_style="cyan"
            ))
        
        # Offer to see examples
        show_examples = questionary.confirm(
            "\nWould you like to see workflow examples?",
            default=False,
            style=custom_style
        ).ask()
        
        if show_examples and self.workflow_helper:
            self.workflow_helper.show_workflow_examples("design_pipeline")

        # 1. Get Prompt
        prompt_text = questionary.text(
            "\nEnter the design task or feature description:",
            style=custom_style
        ).ask()
        
        if not prompt_text:
            return

        # Ensure agent status is up to date
        self.agent_status = AgentConfigTester.test_all()
        
        # 2. Select Agents (using modular ready agent selection)
        self.console.print("\n[bold]Select Agents for Pipeline Steps:[/bold]")
        
        # Show available ready agents
        ready_agents = self._get_ready_agents_for_selection()
        if not ready_agents:
            self.console.print("[red]No agents with Ready status available. Please configure agents first.[/red]")
            questionary.press_any_key_to_continue().ask()
            return
        
        # Display ready agents table
        agent_table = Table(title="Available Agents (Ready Status)", show_header=True)
        agent_table.add_column("", justify="center", width=3)  # Icon
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
        
        # Drafter
        drafter = self._select_ready_agent("Select Agent for DRAFTER", "Sonnet 4.5")
        if not drafter: return
        
        # Reviewer
        reviewer = self._select_ready_agent("Select Agent for REVIEWER", "OpenAI")
        if not reviewer: return
        
        # Final Reviewer
        final_reviewer = self._select_ready_agent("Select Agent for FINAL POLISH", "Composer")
        if not final_reviewer: return
        
        # 3. Run Pipeline
        self.console.print(f"\n[cyan]Running Pipeline...[/cyan]")
        self.console.print(f"  1. Drafter: {drafter.name}")
        self.console.print(f"  2. Reviewer: {reviewer.name}")
        self.console.print(f"  3. Final:   {final_reviewer.name}\n")
        
        try:
            from ..logging_config import get_logger
            logger = get_logger(__name__)
            
            pipeline = WorkflowTemplates.design_review_chain(drafter, reviewer, final_reviewer)
            pipeline.framework = self.framework
            
            with self.console.status("[bold green]Executing pipeline steps...[/bold green]") as status:
                result = pipeline.run(prompt_text)
            
            # 4. Show Result
            self.console.print("\n[green]✓ Pipeline Complete![/green]\n")
            
            self.console.print(Panel(
                result.final_output,
                title="Final Design Document",
                border_style="green"
            ))
            
            # 5. Save
            save = questionary.confirm(
                "Save result to file?",
                default=True,
                style=custom_style
            ).ask()
            
            if save:
                filename = questionary.text(
                    "Filename:",
                    default=f"design_doc_{result.pipeline_id[:8]}.md",
                    style=custom_style
                ).ask()
                
                if filename:
                    content = f"# Design Pipeline Result\n\n"
                    content += f"**Task:** {prompt_text}\n\n"
                    content += "---\n\n"
                    content += result.final_output
                    content += "\n\n---\n"
                    content += "## Pipeline Steps\n"
                    for step in result.steps:
                        content += f"### {step['step_name']} ({step['agent']})\n"
                        content += f"{step['output']}\n\n"
                    
                    saved_path = save_text_file_with_versioning(Path(filename), content)
                    self.console.print(f"[green]Saved to {saved_path}[/green]")
        except (AgentError, APIError, ConfigurationError) as e:
            # Log user-friendly errors properly for error analysis workflow
            from ..logging_config import get_logger
            logger = get_logger(__name__)
            logger.error(
                f"Design pipeline failed: {e}",
                exc_info=False,  # Don't log traceback for user-friendly errors
                extra={
                    "pipeline_name": "design_review_chain",
                    "agent_name": getattr(e, 'agent_name', None),
                    "error_type": type(e).__name__
                }
            )
            self.console.print(f"\n[red]Design pipeline failed: {e}[/red]")
            if hasattr(e, 'original_error') and e.original_error:
                self.console.print(f"[dim]Original error: {e.original_error}[/dim]")
        except Exception as e:
            # Log unexpected errors with full traceback for debugging
            from ..logging_config import get_logger
            logger = get_logger(__name__)
            logger.error(
                f"Design pipeline failed: {e}",
                exc_info=True,  # Log full traceback for unexpected errors
                extra={
                    "pipeline_name": "design_review_chain",
                    "error_type": type(e).__name__
                }
            )
            self.console.print(f"\n[red]Unexpected Error: {e}[/red]")
            import traceback
            self.console.print(f"[dim]{traceback.format_exc()}[/dim]")
        
        questionary.press_any_key_to_continue().ask()

    def run_design_polish_pipeline(self):
        """Run the Design Polish Pipeline workflow (Polish → Suggest Updates → Final Polish)"""
        self.show_header("Design Polish Pipeline")
        
        self.console.print(Panel(
            "✨ [bold cyan]Design Polish Pipeline[/bold cyan]\n\n"
            "Sequential workflow for refining existing design documents:\n"
            "  1. [bold]Polish[/bold] - Initial polish pass\n"
            "  2. [bold]Suggest Updates[/bold] - Review and suggest improvements\n"
            "  3. [bold]Final Polish[/bold] - Incorporate suggestions and finalize\n",
            border_style="cyan"
        ))
        
        # 1. Get document input (file or text)
        input_method = questionary.select(
            "Choose input method:",
            choices=[
                "📁 Load from file",
                "✏️  Paste document text",
                "← Cancel"
            ],
            style=custom_style
        ).ask()
        
        if not input_method or "Cancel" in input_method:
            return
        
        document_text = None
        original_doc_path = None  # Track original file path for saving next to it
        
        if "file" in input_method.lower():
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
            
            try:
                document_text = doc_path.read_text(encoding='utf-8')
                original_doc_path = doc_path  # Store original path for later use
            except Exception as e:
                self.console.print(f"[red]Error reading file: {e}[/red]")
                questionary.press_any_key_to_continue().ask()
                return
        else:
            # Paste text
            document_text = questionary.text(
                "Paste the design document text:",
                multiline=True,
                style=custom_style
            ).ask()
        
        if not document_text or not document_text.strip():
            self.console.print("[yellow]No document text provided.[/yellow]")
            questionary.press_any_key_to_continue().ask()
            return
        
        # 1.5. Show document preview and allow editing
        self.console.print("\n[bold]Document Preview[/bold]\n")
        preview_text = document_text[:500] + ("..." if len(document_text) > 500 else "")
        self.console.print(Panel(
            preview_text,
            title=f"Document Content ({len(document_text)} characters)",
            border_style="cyan"
        ))
        
        edit_document = questionary.confirm(
            "\nWould you like to edit the document before proceeding?",
            default=False,
            style=custom_style
        ).ask()
        
        if edit_document:
            edited_text = questionary.text(
                "Edit the design document:",
                default=document_text,
                multiline=True,
                style=custom_style
            ).ask()
            
            if edited_text and edited_text.strip():
                document_text = edited_text
                self.console.print("[green]✓ Document updated[/green]\n")
            else:
                self.console.print("[yellow]No changes made, using original document.[/yellow]\n")
        
        # Ensure agent status is up to date
        self.agent_status = AgentConfigTester.test_all()
        
        # 2. Select Agents
        self.console.print("\n[bold]Select Agents for Pipeline Steps:[/bold]")
        
        # Show available ready agents
        ready_agents = self._get_ready_agents_for_selection()
        if not ready_agents:
            self.console.print("[red]No agents with Ready status available. Please configure agents first.[/red]")
            questionary.press_any_key_to_continue().ask()
            return
        
        # Display ready agents table
        agent_table = Table(title="Available Agents (Ready Status)", show_header=True)
        agent_table.add_column("", justify="center", width=3)  # Icon
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
        
        # Polisher
        polisher = self._select_ready_agent("Select Agent for POLISHER", "Claude Sonnet")
        if not polisher:
            return
        
        # Updater
        updater = self._select_ready_agent("Select Agent for UPDATER (suggests improvements)", "GPT-4")
        if not updater:
            return
        
        # Final Polisher
        final_polisher = self._select_ready_agent("Select Agent for FINAL POLISHER", "Claude Opus")
        if not final_polisher:
            return
        
        # 2.5. Optional: Load polishing instructions from .md file
        polishing_instructions = None
        use_instructions_file = questionary.confirm(
            "\nWould you like to use a .md file with polishing instructions for the first agent?",
            default=False,
            style=custom_style
        ).ask()
        
        if use_instructions_file:
            instructions_path = self._safe_path_input(
                "Path to polishing instructions file (.md):",
                only_directories=False,
                style=custom_style
            )
            
            if instructions_path:
                instructions_file = Path(instructions_path).expanduser()
                if not instructions_file.exists():
                    self.console.print(f"[yellow]File not found: {instructions_file}[/yellow]")
                    self.console.print("[yellow]Continuing without custom instructions...[/yellow]\n")
                else:
                    try:
                        polishing_instructions = instructions_file.read_text(encoding='utf-8')
                        self.console.print(f"[green]✓ Loaded polishing instructions from {instructions_file.name}[/green]\n")
                    except Exception as e:
                        self.console.print(f"[yellow]Error reading instructions file: {e}[/yellow]")
                        self.console.print("[yellow]Continuing without custom instructions...[/yellow]\n")
        
        # 3. Run Pipeline
        self.console.print(f"\n[cyan]Running Design Polish Pipeline...[/cyan]")
        self.console.print(f"  1. Polisher: {polisher.name}")
        if polishing_instructions:
            self.console.print(f"     [dim]Using custom polishing instructions[/dim]")
        self.console.print(f"  2. Updater: {updater.name}")
        self.console.print(f"  3. Final Polisher: {final_polisher.name}\n")
        
        try:
            from ..exceptions import AgentError, APIError, ConfigurationError

            # Use extracted workflow class for consistency
            workflow = DesignPolishWorkflow()

            with self.console.status("[bold green]Executing pipeline steps...[/bold green]") as status:
                def progress_callback(current, total, message):
                    status.update(f"[bold green]{message} ({current}/{total})...[/bold green]")

                workflow_result = workflow.run(
                    config={
                        "document": document_text,
                        "prompt_instructions": polishing_instructions,
                    },
                    agents=[polisher, updater, final_polisher],
                    on_progress=progress_callback
                )

            # Check for failure
            if not workflow_result.success:
                raise Exception(workflow_result.error or "Workflow failed")

            # 4. Show Result
            self.console.print("\n[green]✓ Pipeline Complete![/green]\n")

            self.console.print(Panel(
                workflow_result.output,
                title="Final Polished Design Document",
                border_style="green"
            ))
            
            # 5. Save
            save = questionary.confirm(
                "Save result to file?",
                default=True,
                style=custom_style
            ).ask()
            
            if save:
                # Determine default filename and location
                if original_doc_path:
                    # If loaded from file, offer option to save next to original
                    original_stem = original_doc_path.stem
                    original_suffix = original_doc_path.suffix or '.md'
                    original_dir = original_doc_path.parent
                    
                    # Generate polished filename next to original
                    polished_filename_next_to_original = original_dir / f"{original_stem}_polished{original_suffix}"
                    
                    # Ask user where to save
                    save_location = questionary.select(
                        "Where would you like to save the polished document?",
                        choices=[
                            f"📁 Next to original file: {polished_filename_next_to_original.name}",
                            "📝 Custom location",
                            "← Cancel"
                        ],
                        default=f"📁 Next to original file: {polished_filename_next_to_original.name}",
                        style=custom_style
                    ).ask()
                    
                    if not save_location or "Cancel" in save_location:
                        return
                    
                    if "Next to original" in save_location:
                        # Save next to original file
                        output_path = polished_filename_next_to_original
                    else:
                        # Custom location
                        filename = questionary.text(
                            "Filename:",
                            default=f"polished_design_{workflow_result.workflow_id}.md",
                            style=custom_style
                        ).ask()
                        
                        if not filename:
                            return
                        
                        output_path = Path(filename)
                        if not output_path.is_absolute():
                            # If relative path, use current directory or original file's directory
                            output_path = original_dir / output_path
                else:
                    # No original file (pasted text), use custom location
                    filename = questionary.text(
                        "Filename:",
                        default=f"polished_design_{workflow_result.workflow_id}.md",
                        style=custom_style
                    ).ask()
                    
                    if not filename:
                        return
                    
                    output_path = Path(filename)
                    if not output_path.is_absolute():
                        output_path = Path.cwd() / output_path
                
                # Write the file
                try:
                    content = f"# Design Polish Pipeline Result\n\n"
                    content += "---\n\n"
                    content += workflow_result.output
                    content += "\n\n---\n"
                    content += "## Pipeline Steps\n"
                    for step in workflow_result.steps:
                        content += f"### {step.step_name} ({step.agent_name})\n"
                        content += f"{step.output}\n\n"
                    
                    saved_path = save_text_file_with_versioning(output_path, content)
                    self.console.print(f"[green]✓ Saved to {saved_path}[/green]")
                    if original_doc_path:
                        self.console.print(f"[dim]Original: {original_doc_path}[/dim]")
                        self.console.print(f"[dim]Polished: {output_path}[/dim]")
                except Exception as e:
                    self.console.print(f"[red]Error saving file: {e}[/red]")
                    questionary.press_any_key_to_continue().ask()
        except (AgentError, APIError, ConfigurationError) as e:
            # Log user-friendly errors properly for error analysis workflow
            from ..logging_config import get_logger
            logger = get_logger(__name__)
            logger.error(
                f"Design polish pipeline failed: {e}",
                exc_info=False,  # Don't log traceback for user-friendly errors
                extra={
                    "pipeline_name": "design_polish_chain",
                    "agent_name": getattr(e, 'agent_name', None),
                    "error_type": type(e).__name__
                }
            )
            self.console.print(f"\n[red]Design polish pipeline failed: {e}[/red]")
            if hasattr(e, 'original_error') and e.original_error:
                self.console.print(f"[dim]Original error: {e.original_error}[/dim]")
        except Exception as e:
            # Log unexpected errors with full traceback for debugging
            from ..logging_config import get_logger
            logger = get_logger(__name__)
            logger.error(
                f"Design polish pipeline failed: {e}",
                exc_info=True,  # Log full traceback for unexpected errors
                extra={
                    "pipeline_name": "design_polish_chain",
                    "error_type": type(e).__name__
                }
            )
            self.console.print(f"\n[red]Unexpected Error: {e}[/red]")
            import traceback
            self.console.print(f"[dim]{traceback.format_exc()}[/dim]")
        
        questionary.press_any_key_to_continue().ask()

    def step2_distribute_prompt(self):
        """Step 2: Distribute prompt to agents"""
        
        # If no current prompt, let user select one
        if not self.current_prompt:
            prompts = self.framework.list_prompts()
            if not prompts:
                self.console.print("\n[yellow]No prompts found. Create one first.[/yellow]\n")
                questionary.press_any_key_to_continue().ask()
                return
            
            self.show_header("Step 2: Select Prompt to Distribute")
            self.console.print("[cyan]Select a prompt to distribute to agents:[/cyan]\n")
            self.select_existing_prompt()
            
            if not self.current_prompt:
                return
        
        self.show_header("Step 2: Distribute to Agents")
        
        # Show current prompt
        self.console.print(Panel(
            f"[bold]Selected Prompt:[/bold]\n\n"
            f"{self.current_prompt.content}\n\n"
            f"[dim]ID: {self.current_prompt.id}[/dim]",
            border_style="cyan"
        ))
        
        # Get existing responses for this prompt to track distribution
        existing_responses = self.framework.list_responses(prompt_id=self.current_prompt.id)
        distributed_agents = set()
        for resp in existing_responses:
            # Track by agent name and model combination
            distributed_agents.add(f"{resp.agent_name}:{resp.model}")
        
        # Get all agents
        custom_agents = self.agent_manager.list_agents()
        all_agents = self._build_unified_agent_list(custom_agents, distributed_agents)
        all_available = self._count_all_available_agents(custom_agents)
        
        # Show unified agent table
        self._show_agent_distribution_table(all_agents, distributed_agents)
        
        # Count undistributed agents
        undistributed_count = sum(1 for a in all_agents if a['available'] and not a['distributed'])
        
        # Build agent selection choices
        agent_choices = []
        
        # ALL AGENTS options
        if all_available['total'] > 1:
            agent_choices.append(questionary.Separator("─── Run Multiple ───"))
            agent_choices.append(
                f"🚀 ALL AVAILABLE ({all_available['total']} agents)"
            )
            if undistributed_count > 0:
                agent_choices.append(
                    f"🆕 ONLY UNDISTRIBUTED ({undistributed_count} agents)"
                )
        
        # Individual agents
        agent_choices.append(questionary.Separator("─── Select Individual ───"))
        
        for agent in all_agents:
            if agent['available']:
                status = "[green]✓ sent[/green]" if agent['distributed'] else "[dim]not sent[/dim]"
                icon = agent.get('icon', '🤖')
                agent_choices.append(
                    f"{icon} {agent['name']} ({agent['model'][:20]}) {status}"
                )
        else:
                agent_choices.append(
                    f"[dim]{agent.get('icon', '🤖')} {agent['name']} ({agent.get('error', 'not available')})[/dim]"
                )
        
        agent_choices.append(questionary.Separator("───────────────────────"))
        agent_choices.append("❓ Help (about agent selection)")
        agent_choices.append("📝 Select Different Prompt")
        agent_choices.append("← Back to Main Menu")
        
        selected = questionary.select(
            "\nWhich agent(s) to use?",
            choices=agent_choices,
            style=custom_style,
        ).ask()
        
        if not selected or "Back to Main" in selected:
            return
        
        if "Help" in selected:
            if self.help_system:
                self.help_system.show_contextual_help("agent_selection")
            # Re-show menu after help
            self.step2_distribute_prompt()
            return
        
        if "Different Prompt" in selected:
            self.current_prompt = None
            self.step2_distribute_prompt()
            return
        
        # Run agents based on selection
        if "ALL AVAILABLE" in selected:
            agents = self._get_all_available_agents(custom_agents)
        elif "ONLY UNDISTRIBUTED" in selected:
            agents = self._get_undistributed_agents(all_agents, custom_agents, distributed_agents)
        else:
            # Individual agent selected
            agents = self._get_agent_from_unified_choice(selected, all_agents, custom_agents)
        
        if not agents:
            self.console.print("\n[red]No valid agents selected[/red]")
            questionary.press_any_key_to_continue().ask()
            return
        
        self._run_agents(agents)
        
        # Next step suggestion
        next_step = questionary.select(
            "\nWhat next?",
            choices=[
                "3️⃣  View results now",
                "🔄 Distribute to more agents",
                "← Back to main menu"
            ],
            style=custom_style
        ).ask()
        
        if "View" in next_step:
            self.step3_view_results()
        elif "Distribute" in next_step:
            self.step2_distribute_prompt()


    def step3_view_results(self):
        """Step 3: View results"""
        
        if not self.current_prompt:
            self.console.print("\n[yellow]No current prompt. Let's select one...[/yellow]\n")
            self.select_existing_prompt()
            
            if not self.current_prompt:
                return
        
        self.show_header("Step 3: View Results")
        
        # Get responses for current prompt
        responses = self.framework.list_responses(prompt_id=self.current_prompt.id)
        
        if not responses:
            self.console.print(Panel(
                "[yellow]No responses yet for this prompt[/yellow]\n\n"
                "Go back and distribute the prompt to agents first.",
                title="No Results",
                border_style="yellow"
            ))
            questionary.press_any_key_to_continue().ask()
            return
        
        # Show prompt
        self.console.print(Panel(
            self.current_prompt.content,
            title=f"📝 Prompt ({len(responses)} responses)",
            border_style="cyan"
        ))
        
        # Show each response
        for i, response in enumerate(responses, 1):
            self.console.print()
            self.console.print(Panel(
                f"[bold cyan]{response.agent_name}[/bold cyan] ([dim]{response.model}[/dim])\n\n"
                f"{response.response}\n\n"
                f"[dim]───────────────────────[/dim]\n"
                f"[dim]Time: {response.response_time_ms}ms | "
                f"Tokens: {response.token_usage.total if response.token_usage else 'N/A'} | "
                f"Cost: ${response.token_usage.cost_estimate:.4f}" if response.token_usage else "N/A" + "[/dim]",
                title=f"Response {i}/{len(responses)}",
                border_style="green"
            ))
        
        # Comparison if multiple responses
        if len(responses) > 1:
            self.console.print()
            self._show_comparison(self.current_prompt.id)
        
        # Options
        self.console.print()
        action = questionary.select(
            "What would you like to do?",
            choices=[
                "💾 Save results to file",
                "🔄 Run more agents on this prompt",
                "📋 Select different prompt",
                "← Back to main menu"
            ],
            style=custom_style
        ).ask()
        
        if "Save" in action:
            self._save_results()
        elif "Run more" in action:
            self.step2_distribute_prompt()
        elif "different prompt" in action:
            self.select_existing_prompt()
            if self.current_prompt:
                self.step3_view_results()


    def _run_agents(self, agents: List[BaseAgent]):
        """Run agents on current prompt"""
        self.console.print(f"\n[cyan]Running {len(agents)} agent(s)...[/cyan]\n")
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=self.console
        ) as progress:
            
            for agent in agents:
                task = progress.add_task(f"Running {agent.name}...", total=None)
                
                try:
                    response = agent.create_response(
                        self.current_prompt.id,
                        self.current_prompt.content
                    )
                    self.framework.storage.save_response(response)
                    progress.update(task, description=f"[green]✓[/green] {agent.name} complete")
                except Exception as e:
                    progress.update(task, description=f"[red]✗[/red] {agent.name} failed: {e}")
        
        self.console.print("\n[green]✓ All agents complete![/green]\n")
        
        # Auto-save results
        self.console.print("[dim]Auto-saving results...[/dim]")
        self._save_results(interactive=False)
        
        questionary.press_any_key_to_continue().ask()

    def _show_comparison(self, prompt_id: str):
        """Show comparison table"""
        comparison = self.framework.compare_responses(prompt_id)
        
        # Handle both dict (backward compat) and ResponseComparison model
        if hasattr(comparison, 'model_dump'):
            comparison_dict = comparison.model_dump()
        else:
            comparison_dict = comparison
        
        table = Table(title="📊 Performance Comparison")
        table.add_column("Agent", style="cyan")
        table.add_column("Time", justify="right", style="yellow")
        table.add_column("Tokens", justify="right", style="blue")
        table.add_column("Cost", justify="right", style="green")
        table.add_column("Rank", justify="center", style="magenta")
        
        for i, resp in enumerate(comparison_dict['responses'], 1):
            table.add_row(
                resp['agent'],
                f"{resp['response_time_ms']}ms",
                str(resp['tokens']) if resp['tokens'] else "N/A",
                f"${resp['cost_estimate']:.4f}" if resp['cost_estimate'] else "N/A",
                f"#{i}"
            )
        
        self.console.print(table)

    def _save_results(self, filename: Optional[str] = None, interactive: bool = True):
        """Save current results"""
        if not self.current_prompt:
            return
        
        if interactive:
            filename = questionary.text(
                "Filename:",
                default=f"results_{self.current_prompt.id[:8]}.md",
                style=custom_style
            ).ask()
        elif not filename:
            # Auto-generate filename if not interactive
            filename = f"results_{self.current_prompt.id[:8]}.md"
        
        if not filename:
            return
        
        responses = self.framework.list_responses(prompt_id=self.current_prompt.id)
        
        with open(filename, 'w') as f:
            f.write(f"# Results for Prompt {self.current_prompt.id}\n\n")
            f.write(f"**Prompt:** {self.current_prompt.content}\n\n")
            f.write("---\n\n")
            
            for i, resp in enumerate(responses, 1):
                f.write(f"## Response {i}: {resp.agent_name}\n\n")
                f.write(resp.response)
                f.write("\n\n")
                f.write(f"- Time: {resp.response_time_ms}ms\n")
                f.write(f"- Tokens: {resp.token_usage.total if resp.token_usage else 'N/A'}\n")
                f.write(f"- Cost: ${resp.token_usage.cost_estimate:.4f}\n" if resp.token_usage else "- Cost: N/A\n")
                f.write("\n---\n\n")
        
        self.console.print(f"\n[green]✓ Saved to {filename}[/green]\n")
        
        if interactive:
            questionary.press_any_key_to_continue().ask()

    def select_existing_prompt(self):
        """Select an existing prompt"""
        prompts = self.framework.list_prompts()
        
        if not prompts:
            self.console.print("\n[yellow]No prompts found. Create one first.[/yellow]\n")
            questionary.press_any_key_to_continue().ask()
            return
        
        choices = [
            f"{p.id[:12]}... | {p.content[:50]}{'...' if len(p.content) > 50 else ''}"
            for p in prompts[:10]  # Show last 10
        ]
        choices.append("← Cancel")
        
        selected = questionary.select(
            "Select a prompt:",
            choices=choices,
            style=custom_style
        ).ask()
        
        if selected == "← Cancel":
            return
        
        prompt_id = selected.split("|")[0].strip().replace("...", "")
        
        for p in prompts:
            if p.id.startswith(prompt_id):
                self.current_prompt = p
                break
