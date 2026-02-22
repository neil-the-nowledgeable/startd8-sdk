// Artisan Contractor Progress dashboard.
// Migrated from out/grafana_dashboard_artisan_contractor.json
local config = (import '../config.libsonnet')._config;
local dashboards = import '../lib/dashboards.libsonnet';
local panels = import '../lib/panels.libsonnet';
local variables = import '../lib/variables.libsonnet';

local am = config.artisanMetrics;
local m = config.metrics;

local mimirDatasource = { type: 'prometheus', uid: '${datasource}' };
local lokiDatasource = { type: 'loki', uid: '${loki}' };
local tempoDatasource = { type: 'tempo', uid: '${tempo}' };

local project = 'artisan_contractor';

local baseDashboard = dashboards.dashboard(
  'Artisan Contractor - Project Progress & ContextCore Insights',
  'artisan-contractor-progress',
  description='Artisan Contractor Workflow - Task Progress, Phase Tracking, and ContextCore Insights',
  tags=['project-tracking', 'artisan-contractor', 'contextcore', 'prime-contractor'],
) {
  time: { from: 'now-15m', to: 'now' },
  style: 'dark',
  templating: {
    list: [
      variables.prometheusDatasource(),
      variables.lokiDatasource(),
      variables.tempoDatasource(),
      variables.constantVariable('project', project),
    ],
  },
};

