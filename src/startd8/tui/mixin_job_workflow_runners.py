"""JobWorkflowRunnersMixin: extracted from JobQueueMixin (Pass C — focused sub-mixin)."""

from ._shared import *  # noqa: F401,F403


class JobWorkflowRunnersMixin:
    def _run_arc_review_from_job(self, job: Any, content: str) -> None:
        """Run Architectural Review Log Workflow from job.

        Job content may be a document path (e.g. docs/plan.md) or a prompt;
        if not parseable as path, user is prompted for the document path.
        """
        from ..logging_config import get_logger
        logger = get_logger(__name__)

        self.show_header("Architectural Review Log (from Job)")
        doc_path = self._parse_doc_path_from_job_content(content)
        doc_path_str = str(doc_path) if doc_path else None
        if not doc_path_str:
            doc_path_str = self._safe_path_input(
                "Path to markdown document to review (job content may not be a path):",
                only_directories=False,
                style=custom_style
            )
        if not doc_path_str:
            return
        doc_path = Path(doc_path_str).expanduser().resolve()
        if not doc_path.exists() or not doc_path.is_file():
            self.console.print(f"[red]File not found: {doc_path}[/red]")
            questionary.press_any_key_to_continue().ask()
            return
        config = {"document_path": str(doc_path), "reviewer_count": 2, "init_if_missing": True}
        try:
            workflow = ArchitecturalReviewLogWorkflow()
            with self.console.status("[bold green]Running architectural review...[/bold green]") as status:
                def progress_cb(c: int, t: int, m: str) -> None:
                    status.update(f"[bold green]{m} ({c}/{t})...[/bold green]")
                result = workflow.run(config=config, agents=None, on_progress=progress_cb)
            metrics = getattr(result, "metrics", None)
            total_cost = getattr(metrics, "total_cost", 0.0) if metrics else 0.0
            if result.success:
                out = result.output or {}
                self.console.print(Panel(
                    f"[green]✓ Review complete[/green]\n\n"
                    f"Document: {out.get('document_path', doc_path)}\n"
                    f"Rounds: {out.get('rounds_appended', 0)}\n"
                    f"Cost: ${total_cost:.4f}",
                    title="Review Complete",
                    border_style="green"
                ))
                logger.info(
                    "Arc review from job completed: doc=%s, rounds=%s, cost=%.4f",
                    doc_path, out.get("rounds_appended", 0), total_cost,
                )
            else:
                self.console.print(f"[red]Review failed: {result.error}[/red]")
                logger.warning("Arc review from job failed: doc=%s, error=%s", doc_path, result.error)
        except Exception as e:
            self.console.print(f"[red]Error: {e}[/red]")
            logger.exception(
                "Arc review from job raised: doc=%s, job_id=%s",
                doc_path, getattr(job, "job_id", "unknown"),
            )
        questionary.press_any_key_to_continue().ask()

    def _run_convergent_review_from_job(self, job: Any, content: str) -> None:
        """Run Convergent Review (Requirements + Plan) from job.

        Job content may be two paths (req_path, plan_path) on separate lines;
        if not parseable, user is prompted for both paths.
        """
        from ..logging_config import get_logger
        logger = get_logger(__name__)

        self.show_header("Convergent Review (Requirements + Plan) from Job")
        req_path, plan_path = self._parse_two_doc_paths_from_job_content(content)
        if not req_path or not plan_path:
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
        config = {
            "requirements_path": str(req_path),
            "plan_path": str(plan_path),
            "reviewer_count": 2,
        }
        try:
            workflow = ConvergentReviewWorkflow()
            with self.console.status(
                "[bold green]Running convergent review (requirements → plan)...[/bold green]"
            ) as status:
                def progress_cb(c: int, t: int, m: str) -> None:
                    status.update(f"[bold green]{m} ({c}/{t})...[/bold green]")
                result = workflow.run(config=config, agents=None, on_progress=progress_cb)
            metrics = getattr(result, "metrics", None)
            total_cost = getattr(metrics, "total_cost", 0.0) if metrics else 0.0
            if result.success:
                out = result.output or {}
                req_out = out.get("requirements_review") or {}
                plan_out = out.get("plan_review") or {}
                self.console.print(Panel(
                    f"[green]✓ Convergent review complete[/green]\n\n"
                    f"Requirements: {req_path.name} — {req_out.get('rounds_appended', 0)} rounds\n"
                    f"Plan: {plan_path.name} — {plan_out.get('rounds_appended', 0)} rounds\n"
                    f"Cost: ${total_cost:.4f}",
                    title="Review Complete",
                    border_style="green",
                ))
                logger.info(
                    "Convergent review from job completed: req=%s, plan=%s, cost=%.4f",
                    req_path, plan_path, total_cost,
                )
            else:
                self.console.print(f"[red]Review failed: {result.error}[/red]")
                logger.warning(
                    "Convergent review from job failed: req=%s, plan=%s, error=%s",
                    req_path, plan_path, result.error,
                )
        except Exception as e:
            self.console.print(f"[red]Error: {e}[/red]")
            logger.exception(
                "Convergent review from job raised: req=%s, plan=%s, job_id=%s",
                req_path, plan_path, getattr(job, "job_id", "unknown"),
            )
        questionary.press_any_key_to_continue().ask()

    def _run_design_polish_pipeline_from_job(self, job, content: str):
        """Run Design Polish Pipeline with job content"""
        self.show_header("Design Polish Pipeline (from Job)")
        
        # Show job content preview first
        self.console.print("[bold]Job Content Preview[/bold]\n")
        preview_text = content[:500] + ("..." if len(content) > 500 else "")
        self.console.print(Panel(
            preview_text,
            title=f"Job {job.job_id[:12]} - Content ({len(content)} characters)",
            border_style="cyan"
        ))
        
        # Option to edit content before proceeding
        edit_content = questionary.confirm(
            "\nWould you like to edit the content before proceeding?",
            default=False,
            style=custom_style
        ).ask()
        
        if edit_content:
            edited_content = questionary.text(
                "Edit the content:",
                default=content,
                multiline=True,
                style=custom_style
            ).ask()
            
            if edited_content and edited_content.strip():
                content = edited_content
                self.console.print("[green]✓ Content updated[/green]\n")
            else:
                self.console.print("[yellow]No changes made, using original content.[/yellow]\n")
        
        self.console.print("[cyan]Selecting agents for pipeline...[/cyan]\n")
        
        # Get agents for the pipeline
        ready_agents = self._get_ready_agents_for_selection()
        if len(ready_agents) < 3:
            self.console.print("[red]Need at least 3 agents for Design Polish Pipeline.[/red]")
            questionary.press_any_key_to_continue().ask()
            return
        
        # Select agents
        agent_choices = [f"{a['icon']} {a['name']} ({a['model']})" for a in ready_agents]
        
        polisher_choice = questionary.select(
            "Select polisher agent:",
            choices=agent_choices,
            style=custom_style
        ).ask()
        
        updater_choice = questionary.select(
            "Select updater agent:",
            choices=agent_choices,
            style=custom_style
        ).ask()
        
        final_polisher_choice = questionary.select(
            "Select final polisher agent:",
            choices=agent_choices,
            style=custom_style
        ).ask()
        
        # Extract agent names
        polisher_name = polisher_choice.split(" (")[0].split(" ", 1)[1] if " " in polisher_choice.split(" (")[0] else polisher_choice.split(" (")[0]
        updater_name = updater_choice.split(" (")[0].split(" ", 1)[1] if " " in updater_choice.split(" (")[0] else updater_choice.split(" (")[0]
        final_polisher_name = final_polisher_choice.split(" (")[0].split(" ", 1)[1] if " " in final_polisher_choice.split(" (")[0] else final_polisher_choice.split(" (")[0]
        
        # Create agents
        polisher = self._create_agent_from_name(polisher_name, ready_agents)
        updater = self._create_agent_from_name(updater_name, ready_agents)
        final_polisher = self._create_agent_from_name(final_polisher_name, ready_agents)
        
        if not all([polisher, updater, final_polisher]):
            self.console.print("[red]Failed to create agents.[/red]")
            questionary.press_any_key_to_continue().ask()
            return
        
        # Run pipeline using extracted workflow class
        try:
            from datetime import datetime, timezone

            workflow = DesignPolishWorkflow()
            workflow_result = workflow.run(
                config={"document": content},
                agents=[polisher, updater, final_polisher]
            )

            if not workflow_result.success:
                raise Exception(workflow_result.error or "Workflow failed")

            # Save result
            output_dir = Path.cwd() / "workflow_results"
            output_dir.mkdir(exist_ok=True)
            output_file = output_dir / f"job_{job.job_id[:12]}_design_polish_{workflow_result.workflow_id}.md"

            file_content = f"# Design Polish Pipeline Result\n\n"
            file_content += f"**Job ID:** {job.job_id}\n"
            file_content += f"**Workflow ID:** {workflow_result.workflow_id}\n"
            file_content += f"**Generated:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}\n\n"
            file_content += "---\n\n"
            file_content += workflow_result.output
            file_content += "\n\n---\n\n"
            file_content += "## Pipeline Steps\n\n"
            for step in workflow_result.steps:
                file_content += f"### {step.step_name} ({step.agent_name})\n\n"
                file_content += f"{step.output}\n\n"

            saved_path = save_text_file_with_versioning(output_file, file_content)
            self.console.print(f"\n[green]✓ Pipeline completed successfully![/green]")
            self.console.print(f"[green]✓ Saved to: {saved_path}[/green]")
            self.console.print(f"\n[dim]Total cost: ${workflow_result.metrics.total_cost:.4f}[/dim]")
            self.console.print(f"[dim]Total time: {workflow_result.metrics.total_time_ms}ms[/dim]")
            
        except Exception as e:
            self.console.print(f"\n[red]Pipeline failed: {e}[/red]")
            import traceback
            self.console.print(f"[dim]{traceback.format_exc()}[/dim]")
        
        questionary.press_any_key_to_continue().ask()

    def _run_critical_review_from_job(self, job, content: str):
        """Run Critical Review Workflow with job content as a document"""
        self.show_header("Critical Review Workflow (from Job)")
        
        self.console.print("[cyan]Running Critical Review Workflow with job content...[/cyan]\n")
        
        # Get agents
        ready_agents = self._get_ready_agents_for_selection()
        if not ready_agents:
            self.console.print("[red]No ready agents available.[/red]")
            questionary.press_any_key_to_continue().ask()
            return
        
        # Select agents
        agent_choices = [f"{a['icon']} {a['name']} ({a['model']})" for a in ready_agents]
        
        self.console.print("[dim]💡 Use SPACE to select/deselect agents, ENTER to confirm[/dim]\n")
        selected_agents = None
        while True:
            selected_agents = questionary.checkbox(
                "Select agents for critical review:",
                choices=agent_choices,
                style=custom_style,
                instruction="(Press SPACE to select, ENTER to confirm)"
            ).ask()
            
            # Handle cancellation (Ctrl+C)
            if selected_agents is None:
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
            
            # Extract agent info
            selected_agent_infos = []
            for agent_choice in selected_agents:
                name_part = agent_choice.split(" (")[0].strip()
                parts = name_part.split()
                if len(parts) > 1:
                    agent_name = " ".join(parts[1:])
                else:
                    agent_name = name_part
                
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
        
        # Output directory
        output_dir = Path.cwd() / "critical_reviews"
        output_dir.mkdir(exist_ok=True)
        
        # Review prompt template
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
        
        self.console.print(f"\n[cyan]Generating reviews with {len(selected_agent_infos)} agent(s)...[/cyan]\n")
        
        all_results = []
        
        try:
            for agent_info in selected_agent_infos:
                agent_name = agent_info.get('name', 'Unknown')
                agent_model = agent_info.get('model', 'unknown')
                
                agent_instance = self._create_agent_from_name(agent_name, ready_agents)
                if not agent_instance:
                    all_results.append({
                        'agent': agent_name,
                        'success': False,
                        'error': 'Failed to create agent'
                    })
                    continue
                
                # Generate review
                review_prompt = review_prompt_template.format(document_content=content)
                response_tuple = agent_instance.generate(review_prompt)
                
                # Extract response
                if isinstance(response_tuple, tuple) and len(response_tuple) >= 1:
                    review_text = response_tuple[0]
                else:
                    review_text = str(response_tuple)
                
                # Save review
                safe_agent_name = agent_name.replace(" ", "_").replace("/", "_")
                output_filename = f"job_{job.job_id[:12]}_review_{safe_agent_name}.md"
                output_path = output_dir / output_filename
                
                from datetime import datetime, timezone
                with open(output_path, 'w', encoding='utf-8') as f:
                    f.write(f"# Critical Review: Job {job.job_id[:12]}\n\n")
                    f.write(f"**Reviewed by:** {agent_name} ({agent_model})\n")
                    f.write(f"**Job ID:** {job.job_id}\n")
                    f.write(f"**Review Date:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}\n\n")
                    f.write("---\n\n")
                    f.write(review_text)
                
                all_results.append({
                    'agent': agent_name,
                    'output_path': output_path,
                    'success': True
                })
            
            # Show results
            self.console.print("\n[bold cyan]Review Complete![/bold cyan]\n")
            for result in all_results:
                if result['success']:
                    self.console.print(f"[green]✓[/green] {result['agent']}: {result['output_path'].name}")
                else:
                    self.console.print(f"[red]✗[/red] {result['agent']}: {result.get('error', 'Unknown error')}")
            
            self.console.print(f"\n[cyan]Output directory:[/cyan] {output_dir}")
            
        except Exception as e:
            self.console.print(f"\n[red]Error: {e}[/red]")
            import traceback
            self.console.print(f"[dim]{traceback.format_exc()}[/dim]")
        
        questionary.press_any_key_to_continue().ask()

    def _run_enhancement_chain_from_job(self, job, content: str):
        """Run Document Enhancement Chain with job content"""
        self.show_header("Document Enhancement Chain (from Job)")
        
        self.console.print("[cyan]Running Document Enhancement Chain with job content...[/cyan]\n")
        
        # Use the existing document enhancement chain menu but with job content
        # We'll create a temporary file or pass content directly
        from ..document_enhancement import DocumentEnhancementChain
        
        ready_agents = self._get_ready_agents_for_selection()
        if not ready_agents:
            self.console.print("[red]No ready agents available.[/red]")
            questionary.press_any_key_to_continue().ask()
            return
        
        # Select agents for the chain
        agent_choices = [f"{a['icon']} {a['name']} ({a['model']})" for a in ready_agents]
        
        self.console.print("[dim]💡 Use SPACE to select/deselect agents, ENTER to confirm[/dim]\n")
        selected_agents = None
        while True:
            selected_agents = questionary.checkbox(
                "Select agents for enhancement chain (in order):",
                choices=agent_choices,
                style=custom_style,
                instruction="(Press SPACE to select, ENTER to confirm)"
            ).ask()
            
            # Handle cancellation (Ctrl+C)
            if selected_agents is None:
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
            
            # Create agents
            chain_agents = []
            for agent_choice in selected_agents:
                name_part = agent_choice.split(" (")[0].strip()
                parts = name_part.split()
                if len(parts) > 1:
                    agent_name = " ".join(parts[1:])
                else:
                    agent_name = name_part
                
                agent = self._create_agent_from_name(agent_name, ready_agents)
                if agent:
                    chain_agents.append(agent)
            
            # Validate that we successfully created at least one agent
            if len(chain_agents) == 0:
                self.console.print("[red]Error: Failed to create agents. Please try again.[/red]")
                retry = questionary.confirm("Select agents again?", default=True, style=custom_style).ask()
                if not retry:
                    return
                continue
            
            # Successfully selected and created agents
            break
        
        # Run enhancement chain
        try:
            from datetime import datetime, timezone
            config = DocumentEnhancementConfig(
                agents=[EnhancementAgentConfig(name=a.name, model=a.model) for a in chain_agents],
                error_handling=ErrorHandling.CONTINUE_ON_ERROR
            )
            
            chain = DocumentEnhancementChain(config, self.framework)
            result = chain.run(content)
            
            # Save result
            output_dir = Path.cwd() / "workflow_results"
            output_dir.mkdir(exist_ok=True)
            output_file = output_dir / f"job_{job.job_id[:12]}_enhancement_chain.md"
            
            content = f"# Document Enhancement Chain Result\n\n"
            content += f"**Job ID:** {job.job_id}\n"
            content += f"**Generated:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}\n\n"
            content += "---\n\n"
            content += result.final_output
            content += "\n\n---\n\n"
            content += "## Enhancement Steps\n\n"
            for i, step in enumerate(result.steps, 1):
                content += f"### Step {i}: {step.get('agent_name', 'Unknown')}\n\n"
                content += f"{step.get('output', '')}\n\n"
            
            saved_path = save_text_file_with_versioning(output_file, content)
            self.console.print(f"\n[green]✓ Enhancement chain completed![/green]")
            self.console.print(f"[green]✓ Saved to: {saved_path}[/green]")
            
        except Exception as e:
            self.console.print(f"\n[red]Enhancement chain failed: {e}[/red]")
            import traceback
            self.console.print(f"[dim]{traceback.format_exc()}[/dim]")
        
        questionary.press_any_key_to_continue().ask()

    def _run_iterative_workflow_from_job(self, job, content: str):
        """Run Iterative Dev Workflow with job content"""
        self.show_header("Iterative Dev Workflow (from Job)")
        
        self.console.print("[yellow]Iterative Dev Workflow requires interactive input.[/yellow]")
        self.console.print("[yellow]This workflow is best run directly from the menu.[/yellow]\n")
        
        use_as_prompt = questionary.confirm(
            "Use job content as the initial prompt for iterative workflow?",
            default=True,
            style=custom_style
        ).ask()
        
        if not use_as_prompt:
            return
        
        # Store the job content as current prompt and run iterative workflow
        # This is a simplified approach - the full iterative workflow has more steps
        self.console.print("\n[cyan]Note: Full iterative workflow requires multiple interactive steps.[/cyan]")
        self.console.print("[cyan]Consider using the Iterative Dev Workflow menu option directly.[/cyan]\n")
        
        questionary.press_any_key_to_continue().ask()

    def _run_design_pipeline_from_job(self, job, content: str):
        """Run Design Pipeline with job content"""
        self.show_header("Design Pipeline (from Job)")
        
        self.console.print("[cyan]Running Design Pipeline with job content...[/cyan]\n")
        
        ready_agents = self._get_ready_agents_for_selection()
        if len(ready_agents) < 3:
            self.console.print("[red]Need at least 3 agents for Design Pipeline.[/red]")
            questionary.press_any_key_to_continue().ask()
            return
        
        # Select agents
        agent_choices = [f"{a['icon']} {a['name']} ({a['model']})" for a in ready_agents]
        
        drafter_choice = questionary.select("Select drafter agent:", choices=agent_choices, style=custom_style).ask()
        reviewer_choice = questionary.select("Select reviewer agent:", choices=agent_choices, style=custom_style).ask()
        final_reviewer_choice = questionary.select("Select final reviewer agent:", choices=agent_choices, style=custom_style).ask()
        
        # Extract and create agents
        drafter_name = drafter_choice.split(" (")[0].split(" ", 1)[1] if " " in drafter_choice.split(" (")[0] else drafter_choice.split(" (")[0]
        reviewer_name = reviewer_choice.split(" (")[0].split(" ", 1)[1] if " " in reviewer_choice.split(" (")[0] else reviewer_choice.split(" (")[0]
        final_reviewer_name = final_reviewer_choice.split(" (")[0].split(" ", 1)[1] if " " in final_reviewer_choice.split(" (")[0] else final_reviewer_choice.split(" (")[0]
        
        drafter = self._create_agent_from_name(drafter_name, ready_agents)
        reviewer = self._create_agent_from_name(reviewer_name, ready_agents)
        final_reviewer = self._create_agent_from_name(final_reviewer_name, ready_agents)
        
        if not all([drafter, reviewer, final_reviewer]):
            self.console.print("[red]Failed to create agents.[/red]")
            questionary.press_any_key_to_continue().ask()
            return
        
        # Run pipeline
        try:
            from datetime import datetime, timezone
            from ..orchestration import WorkflowTemplates
            pipeline = WorkflowTemplates.design_review_chain(drafter, reviewer, final_reviewer)
            pipeline.framework = self.framework
            
            result = pipeline.run(content)
            
            # Save result
            output_dir = Path.cwd() / "workflow_results"
            output_dir.mkdir(exist_ok=True)
            output_file = output_dir / f"job_{job.job_id[:12]}_design_pipeline_{result.pipeline_id[:8]}.md"
            
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(f"# Design Pipeline Result\n\n")
                f.write(f"**Job ID:** {job.job_id}\n")
                f.write(f"**Pipeline ID:** {result.pipeline_id}\n")
                f.write(f"**Generated:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}\n\n")
                f.write("---\n\n")
                f.write(result.final_output)
                f.write("\n\n---\n\n")
                f.write("## Pipeline Steps\n\n")
                for step in result.steps:
                    f.write(f"### {step['step_name']} ({step['agent']})\n\n")
                    f.write(f"{step['output']}\n\n")
            
            self.console.print(f"\n[green]✓ Pipeline completed successfully![/green]")
            self.console.print(f"[green]✓ Saved to: {output_file}[/green]")
            self.console.print(f"\n[dim]Total cost: ${result.total_cost:.4f}[/dim]")
            self.console.print(f"[dim]Total time: {result.total_time_ms}ms[/dim]")
            
        except Exception as e:
            self.console.print(f"\n[red]Pipeline failed: {e}[/red]")
            import traceback
            self.console.print(f"[dim]{traceback.format_exc()}[/dim]")
        
        questionary.press_any_key_to_continue().ask()
