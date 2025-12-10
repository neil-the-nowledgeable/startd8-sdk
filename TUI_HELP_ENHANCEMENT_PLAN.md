# TUI Help Enhancement Plan

**Date**: December 9, 2025  
**Purpose**: Enhance in-TUI help, guidance, and informational content  
**Status**: 📋 Planning Document (No Code Changes Yet)

---

## Executive Summary

This document outlines a comprehensive plan to enhance the help and informational content within the startd8 TUI. The goal is to make the TUI more discoverable, easier to learn, and provide contextual help throughout the user journey.

---

## Current State Analysis

### What Exists Now

1. **Main Help Screen** (`show_help()` method, line 4760-4805)
   - Single comprehensive help panel
   - Covers: Workflow, Prompt Builder, Agents, Output Folders, Tips
   - Accessed via: "❓ Help & Guide" in main menu
   - **Limitation**: Static, non-searchable, covers everything at once

2. **Inline Panels** (Various locations)
   - Brief explanatory panels at the start of workflows
   - Examples:
     - `step1_create_prompt()` - line 2075-2081
     - `_show_iterative_intro_panel()` - line 5085-5098
     - `document_enhancement_chain_menu()` - line 5462-5480
   - **Limitation**: Inconsistent, some workflows have them, others don't

3. **Menu Item Hints** (Main menu, line 2006-2069)
   - Descriptive text in menu items
   - Examples: "(Dev → Review → Fix)", "from templates"
   - **Limitation**: Very brief, no detailed explanations

4. **Disabled State Messages** (Main menu)
   - Shows why options are disabled
   - Example: "[dim]2️⃣ Distribute Prompt to Agents (create prompt first)[/dim]"
   - **Good**: Guides users on prerequisites

### What's Missing

1. **Contextual Help** - No help available within workflows
2. **Tutorial/Walkthrough** - No first-time user guide
3. **Quick Tips** - No hints for common tasks
4. **Keyboard Shortcuts** - No documentation of shortcuts
5. **Troubleshooting** - No in-app error resolution guides
6. **Feature Discovery** - Users may not know all capabilities
7. **Examples Library** - No built-in examples for common tasks
8. **Search/Index** - Can't search help content
9. **Help for New Features** - File input, job queue, etc. not documented
10. **Progressive Disclosure** - All help shown at once, overwhelming

---

## Enhancement Strategy

### Guiding Principles

1. **Progressive Disclosure** - Show relevant help when/where needed
2. **Just-in-Time** - Help appears at the moment of need
3. **Layered Information** - Quick tips → Detailed help → Examples
4. **Contextual** - Help specific to current task/screen
5. **Non-Intrusive** - Don't interrupt workflow, but always available
6. **Searchable** - Users can find what they need quickly
7. **Practical** - Examples and use cases, not just descriptions

---

## Proposed Enhancements

### Phase 1: Core Infrastructure (High Priority)

#### 1.1 Enhanced Main Help System

**Location**: Modify `show_help()` method (line 4760-4805)

**Changes**:
- Convert from single panel to multi-page help system
- Add navigation: Topics → Details → Examples
- Create help topic index

**New Method Structure**:
```python
def show_help(self):
    """Enhanced help system with navigation"""
    while True:
        # Show help topic menu
        topic = self._show_help_topics()
        if not topic:
            break
        
        # Show detailed help for selected topic
        self._show_help_details(topic)
```

**Help Topics to Add**:
1. Getting Started (Quick Tutorial)
2. Workflow Overview
3. Prompt Creation & Management
4. Working with Agents
5. API Key Management
6. Advanced Features (Enhancement Chain, Iterative Workflow, Job Queue)
7. File-Based Input (NEW)
8. Troubleshooting & FAQs
9. Tips & Best Practices
10. Keyboard Shortcuts

**Implementation Details**:
- Create `_show_help_topics()` method - displays topic menu
- Create `_show_help_details(topic)` method - shows detailed help
- Create `_help_content` dictionary - stores all help text
- Add "← Back" navigation to return to topics
- Add "Search" functionality to find help content

---

#### 1.2 Contextual Help System

**Purpose**: Add "?" help option throughout TUI

**Implementation**:
- Add new method: `_show_contextual_help(context_key: str)`
- Add help option to all major menus
- Store context-specific help in `_contextual_help` dictionary

