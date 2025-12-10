"""
Enhanced Interactive Terminal UI for startd8 with built-in configuration

Features:
- API key management through TUI
- Model configuration
- Clear 3-step workflow
- Agent configuration testing
"""

import sys
import os
from typing import Optional, List, Dict, Any
from pathlib import Path

try:
    import questionary
    from questionary import Style
    HAS_QUESTIONARY = True
except ImportError:
    HAS_QUESTIONARY = False
    questionary = None

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich import print as rprint

from .framework import AgentFramework
from .agents import MockAgent, ClaudeAgent, GPT4Agent, BaseAgent
from .config import get_config_manager, ConfigManager
from .orchestration import Pipeline, WorkflowTemplates


console = Console()

# Custom style
custom_style = Style([
    ('qmark', 'fg:#5f87ff bold'),
    ('question', 'bold'),
    ('answer', 'fg:#5fff87 bold'),
    ('pointer', 'fg:#5fff87 bold'),
    ('highlighted', 'fg:#5fff87 bold'),
    ('selected', 'fg:#5fff87'),
    ('separator', 'fg:#555555'),
    ('instruction', 'fg:#888888 italic'),
]) if HAS_QUESTIONARY else None


class AgentConfigTester:
    """Test agent configurations"""
    
    def __init__(self, config_manager: ConfigManager):
        self.config = config_manager
    
    def test_claude(self) -> Dict[str, Any]:
        """Test Claude configuration"""
        result = {
            'name': 'Claude',
            'configured': False,
            'working': False,
            'error': None,
            'source': None
        }
        
        # Check API key
        api_key = self.config.get_api_key('anthropic')
        if not api_key:
            result['error'] = 'API key not set'
            return result
        
        result['configured'] = True
        result['source'] = self.config.get_api_key_source('anthropic')
        
        # Try to initialize
        try:
            agent = ClaudeAgent(
                model=self.config.get_default_model('claude'),
                api_key=api_key
            )
            result['working'] = True
        except Exception as e:
            result['error'] = str(e)
        
        return result
    
    def test_gpt4(self) -> Dict[str, Any]:
        """Test GPT-4 configuration"""
        result = {
            'name': 'GPT-4',
            'configured': False,
            'working': False,
            'error': None,
            'source': None
        }
        
        # Check API key
        api_key = self.config.get_api_key('openai')
        if not api_key:
            result['error'] = 'API key not set'
            return result
        
        result['configured'] = True
        result['source'] = self.config.get_api_key_source('openai')
        
        # Try to initialize
        try:
            agent = GPT4Agent(
                model=self.config.get_default_model('gpt4'),
                api_key=api_key
            )
            result['working'] = True
        except Exception as e:
            result['error'] = str(e)
        
        return result
    
    def test_all(self) -> Dict[str, Dict[str, Any]]:
        """Test all agent configurations"""
        return {
            'claude': self.test_claude(),
            'gpt4': self.test_gpt4(),
            'mock': {
                'name': 'Mock',
                'configured': True,
                'working': True,
                'error': None,
                'source': 'built-in'
            }
        }


