"""FR-6 transient import-alias bridge tests (lead-contractor removal, migration window).

These assert that external consumers importing the OLD module paths still resolve to the
canonical (renamed) modules/symbols while the staged consumer migration is in flight.
The bridge modules are removed in Phase 5 (FR-5); this test is removed with them.
"""
import importlib


def test_old_workflow_module_path_resolves_to_primary():
    old = importlib.import_module("startd8.workflows.builtin.lead_contractor_workflow")
    new = importlib.import_module("startd8.workflows.builtin.primary_contractor_workflow")
    # sys.modules aliasing makes the old path the SAME module object as the canonical one.
    assert old is new
    # Both the canonical class and the legacy alias resolve through the old path.
    assert old.PrimaryContractorWorkflow is new.PrimaryContractorWorkflow
    assert old.LeadContractorWorkflow is new.PrimaryContractorWorkflow


def test_old_models_module_path_resolves():
    from startd8.workflows.builtin.lead_contractor_models import (
        LeadContractorConfig,
        LeadContractorResult,
        PrimaryContractorConfig,
        PrimaryContractorResult,
    )
    assert LeadContractorConfig is PrimaryContractorConfig
    assert LeadContractorResult is PrimaryContractorResult


def test_old_contextcore_module_path_resolves():
    from startd8.workflows.builtin.lead_contractor_contextcore_workflow import (
        LeadContractorContextCoreWorkflow,
        PrimaryContractorContextCoreWorkflow,
    )
    assert LeadContractorContextCoreWorkflow is PrimaryContractorContextCoreWorkflow


def test_old_generator_module_path_resolves():
    from startd8.contractors.generators.lead_contractor import (
        LeadContractorCodeGenerator,
        PrimaryContractorCodeGenerator,
    )
    assert LeadContractorCodeGenerator is PrimaryContractorCodeGenerator
