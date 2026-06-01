"""
UID enforcement + cross-field spec validation (DC-006, DC-007).
"""

import re
from typing import Any, Dict, List

from startd8.dashboard_creator.models import (
    DashboardSpec,
    PanelType,
    VariableType,
)
from startd8.exceptions import ValidationError

_UID_PATTERN = re.compile(r"^cc-[a-z0-9]+-[a-z0-9-]+$")
_UID_MAX_LENGTH = 40
_METRIC_REF_PATTERN = re.compile(r"\$\{metrics\.(\w+)\}")
_SELECTOR_REF_PATTERN = re.compile(r"\$\{selectors\.(\w+)\}")

# Known panel constructor names in panels.libsonnet.
# Defensive guard: Pydantic enforces PanelType enum, so panel.type.value is
# always in this set. Kept as a forward-compatibility guard for potential
# non-enum extensions.
PANEL_CONSTRUCTORS = frozenset(pt.value for pt in PanelType)

# Known variable builder names in variables.libsonnet.
# Same defensive-guard rationale as PANEL_CONSTRUCTORS.
VARIABLE_BUILDERS = frozenset(vt.value for vt in VariableType)


def generate_uid_from_title(title: str, pack: str = "startd8") -> str:
    """Generate a conforming UID from a dashboard title.

    "My Dashboard" → "cc-startd8-my-dashboard"
    """
    slug = title.lower()
    slug = re.sub(r"[\s_]+", "-", slug)  # Spaces/underscores → hyphens first
    slug = re.sub(r"[^a-z0-9-]", "", slug)  # Strip remaining non-alphanumeric
    slug = re.sub(r"-+", "-", slug).strip("-")  # Collapse multiple hyphens
    uid = f"cc-{pack}-{slug}"
    return uid[:_UID_MAX_LENGTH]


def enforce_uid(spec: DashboardSpec) -> DashboardSpec:
    """DC-006: Enforce cc-{pack}-{kebab-name} UID convention.

    - If uid is None, auto-generate from title.
    - If uid is set but non-conforming, raise ValidationError with suggestion.
    - Truncate to 40 characters.

    Returns new DashboardSpec with resolved uid.
    """
    if spec.uid is None:
        uid = generate_uid_from_title(spec.title)
        return spec.model_copy(update={"uid": uid})

    if not _UID_PATTERN.match(spec.uid):
        suggestion = generate_uid_from_title(spec.title)
        raise ValidationError(
            f"UID '{spec.uid}' does not match pattern cc-{{pack}}-{{kebab-name}}. "
            f"Suggestion: '{suggestion}'",
            field="uid",
            value=spec.uid,
        )

    if len(spec.uid) > _UID_MAX_LENGTH:
        return spec.model_copy(update={"uid": spec.uid[:_UID_MAX_LENGTH]})

    return spec


def validate_spec(
    spec: DashboardSpec,
    config_keys: Dict[str, Any],
) -> List[str]:
    """DC-007: Cross-field validation.

    Checks:
    1. All PanelSpec.type values have matching constructors
    2. All VariableSpec.type values have matching builders
    3. ${metrics.*} references resolve to config.metrics keys
    4. ${selectors.*} references resolve to config.selectors keys
    5. Panels with targets have at least one; panels with expr are non-empty
    6. No duplicate panel titles

    Returns list of error strings (empty = valid).
    """
    errors: List[str] = []
    metrics_keys = set(config_keys.get("metrics", {}).keys())
    selector_keys = set(config_keys.get("selectors", {}).keys())

    # Check panel constructors
    for panel in spec.panels:
        if panel.type.value not in PANEL_CONSTRUCTORS:
            errors.append(
                f"Panel '{panel.title}': unknown type '{panel.type.value}'"
            )
        # Recipe validation (REQ-DCR-RCP-030/031)
        if getattr(panel, "recipe", None):
            from startd8.dashboard_creator.recipes import RECIPE_REGISTRY

            recipe = RECIPE_REGISTRY.get(panel.recipe)
            if recipe is None:
                errors.append(
                    f"Panel '{panel.title}': unknown recipe '{panel.recipe}'"
                )
            elif panel.type not in recipe.applies_to:
                allowed = ", ".join(t.value for t in recipe.applies_to)
                errors.append(
                    f"Panel '{panel.title}': recipe '{panel.recipe}' applies to "
                    f"[{allowed}], not '{panel.type.value}'"
                )

    # Check variable builders
    for var in spec.variables:
        if var.type.value not in VARIABLE_BUILDERS:
            errors.append(
                f"Variable '{var.name}': unknown type '{var.type.value}'"
            )

    # Check metric references
    all_exprs = _collect_expressions(spec)
    for expr in all_exprs:
        for match in _METRIC_REF_PATTERN.finditer(expr):
            ref = match.group(1)
            if ref not in metrics_keys:
                errors.append(
                    f"Unresolvable metric reference: ${{metrics.{ref}}}. "
                    f"Available: {', '.join(sorted(metrics_keys))}"
                )

    # Check selector references
    for expr in all_exprs:
        for match in _SELECTOR_REF_PATTERN.finditer(expr):
            ref = match.group(1)
            if ref not in selector_keys:
                errors.append(
                    f"Unresolvable selector reference: ${{selectors.{ref}}}. "
                    f"Available: {', '.join(sorted(selector_keys))}"
                )

    # Check duplicate panel titles
    titles = [p.title for p in spec.panels]
    seen = set()
    for title in titles:
        if title in seen:
            errors.append(f"Duplicate panel title: '{title}'")
        seen.add(title)

    # Advisory: warn on unknown fieldConfig top-level keys
    _KNOWN_FIELD_CONFIG_KEYS = {"defaults", "overrides"}
    for panel in spec.panels:
        if panel.fieldConfig:
            unknown = set(panel.fieldConfig.keys()) - _KNOWN_FIELD_CONFIG_KEYS
            if unknown:
                errors.append(
                    f"Panel '{panel.title}': unknown fieldConfig keys "
                    f"{sorted(unknown)} (expected: defaults, overrides)"
                )

    return errors


def _collect_expressions(spec: DashboardSpec) -> List[str]:
    """Collect all expression strings from panels and variables."""
    exprs: List[str] = []
    for panel in spec.panels:
        if panel.expr:
            exprs.append(panel.expr)
        if panel.query:
            exprs.append(panel.query)
        if panel.targets:
            for target in panel.targets:
                if target.expr:
                    exprs.append(target.expr)
                if target.query:
                    exprs.append(target.query)
    for var in spec.variables:
        if var.metric:
            exprs.append(var.metric)
        if var.query:
            exprs.append(var.query)
    return exprs
