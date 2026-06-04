# Controlled Corpus — Inventory (location · quantity · quality)

**Date:** 2026-06-03
**Purpose:** one place that says *where the corpus artifacts live, how much is in them, and how good
it is.* Deep narrative lives in `CORPUS_V0_FINDINGS.md` (extraction) and `CONTROLLED_CORPUS_REQUIREMENTS.md`
(the capability); this is the index. Counts are reproducible via the scripts noted per row.

> **Note on `corpus_class`:** it is a **derived field, not stored** (R3-F2) — the saved JSON omits it
> and it is recomputed on load. Class counts below are **runtime-computed** via
> `ControlledCorpusRegistry.load(...)`, not read from the JSON.

---

## 1. Where (locations)

| Artifact | Location | What it is |
|----------|----------|------------|
| **Corpus v0 (extracted)** | `docs/design/controlled-corpus/controlled-corpus-v0.json` (155 KB) | Proto terms + explicit forward-manifest bindings + SRE vocab, distilled from the online-boutique trove |
| **Bootstrap corpus** | `docs/design/controlled-corpus/controlled-corpus.bootstrap.json` (64 KB) | v0 + oracle replayed through the real `ControlledCorpusRegistry` (88 accumulated terms) |
| **Determinism oracle v2** | `docs/design/controlled-corpus/scr-labeled-replay-set-v2.json` | Per-`target_file` PASS/FAIL + req-score, from real postmortems (the determinism signal) |
| **Determinism oracle v1** | `docs/design/controlled-corpus/scr-labeled-replay-set.json` | Earlier kaizen-correlation join (superseded by v2; kept for trace) |
| **Variance segregation** | `docs/design/controlled-corpus/scr-variance-segregation.json` | Run→cluster→model map proving inputs evolved (within-cluster signal is valid) |
| **Extraction scripts** | `extract_corpus_v0.py`, `build_scr_replay_set.py`, `build_oracle_v2.py`, `bootstrap.py`, `validate_corpus_integration.py` | Reproduce every artifact above |
| **Runtime corpus (per project)** | `<project_root>/.startd8/controlled-corpus.json` | The **live, accumulating** corpus a project's runs write (path-fixed `71ad1c78`) |
| **Runtime content store** | `<project_root>/.startd8/corpus-content/<term_id>/<source_checksum>` | Proven file content for deterministic serving (FR-9) |
| **Source trove** | `~/Documents/dev/online-boutique-demo/.cap-dev-pipe/pipeline-output/online-boutique/` | 37 runs (Claude + Gemini, 5 langs) the v0/oracle were mined from |
| **Capability code** | `src/startd8/corpus/` (models, registry, extractor, content_store, provider, view, bootstrap, canonical) | The SDK implementation |

**Live-app status (strtd8):** corpus **write enabled** (`STARTD8_CORPUS_ENABLED=1` +
`STARTD8_CORPUS_CONTENT_STORE=1` in its `pipeline.env`); no persisted corpus yet — run-028's only
feature FAILED (so content store stayed empty; the stray root-level file was cleaned up). Next green
run writes to `strtd8/.startd8/`.

---

## 2. How much (quantity)

**Corpus v0** (`extract_corpus_v0.py`): **9 services · 15 RPCs · 32 entities** (proto, `hipstershop`)
+ **228 explicit forward-manifest bindings** (config_key 77 · render_pattern 79 · formula 59 ·
infrastructure 13) + SRE vocab (9 metrics, SLO targets, alert patterns). The 1,655 `inferred`
contracts are excluded as noise.

**Bootstrap corpus** (`controlled-corpus.bootstrap.json`): **88 accumulated terms**
- by kind: entity 32 · file 23 · rpc 15 · metric 9 · service 9
- by maturity: L1 70 · L2 6 · L3 1 · L4 11

**Determinism oracle v2**: **59 observations** across **9 runs** / **23 distinct `target_file`s**
(the 17-feature anchor cluster). (v1 had 49 obs.)

---

## 3. How good (quality)

**Determinism class distribution** (bootstrap, runtime-computed):
| Class | Count | Meaning |
|-------|-------|---------|
| `deterministic_candidate` | **14** | stable build **and** req-score ≥0.9 → safe to serve $0 |
| `false_pass_risk` | **2** | stable build but req-score <0.7 → **must stay LLM + SCR** |
| `residue_corpus_gap` | 2 | structurally unstable → LLM-hard / corpus gap |
| `insufficient_samples` | 5 | <2 observations → not yet trustworthy |
| `unobserved` | 65 | proto/vocabulary terms with no run determinism yet (fill in as runs land) |

- **`false_pass_risk` terms:** `src/shoppingassistantservice/shoppingassistantservice.py` (the Flask
  RAG — stability 1.0, req 0.5, a real false-PASS) and `PI-001` (a positional-id noise artifact —
  see caveats). The guardrail refuses to ever serve these.
- **Two-axis determinism:** quality = structural stability **×** semantic compliance (req-score).
  The headline finding — title-drift is orthogonal to stability (`confirmation.html`: stability 1.0
  with 7 title variants) — is in `CORPUS_V0_FINDINGS.md`.
- **Confidence / provenance:** every binding carries `confidence` (binding-provenance:
  explicit/inferred) and `source_run_ids`; the v0 corpus keeps **explicit-confidence bindings only**.

**Cross-run, cross-model evidence:** the determinism is measured across 37 trove runs spanning Claude
+ Gemini and 5 languages — the `deterministic_candidate` set is what generated identically across
that variance, not a single run.

---

## 4. Caveats (so the numbers aren't over-read)

- **Inputs evolved** across the trove (every run has a distinct `source_checksum`); the valid
  determinism signal is **within a feature-count cluster** (the 17-feature anchor), not across all 37.
- **`PI-NNN` ids are positional** — the oracle joins on `target_file`, not the id; a stray `PI-001`
  in the bootstrap is residual noise from runs with empty `target_files`.
- **Explicit bindings are single-run** (config-heavy); the cartservice cluster has class/interface
  bindings this representative run lacks — v0.2 should aggregate across clusters.
- **Model imbalance** — 34 Claude vs 3 Gemini runs; cross-model claims are Claude-dominated.
- **Sample size** — 59 labeled observations is enough to demonstrate the method, not yet to set the
  SCR's X/Y thresholds; widening needs more green runs (blocked until the run-028 class of failures
  clears — now fixed via the F811 repair `886dccbd`).
- **Bootstrap is one-shot** (synthetic replay run_ids); not a production-idempotent merge.

---

## 5. Reproduce
```bash
cd docs/design/controlled-corpus
python3 extract_corpus_v0.py        # → controlled-corpus-v0.json
python3 build_oracle_v2.py          # → scr-labeled-replay-set-v2.json
python3 bootstrap.py controlled-corpus-v0.json scr-labeled-replay-set-v2.json controlled-corpus.bootstrap.json
python3 validate_corpus_integration.py offline   # write→read chain on real trove
python3 validate_corpus_integration.py provider  # deterministic-serving demo
```
