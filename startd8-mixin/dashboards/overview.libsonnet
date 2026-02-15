// StartD8 SDK Overview dashboard.
// Migrated from dashboards/startd8-sdk-overview.json
local config = (import '../config.libsonnet')._config;
local dashboards = import '../lib/dashboards.libsonnet';
local panels = import '../lib/panels.libsonnet';
local variables = import '../lib/variables.libsonnet';

local m = config.metrics;
local ds = config.datasources;
local sel = config.selectors;

local tempoDatasource = { type: 'tempo', uid: '${tempo}' };
local mimirDatasource = { type: 'prometheus', uid: '${datasource}' };
local lokiDatasource = { type: 'loki', uid: '${loki}' };

local baseDashboard = dashboards.dashboard(
  'StartD8 SDK Overview',
  'startd8-sdk-overview',
  description='Unified overview of StartD8 SDK request rate, latency, token usage, cost, sessions, truncations, errors, and logs across Tempo, Mimir, and Loki datasources.',
  tags=['overview', 'tempo', 'mimir', 'loki'],
) {
  templating: {
    list: [
      variables.tempoDatasource(),
      variables.prometheusDatasource(),
      variables.lokiDatasource(),
      variables.serviceNameVariable(),
      variables.modelVariable(m.costTotal),
      variables.projectVariable(m.activeSessions),
    ],
  },
};

dashboards.withPanels(baseDashboard, [
  // Row 1: Traces & Performance
  panels.row('Traces & Performance', y=0),

  panels.traceqlTimeseries(
    'Request Rate',
    [{
      datasource: tempoDatasource,
      query: '{ name = "agent.generate" && resource.service.name = "$service_name" } | rate()',
      queryType: 'traceql',
      refId: 'A',
    }],
    datasource=tempoDatasource,
    unit='reqps',
  ) {
    gridPos: { h: 8, w: 12, x: 0, y: 1 },
    fieldConfig+: {
      defaults+: {
        custom+: { lineWidth: 2, fillOpacity: 20, gradientMode: 'scheme', showPoints: 'never' },
      },
    },
    options+: { legend+: { calcs: ['mean', 'max'] } },
  },

  panels.traceqlTimeseries(
    'Latency P50 / P95 / P99',
    [
      {
        datasource: tempoDatasource,
        query: '{ name = "agent.generate" && resource.service.name = "$service_name" } | quantile_over_time(span.agent.response_time_ms, 0.50) by (resource.service.name)',
        queryType: 'traceql',
        refId: 'A',
      },
      {
        datasource: tempoDatasource,
        query: '{ name = "agent.generate" && resource.service.name = "$service_name" } | quantile_over_time(span.agent.response_time_ms, 0.95) by (resource.service.name)',
        queryType: 'traceql',
        refId: 'B',
      },
      {
        datasource: tempoDatasource,
        query: '{ name = "agent.generate" && resource.service.name = "$service_name" } | quantile_over_time(span.agent.response_time_ms, 0.99) by (resource.service.name)',
        queryType: 'traceql',
        refId: 'C',
      },
    ],
    datasource=tempoDatasource,
    unit='ms',
    overrides=[
      { matcher: { id: 'byName', options: 'P50' }, properties: [{ id: 'color', value: { fixedColor: 'green', mode: 'fixed' } }] },
      { matcher: { id: 'byName', options: 'P95' }, properties: [{ id: 'color', value: { fixedColor: 'yellow', mode: 'fixed' } }] },
      { matcher: { id: 'byName', options: 'P99' }, properties: [{ id: 'color', value: { fixedColor: 'red', mode: 'fixed' } }] },
    ],
  ) {
    gridPos: { h: 8, w: 12, x: 12, y: 1 },
    options+: { legend+: { displayMode: 'table', calcs: ['mean', 'max'] } },
  },

  // Row 2: Tokens & Cost
  panels.row('Tokens & Cost', y=9),

  panels.barchart(
    'Token Usage by Model',
    [
      { expr: 'sum by (model) (increase(%s{%s, %s, %s}[$__range]))' % [m.costInputTokens, sel.serviceName, sel.model, sel.projectId], refId: 'A', legendFormat: '{{model}} input' },
      { expr: 'sum by (model) (increase(%s{%s, %s, %s}[$__range]))' % [m.costOutputTokens, sel.serviceName, sel.model, sel.projectId], refId: 'B', legendFormat: '{{model}} output' },
    ],
    datasource=mimirDatasource,
    unit='locale',
    orientation='horizontal',
    stacking='normal',
    decimals=0,
  ) {
    gridPos: { h: 8, w: 12, x: 0, y: 10 },
  },

  panels.timeseries(
    'Cost Accumulation',
    [{ expr: 'sum by (model) (increase(%s{%s, %s, %s}[1h]))' % [m.costTotal, sel.serviceName, sel.model, sel.projectId], refId: 'A', legendFormat: '{{model}}' }],
    datasource=mimirDatasource,
    unit='currencyUSD',
    stacking='normal',
    fillOpacity=25,
    lineWidth=2,
  ) {
    gridPos: { h: 8, w: 12, x: 12, y: 10 },
    fieldConfig+: { defaults+: { decimals: 4 } },
  },

  // Row 3: Health & Reliability
  panels.row('Health & Reliability', y=18),

  panels.gauge(
    'Active Sessions',
    'sum(%s{%s, %s, %s})' % [m.activeSessions, sel.serviceName, sel.model, sel.projectId],
    datasource=mimirDatasource,
    unit='short',
    min=0,
    max=30,
    thresholds=[
      { color: 'green', value: null },
      { color: 'yellow', value: 5 },
      { color: 'orange', value: 10 },
      { color: 'red', value: 20 },
    ],
  ) {
    gridPos: { h: 8, w: 12, x: 0, y: 19 },
  },

  panels.timeseries(
    'Truncation Rate',
    [{ expr: 'sum by (model) (rate(%s{%s, %s, %s}[5m]))' % [m.truncationsTotal, sel.serviceName, sel.model, sel.projectId], refId: 'A', legendFormat: '{{model}}' }],
    datasource=mimirDatasource,
    unit='ops',
    drawStyle='bars',
  ) {
    gridPos: { h: 8, w: 12, x: 12, y: 19 },
    fieldConfig+: { defaults+: { decimals: 4, color: { fixedColor: 'orange', mode: 'fixed' } } },
  },

  // Row 4: Errors & Logs
  panels.row('Errors & Logs', y=27),

  panels.traceqlTimeseries(
    'Error Rate',
    [{
      datasource: tempoDatasource,
      query: '{ resource.service.name = "$service_name" && status = error } | rate()',
      queryType: 'traceql',
      refId: 'A',
    }],
    datasource=tempoDatasource,
    unit='ops',
  ) {
    gridPos: { h: 8, w: 12, x: 0, y: 28 },
    fieldConfig+: {
      defaults+: {
        decimals: 4,
        color: { fixedColor: 'red', mode: 'fixed' },
        custom+: { drawStyle: 'bars' },
      },
    },
  },

  panels.logs(
    'Recent Logs',
    '{service_name="$service_name"}',
    datasource=lokiDatasource,
  ) {
    gridPos: { h: 8, w: 12, x: 12, y: 28 },
  },
])
