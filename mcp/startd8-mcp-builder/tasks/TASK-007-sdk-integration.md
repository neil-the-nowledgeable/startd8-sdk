# TASK-007: SDK Integration Planning

**Status:** OPEN  
**Priority:** Medium  
**Category:** Core  
**Created:** 2025-12-09  
**Assigned To:** Unassigned  
**Dependencies:** None  

---

## Objective

Plan and design the integration between the MCP server and the full Startd8 SDK, enabling advanced features like agent comparison and response storage.

## Acceptance Criteria

- [ ] Document SDK API surface needed by MCP
- [ ] Design integration architecture
- [ ] Plan `startd8_compare_agents` implementation
- [ ] Plan response storage integration
- [ ] Identify SDK changes needed (if any)
- [ ] Create implementation roadmap

## Context

The current MCP server uses the Anthropic API directly for simplicity. Full SDK integration would enable:

- **Agent comparison** — Run same prompt through multiple agents
- **Response storage** — Track responses in Startd8's storage system
- **Workflow support** — Execute multi-step workflows
- **SDK version tracking** — Populate `sdk.version` and `sdk.run_id`

Reference: `/Users/neilyashinsky/Documents/Startd8/dev/startd8-sdk-project/`

## Implementation Notes

### Current vs SDK Architecture

**Current (Direct API):**
```
MCP Server → Anthropic API → Claude
```

**With SDK:**
```
MCP Server → Startd8 SDK → Anthropic API → Claude
                ↓
           Response Storage
```

### SDK APIs to Investigate

From SDK docs, look for:
- Agent/skill execution API
- Response storage API
- Workflow execution API
- Multi-agent comparison API
- Version/run ID generation

### Integration Points

1. **`startd8_use_skill`**
   - Replace direct Anthropic call with SDK call
   - Enable response storage via SDK
   - Get `sdk.version` and `sdk.run_id` from SDK

2. **`startd8_compare_agents`**
   - Use SDK's comparison/benchmark API
   - Support configured agents (not just skills)
   - Return structured comparison results

3. **New Tools (Potential)**
   - `startd8_run_workflow` — Execute SDK workflows
   - `startd8_list_responses` — Query stored responses
   - `startd8_get_response` — Retrieve specific response

### Questions to Answer

1. What is the SDK's Python API for running agents?
2. How does response storage work?
3. What configuration is needed?
4. Can we incrementally integrate (keep direct API as fallback)?
5. What SDK version is required?

---

## Work Log

*No work started yet*

---

## Blockers

*None*

---

## Completion Notes

*Task not yet complete*
