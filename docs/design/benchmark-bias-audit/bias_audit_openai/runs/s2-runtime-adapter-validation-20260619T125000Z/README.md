# S2 Runtime Adapter Validation

**Run ID:** `s2-runtime-adapter-validation-20260619T125000Z`  
**Date:** 2026-06-19  
**Scope:** benchmark seed-envelope runtime integration  
**Status:** local adapter validation and one paid generated-service cell complete

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

## Paid Cell Result

One isolated LLM-maximized cell completed through Doppler `startd8/dev`:

```bash
doppler run -p startd8 -c dev -- python3 scripts/run_flagship_benchmark.py \
  --run --budget 5 --reps 1 \
  --models openai:gpt-5.5 \
  --services resolvedpriceservice
```

| Field | Result |
|---|---|
| Run spec | `ada9a30a5c58` |
| Cell | `resolvedpriceservice` × `openai:gpt-5.5` × N=1 |
| Status | `ok` |
| Composite quality | `0.90` |
| Structural quality | `0.80` |
| Compile gate | passed |
| Functional coverage | `1.00` (24/24 behavioral assertions) |
| Actual cost | `$0.4584` of `$5.00` ceiling |
| Pipeline / model time | `689.2s` / `673.3s` |
| Isolation | `rlimits+seatbelt-loopback`; network isolated |
| Integrity | zero deterministic skips; no sandbox violation; no degradation |

The generated service passed all nine valid pricing cases and all fifteen invalid-request cases. Its
only server output was a non-fatal Node deprecation warning about calling `start()`.

The durable run artifacts are under:

```text
.startd8/benchmark-runs/ada9a30a5c58/
  run-spec.json
  cells.json
  aggregate.json
  leaderboard.md
  sandboxes/resolvedpriceservice-openai_gpt-5.5-r0/
```

`run_flagship_benchmark.py` merges `hardened-index.json` and enables the Track 2 suite by default.
The older `run_ob_benchmark.py` path remains baseline-only.
