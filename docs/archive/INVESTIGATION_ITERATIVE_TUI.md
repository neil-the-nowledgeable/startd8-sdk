# Investigation: Iterative Dev Workflow Not Working in TUI

**Date**: December 7, 2025  
**Status**: ✅ RESOLVED (December 9, 2025)  
**Severity**: 🔴 Feature Completely Broken → ✅ Feature Complete + Enhanced

**Update**: Feature has been fully implemented and enhanced with file-based input support.  
See: `IMPLEMENTATION_COMPLETE.md` and `FILE_INPUT_FEATURE.md`

---

## Summary

The "🔄 Iterative Dev Workflow (Dev → Review → Fix)" menu option appears in the TUI but **does nothing when selected** because:

1. ✅ Menu item was added to `main_menu()` (line 2031)
2. ❌ **NO handler was added** to `run()` method (lines 4806-4863)
3. ❌ **NO implementation method exists** (e.g., `_run_iterative_workflow()`)
4. ❌ **NO import** of `IterativeDevWorkflow` in `tui_improved.py`

---

## Root Cause Analysis

### What Was Done

**File**: `src/startd8/tui_improved.py`

**Line 2031** - Menu option was added:
```python
choices.append("🔄 Iterative Dev Workflow (Dev → Review → Fix)")
```

### What Was NOT Done

**1. Missing Handler in `run()` Method (lines 4814-4863)**

The `run()` method handles menu selections with a series of `if/elif` statements:

```python
def run(self):
    while True:
        choice = self.main_menu()
        
        if "Create New Prompt" in choice:
            self.step1_create_prompt()
        elif "Prompt Builder" in choice:
            self.prompt_builder_menu()
        elif "Enhancement Chain" in choice:
            self.document_enhancement_chain_menu()
        elif "Run Design Pipeline" in choice:
            self.step2_run_design_review_chain()
        elif "Job Queue" in choice:
            self.job_queue_menu()
        # ... other handlers ...
        
        # ❌ MISSING: No handler for "Iterative" in choice!
```

**2. Missing Implementation Method**

No method like `_run_iterative_workflow()` or `iterative_workflow_menu()` exists.

**3. Missing Import**

The file doesn't import the `IterativeDevWorkflow` class:

```python
# These imports exist:
from .document_enhancement import DocumentEnhancementChain
from .orchestration import Pipeline, WorkflowTemplates

# This import is MISSING:
# from .iterative_workflow import IterativeDevWorkflow, IterativeWorkflowResult
```

---

## Behavior When Selected

When user selects "🔄 Iterative Dev Workflow (Dev → Review → Fix)":

1. `main_menu()` returns `"🔄 Iterative Dev Workflow (Dev → Review → Fix)"`
2. `run()` evaluates all `if/elif` conditions
3. **None match** (no `"Iterative" in choice` check exists)
4. Control falls through to end of `while True` loop
5. Loop continues, showing main menu again
6. **User sees no feedback** - it appears nothing happened

---

## Evidence

### Menu Option Present (Line 2031)
```python
choices.append("🔄 Iterative Dev Workflow (Dev → Review → Fix)")
```

### Handler Missing in run() (Lines 4822-4863)
```python
if "Create New Prompt" in choice:
    self.step1_create_prompt()
elif "Prompt Builder" in choice:
    self.prompt_builder_menu()
elif "Enhance Prompt File" in choice:
    self.enhance_prompt_file_menu()
elif "Document Updater" in choice:
    self.document_updater_menu()
elif "Enhancement Chain" in choice:
    self.document_enhancement_chain_menu()
elif "Run Design Pipeline" in choice:
    self.step2_run_design_review_chain()
elif "Job Queue" in choice:
    self.job_queue_menu()
# ... continues with other handlers ...
# ❌ NO "Iterative" handler exists
```

### No Implementation Method
```bash
grep -n "iterative" src/startd8/tui_improved.py
# Result: Only line 2031 (the menu item)
```

### No Import
```bash
grep -n "from .iterative_workflow" src/startd8/tui_improved.py
# Result: No matches
```

---

## Impact

- **User Experience**: Menu option appears but does nothing - confusing UX
- **Feature Availability**: Entire iterative workflow feature is inaccessible via TUI
- **Workaround**: Users must use Python API directly (not discoverable)

---

## Fix Required

### Three Components Needed:

1. **Add Import** (top of file, ~line 30-35)
2. **Add Handler** in `run()` method (~line 4833, after "Design Pipeline")
3. **Implement Menu Method** (new method: `iterative_workflow_menu()`)

---

# Implementation Plan

## Overview

**Effort**: 4-6 hours  
**Files Modified**: 1 (`src/startd8/tui_improved.py`)  
**New Methods**: 1-2 (main menu + optional wizard)

---

## Task 1: Add Import Statement

**Location**: `src/startd8/tui_improved.py`, lines 28-36  
**Effort**: 5 minutes

### Action
Add import after existing workflow imports:

```python
# Existing imports (around line 30-31):
from .orchestration import Pipeline, WorkflowTemplates
from .document_enhancement import DocumentEnhancementChain

# Add this import:
from .iterative_workflow import IterativeDevWorkflow, IterativeWorkflowResult, save_workflow_result
```

