# Local Deployment + Graded-Validation Harness — Implementation Plan

**Version:** 1.1 (post-CRP R1; paired with Requirements v0.3)
**Date:** 2026-06-14
**Status:** CRP R1 applied — ready for implementation

---

## 0. Planning Discoveries (feed §0 of the requirements)

| v0.1 assumed | Planning revealed | Impact |
|--------------|-------------------|--------|
| App lands in the "output directory" | App lands in `batch_root/{slug(model)}/workdir/` (project copy w/ generated `app/`); `output/` holds result JSONs only (`model_comparison.py:368-369`) | Fix input contract; deploy target = `workdir/` |
| A manifest enumerates app roots | None exists — discovery is glob `batch_root/*/workdir` + reverse-slug (`model_comparison.py:40-42`) | Batch mode globs; join key = model slug |
| `boot_smoke.py` is in-process TestClient | It's already **subprocess**-based; `resolve_app_target()` reusable, boot script uses TestClient internally (`boot_smoke.py:98-138, 39-65`) | Reuse `resolve_app_target` as fast path; fork the boot script for a live server |
| Entry point = `app/main.py` | Canonical, but `resolve_app_target` depends on `app.yaml`; raw LLM output may lack it | Layer: manifest fast-path → bounded ASGI scan fallback |
| Deployed mode is deployable in v1 | Deployed needs Postgres + refuses to boot without `DATABASE_URL`; installed self-bootstraps `sqlite:///./app.db` via lifespan `create_all` (`settings_renderer.py:48,70-73`) | v1 live-boots **installed only**; deployed → `boot=skipped:deployed-needs-db` |
| Smoke body synth might exist | None; only Prisma-typed `_SCALAR_SAMPLE`/`_sample_literal` (`test_emitter.py:46-71`) | Build OpenAPI→body synth; prefer FK-free resource |
| `requirements.txt` always present | It's deterministic output; deterministic OFF ⇒ raw LLM apps may omit it | FR-2 dep-floor fallback is load-bearing |
| `/health` is the readiness probe | Generated apps may not expose `/health`; FastAPI always serves `/openapi.json` | Probe order: `/openapi.json` → `/health` → `/` |
| venv/port/poll utilities exist | None in repo; subprocess+timeout pattern reusable (`boot_smoke.py:183-194`) | Build venv/free-port/HTTP-poll helpers |
| DB location irrelevant | `sqlite:///./app.db` is **CWD-relative** | Run uvicorn with `cwd=app_root`; DB lands in throwaway space, removed on teardown |

These exceed the 30% revision bar → requirements were appropriately premature; corrections captured at doc cost.

---

## 1. Module layout

```
src/startd8/deploy_harness/
  __init__.py          # public API: deploy_app_local(), deploy_batch(), LadderResult
  discovery.py         # FR-1/2/3: entry-point detect, dep detect, mode detect
  venv_runner.py       # FR-4/5: throwaway venv + pip install (subprocess + timeout)
  server.py            # FR-6/7/8: uvicorn subprocess, free port, health-poll, teardown
  smoke.py             # FR-9/10: OpenAPI → body synth → live CRUD round-trip
  ladder.py            # FR-11: LadderResult model + stage orchestration
  batch.py             # FR-12: glob workdirs, run each, aggregate + join by model slug
src/startd8/cli_deploy.py   # FR-14: `startd8 deploy local|batch` typer group
tests/integration/test_deploy_harness.py   # slow/integration, importorskip
```

Rationale: a dedicated package (not folded into `validators/`) — this is an *orchestrator over a live
process*, distinct from `validators/`'s in-process gates. Keeps the untrusted-code boundary explicit.

## 2. Per-requirement steps

- **FR-1 (entry point)** — `discovery.detect_entrypoint(root)`:
  1. If `app.yaml` present → reuse `boot_smoke.resolve_app_target()` (canonical fast path).
  2. Else probe ordered candidates: `app/main.py:app`, `main.py:app`, `app/server.py:app`.
  3. Else bounded scan (≤N `.py` files) for `FastAPI(` + module-level `app =`/`app:FastAPI`.
  Return `EntryPoint(module, attr, matched_by, deviation?)`. Deviation recorded as a finding.

