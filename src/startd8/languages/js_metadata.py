"""JavaScript host / dialect metadata (REQ-JSF-001, REQ-JSF-002, Phase A).

Canonical IDs for profiles that participate in the shared JS-on-Node host.
Non-JS profiles omit ``js_host_id`` / ``js_dialect_id`` attributes entirely.
"""

from __future__ import annotations

from typing import Optional

# Canonical host for npm / ECMAScript-family dialects (plain Node, future Vue SFC, …).
JS_HOST_JAVASCRIPT_NODE = "javascript_node"

# Plain ``.js`` / ``.ts`` files on disk (not SFC).
JS_DIALECT_PLAIN = "plain"

# Vue 3 single-file component script block (REQ-VUE-B-001).
JS_DIALECT_VUE_SFC = "vue_sfc"


def read_js_host_id(profile: object) -> Optional[str]:
    """Return ``js_host_id`` when the profile defines it, else ``None``."""
    if hasattr(profile, "js_host_id"):
        return profile.js_host_id  # type: ignore[no-any-return]
    return None


def read_js_dialect_id(profile: object) -> Optional[str]:
    """Return ``js_dialect_id`` when the profile defines it, else ``None``."""
    if hasattr(profile, "js_dialect_id"):
        return profile.js_dialect_id  # type: ignore[no-any-return]
    return None
