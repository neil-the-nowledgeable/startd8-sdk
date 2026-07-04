# Consultation Serve Mode — Implementation Plan

**Version:** 1.1 (Post-CRP — R1+R2 applied; see §E)
**Date:** 2026-07-03
**Status:** Draft — pairs with `WEB_UI_SERVE_REQUIREMENTS.md` v0.3

---

## A. Discoveries (what planning revealed)

| Requirements assumed | Planning revealed | Consequence |
|----------------------|-------------------|-------------|
| Reuse `create_app` | Workflow routes; `startd8 serve` binds `0.0.0.0` | New `consultation/serve.py`; bind `127.0.0.1` only |
| Reuse `APIKeyMiddleware` | POST-only, no Origin/Host | Stronger middleware: token-on-all + Origin/Host allowlist |
| Call `ConsultationService.follow_up` | Facade uses `asyncio.run` (can't nest) | `await engine.follow_up` in the async route |
| Static `render_html` is enough | It's static by design | Add serve-config injection; template JS branches on it |
| Just runs follow-ups | Needs keys + spends money | `build_roster` under doppler + cost guard/turn cap |

The code is small; **security is the load-bearing 80%**. Build order: security skeleton first, then wire
the executor, then the interactive JS.

## B. Milestones

### M0 — Design lock (this doc set). **Offer CRP before build** (security-dominated → high value).

### M1 — Loopback server + security middleware (FR-SRV-1/4/6)
1. `consultation/serve.py`: a Starlette app (soft-import; FR-SRV-8 fallback) with routes
   `GET /` (page), `GET /session` (current JSON), `POST /reply`. Bind `127.0.0.1:0` (ephemeral);
   **assert host is loopback**, refuse otherwise.
2. `ConsultTokenMiddleware`: mint a `secrets.token_urlsafe(32)` at startup; require it on **every** request
   (query param on `GET /`, `X-Consult-Token` header on POST — OQ-1); constant-time compare.
3. Origin/Host guard: reject non-`127.0.0.1|localhost` `Host`; reject POST with foreign `Origin`.
4. `asyncio.Lock` per server (single session) → serialize `/reply`; overlapping POST → 409 (FR-SRV-6).

### M2 — Executor route (FR-SRV-3/5/9)
1. `POST /reply` body `{prompt, target}` → load session, rebuild roster (`build_roster`, cached at
   startup), `await engine.follow_up(session, roster, prompt, target)`, persist, return updated session.
   Text-only (NR-6). Enforce the **turn cap** (FR-SRV-5) → 429 when exceeded.
2. Structured errors surface per panel (reuse the Turn error shape); missing-key models already degrade.

### M3 — Serve-config injection + interactive JS (FR-SRV-2/10)
1. `render_html(session, serve=None)`: when `serve={token, base}` is passed, inject a
   `<script id="serve-config">` block (token + `/reply` URL). Default (`serve=None`) → **byte-identical**
   static output (regression test).
2. Template JS: if `#serve-config` present, the composer's button becomes **Send** (POST `/reply` with the
   token header) and on success re-renders panels from the returned session; else the existing
   copy-command composer (FR-WUI-10) stays. Cost note shows model count before Send (FR-SRV-5).

### M4 — CLI `--serve` + lifecycle (FR-SRV-1/7/8)
1. `consult web ... --serve [--port] [--max-turns] [--timeout] [--open]`: build roster, mint token, start
   uvicorn on `127.0.0.1`, print the tokenized URL, `--open` it. Ctrl-C → clean shutdown; idle timeout.
2. Missing `startd8[server]` extras → message + write the **static** file instead (FR-SRV-8).

### M5 — Tests + acceptance
1. Security tests (highest priority): bind refuses non-loopback; missing/wrong token → 401; foreign
   Origin → 403; foreign Host → 403; other-session id → 404/blocked; overlapping POST → 409; turn cap → 429.
2. Executor test: a `/reply` with a stubbed engine adds a turn to the target model only; persisted.
3. `render_html(serve=None)` byte-identical to today (no serve leakage into the static file).
4. Acceptance: §4 scenario under doppler against the live-smoke session.

