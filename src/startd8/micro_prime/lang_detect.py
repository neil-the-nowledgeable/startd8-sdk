"""Language detection from file paths (REQ-MP-330, FR-DFA-002).

Shared by assembler, validator, splicer, and prime_adapter for
consistent language routing across the MicroPrime pipeline.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Literal, Optional

# ``vue`` reserved for SFC dialect (Part B); explicit_lang / registry may return it.
Language = Literal[
    "python",
    "dockerfile",
    "go",
    "java",
    "nodejs",
    "csharp",
    "proto",
    "text",
    "vue",
    "unknown",
]

# Non-language extensions that the LanguageRegistry does not cover.
_TEXT_AND_OTHER_EXTENSIONS: dict[str, Language] = {
    ".pyi": "python",
    ".csx": "csharp",
    ".razor": "csharp",
    ".proto": "proto",
    ".txt": "text",
    ".in": "text",
    ".cfg": "text",
    ".ini": "text",
    ".toml": "text",
    ".yaml": "text",
    ".yml": "text",
    ".json": "text",
    ".md": "text",
    ".html": "text",
    ".css": "text",
    ".sh": "text",
}

_FILENAME_TO_LANG: dict[str, Language] = {
    "Dockerfile": "dockerfile",
    "build.gradle": "java",
    "build.gradle.kts": "java",
    "settings.gradle": "java",
    "pom.xml": "java",
    "package.json": "nodejs",
    "Directory.Build.props": "csharp",
}

_DOCKERFILE_PATTERN = re.compile(r"^Dockerfile(\..+)?$", re.IGNORECASE)


def detect_language(file_path: str, explicit_lang: Optional[str] = None) -> str:
    """Detect language from file path or explicit override.

    Args:
        file_path: Relative or absolute file path.
        explicit_lang: Explicit language override (e.g., from
            ForwardFileSpec.language). When provided, returned directly
            without inference.

    Returns:
        Language identifier string (typically ``language_id`` from
        :class:`~startd8.languages.registry.LanguageRegistry`, plus
        ``proto``, ``text``, ``unknown`` for non-registered extensions).
    """
    if explicit_lang is not None:
        return explicit_lang

    filename = Path(file_path).name

    # Exact filename match (Dockerfile)
    if filename in _FILENAME_TO_LANG:
        return _FILENAME_TO_LANG[filename]

    # Dockerfile variants (Dockerfile.dev, Dockerfile.prod)
    if _DOCKERFILE_PATTERN.match(filename):
        return "dockerfile"

    # Suffix-based detection for C# project/solution files
    if filename.endswith(".csproj") or filename.endswith(".sln"):
        return "csharp"

    # Extension-based detection
    ext = Path(file_path).suffix.lower()
    # Try language registry first (covers .py, .go, .java, .js, .cs, etc.)
    from startd8.languages.registry import LanguageRegistry
    lang_id = LanguageRegistry.get_extension_map().get(ext)
    if lang_id is not None:
        return lang_id
    # Fall back to non-language extensions
    return _TEXT_AND_OTHER_EXTENSIONS.get(ext, "unknown")


def is_dockerfile(file_path: str, explicit_lang: Optional[str] = None) -> bool:
    """Convenience: check if file is a Dockerfile."""
    return detect_language(file_path, explicit_lang) == "dockerfile"
