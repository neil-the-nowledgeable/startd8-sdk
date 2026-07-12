# Cloud Human Door (Magic-Link) Requirements — FR-E12

**Version:** 0.2 (post-planning, self-reflective)
**Date:** 2026-07-12
**Status:** Ready to implement
**Owns:** the OQ-12 "human cloud door" enhancement (`GRANT_AND_COCKPIT_ENHANCEMENTS.md` FR-E12)
**Builds on:** `CLOUD_MIRROR_GRANT_REQUIREMENTS.md` (the grant primitive + FR-14 trust chain, SHIPPED)

---

## 0. Planning Insights (Self-Reflective Update)

> v0.1 assumed the cloud grant-gated chat path already existed in the served app and this was "just a
> magic link on top." Planning against the **actual `origin/main`** both confirmed that and caught a
> near-miss that would have wrecked the design:

| v0.1 Assumption | Planning Discovery | Impact |
|-----------------|--------------------|--------|
| The grant path is wired into the served app | **TRUE on `origin/main`** — `build_kickoff_app(grant_store, deployment_id, cloud_origins)` + `_cloud_capability` trust-chain seam + `_session_grants` + `_cloud_revalidate`; `chat_page` consumes a grant on session creation (web.py:1234). | Door builds on a real endpoint. |
| I can read the seams in the primary worktree | The **primary worktree was STALE** (behind `origin/main`); its `web.py` had *none* of the grant wiring. Reading it first produced a false "grants are unwired" conclusion. | **All planning + build done against a fresh worktree off `origin/main`.** (reference_multiworktree_env fired.) |
| The human just needs the api-key injected | A browser GET navigation to a link sends **Host but usually not `Origin`** and never `X-API-Key`. The existing `_cloud_capability` needs both. | Redemption is a **distinct trust path** (token-as-bearer + Host check), not a reuse of the api-key/Origin gate. |
| The link should be the metered thing | Metering the link would duplicate FR-7/15 (consume/revalidate/revoke/expiry). | **The GRANT stays the single metered resource**; the link token is a one-time *browser bearer* that authorizes consuming it. |

**Resolved open questions:**
- **OQ-12 → magic-link, one-time session** (user decision). Operator issues grant + a one-time URL; the human clicks; the app verifies + mints a session cookie carrying the (existing) grant binding; per-turn uses the existing FR-15 revalidation.
- **Scope → minimal, local cloud door now** (user decision). Single-user, one session at a time, no identity/IdP/multi-user session store. Deferred to when hosting is actually reached.

---

## 1. Problem Statement

The cloud grant path is fully wired, but **only a programmatic client can reach it**: `chat_page`
requires the request to present `X-API-Key` (∧ `Origin` ∈ configured ∧ a live grant). A human in a
browser cannot craft that header, so the granted agentic chat is unreachable to the very users the
grant exists to serve ("avoid the CLI — too advanced for most users").

| Component | Current State | Gap |
|-----------|---------------|-----|
| Grant primitive / trust chain / CLI / metrics | SHIPPED, tested | — |
| Served cloud chat endpoint | Wired; consumes a grant **iff** the request presents api-key + Origin | A human browser can't present api-key |
| Human entry | none | **FR-E12: a one-time link the human clicks to get a session** |

---

## 2. Requirements

- **FR-1 — Link token on the grant.** `CloudGrant` gains an optional `link_token: Optional[str]`
  (default `None`; byte-identical serialization when absent). A grant with a link token can be
  redeemed via the human door; one without behaves exactly as today.
- **FR-2 — Issue with a link.** `startd8 cloud-grant issue --with-link [--serve-url URL]` mints the
  grant with a fresh `secrets.token_urlsafe(32)` link token and prints the entry URL
  `<serve-url>/kickoff/enter?t=<token>` **once**, flagged as a one-time secret. `--serve-url` is
  **required** with `--with-link` (the `issue` command is origin-agnostic — it binds deployment/
  project, not origins — so the base URL is supplied explicitly; a missing one fails fast, before
  minting, so no un-linkable grant is left on disk).