**Where to Add**:
1. Main menu - Overview of current screen
2. Agent selection - How to choose agents
3. Prompt creation - Tips for writing good prompts
4. Workflow menus - Specific workflow guidance
5. Configuration screens - Explanation of options
6. Error screens - How to resolve issues

**Menu Pattern**:
```python
choices = [
    "Option 1",
    "Option 2",
    "Option 3",
    questionary.Separator("───────────────"),
    "❓ Help (about this screen)",
    "← Back"
]
```

**Example Implementation**:
```python
def _show_contextual_help(self, context_key: str):
    """Show help for specific context"""
    help_content = self._contextual_help.get(context_key, {})
    
    self.console.print(Panel(
        f"[bold]{help_content.get('title', 'Help')}[/bold]\n\n"
        f"{help_content.get('description', '')}\n\n"
        f"[bold]How to use:[/bold]\n{help_content.get('usage', '')}\n\n"
        f"[bold]Tips:[/bold]\n{help_content.get('tips', '')}",
        border_style="cyan",
        title="❓ Help"
    ))
    questionary.press_any_key_to_continue().ask()
```

---

#### 1.3 First-Run Tutorial

**Purpose**: Guide new users through first workflow

**Location**: Add new method `_run_first_time_tutorial()`

**Trigger**: 
- Check for `.startd8/.tutorial_completed` file
- If not exists, offer tutorial on startup
- Can also be accessed from Help menu

**Tutorial Flow**:
1. Welcome screen with overview
2. Guided prompt creation (example provided)
3. Agent selection explanation
4. Running first workflow
5. Viewing results
6. Next steps suggestions
7. Mark tutorial as complete

**Implementation**:
```python
def _run_first_time_tutorial(self):
    """Interactive tutorial for first-time users"""
    self.show_header("Welcome to startd8!")
    
    # Step 1: Welcome
    self._tutorial_step_welcome()
    
    # Step 2: Create example prompt
    self._tutorial_step_create_prompt()
    
    # Step 3: Select agent
    self._tutorial_step_select_agent()
    
    # Step 4: View results
    self._tutorial_step_view_results()
    
    # Step 5: Next steps
    self._tutorial_step_next_steps()
    
    # Mark complete
    self._mark_tutorial_complete()
```

---

### Phase 2: Workflow-Specific Help (Medium Priority)

#### 2.1 Standardize Intro Panels

**Current State**: Some workflows have intro panels, others don't

**Goal**: Every workflow has consistent, informative intro panel

**Standard Panel Structure**:
```python
def _show_{workflow}_intro_panel(self):
    """Show introduction to {workflow}"""
    self.console.print(Panel(
        "[bold cyan]{Workflow Name}[/bold cyan]\n\n"
        "[bold]What it does:[/bold]\n"
        "{Clear description of workflow purpose}\n\n"
        "[bold]How it works:[/bold]\n"
        "  1️⃣  {Step 1 description}\n"
        "  2️⃣  {Step 2 description}\n"
        "  3️⃣  {Step 3 description}\n\n"
        "[bold]Use Cases:[/bold]\n"
        "  • {Use case 1}\n"
        "  • {Use case 2}\n\n"
        "[bold]Requirements:[/bold]\n"
        "{What user needs: API keys, files, etc.}\n\n"
        "[bold]Tip:[/bold] {Helpful tip}",
        title="📖 {Workflow Name}",
        border_style="cyan"
    ))
```

**Workflows Needing Intro Panels**:
1. ✅ Iterative Dev Workflow (already exists)
2. ✅ Document Enhancement Chain (already exists)
3. ❌ Prompt Builder (needs enhancement)
4. ❌ Enhance Prompt File (needs creation)
5. ❌ Document Updater (needs creation)
6. ❌ Design Pipeline (needs enhancement)
7. ❌ Job Queue (needs enhancement)
8. ❌ Create New Prompt (exists but needs enhancement)

---

#### 2.2 Step-by-Step Guidance

**Purpose**: Guide users through multi-step workflows

**Implementation**:
- Add step numbers and descriptions
- Show progress indicator
- Explain what each step does before asking for input

**Pattern**:
```python
def workflow_with_guidance(self):
    """Example workflow with step guidance"""
    
    # Show overview
    self._show_workflow_intro()
    
    # Step 1
    self.console.print("\n[bold cyan]Step 1 of 4: {Step Name}[/bold cyan]")
    self.console.print("[dim]{What this step does and why}[/dim]\n")
    result1 = self._get_step1_input()
    
    # Step 2
    self.console.print("\n[bold cyan]Step 2 of 4: {Step Name}[/bold cyan]")
    self.console.print("[dim]{What this step does and why}[/dim]\n")
    result2 = self._get_step2_input()
    
    # Continue...
```

