"""AgentManagementMixin: extracted from tui_improved.py ImprovedTUI (Pass B)."""

from ._shared import *  # noqa: F401,F403

class AgentManagementMixin:
    def test_agent_connections(self):
        """Test and display agent connection status (testing only, no management) with pagination"""
        self.show_header("Test Agent Connections")
        
        self.console.print("[cyan]Testing agent configurations...[/cyan]\n")
        
        self.agent_status = AgentConfigTester.test_all()
        
        # Get config settings
        show_mock = self.config_manager._config.get('tui', {}).get('show_mock_agent', False)
        agents_per_page = self.config_manager._config.get('tui', {}).get('agents_per_page', 10)
        
        # Also test custom agents
        custom_agents = self.agent_manager.list_agents()
        
        # Build list of all agent rows
        key_mapping = {
            'claude': 'ANTHROPIC_API_KEY',
            'gpt4': 'OPENAI_API_KEY',
        }
        
        agent_rows = []
        
        # Add built-in agents (filter mock if config says so)
        for agent_id, status in self.agent_status.items():
            # Skip mock agent if config says to hide it
            if agent_id == 'mock' and not show_mock:
                continue
                
            name = status['name']
            agent_type = "[blue]Built-in[/blue]"
            
            # API Key status with source
            if agent_id == 'mock':
                model_or_key = "[dim]N/A[/dim]"
                source = "[dim]N/A[/dim]"
            else:
                key_name = key_mapping.get(agent_id)
                key_status = self.key_manager.get_key_status(key_name)
                
                if key_status['set']:
                    # Truncate masked key for better display (show first 8 chars + ... + last 4)
                    masked = key_status['masked']
                    if len(masked) > 20:
                        masked = masked[:8] + "..." + masked[-4:]
                    model_or_key = f"[green]✓ {masked}[/green]"
                    source = f"[cyan]{key_status['source']}[/cyan]"
                else:
                    model_or_key = "[red]✗ Missing[/red]"
                    source = "[dim]—[/dim]"
            
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
            
            agent_rows.append((name, agent_type, model_or_key, source, working_status, details, status['working']))
        
        # Add custom agents
        for agent in custom_agents:
            name = agent.get('name', 'unnamed')
            agent_type = "[magenta]User added[/magenta]"
            model = agent.get('model', 'default')
            source = "[cyan]config[/cyan]"
            
            # Test custom agent
            is_working = False
            try:
                instance = self.agent_manager.create_agent_instance(agent)
                if instance:
                    working_status = "[green]✓ Ready[/green]"
                    details = f"[green]{agent.get('type', 'unknown')} agent[/green]"
                    is_working = True
                else:
                    working_status = "[red]✗ Invalid[/red]"
                    # Provide more helpful error message
                    agent_type = agent.get('type', 'unknown')
                    if agent_type not in ['claude', 'gpt4', 'openai_compatible', 'mock', 'provider']:
                        details = f"[red]Invalid type: '{agent_type}' (must be claude, gpt4, openai_compatible, mock, or provider)[/red]"
                    else:
                        details = "[red]Invalid configuration (check model name and settings)[/red]"
            except Exception as e:
                working_status = "[yellow]⚠ Error[/yellow]"
                error_msg = str(e)[:60]
                details = f"[yellow]{error_msg}[/yellow]"
            
            agent_rows.append((name, agent_type, model, source, working_status, details, is_working))
        
        # Display agents with pagination
        total_agents = len(agent_rows)
        total_pages = (total_agents + agents_per_page - 1) // agents_per_page if total_agents > 0 else 1
        current_page = 1
        
        while True:
            # Calculate page range
            start_idx = (current_page - 1) * agents_per_page
            end_idx = min(start_idx + agents_per_page, total_agents)
            page_rows = agent_rows[start_idx:end_idx]
            
            # Create table for current page
            title = f"Agent Status ({total_agents} agents)"
            if total_pages > 1:
                title += f" - Page {current_page}/{total_pages}"
            
            table = Table(title=title, show_header=True, box=None)
            table.add_column("Agent", style="bold cyan", width=20)
            table.add_column("Type", justify="center", width=12)
            table.add_column("Model/Key", justify="left", width=25)
            table.add_column("Source", justify="center", width=15)
            table.add_column("Status", justify="center", width=12)
            table.add_column("Details", width=30)
            
            for row in page_rows:
                table.add_row(row[0], row[1], row[2], row[3], row[4], row[5])
            
            self.console.print(table)
            self.console.print()
            
            # Summary (only on first page or if single page)
            if current_page == 1:
                working_count = sum(1 for row in agent_rows if row[6])
                
                if working_count == 0:
                    self.console.print(Panel(
                        "[red]⚠️  No agents configured![/red]\n\n"
                        "Use [cyan]🔑 Manage API Keys[/cyan] to set up API keys.\n"
                        "Use [cyan]🤖 Manage Agents[/cyan] to create user added agents.",
                        title="Configuration Required",
                        border_style="yellow"
                    ))
                else:
                    # Count by type
                    working_builtin = sum(1 for agent_id, status in self.agent_status.items() 
                                        if status['working'] and (show_mock or agent_id != 'mock'))
                    working_custom = sum(1 for row in agent_rows[len([a for a in self.agent_status.items() if show_mock or a[0] != 'mock']):] if row[6])
                    
                    msg = f"[green]✓ {working_count} of {total_agents} agent(s) ready![/green]"
                    if working_builtin > 0:
                        msg += f"\n  • {working_builtin} built-in"
                    if working_custom > 0:
                        msg += f"\n  • {working_custom} user added"
                    msg += "\n\nYou're ready to create prompts and run benchmarks."
                    
                    self.console.print(Panel(msg, title="Ready to Go", border_style="green"))
                self.console.print()
            
            # Pagination controls
            if total_pages > 1:
                choices = []
                if current_page < total_pages:
                    choices.append("Next Page")
                if current_page > 1:
                    choices.append("Previous Page")
                choices.append("Done")
                
                action = questionary.select(
                    "Navigation:",
                    choices=choices,
                    style=custom_style
                ).ask()
                
                if action == "Next Page":
                    current_page += 1
                    self.show_header("Test Agent Connections")
                elif action == "Previous Page":
                    current_page -= 1
                    self.show_header("Test Agent Connections")
                else:
                    break
            else:
                questionary.press_any_key_to_continue("\nPress any key to continue...").ask()
                break

    def manage_agents(self):
        """Manage custom agents - add, edit, delete"""
        while True:
            self.show_header("Manage Agents")
            
            # List current custom agents
            custom_agents = self.agent_manager.list_agents()
            
            if custom_agents:
                table = Table(title=f"User Added Agents ({len(custom_agents)})", show_header=True)
                table.add_column("ID", style="dim")
                table.add_column("Name", style="bold cyan")
                table.add_column("Type", style="magenta")
                table.add_column("Model", style="bright_white")
                table.add_column("Max Tokens", justify="right")
                table.add_column("Output Dir", style="green", no_wrap=False)
                
                for agent in custom_agents:
                    output_dir = agent.get('output_dir', '')
                    # Show full path - Rich will wrap it automatically
                    output_display = output_dir or "[dim]default[/dim]"
                    table.add_row(
                        agent.get('id', '-')[:8],
                        agent.get('name', 'unnamed'),
                        agent.get('type', 'unknown'),
                        agent.get('model', 'default'),
                        str(agent.get('max_tokens', '-')),
                        output_display
                    )
                
                self.console.print(table)
            else:
                self.console.print(Panel(
                    "[dim]No user added agents configured yet.[/dim]\n\n"
                    "User added agents let you create different configurations\n"
                    "of Claude or GPT-4 with specific models and settings.",
                    title="No User Added Agents",
                    border_style="dim"
                ))
            
            self.console.print()
            
            # Build menu choices
            choices = [
                "➕ Add New Agent",
            ]
            
            if custom_agents:
                choices.extend([
                    "✏️  Edit Agent",
                    "🗑️  Delete Agent",
                ])
            
            choices.extend([
                "🔄 Refresh Available Models",
                "📋 Manage Models",
                "🔬 Test All Agents",
                "← Back to Main Menu"
            ])
            
            action = questionary.select(
                "Agent Management:",
                choices=choices,
                style=custom_style
            ).ask()
            
            if not action or "Back" in action:
                break
            
            if "Add New" in action:
                self._add_new_agent()
            elif "Edit" in action:
                self._edit_agent(custom_agents)
            elif "Delete" in action:
                self._delete_agent(custom_agents)
            elif "Refresh" in action:
                self._refresh_available_models()
            elif "Manage Models" in action:
                self._manage_models()
            elif "Test" in action:
                self.test_agent_connections()

    def _add_new_agent(self):
        """Add a new custom agent"""
        self.console.print()
        self.console.print(Panel(
            "[bold]Create User Added Agent[/bold]\n\n"
            "User added agents let you:\n"
            "  • Use specific models (e.g., claude-3-opus, gpt-4o)\n"
            "  • Connect to other providers (Cursor, Ollama, Groq, etc.)\n"
            "  • Set custom max tokens\n"
            "  • Set a custom output directory for agent responses\n"
            "  • Give meaningful names for easy identification",
            border_style="cyan"
        ))
        
        # First, choose category
        category = questionary.select(
            "\nWhat type of agent do you want to create?",
            choices=[
                questionary.Separator("─── Built-in Providers ───"),
                "🔵 Claude (Anthropic)",
                "🟢 GPT-4 / OpenAI",
                "🧪 Mock (for testing)",
                questionary.Separator("─── OpenAI-Compatible APIs ───"),
                "⚡ Cursor",
                "🦙 Ollama (Local)",
                "🚀 Groq",
                "🌐 Together AI",
                "🔀 OpenRouter",
                "⚙️  Custom Endpoint",
                questionary.Separator("───────────────────────"),
                "← Cancel"
            ],
            style=custom_style
        ).ask()
        
        if not category or "Cancel" in category:
            return
        
        # Map selection to type and preset
        agent_config = {}
        
        if "Claude" in category:
            agent_config = self._configure_builtin_agent('claude')
        elif "GPT-4" in category or "OpenAI" in category:
            agent_config = self._configure_builtin_agent('gpt4')
        elif "Mock" in category:
            agent_config = self._configure_builtin_agent('mock')
        elif "Cursor" in category:
            agent_config = self._configure_openai_compatible('cursor')
        elif "Ollama" in category:
            agent_config = self._configure_openai_compatible('ollama')
        elif "Groq" in category:
            agent_config = self._configure_openai_compatible('groq')
        elif "Together" in category:
            agent_config = self._configure_openai_compatible('together')
        elif "OpenRouter" in category:
            agent_config = self._configure_openai_compatible('openrouter')
        elif "Custom" in category:
            agent_config = self._configure_openai_compatible('custom')
        
        if not agent_config:
            return
        
        # Auto-create output folder if feature is enabled and no output_dir set
        if not agent_config.get('output_dir') and self._tui_settings.get('agent_folders_enabled'):
            auto_folder = self._create_folder_for_new_agent(agent_config.get('name', 'agent'))
            if auto_folder:
                agent_config['output_dir'] = auto_folder
                self.console.print(f"\n[dim]Auto-created output folder: {auto_folder}[/dim]")
        
        # Save agent
        agent_id = self.agent_manager.add_agent(agent_config)
        
        self.console.print()
        self.console.print(Panel(
            f"[green]✓ Agent created successfully![/green]\n\n"
            f"[bold]ID:[/bold] {agent_id}\n"
            f"[bold]Name:[/bold] {agent_config.get('name')}\n"
            f"[bold]Type:[/bold] {agent_config.get('type')}\n"
            f"[bold]Model:[/bold] {agent_config.get('model')}\n"
            + (f"[bold]Base URL:[/bold] {agent_config.get('base_url')}\n" if agent_config.get('base_url') else "")
            + (f"[bold]API Key Env:[/bold] {agent_config.get('api_key_env')}\n" if agent_config.get('api_key_env') else "")
            + f"[bold]Max Tokens:[/bold] {agent_config.get('max_tokens')}\n"
            + (f"[bold]Output Dir:[/bold] {agent_config.get('output_dir')}" if agent_config.get('output_dir') else "[bold]Output Dir:[/bold] [dim]default[/dim]"),
            title="Agent Created",
                border_style="green"
            ))
        
        # Offer to set API key if needed
        api_key_env = agent_config.get('api_key_env')
        if api_key_env:
            key_status = self.key_manager.get_key_status(api_key_env)
            if not key_status['set']:
                set_key = questionary.confirm(
                    f"\n{api_key_env} is not set. Set it now?",
                    default=True,
                    style=custom_style
                ).ask()
                
                if set_key:
                    self._set_api_key(api_key_env, agent_config.get('name', 'Custom'))
                    return
        
        questionary.press_any_key_to_continue("\nPress any key to continue...").ask()

    def _refresh_available_models(self):
        """Refresh available models from provider APIs"""
        self.show_header("Refresh Available Models")
        
        self.console.print(Panel(
            "[bold]Refresh Available Models[/bold]\n\n"
            "This will fetch the latest available models from provider APIs\n"
            "and merge them with the hardcoded model lists.\n\n"
            "Models are cached for 24 hours to reduce API calls.",
            border_style="cyan"
        ))
        
        # Get API keys
        api_keys = {}
        
        anthropic_key = os.getenv('ANTHROPIC_API_KEY')
        if anthropic_key:
            api_keys['anthropic'] = anthropic_key
        
        openai_key = os.getenv('OPENAI_API_KEY')
        if openai_key:
            api_keys['openai'] = openai_key
        
        gemini_key = os.getenv('GOOGLE_API_KEY')
        if gemini_key:
            api_keys['gemini'] = gemini_key
        
        if not api_keys:
            self.console.print("\n[yellow]⚠️ No API keys found in environment variables.[/yellow]")
            self.console.print("[dim]Set ANTHROPIC_API_KEY, OPENAI_API_KEY, or GOOGLE_API_KEY to discover models.[/dim]\n")
            questionary.press_any_key_to_continue().ask()
            return
        
        # Show which providers will be refreshed
        providers_to_refresh = []
        if 'anthropic' in api_keys:
            providers_to_refresh.append("Anthropic Claude")
        if 'openai' in api_keys:
            providers_to_refresh.append("OpenAI GPT")
        if 'gemini' in api_keys:
            providers_to_refresh.append("Google Gemini")
        
        self.console.print(f"\n[cyan]Will refresh models for: {', '.join(providers_to_refresh)}[/cyan]\n")
        
        proceed = questionary.confirm(
            "Proceed with model discovery?",
            default=True,
            style=custom_style
        ).ask()
        
        if not proceed:
            return
        
        # Discover models
        try:
            from ..model_discovery import ModelDiscoveryService
            
            discovery = ModelDiscoveryService()
            
            with self.console.status("[bold green]Discovering models from APIs...[/bold green]") as status:
                results = discovery.discover_all_models(api_keys)
            
            # Show results
            self.console.print("\n[bold green]✓ Model Discovery Complete[/bold green]\n")
            
            if results:
                summary_table = Table(title="Discovered Models", show_header=True)
                summary_table.add_column("Provider", style="bold cyan")
                summary_table.add_column("Models Found", justify="right", style="green")
                summary_table.add_column("New Models", justify="right", style="yellow")
                
                for provider, models in results.items():
                    provider_display = {
                        'anthropic': 'Anthropic Claude',
                        'openai': 'OpenAI GPT',
                        'gemini': 'Google Gemini'
                    }.get(provider, provider.title())
                    
                    # Count new models (not in hardcoded lists)
                    if provider == 'anthropic':
                        from ..providers.anthropic import AnthropicProvider
                        hardcoded = AnthropicProvider.HARDCODED_MODELS
                    elif provider == 'openai':
                        from ..providers.openai import OpenAIProvider
                        hardcoded = OpenAIProvider.HARDCODED_MODELS
                    elif provider == 'gemini':
                        from ..providers.gemini import GeminiProvider
                        hardcoded = GeminiProvider.HARDCODED_MODELS
                    else:
                        hardcoded = []
                    
                    new_models = [m for m in models if m not in hardcoded]
                    
                    summary_table.add_row(
                        provider_display,
                        str(len(models)),
                        str(len(new_models))
                    )
                
                self.console.print(summary_table)
                
                # Show new models if any
                all_new_models = []
                for provider, models in results.items():
                    if provider == 'anthropic':
                        from ..providers.anthropic import AnthropicProvider
                        hardcoded = AnthropicProvider.HARDCODED_MODELS
                    elif provider == 'openai':
                        from ..providers.openai import OpenAIProvider
                        hardcoded = OpenAIProvider.HARDCODED_MODELS
                    elif provider == 'gemini':
                        from ..providers.gemini import GeminiProvider
                        hardcoded = GeminiProvider.HARDCODED_MODELS
                    else:
                        hardcoded = []
                    
                    new_models = [m for m in models if m not in hardcoded]
                    if new_models:
                        all_new_models.extend([(provider, m) for m in new_models])
                
                if all_new_models:
                    self.console.print("\n[bold yellow]New Models Discovered:[/bold yellow]\n")
                    for provider, model in all_new_models:
                        provider_display = {
                            'anthropic': 'Anthropic',
                            'openai': 'OpenAI',
                            'gemini': 'Gemini'
                        }.get(provider, provider.title())
                        self.console.print(f"  [cyan]{provider_display}:[/cyan] {model}")
                
                self.console.print("\n[green]✓ Models have been cached and will be available when configuring agents.[/green]")
            else:
                self.console.print("[yellow]No models were discovered. Check your API keys and try again.[/yellow]")
        
        except Exception as e:
            self.console.print(f"\n[red]Error discovering models: {e}[/red]")
            import traceback
            self.console.print(f"[dim]{traceback.format_exc()}[/dim]")
        
        questionary.press_any_key_to_continue().ask()

    def _provider_name_for_agent_type(self, agent_type: str) -> Optional[str]:
        """Map a builtin agent type to its reconciled provider name (REQ-TMM-110)."""
        return {'claude': 'anthropic', 'gpt4': 'openai', 'gemini': 'gemini'}.get(agent_type)

    def _get_provider_safe(self, provider_name: str):
        """Resolve a provider instance via the registry, or None on failure."""
        try:
            from ..providers.registry import ProviderRegistry
            ProviderRegistry.discover()
            return ProviderRegistry.get_provider(provider_name)
        except Exception:
            return None

    def _model_view_for_provider(self, provider_name: str) -> List[Dict[str, Any]]:
        """Origin-annotated model view for a provider (REQ-TMM-131, 132).

        Baseline derives from ``provider.HARDCODED_MODELS`` (NOT ``AGENT_TYPES`` —
        REQ-TMM-132); discovered from the discovery cache; user-added from the
        overlay. De-duplicated with user > discovered > baseline precedence.
        """
        provider = self._get_provider_safe(provider_name)
        baseline = list(getattr(provider, 'HARDCODED_MODELS', []) or [])
        discovered: List[str] = []
        try:
            from ..model_discovery import ModelDiscoveryService
            discovered = ModelDiscoveryService().get_discovered_models(provider_name)
        except Exception:
            discovered = []
        try:
            from ..user_models import UserModelStore
            return UserModelStore().merge_view(provider_name, baseline, discovered)
        except Exception:
            seen, view = set(), []
            for mid in list(baseline) + list(discovered):
                if mid not in seen:
                    view.append({'model_id': mid, 'origin': 'baseline'})
                    seen.add(mid)
            return view

    def _maybe_persist_custom_model(self, provider_name: Optional[str], raw: Optional[str]) -> Optional[str]:
        """Normalize a custom-entered id and offer to persist it (REQ-TMM-107/111/120)."""
        if not raw:
            return None
        from ..user_models import UserModelStore, normalize_model_id, ModelIdError, VALID_TIERS
        try:
            model_id = normalize_model_id(raw)
        except ModelIdError as e:
            self.console.print(f"[red]Invalid model id: {e}[/red]")
            return None

        if provider_name:
            try:
                from ..model_sources import classify_model_id
                classification = classify_model_id(provider_name, model_id)
            except Exception:
                classification = 'unrecognized'
            if classification == 'unrecognized':
                proceed = questionary.confirm(
                    f"'{model_id}' was not found in any known source. Use it anyway?",
                    default=True, style=custom_style,
                ).ask()
                if not proceed:
                    return None

            save = questionary.confirm(
                "Save this model to your model list for reuse?",
                default=False, style=custom_style,
            ).ask()
            if save:
                tier = questionary.select(
                    "Tier for this model:", choices=sorted(VALID_TIERS),
                    default="balanced", style=custom_style,
                ).ask()
                try:
                    UserModelStore().add(
                        provider_name, model_id, tier=tier or "balanced", source="custom-entry"
                    )
                    self.console.print(f"[green]✓ Saved '{model_id}' to your model list.[/green]")
                except Exception as e:
                    self.console.print(f"[yellow]Could not save model: {e}[/yellow]")
        return model_id

    def _manage_models(self):
        """Top-level Manage Models action: choose a provider, then CRUD its overlay."""
        while True:
            self.show_header("Manage Models")
            self.console.print(
                "[dim]Add, edit, suppress, or remove model ids per provider. "
                "User-added models persist in ~/.startd8/user_models.json and appear "
                "in the agent picker and routing catalog.[/dim]\n"
            )
            provider_name = questionary.select(
                "Choose a provider:",
                choices=[
                    "anthropic", "openai", "gemini",
                    questionary.Separator("──────────"),
                    "← Back",
                ],
                style=custom_style,
            ).ask()
            if not provider_name or "Back" in provider_name:
                break
            self._manage_models_for_provider(provider_name)

    def _manage_models_for_provider(self, provider_name: str):
        """List + CRUD sub-menu for one provider's model overlay."""
        while True:
            self.show_header(f"Manage Models — {provider_name}")
            view = self._model_view_for_provider(provider_name)

            table = Table(title=f"{provider_name} models ({len(view)})", show_header=True)
            table.add_column("Model", style="bright_white", no_wrap=False)
            table.add_column("Origin", style="magenta")
            table.add_column("Tier", style="cyan")
            table.add_column("Source", style="dim")
            for v in view:
                origin = v.get("origin", "")
                origin_disp = {
                    "user-added": "[green]user-added[/green]",
                    "discovered": "[yellow]discovered[/yellow]",
                    "baseline": "baseline",
                }.get(origin, origin)
                table.add_row(
                    v.get("model_id", "-"), origin_disp,
                    v.get("tier") or "-", v.get("source") or "-",
                )
            self.console.print(table)
            self.console.print()

            action = questionary.select(
                f"Manage {provider_name} models:",
                choices=[
                    "➕ Add model",
                    "✏️  Edit user model",
                    "🗑️  Remove / suppress model",
                    questionary.Separator("──────────"),
                    "← Back",
                ],
                style=custom_style,
            ).ask()
            if not action or "Back" in action:
                break
            if "Add" in action:
                self._manage_models_add(provider_name)
            elif "Edit" in action:
                self._manage_models_edit(provider_name, view)
            elif "Remove" in action:
                self._manage_models_remove(provider_name, view)

    def _manage_models_add(self, provider_name: str):
        """Add a model id to the user overlay (REQ-TMM-101/107/120)."""
        from ..user_models import UserModelStore, normalize_model_id, ModelIdError, VALID_TIERS
        raw = questionary.text("Model id to add:", style=custom_style).ask()
        if not raw:
            return
        try:
            model_id = normalize_model_id(raw)
        except ModelIdError as e:
            self.console.print(f"[red]Invalid model id: {e}[/red]")
            questionary.press_any_key_to_continue().ask()
            return

        try:
            from ..model_sources import classify_model_id
            classification = classify_model_id(provider_name, model_id)
        except Exception:
            classification = "unrecognized"
        if classification == "unrecognized":
            proceed = questionary.confirm(
                f"'{model_id}' was not found in any known source. Add anyway?",
                default=True, style=custom_style,
            ).ask()
            if not proceed:
                return

        tier = questionary.select(
            "Tier:", choices=sorted(VALID_TIERS), default="balanced", style=custom_style,
        ).ask()
        if not tier:
            return
        try:
            UserModelStore().add(provider_name, model_id, tier=tier, source="manual")
            self.console.print(f"[green]✓ Added '{model_id}' ({tier}).[/green]")
        except Exception as e:
            self.console.print(f"[red]Failed to add: {e}[/red]")
        questionary.press_any_key_to_continue().ask()

    def _manage_models_edit(self, provider_name: str, view: List[Dict[str, Any]]):
        """Edit a user-added model's id/tier (REQ-TMM-103)."""
        from ..user_models import (
            UserModelStore, ModelCollisionError, ModelIdError, VALID_TIERS,
        )
        user_ids = [v["model_id"] for v in view if v.get("origin") == "user-added"]
        if not user_ids:
            self.console.print("[yellow]No user-added models to edit (only user-added are editable).[/yellow]")
            questionary.press_any_key_to_continue().ask()
            return
        model_id = questionary.select(
            "Edit which model?", choices=user_ids + ["← Cancel"], style=custom_style,
        ).ask()
        if not model_id or "Cancel" in model_id:
            return
        new_id = questionary.text("New id (blank = keep):", default="", style=custom_style).ask()
        tier = questionary.select(
            "New tier (Esc = keep):", choices=sorted(VALID_TIERS), style=custom_style,
        ).ask()

        from ..model_sources import classify_model_id

        def _collision(prov: str, mid: str) -> bool:
            return classify_model_id(prov, mid) != "unrecognized"

        try:
            UserModelStore().edit(
                provider_name, model_id,
                new_id=((new_id or "").strip() or None),
                tier=tier or None,
                collision_check=_collision,
            )
            self.console.print("[green]✓ Updated.[/green]")
        except (ModelCollisionError, ModelIdError) as e:
            self.console.print(f"[red]{e}[/red]")
        questionary.press_any_key_to_continue().ask()

    def _manage_models_remove(self, provider_name: str, view: List[Dict[str, Any]]):
        """Remove a user model, or suppress a baseline/discovered id (REQ-TMM-102)."""
        from ..user_models import UserModelStore
        ids = [v["model_id"] for v in view]
        if not ids:
            return
        model_id = questionary.select(
            "Remove (user) / suppress (baseline·discovered) which model?",
            choices=ids + ["← Cancel"], style=custom_style,
        ).ask()
        if not model_id or "Cancel" in model_id:
            return
        try:
            result = UserModelStore().remove(provider_name, model_id)
        except Exception as e:
            self.console.print(f"[red]Failed: {e}[/red]")
            questionary.press_any_key_to_continue().ask()
            return
        msg = {
            "removed": f"Removed user model '{model_id}'",
            "suppressed": f"Suppressed (hidden) '{model_id}' — re-add to restore",
            "noop": f"No change ('{model_id}' already suppressed)",
        }.get(result, result)
        self.console.print(f"[green]✓ {msg}[/green]")
        questionary.press_any_key_to_continue().ask()

    def _configure_builtin_agent(self, agent_type: str) -> Optional[Dict[str, Any]]:
        """Configure a built-in agent (Claude, GPT-4, Mock)"""
        type_info = CustomAgentManager.AGENT_TYPES.get(agent_type, {})
        
        if not type_info:
            return None
        
        # Check API key status
        if type_info.get('api_key_env'):
            key_status = self.key_manager.get_key_status(type_info['api_key_env'])
            if not key_status['set']:
                self.console.print(f"\n[yellow]⚠️ {type_info['api_key_env']} is not set[/yellow]")
                self.console.print("[dim]You can set it later in 'Manage API Keys'[/dim]\n")
        
        # Get agent name
        name = questionary.text(
            "Agent name:",
            default=f"my-{agent_type}",
            style=custom_style
        ).ask()
        
        if not name:
            return None
        
        # Select model (REQ-TMM-110/132): derive choices from the provider's
        # model view (baseline ∪ discovered ∪ user-added), NOT a hardcoded
        # AGENT_TYPES['models'] copy. Falls back to the static list for agent
        # types without a reconciled provider (e.g. mock).
        provider_name = self._provider_name_for_agent_type(agent_type)
        if provider_name:
            view = self._model_view_for_provider(provider_name)
            baseline = [v['model_id'] for v in view if v.get('origin') == 'baseline']
            discovered = [v['model_id'] for v in view if v.get('origin') == 'discovered']
            user_models = [v['model_id'] for v in view if v.get('origin') == 'user-added']

            model_choices = list(baseline)
            if discovered:
                model_choices.append(questionary.Separator("─── Discovered Models ───"))
                model_choices.extend(discovered)
            if user_models:
                model_choices.append(questionary.Separator("─── Your Models ───"))
                model_choices.extend(user_models)
            model_choices.append(questionary.Separator("───────────────────────"))
            model_choices.append("✏️  Enter custom model name")

            string_choices = [c for c in model_choices if isinstance(c, str)]
            default_model = type_info.get('default_model')
            if default_model not in string_choices:
                default_model = baseline[0] if baseline else None

            model = questionary.select(
                "Select model:",
                choices=model_choices,
                default=default_model,
                style=custom_style
            ).ask()

            # Custom entry: normalize, flag-if-unrecognized, offer to persist.
            if model == "✏️  Enter custom model name":
                raw = questionary.text("Enter model name:", style=custom_style).ask()
                model = self._maybe_persist_custom_model(provider_name, raw)
        elif type_info.get('models'):
            # Agent types without a reconciled provider (e.g. mock): static list.
            model_choices = list(type_info['models'])
            model_choices.append(questionary.Separator("───────────────────────"))
            model_choices.append("✏️  Enter custom model name")
            model = questionary.select(
                "Select model:",
                choices=model_choices,
                default=type_info.get('default_model'),
                style=custom_style
            ).ask()
            if model == "✏️  Enter custom model name":
                model = questionary.text("Enter model name:", style=custom_style).ask()
        else:
            model = type_info.get('default_model', 'default')

        if not model:
            return None
        
        # Get max tokens
        max_tokens_str = questionary.text(
            "Max tokens:",
            default="4096",
            style=custom_style
        ).ask()
        
        try:
            max_tokens = int(max_tokens_str) if max_tokens_str else 4096
        except ValueError:
            max_tokens = 4096
        
        # Get output directory (optional)
        output_dir = self._safe_path_input(
            "Output directory (optional):",
            style=custom_style,
            only_directories=True
        )
        
        # Expand and validate if provided
        if output_dir:
            from pathlib import Path
            output_dir = str(Path(output_dir).expanduser().resolve())
        
        config = {
            'name': name,
            'type': agent_type,
            'model': model,
            'max_tokens': max_tokens
        }
        
        if output_dir:
            config['output_dir'] = output_dir
        
        return config

    def _configure_openai_compatible(self, preset_id: str) -> Optional[Dict[str, Any]]:
        """Configure an OpenAI-compatible agent"""
        preset = CustomAgentManager.OPENAI_COMPATIBLE_PRESETS.get(preset_id, {})
        
        self.console.print()
        
        if preset_id == 'custom':
            # Fully custom configuration
            self.console.print(Panel(
                "[bold]Custom OpenAI-Compatible Endpoint[/bold]\n\n"
                "Enter details for your custom API endpoint.\n"
                "Must be compatible with OpenAI's chat completions API.",
                border_style="cyan"
            ))
            
            name = questionary.text(
                "Agent name:",
                style=custom_style
            ).ask()
            
            if not name:
                return None
            
            base_url = questionary.text(
                "Base URL:",
                style=custom_style,
            ).ask()
            
            if not base_url:
                return None
            
            model = questionary.text(
                "Model name:",
                style=custom_style,
            ).ask()
            
            if not model:
                return None
            
            api_key_env = questionary.text(
                "API key environment variable:",
                style=custom_style,
            ).ask()
            
        else:
            # Use preset values
            self.console.print(Panel(
                f"[bold]{preset.get('name', preset_id)} Configuration[/bold]\n\n"
                f"[bold]Base URL:[/bold] {preset.get('base_url', 'N/A')}\n"
                f"[bold]API Key:[/bold] {preset.get('api_key_env', 'Not required')}",
                border_style="cyan"
            ))
            
            # Check API key status
            if preset.get('api_key_env'):
                key_status = self.key_manager.get_key_status(preset['api_key_env'])
                if not key_status['set']:
                    self.console.print(f"\n[yellow]⚠️ {preset['api_key_env']} is not set[/yellow]")
                    self.console.print("[dim]You can set it after creating the agent[/dim]\n")
            
            name = questionary.text(
                "Agent name:",
                default=f"my-{preset_id}",
                style=custom_style
            ).ask()
            
            if not name:
                return None
            
            # Select model from preset or enter custom
            if preset.get('models'):
                model_choices = preset['models'] + ["[Enter custom model]"]
                model = questionary.select(
                    "Select model:",
                    choices=model_choices,
                    style=custom_style
                ).ask()
                
                if model == "[Enter custom model]":
                    model = questionary.text(
                        "Model name:",
                        style=custom_style
                    ).ask()
            else:
                model = questionary.text(
                    "Model name:",
                    style=custom_style
                ).ask()
            
            if not model:
                return None
            
            base_url = preset.get('base_url')
            api_key_env = preset.get('api_key_env')
        
        # Get max tokens
        max_tokens_str = questionary.text(
            "Max tokens:",
            default="4096",
            style=custom_style
        ).ask()
        
        try:
            max_tokens = int(max_tokens_str) if max_tokens_str else 4096
        except ValueError:
            max_tokens = 4096
        
        # Get output directory (optional)
        output_dir = self._safe_path_input(
            "Output directory (optional):",
            style=custom_style,
            only_directories=True
        )
        
        # Expand and validate if provided
        if output_dir:
            from pathlib import Path
            output_dir = str(Path(output_dir).expanduser().resolve())
        
        config = {
            'name': name,
            'type': 'openai_compatible',
            'model': model,
            'max_tokens': max_tokens,
            'base_url': base_url,
            'provider': preset_id
        }
        
        if api_key_env:
            config['api_key_env'] = api_key_env
        
        if output_dir:
            config['output_dir'] = output_dir
        
        return config

    def _edit_agent(self, agents: List[Dict[str, Any]]):
        """Edit an existing custom agent"""
        if not agents:
            return
        
        # Select agent to edit
        choices = []
        for a in agents:
            agent_type = a.get('type', 'unknown')
            model = a.get('model', 'default')[:20]
            # Check if agent is invalid
            try:
                instance = self.agent_manager.create_agent_instance(a)
                status_icon = "✓" if instance else "✗"
            except Exception:
                status_icon = "⚠"
            choices.append(f"{status_icon} {a.get('name', 'unnamed')} ({agent_type}/{model})")
        choices.append("← Cancel")
        
        selected = questionary.select(
            "Select agent to edit:",
            choices=choices,
            style=custom_style
        ).ask()
        
        if not selected or "Cancel" in selected:
            return
        
        # Find the agent (skip status icon)
        selected_clean = selected.replace("✓ ", "").replace("✗ ", "").replace("⚠ ", "")
        agent = None
        agent_idx = None
        for i, a in enumerate(agents):
            agent_str = f"{a.get('name', 'unnamed')} ({a.get('type')}/{a.get('model', 'default')[:20]})"
            if agent_str == selected_clean:
                agent = a
                agent_idx = i
                break
        
        if not agent:
            # Fallback: try to find by matching the name part
            for i, a in enumerate(agents):
                if a.get('name', 'unnamed') in selected_clean:
                    agent = a
                    agent_idx = i
                    break
        
        if not agent:
            self.console.print("[red]Agent not found[/red]")
            return
        
        agent_id = agent.get('id')
        agent_type = agent.get('type', 'unknown')
        type_info = CustomAgentManager.AGENT_TYPES.get(agent_type, {})
        
        # Check if agent type is invalid and offer to fix it
        if agent_type not in ['claude', 'gpt4', 'openai_compatible', 'mock', 'provider']:
            self.console.print(f"\n[yellow]⚠️  Warning: Invalid agent type '{agent_type}'[/yellow]")
            model = agent.get('model', '').lower()
            
            # Try to auto-detect correct type based on model name
            suggested_type = None
            if 'gpt' in model or 'openai' in model:
                suggested_type = 'gpt4'
            elif 'claude' in model or 'anthropic' in model:
                suggested_type = 'claude'
            
            if suggested_type:
                fix_type = questionary.confirm(
                    f"Would you like to change type to '{suggested_type}'?",
                    default=True,
                    style=custom_style
                ).ask()
                if fix_type:
                    agent_type = suggested_type
                    type_info = CustomAgentManager.AGENT_TYPES.get(agent_type, {})
                    # Update the agent type
                    self.agent_manager.update_agent(agent_id, {'type': agent_type})
                    self.console.print(f"[green]✓ Updated agent type to '{agent_type}'[/green]\n")
        
        self.console.print()
        
        # Edit name
        new_name = questionary.text(
            "Agent name:",
            default=agent.get('name', ''),
            style=custom_style
        ).ask()
        
        # Edit model (REQ-TMM-132): derive choices from the provider, not a
        # hardcoded AGENT_TYPES['models'] copy.
        provider_name = self._provider_name_for_agent_type(agent_type)
        current_model = agent.get('model', type_info.get('default_model'))
        if provider_name:
            view = self._model_view_for_provider(provider_name)
            baseline = [v['model_id'] for v in view if v.get('origin') == 'baseline']
            discovered = [v['model_id'] for v in view if v.get('origin') == 'discovered']
            user_models = [v['model_id'] for v in view if v.get('origin') == 'user-added']
            known_ids = set(baseline) | set(discovered) | set(user_models)

            model_choices = list(baseline)
            if discovered:
                model_choices.append(questionary.Separator("─── Discovered Models ───"))
                model_choices.extend(discovered)
            if user_models:
                model_choices.append(questionary.Separator("─── Your Models ───"))
                model_choices.extend(user_models)
            if current_model and current_model not in known_ids:
                model_choices.append(questionary.Separator("───────────────────────"))
                model_choices.append(f"📌 {current_model} (current)")
            model_choices.append(questionary.Separator("───────────────────────"))
            model_choices.append("✏️  Enter custom model name")

            new_model = questionary.select(
                "Select model:",
                choices=model_choices,
                default=current_model if current_model in known_ids else None,
                style=custom_style
            ).ask()

            if new_model == "✏️  Enter custom model name":
                raw = questionary.text(
                    "Enter model name:",
                    default=current_model if current_model and current_model not in known_ids else "",
                    style=custom_style
                ).ask()
                new_model = self._maybe_persist_custom_model(provider_name, raw) or current_model
            elif isinstance(new_model, str) and new_model.startswith("📌 "):
                new_model = new_model.replace("📌 ", "").replace(" (current)", "")
        elif type_info.get('models'):
            # Agent types without a reconciled provider (e.g. mock): static list.
            model_choices = list(type_info['models']) + ["✏️  Enter custom model name"]
            if current_model and current_model not in type_info['models']:
                model_choices.insert(-1, f"📌 {current_model} (current)")
            new_model = questionary.select(
                "Select model:",
                choices=model_choices,
                default=current_model if current_model in type_info['models'] else None,
                style=custom_style
            ).ask()
            if new_model == "✏️  Enter custom model name":
                new_model = questionary.text(
                    "Enter model name:",
                    default=current_model if current_model and current_model not in type_info['models'] else "",
                    style=custom_style
                ).ask()
            elif isinstance(new_model, str) and new_model.startswith("📌 "):
                new_model = new_model.replace("📌 ", "").replace(" (current)", "")
        else:
            new_model = agent.get('model')
        
        # Edit max tokens
        new_max_tokens_str = questionary.text(
            "Max tokens:",
            default=str(agent.get('max_tokens', 4096)),
            style=custom_style
        ).ask()
        
        try:
            new_max_tokens = int(new_max_tokens_str) if new_max_tokens_str else 4096
        except ValueError:
            new_max_tokens = 4096
        
        # Edit output directory
        current_output_dir = agent.get('output_dir', '')
        self.console.print()
        self.console.print(f"[dim]Current output directory: {current_output_dir or '(default)'}[/dim]")
        
        change_output = questionary.confirm(
            "Change output directory?",
            default=False,
            style=custom_style
        ).ask()
        
        new_output_dir = current_output_dir
        if change_output:
            new_output_dir = self._safe_path_input(
                "Output directory:",
                style=custom_style,
                only_directories=True
            )
            
            # Expand and validate if provided
            if new_output_dir:
                from pathlib import Path
                new_output_dir = str(Path(new_output_dir).expanduser().resolve())
        
        # Update
        updates = {
            'name': new_name or agent.get('name'),
            'model': new_model or agent.get('model'),
            'max_tokens': new_max_tokens,
            'output_dir': new_output_dir or ''
        }
        
        if self.agent_manager.update_agent(agent_id, updates):
            self.console.print("\n[green]✓ Agent updated successfully![/green]")
            if new_output_dir:
                self.console.print(f"[dim]Output directory: {new_output_dir}[/dim]\n")
            else:
                self.console.print("[dim]Output directory: (default)[/dim]\n")
        else:
            self.console.print("\n[red]✗ Failed to update agent[/red]\n")
        
        questionary.press_any_key_to_continue("Press any key...").ask()

    def _delete_agent(self, agents: List[Dict[str, Any]]):
        """Delete a custom agent"""
        if not agents:
            return
        
        # Select agent to delete
        choices = [
            f"{a.get('name', 'unnamed')} ({a.get('type')}/{a.get('model', 'default')[:20]})"
            for a in agents
        ]
        choices.append("← Cancel")
        
        selected = questionary.select(
            "Select agent to delete:",
            choices=choices,
            style=custom_style
        ).ask()
        
        if not selected or "Cancel" in selected:
            return
        
        # Confirm
        confirm = questionary.confirm(
            f"Delete '{selected.split(' (')[0]}'?",
            default=False,
            style=custom_style
        ).ask()
        
        if not confirm:
            return
        
        # Find and delete
        idx = choices.index(selected)
        agent = agents[idx]
        
        if self.agent_manager.delete_agent(agent.get('id')):
            self.console.print("\n[green]✓ Agent deleted[/green]\n")
        else:
            self.console.print("\n[red]✗ Failed to delete agent[/red]\n")
        
        questionary.press_any_key_to_continue("Press any key...").ask()
