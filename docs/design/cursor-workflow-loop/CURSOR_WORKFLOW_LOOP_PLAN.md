# Workflow Loop Queue (WLQ) — Implementation Plan

**Version:** 0.5 (Aligned with Requirements v0.5 — multi-vendor VASI)
**Date:** 2026-07-24
**Status:** Increments 0–2 implemented on `feat/wloq-inc0-inc1` (Inc 3 harden remaining)
**Requirements:** `CURSOR_WORKFLOW_LOOP_REQUIREMENTS.md`

---

## 1. Approach

Build a **sibling** of `JobQueue`: same operational feel (folder, status, priority, sequential drain), new envelope that addresses `WorkflowRegistry` / loop recipes. Core is **vendor-neutral**. v1 ships a **Cursor reference skill**; Codex and Antigravity implement the published **Vendor Agent Surface Interface (VASI)** themselves.

**Code home (recommended):** `src/startd8/workflows/loop_queue/` — keeps “loop queue” next to workflows, avoids overloading `job_queue.py` or `agents/agentic.py` (lessons: overloaded-term).

### Spike + multi-vendor path

The generated `CRP_PROMPT_R1.md` is a self-contained agent-surface bundle. It
cannot be reused as `architectural-review-log.review_template` (`str.format` /
`KeyError: 'n'`).

**Normative path:**

1. Typed `CrpReviewRequest` is the sole CRP config seam.
2. Renderer produces a **fully substituted** markdown bundle (default: `new-cnvrg-rvw-prmpt`; optional `{{slot}}` project template).
3. Drain for `executor=agent-surface` emits a **VASI Drain Hand-off**; the named `surface_id` (cursor / codex / antigravity / …) opens the bundle and appends Appendix C.
4. SDK executor maps the same request → `architectural-review-log` / `convergent-review` — never via agent-surface bundles.
5. Publish `VENDOR_AGENT_SURFACE_INTERFACE.md` early (Inc 0.5) so Codex/Antigravity can proceed without waiting on Cursor-only UX.

---

## 2. Increment 0 — Envelope + disk

| Step | Work | Maps to |
|------|------|---------|
| 0a | Pydantic models: `WorkflowLoopJob`, `LoopJobStatus` ∈ {pending, processing, awaiting_triage, completed, failed, cancelled, blocked}, `LoopExecutor` ∈ {agent-surface, sdk-workflow}, `surface_id`, `LoopQueueConfig`, **`CrpReviewRequest`** | FR-1, FR-1a, FR-3 |
| 0b | Atomic JSON write/read; status sidecar; archive helpers (reuse `utils/file_operations.atomic_write_json`) | FR-2, FR-3 |
| 0c | `enqueue(job)` validates schema; CRP → validate `CrpReviewRequest`; if `workflow_id` set → `WorkflowRegistry.discover()` + input validation; reject agent-surface bundles as `review_template` | FR-5, FR-6, FR-9, NR-8 |
| 0d | CLI stub: `startd8 wloop status` / `enqueue` / `cancel` / `run-next` / `list-loops` / `list-surfaces` (drain may no-op until Inc 1) | FR-4, FR-7, FR-22 |
| 0e | Unit tests: round-trip, unknown workflow fail-closed, missing path fail-closed, CRP intent keys required | FR-1, FR-1a, FR-5, FR-6 |
| 0f | Interim: explicit `requeue`/`cancel` for stuck `processing` (lease TTL deferred to Inc 3 / OQ-5) | FR-3 |

**Default path (OQ-7 lean):** `.startd8/workflow-loop-queue/` under project root — isolates from prompt jobs.

---

## 2.5 Increment 0.5 — Publish VASI (unblocks Codex / Antigravity)

| Step | Work | Maps to |
|------|------|---------|
| 0.5a | Write `VENDOR_AGENT_SURFACE_INTERFACE.md` (ops, capabilities, Drain Hand-off JSON schema, status write-back) | FR-21 |
| 0.5b | Document known surfaces: `cursor` (shipped), `codex` / `antigravity` (external ownership) | FR-22, NR-9 |
| 0.5c | JSON Schema fixture + contract test for Drain Hand-off | FR-21 acceptance |
| 0.5d | Mock surface fixture that only consumes hand-off (no Cursor) | FR-4, FR-8 |

---

## 3. Increment 1 — Agent-surface review-template + Cursor reference

