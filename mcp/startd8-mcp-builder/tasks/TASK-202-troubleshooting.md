# TASK-202: Troubleshooting Guide

**Status:** OPEN  
**Priority:** Low  
**Category:** Docs  
**Created:** 2025-12-09  
**Assigned To:** Unassigned  
**Dependencies:** None  

---

## Objective

Create a troubleshooting guide that helps users diagnose and resolve common issues with the MCP server.

## Acceptance Criteria

- [ ] Document common error messages and solutions
- [ ] Include debugging tips
- [ ] Cover environment setup issues
- [ ] Cover Cursor integration issues
- [ ] Include diagnostic commands

## Context

Users may encounter various issues when setting up or using the MCP server. A troubleshooting guide reduces support burden and improves user experience.

## Implementation Notes

### Sections to Include

1. **Installation Issues**
   - Missing dependencies
   - Python version problems
   - Path issues

2. **Configuration Issues**
   - Environment variables not set
   - Cursor MCP config errors
   - Skill path not found

3. **Runtime Issues**
   - Server won't start
   - Connection failures
   - Timeout errors

4. **Tool-Specific Issues**
   - Skills not discovered
   - Generation failures
   - API key errors

5. **Diagnostic Commands**
   ```bash
   # Test server startup
   python3 startd8_mcp.py
   
   # Test with MCP Inspector
   npx @modelcontextprotocol/inspector python3 startd8_mcp.py
   
   # Check skill discovery
   python3 -c "from startd8_mcp import _find_skills; print(_find_skills())"
   ```

### Error Message Reference

| Error | Cause | Solution |
|-------|-------|----------|
| "ANTHROPIC_API_KEY not set" | Missing env var | Export the variable |
| "No Claude Skills found" | No SKILL.md files | Check skill paths |
| "Skill not found" | Typo in name | Check available skills |

---

## Work Log

*No work started yet*

---

## Blockers

*None*

---

## Completion Notes

*Task not yet complete*
