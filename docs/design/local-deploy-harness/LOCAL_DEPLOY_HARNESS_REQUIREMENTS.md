# Local Deployment + Graded-Validation Harness — Requirements

**Version:** 0.3 (Post-CRP — R1 triage applied)
**Date:** 2026-06-14
**Status:** CRP R1 applied; ready for implementation
**Owner:** SDK / Summer 2026 Benchmark

---

## 0. Planning Insights (Self-Reflective Update)

> What changed between v0.1 (pre-planning) and v0.2 after stress-testing the requirements against
> the actual code. The planning pass produced 10 corrections — past the 30% bar, so v0.1 was
> appropriately premature and these were caught at doc cost, not refactor cost.

| v0.1 assumption | Planning discovery | Impact |
|-----------------|--------------------|--------|
| App lands in the "output directory" | App lands in `batch_root/{slug(model)}/workdir/` (project copy w/ generated `app/`); `output/` holds result JSONs only (`model_comparison.py:368-369`) | Input contract corrected → deploy target is `workdir/` |
| A manifest enumerates app roots | None exists — discovery = glob `batch_root/*/workdir` + reverse the model slug (`model_comparison.py:40-42`) | FR-12 batch discovery globs; join key = model slug |
| `boot_smoke.py` is in-process TestClient only | It is already **subprocess**-based; `resolve_app_target()` is reusable (`boot_smoke.py:98-138`) | FR-1 reuses it as the canonical fast path, scan as fallback |
| Entry point is always `app/main.py` | `resolve_app_target` depends on `app.yaml`, which raw LLM output may lack | FR-1 layered: manifest fast-path → bounded ASGI scan |
| Deployed mode is deployable in v1 | Deployed needs Postgres + refuses to boot without `DATABASE_URL`; installed self-bootstraps `sqlite:///./app.db` via lifespan `create_all` (`settings_renderer.py:48,70-73`) | FR-3/FR-8: v1 live-boots **installed only**; deployed → `skipped:deployed-needs-db` |
| Smoke body synthesis may already exist | None; only Prisma-typed `_SCALAR_SAMPLE`/`_sample_literal` (`test_emitter.py:46-71`) | FR-9 builds OpenAPI→body synth; prefers FK-free resource |
| `requirements.txt` is always present | It is deterministic output; with deterministic OFF, raw LLM apps may omit it | FR-2 dep-floor fallback is load-bearing, not a nicety |
| `/health` is the readiness probe | Generated apps may lack `/health`; FastAPI always serves `/openapi.json` | FR-7 probe order: `/openapi.json` → `/health` → `/` |
| DB location is irrelevant | `sqlite:///./app.db` is **CWD-relative** | FR-6/FR-13: run uvicorn with `cwd=app_root`; DB lands in throwaway space, removed on teardown |
| venv/port/poll utilities exist to reuse | None in repo (subprocess+timeout pattern reusable from `boot_smoke.py:183-194`) | Plan builds these; no requirement change |

**Resolved open questions:**
- **OQ-1 → Resolved.** Input is the per-model `workdir/` (contains generated `app/`); no manifest —
  batch mode globs `batch_root/*/workdir`.
- **OQ-2 → Resolved.** Reuse `boot_smoke.resolve_app_target()` (canonical fast path) but fork its
  TestClient boot script for a live uvicorn server.
- **OQ-3 → Resolved.** v1 live-boots `installed` mode only; `deployed` is a graded `skipped` rung.
- **OQ-4 → Resolved (scoped).** Body synth is best-effort, prefers FK-free resources, grades rather
  than fails on FK chains.
- **OQ-5 → Resolved.** `model_comparison.py` writes per-model `workdir/`+`output/` with `slug(model)`
  dir names; the deploy report joins to `comparison-report.json` by model slug.
- **OQ-6 → Resolved.** v1 runs batch **serially** to avoid port races; parallel deferred.

---

## 1. Problem Statement

The SDK can *generate* applications (deterministic `generate backend` and LLM-driven
`PrimeContractorWorkflow`) but has **no way to actually run a generated app as a live local
server**. All current "does it work" signal comes from `validators/boot_smoke.py`, which boots the
app in-process via `fastapi.testclient.TestClient` — synchronous, in-memory, no real network, no
persistent DB, and *assumes the canonical `app/main.py` layout*.

