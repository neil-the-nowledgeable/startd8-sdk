// Lead Contractor Progress dashboard.
// Migrated from dashboards/lead-contractor-progress.json
local config = (import '../config.libsonnet')._config;
local dashboards = import '../lib/dashboards.libsonnet';
local panels = import '../lib/panels.libsonnet';
local variables = import '../lib/variables.libsonnet';

local m = config.metrics;

local tempoDatasource = { type: 'tempo', uid: '${tempo}' };
local mimirDatasource = { type: 'prometheus', uid: '${datasource}' };
local lokiDatasource = { type: 'loki', uid: '${loki}' };

local baseDashboard = dashboards.dashboard(
  '[BEAVER] Lead Contractor Progress',
  'contextcore-beaver-lead-contractor-progress',
  description='Track project progress with StartD8 SDK Lead Contractor integration - task status and execution traces from Tempo',
  tags=['contextcore', 'beaver', 'project-tracking'],
) {
  time: { from: 'now-7d', to: 'now' },
  templating: {
    list: [
      variables.tempoDatasource(),
      variables.prometheusDatasource(),
      variables.lokiDatasource(),
      {
        name: 'project',
        label: 'Project',
        type: 'custom',
        query: 'beaver-lead-contractor,ajidamoo-squirrel,contextcore,contextcore-tui-fixes,asabikeshiinh-localization,startd8-sdk',
        current: { text: 'beaver-lead-contractor', value: 'beaver-lead-contractor' },
      },
    ],
  },
};

