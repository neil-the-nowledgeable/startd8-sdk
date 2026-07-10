"""
Jsonnet template engine — transforms DashboardSpec into .libsonnet (DC-100–DC-104).

The generator is stateless and pure — no side effects, no file I/O.
Generated Jsonnet follows the overview.libsonnet composition pattern:
  1. Import config, dashboards, panels, variables
  2. Extract local m = config.metrics, ds = config.datasources, sel = config.selectors
  3. Create baseDashboard via dashboards.dashboard()
  4. Add templating list from variables
  5. Call dashboards.withPanels(baseDashboard, [...])
"""

import json
import re
from typing import Any, List, Optional

from startd8.dashboard_creator.models import (
    DashboardLink,
    DashboardSpec,
    DataLink,
    PanelSpec,
    PanelType,
    TargetSpec,
    TransformSpec,
    VariableSpec,
    VariableType,
)

_METRIC_REF = re.compile(r"\$\{metrics\.(\w+)\}")
_SELECTOR_REF = re.compile(r"\$\{selectors\.(\w+)\}")
_COMBINED_REF = re.compile(r"\$\{(metrics|selectors)\.(\w+)\}")
# Config refs require the Jsonnet (not JSON) path — they resolve to m.X / sel.Y.
_CONFIG_REF = re.compile(r"\$\{(?:metrics|selectors)\.\w+\}")


def _to_jsonnet(obj: Any) -> str:
    """Serialize an inert data value to Jsonnet (REQ-DCR-RCP-024), fencing config-refs
    at every leaf (REQ-DCR-RCP-025).

    JSON ⊆ Jsonnet, so ``json.dumps`` is valid for any config-ref-free value. A leaf
    string containing ``${metrics.*}`` / ``${selectors.*}`` is instead routed through
    ``_render_expression`` so it resolves to ``m.X`` / ``sel.Y`` rather than being
    emitted as an inert literal. Deterministic: dict keys are sorted (REQ-DCR-RCP-024
    / R1-S10). Raises on unserializable types instead of the old silent ``repr()``.
    """
    if isinstance(obj, dict):
        body = ", ".join(
            f"{json.dumps(str(k))}: {_to_jsonnet(obj[k])}" for k in sorted(obj)
        )
        return "{" + body + "}"
    if isinstance(obj, list):
        return "[" + ", ".join(_to_jsonnet(v) for v in obj) + "]"
    if isinstance(obj, str) and _CONFIG_REF.search(obj):
        return _render_expression(obj)
    if isinstance(obj, (str, int, float, bool)) or obj is None:
        return json.dumps(obj)
    raise TypeError(
        f"Cannot serialize {type(obj).__name__} to Jsonnet: {obj!r}"
    )


