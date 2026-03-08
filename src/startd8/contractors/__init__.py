"""
Prime Contractor Framework - Continuous Integration for Code Generation.

This module provides the Prime Contractor workflow pattern, which ensures
code is integrated immediately after generation to prevent merge conflicts.

The framework is designed to work standalone (without ContextCore) while
providing enhanced observability when ContextCore is available.

Key Components:
- PrimeContractorWorkflow: Main orchestration class
- FeatureQueue: Ordered feature queue with dependencies
- IntegrationCheckpoint: Validates code before proceeding
- Protocols: Abstract interfaces for extensibility

Example (standalone):
    from startd8.contractors import PrimeContractorWorkflow

    workflow = PrimeContractorWorkflow()
    workflow.queue.add_feature("auth", "Add authentication")
    result = workflow.run()

Example (with ContextCore):
    from startd8.contractors import PrimeContractorWorkflow
    from startd8.contractors.adapters.contextcore import ContextCoreInstrumentor

    workflow = PrimeContractorWorkflow(
        instrumentor=ContextCoreInstrumentor(project_id="myproject"),
    )
    result = workflow.run()  # Emits spans to Tempo
"""

from .checkpoint import (
    CheckpointResult,
    CheckpointStatus,
    IntegrationCheckpoint,
)
from .integration_engine import IntegrationEngine, NullListener
from .prime_contractor import PrimeContractorWorkflow
from .protocols import (
    CheckpointFailedCallback,
    CodeGenerator,
    FeatureCompleteCallback,
    GenerationResult,
    IntegrationListener,
    IntegrationResult,
    IntegrationUnit,
    Instrumentor,
    MergeResult,
    MergeStatus,
    MergeStrategy,
    ProgressCallback,
    SizeEstimate,
    SizeEstimator,
    SpanContext,
)
from .queue import (
    FeatureQueue,
    FeatureSpec,
    FeatureStatus,
)
from .registry import (
    ContractorRegistry,
    discover,
    get_registry,
)
from .cli_helpers import add_workflow_args, apply_workflow_args

# Optional: Code generators (require workflow dependencies)
try:
    from .generators import PrimaryContractorCodeGenerator, LeadContractorCodeGenerator
    _GENERATORS_AVAILABLE = True
except ImportError:
    PrimaryContractorCodeGenerator = None  # type: ignore
    LeadContractorCodeGenerator = None  # type: ignore
    _GENERATORS_AVAILABLE = False

__all__ = [
    # Main workflow
    "PrimeContractorWorkflow",
    # Integration engine
    "IntegrationEngine",
    "NullListener",
    # Queue
    "FeatureQueue",
    "FeatureSpec",
    "FeatureStatus",
    # Checkpoints
    "IntegrationCheckpoint",
    "CheckpointResult",
    "CheckpointStatus",
    # Protocols
    "CodeGenerator",
    "Instrumentor",
    "SizeEstimator",
    "MergeStrategy",
    "IntegrationUnit",
    "IntegrationListener",
    # Data classes
    "GenerationResult",
    "SizeEstimate",
    "MergeResult",
    "MergeStatus",
    "SpanContext",
    "IntegrationResult",
    # Callbacks
    "ProgressCallback",
    "FeatureCompleteCallback",
    "CheckpointFailedCallback",
    # Registry
    "ContractorRegistry",
    "get_registry",
    "discover",
    # CLI helpers
    "add_workflow_args",
    "apply_workflow_args",
    # Generators (optional)
    "PrimaryContractorCodeGenerator",
    "LeadContractorCodeGenerator",  # Backward-compat alias
]
