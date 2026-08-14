# Capability Index — Requirements Navigator

**What this is:** the SDK's capability manifests (`startd8.sdk.capabilities.yaml` — **68** caps /
`v1.27.0` — and the `startd8.observability.manifest.yaml` signal leaf) rendered as **Node cards** —
the *machine-readable* side of the same grammar the requirement docs use in
`startd8-ctxseed/docs/design/{kickoff,wireframe}/README.md`.

> **Why this file exists (data point #4).** Originally the **CL-13 migration rehearsal** for
> `dev-os/NODE-SCHEMA.md` (hand-render before touching the manifest). **CL-13 `wont` is SHIPPED**
> (v1.26.0 rolled `wont` to every capability; v1.27.0 = 68 caps). This README stays the mapping +
> findings record — counts/status below match the live YAML (refreshed 2026-08-14 after a
> survivorship catch: the “refreshed” claim had been stamped without updating this file).

---

## The mapping (YAML entry → Node)

The capability YAML is *already* a Node, minus two fields. Grounded against the file:

| Node field | `sdk.capabilities.yaml` key | Notes |
|---|---|---|
| `key` | `capability_id` | stable identity (e.g. `startd8.observability.otel_logging`) |
| `status` | *(derived)* | from `maturity` **×** evidence strength — see finding #1 |
| `maturity` | `maturity` | `stable` / `beta` (API stability — a **distinct** axis) |
| `does` | `summary` + `description{developer,agent}` | multi-audience, native |
| `wont` | `wont` | **present** on all 68 (CL-13 SHIPPED; seeded from each entry's own prose) |
| `lives` | `evidence[]{type,ref,description}` | already **typed** (`code`/`test`/`doc`) |
| `ships_when` | — **absent by design** | only when no code-type evidence / `maturity: alpha` (none here) |
| `confidence` | `confidence` | native (0.7–0.95 across the file) |
| `triggers` | `triggers` | search index, native |
| `children` | evidence → `observability.manifest.yaml` signals | the drill edge already exists |

---

## Level 1 — The landscape (68 caps, by domain)

*Fly over the whole SDK at the domain altitude — drill into a pedestal for its caps. Grounded 2026-08-14 against `v1.27.0`. Maturity mix file-wide: **31 stable · 37 beta** · confidence 0.7–0.95 (median 0.85).*

```
domain                        caps   maturity mix
Agent layer ..................  3     beta-leaning
Provider layer ...............  2
Utility layer ................  2
Resilience layer .............  2
▶ Observability layer ........  3     1 stable-pair + 1 beta   ← drilled below
Developer tools ..............  2
Integration layer ............ 13     (ContextCore, MCP, forward-manifest, …)
Construction / polyglot ...... 12     the 2nd (LLM-driven) generation path
Cloud-native deploy ..........  8
Agentic loop .................  6
Consultation .................  7
Persona-drafting family ......  3
Kickoff / dev tooling ........  3
```
Same grammar at every altitude: a domain's `status` is the min of its caps; a cap's is the min of its evidence. Advertise the lowest open loop — no rounding up.

---

## Level 2 — The Observability layer, previewed

The three observability caps as full Node cards. `WON'T` is **authored in YAML** (CL-13); cards
below mirror the live entries (not hand-derived placeholders):

```
┌─ startd8.observability.cost_tracking ──────── ✅ built+wired · maturity: stable ─┐
│  DOES    Provider-agnostic cost tracking: CostTracker (per-call), PricingService  │
│          (per-model rates), BudgetManager (warn/max + BUDGET_WARNING/EXCEEDED),    │
│          CostAnalytics (aggregate/forecast), UsageLimitManager (quota). OTel: 4    │
│          metrics via costs/otel_metrics.py.                                        │
│  WON'T   (derived) Won't hardcode a provider's pricing — rates come from           │
│          PricingService. Won't block calls unless UsageLimitManager is configured. │
│  LIVES   code src/startd8/costs/tracker.py · code costs/otel_metrics.py (4 metrics)│
│          code costs/budget.py · test tests/costs/                                  │
│  KEY     startd8.observability.cost_tracking      confidence 0.90                  │
│  APPROVE?  [ does DOES match intent? ] · [ is the derived WON'T right? ]           │
└────────────────────────────────────────────────────────────────────────────────────┘

┌─ startd8.observability.otel_logging ───────── ✅ built+wired · maturity: stable ─┐
│  DOES    get_logger(name) from startd8.logging_config eagerly attaches the OTel    │
│          log handler so all logs reach Loki; _ensure_default_log_file_handler()    │
│          gives eager init. Used across contractors/ + truncation_detection.py.     │
│  WON'T   logging.getLogger() silently misses Loki — the OTel handler is never       │
│          attached. (This anti-pattern IS the floor; it lives in the source prose.) │
│  LIVES   code src/startd8/logging_config.py (get_logger) · code logging_otel.py     │
│  KEY     startd8.observability.otel_logging      confidence 0.90                    │
│  APPROVE?  [ is the anti-pattern the right WON'T? ]                                 │
└────────────────────────────────────────────────────────────────────────────────────┘

┌─ startd8.observability.session_tracking ───────── ✅ built · maturity: beta ────────┐
│  DOES    SessionTracker singleton: start_session → id, record_request(tokens,       │
│          time, cost), end_session. 7 OTel metrics (active_sessions up_down_counter, │
│          requests/tokens/cost counters, response_time histogram, context_usage      │
│          gauge, truncations counter). Thread-safe.                                   │
│  WON'T   Graceful no-op when OTel is not installed — never crashes the host.        │
│          Metrics only — not a tracer/sampler. Thread-safe (no state corruption).     │
│  LIVES   code src/startd8/session_tracking.py  (no test-type evidence listed)        │
│  KEY     startd8.observability.session_tracking      confidence 0.80                 │
│  APPROVE?  [ does built+beta with code-only evidence (no test) match reality? ]      │
└──────────────────────────────────────────────────────────────────────────────────────┘
```

**Drill to the leaf:** each card's metrics (`startd8.active.sessions`, `startd8.cost.total`, …)
are Nodes one level down in `startd8.observability.manifest.yaml` (121 signals), keyed by dotted
name, `source_file` = their `lives`. Concept → signal → code line, one grammar.

---

## Migration findings (the data-point-4 payload)

Rendering the live YAML by hand surfaced what the CL-13 migration must handle:

1. **`maturity` ≠ `status` — they are two axes, and the YAML is right to separate them.**
   `maturity` = API stability (`alpha`/`beta`/`stable`); `status` = build completeness (does a code
   leaf exist, is it tested). `cost_tracking` and `otel_logging` are both `stable`, but only
   `cost_tracking` has `test`-type evidence. **Refinement for `NODE-SCHEMA.md`:** `status` should be
   *derived* from evidence (`code`+`test` ⇒ ✅ · `code` only / `beta` ⇒ 🟡 · no code ⇒ 📄), and
   `maturity` kept as a **distinct optional field**. The single-`status` markdown cards were lossy;
   the machine side caught it.

2. **`wont` is seedable, not hand-written from scratch.** (Confirmed by CL-13 rollout.) `otel_logging`
   carries its anti-pattern *in the description* — that IS the floor. The migration proposed `wont`
   from existing prose; author-confirm was unnecessary at scale (0 TODO flags in v1.26.0).

3. **`ships_when` correctly stays absent.** All 3 have code leaves ⇒ no activation gate. Confirms
   the invariant *`ships_when` present ⟺ `lives` empty* holds on built entries (the wireframe's
   `FR-WPI-8` was the empty-leaf case; here there are none).

4. **The YAML is *ahead* of the markdown on grounding.** `confidence` and typed `evidence` are
   native here and were the fields the hand-drawn cards *lacked*. The migration is genuinely
   **bidirectional**: markdown gains `confidence`/typed-`lives`; YAML gains `wont`/`maturity`-as-
   status-source. Neither format was the superset — the Node is.

### The additive migration — **SHIPPED** (CL-13)

Applied in `startd8.sdk.capabilities.yaml` **v1.26.0** (`wont` on all then-66 caps) and carried
forward in **v1.27.0** (68 caps). Shape that landed:

```yaml
    wont: |                         # seeded from each entry's own prose (no TODO flags)
      logging.getLogger() misses Loki — the OTel handler is never attached.
    # `status` is not stored — it is DERIVED at render time from maturity × evidence.
    # `ships_when` added ONLY when a capability has no code-type evidence (maturity: alpha).
```

Residual (not CL-13): keep `status` derived (never stored); optional `ships_when` only for
alpha/empty-lives. Hand cards above are the consumed face — keep them in sync with YAML counts.
