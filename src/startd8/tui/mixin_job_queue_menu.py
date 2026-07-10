"""JobQueueMixin: extracted from tui_improved.py ImprovedTUI (Pass B)."""

from ._shared import *  # noqa: F401,F403
from ..paths import default_config_dir


# Relocated lazy-loader state (was module-level in tui_improved.py)
# Job Queue imports (lazy loaded)
_job_queue_loaded = False
JobQueue = None
JobQueueConfig = None
JobFile = None
JobStatus = None
create_job_file = None
load_queue_config = None
save_queue_config = None


def _load_job_queue():
    """Lazy load job queue module"""
    global _job_queue_loaded, JobQueue, JobQueueConfig, JobFile, JobStatus
    global create_job_file, load_queue_config, save_queue_config
    
    if _job_queue_loaded:
        return True
    
    try:
        from ..job_queue import (
            JobQueue as JQ,
            JobQueueConfig as JQC,
            create_job_file as cjf,
            load_queue_config as lqc,
            save_queue_config as sqc
        )
        from ..models import JobFile as JF, JobStatus as JS
        
        JobQueue = JQ
        JobQueueConfig = JQC
        JobFile = JF
        JobStatus = JS
        create_job_file = cjf
        load_queue_config = lqc
        save_queue_config = sqc
        _job_queue_loaded = True
        return True
    except ImportError as e:
        console.print(f"[yellow]Job Queue not available: {e}[/yellow]")
        return False


