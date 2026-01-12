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
"""

# Imports are done lazily to avoid circular imports
# and to allow partial availability

__all__ = [
    "PipelineWorkflow",
    "DocEnhancementWorkflow",
    "IterativeDevWorkflowWrapper",
    "DesignPolishWorkflow",
    "CriticalReviewWorkflow",
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
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
