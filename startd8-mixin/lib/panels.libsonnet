// Panel construction helpers for StartD8 dashboards.
local config = (import '../config.libsonnet')._config;
{
  // Stat panel (single value)
  stat(title, expr, datasource={ type: 'prometheus', uid: '${datasource}' }, unit='', thresholds=[], decimals=null, instant=false, legendFormat=''):: {
    title: title,
    type: 'stat',
    datasource: datasource,
    targets: [{
      expr: expr,
      refId: 'A',
      [if instant then 'instant']: true,
      [if legendFormat != '' then 'legendFormat']: legendFormat,
    }],
    fieldConfig: {
      defaults: {
        [if unit != '' then 'unit']: unit,
        [if decimals != null then 'decimals']: decimals,
        color: { mode: 'thresholds' },
        thresholds: {
          mode: 'absolute',
          steps: if std.length(thresholds) > 0 then thresholds else [
            { color: 'green', value: null },
          ],
        },
      },
      overrides: [],
    },
    options: {
      reduceOptions: { calcs: ['lastNotNull'], fields: '', values: false },
      colorMode: 'value',
      graphMode: 'area',
      justifyMode: 'auto',
      textMode: 'auto',
      wideLayout: true,
      orientation: 'auto',
    },
  },

  // Gauge panel
  gauge(title, expr, datasource={ type: 'prometheus', uid: '${datasource}' }, unit='percent', min=0, max=100, thresholds=[], instant=false):: {
    title: title,
    type: 'gauge',
    datasource: datasource,
    targets: [{
      expr: expr,
      refId: 'A',
      [if instant then 'instant']: true,
    }],
    fieldConfig: {
      defaults: {
        unit: unit,
        min: min,
        max: max,
        color: { mode: 'thresholds' },
        thresholds: {
          mode: 'absolute',
          // AES-020: no arbitrary magic-number default ramp — a base step only,
          // unless the spec supplies thresholds (recipes set the actionable range).
          // config.legacyThresholds restores the old 80/100 ramp for consumers that relied on it.
          steps: if std.length(thresholds) > 0 then thresholds
                 else if config.legacyThresholds then [
                   { color: 'red', value: null },
                   { color: 'yellow', value: 80 },
                   { color: 'green', value: 100 },
                 ] else [
                   { color: 'green', value: null },
                 ],
        },
        mappings: [],
      },
      overrides: [],
    },
    options: {
      showThresholdLabels: false,
      showThresholdMarkers: true,
      orientation: 'auto',
      reduceOptions: { calcs: ['lastNotNull'], fields: '', values: false },
      text: {},
    },
  },

  // Time series panel
  timeseries(title, targets, datasource={ type: 'prometheus', uid: '${datasource}' }, unit='', overrides=[], legendMode='list', legendPlacement='bottom', legendCalcs=[], fillOpacity=10, lineWidth=1, drawStyle='line', stacking='none', lineInterpolation='linear', thresholds=[]):: {
    title: title,
    type: 'timeseries',
    datasource: datasource,
    targets: targets,
    fieldConfig: {
      defaults: {
        [if unit != '' then 'unit']: unit,
        color: { mode: if std.length(thresholds) > 0 then 'thresholds' else 'palette-classic' },
        [if std.length(thresholds) > 0 then 'thresholds']: { mode: 'absolute', steps: thresholds },
        custom: {
          drawStyle: drawStyle,
          lineInterpolation: lineInterpolation,
          fillOpacity: fillOpacity,
          lineWidth: lineWidth,
          pointSize: 5,
          showPoints: 'auto',
          stacking: { group: 'A', mode: stacking },
        },
      },
      overrides: overrides,
    },
    options: {
      tooltip: { mode: 'multi', sort: 'desc' },
      legend: {
        displayMode: legendMode,
        placement: legendPlacement,
        [if std.length(legendCalcs) > 0 then 'calcs']: legendCalcs,
      },
    },
  },

  // Table panel
  table(title, targets, datasource={ type: 'prometheus', uid: '${datasource}' }, overrides=[], transformations=[]):: {
    title: title,
    type: 'table',
    datasource: datasource,
    targets: targets,
    fieldConfig: { defaults: {}, overrides: overrides },
    options: {
      showHeader: true,
      sortBy: [],
    },
    [if std.length(transformations) > 0 then 'transformations']: transformations,
  },

  // Bar chart panel
  barchart(title, targets, datasource={ type: 'prometheus', uid: '${datasource}' }, unit='', orientation='horizontal', stacking='normal', showValue='auto', decimals=null):: {
    title: title,
    type: 'barchart',
    datasource: datasource,
    targets: targets,
    fieldConfig: {
      defaults: {
        [if unit != '' then 'unit']: unit,
        [if decimals != null then 'decimals']: decimals,
        color: { mode: 'palette-classic' },
      },
      overrides: [],
    },
    options: {
      orientation: orientation,
      showValue: showValue,
      stacking: stacking,
      legend: { displayMode: 'list', placement: 'bottom' },
    },
  },

  // Bar gauge panel
  barGauge(title, expr, datasource={ type: 'prometheus', uid: '${datasource}' }, unit='percent', min=0, max=100, thresholds=[], legendFormat='', instant=false):: {
    title: title,
    type: 'bargauge',
    datasource: datasource,
    targets: [{
      expr: expr,
      refId: 'A',
      [if instant then 'instant']: true,
      [if legendFormat != '' then 'legendFormat']: legendFormat,
    }],
    fieldConfig: {
      defaults: {
        unit: unit,
        min: min,
        max: max,
        color: { mode: 'thresholds' },
        thresholds: {
          mode: 'absolute',
          // AES-020: base step only by default; config.legacyThresholds restores the old 60/80 ramp.
          steps: if std.length(thresholds) > 0 then thresholds
                 else if config.legacyThresholds then [
                   { color: 'red', value: null },
                   { color: 'yellow', value: 60 },
                   { color: 'green', value: 80 },
                 ] else [
                   { color: 'green', value: null },
                 ],
        },
      },
      overrides: [],
    },
    options: {
      displayMode: 'gradient',
      orientation: 'horizontal',
      reduceOptions: { calcs: ['lastNotNull'], fields: '', values: false },
      showUnfilled: true,
      valueMode: 'color',
    },
  },

  // Pie chart panel
  // AES-014: corpus-mode defaults — donut, legend at bottom, percent labels.
  piechart(title, targets, datasource={ type: 'prometheus', uid: '${datasource}' }, unit='', pieType='donut', legendMode='list', legendPlacement='bottom', overrides=[]):: {
    title: title,
    type: 'piechart',
    datasource: datasource,
    targets: targets,
    fieldConfig: {
      defaults: {
        [if unit != '' then 'unit']: unit,
        color: { mode: 'palette-classic' },
        custom: {
          hideFrom: { legend: false, tooltip: false, viz: false },
        },
        mappings: [],
      },
      overrides: overrides,
    },
    options: {
      legend: { displayMode: legendMode, placement: legendPlacement, showLegend: true },
      pieType: pieType,
      displayLabels: ['percent'],
      reduceOptions: { calcs: ['lastNotNull'], fields: '', values: false },
      tooltip: { mode: 'single', sort: 'none' },
    },
  },

  // Histogram panel
  histogram(title, targets, datasource={ type: 'prometheus', uid: '${datasource}' }, unit='', thresholds=[]):: {
    title: title,
    type: 'histogram',
    datasource: datasource,
    targets: targets,
    fieldConfig: {
      defaults: {
        color: { mode: if std.length(thresholds) > 0 then 'thresholds' else 'palette-classic' },
        custom: {
          fillOpacity: 80,
          gradientMode: 'none',
          hideFrom: { legend: false, tooltip: false, viz: false },
          lineWidth: 1,
          stacking: { group: 'A', mode: 'none' },
        },
        mappings: [],
        thresholds: {
          mode: 'absolute',
          steps: if std.length(thresholds) > 0 then thresholds else [{ color: 'green', value: null }],
        },
        [if unit != '' then 'unit']: unit,
      },
      overrides: [],
    },
    options: {
      bucketOffset: 0,
      legend: {
        calcs: ['mean', 'max'],
        displayMode: 'list',
        placement: 'bottom',
        showLegend: true,
      },
    },
  },

  // Logs panel (Loki)
  logs(title, expr, datasource={ type: 'loki', uid: '${loki}' }, maxLines=200):: {
    title: title,
    type: 'logs',
    datasource: datasource,
    targets: [{
      expr: expr,
      refId: 'A',
      [if maxLines != 200 then 'maxLines']: maxLines,
    }],
    options: {
      showTime: true,
      showLabels: true,
      enableLogDetails: true,
      sortOrder: 'Descending',
    },
  },

  // Row (section header)
  row(title, y=0, collapsed=false):: {
    type: 'row',
    title: title,
    collapsed: collapsed,
    gridPos: { h: 1, w: 24, x: 0, y: y },
    panels: [],
  },

  // Stat panel for TraceQL queries
  traceqlStat(title, query, datasource={ type: 'tempo', uid: '${tempo}' }, limit=1000, thresholds=[], calcs=['count'], graphMode='none', unit=''):: {
    title: title,
    type: 'stat',
    datasource: datasource,
    targets: [{
      datasource: datasource,
      limit: limit,
      query: query,
      queryType: 'traceql',
      refId: 'A',
    }],
    fieldConfig: {
      defaults: {
        color: { mode: if std.length(thresholds) > 0 then 'thresholds' else 'palette-classic' },
        mappings: [],
        thresholds: {
          mode: 'absolute',
          steps: if std.length(thresholds) > 0 then thresholds else [
            { color: 'green', value: null },
          ],
        },
        [if unit != '' then 'unit']: unit,
      },
      overrides: [],
    },
    options: {
      colorMode: 'value',
      graphMode: graphMode,
      justifyMode: 'auto',
      orientation: 'auto',
      reduceOptions: { calcs: calcs, fields: '', values: false },
      textMode: 'auto',
    },
  },

  // Table panel for TraceQL queries
  traceqlTable(title, query, datasource={ type: 'tempo', uid: '${tempo}' }, limit=100, overrides=[]):: {
    title: title,
    type: 'table',
    datasource: datasource,
    targets: [{
      datasource: datasource,
      limit: limit,
      query: query,
      queryType: 'traceql',
      refId: 'A',
    }],
    fieldConfig: {
      defaults: {
        color: { mode: 'thresholds' },
        custom: {
          align: 'auto',
          cellOptions: { type: 'auto' },
          inspect: false,
        },
        mappings: [],
        thresholds: {
          mode: 'absolute',
          steps: [{ color: 'green', value: null }],
        },
      },
      overrides: overrides,
    },
    options: {
      cellHeight: 'sm',
      footer: {
        countRows: false,
        fields: '',
        reducer: ['sum'],
        show: false,
      },
      showHeader: true,
    },
  },

  // Timeseries panel for TraceQL queries
  traceqlTimeseries(title, targets, datasource={ type: 'tempo', uid: '${tempo}' }, unit='', overrides=[]):: {
    title: title,
    type: 'timeseries',
    datasource: datasource,
    targets: targets,
    fieldConfig: {
      defaults: {
        color: { mode: 'palette-classic' },
        custom: {
          drawStyle: 'line',
          fillOpacity: 10,
          lineInterpolation: 'linear',
          lineWidth: 1,
          pointSize: 5,
          showPoints: 'auto',
          stacking: { group: 'A', mode: 'none' },
        },
        mappings: [],
        thresholds: {
          mode: 'absolute',
          steps: [{ color: 'green', value: null }],
        },
        [if unit != '' then 'unit']: unit,
      },
      overrides: overrides,
    },
    options: {
      legend: {
        calcs: ['mean', 'max'],
        displayMode: 'table',
        placement: 'bottom',
        showLegend: true,
      },
      tooltip: { mode: 'multi', sort: 'none' },
    },
  },

  // Gauge panel for TraceQL queries
  traceqlGauge(title, query, datasource={ type: 'tempo', uid: '${tempo}' }, limit=100, unit='none', min=0, max=100, thresholds=[]):: {
    title: title,
    type: 'gauge',
    datasource: datasource,
    targets: [{
      datasource: datasource,
      limit: limit,
      query: query,
      queryType: 'traceql',
      refId: 'A',
    }],
    fieldConfig: {
      defaults: {
        color: { mode: 'thresholds' },
        mappings: [],
        max: max,
        min: min,
        thresholds: {
          mode: 'absolute',
          steps: if std.length(thresholds) > 0 then thresholds else [
            { color: 'green', value: null },
          ],
        },
        unit: unit,
      },
      overrides: [],
    },
    options: {
      minVizHeight: 75,
      minVizWidth: 75,
      orientation: 'auto',
      reduceOptions: { calcs: ['count'], fields: '', values: false },
      showThresholdLabels: false,
      showThresholdMarkers: true,
      sizing: 'auto',
    },
  },

  // Traces panel (Tempo)
  traces(title, query, datasource={ type: 'tempo', uid: '${tempo}' }):: {
    title: title,
    type: 'traces',
    datasource: datasource,
    targets: [{
      datasource: datasource,
      query: query,
      queryType: 'traceql',
      refId: 'A',
    }],
    fieldConfig: { defaults: {}, overrides: [] },
    options: {},
  },

  // Text panel (markdown)
  text(title, content):: {
    title: title,
    type: 'text',
    options: {
      mode: 'markdown',
      content: content,
    },
  },

  // Dashboard-list panel: links to dashboards carrying any of `tags` (Workbook portfolio index, FR-11).
  // No datasource/targets — Grafana resolves the tag filter at view time, so the list is self-updating.
  dashlist(title, tags=[], showSearch=false, showHeadings=true):: {
    title: title,
    type: 'dashlist',
    options: {
      showSearch: showSearch,
      showHeadings: showHeadings,
      showStarred: false,
      showRecentlyViewed: false,
      tags: tags,
    },
  },

  // --- Phase 5: new panel types ------------------------------------------

  // Geomap (markers layer; size/color by field)
  geomap(title, targets, datasource={ type: 'prometheus', uid: '${datasource}' }, unit=''):: {
    title: title,
    type: 'geomap',
    datasource: datasource,
    targets: targets,
    fieldConfig: {
      defaults: {
        [if unit != '' then 'unit']: unit,
        color: { mode: 'continuous-BlYlRd' },
      },
      overrides: [],
    },
    options: {
      view: { id: 'zero', lat: 0, lon: 0, zoom: 1, allLayers: true, shared: false },
      basemap: { type: 'default', name: 'Layer 0' },
      controls: { mouseWheelZoom: true, showZoom: true, showAttribution: true, showScale: false },
      tooltip: { mode: 'details' },
      layers: [{
        type: 'markers',
        name: 'Markers',
        tooltip: true,
        location: { mode: 'auto' },
        config: {
          showLegend: true,
          style: {
            symbol: { mode: 'fixed', fixed: 'img/icons/marker/circle.svg' },
            color: { fixed: 'dark-green' },
            size: { fixed: 5, min: 2, max: 15 },
            opacity: 0.4,
          },
        },
      }],
    },
  },

  // Canvas (empty frame; elements added via spec options)
  canvas(title, targets, datasource={ type: 'prometheus', uid: '${datasource}' }):: {
    title: title,
    type: 'canvas',
    datasource: datasource,
    targets: targets,
    fieldConfig: { defaults: {}, overrides: [] },
    options: {
      inlineEditing: false,
      showAdvancedTypes: true,
      panZoom: false,
      root: { type: 'frame', elements: [], placement: { top: 0, left: 0, width: 100, height: 100 } },
    },
  },

  // Heatmap
  heatmap(title, targets, datasource={ type: 'prometheus', uid: '${datasource}' }, unit=''):: {
    title: title,
    type: 'heatmap',
    datasource: datasource,
    targets: targets,
    fieldConfig: {
      defaults: { custom: { hideFrom: { legend: false, tooltip: false, viz: false } } },
      overrides: [],
    },
    options: {
      calculate: false,
      color: { scheme: 'Oranges', mode: 'scheme', steps: 64, reverse: false },
      yAxis: { [if unit != '' then 'unit']: unit, axisPlacement: 'left' },
      cellGap: 1,
      legend: { show: true },
      tooltip: { show: true, yHistogram: false },
    },
  },

  // State timeline (discrete state over time)
  stateTimeline(title, targets, datasource={ type: 'prometheus', uid: '${datasource}' }, unit=''):: {
    title: title,
    type: 'state-timeline',
    datasource: datasource,
    targets: targets,
    fieldConfig: {
      defaults: {
        [if unit != '' then 'unit']: unit,
        custom: { lineWidth: 0, fillOpacity: 70 },
        color: { mode: 'continuous-GrYlRd' },
      },
      overrides: [],
    },
    options: {
      mergeValues: true,
      showValue: 'auto',
      alignValue: 'left',
      rowHeight: 0.9,
      legend: { displayMode: 'list', placement: 'bottom', showLegend: true },
      tooltip: { mode: 'single', sort: 'none' },
    },
  },

  // XY chart (scatter / bubble)
  xychart(title, targets, datasource={ type: 'prometheus', uid: '${datasource}' }):: {
    title: title,
    type: 'xychart',
    datasource: datasource,
    targets: targets,
    fieldConfig: {
      defaults: {
        custom: { show: 'points', pointSize: { fixed: 5 }, axisPlacement: 'auto' },
      },
      overrides: [],
    },
    options: { mapping: 'auto', series: [] },
  },

  // Candlestick (OHLC + volume)
  candlestick(title, targets, datasource={ type: 'prometheus', uid: '${datasource}' }):: {
    title: title,
    type: 'candlestick',
    datasource: datasource,
    targets: targets,
    fieldConfig: { defaults: { custom: {} }, overrides: [] },
    options: {
      mode: 'candles+volume',
      candleStyle: 'candles',
      colorStrategy: 'open-close',
      colors: { up: 'green', down: 'red' },
      includeAllFields: false,
      legend: { displayMode: 'list', placement: 'bottom', showLegend: true },
      tooltip: { mode: 'multi', sort: 'none' },
    },
  },
}
