"""LanguageRegistry — singleton registry keyed by language ID.

Modeled on ProviderRegistry: thread-safe, supports entry point discovery
for third-party language providers.
"""

from __future__ import annotations

import logging
import sys
import threading
from typing import ClassVar, Dict, List, Optional

from .protocol import LanguageProfile

logger = logging.getLogger(__name__)

# Entry point group name for third-party language profiles
EP_LANGUAGES = "startd8.languages"


class LanguageRegistry:
    """Central registry for language profiles.

    Thread-safe singleton supporting both programmatic registration and
    auto-discovery via Python entry points.

    Example entry_points configuration in pyproject.toml::

        [project.entry-points."startd8.languages"]
        python = "startd8.languages.python:PythonLanguageProfile"
        go = "startd8.languages.go:GoLanguageProfile"

    Usage::

        LanguageRegistry.discover()
        profile = LanguageRegistry.get("python")
        profile = LanguageRegistry.get_default()  # always Python
    """

    _instance: ClassVar[Optional[LanguageRegistry]] = None
    _lock: ClassVar[threading.Lock] = threading.Lock()
    # Shared singleton state — intentionally class-level (not instance).
    # All access goes through the singleton; clear() resets for testing.
    _profiles: ClassVar[Dict[str, LanguageProfile]] = {}
    _discovered: ClassVar[bool] = False

    def __new__(cls) -> LanguageRegistry:
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    @classmethod
    def register(cls, profile: LanguageProfile) -> None:
        """Register a language profile instance.

        Args:
            profile: Instance implementing LanguageProfile protocol.

        Raises:
            TypeError: If profile doesn't satisfy LanguageProfile.
        """
        if not isinstance(profile, LanguageProfile):
            raise TypeError(
                f"{profile} does not implement LanguageProfile protocol"
            )

        lang_id = profile.language_id.lower()
        with cls._lock:
            if lang_id in cls._profiles:
                logger.warning("Overwriting existing language profile: %s", lang_id)
            cls._profiles[lang_id] = profile
            logger.info(
                "Registered language profile: %s (%s) extensions=%s",
                lang_id, profile.display_name, profile.source_extensions,
            )

    @classmethod
    def discover(cls, force: bool = False) -> None:
        """Auto-discover language profiles via entry points and built-ins."""
        with cls._lock:
            if cls._discovered and not force:
                return

        discovered_count = 0
        try:
            if sys.version_info >= (3, 10):
                from importlib.metadata import entry_points
                try:
                    eps = entry_points(group=EP_LANGUAGES)
                except TypeError:
                    eps = entry_points().get(EP_LANGUAGES, [])
            else:
                try:
                    from importlib_metadata import entry_points
                    eps = entry_points().get(EP_LANGUAGES, [])
                except ImportError:
                    eps = []

            for ep in eps:
                try:
                    profile_class = ep.load()
                    profile = profile_class()
                    cls.register(profile)
                    discovered_count += 1
                except (ImportError, AttributeError, TypeError) as e:
                    logger.warning("Failed to load language profile %s: %s", ep.name, e)
                except Exception as e:
                    logger.warning("Unexpected error loading language profile %s: %s", ep.name, e)
        except (ImportError, AttributeError) as e:
            logger.debug("Language entry point discovery failed: %s", e)

        cls._register_builtins()

        with cls._lock:
            cls._discovered = True

        logger.info(
            "Language discovery complete: %d external, %d total",
            discovered_count, len(cls._profiles),
        )

    @classmethod
    def _register_builtins(cls) -> None:
        """Register built-in language profiles."""
        with cls._lock:
            already = set(cls._profiles.keys())

        # Python (always available, default)
        if "python" not in already:
            try:
                from .python import PythonLanguageProfile
                cls.register(PythonLanguageProfile())
            except ImportError:
                logger.debug("PythonLanguageProfile not available")

        # Go
        if "go" not in already:
            try:
                from .go import GoLanguageProfile
                cls.register(GoLanguageProfile())
            except ImportError:
                logger.debug("GoLanguageProfile not available")

        # Node.js
        if "nodejs" not in already:
            try:
                from .nodejs import NodeLanguageProfile
                cls.register(NodeLanguageProfile())
            except ImportError:
                logger.debug("NodeLanguageProfile not available")

        # Java
        if "java" not in already:
            try:
                from .java import JavaLanguageProfile
                cls.register(JavaLanguageProfile())
            except ImportError:
                logger.debug("JavaLanguageProfile not available")

        # C#
        if "csharp" not in already:
            try:
                from .csharp import CSharpLanguageProfile
                cls.register(CSharpLanguageProfile())
            except ImportError:
                logger.debug("CSharpLanguageProfile not available")

    @classmethod
    def get(cls, language_id: str) -> Optional[LanguageProfile]:
        """Get language profile by ID (case-insensitive)."""
        cls.discover()
        return cls._profiles.get(language_id.lower())

    @classmethod
    def get_default(cls) -> LanguageProfile:
        """Get the default language profile (Python).

        Falls back to Python for backward compatibility.
        """
        cls.discover()
        profile = cls._profiles.get("python")
        if profile is None:
            # Should never happen — Python is a built-in
            raise RuntimeError("No default language profile (Python) registered")
        return profile

    @classmethod
    def list_languages(cls) -> List[str]:
        """List all registered language IDs."""
        cls.discover()
        with cls._lock:
            return list(cls._profiles.keys())

    @classmethod
    def get_by_extension(cls, ext: str) -> Optional[LanguageProfile]:
        """Find a language profile that handles the given file extension.

        Args:
            ext: File extension including dot (e.g. '.py', '.go').

        Returns:
            Matching profile, or None.
        """
        cls.discover()
        ext_lower = ext.lower()
        with cls._lock:
            for profile in cls._profiles.values():
                if profile.supports_extension(ext_lower):
                    return profile
        return None

    @classmethod
    def get_extension_map(cls) -> Dict[str, str]:
        """Canonical extension->language_id mapping from all registered profiles.

        Calls :meth:`discover` on first access.  The mapping is computed
        from each profile's ``source_extensions`` property.

        Returns:
            Dict mapping file extensions (with dot, e.g. ``'.py'``) to
            language IDs (e.g. ``'python'``).
        """
        cls.discover()
        mapping: Dict[str, str] = {}
        with cls._lock:
            for profile in cls._profiles.values():
                for ext in profile.source_extensions:
                    mapping[ext] = profile.language_id
        return mapping

    @classmethod
    def clear(cls) -> None:
        """Clear all registered profiles (useful for testing)."""
        with cls._lock:
            cls._profiles.clear()
            cls._discovered = False
