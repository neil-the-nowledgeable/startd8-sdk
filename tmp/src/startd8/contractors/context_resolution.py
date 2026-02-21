"""
Pipeline Context Resolution Module

Implements a context resolution strategy with structured sections (IMP-P1 through IMP-P5),
security validation, and rich context building capabilities. Designed to collect, validate,
organize, and resolve context from multiple sources into a structured format for downstream
pipeline stages.

Sections:
    - P1_IDENTITY: Who/what is being processed (project name, version, etc.)
    - P2_INTENT: What the pipeline aims to accomplish (goals, targets, etc.)
    - P3_ENVIRONMENT: Runtime environment details (OS, paths, runtime config)
    - P4_DEPENDENCIES: External dependencies and their versions
    - P5_CONSTRAINTS: Limits, rules, and policies governing execution

Resolution Strategies:
    - FIRST_WINS: First value set for a key is kept; subsequent writes ignored.
    - LAST_WINS: Latest value always overwrites (default).
    - MERGE_DEEP: Recursively merge dict values; non-dict values use last-wins.
    - ERROR_ON_CONFLICT: Raise ContextValidationError on conflicting values.

Security Validation:
    - Key format enforcement (alphanumeric + underscores)
    - String length limits
    - Nesting depth limits
    - Path traversal detection
    - Shell/SQL injection pattern detection
    - Custom regex pattern support
"""

import logging
import enum
import dataclasses
import copy
import re
import os
import typing
import json
import hashlib
import time

# Configure module logger
logger = logging.getLogger(__name__)

# ============================================================================
# Constants
# ============================================================================

MAX_KEY_LENGTH: int = 128
MAX_STRING_LENGTH: int = 10_000
MAX_NESTING_DEPTH: int = 5

# Regex pattern for valid key names: alphanumeric + underscores, starting with letter or underscore
KEY_PATTERN: re.Pattern = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")

# Path traversal patterns (various encodings and formats)
PATH_TRAVERSAL_PATTERNS: typing.List[re.Pattern] = [
    re.compile(r"\.\./"),
    re.compile(r"\.\.[/\\]"),
    re.compile(r"[/\\]\.\.[/\\]?"),
    re.compile(r"%2e%2e", re.IGNORECASE),
    re.compile(r"\.\.%2f", re.IGNORECASE),
    re.compile(r"%2f\.\.?", re.IGNORECASE),
]

# Injection patterns (shell and SQL)
INJECTION_PATTERNS: typing.List[re.Pattern] = [
    re.compile(r";\s*(rm|cat|ls|wget|curl|chmod|chown|sh|bash)\b", re.IGNORECASE),
    re.compile(r"\|\s*(rm|cat|ls|wget|curl|chmod|chown|sh|bash)\b", re.IGNORECASE),
    re.compile(r"`[^`]+`"),
    re.compile(r"\$\([^)]+\)"),
    re.compile(r"('\s*(OR|AND|UNION|SELECT|DROP|INSERT|UPDATE|DELETE|EXEC)\s)", re.IGNORECASE),
    re.compile(r"(--|#|/\*)\s*$"),
    re.compile(r"'\s*OR\s+'1'\s*=\s*'1", re.IGNORECASE),
    re.compile(r";\s*DROP\s+TABLE", re.IGNORECASE),
]

# Sentinel value for detecting unset keys
_SENTINEL: object = object()


# ============================================================================
# Utility Functions (defined before classes that reference them)
# ============================================================================


def sanitize_key(key: str) -> str:
    """
    Sanitize a key by stripping whitespace, replacing hyphens and spaces with
    underscores, and truncating to MAX_KEY_LENGTH.

    Args:
        key: The raw key string to sanitize.

    Returns:
        A sanitized key string safe for use as a context entry key.
    """
    if not isinstance(key, str):
        key = str(key)
    key = key.strip().replace("-", "_").replace(" ", "_")
    return key[:MAX_KEY_LENGTH]


def validate_key(key: str) -> typing.Optional[str]:
    """
    Validate a key name against format and length constraints.

    Args:
        key: The key string to validate.

    Returns:
        An error message string if the key is invalid, or None if valid.
    """
    if not isinstance(key, str):
        return "Key must be a string"
    if len(key) == 0:
        return "Key cannot be empty"
    if len(key) > MAX_KEY_LENGTH:
        return f"Key exceeds maximum length of {MAX_KEY_LENGTH}"
    if not KEY_PATTERN.match(key):
        return f"Key must match pattern {KEY_PATTERN.pattern}"
    return None


