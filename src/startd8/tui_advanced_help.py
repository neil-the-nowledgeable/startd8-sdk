"""
Advanced Help System for startd8 TUI.

This module provides advanced help features including:
- Interactive FAQ browser with categories
- Tips & Tricks system with random tip display
- Keyboard shortcuts documentation
- Troubleshooting guide with solutions

Module Constants:
    HAS_YAML: bool - Whether PyYAML is available
    HAS_QUESTIONARY: bool - Whether questionary is available

Example:
    >>> from startd8.tui_advanced_help import AdvancedHelpSystem
    >>> help_sys = AdvancedHelpSystem()
    >>> help_sys.show_faq()
"""

import logging
import random
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

# Module logger
logger = logging.getLogger(__name__)

# Constants
BACK_OPTION: Final[str] = "← Back"
CONFIG_ENCODING: Final[str] = "utf-8"
MAX_CONTENT_LENGTH: Final[int] = 50000
MAX_ITEMS_PER_CATEGORY: Final[int] = 100

__all__ = [
    "AdvancedHelpSystem",
    "FAQ",
    "Tip",
    "Shortcut",
    "HAS_YAML",
    "HAS_QUESTIONARY",
]


def _sanitize_content(text: Optional[str], max_length: int = MAX_CONTENT_LENGTH) -> str:
    """
    Sanitize text for safe display.
    
    Args:
        text: Text to sanitize (may be None)
        max_length: Maximum allowed length
        
    Returns:
        Sanitized text safe for display
    """
    if not text:
        return ""
    if len(text) > max_length:
        text = text[:max_length] + "... [truncated]"
    return text


@dataclass
class FAQ:
    """
    Represents a single FAQ item.
    
    Attributes:
        category: FAQ category key
        id: Unique identifier within category
        question: The FAQ question
        answer: The FAQ answer
    """
    category: str
    id: str
    question: str
    answer: str


@dataclass
class Tip:
    """
    Represents a single tip.
    
    Attributes:
        category: Tip category key
        id: Unique identifier within category
        title: Tip title
        content: Tip content
    """
    category: str
    id: str
    title: str
    content: str


@dataclass
class Shortcut:
    """
    Represents a keyboard shortcut.
    
    Attributes:
        section: Shortcut section (navigation, actions, etc.)
        action: Description of what the shortcut does
        keys: List of keys for the shortcut
        context: Where this shortcut applies
    """
    section: str
    action: str
    keys: List[str] = field(default_factory=list)
    context: str = ""


