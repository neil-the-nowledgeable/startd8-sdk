# Clean Authoring Workspace Manifest

**Workspace path:** `/private/tmp/startd8-openai-bias-clean-workspace`  
**Reason:** avoid ambient instruction leakage from the startd8 repository root, especially
`/Users/neilyashinsky/Documents/dev/startd8-sdk/CLAUDE.md`.

## Policy

Authoring tools must run with their working directory inside the clean workspace, not under the
startd8 git root. The workspace contains only:

- `inputs/neutral_brief.md`
- `inputs/source_to_brief_traceability.md`
- `inputs/source_bibliography.md`
- `inputs/leakage_review_checklist.md`
- `inputs/s2_scope_decisions.md`
- `inputs/canonical_pricing.proto`
- `inputs/canonical_spec.md`
- `inputs/canonicalization_decisions.md`
- `prompts/*.md`
- `prompts/self-manifest.schema.json`
- `outputs/`
- `MANIFEST.md`

The workspace intentionally excludes:

- `CLAUDE.md`
- `AGENTS.md`
- `AGENTS.override.md`
- Codex config, rules, skills, plugins, MCP configuration, and memories
- Gemini-specific ambient configuration
- current `pricing.proto`
- current `requirements_text`
- current `pricing_suite.py`

## Invocation Rule

Use an explicit binary path and explicit working directory. For Codex CLI, prefer the app-bundled
binary until the npm shim is repaired:

```bash
/Applications/Codex.app/Contents/Resources/codex exec --json --ephemeral \
  --ignore-user-config --ignore-rules \
  --sandbox workspace-write \
  --cd /private/tmp/startd8-openai-bias-clean-workspace \
  "<rendered prompt>"
```

Record the exact binary path, version, model, auth mode, sandbox mode, and prompt-template version in
the run manifest.
