# Welcome Mat 2.0 — Implementation Plan

**Version:** 0.2 (Post-CRP R1–R4 — pairs with `WELCOME_MAT_2.0_REQUIREMENTS.md` v0.3)
**Date:** 2026-06-26
**Status:** Draft

> This plan maps each FR to concrete files/seams and records what the codebase reveals. Discoveries
> that change the requirements are collected in §6 and fed back into requirements §0 (v0.2).

---

## 1. Architecture at a glance

Everything new attaches to `kickoff_experience/web.py:build_kickoff_app` (the FastAPI factory) and
reuses three existing subsystems verbatim:

| Pillar | Reuses | New surface |
|--------|--------|-------------|
| Download (FR-WM2-1..4, 11, 12) | `concierge/writes.py` `_KICKOFF_FILES`/`_AUTHORING_FILES` + `_load_template`/`_render_input` | a public manifest accessor + 3 GET routes + an in-memory zip |
| Chat (FR-WM2-5..9) | `chat.py` `build_kickoff_registry` + `new_kickoff_chat` + `KickoffChat` + `utils/agent_resolution.resolve_agent_spec` | an agent threaded into the app + a chat-session store + 1 async POST route + overview render |
| Templates (FR-WM2-10..12) | `templates/authoring/*` structure | author `conventions.md` + a manifest/index doc + a completeness test |

---

## 2. Pillar 1 — Template download

**S1. Public manifest accessor (FR-WM2-4, 11).** In `concierge/writes.py`, add
`kickoff_template_manifest() -> list[TemplateEntry]` deriving from the existing
`_KICKOFF_FILES + _AUTHORING_FILES` (the lists stay the single source of truth). Each entry:
`{key, template_rel, dest, group, label}` where `key` is a stable slug (e.g. `package/kickoff-intro`,
`authoring/requirements-template`). This is the closed key space FR-WM2-2/NR-3 depend on.

**S2. Download routes in `web.py` (FR-WM2-1..3).**
- `GET /templates` → HTML list rendered from the manifest (label, dest, group, bytes via
  `len(content.encode())`). Linked from `_render_overview`. Read-only; no CSRF; available in every mode.
- `GET /templates/file/{key}` → look up the manifest entry by `key`; 404 (typed) on miss; return
  `Response(_render_input(rel, posture) or _load_template(rel), media_type=…, headers={Content-Disposition: attachment; filename="<dest basename>"})`. **Key-only lookup ⇒ no path param ⇒ no traversal** (NR-3 satisfied structurally).
- `GET /templates/bundle.zip` → build a `zipfile.ZipFile` in a `BytesIO` with each entry at its
  `dest` path; stream as `application/zip`. Posture defaults to `prototype` (a `?posture=` query may
  select, validated against `VALID_POSTURES`).
- Emit `template_downloaded` / `template_bundle_downloaded` (FR-WM2-14).

**S3. Tests.** Manifest↔instantiate parity (same rel set); key 404; Content-Disposition present;
no path param accepted; zip contains exactly the manifest dests; bytes match `_load_template`.

## 3. Pillar 2 — Home-page agentic chat

**S4. Thread an agent into the app (OQ-3 → resolved).** `build_kickoff_app(..., agent: BaseAgent | None = None)`.
`serve_kickoff` + the `start` CLI gain an optional `--agent` (default `Models.CLAUDE_SONNET_LATEST`),
resolved with `resolve_agent_spec` inside a try/except that mirrors `cli_kickoff.py:chat_cmd` — on
failure, `agent=None` (chat disabled, server still serves). One agent per server process.

**S5. Chat-session store (OQ-1 → resolved).** `_SessionStore` holds CSRF tokens, **not** chat history
— so add a small `_ChatStore` modeled on it: `session_id -> (KickoffChat, last_used, turns)`, idle
expiry (`_IDLE_S`), a per-session turn cap (FR-WM2-9 cost guard, OQ-7), bounded entry count (evict
oldest, like `concierge_view._survey_cache`). `KickoffChat` is built lazily per session via
`new_kickoff_chat(agent, root)`.

**S6. Async chat endpoint (OQ-2 → resolved: use `async def`).** `POST /chat` (`async def`) takes
`message` + a chat-session cookie; calls `await chat.ask(message)` directly (no `asyncio.run` —
uvicorn owns the loop); returns `{text, cost: {turns, tokens, usd}}`. Read-only by construction (the
registry is `allow_effect_classes=("read",)`; `handle_kickoff_read` is the floor). 500-safe: any
agent error returns a typed `chat_error` JSON, never crashes the page.

**S7. Overview render (FR-WM2-5, OQ-6).** Decision: **inline panel on `/`** (single home page), posting
to `/chat`. `_render_overview` gains a chat panel + the posture banner when `agent is not None`; when
`None`, a disabled panel with the degradation message (FR-WM2-8). Emit `chat_turn` / `chat_unavailable`.

**S8. Propose-only bridge (FR-WM2-7).** No new endpoint and **no new tool**. The chat reply may include
a suggested friction draft / instantiate posture (assistant text the user copies, or — thin
enhancement — a "prefill" button that populates the existing `/concierge` friction/instantiate form
client-side). Submission goes through the **unchanged** `/concierge/friction` / `/concierge/instantiate`
(CSRF + loopback + one-time-intent + preview-then-apply all intact). The loop never posts.

**S9. Tests.** Read-floor preserved (no write tool reachable); `agent=None` ⇒ disabled panel + 200
home; async endpoint returns text+cost; turn cap enforced; chat error ⇒ typed JSON not 500; events
exclude message text.

## 4. Pillar 3 — Complete the template set

**S10. Author `docs/design/kickoff/templates/authoring/conventions.md` (FR-WM2-10).** Match
`observability.md`/`business-targets.md` structure; cover `conventions.yaml` (stack, module paths,
naming, `data_model:` cross-cutting choices, field authorship) + the production(architect-authored)
vs prototype(templated) rule from `KICKOFF_INPUT_PACKAGE_GUIDE.md` §5.

**S11. Index doc + manifest assertion (FR-WM2-11, 12).** A short `templates/README` row set (or extend
`templates/authoring/README.md`) naming the complete set; the FR-WM2-4 accessor is the machine-readable
manifest. Completeness test: every manifest entry resolves via `_load_template`; package + quintet all
present; no orphan rows.

**S12. (Pending OQ-5)** If authoring `*.md` guidance should also be downloadable, they must be added to
the packaged `concierge_templates/` tree first (they live only under `docs/` today). Deferred to the
reflect pass / CRP.

## 5. Sequencing

1. S1 manifest accessor → S2 download routes → S3 tests (self-contained, `$0`, lowest risk — ship first).
2. S10 `conventions.md` + S11 index/manifest + S12 decision (docs-only, parallelizable).
3. S4 agent threading → S5 chat store → S6 endpoint → S7 overview → S8 bridge → S9 tests (largest surface; do last).

## 6. Planning discoveries (feed back to requirements §0)

