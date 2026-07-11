# Temporary Cloud Authorization Grant — Implementation Plan

**Version:** 1.2 (OQ-4 issuer model resolved)
**Date:** 2026-07-11
**Status:** Draft — CRP R1 applied + OQ-4 resolved (control-plane issuance). M0 shipped (PR #198).
**Requirements:** `CLOUD_MIRROR_GRANT_REQUIREMENTS.md` (v0.5)
**Direction:** the grant re-enables the **agentic chat-write path** that `--cloud` fully disables
(not merely the disk mirror).

---

## 1. Approach

A cloud deployment normally serves **read/preview-only** (GE-M5): the agentic chat panel is disabled
and every write/LLM endpoint returns `501 cloud_write_deferred`. This plan adds a **server-side grant
record** (human-issued, use-limited, expiring, revocable) that a cloud deployment consults **per gated
action** to *temporarily* lift that deny — re-enabling the token-spending Concierge chat, its
proposal-apply writes, and the redacted cockpit mirror — for a bounded window.

**The load-bearing realization from planning:** `--cloud` is enforced at **two layers**, and one is
**build-time**:

| Gate | Where | Layer |
|------|-------|-------|
| `chat_factory = None` (no session can be created) | `web.py:677` | **build-time** |
| `/capture/apply` → `_cloud_deferred("capture")` | `web.py:773` | per-request |
| `_concierge_write_gate` → `_cloud_deferred()` | `web.py:915` | per-request |
| `/concierge/chat` page → "unavailable on cloud" | `web.py:1108` | per-request |
| `/concierge/chat/message` → `_cloud_deferred("chat")` | `web.py:1163` | per-request |
| `/concierge/chat/*` (2nd) → `_cloud_deferred("chat")` | `web.py:1261` | per-request |

A per-request grant **cannot un-null a build-time factory** — so the app must be *built* grant-capable,
then gate at request time. And the ~6 scattered `if cloud:` denials must collapse into **one**
effective-posture resolution the grant plugs into (not six edited call sites).

---

## 2. Design

### 2.1 The grant record + store
- A `CloudGrant` record: `{id, target(scope), capability, uses_remaining, expires_at, issued_by,
  issued_at, revoked}`. Persisted in a small trusted **server-side store** (file/db behind an interface).
- **Reuse the `consultation/serve.py` pattern** (FR-SRV-5): **consume-before-act** + **anti-replay via
  a server-side counter** (a signed token can't be revoked or made truly single-use — rejected).
- Ops: `issue`, `resolve(target, capability) -> grant|None` (rejects a target mismatch — FR-8),
  `consume(grant) -> bool`, `revoke(id)`. **`resolve`+`consume` is a SINGLE atomic op** (not
  resolve-then-later-consume); **consume-before-act, use forfeit on action-failure** (no refund =
  no replay vector); **store-unavailable mid-consume ⇒ deny, no debit** (R1-S4). *(FR-7)*

### 2.2 One effective-posture resolution (the anti-accidental-complexity move)
- Add `_cloud_capability(request, capability) -> Decision` (typed: `allow` / `deferred(reason)`) used at
  **every** gate. **The consume happens INSIDE the seam** — no call site calls `store.consume` directly,
  so a check/use split can't drift back across sites (R1-S8, preserves FR-13's single-source).
  - **local** (non-cloud) → allow. · **cloud + no valid grant** → `_cloud_deferred(...)`. · **cloud +
    valid grant** → allow + atomically consume (session-granular; §2.4).
- Replace all six `if cloud:` denials + the build-time `chat_factory=None` with this single check.
  **Structural default-deny (R1-S2):** chat/write routes are registered through a mechanism the test
  enumerates; a route **not** wired to the seam **denies** (omission = deny, never allow) — a grep for
  residual `if cloud:` cannot catch a *new* un-chained endpoint, this does.

### 2.3 Cloud-write trust chain (the loopback problem)
- The local write chain is **loopback-Host + local-session CSRF** (`_host_ok`, `sessions.valid`). On a
  **non-loopback** cloud surface `_host_ok` fails regardless of the grant. So the grant path needs its
  **own** trust chain: **`--api-key` (the CONSUMER door, `server/auth.py`) + a valid grant + scope
  binding**, with Host/Origin validated against the *configured cloud origin* instead of loopback.
- **Consume-only served app (OQ-4/NR-6):** the served app never *mints* — it only reads/consumes/validates
  grants. Issuance is out-of-band control-plane (M4), and the consumer `--api-key` is **distinct from the
  issuance credential**, so a leaked consumer key can knock but never create a grant.
- The grant **layers on** the api-key (api-key = who may knock; grant = metered, expiring permission
  to do the elevated thing). Full per-principal tenancy stays **OQ-GE-7 deferred**.

### 2.4 Unit of consumption (safety metering)
- A **"use" = one authorized agentic session**, consumed atomically at **session creation**
  (`chats.put`). The session's **turn cap + per-session rate-limit + budget** bound spend *within* the
  use — and in grant-built cloud mode these **MUST be present, server-enforced, and not request-
  overridable; session creation denies if any is absent** (R1-S3). Consuming at creation must NOT buy an
  unbounded post-expiry session: the seam **re-validates grant liveness on every turn/apply** (R1-S9),
  so a session created just before expiry/revocation is denied on its next action. (Granularity
  alternatives — per-turn, per-apply — parked as OQ-10.)

### 2.5 Safety invariants preserved
- **Writes still go through `apply_proposal`** (the same safe-writer + validation); the grant lifts the
  *cloud-deny*, it does **not** bypass write validation.
- **Redaction unchanged** (`fde.redaction.redact`) and **telemetry privacy unchanged** (FR-WM2-14a,
  no message text) — the mirror under a grant is still redacted.
- **Fail-closed**: no/expired/revoked grant, store unavailable, or clock-untrusted → deny.

---

## 3. Milestones

- **M0 — Grant primitive.** `CloudGrant` model + store + single-atomic `resolve+consume` + `revoke` +
  expiry/clock. **Tests (R1-S4):** N-parallel-redemption of a 1-use grant → exactly 1 wins;
  store-fails-mid-consume → deny + uses unchanged; consume-before-act with use-forfeit-on-failure.
- **M1 — Effective-posture seam.** Introduce `_cloud_capability`; refactor the six `if cloud:` gates +
  the build-time factory decision to consult it. **Behavior-preserving when no grant store is configured**
  (golden: cloud-without-grant == today, byte-for-byte). **Structural default-deny guard (R1-S2):** a
  synthetic write route **not** wired to the seam must return 501, not 200.
- **M2 — Grant-capable build + trust chain.** ✅ **SHIPPED** (core). `build_kickoff_app(..., cloud=True,
  grant_store=…, deployment_id=…, project_id=…, cloud_origins=…)` builds *with* a chat_factory; the
  `_cloud_capability` seam resolves the FR-14 trust chain; session creation (chat page GET) consumes one
  use (FR-15). **Done:** (a) **trust-chain 2⁴ truth table (R1-S1)** — `cloud_grant.evaluate_trust_chain`,
  ordered AND-gate (api-key → Origin → live grant), api-key/Origin short-circuit before consume; only
  all-present allows, 15 partial rows deny; (c) **pre-message surface (R1-S7)** — cloud+no-grant → chat
  page unavailable + no session; full chain → session created + grant consumed; missing factor → no
  session, no spend. **Deferred to M3 (correct sequencing):** (b) **caps-present gate (R1-S3)** — the
  turn/rate/budget caps live on the chat-turn path M3 enables, so the caps gate lands with it. **New
  (OQ-12):** session creation is a **GET**, so a bare browser can't present `X-API-Key` — an
  authenticated *client* (proxy/CLI) can; human-browser cloud UX is a later concern.
- **M3 — Chat turns under grant + per-turn re-validation.** ✅ **SHIPPED** (conversation half). The
  **chat message turn** is enabled on cloud under a grant: the session's grant is **bound at creation**
  and each turn **re-validates liveness without re-consuming** (`_cloud_revalidate` → `store.revalidate`,
  R1-S9), so a session created just before expiry/revocation is denied on its **next** turn. The
  loopback-Host check is bypassed on the cloud path (grant + api-key middleware + Origin is the substrate,
  FR-14). **Caps (R1-S3):** the per-session message rate-limit (`sessions.rate_ok`) + the AgenticSession
  turn/budget caps bound spend within the use and are **not request-raisable** (no such param) — present
  by construction on any grant session; this codebase has **no caps-disable path**, so the "caps-unset →
  deny" branch is unreachable (documented, not a vacuous gate). Tests: turn works live; no re-consume;
  denied after expiry/revocation/wrong-Origin/no-binding.
- **M3b — the WRITE half (proposal-apply + mirror under grant).** ✅ **SHIPPED.** `chat/confirm` is enabled
  on cloud under a grant via the **same per-turn revalidation** (no re-consume) and reaches the
  **UNCHANGED `apply_proposal` safe-writer** (FR-16) — the loopback-Host + local-CSRF chain replaced by
  grant + api-key + Origin (FR-14); local keeps `_concierge_write_gate`. The **redacted cockpit mirror** is
  allowed for a grant-authorized cloud session (the grant temporarily lifts the hosted-strict no-disk
  posture for that session) — **still redacted** (FR-9): a planted secret never reaches disk. Tests:
  confirm reaches the safe-writer under grant / denied after expiry / deferred with no grant; mirror
  written + redacted; no-grant → no mirror. Completes the OQ-6 chat-write path (chat + apply + mirror).
- **M4a — Durable FileGrantStore + append-only AuditLog.** ✅ **SHIPPED.** `FileGrantStore` (JSON on
  disk): each op **reloads** the file (a CLI-issued grant is visible to the served app) under an
  **inter-process `fcntl` lock** (consume is atomic across app instances — FR-7 anti-replay holds
  multi-process), atomic temp-then-rename persist. `AuditLog` = append-only JSONL; the store audits
  issue/consume/revoke **before** committing and is **fail-closed** — an un-auditable issuance raises /
  consume denies with **no debit** (R1-F7/R1-S6). No message text (FR-WM2-14a). Exempted in the
  guided-experience write-floor audit as endpoint/spend-safety state (same pattern as `stakeholder_run.py`).
  **M4b (next): the operator CLI** (`startd8 cloud-grant issue|revoke|list`) on top of this store.
- **M4b — Operator `cloud-grant` CLI.** ✅ **SHIPPED.** `startd8 cloud-grant issue|revoke|list`
  (`cli_cloud_grant.py`, registered in `cli.py`) on top of the M4a store: `issue --deployment --project
  --issued-by [--capability chat-write] [--uses 1] [--ttl 900] --store --audit` (fail-closed — an
  un-writable store/audit aborts with no grant); `revoke <id>`; `list`. Round-trip tested: what the CLI
  issues out-of-band, a `FileGrantStore` (the served app) consumes.
- **M4 — Control-plane issuance + revocation + audit fail-closed (OQ-4 resolved).** ✅ **SHIPPED** (M4a + M4b).
  Issuance/revocation is a **control-plane CLI** — `startd8 cloud-grant issue|revoke|list` — run with the **platform's identity**,
  writing the grant store **out-of-band**; the **served app has NO mint route** (consume-only; NR-6) and
  the issuance credential is **distinct from the consumer `--api-key`**. **Store-backend privilege split:**
  issuance (create-with-N-uses) vs consumption (decrement-existing) is **cleanly enforceable with a
  DB/service backend** and **convention-level with a shared file store** — choose per deployment,
  document the file-store caveat. **Append-only audit with control-plane-actor + issuer-label + timestamp
  (R1-S6); audit-write failure ⇒ action denies** — fault test: audit sink down → issuance/consume denies.
- **M5 — Serve/CLI wiring + per-trigger fail-closed matrix.** `kickoff start --cloud` accepts a grant
  store. **Per-trigger integration matrix (R1-S5):** one case each for {absent, expired, exhausted,
  revoked, store-unavailable, clock-untrusted} → strict 501 + no mirror write + no token spend. Happy
  path: valid grant → 1 session of chat-write + populated cockpit.

---

## 4. Requirements → Milestone Traceability (against the v0.2 update)

| Req | Milestone |
|-----|-----------|
| FR-1 grant enables parity | M2/M3 |
| FR-2 use-limited (default 1) | M0/M2 |
| FR-3 expiring | M0 |
| FR-4 revocable | M0/M4 |
| FR-5 fail-closed | M1/M0 |
| FR-6 human-issued only | M4 |
| FR-7 anti-replay atomic consume | M0 |
| FR-8 least-privilege scope | M0/M2 |
| FR-9 redaction+telemetry unchanged | M3 |
| FR-10 auditable | M4 |
| FR-11 layers on api-key | M2 |
| FR-12 grant-capable build (NEW) | M2 |
| FR-13 single effective-posture (NEW) | M1 |
| FR-14 cloud-write trust chain (NEW) | M2 |
| FR-15 unit of use = session (NEW) | M2 |
| FR-16 safe-writer unchanged (NEW) | M3 |

---

## 5. Risks

- **R1 — Scattered-gate drift + fail-open-by-omission.** Editing six sites invites missing one; worse, a
  *new* write endpoint that never had an `if cloud:` would fail-**open** and a residual-grep can't see it.
  *Mitigation (R1-S2):* M1 collapses to one seam **and** a structural default-deny guard — routes are
  registered so a route not wired to the seam **denies**; test asserts a synthetic un-chained route 501s.
- **R2 — Build-time vs per-request mismatch.** A grant-capable build that forgets a per-request check =
  standing cloud chat. *Mitigation:* default-deny in `_cloud_capability`; M1 golden proves
  cloud-without-grant is byte-identical to today.
- **R3 — The token-spend surface.** Re-enabling chat = un-metered LLM spend risk. *Mitigation:* the
  grant's use-count + expiry + the session's inner turn/rate/budget caps (FR-15); audit every consume.
- **R4 — Issuer trust (OQ-4, RESOLVED).** A weak issuer undoes the whole bound. *Resolution:* issuance is
  **out-of-band control-plane**, bound to the platform's real identity (SSH/IAM/CI); the served app has
  **no mint route** and the consumer `--api-key` ≠ the issuance credential — so the served surface carries
  no grant-creation path. *Residual:* per-*person* attribution is only as fine as the control-plane
  identity until OQ-GE-7 (accepted); the audit field is shaped for a later IdP drop-in.
- **R5 — Loopback-chain assumptions leak.** Reusing local CSRF/Host on a cloud surface would either
  break or falsely trust. *Mitigation:* FR-14's distinct cloud-write trust chain; test a non-loopback
  Host is accepted only with api-key + grant.

---

## 6. Validation

- Unit (M0): single-atomic resolve+consume; **N-parallel-redemption → exactly 1 wins**; store-fail-mid-
  consume → deny+no-debit; expiry/revoke; target-mismatch rejects.
- Structural (M1): golden — cloud-without-grant byte-identical to today (load-bearing regression); **a
  synthetic write route bypassing the seam returns 501** (default-deny).
- Trust chain (M2): **2⁴ factor truth table** — only all-present allows, 15 partial rows 501; caps-
  present gate (caps unset → creation denies); pre-message surface (no-grant → chat GET strict-deny).
- Fail-closed matrix (M5): **one integration case per trigger** {absent, expired, exhausted, revoked,
  store-unavailable, clock-untrusted} → 501 + no mirror write + no token spend.
- Composition (M3): per-turn re-validation (create→expire→next-turn denies); redaction + `apply_proposal`
  safe-writer unchanged under grant; audit-write-failure ⇒ action denies (M4).

---

*v1.0 — plan from the v0.1 draft. Surfaced: build-time chat-disable (FR-12), scattered-gate collapse
(FR-13), cloud-write trust chain (FR-14), unit-of-use (FR-15), safe-writer-preserved (FR-16).*

*v1.1 — Post-CRP R1 triage. All 9 S-suggestions ACCEPTED + applied: M0 concurrency/TOCTOU tests (S4);
M1 structural default-deny guard (S2); M2 2⁴ trust-chain table + caps-present gate + pre-message surface
(S1/S3/S7); M3 per-turn re-validation (S9); M4 audit-fail-closed + issuer-label (S6); M5 6-trigger
fail-closed matrix (S5); §2.2 typed Decision + consume-inside-seam (S8). §6 validation restructured. See
Appendix A.*

*v1.2 — OQ-4 resolved (out-of-band control-plane issuance). M4 reshaped: issuance/revocation is a
control-plane CLI bound to platform identity (not a served route); served app consume-only (NR-6);
issuance credential ≠ consumer `--api-key`; store-backend issuance/consumption privilege split noted
(DB-enforceable / file-convention). §2.3 + R4 updated. M0 already shipped (PR #198); M1 is the next build.*

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
| R1-S1 | M2 trust-chain 2⁴ conjunction test | R1 (claude-opus-4-8[1m]) | Added to **M2** + §6: only all-present allows, 15 rows 501. | 2026-07-11 |
| R1-S2 | M1 structural default-deny guard | R1 | Added to **M1**/§5-R1/§6: synthetic un-chained route → 501. | 2026-07-11 |
| R1-S3 | M2 caps-present gate | R1 | Added to **M2**/§2.4: caps unset → creation denies; non-raisable. | 2026-07-11 |
| R1-S4 | M0 consume ordering + TOCTOU + concurrency | R1 | Added to **§2.1/M0**/§6: single-atomic, forfeit-on-fail, N-parallel→1, mid-consume-fail deny. | 2026-07-11 |
| R1-S5 | M5 per-trigger fail-closed matrix | R1 | Added to **M5**/§6: 6-trigger integration matrix. | 2026-07-11 |
| R1-S6 | M4 audit-fail-closed + issuer label | R1 | Added to **M4**: append-only, audit-fail⇒deny, issuer-label+source. | 2026-07-11 |
| R1-S7 | M2 pre-message surface | R1 | Added to **M2**: chat-page GET + `chats.put` consult seam. | 2026-07-11 |
| R1-S8 | §2.2 typed Decision + consume-inside-seam | R1 | Added to **§2.2**: typed `Decision`; only the seam consumes. | 2026-07-11 |
| R1-S9 | M3 per-turn re-validation | R1 | Added to **§2.4/M3**: create→expire→next-turn denies. | 2026-07-11 |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none) | — | R1 | All 9 R1 S-suggestions accepted. | 2026-07-11 |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — claude-opus-4-8[1m] — 2026-07-11 16:31 UTC

- **Reviewer**: claude-opus-4-8[1m]
- **Scope**: Security-weighted CRP of the implementation plan for the cloud-authorization grant. Focus (per sponsor): non-bypassable cloud-write trust chain (§2.3/FR-14), the collapse-to-one-seam not leaking (§2.2/FR-13, R1), spend-bounding of the session unit-of-use (§2.4/FR-15), fail-closed race-free consume (§2.1/§3 M0, R3/R5), issuer-trust substrate (§5 R4/OQ-4). Honors the settled/do-not-relitigate list (no Temporal, server-side record, single posture, layers-on-api-key, redaction unchanged).

**Executive summary (top risks / blocking gaps):**
- §2.3 states the cloud-write trust chain as a *list* of ingredients but the plan has **no milestone task that tests the chain as a conjunction** (only R5 tests "api-key + grant" for a non-loopback Host) — the AND-gate ordering / partial-chain-denies is unvalidated.
- The M1 "no residual `if cloud:`" golden (§3/R1) catches leftovers but **cannot catch a future write endpoint that never had a denial** — the plan needs a structural default-deny guard, not a grep.
- §2.4 asserts session inner caps bound spend but **no milestone verifies those caps exist / are non-defeatable in the grant-built cloud path** — M2 builds the factory but doesn't gate on caps-present.
- §2.1 `consume` is "atomic" but the plan never specifies **consume-vs-act ordering** or **store-unavailable-mid-consume** behavior; M0 unit tests atomicity in isolation but not the TOCTOU interaction with the action.
- §2.4 consumes the use at session creation; the plan does not sequence a task ensuring **per-turn re-validation** so a session created just-before-expiry can't outlive the grant (interacts with OQ-7).
- R4/§5 issuer trust is mitigated by "operator-credential gate + audit" but the credential is a **shared static key** — the plan should add a task capturing an issuer label + issuance-source in the audit record so FR-10's "who" is not vacuous.
- No milestone covers **audit-write-failure fail-closed** (M4 adds audit but not the "unauditable ⇒ deny" semantics).
- M2 opens `chat_factory` in cloud mode; no explicit task ensures the **chat-page GET / session-creation** pre-message surface also consults the seam before a grant is validated.

**Numbered suggestions:**

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-S1 | Security | critical | Add to **M2** an explicit **trust-chain conjunction test task**: verify the cloud-write path is honored **iff all of** {api-key valid, grant resolves for target+capability, uses>0/unexpired/unrevoked, Host/Origin ∈ configured cloud origin} and denies on **any** missing factor (not just the R5 "non-loopback Host + api-key + grant" case). Enumerate the partial-chain matrix as an acceptance gate. | §2.3 lists the ingredients and R5 tests one partial case; nothing proves the chain is a non-bypassable AND-gate (sponsor crux #2). A partial chain (e.g. api-key + Origin but no grant, or grant but wrong Origin) must be shown to deny. | §3 M2 acceptance criteria; §6 Validation | 2^4 factor truth-table integration test; only all-present allows, 15 others 501. |
| R1-S2 | Validation | critical | Strengthen the **R1 mitigation (§5)** from a "no residual `if cloud:`" grep to a **structural default-deny guard**: require chat/write routes to be registered through a mechanism the test can enumerate, and add a test that a route **not** wired to `_cloud_capability` fails closed (denies). Add this as an M1 acceptance criterion. | The grep in R1/§3-M1 catches *removed* denials but a *newly added* write endpoint that never consulted the seam would fail-open — the plan's own R1 test cannot detect it (sponsor crux #3). | §5 R1 mitigation; §3 M1 | Test: register a synthetic write route bypassing the seam ⇒ assert 501, not 200. |
| R1-S3 | Security | high | Add an **M2 caps-present gate**: when building the grant-capable cloud app and consuming a use at session creation (§2.4), **assert the session's turn-cap, per-session rate-limit, and budget are present, server-enforced, and not request-overridable**; deny session creation if any is absent. | §2.4/R3 claim inner caps bound spend, but the plan builds the factory (M2) without a task ensuring the caps actually exist and can't be defeated in cloud mode (sponsor crux #4) — otherwise "1 use" can be unbounded spend. | §3 M2; §2.4 | Test: grant session with caps unset/zeroed ⇒ creation denies; request cannot raise cap values. |
| R1-S4 | Risks | high | Specify in **§2.1 / M0** the **consume ordering + TOCTOU semantics**: make resolve+consume a single atomic op, define consume-before-act with explicit action-failure semantics (use forfeit vs refunded), and require **store-unavailable during consume ⇒ deny with no use debited**. Add a concurrency test (N parallel redemptions of a 1-use grant → exactly 1 wins) and a mid-consume fault test to M0/M5. | §2.1 says consume is atomic but not its ordering relative to the action nor mid-consume store-failure behavior (sponsor crux #5) — the race/TOCTOU gap where a captured request or a store blip double-spends or silently allows. | §2.1 Ops list; §3 M0/M5; §6 Validation | Concurrency test + fault-injection test as described. |
| R1-S5 | Validation | high | Expand **§6 Validation / M5** into a **per-trigger fail-closed matrix**: one integration case each for {absent, expired, exhausted, revoked, store-unavailable, clock-untrusted} ⇒ strict 501 + no mirror write + no token spend. Today §6 lists only "no-grant → 501" and "expiry/revoke mid-session". | The plan tests two deny paths; FR-5 has six triggers (sponsor crux #5). Each must be independently shown to deny — otherwise store-unavailable / clock-untrusted / exhausted are unvalidated. | §6 Validation; §3 M5 | Parametrized integration test, one case per trigger. |
| R1-S6 | Ops | medium | Add to **M4** an **audit-write-failure fail-closed** task + append-only audit store: if the issuance/consumption audit write fails, the action does not proceed (no unauditable elevation). Also capture an **issuer label + issuance-source** in the record so FR-10's "who" is meaningful under the shared-key OQ-4 lean. | M4 adds audit (FR-10) but not the failure semantics; and §5-R4's "operator-credential gate + audit" is only as attributable as a shared static key allows (sponsor crux #1) — an issuer label closes part of that gap. | §3 M4; §5 R4 | Fault test: audit sink down ⇒ issuance/consume denies; schema review confirms issuer-label + source fields. |
| R1-S7 | Interfaces | medium | Add an **M2 task for the pre-message surface**: ensure the **chat-page GET and `chats.put` session creation** consult `_cloud_capability` before a grant is validated, so opening the `chat_factory` in cloud mode (FR-12) does not expose a live chat surface pre-grant. | §2.4/M2 build the factory but the plan does not sequence a check that the page-render + session-create paths (not just message POST) traverse the seam — a possible un-chained entry (sponsor crux #2). | §3 M2 | Test: cloud build + no grant ⇒ chat page GET returns strict-deny view, `chats.put` denies (no session created). |
| R1-S8 | Architecture | medium | In **§2.2**, require `_cloud_capability` to return a **typed Decision (allow / deferred + reason) with the consume performed inside the seam**, and forbid callers from performing the consume themselves — so "resolve here, consume there" cannot drift back in and reintroduce a check/use split across call sites. | §2.2 says the seam resolves posture and §2.1 says endpoints "atomically consume" — if consume lives in the endpoints rather than the seam, FR-13's single-source property erodes (the accidental-complexity the doc set out to delete). | §2.2 | Test: assert no call site calls `store.consume` directly; only the seam does. |

### Stress-test / adversarial pass

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-S9 | Risks | high | Add a task ensuring **per-turn/per-apply grant re-validation** (not only at session creation) so a session created just-before-expiry cannot keep spending after expiry/revocation — the FR-15 consume-at-creation must compose with the OQ-7 per-action check. Sequence it in M3 alongside enabling chat-write. | §2.4 consumes the use at creation; without per-turn re-check, expiry/revocation (crux #5) is defeated by early session creation — the in-flight session outlives the grant. | §3 M3; §2.4 | Test: create session at T; expire/revoke at T+ε; next turn ⇒ deny despite use already consumed. |

---

## Requirements Coverage Matrix — R1

Analysis only (not triage). Maps each requirement (FR) in `CLOUD_MIRROR_GRANT_REQUIREMENTS.md` to the plan section/milestone that addresses it. `Partial`/`Gap` rows have a corresponding R1-S suggestion above.

| Requirement | Plan Section / Milestone | Coverage | Gaps (→ suggestion) |
| ---- | ---- | ---- | ---- |
| FR-1 grant enables parity | §1, §2.2; M2/M3 | Full | — |
| FR-2 use-limited (default 1) | §2.1, §2.4; M0/M2 | Full | — |
| FR-3 expiring | §2.1, §2.5; M0 | Partial | Expiry-voids-mid-window stated, but composition with consume-at-creation (post-expiry session) not sequenced → R1-S9 |
| FR-4 revocable | §2.1; M0/M4 | Full | — |
| FR-5 fail-closed | §2.5, §6; M1/M0 | Partial | Only 2 of 6 deny triggers tested (no store-unavailable/clock-untrusted/exhausted matrix) → R1-S5 |
| FR-6 human-issued only | §2.3, §5-R4; M4 | Partial | Issuer = shared static key; "human" not attributable, no issuer label captured → R1-S6 |
| FR-7 anti-replay atomic consume | §2.1; M0 | Partial | Atomicity tested in isolation; consume-vs-act ordering + store-unavailable-mid-consume TOCTOU unspecified → R1-S4 |
| FR-8 least-privilege scope | §2.1 (record fields); M0/M2 | Partial | Scope-binding shape present; wrong-target-grant-denies rule not enforced (OQ-5 open) → (see reqs R1-F8) |
| FR-9 redaction + telemetry unchanged | §2.5; M3 | Full | — |
| FR-10 auditable | §2.5, M4 | Partial | Audit-write-failure semantics (fail-closed) + append-only not covered → R1-S6 |
| FR-11 layers on api-key | §2.3; M2 | Full | — |
| FR-12 grant-capable build | §1 (table), §2.2; M2 | Partial | Factory opened, but chat-page GET / session-create pre-message surface not explicitly gated → R1-S7 |
| FR-13 single effective-posture | §2.2; M1 (R1) | Partial | Residual-grep only; no structural default-deny guard for new endpoints; consume-lives-in-seam not enforced → R1-S2, R1-S8 |
| FR-14 cloud-write trust chain | §2.3; M2 (R5) | Partial | Ingredients listed; conjunction/partial-chain-denies matrix not tested → R1-S1 |
| FR-15 unit of use = session | §2.4; M2 | Partial | Spend bound assumes inner caps exist/are non-defeatable; no caps-present gate → R1-S3 |
| FR-16 safe-writer unchanged | §2.5; M3 | Full | — |
