# FR-B4 (single_in_flight_by) Requirements — Audience-B in-flight guard

**Version:** 0.2 (Post-planning — self-reflective update)
**Date:** 2026-07-02
**Status:** Draft
**Parent:** `docs/design/prompt-injection-prevention/REQUIREMENTS.md` FR-B4 (deferred slice)
**Substrate decision:** vendored file-lock **pattern** (not a DB lock table); **held-flock, no TTL lease**.

---

## 0. Planning Insights (Self-Reflective Update)

> The planning pass ran a `/tmp` experiment on real `flock` semantics and reversed the design's most
> complex requirement.

| v0.1 Assumption | Planning Discovery | Impact |
|---|---|---|
| **FR-B4-4:** add a TTL + `holder_id` + `expires_at` lease for stale-lock recovery (the substrate handoff said "ContextCore has no TTL — must add") | **PROVEN:** a held `flock` is **auto-released by the OS when the holder process dies** (verified: a parent acquires immediately after a child that held the lock exits without unlocking). If the pass **holds the flock across the whole `call_ai_service`**, a crashed worker's claim is reclaimed automatically. | **FR-B4-4 collapsed** from a TTL/lease machine to "OS auto-release handles crash recovery." No `expires_at`, no `holder_id`, no steal logic, no sweep. |
| **FR-B4-3:** vendor ContextCore `file_lock` as-is | ContextCore's POSIX lock is **blocking** (`LOCK_EX`) — a contender would *wait*, not fail-fast reject. | FR-B4-3 corrected: **non-blocking** (`LOCK_EX \| LOCK_NB`) so contention raises `BlockingIOError` → immediate `in_flight` reject. |
| Held-flock vs. claim-record undecided (OQ-2) | Held-flock is simpler **and** gets crash recovery free. | Held-flock chosen. |

**Resolved open questions:**
- **OQ-1 → Resolved.** Lock files are 0-byte sentinels, leave-and-reuse; sweep deferred (not required).
- **OQ-2 → Resolved.** Held-flock (not a written claim record).
- **OQ-3 → Resolved.** Non-blocking everywhere (fail-fast reject, never wait).
- **OQ-4 → Resolved.** Keys MUST be a subset of the pass's signature params (`source_id`, `request_field`).
- **OQ-5 → Moot.** No TTL → no `ttl_s` knob.
- **OQ-6 → Resolved.** Cross-process behavior is subprocess-testable (gated).
- **OQ-7 → Resolved.** Independent of `auto_send`/`stricter` (not forced).

**Heuristic check:** the loop deleted the single most complex requirement (FR-B4-4) and corrected FR-B4-3
before any code — exactly the point of planning first.

---

## 1. Problem Statement

The SDK emits AI passes into generated apps. A human-triggerable pass over untrusted input (source-bound
`extract_document`, scoped `draft_interviewer_message`) can be **re-run concurrently** — a button-mash or
a double-submit fires N overlapping `call_ai_service` invocations for the *same logical draft*. That is a
**cost/DoS surface** (N paid LLM calls for one intended draft) and a correctness nuisance (racing
idempotency-deletes + inserts). FR-B4 closes it: **at most one AI call in flight per declared key-tuple**.

FR-B4 is **opt-in** (a pass declares `guards.single_in_flight_by: [keys]`); absent → unchanged behavior.

### Substrate context (why not a DB lock table)

A DB lock table is the "obvious" substrate but collides with the generated app's persistence model: in
**deployed** mode `create_all` is OFF (FR-PER-3) and the SDK emits **no migrations**, so a new table
wouldn't exist in production. A ContextCore lite-mode investigation surfaced a **pure-stdlib file-lock
pattern** (`state.py:55-90` `file_lock()` via `fcntl.flock`/`msvcrt` + re-check-after-acquire) that is
vendorable into `app/ai/guards.py` with **zero schema change**. It has no TTL (must add) and is
**node-local** (works across uvicorn/gunicorn workers on one host; not across k8s replicas) — but that
matches the actual re-run-storm threat (same host, same user, multiple workers).

### Gap table

| Component | Current State | Gap |
|---|---|---|
| `guards.single_in_flight_by` grammar | **Rejected** as unknown key (no silent no-op) | Add to `_GUARDS_KEYS`; parse into `Guards` |
| `app/ai/guards.py` (v4) | fence/normalize/validate/verify — all stateless | No lock/lease primitive; add a vendored file-lock lease |
| pass emission (source-bound, scoped) | `result = call_ai_service(...)` then persist | No acquire/release around the AI call |
| reject contract | `rejected` / `needs_more_data` status dicts exist | No `in_flight` status shape defined |
| stale-lock recovery | — | No TTL / holder / sweep |

---

## 2. Requirements

**FR-B4-1 (Declarative key).** `ai_passes.yaml` MUST accept `guards.single_in_flight_by: [<key>, ...]`
where each key is a request-parameter name available to the pass (e.g. `source_id`, or a `request_field`).
Absent (default) → no in-flight guard (byte-identical emission). `single_in_flight_by` MUST be added to
`_GUARDS_KEYS` and parsed into `Guards` (strict: a non-list, or a key not resolvable in the pass signature,
is a build-time error).

