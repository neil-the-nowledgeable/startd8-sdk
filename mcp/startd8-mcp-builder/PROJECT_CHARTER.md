# Startd8 MCP Builder — Project Charter

**Version:** 1.0  
**Last Updated:** December 9, 2025  
**Project Owner:** Neil Yashinsky  
**Repository:** `/Users/neilyashinsky/Documents/Startd8/mcp/startd8-mcp-builder`

---

## Executive Summary

The **Startd8 MCP Builder** project creates a Model Context Protocol (MCP) server that exposes Startd8 SDK capabilities to LLMs. This enables IDE integrations (starting with Cursor) to leverage skill-based agents, workflows, and evaluation pipelines through a standardized protocol.

---

## 1. Project Vision

### 1.1 What We're Building

An MCP server (`startd8_mcp`) that:

- **Exposes Claude Skills** as discoverable tools and resources
- **Enables skill-based generation** with Claude via the Anthropic API
- **Captures structured metrics** (timing, token usage) for evaluation and benchmarking
- **Provides a programmatic harness** for running and measuring agent performance
- **Integrates with Cursor IDE** as the first target consumer

### 1.2 Why We're Building It

1. **Bridge Startd8 and external tools** — LLMs and IDEs can discover and use Startd8 skills
2. **Enable metrics-driven development** — Capture quantitative data for agent comparison
3. **Standardize on MCP** — Use the Model Context Protocol for broad compatibility
4. **Iterate quickly** — Single-developer project with rapid feedback loops

### 1.3 Success Criteria

| Goal | Metric | Target |
|------|--------|--------|
| **Skill Discovery** | Skills discoverable in Cursor | 100% of configured skills |
| **Skill Execution** | Successful generation calls | >95% success rate |
| **Metrics Capture** | JSON output with timing/tokens | All successful calls |
| **Test Coverage** | Automated test coverage | >80% |
| **Documentation** | All tools documented | Complete |

---

## 2. Project Scope

### 2.1 In Scope (Phase 1)

| Component | Description | Status |
|-----------|-------------|--------|
| **MCP Server Core** | FastMCP-based server with stdio transport | ✅ Complete |
| **Tool: list_skills** | Discover and list available Claude Skills | ✅ Complete |
| **Tool: get_skill_info** | Retrieve skill details and instructions | ✅ Complete |
| **Tool: use_skill** | Generate responses with skill-based agents | ✅ Complete |
| **Resource: skill://** | Skills as MCP resources | ✅ Complete |
| **JSON Metrics** | Timing and token usage capture | ✅ Complete |
| **Test Suite** | Unit and workflow tests | ✅ Complete |
| **Documentation** | README, API docs, examples | ✅ Complete |

### 2.2 In Scope (Phase 2+)

| Component | Description | Status |
|-----------|-------------|--------|
| **Tool: compare_agents** | Multi-agent comparison on same prompt | ⏳ Placeholder |
| **Evaluation Framework** | Structured evaluation workflows | 🔄 In Progress |
| **SDK Integration** | Full Startd8 SDK features | 📋 Planned |
| **Cursor Integration** | Live testing with Cursor IDE | 📋 Planned |
| **Dashboard/Reporting** | Metrics visualization | 📋 Planned |

### 2.3 Out of Scope

- Direct modifications to Startd8 SDK source code
- Cursor extension development (requires Cursor APIs)
- Multi-provider support (OpenAI, etc.) — future consideration
- Cloud deployment — local development only for now

---

