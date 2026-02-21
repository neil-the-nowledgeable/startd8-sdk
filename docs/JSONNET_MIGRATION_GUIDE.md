# Jsonnet Dashboard Migration Guide

How to migrate hand-authored Grafana JSON dashboards to a jsonnet-first generation pipeline using the kubernetes-mixin pattern. This guide documents the exact process used to create `startd8-mixin/` in the startd8-sdk repo, with full file paths for repeatability.

## Prerequisites

```bash
brew install jsonnet go-jsonnet jsonnet-bundler
```

Verify:
```bash
jsonnet --version    # Jsonnet commandline interpreter (Go implementation) v0.21.0+
jsonnetfmt --help    # Should exist
jb --help            # jsonnet-bundler
```

## Reference Implementation

The wayfinder project has the mature reference mixin that startd8-mixin was adapted from:

```
/Users/neilyashinsky/Documents/dev/wayfinder/wayfinder-mixin/
├── config.libsonnet              # Datasource UIDs, metric names, tags
├── mixin.libsonnet               # Entry point aggregating dashboards + alerts + rules
├── Makefile                      # Build system (generate, test, lint, fmt, install)
├── jsonnetfile.json              # Dependency: grafonnet
├── lib/
│   ├── dashboards.libsonnet      # dashboard() wrapper + withPanels() auto-layout
│   ├── panels.libsonnet          # 12 panel constructors (stat, gauge, timeseries, etc.)
│   ├── variables.libsonnet       # Template variable builders
│   ├── alerts.libsonnet          # lokiAlert() + mimirAlert() helpers
│   └── rules.libsonnet           # lokiRule() + mimirRule() helpers
├── dashboards/
│   ├── core/                     # 6 core dashboards
│   ├── beaver/                   # Project-specific dashboards
│   └── squirrel/                 # Project-specific dashboards
├── alerts/
│   ├── contextcore.libsonnet     # 4 alert rules
│   └── fox.libsonnet             # 1 alert rule
├── rules/
│   ├── loki.libsonnet            # 5 Loki recording rules
│   └── mimir.libsonnet           # 1 Mimir recording rule
└── tests/
    └── smoke_test.jsonnet        # Compilation verification
```

The startd8-mixin adapts this pattern with two additions to `lib/panels.libsonnet`:
- `barchart()` — bar chart panel (used for distribution comparisons)
- `logs()` — Loki log panel

## Step-by-Step Migration Process

### Step 1: Create the directory scaffold

```bash
cd <your-repo>
mkdir -p <name>-mixin/{lib,dashboards,alerts,rules,tests,generated/dashboards,generated/alerts}
```

For startd8-sdk this was:
```bash
mkdir -p startd8-mixin/{lib,dashboards,alerts,rules,tests,generated/dashboards,generated/alerts}
```

### Step 2: Create `jsonnetfile.json`

This declares the grafonnet dependency. Copy verbatim — every mixin uses the same dependency.

```json
{
  "version": 1,
  "dependencies": [
    {
      "source": {
        "git": {
          "remote": "https://github.com/grafana/grafonnet.git",
          "subdir": "gen/grafonnet-latest"
        }
      },
      "version": "main"
    }
  ]
}
```

**Reference**: `/Users/neilyashinsky/Documents/dev/wayfinder/wayfinder-mixin/jsonnetfile.json`
**Created**: `/Users/neilyashinsky/Documents/dev/startd8-sdk/startd8-mixin/jsonnetfile.json`

### Step 3: Create the Makefile

The Makefile provides five targets: `generate`, `test`, `lint`, `fmt`, `install`. The structure is identical across mixins — only the path and the presence/absence of rules sections changes.

Key details:
- Dashboard generation uses `jsonnet -e` piped to a Python one-liner that splits the JSON object into individual files
- Alert/rule YAML generation uses `jsonnet -S -e 'std.manifestYamlDoc(...)'` — the `-S` flag is critical to avoid double-serialization (without it, jsonnet wraps the YAML string in JSON quotes)
- If your mixin has no recording rules, omit the rules generation lines

