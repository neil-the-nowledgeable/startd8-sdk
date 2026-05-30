"""
Implementation Engine — reusable spec-draft-review loop.

Extracts the Prime Contractor's spec-creation and iterative draft-review
loop into a standalone package that both PrimaryContractorWorkflow and Artisan
ImplementPhaseHandler can consume.

Usage::

    from startd8.implementation_engine import (
        DefaultImplementationEngine,
        EngineRequest,
        EngineResult,
    )

    engine = DefaultImplementationEngine()
    request = EngineRequest(
        task_description="Implement feature X",
        drafter_agent_spec="gemini:gemini-2.5-flash-lite",
        reviewer_agent_spec="anthropic:claude-sonnet-4-6",
        context={"design_document": "..."},
    )
    result = engine.build_and_execute(request)
"""

from .engine import DefaultImplementationEngine
from .models import (
    DraftResult,
    EngineRequest,
    EngineResult,
    ReviewResult,
    SpecResult,
)
from .protocol import ImplementationEngine


__all__ = [
    "DefaultImplementationEngine",
    "EngineRequest",
    "EngineResult",
    "ImplementationEngine",
    "SpecResult",
    "DraftResult",
    "ReviewResult",
]
