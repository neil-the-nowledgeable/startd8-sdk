# How to Enable the Whole-Project `tsc --noEmit` Gate (Fix #1)

**Status:** operational guide · **Date:** 2026-06-02 (rev. 2 — corrected for the cap-dev-pipe path)
**Audience:** the operator running the prime contractor against a TypeScript project (e.g. strtd8)

> **TL;DR — it depends which command you run; there are TWO mechanisms.**
>
> - **If you run the pipeline** (`startd8-cap-dlv-pipe.sh` → `run.sh` → `run-prime-contractor.sh`):
>   the whole-project `tsc --noEmit` gate (`ts-verify-gate.py`) **already runs by default**
>   after every batch and **self-provisions `npm install` + `prisma generate`** — you don't
>   set `STARTD8_TS_TYPECHECK` (it ignores that var). It is **informational** by default; to
>   make it **fail the run** on a bad verdict, export **`STARTD8_TS_GATE_STRICT=1`**. Disable
>   with `TS_VERIFY_GATE=0`.
> - **If you call the SDK directly** (`scripts/run_prime_workflow.py`, no pipeline wrapper):
>   the only whole-project `tsc` path is the **postmortem** evaluator, which **is** gated by
>   **`STARTD8_TS_TYPECHECK=1`** and needs the toolchain provisioned yourself.
>
> So for the command an operator actually runs (the pipeline), the answer is:
> **`STARTD8_TS_GATE_STRICT=1`**, not `STARTD8_TS_TYPECHECK`. Both mechanisms call the same
> engine (`ts_toolchain.run_project_typecheck`); they differ only in the on/off knob and where
> the verdict is surfaced.

---

## 1. What this gate is (and why it was "missing" in RUN-015/016)

After a batch is assembled, `prime_postmortem` can run a **real, project-level
`tsc --noEmit`** (with `prisma generate` first, so the generated Prisma client types exist)
against the whole output tree. Unlike the per-feature checks, a whole-project compile sees
**cross-file** errors — exactly the RUN-015/016 failure flavors:

- `TS2307` unresolvable imports — invented `~/lib/...` (Gap U), invented `@/components/ui/*` (Gap Y)
- wrong-library idioms — `import zod from "zod"; zod.z.object` (Gap V)
- invented external deps — `import { generateObject } from "ai"` (Gap W), `swr` (Gap Y)
- type errors un-masked once imports resolve — `TS2538`/`TS2345` (Gap X)

The engine lives in **`src/startd8/validators/ts_toolchain.py`**
(`run_project_typecheck`, `parse_tsc_output`, `typecheck_enabled`) and is wired into the
postmortem at **`src/startd8/contractors/prime_postmortem.py:_evaluate_ts_toolchain`**.

**The two mechanisms (both call `ts_toolchain.run_project_typecheck`):**

| | **Pipeline gate** `ts-verify-gate.py` | **Postmortem** `_evaluate_ts_toolchain` |
|---|---|---|
| Runs when | you use the cap-dev-pipe scripts (`run-prime-contractor.sh:549`) | `prime-post-run.py` postmortem step |
| On/off | **on by default** (`TS_VERIFY_GATE` ≠ `0`) when `package.json` exists | gated by **`STARTD8_TS_TYPECHECK`** (off by default) |
| Reads `STARTD8_TS_TYPECHECK`? | **No** — calls the engine directly | **Yes** (`typecheck_enabled()`) |
| Toolchain provisioning | **self-provisions** `npm ci`/`npm install` + `prisma generate` | you provision it yourself |
| Effect of a bad verdict | **informational** unless **`STARTD8_TS_GATE_STRICT=1`** (then fails the run) | annotates report (`FAIL:typecheck`, `tsc_<code>`) |

