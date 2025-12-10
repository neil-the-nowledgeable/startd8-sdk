"""
Unit tests for the Advanced Help System.

Tests FAQ, Tips & Tricks, Keyboard Shortcuts, and Troubleshooting functionality.
"""

import pytest
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch
from rich.console import Console

from startd8.tui_advanced_help import (
    AdvancedHelpSystem,
    FAQ,
    Tip,
    Shortcut,
    HAS_YAML,
    HAS_QUESTIONARY,
)


class TestAdvancedHelpSystemInitialization:
    """Test AdvancedHelpSystem initialization and configuration loading."""

    def test_init_with_default_config_dir(self):
        """Test initialization with default config directory."""
        help_system = AdvancedHelpSystem()
        assert help_system.config_dir is not None
        assert help_system.console is not None

    def test_init_with_custom_console(self):
        """Test initialization with custom console."""
        custom_console = Console()
        help_system = AdvancedHelpSystem(console=custom_console)
        assert help_system.console == custom_console

    def test_init_with_custom_config_dir(self):
        """Test initialization with custom config directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            help_system = AdvancedHelpSystem(config_dir=tmpdir)
            assert help_system.config_dir == Path(tmpdir)

    def test_faqs_loaded(self):
        """Test that FAQs are loaded from configuration."""
        help_system = AdvancedHelpSystem()
        assert len(help_system.faqs) > 0
        assert "getting_started" in help_system.faqs

    def test_tips_loaded(self):
        """Test that tips are loaded from configuration."""
        help_system = AdvancedHelpSystem()
        assert len(help_system.tips) > 0
        assert "productivity" in help_system.tips

    def test_shortcuts_loaded(self):
        """Test that shortcuts are loaded from configuration."""
        help_system = AdvancedHelpSystem()
        assert len(help_system.shortcuts) > 0
        assert "navigation" in help_system.shortcuts

    def test_troubleshooting_loaded(self):
        """Test that troubleshooting guides are loaded."""
        help_system = AdvancedHelpSystem()
        assert len(help_system.troubleshooting) > 0


class TestFAQDataclass:
    """Test FAQ dataclass."""

    def test_faq_creation(self):
        """Test FAQ dataclass creation."""
        faq = FAQ(
            category="test_category",
            id="q1",
            question="Test question?",
            answer="Test answer."
        )
        assert faq.category == "test_category"
        assert faq.id == "q1"
        assert faq.question == "Test question?"
        assert faq.answer == "Test answer."

    def test_faq_loaded_properties(self):
        """Test that loaded FAQs have expected properties."""
        help_system = AdvancedHelpSystem()
        
        # Check a FAQ exists and has content
        if help_system.faqs:
            first_category = list(help_system.faqs.keys())[0]
            first_faq = help_system.faqs[first_category][0]
            
            assert first_faq.category == first_category
            assert first_faq.id != ""
            assert first_faq.question != ""
            assert first_faq.answer != ""


class TestTipDataclass:
    """Test Tip dataclass."""

    def test_tip_creation(self):
        """Test Tip dataclass creation."""
        tip = Tip(
            category="test_category",
            id="tip1",
            title="Test Tip",
            content="Test tip content."
        )
        assert tip.category == "test_category"
        assert tip.id == "tip1"
        assert tip.title == "Test Tip"
        assert tip.content == "Test tip content."

    def test_tip_loaded_properties(self):
        """Test that loaded tips have expected properties."""
        help_system = AdvancedHelpSystem()
        
        if help_system.tips:
            first_category = list(help_system.tips.keys())[0]
            first_tip = help_system.tips[first_category][0]
            
            assert first_tip.category == first_category
            assert first_tip.id != ""
            assert first_tip.title != ""
            assert first_tip.content != ""


class TestShortcutDataclass:
    """Test Shortcut dataclass."""

    def test_shortcut_creation(self):
        """Test Shortcut dataclass creation."""
        shortcut = Shortcut(
            section="navigation",
            action="Navigate up",
            keys=["↑"],
            context="All menus"
        )
        assert shortcut.section == "navigation"
        assert shortcut.action == "Navigate up"
        assert shortcut.keys == ["↑"]
        assert shortcut.context == "All menus"

    def test_shortcut_with_multiple_keys(self):
        """Test shortcut with multiple keys."""
        shortcut = Shortcut(
            section="actions",
            action="Copy",
            keys=["Ctrl", "C"],
            context="Text selection"
        )
        assert len(shortcut.keys) == 2
        assert "Ctrl" in shortcut.keys

    def test_shortcut_loaded_properties(self):
        """Test that loaded shortcuts have expected properties."""
        help_system = AdvancedHelpSystem()
        
        if help_system.shortcuts:
            first_section = list(help_system.shortcuts.keys())[0]
            first_shortcut = help_system.shortcuts[first_section][0]
            
            assert first_shortcut.section == first_section
            assert first_shortcut.action != ""
            assert isinstance(first_shortcut.keys, list)


class TestAdvancedHelpValidation:
    """Test advanced help system validation."""

    def test_validate_configuration_success(self):
        """Test successful configuration validation."""
        help_system = AdvancedHelpSystem()
        validation = help_system.validate_configuration()
        
        assert validation["faqs_loaded"] is True
        assert validation["tips_loaded"] is True
        assert validation["shortcuts_loaded"] is True
        assert validation["troubleshooting_loaded"] is True
        assert validation["config_directory_exists"] is True

    def test_validate_configuration_returns_dict(self):
        """Test that validation returns expected dictionary structure."""
        help_system = AdvancedHelpSystem()
        validation = help_system.validate_configuration()
        
        expected_keys = {
            "faqs_loaded",
            "tips_loaded",
            "shortcuts_loaded",
            "troubleshooting_loaded",
            "faq_count",
            "tips_count",
            "shortcuts_count",
            "problems_count",
            "yaml_available",
            "questionary_available",
            "config_directory",
            "config_directory_exists"
        }
        assert all(key in validation for key in expected_keys)

    def test_counts_are_accurate(self):
        """Test that item counts are accurate."""
        help_system = AdvancedHelpSystem()
        validation = help_system.validate_configuration()
        
        # Calculate expected counts
        expected_faq_count = sum(len(faqs) for faqs in help_system.faqs.values())
        expected_tip_count = sum(len(tips) for tips in help_system.tips.values())
        expected_shortcut_count = sum(len(s) for s in help_system.shortcuts.values())
        expected_problem_count = sum(len(p) for p in help_system.troubleshooting.values())
        
        assert validation["faq_count"] == expected_faq_count
        assert validation["tips_count"] == expected_tip_count
        assert validation["shortcuts_count"] == expected_shortcut_count
        assert validation["problems_count"] == expected_problem_count


class TestAdvancedHelpGracefulFailure:
    """Test advanced help system graceful failure handling."""

    def test_invalid_config_dir_graceful(self):
        """Test that invalid config directory doesn't crash."""
        with tempfile.TemporaryDirectory() as tmpdir:
            help_system = AdvancedHelpSystem(config_dir=tmpdir)
            # Should not raise exception, collections will be empty
            assert len(help_system.faqs) == 0
            assert len(help_system.tips) == 0

    def test_missing_yaml_file_graceful(self):
        """Test that missing YAML files are handled gracefully."""
        with tempfile.TemporaryDirectory() as tmpdir:
            help_system = AdvancedHelpSystem(config_dir=tmpdir)
            validation = help_system.validate_configuration()
            assert validation["faqs_loaded"] is False

    @patch('startd8.tui_advanced_help.HAS_YAML', False)
    def test_missing_yaml_library_graceful(self):
        """Test graceful handling when YAML library is not available."""
        help_system = AdvancedHelpSystem()
        # Should not crash
        assert help_system.faqs is not None
        assert isinstance(help_system.faqs, dict)


