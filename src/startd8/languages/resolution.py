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


# Single-segment directory names that imply a specific language.
_DIR_LANGUAGE_MARKERS: dict[str, str] = {
    "gradle": "java",
}

# Well-known directory path segments that imply a specific language.
# Checked as consecutive path segment tuples.
_PATH_SEGMENT_LANGUAGES: list[tuple[tuple[str, ...], str]] = [
    # Java / Kotlin / Gradle conventions
    (("src", "main", "java"), "java"),
    (("src", "test", "java"), "java"),
    (("src", "main", "resources"), "java"),
    (("src", "test", "resources"), "java"),
    (("src", "main", "kotlin"), "java"),
    # .NET conventions
    (("Properties",), "csharp"),
]


def _get_build_file_map() -> dict[str, str]:
    """Map build/dependency filenames to language IDs.

    Uses ``build_file_patterns`` from registered profiles.  Dockerfile is
    excluded here because it is language-neutral — handled by directory
    context in :func:`_infer_language_from_context` instead.
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

    1. Sibling target files with recognized extensions in the **same
       directory** (e.g., a ``.go`` file alongside an HTML template).
    2. All other target files in the **same batch** with recognized
       extensions (cross-directory).  This handles the common case where
       a Dockerfile sits at a project root while source files are nested
       deeper (e.g., ``src/adservice/Dockerfile`` + ``src/adservice/src/
       main/java/.../Foo.java``).
    3. Directory path heuristics — files under well-known directory
       structures infer the language from the path (e.g., ``src/main/
       java/`` → Java, ``src/main/resources/`` → Java, ``gradle/`` →
       Java).
    4. Build file presence in any ancestor directory (filesystem check).
    """
    fp = Path(file_path)
    parent = fp.parent

    # Steps 1 + 2 merged: single pass with same-dir vs all-batch counters.
    same_dir_counts: Counter = Counter()
    batch_counts: Counter = Counter()
    for sib in all_target_files:
        if sib == file_path:
            continue
        sib_path = Path(sib)
        sib_ext = sib_path.suffix.lower()
        lang_id = ext_map.get(sib_ext)
        if not lang_id:
            lang_id = build_map.get(sib_path.name)
        if lang_id:
            batch_counts[lang_id] += 1
            if sib_path.parent == parent:
                same_dir_counts[lang_id] += 1

    # Prefer same-directory siblings (strongest signal)
    if same_dir_counts:
        result = same_dir_counts.most_common(1)[0][0]
        logger.debug("Language inferred from same-dir sibling: %s -> %s", file_path, result)
        return result

    if batch_counts:
        result = batch_counts.most_common(1)[0][0]
        logger.debug("Language inferred from batch siblings: %s -> %s", file_path, result)
        return result

    # 3. Directory path heuristics for well-known project structures
    parts_lower = [p.lower() for p in fp.parts]
    for segment, lang_id in _DIR_LANGUAGE_MARKERS.items():
        if segment in parts_lower:
            logger.debug("Language inferred from directory marker %r: %s -> %s", segment, file_path, lang_id)
            return lang_id

    # 4. Build file in ancestor directories (walk up from parent).
    # Only attempt filesystem checks for absolute paths — virtual/relative
    # paths from plan ingestion won't have build files on disk.
    if parent.is_absolute():
        for ancestor in parent.parents:
            for build_name, lang_id in build_map.items():
                if (ancestor / build_name).exists():
                    logger.debug("Language inferred from ancestor build file %s: %s -> %s", build_name, file_path, lang_id)
                    return lang_id

    return None


def _infer_language_from_path(file_path: str) -> Optional[str]:
    """Infer language from well-known directory structures in the path.

    Scans ``_PATH_SEGMENT_LANGUAGES`` for consecutive segment matches.
    Safe for short paths — ``range()`` produces an empty iterator when
    the path has fewer segments than the pattern.
    """
    parts = Path(file_path).parts
    for segments, lang_id in _PATH_SEGMENT_LANGUAGES:
        seg_len = len(segments)
        for i in range(len(parts) - seg_len + 1):
            if tuple(parts[i:i + seg_len]) == segments:
                logger.debug("Language inferred from path segments %s: %s -> %s", segments, file_path, lang_id)
                return lang_id
    return None


def resolve_language(
    target_files: Optional[List[str]] = None,
    *,
    default_id: str = "python",
    batch_target_files: Optional[List[str]] = None,
) -> LanguageProfile:
    """Select the dominant language profile from *target_files*.

    Args:
        target_files: Files to resolve language for (this feature's files).
        default_id: Fallback language profile ID.
        batch_target_files: Optional full list of all target files across
            the entire batch (all features).  When provided, used as context
            for inferring the language of language-neutral files
            (Dockerfiles, config files, etc.) that can't be resolved from
            their own extension or path alone.
    """
    if not target_files:
        profile = LanguageRegistry.get(default_id)
        if profile is None:
            LanguageRegistry.discover()
            profile = LanguageRegistry.get(default_id)
        return profile or LanguageRegistry.get_default()

    ext_map = LanguageRegistry.get_extension_map()
    build_map = _get_build_file_map()
    # Use batch files for sibling context when available
    context_files = batch_target_files if batch_target_files else target_files
    counts: Counter = Counter()
    for fpath in target_files:
        fp = Path(fpath)
        ext = fp.suffix.lower()
        lang_id = ext_map.get(ext)
        if lang_id:
            counts[lang_id] += 1
        else:
            # Fall back to build file pattern matching (go.mod, package.json, etc.)
            lang_id = build_map.get(fp.name)
            if lang_id:
                counts[lang_id] += 1
            else:
                # Try well-known directory path inference
                lang_id = _infer_language_from_path(fpath)
                if lang_id:
                    counts[lang_id] += 1
                else:
                    # Language-neutral file (Dockerfile, .html, .json, etc.)
                    # — infer from sibling files or directory context,
                    # using the full batch for cross-feature inference.
                    inferred = _infer_language_from_context(
                        fpath, context_files, ext_map, build_map,
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