## 3. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        Cursor IDE / MCP Client                   │
└─────────────────────────┬───────────────────────────────────────┘
                          │ MCP Protocol (stdio)
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│                     startd8_mcp.py                               │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │ MCP Tools                                                    ││
│  │  • startd8_list_skills      [READ-ONLY]                     ││
│  │  • startd8_get_skill_info   [READ-ONLY]                     ││
│  │  • startd8_use_skill        [GENERATES + METRICS]           ││
│  │  • startd8_compare_agents   [PLACEHOLDER]                   ││
│  └─────────────────────────────────────────────────────────────┘│
│  ┌─────────────────────────────────────────────────────────────┐│
│  │ MCP Resources                                                ││
│  │  • skill://{skill_name}                                     ││
│  └─────────────────────────────────────────────────────────────┘│
└─────────────────────────┬───────────────────────────────────────┘
                          │ Anthropic API
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│                     Claude (Anthropic)                           │
└─────────────────────────────────────────────────────────────────┘
```

### 3.1 Design Principles

1. **JSON-First with Markdown View** — Internal canonical JSON, formatted output
2. **MCP as Harness** — Captures outputs + metrics, analysis happens externally
3. **Backward Compatibility** — Defaults preserve existing behavior
4. **Separation of Concerns** — MCP focused, SDK integration modular

---

## 4. Key Deliverables

### 4.1 Code Artifacts

| Artifact | Path | Purpose |
|----------|------|---------|
| MCP Server | `startd8_mcp.py` | Main implementation |
| Test Suite | `tests/` | Automated tests |
| Fixtures | `tests/fixtures.py` | Test data and mocks |
| Config | `cursor-mcp-config.json` | Cursor integration |

### 4.2 Documentation

| Document | Path | Purpose |
|----------|------|---------|
| Server README | `README_SERVER.md` | Usage and configuration |
| Quick Start | `QUICKSTART.md` | Getting started guide |
| Test Plan | `TEST_PLAN.md` | Test strategy |
| Implementation Summary | `IMPLEMENTATION_SUMMARY.md` | Phase completion summary |
| **Project Charter** | `PROJECT_CHARTER.md` | This document |
| **Project Status** | `PROJECT_STATUS.md` | Current status |
| **Task List** | `tasks/` | Multi-agent task tracking |

### 4.3 Context Documents (for LLMs)

| Document | Path | Purpose |
|----------|------|---------|
| Startd8 Overview | `context/startd8_overview_v1.md` | What is Startd8 |
| SDK and FMLs | `context/sdk_and_fmls_v1.md` | SDK structure |
| MCP Integration Plan | `context/mcp_integration_plan_v1.md` | Integration strategy |
| Evaluations | `context/evaluations_and_workflows_v1.md` | Evaluation approach |
| Glossary | `context/glossary_v1.md` | Term definitions |

---

## 5. Stakeholders

| Role | Name | Responsibilities |
|------|------|------------------|
| **Project Owner** | Neil Yashinsky | Vision, priorities, decisions |
| **Primary Developer** | AI Agents (Claude, Cursor) | Implementation, testing |
| **Primary Consumer** | Neil Yashinsky | Usage, feedback |

---

## 6. Constraints and Assumptions

### 6.1 Constraints

- **Single Developer** — Project designed for solo developer workflow
- **Local Development** — No cloud infrastructure initially
- **Cursor Focus** — Cursor is primary integration target
- **Anthropic Only** — Claude via Anthropic API (for now)

### 6.2 Assumptions

- Cursor MCP support remains stable
- Anthropic API availability and pricing reasonable
- SKILL.md format is standard for skills
- Python 3.10+ available on target systems

### 6.3 Dependencies

| Dependency | Version | Purpose |
|------------|---------|---------|
| `mcp` | ≥0.9.0 | MCP SDK |
| `pydantic` | ≥2.0.0 | Input validation |
| `pyyaml` | ≥6.0.0 | YAML parsing |
| `anthropic` | ≥0.18.0 | Claude API (optional) |

---

## 7. Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| MCP protocol changes | Low | High | Pin MCP version, monitor releases |
| Anthropic API changes | Low | Medium | Wrap API calls, version pin |
| Cursor integration issues | Medium | Medium | Test early and often |
| Skill format inconsistency | Medium | Low | Graceful fallbacks |

---

## 8. Timeline and Phases

### Phase 1: MCP Server Core ✅ COMPLETE

- [x] Basic MCP server with FastMCP
- [x] Skill discovery and listing
- [x] Skill info retrieval
- [x] Skill-based generation
- [x] JSON metrics capture
- [x] Test suite foundation
- [x] Documentation

### Phase 2: Refinement and Testing ✅ COMPLETE

- [x] JSON-first refactor with metrics
- [x] Enhanced Markdown output with metrics
- [x] Test coverage expansion
- [x] Documentation updates

### Phase 3: Evaluations 🔄 IN PROGRESS

- [ ] Evaluation framework design
- [ ] Benchmarking workflows
- [ ] Metrics collection tools
- [ ] Reporting/visualization

### Phase 4: Cursor Integration 📋 PLANNED

- [ ] Live Cursor testing
- [ ] User feedback collection
- [ ] Performance optimization
- [ ] Edge case handling

### Phase 5: SDK Integration 📋 PLANNED

- [ ] Full Startd8 SDK integration
- [ ] Agent comparison tool
- [ ] Workflow support
- [ ] Response storage

---

## 9. Related Documents

### Internal

- `startd8_use_skill_refactor_plan.md` — JSON-first refactor plan
- `REFACTOR_IMPLEMENTATION_SUMMARY.md` — Refactor completion summary
- `reference/python_mcp_server.md` — Python MCP implementation guide
- `reference/mcp_best_practices.md` — MCP best practices

### External

- [Cursor Integration Proposal](/Users/neilyashinsky/Documents/FMLs/dev/version2/startd8/CURSOR_INTEGRATION_PROPOSAL.md)
- [Startd8 SDK Architecture](/Users/neilyashinsky/Documents/Startd8/dev/startd8-sdk-project/docs/SDK_ARCHITECTURE_v1.md)

---

## 10. Approval and Change Control

### 10.1 Charter Approval

This charter is approved and active as of December 9, 2025.

### 10.2 Change Control

Changes to project scope, goals, or major architecture decisions should be:

1. Documented in a proposal (markdown file)
2. Reviewed against charter goals
3. Updated in this charter if approved
4. Reflected in `PROJECT_STATUS.md` and task files

---

## Appendix A: Glossary

| Term | Definition |
|------|------------|
| **MCP** | Model Context Protocol — standard for LLM tool integration |
| **Skill** | A named configuration (SKILL.md) defining agent behavior |
| **FML** | Force Multiplier Lab — skill development methodology |
| **Harness** | The MCP server's role as a metrics-capturing execution layer |

---

## Appendix B: File Structure

```
startd8-mcp-builder/
├── startd8_mcp.py              # Main MCP server
├── test_server.py              # Local testing script
├── requirements-server.txt     # Server dependencies
├── requirements-dev.txt        # Dev dependencies
├── cursor-mcp-config.json      # Cursor config example
├── SKILL.md                    # This project's skill definition
│
├── PROJECT_CHARTER.md          # This document
├── PROJECT_STATUS.md           # Current project status
├── tasks/                      # Multi-agent task tracking
│   ├── _TASK_INDEX.md          # Task index and rules
│   ├── TASK-001-*.md           # Individual task files
│   └── ...
│
├── context/                    # LLM context documents
│   ├── startd8_overview_v1.md
│   ├── sdk_and_fmls_v1.md
│   ├── mcp_integration_plan_v1.md
│   ├── evaluations_and_workflows_v1.md
│   └── glossary_v1.md
│
├── reference/                  # Implementation references
│   ├── python_mcp_server.md
│   ├── mcp_best_practices.md
│   └── evaluation.md
│
├── scripts/                    # Utility scripts
│   ├── evaluation.py
│   └── connections.py
│
├── tests/                      # Test suite
│   ├── conftest.py
│   ├── fixtures.py
│   ├── test_01_basic.py
│   └── ...
│
└── docs/                       # Additional documentation
    ├── README_SERVER.md
    ├── QUICKSTART.md
    ├── TEST_PLAN.md
    ├── IMPLEMENTATION_SUMMARY.md
    └── REFACTOR_IMPLEMENTATION_SUMMARY.md
```

---

**End of Project Charter**
