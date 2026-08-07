# A1 — WLQ Atomic Claim Lease — Next Steps / Build Handoff

**Date:** 2026-08-07 · **Owner:** startd8-sdk · **Status:** teed up, not started · **Chosen scope:** option 2 (minimal)
**Precedes:** `REQ-24-WLQ-Atomic-Claim-Lease.md` (to be authored) + its `PLAN-24`.

> One-screen handoff so this can be picked up cold. A1 is the multi-vendor drain fleet's **rule 1** (one atomic
> claim primitive). It is **decision-gated by nothing** — safe to build — but it is **fleet-readiness, not a
> live-bug fix**: the race it closes only fires when a *coordinated multi-vendor fleet drains concurrently*,
> which is dormant today (single-surface use + the WIP=1 gate). Build it deliberately, framed as readiness.

## 1. The problem — grounded, confirmed real

`run_next`'s claim of a PENDING job is a **TOCTOU** (time-of-check-to-time-of-use):

```
queue.py:~37   if job.status is not LoopJobStatus.PENDING: raise   # CHECK (read)
               … then transition pending → processing via save_job → atomic_write_json  # USE (write)
```

`atomic_write_json` guarantees the file is never *torn* — it does **NOT** guarantee mutual exclusion. Two
drainers (e.g. two vendor surfaces) can both read `PENDING`, both pass the check, and both write `processing`
→ **double-drain**. The per-root `CLAIM.lock.claude` (`drain-claude.py`) is per-surface-per-root, so two
*different* surfaces don't serialize against each other. There is **no `startd8 wloop claim` subcommand**
(confirmed absent). So the race the multi-vendor fleet pattern warns about (rule 1) is real in the code.

**Why it's latent (do not over-urgent-ize):** it only bites with ≥2 surfaces draining the same job in the same
root concurrently — i.e. a live fleet. Today: single-surface per project + `REQ-02` WIP=1 (one loop active).
So build A1 as the *enabler* of the intra-project vendor fleet (convergence / blind_rotate), not a firefight.

## 2. Mottainai — extend the existing lease, do NOT build a new engine

The SDK **already has the lease state**; A1 option 2 exposes + atomicizes it. Reuse:
- `WorkflowLoopJob.lease_expires_at` (`models.py:346`) + `is_expired` (`models.py:~425`).
- `LoopQueueConfig.lease_ttl_seconds` (`models.py:443`, default 3600).
- `WorkflowLoopQueue.reclaim_expired_leases` (`queue.py:1274`) — TTL reclaim on `status`/`run-next`.
- Existing reqs that own this: **FR-3** (durable status + lease reclaim) + **OQ-5** (lease TTL, resolved) in
  `CURSOR_WORKFLOW_LOOP_REQUIREMENTS.md`. A1 is their multi-surface CAS extension, **cite them**.
- `codex-loop/REQ-01` v0.2 already **anticipates** A1: *"WLQ's filesystem path is not an atomic inter-process
  claim primitive, so all Codex entry points share one adapter single-flight guard **until an upstream atomic
  claim contract is available**."* — A1 IS that contract.

## 3. Scope — option 2 (minimal)

**In:** the race-safety core.
- Atomic acquire: `startd8 wloop claim --job-id <id> --surface <sid>` via **`O_CREAT|O_EXCL`** (compare-and-set),
  writing an owner-stamped lease `{surface_id, ts, expiry}` over the existing lease field — never read-then-write.
- Single holder: a second `claim` on a live lease returns **non-zero (exit 3, retryable)**.
- Release: `startd8 wloop release --job-id <id>` (auto on `run-next` consume). WLQ job state authoritative.
- Reuse the existing TTL reclaim (`reclaim_expired_leases`) for stale-lease takeover.

**Out (defer to full A1, when the fleet is actually stood up):**
- `renew`; the blind_rotate/deps **acquire guards** (FR-4 of the code-asks); the `CLAIM{won|lost}` **Fleet Event**
  (that's A3 / `contextcore fleet emit`, not needed for the minimal safety core).

## 4. Proposed REQ-24 FRs (minimal — author before coding)

- **FR-1 Atomic acquire (CAS).** `wloop claim` acquires via `O_EXCL`; no read-then-write. *Verify:* two
  processes race one PENDING job → exactly one `won`, one non-zero.
- **FR-2 Single holder.** second live `claim` → exit 3. *Verify:* held job's second claim exits 3.
- **FR-3 Stale reclaim (reuse).** a lease past `lease_ttl_seconds` is reclaimable (existing `reclaim_expired_leases`).
  *Verify:* expired lease → next `claim` wins.
- **FR-4 Release + authority.** `wloop release` (auto on consume); WLQ state is the single source. *Verify:*
  consume releases; direct status writes are not the claim path.
- **NR:** no `renew`, no fleet-event, no acquire-guards in this phase (full A1). No new lock server — extend the
  existing lease.

## 5. Plan sketch (PLAN-24)

- **It-1** — the CAS acquire over the existing lease + `claim`/`release` CLI (extend `queue.py` claim path with an
  `O_EXCL` guard; wire the two CLI verbs in `cli_wloop.py`).
- **It-2** — a **contention test**: two concurrent `claim`s on one job → exactly one `won` (the acceptance that
  proves the TOCTOU is closed); + stale-lease reclaim test.
- **It-3** — adopt in the adapters: `drain-claude`/`codex` call `wloop claim` before drain (replacing the
  per-surface single-flight lock as the cross-surface primitive); deprecate any `CLAIMED_BY.*` convention in
  the board §2.

**Acceptance:** two surfaces racing one job → exactly one `won`; stale lease reclaimed after expiry; a mixed-surface
temp-queue contention test passes.

## 6. Pointers (read these first)

- **The ask:** `OSS/Istio/analysis/CODE_ASKS_fleet_and_loop_REQ_PLAN_2026-08-04.md` §A1 (FR-1..6 = the *full* A1;
  option 2 is the FR-1/2/5 subset).
- **The pattern (rule 1):** `dev-os/multi-vendor-loop/docs/SURFACE_FLEET.md` + `README.md` (reconciled 2026-08-07).
- **Reconciles already done this session (so you don't re-derive):** A2 claude-code surface registered
  (`surfaces.py`, #405) + reqs (FR-1/21/22, #407); VJO `REQ-01` v1.2 FR-25 (fleet-emit) / FR-26 (per-project roots);
  `codex-loop/REQ-01` v0.3.1; fleet SSOT ratified (`FLEET_TELEMETRY_SCHEMA.md`, #396).
- **The cross-project twin:** `dev-os/visual-tools/REQ-02-Single-Project-Wip-Gate.md` (WIP=1 is multi-project;
  A1 makes intra-project multi-surface race-free — complementary layers).
- **Lacuna context:** A1 = lacuna **L4**; unified `fleet emit` = **L5**; cursor fleet-blind = **L2** (route Istio
  via codex meanwhile).

## 7. Sequencing

1. Author **REQ-24** (det-req/0.1) from §1–§4 above — run the reflective loop; the reqs-readiness grounding is done.
2. **PLAN-24** from §5.
3. Build It-1→It-3.
4. Only then revisit full A1 (renew + guards + fleet-event) when a coordinated fleet is actually being run.
