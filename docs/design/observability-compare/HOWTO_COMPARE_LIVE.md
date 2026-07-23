# How-To: Verify your generated observability against real telemetry (`observability compare` / `compare-live`)

> **What this is.** A portable guide for **any project** that generates observability artifacts
> (SLOs / alert rules / dashboards) from a ContextCore onboarding surface, and wants to prove those
> artifacts actually bind to the metrics a real subject emits — *before* they ship a dead SLI.
>
> This is **not** the model benchmark (`benchmark_matrix`). It is a **derived-vs-emitted fidelity
> check**: it takes the PromQL your generator *derived* and replays it against the metrics a subject
> actually *emits*, then tells you which SLIs bind and which query nothing.

---

## 1. Why you want this (the bug class it catches)

A generator can emit a perfectly well-formed SLO whose PromQL evaluates against **nothing** — because
the subject is traces-only, or emits the metric under a different name/label, or the series is opt-in
and off by default. The SLO looks green (it "exists"), the dashboard panel is blank forever, and no
alert ever fires. This is the **#274 / #275 dead-SLI class**, and it is invisible to any check that
only inspects the generated YAML.

`compare-live` catches it by asking the only question that matters: *does this query return data
against the real emitted surface?*

Two tiers:

| Tier | Verb | What it checks |
|------|------|----------------|
| **A** (static) | `observability compare` | Reconciles the *derived* PromQL identity against the declared/known metric surface — surfaces `fr_coverage` gaps (`suppressed_base_metrics`, `deferred_declared_kinds`, `unverified_base_metrics`, …). No runtime. |
| **B** (live) | `observability compare-live` | Stands up (or connects to) a real Prometheus, waits for a real scrape, **replays every derived query**, and reports per-SLI *bind vs dead*. Merges Tier-A gaps into the same report. **Authoritative.** |

---

## 2. Prerequisites

- `startd8` SDK installed (or `PYTHONPATH=<sdk>/src`).
- Your generated artifacts directory — the output of
  `generate_observability_artifacts(onboarding_metadata_path, output_dir)`, containing:
  - `observability-manifest.yaml` (its `fr_coverage` block = Tier A)
  - `slos/`, `alerts/`, `dashboards/` (the PromQL replayed for Tier B)
- The `onboarding-metadata.json` you generated from (reconstructs the expected metric identity).
- **A backend** — pick one:
  - **Standup path** (needs Docker): `compare-live` boots your subject image + a Prometheus.
  - **Existing-backend path**: `--prometheus <url>` replays against a Prometheus you already run
    (the multi-container / Mastodon path — see §7).

---

## 3. The three-step loop

```bash
# 1. Generate the artifacts (your normal generation step)
python3 - <<'PY'
from pathlib import Path
from startd8.observability.artifact_generator import generate_observability_artifacts
generate_observability_artifacts(Path("onboarding-metadata.json"), Path("./observability"))
PY

# 2a. Static reconcile (fast, no runtime) — surfaces the Tier-A gaps
startd8 observability compare \
  -m ./observability/observability-manifest.yaml \
  --onboarding-metadata onboarding-metadata.json

# 2b. Live replay (authoritative) — stand a subject up and replay every query
startd8 observability compare-live \
  -m ./observability/observability-manifest.yaml \
  --artifacts-dir ./observability \
  --onboarding-metadata onboarding-metadata.json \
  --subject-image myorg/myservice:1.4.0 \
  --subject-port 8080 \
  --metrics-path /metrics
```

Or replay against a Prometheus you already have running:

```bash
startd8 observability compare-live \
  -m ./observability/observability-manifest.yaml \
  --artifacts-dir ./observability \
  --onboarding-metadata onboarding-metadata.json \
  --prometheus http://localhost:9090
```

> `--prometheus` must be a **loopback** URL unless you pass `--allow-prod` (a guard against pointing
> the harness at a production backend by accident).

---

## 4. Reading the report

```
Status: FAIL ✗ — 11 dead SLI(s) (Tier B fail)

Tier B (live fidelity — authoritative):
  replayed 11 · binding coverage 0.0 · bound-no-data 0 · dead (fail) 11
    ✗ myservice/latency: mismatched axes [metric_name.latency_bucket, service_label_key]; the
      emitted identity is absent from the live backend and no built-in profile matches its series —
      declare a per-axis `metrics` override on the target.

Tier A (static divergence): 2 gap(s) across 1 class(es).
  suppressed_base_metrics [2]
```

- **binding coverage** — fraction of replayed SLIs that returned data. `1.0` = every SLI binds.
- **dead (fail)** — the SLI's query returned nothing *and* no built-in metric profile explains it →
  the #274/#275 signal. The `mismatched axes` list tells you *which* dimension is wrong
  (metric name, label key, error selector, `le` bucket, …).
- **bound-no-data** — the query is valid and the series *should* exist but the backend has no samples
  yet (usually a warm-up problem, not a generator bug).
- **Tier A gaps** — honest static divergences the generator already recorded (e.g. base RED SLIs
  *suppressed* because the surface is traces-only). These are surfaced, not failures by default
  (pass `--strict-tier-a` to make them contribute a fail).

