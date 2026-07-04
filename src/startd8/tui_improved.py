"""
Improved Interactive Terminal UI for startd8

Clear workflow: Create Prompt → Distribute to Agents → View Results
Includes agent configuration testing, API key management, and better guidance.
"""

import sys
import os
import json
from typing import Optional, List, Dict, Any, Tuple
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.markdown import Markdown
from rich import print as rprint

from .framework import AgentFramework
from .agents import MockAgent, ClaudeAgent, GPT4Agent, OpenAICompatibleAgent, ComposerAgent, BaseAgent
from .orchestration import Pipeline, WorkflowTemplates
from .workflows.builtin import DesignPolishWorkflow, CriticalReviewWorkflow, ArchitecturalReviewLogWorkflow, ConvergentReviewWorkflow
from .document_enhancement import DocumentEnhancementChain
from .iterative_workflow import IterativeDevWorkflow, IterativeWorkflowResult, save_workflow_result
from .config import ConfigManager
from .tui_help_system import HelpSystem
from .tui_workflow_help import WorkflowHelper
from .error_analysis import (
    get_last_error_from_logs,
    format_error_for_analysis,
)

# ImprovedTUI behavior is composed from topical mixins (Pass B). Each lives
# in tui/mixin_*.py; methods were moved verbatim (relative imports re-leveled).
from .tui.mixin_settings_folders import SettingsFoldersMixin
from .tui.mixin_agent_management import AgentManagementMixin
from .tui.mixin_api_keys import ApiKeyMixin
from .tui.mixin_prompt_workflow import PromptWorkflowMixin
from .tui.mixin_document_updater import DocumentUpdaterMixin
from .tui.mixin_prompt_builder_menu import PromptBuilderMixin
from .tui.mixin_job_queue_menu import JobQueueMixin
from .tui.mixin_external_tools import ExternalToolsMixin
from .tui.mixin_capdevpipe import CapDevPipeMixin
from .tui.mixin_polish import PolishMixin
from .tui.mixin_prompts_stats import PromptsStatsMixin
from .tui.mixin_iterative_workflow import IterativeWorkflowMixin
from .tui.mixin_consultation import ConsultationMixin
from .tui.mixin_enhancement_chain import EnhancementChainMixin
from .tui.mixin_readiness_review import ReadinessReviewMixin
from .tui.mixin_diagnostics import DiagnosticsMixin
from .tui.mixin_job_workflow_runners import JobWorkflowRunnersMixin
from .tui.mixin_agent_selection import AgentSelectionMixin
from .tui.mixin_model_management import ModelManagementMixin
from .paths import default_config_dir, default_data_dir
from .models import (
    DocumentEnhancementConfig,
    AgentConfig as EnhancementAgentConfig,
    ErrorHandling,
    AgentResponse
)
from .exceptions import AgentError, APIError, ConfigurationError
from .utils.file_operations import save_text_file_with_versioning

# Shared TUI primitives and self-contained helper classes were extracted to the
# `tui/` subpackage (Pass A refactor). Re-exported here so existing import paths
# (`from startd8.tui_improved import APIKeyManager`, `tui_improved.questionary`,
# `custom_style`, `select_with_filter`, ...) keep working unchanged.
from .tui import (
    HAS_QUESTIONARY,
    questionary,
    Style,
    console,
    custom_style,
    select_with_filter,
    APIKeyManager,
    CustomAgentManager,
    TourGuide,
    AgentConfigTester,
)


