"""
Storage health checks.

Checks disk space, file permissions, and data directory health.
"""

import os
import shutil
import time
from pathlib import Path
from ...paths import default_config_dir
from typing import Any, Dict, Optional

from ..models import CheckCategory, HealthCheck, HealthStatus
from . import register_check


def _get_startd8_data_dir() -> Path:
    """Get the startd8 data directory."""
    return default_config_dir()


def _get_startd8_log_dir() -> Path:
    """Get the startd8 logs directory."""
    return _get_startd8_data_dir() / "logs"


def _format_bytes(size_bytes: int) -> str:
    """Format bytes as human-readable string."""
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} PB"


@register_check(
    "disk_space",
    CheckCategory.STORAGE,
    description="Check available disk space on data directory",
)
def check_disk_space() -> HealthCheck:
    """Check available disk space on the data directory partition."""
    start = time.time()
    data_dir = _get_startd8_data_dir()

    # Use home directory if data dir doesn't exist
    check_path = data_dir if data_dir.exists() else Path.home()

    try:
        usage = shutil.disk_usage(check_path)
        free_gb = usage.free / (1024 ** 3)
        total_gb = usage.total / (1024 ** 3)
        used_percent = (usage.used / usage.total) * 100

        if free_gb < 1:
            status = HealthStatus.CRITICAL
            message = f"Low disk space: {_format_bytes(usage.free)} free"
        elif free_gb < 5:
            status = HealthStatus.WARNING
            message = f"Disk space getting low: {_format_bytes(usage.free)} free"
        else:
            status = HealthStatus.HEALTHY
            message = f"Disk space OK: {_format_bytes(usage.free)} free ({100-used_percent:.0f}%)"

        details = {
            "path": str(check_path),
            "free_bytes": usage.free,
            "total_bytes": usage.total,
            "used_percent": round(used_percent, 1),
        }

    except Exception as e:
        status = HealthStatus.UNKNOWN
        message = f"Failed to check disk space: {e}"
        details = {"error": str(e)}

    return HealthCheck(
        name="disk_space",
        category=CheckCategory.STORAGE,
        status=status,
        message=message,
        details=details,
        duration_ms=(time.time() - start) * 1000,
    )


@register_check(
    "data_dir_permissions",
    CheckCategory.STORAGE,
    description="Check read/write permissions on data directory",
)
def check_data_dir_permissions() -> HealthCheck:
    """Check read/write permissions on the startd8 data directory."""
    start = time.time()
    data_dir = _get_startd8_data_dir()

    if not data_dir.exists():
        # Try to create it
        try:
            data_dir.mkdir(parents=True, exist_ok=True)
            status = HealthStatus.HEALTHY
            message = "Data directory created successfully"
            details = {"path": str(data_dir), "created": True}
        except PermissionError:
            status = HealthStatus.CRITICAL
            message = f"Cannot create data directory: permission denied"
            details = {"path": str(data_dir)}
            return HealthCheck(
                name="data_dir_permissions",
                category=CheckCategory.STORAGE,
                status=status,
                message=message,
                details=details,
                duration_ms=(time.time() - start) * 1000,
                fix_hint="create_data_directory",
            )
        except Exception as e:
            status = HealthStatus.CRITICAL
            message = f"Cannot create data directory: {e}"
            details = {"path": str(data_dir), "error": str(e)}
            return HealthCheck(
                name="data_dir_permissions",
                category=CheckCategory.STORAGE,
                status=status,
                message=message,
                details=details,
                duration_ms=(time.time() - start) * 1000,
            )

    # Check read/write access
    can_read = os.access(data_dir, os.R_OK)
    can_write = os.access(data_dir, os.W_OK)

    if can_read and can_write:
        # Test actual write
        test_file = data_dir / ".write_test"
        try:
            test_file.write_text("test")
            test_file.unlink()
            status = HealthStatus.HEALTHY
            message = "Data directory permissions OK (read/write)"
        except Exception as e:
            status = HealthStatus.CRITICAL
            message = f"Cannot write to data directory: {e}"
    elif can_read:
        status = HealthStatus.CRITICAL
        message = "Data directory is read-only"
    else:
        status = HealthStatus.CRITICAL
        message = "No access to data directory"

    details = {
        "path": str(data_dir),
        "can_read": can_read,
        "can_write": can_write,
    }

    return HealthCheck(
        name="data_dir_permissions",
        category=CheckCategory.STORAGE,
        status=status,
        message=message,
        details=details,
        duration_ms=(time.time() - start) * 1000,
    )