| Requirements assumed (v0.1) | Planning revealed | Impact on requirements |
|-----------------------------|-------------------|------------------------|
| P-A "reuse, don't re-implement" applies uniformly | Download + templates are pure reuse, but **chat needs genuinely new plumbing**: an agent threaded through `build_kickoff_app`/`serve_kickoff`/`start`, AND a new chat-session store (the `_SessionStore` holds CSRF, not history). | Soften P-A for the chat: reuse the *loop/registry/cost*; acknowledge new *agent-threading + session-store* plumbing. (OQ-1, OQ-3) |
| Chat endpoint shape open (OQ-2) | Routes are sync `def`; `AgenticSession.ask` is async; uvicorn owns the loop ⇒ `POST /chat` must be `async def` calling `await` directly (the CLI's `asyncio.run` is a CLI-only bridge). | Resolve OQ-2: async endpoint. |
| Agent source open (OQ-3) | `serve_kickoff` has no agent; the CLI resolves via `resolve_agent_spec(spec or Models.CLAUDE_SONNET_LATEST)` with a try/except degradation already written. | Resolve OQ-3: one agent per server, `--agent` flag, reuse the CLI's degradation pattern → directly satisfies FR-WM2-8. |
| "Author the missing templates" (P3) sounds large | The 11 packaged templates **all exist**; the *only* genuinely missing file is `conventions.md` authoring guidance. P3 is narrow. | Narrow FR-WM2-10 to `conventions.md` + manifest/index; mark P3 "thinner than feared." |
| Download is the trivial pillar | True, but the real risk is **path traversal / arbitrary-file disclosure** — mitigated structurally by manifest-**key** lookup (no path param). | Elevate the key-closure invariant (already NR-3/FR-WM2-2) as the download acceptance criterion. |
| Posture substitution only matters at instantiate | `conventions.yaml` carries a posture-resolved provenance placeholder; a downloaded copy must resolve it too, else the download differs from instantiate output. | FR-WM2-4 must state download applies the same `_render_input` posture substitution. |
| Chat is "just another panel" | It is the **only non-`$0`, only-stateful, only-async, only-needs-a-key** surface in the whole Welcome Mat. | Make graceful degradation + cost visibility first-class (FR-WM2-8/9), not afterthoughts. |

---

## 7. CRP R1–R4 refinements (fold into the steps above)

> All 16 plan suggestions accepted (2 phased). These sharpen the steps without changing the
> architecture; each is anchored to the step it refines and the requirement it satisfies.

**S1 (manifest accessor)** — each `TemplateEntry` carries `group: package | authoring` (R3-S1). The
accessor **validates each `dest`** as a safe relative path (no leading `/`, no `..`, no backslash) and
the bijection `keys ↔ _KICKOFF_FILES+_AUTHORING_FILES` at construction (R1-S8, R3-S6 → FR-WM2-16).

**S2 (download routes)** — `GET /templates/file/{key}`: `unquote` once → exact manifest-key match →
typed 404 on `..`/`%2e%2e`/leading-`/`/unknown (R1-S6); per-entry `Content-Type`+`charset=utf-8`,
filename = `dest` basename (R2-S8); `?posture=` validated vs `VALID_POSTURES` → `posture_invalid` 400
(R4-S7). `GET /templates/bundle.zip`: `?with_authoring=` filter (R3-S1) + uncompressed-bytes ceiling →
413 `bundle_too_large` (R1-S7). `GET /templates` index: posture selector + authoring toggle (R3-S4).

**S3 (download tests)** — triple-byte parity (single / bundle / instantiate) × all keys × postures
(R2-S6); bijection + dest-safety (R1-S8, R3-S6).

**S5/S6 (chat store + endpoint)** — separate `kickoff_chat` httponly+strict cookie, issued on `GET /`,
`chat_session_expired` on miss (R1-S2, R4-S5); in-memory-only, wipe `session.messages` on eviction
(R3-S5); per-session `asyncio.Lock` / `chat_busy` (R2-S3); inbound `message` cap → `message_too_long`
pre-provider (R2-S5); `_host_ok` + chat rate window (R1-S1); budget via shared
`kickoff_chat_session_config()` `SessionConfig` (incl. `max_tool_calls_per_turn`), `chat_budget_exceeded`
(R2-S1, R4-S4); map `AgenticResult.stop_reason` → typed `chat_<reason>` (R4-S3); sanitized provider-error
codes, no key substrings (R1-S4); `mode in (preview,inspect)` → `preview_only` (R2-S4); stable JSON
schema `{ok,text,cost{…,stop_reason?},propose?,code?,message?}` (R3-S7).

**S4 (agent threading)** — thread `--agent` through `cli_kickoff start` → `serve_kickoff` →
`build_kickoff_app` (both omit it today) (R4-S1).

**S7 (overview)** — escape assistant `text` via `_esc`; home-page templates link + Concierge
`next_action` CTA from `build_concierge_view` (R3-S2, R2-S7).

**S8 (propose bridge)** — server **produces+validates** `propose` from `AgenticResult` (never parse
prose), omit on invalid/oversize; client fills only empty fields via `value`/`textContent`, never
`innerHTML`; never carries csrf/intent (R1-S3, R4-S2, R3-S2).

**S2/S6/S7 (telemetry)** — register events in `telemetry.py` `FUNNEL_EVENTS` + `WM2_EVENT_ATTR_ALLOWLIST`;
emit via `emit()` (R3-S3).

**S9 (tests)** — static import guard: `/chat` module imports no write-apply path (R4-S8 → FR-WM2-17);
registry tools ⊆ `{survey, assess, field_states}`.

**S2 (prompt)** — update `KICKOFF_SYSTEM_PROMPT`/`POSTURE_BANNER` for propose-only drafting (R2-S2).

**Phased to requirements §F:** `POST /chat/reset` new-conversation (R4-S6); OTel `kickoff_span` nesting (R3-S8).

---

*Plan v0.1 — drafted against the live code. Feeds 7 discoveries into requirements §0 for v0.2.*
*Plan v0.2 — Post-CRP R1–R4. 16 plan suggestions accepted (14 folded into §7 step refinements, 2 phased);
none rejected. Pairs with requirements v0.3. Sequencing unchanged: download pillar first.*

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

> Triage R1–R4 (2026-06-26). All 16 plan suggestions accepted; folded into §7 (refinements anchored to
> each step). 2 phased to requirements §F. None rejected.

| ID | Suggestion | Source | Implementation / Validation Notes | Date |
|----|------------|--------|-----------------------------------|------|
| R1-S1 | `/chat` Host check + per-session rate limit | composer-2.5 | §7 S5/S6 | 2026-06-26 |
| R1-S2 | Separate `kickoff_chat` cookie | composer-2.5 | §7 S5/S6 (+ FR-WM2-5) | 2026-06-26 |
| R1-S3 | Bounded `propose` + no chat apply | composer-2.5 | §7 S8 (+ FR-WM2-7) | 2026-06-26 |
| R1-S4 | Mid-turn provider degradation, sanitized | composer-2.5 | §7 S5/S6 (+ FR-WM2-8) | 2026-06-26 |
| R1-S5 | Cumulative budget guard | composer-2.5 | §7 S5/S6 via SessionConfig (R2-S1) | 2026-06-26 |
| R1-S6 | Manifest-key encoding closure | composer-2.5 | §7 S2 (+ FR-WM2-2) | 2026-06-26 |
| R1-S7 | Zip byte ceiling (OQ-4) | composer-2.5 | §7 S2 (+ FR-WM2-3) | 2026-06-26 |
| R1-S8 | Manifest↔lists bijection test | composer-2.5 | §7 S1/S3 (+ FR-WM2-16) | 2026-06-26 |
| R2-S1 | Budget via `SessionConfig` (one source) | claude-sonnet-4-6 | §7 S5/S6 (+ FR-WM2-9) | 2026-06-26 |
| R2-S2 | System-prompt propose-only alignment | claude-sonnet-4-6 | §7 S2 (+ FR-WM2-6) | 2026-06-26 |
| R2-S3 | Per-session `asyncio.Lock` / `chat_busy` | claude-sonnet-4-6 | §7 S5/S6 (+ FR-WM2-5) | 2026-06-26 |
| R2-S4 | Preview/inspect mode gate on chat | claude-sonnet-4-6 | §7 S5/S6 (+ FR-WM2-8) | 2026-06-26 |
| R2-S5 | Inbound message length cap | claude-sonnet-4-6 | §7 S5/S6 (+ FR-WM2-5) | 2026-06-26 |
| R2-S6 | Triple-byte parity all keys × postures | claude-sonnet-4-6 | §7 S3 (+ FR-WM2-4) | 2026-06-26 |
| R2-S7 | Home-page Concierge CTA + templates link | claude-sonnet-4-6 | §7 S7 (+ FR-WM2-1) | 2026-06-26 |
| R2-S8 | Content-Type + charset per entry | claude-sonnet-4-6 | §7 S2 (+ FR-WM2-2) | 2026-06-26 |
| R3-S1 | `with_authoring` split (group + bundle filter) | gemini-3.1-pro | §7 S1/S2 (+ FR-WM2-4) | 2026-06-26 |
| R3-S2 | XSS-safe render/prefill | gemini-3.1-pro | §7 S7/S8 (+ FR-WM2-7) | 2026-06-26 |
| R3-S3 | Register events in `telemetry.py` | gemini-3.1-pro | §7 telemetry (+ FR-WM2-14) | 2026-06-26 |
| R3-S4 | Posture selector on index | gemini-3.1-pro | §7 S2 (+ FR-WM2-1) | 2026-06-26 |
| R3-S5 | Destroy chat state on expiry | gemini-3.1-pro | §7 S5/S6 (+ FR-WM2-5) | 2026-06-26 |
| R3-S6 | Zip-slip `dest` guard | gemini-3.1-pro | §7 S1/S3 (+ FR-WM2-16) | 2026-06-26 |
| R3-S7 | Stable `/chat` JSON contract | gemini-3.1-pro | §7 S5/S6 (+ FR-WM2-5) | 2026-06-26 |
| R3-S8 | OTel span nesting | gemini-3.1-pro | **PHASED** → reqs §F | 2026-06-26 |
| R4-S1 | `--agent` threaded end-to-end | gpt-5.5-extra-high | §7 S4 (+ FR-WM2-5) | 2026-06-26 |
| R4-S2 | Server-produced `propose` | gpt-5.5-extra-high | §7 S8 (+ FR-WM2-7) | 2026-06-26 |
| R4-S3 | `stop_reason` → typed `/chat` codes | gpt-5.5-extra-high | §7 S5/S6 (+ FR-WM2-8) | 2026-06-26 |
| R4-S4 | Shared `SessionConfig` factory + tool-call cap | gpt-5.5-extra-high | §7 S5/S6 (+ FR-WM2-15) | 2026-06-26 |
| R4-S5 | Bootstrap `kickoff_chat` on `GET /` | gpt-5.5-extra-high | §7 S5/S6 (+ FR-WM2-5) | 2026-06-26 |
| R4-S6 | "New conversation" reset | gpt-5.5-extra-high | **PHASED** → reqs §F | 2026-06-26 |
| R4-S7 | `posture_invalid` on tampered query | gpt-5.5-extra-high | §7 S2 (+ FR-WM2-2) | 2026-06-26 |
| R4-S8 | Static write-import guard | gpt-5.5-extra-high | §7 S9 (+ FR-WM2-17) | 2026-06-26 |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none) | — | — | All 16 plan suggestions accepted (2 phased); none re-litigated settled boundaries. | 2026-06-26 |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — composer-2.5 — 2026-06-26

