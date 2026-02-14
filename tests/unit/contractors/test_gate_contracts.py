import pytest
from unittest.mock import patch, MagicMock
from startd8.contractors.gate_contracts import GateEmitter
from startd8.events.types import EventType

@pytest.fixture
def mock_event_bus():
    with patch("startd8.contractors.gate_contracts.EventBus") as mock:
        yield mock

def test_from_review_result_pass(mock_event_bus):
    review = {
        "passed": True,
        "score": 95,
        "feedback": "Great job",
        "critiques": ["Minor nit"]
    }
    
    result = GateEmitter.from_review_result("task-1", review, "wf-1")
    
    # Check shape
    if hasattr(result, "result"): # ContextCore object
        assert result.result == "pass" or result.result.value == "pass"
    else: # Dict
        assert result["result"] == "pass"
        assert result["severity"] == "info"
        assert result["blocking"] is False

    GateEmitter.emit(result)
    mock_event_bus.publish.assert_called_once()
    event = mock_event_bus.publish.call_args[0][0]
    assert event.type == EventType.QUALITY_GATE_RESULT
    assert event.data["gate_id"] == "artisan.review.task-1"

def test_from_review_result_fail(mock_event_bus):
    review = {
        "passed": False,
        "score": 40,
        "feedback": "Terrible",
        "critiques": ["Major bug"]
    }
    
    result = GateEmitter.from_review_result("task-1", review, "wf-1")
    
    if isinstance(result, dict):
        assert result["result"] == "fail"
        assert result["severity"] == "error"
        assert result["blocking"] is True

def test_from_checkpoint_result():
    # Mocking a CheckpointResult-like object
    class MockCheckpointResult:
        valid = False
        errors = ["Drift detected"]
        checkpoint_id = "chk-1"
        
    result = GateEmitter.from_checkpoint_result(MockCheckpointResult(), "wf-1")
    
    if isinstance(result, dict):
        assert result["result"] == "fail"
        assert result["phase"] == "FINALIZE_VERIFY"
        assert result["evidence"] == ["Drift detected"]

def test_from_preflight_report():
    # Mocking a PreFlightReport-like object
    class MockCheck:
        message = "Missing dep"
        name = "dep:foo"
        
    class MockReport:
        passed = False
        failed_checks = [MockCheck()]
        
    result = GateEmitter.from_preflight_report(MockReport(), "wf-1")
    
    if isinstance(result, dict):
        assert result["result"] == "fail"
        assert result["phase"] == "TEST_VALIDATE"
        assert len(result["evidence"]) == 1
        assert result["evidence"][0]["description"] == "dep:foo: Missing dep"