For the Summer 2026 benchmark this is a blocking gap. The benchmark runs with **deterministic +
micro-prime OFF** to measure raw model skill, so PrimeContractor outputs are **raw LLM code** that
will *not* reliably match the canonical layout. We need to deploy those varied outputs locally,
observe where they fail, and grade them — both to **compare code quality across models** and to
**feed concrete defects back into the SDK**.

| Component | Current State | Gap |
|-----------|---------------|-----|
| Live local server | None — `TestClient` in-process only | No pip-install → uvicorn → health-poll path |
| Entry-point discovery | Hardcoded `app/main.py` | LLM output varies (`main.py`, other ASGI app) |
| Dependency install | Assumes canonical `requirements.txt` | LLM output may use `pyproject`, miss deps |
| Outcome signal | Boolean boot pass/fail | Need a graded ladder with per-stage failure reasons |
| Cross-model comparison | None | No machine-readable report aggregating run outcomes |
| Isolation | Runs in SDK's own interpreter | Untrusted LLM code shares the SDK process/env |

---

## 2. Goals & Non-Goals

**Goals**
- Take a PrimeContractor run's output directory and run it as a live local server in isolation.
- Produce a **graded ladder** outcome per app: `discover → install → boot → health → smoke-CRUD`.
- Tolerate non-canonical structure; record deviations as findings rather than crashing.
- Emit a machine-readable report suitable for cross-model aggregation in the benchmark.

**Non-Goals (v1)**
- Docker/container isolation (deferred v2; intersects benchmark FR-44 untrusted-code sandbox).
- Production deployment, cloud targets, orchestration, hot-reload dev server.
- Repairing/fixing generated apps (this harness *observes and grades*, does not mutate the app).
- Multi-language deploy (Python/FastAPI only in v1; Go/Java/etc. deferred).
- Authoring real end-user content (out of scope per the four-bucket separation).

---

## 3. Requirements

### Input contract
- **FR-0** The deploy target is an **app root** = the directory containing the generated `app/`
  package (in benchmark batches this is `batch_root/{slug(model)}/workdir/`, **not** the sibling
  `output/` dir of result JSONs). A single-app invocation takes one app root; batch (FR-12) globs
  `batch_root/*/workdir`. [R1-F6] The model identity is carried by an **explicit sidecar** (FR-12),
  not reconstructed from the lossy directory slug.

### Discovery & tolerance
- **FR-1** Given an app root, **detect the ASGI entry point** in layers: (a) if `app.yaml` is present,
  reuse `boot_smoke.resolve_app_target()` (canonical fast path); (b) else probe ordered candidates
  `app/main.py:app`, `main.py:app`, `app/server.py:app`; (c) else a bounded scan (≤N `.py` files) for
  `FastAPI(` + a module-level `app` binding. Record which candidate matched and any non-canonical
  deviation as a finding.
- **FR-2** **Detect dependencies**: prefer `requirements.txt`; fall back to `pyproject.toml`
  (`[project].dependencies`, then poetry table). If neither is found, record a finding and attempt
  boot with a minimal **dep floor** (`fastapi, uvicorn[standard], sqlmodel, jinja2, python-multipart,
  pydantic-settings`). This fallback is load-bearing: with deterministic generation OFF, raw LLM
  output may omit `requirements.txt`.
- **FR-3** Detect the declared **deployment mode** by reading `app/settings.py` and calling
  `backend_codegen.drift.embedded_mode()` (the self-embedded `# startd8-mode:` header from
  deployment-mode M0). **v1 live-boots `installed` only**; a `deployed` app stops at the `boot` rung
  with `skipped:deployed-needs-db` (it requires Postgres + a `DATABASE_URL` and refuses to boot
  without one). [R1-F8/S5] Detection records a **`derivation` field** (`header` | `default` |
  `ambiguous`). A missing/garbled `settings.py` yields `mode=unknown` + a deviation finding — **not**
  a silent `installed` — because a `deployed` app mis-booted as `installed` hangs on absent Postgres
  and the failure would be wrongly attributed to the model. FR-1 entry-point detection likewise
  records its `matched_by`/confidence and emits a deviation when the bounded scan is ambiguous (more
  than one module-level `app` binding).

