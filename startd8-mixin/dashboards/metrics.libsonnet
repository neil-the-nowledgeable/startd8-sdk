// StartD8 SDK Metrics dashboard.
// Migrated from dashboards/startd8-sdk-metrics.json
local config = (import '../config.libsonnet')._config;
local dashboards = import '../lib/dashboards.libsonnet';
local panels = import '../lib/panels.libsonnet';
local variables = import '../lib/variables.libsonnet';

local m = config.metrics;

local mimirDatasource = { type: 'prometheus', uid: '${datasource}' };

// Common label selector string
local ls = 'agent_name=~"$agent_name", model=~"$model", project_id=~"$project_id", task_id=~"$task_id", sprint_id=~"$sprint_id"';

local baseDashboard = dashboards.dashboard(
  'StartD8 SDK Metrics',
  'startd8-sdk-metrics',
  description='Technical and business metrics for StartD8 SDK sessions, tokens, costs, and performance with ContextCore project tracking',
  tags=['llm', 'agents', 'contextcore'],
) {
  templating: {
    list: [
      variables.prometheusDatasource(),
      variables.projectVariable(m.activeSessions),
      {
        name: 'task_id',
        label: 'Task',
        type: 'query',
        datasource: mimirDatasource,
        query: 'label_values(%s{project_id=~"$project_id"}, task_id)' % m.activeSessions,
        refresh: 1,
        includeAll: true,
        allValue: '.*',
        multi: true,
        current: { text: 'All', value: '$__all' },
      },
      {
        name: 'sprint_id',
        label: 'Sprint',
        type: 'query',
        datasource: mimirDatasource,
        query: 'label_values(%s{project_id=~"$project_id"}, sprint_id)' % m.activeSessions,
        refresh: 1,
        includeAll: true,
        allValue: '.*',
        multi: true,
        current: { text: 'All', value: '$__all' },
      },
      variables.agentVariable(m.activeSessions),
      {
        name: 'model',
        label: 'Model',
        type: 'query',
        datasource: mimirDatasource,
        query: 'label_values(%s{agent_name=~"$agent_name", project_id=~"$project_id"}, model)' % m.activeSessions,
        refresh: 1,
        includeAll: true,
        allValue: '.*',
        multi: true,
        current: { text: 'All', value: '$__all' },
      },
      variables.customVariable('status', 'Status', 'success,error', multi=true),
    ],
  },
  // Truncation annotation
  annotations+: {
    list+: [{
      datasource: mimirDatasource,
      enable: true,
      expr: 'increase(%s{agent_name=~"$agent_name", model=~"$model", project_id=~"$project_id"}[1m]) > 0' % m.truncationsTotal,
      name: 'Truncation Events',
      titleFormat: 'Truncation Detected',
      textFormat: '{{agent_name}} / {{model}} ({{project_id}})',
      iconColor: 'red',
    }],
  },
};

