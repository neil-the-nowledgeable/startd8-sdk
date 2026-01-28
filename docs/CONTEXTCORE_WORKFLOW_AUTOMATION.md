# ContextCore + StartD8 SDK Workflow Automation

This guide explains how to use ContextCore's task tracking system with the StartD8 SDK's Lead Contractor workflow to automatically execute implementation tasks.

## Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           ContextCore Project                                │
│                                                                              │
│  ~/.contextcore/state/my-project/                                           │
│    ├── SDK-101.json  (status: "todo")     ─┐                                │
│    ├── SDK-102.json  (status: "todo")      │ Pending tasks                  │
│    ├── SDK-103.json  (status: "backlog")  ─┘                                │
│    ├── SDK-100.json  (status: "done")      ← Completed (ignored)            │
│    └── completed/                          ← Archive folder                 │
│                                                                              │
└────────────────────────────────────┬────────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         StartD8 SDK Integration                              │
│                                                                              │
│  ContextCoreTaskSource                                                       │
│    • Reads JSON files from state directory                                  │
│    • Filters by status (todo, backlog)                                      │
│    • Extracts task.prompt → workflow task_description                       │
│    • Resolves dependencies (task.depends_on)                                │
│                                                                              │
│  ContextCoreTaskRunner                                                       │
│    • Sorts tasks by dependencies                                            │
│    • Executes LeadContractorWorkflow for each                               │
│    • Updates task status on completion                                       │
│                                                                              │
└────────────────────────────────────┬────────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                        LeadContractorWorkflow                                │
│                                                                              │
│  1. Claude creates implementation spec                                       │
│  2. Drafter (GPT-4o-mini/Gemini) implements                                 │
│  3. Claude reviews → PASS/FAIL                                              │
│  4. Loop until pass or max iterations                                        │
│  5. Claude integrates final version                                          │
│                                                                              │
│  Output: Implementation code + test plan                                     │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Prerequisites

### 1. Install ContextCore

```bash
pip install contextcore
```

Or install from source:
```bash
cd /path/to/ContextCore
pip install -e .
```

### 2. Install StartD8 SDK

```bash
cd /path/to/startd8-sdk
pip install -e ".[all]"
```

### 3. Set API Keys

```bash
export ANTHROPIC_API_KEY="sk-ant-..."    # For Claude (lead agent)
export OPENAI_API_KEY="sk-..."           # For GPT models (drafter)
export GOOGLE_API_KEY="..."              # For Gemini models (drafter)
```

---

## Step 1: Create a ContextCore Project

A "project" in ContextCore is simply a namespace for organizing tasks. Projects are created implicitly when you start your first task.

```bash
# Start the first task to create the project
contextcore task start \
    --id SDK-001 \
    --title "Project setup task" \
    --project my-sdk-project \
    --type task \
    --status todo
```

This creates:
```
~/.contextcore/state/my-sdk-project/
└── SDK-001.json
```

### Project Naming Conventions

| Pattern | Example | Use Case |
|---------|---------|----------|
| `{team}-{product}` | `platform-api` | Team-scoped projects |
| `{product}-{component}` | `myapp-backend` | Component-scoped |
| `{sprint}-{goal}` | `sprint-3-auth` | Sprint-scoped |

---

## Step 2: Create Tasks with Proper Attributes

### Basic Task Structure

When you create a task with `contextcore task start`, it creates a JSON file with this structure:

```json
{
  "task_id": "SDK-101",
  "span_name": "task:SDK-101",
  "trace_id": "...",
  "span_id": "...",
  "start_time": "2026-01-23T10:00:00Z",
  "attributes": {
    "task.id": "SDK-101",
    "task.title": "Implement rate limiter",
    "task.type": "task",
    "task.status": "todo",
    "task.priority": "high",
    "task.story_points": 3
  },
  "events": [],
  "status": "UNSET"
}
```

### Adding Implementation Prompts

The StartD8 SDK uses these attributes for the workflow (in priority order):

