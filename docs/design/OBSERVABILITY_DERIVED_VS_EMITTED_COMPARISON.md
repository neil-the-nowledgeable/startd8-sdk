# Observability: Derived-vs-Emitted Comparison — capability proposal

**Status:** proposal (engine validated, glue not built). **Date:** 2026-07-22.
**One line:** *replay the observability artifacts the SDK/ContextCore **derives** against what a real
subject **actually emits**, and report per-SLI which evaluate vs which are dead — automatically,
repeatably, for any subject.*

This is **not a benchmark** (no model scoring, no user-journey). It is a **fidelity comparison**:
does the derived o11y (SLOs / alerts / dashboards) bind to the subject's real telemetry surface?

---

## 1. The problem it solves

The whole value proposition of the observability generator is *derive real o11y from a project's
declared shape*. The only way to know whether the derived artifacts are **correct** is to check them
against the subject's **actual emission surface** — and today that check is a **manual, one-off
human investigation**.

The Mastodon pilot is the proof. A person hand-diffed the derived artifacts against Mastodon's real
instrumentation and found two defect classes the generator shipped silently:
- **FP-1 (metric shape / #274):** derived SLIs queried `http_server_duration` — a metric Mastodon
  (traces-only) never emits. The SLO evaluates against nothing.
- **FP-2 (service naming / #275):** the SLI label was `service="mastodonweb"`; the real OTel
  `service.name` is `mastodon/web`. The selector never matches.

Both were found **by hand**, documented in prose, and filed as issues — a slow, unrepeatable loop.
**This capability turns that human genchi-genbutsu into a command.**

---

## 2. What it is (two tiers)

### Tier A — Static divergence (in the manifest, $0, offline) — *mostly built*
The generator already self-documents where the derived artifacts diverge from the subject's declared
surface, via `report.fr_coverage` (`artifact_generator.py`):
- `unfulfilled` — a declared FR whose metric is absent.
- `empty_services` — a service observed by nothing.
- `ungrounded_kinds` — a recognized-but-deferred workload kind (batch/cron/ml_inference).
- `unverified_base_metrics` (#277) — base SLIs on convention metrics **not verified as emitted**
  (surface unknown).
- `suppressed_base_metrics` (#274 / REQ-CCL-106) — base SLIs **suppressed** because the declared
  `metrics_surface` doesn't emit the convention metric.

That is a **static, metadata-driven mini-comparison** you get for free in every run — "here's where
the derived artifacts can't be grounded." It needs no live subject.

### Tier B — Live fidelity (against real telemetry) — *engine built, glue missing*
The authoritative check: replay every derived PromQL against a Prometheus scraping the **running
subject**, and categorize each SLI:
- **`pass`** — the derived SLI evaluates against real data.
- **`bound_no_data`** — the metric exists but the window is empty.
- **`fail`** — the derived metric **doesn't exist** in the subject's emission (this is FP-1).

The engine already exists: `startd8 observability validate-promql --artifacts-dir <out>
--onboarding-metadata <md> --prometheus <url>` (`observability/validate_promql.py`,
`bind_and_verify.py`, `runtime_fidelity.py`). It emits a structured report keyed
per-service × per-signal × per-query.

---

## 3. Why it's worth building

- **It validates the product's core claim.** "Derive real o11y from declared shape" is only true if
  the derived SLIs bind to real telemetry. This is the only test that proves it — on a real subject,
  not a fixture.
- **It catches the exact bug class this repo just spent a session fixing — *before* it ships.**
  #274 (dead metric) and #275 (wrong label) are precisely `fail`-verdicts. Run this in CI against a
  reference subject and the generator can never again silently emit an SLI that evaluates against
  nothing. The manual pilot found them after the fact; this finds them on every change.
- **It converts a human loop into a repeatable capability.** The pilot's "grep the output, read the
  subject's OTel config, hand-diff" became this session's genchi-genbutsu discipline. A command makes
  it cheap enough to run continuously, on any subject — not just when someone remembers to look.
- **It's the honest evidence for the "OOB vs ContextCore" story.** The comparison *is* the artifact:
  a report that says, per SLI, "the subject emits X; ContextCore derived Y; they match / they don't."
  That is a far stronger claim than a prose write-up.
- **Subject-agnostic reuse.** Nothing about it is Mastodon-specific. Any subject with a `/metrics`
  surface (or an OTel collector) can be compared. It becomes a general "is my generated o11y real?"
  gate.

---

## 4. What already exists (grounded)

| Piece | Where | Status |
|---|---|---|
| Live replay + fidelity report | `observability/validate_promql.py` (`startd8 observability validate-promql`) | **built** — validated 2026-07-22: extracted + replayed 26 real pilot queries |
| Bind/reconcile against live Prometheus | `observability/bind_and_verify.py` (`bind-and-verify`) | built |
| Scrape `/metrics` + match descriptor | `observability/runtime_fidelity.py` (`check_descriptor_binding`) | built |
| Static divergence signals | `artifact_generator.py` `fr_coverage.{suppressed,unverified}_base_metrics`, etc. | built (extended this session) |
| Stand up ANY subject image + readiness gate | `benchmark_matrix/fleet/containerize.py` `boot_and_probe(image=…)` | reusable |
| Compose subject + Prometheus (net, DNS) | `benchmark_matrix/fleet/compose.py` `generate_compose_dict/yaml` | reusable (relax egress-deny → edge net) |

**Validation evidence (2026-07-22):** `validate-promql` replayed the run-008 Mastodon manifest
(26 queries) against a local Prometheus; confirmed #275's `service="mastodon/web"` label is live, and
returned all-`fail` against a non-Mastodon backend — the exact "derived SLI has no matching emission"
signal, working end-to-end.

---

## 5. What's missing (the glue) — the actual build

A thin, subject-agnostic runner + a first-class verb:

1. **`startd8 observability compare`** — ✅ **BUILT (PR #282).** Reads `fr_coverage` from a generated
   manifest and renders a one-shot "here's where the derived artifacts can't be grounded" report
   (`observability/compare.py`). `--json` for machines, `--strict` exits 2 on divergence (CI gate).
   $0, offline. Verified end-to-end on a generated traces-only manifest (surfaces the #274 suppression).
2. **Live runner** — `fleet.compose`/`boot_and_probe` stand up the subject + a Prometheus scraping its
   `/metrics`, wait for a scrape, then invoke `validate-promql` and merge its Tier-B verdicts with the
   Tier-A gaps into one report. Heavier (needs the subject running), but the engine is done.
3. **CI gate (optional)** — run #2 against a pinned reference subject; fail the build on new `fail`
   verdicts (a regression that ships a dead SLI).

---

## 6. Honest scope / non-goals

- **Not a benchmark.** No model comparison, no journey scoring — that's `benchmark_matrix/`. This
  reuses only its container *stand-up* machinery.
- **Tier B needs a running subject.** For a heavy subject (Mastodon: Postgres+Redis+Sidekiq+assets)
  that's a real stand-up cost — the deferred "Phase 6." Tier A needs nothing and delivers most of the
  value for a generated manifest.
- **`validate-promql` is not modified by this proposal** — it's the engine; this wraps it.
- **The comparison reports fidelity, not a fix.** A `fail` verdict says "this SLI is dead," not "here's
  the right metric" — that's the generator's job (and, e.g., #274's `metrics_surface` consumption
  already prevents many `fail`s at the source).

---

## 7. Recommended first step

Build **#1 (`startd8 observability compare`, Tier A)** — it's ~an afternoon, $0, offline, and turns the
`fr_coverage` divergence classes already in every manifest into a first-class, human-readable "derived
vs declared" report. Then, only when a live subject is worth standing up, add #2 to upgrade it from
*static divergence* to *empirical fidelity*. The engine for #2 is already validated; #1 is the cheap,
high-leverage rung that makes the capability real without any stand-up cost.