---

#### 2.3 Workflow Examples

**Purpose**: Show concrete examples for each workflow

**Location**: Add `_show_examples()` method for each workflow

**Content**: 3-5 real-world examples per workflow

**Example for Iterative Dev Workflow**:
```python
def _show_iterative_workflow_examples(self):
    """Show examples of iterative workflow tasks"""
    examples = [
        {
            'title': 'Example 1: Implement a Function',
            'task': 'Implement a Python function to validate email addresses using regex',
            'agents': 'Dev: Claude, Review: GPT-4',
            'use_case': 'Creating utility functions with quality checks'
        },
        {
            'title': 'Example 2: Fix Buggy Code',
            'task': 'Fix bugs in this function: [code snippet]',
            'agents': 'Dev: GPT-4, Review: Claude',
            'use_case': 'Debugging and improving existing code'
        },
        # More examples...
    ]
```

---

### Phase 3: Advanced Help Features (Low Priority)

#### 3.1 Interactive FAQ

**Purpose**: Searchable, categorized frequently asked questions

**Location**: Add to Help menu

**Categories**:
- Getting Started
- API Keys & Authentication
- Agent Configuration
- Prompt Creation
- Workflows
- File Operations
- Troubleshooting
- Performance & Optimization

**Implementation**:
```python
def show_faq(self):
    """Interactive FAQ browser"""
    while True:
        # Show FAQ categories
        category = self._select_faq_category()
        if not category:
            break
        
        # Show questions in category
        question = self._select_faq_question(category)
        if not question:
            continue
        
        # Show answer with related questions
        self._show_faq_answer(question)
```

---

#### 3.2 Tips & Tricks System

**Purpose**: Show helpful tips at appropriate times

**Implementation**:
- Create tips database
- Show random tip on startup (dismissible)
- Show context-specific tips during workflows
- "Did you know?" panels

**Tip Categories**:
1. **Productivity Tips** - Faster workflows, shortcuts
2. **Agent Tips** - Best models for tasks, cost optimization
3. **Prompt Tips** - Writing better prompts
4. **Feature Discovery** - Lesser-known capabilities
5. **Best Practices** - Quality improvements

**Example**:
```python
def _show_tip_of_the_day(self):
    """Show random helpful tip"""
    tips = [
        {
            'title': 'File-Based Tasks',
            'content': 'Did you know? You can load task descriptions from files! '
                      'Choose "📁 Load from file" in Iterative Workflow.',
            'category': 'productivity'
        },
        # More tips...
    ]
    
    tip = random.choice(tips)
    self.console.print(Panel(
        f"💡 [bold]{tip['title']}[/bold]\n\n{tip['content']}",
        border_style="yellow",
        title="Tip of the Day"
    ))
```

---

#### 3.3 Keyboard Shortcuts Documentation

**Purpose**: Document and display keyboard shortcuts

**Location**: Add to Help menu

**Content**:
- Navigation shortcuts
- Common actions
- Quick access keys
- Copy/paste tips

**Implementation**:
```python
def show_keyboard_shortcuts(self):
    """Display keyboard shortcuts"""
    table = Table(title="Keyboard Shortcuts")
    table.add_column("Action", style="cyan")
    table.add_column("Shortcut", style="yellow")
    table.add_column("Context", style="dim")
    
    shortcuts = [
        ("Navigate menus", "↑/↓ arrows", "All menus"),
        ("Select option", "Enter", "All menus"),
        ("Cancel/Back", "Ctrl+C", "Anywhere"),
        ("Exit TUI", "Ctrl+C twice", "Main menu"),
        # More shortcuts...
    ]
    
    for action, shortcut, context in shortcuts:
        table.add_row(action, shortcut, context)
    
    self.console.print(table)
```

---

#### 3.4 Troubleshooting Guide

**Purpose**: Help users resolve common issues

**Location**: Add to Help menu

**Categories**:
1. **API Key Issues**
   - "Invalid API key" errors
   - "No API key found" warnings
   - How to get API keys

2. **Agent Connection Issues**
   - "Agent not available" errors
   - Network/timeout issues
   - Model availability

