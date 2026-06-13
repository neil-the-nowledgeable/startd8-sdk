# Summer 2026 Model Benchmark — Round 1 (PARTIAL, 2026-06-12)

**Status:** Partial / indicative — **not** the published Round-1 result.
**Spend:** ~$5.25 total (flagships-r1 $1.86 + Opus re-run $3.38 + smokes ~$0.01).

## Scope & caveats (read first)

- **N=1** per (service, model) — single sample, **not statistical** (FR-17 wants N≥5 + median/IQR/CI).
- **Disk-quality (structural-compliance) only** — the **compile gate + test/lint execution** (FR-11
  functional terms) land in **M4**. Per the CRP (R1-F1/F2), this score must be labeled
  "structural-compliance," not "quality," until M4.
- **Fable 5 absent — access-gated.** `claude-fable-5` returns 404 *"not available… see
  anthropic.com/news/fable-mythos-access"*; the account lacks Fable call access. The benchmark's
  hero model awaits access approval.
- **Mistral/Ollama out (FR-7); tier-2/3 not yet run.** This is 3 of the 10-model roster.

## Leaderboard (3 models × 9 services, N=1, structural-compliance)

| Rank | Model | structural score (median) | pass-rate | catastrophic | cost $ |
|---:|---|---:|---:|---:|---:|
| 1 | `gemini-2.5-pro` | 1.000 | 1.000 | 0/9 | **0.40** |
| 2 | `gpt-5.5` | 1.000 | 1.000 | 0/9 | 1.47 |
| 3 | `claude-opus-4-8` | 1.000 | 1.000 | 0/9 | 3.38 |

## The actual finding: the metric saturates → cost is the only differentiator

All three frontier models produced **structurally-perfect code (1.00)** on 8/9 services, so the current
metric **does not discriminate** between them. The only spread observed was **`checkoutservice`** (the
6-dependency orchestration service) at **0.80**. Therefore, at this stage the only real differentiator is
**cost**, where the spread is large:

- **Gemini 2.5 Pro is ~8.5× cheaper than Opus 4.8** and **~3.7× cheaper than gpt-5.5** for equivalent
  structural output.

**Implication:** this directly validates the CRP R1-F1/F2 critique — structural-compliance ≠ functional
quality, and it saturates among frontier models. **M4 (compile gate + test/lint execution) is required for
the benchmark to actually rank frontier models.** Cost + the hardest services (checkout) are the only
signals separating models today.

## Provenance
- Runs: `/tmp/ob-flagships-r1` (gpt-5.5, gemini — valid; Anthropic cells there were dead-key 401, excluded),
  `/tmp/ob-opus-r1` (Opus 4.8, rotated key, 9/9 ok).
- Infra-vs-model failure classification applied (commit `2a5a0493`): auth/access failures excluded from
  scores, not counted catastrophic.
- Sizing reality: actual ~38k in / 15k out tokens per cell (~5× the 8k/6k default). Full Round-1
  (10 models × 9 × N=5) realistically ~$150–200.
