# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""queue CLI command group (extracted from cli.py, Pass E)."""

from typing import Optional, List
from typing import Optional, List
from rich.panel import Panel
from pathlib import Path
from .paths import default_data_dir
from rich.table import Table
import typer
from .cli_shared import console, get_framework, logger


queue_app = typer.Typer(
    name="queue",
    help="Job queue management commands"
)


def _get_queue_config_path(storage_dir: Optional[Path] = None) -> Path:
    """Get path to queue config file"""
    # Decision C: queue is project-scoped (store config alongside project data).
    base = storage_dir or default_data_dir()
    return base / "queue" / "config.json"


def _load_queue():
    """Load job queue module"""
    try:
        from .job_queue import (
            JobQueue, JobQueueConfig, create_job_file,
            load_queue_config, save_queue_config
        )
        from .models import JobStatus
        return JobQueue, JobQueueConfig, create_job_file, load_queue_config, save_queue_config, JobStatus
    except ImportError as e:
        console.print(f"[red]Job Queue not available: {e}[/red]")
        raise typer.Exit(1)


@queue_app.command("status")
def queue_status(
    storage_dir: Optional[Path] = typer.Option(None, "--dir", "-d", help="Storage directory")
):
    """Show queue status"""
    JobQueue, JobQueueConfig, _, load_queue_config, _, JobStatus = _load_queue()
    
    config_path = _get_queue_config_path(storage_dir)
    
    if not config_path.exists():
        console.print("[yellow]Queue not configured.[/yellow]")
        console.print("[dim]Run 'startd8 queue configure' to set up the queue.[/dim]")
        return
    
    config = load_queue_config(config_path)
    framework = get_framework(storage_dir)
    queue = JobQueue(config, framework)
    
    status = queue.get_queue_status()
    
    console.print(Panel(
        f"[bold]Watch Folder:[/bold] {status['watch_folder']}\n\n"
        f"[bold]Total Jobs:[/bold] {status['total_jobs']}\n"
        f"  • [green]Pending:[/green] {status['status_counts']['pending']}\n"
        f"  • [cyan]Processing:[/cyan] {status['status_counts']['processing']}\n"
        f"  • [blue]Completed:[/blue] {status['status_counts']['completed']}\n"
        f"  • [red]Failed:[/red] {status['status_counts']['failed']}\n\n"
        f"[bold]Running:[/bold] {'Yes' if status['is_running'] else 'No'}",
        title="Queue Status",
        border_style="cyan"
    ))


@queue_app.command("run")
def queue_run(
    once: bool = typer.Option(False, "--once", help="Process only one job and exit"),
    storage_dir: Optional[Path] = typer.Option(None, "--dir", "-d", help="Storage directory")
):
    """Process pending jobs in the queue"""
    JobQueue, JobQueueConfig, _, load_queue_config, _, JobStatus = _load_queue()
    
    config_path = _get_queue_config_path(storage_dir)
    
    if not config_path.exists():
        console.print("[red]Queue not configured. Run 'startd8 queue configure' first.[/red]")
        raise typer.Exit(1)
    
    config = load_queue_config(config_path)
    framework = get_framework(storage_dir)
    queue = JobQueue(config, framework)
    
    pending = queue.get_pending_jobs()
    
    if not pending:
        console.print("[dim]No pending jobs.[/dim]")
        return
    
    if once:
        console.print(f"[cyan]Processing 1 job...[/cyan]\n")
        result = queue.process_next()
        if result:
            status_color = "green" if result.status == JobStatus.COMPLETED else "red"
            console.print(f"[{status_color}]{result.status.value}[/{status_color}] - Job {result.job_id}")
            if result.response_ids:
                console.print(f"[dim]Responses: {len(result.response_ids)}[/dim]")
    else:
        console.print(f"[cyan]Processing {len(pending)} pending job(s)...[/cyan]\n")
        
        def on_progress(current, total, job, result):
            status_color = "green" if result.status == JobStatus.COMPLETED else "red"
            icon = "✓" if result.status == JobStatus.COMPLETED else "✗"
            console.print(f"[{status_color}]{icon}[/{status_color}] [{current}/{total}] {job.job_id[:12]}... - {result.status.value}")
        
        results = queue.process_all(on_progress=on_progress)
        
        success = sum(1 for r in results if r.status == JobStatus.COMPLETED)
        console.print(f"\n[green]✓ Completed {success}/{len(results)} jobs[/green]")
        logger.info(
            "Batch job processing completed",
            extra={
                "total_jobs": len(results),
                "successful": success,
                "failed": len(results) - success
            }
        )