3. **File Issues**
   - "File not found" errors
   - Permission issues
   - Encoding problems

4. **Workflow Issues**
   - Stuck workflows
   - Unexpected results
   - Performance problems

**Implementation**:
```python
def show_troubleshooting_guide(self):
    """Interactive troubleshooting guide"""
    
    # Show problem categories
    category = questionary.select(
        "What problem are you experiencing?",
        choices=[
            "API Key / Authentication Issues",
            "Agent Connection Problems",
            "File or Storage Issues",
            "Workflow Not Working",
            "Performance / Speed Issues",
            "Other / Not Sure",
            "← Back"
        ]
    ).ask()
    
    if category:
        self._show_troubleshooting_solutions(category)
```

---

### Phase 4: Content Enhancement (Ongoing)

#### 4.1 Update Existing Help Content

**File**: `src/startd8/tui_improved.py`, method `show_help()` (line 4760-4805)

**Current Help Topics**:
- Workflow (basic)
- Prompt Builder (good)
- Agents Section (good)
- Output Folders (basic)
- Tips (minimal)

**Enhancements Needed**:

1. **Add NEW Features Section**:
```python
"[bold blue]NEW FEATURES[/bold blue]\n"
"  [bold]📁 File-Based Input[/bold]\n"
"    Load task descriptions from files instead of typing\n"
"    Available in: Iterative Dev Workflow\n"
"    Example: Load complex task from project_task.txt\n\n"
"  [bold]🔄 Iterative Dev Workflow[/bold]\n"
"    Automated dev-review-fix loop with two agents\n"
"    Developer implements → Reviewer checks → Loop until perfect\n"
"    Great for code generation with quality control\n\n"
"  [bold]📥 Job Queue[/bold]\n"
"    Watch folder for job files and process automatically\n"
"    Perfect for batch operations and automation\n\n"
```

2. **Expand Workflow Section**:
```python
"[bold cyan]WORKFLOW OVERVIEW[/bold cyan]\n\n"
"[bold]Basic Workflow:[/bold]\n"
"  1️⃣  Create Prompt → Your question/task for AI\n"
"  2️⃣  Distribute → Choose which AI agent(s) to use\n"
"  3️⃣  View Results → Compare responses and metrics\n\n"
"[bold]Advanced Workflows:[/bold]\n"
"  [bold]🔄 Iterative Dev Workflow[/bold]\n"
"    Dev agent implements → Review agent checks → Repeat\n"
"    Use case: Code generation with automated review\n\n"
"  [bold]🔗 Enhancement Chain[/bold]\n"
"    Chain multiple agents to refine a document\n"
"    Use case: Progressive document improvement\n\n"
"  [bold]🚀 Design Pipeline[/bold]\n"
"    Draft → Review → Polish workflow\n"
"    Use case: Design documents, specifications\n\n"
"  [bold]📥 Job Queue[/bold]\n"
"    Automated batch processing from folder\n"
"    Use case: Process multiple tasks overnight\n\n"
```

3. **Add Getting Started Section**:
```python
"[bold green]GETTING STARTED[/bold green]\n\n"
"[bold]First Time?[/bold] Start here:\n"
"  1. Set up API keys (❓ Help → Manage API Keys)\n"
"  2. Test agents (🔬 Test Agent Connections)\n"
"  3. Create your first prompt (1️⃣ Create New Prompt)\n"
"  4. Run with an agent (2️⃣ Distribute)\n"
"  5. View results (3️⃣ View Results)\n\n"
"[bold]No API keys?[/bold] Use Mock agents to learn the interface!\n\n"
```

4. **Add Best Practices Section**:
```python
"[bold magenta]BEST PRACTICES[/bold magenta]\n\n"
"[bold]Prompt Writing:[/bold]\n"
"  • Be specific and clear about what you want\n"
"  • Include context, constraints, and examples\n"
"  • Use Prompt Builder templates for consistency\n\n"
"[bold]Agent Selection:[/bold]\n"
"  • Claude: Creative, detailed, code-heavy tasks\n"
"  • GPT-4: Analysis, reasoning, balanced responses\n"
"  • Mock: Testing workflows without API costs\n\n"
"[bold]Cost Optimization:[/bold]\n"
"  • Test with Mock agents first\n"
"  • Use specific models (e.g., claude-sonnet vs opus)\n"
"  • Compare agents to find best fit for task\n"
"  • Enable output folders to track usage\n\n"
```

