# M-pilot Runbook — Panel-Processing Pipeline end-to-end (FR-P1)

**Goal (FR-P1):** validate the full Increment-3 pipeline on the **household** *through apply-preview*
(no real write), exercise apply's **actual write only on a throwaway project**, and record a **verdict**.

Pipeline: **run → triage → extract→stage → serialize → negotiate → apply(preview→ratify)**.

> **Two ways to exercise "apply".** The **CLI applier** (`startd8 vipp apply`) validates the underlying
> apply mechanics. The **HTTP gate** (`/stakeholders/apply/{preview,ratify}` + challenge) is the M-apply
> surface we shipped — it needs the endpoint served with `--enable-apply --strict`. Do **both**: CLI for
> speed, HTTP to prove the gate.

Command groups: canonical `startd8 kickoff stakeholders …`; legacy `startd8 panel …` still works. Verify
anything with `--help`. Prereqs: `ANTHROPIC_API_KEY` set; a facilitated panel session **with a
synthesis** exists on the household (`startd8 kickoff-panel list`).

---

## Track A — full pipeline via CLI

### A1. Household, through PREVIEW only (no write)

```bash
cd "$HH"                                                      # household project root
startd8 kickoff-panel list                                   # pick a session id with a synthesis
startd8 kickoff-panel triage <sid>                           # FR-R2 · $0 routing report
startd8 kickoff stakeholders propose <sid> --run             # FR-R3 extract→stage · PAID (small)
startd8 kickoff stakeholders propose <sid> --serialize --accept-all   # FR-R5 → VIPP inbox
startd8 vipp negotiate                                       # FR-R6 → dispositions.json
startd8 vipp apply                                           # apply PREVIEW — no write. STOP on household.
```
✅ Check: `startd8 vipp apply` printed the preview; the inbox is unchanged; no `concierge-*` files appeared.

### A2. Throwaway, REAL write

Never write the household's real inputs. Work on a copy (carries the inbox+dispositions from A1):

```bash
TW="$(mktemp -d)/throwaway"
cp -r "$HH" "$TW" && cd "$TW"
startd8 vipp apply --apply --yes                            # REAL write, throwaway only
```
✅ Check: the target `docs/kickoff/inputs/*.yaml` changed (or a `concierge-*.jsonl` appeared) and the
inbox was shredded. Then `rm -rf "$TW"`.

---

## Track B — the HTTP apply gate (proves what M-apply shipped)

Serve the endpoint with the write gate on (mandatory strict). `--enable-apply` **requires** `--strict`
+ at least one `--allowed-origin` (it refuses to start otherwise):

```bash
cd "$HH"
startd8 kickoff stakeholders serve \
  --enable-apply --strict --allowed-origin http://localhost:3000 \
  --host 127.0.0.1 --port 8710
# prints the bearer token — copy it into $TOK below
```

In another shell — **preview is $0 and byte-identical, safe on the household.** Strict mode requires a
matching `Origin` and a **fresh `X-Nonce` per request** (single-use):

```bash
TOK=<token-from-serve>
curl -sS -X POST http://127.0.0.1:8710/stakeholders/apply/preview \
  -H "Authorization: Bearer $TOK" -H "Origin: http://localhost:3000" \
  -H "X-Nonce: n$RANDOM" -H "Content-Type: application/json" -d '{}' | tee /tmp/pv.json
```
Returns `would_apply`, `content_hash`, `challenge`. **On the household, stop here** (preview only).

For the **real ratify write, restart `serve` pointed at the throwaway** (`cd "$TW"; startd8 kickoff
stakeholders serve --enable-apply --strict --allowed-origin http://localhost:3000 …`), then:

```bash
CH=$(python3 -c "import json;print(json.load(open('/tmp/pv.json'))['challenge'])")
curl -sS -X POST http://127.0.0.1:8710/stakeholders/apply/ratify \
  -H "Authorization: Bearer $TOK" -H "Origin: http://localhost:3000" \
  -H "X-Nonce: n$RANDOM" -H "Content-Type: application/json" \
  -d "{\"proposal_ids\":[\"<id-from-would_apply>\"],\"challenge\":\"$CH\"}"
```

### Gate behaviors to verify deliberately (the reason it's built this way)
- **Byte-identical preview:** `shasum "$HH/.startd8/vipp/proposals-inbox.json"` before/after preview → unchanged.
- **Single-use:** re-run the *same* ratify → `409 challenge already used`.
- **Stale:** `startd8 vipp negotiate` (or re-serialize) between preview and ratify → `409 … re-preview`.
- **Expired:** wait > 5 min after preview, then ratify → `403 challenge expired`.
- **Forged:** ratify with a garbage `challenge` → `403 invalid or forged challenge`.

---

## Can I do this end-to-end in a Grafana dashboard? — **Not fully today.**

Grafana can drive the **two ends** and **display** the middle, but not *drive* the middle stages:

| Stage | Grafana today |
|---|---|
| **run** (paid Q&A) | ✅ `kickoff-stakeholders-panel`, mode **Run** |
| triage / extract→stage / serialize / negotiate | ❌ **no panel UI** — CLI or `curl` the endpoint routes |
| **apply** (preview → ratify) | ✅ same panel, mode **Apply** (two-screen flow) |
| pipeline **funnel** (staged→inbox→dispositions→apply-status) | ✅ read-only display (M-display) |

So a Grafana run today is: **Run panel → drop to CLI/curl for triage→negotiate → Apply panel**, watching
the funnel refresh. Two enabling follow-ups are also still open (see `WORKBOOK_PANEL_NEXT_STEPS.md`
*Cross-cutting*): **provision the plugin** into the shared Grafana, and the **datasource `/stakeholders/*`
proxy + token** (so the panel never holds the bearer token). A fully Grafana-native end-to-end would
additionally need drive panels (or a single wizard panel) for the four middle stages — not yet built.

---

## Verdict (fill in — FR-P1 requires a written verdict)

```
# M-pilot verdict — <date>
- Household end-to-end through apply-PREVIEW: PASS/FAIL   (no writes; inbox byte-identical)
- Throwaway apply WRITE via CLI (vipp apply --apply):    PASS/FAIL   (target changed; inbox shredded)
- HTTP gate preview→ratify on throwaway:                 PASS/FAIL
- Gate behaviors: byte-identical [ ]  single-use [ ]  stale [ ]  expiry [ ]  forged [ ]
- Cost spent (household run + extract): $____
- Friction / surprises:
- Verdict: SHIP / FIX-FIRST — <one line>
```
