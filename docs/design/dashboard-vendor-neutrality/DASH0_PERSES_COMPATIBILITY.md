# Dash0 ↔ startd8 Perses Compatibility Note

**Checked:** 2026-08-20 · **Scope:** public contract + sanitized live-export review; no new Dash0
access or import performed

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

## Empirical live-export profile

The pilot supplied 14 dashboards previously exported through Dash0's live UI. startd8 reviewed
their structure offline and committed only a sanitized aggregate profile—no organization name,
dashboard content, or managed identifier value. All 14 exports consistently use:

- `apiVersion: perses.dev/v1alpha1` and `kind: PersesDashboard`;
- `dash0.com/dataset` and `dash0.com/id` metadata labels, with dataset `default`;
- `spec.display`, `duration`, `layouts`, `panels`, and `variables`;
- `TimeSeriesChart` or `GaugeChart`, `TimeSeriesQuery`, and `PrometheusTimeSeriesQuery`;
- units `bytes`, `counts/sec`, `milliseconds`, and `percent-decimal`;
- no explicit datasource object in any query.

The aggregate contract is pinned in
`tests/unit/dashboard_creator/fixtures/dash0_live_export_profile.golden.json`. The offline comparison
test proves the pilot artifact's panel, query, plugin, and layout-reference core agrees with that
observed profile while keeping every known delta explicit.

## Compatibility conclusion

The documented Dash0 UI contract and the emitted startd8 artifact agree at the input boundary:
Dash0 says external Perses JSON is accepted directly, and startd8 emits validated native Perses JSON.
The live exports additionally prove that Dash0's managed saved form is a `perses.dev/v1alpha1`
`PersesDashboard` with Dash0 labels. They do not prove that this exact bare startd8 artifact imports;
that remains the live pilot gate.

One point remains intentionally unclaimed: Dash0's public documentation does not identify the exact
Perses core/spec/plugin release its importer currently implements. Therefore v0.54.0-to-Dash0 runtime
compatibility cannot be declared proven until the pilot team imports this exact artifact and records
the response. That is T7. G3's shape/version question is empirically bounded; its authorization and
current target confirmation remain open.

### Known, test-pinned deltas

| Concern | startd8 pilot input | Observed Dash0 saved form | Pilot treatment |
|---|---|---|---|
| Envelope | bare `kind: Dashboard` | `perses.dev/v1alpha1` `PersesDashboard` | Import unchanged; record saved normalization |
| Metadata | Perses `project` + tags | Dash0 dataset + managed-ID labels | Never fabricate a Dash0 ID |
| Variables | omitted when empty | `variables: []` | Record if Dash0 adds it |
| Datasource | explicit `default` Prometheus datasource | omitted in all 14 exports | Record whether Dash0 accepts/removes it |
| Units | `seconds`, `decimal`, `percent-decimal` | observed set includes only `percent-decimal` of those three | Verify display; `seconds`/`decimal` remain empirical risks |
| Metrics | three synthetic `startd8_*` names | demo exports query `traces_span_metrics_*`/HTTP metrics | First pilot tests format; no-data may be expected |

## Import-path recommendation

Use the UI **Edit as JSON** upload for the first pilot. It is the most direct documented path for an
external native Perses JSON document and keeps format diagnosis visible to the human operator.

Do not assume the Dash0 CLI accepts this exact bare external-Perses envelope. Its documented
configuration-as-code forms add either `apiVersion: dash0.com/v1alpha1` plus Dash0 metadata, or a
`perses.dev/*` `PersesDashboard` CRD wrapper. Those are useful post-pilot managed forms, and the 14
live exports confirm the CRD is Dash0's saved shape, but it is not byte-identical to the
vendor-neutral artifact. Stable re-application requires a Dash0-managed identifier. Do not add a
fabricated Dash0 ID or wrapper to the neutral golden merely to optimize a one-time pilot.

## Compatibility stop conditions

Stop and return evidence to startd8 if any of these occurs:

- Dash0 rejects the bare input or requires a hand edit before acceptance.
- Dash0 changes a panel, query, plugin kind, layout reference, threshold, or unit.
- Dash0 cannot resolve the `default` Prometheus datasource.
- Dash0 accepts a panel the pinned CUE oracle rejects, or rejects one the oracle accepts.
- Dash0's exported saved form cannot be reconciled to the expected CRD/label/datasource normalization.

Changing the accepted bare `Dashboard` into the observed managed `PersesDashboard`, adding Dash0
labels, adding `variables: []`, or omitting the datasource is not automatically a failure. Capture
the exact post-import export and compare it with the pinned delta table. Any other outcome is a
version/interop finding and must not be hidden by hand-editing the pilot artifact.
