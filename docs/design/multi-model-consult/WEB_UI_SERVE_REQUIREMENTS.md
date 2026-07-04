# Consultation Web View — Interactive Serve Mode Requirements

**Version:** 0.4 (Post-CRP — R1+R2 security review triaged & applied)
**Date:** 2026-07-03
**Status:** Draft
**Owner:** neil-the-nowledgeable
**Extends:** the shipped static web view (`WEB_UI_REQUIREMENTS.md`) and the consultation feature (M1–M3.5).
**Relationship:** the **opt-in** interactive alternative to the static copy-command composer (FR-WUI-10).

---

## 0. Planning Insights (Self-Reflective Update)

> Grounded on the existing Starlette server (`server/app.py`), its auth middleware
> (`server/auth.py`), the `startd8 serve` command, and `ConsultationService`. Five corrections.

| v0.1 Assumption | Planning Discovery | Impact |
|-----------------|--------------------|--------|
| "Reuse the SDK's `create_app` server" | `server/app.py` `create_app()` serves **workflow** routes (`/workflows/...`); wrong surface. And `startd8 serve` **binds `0.0.0.0` by default** (all interfaces!). | New **dedicated app** in `consultation/serve.py`; **must bind `127.0.0.1` only**, never inherit the `0.0.0.0` default (FR-SRV-1/4). |
| "Reuse `APIKeyMiddleware` as-is" | It only guards **POST** (GET is open) and checks **no Origin/Host** — insufficient for a money-spending write surface (DNS-rebinding / drive-by localhost POST). | Stronger guard: a **per-run token on every request** + an **Origin/Host allowlist** (FR-SRV-4). Reuse the middleware *pattern*, not the class. |
| "The route calls `ConsultationService.follow_up()`" | The facade uses `asyncio.run()` internally — **it cannot be called inside Starlette's already-running event loop** (nested-loop error). | The async route must `await engine.follow_up(...)` **directly** (or run the facade in a threadpool). Changes the executor wiring (FR-SRV-3). |
| "The page just needs a Send button" | The shipped `render_html` emits a **static** page (composer = copy-command). Serve mode needs the page to know it's interactive (endpoint + token). | `render_html` gains an optional **serve-config injection** (token + `/reply` URL); the template JS switches composer → Send when present (FR-SRV-2/10). Static output unchanged when absent. |
| "It just runs follow-ups" | `engine.follow_up` needs a **rebuilt roster** (`build_roster`), which needs **API keys in the server process**; and each Send spends **real money**. | The server must run in a key-bearing env (doppler); `build_roster` degrades on missing keys; **cost confirmation** is required (FR-SRV-5). |

**Resolved open questions:**
- **OQ-2 → Ephemeral port by default** (bind `127.0.0.1:0`, print the actual URL); `--port` optional.
- **OQ-5 → Serve mode is signalled by an injected config block** (token + endpoint) in the served HTML; absent = the static file (no interactive JS activates).

### 0.1 Lessons-Learned Hardening (v0.3)

- **[Phantom-reference audit]** — verified: `create_app`/`APIKeyMiddleware` (`server/`), `ConsultationService`/
  `ConsultationEngine.follow_up` (`consultation/`), `build_roster`, `render_html`. `uvicorn`+`starlette`
  are the `startd8[server]` extras. See §7.
- **[Overloaded-term co-location]** — do **not** add consult routes to the workflow server
  (`server/app.py`). Serve mode gets its **own** `consultation/serve.py` app + middleware (NR-7).
- **[Security-posture inheritance / inversion]** — this **inverts** the static view's read-only guarantee
  (WEB_UI NR-2). The spec must be loud that `--serve` is an **opt-in write surface that spends money**;
  the static view's guarantee is untouched and remains the default (NR-4). The trust model is
  **single local user** (the token is anti-CSRF/drive-by, *not* multi-user auth, NR-2).
- **[Bucket separation]** — serve mode is still bucket-3 orchestration glue over the consultation core;
  it adds a transport, not new generation. It does not touch the deterministic $0 path.
- **[CRP steering memory]** — least-reviewed = this new doc; the **security model** (loopback + token +
  Origin/Host + cost guard) is the highest-value review target; carried to the CRP focus file.

*Checked lessons base; five classes applied. Ready for CRP.*

---

## 1. Problem Statement

The shipped web view is a read-only snapshot; to ask a follow-up the user copies a `consult reply`
command into a terminal and re-renders (FR-WUI-10). That's safe and offline, but not "click-and-it-runs."
Serve mode adds an **opt-in** interactive path: a local server executes follow-ups from the page itself.
Because a browser page can now trigger **real, paid LLM calls** and **mutate the session**, the entire
value of the increment rides on getting the **local-server security model** right.

| Component | Current State | Gap |
|-----------|---------------|-----|
| Static view | `render_html` → offline file; copy-command composer | No in-page execution (by design) |
| Executor | `ConsultationService`/`engine.follow_up` (CLI/TUI) | Not reachable from the browser |
| Local HTTP | `server/app.py` (workflow routes, `0.0.0.0`, POST-only auth) | Wrong surface + unsafe defaults for this use |

---

## 2. Requirements

