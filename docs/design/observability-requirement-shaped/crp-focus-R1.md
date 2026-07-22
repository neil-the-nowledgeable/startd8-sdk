# CRP Focus — #226 de-overfit observability spec (Round 1)

## Least-reviewed target (concentrate here)
The **v0.4 generalization** content is brand-new and unreviewed:
- §0.3 (De-Overfit Generalization) + the overfit catalog table
- **FR-12** — contract-first SLI-kind determination (resolved SLI-kind set; convention fallback only for the request-serving family; non-request+undeclared ⇒ ∅ + coverage gap)
- **FR-13** — delete the unconditional RED synthesis in `_ensure_red_coverage`
- Generalized **FR-5** (signal_kind primary axis), **FR-6** (kind→profile table), **FR-7** (per-signal_kind thresholds), **FR-9** (∅-service coverage)
- **CR-3** — 7-kind enum + no-listen-port inference

## Settled — DO NOT relitigate
- (a) FR-1/2/3 are **cross-repo** (ContextCore/cap-dev-pipe own the manifest + onboarding-metadata schemas; the SDK is consume-only). Settled by exploration.
- (b) OQ-1..OQ-6 were resolved by the reflective loop (§0). Do not reopen.
- (c) Back-compat mechanism is fixed: byte-identical absent-input parity (**FR-11**) gated by a golden test (**FR-0**).
- (d) Seam is fixed: extend `MetricDescriptor._PROFILES`, not a parallel kind-dispatcher.

## High-value review axes (weight these)
1. **Parity soundness** — does FR-12's "resolved SLI-kind set, convention-fallback-only-for-request-serving-family" *provably* reproduce today's byte-identical output for an existing http_server service (same descriptor, same 3 SLOs, same panels)? Any path where the resolver yields a different set for a plain http service is a defect.
2. **FR-13 safety** — is deleting the unconditional RED synthesis safe for **every** existing http fixture, or does some current http output depend on the synthesis firing even when convention metrics are present? Name the failure mode if any.
3. **Enum completeness/orthogonality** — is `signal_kind` ∈ {availability, latency, throughput, queue_depth, retry_rate, freshness, run_success, saturation, lag, custom} complete and non-overlapping? (e.g. is `retry_rate` a special case of an error-budget on `run_success`? is `lag` vs `freshness` a real distinction?)
4. **Kind taxonomy gaps** — does the kind→profile table {http_server, grpc_server, async_worker, batch, cron, stream, ml_inference, unknown} leave a real gap? Specifically **hybrid services** that both serve HTTP *and* run background workers — which profile, and does one service need multiple SLI-kind sets?
5. **Non-blocking scoping** — are OQ-5 (pilot evidence absent → worker metric names/thresholds ungrounded) and OQ-7 (who authors signal_kind/target) correctly scoped as non-blocking, or does either actually gate the SDK-side seam?
