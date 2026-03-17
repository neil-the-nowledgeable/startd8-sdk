"""Tests for Go text-based stub detection (P5)."""

from pathlib import Path

import pytest

from startd8.contractors.checkpoint import IntegrationCheckpoint, CheckpointStatus
from startd8.languages.go import GoLanguageProfile


@pytest.mark.unit
class TestGoStubDetection:
    """Test that check_stubs detects Go stub patterns."""

    def _make_checkpoint(self, tmp_path):
        profile = GoLanguageProfile()
        return IntegrationCheckpoint(
            project_root=tmp_path,
            run_tests=False,
            language_profile=profile,
        )

    def test_detects_panic_not_implemented(self, tmp_path):
        go_file = tmp_path / "handler.go"
        go_file.write_text('''\
package main

func HandleRequest() {
    panic("not implemented")
}

func HandleResponse() {
    panic("not implemented")
}
''')
        cp = self._make_checkpoint(tmp_path)
        result = cp.check_stubs([go_file])
        # 2/2 functions are stubs → 100% > 30% threshold
        assert result.status == CheckpointStatus.WARNING
        assert "2/2" in result.warnings[0]

    def test_detects_empty_body(self, tmp_path):
        go_file = tmp_path / "handler.go"
        go_file.write_text('''\
package main

func HandleRequest() {}

func HandleResponse() {
    fmt.Println("real implementation")
}
''')
        cp = self._make_checkpoint(tmp_path)
        result = cp.check_stubs([go_file])
        # 1/2 = 50% > 30% threshold
        assert result.status == CheckpointStatus.WARNING

    def test_detects_todo_comment(self, tmp_path):
        go_file = tmp_path / "handler.go"
        go_file.write_text('''\
package main

func HandleRequest() {
    // TODO implement this
}

func HandleResponse() {
    // TODO implement this
}
''')
        cp = self._make_checkpoint(tmp_path)
        result = cp.check_stubs([go_file])
        assert result.status == CheckpointStatus.WARNING

    def test_passes_real_implementation(self, tmp_path):
        go_file = tmp_path / "handler.go"
        go_file.write_text('''\
package main

import "fmt"

func HandleRequest() {
    fmt.Println("handling request")
}

func HandleResponse() {
    fmt.Println("handling response")
}
''')
        cp = self._make_checkpoint(tmp_path)
        result = cp.check_stubs([go_file])
        assert result.status == CheckpointStatus.PASSED

    def test_below_threshold_passes(self, tmp_path):
        """1 stub out of 4 functions = 25% < 30% threshold."""
        go_file = tmp_path / "handler.go"
        go_file.write_text('''\
package main

func A() { fmt.Println("a") }
func B() { fmt.Println("b") }
func C() { fmt.Println("c") }
func D() { panic("not implemented") }
''')
        cp = self._make_checkpoint(tmp_path)
        result = cp.check_stubs([go_file])
        assert result.status == CheckpointStatus.PASSED

    def test_detects_pipeline_stub(self, tmp_path):
        go_file = tmp_path / "handler.go"
        go_file.write_text('''\
package main

// STARTD8_AUTO_STUB
func HandleRequest() {
    panic("not implemented")
}
''')
        cp = self._make_checkpoint(tmp_path)
        result = cp.check_stubs([go_file])
        # Pipeline stubs are info, not warnings
        assert result.status == CheckpointStatus.PASSED
        assert result.details.get("pipeline_stubs") == 1

    def test_method_stubs_detected(self, tmp_path):
        go_file = tmp_path / "server.go"
        go_file.write_text('''\
package main

func (s *Server) Start() {
    panic("not implemented")
}

func (s *Server) Stop() {
    panic("not implemented")
}
''')
        cp = self._make_checkpoint(tmp_path)
        result = cp.check_stubs([go_file])
        assert result.status == CheckpointStatus.WARNING
        assert "2/2" in result.warnings[0]

    def test_skips_non_go_files_without_profile(self, tmp_path):
        """Without language_profile, non-.py files are skipped."""
        go_file = tmp_path / "handler.go"
        go_file.write_text('package main\n\nfunc X() { panic("not implemented") }\n')
        cp = IntegrationCheckpoint(project_root=tmp_path, run_tests=False)
        result = cp.check_stubs([go_file])
        assert result.status == CheckpointStatus.PASSED
        assert result.details["files_checked"] == 0

    def test_python_stubs_still_work(self, tmp_path):
        """Python AST-based detection still works alongside text-based."""
        py_file = tmp_path / "handler.py"
        py_file.write_text('''\
def handle():
    raise NotImplementedError

def respond():
    raise NotImplementedError
''')
        cp = self._make_checkpoint(tmp_path)
        result = cp.check_stubs([py_file])
        assert result.status == CheckpointStatus.WARNING


@pytest.mark.unit
class TestGoStubPatterns:
    """Test individual stub pattern coverage."""

    def test_profile_has_stub_patterns(self):
        p = GoLanguageProfile()
        assert len(p.stub_patterns) >= 3

    def test_profile_has_function_start_pattern(self):
        p = GoLanguageProfile()
        assert p.function_start_pattern is not None

    def test_fmt_errorf_stub(self, tmp_path):
        """Detect return nil, fmt.Errorf('not implemented') as stub."""
        go_file = tmp_path / "handler.go"
        go_file.write_text('''\
package main

func GetProduct() (*Product, error) {
    return nil, fmt.Errorf("not implemented")
}

func ListProducts() (*Products, error) {
    return nil, fmt.Errorf("not implemented")
}
''')
        profile = GoLanguageProfile()
        cp = IntegrationCheckpoint(
            project_root=tmp_path, run_tests=False, language_profile=profile,
        )
        result = cp.check_stubs([go_file])
        assert result.status == CheckpointStatus.WARNING
