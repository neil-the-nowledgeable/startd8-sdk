# Temporary Cloud Authorization Grant — Cockpit-Mirror Parity Bridge (DRAFT)

**Version:** 0.5 (OQ-4 issuer model resolved)
**Date:** 2026-07-11
**Status:** Draft — CRP R1 applied + OQ-4 resolved (out-of-band control-plane issuance; served app
consume-only). Mechanism = server-side grant record; scope = the agentic **chat-write** path. M0 shipped.
Residual opens: OQ-3/8/10/11 (defaults, clock tolerance, granularity, Origin policy).
**Owner doc for:** the human-driven, temporary, use-limited, expiring authorization that grants a
**cloud** deployment the local-only agentic **chat-write** path (Concierge chat + proposal-apply +
redacted cockpit mirror), for parity — in a strictly bounded way.
**Relates to (does not restate):** `WELCOME_MAT_2.0_REQUIREMENTS.md` FR-WM2-5d (the local/hosted
mirror posture, amended 2026-07-11), the GE-M5 cloud read/preview-only posture + **OQ-GE-7**
(cloud-write / net-new auth+tenancy deferred), `server/auth.py:APIKeyMiddleware` (the existing coarse
`--api-key` gate), the `--mirror-cockpit` wiring (`cli_kickoff.py:start_cmd`), and the
`consultation/serve.py` consume-before-act/anti-replay nonce pattern (FR-SRV-5). **Plan:**
`CLOUD_MIRROR_GRANT_PLAN.md`.

---

## 0. Planning Insights (Self-Reflective Update)

> What changed between v0.1 (pre-planning) and this version after planning against the real seams
> (`web.py`/`serve.py` `--cloud` gates, `server/auth.py`, the `/concierge/chat/*` + `apply_proposal`
> write path). The planning pass **materially reshaped** the spec — the `--cloud` disable is deeper
> and more scattered than v0.1 assumed:

| v0.1 Assumption | Planning Discovery | Impact |
|-----------------|--------------------|--------|
| A grant flips a per-request "cloud" boolean to allow the behavior. | `--cloud` disables chat at **build time** — `web.py:677` sets `chat_factory = None`, so **no session can even be created**. A per-request grant cannot un-null a build-time factory. | **FR-12 (new):** the app must be **built grant-capable** (with a factory) in cloud mode when a grant store is configured; the grant gates per-request. |
| Enabling parity flips one gate. | There are **~6 independent `if cloud:` denials** (`/capture/apply` 773, `_concierge_write_gate` 915, chat page 1108, message 1163, +1261) **plus** the build-time null. | **FR-13 (new):** collapse them into **one** effective-posture resolution consulted at every gate (single-source; prevents an un-gated write leak). |
| The `--api-key` gate is the cloud trust substrate for this. | `server/auth.py:APIKeyMiddleware` is a **coarse static single-key** POST gate — no use-count / expiry / revocation. A door, not a meter. | **FR-11 clarified + FR-14 (new):** the grant is a **separate metered/expiring/single-use** primitive **layered on** the api-key. |
| Flipping the cloud flag is enough for cloud writes. | The local write chain also enforces **loopback-Host + local-session CSRF** (`_host_ok`, `sessions.valid`); on a **non-loopback** cloud surface these fail regardless of the flag. | **FR-14 (new):** the grant path needs its **own** trust chain (api-key + grant + scope + cloud-Origin), distinct from the loopback+CSRF local chain. |
| "1 use" is self-evident. | "Use" is ambiguous: 1 session? 1 token-spending turn? 1 proposal-apply (write)? The token-spend is the actual abuse risk the posture protected. | **FR-15 (new):** define **1 use = 1 agentic session**, consumed at session start; the session's existing turn/rate/budget caps bound spend within the use. (Granularity parked as OQ-10.) |
| No grant primitive exists to build on. | Confirmed — no `Grant`/`Lease` primitive. **But** `consultation/serve.py` already has **consume-before-act + anti-replay nonce** (FR-SRV-5). | Reuse that **pattern** (not a signed token — revocation + true single-use need server state). |

**Resolved open questions:**
- **OQ-6 → RESOLVED (explicit direction): the grant enables the agentic *chat-write* path** — the
  token-spending Concierge chat **+** proposal-apply writes **+** the redacted mirror — not merely the
  disk mirror. This is the larger, higher-risk surface, so it carries the extra safety FRs (FR-15/16).