### Isolation & install
- **FR-4** Create a **throwaway isolated venv** per app (e.g. `python -m venv`) in a temp/work dir;
  never install the app's deps into the SDK's interpreter.
- **FR-5** Install detected deps into the venv via `pip install`; capture stdout/stderr and the exit
  code. Enforce a configurable **install timeout**. On failure, stop the ladder at the `install`
  stage and record the reason. [R1-F1/S1] **Install is the first untrusted-code-execution surface**
  (PEP 517 build backends run arbitrary code at install time, before any boot timeout applies), so:
  pass `--disable-pip-version-check`; when a `requirements.txt` is present and fully pinned, use
  `--require-hashes`/`--only-binary` where feasible; make the **build-isolation** choice explicit and
  recorded; and capture the egress fact (the dep-floor path resolves names against the configured
  index over the network). Drawing the v2/Docker line **at install, not at boot** is the key
  correction — see FR-17.

### Boot & probe
- **FR-6** Launch the app as a **uvicorn subprocess** bound to `127.0.0.1` on an
  **ephemeral free port**, using the detected entry point and the venv's interpreter, with
  **`cwd = app_root`** (the generated `sqlite:///./app.db` is CWD-relative — running from the app
  root keeps the DB inside the throwaway space). Capture the child's stdout/stderr to a log.
  [R1-S8] The free-port `bind(0)`→release→hand-off has a **reuse race**: if uvicorn fails to bind the
  chosen port, classify it as a **harness retry** (re-pick a fresh port, bounded attempts), **not** a
  model `boot=fail`. [R1-F3] `cwd` confines only the SQLite DB, **not** arbitrary `open(path,"w")`;
  run the child with `HOME`/`TMPDIR` pointed at the throwaway dir as a cheap partial mitigation —
  full FS confinement is the v2/Docker line (see FR-18).
- **FR-7** **Health-poll** until ready or timeout: probe `/health` first (app-defined readiness), then
  `/openapi.json` (framework liveness), then `/`. First 2xx → `health` stage passes. Record which
  probe answered. [R1-F10] `/openapi.json` is served by FastAPI's static schema and is **liveness, not
  readiness** — when it is the *only* answering probe, mark the rung `pass:liveness-only` (weaker than
  `pass:app-health`) so a partially-initialized app (e.g. lifespan `create_all` raised) is not scored
  a clean `health=pass`; the smoke rung (FR-9) is the authoritative readiness check. Detect early
  child exit (`proc.poll()`) and treat it as a boot failure, not a poll timeout.
- **FR-8** Enforce a **boot timeout**; on timeout or early child exit, stop the ladder at the `boot`
  stage and record captured stderr as the reason.

### Smoke-CRUD
- **FR-9** From the live `/openapi.json`, **derive a smoke-CRUD round-trip**: pick a resource
  exposing list+create (POST then GET), synthesize a minimal valid body from the OpenAPI schema,
  execute against the live server, and assert non-5xx + round-trip consistency. [R1-F4] Body
  synthesis must honor an **enumerated set of JSON-Schema features** as acceptance criteria: `$ref`
  resolution, `allOf` merge, `required` vs `nullable`, `enum` (pick first), `format`
  (date-time/uuid/email), and nested objects; behavior on `oneOf`/`anyOf`/`additionalProperties` is
  explicitly specified (pick first branch / omit). A schema feature the synthesizer cannot satisfy
  yields a typed `skipped` reason, never a malformed body counted as `fail`.
- **FR-10** Smoke-CRUD is **best-effort and graded**, not fatal. [R1-F5] Distinguish three outcomes so
  the FK-free preference's bias is **visible, not hidden** as neutral: `skipped:no-list-create-resource`
  (app genuinely exposes none), `skipped:all-resources-fk-coupled` (harness declined FK chains — a
  *harness* limitation, not a model trait), and `fail` (a derived case that errored). The aggregate
  report (FR-12) buckets these separately.

