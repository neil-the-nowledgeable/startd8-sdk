// Template variable builders for StartD8 dashboards.
local config = (import '../config.libsonnet')._config;

{
  // Prometheus/Mimir datasource variable
  prometheusDatasource(name='datasource', label='Datasource'):: {
    name: name,
    label: label,
    type: 'datasource',
    query: 'prometheus',
    current: { text: 'Mimir', value: 'mimir' },
    refresh: 1,
  },

  // Tempo datasource variable
  tempoDatasource(name='tempo', label='Tempo'):: {
    name: name,
    label: label,
    type: 'datasource',
    query: 'tempo',
    current: { text: 'Tempo', value: 'tempo' },
    refresh: 1,
  },

  // Loki datasource variable
  lokiDatasource(name='loki', label='Loki'):: {
    name: name,
    label: label,
    type: 'datasource',
    query: 'loki',
    current: { text: 'Loki', value: 'loki' },
    refresh: 1,
  },

  // Service name variable (custom, defaults to startd8-sdk)
  serviceNameVariable(name='service_name', label='Service'):: {
    name: name,
    label: label,
    type: 'custom',
    query: config.serviceName,
    current: { text: config.serviceName, value: config.serviceName },
  },

  // Model variable from metric labels
  modelVariable(metric, name='model', label='Model'):: {
    name: name,
    label: label,
    type: 'query',
    datasource: { type: 'prometheus', uid: '${datasource}' },
    query: 'label_values(%s{service_name=~"$service_name"}, model)' % metric,
    refresh: 1,
    includeAll: true,
    allValue: '.*',
    multi: true,
    current: { text: 'All', value: '$__all' },
  },

  // Agent name variable from metric labels
  agentVariable(metric, name='agent_name', label='Agent'):: {
    name: name,
    label: label,
    type: 'query',
    datasource: { type: 'prometheus', uid: '${datasource}' },
    query: 'label_values(%s{service_name=~"$service_name"}, agent_name)' % metric,
    refresh: 1,
    includeAll: true,
    allValue: '.*',
    multi: true,
    current: { text: 'All', value: '$__all' },
  },

  // Project variable from metric labels
  projectVariable(metric, name='project_id', label='Project'):: {
    name: name,
    label: label,
    type: 'query',
    datasource: { type: 'prometheus', uid: '${datasource}' },
    query: 'label_values(%s{service_name=~"$service_name"}, project_id)' % metric,
    refresh: 1,
    includeAll: true,
    allValue: '.*',
    multi: true,
    current: { text: 'All', value: '$__all' },
  },

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
