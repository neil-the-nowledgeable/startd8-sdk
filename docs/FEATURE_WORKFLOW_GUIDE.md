# Feature Development Workflow Guide

## Overview

This guide explains how to use startd8 to implement a series of features from a master plan using the job queue system.

**Example Use Case:** Implementing 9 features for Flower Defense V2 using agent-driven development.

---

## Quick Start

### Step 1: Generate Job Files

Generate a job file for Feature 1:

```bash
cd /Users/neilyashinsky/Documents/Startd8/dev/startd8-sdk-project

python3 scripts/generate_feature_jobs.py --feature 1 --output ~/my-jobs
```

Or generate all features (Feature 9 first, Feature 7 last):

```bash
python3 scripts/generate_feature_jobs.py --all --output ~/my-jobs
```

### Step 2: Process with startd8

**Option A: Using the TUI**

```bash
startd8
```

1. Select: **📥 Job Queue**
2. Select: **⚙️ Configure Queue Folder**
3. Point to your job directory (e.g., `~/my-jobs`)
4. Select: **▶️ Process Queue** (runs all pending jobs)

**Option B: Programmatically**

```python
from startd8 import JobQueue, JobQueueConfig, AgentFramework
from pathlib import Path

# Setup
framework = AgentFramework()
config = JobQueueConfig(
    watch_folder=Path("~/my-jobs").expanduser(),
    default_agents=["claude"]
)

# Process
queue = JobQueue(config, framework)
results = queue.process_all()

# Review
for result in results:
    print(f"{result.job_id}: {result.status}")
    if result.response_ids:
        print(f"  → Generated {len(result.response_ids)} responses")
```

---

## The Complete Workflow

### 1. Master Plan Structure

Your master plan should:
- List all features with metadata
- Define dependencies between features
- Specify implementation order
- Include effort estimates

**Example:** `/Users/neilyashinsky/Documents/FMLs/dev/play/version2/plan/agent_plans/00_MASTER_PLAN.md`

### 2. Feature Plan Files

Each feature gets its own detailed plan:

```markdown
---
feature_id: 1
title: "Session High Score Storage"
disruption: low
effort_hours: "2-3"
depends_on: [9]
---

# Feature 1: Session High Score Storage

## Implementation Steps

### Step 1: Create Storage Utility
...
```

### 3: Generate Job Files

The script `scripts/generate_feature_jobs.py` creates job files that:

- ✅ Include the full feature plan as context
- ✅ Specify file locations and repository paths
- ✅ Define implementation requirements
- ✅ Set priority based on dependencies
- ✅ Target specific agents

**Generated Structure:**

```
my-jobs/
├── README.md                              # Instructions
├── feature_01_session_high_score.json     # Feature 1 job
├── feature_02_initials_entry.json         # Feature 2 job
├── feature_03_pink_trebuchet.json         # Feature 3 job
└── ... (more features)
```

### 4. Job File Format

Each job file contains:

```json
{
  "job_id": "feature-1-abc123",
  "prompt": {
    "content": "# Development Task: ...\n\n## Feature Plan\n...",
    "version": "1.0.0",
    "tags": ["flower-defense", "v2", "feature-1"],
    "metadata": {
      "feature_num": 1,
      "feature_title": "Session High Score Storage",
      "game_repo": "/path/to/repo"
    }
  },
  "agents": ["claude"],
  "priority": 8,
  "status": "pending"
}
```

### 5. Processing Jobs

**Sequential Processing (Recommended):**

Jobs are processed in priority order. Higher priority = processed first.

Example priority order:
1. Feature 9 (priority: 10) - Foundation
2. Feature 1 (priority: 8) - Depends on Feature 9
3. Feature 2 (priority: 7) - Depends on Feature 1
4. ... and so on

**Watch Mode:**

The job queue can watch a folder and auto-process new jobs:

```python
config = JobQueueConfig(
    watch_folder=Path("~/my-jobs"),
    poll_interval_seconds=5.0,
    auto_start=True  # Auto-process new jobs
)

queue = JobQueue(config, framework)
queue.start_watching()  # Runs until stopped
```

### 6. Agent Processing