| Attribute | Description | Used For |
|-----------|-------------|----------|
| `task.prompt` | Detailed implementation instructions | Primary task_description |
| `task.description` | Brief description | Fallback task_description |
| `task.title` | Short title | Display name, final fallback |
| `task.context` | JSON object with context | Workflow context |
| `task.language` | Programming language | Added to context |
| `task.framework` | Framework (FastAPI, React, etc.) | Added to context |
| `task.file` | Target file path | Added to context |
| `task.depends_on` | List of task IDs | Dependency ordering |

### Method 1: Create Task via CLI + Edit JSON

```bash
# Create the task
contextcore task start \
    --id SDK-101 \
    --title "Implement rate limiter" \
    --project my-project \
    --type task \
    --status todo \
    --priority high \
    --points 3
```

Then edit `~/.contextcore/state/my-project/SDK-101.json` to add the prompt:

```json
{
  "attributes": {
    "task.id": "SDK-101",
    "task.title": "Implement rate limiter",
    "task.type": "task",
    "task.status": "todo",
    "task.priority": "high",
    "task.story_points": 3,
    
    "task.prompt": "Implement a rate limiter using the token bucket algorithm.\n\nRequirements:\n1. Create a TokenBucket class with configurable capacity and refill rate\n2. Implement acquire() method that returns True if token available\n3. Implement wait_for_token() async method that waits until token available\n4. Add thread-safety using asyncio.Lock\n5. Include comprehensive docstrings and type hints\n\nAcceptance Criteria:\n- Passes all unit tests\n- Handles edge cases (zero capacity, negative refill)\n- Thread-safe for concurrent access\n\nOutput: Python module with TokenBucket class",
    
    "task.language": "Python",
    "task.framework": "asyncio",
    "task.file": "src/myapp/ratelimit.py"
  }
}
```

### Method 2: Create Task Programmatically

```python
from contextcore import TaskTracker

tracker = TaskTracker(project="my-project")

tracker.start_task(
    task_id="SDK-101",
    title="Implement rate limiter",
    task_type="task",
    status="todo",
    priority="high",
    story_points=3,
    # Custom attributes for the prompt
    **{
        "task.prompt": """Implement a rate limiter using the token bucket algorithm.

Requirements:
1. Create a TokenBucket class with configurable capacity and refill rate
2. Implement acquire() method that returns True if token available
3. Implement wait_for_token() async method that waits until token available
4. Add thread-safety using asyncio.Lock
5. Include comprehensive docstrings and type hints

Acceptance Criteria:
- Passes all unit tests
- Handles edge cases (zero capacity, negative refill)
- Thread-safe for concurrent access

Output: Python module with TokenBucket class""",
        "task.language": "Python",
        "task.framework": "asyncio",
        "task.file": "src/myapp/ratelimit.py",
    }
)
```

### Method 3: Create Task with JSON Template

Create a template file `task_template.json`:

```json
{
  "task_id": "SDK-102",
  "span_name": "task:SDK-102",
  "trace_id": "00000000000000000000000000000001",
  "span_id": "0000000000000001",
  "parent_span_id": null,
  "start_time": "2026-01-23T10:00:00Z",
  "attributes": {
    "task.id": "SDK-102",
    "task.title": "Add caching layer",
    "task.type": "task",
    "task.status": "todo",
    "task.priority": "medium",
    "task.story_points": 5,
    "task.depends_on": ["SDK-101"],
    "task.prompt": "Add a caching layer using Redis...\n\nRequirements:\n...",
    "task.language": "Python",
    "task.framework": "Redis",
    "task.file": "src/myapp/cache.py"
  },
  "events": [],
  "status": "UNSET",
  "status_description": null,
  "schema_version": 2,
  "project_id": "my-project"
}
```

Copy to state directory:
```bash
cp task_template.json ~/.contextcore/state/my-project/SDK-102.json
```

---

## Step 3: Create Task Dependencies