@register_check(
    "log_dir_health",
    CheckCategory.STORAGE,
    description="Check logs directory exists and is writable",
)
def check_log_dir_health() -> HealthCheck:
    """Check if logs directory exists and is writable."""
    start = time.time()
    log_dir = _get_startd8_log_dir()

    if not log_dir.exists():
        # Log dir not existing is OK - it will be created when needed
        return HealthCheck(
            name="log_dir_health",
            category=CheckCategory.STORAGE,
            status=HealthStatus.HEALTHY,
            message="Log directory will be created when needed",
            details={"path": str(log_dir), "exists": False},
            duration_ms=(time.time() - start) * 1000,
        )

    # Check size of log files
    try:
        total_size = 0
        log_count = 0
        for log_file in log_dir.glob("*.log*"):
            total_size += log_file.stat().st_size
            log_count += 1

        # Warn if logs are getting large
        if total_size > 100 * 1024 * 1024:  # > 100 MB
            status = HealthStatus.WARNING
            message = f"Log files large: {_format_bytes(total_size)} in {log_count} files"
            fix_hint = "rotate_logs"
        else:
            status = HealthStatus.HEALTHY
            message = f"Log directory OK: {_format_bytes(total_size)} in {log_count} files"
            fix_hint = None

        details = {
            "path": str(log_dir),
            "total_size_bytes": total_size,
            "log_file_count": log_count,
        }

    except Exception as e:
        status = HealthStatus.UNKNOWN
        message = f"Failed to check log directory: {e}"
        details = {"path": str(log_dir), "error": str(e)}
        fix_hint = None

    return HealthCheck(
        name="log_dir_health",
        category=CheckCategory.STORAGE,
        status=status,
        message=message,
        details=details,
        duration_ms=(time.time() - start) * 1000,
        fix_hint=fix_hint,
    )


@register_check(
    "cache_dir_health",
    CheckCategory.STORAGE,
    description="Check cache directory health",
)
def check_cache_dir_health() -> HealthCheck:
    """Check cache directory health."""
    start = time.time()
    cache_dir = _get_startd8_data_dir() / "cache"

    if not cache_dir.exists():
        return HealthCheck(
            name="cache_dir_health",
            category=CheckCategory.STORAGE,
            status=HealthStatus.HEALTHY,
            message="Cache directory will be created when needed",
            details={"path": str(cache_dir), "exists": False},
            duration_ms=(time.time() - start) * 1000,
        )

    try:
        total_size = 0
        file_count = 0
        for f in cache_dir.rglob("*"):
            if f.is_file():
                total_size += f.stat().st_size
                file_count += 1

        # Warn if cache is getting large
        if total_size > 500 * 1024 * 1024:  # > 500 MB
            status = HealthStatus.WARNING
            message = f"Cache large: {_format_bytes(total_size)} in {file_count} files"
            fix_hint = "clear_cache"
        else:
            status = HealthStatus.HEALTHY
            message = f"Cache OK: {_format_bytes(total_size)} in {file_count} files"
            fix_hint = None

        details = {
            "path": str(cache_dir),
            "total_size_bytes": total_size,
            "file_count": file_count,
        }

    except Exception as e:
        status = HealthStatus.UNKNOWN
        message = f"Failed to check cache directory: {e}"
        details = {"path": str(cache_dir), "error": str(e)}
        fix_hint = None

    return HealthCheck(
        name="cache_dir_health",
        category=CheckCategory.STORAGE,
        status=status,
        message=message,
        details=details,
        duration_ms=(time.time() - start) * 1000,
        fix_hint=fix_hint,
    )
