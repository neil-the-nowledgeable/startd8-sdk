"""
Unit tests for DeterministicFileAssembler.

Covers: import rendering, class rendering, function rendering, constant
rendering, full-file render_specs, safety/validation, materialize, golden
fixtures, and error attribution.
"""

from __future__ import annotations

import ast
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

from startd8.contractors.context_schema import FileStubResult, ScaffoldPhaseOutput
from startd8.forward_manifest import (
    ForwardDependencies,
    ForwardElementSpec,
    ForwardFileSpec,
    ForwardImportSpec,
    ForwardManifest,
)
from startd8.utils.code_manifest import (
    ElementKind,
    Param,
    ParamKind,
    Signature,
    Visibility,
)
from startd8.utils.file_assembler import (
    SKELETON_SENTINEL,
    DeterministicFileAssembler,
    RenderResult,
    StubManifestEntry,
)

GOLDEN_DIR = Path(__file__).parent / "golden_stubs"


# ── Helpers ───────────────────────────────────────────────────────────────


def _make_func(
    name: str = "foo",
    params: Optional[list[Param]] = None,
    return_annotation: Optional[str] = None,
    visibility: Visibility = Visibility.PUBLIC,
    decorators: Optional[list[str]] = None,
    docstring: Optional[str] = None,
    parent_class: Optional[str] = None,
    kind: Optional[ElementKind] = None,
) -> ForwardElementSpec:
    """Helper to create a ForwardElementSpec for a function/method."""
    if kind is None:
        kind = ElementKind.METHOD if parent_class else ElementKind.FUNCTION
    return ForwardElementSpec(
        kind=kind,
        name=name,
        signature=Signature(
            params=params or [],
            return_annotation=return_annotation,
        ),
        visibility=visibility,
        decorators=decorators or [],
        docstring_hint=docstring,
        parent_class=parent_class,
    )


def _make_class(
    name: str = "MyClass",
    bases: Optional[list[str]] = None,
    decorators: Optional[list[str]] = None,
    docstring: Optional[str] = None,
) -> ForwardElementSpec:
    return ForwardElementSpec(
        kind=ElementKind.CLASS,
        name=name,
        bases=bases or [],
        decorators=decorators or [],
        docstring_hint=docstring,
    )


def _make_const(
    name: str = "MAX_VALUE",
    annotation: Optional[str] = None,
    visibility: Visibility = Visibility.PUBLIC,
) -> ForwardElementSpec:
    sig = Signature(params=[], return_annotation=annotation) if annotation else None
    return ForwardElementSpec(
        kind=ElementKind.CONSTANT,
        name=name,
        signature=sig,
        visibility=visibility,
    )


def _make_manifest(
    file_path: str = "src/mod.py",
    elements: Optional[list[ForwardElementSpec]] = None,
    imports: Optional[list[ForwardImportSpec]] = None,
    dependencies: Optional[ForwardDependencies] = None,
) -> ForwardManifest:
    return ForwardManifest(
        file_specs={
            file_path: ForwardFileSpec(
                file=file_path,
                elements=elements or [],
                imports=imports or [],
                dependencies=dependencies,
            )
        }
    )


def _render_one(
    elements: Optional[list[ForwardElementSpec]] = None,
    imports: Optional[list[ForwardImportSpec]] = None,
    dependencies: Optional[ForwardDependencies] = None,
    module_inventory: Optional[list[str]] = None,
) -> str:
    """Render a single file and return the source text."""
    manifest = _make_manifest(
        elements=elements, imports=imports, dependencies=dependencies,
    )
    assembler = DeterministicFileAssembler(module_inventory=module_inventory)
    result = assembler.render_specs(manifest)
    assert len(result.specs) == 1, f"Expected 1 file, got {len(result.specs)}"
    return list(result.specs.values())[0]