class TestFAQMethods:
    """Test FAQ-related methods."""

    def test_get_faq_categories(self):
        """Test getting FAQ categories."""
        help_system = AdvancedHelpSystem()
        categories = help_system.get_faq_categories()
        
        assert isinstance(categories, list)
        assert len(categories) > 0
        assert "getting_started" in categories

    def test_show_faq_with_empty_faqs(self):
        """Test show_faq when no FAQs are loaded."""
        with tempfile.TemporaryDirectory() as tmpdir:
            help_system = AdvancedHelpSystem(config_dir=tmpdir)
            
            with patch.object(help_system.console, 'print'):
                # Should handle gracefully
                help_system.show_faq()


class TestTipMethods:
    """Test Tips-related methods."""

    def test_get_tip_categories(self):
        """Test getting tip categories."""
        help_system = AdvancedHelpSystem()
        categories = help_system.get_tip_categories()
        
        assert isinstance(categories, list)
        assert len(categories) > 0

    def test_get_random_tip(self):
        """Test getting a random tip."""
        help_system = AdvancedHelpSystem()
        tip = help_system.get_random_tip()
        
        assert tip is not None
        assert isinstance(tip, Tip)
        assert tip.title != ""
        assert tip.content != ""

    def test_get_random_tip_empty(self):
        """Test get_random_tip when no tips loaded."""
        with tempfile.TemporaryDirectory() as tmpdir:
            help_system = AdvancedHelpSystem(config_dir=tmpdir)
            tip = help_system.get_random_tip()
            assert tip is None

    def test_show_tips_random(self):
        """Test showing random tips."""
        help_system = AdvancedHelpSystem()
        
        with patch.object(help_system.console, 'print'):
            # Should not raise exception
            help_system.show_tips(max_tips=1, random_select=True)

    def test_show_tips_sequential(self):
        """Test showing tips sequentially."""
        help_system = AdvancedHelpSystem()
        
        with patch.object(help_system.console, 'print'):
            # Should not raise exception
            help_system.show_tips(max_tips=3, random_select=False)

    def test_show_tips_empty(self):
        """Test show_tips when no tips loaded."""
        with tempfile.TemporaryDirectory() as tmpdir:
            help_system = AdvancedHelpSystem(config_dir=tmpdir)
            
            with patch.object(help_system.console, 'print'):
                # Should handle gracefully
                help_system.show_tips()


