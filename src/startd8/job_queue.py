"""
Job Queue for startd8 - File-based job processing system

Monitors a folder for job files (*_startd8_job.json) and processes them
sequentially through configured agents.
"""

import json
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List, Dict, Any, Callable
import threading

from .models import (
    JobStatus, JobFile, JobQueueConfig, JobResult, PromptSpec
)
from .framework import AgentFramework
from .agents import BaseAgent
from .providers import ProviderRegistry
from .logging_config import get_logger
from .utils.file_operations import atomic_write_json

logger = get_logger(__name__)

# Job file suffix pattern
JOB_FILE_SUFFIX = "_startd8_job.json"
STATUS_FILE_SUFFIX = "_startd8_job.status.json"


class JobQueueError(Exception):
    """Base exception for job queue errors"""
    pass


class JobValidationError(JobQueueError):
    """Raised when job file validation fails"""
    pass


class JobProcessingError(JobQueueError):
    """Raised when job processing fails"""
    pass


class AgentRegistry:
    """
    Registry for available agents - now uses ProviderRegistry
    
    This class maintains backward compatibility while leveraging the new
    provider plugin system.
    """
    
    def __init__(self):
        """Initialize agent registry"""
        self._custom_agents: Dict[str, BaseAgent] = {}
        # Trigger provider discovery on first use
        ProviderRegistry.discover()
    
    def register(self, name: str, agent: BaseAgent):
        """
        Register a pre-configured agent instance
        
        Args:
            name: Agent identifier
            agent: Agent instance to register
        """
        self._custom_agents[name.lower()] = agent
        logger.debug(f"Registered custom agent: {name}")
    
    def get_agent(self, name: str) -> Optional[BaseAgent]:
        """
        Get agent by name, checking custom agents then providers
        
        Args:
            name: Agent name, provider name, or model name
            
        Returns:
            Agent instance or None if not found
        
        Example:
            # Get custom agent
            agent = registry.get_agent("my-custom-agent")
            
            # Get agent by provider:model spec
            agent = registry.get_agent("openai:gpt-4-turbo-preview")
            
            # Get agent by provider name (uses default model)
            agent = registry.get_agent("anthropic")
        """
        if not name:
            return None
        
        raw = name.strip()
        if not raw:
            return None
        
        name_lower = raw.lower()
        
        # Check custom agents first
        if name_lower in self._custom_agents:
            logger.debug(f"Found custom agent: {name}")
            return self._custom_agents[name_lower]

        # Provider:model spec (preferred, unambiguous)
        if ":" in raw:
            provider_part, model_part = raw.split(":", 1)
            provider_name = provider_part.strip().lower()
            model = model_part.strip()
            if provider_name and model:
                provider = ProviderRegistry.get_provider(provider_name)
                if provider:
                    try:
                        provider.validate_config({})
                        logger.debug(
                            f"Creating agent from provider {provider.name} for model {model}"
                        )
                        return provider.create_agent(model)
                    except Exception as e:
                        logger.warning(
                            f"Failed to create agent for spec '{raw}': {e}"
                        )
        
        # Try to find a provider that supports this as a model
        provider = ProviderRegistry.find_provider_for_model(raw)
        if provider:
            try:
                logger.debug(f"Creating agent from provider {provider.name} for model {raw}")
                provider.validate_config({})
                return provider.create_agent(raw)
            except Exception as e:
                logger.warning(f"Failed to create agent for model {raw}: {e}")
        
        # Try provider name as fallback (e.g., "anthropic" -> provider's default model)
        provider = ProviderRegistry.get_provider(name_lower)
        if provider and provider.supported_models:
            try:
                default_model = provider.supported_models[0]
                logger.debug(
                    f"Creating agent from provider {name} with default model {default_model}"
                )
                provider.validate_config({})
                return provider.create_agent(default_model)
            except Exception as e:
                logger.warning(f"Failed to create default agent for provider {name}: {e}")
        
        logger.warning(f"No agent found for: {name}")
        return None

    def get_default_agent_spec(self) -> Optional[str]:
        """
        Select a default agent spec from ProviderRegistry.

        Preference order:
        - Providers that require env vars (user explicitly configured keys) first
        - Providers without 'testing' capability before those with it
        - Stable tiebreaker by provider name

        Returns:
            A 'provider:model' spec string, or None if no providers are usable.
        """
        ProviderRegistry.discover()

        candidates: List[tuple[tuple, Any]] = []
        for provider_name in ProviderRegistry.list_providers():
            provider = ProviderRegistry.get_provider(provider_name)
            if not provider:
                continue

            try:
                provider.validate_config({})
            except Exception:
                continue

            models = list(provider.supported_models or [])
            if not models:
                continue

            # Best-effort capability check (custom providers may not implement it).
            caps: List[str] = []
            try:
                if hasattr(provider, "get_capabilities"):
                    caps = list(provider.get_capabilities())  # type: ignore[attr-defined]
            except Exception:
                caps = []

            caps_lower = {c.lower() for c in caps}
            is_testing = "testing" in caps_lower
            requires_env = bool(provider.get_required_env_vars())

            priority = (0 if requires_env else 1, 1 if is_testing else 0, provider.name)
            candidates.append((priority, provider))

        for _, provider in sorted(candidates, key=lambda x: x[0]):
            for model in (provider.supported_models or []):
                try:
                    # Construct (do not execute) an agent to ensure optional deps exist.
                    provider.create_agent(model)
                    return f"{provider.name}:{model}"
                except Exception:
                    continue

        return None
    
    def list_available(self) -> List[str]:
        """
        List all available agent identifiers
        
        Returns:
            List of agent names (custom + providers + models)
        """
        available = list(self._custom_agents.keys())
        
        # Add provider names
        available.extend(ProviderRegistry.list_providers())
        
        # Add all model names
        all_models = ProviderRegistry.list_all_models()
        for models in all_models.values():
            available.extend(models)
        
        return sorted(set(available))
    
    def list_providers(self) -> List[str]:
        """List all registered providers"""
        return ProviderRegistry.list_providers()
    
    def list_models(self, provider: Optional[str] = None) -> Dict[str, List[str]]:
        """
        List models, optionally filtered by provider
        
        Args:
            provider: Optional provider name to filter by
            
        Returns:
            Dictionary mapping provider names to model lists
        """
        all_models = ProviderRegistry.list_all_models()
        
        if provider:
            provider_lower = provider.lower()
            return {provider_lower: all_models.get(provider_lower, [])}
        
        return all_models


