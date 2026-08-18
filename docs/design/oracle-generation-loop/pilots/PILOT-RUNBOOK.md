# OL-EB-1 Pilot Runbook — `startd8 build-to-spec` (the oracle-generation loop)

**Pilot id:** OL-EB-1 — the first **real-LLM** validation of the oracle-generation loop.
**Worktree:** `~/Documents/dev/s8-pilot` (branch `feat/oracle-loop-pilot`, off `main`).
**Artifacts (this dir):**
- `REQ-oracle-loop-dryrun-emailpy.md` — the **$0** oracle-rung dry-run spec (checked-against email-py).
- `REQ-oracle-loop-pilot-todo.md` — the **generated-from** OL-EB-1 pilot spec (a tiny todo/cart API).

> **The two-phase plan.** Phase 1 is a **$0** proof that the deploy→boot→probe **oracle rung** works
> against a real backend_codegen app — no Prime, no LLM spend. Only after phase 1 is green do we
> spend on phase 2, the real-LLM loop. Never run phase 2 before phase 1 passes: a broken rung would
> burn budget grading against a harness bug, not a model.

---

## Phase 1 — $0 dry-run (oracle rung only, NO Prime, NO LLM)

**Goal:** prove `run_oracle` / `deploy_app_local(..., oracle_enabled=True)` boots the real
`fixtures/otel-demo/email-py/` app and grades its runnable `Verify:` clauses. This validates the
**deploy + probe + one-shot** machinery independently of generation.

**Spec:** `REQ-oracle-loop-dryrun-emailpy.md` — 7 FRs, classification confirmed via
`oracle_loop.grammar.parse_verify_clause`: 5 `service` probes + 1 `pytest` one-shot + 1 prose
residue → **coverage 6/7 ≈ 0.86**. All 5 probes hit real routes in `app/{health.py,routers.py}`
(`GET /health`, `GET /health/live`, `GET /orderconfirmation/`, `POST /orderconfirmation/`,
`GET /orderconfirmation/{missing} -> 404`).

**Driver (a small python script calling the harness directly — no CLI spend):**

```python
# phase1_dryrun.py — $0; boots the real email-py app and runs the ORACLE rung.
from pathlib import Path
from startd8.deploy_harness import deploy_app_local

SDK  = Path("~/Documents/dev/startd8-sdk").expanduser()
APP  = SDK / "fixtures/otel-demo/email-py"
SPEC = Path(__file__).parent / "REQ-oracle-loop-dryrun-emailpy.md"

result = deploy_app_local(APP, spec_path=SPEC, oracle_enabled=True)
for fr_id, v in sorted(result.oracle_verdicts.items()):
    print(f"{fr_id:6} {v.kind:9} {v.verdict:5} {v.reason}")
```

Run it from the SDK root so imports resolve:

```bash
cd ~/Documents/dev/startd8-sdk
PYTHONPATH=src python3 ~/Documents/dev/s8-pilot/docs/design/oracle-generation-loop/pilots/phase1_dryrun.py
```

(Alternatively call `oracle_loop.runner.run_oracle(SPEC, APP, live_port=<port>)` against an
already-booted instance to isolate the probe path from the venv/deploy path.)

**Phase-1 pass criteria (all $0):**
- The 5 `service` probes resolve `PASS` (the app boots; every probed route exists and returns the
  stated status — including the `404` for a missing row).