| Step | Work | Maps to |
|------|------|---------|
| 1a | `LoopRecipe` protocol + `crp` recipe registration | FR-7 |
| 1b | Derive next round / A/B ID lists — reuse helpers from `architectural_review_log_helpers.py` | FR-11, Mottainai |
| 1c | **FR-20 renderer:** default shell/import `new-cnvrg-rvw-prmpt`; optional `agent_template_path` with `{{slot}}` only; cache rendered bundle under job artifact dir (content hash) | FR-8, FR-14, FR-20 |
| 1d | Drain step machine: `pending → processing → awaiting_triage \| pending(next round) → completed`; emit VASI Drain Hand-off | FR-12, FR-13, FR-21 |
| 1e | **Cursor reference skill:** `enqueue-crp`, `wloop-status`, `wloop-run-next` (consume hand-off + execute), `wloop-cancel` | FR-4, FR-8 |
| 1f | Fixture: temp markdown → render → R1 append → R2; status write-confirmation + S/F counts; dual-doc prefix isolation; mock-surface drain | FR-8, FR-11, FR-14, FR-20, FR-21 |
| 1g | First-class `triage` skill/CLI: Accepted→A / Rejected→B; keep C append-only; clear `awaiting_triage` | FR-13 |

---

## 4. Increment 1.1 — CRP sdk-workflow executor

| Step | Work | Maps to |
|------|------|---------|
| 1.1a | Map `CrpReviewRequest` → `convergent-review` / `architectural-review-log`; never route Cursor bundle through `review_template` | FR-9, NR-8 |
| 1.1b | Drain via `WorkflowRegistry.run_workflow` (in-process) with progress → status updates | FR-9 |
| 1.1c | Scripted-agent CI path + contract test: one request → two independent renderers | FR-9 acceptance |

---

## 5. Increment 2 — Catalog + deps

| Step | Work | Maps to |
|------|------|---------|
| 2a | `one-shot` recipe: any `workflow_id` + config | FR-15 |
| 2b | Priority list: critical-review, design-polish, doc-enhancement, plain-language, policy-analysis | FR-15 |
| 2c | `depends_on` resolution + cycle detection at enqueue | FR-16 |
| 2d | Optional: MCP tool wrappers if `user-startd8` healthy; optional Automation draft | FR-4 Inc2, OQ-9 |

---

## 6. Increment 3 — Harden

| Step | Work | Maps to |
|------|------|---------|
| 3a | OTel spans / structured logs | FR-17 |
| 3b | Budget wiring for sdk-workflow | FR-18 |
| 3c | Experimental API export + docs | FR-19 |
| 3d | Resolve OQ-5 (lease TTL) and OQ-6 (reflective-reqs recipe) | OQs |

---

## 7. Risks

| Risk | Mitigation |
|------|------------|
| Cursor-agent CRP quality varies by model | Keep sdk-workflow executor; Capability-Delivery Loop already proved Cursor CRP when grounded |
| Helper reuse from architectural_review_log pulls private `_` APIs | Promote a small public parse/derive module if needed (Keiyaku boundary) |
| Dual CRP paths drift | One typed CRP request + single recipe owns policy/completion; executor adapters own rendering; both write the same appendix shape |
| Generated prompt accidentally passed as workflow template | Reject this mapping in validation; regression-test the literal-brace incompatibility discovered by the spike (NR-8 / FR-20) |
| Skill sprawl | One skill with subcommands > many one-off skills |
| Project `{{slot}}` templates diverge from CRP guide | Default renderer remains `new-cnvrg-rvw-prmpt`; overrides are opt-in and must still produce Appendix C append-only contract |

---

## 8. Settled / do-not-relitigate (for CRP)

- Prompt `JobQueue` stays; CWLQ is sibling envelope.
- Agentic tool-use loop is out of scope.
- CRP 7-column schema / A/B/C owned upstream — cite only.
- Prime/cap-dev-pipe not replaced in v1.
- Cursor Automations not a v1 dependency.
- **Agent-surface review path = pre-rendered markdown template workflow (FR-20), not SDK `review_template`.**
- **Codex / Antigravity are VASI consumers (NR-9), not SDK deliverables.**

---

*Plan v0.5 — tracks Requirements v0.5 (multi-vendor VASI). Inc 0.5 publishes the interface so Codex/Antigravity can implement in parallel with Cursor reference work.*

---

## Appendix: Iterative Review Log (Applied / Rejected Suggestions)

This appendix is intentionally **append-only**. New reviewers (human or model) add suggestions to Appendix C; once validated, the orchestrator records the final disposition in Appendix A (applied) or Appendix B (rejected with rationale). **Do not delete A/B** — they are the cross-model memory that stops later reviewers from re-proposing settled or rejected ideas.

### Reviewer Instructions (for humans + models)