class JobQueue:
    """
    File-based job queue manager
    
    Monitors a folder for job files and processes them sequentially.
    """
    
    def __init__(
        self,
        config: JobQueueConfig,
        framework: Optional[AgentFramework] = None,
        agent_registry: Optional[AgentRegistry] = None
    ):
        """
        Initialize job queue
        
        Args:
            config: Queue configuration
            framework: AgentFramework instance (creates one if not provided)
            agent_registry: Agent registry (creates default if not provided)
        """
        self.config = config
        self.framework = framework or AgentFramework()
        self.agent_registry = agent_registry or AgentRegistry()
        
        # Ensure watch folder exists
        self.config.watch_folder.mkdir(parents=True, exist_ok=True)
        
        # Ensure archive folder exists if archiving is enabled
        if self.config.archive_completed and self.config.archive_folder:
            self.config.archive_folder.mkdir(parents=True, exist_ok=True)
        
        # Processing state
        self._running = False
        self._processing_thread: Optional[threading.Thread] = None
        self._current_job: Optional[JobFile] = None
        
        # Callbacks
        self._on_job_start: Optional[Callable[[JobFile], None]] = None
        self._on_job_complete: Optional[Callable[[JobFile, JobResult], None]] = None
        self._on_job_error: Optional[Callable[[JobFile, Exception], None]] = None
    
    def set_callbacks(
        self,
        on_start: Optional[Callable[[JobFile], None]] = None,
        on_complete: Optional[Callable[[JobFile, JobResult], None]] = None,
        on_error: Optional[Callable[[JobFile, Exception], None]] = None
    ):
        """Set callback functions for job events"""
        self._on_job_start = on_start
        self._on_job_complete = on_complete
        self._on_job_error = on_error
    
    def scan_folder(self) -> List[Path]:
        """
        Scan watch folder for job files
        
        Returns:
            List of paths to job files (excluding those already processed)
        """
        job_files = []
        
        for path in self.config.watch_folder.glob(f"*{JOB_FILE_SUFFIX}"):
            # Skip if status file shows completed/processing
            status_path = self._get_status_path(path)
            if status_path.exists():
                try:
                    status = self._load_status(status_path)
                    if status.status in (JobStatus.COMPLETED, JobStatus.PROCESSING):
                        continue
                except Exception:
                    pass  # If status file is corrupt, treat as pending
            
            job_files.append(path)
        
        return sorted(job_files, key=lambda p: p.stat().st_mtime)
    
    def load_job(self, path: Path) -> JobFile:
        """
        Load and validate a job file
        
        Args:
            path: Path to job file
            
        Returns:
            Validated JobFile instance
            
        Raises:
            JobValidationError: If validation fails
        """
        try:
            with open(path, 'r') as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            raise JobValidationError(f"Invalid JSON in {path}: {e}")
        except IOError as e:
            raise JobValidationError(f"Cannot read {path}: {e}")
        
        # Generate job_id if not present
        if 'job_id' not in data:
            data['job_id'] = f"job-{uuid.uuid4().hex[:12]}"
        
        # Set file_path
        data['file_path'] = path
        
        # Parse created_at or set to file mtime
        if 'created_at' not in data:
            data['created_at'] = datetime.fromtimestamp(
                path.stat().st_mtime, tz=timezone.utc
            ).isoformat()
        
        try:
            job = JobFile(**data)
            return job
        except Exception as e:
            raise JobValidationError(f"Invalid job file {path}: {e}")
    
    def list_jobs(self, include_completed: bool = False) -> List[JobFile]:
        """
        List all jobs in the queue
        
        Args:
            include_completed: Whether to include completed jobs
            
        Returns:
            List of JobFile instances sorted by priority then created_at
        """
        jobs = []
        
        for path in self.config.watch_folder.glob(f"*{JOB_FILE_SUFFIX}"):
            try:
                job = self.load_job(path)
                
                # Check status file
                status_path = self._get_status_path(path)
                if status_path.exists():
                    status = self._load_status(status_path)
                    job.status = status.status
                    job.started_at = status.started_at
                    job.completed_at = status.completed_at
                    job.response_ids = status.response_ids
                    job.error = status.error
                
                if include_completed or job.status not in (JobStatus.COMPLETED, JobStatus.FAILED):
                    jobs.append(job)
            except Exception as e:
                logger.warning(f"Failed to load job {path}: {e}")
        
        # Sort by priority (descending) then created_at (ascending)
        jobs.sort(key=lambda j: (-j.priority, j.created_at))
        
        return jobs
    
    def get_pending_jobs(self) -> List[JobFile]:
        """Get only pending jobs"""
        return [j for j in self.list_jobs() if j.status == JobStatus.PENDING]
    
    def get_queue_status(self) -> Dict[str, Any]:
        """
        Get queue status summary
        
        Returns:
            Dictionary with status counts and current job info
        """
        jobs = self.list_jobs(include_completed=True)
        
        status_counts = {
            'pending': 0,
            'processing': 0,
            'completed': 0,
            'failed': 0
        }
        
        for job in jobs:
            status_counts[job.status.value] += 1
        
        return {
            'watch_folder': str(self.config.watch_folder),
            'total_jobs': len(jobs),
            'status_counts': status_counts,
            'current_job': self._current_job.job_id if self._current_job else None,
            'is_running': self._running
        }
    
    def process_job(self, job: JobFile) -> JobResult:
        """
        Process a single job
        
        Args:
            job: Job to process
            
        Returns:
            JobResult with processing outcome
        """
        logger.info(f"Processing job {job.job_id}")
        
        self._current_job = job
        result = JobResult(
            job_id=job.job_id,
            status=JobStatus.PROCESSING,
            started_at=datetime.now(timezone.utc)
        )
        
        # Write initial status
        self._save_status(job, result)
        
        # Notify callback
        if self._on_job_start:
            try:
                self._on_job_start(job)
            except Exception as e:
                logger.warning(f"on_job_start callback failed: {e}")
        
        try:
            # Create prompt from job spec
            prompt = self.framework.create_prompt(
                content=job.prompt.content,
                version=job.prompt.version,
                tags=job.prompt.tags,
                metadata={**job.prompt.metadata, 'job_id': job.job_id}
            )
            result.prompt_id = prompt.id
            
            # Determine which agents to use
            agent_names = job.agents if job.agents else self.config.default_agents
            if not agent_names:
                default_spec = self.agent_registry.get_default_agent_spec()
                if not default_spec:
                    raise JobProcessingError(
                        "No agents specified and no configured providers available. "
                        "Set JobQueueConfig.default_agents or specify job.agents."
                    )
                agent_names = [default_spec]
            
            # Run each agent
            for agent_name in agent_names:
                agent = self.agent_registry.get_agent(agent_name)
                if not agent:
                    logger.warning(f"Agent '{agent_name}' not available, skipping")
                    continue
                
                try:
                    # Generate response via (a)create_response() so cost/budget enforcement
                    # runs consistently and response_id can link to cost records.
                    agent_response = agent.create_response(
                        prompt_id=prompt.id,
                        prompt=job.prompt.content,
                        metadata={"job_id": job.job_id},
                        tags=job.prompt.tags,
                        job_id=job.job_id
                    )

                    # Record response (preserve agent-generated response_id)
                    response = self.framework.record_response(
                        prompt_id=prompt.id,
                        agent_name=agent.name,
                        model=agent.model,
                        response=agent_response.response,
                        response_time_ms=agent_response.response_time_ms,
                        token_usage=agent_response.token_usage,
                        metadata=agent_response.metadata,
                        response_id=agent_response.id,
                        timestamp=agent_response.timestamp,
                    )
                    
                    result.response_ids.append(response.id)
                    result.agents_run.append(agent_name)
                    logger.info(f"Agent {agent_name} completed for job {job.job_id}")
                    
                except Exception as e:
                    logger.error(f"Agent {agent_name} failed: {e}")
                    # Continue with other agents
            
            # Mark as completed
            result.status = JobStatus.COMPLETED
            result.completed_at = datetime.now(timezone.utc)
            
            # Notify callback
            if self._on_job_complete:
                try:
                    self._on_job_complete(job, result)
                except Exception as e:
                    logger.warning(f"on_job_complete callback failed: {e}")
            
        except Exception as e:
            logger.error(f"Job {job.job_id} failed: {e}")
            result.status = JobStatus.FAILED
            result.error = str(e)
            result.completed_at = datetime.now(timezone.utc)
            
            # Notify callback
            if self._on_job_error:
                try:
                    self._on_job_error(job, e)
                except Exception as ce:
                    logger.warning(f"on_job_error callback failed: {ce}")
        
        finally:
            # Save final status
            self._save_status(job, result)
            self._current_job = None
            
            # Archive if configured
            if self.config.archive_completed and result.status == JobStatus.COMPLETED:
                self._archive_job(job)
        
        return result
    
    def process_next(self) -> Optional[JobResult]:
        """
        Process the next pending job
        
        Returns:
            JobResult if a job was processed, None if queue is empty
        """
        pending = self.get_pending_jobs()
        if not pending:
            return None
        
        return self.process_job(pending[0])
    
    def process_all(
        self,
        on_progress: Optional[Callable[[int, int, JobFile, JobResult], None]] = None
    ) -> List[JobResult]:
        """
        Process all pending jobs sequentially
        
        Args:
            on_progress: Optional callback(current, total, job, result)
            
        Returns:
            List of JobResults
        """
        pending = self.get_pending_jobs()
        results = []
        total = len(pending)
        
        for i, job in enumerate(pending, 1):
            result = self.process_job(job)
            results.append(result)
            
            if on_progress:
                try:
                    on_progress(i, total, job, result)
                except Exception as e:
                    logger.warning(f"on_progress callback failed: {e}")
        
        return results
    
    def run_watch(self, stop_event: Optional[threading.Event] = None):
        """
        Run continuous watch loop
        
        Args:
            stop_event: Optional event to signal stop
        """
        self._running = True
        logger.info(f"Starting queue watch on {self.config.watch_folder}")
        
        while self._running:
            if stop_event and stop_event.is_set():
                break
            
            try:
                result = self.process_next()
                if result:
                    logger.info(f"Processed job {result.job_id}: {result.status.value}")
                else:
                    # No jobs, wait before next scan
                    time.sleep(self.config.poll_interval_seconds)
            except Exception as e:
                logger.error(f"Queue processing error: {e}")
                time.sleep(self.config.poll_interval_seconds)
        
        self._running = False
        logger.info("Queue watch stopped")
    
    def start_watch_async(self) -> threading.Thread:
        """
        Start watch loop in background thread
        
        Returns:
            Thread instance
        """
        if self._processing_thread and self._processing_thread.is_alive():
            raise JobQueueError("Queue watch already running")
        
        self._processing_thread = threading.Thread(
            target=self.run_watch,
            daemon=True,
            name="JobQueueWatch"
        )
        self._processing_thread.start()
        return self._processing_thread
    
    def stop_watch(self):
        """Stop the watch loop"""
        self._running = False
        if self._processing_thread:
            self._processing_thread.join(timeout=5.0)
    
    def clear_completed(self) -> int:
        """
        Remove status files for completed jobs
        
        Returns:
            Number of status files removed
        """
        count = 0
        for status_path in self.config.watch_folder.glob(f"*{STATUS_FILE_SUFFIX}"):
            try:
                status = self._load_status(status_path)
                if status.status in (JobStatus.COMPLETED, JobStatus.FAILED):
                    status_path.unlink()
                    count += 1
            except Exception as e:
                logger.warning(f"Failed to clear {status_path}: {e}")
        
        return count
    
    def _get_status_path(self, job_path: Path) -> Path:
        """Get status file path for a job file"""
        # Replace _startd8_job.json with _startd8_job.status.json
        name = job_path.name.replace(JOB_FILE_SUFFIX, STATUS_FILE_SUFFIX)
        return job_path.parent / name
    
    def _load_status(self, status_path: Path) -> JobResult:
        """Load status from file"""
        with open(status_path, 'r') as f:
            data = json.load(f)
        return JobResult(**data)
    
    def _save_status(self, job: JobFile, result: JobResult):
        """Save status to file (atomic write)"""
        if not job.file_path:
            return
        
        status_path = self._get_status_path(job.file_path)
        atomic_write_json(
            status_path,
            result.model_dump(mode='json'),
            indent=2,
            default=str
        )
    
    def _archive_job(self, job: JobFile):
        """Move completed job to archive folder"""
        if not self.config.archive_folder or not job.file_path:
            return
        
        try:
            # Move job file
            dest = self.config.archive_folder / job.file_path.name
            job.file_path.rename(dest)
            
            # Move status file
            status_path = self._get_status_path(job.file_path)
            if status_path.exists():
                status_dest = self.config.archive_folder / status_path.name
                status_path.rename(status_dest)
            
            logger.info(f"Archived job {job.job_id}")
        except Exception as e:
            logger.warning(f"Failed to archive job {job.job_id}: {e}")


