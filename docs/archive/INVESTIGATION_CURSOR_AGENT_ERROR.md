# Investigation: cursorAI_Composor Connection Error

**Date**: December 7, 2025  
**Status**: Root Cause Identified  
**Severity**: 🔴 Agent Unusable

---

## Summary

The "cursorAI_Composor" custom agent fails with a **DNS resolution error** when trying to distribute prompts. This is caused by **two independent issues**:

1. **Deprecated API Endpoint**: The preset uses `api.cursor.sh` which is **no longer active** (Cursor moved to `api.cursor.com`)
2. **Missing API Key**: The `CURSOR_API_KEY` environment variable is not set

---

## Error Analysis

### Error Message
```
httpcore.ConnectError: [Errno 8] nodename nor servname provided, or not known
openai.APIConnectionError: Connection error.
```

### What This Means
The error `[Errno 8] nodename nor servname provided, or not known` is a **DNS resolution failure**. The system cannot find the hostname `api.cursor.sh` because:

1. The domain no longer resolves to an IP address
2. Cursor has migrated their API to a new domain

---

## Root Cause Analysis

### Issue 1: Deprecated API Endpoint

**Current Configuration** (`custom_agents.json`):
```json
{
  "name": "cursorAI_Composor",
  "type": "openai_compatible",
  "base_url": "https://api.cursor.sh/v1",  // ❌ DEPRECATED
  "api_key_env": "CURSOR_API_KEY"
}
```

**Source of the Problem** (`tui_improved.py` line 387-391):
```python
OPENAI_COMPATIBLE_PRESETS = {
    'cursor': {
        'name': 'Cursor',
        'base_url': 'https://api.cursor.sh/v1',  # ❌ OUTDATED
        'api_key_env': 'CURSOR_API_KEY',
        'models': ['cursor-small', 'cursor-large', 'gpt-4', 'gpt-3.5-turbo']
    },
    # ...
}
```

**What Happened**:
- The old domain `api.cursor.sh` is **no longer active** as of late 2024/early 2025
- Cursor has transitioned to `api.cursor.com` for their API services
- Users creating "Cursor" agents get the outdated URL from the hardcoded preset

### Issue 2: Missing API Key

```bash
$ python3 -c "import os; print(os.getenv('CURSOR_API_KEY'))"
None
```

Even if the URL were correct, the API key is not set.

### Issue 3: Cursor API Limitations