5. **Add Common Tasks Section**:
```python
"[bold yellow]COMMON TASKS[/bold yellow]\n\n"
"[bold]How do I...?[/bold]\n"
"  • Add API key: Main menu → 🔑 Manage API Keys\n"
"  • Create custom agent: 🤖 Manage Agents → Add New\n"
"  • Load task from file: Iterative Workflow → 📁 Load from file\n"
"  • Compare agents: Run same prompt on multiple agents → 🔍 Compare\n"
"  • Save workflow results: Most workflows auto-save to .startd8/\n"
"  • Access past results: 📋 List All Prompts → Select → View\n\n"
```

---

#### 4.2 Add Examples to Help

**Purpose**: Show concrete examples in help system

**Implementation**: Add examples section to each help topic

**Example Structure**:
```python
def _show_help_examples(self, topic: str):
    """Show examples for help topic"""
    examples = {
        'prompt_creation': [
            {
                'title': 'Code Generation',
                'prompt': 'Implement a Python function to validate email addresses using regex',
                'why': 'Specific, clear goal with technical details'
            },
            {
                'title': 'Document Analysis',
                'prompt': 'Review this design document and suggest improvements for clarity',
                'why': 'Clear task with defined criteria'
            }
        ],
        'agent_selection': [
            {
                'task': 'Creative writing',
                'recommended': 'Claude (claude-3-5-sonnet)',
                'why': 'Excellent at creative, nuanced content'
            }
        ]
    }
```

---

## Implementation Checklist

### Phase 1: Core Infrastructure

#### 1.1 Enhanced Main Help System
- [ ] Create `_show_help_topics()` method
- [ ] Create `_show_help_details(topic)` method
- [ ] Create `_help_content` dictionary with all topics
- [ ] Add Getting Started topic
- [ ] Add Workflow Overview topic
- [ ] Add Prompt Management topic
- [ ] Add Working with Agents topic
- [ ] Add API Key Management topic
- [ ] Add Advanced Features topic
- [ ] Add File-Based Input topic (NEW)
- [ ] Add Troubleshooting topic
- [ ] Add Tips & Best Practices topic
- [ ] Add Keyboard Shortcuts topic
- [ ] Update `show_help()` to use new system

#### 1.2 Contextual Help System
- [ ] Create `_show_contextual_help(context_key)` method
- [ ] Create `_contextual_help` dictionary
- [ ] Add help content for all contexts:
  - [ ] Main menu
  - [ ] Agent selection
  - [ ] Prompt creation
  - [ ] Each workflow menu
  - [ ] Configuration screens
- [ ] Add "❓ Help" option to all major menus
- [ ] Test help availability throughout TUI

#### 1.3 First-Run Tutorial
- [ ] Create `_run_first_time_tutorial()` method
- [ ] Create `_tutorial_step_welcome()` method
- [ ] Create `_tutorial_step_create_prompt()` method
- [ ] Create `_tutorial_step_select_agent()` method
- [ ] Create `_tutorial_step_view_results()` method
- [ ] Create `_tutorial_step_next_steps()` method
- [ ] Create `_mark_tutorial_complete()` method
- [ ] Create `_check_tutorial_status()` method
- [ ] Add tutorial trigger on first run
- [ ] Add "Run Tutorial" to Help menu

### Phase 2: Workflow-Specific Help

#### 2.1 Standardize Intro Panels
- [ ] Review all existing intro panels
- [ ] Create template for standard intro panel
- [ ] Add/enhance intro panels for:
  - [ ] Prompt Builder
  - [ ] Enhance Prompt File
  - [ ] Document Updater
  - [ ] Design Pipeline
  - [ ] Job Queue
  - [ ] Create New Prompt

#### 2.2 Step-by-Step Guidance
- [ ] Identify all multi-step workflows
- [ ] Add step numbers and progress indicators
- [ ] Add explanatory text before each step
- [ ] Test user comprehension

#### 2.3 Workflow Examples
- [ ] Create `_show_examples()` method template
- [ ] Add examples for each workflow:
  - [ ] Iterative Dev Workflow (3-5 examples)
  - [ ] Enhancement Chain (3-5 examples)
  - [ ] Design Pipeline (3-5 examples)
  - [ ] Prompt Builder (templates are examples)
  - [ ] Job Queue (3-5 examples)
- [ ] Add "View Examples" option to workflow menus

