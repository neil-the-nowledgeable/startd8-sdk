"""
Built-in workflow implementations for the StartD8 SDK.

These workflows wrap existing SDK functionality to provide a
unified interface for agent-accessible execution.

Available workflows:
- PipelineWorkflow: Sequential multi-agent pipelines
- DocEnhancementWorkflow: Document enhancement chains
- IterativeDevWorkflowWrapper: Dev-review-fix iterations
"""

# Imports are done lazily to avoid circular imports
# and to allow partial availability

__all__ = [
    "PipelineWorkflow",
    "DocEnhancementWorkflow",
    "IterativeDevWorkflowWrapper",
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
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
