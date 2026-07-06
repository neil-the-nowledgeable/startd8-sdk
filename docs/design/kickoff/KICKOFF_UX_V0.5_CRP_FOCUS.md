# CRP Focus — Kickoff UX v0.5 (Output Hygiene & Orientation)

**Weight the review on the v0.5 additions only** — §3E (FR-UX-13, FR-UX-14, FR-UX-15, FR-UX-16) and the
new principle UX-P6 in `KICKOFF_UX_REQUIREMENTS.md`, plus the matching **"v0.5 Increment — Output Hygiene &
Orientation"** section in `KICKOFF_UX_PLAN.md` (Steps 7–10, v0.5 planning discoveries, Risks R4–R7, and the
v0.5 coverage matrix). FR-UX-1..12 and plan Steps 1–6 are already CRP-hardened (v0.4); do **not** re-litigate
them except where a v0.5 requirement/step interacts with them. Judge the v0.5 requirements **and** their
plan steps for implementability against the code facts below.

## Context the reviewer must hold

- The trigger was real terminal noise: lines like `2026-07-06 11:54:57 - startd8.concierge.core - INFO -
  concierge.survey root=/…` printed to the user during kickoff.
- **Root cause (code-grounded):** `get_logger()` → `_ensure_default_log_file_handler()` attaches a console
  `StreamHandler(sys.stderr)` at **INFO** to the root `startd8` logger (`src/startd8/logging_config.py`
  lines ~229-238), with formatter `'%(asctime)s - %(name)s - %(levelname)s - %(message)s'` (~lines 125-127,
  233-236). This is **global** — every SDK `logger.info(...)` prints on *any* command (e.g.
  `src/startd8/concierge/core.py:244`).
- `STARTD8_LOG_LEVEL` env already gates console level (~lines 20, 230, 242).
- Locked sponsor decisions (do not re-open): (1) suppression is **CLI-wide** quiet-by-default, not
  kickoff-local; (2) the debug toggle is **`--debug` flag AND env var**; (3) the banner shows on **every**
  kickoff invocation.

## Sponsor focus asks (answer each in the 4-line template)

1. **FR-UX-13 blast radius vs. the doc's home.** FR-UX-13/14 are a **CLI-wide** logging-layer change, but
   they live in a *kickoff* UX doc. Is that placement safe, or does it risk a CLI-wide behavior change that
   other commands' owners won't see? Should there be a pointer/companion requirement at the CLI-logging
   layer, and how do we guarantee the change is applied once (not per-command)?

2. **Mechanism correctness of quiet-by-default.** Given `get_logger()` unconditionally attaches an INFO
   console handler at import/first-use (before argv is parsed), is "console default = WARNING, `--debug`
   raises it" actually achievable at the right point in the CLI lifecycle? Identify the concrete seam
   (Typer root callback? a `configure_cli_logging()` before command dispatch?) and any ordering hazard where
   `logger.info` fires *before* the level is lowered. Does `--debug` (parsed per-command) come too late to
   catch early import-time logs?

3. **Interaction with existing axes (`--verbose`/`--json`/`--check`) and NR-6/7.** Does keeping `--debug`
   and `--verbose` as separate axes hold up end-to-end? Any surface where the quiet default would swallow
   something a user or CI (`--check`, `red_carpet_advisor` error advisories) must see, contradicting the
   FR-UX-5 error exception or NR-7?

4. **Testability of FR-UX-15/16.** Are "every element carries a plain-language what+why" (FR-UX-15) and the
   "≤ ~6 lines, no-jargon, `--json`-suppressed banner" (FR-UX-16) specified tightly enough to write a
   snapshot/assert against, or do they need concrete acceptance anchors (which elements, which why-strings,
   exact banner source and line budget)? Does FR-UX-16's per-invocation banner risk re-creating the
   FR-UX-4 information-overload it's meant to avoid?

## Out of scope

- Backend/generation mechanism, grammar, write paths (NR-1).
- Re-review of FR-UX-1..12 dispositions already in Appendix A.
