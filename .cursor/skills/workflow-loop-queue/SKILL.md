---
name: workflow-loop-queue
description: Enqueues, drains, checks, cancels, and triages startd8 Workflow Loop Queue jobs through the VASI contract. Use when the user asks to run a queued CRP review, enqueue a workflow loop, inspect wloop status, or process a drain hand-off in Cursor.
---

# Workflow Loop Queue

Use the SDK-owned `startd8 wloop` commands. Do not reimplement queue state.
The VASI contract is
`docs/design/cursor-workflow-loop/VENDOR_AGENT_SURFACE_INTERFACE.md`.

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

## Drain a CRP round

1. Run `startd8 wloop run-next --job-id <job-id>`.
2. Parse the returned Drain Hand-off JSON. Do not invent a round number or
   source path.
3. Read the entire file at `bundle_path`.
4. Follow that bundle using filesystem read/write tools:
   - append exactly the requested `#### Review Round R<n>` under Appendix C;
   - initialize the A/B/C scaffold only when absent;
   - in dual-doc mode, write S-prefix suggestions to the plan, F-prefix
     suggestions to requirements, and append the coverage matrix to the plan;
   - never modify populated Appendix A/B and never self-triage;
   - preserve every prior Appendix C round.
5. Verify every source path contains the hand-off round and count S/F
   suggestions.
6. Write JSON to the exact `status_writeback_path`:

```json
{
  "vasi_version": "0.1.0",
  "job_id": "<from hand-off>",
  "surface_id": "cursor",
  "ok": true,
  "round_number": 1,
  "suggestion_counts": {"S": 0, "F": 0},
  "paths_written": ["<all absolute source_paths, exactly>"],
  "error": null
}
```

7. Run `startd8 wloop run-next --job-id <job-id>` again. Success means status
   becomes `awaiting_triage`. If verification failed, write `ok: false` with
   `error` and do not claim success.
8. Reply with only the job id, round, paths written, counts, and resulting
   status. Do not repeat suggestion content in chat.

## Triage

Only triage when explicitly requested. Prepare a JSON list of decisions with
`id`, `decision` (`ACCEPT` or `REJECT`), `summary`, `rationale`, and optional
`source`, then run:

```bash
startd8 wloop triage --job-id <job-id> --decisions <decisions.json>
```

Triage records ACCEPT in Appendix A and REJECT in Appendix B. It must never
delete or rewrite Appendix C. The queue returns `pending` when another round
remains, otherwise `completed`.

## Other operations

```bash
startd8 wloop status [--job-id <job-id>]
startd8 wloop render --job-id <job-id>
startd8 wloop cancel --job-id <job-id>
startd8 wloop requeue --job-id <job-id>
startd8 wloop list-loops
startd8 wloop list-surfaces
```

Exit `2` means validation failed. Exit `3` means retryable `blocked`; restore
the named artifact, then use `requeue`. Do not pass an agent bundle to the SDK
`review_template` field.
