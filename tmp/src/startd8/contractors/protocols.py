"""Core abstractions for context resolution in the startd8 pipeline.

This module defines:
- ``ContextResolutionStrategy`` — A Protocol for mode-aware context resolution
  implementing the Strategy pattern.
- ``ValidationConfig`` — Configuration for post-generation validation hookpoints.
- ``ValidationResult`` — Individual validation findings with severity and provenance.
- Exception hierarchy for typed error handling across protocol methods.
- Utility functions for path validation and context key sanitization.

All collection fields in dataclasses use tuples for true deep immutability.
Use ``dataclasses.replace()`` to create modified copies.
"""

import json
import re
from dataclasses import dataclass
from typing import Any, Literal, Protocol, runtime_checkable

from startd8.contractors.modes import ExecutionMode, ModeConfig

__all__ = [
    "MAX_PATH_DEPTH",
    "MAX_CONTEXT_SIZE_BYTES",
    "SAFE_PATH_PATTERN",
    "validate_path_safe",
    "sanitize_context_keys",
    "ContextResolutionError",
    "SeedContextError",
    "TaskContextError",
    "ValidationConfigError",
    "ValidationResult",
    "ValidationConfig",
    "ContextResolutionStrategy",
]

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_PATH_DEPTH: int = 10
"""Maximum directory traversal depth, counted as number of ``/`` separators."""

MAX_CONTEXT_SIZE_BYTES: int = 1_048_576  # 1 MiB
"""Upper bound on context payload size to prevent resource exhaustion."""

SAFE_PATH_PATTERN: re.Pattern[str] = re.compile(
    r"^[a-zA-Z0-9_\-][a-zA-Z0-9_\-./]*$"
)
"""Regex for POSIX-style relative path validation.

Must start with alphanumeric, underscore, or hyphen.  Body may also contain
dots and forward slashes.  Rejects absolute paths, hidden files, shell
metacharacters, backslashes, Unicode, and spaces.
"""

# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------


def validate_path_safe(path: str) -> bool:
    """Check that a path string is safe for use within a project scope.

    Returns ``True`` if the path:

    - Is non-empty and contains no whitespace-only segments.
    - Matches :data:`SAFE_PATH_PATTERN` (must start with alphanumeric,
      underscore, or hyphen; body may also contain dots and forward slashes).
    - Contains no ``..`` segments (parent traversal).
    - Contains no ``.`` segments (current-directory reference, ambiguous).
    - Contains no null bytes.
    - Is a relative path (no leading ``/``).
    - Does not exceed :data:`MAX_PATH_DEPTH` directory levels (counted as
      number of ``/`` characters).

    This function is designed for POSIX-style relative paths only.  It
    intentionally rejects absolute paths, Windows backslash paths, Unicode
    filenames, spaces, and dot-prefixed path segments.
    """
    if not path or not path.strip():
        return False
    if "\x00" in path:
        return False
    if path.startswith("/"):
        return False
    if not SAFE_PATH_PATTERN.match(path):
        return False
    segments = path.split("/")
    for segment in segments:
        if segment == ".." or segment == ".":
            return False
        if segment == "":
            # Consecutive slashes produce empty segments.
            return False
    if path.count("/") > MAX_PATH_DEPTH:
        return False
    return True


def sanitize_context_keys(context: dict[str, Any]) -> dict[str, Any]:
    """Return a shallow copy of *context* with keys sanitized.

    Removes keys that:

    - Start with ``__`` (dunder — potential injection vector).
    - Contain null bytes.
    - Are not strings.

    Raises:
        ValueError: If total serialized size exceeds
            :data:`MAX_CONTEXT_SIZE_BYTES`, or if the context cannot be
            serialized for size measurement (fail-closed policy).

    .. important::

       This function sanitizes **keys only**, not values.  Value sanitization
       is domain-specific and is the responsibility of downstream validators
       configured via :class:`ValidationConfig`.  Callers **must not** assume
       that a dict passing this function has safe values.
    """
    sanitized = {
        k: v
        for k, v in context.items()
        if isinstance(k, str) and not k.startswith("__") and "\x00" not in k
    }

    # Size check: approximate via JSON serialization.
    # Uses ``json.dumps(default=str)`` to handle non-serializable types.
    try:
        size = len(json.dumps(sanitized, default=str).encode("utf-8"))
    except (TypeError, ValueError, OverflowError, RecursionError) as exc:
        # Fail closed: if we cannot measure the payload, reject it.
        raise ValueError(
            f"Context size cannot be measured due to serialization failure: {exc}. "
            f"Payload rejected (fail-closed)."
        ) from exc

    if size > MAX_CONTEXT_SIZE_BYTES:
        raise ValueError(
            f"Context size {size} bytes exceeds maximum {MAX_CONTEXT_SIZE_BYTES} bytes"
        )
    return sanitized


