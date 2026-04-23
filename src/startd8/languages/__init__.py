"""Multi-language support for the StartD8 code generation pipeline.

Provides a LanguageProfile protocol and registry for abstracting
language-specific behavior across the Prime Contractor, complexity
classifier, checkpoint validation, and prompt construction subsystems.
"""

from .js_metadata import (
    JS_DIALECT_PLAIN,
    JS_DIALECT_VUE_SFC,
    JS_HOST_JAVASCRIPT_NODE,
    read_js_dialect_id,
    read_js_host_id,
)
from .protocol import LanguageProfile
from .registry import LanguageRegistry
from .resolution import resolve_language

__all__ = [
    "JS_DIALECT_PLAIN",
    "JS_DIALECT_VUE_SFC",
    "JS_HOST_JAVASCRIPT_NODE",
    "LanguageProfile",
    "LanguageRegistry",
    "read_js_dialect_id",
    "read_js_host_id",
    "resolve_language",
]