Tasks can depend on other tasks. The StartD8 SDK will execute them in the correct order.

### Example: Multi-Task Project

```bash
# Task 1: No dependencies (executed first)
contextcore task start --id SDK-101 --title "Create base models" \
    --project my-project --status todo

# Task 2: Depends on Task 1
contextcore task start --id SDK-102 --title "Implement repository layer" \
    --project my-project --status todo --depends-on SDK-101

# Task 3: Depends on Task 2
contextcore task start --id SDK-103 --title "Add API endpoints" \
    --project my-project --status todo --depends-on SDK-102

# Task 4: Depends on Task 1 (parallel with 2 and 3)
contextcore task start --id SDK-104 --title "Create test fixtures" \
    --project my-project --status todo --depends-on SDK-101
```

Execution order:
```
SDK-101 (no deps)
    ├── SDK-102 (depends on 101)
    │   └── SDK-103 (depends on 102)
    └── SDK-104 (depends on 101, parallel with 102/103)
```

### Setting Dependencies in JSON

Edit the task file to add `task.depends_on`:

```json
{
  "attributes": {
    "task.id": "SDK-103",
    "task.depends_on": ["SDK-101", "SDK-102"]
  }
}
```

---

## Step 4: Run the Workflow

### Option A: Command Line

```bash
# Dry run - see what tasks would be executed
python scripts/run_contextcore_workflow.py \
    --from-contextcore \
    --project-id my-project \
    --dry-run

# Execute all pending tasks
python scripts/run_contextcore_workflow.py \
    --from-contextcore \
    --project-id my-project \
    --yes

# With sprint tracking and verbose output
python scripts/run_contextcore_workflow.py \
    --from-contextcore \
    --project-id my-project \
    --sprint-id sprint-3 \
    --verbose \
    --yes

# Save results to file
python scripts/run_contextcore_workflow.py \
    --from-contextcore \
    --project-id my-project \
    --output results.json \
    --yes
```

### Option B: Python Script

```python
from startd8.integrations import (
    ContextCoreTaskSource,
    ContextCoreTaskRunner,
    run_contextcore_project,
)

# Quick one-liner
results = run_contextcore_project(
    project_id="my-project",
    sprint_id="sprint-3",
)

# Or with more control
source = ContextCoreTaskSource(
    project_id="my-project",
    status_filter=["todo", "backlog"],
)

tasks = source.get_pending_tasks()
print(f"Found {len(tasks)} tasks")

# Optionally filter
high_priority = [t for t in tasks if t.priority == "high"]

runner = ContextCoreTaskRunner(
    project_id="my-project",
    sprint_id="sprint-3",
)

results = runner.run_all(high_priority)
print(runner.get_summary())
```

### Option C: Using the Native ContextCore Workflow

The `LeadContractorContextCoreWorkflow` has native ContextCore integration:

```python
from startd8.workflows.builtin import LeadContractorContextCoreWorkflow

workflow = LeadContractorContextCoreWorkflow()

result = workflow.run({
    "task_description": "Implement rate limiter",
    "task_id": "SDK-101",
    "project_id": "my-project",
    "parent_id": "EPIC-001",  # Optional parent
    "sprint_id": "sprint-3",
})
```

---

## Step 5: Monitor Progress

### View Active Tasks

```bash
contextcore task list --project my-project
```

### Check Task Status

```bash
# View task state file
cat ~/.contextcore/state/my-project/SDK-101.json | jq '.attributes["task.status"]'
```

### View in Grafana

If you have OTLP export configured, tasks appear as spans in Grafana Tempo:

```bash
# Start Grafana stack (if using docker-compose)
docker-compose -f docker-compose.loki-stack.yml up -d
```

Navigate to Grafana → Explore → Tempo → Search for `service.name = "contextcore-tracker"`

---

## Complete Example: Sprint Planning

### 1. Create Sprint Tasks