@queue_app.command("watch")
def queue_watch(
    storage_dir: Optional[Path] = typer.Option(None, "--dir", "-d", help="Storage directory")
):
    """Watch folder and process jobs continuously (Ctrl+C to stop)"""
    JobQueue, JobQueueConfig, _, load_queue_config, _, JobStatus = _load_queue()
    
    config_path = _get_queue_config_path(storage_dir)
    
    if not config_path.exists():
        console.print("[red]Queue not configured. Run 'startd8 queue configure' first.[/red]")
        raise typer.Exit(1)
    
    config = load_queue_config(config_path)
    framework = get_framework(storage_dir)
    queue = JobQueue(config, framework)
    
    console.print(f"[cyan]Watching folder: {config.watch_folder}[/cyan]")
    console.print(f"[dim]Poll interval: {config.poll_interval_seconds}s[/dim]")
    console.print(f"[dim]Press Ctrl+C to stop[/dim]\n")
    
    def on_job_start(job):
        console.print(f"[cyan]▶ Starting job {job.job_id}[/cyan]")
        logger.info(f"Starting job: {job.job_id}", extra={"job_id": job.job_id})
    
    def on_job_complete(job, result):
        status_color = "green" if result.status == JobStatus.COMPLETED else "red"
        console.print(f"[{status_color}]✓ Completed job {job.job_id}[/{status_color}]")
        logger.info(f"Job completed: {job.job_id}", extra={"job_id": job.job_id, "status": "completed"})
    
    def on_job_error(job, error):
        console.print(f"[red]✗ Job {job.job_id} failed: {error}[/red]")
    
    queue.set_callbacks(
        on_start=on_job_start,
        on_complete=on_job_complete,
        on_error=on_job_error
    )
    
    try:
        queue.run_watch()
    except KeyboardInterrupt:
        console.print("\n[yellow]Watch stopped.[/yellow]")
        logger.info("Job queue watcher stopped")


@queue_app.command("add")
def queue_add(
    content: str = typer.Argument(..., help="Prompt content for the job"),
    agents: Optional[List[str]] = typer.Option(None, "--agent", "-a", help="Agents to use (can specify multiple)"),
    priority: int = typer.Option(0, "--priority", "-p", help="Job priority (higher = first)"),
    version: str = typer.Option("1.0.0", "--version", "-v", help="Prompt version"),
    name: str = typer.Option("job", "--name", "-n", help="Job file name prefix"),
    storage_dir: Optional[Path] = typer.Option(None, "--dir", "-d", help="Storage directory")
):
    """Add a new job to the queue"""
    _, _, create_job_file, load_queue_config, _, _ = _load_queue()
    
    config_path = _get_queue_config_path(storage_dir)
    
    if not config_path.exists():
        console.print("[red]Queue not configured. Run 'startd8 queue configure' first.[/red]")
        raise typer.Exit(1)
    
    config = load_queue_config(config_path)
    
    # Generate unique filename
    import uuid
    filename = f"{name}_{uuid.uuid4().hex[:8]}"
    
    file_path = create_job_file(
        output_path=config.watch_folder / filename,
        content=content,
        version=version,
        agents=agents,
        priority=priority
    )
    
    console.print(f"[green]✓ Job file created:[/green]")
    console.print(f"[dim]{file_path}[/dim]")


