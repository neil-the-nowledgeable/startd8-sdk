"""Smoke tests for Vue SFC + MicroPrime splice (REQ-VUE-B-009)."""

from __future__ import annotations

from pathlib import Path

import pytest

from startd8.forward_manifest import ForwardElementSpec, ForwardFileSpec
from startd8.languages.registry import LanguageRegistry
from startd8.languages.vue import VueLanguageProfile
from startd8.languages.vue_sfc import extract_vue_script
from startd8.micro_prime.engine import _validate_file_whole_result
from startd8.micro_prime.splicer import splice_body_into_skeleton
from startd8.utils.code_manifest import ElementKind, Param, Signature

_FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "lang-vue-basic" / "App.vue"


@pytest.mark.unit
def test_fixture_extract_and_registry_vue() -> None:
    LanguageRegistry.discover()
    src = _FIXTURE.read_text(encoding="utf-8")
    ext = extract_vue_script(src)
    assert ext is not None
    assert "greet" in ext.script
    profile = LanguageRegistry.get_by_extension(".vue")
    assert profile is not None
    assert profile.language_id == "vue"


@pytest.mark.unit
def test_fixture_splice_greet() -> None:
    src = _FIXTURE.read_text(encoding="utf-8")
    element = ForwardElementSpec(
        kind=ElementKind.FUNCTION,
        name="greet",
        signature=Signature(
            params=[Param(name="name", annotation="str")],
            return_annotation="str",
        ),
    )
    body = (
        "function greet(name) {\n"
        "  return `hello ${name}`;\n"
        "}\n"
    )
    res = splice_body_into_skeleton(
        body, element, src, file_path="src/App.vue",
    )
    assert res.code is not None
    assert "<template>" in res.code
    assert "throw new Error" not in res.code
    assert "hello ${name}" in res.code


@pytest.mark.unit
def test_validate_file_whole_vue_no_python_ast() -> None:
    """REQ-VUE-B-003: file-whole validation uses profile syntax, not ``ast.parse``."""
    fs = ForwardFileSpec(file="src/App.vue", elements=[], language="vue")
    ok_sfc = (
        "<template><p>ok</p></template>\n"
        "<script setup>\n"
        "const msg = 'hi';\n"
        "</script>\n"
    )
    ok, reason, _missing = _validate_file_whole_result(
        ok_sfc, "", fs, VueLanguageProfile(),
    )
    assert ok is True
    assert reason == ""


@pytest.mark.unit
def test_fixture_validate_syntax_b5() -> None:
    """REQ-VUE-B-009 / B.5: profile validation on disk fixture (extracted script)."""
    src = _FIXTURE.read_text(encoding="utf-8")
    ok, err = VueLanguageProfile().validate_syntax(src)
    assert ok, err
