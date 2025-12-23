# Startd8 Agent Configuration Guide

**Version:** 0.2.0  
**Document Version:** v1  
**Last Updated:** 2025-01-13

## Overview

This guide covers how to configure and manage agents in Startd8. Agents are the core components that interface with LLM providers to generate responses.

## Agent Types

### Built-in Providers (ProviderRegistry)

Startd8 ships with built-in providers discovered via `ProviderRegistry`:

| Provider | Example Model | API Key Env |
|----------|---------------|-------------|
| Anthropic (`anthropic`) | `claude-3-5-sonnet-20241022` | `ANTHROPIC_API_KEY` |
| OpenAI (`openai`) | `gpt-4-turbo-preview` | `OPENAI_API_KEY` |
| Google (`gemini`) | `gemini-1.5-pro` | `GOOGLE_API_KEY` |
| Ollama (`ollama`) | `llama3` | (optional) |
| Mock (`mock`) | `mock-model` | None required |

### User Added Agents

Custom-configured agents that you create via the TUI:

- Provider-backed agent configs (`type: "provider"` with `provider` + `model`)
- OpenAI-compatible custom endpoints (`type: "openai_compatible"` with `base_url` + `model`)

## Agent Status

Agents have one of three statuses:

| Status | Icon | Color | Meaning |
|--------|------|-------|---------|
| Ready | ✓ | Green | Agent is configured and operational |
| Error | ⚠ | Yellow | Configured but encountering issues |
| Not configured | ✗ | Red | Missing API key or configuration |

## Configuration Methods

### Method 1: Environment Variables (Recommended)

Set environment variables for API keys:

```bash
# Anthropic
export ANTHROPIC_API_KEY="sk-ant-..."

# OpenAI
export OPENAI_API_KEY="sk-..."

# Google Gemini
export GOOGLE_API_KEY="..."

# Optional: custom OpenAI-compatible endpoint key
export MY_CUSTOM_LLM_API_KEY="..."
```

**Best Practice**: Add these to your shell profile (`~/.zshrc`, `~/.bashrc`, etc.)

### Method 2: TUI Key Management

Store keys via the TUI:

1. Launch TUI: `startd8 tui`
2. Select **🔑 Manage API Keys**
3. Choose a key to set
4. Enter the API key value

Keys are stored in `~/.startd8/api_keys.json`

### Method 3: Configuration File

Edit `~/.startd8/config.json` directly:

```json
{
  "api_keys": {
    "anthropic": null,
    "openai": null,
    "google": null
  },
  "tui": {
    "show_mock_agent": false,
    "agents_per_page": 10
  }
}
```

## Priority Order

When loading API keys, Startd8 checks in this order:

1. **Environment Variables** (highest priority)
2. **Stored Keys** (`api_keys.json`)
3. **Config File** (`config.json`)

This allows you to:
- Use environment variables in production
- Store development keys for convenience
- Override stored keys with environment variables

## Creating User Added Agents

### Via TUI

1. Launch TUI: `startd8 tui`
2. Select **🤖 Manage Agents**
3. Select **➕ Add New Agent**
4. Choose agent type (provider-backed or OpenAI-compatible endpoint)
5. Configure settings

### Configuration Options

#### Provider-backed agent

```yaml
Name: my-anthropic-sonnet
Type: provider
Provider: anthropic
Model: claude-3-5-sonnet-20241022
Max Tokens: 8192
Output Directory: /path/to/outputs/my-anthropic-sonnet
```

#### OpenAI-compatible custom endpoint

```yaml
Name: my-custom-endpoint
Type: openai_compatible
Base URL: https://example.com/v1
Model: gpt-4o-mini
Max Tokens: 4096
API Key Env: MY_CUSTOM_LLM_API_KEY
Output Directory: /path/to/outputs/my-custom-endpoint
```

## User Added Agent Configuration File

User added agents are stored in `~/.startd8/custom_agents.json`:

