## Startd8 Glossary (v1)

### Core Entities

- **Startd8**  
  A software development kit (SDK) and framework for building, configuring, and running skill-based LLM agents and multi-step workflows, with support for prompt versioning, evaluation, and job management.

- **StartDate OSS / StartDate SDK**  
  The broader open-source framing and earlier materials that describe the conceptual foundation and evolution of Startd8, located under `/Users/neilyashinsky/Documents/biz/incubator/StartDateOSS/`.

- **Startd8 SDK project**  
  The main SDK implementation, documentation, and examples, located at `/Users/neilyashinsky/Documents/Startd8/dev/startd8-sdk-project/`. Contains the core code, architecture docs, API references, and workflow guides.

- **MCP project / startd8-mcp-builder**  
  This repository, located at `/Users/neilyashinsky/Documents/Startd8/mcp/startd8-mcp-builder/`, focused on implementing a Model Context Protocol (MCP) server for Startd8 and housing LLM-facing context documents.

### Agents, Skills, and Configurations

- **Agent**  
  A configured LLM “persona” or capability in Startd8, typically defined by a combination of system prompts, settings, and behavior rules, often realized via a reusable skill.

- **Skill**  
  A named, reusable configuration that encapsulates an agent’s behavior (system prompt, capabilities, and metadata). Skills are discoverable artifacts that can be listed and invoked (e.g., via MCP tools like `list_skills` and `use_skill`), and may be exposed as MCP resources (e.g., `skill://<name>`).

- **Prompt versioning**  
  The practice and tooling for tracking changes to prompts (especially system prompts and key instructions) over time, so that Startd8 users can evolve agents and skills while maintaining history and comparability.

- **FMLs / configuration artifacts**  
  A shorthand here for Startd8’s domain-specific configuration formats (exact file names/formats may vary) that describe skills, workflows, evaluations, and/or projects. This term is intentionally format-agnostic in v1; future versions should document concrete formats and locations once they are fixed.

### Workflows, Evaluations, and Jobs

- **Workflow / pipeline**  
  A multi-step or multi-agent process defined within Startd8, often described in pipeline terms (e.g., “document enhancement chain” or multi-agent chat flows). Workflows typically route data through several agents or transformations.

- **Evaluation**  
  A structured process that runs agents or workflows on specified inputs to compare responses, measure performance or quality, and validate behavior changes. Evaluations may be defined via configuration files and executed using SDK or CLI tooling.

- **Job / run**  
  A concrete execution of a workflow, evaluation, or batch of tasks in Startd8. Jobs may be queued, tracked, and stored for later inspection.

- **Job queue / batch processing**  
  Facilities in Startd8 for enqueuing many jobs and processing them asynchronously or in bulk, often used for large evaluations or batch tasks.

### MCP and Tooling

- **MCP (Model Context Protocol)**  
  A protocol for exposing tools and resources to LLMs in a standardized way. MCP servers register tools (functions that can be called) and resources (browsable/readable data) that clients like Cursor can use during conversations.

- **MCP server (Startd8 MCP server)**  
  A server process that implements MCP for Startd8. It exposes Startd8 capabilities (e.g., listing and using skills, comparing agents) as MCP tools and surfaces Startd8 artifacts (e.g., skill definitions) as MCP resources.

- **Tool (MCP tool)**  
  A callable operation exposed by the MCP server (for example, `list_skills`, `use_skill`, or `compare_agents`). Tools have names, descriptions, and parameter schemas that LLMs use to decide when and how to call them.

- **Resource (MCP resource)**  
  A piece of data that the MCP server exposes for browsing or reading (for example, a skill definition or configuration file), typically addressed via a URI such as `skill://...`.

### IDE and Integration Concepts

- **Cursor**  
  An AI-assisted IDE that supports multiple interaction modes (Agent, Ask, Plan) and can connect to MCP servers. Startd8 aims to integrate with Cursor first via MCP, and possibly later as a dedicated “Skills” mode.

- **Skills mode (proposed)**  
  A conceptual Cursor mode described in the integration proposal, where users select from Startd8 skills and use them directly within Cursor’s chat interface. Not yet a built-in Cursor feature; the current practical integration path is via MCP.

- **Anthropic context docs**  
  LLM-facing documentation tailored to Anthropic models (e.g., `anthropic_context_v1.md`), summarizing Startd8, the MCP project, and how Anthropic should behave when working with this codebase.

- **Antigravity context docs**  
  LLM-facing documentation tailored to Google Antigravity models (e.g., `antigravity_context_v1.md`), with a more reference-style orientation but sharing the same conceptual foundation.

- **Cursor context docs**  
  LLM-facing documentation and (eventually) configuration tailored to Cursor (e.g., `cursor_context_v1.md`), explaining how Cursor should use this MCP project and its context when assisting with Startd8.

### Versioning of Context Docs

- **`*_v1.md` files**  
  The initial, editable versions of context documents in this MCP project. These are intended to be reviewed, refined, and either updated in place or superseded by `_v2`, `_v3`, etc. as the code and design evolve.

- **Future versions**  
  When making major conceptual or structural changes, prefer creating a new `_vN` file (e.g., `startd8_overview_v2.md`) and clearly indicating which version is currently authoritative.