- **FR-2 (deps)** — `discovery.detect_deps(root)`: prefer `requirements.txt`; else parse
  `pyproject.toml` (`[project].dependencies`, then poetry table); else `DepFloor` =
  `{fastapi, uvicorn[standard], sqlmodel, jinja2, python-multipart, pydantic-settings}` + finding.

- **FR-3 (mode)** — `discovery.detect_mode(root)`: read `app/settings.py`, call
  `backend_codegen.drift.embedded_mode()`. **[R1-S5]** Return `(mode, derivation)` where derivation ∈
  `{header, default, ambiguous}`; missing/garbled settings ⇒ `mode=unknown` + deviation finding (not
  silent `installed`). `detect_entrypoint` likewise records `matched_by` and flags multi-binding
  ambiguity. Deployed → flag for FR-8 skip.

- **FR-4/5 (venv+install)** — `venv_runner.create_and_install(deps, workdir, timeout)`:
  `python -m venv <tmp>/venv` **outside** the app root; `<venv>/bin/pip install ...`; capture
  out/err/rc; `install` rung fails on rc≠0 or timeout. (Reuse subprocess+TimeoutExpired pattern.)
  **[R1-S1]** Treat install as an untrusted-code rung: pip argv carries `--disable-pip-version-check`,
  an explicit build-isolation choice, and `--require-hashes`/`--only-binary` when a fully-pinned
  `requirements.txt` is present; record the index URL + that egress occurs. **[R1-S2]** Spawn pip with
  a `preexec_fn` setting CPU/AS/NPROC rlimits; a breach → `install` rung reason `killed:resource-limit`.

- **FR-6/7/8 (boot+probe)** — `server.LiveServer`:
  - free port via `socket.bind(("127.0.0.1", 0))` then release. **[R1-S8]** On uvicorn bind failure,
    re-pick a fresh port (bounded retries) and classify the bind error as a **harness retry**, never a
    model `boot=fail`.
  - `Popen([<venv>/bin/uvicorn, "{mod}:{attr}", "--host","127.0.0.1","--port",P], cwd=app_root,
    env={...HOME,TMPDIR→throwaway...}, start_new_session=True, preexec_fn=<rlimits>)` **[R1-S2/S4]**,
    stdout/stderr → logfile.
  - poll `GET /health` → `/openapi.json` → `/` until 2xx or `boot_timeout`; **[R1-F10]** if only
    `/openapi.json` answers, mark `pass:liveness-only` (smoke is the authoritative readiness check);
    detect early child exit (`proc.poll()`), capture stderr tail as reason.
  - context manager: `__exit__` signals the **process group** (`killpg` SIGTERM→wait→SIGKILL); never
    leak children/grandchildren.
  - If mode∈{deployed, unknown} → skip boot, rung = `skipped:deployed-needs-db` / `skipped:mode-unknown`.

- **FR-9/10 (smoke)** — `smoke.run_smoke(base_url, openapi)`:
  - parse live `/openapi.json`; find a path with `post`+`get` on a collection whose request schema
    has **no required FK/relation** fields (prefer the simplest resource).
  - synthesize body from `components.schemas` **[R1-F4]** honoring the enumerated feature set (`$ref`
    resolution, `allOf` merge, `required` vs `nullable`, `enum` first, `format`, nested objects;
    explicit `oneOf`/`anyOf`/`additionalProperties` behavior); a feature the synthesizer can't satisfy
    ⇒ typed `skipped`, never a malformed body scored `fail`. POST then GET; assert non-5xx + id round-trip.
  - **[R1-F5]** no eligible resource ⇒ `skipped:no-list-create-resource`; declined FK-only ⇒
    `skipped:all-resources-fk-coupled` (harness limitation, bucketed separately in FR-12); derived-but-errored ⇒ `fail`.

- **FR-11 (result)** — `ladder.LadderResult` (pydantic): `app_root`, `model?`, `mode`+`mode_derivation`,
  `highest_stage`, `stages:{discover,install,boot,health,smoke}->{status,reason,ms}`,
  `entrypoint`+`matched_by`, `dep_source`, `deviations[]`, `log_paths`, `timings`, and **[R1-S6]** a
  `harness_env` block (effective install/boot timeouts, venv Python version, `pip freeze`, pip index
  URL + reachability, chosen port). `.to_json()` + `.summary()`.

