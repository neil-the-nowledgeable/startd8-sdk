# Review Focus — E2E Cap-Dev-Pipe Multi-Model Comparison

Weight these concerns heavily; they are where we most need an external architectural perspective.

1. **Cross-tool / cross-repo boundary.** The pipeline spans two tools — `contextcore` CLI
   (polish/analyze/init/export) and the `startd8` SDK (plan-ingestion, prime) — both orchestrated by
   `run-atomic.sh`. Is threading `--model` only through the startd8 stages (and running contextcore
   once, shared) a sound v1 boundary, or does it undermine the "end-to-end comparison" claim?

2. **"Shared contextcore preamble vs per-model" decision.** v1 runs the contextcore manifest/polish
   stages once (model-independent) because they expose no `--model` flag. Does a shared manifest
   feeding per-model plan-ingestion introduce hidden coupling or bias? Is "shared preamble + per-model
   generative span" the right abstraction, or should the whole thing be per-model even if contextcore
   uses its default model?

3. **Per-stage cost attribution across two tools.** prime cost comes from `prime-result.json`
   (`total_cost_usd`); plan-ingestion from a diagnostic or cost-DB time-window; contextcore cost may be
   unattributable. Is summing these into a "total end-to-end cost" honest/defensible? How should
   unattributed cost be represented so rankings aren't skewed?

4. **Model threading mechanics.** Threading one `--model` to plan-ingestion (config
   `assessor_agent`/`transformer_agent`) + prime (`--lead-agent`/`--drafter-agent`) via the
   orchestration layer. Is config injection without editing `run-plan-ingestion.sh` actually viable
   (OQ-11), and is there a risk a stage silently falls back to its default model (Claude Sonnet),
   invalidating the comparison?

5. **Isolation correctness.** Per-model `{workdir,output}` trees reusing `materialize_sandbox` /
   `SANDBOX_IGNORE`. Does copying the shared provenance into each model's output, plus the existing
   exclusion of `.startd8`/state/`.cap-dev-pipe`, fully prevent cross-model contamination across the
   *whole* pipeline (not just prime)?

6. **Deferred cross-repo dependency (OQ-10).** True all-stage variation needs contextcore to expose a
   model flag. Is deferring this acceptable, and is the v1/v2 split drawn at the right line?

7. **Capability score validity.** Final score reuses prime `cross_file_gate` + feature completion,
   plus plan-ingestion `ingestion_metrics`. Is that a meaningful end-to-end capability signal, or does
   it over-weight the prime stage?
