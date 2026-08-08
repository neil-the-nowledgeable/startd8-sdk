# CRP Focus — REQ-24 / PLAN-24 WLQ Atomic Claim Lease (Round 1)

## Least-reviewed target
Both REQ-24 (v0.3.1) and PLAN-24 are **brand-new, never CRP'd** — this is Round 1. Weight the review
toward the concurrency semantics below; the surrounding det-req scaffolding has already passed the
reflective loop + lessons + principle hardening.

## Settled — do NOT relitigate (already decided with rationale)
1. **Scope is option 2 / minimal.** `renew`/heartbeat, the `CLAIM{won|lost}` fleet event, and
   `blind_rotate`/`depends_on` acquire-guards are **deliberately deferred to full A1** (see Non-goals).
   Do not propose adding them.
2. **`O_EXCL` sentinel over fcntl `FileLock`** — chosen because fcntl advisory locks release on holder
   death, which would defeat TTL takeover; the sentinel persists so `reclaim_expired_leases` can steal
   it. Rationale recorded in Appendix B. Do not re-propose fcntl.
3. **Local-filesystem assumption is intentional.** NFS / network-FS `O_EXCL` correctness is out of
   scope (NR + OQ-B). Do not propose an NFS-safe redesign.
4. **Reuse-not-rebuild (Mottainai) is a hard constraint.** No new lock server, daemon, or second
   ledger. Suggestions must extend the existing lease/queue, not introduce a new engine.

## Where input is most valuable (weight these)
1. **Sentinel lifecycle correctness.** Is there any window where the `CLAIM.lock` sentinel and the
   job-state lease (`lease_expires_at`/`lease_owner`) can diverge? Consider: acquire that stamps the
   lease but crashes before/after writing the sentinel; the `save_job` temp+rename not being atomic
   *with* the `O_EXCL` create (two separate operations). Is FR-1's ordering (sentinel-first, then
   stamp) the safe one, or should it be reversed?
2. **`run_next` internal-CAS integration (FR-6).** `run_next` calls `reclaim_expired_leases()` then
   `_try_claim`. Is there a TOCTOU *between* the reclaim and the acquire? Does routing the internal
   transition through the sentinel change any existing `run_next` behavior (sdk-workflow vs one-shot
   drain paths, `complete_drain` re-entry on an already-PROCESSING job at queue.py:319)?
3. **Reclaim/release cleanup completeness.** FR-4 claims sentinel-unlink at *every*
   `lease_expires_at = None` site (queue.py:248, 262, 1285, 1515, complete_drain, cancel, requeue).
   Is that enumeration complete and correct? Is there a site that nulls the lease *without* going
   through `_transition`? Is unlink idempotent (missing_ok) so double-release/reclaim races don't error?
4. **Cross-process contention test design (It-2).** Is `multiprocessing.Process` racing on a shared
   temp queue root a faithful reproduction of the TOCTOU? Does it need a synchronization barrier so
   both processes reach the acquire simultaneously (else the race never actually fires and the test is
   a false green)? What's the assertion that proves *exactly one* winner without flakiness?
5. **Owner-authority edge cases (FR-4).** After a TTL takeover, surface A's lease was stolen by
   surface B; can surface A's late `release` (still believing it owns the job) now unlink surface B's
   live sentinel? How does release distinguish "I own the current lease" from "I owned a since-expired
   one"?
