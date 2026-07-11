# Phase 1: Critical Security - Detailed Design

**Phase Duration**: 2 Weeks  
**Total Effort**: 50 hours  
**Priority**: 🔴 CRITICAL  
**Status**: Ready for Implementation

---

## Table of Contents
1. [P1.1 Secure API Key Manager](#p11-secure-api-key-manager)
2. [P1.2 Rate Limiter & Circuit Breaker](#p12-rate-limiter--circuit-breaker)
3. [P1.3 Input Validator](#p13-input-validator)
4. [P1.4 Safe File Operations](#p14-safe-file-operations)
5. [P1.5 Async Retry Handler](#p15-async-retry-handler)
6. [P1.6 Graceful Shutdown Manager](#p16-graceful-shutdown-manager)

---

## P1.1 Secure API Key Manager

**File**: `src/startd8/secure_key_manager.py`  
**Effort**: 12 hours  
**Replaces**: `APIKeyManager` in `tui_improved.py`

### Purpose
Store and manage API keys securely using OS keychain (preferred) or encrypted file storage.

### Requirements
- REQ-1.1.1: Use OS keychain when available (macOS Keychain, Windows Credential Store, Linux Secret Service)
- REQ-1.1.2: Fall back to Fernet-encrypted file storage when keychain unavailable
- REQ-1.1.3: Environment variables always take priority
- REQ-1.1.4: Never store plaintext keys on disk
- REQ-1.1.5: Support key rotation without downtime

### Class Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                      SecureKeyManager                            │
├─────────────────────────────────────────────────────────────────┤
│ - _service_name: str                                            │
│ - _storage_backend: KeyStorageBackend                           │
│ - _cache: Dict[str, str]                                        │
│ - _lock: threading.RLock                                        │
├─────────────────────────────────────────────────────────────────┤
│ + __init__(service_name: str, storage_dir: Path)                │
│ + get_key(key_name: str) -> Optional[str]                       │
│ + set_key(key_name: str, key_value: str) -> bool                │
│ + delete_key(key_name: str) -> bool                             │
│ + list_keys() -> List[str]                                      │
│ + get_key_status(key_name: str) -> KeyStatus                    │
│ + rotate_key(key_name: str, new_value: str) -> bool             │
│ + export_keys(password: str) -> str                             │
│ + import_keys(encrypted: str, password: str) -> ImportResult    │
│ - _select_backend() -> KeyStorageBackend                        │
│ - _validate_key_format(key_name: str, key_value: str) -> bool   │
└─────────────────────────────────────────────────────────────────┘
                              │
                              │ uses
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                  <<interface>> KeyStorageBackend                 │
├─────────────────────────────────────────────────────────────────┤
│ + store(key_name: str, key_value: str) -> bool                  │
│ + retrieve(key_name: str) -> Optional[str]                      │
│ + delete(key_name: str) -> bool                                 │
│ + list_keys() -> List[str]                                      │
│ + is_available() -> bool                                        │
└─────────────────────────────────────────────────────────────────┘
          △                               △
          │                               │
          │                               │
┌─────────────────────┐     ┌─────────────────────────────────────┐
│  KeychainBackend    │     │      EncryptedFileBackend           │
├─────────────────────┤     ├─────────────────────────────────────┤
│ - _service: str     │     │ - _file_path: Path                  │
│                     │     │ - _master_key: bytes                │
│                     │     │ - _fernet: Fernet                   │
└─────────────────────┘     └─────────────────────────────────────┘
```

### Implementation

```python
# src/startd8/secure_key_manager.py
"""
Secure API Key Manager for startd8 SDK.

Provides encrypted storage for API keys using OS keychain (preferred)
or Fernet-encrypted file storage as fallback.
"""

import os
import json
import logging
import threading
import hashlib
import base64
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, List, Dict, Any
from enum import Enum

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

logger = logging.getLogger(__name__)

# Try to import keyring for OS keychain support
try:
    import keyring
    from keyring.errors import KeyringError
    HAS_KEYRING = True
except ImportError:
    HAS_KEYRING = False
    KeyringError = Exception


class KeySource(Enum):
    """Source of an API key"""
    ENVIRONMENT = "environment"
    KEYCHAIN = "keychain"
    ENCRYPTED_FILE = "encrypted_file"
    NOT_SET = "not_set"


@dataclass
class KeyStatus:
    """Status information for an API key"""
    key_name: str
    is_set: bool
    source: KeySource
    masked_value: Optional[str] = None
    last_rotated: Optional[str] = None


@dataclass
class ImportResult:
    """Result of key import operation"""
    success: bool
    imported: List[str]
    skipped: List[str]
    errors: List[str]


class KeyStorageBackend(ABC):
    """Abstract base class for key storage backends"""
    
    @abstractmethod
    def store(self, key_name: str, key_value: str) -> bool:
        """Store a key"""
        pass
    
    @abstractmethod
    def retrieve(self, key_name: str) -> Optional[str]:
        """Retrieve a key"""
        pass
    
    @abstractmethod
    def delete(self, key_name: str) -> bool:
        """Delete a key"""
        pass
    
    @abstractmethod
    def list_keys(self) -> List[str]:
        """List all stored key names"""
        pass
    
    @abstractmethod
    def is_available(self) -> bool:
        """Check if backend is available"""
        pass


class KeychainBackend(KeyStorageBackend):
    """OS Keychain storage backend (macOS, Windows, Linux)"""
    
    def __init__(self, service_name: str):
        self._service = service_name
        self._key_registry_name = f"{service_name}_key_registry"
    
    def is_available(self) -> bool:
        if not HAS_KEYRING:
            return False
        try:
            # Test keyring access
            keyring.get_password(self._service, "__test__")
            return True
        except Exception:
            return False
    
    def store(self, key_name: str, key_value: str) -> bool:
        try:
            keyring.set_password(self._service, key_name, key_value)
            self._update_registry(key_name, add=True)
            logger.info(f"Stored key '{key_name}' in OS keychain")
            return True
        except KeyringError as e:
            logger.error(f"Failed to store key in keychain: {e}")
            return False
    
    def retrieve(self, key_name: str) -> Optional[str]:
        try:
            return keyring.get_password(self._service, key_name)
        except KeyringError as e:
            logger.error(f"Failed to retrieve key from keychain: {e}")
            return None
    
    def delete(self, key_name: str) -> bool:
        try:
            keyring.delete_password(self._service, key_name)
            self._update_registry(key_name, add=False)
            return True
        except KeyringError:
            return False
    
    def list_keys(self) -> List[str]:
        try:
            registry = keyring.get_password(self._service, self._key_registry_name)
            if registry:
                return json.loads(registry)
            return []
        except Exception:
            return []
    
    def _update_registry(self, key_name: str, add: bool):
        """Update the key registry"""
        keys = set(self.list_keys())
        if add:
            keys.add(key_name)
        else:
            keys.discard(key_name)
        try:
            keyring.set_password(
                self._service,
                self._key_registry_name,
                json.dumps(list(keys))
            )
        except KeyringError:
            pass


class EncryptedFileBackend(KeyStorageBackend):
    """Encrypted file storage backend using Fernet"""
    
    PBKDF2_ITERATIONS = 480000  # OWASP recommended
    
    def __init__(self, storage_dir: Path, machine_id: Optional[str] = None):
        self._storage_dir = Path(storage_dir)
        self._file_path = self._storage_dir / "keys.enc"
        self._salt_path = self._storage_dir / ".salt"
        self._fernet: Optional[Fernet] = None
        self._machine_id = machine_id or self._get_machine_id()
        self._initialize()
    
    def _get_machine_id(self) -> str:
        """Get a unique machine identifier for key derivation"""
        # Combine various system attributes for uniqueness
        import platform
        import uuid
        
        components = [
            platform.node(),
            str(uuid.getnode()),  # MAC address
            os.getenv("USER", ""),
            os.getenv("HOME", ""),
        ]
        return hashlib.sha256(":".join(components).encode()).hexdigest()[:32]
    
    def _initialize(self):
        """Initialize encryption"""
        self._storage_dir.mkdir(parents=True, exist_ok=True)
        
        # Get or create salt
        if self._salt_path.exists():
            salt = self._salt_path.read_bytes()
        else:
            salt = os.urandom(16)
            self._salt_path.write_bytes(salt)
            # Set restrictive permissions
            try:
                os.chmod(self._salt_path, 0o600)
            except OSError:
                pass
        
        # Derive key from machine ID
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=self.PBKDF2_ITERATIONS,
        )
        key = base64.urlsafe_b64encode(kdf.derive(self._machine_id.encode()))
        self._fernet = Fernet(key)
    
    def is_available(self) -> bool:
        return self._fernet is not None
    
    def _load_keys(self) -> Dict[str, str]:
        """Load and decrypt keys from file"""
        if not self._file_path.exists():
            return {}
        
        try:
            encrypted = self._file_path.read_bytes()
            decrypted = self._fernet.decrypt(encrypted)
            return json.loads(decrypted.decode())
        except Exception as e:
            logger.error(f"Failed to load encrypted keys: {e}")
            return {}
    
    def _save_keys(self, keys: Dict[str, str]) -> bool:
        """Encrypt and save keys to file"""
        try:
            data = json.dumps(keys).encode()
            encrypted = self._fernet.encrypt(data)
            self._file_path.write_bytes(encrypted)
            
            # Set restrictive permissions
            try:
                os.chmod(self._file_path, 0o600)
            except OSError:
                pass
            
            return True
        except Exception as e:
            logger.error(f"Failed to save encrypted keys: {e}")
            return False
    
    def store(self, key_name: str, key_value: str) -> bool:
        keys = self._load_keys()
        keys[key_name] = key_value
        success = self._save_keys(keys)
        if success:
            logger.info(f"Stored key '{key_name}' in encrypted file")
        return success
    
    def retrieve(self, key_name: str) -> Optional[str]:
        keys = self._load_keys()
        return keys.get(key_name)
    
    def delete(self, key_name: str) -> bool:
        keys = self._load_keys()
        if key_name in keys:
            del keys[key_name]
            return self._save_keys(keys)
        return True
    
    def list_keys(self) -> List[str]:
        return list(self._load_keys().keys())


class SecureKeyManager:
    """
    Secure API Key Manager with OS keychain support and encrypted fallback.
    
    Priority order for key retrieval:
    1. Environment variables (highest priority)
    2. OS Keychain (if available)
    3. Encrypted file storage
    
    Example:
        >>> manager = SecureKeyManager()
        >>> manager.set_key("ANTHROPIC_API_KEY", "sk-ant-...")
        >>> key = manager.get_key("ANTHROPIC_API_KEY")
    """
    
    # Known API key patterns for validation
    KEY_PATTERNS = {
        "ANTHROPIC_API_KEY": r"^sk-ant-[a-zA-Z0-9-]{20,}$",
        "OPENAI_API_KEY": r"^sk-(proj-)?[a-zA-Z0-9]{20,}$",
    }
    
    def __init__(
        self,
        service_name: str = "startd8",
        storage_dir: Optional[Path] = None
    ):
        """
        Initialize SecureKeyManager.
        
        Args:
            service_name: Name for keychain service identification
            storage_dir: Directory for encrypted file storage
        """
        self._service_name = service_name
        self._storage_dir = storage_dir or Path.home() / ".startd8"
        self._cache: Dict[str, str] = {}
        self._lock = threading.RLock()
        
        # Select storage backend
        self._backend = self._select_backend()
        
        logger.info(f"SecureKeyManager initialized with {type(self._backend).__name__}")
    
    def _select_backend(self) -> KeyStorageBackend:
        """Select the best available storage backend"""
        # Try keychain first
        keychain = KeychainBackend(self._service_name)
        if keychain.is_available():
            logger.info("Using OS keychain for key storage")
            return keychain
        
        # Fall back to encrypted file
        logger.info("OS keychain not available, using encrypted file storage")
        return EncryptedFileBackend(self._storage_dir)
    
    @staticmethod
    def _mask_key(key_value: str) -> str:
        """Mask API key for display"""
        if not key_value or len(key_value) <= 8:
            return "***"
        return key_value[:4] + "..." + key_value[-4:]
    
    def _validate_key_format(self, key_name: str, key_value: str) -> bool:
        """Validate API key format"""
        import re
        
        if not key_value or len(key_value) < 10:
            return False
        
        pattern = self.KEY_PATTERNS.get(key_name)
        if pattern:
            return bool(re.match(pattern, key_value))
        
        # Generic validation for unknown keys
        return len(key_value) >= 10
    
    def get_key(self, key_name: str) -> Optional[str]:
        """
        Get an API key.
        
        Priority: Environment > Keychain/Encrypted File
        
        Args:
            key_name: Name of the key (e.g., "ANTHROPIC_API_KEY")
            
        Returns:
            The API key value or None if not found
        """
        # Environment variable always takes priority
        env_value = os.getenv(key_name)
        if env_value:
            return env_value
        
        # Check cache
        with self._lock:
            if key_name in self._cache:
                return self._cache[key_name]
        
        # Retrieve from backend
        value = self._backend.retrieve(key_name)
        
        # Cache the result
        if value:
            with self._lock:
                self._cache[key_name] = value
        
        return value
    
    def set_key(self, key_name: str, key_value: str, validate: bool = True) -> bool:
        """
        Store an API key securely.
        
        Args:
            key_name: Name of the key
            key_value: The API key value
            validate: Whether to validate key format
            
        Returns:
            True if successful
        """
        if validate and not self._validate_key_format(key_name, key_value):
            logger.warning(f"Key '{key_name}' failed format validation")
            return False
        
        success = self._backend.store(key_name, key_value)
        
        if success:
            # Update cache
            with self._lock:
                self._cache[key_name] = key_value
            
            # Set in environment for current session
            os.environ[key_name] = key_value
        
        return success
    
    def delete_key(self, key_name: str) -> bool:
        """
        Delete an API key.
        
        Args:
            key_name: Name of the key to delete
            
        Returns:
            True if successful
        """
        success = self._backend.delete(key_name)
        
        if success:
            # Remove from cache
            with self._lock:
                self._cache.pop(key_name, None)
            
            # Remove from environment
            os.environ.pop(key_name, None)
        
        return success
    
    def list_keys(self) -> List[str]:
        """
        List all stored key names.
        
        Returns:
            List of key names
        """
        return self._backend.list_keys()
    
    def get_key_status(self, key_name: str) -> KeyStatus:
        """
        Get status information for a key.
        
        Args:
            key_name: Name of the key
            
        Returns:
            KeyStatus with source and masked value
        """
        # Check environment first
        env_value = os.getenv(key_name)
        if env_value:
            return KeyStatus(
                key_name=key_name,
                is_set=True,
                source=KeySource.ENVIRONMENT,
                masked_value=self._mask_key(env_value)
            )
        
        # Check backend
        stored_value = self._backend.retrieve(key_name)
        if stored_value:
            source = (
                KeySource.KEYCHAIN 
                if isinstance(self._backend, KeychainBackend)
                else KeySource.ENCRYPTED_FILE
            )
            return KeyStatus(
                key_name=key_name,
                is_set=True,
                source=source,
                masked_value=self._mask_key(stored_value)
            )
        
        return KeyStatus(
            key_name=key_name,
            is_set=False,
            source=KeySource.NOT_SET
        )
    
    def rotate_key(self, key_name: str, new_value: str) -> bool:
        """
        Rotate an API key to a new value.
        
        Args:
            key_name: Name of the key
            new_value: New key value
            
        Returns:
            True if successful
        """
        # Validate new key
        if not self._validate_key_format(key_name, new_value):
            logger.warning(f"New key for '{key_name}' failed validation")
            return False
        
        # Store new key (overwrites old)
        success = self.set_key(key_name, new_value, validate=False)
        
        if success:
            logger.info(f"Rotated key '{key_name}'")
        
        return success
    
    def load_all_to_environment(self):
        """Load all stored keys into environment variables"""
        for key_name in self.list_keys():
            if not os.getenv(key_name):
                value = self._backend.retrieve(key_name)
                if value:
                    os.environ[key_name] = value
    
    def clear_cache(self):
        """Clear the in-memory cache"""
        with self._lock:
            self._cache.clear()


# Module-level singleton
_manager: Optional[SecureKeyManager] = None


def get_secure_key_manager(
    service_name: str = "startd8",
    storage_dir: Optional[Path] = None
) -> SecureKeyManager:
    """Get or create the singleton SecureKeyManager instance"""
    global _manager
    if _manager is None:
        _manager = SecureKeyManager(service_name, storage_dir)
    return _manager
```

### Unit Tests

```python
# tests/test_secure_key_manager.py
import pytest
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

from startd8.secure_key_manager import (
    SecureKeyManager,
    KeychainBackend,
    EncryptedFileBackend,
    KeySource,
    KeyStatus
)


class TestSecureKeyManager:
    """Tests for SecureKeyManager"""
    
    @pytest.fixture
    def temp_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)
    
    @pytest.fixture
    def manager(self, temp_dir):
        return SecureKeyManager(storage_dir=temp_dir)
    
    def test_set_and_get_key(self, manager):
        """Test basic key storage and retrieval"""
        manager.set_key("TEST_KEY", "test-value-12345", validate=False)
        assert manager.get_key("TEST_KEY") == "test-value-12345"
    
    def test_environment_priority(self, manager):
        """Test that environment variables take priority"""
        manager.set_key("ENV_TEST_KEY", "stored-value", validate=False)
        
        with patch.dict('os.environ', {'ENV_TEST_KEY': 'env-value'}):
            assert manager.get_key("ENV_TEST_KEY") == "env-value"
    
    def test_delete_key(self, manager):
        """Test key deletion"""
        manager.set_key("DELETE_TEST", "value", validate=False)
        assert manager.get_key("DELETE_TEST") == "value"
        
        manager.delete_key("DELETE_TEST")
        assert manager.get_key("DELETE_TEST") is None
    
    def test_key_status(self, manager):
        """Test key status reporting"""
        status = manager.get_key_status("NONEXISTENT_KEY")
        assert status.is_set is False
        assert status.source == KeySource.NOT_SET
        
        manager.set_key("STATUS_TEST", "value123456", validate=False)
        status = manager.get_key_status("STATUS_TEST")
        assert status.is_set is True
        assert status.masked_value == "valu...3456"
    
    def test_key_validation_anthropic(self, manager):
        """Test Anthropic key format validation"""
        # Valid format
        assert manager.set_key(
            "ANTHROPIC_API_KEY",
            "sk-ant-api03-validkey123456789012345"
        ) is True
        
        # Invalid format (doesn't start with sk-ant-)
        assert manager.set_key(
            "ANTHROPIC_API_KEY",
            "invalid-key-format"
        ) is False
    
    def test_list_keys(self, manager):
        """Test listing stored keys"""
        manager.set_key("KEY1", "value1-12345", validate=False)
        manager.set_key("KEY2", "value2-12345", validate=False)
        
        keys = manager.list_keys()
        assert "KEY1" in keys
        assert "KEY2" in keys
    
    def test_rotate_key(self, manager):
        """Test key rotation"""
        manager.set_key("ROTATE_KEY", "old-value-12345", validate=False)
        
        manager.rotate_key("ROTATE_KEY", "new-value-12345")
        assert manager.get_key("ROTATE_KEY") == "new-value-12345"


class TestEncryptedFileBackend:
    """Tests for encrypted file storage"""
    
    @pytest.fixture
    def backend(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            yield EncryptedFileBackend(Path(tmpdir))
    
    def test_encryption_roundtrip(self, backend):
        """Test that keys survive encryption roundtrip"""
        backend.store("TEST", "secret-value")
        assert backend.retrieve("TEST") == "secret-value"
    
    def test_different_machine_cannot_decrypt(self, backend):
        """Test that different machine ID cannot decrypt"""
        backend.store("TEST", "secret-value")
        
        # Create new backend with different machine ID
        backend2 = EncryptedFileBackend(
            backend._storage_dir,
            machine_id="different-machine"
        )
        
        # Should fail to decrypt
        assert backend2.retrieve("TEST") is None
```

### Migration Guide

```python
# Migration from APIKeyManager to SecureKeyManager

# OLD CODE:
# from tui_improved import APIKeyManager
# key_manager = APIKeyManager(storage_dir)
# key = key_manager.get_key("ANTHROPIC_API_KEY")

# NEW CODE:
from startd8.secure_key_manager import get_secure_key_manager

key_manager = get_secure_key_manager()
key = key_manager.get_key("ANTHROPIC_API_KEY")

# Migration script to convert existing plaintext keys:
def migrate_keys():
    """Migrate keys from old plaintext storage to secure storage"""
    import json
    
    old_file = Path.home() / ".startd8" / "api_keys.json"
    if old_file.exists():
        with open(old_file) as f:
            old_keys = json.load(f)
        
        manager = get_secure_key_manager()
        for key_name, key_value in old_keys.items():
            if key_value:
                manager.set_key(key_name, key_value, validate=False)
                print(f"Migrated: {key_name}")
        
        # Backup and remove old file
        backup = old_file.with_suffix('.json.bak')
        old_file.rename(backup)
        print(f"Old keys backed up to: {backup}")
```

---

## P1.2 Rate Limiter & Circuit Breaker

**File**: `src/startd8/rate_limiter.py`  
**Effort**: 10 hours

### Purpose
Prevent API abuse, runaway costs, and handle API failures gracefully.

### Requirements
- REQ-1.2.1: Token bucket rate limiting per provider
- REQ-1.2.2: Circuit breaker with configurable thresholds
- REQ-1.2.3: Automatic recovery after failures
- REQ-1.2.4: Cost estimation before requests
- REQ-1.2.5: Thread-safe implementation

### Implementation

```python
# src/startd8/rate_limiter.py
"""
Rate Limiter and Circuit Breaker for API protection.

Implements:
- Token bucket rate limiting
- Circuit breaker pattern for failure resilience
- Cost estimation and budget enforcement
"""

import asyncio
import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Optional, Dict, List, Callable, Awaitable, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar('T')


class CircuitState(Enum):
    """Circuit breaker states"""
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Failing, reject requests
    HALF_OPEN = "half_open"  # Testing recovery


@dataclass
class RateLimitConfig:
    """Configuration for rate limiting"""
    requests_per_minute: int = 60
    tokens_per_minute: int = 100000
    max_concurrent: int = 10
    
    # Cost limits
    max_cost_per_request: float = 1.0
    max_cost_per_minute: float = 10.0
    max_cost_per_hour: float = 50.0


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker"""
    failure_threshold: int = 5       # Failures before opening
    success_threshold: int = 2       # Successes to close from half-open
    timeout_seconds: int = 60        # Time before attempting recovery
    half_open_max_calls: int = 1     # Max calls in half-open state


@dataclass
class RequestMetrics:
    """Metrics for a single request"""
    timestamp: datetime
    tokens_used: int
    cost: float
    success: bool
    latency_ms: int


class RateLimiter:
    """
    Token bucket rate limiter with cost tracking.
    
    Example:
        limiter = RateLimiter(RateLimitConfig(requests_per_minute=60))
        
        if await limiter.acquire(estimated_tokens=1000):
            # Make API call
            await limiter.record(tokens_used=1234, cost=0.05, success=True)
        else:
            # Rate limited, wait or reject
    """
    
    def __init__(self, config: RateLimitConfig = None):
        self.config = config or RateLimitConfig()
        self._lock = asyncio.Lock()
        self._requests: List[RequestMetrics] = []
        self._semaphore = asyncio.Semaphore(self.config.max_concurrent)
    
    async def acquire(
        self,
        estimated_tokens: int = 1000,
        estimated_cost: float = 0.01
    ) -> bool:
        """
        Attempt to acquire a rate limit slot.
        
        Args:
            estimated_tokens: Estimated tokens for request
            estimated_cost: Estimated cost for request
            
        Returns:
            True if request can proceed, False if rate limited
        """
        async with self._lock:
            now = datetime.now(timezone.utc)
            
            # Clean old entries
            cutoff_minute = now - timedelta(minutes=1)
            cutoff_hour = now - timedelta(hours=1)
            
            self._requests = [
                r for r in self._requests
                if r.timestamp > cutoff_hour
            ]
            
            # Get recent metrics
            recent_minute = [
                r for r in self._requests
                if r.timestamp > cutoff_minute
            ]
            
            # Check request rate
            if len(recent_minute) >= self.config.requests_per_minute:
                logger.warning("Rate limit exceeded: requests per minute")
                return False
            
            # Check token rate
            tokens_used = sum(r.tokens_used for r in recent_minute)
            if tokens_used + estimated_tokens > self.config.tokens_per_minute:
                logger.warning("Rate limit exceeded: tokens per minute")
                return False
            
            # Check cost limits
            cost_minute = sum(r.cost for r in recent_minute)
            if cost_minute + estimated_cost > self.config.max_cost_per_minute:
                logger.warning("Rate limit exceeded: cost per minute")
                return False
            
            cost_hour = sum(r.cost for r in self._requests)
            if cost_hour + estimated_cost > self.config.max_cost_per_hour:
                logger.warning("Rate limit exceeded: cost per hour")
                return False
            
            return True
    
    async def record(
        self,
        tokens_used: int,
        cost: float,
        success: bool,
        latency_ms: int = 0
    ):
        """Record metrics for a completed request"""
        async with self._lock:
            self._requests.append(RequestMetrics(
                timestamp=datetime.now(timezone.utc),
                tokens_used=tokens_used,
                cost=cost,
                success=success,
                latency_ms=latency_ms
            ))
    
    def get_stats(self) -> Dict:
        """Get current rate limit statistics"""
        now = datetime.now(timezone.utc)
        cutoff_minute = now - timedelta(minutes=1)
        
        recent = [r for r in self._requests if r.timestamp > cutoff_minute]
        
        return {
            "requests_last_minute": len(recent),
            "tokens_last_minute": sum(r.tokens_used for r in recent),
            "cost_last_minute": sum(r.cost for r in recent),
            "requests_remaining": self.config.requests_per_minute - len(recent),
            "tokens_remaining": self.config.tokens_per_minute - sum(r.tokens_used for r in recent),
        }


class CircuitBreaker:
    """
    Circuit breaker for API resilience.
    
    States:
    - CLOSED: Normal operation, requests pass through
    - OPEN: Failures exceeded threshold, requests rejected
    - HALF_OPEN: Testing if service recovered
    
    Example:
        breaker = CircuitBreaker(CircuitBreakerConfig(failure_threshold=5))
        
        if breaker.can_execute():
            try:
                result = await make_api_call()
                breaker.record_success()
            except Exception as e:
                breaker.record_failure()
                raise
        else:
            raise ServiceUnavailableError("Circuit breaker open")
    """
    
    def __init__(self, config: CircuitBreakerConfig = None):
        self.config = config or CircuitBreakerConfig()
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time: Optional[datetime] = None
        self._half_open_calls = 0
        self._lock = threading.RLock()
    
    @property
    def state(self) -> CircuitState:
        """Get current circuit state"""
        with self._lock:
            if self._state == CircuitState.OPEN:
                # Check if timeout elapsed
                if self._last_failure_time:
                    elapsed = datetime.now(timezone.utc) - self._last_failure_time
                    if elapsed.total_seconds() > self.config.timeout_seconds:
                        self._state = CircuitState.HALF_OPEN
                        self._half_open_calls = 0
                        logger.info("Circuit breaker transitioning to HALF_OPEN")
            
            return self._state
    
    def can_execute(self) -> bool:
        """Check if a request can be executed"""
        with self._lock:
            current_state = self.state
            
            if current_state == CircuitState.CLOSED:
                return True
            
            if current_state == CircuitState.OPEN:
                return False
            
            # HALF_OPEN - allow limited calls
            if self._half_open_calls < self.config.half_open_max_calls:
                self._half_open_calls += 1
                return True
            
            return False
    
    def record_success(self):
        """Record a successful request"""
        with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                self._success_count += 1
                if self._success_count >= self.config.success_threshold:
                    self._state = CircuitState.CLOSED
                    self._failure_count = 0
                    self._success_count = 0
                    logger.info("Circuit breaker CLOSED after recovery")
            else:
                # In CLOSED state, reset failure count on success
                self._failure_count = 0
    
    def record_failure(self):
        """Record a failed request"""
        with self._lock:
            self._failure_count += 1
            self._last_failure_time = datetime.now(timezone.utc)
            
            if self._state == CircuitState.HALF_OPEN:
                # Immediate trip back to OPEN
                self._state = CircuitState.OPEN
                self._success_count = 0
                logger.warning("Circuit breaker OPEN after half-open failure")
            elif self._failure_count >= self.config.failure_threshold:
                self._state = CircuitState.OPEN
                logger.warning(f"Circuit breaker OPEN after {self._failure_count} failures")
    
    def reset(self):
        """Manually reset the circuit breaker"""
        with self._lock:
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            self._success_count = 0
            self._half_open_calls = 0
            logger.info("Circuit breaker manually reset")


class ProviderRateLimiter:
    """
    Rate limiter manager for multiple API providers.
    
    Example:
        limiter = ProviderRateLimiter()
        limiter.configure("anthropic", RateLimitConfig(requests_per_minute=50))
        
        async with limiter.acquire("anthropic", tokens=1000) as slot:
            result = await call_api()
            await slot.record(tokens=1234, cost=0.05)
    """
    
    def __init__(self):
        self._limiters: Dict[str, RateLimiter] = {}
        self._breakers: Dict[str, CircuitBreaker] = {}
        self._lock = threading.RLock()
    
    def configure(
        self,
        provider: str,
        rate_config: RateLimitConfig = None,
        breaker_config: CircuitBreakerConfig = None
    ):
        """Configure rate limiting for a provider"""
        with self._lock:
            self._limiters[provider] = RateLimiter(rate_config)
            self._breakers[provider] = CircuitBreaker(breaker_config)
    
    def get_limiter(self, provider: str) -> RateLimiter:
        """Get rate limiter for provider"""
        with self._lock:
            if provider not in self._limiters:
                self._limiters[provider] = RateLimiter()
            return self._limiters[provider]
    
    def get_breaker(self, provider: str) -> CircuitBreaker:
        """Get circuit breaker for provider"""
        with self._lock:
            if provider not in self._breakers:
                self._breakers[provider] = CircuitBreaker()
            return self._breakers[provider]
    
    async def execute(
        self,
        provider: str,
        func: Callable[[], Awaitable[T]],
        estimated_tokens: int = 1000,
        estimated_cost: float = 0.01
    ) -> T:
        """
        Execute a function with rate limiting and circuit breaking.
        
        Args:
            provider: API provider name
            func: Async function to execute
            estimated_tokens: Estimated tokens for request
            estimated_cost: Estimated cost for request
            
        Returns:
            Result from func
            
        Raises:
            RateLimitError: If rate limited
            CircuitOpenError: If circuit breaker is open
        """
        limiter = self.get_limiter(provider)
        breaker = self.get_breaker(provider)
        
        # Check circuit breaker
        if not breaker.can_execute():
            raise CircuitOpenError(f"Circuit breaker open for {provider}")
        
        # Check rate limit
        if not await limiter.acquire(estimated_tokens, estimated_cost):
            raise RateLimitError(f"Rate limit exceeded for {provider}")
        
        start_time = time.time()
        try:
            result = await func()
            breaker.record_success()
            return result
        except Exception as e:
            breaker.record_failure()
            raise
        finally:
            latency_ms = int((time.time() - start_time) * 1000)
            # Note: Actual tokens/cost should be recorded by caller


class RateLimitError(Exception):
    """Raised when rate limit is exceeded"""
    pass


class CircuitOpenError(Exception):
    """Raised when circuit breaker is open"""
    pass


# Default provider configurations
DEFAULT_CONFIGS = {
    "anthropic": RateLimitConfig(
        requests_per_minute=50,
        tokens_per_minute=80000,
        max_cost_per_minute=5.0
    ),
    "openai": RateLimitConfig(
        requests_per_minute=60,
        tokens_per_minute=90000,
        max_cost_per_minute=5.0
    ),
}


# Global instance
_provider_limiter: Optional[ProviderRateLimiter] = None


def get_provider_limiter() -> ProviderRateLimiter:
    """Get or create the global ProviderRateLimiter"""
    global _provider_limiter
    if _provider_limiter is None:
        _provider_limiter = ProviderRateLimiter()
        # Configure defaults
        for provider, config in DEFAULT_CONFIGS.items():
            _provider_limiter.configure(provider, config)
    return _provider_limiter
```

### Integration Example

```python
# In agents.py - integrate rate limiting

from .rate_limiter import get_provider_limiter, RateLimitError, CircuitOpenError

class ClaudeAgent(BaseAgent):
    async def agenerate(self, prompt: str) -> Tuple[str, int, TokenUsage]:
        limiter = get_provider_limiter()
        
        # Estimate tokens (rough: 4 chars per token)
        estimated_tokens = len(prompt) // 4 + 1000  # Plus expected response
        
        async def _call():
            return await self.async_client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                messages=[{"role": "user", "content": prompt}]
            )
        
        try:
            response = await limiter.execute(
                "anthropic",
                _call,
                estimated_tokens=estimated_tokens
            )
        except RateLimitError:
            logger.warning("Rate limited, waiting...")
            await asyncio.sleep(60)  # Wait and retry
            response = await limiter.execute("anthropic", _call, estimated_tokens)
        except CircuitOpenError:
            raise APIError("Anthropic API unavailable, circuit breaker open")
        
        # Record actual usage
        actual_tokens = response.usage.input_tokens + response.usage.output_tokens
        await limiter.get_limiter("anthropic").record(
            tokens_used=actual_tokens,
            cost=self._calculate_cost(response.usage),
            success=True
        )
        
        # ... rest of response processing
```

---

## P1.3 Input Validator

**File**: `src/startd8/validators.py`  
**Effort**: 8 hours

### Purpose
Validate and sanitize all user inputs before processing.

### Implementation

```python
# src/startd8/validators.py
"""
Input Validators for startd8 SDK.

Provides validation for:
- User prompts (injection detection, length limits)
- File paths (traversal protection)
- Configuration values
- API responses
"""

import re
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple, Any, Dict
from enum import Enum

logger = logging.getLogger(__name__)


class ValidationSeverity(Enum):
    """Severity of validation finding"""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class ValidationResult:
    """Result of a validation operation"""
    is_valid: bool
    sanitized_value: Any
    findings: List[Tuple[ValidationSeverity, str]]
    
    def has_warnings(self) -> bool:
        return any(s == ValidationSeverity.WARNING for s, _ in self.findings)
    
    def has_errors(self) -> bool:
        return any(s in (ValidationSeverity.ERROR, ValidationSeverity.CRITICAL) 
                   for s, _ in self.findings)


class PromptValidator:
    """
    Validate user prompts for safety and quality.
    
    Checks for:
    - Maximum length limits
    - Potential injection patterns
    - Token estimation
    - Cost estimation
    
    Example:
        validator = PromptValidator()
        result = validator.validate("Write a Python function...")
        
        if result.is_valid:
            safe_prompt = result.sanitized_value
        else:
            for severity, message in result.findings:
                print(f"{severity}: {message}")
    """
    
    # Configuration
    MAX_PROMPT_LENGTH = 100000
    MAX_ESTIMATED_TOKENS = 25000
    WARN_PROMPT_LENGTH = 50000
    
    # Patterns that may indicate injection attempts
    INJECTION_PATTERNS = [
        (r"ignore\s+(all\s+)?(previous|above|prior)\s+(instructions|context|prompts?)", 
         "Potential instruction override attempt"),
        (r"disregard\s+(everything|all|the above)", 
         "Potential context manipulation"),
        (r"new\s+(system\s+)?instructions?:", 
         "Potential instruction injection"),
        (r"system:\s*", 
         "Potential system prompt injection"),
        (r"\[INST\]|\[/INST\]", 
         "Llama-style instruction markers detected"),
        (r"<<SYS>>|<</SYS>>", 
         "Llama system markers detected"),
        (r"human:|assistant:|system:", 
         "Role markers detected"),
        (r"<\|im_start\|>|<\|im_end\|>", 
         "ChatML markers detected"),
    ]
    
    # Suspicious but not necessarily malicious
    SUSPICIOUS_PATTERNS = [
        (r"pretend\s+(you\s+are|to\s+be)", "Role-play instruction"),
        (r"act\s+as\s+(if|a)", "Acting instruction"),
        (r"forget\s+(everything|what)", "Memory manipulation attempt"),
    ]
    
    def __init__(
        self,
        max_length: int = None,
        max_tokens: int = None,
        block_injections: bool = True
    ):
        self.max_length = max_length or self.MAX_PROMPT_LENGTH
        self.max_tokens = max_tokens or self.MAX_ESTIMATED_TOKENS
        self.block_injections = block_injections
    
    def validate(self, prompt: str) -> ValidationResult:
        """
        Validate a user prompt.
        
        Args:
            prompt: The prompt to validate
            
        Returns:
            ValidationResult with sanitized prompt and any findings
        """
        findings: List[Tuple[ValidationSeverity, str]] = []
        is_valid = True
        
        # Empty check
        if not prompt or not prompt.strip():
            return ValidationResult(
                is_valid=False,
                sanitized_value="",
                findings=[(ValidationSeverity.ERROR, "Prompt cannot be empty")]
            )
        
        # Length check
        if len(prompt) > self.max_length:
            return ValidationResult(
                is_valid=False,
                sanitized_value=prompt[:self.max_length],
                findings=[(
                    ValidationSeverity.ERROR,
                    f"Prompt exceeds maximum length of {self.max_length:,} characters"
                )]
            )
        
        if len(prompt) > self.WARN_PROMPT_LENGTH:
            findings.append((
                ValidationSeverity.WARNING,
                f"Large prompt ({len(prompt):,} chars) may be expensive"
            ))
        
        # Token estimation
        estimated_tokens = len(prompt) // 4
        if estimated_tokens > self.max_tokens:
            findings.append((
                ValidationSeverity.WARNING,
                f"Estimated {estimated_tokens:,} tokens exceeds recommended max of {self.max_tokens:,}"
            ))
        
        # Injection pattern check
        prompt_lower = prompt.lower()
        
        for pattern, description in self.INJECTION_PATTERNS:
            if re.search(pattern, prompt_lower, re.IGNORECASE):
                if self.block_injections:
                    findings.append((
                        ValidationSeverity.CRITICAL,
                        f"Blocked: {description}"
                    ))
                    is_valid = False
                else:
                    findings.append((
                        ValidationSeverity.WARNING,
                        f"Detected: {description}"
                    ))
        
        # Suspicious pattern check (warnings only)
        for pattern, description in self.SUSPICIOUS_PATTERNS:
            if re.search(pattern, prompt_lower, re.IGNORECASE):
                findings.append((
                    ValidationSeverity.INFO,
                    f"Note: {description}"
                ))
        
        # Sanitize
        sanitized = prompt.strip()
        
        return ValidationResult(
            is_valid=is_valid,
            sanitized_value=sanitized,
            findings=findings
        )
    
    def estimate_cost(
        self,
        prompt: str,
        model: str,
        expected_response_tokens: int = 1000
    ) -> Dict[str, float]:
        """
        Estimate API cost for a prompt.
        
        Returns:
            Dict with 'input_cost', 'output_cost', 'total_cost'
        """
        # Approximate costs per 1M tokens (as of 2024)
        COSTS = {
            "claude-3-opus": {"input": 15.0, "output": 75.0},
            "claude-3-sonnet": {"input": 3.0, "output": 15.0},
            "claude-3-haiku": {"input": 0.25, "output": 1.25},
            "gpt-4-turbo": {"input": 10.0, "output": 30.0},
            "gpt-4o": {"input": 5.0, "output": 15.0},
            "gpt-4o-mini": {"input": 0.15, "output": 0.60},
            "gpt-3.5-turbo": {"input": 0.50, "output": 1.50},
        }
        
        # Find matching cost tier
        costs = None
        for model_prefix, model_costs in COSTS.items():
            if model_prefix in model.lower():
                costs = model_costs
                break
        
        if costs is None:
            costs = {"input": 10.0, "output": 30.0}  # Default to GPT-4 rates
        
        input_tokens = len(prompt) // 4
        
        input_cost = (input_tokens / 1_000_000) * costs["input"]
        output_cost = (expected_response_tokens / 1_000_000) * costs["output"]
        
        return {
            "input_tokens": input_tokens,
            "expected_output_tokens": expected_response_tokens,
            "input_cost": round(input_cost, 6),
            "output_cost": round(output_cost, 6),
            "total_cost": round(input_cost + output_cost, 6)
        }


class PathValidator:
    """
    Validate file paths for security.
    
    Example:
        validator = PathValidator(base_dir=Path.home() / "documents")
        result = validator.validate("../../../etc/passwd")
        # result.is_valid == False
    """
    
    ALLOWED_EXTENSIONS = {
        '.txt', '.md', '.json', '.yaml', '.yml',
        '.py', '.js', '.ts', '.jsx', '.tsx',
        '.html', '.css', '.xml', '.csv',
        '.log', '.cfg', '.ini', '.toml'
    }
    
    BLOCKED_PATHS = {
        '/etc/passwd', '/etc/shadow', '/etc/hosts',
        'C:\\Windows\\System32', 'C:\\Windows\\system.ini'
    }
    
    MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
    
    def __init__(
        self,
        base_dir: Path = None,
        allowed_extensions: set = None,
        max_file_size: int = None
    ):
        self.base_dir = base_dir
        self.allowed_extensions = allowed_extensions or self.ALLOWED_EXTENSIONS
        self.max_file_size = max_file_size or self.MAX_FILE_SIZE
    
    def validate(self, path_str: str) -> ValidationResult:
        """
        Validate a file path.
        
        Args:
            path_str: Path string to validate
            
        Returns:
            ValidationResult with resolved Path and findings
        """
        findings: List[Tuple[ValidationSeverity, str]] = []
        
        try:
            path = Path(path_str).expanduser().resolve()
        except Exception as e:
            return ValidationResult(
                is_valid=False,
                sanitized_value=None,
                findings=[(ValidationSeverity.ERROR, f"Invalid path: {e}")]
            )
        
        # Check for traversal attempts in original string
        if '..' in path_str:
            return ValidationResult(
                is_valid=False,
                sanitized_value=path,
                findings=[(
                    ValidationSeverity.CRITICAL,
                    "Path traversal attempt detected (..)"
                )]
            )
        
        # Check against blocked paths
        path_str_normalized = str(path).lower()
        for blocked in self.BLOCKED_PATHS:
            if blocked.lower() in path_str_normalized:
                return ValidationResult(
                    is_valid=False,
                    sanitized_value=path,
                    findings=[(
                        ValidationSeverity.CRITICAL,
                        f"Access to system path blocked"
                    )]
                )
        
        # Check base directory constraint
        if self.base_dir:
            try:
                path.relative_to(self.base_dir.resolve())
            except ValueError:
                return ValidationResult(
                    is_valid=False,
                    sanitized_value=path,
                    findings=[(
                        ValidationSeverity.ERROR,
                        f"Path must be within {self.base_dir}"
                    )]
                )
        
        # Check extension if file exists or for write operations
        if path.suffix and path.suffix.lower() not in self.allowed_extensions:
            findings.append((
                ValidationSeverity.WARNING,
                f"File extension '{path.suffix}' is not in allowed list"
            ))
        
        # Check file size if exists
        if path.exists() and path.is_file():
            size = path.stat().st_size
            if size > self.max_file_size:
                return ValidationResult(
                    is_valid=False,
                    sanitized_value=path,
                    findings=[(
                        ValidationSeverity.ERROR,
                        f"File size ({size:,} bytes) exceeds limit ({self.max_file_size:,} bytes)"
                    )]
                )
        
        return ValidationResult(
            is_valid=True,
            sanitized_value=path,
            findings=findings
        )
    
    def safe_read(self, path_str: str) -> Tuple[Optional[str], ValidationResult]:
        """
        Safely read a file after validation.
        
        Returns:
            Tuple of (content, validation_result)
        """
        result = self.validate(path_str)
        
        if not result.is_valid:
            return None, result
        
        path = result.sanitized_value
        
        if not path.exists():
            result.findings.append((
                ValidationSeverity.ERROR,
                f"File not found: {path}"
            ))
            result.is_valid = False
            return None, result
        
        try:
            content = path.read_text(encoding='utf-8')
            return content, result
        except UnicodeDecodeError:
            result.findings.append((
                ValidationSeverity.ERROR,
                "File is not valid UTF-8 text"
            ))
            result.is_valid = False
            return None, result
        except Exception as e:
            result.findings.append((
                ValidationSeverity.ERROR,
                f"Failed to read file: {e}"
            ))
            result.is_valid = False
            return None, result


class ConfigValidator:
    """Validate configuration values"""
    
    @staticmethod
    def validate_int(
        value: Any,
        min_val: int = None,
        max_val: int = None,
        name: str = "value"
    ) -> ValidationResult:
        """Validate an integer value"""
        findings = []
        
        try:
            int_val = int(value)
        except (ValueError, TypeError):
            return ValidationResult(
                is_valid=False,
                sanitized_value=None,
                findings=[(ValidationSeverity.ERROR, f"{name} must be an integer")]
            )
        
        if min_val is not None and int_val < min_val:
            return ValidationResult(
                is_valid=False,
                sanitized_value=int_val,
                findings=[(ValidationSeverity.ERROR, f"{name} must be >= {min_val}")]
            )
        
        if max_val is not None and int_val > max_val:
            return ValidationResult(
                is_valid=False,
                sanitized_value=int_val,
                findings=[(ValidationSeverity.ERROR, f"{name} must be <= {max_val}")]
            )
        
        return ValidationResult(
            is_valid=True,
            sanitized_value=int_val,
            findings=findings
        )
    
    @staticmethod
    def validate_string(
        value: Any,
        min_length: int = 0,
        max_length: int = 1000,
        pattern: str = None,
        name: str = "value"
    ) -> ValidationResult:
        """Validate a string value"""
        if not isinstance(value, str):
            return ValidationResult(
                is_valid=False,
                sanitized_value=str(value) if value else "",
                findings=[(ValidationSeverity.ERROR, f"{name} must be a string")]
            )
        
        if len(value) < min_length:
            return ValidationResult(
                is_valid=False,
                sanitized_value=value,
                findings=[(ValidationSeverity.ERROR, f"{name} must be at least {min_length} characters")]
            )
        
        if len(value) > max_length:
            return ValidationResult(
                is_valid=False,
                sanitized_value=value[:max_length],
                findings=[(ValidationSeverity.ERROR, f"{name} must be at most {max_length} characters")]
            )
        
        if pattern and not re.match(pattern, value):
            return ValidationResult(
                is_valid=False,
                sanitized_value=value,
                findings=[(ValidationSeverity.ERROR, f"{name} does not match required pattern")]
            )
        
        return ValidationResult(
            is_valid=True,
            sanitized_value=value.strip(),
            findings=[]
        )


# Convenience functions
def validate_prompt(prompt: str, **kwargs) -> ValidationResult:
    """Validate a user prompt"""
    return PromptValidator(**kwargs).validate(prompt)


def validate_path(path: str, **kwargs) -> ValidationResult:
    """Validate a file path"""
    return PathValidator(**kwargs).validate(path)


def safe_read_file(path: str, **kwargs) -> Tuple[Optional[str], ValidationResult]:
    """Safely read a file"""
    return PathValidator(**kwargs).safe_read(path)
```

---

## P1.4 Safe File Operations

**File**: `src/startd8/safe_file_ops.py`  
**Effort**: 6 hours

### Implementation

```python
# src/startd8/safe_file_ops.py
"""
Safe File Operations with validation and atomic writes.
"""

import os
import tempfile
import shutil
import logging
from pathlib import Path
from typing import Optional, Union
from contextlib import contextmanager

from .validators import PathValidator, ValidationResult

logger = logging.getLogger(__name__)


class SafeFileOps:
    """
    Safe file operations with:
    - Path validation
    - Atomic writes
    - Backup creation
    - Permission management
    """
    
    def __init__(
        self,
        base_dir: Path = None,
        create_backups: bool = True,
        validate_paths: bool = True
    ):
        self.base_dir = base_dir
        self.create_backups = create_backups
        self.validator = PathValidator(base_dir=base_dir) if validate_paths else None
    
    def read(self, path: Union[str, Path]) -> Optional[str]:
        """
        Safely read a file.
        
        Args:
            path: File path to read
            
        Returns:
            File content or None if validation fails
            
        Raises:
            FileNotFoundError: If file doesn't exist
            PermissionError: If read permission denied
        """
        if self.validator:
            content, result = self.validator.safe_read(str(path))
            if not result.is_valid:
                for severity, msg in result.findings:
                    logger.error(f"{severity.value}: {msg}")
                return None
            return content
        
        return Path(path).read_text(encoding='utf-8')
    
    def write(
        self,
        path: Union[str, Path],
        content: str,
        atomic: bool = True,
        backup: bool = None
    ) -> bool:
        """
        Safely write to a file.
        
        Args:
            path: File path to write
            content: Content to write
            atomic: Use atomic write (temp file + rename)
            backup: Create backup of existing file
            
        Returns:
            True if successful
        """
        path = Path(path)
        backup = backup if backup is not None else self.create_backups
        
        # Validate path
        if self.validator:
            result = self.validator.validate(str(path))
            if not result.is_valid:
                for severity, msg in result.findings:
                    logger.error(f"{severity.value}: {msg}")
                return False
        
        # Create backup if file exists
        if backup and path.exists():
            backup_path = path.with_suffix(path.suffix + '.bak')
            try:
                shutil.copy2(path, backup_path)
                logger.debug(f"Created backup: {backup_path}")
            except Exception as e:
                logger.warning(f"Failed to create backup: {e}")
        
        # Ensure parent directory exists
        path.parent.mkdir(parents=True, exist_ok=True)
        
        if atomic:
            return self._atomic_write(path, content)
        else:
            return self._direct_write(path, content)
    
    def _atomic_write(self, path: Path, content: str) -> bool:
        """Write using temp file + rename for atomicity"""
        try:
            # Write to temp file in same directory (for same filesystem)
            fd, temp_path = tempfile.mkstemp(
                dir=path.parent,
                prefix=f".{path.name}.",
                suffix=".tmp"
            )
            
            try:
                with os.fdopen(fd, 'w', encoding='utf-8') as f:
                    f.write(content)
                
                # Set permissions before rename
                self._set_permissions(Path(temp_path))
                
                # Atomic rename
                os.replace(temp_path, path)
                logger.debug(f"Atomically wrote: {path}")
                return True
                
            except Exception:
                # Clean up temp file on error
                try:
                    os.unlink(temp_path)
                except OSError:
                    pass
                raise
                
        except Exception as e:
            logger.error(f"Atomic write failed: {e}")
            return False
    
    def _direct_write(self, path: Path, content: str) -> bool:
        """Direct write (not atomic)"""
        try:
            path.write_text(content, encoding='utf-8')
            self._set_permissions(path)
            return True
        except Exception as e:
            logger.error(f"Write failed: {e}")
            return False
    
    def _set_permissions(self, path: Path):
        """Set restrictive file permissions"""
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass  # Windows or permission error
    
    def delete(self, path: Union[str, Path], backup: bool = None) -> bool:
        """
        Safely delete a file.
        
        Args:
            path: File path to delete
            backup: Create backup before deletion
            
        Returns:
            True if successful or file didn't exist
        """
        path = Path(path)
        backup = backup if backup is not None else self.create_backups
        
        if not path.exists():
            return True
        
        # Validate path
        if self.validator:
            result = self.validator.validate(str(path))
            if not result.is_valid:
                return False
        
        # Create backup
        if backup:
            backup_path = path.with_suffix(path.suffix + '.deleted')
            try:
                shutil.copy2(path, backup_path)
            except Exception as e:
                logger.warning(f"Failed to create backup before delete: {e}")
        
        try:
            path.unlink()
            return True
        except Exception as e:
            logger.error(f"Delete failed: {e}")
            return False
    
    @contextmanager
    def safe_update(self, path: Union[str, Path]):
        """
        Context manager for safe file updates.
        
        Usage:
            with safe_ops.safe_update("config.json") as (content, writer):
                data = json.loads(content)
                data["key"] = "value"
                writer(json.dumps(data))
        """
        path = Path(path)
        content = self.read(path) or ""
        
        new_content = [None]  # Use list to allow modification in closure
        
        def writer(c: str):
            new_content[0] = c
        
        yield content, writer
        
        if new_content[0] is not None:
            self.write(path, new_content[0])


# Global instance
_safe_ops: Optional[SafeFileOps] = None


def get_safe_file_ops(base_dir: Path = None) -> SafeFileOps:
    """Get or create global SafeFileOps instance"""
    global _safe_ops
    if _safe_ops is None:
        _safe_ops = SafeFileOps(base_dir=base_dir)
    return _safe_ops
```

---

## P1.5 Async Retry Handler

**File**: `src/startd8/retry_handler.py`  
**Effort**: 8 hours

### Implementation

```python
# src/startd8/retry_handler.py
"""
Async Retry Handler with exponential backoff.
"""

import asyncio
import logging
import random
from dataclasses import dataclass, field
from typing import TypeVar, Callable, Awaitable, Tuple, Type, Optional, List
from functools import wraps

logger = logging.getLogger(__name__)

T = TypeVar('T')


@dataclass
class RetryConfig:
    """Configuration for retry behavior"""
    max_retries: int = 3
    base_delay: float = 1.0
    max_delay: float = 60.0
    exponential_base: float = 2.0
    jitter: bool = True
    jitter_factor: float = 0.1
    
    # Exceptions to retry on
    retryable_exceptions: Tuple[Type[Exception], ...] = field(
        default_factory=lambda: (
            asyncio.TimeoutError,
            ConnectionError,
            OSError,
        )
    )
    
    # HTTP status codes to retry on
    retryable_status_codes: Tuple[int, ...] = (429, 500, 502, 503, 504)


class RetryError(Exception):
    """Raised when all retries are exhausted"""
    
    def __init__(self, message: str, last_exception: Exception = None, attempts: int = 0):
        super().__init__(message)
        self.last_exception = last_exception
        self.attempts = attempts


async def retry_async(
    func: Callable[[], Awaitable[T]],
    config: RetryConfig = None,
    on_retry: Callable[[int, Exception, float], None] = None
) -> T:
    """
    Retry an async function with exponential backoff.
    
    Args:
        func: Async function to retry
        config: Retry configuration
        on_retry: Callback called before each retry (attempt, exception, delay)
        
    Returns:
        Result from func
        
    Raises:
        RetryError: If all retries exhausted
    """
    config = config or RetryConfig()
    last_exception = None
    
    for attempt in range(config.max_retries + 1):
        try:
            return await func()
            
        except config.retryable_exceptions as e:
            last_exception = e
            
            if attempt >= config.max_retries:
                logger.error(f"All {config.max_retries} retries exhausted")
                raise RetryError(
                    f"Failed after {attempt + 1} attempts: {e}",
                    last_exception=e,
                    attempts=attempt + 1
                )
            
            # Calculate delay with exponential backoff
            delay = min(
                config.base_delay * (config.exponential_base ** attempt),
                config.max_delay
            )
            
            # Add jitter
            if config.jitter:
                jitter = delay * config.jitter_factor * random.random()
                delay += jitter
            
            logger.warning(
                f"Attempt {attempt + 1}/{config.max_retries + 1} failed: {e}. "
                f"Retrying in {delay:.2f}s"
            )
            
            if on_retry:
                on_retry(attempt + 1, e, delay)
            
            await asyncio.sleep(delay)
            
        except Exception as e:
            # Non-retryable exception
            logger.error(f"Non-retryable error: {e}")
            raise
    
    # Should not reach here
    raise RetryError(
        "Unexpected retry loop exit",
        last_exception=last_exception,
        attempts=config.max_retries + 1
    )


def with_retry(config: RetryConfig = None):
    """
    Decorator for retry logic.
    
    Usage:
        @with_retry(RetryConfig(max_retries=5))
        async def call_api():
            ...
    """
    def decorator(func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            return await retry_async(
                lambda: func(*args, **kwargs),
                config=config
            )
        return wrapper
    return decorator


class RetryContext:
    """
    Context manager for retry operations with state tracking.
    
    Usage:
        async with RetryContext(config) as ctx:
            while ctx.should_retry():
                try:
                    result = await make_request()
                    ctx.record_success()
                    break
                except Exception as e:
                    await ctx.record_failure(e)
    """
    
    def __init__(self, config: RetryConfig = None):
        self.config = config or RetryConfig()
        self.attempt = 0
        self.last_exception: Optional[Exception] = None
        self._success = False
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass
    
    def should_retry(self) -> bool:
        """Check if another retry should be attempted"""
        if self._success:
            return False
        return self.attempt <= self.config.max_retries
    
    def record_success(self):
        """Record successful operation"""
        self._success = True
    
    async def record_failure(self, exception: Exception):
        """Record failed operation and wait before retry"""
        self.last_exception = exception
        self.attempt += 1
        
        if self.attempt <= self.config.max_retries:
            if isinstance(exception, self.config.retryable_exceptions):
                delay = min(
                    self.config.base_delay * (self.config.exponential_base ** (self.attempt - 1)),
                    self.config.max_delay
                )
                
                if self.config.jitter:
                    delay += delay * self.config.jitter_factor * random.random()
                
                logger.warning(f"Retry {self.attempt}/{self.config.max_retries}: {exception}")
                await asyncio.sleep(delay)
            else:
                # Non-retryable, don't wait
                raise exception
        else:
            raise RetryError(
                f"All retries exhausted",
                last_exception=exception,
                attempts=self.attempt
            )


# Provider-specific configurations
PROVIDER_RETRY_CONFIGS = {
    "anthropic": RetryConfig(
        max_retries=3,
        base_delay=1.0,
        retryable_exceptions=(
            asyncio.TimeoutError,
            ConnectionError,
        )
    ),
    "openai": RetryConfig(
        max_retries=3,
        base_delay=1.0,
        retryable_exceptions=(
            asyncio.TimeoutError,
            ConnectionError,
        )
    ),
}


def get_retry_config(provider: str) -> RetryConfig:
    """Get retry configuration for a provider"""
    return PROVIDER_RETRY_CONFIGS.get(provider, RetryConfig())
```

---

## P1.6 Graceful Shutdown Manager

**File**: `src/startd8/shutdown_manager.py`  
**Effort**: 6 hours

### Implementation

```python
# src/startd8/shutdown_manager.py
"""
Graceful Shutdown Manager for clean application termination.
"""

import asyncio
import atexit
import logging
import signal
import sys
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Callable, List, Set, Optional
from enum import Enum

logger = logging.getLogger(__name__)


class ShutdownPhase(Enum):
    """Shutdown phases in order of execution"""
    STOP_ACCEPTING = 1    # Stop accepting new work
    DRAIN_ACTIVE = 2      # Wait for active operations
    CLEANUP = 3           # Run cleanup handlers
    FINAL = 4             # Final cleanup


@dataclass
class ActiveOperation:
    """Represents an active operation being tracked"""
    id: str
    name: str
    started_at: float
    timeout: float = 30.0


class ShutdownManager:
    """
    Manages graceful application shutdown.
    
    Features:
    - Signal handling (SIGINT, SIGTERM)
    - Active operation tracking
    - Ordered cleanup handlers
    - Timeout enforcement
    
    Example:
        shutdown = ShutdownManager()
        shutdown.register_cleanup(save_state)
        shutdown.install_handlers()
        
        with shutdown.track_operation("api_call"):
            result = await make_api_call()
    """
    
    def __init__(
        self,
        drain_timeout: float = 30.0,
        cleanup_timeout: float = 10.0
    ):
        self.drain_timeout = drain_timeout
        self.cleanup_timeout = cleanup_timeout
        
        self._shutdown_requested = False
        self._shutdown_complete = False
        self._current_phase = None
        
        self._active_operations: Set[str] = set()
        self._operation_details: dict = {}
        self._cleanup_handlers: List[Callable] = []
        
        self._lock = threading.RLock()
        self._shutdown_event = threading.Event()
    
    def install_handlers(self):
        """Install signal handlers for graceful shutdown"""
        # Handle SIGINT (Ctrl+C) and SIGTERM
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
        # Register atexit handler as fallback
        atexit.register(self._atexit_handler)
        
        logger.info("Shutdown handlers installed")
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        sig_name = signal.Signals(signum).name
        logger.info(f"Received {sig_name}, initiating graceful shutdown...")
        
        if self._shutdown_requested:
            # Second signal - force exit
            logger.warning("Forced exit requested")
            sys.exit(1)
        
        self._shutdown_requested = True
        self._shutdown_event.set()
        
        # Start shutdown in background thread to not block signal handler
        threading.Thread(target=self._run_shutdown, daemon=True).start()
    
    def _atexit_handler(self):
        """Handle shutdown at exit"""
        if not self._shutdown_complete:
            self._run_shutdown()
    
    def _run_shutdown(self):
        """Execute shutdown sequence"""
        if self._shutdown_complete:
            return
        
        try:
            # Phase 1: Stop accepting new work
            self._current_phase = ShutdownPhase.STOP_ACCEPTING
            logger.info("Shutdown Phase 1: Stop accepting new work")
            
            # Phase 2: Drain active operations
            self._current_phase = ShutdownPhase.DRAIN_ACTIVE
            logger.info(f"Shutdown Phase 2: Draining {len(self._active_operations)} active operations")
            
            start = time.time()
            while self._active_operations and time.time() - start < self.drain_timeout:
                remaining = list(self._active_operations)[:5]
                logger.info(f"Waiting for operations: {remaining}")
                time.sleep(0.5)
            
            if self._active_operations:
                logger.warning(f"Timeout waiting for {len(self._active_operations)} operations")
            
            # Phase 3: Run cleanup handlers
            self._current_phase = ShutdownPhase.CLEANUP
            logger.info(f"Shutdown Phase 3: Running {len(self._cleanup_handlers)} cleanup handlers")
            
            for handler in reversed(self._cleanup_handlers):
                try:
                    start = time.time()
                    handler()
                    elapsed = time.time() - start
                    logger.debug(f"Cleanup handler {handler.__name__} completed in {elapsed:.2f}s")
                except Exception as e:
                    logger.error(f"Cleanup handler {handler.__name__} failed: {e}")
            
            # Phase 4: Final
            self._current_phase = ShutdownPhase.FINAL
            logger.info("Shutdown complete")
            
        finally:
            self._shutdown_complete = True
    
    def register_cleanup(self, handler: Callable, name: str = None):
        """
        Register a cleanup handler to run during shutdown.
        
        Handlers are run in reverse order of registration.
        
        Args:
            handler: Callable to run during cleanup
            name: Optional name for logging
        """
        if name:
            handler.__name__ = name
        
        with self._lock:
            self._cleanup_handlers.append(handler)
            logger.debug(f"Registered cleanup handler: {handler.__name__}")
    
    def unregister_cleanup(self, handler: Callable):
        """Remove a cleanup handler"""
        with self._lock:
            try:
                self._cleanup_handlers.remove(handler)
            except ValueError:
                pass
    
    @contextmanager
    def track_operation(self, operation_id: str, name: str = None, timeout: float = 30.0):
        """
        Context manager to track an active operation.
        
        Args:
            operation_id: Unique identifier for operation
            name: Human-readable name
            timeout: Maximum time for operation
            
        Usage:
            with shutdown.track_operation("api-call-123"):
                result = await api.call()
        """
        if self._shutdown_requested:
            raise ShutdownInProgressError("Cannot start new operation during shutdown")
        
        with self._lock:
            self._active_operations.add(operation_id)
            self._operation_details[operation_id] = ActiveOperation(
                id=operation_id,
                name=name or operation_id,
                started_at=time.time(),
                timeout=timeout
            )
        
        try:
            yield
        finally:
            with self._lock:
                self._active_operations.discard(operation_id)
                self._operation_details.pop(operation_id, None)
    
    @property
    def shutdown_requested(self) -> bool:
        """Check if shutdown has been requested"""
        return self._shutdown_requested
    
    @property
    def should_stop(self) -> bool:
        """Check if operations should stop (alias for shutdown_requested)"""
        return self._shutdown_requested
    
    def wait_for_shutdown(self, timeout: float = None) -> bool:
        """
        Block until shutdown is requested.
        
        Returns:
            True if shutdown was requested, False if timeout elapsed
        """
        return self._shutdown_event.wait(timeout)
    
    def request_shutdown(self):
        """Programmatically request shutdown"""
        self._shutdown_requested = True
        self._shutdown_event.set()
        self._run_shutdown()
    
    def get_active_operations(self) -> List[ActiveOperation]:
        """Get list of active operations"""
        with self._lock:
            return list(self._operation_details.values())
    
    def cancel_operation(self, operation_id: str):
        """Mark an operation as cancelled (removes from tracking)"""
        with self._lock:
            self._active_operations.discard(operation_id)
            self._operation_details.pop(operation_id, None)


class ShutdownInProgressError(Exception):
    """Raised when trying to start work during shutdown"""
    pass


# Async support
class AsyncShutdownManager(ShutdownManager):
    """Async-compatible shutdown manager"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._async_event: Optional[asyncio.Event] = None
    
    async def async_wait_for_shutdown(self, timeout: float = None) -> bool:
        """Async wait for shutdown"""
        if self._async_event is None:
            self._async_event = asyncio.Event()
        
        if self._shutdown_requested:
            return True
        
        try:
            await asyncio.wait_for(self._async_event.wait(), timeout)
            return True
        except asyncio.TimeoutError:
            return False
    
    def _signal_handler(self, signum, frame):
        """Override to also set async event"""
        super()._signal_handler(signum, frame)
        
        if self._async_event:
            # Need to set from the event loop thread
            try:
                loop = asyncio.get_running_loop()
                loop.call_soon_threadsafe(self._async_event.set)
            except RuntimeError:
                pass


# Global instance
_shutdown_manager: Optional[ShutdownManager] = None


def get_shutdown_manager() -> ShutdownManager:
    """Get or create global shutdown manager"""
    global _shutdown_manager
    if _shutdown_manager is None:
        _shutdown_manager = AsyncShutdownManager()
    return _shutdown_manager


def install_shutdown_handlers():
    """Install shutdown handlers on global manager"""
    get_shutdown_manager().install_handlers()
```

---

## Integration Checklist

### Files to Modify

- [ ] `tui_improved.py`
  - Replace `APIKeyManager` with `SecureKeyManager`
  - Add shutdown manager initialization
  - Wrap API calls with retry handler
  - Add input validation for prompts
  
- [ ] `agents.py`
  - Integrate rate limiter
  - Add retry logic to `agenerate()`
  - Add circuit breaker checks

- [ ] `config.py`
  - Migrate to use `SecureKeyManager`
  - Add validation for config values

### Testing Requirements

- [ ] Unit tests for all new modules (>80% coverage)
- [ ] Integration tests for key flows
- [ ] Security tests for injection attempts
- [ ] Performance tests for rate limiting

### Documentation Updates

- [ ] Update README with security features
- [ ] Add migration guide
- [ ] Document configuration options
- [ ] Add troubleshooting guide

---

## Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| API keys encrypted | 100% | Audit storage files |
| Rate limit enforcement | <1% bypass | Load testing |
| Injection detection | >95% | Security testing |
| Clean shutdown | 100% | Integration tests |
| Code coverage | >80% | pytest-cov |

---

**Next**: See `PHASE2_DETAILED_DESIGN.md` for High Priority Hardening
