## Startd8 Overview (v1)

### What Is Startd8?

Startd8 is an SDK and framework for building and running **skill-based LLM agents and workflows**.

- **Core capabilities** (as of the current design and docs):
  - **Skill-based agents**: Reusable, named configurations (prompts + settings) that encapsulate a specific capability or persona.
  - **Prompt versioning**: Structured tracking and evolution of system and user prompts over time.
  - **Multi-agent workflows**: Pipelines that orchestrate multiple agents and/or models for complex tasks.
  - **Response comparison**: Tools to compare different agents or strategies on the same tasks.
  - **Job queues and batch processing**: Running many jobs or evaluations in a managed way.

Startd8’s detailed architecture, workflows, and design decisions are documented primarily in the **Startd8 SDK project** and the **StartDate OSS** materials:

- `/Users/neilyashinsky/Documents/Startd8/dev/startd8-sdk-project/`
- `/Users/neilyashinsky/Documents/biz/incubator/StartDateOSS/`

### Key Repositories and Directories

- **Startd8 SDK project**
  - Path: `/Users/neilyashinsky/Documents/Startd8/dev/startd8-sdk-project/`
  - Contains:
    - Core SDK source code.
    - Design and architecture docs, including:
      - `docs/SDK_ARCHITECTURE_v1.md`
      - `docs/API_REFERENCE_v1.md`
      - `docs/PIPELINE_WORKFLOWS_v1.md`
      - `docs/FEATURE_WORKFLOW_GUIDE.md`
      - `docs/design/STARTD8_CHAT_MULTI_AGENT_DESIGN_v1.md`
      - `docs/design/STARTD8_CHAT_MULTI_AGENT_DESIGN_v2.md`
      - Other design and review documents under `docs/design/`.
- **StartDate OSS / high-level framing**
  - Path: `/Users/neilyashinsky/Documents/biz/incubator/StartDateOSS/`
  - Contains:
    - README and introductory docs (e.g., `README.md`, `Intro.md`).
    - Materials describing Start Date’s LLM agentic OSS framing and related SDK info.
    - Design docs such as `startdate-sdk/docs/design/PROMPT_BUILDER_DESIGN.md`.
- **MCP + context project (this repo)**
  - Path: `/Users/neilyashinsky/Documents/Startd8/mcp/startd8-mcp-builder/`
  - Contains:
    - MCP design references under `reference/`.
    - Scripts and evaluation helpers under `scripts/`.
    - This `context/` directory with LLM-facing documentation.

### Relationship Between Startd8, Skills, and MCP

- **Skills and agents**:
  - Startd8 treats skills as structured, named configurations that define how an agent behaves.
  - Skills can be discovered from configuration paths (e.g., via `~/.startd8/config.yaml` in the Cursor integration proposal).
  - Skills may be exposed as **MCP resources** (e.g., `skill://...`) with markdown descriptions.
- **MCP integration (Phase 1)**:
  - The MCP server will:
    - Expose tools for listing and using skills and agents.
    - Surface skills and related configurations as browsable resources.
    - Provide a bridge between Startd8’s internal structures and external tools (Cursor, Anthropic, Antigravity).
  - The overall integration vision and phases are described in:
    - `/Users/neilyashinsky/Documents/FMLs/dev/version2/startd8/CURSOR_INTEGRATION_PROPOSAL.md`

### High-Level Goals of the MCP Integration

- **Short term (Phase 1)**:
  - Build a working MCP server around Startd8 that:
    - Exposes reading and usage of skills, agents, and workflows.
    - Can be connected to Cursor as an MCP server today.
  - Provide structured LLM context so models can:
    - Understand Startd8’s concepts and architecture.
    - Help implement and evolve the MCP server and SDK integration.
- **Longer term**:
  - Enable tighter IDE integrations (e.g., dedicated modes in Cursor).
  - Expand tooling to cover evaluations, workflows, and more advanced orchestration.

### Where to Go Next

- For **SDK structure, modules, and APIs**, see:
  - `context/sdk_and_fmls_v1.md`
- For **evaluations, workflows, and how pipelines are structured**, see:
  - `context/evaluations_and_workflows_v1.md`
- For **MCP-specific plans and design**, see:
  - `context/mcp_integration_plan_v1.md`
- For **definitions of key terms**, see:
  - `context/glossary_v1.md`


