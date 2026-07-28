# How-To: Enqueue a Workflow Loop Queue (WLQ) Request

**Audience:** Agents (Cursor, Codex, Antigravity, or any VASI-capable surface)
**Status:** Implemented — CLI/API available with WLQ Increments 0–1
**Related:** [VENDOR_AGENT_SURFACE_INTERFACE.md](VENDOR_AGENT_SURFACE_INTERFACE.md) · [CURSOR_WORKFLOW_LOOP_REQUIREMENTS.md](CURSOR_WORKFLOW_LOOP_REQUIREMENTS.md) FR-1 / FR-1a / FR-4 / FR-24 / FR-25 / FR-26
**Field notes:** [AGENT_FIELD_NOTES_WLQ_ENQUEUE.md](AGENT_FIELD_NOTES_WLQ_ENQUEUE.md)

---

## Goal

Create a **pending** job in the Workflow Loop Queue so a later `run-next` / drain can execute it (CRP review, reflective-requirements, one-shot workflow, etc.).

You are doing **enqueue only**. Do not run the review, do not triage Appendix A/B, and do not invent round numbers.

---

## Preconditions

1. You know which **surface** you are (`cursor`, `codex`, `antigravity`, or custom `surface_id`).
2. Target **plan / requirements** paths exist and are readable markdown (for CRP). Use the documents under review in **their** project folder — not WLQ’s own design docs unless you are literally reviewing WLQ.
3. Prefer **absolute** paths for every document path in `config`.
4. **Queue root ≠ document root (FR-24).**
   - `plan_path` / `requirements_path` → absolute paths into the **consumer** project that owns those docs (e.g. ContextCore, a product repo).
   - `--root` → the **loop-owning** queue (usually the SDK / tooling repo):  
     `/ABS/PATH/startd8-sdk/.startd8/workflow-loop-queue`
   - Default `--root` is `.startd8/workflow-loop-queue` **relative to CWD**. If you enqueue from the doc repo, you create an orphan queue nobody drains. **Always pass an absolute `--root`** when CWD is not the loop-owning project, or set `$STARTD8_WLOOP_ROOT`.
5. Confirm with `startd8 wloop status`, **not** by listing folders (FR-25).

---

## Quick path (CRP dual-doc, agent-surface)

### 1. Write a job envelope (anywhere)

Draft the JSON **anywhere** convenient (temp file, chat workspace, or a local staging folder). CLI enqueue does **not** require `pending/`.

```json
{
  "schema_version": "0.1.0",
  "job_id": "crp-coverage-driven-rca-1",
  "loop_id": "crp",
  "executor": "agent-surface",
  "surface_id": "cursor",
  "priority": 0,
  "status": "pending",
  "depends_on": [],
  "config": {
    "plan_path": "/ABS/PATH/to/YOUR_PROJECT/docs/plans/FEATURE_PLAN.md",
    "requirements_path": "/ABS/PATH/to/YOUR_PROJECT/docs/design/requirements/REQ_FEATURE.md",
    "scope": "Dual-document CRP for Feature X — focus the sponsor's open risks.",
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

Replace the two paths with **that project's** real plan and requirements files. Optional `focus_file` is likewise absolute into the consumer tree.

**Set `surface_id` to your vendor** (`codex`, `antigravity`, …). Keep `executor` as `agent-surface` for IDE/agent CRP.

### 2. Submit via CLI (recommended)

```bash
# Loop-owning root = where drains run (usually startd8-sdk), NOT the doc repo CWD
startd8 wloop enqueue \
  --config /ABS/PATH/to/crp-coverage-driven-rca-1_startd8_wloop.json \
  --root /ABS/PATH/startd8-sdk/.startd8/workflow-loop-queue