### Server + transport
- **FR-SRV-1 — `--serve` launches a local server.** `startd8 consult web <id> --serve` starts an HTTP
  server bound to **loopback only** (`127.0.0.1`, default ephemeral port; `--port` optional), serving the
  interactive view for **exactly one** session.
  - **Bind order / TOCTOU (R2-F5).** The listen socket sets **no** `SO_REUSEADDR`/`SO_REUSEPORT`; the
    launch order is strictly **bind → read `getsockname()` → mint token → print/`--open` URL**. A bind
    failure aborts **before** any token is minted or printed (degrade to static, FR-SRV-8).
  - **`--open` leak (R2-F4).** The tokenized URL handed to `--open` is a known OS-local surface (argv /
    launcher history), accepted only under the single-local-user model (NR-2); where the launcher API
    allows, it is not passed as visible argv.
- **FR-SRV-2 — Interactive composer.** In serve mode the follow-up composer becomes a **Send** button
  (target = all/one) that POSTs to `/reply`; on success the page **updates the affected panel(s) in place**
  from the returned session (no full reload, no page-owned state divergence). Falls back to the static
  copy-command composer if serve-config is absent (FR-SRV-10).
- **FR-SRV-3 — Executor reuse (no logic fork).** `/reply` runs the follow-up through the **same**
  consultation core the CLI/TUI use (`ConsultationEngine.follow_up`, awaited directly in the async route),
  persists via `ConsultationStore`, and returns the updated `ConsultationSession` JSON. **Per-request
  execution timeout (R1-F7):** `follow_up` wall-time is bounded; on timeout the route returns a structured
  per-panel error and **releases the lock**, so one hung provider call cannot wedge the single-worker server.

### Security (the crux)
- **FR-SRV-4 — Local-server security model.** All of:
  - **(a) Loopback bind — positive assertion, not a blacklist (R1-F1).** After binding, the server asserts
    `socket.getsockname()` is within `127.0.0.0/8` or `::1` and **refuses** otherwise; string forms
    `0.0.0.0`, `::`, `0`, and any hostname resolving off-loopback are rejected; IPv6 **dual-stack is
    disabled** (`IPV6_V6ONLY`, or bind IPv4 only). The invariant is "reachable only from this host,"
    verified on the *bound* address.
  - **(b) Per-run secret token — every request, leak-mitigated (R1-F2/F10).** A ≥128-bit token
    (`secrets.token_urlsafe`) minted at startup, required on **every** request and compared
    **constant-time** (`secrets.compare_digest`), **before** any session load or roster work (no
    timing/existence oracle). The initial `GET /` carries it in the URL; the page then (i) **strips it
    from the address bar** via `history.replaceState` and (ii) sends it on each POST via the
    `X-Consult-Token` header. Responses set **`Referrer-Policy: no-referrer`**. The token is **excluded
    from the Uvicorn access log** (drop query string / disable access log) and from any crash/traceback
    output; never persisted; dies with the process. (Transport decision closes OQ-1.)
  - **(c) Origin/Host allowlist — fail-closed (R1-F3).** Reject any request whose `Host` is not exactly
    `127.0.0.1[:port]`; a state-changing POST is rejected **unless `Origin` exactly equals the server's
    own origin** — **missing or `null` `Origin` is rejected** (403). This is what actually stops
    DNS-rebinding + CSRF (R1-S9 proves it with a rebind test).
  - **(d) Single-session confinement (R2-F2).** The server only reads/writes the one launched session id;
    no path/session traversal, no directory listing, no other-file access. **`GET /session` and the
    bootstrap `GET /` are fully token-gated**: a wrong/absent token returns **no session content** (the
    paid model answers are the protected asset), and pass the Host/Origin guard.
  - **(e) Content isolation — CSP + sanitizer (R2-F1, the escalation).** Because the page holds a
    spend-capable token, a markdown-render XSS = token exfiltration + attacker-funded spend. The served
    responses set a **strict CSP** (`default-src 'none'; script-src 'self'; connect-src 'self'`, no
    `unsafe-inline` reaching the markdown path), and model-answer markdown is rendered through a
    sanitizer that cannot emit active content. The token in `sessionStorage` must be unreadable by any
    injected content; `connect-src 'self'` blocks exfiltration to a foreign host.
  - **(f) Uniform, content-free errors (R2-F3).** All 401/403/404/409/429/5xx responses carry **no**
    session id, prompt, answer, file path, stack trace, or token substring, and are **byte-identical
    whether or not the target id exists** (no existence oracle in the body).
  - **(g) No upgrade paths (R2-F6).** The token/Origin guard runs at **ASGI scope** for all request types;
    any `Connection: Upgrade` / WebSocket request is rejected (426/400) — v1 has no streaming endpoint
    (NR-5) and none may bypass the guard.
