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

  // Add panels to dashboard with auto-positioned gridPos
  withPanels(dashboard, panels)::
    dashboard {
      panels: std.mapWithIndex(
        function(i, p)
          p + (
            if std.objectHas(p, 'gridPos') then {}
            else { gridPos: { h: 8, w: 12, x: (i % 2) * 12, y: std.floor(i / 2) * 8 } }
          ) + { id: i + 1 },
        panels
      ),
    },
}