### Reporting
- **FR-11** Emit a per-app **graded result** with: highest stage reached, per-stage status
  (`pass|fail|skipped`), failure reason, matched entry point + detection derivation (FR-1/3), dep
  source, deviations, timings, and log paths. Machine-readable JSON + human summary. [R1-F9/S6]
  Include a **`harness_env` block** required to make a `fail` reproducible and distinguishable from
  harness flakiness: effective install/boot timeouts, venv Python version, resolved installed dep
  versions (`pip freeze`), pip index URL + network reachability, and the chosen ephemeral port.
  Without it, a `fail` from a tight timeout or a transient PyPI outage is indistinguishable from
  genuinely broken model code in the cross-model roll-up.
- **FR-12** Support **batch mode**: glob `batch_root/*/workdir` (fallback `*/app`), run the ladder
  **serially** (v1 — avoids ephemeral port races), and emit an aggregate report (per-app rows +
  roll-up of how many reached each rung). [R1-F6/S3] The authoritative **join key is the verbatim
  model id**, read from an explicit `deploy-manifest.json` / per-workdir `.model` sidecar written by
  `model_comparison.py` (writer-side coordination is M3). Reverse-slugging the directory name is a
  **fallback only** and logs a collision warning when two workdirs resolve to the same slug —
  `slug(model)` is non-invertible (`a/b` and `a-b` collide), so it must not silently mis-join
  `comparison-report.json`.
- **FR-13** Always **tear down** with a **no-orphan guarantee over the whole process group** [R1-F7/S4]:
  start the server in its own session/process group (`start_new_session=True`) and signal the group
  (SIGTERM→wait→SIGKILL) so grandchildren (multi-worker uvicorn, app-spawned subprocesses) are reaped;
  remove the venv/work dir (configurable `--keep` for debugging) such that even a SIGKILL/crash
  mid-`rmtree` cannot leave a half-deleted tree. No orphan processes or ports on exit, including on
  error/Ctrl-C.

### Surface
- **FR-14** Expose via the **startd8 CLI** as a new typer group (`startd8 deploy local <root>` /
  `startd8 deploy batch <dir>`), following the `cli_generate.py` group pattern. Also importable as a
  library function for the benchmark harness.

### Safety
- **FR-15** Treat generated code as **untrusted**: no install into SDK interpreter (FR-4),
  bind loopback only (FR-6), enforce all timeouts, and document the v1 trust boundary (subprocess +
  venv, *not* a kernel sandbox — that is the v2/FR-44 Docker upgrade).
- **FR-16** [R1-F2/S2] Apply configurable **resource limits** to both the pip and uvicorn child
  processes (CPU time, address-space/memory, max processes — `resource.setrlimit` via `preexec_fn` on
  POSIX) so a fork bomb or memory balloon in raw LLM output cannot take down the benchmark host. A
  limit breach is recorded as a `killed:resource-limit` rung reason, not a hang.
- **FR-17** [R1-F1/S1] Recognize **install-time arbitrary code execution + network egress** as an
  in-scope v1 threat (FR-5): the trust-boundary documentation must state that `pip install` runs
  attacker-influenced build code and reaches the package index by name, and that v1 mitigates only by
  pinning/hashes-when-available + recorded build-isolation choice — full containment is the v2/Docker
  line.
- **FR-18** [R1-F3] State the **filesystem-write blast radius** honestly: v1 confines only the SQLite
  DB (via `cwd`) and redirects `HOME`/`TMPDIR` to throwaway space (FR-6); arbitrary `open(path,"w")`
  / `shutil` writes elsewhere are **not** confined in v1, and FS confinement is the v2/Docker line.

---

## 4. Non-Requirements

- Does NOT build Docker images or run containers (v2).
- Does NOT modify, repair, or re-generate the app under test.
- Does NOT provision external databases; v1 assumes app self-bootstraps SQLite (installed mode).
- Does NOT guarantee security isolation beyond process/venv separation.
- Does NOT deploy non-Python apps in v1.

---

## 5. Open Questions

All v0.1 open questions were resolved during the planning pass — see §0 (Resolved open questions).
No open questions block implementation. Remaining *deferrals* (not blockers):