When a job is processed:

1. **Agent receives:** Complete feature plan + context
2. **Agent analyzes:** Existing codebase structure
3. **Agent implements:** According to specifications
4. **Agent returns:** Code changes + explanations
5. **Framework stores:** Response with metadata

### 7. Applying Code Changes

**Automatic (Future Enhancement):**
- Agent responses could include file operations
- Framework applies changes directly to filesystem

**Manual (Current):**
1. Review agent response
2. Extract code changes
3. Apply to your repository
4. Test the implementation
5. Commit changes

### 8. Tracking Progress

**Via TUI:**
- View pending jobs
- View completed jobs
- See response counts and status

**Via API:**
```python
# Get status
status = queue.get_queue_status()
print(f"Pending: {status['status_counts']['pending']}")
print(f"Completed: {status['status_counts']['completed']}")

# List jobs
pending = queue.get_pending_jobs()
completed = [j for j in queue.list_jobs(include_completed=True) 
             if j.is_completed]

# View responses
for job in completed:
    for response_id in job.response_ids:
        response = framework.get_response(response_id)
        print(response.response)
```

---

## Example: Flower Defense V2 Features

### Feature Overview

9 features to implement in specific order:

| Priority | Feature | Depends On | Effort |
|----------|---------|------------|--------|
| 10 | Feature 9: Arcade Mode | None | 12-16h |
| 8 | Feature 1: High Score | Feature 9 | 2-3h |
| 7 | Feature 2: Initials | Feature 1 | 4-6h |
| 6 | Feature 3: Pink Trebuchet | None | 3-4h |
| 5 | Feature 8: Messages | None | 4-6h |
| 4 | Feature 4: Style Selector | Feature 3 | 6-8h |
| 3 | Feature 5: Limited Ammo | None | 4-6h |
| 2 | Feature 6: Continue Progress | Feature 1 | 3-4h |
| 1 | Feature 7: Cat Power-Up | None | 8-12h |

### Implementation Plan

**Phase 1: Foundation**
```bash
# Feature 9 (foundation - must be first)
python3 scripts/generate_feature_jobs.py --feature 9
```

**Phase 2: Low Disruption**
```bash
# Features 1, 2, 3, 8
python3 scripts/generate_feature_jobs.py --features 1 2 3 8
```

**Phase 3: Medium Disruption**
```bash
# Features 4, 5, 6
python3 scripts/generate_feature_jobs.py --features 4 5 6
```

**Phase 4: High Disruption**
```bash
# Feature 7 (last, highest disruption)
python3 scripts/generate_feature_jobs.py --feature 7
```

**Or All at Once:**
```bash
# Generate all with correct priority order
python3 scripts/generate_feature_jobs.py --all
```

---

## Advanced Usage

### Custom Agents

Use different agents for different tasks:

```bash
# Use GPT-4 instead of Claude
python3 scripts/generate_feature_jobs.py --feature 1 --agent gpt4

# Use Composer
python3 scripts/generate_feature_jobs.py --feature 1 --agent composer
```

### Multiple Agents per Job

Edit the job file to use multiple agents:

```json
{
  "agents": ["claude", "gpt4"],
  ...
}
```

Both agents will process the job and you can compare responses.

### Priority Override

Edit job files to change priority:

```json
{
  "priority": 10,  // Highest priority
  ...
}
```

### Batch Processing with Dependencies

The job queue respects dependencies automatically if you encode them in priority:

- Feature 9 (depends on nothing): priority 10
- Feature 1 (depends on 9): priority 8
- Feature 2 (depends on 1): priority 7

Process all at once:
```python
results = queue.process_all()
```

They'll execute in correct order: 9 → 1 → 2

### Error Handling

If a job fails:

```python
# View failed jobs
failed = [j for j in queue.list_jobs(include_completed=True) 
          if j.status == JobStatus.FAILED]

for job in failed:
    print(f"Failed: {job.job_id}")
    print(f"Error: {job.error}")

# Retry a failed job
job = failed[0]
job.status = JobStatus.PENDING  # Reset to pending
queue.process_job(job)  # Try again
```

