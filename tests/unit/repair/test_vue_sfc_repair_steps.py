"""REQ-VUE-P-009: JS repair steps on Vue SFC primary script projection."""

from __future__ import annotations

from pathlib import Path

from startd8.repair.models import RepairContext
from startd8.repair.steps.contamination_strip_js import ContaminationStripJsStep
from startd8.repair.steps.var_to_const import VarToConstStep


def test_contamination_strip_removes_python_from_vue_script_only() -> None:
    sfc = (
        "<template><p>x</p></template>\n"
        "<script setup>\n"
        "import os\n"
        "const a = 1\n"
        "</script>\n"
    )
    step = ContaminationStripJsStep()
    ctx = RepairContext(diagnostics=[], config=None, project_root=Path("."))
    result = step(sfc, ctx, Path("src/App.vue"))
    assert result.modified is True
    assert "import os" not in result.code
    assert "<template>" in result.code
    assert "const a = 1" in result.code


def test_var_to_const_on_vue_script_reinjects() -> None:
    sfc = "<script setup>\nvar x = 1\n</script>\n"
    step = VarToConstStep()
    ctx = RepairContext(diagnostics=[], config=None, project_root=Path("."))
    result = step(sfc, ctx, Path("Comp.vue"))
    assert result.modified is True
    assert "const x = 1" in result.code
    assert "<script setup>" in result.code
    assert "var x" not in result.code