- **FR-3 — Atomic redemption.** `GrantStore.redeem_link(token, target, *, now, clock_trusted)`
  resolves the grant whose `link_token == token` **and** `target` matches (FR-8 binding), and in one
  locked critical section: checks live + uses, **consumes one use**, and **burns the token**
  (clears `link_token`) so the link is strictly one-time regardless of remaining uses. Every failure
  is a typed deny with **no debit** (mirrors `resolve_and_consume`). Fail-open metrics: `consume` on
  allow, `deny{reason}` otherwise (FR-E4 sink).
- **FR-4 — The door route.** `GET /kickoff/enter?t=<token>`, present **only** on a cloud + grant-store
  build. On success it mints the same session `chat_page` does — a `kickoff_chat` + `kickoff_csrf`
  cookie pair, a `chat_factory()` chat, and `_session_grants[chat_sid] = (grant_id, target)` — then
  redirects to `/concierge/chat`. The human lands in a live session; **all per-turn actions use the
  existing `_cloud_revalidate`** (browser POSTs carry `Origin`) with **no re-consume**.
- **FR-5 — Host confinement.** Redemption requires the request `Host` to be a configured/loopback
  host (reuse the DNS-rebinding defense). A leaked link cannot be redeemed against an unexpected host.
- **FR-6 — No oracle.** Any redemption failure (absent/expired/exhausted/revoked/burned/target-mismatch
  /wrong-host) returns **one generic** "link invalid, expired, or already used" page — never a reason
  that distinguishes "no such token" from "already used" (parity with the grant's no-existence-oracle).
- **FR-7 — Revoke kills the door.** Revoking the grant (existing `cloud-grant revoke`) makes the link
  un-redeemable *and* expires any session already minted from it (per-turn revalidation fails). No new
  revocation surface.
- **FR-8 — Byte-preservation.** Non-cloud and non-`--with-link` behavior is byte-identical: the new
  field defaults absent, the new route is only registered on a grant-capable cloud build, and the
  grant-store on-disk shape is unchanged when no link token is set.

## 3. Non-Requirements

- **NR-1 — No identity / multi-user.** One session at a time; no per-user principals, no login, no IdP.
- **NR-2 — No new crypto.** The session rides the existing in-memory session store (opaque random sid
  in an HttpOnly/SameSite cookie); the link token is an opaque random bearer stored on the grant. No
  signed cookies, no separate key material. (A hosted future may add them — deferred.)
- **NR-3 — No separate token store.** The link token rides the grant record (reuses FileGrantStore's
  atomic ops); no `links.json` sidecar.
- **NR-4 — No api-key/Origin reuse for the GET.** Redemption is the token-bearer path; the api-key +
  Origin trust chain remains the programmatic path, unchanged.
- **NR-5 — Tier-2 deferred.** No reverse-proxy/IdP recipe (the rejected option), no hosted session
  store, no rate-limited login.

## 4. Threat Model (documented, accepted for minimal-local scope)

The link token is a **bearer credential** (possession ⇒ authorization) — standard magic-link posture.
Mitigations: **one-time** (burned on first redemption), **short-lived** (grant TTL, default 15m),
**Host-confined** (FR-5), **HTTPS-only** in a real cloud deployment, and **revocable** (FR-7). Residual
risk = link interception before first click (browser history / referrer / logs). Accepted for the
single-user local-cloud scope; a hosted deployment should serve over TLS and treat the link as secret.

## 5. Test Plan

- `redeem_link`: happy path consumes+burns; second redemption → deny (burned); expired/revoked/
  exhausted/target-mismatch → typed deny, no debit; store-unavailable → deny; metrics emitted.
- Route: valid token → 302 to chat + session cookies + binding present; invalid/burned/expired →
  generic page (identical body for every failure); route absent on non-cloud / no-grant-store build.
- Byte-identity: grant with no link token serializes identically to a pre-FR-E12 grant; non-cloud app
  route table unchanged.
- CLI: `issue --with-link` prints an enter URL + one-time warning; `--serve-url` derivation.

---

*v0.2 — Post-planning. 1 near-miss caught (stale worktree), 2 OQs resolved (magic-link, minimal-local),
metering seam corrected (grant, not link). Ready to implement.*
