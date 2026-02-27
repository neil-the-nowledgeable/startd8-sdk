"""
Protocol definition for the implementation engine.

Defines the ``ImplementationEngine`` protocol that ``DefaultImplementationEngine``
implements and consumers depend on.
"""

from typing import Protocol, runtime_checkable

from .models import EngineRequest, EngineResult


__all__ = ["ImplementationEngine"]


@runtime_checkable
class ImplementationEngine(Protocol):
    """Protocol for implementation engines.

    An implementation engine orchestrates the full per-task pipeline:
    spec creation -> [draft -> review -> feedback]* -> result.
    """

    def build_and_execute(self, request: EngineRequest) -> EngineResult:
        """Run the full spec -> draft -> review loop for a single task.

        Args:
            request: Engine request with task description, context, and config.

        Returns:
            EngineResult with spec, drafts, reviews, and final code.
        """
        ...
