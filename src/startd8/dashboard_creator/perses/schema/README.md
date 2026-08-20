# Vendored Perses CUE oracle

This directory is the offline validation oracle used by `dashboard_creator.perses`.

- `oracle.cue` composes the official dashboard model with the exact portable plugin schemas.
- `cue.mod/pkg/` contains unmodified Apache-2.0 CUE sources copied from the releases and commits in
  `SCHEMA-PINS.json`.
- `vendored_cue_tree_sha256` is the SHA-256 of the sorted per-file SHA-256 manifest for every vendored
  `*.cue` file under `cue.mod/pkg`; tests recompute it so drift cannot be silent.
- CUE CLI v0.16.1 is the pinned development/CI tool. Runtime validation fails explicitly when CUE is
  unavailable; it never substitutes a weaker structural validator.

The Perses v0.54.0 repository's CUE module pins `perses/spec` v0.2.0-beta.9, while its Go runtime pins
v0.2.0-rc.0. The oracle follows the published CUE dependency because this is the CUE validation lane.
Before updating any pin, re-run the dual-lowering goldens and the Dash0 pilot.
