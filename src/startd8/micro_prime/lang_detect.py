"""Language detection from file paths (REQ-MP-330, FR-DFA-002).

Shared by assembler, validator, splicer, and prime_adapter for
consistent language routing across the MicroPrime pipeline.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Literal, Optional

Language = Literal["python", "dockerfile", "go", "proto", "text", "unknown"]


_EXTENSION_TO_LANG: dict[str, Language] = {
    ".py": "python",
    ".pyi": "python",
    ".go": "go",
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
    ".js": "text",
    ".ts": "text",
    ".sh": "text",
}

_FILENAME_TO_LANG: dict[str, Language] = {
    "Dockerfile": "dockerfile",
}

_DOCKERFILE_PATTERN = re.compile(r"^Dockerfile(\..+)?$", re.IGNORECASE)


def detect_language(file_path: str, explicit_lang: Optional[str] = None) -> Language:
    """Detect language from file path or explicit override.

    Args:
        file_path: Relative or absolute file path.
        explicit_lang: Explicit language override (e.g., from
            ForwardFileSpec.language). When provided, returned directly
            without inference.

    Returns:
        Language identifier: "python", "dockerfile", "go", "proto",
        or "unknown".
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

    # Extension-based detection
    ext = Path(file_path).suffix.lower()
    return _EXTENSION_TO_LANG.get(ext, "unknown")


def is_dockerfile(file_path: str, explicit_lang: Optional[str] = None) -> bool:
    """Convenience: check if file is a Dockerfile."""
    return detect_language(file_path, explicit_lang) == "dockerfile"
