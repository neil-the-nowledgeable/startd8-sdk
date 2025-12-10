"""
Storage backends for Agent Framework data
"""

import json
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional, List

from ..models import Prompt, AgentResponse, Benchmark
from ..utils.file_operations import atomic_write_json, FileLock
from ..logging_config import get_logger
from ..exceptions import FileOperationError, StorageError
try:
    from .base import BaseStorageOperations
except ImportError:
    BaseStorageOperations = None

logger = get_logger(__name__)


class StorageBackend(ABC):
    """Abstract base class for storage backends"""
    
    @abstractmethod
    def save_prompt(self, prompt: Prompt) -> None:
        """Save a prompt"""
        pass
    
    @abstractmethod
    def load_prompt(self, prompt_id: str) -> Optional[Prompt]:
        """Load a prompt by ID"""
        pass
    
    @abstractmethod
    def list_prompts(self) -> List[Prompt]:
        """List all prompts"""
        pass
    
    @abstractmethod
    def save_response(self, response: AgentResponse) -> None:
        """Save an agent response"""
        pass
    
    @abstractmethod
    def load_response(self, response_id: str) -> Optional[AgentResponse]:
        """Load a response by ID"""
        pass
    
    @abstractmethod
    def list_responses(self) -> List[AgentResponse]:
        """List all responses"""
        pass
    
    @abstractmethod
    def save_benchmark(self, benchmark: Benchmark) -> None:
        """Save a benchmark"""
        pass
    
    @abstractmethod
    def load_benchmark(self, benchmark_id: str) -> Optional[Benchmark]:
        """Load a benchmark by ID"""
        pass
    
    @abstractmethod
    def list_benchmarks(self) -> List[Benchmark]:
        """List all benchmarks"""
        pass


class FileSystemStorage(StorageBackend):
    """File system storage backend using JSON files"""
    
    def __init__(self, base_dir: Path):
        """
        Initialize file system storage
        
        Args:
            base_dir: Base directory for storage
        """
        self.base_dir = Path(base_dir)
        self.prompts_dir = self.base_dir / "prompts"
        self.responses_dir = self.base_dir / "responses"
        self.benchmarks_dir = self.base_dir / "benchmarks"
        
        # Create directories
        for dir_path in [self.prompts_dir, self.responses_dir, self.benchmarks_dir]:
            dir_path.mkdir(parents=True, exist_ok=True)
        
        # Use base storage operations for common patterns
        self._prompt_storage = BaseStorageOperations(base_dir, Prompt, "prompts")
        self._response_storage = BaseStorageOperations(base_dir, AgentResponse, "responses")
        self._benchmark_storage = BaseStorageOperations(base_dir, Benchmark, "benchmarks")
    
    def save_prompt(self, prompt: Prompt) -> None:
        """Save a prompt using base storage operations"""
        if self._prompt_storage:
            self._prompt_storage.save(prompt)
        else:
            # Fallback to original implementation
            file_path = self.prompts_dir / f"{prompt.id}.json"
            lock_file = self.prompts_dir / f".{prompt.id}.lock"
            with FileLock(lock_file):
                atomic_write_json(file_path, prompt.model_dump(), indent=2, default=str)
            logger.debug(f"Saved prompt {prompt.id}", extra={"prompt_id": prompt.id})
    
    def load_prompt(self, prompt_id: str) -> Optional[Prompt]:
        """Load a prompt using base storage operations"""
        if self._prompt_storage:
            return self._prompt_storage.load(prompt_id)
        else:
            # Fallback to original implementation
            file_path = self.prompts_dir / f"{prompt_id}.json"
            if not file_path.exists():
                return None
            with open(file_path, 'r') as f:
                data = json.load(f)
                return Prompt(**data)
    
    def list_prompts(self) -> List[Prompt]:
        """
        List all prompts using base storage operations
        
        Returns:
            List of Prompt objects, sorted by timestamp (newest first)
        """
        if self._prompt_storage:
            return self._prompt_storage.list_all(sort_key="timestamp", reverse=True)
        else:
            # Fallback to original implementation
            prompts = []
            for file_path in self.prompts_dir.glob("*.json"):
                if file_path.name.startswith('.'):
                    continue
                try:
                    with open(file_path, 'r') as f:
                        data = json.load(f)
                        prompts.append(Prompt(**data))
                except Exception:
                    continue
            return sorted(prompts, key=lambda p: p.timestamp, reverse=True)
    
    def list_prompts_generator(self):
        """
        Generator that yields prompts one at a time (memory efficient)
        
        Yields:
            Prompt objects as they are loaded
        """
        for file_path in self.prompts_dir.glob("*.json"):
            if file_path.name.startswith('.'):
                continue
            try:
                with open(file_path, 'r') as f:
                    data = json.load(f)
                    yield Prompt(**data)
            except Exception:
                continue
    
    def save_response(self, response: AgentResponse) -> None:
        """Save a response using base storage operations"""
        self._response_storage.save(response)
    
    def load_response(self, response_id: str) -> Optional[AgentResponse]:
        """Load a response using base storage operations"""
        return self._response_storage.load(response_id)
    
    def list_responses(self) -> List[AgentResponse]:
        """List all responses using base storage operations"""
        return self._response_storage.list_all(sort_key="timestamp", reverse=True)
    
    def save_benchmark(self, benchmark: Benchmark) -> None:
        """Save a benchmark using base storage operations"""
        self._benchmark_storage.save(benchmark)
    
    def load_benchmark(self, benchmark_id: str) -> Optional[Benchmark]:
        """Load a benchmark using base storage operations"""
        return self._benchmark_storage.load(benchmark_id)
    
    def list_benchmarks(self) -> List[Benchmark]:
        """List all benchmarks using base storage operations"""
        return self._benchmark_storage.list_all(sort_key="created_at", reverse=True)