**Important Discovery**: Cursor does NOT provide a public OpenAI-compatible API for external applications to use. Their API is designed for:
- Admin API (team management)
- Background Agents API (for Cursor's own features)

**The Cursor preset in startd8 is fundamentally misleading** - users cannot actually use Cursor's AI models through an external API.

---

## Current Agent Configuration

```json
{
  "name": "cursorAI_Composor",
  "type": "openai_compatible",
  "model": "cursor-large",
  "max_tokens": 4096,
  "base_url": "https://api.cursor.sh/v1",
  "provider": "cursor",
  "api_key_env": "CURSOR_API_KEY",
  "output_dir": "/Users/neilyashinsky/.../startd8_workspace",
  "id": "613dfbdd",
  "created": "2025-12-07T17:27:34.479559+00:00"
}
```

---

## Impact

| Aspect | Status |
|--------|--------|
| Agent creation | ✅ Works (but with invalid config) |
| Agent connection test | ❌ Fails silently or with error |
| Prompt distribution | ❌ Fails with connection error |
| User experience | 😕 Confusing - appears like a network issue |

---

# Implementation Plan

## Overview

This requires **3 levels of fixes**:

1. **Immediate**: Remove/deprecate the Cursor preset (it's not a real public API)
2. **Short-term**: Add validation and health checks for custom agents
3. **Medium-term**: Improve error handling and user guidance

---

## Phase 1: Remove Misleading Preset (High Priority)

**Effort**: 30 minutes  
**Files**: `src/startd8/tui_improved.py`

### Task 1.1: Remove or Deprecate Cursor Preset

**Option A: Remove Cursor from presets entirely**
```python
# Delete or comment out lines 387-392:
# 'cursor': {
#     'name': 'Cursor',
#     'base_url': 'https://api.cursor.sh/v1',
#     'api_key_env': 'CURSOR_API_KEY',
#     'models': ['cursor-small', 'cursor-large', 'gpt-4', 'gpt-3.5-turbo']
# },
```

**Option B: Mark as deprecated with warning**
```python
'cursor': {
    'name': 'Cursor (DEPRECATED - No Public API)',
    'base_url': 'https://api.cursor.com/v1',  # Updated but still won't work
    'api_key_env': 'CURSOR_API_KEY',
    'models': [],  # Empty - no public models
    'deprecated': True,
    'deprecation_note': 'Cursor does not offer a public OpenAI-compatible API'
},
```

### Task 1.2: Remove Cursor from Agent Creation Menu

**Location**: Lines 1174-1175
```python
# Remove or update:
# "⚡ Cursor",  # Remove this line
```

### Task 1.3: Add Deprecation Warning on Selection

If keeping the option, show warning when selected:
```python
elif "Cursor" in category:
    self.console.print(Panel(
        "[bold red]⚠️ Cursor API Not Available[/bold red]\n\n"
        "Cursor does not provide a public OpenAI-compatible API.\n"
        "The Cursor AI is only accessible within the Cursor editor.\n\n"
        "[bold]Alternatives:[/bold]\n"
        "  • Use Claude (Anthropic) directly\n"
        "  • Use GPT-4 (OpenAI) directly\n"
        "  • Use OpenRouter for multiple models",
        border_style="red"
    ))
    return
```

---

## Phase 2: Add Agent Validation (Medium Priority)

**Effort**: 2-3 hours  
**Files**: `src/startd8/tui_improved.py`, possibly `src/startd8/agents.py`

### Task 2.1: Validate Base URL Before Saving Agent

Add URL validation when creating agents:

```python
def _validate_base_url(self, base_url: str) -> Tuple[bool, str]:
    """Validate that a base URL is reachable"""
    import socket
    from urllib.parse import urlparse
    
    try:
        parsed = urlparse(base_url)
        hostname = parsed.hostname
        port = parsed.port or (443 if parsed.scheme == 'https' else 80)
        
        # Quick DNS check
        socket.getaddrinfo(hostname, port, socket.AF_UNSPEC, socket.SOCK_STREAM)
        return True, "URL is reachable"
    except socket.gaierror:
        return False, f"Cannot resolve hostname: {hostname}"
    except Exception as e:
        return False, f"Validation failed: {e}"
```

### Task 2.2: Add Validation to Agent Creation Flow

After getting base_url, validate it:

```python
# In _configure_openai_compatible(), after getting base_url:
if base_url and base_url.startswith('http'):
    self.console.print("[dim]Validating endpoint...[/dim]")
    valid, message = self._validate_base_url(base_url)
    if not valid:
        self.console.print(f"[yellow]⚠️ Warning: {message}[/yellow]")
        proceed = questionary.confirm(
            "The URL may not be reachable. Continue anyway?",
            default=False,
            style=custom_style
        ).ask()
        if not proceed:
            return None
```

### Task 2.3: Add Health Check Before Distribution

Before distributing prompts, verify agents are reachable:

```python
def _check_agent_health(self, agent: BaseAgent) -> Tuple[bool, str]:
    """Quick health check for an agent"""
    if isinstance(agent, OpenAICompatibleAgent):
        if agent.base_url:
            valid, msg = self._validate_base_url(agent.base_url)
            if not valid:
                return False, f"Endpoint unreachable: {msg}"
    return True, "OK"
```

---

## Phase 3: Improve Error Handling (Medium Priority)

**Effort**: 1-2 hours  
**Files**: `src/startd8/agents.py`, `src/startd8/tui_improved.py`

### Task 3.1: Catch DNS Errors Specifically

In `agents.py`, add specific handling for connection errors:

```python
# In OpenAICompatibleAgent.agenerate():
try:
    response = await self.async_client.chat.completions.create(...)
except openai.APIConnectionError as e:
    error_msg = str(e)
    if "nodename nor servname" in error_msg or "getaddrinfo" in error_msg:
        raise AgentError(
            f"DNS resolution failed for {self.base_url}. "
            f"The endpoint may be unreachable or the URL may be incorrect."
        ) from e
    raise
```

### Task 3.2: Show User-Friendly Error in TUI

When distribution fails, show helpful guidance:

```python
# In distribute prompt handling:
if "Connection error" in str(error) or "DNS" in str(error):
    self.console.print(Panel(
        f"[bold red]Connection Failed: {agent_name}[/bold red]\n\n"
        f"[bold]Possible causes:[/bold]\n"
        "  • The API endpoint URL is incorrect or outdated\n"
        "  • The API service is down\n"
        "  • Network connectivity issues\n\n"
        f"[bold]Base URL:[/bold] {agent.base_url}\n"
        f"[bold]Action:[/bold] Edit this agent in 'Manage Agents' to update the URL",
        border_style="red"
    ))
```

---

## Phase 4: Update Existing Configurations (User Action Required)

### Task 4.1: Add Migration Helper

Create a utility to detect and fix problematic agents:

```python
def _check_for_deprecated_agents(self):
    """Check for agents with deprecated configurations"""
    issues = []
    for agent in self.agent_manager.list_agents():
        if agent.get('base_url') == 'https://api.cursor.sh/v1':
            issues.append({
                'agent_id': agent['id'],
                'agent_name': agent['name'],
                'issue': 'Uses deprecated api.cursor.sh endpoint',
                'recommendation': 'Delete or reconfigure this agent'
            })
    return issues
```

### Task 4.2: Show Migration Notice on Startup

If deprecated agents are detected, show notice:

```python
# In _check_first_run_setup() or run():
deprecated_agents = self._check_for_deprecated_agents()
if deprecated_agents:
    self.console.print(Panel(
        "[bold yellow]⚠️ Deprecated Agent Configuration Detected[/bold yellow]\n\n"
        "The following agents use outdated configurations:\n" +
        "\n".join(f"  • {a['agent_name']}: {a['issue']}" for a in deprecated_agents) +
        "\n\n[bold]Recommendation:[/bold] Go to 'Manage Agents' to update or remove them.",
        border_style="yellow"
    ))
```

---

## Phase 5: Fix User's Current Configuration (Immediate User Action)

The user needs to either:

### Option A: Delete the cursorAI_Composor Agent

1. Open TUI
2. Go to "Manage Agents"
3. Select the cursorAI_Composor agent
4. Delete it

### Option B: Edit the Agent to Use a Working Provider

If the user wants similar functionality, reconfigure to use:
- **OpenRouter**: Access to Claude, GPT-4, and more through a single API
- **Direct Claude/GPT-4**: Use the built-in agents instead

---

## Summary of Changes

| Phase | Task | Effort | Priority |
|-------|------|--------|----------|
| 1 | Remove/deprecate Cursor preset | 30 min | 🔴 High |
| 2.1 | Add URL validation function | 30 min | 🟡 Medium |
| 2.2 | Validate URLs during agent creation | 30 min | 🟡 Medium |
| 2.3 | Health check before distribution | 30 min | 🟡 Medium |
| 3.1 | Specific DNS error handling | 30 min | 🟡 Medium |
| 3.2 | User-friendly error messages | 30 min | 🟡 Medium |
| 4.1 | Migration helper for deprecated agents | 30 min | 🟢 Low |
| 4.2 | Show migration notice on startup | 30 min | 🟢 Low |
| **Total** | | **~4 hours** | |

---

## Acceptance Criteria

### Must Have
- [ ] Cursor preset removed or marked as deprecated
- [ ] Users cannot accidentally create agents with defunct URLs
- [ ] Existing deprecated agents are detected and flagged

### Should Have
- [ ] URL validation before agent creation
- [ ] Health checks before prompt distribution
- [ ] Clear error messages explaining connection issues

### Nice to Have
- [ ] Automatic migration of deprecated agent configs
- [ ] Suggested alternatives when removing deprecated presets

---

## For the User (Immediate Fix)

To fix the `cursorAI_Composor` agent now, you have two options:

**Option 1: Delete the broken agent**
```bash
# Edit the config file directly:
nano ~/.startd8/custom_agents.json
# Remove the cursorAI_Composor entry from the "agents" array
```

**Option 2: Use TUI to delete**
1. Run `startd8`
2. Select "Manage Agents"
3. Select "cursorAI_Composor"
4. Choose "Delete"

**Note**: Cursor does not provide a public API for external applications. If you need access to multiple AI models, consider using:
- **OpenRouter** (supports Claude, GPT-4, Llama, and more)
- **Together AI** (supports open-source models)
- Direct **Claude** or **GPT-4** agents

---

**Investigation Complete**: December 7, 2025  
**Ready for Implementation**: Yes

