"""Interactive tour guide for first-time and returning users.

Extracted verbatim from ``tui_improved.py`` (Pass A refactor).
"""

import json
from typing import Optional, Dict, Any
from pathlib import Path
from ..paths import default_config_dir

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.markdown import Markdown

from .widgets import HAS_QUESTIONARY, questionary, custom_style


class TourGuide:
    """
    Interactive tour guide for first-time and returning users.

    Provides orientation to startd8's capabilities, value proposition,
    and key workflows.
    """

    TOUR_SEEN_FILE = "tour_completed.json"

    # Tour content organized by sections
    TOUR_SECTIONS = [
        {
            "id": "welcome",
            "title": "Welcome to Startd8",
            "icon": "rocket",
            "content": """
**Startd8** is your unified command center for working with multiple AI models.

**Core Value:** Compare, benchmark, and orchestrate Claude, GPT-4, Gemini,
and local models (Ollama) - all from one interface.

**Key Benefits:**
- **No vendor lock-in** - Switch between providers seamlessly
- **Cost visibility** - Track spending across all providers
- **Better outputs** - Run the same prompt on multiple models, pick the best
- **Automated workflows** - Chain agents for complex tasks
            """,
        },
        {
            "id": "agents",
            "title": "Meet Your Agents",
            "icon": "robot",
            "content": """
**Agents** are your AI assistants. Each agent connects to a specific model:

| Agent | Provider | Best For |
|-------|----------|----------|
| **Claude** | Anthropic | Complex reasoning, long documents |
| **GPT-4** | OpenAI | General tasks, code generation |
| **Gemini** | Google | Multimodal, fast responses |
| **Ollama** | Local | Privacy, offline use, experimentation |
| **Mock** | Built-in | Testing workflows without API costs |

**Quick Actions:**
- **Chat with Agent** - Direct conversation with any ready agent
- **Test Connections** - Verify which agents are configured
- **Manage API Keys** - Set up your provider credentials
            """,
        },
        {
            "id": "workflows",
            "title": "Powerful Workflows",
            "icon": "workflow",
            "content": """
**Startd8 shines with multi-agent workflows:**

**1. Prompt Distribution**
   Create once, run on multiple agents, compare results side-by-side.

**2. Design Pipeline** (Draft → Review → Polish)
   - Agent 1 drafts the document
   - Agent 2 reviews and critiques
   - Agent 3 polishes the final version

**3. Document Enhancement Chain**
   Pass a document through multiple agents sequentially,
   each one improving on the previous output.

**4. Iterative Development**
   Dev → Review → Fix cycle for code and documents.

**5. Critical Review Workflow**
   Multiple agents analyze from different perspectives.
            """,
        },
        {
            "id": "prompts",
            "title": "Prompt Management",
            "icon": "document",
            "content": """
**Version control for your prompts:**

- **Create & Save** - Store prompts with versions and tags
- **Template Library** - Start from proven templates
- **Prompt Builder** - Wizard for structured prompts
- **History** - Track changes, revert if needed

**Prompt Distribution:**
1. Create a prompt
2. Select agents (all, specific, or undistributed)
3. Compare responses
4. Save the best output

**Pro tip:** Use the Mock agent first to test your workflow
without incurring API costs.
            """,
        },
        {
            "id": "costs",
            "title": "Cost Tracking",
            "icon": "dollar",
            "content": """
**Know exactly what you're spending:**

- **Per-request tracking** - See costs for every API call
- **Provider breakdown** - Compare costs across providers
- **Budget alerts** - Set spending limits
- **Analytics** - Visualize usage patterns

**Cost-Saving Tips:**
1. Use Mock agent for workflow testing
2. Compare model costs before choosing
3. Set project budgets
4. Use Ollama for local inference (free!)
            """,
        },
        {
            "id": "getting_started",
            "title": "Quick Start Guide",
            "icon": "rocket",
            "content": """
**Get started in 3 steps:**

**Step 1: Configure an Agent**
   → Go to **Manage API Keys**
   → Add your Anthropic, OpenAI, or Google API key
   → Test the connection

**Step 2: Chat or Create a Prompt**
   → **Chat with Agent** for quick questions
   → **Create New Prompt** for saved/versioned work

**Step 3: Compare & Iterate**
   → Distribute prompt to multiple agents
   → Compare responses
   → Use design pipelines for complex tasks

**Keyboard shortcuts:**
- ↑/↓ Navigate menus
- Enter Select option
- Ctrl+C Cancel/Exit
            """,
        },
    ]

    # Quick highlights for returning users
    HIGHLIGHTS = [
        ("Chat with Agent", "Direct conversation with any configured AI"),
        ("Design Pipeline", "Draft → Review → Polish workflow"),
        ("Cost Tracking", "Monitor API spending in real-time"),
        ("Prompt Templates", "Start from proven prompt structures"),
        ("Multi-Agent Comparison", "Run same prompt on all agents"),
        ("Document Enhancement", "Chain agents to improve documents"),
        ("Local Models", "Use Ollama for free, private inference"),
        ("Job Queue", "Batch process multiple prompts"),
    ]

    def __init__(self, storage_dir: Optional[Path] = None):
        """Initialize tour guide"""
        if storage_dir is None:
            storage_dir = default_config_dir()
        self.storage_dir = Path(storage_dir)
        self.config_file = self.storage_dir / self.TOUR_SEEN_FILE
        self.console = Console()

    def _load_tour_state(self) -> Dict[str, Any]:
        """Load tour completion state"""
        if not self.config_file.exists():
            return {"completed": False, "version": None, "last_seen": None}
        try:
            with open(self.config_file, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return {"completed": False, "version": None, "last_seen": None}

    def _save_tour_state(self, state: Dict[str, Any]):
        """Save tour completion state"""
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        with open(self.config_file, 'w') as f:
            json.dump(state, f, indent=2)

    def has_seen_tour(self) -> bool:
        """Check if user has completed the tour"""
        state = self._load_tour_state()
        return state.get("completed", False)

    def mark_tour_complete(self):
        """Mark tour as completed"""
        from datetime import datetime
        state = self._load_tour_state()
        state["completed"] = True
        state["version"] = "1.0"
        state["last_seen"] = datetime.now().isoformat()
        self._save_tour_state(state)

    def reset_tour(self):
        """Reset tour state (for testing or re-viewing)"""
        if self.config_file.exists():
            self.config_file.unlink()

    def _get_icon(self, icon_name: str) -> str:
        """Get emoji for icon name"""
        icons = {
            "rocket": "🚀",
            "robot": "🤖",
            "workflow": "🔄",
            "document": "📄",
            "dollar": "💰",
            "star": "⭐",
            "check": "✅",
            "arrow": "➡️",
        }
        return icons.get(icon_name, "•")

    def show_welcome_screen(self) -> bool:
        """
        Show welcome screen for first-time users.
        Returns True if user wants to take the tour.
        """
        self.console.print()
        self.console.print(Panel(
            "[bold cyan]Welcome to Startd8![/bold cyan]\n\n"
            "Your unified interface for AI model comparison and orchestration.\n\n"
            "[dim]Compare Claude, GPT-4, Gemini, and local models in one place.[/dim]\n\n"
            "Would you like a quick tour of the key features?",
            title="🚀 First Time Setup",
            border_style="cyan",
            padding=(1, 2)
        ))

        if not HAS_QUESTIONARY:
            return False

        choice = questionary.select(
            "Choose an option:",
            choices=[
                "📚 Yes, show me around (recommended)",
                "⚡ Skip tour - I'll explore on my own",
                "📋 Just show me the highlights",
            ],
            style=custom_style
        ).ask()

        if not choice:
            return False

        if "Yes" in choice:
            return True
        elif "highlights" in choice:
            self.show_highlights()
            self.mark_tour_complete()
            return False
        else:
            self.mark_tour_complete()
            return False

    def show_highlights(self):
        """Show quick highlights for returning users"""
        self.console.print()

        table = Table(
            title="⭐ Startd8 Highlights",
            show_header=True,
            header_style="bold cyan",
            border_style="cyan",
            padding=(0, 1)
        )
        table.add_column("Feature", style="bold")
        table.add_column("Description")

        for feature, description in self.HIGHLIGHTS:
            table.add_row(feature, description)

        self.console.print(table)
        self.console.print()

        if HAS_QUESTIONARY:
            questionary.press_any_key_to_continue(
                "\nPress any key to continue..."
            ).ask()

    def run_full_tour(self):
        """Run the complete interactive tour"""
        total_sections = len(self.TOUR_SECTIONS)

        for i, section in enumerate(self.TOUR_SECTIONS, 1):
            self.console.print()

            # Progress indicator
            progress_bar = "━" * i + "┅" * (total_sections - i)
            self.console.print(
                f"[dim]Tour Progress: [{progress_bar}] {i}/{total_sections}[/dim]"
            )

            # Section content
            icon = self._get_icon(section.get("icon", "star"))
            self.console.print(Panel(
                Markdown(section["content"].strip()),
                title=f"{icon} {section['title']}",
                border_style="cyan",
                padding=(1, 2)
            ))

            if not HAS_QUESTIONARY:
                continue

            # Navigation
            if i < total_sections:
                choice = questionary.select(
                    "Navigation:",
                    choices=[
                        "➡️  Next",
                        "⏭️  Skip to end",
                        "❌ Exit tour",
                    ],
                    style=custom_style
                ).ask()

                if not choice or "Exit" in choice:
                    self.console.print("\n[yellow]Tour ended early. You can restart anytime from the Help menu.[/yellow]")
                    return
                elif "Skip" in choice:
                    break
            else:
                questionary.press_any_key_to_continue(
                    "\nPress any key to finish the tour..."
                ).ask()

        # Tour complete
        self.mark_tour_complete()
        self.console.print()
        self.console.print(Panel(
            "[bold green]Tour Complete![/bold green]\n\n"
            "You're ready to start using Startd8.\n\n"
            "[bold]Suggested first steps:[/bold]\n"
            "1. Configure an API key (🔑 Manage API Keys)\n"
            "2. Test agent connections (🔬 Test Agent Connections)\n"
            "3. Try chatting with an agent (💬 Chat with Agent)\n\n"
            "[dim]Tip: You can revisit this tour anytime from Help menu.[/dim]",
            title="✅ Ready to Go",
            border_style="green",
            padding=(1, 2)
        ))

        if HAS_QUESTIONARY:
            questionary.press_any_key_to_continue(
                "\nPress any key to continue to the main menu..."
            ).ask()

    def show_tour_menu(self):
        """Show tour options menu for returning users"""
        self.console.print()

        if not HAS_QUESTIONARY:
            self.show_highlights()
            return

        choice = questionary.select(
            "Tour Guide Options:",
            choices=[
                "📚 Take the full tour",
                "📋 Quick highlights",
                "🔄 Reset tour (show welcome on next start)",
                "← Back to menu",
            ],
            style=custom_style
        ).ask()

        if not choice or "Back" in choice:
            return
        elif "full tour" in choice:
            self.run_full_tour()
        elif "highlights" in choice:
            self.show_highlights()
        elif "Reset" in choice:
            self.reset_tour()
            self.console.print("[green]✓ Tour reset. You'll see the welcome screen on next start.[/green]")
            if HAS_QUESTIONARY:
                questionary.press_any_key_to_continue().ask()
