# PLAN-24 — WLQ Atomic Claim Lease (option 2 / minimal)

**Pairs with:** `REQ-24-WLQ-Atomic-Claim-Lease.md` (v0.5)
**Date:** 2026-08-07   **Status:** **It-1 + It-2 BUILT & GREEN (2026-08-08)** · It-3 (adapter adoption) pending · post-CRP R1 + post-audit (L-1/L-2/L-3 → steps 7/8 + chokepoint reposition)

> **It-1/It-2 build record (2026-08-08):** CAS at the `_transition` chokepoint (`queue.py`), `lease_owner`
> field (`models.py`), sentinel helpers (`storage.py`), `claim`/`release` CLI verbs + exit-3 mapping
> (`cli_wloop.py`), reclaim orphan-sweep, FR-7 override warnings, FR-8 read path. Contention suite
> `tests/unit/workflows/loop_queue/test_atomic_claim.py` (12 tests incl. 2 cross-process races) — **all
> green; 113/113 loop_queue tests pass, no regressions.**

> Iterations are dependency-ordered and acyclic. It-1 builds the primitive; It-2 proves it closes the
> TOCTOU; It-3 adopts it in the adapters. Each iteration ends green (tests pass) before the next.

## It-1 — The CAS primitive + model field + CLI verbs  →  FR-1, FR-2, FR-5, FR-6

1. **Model (FR-5).** Add `lease_owner: Optional[str] = None` to `WorkflowLoopJob`
   (`models.py:346`, beside `lease_expires_at`). No migration — additive optional field; existing job
   files deserialize with `lease_owner=None`.
2. **Sentinel helper (FR-1).** Add `claim_lock_path(job_id) -> Path` to `LoopQueueStorage`
   (`storage.py`, beside `handoff_path`/`result_path`) → `artifact_dir(job_id)/wlq-claim.lock`. Add
   `try_acquire_sentinel(job_id, owner, *, dry_run=False) -> bool` (os.open `O_CREAT|O_EXCL|O_WRONLY`,
   write the sentinel schema **`{"owner": "<surface_id>", "acquired_at": "<UTC ISO-8601>"}`** as valid
   UTF-8 JSON, close; `FileExistsError` → `False`) **[R1-S3]** and `release_sentinel(job_id, *,
   expected_owner=None)` (read sentinel; if `expected_owner` given and the on-disk `owner` differs,
   do **not** unlink — return False; else unlink with `missing_ok=True`). **`missing_ok=True` is
   intentional and load-bearing — release and reclaim can race on expiry, both must succeed [R1-S7].**
   **Dry-run guard [R1-S6]:** when `dry_run=True`, skip the real `os.open` and return `True` (probe
   success) — else a `--dry-run` claim leaks a real sentinel that blocks the next real claim
   (`save_job` already no-ops on dry-run, `storage.py:76`). Ensure `artifact_dir` exists before the
   `O_EXCL` open.
3. **Acquire at the `_transition` chokepoint — covers all 5 sites (FR-1, FR-6) [L-2].** Position the
   CAS **inside `_transition`, at the INTO-`PROCESSING` branch (`queue.py:1509-1512`, where the lease
   is stamped)**, symmetric to the OUT-branch cleanup (step 6). On a `→PROCESSING` transition,
   `_transition` first `try_acquire_sentinel(job, owner)`; on success it stamps `lease_expires_at` +
   `lease_owner`; **on failure it raises `LoopQueueValidationError`** (callers translate: CLI → exit-3,
   `run_next` → `None` [R1-F2]). This covers **all five** acquire sites at once — `run_next`:442,
   `_drain_reflective_agent_surface`:512, `_drain_research_agent_surface`:571, `drain_sdk_workflow`:614,
   `drain_one_shot`:733 — not just `run_next` (guarding only :442 would leave four open). `_transition`
   needs an `owner` parameter threaded from the drain caller. **Also guard the already-`PROCESSING`
   consume branch (`queue.py:319→325`) [R1-S2]:** it calls `complete_drain` unconditionally — reject/skip
   when `job.lease_owner` is set and ≠ caller's surface. Keep the leading `reclaim_expired_leases()`
   call (`:317`) — reclaim now clears stale + orphaned sentinels (step 5).
