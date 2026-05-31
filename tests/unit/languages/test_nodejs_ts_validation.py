"""Tests for Node.js TypeScript validation dispatch — REQ-NODE-MP-300.

Verifies that:
- validate_syntax() dispatches to JS or TS validation based on filename_hint
- _looks_like_typescript() detects TS-specific syntax patterns
- JS validation is unchanged (regression)
- Graceful fallback when tsc is not installed
"""

import pytest
from unittest.mock import patch

from startd8.languages.nodejs import (
    NodeLanguageProfile,
    _looks_like_typescript,
)


@pytest.fixture
def profile():
    return NodeLanguageProfile()


# ---------------------------------------------------------------------------
# _looks_like_typescript() — heuristic detection
# ---------------------------------------------------------------------------

class TestLooksLikeTypescript:
    def test_type_annotation_string(self):
        assert _looks_like_typescript("const name: string = 'hello';") is True

    def test_type_annotation_number(self):
        assert _looks_like_typescript("let count: number = 0;") is True

    def test_interface_declaration(self):
        assert _looks_like_typescript("interface User { name: string; }") is True

    def test_generic_parameter(self):
        assert _looks_like_typescript("function parse<T>(data: string): T {}") is True

    def test_type_alias(self):
        assert _looks_like_typescript("type Status = 'active' | 'inactive';") is True

    def test_as_const(self):
        assert _looks_like_typescript("const x = [1, 2] as const;") is True

    def test_plain_js_not_detected(self):
        assert _looks_like_typescript("function add(a, b) { return a + b; }") is False

    def test_plain_js_arrow_not_detected(self):
        assert _looks_like_typescript("const fn = (x) => x * 2;") is False

    def test_empty_string(self):
        assert _looks_like_typescript("") is False


# ---------------------------------------------------------------------------
# validate_syntax() — dispatch
# ---------------------------------------------------------------------------

class TestValidateSyntaxDispatch:
    def test_js_filename_uses_js_validation(self, profile):
        """Plain JS validated via node --check (or best-effort pass)."""
        valid, _ = profile.validate_syntax(
            "function add(a, b) { return a + b; }",
            filename_hint="src/utils.js",
        )
        assert valid is True

    def test_ts_filename_dispatches_to_ts(self, profile):
        """TS filename hint triggers TS validation path."""
        # We can't guarantee tsc is installed, so we mock the internal method.
        with patch.object(profile, "_validate_typescript", return_value=(True, "")) as mock_ts:
            valid, err = profile.validate_syntax(
                "const x: number = 5;",
                filename_hint="src/utils.ts",
            )
            mock_ts.assert_called_once()
            assert valid is True

    def test_tsx_filename_dispatches_to_ts(self, profile):
        with patch.object(profile, "_validate_typescript", return_value=(True, "")) as mock_ts:
            profile.validate_syntax(
                "const App: React.FC = () => <div />;",
                filename_hint="src/App.tsx",
            )
            mock_ts.assert_called_once()

    def test_heuristic_detection_triggers_ts(self, profile):
        """Code with TS syntax but no filename hint still goes TS path."""
        with patch.object(profile, "_validate_typescript", return_value=(True, "")) as mock_ts:
            profile.validate_syntax("interface User { name: string; }")
            mock_ts.assert_called_once()

    def test_plain_js_stays_on_js_path(self, profile):
        """Plain JS without filename hint stays on JS path."""
        with patch.object(profile, "_validate_javascript", return_value=(True, "")) as mock_js:
            profile.validate_syntax("function add(a, b) { return a + b; }")
            mock_js.assert_called_once()

    def test_no_hint_plain_js(self, profile):
        """Backward compat: no filename_hint works like before."""
        valid, _ = profile.validate_syntax("function add(a, b) { return a + b; }")
        assert valid is True


# ---------------------------------------------------------------------------
# _validate_typescript() — graceful fallback
# ---------------------------------------------------------------------------

class TestTypescriptValidationFallback:
    def test_tsc_not_installed_returns_true(self, profile):
        """When tsc is not installed, return (True, '') — best-effort."""
        with patch("shutil.which", return_value=None):
            valid, err = profile._validate_typescript("const x: number = 5;")
            assert valid is True

    def test_valid_js_passes_js_validation(self, profile):
        """Regression: JS validation still works."""
        valid, err = profile._validate_javascript(
            "function add(a, b) { return a + b; }"
        )
        assert valid is True


# ---------------------------------------------------------------------------
# REQ-NODE-MP-301 — toolchain-absence discrimination + JSX handling
# ---------------------------------------------------------------------------

class TestToolchainDegradation:
    """A non-zero tsc exit is only a failure if it carries a real diagnostic."""

    def test_npx_install_noise_is_not_a_syntax_error(self, profile):
        """`npx tsc` without typescript installed prints an install prompt and
        exits non-zero; that must degrade to a best-effort PASS, not a
        false failure that triggers a spurious escalation."""
        from unittest.mock import MagicMock
        noise = "This is not the tsc command you are looking for"
        with patch("shutil.which", side_effect=lambda t: "/usr/bin/npx" if t == "npx" else None):
            with patch("subprocess.run", return_value=MagicMock(returncode=1, stdout=noise, stderr="")):
                valid, err = profile._validate_typescript("const x: number = 5;")
        assert valid is True
        assert err == ""

    def test_real_tsc_diagnostic_is_a_failure(self, profile):
        """Output containing `error TS####` is a genuine syntax error."""
        from unittest.mock import MagicMock
        diag = "tmp.ts(1,5): error TS1005: ';' expected."
        with patch("shutil.which", side_effect=lambda t: "/usr/bin/tsc" if t == "tsc" else None):
            with patch("subprocess.run", return_value=MagicMock(returncode=2, stdout=diag, stderr="")):
                valid, err = profile._validate_typescript("const x: = 5;")
        assert valid is False
        assert "error TS1005" in err


class TestJsxHandling:
    """JSX/TSX files must validate with a .tsx temp + --jsx (latent CI bug)."""

    def test_looks_like_jsx(self):
        from startd8.languages.nodejs import _looks_like_jsx
        assert _looks_like_jsx("return (<div><span>hi</span></div>)")
        assert _looks_like_jsx("const x = <Foo />")
        assert not _looks_like_jsx("const x: number = a < b ? 1 : 2")

    def test_tsx_temp_suffix_and_jsx_flag(self, profile):
        """A .tsx file is written to a .tsx temp and tsc gets --jsx preserve."""
        from unittest.mock import MagicMock
        captured = {}

        def fake_run(cmd, **kwargs):
            captured["cmd"] = cmd
            return MagicMock(returncode=0, stdout="", stderr="")

        with patch("shutil.which", side_effect=lambda t: "/usr/bin/tsc" if t == "tsc" else None):
            with patch("subprocess.run", side_effect=fake_run):
                valid, _ = profile._validate_typescript(
                    "export default () => (<div/>)", filename_hint="app/layout.tsx",
                )
        assert valid is True
        assert "--jsx" in captured["cmd"]
        assert captured["cmd"][-1].endswith(".tsx")