**Why RUN-015/016 still list it as "Fix 12":** the engine was never broken. On those runs the
gate ran **informationally** (or `UNAVAILABLE` if the toolchain wasn't provisioned) — so type
errors were reported but **did not fail the run**, and `STARTD8_TS_TYPECHECK` (the postmortem
knob) wasn't set either. Making it *enforce* is a run-config decision (`STARTD8_TS_GATE_STRICT=1`),
not a code change.

```python
# src/startd8/validators/ts_toolchain.py  — used by BOTH mechanisms
def typecheck_enabled() -> bool:  # only the POSTMORTEM path consults this
    return os.environ.get("STARTD8_TS_TYPECHECK", "").strip().lower() in ("1", "true", "yes", "on")
```
```python
# cap-dev-pipe/ts-verify-gate.py  — the PIPELINE gate; STRICT is its only env knob
def _strict_exit() -> int:
    return 1 if os.environ.get("STARTD8_TS_GATE_STRICT", "").strip().lower() in ("1","true","yes","on") else 0
```

---

## 2. Prerequisites

- **Pipeline path:** essentially none — `ts-verify-gate.py` runs `npm ci`/`npm install` +
  `prisma generate` itself, then `tsc --noEmit -p <project_root>`. You only need `npm` + `node`
  on `PATH` and a `package.json` + `tsconfig.json` + `prisma/schema.prisma` in the project
  (all true for strtd8). If `npm` is missing the gate reports `UNAVAILABLE` (never a silent pass).
- **SDK-direct path** (`run_prime_workflow.py` with no pipeline wrapper): provision yourself —
  `cd <project> && npm install` (gives `node_modules/.bin/tsc`), and ensure
  `prisma`/`prisma/schema.prisma` exist — then set `STARTD8_TS_TYPECHECK=1`.

> The engine resolves `tsc` from the project's `node_modules/.bin/tsc` (`_resolve_tsc`) and
> degrades **loudly** to `UNAVAILABLE` when absent (§5) — never a silent pass.

---

## 3. Enable it for a run

### A. The pipeline command (what an operator actually runs) — use `STARTD8_TS_GATE_STRICT`

The gate already runs; you only choose whether a type error **blocks** the run:

```bash
# from the project's .cap-dev-pipe/ — make tsc errors fail the pipeline:
STARTD8_TS_GATE_STRICT=1 ./startd8-cap-dlv-pipe.sh \
    --contractor-arg --lead-agent   --contractor-arg gemini:gemini-2.5-pro \
    --contractor-arg --drafter-agent --contractor-arg gemini:gemini-2.5-flash-lite
```

- `STARTD8_TS_GATE_STRICT=1` → a `FAIL`/`UNAVAILABLE` verdict sets the pipeline exit code.
- (default, unset) → the gate runs and **prints** the verdict + diagnostics, but does not block.
- `TS_VERIFY_GATE=0` → disable the gate entirely.
- `STARTD8_TS_TYPECHECK` has **no effect** on this path — the gate ignores it.

(Env propagates cleanly: the chain `startd8-cap-dlv-pipe.sh → run.sh → run-atomic.sh →
run-prime-contractor.sh` does no `env -i`/`unset`, and `.venv` activation preserves env vars.)

### B. The SDK-direct path — use `STARTD8_TS_TYPECHECK`

Only when you bypass the pipeline and call the workflow directly (the postmortem is then the
only `tsc` path):

```bash
STARTD8_TS_TYPECHECK=1 python3 scripts/run_prime_workflow.py ...
```

Accepted truthy values for both vars: `1`, `true`, `yes`, `on` (case-insensitive).

---

## 4. What happens when it's on

**Pipeline gate (`ts-verify-gate.py`, path A):** after the batch, prints
`── TypeScript/Prisma verification gate ──`, runs `npm ci`/`install` + `prisma generate`, then
`run_project_typecheck`, and prints `verdict: PASS|FAIL|UNAVAILABLE` with the first ~50
diagnostics. Under `STARTD8_TS_GATE_STRICT=1` a non-`PASS` verdict propagates to the pipeline
exit code (the runner adopts it as `EXIT_CODE`); otherwise it's informational.

**Postmortem (`_evaluate_ts_toolchain`, path B)** does:

1. **Skips** if `typecheck_enabled()` (`STARTD8_TS_TYPECHECK`) is false, or if the batch produced no TypeScript.
2. Runs `run_project_typecheck(project_root)` → `prisma generate` (if applicable) then
   `tsc --noEmit -p <project_root>`.
3. Parses diagnostics (`path(line,col): error TS####: msg`) into structured `TscDiagnostic`s.
4. For each feature with errors in its files:
   - records each diagnostic under `semantic_issues` with category **`tsc_<code>`** (e.g. `tsc_TS2307`);
   - sets the feature's **`verdict = "FAIL:typecheck"`** and an `error_message`.

So enabling it makes a whole-project type error **fail the feature's postmortem verdict** —
this is stronger than the advisory missing-dependency surfacing added in `integration_engine`
(see §6). That is intentional: a real `tsc` error is high-confidence.

**Outputs to look at after the run** (under `<run>/plan-ingestion/`):
- `prime-postmortem-report.json` → per-feature `semantic_issues` with `tsc_*` categories,
  and `verdict: "FAIL:typecheck"`.
- `prime-postmortem-summary.md` → human-readable roll-up.

---

## 5. Loud degradation (the safety property — FR-9)

If the toolchain is **unavailable** (no `node_modules`, no `tsc`/`prisma`), the result is
`status="unavailable"` and the postmortem records a finding like
*"TypeScript typecheck unavailable: …"* plus a warning:

> `FR-9: TS typecheck enabled but toolchain unavailable (…) — treating as non-pass`

It is **never** treated as a silent PASS (the exact deflection that let RUN-008 score 0.99).
Practically: if `npm` is missing (pipeline gate) or you forgot `npm install` (SDK-direct path),
you get a loud `UNAVAILABLE`, not a false green — and under `STARTD8_TS_GATE_STRICT=1`,
`UNAVAILABLE` also fails the run. A `timeout` status is reported the same way.

---

## 6. How this composes with the advisory missing-dependency check (#2)

- **#2 (advisory, always on during integration):** `integration_engine._warn_external_dependencies`
  surfaces *invented external dependencies* (imports not in `package.json`) as **warnings**
  during the run — it never blocks, works with no Node toolchain, and lands in the result's
  `missing_dependency_warnings`. This is the cheap, always-available signal.
- **#1 (this gate, opt-in):** the whole-project `tsc` is the **catch-all** that also confirms
  the invented dep *and* every other compile-class error, and **fails the verdict**. It needs
  the provisioned toolchain.

Run order in a real batch: deterministic generation / repair → integration (advisory #2 fires)
→ postmortem (this gate runs if enabled). Enabling #1 does not change #2.

---

## 7. Quick checklist for the next run

**Pipeline command (the usual case):**
- [ ] `npm` + `node` on `PATH`; project has `package.json` + `tsconfig.json` + `prisma/schema.prisma` (strtd8 ✓) — the gate runs `npm install` + `prisma generate` itself
- [ ] to **enforce**: `export STARTD8_TS_GATE_STRICT=1` (else the gate is informational)
- [ ] run `./startd8-cap-dlv-pipe.sh …` as usual — the gate fires after each batch
- [ ] watch for the `── TypeScript/Prisma verification gate ──` block + `verdict:` line in the run log
- [ ] do **not** rely on `STARTD8_TS_TYPECHECK` here — the pipeline gate ignores it
- [ ] `UNAVAILABLE` verdict ⇒ `npm` missing / install failed — fix and re-run

**SDK-direct only:** `cd <project> && npm install` → `export STARTD8_TS_TYPECHECK=1` → run
`run_prime_workflow.py`; then grep `prime-postmortem-report.json` for `tsc_` / `FAIL:typecheck`.

---

## 8. Reference

| Thing | Location |
|-------|----------|
| Shared engine (run / parse / resolve) | `src/startd8/validators/ts_toolchain.py` — `run_project_typecheck`, `parse_tsc_output`, `diagnostics_by_file`, `_resolve_tsc`, `_resolve_prisma` |
| **Pipeline gate (path A)** | `cap-dev-pipe/ts-verify-gate.py` (self-provisions npm; `_strict_exit` reads `STARTD8_TS_GATE_STRICT`); invoked by `cap-dev-pipe/run-prime-contractor.sh:549` |
| Postmortem (path B) | `src/startd8/contractors/prime_postmortem.py:_evaluate_ts_toolchain`; gated by `ts_toolchain.typecheck_enabled()` (sets `FAIL:typecheck`, `semantic_issues` `tsc_<code>`) |
| Env flags | **`STARTD8_TS_GATE_STRICT`** (pipeline gate: fail-the-run) · **`TS_VERIFY_GATE=0`** (pipeline gate: disable) · **`STARTD8_TS_TYPECHECK`** (postmortem path only). All ∈ {`1`,`true`,`yes`,`on`} |
| Command chain (env propagates, no scrubbing) | `startd8-cap-dlv-pipe.sh → run.sh → run-atomic.sh → run-prime-contractor.sh → {run_prime_workflow.py, prime-post-run.py, ts-verify-gate.py}` |
| Origin | RUN-008 FR-4/5/9; re-surfaced as RUN-015/016 "Fix 12" |
