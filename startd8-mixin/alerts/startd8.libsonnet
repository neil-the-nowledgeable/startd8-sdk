// StartD8 alert rules.
// Derived from observability manifest alert templates.
local alerts = import '../lib/alerts.libsonnet';
local config = (import '../config.libsonnet')._config;

local m = config.metrics;
local t = config.alertThresholds;

{
  groups: [
    {
      name: 'startd8.alerts',
      rules: [
        alerts.mimirAlert(
          'StartD8HighTruncationRate',
          'rate(%s[5m]) / rate(%s[5m]) > %s' % [m.truncationsTotal, m.requestsTotal, t.truncationRate],
          '5m',
          'warning',
          'StartD8 truncation rate exceeds %s%% of requests' % [t.truncationRate * 100],
          description='Truncation rate {{ $value | humanizePercentage }} exceeds threshold. Check context window sizing and prompt lengths.',
        ),
        alerts.mimirAlert(
          'StartD8ContextNearCapacity',
          '%s > %s' % [m.contextUsageRatio, t.contextCapacity],
          '2m',
          'warning',
          'StartD8 session context usage exceeds %s%%' % [t.contextCapacity * 100],
          description='Context usage ratio {{ $value | humanizePercentage }} is near capacity. Sessions may experience truncation.',
        ),
        alerts.mimirAlert(
          'StartD8BudgetExceeded',
          'sum(increase(%s[1d])) > %s' % [m.costTotal, t.budgetDailyUsd],
          '1m',
          'critical',
          'StartD8 daily cost exceeds $%s budget' % [t.budgetDailyUsd],
          description='Daily cost {{ $value | humanize }} USD exceeds budget limit. Review model selection and token usage.',
        ),
      ],
    },
  ],
}