**FR-B4-2 (At most one in flight per key-tuple).** When declared, the generated pass MUST acquire an
exclusive claim keyed by `(pass_name, <resolved key values>)` **before** `call_ai_service`, and release it
after persist (success or failure). A second concurrent invocation with the same key-tuple, while the
claim is held and fresh, MUST NOT call the LLM — it returns an `in_flight` status.

**FR-B4-3 (Cross-process, same-host, NON-BLOCKING).** The claim MUST be honored across **separate OS
processes on the same host** (uvicorn/gunicorn workers) — an in-process lock is insufficient. Implemented
via a `fcntl.flock`/`msvcrt` file-lock over a per-key lock file, acquired **non-blocking**
(`LOCK_EX | LOCK_NB` on POSIX; `LK_NBLCK` on Windows). A held lock MUST cause the contender to **fail fast**
(`BlockingIOError` → `in_flight` reject), NOT wait. *(Corrected from v0.1's "vendor as-is" — ContextCore's
POSIX lock is blocking, which is wrong for reject-don't-wait semantics.)*

**FR-B4-4 (Crash recovery via OS auto-release — NO TTL).** The flock MUST be **held for the duration of
`call_ai_service` + persist**. Because the OS auto-releases an flock when the holding fd closes (including
on process death), a crashed/killed worker's claim is reclaimed automatically — **no TTL, `expires_at`,
`holder_id`, steal logic, or sweep is required** (verified in the planning pass). A *hung* (not crashed)
worker is bounded by the uvicorn/gunicorn worker timeout, which closes the fd. *(v0.1 specified a TTL lease;
planning proved it unnecessary for the held-flock design.)*

**FR-B4-5 (Reject contract).** A rejected concurrent run MUST return a status dict shaped like the existing
guards: `{"status": "in_flight", "created": {<Entity>: 0}}`. The route/trigger surface SHOULD surface this
distinctly (e.g. HTTP 409) but MUST NOT 500.

**FR-B4-6 (Emission scope).** FR-B4 MUST be emitted only for the untrusted-input, human-triggerable pass
shapes (source-bound `_render_pass_text_bound`, scoped `_render_pass_scoped`). Whole-model read passes are
internal (not re-run-storm-prone) and are out of scope.

**FR-B4-7 (Observability, FR-B7 parity).** Each in-flight **rejection** MUST log a structured event
(`ai_in_flight_rejected`) to the generated app's runtime logger, matching the FR-B7 pattern of the other
guards. *(No `stale-claim steal` event — there is no steal; OS auto-release is silent.)*

**FR-B4-8 (Stdlib + versioned).** The lease primitive MUST be pure-stdlib (no new generated-app dependency)
and MUST bump `__guards_version__` (drift detection).

**FR-B4-9 (Storage location).** Lock files MUST live under an app-writable, per-app path (default a temp
subdir, e.g. `<tempdir>/<app>/ai-inflight/`), with a fallback when the primary path is unwritable (mirroring
ContextCore `state.py` fallback behavior). MUST NOT write into the source tree.

---

## 3. Non-Requirements

- **NR-1.** Not **multi-host** exact-once. `flock` is node-local; a k8s multi-replica deployment wanting
  cross-host mutual exclusion is a documented boundary requiring a Postgres-advisory-lock/lease upgrade
  (follow-on, not this slice).
- **NR-2.** Not a **queue** — a rejected run is dropped (`in_flight`), not enqueued/retried.
- **NR-3.** Not **default-on** — opt-in per pass (contrast B2/B3 which are default-on).
- **NR-4.** Not a **dedup/idempotency** mechanism — that's the existing source-scope idempotency (FR-IMP-2).
  B4 is concurrency exclusion, orthogonal.
- **NR-5.** No new **DB table** or migration (the whole reason for the file-lock substrate).

## 4. Open Questions — ALL RESOLVED (see §0)

- **OQ-1 → Resolved.** 0-byte lock files, leave-and-reuse; periodic sweep deferred (not required).
- **OQ-2 → Resolved.** Held-flock (not a written claim record) — simpler + free crash recovery.
- **OQ-3 → Resolved.** Non-blocking everywhere (`LOCK_NB` / `LK_NBLCK`) — fail-fast reject.
- **OQ-4 → Resolved.** Keys MUST be a subset of the pass's signature params (`source_id`, `request_field`);
  validated at render time.
- **OQ-5 → Moot.** No TTL → no configurability knob.
- **OQ-6 → Resolved.** Cross-process behavior is subprocess-testable (gated integration test).
- **OQ-7 → Resolved.** Independent of `auto_send`/`stricter` — not forced (a stricter pass MAY add it).

---

*v0.2 — Post-planning self-reflective update. FR-B4-4 collapsed (TTL lease → OS auto-release; the single
biggest simplification), FR-B4-3 corrected (non-blocking), FR-B4-7 trimmed (no steal event); all 7 open
questions resolved. Ready for implementation (or an optional CRP pass).*
