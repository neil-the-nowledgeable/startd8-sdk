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

    def _build_unified_agent_list(self, custom_agents: List[Dict[str, Any]], distributed_agents: set) -> List[Dict[str, Any]]:
        """Build a unified list of all agents with their status"""
        agents = []
        
        # Built-in: Mock
        mock_key = "mock:mock-model"
        agents.append({
            'name': 'Mock',
            'model': 'mock-model',
            'type': 'builtin',
            'builtin_type': 'mock',
            'icon': '🧪',
            'available': self.agent_status['mock']['working'],
            'distributed': mock_key in distributed_agents,
            'error': None if self.agent_status['mock']['working'] else 'not working'
        })
        
        # Built-in: Claude
        claude_model = 'claude-opus-4-8'
        claude_key = f"claude:{claude_model}"
        agents.append({
            'name': 'Claude',
            'model': claude_model,
            'type': 'builtin',
            'builtin_type': 'claude',
            'icon': '🔵',
            'available': self.agent_status['claude']['working'],
            'distributed': claude_key in distributed_agents or any(
                'claude' in k.lower() for k in distributed_agents
            ),
            'error': self.agent_status['claude'].get('error') if not self.agent_status['claude']['working'] else None
        })
        
        # Built-in: GPT-4
        gpt4_model = 'gpt-5.5-pro'
        gpt4_key = f"gpt4:{gpt4_model}"
        agents.append({
            'name': 'GPT-4',
            'model': gpt4_model,
            'type': 'builtin',
            'builtin_type': 'gpt4',
            'icon': '🟢',
            'available': self.agent_status['gpt4']['working'],
            'distributed': gpt4_key in distributed_agents or any(
                'gpt' in k.lower() for k in distributed_agents
            ),
            'error': self.agent_status['gpt4'].get('error') if not self.agent_status['gpt4']['working'] else None
        })
        
        # Custom agents
        for agent in custom_agents:
            agent_type = agent.get('type', 'unknown')
            type_info = CustomAgentManager.AGENT_TYPES.get(agent_type, {})
            api_key_env = type_info.get('api_key_env')
            
            # For openai_compatible, check the agent's own api_key_env
            if agent_type == 'openai_compatible':
                api_key_env = agent.get('api_key_env')
            
            # Check if agent can work
            available = True
            error = None
            if api_key_env:
                key_status = self.key_manager.get_key_status(api_key_env)
                if not key_status.get('set'):
                    available = False
                    error = f"{api_key_env} not set"
            
            agent_name = agent.get('name', 'custom')
            agent_model = agent.get('model', 'unknown')
            agent_key = f"{agent_name}:{agent_model}"
            
            # Determine icon based on provider
            provider = agent.get('provider', agent_type)
            icon_map = {
                'cursor': '⚡',
                'ollama': '🦙',
                'groq': '🚀',
                'together': '🌐',
                'openrouter': '🔀',
                'openai_compatible': '⚙️',
                'claude': '🔵',
                'gpt4': '🟢',
                'mock': '🧪'
            }
            icon = icon_map.get(provider, '⭐')
            
            agents.append({
                'name': agent_name,
                'model': agent_model,
                'type': 'custom',
                'custom_config': agent,
                'icon': icon,
                'available': available,
                'distributed': agent_key in distributed_agents,
                'error': error
            })
        
        return agents

    def _show_agent_distribution_table(self, agents: List[Dict[str, Any]], distributed_agents: set):
        """Show unified table of all agents with distribution status"""
        table = Table(title="All Agents", show_header=True)
        table.add_column("", justify="center", width=3)  # Icon
        table.add_column("Agent", style="bold")
        table.add_column("Model", style="cyan")
        table.add_column("Type", style="magenta")
        table.add_column("Status", justify="center")
        table.add_column("Sent?", justify="center")
        
        for agent in agents:
            icon: str = agent.get('icon', '🤖')
            name: str = agent['name']
            model: str = agent['model'][:25] + "..." if len(agent['model']) > 25 else agent['model']
            agent_type: str = "Built-in" if agent['type'] == 'builtin' else "User added"
            
            if agent['available']:
                status: str = "[green]✓ Ready[/green]"
            else:
                status = f"[red]✗ {agent.get('error', 'N/A')}[/red]"
            
            if agent['distributed']:
                sent: str = "[green]✓ Yes[/green]"
            else:
                sent = "[dim]No[/dim]"
            
            table.add_row(icon, name, model, agent_type, status, sent)
        
        self.console.print()
        self.console.print(table)
        self.console.print()

    def _get_undistributed_agents(self, all_agents: List[Dict[str, Any]], custom_agents: List[Dict[str, Any]], distributed_agents: set) -> List[BaseAgent]:
        """Get only agents that haven't received this prompt yet"""
        agents: List[BaseAgent] = []
        
        for agent_info in all_agents:
            if agent_info['available'] and not agent_info['distributed']:
                if agent_info['type'] == 'builtin':
                    if agent_info['builtin_type'] == 'mock':
                        agents.append(MockAgent(name="mock", model="mock-model"))
                    elif agent_info['builtin_type'] == 'claude':
                        try:
                            agents.append(ClaudeAgent())
                        except Exception:
                            pass
                    elif agent_info['builtin_type'] == 'gpt4':
                        try:
                            agents.append(GPT4Agent())
                        except Exception:
                            pass
                else:
                    # Custom agent
                    try:
                        instance = self.agent_manager.create_agent_instance(agent_info['custom_config'])
                        if instance:
                            agents.append(instance)
                    except Exception:
                        pass
        
        return agents

    def _get_agent_from_unified_choice(self, choice: str, all_agents: List[Dict[str, Any]], custom_agents: List[Dict[str, Any]]) -> List[BaseAgent]:
        """Get agent from unified selection choice"""
        agents: List[BaseAgent] = []
        
        # Extract agent name from choice (format: "icon name (model)")
        # Try to parse the exact name from the choice string
        agent_name: Optional[str] = None
        if "⭐" in choice:
            # Custom agent format: "⭐ name (model)"
            try:
                parts = choice.split("⭐ ", 1)
                if len(parts) > 1:
                    name_part = parts[1].split(" (")[0]
                    agent_name = name_part.strip()
            except (IndexError, ValueError):
                pass
        
        # If we couldn't parse, try substring matching
        if not agent_name:
            # Find the agent by matching name substring
            for agent_info in all_agents:
                if agent_info['name'] in choice and agent_info.get('available', False):
                    agent_name = agent_info['name']
                    break
        
        # Now find and create the agent
        if agent_name:
            for agent_info in all_agents:
                if agent_info['name'] == agent_name and agent_info.get('available', False):
                    if agent_info['type'] == 'builtin':
                        if agent_info['builtin_type'] == 'mock':
                            agents.append(MockAgent(name="mock", model="mock-model"))
                        elif agent_info['builtin_type'] == 'claude':
                            try:
                                agents.append(ClaudeAgent())
                            except Exception:
                                pass
                        elif agent_info['builtin_type'] == 'gpt4':
                            try:
                                agents.append(GPT4Agent())
                            except Exception:
                                pass
                    else:
                        # Custom agent
                        custom_config = agent_info.get('custom_config')
                        if not custom_config:
                            # Try to find in custom_agents list
                            for custom_agent in custom_agents:
                                if custom_agent.get('name') == agent_name:
                                    custom_config = custom_agent
                                    break
                        
                        if custom_config:
                            try:
                                instance = self.agent_manager.create_agent_instance(custom_config)
                                if instance:
                                    agents.append(instance)
                            except Exception as e:
                                # Log the error for debugging but don't fail silently
                                import logging
                                logger = logging.getLogger(__name__)
                                logger.warning(f"Failed to create agent '{agent_name}': {e}", exc_info=True)
                                # Don't append, but continue to try other matches
                                pass
                    break
        
        return agents

    def _validate_agent_for_workflow(self, agent_info: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """
        Validate that an agent can actually be created and is properly configured.
        
        This performs a real validation by attempting to create the agent instance
        and checking model names against provider supported models.
        
        Args:
            agent_info: Agent dictionary from unified agent list
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            # Try to create the agent instance
            if agent_info['type'] == 'builtin':
                # Built-in agents - try to create
                if agent_info.get('builtin_type') == 'mock':
                    MockAgent(name="mock", model="mock-model")
                    return True, None
                elif agent_info.get('builtin_type') == 'claude':
                    ClaudeAgent()
                    return True, None
                elif agent_info.get('builtin_type') == 'gpt4':
                    GPT4Agent()
                    return True, None
            else:
                # Custom agent - validate configuration
                custom_config = agent_info.get('custom_config')
                if not custom_config:
                    # Try to find in custom agents list
                    custom_agents = self.agent_manager.list_agents()
                    for custom_agent in custom_agents:
                        if custom_agent.get('name') == agent_info.get('name'):
                            custom_config = custom_agent
                            break
                
                if custom_config:
                    # Validate model name if provider-backed agent
                    agent_type = custom_config.get('type')
                    model = custom_config.get('model', '')
                    provider_name = custom_config.get('provider')
                    
                    if agent_type == 'provider' and provider_name and model:
                        # Check if model is supported by provider
                        try:
                            from ..providers.registry import ProviderRegistry
                            ProviderRegistry.discover()
                            provider = ProviderRegistry.get_provider(provider_name.lower())
                            
                            if provider:
                                # Check if model is in supported models (or provider allows unknown models)
                                supported_models = provider.supported_models or []
                                model_lower = model.lower()
                                
                                # Pre-validation: Check for obviously invalid model names
                                if provider_name.lower() == 'openai':
                                    # Check for invalid GPT model versions
                                    if 'gpt-5' in model_lower or 'gpt-6' in model_lower:
                                        return False, f"Model '{model}' is not a valid OpenAI model (GPT-5/6 don't exist)"
                                    # Check if model matches known GPT patterns
                                    valid_patterns = ['gpt-4', 'gpt-3', 'gpt-4o', 'o1', 'davinci', 'curie', 'babbage', 'ada']
                                    if not any(pattern in model_lower for pattern in valid_patterns):
                                        # Not a known GPT pattern - check if it's in supported list
                                        if supported_models and model_lower not in [m.lower() for m in supported_models]:
                                            return False, f"Model '{model}' is not a recognized OpenAI model"
                                
                                elif provider_name.lower() == 'gemini':
                                    # Check for invalid Gemini model names
                                    valid_patterns = ['gemini-1', 'gemini-2', 'gemini-pro']
                                    if not any(pattern in model_lower for pattern in valid_patterns):
                                        if supported_models and model_lower not in [m.lower() for m in supported_models]:
                                            return False, f"Model '{model}' is not a recognized Gemini model"
                                
                                # Try to create agent instance - this will validate everything
                                instance = self.agent_manager.create_agent_instance(custom_config)
                                if instance:
                                    return True, None
                                else:
                                    return False, f"Agent creation returned None for model '{model}'"
                        except Exception as e:
                            error_msg = str(e)
                            # Check for model not found errors
                            if 'not found' in error_msg.lower() or 'not available' in error_msg.lower():
                                return False, f"Model '{model}' not found or not available"
                            elif 'api key' in error_msg.lower() or 'api_key' in error_msg.lower():
                                return False, f"API key not configured"
                            else:
                                return False, f"Configuration error: {error_msg}"
                    else:
                        # Non-provider agent - just try to create
                        instance = self.agent_manager.create_agent_instance(custom_config)
                        if instance:
                            return True, None
                        else:
                            return False, "Agent creation failed"
            
            return False, "Unknown agent type"
        except Exception as e:
            error_msg = str(e)
            # Extract meaningful error message
            if 'not found' in error_msg.lower() or 'not available' in error_msg.lower():
                model = agent_info.get('model', 'unknown')
                return False, f"Model '{model}' not found or not available"
            elif 'api key' in error_msg.lower() or 'api_key' in error_msg.lower():
                return False, "API key not configured"
            else:
                return False, f"Validation error: {error_msg}"

    def _get_ready_agents_for_selection(self) -> List[Dict[str, Any]]:
        """
        Get all agents with Ready status for selection.
        
        This is the single modular way to select agents that have a status of Ready.
        Returns a list of agent dictionaries with 'available' == True (Ready status).
        
        Additionally validates that agents can actually be created before including them.
        Filters out agents with invalid model names or configuration issues.
        
        Ensures agent_status is up to date before filtering.
        
        Returns:
            List of agent dicts with keys: name, model, type, icon, available, etc.
            Only includes agents that pass validation.
        """
        # Ensure agent_status is up to date
        if self.agent_status is None:
            self.agent_status = AgentConfigTester.test_all()
        
        custom_agents: List[Dict[str, Any]] = self.agent_manager.list_agents()
        all_agents: List[Dict[str, Any]] = self._build_unified_agent_list(custom_agents, set())
        
        # Filter to only Ready agents (available == True)
        # This corresponds to agents with Status "Ready" in the agent status table
        ready_agents: List[Dict[str, Any]] = [agent for agent in all_agents if agent.get('available', False)]
        
        # Additional validation: actually try to create each agent to ensure it works
        validated_agents = []
        invalid_agents = []
        
        for agent in ready_agents:
            is_valid, error_msg = self._validate_agent_for_workflow(agent)
            if is_valid:
                validated_agents.append(agent)
            else:
                # Mark agent as invalid but keep for reporting
                agent['validation_error'] = error_msg
                invalid_agents.append(agent)
        
        # Log invalid agents for debugging and optionally show to user
        if invalid_agents:
            import logging
            logger = logging.getLogger(__name__)
            for agent in invalid_agents:
                logger.warning(
                    f"Agent '{agent.get('name')}' filtered from selection: {agent.get('validation_error')}"
                )
            
            # Show warning to user if there are invalid agents
            if len(validated_agents) == 0 and len(invalid_agents) > 0:
                # No valid agents available - show error
                self.console.print(
                    f"[red]No valid agents available for selection.[/red]\n"
                    f"[yellow]Found {len(invalid_agents)} agent(s) with configuration issues:[/yellow]"
                )
                for agent in invalid_agents[:5]:  # Show first 5
                    error = agent.get('validation_error', 'Unknown error')
                    self.console.print(f"  • {agent.get('name')} ({agent.get('model', 'unknown')}): {error}")
                if len(invalid_agents) > 5:
                    self.console.print(f"  ... and {len(invalid_agents) - 5} more")
            elif len(invalid_agents) > 0:
                # Some agents filtered but we have valid ones
                # Only log, don't interrupt workflow
                logger.info(
                    f"Filtered {len(invalid_agents)} invalid agent(s) from selection. "
                    f"{len(validated_agents)} valid agent(s) available."
                )
        
        return validated_agents

    def _select_ready_agent(self, prompt: str, default_hint: Optional[str] = None) -> Optional[BaseAgent]:
        """
        Modular function to select a single agent with Ready status.
        
        Args:
            prompt: Prompt text for the selection question
            default_hint: Optional hint text to display
            
        Returns:
            Selected BaseAgent instance or None if cancelled
        """
        ready_agents = self._get_ready_agents_for_selection()
        
        if not ready_agents:
            self.console.print("[red]No agents with Ready status available.[/red]")
            # Check if there are custom agents that aren't ready
            custom_agents: List[Dict[str, Any]] = self.agent_manager.list_agents()
            not_ready_custom: List[Dict[str, Any]] = []
            for agent in custom_agents:
                try:
                    instance = self.agent_manager.create_agent_instance(agent)
                    if not instance:
                        not_ready_custom.append(agent)
                except Exception as e:
                    try:
                        self.agent_manager.capture_agent_error(agent, e, "creation")
                    except Exception:
                        pass
                    not_ready_custom.append(agent)
            
            if not_ready_custom:
                self.console.print(f"[yellow]Found {len(not_ready_custom)} agent(s) with configuration issues.[/yellow]")
                fix_choice = questionary.confirm(
                    "Would you like to diagnose and fix agent configuration issues?",
                    default=True,
                    style=custom_style
                ).ask()
                if fix_choice:
                    self._fix_agent_configuration_issues(not_ready_custom)
                    # Retry after fixing
                    return self._select_ready_agent(prompt, default_hint)
            else:
                self.console.print("[yellow]Please configure agents first.[/yellow]")
            return None
        
        # Build choices from ready agents
        choices = []
        for agent in ready_agents:
            choices.append(f"{agent['icon']} {agent['name']} ({agent['model']})")
        
        choices.append("← Cancel")
        
        # Build prompt text
        prompt_text = prompt
        if default_hint:
            prompt_text += f" (Default: {default_hint})"
        prompt_text += ":"
        
        selected = questionary.select(
            prompt_text,
            choices=choices,
            style=custom_style
        ).ask()
        
        if not selected or "Cancel" in selected:
            return None
        
        # Convert selection to BaseAgent instance
        custom_agents: List[Dict[str, Any]] = self.agent_manager.list_agents()
        all_agents: List[Dict[str, Any]] = self._build_unified_agent_list(custom_agents, set())
        
        # Try to create agent and capture any errors
        try:
            agents: List[BaseAgent] = self._get_agent_from_unified_choice(selected, all_agents, custom_agents)
            
            if not agents:
                # Try to get more details about why it failed
                agent_name: Optional[str] = None
                if "⭐" in selected:
                    try:
                        parts = selected.split("⭐ ", 1)
                        if len(parts) > 1:
                            name_part = parts[1].split(" (")[0]
                            agent_name = name_part.strip()
                    except (IndexError, ValueError):
                        pass
                
                # Find the agent config to get more details
                agent_config = None
                for agent_info in all_agents:
                    if agent_info.get('name') == agent_name:
                        agent_config = agent_info.get('custom_config') or agent_info
                        break
                
                error_msg = f"[red]Error: Could not create agent from selection '{selected}'[/red]"
                if agent_config:
                    agent_type = agent_config.get('type', 'unknown')
                    provider = agent_config.get('provider', 'unknown')
                    model = agent_config.get('model', 'unknown')
                    error_msg += f"\n[dim]Agent Type: {agent_type}, Provider: {provider}, Model: {model}[/dim]"
                    
                    # Provide helpful hints based on agent type
                    if agent_type == 'provider' and provider == 'gemini':
                        error_msg += "\n[yellow]Hint: Check that GOOGLE_API_KEY is set and the model name is valid.[/yellow]"
                        error_msg += "\n[dim]Supported Gemini models: gemini-1.5-flash, gemini-1.5-pro, gemini-2.0-flash-exp[/dim]"
                    elif agent_type == 'provider' and provider == 'anthropic':
                        error_msg += "\n[yellow]Hint: Check that ANTHROPIC_API_KEY is set.[/yellow]"
                    elif agent_type == 'provider' and provider == 'openai':
                        error_msg += "\n[yellow]Hint: Check that OPENAI_API_KEY is set and model name is valid.[/yellow]"
                        error_msg += "\n[dim]Supported OpenAI models: gpt-4, gpt-4-turbo, gpt-3.5-turbo, gpt-4o, gpt-4o-mini[/dim]"
                
                self.console.print(error_msg)
                return None
            
            # Final validation: ensure the created agent is actually valid
            agent = agents[0]
            
            # Validate model name if it's a provider-backed agent
            if hasattr(agent, 'model') and agent.model:
                try:
                    from ..providers.registry import ProviderRegistry
                    ProviderRegistry.discover()
                    
                    # Try to find provider for this model
                    model_lower = agent.model.lower()
                    provider = ProviderRegistry.find_provider_for_model(model_lower)
                    
                    if provider:
                        # Check if model is in supported models
                        supported_models = provider.supported_models or []
                        if supported_models and model_lower not in [m.lower() for m in supported_models]:
                            # Model not in supported list - check for clearly invalid models
                            # Some providers are permissive, but we should catch obvious errors
                            if 'gpt-5' in model_lower or 'gpt-6' in model_lower:
                                # Clearly invalid GPT model (GPT-5 doesn't exist yet)
                                self.console.print(
                                    f"[red]Error: Model '{agent.model}' is not a valid OpenAI model.[/red]\n"
                                    f"[yellow]Supported OpenAI models: gpt-4, gpt-4-turbo, gpt-3.5-turbo, gpt-4o, gpt-4o-mini[/yellow]\n"
                                    f"[dim]Please update your agent configuration with a valid model name.[/dim]"
                                )
                                return None
                            elif provider.name == 'openai' and 'gpt' in model_lower:
                                # OpenAI provider but model not in supported list
                                # Warn but allow (provider might be permissive)
                                self.console.print(
                                    f"[yellow]Warning: Model '{agent.model}' is not in the standard OpenAI model list.[/yellow]\n"
                                    f"[dim]This may cause errors. Supported models: {', '.join(supported_models[:5])}...[/dim]"
                                )
                except Exception:
                    # If provider lookup fails, continue - agent might still work
                    pass
            
            return agent
        except Exception as e:
            # Catch any unexpected errors during agent creation
            import traceback
            error_msg = str(e)
            
            # Check for model-related errors
            if 'not found' in error_msg.lower() or 'not available' in error_msg.lower():
                self.console.print(f"[red]Error: {error_msg}[/red]")
            else:
                self.console.print(f"[red]Error creating agent: {e}[/red]")
                self.console.print(f"[dim]{traceback.format_exc()}[/dim]")
            return None

    def _count_all_available_agents(self, custom_agents: List[Dict[str, Any]]) -> Dict[str, int]:
        """Count all available (working) agents"""
        counts = {'builtin': 0, 'custom': 0, 'total': 0}
        
        # Count built-in agents
        if self.agent_status['mock']['working']:
            counts['builtin'] += 1
        if self.agent_status['claude']['working']:
            counts['builtin'] += 1
        if self.agent_status['gpt4']['working']:
            counts['builtin'] += 1
        
        # Count working custom agents
        for agent in custom_agents:
            agent_type = agent.get('type', 'unknown')
            type_info = CustomAgentManager.AGENT_TYPES.get(agent_type, {})
            api_key_env = type_info.get('api_key_env')
            
            # For openai_compatible, check the agent's own api_key_env
            if agent_type == 'openai_compatible':
                api_key_env = agent.get('api_key_env')
            
            # Check if agent can work
            if api_key_env:
                key_status = self.key_manager.get_key_status(api_key_env)
                if key_status.get('set'):
                    counts['custom'] += 1
            else:
                # No API key needed
                counts['custom'] += 1
        
        counts['total'] = counts['builtin'] + counts['custom']
        return counts

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

    def _get_agents_from_choice(self, choice: str, custom_agents: List[Dict[str, Any]] = None) -> List[BaseAgent]:
        """Convert choice to list of agents"""
        agents = []
        custom_agents = custom_agents or []
        
        if "ALL AVAILABLE AGENTS" in choice:
            # Run ALL working agents - built-in and custom
            agents = self._get_all_available_agents(custom_agents)
        elif "Mock Agent" in choice and "⭐" not in choice:
            agents.append(MockAgent(name="mock", model="mock-model"))
        elif "Both Claude + GPT-4" in choice:
            if self.agent_status['claude']['working']:
                agents.append(ClaudeAgent())
            if self.agent_status['gpt4']['working']:
                agents.append(GPT4Agent())
        elif "🤖 Claude" in choice:
            if self.agent_status['claude']['working']:
                agents.append(ClaudeAgent())
        elif "🤖 GPT-4" in choice:
            if self.agent_status['gpt4']['working']:
                agents.append(GPT4Agent())
        elif "All User Added Agents" in choice:
            # Run all working user added agents
            agents = self._get_working_custom_agents(custom_agents)
        elif "⭐" in choice:
            # Custom agent selected - find by name
            agent_name = choice.split("⭐ ")[1].split(" (")[0]
            for agent_config in custom_agents:
                if agent_config.get('name') == agent_name:
                    try:
                        instance = self.agent_manager.create_agent_instance(agent_config)
                        if instance:
                            agents.append(instance)
                    except Exception as e:
                        self.console.print(f"[red]Error creating agent: {e}[/red]")
                    break
        
        return agents

    def _get_all_available_agents(self, custom_agents: List[Dict[str, Any]]) -> List[BaseAgent]:
        """Get all available (working) agents - built-in and custom"""
        agents = []
        
        # Add built-in agents
        if self.agent_status['mock']['working']:
            agents.append(MockAgent(name="mock", model="mock-model"))
        
        if self.agent_status['claude']['working']:
            try:
                agents.append(ClaudeAgent())
            except Exception:
                pass
        
        if self.agent_status['gpt4']['working']:
            try:
                agents.append(GPT4Agent())
            except Exception:
                pass
        
        # Add working custom agents
        agents.extend(self._get_working_custom_agents(custom_agents))
        
        return agents

    def _get_working_custom_agents(self, custom_agents: List[Dict[str, Any]]) -> List[BaseAgent]:
        """Get all working custom agents"""
        agents = []
        
        for agent_config in custom_agents:
            agent_type = agent_config.get('type', 'unknown')
            type_info = CustomAgentManager.AGENT_TYPES.get(agent_type, {})
            api_key_env = type_info.get('api_key_env')
            
            # For openai_compatible, check the agent's own api_key_env
            if agent_type == 'openai_compatible':
                api_key_env = agent_config.get('api_key_env')
            
            # Check if agent can work
            can_work = True
            if api_key_env:
                key_status = self.key_manager.get_key_status(api_key_env)
                can_work = key_status.get('set', False)
            
            if can_work:
                try:
                    instance = self.agent_manager.create_agent_instance(agent_config)
                    if instance:
                        agents.append(instance)
                except Exception:
                    pass
        
        return agents

    def _fix_agent_configuration_issues(self, not_ready_agents: List[Dict[str, Any]]):
        """
        Diagnose and help fix agent configuration issues.
        
        Args:
            not_ready_agents: List of agent configs that failed to instantiate
        """
        self.show_header("Fix Agent Configuration Issues")
        
        if not not_ready_agents:
            self.console.print("[green]✓ All agents are ready![/green]")
            questionary.press_any_key_to_continue().ask()
            return
        
        self.console.print(Panel(
            f"[bold]Found {len(not_ready_agents)} agent(s) with configuration issues[/bold]\n\n"
            "This tool will help you diagnose and fix common configuration problems:\n"
            "  • Missing API keys\n"
            "  • Invalid configuration\n"
            "  • Model availability issues\n"
            "  • Network/connection problems",
            border_style="yellow"
        ))
        
        # Diagnose each agent
        issues_table = Table(title="Agent Configuration Issues", show_header=True)
        issues_table.add_column("Agent", style="bold cyan")
        issues_table.add_column("Type", style="magenta")
        issues_table.add_column("Model", style="blue")
        issues_table.add_column("Issue", style="red")
        issues_table.add_column("Fix Available", justify="center")
        
        fixable_agents = []
        
        for agent in not_ready_agents:
            agent_name = agent.get('name', 'unnamed')
            agent_type = agent.get('type', 'unknown')
            agent_model = agent.get('model', 'unknown')
            
            # Try to diagnose the issue
            issue, can_fix = self._diagnose_agent_issue(agent)
            
            if can_fix:
                fixable_agents.append((agent, issue))
                fix_status = "[green]Yes[/green]"
            else:
                fix_status = "[yellow]Manual[/yellow]"
            
            issues_table.add_row(
                agent_name,
                agent_type,
                agent_model,
                issue[:60] + ("..." if len(issue) > 60 else ""),
                fix_status
            )
        
        self.console.print("\n")
        self.console.print(issues_table)
        
        if not fixable_agents:
            self.console.print("\n[yellow]No automatically fixable issues found.[/yellow]")
            self.console.print("[dim]Please check the agent configurations manually.[/dim]")
            questionary.press_any_key_to_continue().ask()
            return
        
        # Offer to fix issues
        self.console.print("\n")
        fix_all = questionary.confirm(
            f"Would you like to fix {len(fixable_agents)} agent(s) automatically?",
            default=True,
            style=custom_style
        ).ask()
        
        if not fix_all:
            # Let user select which ones to fix
            fix_choices = []
            for agent, issue in fixable_agents:
                title = f"{agent.get('name', 'unnamed')} - {issue[:50]}"
                fix_choices.append(title)
            fix_choices.append("← Cancel")
            
            selected = select_with_filter(
                "Select agents to fix:",
                choices=fix_choices,
                style=custom_style
            )
            
            if not selected or "Cancel" in selected:
                return
            
            # Find selected agent
            selected_idx = fix_choices.index(selected) if selected in fix_choices else -1
            if selected_idx >= 0 and selected_idx < len(fixable_agents):
                fixable_agents = [fixable_agents[selected_idx]]
            else:
                return
        
        # Fix each agent
        fixed_count = 0
        for agent, issue in fixable_agents:
            self.console.print(f"\n[cyan]Fixing: {agent.get('name', 'unnamed')}[/cyan]")
            if self._fix_agent_issue(agent, issue):
                fixed_count += 1
                self.console.print(f"[green]✓ Fixed[/green]")
            else:
                self.console.print(f"[red]✗ Could not fix automatically[/red]")
        
        self.console.print(f"\n[green]Fixed {fixed_count}/{len(fixable_agents)} agent(s)[/green]")
        
        # Re-test agents
        self.console.print("\n[yellow]Re-testing agents...[/yellow]")
        self.agent_status = AgentConfigTester.test_all()
        
        questionary.press_any_key_to_continue().ask()

    def _diagnose_agent_issue(self, agent: Dict[str, Any]) -> Tuple[str, bool]:
        """
        Diagnose what's wrong with an agent configuration.
        
        Returns:
            Tuple of (issue_description, can_fix_automatically)
        """
        from typing import Tuple
        
        agent_type = agent.get('type', 'unknown')
        provider_name = agent.get('provider')
        model = agent.get('model', 'unknown')
        
        # Try to create instance to get the actual error
        try:
            instance = self.agent_manager.create_agent_instance(agent)
            if not instance:
                # Provide more specific error message
                agent_type = agent.get('type', 'unknown')
                if agent_type not in ['claude', 'gpt4', 'openai_compatible', 'mock', 'provider']:
                    return f"Invalid agent type: '{agent_type}'. Must be one of: claude, gpt4, openai_compatible, mock, provider", False
                else:
                    return "Agent creation returned None (check model name and configuration)", False
        except Exception as e:
            error_msg = str(e).lower()
            error_class = e.__class__.__name__
            
            # Check for missing API key
            if 'api' in error_msg and ('key' in error_msg or 'token' in error_msg):
                # Determine which key is needed
                if agent_type == 'claude' or provider_name == 'anthropic':
                    return "Missing ANTHROPIC_API_KEY", True
                elif agent_type == 'gpt4' or provider_name == 'openai':
                    return "Missing OPENAI_API_KEY", True
                elif agent_type == 'openai_compatible':
                    api_key_env = agent.get('api_key_env')
                    if api_key_env:
                        return f"Missing {api_key_env}", True
                    return "Missing API key (check configuration)", False
                else:
                    return "Missing API key", False
            
            # Check for model not found
            if 'not found' in error_msg or '404' in error_msg:
                return f"Model '{model}' not found or unavailable", False
            
            # Check for invalid configuration
            if 'invalid' in error_msg or 'configuration' in error_msg:
                return "Invalid configuration", False
            
            # Check for connection errors
            if 'connection' in error_msg or 'network' in error_msg or 'dns' in error_msg:
                return "Network/connection issue", False
            
            # Generic error
            return f"{error_class}: {str(e)[:50]}", False
        
        return "Unknown issue", False

    def _fix_agent_issue(self, agent: Dict[str, Any], issue: str) -> bool:
        """
        Attempt to fix an agent configuration issue.
        
        Returns:
            True if fix was successful, False otherwise
        """
        # Check if it's a missing API key issue
        if "Missing" in issue and "API_KEY" in issue:
            # Extract the key name
            if "ANTHROPIC_API_KEY" in issue:
                self._set_api_key("ANTHROPIC_API_KEY", "Claude (Anthropic)")
                # Re-test
                try:
                    instance = self.agent_manager.create_agent_instance(agent)
                    return instance is not None
                except Exception:
                    return False
            elif "OPENAI_API_KEY" in issue:
                self._set_api_key("OPENAI_API_KEY", "GPT-4 (OpenAI)")
                # Re-test
                try:
                    instance = self.agent_manager.create_agent_instance(agent)
                    return instance is not None
                except Exception:
                    return False
            elif "Missing" in issue:
                # Try to extract key name from issue
                parts = issue.split()
                for i, part in enumerate(parts):
                    if part.endswith("_API_KEY") or part.endswith("_KEY"):
                        key_name = part
                        display_name = agent.get('name', 'Agent')
                        self._set_api_key(key_name, display_name)
                        # Re-test
                        try:
                            instance = self.agent_manager.create_agent_instance(agent)
                            return instance is not None
                        except Exception:
                            return False
        
        return False

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
