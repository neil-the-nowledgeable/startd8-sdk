import pytest
from pathlib import Path
from unittest.mock import patch
from startd8.contractors.handoff import HandoffData, wrap_handoff_in_contract, write_design_handoff

@pytest.fixture(autouse=True)
def mock_validation():
    """Mock schema validation to avoid jsonschema dependency during tests."""
    with patch("startd8.contractors.handoff._validate_handoff"):
        yield

def test_wrap_handoff_in_contract():
    handoff = HandoffData(
        enriched_seed_path="/tmp/seed.json",
        project_root="/tmp/proj",
        output_dir="/tmp/out",
        workflow_id="wf-123",
        context_files=[{"path": "foo.txt", "checksum": "abc"}]
    )
    
    contract = wrap_handoff_in_contract(handoff, project_id="proj-1")
    
    if hasattr(contract, "inputs"):
        inputs = contract.inputs
        status = contract.status
    else:
        inputs = contract["inputs"]
        status = contract["status"]
        
    assert inputs["workflow_id"] == "wf-123"
    assert inputs["context_files"][0]["checksum"] == "abc"
    assert status == "pending" or status.value == "pending"

def test_write_design_handoff_creates_contract(tmp_path):
    output_dir = tmp_path / "designs"
    
    write_design_handoff(
        output_dir=str(output_dir),
        enriched_seed_path="/tmp/seed.json",
        project_root="/tmp/proj",
        workflow_id="wf-test",
    )
    
    contract_file = output_dir / "design-handoff-contract.json"
    assert contract_file.exists()
    
    import json
    data = json.loads(contract_file.read_text())
    assert data["handoff_id"] == "wf-test"
