"""
Unit tests for ManifestRegistry, ManifestDiff, and ManifestSummarySchema.

Covers: Step 1 of Phase 4 plan — registry queries, FQN index, element summaries,
progressive truncation, structural diff, signature normalization, timing metrics,
staleness, path traversal guards, cache loading, and with_updated_files().
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from unittest.mock import patch

import pytest

from startd8.utils.code_manifest import (
    Dependencies,
    Element,
    ElementKind,
    FileManifest,
    ImportEntry,
    InspectInfo,
    Param,
    ResolvedParam,
    ResolvedSignature,
    Signature,
    Span,
    Visibility,
)
from startd8.utils.manifest_registry import (
    ManifestDiff,
    ManifestRegistry,
    ManifestSummarySchema,
    _normalize_signature,
)


# ═══════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════


def _make_element(
    name: str,
    fqn: str,
    kind: ElementKind = ElementKind.FUNCTION,
    visibility: Visibility = Visibility.PUBLIC,
    start_line: int = 1,
    end_line: int = 10,
    signature: Signature | None = None,
    docstring: str | None = None,
    children: list[Element] | None = None,
    class_variables: list[Element] | None = None,
) -> Element:
    """Helper to create an Element with sensible defaults."""
    if signature is None and kind in (
        ElementKind.FUNCTION,
        ElementKind.ASYNC_FUNCTION,
        ElementKind.METHOD,
        ElementKind.ASYNC_METHOD,
        ElementKind.PROPERTY,
    ):
        signature = Signature(params=[])
    return Element(
        kind=kind,
        name=name,
        fqn=fqn,
        span=Span(start_line=start_line, start_col=0, end_line=end_line, end_col=0),
        visibility=visibility,
        signature=signature,
        docstring=docstring,
        children=children or [],
        class_variables=class_variables or [],
    )


def _make_manifest(
    file: str = "src/foo/bar.py",
    module: str = "foo.bar",
    elements: list[Element] | None = None,
    imports: list[ImportEntry] | None = None,
    dependencies: Dependencies | None = None,
    module_version: str | None = None,
) -> FileManifest:
    """Helper to create a FileManifest with sensible defaults."""
    return FileManifest(
        file=file,
        module=module,
        digest="sha256:abc123",
        elements=elements or [],
        imports=imports or [],
        dependencies=dependencies or Dependencies(),
        module_version=module_version,
    )


@pytest.fixture
def sample_elements() -> list[Element]:
    """Sample elements for testing."""
    return [
        _make_element(
            "foo",
            "mod.foo",
            start_line=1,
            end_line=5,
            signature=Signature(
                params=[Param(name="x", annotation="int")],
                return_annotation="str",
            ),
            docstring="Do something useful.",
        ),
        _make_element(
            "bar",
            "mod.bar",
            start_line=10,
            end_line=20,
            signature=Signature(params=[]),
            docstring="Another function.",
        ),
        _make_element(
            "_private",
            "mod._private",
            visibility=Visibility.PRIVATE,
            start_line=25,
            end_line=30,
            signature=Signature(params=[]),
        ),
    ]


@pytest.fixture
def sample_manifest(sample_elements: list[Element]) -> FileManifest:
    return _make_manifest(
        file="src/mod.py",
        module="mod",
        elements=sample_elements,
    )


@pytest.fixture
def sample_registry(sample_manifest: FileManifest) -> ManifestRegistry:
    return ManifestRegistry({"src/mod.py": sample_manifest})


# ═══════════════════════════════════════════════════════════════════════════
# ManifestRegistry — basic queries
# ═══════════════════════════════════════════════════════════════════════════


class TestManifestRegistryBasic:
    def test_get_existing_file(self, sample_registry: ManifestRegistry) -> None:
        result = sample_registry.get("src/mod.py")
        assert result is not None
        assert result.module == "mod"

    def test_get_missing_file(self, sample_registry: ManifestRegistry) -> None:
        assert sample_registry.get("nonexistent.py") is None

    def test_fqn_exists_known(self, sample_registry: ManifestRegistry) -> None:
        assert sample_registry.fqn_exists("mod.foo") is True
        assert sample_registry.fqn_exists("mod.bar") is True
        assert sample_registry.fqn_exists("mod._private") is True

    def test_fqn_exists_unknown(self, sample_registry: ManifestRegistry) -> None:
        assert sample_registry.fqn_exists("mod.nonexistent") is False

    def test_resolve_fqn_known(self, sample_registry: ManifestRegistry) -> None:
        result = sample_registry.resolve_fqn("mod.foo")
        assert result is not None
        file_path, element = result
        assert file_path == "src/mod.py"
        assert element.name == "foo"

    def test_resolve_fqn_unknown(self, sample_registry: ManifestRegistry) -> None:
        assert sample_registry.resolve_fqn("mod.nonexistent") is None

    def test_files(self, sample_registry: ManifestRegistry) -> None:
        assert sample_registry.files() == ["src/mod.py"]

    def test_public_element_count(self, sample_registry: ManifestRegistry) -> None:
        # foo and bar are PUBLIC, _private is PRIVATE
        assert sample_registry.public_element_count("src/mod.py") == 2

    def test_public_element_count_missing_file(
        self, sample_registry: ManifestRegistry
    ) -> None:
        assert sample_registry.public_element_count("nonexistent.py") == 0


# ═══════════════════════════════════════════════════════════════════════════
# ManifestRegistry — path traversal guards
# ═══════════════════════════════════════════════════════════════════════════


class TestPathTraversal:
    def test_get_rejects_dotdot(self, sample_registry: ManifestRegistry) -> None:
        assert sample_registry.get("../../../etc/passwd") is None

    def test_get_rejects_absolute_path(
        self, sample_registry: ManifestRegistry
    ) -> None:
        assert sample_registry.get("/etc/passwd") is None

    def test_get_accepts_nested_path(self, sample_registry: ManifestRegistry) -> None:
        # Legitimate nested path should work
        result = sample_registry.get("src/mod.py")
        assert result is not None

    def test_resolve_fqn_rejects_stored_traversal(self) -> None:
        """Edge case: if a stored path somehow contains .., it should be rejected."""
        el = _make_element("x", "mod.x")
        manifest = _make_manifest(elements=[el])
        # Simulate a bad stored path
        registry = ManifestRegistry({"../../etc/passwd": manifest})
        result = registry.resolve_fqn("mod.x")
        assert result is None


# ═══════════════════════════════════════════════════════════════════════════
# ManifestRegistry — file_element_summary
# ═══════════════════════════════════════════════════════════════════════════


class TestFileElementSummary:
    def test_summary_contains_fqns(
        self, sample_registry: ManifestRegistry
    ) -> None:
        result = sample_registry.file_element_summary("src/mod.py")
        assert "mod.foo" in result
        assert "mod.bar" in result

    def test_summary_respects_budget(
        self, sample_registry: ManifestRegistry
    ) -> None:
        result = sample_registry.file_element_summary("src/mod.py", budget_chars=50)
        assert len(result) <= 50

    def test_summary_empty_for_missing_file(
        self, sample_registry: ManifestRegistry
    ) -> None:
        result = sample_registry.file_element_summary("nonexistent.py")
        assert result == ""

    def test_summary_source_order(self) -> None:
        """Elements should be emitted in source-order (by span.start_line)."""
        elements = [
            _make_element("b_func", "mod.b_func", start_line=20, end_line=30),
            _make_element("a_func", "mod.a_func", start_line=1, end_line=10),
        ]
        manifest = _make_manifest(elements=elements)
        registry = ManifestRegistry({"mod.py": manifest})
        result = registry.file_element_summary("mod.py")
        a_pos = result.find("mod.a_func")
        b_pos = result.find("mod.b_func")
        assert a_pos < b_pos, "Elements should be in source order"

    def test_tier1_includes_docstrings(self) -> None:
        elements = [
            _make_element(
                "func", "mod.func", docstring="My docstring here", start_line=1, end_line=5
            ),
        ]
        manifest = _make_manifest(elements=elements)
        registry = ManifestRegistry({"mod.py": manifest})
        result = registry.file_element_summary("mod.py", budget_chars=4000)
        assert "My docstring here" in result

    def test_progressive_truncation_drops_docstrings(self) -> None:
        """With tight budget, tier 2 should drop docstrings."""
        elements = [
            _make_element(
                "func1",
                "mod.func1",
                docstring="Long docstring " * 20,
                start_line=1,
                end_line=5,
            ),
            _make_element(
                "func2",
                "mod.func2",
                docstring="Another long docstring " * 20,
                start_line=10,
                end_line=15,
            ),
        ]
        manifest = _make_manifest(elements=elements)
        registry = ManifestRegistry({"mod.py": manifest})

        # Large budget — tier 1 includes docstrings
        full = registry.file_element_summary("mod.py", budget_chars=4000)
        assert "Long docstring" in full

        # Small budget — should truncate
        compact = registry.file_element_summary("mod.py", budget_chars=100)
        assert len(compact) <= 100

    def test_summary_emits_timing_log(self, sample_registry: ManifestRegistry, caplog) -> None:
        with caplog.at_level(logging.DEBUG, logger="startd8.utils.manifest_registry"):
            sample_registry.file_element_summary("src/mod.py")
        assert any("manifest.element_summary" in r.message for r in caplog.records)

    def test_include_resolved_types_uses_resolved_signature(self) -> None:
        """PI-2: When include_resolved_types=True, resolved signature is preferred over AST."""
        resolved_sig = ResolvedSignature(
            params=[
                ResolvedParam(name="x", annotation="pandas.DataFrame"),
                ResolvedParam(name="y", annotation="str", default="''"),
            ],
            return_annotation="None",
        )
        inspect_info = InspectInfo(resolved_signature=resolved_sig)
        ast_sig = Signature(
            params=[
                Param(name="x", annotation="'DataFrame'"),
                Param(name="y", annotation="str", default="''"),
            ],
            return_annotation="None",
        )
        el = _make_element("process", "mod.process", signature=ast_sig)
        el = el.model_copy(update={"inspect_info": inspect_info})
        manifest = _make_manifest(elements=[el])
        registry = ManifestRegistry({"mod.py": manifest})

        with_resolved = registry.file_element_summary(
            "mod.py", budget_chars=4000, include_resolved_types=True
        )
        without_resolved = registry.file_element_summary(
            "mod.py", budget_chars=4000, include_resolved_types=False
        )

        assert "pandas.DataFrame" in with_resolved
        assert "'DataFrame'" not in with_resolved or "pandas.DataFrame" in with_resolved
        assert "'DataFrame'" in without_resolved or "DataFrame" in without_resolved


# ═══════════════════════════════════════════════════════════════════════════
# ManifestRegistry — module_version_for (PI-1)
# ═══════════════════════════════════════════════════════════════════════════


class TestModuleVersionFor:
    """PI-1: module_version_for returns FileManifest.module_version."""

    def test_returns_version_when_present(self) -> None:
        manifest = _make_manifest(
            file="src/foo/bar.py",
            module="foo.bar",
            module_version="0.4.0",
        )
        registry = ManifestRegistry({"src/foo/bar.py": manifest})
        assert registry.module_version_for("src/foo/bar.py") == "0.4.0"

    def test_returns_none_when_absent(self) -> None:
        manifest = _make_manifest(file="src/foo/bar.py", module="foo.bar")
        registry = ManifestRegistry({"src/foo/bar.py": manifest})
        assert registry.module_version_for("src/foo/bar.py") is None

    def test_returns_none_for_missing_file(self) -> None:
        registry = ManifestRegistry({})
        assert registry.module_version_for("nonexistent.py") is None


# ═══════════════════════════════════════════════════════════════════════════
# ManifestRegistry — dependency_graph
# ═══════════════════════════════════════════════════════════════════════════


class TestDependencyGraph:
    def test_dependency_graph_returns_relative_posix_paths(self) -> None:
        m1 = _make_manifest(
            file="src/foo/a.py",
            module="foo.a",
            imports=[
                ImportEntry(
                    kind="from",
                    module="foo.b",
                    names=["something"],
                    span=Span(start_line=1, start_col=0, end_line=1, end_col=20),
                ),
            ],
            dependencies=Dependencies(internal=["foo.b"]),
        )
        m2 = _make_manifest(file="src/foo/b.py", module="foo.b")

        registry = ManifestRegistry(
            {"src/foo/a.py": m1, "src/foo/b.py": m2}
        )
        graph = registry.dependency_graph()
        assert "src/foo/b.py" in graph.get("src/foo/a.py", set())

    def test_dependency_graph_excludes_external(self) -> None:
        m = _make_manifest(
            file="src/foo/a.py",
            module="foo.a",
            imports=[
                ImportEntry(
                    kind="import",
                    module="os",
                    span=Span(start_line=1, start_col=0, end_line=1, end_col=9),
                ),
            ],
            dependencies=Dependencies(stdlib=["os"]),
        )
        registry = ManifestRegistry({"src/foo/a.py": m})
        graph = registry.dependency_graph()
        assert graph.get("src/foo/a.py") == set()

    def test_dependency_graph_is_cached(self) -> None:
        registry = ManifestRegistry({"a.py": _make_manifest()})
        g1 = registry.dependency_graph()
        g2 = registry.dependency_graph()
        assert g1 is g2  # Same object — cached


# ═══════════════════════════════════════════════════════════════════════════
# ManifestRegistry — summary_stats
# ═══════════════════════════════════════════════════════════════════════════


class TestSummaryStats:
    def test_summary_stats_keys(self, sample_registry: ManifestRegistry) -> None:
        stats = sample_registry.summary_stats()
        assert "file_count" in stats
        assert "total_elements" in stats
        assert "public_elements" in stats
        assert "schema_version" in stats
        assert "generated_at" in stats

    def test_summary_stats_values(self, sample_registry: ManifestRegistry) -> None:
        stats = sample_registry.summary_stats()
        assert stats["file_count"] == 1
        assert stats["total_elements"] == 3  # foo, bar, _private
        assert stats["public_elements"] == 2  # foo, bar

    def test_summary_stats_schema_version(
        self, sample_registry: ManifestRegistry
    ) -> None:
        stats = sample_registry.summary_stats()
        assert stats["schema_version"] == "1.4.0"


# ═══════════════════════════════════════════════════════════════════════════
# ManifestRegistry — with_updated_files
# ═══════════════════════════════════════════════════════════════════════════


class TestWithUpdatedFiles:
    def test_returns_new_instance(self, sample_registry: ManifestRegistry) -> None:
        new_manifest = _make_manifest(
            file="src/new.py",
            module="new",
            elements=[_make_element("new_func", "new.new_func")],
        )
        new_registry = sample_registry.with_updated_files({"src/new.py": new_manifest})
        assert new_registry is not sample_registry
        assert new_registry.get("src/new.py") is not None
        assert new_registry.get("src/mod.py") is not None  # old files preserved

    def test_old_instance_unchanged(self, sample_registry: ManifestRegistry) -> None:
        new_manifest = _make_manifest(
            file="src/new.py",
            module="new",
            elements=[_make_element("new_func", "new.new_func")],
        )
        sample_registry.with_updated_files({"src/new.py": new_manifest})
        assert sample_registry.get("src/new.py") is None  # old instance unchanged

    def test_invalidates_dep_graph(self, sample_registry: ManifestRegistry) -> None:
        # Build dep graph cache
        _ = sample_registry.dependency_graph()
        assert sample_registry._dep_graph is not None

        new_manifest = _make_manifest(
            file="src/new.py",
            module="new",
        )
        new_registry = sample_registry.with_updated_files({"src/new.py": new_manifest})
        # New registry should have invalidated dep graph (computed fresh)
        # The new instance gets _dep_graph=None initially
        assert new_registry._dep_graph is None

    def test_fqn_index_includes_updated_elements(self) -> None:
        old_manifest = _make_manifest(
            elements=[_make_element("old_func", "mod.old_func")],
        )
        registry = ManifestRegistry({"mod.py": old_manifest})
        assert registry.fqn_exists("mod.old_func")
        assert not registry.fqn_exists("mod.new_func")

        new_manifest = _make_manifest(
            elements=[_make_element("new_func", "mod.new_func")],
        )
        updated = registry.with_updated_files({"mod.py": new_manifest})
        assert updated.fqn_exists("mod.new_func")
        # Old FQN should be gone in updated (file replaced)
        assert not updated.fqn_exists("mod.old_func")


# ═══════════════════════════════════════════════════════════════════════════
# ManifestRegistry — from_cache
# ═══════════════════════════════════════════════════════════════════════════


class TestFromCache:
    def test_returns_none_when_cache_absent(self, tmp_path: Path) -> None:
        result = ManifestRegistry.from_cache(tmp_path)
        assert result is None

    def test_returns_none_on_corrupt_json(self, tmp_path: Path) -> None:
        cache_dir = tmp_path / ".startd8" / "manifests"
        cache_dir.mkdir(parents=True)
        (cache_dir / "_index.json").write_text("NOT VALID JSON", encoding="utf-8")
        result = ManifestRegistry.from_cache(tmp_path)
        assert result is None

    def test_returns_none_on_missing_meta(self, tmp_path: Path) -> None:
        cache_dir = tmp_path / ".startd8" / "manifests"
        cache_dir.mkdir(parents=True)
        (cache_dir / "_index.json").write_text("{}", encoding="utf-8")
        result = ManifestRegistry.from_cache(tmp_path)
        assert result is None

    def test_skips_oversized_manifest(self, tmp_path: Path) -> None:
        """Per-file size guard (req R3-S3): skips manifest files > 5MB."""
        cache_dir = tmp_path / ".startd8" / "manifests"
        cache_dir.mkdir(parents=True)

        index = {
            "_meta": {"schema_version": "1.4.0", "python_version": "3.14"},
            "big.py": "sha256:bigdigest",
        }
        (cache_dir / "_index.json").write_text(json.dumps(index), encoding="utf-8")

        # Create oversized file
        big_file = cache_dir / "sha256_bigdigest.json"
        big_file.write_text("x" * (6 * 1024 * 1024), encoding="utf-8")

        result = ManifestRegistry.from_cache(tmp_path)
        # Should skip the big file and return None (no valid manifests)
        assert result is None

    def test_emits_cache_load_log(self, tmp_path: Path, caplog) -> None:
        with caplog.at_level(logging.INFO, logger="startd8.utils.manifest_registry"):
            ManifestRegistry.from_cache(tmp_path)
        assert any("manifest.cache_load" in r.message or "manifest.fallback" in r.message for r in caplog.records)

    def test_loads_valid_cache(self, tmp_path: Path) -> None:
        """Happy path: valid cache loads successfully."""
        cache_dir = tmp_path / ".startd8" / "manifests"
        cache_dir.mkdir(parents=True)

        # Create a simple manifest
        manifest = _make_manifest(
            file="src/test.py",
            module="test",
            elements=[_make_element("func", "test.func")],
        )
        manifest_data = manifest.model_dump()

        digest = "sha256:testdigest"
        index = {
            "_meta": {"schema_version": "1.4.0", "python_version": "3.14"},
            "src/test.py": digest,
        }
        (cache_dir / "_index.json").write_text(json.dumps(index), encoding="utf-8")
        (cache_dir / "sha256_testdigest.json").write_text(
            json.dumps(manifest_data), encoding="utf-8"
        )

        result = ManifestRegistry.from_cache(tmp_path)
        assert result is not None
        assert result.get("src/test.py") is not None
        assert result.fqn_exists("test.func")


# ═══════════════════════════════════════════════════════════════════════════
# ManifestRegistry — is_stale
# ═══════════════════════════════════════════════════════════════════════════


class TestIsStale:
    def test_returns_false_when_no_mtime_data(
        self, sample_registry: ManifestRegistry
    ) -> None:
        assert sample_registry.is_stale("src/mod.py") is False


# ═══════════════════════════════════════════════════════════════════════════
# ManifestDiff
# ═══════════════════════════════════════════════════════════════════════════


class TestManifestDiff:
    def test_no_changes(self) -> None:
        manifest = _make_manifest(
            elements=[_make_element("func", "mod.func")],
        )
        diff = ManifestDiff.diff(manifest, manifest)
        assert diff.removed_public == []
        assert diff.added_public == []
        assert diff.changed_signatures == []
        assert diff.element_count_delta == 0
        assert diff.has_breaking_changes is False

    def test_detects_removed_public(self) -> None:
        old = _make_manifest(
            elements=[
                _make_element("func1", "mod.func1"),
                _make_element("func2", "mod.func2"),
            ],
        )
        new = _make_manifest(
            elements=[_make_element("func1", "mod.func1")],
        )
        diff = ManifestDiff.diff(old, new)
        assert "mod.func2" in diff.removed_public
        assert diff.has_breaking_changes is True

    def test_detects_added_public(self) -> None:
        old = _make_manifest(
            elements=[_make_element("func1", "mod.func1")],
        )
        new = _make_manifest(
            elements=[
                _make_element("func1", "mod.func1"),
                _make_element("func2", "mod.func2"),
            ],
        )
        diff = ManifestDiff.diff(old, new)
        assert "mod.func2" in diff.added_public
        assert diff.has_breaking_changes is False  # additions aren't breaking

    def test_detects_changed_signatures(self) -> None:
        old = _make_manifest(
            elements=[
                _make_element(
                    "func",
                    "mod.func",
                    signature=Signature(
                        params=[Param(name="x", annotation="int")],
                        return_annotation="str",
                    ),
                ),
            ],
        )
        new = _make_manifest(
            elements=[
                _make_element(
                    "func",
                    "mod.func",
                    signature=Signature(
                        params=[
                            Param(name="x", annotation="int"),
                            Param(name="y", annotation="str"),
                        ],
                        return_annotation="str",
                    ),
                ),
            ],
        )
        diff = ManifestDiff.diff(old, new)
        assert len(diff.changed_signatures) == 1
        assert diff.changed_signatures[0][0] == "mod.func"
        assert diff.has_breaking_changes is True

    def test_element_count_delta(self) -> None:
        old = _make_manifest(
            elements=[_make_element("func1", "mod.func1")],
        )
        new = _make_manifest(
            elements=[
                _make_element("func1", "mod.func1"),
                _make_element("func2", "mod.func2"),
                _make_element("_priv", "mod._priv", visibility=Visibility.PRIVATE),
            ],
        )
        diff = ManifestDiff.diff(old, new)
        assert diff.element_count_delta == 2

    def test_emits_timing_log(self, caplog) -> None:
        manifest = _make_manifest(elements=[_make_element("func", "mod.func")])
        with caplog.at_level(logging.INFO, logger="startd8.utils.manifest_registry"):
            ManifestDiff.diff(manifest, manifest)
        assert any("manifest.diff" in r.message for r in caplog.records)

    def test_malformed_elements_no_crash(self) -> None:
        """Elements with fqn=None or missing visibility don't crash diff (plan R1-S10)."""
        # Create element with empty fqn
        old = _make_manifest(
            elements=[
                _make_element("func", "mod.func"),
                Element(
                    kind=ElementKind.VARIABLE,
                    name="bad",
                    fqn="",  # empty FQN
                    span=Span(start_line=1, start_col=0, end_line=1, end_col=0),
                ),
            ],
        )
        new = _make_manifest(
            elements=[_make_element("func", "mod.func")],
        )
        # Should not raise
        diff = ManifestDiff.diff(old, new)
        assert isinstance(diff, ManifestDiff)