```json
{
  "schema_version": 2,
  "agents": [
    {
      "id": "agent-abc123",
      "name": "my-anthropic-sonnet",
      "type": "provider",
      "provider": "anthropic",
      "model": "claude-3-5-sonnet-20241022",
      "max_tokens": 8192,
      "output_dir": "/path/to/outputs/my-anthropic-sonnet"
    },
    {
      "id": "agent-def456",
      "name": "my-custom-endpoint",
      "type": "openai_compatible",
      "base_url": "https://example.com/v1",
      "model": "gpt-4o-mini",
      "max_tokens": 4096,
      "api_key_env": "MY_CUSTOM_LLM_API_KEY",
      "output_dir": "/path/to/outputs/my-custom-endpoint"
    }
  ]
}
```

## Modular Agent Selection

The SDK provides a modular approach to selecting agents with Ready status:

### Python API

```python
from startd8.tui_improved import ImprovedTUI

tui = ImprovedTUI()

# Get all agents with Ready status
ready_agents = tui._get_ready_agents_for_selection()

# Each agent dict contains:
# - name: Agent name
# - model: Model being used
# - type: 'provider' or 'custom'
# - provider: Provider id (for provider-backed agents)
# - icon: Display icon
# - available: True (always, since filtered)
# - error: None (no error for ready agents)

# Select a single ready agent interactively
agent = tui._select_ready_agent("Select an agent", "Tip: use provider:model (e.g., openai:gpt-4-turbo-preview)")
```

### Integration Example

```python
# Design Pipeline uses modular agent selection
def run_design_pipeline():
    # Get ready agents for display
    ready_agents = self._get_ready_agents_for_selection()
    
    # Show available agents
    for agent in ready_agents:
        print(f"{agent['icon']} {agent['name']} ({agent['model']})")
    
    # Select agents for each pipeline step
    drafter = self._select_ready_agent("Select DRAFTER")
    reviewer = self._select_ready_agent("Select REVIEWER")
    polisher = self._select_ready_agent("Select FINAL POLISH")
```

## Output Directories

Each agent can have a dedicated output directory:

```
~/agent-outputs/
├── provider-anthropic/
│   ├── response-001.md
│   └── response-002.md
├── provider-openai/
│   └── response-003.md
└── my-custom-agent/
    └── response-004.md
```

Configure via TUI:
1. Select **📁 Manage Output Folders**
2. Set base directory
3. Folders are created automatically for each agent

## Testing Agents

### Via TUI

1. Select **🔬 Test Agent Connections**
2. View status table with all agents
3. Check for any errors

### Via CLI

```bash
startd8 test-agents
```

### Programmatically

```python
from startd8.tui_improved import AgentConfigTester

results = AgentConfigTester.test_all()

for agent_id, status in results.items():
    print(f"{agent_id}: {'✓' if status['working'] else '✗'}")
    if status['error']:
        print(f"  Error: {status['error']}")
```

## Troubleshooting

### "API Key Not Set"

1. Check environment variable is exported
2. Verify key is correct (no trailing whitespace)
3. Try setting via TUI key manager

### "Connection Error"

1. Check network connectivity
2. Verify API endpoint is accessible
3. Check for firewall/proxy issues

### "Invalid API Key"

1. Verify the key is valid with the provider
2. Check key hasn't expired
3. Ensure correct key for the provider

### "Model Not Found"

1. Verify model name is correct
2. Check model is available for your API tier
3. Update to a currently available model

### "Rate Limited"

1. Wait and retry
2. Reduce request frequency
3. Consider upgrading API plan

## Best Practices

1. **Use Environment Variables**: More secure than storing in files
2. **Test Regularly**: Verify agents are working before critical tasks
3. **Organize Outputs**: Use dedicated folders per agent
4. **Version Control**: Don't commit API keys to version control
5. **Mock First**: Test workflows with Mock agent before using real LLMs
6. **Monitor Costs**: Track token usage and costs per agent



