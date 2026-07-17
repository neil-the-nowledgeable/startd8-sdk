# Capability Index — Requirements Navigator

**What this is:** the SDK's capability manifests (`startd8.sdk.capabilities.yaml` — 66 caps —
and the `startd8.observability.manifest.yaml` signal leaf) rendered as **Node cards** — the
*machine-readable* side of the same grammar the requirement docs use in
`startd8-ctxseed/docs/design/{kickoff,wireframe}/README.md`.

> **Why this file exists (data point #4).** This is the **CL-13 migration rehearsal** for
> `dev-os/NODE-SCHEMA.md`: render the live capability YAML as Nodes *by hand* to prove the
> mapping and surface what the additive migration needs — **before** refactoring the shipped
> `v1.25.0` manifest. It found one real schema refinement (see [Migration findings](#migration-findings-the-data-point-4-payload)).

---

## The mapping (YAML entry → Node)

The capability YAML is *already* a Node, minus two fields. Grounded against the file:

| Node field | `sdk.capabilities.yaml` key | Notes |
|---|---|---|
| `key` | `capability_id` | stable identity (e.g. `startd8.observability.otel_logging`) |
| `status` | *(derived)* | from `maturity` **×** evidence strength — see finding #1 |
| `maturity` | `maturity` | `stable` / `beta` (API stability — a **distinct** axis) |
| `does` | `summary` + `description{developer,agent}` | multi-audience, native |
| `wont` | — **missing** | the migration adds it (seedable from anti-pattern prose) |
| `lives` | `evidence[]{type,ref,description}` | already **typed** (`code`/`test`/`doc`) |
| `ships_when` | — **missing** | needed only for `maturity: alpha`/deferred (none here) |
| `confidence` | `confidence` | native (0.7–0.95 across the file) |
| `triggers` | `triggers` | search index, native |
| `children` | evidence → `observability.manifest.yaml` signals | the drill edge already exists |

---

## Level 1 — The landscape (66 caps, by domain)

*Fly over the whole SDK at the domain altitude — drill into a pedestal for its caps. Grounded 2026-07-16. Maturity mix file-wide: **31 stable · 35 beta** · confidence 0.7–0.95 (median 0.85).*

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

The three observability caps as full Node cards. `WON'T` is **derived** from each entry's
description/anti-pattern prose (the field the YAML doesn't yet carry — flagged for author confirm):

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

┌─ startd8.observability.session_tracking ───────── 🟡 built, thin · maturity: beta ─┐
│  DOES    SessionTracker singleton: start_session → id, record_request(tokens,       │
│          time, cost), end_session. 7 OTel metrics (active_sessions up_down_counter, │
│          requests/tokens/cost counters, response_time histogram, context_usage      │
│          gauge, truncations counter). Thread-safe.                                   │
│  WON'T   (derived) Graceful no-op when OTel not installed — won't crash the host.    │
│          Metrics only — not a tracer/sampler.                                        │
│  LIVES   code src/startd8/session_tracking.py  (no test-type evidence listed)        │
│  KEY     startd8.observability.session_tracking      confidence 0.80                 │
│  APPROVE?  [ does the 🟡 (beta + single code ref, no test) match reality? ]          │
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

2. **`wont` is seedable, not hand-written from scratch.** `otel_logging` carries its anti-pattern
   *in the description* ("logging.getLogger() silently misses Loki") — that IS the floor.
   `session_tracking`'s "graceful no-op when OTel not installed" is a won't-crash floor. The
   migration can propose `wont` from existing prose, author-confirms, rather than inventing it.

3. **`ships_when` correctly stays absent.** All 3 have code leaves ⇒ no activation gate. Confirms
   the invariant *`ships_when` present ⟺ `lives` empty* holds on built entries (the wireframe's
   `FR-WPI-8` was the empty-leaf case; here there are none).

4. **The YAML is *ahead* of the markdown on grounding.** `confidence` and typed `evidence` are
   native here and were the fields the hand-drawn cards *lacked*. The migration is genuinely
   **bidirectional**: markdown gains `confidence`/typed-`lives`; YAML gains `wont`/`maturity`-as-
   status-source. Neither format was the superset — the Node is.

### The additive migration (proposed, non-breaking)

```yaml
# add to each capability entry — additive, no existing field changes:
    wont: |                         # seeded from description/anti-pattern, author-confirmed
      logging.getLogger() misses Loki — the OTel handler is never attached.
    # `status` is not stored — it is DERIVED at render time from maturity × evidence.
    # `ships_when` added ONLY when a capability has no code-type evidence (maturity: alpha).
```

**Do not apply yet** — this rehearsal *is* the gate evidence; the actual edit to the shipped
`v1.25.0` manifest is CL-13's next step, taken deliberately after this lands.