class AdvancedHelpSystem:
    """
    Manages advanced help features: FAQ, tips, shortcuts, troubleshooting.
    Extends the base help system with advanced features.
    """

    def __init__(self, console: Console = None, config_dir: str = None):
        """Initialize the AdvancedHelpSystem."""
        self.console = console or Console()
        
        if config_dir is None:
            config_dir = Path(__file__).parent / "help_content"
        else:
            config_dir = Path(config_dir)
        
        self.config_dir = config_dir
        self.faqs: Dict[str, List[FAQ]] = {}
        self.tips: Dict[str, List[Tip]] = {}
        self.shortcuts: Dict[str, List[Shortcut]] = {}
        self.troubleshooting: Dict[str, List[Dict[str, Any]]] = {}
        
        # Load configurations
        self._load_advanced_help()

    def _load_advanced_help(self) -> None:
        """
        Load advanced help from YAML file with proper error handling.
        
        Handles the following error cases gracefully:
        - Missing PyYAML library
        - Missing configuration file
        - Permission errors
        - Invalid YAML syntax
        - Invalid configuration structure
        """
        if not HAS_YAML:
            logger.warning("PyYAML not installed. Advanced help unavailable.")
            return
        
        config_file = self.config_dir / "advanced_help.yaml"
        if not config_file.exists():
            logger.warning(f"Advanced help config not found: {config_file}")
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
        
        if not isinstance(data, dict):
            logger.error(f"Invalid config format in {config_file}: expected dict")
            return
        
        # Load FAQs with validation
        faq_data = data.get("faq")
        if isinstance(faq_data, dict):
            for category_key, category_data in faq_data.items():
                if not isinstance(category_data, dict):
                    continue
                
                self.faqs[category_key] = []
                questions = category_data.get("questions", [])
                
                if not isinstance(questions, list):
                    continue
                
                for q in questions[:MAX_ITEMS_PER_CATEGORY]:
                    if not isinstance(q, dict):
                        continue
                    try:
                        faq = FAQ(
                            category=str(category_key),
                            id=str(q.get("id", "")),
                            question=_sanitize_content(q.get("question", "")),
                            answer=_sanitize_content(q.get("answer", ""))
                        )
                        self.faqs[category_key].append(faq)
                    except (TypeError, ValueError) as e:
                        logger.warning(f"Error loading FAQ in {category_key}: {e}")
        
        # Load Tips with validation
        tips_data = data.get("tips")
        if isinstance(tips_data, dict):
            for category_key, category_data in tips_data.items():
                if not isinstance(category_data, dict):
                    continue
                
                self.tips[category_key] = []
                tips_list = category_data.get("tips", [])
                
                if not isinstance(tips_list, list):
                    continue
                
                for t in tips_list[:MAX_ITEMS_PER_CATEGORY]:
                    if not isinstance(t, dict):
                        continue
                    try:
                        tip = Tip(
                            category=str(category_key),
                            id=str(t.get("id", "")),
                            title=_sanitize_content(t.get("title", "")),
                            content=_sanitize_content(t.get("content", ""))
                        )
                        self.tips[category_key].append(tip)
                    except (TypeError, ValueError) as e:
                        logger.warning(f"Error loading tip in {category_key}: {e}")
        
        # Load Shortcuts with validation
        shortcuts_data = data.get("shortcuts")
        if isinstance(shortcuts_data, dict):
            for section_key, section_data in shortcuts_data.items():
                if not isinstance(section_data, dict):
                    continue
                
                self.shortcuts[section_key] = []
                shortcuts_list = section_data.get("shortcuts", [])
                
                if not isinstance(shortcuts_list, list):
                    continue
                
                for s in shortcuts_list[:MAX_ITEMS_PER_CATEGORY]:
                    if not isinstance(s, dict):
                        continue
                    try:
                        keys = s.get("keys", [])
                        if not isinstance(keys, list):
                            keys = [str(keys)] if keys else []
                        
                        shortcut = Shortcut(
                            section=str(section_key),
                            action=_sanitize_content(s.get("action", "")),
                            keys=[str(k) for k in keys],
                            context=_sanitize_content(s.get("context", ""))
                        )
                        self.shortcuts[section_key].append(shortcut)
                    except (TypeError, ValueError) as e:
                        logger.warning(f"Error loading shortcut in {section_key}: {e}")
        
        # Load Troubleshooting with validation
        troubleshooting_data = data.get("troubleshooting")
        if isinstance(troubleshooting_data, dict):
            for category_key, category_data in troubleshooting_data.items():
                if not isinstance(category_data, dict):
                    continue
                
                problems = category_data.get("problems", [])
                if isinstance(problems, list):
                    # Sanitize problem content
                    sanitized_problems = []
                    for p in problems[:MAX_ITEMS_PER_CATEGORY]:
                        if isinstance(p, dict):
                            sanitized_problems.append({
                                "issue": _sanitize_content(p.get("issue", "")),
                                "solutions": [
                                    _sanitize_content(str(s)) 
                                    for s in p.get("solutions", [])[:20]
                                ]
                            })
                    self.troubleshooting[category_key] = sanitized_problems

    def show_faq(self) -> None:
        """Interactive FAQ browser."""
        if not self.faqs:
            self.console.print("[yellow]No FAQs available.[/yellow]")
            return
        
        while True:
            # Show categories
            categories = list(self.faqs.keys())
            category_display = [f"📚 {cat.replace('_', ' ').title()}" for cat in categories]
            category_display.append(BACK_OPTION)
            
            if not HAS_QUESTIONARY:
                self.console.print("[yellow]Questionary not available[/yellow]")
                return
            
            selected = questionary.select(
                "Select FAQ category:",
                choices=category_display,
                use_shortcuts=False
            ).ask()
            
            if not selected or BACK_OPTION in selected:
                break
            
            # Find selected category
            category_idx = category_display.index(selected) if selected in category_display else -1
            if category_idx >= 0 and category_idx < len(categories):
                category = categories[category_idx]
                self._show_faq_questions(category)

    def _show_faq_questions(self, category: str) -> None:
        """Show questions for a FAQ category."""
        if category not in self.faqs:
            return
        
        faqs = self.faqs[category]
        if not faqs:
            self.console.print("[yellow]No questions in this category.[/yellow]")
            return
        
        while True:
            questions = [f"❓ {faq.question}" for faq in faqs]
            questions.append(BACK_OPTION)
            
            selected = questionary.select(
                "Select a question:",
                choices=questions,
                use_shortcuts=False
            ).ask()
            
            if not selected or BACK_OPTION in selected:
                break
            
            # Find and show answer
            q_idx = questions.index(selected) if selected in questions else -1
            if q_idx >= 0 and q_idx < len(faqs):
                faq = faqs[q_idx]
                self.console.print(Panel(
                    faq.answer,
                    title=f"❓ {faq.question[:50]}...",
                    border_style="cyan",
                    padding=(1, 2)
                ))
                
                if HAS_QUESTIONARY:
                    questionary.press_any_key_to_continue("\nPress any key to continue...").ask()

    def show_tips(self, max_tips: int = 1, random_select: bool = True) -> None:
        """Display tips (tip of the day or selection)."""
        if not self.tips:
            self.console.print("[yellow]No tips available.[/yellow]")
            return
        
        # Flatten all tips
        all_tips = []
        for category_tips in self.tips.values():
            all_tips.extend(category_tips)
        
        if not all_tips:
            return
        
        if random_select:
            # Show random tip(s)
            selected_tips = random.sample(all_tips, min(max_tips, len(all_tips)))
        else:
            # Show first tips
            selected_tips = all_tips[:max_tips]
        
        for tip in selected_tips:
            self.console.print(Panel(
                f"💡 [bold]{tip.title}[/bold]\n\n{tip.content}",
                border_style="yellow",
                padding=(1, 2)
            ))
            self.console.print()

    def show_keyboard_shortcuts(self) -> None:
        """Display keyboard shortcuts table."""
        if not self.shortcuts:
            self.console.print("[yellow]No shortcuts available.[/yellow]")
            return
        
        # Build table for each section
        for section_key, shortcuts in self.shortcuts.items():
            if not shortcuts:
                continue
            
            table = Table(
                title=f"Keyboard Shortcuts - {section_key.replace('_', ' ').title()}",
                show_header=True
            )
            table.add_column("Action", style="cyan")
            table.add_column("Keys", style="yellow")
            table.add_column("Context", style="dim")
            
            for shortcut in shortcuts:
                keys_str = " + ".join(shortcut.keys) if isinstance(shortcut.keys, list) else shortcut.keys
                table.add_row(shortcut.action, keys_str, shortcut.context)
            
            self.console.print(Panel(table, padding=(1, 2)))

    def show_troubleshooting(self) -> None:
        """Interactive troubleshooting guide."""
        if not self.troubleshooting:
            self.console.print("[yellow]No troubleshooting guides available.[/yellow]")
            return
        
        while True:
            categories = list(self.troubleshooting.keys())
            category_display = [f"🔧 {cat.replace('_', ' ').title()}" for cat in categories]
            category_display.append(BACK_OPTION)
            
            if not HAS_QUESTIONARY:
                self.console.print("[yellow]Questionary not available[/yellow]")
                return
            
            selected = questionary.select(
                "What problem are you experiencing?",
                choices=category_display,
                use_shortcuts=False
            ).ask()
            
            if not selected or BACK_OPTION in selected:
                break
            
            # Find selected category
            category_idx = category_display.index(selected) if selected in category_display else -1
            if category_idx >= 0 and category_idx < len(categories):
                category = categories[category_idx]
                self._show_troubleshooting_solutions(category)

    def _show_troubleshooting_solutions(self, category: str) -> None:
        """Show troubleshooting solutions for a category."""
        if category not in self.troubleshooting:
            return
        
        problems = self.troubleshooting[category]
        if not problems:
            self.console.print("[yellow]No problems in this category.[/yellow]")
            return
        
        for problem in problems:
            issue = problem.get("issue", "")
            solutions = problem.get("solutions", [])
            
            solutions_text = "\n".join([f"  • {sol}" for sol in solutions])
            
            self.console.print(Panel(
                f"[bold]{issue}[/bold]\n\n{solutions_text}",
                title="🔧 Solution",
                border_style="green",
                padding=(1, 2)
            ))
            self.console.print()
            
            if HAS_QUESTIONARY:
                cont = questionary.confirm(
                    "Continue to next solution?",
                    default=True
                ).ask()
                
                if not cont:
                    break

    def get_random_tip(self) -> Optional[Tip]:
        """Get a random tip for display."""
        all_tips = []
        for category_tips in self.tips.values():
            all_tips.extend(category_tips)
        
        if not all_tips:
            return None
        
        return random.choice(all_tips)

    def get_faq_categories(self) -> List[str]:
        """Get all FAQ categories."""
        return list(self.faqs.keys())

    def get_tip_categories(self) -> List[str]:
        """Get all tip categories."""
        return list(self.tips.keys())

    def validate_configuration(self) -> Dict[str, Any]:
        """Validate advanced help configuration."""
        # Count items
        faq_count = sum(len(faqs) for faqs in self.faqs.values())
        tip_count = sum(len(tips) for tips in self.tips.values())
        shortcut_count = sum(len(shortcuts) for shortcuts in self.shortcuts.values())
        problem_count = sum(len(problems) for problems in self.troubleshooting.values())
        
        return {
            "faqs_loaded": len(self.faqs) > 0,
            "tips_loaded": len(self.tips) > 0,
            "shortcuts_loaded": len(self.shortcuts) > 0,
            "troubleshooting_loaded": len(self.troubleshooting) > 0,
            "faq_count": faq_count,
            "tips_count": tip_count,
            "shortcuts_count": shortcut_count,
            "problems_count": problem_count,
            "yaml_available": HAS_YAML,
            "questionary_available": HAS_QUESTIONARY,
            "config_directory": str(self.config_dir),
            "config_directory_exists": self.config_dir.exists()
        }
