# Forensic — Prime's default path is degraded (Micro Prime + complexity routing OFF)

**Date:** 2026-08-18 · **Type:** forensic findings + conscious-decision record · **Status:** findings landed; the restoration is a DEFERRED design decision (owner: user)
**Scope:** why a normal `run_prime_workflow.py` run (no flags) generates more expensively / more coarsely than it could, and whether the Summer-2026 benchmark caused it.

> **One-line verdict:** The user's intuition is correct — a normal Prime run *is* degraded by default — but the **cause is not the benchmark**. The benchmark's desired posture (Micro Prime off, complexity routing off) is the **global default**, and normal runs silently inherit it. The two are the *same knob*; that coupling is the real defect.

---

## 1. The two layers (why "it's all config-driven" is true AND misses the point)

**Layer A — orchestrator: genuinely clean.** `prime_contractor.py` never reads `benchmark_mode` (its 6 "benchmark" mentions are all docstrings around the deterministic-shortcut gate, `prime_contractor.py:3712-3849`). It only sees **explicit config params** — `skip_deterministic_shortcut` (`:568`), `repair_enabled`, `force_regenerate`. No benchmark concept is baked into the orchestrator. ✅

**Layer B — defaults: the leak.** The degraded posture is the *global default*, so every normal run inherits it:

| Knob | Default | Where | Effect |
|------|---------|-------|--------|
| `micro_prime_enabled` | **False** | `prime_contractor_config.py:78`; instance default `prime_contractor.py:724` | no element-level generation (no local/cheap-model decomposition + element repair) |
| `complexity_routing_enabled` | **False** | `prime_contractor_config.py:79`; instance default `prime_contractor.py:720` | no tier classification → no routing simple tasks to cheaper models |
| `repair_enabled` | True | `prime_contractor_config.py:80` | repair IS on by default ✅ (properly modular) |

**What OFF actually does** (`prime_contractor.py:5174`): with routing disabled, tier-selection **returns the default cloud generator immediately** — no classification, no cheap-model tiering, no Micro Prime. Every feature goes through the single full-file cloud path. → **higher cost + coarser generation** = the reported symptom.

---

## 2. The precise modularity violation

There is **no line** anywhere that says "benchmark mode → micro-prime off." Instead:
- `run_prime_workflow.py:385` — `--benchmark-mode` + `--micro-prime` is a hard `parser.error` (benchmark is *forbidden* from turning it on).
- `run_prime_workflow.py:630 / 647` — Micro Prime / routing engage **only** when `pc_config.*_enabled` is true, which only `--micro-prime` / `--complexity-routing` / config `enabled:true` sets.

So **the benchmark's "off" and the normal run's "default" are the same knob.** The benchmark *free-rides on the shared default being off* rather than owning its own degradation. You cannot restore full-quality normal runs without also changing what the benchmark sees — unless the benchmark first gets its own explicit off-switch.

---

## 3. Attribution (not the benchmark)

The default-off was introduced by two **"accidental complexity reduction"** refactors, not benchmark work:
- **`d2bee926`** (2026-03-11) — *"default micro-prime off (AC-R4-R3)"*, reasoned as "no element-path traffic means no new element-path bugs."
- **`77a7d9c1`** (2026-03-13) — consolidated the defaults into `PrimeContractorConfig`.

The benchmark then *coupled* to this default (via the mutual-exclusion). Refactor + benchmark **jointly** leave normal runs degraded.

---

## 4. Doc-vs-code drift (fix regardless of the decision)

`CLAUDE.md` and memory `project_cheap_model_strategy` describe Micro Prime as the essential default path ("file-whole bypass is no longer the default for non-Python tasks") — but the **code defaults Micro Prime + routing off**. The map contradicts the territory. Align the docs whichever way the decision lands.

---

## 5. Recommended conscious restoration (two-step decouple — NOT yet executed)

To get the intended shape — benchmark disables via *its own* config, normal runs full-quality by default, zero coupling:

1. **Give the benchmark its own off-switch:** make `--benchmark-mode` *explicitly* set `micro_prime_enabled=False` + `complexity_routing_enabled=False` (it already forces `skip_deterministic_shortcut=True`). Benchmark owns its degradation.
2. **Then flip the shared defaults ON:** `micro_prime_enabled=True`, `complexity_routing_enabled=True` (the two dataclass defaults + the `.pop("enabled", True)` loaders + the instance defaults at `prime_contractor.py:720/724` + `--micro-prime`/`--complexity-routing` default-true, keeping the existing `--no-micro-prime` override at `run_prime_workflow.py:258`; add a `--no-complexity-routing` counterpart if absent).

**Conscious tradeoff to own:** step 2 resurrects the element-path bug surface `d2bee926` deliberately parked. Pair it with confidence in the element path's health (the repair pipeline + the 5-language Micro Prime test suites). This is *why* it is a human decision, not an auto-fix.

⚠️ **Implementation caveat:** the decouple edits `prime_contractor.py:720/724`, and that file currently carries **uncommitted user changes** (the Delivery-Evidence-Contract empty-elements skip — unrelated to this). Coordinate with that in-flight work before editing.

---

## 6. Pilot (validate the restored path)

Proven Prime targets: `docs/design/model-benchmark/seeds/seed-{adservice,cartservice,checkoutservice,...}.json` (Online Boutique services). Caveat: each is **single-feature** (1 task), so to actually exercise per-feature routing + Micro Prime, run several or use `scripts/benchmarks/prime_parity_seed_suite.json`. The validation run (spends real LLM $ — gate it):

```
python3 scripts/run_prime_workflow.py \
  --seed docs/design/model-benchmark/seeds/seed-checkoutservice.json \
  --micro-prime --complexity-routing --output-dir /tmp/prime-pilot
```
(no `--benchmark-mode`) → confirm the logs show tier classification + Micro Prime engaging.

---

*Grounded 2026-08-18 against the live tree; every file:line above was opened and confirmed. The restoration in §5 is intentionally left unexecuted — it is a design decision with a real bug-surface tradeoff.*
