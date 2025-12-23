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
from .agents import MockAgent, ClaudeAgent, GPT4Agent, OpenAICompatibleAgent, ComposerAgent, BaseAgent
from .orchestration import Pipeline, WorkflowTemplates
from .document_enhancement import DocumentEnhancementChain
from .iterative_workflow import IterativeDevWorkflow, IterativeWorkflowResult, save_workflow_result
from .config import ConfigManager
from .tui_help_system import HelpSystem
from .tui_workflow_help import WorkflowHelper
from .error_analysis import (
    get_last_error_from_logs,
    format_error_for_analysis,
)
from .paths import default_config_dir, default_data_dir
from .models import (
    DocumentEnhancementConfig,
    AgentConfig as EnhancementAgentConfig,
    ErrorHandling
)
from .exceptions import AgentError, APIError, ConfigurationError

# Prompt Builder imports (lazy loaded to avoid circular imports)
_prompt_builder_loaded = False
TemplateLoader = None
ProjectContext = None
PromptGenerator = None
run_prompt_builder_wizard = None
select_template = None
list_templates_table = None

# Job Queue imports (lazy loaded)
_job_queue_loaded = False
JobQueue = None
JobQueueConfig = None
JobFile = None
JobStatus = None
create_job_file = None
load_queue_config = None
save_queue_config = None


def _load_job_queue():
    """Lazy load job queue module"""
    global _job_queue_loaded, JobQueue, JobQueueConfig, JobFile, JobStatus
    global create_job_file, load_queue_config, save_queue_config
    
    if _job_queue_loaded:
        return True
    
    try:
        from .job_queue import (
            JobQueue as JQ,
            JobQueueConfig as JQC,
            create_job_file as cjf,
            load_queue_config as lqc,
            save_queue_config as sqc
        )
        from .models import JobFile as JF, JobStatus as JS
        
        JobQueue = JQ
        JobQueueConfig = JQC
        JobFile = JF
        JobStatus = JS
        create_job_file = cjf
        load_queue_config = lqc
        save_queue_config = sqc
        _job_queue_loaded = True
        return True
    except ImportError as e:
        console.print(f"[yellow]Job Queue not available: {e}[/yellow]")
        return False


def _load_prompt_builder():
    """Lazy load prompt builder module"""
    global _prompt_builder_loaded, TemplateLoader, ProjectContext, PromptGenerator
    global run_prompt_builder_wizard, select_template, list_templates_table
    
    if _prompt_builder_loaded:
        return True
    
    try:
        from .prompt_builder import TemplateLoader as TL, ProjectContext as PC, PromptGenerator as PG
        from .tui_prompt_builder import run_prompt_builder_wizard as rpbw, select_template as st, list_templates_table as ltt
        
        TemplateLoader = TL
        ProjectContext = PC
        PromptGenerator = PG
        run_prompt_builder_wizard = rpbw
        select_template = st
        list_templates_table = ltt
        _prompt_builder_loaded = True
        return True
    except ImportError as e:
        console.print(f"[yellow]Prompt Builder not available: {e}[/yellow]")
        return False


console = Console()


class APIKeyManager:
    """Manage API keys with secure storage"""
    
    CONFIG_FILENAME = "api_keys.json"
    
    def __init__(self, storage_dir: Optional[Path] = None):
        """Initialize API key manager"""
        if storage_dir is None:
            storage_dir = Path.home() / ".startd8"
        self.storage_dir = Path(storage_dir)
        self.config_file = self.storage_dir / self.CONFIG_FILENAME
        self._ensure_storage_dir()
    
    def _ensure_storage_dir(self):
        """Ensure storage directory exists"""
        self.storage_dir.mkdir(parents=True, exist_ok=True)
    
    def _load_config(self) -> Dict[str, str]:
        """Load API keys from config file"""
        if not self.config_file.exists():
            return {}
        try:
            with open(self.config_file, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return {}
    
    def _save_config(self, config: Dict[str, str]):
        """Save API keys to config file"""
        # Set restrictive permissions (readable only by owner)
        with open(self.config_file, 'w') as f:
            json.dump(config, f, indent=2)
        # Try to set file permissions (Unix-like systems)
        try:
            os.chmod(self.config_file, 0o600)
        except (OSError, AttributeError):
            pass  # Windows or permission error - skip
    
    def get_key(self, key_name: str) -> Optional[str]:
        """Get an API key (checks env first, then config file)"""
        # Environment variable takes precedence
        env_key = os.getenv(key_name)
        if env_key:
            return env_key
        
        # Check config file
        config = self._load_config()
        return config.get(key_name)
    
    def set_key(self, key_name: str, key_value: str):
        """Set an API key in config file and environment"""
        config = self._load_config()
        config[key_name] = key_value
        self._save_config(config)
        
        # Also set in environment for current session
        os.environ[key_name] = key_value
    
    def delete_key(self, key_name: str):
        """Delete an API key from config file"""
        config = self._load_config()
        if key_name in config:
            del config[key_name]
            self._save_config(config)
        
        # Also remove from environment
        if key_name in os.environ:
            del os.environ[key_name]
    
    def load_all_keys(self):
        """Load all stored keys into environment variables"""
        config = self._load_config()
        for key_name, key_value in config.items():
            if not os.getenv(key_name):  # Don't override existing env vars
                os.environ[key_name] = key_value
    
    def get_key_status(self, key_name: str) -> Dict[str, Any]:
        """Get status of a key (source and masked value)"""
        env_key = os.getenv(key_name)
        config = self._load_config()
        stored_key = config.get(key_name)
        
        if env_key:
            source = "environment" if key_name not in config else "config (loaded)"
            masked = self._mask_key(env_key)
            return {'set': True, 'source': source, 'masked': masked}
        elif stored_key:
            return {'set': True, 'source': 'config', 'masked': self._mask_key(stored_key)}
        else:
            return {'set': False, 'source': None, 'masked': None}
    
    @staticmethod
    def _mask_key(key: str) -> str:
        """Mask an API key for display"""
        if len(key) <= 8:
            return '*' * len(key)
        return key[:4] + '*' * (len(key) - 8) + key[-4:]
    
    def export_keys(self, output_path: Path, password: str, key_names: Optional[List[str]] = None) -> bool:
        """
        Export API keys to encrypted file.
        
        Args:
            output_path: Path to save encrypted export
            password: Encryption password
            key_names: Optional list of specific keys to export (None = all)
            
        Returns:
            True if successful
        """
        try:
            from .security import KeyEncryption
            from datetime import datetime, timezone
            
            # Load all keys
            config = self._load_config()
            
            # Filter keys if specified
            if key_names:
                api_keys = {k: v for k, v in config.items() if k in key_names}
            else:
                api_keys = config.copy()
            
            if not api_keys:
                return False
            
            # Encrypt and save
            encryptor = KeyEncryption()
            metadata = {
                'exported_at': datetime.now(timezone.utc).isoformat(),
                'key_count': len(api_keys),
                'key_names': list(api_keys.keys())
            }
            encrypted = encryptor.encrypt_api_keys(api_keys, password, metadata)
            
            # Write to file
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, 'w') as f:
                f.write(encrypted)
            
            # Set restrictive permissions
            try:
                os.chmod(output_path, 0o600)
            except (OSError, AttributeError):
                pass
            
            return True
            
        except Exception:
            return False
    
    def import_keys(self, input_path: Path, password: str, overwrite: bool = False) -> Dict[str, Any]:
        """
        Import API keys from encrypted file.
        
        Args:
            input_path: Path to encrypted export file
            password: Decryption password
            overwrite: Whether to overwrite existing keys
            
        Returns:
            Dictionary with status: {
                'success': bool,
                'imported': List[str],
                'skipped': List[str],
                'error': Optional[str]
            }
        """
        result = {
            'success': False,
            'imported': [],
            'skipped': [],
            'error': None
        }
        
        try:
            from .security import KeyEncryption
            
            if not input_path.exists():
                result['error'] = f"File not found: {input_path}"
                return result
            
            # Read and decrypt
            with open(input_path, 'r') as f:
                encrypted = f.read()
            
            encryptor = KeyEncryption()
            package = encryptor.decrypt_api_keys(encrypted, password)
            imported_keys = package['api_keys']
            
            # Load current config
            config = self._load_config()
            
            # Import keys
            for key_name, key_value in imported_keys.items():
                if key_name in config and not overwrite:
                    result['skipped'].append(key_name)
                else:
                    config[key_name] = key_value
                    result['imported'].append(key_name)
            
            # Save updated config
            if result['imported']:
                self._save_config(config)
                # Load into environment
                self.load_all_keys()
            
            result['success'] = True
            return result
            
        except Exception as e:
            result['error'] = str(e)
            return result