def detect_path_traversal(value: str) -> bool:
    """
    Detect path traversal patterns in a string value.

    Args:
        value: The string to scan.

    Returns:
        True if any path traversal pattern is detected.
    """
    if not isinstance(value, str):
        return False
    for pattern in PATH_TRAVERSAL_PATTERNS:
        if pattern.search(value):
            logger.warning("Path traversal pattern detected in value")
            return True
    return False


def detect_injection(value: str) -> bool:
    """
    Detect shell or SQL injection patterns in a string value.

    Args:
        value: The string to scan.

    Returns:
        True if any injection pattern is detected.
    """
    if not isinstance(value, str):
        return False
    for pattern in INJECTION_PATTERNS:
        if pattern.search(value):
            logger.warning("Injection pattern detected in value")
            return True
    return False


def validate_value(
    value: typing.Any,
    max_depth: int = MAX_NESTING_DEPTH,
    max_str_len: int = MAX_STRING_LENGTH,
    _current_depth: int = 0,
) -> typing.Optional[str]:
    """
    Recursively validate a value for type safety, nesting depth, string length,
    path traversal, and injection patterns.

    Args:
        value: The value to validate.
        max_depth: Maximum allowed nesting depth for dicts/lists.
        max_str_len: Maximum allowed string length.
        _current_depth: Internal counter for current recursion depth.

    Returns:
        An error message string if the value is invalid, or None if valid.
    """
    if _current_depth > max_depth:
        return f"Nesting depth exceeds maximum of {max_depth}"

    # Primitives are always valid
    if value is None or isinstance(value, (bool, int, float)):
        return None

    # String validation
    if isinstance(value, str):
        if len(value) > max_str_len:
            return f"String length {len(value)} exceeds maximum of {max_str_len}"
        if detect_path_traversal(value):
            return "Path traversal pattern detected"
        if detect_injection(value):
            return "Injection pattern detected"
        return None

    # Dict validation
    if isinstance(value, dict):
        for key, val in value.items():
            key_err = validate_key(str(key))
            if key_err:
                return f"Invalid dict key '{key}': {key_err}"
            val_err = validate_value(val, max_depth, max_str_len, _current_depth + 1)
            if val_err:
                return f"Invalid value for dict key '{key}': {val_err}"
        return None

    # List/tuple validation
    if isinstance(value, (list, tuple)):
        for idx, item in enumerate(value):
            item_err = validate_value(item, max_depth, max_str_len, _current_depth + 1)
            if item_err:
                return f"Invalid item at index {idx}: {item_err}"
        return None

    # Reject bytes explicitly
    if isinstance(value, bytes):
        return "Bytes type not supported"

    return f"Unsupported type: {type(value).__name__}"


def deep_merge(base: dict, override: dict) -> dict:
    """
    Deep merge ``override`` into ``base``. Nested dicts are merged recursively;
    non-dict conflicts are resolved by taking the override value.

    Both input dicts are left unmodified; a new dict is returned.

    Args:
        base: The base dictionary.
        override: The dictionary whose values take precedence.

    Returns:
        A new merged dictionary.
    """
    result = copy.deepcopy(base)
    for key, override_val in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(override_val, dict):
            result[key] = deep_merge(result[key], override_val)
        else:
            result[key] = copy.deepcopy(override_val)
    return result


# ============================================================================
# Enums
# ============================================================================


class ContextSection(str, enum.Enum):
    """
    Pipeline context sections representing progressive stages of enrichment.

    Each section corresponds to an IMP phase (P1 through P5) and groups
    related context entries together.
    """

    P1_IDENTITY = "imp_p1_identity"
    P2_INTENT = "imp_p2_intent"
    P3_ENVIRONMENT = "imp_p3_environment"
    P4_DEPENDENCIES = "imp_p4_dependencies"
    P5_CONSTRAINTS = "imp_p5_constraints"


