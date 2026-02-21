"""Feature queue with metadata preservation across serialization boundaries.

This module provides :class:`FeatureItem` (a dataclass) and :class:`FeatureQueue`
(a FIFO queue) that together ensure all enrichment metadata — execution mode,
generation provenance, validation config, context strategy, mode config, and
security flags — survives serialization/deserialization across queue boundaries.

**Metadata preservation, not validation enforcement:** this module does not
validate enum values for ``execution_mode`` or enforce schemas on enrichment
dicts. Downstream consumers are responsible for semantic validation. In
particular, ``security_flags`` is a metadata carrier — prompt injection
detection is handled downstream.

Schema version: 1.0
"""

from __future__ import annotations

import collections
import copy
import dataclasses
import datetime
import logging
import re
import uuid
from typing import Any, Iterator

# ---------------------------------------------------------------------------
# Constants / sentinel values
# ---------------------------------------------------------------------------

METADATA_VERSION: str = "1.0"
"""Serialization schema version tag embedded in :meth:`FeatureQueue.to_dict` output."""

METADATA_MAJOR_VERSION: int = 1
"""Parsed major component of :data:`METADATA_VERSION`; used for compatibility checks."""

EXTRA_METADATA_KEY: str = "extra_metadata"
"""Dict key name in serialized output for forward-compatible extra fields."""

ENRICHMENT_FIELDS: tuple[str, ...] = (
    "execution_mode",
    "generation_provenance",
    "validation_config",
    "context_strategy",
    "mode_config",
    "security_flags",
)
"""Enrichment field names that :meth:`FeatureQueue.add_features_from_seed` propagates."""

logger: logging.Logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class MetadataVersionError(Exception):
    """Raised when deserialized metadata has an incompatible major version."""


# ---------------------------------------------------------------------------
# Utility functions (defined before classes that reference them)
# ---------------------------------------------------------------------------


def _generate_id() -> str:
    """Generate a unique feature-item ID (UUID v4)."""
    return str(uuid.uuid4())


def _now_iso() -> str:
    """Return the current UTC timestamp in ISO-8601 format."""
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _sanitize_name(name: str) -> str:
    """Allowlist-based sanitization for feature names.

    Processing steps:

    1. Replace path separators (``/``, ``\\``, Unicode fullwidth variants
       ``U+FF0F``, ``U+FF3C``) and null bytes with underscores.
    2. Collapse ``..`` sequences to a single ``_`` (path-traversal protection).
    3. Replace any character **not** in ``[a-zA-Z0-9_\\-\\.]`` with ``_``.
    4. Collapse runs of underscores to one; strip leading/trailing ``_`` and ``.``.
    5. Raise :class:`ValueError` if the result is empty.

    This function is **idempotent**:
    ``_sanitize_name(_sanitize_name(x)) == _sanitize_name(x)`` for all inputs.
    """
    # Step 1 — dangerous separators (ASCII + Unicode fullwidth)
    for char in ("/", "\\", "\x00", "\uff0f", "\uff3c"):
        name = name.replace(char, "_")

    # Step 2 — collapse '..' path-traversal sequences
    while ".." in name:
        name = name.replace("..", "_")

    # Step 3 — remove characters outside the allowlist
    name = re.sub(r"[^a-zA-Z0-9_\-\.]", "_", name)

    # Step 4 — collapse multiple underscores; strip edges
    name = re.sub(r"_+", "_", name)
    name = name.strip("_.")

    if not name:
        raise ValueError(
            "Invalid feature name: results in empty string after sanitization"
        )

    return name


def _parse_major_version(version_str: str) -> int:
    """Extract the integer major version from a ``"MAJOR.MINOR"`` string.

    Raises:
        MetadataVersionError: If *version_str* cannot be parsed.
    """
    try:
        return int(version_str.split(".")[0])
    except (ValueError, IndexError, AttributeError):
        raise MetadataVersionError(
            f"Cannot parse metadata version: {version_str!r}"
        )


# ---------------------------------------------------------------------------
# FeatureItem dataclass
# ---------------------------------------------------------------------------


