# Dash0 ↔ startd8 Perses Compatibility Note

**Checked:** 2026-08-20 · **Scope:** public contract review only; no Dash0 access or import performed
**startd8 pin:** Perses v0.54.0 CUE schema + CUE CLI v0.16.1

## Confirmed from Dash0's current public documentation

- Dash0 dashboards are built on the Perses open standard and expose their underlying Perses JSON.
  [About Dashboards](https://www.dash0.com/docs/dash0/dashboards/about-dashboards) ·
  [Manage Dashboards](https://www.dash0.com/docs/dash0/dashboards/manage-existing-dashboards)
- Dash0's UI import explicitly accepts external Perses JSON directly through the dashboard editor's
  **Edit as JSON** upload path.
  [Import Dashboards](https://www.dash0.com/docs/dash0/dashboards/import-dashboards)
- Dash0's CLI recognizes its native `dash0.com/v1alpha1` `Dashboard` envelope and PersesDashboard
  CRDs. The CRD lane documents `perses.dev/v1alpha1` and `perses.dev/v1alpha2`; `dash0 apply -f FILE
  --dry-run` validates those managed-asset forms without applying.
  [Dash0 CLI command reference](https://www.dash0.com/docs/dash0/miscellaneous/tooling/dash0-cli/commands)
- Dash0 also supports PersesDashboard CRDs through its Kubernetes operator and Perses-format YAML
  through its Terraform provider.
  [Manage Dashboards as Code](https://www.dash0.com/docs/dash0/dashboards/manage-dashboards-as-code)

## startd8 artifact shape

The pilot artifact is native Perses JSON:

- `kind: Dashboard`
- `metadata.name`, `metadata.project`, and `metadata.tags`
- `spec.display`, `spec.duration`, `spec.panels`, and `spec.layouts`
- `TimeSeriesChart` panels with `PrometheusTimeSeriesQuery` queries
- explicit `PrometheusDatasource` reference named `default`

It is generated from the bounded neutral model and passes the vendored Perses v0.54.0 CUE oracle.
It is deliberately **not** wrapped in a Kubernetes `PersesDashboard` CRD and carries no Dash0-only
extension or credential.

## Compatibility conclusion

The documented Dash0 UI contract and the emitted startd8 artifact agree at the format boundary:
Dash0 says external Perses JSON is accepted directly, and startd8 emits validated native Perses JSON.

One point remains intentionally unclaimed: Dash0's public documentation does not identify the exact
Perses core/spec/plugin release its importer currently implements. Therefore v0.54.0-to-Dash0 runtime
compatibility cannot be declared proven until the pilot team imports this exact artifact and records
the response. That is G3/T7, not a reason to mutate the artifact speculatively.

## Import-path recommendation

Use the UI **Edit as JSON** upload for the first pilot. It is the most direct documented path for an
external native Perses JSON document and keeps format diagnosis visible to the human operator.

Do not assume the Dash0 CLI accepts this exact bare external-Perses envelope. Its documented
configuration-as-code forms add either `apiVersion: dash0.com/v1alpha1` plus Dash0 metadata, or a
`perses.dev/*` `PersesDashboard` CRD wrapper. Those are useful post-pilot managed forms, but they are
not byte-identical to the vendor-neutral artifact. Also, stable CLI re-application requires a
Dash0-managed identifier. Do not add a fabricated Dash0 ID or wrapper to the neutral golden merely
to optimize a one-time pilot.

## Compatibility stop conditions

Stop and return evidence to startd8 if any of these occurs:

- Dash0 rejects the file before rendering.
- Dash0 accepts it only after changing the resource envelope or plugin kind.
- Dash0 cannot resolve the `default` Prometheus datasource.
- Dash0 accepts a panel the pinned CUE oracle rejects, or rejects one the oracle accepts.
- Layout coordinates, thresholds, units, or queries change during import.

These outcomes are version/interop findings. They must update the pin or lowering explicitly; they
must not be hidden by hand-editing the pilot artifact.
