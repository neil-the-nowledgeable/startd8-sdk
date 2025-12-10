"""
Help System for startd8 TUI.

This module provides the core help system functionality including:
- Help topic management and display
- Contextual help for specific screens
- Configuration loading from YAML files

Module Constants:
    HAS_YAML: bool - Whether PyYAML is available
    HAS_QUESTIONARY: bool - Whether questionary is available

Example:
    >>> from startd8.tui_help_system import HelpSystem
    >>> help_sys = HelpSystem()
    >>> help_sys.show_main_help()
"""

import logging
from pathlib import Path
from typing import Dict, List, Optional, Any, Final
from dataclasses import dataclass, field

try:
    import yaml
    from yaml import YAMLError
    HAS_YAML = True
except ImportError:
    HAS_YAML = False
    YAMLError = Exception  # Fallback for type checking

try:
    import questionary
    HAS_QUESTIONARY = True
except ImportError:
    HAS_QUESTIONARY = False

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.markup import escape

# Module logger
logger = logging.getLogger(__name__)

# Constants
BACK_OPTION: Final[str] = "← Back"
CONFIG_ENCODING: Final[str] = "utf-8"
MAX_CONTENT_LENGTH: Final[int] = 50000

__all__ = [
    "HelpSystem",
    "HelpTopic",
    "ContextualHelp",
    "HAS_YAML",
    "HAS_QUESTIONARY",
]


def _sanitize_content(text: Optional[str], max_length: int = MAX_CONTENT_LENGTH) -> str:
    """
    Sanitize text for safe Rich console display.
    
    Args:
        text: Text to sanitize (may be None)
        max_length: Maximum allowed length
        
    Returns:
        Sanitized text safe for display
    """
    if not text:
        return ""
    
    # Truncate if too long
    if len(text) > max_length:
        text = text[:max_length] + "... [truncated]"
    
    return text


@dataclass
class HelpTopic:
    """
    Represents a help topic.
    
    Attributes:
        key: Unique identifier for the topic
        title: Display title
        icon: Emoji icon for the topic
        content: Help content text
        order: Sort order (lower = first)
        related: List of related topic keys
    """
    key: str
    title: str
    icon: str
    content: str
    order: int
    related: List[str] = field(default_factory=list)


@dataclass
class ContextualHelp:
    """
    Represents contextual help for a specific screen/menu.
    
    Attributes:
        key: Unique identifier for the context
        title: Display title
        icon: Emoji icon
        description: Brief description of the context
        usage: How to use this screen
        tips: Helpful tips
        order: Sort order
    """
    key: str
    title: str
    icon: str
    description: str
    usage: str
    tips: str
    order: int