```bash
# Epic
contextcore task start --id EPIC-001 --title "User Authentication System" \
    --project auth-service --type epic --status in_progress

# Stories under epic
contextcore task start --id AUTH-001 --title "User registration flow" \
    --project auth-service --type story --parent EPIC-001 --status todo

contextcore task start --id AUTH-002 --title "Login with JWT" \
    --project auth-service --type story --parent EPIC-001 --status todo \
    --depends-on AUTH-001

# Tasks under stories
contextcore task start --id AUTH-001-1 --title "Create User model" \
    --project auth-service --type task --parent AUTH-001 --status todo --points 2

contextcore task start --id AUTH-001-2 --title "Implement registration endpoint" \
    --project auth-service --type task --parent AUTH-001 --status todo --points 3 \
    --depends-on AUTH-001-1

contextcore task start --id AUTH-001-3 --title "Add email verification" \
    --project auth-service --type task --parent AUTH-001 --status todo --points 2 \
    --depends-on AUTH-001-2
```

### 2. Add Detailed Prompts

Edit each task JSON to add `task.prompt`:

```bash
# Example for AUTH-001-1
cat > /tmp/prompt.txt << 'EOF'
Create a User model for the authentication system using SQLAlchemy.

Requirements:
1. User model with fields: id, email, password_hash, created_at, updated_at, is_active, is_verified
2. Email must be unique and indexed
3. Password should never be stored in plain text
4. Add methods: set_password(), check_password(), generate_verification_token()
5. Use bcrypt for password hashing
6. Include proper SQLAlchemy relationships placeholder for future OAuth tokens

Acceptance Criteria:
- Model creates proper database schema
- Password hashing is secure (bcrypt with salt)
- Verification token is cryptographically random
- All fields have proper type hints

Output: SQLAlchemy model file
EOF

# Update the task (you'd typically script this)
jq --rawfile prompt /tmp/prompt.txt \
   '.attributes["task.prompt"] = $prompt | .attributes["task.language"] = "Python" | .attributes["task.framework"] = "SQLAlchemy"' \
   ~/.contextcore/state/auth-service/AUTH-001-1.json > /tmp/task.json && \
   mv /tmp/task.json ~/.contextcore/state/auth-service/AUTH-001-1.json
```

### 3. Execute Sprint Tasks

```bash
# Preview
python scripts/run_contextcore_workflow.py \
    --from-contextcore \
    --project-id auth-service \
    --sprint-id sprint-1 \
    --dry-run

# Execute
python scripts/run_contextcore_workflow.py \
    --from-contextcore \
    --project-id auth-service \
    --sprint-id sprint-1 \
    --output sprint-1-results.json \
    --yes
```

---

## Task Attribute Reference

### Required Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `task.id` | string | Unique identifier |
| `task.title` | string | Short title |
| `task.status` | string | `todo`, `backlog`, `in_progress`, `done`, `blocked` |

### Recommended for Workflows

| Attribute | Type | Description |
|-----------|------|-------------|
| `task.prompt` | string | Detailed implementation instructions |
| `task.description` | string | Brief description (fallback for prompt) |
| `task.language` | string | Programming language |
| `task.framework` | string | Framework being used |
| `task.file` | string | Target file path |
| `task.context` | object | Additional context dict |

### For Organization

| Attribute | Type | Description |
|-----------|------|-------------|
| `task.type` | string | `epic`, `story`, `task`, `subtask`, `bug`, `spike` |
| `task.priority` | string | `critical`, `high`, `medium`, `low` |
| `task.story_points` | int | Effort estimate |
| `task.parent_id` | string | Parent task ID |
| `task.depends_on` | list | Task IDs this depends on |
| `task.assignee` | string | Person assigned |
| `task.labels` | list | Tags for categorization |
| `task.url` | string | Link to external system (Jira, GitHub) |
| `task.due_date` | string | ISO date string |
| `sprint.id` | string | Sprint identifier |

---

## Troubleshooting

### No Tasks Found

```
No pending tasks found in project: my-project
```

