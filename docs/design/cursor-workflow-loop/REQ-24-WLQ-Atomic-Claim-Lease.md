# WLQ Atomic Claim Lease (option 2 / minimal) — Requirements

**Project:** startd8-sdk   **Criticality:** medium
**Version:** 0.5 (Post-audit — lacuna L-1/L-2/L-3 + survivorship footer fix folded; FR-7/FR-8 added)
**Date:** 2026-08-07
**Format:** det-req/0.1
**Backend:** spike-component
**Pairs with:** `PLAN-24-WLQ-Atomic-Claim-Lease.md`
**Inherits standards:** det-req-kit
**Precedes / grounds in:** `A1-WLQ-ATOMIC-CLAIM-NEXT-STEPS.md` (the build handoff); extends
`CURSOR_WORKFLOW_LOOP_REQUIREMENTS.md` **FR-3** (durable status + lease reclaim) + **OQ-5** (lease
TTL, resolved). Upstream ask: `OSS/Istio/analysis/CODE_ASKS_fleet_and_loop_REQ_PLAN_2026-08-04.md`
§A1 (option 2 = the FR-1/2/5 subset of the full A1). Pattern (rule 1):
`dev-os/multi-vendor-loop/docs/SURFACE_FLEET.md`.

## 0. Planning Insights (Self-Reflective Update)

> The v0.1 framing is the A1 handoff's §3/§4 ("extend the existing lease, atomicize it with
> `O_EXCL` over the lease field"). A code-grounding planning pass against the real WLQ surface
> (`queue.py`, `storage.py`, `models.py`, `file_operations.py`) falsified or sharpened **6**
> assumptions. The rate (>30%) confirms the handoff framing was a correct *direction* but premature
> as a spec — exactly what this loop is for.

| v0.1 Assumption (A1 handoff) | Planning Discovery (file / fact) | Impact |
|------------------------------|----------------------------------|--------|
| `O_CREAT\|O_EXCL` writes "over the existing lease field" | The lease lives *inside* the job envelope; `storage.job_path` **already exists** after `enqueue`, and `save_job` → `atomic_write_json` is **temp+rename, last-writer-wins** (`file_operations.py:174`) — not a CAS. You cannot `O_EXCL` a file that exists. | The CAS must be a **separate per-job sentinel file**; its `O_EXCL` *creation* is the compare-and-set. The lease field is only the *record* of who won. → **FR-1, FR-5** |
| "Extend the existing lease" is sufficient | The lease is **owner-less**: `lease_expires_at` (`models.py:346`) is a bare timestamp; there is **no** `surface_id`/owner anywhere on `WorkflowLoopJob`. | "Single holder" (FR-2) and "release by owner" (FR-4) are unenforceable without an owner. Add `lease_owner`. → **FR-5** |
| Reuse `reclaim_expired_leases` unchanged for stale takeover | `reclaim_expired_leases` (`queue.py:1274`) only nulls `lease_expires_at` + transitions to PENDING (`:1285`). It knows nothing of a sentinel. | With a sentinel CAS, an expired lease would be "reclaimed" in job state **while the sentinel still blocks every future claim** → permanent wedge. Reclaim **must also unlink the sentinel**. Same for every other `lease_expires_at = None` site (`:248` requeue, `:262`, `:1515` `_transition`). → **FR-3, FR-4** |
| A new `wloop claim` CLI verb closes the race | `run_next` already calls `reclaim_expired_leases()` then a **bare** `_transition(job, PROCESSING)` (`queue.py:317 → 332 → 442`). A CLI-only sentinel leaves the **direct `run-next` path's TOCTOU wide open**. | The CAS must be **internal to the acquire path `run_next` uses**; the `claim` verb is just an explicit entry to the same primitive. → **FR-6** |
| Use `O_EXCL` (vs the existing lock) — unmotivated | A fcntl `FileLock` already exists (`file_operations.py:183`). | Lock the rationale in: **fcntl advisory locks release on holder death**, which would defeat TTL takeover; an **`O_EXCL` sentinel persists** past a dead holder, so `reclaim_expired_leases` can steal it after `lease_ttl_seconds`. Choose sentinel, reject fcntl. → **FR-1 note, NR** |
| `exit 3, retryable` is a given | `cli_wloop.py` is Typer; exit codes are `typer.Exit(code=…)`, not implicit. | FR-2 must specify `typer.Exit(code=3)` and document 0=won / 3=held-retryable / non-3-nonzero=error so drainers can branch. → **FR-2** |