```

Or export once per shell:

```bash
export STARTD8_WLOOP_ROOT=/ABS/PATH/startd8-sdk/.startd8/workflow-loop-queue
startd8 wloop enqueue --config /ABS/PATH/to/crp-coverage-driven-rca-1_startd8_wloop.json
```

**Where the job lands:** `<queue_root>/jobs/<job_id>_startd8_wloop.json` with `status: "pending"`.

Expected: exit `0`, JSON on stdout. Exit `2` = validation fail (bad paths / missing fields). If the queue root was freshly created, a **stderr** note warns you to confirm the loop root (FR-24).

### CLI enqueue vs optional staging (FR-25)

| Mode | What you do | Where it lives after |
|------|-------------|----------------------|
| **CLI enqueue (recommended)** | Write envelope anywhere → `startd8 wloop enqueue --config <file> --root <loop-root>` | `jobs/<id>_startd8_wloop.json` (`status=pending`) |
| **Staging only** | Optionally draft under a personal `pending/` folder, then still pass that file to `--config` | Same — still `jobs/` after enqueue |

There is **no** v1 file-drop watcher. An empty `pending/` after enqueue is normal — use `wloop status`, not `ls pending/`.

### 3. Confirm

```bash
startd8 wloop status --job-id crp-coverage-driven-rca-1 \
  --root /ABS/PATH/startd8-sdk/.startd8/workflow-loop-queue
```

You should see `status: pending` and the absolute `plan_path` / `requirements_path` echoed back. Stop here unless the user asked you to drain.

---

## Field cheat sheet

| Field | Required | What to put |
|-------|----------|-------------|
| `schema_version` | yes | `"0.1.0"` until WLQ bumps it |
| `job_id` | yes | Stable unique id (`crp-<slug>`, uuid ok) |
| `loop_id` | yes | `"crp"` · `"reflective-requirements"` · `"research"` · `"one-shot"` |
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
| `plan_path` | dual-doc / plan-only | Absolute `.md` in the **consumer** project |
| `requirements_path` | dual-doc / requirements-only | Absolute `.md` in the **consumer** project |
| `scope` | yes | One sentence for the review round metadata |
| `max_rounds` | yes | e.g. `2` |
| `substantially_addressed_threshold` | yes | e.g. `3` |
| `max_suggestions` | yes | e.g. `10` (max 25) |
| `focus_file` | no | Optional sponsor/focus markdown (absolute) |
| `agent_template_path` | no | Optional `{{slot}}` template override |
| `reviewer_mode` | no | `"current"` (default) or `"blind_rotate"` |
| `reviewer_tier` | no | `"flagship"` \| `"mid_tier"` — expands 3-vendor roster (FR-23) |
| `reviewer_roster` | if blind_rotate without tier | Cursor Task model slugs; overrides tier expansion |
| `triage_policy` | no | `"auto_accept"` (default) or `"manual"` |
| `enable_triage` / `enable_apply` | sdk-workflow only | Usually leave unset for agent-surface |

Dual-doc CRP needs **both** paths. Single-doc: set only the one you are reviewing.

### Multi-vendor blind rotate (robustness)

**Option A — tier preset (recommended):** Anthropic + OpenAI + Google in one go.

```json
{
  "schema_version": "0.1.0",
  "job_id": "crp-flagship-1",
  "loop_id": "crp",
  "executor": "agent-surface",
  "surface_id": "cursor",
  "status": "pending",
  "config": {
    "plan_path": "/ABS/PATH/to/YOUR_PROJECT/.../PLAN.md",
    "requirements_path": "/ABS/PATH/to/YOUR_PROJECT/.../REQUIREMENTS.md",
    "scope": "Cross-vendor flagship CRP",
    "max_rounds": 3,
    "substantially_addressed_threshold": 3,
    "max_suggestions": 10,
    "reviewer_tier": "flagship"
  }
}
```

Use `"reviewer_tier": "mid_tier"` for mid/balanced models across the same three
vendors. List presets with `startd8 wloop list-reviewer-tiers`.

**Option B — explicit roster** (overrides the tier expansion if both are set):

```json
"reviewer_mode": "blind_rotate",
"reviewer_roster": [
  "claude-opus-5-thinking-high",
  "gpt-5.6-luna-medium",
  "gemini-3.1-pro"
]
```

Omitting `reviewer_mode` while setting `reviewer_tier` or a non-empty
`reviewer_roster` coerces to `blind_rotate`. Drain hand-offs then require a Task
spawn with the assigned model; write-back must include matching `reviewer_model`.

`max_rounds` is independent of roster length (R{n} uses `roster[(n-1) % len]`).
Typical flagship initiation: `max_rounds: 3` + `reviewer_tier: "flagship"`.

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
    "plan_path": "/ABS/PATH/to/YOUR_PROJECT/.../PLAN.md",
    "requirements_path": "/ABS/PATH/to/YOUR_PROJECT/.../REQUIREMENTS.md",
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

### Reflective-requirements (agent-surface)

Parent directories must exist; the requirements/plan files may be created on drain. Paths still point at the **consumer** project tree.

```json
{
  "schema_version": "0.1.0",
  "job_id": "refl-feature-x",
  "loop_id": "reflective-requirements",
  "executor": "agent-surface",
  "surface_id": "cursor",
  "status": "pending",
  "config": {
    "scope": "Feature X — requirements + plan bookend",
    "requirements_path": "/ABS/PATH/to/YOUR_PROJECT/.../REQUIREMENTS.md",
    "plan_path": "/ABS/PATH/to/YOUR_PROJECT/.../PLAN.md"
  }
}
```

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
    "document_path": "/ABS/PATH/to/YOUR_PROJECT/.../doc.md"
  }
}
```