def generate_dashboard_jsonnet(
    spec: DashboardSpec,
    config_overlay_filename: Optional[str] = None,
) -> str:
    """DC-100: Transform DashboardSpec into a .libsonnet string.

    Args:
        spec: Validated DashboardSpec.
        config_overlay_filename: If set, the generated Jsonnet merges a config
            overlay on top of the base ``config.libsonnet`` so that
            ``config_overrides`` take effect during compilation (DC-005 AC3).
    """
    lines: List[str] = []

    # Imports — merge config overlay when overrides are present
    if config_overlay_filename:
        # Guard against path traversal — only bare filenames are safe
        if "/" in config_overlay_filename or "\\" in config_overlay_filename or ".." in config_overlay_filename:
            raise ValueError(
                f"config_overlay_filename must be a bare filename, "
                f"got: {config_overlay_filename!r}"
            )
        lines.append(
            f"local config = ((import '../config.libsonnet') + "
            f"(import '../{config_overlay_filename}'))._config;"
        )
    else:
        lines.append("local config = (import '../config.libsonnet')._config;")
    lines.append("local dashboards = import '../lib/dashboards.libsonnet';")
    lines.append("local panels = import '../lib/panels.libsonnet';")
    lines.append("local variables = import '../lib/variables.libsonnet';")
    lines.append("")
    lines.append("local m = config.metrics;")
    lines.append("local ds = config.datasources;")
    lines.append("local sel = config.selectors;")
    lines.append("")

    # Datasource shortcuts. A bound datasource UID (REQ_DATASOURCE_UID_BINDING FR-4),
    # injected via config_overrides under a key the base config lacks
    # (``prometheusBound``/``lokiBound``), pins the panel datasource to the target
    # Grafana's real UID. Absent ⇒ the ``${...}`` variable, byte-identical to prior output.
    lines.append(
        "local mimirDatasource = { type: 'prometheus', uid: "
        "(if std.objectHas(ds, 'prometheusBound') then ds.prometheusBound.uid "
        "else '${datasource}') };"
    )
    lines.append("local tempoDatasource = { type: 'tempo', uid: '${tempo}' };")
    lines.append(
        "local lokiDatasource = { type: 'loki', uid: "
        "(if std.objectHas(ds, 'lokiBound') then ds.lokiBound.uid "
        "else '${loki}') };"
    )
    lines.append("")

    # Base dashboard
    tags_str = ", ".join(f"'{_escape_jsonnet_string(t)}'" for t in spec.tags)
    desc_arg = ""
    if spec.description:
        desc_arg = f"\n  description='{_escape_jsonnet_string(spec.description)}',"
    lines.append("local baseDashboard = dashboards.dashboard(")
    lines.append(f"  '{_escape_jsonnet_string(spec.title)}',")
    lines.append(f"  '{_escape_jsonnet_string(spec.uid)}',{desc_arg}")
    lines.append(f"  tags=[{tags_str}],")

    # AES-041: shared crosshair (graphTooltip: 1) when the dashboard has >= 2
    # timeseries panels; otherwise leave the mixin default (0).
    n_timeseries = sum(
        1 for p in spec.panels
        if p.type in (PanelType.TIMESERIES, PanelType.TRACEQL_TIMESERIES)
    )
    shared_crosshair = n_timeseries >= 2

    # Merge block fields. ALWAYS emit a `templating.list` (empty when there are no variables) so every
    # generated dashboard carries the key Grafana + the post-compile JSON validation require — a
    # variable-less dashboard (e.g. the FR-11 dashlist index) is valid. Output is byte-identical for
    # specs that have variables (the list is populated exactly as before).
    lines.append(") {")
    if shared_crosshair:
        lines.append("  graphTooltip: 1,")
    lines.append("  templating: {")
    lines.append("    list: [")
    for var in spec.variables:
        lines.append(f"      {_render_variable(var)},")
    lines.append("    ],")
    lines.append("  },")
    if spec.links:
        lines.append("  links: [")
        for link in spec.links:
            lines.append(f"    {_render_dashboard_link(link)},")
        lines.append("  ],")
    lines.append("};")

    lines.append("")

    # Panels
    lines.append("dashboards.withPanels(baseDashboard, [")
    for panel in spec.panels:
        lines.append(f"  {_render_panel(panel)},")
    lines.append("])")
    lines.append("")

    return "\n".join(lines)