4. **CLI verbs (FR-1, FR-2).** Add `@wloop_app.command("claim")` (`--job-id`, `--surface`) and
   `release` (`--job-id`) to `cli_wloop.py`. `claim`: `_try_claim` True → print `won`, exit 0; False →
   if lease live `raise typer.Exit(3)`, else surface the error. `release`: FR-4 (It-1 step 6).
5. **Reclaim cleanup + orphan sweep (FR-3).** In `reclaim_expired_leases` (`queue.py:1274`): for an
   expired lease, `release_sentinel(job.job_id)` + clear `lease_owner` before transitioning to PENDING.
   **Add an orphan sweep [R1-F1/R1-S4]:** because `lease_expired()` returns `False` when
   `lease_expires_at` is `None` (`models.py:425`), a crash between `O_EXCL` create and `save_job`
   leaves a sentinel whose job is `PENDING` (or `PROCESSING` with no lease) that TTL alone never
   reclaims → permanent wedge. Sweep: for each existing `wlq-claim.lock`, if its job is not validly held
   (job `PENDING`, or `PROCESSING` with absent/expired `lease_expires_at`), unlink the sentinel +
   clear `lease_owner`. Keep sentinel-first acquire ordering (step 3) — reversing it would reopen the
   TOCTOU; the orphan sweep, not ordering, is the crash-window remedy.
6. **Release + authority (FR-4).** `release(job_id, owner=None)`: reject with `LoopQueueValidationError`
   + WARNING log (`job_id` + attempting owner) if `job.lease_owner` set and `owner != job.lease_owner`
   and lease not expired **[R1-F4]**; else `release_sentinel(job_id, expected_owner=owner)` (which
   won't unlink a *different* owner's fresh sentinel after a TTL takeover **[R1-S5]**) + clear
   `lease_owner` + transition off PROCESSING. **Single chokepoint [R1-F5]:** wire `release_sentinel` +
   `lease_owner=None` into **`_transition`'s non-PROCESSING branch (`queue.py:1515`)** — every status
   change flows through `_transition`, so `complete_drain`, `cancel`, `requeue`, and reclaim are
   covered transitively. Correct site refs (were `:238/:248`): `lease_expires_at = None` lives at
   `queue.py:248` (awaiting-triage→pending), `:262` (general requeue), `:1285` (reclaim), `:1515`
   (`_transition`) **[R1-S8]**; a `grep -n 'lease_expires_at\s*=\s*None' queue.py` pre-commit check
   confirms no site is added later without cleanup.

7. **Recovery-verb override + logging (FR-7) [L-1].** In `cancel` (`queue.py:230`) / `requeue` (`:238`):
   when the target job is held (live, non-expired lease with a set `lease_owner`), the forced release
   logs a **WARNING** naming the displaced owner (the unlink itself already flows through the step-6
   chokepoint). Do **not** add these verbs to any adapter drain path (It-3 uses `claim`/`release` only).
8. **Observable holder (FR-8) [L-3].** Extend `wloop status` (`cli_wloop.py:109`) to surface, per held
   job, `lease_owner` + `acquired_at` (read from job state / sentinel). No new query path — additive
   render of fields already written in step 3.

## It-2 — Contention test (the acceptance that proves the TOCTOU is closed)  →  FR-1, FR-2, FR-3, FR-6, FR-7, FR-8

- **Cross-process race (FR-1/FR-6).** `tests/unit/workflows/loop_queue/test_atomic_claim.py`: enqueue
  one PENDING job in a temp queue root; spawn **two `multiprocessing.Process`** workers that both call
  `claim` (and a second test: both call `run_next`). **Use a `multiprocessing.Barrier(2)` — each worker
  calls `barrier.wait()` immediately before the acquire so both hit `try_acquire_sentinel`
  concurrently [R1-S1].** Without the barrier one process finishes before the other starts and the
  TOCTOU window is never exercised → structural false green. Assert **exactly one** wins, one gets
  exit-3 / `None`, and exactly one `wlq-claim.lock` exists. Processes not threads — the primitive is
  cross-process.
- **Single-holder (FR-2).** Second `claim` on a held job exits 3; a `claim` with no `--surface` exits
  non-zero and creates no sentinel.