# ═══════════════════════════════════════════════════════════════════════════
# Import rendering
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
class TestImportRendering:
    """6-tier import precedence, from/import, aliases, __future__ first."""

    def test_future_always_present(self):
        src = _render_one(elements=[_make_func()])
        assert "from __future__ import annotations" in src

    def test_future_not_duplicated(self):
        """__future__ in manifest imports should not duplicate."""
        src = _render_one(
            elements=[_make_func()],
            imports=[ForwardImportSpec(kind="from", module="__future__", names=["annotations"])],
        )
        count = src.count("from __future__ import annotations")
        assert count == 1

    def test_stdlib_before_external(self):
        src = _render_one(
            elements=[_make_func()],
            imports=[
                ForwardImportSpec(kind="import", module="requests"),
                ForwardImportSpec(kind="import", module="os"),
            ],
        )
        os_idx = src.index("import os")
        req_idx = src.index("import requests")
        assert os_idx < req_idx

    def test_from_import_rendering(self):
        src = _render_one(
            elements=[_make_func()],
            imports=[ForwardImportSpec(kind="from", module="typing", names=["Optional", "List"])],
        )
        assert "from typing import Optional, List" in src

    def test_import_with_alias(self):
        src = _render_one(
            elements=[_make_func()],
            imports=[ForwardImportSpec(kind="import", module="numpy", alias="np")],
        )
        assert "import numpy as np" in src

    def test_explicit_stdlib_from_deps(self):
        """ForwardDependencies.stdlib takes precedence over _STDLIB_MODULES."""
        src = _render_one(
            elements=[_make_func()],
            imports=[
                ForwardImportSpec(kind="import", module="mylib"),
                ForwardImportSpec(kind="import", module="os"),
            ],
            dependencies=ForwardDependencies(stdlib=["os"], external=["mylib"]),
        )
        os_idx = src.index("import os")
        mylib_idx = src.index("import mylib")
        assert os_idx < mylib_idx

    def test_local_inventory_classification(self):
        """Module inventory puts imports in the local section (after external)."""
        src = _render_one(
            elements=[_make_func()],
            imports=[
                ForwardImportSpec(kind="import", module="mypkg"),
                ForwardImportSpec(kind="import", module="requests"),
            ],
            module_inventory=["mypkg"],
        )
        req_idx = src.index("import requests")
        mypkg_idx = src.index("import mypkg")
        assert req_idx < mypkg_idx


# ═══════════════════════════════════════════════════════════════════════════
# Class rendering
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
class TestClassRendering:

    def test_class_with_bases(self):
        src = _render_one(elements=[_make_class("Foo", bases=["Bar", "Baz"])])
        assert "class Foo(Bar, Baz):" in src

    def test_class_with_decorators(self):
        src = _render_one(elements=[_make_class("Foo", decorators=["dataclass"])])
        assert "@dataclass" in src
        assert "class Foo:" in src

    def test_class_with_methods(self):
        src = _render_one(elements=[
            _make_class("Engine"),
            _make_func("run", parent_class="Engine", params=[Param(name="self")]),
        ])
        assert "class Engine:" in src
        assert "    def run(self):" in src

    def test_empty_class_has_pass(self):
        src = _render_one(elements=[_make_class("Empty")])
        assert "class Empty:" in src
        assert "    pass" in src

    def test_class_docstring(self):
        src = _render_one(elements=[_make_class("Doc", docstring="A documented class.")])
        assert '    """' in src
        assert "    A documented class." in src

    def test_all_excludes_methods(self):
        src = _render_one(elements=[
            _make_class("Service"),
            _make_func("handle", parent_class="Service", params=[Param(name="self")]),
        ])
        assert '"Service"' in src
        assert '"handle"' not in src.split("__all__")[1]

    def test_init_hoisted_first(self):
        """__init__ should come before other methods regardless of manifest order."""
        src = _render_one(elements=[
            _make_class("Widget"),
            _make_func("render", parent_class="Widget", params=[Param(name="self")]),
            _make_func("__init__", parent_class="Widget", params=[Param(name="self")]),
        ])
        init_idx = src.index("def __init__")
        render_idx = src.index("def render")
        assert init_idx < render_idx

    def test_method_ordering_preserves_manifest_order(self):
        """Non-__init__ methods should preserve manifest order."""
        src = _render_one(elements=[
            _make_class("Svc"),
            _make_func("beta", parent_class="Svc", params=[Param(name="self")]),
            _make_func("alpha", parent_class="Svc", params=[Param(name="self")]),
        ])
        beta_idx = src.index("def beta")
        alpha_idx = src.index("def alpha")
        assert beta_idx < alpha_idx

    def test_one_blank_line_between_methods(self):
        """PEP 8: 1 blank line between methods in a class."""
        src = _render_one(elements=[
            _make_class("Svc"),
            _make_func("a", parent_class="Svc", params=[Param(name="self")]),
            _make_func("b", parent_class="Svc", params=[Param(name="self")]),
        ])
        # Find the end of method 'a' and start of method 'b'
        lines = src.split("\n")
        a_end = None
        b_start = None
        for i, line in enumerate(lines):
            if "raise NotImplementedError" in line and a_end is None:
                a_end = i
            if "def b(self):" in line:
                b_start = i
        assert a_end is not None and b_start is not None
        # Exactly 1 blank line between
        assert b_start - a_end == 2


