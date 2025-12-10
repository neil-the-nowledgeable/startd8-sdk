"""
Security utilities for startd8 SDK

Provides functions for input sanitization, path validation, encryption, and security checks.
"""

import os
import base64
import json
import hashlib
from pathlib import Path
from typing import Optional, Union, Dict, Any

try:
    from cryptography.fernet import Fernet
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2
    HAS_CRYPTOGRAPHY = True
except ImportError:
    HAS_CRYPTOGRAPHY = False
    Fernet = None
    PBKDF2 = None
    hashes = None

from .exceptions import ValidationError, ConfigurationError


def sanitize_path(file_path: Union[str, Path], base_dir: Optional[Path] = None) -> Path:
    """
    Sanitize and validate a file path to prevent directory traversal attacks.
    
    Args:
        file_path: Path to sanitize
        base_dir: Optional base directory to restrict paths to
    
    Returns:
        Sanitized Path object
    
    Raises:
        ValidationError: If path is invalid or attempts directory traversal
    """
    path = Path(file_path).resolve()
    
    # Check for directory traversal attempts
    if '..' in str(path):
        raise ValidationError(
            "Path contains directory traversal attempt (..)",
            field="file_path",
            value=str(file_path)
        )
    
    # If base_dir is specified, ensure path is within it
    if base_dir:
        base_dir = Path(base_dir).resolve()
        try:
            path.relative_to(base_dir)
        except ValueError:
            raise ValidationError(
                f"Path {path} is outside allowed directory {base_dir}",
                field="file_path",
                value=str(file_path)
            )
    
    return path


def validate_api_key_format(api_key: str, provider: str) -> bool:
    """
    Validate API key format for common providers.
    
    Args:
        api_key: API key to validate
        provider: Provider name (anthropic, openai, etc.)
    
    Returns:
        True if format appears valid
    
    Raises:
        ValidationError: If format is invalid
    """
    if not api_key or not isinstance(api_key, str):
        raise ValidationError(
            f"API key for {provider} must be a non-empty string",
            field="api_key",
            value=api_key
        )
    
    # Basic format checks
    if len(api_key) < 10:
        raise ValidationError(
            f"API key for {provider} appears too short",
            field="api_key"
        )
    
    # Provider-specific format checks
    if provider.lower() == "anthropic":
        if not api_key.startswith("sk-ant-"):
            raise ValidationError(
                "Anthropic API key should start with 'sk-ant-'",
                field="api_key"
            )
    elif provider.lower() == "openai":
        if not (api_key.startswith("sk-") or api_key.startswith("sk-proj-")):
            raise ValidationError(
                "OpenAI API key should start with 'sk-' or 'sk-proj-'",
                field="api_key"
            )
    
    return True


def mask_api_key(api_key: str, show_chars: int = 4) -> str:
    """
    Mask an API key for display.
    
    Args:
        api_key: API key to mask
        show_chars: Number of characters to show at start and end
    
    Returns:
        Masked API key string
    """
    if not api_key:
        return "***"
    
    if len(api_key) <= show_chars * 2:
        return "***"
    
    return api_key[:show_chars] + "..." + api_key[-show_chars:]