**Resolved open questions (from planning):**
- **OQ-A → Sentinel home = `storage.artifact_dir(job_id)/CLAIM.lock`.** The per-job artifact dir
  already exists (`storage.py:55`); the sentinel rides beside `drain-handoff.json` / `drain-result.json`,
  so cleanup and discovery are trivial and per-job-scoped (not per-root like the old `CLAIM.lock.claude`).
- **OQ-B → Local-filesystem assumption is explicit.** `O_EXCL` atomicity is guaranteed on local FS;
  NFS/`O_EXCL` is out of scope (NR). The queue root is a local `.startd8/` dir today.

### 0.1 Lessons-Learned Hardening (v0.3)

> Keyed Pattern-Catalog recall (`concurrency-primitive × file-lock`, `cli-verb × queue-op`,
> `model-field × lease`) returned empty → domain browse of `craft/Lessons_Learned/sdk/`. Two lessons
> changed the draft:

- **[Phantom-reference audit]** — grepped every symbol the spec names. Caught: the A1 handoff's
  `is_expired` does **not** exist — the model method is `lease_expired(now=…)` (`models.py:424`).
  Corrected here; all other refs verified live (see Reference-Audit below). This is why FR-3 cites
  `reclaim_expired_leases`/the TTL, not a method name.
- **[Single-source vocabulary ownership]** — WLQ **job state remains the one source of truth**; the
  `CLAIM.lock` sentinel and `lease_owner` are **derived records**, not a second authority. Reinforced
  in FR-4 by unlinking the sentinel + clearing `lease_owner` at *every* `lease_expires_at = None` site,
  so the sentinel can never drift out of sync with job state.
- **[Propagation gate]** *(build-time, carried to PLAN It-3, not a spec change)* — "PR merged ≠ tip on
  `main`"; verify the adapter adoption + board-deprecation actually reach `origin/main`.

**Reference-Audit** (every code symbol the spec names, grounded):