Validate `config` keys against `startd8 workflow describe <workflow_id>` (when available).

### Chained jobs (reflective → CRP)

```json
"depends_on": ["refl-feature-x"]
```

Enqueue the reflective job first, then the CRP job with that `depends_on`. Drain skips the CRP until the dependency is `completed`.

### ContextCore O11y Subject-Surface backlog (Round 2)

Two ContextCore work items from the O11y Subject Surface Inputs CEP Round-2 backlog,
expressed as `reflective-requirements` (agent-surface) envelopes — the recipe the field
notes recommend for ContextCore design/build work (author reqs + plan in the consumer
tree, optionally chain a `crp` job for independent review). Paths point at the
**consumer** project (`ContextCore`); the grounded sources currently live on the
`feat/o11y-subject-surface` branch. Provenance is carried in `metadata` (source backlog
doc + item id).

**E3 — Unattended `blocked-awaiting-confirm` hand-off packet** (Size: S/M · Type: wire-existing)

On readiness state `blocked-awaiting-confirm` (exit 10), auto-derive + write the candidate
surface (`subject_surface/confirm.py::derive_candidate` + `write_candidate`, already wired
to `contextcore fde readiness --emit-candidate`) **and** emit a machine-readable readiness
report naming the missing domains (`ReadinessVerdict.to_dict()`) — giving an unattended loop
a ready-to-edit candidate + a structured "confirm these domains" artifact instead of a bare
hard-stop (file-based confirm — OQ-6, plan R1-S3 / R3-S1).

```json
{
  "schema_version": "0.1.0",
  "job_id": "refl-o11y-subject-surface-e3-confirm-handoff",
  "loop_id": "reflective-requirements",
  "executor": "agent-surface",
  "surface_id": "cursor",
  "priority": 0,
  "depends_on": [],
  "status": "pending",
  "config": {
    "scope": "E3 (wire-existing, S/M): on blocked-awaiting-confirm (exit 10) auto-derive+write the candidate surface AND emit a machine-readable readiness report naming missing domains, so an unattended loop gets a ready-to-edit candidate + structured confirm-these-domains artifact instead of a bare hard-stop (file-based confirm, OQ-6).",
    "requirements_path": "/Users/neilyashinsky/Documents/dev/ContextCore/docs/design/requirements/REQ_O11Y_SUBJECT_SURFACE_E3_CONFIRM_HANDOFF.md",
    "plan_path": "/Users/neilyashinsky/Documents/dev/ContextCore/docs/plans/O11Y_SUBJECT_SURFACE_E3_CONFIRM_HANDOFF_PLAN.md"
  },
  "metadata": {
    "enqueued_by": "agent",
    "surface_id": "cursor",
    "size": "S/M",
    "item_type": "wire-existing",
    "source_backlog": "ContextCore:docs/design/O11Y_SUBJECT_SURFACE_ENHANCEMENT_BACKLOG.md",
    "backlog_item": "E3",
    "grounded_in": [
      "src/contextcore/subject_surface/confirm.py (derive_candidate, write_candidate)",
      "src/contextcore/fde/subject_surface_readiness.py (ReadinessVerdict.to_dict)",
      "src/contextcore/fde/cli.py (fde readiness --emit-candidate)"
    ],
    "note": "Enqueue-only; drain separately. ContextCore O11y Subject Surface Inputs CEP Round-2 backlog. Sources on branch feat/o11y-subject-surface."
  }
}
```