class EnhancedTUI:
    """Enhanced Interactive TUI with configuration management"""
    
    def __init__(self, storage_dir: Optional[Path] = None):
        """Initialize TUI"""
        if not HAS_QUESTIONARY:
            console.print(
                "[red]Error: questionary not installed.[/red]\n"
                "Install with: pip install questionary",
                style="red"
            )
            sys.exit(1)
        
        self.framework = AgentFramework(storage_dir)
        self.config = get_config_manager()
        self.tester = AgentConfigTester(self.config)
        self.console = console
        self.agent_status = None
        self.current_prompt = None
        
    def show_header(self, subtitle: Optional[str] = None):
        """Show header with optional subtitle"""
        self.console.clear()
        self.console.print("═" * 80, style="cyan")
        self.console.print(
            "  startd8 - Multi-LLM Benchmarking System  ".center(80),
            style="bold cyan"
        )
        if subtitle:
            self.console.print(subtitle.center(80), style="dim")
        self.console.print("═" * 80, style="cyan")
        self.console.print()
    
    def check_agent_configuration(self):
        """Check and display agent configuration status"""
        self.show_header("Agent Configuration Status")
        
        self.console.print("[cyan]Testing agent configurations...[/cyan]\n")
        
        self.agent_status = self.tester.test_all()
        
        # Display results
        table = Table(title="Agent Configuration Status", show_header=True)
        table.add_column("Agent", style="bold")
        table.add_column("API Key", justify="center")
        table.add_column("Source", justify="center")
        table.add_column("Status", justify="center")
        table.add_column("Details")
        
        for agent_id, status in self.agent_status.items():
            name = status['name']
            
            # API Key status
            if agent_id == 'mock':
                api_status = "[dim]N/A[/dim]"
                source = "[dim]built-in[/dim]"
            elif status['configured']:
                api_status = "[green]✓ Set[/green]"
                source_str = status.get('source', 'unknown')
                source = f"[green]{source_str}[/green]"
            else:
                api_status = "[red]✗ Missing[/red]"
                source = "[dim]-[/dim]"
            
            # Working status
            if status['working']:
                working_status = "[green]✓ Ready[/green]"
                details = "[green]Operational[/green]"
            elif status['configured']:
                working_status = "[yellow]⚠ Error[/yellow]"
                details = f"[yellow]{status['error']}[/yellow]"
            else:
                working_status = "[red]✗ Not configured[/red]"
                details = f"[red]{status['error']}[/red]"
            
            table.add_row(name, api_status, source, working_status, details)
        
        self.console.print(table)
        self.console.print()
        
        # Summary
        working_count = sum(1 for s in self.agent_status.values() if s['working'])
        
        if working_count == 0:
            self.console.print(Panel(
                "[red]⚠️  No agents configured![/red]\n\n"
                "You can use Mock agents for testing, but for real LLM responses,\n"
                "configure your API keys using the Configuration menu.\n\n"
                "[cyan]💡 Tip:[/cyan] Select '[bold]⚙️ Configure API Keys[/bold]' from the main menu.",
                title="Configuration Required",
                border_style="yellow"
            ))
        elif working_count == 1 and self.agent_status['mock']['working']:
            self.console.print(Panel(
                "[yellow]Only Mock agents available[/yellow]\n\n"
                "Mock agents are great for testing, but won't give real LLM responses.\n"
                "Configure API keys in the Configuration menu to use Claude or GPT-4.",
                title="💡 Tip",
                border_style="yellow"
            ))
        else:
            self.console.print(Panel(
                f"[green]✓ {working_count} agent type(s) available![/green]\n\n"
                "You're ready to create prompts and run benchmarks.",
                title="Ready to Go",
                border_style="green"
            ))
        
        questionary.press_any_key_to_continue("\nPress any key to continue...").ask()
    
    def main_menu(self) -> str:
        """Show main menu with clearer workflow"""
        
        # Build dynamic menu based on current state
        choices = []
        
        # Workflow section
        choices.append(questionary.Separator("═══ WORKFLOW ═══"))
        choices.append("1️⃣  Create New Prompt")
        
        if self.current_prompt:
            choices.append(f"2️⃣  Distribute Prompt to Agents (Current: {self.current_prompt.id[:12]}...)")
            choices.append("3️⃣  View Results")
        else:
            choices.append("[dim]2️⃣  Distribute Prompt to Agents (create prompt first)[/dim]")
            choices.append("[dim]3️⃣  View Results (run agents first)[/dim]")
        
        # Management section
        choices.append(questionary.Separator("═══ MANAGE ═══"))
        choices.append("📋 List All Prompts")
        choices.append("🔍 Compare Prompt Responses")
        choices.append("📈 View Statistics")
        
        # Configuration section
        choices.append(questionary.Separator("═══ CONFIGURATION ═══"))
        choices.append("🔑 Configure API Keys")
        choices.append("🤖 Configure Models")
        choices.append("⚙️  Check Agent Status")
        choices.append("💾 View/Export Config")
        
        # System section
        choices.append(questionary.Separator("═══ HELP ═══"))
        choices.append("❓ Help & Guide")
        choices.append("❌ Exit")
        
        return questionary.select(
            "What would you like to do?",
            choices=choices,
            style=custom_style,
            instruction="(Use arrow keys to navigate)"
        ).ask()
    
    def configure_api_keys(self):
        """API key configuration menu"""
        while True:
            self.show_header("API Key Configuration")
            
            # Show current status
            claude_key = self.config.get_api_key('anthropic')
            openai_key = self.config.get_api_key('openai')
            claude_source = self.config.get_api_key_source('anthropic')
            openai_source = self.config.get_api_key_source('openai')
            
            status_table = Table(title="Current API Keys")
            status_table.add_column("Provider", style="bold")
            status_table.add_column("Status", justify="center")
            status_table.add_column("Source", justify="center")
            status_table.add_column("Preview")
            
            def mask_key(key):
                if not key:
                    return "[dim]Not set[/dim]"
                return key[:10] + "..." + key[-4:] if len(key) > 14 else "***"
            
            status_table.add_row(
                "Anthropic (Claude)",
                "[green]✓ Set[/green]" if claude_key else "[red]✗ Not set[/red]",
                f"[green]{claude_source}[/green]" if claude_source else "[dim]-[/dim]",
                mask_key(claude_key)
            )
            status_table.add_row(
                "OpenAI (GPT-4)",
                "[green]✓ Set[/green]" if openai_key else "[red]✗ Not set[/red]",
                f"[green]{openai_source}[/green]" if openai_source else "[dim]-[/dim]",
                mask_key(openai_key)
            )
            
            self.console.print(status_table)
            self.console.print()
            
            # Configuration options
            choices = [
                "🔑 Set Anthropic API Key (Claude)",
                "🔑 Set OpenAI API Key (GPT-4)",
                "🧪 Test Connection",
            ]
            
            if claude_key and claude_source == 'config':
                choices.append("🗑️  Clear Anthropic API Key")
            if openai_key and openai_source == 'config':
                choices.append("🗑️  Clear OpenAI API Key")
            
            choices.append("← Back to Main Menu")
            
            action = questionary.select(
                "What would you like to do?",
                choices=choices,
                style=custom_style
            ).ask()
            
            if not action or "Back" in action:
                break
            elif "Set Anthropic" in action:
                self._set_anthropic_key()
            elif "Set OpenAI" in action:
                self._set_openai_key()
            elif "Test Connection" in action:
                self._test_connections()
            elif "Clear Anthropic" in action:
                self.config.clear_api_key('anthropic')
                self.console.print("\n[green]✓ Anthropic API key cleared from config[/green]")
                questionary.press_any_key_to_continue().ask()
            elif "Clear OpenAI" in action:
                self.config.clear_api_key('openai')
                self.console.print("\n[green]✓ OpenAI API key cleared from config[/green]")
                questionary.press_any_key_to_continue().ask()
    
    def _set_anthropic_key(self):
        """Set Anthropic API key"""
        self.console.print(Panel(
            "[bold]Anthropic API Key[/bold]\n\n"
            "Get your API key from: [cyan]https://console.anthropic.com/[/cyan]\n\n"
            "Your key should start with: [dim]sk-ant-[/dim]\n\n"
            "The key will be stored securely in:\n"
            f"[dim]{self.config.get_config_file_path()}[/dim]",
            border_style="cyan"
        ))
        
        key = questionary.password(
            "\nEnter your Anthropic API key:",
            style=custom_style
        ).ask()
        
        if not key:
            return
        
        if not key.startswith('sk-ant-'):
            self.console.print("\n[yellow]⚠️  Warning: Key doesn't start with 'sk-ant-'[/yellow]")
            confirm = questionary.confirm("Continue anyway?", default=False).ask()
            if not confirm:
                return
        
        self.config.set_api_key('anthropic', key)
        self.console.print("\n[green]✓ Anthropic API key saved successfully![/green]")
        
        # Offer to test
        if questionary.confirm("\nTest connection now?", default=True).ask():
            self._test_connections()
        else:
            questionary.press_any_key_to_continue().ask()
    
    def _set_openai_key(self):
        """Set OpenAI API key"""
        self.console.print(Panel(
            "[bold]OpenAI API Key[/bold]\n\n"
            "Get your API key from: [cyan]https://platform.openai.com/[/cyan]\n\n"
            "Your key should start with: [dim]sk-[/dim]\n\n"
            "The key will be stored securely in:\n"
            f"[dim]{self.config.get_config_file_path()}[/dim]",
            border_style="cyan"
        ))
        
        key = questionary.password(
            "\nEnter your OpenAI API key:",
            style=custom_style
        ).ask()
        
        if not key:
            return
        
        if not key.startswith('sk-'):
            self.console.print("\n[yellow]⚠️  Warning: Key doesn't start with 'sk-'[/yellow]")
            confirm = questionary.confirm("Continue anyway?", default=False).ask()
            if not confirm:
                return
        
        self.config.set_api_key('openai', key)
        self.console.print("\n[green]✓ OpenAI API key saved successfully![/green]")
        
        # Offer to test
        if questionary.confirm("\nTest connection now?", default=True).ask():
            self._test_connections()
        else:
            questionary.press_any_key_to_continue().ask()
    
    def _test_connections(self):
        """Test API connections"""
        self.console.print("\n[cyan]Testing connections...[/cyan]\n")
        
        results = self.tester.test_all()
        
        table = Table(title="Connection Test Results")
        table.add_column("Agent", style="bold")
        table.add_column("Status", justify="center")
        table.add_column("Result")
        
        for agent_id, result in results.items():
            if agent_id == 'mock':
                continue  # Skip mock for connection tests
            
            name = result['name']
            if result['working']:
                status = "[green]✓ Working[/green]"
                details = "[green]Connection successful![/green]"
            elif result['configured']:
                status = "[red]✗ Failed[/red]"
                details = f"[red]{result['error']}[/red]"
            else:
                status = "[yellow]⊘ Not configured[/yellow]"
                details = "[yellow]API key not set[/yellow]"
            
            table.add_row(name, status, details)
        
        self.console.print(table)
        questionary.press_any_key_to_continue("\nPress any key...").ask()
    
    def configure_models(self):
        """Model configuration menu"""
        while True:
            self.show_header("Model Configuration")
            
            # Show current configuration
            config_table = Table(title="Current Model Configuration")
            config_table.add_column("Agent", style="bold")
            config_table.add_column("Default Model")
            config_table.add_column("Max Tokens", justify="right")
            
            claude_model = self.config.get_default_model('claude')
            claude_tokens = self.config.get_max_tokens('claude')
            gpt4_model = self.config.get_default_model('gpt4')
            gpt4_tokens = self.config.get_max_tokens('gpt4')
            
            config_table.add_row("Claude", claude_model, str(claude_tokens))
            config_table.add_row("GPT-4", gpt4_model, str(gpt4_tokens))
            
            self.console.print(config_table)
            self.console.print()
            
            choices = [
                "🤖 Configure Claude Model",
                "🤖 Configure GPT-4 Model",
                "← Back to Main Menu"
            ]
            
            action = questionary.select(
                "What would you like to configure?",
                choices=choices,
                style=custom_style
            ).ask()
            
            if not action or "Back" in action:
                break
            elif "Claude" in action:
                self._configure_claude_model()
            elif "GPT-4" in action:
                self._configure_gpt4_model()
    
    def _configure_claude_model(self):
        """Configure Claude model"""
        self.console.print(Panel(
            "[bold]Claude Model Configuration[/bold]\n\n"
            "Available models:\n"
            "• [cyan]claude-3-opus-20240229[/cyan] - Most capable (expensive)\n"
            "• [cyan]claude-3-sonnet-20240229[/cyan] - Balanced\n"
            "• [cyan]claude-3-5-sonnet-20240620[/cyan] - Enhanced reasoning\n"
            "• [cyan]claude-3-haiku-20240307[/cyan] - Fastest (cheapest)",
            border_style="cyan"
        ))
        
        model = questionary.select(
            "\nSelect default Claude model:",
            choices=[
                "claude-3-opus-20240229",
                "claude-3-sonnet-20240229",
                "claude-3-5-sonnet-20240620",
                "claude-3-haiku-20240307",
                "← Cancel"
            ],
            style=custom_style
        ).ask()
        
        if model == "← Cancel":
            return
        
        max_tokens = questionary.text(
            "Max tokens (default: 4096):",
            default=str(self.config.get_max_tokens('claude')),
            style=custom_style
        ).ask()
        
        try:
            max_tokens = int(max_tokens)
            self.config.set_model('claude', model)
            self.config.set_max_tokens('claude', max_tokens)
            self.console.print(f"\n[green]✓ Claude configured: {model} ({max_tokens} tokens)[/green]")
        except ValueError:
            self.console.print("\n[red]✗ Invalid max tokens value[/red]")
        
        questionary.press_any_key_to_continue().ask()
    
    def _configure_gpt4_model(self):
        """Configure GPT-4 model"""
        self.console.print(Panel(
            "[bold]GPT-4 Model Configuration[/bold]\n\n"
            "Available models:\n"
            "• [cyan]gpt-4-turbo-preview[/cyan] - Latest GPT-4 Turbo\n"
            "• [cyan]gpt-4[/cyan] - Standard GPT-4\n"
            "• [cyan]gpt-4-32k[/cyan] - Extended context\n"
            "• [cyan]gpt-3.5-turbo[/cyan] - Faster, cheaper",
            border_style="cyan"
        ))
        
        model = questionary.select(
            "\nSelect default GPT-4 model:",
            choices=[
                "gpt-4-turbo-preview",
                "gpt-4",
                "gpt-4-32k",
                "gpt-3.5-turbo",
                "← Cancel"
            ],
            style=custom_style
        ).ask()
        
        if model == "← Cancel":
            return
        
        max_tokens = questionary.text(
            "Max tokens (default: 4096):",
            default=str(self.config.get_max_tokens('gpt4')),
            style=custom_style
        ).ask()
        
        try:
            max_tokens = int(max_tokens)
            self.config.set_model('gpt4', model)
            self.config.set_max_tokens('gpt4', max_tokens)
            self.console.print(f"\n[green]✓ GPT-4 configured: {model} ({max_tokens} tokens)[/green]")
        except ValueError:
            self.console.print("\n[red]✗ Invalid max tokens value[/red]")
        
        questionary.press_any_key_to_continue().ask()
    
    def view_export_config(self):
        """View and export configuration"""
        self.show_header("Configuration")
        
        config = self.config.export_config()
        
        self.console.print(Panel(
            f"[bold]Configuration File Location:[/bold]\n"
            f"{self.config.get_config_file_path()}\n\n"
            f"[bold]Configuration:[/bold]\n"
            f"```json\n"
            f"{self._format_config(config)}\n"
            f"```",
            title="Current Configuration",
            border_style="cyan",
            padding=(1, 2)
        ))
        
        choices = [
            "📄 Export to file",
            "🔄 Reset to defaults",
            "← Back"
        ]
        
        action = questionary.select(
            "\nWhat would you like to do?",
            choices=choices,
            style=custom_style
        ).ask()
        
        if "Export" in action:
            filename = questionary.text(
                "Filename:",
                default="startd8_config_export.json",
                style=custom_style
            ).ask()
            
            if filename:
                import json
                with open(filename, 'w') as f:
                    json.dump(config, f, indent=2)
                self.console.print(f"\n[green]✓ Exported to {filename}[/green]")
                questionary.press_any_key_to_continue().ask()
        
        elif "Reset" in action:
            if questionary.confirm(
                "\n⚠️  Are you sure? This will reset ALL settings to defaults.",
                default=False
            ).ask():
                self.config.reset_config()
                self.console.print("\n[green]✓ Configuration reset to defaults[/green]")
                questionary.press_any_key_to_continue().ask()
    
    def _format_config(self, config: dict) -> str:
        """Format config as readable string"""
        import json
        return json.dumps(config, indent=2)
    
    # Copy the rest of the methods from ImprovedTUI
    # (step1_create_prompt, step2_distribute_prompt, step3_view_results, etc.)
    # I'll include the key ones:
    
    def step1_create_prompt(self):
        """Step 1: Create a prompt"""
        # [Copy from ImprovedTUI - same implementation]
        pass
    
    def run(self):
        """Run the TUI"""
        # Start with configuration check
        self.check_agent_configuration()
        
        while True:
            self.show_header()
            choice = self.main_menu()
            
            if not choice or "Exit" in choice:
                self.console.print("\n[cyan]Goodbye![/cyan]\n")
                break
            
            if "Configure API Keys" in choice:
                self.configure_api_keys()
            elif "Configure Models" in choice:
                self.configure_models()
            elif "Check Agent" in choice:
                self.check_agent_configuration()
            elif "View/Export Config" in choice:
                self.view_export_config()
            # ... handle other menu items



