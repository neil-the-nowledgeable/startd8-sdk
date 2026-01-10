# Startd8 MCP Server

An MCP (Model Context Protocol) server that exposes Startd8 SDK capabilities to LLMs, enabling skill-based agent workflows, multi-agent comparison, and response tracking.

## Features

- 🎯 **Skill Discovery**: Automatically finds and lists available Claude Skills
- 🤖 **Skill-Based Generation**: Use skills as system prompts for specialized agents
- 📊 **Agent Comparison**: Compare responses from multiple agents (placeholder)
- 📚 **MCP Resources**: Skills exposed as browsable resources via `skill://` URIs
- 🔄 **Response Tracking**: Optional integration with Startd8 storage

## Installation

### 1. Install Dependencies

```bash
cd /Users/neilyashinsky/Documents/Startd8/mcp/startd8-mcp-builder
pip install -r requirements-server.txt
```

### 2. Set API Key (Required for `startd8_use_skill`)

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
```

### 3. Configure Skill Paths (Optional)

By default, the server searches for skills in:
- `~/.startd8/skills/`
- `~/Documents/FMLs/dev/version2/`
- `./skills/`

To add custom paths:

```bash
export STARTD8_SKILL_PATH="~/my-skills:~/other-skills"
```

## Usage

### Run as Stdio Server (for Cursor, Claude Desktop)

```bash
./run_mcp.sh
```

**Important:** MCP stdio uses **stdout** for JSON-RPC. Do **not** pipe/redirect stdout (e.g. avoid `2>&1 | tee ...`).

To capture logs safely (stderr only), set:

```bash
STARTD8_MCP_LOG_FILE="/tmp/startd8-mcp.log" ./run_mcp.sh
```
### Test with MCP Inspector

```bash
npx @modelcontextprotocol/inspector ./run_mcp.sh
```

### Configure in Cursor

Add to your Cursor MCP configuration (`~/.cursor/mcp.json` or workspace settings):

```json
{
  "mcpServers": {
    "startd8": {
      "command": "/bin/sh",
      "args": ["-lc", "/Users/neilyashinsky/Documents/Startd8/mcp/startd8-mcp-builder/run_mcp.sh"],
      "env": {
        "ANTHROPIC_API_KEY": "${env:ANTHROPIC_API_KEY}",
        "STARTD8_SKILL_PATH": "${env:STARTD8_SKILL_PATH}",
        "STARTD8_MCP_LOG_FILE": "${env:STARTD8_MCP_LOG_FILE}"
      }
    }
  }
}
```

## Available Tools

### `startd8_help`

Explain what the Startd8 MCP server can do and how to use it.

**Parameters:**
- `topic` (optional): `"skills" | "tasks" | "prompts" | "agents" | "resources" | "diagnostics"`
- `response_format`: `"markdown"` (default) or `"json"`

**Example:**
```json
{
  "topic": "skills",
  "response_format": "markdown"
}
```

### `startd8_status`

Return server diagnostics (skills discovery, SDK importability, startup errors, resource/tool registration).

**Parameters:**
- `response_format`: `"markdown"` (default) or `"json"`
- `include_skill_names`: `true` (default) to include skill name list
- `include_pythonpath`: `true` to include full sys.path (very verbose; default `false`)

**Example:**
```json
{
  "response_format": "markdown",
  "include_skill_names": true,
  "include_pythonpath": false
}
```

### `startd8_list_skills`

List all discoverable Claude Skills.

**Parameters:**
- `response_format`: `"markdown"` (default) or `"json"`
- `include_details`: `true` to show full metadata (default: `false`)

**Example:**
```json
{
  "response_format": "markdown",
  "include_details": false
}
```

### `startd8_get_skill_info`

Get detailed information about a specific skill including full instructions.

**Parameters:**
- `skill_name`: Name or directory name of the skill
- `response_format`: `"markdown"` or `"json"`

**Example:**
```json
{
  "skill_name": "mcp-builder",
  "response_format": "markdown"
}
```

### `startd8_use_skill`

Generate a response using a skill-based Claude agent. Returns **structured metrics** including token usage and timing data, optionally formatted as JSON or Markdown.

**Parameters:**
- `skill_name`: Skill to use
- `prompt`: User prompt
- `model`: Claude model (default: `"claude-sonnet-4-20250514"`)
- `max_tokens`: Max response tokens (default: `16384`)
- `track_response`: Store in Startd8 storage (default: `true`)
- `response_format`: Output format `"markdown"` (default) or `"json"` for programmatic access

**Return Formats:**

#### Markdown Mode (Human-Readable)
Returns a formatted summary with metrics in the header:

```markdown
# Response from skill-name

