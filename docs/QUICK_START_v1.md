# Startd8 Quick Start Guide

**Version:** 0.4.0  
**Document Version:** v1  
**Last Updated:** 2025-01-13

## What is Startd8?

Startd8 (StartDate SDK) is a Python framework for:
- 🤖 Managing multiple LLM agents (Claude, GPT-4, etc.)
- 📝 Creating and versioning prompts
- 🔗 Building multi-step AI workflows
- 📊 Comparing and benchmarking responses
- 💰 Tracking token usage and costs

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

## Quick Start: Interactive TUI

The fastest way to get started:

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

1. **Configure Real LLMs**: Set up Claude or GPT-4 API keys
2. **Explore Pipelines**: Try different workflow templates
3. **Build Custom Workflows**: Create your own pipelines
4. **Compare Agents**: Benchmark different models
5. **Automate**: Use job queue for batch processing

## Resources

- [SDK Architecture](SDK_ARCHITECTURE_v1.md)
- [TUI User Guide](TUI_USER_GUIDE_v1.md)
- [Agent Configuration](AGENT_CONFIGURATION_GUIDE_v1.md)
- [API Reference](API_REFERENCE_v1.md)
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


