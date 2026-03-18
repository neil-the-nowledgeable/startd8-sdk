"""Tests for Java syntax validation (Phase 1)."""

import pytest


# ── Valid Java source ──────────────────────────────────────────────────

VALID_JAVA = """\
package com.example;

import java.util.List;

public class Example {
    private String name;

    public Example(String name) {
        this.name = name;
    }

    public String getName() {
        return this.name;
    }
}
"""

VALID_INTERFACE = """\
package com.example;

public interface Service {
    void execute();
    String getName();
}
"""

VALID_ENUM = """\
package com.example;

public enum Color {
    RED, GREEN, BLUE;
}
"""

VALID_RECORD = """\
package com.example;

public record Point(int x, int y) {}
"""

# ── Invalid Java source ───────────────────────────────────────────────

INVALID_UNBALANCED = """\
package com.example;
public class Bad {
    public void foo() {
"""

PYTHON_CODE = """\
def hello():
    print("hello world")
    self.name = name
"""


class TestJavaValidateSyntax:
    """Tests for JavaLanguageProfile.validate_syntax()."""

    def _get_profile(self):
        from startd8.languages.java import JavaLanguageProfile
        return JavaLanguageProfile()

    def test_valid_class(self):
        profile = self._get_profile()
        ok, err = profile.validate_syntax(VALID_JAVA)
        assert ok, f"Expected valid, got: {err}"

    def test_valid_interface(self):
        profile = self._get_profile()
        ok, err = profile.validate_syntax(VALID_INTERFACE)
        assert ok, f"Expected valid, got: {err}"

    def test_valid_enum(self):
        profile = self._get_profile()
        ok, err = profile.validate_syntax(VALID_ENUM)
        assert ok, f"Expected valid, got: {err}"

    def test_invalid_unbalanced_braces(self):
        profile = self._get_profile()
        ok, err = profile.validate_syntax(INVALID_UNBALANCED)
        assert not ok
        assert "brace" in err.lower() or "syntax" in err.lower()

    def test_python_fingerprint_rejected(self):
        profile = self._get_profile()
        ok, err = profile.validate_syntax(PYTHON_CODE)
        assert not ok
        assert "fingerprint" in err.lower() or "syntax" in err.lower()


class TestJavaReservedKeywords:
    """Tests for _JAVA_RESERVED frozenset."""

    def test_keywords_present(self):
        from startd8.languages.java import _JAVA_RESERVED
        for kw in ("class", "interface", "public", "private", "void", "int"):
            assert kw in _JAVA_RESERVED

    def test_contextual_keywords(self):
        from startd8.languages.java import _JAVA_RESERVED
        for kw in ("var", "yield", "record", "sealed"):
            assert kw in _JAVA_RESERVED

    def test_literals(self):
        from startd8.languages.java import _JAVA_RESERVED
        for kw in ("true", "false", "null"):
            assert kw in _JAVA_RESERVED

    def test_non_keyword_absent(self):
        from startd8.languages.java import _JAVA_RESERVED
        assert "foobar" not in _JAVA_RESERVED


class TestJavaLiteralCoerce:
    """Tests for _java_literal_coerce()."""

    def test_true(self):
        from startd8.languages.java import _java_literal_coerce
        assert _java_literal_coerce(True) == "true"

    def test_false(self):
        from startd8.languages.java import _java_literal_coerce
        assert _java_literal_coerce(False) == "false"

    def test_none(self):
        from startd8.languages.java import _java_literal_coerce
        assert _java_literal_coerce(None) == "null"

    def test_list(self):
        from startd8.languages.java import _java_literal_coerce
        result = _java_literal_coerce([1, 2, 3])
        assert result == "List.of(1, 2, 3)"

    def test_string(self):
        from startd8.languages.java import _java_literal_coerce
        assert _java_literal_coerce("hello") == '"hello"'

    def test_int(self):
        from startd8.languages.java import _java_literal_coerce
        assert _java_literal_coerce(42) == "42"

    def test_dict(self):
        from startd8.languages.java import _java_literal_coerce
        result = _java_literal_coerce({"key": "val"})
        assert "Map.of" in result


class TestTextBasedFallback:
    """Tests for text-based validation when javalang is unavailable."""

    def test_text_fallback_valid(self):
        from startd8.languages.java import _text_based_java_validate
        ok, err = _text_based_java_validate(VALID_JAVA)
        assert ok, f"Expected valid: {err}"

    def test_text_fallback_unbalanced(self):
        from startd8.languages.java import _text_based_java_validate
        ok, err = _text_based_java_validate(INVALID_UNBALANCED)
        assert not ok

    def test_text_fallback_python(self):
        from startd8.languages.java import _text_based_java_validate
        ok, err = _text_based_java_validate(PYTHON_CODE)
        assert not ok
        assert "fingerprint" in err.lower()

    def test_text_fallback_no_type_decl(self):
        from startd8.languages.java import _text_based_java_validate
        ok, err = _text_based_java_validate("package com.example;\n// empty\n")
        assert not ok
        assert "type declaration" in err.lower()