# ═══════════════════════════════════════════════════════════════════════════
# Function rendering
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
class TestFunctionRendering:

    def test_sync_function(self):
        src = _render_one(elements=[_make_func("calculate")])
        assert "def calculate():" in src
        assert "raise NotImplementedError" in src

    def test_async_function(self):
        src = _render_one(elements=[
            ForwardElementSpec(
                kind=ElementKind.ASYNC_FUNCTION,
                name="fetch",
                signature=Signature(params=[], return_annotation="dict"),
            ),
        ])
        assert "async def fetch() -> dict:" in src

    def test_all_param_kinds(self):
        """Test positional-only, regular, *args, keyword-only, **kwargs."""
        src = _render_one(elements=[
            _make_func("complex_fn", params=[
                Param(name="pos_only", kind=ParamKind.POSITIONAL_ONLY),
                Param(name="regular", annotation="str"),
                Param(name="args", kind=ParamKind.VAR_POSITIONAL),
                Param(name="kw_only", kind=ParamKind.KEYWORD_ONLY, annotation="int", default="0"),
                Param(name="kwargs", kind=ParamKind.VAR_KEYWORD),
            ]),
        ])
        assert "def complex_fn(pos_only, /, regular: str, *args, kw_only: int = 0, **kwargs):" in src

    def test_return_annotation(self):
        src = _render_one(elements=[
            _make_func("get_value", return_annotation="Optional[str]"),
        ])
        assert "-> Optional[str]:" in src

    def test_default_values(self):
        src = _render_one(elements=[
            _make_func("init", params=[
                Param(name="x", annotation="int", default="42"),
                Param(name="name", annotation="str", default="'default'"),
            ]),
        ])
        assert "x: int = 42" in src
        assert "name: str = 'default'" in src

    def test_decorators(self):
        src = _render_one(elements=[
            _make_func("cached", decorators=["lru_cache(maxsize=128)"]),
        ])
        assert "@lru_cache(maxsize=128)" in src

    def test_docstring(self):
        src = _render_one(elements=[
            _make_func("documented", docstring="Compute the value."),
        ])
        assert '    """' in src
        assert "    Compute the value." in src

    def test_keyword_only_without_varargs(self):
        """Keyword-only params without *args should emit bare *."""
        src = _render_one(elements=[
            _make_func("kw_func", params=[
                Param(name="a"),
                Param(name="b", kind=ParamKind.KEYWORD_ONLY),
            ]),
        ])
        assert "def kw_func(a, *, b):" in src


# ═══════════════════════════════════════════════════════════════════════════
# Constant rendering
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
class TestConstantRendering:

    def test_typed_constant(self):
        src = _render_one(elements=[_make_const("MAX_SIZE", annotation="int")])
        assert "MAX_SIZE: int = ..." in src

    def test_untyped_constant(self):
        src = _render_one(elements=[_make_const("VERSION")])
        assert "VERSION = ..." in src

    def test_private_constant_excluded_from_all(self):
        src = _render_one(elements=[
            _make_const("_INTERNAL", visibility=Visibility.PRIVATE),
            _make_func("public_fn"),
        ])
        assert '"_INTERNAL"' not in src.split("__all__")[1]

    def test_public_constant_in_all(self):
        src = _render_one(elements=[_make_const("API_VERSION", annotation="str")])
        assert '"API_VERSION"' in src


