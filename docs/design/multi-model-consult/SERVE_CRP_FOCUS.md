# CRP Focus — Consultation Serve Mode

**Least-reviewed target:** Both `WEB_UI_SERVE_REQUIREMENTS.md` (v0.3) and `WEB_UI_SERVE_PLAN.md`
(v1.0) are brand-new — first external review. This increment turns the read-only web view into an
**interactive local write surface that spends real money on LLM calls**, so weight scrutiny on the
security model above all else.

## Settled — do NOT relitigate
- Serve mode is **opt-in**; the static offline view (WEB_UI) stays the default and keeps its read-only
  guarantee unchanged.
- Executor is the **existing consultation core** (`engine.follow_up`), awaited directly (the `asyncio.run`
  facade cannot nest in the server loop). No logic fork.
- Own module `consultation/serve.py`; do **not** extend the workflow server (`server/app.py`).
- Follow-ups only (no browser `run`, no roster change); text-only (no browser image upload) in v1.
- No streaming in v1.

## Where review input is most valuable (security model — the crux)
1. **Loopback + bind safety (FR-SRV-4a).** Is "refuse non-`127.0.0.1` bind" sufficient? IPv6 `::1`?
   `localhost` resolving to something unexpected? Ephemeral-port disclosure?
2. **Token model (FR-SRV-4b, OQ-1).** ≥128-bit per-run token on every request; header vs cookie;
   constant-time compare; token-in-URL leakage (browser history, Referer, Loki). Is GET-page-token-in-URL
   an acceptable transport, or should the page bootstrap the token differently?
3. **Origin/Host allowlist + DNS-rebinding (FR-SRV-4c).** Does Host + Origin checking actually stop
   DNS-rebinding against a loopback server? Any bypass (null Origin, missing Origin, non-browser client)?
4. **Cost guard (FR-SRV-5).** Turn cap + per-Send user action — enough to bound runaway spend? Retry/replay
   of a captured POST? Should there be a hard per-server spend ceiling, not just a turn count?
5. **Concurrency/lock (FR-SRV-6).** In-process `asyncio.Lock` + 409 — does it fully close the
   lost-update/interleave window given the store's atomic write, or is a cross-process guard also needed?
6. **Degradation (FR-SRV-8).** Soft `starlette/uvicorn` dependency → fall back to static; any failure mode
   that could leave the server half-up or the token exposed?