def _render_panel(panel: PanelSpec) -> str:
    """DC-101: Render a PanelSpec as a panels.*() constructor call."""
    # REQ-DCR-RCP-020: apply the named recipe (corpus-mode finish) under the panel's
    # explicit values before rendering. No-op when panel.recipe is unset/unknown.
    from startd8.dashboard_creator.recipes import hydrate_panel

    panel, _ = hydrate_panel(panel)
    ptype = panel.type

    if ptype == PanelType.ROW:
        collapsed = "true" if panel.options.get("collapsed") else "false"
        call = f"panels.row('{_escape_jsonnet_string(panel.title)}', collapsed={collapsed})"
        merge_block = _render_merge_block(panel)
        if merge_block:
            call += f" {merge_block}"
        return call

    if ptype == PanelType.TEXT:
        content = _escape_jsonnet_string(panel.options.get("content", ""))
        call = f"panels.text('{_escape_jsonnet_string(panel.title)}', '{content}')"
        merge_block = _render_merge_block(panel)
        if merge_block:
            call += f" {merge_block}"
        return call

    if ptype == PanelType.DASHLIST:
        # A link-list of dashboards by tag (FR-11). No targets/datasource; tags + toggles from options.
        opts = panel.options or {}
        tags = opts.get("tags", []) or []
        tags_lit = "[" + ", ".join(f"'{_escape_jsonnet_string(str(t))}'" for t in tags) + "]"
        show_search = "true" if opts.get("showSearch") else "false"
        show_headings = "false" if opts.get("showHeadings") is False else "true"
        call = (
            f"panels.dashlist('{_escape_jsonnet_string(panel.title)}', "
            f"tags={tags_lit}, showSearch={show_search}, showHeadings={show_headings})"
        )
        merge_block = _render_merge_block(panel)
        if merge_block:
            call += f" {merge_block}"
        return call

    constructor = _panel_constructor_name(ptype)
    args: List[str] = [f"'{_escape_jsonnet_string(panel.title)}'"]

    # Single-target panels: pass expr/query as second positional arg
    if ptype in _SINGLE_TARGET_TYPES:
        if panel.expr:
            args.append(_render_expression(panel.expr))
        elif panel.query:
            args.append(_render_expression(panel.query))
        elif panel.targets and len(panel.targets) == 1:
            t = panel.targets[0]
            if t.expr:
                args.append(_render_expression(t.expr))
            elif t.query:
                args.append(_render_expression(t.query))

    # Multi-target panels: pass targets as named arg
    if ptype in _MULTI_TARGET_TYPES:
        if panel.targets:
            args.append(_render_targets(panel.targets))
        elif panel.expr:
            # Single expr wrapped as target array for timeseries etc.
            args.append(
                f"[{{ expr: {_render_expression(panel.expr)}, refId: 'A' }}]"
            )

    # Datasource (DC-112): explicit selector → query language → panel-type default.
    ds = _panel_datasource(panel)
    if ds:
        args.append(f"datasource={ds}")

    # Unit
    if panel.unit:
        args.append(f"unit='{_escape_jsonnet_string(panel.unit)}'")

    # Thresholds
    if panel.thresholds:
        th_items = []
        for step in panel.thresholds:
            val = "null" if step.value is None else str(step.value)
            th_items.append(f"{{ color: '{_escape_jsonnet_string(step.color)}', value: {val} }}")
        args.append(f"thresholds=[{', '.join(th_items)}]")

    # Overrides
    if panel.overrides:
        args.append(f"overrides={_to_jsonnet(panel.overrides)}")

    sep = ",\n    "
    call = f"panels.{constructor}(\n    {sep.join(args)},\n  )"

    # Build merge block for gridPos, description, fieldConfig, dataLinks, transformations
    merge_block = _render_merge_block(panel)
    if merge_block:
        call += f" {merge_block}"

    return call


