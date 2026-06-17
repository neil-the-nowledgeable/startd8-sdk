# Hardened Difficulty Tier — Implementation Plan

**Version:** 1.0 (Draft)
**Date:** 2026-06-17
**Implements:** `BENCHMARK_TASK_DIFFICULTY_REQUIREMENTS.md` v0.3
**Status:** Plan (feeds the reflective pass → requirements v0.4)

> Scope = **P1** (tier mechanism + behavioral-suite difficulty + stringent spec on launchable Go/Node/
> Python services), with P2 (Java/C# provisioning) and P3 (orchestration) sketched but deferred.
> Lead service: **currencyservice** (Node; suite + launch already work; `Money` nanos arithmetic is the
> richest correctness trap).

---

## Architectural anchors (verified during planning)

| Anchor | Location | Why it matters |
|--------|----------|----------------|
| `spec_hash()` conditional axis inclusion | `run_spec.py` (K2 `leverage_states`, K3 `role_pairs`) | The **exact pattern** the `tier` axis must follow: add to the identity dict *only when non-default* → archived spec_hashes/cell_ids stay byte-stable. |
| `cells()` nested iteration + `MatrixCell` | `run_spec.py:200-216` | Tier nests as a new innermost loop; `MatrixCell.tier` default `"baseline"` keeps baseline cells byte-identical. |
| `cell_id` / `sandbox_dir_name` segment-omission | `runner.py:64-74`, `runner.py:436-453` | Tier segment appended **only when `tier != "baseline"`** (same precedent as leverage/role). |
| Seed selection | `runner.py:~223` (`seed-{service}.json`) | Where `seed-{service}-{tier}.json` selection goes. |
| Suite registry + dispatch | `behavioral/execute.py:28-33` (`_SUITES`), `:104` (`_SUITES.get(service)`), runner `:345-351` | Where tier-aware suite selection threads in. |
| Behavioral scoring | `scoring.py:258-315` (`compute_composite`), `FUNCTIONAL_WEIGHT=0.5`, compile floor | Already per-assertion + degrade-not-zero — **no scoring rework**. |
| Language launch | `behavioral/provision.py`, `contract.py` `_DEFAULTS` (node/go only) | Node/Go launch via defaults already; **Java/C# have no strategy → always degrade** (P2/FR-22). |
| Mottainai rescore | `scripts/rescore_behavioral.py` | Re-launches persisted servers + re-runs the **current** suite for $0. **Not tier-aware today** — must be updated. |
| `expose_defects` spec field | `run_spec.py` (excluded from spec_hash) | The "unused" defect-ledger scorer is already plumbed; enabling is a flag. |

---

## Milestone M0 — Tier matrix dimension (FR-2, FR-4, FR-4a, FR-21, FR-19)

**Goal:** introduce a `tier` axis that is byte-identical to today when defaulted, mirroring the K2/K3
precedent precisely.

1. **`run_spec.py` — add the axis.**
   - Add `tier_states: Tuple[str, ...] = ("baseline",)` (open string axis, like `leverage_states`).
   - Add `_valid_tier_states` validator (non-empty, unique; **do not** restrict the value set — keep
     it open for future variants like `adversarial`).
   - `total_cells` ×= `len(tier_states)`.
   - `cells()`: add innermost `for tier in self.tier_states:` → `MatrixCell(..., tier=tier)`.
   - `spec_hash()`: **conditional inclusion** —
     `if tuple(self.tier_states) != ("baseline",): identity["tier_states"] = list(self.tier_states)`.
   - `MatrixCell`: add `tier: str = "baseline"`.
2. **`runner.py` — thread the tier.**
   - `cell_id`: append `:tier-{tier}` **only when `tier != "baseline"`**.
   - `sandbox_dir_name(...)`: add `tier="baseline"` param; append `-tier-{tier}` only when non-default.
     (Update all call sites, incl. `rescore_behavioral.py` — see M4.)
   - Seed selection: `seed = seeds_dir / f"seed-{service}-{tier}.json"` when `tier != "baseline"`,
     else `seed-{service}.json`. **Robustness (FR-4, no silent fallback):** if `tier != "baseline"`
     and the hardened seed is **absent**, classify the cell `infra_fail` with a named reason — do
     **not** silently run baseline under a hardened label (that corrupts the comparison).
   - Pass `cell.tier` into `run_behavioral_cell(...)` (signature change in M2).
3. **Aggregation/report (FR-21):** carry `tier` through `CellResult` and group baseline vs hardened in
   the markdown/JSON so the gap is visible.

**Tests (M0):**
- `tier_states=("baseline",)` ⇒ `spec_hash()`, `cells()` order, all `cell_id`s and `sandbox_dir_name`s
  **byte-identical** to a pre-tier spec (the critical backward-compat test; assert against a frozen
  fixture).
- `tier_states=("baseline","hardened")` ⇒ `total_cells` doubles; hashes differ; hardened cells carry
  the `-tier-hardened` segment; baseline cells unchanged.
- Missing hardened seed ⇒ `infra_fail`, not a mislabeled baseline run.

---

## Milestone M1 — Hardened seed generation (FR-1, FR-3, FR-8, FR-10, FR-11)

**Goal:** emit additive, byte-stable `seed-{service}.hardened.json` for the P1 services.

1. **`gen_ob_benchmark_seeds.py`:**
   - Add a per-service optional `hardened` block to the `SERVICES` registry entries (extra
     requirements text fragments + a `startup` contract where the language default doesn't already
     cover it).
   - Add `build_hardened_seed(svc, proto, proto_sha)` that reuses `build_seed` and overlays:
     - **stricter `requirements_text`** (FR-10): explicit non-happy-path requirements **within the
       fixed proto** — gRPC status codes, input validation, error semantics, idempotency,
       precision/rounding. (currencyservice: `Money` units/nanos sign+range+rounding rules,
       unsupported-currency → `INVALID_ARGUMENT`; paymentservice: idempotency, amount validation,
       expired/invalid card → explicit error.)
     - `startup` contract (FR-8) — for Node/Go this often matches the existing default; include it
       explicitly so hardened cells are self-describing.
   - Emit `seed-{service}.hardened.json`, add to `seeds-index.json` with its own sha, extend `--check`.
   - **FR-11 (parity):** keep the added-requirement *semantics* identical across languages so hardened
     stays cross-language comparable.
2. **Cross-language note:** P1 hardened set = currencyservice (Node), paymentservice (Node),
   shippingservice (Go); productcatalogservice (Go) added in M2 once its suite exists. C#/Java excluded
   until FR-22.

**Tests (M1):** hardened seeds byte-stable + `--check` clean; hardened `requirements_text` ⊃ baseline
(superset of constraints, no proto changes); `startup` present; baseline seeds + hashes **unchanged**.

---

## Milestone M2 — Tier-aware behavioral suites (FR-5, FR-6, FR-7, FR-9, FR-12)

**Goal:** raise the behavioral bar where scoring can see it, reusing the existing harness.

1. **Tier-aware dispatch (OQ-8 → decision: `tier` param).**
   - `run_behavioral_cell(seed, workdir, service, tfs, *, tier="baseline", cfg=...)`.
   - `_SUITES` values become `suite_fn(port, *, host, connect_timeout, tier="baseline")`; the suite
     runs **baseline assertions always, plus hardened assertions when `tier=="hardened"`**
     (**superset design** → coverage degrades monotonically, so the baseline-vs-hardened delta per
     model is interpretable; FR-12).
   - runner `:345-351` passes `cell.tier`.
2. **Author hardened assertions — invariant/property-based (key design choice).**
   Prefer **rate/data-independent invariants** over golden values (robust, deterministic, language-
   agnostic, hard to game, cheap to author, no embedded ECB rates):
   - **currencyservice.Convert:** X→X identity; round-trip A→B→A ≈ identity (within nanos tolerance);
     **nanos sign matches units sign**; **nanos ∈ [−999,999,999, +999,999,999]**; zero handling;
     unsupported `currency_code` → `INVALID_ARGUMENT`; `GetSupportedCurrencies` non-empty + contains
     the codes `Convert` accepts.
   - **paymentservice.Charge:** idempotency (same request → consistent handling); amount=0/negative →
     error; invalid/expired card → explicit rejection (extends the existing 3 charge probes).
3. **Scoring (FR-9):** unchanged — `compute_composite` already folds the functional term; optionally
   evaluate enabling `expose_defects` for hardened cells (flag only).

**Tests (M2):**
- `(service, tier="hardened")` dispatch resolves and runs the superset.
- **Discrimination unit test:** a checked-in **naive currency stub** (ignores nanos) ⇒ baseline suite
  passes (~1.0) but hardened suite fails the nanos/sign invariants (<1.0). Proves the assertions
  discriminate and documents the difficulty delta.
- Degrade path: hardened suite against a non-launchable target ⇒ `degraded`, not 0 (FR-32 parity).

---

## Milestone M3 — Validation + memorization signal (FR-16, FR-18, FR-21, OQ-6)

**Goal:** prove the dial widens the flagship/mid-tier gap, and report the memorization control.

1. **Cheap pre-validation ($0, before any hardened generation):** via tier-aware rescore (M4), run the
   **hardened suite against existing *baseline* persisted servers**. A happy-path baseline server
   should score lower on hardened assertions → confirms suite discrimination before spending. (Needs a
   rescore flag to set the suite tier independently of the server's generation tier.)
2. **Real validation:** run `baseline` + `hardened` × P1 services × **≥2 model cohorts** (one flagship,
   one mid/cheap). **Success metric (OQ-6):** the mean **functional-coverage** gap
   `flagship − midtier` is **larger under hardened than baseline** (compare raw functional coverage,
   *not* composite — the composite's 50% structural term dilutes the signal both tiers pass).
3. **Memorization signal (FR-16/18):** wire `contamination.py` CodeBLEU similarity-to-canonical-OB per
   `(model, service, tier)`; report the **joint** signal — high hardened coverage + **low** similarity
   = genuine skill; high coverage + **high** similarity = suspected recall.

**Tests (M3):** report contains per-tier functional coverage + gap + CodeBLEU columns; pre-validation
script runs end-to-end on a fixture batch.

---

## Milestone M4 — Mottainai/rescore tier-awareness (FR-20)

**Goal:** keep "generate once, re-score free" working for hardened runs (and enable M3 pre-validation).

1. **`scripts/rescore_behavioral.py`:**
   - Read `tier` from `cells.json` per cell; load `seed-{service}-{tier}.json`; use
     `sandbox_dir_name(..., tier=tier)`; pass `tier` into `run_behavioral_cell`.
   - Add `--suite-tier {baseline|hardened}` override so M3 can score persisted **baseline** servers
     with the **hardened** suite (decoupling suite from server generation tier).
2. **Sequencing payoff:** because rescore re-runs the *current* suite against persisted servers,
   hardened servers are generated **once** (the only spend); suite assertions are then **enriched and
   re-scored for $0**. ⇒ build M0+M1+a *minimal* M2 suite, generate once, then iterate suite richness
   freely.

**Tests (M4):** rescore round-trips a hardened fixture batch; `--suite-tier` override scores baseline
servers with hardened assertions.

---

## Deferred (out of P1)

- **P2 / FR-22 — Java & C# launch provisioning.** Add `provision.py` build/serve strategies +
  `_DEFAULTS` (gradle→jar→`java -jar`; `dotnet build`→`dotnet run`). **Surfaced by planning:**
  `adservice`'s registered suite is **dead today** (Java never launches → always degraded) — this is a
  pre-existing waste, not just a hardening gap. Minimum interim: log the dead-suite/degrade reason
  loudly instead of silent degradation.
- **P3 / FR-13–15 — orchestration with mocked deps.** Requires `run_service_sandboxed` →
  `run_services_sandboxed` (multi-launch, readiness DAG, port map, group teardown). Revisit per OQ-2.

---

## Dependency / sequencing

```
M0 (tier axis) ──► M1 (hardened seeds) ──► M2 (tier-aware suites, minimal) ──► generate hardened once
        │                                          │
        └────────► M4 (rescore tier-aware) ◄───────┘
                          │
                          ▼
                   M3 (pre-validate $0 → real validation → memorization signal)
                          │
                   …then enrich M2 assertions and rescore for $0 (iterate)
```

## Risks

- **R1 — spec_hash regression.** Mitigated by the frozen-fixture byte-identical test (M0) and copying
  the K2/K3 conditional-inclusion pattern verbatim.
- **R2 — silent mislabeled fallback** corrupting baseline-vs-hardened. Mitigated by FR-4 fail-closed.
- **R3 — suite non-determinism** (live servers, random ids). Mitigated by invariant/structural
  assertions (M2), not golden values.
- **R4 — hardened tier doesn't actually widen the gap.** Mitigated by the $0 pre-validation (M3.1)
  *before* committing to hardened generation spend.
- **R5 — rescore tier-blindness** silently scoring against baseline artifacts. Mitigated by M4.
