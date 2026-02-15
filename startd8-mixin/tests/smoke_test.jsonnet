// Smoke test: verify all mixin outputs compile without error.
local mixin = import '../mixin.libsonnet';

{
  // Verify dashboards compile
  dashboards: std.length(std.objectFields(mixin.grafanaDashboards)),
  dashboardCount5: self.dashboards == 5,

  // Verify alerts compile
  alertGroups: std.length(mixin.prometheusAlerts.groups),

  // Verify specific dashboards have expected fields
  overviewHasUid: std.objectHas(mixin.grafanaDashboards['overview.json'], 'uid'),
  overviewHasPanels: std.length(mixin.grafanaDashboards['overview.json'].panels) > 0,
  costTrackingHasUid: mixin.grafanaDashboards['cost-tracking.json'].uid == 'startd8-cost-tracking',
  metricsHasUid: mixin.grafanaDashboards['metrics.json'].uid == 'startd8-sdk-metrics',
  leadContractorHasUid: mixin.grafanaDashboards['lead-contractor.json'].uid == 'contextcore-beaver-lead-contractor-progress',
  artisanContractorHasUid: mixin.grafanaDashboards['artisan-contractor.json'].uid == 'artisan-contractor-progress',

  // Summary
  summary: 'Compiled %d dashboards, %d alert groups' % [
    self.dashboards,
    self.alertGroups,
  ],
}