**Reference**: `/Users/neilyashinsky/Documents/dev/wayfinder/wayfinder-mixin/Makefile`
**Created**: `/Users/neilyashinsky/Documents/dev/startd8-sdk/startd8-mixin/Makefile`

The wayfinder Makefile includes Loki rules and Mimir rules sections that startd8-mixin omits (no recording rules defined yet). If your project has recording rules, add:
```makefile
@$(JSONNET) -S -J vendor -e 'std.manifestYamlDoc((import "mixin.libsonnet").lokiRules)' > $(RULES_DIR)/loki-rules.yaml
@$(JSONNET) -S -J vendor -e 'std.manifestYamlDoc((import "mixin.libsonnet").mimirRules)' > $(RULES_DIR)/mimir-rules.yaml
```

### Step 4: Create `config.libsonnet`

This is the most project-specific file. It centralizes everything that varies between projects:

```jsonnet
{
  _config+:: {
    // Datasource UIDs — override to match your Grafana instance
    datasources: {
      tempo: { uid: 'tempo', type: 'tempo' },
      loki: { uid: 'loki', type: 'loki' },
      mimir: { uid: 'mimir', type: 'prometheus' },
    },

    // Dashboard defaults
    dashboardTags: ['<your-project>'],
    dashboardRefresh: '30s',
    dashboardTimeFrom: 'now-6h',
    dashboardTimeTo: 'now',

    // Metric names — one entry per Prometheus metric your dashboards use
    metrics: {
      metricOne: 'your_project_metric_one',
      metricTwo: 'your_project_metric_two',
      // ...
    },

    // Alert thresholds
    alertThresholds: {
      someRate: 0.05,
      someBudget: 100,
    },
  },
}
```

**Where to find your metric names:**
- Observability manifests (e.g., `/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/capability-index/startd8.observability.manifest.yaml`)
- Existing JSON dashboards — grep for `"expr"` fields to find all PromQL metric references
- OTel instrumentation code — search for `meter.create_counter()`, `meter.create_histogram()`, etc.

**Reference**: `/Users/neilyashinsky/Documents/dev/wayfinder/wayfinder-mixin/config.libsonnet`
**Created**: `/Users/neilyashinsky/Documents/dev/startd8-sdk/startd8-mixin/config.libsonnet`

### Step 5: Create lib/ helpers

These five files are largely project-agnostic and can be copied from the reference with minimal changes.

#### `lib/dashboards.libsonnet`

Provides two functions:
- `dashboard(title, uid, description, tags)` — Creates a standard dashboard skeleton with annotations, schema version, refresh rate, and tags from config
- `withPanels(dashboard, panels)` — Appends panels to the dashboard, auto-assigning `id` and `gridPos` for panels that don't specify their own

Copy verbatim from the reference. No project-specific changes needed.

**Reference**: `/Users/neilyashinsky/Documents/dev/wayfinder/wayfinder-mixin/lib/dashboards.libsonnet`
**Created**: `/Users/neilyashinsky/Documents/dev/startd8-sdk/startd8-mixin/lib/dashboards.libsonnet`

#### `lib/panels.libsonnet`

Panel constructor functions. The wayfinder reference has 12 constructors:

| Function | Panel Type | Datasource Default |
|----------|------------|-------------------|
| `stat()` | Single value stat | Prometheus |
| `gauge()` | Gauge with thresholds | Prometheus |
| `timeseries()` | Time series line/bar chart | Prometheus |
| `table()` | Data table | Prometheus |
| `barGauge()` | Horizontal bar gauge | Prometheus |
| `piechart()` | Pie/donut chart | Prometheus |
| `histogram()` | Distribution histogram | Prometheus |
| `row()` | Section header row | N/A |
| `traceqlStat()` | Stat from TraceQL | Tempo |
| `traceqlTable()` | Table from TraceQL | Tempo |
| `traceqlTimeseries()` | Timeseries from TraceQL | Tempo |
| `traceqlGauge()` | Gauge from TraceQL | Tempo |

