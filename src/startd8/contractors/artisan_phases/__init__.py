"""
Artisan Contractor phase implementations.

This package contains the 9-phase artisan pipeline:

    Phase 0: Pre-Flight Checks          (preflight.py)
    Phase 1: Plan Deconstruction         (plan_deconstruction.py)
    Phase 2: Lessons Learned Discovery   (lessons_discovery.py)
    Phase 3: Design Documentation        (design_documentation.py)
    Phase 4: Test Construction           (test_construction.py)
    Phase 5: Development                 (development.py)
    Phase 6: Final Assembly & Validation (final_assembly.py)
    Phase 7: Final Testing               (final_testing.py)
    Phase 8: Retrospective & Lessons     (retrospective.py)

Supporting modules:
    - runner.py:  PhaseRunner — draft→validate→gate loop with retry/OTel/budget
    - context.py: ContextAssembler — token-aware context building
"""
from __future__ import annotations

# Re-export the PhaseRunner (the real one with OTel, retry, budget)
from startd8.contractors.artisan_phases.runner import (
    PhaseRunner,
    PhaseType,
    PhaseStatus,
    PhaseOutput,
    PhaseConfig,
    PhaseResult,
    RunResult,
    RetryPolicy,
    Phase,
    BudgetExceededError,
    GateRejectionError,
    PhaseExecutionError,
    PhaseRunnerError,
)

# Re-export context assembler
from startd8.contractors.artisan_phases.context import (
    ContextAssembler,
    ContextComponent,
    ContextResult,
    ContextBudget,
    ContextPriority,
)

# Re-export pre-flight checker
from startd8.contractors.artisan_phases.preflight import (
    PreFlightChecker,
    PreFlightConfig,
    PreFlightReport,
    CheckResult,
    CheckStatus,
    CheckCategory,
)

__all__ = [
    # Runner
    "PhaseRunner",
    "PhaseType",
    "PhaseStatus",
    "PhaseOutput",
    "PhaseConfig",
    "PhaseResult",
    "RunResult",
    "RetryPolicy",
    "Phase",
    "BudgetExceededError",
    "GateRejectionError",
    "PhaseExecutionError",
    "PhaseRunnerError",
    # Context
    "ContextAssembler",
    "ContextComponent",
    "ContextResult",
    "ContextBudget",
    "ContextPriority",
    # PreFlight
    "PreFlightChecker",
    "PreFlightConfig",
    "PreFlightReport",
    "CheckResult",
    "CheckStatus",
    "CheckCategory",
]
