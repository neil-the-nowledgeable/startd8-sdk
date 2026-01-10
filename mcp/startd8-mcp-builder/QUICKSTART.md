# Startd8 MCP Server - Quick Start Guide

Get the Startd8 MCP server running in 5 minutes.

---

## 1. Install Dependencies (1 min)

```bash
cd /Users/neilyashinsky/Documents/Startd8/mcp/startd8-mcp-builder
pip install -r requirements-server.txt
```

---

## 2. Set API Key (30 sec)

```bash
export ANTHROPIC_API_KEY="sk-ant-your-key-here"
```

---

## 3. Test Locally (1 min)

```bash
python3 test_server.py
```

**Expected output:**
```
🧪 Startd8 MCP Server Tests

======================================================================
TEST: List Skills (Markdown)
======================================================================
# Available Claude Skills

Found N skill(s)

## mcp-builder
- Guide for creating high-quality MCP servers...

✅ All tests completed
```

---

## 4. Add to Cursor (2 min)

### Option A: Workspace Configuration

Create `.cursor/mcp.json` in your workspace:

```json
{
  "mcpServers": {
    "startd8": {
      "command": "/bin/sh",
      "args": ["-lc", "/Users/neilyashinsky/Documents/Startd8/mcp/startd8-mcp-builder/run_mcp.sh"],
      "env": {
        "ANTHROPIC_API_KEY": "${env:ANTHROPIC_API_KEY}",
        "STARTD8_MCP_QUIET": "1",
        "STARTD8_MCP_REGISTER_SKILL_TOOLS": "1",
        "STARTD8_MCP_MAX_SKILL_TOOLS": "100",
        "STARTD8_MCP_LOG_FILE": "${env:STARTD8_MCP_LOG_FILE}"
      }
    }
  }
}
```

### Option B: Global Configuration

Edit `~/.cursor/mcp.json` to add the `startd8` server.

---

## 5. Verify in Cursor (1 min)

1. Restart Cursor
2. Open any project
3. Start a chat
4. Type: "List available Startd8 skills"

**Expected:** Cursor should call `startd8_list_skills` and show available skills.

If you’re unsure what’s available, ask Cursor to call:
- `startd8_help` (capabilities + examples)
- `startd8_status` (diagnostics if skills/tools aren’t showing)

## Optional: Observability outside Cursor

- **Structured event log (JSONL)**: by default (when launched by an MCP client) the server writes to `logs/mcp-events.jsonl`. You can override with `STARTD8_MCP_EVENT_LOG_FILE`.
- **Prometheus metrics (optional)**: set `STARTD8_MCP_METRICS_PORT=9464` and install `prometheus-client`, then scrape `http://127.0.0.1:9464/metrics` and visualize in Grafana.

---

## Common Issues

### "No skills found"

**Solution:** Add skills to:
- `~/.startd8/skills/`
- `~/Documents/FMLs/dev/version2/`

Or set: `export STARTD8_SKILL_PATH="/path/to/your/skills"`

### "ANTHROPIC_API_KEY not set"

**Solution:** Export your key:
```bash
echo 'export ANTHROPIC_API_KEY="sk-ant-..."' >> ~/.zshrc
source ~/.zshrc
```

### "Anthropic SDK not installed"

**Solution:**
```bash
pip install anthropic
```

---

## Next Steps

- **Read Full Docs:** [README_SERVER.md](./README_SERVER.md)
- **Create Evaluations:** Follow [reference/evaluation.md](./reference/evaluation.md)
- **Review Implementation:** See [IMPLEMENTATION_SUMMARY.md](./IMPLEMENTATION_SUMMARY.md)

---

## Usage Examples

### List Skills

In Cursor chat:
```
What Claude Skills are available?
```

### Get Skill Details

```
Show me the mcp-builder skill instructions
```

### Use a Skill

```
Use the html5-game-designer-pro skill to create a simple catching game
```

### Compare Agents (Coming Soon)

```
Compare Claude and GPT-4 on this code review task: [paste code]
```

---

**That's it! You're ready to use Startd8 skills via MCP. 🚀**