@queue_app.command("configure")
def queue_configure(
    watch_folder: Path = typer.Option(..., "--folder", "-f", help="Folder to watch for job files"),
    poll_interval: float = typer.Option(5.0, "--interval", "-i", help="Poll interval in seconds"),
    archive: bool = typer.Option(False, "--archive", help="Archive completed jobs"),
    default_agents: Optional[List[str]] = typer.Option(None, "--agent", "-a", help="Default agents"),
    storage_dir: Optional[Path] = typer.Option(None, "--dir", "-d", help="Storage directory")
):
    """Configure the job queue"""
    _, JobQueueConfig, _, _, save_queue_config, _ = _load_queue()
    
    watch_path = Path(watch_folder).expanduser().resolve()
    watch_path.mkdir(parents=True, exist_ok=True)
    
    archive_folder = watch_path / "completed" if archive else None
    
    config = JobQueueConfig(
        watch_folder=watch_path,
        poll_interval_seconds=poll_interval,
        archive_completed=archive,
        archive_folder=archive_folder,
        default_agents=default_agents or ["mock"]
    )
    
    config_path = _get_queue_config_path(storage_dir)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    save_queue_config(config, config_path)
    
    console.print(f"[green]✓ Queue configured![/green]")
    console.print(f"[dim]Watch folder: {watch_path}[/dim]")
    console.print(f"[dim]Config saved to: {config_path}[/dim]")
    logger.info(
        "Queue configured",
        extra={
            "watch_folder": str(watch_path),
            "config_path": str(config_path),
            "poll_interval": config.poll_interval_seconds
        }
    )


@queue_app.command("list")
def queue_list(
    all: bool = typer.Option(False, "--all", "-a", help="Include completed jobs"),
    storage_dir: Optional[Path] = typer.Option(None, "--dir", "-d", help="Storage directory")
):
    """List jobs in the queue"""
    JobQueue, JobQueueConfig, _, load_queue_config, _, JobStatus = _load_queue()
    
    config_path = _get_queue_config_path(storage_dir)
    
    if not config_path.exists():
        console.print("[yellow]Queue not configured.[/yellow]")
        return
    
    config = load_queue_config(config_path)
    framework = get_framework(storage_dir)
    queue = JobQueue(config, framework)
    
    jobs = queue.list_jobs(include_completed=all)
    
    if not jobs:
        console.print("[dim]No jobs found.[/dim]")
        logger.info("No jobs found in queue", extra={"status": status.value if status else "all"})
        return
    
    table = Table(title=f"Jobs ({len(jobs)} total)")
    table.add_column("Job ID", style="cyan")
    table.add_column("Status", justify="center")
    table.add_column("Priority", justify="center")
    table.add_column("Agents", style="green")
    table.add_column("Prompt Preview", style="white")
    
    for job in jobs[:30]:
        preview = job.prompt.content[:35] + "..." if len(job.prompt.content) > 35 else job.prompt.content
        agents = ", ".join(job.agents) if job.agents else "(default)"
        
        status_color = {
            JobStatus.PENDING: "yellow",
            JobStatus.PROCESSING: "cyan",
            JobStatus.COMPLETED: "green",
            JobStatus.FAILED: "red"
        }.get(job.status, "white")
        
        table.add_row(
            job.job_id[:12] + "...",
            f"[{status_color}]{job.status.value}[/{status_color}]",
            str(job.priority),
            agents,
            preview.replace("\n", " ")
        )
    
    console.print(table)


@queue_app.command("clear")
def queue_clear(
    storage_dir: Optional[Path] = typer.Option(None, "--dir", "-d", help="Storage directory")
):
    """Clear completed job status files"""
    JobQueue, _, _, load_queue_config, _, _ = _load_queue()
    
    config_path = _get_queue_config_path(storage_dir)
    
    if not config_path.exists():
        console.print("[yellow]Queue not configured.[/yellow]")
        return
    
    config = load_queue_config(config_path)
    framework = get_framework(storage_dir)
    queue = JobQueue(config, framework)
    
    count = queue.clear_completed()
    console.print(f"[green]✓ Cleared {count} status file(s)[/green]")
    logger.info("Cleared completed job status files", extra={"count": count})
