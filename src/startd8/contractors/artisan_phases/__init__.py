from __future__ import annotations
import copy
import enum
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

class PhaseStatus(enum.Enum):
    """Enumeration of phase execution states."""
    PENDING = 'pending'
    RUNNING = 'running'
    COMPLETED = 'completed'
    FAILED = 'failed'
    SKIPPED = 'skipped'

@dataclass
class PhaseResult:
    """Encapsulates the outcome of a phase execution."""
    phase_name: str
    'Name of the phase that was executed.'
    status: PhaseStatus
    'Final status of the phase (COMPLETED, FAILED, SKIPPED, etc.).'
    message: str = ''
    'Human-readable summary of the phase outcome.'
    artifacts: Dict[str, Any] = field(default_factory=dict)
    'Dictionary of artifacts produced by the phase.'
    errors: List[str] = field(default_factory=list)
    'List of error messages, if any occurred during execution.'

class ContextBuilder:
    """
    Manages shared context/state passed between phases.

    Wraps a dictionary with convenience methods for setting, getting,
    merging, and snapshotting context data.  Supports method chaining on
    mutating operations.
    """

    def __init__(self, initial_context: Optional[Dict[str, Any]]=None) -> None:
        """
        Initialize the context builder.

        Args:
            initial_context: Optional seed data for the context.
        """
        self._context: Dict[str, Any] = dict(initial_context) if initial_context else {}

    def set(self, key: str, value: Any) -> ContextBuilder:
        """
        Set a key-value pair in the context.

        Args:
            key: The context key.
            value: The value to store.

        Returns:
            Self, for method chaining.
        """
        self._context[key] = value
        return self

    def merge(self, data: Dict[str, Any]) -> ContextBuilder:
        """
        Merge a dictionary into the context.

        Args:
            data: Dictionary to merge into the context.

        Returns:
            Self, for method chaining.
        """
        self._context.update(data)
        return self

    def get(self, key: str, default: Any=None) -> Any:
        """
        Retrieve a value from the context by key.

        Args:
            key: The context key.
            default: Default value if key is not found.

        Returns:
            The value associated with the key, or *default* if not found.
        """
        return self._context.get(key, default)

    def has(self, key: str) -> bool:
        """
        Check if a key exists in the context.

        Args:
            key: The context key to check.

        Returns:
            True if the key exists, False otherwise.
        """
        return key in self._context

    def snapshot(self) -> Dict[str, Any]:
        """
        Return a deep copy of the current context.

        Mutations to the returned dictionary will **not** affect the
        original context.

        Returns:
            A deep copy of the internal context dictionary.
        """
        return copy.deepcopy(self._context)

    def to_dict(self) -> Dict[str, Any]:
        """
        Return a shallow copy of the context dictionary.

        Returns:
            A shallow copy of the internal context.
        """
        return dict(self._context)

    def __repr__(self) -> str:
        return f'ContextBuilder({self._context!r})'

class BasePhase(ABC):
    """
    Abstract base class for all Drupal site-building phases.

    Subclasses **must** implement :meth:`execute`.  Optional hooks
    :meth:`validate` and :meth:`rollback` may be overridden as needed.
    """

    def __init__(self) -> None:
        self._status: PhaseStatus = PhaseStatus.PENDING
        self._logger: logging.Logger = logging.getLogger(self.__class__.__name__)

    @property
    def name(self) -> str:
        """Human-readable name of this phase (defaults to the class name)."""
        return self.__class__.__name__

    @property
    def status(self) -> PhaseStatus:
        """Current execution status of this phase."""
        return self._status

    @abstractmethod
    def execute(self, context: ContextBuilder) -> PhaseResult:
        """
        Execute the phase logic.

        Args:
            context: Shared :class:`ContextBuilder` instance.

        Returns:
            :class:`PhaseResult` detailing the outcome.
        """
        ...

    def validate(self, context: ContextBuilder) -> bool:
        """
        Validate preconditions before execution.

        Default implementation returns ``True``.  Override in subclasses to
        perform phase-specific validation.

        Args:
            context: Shared :class:`ContextBuilder` instance.

        Returns:
            ``True`` if validation passes, ``False`` otherwise.
        """
        return True

    def rollback(self, context: ContextBuilder) -> None:
        """
        Rollback actions taken by this phase.

        Called when execution fails.  Default implementation is a no-op.

        Args:
            context: Shared :class:`ContextBuilder` instance.
        """

    def skip(self, reason: str='') -> PhaseResult:
        """
        Mark this phase as skipped.

        Args:
            reason: Optional reason for skipping.

        Returns:
            :class:`PhaseResult` with ``SKIPPED`` status.
        """
        self._status = PhaseStatus.SKIPPED
        return PhaseResult(phase_name=self.name, status=PhaseStatus.SKIPPED, message=f'Phase skipped. {reason}'.strip())

    def __repr__(self) -> str:
        return f'{self.__class__.__name__}(status={self._status.value})'