**Adding new panel types**: If your existing dashboards use panel types not in the reference (e.g., `barchart`, `logs`, `traces`, `text`), add constructors following the same pattern. For startd8-mixin, we added:

- `barchart(title, targets, datasource, unit, orientation, stacking, showValue, decimals)` — Grafana bar chart (distinct from `barGauge`)
- `logs(title, expr, datasource, maxLines)` — Loki log panel
- `traces(title, query, datasource)` — Tempo trace viewer
- `text(title, content)` — Markdown text panel

Each constructor returns a panel object with `title`, `type`, `datasource`, `targets`, `fieldConfig`, and `options`. The pattern is consistent: required params first, optional params with defaults.

**Reference**: `/Users/neilyashinsky/Documents/dev/wayfinder/wayfinder-mixin/lib/panels.libsonnet`
**Created**: `/Users/neilyashinsky/Documents/dev/startd8-sdk/startd8-mixin/lib/panels.libsonnet`

#### `lib/variables.libsonnet`

Template variable builders. The wayfinder reference has 4:
- `prometheusDatasource()` — Mimir/Prometheus datasource selector
- `tempoDatasource()` — Tempo datasource selector
- `lokiDatasource()` — Loki datasource selector
- `projectVariable(metric)` — Dynamic project selection from `label_values()`

For startd8-mixin, we added project-specific variable builders:
- `serviceNameVariable()` — Custom variable defaulting to the service name from config
- `modelVariable(metric)` — `label_values(metric, model)` with multi-select
- `agentVariable(metric)` — `label_values(metric, agent_name)` with multi-select
- `customVariable(name, label, query, multi)` — Generic custom variable
- `constantVariable(name, value)` — Hidden constant variable

Add variable builders for whatever label dimensions your dashboards filter on.

**Reference**: `/Users/neilyashinsky/Documents/dev/wayfinder/wayfinder-mixin/lib/variables.libsonnet`
**Created**: `/Users/neilyashinsky/Documents/dev/startd8-sdk/startd8-mixin/lib/variables.libsonnet`

#### `lib/alerts.libsonnet` and `lib/rules.libsonnet`

Copy verbatim. These are simple helper functions that produce the correct Prometheus/Loki alert/rule structure.

**Reference**: `/Users/neilyashinsky/Documents/dev/wayfinder/wayfinder-mixin/lib/alerts.libsonnet`
**Reference**: `/Users/neilyashinsky/Documents/dev/wayfinder/wayfinder-mixin/lib/rules.libsonnet`
**Created**: `/Users/neilyashinsky/Documents/dev/startd8-sdk/startd8-mixin/lib/alerts.libsonnet`
**Created**: `/Users/neilyashinsky/Documents/dev/startd8-sdk/startd8-mixin/lib/rules.libsonnet`

### Step 6: Migrate each JSON dashboard to libsonnet

This is the bulk of the work. For each existing JSON dashboard:

#### 6a. Read the JSON dashboard and extract its structure

Open the JSON file and note:
- `uid` — Preserve exactly (Grafana uses this for bookmarks/links)
- `title` and `description`
- `tags`
- `templating.list` — All template variables (name, type, query, datasource, multi, allValue)
- `annotations` — Custom annotations beyond the default
- `time` — Default time range if different from config
- Every panel: `type`, `title`, `gridPos`, `targets` (full query expressions), `fieldConfig` (unit, decimals, thresholds, color overrides), `options`

