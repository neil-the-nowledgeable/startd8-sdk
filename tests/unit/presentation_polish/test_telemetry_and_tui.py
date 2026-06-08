"""FR-23 telemetry no-op safety + FR-2 TUI wiring (Tier-1 finishers)."""

from pathlib import Path

from startd8.presentation_polish import PolishConfig, apply_polish
from startd8.presentation_polish.telemetry import _OTEL_DESCRIPTORS, record_polish

pytestmark = []


def test_record_polish_never_raises(tmp_path):
    """Emission is no-op-safe whether or not OTel is configured (it must never break a $0 run)."""
    (tmp_path / "app").mkdir()
    result = apply_polish(PolishConfig(project_root=tmp_path, theme="professional"))
    # both modes, regardless of OTel availability
    record_polish(result, check=False)
    record_polish(result, check=True)


def test_descriptors_match_emitted_names():
    """Declared descriptor names must equal the create_counter names (parity bijection, FR-23)."""
    declared = {m["name"] for m in _OTEL_DESCRIPTORS["metrics"]}
    assert declared == {
        "startd8.presentation_polish.files",
        "startd8.presentation_polish.runs",
    }


def test_tui_exposes_polish_flow():
    """The TUI composes PolishMixin and the run_polish_flow entry point (FR-2)."""
    from startd8.tui.mixin_polish import PolishMixin
    from startd8.tui_improved import ImprovedTUI

    assert PolishMixin in ImprovedTUI.__mro__
    assert hasattr(ImprovedTUI, "run_polish_flow")
