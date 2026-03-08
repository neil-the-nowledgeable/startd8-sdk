"""
Unit tests for deterministic element ID generation.

Covers:
  - Determinism: identical inputs → identical outputs, always
  - Uniqueness: distinct inputs → distinct outputs
  - Path normalization: semantically equivalent paths → identical IDs
  - Round-trip / format safety: IDs are non-empty, whitespace-free, shell-safe strings
  - Parameter sensitivity: changing any single parameter changes the ID
  - Edge cases: empty strings, line=0, negative lines, long names, unicode, etc.

Requires:
  pytest >= 7.0
  startd8.element_id.make_element_id(kind, name, file_path=None, parent_class=None, line=None)
"""

import os
import re
import pytest
from pathlib import Path

from startd8.element_id import make_element_id


# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

# Characters that are safe for shell invocation, filesystem use, and URLs.
_SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_.:\-]+$")

_SAMPLE_KINDS = ["function", "class", "method", "constant", "module"]
_SAMPLE_NAMES = ["my_func", "MyClass", "process_data", "_private", "CONSTANT"]


# ---------------------------------------------------------------------------
# TestDeterminism
# ---------------------------------------------------------------------------


class TestDeterminism:
    """make_element_id() must return the identical string on every call."""

    def test_same_args_same_id_no_optional(self):
        """Minimal call (kind + name only) is reproducible."""
        id1 = make_element_id("function", "my_func")
        id2 = make_element_id("function", "my_func")
        assert id1 == id2

    def test_same_args_same_id_all_params(self):
        """All five parameters — result is stable across calls."""
        kwargs = dict(
            kind="method",
            name="process",
            file_path="src/startd8/engine.py",
            parent_class="MicroPrimeEngine",
            line=42,
        )
        id1 = make_element_id(**kwargs)
        id2 = make_element_id(**kwargs)
        assert id1 == id2

    def test_determinism_across_call_order(self):
        """Generating ID for A then B yields same A-ID as B then A."""
        id_a_first = make_element_id("function", "alpha", file_path="src/a.py")
        _id_b = make_element_id("function", "beta", file_path="src/b.py")  # interleaved call
        id_a_second = make_element_id("function", "alpha", file_path="src/a.py")
        assert id_a_first == id_a_second

    @pytest.mark.parametrize(
        "kind,name,file_path,parent_class,line",
        [
            ("function", "foo", None, None, None),
            ("function", "foo", "src/mod.py", None, None),
            ("function", "foo", "src/mod.py", "MyClass", None),
            ("function", "foo", "src/mod.py", "MyClass", 10),
            ("class", "Bar", "src/bar.py", None, None),
            ("method", "baz", "src/bar.py", "Bar", 55),
            ("constant", "MAX_RETRIES", "src/config.py", None, None),
        ],
        ids=[
            "fn-no-opts",
            "fn-with-file",
            "fn-file-parent",
            "fn-all-params",
            "class-with-file",
            "method-full",
            "constant",
        ],
    )
    def test_parametrized_determinism(self, kind, name, file_path, parent_class, line):
        """Every parameter combination is self-consistent across two independent calls."""
        id1 = make_element_id(kind, name, file_path, parent_class, line)
        id2 = make_element_id(kind, name, file_path, parent_class, line)
        assert id1 == id2, (
            f"Non-deterministic for ({kind}, {name}, {file_path}, {parent_class}, {line})"
        )


# ---------------------------------------------------------------------------
# TestUniqueness
# ---------------------------------------------------------------------------


