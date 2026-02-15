// Alert helper functions.
{
  // Loki alert rule
  lokiAlert(name, expr, forDuration, severity, summary, runbookUrl='', description=''):: {
    alert: name,
    expr: expr,
    'for': forDuration,
    labels: { severity: severity },
    annotations: {
      summary: summary,
      [if runbookUrl != '' then 'runbook_url']: runbookUrl,
      [if description != '' then 'description']: description,
    },
  },

  // Mimir/Prometheus alert rule
  mimirAlert(name, expr, forDuration, severity, summary, runbookUrl='', description=''):: {
    alert: name,
    expr: expr,
    'for': forDuration,
    labels: { severity: severity },
    annotations: {
      summary: summary,
      [if runbookUrl != '' then 'runbook_url']: runbookUrl,
      [if description != '' then 'description']: description,
    },
  },
}