class ResolutionStrategy(str, enum.Enum):
    """
    Strategy for resolving conflicts when the same key appears in multiple sources.

    - FIRST_WINS: The first value written is kept.
    - LAST_WINS: The most recent value overwrites previous ones.
    - MERGE_DEEP: Dict values are recursively merged; scalars use last-wins.
    - ERROR_ON_CONFLICT: Raise an error when conflicting values are detected.
    """

    FIRST_WINS = "first_wins"
    LAST_WINS = "last_wins"
    MERGE_DEEP = "merge_deep"
    ERROR_ON_CONFLICT = "error_on_conflict"


# ============================================================================
# Exceptions
# ============================================================================


class ContextValidationError(Exception):
    """Raised when context validation fails."""

    def __init__(self, message: str, violations: typing.Optional[typing.List] = None):
        super().__init__(message)
        self.violations: typing.List = violations or []


# ============================================================================
# Data Classes
# ============================================================================


@dataclasses.dataclass
class ValidationViolation:
    """Represents a single validation violation with location and severity."""

    section: str
    key: str
    message: str
    severity: str = "error"

    def to_dict(self) -> dict:
        """Convert to dictionary representation."""
        return dataclasses.asdict(self)


@dataclasses.dataclass
class ValidationResult:
    """
    Accumulates validation violations from one or more validation passes.
    """

    violations: typing.List[ValidationViolation] = dataclasses.field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        """Return True if no violations have been recorded."""
        return len(self.violations) == 0

    def add(self, violation: ValidationViolation) -> None:
        """Add a single violation."""
        self.violations.append(violation)

    def merge(self, other: "ValidationResult") -> None:
        """Merge all violations from another ValidationResult into this one."""
        self.violations.extend(other.violations)

    def to_dict(self) -> typing.List[dict]:
        """Convert all violations to a list of dictionaries."""
        return [v.to_dict() for v in self.violations]


@dataclasses.dataclass
class ContextEntry:
    """Represents a single context entry with provenance information."""

    section: ContextSection
    key: str
    value: typing.Any
    source: str = "direct"
    timestamp: float = dataclasses.field(default_factory=time.time)


@dataclasses.dataclass(frozen=True)
class ContextSnapshot:
    """
    Immutable snapshot of resolved context.

    Data and metadata are stored as JSON strings for serializability and
    to enforce immutability. A SHA-256 checksum is included for integrity
    verification.
    """

    data: str  # JSON string of sections dict
    metadata: str  # JSON string of metadata dict
    checksum: str  # SHA-256 hex digest of data

    @property
    def sections(self) -> dict:
        """Parse and return the sections dictionary."""
        return json.loads(self.data)

    @property
    def meta(self) -> dict:
        """Parse and return the metadata dictionary."""
        return json.loads(self.metadata)

    def to_dict(self) -> dict:
        """Convert snapshot to a plain dictionary."""
        return {
            "sections": self.sections,
            "metadata": self.meta,
            "checksum": self.checksum,
        }

    def get(self, section_name: str, key: str, default: typing.Any = None) -> typing.Any:
        """
        Retrieve a value from a specific section.

        Args:
            section_name: The section's string value (e.g. ``"imp_p1_identity"``).
            key: The key within the section.
            default: Value to return if the key is not found.

        Returns:
            The stored value, or *default* if not present.
        """
        sections = self.sections
        if section_name in sections and isinstance(sections[section_name], dict):
            return sections[section_name].get(key, default)
        return default


# ============================================================================
# SecurityValidator
# ============================================================================