# ---------------------------------------------------------------------------
# Exception hierarchy
# ---------------------------------------------------------------------------


class ContextResolutionError(Exception):
    """Base exception for all context resolution failures.

    Attributes:
        message: Human-readable error description.
        context: Optional dict of diagnostic information.
    """

    def __init__(self, message: str, context: dict[str, Any] | None = None) -> None:
        self.message = message
        self.context = context or {}
        super().__init__(self.message)


class SeedContextError(ContextResolutionError):
    """Raised when seed context resolution fails.

    Typical causes: invalid ``ExecutionMode``, missing configuration,
    inaccessible pipeline state.
    """

    pass


class TaskContextError(ContextResolutionError):
    """Raised when task-level context resolution fails.

    Typical causes: unknown ``task_id``, invalid ``seed_context`` structure,
    path traversal attempt in task references.
    """

    pass


class ValidationConfigError(ContextResolutionError):
    """Raised when validation configuration cannot be resolved.

    Typical causes: unknown validators referenced, incompatible
    mode/validator combination.
    """

    pass


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ValidationResult:
    """Result of a single validator's execution against generated output.

    Attributes:
        validator_name: Identifier of the validator that produced this result.
        severity: Impact level — ``"error"`` blocks pipeline, ``"warning"`` is
            advisory, ``"info"`` is diagnostic.
        findings: Tuple of human-readable finding descriptions.  Tuple (not
            list) ensures true deep immutability.
        passed: Whether the validator considers the output acceptable.
        metadata: Tuple of ``(key, value)`` pairs for provenance/diagnostics.
            Use ``dict(result.metadata)`` to convert for dict-style access.

    Immutability:
        This dataclass is frozen with all collection fields stored as tuples.
        To create a modified copy use ``dataclasses.replace()``::

            from dataclasses import replace
            new_result = replace(old_result, severity="warning",
                                 findings=old_result.findings + ("additional",))
    """

    validator_name: str
    severity: Literal["error", "warning", "info"]
    findings: tuple[str, ...] = ()
    passed: bool = True
    metadata: tuple[tuple[str, Any], ...] = ()

    def __post_init__(self) -> None:
        if not self.validator_name:
            raise ValueError("validator_name must be a non-empty string")
        if self.severity not in ("error", "warning", "info"):
            raise ValueError(
                f"severity must be 'error', 'warning', or 'info', got '{self.severity}'"
            )
        # Coerce findings from list → tuple when needed.
        if not isinstance(self.findings, tuple):
            object.__setattr__(self, "findings", tuple(self.findings))
        # Coerce metadata from dict/list → tuple-of-tuples when needed.
        if not isinstance(self.metadata, tuple):
            if isinstance(self.metadata, dict):
                object.__setattr__(self, "metadata", tuple(self.metadata.items()))
            else:
                object.__setattr__(self, "metadata", tuple(self.metadata))