class DiscoveryPhase(BasePhase):
    """Phase 1 — Analyse requirements and discover project parameters."""

    def execute(self, context: ContextBuilder) -> PhaseResult:
        self._status = PhaseStatus.RUNNING
        self._logger.info('Running DiscoveryPhase')
        self._status = PhaseStatus.COMPLETED
        return PhaseResult(phase_name=self.name, status=PhaseStatus.COMPLETED, message='Discovery phase completed successfully.')

class ScaffoldPhase(BasePhase):
    """Phase 2 — Scaffold the Drupal project structure."""

    def execute(self, context: ContextBuilder) -> PhaseResult:
        self._status = PhaseStatus.RUNNING
        self._logger.info('Running ScaffoldPhase')
        self._status = PhaseStatus.COMPLETED
        return PhaseResult(phase_name=self.name, status=PhaseStatus.COMPLETED, message='Scaffold phase completed successfully.')

class ConfigPhase(BasePhase):
    """Phase 3 — Generate and apply Drupal configuration."""

    def execute(self, context: ContextBuilder) -> PhaseResult:
        self._status = PhaseStatus.RUNNING
        self._logger.info('Running ConfigPhase')
        self._status = PhaseStatus.COMPLETED
        return PhaseResult(phase_name=self.name, status=PhaseStatus.COMPLETED, message='Config phase completed successfully.')

class ContentModelPhase(BasePhase):
    """Phase 4 — Define content types, fields, and entity relationships."""

    def execute(self, context: ContextBuilder) -> PhaseResult:
        self._status = PhaseStatus.RUNNING
        self._logger.info('Running ContentModelPhase')
        self._status = PhaseStatus.COMPLETED
        return PhaseResult(phase_name=self.name, status=PhaseStatus.COMPLETED, message='Content model phase completed successfully.')

class ModulePhase(BasePhase):
    """Phase 5 — Enable, configure, and generate custom modules."""

    def execute(self, context: ContextBuilder) -> PhaseResult:
        self._status = PhaseStatus.RUNNING
        self._logger.info('Running ModulePhase')
        self._status = PhaseStatus.COMPLETED
        return PhaseResult(phase_name=self.name, status=PhaseStatus.COMPLETED, message='Module phase completed successfully.')

class ThemePhase(BasePhase):
    """Phase 6 — Set up and configure the Drupal theme."""

    def execute(self, context: ContextBuilder) -> PhaseResult:
        self._status = PhaseStatus.RUNNING
        self._logger.info('Running ThemePhase')
        self._status = PhaseStatus.COMPLETED
        return PhaseResult(phase_name=self.name, status=PhaseStatus.COMPLETED, message='Theme phase completed successfully.')

class ContentPhase(BasePhase):
    """Phase 7 — Create initial / seed content."""

    def execute(self, context: ContextBuilder) -> PhaseResult:
        self._status = PhaseStatus.RUNNING
        self._logger.info('Running ContentPhase')
        self._status = PhaseStatus.COMPLETED
        return PhaseResult(phase_name=self.name, status=PhaseStatus.COMPLETED, message='Content phase completed successfully.')

class QAPhase(BasePhase):
    """Phase 8 — Run quality-assurance checks and validation."""

    def execute(self, context: ContextBuilder) -> PhaseResult:
        self._status = PhaseStatus.RUNNING
        self._logger.info('Running QAPhase')
        self._status = PhaseStatus.COMPLETED
        return PhaseResult(phase_name=self.name, status=PhaseStatus.COMPLETED, message='QA phase completed successfully.')

