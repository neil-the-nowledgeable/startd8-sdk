"""
Unit tests for the Help System
Tests configuration loading, help availability, and system validation.
"""

import pytest
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch
from rich.console import Console

from startd8.tui_help_system import HelpSystem, HelpTopic, ContextualHelp


class TestHelpSystemInitialization:
    """Test HelpSystem initialization and configuration loading"""

    def test_init_with_default_config_dir(self):
        """Test initialization with default config directory"""
        help_system = HelpSystem()
        assert help_system.config_dir is not None
        assert help_system.console is not None

    def test_init_with_custom_console(self):
        """Test initialization with custom console"""
        custom_console = Console()
        help_system = HelpSystem(console=custom_console)
        assert help_system.console == custom_console

    def test_init_with_custom_config_dir(self):
        """Test initialization with custom config directory"""
        with tempfile.TemporaryDirectory() as tmpdir:
            help_system = HelpSystem(config_dir=tmpdir)
            assert help_system.config_dir == Path(tmpdir)

    def test_help_topics_loaded(self):
        """Test that help topics are loaded from configuration"""
        help_system = HelpSystem()
        assert len(help_system.help_topics) > 0
        assert "getting_started" in help_system.help_topics

    def test_contextual_help_loaded(self):
        """Test that contextual help is loaded from configuration"""
        help_system = HelpSystem()
        assert len(help_system.contextual_help) > 0
        assert "main_menu" in help_system.contextual_help


class TestHelpTopics:
    """Test help topic functionality"""

    def test_help_topic_creation(self):
        """Test HelpTopic dataclass creation"""
        topic = HelpTopic(
            key="test_topic",
            title="Test Topic",
            icon="🧪",
            content="Test content",
            order=1,
            related=["other_topic"]
        )
        assert topic.key == "test_topic"
        assert topic.title == "Test Topic"
        assert topic.icon == "🧪"
        assert topic.order == 1
        assert "other_topic" in topic.related

    def test_get_help_topics_list(self):
        """Test getting list of available help topics"""
        help_system = HelpSystem()
        topics_list = help_system.get_help_topics_list()
        assert isinstance(topics_list, list)
        assert len(topics_list) > 0
        assert "getting_started" in topics_list

    def test_help_topic_properties(self):
        """Test that loaded help topics have expected properties"""
        help_system = HelpSystem()
        getting_started = help_system.help_topics.get("getting_started")
        
        assert getting_started is not None
        assert getting_started.title != ""
        assert getting_started.icon != ""
        assert getting_started.content != ""
        assert getting_started.order > 0

    def test_help_topic_related_topics(self):
        """Test that related topics are properly loaded"""
        help_system = HelpSystem()
        workflow = help_system.help_topics.get("workflow_overview")
        
        assert workflow is not None
        assert len(workflow.related) > 0
        assert "prompt_creation" in workflow.related


class TestContextualHelp:
    """Test contextual help functionality"""

    def test_contextual_help_creation(self):
        """Test ContextualHelp dataclass creation"""
        context = ContextualHelp(
            key="test_context",
            title="Test Context",
            icon="💬",
            description="Test description",
            usage="How to use",
            tips="Some tips",
            order=1
        )
        assert context.key == "test_context"
        assert context.title == "Test Context"
        assert context.description != ""
        assert context.usage != ""

    def test_get_contextual_help_keys(self):
        """Test getting list of available contextual help contexts"""
        help_system = HelpSystem()
        contexts_list = help_system.get_contextual_help_keys()
        assert isinstance(contexts_list, list)
        assert len(contexts_list) > 0
        assert "main_menu" in contexts_list

    def test_contextual_help_availability(self):
        """Test checking contextual help availability"""
        help_system = HelpSystem()
        assert help_system.is_help_available("main_menu")
        assert help_system.is_help_available("agent_selection")
        assert not help_system.is_help_available("nonexistent_context")

    def test_contextual_help_properties(self):
        """Test that loaded contextual help has expected properties"""
        help_system = HelpSystem()
        main_menu_help = help_system.contextual_help.get("main_menu")
        
        assert main_menu_help is not None
        assert main_menu_help.title != ""
        assert main_menu_help.icon != ""
        assert main_menu_help.description != ""
        assert main_menu_help.usage != ""
        assert main_menu_help.tips != ""


class TestHelpSystemValidation:
    """Test help system validation and configuration checking"""

    def test_validate_configuration_success(self):
        """Test successful configuration validation"""
        help_system = HelpSystem()
        validation = help_system.validate_configuration()
        
        assert validation["help_topics_loaded"] is True
        assert validation["contextual_help_loaded"] is True
        assert validation["topics_count"] > 0
        assert validation["contexts_count"] > 0
        assert validation["config_directory_exists"] is True

    def test_validate_configuration_returns_dict(self):
        """Test that validation returns expected dictionary structure"""
        help_system = HelpSystem()
        validation = help_system.validate_configuration()
        
        expected_keys = {
            "help_topics_loaded",
            "contextual_help_loaded",
            "topics_count",
            "contexts_count",
            "yaml_available",
            "questionary_available",
            "config_directory",
            "config_directory_exists"
        }
        assert all(key in validation for key in expected_keys)

    def test_topics_have_valid_order(self):
        """Test that all topics have valid order values"""
        help_system = HelpSystem()
        for topic in help_system.help_topics.values():
            assert isinstance(topic.order, int)
            assert topic.order > 0

    def test_contextual_help_have_valid_order(self):
        """Test that all contextual help have valid order values"""
        help_system = HelpSystem()
        for context in help_system.contextual_help.values():
            assert isinstance(context.order, int)
            assert context.order > 0


