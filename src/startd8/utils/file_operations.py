"""
File operation utilities with atomic writes and locking support
"""

import os
import tempfile
import shutil
from pathlib import Path
from typing import Optional
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
        
        raise FileOperationError(
            f"Failed to write file: {e}",
            file_path=str(file_path),
            original_error=e
        ) from e
    finally:
        # Clean up backup if write succeeded
        if backup_path and backup_path.exists():
            try:
                backup_path.unlink()
            except:
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
    
    try:
        json_str = json.dumps(data, **json_kwargs)
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
                    except:
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
                except:
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













