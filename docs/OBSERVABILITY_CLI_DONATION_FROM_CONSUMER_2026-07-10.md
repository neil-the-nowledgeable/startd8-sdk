# Consumer feedback + donation candidates — `startd8 observability` generation path

**Date:** 2026-07-10
**Consumer:** an InsightFinder × ContextCore SE demo ("Blue Planetary Investigations") that dogfoods the
observability-generation path end-to-end against a live OpenTelemetry app (Astronomy Shop) + live Prometheus.
**Target:** `startd8-sdk` — `src/startd8/observability/*` and its `observability` CLI group.
**Status:** placed **untracked** for the SDK team to review / commit. Only this file is added; your WIP is untouched.
**Reference code (proven, in the consumer repo):** `.../Insight-Finder/demo/bpi-astronomy/tools/generate_observability.py`
and `.../tools/scorecard.py`.

---

## BLUF
Dogfooding the generation flow surfaced a **coherent abstraction** worth donating, not just a CLI convenience.
Framed simply: **the generator sits between two declarative profiles — `MetricsProfile` (source binding,
which you already have as `MetricDescriptor`) and a proposed symmetric `BackendProfile` (sink targeting).**
Give it both and it emits *directly deployable* observability with no hand-editing on either end.

Concretely, three things:
1. **`startd8 observability generate`** — expose the deterministic generator as a CLI command (it's
   library-only today; only reachable via the full cap-dev-pipe LLM stages).
2. **`BackendProfile`** (new, mirrors your `MetricDescriptor` pattern) — folds two consumer *workarounds*
   (F3 artifact-type scoping + F4 datasource targeting) into one first-class *input*, so `generate` produces
   backend-correct output instead of the consumer post-processing it.
