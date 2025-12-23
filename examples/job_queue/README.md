# Job Queue Examples

This folder contains example job files and scripts for the startd8 job queue feature.

## Quick Start

### 1. Configure the Queue

```bash
# Configure a watch folder for jobs
startd8 queue configure --folder ~/startd8-jobs --agent mock:mock-model
```

### 2. Add Jobs

**Using CLI:**
```bash
startd8 queue add "Write a hello world program in Python" --agent mock:mock-model --priority 1
```

**Using job files:**
Copy any `*_startd8_job.json` file from this folder to your watch folder:
```bash
cp simple_task_startd8_job.json ~/startd8-jobs/
```

### 3. Process Jobs

```bash
# Check status
startd8 queue status

# Process all pending jobs
startd8 queue run

# Process single job
startd8 queue run --once

# Watch mode (continuous processing)
startd8 queue watch
```

## Example Job Files

### `simple_task_startd8_job.json`
A basic coding task for generating a fibonacci function.

### `code_review_startd8_job.json`
A code review task with specific review criteria.

### `design_doc_startd8_job.json`
A high-priority task for creating a technical design document, configured to use multiple agents.

## Job File Format

```json
{
  "prompt": {
    "content": "Your prompt text here",
    "version": "1.0.0",
    "tags": ["tag1", "tag2"],
    "metadata": {}
  },
  "agents": ["anthropic:claude-3-5-sonnet-20241022", "openai:gpt-4-turbo-preview"],
  "priority": 0,
  "metadata": {}
}
```

### Fields

| Field | Required | Description |
|-------|----------|-------------|
| `prompt.content` | Yes | The prompt text to send to agents |
| `prompt.version` | No | Semantic version (default: "1.0.0") |
| `prompt.tags` | No | Tags for categorization |
| `prompt.metadata` | No | Additional prompt metadata |
| `agents` | No | List of agent specs (`provider:model`) (empty = use defaults) |
| `priority` | No | Processing priority (higher = first, default: 0) |
| `metadata` | No | Additional job metadata |

## Programmatic Usage

See `job_queue_example.py` for a complete Python example showing how to:

- Create a queue configuration
- Generate job files programmatically
- Process jobs with progress tracking
- Handle results

```python
from startd8 import JobQueue, JobQueueConfig, create_job_file

# Create config
config = JobQueueConfig(
    watch_folder=Path("~/startd8-jobs"),
    default_agents=["mock:mock-model"]
)

# Create queue
queue = JobQueue(config)

# Create a job
create_job_file(
    output_path=Path("~/startd8-jobs/my_task"),
    content="Your prompt here",
    agents=["mock:mock-model"]
)

# Process
queue.process_all()
```





