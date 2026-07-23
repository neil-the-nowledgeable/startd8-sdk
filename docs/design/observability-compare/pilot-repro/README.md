# Mastodon pilot reproduction — a repeatable `compare-live` regression fixture

This directory turns the one-off Mastodon observability pilot (the manual genchi-genbutsu that found
**#274** and **#275**) into a **repeatable, committed artifact** and a **CI gate** (rung #3 of the
derived-vs-emitted comparison capability). See the parent proposal
`docs/design/OBSERVABILITY_DERIVED_VS_EMITTED_COMPARISON.md` and requirements `../REQUIREMENTS.md`.

## What the pilot found (and the generator has since fixed)

- **#274 — dead base SLIs on a traces-only subject.** Derived SLIs queried `http_server_duration`, a
  metric a traces-only Mastodon never emits. The generator now **suppresses** those base RED SLIs when
  `metrics_surface` is non-emitting (`traces_only`) and records the gap.
- **#275 — wrong service label.** The SLI selector used the sanitized id `mastodonweb`; the real OTel
  `service.name` is `mastodon/web` (slash preserved). The generator now uses the real `service.name`.

## The fixture

`onboarding-metadata.json` — a faithful reconstruction of the pilot input (the original run-008
artifacts were never persisted; the SDK's mastodon o11y unit tests use inline synthetic `_meta`).
It carries the pilot's structural traps:

| Service | `metrics_surface` | Role in the repro |
|---|---|---|
| `mastodon` (umbrella stem) | — | Phantom project-root entry — must be **filtered** (#241). |
| `mastodonweb`, `mastodonsidekiq` | `traces_only` | Base RED SLIs **suppressed** (#274). |
| `mastodonstreaming` | `otel_sdk_meter` | Emits the convention metric → SLIs **survive**, carrying the real `service="mastodon/streaming"` selector (#275), and **replay live** in Tier B. |

`compare_live_baseline.json` — the committed set of accepted (known) `fail` verdict identities for the
CI gate. Each identity is `(service | signal | dir-qualified-source | normalized-expr)` — backend-
independent, so it is stable whether replayed against the demo Prometheus or the CI reference subject.

## Reproduce it locally

Against any running Prometheus (e.g. the OpenTelemetry demo at `:9090`):

```bash
PROMETHEUS_URL=http://localhost:9090 bash scripts/compare_live_gate.sh
```

Expected: **Tier A** reports 2 `suppressed_base_metrics` (the #274 fix); **Tier B** reports the
`mastodonstreaming` SLIs as `fail` against a non-Mastodon backend — with the real `mastodon/streaming`
selector (#275) — and surfaces the one-line fix `metricsProfile = span-metrics-connector`. Because
every dead SLI is in the baseline, the **gate exits 0**.

## The CI gate

`.github/workflows/observability-compare-live-gate.yml` runs `scripts/compare_live_gate.sh` with **no**
`PROMETHEUS_URL`, so compare-live stands up a **pinned self-scraping `prom/prometheus`** subject +
Prometheus (docker), replays, and diffs against `compare_live_baseline.json`:

- **exit 0** — no new dead SLI (all fails baselined). ✅
- **exit 2** — a **new** dead SLI shipped (a generator/engine regression). ❌ fails the build.
- **exit 3** — live replay inconclusive (standup/scrape/infra). ⚠️ warns, does not block.

## Related CI

`.github/workflows/observability-fidelity.yml` is a **complementary, not duplicate** gate: a *reusable*
(`workflow_call`/`dispatch`) **coverage** gate wrapping `validate-promql`, where a caller supplies its own
artifacts + Prometheus. This workflow is the *self-contained, auto-triggered* **regression** gate wrapping
`compare-live` (Tier-A merge + baseline-diff over a committed fixture + a stood-up pinned subject).

## Re-baselining (explicit operator action — the gate never self-heals)

When a new dead SLI is *intentional* (e.g. a deliberate new SLI awaiting instrumentation), re-author
the baseline and commit it:

```bash
WRITE_BASELINE=1 PROMETHEUS_URL=http://localhost:9090 bash scripts/compare_live_gate.sh
```