- **Stale reclaim (FR-3).** Set `lease_ttl_seconds` small (or backdate `lease_expires_at`); assert
  reclaim removes the sentinel and a subsequent `claim` wins.
- **Crash-orphan sweep (FR-3) [R1-F1/R1-S4].** Fabricate a sentinel with the job left `PENDING` (and a
  variant: `PROCESSING` with `lease_expires_at=None`); assert `reclaim_expired_leases` unlinks it and
  the next `claim` wins (guards the permanent-wedge case).
- **Happy-path cleanup (FR-4) [R1-S9].** After a full `run_next` → drain → consume cycle, assert
  `wlq-claim.lock` is gone and `lease_owner is None` (catches sentinel leak on the normal
  `complete_drain → _transition` path).
- **Owner-authority (FR-4) [R1-S2/R1-S5].** (a) surface B `run_next` on a job held by surface A does
  not consume it; (b) after TTL takeover by B, A's late `release` leaves B's sentinel intact.
- **Dry-run no-leak (FR-2) [R1-S6].** `claim --dry-run` leaves no `wlq-claim.lock` on disk.
- **All-5-acquire-sites gated (FR-6) [L-2].** A direct `drain_sdk_workflow`/`drain_one_shot` race (not
  via `run_next`) → exactly one wins; asserts the chokepoint covers non-`run_next` paths.
- **Recovery-verb override (FR-7) [L-1].** `requeue`/`cancel` on a job held by another surface succeeds
  and emits a WARNING naming the displaced owner.
- **Observable holder (FR-8) [L-3].** `wloop status` on a held job shows `lease_owner` + `acquired_at`.
- **Mixed-surface temp-queue contention** (acceptance): two distinct `--surface` ids racing one job →
  exactly one `won`.

## It-3 — Adapter adoption + board deprecation  →  FR-4 (authority)

- `drain-claude` / codex adapters call `wloop claim --job-id --surface` **before** drain, replacing the
  per-surface single-flight lock as the *cross-surface* primitive; `release` (or `run-next` consume) on
  completion.
- Deprecate any `CLAIMED_BY.*` / `CLAIM.lock.claude` per-root convention in the board §2 (it is
  per-surface-per-root and does not serialize across surfaces — superseded by the per-job sentinel).
- Update `codex-loop/REQ-01` note: "until an upstream atomic claim contract is available" → **A1
  option 2 IS that contract** (this REQ).

## Acceptance (whole)

Two surfaces racing one job → exactly one `won`; stale lease reclaimed **and its sentinel removed**
after expiry; a mixed-surface temp-queue contention test passes; `run-next` direct path is race-safe.

## Traceability

| FR | Iteration(s) |
|----|--------------|
| FR-1 Atomic acquire (CAS) | It-1 (2,3,4), It-2 |
| FR-2 Single holder | It-1 (4), It-2 |
| FR-3 Stale reclaim + sentinel cleanup | It-1 (5), It-2 |
| FR-4 Release + owner authority | It-1 (6), It-3 |
| FR-5 Owner-stamped lease field | It-1 (1) |
| FR-6 all-acquire-sites close TOCTOU | It-1 (3), It-2 |
| FR-7 recovery verbs are scoped overrides | It-1 (7), It-2, It-3 |
| FR-8 observable holder (read path) | It-1 (8), It-2 |

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
| R1-S1 | `multiprocessing.Barrier` in race test | CRP R1 | It-2 cross-process race: barrier before acquire (prevents false green). | 2026-08-07 |
| R1-S2 | `run_next` consume branch owner check | CRP R1 | It-1 step 3 + REQ FR-6; It-2 owner-authority test (a). Verified branch at `queue.py:319→325` is unconditional. | 2026-08-07 |
| R1-S3 | Precise sentinel schema | CRP R1 | It-1 step 2 + REQ contract projection: `{"owner","acquired_at":UTC-ISO}` JSON. | 2026-08-07 |
| R1-S4 | Crash-window orphan (sentinel w/o lease) | CRP R1 | It-1 step 5 orphan sweep + REQ FR-3; It-2 crash-orphan test. Grounded: `lease_expired()==False` on `None`. | 2026-08-07 |
| R1-S5 | Release-vs-reacquire TOCTOU | CRP R1 | It-1 steps 2+6: `release_sentinel(expected_owner=)` checks on-disk owner; It-2 owner-authority test (b). | 2026-08-07 |
| R1-S6 | Dry-run sentinel leak | CRP R1 | It-1 step 2 dry-run guard; It-2 dry-run-no-leak test. | 2026-08-07 |
| R1-S7 | Document `missing_ok` intentional | CRP R1 | It-1 step 2 annotation (release/reclaim race). | 2026-08-07 |
| R1-S8 | Requeue line refs off-by-N | CRP R1 | It-1 step 6: corrected to 248/262/1285/1515 + grep pre-commit; REQ reference-audit already correct. | 2026-08-07 |
| R1-S9 | Happy-path cleanup test | CRP R1 | It-2 happy-path cleanup bullet. | 2026-08-07 |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none yet) |  |  |  |  |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — claude-sonnet-4-6 — 2026-08-08 00:45:00 UTC