def create_job_file(
    output_path: Path,
    content: str,
    version: str = "1.0.0",
    agents: Optional[List[str]] = None,
    priority: int = 0,
    tags: Optional[List[str]] = None,
    metadata: Optional[Dict[str, Any]] = None
) -> Path:
    """
    Helper function to create a job file
    
    Args:
        output_path: Path for the job file (will add suffix if needed)
        content: Prompt content
        version: Prompt version (default: 1.0.0)
        agents: List of agent names (default: all)
        priority: Job priority (default: 0)
        tags: Prompt tags
        metadata: Additional metadata
        
    Returns:
        Path to created job file
    """
    # Ensure proper suffix
    if not str(output_path).endswith(JOB_FILE_SUFFIX):
        output_path = output_path.parent / f"{output_path.stem}{JOB_FILE_SUFFIX}"
    
    job_data = {
        "prompt": {
            "content": content,
            "version": version,
            "tags": tags or [],
            "metadata": metadata or {}
        },
        "agents": agents or [],
        "priority": priority,
        "metadata": metadata or {}
    }
    
    # Use atomic write to prevent corruption
    atomic_write_json(output_path, job_data, indent=2)
    
    return output_path


def load_queue_config(config_path: Path) -> JobQueueConfig:
    """
    Load queue configuration from file
    
    Args:
        config_path: Path to config JSON file
        
    Returns:
        JobQueueConfig instance
    """
    with open(config_path, 'r') as f:
        data = json.load(f)
    
    # Convert path strings to Path objects
    if 'watch_folder' in data:
        data['watch_folder'] = Path(data['watch_folder'])
    if 'archive_folder' in data and data['archive_folder']:
        data['archive_folder'] = Path(data['archive_folder'])
    
    return JobQueueConfig(**data)


def save_queue_config(config: JobQueueConfig, config_path: Path):
    """
    Save queue configuration to file
    
    Args:
        config: JobQueueConfig instance
        config_path: Path to save config
    """
    data = config.model_dump(mode='json')
    
    # Convert Path objects to strings
    data['watch_folder'] = str(data['watch_folder'])
    if data.get('archive_folder'):
        data['archive_folder'] = str(data['archive_folder'])
    
    # Use atomic write to prevent corruption
    atomic_write_json(config_path, data, indent=2)