- **FR-SRV-5 — Cost guard (hardened).** Each Send triggers real paid LLM calls. The UI states **how many
  models** a Send will call and requires an explicit user action per Send (no auto-fire); the response
  surfaces per-model token/cost. Server-side, under the **same lock and increment-before-paid-call** (R1-S4):
  - a **turn cap** (`--max-turns`, small default) → 429 when exceeded; **and**
  - an independent **hard spend/total-call ceiling** (`--max-cost` or max-model-calls) → distinct 402/429
    (a turn cap alone doesn't bound a wide/expensive fan-out) (R1-F4); **and**
  - **replay defense** (R1-F5): each accepted `/reply` is single-use (per-Send nonce minted by the page,
    consumed server-side, or the counter incremented atomically before the paid call) so a captured POST
    cannot double-spend.
- **FR-SRV-6 — Concurrency / session lock (in- and cross-process).** Follow-ups are serialized by an
  in-process `asyncio.Lock`; an overlapping POST → 409. **Cross-process (R1-F6):** a second `--serve` on a
  session id that is already served is **refused** (advisory lockfile / `mkdir`-excl marker beside the
  session, released on clean shutdown) — the in-process lock alone gives false safety across two servers.

### Lifecycle + degradation
- **FR-SRV-7 — Lifecycle.** Runs until Ctrl-C; optional **idle auto-shutdown** (`--timeout`); clean
  shutdown releases the port and the cross-process marker. The token is regenerated each launch and never
  echoed in full to the terminal (print a redacted form / "opened in browser"; R1-S8).
- **FR-SRV-8 — Graceful degradation (ordered, token-free — R2-F7).** The launch sequence is
  **(1) import extras → (2) load/validate session → (3) mint token → (4) bind → (5) print/open URL**. A
  failure at any step **before (4)** leaves **no token minted, no port bound, no URL printed** and
  **writes the static view instead** (never a half-up server or exposed token). Per-model failures during a
  served follow-up use the **same failure isolation** as the CLI (recorded, surfaced per panel).
- **FR-SRV-9 — Keys / roster.** The server rebuilds the roster via `build_roster` (needs provider keys in
  its env; run under doppler). Missing-key models are reported as unavailable, not fatal.
- **FR-SRV-10 — Opt-in; static view unchanged (golden-hash verified — R1-F8).** `--serve` is strictly
  opt-in. Without it, `consult web` emits the byte-identical **static, offline** file (WEB_UI).
  **Acceptance:** a pinned test asserts `hash(render_html(session, serve=None))` equals the committed
  golden, and that no token / `/reply` substring appears in the `serve=None` output — the read-only
  guarantee (WEB_UI NR-2) cannot silently regress when the template is touched.

---

## 3. Non-Requirements

- **NR-1 — Not remotely reachable.** No `0.0.0.0`, no LAN/WAN exposure, no TLS, no hosting, no tunneling.
- **NR-2 — Not multi-user auth.** Single local user assumed; the token defends against **other local
  processes / cross-site requests**, not against a hostile local user.
- **NR-3 — Follow-ups only.** Serve mode continues the launched session; it does **not** start new
  consultations or change the roster from the browser (`run` stays CLI/TUI).
- **NR-4 — Not the default.** The static offline view remains primary; serve mode is opt-in.
- **NR-5 — No streaming in v1.** `/reply` returns the completed turn; the panel updates on response.
  Token-by-token streaming (SSE/websocket) is deferred.
- **NR-6 — No browser image upload in v1.** Served follow-ups are **text-only**; image-bearing
  follow-ups stay on the CLI (avoids a browser file-upload trust boundary).
- **NR-7 — Does not extend the workflow server.** Serve mode is its own app/module; it adds nothing to
  `server/app.py`.

---

## 4. First Acceptance Scenario

`startd8 consult web <live-smoke-id> --serve --open` (run under doppler for keys):
1. A loopback server starts on `127.0.0.1:<ephemeral>`; the browser opens the tokenized URL and shows the
   3-model door consultation, all expanded.
2. The user types a follow-up, selects **gemini** only, clicks **Send**; a `/reply` POST (carrying the
   token) runs `engine.follow_up(..., target="gemini…")`; only Gemini's panel gains a new turn (with token
   badges); the session file on disk is updated.
3. A POST with a **missing/wrong token** → 401; a POST with a foreign `Origin` → 403; a second binder on
   `0.0.0.0` is refused at startup.
4. Ctrl-C shuts the server down cleanly; the last-written session opens fine as a static view afterward.

---

## 5. Open Questions

- **OQ-1 → RESOLVED (R1-F9): `X-Consult-Token` header** from an injected value in `sessionStorage`
  (no cookie surface); the token is stripped from the URL after bootstrap. Folded into FR-SRV-4b.
- **OQ-3 — Idle-timeout default** (e.g. 30 min) and whether it's on by default.
- **OQ-4 — Cost-confirm UX.** Confirm dialog *before* each Send, or show cost *after* + a turn cap only?
- **OQ-6 — In-place update granularity.** Return the whole session and re-render all panels, vs patch only
  the targeted model's panel. (Whole-session is simpler and matches the atomic write.)

---

## 6. Reference Audit (verified symbols)