@dataclasses.dataclass
class FeatureItem:
    """A single feature item with core fields and optional enrichment metadata.

    Enrichment fields carry pipeline context (execution mode, validation config,
    security flags, etc.) that must survive serialization across queue boundaries.

    This class does **not** validate the semantic content of enrichment fields
    (e.g. whether *execution_mode* is a valid enum value).  Downstream consumers
    are responsible for semantic validation.  In particular, *security_flags* is
    a metadata carrier — prompt-injection detection is handled downstream.
    """

    # -- Core fields --------------------------------------------------------
    name: str
    description: str = ""
    id: str = dataclasses.field(default_factory=_generate_id)
    created_at: str = dataclasses.field(default_factory=_now_iso)

    # -- Enrichment fields (None ⇒ "not set / standalone default") ----------
    execution_mode: str | None = None
    generation_provenance: dict | None = None
    validation_config: dict | None = None
    context_strategy: str | None = None
    mode_config: dict | None = None
    security_flags: dict | None = None

    # -- Forward-compatibility catch-all ------------------------------------
    extra_metadata: dict = dataclasses.field(default_factory=dict)

    def __post_init__(self) -> None:
        """Sanitize *name* via the allowlist filter."""
        self.name = _sanitize_name(self.name)

    # -- Serialization ------------------------------------------------------

    def to_dict(self) -> dict:
        """Lossless serialization to a JSON-safe :class:`dict`.

        ``_metadata_version`` is **not** embedded at the item level.
        The version tag lives only at the :class:`FeatureQueue` level to avoid
        redundancy and ambiguity.
        """
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> FeatureItem:
        """Reconstruct a :class:`FeatureItem` from *data*.

        Unknown keys are collected into *extra_metadata* so that no data is
        silently lost.

        ``__post_init__`` will re-run :func:`_sanitize_name` on *name*; this
        is safe because the function is idempotent.
        """
        data = dict(data)  # shallow copy — avoid mutating the caller's dict
        data.pop("_metadata_version", None)  # tolerate legacy item-level version

        known_fields = {f.name for f in dataclasses.fields(cls)}
        extra: dict = data.get(EXTRA_METADATA_KEY, {})

        # Move truly unknown keys into extra_metadata
        unknown_keys = set(data.keys()) - known_fields
        for key in unknown_keys:
            extra[key] = data.pop(key)
        data[EXTRA_METADATA_KEY] = extra

        return cls(**data)


# ---------------------------------------------------------------------------
# FeatureQueue class
# ---------------------------------------------------------------------------