- **FR-12 (batch)** — `batch.deploy_batch(batch_root)`: glob `*/workdir` (or `*/app` fallback), run
  ladder **serially** (v1, avoids port races), aggregate to `deploy-report.json` (+ `.md`) with a
  per-model row + rung roll-up (the two `skipped:*` smoke reasons in separate buckets). **[R1-S3]**
  Authoritative join key = verbatim model id read from a `deploy-manifest.json`/`<workdir>/.model`
  sidecar (writer-side = M3); reverse-slug is a **fallback only** that logs a collision warning when
  two workdirs resolve to one slug.

- **FR-13 (teardown)** — try/finally around server + `shutil.rmtree(tmp)`; `--keep` preserves.
  **[R1-S4]** Server started with `start_new_session=True`; teardown `killpg` the group
  (SIGTERM→wait→SIGKILL) so grandchildren are reaped; crash-safe rmtree (ignore_errors + re-sweep) so
  a SIGKILL mid-delete can't leave a half-removed venv; signal handler so Ctrl-C still reaps group + tmp.

- **FR-14 (CLI)** — `cli_deploy.py` (copy `cli_generate.py` skeleton): `deploy local <root>` and
  `deploy batch <dir>` (`--keep`, `--install-timeout`, `--boot-timeout`, `--json`); register
  `app.add_typer(deploy_app, name="deploy")` in `cli.py`. Library API mirrors CLI for the benchmark.

- **FR-15/16/17/18 (safety)** — enforced by FR-4 (venv isolation), FR-6 (loopback bind + HOME/TMPDIR
  redirect), rlimits on both children (FR-16/[R1-S2]), all timeouts; module docstring states the v1
  trust boundary, names **install-time ACE/egress** (FR-17/[R1-S1]) and the **FS-write blast radius**
  (FR-18/[R1-F3]) as known v1 limits, and draws the containment line at v2/FR-44 Docker.

## 3. Sequencing

- **M0** ✅ SHIPPED (`76a56d67`) — `discovery.py` + `ladder.py` models + 21 unit tests (no live process).
- **M1** ✅ SHIPPED — `venv_runner.py` (rlimits, pip hardening) + `server.py` (process-group teardown,
  port retry, HOME/TMPDIR) + `deploy.py` orchestration + `cli_deploy.py` (`startd8 deploy local`).
  12 network-free unit tests (server probe/teardown, orchestration skips) + 3 gated live integration
  tests (real venv+pip+uvicorn boot, incl. liveness-only + broken-boot). Live path verified
  end-to-end (`discover→install→boot→health` all pass on a real installed-mode app). **[R1-S7]** the
  live installed-app fixture is the reusable golden fixture for M2 synth regression.
- **M2** ✅ SHIPPED — `smoke.py`: `synthesize_body` (enumerated feature set: `$ref`/`allOf`/`required`
  vs `nullable`/`enum`/`format`/nested/`oneOf`/`anyOf`) + `select_crud_resource` (FK-free preference,
  3 distinct skip reasons) + live create→list round-trip, wired as the smoke rung in `deploy.py`
  (`--no-smoke` to disable). 18 network-free synth/selection unit tests + 2 live CRUD integration
  tests (round-trip pass; FK-only → `skipped:all-resources-fk-coupled`). Verified end-to-end:
  `discover→install→boot→health→smoke` all pass on a real in-memory CRUD app.
- **M3** — `batch.py` + aggregate report + join to `comparison-report.json`; **writer-side
  coordination [R1-S3]**: have `model_comparison.py` drop the `deploy-manifest.json`/`.model` sidecar
  carrying the verbatim model id. Wire optional post-run call (behind a flag, non-breaking).

## 4. Risks

- **Untrusted code — install is the first ACE surface** [R1-S1/S2]: `pip install` runs build-hook code
  + egress before any boot timeout. v1 mitigates with build-isolation choice, pinning/hashes when
  available, and rlimits on the pip child; full containment is the v2/FR-44 Docker line. v1 is
  venv+subprocess+loopback, explicitly *not* a kernel sandbox; FS-write blast radius beyond the DB is
  a documented v1 limit (FR-18).
- **Host takedown by raw LLM output** [R1-S2] — fork bomb / memory balloon: CPU/AS/NPROC rlimits on
  both children; breach → `killed:resource-limit`, not a hang.
- **OpenAPI body synth brittleness** (FK chains) — enumerated feature set as acceptance criteria;
  prefer FK-free resources; the FK-only case is a *distinct, visible* `skipped` bucket (not neutral)
  so the bias doesn't masquerade as a model trait.
