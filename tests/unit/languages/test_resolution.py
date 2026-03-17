"""Tests for language resolution from file lists."""

import pytest

from startd8.languages.registry import LanguageRegistry
from startd8.languages.resolution import resolve_language


@pytest.fixture(autouse=True)
def clean_registry():
    LanguageRegistry.clear()
    LanguageRegistry.discover()
    yield
    LanguageRegistry.clear()


@pytest.mark.unit
class TestResolveLanguage:

    def test_python_files(self):
        profile = resolve_language(["src/emailservice/email_server.py"])
        assert profile.language_id == "python"

    def test_go_files(self):
        profile = resolve_language(["src/frontend/main.go", "src/frontend/handlers.go"])
        assert profile.language_id == "go"

    def test_js_files(self):
        profile = resolve_language(["src/currencyservice/server.js"])
        assert profile.language_id == "nodejs"

    def test_java_files(self):
        profile = resolve_language(["src/adservice/AdService.java"])
        assert profile.language_id == "java"

    def test_mixed_files_dominant_wins(self):
        """When files are mixed, the most common language wins."""
        profile = resolve_language([
            "src/service/main.go",
            "src/service/handler.go",
            "src/service/config.py",
        ])
        assert profile.language_id == "go"

    def test_empty_list_defaults_to_python(self):
        profile = resolve_language([])
        assert profile.language_id == "python"

    def test_none_defaults_to_python(self):
        profile = resolve_language(None)
        assert profile.language_id == "python"

    def test_unknown_extensions_default_to_python(self):
        profile = resolve_language(["Dockerfile", "README.md"])
        assert profile.language_id == "python"

    def test_dockerfile_with_go_files(self):
        """Dockerfile is ignored, Go wins."""
        profile = resolve_language([
            "Dockerfile",
            "src/service/main.go",
        ])
        assert profile.language_id == "go"

    def test_mjs_resolves_to_nodejs(self):
        profile = resolve_language(["src/service/index.mjs"])
        assert profile.language_id == "nodejs"

    def test_custom_default(self):
        profile = resolve_language([], default_id="go")
        assert profile.language_id == "go"