class TestHelpSystemGracefulFailure:
    """Test help system graceful failure handling"""

    def test_invalid_config_dir_graceful(self):
        """Test that invalid config directory doesn't crash"""
        with tempfile.TemporaryDirectory() as tmpdir:
            help_system = HelpSystem(config_dir=tmpdir)
            # Should not raise exception, topics will be empty
            assert len(help_system.help_topics) == 0

    def test_missing_yaml_file_graceful(self):
        """Test that missing YAML files are handled gracefully"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create empty directory without YAML files
            help_system = HelpSystem(config_dir=tmpdir)
            validation = help_system.validate_configuration()
            assert validation["help_topics_loaded"] is False

    @patch('startd8.tui_help_system.HAS_YAML', False)
    def test_missing_yaml_library_graceful(self):
        """Test graceful handling when YAML library is not available"""
        help_system = HelpSystem()
        # Should not crash, will fail gracefully
        assert help_system.help_topics is not None


class TestHelpSystemMethods:
    """Test public methods of HelpSystem"""

    def test_show_help_topics_returns_topic_key_or_none(self):
        """Test that show_help_topics returns valid response"""
        help_system = HelpSystem()
        
        # Mock questionary to avoid interactive prompt
        with patch('startd8.tui_help_system.questionary'):
            # When no selection, returns None
            result = help_system.show_help_topics()
            # Result can be None (cancelled) or a topic key
            assert result is None or result in help_system.help_topics

    def test_show_help_details_with_valid_topic(self):
        """Test showing help details for valid topic"""
        help_system = HelpSystem()
        
        with patch.object(help_system.console, 'print'):
            # Should not raise exception
            help_system.show_help_details("getting_started")

    def test_show_help_details_with_invalid_topic(self):
        """Test showing help details for invalid topic"""
        help_system = HelpSystem()
        
        with patch.object(help_system.console, 'print'):
            # Should handle gracefully
            help_system.show_help_details("nonexistent_topic")

    def test_show_contextual_help_valid_context(self):
        """Test showing contextual help for valid context"""
        help_system = HelpSystem()
        
        with patch.object(help_system.console, 'print'):
            # Should not raise exception
            help_system.show_contextual_help("main_menu")

    def test_show_contextual_help_invalid_context(self):
        """Test showing contextual help for invalid context"""
        help_system = HelpSystem()
        
        with patch.object(help_system.console, 'print'):
            # Should handle gracefully
            help_system.show_contextual_help("nonexistent_context")


class TestHelpContentStructure:
    """Test the structure and content of help topics and contexts"""

    def test_all_topics_have_required_fields(self):
        """Test that all help topics have required fields"""
        help_system = HelpSystem()
        
        for key, topic in help_system.help_topics.items():
            assert topic.key != ""
            assert topic.title != ""
            assert topic.icon != ""
            assert topic.content != ""
            assert topic.order > 0
            assert isinstance(topic.related, list)

    def test_all_contexts_have_required_fields(self):
        """Test that all contextual help have required fields"""
        help_system = HelpSystem()
        
        for key, context in help_system.contextual_help.items():
            assert context.key != ""
            assert context.title != ""
            assert context.icon != ""
            assert context.description != ""
            assert context.usage != ""
            assert context.tips != ""
            assert context.order > 0

    def test_topics_sorted_by_order(self):
        """Test that topics can be sorted by order"""
        help_system = HelpSystem()
        sorted_topics = sorted(
            help_system.help_topics.values(),
            key=lambda t: t.order
        )
        
        assert len(sorted_topics) == len(help_system.help_topics)
        for i in range(len(sorted_topics) - 1):
            assert sorted_topics[i].order <= sorted_topics[i+1].order

    def test_core_help_topics_exist(self):
        """Test that core help topics are available"""
        help_system = HelpSystem()
        core_topics = [
            "getting_started",
            "workflow_overview",
            "prompt_creation",
            "agents",
            "api_keys",
            "troubleshooting"
        ]
        
        for topic in core_topics:
            assert topic in help_system.help_topics, f"Missing core topic: {topic}"

    def test_core_contextual_help_exist(self):
        """Test that core contextual help contexts are available"""
        help_system = HelpSystem()
        core_contexts = [
            "main_menu",
            "agent_selection",
            "prompt_creation"
        ]
        
        for context in core_contexts:
            assert context in help_system.contextual_help, f"Missing core context: {context}"


class TestHelpSystemIntegration:
    """Integration tests for the help system"""

    def test_related_topics_reference_existing_topics(self):
        """Test that related topics reference only existing topics"""
        help_system = HelpSystem()
        
        for key, topic in help_system.help_topics.items():
            for related_key in topic.related:
                assert related_key in help_system.help_topics, \
                    f"Topic '{key}' references non-existent related topic '{related_key}'"

    def test_help_system_complete_workflow(self):
        """Test complete help system workflow"""
        help_system = HelpSystem()
        
        # Validate configuration
        validation = help_system.validate_configuration()
        assert validation["help_topics_loaded"]
        assert validation["contextual_help_loaded"]
        
        # Check topic availability
        topics = help_system.get_help_topics_list()
        assert len(topics) > 0
        
        # Check contextual help availability
        contexts = help_system.get_contextual_help_keys()
        assert len(contexts) > 0
        
        # Check specific help is available
        assert help_system.is_help_available("main_menu")
