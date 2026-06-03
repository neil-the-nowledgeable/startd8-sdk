# Controlled Corpus — Pipeline Integration Validation Runbook

**Goal:** confirm the corpus + deterministic-ingestion integration fires correctly in a **live**
cap-dev-pipe prime run (the one thing the unit/trove tests can't prove).

## What's already proven (no LLM needed)
`python3 docs/design/controlled-corpus/validate_corpus_integration.py` — replays 20 real trove
postmortems through the actual wired functions and asserts write→accumulate→read. **PASSES.**
So the integration *logic* is correct; the runbook below validates it fires in a *live* run.

## Live validation (needs API keys + LLM budget)

Run from `.cap-dev-pipe/` against a target project (e.g. the strtd8 app or startd8-sdk itself).
Two prime runs are needed: run 1 **writes** the corpus; run 2 **reads** authorities from it.

```bash
cd .cap-dev-pipe
# 0. (optional) seed the corpus so run 1 already has authorities:
#    python3 -m startd8.corpus.bootstrap <v0.json> <oracle.json> <PROJECT_ROOT>/.startd8/controlled-corpus.json

# 1. plan ingestion (now deterministic ASSESS/TRANSFORM by default — watch the cost)
./run-plan-ingestion.sh --provenance pipeline-output/<name>/run-provenance.json

# 2. prime run #1 — accumulates the corpus at <PROJECT_ROOT>/.startd8/controlled-corpus.json
./run-prime-contractor.sh --provenance pipeline-output/<name>/run-provenance.json --all

# 3. prime run #2 — should now inject "Established project vocabulary" into spec prompts
./run-prime-contractor.sh --provenance pipeline-output/<name>/run-provenance.json --all --fresh --kaizen
```

## Assertions (post-run checker)

```bash
python3 docs/design/controlled-corpus/validate_corpus_integration.py postrun \
    pipeline-output/<name>/<run-dir> <PROJECT_ROOT>
```
Checks: ASSESS + TRANSFORM ran **deterministic** (cost 0) in the ingestion diagnostic; the corpus
file was written at `<PROJECT_ROOT>/.startd8/controlled-corpus.json` with terms.

### Manual confirmations (the parts the checker can't see)
- **Deterministic ingestion cost drop:** `plan-ingestion-diagnostic.json` → `phases.assess.cost_usd == 0`
  and `phases.transform.cost_usd == 0`; total ingestion LLM cost ≈ PARSE only (~62% reduction vs the
  ~$0.42 baseline on the 17-feature workload).
- **Seed quality unchanged:** `seed_quality_score` within noise of the pre-change baseline (seed task
  content is derived from PARSE features either way).
- **Read path fired (run #2):** enable `--kaizen` (captures prompts) and grep a captured spec prompt
  for `Established project vocabulary` — confirms `render_authorities_md` reached the drafter with the
  `project_root` thread (the #1 fix). Absent on run #1 (corpus not yet mature) is expected.
- **false_pass_risk surfaced:** `controlled-corpus.json` contains ≥1 `false_pass_risk` term once an
  unstable/semantically-weak file recurs (e.g. the Flask RAG on the OB workload).

## Watch-outs
- The deterministic-ingestion default-flip changes **every** plan-ingestion run — this run is also the
  first live validation of that behavior change.
- Corpus authorities only appear once a `target_file` reaches maturity ≥2 (≥2 runs) — run #1 alone
  won't show them unless the corpus was bootstrapped (step 0).
- If cwd ≠ project_root, the read path still resolves correctly now (project_root is threaded into
  `gen_context`); pre-fix it would have fallen back to cwd.
