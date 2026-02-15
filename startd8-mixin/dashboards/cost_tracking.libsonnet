// StartD8 Cost Tracking dashboard.
// Migrated from dashboards/startd8-cost-tracking.json
local config = (import '../config.libsonnet')._config;
local dashboards = import '../lib/dashboards.libsonnet';
local panels = import '../lib/panels.libsonnet';
local variables = import '../lib/variables.libsonnet';

local m = config.metrics;
local sel = config.selectors;

local mimirDatasource = { type: 'prometheus', uid: '${datasource}' };
local lokiDatasource = { type: 'loki', uid: '${loki}' };

local baseDashboard = dashboards.dashboard(
  'StartD8 Cost Tracking',
  'startd8-cost-tracking',
  description='Cost tracking dashboard for StartD8 SDK — spend by model, budget alerts, token efficiency, and cost-per-request analysis',
  tags=['cost-tracking', 'llm', 'budget'],
) {
  time: { from: 'now-24h', to: 'now' },
  templating: {
    list: [
      variables.prometheusDatasource(),
      variables.lokiDatasource(),
      variables.serviceNameVariable(),
      variables.modelVariable(m.costTotal),
      variables.projectVariable(m.costTotal),
    ],
  },
};

dashboards.withPanels(baseDashboard, [
  // Top stats row
  panels.stat(
    'Total Spend',
    'sum(%s{%s, %s, %s})' % [m.costTotal, sel.serviceName, sel.model, sel.projectId],
    datasource=mimirDatasource,
    unit='currencyUSD',
    decimals=2,
    instant=true,
    thresholds=[
      { color: 'green', value: null },
      { color: 'yellow', value: 10 },
      { color: 'orange', value: 50 },
      { color: 'red', value: 100 },
    ],
  ) {
    gridPos: { h: 6, w: 6, x: 0, y: 0 },
  },

  panels.piechart(
    'Spend by Model',
    [{ expr: 'sum by (model)(%s{%s, %s, %s})' % [m.costTotal, sel.serviceName, sel.model, sel.projectId], refId: 'A', legendFormat: '{{model}}' }],
    datasource=mimirDatasource,
    unit='currencyUSD',
    legendMode='table',
  ) {
    gridPos: { h: 10, w: 10, x: 6, y: 0 },
    options+: { displayLabels: ['name', 'percent'] },
  },

  panels.stat(
    'Budget Utilization',
    'sum(%s{%s, %s}) / sum(%s{%s, %s})' % [m.costTotal, sel.serviceName, sel.projectId, m.budgetLimit, sel.serviceName, sel.projectId],
    datasource=mimirDatasource,
    unit='percentunit',
    decimals=1,
    thresholds=[
      { color: 'green', value: null },
      { color: 'yellow', value: 0.7 },
      { color: 'orange', value: 0.85 },
      { color: 'red', value: 0.95 },
    ],
  ) {
    gridPos: { h: 4, w: 4, x: 0, y: 6 },
  },

  panels.stat(
    'Avg Cost Per Request',
    'sum(%s_bucket{%s, %s, %s}) / count(%s_bucket{%s, %s, %s})' % [m.costPerRequest, sel.serviceName, sel.model, sel.projectId, m.costPerRequest, sel.serviceName, sel.model, sel.projectId],
    datasource=mimirDatasource,
    unit='currencyUSD',
    decimals=4,
    thresholds=[
      { color: 'green', value: null },
      { color: 'yellow', value: 0.05 },
      { color: 'red', value: 0.25 },
    ],
  ) {
    gridPos: { h: 4, w: 4, x: 16, y: 0 },
  },

  // Spend over time
  panels.timeseries(
    'Spend Over Time',
    [{ expr: 'sum by (model)(rate(%s{%s, %s, %s}[5m]))' % [m.costTotal, sel.serviceName, sel.model, sel.projectId], refId: 'A', legendFormat: '{{model}}' }],
    datasource=mimirDatasource,
    unit='currencyUSD',
    fillOpacity=15,
    lineInterpolation='smooth',
    legendMode='table',
    legendCalcs=['sum', 'mean', 'max'],
  ) {
    gridPos: { h: 10, w: 16, x: 0, y: 10 },
    fieldConfig+: { defaults+: { decimals: 4 } },
  },

  panels.timeseries(
    'Spend Over Time (Cumulative)',
    [{ expr: 'sum by (model)(%s{%s, %s, %s})' % [m.costTotal, sel.serviceName, sel.model, sel.projectId], refId: 'A', legendFormat: '{{model}}' }],
    datasource=mimirDatasource,
    unit='currencyUSD',
    stacking='normal',
    fillOpacity=30,
  ) {
    gridPos: { h: 10, w: 8, x: 16, y: 10 },
    fieldConfig+: { defaults+: { decimals: 2 } },
  },

  // Cost distribution
  panels.histogram(
    'Cost Per Request',
    [{ expr: '%s_bucket{%s, %s, %s}' % [m.costPerRequest, sel.serviceName, sel.model, sel.projectId], refId: 'A', legendFormat: '{{le}}', format: 'heatmap' }],
    datasource=mimirDatasource,
    unit='currencyUSD',
  ) {
    gridPos: { h: 10, w: 12, x: 0, y: 20 },
  },

  panels.timeseries(
    'Token Efficiency',
    [
      { expr: 'rate(%s{%s, %s, %s}[5m])' % [m.costInputTokens, sel.serviceName, sel.model, sel.projectId], refId: 'A', legendFormat: 'Input Tokens' },
      { expr: 'rate(%s{%s, %s, %s}[5m])' % [m.costOutputTokens, sel.serviceName, sel.model, sel.projectId], refId: 'B', legendFormat: 'Output Tokens' },
    ],
    datasource=mimirDatasource,
    unit='short',
    overrides=[
      { matcher: { id: 'byName', options: 'Input Tokens' }, properties: [{ id: 'color', value: { fixedColor: '#73BF69', mode: 'fixed' } }] },
      { matcher: { id: 'byName', options: 'Output Tokens' }, properties: [{ id: 'color', value: { fixedColor: '#F2495C', mode: 'fixed' } }] },
    ],
  ) {
    gridPos: { h: 10, w: 12, x: 12, y: 20 },
    fieldConfig+: { defaults+: { decimals: 0 } },
  },

  // Ratio and logs
  panels.timeseries(
    'Input/Output Token Ratio',
    [{ expr: 'rate(%s{%s, %s, %s}[5m]) / rate(%s{%s, %s, %s}[5m])' % [m.costInputTokens, sel.serviceName, sel.model, sel.projectId, m.costOutputTokens, sel.serviceName, sel.model, sel.projectId], refId: 'A', legendFormat: '{{model}}' }],
    datasource=mimirDatasource,
    unit='short',
  ) {
    gridPos: { h: 8, w: 12, x: 0, y: 30 },
    fieldConfig+: { defaults+: { decimals: 2 } },
  },

  panels.logs(
    'Budget Alerts',
    '{service_name="$service_name"} |= "budget"',
    datasource=lokiDatasource,
  ) {
    gridPos: { h: 10, w: 12, x: 12, y: 30 },
  },
])