class TestUniqueness:
    """Distinct inputs must produce distinct IDs."""

    def test_different_kinds_same_name(self):
        """Different kind values produce different IDs for the same name."""
        ids = [make_element_id(kind, "do_thing") for kind in _SAMPLE_KINDS]
        assert len(ids) == len(set(ids)), "Different kinds collided"

    def test_different_names_same_kind(self):
        """Different name values produce different IDs for the same kind."""
        ids = [make_element_id("function", name) for name in _SAMPLE_NAMES]
        assert len(ids) == len(set(ids)), "Different names collided"

    def test_same_name_different_file(self):
        """Same name but different file_path produces different IDs."""
        files = ["src/a.py", "src/b.py", "src/c.py", "tests/test_a.py"]
        ids = [
            make_element_id("function", "helper", file_path=file_path)
            for file_path in files
        ]
        assert len(ids) == len(set(ids))

    def test_same_name_different_parent_class(self):
        """Same name but different parent_class produces different IDs."""
        parents = ["Alpha", "Beta", "Gamma", None]
        ids = [
            make_element_id("method", "run", file_path="src/x.py", parent_class=parent)
            for parent in parents
        ]
        assert len(ids) == len(set(ids))

    def test_same_name_different_line(self):
        """Same name but different line number produces different IDs."""
        lines = [1, 10, 100, 1000, None]
        ids = [
            make_element_id("function", "handler", file_path="src/x.py", line=line_num)
            for line_num in lines
        ]
        assert len(ids) == len(set(ids))

    def test_file_vs_no_file_unique(self):
        """Adding file_path to an otherwise identical call changes the ID."""
        id_no_file = make_element_id("function", "helper")
        id_with_file = make_element_id("function", "helper", file_path="src/helpers.py")
        assert id_no_file != id_with_file

    def test_no_collision_across_full_matrix(self):
        """≥ 20 distinct input tuples must all produce unique IDs."""
        inputs = [
            # (kind, name, file_path, parent_class, line)
            ("function", "foo", None, None, None),
            ("function", "bar", None, None, None),
            ("class", "foo", None, None, None),
            ("class", "Foo", None, None, None),          # case-sensitive names
            ("method", "foo", None, None, None),
            ("function", "foo", "src/a.py", None, None),
            ("function", "foo", "src/b.py", None, None),
            ("function", "foo", "src/a.py", "MyClass", None),
            ("function", "foo", "src/a.py", "OtherClass", None),
            ("function", "foo", "src/a.py", None, 1),
            ("function", "foo", "src/a.py", None, 2),
            ("function", "foo", "src/a.py", "MyClass", 1),
            ("function", "foo", "src/a.py", "MyClass", 2),
            ("method", "run", "src/engine.py", "Engine", 10),
            ("method", "run", "src/engine.py", "Engine", 11),
            ("method", "run", "src/runner.py", "Engine", 10),
            ("constant", "MAX", "src/config.py", None, None),
            ("constant", "MIN", "src/config.py", None, None),
            ("module", "startd8", None, None, None),
            ("function", "_private", "src/util.py", None, 99),
            ("function", "UPPER_CASE", "src/util.py", None, None),
        ]
        assert len(inputs) >= 20, "Test matrix must contain at least 20 entries"
        ids = [
            make_element_id(kind, name, file_path, parent_class, line)
            for kind, name, file_path, parent_class, line in inputs
        ]
        assert len(ids) == len(set(ids)), (
            f"Collision detected among {len(inputs)} distinct inputs"
        )


# ---------------------------------------------------------------------------
# TestPathNormalization
# ---------------------------------------------------------------------------


class TestPathNormalization:
    """Semantically equivalent file paths must produce the same ID."""

    def test_relative_vs_absolute_same_id(self):
        """Relative path and its absolute counterpart produce the same ID."""
        rel = "src/startd8/engine.py"
        abs_path = os.path.join(os.getcwd(), "src/startd8/engine.py")
        id_rel = make_element_id("function", "run", file_path=rel)
        id_abs = make_element_id("function", "run", file_path=abs_path)
        assert id_rel == id_abs, "Relative and absolute paths must yield the same ID"

    def test_forward_vs_backslash_same_id(self):
        """Windows-style backslash path equals the POSIX forward-slash form."""
        posix_path = "src/startd8/engine.py"
        win_path = "src\\startd8\\engine.py"
        id_posix = make_element_id("function", "run", file_path=posix_path)
        id_win = make_element_id("function", "run", file_path=win_path)
        assert id_posix == id_win, "Path separator style must not affect the ID"

    def test_dot_segments_normalized(self):
        """Single-dot (current-directory) segments are eliminated."""
        clean = "src/startd8/engine.py"
        dotted = "src/./startd8/./engine.py"
        id_clean = make_element_id("function", "run", file_path=clean)
        id_dotted = make_element_id("function", "run", file_path=dotted)
        assert id_clean == id_dotted, "Dot segments must be normalized away"

    def test_double_dot_segments_normalized(self):
        """Double-dot segments are resolved before comparison."""
        clean = "src/startd8/engine.py"
        double_dotted = "src/startd8/sub/../engine.py"
        id_clean = make_element_id("function", "run", file_path=clean)
        id_double = make_element_id("function", "run", file_path=double_dotted)
        assert id_clean == id_double, "Double-dot segments must be resolved"

    def test_trailing_slash_normalized(self):
        """A path built with os.path.join (no trailing slash) equals the string form."""
        path_str = "src/startd8/engine.py"
        path_joined = os.path.join("src", "startd8", "engine.py")
        id_str = make_element_id("function", "run", file_path=path_str)
        id_joined = make_element_id("function", "run", file_path=path_joined)
        assert id_str == id_joined

    def test_pathlib_path_vs_string_same_id(self):
        """pathlib.Path converted to str is equivalent to the literal string."""
        str_path = "src/startd8/engine.py"
        path_obj = Path("src/startd8/engine.py")
        id_str = make_element_id("function", "run", file_path=str_path)
        id_path = make_element_id("function", "run", file_path=str(path_obj))
        assert id_str == id_path

    def test_nonexistent_path_does_not_raise(self):
        """Path normalization must not require the file to actually exist."""
        fake_path = "/nonexistent/deep/path/module.py"
        result = make_element_id("function", "ghost", file_path=fake_path)
        assert isinstance(result, str) and len(result) > 0