- The `pytest tests/test_health.py -q` one-shot resolves `PASS` (or is reported honestly if that test
  file isn't present in the fixture — a `no_fitness`/error surface is itself a valid harness finding).
- FR-7 lands in the **residue** (`assertion`), not the fitness — proving the coverage denominator and
  human-gate split are wired.
- `rung_status` = `runnable fitness passed`; `compute_coverage` reports `runnable=6 total=7`.

**If phase 1 is red:** it's a **harness** bug (deploy/boot/probe), not a model failure — fix before
spending. This is the whole point of the $0 gate.

---

## Phase 2 — real-LLM OL-EB-1 run (generate → oracle → regenerate)

**Goal:** does a **live cheap model** CONVERGE under oracle feedback, and at what **$**? This is the
generated-from run over `REQ-oracle-loop-pilot-todo.md`.

**Spec shape (why it discriminates):** 7 FRs, **6 runnable** (coverage ≈ 0.86). FR-1..FR-4 are plain
CRUD a cheap model should one-shot. **FR-5 (computed checkout `total`)** is deliberately
under-specified/ambitious — a request-time derivation, not a stored column — so iteration-1 plausibly
fails the ORACLE rung (wrong/missing `total`, a 422, or a 500). **FR-6 (empty-cart → 400)** is a
second convergence lever (unhandled empties tend to 500 on a first draft). On failure the loop renders
structured feedback (`build_feedback`: intent + probe + observed-vs-expected + assertion_text) and
re-arms the feature for Prime's regen branch (`process_feature`, `GENERATED` + `error_message`) — NOT
`repair/`. **Convergence across iterations — not a first-pass green — is the evidence the regen wire
fires (FR-4).**

**Enable the capability (default-OFF, FR-11) and run:**

```bash
export STARTD8_ORACLE_LOOP_ENABLED=1        # FR-11 gate; without it the loop refuses (cause=disabled)

cd ~/Documents/dev/startd8-sdk
doppler run -p startd8 -c dev -- startd8 build-to-spec \
  --spec ~/Documents/dev/s8-pilot/docs/design/oracle-generation-loop/pilots/REQ-oracle-loop-pilot-todo.md \
  --max-iterations 4 \
  --max-cost-usd 3.00 \
  --min-coverage 0.6 \
  --out ~/Documents/dev/s8-pilot/docs/design/oracle-generation-loop/pilots/ol-eb-1-report.json
```

- `--max-iterations 4` — enough rounds for the FR-5/FR-6 regen to land without runaway spend.
- `--max-cost-usd 3.00` — **cumulative** fail-closed budget across all iterations (tune to model).
- `--min-coverage 0.6` — below the 0.86 the spec provides, so the floor gate is armed but not tripped.
- Exit code: `0` iff `terminal_cause == pass`; non-zero otherwise (the cause is the diagnostic).

Because the harness is Mottainai (persist-then-rescore in spirit), keep `--out` so the run's
per-FR verdicts and cost are durable for the go/no-go read below.

---

## What to measure

Read these from the per-iteration telemetry (`_emit_iteration`, `get_logger` → Loki) and the terminal
`ol-eb-1-report.json` (`OracleReport`):

| Signal | Source | What "good" looks like |
|--------|--------|------------------------|
| **Convergence curve** | `failing_count` per iteration (telemetry `verdict_deltas`) | monotone-decreasing; FR-5/FR-6 flip `newly_passing` by the final round |
| **Cost curve** | `cumulative_cost_usd` per iteration | converges under `--max-cost-usd`; note $ at the iteration that first passes |
| **Coverage** | `report.coverage` (`runnable_frs/total_frs`) | 6/7 ≈ 0.86, stable across iterations (coverage is spec-fixed, not model-fixed) |
| **Per-FR verdict deltas** | `report.verdicts[*].{verdict,reason}` + `verdict_deltas` | CRUD FRs green early; FR-5/FR-6 green only after a regen round (proves feedback, not luck) |
| **Terminal cause** | `report.terminal_cause` | `pass` = converged; `max_iterations`/`budget`/`stall` = did not converge (still a valid result) |
| **Residue** | `report.coverage.residue_fr_ids` | FR-7 held for human gate, never counted as fitness |
| **spec_satisfied** | `report.spec_satisfied` | expected **False** (FR-7 Goodhart gate: `assertion_confirmed` unreviewed) even on a fitness pass |

**Convergence is proven** iff at least one runnable FR is `FAIL` in an early iteration and `PASS` in a
later one with the loop's structured feedback in between — i.e. the regen wire (FR-4) demonstrably
moved the model, distinct from a first-pass one-shot.

---

## Go / No-Go read

**GO (loop is viable at cheap-model tier)** iff, over the phase-2 run:
1. **Phase 1 was green first** ($0 rung proven on the real email-py app), AND
2. the live model **converged** — `terminal_cause == pass` with FR-5 (and ideally FR-6) flipping from
   FAIL→PASS across a regen round (not a lucky iteration-1 green), AND
3. it converged **within a defensible $** — record the total `cumulative_cost_usd` and the iteration
   count; a GO wants convergence well under `--max-cost-usd` with the marginal per-iteration cost
   trending down or flat.

**NO-GO / iterate** if the terminal cause is `stall` (feedback didn't move the model — inspect whether
`build_feedback` carried the observed-vs-expected the model needed), `max_iterations`/`budget`
(convergence too slow/expensive at this tier — try a stronger model or a less ambitious FR-5), or
`no_fitness`/`coverage_below_floor` (a spec/grammar authoring bug — re-check the a1 clauses parse and
classify as runnable).

**The headline the pilot answers:** *does a live model converge under the oracle feedback, and at what
$?* Phase 1 proves the rung is honest for free; phase 2 puts a real model against it and prices the
convergence.
