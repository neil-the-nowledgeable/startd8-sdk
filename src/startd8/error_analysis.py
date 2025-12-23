"""
Error log analysis workflow

Analyzes the last error from log files and generates a prompt describing
the issue and suggested solution.
"""

import json
import re
from pathlib import Path
from typing import Optional, Dict, Any, Tuple
from datetime import datetime

from .paths import default_config_dir, default_data_dir
from .logging_config import get_logger

logger = get_logger(__name__)


def find_log_files(search_dirs: Optional[list[Path]] = None) -> list[Path]:
    """
    Find all log files in common locations.
    
    Args:
        search_dirs: Optional list of directories to search. If None, searches:
            - ~/.startd8/logs/
            - ./.startd8/logs/
            - Current directory for .log files
    
    Returns:
        List of log file paths, sorted by modification time (newest first)
    """
    if search_dirs is None:
        config_dir = default_config_dir()
        data_dir = default_data_dir()
        search_dirs = [
            config_dir / "logs",
            data_dir / "logs",
            Path.cwd(),
        ]
    
    log_files = []
    
    for search_dir in search_dirs:
        if not search_dir.exists():
            continue
        
        # Search for .log files
        if search_dir.is_dir():
            log_files.extend(search_dir.glob("*.log"))
            # Also check subdirectories
            log_files.extend(search_dir.rglob("*.log"))
        elif search_dir.is_file() and search_dir.suffix == ".log":
            log_files.append(search_dir)
    
    # Sort by modification time (newest first)
    log_files.sort(key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True)
    
    return log_files


def extract_last_error(log_file: Path) -> Optional[Dict[str, Any]]:
    """
    Extract the last error entry from a log file.
    
    Supports both JSON-formatted logs and plain text logs.
    
    Args:
        log_file: Path to log file
    
    Returns:
        Dictionary with error information, or None if no error found
    """
    if not log_file.exists():
        return None
    
    try:
        with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
        
        # Try to find last error in reverse order
        for line in reversed(lines):
            line = line.strip()
            if not line:
                continue
            
            # Try JSON format first
            try:
                log_entry = json.loads(line)
                level = log_entry.get('level', '').upper()
                if level in ('ERROR', 'CRITICAL', 'FATAL'):
                    # Extract exception details for better analysis
                    exception_info = log_entry.get('exception', '')
                    if not exception_info and log_entry.get('exception_type'):
                        exception_info = f"{log_entry.get('exception_type', '')}: {log_entry.get('exception_message', '')}"
                    
                    return {
                        'timestamp': log_entry.get('timestamp', ''),
                        'level': level,
                        'logger': log_entry.get('logger', ''),
                        'message': log_entry.get('message', ''),
                        'exception': exception_info,
                        'exception_type': log_entry.get('exception_type'),
                        'exception_message': log_entry.get('exception_message'),
                        'source': log_entry.get('source', {}),
                        'trace_id': log_entry.get('trace_id'),  # For Loki correlation
                        'correlation_id': log_entry.get('correlation_id'),
                        'file': str(log_file),
                        'format': 'json',
                        'raw_json_entry': line  # Store original JSON for full context
                    }
            except (json.JSONDecodeError, ValueError):
                pass
            
            # Try plain text format
            # Look for ERROR, CRITICAL, or exception patterns
            error_patterns = [
                r'ERROR',
                r'CRITICAL',
                r'FATAL',
                r'Exception:',
                r'Traceback',
                r'Error:',
            ]
            
            for pattern in error_patterns:
                if re.search(pattern, line, re.IGNORECASE):
                    # Try to extract more context (previous lines)
                    # Find the index of the original line (before stripping)
                    line_idx = None
                    for idx, orig_line in enumerate(lines):
                        if orig_line.strip() == line:
                            line_idx = idx
                            break
                    
                    if line_idx is not None:
                        context_lines = lines[max(0, line_idx - 5):line_idx + 1]
                        context = '\n'.join(l.strip() for l in context_lines)
                    else:
                        context = line
                    
                    return {
                        'timestamp': '',
                        'level': 'ERROR',
                        'logger': '',
                        'message': line,
                        'exception': context,
                        'file': str(log_file),
                        'format': 'text'
                    }
    
    except Exception as e:
        logger.warning(f"Failed to read log file {log_file}: {e}")
        return None
    
    return None


def get_last_error_from_logs(search_dirs: Optional[list[Path]] = None) -> Optional[Dict[str, Any]]:
    """
    Get the last error from all log files.
    
    Args:
        search_dirs: Optional list of directories to search
    
    Returns:
        Dictionary with error information, or None if no error found
    """
    log_files = find_log_files(search_dirs)
    
    if not log_files:
        logger.info("No log files found")
        return None
    
    # Check each log file (already sorted by modification time)
    for log_file in log_files:
        error = extract_last_error(log_file)
        if error:
            return error
    
    return None


def format_error_for_analysis(error_info: Dict[str, Any]) -> str:
    """
    Format error information for agent analysis.
    
    Args:
        error_info: Dictionary with error information
    
    Returns:
        Formatted string ready for agent analysis
    """
    parts = []
    
    if error_info.get('timestamp'):
        parts.append(f"**Timestamp:** {error_info['timestamp']}")
    
    parts.append(f"**Level:** {error_info.get('level', 'ERROR')}")
    
    if error_info.get('logger'):
        parts.append(f"**Logger:** {error_info['logger']}")
    
    parts.append(f"**Log File:** {error_info.get('file', 'Unknown')}")
    
    parts.append(f"\n**Error Message:**\n{error_info.get('message', 'No message')}")
    
    if error_info.get('exception'):
        parts.append(f"\n**Exception/Traceback:**\n{error_info['exception']}")
    
    return '\n'.join(parts)
