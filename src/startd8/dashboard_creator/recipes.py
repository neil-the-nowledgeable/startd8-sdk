"""Panel recipe library (REQ-DCR-RCP) — named, reusable bundles of corpus-mode
``fieldConfig`` / ``options`` defaults a ``PanelSpec`` can reference by id.

A recipe is the *middle* layer of the three-layer styling model:
**constructor baseline (mixin) < recipe (here) < spec explicit values**.
Hydration merges a recipe *under* the panel's explicit values (spec wins) and the
result rides the existing Jsonnet merge block on top of the constructor defaults —
so recipes need no Jsonnet changes. Seed values are the corpus modes documented in
``docs/design/dashboard_creator/DASHBOARD_AESTHETIC_DEFAULTS.md``.
"""

from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field, field_validator

from startd8.dashboard_creator.models import PanelSpec, PanelType, TransformSpec

# Panel types that have a constructor (RCP-004 gate). Mirrors validation.PANEL_CONSTRUCTORS
# but derived locally to avoid an import cycle (validation imports nothing from here).
_SUPPORTED_TYPES = frozenset(pt for pt in PanelType)


class PanelRecipe(BaseModel):
    """A named bundle of panel finish defaults (REQ-DCR-RCP-001/002)."""

    id: str  # "<archetype>.<variant>", e.g. "stat.kpi"
    applies_to: List[PanelType]
    summary: str = ""
    unit: Optional[str] = None
    field_config: Dict[str, Any] = Field(default_factory=dict)  # merged into fieldConfig
    options: Dict[str, Any] = Field(default_factory=dict)  # merged into panel options
    transformations: List[TransformSpec] = Field(default_factory=list)
    source_exemplar_uid: Optional[str] = None  # play.grafana.org uid (provenance)
    source_url: Optional[str] = None

    @field_validator("id")
    @classmethod
    def _id_shape(cls, v: str) -> str:
        import re

        if not re.fullmatch(r"[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*", v):
            raise ValueError(f"recipe id must be '<archetype>.<variant>', got {v!r}")
        return v


# ---------------------------------------------------------------------------
# Seed recipes (REQ-DCR-RCP-003) — corpus-mode finish for supported panel types.
# ---------------------------------------------------------------------------

_SEED: List[PanelRecipe] = [
    PanelRecipe(
        id="stat.kpi", applies_to=[PanelType.STAT], unit="short",
        summary="Single current-value KPI tile.",
        options={"colorMode": "value", "graphMode": "area", "textMode": "auto",
                 "reduceOptions": {"calcs": ["lastNotNull"]}},
    ),
    PanelRecipe(
        id="stat.headline", applies_to=[PanelType.STAT],
        summary="Status/section headline tile (colored background).",
        options={"colorMode": "background", "graphMode": "none",
                 "textMode": "value_and_name", "reduceOptions": {"calcs": ["lastNotNull"]}},
    ),
    PanelRecipe(
        id="gauge.threshold", applies_to=[PanelType.GAUGE],
        summary="Gauge with a two-step green/danger actionable range.",
        field_config={"defaults": {"thresholds": {"mode": "absolute", "steps": [
            {"color": "green", "value": None}, {"color": "red", "value": 80}]}}},
    ),
    PanelRecipe(
        id="bargauge.lcd", applies_to=[PanelType.BAR_GAUGE],
        summary="Vertical LCD bar gauge.",
        options={"displayMode": "lcd", "orientation": "vertical", "valueMode": "color"},
    ),
    PanelRecipe(
        id="bargauge.basic", applies_to=[PanelType.BAR_GAUGE],
        summary="Horizontal basic bar gauge (quick scan).",
        options={"displayMode": "basic", "orientation": "horizontal", "valueMode": "color"},
    ),
    PanelRecipe(
        id="piechart.composition", applies_to=[PanelType.PIECHART],
        summary="Donut composition with percent labels and a table legend.",
        options={"pieType": "donut", "displayLabels": ["percent"],
                 "legend": {"displayMode": "table", "placement": "bottom",
                            "values": ["percent", "value"]}},
    ),
    PanelRecipe(
        id="timeseries.observability", applies_to=[PanelType.TIMESERIES],
        summary="Observability line chart: table legend with calcs, multi tooltip.",
        options={"legend": {"displayMode": "table", "placement": "bottom",
                            "calcs": ["mean", "lastNotNull", "max"]},
                 "tooltip": {"mode": "multi", "sort": "desc"}},
    ),
    PanelRecipe(
        id="timeseries.stacked", applies_to=[PanelType.TIMESERIES],
        summary="Stacked area time series.",
        field_config={"defaults": {"custom": {
            "stacking": {"group": "A", "mode": "normal"}, "fillOpacity": 20}}},
    ),
    PanelRecipe(
        id="table.aggregation", applies_to=[PanelType.TABLE],
        summary="Compact filterable table for aggregated rows.",
        field_config={"defaults": {"custom": {"filterable": True, "align": "auto"}}},
        options={"cellHeight": "sm", "showHeader": True},
    ),
    PanelRecipe(
        id="table.ranking", applies_to=[PanelType.TABLE],
        summary="Ranking table with color-text cells.",
        field_config={"defaults": {"custom": {
            "cellOptions": {"type": "color-text"}, "filterable": True}}},
        options={"cellHeight": "sm", "showHeader": True},
    ),
    PanelRecipe(
        id="barchart.ranking", applies_to=[PanelType.BARCHART], unit="short",
        summary="Horizontal ranked bar chart.",
        options={"orientation": "horizontal", "showValue": "auto",
                 "legend": {"showLegend": False}},
    ),
    PanelRecipe(
        id="text.banner", applies_to=[PanelType.TEXT],
        summary="Full-width markdown banner/header.",
        options={"mode": "markdown"},
    ),
    # Phase 5 panel-type recipes ------------------------------------------
    PanelRecipe(
        id="canvas.display", applies_to=[PanelType.CANVAS],
        summary="Read-only display canvas (kiosk): no inline editing, no advanced types.",
        options={"inlineEditing": False, "showAdvancedTypes": False, "panZoom": False},
    ),
    PanelRecipe(
        id="canvas.editable", applies_to=[PanelType.CANVAS],
        summary="Authoring canvas: inline editing, advanced element types, pan/zoom.",
        options={"inlineEditing": True, "showAdvancedTypes": True, "panZoom": True},
    ),
    PanelRecipe(
        id="canvas.metric_card", applies_to=[PanelType.CANVAS],
        summary="Starter scaffold: a centered metric-value card — set the element's "
                "config.text.field to your metric.",
        options={"root": {
            "type": "frame",
            "placement": {"top": 0, "left": 0, "width": 100, "height": 100},
            "elements": [{
                "type": "metric-value",
                "name": "value",
                "placement": {"top": 20, "left": 10, "width": 80, "height": 50},
                "constraint": {"horizontal": "left", "vertical": "top"},
                "config": {
                    "align": "center", "valign": "middle", "size": 36,
                    "text": {"mode": "field", "field": ""},
                    "color": {"fixed": "#73BF69"},
                },
                "background": {"color": {"fixed": "transparent"}},
                "border": {"color": {"fixed": "dark-green"}, "width": 1},
            }],
        }},
    ),
    PanelRecipe(
        id="geomap.heatmap", applies_to=[PanelType.GEOMAP],
        summary="Density heatmap layer instead of point markers.",
        options={"layers": [{
            "type": "heatmap", "name": "Heatmap", "location": {"mode": "auto"},
            "config": {"radius": 25, "blur": 27, "weight": {"fixed": 1, "min": 0, "max": 1}},
        }]},
    ),
    PanelRecipe(
        id="heatmap.timeseries", applies_to=[PanelType.HEATMAP],
        summary="Bucket a time series into a heatmap (calculate from data).",
        options={"calculate": True,
                 "calculation": {"xBuckets": {"mode": "size"}, "yBuckets": {"mode": "count"}}},
    ),
    PanelRecipe(
        id="state_timeline.compact", applies_to=[PanelType.STATE_TIMELINE],
        summary="Dense status timeline: no inline values, thinner rows.",
        options={"showValue": "never", "rowHeight": 0.7},
    ),
    PanelRecipe(
        id="xychart.connected", applies_to=[PanelType.XYCHART],
        summary="Scatter with connecting lines.",
        field_config={"defaults": {"custom": {"show": "points+lines"}}},
    ),
    PanelRecipe(
        id="candlestick.ohlc", applies_to=[PanelType.CANDLESTICK],
        summary="OHLC bars instead of filled candles.",
        options={"candleStyle": "ohlcbars", "colorStrategy": "open-close"},
    ),
    PanelRecipe(
        id="candlestick.price", applies_to=[PanelType.CANDLESTICK],
        summary="Price-only candles (no volume pane).",
        options={"mode": "candles", "includeAllFields": False},
    ),
]

