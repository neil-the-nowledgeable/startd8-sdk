# Vendor Agent Surface Interface (VASI)

**Version:** 0.1.0 (Inc 0.5 contract — aligned with WLQ Requirements v0.5 / FR-21)
**Date:** 2026-07-24
**Status:** Published experimental interface
**Owner:** startd8-sdk (contract) · vendors (adapters)
**Related:** `CURSOR_WORKFLOW_LOOP_REQUIREMENTS.md` §0.5, FR-21, FR-22, NR-9

---

## 1. Purpose

Workflow Loop Queue (WLQ) is vendor-neutral. The SDK owns the queue, schemas,
CLI, CRP renderer, and this interface. **Cursor**, **Codex**, **Antigravity**,
and future agent IDEs implement a thin adapter that maps their UX onto WLQ ops.

This document is the contract those adapters implement. The SDK ships a
**Cursor reference adapter**; it does **not** ship Codex or Antigravity plugins.

---

## 2. Identity

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `surface_id` | string | yes | Stable id: `cursor`, `codex`, `antigravity`, or custom |
| `display_name` | string | yes | Human label |
| `vendor` | string | no | Org / product name |
| `vasi_version` | semver | yes | Must match a published VASI minor (this doc) |
| `capabilities` | string[] | yes | Subset of §3 |

---

## 3. Capabilities

| Capability | Meaning |
|------------|---------|
| `enqueue` | Create a WLQ job (CLI or API) |
| `status` | Read job / queue status |
| `drain` | Run next step for `agent-surface` jobs (consume Drain Hand-off) |
| `cancel` | Cancel a job |
| `triage` | Apply CRP ACCEPT/REJECT → Appendix A/B |
| `render` | Force-render review-template bundle without executing agent |

**CRP agent-surface minimum:** `{status, drain}` plus filesystem write access to
source documents named in the hand-off.

---

## 4. Canonical ops (SDK-owned)

Adapters SHOULD invoke these rather than reimplementing queue logic:

```bash
startd8 wloop enqueue  --config <job.json>
startd8 wloop status   [--job-id <id>]
startd8 wloop run-next [--job-id <id>]   # emits Drain Hand-off for agent-surface
startd8 wloop cancel   --job-id <id>
startd8 wloop triage   --job-id <id> --decisions <file>
startd8 wloop render   --job-id <id>
startd8 wloop list-loops
startd8 wloop list-surfaces
```

Python experimental API (pre-1.0): `startd8.workflows.loop_queue` — same ops.

Exit codes (normative intent): `0` success · `2` validation / fail-closed ·
`3` blocked (retryable) · `1` other error.

---

## 5. Drain Hand-off (machine-readable)

When `run-next` selects an `executor=agent-surface` job, WLQ writes a hand-off
sidecar (and MAY print the same JSON to stdout):

**Path:** `<queue_root>/<job_id>/drain-handoff.json`
**Markdown card (OQ-11):** `<queue_root>/<job_id>/drain-handoff.md` — also exposed as `markdown_card_path` on the JSON hand-off
**JSON Schema:** [`schemas/drain-handoff.schema.json`](schemas/drain-handoff.schema.json)

```json
{
  "vasi_version": "0.1.0",
  "job_id": "…",
  "surface_id": "cursor",
  "loop_id": "crp",
  "round_number": 1,
  "bundle_path": "/abs/path/to/rendered-crp-prompt.md",
  "source_paths": [
    "/abs/path/to/PLAN.md",
    "/abs/path/to/REQUIREMENTS.md"
  ],
  "success_criteria": {
    "append_review_round": true,
    "init_appendix_if_missing": true,
    "no_triage": true,
    "dual_doc_coverage_matrix": true
  },
  "status_writeback_path": "/abs/path/to/<job_id>/drain-result.json",
  "budget_warning": null,
  "markdown_card_path": "/abs/path/to/<job_id>/drain-handoff.md"
}
```

### Agent execution contract (all surfaces)

**Default reviewer (OQ-8):** the current chat/session agent. Surfaces MAY
instead spawn a blind subagent / Task tool; that choice is vendor UX.

1. Open `bundle_path` (agent with filesystem read), or paste the markdown card.
2. For `loop_id=crp`: append `#### Review Round R{n}` under Appendix C on each
   in-scope source path; initialize A/B/C scaffold if absent.
3. Dual-doc CRP: also append Requirements Coverage Matrix to the plan.
4. For `loop_id=reflective-requirements`: write/update the requirements + plan
   paths named in the hand-off (no CRP, no implementation).
5. Do **not** modify populated Appendix A/B on CRP drains; do **not** self-triage.
6. Write `drain-result.json` (below); chat/UI reply is a short confirmation only.

### Status write-back

**Path:** `status_writeback_path` from the hand-off.

```json
{
  "vasi_version": "0.1.0",
  "job_id": "…",
  "surface_id": "cursor",
  "ok": true,
  "round_number": 1,
  "suggestion_counts": { "S": 6, "F": 4 },
  "paths_written": ["/abs/…/PLAN.md", "/abs/…/REQUIREMENTS.md"],
  "error": null
}
```

WLQ marks the job `awaiting_triage` (or next-round `pending`) only after a valid
write-back with `ok: true`. Missing/invalid write-back → `failed` or remain
`processing` per FR-3 interim rules.

---

## 6. Known surfaces

| `surface_id` | Ownership | Status |
|--------------|-----------|--------|
| `cursor` | startd8-sdk reference skill | v1 ship target |
| `codex` | Codex / integrator | External — implement this VASI |
| `antigravity` | Antigravity / integrator | External — implement this VASI |

Custom `surface_id` values are allowed without an SDK release if they conform to
this document.

---

## 7. Non-goals

- SDK does not embed Cursor Automations, Codex plugins, or Antigravity SDKs.
- SDK does not require a closed vendor enum for enqueue.
- Surfaces own their UX (skills, slash commands, panels, schedulers).
- Bundle format is shared; vendor-specific prompt dialects are out of scope
  (use `agent_template_path` + `{{slot}}` if needed).

---

## 8. Conformance checklist (for vendor adapters)

- [ ] Declares `surface_id`, `vasi_version`, capabilities
- [ ] Maps UX actions to §4 ops (or equivalent Python API)
- [ ] On drain: reads `drain-handoff.json`, runs agent per §5
- [ ] Writes valid `drain-result.json`
- [ ] Does not pass rendered bundles into SDK `review_template`
- [ ] CRP: no self-triage into Appendix A/B

---

*VASI 0.1.0 — published with WLQ Inc 0.5. Additive changes may land in 0.1.x; breaking changes require a VASI version bump.*