- **DEF-1** Docker/container isolation (v2; intersects benchmark FR-44 untrusted-code sandbox).
- **DEF-2** Parallel batch execution with a port-lease pool (v1 is serial).
- **DEF-3** Live-booting `deployed`-mode apps against an ephemeral Postgres.
- **DEF-4** Multi-language deploy (Go/Java/Node/C#); v1 is Python/FastAPI only.

---

*v0.2 — Post-planning self-reflective update. 1 requirement added (FR-0 input contract), 6 requirements
narrowed/corrected (FR-1,2,3,6,7,12), 6 open questions resolved, 4 deferrals recorded. Paired with
LOCAL_DEPLOY_HARNESS_PLAN.md v1.0.*

*v0.3 — Post-CRP R1. All 10 F-suggestions accepted (see Appendix A). 3 safety requirements added
(FR-16 resource limits, FR-17 install-time ACE/egress, FR-18 FS blast radius); FR-0,3,5,6,7,9,10,11,12,13
hardened. Key correction: the untrusted-code line is drawn at **`pip install`**, not boot. Paired with
LOCAL_DEPLOY_HARNESS_PLAN.md v1.1.*

---

## Appendix: Iterative Review Log (Applied / Rejected Suggestions)

This appendix is intentionally **append-only**. New reviewers (human or model) add suggestions to Appendix C; once validated, the orchestrator records the final disposition in Appendix A (applied) or Appendix B (rejected with rationale). **Do not delete A/B** — they are the cross-model memory that stops later reviewers from re-proposing settled or rejected ideas.

### Reviewer Instructions (for humans + models)

- **Before suggesting changes**: Scan Appendix A and Appendix B first. Do **not** re-suggest items already applied or explicitly rejected.
- **When proposing changes**: Append a `#### Review Round R{n}` block under Appendix C (n = highest existing round + 1, or 1), with unique suggestion IDs `R{n}-S{k}` (plan) / `R{n}-F{k}` (requirements).
- **When endorsing prior suggestions**: If you agree with an untriaged item from a prior round, list it in an **Endorsements** section instead of restating it. Multi-reviewer endorsements raise triage priority.
- **When validating (orchestrator)**: For each suggestion, append a row to Appendix A (applied) or Appendix B (rejected) referencing the suggestion ID.
- **If rejecting**: Record **why** (specific rationale) so future reviewers don't re-propose the same idea.

### Appendix A: Applied Suggestions

| ID | Suggestion | Source | Implementation / Validation Notes | Date |
|----|------------|--------|-----------------------------------|------|
| R1-F1 | pip install build-isolation decision + egress note + pinning | R1 | Merged into FR-5; new FR-17 names install-time ACE/egress as in-scope v1 threat | 2026-06-14 |
| R1-F2 | Resource limits (rlimits) on pip + uvicorn children | R1 | New FR-16; `killed:resource-limit` rung reason | 2026-06-14 |
| R1-F3 | State FS-write blast radius (cwd confines only the DB) | R1 | New FR-18; FR-6 redirects HOME/TMPDIR to throwaway as partial mitigation | 2026-06-14 |
| R1-F4 | Enumerate mandatory OpenAPI/JSON-Schema features for body synth | R1 | Merged into FR-9 ($ref/allOf/required/nullable/enum/format/nested + oneOf/anyOf behavior) | 2026-06-14 |
| R1-F5 | Split `skipped:no-crud-resource` to expose FK-free bias | R1 | Merged into FR-10 (3 outcomes: no-list-create / all-fk-coupled / fail) | 2026-06-14 |
| R1-F6 | Explicit join key (sidecar), reverse-slug fallback only | R1 | Merged into FR-0 + FR-12; writer-side in plan M3 | 2026-06-14 |
| R1-F7 | Process-group teardown / no-orphan guarantee | R1 | Merged into FR-13 (start_new_session + group signal; crash-safe rmtree) | 2026-06-14 |
| R1-F8 | Detection derivation/confidence; mode=unknown not silent installed | R1 | Merged into FR-3 (+ FR-1 ambiguity deviation); surfaced in FR-11 result | 2026-06-14 |
| R1-F9 | `harness_env` block for reproducibility | R1 | Merged into FR-11 (timeouts, py version, pip freeze, index+reachability, port) | 2026-06-14 |
| R1-F10 | `/openapi.json` liveness≠readiness; weaken health rung | R1 | Merged into FR-7 (probe `/health` first; `pass:liveness-only` label; smoke is authoritative) | 2026-06-14 |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none yet) |  |  |  |  |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — claude-opus-4-8-1m — 2026-06-15