class SecurityValidator:
    """
    Validates context entries and entire sections for security issues.

    Checks include key format, value types, string length, nesting depth,
    path traversal patterns, injection patterns, and optional custom patterns.
    """

    def __init__(
        self,
        max_key_len: int = MAX_KEY_LENGTH,
        max_str_len: int = MAX_STRING_LENGTH,
        max_depth: int = MAX_NESTING_DEPTH,
        custom_patterns: typing.Optional[typing.List[re.Pattern]] = None,
    ):
        self.max_key_len = max_key_len
        self.max_str_len = max_str_len
        self.max_depth = max_depth
        self.custom_patterns: typing.List[re.Pattern] = custom_patterns or []

    def validate_entry(self, section: str, key: str, value: typing.Any) -> ValidationResult:
        """
        Validate a single context entry.

        Args:
            section: Name of the section the entry belongs to.
            key: The entry key.
            value: The entry value.

        Returns:
            A ValidationResult containing any violations found.
        """
        result = ValidationResult()

        # Validate key
        key_err = validate_key(key)
        if key_err:
            result.add(ValidationViolation(section=section, key=key, message=key_err))

        # Validate value
        val_err = validate_value(value, self.max_depth, self.max_str_len)
        if val_err:
            result.add(ValidationViolation(section=section, key=key, message=val_err))

        # Check custom patterns on string values
        if isinstance(value, str):
            for pattern in self.custom_patterns:
                if pattern.search(value):
                    result.add(
                        ValidationViolation(
                            section=section,
                            key=key,
                            message=f"Custom pattern matched: {pattern.pattern}",
                            severity="warning",
                        )
                    )

        return result

    def validate_context(self, sections: dict) -> ValidationResult:
        """
        Validate all entries across all sections.

        Args:
            sections: A dict mapping section names to dicts of key-value entries.

        Returns:
            A ValidationResult containing all violations found.
        """
        result = ValidationResult()
        for section_name, entries in sections.items():
            if isinstance(entries, dict):
                for key, value in entries.items():
                    result.merge(self.validate_entry(section_name, key, value))
        return result


# ============================================================================
# PipelineContext
# ============================================================================