@dataclass(frozen=True, slots=True)
class ValidationConfig:
    """Configuration for post-generation validation of a task's output.

    Attributes:
        validators: Ordered tuple of validator names to execute.
        fail_on_error: If ``True``, an ``"error"``-severity
            :class:`ValidationResult` causes the pipeline to halt.
        timeout_seconds: Maximum wall-clock time for all validators combined.
        extra: Tuple of ``(key, value)`` pairs for validator-specific
            configuration.  Use ``dict(config.extra)`` for dict-style access.

    Immutability:
        This dataclass is frozen with all collection fields stored as tuples.
        To create a modified copy use ``dataclasses.replace()``::

            from dataclasses import replace
            new_config = replace(old_config, fail_on_error=False)

    Thread Safety:
        Instances are immutable and safe to share across threads without
        synchronization, provided the values within *extra* tuples are
        themselves immutable or not concurrently mutated.
    """

    validators: tuple[str, ...] = ()
    fail_on_error: bool = True
    timeout_seconds: float = 30.0
    extra: tuple[tuple[str, Any], ...] = ()

    def __post_init__(self) -> None:
        if self.timeout_seconds <= 0:
            raise ValueError(
                f"timeout_seconds must be positive, got {self.timeout_seconds}"
            )
        # Coerce validators from list → tuple when needed.
        if not isinstance(self.validators, tuple):
            object.__setattr__(self, "validators", tuple(self.validators))
        for v in self.validators:
            if not isinstance(v, str) or not v.strip():
                raise ValueError(
                    f"Each validator must be a non-empty string, got {v!r}"
                )
        # Coerce extra from dict/list → tuple-of-tuples when needed.
        if not isinstance(self.extra, tuple):
            if isinstance(self.extra, dict):
                object.__setattr__(self, "extra", tuple(self.extra.items()))
            else:
                object.__setattr__(self, "extra", tuple(self.extra))

    def has_validators(self) -> bool:
        """Return ``True`` if at least one validator is configured.

        Convenience method for mode-aware checks.  In standalone mode,
        implementations typically return ``ValidationConfig()`` with an empty
        validators tuple, and callers can use this to skip validation::

            config = strategy.resolve_validation_config(mode, task_id)
            if config.has_validators():
                run_validators(config)
        """
        return len(self.validators) > 0


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class ContextResolutionStrategy(Protocol):
    """Strategy protocol for resolving pipeline context at different granularities.

    Implementations provide mode-aware context resolution:

    - **Standalone mode** returns minimal/default contexts.
    - **Orchestrated mode** exploits rich pipeline state.

    All methods **must** raise their specific exception subclass on failure
    (never a bare ``Exception`` or :class:`ContextResolutionError`).

    Thread Safety:
        The protocol itself is stateless.  Implementations **should** be safe
        for concurrent use from multiple threads.  If an implementation
        maintains internal mutable state (e.g. caches), it **must** document
        its thread-safety guarantees and provide its own synchronization.

    Documentation-Only Contracts:
        - Exception specificity: each method raises only its designated
          exception subclass.
        - No secrets in exception context dicts.
        - Returned dicts should pass :func:`sanitize_context_keys`.
    """

    def resolve_seed_context(
        self, mode: ExecutionMode, config: ModeConfig
    ) -> dict[str, Any]:
        """Resolve the initial seed context for a pipeline run.

        Args:
            mode: Current execution mode (from PI-001).
            config: Mode-specific configuration (from PI-001).

        Returns:
            A dict of seed context key-value pairs.  The returned dict
            **must** pass :func:`sanitize_context_keys` without raising
            ``ValueError``.

        Raises:
            SeedContextError: On any failure to resolve seed context.
                Must include ``'mode'`` in the exception's context dict.
        """
        ...

    def resolve_task_context(
        self, seed_context: dict[str, Any], task_id: str
    ) -> dict[str, Any]:
        """Resolve context specific to an individual task.

        Args:
            seed_context: The seed context returned by
                :meth:`resolve_seed_context`.
            task_id: Identifier of the task being executed.  Must pass
                :func:`validate_path_safe` if it contains path-like components.

        Returns:
            A dict of task-specific context.  Superset of *seed_context*
            is **not** required — task context is independent.

        Raises:
            TaskContextError: On any failure including invalid *task_id*
                or path traversal attempts.  Must include ``'task_id'`` in the
                exception's context dict.
        """
        ...

    def resolve_validation_config(
        self, mode: ExecutionMode, task_id: str
    ) -> ValidationConfig:
        """Resolve validation configuration for a specific task.

        Args:
            mode: Current execution mode.
            task_id: Identifier of the task whose output will be validated.

        Returns:
            A :class:`ValidationConfig` instance.  In standalone mode,
            implementations **should** return ``ValidationConfig()`` (empty
            validators tuple) to preserve exact standalone behaviour.

        Raises:
            ValidationConfigError: On any failure to resolve configuration.
                Must include both ``'mode'`` and ``'task_id'`` in the
                exception's context dict.
        """
        ...