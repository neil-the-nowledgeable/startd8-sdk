"""
Safe auto-fix operations for diagnostic issues.

The AutoFixer applies safe, reversible fixes for common diagnostic failures.
Only non-destructive operations are included.
"""

import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional

from .models import DiagnosticReport, HealthCheck, HealthStatus


# Registry of safe fix functions
_SAFE_FIXES: Dict[str, Callable[[], str]] = {}


def register_fix(fix_hint: str) -> Callable:
    """
    Decorator to register a safe fix function.

    Args:
        fix_hint: The fix_hint string that triggers this fix

    Returns:
        Decorator function
    """
    def decorator(func: Callable[[], str]) -> Callable[[], str]:
        _SAFE_FIXES[fix_hint] = func
        return func
    return decorator


def _get_startd8_data_dir() -> Path:
    """Get the startd8 data directory."""
    return Path.home() / ".startd8"


def _get_startd8_log_dir() -> Path:
    """Get the startd8 logs directory."""
    return _get_startd8_data_dir() / "logs"


@register_fix("create_data_directory")
def create_data_directory() -> str:
    """Create the startd8 data directory if it doesn't exist."""
    data_dir = _get_startd8_data_dir()
    if data_dir.exists():
        return f"Data directory already exists: {data_dir}"

    try:
        data_dir.mkdir(parents=True, exist_ok=True)
        return f"Created data directory: {data_dir}"
    except Exception as e:
        return f"Failed to create data directory: {e}"


@register_fix("create_log_directory")
def create_log_directory() -> str:
    """Create the startd8 logs directory if it doesn't exist."""
    log_dir = _get_startd8_log_dir()
    if log_dir.exists():
        return f"Log directory already exists: {log_dir}"

    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        return f"Created log directory: {log_dir}"
    except Exception as e:
        return f"Failed to create log directory: {e}"


@register_fix("rotate_logs")
def rotate_logs() -> str:
    """Archive old log files to reduce disk usage."""
    log_dir = _get_startd8_log_dir()
    if not log_dir.exists():
        return "Log directory does not exist"

    archive_dir = log_dir / "archive"
    archive_dir.mkdir(exist_ok=True)

    rotated = []
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    for log_file in log_dir.glob("*.log"):
        # Skip if already small
        if log_file.stat().st_size < 10 * 1024 * 1024:  # 10 MB
            continue

        try:
            archive_name = f"{log_file.stem}_{timestamp}{log_file.suffix}"
            shutil.move(str(log_file), str(archive_dir / archive_name))
            rotated.append(log_file.name)
        except Exception as e:
            return f"Failed to rotate {log_file.name}: {e}"

    if rotated:
        return f"Rotated {len(rotated)} log files to archive"
    else:
        return "No log files needed rotation"


