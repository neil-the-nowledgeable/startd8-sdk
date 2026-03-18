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


def resolve_language(
    target_files: Optional[List[str]] = None,
    *,
    default_id: str = "python",
) -> LanguageProfile:
    """Select the dominant language profile from *target_files*."""
    if not target_files:
        profile = LanguageRegistry.get(default_id)
        if profile is None:
            LanguageRegistry.discover()
            profile = LanguageRegistry.get(default_id)
        return profile or LanguageRegistry.get_default()

    ext_map = LanguageRegistry.get_extension_map()
    counts: Counter = Counter()
    for fpath in target_files:
        ext = Path(fpath).suffix.lower()
        lang_id = ext_map.get(ext)
        if lang_id:
            counts[lang_id] += 1

    if not counts:
        return LanguageRegistry.get(default_id) or LanguageRegistry.get_default()

    dominant_id = counts.most_common(1)[0][0]
    profile = LanguageRegistry.get(dominant_id)
    if profile is None:
        logger.warning(
            "resolve_language: no profile for dominant language %r, falling back to %s",
            dominant_id,
            default_id,
        )
        return LanguageRegistry.get(default_id) or LanguageRegistry.get_default()
    return profile