class ImprovedTUI(
    SettingsFoldersMixin,
    AgentManagementMixin,
    ModelManagementMixin,
    ApiKeyMixin,
    PromptWorkflowMixin,
    AgentSelectionMixin,
    DocumentUpdaterMixin,
    PromptBuilderMixin,
    JobQueueMixin,
    JobWorkflowRunnersMixin,
    ExternalToolsMixin,
    CapDevPipeMixin,
    PolishMixin,
    PromptsStatsMixin,
    IterativeWorkflowMixin,
    ConsultationMixin,
    EnhancementChainMixin,
    ReadinessReviewMixin,
    DiagnosticsMixin,
):
    """Improved Interactive TUI with clear workflows"""
    
    def __init__(self, storage_dir: Optional[Path] = None):
        """Initialize TUI"""
        if not HAS_QUESTIONARY:
            console.print(
                "[red]Error: questionary not installed.[/red]\n"
                "Install with: pip install questionary",
                style="red"
            )
            sys.exit(1)
        
        self.storage_dir = storage_dir
        
        # Initialize framework with error handling to prevent TUI crash
        try:
            self.framework = AgentFramework(storage_dir)
        except Exception as e:
            console.print(
                f"[yellow]Warning: Failed to initialize framework storage: {e}[/yellow]\n"
                "[dim]Creating new storage...[/dim]",
                style="yellow"
            )
            # Try again with a clean state
            try:
                self.framework = AgentFramework(storage_dir)
            except Exception as e2:
                console.print(
                    f"[red]Error: Could not initialize framework: {e2}[/red]\n"
                    "[dim]The TUI will continue but some features may not work.[/dim]",
                    style="red"
                )
                # Create minimal framework object to prevent attribute errors
                self.framework = None
        
        self.console = console
        self.agent_status = None
        self.current_prompt = None
        
        # Initialize API key manager and load stored keys
        try:
            self.key_manager = APIKeyManager(storage_dir)
            self.key_manager.load_all_keys()
        except Exception as e:
            console.print(f"[yellow]Warning: Failed to load API keys: {e}[/yellow]", style="yellow")
            self.key_manager = APIKeyManager(storage_dir)
        
        # Initialize custom agent manager
        try:
            self.agent_manager = CustomAgentManager(storage_dir, framework=self.framework)
        except Exception as e:
            console.print(f"[yellow]Warning: Failed to load custom agents: {e}[/yellow]", style="yellow")
            self.agent_manager = CustomAgentManager(storage_dir, framework=self.framework)
        
        # Initialize config manager
        try:
            self.config_manager = ConfigManager(storage_dir or Path.home() / ".startd8")
        except Exception as e:
            console.print(f"[yellow]Warning: Failed to load config: {e}[/yellow]", style="yellow")
            self.config_manager = ConfigManager(storage_dir or Path.home() / ".startd8")
        
        # Initialize help system
        try:
            self.help_system = HelpSystem(console=console)
        except Exception as e:
            console.print(f"[yellow]Warning: Failed to initialize help system: {e}[/yellow]", style="yellow")
            self.help_system = None
        
        # Initialize workflow help system
        try:
            self.workflow_helper = WorkflowHelper(console=console)
        except Exception as e:
            console.print(f"[yellow]Warning: Failed to initialize workflow help: {e}[/yellow]", style="yellow")
            self.workflow_helper = None

        # Initialize tour guide
        try:
            self.tour_guide = TourGuide(storage_dir)
        except Exception as e:
            console.print(f"[yellow]Warning: Failed to initialize tour guide: {e}[/yellow]", style="yellow")
            self.tour_guide = None

        # TUI settings file for tracking first-run and preferences
        self._tui_settings_file = (self.storage_dir or Path.home() / ".startd8") / "tui_settings.json"
        self._tui_settings = self._load_tui_settings()
    
    
    
    
    
    
        
    def show_header(self, subtitle: Optional[str] = None):
        """Show header with optional subtitle - using larger font styling"""
        self.console.clear()
        # Use larger, bolder styling for headers
        self.console.print("═" * 80, style="bright_cyan bold")
        self.console.print(
            "  startd8 - Multi-LLM Benchmarking System  ".center(80),
            style="bold bright_cyan"
        )
        if subtitle:
            self.console.print(subtitle.center(80), style="bold bright_cyan")
        self.console.print("═" * 80, style="bright_cyan bold")
        self.console.print()
    
    
    
    
    
    # ------------------------------------------------------------------
    # Model-list reconciliation helpers (REQ-TMM-110/120/131/132)
    # ------------------------------------------------------------------


    # ------------------------------------------------------------------
    # Manage Models menu (REQ-TMM-100/101/102/103)
    # ------------------------------------------------------------------


    
    
    
    
    
    
    
    
    
    def main_menu(self) -> str:
        """Show main menu with clearer workflow"""
        
        # Check if prompts exist to enable/disable certain options (with error handling)
        try:
            prompts = self.framework.list_prompts() if self.framework else []
        except Exception as e:
            self.console.print(f"[yellow]Warning: Could not load prompts: {e}[/yellow]")
            prompts = []
        has_prompts = len(prompts) > 0
        
        # Build dynamic menu based on current state
        choices = []
        
        # Check if there are any prompts
        prompts = self.framework.list_prompts()
        has_prompts = len(prompts) > 0
        
        # Workflow section
        choices.append(questionary.Separator("═══ WORKFLOW ═══"))
        choices.append("1️⃣  Create New Prompt")
        choices.append("📝 Prompt Builder (from templates)")
        choices.append("🔧 Enhance Prompt File")
        choices.append("📄 Document Updater")
        choices.append("🔗 Document Enhancement Chain (Multi-Agent)")
        choices.append("🚀 Run Design Pipeline (Draft → Review → Polish)")
        choices.append("✨ Design Polish Pipeline (Polish → Suggest Updates → Final Polish)")
        choices.append("🔍 Critical Review Workflow (Multi-Agent Analysis)")
        choices.append("🏛️ Architectural Review Log Workflow (Append-Only Review)")
        choices.append("🔄 Iterative Dev Workflow (Dev → Review → Fix)")
        choices.append("🗣️  Multi-Model Consultation (Prompt + Images → N Models)")
        choices.append("📥 Job Queue")
        
        if self.current_prompt:
            choices.append(f"2️⃣  Distribute Prompt to Agents (Current: {self.current_prompt.id[:12]}...)")
        elif has_prompts:
            choices.append(f"2️⃣  Distribute Prompt to Agents ({len(prompts)} prompts available)")
        else:
            choices.append("[dim]2️⃣  Distribute Prompt to Agents (create prompt first)[/dim]")
        
        if self.current_prompt or has_prompts:
            choices.append("3️⃣  View Results")
        else:
            choices.append("[dim]3️⃣  View Results (run agents first)[/dim]")
        
        # Management section
        choices.append(questionary.Separator("═══ MANAGE ═══"))
        choices.append("📋 List All Prompts")
        choices.append("🔍 Compare Prompt Responses")
        choices.append("📈 View Statistics")
        
        # Agents section (separated testing and management)
        choices.append(questionary.Separator("═══ AGENTS ═══"))
        choices.append("💬 Chat with Agent")
        choices.append("🔬 Test Agent Connections")
        choices.append("🔧 Fix Agent Configuration Issues")
        choices.append("🤖 Manage Agents")
        choices.append("🔑 Manage API Keys")
        
        # External usage tracking section
        choices.append(questionary.Separator("═══ EXTERNAL USAGE ═══"))
        choices.append("📥 Log External Usage")
        choices.append("📊 Compare SDK vs External")
        choices.append("🔧 Manage External Tools")

        # Project setup section
        choices.append(questionary.Separator("═══ PROJECT SETUP ═══"))
        choices.append("📦 Install Capability Pipeline (cap-dev-pipe)")
        choices.append("🎨 Polish App UI (apply design theme)")

        # System section
        choices.append(questionary.Separator("═══ SYSTEM ═══"))
        choices.append("🧪 Test All Agents Readiness")
        choices.append("🩺 Self-Diagnostics")
        choices.append("🛡️ Resilience Settings")
        choices.append("🔍 Analyze Last Error")
        choices.append("🔍 Analyze Agent Config Errors")
        choices.append("📁 Manage Output Folders")
        choices.append("🎓 Tour Guide")
        choices.append("❓ Help (Context)")
        choices.append("❓ Help & Guide")
        choices.append("❌ Exit")
        
        selected = questionary.select(
            "What would you like to do?",
            choices=choices,
            style=custom_style
        ).ask()
        
        # Handle contextual help option
        if selected == "❓ Help (Context)":
            if self.help_system:
                self.help_system.show_contextual_help("main_menu")
            else:
                self.console.print("[yellow]Help system unavailable.[/yellow]")
            # Re-show menu after help
            return self.main_menu()
        
        return selected
    
    


    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    # =========================================================================
    # Job Queue Methods
    # =========================================================================
    
    
    
    
    
    
    
    
    
    
    


    
    
    
    
    
    
    

    # =========================================================================
    # External Usage Tracking Methods
    # =========================================================================


    def show_help(self):
        """Show help guide using HelpSystem"""
        self.show_header("Help & Guide")
        
        if self.help_system:
            self.help_system.show_main_help()
        else:
            # Fallback if help system is unavailable
            self.console.print(Panel(
                "[bold yellow]Help system unavailable[/bold yellow]\n\n"
                "Please check that YAML configuration files are properly installed.",
                border_style="yellow",
                padding=(1, 2)
            ))
            questionary.press_any_key_to_continue("\nPress any key to continue...").ask()
    
    def run(self):
        """Run the TUI"""
        # Check for first-run setup
        self._check_first_run_setup()
        
        # Start with a quick agent connection test
        self.test_agent_connections()
        
        while True:
            self.show_header()
            choice = self.main_menu()
            
            if not choice or "Exit" in choice:
                self.console.print("\n[cyan]Goodbye![/cyan]\n")
                break
            
            if "Create New Prompt" in choice:
                self.step1_create_prompt()
            elif "Prompt Builder" in choice:
                self.prompt_builder_menu()
            elif "Enhance Prompt File" in choice:
                self.enhance_prompt_file_menu()
            elif "Document Updater" in choice:
                self.document_updater_menu()
            elif "Enhancement Chain" in choice:
                self.document_enhancement_chain_menu()
            elif "Run Design Pipeline" in choice:
                self.step2_run_design_review_chain()
            elif "Design Polish Pipeline" in choice:
                self.run_design_polish_pipeline()
            elif "Critical Review Workflow" in choice:
                self.critical_review_workflow()
            elif "Architectural Review" in choice:
                self.arc_review_workflow()
            elif "Iterative" in choice:
                self.iterative_workflow_menu()
            elif "Multi-Model Consultation" in choice:
                self.consultation_menu()
            elif "Job Queue" in choice:
                self.job_queue_menu()
            elif "Test All Agents Readiness" in choice:
                self.test_all_agents_readiness()
            elif "Self-Diagnostics" in choice:
                self.run_self_diagnostics()
            elif "Resilience Settings" in choice:
                self.configure_resilience()
            elif "Analyze Last Error" in choice:
                self.analyze_last_error_workflow()
            elif "Analyze Agent Config Errors" in choice:
                self.run_agent_config_error_analysis()
            elif "Distribute Prompt" in choice:
                if "[dim]" not in choice:  # Only if not disabled (no prompts exist)
                    self.step2_distribute_prompt()
                else:
                    self.console.print("\n[yellow]No prompts available. Create one first.[/yellow]\n")
                    questionary.press_any_key_to_continue().ask()
            elif "View Results" in choice:
                if "[dim]" not in choice:  # Only if not disabled
                    self.step3_view_results()
                else:
                    self.console.print("\n[yellow]No results to view. Create a prompt and distribute it first.[/yellow]\n")
                    questionary.press_any_key_to_continue().ask()
            elif "List All Prompts" in choice:
                self.list_all_prompts()
            elif "Compare" in choice:
                self.compare_prompts()
            elif "Statistics" in choice:
                self.show_statistics()
            elif "Chat with Agent" in choice:
                self.chat_with_agent()
            elif "Test Agent" in choice:
                self.test_agent_connections()
            elif "Fix Agent" in choice:
                # Find all non-ready agents
                custom_agents = self.agent_manager.list_agents()
                not_ready_custom = []
                for agent in custom_agents:
                    try:
                        instance = self.agent_manager.create_agent_instance(agent)
                        if not instance:
                            not_ready_custom.append(agent)
                    except Exception as e:
                        try:
                            self.agent_manager.capture_agent_error(agent, e, "creation")
                        except Exception:
                            pass
                        not_ready_custom.append(agent)
                
                if not_ready_custom:
                    self._fix_agent_configuration_issues(not_ready_custom)
                else:
                    self.console.print("[green]✓ All agents are ready![/green]")
                    questionary.press_any_key_to_continue().ask()
            elif "Manage Agents" in choice:
                self.manage_agents()
            elif "Manage API" in choice:
                self.manage_api_keys()
            elif "Manage Output Folders" in choice:
                self.manage_output_folders()
            elif "Log External Usage" in choice:
                self.log_external_usage()
            elif "Compare SDK vs External" in choice:
                self.compare_sdk_vs_external()
            elif "Manage External Tools" in choice:
                self.manage_external_tools()
            elif "cap-dev-pipe" in choice:
                self.install_capdevpipe_flow()
            elif "Polish App UI" in choice:
                self.run_polish_flow()
            elif "Tour Guide" in choice:
                if self.tour_guide:
                    self.tour_guide.show_tour_menu()
                else:
                    self.console.print("[yellow]Tour guide unavailable.[/yellow]")
                    questionary.press_any_key_to_continue().ask()
            elif "Help" in choice:
                self.show_help()

    # ------------------------------------------------------------------ #
    # cap-dev-pipe installer flow (FR-1) — thin handler over CapDevPipeInstaller
    # ------------------------------------------------------------------ #


    
    


    
    # ============================================================================
    # Iterative Dev Workflow Methods
    # ============================================================================
    
    
    
    
    
    
    
    
    
    
    
    # ============================================================================
    # Document Enhancement Chain Methods
    # ============================================================================
    
    
    
    
    
    
    
    


    
    
    
    
    


def run_improved_tui(storage_dir: Optional[Path] = None):
    """Launch the improved TUI"""
    tui = ImprovedTUI(storage_dir)
    tui.run()