**Model:** claude-sonnet-4-20250514
**Tokens:** 1234 in, 567 out (total 1801)
**Latency:** 2000 ms

---

[Generated response content here...]
```

#### JSON Mode (Programmatic)
Returns structured data suitable for benchmarking, evaluation, and metrics collection:

```json
{
  "skill_name": "html5-game-designer-pro",
  "skill_directory": "/Users/me/skills/html5-game-designer-pro",
  "model": "claude-sonnet-4-20250514",
  "prompt": "Create a tower defense game called Flower Defense",
  "output": "Here is the game code...",
  "response_format": "json",
  "usage": {
    "input_tokens": 1234,
    "output_tokens": 567,
    "total_tokens": 1801
  },
  "timing": {
    "started_at": "2025-12-09T10:00:00Z",
    "completed_at": "2025-12-09T10:00:02Z",
    "latency_ms": 2000
  },
  "sdk": {
    "version": null,
    "run_id": null,
    "provider": "anthropic"
  },
  "metadata": {},
  "error": null
}
```

**Examples:**

Markdown mode (interactive, human-readable):
```json
{
  "skill_name": "html5-game-designer-pro",
  "prompt": "Create a tower defense game called Flower Defense",
  "response_format": "markdown"
}
```

JSON mode (programmatic, metrics-focused):
```json
{
  "skill_name": "html5-game-designer-pro",
  "prompt": "Create a tower defense game called Flower Defense",
  "response_format": "json"
}
```

**Use Cases:**

- **Markdown mode**: Interactive use with LLMs, real-time feedback
- **JSON mode**: Benchmarking, evaluation workflows, metrics collection, comparison analysis

### `startd8_compare_agents`

Compare multiple agents on the same prompt (placeholder - requires full SDK).

**Parameters:**
- `prompt`: Prompt to send to all agents
- `agents`: List of agent names
- `response_format`: Output format

## Available Resources

### `skill://{skill_name}`

Access skill definitions as MCP resources.

**Example URIs:**
- `skill://mcp-builder`
- `skill://html5-game-designer-pro`
- `skill://skill-html_game_dev`

## Optional: One Tool Per Skill (for easier adoption)

By default, the server registers convenience tools for each discovered skill:

- Tool name pattern: `startd8_skill_<normalized_skill_name>`
- Each tool wraps `startd8_use_skill` with the skill preselected

Control via environment variables:

- `STARTD8_MCP_REGISTER_SKILL_TOOLS=1` (default: enabled)
- `STARTD8_MCP_MAX_SKILL_TOOLS=100` (cap to avoid huge tool lists)

If you prefer a smaller tool list in Cursor, disable per-skill tools:

```bash
export STARTD8_MCP_REGISTER_SKILL_TOOLS="0"
```

## Observability (outside Cursor)

The server is **stdio-based** (Cursor drives it), so observability must use **stderr**, **files**, or an optional **metrics side-channel** (never stdout).

### Structured event log (JSONL)

- Set `STARTD8_MCP_EVENT_LOG_FILE=/path/to/mcp-events.jsonl`
- The launcher defaults this automatically in MCP-client mode to: `logs/mcp-events.jsonl`

This file contains one JSON object per line for tool starts/ends + startup completion (good for Grafana Loki via Promtail).

### Prometheus metrics (optional)

- Set `STARTD8_MCP_METRICS_PORT=9464` (and optionally `STARTD8_MCP_METRICS_ADDR=127.0.0.1`)
- Install dependency: `pip install prometheus-client`

Then scrape `http://127.0.0.1:9464/metrics` from Prometheus and visualize in Grafana.

## Creating Skills

Skills are defined by `SKILL.md` files with YAML frontmatter:

```markdown
---
name: my-awesome-skill
description: Does amazing things
metadata:
  version: "1.0.0"
  author: Your Name
  tags: tag1, tag2, tag3
---

# My Awesome Skill — Agent Instructions

Your detailed agent instructions here...
```