# ═══════════════════════════════════════════════════════════════════════════
# Full file: render_specs
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
class TestRenderSpecs:

    def test_ast_parse_roundtrip(self):
        """Every rendered file must pass ast.parse."""
        manifest = _make_manifest(elements=[
            _make_class("Processor", bases=["Base"]),
            _make_func("run", parent_class="Processor",
                        params=[Param(name="self"), Param(name="data", annotation="str")],
                        return_annotation="bool"),
            _make_func("standalone", return_annotation="int"),
        ])
        assembler = DeterministicFileAssembler()
        result = assembler.render_specs(manifest)
        assert len(result.failures) == 0
        for src in result.specs.values():
            ast.parse(src)  # Should not raise

    def test_multi_class_file(self):
        manifest = _make_manifest(elements=[
            _make_class("Alpha"),
            _make_class("Beta", bases=["Alpha"]),
            _make_func("helper"),
        ])
        assembler = DeterministicFileAssembler()
        result = assembler.render_specs(manifest)
        src = list(result.specs.values())[0]
        assert "class Alpha:" in src
        assert "class Beta(Alpha):" in src
        assert "def helper():" in src

    def test_deterministic_ordering(self):
        """Classes come before functions; sorted by name within each group."""
        manifest = _make_manifest(elements=[
            _make_func("zfunc"),
            _make_class("AClass"),
            _make_func("afunc"),
        ])
        assembler = DeterministicFileAssembler()
        result = assembler.render_specs(manifest)
        src = list(result.specs.values())[0]
        cls_idx = src.index("class AClass:")
        afunc_idx = src.index("def afunc():")
        zfunc_idx = src.index("def zfunc():")
        assert cls_idx < afunc_idx < zfunc_idx

    def test_duplicate_public_symbol_error(self):
        """Duplicate public top-level symbols should raise ValueError."""
        manifest = _make_manifest(elements=[
            _make_func("compute"),
            _make_func("compute"),  # duplicate
        ])
        assembler = DeterministicFileAssembler()
        result = assembler.render_specs(manifest)
        assert len(result.failures) == 1
        assert result.failures[0].status == "syntax_error"
        assert "Duplicate public" in (result.failures[0].error or "")

    def test_duplicate_private_warning_keeps_first(self, caplog):
        """Duplicate private symbols should warn but not fail."""
        manifest = _make_manifest(elements=[
            ForwardElementSpec(
                kind=ElementKind.CONSTANT,
                name="_cache",
                visibility=Visibility.PRIVATE,
            ),
            ForwardElementSpec(
                kind=ElementKind.CONSTANT,
                name="_cache",
                visibility=Visibility.PRIVATE,
            ),
            _make_func("public_fn"),
        ])
        assembler = DeterministicFileAssembler()
        result = assembler.render_specs(manifest)
        # Should succeed (not fail) but with a warning
        assert len(result.specs) == 1

    def test_skeleton_sentinel_present(self):
        src = _render_one(elements=[_make_func()])
        assert src.startswith(SKELETON_SENTINEL)

    def test_pep8_two_blank_lines_between_defs(self):
        src = _render_one(elements=[
            _make_func("alpha"),
            _make_func("beta"),
        ])
        lines = src.split("\n")
        # Find alpha's end and beta's start
        alpha_end = None
        beta_start = None
        for i, line in enumerate(lines):
            if "def alpha():" in line:
                # Find end of alpha (raise NotImplementedError)
                for j in range(i + 1, len(lines)):
                    if "raise NotImplementedError" in lines[j]:
                        alpha_end = j
                        break
            if "def beta():" in line:
                beta_start = i
        assert alpha_end is not None and beta_start is not None
        # 2 blank lines between
        assert beta_start - alpha_end == 3  # line after raise + 2 blanks + def line

    def test_metadata_sha256(self):
        manifest = _make_manifest(elements=[_make_func()])
        assembler = DeterministicFileAssembler()
        result = assembler.render_specs(manifest)
        assert len(result.metadata) == 1
        entry = result.metadata[0]
        assert len(entry.sha256) == 64  # SHA-256 hex digest
        assert entry.validated is True
        assert entry.elements_count == 1

    def test_render_failure_attribution(self):
        """Render failures should have phase='render' and status='syntax_error'."""
        # Use an element with an invalid identifier to trigger a failure
        manifest = _make_manifest(elements=[
            ForwardElementSpec(
                kind=ElementKind.FUNCTION,
                name="123invalid",
                signature=Signature(params=[]),
            ),
        ])
        assembler = DeterministicFileAssembler()
        result = assembler.render_specs(manifest)
        assert len(result.failures) == 1
        assert result.failures[0].phase == "render"
        assert result.failures[0].status == "syntax_error"

    def test_multiple_files_sorted(self):
        """Files should be rendered in sorted path order."""
        manifest = ForwardManifest(file_specs={
            "src/z_module.py": ForwardFileSpec(
                file="src/z_module.py",
                elements=[_make_func("zfn")],
            ),
            "src/a_module.py": ForwardFileSpec(
                file="src/a_module.py",
                elements=[_make_func("afn")],
            ),
        })
        assembler = DeterministicFileAssembler()
        result = assembler.render_specs(manifest)
        paths = list(result.specs.keys())
        assert paths == sorted(paths)


