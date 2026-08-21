# Requirements — Live Perses Dashboard Generation

**Version:** 0.1 · **Date:** 2026-08-20 · **Status:** Implemented

**Parent decision:** `ADR_adopt-perses-neutral-dashboard-ir.md`

**Readiness gates:** `PILOT_NEXT_STEPS_dash0.md` G1, G2, and G4

## 1. Problem

The bounded neutral dashboard model, deterministic Perses v0.54.0 lowering, and pinned CUE oracle
are implemented, but only callable as Python library APIs. The Dash0 pilot needs a supported command
that produces a validated Perses Dashboard resource without asking operators to write Python or
bypassing the neutral model.

The existing `startd8 dashboard create SPEC_FILE` command consumes the legacy Grafana
`DashboardSpec` path. That schema contains Grafana-only constructs and is not the source of the
portable model. The first real portable producer is domain observability:

`observability.yaml → ObservabilitySpec → neutral Dashboard → target lowering`.

## 2. Decisions

- Add `--target grafana|perses` to `dashboard create`; `grafana` remains the default and preserves the
  existing workflow byte-for-byte.
- With `--target perses`, `SPEC_FILE` is an `observability.yaml` document and is parsed only through
  `from_observability_yaml`, then projected by `build_domain_dashboard_neutral`.
- `--project` supplies both the domain dashboard identity and Perses metadata project. It defaults to
  `default` and must be a safe lowercase identifier.
- Perses output is canonical JSON named `<dashboard-name>.perses.json` in `--output-dir` or the
  existing `.startd8/dashboards` default.
- The live path always invokes pinned-CUE validation. There is no CLI escape hatch to disable it.

## 3. Functional requirements

- **FR-1 — Explicit target.** `dashboard create` MUST accept `--target grafana|perses`. Omitting the
  option MUST execute the existing Grafana path with the same inputs and behavior.
- **FR-2 — Neutral producer.** The Perses target MUST parse `SPEC_FILE` as `observability.yaml`, build
  an `ObservabilitySpec`, and call `build_domain_dashboard_neutral`. It MUST NOT translate the legacy
  Grafana `DashboardSpec` into a nominally neutral shape.
- **FR-3 — Mandatory validation.** Every Perses CLI generation and check MUST call
  `emit_perses_dashboard(validate=True)`. Missing CUE or schema rejection MUST fail the command with
  an actionable error and MUST NOT write an artifact.
- **FR-4 — Deterministic persistence.** A successful write MUST use `perses_json()` bytes, an atomic
  replace, and a deterministic `<name>.perses.json` filename.
- **FR-5 — Check mode.** `--check` MUST fully parse, lower, and CUE-validate without creating or
  modifying the output artifact. Exit 0 means the candidate is valid; exit 1 means it is not.
- **FR-6 — Dry run.** `--dry-run` MUST fully parse, lower, and CUE-validate without writing. It remains
  mutually exclusive with `--check`, matching the established dashboard CLI contract.
- **FR-7 — Target-specific options.** Grafana-only options (`--provision`, `--grafana-url`,
  `--allow-insecure`, `--persist-source`, and `--config`) MUST fail loudly with `--target perses`.
  The SDK does not provision or import into Dash0 in this phase.
- **FR-8 — Template.** `--print-template --target perses` MUST print a minimal valid
  `observability.yaml` input rather than the legacy Grafana dashboard-spec template.
- **FR-9 — Pilot artifact.** The repository MUST contain one real sample input and the canonical
  Perses output generated through this command. CI MUST assert regeneration is byte-identical and
  passes the pinned CUE oracle.

## 4. Non-functional requirements

- **NR-1 — Additive safety.** No existing Grafana default, output schema, provisioning behavior, or
  test expectation changes when `--target` is omitted.
- **NR-2 — Fail loud.** Unsupported neutral capabilities and unavailable validation are errors, never
  warnings or silent drops.
- **NR-3 — Offline generation.** Generation and validation require no dashboard vendor endpoint and
  the Perses generation module makes no network call.
- **NR-4 — Credential boundary.** No Dash0 endpoint, token, or credential is accepted or persisted by
  this command.
- **NR-5 — Pinned contract.** The validation contract remains Perses v0.54.0 with CUE v0.16.1 until an
  explicit pin update is reviewed.

## 5. Acceptance

1. Existing `dashboard create` tests prove omitted/explicit `grafana` dispatches to the legacy workflow.
2. Perses CLI tests prove write, `--check`, `--dry-run`, malformed input, unavailable CUE, and
   Grafana-only-option rejection.
3. The real CUE accept/reject tests run without skips locally and in CI.
4. Regenerating the committed pilot artifact through the CLI produces no diff.
5. No Dash0 import or external mutation is performed by this work.