| Symbol | Location | Role |
|--------|----------|------|
| `create_app` / `APIKeyMiddleware` | `server/app.py` / `server/auth.py` | *pattern* to adapt (not reuse) — FR-SRV-4 |
| `startd8 serve` (binds `0.0.0.0`, uvicorn) | `cli.py` | the unsafe-default to NOT inherit |
| `ConsultationEngine.follow_up` (async) | `consultation/engine.py` | the awaited executor (FR-SRV-3) |
| `ConsultationService` / `.follow_up` (asyncio.run) | `consultation/facade.py` | **cannot** be nested in the server loop |
| `build_roster` | `consultation/roster.py` | roster rebuild (FR-SRV-9) |
| `render_html` / `_webview_template` | `consultation/view.py` | gains serve-config injection (FR-SRV-2/10) |
| `ConsultationStore` (atomic save, mkdir-excl) | `consultation/store.py` | persistence + lock anchor (FR-SRV-6) |

*To-be-created:* `consultation/serve.py` (the loopback app + token/Origin middleware + `/reply` route),
the `--serve` path in `consult web`, serve-config injection in `render_html`, interactive JS branch in the
template. `starlette`+`uvicorn` (`startd8[server]`) become a soft dependency (FR-SRV-8).

---

*v0.4 — Post-CRP. Reflective loop v0.1→v0.3, then a 2-round security-weighted CRP (R1+R2, reviewer
`claude-opus-4-8-1m`, R2 endorsed 16 R1 items): all 17 requirements F-suggestions ACCEPTED. FR-SRV-4
rebuilt into 7 sub-clauses (a–g): resolved-address loopback + IPv6, token leakage mitigations +
constant-time + validate-first, Origin fail-closed, GET token-gating, **CSP + sanitizer content
isolation** (the token-theft escalation), uniform errors, no-upgrade. FR-SRV-5 gained a hard spend
ceiling + atomic cap + replay defense; FR-SRV-6 a cross-process guard; FR-SRV-1 TOCTOU/bind-order;
FR-SRV-3 exec timeout; FR-SRV-8 ordered token-free degradation; FR-SRV-10 golden-hash acceptance;
OQ-1 resolved. Dispositions in Appendix A.*

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

> **Triage (2026-07-04, orchestrator):** strongly convergent security review (R2 endorsed 16 R1
> items; its 2 "disagreements" were transport/print-policy *reframes*, folded not rejected). All 17
> requirements suggestions ACCEPTED. Parallel plan `R*-S*` dispositions live in `WEB_UI_SERVE_PLAN.md`.

| ID | Suggestion | Source | Applied to | Date |
|----|------------|--------|-----------|------|
| R1-F1 | Resolved-address loopback assertion (not string blacklist) + IPv6 `::1`/dual-stack | R1 | FR-SRV-4(a) | 2026-07-04 |
| R1-F2 | Token-in-URL leak mitigations (Referrer-Policy, replaceState, no-Loki) | R1 | FR-SRV-4(b) | 2026-07-04 |
| R1-F3 | Origin fail-closed on missing/null; narrow Host | R1 | FR-SRV-4(c) | 2026-07-04 |
| R1-F4 | Hard spend ceiling independent of turn cap; atomic under lock | R1 | FR-SRV-5 | 2026-07-04 |
| R1-F5 | Replay/idempotency defense (single-use POST) | R1 | FR-SRV-5 | 2026-07-04 |
| R1-F6 | Cross-process second-server refusal | R1 | FR-SRV-6 | 2026-07-04 |
| R1-F7 | Per-request execution timeout | R1 | FR-SRV-3 | 2026-07-04 |
| R1-F8 | Golden-hash byte-identity test for serve=None | R1 | FR-SRV-10 | 2026-07-04 |
| R1-F9 | Resolve FR-SRV-4b ↔ OQ-1 contradiction | R1 | OQ-1 resolved / FR-SRV-4(b) | 2026-07-04 |
| R1-F10 | Constant-time compare + validate-before-session-load (oracle) | R1 | FR-SRV-4(b) | 2026-07-04 |
| R2-F1 | CSP + sanitizer content isolation (token-theft escalation) | R2 | FR-SRV-4(e) | 2026-07-04 |
| R2-F2 | Token-gate GET /session + GET / (no session leak) | R2 | FR-SRV-4(d) | 2026-07-04 |
| R2-F3 | Uniform content-free error bodies (no existence oracle) | R2 | FR-SRV-4(f) | 2026-07-04 |
| R2-F4 | `--open`/argv token leak bounded + documented | R2 | FR-SRV-1 | 2026-07-04 |
| R2-F5 | Ephemeral-port TOCTOU: no REUSE, bind→getsockname→mint order | R2 | FR-SRV-1 | 2026-07-04 |
| R2-F6 | Reject WebSocket/Upgrade at ASGI scope | R2 | FR-SRV-4(g) | 2026-07-04 |
| R2-F7 | Ordered, token-free degradation invariant | R2 | FR-SRV-8 | 2026-07-04 |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none) | — | — | High-signal security review; all accepted. R2's 2 "disagreements" (R1-F9 transport, R1-S8 print-policy) were reframes folded into FR-SRV-4b / FR-SRV-7, not rejections. | 2026-07-04 |
| (none yet) |  |  |  |  |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — claude-opus-4-8-1m — 2026-07-04

