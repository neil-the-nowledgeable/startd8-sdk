"""AgentSelectionMixin: extracted from PromptWorkflowMixin (Pass C — focused sub-mixin)."""

from ._shared import *  # noqa: F401,F403


class AgentSelectionMixin:
    def _build_unified_agent_list(self, custom_agents: List[Dict[str, Any]], distributed_agents: set) -> List[Dict[str, Any]]:
        """Build a unified list of all agents with their status"""
        agents = []
        
        # Built-in: Mock
        mock_key = "mock:mock-model"
        agents.append({
            'name': 'Mock',
            'model': 'mock-model',
            'type': 'builtin',
            'builtin_type': 'mock',
            'icon': '🧪',
            'available': self.agent_status['mock']['working'],
            'distributed': mock_key in distributed_agents,
            'error': None if self.agent_status['mock']['working'] else 'not working'
        })
        
        # Built-in: Claude
        claude_model = 'claude-opus-4-8'
        claude_key = f"claude:{claude_model}"
        agents.append({
            'name': 'Claude',
            'model': claude_model,
            'type': 'builtin',
            'builtin_type': 'claude',
            'icon': '🔵',
            'available': self.agent_status['claude']['working'],
            'distributed': claude_key in distributed_agents or any(
                'claude' in k.lower() for k in distributed_agents
            ),
            'error': self.agent_status['claude'].get('error') if not self.agent_status['claude']['working'] else None
        })
        
        # Built-in: GPT-4
        gpt4_model = 'gpt-5.5-pro'
        gpt4_key = f"gpt4:{gpt4_model}"
        agents.append({
            'name': 'GPT-4',
            'model': gpt4_model,
            'type': 'builtin',
            'builtin_type': 'gpt4',
            'icon': '🟢',
            'available': self.agent_status['gpt4']['working'],
            'distributed': gpt4_key in distributed_agents or any(
                'gpt' in k.lower() for k in distributed_agents
            ),
            'error': self.agent_status['gpt4'].get('error') if not self.agent_status['gpt4']['working'] else None
        })
        
        # Custom agents
        for agent in custom_agents:
            agent_type = agent.get('type', 'unknown')
            type_info = CustomAgentManager.AGENT_TYPES.get(agent_type, {})
            api_key_env = type_info.get('api_key_env')
            
            # For openai_compatible, check the agent's own api_key_env
            if agent_type == 'openai_compatible':
                api_key_env = agent.get('api_key_env')
            
            # Check if agent can work
            available = True
            error = None
            if api_key_env:
                key_status = self.key_manager.get_key_status(api_key_env)
                if not key_status.get('set'):
                    available = False
                    error = f"{api_key_env} not set"
            
            agent_name = agent.get('name', 'custom')
            agent_model = agent.get('model', 'unknown')
            agent_key = f"{agent_name}:{agent_model}"
            
            # Determine icon based on provider
            provider = agent.get('provider', agent_type)
            icon_map = {
                'cursor': '⚡',
                'ollama': '🦙',
                'groq': '🚀',
                'together': '🌐',
                'openrouter': '🔀',
                'openai_compatible': '⚙️',
                'claude': '🔵',
                'gpt4': '🟢',
                'mock': '🧪'
            }
            icon = icon_map.get(provider, '⭐')
            
            agents.append({
                'name': agent_name,
                'model': agent_model,
                'type': 'custom',
                'custom_config': agent,
                'icon': icon,
                'available': available,
                'distributed': agent_key in distributed_agents,
                'error': error
            })
        
        return agents

    def _show_agent_distribution_table(self, agents: List[Dict[str, Any]], distributed_agents: set):
        """Show unified table of all agents with distribution status"""
        table = Table(title="All Agents", show_header=True)
        table.add_column("", justify="center", width=3)  # Icon
        table.add_column("Agent", style="bold")
        table.add_column("Model", style="cyan")
        table.add_column("Type", style="magenta")
        table.add_column("Status", justify="center")
        table.add_column("Sent?", justify="center")
        
        for agent in agents:
            icon: str = agent.get('icon', '🤖')
            name: str = agent['name']
            model: str = agent['model'][:25] + "..." if len(agent['model']) > 25 else agent['model']
            agent_type: str = "Built-in" if agent['type'] == 'builtin' else "User added"
            
            if agent['available']:
                status: str = "[green]✓ Ready[/green]"
            else:
                status = f"[red]✗ {agent.get('error', 'N/A')}[/red]"
            
            if agent['distributed']:
                sent: str = "[green]✓ Yes[/green]"
            else:
                sent = "[dim]No[/dim]"
            
            table.add_row(icon, name, model, agent_type, status, sent)
        
        self.console.print()
        self.console.print(table)
        self.console.print()

    def _get_undistributed_agents(self, all_agents: List[Dict[str, Any]], custom_agents: List[Dict[str, Any]], distributed_agents: set) -> List[BaseAgent]:
        """Get only agents that haven't received this prompt yet"""
        agents: List[BaseAgent] = []
        
        for agent_info in all_agents:
            if agent_info['available'] and not agent_info['distributed']:
                if agent_info['type'] == 'builtin':
                    if agent_info['builtin_type'] == 'mock':
                        agents.append(MockAgent(name="mock", model="mock-model"))
                    elif agent_info['builtin_type'] == 'claude':
                        try:
                            agents.append(ClaudeAgent())
                        except Exception:
                            pass
                    elif agent_info['builtin_type'] == 'gpt4':
                        try:
                            agents.append(GPT4Agent())
                        except Exception:
                            pass
                else:
                    # Custom agent
                    try:
                        instance = self.agent_manager.create_agent_instance(agent_info['custom_config'])
                        if instance:
                            agents.append(instance)
                    except Exception:
                        pass
        
        return agents

    def _get_agent_from_unified_choice(self, choice: str, all_agents: List[Dict[str, Any]], custom_agents: List[Dict[str, Any]]) -> List[BaseAgent]:
        """Get agent from unified selection choice"""
        agents: List[BaseAgent] = []
        
        # Extract agent name from choice (format: "icon name (model)")
        # Try to parse the exact name from the choice string
        agent_name: Optional[str] = None
        if "⭐" in choice:
            # Custom agent format: "⭐ name (model)"
            try:
                parts = choice.split("⭐ ", 1)
                if len(parts) > 1:
                    name_part = parts[1].split(" (")[0]
                    agent_name = name_part.strip()
            except (IndexError, ValueError):
                pass
        
        # If we couldn't parse, try substring matching
        if not agent_name:
            # Find the agent by matching name substring
            for agent_info in all_agents:
                if agent_info['name'] in choice and agent_info.get('available', False):
                    agent_name = agent_info['name']
                    break
        
        # Now find and create the agent
        if agent_name:
            for agent_info in all_agents:
                if agent_info['name'] == agent_name and agent_info.get('available', False):
                    if agent_info['type'] == 'builtin':
                        if agent_info['builtin_type'] == 'mock':
                            agents.append(MockAgent(name="mock", model="mock-model"))
                        elif agent_info['builtin_type'] == 'claude':
                            try:
                                agents.append(ClaudeAgent())
                            except Exception:
                                pass
                        elif agent_info['builtin_type'] == 'gpt4':
                            try:
                                agents.append(GPT4Agent())
                            except Exception:
                                pass
                    else:
                        # Custom agent
                        custom_config = agent_info.get('custom_config')
                        if not custom_config:
                            # Try to find in custom_agents list
                            for custom_agent in custom_agents:
                                if custom_agent.get('name') == agent_name:
                                    custom_config = custom_agent
                                    break
                        
                        if custom_config:
                            try:
                                instance = self.agent_manager.create_agent_instance(custom_config)
                                if instance:
                                    agents.append(instance)
                            except Exception as e:
                                # Log the error for debugging but don't fail silently
                                import logging
                                logger = logging.getLogger(__name__)
                                logger.warning(f"Failed to create agent '{agent_name}': {e}", exc_info=True)
                                # Don't append, but continue to try other matches
                                pass
                    break
        
        return agents

    def _validate_agent_for_workflow(self, agent_info: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """
        Validate that an agent can actually be created and is properly configured.
        
        This performs a real validation by attempting to create the agent instance
        and checking model names against provider supported models.
        
        Args:
            agent_info: Agent dictionary from unified agent list
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            # Try to create the agent instance
            if agent_info['type'] == 'builtin':
                # Built-in agents - try to create
                if agent_info.get('builtin_type') == 'mock':
                    MockAgent(name="mock", model="mock-model")
                    return True, None
                elif agent_info.get('builtin_type') == 'claude':
                    ClaudeAgent()
                    return True, None
                elif agent_info.get('builtin_type') == 'gpt4':
                    GPT4Agent()
                    return True, None
            else:
                # Custom agent - validate configuration
                custom_config = agent_info.get('custom_config')
                if not custom_config:
                    # Try to find in custom agents list
                    custom_agents = self.agent_manager.list_agents()
                    for custom_agent in custom_agents:
                        if custom_agent.get('name') == agent_info.get('name'):
                            custom_config = custom_agent
                            break
                
                if custom_config:
                    # Validate model name if provider-backed agent
                    agent_type = custom_config.get('type')
                    model = custom_config.get('model', '')
                    provider_name = custom_config.get('provider')
                    
                    if agent_type == 'provider' and provider_name and model:
                        # Check if model is supported by provider
                        try:
                            from ..providers.registry import ProviderRegistry
                            ProviderRegistry.discover()
                            provider = ProviderRegistry.get_provider(provider_name.lower())
                            
                            if provider:
                                # Check if model is in supported models (or provider allows unknown models)
                                supported_models = provider.supported_models or []
                                model_lower = model.lower()
                                
                                # Pre-validation: Check for obviously invalid model names
                                if provider_name.lower() == 'openai':
                                    # Check for invalid GPT model versions
                                    if 'gpt-5' in model_lower or 'gpt-6' in model_lower:
                                        return False, f"Model '{model}' is not a valid OpenAI model (GPT-5/6 don't exist)"
                                    # Check if model matches known GPT patterns
                                    valid_patterns = ['gpt-4', 'gpt-3', 'gpt-4o', 'o1', 'davinci', 'curie', 'babbage', 'ada']
                                    if not any(pattern in model_lower for pattern in valid_patterns):
                                        # Not a known GPT pattern - check if it's in supported list
                                        if supported_models and model_lower not in [m.lower() for m in supported_models]:
                                            return False, f"Model '{model}' is not a recognized OpenAI model"
                                
                                elif provider_name.lower() == 'gemini':
                                    # Check for invalid Gemini model names
                                    valid_patterns = ['gemini-1', 'gemini-2', 'gemini-pro']
                                    if not any(pattern in model_lower for pattern in valid_patterns):
                                        if supported_models and model_lower not in [m.lower() for m in supported_models]:
                                            return False, f"Model '{model}' is not a recognized Gemini model"
                                
                                # Try to create agent instance - this will validate everything
                                instance = self.agent_manager.create_agent_instance(custom_config)
                                if instance:
                                    return True, None
                                else:
                                    return False, f"Agent creation returned None for model '{model}'"
                        except Exception as e:
                            error_msg = str(e)
                            # Check for model not found errors
                            if 'not found' in error_msg.lower() or 'not available' in error_msg.lower():
                                return False, f"Model '{model}' not found or not available"
                            elif 'api key' in error_msg.lower() or 'api_key' in error_msg.lower():
                                return False, f"API key not configured"
                            else:
                                return False, f"Configuration error: {error_msg}"
                    else:
                        # Non-provider agent - just try to create
                        instance = self.agent_manager.create_agent_instance(custom_config)
                        if instance:
                            return True, None
                        else:
                            return False, "Agent creation failed"
            
            return False, "Unknown agent type"
        except Exception as e:
            error_msg = str(e)
            # Extract meaningful error message
            if 'not found' in error_msg.lower() or 'not available' in error_msg.lower():
                model = agent_info.get('model', 'unknown')
                return False, f"Model '{model}' not found or not available"
            elif 'api key' in error_msg.lower() or 'api_key' in error_msg.lower():
                return False, "API key not configured"
            else:
                return False, f"Validation error: {error_msg}"

    def _get_ready_agents_for_selection(self) -> List[Dict[str, Any]]:
        """
        Get all agents with Ready status for selection.
        
        This is the single modular way to select agents that have a status of Ready.
        Returns a list of agent dictionaries with 'available' == True (Ready status).
        
        Additionally validates that agents can actually be created before including them.
        Filters out agents with invalid model names or configuration issues.
        
        Ensures agent_status is up to date before filtering.
        
        Returns:
            List of agent dicts with keys: name, model, type, icon, available, etc.
            Only includes agents that pass validation.
        """
        # Ensure agent_status is up to date
        if self.agent_status is None:
            self.agent_status = AgentConfigTester.test_all()
        
        custom_agents: List[Dict[str, Any]] = self.agent_manager.list_agents()
        all_agents: List[Dict[str, Any]] = self._build_unified_agent_list(custom_agents, set())
        
        # Filter to only Ready agents (available == True)
        # This corresponds to agents with Status "Ready" in the agent status table
        ready_agents: List[Dict[str, Any]] = [agent for agent in all_agents if agent.get('available', False)]
        
        # Additional validation: actually try to create each agent to ensure it works
        validated_agents = []
        invalid_agents = []
        
        for agent in ready_agents:
            is_valid, error_msg = self._validate_agent_for_workflow(agent)
            if is_valid:
                validated_agents.append(agent)
            else:
                # Mark agent as invalid but keep for reporting
                agent['validation_error'] = error_msg
                invalid_agents.append(agent)
        
        # Log invalid agents for debugging and optionally show to user
        if invalid_agents:
            import logging
            logger = logging.getLogger(__name__)
            for agent in invalid_agents:
                logger.warning(
                    f"Agent '{agent.get('name')}' filtered from selection: {agent.get('validation_error')}"
                )
            
            # Show warning to user if there are invalid agents
            if len(validated_agents) == 0 and len(invalid_agents) > 0:
                # No valid agents available - show error
                self.console.print(
                    f"[red]No valid agents available for selection.[/red]\n"
                    f"[yellow]Found {len(invalid_agents)} agent(s) with configuration issues:[/yellow]"
                )
                for agent in invalid_agents[:5]:  # Show first 5
                    error = agent.get('validation_error', 'Unknown error')
                    self.console.print(f"  • {agent.get('name')} ({agent.get('model', 'unknown')}): {error}")
                if len(invalid_agents) > 5:
                    self.console.print(f"  ... and {len(invalid_agents) - 5} more")
            elif len(invalid_agents) > 0:
                # Some agents filtered but we have valid ones
                # Only log, don't interrupt workflow
                logger.info(
                    f"Filtered {len(invalid_agents)} invalid agent(s) from selection. "
                    f"{len(validated_agents)} valid agent(s) available."
                )
        
        return validated_agents

    def _select_ready_agent(self, prompt: str, default_hint: Optional[str] = None) -> Optional[BaseAgent]:
        """
        Modular function to select a single agent with Ready status.
        
        Args:
            prompt: Prompt text for the selection question
            default_hint: Optional hint text to display
            
        Returns:
            Selected BaseAgent instance or None if cancelled
        """
        ready_agents = self._get_ready_agents_for_selection()
        
        if not ready_agents:
            self.console.print("[red]No agents with Ready status available.[/red]")
            # Check if there are custom agents that aren't ready
            custom_agents: List[Dict[str, Any]] = self.agent_manager.list_agents()
            not_ready_custom: List[Dict[str, Any]] = []
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
                self.console.print(f"[yellow]Found {len(not_ready_custom)} agent(s) with configuration issues.[/yellow]")
                fix_choice = questionary.confirm(
                    "Would you like to diagnose and fix agent configuration issues?",
                    default=True,
                    style=custom_style
                ).ask()
                if fix_choice:
                    self._fix_agent_configuration_issues(not_ready_custom)
                    # Retry after fixing
                    return self._select_ready_agent(prompt, default_hint)
            else:
                self.console.print("[yellow]Please configure agents first.[/yellow]")
            return None
        
        # Build choices from ready agents
        choices = []
        for agent in ready_agents:
            choices.append(f"{agent['icon']} {agent['name']} ({agent['model']})")
        
        choices.append("← Cancel")
        
        # Build prompt text
        prompt_text = prompt
        if default_hint:
            prompt_text += f" (Default: {default_hint})"
        prompt_text += ":"
        
        selected = questionary.select(
            prompt_text,
            choices=choices,
            style=custom_style
        ).ask()
        
        if not selected or "Cancel" in selected:
            return None
        
        # Convert selection to BaseAgent instance
        custom_agents: List[Dict[str, Any]] = self.agent_manager.list_agents()
        all_agents: List[Dict[str, Any]] = self._build_unified_agent_list(custom_agents, set())
        
        # Try to create agent and capture any errors
        try:
            agents: List[BaseAgent] = self._get_agent_from_unified_choice(selected, all_agents, custom_agents)
            
            if not agents:
                # Try to get more details about why it failed
                agent_name: Optional[str] = None
                if "⭐" in selected:
                    try:
                        parts = selected.split("⭐ ", 1)
                        if len(parts) > 1:
                            name_part = parts[1].split(" (")[0]
                            agent_name = name_part.strip()
                    except (IndexError, ValueError):
                        pass
                
                # Find the agent config to get more details
                agent_config = None
                for agent_info in all_agents:
                    if agent_info.get('name') == agent_name:
                        agent_config = agent_info.get('custom_config') or agent_info
                        break
                
                error_msg = f"[red]Error: Could not create agent from selection '{selected}'[/red]"
                if agent_config:
                    agent_type = agent_config.get('type', 'unknown')
                    provider = agent_config.get('provider', 'unknown')
                    model = agent_config.get('model', 'unknown')
                    error_msg += f"\n[dim]Agent Type: {agent_type}, Provider: {provider}, Model: {model}[/dim]"
                    
                    # Provide helpful hints based on agent type
                    if agent_type == 'provider' and provider == 'gemini':
                        error_msg += "\n[yellow]Hint: Check that GOOGLE_API_KEY is set and the model name is valid.[/yellow]"
                        error_msg += "\n[dim]Supported Gemini models: gemini-1.5-flash, gemini-1.5-pro, gemini-2.0-flash-exp[/dim]"
                    elif agent_type == 'provider' and provider == 'anthropic':
                        error_msg += "\n[yellow]Hint: Check that ANTHROPIC_API_KEY is set.[/yellow]"
                    elif agent_type == 'provider' and provider == 'openai':
                        error_msg += "\n[yellow]Hint: Check that OPENAI_API_KEY is set and model name is valid.[/yellow]"
                        error_msg += "\n[dim]Supported OpenAI models: gpt-4, gpt-4-turbo, gpt-3.5-turbo, gpt-4o, gpt-4o-mini[/dim]"
                
                self.console.print(error_msg)
                return None
            
            # Final validation: ensure the created agent is actually valid
            agent = agents[0]
            
            # Validate model name if it's a provider-backed agent
            if hasattr(agent, 'model') and agent.model:
                try:
                    from ..providers.registry import ProviderRegistry
                    ProviderRegistry.discover()
                    
                    # Try to find provider for this model
                    model_lower = agent.model.lower()
                    provider = ProviderRegistry.find_provider_for_model(model_lower)
                    
                    if provider:
                        # Check if model is in supported models
                        supported_models = provider.supported_models or []
                        if supported_models and model_lower not in [m.lower() for m in supported_models]:
                            # Model not in supported list - check for clearly invalid models
                            # Some providers are permissive, but we should catch obvious errors
                            if 'gpt-5' in model_lower or 'gpt-6' in model_lower:
                                # Clearly invalid GPT model (GPT-5 doesn't exist yet)
                                self.console.print(
                                    f"[red]Error: Model '{agent.model}' is not a valid OpenAI model.[/red]\n"
                                    f"[yellow]Supported OpenAI models: gpt-4, gpt-4-turbo, gpt-3.5-turbo, gpt-4o, gpt-4o-mini[/yellow]\n"
                                    f"[dim]Please update your agent configuration with a valid model name.[/dim]"
                                )
                                return None
                            elif provider.name == 'openai' and 'gpt' in model_lower:
                                # OpenAI provider but model not in supported list
                                # Warn but allow (provider might be permissive)
                                self.console.print(
                                    f"[yellow]Warning: Model '{agent.model}' is not in the standard OpenAI model list.[/yellow]\n"
                                    f"[dim]This may cause errors. Supported models: {', '.join(supported_models[:5])}...[/dim]"
                                )
                except Exception:
                    # If provider lookup fails, continue - agent might still work
                    pass
            
            return agent
        except Exception as e:
            # Catch any unexpected errors during agent creation
            import traceback
            error_msg = str(e)
            
            # Check for model-related errors
            if 'not found' in error_msg.lower() or 'not available' in error_msg.lower():
                self.console.print(f"[red]Error: {error_msg}[/red]")
            else:
                self.console.print(f"[red]Error creating agent: {e}[/red]")
                self.console.print(f"[dim]{traceback.format_exc()}[/dim]")
            return None

    def _count_all_available_agents(self, custom_agents: List[Dict[str, Any]]) -> Dict[str, int]:
        """Count all available (working) agents"""
        counts = {'builtin': 0, 'custom': 0, 'total': 0}
        
        # Count built-in agents
        if self.agent_status['mock']['working']:
            counts['builtin'] += 1
        if self.agent_status['claude']['working']:
            counts['builtin'] += 1
        if self.agent_status['gpt4']['working']:
            counts['builtin'] += 1
        
        # Count working custom agents
        for agent in custom_agents:
            agent_type = agent.get('type', 'unknown')
            type_info = CustomAgentManager.AGENT_TYPES.get(agent_type, {})
            api_key_env = type_info.get('api_key_env')
            
            # For openai_compatible, check the agent's own api_key_env
            if agent_type == 'openai_compatible':
                api_key_env = agent.get('api_key_env')
            
            # Check if agent can work
            if api_key_env:
                key_status = self.key_manager.get_key_status(api_key_env)
                if key_status.get('set'):
                    counts['custom'] += 1
            else:
                # No API key needed
                counts['custom'] += 1
        
        counts['total'] = counts['builtin'] + counts['custom']
        return counts

    def _get_agents_from_choice(self, choice: str, custom_agents: List[Dict[str, Any]] = None) -> List[BaseAgent]:
        """Convert choice to list of agents"""
        agents = []
        custom_agents = custom_agents or []
        
        if "ALL AVAILABLE AGENTS" in choice:
            # Run ALL working agents - built-in and custom
            agents = self._get_all_available_agents(custom_agents)
        elif "Mock Agent" in choice and "⭐" not in choice:
            agents.append(MockAgent(name="mock", model="mock-model"))
        elif "Both Claude + GPT-4" in choice:
            if self.agent_status['claude']['working']:
                agents.append(ClaudeAgent())
            if self.agent_status['gpt4']['working']:
                agents.append(GPT4Agent())
        elif "🤖 Claude" in choice:
            if self.agent_status['claude']['working']:
                agents.append(ClaudeAgent())
        elif "🤖 GPT-4" in choice:
            if self.agent_status['gpt4']['working']:
                agents.append(GPT4Agent())
        elif "All User Added Agents" in choice:
            # Run all working user added agents
            agents = self._get_working_custom_agents(custom_agents)
        elif "⭐" in choice:
            # Custom agent selected - find by name
            agent_name = choice.split("⭐ ")[1].split(" (")[0]
            for agent_config in custom_agents:
                if agent_config.get('name') == agent_name:
                    try:
                        instance = self.agent_manager.create_agent_instance(agent_config)
                        if instance:
                            agents.append(instance)
                    except Exception as e:
                        self.console.print(f"[red]Error creating agent: {e}[/red]")
                    break
        
        return agents

    def _get_all_available_agents(self, custom_agents: List[Dict[str, Any]]) -> List[BaseAgent]:
        """Get all available (working) agents - built-in and custom"""
        agents = []
        
        # Add built-in agents
        if self.agent_status['mock']['working']:
            agents.append(MockAgent(name="mock", model="mock-model"))
        
        if self.agent_status['claude']['working']:
            try:
                agents.append(ClaudeAgent())
            except Exception:
                pass
        
        if self.agent_status['gpt4']['working']:
            try:
                agents.append(GPT4Agent())
            except Exception:
                pass
        
        # Add working custom agents
        agents.extend(self._get_working_custom_agents(custom_agents))
        
        return agents

    def _get_working_custom_agents(self, custom_agents: List[Dict[str, Any]]) -> List[BaseAgent]:
        """Get all working custom agents"""
        agents = []
        
        for agent_config in custom_agents:
            agent_type = agent_config.get('type', 'unknown')
            type_info = CustomAgentManager.AGENT_TYPES.get(agent_type, {})
            api_key_env = type_info.get('api_key_env')
            
            # For openai_compatible, check the agent's own api_key_env
            if agent_type == 'openai_compatible':
                api_key_env = agent_config.get('api_key_env')
            
            # Check if agent can work
            can_work = True
            if api_key_env:
                key_status = self.key_manager.get_key_status(api_key_env)
                can_work = key_status.get('set', False)
            
            if can_work:
                try:
                    instance = self.agent_manager.create_agent_instance(agent_config)
                    if instance:
                        agents.append(instance)
                except Exception:
                    pass
        
        return agents

    def _fix_agent_configuration_issues(self, not_ready_agents: List[Dict[str, Any]]):
        """
        Diagnose and help fix agent configuration issues.
        
        Args:
            not_ready_agents: List of agent configs that failed to instantiate
        """
        self.show_header("Fix Agent Configuration Issues")
        
        if not not_ready_agents:
            self.console.print("[green]✓ All agents are ready![/green]")
            questionary.press_any_key_to_continue().ask()
            return
        
        self.console.print(Panel(
            f"[bold]Found {len(not_ready_agents)} agent(s) with configuration issues[/bold]\n\n"
            "This tool will help you diagnose and fix common configuration problems:\n"
            "  • Missing API keys\n"
            "  • Invalid configuration\n"
            "  • Model availability issues\n"
            "  • Network/connection problems",
            border_style="yellow"
        ))
        
        # Diagnose each agent
        issues_table = Table(title="Agent Configuration Issues", show_header=True)
        issues_table.add_column("Agent", style="bold cyan")
        issues_table.add_column("Type", style="magenta")
        issues_table.add_column("Model", style="blue")
        issues_table.add_column("Issue", style="red")
        issues_table.add_column("Fix Available", justify="center")
        
        fixable_agents = []
        
        for agent in not_ready_agents:
            agent_name = agent.get('name', 'unnamed')
            agent_type = agent.get('type', 'unknown')
            agent_model = agent.get('model', 'unknown')
            
            # Try to diagnose the issue
            issue, can_fix = self._diagnose_agent_issue(agent)
            
            if can_fix:
                fixable_agents.append((agent, issue))
                fix_status = "[green]Yes[/green]"
            else:
                fix_status = "[yellow]Manual[/yellow]"
            
            issues_table.add_row(
                agent_name,
                agent_type,
                agent_model,
                issue[:60] + ("..." if len(issue) > 60 else ""),
                fix_status
            )
        
        self.console.print("\n")
        self.console.print(issues_table)
        
        if not fixable_agents:
            self.console.print("\n[yellow]No automatically fixable issues found.[/yellow]")
            self.console.print("[dim]Please check the agent configurations manually.[/dim]")
            questionary.press_any_key_to_continue().ask()
            return
        
        # Offer to fix issues
        self.console.print("\n")
        fix_all = questionary.confirm(
            f"Would you like to fix {len(fixable_agents)} agent(s) automatically?",
            default=True,
            style=custom_style
        ).ask()
        
        if not fix_all:
            # Let user select which ones to fix
            fix_choices = []
            for agent, issue in fixable_agents:
                title = f"{agent.get('name', 'unnamed')} - {issue[:50]}"
                fix_choices.append(title)
            fix_choices.append("← Cancel")
            
            selected = select_with_filter(
                "Select agents to fix:",
                choices=fix_choices,
                style=custom_style
            )
            
            if not selected or "Cancel" in selected:
                return
            
            # Find selected agent
            selected_idx = fix_choices.index(selected) if selected in fix_choices else -1
            if selected_idx >= 0 and selected_idx < len(fixable_agents):
                fixable_agents = [fixable_agents[selected_idx]]
            else:
                return
        
        # Fix each agent
        fixed_count = 0
        for agent, issue in fixable_agents:
            self.console.print(f"\n[cyan]Fixing: {agent.get('name', 'unnamed')}[/cyan]")
            if self._fix_agent_issue(agent, issue):
                fixed_count += 1
                self.console.print(f"[green]✓ Fixed[/green]")
            else:
                self.console.print(f"[red]✗ Could not fix automatically[/red]")
        
        self.console.print(f"\n[green]Fixed {fixed_count}/{len(fixable_agents)} agent(s)[/green]")
        
        # Re-test agents
        self.console.print("\n[yellow]Re-testing agents...[/yellow]")
        self.agent_status = AgentConfigTester.test_all()
        
        questionary.press_any_key_to_continue().ask()

    def _diagnose_agent_issue(self, agent: Dict[str, Any]) -> Tuple[str, bool]:
        """
        Diagnose what's wrong with an agent configuration.
        
        Returns:
            Tuple of (issue_description, can_fix_automatically)
        """
        from typing import Tuple
        
        agent_type = agent.get('type', 'unknown')
        provider_name = agent.get('provider')
        model = agent.get('model', 'unknown')
        
        # Try to create instance to get the actual error
        try:
            instance = self.agent_manager.create_agent_instance(agent)
            if not instance:
                # Provide more specific error message
                agent_type = agent.get('type', 'unknown')
                if agent_type not in ['claude', 'gpt4', 'openai_compatible', 'mock', 'provider']:
                    return f"Invalid agent type: '{agent_type}'. Must be one of: claude, gpt4, openai_compatible, mock, provider", False
                else:
                    return "Agent creation returned None (check model name and configuration)", False
        except Exception as e:
            error_msg = str(e).lower()
            error_class = e.__class__.__name__
            
            # Check for missing API key
            if 'api' in error_msg and ('key' in error_msg or 'token' in error_msg):
                # Determine which key is needed
                if agent_type == 'claude' or provider_name == 'anthropic':
                    return "Missing ANTHROPIC_API_KEY", True
                elif agent_type == 'gpt4' or provider_name == 'openai':
                    return "Missing OPENAI_API_KEY", True
                elif agent_type == 'openai_compatible':
                    api_key_env = agent.get('api_key_env')
                    if api_key_env:
                        return f"Missing {api_key_env}", True
                    return "Missing API key (check configuration)", False
                else:
                    return "Missing API key", False
            
            # Check for model not found
            if 'not found' in error_msg or '404' in error_msg:
                return f"Model '{model}' not found or unavailable", False
            
            # Check for invalid configuration
            if 'invalid' in error_msg or 'configuration' in error_msg:
                return "Invalid configuration", False
            
            # Check for connection errors
            if 'connection' in error_msg or 'network' in error_msg or 'dns' in error_msg:
                return "Network/connection issue", False
            
            # Generic error
            return f"{error_class}: {str(e)[:50]}", False
        
        return "Unknown issue", False

    def _fix_agent_issue(self, agent: Dict[str, Any], issue: str) -> bool:
        """
        Attempt to fix an agent configuration issue.
        
        Returns:
            True if fix was successful, False otherwise
        """
        # Check if it's a missing API key issue
        if "Missing" in issue and "API_KEY" in issue:
            # Extract the key name
            if "ANTHROPIC_API_KEY" in issue:
                self._set_api_key("ANTHROPIC_API_KEY", "Claude (Anthropic)")
                # Re-test
                try:
                    instance = self.agent_manager.create_agent_instance(agent)
                    return instance is not None
                except Exception:
                    return False
            elif "OPENAI_API_KEY" in issue:
                self._set_api_key("OPENAI_API_KEY", "GPT-4 (OpenAI)")
                # Re-test
                try:
                    instance = self.agent_manager.create_agent_instance(agent)
                    return instance is not None
                except Exception:
                    return False
            elif "Missing" in issue:
                # Try to extract key name from issue
                parts = issue.split()
                for i, part in enumerate(parts):
                    if part.endswith("_API_KEY") or part.endswith("_KEY"):
                        key_name = part
                        display_name = agent.get('name', 'Agent')
                        self._set_api_key(key_name, display_name)
                        # Re-test
                        try:
                            instance = self.agent_manager.create_agent_instance(agent)
                            return instance is not None
                        except Exception:
                            return False
        
        return False
