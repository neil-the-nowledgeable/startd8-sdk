"""Tests for LanguageRegistry discover/get/default."""

import pytest

from startd8.languages.protocol import LanguageProfile
from startd8.languages.registry import LanguageRegistry
from startd8.languages.python import PythonLanguageProfile
from startd8.languages.go import GoLanguageProfile
from startd8.languages.nodejs import NodeLanguageProfile
from startd8.languages.java import JavaLanguageProfile


@pytest.fixture(autouse=True)
def clean_registry():
    """Reset registry before each test."""
    LanguageRegistry.clear()
    yield
    LanguageRegistry.clear()


@pytest.mark.unit
class TestRegistryBasics:

    def test_register_and_get(self):
        profile = PythonLanguageProfile()
        LanguageRegistry.register(profile)
        result = LanguageRegistry.get("python")
        assert result is profile

    def test_get_case_insensitive(self):
        LanguageRegistry.register(PythonLanguageProfile())
        assert LanguageRegistry.get("Python") is not None
        assert LanguageRegistry.get("PYTHON") is not None

    def test_get_unknown_returns_none(self):
        assert LanguageRegistry.get("fortran") is None

    def test_register_rejects_non_protocol(self):
        with pytest.raises(TypeError):
            LanguageRegistry.register("not a profile")

    def test_list_languages(self):
        LanguageRegistry.register(PythonLanguageProfile())
        LanguageRegistry.register(GoLanguageProfile())
        langs = LanguageRegistry.list_languages()
        assert "python" in langs
        assert "go" in langs


@pytest.mark.unit
class TestRegistryDiscovery:

    def test_discover_registers_builtins(self):
        LanguageRegistry.discover()
        langs = LanguageRegistry.list_languages()
        assert "python" in langs
        assert "go" in langs
        assert "nodejs" in langs
        assert "java" in langs

    def test_discover_idempotent(self):
        LanguageRegistry.discover()
        count1 = len(LanguageRegistry.list_languages())
        LanguageRegistry.discover()
        count2 = len(LanguageRegistry.list_languages())
        assert count1 == count2

    def test_discover_force(self):
        LanguageRegistry.discover()
        LanguageRegistry.discover(force=True)
        assert "python" in LanguageRegistry.list_languages()


@pytest.mark.unit
class TestRegistryDefaults:

    def test_get_default_returns_python(self):
        LanguageRegistry.discover()
        default = LanguageRegistry.get_default()
        assert default.language_id == "python"

    def test_get_default_discovers_if_needed(self):
        # Even without explicit discover(), get_default() triggers builtin registration
        default = LanguageRegistry.get_default()
        assert default.language_id == "python"


@pytest.mark.unit
class TestRegistryByExtension:

    def test_get_by_extension_py(self):
        LanguageRegistry.discover()
        profile = LanguageRegistry.get_by_extension(".py")
        assert profile is not None
        assert profile.language_id == "python"

    def test_get_by_extension_go(self):
        LanguageRegistry.discover()
        profile = LanguageRegistry.get_by_extension(".go")
        assert profile is not None
        assert profile.language_id == "go"

    def test_get_by_extension_js(self):
        LanguageRegistry.discover()
        profile = LanguageRegistry.get_by_extension(".js")
        assert profile is not None
        assert profile.language_id == "nodejs"

    def test_get_by_extension_java(self):
        LanguageRegistry.discover()
        profile = LanguageRegistry.get_by_extension(".java")
        assert profile is not None
        assert profile.language_id == "java"

    def test_get_by_extension_unknown(self):
        LanguageRegistry.discover()
        assert LanguageRegistry.get_by_extension(".rs") is None

    def test_get_by_extension_case_insensitive(self):
        LanguageRegistry.discover()
        profile = LanguageRegistry.get_by_extension(".PY")
        assert profile is not None
        assert profile.language_id == "python"
