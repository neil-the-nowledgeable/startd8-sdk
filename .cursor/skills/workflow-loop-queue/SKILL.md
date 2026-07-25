---
name: workflow-loop-queue
description: Enqueues, drains, checks, cancels, and triages startd8 Workflow Loop Queue jobs through the VASI contract. Use when the user asks to run a queued CRP review, enqueue a workflow loop, reflective-requirements via wloop, inspect wloop status, or process a drain hand-off in Cursor.
---

# Workflow Loop Queue

Use the SDK-owned `startd8 wloop` commands. Do not reimplement queue state.
The VASI contract is
`docs/design/cursor-workflow-loop/VENDOR_AGENT_SURFACE_INTERFACE.md`.

**Defaults (settled OQs):** current chat agent executes drains (not a blind
subagent unless the user asks); CLI is canonical (do not require MCP); queue
root is `.startd8/workflow-loop-queue/`.

## Enqueue CRP

1. Resolve the plan and/or requirements paths to absolute `.md` paths.
2. Write a job envelope following
   `docs/design/cursor-workflow-loop/HOWTO_AGENT_ENQUEUE.md` with:
   - `loop_id: "crp"`
   - `executor: "agent-surface"`
   - `surface_id: "cursor"`
   - `status: "pending"`
   - a complete `CrpReviewRequest` under `config`
3. Run:

```bash
startd8 wloop enqueue --config <job-envelope.json>
startd8 wloop status --job-id <job-id>
```

Stop after status unless the user also requested drain.

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
3. Open `bundle_path` and follow it with filesystem write tools in **this**
   chat (default). Only spawn a blind subagent if the user explicitly wants
   isolation.
4. CRP: append Appendix C only; no A/B triage. Reflective: write the named
   requirements + plan files; no CRP/implementation.
5. Write `drain-result.json` to `status_writeback_path`.
6. Run `startd8 wloop run-next --job-id <job-id>` again to verify.
7. Reply with job id, paths, counts/status only.

## Triage (CRP)

Only when explicitly requested:

```bash
startd8 wloop triage --job-id <job-id> --decisions <decisions.json>
```

## Other operations

```bash
startd8 wloop status [--job-id <job-id>]
startd8 wloop render --job-id <job-id>
startd8 wloop cancel --job-id <job-id>
startd8 wloop requeue --job-id <job-id>
startd8 wloop list-loops
startd8 wloop list-surfaces
```

Stuck `processing` jobs reclaim automatically after the lease TTL (default 1h),
or use `requeue`. Exit `2` = validation; exit `3` = blocked.
