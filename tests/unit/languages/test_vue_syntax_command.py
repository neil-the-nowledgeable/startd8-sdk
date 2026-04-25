"""REQ-VUE-B-005: Vue optional vue-tsc syntax check wiring."""

from __future__ import annotations

import pytest

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
