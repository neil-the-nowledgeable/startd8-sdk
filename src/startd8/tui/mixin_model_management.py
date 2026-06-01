"""ModelManagementMixin: extracted from AgentManagementMixin (Pass C — focused sub-mixin)."""

from ._shared import *  # noqa: F401,F403


class ModelManagementMixin:
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