**Check:**
1. Project directory exists: `ls ~/.contextcore/state/my-project/`
2. Tasks have correct status: `cat ~/.contextcore/state/my-project/*.json | jq '.attributes["task.status"]'`
3. Status filter matches: By default only `todo` and `backlog` are included

### Task Skipped Due to Dependency

```
⏭️ SKIPPED SDK-102: Dependency SDK-101 failed
```

**Fix:** Ensure dependent task completed successfully, or remove the dependency.

### ContextCore Not Installed

```
WARNING: ContextCore not installed - task tracking disabled
```

**Fix:** `pip install contextcore`

### Empty Task Description

If `task.prompt` is not set, the workflow uses `task.title` which may be too brief.

**Fix:** Add detailed `task.prompt` attribute to the task JSON.

---

## Best Practices

### 1. Write Good Prompts

```
❌ Bad: "Implement caching"

✅ Good: "Implement a caching layer using Redis.

Requirements:
1. Create CacheService class with get(), set(), delete() methods
2. Support TTL (time-to-live) for cache entries
3. Handle Redis connection failures gracefully
4. Add retry logic with exponential backoff

Acceptance Criteria:
- All methods have type hints
- Connection errors don't crash the application
- TTL is configurable per-key

Output: Python module with CacheService class"
```

### 2. Break Down Large Tasks

Instead of one massive task, create a hierarchy:

```
EPIC-001: Payment System
├── STORY-001: Credit Card Processing
│   ├── TASK-001: Create PaymentIntent model
│   ├── TASK-002: Implement Stripe integration
│   └── TASK-003: Add payment confirmation flow
└── STORY-002: Invoice Generation
    ├── TASK-004: Create Invoice model
    └── TASK-005: Generate PDF invoices
```

### 3. Use Dependencies for Ordered Execution

Tasks without explicit dependencies may run in any order. Always specify dependencies for tasks that build on each other.

### 4. Include Context

```json
{
  "task.context": {
    "existing_models": ["User", "Organization"],
    "database": "PostgreSQL",
    "orm": "SQLAlchemy 2.0",
    "api_framework": "FastAPI",
    "test_framework": "pytest"
  }
}
```

### 5. Review Before Large Batches

Always use `--dry-run` first:

```bash
python scripts/run_contextcore_workflow.py \
    --from-contextcore \
    --project-id my-project \
    --dry-run
```

---

## Files Reference

| File | Purpose |
|------|---------|
| `~/.contextcore/state/<project>/*.json` | Active task state files |
| `~/.contextcore/state/<project>/completed/` | Archived completed tasks |
| `scripts/run_contextcore_workflow.py` | CLI runner script |
| `src/startd8/integrations/contextcore.py` | Integration library |
| `scripts/example_tasks.yaml` | Example YAML task list |

---

## Addendum: Environment Setup (2026-01-27)

### Recommended: Use Environment Variables

To avoid hardcoded paths, set up the ContextCore environment:

```bash
# Add to ~/.zshrc or ~/.bashrc
source ~/Documents/dev/contextcore-beaver/env.sh
```

This sets:
- `$STARTD8_SDK_ROOT` - Canonical StartD8 SDK location
- `$CONTEXTCORE_ROOT` - ContextCore main project
- `$CONTEXTCORE_SKILLS_ROOT` - Skills library

### Running Scripts with Environment Variables

```bash
# Instead of:
# cd /path/to/startd8-sdk && python scripts/run_contextcore_workflow.py

# Use:
python $STARTD8_SDK_ROOT/scripts/run_contextcore_workflow.py \
    --from-contextcore \
    --project-id my-project \
    --dry-run
```

### Canonical Documentation

For the authoritative guide on using the Prime Contractor workflow with ContextCore:

```
~/Documents/dev/contextcore-beaver/docs/PRIME_CONTRACTOR_WORKFLOW.md
```

See `contextcore-beaver/REGISTRY.md` for all canonical component locations.
