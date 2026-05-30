"""
Built-in workflow implementations for the StartD8 SDK.

These workflows wrap existing SDK functionality to provide a
unified interface for agent-accessible execution.

Available workflows:
- PipelineWorkflow: Sequential multi-agent pipelines
- DocEnhancementWorkflow: Document enhancement chains
- IterativeDevWorkflowWrapper: Dev-review-fix iterations
- DesignPolishWorkflow: 3-stage design document refinement
- CriticalReviewWorkflow: Multi-agent document review
- PrimaryContractorWorkflow: Cost-efficient primary contractor pattern
- PrimaryContractorContextCoreWorkflow: Primary contractor with ContextCore task tracking
- LeadContractorWorkflow: Backward-compat alias for PrimaryContractorWorkflow
- LeadContractorContextCoreWorkflow: Backward-compat alias for PrimaryContractorContextCoreWorkflow
- PolicyAnalysisWorkflow: Multi-agent critical policy analysis
- PlainLanguageWorkflow: Simplifies complex content into plain language
- PlanIngestionWorkflow: Parses, assesses, and transforms generic plans into SDK-native formats
- DomainPreflightWorkflow: Domain-aware pre-flight analysis for artisan context seeds
- ConvergentReviewWorkflow: Requirements + plan sequential review (two-step arc review)
"""

# Imports are done lazily to avoid circular imports
# and to allow partial availability

__all__ = [
    "PipelineWorkflow",
    "DocEnhancementWorkflow",
    "IterativeDevWorkflowWrapper",
    "DesignPolishWorkflow",
    "CriticalReviewWorkflow",
    "DocReviewLogWorkflow",
    "ArchitecturalReviewLogWorkflow",
    "PrimaryContractorWorkflow",
    "PrimaryContractorContextCoreWorkflow",
    "LeadContractorWorkflow",
    "LeadContractorContextCoreWorkflow",
    "PolicyAnalysisWorkflow",
    "PlainLanguageWorkflow",
    "PlanIngestionWorkflow",
    "DomainPreflightWorkflow",
    "ConvergentReviewWorkflow",
]


def __getattr__(name: str):
    """Lazy import of workflow classes."""
    if name == "PipelineWorkflow":
        from .pipeline_workflow import PipelineWorkflow
        return PipelineWorkflow
    elif name == "DocEnhancementWorkflow":
        from .doc_enhancement_workflow import DocEnhancementWorkflow
        return DocEnhancementWorkflow
    elif name == "IterativeDevWorkflowWrapper":
        from .iterative_dev_workflow import IterativeDevWorkflowWrapper
        return IterativeDevWorkflowWrapper
    elif name == "DesignPolishWorkflow":
        from .design_polish_workflow import DesignPolishWorkflow
        return DesignPolishWorkflow
    elif name == "CriticalReviewWorkflow":
        from .critical_review_workflow import CriticalReviewWorkflow
        return CriticalReviewWorkflow
    elif name == "DocReviewLogWorkflow":
        from .doc_review_log_workflow import DocReviewLogWorkflow
        return DocReviewLogWorkflow
    elif name == "ArchitecturalReviewLogWorkflow":
        from .architectural_review_log_workflow import ArchitecturalReviewLogWorkflow
        return ArchitecturalReviewLogWorkflow
    elif name == "PrimaryContractorWorkflow":
        from .primary_contractor_workflow import PrimaryContractorWorkflow
        return PrimaryContractorWorkflow
    elif name == "PrimaryContractorContextCoreWorkflow":
        from .primary_contractor_contextcore_workflow import PrimaryContractorContextCoreWorkflow
        return PrimaryContractorContextCoreWorkflow
    elif name == "LeadContractorWorkflow":
        from .primary_contractor_workflow import LeadContractorWorkflow
        return LeadContractorWorkflow
    elif name == "LeadContractorContextCoreWorkflow":
        from .primary_contractor_contextcore_workflow import LeadContractorContextCoreWorkflow
        return LeadContractorContextCoreWorkflow
    elif name == "PolicyAnalysisWorkflow":
        from .policy_analysis_workflow import PolicyAnalysisWorkflow
        return PolicyAnalysisWorkflow
    elif name == "PlainLanguageWorkflow":
        from .plain_language_workflow import PlainLanguageWorkflow
        return PlainLanguageWorkflow
    elif name == "PlanIngestionWorkflow":
        from .plan_ingestion_workflow import PlanIngestionWorkflow
        return PlanIngestionWorkflow
    elif name == "DomainPreflightWorkflow":
        from .domain_preflight_workflow import DomainPreflightWorkflow
        return DomainPreflightWorkflow
    elif name == "ConvergentReviewWorkflow":
        from .convergent_review_workflow import ConvergentReviewWorkflow
        return ConvergentReviewWorkflow
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