**W1 — Live `covers 0→9` pipeline-integration test** (Size: L · Type: new-capability, environment/LLM-heavy)

The honest end-to-end anti-inert gate: `write_channel_b → capdevpipe run --plan → generate →
CoverageScorer.score` on a real Harbor subject clone, asserting the real `covers` count moves
off `0`, and that removing the persisted confirmed surface re-triggers the readiness block.
Turns "mechanism-proven" (the unit tests) into "proven on a real pilot." Deferred per
`docs/plans/O11Y_SUBJECT_SURFACE_NEXT_STEPS.md §5`.

```json
{
  "schema_version": "0.1.0",
  "job_id": "refl-o11y-subject-surface-w1-live-covers-test",
  "loop_id": "reflective-requirements",
  "executor": "agent-surface",
  "surface_id": "cursor",
  "priority": 0,
  "depends_on": ["refl-o11y-subject-surface-e3-confirm-handoff"],
  "status": "pending",
  "config": {
    "scope": "W1 (new-capability, L, environment/LLM-heavy): live covers 0->9 pipeline-integration test — write_channel_b -> capdevpipe run --plan -> generate -> CoverageScorer.score on a real Harbor subject clone; assert real covers count moves off 0 and that removing the persisted confirmed surface re-triggers the readiness block. Turns mechanism-proven into proven-on-a-real-pilot.",
    "requirements_path": "/Users/neilyashinsky/Documents/dev/ContextCore/docs/design/requirements/REQ_O11Y_SUBJECT_SURFACE_W1_LIVE_COVERS_TEST.md",
    "plan_path": "/Users/neilyashinsky/Documents/dev/ContextCore/docs/plans/O11Y_SUBJECT_SURFACE_W1_LIVE_COVERS_TEST_PLAN.md"
  },
  "metadata": {
    "enqueued_by": "agent",
    "surface_id": "cursor",
    "size": "L",
    "item_type": "new-capability",
    "environment": "environment/LLM-heavy",
    "source_backlog": "ContextCore:docs/design/O11Y_SUBJECT_SURFACE_ENHANCEMENT_BACKLOG.md",
    "backlog_item": "W1",
    "deferred_ref": "ContextCore:docs/plans/O11Y_SUBJECT_SURFACE_NEXT_STEPS.md §5",
    "grounded_in": [
      "repoprobe spine/runner",
      "repoprobe/coverage_scorer.py (CoverageScorer.score)",
      "real Harbor artifacts at /tmp/harbor-spine-197/analysis/"
    ],
    "note": "Enqueue-only; drain separately. ContextCore O11y Subject Surface Inputs CEP Round-2 backlog. Environment/LLM-heavy; deferred per O11Y_SUBJECT_SURFACE_NEXT_STEPS §5."
  }
}
```

---

## Using WLQ as the substrate for *your* agent loop (FR-26)

WLQ is not only for SDK-internal CRP. Any agent loop that needs durable, cross-session steps can **compose recipes** instead of inventing a new wake prompt:

1. Enqueue `loop_id: "reflective-requirements"` to author/update plan + requirements in the consumer project.
2. Enqueue `loop_id: "crp"` with `depends_on: ["<reflective-job-id>"]` for independent review.
3. Always shell out to `startd8 wloop …` (keep a **zero-import** boundary from consumer code into the SDK).
4. Drain with the loop-owning `--root`; document paths stay absolute into the consumer tree.

That preserves CRP **review independence** (the CRP job is a separate execution, not the author self-reviewing) and reuses lease/status/`depends_on` for free.

**Building a whole loop for another project?** This how-to covers a single enqueue. For the full build path — choosing/composing recipes, the drain loop, multi-vendor rotation, deferred triage, and the traps that have cost real time — see [HOWTO_BUILD_A_LOOP.md](HOWTO_BUILD_A_LOOP.md).