Place skills in:
1. `~/.startd8/skills/my-skill/SKILL.md`
2. `~/Documents/FMLs/dev/version2/my-skill/SKILL.md`
3. Or custom path via `STARTD8_SKILL_PATH`

## Architecture

### MCP Server Structure

```
startd8_mcp.py
├── Tool: startd8_list_skills      [READ-ONLY]
├── Tool: startd8_get_skill_info   [READ-ONLY]
├── Tool: startd8_use_skill        [GENERATES RESPONSES + METRICS]
├── Tool: startd8_compare_agents   [PLACEHOLDER]
└── Resource: skill://{skill_name}
```

### MCP vs SDK Design Philosophy

The **MCP Server** acts as a **programmatic harness** for Startd8 skills:

1. **What the MCP Does:**
   - Exposes skills as tools/resources
   - Calls Claude with skill instructions as system prompt
   - **Captures raw outputs + resource usage** (tokens, latency, timing)
   - Returns structured data (JSON) or human-readable summaries (Markdown)

2. **What the MCP Does NOT Do:**
   - Analyze or score responses
   - Perform benchmarking or evaluation
   - Make comparisons or aggregate metrics

3. **How Analysis Happens:**
   - **Consumers** of the MCP (e.g., evaluation scripts, dashboards) collect the JSON outputs
   - **External tools** analyze, compare, and benchmark the collected metrics
   - This keeps the MCP focused and the analysis layer flexible

**Benefits:**
- MCP stays simple and maintainable
- Analysis tools can be swapped or upgraded independently
- Metrics are accessible to any consumer (CLI, web UI, notebooks, etc.)

## Development

### Verify Syntax

```bash
python -m py_compile startd8_mcp.py
```

### Test Tools Locally

```bash
# List skills
python -c "
import asyncio
from startd8_mcp import startd8_list_skills, ListSkillsInput, ResponseFormat
result = asyncio.run(startd8_list_skills(ListSkillsInput(response_format=ResponseFormat.MARKDOWN)))
print(result)
"
```

## Troubleshooting

### "No Claude Skills found"

- Check that SKILL.md files exist in skill directories
- Verify `STARTD8_SKILL_PATH` is set correctly
- Run `python startd8_mcp.py` and check for errors

### "ANTHROPIC_API_KEY not set"

- Export your API key: `export ANTHROPIC_API_KEY="sk-ant-..."`
- Or add to Cursor MCP config's `env` section

### "Anthropic Python SDK not installed"

```bash
pip install anthropic
```

## Evaluations & Benchmarking

The MCP provides raw metrics data. Use JSON mode to capture outputs and metrics for analysis:

```python
import json
import asyncio
from startd8_mcp import startd8_use_skill, UseSkillInput, ResponseFormat

async def benchmark_skill():
    # Get JSON output with metrics
    result_json = await startd8_use_skill(
        UseSkillInput(
            skill_name="my-skill",
            prompt="Test prompt",
            response_format=ResponseFormat.JSON
        )
    )
    
    # Parse and analyze
    data = json.loads(result_json)
    print(f"Tokens used: {data['usage']['total_tokens']}")
    print(f"Latency: {data['timing']['latency_ms']}ms")
    print(f"Output length: {len(data['output'])} chars")

asyncio.run(benchmark_skill())
```

**For detailed evaluation workflows, see:**
- `context/evaluations_and_workflows_v1.md` - Evaluation strategy
- `reference/evaluation.md` - Evaluation reference implementation
- `scripts/evaluation.py` - Example evaluation script

## Next Steps

1. ✅ **Phase 1 Complete**: MCP server implemented
2. ✅ **Phase 2 Complete**: JSON-first metrics architecture
3. 🔄 **Phase 3**: Create evaluations and benchmarking tools
4. 🚀 **Phase 4**: Test with Cursor integration
5. 📈 **Phase 5**: Add full Startd8 SDK integration for agent comparison

## Related Files

- `SKILL.md` - This MCP builder skill (meta!)
- `reference/python_mcp_server.md` - Python implementation guide
- `reference/mcp_best_practices.md` - MCP best practices
- `context/mcp_integration_plan_v1.md` - Integration plan
- `/Users/neilyashinsky/Documents/FMLs/dev/version2/startd8/CURSOR_INTEGRATION_PROPOSAL.md` - Full proposal

## License

See `LICENSE.txt`