# ---------------------------------------------------------------------------
# TestRoundTrip
# ---------------------------------------------------------------------------


class TestRoundTrip:
    """The returned ID string must be non-empty, whitespace-free, and shell-safe."""

    def test_id_is_nonempty_string(self):
        """Result must be a non-empty str."""
        result = make_element_id("function", "my_func")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_id_has_no_whitespace(self):
        """ID must not contain any whitespace, even when the name contains a space."""
        result = make_element_id("function", "my func")
        assert " " not in result
        assert "\t" not in result
        assert "\n" not in result

    def test_id_safe_characters_only(self):
        """ID must match ^[A-Za-z0-9_.:\\-]+$ for shell and filesystem safety."""
        for kind in _SAMPLE_KINDS:
            for name in _SAMPLE_NAMES:
                result = make_element_id(kind, name, file_path="src/mod.py")
                assert _SAFE_ID_RE.match(result), (
                    f"Unsafe characters in ID {result!r} for ({kind!r}, {name!r})"
                )

    def test_id_contains_kind(self):
        """The kind token must appear verbatim (case-insensitive) in the ID."""
        for kind in _SAMPLE_KINDS:
            result = make_element_id(kind, "some_name")
            assert kind.lower() in result.lower(), (
                f"Kind {kind!r} not found in ID {result!r}"
            )

    def test_id_contains_name_or_slug(self):
        """The name (or its slug) must appear recognizably in the ID."""
        for name in _SAMPLE_NAMES:
            result = make_element_id("function", name)
            slug = name.lower().replace("_", "").replace("-", "")
            result_normalized = result.lower().replace("_", "").replace("-", "")
            assert slug in result_normalized, (
                f"Name {name!r} (slug {slug!r}) not found in ID {result!r}"
            )

    @pytest.mark.parametrize(
        "kind,name",
        [
            ("function", "alpha"),
            ("class", "MyClass"),
            ("method", "process_data"),
            ("constant", "MAX_RETRIES"),
            ("module", "startd8"),
        ],
        ids=["function", "class", "method", "constant", "module"],
    )
    def test_id_format_consistent_across_calls(self, kind, name):
        """ID format and length are stable: same inputs always produce the same ID."""
        id1 = make_element_id(kind, name, file_path="src/mod.py")
        id2 = make_element_id(kind, name, file_path="src/mod.py")
        assert id1 == id2
        assert _SAFE_ID_RE.match(id1)
        assert len(id1) == len(id2)


# ---------------------------------------------------------------------------
# TestParameterSensitivity
# ---------------------------------------------------------------------------


class TestParameterSensitivity:
    """Changing any single parameter must change the output ID."""

    _BASE = dict(
        kind="function",
        name="process",
        file_path="src/engine.py",
        parent_class="MyEngine",
        line=42,
    )

    def _make(self, **overrides):
        """Build and call make_element_id with base kwargs overridden as specified."""
        args = {**self._BASE, **overrides}
        return make_element_id(
            args["kind"],
            args["name"],
            file_path=args["file_path"],
            parent_class=args["parent_class"],
            line=args["line"],
        )

    def test_changing_kind_changes_id(self):
        id_a = self._make(kind="function")
        id_b = self._make(kind="class")
        assert id_a != id_b

    def test_changing_name_changes_id(self):
        id_a = self._make(name="process")
        id_b = self._make(name="process_v2")
        assert id_a != id_b

    def test_adding_file_path_changes_id(self):
        """Adding file_path where there was none changes the ID."""
        id_no_file = make_element_id("function", "process")
        id_with_file = make_element_id("function", "process", file_path="src/engine.py")
        assert id_no_file != id_with_file

    def test_changing_file_path_changes_id(self):
        id_a = self._make(file_path="src/engine.py")
        id_b = self._make(file_path="src/other_engine.py")
        assert id_a != id_b

    def test_adding_parent_class_changes_id(self):
        """Adding parent_class where there was None changes the ID."""
        id_no_parent = self._make(parent_class=None)
        id_with_parent = self._make(parent_class="SomeClass")
        assert id_no_parent != id_with_parent

    def test_changing_parent_class_changes_id(self):
        id_a = self._make(parent_class="Alpha")
        id_b = self._make(parent_class="Beta")
        assert id_a != id_b

    def test_adding_line_changes_id(self):
        """Adding a line number where there was None changes the ID."""
        id_no_line = self._make(line=None)
        id_with_line = self._make(line=1)
        assert id_no_line != id_with_line

    def test_changing_line_changes_id(self):
        id_a = self._make(line=1)
        id_b = self._make(line=2)
        assert id_a != id_b

    @pytest.mark.parametrize(
        "param,sentinel",
        [
            ("file_path", None),
            ("parent_class", None),
            ("line", None),
        ],
        ids=["file_path-none", "parent_class-none", "line-none"],
    )
    def test_none_vs_omitted_equivalent(self, param, sentinel):
        """Passing param=None explicitly must equal omitting the parameter entirely."""
        explicit_none_args = {"kind": "function", "name": "do_thing", param: None}
        id_explicit = make_element_id(**explicit_none_args)

        omitted_args = {"kind": "function", "name": "do_thing"}
        id_omitted = make_element_id(**omitted_args)

        assert id_explicit == id_omitted, (
            f"Explicit {param}=None must equal omitting {param}"
        )


