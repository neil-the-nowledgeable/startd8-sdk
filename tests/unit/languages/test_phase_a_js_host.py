"""Phase A — JS host metadata, extension map uniqueness, resolve_language hints."""

import pytest

from startd8.languages import (
    JS_DIALECT_PLAIN,
    JS_HOST_JAVASCRIPT_NODE,
    LanguageRegistry,
    read_js_dialect_id,
    read_js_host_id,
    resolve_language,
)
from startd8.languages.nodejs import NodeLanguageProfile


def test_node_js_host_metadata() -> None:
    n = NodeLanguageProfile()
    assert n.js_host_id == JS_HOST_JAVASCRIPT_NODE
    assert n.js_dialect_id == JS_DIALECT_PLAIN
    assert read_js_host_id(n) == JS_HOST_JAVASCRIPT_NODE
    assert read_js_dialect_id(n) == JS_DIALECT_PLAIN


def test_python_profile_has_no_js_host_attrs() -> None:
    LanguageRegistry.discover()
    py = LanguageRegistry.get("python")
    assert py is not None
    assert read_js_host_id(py) is None
    assert read_js_dialect_id(py) is None


def test_resolve_language_path_hints_override_inference() -> None:
    LanguageRegistry.discover()
    # Without hint, README.md resolves via sibling/batch inference (varies).
    profile = resolve_language(
        ["README.md"],
        path_language_hints={"README.md": "nodejs"},
    )
    assert profile.language_id == "nodejs"


def test_resolve_language_hint_normalized_key() -> None:
    LanguageRegistry.discover()
    profile = resolve_language(
        ["src/foo.md"],
        path_language_hints={"src/foo.md": "go"},
    )
    assert profile.language_id == "go"


def test_extension_map_rejects_duplicate_extensions() -> None:
    """Second profile claiming the same extensions as Node must raise (REQ-JSF-005)."""

    class EvilNode(NodeLanguageProfile):
        @property
        def language_id(self) -> str:
            return "evil_node"

    LanguageRegistry.clear()
    try:
        LanguageRegistry.discover()
        LanguageRegistry.register(EvilNode())
        with pytest.raises(ValueError, match="extension conflict"):
            LanguageRegistry.get_extension_map()
    finally:
        LanguageRegistry.clear()
        LanguageRegistry.discover(force=True)
