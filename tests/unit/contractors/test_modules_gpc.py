"""Tests for EnrichmentModule marker guard — REQ-GPC-502."""

from __future__ import annotations

import pytest

from startd8.contractors.artisan_phases.design_prompts.modules import (
    EnrichmentModule,
)


class TestEnrichmentModuleMarkerGuard:
    """REQ-GPC-502: render() defense-in-depth against omitted markers."""

    def test_omitted_param_sources_produces_empty(self):
        """Marker dict in parameter_sources → no prompt text."""
        module = EnrichmentModule()
        data = {
            "parameter_sources": {"_omitted": "profile=source"},
            "semantic_conventions": {},
        }
        fragment = module.render(data)
        assert "_omitted" not in fragment.text
        assert fragment.text == ""

    def test_omitted_conventions_produces_empty(self):
        """Marker dict in semantic_conventions → no conventions rendered."""
        module = EnrichmentModule()
        data = {
            "parameter_sources": {},
            "semantic_conventions": {"_omitted": "profile=source"},
        }
        fragment = module.render(data)
        assert "_omitted" not in fragment.text
        assert "Semantic Conventions" not in fragment.text

    def test_real_param_sources_rendered(self):
        """Normal parameter_sources render correctly."""
        module = EnrichmentModule()
        data = {
            "parameter_sources": {
                "dashboard_uid": {"origin": "manifest"},
            },
            "semantic_conventions": {},
        }
        fragment = module.render(data)
        assert "`dashboard_uid`" in fragment.text
        assert "manifest" in fragment.text

    def test_both_omitted_produces_empty(self):
        """Both fields omitted → completely empty output."""
        module = EnrichmentModule()
        data = {
            "parameter_sources": {"_omitted": "profile=source"},
            "semantic_conventions": {"_omitted": "profile=source"},
        }
        fragment = module.render(data)
        assert fragment.text == ""
        assert fragment.token_estimate == 0