# ---------------------------------------------------------------------------
# Edge-case tests (module-level)
# ---------------------------------------------------------------------------


def test_empty_name_returns_valid_id():
    """Empty string name should return a valid, non-empty ID without raising."""
    result = make_element_id("function", "")
    assert isinstance(result, str) and len(result) > 0


def test_empty_name_differs_from_nonempty_name():
    """Empty name and a single-character name must produce different IDs."""
    id_empty = make_element_id("function", "")
    id_named = make_element_id("function", "a")
    assert id_empty != id_named


def test_empty_kind_returns_valid_id():
    """Empty string kind should return a valid, non-empty ID without raising."""
    result = make_element_id("", "my_func")
    assert isinstance(result, str) and len(result) > 0


def test_empty_kind_differs_from_nonempty_kind():
    """Empty kind and a non-empty kind must produce different IDs."""
    id_empty = make_element_id("", "my_func")
    id_kinded = make_element_id("class", "my_func")
    assert id_empty != id_kinded


def test_line_zero_returns_valid_id():
    """line=0 is a valid sentinel and should return a non-empty ID."""
    result = make_element_id("function", "f", line=0)
    assert isinstance(result, str) and len(result) > 0


def test_line_zero_differs_from_none():
    """line=0 and line=None are semantically distinct and must yield different IDs."""
    id_zero = make_element_id("function", "f", line=0)
    id_none = make_element_id("function", "f", line=None)
    assert id_zero != id_none


def test_line_zero_differs_from_one():
    """line=0 and line=1 must produce different IDs."""
    id_zero = make_element_id("function", "f", line=0)
    id_one = make_element_id("function", "f", line=1)
    assert id_zero != id_one


def test_line_negative_does_not_raise():
    """Negative line numbers must not raise; produce a valid non-empty ID."""
    result = make_element_id("function", "f", line=-1)
    assert isinstance(result, str) and len(result) > 0


def test_very_long_name_does_not_raise():
    """A 500-character name must not raise and the resulting ID must be safe."""
    long_name = "x" * 500
    result = make_element_id("function", long_name)
    assert isinstance(result, str) and len(result) > 0
    assert _SAFE_ID_RE.match(result), f"Long name produced unsafe ID: {result!r}"


def test_filename_only_path_does_not_raise():
    """file_path with no directory component should not raise."""
    result = make_element_id("function", "f", file_path="module.py")
    assert isinstance(result, str) and len(result) > 0


def test_qualified_parent_class_with_dots():
    """A dotted (qualified) parent_class must not raise and must yield a safe ID."""
    result = make_element_id("method", "run", parent_class="Outer.Inner")
    assert isinstance(result, str) and len(result) > 0
    assert _SAFE_ID_RE.match(result), f"Unsafe ID for dotted parent: {result!r}"


def test_parent_class_with_dots_differs_from_simple():
    """Qualified parent 'Outer.Inner' and simple parent 'Inner' must differ."""
    id_dotted = make_element_id("method", "run", parent_class="Outer.Inner")
    id_simple = make_element_id("method", "run", parent_class="Inner")
    assert id_dotted != id_simple


def test_unicode_name_does_not_raise():
    """
    Unicode names should either produce a valid non-empty ID or raise
    TypeError/ValueError (both outcomes are explicitly acceptable).
    """
    try:
        result = make_element_id("function", "résumé")
        assert isinstance(result, str) and len(result) > 0
    except (TypeError, ValueError):
        # Explicitly documented: unicode input may be rejected by the implementation.
        pass


def test_windows_path_separator_produces_valid_id():
    """Windows-style backslash separators must not raise; produce a valid ID."""
    result = make_element_id("function", "f", file_path="src\\mymodule\\file.py")
    assert isinstance(result, str) and len(result) > 0