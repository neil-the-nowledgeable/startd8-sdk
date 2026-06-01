"""SettingsFoldersMixin: extracted from tui_improved.py ImprovedTUI (Pass B)."""

from ._shared import *  # noqa: F401,F403

class SettingsFoldersMixin:
    def _load_tui_settings(self) -> Dict[str, Any]:
        """Load TUI-specific settings"""
        if self._tui_settings_file.exists():
            try:
                with open(self._tui_settings_file, 'r') as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                pass
        return {
            'first_run_complete': False,
            'agent_folders_enabled': False,
            'agent_folders_base_dir': None
        }

    def _save_tui_settings(self):
        """Save TUI-specific settings"""
        self._tui_settings_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self._tui_settings_file, 'w') as f:
            json.dump(self._tui_settings, f, indent=2)

    def _check_first_run_setup(self):
        """Check if this is first run and offer tour guide and folder setup"""
        # Check if tour guide should be shown (separate from folder setup)
        if self.tour_guide and not self.tour_guide.has_seen_tour():
            want_tour = self.tour_guide.show_welcome_screen()
            if want_tour:
                self.tour_guide.run_full_tour()

        if self._tui_settings.get('first_run_complete'):
            # Not first run, but still ensure folders exist if enabled
            if self._tui_settings.get('agent_folders_enabled'):
                self._ensure_agent_folders_exist()
            return

        self.show_header("First-Time Setup")

        self.console.print(Panel(
            "[bold cyan]Configure Output Folders[/bold cyan]\n\n"
            "You can organize agent outputs into separate folders.\n"
            "Each agent (Claude, GPT-4, user added agents, etc.) will have\n"
            "its own subfolder to keep responses organized.\n\n"
            "[dim]Example structure:[/dim]\n"
            "  📁 ~/startd8-outputs/\n"
            "     ├── 📁 claude/\n"
            "     ├── 📁 gpt4/\n"
            "     ├── 📁 my-custom-agent/\n"
            "     └── 📁 mock/",
            border_style="cyan",
            title="📁 Output Folder Setup"
        ))

        setup_folders = questionary.confirm(
            "\nWould you like to create agent-specific output folders?",
            default=True,
            style=custom_style
        ).ask()

        if setup_folders:
            self._setup_agent_output_folders()
        else:
            self.console.print("\n[dim]Skipping folder setup. You can configure this later in settings.[/dim]\n")
            self._tui_settings['agent_folders_enabled'] = False

        self._tui_settings['first_run_complete'] = True
        self._save_tui_settings()

        questionary.press_any_key_to_continue("\nPress any key to continue...").ask()

    def _setup_agent_output_folders(self):
        """Interactive setup for agent output folders"""
        self.console.print()
        
        # Get base directory
        default_base = str(Path.home() / "startd8-outputs")
        
        base_dir = self._safe_path_input(
            "Base directory for agent outputs:",
            default=default_base,
            style=custom_style,
            only_directories=True
        )
        
        if not base_dir:
            self.console.print("[yellow]Setup cancelled.[/yellow]")
            return
        
        base_path = Path(base_dir).expanduser().resolve()
        
        # Create base directory
        try:
            base_path.mkdir(parents=True, exist_ok=True)
            self.console.print(f"\n[green]✓ Created base directory: {base_path}[/green]")
        except Exception as e:
            self.console.print(f"\n[red]Failed to create directory: {e}[/red]")
            return
        
        # Store settings
        self._tui_settings['agent_folders_enabled'] = True
        self._tui_settings['agent_folders_base_dir'] = str(base_path)
        self._save_tui_settings()
        
        # Create folders for built-in agent types
        builtin_agents = ['claude', 'gpt4', 'mock']
        
        self.console.print("\n[cyan]Creating agent folders...[/cyan]")
        
        for agent_name in builtin_agents:
            agent_folder = base_path / agent_name
            try:
                agent_folder.mkdir(exist_ok=True)
                self.console.print(f"  [green]✓[/green] {agent_folder}")
            except Exception as e:
                self.console.print(f"  [red]✗[/red] Failed to create {agent_name}: {e}")
        
        # Create folders for custom agents
        custom_agents = self.agent_manager.list_agents()
        if custom_agents:
            self.console.print("\n[cyan]Creating folders for user added agents...[/cyan]")
            for agent in custom_agents:
                agent_name = agent.get('name', '').lower().replace(' ', '-')
                if agent_name and agent_name not in builtin_agents:
                    agent_folder = base_path / agent_name
                    try:
                        agent_folder.mkdir(exist_ok=True)
                        self.console.print(f"  [green]✓[/green] {agent_folder}")
                        
                        # Update agent config with output dir if not set
                        if not agent.get('output_dir'):
                            self.agent_manager.update_agent(
                                agent.get('id'),
                                {'output_dir': str(agent_folder)}
                            )
                    except Exception as e:
                        self.console.print(f"  [red]✗[/red] Failed to create {agent_name}: {e}")
        
        self.console.print(f"\n[green]✓ Agent folders configured![/green]")
        self.console.print(f"[dim]Base directory: {base_path}[/dim]")

    def _ensure_agent_folders_exist(self):
        """Ensure agent folders exist at startup (silent operation)"""
        if not self._tui_settings.get('agent_folders_enabled'):
            return
        
        base_dir = self._tui_settings.get('agent_folders_base_dir')
        if not base_dir:
            return
        
        base_path = Path(base_dir)
        if not base_path.exists():
            try:
                base_path.mkdir(parents=True, exist_ok=True)
            except Exception:
                return
        
        # Ensure built-in agent folders exist
        for agent_name in ['claude', 'gpt4', 'mock']:
            agent_folder = base_path / agent_name
            try:
                agent_folder.mkdir(exist_ok=True)
            except Exception:
                pass
        
        # Ensure custom agent folders exist
        custom_agents = self.agent_manager.list_agents()
        for agent in custom_agents:
            agent_name = agent.get('name', '').lower().replace(' ', '-')
            if agent_name:
                agent_folder = base_path / agent_name
                try:
                    agent_folder.mkdir(exist_ok=True)
                    
                    # Update agent config with output dir if not set
                    if not agent.get('output_dir'):
                        self.agent_manager.update_agent(
                            agent.get('id'),
                            {'output_dir': str(agent_folder)}
                        )
                except Exception:
                    pass

    def _create_folder_for_new_agent(self, agent_name: str) -> Optional[str]:
        """Create output folder for a newly created agent"""
        if not self._tui_settings.get('agent_folders_enabled'):
            return None
        
        base_dir: Optional[str] = self._tui_settings.get('agent_folders_base_dir')
        if not base_dir:
            return None
        
        base_path: Path = Path(base_dir)
        folder_name: str = agent_name.lower().replace(' ', '-')
        agent_folder: Path = base_path / folder_name
        
        try:
            agent_folder.mkdir(parents=True, exist_ok=True)
            return str(agent_folder)
        except Exception:
            return None

    def manage_output_folders(self):
        """Manage agent output folder settings"""
        while True:
            self.show_header("Manage Output Folders")
            
            # Show current status
            enabled = self._tui_settings.get('agent_folders_enabled', False)
            base_dir = self._tui_settings.get('agent_folders_base_dir', '')
            
            status_text = "[green]Enabled[/green]" if enabled else "[dim]Disabled[/dim]"
            
            self.console.print(Panel(
                f"[bold]Agent Output Folders[/bold]\n\n"
                f"[bold]Status:[/bold] {status_text}\n"
                f"[bold]Base Directory:[/bold] {base_dir or '[dim]Not configured[/dim]'}\n\n"
                "[dim]When enabled, each agent gets its own subfolder for outputs.[/dim]",
                border_style="cyan"
            ))
            
            # Show existing folders if enabled
            if enabled and base_dir:
                base_path = Path(base_dir)
                if base_path.exists():
                    self.console.print("\n[bold]Existing Agent Folders:[/bold]")
                    folders = sorted([f for f in base_path.iterdir() if f.is_dir()])
                    if folders:
                        for folder in folders:
                            file_count = len(list(folder.glob('*')))
                            self.console.print(f"  📁 {folder.name}/ [dim]({file_count} files)[/dim]")
                    else:
                        self.console.print("  [dim]No folders created yet[/dim]")
                    self.console.print()
            
            # Build menu choices
            choices = []
            
            if not enabled:
                choices.append("✅ Enable Agent Folders")
            else:
                choices.append("❌ Disable Agent Folders")
                choices.append("📁 Change Base Directory")
                choices.append("➕ Create Missing Folders")
            
            choices.append("← Back to Main Menu")
            
            action = questionary.select(
                "What would you like to do?",
                choices=choices,
                style=custom_style
            ).ask()
            
            if not action or "Back" in action:
                break
            
            if "Enable" in action:
                self._setup_agent_output_folders()
            elif "Disable" in action:
                confirm = questionary.confirm(
                    "Disable agent folders? (Existing folders will not be deleted)",
                    default=False,
                    style=custom_style
                ).ask()
                
                if confirm:
                    self._tui_settings['agent_folders_enabled'] = False
                    self._save_tui_settings()
                    self.console.print("\n[yellow]Agent folders disabled.[/yellow]\n")
                    questionary.press_any_key_to_continue().ask()
            elif "Change Base" in action:
                self._change_base_directory()
            elif "Create Missing" in action:
                self._create_missing_agent_folders()

    def _change_base_directory(self):
        """Change the base directory for agent folders"""
        current = self._tui_settings.get('agent_folders_base_dir', '')
        
        new_dir = self._safe_path_input(
            "New base directory:",
            default=current,
            style=custom_style,
            only_directories=True
        )
        
        if not new_dir:
            return
        
        new_path = Path(new_dir).expanduser().resolve()
        
        # Create if doesn't exist
        try:
            new_path.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            self.console.print(f"\n[red]Failed to create directory: {e}[/red]\n")
            questionary.press_any_key_to_continue().ask()
            return
        
        # Ask about migrating existing folders
        old_dir = self._tui_settings.get('agent_folders_base_dir')
        if old_dir and Path(old_dir).exists():
            migrate = questionary.confirm(
                "Copy existing folders to new location?",
                default=True,
                style=custom_style
            ).ask()
            
            if migrate:
                import shutil
                old_path = Path(old_dir)
                for folder in old_path.iterdir():
                    if folder.is_dir():
                        try:
                            shutil.copytree(folder, new_path / folder.name, dirs_exist_ok=True)
                            self.console.print(f"  [green]✓[/green] Copied {folder.name}/")
                        except Exception as e:
                            self.console.print(f"  [red]✗[/red] Failed to copy {folder.name}: {e}")
        
        # Update settings
        self._tui_settings['agent_folders_base_dir'] = str(new_path)
        self._save_tui_settings()
        
        # Update custom agents to use new paths
        custom_agents = self.agent_manager.list_agents()
        for agent in custom_agents:
            old_output_dir = agent.get('output_dir', '')
            if old_output_dir and old_dir and old_output_dir.startswith(old_dir):
                # Update to new path
                agent_name = agent.get('name', '').lower().replace(' ', '-')
                new_output_dir = str(new_path / agent_name)
                self.agent_manager.update_agent(agent.get('id'), {'output_dir': new_output_dir})
        
        self.console.print(f"\n[green]✓ Base directory updated to: {new_path}[/green]\n")
        questionary.press_any_key_to_continue().ask()

    def _create_missing_agent_folders(self):
        """Create folders for agents that don't have them"""
        base_dir = self._tui_settings.get('agent_folders_base_dir')
        if not base_dir:
            self.console.print("\n[yellow]No base directory configured.[/yellow]\n")
            questionary.press_any_key_to_continue().ask()
            return
        
        base_path = Path(base_dir)
        created = []
        
        # Built-in agents
        for agent_name in ['claude', 'gpt4', 'mock']:
            folder = base_path / agent_name
            if not folder.exists():
                try:
                    folder.mkdir(parents=True, exist_ok=True)
                    created.append(agent_name)
                except Exception:
                    pass
        
        # Custom agents
        custom_agents = self.agent_manager.list_agents()
        for agent in custom_agents:
            agent_name = agent.get('name', '').lower().replace(' ', '-')
            if agent_name:
                folder = base_path / agent_name
                if not folder.exists():
                    try:
                        folder.mkdir(parents=True, exist_ok=True)
                        created.append(agent_name)
                        
                        # Update agent config if output_dir not set
                        if not agent.get('output_dir'):
                            self.agent_manager.update_agent(
                                agent.get('id'),
                                {'output_dir': str(folder)}
                            )
                    except Exception:
                        pass
        
        if created:
            self.console.print(f"\n[green]✓ Created {len(created)} folder(s):[/green]")
            for name in created:
                self.console.print(f"  📁 {name}/")
        else:
            self.console.print("\n[dim]All agent folders already exist.[/dim]")
        
        self.console.print()
        questionary.press_any_key_to_continue().ask()
