# `startd8 capdevpipe run` — Enhancement Backlog

Pass run **after** the issue #220 fix (config-free run when the embed ships no `pipeline.yaml`;
commit `14afbac6`, branch `fix/capdevpipe-run-configless-220`). Scope: the headless orchestration
entrypoint — `src/startd8/capdevpipe_runner.py`, `src/startd8/cli_capdevpipe.py`, and the surface
where they meet the installer (`src/startd8/capdevpipe_installer.py`).

**Grounding note (belief → actual — where going-and-seeing changed the answer):**
- I believed the #220 fix *finished* the config-free story. Actual: it makes `run` **not error**,
  but the user still hand-passes the 6-flag workaround (`--plan/--requirements/--project/...`). The
  installer already builds the exact inputs those flags name (`<embed>/<lang>/<lang>-{plan,requirements}.md`)
  and the runner never looks at them. The real leverage is *downstream* of my fix, not in it.
- I assumed the pipeline had no profile auto-selection. Actual: it does (`cli.py:329`, "Auto-selected
  profile") — but it reads `config.profiles`, which only exist in `pipeline.yaml`. So the capability
  *exists* yet is structurally unreachable on a config-free orchestrator install. That inverts the
  finding: it's not "build auto-select," it's "bridge the embed's on-disk profile dir into the
  auto-select the pipeline already has."

**No verified defect leads this backlog.** The #220 path is wired + verified end-to-end (dry-run
exit 0). The top finding is a *latent capability*, not a break — I am not filing a Closure-Ledger
row, because nothing here claims to work and silently doesn't.

---

## Top findings (do first)

### 1. Zero-flag `capdevpipe run` — auto-discover the embed's profile dir *(latent capability — S/M)*

