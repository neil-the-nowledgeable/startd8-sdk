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
                    "default": "claude-sonnet-4-20250514",
                    "max_tokens": 32768
                },
                "gpt4": {
                    "default": "gpt-4o",
                    "max_tokens": 16384
                }
            },
            "preferences": {
                "auto_save_results": True,
                "default_agent": "claude",
                "show_cost_warnings": True
            },
            "tui": {
                "show_mock_agent": False,
                "show_mock_in_workflows": False,  # Show mock agents in workflow agent selection
                "agents_per_page": 10
            },
            "otel": {
                "endpoint": None,
                "mode": None,
            },
            "artisan": {
                "lead_agent": None,
                "drafter_agent": None,
                "max_iterations": None,
                "pass_threshold": None,
                "max_tokens": None,
                "design_max_tokens": None,
                "fail_on_truncation": None,
                "check_truncation": None,
                "strict_truncation": None,
                "test_timeout_seconds": None,
                "review_temperature": None,
                "review_max_code_chars": None,
                "development_timeout_seconds": None,
                "auto_commit": None,
                "scaffold_test_first": None,
                "force_implement": None,
                "force_design": None,
                "force_review": None,
                "design_agent": None,
                "review_agent": None,
                "enable_prompt_caching": None,
            },
            "resilience": {
                "level": "standard",  # off, minimal, standard, aggressive, custom
                "retry": {
                    "enabled": True,
                    "max_attempts": 3,
                    "base_delay_seconds": 1.0,
                    "max_delay_seconds": 60.0
                },
                "circuit_breaker": {
                    "enabled": True,
                    "failure_threshold": 5,
                    "recovery_timeout_seconds": 30.0
                },
                "workflow_errors": {
                    "default_strategy": "retry",  # stop, retry, skip, fallback
                    "max_iterations": 3
                },
                "auto_fix": {
                    "enabled": True,
                    "safe_only": True,
                    "require_confirmation": True
                },
                "diagnostics": {
                    "enabled": True,
                    "include_api_checks": False,
                    "auto_analyze": False
                }
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
    
    # Resilience Configuration

    def get_resilience_level(self) -> str:
        """Get current resilience level."""
        return self._config.get("resilience", {}).get("level", "standard")

    def set_resilience_level(self, level: str):
        """
        Set resilience level.

        Args:
            level: One of 'off', 'minimal', 'standard', 'aggressive', 'custom'
        """
        valid_levels = {"off", "minimal", "standard", "aggressive", "custom"}
        if level not in valid_levels:
            raise ValueError(f"Invalid resilience level: {level}. Must be one of {valid_levels}")

        if "resilience" not in self._config:
            self._config["resilience"] = self._default_config()["resilience"]

        self._config["resilience"]["level"] = level
        self._save_config()

    def get_resilience_config(self) -> Dict[str, Any]:
        """Get full resilience configuration."""
        return self._config.get("resilience", self._default_config()["resilience"])

    def set_resilience_config(self, config: Dict[str, Any]):
        """
        Set full resilience configuration.

        Args:
            config: Resilience configuration dictionary
        """
        self._config["resilience"] = config
        self._save_config()

    def load_resilience_config(self):
        """
        Load resilience configuration as ResilienceConfig object.

        Returns:
            ResilienceConfig object or None if module not available
        """
        try:
            from .resilience import (
                ResilienceConfig, ResilienceLevel, RetrySettings,
                CircuitBreakerSettings, WorkflowErrorSettings,
                AutoFixSettings, DiagnosticsSettings, ErrorStrategy
            )
        except ImportError:
            return None

        cfg = self.get_resilience_config()
        level_str = cfg.get("level", "standard")

        # If using a preset level, use from_level
        if level_str in ("off", "minimal", "standard", "aggressive"):
            level = ResilienceLevel(level_str)
            return ResilienceConfig.from_level(level)

        # Custom configuration
        retry_cfg = cfg.get("retry", {})
        cb_cfg = cfg.get("circuit_breaker", {})
        workflow_cfg = cfg.get("workflow_errors", {})
        autofix_cfg = cfg.get("auto_fix", {})
        diag_cfg = cfg.get("diagnostics", {})

        return ResilienceConfig(
            enabled=level_str != "off",
            level=ResilienceLevel.CUSTOM,
            retry=RetrySettings(
                enabled=retry_cfg.get("enabled", True),
                max_attempts=retry_cfg.get("max_attempts", 3),
                base_delay_seconds=retry_cfg.get("base_delay_seconds", 1.0),
                max_delay_seconds=retry_cfg.get("max_delay_seconds", 60.0),
            ),
            circuit_breaker=CircuitBreakerSettings(
                enabled=cb_cfg.get("enabled", True),
                failure_threshold=cb_cfg.get("failure_threshold", 5),
                recovery_timeout_seconds=cb_cfg.get("recovery_timeout_seconds", 30.0),
            ),
            workflow_errors=WorkflowErrorSettings(
                default_strategy=ErrorStrategy(workflow_cfg.get("default_strategy", "retry")),
                max_iterations=workflow_cfg.get("max_iterations", 3),
            ),
            auto_fix=AutoFixSettings(
                enabled=autofix_cfg.get("enabled", True),
                safe_only=autofix_cfg.get("safe_only", True),
                require_confirmation=autofix_cfg.get("require_confirmation", True),
            ),
            diagnostics=DiagnosticsSettings(
                enabled=diag_cfg.get("enabled", True),
                include_api_checks=diag_cfg.get("include_api_checks", False),
                auto_analyze=diag_cfg.get("auto_analyze", False),
            ),
        )

    def save_resilience_config(self, config) -> None:
        """
        Save ResilienceConfig object to persistent storage.

        Args:
            config: ResilienceConfig object
        """
        self._config["resilience"] = config.to_dict()
        self._save_config()

    # OTel Configuration

    def get_otel_setting(self, key: str, default: Any = None) -> Any:
        """Get a single OTel setting with env var override.

        Priority: env var ``STARTD8_OTEL_{KEY}`` > config file > *default*.

        Args:
            key: Setting name (snake_case, e.g. ``"endpoint"``).
            default: Fallback if not set anywhere.

        Returns:
            The resolved value.
        """
        env_var = f"STARTD8_OTEL_{key.upper()}"
        env_val = os.getenv(env_var)
        if env_val is not None:
            return env_val

        cfg_val = self._config.get("otel", {}).get(key)
        if cfg_val is not None:
            return cfg_val

        return default

    def set_otel_setting(self, key: str, value: Any) -> None:
        """Persist an OTel setting to the config file.

        Args:
            key: Setting name (snake_case).
            value: The value to store.
        """
        if "otel" not in self._config:
            self._config["otel"] = dict(self._default_config()["otel"])
        self._config["otel"][key] = value
        self._save_config()

    def clear_otel_setting(self, key: str) -> None:
        """Reset an OTel setting back to None (use default).

        Args:
            key: Setting name (snake_case).
        """
        if "otel" in self._config and key in self._config["otel"]:
            self._config["otel"][key] = None
            self._save_config()

    # Artisan Workflow Configuration

    def get_artisan_config(self) -> Dict[str, Any]:
        """Get full artisan workflow configuration."""
        return dict(self._config.get("artisan", self._default_config()["artisan"]))

    def get_artisan_setting(self, key: str, default: Any = None) -> Any:
        """Get a single artisan setting with env var override.

        Priority: env var ``STARTD8_ARTISAN_{KEY}`` > config file > *default*.

        Args:
            key: Setting name (snake_case, e.g. ``"lead_agent"``).
            default: Fallback if not set anywhere.

        Returns:
            The resolved value (coerced from string when sourced from env).
        """
        env_var = f"STARTD8_ARTISAN_{key.upper()}"
        env_val = os.getenv(env_var)
        if env_val is not None:
            return _coerce_artisan_value(key, env_val)

        cfg_val = self._config.get("artisan", {}).get(key)
        if cfg_val is not None:
            return cfg_val

        return default

    def set_artisan_setting(self, key: str, value: Any) -> None:
        """Persist an artisan setting to the config file.

        Args:
            key: Setting name (snake_case).
            value: The value to store.
        """
        if "artisan" not in self._config:
            self._config["artisan"] = dict(self._default_config()["artisan"])
        self._config["artisan"][key] = value
        self._save_config()

    def clear_artisan_setting(self, key: str) -> None:
        """Reset an artisan setting back to None (use dataclass default).

        Args:
            key: Setting name (snake_case).
        """
        if "artisan" in self._config and key in self._config["artisan"]:
            self._config["artisan"][key] = None
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


_ARTISAN_BOOL_KEYS = {
    "fail_on_truncation", "check_truncation", "strict_truncation",
    "scaffold_test_first", "force_implement",
    "force_design", "force_review",
    "enable_prompt_caching",
}
_ARTISAN_INT_KEYS = {
    "max_iterations", "pass_threshold", "max_tokens", "design_max_tokens",
    "test_timeout_seconds", "review_max_code_chars",
}
_ARTISAN_FLOAT_KEYS = {
    "review_temperature", "development_timeout_seconds",
}


def _coerce_artisan_value(key: str, raw: str) -> Any:
    """Coerce a raw env-var string to the correct Python type for *key*.

    Bool keys accept ``true/false/1/0`` (case-insensitive).
    Int/float keys are converted numerically.
    Everything else is returned as-is (str).
    """
    if key in _ARTISAN_BOOL_KEYS:
        return raw.lower() in ("true", "1", "yes")
    if key in _ARTISAN_INT_KEYS:
        return int(raw)
    if key in _ARTISAN_FLOAT_KEYS:
        return float(raw)
    return raw


# Singleton instance
_config_manager = None


def get_config_manager(config_dir: Optional[Path] = None) -> ConfigManager:
    """Get global config manager instance"""
    global _config_manager
    
    if _config_manager is None:
        _config_manager = ConfigManager(config_dir)
    
    return _config_manager