For startd8-sdk, the source dashboards were:
```
/Users/neilyashinsky/Documents/dev/startd8-sdk/dashboards/startd8-sdk-overview.json
/Users/neilyashinsky/Documents/dev/startd8-sdk/dashboards/startd8-cost-tracking.json
/Users/neilyashinsky/Documents/dev/startd8-sdk/dashboards/startd8-sdk-metrics.json
/Users/neilyashinsky/Documents/dev/startd8-sdk/dashboards/lead-contractor-progress.json
/Users/neilyashinsky/Documents/dev/startd8-sdk/out/grafana_dashboard_artisan_contractor.json
```

#### 6b. Write the libsonnet file

Every dashboard libsonnet follows this structure:

```jsonnet
// Description comment.
// Migrated from <original-path>
local config = (import '../config.libsonnet')._config;
local dashboards = import '../lib/dashboards.libsonnet';
local panels = import '../lib/panels.libsonnet';
local variables = import '../lib/variables.libsonnet';

local m = config.metrics;  // Shorthand for metric names

// Datasource references (use template variable UIDs)
local mimirDatasource = { type: 'prometheus', uid: '${datasource}' };
local lokiDatasource = { type: 'loki', uid: '${loki}' };
local tempoDatasource = { type: 'tempo', uid: '${tempo}' };

// Create base dashboard
local baseDashboard = dashboards.dashboard(
  '<Title>',
  '<uid>',                    // Must match original UID exactly
  description='<description>',
  tags=['<extra>', '<tags>'],  // Beyond config.dashboardTags
) {
  // Override time range if different from config default
  time: { from: 'now-24h', to: 'now' },
  // Template variables
  templating: {
    list: [
      variables.prometheusDatasource(),
      variables.lokiDatasource(),
      // ... project-specific variables
    ],
  },
};

// Add panels
dashboards.withPanels(baseDashboard, [
  // Row headers
  panels.row('Section Name', y=0),

  // Each panel with explicit gridPos to match original layout
  panels.stat(
    'Panel Title',
    'sum(%s{label=~"$var"})' % m.metricName,  // Use config metric names
    datasource=mimirDatasource,
    unit='currencyUSD',
    thresholds=[
      { color: 'green', value: null },
      { color: 'red', value: 100 },
    ],
  ) { gridPos: { h: 6, w: 6, x: 0, y: 1 } },

  // ... more panels
])
```

#### 6c. Key translation patterns

**PromQL targets** — Replace hardcoded metric names with config references using string formatting:
```jsonnet
// JSON: "expr": "sum(startd8_cost_total{service_name=~\"$service_name\"})"
// Jsonnet:
{ expr: 'sum(%s{%s})' % [m.costTotal, sel.serviceName], refId: 'A', legendFormat: '{{model}}' }
```

**Multiple targets** — The `timeseries()`, `barchart()`, `piechart()`, and `table()` constructors accept a `targets` array:
```jsonnet
panels.timeseries('Title', [
  { expr: '...', refId: 'A', legendFormat: '...' },
  { expr: '...', refId: 'B', legendFormat: '...' },
])
```

**Single-target constructors** — `stat()`, `gauge()`, and `barGauge()` take a single `expr` string (not an array).

**Field config overrides** — Use jsonnet's `+` merge operator to add customizations beyond what the constructor provides:
```jsonnet
panels.timeseries(...) {
  gridPos: { h: 8, w: 12, x: 0, y: 10 },
  fieldConfig+: {
    defaults+: { decimals: 4, color: { fixedColor: 'red', mode: 'fixed' } },
  },
}
```

**Color overrides by series name** — Pass an `overrides` array:
```jsonnet
overrides=[
  { matcher: { id: 'byName', options: 'P50' }, properties: [{ id: 'color', value: { fixedColor: 'green', mode: 'fixed' } }] },
  { matcher: { id: 'byName', options: 'P99' }, properties: [{ id: 'color', value: { fixedColor: 'red', mode: 'fixed' } }] },
]
```

**TraceQL panels** — Use the `traceql*` constructors. The target format differs from PromQL:
```jsonnet
panels.traceqlStat(
  'Completed Tasks',
  '{resource.project.id = "$project" && span.task.status = "done"}',
  datasource=tempoDatasource,
  thresholds=[{ color: 'green', value: null }],
)
```