### Phase 3: Advanced Features

#### 3.1 Interactive FAQ
- [ ] Create `show_faq()` method
- [ ] Create FAQ content database
- [ ] Organize by categories
- [ ] Add search functionality
- [ ] Link related questions
- [ ] Add to Help menu

#### 3.2 Tips & Tricks System
- [ ] Create tips database
- [ ] Create `_show_tip_of_the_day()` method
- [ ] Add tips to appropriate contexts
- [ ] Make tips dismissible
- [ ] Add "View All Tips" to Help menu

#### 3.3 Keyboard Shortcuts
- [ ] Document all keyboard shortcuts
- [ ] Create `show_keyboard_shortcuts()` method
- [ ] Display in table format
- [ ] Add to Help menu

#### 3.4 Troubleshooting Guide
- [ ] Create `show_troubleshooting_guide()` method
- [ ] Organize by problem categories
- [ ] Add solutions for common issues
- [ ] Link to relevant help topics
- [ ] Add to Help menu

### Phase 4: Content Enhancement

#### 4.1 Update Existing Help
- [ ] Add NEW FEATURES section
- [ ] Expand WORKFLOW section
- [ ] Add GETTING STARTED section
- [ ] Add BEST PRACTICES section
- [ ] Add COMMON TASKS section
- [ ] Update TIPS section

#### 4.2 Add Examples
- [ ] Create examples for each help topic
- [ ] Add use cases and scenarios
- [ ] Include sample prompts
- [ ] Show expected results

---

## File Locations & Line References

### Files to Modify

| File | Location | What to Change |
|------|----------|---------------|
| `src/startd8/tui_improved.py` | Line 4760-4805 | `show_help()` method - expand and reorganize |
| `src/startd8/tui_improved.py` | Line 2006-2069 | `main_menu()` - add help options |
| `src/startd8/tui_improved.py` | New methods | Add all new help methods |
| `src/startd8/tui_improved.py` | Line 4807-4867 | `run()` method - add tutorial check |
| `src/startd8/tui_improved.py` | Throughout | Add contextual help to all menus |

### Methods to Create

| Method Name | Purpose | Estimated Lines |
|-------------|---------|----------------|
| `_show_help_topics()` | Display help topic menu | ~30 |
| `_show_help_details(topic)` | Show detailed help for topic | ~50 |
| `_help_content` (dict) | Store all help content | ~500 |
| `_show_contextual_help(context)` | Show context-specific help | ~30 |
| `_contextual_help` (dict) | Store contextual help content | ~300 |
| `_run_first_time_tutorial()` | Interactive first-run tutorial | ~100 |
| `_tutorial_step_*()` methods | Individual tutorial steps | ~20 each (x5) |
| `show_faq()` | Interactive FAQ browser | ~50 |
| `_show_tip_of_the_day()` | Display random tip | ~20 |
| `show_keyboard_shortcuts()` | Display shortcuts table | ~30 |
| `show_troubleshooting_guide()` | Interactive troubleshooting | ~50 |
| `_show_workflow_examples()` | Display workflow examples | ~30 |

**Total Estimated New Lines**: ~1,500-2,000 lines

---

## Content Structure

### Help Content Dictionary Example

