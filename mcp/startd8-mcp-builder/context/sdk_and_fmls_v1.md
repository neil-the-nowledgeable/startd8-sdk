## Startd8 SDK and FMLs Overview (v1)

### SDK Structure (High-Level)

The Startd8 SDK lives at:

- `/Users/neilyashinsky/Documents/Startd8/dev/startd8-sdk-project/`

Key high-level docs in that project include:

- `docs/SDK_ARCHITECTURE_v1.md` – overall SDK architecture and major components.
- `docs/API_REFERENCE_v1.md` – reference for public APIs.
- `docs/PIPELINE_WORKFLOWS_v1.md` – how pipeline-style workflows are constructed.
- `docs/FEATURE_WORKFLOW_GUIDE.md` – workflow patterns, with examples.
- Additional design docs under `docs/design/` describing multi-agent chat, document enhancement chains, and related features.

The SDK code is organized around:

- **Agents and skills** – abstractions for specialized LLM behaviors.
- **Pipelines / workflows** – orchestration of multi-step or multi-agent flows.
- **Configuration and runtime** – how projects, jobs, and runs are configured and executed.

For exact package/module layout and public interfaces, consult:

- `/Users/neilyashinsky/Documents/Startd8/dev/startd8-sdk-project/README.md`
- `/Users/neilyashinsky/Documents/Startd8/dev/startd8-sdk-project/IMPLEMENTATION_PLAN.md`
- The `src/` or primary package directories in the SDK project.

### FMLs and Configuration Artifacts

Startd8 uses domain-specific configuration artifacts (often referred to informally here as **FMLs**) to describe:

- **Skills and agents** (system prompts, capabilities, metadata).
- **Workflows and pipelines** (how steps and agents are wired together).
- **Evaluations and jobs** (what to run, with which inputs and expectations).

Notes for this v1 context:

- The **exact file formats and locations** of FMLs/configs will depend on the current SDK code and project conventions.
- As of v1, this document intentionally stays **format-agnostic**, and should be updated with concrete examples and paths as the MCP server and SDK integration are implemented.

Recommended actions when working with FMLs/configs:

- When in doubt, search within the SDK project for configuration examples:
  - Look for directories such as `configs/`, `skills/`, `jobs/`, or `job_files/`.
  - There are existing examples, such as:
    - `/Users/neilyashinsky/Documents/Startd8/dev/startd8-sdk-project/job_files/flower-defense-v2/README.md`
- Use the SDK’s existing docs and examples to infer:
  - How skills are defined.
  - How workflows and evaluations are configured.

### How the MCP Server Should Interact with SDK and FMLs (Phase 1)

In Phase 1 of the MCP integration:

- The MCP server should be able to:
  - **Discover** available skills and configurations (e.g., via config paths or discovery rules).
  - **List** and **describe** these artifacts in a way that is meaningful to LLM agents.
  - **Expose tools** to:
    - List skills / agents.
    - Use a skill to generate a response for a given prompt.
    - Potentially compare agents on a given input.
- Over time, the MCP server may also:
  - Read and update FML/config documents.
  - Scaffold new skills, workflows, or evaluations from high-level descriptions.

### Key SDK Docs to Consult When Implementing MCP Tools

When designing or implementing MCP tools that interact with the SDK, consult:

- `docs/SDK_ARCHITECTURE_v1.md` – to understand the main components and how they should be used.
- `docs/API_REFERENCE_v1.md` – to see which APIs are stable and intended for external use.
- `docs/FEATURE_WORKFLOW_GUIDE.md` and `docs/PIPELINE_WORKFLOWS_v1.md` – to see how workflows and pipelines are modeled.
- `QUICK_REFERENCE.md` and `IMPLEMENTATION_PLAN.md` – for summarized behavior and planned work.

### Future Refinements for This Document

As the MCP server and SDK evolve, this file should be updated to:

- Include **concrete examples** of FML/config files (paths, snippets, and conventions).
- Document **exact discovery rules** for locating skills and workflows (e.g., environment variables, config files).
- Describe any **public CLI or Python APIs** that the MCP server will rely on for listing/using skills and running workflows.