**Table transformations** — Pass as a `transformations` parameter:
```jsonnet
panels.table('Title', targets, transformations=[
  { id: 'merge', options: {} },
  { id: 'organize', options: { excludeByName: { Time: true }, renameByName: { 'Value #A': 'Requests' } } },
])
```

**Collapsed rows** — Use `panels.row('Title', y=N, collapsed=true)`. Note: panels inside collapsed rows in the original JSON should follow the row in the panel array.

**Custom/plugin panels** — For non-standard panel types (e.g., `contextcore-workflow-panel`), use a raw object literal:
```jsonnet
{
  title: 'Custom Panel',
  type: 'custom-plugin-type',
  gridPos: { h: 10, w: 12, x: 0, y: 50 },
  options: { ... },
},
```

### Step 7: Create alert rules

Create `alerts/<project>.libsonnet`:

```jsonnet
local alerts = import '../lib/alerts.libsonnet';
local config = (import '../config.libsonnet')._config;

{
  groups: [
    {
      name: '<project>.alerts',
      rules: [
        alerts.mimirAlert(
          'AlertName',
          '<promql-expression>',
          '<for-duration>',    // e.g., '5m'
          '<severity>',       // 'warning' or 'critical'
          'Human-readable summary',
          description='Template description with {{ $value }}',
        ),
      ],
    },
  ],
}
```

Source alert definitions from:
- Observability manifests (alert templates section)
- Existing Prometheus alert rules
- SLO definitions

**Reference**: `/Users/neilyashinsky/Documents/dev/wayfinder/wayfinder-mixin/alerts/contextcore.libsonnet`
**Created**: `/Users/neilyashinsky/Documents/dev/startd8-sdk/startd8-mixin/alerts/startd8.libsonnet`

### Step 8: Create `mixin.libsonnet` entry point

This file aggregates everything:

```jsonnet
(import 'config.libsonnet') +
{
  grafanaDashboards+:: {
    'dashboard-one.json': (import 'dashboards/dashboard_one.libsonnet'),
    'dashboard-two.json': (import 'dashboards/dashboard_two.libsonnet'),
  },

  prometheusAlerts+:: {
    groups+: (import 'alerts/<project>.libsonnet').groups,
  },

  // Include if you have recording rules:
  // lokiRules+:: { groups+: (import 'rules/loki.libsonnet').groups },
  // mimirRules+:: { groups+: (import 'rules/mimir.libsonnet').groups },
}
```

The keys in `grafanaDashboards` become the output filenames.

**Reference**: `/Users/neilyashinsky/Documents/dev/wayfinder/wayfinder-mixin/mixin.libsonnet`
**Created**: `/Users/neilyashinsky/Documents/dev/startd8-sdk/startd8-mixin/mixin.libsonnet`

### Step 9: Create smoke test

```jsonnet
local mixin = import '../mixin.libsonnet';

{
  dashboards: std.length(std.objectFields(mixin.grafanaDashboards)),
  dashboardCountCorrect: self.dashboards == <expected-count>,
  alertGroups: std.length(mixin.prometheusAlerts.groups),

  // Verify each dashboard has correct UID
  dash1HasUid: mixin.grafanaDashboards['dashboard-one.json'].uid == '<expected-uid>',

  summary: 'Compiled %d dashboards, %d alert groups' % [self.dashboards, self.alertGroups],
}
```

**Reference**: `/Users/neilyashinsky/Documents/dev/wayfinder/wayfinder-mixin/tests/smoke_test.jsonnet`
**Created**: `/Users/neilyashinsky/Documents/dev/startd8-sdk/startd8-mixin/tests/smoke_test.jsonnet`

### Step 10: Create root Makefile

Add targets that delegate to the mixin's Makefile and copy generated dashboards to the project's dashboard directory:

```makefile
jsonnet-generate:
	$(MAKE) -C <name>-mixin generate
	@cp <name>-mixin/generated/dashboards/*.json dashboards/

jsonnet-test:
	$(MAKE) -C <name>-mixin test

jsonnet-lint:
	$(MAKE) -C <name>-mixin lint
```

**Created**: `/Users/neilyashinsky/Documents/dev/startd8-sdk/Makefile`

### Step 11: Update `.gitignore`

Add three entries to prevent vendor, generated output, and lock files from being committed:

```gitignore
<name>-mixin/vendor/
<name>-mixin/generated/
<name>-mixin/jsonnetfile.lock.json
```

**Modified**: `/Users/neilyashinsky/Documents/dev/startd8-sdk/.gitignore`

### Step 12: Install, generate, and verify

```bash
cd <name>-mixin

# Install grafonnet vendor library
make install

# Generate all dashboards + alerts
make generate

# Run smoke test
make test

# Check formatting
make lint
```

Expected output:
```
OK: All outputs compile
OK: All files formatted
```

Verify generated dashboards:
```bash
python3 -c "
import json, os
for f in sorted(os.listdir('generated/dashboards')):
    d = json.load(open(f'generated/dashboards/{f}'))
    print(f'{f}: uid={d[\"uid\"]}, panels={len(d[\"panels\"])}')
"
```

## Gotchas and Lessons Learned

### 1. `-S` flag for YAML output

Without `-S`, `jsonnet -e 'std.manifestYamlDoc(...)'` wraps the YAML in JSON string quotes with escaped newlines. Always use:
```bash
jsonnet -S -J vendor -e 'std.manifestYamlDoc(...)'
```

### 2. Float precision in alert thresholds

Jsonnet represents `0.05` as `0.050000000000000003` in output. This is functionally correct for Prometheus but looks odd. If it bothers you, use string thresholds in the alert expression directly rather than config references.

### 3. Panel ID assignment

`withPanels()` auto-assigns sequential IDs starting from 1. This means generated panel IDs won't match original JSON panel IDs. This is fine — Grafana doesn't use panel IDs for persistence (it uses UIDs for links/bookmarks).

### 4. gridPos must be explicit for faithful layout

The auto-layout in `withPanels()` (alternating 12-wide columns) only applies to panels without a `gridPos`. For faithful reproduction of the original layout, always set `gridPos` explicitly on each panel:
```jsonnet
panels.stat(...) { gridPos: { h: 4, w: 6, x: 0, y: 1 } },
```

### 5. Datasource references use template variables

Panels should reference datasources via template variable UIDs (`${datasource}`, `${tempo}`, `${loki}`), not hardcoded UIDs. This matches the original dashboard pattern and allows users to select different datasource instances.

### 6. Panel counts will differ from originals

The generated JSON includes row panels in the panel count, while the original JSON may have had them as separate objects. A generated dashboard with "35 panels" may correspond to an original with "29 panels" — the difference is row headers. Verify by spot-checking individual panel titles and queries rather than counting.

### 7. Source of truth transition

After migration, the jsonnet files are the source of truth. The `dashboards/*.json` files become generated output (overwritten by `make jsonnet-generate`). Any future dashboard changes should be made in the `.libsonnet` files, not the JSON.

## File Inventory

### startd8-mixin files created

