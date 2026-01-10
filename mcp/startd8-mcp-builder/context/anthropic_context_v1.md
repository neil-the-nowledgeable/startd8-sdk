## Startd8 + MCP Context for Anthropic (v1)

### Purpose

This document provides Anthropic models with a concise overview of the Startd8 ecosystem and this MCP integration so they can act as effective developer assistants for Startd8 work.

- **Primary audience**: Anthropic models used from IDEs, terminals, or notebooks when working on Startd8 and its MCP server.
- **Primary goal**: Enable the model to understand what Startd8 is, how the SDK and FMLs fit together, and how this MCP project is intended to be used and extended.

### High-level Overview

- **Startd8** is an SDK and framework for:
  - **Skill-based agents** (specialized, reusable system prompts / configurations).
  - **Prompt versioning** (tracking and evolving prompts over time).
  - **Multi-agent workflows** (pipelines that can route through multiple LLMs or skills).
  - **Response comparison and evaluation** (benchmarking different approaches or agents).
  - **Job queues and batch processing**.
- **This MCP project** (`startd8-mcp-builder`) is the hub for:
  - A **Model Context Protocol (MCP) server** that exposes Startd8 capabilities as tools and resources.
  - **LLM context documents** tailored for Anthropic, Google Antigravity, and Cursor.
  - Integration planning and glue code that connect the Startd8 SDK to external LLM tools.

For deeper background on Startd8’s SDK design and architecture, see:

- `/Users/neilyashinsky/Documents/Startd8/dev/startd8-sdk-project/docs/SDK_ARCHITECTURE_v1.md`
- `/Users/neilyashinsky/Documents/Startd8/dev/startd8-sdk-project/docs/API_REFERENCE_v1.md`
- `/Users/neilyashinsky/Documents/Startd8/dev/startd8-sdk-project/docs/FEATURE_WORKFLOW_GUIDE.md`

### Current Phase and Scope

The current work corresponds to **Phase 1: MCP Server**, as described in:

- `/Users/neilyashinsky/Documents/FMLs/dev/version2/startd8/CURSOR_INTEGRATION_PROPOSAL.md`

In this phase:

- The focus is on building an MCP server that:
  - Exposes Startd8 **skills and agents** through tools (e.g., `list_skills`, `use_skill`, `compare_agents`).
  - Exposes Startd8 **configuration and design artifacts** (FMLs, evaluation specs, docs) as resources.
  - Enables **personal developer use first** (single-user, low security concerns).
- Primary client priority is **Cursor**, but context is being prepared so that Anthropic can:
  - Help reason about the MCP server design and implementation.
  - Assist in writing and evolving the associated context docs.
  - Understand the broader Startd8 SDK and its design documents.

### How Anthropic Should Use This Context

- **When asked to work on Startd8 or the MCP server**:
  - Prefer to first consult the shared topic docs in this project:
    - `context/startd8_overview_v1.md`
    - `context/sdk_and_fmls_v1.md`
    - `context/evaluations_and_workflows_v1.md`
    - `context/mcp_integration_plan_v1.md`
    - `context/glossary_v1.md`
  - Treat these as the **primary source of high-level truth**, and then drill into the external SDK/docs as needed.
- **When generating or modifying code**:
  - Keep changes **small and reviewable**, especially in the MCP server and context documents.
  - Maintain consistency with terminology defined in `context/glossary_v1.md`.
  - If unsure about a detail in the SDK, prefer reading the relevant docs or code from:
    - `/Users/neilyashinsky/Documents/Startd8/dev/startd8-sdk-project/`
- **When updating documentation**:
  - Update the `_v1` documents incrementally or create `_v2` variants as needed, preserving clear version history in filenames.

### Related Context Files in This Project

- **Shared / cross-LLM context**:
  - `context/startd8_overview_v1.md`
  - `context/sdk_and_fmls_v1.md`
  - `context/evaluations_and_workflows_v1.md`
  - `context/mcp_integration_plan_v1.md`
  - `context/glossary_v1.md`
- **Other LLM-specific entry docs**:
  - `context/antigravity_context_v1.md`
  - `context/cursor_context_v1.md`

### Source-of-Truth Note

- Unless explicitly stated otherwise, the **authoritative source of truth** for Startd8 and the SDK is the **current filesystem state** under:
  - `/Users/neilyashinsky/Documents/biz/incubator/StartDateOSS`
  - `/Users/neilyashinsky/Documents/Startd8`
  - `/Users/neilyashinsky/Documents/Startd8/dev/startd8-sdk-project`
- This project (`startd8-mcp-builder`) contains **derivative context** and MCP-related code that should remain aligned with those sources over time.


