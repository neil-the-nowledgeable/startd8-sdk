# S2 Runtime Adapter Validation

**Run ID:** `s2-runtime-adapter-validation-20260619T125000Z`  
**Date:** 2026-06-19  
**Scope:** benchmark seed-envelope runtime integration  
**Status:** local adapter validation complete; paid generated-service cell blocked at credential preflight

## Completed Validation

The committed adapter integrates `resolvedpriceservice` with the Track 2 behavioral harness:

- Feature commit: `522f8bed` (`Add resolved pricing benchmark adapter`).
- Node runtime closure vendored with the lockfile: `npm ci` added 77 packages.
- Focused behavioral checks passed after vendoring:

```text
6 passed, 1 warning
```

The passing tests cover the `resolvedpriceservice` SDK-authored suite, the canonical S2 fixture
adapter, Node workdir provisioning, canonical proto propagation as `pricing.proto`, and the existing
pricing suite regression coverage.

## Paid Cell Preflight

The intended live cell is a one-repetition, LLM-maximized generation from
`docs/design/model-benchmark/seeds/seed-resolvedpriceservice.json`, executed through
`scripts/run_flagship_benchmark.py`, which then invokes the Track 2 behavioral runner.

No `OPENAI_API_KEY` was exported in the execution shell. Doppler is installed and the authenticated
account exposes a `startd8` project, but non-secret configuration lookup did not complete within the
bounded diagnostic attempts. No model call was made and no model quality result is recorded.

This is an infrastructure preflight block, not a model failure. The evidence must remain excluded from
any model comparison until a named Doppler configuration or an exported OpenAI credential is available.

## Remaining Execution Command

Once a credentialed environment is available, execute one isolated cell with an explicit cost ceiling:

```bash
doppler run -p startd8 -c dev -- python3 scripts/run_flagship_benchmark.py \
  --run --budget 5 --reps 1 \
  --models openai:gpt-5.5 \
  --services resolvedpriceservice
```

`run_flagship_benchmark.py` merges `hardened-index.json` and enables the Track 2 suite by default.
The older `run_ob_benchmark.py` path remains baseline-only.
