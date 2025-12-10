"""
Base storage implementation with common patterns
"""

import json
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional, List, TypeVar, Generic, Type
from functools import wraps
from datetime import datetime, timezone

from ..models import Prompt, AgentResponse, Benchmark
from ..utils.file_operations import atomic_write_json, FileLock
from ..logging_config import get_logger
from ..exceptions import FileOperationError, StorageError

logger = get_logger(__name__)

T = TypeVar('T', Prompt, AgentResponse, Benchmark)


def handle_storage_errors(func):
    """Decorator to handle storage operation errors"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except FileOperationError as e:
            logger.error(f"File operation error in {func.__name__}: {e}", exc_info=True)
            raise StorageError(f"Storage operation failed: {e}", original_error=e) from e
        except Exception as e:
            logger.error(f"Unexpected error in {func.__name__}: {e}", exc_info=True)
            raise StorageError(f"Unexpected storage error: {e}", original_error=e) from e
    return wrapper


class BaseStorageOperations(Generic[T]):
    """Base class for common storage operations"""
    
    def __init__(
        self,
        storage_dir: Path,
        model_class: Type[T],
        subdirectory: str
    ):
        """
        Initialize base storage operations
        
        Args:
            storage_dir: Base storage directory
            model_class: Pydantic model class
            subdirectory: Subdirectory name for this type
        """
        self.storage_dir = Path(storage_dir)
        self.data_dir = self.storage_dir / subdirectory
        self.model_class = model_class
        self.data_dir.mkdir(parents=True, exist_ok=True)
    
    @handle_storage_errors
    def save(self, item: T) -> None:
        """Save an item"""
        file_path = self.data_dir / f"{item.id}.json"
        lock_file = self.data_dir / f".{item.id}.lock"
        
        with FileLock(lock_file):
            atomic_write_json(
                file_path,
                item.model_dump(),
                indent=2,
                default=str
            )
        logger.debug(f"Saved {self.model_class.__name__} {item.id}", extra={f"{self.model_class.__name__.lower()}_id": item.id})
    
    @handle_storage_errors
    def load(self, item_id: str) -> Optional[T]:
        """Load an item by ID"""
        file_path = self.data_dir / f"{item_id}.json"
        if not file_path.exists():
            logger.debug(f"{self.model_class.__name__} {item_id} not found", extra={f"{self.model_class.__name__.lower()}_id": item_id})
            return None
        
        try:
            with open(file_path, 'r') as f:
                data = json.load(f)
                return self.model_class(**data)
        except json.JSONDecodeError as e:
            logger.error(
                f"Failed to parse {self.model_class.__name__} {item_id}: {e}",
                exc_info=True,
                extra={f"{self.model_class.__name__.lower()}_id": item_id, "file_path": str(file_path)}
            )
            raise FileOperationError(
                f"Invalid JSON in {self.model_class.__name__.lower()} file: {e}",
                file_path=str(file_path),
                original_error=e
            ) from e
        except Exception as e:
            logger.error(
                f"Failed to load {self.model_class.__name__} {item_id}: {e}",
                exc_info=True,
                extra={f"{self.model_class.__name__.lower()}_id": item_id, "file_path": str(file_path)}
            )
            raise StorageError(f"Failed to load {self.model_class.__name__.lower()}: {e}", original_error=e) from e
    
    @handle_storage_errors
    def list_all(self, sort_key: str = "timestamp", reverse: bool = True) -> List[T]:
        """List all items"""
        from datetime import datetime, timezone
        
        items = []
        for file_path in self.data_dir.glob("*.json"):
            # Skip lock files
            if file_path.name.startswith('.'):
                continue
            
            try:
                with open(file_path, 'r') as f:
                    data = json.load(f)
                    items.append(self.model_class(**data))
            except (json.JSONDecodeError, Exception) as e:
                logger.warning(
                    f"Skipping invalid {self.model_class.__name__.lower()} file {file_path.name}: {e}",
                    extra={"file_path": str(file_path)}
                )
                continue
        
        # Sort by specified key with datetime normalization
        def get_sort_value(item):
            """Get sort value, normalizing datetimes to be timezone-aware"""
            value = getattr(item, sort_key, None)
            
            # Fallback to timestamp or created_at if sort_key not found
            if value is None:
                if hasattr(item, 'timestamp'):
                    value = item.timestamp
                elif hasattr(item, 'created_at'):
                    value = item.created_at
            
            # Normalize datetime objects to be timezone-aware
            if isinstance(value, datetime):
                if value.tzinfo is None:
                    # Naive datetime - assume UTC
                    value = value.replace(tzinfo=timezone.utc)
            
            return value
        
        try:
            return sorted(items, key=get_sort_value, reverse=reverse)
        except Exception as e:
            # If sorting still fails for any reason, log warning and return unsorted
            logger.warning(f"Failed to sort items by '{sort_key}': {e}. Returning unsorted list.", exc_info=True)
            return items