- **Before suggesting changes**: Scan Appendix A and Appendix B first. Do **not** re-suggest items already applied or explicitly rejected.
- **When proposing changes**: Append a `#### Review Round R{n}` block under Appendix C (n = highest existing round + 1, or 1), with unique suggestion IDs `R{n}-S{k}` (plan) / `R{n}-F{k}` (requirements).
- **When endorsing prior suggestions**: If you agree with an untriaged item from a prior round, list it in an **Endorsements** section instead of restating it. Multi-reviewer endorsements raise triage priority.
- **When validating (orchestrator)**: For each suggestion, append a row to Appendix A (applied) or Appendix B (rejected) referencing the suggestion ID.
- **If rejecting**: Record **why** (specific rationale) so future reviewers don't re-propose the same idea.

### Appendix A: Applied Suggestions

| ID | Suggestion | Source | Implementation / Validation Notes | Date |
|----|------------|--------|-----------------------------------|------|
| R1-S1 | Explicit `CrpReviewRequest` in Inc 0 | CRP R1 | Step 0a | 2026-07-24 |
| R1-S2 | CLI cancel / run-next / list-loops | CRP R1 | Step 0d | 2026-07-24 |
| R1-S3 | Full `LoopJobStatus` wire set | CRP R1 | Step 0a | 2026-07-24 |
| R1-S4 | Interim requeue/cancel before OQ-5 | CRP R1 | Step 0f | 2026-07-24 |
| R1-S5 | First-class triage action | CRP R1 | Step 1g | 2026-07-24 |
| R1-S6 | Status write-confirmation + dual-doc tests | CRP R1 | Step 1f | 2026-07-24 |
| FR-20 | Cursor review-template workflow | reqs v0.4 | Steps 1c–1f rewritten | 2026-07-24 |
| multi-vendor | VASI + surface_id + Inc 0.5 | reqs v0.5 | §1 rewrite; Inc 0.5; NR-9 | 2026-07-24 |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (implicit) Use Cursor CRP bundle as SDK `review_template` | Spike | `str.format` / `KeyError: 'n'`; NR-8 | 2026-07-24 |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — composer-2.5 — 2026-07-25

- **Reviewer**: composer-2.5
- **Date**: 2026-07-25 02:40:00 UTC
- **Scope**: Dual-doc first pass — plan sequencing, executor seam, status/ops gaps vs Requirements v0.3.2

**Executive summary**

- Typed `CrpReviewRequest` is named in §1 but has no Increment step — risk of drifting into ad-hoc `config` dicts.
- Inc 0 CLI (0d) covers only status/enqueue; FR-4 also needs cancel, run-next/drain, and FR-7 `list-loops`.
- Step 0a status models omit `awaiting_triage` / lease fields that FR-13 and FR-3 acceptance require.
- OQ-5 deferred to Inc 3 (3d) leaves FR-3 kill-mid-job acceptance untestable in Inc 0–1.
- Drain machine (1d) enters `awaiting_triage` but no plan step owns the triage skill/CLI action.
- Plan settles OQ-7 lean (dedicated folder) while requirements still list OQ-7 as open — cross-doc conflict.

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-S1 | Architecture | high | Add an explicit Increment 0 or early-1 step that defines and persists the typed `CrpReviewRequest` (paths, scope, rounds, threshold, max suggestions, agent/provider policy, triage/apply policy) as the sole CRP config seam — not only prose in Approach. | §1 Approach says “Create one typed `CrpReviewRequest` (or equivalent job config) as the seam” but §§2–4 tables never schedule it; without a step, implementers will stuff fields into opaque `config`. | New row after 0a or as 1a-pre in §3 Increment 1 | Unit test: both executor mappers accept one `CrpReviewRequest` instance and reject unknown keys |
| R1-S2 | Interfaces | high | Expand step 0d CLI stub beyond `status` / `enqueue` to include `cancel`, `run-next`/`drain`, and `list-loops` (even if drain is no-op until Inc 1). | Step 0d text is “CLI stub: `startd8 wloop status` / `enqueue`”; FR-4 requires enqueue, status, run-next/drain, cancel; FR-7 acceptance needs `list-loops`. | §2 Increment 0, step 0d | CLI `--help` smoke + fail-closed cancel of unknown job_id |
| R1-S3 | Data | high | In step 0a, pin `LoopJobStatus` to the full wire set used later: at least `pending`, `processing`, `completed`, `failed`, `cancelled`, `blocked`, `awaiting_triage`, plus optional lease/heartbeat fields. | 0a lists `LoopJobStatus` without enumerating values; §3 step 1d already transitions to `awaiting_triage`, and FR-3/FR-13 require those statuses on disk. | §2 Increment 0, step 0a | Schema round-trip test for every status enum member |
| R1-S4 | Risks | high | Add an Inc 0/1 interim lease stub (TTL or explicit `requeue`) so kill-mid-job behavior is defined before OQ-5 final resolution in 3d. | §6 step 3d defers OQ-5 to harden, but FR-3 acceptance (“kill mid-job → failed or resumable processing with a clear lease/heartbeat rule”) is otherwise untestable in the flagship path. | New 0f or 1d-adjacent note under §3; keep 3d as final policy pick | Integration: kill drain process → status becomes `failed` or leased-stale `processing` per documented rule |
| R1-S5 | Ops | medium | Add an Increment 1 step for a first-class `triage` skill/CLI action that moves Accepted→A / Rejected→B and updates job status out of `awaiting_triage`. | Step 1d machine includes `awaiting_triage` but §§3–4 never schedule the FR-13 triage action; without it, jobs stall or humans bypass the queue. | New 1g under §3 Increment 1 | Fixture: after R1 append, `triage` flips status from `awaiting_triage` to `pending` (next round) or `completed` |
| R1-S6 | Validation | medium | Extend 1f fixture tests to assert job status records write-confirmation + suggestion counts (FR-8d) and that dual-doc mode appends to both docs without mixing S/F prefixes. | Step 1f covers “temp markdown → R1 append → R2” but not the status write-back or dual-doc routing the requirements spike and FR-8(d) demand. | §3 Increment 1, step 1f | Assert status JSON has round id, S/F counts, paths; grep appendices for prefix isolation |

