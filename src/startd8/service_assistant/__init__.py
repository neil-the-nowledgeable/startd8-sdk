"""Service Assistant — the project<->SDK bridge.

A one-shot, idempotent post-run component that detects completed cap-dev-pipe Prime
Contractor runs and their post-mortems on the filesystem, notifies the SDK (EventBus +
authoritative on-disk triage artifact), and produces a project-contextualized triage
report with recommended remediations — without executing them.

See ``docs/design/service-assistant/`` for requirements, plan, and the triage schema.
"""

from .assistant import ServiceAssistant, run_service_assistant
from .models import TriageReport
from .operational_actions import (
    CAUSE_TO_OPERATIONAL_ACTION,
    OperationalAction,
    resolve_operational_action,
)

__all__ = [
    "ServiceAssistant",
    "run_service_assistant",
    "TriageReport",
    "CAUSE_TO_OPERATIONAL_ACTION",
    "OperationalAction",
    "resolve_operational_action",
]
