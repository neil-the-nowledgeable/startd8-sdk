"""Tests for language detection from file paths (FR-DFA-002)."""
import pytest

from startd8.micro_prime.lang_detect import detect_language, is_dockerfile


class TestDetectLanguage:
    """Test detect_language() extension/filename-based detection."""

    def test_python_extension(self):
        assert detect_language("src/app.py") == "python"

    def test_python_stub_extension(self):
        assert detect_language("src/app.pyi") == "python"

    def test_go_extension(self):
        assert detect_language("cmd/main.go") == "go"

    def test_proto_extension(self):
        assert detect_language("api/service.proto") == "proto"

    def test_dockerfile_exact(self):
        assert detect_language("src/loadgenerator/Dockerfile") == "dockerfile"

    def test_dockerfile_variant_dev(self):
        assert detect_language("Dockerfile.dev") == "dockerfile"

    def test_dockerfile_variant_prod(self):
        assert detect_language("services/api/Dockerfile.prod") == "dockerfile"

    def test_dockerfile_case_insensitive(self):
        assert detect_language("dockerfile") == "dockerfile"
        assert detect_language("DOCKERFILE") == "dockerfile"

    def test_unknown_extension(self):
        assert detect_language("main.rs") == "unknown"
        assert detect_language("data.parquet") == "unknown"

    def test_text_extension(self):
        """Common text/config files now detected as 'text' for pipeline registration."""
        assert detect_language("README.md") == "text"
        assert detect_language("config.yaml") == "text"
        assert detect_language("requirements.txt") == "text"
        assert detect_language("setup.cfg") == "text"
        assert detect_language("app.json") == "text"
        assert detect_language("style.css") == "text"

    def test_explicit_override(self):
        """explicit_lang takes precedence over file extension."""
        assert detect_language("app.py", explicit_lang="go") == "go"
        assert detect_language("Dockerfile", explicit_lang="python") == "python"

    def test_explicit_vue_reserved(self):
        """``explicit_lang`` passes through without consulting the extension map."""
        assert detect_language("src/App.vue", explicit_lang="vue") == "vue"

    def test_vue_extension_registered(self):
        from startd8.languages.registry import LanguageRegistry

        LanguageRegistry.discover()
        assert detect_language("src/App.vue") == "vue"

    def test_explicit_none_falls_through(self):
        """explicit_lang=None triggers normal inference."""
        assert detect_language("app.py", explicit_lang=None) == "python"

    def test_no_extension(self):
        """File with no extension and not a known filename → unknown."""
        assert detect_language("Makefile") == "unknown"


class TestIsDockerfile:
    """Test is_dockerfile() convenience helper."""

    def test_is_dockerfile_true(self):
        assert is_dockerfile("src/app/Dockerfile") is True

    def test_is_dockerfile_false(self):
        assert is_dockerfile("src/app/main.py") is False

    def test_is_dockerfile_with_override(self):
        assert is_dockerfile("Dockerfile", explicit_lang="python") is False