class CustomAgentManager:
    """Manage custom agent configurations"""
    
    CONFIG_FILENAME = "custom_agents.json"
    
    # Available agent types (built-in)
    AGENT_TYPES = {
        'claude': {
            'name': 'Claude',
            'class': 'ClaudeAgent',
            'api_key_env': 'ANTHROPIC_API_KEY',
            'default_model': 'claude-sonnet-4-20250514',
            'models': [
                'claude-sonnet-4-20250514',
                'claude-3-5-sonnet-20241022',
                'claude-3-opus-20240229',
                'claude-3-haiku-20240307',
            ]
        },
        'gpt4': {
            'name': 'GPT-4 / OpenAI',
            'class': 'GPT4Agent',
            'api_key_env': 'OPENAI_API_KEY',
            'default_model': 'gpt-4-turbo-preview',
            'models': [
                'gpt-4-turbo-preview',
                'gpt-4-turbo',
                'gpt-4',
                'gpt-4o',
                'gpt-4o-mini',
                'gpt-3.5-turbo',
                'gpt-5.2-pro',
            ]
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
            'models': ['cursor-small', 'cursor-large', 'gpt-4', 'gpt-3.5-turbo']
        },
        'ollama': {
            'name': 'Ollama (Local)',
            'base_url': 'http://localhost:11434/v1',
            'api_key_env': None,
            'models': ['llama2', 'llama3', 'mistral', 'codellama', 'mixtral']
        },
        'together': {
            'name': 'Together AI',
            'base_url': 'https://api.together.xyz/v1',
            'api_key_env': 'TOGETHER_API_KEY',
            'models': ['meta-llama/Llama-3-70b-chat-hf', 'mistralai/Mixtral-8x7B-Instruct-v0.1']
        },
        'groq': {
            'name': 'Groq',
            'base_url': 'https://api.groq.com/openai/v1',
            'api_key_env': 'GROQ_API_KEY',
            'models': ['llama3-8b-8192', 'llama3-70b-8192', 'mixtral-8x7b-32768']
        },
        'openrouter': {
            'name': 'OpenRouter',
            'base_url': 'https://openrouter.ai/api/v1',
            'api_key_env': 'OPENROUTER_API_KEY',
            'models': ['openai/gpt-4-turbo', 'anthropic/claude-3-opus', 'meta-llama/llama-3-70b-instruct']
        },
        'custom': {
            'name': 'Custom Endpoint',
            'base_url': None,  # User specifies
            'api_key_env': None,  # User specifies
            'models': []
        }
    }
    
    def __init__(self, storage_dir: Optional[Path] = None):
        """Initialize custom agent manager"""
        if storage_dir is None:
            storage_dir = Path.home() / ".startd8"
        self.storage_dir = Path(storage_dir)
        self.config_file = self.storage_dir / self.CONFIG_FILENAME
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
        """Create an agent instance from a custom config"""
        agent_type = agent_config.get('type')
        model = agent_config.get('model', '')
        
        if agent_type == 'claude':
            return ClaudeAgent(
                name=agent_config.get('name', 'claude'),
                model=model or 'claude-sonnet-4-20250514',
                max_tokens=agent_config.get('max_tokens', 4096)
            )
        elif agent_type == 'gpt4':
            return GPT4Agent(
                name=agent_config.get('name', 'gpt4'),
                model=model or 'gpt-4-turbo-preview',
                max_tokens=agent_config.get('max_tokens', 4096)
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
                    from .providers.registry import ProviderRegistry
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
                except Exception as e:
                    # Log error but fall through to manual creation
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.warning(f"Failed to create agent via ProviderRegistry: {e}")
            
            # Fallback to manual creation if ProviderRegistry fails
            if provider_name == 'openai' or (model and 'gpt' in model.lower()):
                # Treat as GPT-4 agent
                return GPT4Agent(
                    name=agent_config.get('name', 'gpt4'),
                    model=model or 'gpt-4-turbo-preview',
                    max_tokens=agent_config.get('max_tokens', 4096)
                )
            elif provider_name == 'anthropic' or (model and 'claude' in model.lower()):
                # Treat as Claude agent
                return ClaudeAgent(
                    name=agent_config.get('name', 'claude'),
                    model=model or 'claude-sonnet-4-20250514',
                    max_tokens=agent_config.get('max_tokens', 4096)
                )
            elif provider_name == 'gemini' or (model and 'gemini' in model.lower()):
                # Treat as Gemini agent
                from .agents import GeminiAgent
                return GeminiAgent(
                    name=agent_config.get('name', 'gemini'),
                    model=model or 'gemini-1.5-flash',
                    max_tokens=agent_config.get('max_tokens', 4096),
                    temperature=agent_config.get('temperature', 0.7),
                    api_key=agent_config.get('api_key')
                )
            # Fall through to None if provider type not recognized
        
        return None


# Custom style
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


class AgentConfigTester:
    """Test agent configurations"""
    
    @staticmethod
    def test_claude() -> Dict[str, Any]:
        """Test Claude configuration"""
        result = {
            'name': 'Claude',
            'configured': False,
            'working': False,
            'error': None
        }
        
        # Check API key
        api_key = os.getenv('ANTHROPIC_API_KEY')
        if not api_key:
            result['error'] = 'ANTHROPIC_API_KEY not set'
            return result
        
        result['configured'] = True
        
        # Try to initialize
        try:
            agent = ClaudeAgent()
            result['working'] = True
        except Exception as e:
            result['error'] = str(e)
        
        return result
    
    @staticmethod
    def test_gpt4() -> Dict[str, Any]:
        """Test GPT-4 configuration"""
        result = {
            'name': 'GPT-4',
            'configured': False,
            'working': False,
            'error': None
        }
        
        # Check API key
        api_key = os.getenv('OPENAI_API_KEY')
        if not api_key:
            result['error'] = 'OPENAI_API_KEY not set'
            return result
        
        result['configured'] = True
        
        # Try to initialize
        try:
            agent = GPT4Agent()
            result['working'] = True
        except Exception as e:
            result['error'] = str(e)
        
        return result
    
    @staticmethod
    def test_all() -> Dict[str, Dict[str, Any]]:
        """Test all agent configurations"""
        return {
            'claude': AgentConfigTester.test_claude(),
            'gpt4': AgentConfigTester.test_gpt4(),
            'mock': {
                'name': 'Mock',
                'configured': True,
                'working': True,
                'error': None
            }
        }


class ImprovedTUI:
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
            self.agent_manager = CustomAgentManager(storage_dir)
        except Exception as e:
            console.print(f"[yellow]Warning: Failed to load custom agents: {e}[/yellow]", style="yellow")
            self.agent_manager = CustomAgentManager(storage_dir)
        
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
        
        # TUI settings file for tracking first-run and preferences
        self._tui_settings_file = (self.storage_dir or Path.home() / ".startd8") / "tui_settings.json"
        self._tui_settings = self._load_tui_settings()
    
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
        """Check if this is first run and offer to set up agent folders"""
        if self._tui_settings.get('first_run_complete'):
            # Not first run, but still ensure folders exist if enabled
            if self._tui_settings.get('agent_folders_enabled'):
                self._ensure_agent_folders_exist()
            return
        
        self.show_header("First-Time Setup")
        
        self.console.print(Panel(
            "[bold cyan]Welcome to startd8![/bold cyan]\n\n"
            "This appears to be your first time running the TUI.\n"
            "Let's configure a few things to get you started.\n\n"
            "[bold]Agent Output Folders[/bold]\n"
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
            title="🚀 First-Time Setup"
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
        
        base_dir = self._tui_settings.get('agent_folders_base_dir')
        if not base_dir:
            return None
        
        base_path = Path(base_dir)
        folder_name = agent_name.lower().replace(' ', '-')
        agent_folder = base_path / folder_name
        
        try:
            agent_folder.mkdir(parents=True, exist_ok=True)
            return str(agent_folder)
        except Exception:
            return None
        
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
                table.add_column("Model", style="blue")
                table.add_column("Max Tokens", justify="right")
                table.add_column("Output Dir", style="green")
                
                for agent in custom_agents:
                    output_dir = agent.get('output_dir', '')
                    # Truncate long paths for display
                    output_display = output_dir if len(output_dir) <= 25 else "..." + output_dir[-22:]
                    table.add_row(
                        agent.get('id', '-')[:8],
                        agent.get('name', 'unnamed'),
                        agent.get('type', 'unknown'),
                        agent.get('model', 'default'),
                        str(agent.get('max_tokens', '-')),
                        output_display or "[dim]default[/dim]"
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
        
        # Select model
        if type_info.get('models'):
            # Add option to enter custom model name
            model_choices = type_info['models'] + ["✏️  Enter custom model name"]
            model = questionary.select(
                "Select model:",
                choices=model_choices,
                default=type_info.get('default_model'),
                style=custom_style
            ).ask()
            
            # If user selected custom model option
            if model == "✏️  Enter custom model name":
                model = questionary.text(
                    "Enter model name:",
                    style=custom_style
                ).ask()
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
        
        # Edit model
        if type_info.get('models'):
            # Add option to enter custom model name
            model_choices = type_info['models'] + ["✏️  Enter custom model name"]
            current_model = agent.get('model', type_info.get('default_model'))
            # If current model is not in the list, add it as an option
            if current_model and current_model not in type_info['models']:
                model_choices.insert(-1, f"📌 {current_model} (current)")
            
            new_model = questionary.select(
                "Select model:",
                choices=model_choices,
                default=current_model if current_model in type_info['models'] else None,
                style=custom_style
            ).ask()
            
            # Handle custom model selection
            if new_model == "✏️  Enter custom model name":
                new_model = questionary.text(
                    "Enter model name:",
                    default=current_model if current_model and current_model not in type_info['models'] else "",
                    style=custom_style
                ).ask()
            elif new_model.startswith("📌 "):
                # User selected the current custom model, keep it
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
        choices.append("🔄 Iterative Dev Workflow (Dev → Review → Fix)")
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
        choices.append("🔬 Test Agent Connections")
        choices.append("🔧 Fix Agent Configuration Issues")
        choices.append("🤖 Manage Agents")
        choices.append("🔑 Manage API Keys")
        
        # System section
        choices.append(questionary.Separator("═══ SYSTEM ═══"))
        choices.append("🔍 Analyze Last Error")
        choices.append("🔍 Analyze Agent Config Errors")
        choices.append("📁 Manage Output Folders")
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
    
    def step1_create_prompt(self):
        """Step 1: Create a prompt"""
        self.show_header("Step 1: Create Prompt")
        
        # Show workflow intro if available
        if self.workflow_helper and self.workflow_helper.has_workflow_help("create_prompt"):
            show_intro = questionary.confirm(
                "\nWould you like to see an overview of this workflow?",
                default=False,
                style=custom_style
            ).ask()
            
            if show_intro:
                self.workflow_helper.show_workflow_intro("create_prompt")
        else:
            # Fallback to simple help
            self.console.print(Panel(
                "[bold]Creating a Prompt[/bold]\n\n"
                "A prompt is the question or task you want to send to LLMs.\n"
                "Example: 'Explain quantum computing in simple terms'\n\n"
                "The prompt will be versioned and stored for tracking.",
                border_style="cyan"
            ))
        
        # Offer contextual help
        show_help = questionary.confirm(
            "\nWould you like help with creating prompts?",
            default=False,
            style=custom_style
        ).ask()
        
        if show_help and self.help_system:
            self.help_system.show_contextual_help("prompt_creation")
        
        # Get prompt text
        prompt_text = questionary.text(
            "\nEnter your prompt:",
            style=custom_style,
        ).ask()
        
        if not prompt_text:
            return
        
        # Get tags (optional)
        tags_input = questionary.text(
            "Add tags (optional, comma-separated):",
            style=custom_style,
        ).ask()
        
        tags = [t.strip() for t in tags_input.split(",")] if tags_input else []
        
        # Create prompt
        self.console.print("\n[cyan]Creating prompt...[/cyan]")
        
        self.current_prompt = self.framework.create_prompt(
            content=prompt_text,
            version="1.0.0",
            tags=tags
        )
        
        self.console.print()
        self.console.print(Panel(
            f"[green]✓ Prompt Created Successfully![/green]\n\n"
            f"[bold]Prompt ID:[/bold] {self.current_prompt.id}\n"
            f"[bold]Version:[/bold] {self.current_prompt.version}\n"
            f"[bold]Tags:[/bold] {', '.join(self.current_prompt.tags) if self.current_prompt.tags else 'None'}\n\n"
            f"[bold]Content:[/bold]\n{self.current_prompt.content}",
            title="✅ Prompt Stored",
            border_style="green"
        ))
        
        # Next step suggestion
        next_step = questionary.select(
            "\nWhat next?",
            choices=[
                "2️⃣  Distribute this prompt to agents now",
                "← Back to main menu"
            ],
            style=custom_style
        ).ask()
        
        if "Distribute" in next_step:
            self.step2_distribute_prompt()
    
    def step2_run_design_review_chain(self):
        """Run the Design Review Chain workflow"""
        self.show_header("Run Design Pipeline")
        
        # Show workflow intro with help
        if self.workflow_helper and self.workflow_helper.has_workflow_help("design_pipeline"):
            self.workflow_helper.show_workflow_intro("design_pipeline")
        else:
            self.console.print(Panel(
                "🚀 [bold cyan]Design Review Pipeline[/bold cyan]\n\n"
                "Sequential workflow:\n"
                "  1. [bold]Draft[/bold] (Sonnet 4.5) - Create initial design\n"
                "  2. [bold]Review[/bold] (OpenAI) - Critique and find gaps\n"
                "  3. [bold]Polish[/bold] (Composer) - Finalize document\n",
                border_style="cyan"
            ))
        
        # Offer to see examples
        show_examples = questionary.confirm(
            "\nWould you like to see workflow examples?",
            default=False,
            style=custom_style
        ).ask()
        
        if show_examples and self.workflow_helper:
            self.workflow_helper.show_workflow_examples("design_pipeline")

        # 1. Get Prompt
        prompt_text = questionary.text(
            "\nEnter the design task or feature description:",
            style=custom_style
        ).ask()
        
        if not prompt_text:
            return

        # Ensure agent status is up to date
        self.agent_status = AgentConfigTester.test_all()
        
        # 2. Select Agents (using modular ready agent selection)
        self.console.print("\n[bold]Select Agents for Pipeline Steps:[/bold]")
        
        # Show available ready agents
        ready_agents = self._get_ready_agents_for_selection()
        if not ready_agents:
            self.console.print("[red]No agents with Ready status available. Please configure agents first.[/red]")
            questionary.press_any_key_to_continue().ask()
            return
        
        # Display ready agents table
        agent_table = Table(title="Available Agents (Ready Status)", show_header=True)
        agent_table.add_column("", justify="center", width=3)  # Icon
        agent_table.add_column("Agent", style="bold cyan")
        agent_table.add_column("Model", style="cyan")
        agent_table.add_column("Type", style="magenta")
        
        for agent in ready_agents:
            agent_type = "Built-in" if agent['type'] == 'builtin' else "User added"
            agent_table.add_row(
                agent['icon'],
                agent['name'],
                agent['model'],
                agent_type
            )
        
        self.console.print(agent_table)
        self.console.print()
        
        # Drafter
        drafter = self._select_ready_agent("Select Agent for DRAFTER", "Sonnet 4.5")
        if not drafter: return
        
        # Reviewer
        reviewer = self._select_ready_agent("Select Agent for REVIEWER", "OpenAI")
        if not reviewer: return
        
        # Final Reviewer
        final_reviewer = self._select_ready_agent("Select Agent for FINAL POLISH", "Composer")
        if not final_reviewer: return
        
        # 3. Run Pipeline
        self.console.print(f"\n[cyan]Running Pipeline...[/cyan]")
        self.console.print(f"  1. Drafter: {drafter.name}")
        self.console.print(f"  2. Reviewer: {reviewer.name}")
        self.console.print(f"  3. Final:   {final_reviewer.name}\n")
        
        try:
            pipeline = WorkflowTemplates.design_review_chain(drafter, reviewer, final_reviewer)
            pipeline.framework = self.framework
            
            with self.console.status("[bold green]Executing pipeline steps...[/bold green]") as status:
                result = pipeline.run(prompt_text)
            
            # 4. Show Result
            self.console.print("\n[green]✓ Pipeline Complete![/green]\n")
            
            self.console.print(Panel(
                result.final_output,
                title="Final Design Document",
                border_style="green"
            ))
            
            # 5. Save
            save = questionary.confirm(
                "Save result to file?",
                default=True,
                style=custom_style
            ).ask()
            
            if save:
                filename = questionary.text(
                    "Filename:",
                    default=f"design_doc_{result.pipeline_id[:8]}.md",
                    style=custom_style
                ).ask()
                
                if filename:
                    with open(filename, 'w') as f:
                        f.write(f"# Design Pipeline Result\n\n")
                        f.write(f"**Task:** {prompt_text}\n\n")
                        f.write("---\n\n")
                        f.write(result.final_output)
                        f.write("\n\n---\n")
                        f.write("## Pipeline Steps\n")
                        for step in result.steps:
                            f.write(f"### {step['step_name']} ({step['agent']})\n")
                            f.write(f"{step['output']}\n\n")
                    
                    self.console.print(f"[green]Saved to {filename}[/green]")
        except Exception as e:
            self.console.print(f"\n[red]Pipeline failed: {e}[/red]")
        
        questionary.press_any_key_to_continue().ask()

    def run_design_polish_pipeline(self):
        """Run the Design Polish Pipeline workflow (Polish → Suggest Updates → Final Polish)"""
        self.show_header("Design Polish Pipeline")
        
        self.console.print(Panel(
            "✨ [bold cyan]Design Polish Pipeline[/bold cyan]\n\n"
            "Sequential workflow for refining existing design documents:\n"
            "  1. [bold]Polish[/bold] - Initial polish pass\n"
            "  2. [bold]Suggest Updates[/bold] - Review and suggest improvements\n"
            "  3. [bold]Final Polish[/bold] - Incorporate suggestions and finalize\n",
            border_style="cyan"
        ))
        
        # 1. Get document input (file or text)
        input_method = questionary.select(
            "Choose input method:",
            choices=[
                "📁 Load from file",
                "✏️  Paste document text",
                "← Cancel"
            ],
            style=custom_style
        ).ask()
        
        if not input_method or "Cancel" in input_method:
            return
        
        document_text = None
        original_doc_path = None  # Track original file path for saving next to it
        
        if "file" in input_method.lower():
            file_path = self._safe_path_input(
                "Path to design document:",
                only_directories=False,
                style=custom_style
            )
            
            if not file_path:
                return
            
            doc_path = Path(file_path).expanduser()
            if not doc_path.exists():
                self.console.print(f"[red]File not found: {doc_path}[/red]")
                questionary.press_any_key_to_continue().ask()
                return
            
            try:
                document_text = doc_path.read_text(encoding='utf-8')
                original_doc_path = doc_path  # Store original path for later use
            except Exception as e:
                self.console.print(f"[red]Error reading file: {e}[/red]")
                questionary.press_any_key_to_continue().ask()
                return
        else:
            # Paste text
            document_text = questionary.text(
                "Paste the design document text:",
                multiline=True,
                style=custom_style
            ).ask()
        
        if not document_text or not document_text.strip():
            self.console.print("[yellow]No document text provided.[/yellow]")
            questionary.press_any_key_to_continue().ask()
            return
        
        # Ensure agent status is up to date
        self.agent_status = AgentConfigTester.test_all()
        
        # 2. Select Agents
        self.console.print("\n[bold]Select Agents for Pipeline Steps:[/bold]")
        
        # Show available ready agents
        ready_agents = self._get_ready_agents_for_selection()
        if not ready_agents:
            self.console.print("[red]No agents with Ready status available. Please configure agents first.[/red]")
            questionary.press_any_key_to_continue().ask()
            return
        
        # Display ready agents table
        agent_table = Table(title="Available Agents (Ready Status)", show_header=True)
        agent_table.add_column("", justify="center", width=3)  # Icon
        agent_table.add_column("Agent", style="bold cyan")
        agent_table.add_column("Model", style="cyan")
        agent_table.add_column("Type", style="magenta")
        
        for agent in ready_agents:
            agent_type = "Built-in" if agent['type'] == 'builtin' else "User added"
            agent_table.add_row(
                agent['icon'],
                agent['name'],
                agent['model'],
                agent_type
            )
        
        self.console.print(agent_table)
        self.console.print()
        
        # Polisher
        polisher = self._select_ready_agent("Select Agent for POLISHER", "Claude Sonnet")
        if not polisher:
            return
        
        # Updater
        updater = self._select_ready_agent("Select Agent for UPDATER (suggests improvements)", "GPT-4")
        if not updater:
            return
        
        # Final Polisher
        final_polisher = self._select_ready_agent("Select Agent for FINAL POLISHER", "Claude Opus")
        if not final_polisher:
            return
        
        # 3. Run Pipeline
        self.console.print(f"\n[cyan]Running Design Polish Pipeline...[/cyan]")
        self.console.print(f"  1. Polisher: {polisher.name}")
        self.console.print(f"  2. Updater: {updater.name}")
        self.console.print(f"  3. Final Polisher: {final_polisher.name}\n")
        
        try:
            from .exceptions import AgentError, APIError, ConfigurationError
            
            pipeline = WorkflowTemplates.design_polish_chain(polisher, updater, final_polisher)
            pipeline.framework = self.framework
            
            with self.console.status("[bold green]Executing pipeline steps...[/bold green]") as status:
                result = pipeline.run(document_text)
            
            # 4. Show Result
            self.console.print("\n[green]✓ Pipeline Complete![/green]\n")
            
            self.console.print(Panel(
                result.final_output,
                title="Final Polished Design Document",
                border_style="green"
            ))
            
            # 5. Save
            save = questionary.confirm(
                "Save result to file?",
                default=True,
                style=custom_style
            ).ask()
            
            if save:
                # Determine default filename and location
                if original_doc_path:
                    # If loaded from file, offer option to save next to original
                    original_stem = original_doc_path.stem
                    original_suffix = original_doc_path.suffix or '.md'
                    original_dir = original_doc_path.parent
                    
                    # Generate polished filename next to original
                    polished_filename_next_to_original = original_dir / f"{original_stem}_polished{original_suffix}"
                    
                    # Ask user where to save
                    save_location = questionary.select(
                        "Where would you like to save the polished document?",
                        choices=[
                            f"📁 Next to original file: {polished_filename_next_to_original.name}",
                            "📝 Custom location",
                            "← Cancel"
                        ],
                        default=f"📁 Next to original file: {polished_filename_next_to_original.name}",
                        style=custom_style
                    ).ask()
                    
                    if not save_location or "Cancel" in save_location:
                        return
                    
                    if "Next to original" in save_location:
                        # Save next to original file
                        output_path = polished_filename_next_to_original
                    else:
                        # Custom location
                        filename = questionary.text(
                            "Filename:",
                            default=f"polished_design_{result.pipeline_id[:8]}.md",
                            style=custom_style
                        ).ask()
                        
                        if not filename:
                            return
                        
                        output_path = Path(filename)
                        if not output_path.is_absolute():
                            # If relative path, use current directory or original file's directory
                            output_path = original_dir / output_path
                else:
                    # No original file (pasted text), use custom location
                    filename = questionary.text(
                        "Filename:",
                        default=f"polished_design_{result.pipeline_id[:8]}.md",
                        style=custom_style
                    ).ask()
                    
                    if not filename:
                        return
                    
                    output_path = Path(filename)
                    if not output_path.is_absolute():
                        output_path = Path.cwd() / output_path
                
                # Write the file
                try:
                    with open(output_path, 'w', encoding='utf-8') as f:
                        f.write(f"# Design Polish Pipeline Result\n\n")
                        f.write("---\n\n")
                        f.write(result.final_output)
                        f.write("\n\n---\n")
                        f.write("## Pipeline Steps\n")
                        for step in result.steps:
                            f.write(f"### {step['step_name']} ({step['agent']})\n")
                            f.write(f"{step['output']}\n\n")
                    
                    self.console.print(f"[green]✓ Saved to {output_path}[/green]")
                    if original_doc_path:
                        self.console.print(f"[dim]Original: {original_doc_path}[/dim]")
                        self.console.print(f"[dim]Polished: {output_path}[/dim]")
                except Exception as e:
                    self.console.print(f"[red]Error saving file: {e}[/red]")
                    questionary.press_any_key_to_continue().ask()
        except (AgentError, APIError, ConfigurationError) as e:
            self.console.print(f"\n[red]Design polish pipeline failed: {e}[/red]")
            if hasattr(e, 'original_error') and e.original_error:
                self.console.print(f"[dim]Original error: {e.original_error}[/dim]")
        except Exception as e:
            self.console.print(f"\n[red]Unexpected Error: {e}[/red]")
            import traceback
            self.console.print(f"[dim]{traceback.format_exc()}[/dim]")
        
        questionary.press_any_key_to_continue().ask()

    def step2_distribute_prompt(self):
        """Step 2: Distribute prompt to agents"""
        
        # If no current prompt, let user select one
        if not self.current_prompt:
            prompts = self.framework.list_prompts()
            if not prompts:
                self.console.print("\n[yellow]No prompts found. Create one first.[/yellow]\n")
                questionary.press_any_key_to_continue().ask()
                return
            
            self.show_header("Step 2: Select Prompt to Distribute")
            self.console.print("[cyan]Select a prompt to distribute to agents:[/cyan]\n")
            self.select_existing_prompt()
            
            if not self.current_prompt:
                return
        
        self.show_header("Step 2: Distribute to Agents")
        
        # Show current prompt
        self.console.print(Panel(
            f"[bold]Selected Prompt:[/bold]\n\n"
            f"{self.current_prompt.content}\n\n"
            f"[dim]ID: {self.current_prompt.id}[/dim]",
            border_style="cyan"
        ))
        
        # Get existing responses for this prompt to track distribution
        existing_responses = self.framework.list_responses(prompt_id=self.current_prompt.id)
        distributed_agents = set()
        for resp in existing_responses:
            # Track by agent name and model combination
            distributed_agents.add(f"{resp.agent_name}:{resp.model}")
        
        # Get all agents
        custom_agents = self.agent_manager.list_agents()
        all_agents = self._build_unified_agent_list(custom_agents, distributed_agents)
        all_available = self._count_all_available_agents(custom_agents)
        
        # Show unified agent table
        self._show_agent_distribution_table(all_agents, distributed_agents)
        
        # Count undistributed agents
        undistributed_count = sum(1 for a in all_agents if a['available'] and not a['distributed'])
        
        # Build agent selection choices
        agent_choices = []
        
        # ALL AGENTS options
        if all_available['total'] > 1:
            agent_choices.append(questionary.Separator("─── Run Multiple ───"))
            agent_choices.append(
                f"🚀 ALL AVAILABLE ({all_available['total']} agents)"
            )
            if undistributed_count > 0:
                agent_choices.append(
                    f"🆕 ONLY UNDISTRIBUTED ({undistributed_count} agents)"
                )
        
        # Individual agents
        agent_choices.append(questionary.Separator("─── Select Individual ───"))
        
        for agent in all_agents:
            if agent['available']:
                status = "[green]✓ sent[/green]" if agent['distributed'] else "[dim]not sent[/dim]"
                icon = agent.get('icon', '🤖')
                agent_choices.append(
                    f"{icon} {agent['name']} ({agent['model'][:20]}) {status}"
                )
        else:
                agent_choices.append(
                    f"[dim]{agent.get('icon', '🤖')} {agent['name']} ({agent.get('error', 'not available')})[/dim]"
                )
        
        agent_choices.append(questionary.Separator("───────────────────────"))
        agent_choices.append("❓ Help (about agent selection)")
        agent_choices.append("📝 Select Different Prompt")
        agent_choices.append("← Back to Main Menu")
        
        selected = questionary.select(
            "\nWhich agent(s) to use?",
            choices=agent_choices,
            style=custom_style,
        ).ask()
        
        if not selected or "Back to Main" in selected:
            return
        
        if "Help" in selected:
            if self.help_system:
                self.help_system.show_contextual_help("agent_selection")
            # Re-show menu after help
            self.step2_distribute_prompt()
            return
        
        if "Different Prompt" in selected:
            self.current_prompt = None
            self.step2_distribute_prompt()
            return
        
        # Run agents based on selection
        if "ALL AVAILABLE" in selected:
            agents = self._get_all_available_agents(custom_agents)
        elif "ONLY UNDISTRIBUTED" in selected:
            agents = self._get_undistributed_agents(all_agents, custom_agents, distributed_agents)
        else:
            # Individual agent selected
            agents = self._get_agent_from_unified_choice(selected, all_agents, custom_agents)
        
        if not agents:
            self.console.print("\n[red]No valid agents selected[/red]")
            questionary.press_any_key_to_continue().ask()
            return
        
        self._run_agents(agents)
        
        # Next step suggestion
        next_step = questionary.select(
            "\nWhat next?",
            choices=[
                "3️⃣  View results now",
                "🔄 Distribute to more agents",
                "← Back to main menu"
            ],
            style=custom_style
        ).ask()
        
        if "View" in next_step:
            self.step3_view_results()
        elif "Distribute" in next_step:
            self.step2_distribute_prompt()
    
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
        claude_model = 'claude-sonnet-4-20250514'
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
        gpt4_model = 'gpt-4-turbo-preview'
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
            icon = agent.get('icon', '🤖')
            name = agent['name']
            model = agent['model'][:25] + "..." if len(agent['model']) > 25 else agent['model']
            agent_type = "Built-in" if agent['type'] == 'builtin' else "User added"
            
            if agent['available']:
                status = "[green]✓ Ready[/green]"
            else:
                status = f"[red]✗ {agent.get('error', 'N/A')}[/red]"
            
            if agent['distributed']:
                sent = "[green]✓ Yes[/green]"
            else:
                sent = "[dim]No[/dim]"
            
            table.add_row(icon, name, model, agent_type, status, sent)
        
        self.console.print()
        self.console.print(table)
        self.console.print()
    
    def _get_undistributed_agents(self, all_agents: List[Dict[str, Any]], custom_agents: List[Dict[str, Any]], distributed_agents: set) -> List[BaseAgent]:
        """Get only agents that haven't received this prompt yet"""
        agents = []
        
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
        agents = []
        
        # Extract agent name from choice (format: "icon name (model)")
        # Try to parse the exact name from the choice string
        agent_name = None
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
                            from .providers.registry import ProviderRegistry
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
        
        custom_agents = self.agent_manager.list_agents()
        all_agents = self._build_unified_agent_list(custom_agents, set())
        
        # Filter to only Ready agents (available == True)
        # This corresponds to agents with Status "Ready" in the agent status table
        ready_agents = [agent for agent in all_agents if agent.get('available', False)]
        
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
        custom_agents = self.agent_manager.list_agents()
        all_agents = self._build_unified_agent_list(custom_agents, set())
        
        # Try to create agent and capture any errors
        try:
            agents = self._get_agent_from_unified_choice(selected, all_agents, custom_agents)
            
            if not agents:
                # Try to get more details about why it failed
                agent_name = None
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
                    from .providers.registry import ProviderRegistry
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
    
    def step3_view_results(self):
        """Step 3: View results"""
        
        if not self.current_prompt:
            self.console.print("\n[yellow]No current prompt. Let's select one...[/yellow]\n")
            self.select_existing_prompt()
            
            if not self.current_prompt:
                return
        
        self.show_header("Step 3: View Results")
        
        # Get responses for current prompt
        responses = self.framework.list_responses(prompt_id=self.current_prompt.id)
        
        if not responses:
            self.console.print(Panel(
                "[yellow]No responses yet for this prompt[/yellow]\n\n"
                "Go back and distribute the prompt to agents first.",
                title="No Results",
                border_style="yellow"
            ))
            questionary.press_any_key_to_continue().ask()
            return
        
        # Show prompt
        self.console.print(Panel(
            self.current_prompt.content,
            title=f"📝 Prompt ({len(responses)} responses)",
            border_style="cyan"
        ))
        
        # Show each response
        for i, response in enumerate(responses, 1):
            self.console.print()
            self.console.print(Panel(
                f"[bold cyan]{response.agent_name}[/bold cyan] ([dim]{response.model}[/dim])\n\n"
                f"{response.response}\n\n"
                f"[dim]───────────────────────[/dim]\n"
                f"[dim]Time: {response.response_time_ms}ms | "
                f"Tokens: {response.token_usage.total if response.token_usage else 'N/A'} | "
                f"Cost: ${response.token_usage.cost_estimate:.4f}" if response.token_usage else "N/A" + "[/dim]",
                title=f"Response {i}/{len(responses)}",
                border_style="green"
            ))
        
        # Comparison if multiple responses
        if len(responses) > 1:
            self.console.print()
            self._show_comparison(self.current_prompt.id)
        
        # Options
        self.console.print()
        action = questionary.select(
            "What would you like to do?",
            choices=[
                "💾 Save results to file",
                "🔄 Run more agents on this prompt",
                "📋 Select different prompt",
                "← Back to main menu"
            ],
            style=custom_style
        ).ask()
        
        if "Save" in action:
            self._save_results()
        elif "Run more" in action:
            self.step2_distribute_prompt()
        elif "different prompt" in action:
            self.select_existing_prompt()
            if self.current_prompt:
                self.step3_view_results()
    
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
    
    def _run_agents(self, agents: List[BaseAgent]):
        """Run agents on current prompt"""
        self.console.print(f"\n[cyan]Running {len(agents)} agent(s)...[/cyan]\n")
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=self.console
        ) as progress:
            
            for agent in agents:
                task = progress.add_task(f"Running {agent.name}...", total=None)
                
                try:
                    response = agent.create_response(
                        self.current_prompt.id,
                        self.current_prompt.content
                    )
                    self.framework.storage.save_response(response)
                    progress.update(task, description=f"[green]✓[/green] {agent.name} complete")
                except Exception as e:
                    progress.update(task, description=f"[red]✗[/red] {agent.name} failed: {e}")
        
        self.console.print("\n[green]✓ All agents complete![/green]\n")
        
        # Auto-save results
        self.console.print("[dim]Auto-saving results...[/dim]")
        self._save_results(interactive=False)
        
        questionary.press_any_key_to_continue().ask()
    
    def _show_comparison(self, prompt_id: str):
        """Show comparison table"""
        comparison = self.framework.compare_responses(prompt_id)
        
        # Handle both dict (backward compat) and ResponseComparison model
        if hasattr(comparison, 'model_dump'):
            comparison_dict = comparison.model_dump()
        else:
            comparison_dict = comparison
        
        table = Table(title="📊 Performance Comparison")
        table.add_column("Agent", style="cyan")
        table.add_column("Time", justify="right", style="yellow")
        table.add_column("Tokens", justify="right", style="blue")
        table.add_column("Cost", justify="right", style="green")
        table.add_column("Rank", justify="center", style="magenta")
        
        for i, resp in enumerate(comparison_dict['responses'], 1):
            table.add_row(
                resp['agent'],
                f"{resp['response_time_ms']}ms",
                str(resp['tokens']) if resp['tokens'] else "N/A",
                f"${resp['cost_estimate']:.4f}" if resp['cost_estimate'] else "N/A",
                f"#{i}"
            )
        
        self.console.print(table)
    
    def _save_results(self, filename: Optional[str] = None, interactive: bool = True):
        """Save current results"""
        if not self.current_prompt:
            return
        
        if interactive:
            filename = questionary.text(
                "Filename:",
                default=f"results_{self.current_prompt.id[:8]}.md",
                style=custom_style
            ).ask()
        elif not filename:
            # Auto-generate filename if not interactive
            filename = f"results_{self.current_prompt.id[:8]}.md"
        
        if not filename:
            return
        
        responses = self.framework.list_responses(prompt_id=self.current_prompt.id)
        
        with open(filename, 'w') as f:
            f.write(f"# Results for Prompt {self.current_prompt.id}\n\n")
            f.write(f"**Prompt:** {self.current_prompt.content}\n\n")
            f.write("---\n\n")
            
            for i, resp in enumerate(responses, 1):
                f.write(f"## Response {i}: {resp.agent_name}\n\n")
                f.write(resp.response)
                f.write("\n\n")
                f.write(f"- Time: {resp.response_time_ms}ms\n")
                f.write(f"- Tokens: {resp.token_usage.total if resp.token_usage else 'N/A'}\n")
                f.write(f"- Cost: ${resp.token_usage.cost_estimate:.4f}\n" if resp.token_usage else "- Cost: N/A\n")
                f.write("\n---\n\n")
        
        self.console.print(f"\n[green]✓ Saved to {filename}[/green]\n")
        
        if interactive:
            questionary.press_any_key_to_continue().ask()
    
    def select_existing_prompt(self):
        """Select an existing prompt"""
        prompts = self.framework.list_prompts()
        
        if not prompts:
            self.console.print("\n[yellow]No prompts found. Create one first.[/yellow]\n")
            questionary.press_any_key_to_continue().ask()
            return
        
        choices = [
            f"{p.id[:12]}... | {p.content[:50]}{'...' if len(p.content) > 50 else ''}"
            for p in prompts[:10]  # Show last 10
        ]
        choices.append("← Cancel")
        
        selected = questionary.select(
            "Select a prompt:",
            choices=choices,
            style=custom_style
        ).ask()
        
        if selected == "← Cancel":
            return
        
        prompt_id = selected.split("|")[0].strip().replace("...", "")
        
        for p in prompts:
            if p.id.startswith(prompt_id):
                self.current_prompt = p
                break
    
    def enhance_prompt_file_menu(self):
        """Enhance a prompt file using Claude and prompt engineering best practices"""
        self.show_header("Enhance Prompt File")
        
        self.console.print(Panel(
            "[bold]Prompt Enhancement[/bold]\n\n"
            "Reads a file containing a prompt and uses Claude to enhance it\n"
            "based on prompt engineering best practices.\n\n"
            "[bold]Strategies:[/bold]\n"
            "• [cyan]comprehensive[/cyan] - Full enhancement with all techniques\n"
            "• [cyan]clarity[/cyan] - Focus on clear, unambiguous instructions\n"
            "• [cyan]structure[/cyan] - Add professional formatting\n"
            "• [cyan]context[/cyan] - Enrich with background and examples\n"
            "• [cyan]constraints[/cyan] - Add guardrails and boundaries\n"
            "• [cyan]minimal[/cyan] - Light touch preserving style",
            border_style="cyan"
        ))
        
        # Check for Anthropic API key
        api_key = self.key_manager.get_key("ANTHROPIC_API_KEY")
        if not api_key:
            import os
            api_key = os.getenv("ANTHROPIC_API_KEY")
        
        if not api_key:
            self.console.print("\n[yellow]⚠️  Anthropic API key required for enhancement.[/yellow]")
            self.console.print("[dim]Set via 'Manage API Keys' or ANTHROPIC_API_KEY env var[/dim]\n")
            questionary.press_any_key_to_continue().ask()
            return
        
        # Get input file path
        input_path = self._safe_path_input(
            "Enter path to prompt file:",
            style=custom_style,
            only_directories=False
        )
        
        if not input_path:
            return
        
        from pathlib import Path
        input_file = Path(input_path).expanduser()
        
        if not input_file.exists():
            self.console.print(f"\n[red]File not found: {input_file}[/red]\n")
            questionary.press_any_key_to_continue().ask()
            return
        
        # Select strategy
        strategy = questionary.select(
            "Select enhancement strategy:",
            choices=[
                "comprehensive - Full enhancement with all techniques",
                "clarity - Focus on clear instructions",
                "structure - Add professional formatting",
                "context - Enrich with examples",
                "constraints - Add guardrails",
                "minimal - Light touch improvements"
            ],
            style=custom_style
        ).ask()
        
        if not strategy:
            return
        
        strategy_value = strategy.split(" - ")[0]
        
        # Optional additional guidance
        guidance = questionary.text(
            "Additional guidance (optional):",
            style=custom_style,
        ).ask()
        
        # Get output path
        stem = input_file.stem
        suffix = input_file.suffix
        default_output = input_file.parent / f"{stem}_enhanced{suffix}"
        
        output_path = questionary.text(
            f"Output file path:",
            default=str(default_output),
            style=custom_style
        ).ask()
        
        if not output_path:
            return
        
        # Perform enhancement
        self.console.print(f"\n[cyan]🔧 Enhancing prompt with Claude...[/cyan]")
        
        try:
            from .prompt_enhancer import PromptEnhancer, EnhancementStrategy
            
            with self.console.status("[cyan]Processing..."):
                enhancer = PromptEnhancer(api_key=api_key)
                result = enhancer.enhance_file(
                    input_path=input_file,
                    output_path=Path(output_path),
                    strategy=EnhancementStrategy(strategy_value),
                    additional_guidance=guidance if guidance else None,
                    include_metadata=True
                )
            
            # Show results
            self.console.print()
            self.console.print(Panel(
                f"[green]✅ Enhancement complete![/green]\n\n"
                f"[bold]Output:[/bold] {result.metadata.get('output_file', output_path)}\n"
                f"[bold]Model:[/bold] {result.model}\n"
                f"[bold]Time:[/bold] {result.response_time_ms}ms\n"
                f"[bold]Tokens:[/bold] {result.token_usage.total if result.token_usage else 'N/A'}\n"
                f"[bold]Cost:[/bold] ${result.token_usage.cost_estimate:.4f}" if result.token_usage else "",
                title="Enhancement Result",
                border_style="green"
            ))
            
            # Show comparison
            from rich.table import Table
            table = Table(title="Content Comparison", show_header=True)
            table.add_column("Metric", style="cyan")
            table.add_column("Original", justify="right")
            table.add_column("Enhanced", justify="right")
            table.add_column("Change", justify="right")
            
            orig_words = result.word_count_original
            enh_words = result.word_count_enhanced
            word_change = enh_words - orig_words
            word_pct = ((enh_words / orig_words) - 1) * 100 if orig_words > 0 else 0
            
            table.add_row("Words", str(orig_words), str(enh_words), f"{word_change:+d} ({word_pct:+.1f}%)")
            table.add_row("Characters", str(len(result.original_content)), str(len(result.enhanced_content)), f"{len(result.enhanced_content) - len(result.original_content):+d}")
            
            self.console.print()
            self.console.print(table)
            
            # Show changes summary if available
            if result.changes_summary:
                self.console.print()
                self.console.print(Panel(
                    result.changes_summary,
                    title="Changes Made",
                    border_style="blue"
                ))
            
        except ImportError as e:
            self.console.print(f"\n[red]Error: {e}[/red]")
            self.console.print("[yellow]Ensure anthropic is installed: pip install anthropic[/yellow]")
        except Exception as e:
            self.console.print(f"\n[red]Enhancement failed: {e}[/red]")
        
        self.console.print()
        questionary.press_any_key_to_continue().ask()
    
    def document_updater_menu(self):
        """Document Updater - Consolidate documents from multiple sources"""
        self.show_header("Document Updater")
        
        self.console.print(Panel(
            "[bold cyan]Document Updater[/bold cyan]\n\n"
            "Consolidate documents from multiple AI sources by:\n"
            "  1. Reading a BASE document (e.g., Sonnet 4.5's version)\n"
            "  2. Patching in specific sections from other sources\n"
            "  3. Creating a NEW consolidated document\n\n"
            "[bold]Important:[/bold] Original files are NEVER modified.\n"
            "Only new consolidated files are created.\n\n"
            "[dim]Example: Merge Feature Design docs from Sonnet, GPT-5, and Composer[/dim]",
            border_style="cyan"
        ))
        
        action = questionary.select(
            "What would you like to do?",
            choices=[
                "🔄 Run Feature Design Consolidation (Default Workflow)",
                "📂 Smart Single-Folder Processing (Auto-Detect)",
                "📝 Custom Single Document Consolidation",
                "📁 Process Directory (Async Sequential)",
                "⚙️  Configure Source Directories",
                "← Back to Main Menu"
            ],
            style=custom_style
        ).ask()
        
        if not action or "Back" in action:
            return
        
        if "Feature Design" in action:
            self._run_feature_design_workflow()
        elif "Smart Single-Folder" in action:
            self._run_single_folder_processor()
        elif "Custom Single" in action:
            self._run_custom_consolidation()
        elif "Process Directory" in action:
            self._run_async_directory_processing()
        elif "Configure" in action:
            self._configure_document_sources()
    
    def _run_feature_design_workflow(self):
        """Run the default feature design consolidation workflow"""
        self.show_header("Feature Design Consolidation")
        
        # Get or create source directory configuration
        doc_config = self._load_document_updater_config()
        
        if not doc_config.get('source_dirs'):
            self.console.print("[yellow]Source directories not configured.[/yellow]\n")
            configure = questionary.confirm(
                "Configure source directories now?",
                default=True,
                style=custom_style
            ).ask()
            
            if configure:
                self._configure_document_sources()
                doc_config = self._load_document_updater_config()
            else:
                return
        
        # Show current configuration
        self.console.print(Panel(
            f"[bold]Source Directories:[/bold]\n"
            f"  Base (Sonnet 4.5): {doc_config.get('source_dirs', {}).get('sonnet_45', '[not set]')}\n"
            f"  GPT-5: {doc_config.get('source_dirs', {}).get('gpt5', '[not set]')}\n"
            f"  Composer: {doc_config.get('source_dirs', {}).get('composer', '[not set]')}\n\n"
            f"[bold]Output Directory:[/bold] {doc_config.get('output_dir', '[not set]')}\n\n"
            "[bold]Default Patches:[/bold]\n"
            "  From GPT-5: User Stories, Accessibility, Config\n"
            "  From Composer: CSS Animations, Notes, Definition of Done",
            border_style="cyan",
            title="Configuration"
        ))
        
        # Select which batches to run
        self.console.print("\n[bold]Batch Processing Order:[/bold]")
        self.console.print("  Batch 1: Feature 2 (Initials Entry)")
        self.console.print("  Batch 2: Features 3 & 4 (Trebuchet visual) - parallel")
        self.console.print("  Batch 3: Features 5 & 6 (Game progression) - parallel")
        self.console.print("  Batch 4: Features 7 & 8 (Power-ups & Messages) - parallel")
        self.console.print()
        
        batch_choice = questionary.select(
            "Which batches to run?",
            choices=[
                "🚀 Run ALL Batches (Features 2-8)",
                "📦 Run Single Batch",
                "🎯 Run Single Feature (Smart Merge)",
                "← Cancel"
            ],
            style=custom_style
        ).ask()
        
        if not batch_choice or "Cancel" in batch_choice:
            return
        
        try:
            from .document_updater import (
                DocumentUpdaterWorkflow,
                get_default_feature_batches,
                BatchConfig
            )
        except ImportError as e:
            self.console.print(f"[red]Error importing document updater: {e}[/red]")
            questionary.press_any_key_to_continue().ask()
            return
        
        # Initialize workflow
        source_dirs = doc_config.get('source_dirs', {})
        output_dir = doc_config.get('output_dir', '')
        
        if not output_dir:
            self.console.print("[red]Output directory not configured.[/red]")
            questionary.press_any_key_to_continue().ask()
            return
        
        workflow = DocumentUpdaterWorkflow(
            base_dir=Path(source_dirs.get('sonnet_45', '.')),
            output_dir=Path(output_dir),
            source_dirs={k: Path(v) for k, v in source_dirs.items()}
        )
        
        # Determine batches to run
        batches = get_default_feature_batches()
        
        if "Single Batch" in batch_choice:
            batch_options = [f"Batch {b.batch_number}: {b.name}" for b in batches]
            batch_options.append("← Cancel")
            
            selected = questionary.select(
                "Select batch:",
                choices=batch_options,
                style=custom_style
            ).ask()
            
            if not selected or "Cancel" in selected:
                return
            
            batch_num = int(selected.split(":")[0].replace("Batch ", ""))
            batches = [b for b in batches if b.batch_number == batch_num]
        
        elif "Single Feature" in batch_choice:
            feature_num = questionary.text(
                "Feature number:",
                style=custom_style
            ).ask()
            
            try:
                fn = int(feature_num)
            except ValueError:
                self.console.print("[red]Invalid feature number[/red]")
                questionary.press_any_key_to_continue().ask()
                return
            
            # Customization Option
            customize = questionary.confirm(
                "Customize extraction rules? (Grep/Keywords)",
                default=False,
                style=custom_style
            ).ask()
            
            if customize:
                gpt5_keywords = questionary.text(
                    "GPT-5 keywords (comma-separated):",
                    default="User Stories, Accessibility, Config",
                    style=custom_style
                ).ask()
                
                composer_keywords = questionary.text(
                    "Composer keywords (comma-separated):",
                    default="Animations, Notes, Definition of Done",
                    style=custom_style
                ).ask()
                
                # Create custom config directly
                custom_patches = [
                    {
                        "source_name": "gpt5",
                        "sections": [s.strip() for s in gpt5_keywords.split(",") if s.strip()]
                    },
                    {
                        "source_name": "composer",
                        "sections": [s.strip() for s in composer_keywords.split(",") if s.strip()]
                    }
                ]
                
                self.console.print("\n[cyan]Running custom consolidation...[/cyan]")
                try:
                    config = workflow.create_feature_config(fn, patches=custom_patches)
                    
                    # Manual run
                    from .document_updater import DocumentConsolidator
                    consolidator = DocumentConsolidator(config)
                    result = consolidator.consolidate()
                    
                    # Show results directly
                    self.console.print()
                    if result.success:
                        self.console.print(Panel(
                            f"[green]✓ Consolidation successful![/green]\n\n"
                            f"[bold]Output:[/bold] {result.output_path}\n"
                            f"[bold]Patched:[/bold] {len(result.sections_patched)}\n"
                            f"[bold]Not Found:[/bold] {len(result.sections_not_found)}",
                            title="Success",
                            border_style="green"
                        ))
                        if result.sections_not_found:
                            self.console.print("[yellow]Sections not found:[/yellow]")
                            for s in result.sections_not_found:
                                self.console.print(f"  ✗ {s}")
                    else:
                        self.console.print(f"[red]Failed: {result.error}[/red]")
                    
                    questionary.press_any_key_to_continue().ask()
                    return
                except Exception as e:
                    self.console.print(f"[red]Error running custom consolidation: {e}[/red]")
                    return

            # Standard path for single feature (using defaults)
            batches = [BatchConfig(
                batch_number=1,
                name=f"Feature {fn}",
                items=[str(fn)],
                parallel=False
            )]
        
        # Run the workflow
        self.console.print("\n[cyan]Running Document Updater...[/cyan]\n")
        
        def on_batch_start(batch):
            self.console.print(f"[bold]Starting Batch {batch.batch_number}: {batch.name}[/bold]")
        
        def on_batch_complete(batch, results):
            success_count = sum(1 for r in results.values() if r.success)
            self.console.print(f"  [green]✓ Completed: {success_count}/{len(results)} successful[/green]\n")
        
        def on_progress(batch_num, item, current, total):
            self.console.print(f"  Processing Feature {item}... ({current}/{total})")
        
        all_results = workflow.run_all_batches(
            batches,
            on_batch_start=on_batch_start,
            on_batch_complete=on_batch_complete,
            on_progress=on_progress
        )
        
        # Show summary
        self.console.print()
        self._show_consolidation_results(all_results)
        
        questionary.press_any_key_to_continue().ask()
    
    def _show_consolidation_results(self, all_results: Dict):
        """Show summary of consolidation results"""
        from rich.table import Table
        
        table = Table(title="Consolidation Results", show_header=True, show_lines=True)
        table.add_column("Feature", style="cyan")
        table.add_column("Status", justify="center")
        table.add_column("Sections Patched", justify="right")
        table.add_column("Not Found", justify="right")
        table.add_column("Output File / Error", overflow="fold")
        
        total_success = 0
        total_failed = 0
        
        # Flatten results if nested
        flat_results = {}
        for key, val in all_results.items():
            if isinstance(val, dict):
                for k, v in val.items():
                    flat_results[f"Batch {key} - {k}"] = v
            else:
                flat_results[key] = val

        for feature_id, result in sorted(flat_results.items()):
            if result.success:
                total_success += 1
                status = "[green]✓ Success[/green]"
                output = str(result.output_path) if result.output_path else "-"
            else:
                total_failed += 1
                status = f"[red]✗ Failed[/red]"
                output = result.error if result.error else "Unknown Error"
            
            table.add_row(
                str(feature_id),
                status,
                str(len(result.sections_patched)),
                str(len(result.sections_not_found)),
                output
            )
        
        self.console.print(table)
        self.console.print()
        self.console.print(f"[bold]Total:[/bold] {total_success} successful, {total_failed} failed")
    
    def _run_custom_consolidation(self):
        """Run a custom single document consolidation"""
        self.show_header("Custom Document Consolidation")
        
        self.console.print(Panel(
            "[bold]Custom Consolidation[/bold]\n\n"
            "Create a consolidated document from:\n"
            "  1. A base document (copied entirely)\n"
            "  2. Sections patched from other documents\n\n"
            "[dim]Output is always a NEW file.[/dim]",
            border_style="cyan"
        ))
        
        # Get base document
        base_path = self._safe_path_input(
            "Base document path:",
            style=custom_style,
            only_directories=False
        )
        
        if not base_path:
            return
        
        base_file = Path(base_path).expanduser().resolve()
        if not base_file.exists():
            self.console.print(f"[red]File not found: {base_file}[/red]")
            questionary.press_any_key_to_continue().ask()
            return
        
        # Show sections in base document
        try:
            from .document_updater import MarkdownSectionExtractor
        except ImportError as e:
            self.console.print(f"[red]Error: {e}[/red]")
            return
        
        content = base_file.read_text(encoding='utf-8')
        extractor = MarkdownSectionExtractor(content, str(base_file), "base")
        sections = extractor.list_sections()
        
        self.console.print(f"\n[bold]Sections in base document:[/bold]")
        for s in sections[:15]:  # Show first 15
            self.console.print(f"  • {s}")
        if len(sections) > 15:
            self.console.print(f"  ... and {len(sections) - 15} more")
        
        # Get patch sources
        self.console.print("\n[bold]Add patch sources[/bold]")
        self.console.print("[dim]Enter documents to extract sections from. Empty to finish.[/dim]\n")
        
        patches = []
        while True:
            source_path = self._safe_path_input(
                "Patch source document (empty to finish):",
                style=custom_style,
                only_directories=False
            )
            
            if not source_path:
                break
            
            source_file = Path(source_path).expanduser().resolve()
            if not source_file.exists():
                self.console.print(f"[yellow]File not found: {source_file}[/yellow]")
                continue
            
            source_name = questionary.text(
                "Source name (for attribution):",
                default=source_file.stem,
                style=custom_style
            ).ask()
            
            # Show sections in source
            source_content = source_file.read_text(encoding='utf-8')
            source_extractor = MarkdownSectionExtractor(source_content, str(source_file), source_name)
            source_sections = source_extractor.list_sections()
            
            self.console.print(f"\n[dim]Sections in {source_name}:[/dim]")
            for s in source_sections[:10]:
                self.console.print(f"  • {s}")
            
            sections_to_patch = questionary.text(
                "Sections to patch (comma-separated):",
                style=custom_style,
            ).ask()
            
            if sections_to_patch:
                section_list = [s.strip() for s in sections_to_patch.split(",")]
                patches.append({
                    "source_name": source_name,
                    "source_path": source_file,
                    "sections": section_list
                })
                self.console.print(f"[green]✓ Added {len(section_list)} section(s) from {source_name}[/green]\n")
        
        if not patches:
            self.console.print("[yellow]No patches configured. Cancelling.[/yellow]")
            questionary.press_any_key_to_continue().ask()
            return
        
        # Get output path
        default_output = base_file.parent / f"{base_file.stem}_consolidated{base_file.suffix}"
        output_path = questionary.text(
            "Output file path:",
            default=str(default_output),
            style=custom_style
        ).ask()
        
        if not output_path:
            return
        
        # Run consolidation
        from .document_updater import ConsolidationConfig, PatchRule, DocumentConsolidator
        
        patch_rules = [
            PatchRule(
                source_name=p["source_name"],
                source_path=p["source_path"],
                sections=p["sections"]
            )
            for p in patches
        ]
        
        config = ConsolidationConfig(
            name="Custom Consolidation",
            base_source_name="base",
            base_path=base_file,
            patches=patch_rules,
            output_path=Path(output_path)
        )
        
        self.console.print("\n[cyan]Running consolidation...[/cyan]")
        
        consolidator = DocumentConsolidator(config)
        result = consolidator.consolidate()
        
        if result.success:
            self.console.print(Panel(
                f"[green]✓ Consolidation successful![/green]\n\n"
                f"[bold]Output:[/bold] {result.output_path}\n"
                f"[bold]Base sections:[/bold] {result.base_sections}\n"
                f"[bold]Final sections:[/bold] {result.final_sections}\n"
                f"[bold]Sections patched:[/bold] {len(result.sections_patched)}\n"
                f"[bold]Sections not found:[/bold] {len(result.sections_not_found)}",
                title="Success",
                border_style="green"
            ))
            
            if result.sections_not_found:
                self.console.print("\n[yellow]Sections not found:[/yellow]")
                for s in result.sections_not_found:
                    self.console.print(f"  ✗ {s}")
        else:
            self.console.print(f"[red]Consolidation failed: {result.error}[/red]")
        
        questionary.press_any_key_to_continue().ask()
    
    def _run_async_directory_processing(self):
        """Run async sequential processing on a directory of design documents"""
        self.show_header("Async Directory Processing")
        
        self.console.print(Panel(
            "[bold cyan]Async Sequential Directory Processing[/bold cyan]\n\n"
            "Process all design documents in a directory sequentially.\n\n"
            "[bold]How it works:[/bold]\n"
            "  1. Scans directory for design documents\n"
            "  2. Uses filename heuristics (feature, design, spec, etc.)\n"
            "  3. Checks meta documents (DESIGN_DOCUMENTS_SUMMARY.md) if present\n"
            "  4. Ignores files with 'COMPARISON' in name\n"
            "  5. Processes documents one at a time (sequential)\n"
            "  6. Creates NEW consolidated files (originals untouched)\n\n"
            "[bold yellow]Important:[/bold yellow]\n"
            "  The directory should contain ONLY design documents.\n"
            "  Other files will be ignored based on filename patterns.",
            border_style="cyan"
        ))
        
        # Get directory path
        doc_config = self._load_document_updater_config()
        default_dir = doc_config.get('last_processed_dir', '')
        
        directory_path = self._safe_path_input(
            "Directory containing design documents:",
            default=default_dir,
            style=custom_style,
            only_directories=True
        )
        
        if not directory_path:
            return
        
        directory = Path(directory_path).expanduser().resolve()
        
        if not directory.exists():
            self.console.print(f"[red]Directory not found: {directory}[/red]")
            questionary.press_any_key_to_continue().ask()
            return
        
        # Save as last processed
        doc_config['last_processed_dir'] = str(directory)
        self._save_document_updater_config(doc_config)
        
        # Detect design documents
        try:
            from .document_updater import DesignDocumentDetector
        except ImportError as e:
            self.console.print(f"[red]Error: {e}[/red]")
            return
        
        detector = DesignDocumentDetector(directory)
        design_docs = detector.find_design_documents()
        
        if not design_docs:
            self.console.print("\n[yellow]No design documents found in directory.[/yellow]")
            self.console.print("[dim]Looking for files with: feature, design, spec, plan, etc.[/dim]")
            questionary.press_any_key_to_continue().ask()
            return
        
        # Show detected documents
        self.console.print(f"\n[bold]Found {len(design_docs)} design document(s):[/bold]")
        for doc in design_docs:
            self.console.print(f"  📄 {doc.name}")
        
        # Check for meta documents
        meta_docs = []
        for meta_name in ["DESIGN_DOCUMENTS_SUMMARY.md", "DESIGN_DOCS_INDEX.md"]:
            meta_path = directory / meta_name
            if meta_path.exists():
                meta_docs.append(meta_name)
        
        if meta_docs:
            self.console.print(f"\n[green]✓ Found meta document(s): {', '.join(meta_docs)}[/green]")
            self.console.print("[dim]Using meta documents to identify design docs[/dim]")
        
        # Confirm processing
        confirm = questionary.confirm(
            f"\nProcess {len(design_docs)} document(s)?",
            default=True,
            style=custom_style
        ).ask()
        
        if not confirm:
            return
        
        # Get source directories
        source_dirs = doc_config.get('source_dirs', {})
        if not source_dirs:
            self.console.print("\n[yellow]Source directories not configured.[/yellow]")
            configure = questionary.confirm(
                "Configure source directories now?",
                default=True,
                style=custom_style
            ).ask()
            
            if configure:
                self._configure_document_sources()
                doc_config = self._load_document_updater_config()
                source_dirs = doc_config.get('source_dirs', {})
            else:
                return
        
        # Get output directory
        output_dir = doc_config.get('output_dir', '')
        if not output_dir:
            output_dir = self._safe_path_input(
                "Output directory for consolidated files:",
                style=custom_style,
                only_directories=True
            )
            
            if not output_dir:
                return
            
            doc_config['output_dir'] = str(Path(output_dir).expanduser().resolve())
            self._save_document_updater_config(doc_config)
        
        # Initialize async updater
        try:
            from .document_updater import AsyncDocumentUpdater
            import asyncio
        except ImportError as e:
            self.console.print(f"[red]Error: {e}[/red]")
            return
        
        # The directory itself contains the BASE documents
        # Determine base source name (default to sonnet_45, but can be inferred)
        base_source = doc_config.get('base_source', 'sonnet_45')
        
        # If directory matches a configured source, use that
        directory_str = str(directory)
        for source_name, source_path in source_dirs.items():
            if directory_str == str(Path(source_path)):
                base_source = source_name
                break
        
        updater = AsyncDocumentUpdater(
            base_source_name=base_source,
            output_dir=Path(output_dir),
            source_dirs={k: Path(v) for k, v in source_dirs.items()}
        )
        
        # Progress tracking
        processed = []
        failed = []
        
        def on_progress(current, total, filename, result):
            if result.success:
                processed.append((filename, result))
                self.console.print(
                    f"  [green]✓[/green] [{current}/{total}] {filename} → {result.output_path.name if result.output_path else 'N/A'}"
                )
            else:
                failed.append((filename, result))
                self.console.print(
                    f"  [red]✗[/red] [{current}/{total}] {filename} - {result.error or 'Failed'}"
                )
        
        def on_complete(all_results):
            pass  # Summary shown below
        
        # Run async processing
        self.console.print("\n[cyan]Processing documents sequentially...[/cyan]\n")
        
        try:
            results = asyncio.run(
                updater.process_directory(
                    directory,
                    on_progress=on_progress,
                    on_complete=on_complete
                )
            )
        except Exception as e:
            self.console.print(f"\n[red]Processing failed: {e}[/red]")
            questionary.press_any_key_to_continue().ask()
            return
        
        # Show summary
        self.console.print()
        self.console.print(Panel(
            f"[bold]Processing Complete[/bold]\n\n"
            f"[green]✓ Successful:[/green] {len(processed)}\n"
            f"[red]✗ Failed:[/red] {len(failed)}\n"
            f"[bold]Total:[/bold] {len(results)}\n\n"
            f"[bold]Output Directory:[/bold] {output_dir}",
            title="Summary",
            border_style="green" if not failed else "yellow"
        ))
        
        if failed:
            self.console.print("\n[yellow]Failed Documents:[/yellow]")
            for filename, result in failed:
                self.console.print(f"  ✗ {filename}: {result.error or 'Unknown error'}")
        
        questionary.press_any_key_to_continue().ask()
    
    def _configure_document_sources(self):
        """Configure source directories for document updater"""
        self.show_header("Configure Document Sources")
        
        doc_config = self._load_document_updater_config()
        
        self.console.print(Panel(
            "[bold]Configure Source Directories[/bold]\n\n"
            "Set the directories where each AI agent's documents are stored.\n\n"
            "[bold]Required sources:[/bold]\n"
            "  • sonnet_45 - Base documents (Sonnet 4.5)\n"
            "  • gpt5 - GPT-5 documents\n"
            "  • composer - Composer documents\n\n"
            "[bold]Output directory:[/bold]\n"
            "  Where consolidated documents will be saved (NEW files only)",
            border_style="cyan"
        ))
        
        source_dirs = doc_config.get('source_dirs', {})
        
        # Configure each source
        sources = [
            ("sonnet_45", "Sonnet 4.5 (BASE)"),
            ("gpt5", "GPT-5"),
            ("composer", "Composer")
        ]
        
        for source_id, source_name in sources:
            current = source_dirs.get(source_id, '')
            path = self._safe_path_input(
                f"{source_name} directory:",
                default=current,
                style=custom_style,
                only_directories=True
            )
            
            if path:
                source_dirs[source_id] = str(Path(path).expanduser().resolve())
        
        # Output directory
        current_output = doc_config.get('output_dir', '')
        output_dir = self._safe_path_input(
            "Output directory:",
            default=current_output,
            style=custom_style,
            only_directories=True
        )
        
        if output_dir:
            doc_config['output_dir'] = str(Path(output_dir).expanduser().resolve())
        
        doc_config['source_dirs'] = source_dirs
        self._save_document_updater_config(doc_config)
        
        self.console.print("\n[green]✓ Configuration saved![/green]")
        questionary.press_any_key_to_continue().ask()
    
    def _load_document_updater_config(self) -> Dict[str, Any]:
        """Load document updater configuration"""
        config_file = (self.storage_dir or Path.home() / ".startd8") / "document_updater.json"
        if config_file.exists():
            try:
                with open(config_file, 'r') as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                pass
        return {'source_dirs': {}, 'output_dir': ''}
    
    def _save_document_updater_config(self, config: Dict[str, Any]):
        """Save document updater configuration"""
        config_file = (self.storage_dir or Path.home() / ".startd8") / "document_updater.json"
        config_file.parent.mkdir(parents=True, exist_ok=True)
        with open(config_file, 'w') as f:
            json.dump(config, f, indent=2)
    
    def prompt_builder_menu(self):
        """Prompt Builder - create prompts from templates"""
        # Lazy load prompt builder
        if not _load_prompt_builder():
            self.console.print("[red]Prompt Builder module not available.[/red]")
            self.console.print("[yellow]Try: pip install pyyaml[/yellow]")
            questionary.press_any_key_to_continue().ask()
            return
        
        first_run = True
        
        while True:
            self.show_header("Prompt Builder")
            
            # Show workflow intro on first run
            if first_run:
                if self.workflow_helper and self.workflow_helper.has_workflow_help("prompt_builder"):
                    self.workflow_helper.show_workflow_intro("prompt_builder")
                    
                    # Offer to see examples
                    show_examples = questionary.confirm(
                        "\nWould you like to see workflow examples?",
                        default=False,
                        style=custom_style
                    ).ask()
                    
                    if show_examples:
                        self.workflow_helper.show_workflow_examples("prompt_builder")
                first_run = False
            
            # Initialize loader with project templates support
            loader = TemplateLoader(project_dir=self.storage_dir)
            
            # Show available templates
            list_templates_table(loader)
            
            # Menu options
            action = questionary.select(
                "What would you like to do?",
                choices=[
                    "📝 Build prompt from template",
                    "📋 View template details",
                    "📁 Open templates folder",
                    "← Back to main menu"
                ],
                style=custom_style
            ).ask()
            
            if not action or "Back" in action:
                return
            
            if "Build prompt" in action:
                self._build_prompt_from_template(loader)
            elif "View template" in action:
                self._view_template_details(loader)
            elif "Open templates" in action:
                self._show_templates_location(loader)
    
    def _build_prompt_from_template(self, loader):
        """Build a prompt using the wizard"""
        # Select template
        template = select_template(loader)
        
        if not template:
            return
        
        # Determine project path for context
        # Priority: 1) User specified, 2) storage_dir parent, 3) cwd
        project_path_options = [
            f"Current directory: {Path.cwd()}",
        ]
        
        if self.storage_dir and self.storage_dir.parent != Path.cwd():
            project_path_options.insert(0, f"Storage directory parent: {self.storage_dir.parent}")
        
        project_path_options.extend([
            "Enter custom path...",
            "Skip (use defaults only)"
        ])
        
        self.console.print()
        path_choice = questionary.select(
            "Select project path for context auto-fill:",
            choices=project_path_options,
            style=custom_style
        ).ask()
        
        if not path_choice:
            return
        
        if "Current directory" in path_choice:
            project_path = Path.cwd()
        elif "Storage directory" in path_choice:
            project_path = self.storage_dir.parent
        elif "Enter custom" in path_choice:
            custom_path = questionary.text(
                "Enter project path:",
                default=str(Path.cwd()),
                style=custom_style
            ).ask()
            project_path = Path(custom_path) if custom_path else Path.cwd()
        else:
            project_path = None
        
        # Run the wizard
        result = run_prompt_builder_wizard(template, project_path, self.storage_dir)
        
        if result:
            # Save as prompt in framework and offer distribution
            self._save_generated_prompt(result)
    
    def _save_generated_prompt(self, generated):
        """Save generated prompt to framework and offer distribution"""
        self.console.print(Panel(
            f"[bold]Generated Prompt[/bold]\n\n"
            f"From template: {generated.template_name}\n"
            f"Words: {generated.word_count} | Lines: {generated.line_count}",
            border_style="green"
        ))
        
        action = questionary.select(
            "What would you like to do with this prompt?",
            choices=[
                "💾 Save and distribute to agents",
                "💾 Save only (distribute later)",
                "📋 Copy to clipboard (if available)",
                "👁️  View full content",
                "❌ Discard"
            ],
            style=custom_style
        ).ask()
        
        if not action or "Discard" in action:
            return
        
        if "View full" in action:
            self.console.print(Panel(
                generated.content,
                title="Full Prompt Content",
                border_style="cyan"
            ))
            questionary.press_any_key_to_continue().ask()
            # Ask again
            return self._save_generated_prompt(generated)
        
        if "Copy" in action:
            try:
                import subprocess
                subprocess.run(['pbcopy'], input=generated.content.encode(), check=True)
                self.console.print("[green]✓ Copied to clipboard[/green]")
            except Exception:
                self.console.print("[yellow]Clipboard not available. Showing content instead:[/yellow]")
                self.console.print(Panel(generated.content[:500] + "...", border_style="cyan"))
            questionary.press_any_key_to_continue().ask()
            return
        
        # Save to framework
        tags = [f"template:{generated.template_id}", "prompt-builder"]
        self.current_prompt = self.framework.create_prompt(
            content=generated.content,
            version="1.0.0",
            tags=tags
        )
        
        self.console.print(f"[green]✓ Prompt saved with ID: {self.current_prompt.id[:12]}...[/green]")
        
        if "distribute" in action.lower():
            # Go to distribution
            self.step2_distribute_prompt()
        else:
            questionary.press_any_key_to_continue().ask()
    
    def _view_template_details(self, loader):
        """View details of a specific template"""
        template = select_template(loader)
        
        if not template:
            return
        
        # Show template details
        self.console.print(Panel(
            f"[bold cyan]{template.name}[/bold cyan]\n\n"
            f"[bold]ID:[/bold] {template.id}\n"
            f"[bold]Category:[/bold] {template.category}\n"
            f"[bold]Version:[/bold] {template.version}\n"
            f"[bold]Source:[/bold] {'Built-in' if template.source == 'builtin' else 'User'}\n\n"
            f"[bold]Description:[/bold]\n{template.description}",
            title="Template Details",
            border_style="cyan"
        ))
        
        # Show variables
        if template.variables:
            var_table = Table(title="Template Variables", show_header=True)
            var_table.add_column("Name", style="cyan")
            var_table.add_column("Type", style="magenta")
            var_table.add_column("Required", justify="center")
            var_table.add_column("Default")
            var_table.add_column("Description")
            
            for var in sorted(template.variables, key=lambda v: v.order):
                var_table.add_row(
                    var.name,
                    var.input_type,
                    "✓" if var.required else "",
                    var.default or "",
                    var.description[:30] + "..." if len(var.description) > 30 else var.description
                )
            
            self.console.print()
            self.console.print(var_table)
        
        # Show content preview
        self.console.print()
        preview_content = template.content[:800] + "..." if len(template.content) > 800 else template.content
        self.console.print(Panel(
            preview_content,
            title="Content Preview (first 800 chars)",
            border_style="dim"
        ))
        
        questionary.press_any_key_to_continue().ask()
    
    def _show_templates_location(self, loader):
        """Show where templates are stored"""
        self.console.print(Panel(
            f"[bold]Template Locations[/bold]\n\n"
            f"[cyan]Built-in templates:[/cyan]\n  {loader.builtin_dir}\n\n"
            f"[cyan]User templates:[/cyan]\n  {loader.user_dir}\n\n"
            f"[cyan]Project templates:[/cyan]\n  {self.storage_dir / 'templates' if self.storage_dir else 'N/A'}\n\n"
            f"[dim]To add custom templates, create .yaml files in the user templates directory.[/dim]",
            title="Template Locations",
            border_style="cyan"
        ))
        
        # Offer to create user templates directory
        if not loader.user_dir.exists():
            if questionary.confirm("Create user templates directory?", default=True).ask():
                loader.create_user_templates_dir()
                self.console.print(f"[green]✓ Created: {loader.user_dir}[/green]")
        
        questionary.press_any_key_to_continue().ask()
    
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
    
    # =========================================================================
    # Job Queue Methods
    # =========================================================================
    
    def _get_queue_config_path(self) -> Path:
        """Get path to queue config file"""
        return (self.storage_dir or Path.home() / ".startd8") / "queue" / "config.json"
    
    def _load_queue_config(self) -> Optional[Any]:
        """Load queue configuration"""
        if not _load_job_queue():
            return None
        
        config_path = self._get_queue_config_path()
        if config_path.exists():
            try:
                return load_queue_config(config_path)
            except Exception:
                pass
        return None
    
    def _save_queue_config(self, config: Any):
        """Save queue configuration"""
        if not _load_job_queue():
            return
        
        config_path = self._get_queue_config_path()
        config_path.parent.mkdir(parents=True, exist_ok=True)
        save_queue_config(config, config_path)
    
    def _get_job_queue(self) -> Optional[Any]:
        """Get or create JobQueue instance"""
        if not _load_job_queue():
            return None
        
        config = self._load_queue_config()
        if not config:
            return None
        
        return JobQueue(config, self.framework)
    
    def job_queue_menu(self):
        """Job Queue menu"""
        if not _load_job_queue():
            self.console.print("[red]Job Queue module not available.[/red]")
            questionary.press_any_key_to_continue().ask()
            return
        
        # Show workflow intro on first run
        first_run = True
        
        while True:
            self.show_header("Job Queue")
            
            # Show workflow intro with help on first run
            if first_run:
                if self.workflow_helper and self.workflow_helper.has_workflow_help("job_queue"):
                    self.workflow_helper.show_workflow_intro("job_queue")
                    
                    # Offer to see examples
                    show_examples = questionary.confirm(
                        "\nWould you like to see workflow examples?",
                        default=False,
                        style=custom_style
                    ).ask()
                    
                    if show_examples:
                        self.workflow_helper.show_workflow_examples("job_queue")
                first_run = False
            
            # Check if queue is configured
            config = self._load_queue_config()
            
            if config:
                queue = JobQueue(config, self.framework)
                status = queue.get_queue_status()
                
                self.console.print(Panel(
                    f"[bold]Watch Folder:[/bold] {status['watch_folder']}\n"
                    f"[bold]Pending:[/bold] {status['status_counts']['pending']} | "
                    f"[bold]Processing:[/bold] {status['status_counts']['processing']} | "
                    f"[bold]Completed:[/bold] {status['status_counts']['completed']} | "
                    f"[bold]Failed:[/bold] {status['status_counts']['failed']}",
                    title="Queue Status",
                    border_style="cyan"
                ))
            else:
                self.console.print(Panel(
                    "[yellow]Job Queue not configured.[/yellow]\n"
                    "Configure a watch folder to start processing jobs.",
                    title="Queue Status",
                    border_style="yellow"
                ))
            
            choices = []
            
            if config:
                choices.extend([
                    "📋 View Pending Jobs",
                    "▶️  Process Queue (run all pending)",
                    "⏭️  Process Single Job",
                    "📜 View Completed Jobs",
                    "🧹 Clear Completed",
                    questionary.Separator("───"),
                ])
            
            choices.extend([
                "⚙️  Configure Queue Folder",
                "📝 Create Job File",
                "← Back to Main Menu"
            ])
            
            action = questionary.select(
                "What would you like to do?",
                choices=choices,
                style=custom_style
            ).ask()
            
            if not action or "Back" in action:
                break
            elif "View Pending" in action:
                self._view_pending_jobs()
            elif "Process Queue" in action:
                self._process_queue()
            elif "Process Single" in action:
                self._process_single_job()
            elif "View Completed" in action:
                self._view_completed_jobs()
            elif "Clear Completed" in action:
                self._clear_completed_jobs()
            elif "Configure" in action:
                self._configure_queue_folder()
            elif "Create Job" in action:
                self._create_job_file()
    
    def _configure_queue_folder(self):
        """Configure the queue watch folder"""
        self.show_header("Configure Queue Folder")
        
        # Get current config or defaults
        current_config = self._load_queue_config()
        
        default_folder = str(Path.home() / "startd8-jobs")
        if current_config:
            default_folder = str(current_config.watch_folder)
        
        watch_folder = self._safe_path_input(
            "Watch folder for job files:",
            default=default_folder,
            only_directories=True,
            style=custom_style
        )
        
        if not watch_folder:
            return
        
        watch_path = Path(watch_folder).expanduser().resolve()
        
        # Create folder if it doesn't exist
        try:
            watch_path.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            self.console.print(f"[red]Failed to create folder: {e}[/red]")
            questionary.press_any_key_to_continue().ask()
            return
        
        # Poll interval
        poll_interval = questionary.text(
            "Poll interval (seconds):",
            default="5.0",
            style=custom_style
        ).ask()
        
        try:
            poll_interval = float(poll_interval)
        except ValueError:
            poll_interval = 5.0
        
        # Archive completed
        archive = questionary.confirm(
            "Archive completed jobs to subfolder?",
            default=False,
            style=custom_style
        ).ask()
        
        archive_folder = None
        if archive:
            archive_folder = watch_path / "completed"
        
        # Default agents
        default_agents_str = questionary.text(
            "Default agents (comma-separated, e.g., 'claude,gpt4'):",
            default="mock",
            style=custom_style
        ).ask()
        
        default_agents = [a.strip() for a in default_agents_str.split(",") if a.strip()]
        
        # Create config
        config = JobQueueConfig(
            watch_folder=watch_path,
            poll_interval_seconds=poll_interval,
            archive_completed=archive,
            archive_folder=archive_folder,
            default_agents=default_agents
        )
        
        # Save config
        self._save_queue_config(config)
        
        self.console.print(f"\n[green]✓ Queue configured![/green]")
        self.console.print(f"[dim]Watch folder: {watch_path}[/dim]")
        self.console.print(f"[dim]Poll interval: {poll_interval}s[/dim]")
        self.console.print(f"[dim]Default agents: {', '.join(default_agents)}[/dim]")
        
        questionary.press_any_key_to_continue("\nPress any key...").ask()
    
    def _view_pending_jobs(self):
        """View pending jobs in queue"""
        self.show_header("Pending Jobs")
        
        queue = self._get_job_queue()
        if not queue:
            self.console.print("[yellow]Queue not configured.[/yellow]")
            questionary.press_any_key_to_continue().ask()
            return
        
        jobs = queue.get_pending_jobs()
        
        if not jobs:
            self.console.print("[dim]No pending jobs.[/dim]")
            questionary.press_any_key_to_continue().ask()
            return
        
        table = Table(title=f"Pending Jobs ({len(jobs)})")
        table.add_column("Job ID", style="cyan")
        table.add_column("Priority", justify="center")
        table.add_column("Agents", style="green")
        table.add_column("Prompt Preview", style="white")
        table.add_column("Created", style="dim")
        
        for job in jobs[:20]:
            preview = job.prompt.content[:40] + "..." if len(job.prompt.content) > 40 else job.prompt.content
            agents = ", ".join(job.agents) if job.agents else "(default)"
            created = job.created_at.strftime("%Y-%m-%d %H:%M") if job.created_at else "-"
            
            table.add_row(
                job.job_id[:12] + "...",
                str(job.priority),
                agents,
                preview.replace("\n", " "),
                created
            )
        
        self.console.print(table)
        questionary.press_any_key_to_continue("\nPress any key...").ask()
    
    def _view_completed_jobs(self):
        """View completed jobs"""
        self.show_header("Completed Jobs")
        
        queue = self._get_job_queue()
        if not queue:
            self.console.print("[yellow]Queue not configured.[/yellow]")
            questionary.press_any_key_to_continue().ask()
            return
        
        jobs = [j for j in queue.list_jobs(include_completed=True) 
                if j.status in (JobStatus.COMPLETED, JobStatus.FAILED)]
        
        if not jobs:
            self.console.print("[dim]No completed jobs.[/dim]")
            questionary.press_any_key_to_continue().ask()
            return
        
        table = Table(title=f"Completed Jobs ({len(jobs)})")
        table.add_column("Job ID", style="cyan")
        table.add_column("Status", justify="center")
        table.add_column("Responses", justify="center", style="green")
        table.add_column("Prompt Preview", style="white")
        table.add_column("Completed", style="dim")
        
        for job in jobs[:20]:
            preview = job.prompt.content[:40] + "..." if len(job.prompt.content) > 40 else job.prompt.content
            status_style = "green" if job.status == JobStatus.COMPLETED else "red"
            completed = job.completed_at.strftime("%Y-%m-%d %H:%M") if job.completed_at else "-"
            
            table.add_row(
                job.job_id[:12] + "...",
                f"[{status_style}]{job.status.value}[/{status_style}]",
                str(len(job.response_ids)),
                preview.replace("\n", " "),
                completed
            )
        
        self.console.print(table)
        questionary.press_any_key_to_continue("\nPress any key...").ask()
    
    def _process_queue(self):
        """Process all pending jobs"""
        self.show_header("Process Queue")
        
        queue = self._get_job_queue()
        if not queue:
            self.console.print("[yellow]Queue not configured.[/yellow]")
            questionary.press_any_key_to_continue().ask()
            return
        
        pending = queue.get_pending_jobs()
        
        if not pending:
            self.console.print("[dim]No pending jobs to process.[/dim]")
            questionary.press_any_key_to_continue().ask()
            return
        
        self.console.print(f"[cyan]Found {len(pending)} pending job(s).[/cyan]\n")
        
        confirm = questionary.confirm(
            f"Process all {len(pending)} jobs?",
            default=True,
            style=custom_style
        ).ask()
        
        if not confirm:
            return
        
        self.console.print("\n[cyan]Processing jobs...[/cyan]\n")
        
        def on_progress(current, total, job, result):
            status_color = "green" if result.status == JobStatus.COMPLETED else "red"
            icon = "✓" if result.status == JobStatus.COMPLETED else "✗"
            self.console.print(
                f"  [{status_color}]{icon}[/] [{current}/{total}] "
                f"Job {job.job_id[:12]}... - {result.status.value}"
            )
        
        results = queue.process_all(on_progress=on_progress)
        
        success_count = sum(1 for r in results if r.status == JobStatus.COMPLETED)
        
        self.console.print(f"\n[green]✓ Processed {success_count}/{len(results)} jobs successfully[/green]")
        questionary.press_any_key_to_continue("\nPress any key...").ask()
    
    def _process_single_job(self):
        """Process a single job"""
        queue = self._get_job_queue()
        if not queue:
            self.console.print("[yellow]Queue not configured.[/yellow]")
            questionary.press_any_key_to_continue().ask()
            return
        
        pending = queue.get_pending_jobs()
        
        if not pending:
            self.console.print("[dim]No pending jobs to process.[/dim]")
            questionary.press_any_key_to_continue().ask()
            return
        
        # Let user select a job
        choices = []
        for job in pending[:20]:
            preview = job.prompt.content[:30] + "..." if len(job.prompt.content) > 30 else job.prompt.content
            choices.append(f"{job.job_id[:12]}... | {preview.replace(chr(10), ' ')}")
        
        choices.append("← Cancel")
        
        selection = questionary.select(
            "Select job to process:",
            choices=choices,
            style=custom_style
        ).ask()
        
        if not selection or "Cancel" in selection:
            return
        
        # Find selected job
        job_id_prefix = selection.split(" | ")[0].replace("...", "")
        selected_job = None
        for job in pending:
            if job.job_id.startswith(job_id_prefix):
                selected_job = job
                break
        
        if not selected_job:
            self.console.print("[red]Job not found.[/red]")
            questionary.press_any_key_to_continue().ask()
            return
        
        self.console.print(f"\n[cyan]Processing job {selected_job.job_id}...[/cyan]\n")
        
        result = queue.process_job(selected_job)
        
        status_color = "green" if result.status == JobStatus.COMPLETED else "red"
        self.console.print(f"[{status_color}]Status: {result.status.value}[/{status_color}]")
        
        if result.response_ids:
            self.console.print(f"[dim]Responses generated: {len(result.response_ids)}[/dim]")
        
        if result.error:
            self.console.print(f"[red]Error: {result.error}[/red]")
        
        questionary.press_any_key_to_continue("\nPress any key...").ask()
    
    def _clear_completed_jobs(self):
        """Clear completed job status files"""
        queue = self._get_job_queue()
        if not queue:
            self.console.print("[yellow]Queue not configured.[/yellow]")
            questionary.press_any_key_to_continue().ask()
            return
        
        confirm = questionary.confirm(
            "Clear all completed/failed job status files?",
            default=False,
            style=custom_style
        ).ask()
        
        if not confirm:
            return
        
        count = queue.clear_completed()
        
        self.console.print(f"\n[green]✓ Cleared {count} status file(s)[/green]")
        questionary.press_any_key_to_continue("\nPress any key...").ask()
    
    def _create_job_file(self):
        """Create a new job file"""
        self.show_header("Create Job File")
        
        config = self._load_queue_config()
        
        if config:
            default_folder = str(config.watch_folder)
        else:
            default_folder = str(Path.home() / "startd8-jobs")
        
        # Get output folder
        output_folder = self._safe_path_input(
            "Output folder for job file:",
            default=default_folder,
            only_directories=True,
            style=custom_style
        )
        
        if not output_folder:
            return
        
        output_path = Path(output_folder).expanduser().resolve()
        output_path.mkdir(parents=True, exist_ok=True)
        
        # Get job name
        job_name = questionary.text(
            "Job name (will be used as filename):",
            default="my_task",
            style=custom_style
        ).ask()
        
        if not job_name:
            return
        
        # Get prompt content
        self.console.print("\n[cyan]Enter prompt content (Ctrl+D or empty line to finish):[/cyan]")
        
        content_lines = []
        try:
            while True:
                line = input()
                if line == "":
                    break
                content_lines.append(line)
        except EOFError:
            pass
        
        content = "\n".join(content_lines)
        
        if not content.strip():
            self.console.print("[yellow]No content provided. Cancelled.[/yellow]")
            questionary.press_any_key_to_continue().ask()
            return
        
        # Get agents
        agents_str = questionary.text(
            "Agents (comma-separated, leave empty for default):",
            default="",
            style=custom_style
        ).ask()
        
        agents = [a.strip() for a in agents_str.split(",") if a.strip()] if agents_str else []
        
        # Get priority
        priority_str = questionary.text(
            "Priority (0-10, higher = first):",
            default="0",
            style=custom_style
        ).ask()
        
        try:
            priority = int(priority_str)
        except ValueError:
            priority = 0
        
        # Create the job file
        file_path = create_job_file(
            output_path=output_path / job_name,
            content=content,
            agents=agents if agents else None,
            priority=priority
        )
        
        self.console.print(f"\n[green]✓ Job file created:[/green]")
        self.console.print(f"[dim]{file_path}[/dim]")
        
        questionary.press_any_key_to_continue("\nPress any key...").ask()
    
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
            elif "Iterative" in choice:
                self.iterative_workflow_menu()
            elif "Job Queue" in choice:
                self.job_queue_menu()
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
            elif "Help" in choice:
                self.show_help()
    
    def list_all_prompts(self):
        """List all prompts"""
        self.show_header("All Prompts")
        
        prompts = self.framework.list_prompts()
        
        if not prompts:
            self.console.print("[yellow]No prompts found.[/yellow]\n")
            questionary.press_any_key_to_continue().ask()
            return
        
        table = Table(title=f"Prompts ({len(prompts)} total)")
        table.add_column("ID", style="cyan")
        table.add_column("Content Preview", style="white")
        table.add_column("Tags", style="green")
        table.add_column("Responses", justify="center", style="yellow")
        
        for prompt in prompts[:20]:  # Show last 20
            responses = self.framework.list_responses(prompt_id=prompt.id)
            preview = prompt.content[:60] + "..." if len(prompt.content) > 60 else prompt.content
            tags = ", ".join(prompt.tags[:3]) if prompt.tags else "-"
            
            table.add_row(
                prompt.id[:12] + "...",
                preview,
                tags,
                str(len(responses))
            )
        
        self.console.print(table)
        questionary.press_any_key_to_continue("\nPress any key...").ask()
    
    def compare_prompts(self):
        """Compare responses for a prompt"""
        self.show_header("Compare Responses")
        
        # Let them select a prompt
        self.select_existing_prompt()
        
        if self.current_prompt:
            self.step3_view_results()
    
    def show_statistics(self):
        """Show overall statistics"""
        self.show_header("Statistics")
        
        prompts = self.framework.list_prompts()
        responses = self.framework.list_responses()
        
        total_tokens = sum(r.token_usage.total if r.token_usage else 0 for r in responses)
        total_cost = sum(r.token_usage.cost_estimate if r.token_usage else 0 for r in responses)
        
        self.console.print(Panel(
            f"[bold]Overall Statistics[/bold]\n\n"
            f"Prompts Created: {len(prompts)}\n"
            f"Responses Generated: {len(responses)}\n"
            f"Total Tokens Used: {total_tokens:,}\n"
            f"Total Cost: ${total_cost:.2f}\n\n"
            f"Average Tokens per Response: {total_tokens // len(responses) if responses else 0:,}\n"
            f"Average Cost per Response: ${total_cost / len(responses):.4f}" if responses else "$0",
            title="📊 Statistics",
            border_style="cyan"
        ))
        
        questionary.press_any_key_to_continue("\nPress any key...").ask()


    def _run_single_folder_processor(self):
        """Run smart single-folder processing"""
        self.show_header("Smart Single-Folder Processing")
        
        self.console.print(Panel(
            "[bold cyan]Smart Single-Folder Auto-Detection[/bold cyan]\n\n"
            "This workflow scans a SINGLE folder for multiple versions of design documents\n"
            "and automatically consolidates them based on their Author/Model.\n\n"
            "[bold]Why this exists (The 'Option 1' Strategy):[/bold]\n"
            "When generating design documents, different AI models excel at different tasks:\n\n"
            "  • [bold green]Sonnet (Claude):[/bold green] Best at overall structure, comprehensive system design,\n"
            "    and architectural coherence. We use this as the [bold]BASE[/bold] document.\n\n"
            "  • [bold blue]GPT-5 (OpenAI):[/bold blue] Excellent at User Stories, Accessibility requirements,\n"
            "    and Configuration details. We extract these sections to patch the base.\n\n"
            "  • [bold magenta]Composer (Cursor):[/bold magenta] Great at implementation details like Animations,\n"
            "    CSS specific notes, and 'Definition of Done'. We extract these too.\n\n"
            "[bold]How it works:[/bold]\n"
            "  1. You point to a folder containing all versions (e.g., feature_1_sonnet.md, feature_1_gpt5.md).\n"
            "  2. The system groups files by Feature ID.\n"
            "  3. It detects authors from filenames (e.g., 'sonnet', 'gpt5', 'cursor').\n"
            "  4. It automatically builds the best combined version.",
            border_style="cyan"
        ))
        
        # Get directory
        doc_config = self._load_document_updater_config()
        default_dir = doc_config.get('last_processed_dir', '')
        
        directory_path = self._safe_path_input(
            "Directory containing all design documents:",
            default=default_dir,
            style=custom_style,
            only_directories=True
        )
        
        if not directory_path:
            return
            
        # Clean up input path
        directory_path = directory_path.strip().strip("'").strip('"')
        self.console.print(f"[dim]Debug: Checking path: {repr(directory_path)}[/dim]")
        
        directory = Path(directory_path).expanduser().resolve()
        
        if not directory.exists():
            self.console.print(f"[red]Directory not found: {directory}[/red]")
            self.console.print(f"[dim]Resolved from: {directory_path}[/dim]")
            questionary.press_any_key_to_continue().ask()
            return
            
        # Save as last processed
        doc_config['last_processed_dir'] = str(directory)
        self._save_document_updater_config(doc_config)
        
        # Import processor
        try:
            from .document_updater import SingleFolderProcessor
        except ImportError as e:
            self.console.print(f"[red]Error importing processor: {e}[/red]")
            questionary.press_any_key_to_continue().ask()
            return
            
        # Load strategy from config if available
        strategy = doc_config.get("consolidation_strategy")
        
        # Run processing
        processor = SingleFolderProcessor(directory, directory / "consolidated", strategy=strategy)
        
        self.console.print("\n[cyan]Processing...[/cyan]\n")
        
        def on_progress(feature, status, current, total, success):
            color = "green" if success else "yellow"
            icon = "✓" if success else "⚠"
            self.console.print(f"  [{color}]{icon}[/] [{current}/{total}] Feature {feature}: {status}")
            
        results = processor.process_all(on_progress=on_progress)
        
        success_count = sum(1 for r in results if r.success)
        
        self.console.print()
        self.console.print(Panel(
            f"[bold]Processing Complete[/bold]\n\n"
            f"Total Processed: {len(results)}\n"
            f"Successful: {success_count}\n\n"
            f"[bold]Output Directory:[/bold] {directory}/consolidated",
            title="Summary",
            border_style="green"
        ))
        
        questionary.press_any_key_to_continue().ask()
    
    # ============================================================================
    # Iterative Dev Workflow Methods
    # ============================================================================
    
    def iterative_workflow_menu(self):
        """Interactive menu for iterative dev-review-fix workflow"""
        self.show_header("Iterative Dev Workflow")
        
        # Show workflow intro with help
        if self.workflow_helper and self.workflow_helper.has_workflow_help("iterative_workflow"):
            self.workflow_helper.show_workflow_intro("iterative_workflow")
        else:
            self._show_iterative_intro_panel()
        
        # Offer to see examples
        show_examples = questionary.confirm(
            "\nWould you like to see workflow examples?",
            default=False,
            style=custom_style
        ).ask()
        
        if show_examples and self.workflow_helper:
            self.workflow_helper.show_workflow_examples("iterative_workflow")
        
        self.console.print()
        if not questionary.confirm("Continue with iterative workflow?", default=True, style=custom_style).ask():
            return
        
        # Step 1: Get task description
        if self.workflow_helper:
            self.workflow_helper.show_step_guidance("iterative_workflow", 1, "Describe the task you want the developer to implement")
        else:
            self.console.print("\n[bold cyan]Step 1 of 5: Describe Task[/bold cyan]")
        task = self._get_task_description()
        if not task:
            return
        
        # Step 2: Select developer agent
        if self.workflow_helper:
            self.workflow_helper.show_step_guidance("iterative_workflow", 2, "Choose the agent that will develop the solution")
        else:
            self.console.print("\n[bold cyan]Step 2 of 5: Select Developer Agent[/bold cyan]")
            self.console.print("[dim]This agent will implement your task[/dim]\n")
        dev_agent = self._select_ready_agent(
            "Choose developer agent",
            default_hint="Claude"
        )
        if not dev_agent:
            self.console.print("[yellow]No developer agent selected. Cancelled.[/yellow]")
            questionary.press_any_key_to_continue().ask()
            return
        
        # Step 3: Select reviewer agent
        self.console.print("\n[bold cyan]Step 2: Select Reviewer Agent[/bold cyan]")
        self.console.print("[dim]This agent will review the code (best to use a different agent)[/dim]\n")
        review_agent = self._select_ready_agent(
            "Choose reviewer agent",
            default_hint="GPT-4"
        )
        if not review_agent:
            self.console.print("[yellow]No reviewer agent selected. Cancelled.[/yellow]")
            questionary.press_any_key_to_continue().ask()
            return
        
        # Step 4: Configure options
        self.console.print("\n[bold cyan]Step 3: Configuration[/bold cyan]\n")
        config = self._configure_iterative_workflow()
        if not config:
            return
        
        # Step 5: Show confirmation
        if not self._confirm_iterative_workflow(task, dev_agent, review_agent, config):
            return
        
        # Step 6: Run workflow with progress display
        result = self._execute_iterative_workflow(task, dev_agent, review_agent, config)
        
        # Step 7: Display results
        if result:
            self._display_iterative_results(result)
    
    def _show_iterative_intro_panel(self):
        """Show introduction to iterative workflow"""
        self.console.print(Panel(
            "[bold cyan]Iterative Dev-Review-Fix Workflow[/bold cyan]\n\n"
            "This workflow automates the development cycle:\n\n"
            "  1️⃣  [bold]Developer Agent[/bold] implements your task\n"
            "  2️⃣  [bold]Reviewer Agent[/bold] checks the code\n"
            "  3️⃣  If issues found → Developer fixes them\n"
            "  4️⃣  Repeat until code passes review\n\n"
            "[bold]Best Practice:[/bold] Use different agents for dev and review\n"
            "[dim]Example: Claude for development, GPT-4 for review[/dim]",
            title="🔄 Dev → Review → Fix Loop",
            border_style="cyan"
        ))
    
    def _safe_path_input(self, prompt: str, **kwargs) -> Optional[str]:
        """
        Safely get path input from user, handling cases where questionary.path might not work.
        
        This handles the case where questionary.path() might return a string directly
        instead of a prompt object, which causes "'str' object has no attribute 'ask'" errors.
        
        Args:
            prompt: Prompt text
            **kwargs: Additional arguments for questionary.path or questionary.text
            
        Returns:
            Path string or None if cancelled
        """
        try:
            if hasattr(questionary, 'path'):
                path_prompt = questionary.path(prompt, **kwargs)
                # Check if it's actually a prompt object (has .ask method)
                if hasattr(path_prompt, 'ask'):
                    result = path_prompt.ask()
                    return result if isinstance(result, str) else None
                elif isinstance(path_prompt, str):
                    # If it returned a string directly (some versions do this), return it
                    return path_prompt if path_prompt else None
                else:
                    # Unexpected return type, fallback to text
                    return questionary.text(prompt, **kwargs).ask()
            else:
                # Fallback to text input if path() doesn't exist
                return questionary.text(prompt, **kwargs).ask()
        except (AttributeError, TypeError) as e:
            # If questionary.path fails for any reason, fallback to text input
            return questionary.text(prompt, **kwargs).ask()
    
    def _get_text_or_file_input(
        self,
        title: str,
        prompt_text: str,
        description: Optional[str] = None,
        example: Optional[str] = None,
        allow_empty: bool = False
    ) -> Optional[str]:
        """
        Reusable helper to get text input from user with option to load from file.
        
        Args:
            title: Title to display (e.g., "Task Description")
            prompt_text: Prompt label for text input (e.g., "Task:")
            description: Optional description/instructions to show
            example: Optional example text to show
            allow_empty: Whether to allow empty input (default: False)
            
        Returns:
            Text content or None if cancelled
        """
        self.console.print(f"\n[bold cyan]{title}[/bold cyan]\n")
        if description:
            self.console.print(f"[dim]{description}[/dim]")
        if example:
            self.console.print(f"[dim]Example: {example}[/dim]\n")
        
        # Ask user for input method
        input_method = questionary.select(
            "Choose input method:",
            choices=[
                "✏️  Enter text directly",
                "📁 Load from file",
                "← Cancel"
            ],
            style=custom_style
        ).ask()
        
        if not input_method or "Cancel" in input_method:
            return None
        
        content = None
        
        if "Enter text" in input_method:
            # Direct text input
            content = questionary.text(
                prompt_text,
                multiline=True,
                style=custom_style
            ).ask()
        
        elif "Load from file" in input_method:
            # File input - use safe path input helper
            file_path = self._safe_path_input(
                "Enter path to file:",
                style=custom_style,
                only_directories=False
            )
            
            if not file_path:
                return None
            
            try:
                from pathlib import Path
                file = Path(file_path).expanduser()
                
                if not file.exists():
                    self.console.print(f"\n[red]❌ File not found: {file}[/red]\n")
                    questionary.press_any_key_to_continue().ask()
                    return None
                
                if not file.is_file():
                    self.console.print(f"\n[red]❌ Not a file: {file}[/red]\n")
                    questionary.press_any_key_to_continue().ask()
                    return None
                
                # Read file content
                content = file.read_text(encoding='utf-8')
                
                # Show preview
                preview = content[:300] + ("..." if len(content) > 300 else "")
                self.console.print(Panel(
                    preview,
                    title=f"[dim]Loaded from {file.name} ({len(content)} chars)[/dim]",
                    border_style="green"
                ))
                
                # Confirm
                confirm = questionary.confirm(
                    "Use this content?",
                    default=True,
                    style=custom_style
                ).ask()
                
                if not confirm:
                    return None
                
            except UnicodeDecodeError:
                self.console.print(f"\n[red]❌ Error: File is not valid UTF-8 text[/red]\n")
                questionary.press_any_key_to_continue().ask()
                return None
            except Exception as e:
                self.console.print(f"\n[red]❌ Error reading file: {e}[/red]\n")
                questionary.press_any_key_to_continue().ask()
                return None
        
        # Validate content
        if not content or not content.strip():
            if not allow_empty:
                self.console.print("[yellow]⚠️  No content provided. Cancelled.[/yellow]")
                questionary.press_any_key_to_continue().ask()
                return None
        
        return content.strip() if content else None
    
    def _get_task_description(self) -> Optional[str]:
        """Get task description from user (via text input or file)"""
        return self._get_text_or_file_input(
            title="Task Description",
            prompt_text="Task:",
            description="Describe what you want the developer agent to implement.",
            example="Implement a function to validate email addresses with regex",
            allow_empty=False
        )
    
    def _configure_iterative_workflow(self) -> Optional[Dict[str, Any]]:
        """Configure workflow options"""
        # Max iterations
        max_iter_str = questionary.text(
            "Maximum iterations (1-10):",
            default="3",
            style=custom_style
        ).ask()
        
        if not max_iter_str:
            return None
        
        try:
            max_iterations = int(max_iter_str)
            max_iterations = max(1, min(10, max_iterations))
        except ValueError:
            max_iterations = 3
        
        # Save results
        save_results = questionary.confirm(
            "Save workflow results to file?",
            default=True,
            style=custom_style
        ).ask()
        
        if save_results is None:
            return None
        
        return {
            'max_iterations': max_iterations,
            'save_results': save_results
        }
    
    def _confirm_iterative_workflow(
        self,
        task: str,
        dev_agent: BaseAgent,
        review_agent: BaseAgent,
        config: Dict[str, Any]
    ) -> bool:
        """Show confirmation and get user approval"""
        
        task_preview = task[:200] + "..." if len(task) > 200 else task
        
        self.console.print("\n")
        self.console.print(Panel(
            f"[bold]Task:[/bold]\n{task_preview}\n\n"
            f"[bold]Developer:[/bold] {dev_agent.agent_name} ({dev_agent.model})\n"
            f"[bold]Reviewer:[/bold] {review_agent.agent_name} ({review_agent.model})\n"
            f"[bold]Max Iterations:[/bold] {config['max_iterations']}\n"
            f"[bold]Save Results:[/bold] {'Yes' if config['save_results'] else 'No'}",
            title="Confirm Workflow",
            border_style="yellow"
        ))
        
        return questionary.confirm(
            "Start workflow?",
            default=True,
            style=custom_style
        ).ask()
    
    def _execute_iterative_workflow(
        self,
        task: str,
        dev_agent: BaseAgent,
        review_agent: BaseAgent,
        config: Dict[str, Any]
    ) -> Optional[IterativeWorkflowResult]:
        """Execute workflow with progress display"""
        
        self.console.print("\n")
        self.show_header("Running Iterative Workflow")
        
        # Progress callback
        def on_iteration_complete(iteration):
            status = "✓ PASSED" if iteration.feedback and iteration.feedback.passed else "✗ FAILED"
            color = "green" if iteration.feedback and iteration.feedback.passed else "yellow"
            
            self.console.print(
                f"[{color}]Iteration {iteration.iteration_number}: {status}[/{color}]"
            )
            
            if iteration.feedback:
                if iteration.feedback.score is not None:
                    self.console.print(f"  Score: {iteration.feedback.score}/100")
                if iteration.feedback.issues:
                    self.console.print(f"  Issues: {len(iteration.feedback.issues)}")
            
            self.console.print(
                f"  Time: {iteration.dev_time_ms + iteration.review_time_ms}ms"
            )
            self.console.print()
        
        # Create and run workflow
        try:
            workflow = IterativeDevWorkflow(
                developer_agent=dev_agent,
                reviewer_agent=review_agent,
                max_iterations=config['max_iterations'],
                on_iteration_complete=on_iteration_complete
            )
            
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=self.console
            ) as progress:
                progress.add_task("[cyan]Running iterative workflow...", total=None)
                
                result = workflow.run(task)
            
            # Save if requested
            if config.get('save_results') and result:
                output_dir = self.storage_dir / "workflow_results"
                output_dir.mkdir(parents=True, exist_ok=True)
                save_workflow_result(result, output_dir)
                self.console.print(f"[dim]Results saved to {output_dir / result.workflow_id}.json[/dim]\n")
            
            return result
            
        except Exception as e:
            self.console.print(f"[red]Error: {e}[/red]")
            import traceback
            self.console.print(f"[dim]{traceback.format_exc()}[/dim]")
            questionary.press_any_key_to_continue().ask()
            return None
    
    def _display_iterative_results(self, result: IterativeWorkflowResult):
        """Display workflow results"""
        
        # Status
        status_color = "green" if result.successful else "yellow"
        status_text = "SUCCESS ✓" if result.successful else "INCOMPLETE"
        
        self.console.print(Panel(
            f"[bold {status_color}]{status_text}[/bold {status_color}]",
            border_style=status_color
        ))
        
        # Summary table
        table = Table(title="Workflow Summary")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", justify="right")
        
        table.add_row("Total Iterations", str(result.total_iterations))
        table.add_row("Status", result.status.value if hasattr(result.status, 'value') else str(result.status))
        table.add_row("Total Time", f"{result.total_time_ms / 1000:.2f}s")
        table.add_row("Total Tokens", f"{result.total_dev_tokens + result.total_review_tokens:,}")
        table.add_row("Estimated Cost", f"${result.total_cost:.4f}")
        
        if result.final_review and result.final_review.score is not None:
            table.add_row("Final Score", f"{result.final_review.score}/100")
        
        self.console.print(table)
        self.console.print()
        
        # Final code preview
        if result.final_code:
            code_preview = result.final_code[:500]
            if len(result.final_code) > 500:
                code_preview += "\n... (truncated)"
            
            self.console.print(Panel(
                code_preview,
                title="Final Implementation (Preview)",
                border_style="dim"
            ))
        
        # Actions menu
        while True:
            action = questionary.select(
                "What would you like to do?",
                choices=[
                    "📋 View full code",
                    "📊 View iteration details",
                    "💾 Copy code to clipboard",
                    "← Done"
                ],
                style=custom_style
            ).ask()
            
            if not action or "Done" in action:
                break
            
            if "full code" in action:
                self.console.print(Panel(result.final_code, title="Full Implementation"))
                questionary.press_any_key_to_continue().ask()
            
            elif "iteration details" in action:
                self._show_iteration_details(result)
            
            elif "clipboard" in action:
                try:
                    import pyperclip
                    pyperclip.copy(result.final_code)
                    self.console.print("[green]✓ Code copied to clipboard![/green]")
                except ImportError:
                    self.console.print("[yellow]pyperclip not installed. Install with: pip install pyperclip[/yellow]")
                questionary.press_any_key_to_continue().ask()
    
    def _show_iteration_details(self, result: IterativeWorkflowResult):
        """Show detailed view of each iteration"""
        for iteration in result.iterations:
            status = "PASSED" if iteration.feedback and iteration.feedback.passed else "FAILED"
            color = "green" if status == "PASSED" else "red"
            
            feedback_score = iteration.feedback.score if iteration.feedback else 'N/A'
            feedback_issues = len(iteration.feedback.issues) if iteration.feedback else 0
            feedback_suggestions = len(iteration.feedback.suggestions) if iteration.feedback else 0
            
            self.console.print(Panel(
                f"[bold]Status:[/bold] [{color}]{status}[/{color}]\n"
                f"[bold]Dev Time:[/bold] {iteration.dev_time_ms}ms\n"
                f"[bold]Review Time:[/bold] {iteration.review_time_ms}ms\n"
                f"[bold]Score:[/bold] {feedback_score}/100\n"
                f"[bold]Issues:[/bold] {feedback_issues}\n"
                f"[bold]Suggestions:[/bold] {feedback_suggestions}",
                title=f"Iteration {iteration.iteration_number}",
                border_style=color
            ))
            
            if iteration.feedback and iteration.feedback.issues:
                self.console.print("[bold]Issues:[/bold]")
                for issue in iteration.feedback.issues:
                    self.console.print(f"  • {issue}")
                self.console.print()
        
        questionary.press_any_key_to_continue().ask()
    
    # ============================================================================
    # Document Enhancement Chain Methods
    # ============================================================================
    
    def document_enhancement_chain_menu(self):
        """Document Enhancement Chain - sequential multi-agent document enhancement"""
        self.show_header("Document Enhancement Chain")
        
        # Show workflow intro with help
        if self.workflow_helper and self.workflow_helper.has_workflow_help("enhancement_chain"):
            self.workflow_helper.show_workflow_intro("enhancement_chain")
        else:
            self.console.print(Panel(
                "[bold cyan]Document Enhancement Chain[/bold cyan]\n\n"
                "Chain multiple AI agents to sequentially enhance a single document.\n"
                "Each agent receives the output from the previous agent, creating a\n"
                "refinement pipeline.\n\n"
                "[bold]Example Flow:[/bold]\n"
                "  Original Document\n"
                "    ↓\n"
                "  GPT-4 Enhancement (adds structure)\n"
                "    ↓\n"
                "  Claude Refinement (improves clarity)\n"
                "    ↓\n"
                "  Composer Polish (final touches)\n\n"
                "[bold]Use Cases:[/bold]\n"
                "  • Progressively refine design documents\n"
                "  • Apply different AI strengths sequentially\n"
                "  • Create high-quality documentation through iteration",
                border_style="cyan"
            ))
        
        # Offer to see examples
        show_examples = questionary.confirm(
            "\nWould you like to see workflow examples?",
            default=False,
            style=custom_style
        ).ask()
        
        if show_examples and self.workflow_helper:
            self.workflow_helper.show_workflow_examples("enhancement_chain")
        
        self.console.print()
        if not questionary.confirm("Continue with enhancement chain?", default=True, style=custom_style).ask():
            return
        
        self._run_document_enhancement_chain()
    
    def _run_document_enhancement_chain(self):
        """Run the document enhancement chain workflow"""
        
        # Step 1: Select document
        self.console.print("\n[bold cyan]Step 1: Select Document[/bold cyan]\n")
        doc_path = self._select_document_for_enhancement()
        if not doc_path:
            return
        
        # Step 2: Get enhancement instructions (optional)
        self.console.print("\n[bold cyan]Step 2: Enhancement Instructions[/bold cyan]\n")
        instructions = self._get_enhancement_instructions()
        
        # Step 3: Select and order agents
        self.console.print("\n[bold cyan]Step 3: Select Agents[/bold cyan]\n")
        agent_configs = self._select_agents_for_chain()
        if not agent_configs:
            self.console.print("[yellow]No agents selected. Aborting.[/yellow]")
            questionary.press_any_key_to_continue().ask()
            return
        
        # Step 4: Configure error handling
        self.console.print("\n[bold cyan]Step 4: Error Handling[/bold cyan]\n")
        error_handling = self._select_error_handling()
        
        # Step 5: Configure output
        self.console.print("\n[bold cyan]Step 5: Output Configuration[/bold cyan]\n")
        save_intermediate = questionary.confirm(
            "Save intermediate results from each agent?",
            default=True,
            style=custom_style
        ).ask()
        
        # Show summary and confirm
        self.console.print("\n")
        self._show_enhancement_summary(
            doc_path=doc_path,
            instructions=instructions,
            agent_configs=agent_configs,
            error_handling=error_handling,
            save_intermediate=save_intermediate
        )
        
        if not questionary.confirm("\nProceed with enhancement?", default=True, style=custom_style).ask():
            return
        
        # Build configuration
        config = DocumentEnhancementConfig(
            source_document=doc_path,
            enhancement_instructions=instructions,
            agents=agent_configs,
            save_intermediate=save_intermediate,
            on_error=error_handling
        )
        
        # Execute chain
        result = self._execute_enhancement_chain(config)
        
        # Review results
        if result:
            self._review_enhancement_results(result, doc_path)
    
    def _select_document_for_enhancement(self) -> Optional[Path]:
        """Select a document for enhancement"""
        default_dir = str(Path.home() / "Documents")
        
        self.console.print(Panel(
            "Select a markdown document to enhance.\n"
            "The original file will NOT be modified.",
            border_style="cyan"
        ))
        
        # Use text input with validation since path() might not support validate parameter well
        doc_path = questionary.text(
            "Select document:",
            default=default_dir,
            style=custom_style
        ).ask()
        if doc_path:
            from pathlib import Path
            path_obj = Path(doc_path).expanduser()
            if not path_obj.is_file():
                self.console.print("[red]Please select a file, not a directory[/red]")
                return None
            doc_path = str(path_obj)
        
        if not doc_path:
            return None
        
        doc_path = Path(doc_path)
        
        if not doc_path.exists():
            self.console.print(f"[red]File not found: {doc_path}[/red]")
            return None
        
        # Preview document
        if questionary.confirm("Preview document?", default=False, style=custom_style).ask():
            self._preview_document(doc_path)
        
        return doc_path
    
    def _preview_document(self, doc_path: Path):
        """Preview a document (smart preview: metadata + first 50 lines)"""
        try:
            with open(doc_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            lines = content.split('\n')
            num_lines = len(lines)
            file_size = len(content)
            
            # Extract headings
            headings = [line.strip() for line in lines if line.strip().startswith('#')]
            num_headings = len(headings)
            
            # Show metadata
            self.console.print(Panel(
                f"[bold]File:[/bold] {doc_path.name}\n"
                f"[bold]Size:[/bold] {file_size:,} bytes\n"
                f"[bold]Lines:[/bold] {num_lines:,}\n"
                f"[bold]Sections:[/bold] {num_headings}\n\n"
                f"[bold]First {min(num_headings, 5)} headings:[/bold]\n" +
                '\n'.join(f"  {h}" for h in headings[:5]),
                title="Document Preview",
                border_style="cyan"
            ))
            
            # Show first 50 lines
            preview_lines = min(50, num_lines)
            self.console.print(f"\n[dim]First {preview_lines} lines:[/dim]\n")
            self.console.print('\n'.join(lines[:preview_lines]))
            
            if num_lines > preview_lines:
                self.console.print(f"\n[dim]... ({num_lines - preview_lines} more lines)[/dim]")
            
            self.console.print()
            questionary.press_any_key_to_continue().ask()
            
        except Exception as e:
            self.console.print(f"[red]Failed to preview document: {e}[/red]")
    
    def _get_enhancement_instructions(self) -> Optional[str]:
        """Get optional enhancement instructions from user"""
        self.console.print(Panel(
            "[bold]Enhancement Instructions[/bold]\n\n"
            "Provide instructions on how the document should be enhanced.\n\n"
            "[bold]Examples:[/bold]\n"
            "  • 'Add accessibility section with WCAG guidelines'\n"
            "  • 'Improve CSS animations and add code examples'\n"
            "  • 'Expand the testing section with more detail'\n"
            "  • 'Add API documentation and usage examples'\n\n"
            "[dim]Leave empty to let agents use their own judgment.[/dim]",
            title="Instructions",
            border_style="cyan"
        ))
        
        instructions = questionary.text(
            "Enhancement instructions (optional, press Enter to skip):",
            style=custom_style,
            multiline=True
        ).ask()
        
        return instructions.strip() if instructions else None
    
    def _select_agents_for_chain(self) -> List[EnhancementAgentConfig]:
        """Interactive agent selection and ordering"""
        
        # Get available agents
        available_agents = self._get_available_agents_for_enhancement()
        
        if not available_agents:
            self.console.print("[red]No agents available. Please configure API keys first.[/red]")
            return []
        
        # Display agents
        agent_table = Table(title="Available Agents")
        agent_table.add_column("Agent", style="cyan")
        agent_table.add_column("Status", style="green")
        agent_table.add_column("Model", style="dim")
        
        for agent_info in available_agents:
            status = "✓ Available" if agent_info['available'] else "✗ Not configured"
            agent_table.add_row(
                agent_info['name'],
                status,
                agent_info.get('model', 'N/A')
            )
        
        self.console.print(agent_table)
        self.console.print()
        
        # Multi-select agents
        available_names = [a['name'] for a in available_agents if a['available']]
        
        if not available_names:
            self.console.print("[red]No agents are available. Please configure API keys.[/red]")
            return []
        
        selected_names = questionary.checkbox(
            "Select agents for enhancement chain (select at least one):",
            choices=available_names,
            style=custom_style
        ).ask()
        
        if not selected_names:
            return []
        
        # Order agents
        self.console.print("\n[bold]Order the selected agents[/bold]")
        self.console.print("[dim]The order determines the sequence of enhancement.[/dim]\n")
        
        ordered_agents = []
        remaining = selected_names.copy()
        
        while remaining:
            if len(remaining) == 1:
                ordered_agents.append(remaining[0])
                break
            
            next_agent = questionary.select(
                f"Select agent #{len(ordered_agents) + 1} (of {len(selected_names)}):",
                choices=remaining,
                style=custom_style
            ).ask()
            
            if not next_agent:
                return []
            
            ordered_agents.append(next_agent)
            remaining.remove(next_agent)
        
        # Show chain preview
        self.console.print("\n[bold green]Enhancement Chain:[/bold green]")
        for i, agent_name in enumerate(ordered_agents, 1):
            arrow = "  ↓" if i < len(ordered_agents) else ""
            self.console.print(f"  {i}. {agent_name}{arrow}")
        self.console.print()
        
        # Create AgentConfig objects
        agent_configs = []
        for order, agent_name in enumerate(ordered_agents):
            agent_instance = self._create_agent_instance(agent_name)
            agent_configs.append(EnhancementAgentConfig(
                agent_name=agent_name,
                agent_instance=agent_instance,
                step_name=f"{agent_name}-enhancement",
                order=order
            ))
        
        return agent_configs
    
    def _get_available_agents_for_enhancement(self) -> List[Dict[str, Any]]:
        """Get list of available agents for enhancement"""
        agents = []
        
        # Built-in agents
        try:
            claude = ClaudeAgent()
            agents.append({
                'name': 'claude',
                'available': True,
                'model': claude.model,
                'type': 'builtin'
            })
        except:
            agents.append({
                'name': 'claude',
                'available': False,
                'model': 'N/A',
                'type': 'builtin'
            })
        
        try:
            gpt4 = GPT4Agent()
            agents.append({
                'name': 'gpt4',
                'available': True,
                'model': gpt4.model,
                'type': 'builtin'
            })
        except:
            agents.append({
                'name': 'gpt4',
                'available': False,
                'model': 'N/A',
                'type': 'builtin'
            })
        
        try:
            composer = ComposerAgent()
            agents.append({
                'name': 'composer',
                'available': True,
                'model': composer.model,
                'type': 'builtin'
            })
        except:
            agents.append({
                'name': 'composer',
                'available': False,
                'model': 'N/A',
                'type': 'builtin'
            })
        
        # Mock agent (always available)
        agents.append({
            'name': 'mock',
            'available': True,
            'model': 'mock-model',
            'type': 'builtin'
        })
        
        return agents
    
    def _create_agent_instance(self, agent_name: str) -> BaseAgent:
        """Create an agent instance by name"""
        if agent_name == 'claude':
            return ClaudeAgent()
        elif agent_name == 'gpt4':
            return GPT4Agent()
        elif agent_name == 'composer':
            return ComposerAgent()
        elif agent_name == 'mock':
            return MockAgent()
        else:
            raise ValueError(f"Unknown agent: {agent_name}")
    
    def _select_error_handling(self) -> ErrorHandling:
        """Select error handling strategy"""
        self.console.print(Panel(
            "[bold]Error Handling Strategy[/bold]\n\n"
            "If an agent fails during enhancement:\n\n"
            "[bold cyan]STOP:[/bold cyan] Stop the chain immediately and return partial results\n"
            "[bold yellow]RETRY:[/bold yellow] Retry the failed step once before stopping\n"
            "[bold green]SKIP:[/bold green] Skip the failed agent and continue with next one\n\n"
            "[dim]Recommended: STOP (safest option)[/dim]",
            border_style="cyan"
        ))
        
        choice = questionary.select(
            "Error handling strategy:",
            choices=[
                "STOP - Stop on first error (recommended)",
                "RETRY - Retry failed step once",
                "SKIP - Skip failed agents and continue"
            ],
            style=custom_style
        ).ask()
        
        if not choice:
            return ErrorHandling.STOP
        
        if "RETRY" in choice:
            return ErrorHandling.RETRY
        elif "SKIP" in choice:
            return ErrorHandling.SKIP
        else:
            return ErrorHandling.STOP
    
    def _show_enhancement_summary(
        self,
        doc_path: Path,
        instructions: Optional[str],
        agent_configs: List[EnhancementAgentConfig],
        error_handling: ErrorHandling,
        save_intermediate: bool
    ):
        """Show enhancement configuration summary"""
        
        # Build chain display
        chain_display = ""
        for i, config in enumerate(agent_configs, 1):
            arrow = "\n  ↓\n" if i < len(agent_configs) else ""
            chain_display += f"  {i}. {config.agent_name} ({config.agent_instance.model}){arrow}"
        
        instructions_display = instructions if instructions else "[dim]Let agents use their judgment[/dim]"
        
        self.console.print(Panel(
            f"[bold]Configuration Summary[/bold]\n\n"
            f"[bold]Document:[/bold] {doc_path.name}\n"
            f"[bold]Path:[/bold] {doc_path}\n\n"
            f"[bold]Instructions:[/bold]\n{instructions_display}\n\n"
            f"[bold]Enhancement Chain:[/bold]\n{chain_display}\n\n"
            f"[bold]Error Handling:[/bold] {error_handling.value.upper()}\n"
            f"[bold]Save Intermediate:[/bold] {'Yes' if save_intermediate else 'No'}",
            title="Ready to Enhance",
            border_style="green"
        ))
    
    def _execute_enhancement_chain(
        self,
        config: DocumentEnhancementConfig
    ) -> Optional:
        """Execute the enhancement chain with progress display"""
        
        self.console.print("\n")
        self.show_header("Executing Enhancement Chain")
        
        # Create chain
        chain = DocumentEnhancementChain(config, self.framework)
        
        # Progress tracking
        current_step = [0]  # Use list for mutable closure
        total_steps = len(config.agents)
        
        def on_step_start(step_num: int, total: int, agent_name: str):
            current_step[0] = step_num
            self.console.print(f"\n[bold cyan]Step {step_num}/{total}: {agent_name}[/bold cyan]")
            self.console.print(f"[dim]Enhancing document...[/dim]")
        
        def on_step_complete(step_num: int, total: int, agent_name: str, result):
            if result.success:
                tokens = result.token_usage.total if result.token_usage else 0
                cost = result.token_usage.cost_estimate if result.token_usage else 0
                self.console.print(
                    f"[green]✓ Complete[/green] "
                    f"({result.response_time_ms}ms, {tokens:,} tokens, ${cost:.4f})"
                )
            else:
                self.console.print(f"[red]✗ Failed: {result.error}[/red]")
        
        # Execute with callbacks
        try:
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=self.console
            ) as progress:
                task = progress.add_task("Running enhancement chain...", total=total_steps)
                
                result = chain.run(
                    on_step_start=on_step_start,
                    on_step_complete=on_step_complete,
                    on_progress=lambda current, total: progress.update(task, completed=current)
                )
            
            return result
            
        except Exception as e:
            self.console.print(f"\n[red]Error executing chain: {e}[/red]")
            import traceback
            traceback.print_exc()
            questionary.press_any_key_to_continue().ask()
            return None
    
    def _review_enhancement_results(self, result, original_path: Path):
        """Display and review enhancement results"""
        self.console.print("\n")
        self.show_header("Enhancement Results")
        
        # Summary table
        summary_table = Table(title="Enhancement Summary")
        summary_table.add_column("Metric", style="cyan")
        summary_table.add_column("Value", style="green")
        
        summary_table.add_row("Total Steps", str(len(result.steps)))
        summary_table.add_row("Successful", str(result.steps_completed))
        summary_table.add_row("Failed", str(result.steps_failed))
        summary_table.add_row("Total Time", f"{result.total_time_ms:,}ms ({result.total_time_ms/1000:.1f}s)")
        summary_table.add_row("Total Tokens", f"{result.total_tokens:,}")
        summary_table.add_row("Total Cost", f"${result.total_cost:.4f}")
        summary_table.add_row("Overall Status", "✓ Success" if result.success else "✗ Partial/Failed")
        
        self.console.print(summary_table)
        self.console.print()
        
        # Step-by-step results
        steps_table = Table(title="Step Results")
        steps_table.add_column("Step", style="cyan", justify="center")
        steps_table.add_column("Agent", style="green")
        steps_table.add_column("Model", style="dim")
        steps_table.add_column("Time", style="dim", justify="right")
        steps_table.add_column("Tokens", style="dim", justify="right")
        steps_table.add_column("Cost", style="dim", justify="right")
        steps_table.add_column("Status", style="green", justify="center")
        
        for step in result.steps:
            tokens = step.token_usage.total if step.token_usage else 0
            cost = step.token_usage.cost_estimate if step.token_usage else 0
            
            steps_table.add_row(
                str(step.step_number),
                step.agent_name,
                step.model,
                f"{step.response_time_ms:,}ms",
                f"{tokens:,}",
                f"${cost:.4f}",
                "✓" if step.success else "✗"
            )
        
        self.console.print(steps_table)
        self.console.print()
        
        # Output location
        if result.output_path:
            self.console.print(Panel(
                f"[bold green]✓ Enhanced document saved![/bold green]\n\n"
                f"[bold]Final output:[/bold]\n{result.output_path}\n\n"
                f"[bold]Output directory:[/bold]\n{result.output_path.parent}\n\n"
                + (f"[bold]Intermediate results:[/bold]\nSaved in step subdirectories" if result.config.save_intermediate else ""),
                title="Output Location",
                border_style="green"
            ))
        
        self.console.print()
        
        # Actions
        while True:
            action = questionary.select(
                "What would you like to do?",
                choices=[
                    "📄 Preview final document",
                    "📂 Open output directory",
                    "📊 View detailed metrics",
                    "← Done"
                ],
                style=custom_style
            ).ask()
            
            if not action or "Done" in action:
                break
            
            if "Preview" in action:
                self._preview_document_content(result.final_document)
            elif "Open output" in action:
                import subprocess
                subprocess.run(["open", str(result.output_path.parent)])
            elif "detailed metrics" in action:
                self._show_detailed_step_metrics(result)
    
    def _preview_document_content(self, content: str):
        """Preview document content"""
        lines = content.split('\n')
        num_lines = len(lines)
        preview_lines = min(100, num_lines)
        
        self.console.print(Panel(
            f"[bold]Document Preview[/bold]\n"
            f"[dim]Showing first {preview_lines} of {num_lines} lines[/dim]",
            border_style="cyan"
        ))
        
        self.console.print()
        self.console.print('\n'.join(lines[:preview_lines]))
        
        if num_lines > preview_lines:
            self.console.print(f"\n[dim]... ({num_lines - preview_lines} more lines)[/dim]")
        
        self.console.print()
        questionary.press_any_key_to_continue().ask()
    
    def _show_detailed_step_metrics(self, result):
        """Show detailed metrics for each step"""
        self.console.print("\n")
        self.show_header("Detailed Step Metrics")
        
        for step in result.steps:
            status_color = "green" if step.success else "red"
            status_text = "SUCCESS" if step.success else f"FAILED: {step.error}"
            
            tokens_text = "N/A"
            cost_text = "N/A"
            
            if step.token_usage:
                tokens_text = (
                    f"Input: {step.token_usage.input:,}, "
                    f"Output: {step.token_usage.output:,}, "
                    f"Total: {step.token_usage.total:,}"
                )
                cost_text = f"${step.token_usage.cost_estimate:.6f}"
            
            self.console.print(Panel(
                f"[bold]Agent:[/bold] {step.agent_name}\n"
                f"[bold]Model:[/bold] {step.model}\n"
                f"[bold]Status:[/bold] [{status_color}]{status_text}[/{status_color}]\n"
                f"[bold]Response Time:[/bold] {step.response_time_ms:,}ms ({step.response_time_ms/1000:.2f}s)\n"
                f"[bold]Tokens:[/bold] {tokens_text}\n"
                f"[bold]Cost:[/bold] {cost_text}\n"
                f"[bold]Timestamp:[/bold] {step.timestamp.strftime('%Y-%m-%d %H:%M:%S')}",
                title=f"Step {step.step_number}",
                border_style=status_color
            ))
            self.console.print()
        
        questionary.press_any_key_to_continue().ask()

    def analyze_last_error_workflow(self):
        """Analyze the last error from log files"""
        self.show_header("Analyze Last Error")
        
        # Show where logs are searched
        config_dir = default_config_dir()
        data_dir = default_data_dir()
        search_paths = [
            config_dir / "logs",
            data_dir / "logs",
            Path.cwd(),
        ]
        
        error_info = get_last_error_from_logs()
        if not error_info:
            self.console.print(Panel(
                "[yellow]No recent errors found.[/yellow]\n\n"
                f"Searched directories:\n"
                f"  • {config_dir / 'logs'}\n"
                f"  • {data_dir / 'logs'}\n"
                f"  • {Path.cwd()}\n\n"
                "Logs are automatically created when you run workflows.\n"
                "Run a workflow first to generate error logs.",
                title="No Errors Found",
                border_style="yellow",
            ))
            questionary.press_any_key_to_continue().ask()
            return

        # Display structured error information using Rich Table
        formatted = format_error_for_analysis(error_info)
        
        # Create metadata table
        metadata_table = Table(title="Error Metadata", show_header=True, header_style="bold cyan")
        metadata_table.add_column("Field", style="cyan")
        metadata_table.add_column("Value", style="white")
        
        if error_info.get('timestamp'):
            metadata_table.add_row("Timestamp", str(error_info['timestamp']))
        if error_info.get('logger'):
            metadata_table.add_row("Logger", error_info['logger'])
        if error_info.get('source'):
            src = error_info['source']
            source_str = f"{src.get('file', 'Unknown')}:{src.get('line', '?')} in {src.get('function', '?')}"
            metadata_table.add_row("Source", source_str)
        if error_info.get('exception_type'):
            metadata_table.add_row("Exception Type", error_info['exception_type'])
        if error_info.get('correlation_id'):
            metadata_table.add_row("Correlation ID", f"[bold cyan]{error_info['correlation_id']}[/bold cyan]")
        if error_info.get('trace_id'):
            metadata_table.add_row("Trace ID", f"[bold cyan]{error_info['trace_id']}[/bold cyan]")
        
        self.console.print("\n")
        self.console.print(metadata_table)
        self.console.print("\n")
        
        # Show error message panel
        error_message = error_info.get('message', 'No message')
        self.console.print(Panel(
            error_message,
            title="Error Message",
            border_style="red"
        ))
        
        # Show traceback if available
        if error_info.get('exception'):
            self.console.print("\n")
            self.console.print(Panel(
                error_info['exception'],
                title="Exception/Traceback",
                border_style="yellow"
            ))
        
        proceed = questionary.confirm("\nUse this error for analysis?", default=True, style=custom_style).ask()
        if not proceed:
            return
        
        # Allow editing the error text before analysis (requirement #3)
        edit_choice = questionary.select(
            "Would you like to edit the error text before analysis?",
            choices=[
                "Use as-is",
                "Edit error text",
                "← Cancel"
            ],
            default="Use as-is",
            style=custom_style
        ).ask()
        
        if not edit_choice or "Cancel" in edit_choice:
            return
        
        if "Edit" in edit_choice:
            edited_text = questionary.text(
                "Edit the error text (you can modify or add context):",
                default=formatted,
                multiline=True,
                style=custom_style
            ).ask()
            if edited_text:
                formatted = edited_text
            else:
                self.console.print("[yellow]No changes made, using original error text.[/yellow]")

        # Ensure agent status is up to date
        self.agent_status = AgentConfigTester.test_all()
        
        # Select analyzer agent
        analyzer = self._select_ready_agent("Select agent for error analysis")
        if not analyzer:
            return

        # Run pipeline
        try:
            pipeline = WorkflowTemplates.error_analysis_chain(analyzer)
            pipeline.framework = self.framework
            
            with self.console.status("[bold green]Running analysis...[/bold green]"):
                result = pipeline.run(formatted)

            # Display results
            result_panel = Panel(
                f"[bold]Agent:[/bold] {analyzer.name} ({analyzer.model})\n"
                f"[bold]Time:[/bold] {result.total_time_ms}ms\n"
                f"[bold]Tokens:[/bold] {result.total_tokens:,}\n"
                f"[bold]Cost:[/bold] ${result.total_cost:.4f}\n\n"
                f"{result.final_output}",
                title="Error Analysis Summary",
                border_style="green"
            )
            self.console.print("\n")
            self.console.print(result_panel)
            
            # Save option
            saved_path = None
            save = questionary.confirm("\nSave analysis to file?", default=True, style=custom_style).ask()
            if save:
                default_dir = Path.cwd()
                default_filename = f"error_analysis_{result.pipeline_id[:8]}.md"
                filename = questionary.text("Filename:", default=default_filename, style=custom_style).ask()
                
                if filename:
                    filename_path = Path(filename)
                    if not filename_path.is_absolute():
                        filename_path = default_dir / filename_path
                    
                    # Include raw JSON entry if available
                    raw_json = error_info.get('raw_json_entry', '')
                    json_section = ""
                    if raw_json:
                        json_section = f"\n\n---\n\n## Raw JSON Log Entry\n\n```json\n{json.dumps(raw_json, indent=2)}\n```\n"
                    
                    with open(filename_path, 'w', encoding='utf-8') as f:
                        f.write(f"# Error Analysis Report\n\n")
                        f.write(f"**Pipeline ID:** {result.pipeline_id}\n")
                        f.write(f"**Analyzed:** {error_info.get('timestamp', 'Unknown')}\n")
                        f.write(f"**Agent:** {analyzer.name} ({analyzer.model})\n\n")
                        f.write("---\n\n")
                        f.write("## Original Error\n\n")
                        f.write(formatted)
                        f.write("\n\n---\n\n")
                        f.write("## Analysis Result\n\n")
                        f.write(result.final_output)
                        f.write("\n\n---\n\n")
                        f.write("## Pipeline Steps\n\n")
                        for step in result.steps:
                            f.write(f"### {step['step_name']} ({step['agent']})\n\n")
                            f.write(f"{step['output']}\n\n")
                        f.write(json_section)
                    
                    saved_path = str(filename_path)
                    self.console.print(f"[green]✓ Saved to {filename_path}[/green]")
                    
                    # Option to copy to clipboard (requirement #6)
                    try:
                        import pyperclip
                        copy_choice = questionary.confirm(
                            "Copy analysis result to clipboard?",
                            default=False,
                            style=custom_style
                        ).ask()
                        if copy_choice:
                            clipboard_text = f"Error Analysis Result\n\n{result.final_output}\n\nSaved to: {saved_path}"
                            pyperclip.copy(clipboard_text)
                            self.console.print("[green]✓ Copied to clipboard[/green]")
                    except ImportError:
                        # pyperclip not available, skip clipboard option
                        pass
            
            # Option to create queue prompt
            if saved_path:
                create_queue = questionary.confirm(
                    "\nCreate a prompt from this analysis to distribute via job queue?",
                    default=False,
                    style=custom_style
                ).ask()
                if create_queue:
                    error_info_str = formatted
                    self._create_queue_prompt_from_analysis(
                        error_info_str,
                        result.final_output,
                        saved_path
                    )
        except (AgentError, APIError, ConfigurationError) as e:
            self.console.print(f"\n[red]Error analysis failed: {e}[/red]")
            if hasattr(e, 'original_error') and e.original_error:
                self.console.print(f"[dim]Original error: {e.original_error}[/dim]")
        except Exception as e:
            self.console.print(f"\n[red]Unexpected Error: {e}[/red]")
            import traceback
            self.console.print(f"[dim]{traceback.format_exc()}[/dim]")
        
        questionary.press_any_key_to_continue().ask()

    def run_agent_config_error_analysis(self):
        """Analyze agent configuration errors"""
        self.show_header("Analyze Agent Config Errors")
        
        # Get non-ready agents
        custom_agents = self.agent_manager.list_agents()
        not_ready_agents = []
        
        for agent in custom_agents:
            try:
                instance = self.agent_manager.create_agent_instance(agent)
                if not instance:
                    not_ready_agents.append(agent)
            except Exception as e:
                try:
                    self.agent_manager.capture_agent_error(agent, e, "creation")
                except Exception:
                    pass
                not_ready_agents.append(agent)
        
        if not not_ready_agents:
            self.console.print(Panel(
                "[green]✓ All agents are configured correctly![/green]\n\n"
                "No agent configuration errors found.",
                title="No Errors",
                border_style="green"
            ))
            questionary.press_any_key_to_continue().ask()
            return
        
        # Display agents with errors
        error_table = Table(title="Agents with Configuration Errors", show_header=True)
        error_table.add_column("Agent", style="bold cyan")
        error_table.add_column("Type", style="magenta")
        error_table.add_column("Model", style="blue")
        error_table.add_column("Error", style="red")
        
        error_info_list = []
        for agent in not_ready_agents:
            agent_name = agent.get('name', 'unnamed')
            agent_type = agent.get('type', 'unknown')
            agent_model = agent.get('model', 'unknown')
            
            # Try to get error details
            error_msg = "Invalid configuration"
            try:
                instance = self.agent_manager.create_agent_instance(agent)
                if not instance:
                    error_msg = "Agent creation returned None"
            except Exception as e:
                error_msg = str(e)[:60]
            
            error_table.add_row(agent_name, agent_type, agent_model, error_msg)
            error_info_list.append({
                'agent': agent_name,
                'type': agent_type,
                'model': agent_model,
                'error': error_msg,
                'config': agent
            })
        
        self.console.print("\n")
        self.console.print(error_table)
        
        # Select which agent to analyze
        if len(not_ready_agents) > 1:
            choices = [f"{a.get('name', 'unnamed')} ({a.get('type')}/{a.get('model', 'default')})" for a in not_ready_agents]
            choices.append("All agents")
            choices.append("← Cancel")
            
            selected = questionary.select(
                "\nSelect agent to analyze:",
                choices=choices,
                style=custom_style
            ).ask()
            
            if not selected or "Cancel" in selected:
                return
            
            if "All agents" in selected:
                agents_to_analyze = not_ready_agents
            else:
                idx = choices.index(selected)
                agents_to_analyze = [not_ready_agents[idx]]
        else:
            agents_to_analyze = not_ready_agents
        
        # Format error info for analysis
        error_info_str = "Agent Configuration Errors:\n\n"
        for agent_info in error_info_list:
            if any(a.get('name') == agent_info['agent'] for a in agents_to_analyze):
                error_info_str += f"Agent: {agent_info['agent']}\n"
                error_info_str += f"Type: {agent_info['type']}\n"
                error_info_str += f"Model: {agent_info['model']}\n"
                error_info_str += f"Error: {agent_info['error']}\n"
                error_info_str += f"Config: {json.dumps(agent_info['config'], indent=2)}\n\n"
        
        # Select analyzer agent
        self.agent_status = AgentConfigTester.test_all()
        analyzer = self._select_ready_agent("Select agent for error analysis")
        if not analyzer:
            return
        
        # Run pipeline
        try:
            pipeline = WorkflowTemplates.agent_config_error_analysis_chain(analyzer)
            pipeline.framework = self.framework
            
            with self.console.status("[bold green]Running analysis...[/bold green]"):
                result = pipeline.run(error_info_str)
            
            # Display results
            result_panel = Panel(
                f"[bold]Agent:[/bold] {analyzer.name} ({analyzer.model})\n"
                f"[bold]Time:[/bold] {result.total_time_ms}ms\n"
                f"[bold]Tokens:[/bold] {result.total_tokens:,}\n"
                f"[bold]Cost:[/bold] ${result.total_cost:.4f}\n\n"
                f"{result.final_output}",
                title="Configuration Error Analysis Summary",
                border_style="green"
            )
            self.console.print("\n")
            self.console.print(result_panel)
            
            # Save option
            saved_path = None
            save = questionary.confirm("\nSave analysis to file?", default=True, style=custom_style).ask()
            if save:
                default_dir = Path.cwd()
                default_filename = f"agent_config_analysis_{result.pipeline_id[:8]}.md"
                filename = questionary.text("Filename:", default=default_filename, style=custom_style).ask()
                
                if filename:
                    filename_path = Path(filename)
                    if not filename_path.is_absolute():
                        filename_path = default_dir / filename_path
                    
                    with open(filename_path, 'w', encoding='utf-8') as f:
                        f.write(f"# Agent Configuration Error Analysis Report\n\n")
                        f.write(f"**Pipeline ID:** {result.pipeline_id}\n")
                        f.write(f"**Agent:** {analyzer.name} ({analyzer.model})\n\n")
                        f.write("---\n\n")
                        f.write("## Configuration Errors\n\n")
                        f.write(error_info_str)
                        f.write("\n\n---\n\n")
                        f.write("## Analysis Result\n\n")
                        f.write(result.final_output)
                        f.write("\n\n---\n\n")
                        f.write("## Pipeline Steps\n\n")
                        for step in result.steps:
                            f.write(f"### {step['step_name']} ({step['agent']})\n\n")
                            f.write(f"{step['output']}\n\n")
                    
                    saved_path = str(filename_path)
                    self.console.print(f"[green]✓ Saved to {filename_path}[/green]")
            
            # Option to create queue prompt
            if saved_path:
                create_queue = questionary.confirm(
                    "\nCreate a prompt from this analysis to distribute via job queue?",
                    default=False,
                    style=custom_style
                ).ask()
                if create_queue:
                    error_info_str_final = error_info_str if isinstance(error_info_str, str) else json.dumps(error_info_list, indent=2)
                    self._create_queue_prompt_from_analysis(
                        error_info_str_final,
                        result.final_output,
                        saved_path
                    )
        except (AgentError, APIError, ConfigurationError) as e:
            self.console.print(f"\n[red]Error analysis failed: {e}[/red]")
            if hasattr(e, 'original_error') and e.original_error:
                self.console.print(f"[dim]Original error: {e.original_error}[/dim]")
        except Exception as e:
            self.console.print(f"\n[red]Unexpected Error: {e}[/red]")
            import traceback
            self.console.print(f"[dim]{traceback.format_exc()}[/dim]")
        
        questionary.press_any_key_to_continue().ask()

    def _create_queue_prompt_from_analysis(self, error_info: str, analysis_result: str, saved_path: str):
        """Create a job queue prompt from error analysis results"""
        self.show_header("Create Queue Prompt from Analysis")
        
        # Generate prompt content
        prompt_content = f"""Error Analysis Summary

## Error Information
{error_info}

## Analysis Result
{analysis_result}

## Analysis File
Saved to: {saved_path}

Please review this error analysis and provide feedback or suggestions for resolution.
"""
        
        # Allow user to edit
        edited = questionary.confirm(
            "Would you like to edit the prompt before creating the job?",
            default=False,
            style=custom_style
        ).ask()
        
        if edited:
            prompt_content = questionary.text(
                "Edit prompt content:",
                default=prompt_content,
                multiline=True,
                style=custom_style
            ).ask()
            if not prompt_content:
                return
        
        # Select agents for distribution
        custom_agents = self.agent_manager.list_agents()
        ready_agents = self._get_ready_agents_for_selection()
        
        if not ready_agents:
            self.console.print("[red]No ready agents available for distribution.[/red]")
            questionary.press_any_key_to_continue().ask()
            return
        
        agent_choices = []
        for agent in ready_agents:
            agent_choices.append(f"{agent['icon']} {agent['name']} ({agent['model']})")
        
        # Add instruction text
        self.console.print("[dim]💡 Use SPACE to select/deselect agents, ENTER to confirm selection[/dim]\n")
        
        # Loop until at least one agent is selected or user cancels
        selected_agents = None
        while True:
            selected_agents = questionary.checkbox(
                "Select agents to distribute this prompt to:",
                choices=agent_choices,
                style=custom_style,
                instruction="(Press SPACE to select, ENTER to confirm)"
            ).ask()
            
            # Check if user cancelled (None) vs selected nothing (empty list)
            if selected_agents is None:
                # User cancelled (Ctrl+C or similar)
                self.console.print("[yellow]Cancelled.[/yellow]")
                return
            
            if selected_agents and len(selected_agents) > 0:
                # At least one agent selected - break out of loop
                break
            
            # No agents selected - ask user what to do
            self.console.print("\n[yellow]⚠️  No agents selected. At least one agent must be selected to create a job.[/yellow]\n")
            action = questionary.select(
                "What would you like to do?",
                choices=[
                    "🔄 Select agents again",
                    "❌ Cancel job creation"
                ],
                default="🔄 Select agents again",
                style=custom_style
            ).ask()
            
            if "Cancel" in action:
                return
            # Otherwise, loop continues to retry selection
        
        # Get priority
        priority = questionary.select(
            "Job priority:",
            choices=["low", "normal", "high"],
            default="normal",
            style=custom_style
        ).ask()
        
        # Create job file
        _load_job_queue()
        if create_job_file:
            config = self._load_queue_config()
            if config:
                watch_folder = config.watch_folder
            else:
                watch_folder = Path.home() / "startd8-jobs"
            
            watch_folder.mkdir(parents=True, exist_ok=True)
            
            # Create job file
            job_name = f"error_analysis_{Path(saved_path).stem}"
            job_file = create_job_file(
                prompt_content=prompt_content,
                agents=[agent.split(" (")[0].split("⭐ ")[-1] for agent in selected_agents],
                priority=priority,
                output_folder=str(watch_folder / "output"),
                job_name=job_name
            )
            
            if job_file:
                job_path = watch_folder / f"{job_name}.json"
                self.console.print(f"\n[green]✓ Created job file: {job_path}[/green]")
                self.console.print(f"[dim]The job queue will process this automatically.[/dim]")
            else:
                self.console.print("[red]Failed to create job file.[/red]")
        else:
            self.console.print("[yellow]Job queue module not available.[/yellow]")
        
        questionary.press_any_key_to_continue().ask()


def run_improved_tui(storage_dir: Optional[Path] = None):
    """Launch the improved TUI"""
    tui = ImprovedTUI(storage_dir)
    tui.run()

