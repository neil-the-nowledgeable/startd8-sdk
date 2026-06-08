# startd8 Quick Start Guide

**Version:** 0.4.0  
**Document Version:** v2  
**Last Updated:** 2026-06-08

## What is startd8?

**startd8-SDK** is a software-engineering harness and toolkit for LLM-assisted development. It
has two halves that work together:

1. **Deterministic-first code generation** — turn a data-model contract into a working
   application at **$0 LLM cost**, using language models only for integration glue. This is the
   headline capability (see the next section).
2. **Multi-LLM benchmarking & model evaluation** — compare and rank models (cloud and
   edge/local), version prompts, build multi-step workflows, and track token usage and costs.

The throughline: maximize deterministic generation, use LLMs only where they earn their cost —
a bridge toward deterministic, auditable generation for production/enterprise apps. The original
agent-framework capabilities are below; start with **Deterministic Code Generation** if you want
to build an app.

## Installation

### Option 1: pipx (Recommended)

```bash
# Install pipx if needed
brew install pipx  # macOS
# or: pip install --user pipx

pipx ensurepath

# Install startd8
pipx install startd8
```

### Option 2: pip

```bash
pip install startd8

# With LLM support
pip install "startd8[anthropic,openai]"
```

### Verify Installation

```bash
startd8 --version
```

## Configuration

### Set API Keys

```bash
# Claude
export ANTHROPIC_API_KEY="sk-ant-..."

# GPT-4
export OPENAI_API_KEY="sk-..."
```

Or use the TUI:
```bash
startd8 tui
# Select: 🔑 Manage API Keys
```

## Quick Start: Deterministic Code Generation ($0, no LLM)

The deterministic cascade projects **one Prisma data-model contract** into a working all-Python
application (Pydantic + SQLModel + FastAPI + HTMX) — no API calls, no cost.

```bash
# 1. Preview what the $0 cascade WILL build (read-only, advisory; add --json for CI)
startd8 wireframe --inputs assembly-inputs.yaml

# 2. Generate the full backend from the contract
startd8 generate backend --schema schema.prisma --out ./app

# 3. Emit project plumbing (pyproject / logging / alembic / Dockerfile) from app.yaml
startd8 generate scaffold --inputs app.yaml --out ./app

# 4. Emit composite/relational views (dashboard / board / workspace) from views.yaml
startd8 generate views --inputs views.yaml --out ./app

# 5. (optional) apply an accessible design theme to the built app ($0)
startd8 polish ./app
```

`startd8 generate --help` lists all four targets (`frontend`, `backend`, `scaffold`, `views`).

For a full requirements-doc → working-app run, use the **Capability Delivery Pipeline** from
`.cap-dev-pipe/` — see [Prime Contractor Workflow Guide](PRIME_CONTRACTOR_WORKFLOW_GUIDE.md).

### Evaluate models for a generation task

```bash
# Run the same seed through Prime Contractor across 2+ models (cloud + edge/local) and rank
startd8 compare-models --seed seed.json \
    --model anthropic:claude-sonnet-4-20250514 \
    --model ollama:llama3
```

## Quick Start: Interactive TUI

The fastest way to explore the benchmarking side:

```bash
startd8 tui
```

### Basic Workflow

1. **Test Agents**: Select `🔬 Test Agent Connections`
2. **Create Prompt**: Select `1️⃣ Create New Prompt`
3. **Distribute**: Select `2️⃣ Distribute Prompt to Agents`
4. **View Results**: Select `3️⃣ View Results`

## Quick Start: Python API

### Basic Usage

```python
from startd8 import AgentFramework
from startd8.providers import ProviderRegistry

# Initialize
framework = AgentFramework()

# Create a prompt
prompt = framework.create_prompt(
    content="Explain how to implement JWT authentication",
    version="1.0.0",
    tags=["auth", "jwt"]
)

# Get a response (using Mock provider for testing)
ProviderRegistry.discover()
mock = ProviderRegistry.get_provider("mock")
agent = mock.create_agent("mock-model")
response = agent.create_response(
    prompt_id=prompt.id,
    prompt=prompt.content
)

# Store response
framework.storage.save_response(response)

print(f"Response: {response.response[:200]}...")
print(f"Time: {response.response_time_ms}ms")
```

### Compare Multiple Agents

