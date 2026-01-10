# Master Task List — Startd8 MCP Builder

**Purpose:** Self-contained task list for agent frameworks (Startd8, Claude, etc.)  
**Last Updated:** December 9, 2025  
**Project Path:** `/Users/neilyashinsky/Documents/Startd8/mcp/startd8-mcp-builder`

---

## How to Use This Document

This document contains everything an agent needs to:
1. **Understand the project** — Context, goals, architecture
2. **Select a task** — Prioritized list with dependencies
3. **Execute the task** — Detailed requirements and acceptance criteria
4. **Verify completion** — Clear success metrics

### For Agent Frameworks

```yaml
# Example Startd8 usage
skill: task-executor
input:
  task_list: MASTER_TASK_LIST.md
  mode: "execute_next"  # or "execute_specific: TASK-003"
```

---

## Project Context

### What Is This Project?

An **MCP (Model Context Protocol) server** that exposes Startd8 SDK capabilities to LLMs and IDEs (primarily Cursor).

### Key Capabilities

| Tool | Status | Purpose |
|------|--------|---------|
| `startd8_list_skills` | ✅ Done | Discover available Claude Skills |
| `startd8_get_skill_info` | ✅ Done | Get skill details and instructions |
| `startd8_use_skill` | ✅ Done | Generate responses with metrics |
| `startd8_compare_agents` | ⏳ Placeholder | Compare multiple agents |

### Architecture

```
Cursor/MCP Client → startd8_mcp.py → Anthropic API → Claude
                          ↓
                    JSON Metrics Output
```

### Key Files

| File | Purpose |
|------|---------|
| `startd8_mcp.py` | Main MCP server (~700 lines) |
| `tests/` | Test suite (73 tests) |
| `README_SERVER.md` | Usage documentation |
| `PROJECT_CHARTER.md` | Full project details |
| `tasks/` | Individual task files |

---

## Current Status

| Phase | Status | Progress |
|-------|--------|----------|
| Phase 1: MCP Server Core | ✅ Complete | 100% |
| Phase 2: JSON-First Metrics | ✅ Complete | 100% |
| Phase 3: Evaluations | 🔄 In Progress | 20% |
| Phase 4: Cursor Integration | 📋 Planned | 0% |
| Phase 5: SDK Integration | 📋 Planned | 0% |

---

## Task Queue

### Priority Legend

| Symbol | Meaning |
|--------|---------|
| 🔴 | **Critical** — Blocking other work |
| 🟠 | **High** — Important, do soon |
| 🟡 | **Medium** — Do after high priority |
| 🟢 | **Low** — Nice to have |

### Dependency Legend

| Symbol | Meaning |
|--------|---------|
| ✅ | Complete — Can reference for context |
| ⏳ | In Progress — Do not start |
| 🔓 | Open — Available to claim |
| 🚫 | Blocked — Waiting on dependency |

---

## Active Tasks (Ready to Work)

### TASK-003: Evaluation Framework Design 🟠

**Status:** 🔓 Open  
**Dependencies:** None  
**Estimated Effort:** 4-6 hours  
**Output:** `scripts/evaluation_runner.py`, `evaluations/` directory structure

#### Objective
Design and implement an evaluation framework that consumes JSON output from `startd8_use_skill` to enable systematic skill comparison.

#### Acceptance Criteria
- [ ] Define evaluation spec format (YAML recommended)
- [ ] Create `evaluation_runner.py` that executes skills
- [ ] Capture metrics from JSON responses
- [ ] Support multiple test cases per evaluation
- [ ] Generate structured results (JSON)
- [ ] Document the workflow

#### Implementation Guide

**Step 1: Create evaluation spec format**
```yaml
# evaluations/example_eval.yaml
evaluation:
  name: "skill-comparison-v1"
  description: "Compare game design skills"
  
skills:
  - html5-game-designer-pro
  - mcp-builder

test_cases:
  - id: TC001
    prompt: "Create a simple tower defense game"
    timeout_ms: 60000
    
  - id: TC002
    prompt: "Create a puzzle game with 3 levels"

metrics_to_collect:
  - latency_ms
  - input_tokens
  - output_tokens
  - output_length
```

