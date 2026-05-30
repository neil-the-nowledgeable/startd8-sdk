"""User model overlay store.

A manual, persistent, user-owned model list that complements API discovery
(``model_discovery.py``) and the curated provider baselines
(``<Provider>.HARDCODED_MODELS``). Backs the TUI "Manage Models" feature
(REQ-TMM-100..107, 110/111) and the ``model_catalog`` overlay (REQ-TMM-130/131).

The store persists to ``~/.startd8/user_models.json`` — a dedicated, global file
kept separate from ``discovered_models.json`` so the 24h discovery refresh never
clobbers manual entries (REQ-TMM-104). It reuses :class:`_JsonFileStore` for
atomic writes and malformed-file recovery (REQ-TMM-106, PL-TMM-1).
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .logging_config import get_logger
from .model_discovery import _JsonFileStore

logger = get_logger(__name__)

SCHEMA_VERSION = 1

# Tier vocabulary shared with model_catalog._MODEL_REGISTRY / ModelInfo.tier.
VALID_TIERS = {"flagship", "balanced", "fast", "mini", "reasoning"}
DEFAULT_CAPABILITIES: List[str] = ["text", "code"]

_MAX_MODEL_ID_LEN = 200
# Reject C0/C1 control chars (incl. newlines/tabs), DEL, and the provider
# separator ':' (which would corrupt "provider:model" specs and questionary
# choice lists). '/' is intentionally allowed — many valid ids contain it
# (e.g. "nvidia/nemotron-3-nano-30b-a3b", "meta-llama/Llama-3.3-70B").
_FORBIDDEN_RE = re.compile(r"[\x00-\x1f\x7f:]")


class ModelIdError(ValueError):
    """A model_id or tier failed normalization/validation (REQ-TMM-107)."""


class ModelCollisionError(ValueError):
    """An edit would collide with an existing id (REQ-TMM-103)."""


def normalize_model_id(model_id: Any) -> str:
    """Trim and validate a model id (REQ-TMM-107).

    Rejects non-strings, empty/whitespace, over-long (>200), and ids containing
    control chars, newlines, or the ':' provider separator.
    """
    if not isinstance(model_id, str):
        raise ModelIdError(f"model_id must be a string, got {type(model_id).__name__}")
    trimmed = model_id.strip()
    if not trimmed:
        raise ModelIdError("model_id must be non-empty")
    if len(trimmed) > _MAX_MODEL_ID_LEN:
        raise ModelIdError(f"model_id exceeds {_MAX_MODEL_ID_LEN} characters")
    if _FORBIDDEN_RE.search(trimmed):
        raise ModelIdError("model_id contains control characters, newlines, or ':'")
    return trimmed


def normalize_tier(tier: Any) -> str:
    """Lowercase + validate a tier against :data:`VALID_TIERS`."""
    if not isinstance(tier, str) or tier.strip().lower() not in VALID_TIERS:
        raise ModelIdError(f"tier must be one of {sorted(VALID_TIERS)}, got {tier!r}")
    return tier.strip().lower()


class UserModelStore:
    """CRUD over the user-owned model overlay (REQ-TMM-101..107, 131)."""

    CONFIG_FILENAME = "user_models.json"

    def __init__(self, config_dir: Optional[Path] = None):
        self._store = _JsonFileStore(config_dir, self.CONFIG_FILENAME)
        self.config_dir = self._store.config_dir
        self.config_file = self._store.config_file

    # -- internal state ----------------------------------------------------

    def _empty(self) -> Dict[str, Any]:
        return {
            "version": SCHEMA_VERSION,
            "last_updated": None,
            "models": {},
            "suppressed": {},
        }

    def _migrate(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Forward-compatible schema migration scaffold (R1-S9).

        Only v1 exists today. A file from a *newer* schema is read best-effort
        with a warning rather than treated as corrupt; a future v2 reader would
        perform the v1->v2 upgrade here.
        """
        version = data.get("version", SCHEMA_VERSION)
        if not isinstance(version, int):
            version = SCHEMA_VERSION
        if version > SCHEMA_VERSION:
            logger.warning(
                "user_models.json schema version %s > supported %s; reading best-effort",
                version,
                SCHEMA_VERSION,
            )
        data["version"] = SCHEMA_VERSION
        return data

    def _load(self) -> Dict[str, Any]:
        """Load with malformed-file recovery (REQ-TMM-106) + migration."""
        data = self._migrate(self._store.load_raw(default=self._empty()))
        if not isinstance(data.get("models"), dict):
            data["models"] = {}
        if not isinstance(data.get("suppressed"), dict):
            data["suppressed"] = {}
        return data

    def _save(self, data: Dict[str, Any]) -> bool:
        data["version"] = SCHEMA_VERSION
        data["last_updated"] = datetime.now(timezone.utc).isoformat()
        return self._store.save_raw(data)

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    # -- CRUD --------------------------------------------------------------

    def add(
        self,
        provider: str,
        model_id: str,
        *,
        tier: str,
        capabilities: Optional[List[str]] = None,
        source: str = "manual",
    ) -> Dict[str, Any]:
        """Idempotent upsert of a user model; clears any suppression (REQ-TMM-101/102)."""
        provider = provider.lower()
        model_id = normalize_model_id(model_id)
        tier = normalize_tier(tier)
        caps = list(capabilities) if capabilities else list(DEFAULT_CAPABILITIES)

        data = self._load()  # reload-before-write (R1-S4)
        models = data["models"].setdefault(provider, [])
        existing = next((m for m in models if m.get("model_id") == model_id), None)
        if existing is not None:
            existing.update({"tier": tier, "capabilities": caps, "source": source})
            record = existing
        else:
            record = {
                "model_id": model_id,
                "tier": tier,
                "capabilities": caps,
                "added_at": self._now(),
                "source": source,
            }
            models.append(record)

        # Resurrection: re-adding a suppressed id un-hides it (REQ-TMM-102).
        suppressed = data["suppressed"].get(provider, [])
        if model_id in suppressed:
            suppressed.remove(model_id)
            data["suppressed"][provider] = suppressed

        self._save(data)
        return record

    def remove(self, provider: str, model_id: str) -> str:
        """Remove a user model, else suppress a baseline/discovered id (REQ-TMM-102).

        Returns one of ``"removed"`` | ``"suppressed"`` | ``"noop"``.
        """
        provider = provider.lower()
        model_id = normalize_model_id(model_id)
        data = self._load()
        models = data["models"].get(provider, [])
        idx = next(
            (i for i, m in enumerate(models) if m.get("model_id") == model_id), None
        )
        if idx is not None:
            models.pop(idx)
            self._save(data)
            return "removed"

        suppressed = data["suppressed"].setdefault(provider, [])
        if model_id not in suppressed:
            suppressed.append(model_id)
            self._save(data)
            return "suppressed"
        return "noop"

    def edit(
        self,
        provider: str,
        model_id: str,
        *,
        new_id: Optional[str] = None,
        tier: Optional[str] = None,
        capabilities: Optional[List[str]] = None,
        collision_check: Optional[Callable[[str, str], bool]] = None,
    ) -> Dict[str, Any]:
        """Edit a user model's id/tier/capabilities (REQ-TMM-103).

        Renaming to an id that already exists is rejected. Collisions within the
        user list are always checked; cross-source collisions (baseline/
        discovered) are checked via the optional ``collision_check(provider,
        new_id) -> bool`` callback so this module stays decoupled from the
        provider/catalog layers (avoids a circular import).
        """
        provider = provider.lower()
        model_id = normalize_model_id(model_id)
        data = self._load()
        models = data["models"].get(provider, [])
        record = next((m for m in models if m.get("model_id") == model_id), None)
        if record is None:
            raise ModelIdError(
                f"no user model '{model_id}' for provider '{provider}'"
            )

        if new_id is not None:
            new_id = normalize_model_id(new_id)
            if new_id != model_id:
                clash = any(m.get("model_id") == new_id for m in models)
                if not clash and collision_check is not None:
                    clash = bool(collision_check(provider, new_id))
                if clash:
                    raise ModelCollisionError(
                        f"cannot rename '{model_id}' to '{new_id}': id already exists"
                    )
                record["model_id"] = new_id

        if tier is not None:
            record["tier"] = normalize_tier(tier)
        if capabilities is not None:
            record["capabilities"] = list(capabilities)

        self._save(data)
        return record

    def list(self, provider: str) -> List[Dict[str, Any]]:
        """User model records for a provider (copy)."""
        return list(self._load()["models"].get(provider.lower(), []))

    def suppressed(self, provider: str) -> List[str]:
        """Suppressed (hidden) baseline/discovered ids for a provider (copy)."""
        return list(self._load()["suppressed"].get(provider.lower(), []))

    # -- reconciliation ----------------------------------------------------

    def merge_view(
        self,
        provider: str,
        baseline: List[str],
        discovered: List[str],
    ) -> List[Dict[str, Any]]:
        """Single de-duplicated, origin-annotated list (REQ-TMM-131).

        Precedence user-added > discovered > baseline governs both the origin
        label and (for user entries) the metadata. Suppressed baseline/
        discovered ids are hidden (REQ-TMM-102).
        """
        provider = provider.lower()
        data = self._load()
        suppressed = set(data["suppressed"].get(provider, []))
        out: List[Dict[str, Any]] = []
        seen: set[str] = set()

        for rec in data["models"].get(provider, []):
            mid = rec.get("model_id")
            if not mid or mid in seen:
                continue
            out.append(
                {
                    "model_id": mid,
                    "origin": "user-added",
                    "tier": rec.get("tier"),
                    "capabilities": rec.get("capabilities"),
                    "source": rec.get("source"),
                }
            )
            seen.add(mid)

        for mid in discovered:
            if mid in seen or mid in suppressed:
                continue
            out.append({"model_id": mid, "origin": "discovered"})
            seen.add(mid)

        for mid in baseline:
            if mid in seen or mid in suppressed:
                continue
            out.append({"model_id": mid, "origin": "baseline"})
            seen.add(mid)

        return out

    def as_catalog_overlay(self) -> Dict[str, Dict[str, Any]]:
        """Overlay consumable by ``model_catalog`` (REQ-TMM-130).

        Returns ``{model_id: {"provider", "tier", "capabilities"}}`` for user
        models with a *valid* tier only. Records with an invalid tier are
        dropped with a warning so routing never trusts a bad tier (R1-S3).
        """
        data = self._load()
        overlay: Dict[str, Dict[str, Any]] = {}
        for provider, records in data["models"].items():
            for rec in records:
                mid = rec.get("model_id")
                tier = rec.get("tier")
                if not mid:
                    continue
                if tier not in VALID_TIERS:
                    logger.warning(
                        "user model '%s' has invalid tier %r; excluding from catalog overlay",
                        mid,
                        tier,
                    )
                    continue
                overlay[mid] = {
                    "provider": provider,
                    "tier": tier,
                    "capabilities": set(rec.get("capabilities") or DEFAULT_CAPABILITIES),
                }
        return overlay


__all__ = [
    "UserModelStore",
    "ModelIdError",
    "ModelCollisionError",
    "normalize_model_id",
    "normalize_tier",
    "VALID_TIERS",
    "DEFAULT_CAPABILITIES",
    "SCHEMA_VERSION",
]
