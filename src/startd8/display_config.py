"""
Display configuration for prompt and response rendering

Controls what information is shown when displaying prompts and responses in the TUI.
"""

import json
import yaml
from pathlib import Path
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field

from .config import ConfigManager
from .logging_config import get_logger
from .exceptions import ConfigurationError

logger = get_logger(__name__)


class PromptDisplayConfig(BaseModel):
    """Configuration for how prompts are displayed"""
    show_timestamp: bool = Field(default=True, description="Show prompt creation timestamp")
    show_version: bool = Field(default=True, description="Show prompt version")
    show_tags: bool = Field(default=True, description="Show prompt tags")
    show_metadata: bool = Field(default=False, description="Show prompt metadata")
    show_content_preview: bool = Field(default=True, description="Show content preview")
    content_preview_length: int = Field(default=200, description="Max length of content preview")


class ResponseDisplayConfig(BaseModel):
    """Configuration for how responses are displayed"""
    show_timestamp: bool = Field(default=True, description="Show response timestamp")
    show_response_time: bool = Field(default=True, description="Show response time (ms)")
    show_time_estimate: bool = Field(default=True, description="Show time estimates")
    show_token_usage: bool = Field(default=True, description="Show token usage")
    show_cost_estimate: bool = Field(default=True, description="Show cost estimate")
    show_model_name: bool = Field(default=True, description="Show model name")
    show_agent_name: bool = Field(default=True, description="Show agent name")
    show_full_response: bool = Field(default=False, description="Show full response by default")
    response_preview_length: int = Field(default=500, description="Max length of response preview")


class ComparisonDisplayConfig(BaseModel):
    """Configuration for how comparisons are displayed"""
    show_rankings: bool = Field(default=True, description="Show rankings")
    show_statistics: bool = Field(default=True, description="Show statistics")
    show_response_previews: bool = Field(default=True, description="Show response previews")
    max_rankings_shown: int = Field(default=10, description="Max number of rankings to show")


class DisplayConfig(BaseModel):
    """Complete display configuration"""
    prompt: PromptDisplayConfig = Field(default_factory=PromptDisplayConfig)
    response: ResponseDisplayConfig = Field(default_factory=ResponseDisplayConfig)
    comparison: ComparisonDisplayConfig = Field(default_factory=ComparisonDisplayConfig)
    
    @classmethod
    def default(cls) -> 'DisplayConfig':
        """Get default display configuration"""
        return cls()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "prompt": self.prompt.model_dump(),
            "response": self.response.model_dump(),
            "comparison": self.comparison.model_dump()
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'DisplayConfig':
        """Create from dictionary"""
        return cls(
            prompt=PromptDisplayConfig(**data.get("prompt", {})),
            response=ResponseDisplayConfig(**data.get("response", {})),
            comparison=ComparisonDisplayConfig(**data.get("comparison", {}))
        )


class DisplayConfigManager:
    """Manager for display configuration"""
    
    CONFIG_FILENAME = "display_config.yaml"
    
    def __init__(self, config_dir: Optional[Path] = None):
        """
        Initialize display config manager
        
        Args:
            config_dir: Configuration directory (default: ~/.startd8)
        """
        if config_dir is None:
            config_dir = Path.home() / ".startd8"
        
        self.config_dir = Path(config_dir)
        self.config_file = self.config_dir / self.CONFIG_FILENAME
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self._config: Optional[DisplayConfig] = None
    
    def load(self) -> DisplayConfig:
        """
        Load display configuration from file
        
        Returns:
            DisplayConfig instance
        """
        if self._config is not None:
            return self._config
        
        if not self.config_file.exists():
            logger.debug("Display config file not found, using defaults")
            self._config = DisplayConfig.default()
            self.save(self._config)  # Save defaults
            return self._config
        
        try:
            with open(self.config_file, 'r') as f:
                if self.config_file.suffix == '.yaml' or self.config_file.suffix == '.yml':
                    data = yaml.safe_load(f)
                else:
                    data = json.load(f)
            
            if not data:
                data = {}
            
            self._config = DisplayConfig.from_dict(data)
            logger.debug("Loaded display configuration")
            return self._config
        
        except Exception as e:
            logger.warning(f"Failed to load display config: {e}, using defaults")
            self._config = DisplayConfig.default()
            return self._config
    
    def save(self, config: DisplayConfig) -> None:
        """
        Save display configuration to file
        
        Args:
            config: DisplayConfig to save
        """
        try:
            self.config_dir.mkdir(parents=True, exist_ok=True)
            
            data = config.to_dict()
            
            # Save as YAML for better readability
            with open(self.config_file, 'w') as f:
                yaml.dump(data, f, default_flow_style=False, sort_keys=False, indent=2)
            
            self._config = config
            logger.info("Saved display configuration")
        
        except Exception as e:
            logger.error(f"Failed to save display config: {e}", exc_info=True)
            raise ConfigurationError(f"Failed to save display configuration: {e}") from e
    
    def get_config(self) -> DisplayConfig:
        """Get current configuration (loads if needed)"""
        if self._config is None:
            return self.load()
        return self._config
    
    def update_prompt_config(self, **kwargs) -> None:
        """Update prompt display configuration"""
        config = self.get_config()
        for key, value in kwargs.items():
            if hasattr(config.prompt, key):
                setattr(config.prompt, key, value)
        self.save(config)
    
    def update_response_config(self, **kwargs) -> None:
        """Update response display configuration"""
        config = self.get_config()
        for key, value in kwargs.items():
            if hasattr(config.response, key):
                setattr(config.response, key, value)
        self.save(config)
    
    def update_comparison_config(self, **kwargs) -> None:
        """Update comparison display configuration"""
        config = self.get_config()
        for key, value in kwargs.items():
            if hasattr(config.comparison, key):
                setattr(config.comparison, key, value)
        self.save(config)
    
    def reset_to_defaults(self) -> None:
        """Reset configuration to defaults"""
        self._config = DisplayConfig.default()
        self.save(self._config)
        logger.info("Reset display configuration to defaults")









