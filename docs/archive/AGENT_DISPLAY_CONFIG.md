# Agent Display Configuration

## Overview
The TUI agent status display is now configurable and supports pagination for better organization when you have many agents.

## Configuration File Location

The configuration is stored in: `~/.startd8/config.json`

## Configuration Options

### TUI Section

```json
{
  "tui": {
    "show_mock_agent": false,
    "agents_per_page": 10
  }
}
```

### Options

#### `show_mock_agent` (boolean)
- **Default**: `false`
- **Description**: Controls whether the Mock agent appears in the agent status table
- **Use case**: 
  - Set to `false` in production to hide the mock agent
  - Set to `true` during development/testing to see the mock agent

#### `agents_per_page` (integer)
- **Default**: `10`
- **Description**: Number of agents to display per page in the agent status table
- **Range**: 1-50 (recommended: 5-15 for best readability)
- **Use case**:
  - Increase for fewer pages if you have a large monitor
  - Decrease for better visibility on smaller screens

## Features

### Pagination
When you have more agents than `agents_per_page`, the TUI will automatically:
- Show page numbers (e.g., "Page 1/3")
- Provide "Next Page" and "Previous Page" navigation
- Display summary only on the first page

### Mock Agent Filtering
- By default, the mock agent is hidden from the status table
- This reduces clutter when working with real LLM agents
- The mock agent still works - it's just not shown in the status display

## How to Change Settings

### Method 1: Edit config.json directly

1. Open the config file:
   ```bash
   nano ~/.startd8/config.json
   ```

2. Add or modify the `tui` section:
   ```json
   {
     "api_keys": { ... },
     "models": { ... },
     "preferences": { ... },
     "tui": {
       "show_mock_agent": true,
       "agents_per_page": 5
     }
   }
   ```

3. Save and restart the TUI

### Method 2: Programmatically

```python
from startd8.config import ConfigManager
from pathlib import Path

config = ConfigManager(Path.home() / ".startd8")
config._config['tui'] = {
    'show_mock_agent': True,
    'agents_per_page': 15
}
config._save_config()
```

## Example Scenarios

### Scenario 1: Development Environment
Show mock agent for testing, 5 agents per page:
```json
{
  "tui": {
    "show_mock_agent": true,
    "agents_per_page": 5
  }
}
```

### Scenario 2: Production Environment
Hide mock agent, 10 agents per page:
```json
{
  "tui": {
    "show_mock_agent": false,
    "agents_per_page": 10
  }
}
```

### Scenario 3: Large Team with Many Custom Agents
Hide mock agent, show 15 agents per page:
```json
{
  "tui": {
    "show_mock_agent": false,
    "agents_per_page": 15
  }
}
```

## Agent Status Table Columns

The consolidated agent status table now shows:

| Column | Description |
|--------|-------------|
| **Agent** | Agent name |
| **Type** | Built-in (blue) or Custom (magenta) |
| **Model/API Key** | For built-in: API key status; For custom: model name |
| **Source** | Where the config comes from (env, stored, config) |
| **Status** | ✓ Ready / ⚠ Error / ✗ Not configured |
| **Details** | Additional information about the agent |

## Benefits

### Better Organization
- Cleaner display without mock agent in production
- Easy navigation with pagination
- Single unified table for all agents

### Flexibility
- Customize display for your workflow
- Adapt to team size and screen size
- Hide agents that aren't relevant

### Performance
- Faster rendering with pagination
- Only load visible agents
- Smooth navigation experience

## Troubleshooting

### Mock agent not showing even with `show_mock_agent: true`
1. Check the config file exists: `~/.startd8/config.json`
2. Verify the JSON syntax is valid
3. Restart the TUI
4. Check for typos in the setting name

### Pagination not working
1. Verify you have more agents than `agents_per_page`
2. Check that both built-in and custom agents are counted
3. Try setting a smaller `agents_per_page` value

### Changes not taking effect
1. Restart the TUI completely
2. Check file permissions on config.json
3. Look for error messages during TUI startup

## Future Enhancements

Potential future improvements:
- Sort options (by name, status, type)
- Filter by status (ready, error, not configured)
- Search/filter by name
- Export agent status to file
- Agent groups/categories
- Bulk agent management

---

**Last Updated**: December 7, 2025
