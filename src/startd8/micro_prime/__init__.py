"""Micro Prime — Local-First Code Generation Engine.

Routes TRIVIAL and SIMPLE elements to a tuned Ollama model (``startd8-coder``)
instead of cloud models. Provides template-based generation for trivial
patterns, a 7-step repair pipeline, and verification-gated escalation.

Public API::

    from startd8.micro_prime import MicroPrimeEngine, MicroPrimeConfig

    engine = MicroPrimeEngine(config=MicroPrimeConfig())
    result = engine.process_element(element, file_spec, skeleton)
"""

from startd8.micro_prime.classifier import classify_element
from startd8.micro_prime.engine import MicroPrimeEngine
from startd8.micro_prime.context import MicroPrimeContext
from startd8.micro_prime.models import (
    ElementResult,
    EscalationReason,
    EscalationContext,
    EscalationResult,
    FileResult,
    MicroPrimeConfig,
    MicroPrimeCostReport,
    MicroPrimeElementMetrics,
    SeedResult,
    TierClassification,
)
from startd8.micro_prime.repair import run_repair_pipeline
from startd8.micro_prime.templates import TemplateRegistry

__all__ = [
    "MicroPrimeEngine",
    "MicroPrimeContext",
    "MicroPrimeConfig",
    "TierClassification",
    "ElementResult",
    "EscalationReason",
    "EscalationContext",
    "EscalationResult",
    "FileResult",
    "SeedResult",
    "MicroPrimeCostReport",
    "MicroPrimeElementMetrics",
    "TemplateRegistry",
    "classify_element",
    "run_repair_pipeline",
]
