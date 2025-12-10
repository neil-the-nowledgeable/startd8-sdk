"""
Configuration management for startd8

Handles API keys, model preferences, and secure storage.
"""

import os
import json
from pathlib import Path
from typing import Optional, Dict, Any
import stat


class ConfigManager:
    """Manage startd8 configuration"""
    
    def __init__(self, config_dir: Optional[Path] = None):
        """
        Initialize config manager
        
        Args:
            config_dir: Directory for config file (default: ~/.startd8)
        """
        if config_dir is None:
            config_dir = Path.home() / ".startd8"
        
        self.config_dir = Path(config_dir)
        self.config_file = self.config_dir / "config.json"
        self._ensure_config_dir()
        self._config = self._load_config()
    
    def _ensure_config_dir(self):
        """Create config directory if it doesn't exist"""
        self.config_dir.mkdir(parents=True, exist_ok=True)
        # Set restrictive permissions (owner only)
        os.chmod(self.config_dir, stat.S_IRWXU)
    
    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from file"""
        if not self.config_file.exists():
            return self._default_config()
        
        try:
            with open(self.config_file, 'r') as f:
                config = json.load(f)
            return config
        except Exception:
            return self._default_config()
    
    def _save_config(self):
        """Save configuration to file"""
        with open(self.config_file, 'w') as f:
            json.dump(self._config, f, indent=2)
        # Set restrictive permissions (owner only)
        os.chmod(self.config_file, stat.S_IRUSR | stat.S_IWUSR)
    
    def _default_config(self) -> Dict[str, Any]:
        """Get default configuration"""
        return {
            "api_keys": {
                "anthropic": None,
                "openai": None
            },
            "models": {
                "claude": {
                    "default": "claude-3-opus-20240229",
                    "max_tokens": 4096
                },
                "gpt4": {
                    "default": "gpt-4-turbo-preview",
                    "max_tokens": 4096
                }
            },
            "preferences": {
                "auto_save_results": True,
                "default_agent": "claude",
                "show_cost_warnings": True
            },
            "tui": {
                "show_mock_agent": False,
                "agents_per_page": 5
            }
        }
    
    # API Key Management
    
    def get_api_key(self, provider: str) -> Optional[str]:
        """
        Get API key for provider
        
        Priority:
        1. Environment variable (always checked first)
        2. Stored in config
        
        Args:
            provider: 'anthropic' or 'openai'
        
        Returns:
            API key if found, None otherwise
        """
        # Always check environment first
        env_var = f"{provider.upper()}_API_KEY"
        env_key = os.getenv(env_var)
        if env_key:
            return env_key
        
        # Fall back to config
        return self._config.get("api_keys", {}).get(provider)
    
    def set_api_key(self, provider: str, key: str):
        """
        Save API key for provider
        
        Args:
            provider: 'anthropic' or 'openai'
            key: API key
        """
        if "api_keys" not in self._config:
            self._config["api_keys"] = {}
        
        self._config["api_keys"][provider] = key
        self._save_config()
    
    def clear_api_key(self, provider: str):
        """Clear stored API key for provider"""
        if "api_keys" in self._config and provider in self._config["api_keys"]:
            self._config["api_keys"][provider] = None
            self._save_config()
    
    def has_api_key(self, provider: str) -> bool:
        """Check if API key is available (env or config)"""
        return self.get_api_key(provider) is not None
    
    def get_api_key_source(self, provider: str) -> Optional[str]:
        """Get where the API key is coming from"""
        env_var = f"{provider.upper()}_API_KEY"
        if os.getenv(env_var):
            return "environment"
        elif self._config.get("api_keys", {}).get(provider):
            return "config"
        return None
    
    # Model Configuration
    
    def get_model_config(self, agent: str) -> Dict[str, Any]:
        """Get model configuration for agent"""
        return self._config.get("models", {}).get(agent, {})
    
    def set_model(self, agent: str, model: str):
        """Set default model for agent"""
        if "models" not in self._config:
            self._config["models"] = {}
        if agent not in self._config["models"]:
            self._config["models"][agent] = {}
        
        self._config["models"][agent]["default"] = model
        self._save_config()
    
    def set_max_tokens(self, agent: str, max_tokens: int):
        """Set max tokens for agent"""
        if "models" not in self._config:
            self._config["models"] = {}
        if agent not in self._config["models"]:
            self._config["models"][agent] = {}
        
        self._config["models"][agent]["max_tokens"] = max_tokens
        self._save_config()
    
    def get_default_model(self, agent: str) -> str:
        """Get default model for agent"""
        config = self.get_model_config(agent)
        return config.get("default", "")
    
    def get_max_tokens(self, agent: str) -> int:
        """Get max tokens for agent"""
        config = self.get_model_config(agent)
        return config.get("max_tokens", 4096)
    
    # Preferences
    
    def get_preference(self, key: str, default: Any = None) -> Any:
        """Get user preference"""
        return self._config.get("preferences", {}).get(key, default)
    
    def set_preference(self, key: str, value: Any):
        """Set user preference"""
        if "preferences" not in self._config:
            self._config["preferences"] = {}
        
        self._config["preferences"][key] = value
        self._save_config()
    
    # Utility
    
    def export_config(self) -> Dict[str, Any]:
        """Export config (with masked API keys)"""
        config = self._config.copy()
        
        # Mask API keys for security - always mask regardless of length
        if "api_keys" in config:
            for provider, key in config["api_keys"].items():
                if key:
                    # Always mask: show first 4 and last 4 chars, or just *** if too short
                    if len(key) > 8:
                        config["api_keys"][provider] = key[:4] + "..." + key[-4:]
                    else:
                        config["api_keys"][provider] = "***"
        
        return config
    
    def reset_config(self):
        """Reset to default configuration"""
        self._config = self._default_config()
        self._save_config()
    
    def get_config_file_path(self) -> Path:
        """Get path to config file"""
        return self.config_file


# Singleton instance
_config_manager = None


def get_config_manager(config_dir: Optional[Path] = None) -> ConfigManager:
    """Get global config manager instance"""
    global _config_manager
    
    if _config_manager is None:
        _config_manager = ConfigManager(config_dir)
    
    return _config_manager