- **Reviewer**: composer-2.5
- **Date**: 2026-06-26 19:35:00 UTC
- **Scope**: Welcome Mat 2.0 R1 — chat security/lifecycle (highest), download key-closure/parity (medium), OQ-4/OQ-5; grounded in live `web.py` Concierge gates (`_concierge_write_gate`, `_IntentStore`, `validate_friction`) and `chat.py` read floor.

**Focus-area answers (sponsor asks — triage later)**

**A — Propose-only write bridge (FR-WM2-7 / S8)**
- **Summary answer:** Partial — safe only if chat prefill is display-only and every write still passes the existing Concierge apply gates unchanged.
- **Rationale:** The shipped Concierge surface already enforces mode + loopback `Host` + CSRF + rate-limit + one-time `intent` + server-side `validate_friction`/`validate_posture` before `apply_concierge_plan` (`web.py:_concierge_write_gate`, `_IntentStore.consume`). A chat "prefill" that only copies bounded text into empty form fields and still requires the human to submit through `/concierge/*` does not bypass those gates — but an unstructured assistant reply parsed client-side could smuggle oversized or extra fields unless the prefill contract is bounded.
- **Assumptions / conditions:** No new server endpoint applies chat-origin values; intent/csrf tokens are never taken from chat output.
- **Suggested improvements:** Pin a bounded `propose` payload shape in S8; add S9 regression that `POST /chat` never calls `apply_concierge_plan` and the registry still exposes only read tools.

**A — `_ChatStore` session lifecycle (FR-WM2-5 / S5)**
- **Summary answer:** Partial — TTL + bounded eviction modeled on `_SessionStore` is necessary but not sufficient without a separate, server-issued chat session id.
- **Rationale:** `_SessionStore` issues `secrets.token_urlsafe(24)` CSRF tokens (`web.py:79-83`); chat history must not share that token or a guessable client id. Reusing the CSRF cookie for chat session identity would couple capture and chat lifecycles and widen fixation impact.
- **Assumptions / conditions:** Chat uses its own httponly+SameSite=strict cookie; `_ChatStore` keys only on server-issued ids.
- **Suggested improvements:** Document separate `kickoff_chat` cookie in S5; reject missing/expired chat session with typed `chat_session_expired`.

**A — Async `POST /chat` + rate limiting (S6)**
- **Summary answer:** Yes for async; no — the plan does not yet rate-limit the paid chat endpoint.
- **Rationale:** FastAPI supports mixed sync/async routes; uvicorn handles `async def` correctly. Capture POSTs are capped at `_RATE_MAX=20` per 60s (`web.py:38-40`), but S6 defines no analogous guard for `POST /chat`, which is the only LLM-spend surface.
- **Assumptions / conditions:** Chat rate limit is separate from capture/concierge write limits.
- **Suggested improvements:** Add per-session chat rate window in S5/S6; apply `_host_ok` to `POST /chat` like Concierge writes.

**A — Cost/turn caps (FR-WM2-9 / OQ-7)**
- **Summary answer:** Partial — per-session turn cap is necessary but not sufficient alone.
- **Rationale:** A single turn with a huge tool loop or long completion can blow past budget before the turn counter increments. `KickoffChat.cost_line` already exposes tokens/usd per turn; `_ChatStore` should accumulate them.
- **Assumptions / conditions:** Cap refusal is typed JSON, never a 500.
- **Suggested improvements:** Track cumulative `tokens`/`usd` in `_ChatStore`; refuse with `chat_budget_exceeded` at a documented ceiling.

**A — Graceful degradation + error containment (FR-WM2-8 / S6)**
- **Summary answer:** Partial — startup `agent=None` is covered; mid-conversation provider failures are not.
- **Rationale:** `cli_kickoff.py:chat_cmd` degrades at resolve time, but S6 only says "500-safe" without forbidding provider error text in responses. A timeout on turn 3 must not break `GET /`.
- **Assumptions / conditions:** Sanitized `chat_error` codes; overview render never awaits chat.
- **Suggested improvements:** Extend S6/S9 with typed provider/timeout/infra codes and a redaction rule (no API key substrings).

**C — OQ-4 (zip size ceiling)**
- **Summary answer:** Yes — add a hard uncompressed-bytes ceiling at zip build time.
- **Suggested improvements:** Resolve OQ-4 in S2 with typed 413 when manifest total exceeds cap (~2MB is ample for 11 templates).