- **Reviewer**: claude-sonnet-4-6
- **Date**: 2026-08-08 00:45:00 UTC
- **Scope**: Concurrency semantics, sentinel lifecycle, test design, cross-process race, owner-authority edge cases

**Executive summary:**

- The sentinel-first ordering in step 3 is correct (acquire before stamping), but a crash window between sentinel creation and `save_job` completion leaves the job in a state where `lease_expired()` reads a stale (or missing) `lease_expires_at` — reclaim may fail to detect the orphan.
- The plan's `_try_claim` design closes the TOCTOU for `run_next`, but the `run_next → complete_drain` branch (line 325) fires without checking `lease_owner`, allowing a non-owning surface to consume a PROCESSING job.
- The It-2 race test has no synchronization barrier between the two spawned processes; without one, the first process will typically acquire before the second starts, making the test a structural false green.
- The release-guard logic correctly rejects non-owners via job-state check, but there is a TOCTOU between the ownership check passing (because lease appears expired) and `release_sentinel` unlinking — a newly acquired sentinel by a second winner could be unlinked.
- The plan's `requeue` line reference (``:238/:248``) does not match the actual code: `lease_expires_at = None` appears at lines 248 and 262 (not 238 and 248), suggesting one site is the `AWAITING_TRIAGE → PENDING` path and one is the general requeue; both need sentinel cleanup.
- `try_acquire_sentinel` writes `{owner, ts}` JSON to the sentinel but the plan does not specify the exact schema; `ts` semantics (wall clock vs UTC ISO) matter for diagnosability and future `reclaim` introspection.
- It-3 deprecates the per-surface `CLAIM.lock.claude` convention but does not require any migration or cleanup of existing sentinel files already present on disk in adopting repos.
- No plan step covers the `dry_run=True` job path: `save_job` is a no-op for dry-run jobs (`storage.py:76`), but `try_acquire_sentinel` would still write a real file to disk, making dry-run non-idempotent.

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-S1 | Risks | high | Add a synchronization barrier in the It-2 race test so both processes attempt the acquire simultaneously. Without it, one process will typically finish before the other starts and the test never exercises the actual TOCTOU window. | It-2 specifies "spawn **two `multiprocessing.Process`** workers" but gives no barrier. The race fires only if both processes reach `try_acquire_sentinel` concurrently; an unbarriered test is a structural false green. | It-2 — Cross-process race bullet | Add `multiprocessing.Barrier(2)` passed to both workers; each worker calls `barrier.wait()` immediately before the acquire call. Assert exactly one sentinel exists after both return. |
| R1-S2 | Architecture | high | Specify what `run_next`'s `complete_drain` branch (line 325) does when the PROCESSING job's `lease_owner` does not match the calling surface. Currently `run_next` calls `complete_drain(job.job_id)` unconditionally when it finds a PROCESSING job (line 319–325), without any ownership check — a surface that does not hold the sentinel can consume another surface's in-flight job. | It-1 step 3 routes `run_next`'s pending→processing through `_try_claim`, but the existing PROCESSING-job path in `run_next` (line 319: `if job.status is LoopJobStatus.PROCESSING: return self.complete_drain(...)`) is unmodified. Ownership of a PROCESSING job is now tracked via `lease_owner` but `run_next` never checks it on this code path. | It-1 step 3 — Internal acquire (FR-1, FR-6); also add to FR-6 Verify clause | Add ownership check before `complete_drain`: reject or skip if `job.lease_owner` is set and does not match the calling surface's owner argument. Add a test case: surface B calls `run_next` on a job held by surface A; assert it does not consume the job. |
| R1-S3 | Risks | high | Specify the sentinel file schema (`{owner, ts}`) precisely — at minimum: field names, `ts` format (UTC ISO-8601 string), and that the file is valid UTF-8 JSON. | It-1 step 2 says "write `{owner, ts}`" but gives no schema. `reclaim_expired_leases` today does not read the sentinel, but future tooling (diagnostics, `wloop list`, board display) will. An undocumented binary blob is harder to introspect and increases orphan-sentinel debug cost. | It-1 step 2 — Sentinel helper (FR-1) | Add a sentinel schema note: `{"owner": "<surface_id>", "acquired_at": "<UTC ISO-8601>"}`. Verify in It-2 that the written sentinel is valid JSON with the expected fields. |
| R1-S4 | Architecture | medium | Address the crash window between sentinel creation and `save_job` completion: if the process dies after `O_EXCL` succeeds but before `atomic_write_json` finishes (temp+rename), the job file may still show the old `lease_expires_at` (or none), causing `reclaim_expired_leases` to see a PROCESSING job that `lease_expired()` incorrectly evaluates. | `_try_claim` calls `try_acquire_sentinel` then `_transition` (which calls `save_job` → `atomic_write_json` → temp+rename). These are two independent FS operations. A crash between them leaves: sentinel present, `lease_expires_at` stale or absent. `reclaim_expired_leases` at line 1274 calls `job.lease_expired(now=now)` — if `lease_expires_at` is absent, `lease_expired()` returns `False` (line 425), so the orphaned job is never reclaimed. | It-1 step 3 — Internal acquire; also FR-1 note and FR-3 Verify clause | Two mitigations to discuss: (a) sentinel-last ordering (stamp lease first, write sentinel after — reclaim can then always detect the expired lease by TTL even if sentinel exists); (b) reclaim fallback: if sentinel exists but `lease_expires_at` is absent or job is not PROCESSING, treat as orphan and unlink. Pick one and document in the plan. |
| R1-S5 | Risks | medium | Clarify the release-sentinel TOCTOU: between `owner != job.lease_owner` check passing (because lease has expired) and `release_sentinel` unlinking, a second winner may have already acquired a fresh sentinel. Unlinking that fresh sentinel breaks the new owner's exclusion. | It-1 step 6 says "reject if `job.lease_owner` set and `owner != job.lease_owner` and lease not expired" — the guard fires on `lease not expired`. But if the lease is expired and owner is calling late, the check allows the release. A concurrent process may have already won a new sentinel in that expiry window. | It-1 step 6 — Release + authority (FR-4) | Specify that `release_sentinel` is called only when (a) `owner == job.lease_owner` OR (b) the sentinel's own `acquired_at` timestamp confirms it belongs to the current owner. Alternative: have `release_sentinel` check that the sentinel content's `owner` field matches before unlinking. Add a test: TTL expires, surface B acquires, surface A calls `release` — assert surface B's sentinel is intact. |
| R1-S6 | Validation | medium | Add a dry-run guard to `try_acquire_sentinel`: when the calling job has `dry_run=True`, skip the real `O_EXCL` open (or create in a temp location and immediately unlink) to preserve the dry-run non-side-effect contract. | `storage.save_job` already no-ops on `dry_run=True` jobs (line 76). `try_acquire_sentinel` creates a real file on disk regardless. If a drainer calls `wloop claim --dry-run`, a sentinel file persists after the dry-run completes, blocking the real next claim. | It-1 step 2 — Sentinel helper; also FR-2 (Verify clause) | Add `dry_run: bool = False` parameter to `try_acquire_sentinel`; when True, skip the `os.open` and return `True` (probe success). Verify in a unit test that `claim --dry-run` leaves no sentinel file. |
| R1-S7 | Data | low | Document that the sentinel's `missing_ok=True` unlink in `release_sentinel` is intentional and covers double-release / reclaim races — add a brief comment in the plan and a code comment in step 2. | The plan states `release_sentinel(job_id)` uses `missing_ok=True` in It-1 step 2 but does not document why, leaving future implementers uncertain whether to change it. The idempotency is load-bearing: concurrent reclaim + release could both call unlink; without `missing_ok` one would raise. | It-1 step 2 — Sentinel helper | No test change needed; annotate: "`missing_ok=True` is intentional — release and reclaim may race on expiry; both must succeed." |

