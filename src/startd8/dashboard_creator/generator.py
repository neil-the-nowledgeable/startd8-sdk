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

    # Datasource shortcuts
    lines.append("local mimirDatasource = { type: 'prometheus', uid: '${datasource}' };")
    lines.append("local tempoDatasource = { type: 'tempo', uid: '${tempo}' };")
    lines.append("local lokiDatasource = { type: 'loki', uid: '${loki}' };")
    lines.append("")

    # Base dashboard
    tags_str = ", ".join(f"'{t}'" for t in spec.tags)
    desc_arg = ""
    if spec.description:
        desc_arg = f"\n  description='{_escape_jsonnet_string(spec.description)}',"
    lines.append("local baseDashboard = dashboards.dashboard(")
    lines.append(f"  '{_escape_jsonnet_string(spec.title)}',")
    lines.append(f"  '{spec.uid}',{desc_arg}")
    lines.append(f"  tags=[{tags_str}],")

    # Merge block fields (templating, links)
    has_merge = bool(spec.variables) or bool(spec.links)
    if has_merge:
        lines.append(") {")
        if spec.variables:
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
    else:
        lines.append(");")

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
    ptype = panel.type

    if ptype == PanelType.ROW:
        collapsed = "true" if panel.options.get("collapsed") else "false"
        return f"panels.row('{_escape_jsonnet_string(panel.title)}', collapsed={collapsed})"

    if ptype == PanelType.TEXT:
        content = _escape_jsonnet_string(panel.options.get("content", ""))
        return f"panels.text('{_escape_jsonnet_string(panel.title)}', '{content}')"

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

    # Datasource
    ds = _datasource_for_panel(ptype)
    if ds:
        args.append(f"datasource={ds}")

    # Unit
    if panel.unit:
        args.append(f"unit='{panel.unit}'")

    # Thresholds
    if panel.thresholds:
        th_items = []
        for step in panel.thresholds:
            val = "null" if step.value is None else str(step.value)
            th_items.append(f"{{ color: '{step.color}', value: {val} }}")
        args.append(f"thresholds=[{', '.join(th_items)}]")

    # Overrides
    if panel.overrides:
        args.append(f"overrides={_render_jsonnet_value(panel.overrides)}")

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
        return f"variables.{builder}('{variable.name}', '{_escape_jsonnet_string(variable.value or '')}')"

    args: List[str] = []

    # Metric-based variables: metric is first positional arg
    if vtype in {VariableType.MODEL, VariableType.AGENT, VariableType.PROJECT}:
        if variable.metric:
            args.append(_render_expression(variable.metric))

    # Name and label
    if variable.name:
        args.append(f"name='{variable.name}'")
    if variable.label:
        args.append(f"label='{_escape_jsonnet_string(variable.label)}'")

    # Custom variable: query and multi
    if vtype == VariableType.CUSTOM:
        if variable.query:
            args.append(f"query='{_escape_jsonnet_string(variable.query)}'")
        if variable.multi:
            args.append("multi=true")

    call = f"variables.{builder}({', '.join(args)})"

    # Extended options + default go in a merge block (not constructor args)
    merge_fields: List[str] = []
    if variable.includeAll:
        merge_fields.append("includeAll: true")
    if variable.allValue is not None:
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
        fields.append(f"refId: '{ref_id}'")
        if target.datasource:
            fields.append(f"datasource: {_render_jsonnet_value(target.datasource)}")
        if target.queryType:
            fields.append(f"queryType: '{target.queryType}'")
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
                        f"{k}: {_render_jsonnet_value(v)}"
                    )
            else:
                fc_fields.append(f"{key}: {_render_jsonnet_value(value)}")

    if defaults_inner:
        fc_fields.insert(0, "defaults+: { " + ", ".join(defaults_inner) + " }")

    if fc_fields:
        fields.append("fieldConfig+: { " + ", ".join(fc_fields) + " }")

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
            parts.append(f"options: {_render_jsonnet_value(t.options)}")
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
        fields.append(f"type: '{link.type}'")
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


def _render_jsonnet_value(obj: Any) -> str:
    """Convert a Python value to a Jsonnet literal."""
    if isinstance(obj, dict):
        if not obj:
            return "{}"
        fields = [f"{k}: {_render_jsonnet_value(v)}" for k, v in obj.items()]
        return "{ " + ", ".join(fields) + " }"
    elif isinstance(obj, list):
        if not obj:
            return "[]"
        items = [_render_jsonnet_value(item) for item in obj]
        return "[" + ", ".join(items) + "]"
    elif isinstance(obj, str):
        return f"'{_escape_jsonnet_string(obj)}'"
    elif isinstance(obj, bool):
        return "true" if obj else "false"
    elif isinstance(obj, (int, float)):
        return str(obj)
    elif obj is None:
        return "null"
    return repr(obj)


def _escape_jsonnet_string(s: str) -> str:
    """Escape a string for Jsonnet single-quoted string literal."""
    return s.replace("\\", "\\\\").replace("'", "\\'")


def _panel_constructor_name(ptype: PanelType) -> str:
    """Map PanelType to panels.libsonnet constructor name."""
    return ptype.value


def _variable_builder_name(vtype: VariableType) -> str:
    """Map VariableType to variables.libsonnet builder name."""
    return vtype.value


def _datasource_for_panel(ptype: PanelType) -> str:
    """Return the default datasource variable for a panel type."""
    if ptype in {
        PanelType.TRACEQL_STAT,
        PanelType.TRACEQL_TABLE,
        PanelType.TRACEQL_TIMESERIES,
        PanelType.TRACEQL_GAUGE,
        PanelType.TRACES,
    }:
        return "tempoDatasource"
    if ptype == PanelType.LOGS:
        return "lokiDatasource"
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
}
