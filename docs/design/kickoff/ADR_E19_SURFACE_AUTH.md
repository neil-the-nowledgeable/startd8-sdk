# ADR — FR-E19: Reusable served-surface auth middleware

**Status:** Decided — **REJECT the shared middleware; consolidate the *contract*, not the *code*.**
**Date:** 2026-07-12
**Context:** FR-E19 (`GRANT_AND_COCKPIT_ENHANCEMENTS.md`) proposed lifting `_cloud_capability` + the
trust chain into a reusable middleware so `stakeholder_run_server` and `consult --serve` stop
"re-implementing" cloud auth.

## Decision

**Do not extract a shared auth middleware / trust chain across the three served surfaces.** After
reading all three, their apparent similarity is superficial: each auth check has **deliberately
different security semantics** tuned to a different threat model. A shared module would either need a
policy flag at every decision point (no real consolidation) or would silently change one surface's
posture (a security regression). Instead, **guard the one genuinely-universal invariant with a shared
conformance test** (`test_surface_auth_conformance.py`) and leave each surface's implementation alone.

## Evidence — the semantics genuinely diverge

| Auth check | kickoff (`web.py`, **cloud**) | `stakeholder_run_server` (**household**) | `consultation/serve` (**loopback**) |
|---|---|---|---|
| **Primary credential** | `X-API-Key` ∧ Origin ∧ **grant (resolve+consume)** | **bearer token** ∧ budget | **per-run token** ∧ CSP nonce |
| **Empty Origin allow-list** | **reject** (`not allowed or origin not in allowed`) | **allow** (strict-only: `if allowed and origin not in allowed`) | N/A — single **exact** origin, missing→reject |
| **Loopback `Host`** | accepts `localhost` **and** `127.0.0.1` | (relies on the bound socket) | **rejects `localhost`** — only `127.0.0.1[:port]` |
| **Replay defense** | bounded-FIFO **intent store** (one-time apply) | **TTL nonce set** + lock (strict) | plain **single-use set** (session-scoped) |
| **Transport** | operator-provided bind / reverse proxy | docker-bridge or loopback | **asserts loopback on the bound address** |

Two surfaces even define a function named `_host_ok` with **opposite** `localhost` behavior. These are
not accidental copies — a cloud surface, an on-demand household tool, and a strictly-loopback consult
server *should* differ (different attack surface ⇒ different posture). Unifying them would be a **false
unification**: the textbook "over-abstraction is itself accidental complexity" (project design rule).

## What IS shared — and how we protect it

Exactly one invariant is universal and must never regress on any surface:

> **A credential comparison is constant-time** (`hmac`/`secrets.compare_digest`), and a wrong/absent
> credential is rejected.

Everything else (Origin-empty policy, `localhost` handling, nonce model, CSP, budget) is
surface-specific and already covered by each surface's own tests.

We consolidate the **contract**, not the code: `tests/unit/kickoff_experience/test_surface_auth_conformance.py`
asserts, across all three surfaces, that the credential comparator is constant-time (a source-level
drift guard that fails if anyone swaps `compare_digest` for `==`) and that a bad credential is rejected.
The divergence matrix above lives in that test's docstring so a future reader is warned off re-unifying.

## Consequences

- **No production code change.** The three surfaces keep their tuned, independently-tested auth.
- **Drift is caught** by the conformance test without imposing a lowest-common-denominator abstraction.
- If a *fourth* served surface appears, it gets a conformance-test row (a contract to satisfy), not a
  forced dependency on a kickoff-shaped middleware.

## Alternatives considered

- **Lift the grant trust chain into shared middleware** (the FR's literal ask) — rejected: the
  grant/consume model is kickoff-specific; the other two are static-token servers. Forcing a grant
  shape onto them is wrong.
- **Extract `origin_allowed()` / `host_is_loopback()` helpers** — rejected: the empty-Origin and
  `localhost` semantics differ per surface, so a shared helper needs a policy flag at each call site,
  yielding indirection without dedup (and a live risk of passing the wrong flag).
- **Extract the replay-nonce store** — rejected: the three replay models (TTL set / plain set /
  bounded-FIFO intent) have different lifetimes; sharing one would change a surface's expiry behavior.