- **Reviewer**: claude-opus-4-8-1m
- **Date**: 2026-06-15 00:30:00 UTC
- **Scope**: Requirements review (F-prefix). Sponsor focus: untrusted-code trust boundary, OpenAPI→body-synth brittleness, input-contract/reverse-slug ambiguity, teardown/no-orphan, reuse correctness, benchmark signal integrity.

##### Sponsor focus asks (answered before standard suggestions)

**Ask 1 — Untrusted-code trust boundary honest & adequate for v1?**
- **Summary answer:** Honestly stated, but **not adequate** without a few cheap v1 mitigations the requirements do not yet mandate.
- **Rationale:** FR-15 + §Non-Requirements correctly disclaim kernel isolation and point to v2/FR-44. But venv+subprocess+loopback leaves real v1 holes the focus file names: `pip install` of attacker-named/typosquatted deps performs **arbitrary network egress + arbitrary code execution at build time** (setup.py / PEP 517 build hooks) *before* any boot timeout applies; a malicious app can write **anywhere the SDK user can write** (only the SQLite DB is CWD-confined, not arbitrary `open(...,"w")`); and no `ulimit`/resource cap means a fork bomb or memory balloon takes down the benchmark host. None of FR-4/5/6/15 bound these.
- **Assumptions / conditions:** Runs on a developer/benchmark machine with the SDK user's full FS+network privileges; deterministic OFF ⇒ apps are raw LLM output.
- **Suggested improvements:** see R1-F1 (pip build-isolation/`--no-build-isolation` decision + egress note), R1-F2 (ulimit/resource caps), R1-F3 (FS-write blast radius statement). Drawing the v2/Docker line *at pip install* (not at boot) is the key correction.

**Ask 2 — OpenAPI→body synthesis robust enough; does FK-free bias the signal?**
- **Summary answer:** Partial — the FK-free preference is pragmatic but **biases the quality signal**, and the required schema-feature coverage is under-specified.
- **Rationale:** FR-9 says "synthesize a minimal valid body from the OpenAPI schema" without enumerating which JSON-Schema features must be honored (`$ref` resolution, `allOf`/`oneOf`, `required` vs `nullable`, `enum`, `format`, nested objects, `additionalProperties`). FR-10's `skipped:no-crud-resource` collapses two very different cases: "app legitimately has no list+create resource" vs "every resource is FK-coupled so we declined" — an app whose only resources are FK-coupled always scores `skipped`, which **reads as neutral** in cross-model aggregation when it is actually a harness limitation, not a model trait.
- **Assumptions / conditions:** Benchmark aggregates `skipped` distinctly from `pass`/`fail`; reverse FK chains are common in generated schemas.
- **Suggested improvements:** see R1-F4 (enumerate mandatory schema-feature coverage as acceptance criteria), R1-F5 (split `skipped:no-crud-resource` from `skipped:all-resources-fk-coupled` so the bias is visible, not hidden).

**Ask 3 — Reverse-slug join lossy/ambiguous; carry the key explicitly?**
- **Summary answer:** Yes — reverse-slug is lossy and should not be the join key of record.
- **Rationale:** FR-0/FR-12 reconstruct the model name by reversing `slug(model)` off a directory name. Slugging is generally **non-invertible** (e.g. `claude/sonnet` and `claude-sonnet` both slug to `claude-sonnet`; case folding; provider prefixes). Two providers' models can collide on one slug → silently wrong left-join to `comparison-report.json`, corrupting the benchmark comparison.
- **Assumptions / conditions:** `model_comparison.py` already knows the true model string at write time.
- **Suggested improvements:** see R1-F6 — require the writer to drop a `deploy-manifest.json` (or per-workdir `.model`) carrying the verbatim model id, and make reverse-slug only a *fallback* with a logged warning on collision.