### Archive Completed Jobs

```python
config = JobQueueConfig(
    watch_folder=Path("~/my-jobs"),
    archive_completed=True,
    archive_folder=Path("~/my-jobs/completed")
)

queue = JobQueue(config, framework)
queue.process_all()  # Jobs move to archive when done
```

---

## Best Practices

### 1. Start Small

Begin with a single feature to validate the workflow:

```bash
python3 scripts/generate_feature_jobs.py --feature 1
```

Process it, review the results, adjust as needed.

### 2. Review Agent Output

Always review agent responses before applying code:
- Check for correctness
- Verify it follows your patterns
- Test changes thoroughly

### 3. Use Version Control

Before processing features:
```bash
cd /path/to/your/repo
git checkout -b feature/batch-implementation
```

After each feature:
```bash
git add .
git commit -m "Implement Feature N: Title"
```

### 4. Test Incrementally

Don't implement all 9 features without testing:
1. Implement Feature 9 (foundation)
2. Test thoroughly
3. Implement Features 1-3
4. Test again
5. Continue in phases

### 5. Track Progress

Keep a checklist:

```markdown
## Implementation Progress

- [x] Feature 9: Arcade Mode (12-16h) ✓
- [x] Feature 1: High Score (2-3h) ✓
- [ ] Feature 2: Initials (4-6h) - In Progress
- [ ] Feature 3: Pink Trebuchet (3-4h)
- [ ] Feature 8: Messages (4-6h)
- [ ] Feature 4: Style Selector (6-8h)
- [ ] Feature 5: Limited Ammo (4-6h)
- [ ] Feature 6: Continue Progress (3-4h)
- [ ] Feature 7: Cat Power-Up (8-12h) - Do Last
```

---

## Troubleshooting

### Jobs Not Processing

**Check queue configuration:**
```python
status = queue.get_queue_status()
print(status)
```

**Verify job files are valid JSON:**
```bash
python3 -m json.tool job_file.json
```

### Agent Not Responding

**Check agent configuration:**
```python
# Test agent directly
agent = ClaudeAgent()
response, time, tokens = agent.generate("Test prompt")
print(response)
```

**Check API keys:**
```bash
echo $ANTHROPIC_API_KEY  # Claude
echo $OPENAI_API_KEY     # GPT-4
echo $CURSOR_API_KEY     # Composer
```

### Code Changes Not Applying

The current implementation stores responses but doesn't auto-apply changes.

**Manual process:**
1. View response: `framework.get_response(response_id)`
2. Extract code blocks from response
3. Apply to your repository manually

**Future enhancement:** Auto-application with safety checks.

---

## Reference

### Script Options

```bash
python3 scripts/generate_feature_jobs.py --help

Options:
  --feature N          Generate single feature
  --features N M ...   Generate multiple features
  --all                Generate all features
  --agent NAME         Agent to use (default: claude)
  --output PATH        Output directory
```

### Job File Locations

After generation:
- **Job files:** `{output_dir}/*.json`
- **README:** `{output_dir}/README.md`
- **Completed:** `{output_dir}/completed/` (if archiving enabled)

### Framework Storage

Agent responses stored in:
- **Default:** `~/.startd8/`
- **Custom:** Set via `AgentFramework(storage_dir=Path("..."))`

---

## Next Steps

1. **Generate your first job:**
   ```bash
   python3 scripts/generate_feature_jobs.py --feature 1 --output ./jobs
   ```

2. **Review the job file:**
   ```bash
   cat jobs/feature_01_*.json | python3 -m json.tool
   ```

3. **Process it:**
   ```bash
   startd8
   # → Job Queue → Configure → ./jobs → Process Queue
   ```

4. **Review results:**
   ```bash
   startd8
   # → View Results → Select prompt
   ```

5. **Apply changes to your codebase**

6. **Generate next feature and repeat!**

---

## Questions?

- **Job Queue Issues:** Check `docs/JOB_QUEUE.md` (if available)
- **Agent Problems:** Check API keys and `docs/AGENTS.md`
- **Framework Help:** Run `startd8 → Help & Guide`

---

*Generated: December 6, 2025*