### Stress-test / adversarial pass

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-S8 | Risks | medium | Verify that the `requeue` sentinel-cleanup site count matches the actual code. The plan references `requeue (`:238/:248`)` but the code (queue.py) shows `lease_expires_at = None` at lines 248 and 262, not 238 and 248. Line 248 is inside the `AWAITING_TRIAGE → PENDING` early-return branch; line 262 is the general requeue. Both paths must call `release_sentinel`. If the plan's line reference is wrong, one of the two sites may be missed during implementation. | The Reference-Audit in REQ-24 §0.1 and the plan's It-1 step 6 enumerate ``:238/:248`` as the requeue sites. Actual code at queue.py shows the two `lease_expires_at = None` assignments at 248 and 262. This 10-line discrepancy is within refactor range but enough for an implementer to miss one site. | It-1 step 6 — Release + authority; cross-reference FR-4 "Every `lease_expires_at = None` site" | Re-run `grep -n 'lease_expires_at\s*=\s*None' queue.py` as a pre-commit check; confirm both 248 and 262 (and any others added since) call `release_sentinel`. |
| R1-S9 | Validation | medium | Add an It-2 test that verifies sentinel cleanup after `run-next` consume (not just explicit `release`): call `run_next` on a job, complete the drain, assert sentinel is gone and `lease_owner=None`. | The It-2 acceptance criteria cover the race (one winner) and stale reclaim but not the normal happy-path cleanup. Without this test, sentinel leakage on normal `complete_drain` → `_transition` → non-PROCESSING path could go undetected. | It-2 — Stale reclaim bullet; add as a new bullet | Assert: after a full `run_next` → drain cycle on a job, `wlq-claim.lock` does not exist and `job.lease_owner` is None. |

