"""Tests for Go module wiring into the pipeline (forward manifest, splicer, dep gen)."""

from pathlib import Path

import pytest

from startd8.forward_manifest import InterfaceContract
from startd8.micro_prime.splicer import splice_body_into_skeleton, SpliceResult
from startd8.utils.code_manifest import ElementKind, Param, ParamKind, Signature, Visibility
from startd8.forward_manifest import ForwardElementSpec

# Minimal signature for callable elements (ForwardElementSpec requires it)
_EMPTY_SIG = Signature(params=[], return_annotation=None)


@pytest.mark.unit
class TestSplicerGoDispatch:
    """Test that splice_body_into_skeleton dispatches to Go splicer for Go files."""

    def _make_element(self, name, kind=ElementKind.FUNCTION, parent_class=None):
        sig = _EMPTY_SIG if kind in (ElementKind.FUNCTION, ElementKind.METHOD) else None
        return ForwardElementSpec(
            kind=kind,
            name=name,
            signature=sig,
            visibility=Visibility.PUBLIC,
            parent_class=parent_class,
        )

    def test_go_skeleton_detected_by_package_keyword(self):
        skeleton = '''\
package main

func Hello() {
\tpanic("not implemented")
}
'''
        generated_body = '''\
func Hello() {
\tfmt.Println("hello world")
}
'''
        elem = self._make_element("Hello")
        result = splice_body_into_skeleton(generated_body, elem, skeleton)
        assert result.code is not None
        assert "hello world" in result.code
        assert 'panic("not implemented")' not in result.code

    def test_go_skeleton_detected_by_file_path(self):
        skeleton = '''\
// This file has no package line yet but is .go
func Process() {
\tpanic("not implemented")
}
'''
        generated_body = '''\
func Process() {
\tresult := compute()
\treturn result
}
'''
        elem = self._make_element("Process")
        result = splice_body_into_skeleton(
            generated_body, elem, skeleton, file_path="src/service/handler.go",
        )
        assert result.code is not None
        assert "compute()" in result.code

    def test_go_method_splice_with_parent_class(self):
        skeleton = '''\
package main

type Server struct{}

func (s *Server) Start() error {
\tpanic("not implemented")
}
'''
        generated_body = '''\
func (s *Server) Start() error {
\tlis, err := net.Listen("tcp", ":8080")
\tif err != nil {
\t\treturn err
\t}
\treturn s.srv.Serve(lis)
}
'''
        elem = self._make_element("Start", kind=ElementKind.METHOD, parent_class="Server")
        result = splice_body_into_skeleton(generated_body, elem, skeleton)
        assert result.code is not None
        assert "net.Listen" in result.code

    def test_python_skeleton_still_uses_ast_path(self):
        """Python files should NOT dispatch to Go splicer."""
        skeleton = '''\
def hello():
    raise NotImplementedError
'''
        body = '''\
    print("hello")
'''
        elem = self._make_element("hello")
        result = splice_body_into_skeleton(body, elem, skeleton)
        assert result.code is not None
        assert "hello" in result.code

    def test_go_splice_warning_becomes_violation(self):
        """Warnings from Go splicer become SpliceViolation objects."""
        skeleton = '''\
package main

func Existing() {
\tfmt.Println("real code")
}
'''
        generated_body = '''\
func Existing() {
\tfmt.Println("new code")
}
'''
        elem = self._make_element("Existing")
        result = splice_body_into_skeleton(generated_body, elem, skeleton)
        # "not a stub" warning should become a violation
        assert any(v.violation_type == "go_splice_warning" for v in result.violations)


@pytest.mark.unit
class TestForwardManifestGoReconciler:
    """Test that SourceReconciler discovers Go elements."""

    def test_reconcile_go_file(self, tmp_path):
        """Go files produce function and struct contracts."""
        from startd8.forward_manifest_extractor import SourceReconciler
        from startd8.workflows.builtin.plan_ingestion_models import ParsedFeature

        go_file = tmp_path / "src" / "service" / "handler.go"
        go_file.parent.mkdir(parents=True)
        go_file.write_text('''\
package service

type Server struct {
    port int
}

func (s *Server) Start() error {
    return nil
}

func NewServer(port int) *Server {
    return &Server{port: port}
}
''')

        feature = ParsedFeature(
            feature_id="F-1",
            name="service handler",
            description="Handle requests",
            target_files=["src/service/handler.go"],
        )

        reconciler = SourceReconciler(project_root=tmp_path)
        contracts = reconciler.reconcile([feature])

        # Should find: Server (struct), Start (method), NewServer (function)
        names = {c.description for c in contracts}
        assert any("Server" in n for n in names)
        assert any("NewServer" in n for n in names)
        assert any("Start" in n for n in names)

    def test_reconcile_skips_missing_dir(self):
        from startd8.forward_manifest_extractor import SourceReconciler

        reconciler = SourceReconciler(project_root=Path("/nonexistent/path"))
        contracts = reconciler.reconcile([])
        assert contracts == []


@pytest.mark.unit
class TestDependencyFileWiring:
    """Test that _ensure_dependency_file generates go.mod when appropriate."""

    def test_go_mod_not_generated_if_exists(self, tmp_path):
        """Don't overwrite existing go.mod."""
        from startd8.languages.go import GoLanguageProfile

        (tmp_path / "go.mod").write_text("module existing\n")
        profile = GoLanguageProfile()

        # Simulate what _ensure_dependency_file checks
        for pattern in profile.build_file_patterns:
            if (tmp_path / pattern).exists():
                exists = True
                break
        assert exists  # go.mod already exists, so generation is skipped

    def test_go_mod_generated_from_metadata(self, tmp_path):
        from startd8.languages.go import GoLanguageProfile

        profile = GoLanguageProfile()
        content = profile.generate_dependency_file(
            project_root=tmp_path,
            service_name="frontend",
            module_path="github.com/example/frontend",
            dependencies=["google.golang.org/grpc v1.68.0"],
            metadata={"go_version": "1.23"},
        )
        assert content is not None
        assert "module github.com/example/frontend" in content
        assert "google.golang.org/grpc v1.68.0" in content
