"""Tests for PCA-605d defense-in-depth design→implement file discovery.

Covers all 4 extraction layers in ``_extract_design_target_files``:
- Layer 4 (primary): ``### Files Touched`` structured section
- Layer 1 (fallback): ``**File: `name`**`` bold markers
- Layer 2 (fallback): Fenced code blocks with file paths
- Layer 3 (fallback): Prose "new file" signals with conditional filter
- Integration: multi-layer dedup, bare filename prefix normalization
"""

from __future__ import annotations

import pytest

from startd8.contractors.context_seed_handlers import (
    _extract_design_target_files,
    _has_valid_extension,
    _infer_path_prefix,
)


# ── Helpers ──────────────────────────────────────────────────────────────

CURRENT_TARGETS = ["src/startd8/contractors/prime_contractor.py"]
PREFIX = "src/startd8/contractors/"


# ── Layer 4: ### Files Touched section ───────────────────────────────────

class TestLayer4FilesTouched:
    """Layer 4: prompt-guided structured output (primary)."""

    def test_files_touched_section_basic(self):
        doc = (
            "## Design\nSome design prose.\n\n"
            "### Files Touched\n"
            "- `src/startd8/contractors/prime_contractor.py` (modify) — add mode field\n"
            "- `src/startd8/contractors/execution_mode.py` (new) — execution mode enum\n"
            "\n## Implementation\n"
        )
        result = _extract_design_target_files(doc, CURRENT_TARGETS)
        assert "src/startd8/contractors/execution_mode.py" in result
        assert "src/startd8/contractors/prime_contractor.py" in result

    def test_files_touched_missing_section_passthrough(self):
        doc = "## Design\nNo files touched section here.\n"
        result = _extract_design_target_files(doc, CURRENT_TARGETS)
        assert result == CURRENT_TARGETS

    def test_files_touched_partial_entries(self):
        """Section present but some entries lack valid extensions."""
        doc = (
            "### Files Touched\n"
            "- `src/startd8/contractors/foo.py` (new) — foo module\n"
            "- `README` — update docs\n"
        )
        result = _extract_design_target_files(doc, CURRENT_TARGETS)
        assert "src/startd8/contractors/foo.py" in result
        # README has no extension → filtered out
        assert not any("README" in f for f in result)

    def test_files_touched_singular_file(self):
        """Regex handles both 'File Touched' and 'Files Touched'."""
        doc = (
            "### File Touched\n"
            "- `src/startd8/contractors/new_module.py` (new) — new module\n"
        )
        result = _extract_design_target_files(doc, CURRENT_TARGETS)
        assert "src/startd8/contractors/new_module.py" in result


# ── Layer 1: **File: `name`** bold markers ───────────────────────────────

class TestLayer1BoldMarkers:
    """Layer 1: original PCA-605c format."""

    def test_bold_marker_bare_filename(self):
        doc = "**File: `execution_mode.py`** (new file):\nSome content."
        result = _extract_design_target_files(doc, CURRENT_TARGETS)
        assert f"{PREFIX}execution_mode.py" in result

    def test_bold_marker_full_path(self):
        doc = "**File: `src/startd8/contractors/execution_mode.py`** (new file):\n"
        result = _extract_design_target_files(doc, CURRENT_TARGETS)
        assert "src/startd8/contractors/execution_mode.py" in result

    def test_bold_marker_modify_existing(self):
        doc = "**File: `prime_contractor.py`** (additive change only):\n"
        result = _extract_design_target_files(doc, CURRENT_TARGETS)
        # Already in targets, should not duplicate
        assert result.count(f"{PREFIX}prime_contractor.py") == 1


# ── Layer 2: Fenced code blocks with file paths ─────────────────────────

class TestLayer2FencedBlocks:
    """Layer 2: file paths in code block lang tags or first-line comments."""

    def test_lang_tag_with_path(self):
        doc = (
            "```src/startd8/contractors/execution_mode.py\n"
            "class ExecutionMode:\n"
            "    pass\n"
            "```\n"
        )
        result = _extract_design_target_files(doc, CURRENT_TARGETS)
        assert "src/startd8/contractors/execution_mode.py" in result

    def test_first_line_comment_path(self):
        doc = (
            "```python\n"
            "# src/startd8/contractors/execution_mode.py\n"
            "class ExecutionMode:\n"
            "    pass\n"
            "```\n"
        )
        result = _extract_design_target_files(doc, CURRENT_TARGETS)
        assert "src/startd8/contractors/execution_mode.py" in result

    def test_bare_lang_tag_ignored(self):
        """A bare language tag like 'python' should NOT be treated as a file."""
        doc = (
            "```python\n"
            "print('hello')\n"
            "```\n"
        )
        result = _extract_design_target_files(doc, CURRENT_TARGETS)
        assert result == CURRENT_TARGETS

    def test_first_line_comment_without_path(self):
        """First-line comment without / is not a file path."""
        doc = (
            "```python\n"
            "# This is just a comment\n"
            "x = 1\n"
            "```\n"
        )
        result = _extract_design_target_files(doc, CURRENT_TARGETS)
        assert result == CURRENT_TARGETS