- **Reviewer**: claude-opus-4-8-1m
- **Date**: 2026-07-04 02:55:00 UTC
- **Scope**: First external review. Security-weighted per SERVE_CRP_FOCUS.md — attack the local-server security model (loopback bind, per-run token, Origin/Host allowlist, cost guard). Requirements-doc (F-prefix) suggestions here; plan (S-prefix) + coverage matrix in the plan file.

**Executive summary (top risks / gaps):**

- FR-SRV-4a says "refuse to bind `0.0.0.0`/any non-loopback" but the acceptance criterion is a *string blacklist*, not a *resolved-address whitelist* — `::1`, `0`, `127.0.0.2`, and `localhost`-that-resolves-elsewhere all slip a blacklist. The bind rule should be "resolve and assert the socket's actual bound address is in {127.0.0.0/8, ::1}", not "reject the literal `0.0.0.0`".
- FR-SRV-4b puts the ≥128-bit token **in the GET-page URL**. That token then lives in browser history, any `Referer` header the page emits, shoulder-surfing, and (per Risk in plan) is one `info` log away from Loki. No requirement mandates rotating-it-off-the-URL after bootstrap, a `Referrer-Policy: no-referrer`, or a scheme where the URL token is single-use.
- FR-SRV-4c allows `Host: localhost` — but `localhost` is exactly the name a DNS-rebinding attacker cannot forge yet a *malicious `/etc/hosts`-style* or public-suffix trick could. Also no requirement states what happens on **missing/null `Origin`** (non-browser clients, some `fetch` modes send none) — the allowlist must *fail closed* on absent Origin for state-changing POSTs, which the text leaves ambiguous.
- FR-SRV-5 bounds spend with a **turn cap only**. A turn = one Send = N model calls; a small turn cap still permits large spend if the roster is large or a model is expensive. There is no **hard per-server spend/token ceiling**, and no requirement that a **replayed captured POST** (same token, same body) is rejected or counts against the cap idempotently.
- FR-SRV-6's lock is **in-process `asyncio.Lock`**. Two `--serve` invocations on the *same session id* (two processes) each hold their own lock → the cross-process lost-update window the store's atomic write was supposed to close is still open. Requirement should either forbid a second server on a live session id (lockfile / mkdir-excl on the session) or state the risk is accepted.
- FR-SRV-3 asserts `engine.follow_up` is "awaited directly in the async route" but does not bound its **duration** — a slow N-model turn holds the single lock and the single Uvicorn worker; no per-request timeout requirement means one hung provider call wedges the whole server (no 409-able, no idle-timeout help mid-turn).
- FR-SRV-10 promises the static output is **byte-identical when serve-config is absent**, but the requirement gives no *verification hook* (e.g. "a golden-file / hash test asserts `render_html(serve=None)` == committed static output"). Without it the guarantee is un-auditable and will silently rot.
- OQ-1 (header vs cookie) is still open, yet FR-SRV-4b already commits to "URL on GET, custom header on POST." The requirement and the open question contradict; one must yield before build.

