"""
Parse requirements markdown documents into DashboardSpec YAML.

Converts the 10-section Michigan budget requirements format into
DashboardSpec models that can be serialized to YAML and compiled
by the dashboard creator workflow.

Public API:
    parse_requirements(path) -> DashboardSpec
    requirements_to_yaml(path) -> str
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

from startd8.exceptions import ConfigurationError
from startd8.logging_config import get_logger
from startd8.dashboard_creator.models import (
    DashboardLink,
    DashboardSpec,
    DataLink,
    GridPos,
    PanelSpec,
    PanelType,
    TargetSpec,
    ThresholdStep,
    TransformSpec,
    VariableSpec,
    VariableType,
)

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# UID transform
# ---------------------------------------------------------------------------

_UID_PREFIX = "cc-govbudget-"


def _uid_transform(uid: str) -> str:
    """Transform gov-michigan-X → cc-govbudget-michigan-X. Already cc-* → keep."""
    if uid.startswith("cc-"):
        return uid
    if uid.startswith("gov-"):
        return _UID_PREFIX + uid[len("gov-"):]
    return _UID_PREFIX + uid


# ---------------------------------------------------------------------------
# Section splitting
# ---------------------------------------------------------------------------

_SECTION_RE = re.compile(r"^## (\d+)\.\s", re.MULTILINE)


def _split_sections(text: str) -> Tuple[str, Dict[int, str]]:
    """Split markdown into header (before ## 1) and numbered sections."""
    matches = list(_SECTION_RE.finditer(text))
    if not matches:
        return text, {}

    header = text[: matches[0].start()]
    sections: Dict[int, str] = {}
    for i, m in enumerate(matches):
        num = int(m.group(1))
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        sections[num] = text[start:end]
    return header, sections


# ---------------------------------------------------------------------------
# Header parsing
# ---------------------------------------------------------------------------

_UID_RE = re.compile(r"\*\*Dashboard UID\*\*:\s*`([^`]+)`")
_TITLE_RE = re.compile(r"\*\*Title\*\*:\s*(.+)")


def _parse_header(text: str) -> Tuple[str, str]:
    """Extract uid and title from header block."""
    uid_m = _UID_RE.search(text)
    title_m = _TITLE_RE.search(text)
    uid = uid_m.group(1).strip() if uid_m else ""
    title = title_m.group(1).strip() if title_m else ""
    if not uid:
        logger.warning("No Dashboard UID found in header")
    if not title:
        logger.warning("No Title found in header")
    return uid, title


def _extract_description(section1: str) -> str:
    """Extract dashboard description from Section 1 (Mission & Intent).

    Uses the Dashboard-Specific Question section's bold text as the
    description base, with the first paragraph of explanatory text appended.
    """
    # Find Dashboard-Specific Question bold line
    m = re.search(
        r"### Dashboard-Specific Question\s*\n+\*\*\"([^\"]+)\"\*\*",
        section1,
    )
    if not m:
        return ""

    question = m.group(1)

    # Get the explanatory paragraph after the question
    after = section1[m.end():]
    lines = []
    for line in after.split("\n"):
        stripped = line.strip()
        if not stripped:
            if lines:
                break
            continue
        if stripped.startswith("#") or stripped.startswith("|"):
            break
        lines.append(stripped)

    if lines:
        return question + " " + " ".join(lines)
    return question


# ---------------------------------------------------------------------------
# Grid position parser
# ---------------------------------------------------------------------------

_GRID_RE = re.compile(r"h=(\d+)\s+w=(\d+)\s+x=(\d+)\s+y=(\d+)")


def _parse_grid(s: str) -> GridPos:
    """Parse 'h=5 w=4 x=0 y=1' into GridPos."""
    m = _GRID_RE.search(s)
    if not m:
        raise ValueError(f"Cannot parse grid position: {s!r}")
    return GridPos(
        h=int(m.group(1)),
        w=int(m.group(2)),
        x=int(m.group(3)),
        y=int(m.group(4)),
    )


# ---------------------------------------------------------------------------
# Threshold parser
# ---------------------------------------------------------------------------

_THRESHOLD_STEP_RE = re.compile(r"(\S+?)\s*\(([^)]*)\)")


def _parse_thresholds(s: str) -> List[ThresholdStep]:
    """Parse 'red(null)→orange(0.15)→green(0.50)' into ThresholdStep list."""
    # Split on → or ->
    parts = re.split(r"→|->", s)
    steps = []
    for part in parts:
        part = part.strip()
        m = _THRESHOLD_STEP_RE.match(part)
        if not m:
            continue
        color = m.group(1)
        val_str = m.group(2).strip()
        if val_str in ("null", ""):
            value = None
        else:
            try:
                value = float(val_str)
            except ValueError:
                logger.warning("Non-numeric threshold value %r for color %r, skipping step", val_str, color)
                continue
        steps.append(ThresholdStep(value=value, color=color))
    return steps


# ---------------------------------------------------------------------------
# Field config parser
# ---------------------------------------------------------------------------

def _parse_legend_shorthand(s: str) -> Dict[str, Any]:
    """Parse legend shorthand 'table+right with value+percent' into structured dict.

    Returns e.g.:
        {"displayMode": "table", "placement": "right", "calcs": ["value", "percent"]}
    """
    legend: Dict[str, Any] = {}
    # Parse 'table+right' or 'table + right'
    mode_match = re.match(r"(\w+)\s*\+\s*(\w+)", s)
    if mode_match:
        legend["displayMode"] = mode_match.group(1)
        legend["placement"] = mode_match.group(2)

    # Parse 'with value+percent' or 'with value + percent'
    calcs_match = re.search(r"with\s+(.+)", s)
    if calcs_match:
        calcs_str = calcs_match.group(1)
        calcs = [c.strip() for c in re.split(r"\s*\+\s*", calcs_str)]
        legend["calcs"] = calcs

    return legend


def _parse_field_config(s: str) -> Dict[str, Any]:
    """Parse field config string into structured dict.

    Input examples::

        'unit=currencyUSD, decimals=0, threshold=blue(null)'
        'unit=percentunit, decimals=1, min=0, max=1, thresholds: red(null)→orange(0.15)→green(0.50)'
        'unit=currencyUSD, decimals=0, horizontal, palette-classic, barWidth=0.7'

    Returns:
        Dict with optional keys:
        - ``unit`` (str): Grafana unit string, or ``""`` for unit=none.
        - ``fieldConfig`` (dict): ``{"defaults": {"decimals": int, "min": float, ...}}``.
        - ``thresholds`` (list): ``[ThresholdStep, ...]`` parsed from threshold chain.
        - ``options`` (dict): Panel options — orientation, barWidth, pieType, legend, etc.
    """
    result: Dict[str, Any] = {}

    # Extract thresholds first (they may contain commas inside parens)
    thresholds: List[ThresholdStep] = []

    # Match 'threshold=color(val)' or 'thresholds: chain'
    # Handle the full threshold chain that may span to end of string
    threshold_match = re.search(
        r"threshold[s]?\s*[:=]\s*(.+?)(?=,\s*[a-zA-Z_]+[=:]|\s*$)", s
    )
    if threshold_match:
        thresh_str = threshold_match.group(1).strip()
        thresholds = _parse_thresholds(thresh_str)
        # Remove threshold portion from s for remaining parsing
        s_clean = s[: threshold_match.start()] + s[threshold_match.end():]
    else:
        s_clean = s

    if thresholds:
        result["thresholds"] = thresholds

    # Split remaining on ', ' for key=value pairs
    field_config: Dict[str, Any] = {}
    options: Dict[str, Any] = {}

    parts = [p.strip() for p in s_clean.split(",") if p.strip()]
    for part in parts:
        if "=" in part:
            key, val = part.split("=", 1)
            key = key.strip()
            val = val.strip()

            if key == "unit":
                # unit=none means no unit, not the literal string "none"
                result["unit"] = "" if val.lower() == "none" else val
            elif key == "decimals":
                try:
                    field_config.setdefault("defaults", {})["decimals"] = int(val)
                except ValueError:
                    logger.warning("Non-numeric decimals value: %r", val)
            elif key == "min":
                try:
                    field_config.setdefault("defaults", {})["min"] = float(val)
                except ValueError:
                    logger.warning("Non-numeric min value: %r", val)
            elif key == "max":
                try:
                    field_config.setdefault("defaults", {})["max"] = float(val)
                except ValueError:
                    logger.warning("Non-numeric max value: %r", val)
            elif key == "barWidth":
                try:
                    options["barWidth"] = float(val)
                except ValueError:
                    logger.warning("Non-numeric barWidth value: %r", val)
            elif key == "color":
                field_config.setdefault("defaults", {})["color"] = {
                    "mode": "fixed",
                    "fixedColor": val,
                }
            elif key == "graphMode":
                options["graphMode"] = val
            elif key == "legend":
                # Parse 'table+right with value+percent' → structured legend
                legend = _parse_legend_shorthand(val)
                if legend:
                    options["legend"] = legend
            elif key == "pieType":
                options["pieType"] = val
            else:
                logger.debug("Unrecognized field config key: %s=%s", key, val)
                options[key] = val
        else:
            # Standalone keywords
            part_lower = part.strip().lower()
            if part_lower == "horizontal":
                options["orientation"] = "horizontal"
            elif part_lower == "palette-classic":
                pass  # default Grafana behavior, no explicit config needed
            elif part_lower:
                logger.debug("Unrecognized field config keyword: %r", part)

    if field_config:
        result["fieldConfig"] = field_config
    if options:
        result["options"] = options

    return result


# ---------------------------------------------------------------------------
# PromQL parser
# ---------------------------------------------------------------------------

_MULTI_TARGET_RE = re.compile(r"\*\*PromQL\*\*\s*\((\d+)\s+targets?\)", re.IGNORECASE)
_SINGLE_PROMQL_RE = re.compile(r"\*\*PromQL\*\*\s*:\s*`([^`]+)`")
_TARGET_LINE_RE = re.compile(
    r"-\s+\*\*([A-Z])\*\*\s*:\s*`([^`]+)`(?:\s*→\s*(.+))?"
)


def _parse_promql(block: str) -> Tuple[Optional[str], Optional[List[Dict[str, Any]]]]:
    """Parse PromQL from a panel block.

    Returns (expr, targets) where:
    - Single target: (expr_string, None)
    - Multi target: (None, [target_dicts])
    """
    # Check for multi-target first
    multi_m = _MULTI_TARGET_RE.search(block)
    if multi_m:
        # Find all target lines after this match
        after = block[multi_m.end():]
        targets = []
        for tm in _TARGET_LINE_RE.finditer(after):
            ref_id = tm.group(1)
            expr = tm.group(2)
            legend = tm.group(3).strip().strip('"').strip("'") if tm.group(3) else ""
            targets.append({
                "refId": ref_id,
                "expr": expr,
                "legendFormat": legend,
            })
        if targets:
            return None, targets

    # Single target
    single_m = _SINGLE_PROMQL_RE.search(block)
    if single_m:
        return single_m.group(1), None

    return None, None


# ---------------------------------------------------------------------------
# Transformation parser
# ---------------------------------------------------------------------------

def _split_transform_chain(s: str) -> List[str]:
    """Split chained transforms on → but only outside parentheses.

    'joinByField (a, b) → organize (c → d) → sortBy (X, desc)'
    → ['joinByField (a, b)', 'organize (c → d)', 'sortBy (X, desc)']
    """
    parts = []
    depth = 0
    current: List[str] = []
    i = 0
    while i < len(s):
        ch = s[i]
        if ch == "(":
            depth += 1
            current.append(ch)
        elif ch == ")":
            depth = max(0, depth - 1)
            current.append(ch)
        elif depth == 0 and (s[i:i+1] == "→" or s[i:i+2] == "->"):
            parts.append("".join(current).strip())
            current = []
            i += 1 if s[i] == "→" else 2
            continue
        else:
            current.append(ch)
        i += 1
    tail = "".join(current).strip()
    if tail:
        parts.append(tail)
    return parts


_TRANSFORM_RE = re.compile(r"(\w+)\s*\((.+)\)\s*$", re.DOTALL)


def _parse_transformations(s: str) -> List[TransformSpec]:
    """Parse transformation string into TransformSpec list.

    Input: 'sortBy (Value, desc)' or chained 'joinByField (...) → organize (...) → sortBy (...)'
    """
    parts = _split_transform_chain(s)
    transforms = []
    for part in parts:
        part = part.strip()
        if not part or part.lower() == "none":
            continue
        m = _TRANSFORM_RE.match(part)
        if not m:
            logger.warning("Unparseable transformation: %r", part)
            continue

        tid = m.group(1)
        opts_str = m.group(2).strip()

        if tid == "sortBy":
            # Parse 'Value, desc' or 'GF/GP, desc'
            sort_parts = [p.strip() for p in opts_str.split(",")]
            field = sort_parts[0] if sort_parts else "Value"
            desc = len(sort_parts) > 1 and sort_parts[1].lower() == "desc"
            transforms.append(TransformSpec(
                id="sortBy",
                options={"sort": [{"field": field, "desc": desc}]},
            ))
        else:
            # Complex transforms — store raw description
            logger.warning(
                "Complex transformation '%s' stored as raw description: %r",
                tid, opts_str,
            )
            transforms.append(TransformSpec(id=tid, options={"_raw": opts_str}))

    return transforms


# ---------------------------------------------------------------------------
# Data link parser
# ---------------------------------------------------------------------------

_DATA_LINK_RE = re.compile(
    r"Click\s*→\s*`?([^`\s]+)`?\s+with\s+(.+)", re.IGNORECASE
)


def _parse_data_link(s: str) -> Optional[DataLink]:
    """Parse data link prose into DataLink.

    Input: 'Click → gov-michigan-dept-detail with var-department=${__field.labels.department}, includeVars: true, keepTime: true'
    """
    m = _DATA_LINK_RE.search(s)
    if not m:
        return None

    target_uid = m.group(1).strip()
    params_str = m.group(2).strip()

    # Extract var- params
    var_params = re.findall(r"(var-\w+)=([^,]+)", params_str)
    url_parts = [f"/d/{target_uid}"]
    query_parts = []
    for var_name, var_value in var_params:
        query_parts.append(f"{var_name}={var_value.strip().strip('`')}")

    # Always append time range and variables macros
    query_parts.append("${__url_time_range}")
    query_parts.append("${__all_variables}")

    url = url_parts[0]
    if query_parts:
        url += "?" + "&".join(query_parts)

    return DataLink(title="View Department Detail", url=url)


# ---------------------------------------------------------------------------
# Content block parser
# ---------------------------------------------------------------------------


def _parse_content_block(lines: List[str], start_idx: int) -> str:
    """Extract multi-line markdown content block starting after '- **Content**:'.

    Captures lines until the next field bullet (- **) or next panel header (####).
    """
    content_lines = []
    i = start_idx
    while i < len(lines):
        line = lines[i]
        # Stop at next field bullet or panel/row header
        if re.match(r"^- \*\*\w", line) or line.startswith("####") or line.startswith("### "):
            break
        content_lines.append(line)
        i += 1

    # Strip leading/trailing blank lines, preserve internal structure
    text = "\n".join(content_lines)
    return text.strip() + "\n"


# ---------------------------------------------------------------------------
# Color override parser
# ---------------------------------------------------------------------------


def _parse_color_overrides(block: str) -> List[Dict[str, Any]]:
    """Parse color override lines into Grafana override format.

    Input lines like:
      - General Fund/General Purpose → green
      - Federal → blue
    """
    overrides = []
    override_section = False
    for line in block.split("\n"):
        if "**Color overrides**" in line:
            override_section = True
            continue
        if override_section:
            # Stop at next field bullet
            if re.match(r"^- \*\*\w", line):
                break
            m = re.match(r"\s*-\s+(.+?)\s*→\s*(\S+)", line)
            if m:
                name = m.group(1).strip()
                color = m.group(2).strip()
                overrides.append({
                    "matcher": {"id": "byName", "options": name},
                    "properties": [
                        {"id": "color", "value": {"mode": "fixed", "fixedColor": color}},
                    ],
                })
    return overrides


# ---------------------------------------------------------------------------
# Row→Panel grouping
# ---------------------------------------------------------------------------

_ROW_HEADER_RE = re.compile(r"^### Row \d+:\s*(.+?)\s*\(y=(\d+)\)", re.MULTILINE)
_PANEL_HEADER_RE = re.compile(r"^#### Panel \d+:\s*(.+)", re.MULTILINE)


def _split_row_groups(
    section4: str,
) -> List[Tuple[str, int, str]]:
    """Split Section 4 into row groups: (row_title, y, panel_blocks_text)."""
    matches = list(_ROW_HEADER_RE.finditer(section4))
    if not matches:
        return []

    groups = []
    for i, m in enumerate(matches):
        title = m.group(1).strip()
        y = int(m.group(2))
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(section4)
        groups.append((title, y, section4[start:end]))
    return groups


# ---------------------------------------------------------------------------
# Per-panel parsing
# ---------------------------------------------------------------------------


def _parse_single_panel(block: str, row_title: str) -> Optional[PanelSpec]:
    """Parse a single ``#### Panel N: Title`` block into a PanelSpec.

    Extracts field bullets (``- **Key**: Value``) from the block, then
    dispatches to type-specific handling: row panels get collapsed flag,
    text panels get content blocks, and metric panels get PromQL targets,
    field config, transformations, data links, and color overrides.

    Returns None (with a warning log) if the panel type is unrecognized.
    """
    lines = block.split("\n")

    # Extract panel title from header
    title_m = _PANEL_HEADER_RE.match(lines[0])
    if not title_m:
        return None
    panel_title = title_m.group(1).strip()

    # Parse field bullets
    fields: Dict[str, str] = {}
    content_text: Optional[str] = None
    i = 1
    while i < len(lines):
        line = lines[i]
        # Field bullet: - **Key**: Value
        fm = re.match(r"^- \*\*(\w[\w\s]*?)\*\*\s*:\s*(.*)", line)
        if fm:
            key = fm.group(1).strip()
            val = fm.group(2).strip()
            if key == "Content":
                # Multi-line content block
                if val:
                    # Inline content on same line
                    content_text = val + "\n"
                    i += 1
                    # Collect continuation lines
                    content_text += _parse_content_block(lines, i)
                else:
                    i += 1
                    content_text = _parse_content_block(lines, i)
                # Skip past content block
                while i < len(lines):
                    cline = lines[i]
                    if re.match(r"^- \*\*\w", cline) or cline.startswith("####"):
                        break
                    i += 1
                continue
            else:
                fields[key] = val
        i += 1

    # Determine type
    type_str = fields.get("Type", "").lower().strip()
    try:
        panel_type = PanelType(type_str)
    except ValueError:
        logger.warning("Unknown panel type %r for panel %r", type_str, panel_title)
        return None

    # Build panel kwargs
    kwargs: Dict[str, Any] = {
        "type": panel_type,
        "title": panel_title,
    }

    # Grid
    grid_str = fields.get("Grid", "")
    if grid_str:
        try:
            kwargs["gridPos"] = _parse_grid(grid_str)
        except ValueError:
            logger.warning("Malformed gridPos %r for panel %r, skipping grid", grid_str, panel_title)

    # Description
    desc = fields.get("Description", "").strip().strip('"')
    if desc:
        kwargs["description"] = desc

    # Collapsed (for row panels)
    if panel_type == PanelType.ROW:
        collapsed = fields.get("Collapsed", "false").strip().lower()
        if collapsed == "true":
            kwargs.setdefault("options", {})["collapsed"] = True
        return PanelSpec(**kwargs)

    # Content (for text panels)
    if panel_type == PanelType.TEXT:
        if content_text:
            kwargs["options"] = {"content": content_text}
        return PanelSpec(**kwargs)

    # Field config
    fc_str = fields.get("Field config", "")
    if fc_str:
        fc_parsed = _parse_field_config(fc_str)
        if "unit" in fc_parsed:
            kwargs["unit"] = fc_parsed["unit"]
        if "thresholds" in fc_parsed:
            kwargs["thresholds"] = fc_parsed["thresholds"]
        if "fieldConfig" in fc_parsed:
            kwargs["fieldConfig"] = fc_parsed["fieldConfig"]
        if "options" in fc_parsed:
            kwargs.setdefault("options", {}).update(fc_parsed["options"])

    # PromQL
    is_instant = fields.get("instant", "").strip().lower() == "true"
    fmt_raw = fields.get("format", "").strip()
    # Clean format: 'table (all 6 targets)' → 'table'
    fmt = fmt_raw.split("(")[0].strip() if fmt_raw else ""

    expr, multi_targets = _parse_promql(block)

    if multi_targets:
        targets = []
        for t in multi_targets:
            target = TargetSpec(
                expr=t["expr"],
                legendFormat=t.get("legendFormat", ""),
                refId=t.get("refId"),
                instant=is_instant,
            )
            if fmt:
                target = target.model_copy(update={"format": fmt})
            targets.append(target)
        kwargs["targets"] = targets
    elif expr:
        kwargs["targets"] = [
            TargetSpec(
                expr=expr,
                instant=is_instant,
                refId="A",
                format=fmt if fmt else None,
            )
        ]

    # Transformations
    trans_str = fields.get("Transformations", "")
    if trans_str and trans_str.strip().lower() != "none":
        kwargs["transformations"] = _parse_transformations(trans_str)

    # Data link
    data_link_str = fields.get("Data link", "")
    if data_link_str:
        dl = _parse_data_link(data_link_str)
        if dl:
            kwargs["dataLinks"] = [dl]

    # Color overrides
    overrides = _parse_color_overrides(block)
    if overrides:
        kwargs["overrides"] = overrides

    return PanelSpec(**kwargs)


# ---------------------------------------------------------------------------
# Parse all panels from Section 4
# ---------------------------------------------------------------------------


def _parse_panels(section4: str) -> List[PanelSpec]:
    """Parse all panels from Section 4, ordered by row groups."""
    row_groups = _split_row_groups(section4)
    panels: List[PanelSpec] = []

    for row_title, row_y, group_text in row_groups:
        # Split into individual panel blocks
        panel_matches = list(_PANEL_HEADER_RE.finditer(group_text))
        if not panel_matches:
            continue

        row_panels: List[PanelSpec] = []
        content_panels: List[PanelSpec] = []

        for i, pm in enumerate(panel_matches):
            start = pm.start()
            end = (
                panel_matches[i + 1].start()
                if i + 1 < len(panel_matches)
                else len(group_text)
            )
            block = group_text[start:end]
            panel = _parse_single_panel(block, row_title)
            if panel is None:
                # Extract panel header for diagnostic logging
                header_line = block.split("\n", 1)[0] if block else "<empty>"
                logger.warning("Skipped unparseable panel in row %r: %s", row_title, header_line)
                continue

            if panel.type == PanelType.ROW:
                # Strip "(Row)" suffix from panel title for cleaner display.
                # The panel title (e.g., "Welcome (Row)" → "Welcome") is the
                # canonical row name for the YAML spec.
                clean_title = re.sub(r"\s*\(Row\)\s*$", "", panel.title)
                panel = panel.model_copy(update={"title": clean_title})
                row_panels.append(panel)
            else:
                content_panels.append(panel)

        # Sort content panels by (y, x) for consistent layout
        content_panels.sort(
            key=lambda p: (
                p.gridPos.y if p.gridPos else 0,
                p.gridPos.x if p.gridPos else 0,
            )
        )

        # Validate: content panel y > row y
        for cp in content_panels:
            if cp.gridPos and cp.gridPos.y <= row_y:
                logger.warning(
                    "Panel %r has gridPos.y=%d <= row y=%d",
                    cp.title, cp.gridPos.y, row_y,
                )

        # Emit: row panel first, then content panels
        panels.extend(row_panels)
        panels.extend(content_panels)

    return panels


# ---------------------------------------------------------------------------
# Variable table parser
# ---------------------------------------------------------------------------

_VAR_HEADER_RE = re.compile(r"^### `(\w+)`", re.MULTILINE)

_VARIABLE_TYPE_MAP = {
    "custom": VariableType.CUSTOM,
    "prometheusdatasource": VariableType.PROMETHEUS_DATASOURCE,
    "constant": VariableType.CONSTANT,
}


def _extract_query_from_table(block: str) -> Optional[str]:
    """Extract a query string from a Slug/Display Name table in the variable block.

    Handles tables like:
        | Slug | Display Name |
        |------|-------------|
        | `corrections` | Corrections |
        | `education` | Education |

    Produces: 'Corrections : corrections,Education : education,...'
    (Grafana custom variable 'key : value' format)
    """
    entries: List[str] = []
    in_slug_table = False
    for line in block.split("\n"):
        if not line.strip().startswith("|"):
            if in_slug_table and entries:
                break  # End of table
            continue

        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 2:
            continue

        # Detect the Slug | Display Name header row (skip Property tables)
        first_lower = cells[0].lower().strip()
        if first_lower == "slug":
            in_slug_table = True
            continue

        # Skip separator rows
        if cells[0].startswith("-"):
            continue

        if in_slug_table:
            slug = cells[0].strip("`").strip()
            display = cells[1].strip()
            if slug and display and not slug.startswith("*"):
                entries.append(f"{display} : {slug}")

    return ",".join(entries) if entries else None


def _parse_variable_table(block: str, var_name: str) -> VariableSpec:
    """Parse a single variable's property table into VariableSpec."""
    props: Dict[str, str] = {}
    for line in block.split("\n"):
        m = re.match(r"\|\s*\*\*(\w+)\*\*\s*\|\s*(.+?)\s*\|", line)
        if m:
            props[m.group(1).lower()] = m.group(2).strip()

    # Type mapping
    raw_type = props.get("type", "custom").strip("`").lower()
    var_type = _VARIABLE_TYPE_MAP.get(raw_type, VariableType.CUSTOM)

    kwargs: Dict[str, Any] = {
        "type": var_type,
        "name": props.get("name", var_name).strip("`"),
        "label": props.get("label", "").strip("`"),
    }

    # Query — may be a literal value or a reference to a table below
    query = props.get("query", "")
    if query and query != "—":
        query_clean = query.strip("`")
        if "entries in" in query_clean and "format" in query_clean:
            # Query references a separate table — extract from the block
            extracted = _extract_query_from_table(block)
            if extracted:
                kwargs["query"] = extracted
            else:
                kwargs["query"] = query_clean
        else:
            kwargs["query"] = query_clean

    # Boolean fields
    for bool_field in ("multi", "includeAll", "skipUrlSync"):
        val = props.get(bool_field.lower(), "")
        if val:
            kwargs[bool_field] = val.strip("`").lower() == "true"

    # allValue
    all_val = props.get("allvalue", "")
    if all_val and all_val != "—":
        kwargs["allValue"] = all_val.strip("`")

    # default
    default = props.get("default", "")
    if default and default != "—":
        # Clean up special values: strip backticks and handle 'All ($__all)' → 'All'
        default_clean = re.sub(r"`", "", default)
        default_clean = re.sub(r"\s*\(\$__all\)", "", default_clean).strip()
        kwargs["default"] = default_clean

    # hide
    hide = props.get("hide", "0").strip("`")
    try:
        kwargs["hide"] = int(hide)
    except ValueError:
        logger.warning("Non-numeric hide value %r for variable %r, defaulting to 0", hide, var_name)
        kwargs["hide"] = 0

    return VariableSpec(**kwargs)


def _parse_variables(section6: str) -> List[VariableSpec]:
    """Parse all variables from Section 6."""
    variables: List[VariableSpec] = []

    # Always prepend prometheusDatasource
    variables.append(
        VariableSpec(
            type=VariableType.PROMETHEUS_DATASOURCE,
            name="datasource",
            label="Data Source",
            hide=0,
        )
    )

    # Find each variable subsection
    matches = list(_VAR_HEADER_RE.finditer(section6))
    for i, m in enumerate(matches):
        var_name = m.group(1)
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(section6)
        block = section6[start:end]
        variables.append(_parse_variable_table(block, var_name))

    return variables


# ---------------------------------------------------------------------------
# Link table parser
# ---------------------------------------------------------------------------


def _parse_links(section7: str) -> List[DashboardLink]:
    """Parse dashboard-level navigation links from Section 7.

    Handles tables with varying column counts:
      | Link | Target UID | includeVars | keepTime | targetBlank | Icon |  (6 cols)
      | Link | Target UID | includeVars | keepTime | Icon |              (5 cols)
    """
    links: List[DashboardLink] = []

    # Find the Dashboard-Level Navigation Links table header row
    table_match = re.search(
        r"Dashboard-Level Navigation Links\s*\n+\|([^\n]+)\|\s*\n\|[-|\s]+\|\s*\n",
        section7,
    )
    if not table_match:
        return links

    # Detect column layout from header
    header_cells = [
        c.strip().strip("`").lower()
        for c in table_match.group(1).split("|")
    ]
    has_target_blank = any("targetblank" in c for c in header_cells)

    # Parse table rows after header
    after = section7[table_match.end():]
    for line in after.split("\n"):
        if not line.strip().startswith("|"):
            break
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 4:
            continue

        link_title = cells[0].strip()
        target_uid = cells[1].strip().strip("`")
        include_vars = cells[2].strip().strip("`").lower() == "true"
        keep_time = cells[3].strip().strip("`").lower() == "true"

        if has_target_blank and len(cells) >= 6:
            target_blank = cells[4].strip().strip("`").lower() == "true"
            icon = cells[5].strip().strip("`")
        elif len(cells) >= 5:
            target_blank = False
            icon = cells[4].strip().strip("`")
        else:
            target_blank = False
            icon = "arrow-right"

        url = f"/d/{target_uid}"

        links.append(
            DashboardLink(
                title=link_title,
                url=url,
                icon=icon,
                targetBlank=target_blank,
                includeVars=include_vars,
                keepTime=keep_time,
            )
        )

    return links


# ---------------------------------------------------------------------------
# Auto-generate tags
# ---------------------------------------------------------------------------


def _auto_tags(uid: str) -> List[str]:
    """Generate tags from UID: ['government', 'budget', 'michigan', '<type>']."""
    tags = ["government", "budget", "michigan"]
    # Extract type hint from UID
    parts = uid.replace("gov-michigan-", "").replace("cc-govbudget-michigan-", "").split("-")
    if parts:
        # Use first meaningful part as dashboard type tag
        type_tag = parts[0]
        if type_tag and type_tag not in tags:
            tags.append(type_tag)
    return tags


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def parse_requirements(path: str | Path) -> DashboardSpec:
    """Parse a requirements markdown document into a DashboardSpec.

    Args:
        path: Path to the requirements markdown file.

    Returns:
        DashboardSpec ready for YAML serialization or workflow processing.

    Raises:
        ConfigurationError: If the file does not exist or cannot be read.
    """
    path = Path(path)
    if not path.is_file():
        raise ConfigurationError(f"Requirements file not found: {path}")
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ConfigurationError(
            f"Cannot read {path}: encoding error ({exc.reason})"
        ) from exc

    logger.info("Parsing requirements from %s", path)
    header, sections = _split_sections(text)
    logger.debug("Found %d numbered sections", len(sections))

    # Header extraction
    uid, title = _parse_header(header)
    transformed_uid = _uid_transform(uid)

    # Description from Section 1
    description = _extract_description(sections.get(1, ""))

    # Tags
    tags = _auto_tags(uid)

    # Panels from Section 4
    panels = _parse_panels(sections.get(4, ""))
    logger.info(
        "Parsed %d panels, %d sections from %s",
        len(panels), len(sections), path.name,
    )

    # Variables from Section 6
    variables = _parse_variables(sections.get(6, ""))

    # Links from Section 7
    links = _parse_links(sections.get(7, ""))

    return DashboardSpec(
        title=title,
        uid=transformed_uid,
        description=description,
        tags=tags,
        panels=panels,
        variables=variables,
        links=links,
    )


def requirements_to_yaml(path: str | Path) -> str:
    """Parse requirements and return YAML string.

    Args:
        path: Path to the requirements markdown file.

    Returns:
        YAML string suitable for writing to a .spec.yaml file.
    """
    spec = parse_requirements(path)
    data = _spec_to_dict(spec)
    return yaml.dump(data, default_flow_style=False, allow_unicode=True, sort_keys=False)


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------


def _spec_to_dict(spec: DashboardSpec) -> Dict[str, Any]:
    """Convert DashboardSpec to an ordered dict for YAML serialization."""
    d: Dict[str, Any] = {
        "title": spec.title,
    }
    if spec.uid:
        d["uid"] = spec.uid
    if spec.description:
        d["description"] = spec.description
    if spec.tags:
        d["tags"] = spec.tags

    # Links
    if spec.links:
        d["links"] = [_link_to_dict(link) for link in spec.links]

    # Variables
    if spec.variables:
        d["variables"] = [_variable_to_dict(v) for v in spec.variables]

    # Panels
    d["panels"] = [_panel_to_dict(p) for p in spec.panels]

    return d


def _link_to_dict(link: DashboardLink) -> Dict[str, Any]:
    """Serialize DashboardLink for YAML output."""
    d: Dict[str, Any] = {"title": link.title}
    if link.url:
        d["url"] = link.url
    d["icon"] = link.icon
    if link.tooltip:
        d["tooltip"] = link.tooltip
    d["targetBlank"] = link.targetBlank
    if link.includeVars:
        d["includeVars"] = True
    if link.keepTime:
        d["keepTime"] = True
    return d


def _variable_to_dict(v: VariableSpec) -> Dict[str, Any]:
    """Serialize VariableSpec for YAML output."""
    d: Dict[str, Any] = {
        "type": v.type.value,
        "name": v.name,
        "label": v.label,
    }
    if v.query:
        d["query"] = v.query
    if v.type == VariableType.CUSTOM:
        d["multi"] = v.multi
        d["includeAll"] = v.includeAll
    if v.allValue is not None:
        d["allValue"] = v.allValue
    if v.default:
        d["default"] = v.default
    d["hide"] = v.hide
    if v.type == VariableType.CUSTOM:
        d["skipUrlSync"] = v.skipUrlSync
    return d


def _panel_to_dict(p: PanelSpec) -> Dict[str, Any]:
    """Serialize PanelSpec for YAML output."""
    d: Dict[str, Any] = {
        "type": p.type.value,
        "title": p.title,
    }

    if p.gridPos:
        d["gridPos"] = {
            "h": p.gridPos.h,
            "w": p.gridPos.w,
            "x": p.gridPos.x,
            "y": p.gridPos.y,
        }

    if p.description:
        d["description"] = p.description

    # Targets
    if p.targets:
        d["targets"] = []
        for t in p.targets:
            td: Dict[str, Any] = {}
            if t.expr:
                td["expr"] = t.expr
            if t.instant:
                td["instant"] = True
            if t.format:
                td["format"] = t.format
            if t.refId:
                td["refId"] = t.refId
            if t.legendFormat:
                td["legendFormat"] = t.legendFormat
            d["targets"].append(td)

    # Unit
    if p.unit:
        d["unit"] = p.unit

    # Field config
    if p.fieldConfig:
        d["fieldConfig"] = p.fieldConfig

    # Thresholds
    if p.thresholds:
        d["thresholds"] = [
            {"value": t.value, "color": t.color} for t in p.thresholds
        ]

    # Options
    if p.options:
        d["options"] = p.options

    # Overrides
    if p.overrides:
        d["overrides"] = p.overrides

    # Transformations
    if p.transformations:
        d["transformations"] = [
            {"id": t.id, "options": t.options} for t in p.transformations
        ]

    # Data links
    if p.dataLinks:
        d["dataLinks"] = [
            {"title": dl.title, "url": dl.url} for dl in p.dataLinks
        ]

    return d
