"""
Project-specific configuration management for startd8

Stores project-scoped settings like design document index file paths.
Configuration is stored in ./.startd8/project_config.json and is specific
to the folder where startd8 is being run from.
"""

import json
from pathlib import Path
from typing import Optional, Dict, Any
from .paths import startd8_dir


class ProjectConfigManager:
    """Manage project-specific configuration"""
    
    def __init__(self, project_root: Optional[Path] = None):
        """
        Initialize project config manager
        
        Args:
            project_root: Project root directory (default: current working directory)
        """
        if project_root is None:
            project_root = Path.cwd()
        
        self.project_root = Path(project_root).resolve()
        self.config_dir = startd8_dir(self.project_root)
        self.config_file = self.config_dir / "project_config.json"
        self._ensure_config_dir()
        self._config = self._load_config()
    
    def _ensure_config_dir(self):
        """Create config directory if it doesn't exist"""
        self.config_dir.mkdir(parents=True, exist_ok=True)
    
    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from file"""
        if not self.config_file.exists():
            return {}
        
        try:
            with open(self.config_file, 'r') as f:
                config = json.load(f)
            return config
        except (json.JSONDecodeError, IOError) as e:
            # Return empty config if file is corrupted
            return {}
    
    def _save_config(self):
        """Save configuration to file"""
        self._ensure_config_dir()
        with open(self.config_file, 'w') as f:
            json.dump(self._config, f, indent=2)
    
    def get_index_file_path(self) -> Optional[Path]:
        """
        Get the configured project index file path
        
        Returns:
            Path to index file if configured, None otherwise
        """
        path_str = self._config.get('index_file_path')
        if path_str:
            path = Path(path_str)
            # If path is relative, make it relative to project root
            if not path.is_absolute():
                path = self.project_root / path
            return path.resolve()
        return None
    
    def set_index_file_path(self, path: Path) -> None:
        """
        Set the project index file path
        
        Args:
            path: Path to the index file (can be absolute or relative to project root)
        """
        path = Path(path).resolve()
        
        # Store as relative path if it's within project root, otherwise absolute
        try:
            relative_path = path.relative_to(self.project_root)
            self._config['index_file_path'] = str(relative_path)
        except ValueError:
            # Path is outside project root, store as absolute
            self._config['index_file_path'] = str(path)
        
        self._save_config()
    
    def clear_index_file_path(self) -> None:
        """Clear the configured index file path"""
        if 'index_file_path' in self._config:
            del self._config['index_file_path']
            self._save_config()
    
    def get_config(self) -> Dict[str, Any]:
        """Get the full configuration dictionary"""
        return self._config.copy()
    
    def set_config(self, config: Dict[str, Any]) -> None:
        """Set the full configuration dictionary"""
        self._config.update(config)
        self._save_config()

