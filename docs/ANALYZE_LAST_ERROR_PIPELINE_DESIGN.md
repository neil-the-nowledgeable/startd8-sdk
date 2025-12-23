## Analyze Last Error Workflow – Design Brief

### Objective
- Wire up the existing error-analysis building blocks (`error_analysis.py`, `WorkflowTemplates.error_analysis_chain`) into the TUI so that selecting “🔍 Analyze Last Error” launches a guided workflow.
- Make the flow resilient: show actionable feedback when logs are missing or no ready agents exist.
- Keep all implementation self-contained in `ImprovedTUI` (for UX) and reuse existing pipeline infrastructure.

### Current State
- Menu entry exists in `src/startd8/tui_improved.py` but no handler is invoked, so the option is a no-op.
- Log discovery/formatting lives in `src/startd8/error_analysis.py`.
- Error-analysis pipeline template already exists (`WorkflowTemplates.error_analysis_chain`).
- Agent selection helpers (`_get_ready_agents_for_selection`, `_select_ready_agent`) can be reused.

### Logging Implementation Details
The application uses **structured JSON logging** (Loki-friendly format) with the following characteristics:

- **Log Format**: JSON lines (one JSON object per line) with structured fields
- **Default Location**: `~/.startd8/logs/startd8.log` (automatically created when `get_logger()` is first called)
- **Search Paths**: 
  - `~/.startd8/logs/` (user config directory)
  - `./.startd8/logs/` (project data directory)
  - Current working directory (for `.log` files)
- **Structured Fields Available**:
  - `timestamp`: ISO format UTC timestamp
  - `level`: Log level (ERROR, CRITICAL, FATAL)
  - `logger`: Logger name (e.g., "startd8.agents", "startd8.framework")
  - `message`: Error message text
  - `exception`: Full exception traceback (if available)
  - `exception_type`: Exception class name (e.g., "APIConnectionError")
  - `exception_message`: Exception message string
  - `source`: Dict with `file`, `function`, `line` (source code location)
  - `trace_id`: OpenTelemetry trace ID (for distributed tracing)
  - `correlation_id`: Request correlation ID (for request tracking)
  - `agent_name`: Agent name (if error occurred in agent context)
  - `file_path`: File path (if relevant to the error)

- **Error Extraction**: `extract_last_error()` in `error_analysis.py` already handles JSON logs and extracts all structured fields. It falls back to plain text pattern matching for non-JSON logs.

### Requirements
1. **User Flow**
   - Triggered via `Analyze Last Error` menu.
   - Steps: locate latest error → pick analyzer agent → run pipeline → display results → optional save/export.
2. **Resilience**
   - If no log files or no error can be extracted, show a yellow panel with guidance and abort gracefully.
   - If no ready agents, reuse existing warning panel from other workflows.
   - Wrap pipeline execution with try/except to bubble up failures via red panel plus optional log path.
3. **Ergonomics**
   - Offer preview of the extracted error (timestamp, level, snippet).
   - Allow user to confirm or supply alternative text (for manually pasted errors).
   - Provide save-to-file option with sensible defaults (`analyze_last_error_{pipeline_id}.md`).

### Proposed Implementation Outline
1. **Handler Skeleton**
   - Add `def analyze_last_error_workflow(self): ...` near other workflow methods in `ImprovedTUI`.
   - Show header/panel describing the pipeline phases.
2. **Log Retrieval**
   - Call `get_last_error_from_logs()` which searches `~/.startd8/logs/`, `./.startd8/logs/`, and current directory.
   - Logs are automatically created at `~/.startd8/logs/startd8.log` when the application starts (via `get_logger()`).
   - If `None`, render guidance showing the exact directories searched and suggest running a workflow to generate logs.
3. **User Confirmation**
   - Format error via `format_error_for_analysis()` which extracts structured fields from JSON logs.
   - Display rich error preview including:
     - Timestamp (ISO format)
     - Logger name (shows which module/component failed)
     - Source location (file, function, line number)
     - Exception type and message (if available)
     - Full traceback
     - Correlation/trace IDs (for debugging distributed systems)
   - Allow editing/confirming using `questionary.text` so they can tweak the prompt.
   - Consider showing a formatted table of structured fields for better readability.
4. **Agent Selection**
   - Refresh agent status with `AgentConfigTester.test_all()`.
   - Reuse `_select_ready_agent("Select agent for error analysis")`.
5. **Run Pipeline**
   - Instantiate pipeline via `WorkflowTemplates.error_analysis_chain(analyzer_agent)` and set `pipeline.framework = self.framework`.
   - Use `self.console.status` context manager to show progress.
6. **Results + Save**
   - Print final summary panel (root cause, fix steps).
   - Provide option to save markdown file containing error context + pipeline output.
   - Consider copying to clipboard for convenience.

### Sample Code Snippets
*Hooking the menu option into the dispatcher:*
```python
# inside ImprovedTUI.run()
elif "Analyze Last Error" in choice:
    self.analyze_last_error_workflow()
```

