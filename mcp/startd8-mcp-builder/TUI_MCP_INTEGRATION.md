# TUI Capabilities Exposed via MCP

## Overview

All major TUI (Text User Interface) capabilities from the Startd8 SDK are now available via MCP (Model Context Protocol) tools. This allows LLMs to interact with the Startd8 framework programmatically.

## Available MCP Tools

### Prompt Management

#### `startd8_create_prompt`
Create a new versioned prompt.

**Input:**
- `content` (str): Prompt content
- `version` (str, optional): Version identifier (default: "1.0.0")
- `tags` (List[str], optional): Tags for categorization
- `metadata` (Dict, optional): Additional metadata
- `response_format` (ResponseFormat, optional): Output format (markdown/json)

**Example:**
```json
{
  "content": "Explain quantum computing",
  "version": "1.0.0",
  "tags": ["science", "quantum"],
  "response_format": "markdown"
}
```

#### `startd8_list_prompts`
List all prompts, optionally filtered by tags.

**Input:**
- `tags` (List[str], optional): Filter by tags
- `page` (int, optional): Page number (1-indexed)
- `page_size` (int, optional): Items per page (default: 50)
- `response_format` (ResponseFormat, optional): Output format

#### `startd8_get_prompt`
Get detailed information about a specific prompt.

**Input:**
- `prompt_id` (str): Prompt ID to retrieve
- `response_format` (ResponseFormat, optional): Output format

### Agent Operations

#### `startd8_distribute_prompt`
Distribute a prompt to one or more agents and get responses.

**Input:**
- `prompt_id` (str): Prompt ID to distribute
- `agents` (List[str], optional): Agent names (None = all available)
- `response_format` (ResponseFormat, optional): Output format

**Returns:** Results for each agent including response IDs, timing, and token usage.

#### `startd8_list_agents`
List all available agents in the framework"""
**Input:**
- `response_format` (ResponseFormat, optional): Output format

#### `startd8_test_agent_connection`
Test if an agent is properly configured and can be used.

**Input:**
- `agent_name` (str): Agent name to test
- `response_format` (ResponseFormat, optional): Output format

### Results & Comparison

#### `startd8_compare_responses`
Compare all responses for a prompt.

**Input:**
- `prompt_id` (str): Prompt ID to compare responses for
- `response_format` (ResponseFormat, optional): Output format

**Returns:** Comparison data including total responses, average response time, token usage, and individual response details.

### Statistics

#### `startd8_view_statistics`
View statistics about prompts and responses.

**Input:**
- `prompt_id` (str, optional): Filter by prompt ID
- `agent_name` (str, optional): Filter by agent name
- `response_format` (ResponseFormat, optional): Output format

## Response Formats

All tools support two response formats:

1. **Markdown** (default): Human-readable format with headers and formatting
2. **JSON**: Machine-readable format with structured data

## Usage Workflow

### Typical Workflow

1. **Create a prompt:**
   ```
   startd8_create_prompt({
     "content": "Your prompt here",
     "tags": ["category"]
   })
   ```

2. **List available agents:**
   ```
   startd8_list_agents()
   ```

3. **Distribute prompt to agents:**
   ```
   startd8_distribute_prompt({
     "prompt_id": "<prompt_id>",
     "agents": ["claude", "gpt4"]
   })
   ```

4. **Compare responses:**
   ```
   startd8_compare_responses({
     "prompt_id": "<prompt_id>"
   })
   ```

5. **View statistics:**
   ```
   startd8_view_statistics()
   ```

## Integration with Existing Tools

These new tools complement the existing MCP tools:
- `startd8_list_skills` - List Claude Skills
- `startd8_get_skill_info` - Get skill information
- `startd8_use_skill` - Use a skill-based agent
- `startd8_compare_agents` - Compare multiple agents (placeholder)
- `tasks.list` - List tasks
- `tasks.status` - Task status summary
- `tasks.run` - Execute tasks

## Error Handling

All tools use consistent error handling:
- Errors are returned as formatted strings
- JSON format includes error details in structured format
- Markdown format provides user-friendly error messages

## Future Enhancements

The following TUI capabilities are planned for future MCP integration:
- Design Pipeline workflow
- Document Enhancement Chain
- Job Queue management
- Prompt Builder (from templates)
- Document Updater
- Iterative Dev Workflow

## Notes

- All tools require the Startd8 SDK to be available (set `STARTD8_SDK_PATH`)
- Storage directory defaults to `~/.startd8` (can be set via `STARTD8_STORAGE_DIR`)
- Agent configuration must be set up before using agent-related tools
- Response format defaults to Markdown for better readability
