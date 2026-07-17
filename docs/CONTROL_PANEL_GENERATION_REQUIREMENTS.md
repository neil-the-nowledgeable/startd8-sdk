# Control Panel Generation — SDK Requirements

> Requirements for embedding control-panel generation into the startd8-sdk so that
> apps produced by the SDK can be given a browser-based operator console with a
> single command. Ground-truth reference: the hand-built [strtd8 panel] at
> `/Users/neilyashinsky/Documents/dev/strtd8/strtd8/control-panel` — this SDK
> feature formalizes that pattern.

**Version:** 0.1.0-draft
**Date:** 2026-07-01
**Status:** Draft
**Parent framework spec:** [`control-panels/REQUIREMENTS.md`](../../../tools/control-panels/REQUIREMENTS.md)
**Related:** [`control-panels/CCCC_REQUIREMENTS.md`](../../../tools/control-panels/CCCC_REQUIREMENTS.md)
**Depends on:** Control Central v0.3.0+ (`retro-futurism` and `six-million` themes shipped, ENH-3 auto-sibling discovery, `panelId` in `/health`)

---

## 1. Purpose & Scope

Every app the SDK generates would benefit from an operator console — a way to start/stop it, run its gates (tests, typecheck, migrations), see it live/dead, and open it in a browser without hunting for commands. Today an operator hand-builds that console per app (see the strtd8 panel). This spec defines a **generation primitive** in the SDK that produces a ready-to-use control panel from an app directory, formalizing the strtd8 pattern into repeatable output.

**Scope:**
- Add a `startd8 generate panel <app-dir>` subcommand
- Emit a self-contained `control-panel/` inside the target app
- Interactively offer registration in the shared panel registry (`control-panels/panels.json`)
- Use the existing Control Central framework unchanged (Tier 1 panel; no CC modifications)

**Out of scope:**
- Modifying Control Central itself
- Introducing a new panel tier
- Panels for non-SDK apps (though the primitive can retrofit any app dir; see §3)
- Building the CCCC hub (already exists — a generated panel simply registers into `panels.json` and CCCC picks it up via ENH-3)

## 2. Design Principles

These principles are load-bearing.

- **REQ-SDK-P1 — Additive, never destructive.** `startd8 generate panel` never modifies files outside the new `control-panel/` directory (except the optional, explicitly-consented `panels.json` write in §11). It never alters the app's source, its `pyproject.toml`, its `.env`, or its `Makefile`.
- **REQ-SDK-P2 — Framework-native output.** The generated panel is a **Tier 1** Control Central panel per the framework spec (config-driven `registry.json`, shell scripts, retro-futurism theme). It uses no SDK-specific runtime hooks: the panel works standalone even if the SDK is uninstalled after generation.
- **REQ-SDK-P3 — Idempotent + user-safe regeneration.** Re-running generation on an existing `control-panel/` preserves operator edits. Generated files carry a header marker; regeneration only rewrites unmarked/generated files, or explicitly asks before overwriting edited ones (§12).
- **REQ-SDK-P4 — App-agnostic core, app-aware defaults.** The primitive works on any app directory. When the SDK recognizes the app as its own generated output (FastAPI + alembic + pyproject.toml shape), it wires app-appropriate defaults (uvicorn start, alembic migrate, pytest gates). For unrecognized apps it emits a minimal scaffold and points the operator at the extension points.
- **REQ-SDK-P5 — Optional registration.** panels.json registration is offered interactively (opt-in), never automatic. The operator retains full control over which panels enter the shared registry.

## 3. CLI Surface

### Primitive command

```
startd8 generate panel <app-dir> [options]
```

- **`<app-dir>`** — path to the app the panel will control. May be an SDK-generated app or an arbitrary existing project.

### Options