# ═══════════════════════════════════════════════════════════════════════════
# Safety & validation
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
class TestSafetyAndValidation:

    def test_invalid_identifier_fails_fast(self):
        manifest = _make_manifest(elements=[
            ForwardElementSpec(
                kind=ElementKind.FUNCTION,
                name="not-valid",
                signature=Signature(params=[]),
            ),
        ])
        assembler = DeterministicFileAssembler()
        result = assembler.render_specs(manifest)
        assert len(result.failures) == 1
        assert "identifier" in (result.failures[0].error or "").lower()

    def test_keyword_rejected(self):
        manifest = _make_manifest(elements=[
            ForwardElementSpec(
                kind=ElementKind.FUNCTION,
                name="class",
                signature=Signature(params=[]),
            ),
        ])
        assembler = DeterministicFileAssembler()
        result = assembler.render_specs(manifest)
        assert len(result.failures) == 1
        assert "keyword" in (result.failures[0].error or "").lower()

    def test_path_traversal_rejection(self, tmp_path):
        """Paths with .. should be rejected during materialize."""
        assembler = DeterministicFileAssembler()
        results = assembler.materialize(
            {"../escape.py": "# bad"},
            project_root=tmp_path,
        )
        assert len(results) == 1
        assert results[0].status == "syntax_error"
        assert "safety" in (results[0].error or "").lower() or "traversal" in (results[0].error or "").lower()

    def test_utf8_encoding(self, tmp_path):
        """Materialized files should be UTF-8."""
        manifest = _make_manifest(
            file_path="mod.py",
            elements=[_make_func("greet", docstring="Say héllo")],
        )
        assembler = DeterministicFileAssembler()
        result = assembler.render_specs(manifest)
        mat_results = assembler.materialize(result.specs, project_root=tmp_path)
        created = [r for r in mat_results if r.status == "created"]
        assert len(created) >= 1
        content = (tmp_path / "mod.py").read_text(encoding="utf-8")
        assert "héllo" in content

    def test_parent_class_validation(self):
        """parent_class on non-method kind should raise ValueError."""
        with pytest.raises(ValueError, match="parent_class"):
            ForwardElementSpec(
                kind=ElementKind.FUNCTION,
                name="bad",
                parent_class="SomeClass",
                signature=Signature(params=[]),
            )


# ═══════════════════════════════════════════════════════════════════════════
# Materialize
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
class TestMaterialize:

    def test_existing_file_skipped(self, tmp_path):
        existing = tmp_path / "existing.py"
        existing.write_text("# original content", encoding="utf-8")

        assembler = DeterministicFileAssembler()
        results = assembler.materialize(
            {"existing.py": "# new content"},
            project_root=tmp_path,
        )
        assert results[0].status == "skipped_exists"
        # Original content preserved
        assert existing.read_text(encoding="utf-8") == "# original content"

    def test_dry_run_no_write(self, tmp_path):
        assembler = DeterministicFileAssembler()
        results = assembler.materialize(
            {"new.py": "# content"},
            project_root=tmp_path,
            dry_run=True,
        )
        assert results[0].status == "would_create"
        assert not (tmp_path / "new.py").exists()

    def test_dry_run_existing(self, tmp_path):
        (tmp_path / "existing.py").write_text("# old", encoding="utf-8")
        assembler = DeterministicFileAssembler()
        results = assembler.materialize(
            {"existing.py": "# new"},
            project_root=tmp_path,
            dry_run=True,
        )
        assert results[0].status == "would_skip_exists"

    def test_init_chain_created(self, tmp_path):
        assembler = DeterministicFileAssembler()
        results = assembler.materialize(
            {"pkg/sub/mod.py": SKELETON_SENTINEL + "\n"},
            project_root=tmp_path,
        )
        # Should have created __init__.py for pkg/ and pkg/sub/
        created = [r for r in results if r.status == "created"]
        created_paths = [r.file_path for r in created]
        assert any("__init__.py" in p for p in created_paths)
        assert (tmp_path / "pkg" / "__init__.py").exists()
        assert (tmp_path / "pkg" / "sub" / "__init__.py").exists()

    def test_materialize_phase_attribution(self, tmp_path):
        assembler = DeterministicFileAssembler()
        results = assembler.materialize(
            {"new.py": "# content"},
            project_root=tmp_path,
        )
        for r in results:
            assert r.phase == "materialize"

    def test_materialize_creates_file(self, tmp_path):
        manifest = _make_manifest(
            file_path="output.py",
            elements=[_make_func("hello")],
        )
        assembler = DeterministicFileAssembler()
        result = assembler.render_specs(manifest)
        mat_results = assembler.materialize(result.specs, project_root=tmp_path)
        created = [r for r in mat_results if r.status == "created"]
        assert len(created) >= 1
        content = (tmp_path / "output.py").read_text(encoding="utf-8")
        assert SKELETON_SENTINEL in content
        assert "def hello():" in content


