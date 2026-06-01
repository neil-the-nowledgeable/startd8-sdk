// Dashboard builder helpers.
local config = (import '../config.libsonnet')._config;

{
  // Standard dashboard wrapper
  dashboard(title, uid, description='', tags=[]):: {
    annotations: {
      list: [{
        builtIn: 1,
        datasource: { type: 'grafana', uid: '-- Grafana --' },
        enable: true,
        hide: true,
        iconColor: 'rgba(0, 211, 255, 1)',
        name: 'Annotations & Alerts',
        type: 'dashboard',
      }],
    },
    editable: true,
    fiscalYearStartMonth: 0,
    graphTooltip: 0,
    id: null,
    links: [],
    liveNow: false,
    panels: [],
    refresh: config.dashboardRefresh,
    schemaVersion: 39,
    tags: config.dashboardTags + tags,
    time: { from: config.dashboardTimeFrom, to: config.dashboardTimeTo },
    title: title,
    uid: uid,
    version: 1,
    [if description != '' then 'description']: description,
  },

  // Attach panels + assign ids. AES-030b: the Python layout pass (apply_layout) is the
  // single source of layout truth and always fills gridPos before compile; withPanels
  // trusts incoming gridPos and fails loud rather than silently synthesizing an
  // overlapping {x:0,y:0} — protecting direct mixin consumers that bypass apply_layout.
  withPanels(dashboard, panels)::
    dashboard {
      panels: std.mapWithIndex(
        function(i, p)
          (if std.objectHas(p, 'gridPos') then {}
           else error 'withPanels: panel %d (%s) has no gridPos — run apply_layout first'
                      % [i, if std.objectHas(p, 'title') then p.title else '?'])
          + p + { id: i + 1 },
        panels
      ),
    },
}
