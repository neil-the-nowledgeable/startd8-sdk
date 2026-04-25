"""Tests for Vue SFC script extraction (REQ-VUE-B-002, REQ-VUE-P-002/003/013)."""

from pathlib import Path

from startd8.languages.vue_sfc import (
    extract_vue_script,
    non_script_blocks_unchanged,
    non_script_region_snapshot,
    parse_vue_sfc_script_elements,
    reinject_vue_script,
    vue_script_block_checksum,
)

_FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "lang-vue-basic" / "App.vue"


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


def test_reinject_idempotent_same_body() -> None:
    """REQ-VUE-P-013: reinjecting the extracted body leaves the SFC unchanged."""
    src = '<script setup lang="ts" generic="T extends object">\nconst n = 1\n</script>\n'
    ext = extract_vue_script(src)
    assert ext is not None
    assert reinject_vue_script(src, ext.script) == src


def test_reinject_idempotent_double_apply() -> None:
    body = "\nconst y = 2;\n"
    src = f"<script setup>{body}</script>"
    once = reinject_vue_script(src, body)
    twice = reinject_vue_script(once, body)
    assert once == twice == src


def test_crlf_round_trip_preserves_prefix() -> None:
    """REQ-VUE-P-013: CRLF outside the script block is preserved."""
    src = (
        "<template>\r\n<p>x</p>\r\n</template>\r\n"
        "<script setup>\r\nconst a = 1\r\n</script>"
    )
    ext = extract_vue_script(src)
    assert ext is not None
    assert "\r\n" in ext.script
    new_body = ext.script.replace("1", "2")
    out = reinject_vue_script(src, new_body)
    assert "<template>\r\n" in out
    assert "const a = 2" in out


def test_vue_script_block_checksum_stable_under_reinject() -> None:
    src = "<script setup>\nfoo()\n</script>"
    ext = extract_vue_script(src)
    assert ext is not None
    c0 = vue_script_block_checksum(src)
    c1 = vue_script_block_checksum(reinject_vue_script(src, ext.script))
    assert c0 == c1


def test_parse_vue_sfc_matches_nodejs_on_extracted_fixture() -> None:
    """REQ-VUE-P-002: same extractor as ``nodejs_parser`` on extracted script."""
    from startd8.languages.nodejs_parser import parse_nodejs_source

    sfc = _FIXTURE.read_text(encoding="utf-8")
    ext = extract_vue_script(sfc)
    assert ext is not None
    from_script = parse_vue_sfc_script_elements(sfc)
    direct = parse_nodejs_source(ext.script)
    assert from_script == direct


def test_parse_vue_lists_top_level_function() -> None:
    """REQ-VUE-P-002: extracted script uses same heuristics as ``nodejs_parser``."""
    src = (
        '<script setup lang="ts">\n'
        "export function greet(name: string): string {\n"
        "  return `hello ${name}`;\n"
        "}\n"
        "</script>\n"
    )
    els = parse_vue_sfc_script_elements(src)
    assert any(e.kind == "function" and e.name == "greet" for e in els)


def test_non_script_snapshot_skips_style_src() -> None:
    """P-011: external style links are not part of the inline snapshot."""
    src = (
        '<style src="./foo.css"></style>\n'
        "<template><p>hi</p></template>\n"
        "<style scoped>.a{color:red}</style>\n"
    )
    snap = non_script_region_snapshot(src)
    assert "foo" not in snap.lower()
    assert "hi" in snap
    assert "color" in snap


def test_reinject_preserves_non_script_for_guardrail() -> None:
    """P-011: script-only round-trip does not change template/style snapshot."""
    src = (
        "<template><p>ok</p></template>\n"
        "<script setup>\n"
        "const n = 1\n"
        "</script>\n"
        "<style scoped>\n"
        "p { margin: 0; }\n"
        "</style>\n"
    )
    ext = extract_vue_script(src)
    assert ext is not None
    out = reinject_vue_script(src, ext.script.replace("1", "2"))
    assert "const n = 2" in out
    assert non_script_blocks_unchanged(src, out) is True
