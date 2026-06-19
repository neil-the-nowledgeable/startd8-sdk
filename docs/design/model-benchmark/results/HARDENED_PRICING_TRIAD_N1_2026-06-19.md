# Hardened Pricing Triad — Model-Generation Scoring Run (N=1)

**Date:** 2026-06-19
**Run:** `summer-2026-flagship` (spec `63ee75adaf24`), via `scripts/run_flagship_benchmark.py`
**Matrix:** 3 hardened pricing seeds × 3 flagship models × N=1 = 9 cells, **behavioral scoring ON**
**Cost:** **$3.23** (vs $1.60 flat-token estimate — the GraphQL spec prompt is large)
**Status:** the first real model-generation scoring run across the gRPC / REST / GraphQL pricing lanes.

This is the inaugural exercise of all three protocol lanes end-to-end: each model **generates** the
server from the seed's `requirements_text`, the harness provisions + sandbox-launches it, probes
readiness (tcp for gRPC, http for REST/GraphQL), and scores it with the SDK-authored behavioral suite.

## Leaderboard (functional = behavioral coverage ∈ [0,1]; quality = composite)

| Seed | Opus 4.8 | gpt-5.5 | Gemini 2.5 Pro |
|---|---|---|---|
| **REST** (python stdlib) | q 0.73 · **fn 0.47** | q 1.00 · **fn 1.00** | q 0.97 · **fn 1.00** |
| **gRPC** (Node) | q 0.88 · *degraded* | q 0.90 · **fn 1.00** | q 0.88 · *degraded* |
| **GraphQL** (hardened, python) | q 0.97 · **fn 1.00** | q 0.92 · *degraded* | **failed** (no compile) |

Per-cell cost: graphql/opus $1.235 · graphql/gpt-5.5 $0.301 · graphql/gemini $0.154 ·
gRPC/opus $0.458 · gRPC/gpt-5.5 $0.250 · gRPC/gemini $0.061 ·
rest/opus $0.393 · rest/gpt-5.5 $0.247 · rest/gemini $0.128.

## Honest diagnostics for every non-perfect cell (FR-32 degrade, not 0)

| Cell | Outcome | Root cause (from behavioral provenance) |
|---|---|---|
| GraphQL / gpt-5.5 | degraded | server crashed `ModuleNotFoundError: uvicorn` — reached for a framework and **did not declare it** in `requirements.txt`, so it wasn't provisioned. |
| GraphQL / Gemini | failed | did not pass the compile/structural gate (quality `None`) — no scoreable server. |
| gRPC / Opus | degraded | "server never became ready within 30s" — started but never bound the port. |
| gRPC / Gemini | degraded | crashed `Cannot read properties of undefined (reading 'PricingService')` — a proto-package access bug in the generated Node server. |
| REST / Opus | scored 0.47 | ran and was scored, but failed ~half the behavioral checks — genuine *partial* correctness. |

## What it validates

1. **The benchmark works end-to-end across three protocols** — generation → provision → sandbox →
   readiness → behavioral score. The `.pydeps` import fix held (the GraphQL cell that *did* declare
   its dep — Opus — scored 1.00).
2. **It discriminates, two ways.** By **protocol**: REST easiest (2 perfect), gRPC medium, **GraphQL
   hardest — only 1 of 3 fully scored**, validating the hardened FR-10 design. By **model**: no sweep —
   Opus nailed the hardest seed (GraphQL, incl. selection-driven + derivation + partial-errors) but
   stumbled on gRPC startup and half of REST; gpt-5.5 aced gRPC+REST but under-declared deps on GraphQL;
   Gemini aced REST but couldn't compile GraphQL.
3. **Degrade-honesty works in the wild** — every failure kept its structural score and reported a
   *named* reason; nothing was misscored as 0.

## Caveats & open design signals

- **N=1 — single sample per cell.** These are illustrative, not claims. Degradations especially may be
  one-off; N≥5 is needed to separate skill from run-variance. (An N=2 run follows.)
- **Dependency-declaration policy (design decision).** gpt-5.5's GraphQL degradation was *not* a pricing
  error — it used uvicorn without declaring it. Decide whether common frameworks (uvicorn/FastAPI) should
  be pre-provisioned vs strictly self-declared; this materially affects GraphQL scores.
- **Cost realism:** actual $3.23 ≈ 2× the flat-token estimate — the GraphQL `requirements_text` (SDL +
  algorithm + conventions) is large; budget accordingly for higher N.

## Reproduce / re-score (Mottainai)
```
doppler run -p startd8 -c dev -- python3 scripts/run_flagship_benchmark.py --run --budget 10 \
  --services pricingservice rest-pricingservice graphql-pricingservice --reps 1
```
Raw `cells.json` + `leaderboard.md` persist under the run's `--out-dir`.