# ═══════════════════════════════════════════════════════════════════════════
# Golden fixtures
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
class TestGoldenFixtures:

    def test_golden_simple_module(self):
        manifest = _make_manifest(
            elements=[
                _make_func("compute", params=[
                    Param(name="x", annotation="int"),
                    Param(name="y", annotation="int", default="0"),
                ], return_annotation="str"),
                _make_func("process", params=[
                    Param(name="data", annotation="str"),
                ], return_annotation="None"),
            ],
            imports=[
                ForwardImportSpec(kind="import", module="os"),
                ForwardImportSpec(kind="from", module="pathlib", names=["Path"]),
            ],
        )
        assembler = DeterministicFileAssembler()
        result = assembler.render_specs(manifest)
        rendered = list(result.specs.values())[0]
        expected = (GOLDEN_DIR / "golden_simple_module.py").read_text(encoding="utf-8")
        assert rendered == expected, (
            f"Golden mismatch for golden_simple_module.py.\n"
            f"--- Expected ---\n{expected}\n"
            f"--- Got ---\n{rendered}"
        )

    def test_golden_class_with_methods(self):
        manifest = _make_manifest(
            elements=[
                _make_class("BaseProcessor", docstring="Base class for data processing."),
                _make_func("__init__", parent_class="BaseProcessor",
                           params=[Param(name="self"), Param(name="config", annotation="dict")],
                           return_annotation="None"),
                _make_func("process", parent_class="BaseProcessor",
                           params=[Param(name="self"), Param(name="data", annotation="str")],
                           return_annotation="Optional[str]"),
                _make_func("validate", parent_class="BaseProcessor",
                           params=[Param(name="data", annotation="str")],
                           return_annotation="bool",
                           decorators=["staticmethod"]),
            ],
            imports=[
                ForwardImportSpec(kind="from", module="typing", names=["Optional"]),
            ],
        )
        assembler = DeterministicFileAssembler()
        result = assembler.render_specs(manifest)
        rendered = list(result.specs.values())[0]
        expected = (GOLDEN_DIR / "golden_class_with_methods.py").read_text(encoding="utf-8")
        assert rendered == expected, (
            f"Golden mismatch for golden_class_with_methods.py.\n"
            f"--- Expected ---\n{expected}\n"
            f"--- Got ---\n{rendered}"
        )

    def test_golden_async_module(self):
        manifest = _make_manifest(
            elements=[
                ForwardElementSpec(
                    kind=ElementKind.ASYNC_FUNCTION,
                    name="fetch_data",
                    signature=Signature(params=[
                        Param(name="url", annotation="str"),
                        Param(name="args", kind=ParamKind.VAR_POSITIONAL),
                        Param(name="kwargs", kind=ParamKind.VAR_KEYWORD),
                    ], return_annotation="dict"),
                ),
                ForwardElementSpec(
                    kind=ElementKind.ASYNC_FUNCTION,
                    name="send_request",
                    signature=Signature(params=[
                        Param(name="method", annotation="str"),
                        Param(name="timeout", annotation="int", default="30", kind=ParamKind.KEYWORD_ONLY),
                    ], return_annotation="str"),
                ),
            ],
            imports=[
                ForwardImportSpec(kind="import", module="asyncio"),
            ],
        )
        assembler = DeterministicFileAssembler()
        result = assembler.render_specs(manifest)
        rendered = list(result.specs.values())[0]
        expected = (GOLDEN_DIR / "golden_async_module.py").read_text(encoding="utf-8")
        assert rendered == expected, (
            f"Golden mismatch for golden_async_module.py.\n"
            f"--- Expected ---\n{expected}\n"
            f"--- Got ---\n{rendered}"
        )

    def test_golden_constants_and_all(self):
        manifest = _make_manifest(
            elements=[
                _make_const("MAX_RETRIES", annotation="int"),
                _make_const("DEFAULT_TIMEOUT", annotation="float"),
                _make_func("get_config", return_annotation="dict"),
            ],
        )
        assembler = DeterministicFileAssembler()
        result = assembler.render_specs(manifest)
        rendered = list(result.specs.values())[0]
        expected = (GOLDEN_DIR / "golden_constants_and_all.py").read_text(encoding="utf-8")
        assert rendered == expected, (
            f"Golden mismatch for golden_constants_and_all.py.\n"
            f"--- Expected ---\n{expected}\n"
            f"--- Got ---\n{rendered}"
        )