```python
self._help_content = {
    'getting_started': {
        'title': 'Getting Started with startd8',
        'content': '''
            [bold]Welcome to startd8![/bold]
            
            startd8 helps you interact with multiple AI agents
            and compare their responses.
            
            [bold]Quick Start (5 minutes):[/bold]
            
            1. [bold]Set up API keys[/bold]
               • Main menu → 🔑 Manage API Keys
               • Add your Anthropic and/or OpenAI key
               • Or use Mock agents to explore (no keys needed!)
            
            2. [bold]Test your agents[/bold]
               • Main menu → 🔬 Test Agent Connections
               • Verify your agents are working
            
            3. [bold]Create your first prompt[/bold]
               • Main menu → 1️⃣ Create New Prompt
               • Example: "Explain recursion in programming"
            
            4. [bold]Run an agent[/bold]
               • Main menu → 2️⃣ Distribute Prompt to Agents
               • Choose Claude or GPT-4
               • Wait for response
            
            5. [bold]View results[/bold]
               • Main menu → 3️⃣ View Results
               • Compare response quality and metrics
            
            [bold]First time?[/bold] Try the interactive tutorial!
            Main menu → ❓ Help & Guide → Run Tutorial
        ''',
        'related': ['workflow_overview', 'agents', 'api_keys']
    },
    
    'file_based_input': {
        'title': 'File-Based Input (NEW)',
        'content': '''
            [bold]Load Task Descriptions from Files[/bold]
            
            Instead of typing tasks every time, you can load them
            from files. Great for:
            • Complex, detailed tasks
            • Reusing tasks across runs
            • Version controlling tasks in Git
            • Sharing tasks with team
            
            [bold]How to use:[/bold]
            
            1. Create a text file with your task:
               ```
               # my_task.txt
               Implement a user authentication system with:
               1. Email/password login
               2. JWT tokens
               3. Password reset
               ```
            
            2. In Iterative Dev Workflow:
               • When prompted for task description
               • Choose "📁 Load from file"
               • Enter path: ./my_task.txt
               • Review preview and confirm
            
            3. Continue workflow as normal
            
            [bold]File format:[/bold]
            • Any plain text file (UTF-8)
            • .txt, .md, or any text format
            • No binary files (images, PDFs, etc.)
            
            [bold]Example file:[/bold]
            See test_task_example.txt for a template
        ''',
        'related': ['iterative_workflow', 'tips']
    },
    
    # More topics...
}
```

### Contextual Help Dictionary Example

```python
self._contextual_help = {
    'main_menu': {
        'title': 'Main Menu Help',
        'description': 'This is the main navigation hub for startd8.',
        'usage': '''
            • WORKFLOW section: Create and distribute prompts
            • MANAGE section: View history and statistics
            • AGENTS section: Configure AI agents and API keys
            • SYSTEM section: Settings and help
        ''',
        'tips': '''
            • Grey/dimmed options need prerequisites (e.g., create prompt first)
            • Numbers show workflow order: 1→2→3
            • Use Mock agents to learn without API costs
        '''
    },
    
    'agent_selection': {
        'title': 'Agent Selection Help',
        'description': 'Choose which AI agent(s) to run your prompt on.',
        'usage': '''
            • Individual agent: Run on one specific agent
            • ALL AVAILABLE: Run on all configured agents
            • ONLY UNDISTRIBUTED: Run on agents not yet used
        ''',
        'tips': '''
            • Claude excels at: Creative content, code, detailed responses
            • GPT-4 excels at: Analysis, reasoning, structured output
            • Mock agents: Testing workflows without API costs
            • Compare agents to find best for your task type
        '''
    },
    
    # More contexts...
}
```

---

## Testing Plan

### Manual Testing Checklist

#### Phase 1 Testing
- [ ] Help menu displays all topics
- [ ] Can navigate between help topics
- [ ] "Back" returns to topic menu
- [ ] Help content is readable and formatted correctly
- [ ] Contextual help appears in all major menus
- [ ] Contextual help content is relevant
- [ ] Tutorial runs start to finish
- [ ] Tutorial creates valid example
- [ ] Tutorial marks completion correctly
- [ ] Can access tutorial from Help menu

#### Phase 2 Testing
- [ ] All workflows have intro panels
- [ ] Intro panels are consistent
- [ ] Step guidance is clear
- [ ] Progress indicators work
- [ ] Examples display correctly
- [ ] Examples are helpful and accurate

#### Phase 3 Testing
- [ ] FAQ displays and navigates correctly
- [ ] FAQ content answers common questions
- [ ] Tips display without interrupting workflow
- [ ] Tips are helpful and relevant
- [ ] Keyboard shortcuts list is complete
- [ ] Troubleshooting guide is helpful

#### Phase 4 Testing
- [ ] Updated help content is accurate
- [ ] New sections are well-organized
- [ ] Examples are clear and useful
- [ ] No outdated information remains

---

## Accessibility Considerations

1. **Text Size** - Use Rich formatting for readability
2. **Color Contrast** - Ensure text is readable (cyan, yellow, etc.)
3. **Navigation** - Clear "Back" options everywhere
4. **Progressive Disclosure** - Don't overwhelm with too much at once
5. **Search** - Help users find what they need quickly
6. **Plain Language** - Avoid jargon, explain technical terms
7. **Examples** - Show, don't just tell

---

## Success Metrics

### Quantitative
- Help menu usage (track access count)
- Tutorial completion rate
- Time to first successful workflow
- Reduction in error-triggered exits
- User retention (return usage)