dashboards.withPanels(baseDashboard, [
  // Row 1: Task Status Overview
  panels.row('Task Status Overview', y=0),

  panels.traceqlStat(
    'Completed Tasks',
    '{resource.project.id = "$project" && span.task.status = "done"}',
    datasource=tempoDatasource,
    thresholds=[{ color: 'green', value: null }],
  ) { gridPos: { h: 4, w: 6, x: 0, y: 1 } },

  panels.traceqlStat(
    'In Progress Tasks',
    '{resource.project.id = "$project" && span.task.status = "in_progress"}',
    datasource=tempoDatasource,
    thresholds=[{ color: 'blue', value: null }],
  ) { gridPos: { h: 4, w: 6, x: 6, y: 1 } },

  panels.traceqlStat(
    'Avg Task Duration',
    '{resource.project.id = "$project"} | select(duration)',
    datasource=tempoDatasource,
    limit=100,
    calcs=['mean'],
    unit='ms',
    thresholds=[
      { color: 'green', value: null },
      { color: 'yellow', value: 60000 },
      { color: 'red', value: 300000 },
    ],
  ) { gridPos: { h: 4, w: 6, x: 12, y: 1 } },

  panels.traceqlStat(
    'Total Task Spans',
    '{resource.project.id = "$project"}',
    datasource=tempoDatasource,
    thresholds=[{ color: 'purple', value: null }],
  ) { gridPos: { h: 4, w: 6, x: 18, y: 1 } },

  // Row 2: Task Execution History
  panels.row('Task Execution History', y=5),

  panels.traceqlTable(
    'Task Execution History',
    '{resource.project.id = "$project"} | select(span.task.id, span.task.title, span.task.status, span.task.percent_complete, duration)',
    datasource=tempoDatasource,
    limit=50,
    overrides=[
      {
        matcher: { id: 'byName', options: 'task.status' },
        properties: [
          { id: 'custom.cellOptions', value: { type: 'color-background' } },
          {
            id: 'mappings',
            value: [
              { type: 'value', options: { pending: { color: 'yellow', text: 'PENDING' }, in_progress: { color: 'blue', text: 'IN PROGRESS' }, done: { color: 'green', text: 'DONE' }, blocked: { color: 'red', text: 'BLOCKED' } } },
            ],
          },
        ],
      },
      { matcher: { id: 'byName', options: 'Duration' }, properties: [{ id: 'unit', value: 'ms' }] },
      {
        matcher: { id: 'byName', options: 'task.percent_complete' },
        properties: [
          { id: 'unit', value: 'percent' },
          { id: 'custom.cellOptions', value: { type: 'gauge' } },
        ],
      },
    ],
  ) { gridPos: { h: 12, w: 24, x: 0, y: 6 } },

  // Row 3: Task Duration Analysis
  panels.row('Task Duration Analysis', y=18),

  panels.histogram(
    'Task Lead Time Distribution',
    [{
      datasource: tempoDatasource,
      query: '{resource.project.id = "$project" && span.task.status = "done"} | select(duration)',
      queryType: 'traceql',
      refId: 'A',
      limit: 1000,
    }],
    datasource=tempoDatasource,
    unit='ms',
  ) { gridPos: { h: 8, w: 12, x: 0, y: 19 } },

  panels.piechart(
    'Tasks by Status',
    [{
      datasource: tempoDatasource,
      query: '{resource.project.id = "$project"} | select(span.task.status)',
      queryType: 'traceql',
      refId: 'A',
      limit: 1000,
    }],
    datasource=tempoDatasource,
    pieType='donut',
    legendMode='table',
  ) { gridPos: { h: 8, w: 12, x: 12, y: 19 } },

  // Row 4: Workflow Runs
  panels.row('Workflow Runs (from Tempo)', y=27),

  panels.traceqlTable(
    'Workflow Executions',
    '{resource.project.id = "$project" && name =~ "workflow.*"} | select(span.workflow.id, span.workflow.status, span.workflow.type, duration)',
    datasource=tempoDatasource,
    limit=50,
    overrides=[
      {
        matcher: { id: 'byName', options: 'workflow.status' },
        properties: [
          { id: 'custom.cellOptions', value: { type: 'color-background' } },
          {
            id: 'mappings',
            value: [
              { type: 'value', options: { running: { color: 'blue', text: 'RUNNING' }, completed: { color: 'green', text: 'COMPLETED' }, failed: { color: 'red', text: 'FAILED' } } },
            ],
          },
        ],
      },
      { matcher: { id: 'byName', options: 'Duration' }, properties: [{ id: 'unit', value: 'ms' }] },
    ],
  ) { gridPos: { h: 8, w: 24, x: 0, y: 28 } },

  // Row 5: StartD8 Agent Metrics (collapsed)
  panels.row('StartD8 Agent Metrics', y=36, collapsed=true),

  panels.stat(
    'Total Cost (USD)',
    'sum(%s{project="$project"})' % m.costTotal,
    datasource=mimirDatasource,
    unit='currencyUSD',
    decimals=4,
    thresholds=[
      { color: 'green', value: null },
      { color: 'yellow', value: 1 },
      { color: 'red', value: 5 },
    ],
  ) { gridPos: { h: 4, w: 6, x: 0, y: 37 } },

  panels.stat(
    'Total Tokens',
    'sum(%s{project="$project"})' % m.tokensTotal,
    datasource=mimirDatasource,
    unit='short',
  ) { gridPos: { h: 4, w: 6, x: 6, y: 37 } },

  panels.timeseries(
    'Cost by Agent/Model',
    [{ expr: 'sum by (agent, model) (rate(%s{project="$project"}[5m]))' % m.costTotal, refId: 'A', legendFormat: '{{agent}} / {{model}}' }],
    datasource=mimirDatasource,
    unit='currencyUSD',
  ) { gridPos: { h: 8, w: 12, x: 0, y: 41 } },

  panels.timeseries(
    'Token Usage',
    [{ expr: 'sum by (type) (rate(%s{project="$project"}[5m]))' % m.tokensTotal, refId: 'A', legendFormat: '{{type}}' }],
    datasource=mimirDatasource,
    unit='short',
    stacking='normal',
  ) { gridPos: { h: 8, w: 12, x: 12, y: 41 } },

  // Row 6: Workflow Trigger
  panels.row('Workflow Trigger', y=49),

  // Custom workflow panel (contextcore-workflow-panel plugin)
  {
    title: 'Trigger Lead Contractor Workflow',
    type: 'contextcore-workflow-panel',
    gridPos: { h: 10, w: 12, x: 0, y: 50 },
    options: {
      apiUrl: 'http://localhost:8082',
      projectId: '$project',
      showDryRun: true,
      showExecute: true,
      confirmExecution: true,
      refreshInterval: 10,
    },
  },

  panels.text(
    'Workflow API Info',
    |||
      ## Lead Contractor Workflow

      ### REST API Endpoints
      - `POST /workflows/lead-contractor/run` — Run with default config
      - `POST /workflows/lead-contractor/run` with JSON body — Run with custom config

      ### CLI Alternative
      ```bash
      startd8 run-workflow lead-contractor --project $project
      ```
    |||,
  ) { gridPos: { h: 10, w: 12, x: 12, y: 50 } },
])
