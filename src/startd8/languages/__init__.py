"""Multi-language support for the StartD8 code generation pipeline.

Provides a LanguageProfile protocol and registry for abstracting
language-specific behavior across the Prime Contractor, complexity
classifier, checkpoint validation, and prompt construction subsystems.
"""

from .protocol import LanguageProfile
from .registry import LanguageRegistry
from .resolution import resolve_language

__all__ = [
    "LanguageProfile",
    "LanguageRegistry",
    "resolve_language",
]
