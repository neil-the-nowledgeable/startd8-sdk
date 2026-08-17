# Analysis: runtime grounding — feature o11y + AI o11y complete the circle

**Date:** 2026-08-17 · **Type:** synthesis (grounded) · **Status:** proposed as the loop's runtime edge
**Grounds:** `observability/parity.py` (compare-live) · `costs/otel_metrics.py` (AI cost) · `scaffold_codegen/instrumentation_gen.py` (Harbor-proven) · the o11y→SARIF bridge (`c8fc0314`) · REQ-18/19 (realization) · REQ-22 (verify-liveness) · the CHARTER (SARIF = the findings IR)

## The core insight

The loop so far grounds claims in the **map** — the documents and code-as-written (verify-liveness checks the
gate resolves *at authoring time*). **Feature o11y and AI o11y ground them in the territory — the running
system.** That is how they complete the circle: they extend the NLPS's deepest principle (*grounded, not
asserted*) from the map to deployed reality — the outermost feedback edge.

## Feature o11y = runtime verify-liveness (the top of the liveness column)

`observability/parity.py` is the compare-live *declared-vs-emitted* check (the dead-SLI detector). It is the
**strongest** form of "a requirement can't lie about being verified": not "the gate ran at authoring time" but
**"the deployed feature emits a live signal proving the guarantee holds."** A declared feature with no live
emission is the *runtime* present-but-dead — one altitude above every static cell:

```
FR-gate → REQ-verify → PAIR-companion → corpus  →  RUNTIME feature-signal
  ─────────────── static (map) ─────────────────     ── runtime (territory), the deepest ──
```

And the generative fix is **already built**: `instrumentation_gen.py` (Harbor-FDE-proven, language-agnostic:
`InstrumentationGap → Contract → Renderer → Patch`) *generates the instrumentation that makes a subject emit
the metrics its artifacts want.* A feature-o11y gap → generate the instrumentation → it emits → the gap closes.
`$0`-ish, deterministic — the observability analog of `backend_codegen`.

## AI o11y = the *measured* realization regime (fills the REQ-19 seam)

`costs/otel_metrics.py` (cost telemetry as OTel) is exactly the **"b" provenance source** REQ-19's
confidence-aware seam was built to accept. A node *planned* deterministic (`$0`) whose AI o11y shows real LLM
cost = a **determinism regression, measured from live telemetry** (REQ-19 FR-6). AI o11y grounds the
determinism-% and the planned-vs-realized signal in production, not in static provenance files.

## The circle, closed — with two cheap generative roles

```
INTENT → det-req → det-plan → code → DEPLOY/RUN
                                        │ runtime signals
        feature o11y (parity): live signal?  ── dead SLI = runtime present-but-dead
        AI o11y (costs/otel): generation cost? ── grounds determinism-%, regression
                                        │ findings  (o11y→SARIF bridge already routed — c8fc0314)
                                     SARIF (the findings IR)
                                  ↙                    ↘
      finding→REQ-stub                        o11y-gap→generate-instrumentation
      (sarif_to_req_stub, reactive req)         (instrumentation_gen, $0)
                                        │ human-gated
                              → back to det-req → loop repeats
```

o11y is **not a third IR** — it is the **runtime signal source that makes the findings IR (SARIF) carry
production truth**, not just static truth.

## The convergence that proves it's the same shape

The Harbor pilot's own recurring bug (`FIELDSTATE_EXPLICIT_STATE`): *"`observability-quality.json` emits a bare
`0` **or an absent field**, and a consumer misreads it as a real value."* That is **present-but-dead /
honest-absent, independently rediscovered in the o11y layer** — the same *absence-vs-error* move as
verify-liveness (gate-unrunnable vs gate-fail) and REQ-27 (mechanical-vs-manual). The o11y layer converged on
our exact discipline ⇒ it is essential structure, and it plugs in natively.

## Why it's little cost (all reuse)

`parity.py` · `instrumentation_gen.py` (Harbor-proven) · `costs/otel_metrics.py` · the o11y→SARIF bridge
(routed) · REQ-19's seam (built for exactly this) · the ContextCore Harbor `metric_cov` pilot — **all exist.**
The synergy is **wiring existing pieces through the SARIF loop**, not building new ones. `REQ-28` specs that wiring.

## The one-line conclusion

*The static loop grounds requirements in the map (docs/code); feature o11y + AI o11y ground them in the
territory (the running system) — closing the circle by making "a requirement can't lie about being verified"
mean "the feature emits a live signal proving it works, and here's what it cost to build" — for the price of
wiring, because every piece already exists.*