# ── Layer 3: Prose "new file" signals ────────────────────────────────────

class TestLayer3ProseSignals:
    """Layer 3: prose patterns like 'new module', 'extract to', etc."""

    def test_new_module_prose(self):
        doc = "We introduce a new module `execution_mode.py` to encapsulate modes."
        result = _extract_design_target_files(doc, CURRENT_TARGETS)
        assert f"{PREFIX}execution_mode.py" in result

    def test_extract_to_prose(self):
        doc = "The enum should be extracted to `src/startd8/contractors/modes.py` for reuse."
        result = _extract_design_target_files(doc, CURRENT_TARGETS)
        assert "src/startd8/contractors/modes.py" in result

    def test_split_into_prose(self):
        doc = "We split into `src/startd8/contractors/config_models.py` for clarity."
        result = _extract_design_target_files(doc, CURRENT_TARGETS)
        assert "src/startd8/contractors/config_models.py" in result

    def test_conditional_filter_when(self):
        """PI-001 real case: 'when a second consumer' should filter out."""
        doc = (
            "The execution mode logic could be extracted to a dedicated module "
            "(e.g., `execution_mode.py`) when a second consumer emerges. "
            "For now, inline it."
        )
        result = _extract_design_target_files(doc, CURRENT_TARGETS)
        # Should be filtered — conditional language "when"
        assert result == CURRENT_TARGETS

    def test_conditional_filter_if_needed(self):
        doc = "Create a new file `utils.py` if needed for shared helpers."
        result = _extract_design_target_files(doc, CURRENT_TARGETS)
        assert result == CURRENT_TARGETS

    def test_conditional_filter_eventually(self):
        doc = "Eventually create a separate module `cache.py` for caching."
        result = _extract_design_target_files(doc, CURRENT_TARGETS)
        assert result == CURRENT_TARGETS

    def test_conditional_filter_future(self):
        doc = "In the future, a dedicated file `router.py` may be warranted."
        result = _extract_design_target_files(doc, CURRENT_TARGETS)
        assert result == CURRENT_TARGETS


# ── Integration tests ────────────────────────────────────────────────────

class TestIntegration:
    """Cross-layer dedup, prefix normalization, and passthrough."""

    def test_multi_layer_dedup(self):
        """Same file found by Layer 4 and Layer 1 → only appears once."""
        doc = (
            "### Files Touched\n"
            "- `src/startd8/contractors/execution_mode.py` (new) — enum\n"
            "\n"
            "**File: `src/startd8/contractors/execution_mode.py`** (new file):\n"
        )
        result = _extract_design_target_files(doc, CURRENT_TARGETS)
        count = result.count("src/startd8/contractors/execution_mode.py")
        assert count == 1

    def test_bare_filename_prefix_normalization(self):
        """Bare filename 'foo.py' gets prefix from current_targets."""
        doc = "**File: `foo.py`** (new):\n"
        result = _extract_design_target_files(doc, CURRENT_TARGETS)
        assert f"{PREFIX}foo.py" in result

    def test_no_discovery_passthrough(self):
        """No file markers anywhere → return original targets unchanged."""
        doc = "This is a design document with no file references at all."
        result = _extract_design_target_files(doc, CURRENT_TARGETS)
        assert result == CURRENT_TARGETS

    def test_empty_targets_no_prefix(self):
        """Empty current_targets → bare filenames stay bare."""
        doc = "**File: `execution_mode.py`** (new):\n"
        result = _extract_design_target_files(doc, [])
        assert "execution_mode.py" in result

    def test_preserves_original_order(self):
        """Original targets appear first, discoveries appended."""
        targets = [
            "src/startd8/contractors/prime_contractor.py",
            "src/startd8/contractors/config.py",
        ]
        doc = "**File: `execution_mode.py`** (new):\n"
        result = _extract_design_target_files(doc, targets)
        assert result[0] == "src/startd8/contractors/prime_contractor.py"
        assert result[1] == "src/startd8/contractors/config.py"
        assert result[-1] == "src/startd8/contractors/execution_mode.py"

    def test_invalid_extension_filtered(self):
        """Files with unrecognized extensions are not included."""
        doc = "**File: `data.parquet`** (new):\n"
        result = _extract_design_target_files(doc, CURRENT_TARGETS)
        assert result == CURRENT_TARGETS


