# Startd8 TUI User Guide

**Version:** 0.2.0  
**Document Version:** v1  
**Last Updated:** 2025-01-13

## Overview

The Startd8 TUI (Terminal User Interface) provides an interactive way to manage LLM agents, create prompts, distribute them to multiple agents, and compare results—all from your terminal.

## Launching the TUI

```bash
startd8 tui
```

## Main Menu Structure

The TUI is organized into four main sections:

```
═══ WORKFLOW ═══
  1️⃣  Create New Prompt
  📝  Prompt Builder (from templates)
  🔧  Enhance Prompt File
  📄  Document Updater
  🔗  Document Enhancement Chain (Multi-Agent)
  🚀  Run Design Pipeline (Draft → Review → Polish)
  📥  Job Queue
  2️⃣  Distribute Prompt to Agents
  3️⃣  View Results

═══ MANAGE ═══
  📋  List All Prompts
  🔍  Compare Prompt Responses
  📈  View Statistics

═══ AGENTS ═══
  🔬  Test Agent Connections
  🤖  Manage Agents
  🔑  Manage API Keys

═══ SYSTEM ═══
  📁  Manage Output Folders
  ❓  Help & Guide
  ❌  Exit
```

## Core Workflow

### Step 1: Create a Prompt

1. Select **1️⃣ Create New Prompt**
2. Enter your prompt text
3. Optionally add version and tags
4. The prompt is saved and becomes the "current prompt"

### Step 2: Distribute to Agents

1. Select **2️⃣ Distribute Prompt to Agents**
2. Choose from available agents:
   - **ALL AVAILABLE**: Run all agents with Ready status
   - **ONLY UNDISTRIBUTED**: Run only agents that haven't received this prompt
   - **Individual Agent**: Select a specific agent
3. Wait for responses

### Step 3: View Results

1. Select **3️⃣ View Results**
2. Compare responses side-by-side
3. View metrics (response time, tokens, cost)

## Agent Management

### Agent Types

| Type | Description |
|------|-------------|
| **Built-in** | Pre-configured agents (Claude, GPT-4, Mock) |
| **User added** | Custom-configured agents you create |

### Agent Status

| Status | Color | Meaning |
|--------|-------|---------|
| ✓ Ready | Green | Agent is configured and working |
| ⚠ Error | Yellow | Agent is configured but has issues |
| ✗ Not configured | Red | Agent needs configuration |

### Testing Agent Connections

1. Select **🔬 Test Agent Connections**
2. View the Agent Status table:
   - **Agent**: Agent name
   - **Type**: Built-in or User added
   - **Model/Key**: API key status or model name
   - **Source**: Where config comes from (env, config, stored)
   - **Status**: Ready, Error, or Not configured
   - **Details**: Additional information

### Managing User Added Agents

1. Select **🤖 Manage Agents**
2. Options:
   - **➕ Add New Agent**: Create a new agent configuration
   - **✏️ Edit Agent**: Modify existing agent
   - **🗑️ Delete Agent**: Remove an agent
   - **🔬 Test All Agents**: Verify all agents work

#### Adding a New Agent

1. Choose provider category:
   - Built-in Providers (Claude, GPT-4/OpenAI, Mock)
   - OpenAI-Compatible (Cursor, Ollama, Groq, Together, OpenRouter)
   - Custom Endpoint

2. Configure settings:
   - **Name**: Unique identifier (e.g., "my-claude-opus")
   - **Model**: Model to use
   - **Max Tokens**: Maximum response length
   - **Output Directory**: Where to save responses

### Managing API Keys

1. Select **🔑 Manage API Keys**
2. Options:
   - View current key status
   - Set/update API keys
   - Keys are stored securely in `~/.startd8/api_keys.json`

**Priority Order:**
1. Environment variables (highest)
2. Stored keys in config
3. Not set (lowest)

## Advanced Features

### Prompt Builder

Use templates to create structured prompts:

1. Select **📝 Prompt Builder**
2. Choose a template:
   - `design_document`: Create design documents
   - `project_plan`: Create project plans
   - `code_review`: Code review prompts
3. Fill in template variables
4. Preview and generate

### Document Enhancement Chain

Process documents through multiple agents sequentially:

1. Select **🔗 Document Enhancement Chain**
2. Select a document
3. Choose enhancement agents in order
4. Each agent improves upon the previous output

### Run Design Pipeline

Three-step design workflow:

1. Select **🚀 Run Design Pipeline**
2. Enter design task description
3. Select agents for each role:
   - **DRAFTER**: Creates initial design
   - **REVIEWER**: Critiques and finds gaps
   - **FINAL POLISH**: Finalizes the document
4. View and optionally save the result

### Job Queue

Process batch jobs from files:

1. Select **📥 Job Queue**
2. Options:
   - View pending jobs
   - Process jobs
   - Configure queue settings

## Output Folders

Organize agent outputs into separate folders:

1. Select **📁 Manage Output Folders**
2. Configure base directory
3. Each agent gets its own subfolder

```
outputs/
├── claude/
├── gpt4/
├── mock/
└── my-custom-agent/
```

## Configuration

### TUI Settings

Edit `~/.startd8/config.json`:

```json
{
  "tui": {
    "show_mock_agent": false,    // Hide mock from agent list
    "agents_per_page": 10        // Agents per page (pagination)
  }
}
```

### Display Options

- **Pagination**: When you have many agents, results are paginated
- **Agent Filtering**: Mock agent can be hidden in production

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| ↑/↓ | Navigate menu options |
| Enter | Select option |
| Ctrl+C | Cancel/Exit |
| Esc | Go back (in some contexts) |

## Troubleshooting

### No Agents Available

1. Check **🔬 Test Agent Connections** for status
2. Configure API keys via **🔑 Manage API Keys**
3. Verify environment variables are set

### Agent Shows Error Status

1. Check the **Details** column for specific error
2. Common issues:
   - Invalid API key
   - Network connectivity
   - Rate limiting
   - Model not available

### TUI Not Launching

Ensure dependencies are installed:

```bash
pip install questionary rich
```

## Tips

1. **Start with Mock**: Learn the workflow using Mock agents before configuring real LLMs
2. **Use Templates**: Prompt Builder templates ensure consistent, structured prompts
3. **Compare Results**: Always compare responses to find the best implementation
4. **Organize Outputs**: Use output folders to keep agent responses organized
5. **Test Connections**: Regularly test agent connections to catch issues early