## C. Risks
- **DNS-rebinding / drive-by localhost** — the whole reason for token + Origin/Host + loopback; test all three.
- **Nested event loop** — must `await engine.follow_up`, never the `asyncio.run` facade, inside Starlette.
- **Runaway cost** — a stuck/retried client could spam Sends; turn cap + per-Send user action + lock.
- **Token leakage** — never log the URL-with-token at info; keep it out of Loki (redaction posture).
- **Soft dependency** — starlette/uvicorn optional; import-guard and fall back to static (FR-SRV-8).

## D. Traceability
| FR | Milestone |
|----|-----------|
| FR-SRV-1 | M1.1 + M4 |
| FR-SRV-2 | M3 |
| FR-SRV-3 | M2 |
| FR-SRV-4 | M1.1–M1.3 |
| FR-SRV-5 | M2.1 + M3.2 |
| FR-SRV-6 | M1.4 |
| FR-SRV-7 | M4 |
| FR-SRV-8 | M1.1 + M4.2 |
| FR-SRV-9 | M2.1 |
| FR-SRV-10 | M3.1 |

---

## E. Post-CRP Hardening (v1.1 — R1+R2 security review applied)

Concrete plan steps added by the CRP (all S-suggestions ACCEPTED; each also in `WEB_UI_SERVE_REQUIREMENTS`
v0.4 Appendix A). Build order unchanged — security skeleton first — but M1/M2 grow the most.

**M1 — server + middleware:**
- **M1.1 loopback (R1-S1):** bind then assert `getsockname()` ∈ `127.0.0.0/8`/`::1`; `IPV6_V6ONLY` (or IPv4-only);
  **no `SO_REUSEADDR`/`SO_REUSEPORT`**; order **bind → getsockname → mint → print** (R2-S4).
- **M1.2 token (R1-S2, R1-S10-oracle):** `secrets.token_urlsafe`; `secrets.compare_digest`; validate **before**
  session load; strip from access log; `Referrer-Policy: no-referrer`; page does `history.replaceState`.
- **M1.3 Origin/Host (R1-S3):** reject missing/`null` Origin on POST; `Host` == `127.0.0.1[:port]` only.
- **M1.4 lock (R1... ):** `asyncio.Lock` → 409; **plus cross-process refusal** of a second server on the id
  (advisory lockfile / `mkdir`-excl marker, released on shutdown) (R1-S5).
- **M1.5 CSP + ASGI-scope guard (R2-S1, R2-S6):** strict CSP header (`default-src 'none'; script-src 'self';
  connect-src 'self'`) on all responses; token/Origin middleware at ASGI scope; reject `Upgrade`/WebSocket (426/400).
- **M1.6 GET gating (R2-S2):** `GET /session` **and** `GET /?token=wrong` return **no** session JSON.
- **M1.7 uniform errors (R2-S3):** 401/403/404/409/429/5xx bodies content-free + byte-identical regardless of id.

**M2 — executor:**
- **M2.1 cost (R1-S4):** turn-cap + hard spend/call ceiling enforced **inside the lock, increment-before-paid-call**;
  **replay defense** (per-Send nonce consumed server-side). Exec **timeout** wraps `engine.follow_up` (R1-S6);
  on timeout → per-panel error + lock released.

**M3 — page:** sanitizer on the markdown-render path so injected model content can't emit active content or read
the token (R2-S1); the golden static output is unaffected.

**M4 — CLI:** print a **redacted** URL (not the full token) to the terminal (R1-S8); bound the `--open` argv leak
and document it as an NR-2 surface (R2-S5); redact the token from **any** crash/traceback path (R2-S8).

**M5 — tests (security-first):** DNS-rebinding blocked (R1-S9); atomic token-free degradation (R1-S10);
`render_html(serve=None)` == committed golden hash + no token/`/reply` substring (R1-S7); malicious-model-answer
cannot self-fund a follow-up — CSP + Origin + per-Send user-action all block auto-fire (R2-S7).

---

*v1.1 — Post-CRP (R1+R2, reviewer `claude-opus-4-8-1m`): all 18 plan S-suggestions mapped into §E. The
increment stays small-code / security-dominated; M1 (the security skeleton) is the critical path and was
the CRP's highest-value target.*

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

