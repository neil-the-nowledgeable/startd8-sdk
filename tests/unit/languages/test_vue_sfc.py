"""Tests for Vue SFC script extraction (REQ-VUE-B-002)."""

from startd8.languages.vue_sfc import extract_vue_script, reinject_vue_script


def test_extract_script_setup_default_js() -> None:
    src = """<template><p>x</p></template>
<script setup>
const x = 1
</script>
"""
    ext = extract_vue_script(src)
    assert ext is not None
    assert ext.setup is True
    assert ext.lang == "js"
    assert "const x = 1" in ext.script


def test_extract_script_setup_lang_ts() -> None:
    src = '<script setup lang="ts">\nconst n: number = 2\n</script>\n'
    ext = extract_vue_script(src)
    assert ext is not None
    assert ext.lang == "ts"


def test_precedence_setup_over_plain() -> None:
    src = """
<script>console.log(1)</script>
<script setup>const a = 1</script>
"""
    ext = extract_vue_script(src)
    assert ext is not None
    assert ext.setup is True
    assert "const a = 1" in ext.script


def test_skips_external_src_script() -> None:
    src = '<script src="./foo.ts"></script><script setup>const b = 2</script>'
    ext = extract_vue_script(src)
    assert ext is not None
    assert "const b = 2" in ext.script


def test_reinject_round_trip() -> None:
    src = "<script setup>old</script>"
    ext = extract_vue_script(src)
    assert ext is not None
    out = reinject_vue_script(src, "new")
    assert "new" in out
    assert "old" not in out


def test_no_script_returns_none() -> None:
    assert extract_vue_script("<template></template>") is None


def test_extract_empty_script_setup() -> None:
    """B.2.4: empty primary script block is still discoverable."""
    src = "<template><p>x</p></template><script setup></script>"
    ext = extract_vue_script(src)
    assert ext is not None
    assert ext.setup is True
    assert ext.script.strip() == ""


def test_extract_whitespace_only_script() -> None:
    src = "<script setup>\n   \n  \n</script>"
    ext = extract_vue_script(src)
    assert ext is not None
    assert ext.script.strip() == ""


def test_reinject_preserves_script_whitespace_slice() -> None:
    """Replacement span must match ``<script>`` inner text including newlines."""
    src = "<script setup>\nconst x = 1\n</script>"
    ext = extract_vue_script(src)
    assert ext is not None
    assert ext.script.startswith("\n")
    out = reinject_vue_script(src, "\nconst x = 2\n")
    assert "const x = 2" in out
    assert "const x = 1" not in out
    assert out.endswith("</script>")