**Ask 4 — Teardown/no-orphan sufficient (FR-13)?**
- **Summary answer:** Directionally right, but FR-13 under-specifies the leak paths the focus file calls out.
- **Rationale:** FR-13 says "kill the uvicorn child" — but uvicorn with `--workers>1` or an app that spawns its own subprocesses/threads leaves grandchildren that a single `proc.kill()` orphans. SIGKILL races (DB/tmp handle still open on Windows; tmp dir half-removed on crash) are not addressed. Signal handling is mentioned in the plan but FR-13 gives no testable guarantee.
- **Suggested improvements:** see R1-F7 (process-group kill + grandchild reaping as acceptance criterion).

**Ask 5 — Reuse correctness for non-canonical apps?**
- **Summary answer:** Partial — FR-1/FR-3 reuse points can *silently mis-detect*, which is the dangerous failure.
- **Rationale:** FR-3 calls `embedded_mode()` on raw `app/settings.py`; if that file is missing/garbled the requirement says "default `installed`" — but a truly `deployed` app mis-detected as `installed` will then be live-booted, hang on a missing Postgres, and surface as a `boot=fail` *attributed to the model* rather than a harness mis-detection. Same risk class as FR-1's bounded scan picking the wrong `app =` binding.
- **Suggested improvements:** see R1-F8 (require mode/entry-point detection to record a *confidence/derivation* field and treat ambiguous detection as a deviation finding, not a silent default).

**Ask 6 — Signal integrity: is a `fail` attributable to the model, not harness flakiness?**
- **Summary answer:** Not yet — the result schema (FR-11) does not capture enough environment to make a `fail` reproducible.
- **Rationale:** FR-11 lists timings + reasons but not the **timeout values used, venv python version, pip index/network status, resolved dep versions, or port** — so a `boot=fail` from a too-tight timeout or a transient PyPI outage is indistinguishable from genuinely broken model code in the aggregate. That confounds the entire cross-model comparison.
- **Suggested improvements:** see R1-F9 (record harness environment + effective timeouts in every LadderResult), and plan-side R1-S6.

