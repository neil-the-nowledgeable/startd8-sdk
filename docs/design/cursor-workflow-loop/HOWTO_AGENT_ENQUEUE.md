# How-To: Enqueue a Workflow Loop Queue (WLQ) Request

**Audience:** Agents (Cursor, Codex, Antigravity, or any VASI-capable surface)
**Status:** Implemented — CLI/API available with WLQ Increments 0–1
**Related:** [VENDOR_AGENT_SURFACE_INTERFACE.md](VENDOR_AGENT_SURFACE_INTERFACE.md) · [CURSOR_WORKFLOW_LOOP_REQUIREMENTS.md](CURSOR_WORKFLOW_LOOP_REQUIREMENTS.md) FR-1 / FR-1a / FR-4

---

## Goal

Create a **pending** job in the Workflow Loop Queue so a later `run-next` / drain can execute it (CRP review, one-shot workflow, etc.).

You are doing **enqueue only**. Do not run the review, do not triage Appendix A/B, and do not invent round numbers.

---

## Preconditions

1. You know which **surface** you are (`cursor`, `codex`, `antigravity`, or custom `surface_id`).
2. Target paths exist and are readable markdown (for CRP).
3. Prefer absolute paths.
4. Queue root (default when implemented): `.startd8/workflow-loop-queue/` under the project.

---

## Quick path (CRP dual-doc, agent-surface)

### 1. Write a job file

Save as something like:

`.startd8/workflow-loop-queue/pending/crp-cwlq-r1_startd8_wloop.json`

```json
{
  "schema_version": "0.1.0",
  "job_id": "crp-cwlq-r1",
  "loop_id": "crp",
  "executor": "agent-surface",
  "surface_id": "cursor",
  "priority": 0,
  "status": "pending",
  "depends_on": [],
  "config": {
    "plan_path": "/ABS/PATH/to/CURSOR_WORKFLOW_LOOP_PLAN.md",
    "requirements_path": "/ABS/PATH/to/CURSOR_WORKFLOW_LOOP_REQUIREMENTS.md",
    "scope": "Dual-document CRP: architecture + requirements gaps for WLQ.",
    "max_rounds": 2,
    "substantially_addressed_threshold": 3,
    "max_suggestions": 10,
    "focus_file": null,
    "agent_template_path": null
  },
  "budget": {
    "max_rounds": 2
  },
  "metadata": {
    "enqueued_by": "agent",
    "surface_id": "cursor",
    "note": "Enqueue-only; drain separately"
  }
}
```

**Set `surface_id` to your vendor** (`codex`, `antigravity`, …). Keep `executor` as `agent-surface` for IDE/agent CRP.

### 2. Submit via CLI

```bash
# From project root, venv active
startd8 wloop enqueue --config .startd8/workflow-loop-queue/pending/crp-cwlq-r1_startd8_wloop.json
```

Expected: exit `0`, job appears as `pending`. Exit `2` = validation fail (fix paths / missing fields).

### 3. Confirm

```bash
startd8 wloop status --job-id crp-cwlq-r1
```

You should see `status: pending`. Stop here unless the user asked you to drain.

---

## Field cheat sheet

| Field | Required | What to put |
|-------|----------|-------------|
| `schema_version` | yes | `"0.1.0"` until WLQ bumps it |
| `job_id` | yes | Stable unique id (`crp-<slug>`, uuid ok) |
| `loop_id` | yes | `"crp"` for Convergent Review; `"one-shot"` for a catalog workflow |
| `executor` | yes | `"agent-surface"` (IDE agent) or `"sdk-workflow"` (API keys / headless) |
| `surface_id` | if agent-surface | `"cursor"` \| `"codex"` \| `"antigravity"` \| custom |
| `workflow_id` | if sdk-workflow / one-shot | e.g. `"plain-language"`, `"architectural-review-log"` |
| `status` | yes on create | Always `"pending"` at enqueue |
| `config` | yes | Loop-specific; for CRP see below |
| `depends_on` | no | Other `job_id`s that must be `completed` first |
| `priority` | no | Higher = sooner (default `0`) |

