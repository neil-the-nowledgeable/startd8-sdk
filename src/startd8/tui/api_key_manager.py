"""API key management with secure storage.

Extracted verbatim from ``tui_improved.py`` (Pass A refactor).
"""

import os
import json
from typing import Optional, List, Dict, Any
from pathlib import Path
from ..paths import default_config_dir


class APIKeyManager:
    """Manage API keys with secure storage"""

    CONFIG_FILENAME = "api_keys.json"

    def __init__(self, storage_dir: Optional[Path] = None):
        """Initialize API key manager"""
        if storage_dir is None:
            storage_dir = default_config_dir()
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
            from ..security import KeyEncryption
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

        except (OSError, PermissionError, ValueError) as e:
            # Log specific file operation errors
            from ..logging_config import get_logger
            logger = get_logger(__name__)
            logger.debug(f"Failed to export keys: {e}", exc_info=True)
            return False
        except Exception as e:
            # Log unexpected errors
            from ..logging_config import get_logger
            logger = get_logger(__name__)
            logger.warning(f"Unexpected error exporting keys: {e}", exc_info=True)
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
            from ..security import KeyEncryption

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