**A "dead" SLI is a finding, not always a bug.** If the subject genuinely doesn't emit that series,
the honest fix is upstream (declare the real emitted series, or a functional FR with a real target) —
the report tells you exactly which axis to correct.

---

## 5. Exit codes & the baseline (CI gate)

| Exit | Meaning |
|------|---------|
| `0` | Clean — every SLI binds (or every dead SLI is in the baseline). |
| `2` | **FAIL** — a **new** dead SLI shipped (the regression signal). |
| `3` | **UNKNOWN** — the live replay was inconclusive (standup/scrape/backend failed). *Infra, not a code regression* — don't fail the build on this alone. |

A real subject legitimately has *some* dead SLIs (metrics it doesn't emit). You don't want those to
fail CI forever — you want to catch a **new** one. That's the baseline:

```bash
# Author the baseline once (explicit operator action — never automatic)
startd8 observability compare-live ... --baseline compare_live_baseline.json --write-baseline

# Thereafter, gate: exit 2 ONLY on a dead SLI not already in the baseline
startd8 observability compare-live ... --baseline compare_live_baseline.json
```

Commit `compare_live_baseline.json` next to your fixture. When you intentionally change the accepted
set, re-run with `--write-baseline` and commit the diff — the baseline diff is your reviewable record
of which SLIs are known-dead.

---

## 6. Wiring it into CI

The SDK ships a reference gate — copy `scripts/compare_live_gate.sh` and adapt the fixture paths. Its
two hard-won safety properties are worth preserving verbatim:

1. **A presence floor.** A baseline diff is *asymmetric*: it catches new dead SLIs but is **blind to a
   generator regression that DROPS your SLIs entirely** (zero SLIs ⇒ zero new fails ⇒ false PASS). The
   gate asserts a minimum SLO-file count (`EXPECT_MIN_SLOS`) so "the generator stopped emitting" is
   itself a failure.
2. **Fail-closed exit mapping.** A crashed standup must not read as green. Map every non-{0,2,3} exit
   to a failure explicitly.

```yaml
# .github/workflows/observability-compare-live-gate.yml (sketch)
jobs:
  gate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: pip install -e .
      - name: derived-vs-emitted gate
        run: bash scripts/compare_live_gate.sh   # boots a pinned prom/prometheus subject in CI
```

Set `PROMETHEUS_URL` to use an existing backend; leave it unset to use the Docker standup path with a
pinned `SUBJECT_IMAGE`.

---

## 7. Multi-container / real-app subjects (the Mastodon path)

`--subject-image` stands up **one** image (v1). A real app (Mastodon = Postgres + Redis + Sidekiq +
web + streaming) can't be a single container. For those, run the app's own stack however you normally
do, point a Prometheus at it, and replay:

```bash
startd8 observability compare-live \
  -m ./observability/observability-manifest.yaml \
  --artifacts-dir ./observability \
  --onboarding-metadata onboarding-metadata.json \
  --prometheus http://localhost:9090
```

This is exactly how the Mastodon RepoProbe pilot ran: declare the app's real
`prometheus_exporter` surface in the onboarding metadata, generate, then replay the derived queries
against the app's live Prometheus. Cross-subject mismatches (queries for series the backend doesn't
have) show up as `fail` — which is the whole point.

---

## 8. Gotchas (read these — each one has bitten someone)

- **`... | head` eats the real exit code.** Piping the CLI/gate into `head`/`tail` makes `$?` report
  the pager's exit, not the gate's. Capture the exit code without a pipe:
  `startd8 ... ; code=$?`.
- **`unknown` (exit 3) is not a pass and not a code regression.** It means the live replay couldn't
  reach a real scrape. Treat it as infra flakiness (retry / investigate the standup), never as green.
- **The scrape gate proves *warmth*, not just liveness.** `compare-live` waits until samples have
  actually landed (`scrape_samples_scraped > 0`) *and* the job's series set is stable across two
  consecutive scrapes — otherwise a query races the first scrape and false-fails as `bound-no-data`.
- **Duplicate / empty-value label matchers fail *silently*, not loudly.** A query like
  `{status="",status=~"5.."}` or `{method=""}` is **accepted** by the Prometheus query API (Prometheus
  2.47 returns `success` with **zero results**) — it does not 400. So a malformed selector is a
  *silent* dead SLI, exactly the class `compare-live` exists to catch. (Stricter validators/linters
  *do* reject duplicate label names — don't rely on the query API to reject them for you.)
- **Grafana dashboard JSON needs `jb install`.** If you see
  `startd8-mixin/vendor/ is missing or empty`, the dashboard-JSON step is skipped — harmless for
  compare-live (it replays SLO/alert PromQL), but run `jb install` in `startd8-mixin/` to silence it.
- **Baseline identity is directory-qualified.** Verdict IDs incorporate the artifact path, so two
  services with the same-named SLI in different dirs don't collide in the baseline.

---

## 9. One-line mental model

> **`compare` asks "does the derived query's identity match the declared surface?" (static).
> `compare-live` asks "does the derived query return data from the real surface?" (runtime).
> A `fail` is a query that binds to nothing — ship it and you've shipped a blind SLO.**

See `RETROSPECTIVE.md` (how this capability was built — reuse the engine, add only the seam) and
`REQUIREMENTS.md` (the full contract) in this directory.