class KeyEncryption:
    """
    Handle encryption and decryption of API keys using Fernet (symmetric encryption).
    
    Uses PBKDF2 for key derivation from password, providing secure encryption at rest.
    """
    
    # Salt for key derivation (static per instance, stored with encrypted data)
    ITERATIONS = 480000  # PBKDF2 iterations (OWASP recommended minimum)
    
    def __init__(self):
        """Initialize encryption handler"""
        if not HAS_CRYPTOGRAPHY:
            raise ConfigurationError(
                "Cryptography library not installed. "
                "Install with: pip install cryptography"
            )
    
    def _derive_key(self, password: str, salt: bytes) -> bytes:
        """
        Derive encryption key from password using PBKDF2.
        
        Args:
            password: User password
            salt: Random salt bytes
            
        Returns:
            32-byte encryption key
        """
        kdf = PBKDF2(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=self.ITERATIONS,
        )
        return base64.urlsafe_b64encode(kdf.derive(password.encode()))
    
    def encrypt_data(self, data: Dict[str, Any], password: str) -> str:
        """
        Encrypt data with password.
        
        Args:
            data: Dictionary to encrypt
            password: Encryption password
            
        Returns:
            Base64-encoded encrypted string
            
        Raises:
            ConfigurationError: If encryption fails
        """
        try:
            # Generate random salt
            salt = os.urandom(16)
            
            # Derive key from password
            key = self._derive_key(password, salt)
            
            # Create Fernet cipher
            f = Fernet(key)
            
            # Serialize and encrypt data
            json_data = json.dumps(data)
            encrypted = f.encrypt(json_data.encode())
            
            # Package salt + encrypted data
            package = {
                'version': 1,
                'salt': base64.b64encode(salt).decode(),
                'data': encrypted.decode()
            }
            
            return base64.b64encode(json.dumps(package).encode()).decode()
            
        except Exception as e:
            raise ConfigurationError(f"Encryption failed: {e}") from e
    
    def decrypt_data(self, encrypted_str: str, password: str) -> Dict[str, Any]:
        """
        Decrypt data with password.
        
        Args:
            encrypted_str: Base64-encoded encrypted string
            password: Decryption password
            
        Returns:
            Decrypted dictionary
            
        Raises:
            ConfigurationError: If decryption fails or password is wrong
        """
        try:
            # Unpackage
            package_json = base64.b64decode(encrypted_str.encode()).decode()
            package = json.loads(package_json)
            
            if package.get('version') != 1:
                raise ConfigurationError("Unsupported encryption version")
            
            # Extract salt and encrypted data
            salt = base64.b64decode(package['salt'].encode())
            encrypted_data = package['data'].encode()
            
            # Derive key from password
            key = self._derive_key(password, salt)
            
            # Create Fernet cipher and decrypt
            f = Fernet(key)
            decrypted = f.decrypt(encrypted_data)
            
            # Deserialize
            return json.loads(decrypted.decode())
            
        except json.JSONDecodeError as e:
            raise ConfigurationError("Invalid encrypted data format") from e
        except Exception as e:
            if "Invalid" in str(e) or "token" in str(e).lower():
                raise ConfigurationError("Decryption failed: incorrect password") from e
            raise ConfigurationError(f"Decryption failed: {e}") from e
    
    def encrypt_api_keys(self, api_keys: Dict[str, str], password: str, metadata: Optional[Dict[str, Any]] = None) -> str:
        """
        Encrypt API keys for export.
        
        Args:
            api_keys: Dictionary of provider -> API key
            password: Encryption password
            metadata: Optional metadata to include
            
        Returns:
            Encrypted package string
        """
        package = {
            'api_keys': api_keys,
            'metadata': metadata or {},
            'version': '1.0',
            'exported_at': __import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat()
        }
        
        return self.encrypt_data(package, password)
    
    def decrypt_api_keys(self, encrypted_str: str, password: str) -> Dict[str, Any]:
        """
        Decrypt API keys from export.
        
        Args:
            encrypted_str: Encrypted package string
            password: Decryption password
            
        Returns:
            Dictionary with 'api_keys' and 'metadata' keys
        """
        package = self.decrypt_data(encrypted_str, password)
        
        if 'api_keys' not in package:
            raise ConfigurationError("Invalid API key export format")
        
        return package


def store_encrypted_keys(file_path: Path, api_keys: Dict[str, str], password: str) -> None:
    """
    Store API keys in encrypted file.
    
    Args:
        file_path: Path to save encrypted file
        api_keys: Dictionary of API keys to encrypt
        password: Encryption password
    """
    encryptor = KeyEncryption()
    encrypted = encryptor.encrypt_api_keys(api_keys, password)
    
    # Write to file
    file_path.parent.mkdir(parents=True, exist_ok=True)
    with open(file_path, 'w') as f:
        f.write(encrypted)
    
    # Set restrictive permissions
    import stat
    os.chmod(file_path, stat.S_IRUSR | stat.S_IWUSR)


def load_encrypted_keys(file_path: Path, password: str) -> Dict[str, str]:
    """
    Load API keys from encrypted file.
    
    Args:
        file_path: Path to encrypted file
        password: Decryption password
        
    Returns:
        Dictionary of API keys
    """
    if not file_path.exists():
        raise FileNotFoundError(f"Encrypted file not found: {file_path}")
    
    with open(file_path, 'r') as f:
        encrypted = f.read()
    
    encryptor = KeyEncryption()
    package = encryptor.decrypt_api_keys(encrypted, password)
    
    return package['api_keys']