---

## Requirements Coverage Matrix — R1

| Requirement Section | Plan Step(s) | Coverage | Gaps |
| ---- | ---- | ---- | ---- |
| FR-1 Atomic acquire (CAS via sentinel) | It-1 steps 2+3+4; It-2 cross-process race | Partial | Crash window between `O_EXCL` success and `save_job` completion is unaddressed (see R1-S4). Sentinel schema (`{owner, ts}`) is not specified precisely (see R1-S3). |
| FR-2 Single holder | It-1 step 4 (`claim` verb, exit-3); It-2 single-holder bullet | Partial | `--surface` required is spec'd but no plan task explicitly validates the "no owner → rejected" path in the CLI verb. Dry-run path not covered (see R1-S6). |
| FR-3 Stale reclaim + sentinel cleanup | It-1 step 5 (`reclaim_expired_leases` + unlink); It-2 stale reclaim bullet | Partial | Orphan detection when `lease_expires_at` is absent (crash after sentinel but before save_job) not addressed (see R1-S4). |
| FR-4 Release + owner authority | It-1 step 6; It-3 (adapter adoption) | Partial | Release TOCTOU when lease expires concurrently with a new acquire (see R1-S5). Requeue site line references may be off by one (see R1-S8). It-3 does not cover migration/cleanup of existing per-surface sentinels. |
| FR-5 Owner-stamped lease field | It-1 step 1 (`lease_owner` model field) | Full | — |
| FR-6 `run_next` closes the TOCTOU | It-1 step 3 (`_try_claim` routes `run_next`); It-2 (both-call-`run_next` test) | Partial | The `run_next → complete_drain` branch (line 325) fires for an already-PROCESSING job without checking `lease_owner` — a non-owning surface can consume the job (see R1-S2). |
| Non-goals (renew, fleet event, blind_rotate, lock server, NFS) | Not planned (correct) | Full | — |
| Acceptance (whole) | It-2 (mixed-surface test); It-1 (all primitives) | Partial | Race test lacks a synchronization barrier (see R1-S1); normal happy-path sentinel cleanup test absent (see R1-S9). |
