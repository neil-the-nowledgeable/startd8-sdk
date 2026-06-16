# Benchmark Knobs K2 + K3 — Next Steps

**Date:** 2026-06-15 · **Status:** K1 built+leveraged; K2/K3 spec'd, not built.
**Source spec:** `docs/design/model-benchmark/INFORMATIVE_KNOBS_{REQUIREMENTS,PLAN}.md` (gitignored
working docs) — the original three-knob analysis. **K2 CRP prompt already exists:**
`docs/design/model-benchmark/CRP_PROMPT_K2_R1.md`.

---

## 0. Why now (the prerequisite is finally met)
The three knobs measure *deltas* in a quality signal. Round 1 **saturated** (every model ~1.0
structural), so K1/K2/K3 would have shown nothing but ties — which is why the whole effort detoured
through **Track 2 behavioral scoring** to build a non-saturating metric. That's done: behavior
discriminates (paymentservice **Opus 1.0 vs gpt-5.5/gemini 0.33**), and **K1 is wired into the rescore
report** and already adds signal (separates reliably-wrong gemini from inconsistent gpt-5.5).

**The load-bearing constraint (from the Track 2 retrospective):** run K2/K3 on **validation-rich RPCs**
(payment-like `Charge`), NOT the stateless set (shipping/currency/ad) — those saturate and would flatten
any leverage/role delta the same way structural did. Build the knob; point it at a discriminating RPC.

---

## K2 — Leverage delta (the cost-efficiency thesis)

**What:** run each model with SDK leverage **OFF** (today's benchmark default: deterministic cascade +
micro-prime off) **and ON**, and report the per-model **Δquality / Δcost**. Tests whether a cheaper
model + SDK scaffolding matches a pricier one raw (the prior: lift is largest on the cheapest model).

**Current state in code:**
- `benchmark_matrix/run_spec.py` has `llm_maximize` / `micro_prime_enabled` as **global per-run
  booleans** — one leverage state per run, **no paired axis, no delta**.
- `runner.py` marks any cell with `deterministic_skips>0` as `INTEGRITY_FAIL` — i.e. the integrity gate
  is **designed to reject** leverage-on cells. `run_prime_workflow.py:385` **errors** on
  `--benchmark-mode` + `--micro-prime`.

**Build (per INFORMATIVE_KNOBS plan S2–S4, already CRP-reviewed):**
1. Add a **leverage state** to the cell coordinate (`MatrixCell` + spec `leverage_states=("off","on")`);
   pair each (service, model, rep) across both. Include in `spec_hash`/`total_cells`.
2. **Integrity-exempt ON path:** leverage-on cells omit `--benchmark-mode` and pass
   `--complexity-routing`/`--micro-prime`; for them, `deterministic_skips>0` is **expected, not
   `INTEGRITY_FAIL`** (gate the exemption to `leverage=="on"` — fail-closed for `off`).
3. **Delta report:** per-model `Δquality` + `Δcost` + quality-per-$ (reuse `aggregate_cells` grouped on
   the off/on partition); the "largest lift on the cheapest model" must be directly readable.
4. **Caveat (RUN-028):** when leverage is micro-prime, the on-delta **understates** lift — micro_prime
   doesn't get the `project_knowledge` adherence injection the lead path does; emit the caveat.

**Gotchas:** the integrity-gate exemption is the riskiest spot (a bug exempting `off` cells silently
admits non-LLM-maximal output); same scoring formula across off/on (else the delta is meaningless).
**The K2 CRP (`CRP_PROMPT_K2_R1.md`) already targets these — run it before building.**

---

## K3 — Lead/drafter role matrix

**What:** vary `--lead-agent` vs `--drafter-agent` across models. Diagonal (`lead==drafter`) = the
single-model baseline; off-diagonal = hybrid teams. Reveals planner-vs-implementer asymmetry (is a
model a better lead or drafter?) and whether a hybrid beats any single model.

**Current state in code (greenfield):**
- `MatrixCell = (service, model, repetition)` — **no role axis**.
- `model_comparison.build_command` hard-pins `lead==drafter==cell.model`; `cell_id`/`sandbox_dir_name`
  key on a **single** model (role cells would collide on disk + idempotency key).

**Build (per INFORMATIVE_KNOBS plan S5–S6):**
1. Generalize the cell coordinate to carry **distinct `lead`/`drafter`**; diagonal default must emit a
   command **byte-identical** to today (regression test — or every existing result becomes non-comparable).
2. Make `cell_id` + `sandbox_dir_name` **unique per role cell** (include both specs).
3. **Prunable selection:** `role_pairs` = diagonal-only (default) | full L×D grid | explicit
   `(lead, drafter)` list. Full grid must NOT be implied by merely listing N models (cost guard).
4. Aggregation grouping **by lead / by drafter / by (lead,drafter) pair**; render the L×D quality grid
   with the diagonal marked.

**Gotchas:** combinatorial blow-up (L×D × leverage × reps) — keep each knob independently selectable +
the 200-cell `--allow-large` guard from INFORMATIVE_KNOBS FR-2; `tier3-agent` only matters if routing is
on (K2×K3 interaction — defer).

---

## Recommended order & framing
1. **K2 first** — its CRP is already written, it directly tests the SDK's cost-efficiency thesis (the
   highest-value finding), and the leverage axis is a cleaner code change than K3's coordinate
   generalization. **Run `CRP_PROMPT_K2_R1.md` → triage → build S2–S4.**
2. **K3 second** — guard the diagonal byte-identity, then add the role axis + grouping.
3. **Both run on a validation-rich RPC** (start with paymentservice `Charge`), N≥5, behavioral scoring
   on, leveraging **persist-then-$0-rescore** so the matrix can be re-aggregated for free.

**Composition:** K1×K2×K3 multiply (reps × 2 leverage × ≤9 role cells). Keep each independently
selectable; never default to the full cross-product (INFORMATIVE_KNOBS FR-1/2). The pilot-each-once gate
applies: confirm a knob's delta is non-zero on one cell before funding the matrix.