def _render_variable(variable: VariableSpec) -> str:
    """DC-102: Render a VariableSpec as a variables.*() builder call."""
    vtype = variable.type
    builder = _variable_builder_name(vtype)

    # Constant takes (name, value) positionally — separate path
    if vtype == VariableType.CONSTANT:
        return (f"variables.{builder}('{_escape_jsonnet_string(variable.name)}', "
                f"'{_escape_jsonnet_string(variable.value or '')}')")

    args: List[str] = []

    # Metric-based variables: metric is first positional arg
    if vtype in {VariableType.MODEL, VariableType.AGENT, VariableType.PROJECT}:
        if variable.metric:
            args.append(_render_expression(variable.metric))

    # Name and label
    if variable.name:
        args.append(f"name='{_escape_jsonnet_string(variable.name)}'")
    if variable.label:
        args.append(f"label='{_escape_jsonnet_string(variable.label)}'")

    # Custom variable: query and multi
    if vtype == VariableType.CUSTOM:
        if variable.query:
            args.append(f"query='{_escape_jsonnet_string(variable.query)}'")
        if variable.multi:
            args.append("multi=true")

    # Query variable (GAP-VAR-01): query/definition is the first positional arg;
    # multi/includeAll/regex/datasource are constructor args the builder consumes.
    if vtype == VariableType.QUERY:
        args.insert(0, _render_expression(variable.query or ""))
        if variable.datasource_var:
            args.append(
                f"datasource={{ type: 'prometheus', uid: "
                f"'{_escape_jsonnet_string(variable.datasource_var)}' }}"
            )
        if variable.multi:
            args.append("multi=true")
        if variable.includeAll:
            args.append("includeAll=true")
        if variable.regex:
            args.append(f"regex='{_escape_jsonnet_string(variable.regex)}'")

    # Interval variable (GAP-VAR-03): options list is the first positional arg.
    if vtype == VariableType.INTERVAL:
        args.insert(0, f"'{_escape_jsonnet_string(variable.query or '')}'")

    # Datasource variable regex filter (GAP-VAR-02).
    if vtype in {
        VariableType.PROMETHEUS_DATASOURCE,
        VariableType.TEMPO_DATASOURCE,
        VariableType.LOKI_DATASOURCE,
    } and variable.regex:
        args.append(f"regex='{_escape_jsonnet_string(variable.regex)}'")

    call = f"variables.{builder}({', '.join(args)})"

    # Extended options + default go in a merge block (not constructor args).
    # For QUERY the builder already emits includeAll/allValue/current, so skip them
    # here to avoid duplicate Jsonnet keys.
    merge_fields: List[str] = []
    if variable.includeAll and vtype != VariableType.QUERY:
        merge_fields.append("includeAll: true")
    if variable.allValue is not None and vtype != VariableType.QUERY:
        merge_fields.append(f"allValue: '{_escape_jsonnet_string(variable.allValue)}'")
    if variable.hide != 0:
        merge_fields.append(f"hide: {variable.hide}")
    if variable.skipUrlSync:
        merge_fields.append("skipUrlSync: true")
    if variable.default is not None:
        escaped = _escape_jsonnet_string(variable.default)
        merge_fields.append(f"current: {{ text: '{escaped}', value: '{escaped}' }}")

    if merge_fields:
        call += " { " + ", ".join(merge_fields) + " }"

    return call


def _render_expression(expr: str) -> str:
    """Render an expression string as a Jsonnet string/concat.

    Handles metric/selector refs by splitting the string into
    literal parts and variable references:

    'rate(${metrics.requestsTotal}[5m])' →
    'rate(' + m.requestsTotal + '[5m])'

    Pure metric references (no surrounding text):
    '${metrics.activeSessions}' → m.activeSessions
    """
    # Check if the entire expression is a single reference
    metric_match = re.fullmatch(r"\$\{metrics\.(\w+)\}", expr)
    if metric_match:
        return f"m.{metric_match.group(1)}"

    selector_match = re.fullmatch(r"\$\{selectors\.(\w+)\}", expr)
    if selector_match:
        return f"sel.{selector_match.group(1)}"

    # Mixed expression: split on references
    parts: List[str] = []
    last_end = 0

    for match in _COMBINED_REF.finditer(expr):
        # Literal text before this match
        if match.start() > last_end:
            literal = expr[last_end:match.start()]
            parts.append(f"'{_escape_jsonnet_string(literal)}'")

        # Variable reference
        namespace = match.group(1)
        name = match.group(2)
        if namespace == "metrics":
            parts.append(f"m.{name}")
        else:
            parts.append(f"sel.{name}")

        last_end = match.end()

    # Trailing literal
    if last_end < len(expr):
        literal = expr[last_end:]
        parts.append(f"'{_escape_jsonnet_string(literal)}'")

    if not parts:
        return f"'{_escape_jsonnet_string(expr)}'"

    if len(parts) == 1:
        return parts[0]

    return " + ".join(parts)


def _render_targets(targets: List[TargetSpec]) -> str:
    """Render a list of TargetSpec as a Jsonnet array of objects."""
    items: List[str] = []
    for i, target in enumerate(targets):
        fields: List[str] = []
        if target.expr:
            fields.append(f"expr: {_render_expression(target.expr)}")
        if target.query:
            fields.append(f"query: {_render_expression(target.query)}")
        if target.legendFormat:
            fields.append(f"legendFormat: '{_escape_jsonnet_string(target.legendFormat)}'")
        # A, B, ..., Z for first 26 targets; fallback for >26
        ref_id = target.refId or (chr(65 + i) if i < 26 else f"REF_{i}")
        fields.append(f"refId: '{_escape_jsonnet_string(ref_id)}'")
        if target.datasource:
            fields.append(f"datasource: {_to_jsonnet(target.datasource)}")
        if target.queryType:
            fields.append(f"queryType: '{_escape_jsonnet_string(target.queryType)}'")
        if target.instant:
            fields.append("instant: true")
        if target.format:
            fields.append(f"format: '{target.format}'")
        items.append("{ " + ", ".join(fields) + " }")
    return "[\n      " + ",\n      ".join(items) + ",\n    ]"