class PipelineContext:
    """
    Mutable context holder with support for multiple resolution strategies.

    Manages five context sections (P1–P5) and provides methods for setting,
    getting, merging, validating, and snapshotting context data with full
    provenance tracking.
    """

    def __init__(
        self,
        strategy: ResolutionStrategy = ResolutionStrategy.LAST_WINS,
        validator: typing.Optional[SecurityValidator] = None,
    ):
        self._sections: typing.Dict[ContextSection, dict] = {
            section: {} for section in ContextSection
        }
        self._strategy: ResolutionStrategy = strategy
        self._validator: SecurityValidator = validator or SecurityValidator()
        self._entries_log: typing.List[ContextEntry] = []

    def set(
        self,
        section: ContextSection,
        key: str,
        value: typing.Any,
        source: str = "direct",
    ) -> None:
        """
        Set a value in a section, applying the configured resolution strategy
        if the key already exists.

        Args:
            section: The target context section.
            key: The entry key.
            value: The entry value.
            source: Provenance label for this write.

        Raises:
            ContextValidationError: If strategy is ERROR_ON_CONFLICT and a
                conflicting value already exists for this key.
        """
        existing = self._sections[section].get(key, _SENTINEL)

        if existing is not _SENTINEL:
            if self._strategy == ResolutionStrategy.FIRST_WINS:
                logger.debug(
                    "FIRST_WINS: keeping existing value for %s.%s",
                    section.value,
                    key,
                )
                return
            elif self._strategy == ResolutionStrategy.ERROR_ON_CONFLICT:
                if existing != value:
                    raise ContextValidationError(
                        f"Conflict on {section.value}.{key}: "
                        f"existing={existing!r}, new={value!r}",
                        violations=[],
                    )
                # Same value — allow silently
                return
            elif self._strategy == ResolutionStrategy.MERGE_DEEP:
                if isinstance(existing, dict) and isinstance(value, dict):
                    value = deep_merge(existing, value)
                    logger.debug(
                        "MERGE_DEEP: merged dict for %s.%s", section.value, key
                    )
            # LAST_WINS (and MERGE_DEEP for non-dict): fall through to overwrite

        self._sections[section][key] = value
        self._entries_log.append(
            ContextEntry(section=section, key=key, value=value, source=source)
        )
        logger.debug("Set %s.%s = %r (source: %s)", section.value, key, value, source)

    def get(
        self, section: ContextSection, key: str, default: typing.Any = None
    ) -> typing.Any:
        """Retrieve a value from a section, returning *default* if absent."""
        return self._sections[section].get(key, default)

    def get_section(self, section: ContextSection) -> dict:
        """Return a deep copy of an entire section's data."""
        return copy.deepcopy(self._sections[section])

    def get_all_sections(self) -> dict:
        """Return all sections as ``{section_name: {key: value, ...}, ...}``."""
        return {
            section.value: copy.deepcopy(entries)
            for section, entries in self._sections.items()
        }

    def merge_dict(
        self, section: ContextSection, data: dict, source: str = "dict"
    ) -> None:
        """
        Merge a flat dictionary into a section, sanitizing keys.

        Args:
            section: The target context section.
            data: Dictionary of key-value pairs to merge.
            source: Provenance label for this merge.
        """
        if not isinstance(data, dict):
            logger.warning("merge_dict called with non-dict data, skipping")
            return
        for key, value in data.items():
            safe_key = sanitize_key(key)
            if not safe_key:
                logger.warning("Key sanitized to empty string, skipping: %r", key)
                continue
            self.set(section, safe_key, value, source=source)

    def merge_context(self, other: "PipelineContext") -> None:
        """Merge all sections from another PipelineContext into this one."""
        for section in ContextSection:
            for key, value in other._sections[section].items():
                self.set(section, key, value, source="merged_context")

    def merge_env(
        self,
        section: ContextSection,
        prefix: str,
        strip_prefix: bool = True,
    ) -> None:
        """
        Merge environment variables whose names start with *prefix* into a section.

        Args:
            section: The target context section.
            prefix: Only env vars starting with this prefix are included.
            strip_prefix: If True, remove the prefix from the resulting key name.
        """
        for env_key, env_val in os.environ.items():
            if env_key.startswith(prefix):
                key = env_key[len(prefix) :] if strip_prefix else env_key
                key = sanitize_key(key.lower())
                if not key:
                    logger.warning(
                        "Env key sanitized to empty string, skipping: %r", env_key
                    )
                    continue
                self.set(section, key, env_val, source="environment")

    def validate(self) -> ValidationResult:
        """Validate all current context entries and return the result."""
        sections_dict = {
            section.value: entries for section, entries in self._sections.items()
        }
        return self._validator.validate_context(sections_dict)

    def snapshot(self, strict: bool = True) -> ContextSnapshot:
        """
        Create an immutable snapshot of the current context.

        Args:
            strict: If True, raise ContextValidationError when validation fails.
                If False, log a warning and proceed.

        Returns:
            A frozen ContextSnapshot with data, metadata, and integrity checksum.

        Raises:
            ContextValidationError: If strict=True and validation violations exist.
        """
        result = self.validate()
        if strict and not result.is_valid:
            raise ContextValidationError(
                f"Context validation failed with {len(result.violations)} violation(s)",
                violations=result.violations,
            )
        if not result.is_valid:
            logger.warning(
                "Context has %d validation violation(s), but proceeding (strict=False)",
                len(result.violations),
            )

        sections_dict = self.get_all_sections()
        metadata = {
            "strategy": self._strategy.value,
            "entry_count": sum(
                len(entries) for entries in self._sections.values()
            ),
            "sections_populated": [
                s.value for s in ContextSection if self._sections[s]
            ],
        }

        data_str = json.dumps(sections_dict, sort_keys=True, default=str)
        meta_str = json.dumps(metadata, sort_keys=True)
        checksum = hashlib.sha256(data_str.encode("utf-8")).hexdigest()

        return ContextSnapshot(data=data_str, metadata=meta_str, checksum=checksum)

    def to_dict(self) -> dict:
        """Serialize context to a plain dictionary."""
        return {
            "sections": self.get_all_sections(),
            "strategy": self._strategy.value,
        }

    @classmethod
    def from_dict(
        cls,
        data: dict,
        strategy: typing.Optional[typing.Union[str, ResolutionStrategy]] = None,
    ) -> "PipelineContext":
        """
        Deserialize a PipelineContext from a dictionary.

        Accepts dicts in the format ``{"sections": {...}, "strategy": "..."}``
        or with section data at the top level.

        Args:
            data: The source dictionary.
            strategy: Override resolution strategy. If None, uses the strategy
                stored in *data* or defaults to LAST_WINS.

        Returns:
            A new PipelineContext populated with the deserialized data.
        """
        if strategy is None:
            strategy_str = data.get("strategy", "last_wins")
            strat = ResolutionStrategy(strategy_str)
        elif isinstance(strategy, ResolutionStrategy):
            strat = strategy
        else:
            strat = ResolutionStrategy(strategy)

        ctx = cls(strategy=strat)

        sections_data = data.get("sections", data)
        section_map = {section.value: section for section in ContextSection}

        for section_name, entries in sections_data.items():
            if section_name not in section_map:
                logger.warning("Unknown section name: %s, skipping", section_name)
                continue
            section = section_map[section_name]
            if isinstance(entries, dict):
                for key, value in entries.items():
                    ctx.set(section, key, value, source="from_dict")

        return ctx


