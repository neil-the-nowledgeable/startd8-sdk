"""ApiKeyMixin: extracted from tui_improved.py ImprovedTUI (Pass B)."""

from ._shared import *  # noqa: F401,F403

class ApiKeyMixin:
    def manage_api_keys(self):
        """Standalone API key management menu"""
        while True:
            self.show_header("Manage API Keys")
            
            # Show current key status
            table = Table(title="API Key Status", show_header=True)
            table.add_column("Provider", style="bold")
            table.add_column("Environment Variable")
            table.add_column("Status", justify="center")
            table.add_column("Source")
            
            claude_status = self.key_manager.get_key_status('ANTHROPIC_API_KEY')
            gpt4_status = self.key_manager.get_key_status('OPENAI_API_KEY')
            
            if claude_status['set']:
                table.add_row(
                    "Claude (Anthropic)",
                    "ANTHROPIC_API_KEY",
                    f"[green]✓ {claude_status['masked']}[/green]",
                    f"[cyan]{claude_status['source']}[/cyan]"
                )
            else:
                table.add_row(
                    "Claude (Anthropic)",
                    "ANTHROPIC_API_KEY",
                    "[red]✗ Not set[/red]",
                    "[dim]—[/dim]"
                )
            
            if gpt4_status['set']:
                table.add_row(
                    "GPT-4 (OpenAI)",
                    "OPENAI_API_KEY",
                    f"[green]✓ {gpt4_status['masked']}[/green]",
                    f"[cyan]{gpt4_status['source']}[/cyan]"
                )
            else:
                table.add_row(
                    "GPT-4 (OpenAI)",
                    "OPENAI_API_KEY",
                    "[red]✗ Not set[/red]",
                    "[dim]—[/dim]"
                )
            
            self.console.print(table)
            self.console.print()
            
            self.console.print(Panel(
                "[dim]API keys are stored securely in:[/dim]\n"
                f"[cyan]{self.key_manager.config_file}[/cyan]\n\n"
                "[dim]Environment variables take priority over stored keys.[/dim]",
                border_style="dim"
            ))
            
            # Build choices based on current state
            choices = []
            
            if claude_status['set']:
                choices.append(f"🔑 Update Claude API Key")
                choices.append("🗑️  Remove Claude API Key")
            else:
                choices.append("🔑 Set Claude API Key")
            
            if gpt4_status['set']:
                choices.append(f"🔑 Update GPT-4 API Key")
                choices.append("🗑️  Remove GPT-4 API Key")
            else:
                choices.append("🔑 Set GPT-4 API Key")
            
            choices.append("📤 Export API Keys (Encrypted)")
            choices.append("📥 Import API Keys (Encrypted)")
            choices.append("🔬 Test Agent Connections")
            choices.append("← Back to Main Menu")
            
            action = questionary.select(
                "API Key Management:",
                choices=choices,
                style=custom_style
            ).ask()
            
            if not action or "Back" in action:
                break
            
            if "Set Claude" in action or "Update Claude" in action:
                self._set_api_key("ANTHROPIC_API_KEY", "Claude (Anthropic)")
            elif "Remove Claude" in action:
                self._remove_api_key("ANTHROPIC_API_KEY", "Claude")
            elif "Set GPT-4" in action or "Update GPT-4" in action:
                self._set_api_key("OPENAI_API_KEY", "GPT-4 (OpenAI)")
            elif "Remove GPT-4" in action:
                self._remove_api_key("OPENAI_API_KEY", "GPT-4")
            elif "Export" in action:
                self._export_api_keys()
            elif "Import" in action:
                self._import_api_keys()
            elif "Test" in action:
                self.test_agent_connections()
                return  # Exit to main menu after test

    def _set_api_key(self, key_name: str, display_name: str):
        """Prompt user to set an API key"""
        self.console.print()
        self.console.print(Panel(
            f"[bold]Setting {display_name} API Key[/bold]\n\n"
            f"Enter your API key below. It will be:\n"
            f"  • Stored securely in [cyan]{self.key_manager.config_file}[/cyan]\n"
            f"  • Loaded automatically when you start the TUI\n"
            f"  • Used for this session immediately\n\n"
            f"[dim]Tip: You can paste your key (it won't be shown)[/dim]",
            border_style="cyan"
        ))
        
        # Get the API key (password mode hides input)
        api_key = questionary.password(
            f"Enter {key_name}:",
            style=custom_style
        ).ask()
        
        if not api_key:
            self.console.print("[yellow]Cancelled - no key set[/yellow]")
            return
        
        # Validate key format (basic check)
        if key_name == "ANTHROPIC_API_KEY" and not api_key.startswith("sk-ant-"):
            confirm = questionary.confirm(
                "Key doesn't start with 'sk-ant-'. Set anyway?",
                default=False,
                style=custom_style
            ).ask()
            if not confirm:
                return
        
        if key_name == "OPENAI_API_KEY" and not api_key.startswith("sk-"):
            confirm = questionary.confirm(
                "Key doesn't start with 'sk-'. Set anyway?",
                default=False,
                style=custom_style
            ).ask()
            if not confirm:
                return
        
        # Save the key
        self.key_manager.set_key(key_name, api_key)
        
        self.console.print(f"\n[green]✓ {display_name} API key saved![/green]")
        self.console.print(f"[dim]Stored in: {self.key_manager.config_file}[/dim]\n")
        
        # Re-test agents
        self.console.print("[cyan]Re-testing agent configuration...[/cyan]\n")
        self.agent_status = AgentConfigTester.test_all()
        
        # Show result for this agent
        agent_id = 'claude' if 'ANTHROPIC' in key_name else 'gpt4'
        status = self.agent_status[agent_id]
        
        if status['working']:
            self.console.print(f"[green]✓ {status['name']} is now operational![/green]\n")
        else:
            self.console.print(f"[yellow]⚠ {status['name']} key set but: {status['error']}[/yellow]\n")
        
        questionary.press_any_key_to_continue("Press any key...").ask()

    def _remove_api_key(self, key_name: str, display_name: str):
        """Remove an API key"""
        confirm = questionary.confirm(
            f"Remove {display_name} API key?",
            default=False,
            style=custom_style
        ).ask()
        
        if confirm:
            self.key_manager.delete_key(key_name)
            self.console.print(f"\n[green]✓ {display_name} API key removed[/green]\n")
            
            # Re-test
            self.agent_status = AgentConfigTester.test_all()
            questionary.press_any_key_to_continue("Press any key...").ask()

    def _export_api_keys(self):
        """Export API keys to encrypted file"""
        self.show_header("Export API Keys")
        
        self.console.print(Panel(
            "[bold cyan]Export API Keys (Encrypted)[/bold cyan]\n\n"
            "This will export your stored API keys to an encrypted file.\n"
            "You'll need to set a password to protect the export.\n\n"
            "[yellow]⚠️  The export file will contain your API keys![/yellow]\n"
            "[yellow]Keep it secure and delete it after importing.[/yellow]",
            border_style="cyan"
        ))
        self.console.print()
        
        # Check if any keys are stored
        config = self.key_manager._load_config()
        if not config:
            self.console.print("[yellow]No API keys stored to export.[/yellow]\n")
            questionary.press_any_key_to_continue().ask()
            return
        
        # Show keys that will be exported
        self.console.print("[bold]Keys to be exported:[/bold]")
        for key_name in config.keys():
            self.console.print(f"  • {key_name}")
        self.console.print()
        
        # Get export path
        default_path = Path.home() / "startd8_keys_export.enc"
        export_path_str = questionary.text(
            "Export file path:",
            default=str(default_path),
            style=custom_style
        ).ask()
        
        if not export_path_str:
            return
        
        export_path = Path(export_path_str).expanduser()
        
        # Check if file exists
        if export_path.exists():
            overwrite = questionary.confirm(
                f"File {export_path} already exists. Overwrite?",
                default=False,
                style=custom_style
            ).ask()
            if not overwrite:
                return
        
        # Get password (with confirmation)
        password = questionary.password(
            "Set encryption password:",
            style=custom_style
        ).ask()
        
        if not password or len(password) < 8:
            self.console.print("[red]Password must be at least 8 characters.[/red]\n")
            questionary.press_any_key_to_continue().ask()
            return
        
        password_confirm = questionary.password(
            "Confirm password:",
            style=custom_style
        ).ask()
        
        if password != password_confirm:
            self.console.print("[red]Passwords don't match.[/red]\n")
            questionary.press_any_key_to_continue().ask()
            return
        
        # Export
        self.console.print()
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=self.console
        ) as progress:
            task = progress.add_task("[cyan]Encrypting and exporting...", total=None)
            
            success = self.key_manager.export_keys(export_path, password)
            
            progress.update(task, completed=True)
        
        if success:
            self.console.print()
            self.console.print(Panel(
                f"[green]✓ API keys exported successfully![/green]\n\n"
                f"Encrypted file saved to:\n[cyan]{export_path}[/cyan]\n\n"
                f"[bold]To import on another system:[/bold]\n"
                f"1. Copy the .enc file securely\n"
                f"2. Use 'Import API Keys' in this menu\n"
                f"3. Enter the same password\n\n"
                f"[yellow]⚠️  Keep this file secure and delete after importing![/yellow]",
                title="Export Successful",
                border_style="green"
            ))
        else:
            self.console.print("[red]✗ Export failed.[/red]\n")
        
        self.console.print()
        questionary.press_any_key_to_continue().ask()

    def _import_api_keys(self):
        """Import API keys from encrypted file"""
        self.show_header("Import API Keys")
        
        self.console.print(Panel(
            "[bold cyan]Import API Keys (Encrypted)[/bold cyan]\n\n"
            "This will import API keys from an encrypted export file.\n"
            "You'll need the password that was used during export.\n\n"
            "[dim]Existing keys with the same name can be overwritten.[/dim]",
            border_style="cyan"
        ))
        self.console.print()
        
        # Get import path
        default_path = Path.home() / "startd8_keys_export.enc"
        import_path_str = questionary.text(
            "Import file path:",
            default=str(default_path),
            style=custom_style
        ).ask()
        
        if not import_path_str:
            return
        
        import_path = Path(import_path_str).expanduser()
        
        if not import_path.exists():
            self.console.print(f"[red]File not found: {import_path}[/red]\n")
            questionary.press_any_key_to_continue().ask()
            return
        
        # Get password
        password = questionary.password(
            "Enter decryption password:",
            style=custom_style
        ).ask()
        
        if not password:
            return
        
        # Ask about overwriting
        overwrite = questionary.confirm(
            "Overwrite existing keys with same name?",
            default=False,
            style=custom_style
        ).ask()
        
        # Import
        self.console.print()
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=self.console
        ) as progress:
            task = progress.add_task("[cyan]Decrypting and importing...", total=None)
            
            result = self.key_manager.import_keys(import_path, password, overwrite)
            
            progress.update(task, completed=True)
        
        self.console.print()
        
        if result['success']:
            # Show results
            if result['imported']:
                self.console.print("[green]✓ Successfully imported keys:[/green]")
                for key_name in result['imported']:
                    self.console.print(f"  [green]✓[/green] {key_name}")
                self.console.print()
            
            if result['skipped']:
                self.console.print("[yellow]Skipped (already exists):[/yellow]")
                for key_name in result['skipped']:
                    self.console.print(f"  [yellow]−[/yellow] {key_name}")
                self.console.print()
            
            if result['imported']:
                self.console.print(Panel(
                    "[green]Import completed successfully![/green]\n\n"
                    "API keys are now available for use.\n"
                    "You can test them with 'Test Agent Connections'.",
                    title="Import Successful",
                    border_style="green"
                ))
            else:
                self.console.print(Panel(
                    "[yellow]No new keys imported.[/yellow]\n\n"
                    "All keys from the export already exist.\n"
                    "Use 'overwrite' option to replace existing keys.",
                    title="Import Complete",
                    border_style="yellow"
                ))
        else:
            error_msg = result.get('error', 'Unknown error')
            if "incorrect password" in error_msg.lower():
                self.console.print(Panel(
                    "[red]✗ Incorrect password![/red]\n\n"
                    "The password you entered doesn't match the one\n"
                    "used to encrypt this export file.",
                    title="Decryption Failed",
                    border_style="red"
                ))
            else:
                self.console.print(Panel(
                    f"[red]✗ Import failed![/red]\n\n"
                    f"Error: {error_msg}",
                    title="Import Failed",
                    border_style="red"
                ))
        
        self.console.print()
        questionary.press_any_key_to_continue().ask()