| Symbol / anchor | Status |
|-----------------|--------|
| `WorkflowLoopJob.lease_expires_at` `models.py:346` | ✅ exists |
| `lease_expired(now=…)` `models.py:424` | ✅ exists (**A1's `is_expired` was phantom**) |
| `LoopQueueConfig.lease_ttl_seconds` `models.py:443` | ✅ exists |
| `reclaim_expired_leases` `queue.py:1274` | ✅ exists |
| `run_next` acquire `queue.py:317/332/442` | ✅ exists (TOCTOU confirmed) |
| `cancel` `queue.py:230` · `requeue` `queue.py:238` · `_transition` `queue.py:1500/1515` | ✅ exist |
| `LoopQueueStorage.artifact_dir` `storage.py:55` · `save_job`→`atomic_write_json` `storage.py:92` | ✅ exist |
| `atomic_write_json` (temp+rename) `file_operations.py:174` · fcntl `FileLock` `:183` | ✅ exist |
| `wloop_app` Typer verbs `cli_wloop.py:38` | ✅ exists; `claim`/`release` **to-be-created** |
| `WorkflowLoopJob.lease_owner` | ⛔ **to-be-created** (FR-5) |
| `CLAIM.lock` sentinel + `claim_lock_path`/`try_acquire_sentinel` | ⛔ **to-be-created** (FR-1) |

### 0.2 Design-Principle Hardening (v0.3.1)

> Keyed lookup against `dev-os/PRINCIPLE-INDEX.md` §2 on this draft's decision-classes
> (`code × fail-loud/validation-gate`, `× single-source/no-drift`, `code × idempotency/reuse`). Four
> principles bore on the draft:

- **[Hayai — don't defer enforcement]** — mutual exclusion binds at the **earliest resolvable point**
  (the `O_EXCL` acquire), never a later scan/review. *Enforcer named:* the `O_EXCL` open itself + the
  cross-process contention test (PLAN It-2) — surfacing is not the gate, the failing-then-passing race
  test is.
- **[Mottainai — don't regenerate what exists]** — reuse `lease_expires_at`, `lease_ttl_seconds`,
  `reclaim_expired_leases`, `_transition`'s stamp, and `artifact_dir`; **no new engine, no lock
  server**. The whole premise of option 2. → Non-goals, FR-3/FR-5.
- **[Single-source / no-drift]** *(enforceable)* — job state is authoritative; the sentinel is derived.
  *Enforcer named:* the unified sentinel-cleanup wired into every `lease_expires_at = None` site
  (FR-4) — one code path keeps the two representations from ever diverging.
- **[Context-Correctness-by-Construction]** — `lease_owner` must **arrive**, not silently be `None`
  (else FR-2 single-holder and FR-4 owner-authority degrade to no-ops). → **sharpened FR-2/FR-5:
  `--surface` is required on `claim`; an acquire with no owner is rejected, not defaulted.**
- **[Accidental-Complexity]** — checked: the sentinel + one owner field is the single general rule;
  the fcntl alternative and a per-root allowlist were both rejected (Appendix B). No compensating
  layer added.

## Overview

`run_next`'s pending→processing claim is a TOCTOU: two drainers (e.g. two vendor surfaces) can both
read `PENDING`, both pass the check, and both write `processing` → double-drain. This adds one
**atomic claim primitive** — a per-job `O_EXCL` sentinel that is the compare-and-set — reusing the
SDK's existing lease state (`lease_expires_at`, `lease_ttl_seconds`, `reclaim_expired_leases`) and
adding only an owner field plus two CLI verbs. It is the multi-vendor fleet's **rule 1**. It is
**fleet-readiness, not a live-bug fix**: the race is dormant today (single-surface use + WIP=1), so
build it deliberately as the enabler of the intra-project vendor fleet, not a firefight.

## Objectives

- O-1: Exactly one drainer can hold a given job at a time — the pending→processing acquire is atomic
  across processes and across surfaces.
- O-2: An abandoned claim is recoverable without operator intervention — reused TTL reclaim, sentinel included.
- O-3: Zero new engines — extend the existing lease + queue; no lock server, no fleet-event, no renew.

## Risks

| Type | Description | Mitigation | Priority |
|------|-------------|------------|----------|
| quality | Orphaned sentinel wedges the queue (holder dies mid-claim) | FR-3: TTL reclaim unlinks the sentinel; local-FS `O_EXCL` + TTL bounds the wedge window | high |
| quality | CLI-only CAS leaves `run_next`'s internal path racy | FR-6: acquire is internal to the path `run_next` uses, not a bolt-on | high |
| safety | Non-owner releases someone else's live claim | FR-4: release checks recorded `lease_owner`; only owner or TTL-expired takeover may release | medium |
| availability | `O_EXCL` semantics on NFS/network FS | NR + OQ-B: local-filesystem assumption stated; NFS out of scope | low |

## Profile

Declared profile: **internal**

## Functional requirements

- **FR-1 — Atomic acquire (CAS via sentinel).** Acquiring a `PENDING` job creates
  `storage.artifact_dir(job_id)/CLAIM.lock` via `O_CREAT|O_EXCL` (a separate sentinel, **never** the
  job envelope); on success it stamps `lease_owner=<surface_id>` + `lease_expires_at` (reusing
  `_transition`'s existing stamp) — never read-then-write. **The `O_EXCL` create is positioned at the
  single `_transition`-INTO-`PROCESSING` chokepoint (`queue.py:1509-1512`, where the lease is stamped)
  [L-2]** — symmetric to FR-4's cleanup at the `_transition`-OUT branch (`:1515`) — so **every** acquire
  path is covered by one gate, not just `run_next`'s (see FR-6 for the five sites). Note: sentinel chosen over the existing
  fcntl `FileLock` because the sentinel survives holder death (required by FR-3). **Ordering is
  mandatory: sentinel-first (the `O_EXCL` create is the CAS gate), then stamp** — reversing it would
  let two racers both stamp the last-writer-wins job file and reopen the TOCTOU. The sentinel content
  is `{"owner": "<surface_id>", "acquired_at": "<UTC ISO-8601>"}` (valid UTF-8 JSON, for
  diagnosability + owner-checked release per FR-4) **[R1-S3]**. The crash window between the `O_EXCL`
  create and `save_job` (two separate FS ops) is handled by FR-3's orphan sweep, not by ordering.
  Touches: `src/startd8/workflows/loop_queue/queue.py` (claim path),
  `src/startd8/workflows/loop_queue/storage.py` (sentinel path helper). Verify: two processes race one
  `PENDING` job → exactly one `CLAIM.lock` created, one `won`, one non-zero.
- **FR-2 — Single holder.** A second `claim` on a job whose sentinel exists and whose lease is not
  expired returns `typer.Exit(code=3)` (retryable); exit codes: `0`=won, `3`=held-retryable,
  other-nonzero=error. `--surface <sid>` is **required** (no default) — an acquire with no owner is
  rejected, so `lease_owner` can never be `None` on a held job (CCbC). Touches:
  `src/startd8/cli_wloop.py` (`claim` verb), `src/startd8/workflows/loop_queue/queue.py`. Verify: a
  held job's second `claim` exits `3`; a `claim` with no `--surface` exits non-zero (never acquires).
- **FR-3 — Stale reclaim + sentinel cleanup + orphan sweep (extends existing).** A lease past
  `lease_ttl_seconds` is reclaimable via the existing `reclaim_expired_leases`, **and that reclaim now
  also unlinks the orphaned `CLAIM.lock`** so the next `claim` can win. **Reclaim must additionally
  sweep crash-orphaned sentinels [R1-F1/R1-S4]:** a `CLAIM.lock` whose job is not in a validly-held
  state — job is `PENDING` (crash before `save_job`), or `PROCESSING` with `lease_expires_at` absent or
  expired — is an orphan and is unlinked (+ `lease_owner` cleared). This is required because
  `lease_expired()` returns `False` when `lease_expires_at` is `None` (`models.py:425`), so a
  bare-timestamp check alone would never reclaim a crash-orphan → permanent wedge. `0` disables
  automatic reclaim (unchanged); **when TTL=0, `wloop requeue --job-id <id>` is the manual recovery
  primitive** (it also unlinks the sentinel per FR-4) **[R1-F3]**. Touches:
  `src/startd8/workflows/loop_queue/queue.py:1274`. Verify: (a) an expired lease → reclaim removes the
  sentinel and the next `claim` wins; (b) a sentinel present with `lease_expires_at=None` on a
  `PENDING`/`PROCESSING` job → reclaim unlinks it and the next `claim` wins.
- **FR-4 — Release + owner authority.** `startd8 wloop release --job-id <id>` (auto on `run-next`
  consume / `complete_drain`) unlinks the sentinel and clears `lease_owner`; only the recorded
  `lease_owner` (or a TTL-expired takeover) may release; WLQ job state is the single source of truth.
  **Sentinel unlink is wired at the single chokepoint — `_transition`'s non-PROCESSING branch
  (`queue.py:1515`), through which every status change flows — not per-call-site [R1-F5].** The
  `lease_expires_at = None` sites (`queue.py:248` awaiting-triage→pending, `:262` general requeue,
  `:1285` reclaim, `:1515` `_transition`) all route through `_transition`, so one enforcement point
  covers `requeue`/`cancel`/`complete_drain`/reclaim transitively; the enumeration is a completeness
  audit, not a per-site wiring mandate. **Note the flip side: this same transitive unlink is what lets
  `cancel`/`requeue` release *another surface's* claim — governed by FR-7's operator-override rule.** **A non-owner `release` raises `LoopQueueValidationError`
  (internal) / exits non-zero with a descriptive message (CLI) and logs at WARNING with `job_id` +
  attempting owner [R1-F4].** **To avoid a release-vs-reacquire TOCTOU [R1-S5]** — after TTL expiry a
  second surface may hold a fresh sentinel — `release` unlinks **only** when the on-disk sentinel's
  `owner` field matches the caller (not merely the job-state `lease_owner`), so a late owner cannot
  unlink the new holder's sentinel. Touches: `src/startd8/cli_wloop.py` (`release` verb),
  `src/startd8/workflows/loop_queue/queue.py`. Verify: consume releases + removes sentinel; a
  non-owner `release` raises `LoopQueueValidationError` + is logged; after a TTL takeover, the prior
  owner's late `release` leaves the new holder's sentinel intact; direct status writes are not the
  claim path.
- **FR-5 — Owner-stamped lease field.** Add `lease_owner: Optional[str] = None` to `WorkflowLoopJob`;
  stamped on acquire, cleared on release/reclaim. Touches:
  `src/startd8/workflows/loop_queue/models.py:346`. Verify: an acquired job serializes
  `lease_owner=<surface_id>`; a released/reclaimed job serializes `lease_owner=None`.
- **FR-6 — Every acquire path closes the TOCTOU (not just `run_next`) [L-2].** There are **five**
  `_transition(…PROCESSING)` acquire sites — `run_next`:442, `_drain_reflective_agent_surface`:512,
  `_drain_research_agent_surface`:571, and the **public** `drain_sdk_workflow`:614 + `drain_one_shot`:733.
  Because the CAS lives at the `_transition` chokepoint (FR-1), **all five** are race-safe, including
  direct programmatic callers of the public `drain_*` methods — guarding only `run_next`'s line 442
  would leave four acquire paths open. **On a lost CAS, the acquire returns `None` / raises
  `LoopQueueValidationError` (typed contract for programmatic callers, distinct from the CLI's
  `typer.Exit(3)`) [R1-F2].** **The already-`PROCESSING` consume branch (`queue.py:319→325`) must also
  check ownership [R1-S2]:** it currently calls `complete_drain` unconditionally, letting a
  non-owning surface consume another surface's in-flight job; it must reject/skip when `lease_owner`
  is set and does not match the caller's surface. Touches:
  `src/startd8/workflows/loop_queue/queue.py` (the `_transition` chokepoint + the `:319` consume branch).
  Verify: (a) two concurrent `run-next` on one `PENDING` job → exactly one drains, the other gets
  `None`; (b) the same holds for a direct `drain_sdk_workflow`/`drain_one_shot` race (all five sites);
  (c) surface B calling `run_next` on a job held `PROCESSING` by surface A does not consume it.
- **FR-7 — Recovery verbs are privileged operator-overrides, not silent theft [L-1].** `cancel`
  (`queue.py:230`) and `requeue` (`:238`) also transition off `PROCESSING` and thus release the claim,
  but take no owner — so absent a rule, surface B could `requeue` surface A's live job and steal it,
  bypassing FR-1. Resolution: `cancel`/`requeue` are **operator recovery verbs** that *may* forcibly
  release a live claim, but (a) the forced release of a **held** job (live, non-expired lease with a
  different `lease_owner`) logs a **WARNING** naming the displaced owner, and (b) they are **not** part
  of the automated drain path — adapters (It-3) use `claim`/`release` only, never `cancel`/`requeue`.
  This makes the override intentional, observable, and scoped rather than a silent claim-theft hole.
  Touches: `src/startd8/workflows/loop_queue/queue.py` (`cancel`, `requeue`),
  `src/startd8/cli_wloop.py`. Verify: `requeue`/`cancel` on a job held by another surface succeeds but
  emits a WARNING with the displaced owner; the drain adapters call neither.
- **FR-8 — The holder is observable (read path) [L-3].** `lease_owner` + `acquired_at` are written
  (FR-1/FR-5) and must be **readable**: `startd8 wloop status` surfaces, per held job, who holds it
  (`lease_owner`) and since when (`acquired_at`) — a written-but-unsurfaced owner is a built-but-unwired
  value path; a multi-surface fleet is inoperable if you cannot see who holds what. Touches:
  `src/startd8/cli_wloop.py` (`status`), `src/startd8/workflows/loop_queue/queue.py`. Verify: `wloop
  status` on a held job shows `lease_owner` + `acquired_at`; on a free job shows unheld.

## Non-goals

- `renew` / heartbeat lease extension (full A1).
- The `CLAIM{won|lost}` **Fleet Event** (`contextcore fleet emit` — A3).
- `blind_rotate` / `depends_on` **acquire guards** (FR-4 of the code-asks — full A1).
- A new lock server or daemon; a second ledger; any fcntl-based lock (rejected — see FR-1).
- NFS / network-filesystem `O_EXCL` correctness (local-FS queue root only — OQ-B).

## Owned fields

Only humans enter: none. `lease_owner` is **machine-stamped** from the caller's `--surface <sid>`;
never hand-authored into a job file.

## Contract projection

- **Backend:** spike-component
- **Vocabulary home (cite):** `src/startd8/workflows/loop_queue/models.py` (`WorkflowLoopJob`,
  `LoopQueueConfig`, `LoopJobStatus`); `src/startd8/cli_wloop.py` (`wloop_app` Typer verbs).

| Entry (name) | Kind | Words/Structure | Notes |
|--------------|------|-----------------|-------|
| `WorkflowLoopJob.lease_owner` | field | structure | new `Optional[str]`; drift-hashed |
| `CLAIM.lock` sentinel | file path | structure | `storage.artifact_dir(job_id)/CLAIM.lock`; `O_EXCL` = CAS; content `{"owner","acquired_at"}` UTC-ISO JSON |
| `wloop claim` | cli-verb | structure | `--job-id`, `--surface`; exit 0/3/other |
| `wloop release` | cli-verb | structure | `--job-id`; owner-checked |
| `reclaim_expired_leases` (extended) | queue-op | structure | now also unlinks sentinel |

---

## Appendix A — Accepted (with where merged)

_(none yet — pre-CRP)_

## Appendix B — Rejected (with rationale)

- **fcntl `FileLock` for the CAS** — rejected: advisory locks release on holder death, defeating TTL
  takeover (FR-3). The `O_EXCL` sentinel persists past death so reclaim can steal it. (planning, v0.2)

## Appendix C — Incoming review rounds

CRP Round 1 (claude-sonnet-4-6, 2026-08-07) landed under the **Iterative Review Log → Appendix C**
below; dispositions recorded in that log's Appendix A. All 5 F-suggestions accepted into FR-1/3/4/6.

---

*v0.2 — Post-planning self-reflective update. 6 assumptions corrected (1 CAS-target, 1 owner-field,
1 reclaim-cleanup, 1 run_next-internal, 1 fcntl-rationale, 1 exit-code), 2 open questions resolved,
1 requirement added (FR-6). — v0.3 — Applied 2 lessons (phantom-reference audit → caught A1's
`is_expired`; single-source vocabulary), reference-audit table added. — v0.3.1 — Applied 4 principles
(Hayai, Mottainai, single-source/no-drift, CCbC → `--surface` required; Accidental-Complexity checked).
— v0.4 — Post-CRP R1: 5 requirements suggestions accepted (crash-window orphan sweep, run_next
return-contract + consume-branch owner check, TTL=0 recovery, non-owner release contract, `_transition`
chokepoint). — v0.5 — Post-audit (lacuna + survivorship): L-1 claim-theft → FR-7 (recovery verbs are
scoped operator-overrides); L-2 CAS-on-1-of-5-sites → FR-1/FR-6 move the CAS to the `_transition`
chokepoint; L-3 no read path → FR-8 (`wloop status` shows holder). **Status: CRP-hardened + audited,
NOT yet implementation-ready — PLAN coverage is Partial on 6 FRs and FR-7/FR-8 need iteration steps;
build after PLAN-24 v0.5 closes those.** (Survivorship: the v0.4 "Ready for implementation" marker was
a false green, contradicted by the plan's own Partial coverage matrix — corrected here.)*

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
| R1-F1 | Crash-window orphan: reclaim must detect sentinel-without-lease | CRP R1 | Merged into **FR-3** orphan sweep (sentinel present + job PENDING or PROCESSING-with-absent/expired-lease → unlink). Grounded: `lease_expired()` returns False on `None` (`models.py:425`) — verified. | 2026-08-07 |
| R1-F2 | `run_next` programmatic contract on lost CAS | CRP R1 | Merged into **FR-6**: `run_next` returns `None` on lost CAS (distinct from CLI `typer.Exit(3)`). | 2026-08-07 |
| R1-F3 | TTL=0 disables reclaim → document manual recovery | CRP R1 | Merged into **FR-3**: `wloop requeue` is the recovery primitive when TTL=0. | 2026-08-07 |
| R1-F4 | Non-owner release error type + logging | CRP R1 | Merged into **FR-4**: `LoopQueueValidationError` (internal) / non-zero + WARNING log (CLI). | 2026-08-07 |
| R1-F5 | Wire sentinel unlink at `_transition` chokepoint, not per-site | CRP R1 | Merged into **FR-4**: single enforcement point at `queue.py:1515`; enumeration is a completeness audit. Line refs corrected to 248/262/1285/1515 (see R1-S8). | 2026-08-07 |
| L-1 | Claim-theft: `cancel`/`requeue` unlink another surface's sentinel with no owner check | Lacuna audit | New **FR-7**: recovery verbs are scoped operator-overrides — WARNING on forced release of a held job; excluded from the automated drain path. Verified in code (queue.py:230/238 take no owner). | 2026-08-07 |
| L-2 | CAS guards only 1 of 5 `_transition(PROCESSING)` acquire sites | Lacuna audit | **FR-1/FR-6** rewritten: CAS positioned at the `_transition`-INTO-PROCESSING chokepoint (queue.py:1509-1512), covering run_next + drain_sdk_workflow + drain_one_shot + 2 `_drain_*` helpers. Verified 5 sites (442/512/571/614/733). | 2026-08-07 |
| L-3 | `lease_owner`/sentinel written but no read path | Lacuna audit | New **FR-8**: `wloop status` surfaces holder + `acquired_at`. Verified no lease_owner read in cli_wloop.py. | 2026-08-07 |
| SURV-1 | "Ready for implementation" footer was a false green | Survivorship audit | Footer corrected: status is CRP-hardened + audited, NOT yet impl-ready (contradicted by the plan's own 6-Partial coverage matrix). | 2026-08-07 |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none yet) |  |  |  |  |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — claude-sonnet-4-6 — 2026-08-08 00:45:00 UTC

- **Reviewer**: claude-sonnet-4-6
- **Date**: 2026-08-08 00:45:00 UTC
- **Scope**: Concurrency semantics, sentinel lifecycle, acceptance criteria completeness, owner-authority edge cases (Feature Requirements)

**Executive summary:**

- FR-1's ordering note says "sentinel-first, then stamp" but does not address the crash window between `O_EXCL` success and the subsequent `save_job` (temp+rename), which can leave `lease_expires_at` absent and the orphan undetectable by reclaim.
- FR-2's Verify clause checks "a held job's second `claim` exits 3" but does not specify what the `run_next`-internal path returns/raises when it loses the CAS — implementers may not know whether to return `None`, raise, or return the losing job.
- FR-3's `0 disables` clause is carried over from the parent OQ-5 requirement, but the interaction with the sentinel is underspecified: when `lease_ttl_seconds=0`, `reclaim_expired_leases` is skipped entirely and an orphaned sentinel from a crashed holder is permanently wedged with no recovery path.
- FR-4 does not specify what error code or exception type is raised when a non-owner calls `release` — implementers lack a contract for what callers should catch.
- FR-4's enumeration of `lease_expires_at = None` sites cites `queue.py:248` requeue and `:262` — but also says `:1515` and `complete_drain` and `cancel`. The code shows `_transition` at line 1515 clears `lease_expires_at` for ALL non-PROCESSING transitions, meaning sentinel unlink is already covered transitively via `_transition` for most sites; the spec should clarify which sites route through `_transition` vs. bypass it.

#### Feature Requirements Suggestions

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F1 | Risks | high | Add an explicit acceptance criterion to FR-1 covering the crash window: "if the process dies after `O_EXCL` succeeds but before `save_job` completes, a subsequent `reclaim_expired_leases` call must detect and unlink the orphaned sentinel." | FR-1 Verify clause says "two processes race one `PENDING` job → exactly one `CLAIM.lock` created, one `won`, one non-zero." This tests the happy race path but not the crash-after-acquire path. `lease_expired()` at `models.py:424` returns `False` when `lease_expires_at` is `None`, so an orphan with a missing expiry is never reclaimed (permanent wedge). The design must specify how reclaim handles this case. | FR-1 — Verify clause; cross-reference FR-3 | Add test: sentinel present, job status=PROCESSING, `lease_expires_at=None` — assert `reclaim_expired_leases` unlinks the sentinel and requeues the job. |
| R1-F2 | Interfaces | high | FR-6's Verify clause specifies "the other raises/exits non-zero" but does not distinguish between what `run_next` raises vs. what it returns when `_try_claim` returns False in the internal CAS path. For programmatic callers of `run_next` (not the CLI), the exception type or return value is the contract. | FR-2 specifies `typer.Exit(code=3)` for the CLI verb. FR-6 covers `run_next` internally but says only "raises/exits non-zero." Callers of `WorkflowLoopQueue.run_next()` need to know whether to catch `LoopQueueValidationError`, `LoopQueueBlockedError`, or check a return value. Without a typed contract, integrators will write catch-all handlers. | FR-6 — Verify clause; also Contract projection table | Add: "`run_next` returns `None` (or raises `LoopQueueValidationError`) when `_try_claim` returns False — specify which, and add it to the Contract projection table." Verify: unit test that calls `queue.run_next()` when another process holds the sentinel — assert the correct exception type (not `typer.Exit`). |
| R1-F3 | Risks | medium | FR-3 states "`0` disables (unchanged)" — but with the sentinel in place, `lease_ttl_seconds=0` disables reclaim entirely and orphaned sentinels from crashed holders become permanent wedges with no operator recovery path. The requirement should specify the manual recovery mechanism for sentinel orphans when TTL is disabled. | FR-3 inherits the `0 disables` behavior from the parent OQ-5 requirement. The parent's TTL=0 meant "no automatic reclaim; use explicit requeue." With sentinels added, `requeue` now also must unlink the sentinel (It-1 step 6 covers this), so manual `requeue` is the recovery. But FR-3 does not say this — operators running TTL=0 may not know that `wloop requeue` is the recovery primitive. | FR-3 — body prose | Add: "When `lease_ttl_seconds=0`, automatic reclaim is disabled; sentinel orphans from crashed holders must be recovered via `wloop requeue --job-id <id>` (which also unlinks the sentinel per FR-4)." |
| R1-F4 | Security | medium | FR-4 does not specify the error type or message returned when a non-owner calls `release`. The "rejected" outcome is behaviorally specified but not typed — callers cannot write precise exception handlers. | FR-4 Verify clause says "a non-owner `release` is rejected" but does not specify whether this is `LoopQueueValidationError`, `typer.Exit(code=1)` (CLI), or a silent no-op. A non-owner could be a bug (wrong surface ID) or an attack (spoofed surface ID); the response should be consistent and loggable. | FR-4 — Verify clause | Specify: "non-owner `release` raises `LoopQueueValidationError` (internal) / exits non-zero with a descriptive message (CLI); the rejection is logged at WARNING level with job_id and attempting owner." Verify: unit test catches the correct exception type with a specific message. |
| R1-F5 | Architecture | medium | FR-4 enumerates `lease_expires_at = None` sites but conflates sites that go through `_transition` (which clears the lease at line 1515 for all non-PROCESSING statuses) with sites that bypass it. `complete_drain` and `cancel` both ultimately call `_transition`, which already nulls `lease_expires_at` — the sentinel unlink only needs to be added at `_transition`'s non-PROCESSING branch, not at each call site individually. This is a potential source of missed-site bugs if the spec implies per-site wiring. | FR-4: "Every `lease_expires_at = None` site (`queue.py:248` requeue, `:262`, `:1515`, `complete_drain`, `cancel`) also unlinks the sentinel." `_transition` at line 1500–1515 is the single chokepoint for all status changes; line 1515 sets `lease_expires_at = None` for every non-PROCESSING transition. Wiring `release_sentinel` into `_transition` at line 1515 covers all downstream callers transitively. The spec should clarify whether the implementation wires at `_transition` (preferred, fewer sites) or at each call site. | FR-4 — body prose; cross-reference It-1 step 6 | Clarify: "Preferred implementation: wire `release_sentinel` + `lease_owner=None` into `_transition`'s non-PROCESSING branch (line 1515) as the single enforcement point; the per-site enumeration above is a completeness audit, not a per-site wiring mandate." Add a test that exercises a non-enumerated status transition and asserts the sentinel is cleaned up. |
