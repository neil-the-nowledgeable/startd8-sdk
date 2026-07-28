---
name: workflow-loop-queue
description: Enqueues, drains, checks, cancels, and triages startd8 Workflow Loop Queue jobs through the VASI contract. Use when the user asks to run a queued CRP review, enqueue a workflow loop, reflective-requirements via wloop, inspect wloop status, or process a drain hand-off in Cursor.
---

# Workflow Loop Queue

Use the SDK-owned `startd8 wloop` commands. Do not reimplement queue state.
The VASI contract is
`docs/design/cursor-workflow-loop/VENDOR_AGENT_SURFACE_INTERFACE.md`.

**Defaults (settled OQs):** CLI is canonical (do not require MCP); queue root is
`.startd8/workflow-loop-queue/`. Reviewer default is the current chat agent
unless the drain hand-off sets `assigned_reviewer.mode=blind_rotate`.

## Enqueue CRP

1. Resolve the plan and/or requirements paths to absolute `.md` paths in the
   **consumer** project that owns those docs (not WLQ design docs by default).
2. Resolve the **loop-owning** queue root (usually the SDK repo). Pass
   `--root /ABS/.../startd8-sdk/.startd8/workflow-loop-queue` or set
   `$STARTD8_WLOOP_ROOT`. Do **not** enqueue from the doc-repo CWD without an
   explicit root — that creates an orphan queue (FR-24).
3. Write a job envelope following
   `docs/design/cursor-workflow-loop/HOWTO_AGENT_ENQUEUE.md` with:
   - `loop_id: "crp"`
   - `executor: "agent-surface"`
   - `surface_id: "cursor"`
   - `status: "pending"`
   - a complete `CrpReviewRequest` under `config`
4. For cross-vendor robustness, set either:
   - `reviewer_tier: "flagship"` or `"mid_tier"` (Anthropic+OpenAI+Google presets), or
   - `reviewer_mode: "blind_rotate"` + explicit `reviewer_roster` of Cursor Task
     model slugs (R1→roster[0], R2→roster[1], …).
   Also set `max_rounds` (e.g. `3` with flagship).
5. Run:

```bash
startd8 wloop enqueue --config <job-envelope.json> --root <loop-owning-queue-root>
startd8 wloop status --job-id <job-id> --root <loop-owning-queue-root>
```

Confirm via `wloop status` (jobs live under `jobs/`, not `pending/`). Stop after
status unless the user also requested drain.

## Enqueue reflective-requirements

When the user wants the reflective-requirements loop queued (not only the
skill ad hoc):

```json
{
  "job_id": "refl-feature-x",
  "loop_id": "reflective-requirements",
  "executor": "agent-surface",
  "surface_id": "cursor",
  "status": "pending",
  "config": {
    "scope": "Feature X",
    "requirements_path": "/ABS/PATH/REQUIREMENTS.md",
    "plan_path": "/ABS/PATH/PLAN.md"
  }
}
```

Parent directories must exist. Follow-on CRP should be a separate job with
`depends_on: ["refl-feature-x"]`.

## Drain (CRP or reflective-requirements)

1. Run `startd8 wloop run-next --job-id <job-id>`.
2. Read the Drain Hand-off JSON (and optionally `markdown_card_path`).
3. **If `assigned_reviewer.mode == "blind_rotate"`:**
   - Spawn a Task/subagent with `model` = `assigned_reviewer.model`.
   - Pass `bundle_path` and `status_writeback_path`; the Task appends CRP /
     writes docs. **Do not** review in the current chat.
   - Task must write a valid VASI `DrainResult` to `status_writeback_path`
     (`vasi_version`, `job_id`, `surface_id`, `ok`, `round_number`,
     `suggestion_counts`, `paths_written`, `reviewer_model` = exact assigned
     slug). Do **not** use `schema_version` — that field fails closed.
   - Current chat only orchestrates and runs the verify `run-next`.
   - **Scope the reviewer tightly:** instruct it to read only the bundle, the
     focus file, and the source docs — no repo-wide greps or exploration — and
     state that persisting the Appendix C append is mandatory. Unscoped
     reviewers have burned 90+ minutes writing nothing.
4. **Else (`current`):** open `bundle_path` and follow it in this chat.
5. CRP: append Appendix C only; no A/B triage. WLQ already ensured the A/B/C
   scaffold (like `new-cnvrg-rvw-prmpt`) — do **not** initialize it. Reflective:
   write the named requirements + plan files; no CRP/implementation.
6. Write `drain-result.json` to `status_writeback_path`.
7. Run `startd8 wloop run-next --job-id <job-id>` again to verify.
8. If status is `pending`, more review rounds remain — repeat drain (do **not**
   triage yet). If status is `completed`, the loop finished (default
   `triage_policy=auto_accept` auto-triaged after the last round). If status is
   `awaiting_triage`, the job used `triage_policy=manual` — run batch triage.
9. Reply with job id, paths, counts/status only.

## Triage (CRP)

**Default:** after all review rounds, WLQ **auto-ACCEPTS** untriaged Appendix C
ids into Appendix A and marks the job `completed` — no separate triage call.

Only when the job was enqueued with `triage_policy: "manual"` (status
`awaiting_triage`):

```bash
startd8 wloop triage --job-id <job-id> --decisions <decisions.json>
```

Do not triage between rounds.

## Other operations

```bash
startd8 wloop status [--job-id <job-id>]
startd8 wloop render --job-id <job-id>
startd8 wloop cancel --job-id <job-id>
startd8 wloop requeue --job-id <job-id>
startd8 wloop list-loops
startd8 wloop list-reviewer-tiers
startd8 wloop list-surfaces
```

Stuck `processing` jobs reclaim automatically after the lease TTL (default 1h),
or use `requeue`. Exit `2` = validation; exit `3` = blocked.

Source docs must live in a real git worktree on a **named branch** — `/tmp`
paths or a detached HEAD get the job `blocked` at render. Use
`git worktree add <path> <branch>` first if needed.

## Building a new loop for another project

When the user asks for a durable agent loop in a *different* project (not just
one enqueue), read
`docs/design/cursor-workflow-loop/HOWTO_BUILD_A_LOOP.md`. It covers choosing vs.
composing recipes, `depends_on` chaining, the per-round drain loop, multi-vendor
rotation, deferred triage, and the known traps. Default to composing the
existing `crp` / `reflective-requirements` / `one-shot` recipes with zero SDK
code changes.
