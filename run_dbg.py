from unittest.mock import Mock, patch
from startd8.workflows.builtin.lead_contractor_workflow import LeadContractorWorkflow
from startd8.workflows.builtin.lead_contractor_models import ImplementationSpec
from startd8.forward_manifest_validator import ContractViolation
import logging

logging.basicConfig(level=logging.DEBUG)

@patch("startd8.forward_manifest_validator.validate_forward_manifest")
def test_dbg(mock_validate):
    mock_validate.return_value = [
        ContractViolation(
            contract_id="function-foo",
            violation_type="MissingFunction",
            expected="def foo():",
            actual="None",
            file_path="src/app.py",
            severity="error"
        )
    ]

    workflow = LeadContractorWorkflow()
    lead_agent = Mock()
    lead_agent.model = "claude-sonnet"
    
    token_usage = Mock()
    token_usage.input = 100
    token_usage.output = 50

    lead_agent.generate.return_value = (
        "### Score: 90\n### Verdict: PASS\n### Strengths\n- Good\n",
        100,
        token_usage
    )

    spec = ImplementationSpec(
        spec_id="spec-1",
        task_summary="task",
        requirements=[],
        technical_approach="",
        acceptance_criteria=[]
    )

    mock_manifest = Mock()
    mock_manifest.contracts = ["fake"]

    result = workflow._review_draft(
        lead_agent=lead_agent,
        task_description="do thing",
        spec=spec,
        implementation="```python\ndef wrong_name(): pass\n```",
        pass_threshold=80,
        iteration=1,
        forward_manifest=mock_manifest,
        target_files=["src/app.py"]
    )
    print(f"Passed: {result.passed}")
    print(f"Blocking issues: {result.blocking_issues}")

test_dbg()