class JobQueueMixin:
    def _get_queue_config_path(self) -> Path:
        """Get path to queue config file"""
        return (self.storage_dir or default_config_dir()) / "queue" / "config.json"

    def _load_queue_config(self) -> Optional[Any]:
        """Load queue configuration"""
        if not _load_job_queue():
            return None
        
        config_path = self._get_queue_config_path()
        if config_path.exists():
            try:
                return load_queue_config(config_path)
            except Exception:
                pass
        return None

    def _save_queue_config(self, config: Any):
        """Save queue configuration"""
        if not _load_job_queue():
            return
        
        config_path = self._get_queue_config_path()
        config_path.parent.mkdir(parents=True, exist_ok=True)
        save_queue_config(config, config_path)

    def _get_job_queue(self) -> Optional[Any]:
        """Get or create JobQueue instance"""
        if not _load_job_queue():
            return None
        
        config = self._load_queue_config()
        if not config:
            return None
        
        return JobQueue(config, self.framework)

    def job_queue_menu(self):
        """Job Queue menu"""
        if not _load_job_queue():
            self.console.print("[red]Job Queue module not available.[/red]")
            questionary.press_any_key_to_continue().ask()
            return
        
        # Show workflow intro on first run
        first_run = True
        
        while True:
            self.show_header("Job Queue")
            
            # Show workflow intro with help on first run
            if first_run:
                if self.workflow_helper and self.workflow_helper.has_workflow_help("job_queue"):
                    self.workflow_helper.show_workflow_intro("job_queue")
                    
                    # Offer to see examples
                    show_examples = questionary.confirm(
                        "\nWould you like to see workflow examples?",
                        default=False,
                        style=custom_style
                    ).ask()
                    
                    if show_examples:
                        self.workflow_helper.show_workflow_examples("job_queue")
                first_run = False
            
            # Check if queue is configured
            config = self._load_queue_config()
            
            if config:
                queue = JobQueue(config, self.framework)
                status = queue.get_queue_status()
                
                self.console.print(Panel(
                    f"[bold]Watch Folder:[/bold] {status['watch_folder']}\n"
                    f"[bold]Pending:[/bold] {status['status_counts']['pending']} | "
                    f"[bold]Processing:[/bold] {status['status_counts']['processing']} | "
                    f"[bold]Completed:[/bold] {status['status_counts']['completed']} | "
                    f"[bold]Failed:[/bold] {status['status_counts']['failed']}",
                    title="Queue Status",
                    border_style="cyan"
                ))
            else:
                self.console.print(Panel(
                    "[yellow]Job Queue not configured.[/yellow]\n"
                    "Configure a watch folder to start processing jobs.",
                    title="Queue Status",
                    border_style="yellow"
                ))
            
            choices = []
            
            if config:
                choices.extend([
                    "📋 View Pending Jobs",
                    "▶️  Process Queue (run all pending)",
                    "⏭️  Process Single Job",
                    "🔄 Send Job to Workflow",
                    "📜 View Completed Jobs",
                    "🧹 Clear Completed",
                    questionary.Separator("───"),
                ])
            
            choices.extend([
                "⚙️  Configure Queue Folder",
                "📝 Create Job File",
                "← Back to Main Menu"
            ])
            
            action = questionary.select(
                "What would you like to do?",
                choices=choices,
                style=custom_style
            ).ask()
            
            if not action or "Back" in action:
                break
            elif "View Pending" in action:
                self._view_pending_jobs()
            elif "Process Queue" in action:
                self._process_queue()
            elif "Process Single" in action:
                self._process_single_job()
            elif "Send Job to Workflow" in action:
                self._send_job_to_workflow()
            elif "View Completed" in action:
                self._view_completed_jobs()
            elif "Clear Completed" in action:
                self._clear_completed_jobs()
            elif "Configure" in action:
                self._configure_queue_folder()
            elif "Create Job" in action:
                self._create_job_file()

    def _configure_queue_folder(self):
        """Configure the queue watch folder"""
        self.show_header("Configure Queue Folder")
        
        # Get current config or defaults
        current_config = self._load_queue_config()
        
        default_folder = str(Path.home() / "startd8-jobs")
        if current_config:
            default_folder = str(current_config.watch_folder)
        
        watch_folder = self._safe_path_input(
            "Watch folder for job files:",
            default=default_folder,
            only_directories=True,
            style=custom_style
        )
        
        if not watch_folder:
            return
        
        watch_path = Path(watch_folder).expanduser().resolve()
        
        # Create folder if it doesn't exist
        try:
            watch_path.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            self.console.print(f"[red]Failed to create folder: {e}[/red]")
            questionary.press_any_key_to_continue().ask()
            return
        
        # Poll interval
        poll_interval = questionary.text(
            "Poll interval (seconds):",
            default="5.0",
            style=custom_style
        ).ask()
        
        try:
            poll_interval = float(poll_interval)
        except ValueError:
            poll_interval = 5.0
        
        # Archive completed
        archive = questionary.confirm(
            "Archive completed jobs to subfolder?",
            default=False,
            style=custom_style
        ).ask()
        
        archive_folder = None
        if archive:
            archive_folder = watch_path / "completed"
        
        # Default agents
        default_agents_str = questionary.text(
            "Default agents (comma-separated, e.g., 'claude,gpt4'):",
            default="mock",
            style=custom_style
        ).ask()
        
        default_agents = [a.strip() for a in default_agents_str.split(",") if a.strip()]
        
        # Create config
        config = JobQueueConfig(
            watch_folder=watch_path,
            poll_interval_seconds=poll_interval,
            archive_completed=archive,
            archive_folder=archive_folder,
            default_agents=default_agents
        )
        
        # Save config
        self._save_queue_config(config)
        
        self.console.print(f"\n[green]✓ Queue configured![/green]")
        self.console.print(f"[dim]Watch folder: {watch_path}[/dim]")
        self.console.print(f"[dim]Poll interval: {poll_interval}s[/dim]")
        self.console.print(f"[dim]Default agents: {', '.join(default_agents)}[/dim]")
        
        questionary.press_any_key_to_continue("\nPress any key...").ask()

    def _view_pending_jobs(self):
        """View pending jobs in queue"""
        self.show_header("Pending Jobs")
        
        queue = self._get_job_queue()
        if not queue:
            self.console.print("[yellow]Queue not configured.[/yellow]")
            questionary.press_any_key_to_continue().ask()
            return
        
        jobs = queue.get_pending_jobs()
        
        if not jobs:
            self.console.print("[dim]No pending jobs.[/dim]")
            questionary.press_any_key_to_continue().ask()
            return
        
        table = Table(title=f"Pending Jobs ({len(jobs)})")
        table.add_column("Job ID", style="cyan")
        table.add_column("Priority", justify="center")
        table.add_column("Agents", style="green")
        table.add_column("Prompt Preview", style="white")
        table.add_column("Created", style="dim")
        
        for job in jobs[:20]:
            preview = job.prompt.content[:40] + "..." if len(job.prompt.content) > 40 else job.prompt.content
            agents = ", ".join(job.agents) if job.agents else "(default)"
            created = job.created_at.strftime("%Y-%m-%d %H:%M") if job.created_at else "-"
            
            table.add_row(
                job.job_id[:12] + "...",
                str(job.priority),
                agents,
                preview.replace("\n", " "),
                created
            )
        
        self.console.print(table)
        questionary.press_any_key_to_continue("\nPress any key...").ask()

    def _view_completed_jobs(self):
        """View completed jobs"""
        self.show_header("Completed Jobs")
        
        queue = self._get_job_queue()
        if not queue:
            self.console.print("[yellow]Queue not configured.[/yellow]")
            questionary.press_any_key_to_continue().ask()
            return
        
        jobs = [j for j in queue.list_jobs(include_completed=True) 
                if j.status in (JobStatus.COMPLETED, JobStatus.FAILED)]
        
        if not jobs:
            self.console.print("[dim]No completed jobs.[/dim]")
            questionary.press_any_key_to_continue().ask()
            return
        
        table = Table(title=f"Completed Jobs ({len(jobs)})")
        table.add_column("Job ID", style="cyan")
        table.add_column("Status", justify="center")
        table.add_column("Responses", justify="center", style="green")
        table.add_column("Prompt Preview", style="white")
        table.add_column("Completed", style="dim")
        
        for job in jobs[:20]:
            preview = job.prompt.content[:40] + "..." if len(job.prompt.content) > 40 else job.prompt.content
            status_style = "green" if job.status == JobStatus.COMPLETED else "red"
            completed = job.completed_at.strftime("%Y-%m-%d %H:%M") if job.completed_at else "-"
            
            table.add_row(
                job.job_id[:12] + "...",
                f"[{status_style}]{job.status.value}[/{status_style}]",
                str(len(job.response_ids)),
                preview.replace("\n", " "),
                completed
            )
        
        self.console.print(table)
        questionary.press_any_key_to_continue("\nPress any key...").ask()

    def _process_queue(self):
        """Process all pending jobs"""
        self.show_header("Process Queue")
        
        queue = self._get_job_queue()
        if not queue:
            self.console.print("[yellow]Queue not configured.[/yellow]")
            questionary.press_any_key_to_continue().ask()
            return
        
        pending = queue.get_pending_jobs()
        
        if not pending:
            self.console.print("[dim]No pending jobs to process.[/dim]")
            questionary.press_any_key_to_continue().ask()
            return
        
        self.console.print(f"[cyan]Found {len(pending)} pending job(s).[/cyan]\n")
        
        confirm = questionary.confirm(
            f"Process all {len(pending)} jobs?",
            default=True,
            style=custom_style
        ).ask()
        
        if not confirm:
            return
        
        self.console.print("\n[cyan]Processing jobs...[/cyan]\n")
        
        def on_progress(current, total, job, result):
            status_color = "green" if result.status == JobStatus.COMPLETED else "red"
            icon = "✓" if result.status == JobStatus.COMPLETED else "✗"
            self.console.print(
                f"  [{status_color}]{icon}[/] [{current}/{total}] "
                f"Job {job.job_id[:12]}... - {result.status.value}"
            )
        
        results = queue.process_all(on_progress=on_progress)
        
        success_count = sum(1 for r in results if r.status == JobStatus.COMPLETED)
        
        self.console.print(f"\n[green]✓ Processed {success_count}/{len(results)} jobs successfully[/green]")
        questionary.press_any_key_to_continue("\nPress any key...").ask()

    def _process_single_job(self):
        """Process a single job"""
        queue = self._get_job_queue()
        if not queue:
            self.console.print("[yellow]Queue not configured.[/yellow]")
            questionary.press_any_key_to_continue().ask()
            return
        
        pending = queue.get_pending_jobs()
        
        if not pending:
            self.console.print("[dim]No pending jobs to process.[/dim]")
            questionary.press_any_key_to_continue().ask()
            return
        
        # Let user select a job
        choices = []
        for job in pending[:20]:
            preview = job.prompt.content[:30] + "..." if len(job.prompt.content) > 30 else job.prompt.content
            choices.append(f"{job.job_id[:12]}... | {preview.replace(chr(10), ' ')}")
        
        choices.append("← Cancel")
        
        selection = questionary.select(
            "Select job to process:",
            choices=choices,
            style=custom_style
        ).ask()
        
        if not selection or "Cancel" in selection:
            return
        
        # Find selected job
        job_id_prefix = selection.split(" | ")[0].replace("...", "")
        selected_job = None
        for job in pending:
            if job.job_id.startswith(job_id_prefix):
                selected_job = job
                break
        
        if not selected_job:
            self.console.print("[red]Job not found.[/red]")
            questionary.press_any_key_to_continue().ask()
            return
        
        self.console.print(f"\n[cyan]Processing job {selected_job.job_id}...[/cyan]\n")
        
        result = queue.process_job(selected_job)
        
        status_color = "green" if result.status == JobStatus.COMPLETED else "red"
        self.console.print(f"[{status_color}]Status: {result.status.value}[/{status_color}]")
        
        if result.response_ids:
            self.console.print(f"[dim]Responses generated: {len(result.response_ids)}[/dim]")
        
        if result.error:
            self.console.print(f"[red]Error: {result.error}[/red]")
        
        questionary.press_any_key_to_continue("\nPress any key...").ask()

    def _send_job_to_workflow(self):
        """Send a job from the queue to a workflow"""
        self.show_header("Send Job to Workflow")
        
        queue = self._get_job_queue()
        if not queue:
            self.console.print("[yellow]Queue not configured.[/yellow]")
            questionary.press_any_key_to_continue().ask()
            return
        
        pending = queue.get_pending_jobs()
        
        if not pending:
            self.console.print("[dim]No pending jobs to send to workflow.[/dim]")
            questionary.press_any_key_to_continue().ask()
            return
        
        # 1. Select job
        self.console.print("[bold]Select Job to Send to Workflow[/bold]\n")
        choices = []
        for job in pending[:20]:
            preview = job.prompt.content[:50] + "..." if len(job.prompt.content) > 50 else job.prompt.content
            preview = preview.replace("\n", " ").replace("\r", "")
            choices.append(f"{job.job_id[:12]}... | {preview}")
        
        choices.append("← Cancel")
        
        selection = questionary.select(
            "Select job:",
            choices=choices,
            style=custom_style
        ).ask()
        
        if not selection or "Cancel" in selection:
            return
        
        # Find selected job
        job_id_prefix = selection.split(" | ")[0].replace("...", "")
        selected_job = None
        for job in pending:
            if job.job_id.startswith(job_id_prefix):
                selected_job = job
                break
        
        if not selected_job:
            self.console.print("[red]Job not found.[/red]")
            questionary.press_any_key_to_continue().ask()
            return
        
        # Show job preview
        self.console.print(f"\n[bold]Selected Job:[/bold] {selected_job.job_id}\n")
        self.console.print(Panel(
            selected_job.prompt.content[:500] + ("..." if len(selected_job.prompt.content) > 500 else ""),
            title="Job Content Preview",
            border_style="cyan"
        ))
        
        # 2. Select workflow
        self.console.print("\n[bold]Select Workflow[/bold]\n")
        workflow_choices = [
            "✨ Design Polish Pipeline (Polish → Suggest Updates → Final Polish)",
            "🔍 Critical Review Workflow (Multi-Agent Analysis)",
            "🏛️ Architectural Review Log Workflow (Append-Only Review)",
            "📋 Convergent Review (Requirements + Plan)",
            "🔗 Document Enhancement Chain (Sequential Multi-Agent)",
            "🔄 Iterative Dev Workflow (Dev → Review → Fix)",
            "🚀 Design Pipeline (Draft → Review → Polish)",
            "← Cancel"
        ]
        
        workflow_selection = questionary.select(
            "Select workflow to run with this job:",
            choices=workflow_choices,
            style=custom_style
        ).ask()
        
        if not workflow_selection or "Cancel" in workflow_selection:
            return
        
        # 3. Run workflow with job content
        job_content = selected_job.prompt.content
        
        try:
            if "Design Polish Pipeline" in workflow_selection:
                self._run_design_polish_pipeline_from_job(selected_job, job_content)
            elif "Critical Review Workflow" in workflow_selection:
                self._run_critical_review_from_job(selected_job, job_content)
            elif "Architectural Review" in workflow_selection:
                self._run_arc_review_from_job(selected_job, job_content)
            elif "Convergent Review" in workflow_selection:
                self._run_convergent_review_from_job(selected_job, job_content)
            elif "Document Enhancement Chain" in workflow_selection:
                self._run_enhancement_chain_from_job(selected_job, job_content)
            elif "Iterative Dev Workflow" in workflow_selection:
                self._run_iterative_workflow_from_job(selected_job, job_content)
            elif "Design Pipeline" in workflow_selection:
                self._run_design_pipeline_from_job(selected_job, job_content)
            else:
                self.console.print("[red]Unknown workflow selected.[/red]")
                questionary.press_any_key_to_continue().ask()
                return
                
        except Exception as e:
            self.console.print(f"\n[red]Error running workflow: {e}[/red]")
            import traceback
            self.console.print(f"[dim]{traceback.format_exc()}[/dim]")
            questionary.press_any_key_to_continue().ask()

    def _parse_two_doc_paths_from_job_content(self, content: str) -> tuple[Optional[Path], Optional[Path]]:
        """Parse requirements and plan paths from job content (two lines).

        Returns (req_path, plan_path) if both lines are valid .md paths, else (None, None).
        """
        content_stripped = (content or "").strip()
        if not content_stripped:
            return None, None
        lines = [ln.strip() for ln in content_stripped.splitlines() if ln.strip()]
        if len(lines) < 2:
            return None, None
        req_p = Path(lines[0]).expanduser().resolve()
        plan_p = Path(lines[1]).expanduser().resolve()
        if req_p.exists() and req_p.is_file() and plan_p.exists() and plan_p.is_file():
            return req_p, plan_p
        return None, None

    def _parse_doc_path_from_job_content(self, content: str) -> Optional[Path]:
        """Parse document path from job content if it looks like a file path.

        Returns Path if content appears to be a path to an existing .md file,
        else None. Uses first line when content has multiple lines.
        """
        content_stripped = (content or "").strip()
        if not content_stripped:
            return None
        looks_like_path = (
            content_stripped.endswith(".md") or ".md" in content_stripped
            or "/" in content_stripped or "\\" in content_stripped
        )
        if not looks_like_path:
            return None
        lines = content_stripped.splitlines()
        first_line = lines[0].strip() if lines else ""
        if not first_line:
            return None
        path = Path(first_line).expanduser().resolve()
        return path if path.exists() and path.is_file() else None

    def _create_agents_from_infos(self, agent_infos: List[Dict[str, Any]]) -> List[BaseAgent]:
        """Create BaseAgent instances from TUI agent info dicts.

        Used by arc_review_workflow and other workflows that accept
        agent selection from the TUI. Handles builtin (mock, claude, gpt4)
        and custom agents via agent_manager.
        """
        agents: List[BaseAgent] = []
        for agent_info in agent_infos:
            inst = None
            if agent_info.get("type") == "builtin":
                bt = agent_info.get("builtin_type")
                if bt == "mock":
                    inst = MockAgent(name="mock", model="mock-model")
                elif bt == "claude":
                    inst = ClaudeAgent()
                elif bt == "gpt4":
                    inst = GPT4Agent()
            else:
                cfg = agent_info.get("custom_config")
                if not cfg:
                    for ca in self.agent_manager.list_agents():
                        if ca.get("name") == agent_info.get("name"):
                            cfg = ca
                            break
                if cfg:
                    inst = self.agent_manager.create_agent_instance(cfg)
            if inst:
                agents.append(inst)
        return agents


    def _create_agent_from_name(self, agent_name: str, ready_agents: List[Dict[str, Any]]) -> Optional[BaseAgent]:
        """Helper to create an agent instance from name"""
        for agent_info in ready_agents:
            if agent_info.get('name') == agent_name:
                if agent_info.get('type') == 'builtin':
                    builtin_type: Optional[str] = agent_info.get('builtin_type')
                    if builtin_type == 'mock':
                        return MockAgent(name="mock", model="mock-model")
                    elif builtin_type == 'claude':
                        return ClaudeAgent()
                    elif builtin_type == 'gpt4':
                        return GPT4Agent()
                else:
                    custom_config: Optional[Dict[str, Any]] = agent_info.get('custom_config')
                    if not custom_config:
                        custom_agents: List[Dict[str, Any]] = self.agent_manager.list_agents()
                        for custom_agent in custom_agents:
                            if custom_agent.get('name') == agent_name:
                                custom_config = custom_agent
                                break
                    
                    if custom_config:
                        return self.agent_manager.create_agent_instance(custom_config)
        return None

    def _clear_completed_jobs(self):
        """Clear completed job status files"""
        queue = self._get_job_queue()
        if not queue:
            self.console.print("[yellow]Queue not configured.[/yellow]")
            questionary.press_any_key_to_continue().ask()
            return
        
        confirm = questionary.confirm(
            "Clear all completed/failed job status files?",
            default=False,
            style=custom_style
        ).ask()
        
        if not confirm:
            return
        
        count = queue.clear_completed()
        
        self.console.print(f"\n[green]✓ Cleared {count} status file(s)[/green]")
        questionary.press_any_key_to_continue("\nPress any key...").ask()

    def _create_job_file(self):
        """Create a new job file"""
        self.show_header("Create Job File")
        
        config = self._load_queue_config()
        
        if config:
            default_folder = str(config.watch_folder)
        else:
            default_folder = str(Path.home() / "startd8-jobs")
        
        # Get output folder
        output_folder = self._safe_path_input(
            "Output folder for job file:",
            default=default_folder,
            only_directories=True,
            style=custom_style
        )
        
        if not output_folder:
            return
        
        output_path = Path(output_folder).expanduser().resolve()
        output_path.mkdir(parents=True, exist_ok=True)
        
        # Get job name
        job_name = questionary.text(
            "Job name (will be used as filename):",
            default="my_task",
            style=custom_style
        ).ask()
        
        if not job_name:
            return
        
        # Get prompt content
        self.console.print("\n[cyan]Enter prompt content (Ctrl+D or empty line to finish):[/cyan]")
        
        content_lines = []
        try:
            while True:
                line = input()
                if line == "":
                    break
                content_lines.append(line)
        except EOFError:
            pass
        
        content = "\n".join(content_lines)
        
        if not content.strip():
            self.console.print("[yellow]No content provided. Cancelled.[/yellow]")
            questionary.press_any_key_to_continue().ask()
            return
        
        # Get agents
        agents_str = questionary.text(
            "Agents (comma-separated, leave empty for default):",
            default="",
            style=custom_style
        ).ask()
        
        agents = [a.strip() for a in agents_str.split(",") if a.strip()] if agents_str else []
        
        # Get priority
        priority_str = questionary.text(
            "Priority (0-10, higher = first):",
            default="0",
            style=custom_style
        ).ask()
        
        try:
            priority = int(priority_str)
        except ValueError:
            priority = 0
        
        # Create the job file
        file_path = create_job_file(
            output_path=output_path / job_name,
            content=content,
            agents=agents if agents else None,
            priority=priority
        )
        
        self.console.print(f"\n[green]✓ Job file created:[/green]")
        self.console.print(f"[dim]{file_path}[/dim]")
        
        questionary.press_any_key_to_continue("\nPress any key...").ask()

    def _create_queue_prompt_from_analysis(self, error_info: str, analysis_result: str, saved_path: str):
        """Create a job queue prompt from error analysis results"""
        self.show_header("Create Queue Prompt from Analysis")
        
        # Generate prompt content
        prompt_content = f"""Error Analysis Summary

## Error Information
{error_info}

## Analysis Result
{analysis_result}

## Analysis File
Saved to: {saved_path}

Please review this error analysis and provide feedback or suggestions for resolution.
"""
        
        # Allow user to edit
        edited = questionary.confirm(
            "Would you like to edit the prompt before creating the job?",
            default=False,
            style=custom_style
        ).ask()
        
        if edited:
            prompt_content = questionary.text(
                "Edit prompt content:",
                default=prompt_content,
                multiline=True,
                style=custom_style
            ).ask()
            if not prompt_content:
                return
        
        # Select agents for distribution
        custom_agents = self.agent_manager.list_agents()
        ready_agents = self._get_ready_agents_for_selection()
        
        if not ready_agents:
            self.console.print("[red]No ready agents available for distribution.[/red]")
            self.console.print("[yellow]Please configure at least one agent with Ready status first.[/yellow]")
            questionary.press_any_key_to_continue().ask()
            return
        
        # Build agent choices list with proper formatting
        agent_choices = []
        for agent in ready_agents:
            # Ensure icon exists, default to empty string if not
            icon = agent.get('icon', '')
            name = agent.get('name', 'Unknown')
            model = agent.get('model', 'unknown')
            agent_choices.append(f"{icon} {name} ({model})")
        
        # Debug: Show how many agents are available
        self.console.print(f"[dim]Found {len(agent_choices)} available agent(s) for selection[/dim]\n")
        
        # Add instruction text
        self.console.print("[dim]💡 Use SPACE to select/deselect agents, ENTER to confirm selection[/dim]\n")
        
        # Show available agents count for debugging
        if len(agent_choices) == 0:
            self.console.print("[red]Error: No agent choices available. This should not happen.[/red]")
            questionary.press_any_key_to_continue().ask()
            return
        
        # Loop until at least one agent is selected or user cancels
        selected_agents = None
        retry_count = 0
        while True:
            # Show helpful message on retry
            if retry_count > 0:
                self.console.print(f"\n[cyan]Retrying agent selection (attempt {retry_count + 1})...[/cyan]\n")
                self.console.print(f"[dim]Available agents: {len(agent_choices)}[/dim]\n")
            
            selected_agents = questionary.checkbox(
                "Select agents to distribute this prompt to:",
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
            if len(selected_agents) > 0:
                # At least one agent selected - break out of loop
                self.console.print(f"[green]✓ Selected {len(selected_agents)} agent(s)[/green]\n")
                break
            
            # No agents selected - ask user what to do
            retry_count += 1
            self.console.print(f"\n[yellow]⚠️  No agents selected. At least one agent must be selected to create a job.[/yellow]")
            self.console.print(f"[dim]Available agents: {len(agent_choices)}[/dim]\n")
            
            action = questionary.select(
                "What would you like to do?",
                choices=[
                    "🔄 Select agents again",
                    "❌ Cancel job creation"
                ],
                default="🔄 Select agents again",
                style=custom_style
            ).ask()
            
            if "Cancel" in action or action is None:
                return
            # Otherwise, loop continues to retry selection
        
        # Get priority
        priority = questionary.select(
            "Job priority:",
            choices=["low", "normal", "high"],
            default="normal",
            style=custom_style
        ).ask()
        
        # Load job queue module and create job file
        if not _load_job_queue():
            self.console.print("[red]Job queue module not available. Cannot create job file.[/red]")
            questionary.press_any_key_to_continue().ask()
            return
        
        if create_job_file:
            config = self._load_queue_config()
            if config:
                watch_folder = config.watch_folder
            else:
                watch_folder = Path.home() / "startd8-jobs"
            
            watch_folder.mkdir(parents=True, exist_ok=True)
            
            # Create job file
            job_name = f"error_analysis_{Path(saved_path).stem}"
            
            # Extract agent names from selected choices
            # Format can be: "⭐ Name (model)", "🧪 Name (model)", "🤖 Name (model)", etc.
            agent_names = []
            for agent_choice in selected_agents:
                # Remove model part first: "Icon Name (model)" -> "Icon Name"
                name_part = agent_choice.split(" (")[0].strip()
                # Remove any icon emoji (⭐, 🧪, 🤖, etc.) - split by space and take last part
                # This handles: "⭐ Name", "🧪 Name", "🤖 Name", or just "Name"
                parts = name_part.split()
                if len(parts) > 1:
                    # Has icon, take everything after first part
                    agent_name = " ".join(parts[1:])
                else:
                    # No icon or just name
                    agent_name = name_part
                agent_names.append(agent_name.strip())
            
            if not agent_names:
                self.console.print("[red]Error: Could not extract agent names from selection.[/red]")
                self.console.print(f"[dim]Selected agents: {selected_agents}[/dim]")
                questionary.press_any_key_to_continue().ask()
                return
            
            job_file = create_job_file(
                prompt_content=prompt_content,
                agents=agent_names,
                priority=priority,
                output_folder=str(watch_folder / "output"),
                job_name=job_name
            )
            
            if job_file:
                job_path = watch_folder / f"{job_name}.json"
                self.console.print(f"\n[green]✓ Created job file: {job_path}[/green]")
                self.console.print(f"[dim]The job queue will process this automatically.[/dim]")
            else:
                self.console.print("[red]Failed to create job file.[/red]")
        else:
            self.console.print("[yellow]Job queue module not available.[/yellow]")
        
        questionary.press_any_key_to_continue().ask()
