# S2 Codex Proto Collection Run

**Run ID:** `s2-codex-proto-clean-20260618T205742Z`  
**Date:** 2026-06-18  
**Authoring surface:** Codex CLI  
**Canonical status:** Canonical initial S2 proto-collection pass  

## Invocation

The run was executed from the clean workspace with the app-bundled Codex binary and plugins disabled:

```bash
/Applications/Codex.app/Contents/Resources/codex --disable plugins exec --json --ephemeral \
  --ignore-user-config --ignore-rules --skip-git-repo-check \
  --sandbox workspace-write \
  --cd /private/tmp/startd8-openai-bias-clean-workspace/outputs/s2-codex-proto-clean-20260618T205742Z \
  --output-last-message codex_last_message.txt \
  - < rendered_prompt.md
```

The earlier exploratory run at `/private/tmp/startd8-openai-bias-clean-workspace/outputs/s2-codex-proto-20260618T205033Z`
loaded user plugin metadata despite `--ignore-user-config --ignore-rules`, so it is not the canonical
audit record.

## Outputs

- `pricing_candidate.proto`
- `contract_rationale.md`
- `authoring_manifest.json`
- `rendered_prompt.md`
- `codex_last_message.txt`

## Validation

- `authoring_manifest.json` validates against `self-manifest.schema.json`.
- `pricing_candidate.proto` compiles with `protoc`.
- Forbidden current-seed contract names did not appear in the generated proto, rationale, or manifest.
