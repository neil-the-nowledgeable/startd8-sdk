## Evaluations and Workflows in Startd8 (v1)

### Conceptual Overview

Startd8 supports building and running **workflows** (pipelines of agents and steps) and then **evaluating** those workflows and agents.

- **Workflows**:
  - Define a sequence or graph of steps, each potentially using different skills/agents.
  - Can be used for complex tasks (e.g., multi-step document enhancement or multi-agent chat).
- **Evaluations**:
  - Compare agents or workflows on specific inputs or tasks.
  - Support measuring performance, quality, or other metrics across runs.

These concepts are described across several SDK documents, including (paths on disk):

- `/Users/neilyashinsky/Documents/Startd8/dev/startd8-sdk-project/docs/PIPELINE_WORKFLOWS_v1.md`
- `/Users/neilyashinsky/Documents/Startd8/dev/startd8-sdk-project/docs/FEATURE_WORKFLOW_GUIDE.md`
- `/Users/neilyashinsky/Documents/Startd8/dev/startd8-sdk-project/docs/design/DOCUMENT_ENHANCEMENT_CHAIN.md`
- `/Users/neilyashinsky/Documents/Startd8/dev/startd8-sdk-project/docs/design/DOCUMENT_ENHANCEMENT_CHAIN_IMPLEMENTATION.md`
- `/Users/neilyashinsky/Documents/Startd8/dev/startd8-sdk-project/docs/design/DOCUMENT_ENHANCEMENT_CHAIN_COMPLETE.md`

### Workflows and Pipelines

From the available docs and design files, workflows in Startd8 typically:

- Use **named features or pipelines** to capture multi-step processing.
- May chain multiple agents or transformations (e.g., document enhancement chains).
- Can be configured via configuration files, SDK APIs, or both.

Important references:

- `docs/PIPELINE_WORKFLOWS_v1.md` – overall pipeline and workflow patterns.
- `docs/FEATURE_WORKFLOW_GUIDE.md` – detailed guidance on defining and using feature workflows.
- `docs/design/*MULTI_AGENT*` – design for multi-agent chat and review workflows.

### Evaluations and Comparison

Evaluations are used to:

- Compare responses from different agents/skills.
- Validate that changes to prompts, workflows, or code do not regress behavior.
- Provide structured feedback loops for iterative improvement.

Relevant materials include:

- Evaluations and scoring documents under:
  - `/Users/neilyashinsky/Documents/Startd8/score/Startdate Framework eval.md`
- Bugfix and change summaries that show how evaluations inform development:
  - `docs/BUGFIX_DATETIME_STORAGE.md`
  - `BUGFIX_SUMMARY.md`
  - `FIXES_APPLIED.md`

The exact evaluation configuration formats and APIs will be clarified as the MCP integration is implemented; this v1 document intentionally does not hard-code those details.

### How the MCP Server Should Support Evaluations and Workflows (Phase 1)

In Phase 1 of the MCP integration, the MCP server should focus on:

- **Discovery and inspection**:
  - List defined workflows and evaluation specs.
  - Provide human-readable descriptions or summaries for them.
- **Read-oriented tools**:
  - Fetch and return evaluation configuration documents.
  - Fetch and return workflow definitions or key files.
- **Optional early scaffolding** (if desired by the user):
  - Propose new evaluation specs or workflow definitions based on high-level descriptions.
  - Write these as draft configuration files that can be reviewed and refined.

Running full evaluations or pipelines via MCP tools can be added incrementally:

- Initially, the MCP server might:
  - Trigger SDK-level evaluation commands or scripts.
  - Provide status and high-level result summaries.

### Key Questions to Refine in Future Versions

This v1 document intentionally leaves some implementation details open, to be filled in as the MCP and SDK integration work progresses:

- Where are evaluation specifications stored by default (paths, formats)?
- How are workflows and pipelines declared (configuration vs. code vs. both)?
- What are the stable SDK APIs or CLIs for:
  - Listing workflows and evaluations.
  - Running evaluations.
  - Accessing evaluation results and metrics.

As these questions are answered in code and practice, this file should be updated (or replaced with a `_v2` version) to include:

- Concrete examples of evaluation and workflow configuration files.
- Exact tool signatures for MCP-based interactions with evaluations and workflows.


