# Hardened Pricing Triad — N=2 Run + N=1↔N=2 Repeat-vs-Flip Comparison

**Date:** 2026-06-19
**Runs:** N=1 (`HARDENED_PRICING_TRIAD_N1_2026-06-19.md`) + N=2 (18 cells); compared via `scripts/compare_runs.py`
**Effective samples:** 3 per (service, model) coordinate (1 from N=1 + 2 from N=2)
**Cost:** N=2 ≈ $7.04; **$10.27 total across both runs**
**Headline:** N≥2 converted the N=1 snapshot into signal — **one degradation was a real, reproducible weakness; three were variance that flipped.** Trusting N=1 alone would have mislabeled them.

## Repeat-vs-flip verdict (samples shown as `N1, N2-r0, N2-r1`)

| Seed | Opus 4.8 | gpt-5.5 | Gemini 2.5 Pro |
|---|---|---|---|
| **REST** | `0.47,1.00,1.00` — **FLIPPED** (0.47 was noise) | `1.00×3` — **STABLE** | `1.00×3` — **STABLE** |
| **gRPC** (Node) | `deg,0.93,deg` — **FLIPPED** (flaky bind) | `1.00,1.00,deg` — **FLIPPED** (one flake) | `deg×3` — **VARIANT-DEGRADE** (varied causes) |
| **GraphQL** | `1.00,0.84,1.00` — **FLIPPED** (mostly nails it) | `deg×3` — **CONSISTENT-DEGRADE (real weakness)** | `deg×3` — **VARIANT-DEGRADE** (varied causes) |

## Findings N=1 could not have given

1. **One genuine, reproducible weakness — gpt-5.5 on GraphQL.** Degraded all three samples for the same reason (server exits rc=1, the undeclared-framework problem). Not variance — a consistent blind spot (reaches for a framework like uvicorn without declaring it in `requirements.txt`).
2. **Three N=1 "failures" were variance and flipped:** Opus/REST `0.47`→`1.00,1.00`; Opus/gRPC never-ready→scored `0.93` once (intermittent bind, not incapacity); gpt-5.5/gRPC mostly perfect with one flake. **N=1 would have mislabeled all three** — the concrete case for N≥2.
3. **Gemini consistently fails the Node/GraphQL lanes, but with *differing* causes** (never-ready, missing `winston`, compile-fail) → a real inability to ship a working Node gRPC / GraphQL server, not a single bug.

## Discrimination, sharpened
- **By protocol:** REST solved by all (2 STABLE + 1 flipped-to-good); gRPC flaky for all and beyond Gemini; **GraphQL hardest — only Opus reliably scores it.**
- **By model:** Opus strongest on the hard lanes (GraphQL), flaky on gRPC bind; gpt-5.5 solid REST/gRPC, reproducible GraphQL dep-declaration weakness; Gemini solid REST, can't ship Node/GraphQL.
- **Cross-cutting failure class:** dependency-declaration (uvicorn, winston) recurs across models — the design question stands: pre-provision common frameworks vs require self-declaration materially moves GraphQL/gRPC scores.

## Method & caveats
- `compare_runs.py` aggregates all samples per coordinate across runs (Mottainai — generate once, compare free) and classifies STABLE / VARIANT / CONSISTENT-DEGRADE / VARIANT-DEGRADE; it is sample-count-aware (n=1 is inconclusive).
- **Still small:** 3 samples; coordinates reading "med 0.93, range 0.00" rest on a single scored sample. **N≥5 for any published claim**, especially to firm up the flaky-bind (gRPC) and the gpt-5.5/GraphQL weakness.
- Degrade-honesty (FR-32) held throughout: every failure kept its structural score and reported a named cause; nothing misscored as 0.

## Reproduce
```
doppler run -p startd8 -c dev -- python3 scripts/run_flagship_benchmark.py --run --budget 15 \
  --services pricingservice rest-pricingservice graphql-pricingservice --reps 2
python3 scripts/compare_runs.py <N1-out-dir> <N2-out-dir>
```