**Numbered suggestions (F-prefix):**

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F1 | Security | critical | Re-specify FR-SRV-4a as a positive assertion on the *resolved bound socket address* (must be in `127.0.0.0/8` or `::1`), not a blacklist of the literal string `0.0.0.0`. Explicitly enumerate that `::` / `::1` / `0` / a hostname resolving off-loopback must all be refused, and that dual-stack IPv6 binding is disabled. | A string blacklist of `0.0.0.0` is trivially bypassed (`::`, `0`, `0.0.0.0.0`, an env-var host); the real invariant is "the socket is only reachable from this host." IPv6 `::1` is a named focus concern. | §2 FR-SRV-4(a) | Unit test: attempt binds to `0.0.0.0`, `::`, `::1`, `0`, `127.0.0.1`; assert only loopback addresses succeed and `getsockname()` is asserted, not the requested string. |
| R1-F2 | Security | critical | Add an explicit token-leakage-mitigation clause to FR-SRV-4b: (i) set `Referrer-Policy: no-referrer` on the page response, (ii) after the page bootstraps, the JS moves the token out of the address bar (`history.replaceState`) so it does not persist in history, and (iii) restate the never-log/never-Loki rule as a *requirement*, not just a plan Risk. | Token-in-URL is the single largest leakage surface (history, Referer, Loki). The doc names the surfaces but imposes no countermeasure requirement, so an implementer could ship the leak. | §2 FR-SRV-4(b) | Manual+test: load page, assert address bar no longer contains the token after load; assert responses carry `Referrer-Policy: no-referrer`; grep server logs/Loki for the token string in an integration run → must be absent. |
| R1-F3 | Security | high | FR-SRV-4c must state the **fail-closed rule for absent/`null` `Origin`** on state-changing POSTs (reject unless Origin exactly equals the server's own origin) and clarify whether `Host: localhost` is actually accepted or only `127.0.0.1[:port]` — pick the narrowest that still works. | Non-browser clients and some `fetch` modes omit `Origin`; "reject POST with foreign Origin" is silent on *missing* Origin, which is the actual bypass. Accepting bare `localhost` widens the Host surface for little benefit if the page is served on `127.0.0.1`. | §2 FR-SRV-4(c) | Tests: POST with no `Origin` header → 403; POST with `Origin: null` → 403; POST with correct Origin → 200; `Host: evil.com` → 403; `Host: localhost` → (documented expected code). |
| R1-F4 | Security | high | Add a **hard per-server spend ceiling** to FR-SRV-5 (e.g. `--max-cost` in tokens or dollars, or max-total-model-calls) that is independent of the turn cap, and require that the turn cap is enforced **server-side atomically under the same lock** so concurrent/replayed Sends cannot each pass the check. | A turn cap alone does not bound cost when a Send fans out to many/expensive models; and a check-then-act turn counter outside the lock is racy under replay/retry. Focus item #4 asks exactly this. | §2 FR-SRV-5 | Test: set `--max-turns 2` and a low `--max-cost`; fire Sends until each limit trips independently; assert 429 (turns) and a distinct 402/429 (cost). Concurrency test: fire two Sends at cap boundary → only one succeeds. |
| R1-F5 | Security | high | Require **replay/idempotency defense** for `/reply`: each accepted POST must be non-replayable (e.g. a per-Send nonce minted by the page and consumed server-side, or the turn counter incremented atomically *before* the paid call so a re-POST of the same body cannot double-spend). | The token authenticates but does not make a captured POST single-use; an attacker (or a buggy retrying client) replaying a captured `/reply` spends money again. Neither FR-SRV-5 nor FR-SRV-6 closes this. | §2 FR-SRV-5 / new sub-bullet | Test: capture a valid `/reply` request, replay it verbatim → second call rejected (409/409-conflict) or provably counted once; assert no second paid call via stubbed engine call-count. |
| R1-F6 | Data | high | FR-SRV-6 must address the **cross-process** case: forbid a second `--serve` on a session id already served (e.g. an OS-level advisory lock / mkdir-excl marker beside the session file), or explicitly mark the cross-process lost-update window as an *accepted risk* with rationale. As written the in-process lock gives a false sense of safety. | Two servers on the same session each have an independent `asyncio.Lock`; the store's atomic write prevents corruption but not lost updates across processes. Focus item #5 raises this directly. | §2 FR-SRV-6 | Test: start two serve processes on one session id; assert the second refuses to start (or documents interleave). Integration: concurrent Sends across two processes → assert no silently-dropped turn. |
| R1-F7 | Risks | medium | Add a **per-request execution timeout** requirement to FR-SRV-3 (bound `engine.follow_up` wall-time; on timeout return a structured error and release the lock) so one hung provider call cannot wedge the single-worker, single-lock server indefinitely. | The single Uvicorn worker + single session lock means one slow/hung model call blocks all further Sends and even a clean 409; idle-timeout (FR-SRV-7) does not help mid-turn. | §2 FR-SRV-3 (add bullet) | Test with a stubbed engine that sleeps beyond the timeout → route returns error, lock released, a subsequent Send succeeds. |
| R1-F8 | Validation | medium | Make FR-SRV-10's byte-identity claim **verifiable**: require a golden/hash regression test asserting `render_html(session, serve=None)` is byte-for-byte equal to the committed static output, and that no token/endpoint string appears in that output. | The guarantee is currently un-auditable prose; without a pinned test it will silently regress the first time the template is touched. Focus explicitly asks to probe this claim. | §2 FR-SRV-10 (add acceptance criterion) | CI test: `hash(render_html(s, serve=None)) == committed_golden_hash`; assert token/`/reply` substrings absent from `serve=None` output. |
| R1-F9 | Interfaces | low | Resolve the FR-SRV-4b ↔ OQ-1 contradiction: FR-SRV-4b already prescribes "URL on GET + custom header on POST" while OQ-1 lists header-vs-cookie as open. Either close OQ-1 (record the decision + rationale) or soften FR-SRV-4b to "transport per OQ-1." | A normative requirement and an open question disagreeing on the same mechanism will confuse the implementer about what is settled. | §5 OQ-1 / §2 FR-SRV-4(b) | Doc check: no open question contradicts a normative FR; OQ-1 resolved-questions list updated. |

### Stress-test / adversarial pass (R1, F-prefix continued)

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F10 | Security | high | Require the token comparison to be **constant-time** at the *requirement* level (the plan mentions it; the requirement does not) and require the token be validated **before** any session load or roster work so a wrong token cannot be used as a timing/existence oracle for session ids. | FR-SRV-4b says "required on every request" but not *how* it is checked; a naive `==` leaks length/prefix timing, and checking the token after loading the session leaks whether a session id exists. | §2 FR-SRV-4(b) | Timing test over many trials (best-effort) + code assertion `secrets.compare_digest` is used; assert 401 returns identically for valid-token/bad-session and bad-token/valid-session. |

#### Review Round R2 — claude-opus-4-8-1m — 2026-07-04

- **Reviewer**: claude-opus-4-8-1m
- **Date**: 2026-07-04 03:20:00 UTC
- **Scope**: Second external review, security-weighted per SERVE_CRP_FOCUS.md. R1 covered the focus asks (bind assertion, token-in-URL, null Origin, spend/replay, cross-process lock, timeout, byte-identity, constant-time). R2 goes **deeper** on interactions R1 missed: the stored-model-content → XSS → token-theft escalation unique to serve mode, whether `GET /session` (the paid answers) is itself token-gated, `--open`/OS process-list token leakage, port TOCTOU, unauthorized-error content leaks, and WebSocket/upgrade guarding. Requirements (F-prefix) here; plan (S-prefix) + coverage matrix in the plan file.

**Executive summary (top risks / gaps R1 missed):**

- **Stored-XSS → token theft escalation.** `render_html` embeds untrusted model answers and the client renders them as **markdown in the DOM** (`view.py` FR-WUI-9). In the *static* file an XSS is cosmetic; in *serve* mode the same page holds a live money-spending token in `sessionStorage` — so any markdown-renderer XSS becomes **token exfiltration + attacker-funded spend**. No FR requires a **Content-Security-Policy** for serve mode, and OQ-1's move of the token into `sessionStorage` (readable by any script on the origin) makes this worse, not better. This is the highest-value gap in the doc.
- **`GET /session` info-leak.** FR-SRV-4b says the token is "required on **every** request," but §4 scenario and the plan's `GET /session` route are not called out as token-gated in the *requirements*. `GET /session` returns the full model answers — the paid content. If it is reachable without the token (or via a foreign Origin), an unauthorized local process reads the consultation. The requirement should name `GET /session` as token-AND-Origin-gated, and state whether `GET /` (the bootstrap page) leaks any session content before the token check.
- **`--open` leaks the tokenized URL to the OS.** FR-SRV-1's `--open` hands the full tokenized URL to a browser-launcher (`webbrowser`/`xdg-open`/`open`), which appears in the process argument list (`ps`), shell/job history, and any launcher log — a leakage surface distinct from the URL-in-browser-history one R1-F2 addressed. No requirement bounds how `--open` transports the token.
- **Ephemeral-port TOCTOU / reuse.** FR-SRV-1 binds `127.0.0.1:0`. Nothing forbids `SO_REUSEADDR`/`SO_REUSEPORT` (another local process could pre-bind or race the port), and the token is minted *before* the bind is confirmed — a failed/re-raced bind could print a URL for a port a different process now owns.
- **Unauthorized responses leaking content.** No requirement states that 401/403/404 and 5xx responses must be **content-free** (no session data, no stack traces, no token echo, uniform body) — an error path is a classic side channel for the very session content the token protects.
- **WebSocket/upgrade bypass.** NR-5 defers streaming, but nothing requires the middleware to **reject `Upgrade`/WebSocket requests** outright. If a future SSE/WS path is added, or Starlette's routing answers an upgrade before the ASGI token middleware runs, the Origin/token guard could be bypassed. State "no upgrade endpoints; upgrade requests are rejected" as an explicit invariant.
- **Degradation half-up (FR-SRV-8) requirement gap.** R1-S10 tested atomic degradation in the *plan*; the *requirement* itself does not state the ordering invariant (import-check extras → *then* mint token → *then* bind), so an implementer could mint/print the token before discovering extras are missing.

**Numbered suggestions (F-prefix):**

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R2-F1 | Security | critical | Add a serve-mode **Content-Security-Policy** requirement to FR-SRV-4: the served page must set a strict CSP (e.g. `default-src 'none'; script-src 'self'` or a nonce; no `unsafe-inline` on the markdown-render path; `connect-src 'self'`), and the model-answer markdown must be rendered through a **sanitizer/escape** that cannot emit active content. Rationale that serve mode *escalates* an existing XSS to token theft must be stated. | `view.py` renders untrusted model text as markdown; in serve mode the page holds a spend-capable token in `sessionStorage`, so a renderer XSS = token exfil + attacker-funded LLM spend. The static-view XSS hardening (escape `<` in embedded JSON) does not cover the client markdown path in a token-bearing context. | §2 FR-SRV-4 (new sub-bullet (e) "Content isolation") | Test: inject a model answer containing `<img src=x onerror=…>` / `[x](javascript:…)` / `<script>`; assert it renders inert (no script exec, no token read) and CSP header present; assert `connect-src` blocks exfil to a foreign host. |
| R2-F2 | Security | high | State explicitly in FR-SRV-4b/4d that **`GET /session` requires the token AND passes the Host/Origin guard**, and that no route returns session content before the token check. Clarify whether the bootstrap `GET /` embeds session JSON (it does today, via `render_html`) and therefore must also be fully token-gated — i.e. a wrong/absent token on `GET /` returns **no** session content. | The token is "required on every request," but the model answers are the paid asset; if `GET /session` (or the token-in-URL `GET /` on a *wrong* token) leaks session JSON, an unauthorized local process reads the consultation for free. Currently unstated for GET. | §2 FR-SRV-4(b)/(d) | Tests: `GET /session` no token → 401 and empty body; `GET /?token=wrong` → 401 with no session JSON in the response; `GET /session` foreign Origin → 403. |
| R2-F3 | Security | high | Require all **unauthorized/error responses (401/403/404/5xx) to be content-free and uniform**: no session data, no file paths, no stack traces, no token echo, and identical shape regardless of whether the session/id exists (extends R1-F10's oracle concern to the error *body*, not just status/timing). | Error bodies are a standard side channel; a 404 that says "session <id> not found" vs a generic 404 leaks session existence, and a 500 traceback can leak session content or filesystem layout to an unauthorized caller. | §2 FR-SRV-4 (new sub-bullet or §2 FR-SRV-8) | Test: trigger 401/403/404/500 paths; assert bodies contain no session id, path, prompt, answer, or token substring and are byte-identical across existing/non-existing ids. |
| R2-F4 | Security | medium | Bound `--open` token transport in FR-SRV-1: prefer launching via an API that does not expose the URL in the global process table where feasible, and state that the tokenized URL passed to `--open` is a known OS-local leak surface (process args, launcher history) accepted only under the single-local-user trust model (NR-2). Pair with R1-F2 (browser-history) as the *other half* of URL leakage. | R1-F2 handled the token in browser history/Referer; the `--open` handoff leaks the same token to `ps`/shell/launcher logs — a distinct surface no requirement bounds. | §2 FR-SRV-1 / §3 NR-2 | Manual/integration: run `--open`; assert the token surface is documented; assert (where the launcher allows) the URL is not passed as a visible argv; assert consistency with the NR-2 trust statement. |
| R2-F5 | Risks | medium | Add to FR-SRV-1 that the ephemeral bind must **not** set `SO_REUSEADDR`/`SO_REUSEPORT`, that the token/URL are printed **only after** the bind is confirmed and `getsockname()` read, and that a bind failure aborts before any token is minted or printed (TOCTOU on the ephemeral port). | Minting/printing a token for a port before the bind is confirmed, or allowing address reuse, lets another local process race or pre-own the port; the printed URL could then point at a foreign listener. | §2 FR-SRV-1 (add clause) | Test: assert socket options exclude REUSE flags; simulate bind failure → assert no token minted/printed and clean abort; assert order (bind → getsockname → mint/print). |
| R2-F6 | Interfaces | medium | Add an explicit invariant to FR-SRV-4/NR-5: **no WebSocket/SSE/`Upgrade` endpoints exist in v1, and any request with `Connection: Upgrade`/`Upgrade:` is rejected** (before or independent of routing) so streaming's deferral cannot become a middleware-bypass path later. | NR-5 defers streaming but does not forbid upgrade *requests*; if the token/Origin guard is route-level rather than ASGI-scope-level, an upgrade could dodge it, and a future SSE add-on could silently open an unguarded channel. | §2 FR-SRV-4 or §3 NR-5 | Test: send a WebSocket `Upgrade` request with a valid token → rejected (426/400); assert the token/Origin middleware runs in ASGI scope for all request types including upgrades. |
| R2-F7 | Validation | low | Strengthen FR-SRV-8 into an ordered, testable invariant at the *requirement* level: on serve launch the sequence is **(1) import extras (2) load/validate session (3) mint token (4) bind (5) print URL**, and a failure at any step before (4) must leave **no token minted, no port bound, no URL printed** — degrading to the static write. | R1-S10 put the atomic-degradation test in the plan; the requirement never states the ordering, so the "never half-up / token-exposed" guarantee (focus item #6) is prose, not a spec an implementer can violate visibly. | §2 FR-SRV-8 | Test: monkeypatch each early step to fail; assert static file written and (no token in output/logs, no socket bound) at every pre-bind failure point. |

### Endorsements / Disagreements (R2, on prior untriaged R1 items)

**Endorsements** (R1 items R2 agrees should be applied):
- R1-F1: Correct — the invariant is the *resolved bound socket address* (`getsockname()` ∈ loopback), not a literal-string blacklist; my R2-F5 depends on this ordering (bind → getsockname → print).
- R1-F2: Endorse — token-in-URL is the top leakage surface; R2-F4 extends it to the `--open`/OS-process-list half, so treat F2 and R2-F4 as the two halves of one leakage requirement.
- R1-F3: Endorse — fail-closed on missing/`null` Origin is the *actual* bypass; my R2-F2/F6 assume this Origin rule also covers `GET /session` and upgrade requests.
- R1-F4 / R1-F5: Endorse both — a hard spend ceiling and replay/idempotency defense are the correct bound; a turn cap alone is insufficient. Note the CSP gap (R2-F1) is what makes an *attacker-driven* replay realistic, so F4/F5 and R2-F1 reinforce each other.
- R1-F6: Endorse — in-process `asyncio.Lock` gives false cross-process safety; a session-level lockfile (or documented accepted risk) is required.
- R1-F8: Endorse — pin a golden hash; "byte-identical to today" drifts. R2 adds only that the golden must also be asserted **token/endpoint-substring-free** (F8 already notes this).
- R1-F10: Endorse and extend — constant-time compare + token-before-session-load; R2-F3 extends the same oracle concern from status/timing to the error *body*.

**Disagreements / scope notes:**
- R1-F9 (low): Agree the FR-SRV-4b ↔ OQ-1 contradiction should be closed, but I'd resolve it toward a **non-`sessionStorage`** transport given R2-F1 (any-script-readable storage is an XSS exfil target). If OQ-1 lands on `sessionStorage`, F1's CSP/sanitizer requirement becomes load-bearing rather than defense-in-depth — flag that dependency during triage rather than treating F9 as purely editorial.

