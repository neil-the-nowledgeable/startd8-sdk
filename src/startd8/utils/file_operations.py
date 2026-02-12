"""
File operation utilities with atomic writes and locking support
"""

import os
import tempfile
import shutil
import re
from dataclasses import asdict, is_dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Optional, Union
import platform

from ..exceptions import FileOperationError


def atomic_write(
    file_path: Path,
    content: bytes,
    mode: str = 'wb',
    backup: bool = False
) -> None:
    """
    Atomically write content to a file.
    
    Writes to a temporary file first, then renames it to the target.
    This ensures the target file is never in a partially-written state.
    
    Args:
        file_path: Target file path
        content: Content to write (bytes or str)
        mode: Write mode ('wb' for bytes, 'w' for text)
        backup: Whether to create a backup of existing file
    
    Raises:
        FileOperationError: If write operation fails
    """
    file_path = Path(file_path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Convert content to bytes if needed
    if isinstance(content, str) and mode == 'wb':
        content = content.encode('utf-8')
    elif isinstance(content, bytes) and mode == 'w':
        mode = 'wb'
    
    # Create backup if requested and file exists
    backup_path = None
    if backup and file_path.exists():
        backup_path = file_path.with_suffix(file_path.suffix + '.bak')
        try:
            shutil.copy2(file_path, backup_path)
        except Exception as e:
            raise FileOperationError(
                f"Failed to create backup: {e}",
                file_path=str(file_path),
                original_error=e
            )
    
    # Write to temporary file in same directory (for atomic rename)
    temp_dir = file_path.parent
    try:
        # Create temporary file with same extension
        with tempfile.NamedTemporaryFile(
            mode=mode,
            dir=str(temp_dir),
            suffix=file_path.suffix,
            delete=False
        ) as temp_file:
            temp_path = Path(temp_file.name)
            temp_file.write(content)
            temp_file.flush()
            os.fsync(temp_file.fileno())  # Ensure data is written to disk
        
        # Atomic rename
        try:
            if platform.system() == 'Windows':
                # Windows doesn't support atomic rename if target exists
                # So we delete first (after backup)
                if file_path.exists():
                    file_path.unlink()
            temp_path.replace(file_path)
        except (OSError, PermissionError) as e:
            # Clean up temp file if rename fails
            try:
                temp_path.unlink()
            except (OSError, FileNotFoundError):
                pass  # Temp file may not exist or already deleted
            raise FileOperationError(
                f"Failed to atomically write file: {e}",
                file_path=str(file_path),
                original_error=e
            )
    
    except (OSError, PermissionError, IOError) as e:
        # Restore backup if write failed
        if backup_path and backup_path.exists():
            try:
                shutil.copy2(backup_path, file_path)
            except (OSError, PermissionError, shutil.Error):
                pass  # Best effort restore - already logged above
        raise FileOperationError(
            f"Failed to write file: {e}",
            file_path=str(file_path),
            original_error=e
        ) from e
    except Exception as e:
        # Catch-all for unexpected errors
        if backup_path and backup_path.exists():
            try:
                shutil.copy2(backup_path, file_path)
            except Exception:
                pass  # Best effort restore
        raise FileOperationError(
            f"Unexpected error writing file: {e}",
            file_path=str(file_path),
            original_error=e
        ) from e
    finally:
        # Clean up backup if write succeeded
        if backup_path and backup_path.exists():
            try:
                backup_path.unlink()
            except OSError:
                pass  # Best effort cleanup


def atomic_write_json(file_path: Path, data: dict, **json_kwargs) -> None:
    """
    Atomically write JSON data to a file.
    
    Args:
        file_path: Target file path
        data: Dictionary to serialize as JSON
        **json_kwargs: Additional arguments for json.dump
    
    Raises:
        FileOperationError: If write operation fails
    """
    import json

    user_default = json_kwargs.pop("default", None)

    def _default_serializer(value: Any) -> Any:
        """Best-effort serializer for non-JSON-native objects."""
        if user_default is not None:
            try:
                return user_default(value)
            except TypeError:
                # Fall through to SDK fallback behavior.
                pass

        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, Enum):
            return value.value
        if isinstance(value, Path):
            return str(value)
        if is_dataclass(value):
            return asdict(value)
        if hasattr(value, "model_dump") and callable(value.model_dump):
            return value.model_dump()
        if hasattr(value, "to_dict") and callable(value.to_dict):
            return value.to_dict()
        if isinstance(value, set):
            return list(value)
        if hasattr(value, "__dict__"):
            return vars(value)
        return str(value)
    
    try:
        json_str = json.dumps(data, default=_default_serializer, **json_kwargs)
        atomic_write(file_path, json_str, mode='w')
    except Exception as e:
        raise FileOperationError(
            f"Failed to write JSON file: {e}",
            file_path=str(file_path),
            original_error=e
        ) from e


