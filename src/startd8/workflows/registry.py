"""
Workflow registry for managing and discovering workflows.

Provides a centralized registry for workflow discovery, registration,
and execution. Follows the same patterns as ProviderRegistry.
"""

from typing import Any, Dict, List, Optional, ClassVar
import logging
import sys
import threading

from .base import Workflow, ProgressCallback
from .models import WorkflowMetadata, WorkflowResult, ValidationResult
from ..exceptions import ConfigurationError

logger = logging.getLogger(__name__)


class WorkflowRegistry:
    """
    Central registry for workflows.

    Thread-safe singleton implementation supporting both programmatic
    registration and auto-discovery via Python entry points.

    Example entry_points configuration in pyproject.toml:

        [project.entry-points."startd8.workflows"]
        pipeline = "startd8.workflows.builtin.pipeline_workflow:PipelineWorkflow"
        doc-enhancement = "startd8.workflows.builtin.doc_enhancement:DocEnhancementWorkflow"

    Usage:
        # Auto-discover and register all workflows
        WorkflowRegistry.discover()

        # List available workflows
        workflows = WorkflowRegistry.list_workflows()

        # Get a specific workflow
        workflow = WorkflowRegistry.get_workflow("pipeline")

        # Run a workflow
        result = WorkflowRegistry.run_workflow(
            "pipeline",
            config={"initial_input": "...", "agents": ["anthropic:claude-sonnet-4-20250514"]}
        )
    """

    _instance: ClassVar[Optional['WorkflowRegistry']] = None
    _lock: ClassVar[threading.Lock] = threading.Lock()
    _workflows: Dict[str, Workflow] = {}
    _discovered: bool = False

    def __new__(cls):
        """Thread-safe singleton pattern using double-check locking."""
        if cls._instance is None:
            with cls._lock:
                # Double-check pattern to avoid race conditions
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    @classmethod
    def register(cls, workflow: Any) -> None:
        """
        Register a workflow instance.

        Args:
            workflow: Workflow instance implementing the Workflow protocol

        Raises:
            TypeError: If workflow doesn't implement required interface
            ValueError: If workflow_id is already registered

        Example:
            workflow = MyWorkflow()
            WorkflowRegistry.register(workflow)
        """
        # Use permissive duck-typing checks
        required_attrs = (
            "metadata",
            "validate_config",
            "run",
        )
        if not all(hasattr(workflow, attr) for attr in required_attrs):
            raise TypeError(
                f"{workflow} does not implement Workflow protocol. "
                f"Required: metadata, validate_config, run"
            )

        # Get workflow ID from metadata
        try:
            metadata = workflow.metadata
            workflow_id = metadata.workflow_id.lower()
        except (AttributeError, TypeError) as e:
            raise TypeError(
                f"Workflow metadata not accessible: {e}"
            ) from e

        # Thread-safe registration
        with cls._lock:
            if workflow_id in cls._workflows:
                logger.warning(f"Overwriting existing workflow: {workflow_id}")

            cls._workflows[workflow_id] = workflow
            logger.info(
                f"Registered workflow: {workflow_id} ({metadata.name}) "
                f"with capabilities: {metadata.capabilities}"
            )

    @classmethod
    def discover(cls, force: bool = False) -> None:
        """
        Auto-discover workflows via entry points (thread-safe).

        Workflows can be registered via setuptools entry points in pyproject.toml
        or setup.py. This method loads all registered workflows.

        Args:
            force: Re-discover even if already discovered

        Example entry_points in pyproject.toml:
            [project.entry-points."startd8.workflows"]
            pipeline = "startd8.workflows.builtin.pipeline_workflow:PipelineWorkflow"
        """
        # Thread-safe check
        with cls._lock:
            if cls._discovered and not force:
                logger.debug("Workflows already discovered, skipping")
                return

        discovered_count = 0

        # Try Python 3.10+ importlib.metadata
        try:
            if sys.version_info >= (3, 10):
                from importlib.metadata import entry_points

                try:
                    eps = entry_points(group='startd8.workflows')
                except TypeError:
                    # Fallback for older interface
                    eps = entry_points().get('startd8.workflows', [])
            else:
                # Python 3.9 fallback
                try:
                    from importlib_metadata import entry_points
                    eps = entry_points().get('startd8.workflows', [])
                except ImportError:
                    logger.warning(
                        "importlib_metadata not available. "
                        "Install with: pip install importlib-metadata"
                    )
                    eps = []

            for ep in eps:
                try:
                    logger.debug(f"Loading workflow from entry point: {ep.name}")
                    workflow_class = ep.load()
                    workflow = workflow_class()
                    cls.register(workflow)
                    discovered_count += 1
                except (ImportError, AttributeError, TypeError) as e:
                    logger.warning(
                        f"Failed to load workflow {ep.name}: {e}",
                        exc_info=True,
                        extra={
                            "entry_point": ep.name,
                            "error_type": type(e).__name__,
                            "operation": "load_workflow"
                        }
                    )
                except Exception as e:
                    logger.warning(
                        f"Unexpected error loading workflow {ep.name}: {e}",
                        exc_info=True,
                        extra={
                            "entry_point": ep.name,
                            "error_type": type(e).__name__,
                            "operation": "load_workflow"
                        }
                    )

        except (ImportError, AttributeError) as e:
            logger.debug(
                f"Entry point discovery failed: {e}",
                exc_info=True,
                extra={"operation": "discover_workflows", "error_type": type(e).__name__}
            )
        except Exception as e:
            logger.warning(
                f"Unexpected error during entry point discovery: {e}",
                exc_info=True,
                extra={"operation": "discover_workflows", "error_type": type(e).__name__}
            )

        # Also register built-in workflows
        cls._register_builtin_workflows()

        # Thread-safe update of discovery flag
        with cls._lock:
            cls._discovered = True
            workflow_count = len(cls._workflows)

        logger.info(
            f"Workflow discovery complete. "
            f"Discovered {discovered_count} external workflows, "
            f"total {workflow_count} workflows registered"
        )

    @classmethod
    def _register_builtin_workflows(cls) -> None:
        """Register built-in workflows that ship with the SDK."""
        try:
            from .builtin.pipeline_workflow import PipelineWorkflow
            cls.register(PipelineWorkflow())
            logger.debug("Registered built-in Pipeline workflow")
        except ImportError as e:
            logger.debug(f"Pipeline workflow not available: {e}")

        try:
            from .builtin.doc_enhancement_workflow import DocEnhancementWorkflow
            cls.register(DocEnhancementWorkflow())
            logger.debug("Registered built-in DocEnhancement workflow")
        except ImportError as e:
            logger.debug(f"DocEnhancement workflow not available: {e}")

        try:
            from .builtin.iterative_dev_workflow import IterativeDevWorkflowWrapper
            cls.register(IterativeDevWorkflowWrapper())
            logger.debug("Registered built-in IterativeDev workflow")
        except ImportError as e:
            logger.debug(f"IterativeDev workflow not available: {e}")

        # Document review workflows (previously built but not registered by default)
        try:
            from .builtin.critical_review_workflow import CriticalReviewWorkflow
            cls.register(CriticalReviewWorkflow())
            logger.debug("Registered built-in CriticalReview workflow")
        except ImportError as e:
            logger.debug(f"CriticalReview workflow not available: {e}")

        try:
            from .builtin.doc_review_log_workflow import DocReviewLogWorkflow
            cls.register(DocReviewLogWorkflow())
            logger.debug("Registered built-in DocReviewLog workflow")
        except ImportError as e:
            logger.debug(f"DocReviewLog workflow not available: {e}")

        try:
            from .builtin.architectural_review_log_workflow import (
                ArchitecturalReviewLogWorkflow,
            )
            cls.register(ArchitecturalReviewLogWorkflow())
            logger.debug("Registered built-in ArchitecturalReviewLog workflow")
        except ImportError as e:
            logger.debug(f"ArchitecturalReviewLog workflow not available: {e}")

        try:
            from .builtin.plan_ingestion_workflow import PlanIngestionWorkflow
            cls.register(PlanIngestionWorkflow())
            logger.debug("Registered built-in PlanIngestion workflow")
        except ImportError as e:
            logger.debug(f"PlanIngestion workflow not available: {e}")

    @classmethod
    def get_workflow(cls, workflow_id: str) -> Optional[Workflow]:
        """
        Get workflow by ID.

        Args:
            workflow_id: Workflow identifier (case-insensitive)

        Returns:
            Workflow instance or None if not found

        Example:
            workflow = WorkflowRegistry.get_workflow("pipeline")
            if workflow:
                result = workflow.run(config)
        """
        cls.discover()
        return cls._workflows.get(workflow_id.lower())

    @classmethod
    def list_workflows(cls) -> List[str]:
        """
        List all registered workflow IDs.

        Returns:
            List of workflow identifiers

        Example:
            workflows = WorkflowRegistry.list_workflows()
            # ['pipeline', 'doc-enhancement', 'iterative-dev']
        """
        cls.discover()
        with cls._lock:
            return list(cls._workflows.keys())

    @classmethod
    def list_workflow_metadata(cls) -> List[WorkflowMetadata]:
        """
        List metadata for all registered workflows.

        Returns:
            List of WorkflowMetadata objects

        Example:
            for meta in WorkflowRegistry.list_workflow_metadata():
                print(f"{meta.workflow_id}: {meta.description}")
        """
        cls.discover()
        with cls._lock:
            return [w.metadata for w in cls._workflows.values()]

    @classmethod
    def get_workflow_info(cls, workflow_id: str) -> Optional[Dict[str, Any]]:
        """
        Get detailed information about a workflow.

        Args:
            workflow_id: Workflow identifier

        Returns:
            Dictionary with workflow information or None

        Example:
            info = WorkflowRegistry.get_workflow_info("pipeline")
            # {
            #     'workflow_id': 'pipeline',
            #     'name': 'Pipeline Workflow',
            #     'description': '...',
            #     'input_schema': {...},
            #     ...
            # }
        """
        workflow = cls.get_workflow(workflow_id)
        if workflow is None:
            return None

        return workflow.metadata.to_dict()

    @classmethod
    def validate_config(
        cls,
        workflow_id: str,
        config: Dict[str, Any]
    ) -> ValidationResult:
        """
        Validate configuration for a workflow.

        Args:
            workflow_id: Workflow identifier
            config: Configuration to validate

        Returns:
            ValidationResult with valid=True or errors

        Raises:
            ConfigurationError: If workflow not found

        Example:
            result = WorkflowRegistry.validate_config(
                "pipeline",
                {"initial_input": "...", "agents": [...]}
            )
            if not result.valid:
                print(f"Errors: {result.errors}")
        """
        workflow = cls.get_workflow(workflow_id)
        if workflow is None:
            raise ConfigurationError(
                f"Unknown workflow: {workflow_id}. "
                f"Available: {', '.join(cls.list_workflows())}"
            )

        return workflow.validate_config(config)

    @classmethod
    def run_workflow(
        cls,
        workflow_id: str,
        config: Dict[str, Any],
        agents: Optional[List['BaseAgent']] = None,
        on_progress: Optional[ProgressCallback] = None,
        dry_run: bool = False,
    ) -> WorkflowResult:
        """
        Convenience method to run a workflow by ID.

        Args:
            workflow_id: Workflow identifier
            config: Workflow configuration
            agents: Optional pre-resolved agents
            on_progress: Optional progress callback
            dry_run: If True, simulate execution without API calls (FR-103)

        Returns:
            WorkflowResult

        Raises:
            ConfigurationError: If workflow not found or config invalid

        Example:
            result = WorkflowRegistry.run_workflow(
                "pipeline",
                config={"initial_input": "Write a function..."},
                agents=[claude_agent, gpt_agent]
            )
        """
        workflow = cls.get_workflow(workflow_id)
        if workflow is None:
            available = cls.list_workflows()
            raise ConfigurationError(
                f"Unknown workflow: {workflow_id}. "
                f"Available workflows: {', '.join(available)}"
            )

        try:
            return workflow.run(config, agents, on_progress, dry_run=dry_run)
        except Exception as e:
            logger.error(
                f"Workflow {workflow_id} failed: {e}",
                exc_info=True,
                extra={
                    "workflow_id": workflow_id,
                    "error_type": type(e).__name__,
                    "operation": "run_workflow"
                }
            )
            return WorkflowResult.from_error(workflow_id, str(e))

    @classmethod
    async def arun_workflow(
        cls,
        workflow_id: str,
        config: Dict[str, Any],
        agents: Optional[List['BaseAgent']] = None,
        on_progress: Optional[ProgressCallback] = None,
    ) -> WorkflowResult:
        """
        Async convenience method to run a workflow by ID.

        Args:
            workflow_id: Workflow identifier
            config: Workflow configuration
            agents: Optional pre-resolved agents
            on_progress: Optional progress callback

        Returns:
            WorkflowResult
        """
        workflow = cls.get_workflow(workflow_id)
        if workflow is None:
            available = cls.list_workflows()
            raise ConfigurationError(
                f"Unknown workflow: {workflow_id}. "
                f"Available workflows: {', '.join(available)}"
            )

        try:
            if hasattr(workflow, 'arun'):
                return await workflow.arun(config, agents, on_progress)
            else:
                # Fall back to sync execution
                return workflow.run(config, agents, on_progress)
        except Exception as e:
            logger.error(
                f"Workflow {workflow_id} failed: {e}",
                exc_info=True,
                extra={
                    "workflow_id": workflow_id,
                    "error_type": type(e).__name__,
                    "operation": "arun_workflow"
                }
            )
            return WorkflowResult.from_error(workflow_id, str(e))

    @classmethod
    def find_workflows_by_capability(cls, capability: str) -> List[Workflow]:
        """
        Find workflows that have a specific capability.

        Args:
            capability: Capability tag to search for

        Returns:
            List of workflows with that capability

        Example:
            doc_workflows = WorkflowRegistry.find_workflows_by_capability(
                "document-enhancement"
            )
        """
        cls.discover()
        capability_lower = capability.lower()

        with cls._lock:
            return [
                w for w in cls._workflows.values()
                if any(capability_lower == c.lower() for c in w.metadata.capabilities)
            ]

    @classmethod
    def find_workflows_by_tag(cls, tag: str) -> List[Workflow]:
        """
        Find workflows that have a specific tag.

        Args:
            tag: Tag to search for

        Returns:
            List of workflows with that tag
        """
        cls.discover()
        tag_lower = tag.lower()

        with cls._lock:
            return [
                w for w in cls._workflows.values()
                if tag_lower in [t.lower() for t in w.metadata.tags]
            ]

    @classmethod
    def search_workflows(cls, query: str) -> List[Workflow]:
        """
        Search workflows by name or description text (FR-201).

        Args:
            query: Substring to search for in workflow name or description

        Returns:
            List of workflows matching the query
        """
        cls.discover()
        query_lower = query.lower()

        with cls._lock:
            return [
                w for w in cls._workflows.values()
                if query_lower in w.metadata.name.lower()
                or query_lower in w.metadata.description.lower()
            ]

    @classmethod
    def clear(cls) -> None:
        """
        Clear all registered workflows (useful for testing).

        Example:
            WorkflowRegistry.clear()
            WorkflowRegistry.register(MyTestWorkflow())
        """
        with cls._lock:
            cls._workflows.clear()
            cls._discovered = False
            logger.debug("Cleared workflow registry")

    # --- Filesystem-based Discovery ---

    @classmethod
    def export_to_filesystem(cls, output_dir: Optional[str] = None) -> Dict[str, Any]:
        """
        Export all workflows to filesystem for agent discovery.

        Creates YAML files that agents can explore on-demand instead of
        loading all schemas upfront. Follows Anthropic's "progressive
        disclosure" pattern for token efficiency.

        Args:
            output_dir: Output directory (default: .startd8/workflows)

        Returns:
            Dict with 'files' (mapping workflow_id to path) and 'index' path

        Example:
            result = WorkflowRegistry.export_to_filesystem("./workflows")
            print(f"Index at: {result['index']}")
            print(f"Exported: {list(result['files'].keys())}")
        """
        from .filesystem import WorkflowFilesystem

        cls.discover()
        metadata_list = cls.list_workflow_metadata()

        fs = WorkflowFilesystem(output_dir)
        exported = fs.export_all(metadata_list)

        # Separate index from workflow files
        index_path = exported.pop('_index', None)
        return {
            'files': exported,
            'index': index_path,
            'directory': str(fs.base_dir),
        }

    @classmethod
    def discover_from_filesystem(
        cls,
        directory: Optional[str] = None,
        register: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        Discover workflows from filesystem (lightweight listing).

        Returns minimal workflow info from index file without loading
        full definitions. Use get_workflow_from_filesystem() to load
        full schema for specific workflow when needed.

        Args:
            directory: Directory containing workflow files
            register: If True, also register discovered workflows

        Returns:
            List of lightweight workflow summaries from index

        Example:
            # Agent discovers available workflows (minimal tokens)
            workflows = WorkflowRegistry.discover_from_filesystem()
            for wf in workflows:
                print(f"{wf['workflow_id']}: {wf['description']}")

            # Later, get full schema for specific workflow
            schema = WorkflowRegistry.get_workflow_from_filesystem("pipeline")
        """
        from .filesystem import WorkflowFilesystem

        fs = WorkflowFilesystem(directory)
        workflows = fs.list_workflows()

        if register:
            for entry in workflows:
                # Import full metadata and create placeholder
                metadata = fs.import_workflow(entry['workflow_id'])
                if metadata:
                    logger.info(f"Discovered workflow from filesystem: {entry['workflow_id']}")

        return workflows

    @classmethod
    def get_workflow_from_filesystem(
        cls,
        workflow_id: str,
        directory: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Get full workflow definition from filesystem.

        Loads complete schema for a specific workflow. Use this when
        agent needs full details after discovering via index.

        Args:
            workflow_id: The workflow to load
            directory: Directory containing workflow files

        Returns:
            Full workflow definition dict, or None if not found

        Example:
            # Agent needs full schema for pipeline workflow
            schema = WorkflowRegistry.get_workflow_from_filesystem("pipeline")
            if schema:
                print(f"Inputs: {schema['input_schema']}")
                print(f"Example: {schema['invocation']['example']}")
        """
        from .filesystem import WorkflowFilesystem

        fs = WorkflowFilesystem(directory)
        return fs.get_workflow_definition(workflow_id)
