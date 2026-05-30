"""
Tests for Phase 1.4 Async Audit: FR-150.

Verifies that _aexecute() exists on workflows that make async agent calls.
"""

import pytest

from startd8.workflows.builtin.critical_review_workflow import CriticalReviewWorkflow
from startd8.workflows.builtin.primary_contractor_workflow import LeadContractorWorkflow
from startd8.workflows.builtin.primary_contractor_contextcore_workflow import LeadContractorContextCoreWorkflow
from startd8.workflows.builtin.pipeline_workflow import PipelineWorkflow
from startd8.workflows.builtin.plain_language_workflow import PlainLanguageWorkflow
from startd8.workflows.builtin.policy_analysis_workflow import PolicyAnalysisWorkflow


class TestAsyncMethodExists:
    """Verify _aexecute is defined on workflows with async agent calls."""

    def test_critical_review_has_aexecute(self):
        wf = CriticalReviewWorkflow()
        assert hasattr(wf, '_aexecute')
        assert callable(wf._aexecute)

    def test_lead_contractor_has_aexecute(self):
        wf = LeadContractorWorkflow()
        assert hasattr(wf, '_aexecute')
        assert callable(wf._aexecute)

    def test_lead_contractor_contextcore_has_aexecute(self):
        wf = LeadContractorContextCoreWorkflow()
        assert hasattr(wf, '_aexecute')
        assert callable(wf._aexecute)

    def test_pipeline_has_aexecute(self):
        """Pipeline workflow already had _aexecute before Phase 1."""
        wf = PipelineWorkflow()
        assert hasattr(wf, '_aexecute')

    def test_plain_language_has_aexecute(self):
        """Plain language workflow already had _aexecute before Phase 1."""
        wf = PlainLanguageWorkflow()
        assert hasattr(wf, '_aexecute')

    def test_policy_analysis_has_aexecute(self):
        """Policy analysis workflow already had _aexecute before Phase 1."""
        wf = PolicyAnalysisWorkflow()
        assert hasattr(wf, '_aexecute')


class TestAsyncHelperMethods:
    """Verify async helper methods exist on lead_contractor workflow."""

    def test_lead_contractor_acreate_spec(self):
        wf = LeadContractorWorkflow()
        assert hasattr(wf, '_acreate_spec')
        assert callable(wf._acreate_spec)

    def test_lead_contractor_acreate_draft(self):
        wf = LeadContractorWorkflow()
        assert hasattr(wf, '_acreate_draft')
        assert callable(wf._acreate_draft)

    def test_lead_contractor_areview_draft(self):
        wf = LeadContractorWorkflow()
        assert hasattr(wf, '_areview_draft')
        assert callable(wf._areview_draft)

    def test_lead_contractor_aintegrate_final(self):
        wf = LeadContractorWorkflow()
        assert hasattr(wf, '_aintegrate_final')
        assert callable(wf._aintegrate_final)
