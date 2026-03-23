"""Verify YAML templates and fallback strings stay in sync (R0-4).

This test prevents the fragmentation that caused 19 mismatches between
YAML and fallback templates. Every YAML template must have a fallback,
and every fallback must have the same placeholders as its YAML counterpart.
"""

import pytest
import re
import yaml
from pathlib import Path

from startd8.implementation_engine.prompts import (
    _FALLBACK_TEMPLATES,
    get_template,
)

_YAML_PATH = Path(__file__).parent.parent.parent.parent / (
    "src/startd8/implementation_engine/prompts/contractor_prompts.yaml"
)


def _extract_placeholders(template: str) -> set:
    """Extract {placeholder} names from a template string."""
    return set(re.findall(r"\{(\w+)\}", template))


@pytest.fixture(scope="module")
def yaml_templates():
    data = yaml.safe_load(_YAML_PATH.read_text(encoding="utf-8"))
    return {
        name: entry["template"]
        for name, entry in data.get("prompts", {}).items()
        if isinstance(entry, dict) and "template" in entry
    }


class TestYamlFallbackSync:
    """Every YAML template must have a corresponding fallback."""

    def test_all_yaml_templates_have_fallbacks(self, yaml_templates):
        missing = set(yaml_templates.keys()) - set(_FALLBACK_TEMPLATES.keys())
        assert not missing, (
            f"{len(missing)} YAML template(s) have no fallback in "
            f"_FALLBACK_TEMPLATES: {sorted(missing)}"
        )

    def test_no_orphaned_fallbacks(self, yaml_templates):
        """Every fallback should correspond to a YAML template."""
        orphaned = set(_FALLBACK_TEMPLATES.keys()) - set(yaml_templates.keys())
        assert not orphaned, (
            f"{len(orphaned)} fallback(s) have no YAML template: {sorted(orphaned)}"
        )

    @pytest.mark.parametrize("name", sorted(_FALLBACK_TEMPLATES.keys()))
    def test_placeholder_parity(self, name, yaml_templates):
        """Fallback must accept the same placeholders as YAML."""
        if name not in yaml_templates:
            pytest.skip(f"No YAML template for '{name}'")
        yaml_placeholders = _extract_placeholders(yaml_templates[name])
        fallback_placeholders = _extract_placeholders(_FALLBACK_TEMPLATES[name])
        assert yaml_placeholders == fallback_placeholders, (
            f"Template '{name}' placeholder mismatch:\n"
            f"  YAML only: {yaml_placeholders - fallback_placeholders}\n"
            f"  Fallback only: {fallback_placeholders - yaml_placeholders}"
        )


class TestGetTemplateLoads:
    """get_template() returns a non-empty string for every known template."""

    @pytest.mark.parametrize("name", sorted(_FALLBACK_TEMPLATES.keys()))
    def test_template_loads(self, name):
        template = get_template(name)
        assert template and len(template.strip()) > 0, (
            f"get_template('{name}') returned empty"
        )
