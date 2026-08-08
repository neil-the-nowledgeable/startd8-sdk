# What REQ-24 Builds

*A plain-language brief for a reader new to the Workflow Loop Queue (WLQ). Companion to `REQ-24-WLQ-Atomic-Claim-Lease.md` and `PLAN-24-WLQ-Atomic-Claim-Lease.md` (both v0.5).*

## In one sentence

REQ-24 builds an **atomic claim primitive** for the workflow loop queue — a small, reliable "call dibs" mechanism so that when two independent worker processes reach for the same queued job at the same moment, **exactly one of them wins and the other is cleanly turned away**, instead of both grabbing it and doing the work twice.

## The problem, concretely

Some background nouns first:

- A **job** is a unit of work sitting in the queue (WLQ), represented as a file on disk. Each job has a **status** — the ones that matter here are `PENDING` (waiting to be worked) and `PROCESSING` (someone is working it).
- A **surface** is a worker — a "drainer." Think of each vendor's automation (a Claude drainer, a Codex drainer) as a separate surface pulling jobs off the queue. **Draining** just means "pick up a `PENDING` job and process it."
- Picking up a job means moving it `PENDING → PROCESSING` and stamping a **lease** on it — a note that says "claimed, don't touch until it expires."

Here is the race. Today, picking up a job looks like: *read the job, see it's `PENDING`, then write `PROCESSING`.* That's two separate steps with a gap between them. If two surfaces both read the job during that gap, **both see `PENDING`, both pass the check, and both write `PROCESSING`** — and now the same job gets drained twice. This is a classic **TOCTOU** bug ("time-of-check to time-of-use": what you checked is no longer true by the time you act on it), also called a **double-drain**.

Why the current file write doesn't save us: the queue writes job files safely in the sense that you never get a half-written, corrupted file (it writes to a temp file and renames it into place — "tear-free"). But tear-free is not the same as **mutually exclusive**. Last writer simply wins; there is no gate that stops the *second* writer from clobbering the first. There is also no owner recorded on the lease — it's just a bare expiry timestamp — so nothing even knows *who* holds a job.

Crucially, **this bug is dormant today.** The system currently runs with a single surface and only one job in flight at a time (WIP=1), so the two-racer situation can't actually arise yet. REQ-24 is therefore **fleet-readiness, not a live firefight**: it deliberately builds the safety mechanism *before* turning on the multi-vendor fleet that would trigger the race.

## What gets built

The mechanism is intentionally minimal — no lock server, no new engine, just three pieces layered onto the queue's existing lease machinery:

1. **A per-job sentinel file, `CLAIM.lock`** — the gate. To claim a job, a surface tries to *create* a file named `CLAIM.lock` in that job's folder using the operating system's "create only if it doesn't already exist" mode (`O_EXCL`). On a local disk this create is **atomic**: if two surfaces try it simultaneously, the OS guarantees exactly one succeeds and the other gets "file already exists." That single atomic create *is* the compare-and-set — the win/lose decision that the old read-then-write couldn't provide.
2. **An owner-stamped lease.** The winner records who they are (`lease_owner = <surface id>`) plus when they claimed it. So the queue now knows not just *that* a job is held but *by whom* — which is what makes "only the owner may release it" enforceable.
3. **CLI verbs** so humans and adapters can drive it.

The lifecycle a reader can picture:

```
  claim  ──►  (do the work)  ──►  release
    │                              ▲
    │  someone else already holds it
    └──► turned away (retry later)

  reclaim  ── takes over a claim whose holder died or timed out
  status   ── shows who holds a job and since when
```

The eight behaviors (the "FRs"), in plain terms:

- **Atomic acquire** — claiming creates the `CLAIM.lock` sentinel first, *then* stamps the owner; the create is the win/lose gate.
- **Single holder** — a second claim on an already-held, unexpired job is politely refused with a "held, try again" signal (retryable), not an error.
- **Stale reclaim + orphan cleanup** — if a holder's lease expires or its process crashes mid-claim, the recovery pass takes the job back *and* deletes the leftover sentinel, so the queue can't get permanently wedged by an abandoned lock.
- **Release + owner authority** — only the surface that holds a job (or a timed-out takeover) can release it; a stranger trying to release someone else's live claim is rejected and logged.
- **Owner-stamped field** — the job record carries `lease_owner`, set on claim and cleared on release.
- **Every pickup path is covered** — the gate is placed at the *one internal chokepoint* every acquire flows through, so all five ways of picking up a job are protected, not just the obvious one.
- **Recovery verbs are honest overrides** — the `cancel`/`requeue` admin verbs *can* forcibly wrest a live job away, but doing so logs a loud warning naming who got displaced; they are never used in normal automated draining.
- **The holder is visible** — `status` shows who holds each job and since when, so a multi-surface fleet is actually operable.

## How it's built (order)

**Iteration 1 — the primitive.** Add the `lease_owner` field to the job model; add the sentinel helper (`CLAIM.lock` create/release) to storage; wire the atomic create-and-stamp into the single `_transition`-into-`PROCESSING` chokepoint so every pickup path is guarded at once; add the `claim` and `release` CLI verbs; extend the existing reclaim pass to also unlink stale and crash-orphaned sentinels; enforce owner-only release; make the admin override verbs log loudly; and extend `status` to show the holder. This iteration delivers the whole working mechanism.

**Iteration 2 — the proof.** Build a contention test suite that actually forces the race: spawn two real processes, hold them at a starting-line barrier, and release them at the exact same instant onto one job. The tests assert exactly one wins, stale and crash-orphaned locks get reclaimed, no job is consumed by a non-owner, and the holder is observable. Without the barrier the test would be a false pass, so the barrier is load-bearing.

**Iteration 3 — adoption.** Switch the real vendor adapters (the Claude and Codex drainers) to call `claim`/`release` before and after draining, and retire the older per-worker locking convention that never actually serialized work *across* different surfaces.

## How we'll know it works

The acceptance tests, in plain language:

- **Two processes race one job → exactly one wins.** The other is cleanly turned away; only one `CLAIM.lock` exists on disk afterward.
- **A crashed or timed-out claim gets recovered.** An abandoned lock (holder died mid-claim, or lease expired) is swept away automatically and the next claimer can win — no permanent wedge.
- **No double-consume across surfaces.** A surface that doesn't own a job cannot pick it up or complete it out from under the owner.
- **The holder is observable.** `status` shows who holds a given job and since when; a free job shows as unheld.

## Explicitly NOT in scope

- **`renew` / heartbeat** lease extension (holders can't keep a claim alive indefinitely; that's a later, fuller design).
- **Fleet events** — no broadcasting "claim won/lost" notifications.
- **Acquire guards** like `blind_rotate` / `depends_on` sequencing.
- **A new lock server or daemon**, a second ledger, or any OS advisory (`fcntl`) lock — the sentinel deliberately replaces all of these. (Advisory locks were rejected because they vanish when the holder dies, which would defeat timeout-based takeover.)
- **NFS / network filesystems** — the atomic-create guarantee is assumed only for a **local** disk, which is where the queue lives today.