### Acceptance Criteria
- [ ] Import statement added
- [ ] No circular import errors
- [ ] TUI still starts successfully

---

## Task 2: Add Handler in run() Method

**Location**: `src/startd8/tui_improved.py`, line ~4833 (after "Design Pipeline" handler)  
**Effort**: 5 minutes

### Action
Add handler in the `run()` method's if/elif chain:

```python
# Existing handler (line 4832-4833):
elif "Run Design Pipeline" in choice:
    self.step2_run_design_review_chain()

# Add this handler:
elif "Iterative" in choice:
    self.iterative_workflow_menu()

# Existing handler (line 4834-4835):
elif "Job Queue" in choice:
    self.job_queue_menu()
```

### Acceptance Criteria
- [ ] Handler added in correct location
- [ ] String match is unambiguous ("Iterative" is unique)
- [ ] Calls new menu method

---

## Task 3: Implement iterative_workflow_menu() Method

**Location**: `src/startd8/tui_improved.py`, after similar workflow methods  
**Effort**: 3-5 hours

### Overview
Create a comprehensive menu method similar to `document_enhancement_chain_menu()` or `step2_run_design_review_chain()`.

### Method Structure

```python
def iterative_workflow_menu(self):
    """Interactive menu for iterative dev-review-fix workflow"""
    
    # 1. Show header and introduction
    self.show_header("Iterative Dev Workflow")
    self._show_iterative_intro_panel()
    
    # 2. Get task description
    task = self._get_task_description()
    if not task:
        return
    
    # 3. Select developer agent
    dev_agent = self._select_agent_for_role("Developer")
    if not dev_agent:
        return
    
    # 4. Select reviewer agent
    review_agent = self._select_agent_for_role("Reviewer")
    if not review_agent:
        return
    
    # 5. Configure options (max iterations, etc.)
    config = self._configure_iterative_workflow()
    if not config:
        return
    
    # 6. Show confirmation
    if not self._confirm_iterative_workflow(task, dev_agent, review_agent, config):
        return
    
    # 7. Run workflow with progress display
    result = self._execute_iterative_workflow(task, dev_agent, review_agent, config)
    
    # 8. Display results
    if result:
        self._display_iterative_results(result)
```

### Sub-Methods Needed

#### 3.1: Introduction Panel
```python
def _show_iterative_intro_panel(self):
    """Show introduction to iterative workflow"""
    self.console.print(Panel(
        "[bold cyan]Iterative Dev-Review-Fix Workflow[/bold cyan]\n\n"
        "This workflow automates the development cycle:\n\n"
        "  1️⃣  [bold]Developer Agent[/bold] implements your task\n"
        "  2️⃣  [bold]Reviewer Agent[/bold] checks the code\n"
        "  3️⃣  If issues found → Developer fixes them\n"
        "  4️⃣  Repeat until code passes review\n\n"
        "[dim]Best results: Use different agents for dev and review[/dim]",
        title="🔄 Dev → Review → Fix Loop",
        border_style="cyan"
    ))
```

#### 3.2: Task Description Input
```python
def _get_task_description(self) -> Optional[str]:
    """Get task description from user"""
    self.console.print("\n[bold]Enter your development task:[/bold]")
    self.console.print("[dim]Example: 'Implement a function to validate email addresses'[/dim]\n")
    
    task = questionary.text(
        "Task:",
        multiline=True,
        style=custom_style
    ).ask()
    
    if not task or not task.strip():
        self.console.print("[yellow]No task provided. Cancelled.[/yellow]")
        questionary.press_any_key_to_continue().ask()
        return None
    
    return task.strip()
```

#### 3.3: Agent Selection (reuse existing `_select_ready_agent()`)
```python
def _select_agent_for_role(self, role: str) -> Optional[BaseAgent]:
    """Select an agent for a specific role"""
    self.console.print(f"\n[bold]Select {role} Agent:[/bold]")
    
    # Reuse existing ready agent selection
    return self._select_ready_agent(
        f"Choose agent for {role}",
        default_hint="Claude" if role == "Developer" else "GPT-4"
    )
```

#### 3.4: Configuration Options
```python
def _configure_iterative_workflow(self) -> Optional[Dict[str, Any]]:
    """Configure workflow options"""
    self.console.print("\n[bold]Configuration:[/bold]")
    
    # Max iterations
    max_iter_str = questionary.text(
        "Maximum iterations (1-10):",
        default="3",
        style=custom_style
    ).ask()
    
    try:
        max_iterations = int(max_iter_str)
        max_iterations = max(1, min(10, max_iterations))
    except ValueError:
        max_iterations = 3
    
    # Optional: Save intermediate results
    save_results = questionary.confirm(
        "Save workflow results to file?",
        default=True,
        style=custom_style
    ).ask()
    
    return {
        'max_iterations': max_iterations,
        'save_results': save_results
    }
```