- **Harness flakiness misattributed to the model** [R1-S6/S8] — `harness_env` block makes a `fail`
  reproducible; port bind-race is a harness retry; silent mode mis-detect becomes `mode=unknown`.
- **Lossy join key** [R1-S3] — explicit model-id sidecar is authoritative; reverse-slug is a
  warned fallback.
- **Teardown orphans** [R1-S4] — process-group kill + crash-safe rmtree.
- **pip install latency/network** — generous `--install-timeout`; install is its own graded rung so
  slowness/offline shows up as data, not a crash.
- **Port races in parallel batch** — v1 serial; parallel deferred with a port-lease pool.

## 5. Test plan

- Unit: discovery (canonical, non-canonical, missing-deps, deployed-mode), ladder serialization,
  body-synth from a fixture OpenAPI. Fast, no process.
- Integration (`@pytest.mark.slow`+`integration`, `importorskip("fastapi")`): generate a backend →
  `deploy_app_local` → assert rungs reach `smoke=pass`; a deliberately-broken app → assert it stops
  at the right rung with a reason. Teardown asserts no orphan port/process.

## 6. Traceability

Every FR-0..18 maps to a step in §2 (FR-16/17/18 added in CRP R1 → covered by the FR-4/5, FR-6, and
FR-15/16/17/18 safety steps); every step traces to an FR. OQ-1..6 all resolved (see §0 table +
requirements §0). All CRP R1 suggestions (S1–S8, F1–F10) applied — see Appendix A in each doc. No open
questions block implementation.

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
| R1-S1 | pip build-isolation + pinning/hashes + egress note (install = untrusted-code rung) | R1 | §2 FR-4/5 step; §4 Risks; mirrors req FR-5/FR-17 | 2026-06-14 |
| R1-S2 | rlimits on pip + uvicorn children (`killed:resource-limit`) | R1 | §2 FR-4/5 + FR-6 steps; §4 Risks; mirrors req FR-16 | 2026-06-14 |
| R1-S3 | Explicit model-id sidecar join key; reverse-slug fallback+warn | R1 | §2 FR-12 step + §3 M3 writer-side; mirrors req FR-0/FR-12 | 2026-06-14 |
| R1-S4 | Process-group teardown + crash-safe rmtree | R1 | §2 FR-13 step; §4 Risks; mirrors req FR-13 | 2026-06-14 |
| R1-S5 | Detection derivation/confidence; mode=unknown | R1 | §2 FR-3 step; mirrors req FR-3/FR-1 | 2026-06-14 |
| R1-S6 | `harness_env` block in LadderResult | R1 | §2 FR-11 step; mirrors req FR-11 | 2026-06-14 |
| R1-S7 | M1 generated app = reusable golden fixture for M2 synth regression | R1 | §3 M1/M2 | 2026-06-14 |
| R1-S8 | Port bind-race → harness retry, not `boot=fail` | R1 | §2 FR-6 step; §4 Risks; mirrors req FR-6 | 2026-06-14 |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none yet) |  |  |  |  |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — claude-opus-4-8-1m — 2026-06-15

- **Reviewer**: claude-opus-4-8-1m
- **Date**: 2026-06-15 00:30:00 UTC
- **Scope**: Plan review (S-prefix). Sponsor focus: untrusted-code trust boundary, OpenAPI→body-synth brittleness, input-contract/reverse-slug ambiguity, teardown/no-orphan, reuse correctness, benchmark signal integrity. (Sponsor-ask answers live in the requirements-file R1 block; plan deltas referenced below.)

##### Executive summary

- **Install step is the first untrusted-code-execution surface** and is unguarded: §2 FR-4/5 runs `pip install` with no build-isolation decision and no resource caps — arbitrary code (build hooks) + arbitrary egress fire before any boot timeout. Highest risk.
- **No resource limits** anywhere in §2 (`venv_runner`/`server`): a fork bomb or memory balloon in raw LLM output takes down the benchmark host.
- **Reverse-slug join (§2 FR-12) is the benchmark's join key of record but is lossy** — slug collisions across providers silently corrupt the left-join to `comparison-report.json`.
- **Teardown (§2 FR-13) kills only the direct child** — grandchildren (multi-worker uvicorn, app-spawned subprocesses) orphan; partial tmp cleanup on SIGKILL unaddressed.
- **`detect_mode` silent default to `installed` (§2 FR-3)** mis-detects a `deployed` app, live-boots it, and the hang is misattributed to the model.
- **LadderResult (§2 FR-11) omits the environment** (effective timeouts, dep versions, network status) needed to make a `fail` reproducible and not confounded with harness flakiness.
- **`/openapi.json`-first probe (§2 FR-6/7)** can yield a false `health=pass` on an app whose DB lifespan is dead.
- **Opportunity:** M1's "generate a backend, deploy it" integration test already produces a known-good canonical app — reuse it as the harness's golden fixture for FR-9 synth regression at near-zero extra cost.

