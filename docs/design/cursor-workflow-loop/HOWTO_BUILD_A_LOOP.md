# How to Build an Agent Loop on the Workflow Loop Queue

**Audience:** Cursor agents (and any VASI surface) asked to build a durable, multi-step
agent loop for **some other project** — not to enqueue into an existing one.
**Status:** Experimental pre-1.0 (FR-19). Envelope fields may change in MINOR versions.
**Related:** [HOWTO_AGENT_ENQUEUE.md](HOWTO_AGENT_ENQUEUE.md) (how to enqueue one job) ·
[VENDOR_AGENT_SURFACE_INTERFACE.md](VENDOR_AGENT_SURFACE_INTERFACE.md) (the drain contract) ·
[CURSOR_WORKFLOW_LOOP_REQUIREMENTS.md](CURSOR_WORKFLOW_LOOP_REQUIREMENTS.md) (normative FRs)

---

## Read this first: you almost certainly should not write new code

The instinct when asked for "a review loop for project X" is to write a driver script that
walks rounds, tracks state in memory, and re-prompts a model. Don't. That state dies with the
chat session, and every project ends up with a slightly different, slightly broken loop.

WLQ already owns the hard parts, and they are the parts that break:

| You get for free | Why you'd otherwise get it wrong |
|---|---|
| Durable on-disk job state | Chat context ends; the loop must survive session death |
| Lease + expiry (`lease_ttl_seconds`, default 3600s) | A crashed reviewer otherwise wedges the job forever |
| `depends_on` DAG with cycle detection at enqueue | Hand-rolled ordering silently runs steps out of order |
| Round derivation from the document itself | In-memory round counters desync from the doc on resume |
| Cross-vendor reviewer rotation (`blind_rotate`) | One model reviewing its own work is not independent review |
| Deferred batch triage + `auto_accept` | Triaging between rounds lets round N see round N-1's verdicts |
| Bundle caching by content hash (Mottainai) | Re-rendering wastes work and changes the prompt mid-loop |
| JSON-only stdout contract | Log/OTel noise otherwise breaks your `json.loads` |

