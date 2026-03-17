"""Language resolution — given target_files, resolve to dominant LanguageProfile.

Falls back to Python for backward compatibility.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import List, Optional

from ..logging_config import get_logger
from .protocol import LanguageProfile
from .registry import LanguageRegistry

logger = get_logger(__name__)

# Extension → language ID mapping (covers the 4 target languages + common extras)
_EXT_TO_LANGUAGE_ID: dict[str, str] = {
    ".py": "python",
    ".pyw": "python",
    ".go": "go",
    ".js": "nodejs",
    ".mjs": "nodejs",
    ".cjs": "nodejs",
    ".ts": "nodejs",
    ".tsx": "nodejs",
    ".java": "java",
}


def resolve_language(
    target_files: Optional[List[str]] = None,
    *,
    default_id: str = "python",
) -> LanguageProfile:
    """Resolve the dominant language profile from a list of target files.

    Strategy:
    1. Count file extensions across target_files.
    2. Map each extension to a language ID.
    3. Return the profile for the most common language.
    4. Fall back to *default_id* (Python) if no files or unknown extensions.

    Args:
        target_files: List of relative file paths.
        default_id: Fallback language ID when resolution fails.

    Returns:
        LanguageProfile for the dominant language.
    """
    if not target_files:
        profile = LanguageRegistry.get(default_id) or LanguageRegistry.get_default()
        logger.debug("No target files — using default language: %s", profile.language_id)
        return profile

    # Count language IDs by extension
    lang_counts: Counter[str] = Counter()
    for tf in target_files:
        ext = Path(tf).suffix.lower()
        if not ext:
            continue
        lang_id = _EXT_TO_LANGUAGE_ID.get(ext)
        if lang_id:
            lang_counts[lang_id] += 1
        else:
            # Try registry lookup by extension
            profile = LanguageRegistry.get_by_extension(ext)
            if profile:
                lang_counts[profile.language_id] += 1

    if not lang_counts:
        profile = LanguageRegistry.get(default_id) or LanguageRegistry.get_default()
        logger.debug(
            "No recognized extensions in target_files — using default: %s",
            profile.language_id,
        )
        return profile

    dominant_id = lang_counts.most_common(1)[0][0]
    profile = LanguageRegistry.get(dominant_id)
    if profile is None:
        profile = LanguageRegistry.get(default_id) or LanguageRegistry.get_default()
        logger.warning(
            "Dominant language '%s' not registered — falling back to %s",
            dominant_id, profile.language_id,
        )
    else:
        logger.info(
            "Resolved language: %s (from %d files, counts=%s)",
            profile.language_id, len(target_files), dict(lang_counts),
        )

    return profile