- **OQ-1 → RESOLVED: a server-side grant record + atomic counter** (revocation + anti-replay need
  server state; a signed token can't be revoked or made truly single-use). Reuses the consult pattern.
- **OQ-2 → RESOLVED: enforced server-side** (per-request resolve + atomic consume).
- **OQ-9 → RESOLVED: the grant layers ON the api-key** (api-key = who may knock; grant = metered,
  expiring permission for the elevated capability).

### 0.1 Lessons-Learned Hardening (v0.3)

> Applied the SDK/knowledge-management lessons before CRP. Each changed or confirmed the draft:

- **[Reuse-first audit — KM Leg 3 #34]** — grepped for an existing grant/lease/one-time-token
  primitive: none. **But** the consume-before-act + anti-replay nonce already exists in
  `consultation/serve.py` (FR-SRV-5) → reuse the **pattern** (M0), don't invent a new anti-replay
  scheme. Also confirmed `apply_proposal` (the safe-writer) is reused unchanged (FR-16), not reimplemented.
- **[Verify-against-source / phantom-reference audit — KM Leg 7 #48]** — every symbol this doc names
  was grepped: `server/auth.py:APIKeyMiddleware` ✓, `web.py` cloud gates at 677/773/915/1108/1163/1261 ✓,
  `_cloud_deferred`/`CLOUD_WRITE_DEFERRED_CODE` ✓, `_concierge_write_gate`/`_host_ok`/`sessions.valid` ✓,
  `apply_proposal` ✓, `consultation/serve.py` nonce (FR-SRV-5) ✓. No phantoms; the grant primitive is
  the only to-be-created symbol (marked as such).
- **[Single-source vocabulary ownership — Design_Docs #5]** — this doc **owns** the grant vocabulary;
  it **cites** (does not restate) FR-WM2-5d, GE-M5/OQ-GE-7, and FR-SRV-5. FR-13 is itself the
  single-source move applied to *code* (one posture rule, not six).

### 0.2 Design-Principle Hardening (v0.3.1)

> Checked the draft against the design principles. Each changed or confirmed the draft:

- **[Accidental-Complexity anti-principle]** — the biggest yield: v0.1 would have edited six `if cloud:`
  sites (an implicit allowlist that drifts and leaks). **FR-13 replaces them with ONE
  `_cloud_capability(request, capability)` rule** — a general check, not an enumerated per-endpoint
  bypass. Deleting the scatter is the point.
- **[Genchi Genbutsu — bind to the real artifact]** — the grant's trust chain binds to the **actual**
  auth substrate (`APIKeyMiddleware` + a real server-side record), not an inferred/templated identity;
  and it **respects the boundary** — least-privilege scope bound to a target (FR-8), no broader
  elevation. Human-issuer identity in a tenancy-less cloud (OQ-4) is honestly left partially open.
- **[Context-Correctness-by-Construction]** — the grant decision must **reach every gate**,
  default-deny: **FR-5 fail-closed** + FR-13's single seam mean a missing grant can never silently
  arrive as "allowed" (the "slot exists, artifact never arrives" failure) — absence = deny, everywhere.
- **[Hitsuzen / Mottainai]** — checked; no LLM is asked to derive a determinable, and no earlier-stage
  artifact is regenerated (the safe-writer + redactor + nonce pattern are all forwarded, not rebuilt).

---

## 1. Problem Statement

`--mirror-cockpit` lets a **local single-user** serve persist a *redacted* session mirror so the
agentic Grafana cockpit populates (FR-WM2-5d, softened for local). **Cloud/hosted stays strict**: the
chat panel is disabled and no disk mirror is written, because a hosted surface has *no per-tenant trust
substrate* — full cloud-write auth/tenancy is deferred (OQ-GE-7). Result: **no parity** — a cloud
deployment can never surface an agentic session in the cockpit.

We want **parity on demand**: a way to *temporarily* let a cloud deployment do the mirror — but only
under an explicit, human-granted, tightly-bounded authorization, **never as a standing capability**.
The bounding is the whole point: a single (initially) use, an expiration, revocable, least-privilege,
fail-closed. This is a **narrow authorization primitive**, deliberately *not* the full tenancy model
(that stays deferred).

| Aspect | Local (today) | Cloud (today) | Cloud WITH a grant (this doc) |
|--------|---------------|---------------|-------------------------------|
| Agentic chat (token-spend) | enabled | **disabled** (`chat_factory=None`) | temporarily enabled — chat turns **+ proposal-apply writes** (OQ-6 resolved) |
| Disk mirror → cockpit | on by default (redacted) | **off** (forced) | temporarily on (redacted), **bounded** |
| Authorization | implicit (your machine) | none (strict deny) | **explicit, human-issued, expiring, use-limited** |

---

## 2. Requirements

> The **grant** = a temporary authorization artifact/record that, while valid, permits the
> cockpit-mirror behavior on a cloud deployment. Its concrete *form* is **TBD** (OQ-1).

- **FR-1 — Human-issued grant enables cloud mirror parity.** A grant, and only a grant, temporarily
  authorizes a cloud deployment to perform the (redacted) cockpit mirror that is otherwise local-only.
  Absent a valid grant, cloud behavior is **exactly today's strict posture** (FR-WM2-5d hosted / GE-M5).
- **FR-2 — Use-limited.** A grant carries a **maximum number of uses**; the **initial/default is 1**
  ("1 to start"). Each authorized action **consumes one use**. At 0 remaining, the grant is void.
  (Whether the limit is later configurable > 1 is in scope of the design, default stays 1 — see OQ-3.)
- **FR-3 — Time-expiring.** A grant carries an **absolute expiration time**. After expiry it is void
  **regardless of remaining uses**. (Default window TBD — OQ-3.)
- **FR-4 — Revocable.** The issuing human (or an authorized principal) can **revoke** a grant before
  expiry/exhaustion; a revoked grant is immediately void.
- **FR-5 — Fail-closed / default-deny (per-trigger acceptance matrix; R1-F5).** No valid grant ⇒ **no
  parity**. **Each** of the following triggers must **independently** produce the strict
  `cloud_write_deferred` 501 **with no mirror write and no token spend** — verified one case per trigger:
  **{absent, expired, exhausted (uses=0), revoked, store-unavailable, clock-untrusted / skew-exceeded}**
  (clock row parameterized by OQ-8's tolerance). No partial success on any trigger.
- **FR-6 — Human-in-the-loop issuance, out-of-band via the control plane (OQ-4 resolved).** A grant is
  minted **only** by a human running a **control-plane action** (`startd8 cloud-grant issue …`) with the
  **deployment platform's own identity** (SSH / cloud IAM / kubectl / CI) — issuance is **not** a route on
  the served app, and the cloud process/agent **cannot self-issue** or self-extend. Issuer trust binds to
  the *real, already-existing* platform identity substrate rather than a home-rolled secret. The
  **issuance credential is DISTINCT from the served app's consumer `--api-key`** (a leaked consumer key
  can never mint). **Accepted residual:** per-*person* attribution is only as fine as the control-plane
  identity provides — the audit record captures **control-plane actor (platform-provided) + a required
  issuer label + issuance timestamp** (FR-10); a verified per-principal identity awaits OQ-GE-7, and the
  audit field is shaped so real IdP identity drops in later without redesign.
- **FR-7 — Single-consumption / anti-replay + ordering (R1-F4).** `resolve`+`consume` is a **single
  atomic operation** (not resolve-then-later-consume). **Consume-before-act**; if the authorized action
  then fails, the use is **forfeit** (not silently refunded — a refund path is a replay vector). A
  **store-unavailable *during* consume ⇒ deny with no use debited**. Anti-replay: a spent use can never
  be redeemed twice (server-side counter). **AC:** N parallel redemptions of a 1-use grant → **exactly
  one** succeeds; store-fails-mid-consume → deny, uses unchanged.
- **FR-8 — Least-privilege scope + wrong-target-denies (R1-F8).** A grant authorizes **only** the
  granted capability (nothing broader). Its scope is **normative**: `target = {deployment_id,
  project_id, capability}`. `resolve()` MUST **reject a grant whose bound target ≠ the requesting
  deployment/project/capability** — so a grant issued for deployment A cannot be replayed against
  deployment B. (Exact identifier source stays OQ-5; the *shape* + mismatch-denies rule are committed now.)
- **FR-9 — Redaction + telemetry privacy unchanged.** When a grant is active, the mirror content is
  still **redacted** (`fde.redaction.redact`) and the telemetry-privacy contract (FR-WM2-14a — no
  message text in spans/logs) still holds. The grant relaxes **where** the mirror may run, **never**
  the scrubbing.
- **FR-10 — Auditable + audit-write fail-closed (R1-F6/R1-F7).** Every **issuance, consumption, expiry,
  and revocation** is recorded (issuance-source, issuer-label, when, target scope, uses-remaining) to an
  **append-only** log, under the no-message-text privacy rule (FR-WM2-14a). **If the audit write fails,
  the corresponding action MUST NOT proceed** — an unauditable elevation is not permitted (fail-closed).
  **AC:** audit sink unavailable → issuance/consume denies; no orphan action without a matching audit entry.
- **FR-11 — Layered on the api-key, not a replacement.** The grant composes with the current `--cloud`
  read-only posture and the coarse `--api-key` gate (`server/auth.py:APIKeyMiddleware` — a static
  single-key POST door with no use-count/expiry/revocation). The grant is the **metered, expiring,
  single-use elevation** layered on that door; it is not a new standing auth model (OQ-GE-7 stays
  deferred until the real tenancy work).

### Group B — Chat-write parity (new, from planning; OQ-6 resolved)

- **FR-12 — Grant-capable cloud build + pre-message surface gated (R1-F9).** In cloud mode **with a
  grant store configured**, the app is built **with** a `chat_factory` (sessions *can* be created); the
  build-time `chat_factory = None` cloud-null applies **only** when no grant store is configured. Opening
  the factory MUST NOT expose a live chat surface pre-grant: **the chat-page GET and session creation
  (`chats.put`) themselves consult the seam (FR-13)** — a grant-capable build with no valid grant returns
  the strict-deny view and creates **no** session. **AC:** cloud build + no grant → chat page GET =
  strict-deny, `chats.put` denies.
- **FR-13 — Single effective-posture resolution + structural default-deny (R1-F2/R1-S8).** One helper —
  `_cloud_capability(request, capability) -> Decision` (typed: allow / deferred+reason) — is consulted at
  **every** chat/write gate, and **the consume happens INSIDE the seam** (no call site calls the store's
  consume directly — prevents a check/use split drifting back across sites). The ~6 scattered `if cloud:`
  denials + the build-time null are **replaced by** this one rule. **Structural guard (not just a
  grep):** chat/write routes are registered through a mechanism the test enumerates so that a route
  **not** wired to the seam **fails closed (denies)** — omission of the seam = **deny, never allow**.
  **AC:** a synthetic write route bypassing the seam returns 501, not 200.
- **FR-14 — Cloud-write trust chain as an ordered AND-gate (R1-F1, critical).** A non-loopback write is
  honored **iff ALL of**: (1) api-key valid **AND** (2) a grant **resolves** for the target+capability
  **AND** (3) that grant has **uses>0, unexpired, unrevoked** **AND** (4) **Host/Origin ∈ configured
  cloud origin**. **Absence or failure of ANY factor ⇒ 501**, and **no factor may be skipped by any
  endpoint**. Explicitly: api-key alone (no grant) denies; grant alone (no api-key) denies. The local
  loopback-Host + local-session-CSRF chain does not apply on a non-loopback surface. Here the `--api-key`
  is the **consumer door only** — it is **distinct from the issuance credential** (FR-6, OQ-4), and the
  served app **only consumes/validates** grants; it can never mint one. **AC:** a 2⁴ factor-present/absent
  truth table — only the all-present row allows; all 15 others return 501.
- **FR-15 — Unit of use = one agentic session, with non-defeatable caps + per-action re-validation
  (R1-F3/R1-F10).** A "use" is consumed **atomically at session creation** (default 1, FR-2). Token
  spend **within** the use is bounded by the session's turn-cap, per-session rate-limit, and budget —
  which in grant-built cloud mode **MUST be present, server-enforced, and NOT disable-able or
  raise-able via request-controlled input** (a session created under a grant with any cap absent ⇒
  **deny**). Consuming the use at creation MUST NOT buy an **unbounded post-expiry session**: the
  per-action seam (FR-13) **re-validates grant liveness on every turn/apply**, so a session created just
  before expiry/revocation is denied on its **next** action. **AC:** caps unset/zeroed ⇒ creation denies;
  create at T, revoke/expire at T+ε, next turn at T+2ε ⇒ deny despite the use already consumed.
- **FR-16 — Safe-writer + redaction path unchanged.** Proposal-apply under a grant still goes through
  `apply_proposal` (the same validation/safe-writer); the mirror is still redacted
  (`fde.redaction.redact`). The grant lifts the **cloud-deny only** — it does **not** bypass write
  validation, redaction, or the telemetry-privacy contract (FR-9).

---

## 3. Non-Requirements

- **NR-1 — Not the tenancy/auth model.** This is a narrow, human-gated, temporary elevation. Full
  multi-tenant RBAC / cloud-write auth remains **deferred** (OQ-GE-7); this doc does not resolve it.
- **NR-2 — Not a standing/always-on cloud mirror.** Parity is transient by construction (use-limited +
  expiring). There is no "just leave it on for cloud" mode.
- **NR-3 — No self-service issuance by the agent or cloud process** (FR-6).
- **NR-6 — The served cloud app has no mint/issuance endpoint (OQ-4).** It only **reads + consumes +
  validates** grants. Issuance (and revocation) is a **control-plane** action bound to platform identity,
  never a route on the served surface — so the served app's attack surface carries no privileged
  grant-creation path, and the consumer `--api-key` can never mint.
- **NR-4 — Does not weaken redaction or telemetry privacy** (FR-9) — softens *placement*, not scrubbing.
- **NR-5 — The concrete mechanism is out of scope of THIS draft** — see §4 OQ-1 (that's the
  "to be determined" the title calls out; it's resolved in the planning pass, not asserted here).

---

## 4. Open Questions (the TBDs — resolve in the planning pass)

- **OQ-1 → RESOLVED (planning): a server-side grant record + atomic counter.** A signed token can't be
  revoked or made truly single-use without server state, so FR-4 (revoke) + FR-7 (anti-replay) settle
  it. Reuses the `consultation/serve.py` consume-before-act/anti-replay pattern (FR-SRV-5).
- **OQ-2 → RESOLVED (planning): enforced server-side** (per-request resolve + atomic consume).
- **OQ-3 — Defaults (still open).** Expiration window (lean: 15 min) and use-count (fixed at 1, or
  configurable ≥1?). Decide in CRP/impl.
- **OQ-4 → RESOLVED (user decision): out-of-band control-plane issuance.** Issuance is a **control-plane
  CLI** (`startd8 cloud-grant issue`) bound to the **deployment platform's own identity** (SSH / cloud
  IAM / kubectl / CI); the served app has **no mint route** (consume-only); the **issuance credential is
  distinct from the consumer `--api-key`**. Issuer trust reuses the real platform identity substrate
  (Genchi Genbutsu), not a home-rolled secret (FR-6, NR-6). **Residual (accepted, not open):** per-person
  attribution is only as fine as the control-plane identity until **OQ-GE-7** wires a real IdP into the
  issuer field. Store-backend nuance: issuance-vs-consumption privilege split is **cleanly enforceable
  with a DB/service backend**, **convention-level with a shared file store** (a plan/M4 decision).
- **OQ-5 — Scope binding (lean).** Bound to **deployment + project + capability**; consumption is
  **session-scoped** (FR-15). Confirm the exact bound identifier in impl.
- **OQ-6 → RESOLVED (explicit direction): the agentic chat-write path** — chat turns + proposal-apply +
  redacted mirror (see §0, FR-12–16). Not split into two scopes for v1; a single `chat-write`
  capability covers all three (a finer split is a future refinement).
- **OQ-7 → RESOLVED (planning): fail-closed on the next gated action.** The grant is checked
  per-gated-action (FR-13), so an expiry/revocation mid-session denies the **next** turn/apply while the
  in-flight action completes. No silent continuation.
- **OQ-8 — Clock trust (open).** Absolute expiry needs a trusted server clock; define skew tolerance;
  store/clock unavailable → **deny** (FR-5). Confirm in impl.
- **OQ-9 → RESOLVED (planning): the grant layers ON the api-key** (api-key = coarse door; grant =
  metered/expiring elevation) — FR-11/FR-14.
- **OQ-10 (NEW) — Consumption granularity.** v1 = **per session** (FR-15). Alternatives (per-turn,
  per-apply) give tighter metering but a worse UX and more bookkeeping; revisit if session-granular
  metering proves too coarse against real spend.
- **OQ-11 (NEW) — Cloud Origin/Host validation.** FR-14 replaces the loopback-Host check with
  validation against the *configured cloud origin* — confirm the exact allowed-Origin/Host policy and
  how it's configured for a real deployment (paired with the api-key).
- **OQ-12 (NEW, from M2) — Session-creation auth surface / human-browser UX.** M2 consumes the grant at
  the chat-page **GET** (session creation), which reads `X-API-Key`/`Origin` headers — an authenticated
  *client* (reverse proxy / CLI) can present them, but a **bare browser navigating the URL cannot**. So
  the current cloud chat is reachable only by a header-presenting client. Decide the human-browser cloud
  flow (an auth-injecting reverse proxy? a login → session-mint POST?) before a human-facing cloud UX.

> **Note (scope discipline):** this is an *authorization* primitive, not a durable-execution one — it
> does **not** require Temporal or any workflow engine (see the prior Temporal NO-GO). Keep it small.

---

*v0.1 — Draft. Mechanism (OQ-1) left TBD.*

*v0.2 — Post-planning self-reflective update (planned against `web.py`/`serve.py`/`server/auth.py`/
`apply_proposal`). 6 discoveries reshaped the spec; added FR-12–16 (grant-capable build, single
effective-posture, cloud-write trust chain, unit-of-use, safe-writer-preserved); resolved OQ-1/2/6/7/9;
added OQ-10/11. OQ-6 resolved to the **agentic chat-write path** per explicit direction.*

*v0.3 — Post lessons-learned hardening. Applied 3 lessons: reuse-first (reuse the FR-SRV-5 nonce pattern
+ `apply_proposal`, don't reinvent), verify-against-source (all named symbols exist; grant primitive is
the only to-be-created one), single-source ownership.*

*v0.3.1 — Post design-principle hardening. Applied 4 principles: Accidental-Complexity (FR-13 one rule
replaces six gates — the headline move), Genchi Genbutsu (bind to the real api-key/record substrate +
respect the boundary), Context-Correctness (default-deny reaches every gate), Hitsuzen/Mottainai
(nothing re-derived/regenerated). Residual open: OQ-3/4/8/10/11.*

*v0.4 — Post-CRP R1 triage (security-weighted). All 10 F-suggestions ACCEPTED + applied: FR-14 → an
ordered AND-gate with a 2⁴ truth table (F1); FR-13 → structural default-deny for new endpoints +
consume-inside-seam (F2/S8); FR-15 → non-defeatable caps + per-action re-validation of an idle session
(F3/F10); FR-7 → single-atomic resolve+consume, forfeit-on-failure, TOCTOU deny (F4); FR-5 → 6-trigger
acceptance matrix (F5); FR-6/FR-10 → the shared-key attribution gap as an accepted shippable condition +
issuer-label + audit-write fail-closed (F6/F7); FR-8 → normative scope fields + wrong-target-denies (F8);
FR-12 → the pre-message chat-page/session-create surface must consult the seam (F9). See Appendix A.*

*v0.5 — OQ-4 (the issuer crux) resolved by user decision: **out-of-band control-plane issuance**. FR-6
rewritten (control-plane CLI bound to platform identity; issuance credential ≠ consumer `--api-key`);
FR-14 clarified (`--api-key` = consumer door only; served app consume-only); new **NR-6** (no mint route
on the served app); OQ-4 moved from open to resolved. Reshapes plan M4. Residual per-person attribution
until OQ-GE-7 (accepted). M0 (CloudGrant primitive) already shipped (PR #198).*

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
| R1-F1 | FR-14 as ordered AND-gate + 2⁴ truth table | R1 (claude-opus-4-8[1m]) | Merged into **FR-14**: iff all-4 factors; 15 partial rows 501; no skip. | 2026-07-11 |
| R1-F2 | FR-13 structural default-deny for new endpoints | R1 | Merged into **FR-13**: route-registry guard, omission=deny, synthetic-route AC. | 2026-07-11 |
| R1-F3 | FR-15 caps must exist + non-defeatable | R1 | Merged into **FR-15**: caps present/server-enforced/non-raisable, else deny. | 2026-07-11 |
| R1-F4 | FR-7 consume ordering + TOCTOU | R1 | Merged into **FR-7**: single-atomic resolve+consume, forfeit-on-fail, mid-consume-fail deny. | 2026-07-11 |
| R1-F5 | FR-5 per-trigger acceptance matrix | R1 | Merged into **FR-5**: 6 triggers each → 501 + no write/spend. | 2026-07-11 |
| R1-F6 | FR-6/FR-10 attribution gap as shippable condition | R1 | Merged into **FR-6/FR-10**: shared-key residual stated; issuer-label + source captured. | 2026-07-11 |
| R1-F7 | FR-10 audit-write fail-closed + append-only | R1 | Merged into **FR-10**: audit-fail ⇒ action denies; append-only; AC. | 2026-07-11 |
| R1-F8 | FR-8 normative scope + wrong-target-denies | R1 | Merged into **FR-8**: `{deployment,project,capability}`; resolve rejects mismatch. | 2026-07-11 |
| R1-F9 | FR-12 pre-message surface gated | R1 | Merged into **FR-12**: chat-page GET + `chats.put` consult the seam; no-grant → no session. | 2026-07-11 |
| R1-F10 | FR-15 expiry voids idle session | R1 | Merged into **FR-15**: per-turn re-validation; created-just-before-expiry denies next action. | 2026-07-11 |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none) | — | R1 | All 10 R1 F-suggestions accepted. | 2026-07-11 |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — claude-opus-4-8[1m] — 2026-07-11 16:31 UTC

- **Reviewer**: claude-opus-4-8[1m]
- **Scope**: Security-weighted CRP of the cloud-authorization-grant requirements. Focus (per sponsor): issuer trust (OQ-4), cloud-write trust-chain completeness/non-bypassability (FR-14), un-gated write leak past the single seam (FR-12/13), spend-bounding of session-granular metering (FR-15), fail-closed correctness under expiry/revocation/store-unavailable/clock-untrusted with race-free atomic consume (FR-5/FR-7/OQ-7). Honors the settled/do-not-relitigate list.

**Executive summary (top risks / blocking gaps):**
- FR-14's trust chain names the *ingredients* (api-key + grant + scope + configured-Origin) but never states the **conjunction/ordering as a testable AND-gate**, nor forbids a partial chain — the highest-value gap for a non-bypassable cloud-write door.
- FR-13 asserts "no residual `if cloud:` outside the seam" but has **no regression-guard requirement for NEW endpoints** — a future write route can silently skip the seam and default-*allow* (fail-open by omission), the exact leak the doc says it prevents.
- FR-6/OQ-4 issuer trust rests on "whoever holds the operator `--api-key`", but the api-key is described as a **static single shared key** — so "human-issued only" (FR-6) and "who + audit" (FR-10) are **not actually attributable to a person**; this is a stated-vs-real gap that should be an explicit acceptance condition, not left implicit in OQ-4.
- FR-15 bounds spend "per session by the session's inner caps" but never **requires those inner caps to exist and be non-defeatable in cloud mode** — if a grant-built cloud app can be configured with no/large turn/budget caps, "1 use" is unbounded. The bound is asserted, not required.
- FR-7 atomic-consume + FR-5 mid-flight checks have **no stated race/ordering requirement** (consume-then-act vs act-then-consume) and no requirement that a store-unavailable *during* consume denies — a check-time/use-time (TOCTOU) gap.
- FR-5 lists deny triggers but omits a **positive acceptance criterion per trigger** (each of: absent / expired / revoked / exhausted / store-unavailable / clock-untrusted must independently produce the strict 501) — currently untestable as a set.
- FR-10 audit lacks a **tamper/append-only + failure-mode** clause (what happens if the audit write fails — does the action proceed?). For an elevation primitive, audit-write failure should fail-closed.
- OQ-8 clock trust is open but FR-3/FR-5 depend on it as load-bearing; the requirement should state the **deny-on-clock-untrusted acceptance test** even while the tolerance value stays open.

**Numbered suggestions:**

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F1 | Security | critical | Rewrite FR-14 to state the trust chain as an explicit **ordered AND-gate that fails closed on any missing factor**: "a non-loopback write is honored **iff** (api-key valid) AND (grant resolves for the target+capability) AND (grant has uses>0, unexpired, unrevoked) AND (Host/Origin ∈ configured cloud origin) — absence or failure of **any** factor ⇒ 501, and no factor may be skipped by any endpoint." Add that api-key alone (no grant) and grant alone (no api-key) both deny. | The doc currently lists the four ingredients but never binds them as a conjunction, an order, or a total function — leaving "is the chain non-bypassable?" (the sponsor's crux #2) unanswerable and untestable. | FR-14 body | Truth-table test: enumerate all 2^4 factor-present/absent combinations; assert only the all-present row allows, all 15 others 501. |
| R1-F2 | Validation | critical | Add an acceptance criterion to FR-13 requiring a **default-deny regression guard for new endpoints**, not only the "no residual `if cloud:`" grep: any chat/write route must be **structurally forced** through `_cloud_capability` (e.g. a decorator/registry the test enumerates), so a newly-added route that forgets the seam **denies** rather than silently allows. State the failure mode explicitly: "omission of the seam = deny, never allow." | The "no residual `if cloud:`" test (crux #3) only catches *leftover* denials; it cannot catch a *new* write endpoint that never had one — that endpoint would fail-open. This is the regression the plan's R1 test cannot see. | FR-13, after the residual-grep sentence | Test: register a synthetic write route without the seam; assert it returns 501 (deny-by-default), not 200. |
| R1-F3 | Security | high | Make FR-15's spend bound a **requirement on the caps, not an assumption**: "In grant-built cloud mode, the session turn-cap, per-session rate-limit, and budget cap **must be present and enforced server-side, and must not be disable-able or raise-able via request-controlled input**; a session created under a grant with any of these absent ⇒ deny." | FR-15 says spend is bounded "by the session's existing caps" but never requires them to exist/be non-defeatable in cloud mode — so "1 use ≠ unbounded spend" (crux #4) is currently only true if an operator happens to configure caps. | FR-15 body | Test: create a grant session with caps unset/zeroed; assert session creation denies. Test: request cannot override cap values. |
| R1-F4 | Risks | high | Add an explicit **atomic consume ordering + TOCTOU** requirement to FR-7: state whether consumption is **consume-before-act** (and what happens if the action then fails — is the use refunded or forfeit?), require the resolve+consume to be a **single atomic operation** (not resolve-then-later-consume), and require **store-unavailable *during* consume ⇒ deny + no use debited**. | FR-7 says "atomic and non-replayable" but not the *ordering* relative to the action, nor the failure semantics — the gap where a check-then-consume race (crux #5) or a mid-consume store failure could double-spend or silently allow. | FR-7 body | Concurrency test: N parallel redemptions of a 1-use grant → exactly 1 succeeds. Fault test: store fails mid-consume → deny, uses unchanged. |
| R1-F5 | Validation | high | Expand FR-5 into a **per-trigger acceptance matrix**: each of {absent, expired, exhausted (uses=0), revoked, store-unavailable, clock-untrusted/skew-exceeded} must **independently** produce the strict `cloud_write_deferred` 501 with no partial success. Reference OQ-8's skew tolerance as the parameter for the clock row. | FR-5 enumerates ambiguity sources in prose but gives no testable one-per-trigger criterion — "is every one a deny?" (crux #5) can't be verified as a set today. | FR-5 body, as a bullet list or table | Parametrized test, one case per trigger, each asserting 501 + no mirror write + no token spend. |
| R1-F6 | Security | high | Add a sub-clause to FR-6/FR-10 acknowledging the **attribution gap** and making it a shippable condition: because issuance is gated by a **shared static `--api-key`** (OQ-4 lean), "human-issued" and the FR-10 `who` are attributable only to *the credential holder, not a person*; require the audit record to at minimum capture **issuance source (CLI/admin path) + timestamp + a caller-supplied issuer label**, and flag that true per-principal attribution needs OQ-GE-7. | Sponsor crux #1: the whole bound collapses if the issuer isn't trustworthy. Today FR-6 "only a human can mint" is not enforceable against a shared key — the doc should say so as an accepted residual, not bury it in OQ-4. | FR-6 and FR-10 bodies | Review-time: confirm audit record schema includes issuer-source + label fields; confirm OQ-4 residual is stated as accepted risk, not open. |
| R1-F7 | Ops | medium | Add an **audit-write-failure fail-closed** clause to FR-10: if the issuance/consumption audit record cannot be written, the corresponding action **must not proceed** (an unauditable elevation is not permitted); the audit log must be append-only. | FR-10 requires auditing but is silent on what happens when the audit write itself fails — for an elevation primitive, a silently-unaudited consume defeats traceability. | FR-10 body | Fault test: audit sink unavailable → issuance/consume denies; assert no orphan action without a matching audit entry. |
| R1-F8 | Data | medium | Specify the **CloudGrant scope-binding fields as normative** in FR-8 (target = {deployment_id, project_id, capability}) and require **resolve() to reject a grant whose bound target ≠ the requesting deployment/project** — closing the "wrong-target grant honored" hole. Currently OQ-5 leaves the exact identifier open, but FR-8 can commit the *shape* and the mismatch-denies rule now. | FR-8 says "bound to a specific target" but the binding is only illustrative (deployment/project/session — OQ-5); without a mismatch-denies rule, a grant issued for deployment A could be replayed against deployment B. | FR-8 body | Test: grant bound to deployment A presented on deployment B ⇒ deny. |

### Stress-test / adversarial pass

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F9 | Security | high | Add a requirement covering the **chat-page GET / session-creation path** explicitly: FR-12 makes the app grant-*capable* by building a `chat_factory`, but the requirements never state that **rendering the chat page or creating a session** must itself consult the seam. Require that the page GET and `chats.put` both go through `_cloud_capability` so a grant-capable cloud build does not expose a live chat surface before a grant is validated. | Sponsor crux #2 asks about "the chat page GET, session creation" as a possible un-chained write path. FR-12 opens the factory; nothing in the reqs re-closes the pre-message surface. | New sub-bullet under FR-12/FR-13 | Test: cloud build + no grant → chat page GET returns the strict-deny view and `chats.put` denies (no session object created). |
| R1-F10 | Risks | medium | Require **expiry to void an already-created-but-idle session** (FR-3/FR-15 interaction): FR-15 consumes the use at session creation and FR-3 says expiry voids mid-window, but the doc doesn't state that a session created just before expiry cannot keep spending turns *after* expiry. Require the per-action check (FR-13/OQ-7) to re-validate grant liveness on **every turn/apply**, not just at creation. | The "1 use = 1 session" model + per-action check must compose so that consuming the use at creation does not buy an unbounded post-expiry session — otherwise expiry (crux #5) is defeated by early session creation. | FR-15 body, cross-ref FR-3/OQ-7 | Test: create session at T; revoke/expire at T+ε; next turn at T+2ε ⇒ deny even though the use was already consumed. |