| File | Purpose | Lines |
|------|---------|-------|
| `startd8-mixin/jsonnetfile.json` | Grafonnet dependency | 14 |
| `startd8-mixin/Makefile` | Build system | 52 |
| `startd8-mixin/config.libsonnet` | Centralized config (12 metrics, 5 spans, 3 thresholds) | 80 |
| `startd8-mixin/mixin.libsonnet` | Entry point | 14 |
| `startd8-mixin/lib/dashboards.libsonnet` | Dashboard wrapper + auto-layout | 47 |
| `startd8-mixin/lib/panels.libsonnet` | 17 panel constructors | 340 |
| `startd8-mixin/lib/variables.libsonnet` | 8 template variable builders | 95 |
| `startd8-mixin/lib/alerts.libsonnet` | Alert rule helpers | 28 |
| `startd8-mixin/lib/rules.libsonnet` | Recording rule helpers | 15 |
| `startd8-mixin/dashboards/overview.libsonnet` | SDK Overview (12 panels) | 145 |
| `startd8-mixin/dashboards/cost_tracking.libsonnet` | Cost Tracking (10 panels) | 135 |
| `startd8-mixin/dashboards/metrics.libsonnet` | SDK Metrics (35 panels) | 285 |
| `startd8-mixin/dashboards/lead_contractor.libsonnet` | Lead Contractor (20 panels) | 195 |
| `startd8-mixin/dashboards/artisan_contractor.libsonnet` | Artisan Contractor (33 panels) | 265 |
| `startd8-mixin/alerts/startd8.libsonnet` | 3 alert rules | 35 |
| `startd8-mixin/tests/smoke_test.jsonnet` | Compilation + UID verification | 25 |

### Other files modified

| File | Change |
|------|--------|
| `/Users/neilyashinsky/Documents/dev/startd8-sdk/.gitignore` | Added `startd8-mixin/vendor/`, `generated/`, `jsonnetfile.lock.json` |
| `/Users/neilyashinsky/Documents/dev/startd8-sdk/Makefile` | Created — `jsonnet-generate`, `jsonnet-test`, `jsonnet-lint` targets |

### Reference files consulted

| File | Used For |
|------|----------|
| `/Users/neilyashinsky/Documents/dev/wayfinder/wayfinder-mixin/config.libsonnet` | Config structure pattern |
| `/Users/neilyashinsky/Documents/dev/wayfinder/wayfinder-mixin/mixin.libsonnet` | Entry point pattern |
| `/Users/neilyashinsky/Documents/dev/wayfinder/wayfinder-mixin/Makefile` | Build system pattern |
| `/Users/neilyashinsky/Documents/dev/wayfinder/wayfinder-mixin/jsonnetfile.json` | Dependency declaration |
| `/Users/neilyashinsky/Documents/dev/wayfinder/wayfinder-mixin/lib/dashboards.libsonnet` | Dashboard helper pattern |
| `/Users/neilyashinsky/Documents/dev/wayfinder/wayfinder-mixin/lib/panels.libsonnet` | Panel constructor patterns (12 types) |
| `/Users/neilyashinsky/Documents/dev/wayfinder/wayfinder-mixin/lib/variables.libsonnet` | Variable builder patterns |
| `/Users/neilyashinsky/Documents/dev/wayfinder/wayfinder-mixin/lib/alerts.libsonnet` | Alert helper pattern |
| `/Users/neilyashinsky/Documents/dev/wayfinder/wayfinder-mixin/lib/rules.libsonnet` | Rule helper pattern |
| `/Users/neilyashinsky/Documents/dev/wayfinder/wayfinder-mixin/tests/smoke_test.jsonnet` | Test pattern |
| `/Users/neilyashinsky/Documents/dev/startd8-sdk/dashboards/startd8-sdk-overview.json` | Source dashboard |
| `/Users/neilyashinsky/Documents/dev/startd8-sdk/dashboards/startd8-cost-tracking.json` | Source dashboard |
| `/Users/neilyashinsky/Documents/dev/startd8-sdk/dashboards/startd8-sdk-metrics.json` | Source dashboard |
| `/Users/neilyashinsky/Documents/dev/startd8-sdk/dashboards/lead-contractor-progress.json` | Source dashboard |
| `/Users/neilyashinsky/Documents/dev/startd8-sdk/out/grafana_dashboard_artisan_contractor.json` | Source dashboard |
| `/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/capability-index/startd8.observability.manifest.yaml` | Metric names, span patterns, alert templates |
