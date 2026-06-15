# Deploy Harness — How-To

`startd8 deploy` takes an SDK-generated application and **runs it as a live local server**, grading
how far it gets through a fixed ladder: **`discover → install → boot → health → smoke-CRUD`**. Each
rung records a typed pass/fail/skipped reason.

It exists to turn a PrimeContractor (or `generate backend`) output into a *deployed, graded* app —
primarily to **compare code quality across models** in the Summer 2026 benchmark (where deterministic
generation is OFF, so apps are raw LLM output and won't reliably match the canonical layout), and to
**feed concrete defects back into the SDK**.

- **Design docs:** `docs/design/local-deploy-harness/` (Requirements v0.3, Plan v1.1, CRP review).
- **Code:** `src/startd8/deploy_harness/` + `src/startd8/cli_deploy.py`.

---

## TL;DR

```bash
# Deploy one generated app and grade it
startd8 deploy local path/to/app-root

# Deploy every per-model app from a comparison batch and join to the quality report
startd8 deploy batch path/to/batch-root
```

An "app root" is the directory that **contains the generated `app/` package** (i.e. `app/main.py`
lives at `<app-root>/app/main.py`).

---

## The graded ladder

| Rung | What it checks | Passes when |
|------|----------------|-------------|
| **discover** | Find the ASGI entry point, dependencies, and deployment mode | A bootable `module:app` target is found |
| **install** | Create a throwaway venv and `pip install` the app's deps | pip exits 0 |
| **boot** | Launch the app under uvicorn on a loopback port | The server process stays up and accepts connections |
| **health** | Probe `/health` → `/openapi.json` → `/` | A probe returns 2xx |
| **smoke** | Synthesize a POST body from the live OpenAPI, create→list round-trip | The created row is observable in the list |

Each rung has a **status** — `pass` / `fail` / `skipped` / `not_reached` — and, when not a clean pass,
a **typed reason**. The ladder stops at the first hard failure; `highest_stage` records how far it got.

### Common reasons you'll see

| Reason | Meaning |
|--------|---------|
| `entrypoint-missing` | No FastAPI app found anywhere under the app root |
| `pip-exit-1` / `install-timeout:600s` | Dependency install failed or timed out |
| `early-exit:rc=1` | The server process crashed during startup (see the server log for the traceback) |
| `boot-timeout:60s` | The server never became reachable within the timeout |
| `skipped:deployed-needs-db` | App is `deployed`-mode (needs Postgres) — not live-bootable in v1 |
| `skipped:mode-unknown` | `app/settings.py` is present but its mode header is unparseable |
| health `pass:liveness-only` | Only `/openapi.json` answered — the framework is up, but app readiness is unconfirmed |
| smoke `skipped:no-list-create-resource` | The app exposes no JSON list+create collection to smoke |
| smoke `skipped:all-resources-fk-coupled` | Every create endpoint needs a foreign key — a harness limitation, **not** a model defect |
| smoke `fail` → `post-422` / `no-round-trip` | The create call errored, or the created row didn't appear in the list |

---

## `startd8 deploy local`

```bash
startd8 deploy local <app-root> [OPTIONS]
```

| Option | Default | Purpose |
|--------|---------|---------|
| `--model TEXT` | — | Verbatim model id, recorded in the result |
| `--install-timeout FLOAT` | `600` | pip install timeout (seconds) |
| `--boot-timeout FLOAT` | `60` | Server boot timeout (seconds) |
| `--no-smoke` | off | Stop after the health rung |
| `--editable PATH`, `-e` | — | pip-install a local project editable (repeatable). For apps that depend on an unpublished local package — see below |
| `--keep` | off | Keep the throwaway venv/work dir for debugging |
| `--json` | off | Emit the full `LadderResult` as JSON (for CI) |

#### Apps that depend on an unpublished local package (`--editable`)

If a generated app's `requirements.txt` lists a package that isn't on PyPI — e.g. **`startd8`** itself
(the SDK) for an app that uses the AI layer — a clean-room `pip install` will fail at the `install`
rung (`No matching distribution found`). Point `--editable` at the local checkout:

```bash
startd8 deploy local ./my-app --editable /path/to/startd8-sdk
```

The harness installs each editable in a **prior pip pass**, so the bare `startd8` requirement is then
already-satisfied and pip skips the index lookup. (This is exactly how StartDate — which depends on
`startd8` — deploys clean-room through the full ladder.) Repeatable for multiple local deps;
`deploy batch` accepts the same flag (applied to every app's venv).

**Exit code:** `0` if the app reached a clean `health` rung, else `1` (`2` if the path isn't a directory).

### Example

```text
$ startd8 deploy local ./my-app
/abs/my-app model=- mode=installed highest=smoke [discover:pass install:pass boot:pass health:pass smoke:pass]
  discover  pass
  install   pass
  boot      pass
  health    pass
  smoke     pass
```

### JSON output (`--json`)

```jsonc
{
  "app_root": "/abs/my-app",
  "model": "anthropic:claude-opus-4-8",
  "mode": "installed",
  "mode_derivation": "default",
  "entrypoint": { "target": "app.main:app", "matched_by": "app-package-default" },
  "dep_source": "requirements.txt",
  "highest_stage": "smoke",
  "stages": {
    "discover": { "status": "pass" },
    "install":  { "status": "pass", "ms": 4200.5 },
    "boot":     { "status": "pass", "ms": 1275.3 },
    "health":   { "status": "pass" },
    "smoke":    { "status": "pass", "ms": 41.0 }
  },
  "deviations": [],
  "harness_env": {
    "install_timeout_s": 600, "boot_timeout_s": 60,
    "venv_python_version": "Python 3.14.5",
    "installed_deps": ["fastapi==0.x", "uvicorn==0.x", ...],
    "pip_index_url": "https://pypi.org/simple", "network_reachable": true, "port": 56143
  },
  "log_paths": { "install": "...", "server": "..." }
}
```

`harness_env` exists so a `fail` is **reproducible and attributable** — a `boot-timeout` from a tight
limit or a PyPI blip is distinguishable from genuinely broken model code.

---

## `startd8 deploy batch`

Deploys every per-model app under a comparison batch root, **serially**, and writes an aggregate
report joined to the model-quality report.

```bash
startd8 deploy batch <batch-root> [OPTIONS]   # --install-timeout --boot-timeout --no-smoke --no-join --keep
```

### Expected batch layout

This is exactly what `model_comparison.py` (`startd8 compare-models`) produces:

```
batch-root/
├── comparison-report.json          # model-quality metrics (optional; enables the join)
├── anthropic-claude-opus-4-8/
│   ├── .model                      # verbatim model id sidecar (written by model_comparison.py)
│   ├── workdir/                    # <- the app root (contains app/)
│   └── output/                     # prime result JSONs (ignored by the harness)
└── openai-gpt-5/
    ├── .model
    ├── workdir/
    └── output/
```

The harness globs `*/workdir`, reads the **`.model` sidecar** for the verbatim model id, and joins each
deploy outcome to `comparison-report.json` by that id. (If a sidecar is missing it falls back to the
directory slug and emits a warning — the slug is lossy, so the join basis is always recorded.)

### Output

Writes two files to the batch root:

- **`deploy-report.json`** — per-model `LadderResult` rows + a reached/passed roll-up + the
  `comparison` metrics joined in per model + a `join_basis` (`exact` / `reverse-slug` / `ambiguous` /
  `no-match`) + any `warnings`.
- **`deploy-report.md`** — human-readable roll-up + per-model table.

```text
$ startd8 deploy batch ./batch-root
2 app(s) under ./batch-root
  install   2 passed / 2 reached
  boot      2 passed / 2 reached
  health    2 passed / 2 reached
  smoke     2 passed / 2 reached
  report → ./batch-root/deploy-report.md
```

### Auto-run from a model comparison

`startd8 compare-models` can run the deploy harness automatically as a final step, so a single
command produces both the code-quality ranking *and* the deploy outcomes (joined by model id):

```bash
startd8 compare-models --seed seed.json -m anthropic:opus -m openai:gpt --batch-root ./out --deploy-after
```

`--deploy-after` is **off by default** (it boots untrusted generated code in throwaway venvs). When
set, after `comparison-report.{json,md}` is written it runs `deploy_batch` over the same batch root
and writes `deploy-report.{json,md}` alongside it. The deploy step is fail-safe — a failure there is
logged but never changes the comparison result. The same flag exists on
`scripts/run_prime_model_comparison.py` and as `run_comparison(..., deploy_after=True)`.

You can also run it after the fact on a finished batch: `startd8 deploy batch ./out`.

---

## Library API

Everything is importable for use inside the benchmark harness or your own scripts:

```python
from startd8.deploy_harness import deploy_app_local, deploy_batch

# one app
result = deploy_app_local(
    "path/to/app-root",
    model="anthropic:claude-opus-4-8",
    install_timeout_s=600,
    boot_timeout_s=60,
    do_smoke=True,
    keep=False,
)
print(result.summary())          # one-line roll-up
print(result.highest_stage)      # "smoke"
print(result.to_json())          # full graded result

# a whole batch (writes deploy-report.{json,md} to the batch root)
report = deploy_batch("path/to/batch-root", join=True)
print(report["rollup"]["passed"])  # {"discover": 2, "install": 2, ... }
```

Also exported: `detect_entrypoint`, `detect_deps`, `detect_mode` (pure discovery), `synthesize_body`,
`select_crud_resource`, `run_smoke` (smoke internals), `LiveServer`, `create_venv`, `install_deps`,
`ResourceLimits`, and the `LadderResult` model.

> **Advanced:** `deploy_app_local(..., runner_python="/path/to/python")` skips venv creation and uses a
> prepared interpreter (it must already have the app's deps + uvicorn). Useful for fast, network-free
> runs; the `install` rung is recorded as `skipped:prepared-env`.

---

## Deployment modes

The harness reads the deployment mode from `app/settings.py` (the self-embedded `# startd8-mode:`
header from the deployment-mode capability):

- **`installed`** (default; also when `settings.py` is absent) — single-user, self-bootstraps a local
  `sqlite:///./app.db` via the lifespan `create_all`. **This is what v1 live-boots.**
- **`deployed`** — multi-user, needs Postgres + `DATABASE_URL`; **not** live-bootable in v1, so the
  `boot` rung is `skipped:deployed-needs-db`.
- **`unknown`** — `settings.py` is present but has no parseable mode header; treated as a graded
  deviation (`skipped:mode-unknown`), **never** silently assumed `installed` (a mis-detected
  `deployed` app would hang and be wrongly blamed on the model).

---

## Tolerance & deviations

Because benchmark apps are raw LLM output, the harness **never assumes the canonical layout** and
records departures as graded `deviations` (it does not fail on them):

| Deviation code | Meaning |
|----------------|---------|
| `entrypoint-noncanonical` | Entry point found, but not at the canonical `app/main.py:app` |
| `entrypoint-ambiguous` | The bounded scan found more than one module-level `FastAPI()` — picked the first deterministically |
| `entrypoint-scan-truncated` | The scan hit its file budget before exhausting the tree |
| `deps-missing` | No `requirements.txt`/`pyproject` deps — installed a minimal dep floor instead |
| `mode-ambiguous` | `settings.py` present but mode header unparseable |

Entry-point detection is layered: **manifest fast-path** (`app.yaml` → `resolve_app_target`) →
ordered candidates (`app/main.py`, `main.py`, `app/server.py`) → a bounded scan for any module-level
`FastAPI()` binding. Dependencies: `requirements.txt` → `pyproject.toml` → dep floor.

---

## Safety & the trust boundary (read this)

**The apps under test are UNTRUSTED.** v1 isolation is **throwaway venv + subprocess + loopback bind +
resource limits + timeouts** — it is **not** a kernel sandbox.

- **`pip install` is the first arbitrary-code-execution surface.** PEP 517 build backends run
  attacker-influenced code, and the resolver reaches the package index over the network — both
  *before* any boot timeout. v1 hardens install (no SDK-interpreter install, build-isolation recorded,
  pinning/hashes when available) but does **not** fully contain it.
- **Resource limits** (CPU left unbounded; address-space 4 GiB + max-processes 256 by default) backstop
  fork bombs and memory balloons via `ResourceLimits` — best-effort, POSIX-only.
- **Filesystem writes** are only partially confined: the SQLite DB stays in throwaway space and
  `HOME`/`TMPDIR` are redirected, but arbitrary `open(path, "w")` elsewhere is **not** blocked in v1.
- **Teardown** kills the whole process group (`SIGTERM` → `SIGKILL`), so multi-worker uvicorn and
  app-spawned grandchildren are reaped — no orphan processes or ports.

Full containment (kernel isolation, dependency quarantine, network egress control) is the **v2 / Docker**
upgrade and intersects benchmark FR-44. Run v1 on a dev/benchmark machine you're willing to expose.

---

## Testing

```bash
# Fast, network-free unit tests (discovery, ladder, server logic, smoke synthesis, batch)
pytest tests/unit/deploy_harness/ -q

# Full live path: real venv + pip + uvicorn boot + CRUD round-trip + batch (gated; needs network)
STARTD8_RUN_INTEGRATION=1 pytest tests/integration/test_deploy_harness_live.py -q
```

---

## Limits & roadmap (v1)

- **Python/FastAPI only.** Go/Java/Node/C# apps are out of scope for v1.
- **`installed`-mode only** for live boot; `deployed`-mode apps are graded `skipped`.
- **Serial batch execution** (avoids ephemeral port races); parallel is deferred.
- **No Docker** — v1 is venv-based; container isolation is the v2/FR-44 upgrade.
- Smoke is **best-effort**: it prefers FK-free resources and grades the FK-only case as a distinct
  `skipped` (so the bias is visible, not counted as neutral).
