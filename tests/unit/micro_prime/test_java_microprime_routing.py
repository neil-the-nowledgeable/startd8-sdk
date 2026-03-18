"""Tests for Java MicroPrime routing (Phase 3)."""

import pytest
from unittest.mock import patch


class TestJavaMicroPrimeRouting:

    def test_java_bypass_by_default(self):
        """Java files should bypass MicroPrime by default."""
        from startd8.micro_prime.engine import _is_non_python_file
        assert _is_non_python_file("src/main/java/com/example/MyClass.java") is True

    def test_java_routes_when_enabled(self):
        """When JAVA_MICROPRIME_ENABLED=True, .java files are NOT non-Python."""
        import startd8.micro_prime.engine as engine_mod
        original = engine_mod.JAVA_MICROPRIME_ENABLED
        try:
            engine_mod.JAVA_MICROPRIME_ENABLED = True
            assert engine_mod._is_non_python_file("MyClass.java") is False
        finally:
            engine_mod.JAVA_MICROPRIME_ENABLED = original

    def test_python_still_not_non_python(self):
        from startd8.micro_prime.engine import _is_non_python_file
        assert _is_non_python_file("main.py") is False

    def test_go_still_not_non_python(self):
        """Go was already removed from _NON_PYTHON_EXTENSIONS (MP-P6)."""
        from startd8.micro_prime.engine import _is_non_python_file
        # Go files should be handled by Go path, not in _NON_PYTHON_EXTENSIONS
        # But .go is also not in the set, so this should return False
        # Actually, .go was removed from the set, so unknown → False
        result = _is_non_python_file("main.go")
        # .go is not in _NON_PYTHON_EXTENSIONS and not .py, so returns False
        assert result is False


class TestJavaSplicerDispatch:

    def test_is_java_source_by_extension(self):
        from startd8.micro_prime.splicer import _is_java_source
        assert _is_java_source("anything", "MyClass.java") is True

    def test_is_java_source_by_content(self):
        from startd8.micro_prime.splicer import _is_java_source
        java_content = "package com.example;\npublic class Foo {}\n"
        assert _is_java_source(java_content, "unknown") is True

    def test_is_not_java_source(self):
        from startd8.micro_prime.splicer import _is_java_source
        python_content = "def foo():\n    pass\n"
        assert _is_java_source(python_content, "main.py") is False


class TestJavaSystemPrompt:

    def test_java_stub_marker_in_prompt(self):
        """Java system prompt should use UnsupportedOperationException stub marker."""
        from startd8.micro_prime.engine import _build_system_prompt
        from startd8.languages.java import JavaLanguageProfile

        profile = JavaLanguageProfile()
        prompt = _build_system_prompt(profile, "file_whole")
        assert "UnsupportedOperationException" in prompt

    def test_java_body_prompt(self):
        from startd8.micro_prime.engine import _build_system_prompt
        from startd8.languages.java import JavaLanguageProfile

        profile = JavaLanguageProfile()
        prompt = _build_system_prompt(profile, "body")
        assert "Java" in prompt
        assert "expert" in prompt.lower()

    def test_java_full_function_prompt(self):
        from startd8.micro_prime.engine import _build_system_prompt
        from startd8.languages.java import JavaLanguageProfile

        profile = JavaLanguageProfile()
        prompt = _build_system_prompt(profile, "full_function")
        assert "Java" in prompt