@register_fix("clear_cache")
def clear_cache() -> str:
    """Clear the cache directory to free up disk space."""
    cache_dir = _get_startd8_data_dir() / "cache"
    if not cache_dir.exists():
        return "Cache directory does not exist"

    try:
        # Move to trash first (safe delete)
        trash_dir = _get_startd8_data_dir() / ".trash"
        trash_dir.mkdir(exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = f"cache_backup_{timestamp}"

        shutil.move(str(cache_dir), str(trash_dir / backup_name))

        # Recreate empty cache dir
        cache_dir.mkdir(exist_ok=True)

        return f"Cleared cache (backup saved to .trash/{backup_name})"
    except Exception as e:
        return f"Failed to clear cache: {e}"


@register_fix("update_pricing_cache")
def update_pricing_cache() -> str:
    """Refresh the pricing cache from the pricing service."""
    try:
        from startd8.costs import PricingService

        pricing = PricingService()
        # Force refresh by clearing and reloading
        if hasattr(pricing, "_cache"):
            pricing._cache.clear()

        return "Pricing cache refreshed"
    except ImportError:
        return "PricingService not available"
    except Exception as e:
        return f"Failed to refresh pricing cache: {e}"


@register_fix("rebuild_cost_db")
def rebuild_cost_db() -> str:
    """
    Attempt to rebuild/repair the cost database.

    This creates a backup and attempts VACUUM to recover.
    """
    db_path = _get_startd8_data_dir() / "costs.db"
    if not db_path.exists():
        return "Cost database does not exist"

    try:
        import sqlite3

        # Create backup first
        backup_dir = _get_startd8_data_dir() / "backups"
        backup_dir.mkdir(exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = backup_dir / f"costs_backup_{timestamp}.db"

        shutil.copy2(str(db_path), str(backup_path))

        # Try VACUUM to rebuild
        conn = sqlite3.connect(str(db_path))
        conn.execute("VACUUM")
        conn.close()

        return f"Database rebuilt (backup at {backup_path.name})"
    except Exception as e:
        return f"Failed to rebuild database: {e}"


@register_fix("set_anthropic_api_key")
def set_anthropic_api_key() -> str:
    """
    Provide instructions for setting the Anthropic API key.

    This doesn't actually set the key (that would be unsafe) but returns
    instructions for the user.
    """
    return (
        "To set ANTHROPIC_API_KEY:\n"
        "1. Get your API key from https://console.anthropic.com/\n"
        "2. Add to your shell config (~/.zshrc or ~/.bashrc):\n"
        "   export ANTHROPIC_API_KEY='sk-ant-...'\n"
        "3. Restart your terminal or run: source ~/.zshrc"
    )


class AutoFixer:
    """
    Applies safe auto-fixes based on diagnostic results.

    Only non-destructive, reversible operations are supported.
    All fixes create backups before making changes.

    Example:
        fixer = AutoFixer()
        results = fixer.apply_all(report)
        for action, result in results:
            print(f"{action}: {result}")
    """

    def __init__(self):
        """Initialize the auto-fixer."""
        self.applied_fixes: List[str] = []

    def get_available_fixes(self, report: DiagnosticReport) -> List[str]:
        """
        Get list of fixes that can be applied for this report.

        Args:
            report: Diagnostic report with failures

        Returns:
            List of fix hint strings that can be applied
        """
        available = []
        for check in report.get_fixable():
            if check.fix_hint in _SAFE_FIXES:
                available.append(check.fix_hint)
        return list(set(available))  # Dedupe

    def can_auto_fix(self, fix_hint: str) -> bool:
        """
        Check if a fix hint has an auto-fix function.

        Args:
            fix_hint: The fix hint string

        Returns:
            True if an auto-fix is available
        """
        return fix_hint in _SAFE_FIXES

    def apply_fix(self, fix_hint: str) -> str:
        """
        Apply a specific fix by its hint.

        Args:
            fix_hint: The fix hint string

        Returns:
            Result message from the fix
        """
        if fix_hint not in _SAFE_FIXES:
            return f"No auto-fix available for: {fix_hint}"

        try:
            result = _SAFE_FIXES[fix_hint]()
            self.applied_fixes.append(fix_hint)
            return result
        except Exception as e:
            return f"Fix failed: {e}"

    def apply_all(self, report: DiagnosticReport) -> List[tuple]:
        """
        Apply all available fixes for the report.

        Args:
            report: Diagnostic report with failures

        Returns:
            List of (fix_hint, result) tuples
        """
        results = []
        fixes = self.get_available_fixes(report)

        for fix_hint in fixes:
            result = self.apply_fix(fix_hint)
            results.append((fix_hint, result))

        # Update report with applied fixes
        report.auto_fixes_applied = [f for f, _ in results]

        return results


def apply_safe_fixes(report: DiagnosticReport) -> List[tuple]:
    """
    Convenience function to apply all safe fixes for a report.

    Args:
        report: Diagnostic report with failures

    Returns:
        List of (fix_hint, result) tuples

    Example:
        report = run_diagnostics()
        if report.has_failures():
            results = apply_safe_fixes(report)
            for fix, result in results:
                print(f"Applied {fix}: {result}")
    """
    fixer = AutoFixer()
    return fixer.apply_all(report)