def _render_merge_block(panel: PanelSpec) -> str:
    """Build a Jsonnet merge block for extended panel fields.

    Returns empty string if no merge fields are set.
    Uses fieldConfig+: for deep merge to avoid clobbering constructor defaults.
    """
    fields: List[str] = []

    if panel.gridPos:
        gp = panel.gridPos
        fields.append(
            f"gridPos: {{ h: {gp.h}, w: {gp.w}, x: {gp.x}, y: {gp.y} }}"
        )

    if panel.description:
        fields.append(
            f"description: '{_escape_jsonnet_string(panel.description)}'"
        )

    if panel.transformations:
        fields.append(
            f"transformations: {_render_transformations(panel.transformations)}"
        )

    # fieldConfig+: deep merge — combine dataLinks and user fieldConfig
    # Build a single defaults+: with all sub-fields to avoid Jsonnet duplicate keys
    fc_fields: List[str] = []
    defaults_inner: List[str] = []

    if panel.dataLinks:
        defaults_inner.append(
            f"links: {_render_data_links(panel.dataLinks)}"
        )

    if panel.fieldConfig:
        for key, value in panel.fieldConfig.items():
            if key == "defaults" and isinstance(value, dict):
                # Merge into defaults_inner (skip "links" if dataLinks provides it)
                for k, v in value.items():
                    if k == "links" and panel.dataLinks:
                        continue  # dataLinks takes precedence
                    defaults_inner.append(
                        f"{json.dumps(str(k))}: {_to_jsonnet(v)}"
                    )
            else:
                fc_fields.append(f"{json.dumps(str(key))}: {_to_jsonnet(value)}")

    if defaults_inner:
        fc_fields.insert(0, "defaults+: { " + ", ".join(defaults_inner) + " }")

    if fc_fields:
        fields.append("fieldConfig+: { " + ", ".join(fc_fields) + " }")

    # options+: deep-merge the panel's options (recipe finish + spec) onto the
    # constructor's options (REQ-DCR-RCP-020). ROW/TEXT consume options specially
    # (collapsed / content) and are excluded.
    if panel.type not in (PanelType.ROW, PanelType.TEXT) and panel.options:
        opt_fields = [f"{json.dumps(str(k))}: {_to_jsonnet(v)}" for k, v in panel.options.items()]
        fields.append("options+: { " + ", ".join(opt_fields) + " }")

    # Single-target panels: emit instant/format via targets array in merge block
    if panel.type in _SINGLE_TARGET_TYPES and panel.targets and len(panel.targets) == 1:
        t = panel.targets[0]
        target_fields: List[str] = []
        if t.instant:
            target_fields.append("instant: true")
        if t.format:
            target_fields.append(f"format: '{t.format}'")
        if target_fields:
            fields.append("targets: [{ " + ", ".join(target_fields) + " }]")

    if not fields:
        return ""

    return "{\n    " + ",\n    ".join(fields) + ",\n  }"


def _render_data_links(links: List[DataLink]) -> str:
    """Render a list of DataLink as a Jsonnet array."""
    items: List[str] = []
    for link in links:
        parts = [
            f"title: '{_escape_jsonnet_string(link.title)}'",
            f"url: '{_escape_jsonnet_string(link.url)}'",
        ]
        if link.targetBlank:
            parts.append("targetBlank: true")
        else:
            parts.append("targetBlank: false")
        items.append("{ " + ", ".join(parts) + " }")
    return "[" + ", ".join(items) + "]"


