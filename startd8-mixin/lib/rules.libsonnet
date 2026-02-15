// Recording rule helper functions.
{
  // Loki recording rule
  lokiRule(record, expr, source='loki'):: {
    record: record,
    expr: expr,
    labels: { source: source },
  },

  // Mimir/Prometheus recording rule
  mimirRule(record, expr):: {
    record: record,
    expr: expr,
  },
}