class FileLock:
    """
    Simple file-based locking mechanism.
    
    Uses fcntl on Unix and msvcrt on Windows.
    """
    
    def __init__(self, lock_file: Path):
        """
        Initialize file lock.
        
        Args:
            lock_file: Path to lock file
        """
        self.lock_file = Path(lock_file)
        self.lock_fd = None
        self._is_locked = False
    
    def acquire(self, blocking: bool = True, timeout: Optional[float] = None) -> bool:
        """
        Acquire the lock.
        
        Args:
            blocking: If True, wait for lock; if False, return immediately
            timeout: Maximum time to wait (None = wait forever)
        
        Returns:
            True if lock acquired, False otherwise
        
        Raises:
            FileOperationError: If lock acquisition fails
        """
        import time
        
        if self._is_locked:
            return True
        
        self.lock_file.parent.mkdir(parents=True, exist_ok=True)
        
        start_time = time.time()
        while True:
            try:
                if platform.system() == 'Windows':
                    import msvcrt
                    self.lock_fd = open(self.lock_file, 'w')
                    try:
                        msvcrt.locking(self.lock_fd.fileno(), msvcrt.LK_NBLCK, 1)
                        self._is_locked = True
                        return True
                    except IOError:
                        self.lock_fd.close()
                        self.lock_fd = None
                        if not blocking:
                            return False
                else:
                    import fcntl
                    self.lock_fd = open(self.lock_file, 'w')
                    try:
                        fcntl.flock(self.lock_fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                        self._is_locked = True
                        return True
                    except (IOError, OSError):
                        self.lock_fd.close()
                        self.lock_fd = None
                        if not blocking:
                            return False
                
            except Exception as e:
                if self.lock_fd:
                    try:
                        self.lock_fd.close()
                    except OSError:
                        pass
                    self.lock_fd = None

                raise FileOperationError(
                    f"Failed to acquire lock: {e}",
                    file_path=str(self.lock_file),
                    original_error=e
                )
            
            # Check timeout
            if timeout and (time.time() - start_time) >= timeout:
                return False
            
            # Wait a bit before retrying
            if blocking:
                time.sleep(0.1)
    
    def release(self) -> None:
        """Release the lock."""
        if not self._is_locked:
            return
        
        try:
            if platform.system() == 'Windows':
                import msvcrt
                if self.lock_fd:
                    msvcrt.locking(self.lock_fd.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                if self.lock_fd:
                    fcntl.flock(self.lock_fd.fileno(), fcntl.LOCK_UN)
        except Exception:
            pass  # Best effort
        finally:
            if self.lock_fd:
                try:
                    self.lock_fd.close()
                except OSError:
                    pass
                self.lock_fd = None
            self._is_locked = False
    
    def __enter__(self):
        """Context manager entry."""
        self.acquire()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.release()
    
    def __del__(self):
        """Cleanup on deletion."""
        self.release()


def get_unique_file_path(file_path: Path) -> Path:
    """
    Get a unique file path by appending version suffix if file exists.
    
    Checks if the file exists, and if so, appends _v2, _v3, etc. until
    a unique filename is found. Handles files that already have version suffixes.
    
    Args:
        file_path: Desired file path
        
    Returns:
        Unique file path (may be same as input if file doesn't exist)
    
    Examples:
        If "document.md" exists, returns "document_v2.md"
        If "document_v2.md" exists, returns "document_v3.md"
        If "document_v2.md" and "document_v3.md" exist, returns "document_v4.md"
    """
    file_path = Path(file_path)
    
    # If file doesn't exist, return as-is
    if not file_path.exists():
        return file_path
    
    # Extract base name and extension
    stem = file_path.stem
    suffix = file_path.suffix
    parent = file_path.parent
    
    # Check if stem already has a version suffix (_vN)
    version_pattern = re.compile(r'^(.+)_v(\d+)$')
    match = version_pattern.match(stem)
    
    if match:
        # File already has version suffix
        base_name = match.group(1)
        current_version = int(match.group(2))
        next_version = current_version + 1
    else:
        # No version suffix, start from v2
        base_name = stem
        next_version = 2
    
    # Find next available version
    while True:
        new_stem = f"{base_name}_v{next_version}"
        new_path = parent / f"{new_stem}{suffix}"
        
        if not new_path.exists():
            return new_path
        
        next_version += 1


def save_file_with_versioning(
    file_path: Path,
    content: Union[str, bytes],
    encoding: str = 'utf-8',
    atomic: bool = True
) -> Path:
    """
    Save content to a file with automatic versioning to avoid overwriting.
    
    This is the centralized file saving function for all workflows.
    It ensures files are never overwritten by appending version suffixes.
    
    Args:
        file_path: Desired file path
        content: Content to write (str or bytes)
        encoding: Text encoding (only used for text mode)
        atomic: Whether to use atomic write (default: True)
        
    Returns:
        Path to the actual file that was saved (may have version suffix)
        
    Raises:
        FileOperationError: If write operation fails
        
    Examples:
        >>> save_file_with_versioning(Path("result.md"), "# Result")
        Path("result.md")  # If result.md doesn't exist
        
        >>> save_file_with_versioning(Path("result.md"), "# Result")
        Path("result_v2.md")  # If result.md exists
        
        >>> save_file_with_versioning(Path("result_v2.md"), "# Result")
        Path("result_v3.md")  # If result_v2.md exists
    """
    file_path = Path(file_path)
    
    # Get unique file path (with versioning if needed)
    unique_path = get_unique_file_path(file_path)
    
    # Ensure parent directory exists
    unique_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Convert content to bytes if needed
    if isinstance(content, str):
        content_bytes = content.encode(encoding)
        mode = 'wb'
    else:
        content_bytes = content
        mode = 'wb'
    
    # Use atomic write if requested, otherwise direct write
    if atomic:
        atomic_write(unique_path, content_bytes, mode=mode, backup=False)
    else:
        # Direct write (non-atomic)
        try:
            with open(unique_path, mode) as f:
                f.write(content_bytes)
                if mode == 'wb':
                    f.flush()
                    os.fsync(f.fileno())
        except (OSError, PermissionError, IOError) as e:
            raise FileOperationError(
                f"Failed to write file: {e}",
                file_path=str(unique_path),
                original_error=e
            ) from e
    
    return unique_path


def save_text_file_with_versioning(
    file_path: Path,
    content: str,
    encoding: str = 'utf-8',
    atomic: bool = True
) -> Path:
    """
    Convenience function to save text content with versioning.
    
    Args:
        file_path: Desired file path
        content: Text content to write
        encoding: Text encoding (default: utf-8)
        atomic: Whether to use atomic write (default: True)
        
    Returns:
        Path to the actual file that was saved
    """
    return save_file_with_versioning(file_path, content, encoding=encoding, atomic=atomic)