## Requirements Coverage Matrix — R1

| Requirement ID / Section | Plan section / step | Coverage | Notes |
| ---- | ---- | ---- | ---- |
| FR-1 Workflow-loop job envelope | §2 0a, 0e | Partial | Models + round-trip; typed CRP request fields not yet a plan step (see R1-S1) |
| FR-2 JobQueue patterns, not JobFile | §1 Approach; §2 0b; OQ-7 lean path | Covered | Sibling tree default stated |
| FR-3 Durable status / lease | §2 0a–0b; §6 3d | Partial | Persistence covered; lease/heartbeat deferred (R1-S4) |
| FR-4 Cursor skill + CLI | §2 0d; §3 1e | Partial | Skill planned; CLI incomplete vs cancel/drain/list-loops (R1-S2) |
| FR-5 Catalog-validated workflow jobs | §2 0c, 0e | Covered | discover + fail-closed tests |
| FR-6 Fail-closed missing artifacts | §2 0c, 0e | Covered | enqueue + unit tests; drain re-check implied via FR-6 map |
| FR-7 Loop recipe registry | §3 1a | Partial | `crp` registration; `list-loops` CLI not scheduled |
| FR-8 CRP cursor-agent executor | §3 1b–1f; §1 spike | Partial | Prompt/cache/append covered; status write-confirmation under-specified (R1-S6) |
| FR-9 CRP sdk-workflow executor | §4 1.1a–1.1c | Covered | Canonical request → workflow; no Cursor bundle as template |
| FR-10 Cite, don’t fork CRP | §8 Settled | Covered | Cite-only; no schema fork |
| FR-11 Derive round / coverage | §3 1b, 1f | Covered | Helper reuse + R1→R2 fixture |
| FR-12 Multi-round + stop | §3 1d | Partial | Step machine present; max_rounds/budget knobs not named as tasks |
| FR-13 Triage handoff | §3 1d | Gap | Status transition only; no triage action step (R1-S5) |
| FR-14 Resume / Mottainai | §3 1c, 1f | Covered | Content-hash cache + R2 fixture |
| FR-15 One-shot workflow jobs | §5 2a–2b | Covered | Recipe + priority list |
| FR-16 Dependency DAG | §5 2c | Covered | depends_on + cycle detection |
| FR-17 Observability | §6 3a | Covered | OTel/logs in harden |
| FR-18 Budget fail-closed | §6 3b | Covered | Budget wiring for sdk-workflow |
| FR-19 Experimental API | §6 3c; §1 code home | Covered | Export + docs |
| NR-1…NR-7 | §8 Settled | Covered | Do-not-relitigate aligns |
| OQ-5 Lease TTL | §6 3d | Partial | Deferred; conflicts with FR-3 early acceptance (R1-S4) |
| OQ-6 Reflective-reqs recipe | §6 3d | Partial | Deferred resolve only |
| OQ-7 Watch folder | §2 Default path | Covered (plan) / Conflict | Plan leans dedicated folder; requirements still list OQ-7 open |
| OQ-8 Current vs subagent | (none) | Gap | Affects FR-4 drain semantics; no plan lean |
| OQ-9 MCP backend | §5 2d | Partial | Optional Inc2 only |
