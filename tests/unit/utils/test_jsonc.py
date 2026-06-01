"""Tests for the string-aware JSONC parser (utils/jsonc.py)."""

from __future__ import annotations

import pytest

from startd8.utils.jsonc import loads_jsonc, strip_jsonc


def test_glob_slashstar_in_string_is_not_treated_as_comment():
    # Regression: "./src/*" contains '/*'; a naive stripper + a later '*/' comment ate the JSON.
    text = (
        '{\n  // line comment\n  "compilerOptions": {\n'
        '    "paths": { "@/*": ["./src/*"], },  /* trailing block */\n  },\n}\n'
    )
    obj = loads_jsonc(text)
    assert obj["compilerOptions"]["paths"]["@/*"] == ["./src/*"]


def test_comment_markers_inside_strings_preserved():
    obj = loads_jsonc('{ "a": "http://x", "b": "/* not a comment */", "c": "// nope" }')
    assert obj == {"a": "http://x", "b": "/* not a comment */", "c": "// nope"}


def test_escaped_quote_in_string():
    assert loads_jsonc(r'{ "a": "he said \"hi\" // x" }') == {"a": 'he said "hi" // x'}


def test_trailing_commas_dropped():
    assert loads_jsonc('{ "a": [1, 2,], "b": 3, }') == {"a": [1, 2], "b": 3}


def test_invalid_json_still_raises():
    with pytest.raises(ValueError):
        loads_jsonc("{ this is : not json ]")


def test_strip_is_idempotent_on_plain_json():
    assert strip_jsonc('{"a":1}') == '{"a":1}'
