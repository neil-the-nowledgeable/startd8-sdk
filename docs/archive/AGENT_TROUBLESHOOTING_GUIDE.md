# Agent Configuration Troubleshooting Guide

## Issue: `'ClaudeAgent' object has no attribute 'agent_name'`

### Status: ✅ FIXED

**Error Message:**
```
AttributeError: 'ClaudeAgent' object has no attribute 'agent_name'
```

**Root Cause:**
- Agent instances store the name as `self.name`, not `self.agent_name`
- Some code was accessing `agent.agent_name` directly
- Only `SkillAgent` had a compatibility property, but other agents didn't

**Solution Applied:**
- Added `agent_name` property to `BaseAgent` class
- All agent subclasses now inherit this property
- Both `agent.name` and `agent.agent_name` work correctly

**Verification:**
All agent classes now support both access patterns:
- `agent.name` (original attribute) ✅
- `agent.agent_name` (compatibility property) ✅

---

## Common Agent Configuration Issues

### 1. Missing API Keys

**Symptoms:**
- Agent shows as "Not configured" or "Error" status
- Error messages about missing API keys
- Connection failures

**Solutions:**

#### For Anthropic/Claude:
```bash
export ANTHROPIC_API_KEY="sk-ant-..."
```

#### For OpenAI/GPT-4:
```bash
export OPENAI_API_KEY="sk-..."
```

#### For Google Gemini:
```bash
export GOOGLE_API_KEY="..."
```

#### Via TUI:
1. Launch TUI: `startd8 tui`
2. Select **🔑 Manage API Keys**
3. Choose provider and enter key

**Verification:**
```bash
# Check if key is set
echo $ANTHROPIC_API_KEY
echo $OPENAI_API_KEY
echo $GOOGLE_API_KEY
```

---

### 2. Invalid Model Names

**Symptoms:**
- "Model not found" errors
- 404 errors from API
- Agent creation fails

**Common Issues:**
- Using deprecated model names (e.g., `gemini-pro` instead of `gemini-1.5-flash`)
- Typos in model names
- Model not available for your API tier

**Solutions:**

#### Check Available Models:
```python
from startd8.providers.registry import ProviderRegistry

ProviderRegistry.discover()
provider = ProviderRegistry.get_provider("anthropic")
print(provider.supported_models)
```

#### Update Model Names:
- `gemini-pro` → `gemini-1.5-flash` or `gemini-1.5-pro`
- `claude-3-opus-20240229` → `claude-sonnet-4-20250514` (latest)
- `gpt-4-turbo-preview` → `gpt-4-turbo` or `gpt-4o`

---

### 3. Network/Connection Errors

**Symptoms:**
- DNS resolution failures
- Connection timeouts
- "nodename nor servname provided" errors

**Common Causes:**
- Deprecated API endpoints (e.g., `api.cursor.sh` → `api.cursor.com`)
- Network connectivity issues
- Firewall/proxy blocking API calls
- Invalid `base_url` for OpenAI-compatible agents

**Solutions:**

#### Check Network Connectivity:
```bash
# Test API endpoints
curl https://api.anthropic.com/v1/messages
curl https://api.openai.com/v1/models
```

#### Verify base_url:
For OpenAI-compatible agents, ensure `base_url` is correct:
- Ollama: `http://localhost:11434/v1`
- Together AI: `https://api.together.xyz/v1`
- Groq: `https://api.groq.com/openai/v1`

#### Update Deprecated Endpoints:
If using custom agents with deprecated endpoints:
1. Check provider's latest API documentation
2. Update `base_url` in agent configuration
3. Test connection via TUI: **🔬 Test Agent Connections**

---

### 4. Agent Creation Failures

**Symptoms:**
- Agent creation returns `None`
- Silent failures
- Configuration errors

**Debugging Steps:**

1. **Check Agent Type:**
   ```python
   from startd8.agents import ClaudeAgent
   
   try:
       agent = ClaudeAgent(name="test", model="claude-sonnet-4-20250514")
       print(f"✓ Agent created: {agent.name}")
   except Exception as e:
       print(f"✗ Error: {e}")
   ```

2. **Verify Configuration:**
   - Check `custom_agents.json` for syntax errors
   - Ensure required fields are present:
     - `name`: Agent identifier
     - `type`: Agent type (`claude`, `gpt4`, `openai_compatible`, etc.)
     - `model`: Model name
     - `api_key_env` or API key set

