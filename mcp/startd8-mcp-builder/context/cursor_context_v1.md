## Startd8 + MCP Context for Cursor (v1)

### Purpose

This document explains how this repo and its context files should be used by Cursor as part of the Startd8 MCP integration.

- **Primary audience**: Cursor AI (especially in Agent mode) when connected to the Startd8 MCP server.
- **Primary goal**: Help Cursor understand what this project does, where to look for canonical information, and how to behave when editing code and docs related to Startd8 and the MCP server.

### Role of This Repo

- This repo, `startd8-mcp-builder`, is the **MCP and context hub** for Startd8.
- It is responsible for:
  - The **MCP server implementation** that exposes Startd8 capabilities to tools (starting with Cursor).
  - A curated set of **LLM context documents** under `context/` that describe Startd8, the SDK, and the MCP integration.
  - Acting as a **bridge** between the Startd8 SDK and external LLM tools.

The actual SDK and product documents live primarily under:

- `/Users/neilyashinsky/Documents/biz/incubator/StartDateOSS`
- `/Users/neilyashinsky/Documents/Startd8`
- `/Users/neilyashinsky/Documents/Startd8/dev/startd8-sdk-project`

These should be treated as **readable sources of truth** unless the user explicitly asks Cursor to modify them.

### Cursor-Specific Behavior Guidelines

- **When reasoning about Startd8**:
  - First consult the shared context docs in this repo:
    - `context/startd8_overview_v1.md`
    - `context/sdk_and_fmls_v1.md`
    - `context/evaluations_and_workflows_v1.md`
    - `context/mcp_integration_plan_v1.md`
    - `context/glossary_v1.md`
  - Then, if more detail is required, read the relevant docs or code in:
    - `/Users/neilyashinsky/Documents/Startd8/dev/startd8-sdk-project/`
    - `/Users/neilyashinsky/Documents/biz/incubator/StartDateOSS/`
- **When editing code**:
  - Prefer to make changes inside this MCP repo unless explicitly instructed otherwise.
  - Keep edits **small, well-scoped, and reviewable**.
  - Keep documentation and code **in sync**, especially when adjusting the MCP server’s tools or resources.
- **When editing context docs**:
  - Update the `_v1` documents incrementally, or create `_v2` variants when making larger changes.
  - Maintain consistency with terminology and definitions in `context/glossary_v1.md`.

### Relevant External Design Doc

The overall Cursor integration plan is described in:

- `/Users/neilyashinsky/Documents/FMLs/dev/version2/startd8/CURSOR_INTEGRATION_PROPOSAL.md`

Key points from that proposal:

- Startd8 should eventually integrate with Cursor as:
  - A **Skills mode** alongside existing modes (Agent, Ask, Plan), and/or
  - An **MCP server** exposing tools like `list_skills`, `use_skill`, `compare_agents`, and skill resources.
- **Phase 1 (now)** focuses on the **MCP server approach**, which:
  - Works with Cursor’s existing MCP support.
  - Exposes Startd8 skills and artifacts as tools and resources.

### How Cursor Should Use Context Files

- Treat this project’s `context/` directory as the **entry point** for understanding Startd8 and the MCP server:
  - `anthropic_context_v1.md`, `antigravity_context_v1.md`, `cursor_context_v1.md` give LLM-specific framing.
  - The shared topic docs and glossary provide stable reference material.
- When the user asks Cursor to:
  - **Design or modify the MCP server**: Read `context/mcp_integration_plan_v1.md` and relevant SDK docs before changing code.
  - **Explain or modify Startd8 SDK usage**: Use `context/startd8_overview_v1.md` and `context/sdk_and_fmls_v1.md`, then inspect the SDK repo as needed.
  - **Work with evaluations/workflows**: Use `context/evaluations_and_workflows_v1.md` and any linked SDK evaluation docs.

### Future Enhancements

Over time, this repo may add:

- A `.cursorrules` configuration tailored to Startd8 MCP work.
- Additional context files (e.g., `cursor_usage_patterns_v1.md`) with concrete examples of using MCP tools from within Cursor.
- More detailed per-tool documentation once the MCP server is implemented.


