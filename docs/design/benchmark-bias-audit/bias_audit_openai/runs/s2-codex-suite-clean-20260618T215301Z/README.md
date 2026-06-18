# S2 Codex Suite Author Run

**Run ID:** `s2-codex-suite-clean-20260618T215301Z`  
**Date:** 2026-06-18  
**Authoring surface:** Codex CLI  
**Canonical status:** Canonical initial S2 suite-author pass  

## Invocation

The run was executed from the clean workspace with the app-bundled Codex binary and plugins disabled:

```bash
/Applications/Codex.app/Contents/Resources/codex --disable plugins exec --json --ephemeral \
  --ignore-user-config --ignore-rules --skip-git-repo-check \
  --sandbox workspace-write \
  --cd /private/tmp/startd8-openai-bias-clean-workspace/outputs/s2-codex-suite-clean-20260618T215301Z \
  --output-last-message codex_last_message.txt \
  - < rendered_prompt.md
```

The canonical proto and canonical prose specification were embedded in the rendered prompt and copied
under `inputs/`.

## Outputs

- `suite.py`
- `suite_manifest.json`
- `authoring_manifest.json`
- `rendered_prompt.md`
- `codex_last_message.txt`

## Validation

- `suite.py` compiles with `py_compile`.
- Suite self-checks passed: 9 valid fixtures and 15 invalid fixtures.
- `authoring_manifest.json` validates against `self-manifest.schema.json`.
- `suite_manifest.json` parses as JSON.
- Forbidden current-seed contract names did not appear in the generated suite or manifests.

## Scope Note

The suite is behavioral and does not cover `FIXED-009` benchmark seed-envelope packaging. That remains
a later packaging task.
