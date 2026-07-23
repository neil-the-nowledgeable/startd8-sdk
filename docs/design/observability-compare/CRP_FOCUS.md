# CRP Focus — Tier-B live derived-vs-emitted comparison

## Settled — do NOT relitigate (already decided; cross-model memory)
1. **Separate `compare-live` verb** (not a `--live` flag on `compare`). Tier A `compare` already merged (#282); a separate verb + `compare_live.py` module keeps the shipped surface untouched.
2. **Single-image v1 scope.** Multi-container subjects (Mastodon = Postgres+Redis+Sidekiq) are deferred; reachable via `--prometheus <existing-backend>`. OTel-collector-fronted (span-metrics) subjects are out of scope.
3. **`live_standup` owns the subject `docker run`** (threads `--network`) rather than editing `benchmark_matrix/fleet/containerize.py`; reuses only `_await_port_ready`/`docker_available` semantics.
4. Verdict taxonomy (`pass|bound_no_data|fail|error|excluded`) and exit codes (0/2/3) are owned by `validate_promql.py` and imported, not restated.

## Where review input is most valuable (weight these)
- **Scrape-ready gate semantics (FR-3).** Gate is `sum(scrape_samples_scraped{job="subject"})>0`, poll interval 1s, timeout ~60s, errors swallowed to keep polling. Is `scrape_samples_scraped` the right signal vs `up==1` vs both? Any race where the gate passes but the *replayed* metrics still aren't queryable (e.g. subject exposes /metrics but the specific SLI series appear only after warm-up)? Is timeout→`unknown` (never `fail`) correctly load-bearing?
- **Tier-A/Tier-B merge severity rollup (FR-6).** Severity `unknown > fail > pass`; Tier B authoritative; Tier A advisory unless `--strict-tier-a`. Any status combination that produces a misleading rollup (e.g. Tier B `pass` masking a large Tier-A gap set the operator should act on)?
- **CI-gate verdict identity stability (FR-8).** Identity = `(service, signal, source_file-basename, whitespace-normalized expr)`. Is this stable across benign regeneration churn yet sensitive enough to catch a genuinely new dead SLI? Failure modes: two distinct SLIs colliding on the same id; an expr edit that *should* count as new but normalizes to an existing id; basename collisions across dirs.
- **Teardown / leak safety (FR-9).** `finally` teardown removes both containers + network + temp yml, best-effort/never-raises, on every path incl. mid-flight exception and scrape-timeout. Per-run `startd8-cmp-<8hex>` names. Any path that leaks a container/network/tempfile? Is `--keep-up` safe (prints exact rm commands)?
- **localhost / `--allow-prod` guardrail (FR-5).** Standup publishes Prometheus on `127.0.0.1` so `run_validation`'s `_is_local_backend` passes without `--allow-prod`. Is there a way the guardrail is bypassed or a non-local backend reached unintentionally on the `--prometheus` path?
