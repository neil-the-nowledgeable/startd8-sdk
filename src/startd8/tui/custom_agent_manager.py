"""Custom agent configuration management.

Extracted verbatim from ``tui_improved.py`` (Pass A refactor).
"""

import json
from typing import Optional, List, Dict, Any, TYPE_CHECKING
from pathlib import Path
from ..paths import default_config_dir

from ..agents import MockAgent, ClaudeAgent, GPT4Agent, OpenAICompatibleAgent, BaseAgent

if TYPE_CHECKING:
    from ..framework import AgentFramework


class CustomAgentManager:
    """Manage custom agent configurations"""

    CONFIG_FILENAME = "custom_agents.json"

    # Available agent types (built-in)
    AGENT_TYPES = {
        'claude': {
            'name': 'Claude',
            'class': 'ClaudeAgent',
            'api_key_env': 'ANTHROPIC_API_KEY',
            'default_model': 'claude-opus-4-8',
            # Model list derives from AnthropicProvider.supported_models at
            # selection time (REQ-TMM-132); no parallel hardcoded copy here.
            'models': []
        },
        'gpt4': {
            'name': 'GPT-4 / OpenAI',
            'class': 'GPT4Agent',
            'api_key_env': 'OPENAI_API_KEY',
            'default_model': 'gpt-5.5-pro',
            # Model list derives from OpenAIProvider.supported_models at
            # selection time (REQ-TMM-132); no parallel hardcoded copy here.
            'models': []
        },
        'openai_compatible': {
            'name': 'OpenAI-Compatible (Cursor, Ollama, etc.)',
            'class': 'OpenAICompatibleAgent',
            'api_key_env': None,  # User specifies
            'default_model': 'custom-model',
            'models': [],  # User specifies
            'requires_base_url': True
        },
        'mock': {
            'name': 'Mock',
            'class': 'MockAgent',
            'api_key_env': None,
            'default_model': 'mock-model',
            'models': ['mock-model']
        }
    }

    # Common OpenAI-compatible providers
    OPENAI_COMPATIBLE_PRESETS = {
        'cursor': {
            'name': 'Cursor',
            'base_url': 'https://api.cursor.sh/v1',
            'api_key_env': 'CURSOR_API_KEY',
            'models': ['cursor-small', 'cursor-large', 'gpt-4o', 'gpt-4o-mini']
        },
        'ollama': {
            'name': 'Ollama (Local)',
            'base_url': 'http://localhost:11434/v1',
            'api_key_env': None,
            'models': ['llama3.3', 'llama3.2', 'mistral', 'codellama', 'mixtral']
        },
        'together': {
            'name': 'Together AI',
            'base_url': 'https://api.together.xyz/v1',
            'api_key_env': 'TOGETHER_API_KEY',
            'models': ['meta-llama/Llama-3.3-70B-Instruct-Turbo', 'mistralai/Mixtral-8x7B-Instruct-v0.1']
        },
        'groq': {
            'name': 'Groq',
            'base_url': 'https://api.groq.com/openai/v1',
            'api_key_env': 'GROQ_API_KEY',
            'models': ['llama-3.3-70b-versatile', 'llama-3.1-8b-instant', 'mixtral-8x7b-32768']
        },
        'openrouter': {
            'name': 'OpenRouter',
            'base_url': 'https://openrouter.ai/api/v1',
            'api_key_env': 'OPENROUTER_API_KEY',
            'models': ['openai/gpt-4o', 'anthropic/claude-sonnet-4', 'meta-llama/llama-3.3-70b-instruct']
        },
        'custom': {
            'name': 'Custom Endpoint',
            'base_url': None,  # User specifies
            'api_key_env': None,  # User specifies
            'models': []
        }
    }

    def __init__(self, storage_dir: Optional[Path] = None, framework: Optional["AgentFramework"] = None):
        """Initialize custom agent manager.

        Args:
            storage_dir: Directory for the custom_agents.json config file.
            framework: Optional AgentFramework used by ``create_agent_instance`` /
                ``_create_builtin_agent`` to apply resilience settings via its
                factory. When None, those methods fall back to direct creation.
        """
        if storage_dir is None:
            storage_dir = default_config_dir()
        self.storage_dir = Path(storage_dir)
        self.config_file = self.storage_dir / self.CONFIG_FILENAME
        self.framework = framework
        self._ensure_storage_dir()

    def _ensure_storage_dir(self):
        """Ensure storage directory exists"""
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def _load_config(self) -> Dict[str, Any]:
        """Load custom agents from config file"""
        if not self.config_file.exists():
            return {'agents': []}
        try:
            with open(self.config_file, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return {'agents': []}

    def _save_config(self, config: Dict[str, Any]):
        """Save custom agents to config file"""
        with open(self.config_file, 'w') as f:
            json.dump(config, f, indent=2)

    def list_agents(self) -> List[Dict[str, Any]]:
        """List all custom agents"""
        config = self._load_config()
        return config.get('agents', [])

    def get_agent(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """Get a specific custom agent by ID"""
        agents = self.list_agents()
        for agent in agents:
            if agent.get('id') == agent_id:
                return agent
        return None

    def add_agent(self, agent_config: Dict[str, Any]) -> str:
        """Add a new custom agent"""
        import uuid

        config = self._load_config()

        # Generate ID if not provided
        if 'id' not in agent_config:
            agent_config['id'] = str(uuid.uuid4())[:8]

        # Add timestamp
        from datetime import datetime, timezone
        agent_config['created'] = datetime.now(timezone.utc).isoformat()

        config['agents'].append(agent_config)
        self._save_config(config)

        return agent_config['id']

    def update_agent(self, agent_id: str, updates: Dict[str, Any]) -> bool:
        """Update an existing custom agent"""
        config = self._load_config()

        for i, agent in enumerate(config['agents']):
            if agent.get('id') == agent_id:
                config['agents'][i].update(updates)
                self._save_config(config)
                return True

        return False

    def delete_agent(self, agent_id: str) -> bool:
        """Delete a custom agent"""
        config = self._load_config()

        original_length = len(config['agents'])
        config['agents'] = [a for a in config['agents'] if a.get('id') != agent_id]

        if len(config['agents']) < original_length:
            self._save_config(config)
            return True

        return False

    def create_agent_instance(self, agent_config: Dict[str, Any]) -> Optional[BaseAgent]:
        """Create an agent instance from a custom config.

        Uses the framework's create_agent method when available to apply
        resilience settings (retry config, etc.) automatically.
        """
        agent_type = agent_config.get('type')
        model = agent_config.get('model', '')
        name = agent_config.get('name')
        max_tokens = agent_config.get('max_tokens', 4096)

        # Use framework's factory method for standard agent types
        # This automatically applies retry config from ResilienceConfig
        if self.framework and agent_type in ('claude', 'gpt4', 'gemini', 'mock'):
            try:
                return self.framework.create_agent(
                    agent_type=agent_type,
                    name=name,
                    model=model if model else None,
                    max_tokens=max_tokens
                )
            except (ValueError, ImportError):
                # Fall back to direct creation
                pass

        # Direct creation (fallback or for types not supported by framework)
        if agent_type == 'claude':
            return ClaudeAgent(
                name=name or 'claude',
                model=model or 'claude-opus-4-8',
                max_tokens=max_tokens
            )
        elif agent_type == 'gpt4':
            return GPT4Agent(
                name=name or 'gpt4',
                model=model or 'gpt-5.5-pro',
                max_tokens=max_tokens
            )
        elif agent_type == 'openai_compatible':
            # Create OpenAI-compatible agent with custom base URL
            base_url = agent_config.get('base_url')
            if not base_url:
                # If no base_url but model looks like a GPT model, might be misconfigured
                # Try to help by checking if it should be gpt4 type instead
                if model and ('gpt' in model.lower() or 'openai' in model.lower()):
                    # This might be a GPT model that should use gpt4 type
                    # But we'll still create it as openai_compatible if that's what user configured
                    pass
            return OpenAICompatibleAgent(
                name=agent_config.get('name', 'custom'),
                model=model or 'custom-model',
                max_tokens=agent_config.get('max_tokens', 4096),
                base_url=base_url,
                api_key_env=agent_config.get('api_key_env')
            )
        elif agent_type == 'mock':
            return MockAgent(
                name=agent_config.get('name', 'mock'),
                model=model or 'mock-model'
            )
        elif agent_type == 'provider':
            # Handle provider-backed agents (newer format)
            # Use ProviderRegistry for proper provider handling
            provider_name = agent_config.get('provider')
            if not provider_name and model:
                # Try to infer provider from model name
                model_lower = model.lower()
                if 'gemini' in model_lower:
                    provider_name = 'gemini'
                elif 'gpt' in model_lower or 'openai' in model_lower:
                    provider_name = 'openai'
                elif 'claude' in model_lower:
                    provider_name = 'anthropic'

            if provider_name:
                try:
                    from ..providers.registry import ProviderRegistry
                    ProviderRegistry.discover()
                    provider = ProviderRegistry.get_provider(provider_name.lower())

                    if provider:
                        # Use provider to create agent (handles model validation, etc.)
                        return provider.create_agent(
                            model=model or provider.supported_models[0] if provider.supported_models else 'unknown',
                            name=agent_config.get('name'),
                            api_key=agent_config.get('api_key'),
                            max_tokens=agent_config.get('max_tokens', 4096),
                            temperature=agent_config.get('temperature'),
                            **{k: v for k, v in agent_config.items()
                               if k not in ['type', 'provider', 'name', 'model', 'api_key', 'max_tokens', 'temperature']}
                        )
                except (ImportError, AttributeError, ValueError) as e:
                    # Log specific provider registry errors
                    from ..logging_config import get_logger
                    logger = get_logger(__name__)
                    logger.debug(
                        f"Failed to create agent via ProviderRegistry: {e}",
                        exc_info=True,
                        extra={
                            "operation": "create_agent_via_provider",
                            "provider": provider_name,
                            "model": model
                        }
                    )
                except Exception as e:
                    # Log unexpected errors but fall through to manual creation
                    from ..logging_config import get_logger
                    logger = get_logger(__name__)
                    logger.warning(
                        f"Unexpected error creating agent via ProviderRegistry: {e}",
                        exc_info=True,
                        extra={
                            "operation": "create_agent_via_provider",
                            "provider": provider_name,
                            "model": model
                        }
                    )

            # Fallback to framework.create_agent or manual creation if ProviderRegistry fails
            fallback_type = None
            if provider_name == 'openai' or (model and 'gpt' in model.lower()):
                fallback_type = 'gpt4'
            elif provider_name == 'anthropic' or (model and 'claude' in model.lower()):
                fallback_type = 'claude'
            elif provider_name == 'gemini' or (model and 'gemini' in model.lower()):
                fallback_type = 'gemini'

            if fallback_type:
                # Try framework factory first for resilience settings
                if self.framework:
                    try:
                        return self.framework.create_agent(
                            agent_type=fallback_type,
                            name=name,
                            model=model if model else None,
                            max_tokens=max_tokens
                        )
                    except (ValueError, ImportError):
                        pass

                # Direct creation fallback
                if fallback_type == 'gpt4':
                    return GPT4Agent(
                        name=name or 'gpt4',
                        model=model or 'gpt-5.5-pro',
                        max_tokens=max_tokens
                    )
                elif fallback_type == 'claude':
                    return ClaudeAgent(
                        name=name or 'claude',
                        model=model or 'claude-opus-4-8',
                        max_tokens=max_tokens
                    )
                elif fallback_type == 'gemini':
                    from ..agents import GeminiAgent
                    return GeminiAgent(
                        name=name or 'gemini',
                        model=model or 'gemini-2.5-pro',
                        max_tokens=max_tokens,
                        temperature=agent_config.get('temperature', 0.7),
                        api_key=agent_config.get('api_key')
                    )
            # Fall through to None if provider type not recognized

        return None

    def _create_builtin_agent(self, agent_type: str, **kwargs) -> Optional[BaseAgent]:
        """Create a built-in agent with resilience settings from framework.

        Helper method for creating agents throughout the TUI.
        Uses framework.create_agent when available for retry/resilience config.

        Args:
            agent_type: Type of agent ('claude', 'gpt4', 'gemini', 'mock')
            **kwargs: Additional arguments to pass to the agent

        Returns:
            Configured agent instance, or None if creation fails
        """
        if self.framework:
            try:
                return self.framework.create_agent(agent_type=agent_type, **kwargs)
            except (ValueError, ImportError):
                pass

        # Fallback to direct creation
        if agent_type == 'claude':
            return ClaudeAgent(
                name=kwargs.get('name', 'claude'),
                model=kwargs.get('model', 'claude-opus-4-8'),
                max_tokens=kwargs.get('max_tokens', 4096)
            )
        elif agent_type == 'gpt4':
            return GPT4Agent(
                name=kwargs.get('name', 'gpt4'),
                model=kwargs.get('model', 'gpt-5.5-pro'),
                max_tokens=kwargs.get('max_tokens', 4096)
            )
        elif agent_type == 'mock':
            return MockAgent(
                name=kwargs.get('name', 'mock'),
                model=kwargs.get('model', 'mock-model')
            )
        elif agent_type == 'gemini':
            try:
                from ..agents import GeminiAgent
                return GeminiAgent(
                    name=kwargs.get('name', 'gemini'),
                    model=kwargs.get('model', 'gemini-2.5-pro'),
                    max_tokens=kwargs.get('max_tokens', 4096)
                )
            except ImportError:
                return None

        return None