> **Triage (2026-07-04):** all 18 plan S-suggestions ACCEPTED and mapped into §E (R1: S1–S10; R2:
> S1–S8). Strongly convergent with the requirements F-suggestions; no rejections.

| ID | Suggestion | Mapped to |
|----|------------|-----------|
| R1-S1 | Resolved-address loopback + IPv6 dual-stack off | §E M1.1 |
| R1-S2 | Token: access-log exclusion + replaceState + Referrer-Policy | §E M1.2 |
| R1-S3 | Origin fail-closed (missing/null); narrow Host | §E M1.3 |
| R1-S4 | Atomic turn-cap + spend ceiling + replay nonce | §E M2.1 |
| R1-S5 | Cross-process second-server refusal | §E M1.4 |
| R1-S6 | Bounded execution timeout | §E M2.1 |
| R1-S7 | Golden-hash serve=None regression | §E M5 |
| R1-S8 | Redacted URL print (no full token to scrollback) | §E M4 |
| R1-S9 | DNS-rebinding negative test | §E M5 |
| R1-S10 | Atomic token-free degradation test | §E M5 |
| R2-S1 | CSP + sanitizer content isolation | §E M1.5 / M3 |
| R2-S2 | Token-gate GET /session + GET / | §E M1.6 |
| R2-S3 | Uniform content-free error bodies | §E M1.7 |
| R2-S4 | No REUSE flags; bind→getsockname→mint order | §E M1.1 |
| R2-S5 | Bound `--open` argv leak; document NR-2 surface | §E M4 |
| R2-S6 | ASGI-scope guard; reject Upgrade/WebSocket | §E M1.5 |
| R2-S7 | Malicious-answer cannot self-fund a follow-up (test) | §E M5 |
| R2-S8 | Redact token from crash/traceback paths | §E M4 |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none) | — | — | High-signal review; all accepted. | 2026-07-04 |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — claude-opus-4-8-1m — 2026-07-04

- **Reviewer**: claude-opus-4-8-1m
- **Date**: 2026-07-04 02:55:00 UTC
- **Scope**: First external review of the implementation plan, security-weighted per SERVE_CRP_FOCUS.md. Attacks the M1 security skeleton (bind/token/Origin-Host/cost/lock), the M2 executor wiring (nested loop, timeout), and the M3 byte-identity claim. Plan (S-prefix) suggestions here; requirements (F-prefix) in the requirements file; coverage matrix below.

**Executive summary (top risks / gaps):**

- M1.1 says "assert host is loopback, refuse otherwise" but the *how* is a string check on the requested bind; the plan should assert on the **resolved bound socket** and explicitly disable IPv6 dual-stack (mirrors R1-F1). "Bind `127.0.0.1:0`" also never states IPv6 is off.
- M1.2 mints `token_urlsafe(32)` (256-bit — fine) but carries it as a **query param on `GET /`**; the plan has no step to strip it from the URL after bootstrap, set `Referrer-Policy`, or keep it out of Uvicorn's access log (which logs the full path incl. query by default → straight to Loki). The "never log at info" Risk is not wired to a concrete step.
- M1.3's Origin/Host guard accepts `localhost` and is silent on **missing/null Origin**; a non-browser POST with no Origin would pass a "reject *foreign* Origin" check. Needs an explicit fail-closed step.
- M2.1 enforces the turn cap but there is no **spend ceiling** and no **replay defense**; a retried/captured POST re-runs paid calls. The turn-cap check must be inside the lock and increment-before-spend.
- M1.4's lock is per-process; the plan has no step preventing a **second `--serve` on the same session id** → cross-process lost update. Either add a session lockfile step or record accepted-risk.
- M2.1 awaits `engine.follow_up` with **no timeout**; one hung provider call wedges the single worker + single lock. Add a bounded wait.
- M3.1's byte-identical claim has a regression test (M5.3) but no **pinned golden hash**; a hash assertion is stronger than "byte-identical to today," which drifts as "today" moves.
- M4.1 "print the tokenized URL" re-introduces the leak surface at the CLI/terminal-scrollback level; note the trade-off and prefer `--open` without echoing the full token, or print a redacted URL.