##### Numbered suggestions

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-S1 | Security | critical | In §2 FR-4/5 (`venv_runner.create_and_install`), make the pip invocation's build-isolation explicit and document the egress: decide `--no-build-isolation` vs default, prefer `--require-hashes`/pinned installs when `requirements.txt` is present, and pass `--disable-pip-version-check`. Treat install as an untrusted-code rung, not a setup step. | Build backends execute arbitrary code at install time, before the boot timeout window — the plan's "untrusted code" mitigations (FR-6 loopback, timeouts) never cover this surface. | §2 FR-4/5 step + §4 Risks | Unit assert pip argv carries the chosen flags; integration: malicious `setup.py` in deps is contained/observed. |
| R1-S2 | Security | high | Add resource limits to both subprocesses in §2: `venv_runner` (pip) and `server.LiveServer` (uvicorn) should set CPU-time + address-space + max-process rlimits via a `preexec_fn` (POSIX) and record a `killed:resource-limit` rung reason. | §1's "keeps the untrusted-code boundary explicit" claim is undercut if a fork bomb/OOM in the child can crash the host running the benchmark. | §2 FR-4/5 and FR-6 steps; note in §4 Risks | Integration: app that forks/allocates aggressively is capped and reported, host survives. |
| R1-S3 | Ops | high | In §2 FR-12, stop using reverse-slug as the authoritative join key: have the batch step read an explicit model id written alongside each workdir (or a `deploy-manifest.json`), and demote reverse-slug to a fallback that logs a collision warning when two workdirs resolve to the same slug. Coordinate the writer side in M3 (`model_comparison.py`). | A lossy directory-name inversion is the join key for the entire cross-model comparison; collisions silently mis-join `comparison-report.json`. | §2 FR-12 step + §3 M3 | Unit: two model ids slugging identically are disambiguated by the explicit key; collision path warns. |
| R1-S4 | Risks | high | Upgrade §2 FR-13 teardown to **process-group** semantics: start the server with `start_new_session=True` (or `setsid`), and on teardown signal the whole group (SIGTERM→wait→SIGKILL) so multi-worker/grandchild processes are reaped; wrap tmp removal so SIGKILL/crash cannot leave a half-deleted venv. | `__exit__ SIGTERM→SIGKILL` on a single PID orphans grandchildren and may leave the tmp dir on a crash mid-rmtree. | §2 FR-13 step | Integration: app spawns a child + extra port; post-teardown assert empty process group and freed port (extend §5 teardown test). |
| R1-S5 | Architecture | medium | In §2 FR-3 (`detect_mode`) and FR-1 (`detect_entrypoint`), return a derivation/confidence on every detection and route ambiguous/garbled inputs (missing or unparseable `app/settings.py`, scan picking among multiple `app =` bindings) to a graded deviation rather than a silent default. A `deployed` app mis-read as `installed` should surface as `mode=unknown` + deviation, not a clean boot attempt. | Silent defaults convert a harness mis-detection into a model-attributed `boot=fail`, corrupting the benchmark signal. | §2 FR-1/FR-3 steps | Unit: garbled settings.py ⇒ `mode_derivation` + deviation; multi-binding scan ⇒ recorded ambiguity. |
| R1-S6 | Validation | high | Extend the §2 FR-11 `LadderResult` to persist a `harness_env` block: effective install/boot timeouts, venv Python version, pip index URL + reachability, installed dep versions (pip freeze), and chosen port. Add to §5 a reproducibility assertion. | Without recorded environment a `fail` is not reproducible and a timeout/network-induced `fail` is indistinguishable from broken model code in the roll-up. | §2 FR-11 step + §5 Test plan | Schema test for `harness_env`; force a 1ms boot timeout and confirm the report marks it environment-induced. |
| R1-S7 | Validation | medium | In §3 M1, designate the "generate a backend → deploy it → assert `health`" app as the **reusable golden fixture** for M2's body-synth regression (a known-good canonical OpenAPI), and add a deliberately-broken-schema fixture for the `skipped`/`fail` synth paths. Near-zero extra cost since M1 already builds the app. | §5 already implies these fixtures; naming and reusing them across M1→M2 captures the synth regression surface (the riskiest correctness area) with no new infra. | §3 M1/M2 + §5 | The same generated app feeds both the live-boot test and the synth unit test; broken-schema fixture exercises `skipped:*`/`fail`. |