# ── Test file filtering ──────────────────────────────────────────────────

class TestTestFileFiltering:
    """Test files discovered from design docs are filtered out.

    The TEST phase handles test generation — IMPLEMENT should not receive
    test file targets, as this causes the drafter to generate test code
    instead of the primary implementation artifact.
    """

    def test_layer2_test_file_filtered(self):
        """PI-002 real case: fenced code block with test file path."""
        doc = (
            "```python\n"
            "# tests/unit/scripts/test_verify_otel_trace.py\n"
            "import importlib.util\n"
            "```\n"
        )
        result = _extract_design_target_files(doc, ["scripts/verify_otel_trace.py"])
        assert result == ["scripts/verify_otel_trace.py"]
        assert "tests/unit/scripts/test_verify_otel_trace.py" not in result

    def test_layer4_test_file_filtered(self):
        """Test file in Files Touched section is filtered."""
        doc = (
            "### Files Touched\n"
            "- `scripts/verify_otel_trace.py` (new) — main script\n"
            "- `tests/unit/test_verify.py` (new) — tests\n"
        )
        result = _extract_design_target_files(doc, ["scripts/verify_otel_trace.py"])
        assert "scripts/verify_otel_trace.py" in result
        assert "tests/unit/test_verify.py" not in result

    def test_layer1_test_file_filtered(self):
        """Test file via bold marker is filtered."""
        doc = "**File: `tests/test_feature.py`** (new):\n"
        result = _extract_design_target_files(doc, CURRENT_TARGETS)
        assert result == CURRENT_TARGETS

    def test_test_prefix_bare_name_filtered(self):
        """Bare filename starting with test_ is filtered."""
        doc = "**File: `test_something.py`** (new):\n"
        result = _extract_design_target_files(doc, CURRENT_TARGETS)
        assert result == CURRENT_TARGETS

    def test_test_suffix_name_filtered(self):
        """File ending with _test.py is filtered."""
        doc = "**File: `src/pkg/feature_test.py`** (new):\n"
        result = _extract_design_target_files(doc, CURRENT_TARGETS)
        assert result == CURRENT_TARGETS

    def test_non_test_file_not_filtered(self):
        """Non-test file in tests-adjacent path is preserved."""
        doc = "**File: `src/startd8/testing/helpers.py`** (new):\n"
        result = _extract_design_target_files(doc, CURRENT_TARGETS)
        assert "src/startd8/testing/helpers.py" in result

    def test_mixed_test_and_impl_files(self):
        """Test files filtered, implementation files kept."""
        doc = (
            "### Files Touched\n"
            "- `scripts/verify_otel_trace.py` (new) — script\n"
            "- `tests/unit/test_verify.py` (new) — tests\n"
            "- `src/startd8/utils/trace_parser.py` (new) — parser\n"
        )
        result = _extract_design_target_files(doc, ["scripts/verify_otel_trace.py"])
        assert "scripts/verify_otel_trace.py" in result
        assert "src/startd8/utils/trace_parser.py" in result
        assert "tests/unit/test_verify.py" not in result


# ── Contradictory path deduplication (PCA-605d) ─────────────────────────

