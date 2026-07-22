# Requirements — Profile-aware `verify`/`doctor` + expose them as `capdevpipe` verbs

Status: draft (v0.1) · Seeds: enhancement-backlog finding #2 (`CAPDEVPIPE_RUN_ENHANCEMENT_BACKLOG.md`)
· Relates: issue #220 (config-free run), companion `cap-dev-pipe#2` (orchestrator wrapper)

## Why this needs requirements (the mis-size that grounding caught)

The backlog filed #2 as *"pure wiring — no new logic: add `capdevpipe verify`/`doctor` over the
existing installer methods."* Grounding the methods **falsified that**:

- `CapDevPipeInstaller.verify()` (`capdevpipe_installer.py:1295-1359`) hard-requires an embedded
  **`run.sh`** and runs `run.sh --list-langs`; its `single_source_ok` requires `design/` **and**
  `prompts/` **and** `run.sh` (`:1308-1312`).
- `doctor()` (`:1456-1490`) falls through to `verify()` when the source is intact.
- But **`run.sh` is a `full`-profile-only script** (`~/Documents/dev/cap-dev-pipe/embed-manifest.yaml`:
  `full.scripts` includes `run.sh`; `orchestrator`/`minimal` do not). The `orchestrator` profile —
  the exact one issue #220 is about — ships `run-cap-delivery.sh`, `run-plan-ingestion.sh`, etc.,
  and **no `run.sh`**.

**Consequence:** on a *healthy* orchestrator (or minimal) install, `verify()` and `doctor()` both
return `passed=False` with "Embedded run.sh not found." Exposing them as CLI verbs unchanged would
hand every non-`full` user a false FAILED at the exact moment they're debugging a run. So the verb
exposure is **blocked on** making verify profile-aware. Two coupled changes, one of which is real.

## The latent lever (wire what exists)

The installer already persists what verify needs to be profile-aware: `Manifest.embed_profile` and
`Manifest.managed_paths` — the resolved top-level entry set (scripts + aliases + packages +
resource trees + copy_files) for the install's profile, written at `capdevpipe_installer.py:805-813`
via `_resolved_managed_paths()` (`:835-857`). `managed_paths` was added *for exactly this* (canonical
`verify_embed`/`repair_embed` interop). verify currently ignores it and hardcodes `run.sh`. Reading
it converts a hardcoded assumption into a single-sourced, profile-correct check.

## Functional requirements

- **FR-1 — Profile-aware runnable check.** `verify()` selects its liveness probe from the install's
  profile (via `Manifest.managed_paths` / `embed_profile`), not a hardcoded `run.sh`:
  - If `run.sh` ∈ `managed_paths` (`full`) → keep the existing `run.sh --list-langs` check.
  - Else (`orchestrator`/`minimal`) → probe the profile's actual entrypoint(s) present on disk
    (e.g. `run-cap-delivery.sh` for orchestrator) — existence + executable bit — and do **not**
    require `run.sh`. A `--list-langs` equivalent is out of scope where the profile has no lang
    listing (OQ-1).
- **FR-2 — Profile-aware single-source check.** `single_source_ok` requires only the resource trees
  the profile actually declares: `design/` for all profiles; `prompts/` only when `prompts` ∈
  `managed_paths` (orchestrator+); never `run.sh` for a profile that excludes it.
- **FR-3 — Manifest-absent degradation.** When no manifest is readable (`read_manifest` → None),
  verify must not crash or assume `full`. It degrades to a filesystem-only structural check
  (embed dir + `pipeline/` package present, at least one known entrypoint present) and says so in
  its message, rather than falsely failing on a missing `run.sh`. (Mirrors the existing
  "re-derive from disk" posture at `capdevpipe_installer.py:873-904`.)
- **FR-4 — Expose `capdevpipe verify`.** New CLI command (`cli_capdevpipe.py`) taking
  `--target-root` (default cwd), constructing no full `InstallConfig` (verify needs only the
  target), calling `installer.verify()`, rendering pass/fail, exiting 0/1.
- **FR-5 — Expose `capdevpipe doctor`.** As FR-4 for `installer.doctor()` (adds the dangling-source
  relocation diagnostic). Both reuse a shared render helper.
- **FR-6 — Honest render for the no-install case.** Running `verify`/`doctor` where no
  `.cap-dev-pipe/` exists reports "no install found here" with the install hint — not a stack trace
  or a confusing structural failure. (`detect_existing().exists` is the gate — `:1363-1367`.)

## Non-functional / guardrails

- **NFR-1 — No false pass.** A genuinely broken `full` install must still fail exactly as today;
  profile-awareness only removes false *failures*, it must not introduce false *passes*.
- **NFR-2 — Read-only.** `verify`/`doctor` are diagnostics: no writes, no repair side effects
  (repair stays behind `install --rerun-mode repair`). Aligns with the MEMORY "a check must be
  READ-ONLY" rule.
- **NFR-3 — Single-source the profile set.** Derive expected entrypoints from
  `managed_paths`/canonical inventory, never a second hardcoded per-profile list in the SDK
  (avoid a new drift seam vs `embed-manifest.yaml`).

## Grounding note (belief → actual)

| Believed | Actual | Consequence |
|---|---|---|
| verify/doctor are profile-agnostic; exposing them is pure wiring | Both hard-require `run.sh`, a `full`-only script | Orchestrator/minimal installs falsely FAIL → verb exposure is blocked on FR-1/2/3 |
| I'd need a new per-profile entrypoint table | `Manifest.managed_paths` already carries the resolved set, persisted for exactly this | FR-1/2 are wiring an existing single-source, not authoring a new one |

## Open questions

- **OQ-1** — For non-`full` profiles, is there a meaningful liveness probe beyond "entrypoint file
  exists + executable"? `run-cap-delivery.sh --help`/dry equivalent? Or is existence enough for a
  read-only health verb? (Leaning: existence + exec bit for v1; a real invocation risks side
  effects, violating NFR-2.)
- **OQ-2** — Should `verify` accept `--embed-dir` (like `run`) for a non-cwd embed, or is
  `--target-root` sufficient? (Leaning: mirror `run`'s `--embed-dir` for consistency.)
- **OQ-3** — Does the canonical `pipeline verify`/`verify_embed` already implement profile-aware
  verification we should delegate to (as the installer delegates embed planning), rather than
  re-implement FR-1/2 in the SDK? Check `~/Documents/dev/cap-dev-pipe/pipeline/` before building.

## Effort

FR-4/5/6 (verb exposure + render) once verify is correct: **S**. FR-1/2/3 (profile-aware verify):
**S/M** — small, but load-bearing and test-heavy (each profile × healthy/broken/manifest-absent).
Do **not** ship the verbs (FR-4/5) without FR-1/2/3, or the headline diagnostic lies for the exact
audience #220 serves. **Resolve OQ-3 first** — if canonical already does this, the SDK side collapses
to delegation.