**So the default answer is: compose existing recipes, shell out to `startd8 wloop`, write zero
Python.** Only add a new recipe when your loop's *steps* genuinely differ (see
[§7](#7-when-you-actually-need-a-new-recipe)).

---

## 1. The mental model — four nouns, two verbs

**Nouns:**

1. **Queue root** — the directory that *owns the loop*. Holds `jobs/` plus per-job artifact
   folders. Usually lives in the **tooling** repo (startd8-sdk), *not* the project whose docs
   you're processing.
2. **Job envelope** — one JSON file describing one unit of durable work. Persisted as
   `<queue_root>/jobs/<job_id>_startd8_wloop.json`.
3. **Loop recipe** (`loop_id`) — declares what a loop needs and which executors can drain it.
   Built-ins: `crp`, `reflective-requirements`, `research`, `one-shot`.
4. **Executor** — who does the work:
   - `agent-surface` → *you* (an agent) do it. Requires `surface_id` (`cursor`, `codex`, …).
   - `sdk-workflow` → the SDK runs a registered workflow. Requires `workflow_id`.

**Verbs:**

- `enqueue` — validate + persist an envelope as `pending`.
- `run-next` — the whole loop engine. Called on a `pending` job it **emits a hand-off**; called
  again on a `processing` job it **consumes the drain-result** and advances. You call it
  repeatedly; it decides what happens.

Everything else (`status`, `render`, `cancel`, `requeue`, `triage`) is inspection or recovery.

### Job status lifecycle

```
pending ──run-next──▶ processing ──(you drain + write drain-result)──▶ run-next
                                                                          │
                        ┌── more rounds remain ────────────────────────────┤
                        ▼                                                  ▼
                     pending                            triage_policy=auto_accept → completed
                                                        triage_policy=manual      → awaiting_triage
```

Terminal: `completed`, `failed`, `cancelled`. Recoverable: `blocked`, plus `processing` with an
expired lease.

---

## 2. Decide your shape (30 seconds)

| Your loop is… | Do this |
|---|---|
| "Review these docs with several models, then apply the suggestions" | One `crp` job. §3. |
| "Write requirements + a plan, then review them independently" | `reflective-requirements` job, then a `crp` job with `depends_on`. §4. |
| "Investigate a RESEARCH brief and write FINDINGS" | `research` job (brief → findings). Optional follow-on `crp` with `depends_on`. |
| "Run one catalog workflow once, durably" | `one-shot` + `sdk-workflow` + `workflow_id`. |
| "Chain several of the above with ordering" | Multiple envelopes + `depends_on`. §4. |
| Genuinely new step sequence | New recipe — SDK code change. §7. |

Confirm what's actually registered instead of trusting this table:

```bash
startd8 wloop list-loops
startd8 wloop list-reviewer-tiers
startd8 wloop list-surfaces
```

---

## 3. The minimum viable loop: one CRP job

### 3.1 Set the queue root once

This is the single most common mistake, so do it before anything else:

```bash
export STARTD8_WLOOP_ROOT=/ABS/PATH/startd8-sdk/.startd8/workflow-loop-queue
```

The queue root is where the **loop** lives. The document paths in `config` point into the
**project under review**. They are different repos and that is normal. If you skip this and
enqueue from the project directory, you create an orphan queue under that project's CWD that
nobody will ever drain — and enqueue will still *succeed*, so nothing tells you until much
later. (WLQ prints a one-time stderr note when it creates a brand-new root; read it.)

### 3.2 Write the envelope

Draft it anywhere — a temp file is fine. `enqueue` copies it into `jobs/`.

```json
{
  "schema_version": "0.1.0",
  "job_id": "crp-widget-pipeline-1",
  "loop_id": "crp",
  "executor": "agent-surface",
  "surface_id": "cursor",
  "priority": 0,
  "status": "pending",
  "depends_on": [],
  "config": {
    "plan_path": "/ABS/PATH/your-project/docs/plans/WIDGET_PIPELINE_PLAN.md",
    "requirements_path": "/ABS/PATH/your-project/docs/design/requirements/REQ_WIDGET_PIPELINE.md",
    "scope": "Dual-doc CRP for the widget pipeline — focus idempotency, the retry budget, and failure attribution.",
    "max_rounds": 3,
    "substantially_addressed_threshold": 3,
    "max_suggestions": 10,
    "focus_file": null,
    "reviewer_tier": "flagship",
    "triage_policy": "auto_accept"
  },
  "budget": { "max_rounds": 3 },
  "metadata": { "enqueued_by": "agent", "surface_id": "cursor" }
}
```

`config` is a `CrpReviewRequest` and **rejects unknown keys** — a typo fails at enqueue with
exit 2 rather than being silently ignored. Requires `plan_path` and/or `requirements_path`.
`max_suggestions` is capped at 25; `max_rounds` ≥ 1 (default 2).

Note there is **no `round` field**. Round numbers are derived at drain time from the highest
existing `#### Review Round R{n}` in the document. Never invent one — that's what makes resume
work after a crash.

### 3.3 Enqueue and confirm

```bash
startd8 wloop enqueue --config /tmp/crp-widget-pipeline-1_startd8_wloop.json
startd8 wloop status --job-id crp-widget-pipeline-1
```

Confirm with `status`, **not** by listing directories. There is no `pending/` folder in the
post-enqueue storage layout and no file-drop watcher in v1; jobs live in `jobs/`.

Exit codes are stable and worth branching on in scripts: `0` ok, `2` validation failed (fix the
envelope), `3` blocked/retryable, `1` other WLQ error.

---

## 4. Composing steps: author, then review independently

The valuable pattern. Two envelopes, one dependency edge:

```json
{ "job_id": "refl-widget", "loop_id": "reflective-requirements",
  "executor": "agent-surface", "surface_id": "cursor", "status": "pending",
  "config": {
    "scope": "Widget pipeline — requirements + plan bookend",
    "requirements_path": "/ABS/PATH/your-project/docs/design/requirements/REQ_WIDGET_PIPELINE.md",
    "plan_path": "/ABS/PATH/your-project/docs/plans/WIDGET_PIPELINE_PLAN.md"
  } }
```

```json
{ "job_id": "crp-widget-pipeline-1", "loop_id": "crp",
  "executor": "agent-surface", "surface_id": "cursor", "status": "pending",
  "depends_on": ["refl-widget"],
  "config": { "...": "as in §3.2" } }
```

Enqueue the reflective job first. `run-next` refuses to drain the CRP job until `refl-widget`
is `completed`; cycles are rejected at enqueue.

This matters beyond convenience: because the CRP job is a **separate execution** from the
authoring job, the reviewer is not the author holding its own reasoning in context. That's the
review independence you'd lose by doing both in one chat.

For `reflective-requirements`, parent directories must exist at enqueue, but the target files
themselves may be created during drain.

### Keep the consumer project import-free

Consumer projects should **shell out** to `startd8 wloop` and parse JSON. Do not
`import startd8` from the project's own code just to enqueue. The envelope + CLI is the
contract; keeping it a process boundary means the project doesn't inherit the SDK's dependency
tree or its pre-1.0 API churn.

---

## 5. Draining: the loop an agent actually runs

Per round, four steps. Do not batch them or skip the second `run-next`.

**1. Get the hand-off.**

```bash
startd8 wloop run-next --job-id crp-widget-pipeline-1
```

Returns a `DrainHandoff` on stdout. The fields you need:

| Field | Use |
|---|---|
| `round_number` | The `R{n}` to append |
| `bundle_path` | Self-contained markdown instructions — the reviewer's only prompt |
| `source_paths` | Absolute docs to edit |
| `status_writeback_path` | Where your `drain-result.json` goes |
| `assigned_reviewer.mode` | `current` (review in this chat) or `blind_rotate` (spawn a Task) |
| `assigned_reviewer.model` | The Cursor Task model slug for this round |
| `success_criteria` | What "done" means, machine-readable |
| `markdown_card_path` | Human-readable version of the hand-off |

**2. Execute the round.** If `blind_rotate`, spawn a Task with exactly
`assigned_reviewer.model` and point it at `bundle_path`. If `current`, follow the bundle here.

For `crp`: append `#### Review Round R{n}` under **Appendix C only**. Do not triage, do not
touch Appendix A/B, do not rewrite prose. Dual-doc rounds also append a Requirements Coverage
Matrix to the plan.

**The A/B/C scaffold is already there.** WLQ ensures it on render (same contract as
`new-cnvrg-rvw-prmpt`), which is why the hand-off says
`init_appendix_if_missing: false, appendix_scaffold_ensured: true`. A reviewer that "helpfully"
initializes it creates a second scaffold and corrupts the doc.

**3. Write the drain-result** to `status_writeback_path`:

```json
{
  "vasi_version": "0.1.0",
  "job_id": "crp-widget-pipeline-1",
  "surface_id": "cursor",
  "ok": true,
  "round_number": 1,
  "suggestion_counts": { "S": 5, "F": 4 },
  "paths_written": [
    "/ABS/PATH/your-project/docs/plans/WIDGET_PIPELINE_PLAN.md",
    "/ABS/PATH/your-project/docs/design/requirements/REQ_WIDGET_PIPELINE.md"
  ],
  "reviewer_model": "claude-opus-5-thinking-high"
}
```

`suggestion_counts` keys must be exactly `S` (plan) and `F` (requirements), non-negative.
`reviewer_model` is **required** under `blind_rotate` and must match
`assigned_reviewer.model` — that's the check that catches "I said Gemini but Opus actually ran."

**4. Call `run-next` again** to consume the write-back. WLQ verifies the append landed, records
the round, and either returns the job to `pending` (more rounds) or finishes it. Repeat from
step 1 until the status is terminal.

---

## 6. Multi-vendor rounds and deferred triage

### Reviewer rotation

Set `reviewer_tier` and WLQ expands a cross-vendor roster (Anthropic → OpenAI → Google) and
coerces `reviewer_mode` to `blind_rotate`:

| Tier | Roster |
|---|---|
| `flagship` | `claude-opus-5-thinking-high`, `gpt-5.6-luna-medium`, `gemini-3.1-pro` |
| `mid_tier` | `claude-sonnet-5-thinking-high`, `gpt-5.6-terra-medium`, `gemini-3.6-flash-high` |

Round → model is `roster[(round_number - 1) % len(roster)]`, so `max_rounds: 3` with a 3-model
roster gives one round per vendor. An explicit `reviewer_roster` overrides the tier. Verify
slugs with `list-reviewer-tiers` rather than hardcoding from this doc — if a slug isn't
available, say so instead of substituting a different model.

Use `reviewer_mode: "current"` (the default, no roster) when you want the round done in-chat.
It's faster and avoids subagent overhead, but it is *not* independent review.

### Why triage is deferred

All `max_rounds` rounds run to completion **before** any triage. Round 2 therefore sees round
1's raw suggestions in Appendix C but not their dispositions — it can independently endorse or
contradict them instead of treating an early ACCEPT as settled.

After the final round, `triage_policy` decides:

- `auto_accept` (default) — every untriaged Appendix C id is ACCEPTed into Appendix A and the
  job goes `completed`.
- `manual` — the job parks in `awaiting_triage` until you run
  `startd8 wloop triage --job-id … --decisions decisions.json` with explicit
  `ACCEPT`/`REJECT` + rationale. Rejections go to Appendix B *with the reason*, which is what
  stops a later round from re-proposing the same idea.

Pick `manual` when the docs are load-bearing and a wrong auto-apply is expensive.

---

## 7. When you actually need a new recipe

Only if your loop's **steps** differ — not merely its subject matter, prompt, or model. A
different focus for a CRP is a `scope` string and a `focus_file`, not a new recipe.

If you do need one, in `src/startd8/workflows/loop_queue/`:

1. Define a request model in `models.py` with `extra="forbid"`, a `source_paths` property, and
   `content_hash()` (the bundle-cache key).
2. `register_recipe(LoopRecipe(...))` in `recipes.py` — declare `loop_id`, `executors`,
   `inputs`, `completion`, `steps`.
3. Add a `<loop_id>_request()` accessor on `WorkflowLoopJob`.
4. Handle the loop in `queue.py`'s drain path; add a renderer if it needs a bundle.
5. Add an FR to the requirements doc and tests under
   `tests/unit/workflows/loop_queue/`.

Keep recipes thin. The registry deliberately is not a second `WorkflowRegistry` — if the work
is a registered workflow, use `one-shot` + `sdk-workflow` instead of a new recipe.

---

## 8. Traps that have actually bitten people

Ordered by how much time each has cost.

**Source docs must be in a real worktree on a named branch.** Docs under `/tmp`, or in a repo
sitting on a detached HEAD, get the job `blocked` at render. If the docs you need aren't on a
branch, make a worktree first:
`git worktree add /ABS/PATH/project-loopwork my-branch`. Two jobs were lost to this before the
cause was clear.

**Queue root ≠ document root.** Covered in §3.1 because it's the #1 error. Always set
`$STARTD8_WLOOP_ROOT` or pass `--root`.

**Keep reviewer subagent scope tight.** A `blind_rotate` reviewer given free rein to explore
the target repo can burn 90+ minutes without writing anything. Tell it to read the bundle, the
focus file, and the source docs — *and nothing else*. No repo-wide greps. Emphasize that
persisting the append is mandatory and that the round fails if nothing is written.

**Never pass an agent bundle as a `review_template`.** SDK `review_template` goes through
`str.format`, so a CRP bundle containing `R{n}` dies with `KeyError: 'n'`. WLQ detects bundle
markers (`{{`, `R{n}`, `{round}`) and fails closed. Agent-surface template overrides go in
`agent_template_path` and use **`{{slot}}` placeholders only**.

**Recovering a stuck job.** A `processing` job whose `lease_expires_at` has passed reclaims
automatically on the next call (TTL default 3600s; `0` disables auto-reclaim). To force it:
`startd8 wloop requeue --job-id …`. Check for a partial append before retrying — if the
reviewer wrote Appendix C but never wrote the drain-result, re-running the round duplicates
suggestions.

**Parse stdout, not the whole stream.** `wloop` guarantees JSON-only on stdout; logs and OTel
failures go to stderr. Keep them separate (`2>/dev/null` when you only want the payload)
instead of reading combined output. If you see `JSONDecodeError: Extra data`, you merged the
streams.

**Filename suffix is `_startd8_wloop.json`.** `_startd8_job.json` is the unrelated prompt
JobQueue.

**Don't set `status: "processing"` yourself.** The drain path owns that transition; setting it
by hand creates a job with no lease that never reclaims.

**`executor: "cursor-agent"`** is a deprecated synonym for `agent-surface` (auto-migrated with
`surface_id: "cursor"`). Write `agent-surface` in anything new.

---

## 9. Cursor-specific setup

A multi-round loop with subagents generates a lot of permission prompts, which stalls
unattended drains. Two hooks in the loop-owning repo fix that — see `.cursor/hooks.json` plus
`.cursor/hooks/` in startd8-sdk:

- a `preToolUse` hook auto-allowing `Write`/`StrReplace`/`Delete`/`ApplyPatch` so reviewers can
  append without interruption;
- a `subagentStart` hook auto-allowing the Task spawns `blind_rotate` needs.

Both fail open for unmatched tools. Scope them to a repo where auto-allowing writes is
acceptable.

There's also a `workflow-loop-queue` skill in `.cursor/skills/` with the condensed enqueue and
drain procedures — worth reading before driving a loop by hand.

---

## 10. Build checklist

1. [ ] `startd8 wloop list-loops` — confirm an existing recipe fits; don't invent one.
2. [ ] Source docs exist, are markdown, are in a **real worktree on a named branch**.
3. [ ] `export STARTD8_WLOOP_ROOT=…` pointing at the **loop-owning** repo.
4. [ ] Envelope(s) written: absolute doc paths, `status: "pending"`, correct executor +
       `surface_id`/`workflow_id`, no invented fields.
5. [ ] Multi-step? `depends_on` set, authoring job enqueued first.
6. [ ] CRP? `reviewer_tier` + `max_rounds` matching the roster length, `triage_policy` chosen
       deliberately.
7. [ ] `enqueue` → `status` confirms `pending`.
8. [ ] Drain loop: `run-next` → execute (tight scope) → `drain-result.json` → `run-next`,
       repeated to terminal status.
9. [ ] Tell the user the `job_id`, the queue root, the reviewer roster, and the triage policy.

---

*Guide for agents building loops on WLQ · pairs with HOWTO_AGENT_ENQUEUE.md (single-job
enqueue) and VENDOR_AGENT_SURFACE_INTERFACE.md (the drain contract) · FR-7 / FR-15 / FR-16 /
FR-23 / FR-24 / FR-25 / FR-26.*
