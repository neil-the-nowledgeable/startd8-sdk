# TASK-201: API Reference Documentation

**Status:** OPEN  
**Priority:** Low  
**Category:** Docs  
**Created:** 2025-12-09  
**Assigned To:** Unassigned  
**Dependencies:** None  

---

## Objective

Create comprehensive API reference documentation for the MCP server, documenting all tools, resources, and data structures.

## Acceptance Criteria

- [ ] Document all tool input schemas
- [ ] Document all response formats (JSON and Markdown)
- [ ] Document resource URIs
- [ ] Document error codes and messages
- [ ] Include complete examples
- [ ] Generate from code if possible

## Context

While README_SERVER.md covers basic usage, a more detailed API reference would help developers understand all options and edge cases.

## Implementation Notes

### Sections to Include

1. **Tools Reference**
   - `startd8_list_skills`
     - Full input schema with all fields
     - All response format examples
     - Error scenarios
   - `startd8_get_skill_info`
   - `startd8_use_skill`
   - `startd8_compare_agents`

2. **Resources Reference**
   - `skill://{name}` URI format
   - Response format
   - Error handling

3. **Data Structures**
   - ResponseFormat enum
   - JSON output schema
   - Error response format

4. **Configuration**
   - Environment variables
   - Cursor configuration
   - Skill path discovery

### Format Options

- Markdown file (`API_REFERENCE.md`)
- Generated from docstrings (Sphinx, pdoc)
- Inline in README (current approach)

---

## Work Log

*No work started yet*

---

## Blockers

*None*

---

## Completion Notes

*Task not yet complete*