3. **Test via TUI:**
   - Use **🔬 Test Agent Connections** to diagnose issues
   - Check agent status table for specific errors

---

### 5. Provider Not Available

**Symptoms:**
- "Provider not found" errors
- Import errors for provider packages

**Solutions:**

#### Install Required Packages:
```bash
# For Anthropic
pip install anthropic

# For OpenAI
pip install openai

# For Gemini
pip install google-genai

# Or install all extras
pip install 'startd8[anthropic,openai,gemini]'
```

#### Check Provider Availability:
```python
from startd8.agents import _ANTHROPIC_AVAILABLE, _OPENAI_AVAILABLE, _GEMINI_AVAILABLE

print(f"Anthropic: {_ANTHROPIC_AVAILABLE}")
print(f"OpenAI: {_OPENAI_AVAILABLE}")
print(f"Gemini: {_GEMINI_AVAILABLE}")
```

---

### 6. Cost Tracking/Budget Issues

**Symptoms:**
- Budget exceeded errors
- Cost tracking not working
- Missing cost records

**Solutions:**

1. **Check Cost Tracker Configuration:**
   ```python
   from startd8.costs import CostTracker, CostStore
   from pathlib import Path
   
   store = CostStore(Path("costs.db"))
   tracker = CostTracker(store, enabled=True)
   ```

2. **Verify Budget Settings:**
   - Check budget limits are reasonable
   - Verify `block_on_exceed` setting
   - Check project/tag scoping

3. **Test Cost Recording:**
   ```python
   agent.cost_tracker = tracker
   response = agent.create_response(prompt_id="test", prompt="test")
   # Check if cost was recorded
   records = tracker.store.query()
   ```

---

## Testing Agent Configuration

### Quick Test Script

```python
#!/usr/bin/env python3
"""Quick test to verify agent configuration"""

from startd8.agents import MockAgent, ClaudeAgent

# Test MockAgent (always works)
agent = MockAgent(name="test", model="test-model")
assert agent.name == "test"
assert agent.agent_name == "test"  # Should work after fix
print("✓ MockAgent: OK")

# Test ClaudeAgent (requires API key)
try:
    agent = ClaudeAgent(name="test-claude", model="claude-sonnet-4-20250514")
    assert agent.name == "test-claude"
    assert agent.agent_name == "test-claude"  # Should work after fix
    print("✓ ClaudeAgent: OK")
except Exception as e:
    print(f"⚠ ClaudeAgent: {e}")
```

### Run Full Test Suite

```bash
# Run agent tests
pytest tests/unit/test_agents.py -v

# Test specific agent
pytest tests/unit/test_agents.py::TestMockAgent -v
```

---

## Agent Status Reference

| Status | Icon | Meaning | Action |
|--------|------|---------|--------|
| Ready | ✓ | Configured and working | Use normally |
| Error | ⚠ | Configuration issue | Check API key, model name |
| Not configured | ✗ | Missing API key | Set environment variable |

---

## Getting Help

1. **Check Logs:**
   - Default: `~/.startd8/logs/startd8.log`
   - Look for error messages and stack traces

2. **Use TUI Diagnostics:**
   - **🔬 Test Agent Connections**: Shows status of all agents
   - **🔧 Fix Agent Configuration Issues**: Interactive troubleshooting

3. **Verify Configuration:**
   - Check `~/.startd8/custom_agents.json` for syntax errors
   - Verify environment variables are set
   - Test API keys directly with provider

4. **Common Fixes:**
   - Restart TUI after setting environment variables
   - Recreate agent with correct configuration
   - Check provider status pages for outages

---

## Prevention Checklist

- [ ] Set API keys via environment variables (recommended)
- [ ] Use current model names (check provider docs)
- [ ] Test agent connection after creation
- [ ] Keep provider packages updated
- [ ] Use TUI's built-in diagnostics
- [ ] Check logs for detailed error messages
- [ ] Verify network connectivity for API calls

---

## Related Documentation

- `AGENT_CONFIGURATION_FIX.md` - Details of the `agent_name` fix
- `docs/AGENT_CONFIGURATION_GUIDE_v1.md` - Full configuration guide
- `INVESTIGATION_CURSOR_AGENT_ERROR.md` - Example of connection issue debugging