##### Numbered suggestions

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F1 | Security | critical | Add a requirement that `pip install` runs with an explicit build-isolation decision and an egress note: state whether PEP 517 build backends are allowed to run (they execute arbitrary code at install time), and record that install performs outbound network to the configured index. At minimum mandate a pinned/`--require-hashes`-capable path when deps come from `requirements.txt`, and document that the dep-floor install (FR-2) reaches PyPI by name. | FR-15 disclaims kernel isolation but the **install step is the first arbitrary-code-execution surface** and fires before any boot timeout; "untrusted code" that never boots can still execute via a malicious `setup.py`/build hook. | New FR under "Safety" or extend FR-5/FR-15 | Unit: assert pip invocation includes the chosen isolation flags; doc check: trust-boundary section names install-time ACE. |
| R1-F2 | Security | high | Require configurable **resource limits** on the uvicorn child and pip subprocess (CPU time, address-space/memory, max processes via `resource.setrlimit`/`preexec_fn` or equivalent) so a fork bomb or memory balloon in raw LLM output cannot take down the benchmark host. | FR-15 enumerates venv+loopback+timeouts but **no resource caps**; the focus file explicitly names fork bombs / resource exhaustion as in-scope v1 threats. | New FR under "Safety"; reference from FR-6 | Integration: deploy an app that spawns N processes / allocates M GB; assert the harness caps it and records the kill reason rather than hanging. |
| R1-F3 | Security | high | State the **filesystem write blast radius** explicitly: FR-6's `cwd=app_root` only confines the *SQLite DB*, not arbitrary `open(path,"w")`/`shutil` calls in the generated app, which can write anywhere the SDK user can. Either accept and document this (v1) or constrain via a dedicated tmp HOME/`TMPDIR` and a note that FS confinement is the v2/Docker line. | FR-6 implies confinement ("DB lands in throwaway space") that does not extend to arbitrary FS writes; readers will over-trust the boundary. | FR-6 note + FR-15 | Doc check: FR-15 enumerates which writes are confined vs not; integration: app writing to `$HOME/poc` is observed (documented limitation) or blocked. |
| R1-F4 | Validation | high | Enumerate the **mandatory OpenAPI/JSON-Schema features** body synth must honor as acceptance criteria: `$ref` resolution, `allOf` merge, `required` vs `nullable`, `enum` (pick first), `format` (date-time/uuid/email), nested objects, and explicit behavior on `oneOf`/`anyOf`/`additionalProperties`. Today FR-9 says only "synthesize a minimal valid body." | Without an enumerated contract, "valid body" is untestable and synth robustness (the riskiest correctness surface) cannot be graded or regression-tested. | FR-9 | Unit: fixture OpenAPI exercising each feature; assert a schema-valid body is produced or a typed `skipped` reason is emitted. |
| R1-F5 | Data | high | Split FR-10's `skipped:no-crud-resource` into two reasons: `skipped:no-list-create-resource` (app genuinely exposes none) vs `skipped:all-resources-fk-coupled` (harness declined FK chains). Collapsing them **hides the FK-free bias** in cross-model aggregation. | A model whose only resources are FK-coupled scores `skipped` identically to a model with no CRUD at all — the benchmark cannot tell harness limitation from model trait. | FR-10 | Verify the aggregate report (FR-12) reports the two reasons in separate buckets. |
| R1-F6 | Data | high | Require an **explicit join key** carried with each workdir (e.g. a `deploy-manifest.json` or `<workdir>/.model` written by `model_comparison.py`, or a `model` field in the result) instead of reconstructing it by reversing `slug(model)`. Reverse-slug is non-invertible and can collide across providers, silently corrupting the left-join to `comparison-report.json`. | FR-0/FR-12 make a lossy directory-name slug the join key of record for the entire benchmark comparison. | FR-0 and FR-12 | Unit: two distinct model ids that slug identically; assert the explicit key disambiguates and reverse-slug-only path logs a collision warning. |
| R1-F7 | Risks | high | Strengthen FR-13 from "kill the uvicorn child" to a **no-orphan guarantee over the process group**: spawn the server in its own session/process group and kill the group (SIGTERM→SIGKILL) so grandchildren (extra uvicorn workers, app-spawned subprocesses) are reaped; guarantee tmp-dir removal even on SIGKILL/crash. | FR-13 as written orphans grandchildren and says nothing about partial tmp cleanup; the focus file names exactly these leak paths. | FR-13 | Integration: app spawns a child process and binds an extra port; after teardown assert zero processes in the group and the port is free. |
| R1-F8 | Risks | medium | Require detection steps (FR-1 entry point, FR-3 mode) to record a **derivation/confidence field** and treat ambiguous results as a deviation finding rather than a silent default — specifically, a missing/garbled `app/settings.py` must yield `mode=unknown` (graded), not silently `installed`, when signals conflict. | FR-3's silent "default installed" mis-detects a `deployed` app as `installed`, live-boots it, and the resulting hang is misattributed to the model — a benchmark-corrupting silent failure. | FR-1 and FR-3 | Unit: garbled settings.py ⇒ result carries `mode_derivation` + deviation, not a clean `installed`. |
| R1-F9 | Validation | high | Add to FR-11's result schema the **harness environment + effective parameters** required to make a `fail` reproducible: effective install/boot timeouts, venv Python version, resolved/installed dep versions (pip freeze), pip index URL + whether network was reachable, and the chosen ephemeral port. | FR-11 records timings/reasons but not the environment; a `fail` from a tight timeout or a PyPI blip is then indistinguishable from broken model code, confounding the cross-model comparison. | FR-11 | Schema test: LadderResult includes env block; reproduce a `boot=fail` from a forced 1ms timeout and confirm it is distinguishable from a real failure in the report. |

##### Stress-test / adversarial pass

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F10 | Risks | medium | FR-7's probe order (`/openapi.json` → `/health` → `/`) can produce a **false `health=pass`**: a partially-initialized app serves `/openapi.json` from FastAPI's static schema before the lifespan `create_all` finishes (or while it errors), so `health` passes on an app whose DB layer is dead. Require that when `/openapi.json` is the answering probe, smoke-CRUD failure be reported as a *boot/init* concern, not only a smoke concern — or probe `/health` first when present. | `/openapi.json` is served by the framework, not the app's readiness; treating it as readiness inflates the `health` rung for broken apps and muddies the model signal. | FR-7 (and interaction with FR-9) | Integration: app whose lifespan raises during `create_all` but still imports; assert it does not score `health=pass` cleanly (records the init failure). |