##### Stress-test / adversarial pass

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-S8 | Ops | medium | §2 FR-6 free-port selection has a **bind-release-then-reuse race**: `socket.bind(("127.0.0.1",0))` then release, then hand the port to uvicorn, leaves a window where another process grabs the port → spurious `boot=fail`. Even in serial batch this races against other host processes. Mitigate by retrying boot on bind-failure with a fresh port (bounded) and classifying a port-bind error as a harness retry, not a model `boot=fail`. | A harness-side port race is exactly the "flakiness misattributed to the model" failure the focus file warns against. | §2 FR-6 step + §4 Risks | Integration: occupy the just-released port before uvicorn binds; assert harness retries with a new port rather than recording `boot=fail`. |

---

## Requirements Coverage Matrix — R1

Analysis only (not triage). Maps each requirement (FR-0..15) to the plan step(s) that address it. `Partial`/`Gap` rows reference the corresponding R1 suggestion.

| Requirement | Plan Step(s) | Coverage | Gaps |
| ---- | ---- | ---- | ---- |
| FR-0 (input contract = workdir/) | §0 table, §2 FR-12 | Partial | Join key reconstructed by reverse-slug, not carried explicitly (R1-F6/R1-S3). |
| FR-1 (entry-point detect, layered) | §2 FR-1 | Partial | No derivation/confidence; multi-binding scan ambiguity defaults silently (R1-F8/R1-S5). |
| FR-2 (dep detect + dep floor) | §2 FR-2 | Partial | Dep-floor install reaches PyPI by name with no pinning/hash/egress note (R1-F1/R1-S1). |
| FR-3 (mode detect via embedded_mode) | §2 FR-3 | Partial | Silent default `installed` on garbled settings mis-attributes hangs (R1-F8/R1-S5). |
| FR-4 (throwaway venv) | §2 FR-4/5 | Full | — |
| FR-5 (pip install + timeout) | §2 FR-4/5 | Partial | No build-isolation decision; install is untrusted-code ACE surface (R1-F1/R1-S1); no resource caps (R1-F2/R1-S2). |
| FR-6 (uvicorn subprocess, loopback, cwd) | §2 FR-6 | Partial | FS-write blast radius beyond DB unstated (R1-F3); port bind-release race (R1-S8); no rlimits (R1-S2). |
| FR-7 (health-poll order) | §2 FR-6/7 | Partial | `/openapi.json`-first can yield false `health=pass` on dead-DB app (R1-F10). |
| FR-8 (boot timeout / early-exit) | §2 FR-6 | Full | — |
| FR-9 (OpenAPI→body synth) | §2 FR-9 | Partial | Mandatory schema-feature coverage ($ref/allOf/enum/format/nullable) unspecified (R1-F4). |
| FR-10 (smoke best-effort, graded) | §2 FR-9 | Partial | `skipped:no-crud-resource` conflates "none" with "all-FK-coupled" → hidden bias (R1-F5). |
| FR-11 (graded result schema) | §2 FR-11 | Partial | No harness-env block for reproducibility (R1-F9/R1-S6). |
| FR-12 (batch mode + join) | §2 FR-12, §3 M3 | Partial | Lossy reverse-slug as authoritative join key (R1-F6/R1-S3). |
| FR-13 (teardown / no-orphan) | §2 FR-13 | Partial | Single-PID kill orphans grandchildren; partial tmp cleanup on SIGKILL (R1-F7/R1-S4). |
| FR-14 (CLI surface + library API) | §2 FR-14 | Full | — |
| FR-15 (untrusted-code safety) | §2 FR-15, §4 Risks | Partial | Boundary honestly stated but missing install-time ACE, resource caps, FS-write scope (R1-F1/F2/F3, R1-S1/S2). |
