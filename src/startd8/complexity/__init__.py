"""Shared complexity classification and routing.

Provides a unified 4-tier complexity classification system used by
Artisan, Prime Contractor, and Micro Prime subsystems.
"""

from .classifier import classify_tier, log_tier_distribution
from .models import ComplexityRoutingConfig, ComplexityTier, TaskComplexitySignals
from .router import ComplexityRouter
from .signals import detect_cross_file_edges, extract_signals_from_feature

__all__ = [
    "ComplexityTier",
    "TaskComplexitySignals",
    "ComplexityRoutingConfig",
    "classify_tier",
    "extract_signals_from_feature",
    "detect_cross_file_edges",
    "ComplexityRouter",
    "log_tier_distribution",
]
