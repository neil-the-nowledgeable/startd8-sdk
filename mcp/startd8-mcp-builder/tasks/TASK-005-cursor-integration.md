# TASK-005: Cursor Integration Testing

**Status:** OPEN  
**Priority:** Medium  
**Category:** Integ  
**Created:** 2025-12-09  
**Assigned To:** Unassigned  
**Dependencies:** None  

---

## Objective

Test the MCP server integration with Cursor IDE to validate real-world usage and identify any issues.

## Acceptance Criteria

- [ ] Server connects to Cursor successfully
- [ ] All tools visible in Cursor's tool list
- [ ] `startd8_list_skills` works from Cursor
- [ ] `startd8_get_skill_info` works from Cursor
- [ ] `startd8_use_skill` generates responses
- [ ] Environment variables passed correctly
- [ ] Error handling works as expected
- [ ] Document any issues found

## Context

The MCP server has been tested with MCP Inspector and unit tests, but needs real-world testing with Cursor IDE to ensure it works correctly in the intended environment.

This is largely a manual testing task, though some automation may be possible.

## Implementation Notes

### Setup Steps

1. **Configure Cursor MCP settings**
   ```json
   // ~/.cursor/mcp.json
   {
     "mcpServers": {
       "startd8": {
         "command": "python3",
         "args": ["/path/to/startd8_mcp.py"],
         "env": {
           "ANTHROPIC_API_KEY": "${env:ANTHROPIC_API_KEY}",
           "STARTD8_SKILL_PATH": "/path/to/skills"
         }
       }
     }
   }
   ```

2. **Restart Cursor**

3. **Run test scenarios**

### Test Scenarios

| ID | Scenario | Expected Result |
|----|----------|-----------------|
| CI-01 | Ask "What skills are available?" | List of skills returned |
| CI-02 | Ask "Show me the mcp-builder skill" | Skill details displayed |
| CI-03 | Ask "Use html5-game-designer-pro to create a simple game" | Game code generated |
| CI-04 | Use skill without ANTHROPIC_API_KEY set | Error message shown |
| CI-05 | Use non-existent skill | Error with suggestions |
| CI-06 | Rapid successive requests | All handled correctly |

### Logging and Debugging

- Check Cursor logs for MCP connection issues
- Enable verbose logging if available
- Monitor server stdout/stderr

### Issues to Watch For

- Connection timeouts
- Environment variable not passed
- Large responses truncated unexpectedly
- Unicode handling issues
- Path resolution problems on different OS

---

## Work Log

*No work started yet*

---

## Blockers

*None*

---

## Completion Notes

*Task not yet complete*
