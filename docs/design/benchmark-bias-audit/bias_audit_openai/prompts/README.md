# Prompt Template Package

**Version:** 0.1  
**Brief dependency:** `../brief/pricing-task-brief.md`  
**Purpose:** Render equivalent prompts for Codex CLI, Claude Code, and Gemini CLI without leaking
vendor-specific mechanics into the task instructions.

## Templates

- `suite-author.v0.1.md` — generate a behavioral suite from a fixed spec and oracle contract.
- `spec-author.v0.1.md` — generate a benchmark implementation spec from the neutral brief.
- `proto-collection.v0.1.md` — optional secondary contract-shape collection; not used in primary FR-6.
- `self-manifest.schema.json` — required final JSON shape for each authoring run.

## Rendering Rules

Renderers may substitute only these variables:

- `{{RUN_ID}}`
- `{{AUTHORING_SURFACE}}`
- `{{AUTHOR_VENDOR}}`
- `{{MODEL_ID}}`
- `{{PROMPT_TEMPLATE_VERSION}}`
- `{{NEUTRAL_BRIEF}}`
- `{{EXPERIMENT_INSTRUCTIONS}}`
- `{{OUTPUT_CONTRACT}}`
- `{{ALLOWED_DEPENDENCIES}}`
- `{{FORBIDDEN_INPUTS}}`
- `{{RUN_METADATA}}`

Rendered prompts for all authoring tools must be diffed before execution. Differences must be limited
to invocation mechanics and `RUN_METADATA`; task content must remain identical.

## Ambient Instruction Policy

Run authoring from `/private/tmp/startd8-openai-bias-clean-workspace`, not the repository root. Do not
allow tool execution to discover repo-level `CLAUDE.md`, `AGENTS.md`, local MCP config, skills,
plugins, memories, or user rules unless a later sensitivity stratum explicitly records them as inputs.