def _render_transformations(transforms: List[TransformSpec]) -> str:
    """Render a list of TransformSpec as a Jsonnet array."""
    items: List[str] = []
    for t in transforms:
        parts = [f"id: '{_escape_jsonnet_string(t.id)}'"]
        if t.options:
            parts.append(f"options: {_to_jsonnet(t.options)}")
        items.append("{ " + ", ".join(parts) + " }")
    return "[\n      " + ",\n      ".join(items) + ",\n    ]"


def _render_dashboard_link(link: DashboardLink) -> str:
    """Render a DashboardLink as a Jsonnet object literal."""
    fields: List[str] = [
        f"title: '{_escape_jsonnet_string(link.title)}'",
    ]
    if link.url:
        fields.append(f"url: '{_escape_jsonnet_string(link.url)}'")
    if link.type != "link":
        fields.append(f"type: '{_escape_jsonnet_string(link.type)}'")
    if link.icon != "external link":
        fields.append(f"icon: '{_escape_jsonnet_string(link.icon)}'")
    if link.tooltip:
        fields.append(f"tooltip: '{_escape_jsonnet_string(link.tooltip)}'")
    if not link.targetBlank:
        fields.append("targetBlank: false")
    if link.tags:
        tags_str = ", ".join(f"'{_escape_jsonnet_string(t)}'" for t in link.tags)
        fields.append(f"tags: [{tags_str}]")
    if link.asDropdown:
        fields.append("asDropdown: true")
    if link.includeVars:
        fields.append("includeVars: true")
    if link.keepTime:
        fields.append("keepTime: true")
    return "{ " + ", ".join(fields) + " }"


def _escape_jsonnet_string(s: str) -> str:
    """Escape a string for a Jsonnet single-quoted string literal (REQ-DCR-RCP-026).

    Delegates the escaping to ``json.dumps`` (which correctly handles newlines, tabs,
    control characters, backslashes, and unicode) so a multi-line text-panel content or
    a title containing ``\\n`` no longer produces invalid Jsonnet, and crafted strings
    can't break out of the literal. Output stays in the single-quoted style used
    throughout the generator: take the json.dumps body (already fully escaped) and
    escape ``'`` for the single-quote context. The legacy implementation escaped only
    ``\\`` and ``'`` and silently emitted raw control characters.
    """
    inner = json.dumps(s)[1:-1]  # strip the surrounding double quotes; everything else escaped
    return inner.replace("'", "\\'")


# Panel types whose Jsonnet value is not a valid identifier need an explicit name.
_CONSTRUCTOR_NAMES = {
    PanelType.STATE_TIMELINE: "stateTimeline",  # 'state-timeline' has a hyphen
}


def _panel_constructor_name(ptype: PanelType) -> str:
    """Map PanelType to panels.libsonnet constructor name."""
    return _CONSTRUCTOR_NAMES.get(ptype, ptype.value)


def _variable_builder_name(vtype: VariableType) -> str:
    """Map VariableType to variables.libsonnet builder name."""
    return vtype.value


# DC-112: friendly datasource selector → the jsonnet datasource local defined in the template head.
_DATASOURCE_LOCALS = {
    "tempo": "tempoDatasource",
    "mimir": "mimirDatasource",
    "prometheus": "mimirDatasource",  # the mimir local is the prometheus-typed datasource
    "loki": "lokiDatasource",
}

# TraceQL-metrics functions that only Tempo evaluates (piped after a `{ … }` selector).
_TRACEQL_METRIC_FUNCS = (
    "count_over_time", "rate(", "sum_over_time", "quantile_over_time",
    "histogram_over_time", "min_over_time", "max_over_time", "avg_over_time",
)


# LogQL log-pipe stages (Loki) — matched space-insensitively; a `{ … }` selector carrying any of
# these (or a log-filter operator) is a Loki query, never TraceQL.
_LOGQL_STAGE_RE = re.compile(
    r"\|\s*(json|logfmt|pattern|regexp|unwrap|line_format|label_format|keep|drop|decolorize)\b"
)


