## Startd8 + MCP Context for Google Antigravity (v1)

### Purpose

This document gives Google Antigravity a structured, reference-style overview of the Startd8 SDK and the Startd8 MCP integration so it can assist with design, implementation, and maintenance work.

- **Primary audience**: Google Antigravity models working with Startd8 and this MCP server.
- **Primary goal**: Provide a stable, linkable reference that explains how Startd8 is structured, what this MCP server does, and where to find detailed information.

### High-level Overview

- **Startd8** is an SDK and framework for:
  - **Skill-based agents** (specialized configurations and prompts).
  - **Prompt versioning** and evolution.
  - **Multi-agent workflows** (pipelines involving multiple skills and/or models).
  - **Response comparison and evaluation**.
  - **Job queues and batch processing**.
- **This project (`startd8-mcp-builder`)** focuses on:
  - Implementing a **Model Context Protocol (MCP) server** that exposes Startd8 capabilities as tools and resources.
  - Providing **LLM-oriented documentation** (including this file) for consistent behavior across Anthropic, Google Antigravity, and Cursor.

For detailed SDK-level design and architecture, see (on disk):

- `/Users/neilyashinsky/Documents/Startd8/dev/startd8-sdk-project/docs/SDK_ARCHITECTURE_v1.md`
- `/Users/neilyashinsky/Documents/Startd8/dev/startd8-sdk-project/docs/API_REFERENCE_v1.md`
- `/Users/neilyashinsky/Documents/Startd8/dev/startd8-sdk-project/docs/FEATURE_WORKFLOW_GUIDE.md`

### Current Phase: MCP Server First

The current work corresponds to **Phase 1: MCP Server** from:

- `/Users/neilyashinsky/Documents/FMLs/dev/version2/startd8/CURSOR_INTEGRATION_PROPOSAL.md`

Key implications:

- Focus is on a **working MCP server** that:
  - Exposes Startd8 skills and agents via tools (e.g., `list_skills`, `use_skill`, `compare_agents`).
  - Exposes Startd8 skills and configurations as **MCP resources**.
  - Is initially targeted at **personal developer use** inside Cursor and other environments.
- Later phases may add:
  - Deeper IDE mode integrations.
  - More sophisticated workflow and evaluation tooling.

### How Antigravity Should Use This Context

When working on Startd8 or this MCP server:

- **Use this file as the entry point**, but rely on the shared topic docs for detail:
  - `context/startd8_overview_v1.md`
  - `context/sdk_and_fmls_v1.md`
  - `context/evaluations_and_workflows_v1.md`
  - `context/mcp_integration_plan_v1.md`
  - `context/glossary_v1.md`
- **Prefer reference-style reasoning**:
  - Summarize or restate relevant sections from these docs when answering questions.
  - Include pointers back to specific files or paths on disk when helpful.
- **When proposing changes**:
  - Clearly indicate which files in this MCP project or in the SDK should be modified.
  - Keep suggestions consistent with terminology from `context/glossary_v1.md`.

### Related Context Files

- **Shared / cross-LLM context**:
  - `context/startd8_overview_v1.md`
  - `context/sdk_and_fmls_v1.md`
  - `context/evaluations_and_workflows_v1.md`
  - `context/mcp_integration_plan_v1.md`
  - `context/glossary_v1.md`
- **Other LLM-specific entry docs**:
  - `context/anthropic_context_v1.md`
  - `context/cursor_context_v1.md`

### Source-of-Truth Note

- Treat the following directories as the **authoritative state** of Startd8 and its SDK:
  - `/Users/neilyashinsky/Documents/biz/incubator/StartDateOSS`
  - `/Users/neilyashinsky/Documents/Startd8`
  - `/Users/neilyashinsky/Documents/Startd8/dev/startd8-sdk-project`
- Treat this MCP project (`startd8-mcp-builder`) as the **authoritative source** for:
  - MCP server implementation.
  - Shared context documentation.
  - Integration planning specific to MCP and IDE/tooling.