class TestShortcutMethods:
    """Test Shortcuts-related methods."""

    def test_show_keyboard_shortcuts(self):
        """Test showing keyboard shortcuts."""
        help_system = AdvancedHelpSystem()
        
        with patch.object(help_system.console, 'print'):
            # Should not raise exception
            help_system.show_keyboard_shortcuts()

    def test_show_keyboard_shortcuts_empty(self):
        """Test show_keyboard_shortcuts when empty."""
        with tempfile.TemporaryDirectory() as tmpdir:
            help_system = AdvancedHelpSystem(config_dir=tmpdir)
            
            with patch.object(help_system.console, 'print'):
                # Should handle gracefully
                help_system.show_keyboard_shortcuts()


class TestTroubleshootingMethods:
    """Test Troubleshooting-related methods."""

    def test_show_troubleshooting_empty(self):
        """Test show_troubleshooting when empty."""
        with tempfile.TemporaryDirectory() as tmpdir:
            help_system = AdvancedHelpSystem(config_dir=tmpdir)
            
            with patch.object(help_system.console, 'print'):
                # Should handle gracefully
                help_system.show_troubleshooting()


class TestContentStructure:
    """Test the structure and content of advanced help items."""

    def test_all_faqs_have_required_fields(self):
        """Test that all FAQs have required fields."""
        help_system = AdvancedHelpSystem()
        
        for category, faqs in help_system.faqs.items():
            for faq in faqs:
                assert faq.category == category
                assert faq.id != ""
                assert faq.question != ""
                assert faq.answer != ""

    def test_all_tips_have_required_fields(self):
        """Test that all tips have required fields."""
        help_system = AdvancedHelpSystem()
        
        for category, tips in help_system.tips.items():
            for tip in tips:
                assert tip.category == category
                assert tip.id != ""
                assert tip.title != ""
                assert tip.content != ""

    def test_all_shortcuts_have_required_fields(self):
        """Test that all shortcuts have required fields."""
        help_system = AdvancedHelpSystem()
        
        for section, shortcuts in help_system.shortcuts.items():
            for shortcut in shortcuts:
                assert shortcut.section == section
                assert shortcut.action != ""
                assert isinstance(shortcut.keys, list)
                assert len(shortcut.keys) > 0

    def test_troubleshooting_structure(self):
        """Test troubleshooting guide structure."""
        help_system = AdvancedHelpSystem()
        
        for category, problems in help_system.troubleshooting.items():
            assert isinstance(problems, list)
            for problem in problems:
                assert "issue" in problem
                assert "solutions" in problem
                assert isinstance(problem["solutions"], list)