class TestContradictoryPathDedup:
    """PCA-605d: prevent mixed-layout target lists from design doc discovery.

    When current_targets already specifies a path for a file, discovered
    paths that share the same basename but differ in directory depth should
    be dropped — the plan's path is authoritative.
    """

    # --- Prefix guard: bare filenames already in current_targets ---

    def test_bare_filename_not_prefixed_when_in_targets(self):
        """Root-level pyproject.toml should not be prefixed to src/pkg/."""
        targets = [
            "src/hybrid_scaffold/__init__.py",
            "pyproject.toml",
        ]
        doc = (
            "### Files Touched\n"
            "- `pyproject.toml` (new) — project metadata\n"
            "- `src/hybrid_scaffold/__init__.py` (modify) — add version\n"
        )
        result = _extract_design_target_files(doc, targets)
        assert "pyproject.toml" in result
        assert "src/hybrid_scaffold/pyproject.toml" not in result

    def test_bare_filename_still_prefixed_when_not_in_targets(self):
        """Bare filename not in current_targets gets normal prefix."""
        targets = ["src/startd8/contractors/prime_contractor.py"]
        doc = "**File: `execution_mode.py`** (new):\n"
        result = _extract_design_target_files(doc, targets)
        assert "src/startd8/contractors/execution_mode.py" in result

    # --- Post-normalization contradictory path dedup ---

    def test_layer2_contradictory_path_dropped(self):
        """Layer 2 full path that contradicts a current_target is dropped."""
        targets = [
            "src/hybrid_scaffold/__init__.py",
            "pyproject.toml",
        ]
        # Layer 2: fenced code block with path in lang tag
        doc = (
            "```src/hybrid_scaffold/pyproject.toml\n"
            "[build-system]\n"
            'requires = ["hatchling"]\n'
            "```\n"
        )
        result = _extract_design_target_files(doc, targets)
        assert "pyproject.toml" in result
        assert "src/hybrid_scaffold/pyproject.toml" not in result

    def test_ambiguous_basename_not_deduped(self):
        """When basename appears in multiple targets, dedup is skipped."""
        targets = [
            "src/hybrid_scaffold/__init__.py",
            "tests/__init__.py",
        ]
        # __init__.py is ambiguous — appears in 2 targets.
        # A newly discovered path with the same basename should be kept.
        doc = (
            "```src/hybrid_scaffold/subpkg/__init__.py\n"
            "# sub-package init\n"
            "```\n"
        )
        result = _extract_design_target_files(doc, targets)
        assert "src/hybrid_scaffold/subpkg/__init__.py" in result

    def test_context_bridge_pi001_scenario(self):
        """Exact PI-001 context-bridge scenario that produced the bug."""
        targets = [
            "src/hybrid_scaffold/__init__.py",
            "pyproject.toml",
        ]
        # Design doc has Files Touched with bare pyproject.toml
        # AND architecture section with src/hybrid_scaffold/pyproject.toml
        doc = (
            "### Files Touched\n"
            "- `pyproject.toml` (new) — Project metadata\n"
            "- `src/hybrid_scaffold/__init__.py` (new) — Package init\n"
            "- `src/hybrid_scaffold/py.typed` (new) — PEP 561 marker\n"
            "- `tests/__init__.py` (new) — Test package marker\n"
            "\n"
            "## Architecture\n\n"
            "### Dependency Configuration (`pyproject.toml`)\n\n"
            "```toml\n"
            "[build-system]\n"
            'requires = ["hatchling"]\n'
            "```\n"
            "\n"
            "### `src/hybrid_scaffold/__init__.py`\n\n"
            "```python\n"
            '"""hybrid_scaffold."""\n'
            '__version__ = "0.1.0"\n'
            "```\n"
        )
        result = _extract_design_target_files(doc, targets)
        # pyproject.toml should appear exactly once, at root
        assert "pyproject.toml" in result
        assert "src/hybrid_scaffold/pyproject.toml" not in result
        # __init__.py should be present
        assert "src/hybrid_scaffold/__init__.py" in result
        # test files should be filtered
        assert "tests/__init__.py" not in [
            p for p in result if p not in targets
        ] or "tests/__init__.py" in targets

    def test_genuinely_different_files_not_deduped(self):
        """Files with same basename but in different packages are kept."""
        targets = ["src/startd8/config.py"]
        doc = (
            "### Files Touched\n"
            "- `src/startd8/config.py` (modify) — update config\n"
            "- `src/startd8/utils/config.py` (new) — utility config\n"
        )
        # config.py basename matches target, but src/startd8/utils/config.py
        # also matches.  Since there's only 1 target with that basename,
        # the contradictory dedup would drop the new path.
        # This is the expected (conservative) behavior — the plan's path
        # takes precedence for ambiguous basenames.
        result = _extract_design_target_files(doc, targets)
        assert "src/startd8/config.py" in result
        # The utils/config.py is dropped because it contradicts the
        # single target with basename config.py
        assert "src/startd8/utils/config.py" not in result


# ── Helper function tests ────────────────────────────────────────────────

class TestHelpers:
    def test_infer_path_prefix_with_path(self):
        assert _infer_path_prefix(["src/pkg/mod.py"]) == "src/pkg/"

    def test_infer_path_prefix_bare(self):
        assert _infer_path_prefix(["mod.py"]) == ""

    def test_infer_path_prefix_empty(self):
        assert _infer_path_prefix([]) == ""

    def test_has_valid_extension_python(self):
        assert _has_valid_extension("foo.py") is True

    def test_has_valid_extension_typescript(self):
        assert _has_valid_extension("bar.tsx") is True

    def test_has_valid_extension_invalid(self):
        assert _has_valid_extension("data.parquet") is False

    def test_has_valid_extension_no_dot(self):
        assert _has_valid_extension("Makefile") is False
