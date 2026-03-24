"""Tests for LanguageProfile.sanitize_code_examples() — REQ-TDE-202.

Each language profile transforms known anti-patterns (Console.WriteLine,
fmt.Println, System.out.println, console.log) into standards-compliant
equivalents.  Python is a no-op.
"""

import pytest

from startd8.languages.registry import LanguageRegistry


@pytest.fixture(autouse=True, scope="module")
def discover_profiles():
    LanguageRegistry.discover()


class TestCSharpSanitize:
    def _profile(self):
        return LanguageRegistry.get("csharp")

    def test_console_writeline_transformed(self):
        text = 'Console.WriteLine($"AddItemAsync userId={userId}");'
        result = self._profile().sanitize_code_examples(text)
        assert "Console.WriteLine" not in result
        assert "_logger.LogInformation" in result

    def test_console_error_writeline_transformed(self):
        text = 'Console.Error.WriteLine("connection failed");'
        result = self._profile().sanitize_code_examples(text)
        assert "Console.Error.WriteLine" not in result
        assert "_logger.LogError" in result

    def test_clean_code_unchanged(self):
        text = '_logger.LogInformation("hello");'
        result = self._profile().sanitize_code_examples(text)
        assert result == text

    def test_multiline_transforms(self):
        text = (
            'Console.WriteLine("line1");\n'
            'Console.Error.WriteLine("line2");\n'
            '_logger.LogInformation("line3");\n'
        )
        result = self._profile().sanitize_code_examples(text)
        assert "Console" not in result
        assert result.count("_logger") == 3


class TestGoSanitize:
    def _profile(self):
        return LanguageRegistry.get("go")

    def test_fmt_println_transformed(self):
        text = 'fmt.Println("starting server")'
        result = self._profile().sanitize_code_examples(text)
        assert "fmt.Println" not in result
        assert "slog.Info" in result

    def test_fmt_printf_transformed(self):
        text = 'fmt.Printf("port: %d", port)'
        result = self._profile().sanitize_code_examples(text)
        assert "fmt.Printf" not in result
        assert "slog.Info" in result
        assert "fmt.Sprintf" in result

    def test_clean_code_unchanged(self):
        text = 'slog.Info("hello")'
        result = self._profile().sanitize_code_examples(text)
        assert result == text


class TestJavaSanitize:
    def _profile(self):
        return LanguageRegistry.get("java")

    def test_sysout_println_transformed(self):
        text = 'System.out.println("hello");'
        result = self._profile().sanitize_code_examples(text)
        assert "System.out.println" not in result
        assert "logger.info" in result

    def test_syserr_println_transformed(self):
        text = 'System.err.println("error");'
        result = self._profile().sanitize_code_examples(text)
        assert "System.err.println" not in result
        assert "logger.error" in result

    def test_clean_code_unchanged(self):
        text = 'logger.info("hello");'
        result = self._profile().sanitize_code_examples(text)
        assert result == text


class TestPythonSanitize:
    def test_noop(self):
        profile = LanguageRegistry.get("python")
        text = 'print("debug")'
        assert profile.sanitize_code_examples(text) == text


class TestNodeSanitize:
    def _profile(self):
        return LanguageRegistry.get("nodejs")

    def test_console_log_transformed(self):
        text = 'console.log("starting server")'
        result = self._profile().sanitize_code_examples(text)
        assert "console.log" not in result
        assert "logger.info" in result

    def test_console_error_transformed(self):
        text = 'console.error("connection failed")'
        result = self._profile().sanitize_code_examples(text)
        assert "console.error" not in result
        assert "logger.error" in result

    def test_console_warn_transformed(self):
        text = 'console.warn("deprecated")'
        result = self._profile().sanitize_code_examples(text)
        assert "console.warn" not in result
        assert "logger.warn" in result

    def test_var_to_const(self):
        text = "var count = 0"
        result = self._profile().sanitize_code_examples(text)
        assert "var " not in result
        assert "const count =" in result

    def test_clean_code_unchanged(self):
        text = 'logger.info("hello")'
        result = self._profile().sanitize_code_examples(text)
        assert result == text

    def test_multiline_transforms(self):
        text = (
            'console.log("line1");\n'
            'console.error("line2");\n'
            'logger.info("line3");\n'
        )
        result = self._profile().sanitize_code_examples(text)
        assert "console" not in result
        assert result.count("logger") == 3