**Numbered suggestions (S-prefix):**

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-S1 | Security | critical | In M1.1 change "assert host is loopback" to "bind, then assert `socket.getsockname()` is in `127.0.0.0/8`/`::1`; disable IPv6 dual-stack (`IPV6_V6ONLY` or bind IPv4 only)". Refuse `0.0.0.0`, `::`, `0`, and any hostname resolving off-loopback. | The current wording invites a string check that `::`/`0`/dual-stack bypass; asserting the *actual bound address* is the real invariant (pairs with R1-F1). | §B M1 step 1 | Security test in M5.1: attempt binds to `0.0.0.0`/`::`/`::1`/`0`; assert only loopback succeeds and `getsockname()` is checked. |
| R1-S2 | Security | critical | Add an M1 step: after `GET /` serves the page, the token must be (a) excluded from Uvicorn's access log (configure `access_log`/log-format to drop the query string, or disable access log), and (b) stripped from the browser URL via `history.replaceState`, with `Referrer-Policy: no-referrer` on responses. | Uvicorn logs the full request path *including the query token* by default → the token lands in stdout/Loki; the plan's "never log at info" Risk has no implementing step. Pairs with R1-F2. | §B M1 (new step) / §C Risk "Token leakage" | Integration: run a served session, grep captured server logs + Loki for the token → absent; assert address bar cleared post-load; assert `Referrer-Policy` header. |
| R1-S3 | Security | high | In M1.3 add an explicit fail-closed rule for **missing/`null` `Origin`** on `POST /reply` (reject unless Origin equals the server's own origin), and narrow `Host` acceptance to `127.0.0.1[:port]` (decide on `localhost` explicitly). | "Reject POST with foreign Origin" does not cover *absent* Origin, which is the real bypass for non-browser clients; pairs with R1-F3. | §B M1 step 3 | M5.1 tests: POST with no Origin → 403; `Origin: null` → 403; correct Origin → 200. |
| R1-S4 | Security | high | In M2.1 (a) enforce the turn-cap **atomically inside the `asyncio.Lock`** with increment-before-paid-call, (b) add a hard **spend/total-call ceiling** independent of turn count, and (c) reject **replayed** POSTs (per-Send nonce consumed server-side). | A check-then-spend counter outside the lock is racy under retry/replay; turn count alone doesn't bound cost for large/expensive rosters. Pairs with R1-F4/F5; focus items #4. | §B M2 step 1 | M5: fire concurrent Sends at cap → one succeeds; replay a captured POST → rejected, stubbed engine call-count unchanged; trip spend ceiling independently → distinct error. |
| R1-S5 | Data | high | Add an M1/M4 step to **prevent a second server on a live session id** (e.g. `mkdir`-excl / advisory lockfile beside the session file, released on clean shutdown), or record the cross-process lost-update window as an accepted risk in §C. | The per-process `asyncio.Lock` (M1.4) does not serialize two processes on one session; store atomicity prevents corruption but not lost updates. Pairs with R1-F6; focus item #5. | §B M1.4 or M4 / §C Risks | Test: launch two `--serve` on one id → second refuses (or documents interleave); concurrent cross-process Sends → no dropped turn. |
| R1-S6 | Risks | medium | In M2.1 wrap `await engine.follow_up(...)` in a bounded timeout (config or default); on timeout return a structured per-panel error and release the lock. | The single worker + single lock means one hung provider call blocks all further Sends and clean 409s; idle-timeout doesn't fire mid-turn. Pairs with R1-F7. | §B M2 step 1 | Stubbed engine sleeps past timeout → structured error, lock freed, next Send works. |
| R1-S7 | Validation | medium | Strengthen M5.3: assert `render_html(serve=None)` equals a **committed golden hash** (not merely "byte-identical to today"), and assert no token/`/reply` substring appears in the `serve=None` output. | "Identical to today" drifts as the template evolves; a pinned golden hash is a stable regression anchor. Pairs with R1-F8. | §B M5 step 3 | CI: `sha256(render_html(s, serve=None)) == pinned_hash`; substring assertions. |
| R1-S8 | Ops | medium | In M4.1 avoid echoing the full tokenized URL to the terminal (scrollback/screen-share leak); prefer `--open` the URL and print a redacted form, or print only the port with a "opened in browser" note. Note the trade-off if `--open` is unavailable. | Printing the token-bearing URL re-creates the leakage surface the plan otherwise guards, in terminal history/scrollback. | §B M4 step 1 / §C Risk "Token leakage" | Manual: run without `--open`; assert printed line contains no full token (redacted); with `--open`, browser receives token but terminal does not print it. |

### Stress-test / adversarial pass (R1, S-prefix continued)

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-S9 | Security | medium | Add an M5 negative test that a **DNS-rebinding** client (correct `Host: 127.0.0.1` spoofed via a rebind, foreign real `Origin`) is blocked, and that a client sending `Host: 127.0.0.1` but connecting to a rebind hostname is rejected by the *resolved bound address + Origin* pair — proving Host+Origin actually stops rebinding rather than assuming it. | §C lists DNS-rebinding as "the whole reason" but M5.1 only tests foreign Host/Origin in isolation; the rebind case (valid Host, hostile Origin, cross-origin fetch) is the actual attack and must be tested end-to-end. | §B M5 step 1 | Simulated rebind: request with spoofed `Host: 127.0.0.1` + cross-site `Origin` → 403; assert the guard is the Origin check, not just Host. |
| R1-S10 | Validation | low | Add an M5 test that FR-SRV-8 degradation is **atomic and token-free**: when `starlette`/`uvicorn` import fails, assert no port is opened, no token is minted/printed, and the static file is written — i.e. the failure cannot leave the server half-up or a token exposed (focus item #6). | The plan falls back to static on missing extras but never proves the fallback doesn't partially initialize (mint token, half-bind) before failing. | §B M5 (new step) / §C Risk "Soft dependency" | Test with `starlette` import monkey-patched to fail: assert static file written, no socket bound, no token in output/logs. |

**Endorsements & Disagreements:** none — this is R1 (no prior untriaged suggestions to react to).

#### Review Round R2 — claude-opus-4-8-1m — 2026-07-04

- **Reviewer**: claude-opus-4-8-1m
- **Date**: 2026-07-04 03:20:00 UTC
- **Scope**: Second review of the implementation plan, security-weighted per SERVE_CRP_FOCUS.md. R1 covered the focus asks (bind, token-in-URL, null Origin, spend/replay, cross-process lock, timeout, byte-identity). R2 goes deeper on interactions R1 missed: no CSP/sanitizer step for the untrusted-model-content render path in a token-bearing page, `GET /session` token-gating, `--open`/process-list token leak, port TOCTOU/reuse, error-body content leaks, and WebSocket/upgrade guarding. Plan (S-prefix) here; requirements (F-prefix) in the requirements file; R2 coverage matrix below.

**Executive summary (top plan gaps R1 missed):**

- **No CSP / sanitizer step for the model-content render path.** M3.1/M3.2 inject serve-config and re-render panels from returned session JSON, reusing the static template's client markdown render. The plan has no step to add a **strict CSP header** or route model text through a sanitizer in serve mode — yet the page now holds a spend-capable token. A markdown-render XSS becomes token theft (mirrors R2-F1). This should be an M1 (header) + M3 (sanitizer) step.
- **`GET /session` not shown as token+Origin gated.** M1.1 lists `GET /session` as a route but M1.2/M1.3 describe the token/Origin guard generically; no step asserts `GET /session` (which returns the paid answers) 401s without the token and 403s on foreign Origin (mirrors R2-F2).
- **`--open` leaks the token to the OS.** M4.1 "print the tokenized URL … `--open` it" hands the token to a launcher visible in `ps`/history — a surface distinct from R1-S2/R1-S8 (access-log/scrollback). Add a step bounding `--open` transport (R2-F4).
- **Port TOCTOU.** M1.1 binds `127.0.0.1:0` but the plan mints the token in M1.2/M4.1 without pinning bind→getsockname→mint→print ordering or forbidding `SO_REUSEADDR`/`SO_REUSEPORT` (mirrors R2-F5).
- **Error bodies uncontrolled.** M5.1 asserts status codes (401/403/404/409/429) but no step asserts the error **bodies** are content-free and uniform (no session id/prompt/answer/traceback/token) — an info-leak side channel R1-F10 only partially reached (timing/status).
- **Upgrade requests unguarded.** No M-step rejects `Upgrade`/WebSocket requests; NR-5 defers streaming but the middleware must still refuse upgrades so a future SSE path can't bypass the ASGI-scope guard (mirrors R2-F6).

**Numbered suggestions (S-prefix):**

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R2-S1 | Security | critical | Add steps: (M1) set a strict CSP header on all served responses (`default-src 'none'; script-src 'self'; connect-src 'self'`, no `unsafe-inline` reaching the markdown path); (M3) render model answers through a sanitizer that cannot emit active content, and verify the serve-mode page's token-in-`sessionStorage` is unreadable by injected content. | The static template renders untrusted model markdown; in serve mode the page holds a spend-capable token, so a renderer XSS = token exfil + attacker-funded spend. No current step contains injected model content in the token-bearing context. | §B M1 (header step) + M3.2 (sanitizer) / §C Risks (new "Stored-content XSS → token theft") | M5: inject `<img onerror>`/`javascript:` link/`<script>` in a model answer → assert inert, CSP present, `connect-src` blocks foreign exfil, token not readable by injected script. |
| R2-S2 | Security | high | In M1.2/M1.3 explicitly apply the token AND Origin/Host guard to `GET /session` (and confirm `GET /?token=wrong` returns no session JSON): assert no route returns session content before the token check. | `GET /session` returns the paid model answers; the plan lists it as a route but never states it is token+Origin gated, so an unauthorized local process could read the consultation. | §B M1 steps 2–3 / M5.1 | M5.1: `GET /session` no token → 401 empty body; foreign Origin → 403; `GET /?token=wrong` → 401 with no session JSON in body. |
| R2-S3 | Security | high | Add an M5 step asserting all error responses (401/403/404/409/429/5xx) are **content-free and uniform** — no session id, prompt, answer, file path, stack trace, or token substring, and byte-identical whether or not the target id exists. | M5.1 tests status codes only; the error *body* is a classic side channel that can leak session existence/content to an unauthorized caller (extends R1-S/F10 from timing to body). | §B M5 step 1 / §C Risks | M5: trigger each error path; assert bodies contain none of the forbidden substrings and are identical for existing vs non-existing ids. |
| R2-S4 | Security | medium | In M1.1 forbid `SO_REUSEADDR`/`SO_REUSEPORT` on the listen socket and pin the launch order **bind → `getsockname()` → mint token → print/`--open` URL**; a bind failure aborts before any token is minted or printed. | Minting the token before the bind is confirmed, or allowing address reuse, permits a local process to race/pre-own the ephemeral port so the printed URL targets a foreign listener. | §B M1 step 1 + M4.1 | M5: assert socket opts exclude REUSE flags; simulate bind failure → no token minted/printed, clean abort; assert the ordering. |
| R2-S5 | Ops | medium | In M4.1 bound the `--open` token handoff: where the launcher API allows, avoid passing the full tokenized URL as a visible argv, and document the `ps`/history leak as an accepted single-local-user (NR-2) surface distinct from access-log (R1-S2) and scrollback (R1-S8). | `--open`'s URL is visible in the process table and launcher history — a token-leak surface no current step bounds. | §B M4 step 1 / §C Risk "Token leakage" | Manual: run `--open`; assert (where possible) the URL is not a visible argv; assert the leak is documented and consistent with NR-2. |
| R2-S6 | Interfaces | medium | Add an M1 step: the ASGI token/Origin middleware runs for **all** scope types and any `Upgrade`/WebSocket request is rejected (426/400) since v1 has no streaming endpoints (NR-5). | If the guard is route-level rather than ASGI-scope-level, an upgrade request could bypass it; forbidding upgrades now keeps a future SSE add-on from silently opening an unguarded channel. | §B M1 (new step) / §C Risks | M5: send a WebSocket upgrade with a valid token → rejected; assert middleware runs in scope for upgrade requests. |

### Stress-test / adversarial pass (R2, S-prefix continued)

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R2-S7 | Validation | low | Add an M5 negative test that a **malicious model answer cannot self-fund a follow-up**: render a session whose stored answer contains an auto-submitting form / `fetch('/reply', …)` payload; assert CSP + Origin + per-Send user-action (FR-SRV-5) all block the auto-fire so injected content cannot spend money without the local user's click. | Combines the CSP gap (R2-S1) with the cost guard (FR-SRV-5): the worst case is not just token theft but injected content triggering paid `/reply` calls; the plan should prove the per-Send user-action + CSP `connect-src` defeat auto-fire. | §B M5 (new step) | M5: session answer embeds an auto-`fetch('/reply')`; assert no paid call occurs (stubbed engine call-count 0) absent an explicit user click. |
| R2-S8 | Ops | low | In M4.1/§C add a step to redact the token from **any** crash/traceback path (uvicorn exception dumps, `--open` failures) — not just the info access log (R1-S2) — so an error at launch cannot print the token-bearing URL to stderr/Loki. | R1-S2 covers the *access* log; an exception during startup (bind race, launcher failure) can still dump the token-bearing URL via the error logger, which R1 did not close. | §C Risk "Token leakage" / §B M4 | Test: force a startup exception after mint → assert the token substring appears in no captured stderr/Loki output. |

### Endorsements / Disagreements (R2, on prior untriaged R1 items)

**Endorsements** (R1 S-items R2 agrees should be applied):
- R1-S1: Endorse — assert the resolved bound address + disable IPv6 dual-stack; R2-S4's ordering (bind→getsockname→mint→print) builds directly on it.
- R1-S2: Endorse — dropping the query token from the uvicorn access log is essential; R2-S8 extends the same concern to crash/exception log paths R1-S2 didn't cover.
- R1-S3: Endorse — fail-closed on missing/`null` Origin; R2-S2/R2-S6 assume this rule also guards `GET /session` and upgrade requests.
- R1-S4: Endorse strongly — turn cap under the lock + spend ceiling + replay defense; R2-S7 shows why (injected content self-funding a Send) this is not merely a "runaway retry" concern.
- R1-S5: Endorse — cross-process session lockfile (or documented accepted risk) is required; the in-process lock is a false guarantee.
- R1-S6: Endorse — bounded timeout on `await engine.follow_up` so a hung provider can't wedge the single worker/lock.
- R1-S7: Endorse — pin a golden hash rather than "byte-identical to today."
- R1-S9: Endorse — test the *actual* rebind case (valid Host, hostile Origin) end-to-end, not Host/Origin in isolation.
- R1-S10: Endorse and extend — atomic/token-free degradation; R2-S4's ordering and requirements R2-F7 make the pre-bind failure invariant explicit.

**Disagreements / scope notes:**
- R1-S8 (redacted-URL print): Agree in spirit, but under the single-local-user trust model (NR-2) printing the URL for copy/paste has real UX value; rather than *always* redacting, scope it as "redact by default, `--print-url` opt-in" so R1-S8 and R2-S5 (`--open` argv leak) are handled as one policy rather than two conflicting ones.

---

## Requirements Coverage Matrix — R1

Analysis only (not triage). Maps each requirements FR/NR to the plan milestone(s) that address it.

| Requirement | Plan Step(s) | Coverage | Gaps |
| ---- | ---- | ---- | ---- |
| FR-SRV-1 (`--serve` loopback launch, ephemeral port, tokenized URL) | M1.1, M4.1 | Full | — |
| FR-SRV-2 (interactive Send composer, in-place panel update, fallback) | M3.1, M3.2 | Full | — |
| FR-SRV-3 (executor reuse, `await engine.follow_up`, persist) | M2.1 | Partial | No per-request timeout bound on the awaited call (R1-S6/R1-F7); single-worker wedge risk unaddressed. |
| FR-SRV-4(a) loopback bind only | M1.1 | Partial | Assertion is on requested host, not resolved bound address; IPv6 `::1`/`::`/dual-stack not enumerated (R1-S1/R1-F1). |
| FR-SRV-4(b) per-run token on every request | M1.2 | Partial | Token-in-URL leakage (access log, history, Referer) has no mitigation step; constant-time compare present in plan but not token-before-session-load ordering (R1-S2/R1-F2/R1-F10). |
| FR-SRV-4(c) Origin/Host allowlist | M1.3 | Partial | Missing/null `Origin` behavior unspecified; `localhost` acceptance not narrowed (R1-S3/R1-F3). |
| FR-SRV-4(d) single-session confinement | M2.1 (loads the one session) | Partial | No explicit plan step asserting path/session-traversal refusal or no-directory-listing; relies on implicit single-id load. Recommend an explicit M1 guard + test. |
| FR-SRV-5 (cost guard: turn cap + per-Send action + cost surfacing) | M2.1, M3.2 | Partial | Turn cap not shown enforced under lock; no hard spend ceiling; no replay/idempotency defense (R1-S4/R1-F4/R1-F5). |
| FR-SRV-6 (concurrency lock, 409) | M1.4 | Partial | In-process only; cross-process second-server-on-same-session window open (R1-S5/R1-F6). |
| FR-SRV-7 (lifecycle, idle timeout, port release, token regen) | M4.1 | Full | (Idle-timeout default is OQ-3, correctly deferred.) |
| FR-SRV-8 (graceful degradation → static, per-model failure isolation) | M1.1, M4.2 | Partial | No test that the degradation is atomic/token-free (no half-up server) (R1-S10). |
| FR-SRV-9 (keys/roster via `build_roster` under doppler, missing-key non-fatal) | M2.1, M4.1 | Full | — |
| FR-SRV-10 (opt-in; static byte-identical when serve absent) | M3.1, M5.3 | Partial | Byte-identity anchored to "today" not a pinned golden hash; no assertion token/endpoint absent from `serve=None` output (R1-S7/R1-F8). |
| NR-1..NR-7 (non-goals: no remote, not multi-user, follow-ups only, not default, no streaming, no image upload, no workflow-server extension) | Enforced across M1–M4 (bind, opt-in, text-only, own module) | Full | Non-goals are respected by the plan; NR-2 trust model (token = anti-CSRF, not multi-user) is consistent with FR-SRV-4. |

---

## Requirements Coverage Matrix — R2

Analysis only (not triage). Re-examines coverage after R2 with the R2 findings folded in; focuses on rows R1 marked Full/Partial that R2 downgrades or refines. Cites the R2 F/S ids driving each change.

| Requirement | Plan Step(s) | Coverage | Gaps (R2 refinement) |
| ---- | ---- | ---- | ---- |
| FR-SRV-2 (interactive Send composer, in-place panel re-render) | M3.1, M3.2 | Partial (was Full in R1) | Re-rendering untrusted model markdown in a token-bearing page has no CSP/sanitizer step → stored-XSS → token-theft escalation (R2-S1/R2-F1); injected content could auto-fire a paid `/reply` (R2-S7). |
| FR-SRV-4(b) per-run token on every request | M1.2 | Partial | R1 gaps stand; add: `GET /session` (paid answers) not shown token-gated (R2-S2/R2-F2); token in `sessionStorage` is script-readable → depends on CSP (R2-F1). |
| FR-SRV-4(c) Origin/Host allowlist | M1.3 | Partial | R1 null-Origin gap stands; add: `Upgrade`/WebSocket requests not rejected → possible ASGI-scope bypass path (R2-S6/R2-F6). |
| FR-SRV-4(d) single-session confinement | M2.1 | Partial | Add: error/404 bodies not asserted content-free/uniform → session-existence & content leak side channel (R2-S3/R2-F3). |
| FR-SRV-1 (loopback launch, ephemeral port, tokenized URL) | M1.1, M4.1 | Partial (was Full in R1) | No REUSEADDR/REUSEPORT prohibition, no pinned bind→getsockname→mint→print ordering → port TOCTOU (R2-S4/R2-F5); `--open` leaks the token to the OS process table/history (R2-S5/R2-F4). |
| FR-SRV-8 (graceful degradation → static) | M1.1, M4.2 | Partial | R1-S10 stands; add: startup crash/exception log path can dump the token-bearing URL (not just the access log) (R2-S8); requirement lacks the ordered pre-bind invariant (R2-F7). |
| (New cross-cutting) Content isolation / CSP | (none) | Missing | No requirement or plan step sets a CSP or sanitizes model content in serve mode; this is the highest-value new gap (R2-F1/R2-S1) and interacts with FR-SRV-5 cost guard (R2-S7). |
