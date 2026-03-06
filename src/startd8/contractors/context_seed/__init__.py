"""Context seed handler implementation package."""

from __future__ import annotations

from typing import TYPE_CHECKING

from startd8.contractors.context_seed.core import (  # noqa: F401
    ContextSeedHandlers,
    EditModeClassification,
    FinalizePhaseHandler,
    HandlerConfig,
    ImplementPhaseHandler,
    IntegratePhaseHandler,
    OTelIntegrationListener,
    PerFileMode,
    PlanPhaseHandler,
    ReviewPhaseHandler,
    ScaffoldPhaseHandler,
    SeedTask,
    SeedTaskUnit,
    TestPhaseHandler,
)

__all__ = [
    "ContextSeedHandlers",
    "DesignPhaseHandler",
    "EditModeClassification",
    "FinalizePhaseHandler",
    "HandlerConfig",
    "ImplementPhaseHandler",
    "IntegratePhaseHandler",
    "OTelIntegrationListener",
    "PerFileMode",
    "PlanPhaseHandler",
    "ReviewPhaseHandler",
    "ScaffoldPhaseHandler",
    "SeedTask",
    "SeedTaskUnit",
    "TestPhaseHandler",
]


if TYPE_CHECKING:  # pragma: no cover - typing-only imports
    from startd8.contractors.context_seed.phases.design import DesignPhaseHandler


def __getattr__(name: str):
    if name == "DesignPhaseHandler":
        from startd8.contractors.context_seed.phases.design import DesignPhaseHandler
        return DesignPhaseHandler
    raise AttributeError(name)