**Step 2: Create evaluation runner**
```python
# scripts/evaluation_runner.py
import asyncio
import json
import yaml
from pathlib import Path
from startd8_mcp import startd8_use_skill, UseSkillInput, ResponseFormat

async def run_evaluation(spec_path: str) -> dict:
    # Load spec
    # For each skill × test_case:
    #   Call startd8_use_skill with JSON format
    #   Collect metrics
    # Return aggregated results
    pass
```

**Step 3: Create results structure**
```json
{
  "evaluation": "skill-comparison-v1",
  "run_date": "2025-12-09T10:00:00Z",
  "results": [...],
  "summary": {
    "total_tests": 4,
    "passed": 4,
    "avg_latency_ms": 2800
  }
}
```

#### Files to Create/Modify
- `scripts/evaluation_runner.py` (new)
- `evaluations/example_eval.yaml` (new)
- `evaluations/results/.gitkeep` (new)

#### Verification
```bash
# Test the runner
python scripts/evaluation_runner.py evaluations/example_eval.yaml
# Should produce evaluations/results/YYYY-MM-DD_example_eval.json
```

---

### TASK-005: Cursor Integration Testing 🟡

**Status:** 🔓 Open  
**Dependencies:** None  
**Estimated Effort:** 2-3 hours  
**Output:** Test results documented, issues filed

#### Objective
Test the MCP server with Cursor IDE to validate real-world usage.

#### Acceptance Criteria
- [ ] Server connects to Cursor
- [ ] All tools visible and callable
- [ ] Environment variables work
- [ ] Error handling verified
- [ ] Document any issues

#### Implementation Guide

**Step 1: Configure Cursor**
```json
// ~/.cursor/mcp.json
{
  "mcpServers": {
    "startd8": {
      "command": "python3",
      "args": ["/Users/neilyashinsky/Documents/Startd8/mcp/startd8-mcp-builder/startd8_mcp.py"],
      "env": {
        "ANTHROPIC_API_KEY": "${env:ANTHROPIC_API_KEY}",
        "STARTD8_SKILL_PATH": "${env:STARTD8_SKILL_PATH}"
      }
    }
  }
}
```

**Step 2: Test scenarios**

| Test | Action | Expected |
|------|--------|----------|
| CI-01 | "What skills are available?" | List returned |
| CI-02 | "Show me mcp-builder skill" | Details shown |
| CI-03 | "Use html5-game-designer-pro to make a game" | Code generated |
| CI-04 | Use skill without API key | Error message |
| CI-05 | Use non-existent skill | Error with suggestions |

**Step 3: Document results**
- Update `PROJECT_STATUS.md` with findings
- Create issues for any bugs found

#### Verification
All test scenarios pass or issues documented.

---

### TASK-007: SDK Integration Planning 🟡

**Status:** 🔓 Open  
**Dependencies:** None  
**Estimated Effort:** 3-4 hours  
**Output:** `SDK_INTEGRATION_PLAN.md`

#### Objective
Plan integration between MCP server and full Startd8 SDK for advanced features.

#### Acceptance Criteria
- [ ] Document SDK APIs needed
- [ ] Design integration architecture
- [ ] Plan `compare_agents` implementation
- [ ] Identify SDK changes needed
- [ ] Create implementation roadmap

#### Implementation Guide

**Step 1: Review SDK documentation**
- Path: `/Users/neilyashinsky/Documents/Startd8/dev/startd8-sdk-project/`
- Key files:
  - `docs/SDK_ARCHITECTURE_v1.md`
  - `docs/API_REFERENCE_v1.md`

**Step 2: Document integration points**
```markdown
# SDK_INTEGRATION_PLAN.md

## Current Architecture
MCP Server → Anthropic API (direct)

## Target Architecture  
MCP Server → Startd8 SDK → Anthropic API
                 ↓
            Response Storage

## Integration Points
1. startd8_use_skill — Use SDK for execution
2. startd8_compare_agents — Use SDK comparison API
3. New: startd8_run_workflow — Execute SDK workflows
```

**Step 3: Create roadmap**
- Phase A: SDK as optional backend
- Phase B: Response storage
- Phase C: Full workflow support

#### Verification
`SDK_INTEGRATION_PLAN.md` created with actionable roadmap.

---

## Blocked Tasks (Waiting on Dependencies)

### TASK-004: Benchmarking Workflow 🟠

