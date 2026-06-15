# Scope: Adopt cap-dev-pipe `run-atomic` for the model-comparison harness (cross-repo)

**Date:** 2026-06-02
**Status:** Scope / proposal (not implemented)
**Why:** Our harness bypasses `run-atomic`, which costs us three of its validated features —
**run-NNN numbering** (now re-implemented on our side, `--runs-root`), the **`--fresh` anchor-aware
clean** (M3 landmine **L1**), and **operator-gate handling**. Routing the comparison *through*
`run-atomic` folds all three back in instead of re-implementing each. The one blocker is that
`run-atomic` can't pin a model.

## What `run-atomic` already provides (verified)
- **Auto run-numbering** `run-%03d-<ts>` + `latest` symlink (`run-atomic.sh:164-174`).
- **`--reuse-export <run-provenance.json>`** — skip stages 0–4 and reuse a prior manifest (line 105).
- **`--stop-after export|ingestion`** — run only the shared preamble once (line 104).
- **`--run-id <id>`**, `--route prime|artisan`, `--profile`, `--skip-*`.
- **`run-prime-contractor.sh --fresh`** in the chain = the **anchor-aware clean** (won't wipe the
  M3 spine) — resolves **L1** for free.
- **Unrecognized flags pass through** `run-prime-contractor → run_prime_workflow` (line 31/99/419),
  so `--lead-agent`/`--drafter-agent` already reach prime *if run-atomic forwards them*.
- Operator-gate non-interactive handling (REQ-CDP-INT-010 / `CDP_NON_INTERACTIVE`).

## The one missing piece (the cross-repo change)
A single **`--model provider:model`** on `run-atomic.sh` (and `run.sh`) that threads to both
generative stages:
1. **prime** — forward `--lead-agent`/`--drafter-agent` to `run-prime-contractor` (already
   passthrough-capable; run-atomic just needs to **forward** them — likely a small addition to its
   arg loop). *Trivial.*
2. **plan-ingestion** — inject `assessor_agent`/`transformer_agent` into the ingestion **config**
   (exactly the patch our harness does today in `live_stage_runner`). The native chain resolves the
   config from provenance (`resolve-provenance.py`), so run-atomic/`run-plan-ingestion.sh` needs a
   `--model` that post-patches `EFFECTIVE_CONFIG` (the documented OQ-11 mechanism). *The real work.*
   - contextcore stages (polish/analyze/init) stay model-independent — **OQ-10 unchanged**.

## Harness-side rework (startd8 side)
Replace the bespoke orchestration (`run-cap-delivery` once + per-model `run-plan-ingestion` +
`run_prime_workflow`) with a thin loop over `run-atomic`:
1. **Shared preamble once:** `run-atomic --plan … --requirements … --stop-after export --run-id shared`
   → one `run-provenance.json`.
2. **Per model (serial, A→G→O):** in its isolated copy,
   `run-atomic --reuse-export <shared-prov> --route prime --model <m> --run-id <NNN-or-slug>`
   → auto-numbered, `--fresh` anchor-safe, gates honored.
3. **Extraction/analysis unchanged:** read each run's `prime-result.json` (+ `--check in_sync` for
   L3) and feed the existing `comparison_analysis`.
- Keep per-model **isolation** via either (a) our existing per-model source copies, or (b)
  run-atomic's own run dirs + a per-model `--name`/project scope (also fixes the cosmetic
  **ContextCore project-state** collision).

## What this resolves / gains
- **L1 (anchor/spine safety):** inherited via `run-prime-contractor --fresh` — no more "validate the
  seed first" gate.
- **Run-numbering:** native (could retire our `--runs-root` shim, or keep it for non-atomic mode).
- **Operator gates / non-interactive:** handled by run-atomic + `CDP_NON_INTERACTIVE`.
- **Manifest reuse:** `--reuse-export` is the first-class version of our "shared preamble."
- One validated pipeline path instead of two divergent ones.

## Costs / risks
- **Cross-repo change** in cap-dev-pipe (the `--model` threading) — must be authored + tested there.
- Reworking the harness orchestration (the validated direct path would become a fallback).
- run-atomic re-runs more per invocation (gates, postmortem) — slightly heavier per model.
- `--reuse-export` + per-model isolation interaction needs validation (does reuse copy provenance
  into each model's tree correctly?).

## Migration plan (low-risk)
1. Land the cap-dev-pipe `--model` change (prime forward is trivial; ingestion config-injection is
   the substantive part) + a unit/dry-run test there.
2. Add `--orchestrator {native,atomic}` to `compare-models-e2e` (default stays **native** until
   proven); `atomic` routes through run-atomic per the loop above.
3. Validate `atomic` on the **M3** run (small/cheap) — confirm numbering, spine `in_sync`, gates,
   reuse-export sharing — then flip the default.
4. Once stable, optionally retire the bespoke `live_stage_runner` stage calls (keep the extraction).

## Open questions
- **OQ-A:** Does `run-atomic` forward arbitrary `--lead-agent/--drafter-agent` to
  `run-prime-contractor`, or only its known flags? (If not, add forwarding.)
- **OQ-B:** Cleanest injection point for plan-ingestion `--model` — a `run-plan-ingestion.sh
  --model` that patches the config, or run-atomic patching `EFFECTIVE_CONFIG` directly?
- **OQ-C:** With `--reuse-export`, does each model run get an isolated working tree, or do we still
  wrap with our per-model source copies? (Determines isolation strategy + ContextCore scoping.)
- **OQ-D:** Per-model `--run-id`/project scoping to eliminate the ContextCore state collision.

**Bottom line:** the adoption is mostly *one* cap-dev-pipe feature (`--model`, where ingestion
config-injection is the only non-trivial part) plus a harness orchestration swap behind a flag. It
trades re-implementing numbering/anchor-safety/gates for a single cross-repo change — and resolves
L1 properly. Recommended once the M3 native run has proven the comparison shape is what we want.