3. **`startd8 observability slo-status`** (secondary) — report SLO status/error-budget from the generated
   OpenSLO + live Prometheus (you generate SLOs but can't yet evaluate them).

A **proven reference** for `BackendProfile` (`bpi-astronomy/tools/backend_descriptor.py`) reproduces the
consumer's hand-rolled post-processing exactly, from one declarative profile.

---

## What worked well (so the balance is honest)
- **`metricsProfile` binding is excellent.** One manifest field (`span-metrics-connector`) bound all four axes
  we'd flagged (metric name, `service_name` label, `status_code` error selector, ms unit). It replaced an
  entire hand-patch. This is exactly the right generalization.
- **The generator is deterministic.** Two runs → byte-identical output (once `alerting.receivers` are declared
  via `observability.yaml`). We diffed it.
- **`validate-promql` is a great primitive.** We independently built our own PromQL-vs-live-Prometheus replayer
  before discovering yours; yours is better-integrated (reconstructs identity from onboarding metadata). Keep it.
- **`detect-profile` / `bind-and-verify` / `contrast`** are strong, discoverable commands.
- **Pollution fix confirmed.** `onboarding-metadata.json` no longer injects `contextcore_*` / `startd8_*`
  dogfooding metrics into every service.
- **Notification policies fail safe.** The generator refuses to fabricate a transport and emits an
  `UNRESOLVED REQUIRED PARAM` comment pointing at `observability.yaml alerting.receivers` — correct behavior.

---

## Findings (symptom → where → workaround → suggested fix → severity)

### F1 — No `startd8 observability generate` command (**HIGH**) — *this is the donation candidate*
- **Symptom:** The deterministic generator can only be run via the cap-dev-pipe (which pulls in LLM plan/prime
  stages) or by importing the library function. `python3 -m startd8.observability.artifact_generator` has no CLI.
- **Where:** `src/startd8/observability/cli.py` (has validate-promql/detect-profile/bind-and-verify/contrast, no `generate`);
  `artifact_generator.py::generate_observability_artifacts` (library-only).
- **Workaround:** a ~30-line consumer wrapper calling the function directly (`tools/generate_observability.py`).
- **Suggested fix:** add a `generate` command that wraps `generate_observability_artifacts()` — see candidate design below.

### F2 — `manifest export` requires `--no-strict-quality` for a plain observability export (**MEDIUM**)
- **Symptom:** `contextcore manifest export -p .contextcore.yaml -o ./out --profile observability` fails with
  "Strict quality requires --task-mapping" — for a straight observability export with no task mapping in play.
- **Workaround:** append `--no-strict-quality`.
- **Suggested fix:** default strict-quality off (or auto-relax) for the `observability` profile, or make the error name the profile.

### F3 — Generator ignores `generation_profile`; emits all artifact types (**MEDIUM**)
- **Symptom:** `--profile observability` sets `onboarding-metadata.generation_profile: observability`, but the
  generator still emits `service_monitor`, `loki_rule`, `runbook`, etc. For an OTLP-push app with no
  Prometheus-Operator and logs in OpenSearch, those are inapplicable.
- **Workaround:** consumer post-gen scope-filter (`tools/postgen.py`).
- **Suggested fix:** → **subsumed by `BackendProfile.supported_artifact_types`** (primary candidate).

### F4 — Dashboard datasource is unconfigurable (defaults to `mimir`) (**MEDIUM**)
- **Symptom:** generated dashboards use a `datasource` template var whose `current` defaults to `mimir`
  (`dashboard_renderer.py`), so they render empty against a Prometheus datasource with a different uid.
- **Workaround:** consumer post-gen remap of the template-var default to the deployment's uid (`webstore-metrics`).
- **Suggested fix:** → **subsumed by `BackendProfile.datasource_uid`** (primary candidate).

### F5 — No SLO-status / error-budget reporting from generated OpenSLO (**LOW**) — *secondary candidate*
- **Symptom:** the SDK *generates* OpenSLO defs but has no command to report current SLI/status/error-budget
  against live Prometheus.
- **Workaround:** consumer `tools/scorecard.py` (parses generated OpenSLO + queries Prometheus).
- **Suggested fix:** `startd8 observability slo-status` — see secondary candidate below.

### F6 — `capdevpipe install` needs `SDK_ROOT` set explicitly (**LOW**)
- **Symptom:** `startd8 capdevpipe install` errors "no value for SDK_ROOT". (Error was clear; `--set-env SDK_ROOT=...` fixed it.)
- **Suggested fix:** discover SDK_ROOT from the installed package location as a default.

---

## Donation candidate (primary): symmetric profiles — `MetricsProfile` (source) + `BackendProfile` (sink)

**The abstraction.** `MetricDescriptor` (`metric_descriptor.py:39`) already decouples *metric identity*
(name / service-label / error-selector / unit) from the PromQL templates — the **source-side** binding.
The generator's output is *also* a function of a second thing you haven't abstracted yet: the **deployment
target**. Two consumer post-processors (F3, F4) exist purely because that's un-modeled. Mirror the pattern:

| | `MetricDescriptor` / `_PROFILES` (exists) | `BackendDescriptor` / `_BACKEND_PROFILES` (proposed) |
|---|---|---|
| Answers | *how does the app emit?* | *what does the backend accept?* |
| Axes | metric name · service label · error selector · unit | datasource uid · supported artifact types · log backend · metrics query URL |
| Effect | binds PromQL identity (F1-metrics) | scopes emitted types (F3) + sets dashboard datasource (F4) + gives validate/slo-status their query URL |

```python
# backend_descriptor.py — mirrors metric_descriptor.py
@dataclass(frozen=True)
class BackendDescriptor:
    profile: str
    datasource_uid: str
    supported_artifact_types: frozenset   # subset of _IMPLEMENTED_ARTIFACT_TYPES
    log_backend: str = "none"             # loki | opensearch | none
    metrics_query_url: str = "http://localhost:9090"

_BACKEND_PROFILES = {
    "mimir-grafana":      BackendDescriptor("mimir-grafana", "mimir", ALL_TYPES, "loki"),         # current default
    "prometheus-grafana": BackendDescriptor("prometheus-grafana", "prometheus", CORE|{"loki-rules"}, "loki"),
    "otlp-opensearch":    BackendDescriptor("otlp-opensearch", "webstore-metrics", CORE, "opensearch"),
}
def resolve_backend(profile, overrides=None): ...   # same shape as resolve_descriptor()
```

**The command consumes both profiles** (mirrors `validate-promql` in `cli.py`):
```python
@observability_app.command("generate")
def generate(
    onboarding_metadata: Path = typer.Option(..., "--onboarding-metadata"),   # carries the MetricsProfile
    output_dir: Path = typer.Option(..., "--output-dir"),
    manifest: Optional[Path] = typer.Option(None, "--manifest"),
    observability_yaml: Optional[Path] = typer.Option(None, "--observability-yaml"),
    backend_profile: str = typer.Option("mimir-grafana", "--backend-profile"),  # NEW: the BackendProfile
    dry_run: bool = typer.Option(False, "--dry-run"),
):
    """Generate deployable observability deterministically (no LLM, no cap-dev-pipe)."""
    from startd8.observability.artifact_generator import generate_observability_artifacts
    from startd8.observability.backend_descriptor import resolve_backend      # NEW
    backend = resolve_backend(backend_profile)
    report = generate_observability_artifacts(
        onboarding_metadata_path=onboarding_metadata, output_dir=output_dir,
        manifest_path=manifest, observability_yaml_path=observability_yaml,
        backend=backend, dry_run=dry_run,                                     # scope + datasource applied inside
    )
    typer.echo(f"services={report.services_processed} artifacts={len(report.artifacts)} "
               f"backend={backend.profile} -> {output_dir}")
```
`backend_profile` defaults to `mimir-grafana` (**byte-identical to today's behavior** — no regression).
This is a small addition that mirrors your own descriptor pattern; it is *not* a parallel subsystem.

**Why it's higher-value than a bare wrapper:** it retires `postgen.py` entirely (F3+F4 become an input),
generalizes `generate` beyond mimir/grafana to *any* backend, and unifies the CLI group — the same
`BackendDescriptor.metrics_query_url` feeds `validate-promql` and `slo-status`, replacing three ad-hoc flags.

**Proven bar (consumer references):**
- `tools/generate_observability.py` — generated **105–107 artifacts / 13 services**, validated by your own
  `observability validate-promql` (**160 PASS / 0 ERROR** at full traffic), **byte-deterministic** across runs.
- `tools/backend_descriptor.py` — the `BackendProfile` reference; `--backend-profile otlp-opensearch`
  **reproduces the consumer's `postgen.py` output exactly** (drops `service-monitors`/`loki-rules`/`runbooks`,
  remaps 13 dashboards `mimir → webstore-metrics`) from one declarative profile.

## Donation candidate (secondary): `startd8 observability slo-status`
Reports current SLO status from the **generated OpenSLO** + live Prometheus (uses your existing
`prometheus_query`): per-service availability, p99, error-budget burn, status. Consumer reference:
`tools/scorecard.py`. Consumer-specifics (owner/criticality enrichment) live in a small config map, not the core.

---

## The remaining hand-off (what "fully donated" would take)
Small, pattern-consistent commits building on existing infra:
1. Add `backend_descriptor.py` (`BackendDescriptor` + `_BACKEND_PROFILES` + `resolve_backend`) — a copy of the
   `metric_descriptor.py` shape. Thread a `backend` arg through `generate_observability_artifacts()` so scope
   + datasource are applied at generation (defaulting to `mimir-grafana` = today's behavior).
2. Add the `generate` command to `observability/cli.py` consuming both profiles.
3. (From F5) add `slo-status` reading generated OpenSLO + `prometheus_query`, taking its query URL from the
   resolved `BackendDescriptor`.
Working references (proven): `tools/backend_descriptor.py` (BackendProfile), `tools/generate_observability.py`
(the generate wrapper), `tools/scorecard.py` (slo-status). `tools/postgen.py` is retired once step 1 lands.

---

## Appendix — reproduce
```bash
# F1 — generation has no CLI (only cap-dev-pipe or the library function)
startd8 observability --help          # lists validate-promql / detect-profile / bind-and-verify / contrast; no generate

# F2/F3 — export needs --no-strict-quality; metadata says observability but generator emits all types
contextcore manifest export -p .contextcore.yaml -o ./out --profile observability            # fails
contextcore manifest export -p .contextcore.yaml -o ./out --profile observability --no-strict-quality
python3 -c "import json;print(json.load(open('out/onboarding-metadata.json'))['generation_profile'])"  # 'observability'
# generate anyway (consumer wrapper) -> out/observability/ still contains service-monitors/ loki-rules/ runbooks/

# F4 — dashboards default to the 'mimir' datasource var
python3 -c "import json,glob;d=json.load(open(glob.glob('out/observability/grafana/dashboards/*.json')[0]));\
print([v['current'] for v in d['templating']['list'] if v.get('name')=='datasource'])"

# Proven: validate the (metricsProfile-bound) output against live Prometheus
startd8 observability validate-promql --artifacts-dir out/observability \
  --onboarding-metadata out/onboarding-metadata.json --prometheus http://localhost:9090
```