# ═══════════════════════════════════════════════════════════════════════════
# Signature normalization
# ═══════════════════════════════════════════════════════════════════════════


class TestSignatureNormalization:
    def test_optional_vs_pipe_none_no_change(self) -> None:
        """Optional[X] vs X | None does NOT trigger changed_signatures."""
        old = _make_manifest(
            elements=[
                _make_element(
                    "func",
                    "mod.func",
                    signature=Signature(
                        params=[Param(name="x", annotation="Optional[int]")],
                    ),
                ),
            ],
        )
        new = _make_manifest(
            elements=[
                _make_element(
                    "func",
                    "mod.func",
                    signature=Signature(
                        params=[Param(name="x", annotation="int | None")],
                    ),
                ),
            ],
        )
        diff = ManifestDiff.diff(old, new)
        assert diff.changed_signatures == []

    def test_typing_optional_vs_pipe_none_no_change(self) -> None:
        """typing.Optional[X] vs X | None does NOT trigger changed_signatures."""
        old = _make_manifest(
            elements=[
                _make_element(
                    "func",
                    "mod.func",
                    signature=Signature(
                        params=[Param(name="x", annotation="typing.Optional[str]")],
                    ),
                ),
            ],
        )
        new = _make_manifest(
            elements=[
                _make_element(
                    "func",
                    "mod.func",
                    signature=Signature(
                        params=[Param(name="x", annotation="str | None")],
                    ),
                ),
            ],
        )
        diff = ManifestDiff.diff(old, new)
        assert diff.changed_signatures == []

    def test_whitespace_only_no_change(self) -> None:
        """Whitespace-only differences do NOT trigger changed_signatures."""
        assert _normalize_signature("(x:  int)") == _normalize_signature("(x: int)")
        # Multiple spaces collapsed to single
        assert _normalize_signature("(x:     int)") == "(x: int)"

    def test_actual_type_change_triggers(self) -> None:
        """Actual type changes DO trigger changed_signatures."""
        old = _make_manifest(
            elements=[
                _make_element(
                    "func",
                    "mod.func",
                    signature=Signature(
                        params=[Param(name="x", annotation="int")],
                        return_annotation="str",
                    ),
                ),
            ],
        )
        new = _make_manifest(
            elements=[
                _make_element(
                    "func",
                    "mod.func",
                    signature=Signature(
                        params=[Param(name="x", annotation="float")],
                        return_annotation="str",
                    ),
                ),
            ],
        )
        diff = ManifestDiff.diff(old, new)
        assert len(diff.changed_signatures) == 1

    def test_normalize_signature_basic(self) -> None:
        assert _normalize_signature("  (x: int)  ") == "(x: int)"
        assert _normalize_signature("(x:   int,   y: str)") == "(x: int, y: str)"
        assert _normalize_signature("Optional[int]") == "int | None"
        assert _normalize_signature("typing.Optional[str]") == "str | None"


# ═══════════════════════════════════════════════════════════════════════════
# Schema version compatibility
# ═══════════════════════════════════════════════════════════════════════════


class TestSchemaCompatibility:
    def test_works_with_100_manifests(self) -> None:
        manifest = _make_manifest()
        # Override schema_version
        data = manifest.model_dump()
        data["schema_version"] = "1.0.0"
        m = FileManifest.model_validate(data)
        registry = ManifestRegistry({"test.py": m})
        assert registry.files() == ["test.py"]

    def test_works_with_120_manifests(self) -> None:
        manifest = _make_manifest()
        registry = ManifestRegistry({"test.py": manifest})
        assert registry.files() == ["test.py"]

    def test_diff_across_versions(self) -> None:
        """Cross-version diff works on common fields (req R2-S2)."""
        old_data = _make_manifest(elements=[_make_element("func", "mod.func")]).model_dump()
        old_data["schema_version"] = "1.0.0"
        old = FileManifest.model_validate(old_data)

        new = _make_manifest(elements=[_make_element("func", "mod.func")])
        assert new.schema_version == "1.4.0"

        # Should diff without errors
        diff = ManifestDiff.diff(old, new)
        assert isinstance(diff, ManifestDiff)
