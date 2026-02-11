"""
Security utilities for startd8 SDK

Provides functions for input sanitization, path validation, encryption, and security checks.
"""

import os
import base64
import json
import hashlib
import re
from pathlib import Path
from typing import Optional, Union, Dict, Any, List
from urllib.parse import urlparse
from ipaddress import ip_address, AddressValueError

try:
    from cryptography.fernet import Fernet
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    HAS_CRYPTOGRAPHY = True
except ImportError:
    HAS_CRYPTOGRAPHY = False
    Fernet = None
    PBKDF2HMAC = None
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
    # CRITICAL FIX: Check original input FIRST, before resolve()
    # After resolve(), '..' is normalized away, so we must check the original string
    path_str = str(file_path)
    
    # Check for directory traversal attempts in original input
    if '..' in path_str or path_str.startswith('/') and not path_str.startswith(str(Path.home())):
        # Additional check: look for path components with '..'
        path_parts = Path(path_str).parts
        if '..' in path_parts:
            raise ValidationError(
                "Path contains directory traversal attempt (..)",
                field="file_path",
                value=path_str
            )
    
    # Now resolve and check base directory
    try:
        raw_path = Path(file_path).expanduser()
        # Resolve relative paths against base_dir when provided,
        # so that target_files like "scripts/foo.py" resolve against
        # the project root rather than the current working directory.
        if base_dir and not raw_path.is_absolute():
            path = (Path(base_dir).resolve() / raw_path).resolve()
        else:
            path = raw_path.resolve()
    except (OSError, ValueError) as e:
        raise ValidationError(
            f"Invalid path: {e}",
            field="file_path",
            value=path_str
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
                value=path_str
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
        kdf = PBKDF2HMAC(
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
            if type(e).__name__ == "InvalidToken" or "Invalid" in str(e) or "token" in str(e).lower():
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


# ============================================================================
# Input Validation Functions
# ============================================================================

# Constants for validation
MAX_PROMPT_LENGTH = 1_000_000  # 1MB limit
MIN_MAX_TOKENS = 1
MAX_MAX_TOKENS = 1_000_000  # Reasonable upper limit
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
MAX_MODEL_NAME_LENGTH = 100
MAX_AGENT_NAME_LENGTH = 50


def sanitize_model_name_for_agent_name(model_name: str) -> str:
    """
    Sanitize a model name for use in default agent names.
    
    Removes or replaces characters that are not allowed in agent names
    (only letters, numbers, underscores, and hyphens are allowed).
    
    Args:
        model_name: Model name to sanitize (e.g., "gpt-4.5", "claude-3-opus-20240229")
    
    Returns:
        Sanitized model name safe for use in agent names
    
    Example:
        >>> sanitize_model_name_for_agent_name("gpt-4.5")
        'gpt-4-5'
        >>> sanitize_model_name_for_agent_name("claude-3-opus-20240229")
        'claude-3-opus-20240229'
        >>> sanitize_model_name_for_agent_name("model:name/with.dots")
        'model-name-with-dots'
    """
    if not model_name:
        return "model"
    
    # Replace common problematic characters with hyphens
    # This includes: dots, colons, slashes, spaces, and other special chars
    sanitized = re.sub(r'[^a-zA-Z0-9_-]', '-', str(model_name))
    
    # Collapse multiple consecutive hyphens into a single hyphen
    sanitized = re.sub(r'-+', '-', sanitized)
    
    # Remove leading/trailing hyphens
    sanitized = sanitized.strip('-')
    
    # Ensure it's not empty after sanitization
    if not sanitized:
        sanitized = "model"
    
    # Truncate if too long (leave room for provider prefix)
    if len(sanitized) > MAX_AGENT_NAME_LENGTH - 20:  # Reserve space for "provider-" prefix
        sanitized = sanitized[:MAX_AGENT_NAME_LENGTH - 20]
        sanitized = sanitized.rstrip('-')
    
    return sanitized

ALLOWED_FILE_EXTENSIONS = {
    '.txt', '.md', '.json', '.yaml', '.yml',
    '.py', '.js', '.ts', '.jsx', '.tsx',
    '.html', '.css', '.xml', '.csv', '.log',
    '.cfg', '.ini', '.toml'
}

MODEL_NAME_PATTERN = re.compile(r'^[a-zA-Z0-9._-]+$')
AGENT_NAME_PATTERN = re.compile(r'^[a-zA-Z0-9_-]+$')
ENV_VAR_NAME_PATTERN = re.compile(r'^[A-Z][A-Z0-9_]*$')


def validate_api_endpoint(url: str, allow_localhost: bool = False) -> str:
    """
    Validate API endpoint URL to prevent SSRF attacks.
    
    Args:
        url: URL to validate
        allow_localhost: Whether to allow localhost URLs (default: False)
    
    Returns:
        Validated URL string
    
    Raises:
        ValidationError: If URL is invalid or poses security risk
    """
    if not url:
        raise ValidationError("Base URL cannot be empty", field="base_url")
    
    # Parse URL
    try:
        parsed = urlparse(url)
    except Exception as e:
        raise ValidationError(f"Invalid URL format: {e}", field="base_url")
    
    # Must be http or https
    if parsed.scheme not in ('http', 'https'):
        raise ValidationError(
            f"URL scheme must be http or https, got: {parsed.scheme}",
            field="base_url"
        )
    
    # Must have hostname
    if not parsed.hostname:
        raise ValidationError("URL must include a hostname", field="base_url")
    
    # Block localhost/internal IPs unless explicitly allowed
    hostname = parsed.hostname.lower()
    
    if hostname in ('localhost', '127.0.0.1', '::1', '0.0.0.0'):
        if not allow_localhost:
            # Check environment variable as fallback
            allow_localhost = os.getenv('STARTD8_ALLOW_LOCALHOST') == 'true'
        
        if not allow_localhost:
            raise ValidationError(
                "Localhost URLs are not allowed for security reasons. "
                "Set STARTD8_ALLOW_LOCALHOST=true environment variable to allow.",
                field="base_url"
            )
    
    # Check for private/internal IPs
    try:
        ip = ip_address(hostname)
        if ip.is_private or ip.is_loopback or ip.is_link_local:
            if not allow_localhost and os.getenv('STARTD8_ALLOW_LOCALHOST') != 'true':
                raise ValidationError(
                    "Private/internal IP addresses are not allowed for security reasons",
                    field="base_url"
                )
    except (ValueError, AddressValueError):
        # Not an IP address, check hostname format
        if not re.match(r'^[a-zA-Z0-9.-]+$', hostname):
            raise ValidationError(
                "Hostname contains invalid characters",
                field="base_url"
            )
    
    # Validate port if specified
    if parsed.port is not None:
        if parsed.port < 1 or parsed.port > 65535:
            raise ValidationError(
                f"Port must be between 1 and 65535, got: {parsed.port}",
                field="base_url"
            )
    
    return url


def validate_max_tokens(value_str: str) -> int:
    """
    Validate and convert max_tokens input.
    
    Args:
        value_str: String value to validate
    
    Returns:
        Validated integer value
    
    Raises:
        ValidationError: If value is invalid or out of bounds
    """
    if not value_str:
        return 4096  # Default
    
    try:
        value = int(value_str)
    except ValueError:
        raise ValidationError(
            f"Max tokens must be a number, got: {value_str}",
            field="max_tokens"
        )
    
    if value < MIN_MAX_TOKENS:
        raise ValidationError(
            f"Max tokens must be at least {MIN_MAX_TOKENS}",
            field="max_tokens"
        )
    
    if value > MAX_MAX_TOKENS:
        raise ValidationError(
            f"Max tokens cannot exceed {MAX_MAX_TOKENS:,}",
            field="max_tokens"
        )
    
    return value


def validate_model_name(name: str) -> str:
    """
    Validate model name format to prevent injection attacks.
    
    Args:
        name: Model name to validate
    
    Returns:
        Validated model name
    
    Raises:
        ValidationError: If name is invalid
    """
    if not name:
        raise ValidationError("Model name cannot be empty", field="model")
    
    if len(name) > MAX_MODEL_NAME_LENGTH:
        raise ValidationError(
            f"Model name too long (max {MAX_MODEL_NAME_LENGTH} chars)",
            field="model"
        )
    
    if not MODEL_NAME_PATTERN.match(name):
        raise ValidationError(
            "Model name can only contain letters, numbers, dots, underscores, and hyphens",
            field="model"
        )
    
    return name


def validate_agent_name(name: str, existing_names: Optional[List[str]] = None) -> str:
    """
    Validate agent name format and check for conflicts.
    
    Args:
        name: Agent name to validate
        existing_names: Optional list of existing agent names to check against
    
    Returns:
        Validated agent name
    
    Raises:
        ValidationError: If name is invalid or conflicts with existing name
    """
    if not name:
        raise ValidationError("Agent name cannot be empty", field="name")
    
    if len(name) > MAX_AGENT_NAME_LENGTH:
        raise ValidationError(
            f"Agent name too long (max {MAX_AGENT_NAME_LENGTH} chars)",
            field="name"
        )
    
    if not AGENT_NAME_PATTERN.match(name):
        raise ValidationError(
            "Agent name can only contain letters, numbers, underscores, and hyphens",
            field="name"
        )
    
    if existing_names and name in existing_names:
        raise ValidationError(
            f"Agent name '{name}' already exists",
            field="name"
        )
    
    return name


def validate_file_extension(file_path: Path) -> None:
    """
    Validate file has allowed extension.
    
    Args:
        file_path: Path to validate
    
    Raises:
        ValidationError: If extension is not allowed
    """
    if file_path.suffix and file_path.suffix.lower() not in ALLOWED_FILE_EXTENSIONS:
        raise ValidationError(
            f"File extension '{file_path.suffix}' not allowed. "
            f"Allowed extensions: {', '.join(sorted(ALLOWED_FILE_EXTENSIONS))}",
            field="file_path"
        )


def validate_file_size(file_path: Path) -> None:
    """
    Validate file size is within limits.
    
    Args:
        file_path: Path to validate
    
    Raises:
        ValidationError: If file is too large
    """
    if not file_path.exists():
        return  # Can't check size of non-existent file
    
    size = file_path.stat().st_size
    if size > MAX_FILE_SIZE:
        raise ValidationError(
            f"File too large ({size:,} bytes, max {MAX_FILE_SIZE:,} bytes)",
            field="file_path"
        )


def sanitize_prompt_content(content: str) -> str:
    """
    Sanitize prompt content to prevent encoding issues and injection.
    
    Args:
        content: Prompt content to sanitize
    
    Returns:
        Sanitized content
    
    Raises:
        ValidationError: If content is invalid
    """
    if not content:
        raise ValidationError("Prompt content cannot be empty", field="content")
    
    # Remove null bytes
    content = content.replace('\x00', '')
    
    # Validate encoding
    try:
        content.encode('utf-8')
    except UnicodeEncodeError as e:
        raise ValidationError(
            f"Prompt contains invalid UTF-8 characters: {e}",
            field="content"
        )
    
    # Validate length
    if len(content) > MAX_PROMPT_LENGTH:
        raise ValidationError(
            f"Prompt content exceeds maximum length of {MAX_PROMPT_LENGTH:,} characters",
            field="content"
        )
    
    # Strip leading/trailing whitespace but preserve intentional formatting
    content = content.strip()
    
    if not content:
        raise ValidationError("Prompt content cannot be empty after sanitization", field="content")
    
    return content


def validate_env_var_name(name: str) -> str:
    """
    Validate environment variable name format.
    
    Args:
        name: Environment variable name to validate
    
    Returns:
        Validated name
    
    Raises:
        ValidationError: If name is invalid
    """
    if not name:
        raise ValidationError("Environment variable name cannot be empty", field="api_key_env")
    
    if not ENV_VAR_NAME_PATTERN.match(name):
        raise ValidationError(
            "Environment variable name must be uppercase, start with a letter, "
            "and contain only letters, numbers, and underscores",
            field="api_key_env"
        )
    
    return name