# RCP-004: refuse to register a recipe for a panel type with no constructor.
for _r in _SEED:
    for _t in _r.applies_to:
        if _t not in _SUPPORTED_TYPES:
            raise ValueError(
                f"recipe {_r.id!r} applies_to unsupported panel type {_t!r}"
            )

RECIPE_REGISTRY: Dict[str, PanelRecipe] = {r.id: r for r in _SEED}


# ---------------------------------------------------------------------------
# Hydration (REQ-DCR-RCP-020..023)
# ---------------------------------------------------------------------------


def _deep_merge(base: Any, override: Any) -> Any:
    """Recursive merge: dicts deep-merge; lists and scalars are replaced wholesale
    by ``override`` (REQ-DCR-RCP-021/022). ``base`` is never mutated."""
    if isinstance(base, dict) and isinstance(override, dict):
        out = dict(base)
        for k, v in override.items():
            out[k] = _deep_merge(base[k], v) if k in base else v
        return out
    return override


def hydrate_panel(panel: PanelSpec) -> Tuple[PanelSpec, List[str]]:
    """Resolve ``panel.recipe`` and return an *effective* panel with the recipe
    merged **under** the panel's explicit values (spec wins), plus shadow warnings
    (REQ-DCR-RCP-020/032). A panel with no recipe — or an unknown recipe id, which
    validation rejects separately — is returned unchanged.
    """
    rid = getattr(panel, "recipe", None)
    if not rid:
        return panel, []
    recipe = RECIPE_REGISTRY.get(rid)
    if recipe is None:
        return panel, []  # RCP-030 surfaces the unknown id during validation

    warnings = [
        f"panel '{panel.title}': recipe '{recipe.id}' option '{k}' overridden by spec"
        for k in set(recipe.options) & set(panel.options or {})
    ]

    effective_fc = _deep_merge(recipe.field_config, panel.fieldConfig or {})
    effective_opts = _deep_merge(recipe.options, panel.options or {})
    effective_unit = panel.unit if panel.unit else (recipe.unit or "")  # RCP-023
    effective_tx = panel.transformations if panel.transformations else recipe.transformations  # RCP-022

    effective = panel.model_copy(update={
        "fieldConfig": effective_fc,
        "options": effective_opts,
        "unit": effective_unit,
        "transformations": effective_tx,
    })
    return effective, warnings