Config-free (issue #220), the pipeline's own "auto-select single profile" (`~/Documents/dev/cap-dev-pipe/pipeline/cli.py:329`)
is dead code: it keys on `config.profiles`, which are populated only from `pipeline.yaml`, and the
orchestrator embed has none. Meanwhile the installer **already writes** the profile docs the run
needs — `create_profile()` emits `<embed>/<lang>/<lang>-plan.md` + `<lang>-requirements.md`
(`capdevpipe_installer.py:1214-1236`) and records the langs in the manifest's `profiles` field
(`Manifest.profiles`, written at `capdevpipe_installer.py:805-813`). The runner
(`capdevpipe_runner.py`) reads **neither**.

Wire it: on the config-free path, when the caller passed no `--plan`, discover the profile dir
(glob `<embed>/*/` for a `*-plan.md`/`*-requirements.md` pair, or read `read_manifest().profiles`)
and inject `--plan`/`--requirements` (absolute paths) — `--project` already arrives via the
pipeline.env hydration the #220 fix added. Handle the three cases honestly: exactly one profile →
inject + log which; zero → today's config-free behavior (unchanged); more than one → don't guess,
print the candidates and ask for `--profile-lang`.

- **Value:** *direct* — collapses the documented 6-flag workaround into `startd8 capdevpipe run`;
  *ripple* — the Mastodon deterministic-observability pilot (the reporter) and any orchestrator-profile
  consumer get a real out-of-the-box entrypoint, not just a non-erroring one. So a pilot author can
  kick off a delivery run without memorizing embed-relative paths.
- **Leverages:** installer profile-dir writer + manifest `profiles` (both already built *for exactly
  this*); pipeline.env hydration (just shipped).

### 2. Surface `verify` / `doctor` verbs — but they need profile-awareness first *(S + S/M — reqs drafted)*

> **Correction (grounding falsified the original "pure wiring — no new logic" sizing).**
> `verify()` (`capdevpipe_installer.py:1295`) hard-requires an embedded **`run.sh`** and runs
> `run.sh --list-langs`; `doctor()` (`:1456`) falls through to it. But `run.sh` is a **`full`-only**
> script — the `orchestrator`/`minimal` profiles ship none. So on a *healthy* orchestrator install
> (the exact #220 audience), both methods return `passed=False`. Exposing them unchanged would hand
> every non-`full` user a **false FAILED**. The verb exposure is therefore *blocked on* making verify
> profile-aware — not thin wiring.

The verbs are still worth adding (today the only health check is the non-obvious
`capdevpipe install --rerun-mode doctor`), and the profile-aware fix has a clean latent lever:
`Manifest.managed_paths` already persists the profile's resolved entrypoint set *for exactly this*
(`capdevpipe_installer.py:805-813`), so verify can single-source its expected-scripts check instead
of hardcoding `run.sh`.

Requirements drafted in **`CAPDEVPIPE_VERIFY_PROFILE_AWARE_REQUIREMENTS.md`** (FR-1/2/3 profile-aware
verify, FR-4/5/6 verb exposure + render). **Do not ship FR-4/5 without FR-1/2/3**, and resolve OQ-3
first (canonical `pipeline verify` may already do this — delegate rather than re-implement).

- **Value:** *direct* — a discoverable, *profile-correct* "is my install healthy?" command; *indirect*
  — gives the #220 class of "my run won't start" a first-stop diagnostic that doesn't lie for
  orchestrator installs.
- **Leverages:** `verify()`/`doctor()`/`detect_existing()` (built) + `Manifest.managed_paths` (the
  latent single-source that makes FR-1/2 wiring rather than authoring).

---

<details>
<summary>Backlog appendix (draw from over later increments)</summary>

> **Delivered (chore/capdevpipe-run-quickwins):** AQ-1, QW-1, QW-2, LH-1 are all done — see the
> ✅ markers below. Finding #1 (zero-flag run) shipped in #221; finding #2 (profile-aware verify)
> in #222. AQ-1's actual size was S (not XS): canonical `load_pipeline_env` needs a real importable
> `pipeline` package, so the config-free tests gained real package scaffolding + a `sys.modules`
> isolation fixture — a grounding correction to the original estimate.

### 🏗️ Architectural quick wins

- ✅ **AQ-1 — Use canonical `load_pipeline_env` instead of the hand-rolled parser *(XS/S → S)*.** The #220
  fix added `_hydrate_env_from_pipeline_env` (`capdevpipe_runner.py`), which re-implements
  `KEY=value` parsing that already exists canonically as `pipeline.config.load_pipeline_env(script_dir)`
  (`~/Documents/dev/cap-dev-pipe/pipeline/config.py:207`) — importable once `ensure_pipeline_import`
  has run. Swapping to it single-sources the env format (the canonical parser also handles the
  `export ` prefix the SDK installer's `_merge_managed_env` explicitly tolerates), removing a
  **mirror-drift seam** (a `/complexity-distiller` "S6" smell) between two copies of the format
  contract. One item, and it rides on a single-source the ecosystem already owns. *(Caveat: keep
  the flag-guarded `setdefault` layer — only the parse step is duplicated.)*

### ⚡ Quick wins

- ✅ **QW-1 — Announce the run mode *(XS)*.** On the config-free path, emit one info line —
  `running config-free (no pipeline.yaml); profile=<lang>` — so the user understands *why* they
  didn't need `--config` and which inputs were selected. Closes a comprehension gap the #220 fix
  opened. *(Delivered as two stderr lines via `_announce`.)*
- ✅ **QW-2 — Point the config-free error at the fix, not just the symptom *(XS)*.** If discovery
  (finding #1) finds no profile *and* the caller passed no `--plan`, the pipeline's downstream
  "`--project`/plan required" error is opaque. Pre-empt it with a message naming the embed's
  expected `<lang>/<lang>-plan.md` convention and the `capdevpipe install --profile` that creates it.

### 🌱 Low-hanging fruit

- ✅ **LH-1 — `capdevpipe run --dry-run` is already reachable — document it *(XS)*.** Passthrough argv
  carries `--dry-run` through to the pipeline (validated in the #220 smoke test: it prints the full
  stage plan, exit 0). It's a strong "what will this do?" affordance that no help text mentions. Add
  it to the `run` command help / a docs example. Pure surfacing.

### Honest gaps (decisions, not bugs)

- **Installer emitting a `pipeline.yaml` (issue #220 proposed-fix option 1) is now moot — by
  choice.** With config-free `run` working, materializing a `pipeline.yaml` at install time would
  add a file to keep in sync for no functional gain. Leave the orchestrator profile config-less;
  the `pipeline init` subcommand (`~/Documents/dev/cap-dev-pipe/pipeline/cli.py:137`) remains the
  path for a project that genuinely wants a checked-in config. Confirm that's the intended shape
  before anyone "helpfully" adds option 1.
- **`env > CLI` precedence is a cap-dev-pipe design choice, not a bug to fix here.** The #220 fix
  works *around* it (flag-guarded injection). Any deeper reconciliation belongs upstream in
  cap-dev-pipe's `build_config` precedence, not in the SDK runner — don't paper over it with more
  guards on the SDK side.

</details>