**C — OQ-5 (authoring `*.md` downloadable)**
- **Summary answer:** Defer packaging for v1; link human guidance from the download index instead.
- **Rationale:** Authoring guidance lives under `docs/design/kickoff/templates/authoring/` and is not in `concierge_templates/`; adding them changes NR-6 scope slightly. FR-WM2-10 still authors `conventions.md` for completeness; download can stay the 11 packaged files until explicitly packaged.
- **Suggested improvements:** Close OQ-5 as "index link only in v1"; revisit packaging in a follow-on if users need offline guidance bytes.

**Executive summary**
- Chat prefill is safe only as a bounded, client-side bridge — the existing Concierge apply gates must remain the sole write path.
- `_ChatStore` needs its own httponly session cookie, not reuse of `kickoff_csrf`.
- `POST /chat` is the paid surface but has no rate limit, Host check, or cumulative spend guard in the plan yet.
- Mid-turn provider failures need explicit typed degradation beyond startup `agent=None`.
- Manifest-key download is structurally sound, but slash-containing keys need an encoding/normalization contract.
- OQ-4 should close with a zip byte ceiling; OQ-5 should defer authoring-md packaging for v1.

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-S1 | Security | high | Add a dedicated chat rate limit and loopback `Host` check on `POST /chat`, distinct from capture/concierge write limits. S6 defines `async def POST /chat` but does not apply `_host_ok` (`web.py:220-225`) or any per-session throttle — unlike `_concierge_write_gate` which enforces both Host and `sessions.rate_ok`. | Chat is the only paid, key-needing endpoint; without Host + rate limits it is the weakest loopback seam and the easiest budget drain. | S5 `_ChatStore` + S6 "Async chat endpoint" | Test forged `Host` → 403; burst >N chat POSTs/session → 429 typed `chat_rate_limited`; capture limits unchanged. |
| R1-S2 | Security | high | Issue a separate `kickoff_chat` httponly+SameSite=strict cookie for `_ChatStore`; never key chat history on `kickoff_csrf` or a client-supplied session id. S5 says "session-id → KickoffChat" modeled on `_SessionStore` but does not specify a distinct cookie/name or rejection of client-provided ids. | Coupling chat to the CSRF token increases fixation impact and lets a capture session double as a chat session; chat history is more sensitive than a one-shot CSRF. | S5 "Chat-session store" | Test: chat works with valid server cookie; missing/expired cookie → typed `chat_session_expired`; CSRF token alone cannot drive `/chat`. |
| R1-S3 | Security | high | Pin the propose-only bridge (S8) to a bounded machine-readable shape and forbid server-side apply from chat. Define an optional `propose` object in the `/chat` JSON response (`friction` triple + `posture` enum) with the same max lengths as `validate_friction`/`FRICTION_FIELD_MAX`; client may only populate empty Concierge form fields; submission still goes through unchanged `/concierge/*` with intent+csrf. Add explicit S9 assertion that `POST /chat` never imports `apply_concierge_plan`. | FR-WM2-7 "prefill" is only safe if it cannot substitute intent/csrf or bypass server validation; unstructured assistant prose parsed loosely is a smuggling vector for oversized friction text. | S8 "Propose-only bridge" + S9 tests | Regression: registry tools ⊆ `{survey, assess, field_states}`; `/chat` handler has no write import; prefill over max length is clipped/rejected client-side and still blocked server-side on apply. |
| R1-S4 | Risks | medium | Extend graceful degradation beyond startup `agent=None` to mid-conversation failures. S4/S6 cover missing agent at boot; add typed `chat_error` codes for provider 401/429/timeout/infra and **sanitize** messages (no API key substrings, no raw provider bodies). Overview `GET /` must not await chat. | FR-WM2-8 only addresses resolve-time failure; a user with a valid key can still hit a mid-session 401/timeout that becomes an unhandled 500 without an explicit contract. | S6 "500-safe" bullet + S9 tests | Simulate provider timeout → `/chat` returns 200/503 JSON `{code: chat_provider_timeout}`; `GET /` still 200; response body grep asserts no `sk-`/`ANTHROPIC` fragments. |
| R1-S5 | Ops | medium | Track cumulative tokens/usd in `_ChatStore` and refuse with typed `chat_budget_exceeded` in addition to the per-session turn cap (OQ-7). S5 mentions turn cap only; `KickoffChat.cost_line` already exposes per-turn `tokens` and `cost≈$` — accumulate after each `ask`. | One expensive turn can exceed a reasonable budget before turn cap trips; turn count alone is a weak cost guard on a paid surface. | S5 `_ChatStore` + FR-WM2-9 cross-ref in S6 return shape | Test: after cumulative usd crosses ceiling, next `/chat` returns typed refusal (not 500) while download/overview still work. |
| R1-S6 | Security | medium | Harden manifest-key lookup against encoding tricks. S2 uses `GET /templates/file/{key}` with slugs like `package/kickoff-intro`; specify `{key:path}` routing or flat keys, `urllib.parse.unquote` once, exact match against manifest keys only, and reject `..`, `%2e%2e`, leading `/`, and unknown keys with typed 404. | Key-only lookup is structurally right (NR-3), but slash/dot encoding in the path parameter is the remaining traversal surface if normalization is loose. | S2 second bullet "`GET /templates/file/{key}`" | Tests: keys with slashes download correctly; `..`, `%2e%2e`, and `authoring/../../etc/passwd` → 404; no bytes served outside manifest. |
| R1-S7 | Ops | low | Resolve OQ-4 in S2: cap in-memory zip build by total uncompressed bytes (suggest ≤2MB for the 11-file set) and return typed 413 `bundle_too_large` if exceeded. | Even a bounded template set should fail closed against accidental manifest bloat or future row mistakes before allocating an unbounded `BytesIO`. | S2 "`GET /templates/bundle.zip`" | Test: artificially inflate a template in a fixture manifest over cap → 413; normal bundle < cap → 200 with correct `Content-Type`. |
| R1-S8 | Validation | medium | Make the one-inventory guard concrete in S3/S11: a test asserts `kickoff_template_manifest()` keys biject with `_KICKOFF_FILES + _AUTHORING_FILES` template rels **and** that `build_instantiate_plan(...).writes[].path` equals the manifest `dest` set; adding a row to one list without the accessor fails CI. | FR-WM2-4/11/12 claim no drift, but S3 only lists parity informally; without a bijection test the manifest can silently diverge. | S1 manifest accessor + S3 tests + S11 completeness | CI test fails if a template rel is added to `_KICKOFF_FILES` without manifest row; passes when sets match. |

**Endorsements** (prior untriaged suggestions this reviewer agrees with): none — first round.

---

## Requirements Coverage Matrix — R1

Analysis only (not triage). Maps each requirement ID → plan step(s) → coverage.

