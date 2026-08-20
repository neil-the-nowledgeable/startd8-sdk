# T0 — Perses coverage map for the generated dashboard vocabulary

**Decision input for:** [ADR_adopt-perses-neutral-dashboard-ir.md](ADR_adopt-perses-neutral-dashboard-ir.md)

**Audit date:** 2026-08-20

**Audited oracle:** Perses `v0.54.0` (`4c719fc19fa21d333797e84c4fe7e3d81c25f4f5`), its published CUE
dependency `perses/spec` `v0.2.0-beta.9` (`ab48cf4fd4a3db157e0250f2814e19e897efa449`), and the exact plugin
versions in that release's
[`scripts/plugin/plugin.yaml`](https://github.com/perses/perses/blob/v0.54.0/scripts/plugin/plugin.yaml).

## Result

**Bound and revise the ADR before a Perses emitter is implemented.** Perses covers the portable
panel/query core, but it does **not** preserve every behavior emitted by the current Grafana v2 path.
The safe adoption boundary is:

- portable: explicit grid placement and titled/collapsible sections; Markdown, time-series, and logs
  panels; PromQL and LogQL queries; datasource references; dashboard-level static-list variables;
- Grafana-only until Perses gains an equivalent: nested tab/section composition, conditional rendering,
  responsive auto-grid, section-scoped variables, and the dashboard-list panel. Flat tab-to-grid layouts
  exist in the pinned Perses schema, but are not needed by the first neutral-core pilot.

This became an **accepted bounded go** on 2026-08-20: build a fail-loud portable-subset emitter, while
continuing to treat arbitrary current Grafana v2 dashboards as not necessarily losslessly portable.

## Evidence base

The inventory uses both production call sites and committed goldens:

- `src/startd8/kickoff_experience/portal_spec_v2.py` emits text, time-series, logs, and dashboard-list
  panels; Prometheus and Loki queries; tabs, rows, grids, conditional visibility, and a dashboard-level
  custom variable.
- `src/startd8/observability/dashboard_renderer_v2.py` emits time-series panels with Prometheus queries,
  thresholds, explicit grid positions, and titled rows.
- `src/startd8/dashboard_creator/v2/sectioned.py` also exposes an open-ended Grafana `viz_config` pass-through.
  That pass-through is **not a finite portable vocabulary** and must remain outside the neutral core.
- The seven `tests/unit/dashboard_creator/fixtures/v2_*.golden.json` files exercise all four Grafana v2
  layout kinds, all three conditional kinds, static variables, text/time-series panels, and query envelopes.

Perses `v0.54.0` defines a dashboard as a panel map plus a list of layouts. Its published `perses/spec`
CUE dependency admits `Grid` and flat `Tabs`; a tab's content is a direct `Grid`, so it does not represent
the current Workbook's nested tab → rows/sections shape. Panel, query, variable, and datasource details are
validated by separately versioned plugin schemas. See the pinned
[`dashboard_patch.cue`](https://github.com/perses/perses/blob/v0.54.0/cue/model/api/v1/dashboard_patch.cue)
and [`layout.cue`](https://github.com/perses/spec/blob/ab48cf4fd4a3db157e0250f2814e19e897efa449/cue/dashboard/layout.cue).

> **Correction recorded 2026-08-20:** the first pass inspected Perses' deprecated generated API layout
> file and incorrectly classified all tabs as unsupported. The release's actual pinned CUE dependency
> supports flat tabs. The portability gap is nested layout composition, not tabs categorically.

## Coverage matrix

| startd8 construct or behavior | Actually emitted by | Perses `v0.54.0` mapping | Fidelity | Disposition |
|---|---|---|---|---|
| Dashboard envelope, metadata name, title, description, tags | all v2 producers | `Dashboard` metadata + `spec.display` | Direct, subject to metadata-field naming | Portable |
| Explicit `GridLayout` (`x/y/width/height`) | sectioned renderer, goldens | `layouts[]: {kind: "Grid", spec.items[]}` | Direct | Portable |
| Titled/collapsible `RowsLayoutRow` | sectioned renderer, Workbook | one Perses `Grid` layout per row, using `spec.display.title/collapse` | Direct for ordered sections | Portable |
| `TabsLayout` | Workbook, fleet golden | `Tabs` exists, but each tab directly owns a `Grid`; Workbook tabs contain nested rows/sections | Direct only for flat tab→grid; lossy for the current Workbook | Flat tabs are a future portable-core extension; current nested shape remains Grafana-only and must fail loudly |
| `AutoGridLayout` | tabs golden, public v2 model | no responsive/auto layout; only explicit `Grid` | Semantic loss if materialized to coordinates | Grafana capability |
| Nested layouts | Workbook and layout goldens | top-level `Grid` or `Tabs`, with tab content limited to `Grid` | Rows can normalize to ordered top-level grids; tab→row→grid nesting cannot be retained | Portable only after validating the relevant normalization; never flatten nested tabs implicitly |
| Markdown/text panel | Workbook, sectioned renderer, goldens | `Markdown` plugin `v0.12.0` | Direct | Portable |
| Time-series panel | Workbook, observability renderer | `TimeSeriesChart` `v0.13.0` | Direct for line/threshold/unit/legend subset; option names require lowering | Portable subset |
| Logs panel | Workbook with a live session | `LogsTable` `v0.3.0` | High; Grafana-only label/dedup/sort options do not all map | Portable with documented option narrowing |
| Dashboard-list panel | portfolio index | no bundled Perses dashboard-list plugin | Unsupported | Grafana capability; keep the index on Grafana or replace it with a separate Perses navigation surface |
| Arbitrary `viz_config` dictionary | `build_sectioned_v2` public seam | unknowable without selecting and validating a plugin schema | Unbounded | Exclude from neutral core; retain only as a Grafana compatibility API |
| Prometheus range query | Workbook, observability renderer | `PrometheusTimeSeriesQuery` `v0.58.0` | Direct (`expr`→`query`, datasource selector) | Portable |
| Loki log query | Workbook with a live session | `LokiLogQuery` `v0.6.0` | Direct (`expr`→`query`, datasource selector) | Portable |
| Grafana `QueryGroup`/`PanelQuery`/`DataQuery` wrappers | queried panels | Perses `Panel.spec.queries[]` with a query plugin | Structural lowering, no semantic loss for the mapped query kinds | Target-specific wrappers, not neutral-core types |
| Datasource reference by name/variable | queried panels | plugin datasource selector/ref | Direct; target syntax differs | Portable |
| Dashboard-level `CustomVariable` with fixed options | Workbook, goldens | core `ListVariable` + `StaticListVariable` `v0.9.0` | Values/multi map; explicit default is withheld because v0.54 CUE leaves `defaultValue` unconstrained while the Go API limits it to string/string-array; display/hide/URL-sync settings differ | Portable subset; explicit current/default fails loudly until the oracle can verify it |
| Section-scoped variables | sectioned/fleet goldens | Perses variables are dashboard-level | Scope loss/name collision risk | Grafana capability |
| Variable/data/time-range conditional rendering | Workbook, conditional golden | no conditional field on Perses layout/panel schema | Unsupported | Grafana capability |
| Panel links | public v2 model | `Panel.spec.links[]` | Direct | Portable |
| Relative time window (`now-6h`→`now`) | default emitter | `spec.duration: "6h"` | Direct for the common relative-duration case | Portable subset |
| Grafana timezone/timepicker/refresh interval list | default emitter | duration + optional single refresh interval only | Partial | Target presentation settings, outside portable core |

The relevant plugin schemas are pinned by tag:

- [`Markdown v0.12.0`](https://github.com/perses/plugins/blob/a62049f1624ee7c62466189ec2ea72b4d64cb31a/markdown/schemas/markdown.cue)
- [`TimeSeriesChart v0.13.0`](https://github.com/perses/plugins/blob/a62049f1624ee7c62466189ec2ea72b4d64cb31a/timeserieschart/schemas/time-series.cue)
- [`LogsTable v0.3.0`](https://github.com/perses/plugins/blob/a62049f1624ee7c62466189ec2ea72b4d64cb31a/logstable/schemas/logstable.cue)
- [`PrometheusTimeSeriesQuery v0.58.0`](https://github.com/perses/plugins/blob/a62049f1624ee7c62466189ec2ea72b4d64cb31a/prometheus/schemas/prometheus-time-series-query/query.cue)
- [`LokiLogQuery v0.6.0`](https://github.com/perses/plugins/blob/a62049f1624ee7c62466189ec2ea72b4d64cb31a/loki/schemas/queries/loki-log-query/query.cue)
- [`StaticListVariable v0.9.0`](https://github.com/perses/plugins/blob/a62049f1624ee7c62466189ec2ea72b4d64cb31a/staticlistvariable/schemas/static-list.cue)

## Decision checkpoint criteria

The ADR may advance only under one of these explicit outcomes:

1. **Lossless go:** every construct used by the selected pilot corpus maps to pinned Perses core/plugin
   schemas without semantic loss.
2. **Bounded go:** every non-mapping construct is named above, excluded from the portable core, and causes
   the Perses lowering to fail loudly with an actionable capability error. Grafana output remains available.
3. **No-go:** a pilot-required behavior is unsupported and neither exclusion nor an approved UX change is
   acceptable. Stop before implementing `to_perses()` or ContextCore CRD output.

Updating a golden file or adding a new production v2 construct must update this matrix. A future Perses
version may move an item across the boundary only after its pinned CUE schema and Dash0 behavior are verified.

## Recommendation

Proceed under **bounded go**. Freeze the typed neutral source core at explicit-grid sections, portable
panels, typed queries/datasource refs, and dashboard-level static-list variables. Keep unsupported
capabilities typed and explicit on the Grafana side; never flatten, drop, or promote their scope implicitly.
The Dash0 pilot should start with the domain-observability dashboard, which stays inside the portable subset,
not the tabbed/conditional Workbook or the dashboard-list index.

## Accepted direction for the gaps

The authorized decider proxy accepted bounded adoption with an upstream-first posture. Each gap remains an
explicit Grafana capability and a fail-loud Perses error until an equivalent ships upstream. startd8 will first
check for existing Perses issues/RFCs, contribute generally useful capabilities where maintainers are receptive,
and consume them only from a pinned released schema after CUE and Dash0 verification. This decision does not
authorize a private Perses fork, a startd8-only schema dialect, or silent degradation while upstream work proceeds.