**Status:** 🚫 Blocked by TASK-003  
**Dependencies:** TASK-003 (Evaluation Framework)  
**Estimated Effort:** 4-5 hours  

#### Objective
Create complete benchmarking workflow for comparing skills and tracking performance over time.

#### Will Include
- Multi-skill comparison
- Metrics aggregation
- Comparison reports
- Trend tracking

**Do not start until TASK-003 is complete.**

---

### TASK-006: Evaluation Reporter Tool 🟡

**Status:** 🚫 Blocked by TASK-003  
**Dependencies:** TASK-003 (Evaluation Framework)  
**Estimated Effort:** 3-4 hours  

#### Objective
Generate human-readable reports from evaluation results.

#### Will Include
- Markdown report generation
- Summary statistics
- Comparison tables
- Optional HTML output

**Do not start until TASK-003 is complete.**

---

## Low Priority Tasks

### TASK-201: API Reference Documentation 🟢

**Status:** 🔓 Open  
**Dependencies:** None  
**Estimated Effort:** 2-3 hours  

#### Objective
Create detailed API reference for all MCP tools.

#### Scope
- Full input schemas
- All response formats
- Error codes
- Complete examples

---

### TASK-202: Troubleshooting Guide 🟢

**Status:** 🔓 Open  
**Dependencies:** None  
**Estimated Effort:** 2 hours  

#### Objective
Help users diagnose and resolve common issues.

#### Scope
- Common errors and solutions
- Debugging tips
- Diagnostic commands

---

## Completed Tasks (Reference)

### TASK-001: MCP Server Core ✅

**Completed:** 2025-12-08  
**Summary:** Implemented core MCP server with 4 tools and skill:// resources.

### TASK-002: JSON-First Refactor ✅

**Completed:** 2025-12-09  
**Summary:** Refactored `startd8_use_skill` to return JSON with timing/token metrics.

### TASK-101: Test Suite ✅

**Completed:** 2025-12-08  
**Summary:** 73 tests covering all tools, validation, errors, workflows.

### TASK-102: Test Coverage Expansion ✅

**Completed:** 2025-12-09  
**Summary:** Added tests for JSON/Markdown formats and metrics.

---

## Agent Execution Rules

### Before Starting Any Task

1. **Read this document** to understand context
2. **Check task status** — Only work on 🔓 Open tasks
3. **Check dependencies** — Don't start blocked tasks
4. **Claim the task** — Update the task file in `tasks/`

### While Working

1. **Stay focused** — Complete one task before starting another
2. **Document progress** — Update the task file's Work Log
3. **Test your changes** — Run relevant tests
4. **Commit incrementally** — Clear commit messages

### After Completing

1. **Update task file** — Set status to COMPLETED
2. **Update PROJECT_STATUS.md** — Move task to completed
3. **Verify acceptance criteria** — All boxes checked
4. **Note any follow-up work** — In Related Work section

### If Blocked

1. **Document the blocker** in the task file
2. **Do not start dependent tasks**
3. **Consider switching to an unblocked task**

---

## Quick Start for Agents

### Option 1: Execute Next Priority Task

```
1. Find first 🔓 Open task with 🟠 or 🟡 priority
2. Read its Implementation Guide
3. Execute the steps
4. Verify with acceptance criteria
5. Mark complete
```

**Current recommendation:** Start with **TASK-003** (Evaluation Framework)

### Option 2: Execute Specific Task

```
1. Locate task by ID (e.g., TASK-005)
2. Verify it's 🔓 Open (not blocked)
3. Follow Implementation Guide
4. Complete and verify
```

### Option 3: Quick Win

For a faster completion, try **TASK-201** or **TASK-202** (documentation tasks).

---

## Environment Setup

### Required

```bash
# Python environment
cd /Users/neilyashinsky/Documents/Startd8/mcp/startd8-mcp-builder
pip install -r requirements-server.txt

# API key (for startd8_use_skill)
export ANTHROPIC_API_KEY="sk-ant-..."
```

### Optional

```bash
# Custom skill paths
export STARTD8_SKILL_PATH="~/my-skills"

# Run tests
pip install -r requirements-dev.txt
pytest tests/ -v
```

---

## Contact

**Project Owner:** Neil Yashinsky  
**Questions:** Document in task file or PROJECT_STATUS.md

---

**End of Master Task List**
