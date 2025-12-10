# Quick Reference - Agent Table Configuration

## Show/Hide Mock Agent

### Hide Mock Agent (Default)
Edit `~/.startd8/config.json`:
```json
{
  "tui": {
    "show_mock_agent": false
  }
}
```

### Show Mock Agent
Edit `~/.startd8/config.json`:
```json
{
  "tui": {
    "show_mock_agent": true
  }
}
```

## Adjust Page Size

### Show 5 Agents Per Page
```json
{
  "tui": {
    "agents_per_page": 5
  }
}
```

### Show 15 Agents Per Page
```json
{
  "tui": {
    "agents_per_page": 15
  }
}
```

## Navigation

When multiple pages exist:
- **Next Page**: Go to next page of agents
- **Previous Page**: Go to previous page
- **Done**: Exit agent status display

## Complete Config Example

`~/.startd8/config.json`:
```json
{
  "api_keys": {
    "anthropic": null,
    "openai": null
  },
  "models": {
    "claude": {
      "default": "claude-3-opus-20240229",
      "max_tokens": 4096
    },
    "gpt4": {
      "default": "gpt-4-turbo-preview",
      "max_tokens": 4096
    }
  },
  "preferences": {
    "auto_save_results": true,
    "default_agent": "claude",
    "show_cost_warnings": true
  },
  "tui": {
    "show_mock_agent": false,
    "agents_per_page": 10
  }
}
```

## Troubleshooting

### Changes not taking effect?
1. Save the config file
2. Restart the TUI completely
3. Check for JSON syntax errors

### Can't find config file?
Create it: `mkdir -p ~/.startd8 && touch ~/.startd8/config.json`

### Want to reset to defaults?
Delete config file: `rm ~/.startd8/config.json`

The TUI will recreate it with defaults on next launch.

---

**For detailed information, see**: `AGENT_DISPLAY_CONFIG.md`
