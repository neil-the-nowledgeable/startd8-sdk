// Template variable builders for StartD8 dashboards.
local config = (import '../config.libsonnet')._config;

{
  // Prometheus/Mimir datasource variable (GAP-VAR-02: optional regex filter)
  prometheusDatasource(name='datasource', label='Datasource', regex=''):: {
    name: name,
    label: label,
    type: 'datasource',
    query: 'prometheus',
    current: { text: 'Mimir', value: 'mimir' },
    refresh: 1,
    [if regex != '' then 'regex']: regex,
  },

  // Tempo datasource variable
  tempoDatasource(name='tempo', label='Tempo', regex=''):: {
    name: name,
    label: label,
    type: 'datasource',
    query: 'tempo',
    current: { text: 'Tempo', value: 'tempo' },
    refresh: 1,
    [if regex != '' then 'regex']: regex,
  },

  // Loki datasource variable
  lokiDatasource(name='loki', label='Loki', regex=''):: {
    name: name,
    label: label,
    type: 'datasource',
    query: 'loki',
    current: { text: 'Loki', value: 'loki' },
    refresh: 1,
    [if regex != '' then 'regex']: regex,
  },

  // Service name variable (custom, defaults to startd8-sdk)
  serviceNameVariable(name='service_name', label='Service'):: {
    name: name,
    label: label,
    type: 'custom',
    query: config.serviceName,
    current: { text: config.serviceName, value: config.serviceName },
  },

  // Generic query variable (GAP-VAR-01) — label_values(...) and any other Grafana
  // query-variable definition. The metric-specific builders below are thin wrappers.
  queryVariable(
    query,
    name='query',
    label='',
    datasource={ type: 'prometheus', uid: '${datasource}' },
    multi=false,
    includeAll=false,
    regex='',
    refresh=1,
  ):: {
    name: name,
    [if label != '' then 'label']: label,
    type: 'query',
    datasource: datasource,
    query: query,
    refresh: refresh,
    [if includeAll then 'includeAll']: true,
    [if includeAll then 'allValue']: '.*',
    [if multi then 'multi']: true,
    [if includeAll then 'current']: { text: 'All', value: '$__all' },
    [if regex != '' then 'regex']: regex,
  },

  // Interval variable (GAP-VAR-03) — e.g. '1m,10m,30m,1h,6h,12h,1d'.
  intervalVariable(query, name='interval', label='Interval'):: {
    name: name,
    [if label != '' then 'label']: label,
    type: 'interval',
    query: query,
    auto: false,
    current: { text: std.split(query, ',')[0], value: std.split(query, ',')[0] },
  },

  // Metric-label variables — thin wrappers over queryVariable (GAP-VAR-01 dedup).
  modelVariable(metric, name='model', label='Model'):: self.queryVariable(
    'label_values(%s{service_name=~"$service_name"}, model)' % metric,
    name=name, label=label, multi=true, includeAll=true,
  ),

  agentVariable(metric, name='agent_name', label='Agent'):: self.queryVariable(
    'label_values(%s{service_name=~"$service_name"}, agent_name)' % metric,
    name=name, label=label, multi=true, includeAll=true,
  ),

  projectVariable(metric, name='project_id', label='Project'):: self.queryVariable(
    'label_values(%s{service_name=~"$service_name"}, project_id)' % metric,
    name=name, label=label, multi=true, includeAll=true,
  ),

  // Custom variable with explicit options
  customVariable(name, label, query, multi=false):: {
    name: name,
    label: label,
    type: 'custom',
    query: query,
    multi: multi,
    current: { text: std.split(query, ',')[0], value: std.split(query, ',')[0] },
  },

  // Constant variable (hidden)
  constantVariable(name, value):: {
    name: name,
    type: 'constant',
    query: value,
    hide: 2,
    current: { text: value, value: value },
  },
}