*Core workflow skeleton for another developer to flesh out:*
```python
from .error_analysis import (
    get_last_error_from_logs,
    format_error_for_analysis,
)
from .paths import default_config_dir, default_data_dir
from rich.table import Table

def analyze_last_error_workflow(self):
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

    # Display structured error information
    formatted = format_error_for_analysis(error_info)
    
    # Show rich preview with structured fields
    preview_parts = []
    if error_info.get('timestamp'):
        preview_parts.append(f"[bold]Timestamp:[/bold] {error_info['timestamp']}")
    if error_info.get('logger'):
        preview_parts.append(f"[bold]Logger:[/bold] {error_info['logger']}")
    if error_info.get('source'):
        src = error_info['source']
        preview_parts.append(f"[bold]Source:[/bold] {src.get('file', 'Unknown')}:{src.get('line', '?')} in {src.get('function', '?')}")
    if error_info.get('exception_type'):
        preview_parts.append(f"[bold]Exception Type:[/bold] {error_info['exception_type']}")
    if error_info.get('correlation_id'):
        preview_parts.append(f"[bold]Correlation ID:[/bold] {error_info['correlation_id']}")
    if error_info.get('trace_id'):
        preview_parts.append(f"[bold]Trace ID:[/bold] {error_info['trace_id']}")
    
    preview_parts.append(f"\n[bold]Error Message:[/bold]\n{error_info.get('message', 'No message')}")
    
    if error_info.get('exception'):
        preview_parts.append(f"\n[bold]Exception/Traceback:[/bold]\n{error_info['exception']}")
    
    preview_text = '\n'.join(preview_parts)
    preview = Panel(
        preview_text[:1000] + ("\n… (truncated)" if len(preview_text) > 1000 else ""),
        title="Last Error Preview",
        border_style="cyan"
    )
    self.console.print(preview)

    proceed = questionary.confirm("Use this error for analysis?", default=True,
                                  style=custom_style).ask()
    if not proceed:
        return

    self.agent_status = AgentConfigTester.test_all()
    analyzer = self._select_ready_agent("Select agent for error analysis")
    if not analyzer:
        return

    pipeline = WorkflowTemplates.error_analysis_chain(analyzer)
    pipeline.framework = self.framework
    
    # Pass the formatted error text (includes all structured fields)
    with self.console.status("[bold green]Running analysis...[/bold green]"):
        result = pipeline.run(formatted)

    # Display results with metrics
    result_panel = Panel(
        f"[bold]Agent:[/bold] {analyzer.name} ({analyzer.model})\n"
        f"[bold]Time:[/bold] {result.total_time_ms}ms\n"
        f"[bold]Tokens:[/bold] {result.total_tokens:,}\n"
        f"[bold]Cost:[/bold] ${result.total_cost:.4f}\n\n"
        f"{result.final_output}",
        title="Error Analysis Summary",
        border_style="green"
    )
    self.console.print(result_panel)
    
    # Follow with save-to-file prompt...
    save = questionary.confirm("Save analysis to file?", default=True, style=custom_style).ask()
    if save:
        preferred_dir = self._get_preferred_output_directory()
        default_dir = preferred_dir if preferred_dir else Path.cwd()
        default_filename = f"error_analysis_{result.pipeline_id[:8]}.md"
        filename = questionary.text("Filename:", default=default_filename, style=custom_style).ask()
        
        if filename:
            filename_path = Path(filename)
            if not filename_path.is_absolute():
                filename_path = default_dir / filename_path
            
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
            
            self.console.print(f"[green]✓ Saved to {filename_path}[/green]")
```

### UX & Messaging Details
- **Success** panel: green border, include agent/model name, runtime, token cost, and full analysis output.
- **Failure** panel: red border with exception text, log file path (`error_info['file']`), and structured error details. Show correlation_id/trace_id if available for debugging.
- **No Logs**: 
  - Show exact directories searched: `~/.startd8/logs/`, `./.startd8/logs/`, and current directory.
  - Explain that logs are automatically created when workflows run (via `get_logger()`).
  - Note that logs are JSON-formatted and stored in `startd8.log` by default.
- **No Agents Ready**: reuse existing `[red]No agents with Ready status...[/red]` message plus `press any key` pause.
- **Error Preview**: Display structured fields in a readable format:
  - Use Rich Table for structured metadata (timestamp, logger, source location, exception type)
  - Show full traceback in a code block or monospace panel
  - Highlight correlation_id and trace_id if present (useful for distributed tracing)

### Testing Strategy
- **Unit Tests**: 
  - Create temp log directory with JSON-formatted `.log` file containing structured error entries.
  - Test with both JSON logs (primary) and plain text logs (fallback).
  - Verify extraction of all structured fields: timestamp, logger, source, exception_type, exception_message, trace_id, correlation_id.
  - Test error extraction from `~/.startd8/logs/startd8.log` (default location).
- **Manual Testing**: Run TUI, choose "Analyze Last Error," ensure:
  - No logs scenario shows helpful message with search paths.
  - JSON log parsing extracts all structured fields correctly.
  - Error preview displays source location, exception type, and traceback clearly.
  - Successful path saves file with full error context and analysis result.
  - Pipeline result is recorded in framework storage with proper metadata.
  - Agent selection gracefully cancels.
  - Test with errors that have correlation_id/trace_id to verify they're displayed.

### Future Enhancements (Optional)
- **Multiple Error Selection**: Allow user to pick from multiple recent errors instead of only the last one. Show a table with timestamp, logger, exception_type, and message preview.
- **Manual Paste Mode**: Support manual paste mode for errors copied from CI logs or other sources. Parse pasted text and extract error patterns.
- **Enhanced Error Preview**: 
  - Use Rich Table to display structured fields in columns (timestamp, logger, source, exception_type).
  - Add syntax highlighting for tracebacks.
  - Show correlation_id/trace_id as clickable links (if trace viewer is available).
- **Log File Selection**: Allow user to manually select a log file if auto-discovery doesn't find the right one.
- **Error Filtering**: Filter errors by logger name, exception type, or time range.
- **Auto-attach Context**: When saving results, include original JSON log entry as appendix for full context.
- **Integration with Tracing**: If trace_id is present, offer to open trace viewer or show related log entries.