dashboards.withPanels(baseDashboard, [
  // Row 1: Overview KPIs
  panels.row('Overview KPIs', y=0),

  panels.stat(
    'Active Sessions',
    'sum(%s{%s})' % [m.activeSessions, ls],
    datasource=mimirDatasource,
    thresholds=[
      { color: 'green', value: null },
      { color: 'yellow', value: 5 },
      { color: 'red', value: 10 },
    ],
  ) { gridPos: { h: 4, w: 4, x: 0, y: 1 } },

  panels.stat(
    'Request Rate',
    'sum(rate(%s{%s}[5m])) * 60' % [m.requestsTotal, ls],
    datasource=mimirDatasource,
    unit='reqpm',
  ) { gridPos: { h: 4, w: 4, x: 4, y: 1 } },

  panels.stat(
    'Total Tokens (24h)',
    'sum(increase(%s{%s}[24h]))' % [m.tokensTotal, ls],
    datasource=mimirDatasource,
    unit='locale',
    decimals=0,
  ) { gridPos: { h: 4, w: 4, x: 8, y: 1 } },

  panels.stat(
    'Total Cost (24h)',
    'sum(increase(%s{%s}[24h]))' % [m.costTotal, ls],
    datasource=mimirDatasource,
    unit='currencyUSD',
    decimals=2,
  ) { gridPos: { h: 4, w: 4, x: 12, y: 1 } },

  panels.gauge(
    'Avg Context Usage',
    'avg(%s{%s})' % [m.contextUsageRatio, ls],
    datasource=mimirDatasource,
    unit='percentunit',
    min=0,
    max=1,
    thresholds=[
      { color: 'green', value: null },
      { color: 'yellow', value: 0.6 },
      { color: 'orange', value: 0.8 },
      { color: 'red', value: 0.95 },
    ],
  ) { gridPos: { h: 4, w: 4, x: 16, y: 1 } },

  panels.stat(
    'Truncations (24h)',
    'sum(increase(%s{%s}[24h]))' % [m.truncationsTotal, ls],
    datasource=mimirDatasource,
    thresholds=[
      { color: 'green', value: null },
      { color: 'yellow', value: 1 },
      { color: 'red', value: 10 },
    ],
  ) { gridPos: { h: 4, w: 4, x: 20, y: 1 } },

  // Row 2: Project Context (ContextCore)
  panels.row('Project Context (ContextCore)', y=5),

  panels.barchart(
    'Cost by Project',
    [{ expr: 'sum by (project_id) (increase(%s{project_id=~"$project_id", project_id!=""}[24h]))' % m.costTotal, refId: 'A', legendFormat: '{{project_id}}' }],
    datasource=mimirDatasource,
    unit='currencyUSD',
  ) { gridPos: { h: 8, w: 8, x: 0, y: 6 } },

  panels.barchart(
    'Tokens by Project',
    [{ expr: 'sum by (project_id) (increase(%s{project_id=~"$project_id", project_id!=""}[24h]))' % m.tokensTotal, refId: 'A', legendFormat: '{{project_id}}' }],
    datasource=mimirDatasource,
    unit='locale',
  ) { gridPos: { h: 8, w: 8, x: 8, y: 6 } },

  panels.barchart(
    'Requests by Sprint',
    [{ expr: 'sum by (sprint_id) (increase(%s{sprint_id=~"$sprint_id", sprint_id!=""}[24h]))' % m.requestsTotal, refId: 'A', legendFormat: '{{sprint_id}}' }],
    datasource=mimirDatasource,
  ) { gridPos: { h: 8, w: 8, x: 16, y: 6 } },

  panels.timeseries(
    'Cost Over Time by Project',
    [{ expr: 'sum by (project_id) (increase(%s{project_id=~"$project_id", project_id!=""}[1h]))' % m.costTotal, refId: 'A', legendFormat: '{{project_id}}' }],
    datasource=mimirDatasource,
    unit='currencyUSD',
  ) { gridPos: { h: 8, w: 12, x: 0, y: 14 } },

  panels.timeseries(
    'Requests Over Time by Task',
    [{ expr: 'sum by (task_id) (rate(%s{task_id=~"$task_id", task_id!=""}[5m])) * 60' % m.requestsTotal, refId: 'A', legendFormat: '{{task_id}}' }],
    datasource=mimirDatasource,
    unit='reqpm',
  ) { gridPos: { h: 8, w: 12, x: 12, y: 14 } },

  panels.table(
    'Project Summary',
    [
      { expr: 'sum by (project_id, project_name) (increase(%s{project_id!=""}[24h]))' % m.requestsTotal, refId: 'A', format: 'table', instant: true },
      { expr: 'sum by (project_id, project_name) (increase(%s{project_id!=""}[24h]))' % m.tokensTotal, refId: 'B', format: 'table', instant: true },
      { expr: 'sum by (project_id, project_name) (increase(%s{project_id!=""}[24h]))' % m.costTotal, refId: 'C', format: 'table', instant: true },
    ],
    datasource=mimirDatasource,
    transformations=[
      { id: 'merge', options: {} },
      {
        id: 'organize',
        options: {
          excludeByName: { Time: true, __name__: true, job: true, instance: true },
          renameByName: { 'Value #A': 'Requests (24h)', 'Value #B': 'Tokens (24h)', 'Value #C': 'Cost (24h)' },
        },
      },
    ],
  ) { gridPos: { h: 8, w: 24, x: 0, y: 22 } },

  // Row 3: Sessions & Requests
  panels.row('Sessions & Requests', y=30),

  panels.timeseries(
    'Active Sessions Over Time',
    [{ expr: 'sum by (agent_name, model) (%s{%s})' % [m.activeSessions, ls], refId: 'A', legendFormat: '{{agent_name}} / {{model}}' }],
    datasource=mimirDatasource,
  ) { gridPos: { h: 8, w: 12, x: 0, y: 31 } },

  panels.timeseries(
    'Request Rate by Status',
    [{ expr: 'sum by (status) (rate(%s{%s, status=~"$status"}[5m])) * 60' % [m.requestsTotal, ls], refId: 'A', legendFormat: '{{status}}' }],
    datasource=mimirDatasource,
    unit='reqpm',
    overrides=[
      { matcher: { id: 'byName', options: 'success' }, properties: [{ id: 'color', value: { fixedColor: 'green', mode: 'fixed' } }] },
      { matcher: { id: 'byName', options: 'error' }, properties: [{ id: 'color', value: { fixedColor: 'red', mode: 'fixed' } }] },
    ],
  ) { gridPos: { h: 8, w: 12, x: 12, y: 31 } },

  panels.barchart(
    'Requests by Agent',
    [{ expr: 'sum by (agent_name) (increase(%s{%s}[24h]))' % [m.requestsTotal, ls], refId: 'A', legendFormat: '{{agent_name}}' }],
    datasource=mimirDatasource,
  ) { gridPos: { h: 8, w: 8, x: 0, y: 39 } },

  panels.barchart(
    'Requests by Model',
    [{ expr: 'sum by (model) (increase(%s{%s}[24h]))' % [m.requestsTotal, ls], refId: 'A', legendFormat: '{{model}}' }],
    datasource=mimirDatasource,
  ) { gridPos: { h: 8, w: 8, x: 8, y: 39 } },

  panels.piechart(
    'Request Status Distribution',
    [{ expr: 'sum by (status) (increase(%s{%s}[24h]))' % [m.requestsTotal, ls], refId: 'A', legendFormat: '{{status}}' }],
    datasource=mimirDatasource,
    overrides=[
      { matcher: { id: 'byName', options: 'success' }, properties: [{ id: 'color', value: { fixedColor: 'green', mode: 'fixed' } }] },
      { matcher: { id: 'byName', options: 'error' }, properties: [{ id: 'color', value: { fixedColor: 'red', mode: 'fixed' } }] },
    ],
  ) { gridPos: { h: 8, w: 8, x: 16, y: 39 } },

  // Row 4: Token Consumption & Cost
  panels.row('Token Consumption & Cost', y=47),

  panels.timeseries(
    'Token Consumption Over Time',
    [{ expr: 'sum by (direction) (rate(%s{%s}[5m])) * 60' % [m.tokensTotal, ls], refId: 'A', legendFormat: '{{direction}}' }],
    datasource=mimirDatasource,
    overrides=[
      { matcher: { id: 'byName', options: 'input' }, properties: [{ id: 'color', value: { fixedColor: 'blue', mode: 'fixed' } }] },
      { matcher: { id: 'byName', options: 'output' }, properties: [{ id: 'color', value: { fixedColor: 'purple', mode: 'fixed' } }] },
    ],
  ) { gridPos: { h: 8, w: 12, x: 0, y: 48 } },

  panels.timeseries(
    'Cost Over Time',
    [{ expr: 'sum by (agent_name) (increase(%s{%s}[1h]))' % [m.costTotal, ls], refId: 'A', legendFormat: '{{agent_name}}' }],
    datasource=mimirDatasource,
    unit='currencyUSD',
  ) { gridPos: { h: 8, w: 12, x: 12, y: 48 } },

  panels.barchart(
    'Token Usage by Model',
    [{ expr: 'sum by (model) (increase(%s{%s}[24h]))' % [m.tokensTotal, ls], refId: 'A', legendFormat: '{{model}}' }],
    datasource=mimirDatasource,
    unit='locale',
  ) { gridPos: { h: 8, w: 12, x: 0, y: 56 } },

  panels.barchart(
    'Cost by Model',
    [{ expr: 'sum by (model) (increase(%s{%s}[24h]))' % [m.costTotal, ls], refId: 'A', legendFormat: '{{model}}' }],
    datasource=mimirDatasource,
    unit='currencyUSD',
  ) { gridPos: { h: 8, w: 12, x: 12, y: 56 } },

  // Row 5: Performance & Health
  panels.row('Performance & Health', y=64),

  panels.timeseries(
    'Response Time Distribution',
    [
      { expr: 'histogram_quantile(0.50, sum(rate(%s_bucket{%s}[5m])) by (le))' % [m.responseTimeMs, ls], refId: 'A', legendFormat: 'P50' },
      { expr: 'histogram_quantile(0.90, sum(rate(%s_bucket{%s}[5m])) by (le))' % [m.responseTimeMs, ls], refId: 'B', legendFormat: 'P90' },
      { expr: 'histogram_quantile(0.99, sum(rate(%s_bucket{%s}[5m])) by (le))' % [m.responseTimeMs, ls], refId: 'C', legendFormat: 'P99' },
    ],
    datasource=mimirDatasource,
    unit='ms',
    overrides=[
      { matcher: { id: 'byName', options: 'P50' }, properties: [{ id: 'color', value: { fixedColor: 'green', mode: 'fixed' } }] },
      { matcher: { id: 'byName', options: 'P90' }, properties: [{ id: 'color', value: { fixedColor: 'yellow', mode: 'fixed' } }] },
      { matcher: { id: 'byName', options: 'P99' }, properties: [{ id: 'color', value: { fixedColor: 'red', mode: 'fixed' } }] },
    ],
  ) { gridPos: { h: 8, w: 12, x: 0, y: 65 } },

  panels.timeseries(
    'Context Usage by Session',
    [{ expr: '%s{%s}' % [m.contextUsageRatio, ls], refId: 'A', legendFormat: '{{agent_name}} / {{model}}' }],
    datasource=mimirDatasource,
    unit='percentunit',
  ) {
    gridPos: { h: 8, w: 12, x: 12, y: 65 },
    fieldConfig+: { defaults+: { min: 0, max: 1 } },
  },

  panels.timeseries(
    'Truncation Events',
    [{ expr: 'sum by (agent_name, model) (rate(%s{%s}[5m])) * 60' % [m.truncationsTotal, ls], refId: 'A', legendFormat: '{{agent_name}} / {{model}}' }],
    datasource=mimirDatasource,
    drawStyle='bars',
  ) {
    gridPos: { h: 8, w: 12, x: 0, y: 73 },
    fieldConfig+: { defaults+: { color: { fixedColor: 'red', mode: 'fixed' } } },
  },

  panels.stat(
    'Success Rate',
    'sum(rate(%s{%s, status="success"}[24h])) / sum(rate(%s{%s}[24h]))' % [m.requestsTotal, ls, m.requestsTotal, ls],
    datasource=mimirDatasource,
    unit='percentunit',
    decimals=2,
    thresholds=[
      { color: 'red', value: null },
      { color: 'yellow', value: 0.9 },
      { color: 'green', value: 0.99 },
    ],
  ) { gridPos: { h: 4, w: 6, x: 12, y: 73 } },

  panels.stat(
    'Avg Response Time',
    'histogram_quantile(0.50, sum(rate(%s_bucket{%s}[5m])) by (le))' % [m.responseTimeMs, ls],
    datasource=mimirDatasource,
    unit='ms',
    thresholds=[
      { color: 'green', value: null },
      { color: 'yellow', value: 5000 },
      { color: 'red', value: 30000 },
    ],
  ) { gridPos: { h: 4, w: 6, x: 18, y: 73 } },

  panels.stat(
    'Sessions Near Capacity',
    'count(%s{%s} > 0.8)' % [m.contextUsageRatio, ls],
    datasource=mimirDatasource,
    thresholds=[
      { color: 'green', value: null },
      { color: 'yellow', value: 1 },
      { color: 'red', value: 3 },
    ],
  ) { gridPos: { h: 4, w: 6, x: 12, y: 77 } },

  panels.stat(
    'Truncation Rate',
    'sum(rate(%s{%s}[24h])) / sum(rate(%s{%s}[24h])) * 100' % [m.truncationsTotal, ls, m.requestsTotal, ls],
    datasource=mimirDatasource,
    unit='percent',
    decimals=2,
    thresholds=[
      { color: 'green', value: null },
      { color: 'yellow', value: 1 },
      { color: 'red', value: 5 },
    ],
  ) { gridPos: { h: 4, w: 6, x: 18, y: 77 } },

  // Row 6: Session Details (collapsed)
  panels.row('Detailed Metrics', y=81, collapsed=true),

  panels.table(
    'Session Details',
    [{ expr: '%s{%s}' % [m.contextUsageRatio, ls], refId: 'A', format: 'table', instant: true }],
    datasource=mimirDatasource,
    overrides=[{
      matcher: { id: 'byName', options: 'Value' },
      properties: [
        { id: 'unit', value: 'percentunit' },
        { id: 'displayName', value: 'Context Usage' },
        { id: 'custom.cellOptions', value: { type: 'gauge', mode: 'gradient' } },
        { id: 'thresholds', value: { mode: 'absolute', steps: [{ color: 'green', value: null }, { color: 'yellow', value: 0.6 }, { color: 'red', value: 0.8 }] } },
      ],
    }],
    transformations=[{
      id: 'organize',
      options: {
        excludeByName: { Time: true, __name__: true, job: true, instance: true },
      },
    }],
  ) { gridPos: { h: 10, w: 24, x: 0, y: 82 } },
])