| Requirement | Plan Step(s) | Coverage | Gaps |
| ---- | ---- | ---- | ---- |
| FR-WM2-1 (download surface) | S2 `GET /templates`, overview link | Partial | Overview/templates nav not specified for package-less first-run CTA (download is independent of instantiate). |
| FR-WM2-2 (individual download) | S1, S2 | Partial | Key normalization/encoding contract underspecified (R1-S6). |
| FR-WM2-3 (bundle download) | S2 bundle route | Partial | OQ-4 size ceiling not closed (R1-S7). |
| FR-WM2-4 (one inventory) | S1, S3, S11 | Partial | Bijection test not explicit (R1-S8). |
| FR-WM2-5 (chat on home page) | S4–S7, S5 `_ChatStore` | Partial | Separate chat session cookie not specified (R1-S2). |
| FR-WM2-6 (read-only floor) | S6, S9 | Full | Registry floor already exists in `chat.py`; S9 preserves it. |
| FR-WM2-7 (propose-only bridge) | S8 | Partial | Bounded prefill contract + no server apply from chat not specified (R1-S3). |
| FR-WM2-8 (graceful degradation) | S4, S6, S7 | Partial | Mid-turn provider failures not covered (R1-S4). |
| FR-WM2-9 (cost visibility) | S6 return shape, S5 turn cap | Partial | Cumulative spend ceiling missing (R1-S5). |
| FR-WM2-10 (conventions.md) | S10 | Full | — |
| FR-WM2-11 (manifest) | S1, S11 | Partial | Depends on R1-S8 bijection guard. |
| FR-WM2-12 (verify completeness) | S3, S11 | Partial | Same as R1-S8. |
| FR-WM2-13 (MCP unchanged) | (none — inherited) | Full | Settled boundary. |
| FR-WM2-14 (observability) | S2, S7 telemetry bullets | Partial | Chat rate-limit/budget refusal events not named. |
| FR-WM2-15 (parity) | S6/S9 vs CLI `kickoff chat` | Full | Shared registry construction. |
| NR-1..NR-6 | S8, S2, S12 | Full | OQ-5 defer aligns with NR-6 scope. |

#### Review Round R2 — claude-sonnet-4-6 — 2026-06-26

- **Reviewer**: claude-sonnet-4-6
- **Date**: 2026-06-26 20:10:00 UTC
- **Scope**: R2 gap-hunting after R1 — platform leverage (`SessionConfig`), prompt/UX alignment for propose-only, concurrency/mode gates, download parity depth, telemetry completeness.

**Executive summary**
- `_ChatStore` should delegate turn/token/cost caps to existing `AgenticSession` `SessionConfig` rather than reimplementing budget logic — a low-effort reuse win R1's cumulative-cap suggestion missed.
- `KICKOFF_SYSTEM_PROMPT` currently tells the model it *cannot* log friction, which conflicts with FR-WM2-7's propose/prefill bridge unless the prompt is updated.
- Parallel `POST /chat` requests against one session can corrupt `AgenticSession` history unless serialized per session.
- Chat is not gated by feature `mode` (preview/inspect still spends tokens) unlike capture/concierge writes.
- FR-WM2-4 posture parity should be tested for every manifest file in bundle + single download + instantiate, not only `conventions.yaml`.
- Home-page discoverability: S7 should wire templates link and a Concierge apply CTA into `_render_overview` using existing `build_concierge_view.next_action`.

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R2-S1 | Architecture | medium | Wire `_ChatStore` budget/turn limits through existing `AgenticSession` `SessionConfig` (`agents/agentic.py:232-239`: `max_turns`, `max_total_tokens`, `max_cost_usd`) when constructing `new_kickoff_chat`, instead of only counting turns externally. S5 describes a per-session turn cap in `_ChatStore` but does not mention the loop already enforces budgets and returns `stop_reason` ∈ `{budget, max_turns}`. | R1-S5 proposed cumulative tracking in `_ChatStore`; the agentic layer already accumulates `total_tokens`/`total_cost_usd` and stops on budget — duplicating counters risks drift. This is the Mottainai quick win: one config object, one source of truth. | S5 `_ChatStore` + S6 return shape (`cost` block) | Test: set `SessionConfig(max_cost_usd=0.01)` → `/chat` returns typed `chat_budget_exceeded` when `AgenticResult.stop_reason == "budget"`; no duplicate accounting in store. |
| R2-S2 | Architecture | medium | Add an explicit S8 sub-step to update `KICKOFF_SYSTEM_PROMPT` / `POSTURE_BANNER` for propose-only drafting. Today `chat.py:47-50` says the assistant *"CANNOT … log friction"* and must direct users to the kickoff UI/CLI — but FR-WM2-7 wants the web chat to *suggest* friction/instantiate drafts for Concierge prefill. Without a prompt delta, the model will refuse to draft or will hallucinate that it applied. | Prompt/registry mismatch is a functional gap, not just security — users won't get the propose-only value FR-WM2-7 promises. | S8 "Propose-only bridge" + cross-ref `chat.py` | Test: fixture agent asked to draft friction receives system prompt containing "suggest / prefill" and "human applies via Concierge"; regression that prompt still forbids claiming files were written. |
| R2-S3 | Risks | high | Serialize `POST /chat` per chat session with an `asyncio.Lock` (or equivalent) held for the duration of `await chat.ask(message)`. S6 defines async handler but not concurrency; two rapid parallel POSTs sharing one `_ChatStore` entry can interleave `AgenticSession.send` and corrupt message history or double-charge. | Stateful paid endpoint + async ≠ thread-safe by default; this is a second-order bug R1's rate limit does not prevent (two concurrent requests both under limit). | S5 `_ChatStore` entry shape + S6 endpoint | Test: fire two concurrent `/chat` POSTs with same session cookie; assert exactly one runs at a time (second waits or gets `chat_busy`), history remains coherent. |
| R2-S4 | Security | medium | Gate chat by feature `mode` like capture/concierge writes: when `mode in ("preview", "inspect")`, render disabled chat panel and return typed `preview_only` on `POST /chat`. S4 threads `mode` into `build_kickoff_app` and capture/concierge refuse applies in preview (`web.py:396-401`), but S6/S7 do not mention chat — a preview-mode serve would still spend LLM tokens. | Preview/inspect modes are documented as read-only; the paid chat surface should respect the same least-privilege story. | S6 + S7 overview render | Test: `build_kickoff_app(..., mode="preview")` → `/chat` returns 403 `preview_only`; panel shows disabled state. |
| R2-S5 | Security | medium | Cap inbound user message length on `POST /chat` before calling the agent (e.g. ≤4096 chars, typed `message_too_long`). S6 accepts `message` with no bound; oversized paste is a cheap token-burn / latency attack even with rate limits (R1-S1). | Complements rate/cost caps — blocks single-request payload bombs. | S6 "Async chat endpoint" | Test: 10k-char message → 400 `message_too_long` without provider call (mock agent not invoked). |
| R2-S6 | Validation | medium | Extend S3 with a **triple-byte parity** test across all manifest entries: for posture P, bytes from `GET /templates/file/{key}?posture=P`, the corresponding zip entry in `GET /templates/bundle.zip?posture=P`, and `build_instantiate_plan(..., posture=P)` content for that dest must be identical. FR-WM2-4 only exemplifies `conventions.yaml`; R1-S8 covers set bijection but not per-file byte equality across all three consumers. | One-inventory/no-drift (P-E) fails in production if any non-conventions template diverges between download paths. | S3 tests | Parametrize over manifest keys × `{prototype, production}`; assert three-way byte equality. |
| R2-S7 | Ops | low | In S7 `_render_overview`, add the templates nav link (S2) **and** a Concierge CTA driven by `build_concierge_view(root)["next_action"]` (already shipped for `/concierge`). When `instantiate_offer.needed`, home page should surface "Create kickoff package" linking to `/concierge`, not only the generic Concierge link at `web.py:159`. | Low-effort end-user value: reuses existing view-model CTA logic instead of duplicating package-missing detection on the home page. | S7 "Overview render" + S2 overview link | Web test: project without inputs shows `next_action.title` CTA on `/` pointing to `/concierge`. |
| R2-S8 | Ops | low | Extend S2/S3 to set explicit `Content-Type` + `charset=utf-8` per manifest entry (`.yaml` → `text/yaml`, `.md` → `text/markdown`) and `Content-Disposition` filename from manifest `dest` basename only. Plan mentions media_type elliptically but not charset; wrong types break offline editing for users who "download to read." | Deterministic polish with high end-user value for the lowest-risk pillar. | S2 `GET /templates/file/{key}` response headers | Test: YAML entry returns `text/yaml`; MD returns `text/markdown`; filename matches dest basename. |

