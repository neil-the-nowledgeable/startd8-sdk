## Startd8 MCP Integration Plan (v1)

### Purpose

This document summarizes the current plan for integrating Startd8 with external tools via the **Model Context Protocol (MCP)**, with special attention to Cursor as the first target.

It is based primarily on:

- `/Users/neilyashinsky/Documents/FMLs/dev/version2/startd8/CURSOR_INTEGRATION_PROPOSAL.md`

### Integration Options Considered

The Cursor integration proposal outlines three main options:

- **Option 1: Cursor Extension API**
  - Register a new Cursor mode (e.g., `startd8-skills`) via an extension.
  - Integrate deeply with Cursor’s mode and chat pipeline.
  - Requires specific Cursor-side APIs for mode registration and message handling.
- **Option 2: MCP Server (Current Focus)**
  - Expose Startd8 as an MCP server that Cursor can connect to today.
  - Provide tools and resources via the MCP protocol.
  - Uses existing Cursor infrastructure for MCP, with no Cursor-side changes required.
- **Option 3: Custom Chat Provider**
  - Register Startd8 as a chat provider that surfaces skills as “models”.
  - Route chat messages through Startd8 over HTTP or similar.
  - Depends on hypothetical or future Cursor APIs for chat provider registration.

### Recommended Approach (Phase 1)

The proposal’s recommended path, and the focus of this project, is:

- **Phase 1: MCP Server (Now)**
  - Build and run a Startd8 MCP server process, for example:
    - `startd8 mcp-server --port 8765`
  - Expose tools such as:
    - `list_skills` – list available skills.
    - `use_skill` – generate a response using a specific skill.
    - `compare_responses` or `compare_agents` – run prompts through multiple agents and compare.
    - `save_response` – track responses in Startd8’s storage.
  - Expose skills as **MCP resources**, e.g.:
    - `skill://<skill-name>` with markdown descriptions.
- **Future phases**:
  - Request enhanced Cursor APIs for custom modes and deeper integration.
  - Potentially create a dedicated “Skills” mode in Cursor that uses Startd8 under the hood.

### Role of This MCP Project

This repo (`startd8-mcp-builder`) serves as:

- The **implementation site** for the Startd8 MCP server.
- The **home for LLM context docs** that describe:
  - Startd8 (`startd8_overview_v1.md`).
  - The SDK and FMLs (`sdk_and_fmls_v1.md`).
  - Evaluations and workflows (`evaluations_and_workflows_v1.md`).
  - The integration plan (this file).
- A **safe place to iterate** on MCP design and tools, starting with a single user (the project author) as the primary consumer.

### Target MCP Capabilities (Phase 1)

For Phase 1, the MCP server should prioritize:

- **Skill and agent operations**:
  - `list_skills` – enumerate available skills.
  - `use_skill` – run a prompt through a chosen skill/agent.
  - `compare_agents` – send a prompt to multiple agents and compare responses.
- **Resource exposure**:
  - Expose skills as readable resources (e.g., markdown descriptions and metadata).
  - Optionally expose key Startd8 docs or configs as resources.
- **Developer-focused usage**:
  - Focus on empowering a single developer (the project author) to:
    - Experiment with skills and workflows from within Cursor.
    - Inspect and adjust Startd8-related artifacts through MCP tools.

Over time, additional tools may be added to:

- Inspect and modify FML/config files.
- Interact with evaluation pipelines.
- Scaffold new skills, workflows, or evaluation specs.

### Roadmap Summary

The integration proposal includes a high-level roadmap:

- **Phase 1** – MCP server for Startd8 (current focus; this project).
- **Phase 2** – Feature request and advocacy for Cursor mode APIs.
- **Phase 3** – Cursor extension using new APIs (if available).
- **Phase 4** – Native mode integration (if Cursor supports it).

This document focuses on **Phase 1** and should be kept aligned with implementation details as the MCP server is built.

### Next Steps for Implementers

- Define the **minimal viable set of MCP tools and resources** for Phase 1.
- Map those tools and resources to:
  - Concrete SDK APIs.
  - Configuration discovery and storage paths.
- Ensure **good, LLM-readable descriptions** for tools and resources so that:
  - Cursor (and other MCP clients) can use them effectively.
  - Other LLMs (Anthropic, Antigravity) can reason about and improve them over time.