# ============================================================================
# ContextBuilder
# ============================================================================


class ContextBuilder:
    """
    Builder-pattern API for constructing and resolving pipeline context.

    All ``with_*`` and ``merge_*`` methods return ``self`` for fluent chaining::

        snapshot = (
            ContextBuilder()
            .with_identity(project="myapp", version="1.0.0")
            .with_intent(goal="deploy")
            .with_environment(runtime="python3.12")
            .with_constraints(max_memory="512M")
            .resolve()
        )
    """

    def __init__(
        self,
        strategy: ResolutionStrategy = ResolutionStrategy.LAST_WINS,
        validator: typing.Optional[SecurityValidator] = None,
    ):
        self._context = PipelineContext(strategy=strategy, validator=validator)

    def with_identity(self, **kwargs: typing.Any) -> "ContextBuilder":
        """Add entries to the P1_IDENTITY section."""
        return self.with_section(ContextSection.P1_IDENTITY, **kwargs)

    def with_intent(self, **kwargs: typing.Any) -> "ContextBuilder":
        """Add entries to the P2_INTENT section."""
        return self.with_section(ContextSection.P2_INTENT, **kwargs)

    def with_environment(self, **kwargs: typing.Any) -> "ContextBuilder":
        """Add entries to the P3_ENVIRONMENT section."""
        return self.with_section(ContextSection.P3_ENVIRONMENT, **kwargs)

    def with_dependencies(self, **kwargs: typing.Any) -> "ContextBuilder":
        """Add entries to the P4_DEPENDENCIES section."""
        return self.with_section(ContextSection.P4_DEPENDENCIES, **kwargs)

    def with_constraints(self, **kwargs: typing.Any) -> "ContextBuilder":
        """Add entries to the P5_CONSTRAINTS section."""
        return self.with_section(ContextSection.P5_CONSTRAINTS, **kwargs)

    def with_section(
        self, section: ContextSection, **kwargs: typing.Any
    ) -> "ContextBuilder":
        """Add arbitrary entries to a specific section."""
        for key, value in kwargs.items():
            self._context.set(section, key, value, source="builder")
        return self

    def merge_from_dict(
        self, data: dict, source: str = "dict"
    ) -> "ContextBuilder":
        """
        Merge entries from a dictionary.

        Expected format: ``{"imp_p1_identity": {...}, ...}`` or
        ``{"sections": {"imp_p1_identity": {...}, ...}}``.
        """
        sections = data.get("sections", data)
        section_map = {section.value: section for section in ContextSection}

        for section_name, entries in sections.items():
            if section_name not in section_map:
                logger.warning(
                    "Unknown section in dict merge: %s, skipping", section_name
                )
                continue
            section = section_map[section_name]
            if isinstance(entries, dict):
                self._context.merge_dict(section, entries, source=source)

        return self

    def merge_from_env(
        self,
        section: ContextSection,
        prefix: str,
        strip_prefix: bool = True,
    ) -> "ContextBuilder":
        """Merge environment variables matching *prefix* into a section."""
        self._context.merge_env(section, prefix, strip_prefix)
        return self

    def merge_from_context(self, other: PipelineContext) -> "ContextBuilder":
        """Merge another PipelineContext into the builder's context."""
        self._context.merge_context(other)
        return self

    def set_strategy(self, strategy: ResolutionStrategy) -> "ContextBuilder":
        """Change the resolution strategy for subsequent operations."""
        self._context._strategy = strategy
        return self

    def resolve(self, strict: bool = True) -> ContextSnapshot:
        """
        Resolve and return an immutable snapshot of the built context.

        Args:
            strict: If True, raises ContextValidationError on validation failure.

        Returns:
            A frozen ContextSnapshot.
        """
        return self._context.snapshot(strict=strict)

    def build_context(self) -> PipelineContext:
        """Return the underlying mutable PipelineContext for direct manipulation."""
        return self._context