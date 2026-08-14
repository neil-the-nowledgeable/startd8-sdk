# Navigator Dogfood — Pilot Improvement Loop

**Date:** 2026-08-14 · **Scope:** improve the dogfood navigator (REQ-01 rendered as Nodes) one
requirement at a time, measurably and repeatably. Companion to `TOP_DOWN_IMPROVEMENT_PLAN.md` §6
(operating recipe) and §7 (architect acceptance test).

## Pilots (confirmed trio, causal order)

The three were chosen because the dogfood render exposed a **grounding-fidelity chain**, not
cosmetic nits — each is self-referential (the capability improving itself) and each metric moves:

| Order | FR | What it drives | Baseline `pilot_score` |
|-------|-----|----------------|------------------------|
| 1 | **FR-6** — det-req source / extractor | root fidelity: multiple Lives per FR + real `fr_health` | 0.65 |
| 2 | **FR-4** — default confidence | 0.6→0.9 once the extractor feeds code+test | 0.50 |
| 3 | **FR-8** — app-path byte identity | honest status: built+tested yet shown *spec* (under-cites evidence) | 0.20 |

FR-6 feeds FR-4 feeds the FR-8 outcome — improve in that order.

## The 5-step loop (per FR, repeatable)

Driver: `scripts/navigator_pilot_loop.py`. State lives in `_pilot/ledger.{json,md}` (auto-generated).

```
baseline  →  diagnose  →  [apply smallest fix]  →  verify  →  record
```

1. **Baseline** — snapshot the FR's current metrics + score.
   ```bash
   python3 scripts/navigator_pilot_loop.py FR-6
   ```
   Records a `baseline` entry and prints the metrics, `cruft_lint` line, and the **TOP GAP**.

2. **Diagnose** — the script already ran the mechanical gate (render → `cruft_lint` → evidence
   resolve → top-gap heuristic). For a fresh-eyes structural pass, run `/cruft-audit` on
   `_pilot/FR-6.html` with a *different* agent/model (the author is blind to their own cruft).
   Confirm the single highest-value gap to attack.

3. **Improve** — apply the **smallest** fix that closes that gap. It may live in:
   - the **extractor** (`navigator/det_req.py`, `sources_requirements.py`) — e.g. capture *all*
     Lives per FR, compute `fr_health`;
   - the **confidence** derivation (`navigator/models.py` `default_confidence`);
   - the **renderer** (`wireframe_view/`, `wireframe/`);
   - or the FR's **own evidence text** in `REQ-01` (add the missing `Lives:`/`Approve?:`).
   Keep it **behaviour-preserving for the other 9 FRs** — the byte-identity + determinism tests
   are the guard (`pytest tests/unit/wireframe/ tests/unit/navigator/`).

4. **Verify** — re-run in verify mode; the script computes the before→after delta and asserts the
   score moved the right way.
   ```bash
   pytest tests/unit/navigator/ tests/unit/wireframe/ -q      # no regression
   python3 scripts/navigator_pilot_loop.py FR-6 --verify      # delta vs baseline
   ```

5. **Record** — the verify pass appends to the ledger (`_pilot/ledger.md` renders the trend). When
   an FR reaches `pilot_score == 1.0` and `TOP GAP → glance-approvable ✓`, promote it as an
   exemplar of a well-grounded requirement and move to the next pilot.

`python3 scripts/navigator_pilot_loop.py --status` shows all three at a glance.

## `pilot_score` (the moving number)

Composite in `[0,1]` over the glance-approvability signals the architect test cares about:

| Signal | Weight | Earns it when |
|--------|-------:|---------------|
| status grounded/built | 0.30 | not spec/unknown |
| confidence ≥ 0.9 | 0.20 | code+test Lives (FR-4 rubric) |
| all Lives resolve | 0.20 | every `git:sha:path` exists on disk |
| `fr_health` is not a dishonest done-claim | 0.15 | `!= "unknown"` — spec-time `n/a` is honest and earns it; only a done-claim citing no evidence fails |
| has APPROVE? prompt | 0.15 | per-item sign-off lights up |

## Git cadence (per the standing rule)

Each pilot iteration is a self-contained change: branch → commit → **merge to local `main` if 100%
safe** (tests green, byte-identity holds, disjoint from others' in-flight work) → **return the
primary checkout to `main`**. Do not push to `origin/main` unilaterally when the local base carries
other agents' unpushed work — surface it instead.
