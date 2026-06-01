"""Regression guard for the Prime/Primary Contractor model-centralization invariant.

REQ-PCMR (Prime Contractor Model Refresh): every default model the contractor path
uses MUST resolve through ``startd8.model_catalog`` — no parallel hardcoded lists,
no stale literals. These tests fail if the surface re-fragments.
"""

import re
from pathlib import Path

import pytest

import startd8
from startd8 import config as config_mod
from startd8.config import ConfigManager
from startd8.model_catalog import Models, is_known_model
from startd8.workflows.builtin import primary_contractor_models as pcm

_PKG_ROOT = Path(startd8.__file__).resolve().parent

# Models removed from the contractor path or flagged retiring (REQ-PCMR-102).
_FORBIDDEN_LITERALS = ("gpt-4o-mini", "gemini-2.0-flash")

# Contractor-path source files that must not carry stale/parallel model literals
# (REQ-PCMR-110/111). Paths are relative to the startd8 package root.
_GUARDED_SOURCES = (
    "workflows/builtin/primary_contractor_models.py",
    "workflows/builtin/primary_contractor_workflow.py",
    "workflows/builtin/primary_contractor_contextcore_workflow.py",
    "integrations/contextcore.py",
)


class TestDefaultsAreCatalogBacked:
    """REQ-PCMR-100/101/130: contractor defaults are catalog constants."""

    def test_lead_default_is_opus_flagship(self):
        cfg = pcm.PrimaryContractorConfig(task_description="x")
        assert cfg.lead_agent == Models.PRIMARY_CONTRACTOR_LEAD
        assert cfg.lead_agent == Models.CLAUDE_OPUS_LATEST  # REQ-PCMR-100
        assert is_known_model(cfg.lead_agent)

    def test_drafter_default_is_gemini_flash_lite(self):
        cfg = pcm.PrimaryContractorConfig(task_description="x")
        assert cfg.drafter_agent == Models.PRIMARY_CONTRACTOR_DRAFTER
        assert cfg.drafter_agent == Models.GEMINI_FLASH_LITE  # REQ-PCMR-101
        assert is_known_model(cfg.drafter_agent)

    def test_all_contractor_role_defaults_are_known_models(self):
        # REQ-PCMR-102: no default spec may be absent from the catalog.
        for spec in (Models.PRIMARY_CONTRACTOR_LEAD, Models.PRIMARY_CONTRACTOR_DRAFTER):
            assert is_known_model(spec), f"{spec} is not in the model catalog"


class TestConfigDefaultsDeriveFromCatalog:
    """REQ-PCMR-112: TUI agent defaults follow the catalog, not bare literals."""

    def test_config_claude_default_tracks_catalog(self, tmp_path, monkeypatch):
        manager = ConfigManager(config_dir=tmp_path)
        defaults = manager._default_config()
        claude_default = defaults["models"]["claude"]["default"]
        # Bare id form of the balanced anthropic catalog spec.
        assert claude_default == Models.CLAUDE_SONNET_LATEST.split(":", 1)[1]

        # A catalog bump must propagate with no edit to config.py (REQ-PCMR-112 AC).
        monkeypatch.setattr(
            config_mod, "get_latest_model", lambda p, t: "anthropic:claude-sonnet-9-9"
        )
        bumped = ConfigManager(config_dir=tmp_path)._default_config()
        assert bumped["models"]["claude"]["default"] == "claude-sonnet-9-9"

    def test_config_defaults_have_no_provider_prefix(self, tmp_path):
        # Config stores bare ids; deriving from catalog must strip the prefix.
        defaults = ConfigManager(config_dir=tmp_path)._default_config()
        for agent in ("claude", "gpt4"):
            assert ":" not in defaults["models"][agent]["default"]


class TestNoParallelOrStaleLists:
    """REQ-PCMR-110/111: dead enum gone, no stale literals in contractor sources."""

    def test_drafter_choice_enum_removed(self):
        assert not hasattr(pcm, "DrafterChoice")
        assert "DrafterChoice" not in pcm.__all__

    @pytest.mark.parametrize("rel_path", _GUARDED_SOURCES)
    def test_no_forbidden_model_literals(self, rel_path):
        src = (_PKG_ROOT / rel_path).read_text()
        for literal in _FORBIDDEN_LITERALS:
            assert literal not in src, (
                f"{rel_path} contains forbidden model literal {literal!r}; "
                "route through startd8.model_catalog instead (REQ-PCMR-111)."
            )

    @pytest.mark.parametrize("rel_path", _GUARDED_SOURCES)
    def test_provider_model_literals_are_known(self, rel_path):
        # Any provider:model string a contractor source still names must be a
        # catalog-known model (REQ-PCMR-102). Catches drift toward unknown ids.
        src = (_PKG_ROOT / rel_path).read_text()
        specs = re.findall(
            r"\"((?:anthropic|openai|gemini|mistral|ollama|nim):[A-Za-z0-9.\-/]+)\"",
            src,
        )
        for spec in specs:
            assert is_known_model(spec), (
                f"{rel_path} names unknown model {spec!r}; add it to the catalog "
                "or use a Models.* constant (REQ-PCMR-102/130)."
            )
