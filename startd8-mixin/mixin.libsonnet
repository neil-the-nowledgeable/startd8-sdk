(import 'config.libsonnet') +
{
  grafanaDashboards+:: {
    'overview.json': (import 'dashboards/overview.libsonnet'),
    'cost-tracking.json': (import 'dashboards/cost_tracking.libsonnet'),
    'metrics.json': (import 'dashboards/metrics.libsonnet'),
    'primary-contractor.json': (import 'dashboards/primary_contractor.libsonnet'),
    'artisan-contractor.json': (import 'dashboards/artisan_contractor.libsonnet'),
  },

  prometheusAlerts+:: {
    groups+: (import 'alerts/startd8.libsonnet').groups,
  },
}