def _query_is_traceql(text: Optional[str], query_type: Optional[str] = None) -> bool:
    """True if a target query is a TraceQL (Tempo) query, so a plain panel type still routes to Tempo.

    Detects: an explicit ``queryType == "traceql"``; or a ``{ … }`` selector that references
    ``span.``/``resource.`` attributes or pipes into a TraceQL metrics function
    (``count_over_time()``/``rate()``/…). PromQL never starts with ``{``; LogQL log queries
    (``|=``/``|~`` filters or ``| json``/``| logfmt``/… stages) are excluded so Loki queries are not
    misrouted. The bare ``name`` intrinsic is deliberately NOT a signal — it collides with a PromQL
    bare-vector selector on a ``name`` label (e.g. cAdvisor ``{name="ctr"}``); rely on an explicit
    ``queryType``/``target.query`` for those TraceQL cases (DC-112).
    """
    if query_type and query_type.strip().lower() == "traceql":
        return True
    if not text:
        return False
    s = text.strip()
    if not s.startswith("{"):
        return False
    # Exclude LogQL (Loki), which also uses `{ … }` selectors.
    if any(op in s for op in ("|=", "|~", "!=", "!~")) or _LOGQL_STAGE_RE.search(s):
        return False
    if "span." in s or "resource." in s:
        return True
    return any(fn in s for fn in _TRACEQL_METRIC_FUNCS)


_TEMPO_PANEL_TYPES = {
    PanelType.TRACEQL_STAT,
    PanelType.TRACEQL_TABLE,
    PanelType.TRACEQL_TIMESERIES,
    PanelType.TRACEQL_GAUGE,
    PanelType.TRACES,
}


def _panel_datasource(panel: "PanelSpec") -> str:
    """Resolve a panel's datasource by priority (DC-112): explicit selector → typed panel → query.

    Rung 1 — an explicit ``panel.datasource`` selector wins. Rung 2 — an explicit datasource-bound
    panel TYPE (traceql*/traces→Tempo, logs→Loki) is the author's intent and beats the query
    heuristic (so a ``logs`` panel is never re-routed by a name-like label). Rung 3 — for a generic
    type, any TraceQL target routes to Tempo (the trap this fixes). Rung 4 — default Mimir.
    """
    if panel.datasource:
        local = _DATASOURCE_LOCALS.get(panel.datasource.strip().lower())
        if local:
            return local
    if panel.type in _TEMPO_PANEL_TYPES:
        return "tempoDatasource"
    if panel.type == PanelType.LOGS:
        return "lokiDatasource"
    # Rung 3 — generic panel type: infer from the query language. `query`-field values (single or
    # per-target) are TraceQL by model contract (PanelSpec.query / TargetSpec.query), so tag them
    # accordingly — otherwise a TraceQL intrinsic query on the multi-target path (e.g.
    # `{ .foo = "bar" }`) would miss the text heuristic and re-open the trap (DC-112).
    queries = [(panel.expr, None)] if panel.expr else []
    if panel.query:
        queries.append((panel.query, "traceql"))
    for t in panel.targets or []:
        qt = getattr(t, "queryType", None) or ("traceql" if (t.query and not t.expr) else None)
        queries.append((t.expr or t.query, qt))
    if any(_query_is_traceql(text, qt) for text, qt in queries):
        return "tempoDatasource"
    return "mimirDatasource"


# Panel types that take a single expression as 2nd positional arg
_SINGLE_TARGET_TYPES = {
    PanelType.STAT,
    PanelType.GAUGE,
    PanelType.BAR_GAUGE,
    PanelType.LOGS,
    PanelType.TRACEQL_STAT,
    PanelType.TRACEQL_GAUGE,
    PanelType.TRACES,
}

# Panel types that take a targets array
_MULTI_TARGET_TYPES = {
    PanelType.TIMESERIES,
    PanelType.TABLE,
    PanelType.BARCHART,
    PanelType.PIECHART,
    PanelType.HISTOGRAM,
    PanelType.TRACEQL_TABLE,
    PanelType.TRACEQL_TIMESERIES,
    # Phase 5 — new data-bound panels
    PanelType.GEOMAP,
    PanelType.CANVAS,
    PanelType.HEATMAP,
    PanelType.STATE_TIMELINE,
    PanelType.XYCHART,
    PanelType.CANDLESTICK,
}