**Endorsements** (prior untriaged suggestions this reviewer agrees with):
- R1-S1: Chat needs its own Host check and rate limit — the paid endpoint is otherwise the weakest seam.
- R1-S2: Separate `kickoff_chat` cookie is required; CSRF must not double as chat session id.
- R1-S3: Bounded machine-readable `propose` payload is the right way to implement FR-WM2-7 safely.
- R1-S4: Mid-turn provider failures need typed degradation, not just startup `agent=None`.
- R1-S6: Manifest key normalization must be specified for slash-containing keys.
- R1-F1: FR-WM2-7 needs explicit acceptance that prefill cannot supply csrf/intent and is re-validated on apply.

---

## Requirements Coverage Matrix — R2

Analysis only (not triage). Highlights gaps addressed by R2 suggestions; assumes R1 gaps remain open until triaged.

| Requirement | Plan Step(s) | Coverage | Gaps |
| ---- | ---- | ---- | ---- |
| FR-WM2-1 (download surface) | S2, S7 | Partial | Home-page templates link + CTA wiring underspecified (R2-S7). |
| FR-WM2-2 (individual download) | S2 | Partial | Content-Type/charset not specified (R2-S8). |
| FR-WM2-3 (bundle download) | S2 | Partial | Triple-byte parity with single+instantiate not required (R2-S6). |
| FR-WM2-4 (one inventory) | S1, S3 | Partial | Per-file byte parity across three consumers missing (R2-S6). |
| FR-WM2-5 (chat on home page) | S4–S7 | Partial | SessionConfig reuse + message length cap + concurrency not specified (R2-S1, R2-S3, R2-S5). |
| FR-WM2-6 (read-only floor) | S6, S9 | Partial | System prompt conflicts with propose-only drafting (R2-S2). |
| FR-WM2-7 (propose-only bridge) | S8 | Partial | Prompt alignment + home Concierge CTA (R2-S2, R2-S7). |
| FR-WM2-8 (graceful degradation) | S4, S6, S7 | Partial | Preview/inspect mode chat gate missing (R2-S4). |
| FR-WM2-9 (cost visibility) | S5, S6 | Partial | Should leverage AgenticSession budgets (R2-S1). |
| FR-WM2-10–12 | S10, S11 | Full | — |
| FR-WM2-13 (MCP unchanged) | — | Full | Settled. |
| FR-WM2-14 (observability) | S2, S7 | Partial | `chat_busy`, `message_too_long`, `preview_only` events not named (R2-F4). |
| FR-WM2-15 (parity) | S6/S9 | Full | Registry shared with CLI. |

#### Review Round R3 — gemini-3.1-pro — 2026-06-26

- **Reviewer**: gemini-3.1-pro
- **Date**: 2026-06-26 21:05:00 UTC
- **Scope**: R3 adversarial / cross-cutting — `with_authoring` inventory drift, chat XSS + prefill DOM safety, telemetry module reuse, session memory lifecycle, stable `/chat` JSON contract.

**Focus-area deltas (second-order — prior rounds covered first-order)**

**A — Propose-only bridge:** R1-S3's bounded `propose` object is necessary but not sufficient for web safety — if S7/S8 render assistant `text` or inject `propose` values via `innerHTML`, model output becomes an XSS vector even with a read-only registry.
**B — One inventory:** `build_instantiate_plan(..., with_authoring=False)` writes only `_KICKOFF_FILES` (6 package files) by default (`writes.py:85-91`), while S1 derives the manifest from `_KICKOFF_FILES + _AUTHORING_FILES` (11). P-E "no drift" needs an explicit rule for this parameterization, not only posture parity.
**A — `_ChatStore` lifecycle:** Idle eviction must destroy the in-memory `AgenticSession` message list, not only drop the map entry — otherwise conversation text lingers until process exit.

**Executive summary**
- Default instantiate ships 6 package files; download manifest always lists 11 — document `with_authoring` grouping and optional bundle filter or users will assume byte parity with default instantiate incorrectly.
- Chat panel HTML must treat assistant output as untrusted (`_esc()` server-side or `textContent` client-side); prefill must never use `innerHTML`.
- WM2 funnel events belong in `telemetry.py` `FUNNEL_EVENTS` + an attribute allowlist — not ad-hoc `emit` strings scattered in `web.py`.
- `_ChatStore` eviction should explicitly wipe `KickoffChat.session.messages` on idle expiry (memory-only, never disk).
- `GET /templates` needs a posture selector (and optional `with_authoring` toggle) so downloaded `conventions.yaml` matches user intent without manual query-string editing.
- Pin a stable `POST /chat` JSON schema (`text`, `cost`, optional `propose`, typed `code`) for the inline panel's fetch client.
- Zip build should assert every manifest `dest` is a relative path with no `..` segments (zip-slip guard even with closed keys).
- Parent OTel: wrap `/chat` in existing `kickoff_span` / let `AgenticSession` child spans nest under `kickoff.session`.

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R3-S1 | Data | high | Resolve the **`with_authoring` inventory split** in S1/S2. `kickoff_template_manifest()` derives from `_KICKOFF_FILES + _AUTHORING_FILES`, but `build_instantiate_plan` defaults to `with_authoring=False` and only writes the 6 package files (`concierge/writes.py:85-91`). S1 must tag each manifest row `group: package \| authoring` and S2 must document whether the bundle is always 11 files or accepts `?with_authoring=` to mirror instantiate's default (6). Without this, FR-WM2-4 "one inventory" is misread as "download always equals default instantiate bytes." | Real drift vector R1-S8 bijection misses — set equality holds, but **parameterized subset** does not unless documented. | S1 manifest accessor + S2 bundle route + S3 parity tests | Test: default bundle with `with_authoring=false` contains exactly `_KICKOFF_FILES` dests; `true` adds `_AUTHORING_FILES`; bytes match `build_instantiate_plan` at same flags. |
| R3-S2 | Security | high | Require **HTML escaping** for all chat output in S7 and **DOM-safe prefill** in S8. `_render_overview` already uses `_esc()` for every dynamic string (`web.py:123-130`); S7 does not say assistant `text` is escaped. S8 "prefill button" must set form field values via `textContent`/`value` assignment, never `innerHTML`. Model text can contain `<script>` or event handlers. | Read-only registry does not prevent XSS when assistant prose is rendered into HTML — a second-order gap after R1-S3's bounded `propose` object. | S7 overview chat panel + S8 prefill bridge | Test: fixture response with `<img onerror=…>` renders as literal text; prefill populates textarea without executing markup. |
| R3-S3 | Ops | medium | Register WM2 events in **`telemetry.py`** instead of inventing parallel emit paths. `FUNNEL_EVENTS` today ends at Concierge events (`telemetry.py:49-60`); FR-WM2-14 names `template_downloaded`, `chat_turn`, etc. but they are not in the module. Extend `FUNNEL_EVENTS`, add a `WM2_EVENT_ATTR_ALLOWLIST` mirroring `CONCIERGE_EVENT_ATTR_ALLOWLIST` (`telemetry.py:64-66`), and call `emit()` from S2/S6/S7. | Mottainai — the funnel sink + `record_events()` test harness already exists; ad-hoc event strings in `web.py` won't be CI-guarded. | S2/S6/S7 telemetry bullets + `telemetry.py` | `record_events()` captures each new event name; attributes ⊆ allowlist; no `message` or raw `project_root` path keys. |
| R3-S4 | Interfaces | medium | Add a **posture selector** (and optional `with_authoring` toggle if R3-S1 closes that way) to `GET /templates` HTML. S2 allows `?posture=` on file/bundle routes but the index does not expose it — users downloading `conventions.yaml` without the query get the default only and may not discover production substitution (`writes.py:_POSTURE_CONVENTIONS`). | High end-user value, low implementation cost — purely presentational on an existing query param. | S2 "`GET /templates`" HTML list | Web test: index form/link sets `?posture=production` on download hrefs; downloaded conventions bytes match production placeholder. |
| R3-S5 | Security | medium | On `_ChatStore` idle expiry or eviction, **destroy conversation state** explicitly: drop the `KickoffChat` entry and clear `AgenticSession.messages` (or discard the session object). S5 copies `_SessionStore` TTL/eviction but CSRF tokens are stateless secrets; chat entries hold full multi-turn history in RAM. | Privacy + memory bound — expired sessions should not retain user/assistant text until process exit; complements R1-S2 separate cookie. | S5 `_ChatStore` eviction policy | Test: advance clock past `_IDLE_S` → next `/chat` gets `chat_session_expired`; prior messages unreachable; `len(store)` bounded after many sessions. |
| R3-S6 | Validation | low | In S3 zip build, assert every manifest **`dest` is a safe relative path**: no leading `/`, no `..` segments, no backslashes. Keys are closed (R1-S6) but `dest` values are still written into the archive path — a future manifest typo could zip-slip. | Defensive guard on the third delivery shape (bundle) R2-S6 triple-parity assumes is safe. | S3 tests + S1 manifest row validation | Test: fixture manifest row with `dest="../../etc/passwd"` fails manifest validation at accessor time, not at serve time. |
| R3-S7 | Interfaces | medium | Document a **stable `POST /chat` JSON contract** in S6 for the inline panel's fetch client: `{ok, text?, cost?: {turns, tokens, usd}, propose?: {friction?, posture?}, code?, message?}`. S6 lists return fields informally; without a schema, S7 client and S8 prefill will diverge. | Context-correctness at the web↔chat boundary — the home page is the only consumer. | S6 "Async chat endpoint" + S7 panel | Contract test: JSON schema or snapshot test on success, budget refusal, and `chat_error` paths. |
| R3-S8 | Ops | low | Nest chat turns under existing kickoff OTel: wrap `POST /chat` handler in `kickoff_span` (`telemetry.py`) and rely on `AgenticSession`'s built-in `agentic.session` / `agentic.turn` spans (`agentic_otel.py:9-15`). S6/S7 mention funnel events but not trace hierarchy. | Free observability — agentic spans already emit `stop_reason`, tokens, cost; parent kickoff span links chat to the Welcome Mat session funnel. | S6 endpoint + cross-ref `agentic_otel.py` | Trace fixture: `/chat` produces `kickoff.session` parent with `agentic.session` child when OTel enabled. |