```python
from startd8 import AgentFramework
from startd8.providers import ProviderRegistry

framework = AgentFramework()

# Create prompt
prompt = framework.create_prompt(
    content="Write a Python function to validate email addresses",
    version="1.0.0"
)

# Get responses from multiple agents (provider:model)
ProviderRegistry.discover()
anthropic = ProviderRegistry.get_provider("anthropic")
openai = ProviderRegistry.get_provider("openai")
anthropic.validate_config({})
openai.validate_config({})

agents = [
    anthropic.create_agent("claude-sonnet-4-20250514"),
    openai.create_agent("gpt-4o"),
]

for agent in agents:
    response = agent.create_response(prompt.id, prompt.content)
    framework.storage.save_response(response)

# Compare results
comparison = framework.compare_responses(prompt.id)

print(f"Fastest: {comparison['rankings']['by_speed'][0]}")
print(f"Total tokens: {comparison['metrics']['total_tokens']}")
```

### Build a Pipeline

```python
from startd8 import WorkflowTemplates
from startd8.providers import ProviderRegistry

# Use pre-built template
ProviderRegistry.discover()
anthropic = ProviderRegistry.get_provider("anthropic")
openai = ProviderRegistry.get_provider("openai")
anthropic.validate_config({})
openai.validate_config({})

pipeline = WorkflowTemplates.design_review_chain(
    drafter_agent=anthropic.create_agent("claude-sonnet-4-20250514"),
    reviewer_agent=openai.create_agent("gpt-4o"),
    final_reviewer_agent=anthropic.create_agent("claude-sonnet-4-20250514")
)

result = pipeline.run("Design a REST API for a todo app")

print(f"Final design: {result.final_output}")
print(f"Total time: {result.total_time_ms}ms")
print(f"Total cost: ${result.total_cost:.4f}")
```

## Quick Start: CLI

### Create and Manage Prompts

```bash
# Create a prompt
startd8 create-prompt "Write unit tests for user service" \
    --version 1.0.0 \
    --tag testing

# List prompts
startd8 list-prompts

# Run benchmark with mock agent
startd8 run-benchmark <prompt-id> --agent mock:mock-model
```

### Run Pipelines

```bash
startd8 pipeline "Design a caching system" --workflow planner-implementer
```

### Job Queue

```bash
# Configure queue
startd8 queue configure

# Process jobs
startd8 queue run
```

## 5-Minute Tutorial

### Step 1: Launch TUI

```bash
startd8 tui
```

### Step 2: Test with Mock Agent

1. Select `🔬 Test Agent Connections`
2. Verify Mock agent shows ✓ Ready
3. Press any key to continue

### Step 3: Create a Prompt

1. Select `1️⃣ Create New Prompt`
2. Enter: "Explain the MVC pattern in 3 sentences"
3. Accept defaults for version and tags

### Step 4: Distribute to Agent

1. Select `2️⃣ Distribute Prompt to Agents`
2. Select your prompt
3. Choose `Mock` agent
4. Wait for response

### Step 5: View Results

1. Select `3️⃣ View Results`
2. See response with timing info
3. Compare metrics if multiple agents used

## Common Tasks

### Add a User Added Agent

```bash
startd8 tui
# Select: 🤖 Manage Agents
# Select: ➕ Add New Agent
# Follow prompts
```

### Use Prompt Templates

```bash
startd8 tui
# Select: 📝 Prompt Builder
# Choose template
# Fill variables
```

### Run Design Pipeline

```bash
startd8 tui
# Select: 🚀 Run Design Pipeline
# Enter description
# Select agents for each step
```

## Next Steps

1. **Build an app**: run the deterministic `generate` cascade against your `.prisma` contract
2. **Run the full pipeline**: requirements doc → working app via `.cap-dev-pipe/`
3. **Evaluate models**: `startd8 compare-models` across cloud and edge/local models
4. **Configure Real LLMs**: set up API keys for the integration passes
5. **Benchmark & automate**: prompt benchmarking, workflow templates, and the job queue

## Resources

- [Prime Contractor Workflow Guide](PRIME_CONTRACTOR_WORKFLOW_GUIDE.md) — requirements → app
- [SDK Architecture](SDK_ARCHITECTURE_v1.md)
- [API Reference](API_REFERENCE_v1.md)
- [Cost Tracking User Guide](COST_TRACKING_USER_GUIDE.md)
- [TUI User Guide](TUI_USER_GUIDE_v1.md)
- [Pipeline Workflows](PIPELINE_WORKFLOWS_v1.md)

## Getting Help

```bash
# CLI help
startd8 --help
startd8 <command> --help

# TUI help
startd8 tui
# Select: ❓ Help & Guide
```

## Troubleshooting

### "No agents available"

1. Check API keys are set: `echo $ANTHROPIC_API_KEY`
2. Test connections: TUI → `🔬 Test Agent Connections`
3. Use Mock agent for testing

### "Import error"

```bash
pip install startd8[all]
```

### "Command not found"

```bash
# Ensure pipx bin is in PATH
pipx ensurepath
source ~/.zshrc  # or ~/.bashrc
```


