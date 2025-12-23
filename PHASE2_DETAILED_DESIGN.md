# Phase 2: High Priority Hardening - Detailed Design

**Phase Duration**: 2 Weeks (Weeks 3-4)  
**Total Effort**: 45 hours  
**Priority**: 🟠 HIGH  
**Prerequisites**: Phase 1 Complete

---

## Table of Contents
1. [P2.1 Log Sanitization Filter](#p21-log-sanitization-filter)
2. [P2.2 Request Timeout Configuration](#p22-request-timeout-configuration)
3. [P2.3 Audit Logger](#p23-audit-logger)
4. [P2.4 Connection Pool Manager](#p24-connection-pool-manager)
5. [P2.5 Bounded LRU Cache](#p25-bounded-lru-cache)
6. [P2.6 Async File Operations](#p26-async-file-operations)
7. [P2.7 Cross-platform Permissions](#p27-cross-platform-permissions)
8. [P2.8 Agent Integration Updates](#p28-agent-integration-updates)

---

## P2.1 Log Sanitization Filter

**File**: `src/startd8/log_filter.py`  
**Effort**: 4 hours

### Purpose
Prevent sensitive data (API keys, passwords, PII) from appearing in logs.

### Implementation

```python
# src/startd8/log_filter.py
"""
Log Sanitization Filter for sensitive data protection.

Automatically redacts:
- API keys (various formats)
- Passwords and secrets
- Email addresses (optional)
- Credit card numbers (optional)
"""

import logging
import re
from typing import List, Tuple, Pattern
from dataclasses import dataclass


@dataclass
class SanitizationRule:
    """Rule for sanitizing sensitive data"""
    name: str
    pattern: Pattern
    replacement: str
    enabled: bool = True


class SensitiveDataFilter(logging.Filter):
    """
    Logging filter that redacts sensitive information.
    
    Example:
        import logging
        from startd8.log_filter import SensitiveDataFilter
        
        # Apply to root logger
        logging.getLogger().addFilter(SensitiveDataFilter())
        
        # Now all logs are sanitized
        logging.info(f"Using key: {api_key}")  # Key will be redacted
    """
    
    # Default sanitization rules
    DEFAULT_RULES: List[SanitizationRule] = [
        # API Keys
        SanitizationRule(
            name="anthropic_key",
            pattern=re.compile(r'sk-ant-[a-zA-Z0-9-]{20,}'),
            replacement='[REDACTED_ANTHROPIC_KEY]'
        ),
        SanitizationRule(
            name="openai_key",
            pattern=re.compile(r'sk-(?:proj-)?[a-zA-Z0-9]{20,}'),
            replacement='[REDACTED_OPENAI_KEY]'
        ),
        SanitizationRule(
            name="generic_api_key",
            pattern=re.compile(r'(?i)api[_-]?key["\s:=]+["\']?([a-zA-Z0-9_-]{20,})["\']?'),
            replacement='api_key=[REDACTED]'
        ),
        SanitizationRule(
            name="bearer_token",
            pattern=re.compile(r'(?i)bearer\s+[a-zA-Z0-9._-]{20,}'),
            replacement='Bearer [REDACTED]'
        ),
        
        # Passwords and Secrets
        SanitizationRule(
            name="password_field",
            pattern=re.compile(r'(?i)password["\s:=]+["\']?[^"\'\s,}]{1,}["\']?'),
            replacement='password=[REDACTED]'
        ),
        SanitizationRule(
            name="secret_field",
            pattern=re.compile(r'(?i)secret["\s:=]+["\']?[^"\'\s,}]{1,}["\']?'),
            replacement='secret=[REDACTED]'
        ),
        SanitizationRule(
            name="token_field",
            pattern=re.compile(r'(?i)(?:access_?|refresh_?)?token["\s:=]+["\']?[^"\'\s,}]{20,}["\']?'),
            replacement='token=[REDACTED]'
        ),
        
        # Credentials in URLs
        SanitizationRule(
            name="url_credentials",
            pattern=re.compile(r'://[^:]+:[^@]+@'),
            replacement='://[REDACTED]@'
        ),
    ]
    
    # Optional rules (disabled by default)
    OPTIONAL_RULES: List[SanitizationRule] = [
        SanitizationRule(
            name="email",
            pattern=re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'),
            replacement='[REDACTED_EMAIL]',
            enabled=False
        ),
        SanitizationRule(
            name="credit_card",
            pattern=re.compile(r'\b(?:\d{4}[- ]?){3}\d{4}\b'),
            replacement='[REDACTED_CC]',
            enabled=False
        ),
        SanitizationRule(
            name="ssn",
            pattern=re.compile(r'\b\d{3}-\d{2}-\d{4}\b'),
            replacement='[REDACTED_SSN]',
            enabled=False
        ),
        SanitizationRule(
            name="phone",
            pattern=re.compile(r'\b(?:\+1[- ]?)?\(?\d{3}\)?[- ]?\d{3}[- ]?\d{4}\b'),
            replacement='[REDACTED_PHONE]',
            enabled=False
        ),
    ]
    
    def __init__(
        self,
        additional_rules: List[SanitizationRule] = None,
        enable_pii_redaction: bool = False
    ):
        """
        Initialize the filter.
        
        Args:
            additional_rules: Extra rules to add
            enable_pii_redaction: Enable email, phone, etc. redaction
        """
        super().__init__()
        
        self.rules = list(self.DEFAULT_RULES)
        
        if enable_pii_redaction:
            self.rules.extend(self.OPTIONAL_RULES)
        
        if additional_rules:
            self.rules.extend(additional_rules)
    
    def filter(self, record: logging.LogRecord) -> bool:
        """
        Filter log record, sanitizing sensitive data.
        
        Always returns True (doesn't filter out records).
        """
        # Sanitize the message
        if isinstance(record.msg, str):
            record.msg = self._sanitize(record.msg)
        
        # Sanitize args if present
        if record.args:
            if isinstance(record.args, dict):
                record.args = {
                    k: self._sanitize(str(v)) if isinstance(v, str) else v
                    for k, v in record.args.items()
                }
            elif isinstance(record.args, tuple):
                record.args = tuple(
                    self._sanitize(str(arg)) if isinstance(arg, str) else arg
                    for arg in record.args
                )
        
        return True
    
    def _sanitize(self, text: str) -> str:
        """Apply all sanitization rules to text"""
        for rule in self.rules:
            if rule.enabled:
                text = rule.pattern.sub(rule.replacement, text)
        return text
    
    def add_rule(self, rule: SanitizationRule):
        """Add a sanitization rule"""
        self.rules.append(rule)
    
    def enable_rule(self, name: str):
        """Enable a rule by name"""
        for rule in self.rules:
            if rule.name == name:
                rule.enabled = True
                return
    
    def disable_rule(self, name: str):
        """Disable a rule by name"""
        for rule in self.rules:
            if rule.name == name:
                rule.enabled = False
                return


class StructuredLogFormatter(logging.Formatter):
    """
    JSON-structured log formatter with automatic sanitization.
    
    Outputs logs in JSON format suitable for log aggregation systems.
    """
    
    def __init__(self, sanitize: bool = True, include_extras: bool = True):
        super().__init__()
        self.sanitize = sanitize
        self.include_extras = include_extras
        self._sanitizer = SensitiveDataFilter() if sanitize else None
    
    def format(self, record: logging.LogRecord) -> str:
        import json
        from datetime import datetime, timezone
        
        # Base log entry
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        
        # Sanitize message
        if self._sanitizer:
            log_entry["message"] = self._sanitizer._sanitize(log_entry["message"])
        
        # Add exception info
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)
        
        # Add extra fields
        if self.include_extras:
            extras = {
                k: v for k, v in record.__dict__.items()
                if k not in {
                    'name', 'msg', 'args', 'created', 'filename', 'funcName',
                    'levelname', 'levelno', 'lineno', 'module', 'msecs',
                    'pathname', 'process', 'processName', 'relativeCreated',
                    'stack_info', 'exc_info', 'exc_text', 'thread', 'threadName',
                    'message', 'asctime'
                }
            }
            if extras:
                log_entry["extra"] = extras
        
        return json.dumps(log_entry)


def configure_secure_logging(
    level: int = logging.INFO,
    enable_pii_redaction: bool = False,
    json_format: bool = False,
    log_file: str = None
):
    """
    Configure logging with security features.
    
    Args:
        level: Logging level
        enable_pii_redaction: Redact PII in logs
        json_format: Use JSON structured logging
        log_file: Optional file to log to
    """
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    
    # Clear existing handlers
    root_logger.handlers.clear()
    
    # Add sanitization filter
    sanitize_filter = SensitiveDataFilter(enable_pii_redaction=enable_pii_redaction)
    root_logger.addFilter(sanitize_filter)
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    
    if json_format:
        console_handler.setFormatter(StructuredLogFormatter())
    else:
        console_handler.setFormatter(logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        ))
    
    root_logger.addHandler(console_handler)
    
    # File handler
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(level)
        file_handler.setFormatter(StructuredLogFormatter() if json_format else logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        ))
        root_logger.addHandler(file_handler)
    
    logging.info("Secure logging configured")
```

---

## P2.2 Request Timeout Configuration

**File**: `src/startd8/http_config.py`  
**Effort**: 4 hours

### Implementation

```python
# src/startd8/http_config.py
"""
HTTP Configuration for API clients.

Provides standardized timeout and connection settings.
"""

import httpx
from dataclasses import dataclass
from typing import Optional, Dict, Any


@dataclass
class TimeoutConfig:
    """HTTP timeout configuration"""
    connect: float = 10.0      # Connection timeout
    read: float = 120.0        # Read timeout (LLM responses can be slow)
    write: float = 30.0        # Write timeout
    pool: float = 10.0         # Connection pool timeout
    
    def to_httpx(self) -> httpx.Timeout:
        """Convert to httpx Timeout object"""
        return httpx.Timeout(
            connect=self.connect,
            read=self.read,
            write=self.write,
            pool=self.pool
        )


@dataclass
class ConnectionLimits:
    """Connection pool limits"""
    max_connections: int = 100
    max_keepalive_connections: int = 20
    keepalive_expiry: float = 30.0
    
    def to_httpx(self) -> httpx.Limits:
        """Convert to httpx Limits object"""
        return httpx.Limits(
            max_connections=self.max_connections,
            max_keepalive_connections=self.max_keepalive_connections,
            keepalive_expiry=self.keepalive_expiry
        )


@dataclass
class HTTPConfig:
    """Complete HTTP client configuration"""
    timeout: TimeoutConfig = None
    limits: ConnectionLimits = None
    verify_ssl: bool = True
    http2: bool = True
    follow_redirects: bool = True
    max_redirects: int = 10
    
    # Retry settings (used with retry_handler)
    retries: int = 3
    retry_statuses: tuple = (429, 500, 502, 503, 504)
    
    def __post_init__(self):
        if self.timeout is None:
            self.timeout = TimeoutConfig()
        if self.limits is None:
            self.limits = ConnectionLimits()
    
    def to_client_kwargs(self) -> Dict[str, Any]:
        """Get kwargs for httpx client initialization"""
        return {
            "timeout": self.timeout.to_httpx(),
            "limits": self.limits.to_httpx(),
            "verify": self.verify_ssl,
            "http2": self.http2,
            "follow_redirects": self.follow_redirects,
            "max_redirects": self.max_redirects,
        }


# Provider-specific configurations
PROVIDER_CONFIGS: Dict[str, HTTPConfig] = {
    "anthropic": HTTPConfig(
        timeout=TimeoutConfig(read=180.0),  # Claude can be slow
        limits=ConnectionLimits(max_connections=50),
    ),
    "openai": HTTPConfig(
        timeout=TimeoutConfig(read=120.0),
        limits=ConnectionLimits(max_connections=50),
    ),
    "default": HTTPConfig(),
}


def get_http_config(provider: str) -> HTTPConfig:
    """Get HTTP configuration for a provider"""
    return PROVIDER_CONFIGS.get(provider, PROVIDER_CONFIGS["default"])


def create_async_client(provider: str = "default", **kwargs) -> httpx.AsyncClient:
    """
    Create configured async HTTP client.
    
    Args:
        provider: Provider name for config lookup
        **kwargs: Additional client arguments
        
    Returns:
        Configured httpx.AsyncClient
    """
    config = get_http_config(provider)
    client_kwargs = config.to_client_kwargs()
    client_kwargs.update(kwargs)
    
    return httpx.AsyncClient(**client_kwargs)


def create_sync_client(provider: str = "default", **kwargs) -> httpx.Client:
    """
    Create configured sync HTTP client.
    
    Args:
        provider: Provider name for config lookup
        **kwargs: Additional client arguments
        
    Returns:
        Configured httpx.Client
    """
    config = get_http_config(provider)
    client_kwargs = config.to_client_kwargs()
    client_kwargs.update(kwargs)
    
    return httpx.Client(**client_kwargs)
```

---

## P2.3 Audit Logger

**File**: `src/startd8/audit_logger.py`  
**Effort**: 8 hours

### Implementation

```python
# src/startd8/audit_logger.py
"""
Audit Logger for security event tracking.

Records security-relevant events for compliance and forensics.
"""

import json
import logging
import os
import threading
import hashlib
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional, Dict, Any, List
from queue import Queue

logger = logging.getLogger(__name__)


class AuditEventType(Enum):
    """Types of audit events"""
    # Authentication & Authorization
    API_KEY_ACCESS = "api_key_access"
    API_KEY_CREATED = "api_key_created"
    API_KEY_DELETED = "api_key_deleted"
    API_KEY_ROTATED = "api_key_rotated"
    
    # Data Access
    FILE_READ = "file_read"
    FILE_WRITE = "file_write"
    FILE_DELETE = "file_delete"
    CONFIG_CHANGE = "config_change"
    
    # API Operations
    AGENT_INVOCATION = "agent_invocation"
    AGENT_ERROR = "agent_error"
    RATE_LIMIT_HIT = "rate_limit_hit"
    CIRCUIT_BREAKER_OPEN = "circuit_breaker_open"
    
    # Security Events
    VALIDATION_FAILURE = "validation_failure"
    INJECTION_ATTEMPT = "injection_attempt"
    PATH_TRAVERSAL_ATTEMPT = "path_traversal_attempt"
    UNAUTHORIZED_ACCESS = "unauthorized_access"
    
    # System Events
    APPLICATION_START = "application_start"
    APPLICATION_STOP = "application_stop"
    SHUTDOWN_INITIATED = "shutdown_initiated"


class AuditSeverity(Enum):
    """Severity levels for audit events"""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class AuditEvent:
    """Represents a single audit event"""
    event_type: AuditEventType
    severity: AuditSeverity
    timestamp: datetime
    user: str
    action: str
    resource: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)
    source_ip: Optional[str] = None
    session_id: Optional[str] = None
    success: bool = True
    error_message: Optional[str] = None
    
    # Computed fields
    event_id: str = field(default="")
    
    def __post_init__(self):
        if not self.event_id:
            # Generate unique event ID
            content = f"{self.timestamp.isoformat()}{self.event_type.value}{self.user}{self.action}"
            self.event_id = hashlib.sha256(content.encode()).hexdigest()[:16]
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            "event_id": self.event_id,
            "event_type": self.event_type.value,
            "severity": self.severity.value,
            "timestamp": self.timestamp.isoformat(),
            "user": self.user,
            "action": self.action,
            "resource": self.resource,
            "details": self.details,
            "source_ip": self.source_ip,
            "session_id": self.session_id,
            "success": self.success,
            "error_message": self.error_message,
        }


class AuditLogger:
    """
    Audit logger for security event tracking.
    
    Features:
    - Async event writing
    - File rotation support
    - Structured JSON output
    - Event queuing for performance
    
    Example:
        audit = AuditLogger()
        audit.log_api_key_access("ANTHROPIC_API_KEY", "read")
        audit.log_agent_invocation(
            "anthropic:claude-3-5-sonnet-20241022",
            prompt_hash="abc123",
            tokens=1500,
        )
    """
    
    def __init__(
        self,
        audit_dir: Path = None,
        max_file_size: int = 10 * 1024 * 1024,  # 10MB
        async_write: bool = True
    ):
        self.audit_dir = audit_dir or Path.home() / ".startd8" / "audit"
        self.audit_dir.mkdir(parents=True, exist_ok=True)
        
        self.max_file_size = max_file_size
        self.async_write = async_write
        
        self._current_file: Optional[Path] = None
        self._lock = threading.RLock()
        
        # Async writing
        if async_write:
            self._queue: Queue = Queue()
            self._writer_thread = threading.Thread(target=self._writer_loop, daemon=True)
            self._writer_thread.start()
        
        self._user = os.getenv("USER", os.getenv("USERNAME", "unknown"))
        self._session_id = hashlib.sha256(
            f"{datetime.now().isoformat()}{os.getpid()}".encode()
        ).hexdigest()[:12]
    
    def _get_audit_file(self) -> Path:
        """Get current audit file, rotating if necessary"""
        with self._lock:
            today = datetime.now().strftime("%Y-%m-%d")
            base_file = self.audit_dir / f"audit-{today}.jsonl"
            
            # Check if rotation needed
            if base_file.exists() and base_file.stat().st_size >= self.max_file_size:
                # Find next available file number
                i = 1
                while True:
                    rotated = self.audit_dir / f"audit-{today}-{i:03d}.jsonl"
                    if not rotated.exists():
                        base_file = rotated
                        break
                    i += 1
            
            return base_file
    
    def _write_event(self, event: AuditEvent):
        """Write event to file"""
        try:
            audit_file = self._get_audit_file()
            
            with open(audit_file, 'a') as f:
                f.write(json.dumps(event.to_dict()) + '\n')
            
            # Set permissions
            try:
                os.chmod(audit_file, 0o600)
            except OSError:
                pass
                
        except Exception as e:
            logger.error(f"Failed to write audit event: {e}")
    
    def _writer_loop(self):
        """Background thread for async writing"""
        while True:
            try:
                event = self._queue.get()
                if event is None:
                    break
                self._write_event(event)
            except Exception as e:
                logger.error(f"Audit writer error: {e}")
    
    def log(
        self,
        event_type: AuditEventType,
        action: str,
        severity: AuditSeverity = AuditSeverity.INFO,
        resource: str = None,
        details: Dict[str, Any] = None,
        success: bool = True,
        error_message: str = None
    ):
        """
        Log an audit event.
        
        Args:
            event_type: Type of event
            action: Action description
            severity: Event severity
            resource: Resource affected
            details: Additional details
            success: Whether action succeeded
            error_message: Error if failed
        """
        event = AuditEvent(
            event_type=event_type,
            severity=severity,
            timestamp=datetime.now(timezone.utc),
            user=self._user,
            action=action,
            resource=resource,
            details=details or {},
            session_id=self._session_id,
            success=success,
            error_message=error_message
        )
        
        if self.async_write:
            self._queue.put(event)
        else:
            self._write_event(event)
    
    # Convenience methods
    
    def log_api_key_access(self, key_name: str, action: str):
        """Log API key access"""
        self.log(
            AuditEventType.API_KEY_ACCESS,
            f"{action} API key",
            resource=key_name
        )
    
    def log_api_key_created(self, key_name: str):
        """Log API key creation"""
        self.log(
            AuditEventType.API_KEY_CREATED,
            "Created API key",
            resource=key_name
        )
    
    def log_api_key_deleted(self, key_name: str):
        """Log API key deletion"""
        self.log(
            AuditEventType.API_KEY_DELETED,
            "Deleted API key",
            resource=key_name,
            severity=AuditSeverity.WARNING
        )
    
    def log_file_access(self, path: str, action: str):
        """Log file access"""
        event_type = {
            "read": AuditEventType.FILE_READ,
            "write": AuditEventType.FILE_WRITE,
            "delete": AuditEventType.FILE_DELETE,
        }.get(action, AuditEventType.FILE_READ)
        
        self.log(event_type, f"{action} file", resource=path)
    
    def log_agent_invocation(
        self,
        agent: str,
        prompt_hash: str,
        tokens: int,
        cost: float = 0.0,
        latency_ms: int = 0
    ):
        """Log agent invocation"""
        self.log(
            AuditEventType.AGENT_INVOCATION,
            f"Invoked {agent}",
            resource=agent,
            details={
                "prompt_hash": prompt_hash,
                "tokens": tokens,
                "cost": cost,
                "latency_ms": latency_ms
            }
        )
    
    def log_agent_error(self, agent: str, error: str):
        """Log agent error"""
        self.log(
            AuditEventType.AGENT_ERROR,
            f"Error from {agent}",
            resource=agent,
            severity=AuditSeverity.ERROR,
            success=False,
            error_message=error
        )
    
    def log_validation_failure(self, validator: str, input_type: str, reason: str):
        """Log validation failure"""
        self.log(
            AuditEventType.VALIDATION_FAILURE,
            f"Validation failed: {reason}",
            resource=validator,
            severity=AuditSeverity.WARNING,
            success=False,
            details={"input_type": input_type, "reason": reason}
        )
    
    def log_security_event(
        self,
        event_type: AuditEventType,
        description: str,
        details: Dict[str, Any] = None
    ):
        """Log security-related event"""
        self.log(
            event_type,
            description,
            severity=AuditSeverity.CRITICAL,
            details=details
        )
    
    def log_injection_attempt(self, input_type: str, pattern: str):
        """Log potential injection attempt"""
        self.log_security_event(
            AuditEventType.INJECTION_ATTEMPT,
            f"Potential injection detected in {input_type}",
            {"pattern": pattern}
        )
    
    def log_path_traversal_attempt(self, path: str):
        """Log path traversal attempt"""
        self.log_security_event(
            AuditEventType.PATH_TRAVERSAL_ATTEMPT,
            f"Path traversal attempt blocked",
            {"path": path}
        )
    
    def shutdown(self):
        """Shutdown audit logger"""
        if self.async_write:
            self._queue.put(None)
            self._writer_thread.join(timeout=5)


# Global instance
_audit_logger: Optional[AuditLogger] = None


def get_audit_logger() -> AuditLogger:
    """Get or create global audit logger"""
    global _audit_logger
    if _audit_logger is None:
        _audit_logger = AuditLogger()
    return _audit_logger


# Convenience functions
def audit_log(event_type: AuditEventType, action: str, **kwargs):
    """Log an audit event"""
    get_audit_logger().log(event_type, action, **kwargs)
```

---

## P2.4 Connection Pool Manager

**File**: `src/startd8/connection_pool.py`  
**Effort**: 8 hours

### Implementation

```python
# src/startd8/connection_pool.py
"""
Connection Pool Manager for efficient HTTP client management.
"""

import asyncio
import logging
import threading
from typing import Dict, Optional, Any
from contextlib import asynccontextmanager

import httpx

from .http_config import get_http_config, HTTPConfig

logger = logging.getLogger(__name__)


class ConnectionPoolManager:
    """
    Manages pooled HTTP connections for API clients.
    
    Features:
    - Singleton clients per base URL
    - Automatic cleanup on shutdown
    - Health checking
    - Statistics tracking
    
    Example:
        pool = ConnectionPoolManager()
        
        async with pool.get_client("https://api.anthropic.com") as client:
            response = await client.get("/v1/models")
    """
    
    def __init__(self):
        self._async_clients: Dict[str, httpx.AsyncClient] = {}
        self._sync_clients: Dict[str, httpx.Client] = {}
        self._lock = asyncio.Lock()
        self._sync_lock = threading.RLock()
        self._stats: Dict[str, Dict[str, int]] = {}
    
    async def get_async_client(
        self,
        base_url: str,
        provider: str = "default",
        **kwargs
    ) -> httpx.AsyncClient:
        """
        Get or create pooled async client for base URL.
        
        Args:
            base_url: Base URL for the client
            provider: Provider name for config lookup
            **kwargs: Additional client arguments
            
        Returns:
            Configured httpx.AsyncClient
        """
        async with self._lock:
            if base_url not in self._async_clients:
                config = get_http_config(provider)
                client_kwargs = config.to_client_kwargs()
                client_kwargs["base_url"] = base_url
                client_kwargs.update(kwargs)
                
                self._async_clients[base_url] = httpx.AsyncClient(**client_kwargs)
                self._stats[base_url] = {"requests": 0, "errors": 0}
                
                logger.debug(f"Created async client for {base_url}")
            
            return self._async_clients[base_url]
    
    def get_sync_client(
        self,
        base_url: str,
        provider: str = "default",
        **kwargs
    ) -> httpx.Client:
        """
        Get or create pooled sync client for base URL.
        
        Args:
            base_url: Base URL for the client
            provider: Provider name for config lookup
            **kwargs: Additional client arguments
            
        Returns:
            Configured httpx.Client
        """
        with self._sync_lock:
            if base_url not in self._sync_clients:
                config = get_http_config(provider)
                client_kwargs = config.to_client_kwargs()
                client_kwargs["base_url"] = base_url
                client_kwargs.update(kwargs)
                
                self._sync_clients[base_url] = httpx.Client(**client_kwargs)
                
                logger.debug(f"Created sync client for {base_url}")
            
            return self._sync_clients[base_url]
    
    @asynccontextmanager
    async def client(
        self,
        base_url: str,
        provider: str = "default",
        **kwargs
    ):
        """
        Context manager for getting a pooled client.
        
        Usage:
            async with pool.client("https://api.example.com") as client:
                response = await client.get("/endpoint")
        """
        client = await self.get_async_client(base_url, provider, **kwargs)
        
        try:
            yield client
            self._record_success(base_url)
        except Exception as e:
            self._record_error(base_url)
            raise
    
    def _record_success(self, base_url: str):
        """Record successful request"""
        if base_url in self._stats:
            self._stats[base_url]["requests"] += 1
    
    def _record_error(self, base_url: str):
        """Record failed request"""
        if base_url in self._stats:
            self._stats[base_url]["requests"] += 1
            self._stats[base_url]["errors"] += 1
    
    async def close_async(self, base_url: str = None):
        """
        Close async client(s).
        
        Args:
            base_url: Specific URL to close, or None for all
        """
        async with self._lock:
            if base_url:
                if base_url in self._async_clients:
                    await self._async_clients[base_url].aclose()
                    del self._async_clients[base_url]
                    logger.debug(f"Closed async client for {base_url}")
            else:
                for url, client in self._async_clients.items():
                    await client.aclose()
                    logger.debug(f"Closed async client for {url}")
                self._async_clients.clear()
    
    def close_sync(self, base_url: str = None):
        """
        Close sync client(s).
        
        Args:
            base_url: Specific URL to close, or None for all
        """
        with self._sync_lock:
            if base_url:
                if base_url in self._sync_clients:
                    self._sync_clients[base_url].close()
                    del self._sync_clients[base_url]
            else:
                for client in self._sync_clients.values():
                    client.close()
                self._sync_clients.clear()
    
    async def close_all(self):
        """Close all clients"""
        await self.close_async()
        self.close_sync()
    
    def get_stats(self) -> Dict[str, Dict[str, int]]:
        """Get connection pool statistics"""
        return dict(self._stats)
    
    async def health_check(self, base_url: str) -> bool:
        """
        Check if a client's connection is healthy.
        
        Args:
            base_url: Base URL to check
            
        Returns:
            True if healthy
        """
        try:
            client = await self.get_async_client(base_url)
            # Simple HEAD request to check connectivity
            response = await client.head("/")
            return response.status_code < 500
        except Exception:
            return False


# Global instance
_pool_manager: Optional[ConnectionPoolManager] = None


def get_connection_pool() -> ConnectionPoolManager:
    """Get or create global connection pool manager"""
    global _pool_manager
    if _pool_manager is None:
        _pool_manager = ConnectionPoolManager()
    return _pool_manager


async def cleanup_connections():
    """Cleanup all pooled connections"""
    global _pool_manager
    if _pool_manager:
        await _pool_manager.close_all()
```

---

## P2.5 Bounded LRU Cache

**File**: `src/startd8/bounded_cache.py`  
**Effort**: 6 hours

### Implementation

```python
# src/startd8/bounded_cache.py
"""
Bounded LRU Cache with TTL support.

Replaces the unbounded SimpleCache with memory-safe implementation.
"""

import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Any, Optional, Dict, TypeVar, Generic, Callable
from functools import wraps

T = TypeVar('T')


@dataclass
class CacheEntry(Generic[T]):
    """A single cache entry with metadata"""
    value: T
    created_at: float
    accessed_at: float
    ttl: Optional[float]
    size_bytes: int = 0
    
    def is_expired(self) -> bool:
        """Check if entry has expired"""
        if self.ttl is None:
            return False
        return time.time() - self.created_at > self.ttl


class BoundedLRUCache(Generic[T]):
    """
    Thread-safe LRU cache with size limits and TTL support.
    
    Features:
    - Maximum item count limit
    - Maximum memory size limit (approximate)
    - TTL per entry
    - LRU eviction policy
    - Statistics tracking
    
    Example:
        cache = BoundedLRUCache[str](max_items=1000, max_size_bytes=100*1024*1024)
        
        cache.set("key", "value", ttl=300)
        value = cache.get("key")  # Returns "value"
        
        # With decorator
        @cache.cached(ttl=60)
        def expensive_function(x):
            return x * 2
    """
    
    def __init__(
        self,
        max_items: int = 1000,
        max_size_bytes: int = 100 * 1024 * 1024,  # 100MB
        default_ttl: Optional[float] = 300.0  # 5 minutes
    ):
        self.max_items = max_items
        self.max_size_bytes = max_size_bytes
        self.default_ttl = default_ttl
        
        self._cache: OrderedDict[str, CacheEntry[T]] = OrderedDict()
        self._lock = threading.RLock()
        self._current_size = 0
        
        # Statistics
        self._hits = 0
        self._misses = 0
        self._evictions = 0
    
    def _estimate_size(self, value: Any) -> int:
        """Estimate memory size of a value"""
        import sys
        try:
            return sys.getsizeof(value)
        except TypeError:
            return 100  # Default estimate
    
    def _evict_if_needed(self):
        """Evict entries if limits exceeded"""
        # Evict by count
        while len(self._cache) >= self.max_items:
            self._evict_oldest()
        
        # Evict by size
        while self._current_size > self.max_size_bytes and self._cache:
            self._evict_oldest()
    
    def _evict_oldest(self):
        """Evict oldest (least recently used) entry"""
        if self._cache:
            key, entry = self._cache.popitem(last=False)
            self._current_size -= entry.size_bytes
            self._evictions += 1
    
    def get(self, key: str) -> Optional[T]:
        """
        Get value from cache.
        
        Args:
            key: Cache key
            
        Returns:
            Cached value or None if not found/expired
        """
        with self._lock:
            entry = self._cache.get(key)
            
            if entry is None:
                self._misses += 1
                return None
            
            if entry.is_expired():
                self._remove(key)
                self._misses += 1
                return None
            
            # Move to end (most recently used)
            self._cache.move_to_end(key)
            entry.accessed_at = time.time()
            
            self._hits += 1
            return entry.value
    
    def set(
        self,
        key: str,
        value: T,
        ttl: Optional[float] = None
    ) -> None:
        """
        Set value in cache.
        
        Args:
            key: Cache key
            value: Value to cache
            ttl: Time to live in seconds (uses default if None)
        """
        with self._lock:
            # Remove existing entry if present
            if key in self._cache:
                self._remove(key)
            
            # Calculate size
            size = self._estimate_size(value)
            
            # Evict if needed
            self._evict_if_needed()
            
            # Create entry
            now = time.time()
            entry = CacheEntry(
                value=value,
                created_at=now,
                accessed_at=now,
                ttl=ttl if ttl is not None else self.default_ttl,
                size_bytes=size
            )
            
            self._cache[key] = entry
            self._current_size += size
    
    def _remove(self, key: str) -> bool:
        """Remove entry by key"""
        if key in self._cache:
            entry = self._cache.pop(key)
            self._current_size -= entry.size_bytes
            return True
        return False
    
    def delete(self, key: str) -> bool:
        """
        Delete entry from cache.
        
        Args:
            key: Key to delete
            
        Returns:
            True if key existed
        """
        with self._lock:
            return self._remove(key)
    
    def clear(self) -> None:
        """Clear all entries"""
        with self._lock:
            self._cache.clear()
            self._current_size = 0
    
    def cleanup_expired(self) -> int:
        """
        Remove all expired entries.
        
        Returns:
            Number of entries removed
        """
        with self._lock:
            expired = [
                key for key, entry in self._cache.items()
                if entry.is_expired()
            ]
            
            for key in expired:
                self._remove(key)
            
            return len(expired)
    
    def get_or_set(
        self,
        key: str,
        factory: Callable[[], T],
        ttl: Optional[float] = None
    ) -> T:
        """
        Get value or compute and cache it.
        
        Args:
            key: Cache key
            factory: Function to compute value if not cached
            ttl: TTL for new entry
            
        Returns:
            Cached or computed value
        """
        value = self.get(key)
        if value is not None:
            return value
        
        value = factory()
        self.set(key, value, ttl)
        return value
    
    def cached(
        self,
        ttl: Optional[float] = None,
        key_prefix: str = ""
    ):
        """
        Decorator to cache function results.
        
        Args:
            ttl: TTL for cached results
            key_prefix: Prefix for cache keys
            
        Usage:
            @cache.cached(ttl=60)
            def expensive_function(x, y):
                return x + y
        """
        def decorator(func: Callable) -> Callable:
            @wraps(func)
            def wrapper(*args, **kwargs):
                # Generate cache key
                key_parts = [key_prefix, func.__name__]
                key_parts.extend(str(arg) for arg in args)
                key_parts.extend(f"{k}={v}" for k, v in sorted(kwargs.items()))
                cache_key = ":".join(key_parts)
                
                # Try cache
                cached = self.get(cache_key)
                if cached is not None:
                    return cached
                
                # Compute and cache
                result = func(*args, **kwargs)
                self.set(cache_key, result, ttl)
                return result
            
            return wrapper
        return decorator
    
    def stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        with self._lock:
            total_requests = self._hits + self._misses
            hit_rate = self._hits / total_requests if total_requests > 0 else 0
            
            return {
                "items": len(self._cache),
                "max_items": self.max_items,
                "size_bytes": self._current_size,
                "max_size_bytes": self.max_size_bytes,
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": hit_rate,
                "evictions": self._evictions,
            }
    
    def __len__(self) -> int:
        return len(self._cache)
    
    def __contains__(self, key: str) -> bool:
        return self.get(key) is not None


# Global caches
_caches: Dict[str, BoundedLRUCache] = {}
_cache_lock = threading.RLock()


def get_cache(
    name: str = "default",
    max_items: int = 1000,
    max_size_bytes: int = 100 * 1024 * 1024,
    default_ttl: float = 300.0
) -> BoundedLRUCache:
    """Get or create a named cache"""
    with _cache_lock:
        if name not in _caches:
            _caches[name] = BoundedLRUCache(
                max_items=max_items,
                max_size_bytes=max_size_bytes,
                default_ttl=default_ttl
            )
        return _caches[name]


def clear_all_caches():
    """Clear all caches"""
    with _cache_lock:
        for cache in _caches.values():
            cache.clear()
```

---

## P2.6 Async File Operations

**File**: `src/startd8/async_file_ops.py`  
**Effort**: 8 hours

### Implementation

```python
# src/startd8/async_file_ops.py
"""
Async File Operations for non-blocking I/O.
"""

import asyncio
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional, Union, Any
from functools import partial

try:
    import aiofiles
    HAS_AIOFILES = True
except ImportError:
    HAS_AIOFILES = False

from .validators import PathValidator

logger = logging.getLogger(__name__)

# Thread pool for fallback sync operations
_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="file_io")


async def async_read(
    path: Union[str, Path],
    encoding: str = "utf-8",
    validate: bool = True
) -> Optional[str]:
    """
    Async read file contents.
    
    Uses aiofiles if available, falls back to thread pool.
    
    Args:
        path: File path
        encoding: File encoding
        validate: Validate path before reading
        
    Returns:
        File contents or None if validation fails
    """
    path = Path(path)
    
    if validate:
        validator = PathValidator()
        result = validator.validate(str(path))
        if not result.is_valid:
            logger.error(f"Path validation failed: {result.findings}")
            return None
    
    if HAS_AIOFILES:
        async with aiofiles.open(path, 'r', encoding=encoding) as f:
            return await f.read()
    else:
        # Fallback to thread pool
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            _executor,
            partial(path.read_text, encoding=encoding)
        )


async def async_write(
    path: Union[str, Path],
    content: str,
    encoding: str = "utf-8",
    create_parents: bool = True,
    atomic: bool = True
) -> bool:
    """
    Async write to file.
    
    Args:
        path: File path
        content: Content to write
        encoding: File encoding
        create_parents: Create parent directories
        atomic: Use atomic write
        
    Returns:
        True if successful
    """
    path = Path(path)
    
    if create_parents:
        path.parent.mkdir(parents=True, exist_ok=True)
    
    try:
        if atomic:
            # Write to temp file then rename
            import tempfile
            import os
            
            fd, temp_path = tempfile.mkstemp(
                dir=path.parent,
                prefix=f".{path.name}.",
                suffix=".tmp"
            )
            
            try:
                if HAS_AIOFILES:
                    async with aiofiles.open(temp_path, 'w', encoding=encoding) as f:
                        await f.write(content)
                else:
                    loop = asyncio.get_event_loop()
                    await loop.run_in_executor(
                        _executor,
                        partial(Path(temp_path).write_text, content, encoding=encoding)
                    )
                
                os.close(fd)
                os.replace(temp_path, path)
                
            except Exception:
                os.close(fd)
                try:
                    os.unlink(temp_path)
                except OSError:
                    pass
                raise
        else:
            if HAS_AIOFILES:
                async with aiofiles.open(path, 'w', encoding=encoding) as f:
                    await f.write(content)
            else:
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(
                    _executor,
                    partial(path.write_text, content, encoding=encoding)
                )
        
        return True
        
    except Exception as e:
        logger.error(f"Failed to write {path}: {e}")
        return False


async def async_read_json(
    path: Union[str, Path],
    default: Any = None
) -> Any:
    """
    Async read JSON file.
    
    Args:
        path: File path
        default: Default value if file doesn't exist or is invalid
        
    Returns:
        Parsed JSON or default
    """
    path = Path(path)
    
    if not path.exists():
        return default
    
    try:
        content = await async_read(path)
        return json.loads(content)
    except (json.JSONDecodeError, TypeError) as e:
        logger.warning(f"Invalid JSON in {path}: {e}")
        return default


async def async_write_json(
    path: Union[str, Path],
    data: Any,
    indent: int = 2
) -> bool:
    """
    Async write JSON file.
    
    Args:
        path: File path
        data: Data to serialize
        indent: JSON indentation
        
    Returns:
        True if successful
    """
    try:
        content = json.dumps(data, indent=indent, default=str)
        return await async_write(path, content)
    except Exception as e:
        logger.error(f"Failed to write JSON to {path}: {e}")
        return False


async def async_exists(path: Union[str, Path]) -> bool:
    """Check if path exists (async)"""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        _executor,
        Path(path).exists
    )


async def async_mkdir(
    path: Union[str, Path],
    parents: bool = True,
    exist_ok: bool = True
) -> bool:
    """Create directory (async)"""
    try:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            _executor,
            partial(Path(path).mkdir, parents=parents, exist_ok=exist_ok)
        )
        return True
    except Exception as e:
        logger.error(f"Failed to create directory {path}: {e}")
        return False


async def async_delete(path: Union[str, Path]) -> bool:
    """Delete file (async)"""
    path = Path(path)
    
    if not path.exists():
        return True
    
    try:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(_executor, path.unlink)
        return True
    except Exception as e:
        logger.error(f"Failed to delete {path}: {e}")
        return False


def shutdown_executor():
    """Shutdown the file I/O thread pool"""
    _executor.shutdown(wait=True)
```

---

## P2.7 Cross-platform Permissions

**File**: `src/startd8/permissions.py`  
**Effort**: 4 hours

### Implementation

```python
# src/startd8/permissions.py
"""
Cross-platform File Permissions Management.
"""

import logging
import os
import platform
import stat
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Check for Windows-specific modules
HAS_WIN32 = False
if platform.system() == 'Windows':
    try:
        import win32security
        import ntsecuritycon as con
        HAS_WIN32 = True
    except ImportError:
        pass


def set_owner_only(path: Path) -> bool:
    """
    Set file permissions to owner-only (read/write).
    
    Unix: chmod 600
    Windows: Remove all ACEs except owner
    
    Args:
        path: File path
        
    Returns:
        True if successful
    """
    try:
        if platform.system() == 'Windows':
            return _set_windows_permissions(path)
        else:
            return _set_unix_permissions(path, 0o600)
    except Exception as e:
        logger.warning(f"Could not set permissions on {path}: {e}")
        return False


def set_owner_read_only(path: Path) -> bool:
    """
    Set file to owner read-only.
    
    Unix: chmod 400
    Windows: Remove write permissions
    
    Args:
        path: File path
        
    Returns:
        True if successful
    """
    try:
        if platform.system() == 'Windows':
            return _set_windows_read_only(path)
        else:
            return _set_unix_permissions(path, 0o400)
    except Exception as e:
        logger.warning(f"Could not set read-only on {path}: {e}")
        return False


def set_directory_private(path: Path) -> bool:
    """
    Set directory to owner-only access.
    
    Unix: chmod 700
    Windows: Remove all ACEs except owner
    
    Args:
        path: Directory path
        
    Returns:
        True if successful
    """
    try:
        if platform.system() == 'Windows':
            return _set_windows_permissions(path)
        else:
            return _set_unix_permissions(path, 0o700)
    except Exception as e:
        logger.warning(f"Could not set directory permissions on {path}: {e}")
        return False


def _set_unix_permissions(path: Path, mode: int) -> bool:
    """Set Unix file permissions"""
    os.chmod(path, mode)
    return True


def _set_windows_permissions(path: Path) -> bool:
    """Set Windows file permissions to owner-only"""
    if not HAS_WIN32:
        logger.warning("win32security not available, cannot set Windows permissions")
        return False
    
    # Get current user's SID
    username = os.environ.get('USERNAME')
    domain = os.environ.get('USERDOMAIN', '')
    
    try:
        user_sid, _, _ = win32security.LookupAccountName(domain, username)
    except Exception as e:
        logger.error(f"Could not get user SID: {e}")
        return False
    
    # Create new DACL with only owner access
    dacl = win32security.ACL()
    dacl.AddAccessAllowedAce(
        win32security.ACL_REVISION,
        con.FILE_ALL_ACCESS,
        user_sid
    )
    
    # Get security descriptor
    sd = win32security.GetFileSecurity(
        str(path),
        win32security.DACL_SECURITY_INFORMATION
    )
    
    # Set new DACL
    sd.SetSecurityDescriptorDacl(1, dacl, 0)
    win32security.SetFileSecurity(
        str(path),
        win32security.DACL_SECURITY_INFORMATION,
        sd
    )
    
    return True


def _set_windows_read_only(path: Path) -> bool:
    """Set Windows file to read-only"""
    if not HAS_WIN32:
        # Fallback: use standard read-only attribute
        import stat
        os.chmod(path, stat.S_IREAD)
        return True
    
    # Get current user's SID
    username = os.environ.get('USERNAME')
    domain = os.environ.get('USERDOMAIN', '')
    
    try:
        user_sid, _, _ = win32security.LookupAccountName(domain, username)
    except Exception:
        return False
    
    # Create DACL with read-only access
    dacl = win32security.ACL()
    dacl.AddAccessAllowedAce(
        win32security.ACL_REVISION,
        con.FILE_GENERIC_READ,
        user_sid
    )
    
    sd = win32security.GetFileSecurity(
        str(path),
        win32security.DACL_SECURITY_INFORMATION
    )
    sd.SetSecurityDescriptorDacl(1, dacl, 0)
    win32security.SetFileSecurity(
        str(path),
        win32security.DACL_SECURITY_INFORMATION,
        sd
    )
    
    return True


def check_permissions(path: Path) -> dict:
    """
    Check file permissions.
    
    Args:
        path: File path
        
    Returns:
        Dict with permission information
    """
    if not path.exists():
        return {"exists": False}
    
    stat_info = path.stat()
    mode = stat_info.st_mode
    
    result = {
        "exists": True,
        "is_file": path.is_file(),
        "is_dir": path.is_dir(),
        "owner_read": bool(mode & stat.S_IRUSR),
        "owner_write": bool(mode & stat.S_IWUSR),
        "owner_execute": bool(mode & stat.S_IXUSR),
        "group_read": bool(mode & stat.S_IRGRP),
        "group_write": bool(mode & stat.S_IWGRP),
        "other_read": bool(mode & stat.S_IROTH),
        "other_write": bool(mode & stat.S_IWOTH),
        "mode_octal": oct(mode)[-3:],
    }
    
    # Check if secure (only owner has access)
    result["is_secure"] = (
        result["owner_read"] and
        not result["group_read"] and
        not result["group_write"] and
        not result["other_read"] and
        not result["other_write"]
    )
    
    return result


def ensure_secure_file(path: Path, content: str = None) -> bool:
    """
    Create or update file with secure permissions.
    
    Args:
        path: File path
        content: Optional content to write
        
    Returns:
        True if successful
    """
    try:
        # Create parent with secure permissions
        path.parent.mkdir(parents=True, exist_ok=True)
        set_directory_private(path.parent)
        
        # Write content if provided
        if content is not None:
            path.write_text(content)
        elif not path.exists():
            path.touch()
        
        # Set secure permissions
        return set_owner_only(path)
        
    except Exception as e:
        logger.error(f"Failed to create secure file {path}: {e}")
        return False
```

---

## P2.8 Agent Integration Updates

**File**: Modifications to `src/startd8/agents.py`  
**Effort**: 3 hours

### Changes Required

```python
# Updates to agents.py

# Add imports
from .rate_limiter import get_provider_limiter, RateLimitError, CircuitOpenError
from .retry_handler import retry_async, RetryConfig, get_retry_config
from .http_config import get_http_config
from .audit_logger import get_audit_logger
import hashlib

class ClaudeAgent(BaseAgent):
    """Updated ClaudeAgent with security features"""
    
    def __init__(
        self,
        name: str = "anthropic:claude-3-opus-20240229",
        model: str = "claude-3-opus-20240229",
        api_key: Optional[str] = None,
        max_tokens: int = 4096,
        cost_tracker: Optional['CostTracker'] = None,
        budget_manager: Optional['BudgetManager'] = None
    ):
        super().__init__(name, model, cost_tracker, budget_manager)
        
        if not _ANTHROPIC_AVAILABLE:
            raise ImportError(
                "anthropic package not installed. "
                "Install with: pip install startd8[anthropic] or pip install anthropic"
            )
        
        # Get HTTP config with timeouts
        http_config = get_http_config("anthropic")
        
        self.client = Anthropic(
            api_key=api_key,
            timeout=http_config.timeout.to_httpx()
        )
        self.async_client = AsyncAnthropic(
            api_key=api_key,
            timeout=http_config.timeout.to_httpx()
        )
        self.max_tokens = max_tokens
        
        # Get retry config
        self.retry_config = get_retry_config("anthropic")
        
        # Audit logger
        self.audit = get_audit_logger()
    
    async def agenerate(self, prompt: str) -> Tuple[str, int, TokenUsage]:
        """Generate response with rate limiting and retry"""
        limiter = get_provider_limiter()
        
        # Estimate tokens
        estimated_tokens = len(prompt) // 4 + self.max_tokens
        
        # Check circuit breaker
        breaker = limiter.get_breaker("anthropic")
        if not breaker.can_execute():
            raise CircuitOpenError("Claude API circuit breaker is open")
        
        # Check rate limit
        rate_limiter = limiter.get_limiter("anthropic")
        if not await rate_limiter.acquire(estimated_tokens):
            raise RateLimitError("Rate limit exceeded for Anthropic")
        
        start_time = time.time()
        prompt_hash = hashlib.sha256(prompt.encode()).hexdigest()[:12]
        
        try:
            # Define the API call
            async def _api_call():
                return await self.async_client.messages.create(
                    model=self.model,
                    max_tokens=self.max_tokens,
                    messages=[{"role": "user", "content": prompt}]
                )
            
            # Execute with retry
            response = await retry_async(_api_call, self.retry_config)
            
            end_time = time.time()
            response_time_ms = int((end_time - start_time) * 1000)
            
            response_text = response.content[0].text
            
            token_usage = TokenUsage(
                input=response.usage.input_tokens,
                output=response.usage.output_tokens,
                total=response.usage.input_tokens + response.usage.output_tokens
            )
            
            # Record success
            breaker.record_success()
            await rate_limiter.record(
                tokens_used=token_usage.total,
                cost=self._calculate_cost(token_usage),
                success=True,
                latency_ms=response_time_ms
            )
            
            # Audit log
            self.audit.log_agent_invocation(
                agent=self.name,
                prompt_hash=prompt_hash,
                tokens=token_usage.total,
                cost=self._calculate_cost(token_usage),
                latency_ms=response_time_ms
            )
            
            return response_text, response_time_ms, token_usage
            
        except Exception as e:
            breaker.record_failure()
            self.audit.log_agent_error(self.name, str(e))
            raise
    
    def _calculate_cost(self, usage: TokenUsage) -> float:
        """Calculate cost based on token usage"""
        # Costs per 1M tokens (approximate)
        costs = {
            "claude-3-opus": {"input": 15.0, "output": 75.0},
            "claude-3-sonnet": {"input": 3.0, "output": 15.0},
            "claude-3-haiku": {"input": 0.25, "output": 1.25},
        }
        
        rates = costs.get(self.model.split("-20")[0], costs["claude-3-sonnet"])
        
        input_cost = (usage.input / 1_000_000) * rates["input"]
        output_cost = (usage.output / 1_000_000) * rates["output"]
        
        return input_cost + output_cost
```

---

## Integration Checklist for Phase 2

### Files to Create
- [ ] `src/startd8/log_filter.py`
- [ ] `src/startd8/http_config.py`
- [ ] `src/startd8/audit_logger.py`
- [ ] `src/startd8/connection_pool.py`
- [ ] `src/startd8/bounded_cache.py`
- [ ] `src/startd8/async_file_ops.py`
- [ ] `src/startd8/permissions.py`

### Files to Modify
- [ ] `src/startd8/agents.py` - Add timeouts, rate limiting
- [ ] `src/startd8/logging_config.py` - Add sanitization filter
- [ ] `src/startd8/cache.py` - Replace with bounded cache
- [ ] `src/startd8/config.py` - Use permissions module

### Testing Requirements
- [ ] Unit tests for all new modules
- [ ] Integration tests for audit logging
- [ ] Performance tests for cache
- [ ] Log sanitization verification

---

**Next**: See `PHASE3_DETAILED_DESIGN.md` for Medium Priority Improvements
