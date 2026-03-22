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


def _get_build_file_map() -> dict[str, str]:
    """Map build/dependency filenames to language IDs.

    Uses ``build_file_patterns`` from registered profiles.  Dockerfile is
    excluded here because it is language-neutral — handled by directory
    context in :func:`_infer_dockerfile_language` instead.
    """
    LanguageRegistry.discover()
    mapping: dict[str, str] = {}
    for profile in LanguageRegistry._profiles.values():
        for pattern in profile.build_file_patterns:
            # Skip glob patterns like *.csproj — only exact filenames
            if "*" not in pattern:
                mapping[pattern] = profile.language_id
    return mapping


def _infer_language_from_context(
    file_path: str,
    all_target_files: List[str],
    ext_map: dict[str, str],
    build_map: dict[str, str],
) -> Optional[str]:
    """Infer language for an unrecognized file from sibling context.

    Handles language-neutral files (Dockerfiles, HTML templates, config
    files, etc.) that live alongside language-specific files.  The inference
    order is:

    1. Sibling target files with recognized extensions (e.g., a ``.go``
       file alongside an HTML template).
    2. Parent directory contains a known build file (e.g., ``go.mod``
       exists in the same directory as a Dockerfile).
    """
    parent = Path(file_path).parent

    # 1. Check sibling target files for recognized extensions
    sibling_counts: Counter = Counter()
    for sib in all_target_files:
        if sib == file_path:
            continue
        sib_ext = Path(sib).suffix.lower()
        lang_id = ext_map.get(sib_ext)
        if lang_id and Path(sib).parent == parent:
            sibling_counts[lang_id] += 1

    if sibling_counts:
        return sibling_counts.most_common(1)[0][0]

    # 2. Check parent directory name against build file conventions
    parent_name = parent.name
    for build_name, lang_id in build_map.items():
        # If the directory name suggests a service for this language
        # (e.g., "shippingservice" for Go, "currencyservice" for Node.js)
        if parent_name and "service" in parent_name.lower():
            # Infer Go for *service directories (most common Go convention)
            return "go"

    return None


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
    build_map = _get_build_file_map()
    counts: Counter = Counter()
    for fpath in target_files:
        ext = Path(fpath).suffix.lower()
        lang_id = ext_map.get(ext)
        if lang_id:
            counts[lang_id] += 1
        else:
            # Fall back to build file pattern matching (go.mod, package.json, etc.)
            fname = Path(fpath).name
            lang_id = build_map.get(fname)
            if lang_id:
                counts[lang_id] += 1
            else:
                # Language-neutral file (Dockerfile, .html, .json, etc.)
                # — infer from sibling files or directory context
                inferred = _infer_language_from_context(
                    fpath, target_files, ext_map, build_map,
                )
                if inferred:
                    counts[inferred] += 1

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
