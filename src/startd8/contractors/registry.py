"""
Registry for Prime Contractor plugins and adapters.

Provides automatic discovery of:
- CodeGenerator implementations
- Instrumentor implementations (standalone vs ContextCore)
- SizeEstimator implementations
- MergeStrategy implementations

Uses Python entry points for plugin discovery.
"""

from importlib.metadata import entry_points
from typing import Dict, List, Optional, Type

from ..logging_config import get_logger
from .protocols import (
    CodeGenerator,
    Instrumentor,
    MergeStrategy,
    SizeEstimator,
)
from .adapters import (
    HeuristicSizeEstimator,
    LoggingInstrumentor,
    SimpleMergeStrategy,
)


logger = get_logger("startd8.contractors.registry")


# Entry point group names
EP_CODE_GENERATORS = "startd8.contractors.code_generators"
EP_INSTRUMENTORS = "startd8.contractors.instrumentors"
EP_SIZE_ESTIMATORS = "startd8.contractors.size_estimators"
EP_MERGE_STRATEGIES = "startd8.contractors.merge_strategies"


class ContractorRegistry:
    """
    Registry for Prime Contractor components.

    Discovers and manages implementations of the contractor protocols.
    Falls back to standalone adapters when ContextCore is not available.

    Example:
        registry = ContractorRegistry()
        registry.discover()

        instrumentor = registry.get_instrumentor("contextcore")
        if not instrumentor:
            instrumentor = registry.get_default_instrumentor()
    """

    def __init__(self):
        """Initialize the registry."""
        self._code_generators: Dict[str, Type[CodeGenerator]] = {}
        self._instrumentors: Dict[str, Type[Instrumentor]] = {}
        self._size_estimators: Dict[str, Type[SizeEstimator]] = {}
        self._merge_strategies: Dict[str, Type[MergeStrategy]] = {}
        self._discovered = False

    def discover(self) -> None:
        """
        Discover all registered plugins via entry points.

        This scans Python package metadata for registered contractors
        implementations and adds them to the registry.
        """
        if self._discovered:
            return

        # Discover code generators
        self._discover_group(EP_CODE_GENERATORS, self._code_generators)

        # Discover instrumentors
        self._discover_group(EP_INSTRUMENTORS, self._instrumentors)

        # Discover size estimators
        self._discover_group(EP_SIZE_ESTIMATORS, self._size_estimators)

        # Discover merge strategies
        self._discover_group(EP_MERGE_STRATEGIES, self._merge_strategies)

        # Register built-in adapters
        self._register_builtins()

        self._discovered = True
        logger.debug(
            f"Discovered contractors: "
            f"{len(self._code_generators)} generators, "
            f"{len(self._instrumentors)} instrumentors, "
            f"{len(self._size_estimators)} estimators, "
            f"{len(self._merge_strategies)} strategies"
        )

    def _discover_group(
        self,
        group: str,
        registry: Dict[str, Type],
    ) -> None:
        """Discover entry points for a specific group."""
        try:
            eps = entry_points(group=group)
            for ep in eps:
                try:
                    cls = ep.load()
                    registry[ep.name] = cls
                    logger.debug(f"Registered {group}.{ep.name}")
                except Exception as e:
                    logger.warning(f"Failed to load {group}.{ep.name}: {e}")
        except Exception as e:
            logger.debug(f"No entry points for {group}: {e}")

    def _register_builtins(self) -> None:
        """Register built-in adapters."""
        # Standalone adapters (always available)
        self._instrumentors["logging"] = LoggingInstrumentor
        self._size_estimators["heuristic"] = HeuristicSizeEstimator
        self._merge_strategies["simple"] = SimpleMergeStrategy

        # ContextCore adapters (if available)
        try:
            from .adapters.contextcore import (
                ASTMergeStrategy,
                ContextCoreInstrumentor,
            )

            self._instrumentors["contextcore"] = ContextCoreInstrumentor
            self._merge_strategies["ast"] = ASTMergeStrategy
            logger.debug("ContextCore adapters registered")
        except ImportError:
            logger.debug("ContextCore adapters not available")

    # =========================================================================
    # Code Generators
    # =========================================================================

    def get_code_generator(self, name: str) -> Optional[Type[CodeGenerator]]:
        """Get a code generator by name."""
        self.discover()
        return self._code_generators.get(name)

    def list_code_generators(self) -> List[str]:
        """List available code generator names."""
        self.discover()
        return list(self._code_generators.keys())

    # =========================================================================
    # Instrumentors
    # =========================================================================

    def get_instrumentor(self, name: str) -> Optional[Type[Instrumentor]]:
        """Get an instrumentor by name."""
        self.discover()
        return self._instrumentors.get(name)

    def get_default_instrumentor(self) -> Type[Instrumentor]:
        """
        Get the default instrumentor.

        Returns ContextCoreInstrumentor if available, else LoggingInstrumentor.
        """
        self.discover()
        if "contextcore" in self._instrumentors:
            return self._instrumentors["contextcore"]
        return self._instrumentors["logging"]

    def list_instrumentors(self) -> List[str]:
        """List available instrumentor names."""
        self.discover()
        return list(self._instrumentors.keys())

    # =========================================================================
    # Size Estimators
    # =========================================================================

    def get_size_estimator(self, name: str) -> Optional[Type[SizeEstimator]]:
        """Get a size estimator by name."""
        self.discover()
        return self._size_estimators.get(name)

    def get_default_size_estimator(self) -> Type[SizeEstimator]:
        """Get the default size estimator."""
        self.discover()
        return self._size_estimators.get("heuristic", HeuristicSizeEstimator)

    def list_size_estimators(self) -> List[str]:
        """List available size estimator names."""
        self.discover()
        return list(self._size_estimators.keys())

    # =========================================================================
    # Merge Strategies
    # =========================================================================

    def get_merge_strategy(self, name: str) -> Optional[Type[MergeStrategy]]:
        """Get a merge strategy by name."""
        self.discover()
        return self._merge_strategies.get(name)

    def get_default_merge_strategy(self, for_python: bool = False) -> Type[MergeStrategy]:
        """
        Get the default merge strategy.

        Args:
            for_python: If True, prefer AST merge for Python files

        Returns:
            ASTMergeStrategy for Python (if available), else SimpleMergeStrategy
        """
        self.discover()
        if for_python and "ast" in self._merge_strategies:
            return self._merge_strategies["ast"]
        return self._merge_strategies.get("simple", SimpleMergeStrategy)

    def list_merge_strategies(self) -> List[str]:
        """List available merge strategy names."""
        self.discover()
        return list(self._merge_strategies.keys())


# Global registry instance
_registry: Optional[ContractorRegistry] = None


def get_registry() -> ContractorRegistry:
    """Get the global contractor registry."""
    global _registry
    if _registry is None:
        _registry = ContractorRegistry()
    return _registry


def discover() -> None:
    """Discover all available contractors."""
    get_registry().discover()
