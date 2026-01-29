"""
Adapter implementations for Prime Contractor protocols.

This module provides both standalone and ContextCore-integrated adapters.
"""

from .standalone import (
    LoggingInstrumentor,
    HeuristicSizeEstimator,
    SimpleMergeStrategy,
)

__all__ = [
    "LoggingInstrumentor",
    "HeuristicSizeEstimator",
    "SimpleMergeStrategy",
]

# Conditional imports for ContextCore adapters
try:
    from .contextcore import (
        ContextCoreInstrumentor,
        ASTMergeStrategy,
    )
    __all__.extend([
        "ContextCoreInstrumentor",
        "ASTMergeStrategy",
    ])
    CONTEXTCORE_AVAILABLE = True
except ImportError:
    CONTEXTCORE_AVAILABLE = False
