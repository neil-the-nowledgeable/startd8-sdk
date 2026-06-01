"""Shared TUI primitives: questionary detection, console, style, and helpers.

Extracted from ``tui_improved.py`` (Pass A refactor). These are foundational
symbols used by both the TUI helper classes (``TourGuide`` et al.) and the
``ImprovedTUI`` controller, so they live in the lowest layer of the ``tui``
package to keep imports acyclic.
"""

from typing import Any, List, Optional

try:
    import questionary
    from questionary import Style
    HAS_QUESTIONARY = True
except ImportError:
    HAS_QUESTIONARY = False
    questionary = None
    Style = None

from rich.console import Console


# Configure console with larger default styling
console = Console(
    width=None,  # Auto-detect terminal width
    force_terminal=True,  # Force terminal output
    legacy_windows=False,  # Use modern Windows terminal if available
    # Note: Font size is controlled by terminal settings, but we use larger/bolder styling
)


# Custom style for questionary prompts
custom_style = Style([
    ('qmark', 'fg:#5f87ff bold'),
    ('question', 'bold'),
    ('answer', 'fg:#5fff87 bold'),
    ('pointer', 'fg:#5fff87 bold'),
    ('highlighted', 'fg:#5fff87 bold'),
    ('selected', 'fg:#5fff87'),
    ('separator', 'fg:#ffffff bold'),
    ('instruction', 'fg:#888888 bold'),
]) if HAS_QUESTIONARY else None


def select_with_filter(
    message: str,
    choices: List[str],
    style: Optional[Any] = None,
    default: Optional[str] = None
) -> Optional[str]:
    """
    Select with typing filter support.

    Uses questionary.autocomplete to enable typing to filter menu choices.
    Falls back to questionary.select if autocomplete is not available.

    Args:
        message: Prompt message
        choices: List of choice strings
        style: Optional questionary Style object
        default: Optional default choice

    Returns:
        Selected choice string or None if cancelled
    """
    if not HAS_QUESTIONARY:
        console.print("[red]questionary not available[/red]")
        return None

    # Filter out Separator objects for autocomplete (they're not strings)
    string_choices = [c for c in choices if isinstance(c, str)]

    # If we have separators, use regular select (autocomplete doesn't support separators well)
    has_separators = any(not isinstance(c, str) for c in choices)

    if has_separators:
        # Use regular select for menus with separators
        return questionary.select(
            message,
            choices=choices,
            style=style,
            default=default
        ).ask()
    else:
        # Use autocomplete for filtering when no separators
        # Autocomplete allows typing to filter choices
        try:
            return questionary.autocomplete(
                message,
                choices=string_choices,
                style=style,
                default=default
            ).ask()
        except (AttributeError, TypeError):
            # Fallback to select if autocomplete fails
            return questionary.select(
                message,
                choices=choices,
                style=style,
                default=default
            ).ask()