### CRP `config` (`CrpReviewRequest`)

| Key | Required | Notes |
|-----|----------|-------|
| `plan_path` | dual-doc / plan-only | Absolute `.md` |
| `requirements_path` | dual-doc / requirements-only | Absolute `.md` |
| `scope` | yes | One sentence for the review round metadata |
| `max_rounds` | yes | e.g. `2` |
| `substantially_addressed_threshold` | yes | e.g. `3` |
| `max_suggestions` | yes | e.g. `10` (max 25) |
| `focus_file` | no | Optional sponsor/focus markdown |
| `agent_template_path` | no | Optional `{{slot}}` template override |
| `enable_triage` / `enable_apply` | sdk-workflow only | Usually leave unset for agent-surface |

Dual-doc CRP needs **both** paths. Single-doc: set only the one you are reviewing.

---

## Other common requests

### SDK headless CRP (no IDE agent)

```json
{
  "schema_version": "0.1.0",
  "job_id": "crp-sdk-1",
  "loop_id": "crp",
  "executor": "sdk-workflow",
  "workflow_id": "convergent-review",
  "status": "pending",
  "config": {
    "plan_path": "/ABS/PATH/PLAN.md",
    "requirements_path": "/ABS/PATH/REQUIREMENTS.md",
    "scope": "Headless CRP via convergent-review workflow",
    "max_rounds": 1,
    "substantially_addressed_threshold": 3,
    "max_suggestions": 10,
    "enable_triage": false,
    "enable_apply": false
  }
}
```

Do **not** put a Cursor/CRP prompt bundle into any `review_template` field.

### One-shot catalog workflow

```json
{
  "schema_version": "0.1.0",
  "job_id": "oneshot-plain-1",
  "loop_id": "one-shot",
  "executor": "sdk-workflow",
  "workflow_id": "plain-language",
  "status": "pending",
  "config": {
    "document_path": "/ABS/PATH/doc.md"
  }
}
```

Validate `config` keys against `startd8 workflow describe <workflow_id>` (when available).

### Chained jobs

```json
"depends_on": ["reflective-reqs-1"]
```

Enqueue the dependency first. Drain will skip this job until the dependency is `completed`.

---

## Agent checklist (enqueue)

Copy and tick mentally:

1. [ ] Resolve absolute paths; confirm files exist.
2. [ ] Choose `executor` + `surface_id` (or `workflow_id` for sdk).
3. [ ] Fill CRP `config` or workflow inputs — no phantom fields.
4. [ ] Set `status` to `pending`.
5. [ ] Write `*_startd8_wloop.json` (not `*_startd8_job.json` — that is the old prompt queue).
6. [ ] Run `startd8 wloop enqueue --config …` (or drop into the pending folder if using file-drop mode).
7. [ ] `startd8 wloop status` → confirm `pending`.
8. [ ] Tell the user the `job_id` and that drain is a separate step.

---

## What not to do

| Anti-pattern | Why |
|--------------|-----|
| Use `*_startd8_job.json` / prompt JobQueue | Different system; no `workflow_id` / CRP intent |
| Pass a generated CRP prompt as `review_template` | Breaks SDK `str.format` (`KeyError: 'n'`) |
| Set `status` to `processing` yourself | Only the drain path owns that |
| Triage Appendix A/B during enqueue | Separate `triage` / human step |
| Invent `R{n}` | Derived at drain from the doc |
| Relative paths without project-root resolution | Fail-closed validation |

---

## After enqueue (not part of this how-to)

When the user asks to **run** the job:

```bash
startd8 wloop run-next --job-id crp-cwlq-r1
```

For `agent-surface`, read the Drain Hand-off JSON and execute the rendered bundle (see VASI §5). Then write `drain-result.json`.

---

## Minimal chat reply after enqueue

Keep it short, for example:

> Enqueued `crp-cwlq-r1` (`loop_id=crp`, `executor=agent-surface`, `surface_id=cursor`) — status `pending`. Say when to `run-next`.

---

*How-to for agents · WLQ enqueue · pairs with VASI `enqueue` capability.*