# ═══════════════════════════════════════════════════════════════════════════
# Error attribution
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
class TestErrorAttribution:

    def test_render_failure_phase(self):
        """Render errors have phase='render'."""
        manifest = _make_manifest(elements=[
            ForwardElementSpec(
                kind=ElementKind.FUNCTION,
                name="123bad",
                signature=Signature(params=[]),
            ),
        ])
        assembler = DeterministicFileAssembler()
        result = assembler.render_specs(manifest)
        assert all(f.phase == "render" for f in result.failures)

    def test_materialize_failure_phase(self, tmp_path):
        """Materialize errors have phase='materialize'."""
        assembler = DeterministicFileAssembler()
        results = assembler.materialize(
            {"../bad.py": "# content"},
            project_root=tmp_path,
        )
        assert all(r.phase == "materialize" for r in results)


# ═══════════════════════════════════════════════════════════════════════════
# FileStubResult + ScaffoldPhaseOutput models
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
class TestContextSchemaModels:

    def test_file_stub_result_creation(self):
        r = FileStubResult(
            file_path="test.py",
            elements_count=3,
            imports_count=2,
            status="created",
            phase="materialize",
        )
        assert r.file_path == "test.py"
        assert r.phase == "materialize"
        assert r.error is None

    def test_file_stub_result_render_phase(self):
        r = FileStubResult(
            file_path="test.py",
            elements_count=1,
            imports_count=0,
            status="syntax_error",
            phase="render",
            error="bad syntax",
        )
        assert r.phase == "render"
        assert r.error == "bad syntax"

    def test_scaffold_output_backward_compat(self):
        """ScaffoldPhaseOutput works without new fields (backward compat)."""
        out = ScaffoldPhaseOutput(
            scaffold={
                "directories_needed": [],
                "directories_created": [],
                "project_root": "/tmp/test",
            },
        )
        assert out.file_stubs == []
        assert out.file_stubs_created == 0
        assert out.assembly_degraded is False

    def test_scaffold_output_with_stubs(self):
        out = ScaffoldPhaseOutput(
            scaffold={
                "directories_needed": [],
                "directories_created": [],
                "project_root": "/tmp/test",
            },
            file_stubs=[{"file_path": "mod.py", "status": "created"}],
            file_stubs_created=1,
            assembly_degraded=False,
        )
        assert out.file_stubs_created == 1

    def test_assembly_degraded_flag(self):
        out = ScaffoldPhaseOutput(
            scaffold={
                "directories_needed": [],
                "directories_created": [],
                "project_root": "/tmp/test",
            },
            assembly_degraded=True,
        )
        assert out.assembly_degraded is True


# ═══════════════════════════════════════════════════════════════════════════
# StubManifestEntry + RenderResult
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
class TestResultTypes:

    def test_stub_manifest_entry_asdict(self):
        e = StubManifestEntry(
            file_path="mod.py",
            sha256="abc123",
            elements_count=5,
            imports_count=2,
            validated=True,
        )
        d = e._asdict()
        assert d["file_path"] == "mod.py"
        assert d["validated"] is True

    def test_render_result_is_namedtuple(self):
        r = RenderResult(specs={}, failures=[], metadata=[])
        assert r.specs == {}
        assert isinstance(r, tuple)