### Qualitative
- User feedback on help usefulness
- Questions in support channels
- Self-service success rate
- Learning curve perception

---

## Maintenance Plan

### Regular Updates
- [ ] Add help for new features immediately
- [ ] Update examples when workflows change
- [ ] Refresh tips quarterly
- [ ] Review troubleshooting annually
- [ ] Test all help content on major updates

### Content Review Schedule
- **Monthly**: Check for outdated information
- **Quarterly**: Add new tips and examples
- **Annually**: Full content audit

---

## Implementation Priority

### High Priority (Phase 1)
**Goal**: Make TUI learnable and discoverable
**Timeline**: 1-2 weeks
**Focus**: 
- Enhanced main help system
- Contextual help
- First-run tutorial

### Medium Priority (Phase 2)
**Goal**: Improve workflow guidance
**Timeline**: 1 week
**Focus**:
- Standardized intro panels
- Step-by-step guidance
- Workflow examples

### Low Priority (Phase 3)
**Goal**: Advanced help features
**Timeline**: 2-3 weeks
**Focus**:
- FAQ system
- Tips & tricks
- Troubleshooting guide

### Ongoing (Phase 4)
**Goal**: Keep content fresh
**Timeline**: Continuous
**Focus**:
- Content updates
- New examples
- User feedback integration

---

## Estimated Effort

| Phase | Tasks | Lines of Code | Time | Priority |
|-------|-------|--------------|------|----------|
| Phase 1 | 3 | ~800 | 1-2 weeks | High |
| Phase 2 | 3 | ~400 | 1 week | Medium |
| Phase 3 | 4 | ~500 | 2-3 weeks | Low |
| Phase 4 | 2 | ~200 | Ongoing | Ongoing |
| **Total** | **12** | **~1,900** | **4-6 weeks** | - |

---

## Dependencies

### Technical Dependencies
- No new external libraries needed
- Uses existing: Rich, questionary
- Compatible with current TUI structure

### Content Dependencies
- Requires accurate feature documentation
- Needs example prompts and workflows
- Requires testing to validate help accuracy

---

## Future Enhancements (Beyond This Plan)

1. **Video Tutorials** - Link to video walkthroughs
2. **Interactive Demos** - Automated demos of features
3. **Help Search** - Full-text search across all help
4. **Help History** - Track what user has viewed
5. **Smart Help** - AI-powered help suggestions
6. **Community Help** - Link to forums, Discord
7. **Help Export** - Save help as PDF/Markdown
8. **Multi-language** - Translate help content
9. **Voice Help** - Audio help for accessibility
10. **Help Customization** - Users customize help depth

---

## Approval & Sign-Off

### Review Checklist
- [ ] Plan reviewed by team
- [ ] Content strategy approved
- [ ] Priority agreed upon
- [ ] Timeline acceptable
- [ ] Resources allocated
- [ ] Success metrics defined

### Approval

**Reviewed by**: _____________  
**Date**: _____________  
**Status**: [ ] Approved [ ] Needs Changes [ ] Rejected

---

## Appendix

### A. Example Help Topics (Full Content)

See content structure section above for examples.

### B. Contextual Help Locations

| Screen/Menu | Context Key | Priority |
|-------------|-------------|----------|
| Main Menu | `main_menu` | High |
| Agent Selection | `agent_selection` | High |
| Prompt Creation | `prompt_creation` | High |
| Iterative Workflow | `iterative_workflow` | Medium |
| Enhancement Chain | `enhancement_chain` | Medium |
| Job Queue | `job_queue` | Medium |
| API Key Management | `api_key_mgmt` | High |
| Agent Management | `agent_mgmt` | Medium |

### C. Tutorial Script Outline

1. **Welcome** (30 seconds)
   - Introduce startd8
   - Explain what we'll do
   - Option to skip

2. **Create Prompt** (1 minute)
   - Pre-filled example
   - Explain what prompts are
   - Create and save

3. **Select Agent** (1 minute)
   - Explain agent types
   - Recommend Mock for tutorial
   - Select and run

4. **View Results** (1 minute)
   - Show response
   - Explain metrics
   - Interpret results

5. **Next Steps** (30 seconds)
   - Suggest trying real agents
   - Point to advanced features
   - Link to help

**Total**: ~4 minutes

---

**Document Version**: 1.0  
**Last Updated**: December 9, 2025  
**Status**: 📋 Planning (Ready for Implementation)
