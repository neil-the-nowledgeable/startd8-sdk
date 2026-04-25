"""REQ-VUE-B-005 / C.3: Vue syntax check, validate_syntax, lint, test_command."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from startd8.languages.nodejs import NodeLanguageProfile
from startd8.languages.vue import VueLanguageProfile


@pytest.fixture
def vue_profile() -> VueLanguageProfile:
    return VueLanguageProfile()


def test_syntax_check_uses_vue_tsc_by_default(vue_profile: VueLanguageProfile, monkeypatch) -> None:
    monkeypatch.delenv("STARTD8_VUE_SYNTAX_CHECK", raising=False)
    cmd = vue_profile.syntax_check_command
    assert cmd is not None
    assert "vue-tsc" in cmd
    assert "{file}" in cmd


def test_syntax_check_disabled_via_env(vue_profile: VueLanguageProfile, monkeypatch) -> None:
    monkeypatch.setenv("STARTD8_VUE_SYNTAX_CHECK", "0")
    assert vue_profile.syntax_check_command is None


def test_validate_syntax_lang_ts_dispatches_typescript(vue_profile: VueLanguageProfile) -> None:
    """REQ-VUE-P-004: ``lang=\"ts\"`` uses the same TS path as Node."""
    sfc = '<script setup lang="ts">\nconst x: number = 1;\n</script>'
    with patch.object(vue_profile, "_validate_typescript", return_value=(True, "")) as m_ts:
        ok, err = vue_profile.validate_syntax(sfc)
    m_ts.assert_called_once()
    assert ok is True
    assert err == ""


def test_validate_syntax_plain_script_interface_uses_ts_heuristic(
    vue_profile: VueLanguageProfile,
) -> None:
    """REQ-VUE-P-004: TS-shaped ``<script setup>`` without ``lang`` matches Node."""
    sfc = "<script setup>\ninterface User { name: string }\n</script>"
    with patch.object(vue_profile, "_validate_typescript", return_value=(True, "")) as m_ts:
        vue_profile.validate_syntax(sfc)
    m_ts.assert_called_once()


def test_validate_syntax_plain_js_stays_js_path(vue_profile: VueLanguageProfile) -> None:
    sfc = "<script setup>\nfunction add(a, b) { return a + b; }\n</script>"
    with patch.object(vue_profile, "_validate_javascript", return_value=(True, "")) as m_js:
        vue_profile.validate_syntax(sfc)
    m_js.assert_called_once()


def test_test_command_parity_with_node(vue_profile: VueLanguageProfile) -> None:
    """REQ-VUE-P-005: Vue uses the same ``npm test`` baseline as Node."""
    assert vue_profile.test_command == NodeLanguageProfile().test_command


def test_lint_command_disabled_by_default(vue_profile: VueLanguageProfile, monkeypatch) -> None:
    monkeypatch.delenv("STARTD8_VUE_LINT", raising=False)
    assert vue_profile.lint_command is None


def test_lint_command_opt_in_via_env(vue_profile: VueLanguageProfile, monkeypatch) -> None:
    monkeypatch.setenv("STARTD8_VUE_LINT", "1")
    cmd = vue_profile.lint_command
    assert cmd is not None
    assert "eslint" in cmd
    assert "{file}" in cmd
