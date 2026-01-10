# Task Index — Startd8 MCP Builder

**Last Updated:** December 9, 2025  
**Purpose:** Multi-agent task coordination without conflicts

---

## Multi-Agent Coordination Rules

This task system is designed so **multiple AI agents can work independently** without overwriting each other's updates. Follow these rules:

### 1. File Ownership

- **Each task has its own file** (e.g., `TASK-001-mcp-server-core.md`)
- **Only one agent works on a task at a time**
- **Agents only modify their assigned task file**
- **This index file (`_TASK_INDEX.md`) is read-only for agents** — only humans update it

### 2. Task Lifecycle

```
OPEN → IN_PROGRESS → COMPLETED
         ↓
      BLOCKED → (resolved) → IN_PROGRESS
```

### 3. Claiming a Task

To work on a task:

1. Read this index to find an `OPEN` task
2. Open the task file (e.g., `TASK-003-evaluation-framework.md`)
3. Change `status: OPEN` to `status: IN_PROGRESS`
4. Add your agent identifier to `assigned_to:`
5. Begin work

### 4. Completing a Task

When done:

1. Update the task file with:
   - `status: COMPLETED`
   - `completed_date:`
   - Summary of what was done in the `## Completion Notes` section
2. Do NOT modify other task files or this index

### 5. Conflict Avoidance

- **Never modify `_TASK_INDEX.md`** — humans maintain this
- **Never modify another agent's in-progress task**
- **If blocked, add to `## Blockers` section in YOUR task file**
- **Create new tasks by notifying the human** (don't create files yourself)

---

## Task Categories

| Category | Prefix | Description |
|----------|--------|-------------|
| **Core** | `TASK-0xx` | MCP server implementation |
| **Test** | `TASK-1xx` | Testing and validation |
| **Docs** | `TASK-2xx` | Documentation |
| **Eval** | `TASK-3xx` | Evaluation and benchmarking |
| **Integ** | `TASK-4xx` | Integration (Cursor, SDK) |

---

## Current Tasks

### Open Tasks (Available for Assignment)

| ID | Title | Priority | Category | Dependencies |
|----|-------|----------|----------|--------------|
| TASK-003 | Evaluation Framework Design | High | Eval | None |
| TASK-004 | Benchmarking Workflow | High | Eval | TASK-003 |
| TASK-005 | Cursor Integration Testing | Medium | Integ | None |
| TASK-006 | Evaluation Reporter Tool | Medium | Eval | TASK-003 |
| TASK-007 | SDK Integration Planning | Medium | Core | None |
| TASK-201 | API Reference Documentation | Low | Docs | None |
| TASK-202 | Troubleshooting Guide | Low | Docs | None |

### In Progress Tasks

| ID | Title | Assigned To | Started |
|----|-------|-------------|---------|
| *None currently* | | | |

### Completed Tasks

| ID | Title | Completed | By |
|----|-------|-----------|-----|
| TASK-001 | MCP Server Core Implementation | 2025-12-08 | Claude |
| TASK-002 | JSON-First Refactor | 2025-12-09 | Claude |
| TASK-101 | Test Suite Implementation | 2025-12-08 | Claude |
| TASK-102 | Test Coverage Expansion | 2025-12-09 | Claude |

### Blocked Tasks

| ID | Title | Blocked By | Notes |
|----|-------|------------|-------|
| *None currently* | | | |

---

## Task Files

Each task has a dedicated file following this naming convention:

```
tasks/TASK-{ID}-{slug}.md
```

### Existing Task Files

```
tasks/
├── _TASK_INDEX.md              # This file (read-only for agents)
├── TASK-001-mcp-server-core.md
├── TASK-002-json-first-refactor.md
├── TASK-003-evaluation-framework.md
├── TASK-004-benchmarking-workflow.md
├── TASK-005-cursor-integration.md
├── TASK-006-evaluation-reporter.md
├── TASK-007-sdk-integration.md
├── TASK-101-test-suite.md
├── TASK-102-test-coverage.md
├── TASK-201-api-reference.md
└── TASK-202-troubleshooting.md
```

---

## How to Create a New Task

**Agents:** Do not create task files directly. Instead:

1. Document the need in your current task's `## Related Work` section
2. Notify the human project owner
3. Human will create the task file and update this index

**Humans:** To create a new task:

1. Choose the next available ID in the appropriate category
2. Create the task file using the template below
3. Add the task to this index under "Open Tasks"

---

## Task File Template

```markdown
# TASK-{ID}: {Title}

**Status:** OPEN | IN_PROGRESS | COMPLETED | BLOCKED  
**Priority:** High | Medium | Low  
**Category:** Core | Test | Docs | Eval | Integ  
**Created:** {date}  
**Assigned To:** {agent or "Unassigned"}  
**Dependencies:** {task IDs or "None"}  

---

## Objective

{Clear statement of what needs to be accomplished}

## Acceptance Criteria

- [ ] {Criterion 1}
- [ ] {Criterion 2}
- [ ] {Criterion 3}

## Context

{Background information, links to related docs}

## Implementation Notes

{Technical details, approach suggestions}

---

## Work Log

### {Date} - {Agent}

{Description of work done}

---

## Blockers

{Any issues preventing progress}

---

## Completion Notes

{Filled in when task is completed}

**Completed Date:** {date}  
**Summary:** {Brief summary of what was done}  
**Files Changed:** {List of files}  
**Commits:** {Commit hashes if applicable}
```

---

## Quick Reference

### Task Status Values

| Status | Meaning | Who Can Change |
|--------|---------|----------------|
| `OPEN` | Available for work | Human or claiming agent |
| `IN_PROGRESS` | Being worked on | Assigned agent |
| `COMPLETED` | Finished | Assigned agent |
| `BLOCKED` | Cannot proceed | Assigned agent |

### Priority Levels

| Priority | Meaning |
|----------|---------|
| **High** | Critical path, do first |
| **Medium** | Important, do after high |
| **Low** | Nice to have, do when free |

### Agent Identifiers

When claiming a task, use a clear identifier:

- `Claude-Cursor-{session-id}`
- `Claude-API-{date}`
- `Human-{name}`

---

## Coordination Log

Record of multi-agent coordination events:

| Date | Event | Notes |
|------|-------|-------|
| 2025-12-09 | Task system created | Initial setup |
| 2025-12-09 | TASK-001, TASK-002 marked complete | JSON-first refactor done |

---

**This index is maintained by the human project owner.**  
**Agents: Do not modify this file.**