class DeployPhase(BasePhase):
    """Phase 9 — Package and deploy the site."""

    def execute(self, context: ContextBuilder) -> PhaseResult:
        self._status = PhaseStatus.RUNNING
        self._logger.info('Running DeployPhase')
        self._status = PhaseStatus.COMPLETED
        return PhaseResult(phase_name=self.name, status=PhaseStatus.COMPLETED, message='Deploy phase completed successfully.')

class PhaseRunner:
    """
    Orchestrates sequential execution of phases.

    Manages the full phase lifecycle — validation → execution → error
    handling → rollback — while maintaining execution results and a shared
    context.
    """

    def __init__(self, phases: Optional[List[BasePhase]]=None, context: Optional[ContextBuilder]=None, stop_on_failure: bool=True) -> None:
        """
        Initialize the phase runner.

        Args:
            phases: Optional ordered list of phases to run.
            context: Optional shared context (created automatically if omitted).
            stop_on_failure: If ``True``, halt on the first failed phase.
        """
        self._phases: List[BasePhase] = phases if phases is not None else []
        self._context: ContextBuilder = context if context is not None else ContextBuilder()
        self._stop_on_failure: bool = stop_on_failure
        self._results: List[PhaseResult] = []
        self._logger: logging.Logger = logging.getLogger(self.__class__.__name__)

    def add_phase(self, phase: BasePhase) -> PhaseRunner:
        """
        Append a phase to the execution list.

        Args:
            phase: The phase to add.

        Returns:
            Self, for method chaining.
        """
        self._phases.append(phase)
        return self

    def run(self) -> List[PhaseResult]:
        """
        Execute all registered phases in order.

        Returns:
            List of :class:`PhaseResult` — one per phase attempted.
        """
        self._results = []
        for phase in self._phases:
            result = self.run_phase(phase)
            self._results.append(result)
            if result.status == PhaseStatus.FAILED and self._stop_on_failure:
                self._logger.warning('Phase %s failed. Stopping execution.', phase.name)
                break
        return self._results

    def run_phase(self, phase: BasePhase) -> PhaseResult:
        """
        Execute a single phase with validation, execution, and error handling.

        Args:
            phase: The phase to execute.

        Returns:
            :class:`PhaseResult` detailing the outcome.
        """
        try:
            if not phase.validate(self._context):
                self._logger.info('Phase %s validation failed. Skipping.', phase.name)
                return phase.skip('Validation failed.')
            self._logger.info('Executing phase: %s', phase.name)
            result = phase.execute(self._context)
            self._logger.info('Phase %s finished with status: %s', phase.name, result.status.value)
            return result
        except Exception as exc:
            error_message = f'Exception in {phase.name}: {exc}'
            self._logger.error(error_message, exc_info=True)
            try:
                self._logger.info('Rolling back phase: %s', phase.name)
                phase.rollback(self._context)
            except Exception as rollback_exc:
                self._logger.error('Rollback of %s failed: %s', phase.name, rollback_exc, exc_info=True)
            return PhaseResult(phase_name=phase.name, status=PhaseStatus.FAILED, message='Phase execution failed.', errors=[error_message])

    @property
    def results(self) -> List[PhaseResult]:
        """Results from the most recent :meth:`run` invocation."""
        return self._results

    @property
    def context(self) -> ContextBuilder:
        """Shared :class:`ContextBuilder` used across all phases."""
        return self._context

    def __repr__(self) -> str:
        return f'PhaseRunner(phases={len(self._phases)}, results={len(self._results)}, stop_on_failure={self._stop_on_failure})'

__all__: List[str] = [
    'PhaseStatus', 'PhaseResult', 'BasePhase', 'ContextBuilder',
    'PhaseRunner', 'DiscoveryPhase', 'ScaffoldPhase', 'ConfigPhase',
    'ContentModelPhase', 'ModulePhase', 'ThemePhase', 'ContentPhase',
    'QAPhase', 'DeployPhase',
]