#### 3.5: Confirmation Panel
```python
def _confirm_iterative_workflow(
    self,
    task: str,
    dev_agent: BaseAgent,
    review_agent: BaseAgent,
    config: Dict[str, Any]
) -> bool:
    """Show confirmation and get user approval"""
    
    task_preview = task[:200] + "..." if len(task) > 200 else task
    
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
```

#### 3.6: Execution with Progress
```python
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
            save_workflow_result(result, output_dir)
            self.console.print(f"[dim]Results saved to {output_dir}[/dim]")
        
        return result
        
    except Exception as e:
        self.console.print(f"[red]Error: {e}[/red]")
        questionary.press_any_key_to_continue().ask()
        return None
```

#### 3.7: Results Display
```python
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
```

#### 3.8: Iteration Details View
```python
def _show_iteration_details(self, result: IterativeWorkflowResult):
    """Show detailed view of each iteration"""
    for iteration in result.iterations:
        status = "PASSED" if iteration.feedback and iteration.feedback.passed else "FAILED"
        color = "green" if status == "PASSED" else "red"
        
        self.console.print(Panel(
            f"[bold]Status:[/bold] [{color}]{status}[/{color}]\n"
            f"[bold]Dev Time:[/bold] {iteration.dev_time_ms}ms\n"
            f"[bold]Review Time:[/bold] {iteration.review_time_ms}ms\n"
            f"[bold]Score:[/bold] {iteration.feedback.score if iteration.feedback else 'N/A'}/100\n"
            f"[bold]Issues:[/bold] {len(iteration.feedback.issues) if iteration.feedback else 0}\n"
            f"[bold]Suggestions:[/bold] {len(iteration.feedback.suggestions) if iteration.feedback else 0}",
            title=f"Iteration {iteration.iteration_number}",
            border_style=color
        ))
        
        if iteration.feedback and iteration.feedback.issues:
            self.console.print("[bold]Issues:[/bold]")
            for issue in iteration.feedback.issues:
                self.console.print(f"  • {issue}")
            self.console.print()
    
    questionary.press_any_key_to_continue().ask()
```

---

## Task 4: Testing

**Effort**: 30 minutes

### Manual Testing Checklist

- [ ] TUI starts without import errors
- [ ] Menu item "🔄 Iterative Dev Workflow" appears
- [ ] Selecting menu item opens workflow wizard
- [ ] Can enter task description
- [ ] Can select developer agent (from ready agents)
- [ ] Can select reviewer agent (from ready agents)
- [ ] Can configure max iterations
- [ ] Confirmation panel shows correct info
- [ ] Workflow executes with progress display
- [ ] Results display correctly
- [ ] Can view full code
- [ ] Can view iteration details
- [ ] "← Done" returns to main menu
- [ ] Cancelling at any step returns gracefully

### Edge Case Testing

- [ ] Cancel before selecting task → Returns to menu
- [ ] Cancel before selecting agents → Returns to menu
- [ ] No ready agents available → Shows helpful message
- [ ] Workflow fails → Shows error, doesn't crash
- [ ] Empty task → Shows validation error
- [ ] Very long task → Works correctly

---

## Summary

### Files to Modify
| File | Changes |
|------|---------|
| `src/startd8/tui_improved.py` | Add import, handler, menu method |

### New Code to Add
| Component | Lines (approx) |
|-----------|---------------|
| Import statement | 1-2 |
| Handler in `run()` | 2 |
| `iterative_workflow_menu()` | ~30 |
| `_show_iterative_intro_panel()` | ~15 |
| `_get_task_description()` | ~20 |
| `_configure_iterative_workflow()` | ~25 |
| `_confirm_iterative_workflow()` | ~25 |
| `_execute_iterative_workflow()` | ~50 |
| `_display_iterative_results()` | ~60 |
| `_show_iteration_details()` | ~30 |
| **Total** | **~260 lines** |

### Estimated Effort
| Task | Time |
|------|------|
| Task 1: Import | 5 min |
| Task 2: Handler | 5 min |
| Task 3: Implementation | 3-5 hours |
| Task 4: Testing | 30 min |
| **Total** | **4-6 hours** |

---

## Acceptance Criteria

### Must Have
- [ ] Import added without errors
- [ ] Handler routes to menu method
- [ ] Menu method provides interactive wizard
- [ ] Can select agents from ready agents
- [ ] Workflow executes successfully
- [ ] Results displayed to user
- [ ] Returns to main menu when done

### Should Have
- [ ] Progress display during execution
- [ ] Iteration-by-iteration feedback
- [ ] Save results option
- [ ] View full code option
- [ ] Copy to clipboard option

### Nice to Have
- [ ] Context input (additional requirements)
- [ ] Custom prompt templates
- [ ] Compare with previous runs
- [ ] Export results to file

---

## Conclusion

The issue is a **simple oversight** - the menu item was added but the handler and implementation were not. This is a straightforward fix requiring:

1. **1 import statement**
2. **1 handler line** in `run()`
3. **~260 lines** of new menu/wizard code

The fix follows the existing patterns in the codebase (similar to `document_enhancement_chain_menu()`) and reuses existing helper methods like `_select_ready_agent()`.

---

**Investigation Complete**: December 7, 2025  
**Ready for Implementation**: Yes