dashboards.withPanels(baseDashboard, [
  // Row 1: Overview
  panels.row('Overview', y=0),

  panels.gauge(
    'Overall Progress',
    '%s{project="%s"}' % [am.weightedProgress, project],
    datasource=mimirDatasource,
    unit='percentunit',
    min=0,
    max=1,
    instant=true,
    thresholds=[
      { color: 'red', value: null },
      { color: 'orange', value: 0.25 },
      { color: 'yellow', value: 0.5 },
      { color: 'green', value: 0.75 },
    ],
  ) { gridPos: { h: 5, w: 6, x: 0, y: 1 } },

  panels.stat(
    'Total Tasks',
    'sum(%s{project="%s"})' % [am.tasksTotal, project],
    datasource=mimirDatasource,
    unit='short',
    instant=true,
  ) { gridPos: { h: 5, w: 3, x: 6, y: 1 } },

  panels.stat(
    'Completed',
    '%s{project="%s",status="complete"}' % [am.tasksTotal, project],
    datasource=mimirDatasource,
    unit='short',
    instant=true,
    thresholds=[{ color: 'green', value: null }],
  ) { gridPos: { h: 5, w: 3, x: 9, y: 1 } },

  panels.stat(
    'In Progress',
    '%s{project="%s",status="in_progress"}' % [am.tasksTotal, project],
    datasource=mimirDatasource,
    unit='short',
    instant=true,
    thresholds=[{ color: 'blue', value: null }],
  ) { gridPos: { h: 5, w: 3, x: 12, y: 1 } },

  panels.stat(
    'Blocked',
    '%s{project="%s"}' % [am.blockersActive, project],
    datasource=mimirDatasource,
    unit='short',
    instant=true,
    thresholds=[{ color: 'red', value: null }],
  ) { gridPos: { h: 5, w: 3, x: 15, y: 1 } },

  panels.stat(
    'Story Points',
    'sum(%s{project="%s"})' % [am.storyPointsTotal, project],
    datasource=mimirDatasource,
    unit='short',
    instant=true,
    thresholds=[{ color: 'purple', value: null }],
  ) { gridPos: { h: 5, w: 3, x: 18, y: 1 } },

  panels.stat(
    'Est. LOC',
    'sum(%s{project="%s"})' % [am.estimatedLocTotal, project],
    datasource=mimirDatasource,
    unit='short',
    instant=true,
    thresholds=[{ color: 'orange', value: null }],
  ) { gridPos: { h: 5, w: 3, x: 21, y: 1 } },

  // Row 2: Phase Progress
  panels.row('Phase Progress', y=6),

  panels.barGauge(
    'Phase Completion',
    '%s{project="%s"}' % [am.phaseProgress, project],
    datasource=mimirDatasource,
    unit='percentunit',
    min=0,
    max=1,
    legendFormat='{{phase}}',
    instant=true,
  ) { gridPos: { h: 6, w: 12, x: 0, y: 7 } },

  panels.piechart(
    'Tasks by Status',
    [{ expr: '%s{project="%s"}' % [am.tasksTotal, project], refId: 'A', legendFormat: '{{status}}', instant: true }],
    datasource=mimirDatasource,
    pieType='donut',
  ) { gridPos: { h: 6, w: 12, x: 12, y: 7 } },

  // Row 3: Per-Task Detail
  panels.row('Per-Task Detail', y=13),

  panels.table(
    'All Tasks - Completion Status',
    [{ expr: '%s{project="%s"}' % [am.taskPercentComplete, project], refId: 'A', format: 'table', instant: true }],
    datasource=mimirDatasource,
    overrides=[
      {
        matcher: { id: 'byName', options: 'Value' },
        properties: [
          { id: 'custom.cellOptions', value: { type: 'gauge', mode: 'gradient' } },
          { id: 'min', value: 0 },
          { id: 'max', value: 100 },
          { id: 'thresholds', value: { mode: 'absolute', steps: [{ color: 'red', value: null }, { color: 'orange', value: 25 }, { color: 'yellow', value: 50 }, { color: 'green', value: 100 }] } },
        ],
      },
      { matcher: { id: 'byName', options: 'task' }, properties: [{ id: 'displayName', value: 'Task ID' }, { id: 'custom.width', value: 80 }] },
      { matcher: { id: 'byName', options: 'phase' }, properties: [{ id: 'displayName', value: 'Phase' }, { id: 'custom.width', value: 120 }] },
      { matcher: { id: 'byName', options: 'component' }, properties: [{ id: 'displayName', value: 'Component' }, { id: 'custom.width', value: 150 }] },
      { matcher: { id: 'byName', options: 'type' }, properties: [{ id: 'displayName', value: 'Type' }, { id: 'custom.width', value: 60 }] },
      { matcher: { id: 'byName', options: 'priority' }, properties: [{ id: 'displayName', value: 'Priority' }, { id: 'custom.width', value: 70 }] },
    ],
    transformations=[{
      id: 'organize',
      options: { excludeByName: { Time: true, __name__: true, instance: true, job: true, project: true } },
    }],
  ) { gridPos: { h: 12, w: 24, x: 0, y: 14 } },

  // Row 4: Burndown & Timeline
  panels.row('Burndown & Timeline', y=26),

  panels.timeseries(
    'Story Points Burndown',
    [
      { expr: '%s{project="%s",status="not_started"}' % [am.storyPointsTotal, project], refId: 'A', legendFormat: 'Not Started' },
      { expr: '%s{project="%s",status="in_progress"}' % [am.storyPointsTotal, project], refId: 'B', legendFormat: 'In Progress' },
      { expr: '%s{project="%s",status="complete"}' % [am.storyPointsTotal, project], refId: 'C', legendFormat: 'Complete' },
    ],
    datasource=mimirDatasource,
    unit='short',
  ) { gridPos: { h: 8, w: 12, x: 0, y: 27 } },

  panels.timeseries(
    'Completion Rate Over Time',
    [
      { expr: '%s{project="%s"}' % [am.completionRate, project], refId: 'A', legendFormat: 'Completion Rate' },
      { expr: '%s{project="%s"}' % [am.criticalPathProgress, project], refId: 'B', legendFormat: 'Critical Path' },
      { expr: '%s{project="%s"}' % [am.weightedProgress, project], refId: 'C', legendFormat: 'Weighted Progress' },
    ],
    datasource=mimirDatasource,
    unit='percentunit',
  ) {
    gridPos: { h: 8, w: 12, x: 12, y: 27 },
    fieldConfig+: { defaults+: { min: 0, max: 1 } },
  },

  // Row 5: Distribution Analysis
  panels.row('Distribution Analysis', y=35),

  panels.piechart(
    'Tasks by Type',
    [{ expr: '%s{project="%s"}' % [am.tasksByType, project], refId: 'A', legendFormat: '{{type}}', instant: true }],
    datasource=mimirDatasource,
  ) { gridPos: { h: 6, w: 8, x: 0, y: 36 } },

  panels.piechart(
    'Tasks by Priority',
    [{ expr: '%s{project="%s"}' % [am.tasksByPriority, project], refId: 'A', legendFormat: '{{priority}}', instant: true }],
    datasource=mimirDatasource,
  ) { gridPos: { h: 6, w: 8, x: 8, y: 36 } },

  panels.barGauge(
    'Effort by Status',
    '%s{project="%s"}' % [am.effortTotal, project],
    datasource=mimirDatasource,
    legendFormat='{{status}}',
    instant=true,
  ) { gridPos: { h: 6, w: 8, x: 16, y: 36 } },

  // Row 6: ContextCore Insights (Runtime Telemetry)
  panels.row('ContextCore Insights (Runtime Telemetry)', y=42),

  panels.logs(
    'Task Lifecycle Events (Loki Logs)',
    '{service_name="artisan-contractor-tracker"}',
    datasource=lokiDatasource,
  ) {
    gridPos: { h: 10, w: 24, x: 0, y: 43 },
    options+: { prettifyLogMessage: true },
  },

  panels.logs(
    'ContextCore: Feature Selection Insights',
    '{service_name="artisan-contractor-tracker"} |= "task.state_change"',
    datasource=lokiDatasource,
  ) { gridPos: { h: 8, w: 12, x: 0, y: 53 } },

  panels.logs(
    'ContextCore: Integration Results',
    '{service_name="artisan-contractor-tracker"} |~ "task.completed|task.blocked"',
    datasource=lokiDatasource,
  ) { gridPos: { h: 8, w: 12, x: 12, y: 53 } },

  // Row 7: Cost & Token Tracking
  panels.row('Cost & Token Tracking (ContextCore Runtime)', y=61),

  panels.timeseries(
    'Per-Feature Cost',
    [{ expr: '%s{project="%s"}' % [am.featureCostUsd, project], refId: 'A', legendFormat: '{{feature_name}}' }],
    datasource=mimirDatasource,
    unit='currencyUSD',
  ) { gridPos: { h: 8, w: 12, x: 0, y: 62 } },

  panels.timeseries(
    'Integration Success Rate',
    [{ expr: '%s{project="%s"}' % [am.integrationSuccess, project], refId: 'A', legendFormat: 'Successes' }],
    datasource=mimirDatasource,
    unit='short',
  ) { gridPos: { h: 8, w: 12, x: 12, y: 62 } },

  // Row 8: Dependency & Critical Path
  panels.row('Dependency & Critical Path', y=70),

  panels.gauge(
    'Critical Path Progress',
    '%s{project="%s"}' % [am.criticalPathProgress, project],
    datasource=mimirDatasource,
    unit='percentunit',
    min=0,
    max=1,
    instant=true,
    thresholds=[
      { color: 'red', value: null },
      { color: 'orange', value: 0.25 },
      { color: 'yellow', value: 0.5 },
      { color: 'green', value: 0.75 },
    ],
  ) { gridPos: { h: 5, w: 8, x: 0, y: 71 } },

  panels.stat(
    'Quality Score (Avg)',
    '%s{project="%s"}' % [am.qualityScoreAvg, project],
    datasource=mimirDatasource,
    unit='short',
    instant=true,
    thresholds=[{ color: 'semi-dark-blue', value: null }],
  ) { gridPos: { h: 5, w: 8, x: 8, y: 71 } },

  panels.text(
    'Dependency Map',
    |||
      ## Critical Path

      ```
      PLAN → SCAFFOLD → DESIGN → IMPLEMENT → INTEGRATE → TEST → REVIEW → FINALIZE
      ```

      ### Dependency Clusters
      - **Foundation**: PLAN, SCAFFOLD (must complete before DESIGN)
      - **Core**: DESIGN, IMPLEMENT, INTEGRATE (sequential, design-first)
      - **Validation**: TEST, REVIEW (can partial overlap)
      - **Delivery**: FINALIZE (requires all above)
    |||,
  ) { gridPos: { h: 5, w: 8, x: 16, y: 71 } },

  // Row 9: Trace Explorer
  panels.row('Trace Explorer (Tempo)', y=76),

  panels.traces(
    'Task Span Hierarchy (project -> phase -> task)',
    '{resource.service.name="artisan-contractor-tracker"}',
    datasource=tempoDatasource,
  ) { gridPos: { h: 8, w: 24, x: 0, y: 77 } },
])