| Flag | Default | Meaning |
|------|---------|---------|
| `--panel-id <slug>` | derived from `<app-dir>` basename (kebab-case) | Panel ID for `panels.json` and `/health`. Must be kebab-case, ≤30 chars, unique across the registry. |
| `--panel-name "<text>"` | Title-cased app-dir name | Human-readable panel name (masthead + browser tab). |
| `--panel-port <int>` | next available ops-class port (see §10) | Fixed port for the panel. |
| `--app-port <int>` | detected from app (e.g., uvicorn config) or `8000` | Port the app itself listens on; used for the app-status probe and start scripts. |
| `--theme <name>` | `retro-futurism` | Any bundled CC theme name (`retro-futurism`, `mission-control`, `sector-7g`, `six-million`). |
| `--kind <auto\|fastapi\|generic>` | `auto` | Introspection mode (§5). `auto` = detect; `fastapi` = force the FastAPI/uvicorn template; `generic` = minimal scaffold. |
| `--force` | false | Overwrite an existing `control-panel/` without prompting (still preserves marked operator edits per REQ-SDK-P3). |
| `--no-register` | false | Skip the interactive `panels.json` registration prompt entirely. |
| `--dry-run` | false | Print the file plan and detected settings; write nothing. |

### Non-destructive integration

**REQ-SDK-CLI-1:** `startd8 generate panel` is a **separate subcommand**, not folded into other `generate` targets. Existing `startd8 generate backend` (and any other `generate <target>` subcommands) are unchanged. This satisfies REQ-SDK-P1 and lets the same primitive scaffold panels for freshly generated apps *and* retrofit them onto older ones.

**REQ-SDK-CLI-2:** Convenience callers (e.g., a future `startd8 generate backend --with-panel`) may internally invoke this primitive, but the primitive is the source of truth and never depends on other subcommands.

## 4. Generated File Layout

Emitted under `<app-dir>/control-panel/`. Filenames and roles mirror the strtd8 reference (see Appendix A).

```
<app-dir>/control-panel/
├── registry.json               # Panel configuration (REQ-SDK-F1)
├── start.sh                    # CC launcher shim (REQ-SDK-F2)
├── README.md                   # Operator-facing quick-reference (REQ-SDK-F3)
└── scripts/
    ├── _env.sh                 # Shared env loader: venv, app paths, port defaults
    ├── start-app.sh            # App lifecycle: start (detached, non-blocking)
    ├── stop-app.sh             # App lifecycle: stop (SIGTERM to app-port holder)
    ├── restart-app.sh          # App lifecycle: stop + start
    ├── migrate.sh              # Build: alembic head (FastAPI kind only)
    ├── regen-check.sh          # Build: SDK drift check (SDK-generated apps only)
    ├── tests.sh                # Gate: pytest
    ├── compile.sh              # Gate: python -m compileall
    ├── typecheck.sh            # Gate: mypy (skips cleanly if absent)
    ├── doctor.sh               # Gate: preflight (venv / api key / db / port / alembic / CLI)
    ├── probe_venv.sh           # Custom probe: venv presence + basics
    ├── probe_db.sh             # Custom probe: app.db size (or app's DB analogue)
    └── probe_alembic.sh        # Custom probe: current alembic head
```

### File requirements

- **REQ-SDK-F1 — `registry.json`.** Includes `panelId`, `panelPort`, `panelName`, `brand`, `theme.name` (`retro-futurism` default), an `actions` block reflecting the app kind (§6), a `status.custom` block for the probes (§7), and `allowedRunEnvKeys` matching what the scripts consume. Conforms fully to the framework spec's Tier 1 schema.
- **REQ-SDK-F2 — `start.sh`.** Standard CC launcher shim — sets `PANEL_HOME` to the panel's own directory and delegates to the shared CC `start.sh`. Identical shape to every other Tier 1 panel; no SDK-specific logic.
- **REQ-SDK-F3 — `README.md`.** Explains: how to run the panel, what each button does, how status probes are wired, where the app itself lives, and how to regenerate the panel non-destructively. Links back to the framework spec.
- **REQ-SDK-F4 — Script cwd + env discipline.** Every script resolves the app root from its own filesystem location (`$(cd "$(dirname "$0")/../.." && pwd)`) and prefers `<app-dir>/.venv` over the system `python3`. Scripts never hard-code the app root as an absolute path (portable across machines and forks).
- **REQ-SDK-F5 — Generation marker.** Every generated file that could reasonably be re-emitted carries a header comment of the form `# startd8-generated (idempotent): panel-gen v<X.Y.Z>` (or `//` / `<!--` per file type). Regeneration inspects this marker to decide whether it may safely rewrite (§12).

## 5. App Introspection

**REQ-SDK-I1 — Detect app kind (`--kind auto`).** The generator classifies the target app to pick script templates:

| Signal | Kind |
|--------|------|
| `pyproject.toml` + `app/main.py` with FastAPI import + `alembic.ini` | `fastapi` (the SDK's canonical output) |
| Anything else | `generic` |

Additional detectors (Node, Rust, etc.) are out of scope for v0.1 and are the natural extension surface.

**REQ-SDK-I2 — Detect app port.** In order of precedence:
1. `--app-port` flag if provided.
2. A `.env` or `pyproject.toml` value the SDK recognizes (e.g., an `[tool.startd8]` block with `app_port`).
3. Fallback: `8000` for `fastapi`; leave unset (with a TODO in `_env.sh`) for `generic`.

**REQ-SDK-I3 — Detect a .venv.** Look for `<app-dir>/.venv/bin/python`. Record its path in `_env.sh`. If absent, the doctor script reports it as the first missing prerequisite.

**REQ-SDK-I4 — Detect alembic.** If `alembic.ini` is present, wire `migrate.sh` and `probe_alembic.sh`. If absent, omit both — no dead buttons.

## 6. Action Templates

Actions emitted by kind. Every button's `argv` points to a script under `scripts/`; script names match §4.

### Kind = `fastapi` (default template, mirroring strtd8)

| Group | Button | Script | `timeout_s` | `danger` |
|-------|--------|--------|-------------|----------|
| System | Power On | `scripts/start-app.sh` | 30 | – |
| System | Power Off | `scripts/stop-app.sh` | 10 | ✓ |
| System | Reboot | `scripts/restart-app.sh` | 45 | – |
| Build | Drift Check | `scripts/regen-check.sh` | 60 | – |
| Build | Migrate Head | `scripts/migrate.sh` | 120 | ✓ |
| Gates | Run Tests | `scripts/tests.sh` | 600 | – |
| Gates | Compile All | `scripts/compile.sh` | 120 | – |
| Gates | Type Check | `scripts/typecheck.sh` | 300 | – |
| Gates | Doctor | `scripts/doctor.sh` | 60 | – |

### Kind = `generic`

Emit `System` group only (start/stop/restart) plus a `Doctor` button. `migrate.sh`, `regen-check.sh`, and gate scripts are **not** emitted; the operator adds them if useful.

### Rules

- **REQ-SDK-A1 — Non-blocking start.** `start-app.sh` spawns the app **detached** (`nohup ... & disown`) with stdout/stderr to a log under `<app-dir>/logs/` (created on demand). The action returns after polling app health (up to `~10s`). This matches CCCC's own launch discipline and prevents any hang under CC's `POST /run/<key>` subprocess.
- **REQ-SDK-A2 — Stop is idempotent.** `stop-app.sh` on a dead app is a success no-op.
- **REQ-SDK-A3 — Danger flags.** `Power Off` and `Migrate Head` are marked `danger: true` in the registry.
- **REQ-SDK-A4 — `regen-check.sh` is SDK-drift-only.** It calls `startd8 generate backend --check` (or equivalent read-only variant). It never writes files. Emitted only when the SDK detects the app is its own generation output.

## 7. Status Probes

Emitted in `registry.status`. Rendered on the panel's status grid, refreshed every 10 s.

### Endpoint probe (all kinds)

- **REQ-SDK-S1 — App HTTP.** One `endpoints` entry hitting `http://localhost:<app-port>/health` (or `/`, fallback for apps without a health route). Uses the framework's HTTP probe.

### Custom probes (kind-appropriate)

- **REQ-SDK-S2 — Python venv.** `scripts/probe_venv.sh` returns "ready" (exit 0) or "missing" (exit 1). Uses the `raw` parser.
- **REQ-SDK-S3 — DB presence.** `scripts/probe_db.sh` reports the app's DB size (SQLite `app.db` for `fastapi` kind, path derived per app). `raw` parser.
- **REQ-SDK-S4 — Alembic head.** `scripts/probe_alembic.sh` prints the current head (or "no alembic"). `raw` parser. Emitted only if `alembic.ini` exists.

All probes bounded by a 2-second `timeout_ms`.

## 8. Theme

- **REQ-SDK-T1 — Default `retro-futurism`.** Every generated panel gets `theme.name = "retro-futurism"` unless `--theme` overrides.
- **REQ-SDK-T2 — Theme validation.** The generator validates `--theme` against the bundled catalog (`retro-futurism`, `mission-control`, `sector-7g`, `six-million`); unknown themes are rejected with the catalog listed.
- **REQ-SDK-T3 — No custom CSS emitted.** Panels rely on the bundled theme; no `theme.css` overlay is written by the generator (operator may add one later).

## 9. Interactive Registration in `panels.json`

- **REQ-SDK-R1 — Prompt after successful generation.** Unless `--no-register` is set, the generator prints a summary of the entry it would add and asks:
  ```
  Register 'startd8 Console' in the shared control-panels registry? [y/N/skip]
    id: strtd8-console  port: 8994  path: /Users/.../control-panel
    class: ops  tier: 1  proxy: true
  ```
- **REQ-SDK-R2 — `y` writes the entry.** Appends the new entry to `<control-panels>/panels.json` (default path resolved via `CC_PANELS_REGISTRY` env or the canonical path). Also updates `PANELS.md` to keep the human table in sync. Refuses to write if the id or port collides; suggests the next free port and re-asks.
- **REQ-SDK-R3 — `N` or empty prints the snippet.** Renders the JSON entry to stdout for the operator to paste manually.
- **REQ-SDK-R4 — `skip` proceeds silently.** For batch or CI use.
- **REQ-SDK-R5 — Non-interactive safety.** When stdin is not a TTY, the generator falls back to REQ-SDK-R3 behavior (print snippet, exit success). It never writes to `panels.json` in a non-interactive context.
- **REQ-SDK-R6 — `proxy: true` by default.** Generated panels use only relative asset/fetch paths (the bundled CC UI is already relative — REQ-CCCC-X4 in the CCCC spec), so they are proxy-safe. The registration entry sets `proxy: true`.

## 10. Port Allocation

- **REQ-SDK-P-P1 — Default: next free ops-class port.** When `--panel-port` is omitted, the generator reads `panels.json` and picks the next available port in the ops range **8980–8999**, after the highest currently allocated (matching the framework's REQ-PORT-3). Refuses to proceed if the range is exhausted.
- **REQ-SDK-P-P2 — Collision guard.** If `--panel-port` is provided, the generator verifies no active panel already uses that port (via `panels.json`); rejects with a clear error listing the collision.
- **REQ-SDK-P-P3 — Sandbox class opt-in.** `--panel-port` in the range 8780–8799 is allowed for development/experimental apps; the generator writes `"class": "sandbox"` in the registration entry.

## 11. Idempotency & Re-generation

- **REQ-SDK-IDEMP-1 — Marker-driven overwrite.** Files carrying the generation marker (REQ-SDK-F5) are safely overwritten on re-run. Files without the marker (operator-edited or hand-added) are preserved.
- **REQ-SDK-IDEMP-2 — `--force` overwrites everything.** Skips marker checks. The operator is warned before executing.
- **REQ-SDK-IDEMP-3 — Diff summary.** Every non-`--dry-run` run prints a summary of files created / rewritten / preserved / skipped.
- **REQ-SDK-IDEMP-4 — Registry re-sync (optional).** If a panel is already registered in `panels.json` with a different port or path, the generator surfaces the drift and offers to update the registry entry (never silent).

## 12. Non-Goals

- **Not** modifying Control Central. The generated panel uses CC unchanged.
- **Not** introducing a new panel tier. Everything generated is Tier 1.
- **Not** managing app-level infrastructure (databases, containers). The panel controls what the app already exposes.
- **Not** replacing the CCCC hub. Generated panels register into `panels.json` and CCCC picks them up via ENH-3 auto-siblings.
- **Not** requiring the SDK at runtime. Once generated, the panel operates without the SDK installed (regen-check.sh, which shells out to `startd8`, is the sole exception and degrades gracefully when the CLI is absent).

## 13. Open Risks & Design Questions

- **R1 — Detection accuracy for `--kind auto`.** FastAPI apps come in many shapes. First-pass detection (§5 REQ-SDK-I1) targets the SDK's own template. A misclassification into `generic` is safe (fewer buttons emitted, no wrong buttons); the reverse would emit dead buttons. Keep the fastapi detector conservative.
- **R2 — App-port detection for non-SDK apps.** Retrofitting `generic` apps often has no reliable port source. Fallback: emit a `TODO: set APP_PORT` in `_env.sh` and have doctor.sh fail loudly on it. Better than a wrong value.
- **R3 — panels.json write races.** If two `startd8 generate panel` runs execute concurrently, both may pick the same "next free" port. Mitigation: hold an fcntl file lock on `panels.json` during the read-check-write cycle. Low probability in operator flow; still cheap to add.
- **R4 — Six-million as SDK default vs framework default.** The framework spec's default is `retro-futurism`, but strtd8 (the reference) uses `six-million`. This spec adopts `retro-futurism` (REQ-SDK-T1) to align with the framework; operators can `--theme six-million` to match strtd8. Reconsider if operators consistently override.
- **R5 — Tier 2 SDK apps.** Some future SDK-generated apps may want custom UI (Tier 2). Out of scope for v0.1; the primitive would need a separate `--tier 2` mode that emits a `panel_server.py` skeleton. Document as a follow-up.

## 14. Implementation Phases

1. **Phase 0 — Reference alignment.** Read strtd8's `control-panel/` end-to-end (Appendix A) and codify its scripts and registry as the golden template.
2. **Phase 1 — Primitive scaffolding.** `startd8 generate panel <app-dir> --kind generic --dry-run` prints a plan; then `--kind generic` (no `--dry-run`) writes the minimal scaffold. Verify a hand-run panel launches and is visible to CCCC.
3. **Phase 2 — FastAPI kind + probes.** `--kind fastapi` (default when detected) emits the full strtd8-shaped panel with lifecycle, gates, and status probes. Verify against a freshly generated SDK backend.
4. **Phase 3 — Interactive registration.** REQ-SDK-R1–R6. Include lock file (R3), PANELS.md sync, and drift detection (REQ-SDK-IDEMP-4).
5. **Phase 4 — Idempotent regeneration.** Marker-driven overwrite (§11) plus the diff summary.
6. **Phase 5 — Polish.** `--force`, error messages, non-TTY behavior, telemetry (an OTLP span per generation for observability).

---

## Appendix A — strtd8 as Ground Truth

The strtd8 panel is the reference implementation this spec formalizes. Any generator implementation should produce output that is functionally equivalent to strtd8 for a fresh SDK-generated FastAPI backend.

- **Path:** `/Users/neilyashinsky/Documents/dev/strtd8/strtd8/control-panel`
- **Port:** 8994
- **Theme:** `six-million`
- **Registry actions (canonical):** `start-app`, `stop-app`, `restart-app`, `regen-check`, `migrate`, `tests`, `compile`, `typecheck`, `doctor`
- **Scripts (canonical):** `_env.sh`, `start-app.sh`, `stop-app.sh`, `restart-app.sh`, `migrate.sh`, `regen-check.sh`, `tests.sh`, `compile.sh`, `typecheck.sh`, `doctor.sh`, `probe_venv.sh`, `probe_db.sh`, `probe_alembic.sh`
- **App under control:** `uvicorn app.main:app` on `http://localhost:8099/`

Deltas the SDK generator will introduce:
- Default theme flips to `retro-futurism` (REQ-SDK-T1). strtd8's `six-million` remains available via `--theme`.
- `panelId` is explicitly set (strtd8 predates ENH-1).
- Files carry the generation marker (REQ-SDK-F5).
- Registration is offered but not automatic (REQ-SDK-P5).

## Appendix B — Framework Cross-References

Requirements in this doc that inherit from or must remain consistent with the framework spec:

| SDK requirement | Framework anchor |
|-----------------|------------------|
| REQ-SDK-P2 (Tier 1 output) | REQUIREMENTS §5a Tier 1 schema |
| REQ-SDK-F1 (registry.json shape) | REQUIREMENTS §5a Registry Schema Contract |
| REQ-SDK-F2 (`start.sh` shim) | REQUIREMENTS §9 REQ-LAUNCH-1 |
| REQ-SDK-A1 (non-blocking spawn) | CCCC_REQUIREMENTS §5 REQ-CCCC-L1 |
| REQ-SDK-P-P1 (port allocation) | REQUIREMENTS §6 REQ-PORT-3 |
| REQ-SDK-R6 (proxy: true) | CCCC_REQUIREMENTS §6 REQ-CCCC-X4 |
| REQ-SDK-T1 (theme default) | REQUIREMENTS §4 REQ-THEME-1 |