---

## Agent checklist (enqueue)

Copy and tick mentally:

1. [ ] Resolve **absolute** plan/requirements paths in the **consumer** project; confirm files exist.
2. [ ] Choose the **loop-owning** `--root` (or `$STARTD8_WLOOP_ROOT`) — not “wherever I opened the docs.”
3. [ ] Choose `executor` + `surface_id` (or `workflow_id` for sdk).
4. [ ] Fill CRP `config` or workflow inputs — no phantom fields.
5. [ ] Set `status` to `pending`.
6. [ ] Write `*_startd8_wloop.json` (not `*_startd8_job.json` — that is the old prompt queue).
7. [ ] Run `startd8 wloop enqueue --config … --root …`.
8. [ ] Confirm via `startd8 wloop status --job-id …` (not `ls pending/`).
9. [ ] Tell the user the `job_id`, the queue root used, and that drain is a separate step.

---

## What not to do

| Anti-pattern | Why |
|--------------|-----|
| Enqueue from the doc repo without `--root` / `$STARTD8_WLOOP_ROOT` | Creates an orphan queue under CWD (FR-24) |
| Point `plan_path` at WLQ design docs by default | Review the **consumer** plan/reqs unless reviewing WLQ itself |
| Use `*_startd8_job.json` / prompt JobQueue | Different system; no `workflow_id` / CRP intent |
| Pass a generated CRP prompt as `review_template` | Breaks SDK `str.format` (`KeyError: 'n'`) |
| Set `status` to `processing` yourself | Only the drain path owns that |
| Triage Appendix A/B during enqueue | Separate `triage` / human step |
| Invent `R{n}` | Derived at drain from the doc |
| Relative paths without project-root resolution | Fail-closed validation |
| Confirm enqueue by `ls …/pending/` | CLI stores under `jobs/`; use `wloop status` (FR-25) |

---

## After enqueue (not part of this how-to)

When the user asks to **run** the job:

```bash
startd8 wloop run-next --job-id crp-coverage-driven-rca-1 \
  --root /ABS/PATH/startd8-sdk/.startd8/workflow-loop-queue
```

For `agent-surface`, read the Drain Hand-off JSON (and optional `markdown_card_path`) and execute the rendered bundle in the **current** chat by default (see VASI §5), or spawn a Task when `assigned_reviewer.mode=blind_rotate`. Then write `drain-result.json` and re-run `run-next` to verify.

**Deferred triage:** after each review round short of `max_rounds`, status returns to `pending` so the next round can drain immediately. After the final review round, default `triage_policy=auto_accept` automatically ACCEPTS untriaged Appendix C ids into Appendix A and marks the job `completed`. Set `"triage_policy": "manual"` to stop at `awaiting_triage` for an explicit `startd8 wloop triage` call instead.

**A/B/C scaffold:** on render/drain, WLQ idempotently ensures the `## Appendix: Iterative Review Log` scaffold in each source doc (same contract as `new-cnvrg-rvw-prmpt.sh`). Reviewers only append a `#### Review Round` under Appendix C — they do not initialize the scaffold.

---

## Minimal chat reply after enqueue

Keep it short, for example:

> Enqueued `crp-coverage-driven-rca-1` (`loop_id=crp`, `executor=agent-surface`, `surface_id=cursor`) under `/ABS/…/startd8-sdk/.startd8/workflow-loop-queue` — status `pending`. Docs: `<plan>` + `<reqs>`. Say when to `run-next`.

---

## Experimental Python API (FR-19)

```python
from startd8.workflows.loop_queue import (
    LoopQueueConfig,
    WorkflowLoopJob,
    WorkflowLoopQueue,
)

queue = WorkflowLoopQueue(
    LoopQueueConfig(queue_root="/ABS/PATH/startd8-sdk/.startd8/workflow-loop-queue")
)
queue.enqueue(WorkflowLoopJob.model_validate({...}))  # same envelope as CLI
queue.run_next(job_id="crp-coverage-driven-rca-1")
```

Pre-1.0: import path and envelope fields may change in MINOR versions.

---

*How-to for agents · WLQ enqueue · pairs with VASI `enqueue` capability · FR-24/25/26.*