**Endorsements** (prior untriaged suggestions this reviewer agrees with):
- R1-S1: `POST /chat` needs Host check + rate limit — cross-site loopback abuse of the paid surface.
- R1-S5 / R2-S1: Budget caps should use `SessionConfig` totals, not duplicate counters in `_ChatStore`.
- R2-S3: Per-session `asyncio.Lock` on `/chat` — rate limits do not serialize concurrent state mutation.
- R2-S6: Triple-byte parity across single download, bundle, and instantiate for every manifest key.
- R1-F5: FR-WM2-2 encoding edge cases must be acceptance-testable.

**Disagreements** (untriaged prior items this reviewer would reject or defer):
- None — R1/R2 items are directionally sound; R3 extends rather than contradicts.

---

## Requirements Coverage Matrix — R3

Analysis only (not triage). Second-order gaps and cross-cutting interactions after R1–R2.

| Requirement | Plan Step(s) | Coverage | Gaps |
| ---- | ---- | ---- | ---- |
| FR-WM2-1 (download surface) | S2, S7 | Partial | Posture/`with_authoring` controls on index missing (R3-S4, R3-S1). |
| FR-WM2-2 (individual download) | S2 | Partial | Depends on index exposing posture (R3-S4). |
| FR-WM2-3 (bundle download) | S2 | Partial | `with_authoring` subset + zip-slip dest guard (R3-S1, R3-S6). |
| FR-WM2-4 (one inventory) | S1, S3 | Partial | `with_authoring` parameterization undocumented (R3-S1). |
| FR-WM2-5 (chat on home page) | S4–S7 | Partial | JSON contract + session memory wipe on expiry (R3-S7, R3-S5). |
| FR-WM2-6 (read-only floor) | S6, S9 | Full | Registry floor unchanged. |
| FR-WM2-7 (propose-only bridge) | S8 | Partial | DOM-safe prefill + escaped render (R3-S2). |
| FR-WM2-8 (graceful degradation) | S4, S6, S7 | Partial | Unchanged from R2 — preview gate still open. |
| FR-WM2-9 (cost visibility) | S5, S6 | Partial | `cost` block should match R3-S7 schema. |
| FR-WM2-10–12 | S10, S11 | Full | — |
| FR-WM2-13 | — | Full | Settled. |
| FR-WM2-14 (observability) | S2, S6, S7 | Partial | Events must land in `telemetry.py` (R3-S3); OTel nesting (R3-S8). |
| FR-WM2-15 (parity) | S6/S9 | Full | — |

#### Review Round R4 — gpt-5.5-extra-high — 2026-06-26

- **Reviewer**: gpt-5.5-extra-high
- **Date**: 2026-06-26 22:15:00 UTC
- **Scope**: R4 late-phase gap-hunt — CLI/serve agent threading, propose production contract, agentic stop_reason mapping, shared SessionConfig, session bootstrap/reset, download posture validation.