class TestAdvancedHelpIntegration:
    """Integration tests for the advanced help system."""

    def test_complete_validation_workflow(self):
        """Test complete validation workflow."""
        help_system = AdvancedHelpSystem()
        
        # Validate configuration
        validation = help_system.validate_configuration()
        assert validation["faqs_loaded"]
        assert validation["tips_loaded"]
        assert validation["shortcuts_loaded"]
        assert validation["troubleshooting_loaded"]
        
        # Check category availability
        faq_categories = help_system.get_faq_categories()
        tip_categories = help_system.get_tip_categories()
        
        assert len(faq_categories) > 0
        assert len(tip_categories) > 0
        
        # Get random tip
        tip = help_system.get_random_tip()
        assert tip is not None

    def test_all_categories_consistent(self):
        """Test that all categories are internally consistent."""
        help_system = AdvancedHelpSystem()
        
        # FAQ categories match stored data
        faq_categories = help_system.get_faq_categories()
        assert set(faq_categories) == set(help_system.faqs.keys())
        
        # Tip categories match stored data
        tip_categories = help_system.get_tip_categories()
        assert set(tip_categories) == set(help_system.tips.keys())


class TestSecurityAndRobustness:
    """Test security and robustness features."""

    def test_content_sanitization(self):
        """Test that content is sanitized."""
        help_system = AdvancedHelpSystem()
        
        # All content should be strings
        for category, faqs in help_system.faqs.items():
            for faq in faqs:
                assert isinstance(faq.question, str)
                assert isinstance(faq.answer, str)

    def test_handles_missing_keys_gracefully(self):
        """Test that missing keys in config don't cause crashes."""
        # Create a minimal YAML file
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "advanced_help.yaml"
            config_path.write_text("faq:\n  test:\n    questions: []")
            
            help_system = AdvancedHelpSystem(config_dir=tmpdir)
            
            # Should load without crash
            assert help_system.faqs.get("test") == []

    def test_item_count_limits(self):
        """Test that item count limits are enforced."""
        help_system = AdvancedHelpSystem()
        
        # Each category should have reasonable limits
        for category, faqs in help_system.faqs.items():
            assert len(faqs) <= 100  # MAX_ITEMS_PER_CATEGORY
        
        for category, tips in help_system.tips.items():
            assert len(tips) <= 100


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_empty_tip_display(self):
        """Test displaying zero tips."""
        help_system = AdvancedHelpSystem()
        
        with patch.object(help_system.console, 'print'):
            # Should handle gracefully
            help_system.show_tips(max_tips=0, random_select=True)

    def test_large_max_tips(self):
        """Test requesting more tips than available."""
        help_system = AdvancedHelpSystem()
        
        with patch.object(help_system.console, 'print'):
            # Should handle gracefully
            help_system.show_tips(max_tips=1000, random_select=True)

    def test_repeated_random_tip_calls(self):
        """Test multiple random tip retrievals."""
        help_system = AdvancedHelpSystem()
        
        # Multiple calls should not fail
        tips = [help_system.get_random_tip() for _ in range(10)]
        assert all(tip is not None for tip in tips)
