# WLQ packaged prompts

Markdown here is the **default drain / hand-off config** for `startd8 wloop` agent-surface jobs.

| File | Loop |
|------|------|
| `reflective-requirements.md` | `reflective-requirements` (thin wrapper — follow the Claude skill) |
| `research.md` | `research` |
| `drain-handoff*.md` | All agent-surface hand-off cards |
| `crp-memory-preamble.md` | Prepended to CRP bundles |

Resolution: `prompt_loader.py` — env overrides in `PROMPT_ENV`, then these files.
Procedure skills remain under `~/.claude/skills/` (see ContextCore `docs/plans/PROMPT_CONFIG_INDEX.md`).