class FeatureQueue:
    """FIFO queue of :class:`FeatureItem` objects that preserves all enrichment
    metadata across serialization boundaries.

    This class is a **metadata-preserving transport layer**.  It does not
    perform semantic validation of enrichment fields:

    * *execution_mode* values are not checked against a known enum.
    * *security_flags* are carried faithfully; prompt-injection detection is
      the responsibility of downstream validators.
    * *validation_config* schemas are not enforced here.

    Example::

        queue = FeatureQueue()
        queue.add_feature("auth", execution_mode="pipeline")
        item = queue.pop()                          # dequeue for processing
        serialized = queue.to_dict()                # cross-boundary transport
        restored = FeatureQueue.from_dict(serialized)
    """

    def __init__(self) -> None:
        self._items: collections.deque[FeatureItem] = collections.deque()

    # -- Dunder helpers -----------------------------------------------------

    def __repr__(self) -> str:
        return f"<FeatureQueue items={len(self._items)}>"

    def __len__(self) -> int:
        return len(self._items)

    def __iter__(self) -> Iterator[FeatureItem]:
        return iter(self._items)

    # -- Single-item convenience -------------------------------------------

    def add_feature(
        self,
        name: str,
        *,
        description: str = "",
        metadata: dict | None = None,
        execution_mode: str | None = None,
        generation_provenance: dict | None = None,
        validation_config: dict | None = None,
        context_strategy: str | None = None,
        mode_config: dict | None = None,
        security_flags: dict | None = None,
    ) -> FeatureItem:
        """Add a single feature with optional enrichment fields.

        Args:
            name: Feature name (required; will be sanitized).
            description: Human-readable description.
            metadata: Extra metadata dict assigned to *extra_metadata*.
            execution_mode: Execution-mode string.
            generation_provenance: Provenance information dict.
            validation_config: Validation configuration dict.
            context_strategy: Context-strategy name.
            mode_config: Mode configuration dict.
            security_flags: Security flags dict.

        Returns:
            The newly created :class:`FeatureItem`.
        """
        item = FeatureItem(
            name=name,
            description=description,
            execution_mode=execution_mode,
            generation_provenance=generation_provenance,
            validation_config=validation_config,
            context_strategy=context_strategy,
            mode_config=mode_config,
            security_flags=security_flags,
            extra_metadata=metadata or {},
        )
        self._items.append(item)
        return item

    # -- Bulk ingestion from seed ------------------------------------------

    def add_features_from_seed(self, seed: dict) -> list[FeatureItem]:
        """Parse *seed* into :class:`FeatureItem` instances, propagating **all**
        enrichment fields.

        Both queue-level and feature-level enrichment values are deep-copied to
        prevent shared mutable state between items or between items and the
        input seed dict.

        Seed format::

            {
                "features": [{"name": "...", "description": "...", ...}, ...],
                "execution_mode": "...",
                "generation_provenance": {...},
                "validation_config": {...},
                "context_strategy": "...",
                "mode_config": {...},
                "security_flags": {...},
            }

        Args:
            seed: A dict containing a ``"features"`` list and optional
                enrichment keys.

        Returns:
            List of newly created :class:`FeatureItem` instances.

        Raises:
            TypeError: If *seed* is not a :class:`dict`.
            ValueError: If any feature name sanitizes to an empty string.
        """
        if not isinstance(seed, dict):
            raise TypeError(f"seed must be a dict, got {type(seed).__name__}")

        # Queue-level enrichment defaults (deep-copied to isolate from input)
        queue_defaults: dict[str, Any] = {}
        for field_name in ENRICHMENT_FIELDS:
            value = seed.get(field_name)
            if value is not None:
                queue_defaults[field_name] = copy.deepcopy(value)

        features_raw = seed.get("features", [])
        if not features_raw:
            return []

        added: list[FeatureItem] = []
        for feat_data in features_raw:
            # Deep-copy each feature dict to isolate from the input seed
            feat_data = copy.deepcopy(feat_data)

            # Merge: item-level enrichment overrides queue-level defaults
            for field_name in ENRICHMENT_FIELDS:
                if field_name not in feat_data and field_name in queue_defaults:
                    feat_data[field_name] = copy.deepcopy(queue_defaults[field_name])

            # Extract core fields
            name: str = feat_data.pop("name", "")
            description: str = feat_data.pop("description", "")

            # Collect enrichment kwargs
            enrichment_kwargs: dict[str, Any] = {}
            for field_name in ENRICHMENT_FIELDS:
                if field_name in feat_data:
                    enrichment_kwargs[field_name] = feat_data.pop(field_name)

            # Anything still remaining becomes extra_metadata
            item = FeatureItem(
                name=name,
                description=description,
                extra_metadata=feat_data if feat_data else {},
                **enrichment_kwargs,
            )
            self._items.append(item)
            added.append(item)

        return added

    # -- Dequeue operations ------------------------------------------------

    def peek(self) -> FeatureItem:
        """Return the front item **without** removing it.

        Raises:
            IndexError: If the queue is empty.
        """
        if not self._items:
            raise IndexError("peek from an empty FeatureQueue")
        return self._items[0]

    def pop(self) -> FeatureItem:
        """Remove and return the front item (FIFO order).

        Raises:
            IndexError: If the queue is empty.
        """
        if not self._items:
            raise IndexError("pop from an empty FeatureQueue")
        return self._items.popleft()

    # -- Serialization / deserialization -----------------------------------

    def to_dict(self) -> dict:
        """Serialize the entire queue to a JSON-safe :class:`dict`.

        The ``_metadata_version`` tag is embedded at the queue level **only**.

        Returns:
            A dict with keys ``"_metadata_version"`` and ``"items"``.
        """
        return {
            "_metadata_version": METADATA_VERSION,
            "items": [item.to_dict() for item in self._items],
        }

    @classmethod
    def from_dict(cls, data: dict) -> FeatureQueue:
        """Deserialize a queue from *data*, preserving all metadata.

        Version handling:

        * **Missing** ``_metadata_version`` — tolerated for backward
          compatibility with pre-versioned data.
        * **Minor** version bump (e.g. ``"1.1"`` vs ``"1.0"``) — accepted
          (minor versions are forward-compatible by convention).
        * **Major** version mismatch — :class:`MetadataVersionError` raised.

        Args:
            data: A dict with optional ``"_metadata_version"`` and ``"items"``.

        Returns:
            A new :class:`FeatureQueue` with all items restored.

        Raises:
            MetadataVersionError: On incompatible major version.
        """
        version_str = data.get("_metadata_version")
        if version_str is not None:
            incoming_major = _parse_major_version(version_str)
            if incoming_major != METADATA_MAJOR_VERSION:
                raise MetadataVersionError(
                    f"Incompatible metadata version: got {version_str!r} "
                    f"(major={incoming_major}), expected "
                    f"major={METADATA_MAJOR_VERSION}. Migration is required."
                )

        queue = cls()
        for item_data in data.get("items", []):
            queue._items.append(FeatureItem.from_dict(item_data))
        return queue