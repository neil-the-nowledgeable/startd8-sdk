# `synthetic-probe` SLI Type — Design Doc (fan-out freshness; a signal the subject has no metric for)

**Status:** Design doc (pre-requirements) — larger/novel capability; NOT yet specced to FR level
**Date:** 2026-07-23
**GitHub:** startd8-sdk **#308** (ContextCore carry to follow) · companion to #307 (span-metrics binding)
**Source:** `OSS/mastodon/analysis/option-b2-freshness-probe-capability-ask.md`
**Owner:** observability artifact generator (`src/startd8/observability/`)

> **Why a design doc, not requirements.** #307 is a binding increment on a proven pattern (#286/#300).
> #308 is materially bigger: a **new SLI *type*** and a **new artifact class** (a runnable probe spec with
> runtime-execution semantics), grounding a signal the subject emits **no metric for**. This doc frames the
> shape, the hard constraints, and the phasing so a follow-on `/reflective-requirements` + CRP pass can spec
> it properly. **Do not implement from this doc.**

---

## 1. The problem (settled from source)

FR-007 **fan-out freshness** = status-creation → feed-visible latency. It is the pilot's flagship
*derive-value* case: *"a derived SLO Mastodon has no metric for is a positive finding."* It cannot be
shortcut two ways over:

- Mastodon emits **no** freshness metric (no manual span on the write path).
- **`propagation_style: :link`** (OTel Sidekiq gem 0.29.0, not overridden): `FeedInsertWorker` runs in its
  **own trace** with a span *link* to the enqueue — creation and feed-visible are **not in one trace**. So
  freshness is **not** a single-trace span-duration, and a span-metrics connector (#307) **cannot** produce
  it. This is the precise reason #307 stops at per-span RED and #308 exists.

## 2. The capability — a `synthetic-probe` SLI

The author declares a probe *shape*; the generator emits **two** artifacts:

```
declared:  probe = { action, poll, assert, interval, timeout }     # author states the SHAPE
                                                                    # (threshold stays INFERRED)
emit ┌─ freshness SLO   : SLI queries the probe's published metric (e.g. probe_fanout_freshness_seconds), target p99 < N
     └─ probe-runner spec: a blackbox-style job — run `action`, poll `poll` until `assert`, publish t(visible)−t(created)
```

**Mastodon fan-out probe:**
- `action` = `POST /api/v1/statuses` (create a status)
- `poll` = `GET /api/v1/timelines/home` for the returned status id
- `assert` = id present; **measure** = `t(visible) − t(created)`
- publishes e.g. `probe_fanout_freshness_seconds`

**Author-quality vs derivation-quality:** the author supplies the probe shape; the **threshold stays
inferred** (pilot discipline — Genchi Genbutsu: don't hand the SDK the SLO number). This mirrors #300's
"query determinable, target from author-or-deferred," but here even the *metric* is produced by the probe.

## 3. What makes this different from #286/#300/#307 (the design tension)

| Axis | #286/#300/#307 (bind) | #308 (probe) |
|---|---|---|
| Metric | already emitted; we bind a query | **does not exist** until the probe runs and publishes it |
| Artifact | SLO/alert (declarative YAML) | SLO **+ a runnable probe-runner spec** (a new artifact class) |
| Execution | none (static generation) | **runtime**: needs a running Mastodon + API credentials + a scheduler |
| Trust | reads real telemetry | **writes synthetic traffic** (creates real statuses) — side effects |
| `compare-live` | replay PromQL, expect data | SLI binds **only once the probe runs** — a new "pending-probe" verdict class |

The last row is the crux: this is **genuinely a live-subject SLI**, not static generation. That is
inherent to grounding a signal the app doesn't emit — and it is **not fabrication**: the probe *measures*
real behavior; it does not assume a metric that isn't there.

## 4. Open questions for the requirements pass

- **OQ-1 — probe-runner artifact target.** What does the SDK emit? A Prometheus **blackbox_exporter** module
  config? A k8s **CronJob**/**Deployment** manifest? A generic `probe-spec.yaml` the operator wires to a
  runner? (Leaning: a portable declarative `probe-spec.yaml` + one concrete runner recipe, mirroring how the
  SDK emits ServiceMonitors/alerts rather than running them.)
- **OQ-2 — credential & side-effect handling.** The probe creates real statuses and needs API tokens. How are
  secrets referenced (never fabricated — reuse the `Receiver.target` secret-reference discipline)? Is a
  cleanup/delete step part of the probe shape? A dedicated test account?
- **OQ-3 — the published-metric contract.** Name/labels/unit of `probe_fanout_freshness_seconds` — single-
  sourced (a descriptor profile, like #307 FR-3) so the SLO's SLI query and the runner's publish agree.
- **OQ-4 — threshold inference vs deferral.** With no author target, is the freshness SLO threshold-deferred
  (like #300 D2) or does the SLO ship target-less as a monitoring SLI? (Leaning: threshold-deferred — reuse
  the #300 D2 machinery; the probe still emits a bindable query.)
- **OQ-5 — `compare-live` semantics.** A new verdict class: "SLI valid but unbound until the probe runs."
  Distinct from a dead SLI (#274) and a bound one. How does the baseline/gate treat it? (It must NOT red-flag
  as a dead SLI — it is a *pending-probe*, not a *no-matching-series* defect.)
- **OQ-6 — ContextCore carry.** The probe declaration `{action, poll, assert, interval, timeout}` needs a
  carry mechanism analogous to REQ-CCL-107/109. That is a paired ContextCore ask (to follow).

## 5. Phasing (proposed)

1. **P0 — declaration + SLO (static).** `DeclaredProbe` model + parse; emit the freshness SLO (threshold-
   deferred, reusing #300 D2) whose SLI queries the probe's (not-yet-published) metric; record a **pending-
   probe** gap. **$0, no runtime.** Delivers the "derived SLO Mastodon has no metric for" as a *positive
   finding* immediately — the pilot's headline value — without the runtime surface.
2. **P1 — probe-runner spec emission.** Emit a portable `probe-spec.yaml` + one concrete runner recipe
   (blackbox/CronJob), secret-referenced, with the published-metric contract single-sourced.
3. **P2 — live binding + `compare-live` pending-probe verdict.** Run the probe against a real Mastodon;
   `compare-live` shows the freshness SLI binds; add the pending-probe verdict class to the gate.
4. **P3 (alternative track) — link-aware cross-trace analysis.** Follow the `FeedInsertWorker` span *link*
   back to the enqueue and compute the delta trace-natively (no synthetic traffic). Novel; most connectors
   don't do cross-trace link math. Track as a b2-upgrade once P0–P2 exist.

## 6. Relationship to #307 & dependencies

- **Independent of #307** (needs nothing from span-metrics binding) but pairs naturally: #307 = the emitted
  async **RED**; #308 = the derived end-to-end **freshness**.
- **Depends on** a ContextCore probe-declaration carry (OQ-6) for the non-hand-authored path.
- **Reuses** #300 D2 threshold-deferral, the secret-reference discipline (notification policy), and the
  descriptor-profile single-sourcing (#307 FR-3).

## 7. Recommendation

Spec **P0 first** via `/reflective-requirements` — it delivers the flagship derive-value finding at **$0/no
runtime**, exercises the ContextCore-carry + SLO-emit path, and de-risks the runtime questions (P1–P2) behind
a working static artifact. P1–P3 follow as separate increments once P0 lands and OQ-1/2/5 are answered.

*Read-only pilot origin; design doc — not a build order. Requirements + CRP precede any code.*