**Executive summary**
- S4 names `--agent` on `serve`/`start` but `serve_kickoff` (`serve.py:214-239`) and `cli_kickoff.py start` (`:216`) do not pass an agent today — the seam must be explicit or chat never boots on the web path.
- R1-S3's bounded `propose` object lacks a **producer**: S6/S8 must define server-side extraction/validation from `AgenticResult`, not client parsing of free-form assistant prose.
- `AgenticSession` can stop with `context_overflow` / `repeated_calls` / `max_turns` (`agentic.py:248-249`) — S6 must map these to typed `/chat` codes, not only provider exceptions (R1-S4).
- Web and CLI should share one `SessionConfig` factory (incl. `max_tool_calls_per_turn`) so per-turn tool-loop burn is capped consistently (extends R2-S1).
- Issue `kickoff_chat` on `GET /` when `agent is not None` (parallel CSRF issuance) so the first POST is not session-bootstrap + LLM spend in one step.
- End-user quick win: "New conversation" resets `_ChatStore` entry without restarting the server.
- Download routes must reject unknown `posture` with typed `posture_invalid`, reusing `VALID_POSTURES`.
- S9 should add a static import guard that the `/chat` handler path never imports `apply_concierge_plan` / write apply modules.

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R4-S1 | Architecture | high | Thread **`--agent` end-to-end** in S4: `cli_kickoff.py start` → `serve_kickoff(..., agent=...)` → `build_kickoff_app(..., agent=...)`. Today `serve_kickoff` (`serve.py:214-239`) accepts only `project_root/mode/theme/port/config` and always calls `build_kickoff_app` without an agent; `start` (`cli_kickoff.py:216`) never forwards a flag. S4 resolves OQ-3 but omits the two call sites that actually launch the server. | Without this wiring, FR-WM2-5/8 are dead on the primary `kickoff start` path — chat stays `agent=None` forever despite the plan text. | S4 first paragraph + cross-ref `serve.py` + `cli_kickoff.py start` | Integration test: `start --agent mock:…` (or fixture agent) → `GET /` shows enabled chat panel, not degradation. |
| R4-S2 | Interfaces | high | Define **how `propose` is produced** in S6/S8. R1-S3 requires a bounded `propose` object in the `/chat` JSON response, but S6 only returns `{text, cost}` and S8 says the assistant may suggest drafts in prose. Add a server-side post-pass on `AgenticResult` (structured tool output or a constrained JSON slice — not regex on arbitrary prose) that emits `propose.friction` / `propose.posture` only when values pass `validate_friction` / `VALID_POSTURES`; otherwise omit `propose`. Forbid client-side parsing of assistant `text` as the sole prefill source. | Without a producer contract, implementers will either skip prefill (poor UX) or parse HTML/markdown loosely (R3-S2 XSS + R1-S3 smuggling). | S6 return shape + S8 "Propose-only bridge" | Test: fixture result with valid friction triple → `propose` present; oversize field → `propose` absent; client never reads `text` for hidden fields. |
| R4-S3 | Risks | medium | Map **`AgenticResult.stop_reason`** to typed `/chat` responses in S6. R1-S4 covers provider 401/timeout; the agentic layer also stops on `context_overflow`, `repeated_calls`, `max_turns`, `budget`, `stream_error` (`agents/agentic.py:248-249`). Return `{ok: false, code: chat_<stop_reason>}` with sanitized `message` and still 200/503 — never 500 `/`. Include `stop_reason` in the `cost` block on success for FR-WM2-9 honesty. | Mid-turn failures are not only HTTP provider errors — a tool loop can exhaust context or repeat identical calls without any provider fault. | S6 "500-safe" + S9 tests | Force `SessionConfig(max_turns=1)` or repeated-call fixture → typed `chat_max_turns` / `chat_repeated_calls`; overview still 200. |
| R4-S4 | Architecture | medium | Introduce a shared **`kickoff_chat_session_config()`** (or reuse from `chat.py`) consumed by both `new_kickoff_chat` call sites — web `_ChatStore` and CLI `chat_cmd`. Set `max_turns`, `max_cost_usd`, `max_total_tokens`, and **`max_tool_calls_per_turn`** (`agentic.py:236`) from one documented default table. R2-S1 says wire `SessionConfig` but does not cap tool calls per user message — one `/chat` POST can fan out 16 tool calls per turn. | Mottainai + FR-WM2-15 parity: CLI and web must share the same loop-safety envelope, not divergent caps. | S5 `_ChatStore` lazy `new_kickoff_chat` + S4 CLI cross-ref | Test: web and CLI configs equal; exceeding `max_tool_calls_per_turn` yields typed refusal with `stop_reason=repeated_calls` or turn cap. |
| R4-S5 | Security | medium | **Bootstrap `kickoff_chat` on `GET /`** when `agent is not None`: issue the httponly+SameSite=strict session cookie alongside `kickoff_csrf` (`web.py:354-356` pattern). R1-S2 requires a separate cookie but does not say when it is minted; deferring issuance to the first `POST /chat` couples session creation with the first paid call and complicates rate-limit accounting. | Session bootstrap should be `$0` and precede any provider spend; mirrors CSRF issuance on every overview load. | S5 + S7 overview route | Test: `GET /` sets `kickoff_chat` cookie; first `POST /chat` does not set a new session id unless expired; missing cookie before fix → `chat_session_expired`. |
| R4-S6 | Ops | low | Add a **"New conversation"** affordance in S7/S6: `POST /chat/reset` (or `DELETE`) clears the current `_ChatStore` entry, mints a fresh `kickoff_chat` cookie, and returns `{ok: true}` without calling the provider. Complements R3-S5 memory wipe with an explicit user-triggered reset. | End-user value for mistaken threads; avoids asking users to restart the server or clear cookies manually. | S6 new route + S7 panel button | Test: multi-turn history → reset → next `/chat` has empty context; prior turns unreachable. |
| R4-S7 | Validation | low | Validate **`posture` query params** on S2 download routes against `VALID_POSTURES` (`writes.py:28`); unknown value → typed 400 `posture_invalid` (not silent default, not 500). R3-S4 adds a posture selector UI — the server must fail closed on tampered query strings. | UI controls do not remove direct URL tampering; invalid posture should be testable and explicit. | S2 file + bundle routes | `?posture=evil` → 400 `posture_invalid`; omitted → `prototype` default. |
| R4-S8 | Validation | medium | Extend S9 with a **static write-import guard** for the chat surface: assert the module defining `POST /chat` does not import `apply_concierge_plan`, `apply_write_plan`, or `concierge/writes` apply paths (AST or grep test). R1-S3 requires "loop never posts" — an import regression is the earliest CI signal. | Convention-only guarantees erode under refactor; Concierge mode already treats write gates as testable infrastructure. | S9 tests | CI fails if chat handler imports apply modules; passes on read-only imports only. |

**Endorsements** (prior untriaged suggestions this reviewer agrees with):
- R1-S3: Bounded server response `propose` object — R4-S2 supplies the missing producer half.
- R1-S4: Mid-turn failures need typed degradation — R4-S3 extends to agentic `stop_reason` values.
- R2-S1: Wire `SessionConfig` budgets — R4-S4 adds shared factory + tool-call cap.
- R2-S4: Preview/inspect must disable paid chat.
- R3-S1: `with_authoring` parameterization must be explicit in manifest/bundle.
- R3-S3: WM2 events belong in `telemetry.py` `FUNNEL_EVENTS`.
- R1-S7 / R1-F6: Close OQ-4 with zip byte ceiling.

**Disagreements**: none.

---

## Requirements Coverage Matrix — R4

Analysis only (not triage). Late-round interactions and implementation seams.

| Requirement | Plan Step(s) | Coverage | Gaps |
| ---- | ---- | ---- | ---- |
| FR-WM2-1 (download surface) | S2, S7 | Partial | Posture validation on tampered queries (R4-S7); index UI still R3-S4. |
| FR-WM2-2 (individual download) | S2 | Partial | Invalid posture handling (R4-S7). |
| FR-WM2-3 (bundle download) | S2 | Partial | Same posture guard (R4-S7). |
| FR-WM2-4 (one inventory) | S1, S3 | Partial | `with_authoring` still R3-S1. |
| FR-WM2-5 (chat on home page) | S4–S7 | Partial | Agent CLI threading (R4-S1); cookie bootstrap (R4-S5); reset affordance (R4-S6). |
| FR-WM2-6 (read-only floor) | S6, S9 | Partial | Static write-import guard (R4-S8). |
| FR-WM2-7 (propose-only bridge) | S8 | Partial | Server-side propose producer unspecified (R4-S2). |
| FR-WM2-8 (graceful degradation) | S4, S6 | Partial | Agentic `stop_reason` mapping (R4-S3); preview gate still R2-S4. |
| FR-WM2-9 (cost visibility) | S5, S6 | Partial | Shared SessionConfig + tool-call cap (R4-S4); expose `stop_reason` in cost block. |
| FR-WM2-10–12 | S10, S11 | Partial | OQ-5 index links still R1-F7/R3-F4. |
| FR-WM2-13 | — | Full | Settled. |
| FR-WM2-14 (observability) | S2, S6, S7 | Partial | `stop_reason` attribute on `chat_turn` not named (R4-S3). |
| FR-WM2-15 (parity) | S4, S6, S9 | Partial | Shared SessionConfig factory across CLI/web (R4-S4). |