class HelpSystem:
    """
    Manages help content for the TUI.
    Loads help topics and contextual help from YAML configuration files.
    """

    def __init__(self, console: Console = None, config_dir: str = None):
        """
        Initialize the HelpSystem.
        
        Args:
            console: Rich console for output
            config_dir: Directory containing help YAML files
        """
        self.console = console or Console()
        
        # Determine config directory
        if config_dir is None:
            # Default to help_content directory in same package
            config_dir = Path(__file__).parent / "help_content"
        else:
            config_dir = Path(config_dir)
        
        self.config_dir = config_dir
        self.help_topics: Dict[str, HelpTopic] = {}
        self.contextual_help: Dict[str, ContextualHelp] = {}
        self._related_topics: Dict[str, List[str]] = {}
        
        # Load configurations
        self._load_help_topics()
        self._load_contextual_help()

    def _load_help_topics(self) -> None:
        """
        Load help topics from YAML file with proper error handling.
        
        Handles the following error cases gracefully:
        - Missing PyYAML library
        - Missing configuration file
        - Permission errors
        - Invalid YAML syntax
        - Invalid configuration structure
        """
        if not HAS_YAML:
            logger.warning("PyYAML not installed. Help system unavailable.")
            return
        
        config_file = self.config_dir / "help_topics.yaml"
        
        if not config_file.exists():
            logger.warning(f"Help config file not found: {config_file}")
            return
        
        try:
            with open(config_file, "r", encoding=CONFIG_ENCODING) as f:
                data = yaml.safe_load(f)
        except PermissionError:
            logger.error(f"Permission denied reading: {config_file}")
            return
        except YAMLError as e:
            logger.error(f"Invalid YAML syntax in {config_file}: {e}")
            return
        except OSError as e:
            logger.error(f"Error reading {config_file}: {e}")
            return
        
        # Validate data structure
        if not isinstance(data, dict):
            logger.error(f"Invalid config format in {config_file}: expected dict")
            return
        
        topics_data = data.get("topics")
        if not isinstance(topics_data, dict):
            logger.warning("No valid topics found in configuration")
            return
        
        # Load topics with validation
        for key, topic_data in topics_data.items():
            if not isinstance(topic_data, dict):
                logger.warning(f"Skipping invalid topic: {key}")
                continue
            
            try:
                topic = HelpTopic(
                    key=str(key),
                    title=_sanitize_content(topic_data.get("title", "")),
                    icon=str(topic_data.get("icon", ""))[:10],  # Limit icon length
                    content=_sanitize_content(topic_data.get("content", "")),
                    order=int(topic_data.get("order", 999)),
                    related=[]  # Will be populated from related_topics
                )
                self.help_topics[key] = topic
            except (TypeError, ValueError) as e:
                logger.warning(f"Error loading topic {key}: {e}")
                continue
        
        # Load related topics mapping
        related_data = data.get("related_topics", {})
        if isinstance(related_data, dict):
            self._related_topics = related_data
        
        # Populate related topics for each topic (only valid references)
        for key, topic in self.help_topics.items():
            related = self._related_topics.get(key, [])
            if isinstance(related, list):
                # Only include references to existing topics
                topic.related = [r for r in related if r in self.help_topics]

    def _load_contextual_help(self) -> None:
        """
        Load contextual help from YAML file with proper error handling.
        
        Handles the following error cases gracefully:
        - Missing PyYAML library
        - Missing configuration file
        - Permission errors
        - Invalid YAML syntax
        - Invalid configuration structure
        """
        if not HAS_YAML:
            return
        
        config_file = self.config_dir / "contextual_help.yaml"
        
        if not config_file.exists():
            logger.warning(f"Contextual help config not found: {config_file}")
            return
        
        try:
            with open(config_file, "r", encoding=CONFIG_ENCODING) as f:
                data = yaml.safe_load(f)
        except PermissionError:
            logger.error(f"Permission denied reading: {config_file}")
            return
        except YAMLError as e:
            logger.error(f"Invalid YAML syntax in {config_file}: {e}")
            return
        except OSError as e:
            logger.error(f"Error reading {config_file}: {e}")
            return
        
        # Validate data structure
        if not isinstance(data, dict):
            logger.error(f"Invalid config format in {config_file}: expected dict")
            return
        
        contexts_data = data.get("contexts")
        if not isinstance(contexts_data, dict):
            logger.warning("No valid contexts found in configuration")
            return
        
        # Load contexts with validation
        for key, context_data in contexts_data.items():
            if not isinstance(context_data, dict):
                logger.warning(f"Skipping invalid context: {key}")
                continue
            
            try:
                context = ContextualHelp(
                    key=str(key),
                    title=_sanitize_content(context_data.get("title", "")),
                    icon=str(context_data.get("icon", ""))[:10],
                    description=_sanitize_content(context_data.get("description", "")),
                    usage=_sanitize_content(context_data.get("usage", "")),
                    tips=_sanitize_content(context_data.get("tips", "")),
                    order=int(context_data.get("order", 999))
                )
                self.contextual_help[key] = context
            except (TypeError, ValueError) as e:
                logger.warning(f"Error loading context {key}: {e}")
                continue

    def show_help_topics(self) -> Optional[str]:
        """
        Display help topics menu and let user select one.
        Returns the selected topic key, or None if user cancels.
        """
        if not self.help_topics:
            self.console.print(
                "[yellow]Help system not available. Please check configuration.[/yellow]"
            )
            return None
        
        # Sort topics by order
        sorted_topics = sorted(
            self.help_topics.values(),
            key=lambda t: t.order
        )
        
        choices = [f"{t.icon} {t.title}" for t in sorted_topics]
        choices.append(BACK_OPTION)
        
        if not HAS_QUESTIONARY:
            self.console.print("[red]Questionary not available[/red]")
            return None
        
        self.console.print("\n")
        selected = questionary.select(
            "Select a help topic:",
            choices=choices,
            use_shortcuts=False,
            use_pointer=True
        ).ask()
        
        if not selected or BACK_OPTION in selected:
            return None
        
        # Find selected topic
        for topic in sorted_topics:
            if f"{topic.icon} {topic.title}" == selected:
                return topic.key
        
        return None

    def show_help_details(self, topic_key: str) -> None:
        """
        Display detailed help for a specific topic.
        
        Args:
            topic_key: Key of the help topic to display
        """
        if topic_key not in self.help_topics:
            self.console.print("[red]Topic not found[/red]")
            return
        
        topic = self.help_topics[topic_key]
        
        # Build help panel content
        content = topic.content
        
        # Add related topics if available
        if topic.related:
            related_titles = []
            for related_key in topic.related:
                if related_key in self.help_topics:
                    related_topic = self.help_topics[related_key]
                    related_titles.append(f"{related_topic.icon} {related_topic.title}")
            
            if related_titles:
                content += "\n\n[bold cyan]Related Topics:[/bold cyan]\n"
                for title in related_titles:
                    content += f"  • {title}\n"
        
        # Display in panel
        self.console.print(Panel(
            content,
            title=f"{topic.icon} {topic.title}",
            border_style="cyan",
            padding=(1, 2)
        ))
        
        # Wait for user to continue
        if HAS_QUESTIONARY:
            questionary.press_any_key_to_continue("\nPress any key to continue...").ask()
        else:
            input("\nPress Enter to continue...")

    def show_main_help(self) -> None:
        """
        Show main help menu with topic selection loop.
        User can browse through topics and return to help menu.
        """
        if not self.help_topics:
            self.console.print(
                "[yellow]Help system not available.[/yellow]"
            )
            return
        
        while True:
            topic_key = self.show_help_topics()
            if not topic_key:
                break
            
            self.show_help_details(topic_key)

    def show_contextual_help(self, context_key: str) -> None:
        """
        Display contextual help for a specific menu/screen.
        
        Args:
            context_key: Key of the context (e.g., 'main_menu', 'agent_selection')
        """
        if context_key not in self.contextual_help:
            self.console.print(
                f"[yellow]No help available for this screen.[/yellow]"
            )
            return
        
        context = self.contextual_help[context_key]
        
        # Build help content
        help_content = f"""[bold]{context.description}[/bold]

[bold cyan]What you can do:[/bold cyan]
{context.usage}

[bold yellow]Tips:[/bold yellow]
{context.tips}"""
        
        # Display in panel
        self.console.print(Panel(
            help_content,
            title=f"{context.icon} {context.title}",
            border_style="yellow",
            padding=(1, 2)
        ))
        
        # Wait for user to continue
        if HAS_QUESTIONARY:
            questionary.press_any_key_to_continue("\nPress any key to continue...").ask()
        else:
            input("\nPress Enter to continue...")

    def get_help_topics_list(self) -> List[str]:
        """
        Get list of all available help topic keys.
        
        Returns:
            List of topic keys
        """
        return list(self.help_topics.keys())

    def get_contextual_help_keys(self) -> List[str]:
        """
        Get list of all available contextual help keys.
        
        Returns:
            List of context keys
        """
        return list(self.contextual_help.keys())

    def is_help_available(self, context_key: str) -> bool:
        """
        Check if contextual help is available for a context.
        
        Args:
            context_key: Key of the context to check
        
        Returns:
            True if help is available, False otherwise
        """
        return context_key in self.contextual_help

    def validate_configuration(self) -> Dict[str, Any]:
        """
        Validate help system configuration.
        
        Returns:
            Dictionary with validation results
        """
        return {
            "help_topics_loaded": len(self.help_topics) > 0,
            "contextual_help_loaded": len(self.contextual_help) > 0,
            "topics_count": len(self.help_topics),
            "contexts_count": len(self.contextual_help),
            "yaml_available": HAS_YAML,
            "questionary_available": HAS_QUESTIONARY,
            "config_directory": str(self.config_dir),
            "config_directory_exists": self.config_dir.exists()
        }

    def add_workflow_help_link(self, workflow_key: str) -> str:
        """
        Get reference to workflow help topic if available.
        
        Args:
            workflow_key: Key of the workflow
        
        Returns:
            Related topic suggestion or empty string
        """
        # Map workflow keys to help topics
        workflow_to_topic = {
            'iterative_workflow': 'advanced_features',
            'enhancement_chain': 'advanced_features',
            'design_pipeline': 'advanced_features',
            'job_queue': 'advanced_features'
        }
        
        if workflow_key in workflow_to_topic:
            return workflow_to_topic[workflow_key]
        
        return 'workflow_overview'
