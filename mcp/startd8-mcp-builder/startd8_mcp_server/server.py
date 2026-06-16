#!/usr/bin/env python3
"""
Startd8 MCP Server

This MCP server exposes Startd8 SDK capabilities including:
- Skill discovery and listing
- Skill-based agent generation
- Multi-agent comparison
- Response tracking and storage

Enables LLMs to leverage Startd8's skill-based agents and workflows directly
through the Model Context Protocol.
"""

import json
import os
import re
import sys
import signal
import logging
from contextlib import contextmanager, redirect_stdout
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple, Set
from enum import Enum
from difflib import unified_diff

from pydantic import BaseModel, Field, field_validator, ConfigDict
from mcp.server.fastmcp import FastMCP

# -----------------------------------------------------------------------------
# Startup error aggregation (surfaced at end of startup)
# -----------------------------------------------------------------------------
STARTUP_ERRORS: list[str] = []


def _record_startup_error(msg: str) -> None:
    """Record a startup-time error and log it to stderr."""
    try:
        STARTUP_ERRORS.append(str(msg))
    except Exception:
        pass
    try:
        _eprint(f"[startup-error] {msg}", flush=True)
    except Exception:
        pass

# -----------------------------------------------------------------------------
# Global logging guards to prevent LogRecord collisions on reserved keys (e.g. 'name')
# -----------------------------------------------------------------------------
# Strip reserved keys from LogRecord factory
_ORIG_FACTORY = logging.getLogRecordFactory()
_RESERVED_LOG_KEYS = {
    "name",
    "msg",
    "args",
    "levelname",
    "levelno",
    "pathname",
    "filename",
    "module",
    "exc_info",
    "exc_text",
    "stack_info",
    "lineno",
    "funcName",
    "created",
    "msecs",
    "relativeCreated",
    "thread",
    "threadName",
    "processName",
    "process",
}


def _sanitize_extra(extra: Any) -> Any:
    if isinstance(extra, Mapping):
        cleaned = dict(extra)
        for k in list(cleaned.keys()):
            if k in _RESERVED_LOG_KEYS:
                cleaned.pop(k, None)
        return cleaned
    return None


def _safe_logrecord_factory(*args, **kwargs):
    extra = kwargs.get("extra")
    cleaned = _sanitize_extra(extra)
    if cleaned is not None:
        kwargs["extra"] = cleaned
    elif "extra" in kwargs:
        kwargs.pop("extra")
    try:
        return _ORIG_FACTORY(*args, **kwargs)
    except Exception:
        kwargs.pop("extra", None)
        return _ORIG_FACTORY(*args, **kwargs)


logging.setLogRecordFactory(_safe_logrecord_factory)

# Patch Logger.makeRecord to sanitize extras
_ORIG_MAKE_RECORD = logging.Logger.makeRecord
def _safe_make_record(self, name, level, fn, lno, msg, args, exc_info, func=None, extra=None, sinfo=None):
    cleaned = _sanitize_extra(extra)
    if cleaned is not None:
        extra = cleaned
    else:
        extra = None
    try:
        return _ORIG_MAKE_RECORD(self, name, level, fn, lno, msg, args, exc_info, func, extra, sinfo)
    except Exception:
        return _ORIG_MAKE_RECORD(self, name, level, fn, lno, msg, args, exc_info, func, None, sinfo)
logging.Logger.makeRecord = _safe_make_record  # type: ignore

# Patch Logger._log to sanitize extras pre-validation
_ORIG_LOG = logging.Logger._log
def _safe_log(self, level, msg, args, exc_info=None, extra=None, stack_info=False, stacklevel=1):
    cleaned = _sanitize_extra(extra)
    if cleaned is not None:
        extra = cleaned
    else:
        extra = None
    try:
        return _ORIG_LOG(self, level, msg, args, exc_info=exc_info, extra=extra, stack_info=stack_info, stacklevel=stacklevel)
    except Exception:
        # Retry without extras if validation still trips
        return _ORIG_LOG(self, level, msg, args, exc_info=exc_info, extra=None, stack_info=stack_info, stacklevel=stacklevel)
logging.Logger._log = _safe_log  # type: ignore

# Add a root filter as defense-in-depth
class _StripReservedFilter(logging.Filter):
    def filter(self, record):
        record.__dict__.pop("name", None)
        return True


root_logger = logging.getLogger()
if not any(isinstance(f, _StripReservedFilter) for f in root_logger.filters):
    root_logger.addFilter(_StripReservedFilter())

# Allow logging (guards above should prevent collisions).
logging.disable(logging.NOTSET)
# Never raise logging exceptions in production mode.
logging.raiseExceptions = False


def _eprint(*args, **kwargs) -> None:
    """Print to stderr (safe for MCP stdio)."""
    kwargs.setdefault("file", sys.stderr)
    print(*args, **kwargs)

# Initialize the MCP server
mcp = FastMCP("startd8_mcp")

# Constants
CHARACTER_LIMIT = 25000  # Maximum response size in characters
DEFAULT_PRIMARY_SKILL_PATH = (
    Path.home() / "Documents" / "tools" / "Anthropic" / "context" / "Claude" / "Skills"
)
DEFAULT_SECONDARY_SKILL_PATH = (
    Path.home() / "Documents" / "FMLs" / "dev" / "version2" / "skill-react-game-enhancer"
)
DEFAULT_SKILL_PATHS = [
    Path.home() / ".startd8" / "skills",
    Path("./skills"),
]
DEFAULT_SDK_PATHS = [
    Path(os.getenv("STARTD8_SDK_PATH", "")).expanduser(),
    # Preserve historical path semantics from when this file lived at repo root:
    # old startd8_mcp.py used Path(__file__).parent.parent which resolved to .../Startd8/mcp/
    # This module now lives under startd8_mcp_server/, so we use parent.parent.parent.
    Path(__file__).resolve().parents[2] / "dev" / "startd8-sdk-project" / "src",
]
DEFAULT_PROJECT_ROOT = Path(os.getenv("PROJECT_ROOT", Path.cwd())).resolve()
DEFAULT_TASK_LIST_PATH = os.getenv("TASK_LIST_PATH", "MASTER_TASK_LIST.md")
DEFAULT_TASK_LOG_PATH = os.getenv(
    "TASK_LOG_PATH", str(DEFAULT_PROJECT_ROOT / "logs" / "task-execution.log")
)
DEFAULT_AGENT_NAME = os.getenv("DEFAULT_AGENT", "claude")
ALLOW_AUTO_DEPS = os.getenv("ALLOW_AUTO_DEPS", "true").lower() not in {"0", "false"}
AUTO_MAX_DEPTH = int(os.getenv("AUTO_MAX_DEPTH", "5"))
AUTO_MAX_TASKS = int(os.getenv("AUTO_MAX_TASKS", "20"))
TASK_LOG_ENABLED = os.getenv("TASK_LOG_ENABLED", "true").lower() not in {"0", "false"}
ALLOWED_AGENTS = {
    agent.strip().lower()
    for agent in os.getenv("ALLOWED_AGENTS", DEFAULT_AGENT_NAME).split(",")
    if agent.strip()
}
SCHEMA_VERSION = 1
DEFAULT_ALLOWED_EXTENSIONS = {
    ext.strip().lower().lstrip(".")
    for ext in os.getenv("ALLOWED_EXTENSIONS", "").split(",")
    if ext.strip()
}
DEFAULT_BLOCKED_EXTENSIONS = {
    ext.strip().lower().lstrip(".")
    for ext in os.getenv(
        "BLOCKED_EXTENSIONS", ".exe,.dll,.bat,.sh,.cmd,.com"
    ).split(",")
    if ext.strip()
}
TASK_LOG_ROTATION_DAYS = int(os.getenv("TASK_LOG_ROTATION_DAYS", "14"))
TASK_LOG_MAX_BYTES = int(os.getenv("TASK_LOG_MAX_BYTES", "0"))
FORCE_ANTHROPIC_FALLBACK = os.getenv("STARTD8_FORCE_ANTHROPIC_FALLBACK", "0").lower() not in {"0", "false"}

def _env_flag(name: str, default: bool = False) -> bool:
    """Parse a boolean env var with common truthy/falsey values."""
    raw = os.getenv(name)
    if raw is None:
        return default
    v = raw.strip().lower()
    return v not in {"", "0", "false", "no", "off"}


# Runtime flags (stderr-safe; do not affect MCP JSON on stdout)
MCP_DEBUG = _env_flag("STARTD8_MCP_DEBUG", default=False)
MCP_QUIET = _env_flag("STARTD8_MCP_QUIET", default=False)
MCP_REGISTER_SKILL_TOOLS = _env_flag("STARTD8_MCP_REGISTER_SKILL_TOOLS", default=True)
try:
    MCP_MAX_SKILL_TOOLS = int(os.getenv("STARTD8_MCP_MAX_SKILL_TOOLS", "100") or "100")
except Exception:
    MCP_MAX_SKILL_TOOLS = 100

try:
    MCP_SKILL_CACHE_TTL_SECONDS = int(os.getenv("STARTD8_MCP_SKILL_CACHE_TTL_SECONDS", "10") or "0")
except Exception:
    MCP_SKILL_CACHE_TTL_SECONDS = 0

try:
    MCP_STARTUP_MAX_SKILLS = int(
        os.getenv("STARTD8_MCP_STARTUP_MAX_SKILLS", str(max(MCP_MAX_SKILL_TOOLS, 100))) or "0"
    )
except Exception:
    MCP_STARTUP_MAX_SKILLS = max(MCP_MAX_SKILL_TOOLS, 100)

# Startup bookkeeping (filled when running main()).
STARTUP_SKILLS_INDEXED: Optional[int] = None
STARTUP_SKILLS_INDEX_LIMIT: Optional[int] = None
STARTUP_SKILLS_INDEX_SKIPPED: Optional[bool] = None
STARTUP_METRICS: Dict[str, Any] = {}

# In-memory cache for skill discovery (helps repeated tool calls).
_SKILLS_CACHE: Dict[str, Any] = {
    "key": None,
    "expires_at": 0.0,
    "skills": [],
}

@contextmanager
def _redirect_stdout_to_stderr():
    """Best-effort guard to prevent accidental stdout noise from breaking MCP stdio."""
    try:
        with redirect_stdout(sys.stderr):
            yield
    except Exception:
        yield


# ═══════════════════════════════════════════════════════════════
# SIGNAL HANDLERS
# ═══════════════════════════════════════════════════════════════


def _setup_signal_handlers() -> None:
    """Handle SIGINT for a clean exit without stack traces."""

    def _handle_sigint(signum, frame):
        _eprint("\nStartd8 MCP server received SIGINT. Shutting down cleanly.", flush=True)
        sys.exit(0)

    try:
        signal.signal(signal.SIGINT, _handle_sigint)
    except Exception:
        pass

# ═══════════════════════════════════════════════════════════════
# LOGGING HELPERS
# ═══════════════════════════════════════════════════════════════


def _log(msg: str) -> None:
    """Lightweight server-side debug logger."""
    # IMPORTANT: MCP stdio transport uses stdout for JSON-RPC. Logs must go to stderr.
    if not MCP_DEBUG:
        return
    print(f"[mcp-debug] {msg}", file=sys.stderr, flush=True)


def _log_request(tool: str, payload: Dict[str, Any]) -> None:
    """Log incoming tool requests."""
    try:
        _log(f"REQ {tool}: {payload}")
    except Exception:
        pass


def _log_response(tool: str, payload: Dict[str, Any]) -> None:
    """Log outgoing tool responses (truncated)."""
    try:
        preview = json.dumps(payload)
        if len(preview) > 500:
            preview = preview[:500] + "...(truncated)"
        _log(f"RESP {tool}: {preview}")
    except Exception:
        pass


# ═══════════════════════════════════════════════════════════════
# ENUMS
# ═══════════════════════════════════════════════════════════════

class ResponseFormat(str, Enum):
    """Output format for tool responses."""
    MARKDOWN = "markdown"
    JSON = "json"


# ═══════════════════════════════════════════════════════════════
# PYDANTIC MODELS FOR INPUT VALIDATION
# ═══════════════════════════════════════════════════════════════

class ListSkillsInput(BaseModel):
    """Input model for listing available Claude Skills."""
    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True,
        extra='forbid'
    )

    response_format: ResponseFormat = Field(
        default=ResponseFormat.MARKDOWN,
        description="Output format: 'markdown' for human-readable or 'json' for machine-readable"
    )
    include_details: bool = Field(
        default=False,
        description="Include full skill descriptions and metadata (default: False for concise output)"
    )


class GetSkillInput(BaseModel):
    """Input model for retrieving skill information."""
    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True,
        extra='forbid'
    )

    skill_name: str = Field(
        ...,
        description="Name or directory name of the skill (e.g., 'html5-game-designer-pro', 'skill-html_game_dev')",
        min_length=1,
        max_length=200
    )
    response_format: ResponseFormat = Field(
        default=ResponseFormat.MARKDOWN,
        description="Output format: 'markdown' for human-readable or 'json' for machine-readable"
    )

    @field_validator('skill_name')
    @classmethod
    def validate_skill_name(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Skill name cannot be empty")
        return v.strip()


class UseSkillInput(BaseModel):
    """Input model for generating responses using a skill-based agent."""
    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True,
        extra='forbid'
    )

    skill_name: str = Field(
        ...,
        description="Name of the skill to use (e.g., 'html5-game-designer-pro', 'mcp-builder')",
        min_length=1,
        max_length=200
    )
    prompt: str = Field(
        ...,
        description="User prompt to send to the skill-based agent",
        min_length=1,
        max_length=50000
    )
    model: Optional[str] = Field(
        default="claude-sonnet-4-6",
        description="Claude model to use (default: claude-sonnet-4-6)",
        max_length=100
    )
    max_tokens: Optional[int] = Field(
        default=16384,
        description="Maximum tokens in response (default: 16384)",
        ge=1,
        le=200000
    )
    track_response: bool = Field(
        default=True,
        description="Store response in Startd8 storage for tracking (default: True)"
    )
    response_format: ResponseFormat = Field(
        default=ResponseFormat.MARKDOWN,
        description=(
            "Output format: 'markdown' for human-readable summary "
            "or 'json' for structured metrics and output."
        ),
    )

    @field_validator('skill_name', 'prompt')
    @classmethod
    def validate_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Field cannot be empty")
        return v.strip()


class CompareAgentsInput(BaseModel):
    """Input model for comparing multiple agents on the same prompt."""
    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True,
        extra='forbid'
    )

    prompt: str = Field(
        ...,
        description="Prompt to send to all agents for comparison",
        min_length=1,
        max_length=50000
    )
    agents: List[str] = Field(
        ...,
        description="List of agent names to compare (e.g., ['claude', 'gpt4', 'composer'])",
        min_length=2,
        max_length=5
    )
    response_format: ResponseFormat = Field(
        default=ResponseFormat.MARKDOWN,
        description="Output format for comparison results"
    )

    @field_validator('prompt')
    @classmethod
    def validate_prompt(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Prompt cannot be empty")
        return v.strip()


class SkillPromptInput(BaseModel):
    """Input model for running a specific skill as a dedicated tool."""
    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True, extra="forbid")

    prompt: str = Field(
        ...,
        description="User prompt to send to this skill",
        min_length=1,
        max_length=50000,
    )
    model: Optional[str] = Field(
        default="claude-sonnet-4-6",
        description="Claude model to use (default: claude-sonnet-4-6)",
        max_length=100,
    )
    max_tokens: Optional[int] = Field(
        default=16384,
        description="Maximum tokens in response (default: 16384)",
        ge=1,
        le=200000,
    )
    track_response: bool = Field(
        default=True,
        description="Store response in Startd8 storage for tracking (default: True)",
    )
    response_format: ResponseFormat = Field(
        default=ResponseFormat.MARKDOWN,
        description="Output format: 'markdown' for human-readable or 'json' for structured output.",
    )

    @field_validator("prompt")
    @classmethod
    def _validate_prompt(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Prompt cannot be empty")
        return v.strip()


class HelpInput(BaseModel):
    """Input model for server help / capability overview."""
    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True, extra="forbid")

    topic: Optional[str] = Field(
        default=None,
        description=(
            "Optional focus area: skills, tasks, prompts, agents, resources, troubleshooting. "
            "If omitted, returns a general overview."
        ),
        max_length=100,
    )
    response_format: ResponseFormat = Field(
        default=ResponseFormat.MARKDOWN,
        description="Output format for help content",
    )


class StatusInput(BaseModel):
    """Input model for server status / diagnostics."""
    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True, extra="forbid")

    response_format: ResponseFormat = Field(
        default=ResponseFormat.MARKDOWN,
        description="Output format for status content",
    )
    include_skill_names: bool = Field(
        default=True,
        description="Include skill names in output (may be long)",
    )
    include_pythonpath: bool = Field(
        default=False,
        description="Include full sys.path entries (very verbose)",
    )


class ConciergeAction(str, Enum):
    """Concierge actions. Over MCP all are read/preview-only — the CLI is the only writer (OQ-7)."""
    SURVEY = "survey"
    ASSESS = "assess"
    INSTANTIATE_KICKOFF = "instantiate-kickoff"
    LOG_FRICTION = "log-friction"


class ConciergeInput(BaseModel):
    """Input for the project-side onboarding-assist tool. Over MCP every action is preview-only
    (FR-C3): survey/assess read; instantiate-kickoff/log-friction return a planned-write
    descriptor and never touch disk (only the CLI applies)."""
    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True, extra="forbid")

    action: ConciergeAction = Field(
        description="survey/assess = read reports; instantiate-kickoff/log-friction = preview the planned writes",
    )
    project_root: Optional[str] = Field(
        default=None,
        description="Path to the project to inspect (default: server PROJECT_ROOT). Read-only over MCP.",
    )
    # instantiate-kickoff
    posture: Optional[str] = Field(default=None, description="prototype | production (instantiate-kickoff)")
    with_authoring: bool = Field(default=False, description="Also project the authoring trio (instantiate-kickoff)")
    # log-friction
    friction: Optional[str] = Field(default=None, description="The friction encountered (log-friction)")
    what_happened: Optional[str] = Field(default=None, description="What happened (log-friction)")
    implication: Optional[str] = Field(default=None, description="Implication for the SDK/role (log-friction)")


class TaskListInput(BaseModel):
    """Input for tasks.list."""
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    file: Optional[str] = Field(
        default=None,
        description="Path to task list (default: TASK_LIST_PATH or MASTER_TASK_LIST.md)",
    )


class TaskStatusInput(BaseModel):
    """Input for tasks.status."""
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    file: Optional[str] = Field(
        default=None,
        description="Path to task list (default: TASK_LIST_PATH or MASTER_TASK_LIST.md)",
    )


class TaskRunInput(BaseModel):
    """Input for tasks.run."""
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    id: Optional[str] = Field(default=None, description="Task ID to run")
    file: Optional[str] = Field(
        default=None,
        description="Path to task list (default: TASK_LIST_PATH or MASTER_TASK_LIST.md)",
    )
    auto: bool = Field(
        default=False,
        description="Auto-resolve unmet dependencies (recursively within caps)",
    )
    agent: Optional[str] = Field(
        default=None,
        description="Agent name (default: DEFAULT_AGENT; validated against ALLOWED_AGENTS)",
    )
    dry_run: bool = Field(
        default=True,
        description="If true, validate and return diffs without applying",
    )


# ═══════════════════════════════════════════════════════════════
# SHARED UTILITY FUNCTIONS
# ═══════════════════════════════════════════════════════════════

def _get_skill_directories() -> List[Path]:
    """
    Discover skill directories from configured paths.
    
    Returns list of paths that exist and contain SKILL.md files.
    """
    skill_dirs: list[Path] = []
    seen: set[str] = set()

    def _add_dir(p: Path) -> None:
        try:
            key = str(p.expanduser().resolve()).lower()
        except Exception:
            key = str(p.expanduser()).lower()
        if key in seen:
            return
        seen.add(key)
        skill_dirs.append(p)
    
    # Primary skill scan roots:
    # - STARTD8_SKILL_PATH (colon-separated)
    # - fallback to DEFAULT_PRIMARY_SKILL_PATH when unset
    env_paths = (os.getenv("STARTD8_SKILL_PATH") or "").strip()
    if env_paths:
        for path_str in env_paths.split(":"):
            if not path_str.strip():
                continue
            path = Path(path_str).expanduser()
            if path.exists():
                _add_dir(path)
    else:
        try:
            if DEFAULT_PRIMARY_SKILL_PATH.exists():
                _add_dir(DEFAULT_PRIMARY_SKILL_PATH)
        except Exception:
            pass

    # Secondary skill scan roots (disabled by default):
    # - STARTD8_SKILL_PATH_SECONDARY_ENABLED=1 enables scanning
    # - STARTD8_SKILL_PATH_SECONDARY can override the default secondary path
    secondary_enabled = _env_flag("STARTD8_SKILL_PATH_SECONDARY_ENABLED", default=False)
    if secondary_enabled:
        secondary_paths = (os.getenv("STARTD8_SKILL_PATH_SECONDARY") or "").strip()
        if secondary_paths:
            for path_str in secondary_paths.split(":"):
                if not path_str.strip():
                    continue
                path = Path(path_str).expanduser()
                if path.exists():
                    _add_dir(path)
        else:
            try:
                if DEFAULT_SECONDARY_SKILL_PATH.exists():
                    _add_dir(DEFAULT_SECONDARY_SKILL_PATH)
            except Exception:
                pass
    
    # Add default paths
    for path in DEFAULT_SKILL_PATHS:
        path = path.expanduser()
        if path.exists():
            _add_dir(path)
    
    return skill_dirs


def _skill_cache_key(dirs: List[Path]) -> tuple:
    """Build a stable cache key for the current skill discovery configuration."""
    try:
        resolved = []
        for d in dirs:
            try:
                resolved.append(str(d.expanduser().resolve()))
            except Exception:
                resolved.append(str(d.expanduser()))
        return (
            tuple(x.lower() for x in resolved),
            os.getenv("STARTD8_SKILL_PATH", ""),
            os.getenv("STARTD8_SKILL_PATH_SECONDARY", ""),
            os.getenv("STARTD8_SKILL_PATH_SECONDARY_ENABLED", ""),
        )
    except Exception:
        return (
            os.getenv("STARTD8_SKILL_PATH", ""),
            os.getenv("STARTD8_SKILL_PATH_SECONDARY", ""),
            os.getenv("STARTD8_SKILL_PATH_SECONDARY_ENABLED", ""),
        )


def _find_skills(max_results: Optional[int] = None) -> List[Dict[str, Any]]:
    """
    Find all available Claude Skills by searching for SKILL.md files.
    
    Returns list of skill metadata dictionaries.
    """
    # Fast path: in-memory cache (only for full scans).
    if max_results is None and MCP_SKILL_CACHE_TTL_SECONDS > 0:
        try:
            now = datetime.now(timezone.utc).timestamp()
            dirs_now = _get_skill_directories()
            key_now = _skill_cache_key(dirs_now)
            cache_key = _SKILLS_CACHE.get("key")
            if cache_key == key_now and now < float(_SKILLS_CACHE.get("expires_at", 0.0) or 0.0):
                cached = _SKILLS_CACHE.get("skills") or []
                return [dict(x) for x in cached]
        except Exception:
            pass

    skills: list[Dict[str, Any]] = []
    seen_skill_files_global: set[str] = set()
    try:
        skill_dirs = _get_skill_directories()
        hit_limit = False
        
        for base_dir in skill_dirs:
            try:
                # Stream scan files so we can stop early when max_results is set.
                for pattern in ("SKILL.md", "skill.md"):
                    for sf in base_dir.rglob(pattern):
                        try:
                            key = str(sf.resolve()).lower()
                        except Exception:
                            key = str(sf).lower()
                        if key in seen_skill_files_global:
                            continue
                        seen_skill_files_global.add(key)
                        try:
                            skill_dir = sf.parent
                            metadata = _parse_skill_file(sf)

                            if metadata:
                                metadata["directory"] = str(skill_dir)
                                metadata["file_path"] = str(sf)
                                skills.append(metadata)
                                if max_results is not None and len(skills) >= max_results:
                                    hit_limit = True
                                    break
                        except Exception as e:
                            # Skip individual skill files that fail to parse
                            _log(f"Skipping skill file {sf}: {e}")
                            continue
                    if hit_limit:
                        break
                if hit_limit:
                    break
            except Exception as e:
                # Skip directories that fail to scan
                _log(f"Skipping skill directory {base_dir}: {e}")
                continue
        if hit_limit:
            _log(
                f"Skill discovery hit max_results={max_results}. "
                "Increase STARTD8_MCP_STARTUP_MAX_SKILLS if you want more indexed at startup."
            )
    except Exception as e:
        # Log but don't fail - return empty list if skill discovery fails
        _record_startup_error(f"Error discovering skills: {e}")
        _log(f"Error discovering skills: {e}")
        return []

    # Stable ordering helps clients (and users) scan large skill lists.
    try:
        skills.sort(
            key=lambda s: (
                str(s.get("name", "")).lower(),
                str(s.get("directory", "")).lower(),
            )
        )
    except Exception:
        pass

    # Populate cache (only for full scans).
    if max_results is None and MCP_SKILL_CACHE_TTL_SECONDS > 0:
        try:
            now = datetime.now(timezone.utc).timestamp()
            dirs_now = _get_skill_directories()
            _SKILLS_CACHE["key"] = _skill_cache_key(dirs_now)
            _SKILLS_CACHE["expires_at"] = now + float(MCP_SKILL_CACHE_TTL_SECONDS)
            _SKILLS_CACHE["skills"] = [dict(x) for x in skills]
        except Exception:
            pass

    return skills


def _parse_skill_file(skill_path: Path) -> Optional[Dict[str, Any]]:
    """
    Parse a SKILL.md file to extract metadata.
    
    Expected format:
    ---
    name: skill-name
    description: Description text
    metadata:
      version: "1.0.0"
      author: Name
      tags: tag1, tag2
    ---
    """
    try:
        content = skill_path.read_text(encoding='utf-8')
        
        # Extract YAML frontmatter
        if content.startswith('---'):
            parts = content.split('---', 2)
            if len(parts) >= 3:
                import yaml
                frontmatter = yaml.safe_load(parts[1])
                
                return {
                    "name": frontmatter.get("name", skill_path.parent.name),
                    "description": frontmatter.get("description", ""),
                    "metadata": frontmatter.get("metadata", {}),
                }
        
        # Fallback: use directory name
        return {
            "name": skill_path.parent.name,
            "description": "Claude Skill",
            "metadata": {},
        }
    
    except Exception as e:
        return None


def _find_skill_by_name(skill_name: str) -> Optional[Dict[str, Any]]:
    """Find a skill by its name or directory name."""
    skills = _find_skills()
    
    # Try exact match first
    for skill in skills:
        if skill["name"] == skill_name:
            return skill
    
    # Try directory name match
    for skill in skills:
        dir_name = Path(skill["directory"]).name
        if dir_name == skill_name:
            return skill
    
    # Try partial match
    skill_name_lower = skill_name.lower()
    for skill in skills:
        if skill_name_lower in skill["name"].lower():
            return skill
        if skill_name_lower in Path(skill["directory"]).name.lower():
            return skill
    
    return None


def _load_skill_instructions(skill: Dict[str, Any]) -> str:
    """Load the full SKILL.md content for a skill."""
    try:
        skill_path = Path(skill["file_path"])
        return skill_path.read_text(encoding='utf-8')
    except Exception as e:
        return f"Error loading skill instructions: {str(e)}"


def _handle_error(e: Exception) -> str:
    """Consistent error formatting across all tools."""
    return f"Error: {type(e).__name__}: {str(e)}"


def _response(
    *,
    error: Optional[str] = None,
    message: Optional[str] = None,
    data: Optional[Dict[str, Any]] = None,
    status: Optional[str] = None,
    **kwargs: Any,
) -> str:
    """Build the canonical JSON envelope for tool responses."""
    payload: Dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "error": error,
        "message": message,
    }
    if status is not None:
        payload["status"] = status
    if data is not None:
        payload["data"] = data
    payload.update(kwargs)
    return json.dumps(payload, indent=2)


def _normalize_token_usage(usage: Any) -> Dict[str, Optional[int]]:
    """
    Normalize token usage returned by different SDKs into a stable dict.

    Seen shapes:
    - dicts: {"input_tokens": ..., "output_tokens": ..., "total_tokens": ...}
    - Anthropic SDK objects (e.g. TokenUsage) with .input_tokens/.output_tokens
    - Startd8 SDK TokenUsage-like objects with .input/.output/.total
    """
    try:
        if usage is None:
            return {"input_tokens": None, "output_tokens": None, "total_tokens": None}

        inp = out = total = None

        if isinstance(usage, dict):
            inp = usage.get("input_tokens", usage.get("input"))
            out = usage.get("output_tokens", usage.get("output"))
            total = usage.get("total_tokens", usage.get("total"))
        else:
            inp = getattr(usage, "input_tokens", None)
            out = getattr(usage, "output_tokens", None)
            total = getattr(usage, "total_tokens", None)
            if inp is None:
                inp = getattr(usage, "input", None)
            if out is None:
                out = getattr(usage, "output", None)
            if total is None:
                total = getattr(usage, "total", None)

        def _to_int(v: Any) -> Optional[int]:
            try:
                if v is None:
                    return None
                return int(v)
            except Exception:
                return None

        inp_i = _to_int(inp)
        out_i = _to_int(out)
        total_i = _to_int(total)

        if total_i is None and inp_i is not None and out_i is not None:
            total_i = inp_i + out_i

        return {"input_tokens": inp_i, "output_tokens": out_i, "total_tokens": total_i}
    except Exception:
        return {"input_tokens": None, "output_tokens": None, "total_tokens": None}


def _format_skills_markdown(skills: List[Dict[str, Any]], include_details: bool = False) -> str:
    """Format skills list as markdown."""
    if not skills:
        return (
            "No Claude Skills found.\n\n"
            "To add skills, place SKILL.md files in:\n"
            "- ~/.startd8/skills/\n"
            "- ./skills/\n\n"
            "Or set STARTD8_SKILL_PATH to a directory (or colon-separated list) to scan.\n"
            "Optional: set STARTD8_SKILL_PATH_SECONDARY and enable STARTD8_SKILL_PATH_SECONDARY_ENABLED=1.\n"
        )
    
    lines = ["# Available Claude Skills", ""]
    lines.append(f"Found {len(skills)} skill(s)\n")
    
    for skill in skills:
        name = skill.get("name", "Unknown")
        desc = skill.get("description", "No description")
        meta = skill.get("metadata", {})
        suggested_tool: Optional[str] = None
        if MCP_REGISTER_SKILL_TOOLS:
            try:
                base = Path(skill.get("directory", "")).name
            except Exception:
                base = ""
            raw_name = (base or name or "").strip()
            if raw_name and raw_name != "Unknown":
                try:
                    suggested_tool = f"startd8_skill_{_normalize_skill_tool_suffix(raw_name)}"
                except Exception:
                    suggested_tool = None
        
        lines.append(f"## {name}")
        
        if include_details:
            lines.append(f"\n**Description:** {desc}\n")
            if suggested_tool:
                lines.append(f"**Tool:** `{suggested_tool}`")
            lines.append(f"**Resource:** `skill://{name}`")
            
            if meta:
                lines.append("**Metadata:**")
                if "version" in meta:
                    lines.append(f"- Version: {meta['version']}")
                if "author" in meta:
                    lines.append(f"- Author: {meta['author']}")
                if "tags" in meta:
                    tags = meta['tags']
                    if isinstance(tags, str):
                        tags = tags.split(", ")
                    lines.append(f"- Tags: {', '.join(tags)}")
            
            lines.append(f"\n**Location:** `{skill.get('directory', 'Unknown')}`")
        else:
            if suggested_tool:
                lines.append(f"- {desc} (tool: `{suggested_tool}`)")
            else:
                lines.append(f"- {desc}")
        
        lines.append("")
    
    return "\n".join(lines)


def _format_skills_json(skills: List[Dict[str, Any]]) -> str:
    """Format skills list as JSON."""
    enriched: list[Dict[str, Any]] = []
    for s in skills:
        item = dict(s)
        try:
            base = Path(item.get("directory", "")).name
        except Exception:
            base = ""
        raw_name = (base or item.get("name") or "").strip()
        if raw_name:
            item["resource_uri"] = f"skill://{item.get('name') or raw_name}"
            if MCP_REGISTER_SKILL_TOOLS:
                try:
                    item["tool_name"] = f"startd8_skill_{_normalize_skill_tool_suffix(raw_name)}"
                except Exception:
                    pass
        enriched.append(item)
    return json.dumps({"total": len(skills), "skills": enriched}, indent=2)


# ═══════════════════════════════════════════════════════════════
# TASK EXECUTION HELPERS
# ═══════════════════════════════════════════════════════════════


def _ensure_sdk_available() -> bool:
    """
    Make the Startd8 SDK importable by extending sys.path with known locations.
    """
    for candidate in DEFAULT_SDK_PATHS:
        if candidate and candidate.exists():
            candidate_str = str(candidate)
            if candidate_str not in sys.path:
                sys.path.insert(0, candidate_str)
    try:
        with _redirect_stdout_to_stderr():
            import startd8  # noqa: F401
        try:
            with _redirect_stdout_to_stderr():
                from startd8.skills.agent import SkillAgent  # noqa: F401
            globals()["SkillAgentConcrete"] = SkillAgent
            _log(f"SkillAgent loaded from {SkillAgent.__module__}")
        except Exception as e:
            globals()["SkillAgentConcrete"] = None
            _record_startup_error(f"SkillAgent import failed: {e}")
            _log(f"SkillAgent import failed: {e}")
        # ClaudeSkillAgent is optional (some SDK layouts don't export it at package top-level).
        # Prefer canonical import path, but do not treat absence as a startup error if SkillAgent works.
        try:
            with _redirect_stdout_to_stderr():
                from startd8.skills.agent import ClaudeSkillAgent  # type: ignore  # noqa: F401
            globals()["ClaudeSkillAgent"] = ClaudeSkillAgent
            _log(f"ClaudeSkillAgent loaded from {ClaudeSkillAgent.__module__}")
        except Exception as e1:
            try:
                with _redirect_stdout_to_stderr():
                    from startd8.skills import ClaudeSkillAgent  # type: ignore  # noqa: F401
                globals()["ClaudeSkillAgent"] = ClaudeSkillAgent
                _log(f"ClaudeSkillAgent loaded from {ClaudeSkillAgent.__module__}")
            except Exception as e2:
                globals()["ClaudeSkillAgent"] = None
                if globals().get("SkillAgentConcrete") is None:
                    _record_startup_error(f"ClaudeSkillAgent import failed: {e2}")
                else:
                    _log(f"ClaudeSkillAgent unavailable (non-fatal): {e2}")
        return True
    except Exception as e:
        globals()["ClaudeSkillAgent"] = None
        globals()["SkillAgentConcrete"] = None
        _record_startup_error(f"startd8 import failed: {e}")
        _log(f"startd8 import failed: {e}")
        return False


def _resolve_skill_agent_cls():
    """
    Resolve a concrete SkillAgent/ClaudeSkillAgent from the SDK at call time.
    Prefer SkillAgent, then ClaudeSkillAgent. Returns None if unavailable.
    """
    # Prefer already loaded
    if globals().get("SkillAgentConcrete"):
        return globals()["SkillAgentConcrete"]
    if globals().get("ClaudeSkillAgent"):
        return globals()["ClaudeSkillAgent"]

    # Attempt fresh import (in case server was started without SDK on PYTHONPATH).
    try:
        with _redirect_stdout_to_stderr():
            from startd8.skills.agent import SkillAgent as _SkillAgent
        globals()["SkillAgentConcrete"] = _SkillAgent
        return _SkillAgent
    except Exception:
        pass
    try:
        with _redirect_stdout_to_stderr():
            from startd8.skills import ClaudeSkillAgent as _ClaudeSkillAgent
        globals()["ClaudeSkillAgent"] = _ClaudeSkillAgent
        return _ClaudeSkillAgent
    except Exception:
        return None


def _get_task_modules():
    """Import and return task-related modules, raising a clear error if missing."""
    if not _ensure_sdk_available():
        raise ImportError(
            "Startd8 SDK not found. Set STARTD8_SDK_PATH or install the SDK."
        )
    with _redirect_stdout_to_stderr():
        from startd8.tasks.manager import TaskListManager as _TaskListManager
        from startd8.tasks.models import TaskStatus as _TaskStatus, Task as _Task
        from startd8.execution.parser import ActionParser as _ActionParser
        from startd8.execution.actions import ActionApplicator as _ActionApplicator
        from startd8.execution.prompt import PromptBuilder as _PromptBuilder
        try:
            from startd8.providers.registry import ProviderRegistry as _ProviderRegistry
        except Exception:
            _ProviderRegistry = None  # type: ignore

    # Prefer already-monkeypatched globals when present (tests).
    TaskListManager = globals().get("TaskListManager", _TaskListManager)
    TaskStatus = globals().get("TaskStatus", _TaskStatus)
    Task = globals().get("Task", _Task)
    ActionParser = globals().get("ActionParser", _ActionParser)
    ActionApplicator = globals().get("ActionApplicator", _ActionApplicator)
    PromptBuilder = globals().get("PromptBuilder", _PromptBuilder)
    ProviderRegistry = globals().get("ProviderRegistry", _ProviderRegistry)
    # Expose for monkeypatch in tests.
    globals().update(
        {
            "TaskListManager": TaskListManager,
            "TaskStatus": TaskStatus,
            "Task": Task,
            "ActionParser": ActionParser,
            "ActionApplicator": ActionApplicator,
            "PromptBuilder": PromptBuilder,
            "ProviderRegistry": ProviderRegistry,
        }
    )
    return {
        "TaskListManager": TaskListManager,
        "TaskStatus": TaskStatus,
        "Task": Task,
        "ActionParser": ActionParser,
        "ActionApplicator": ActionApplicator,
        "PromptBuilder": PromptBuilder,
        "ProviderRegistry": ProviderRegistry,
    }


def _resolve_path(path_str: Optional[str], default_path: str) -> Path:
    """Resolve a path relative to PROJECT_ROOT and enforce allowlist."""
    base = DEFAULT_PROJECT_ROOT
    target = Path(path_str or default_path).expanduser()
    if not target.is_absolute():
        target = base / target
    resolved = target.resolve()
    if base not in resolved.parents and resolved != base:
        raise ValueError(f"Path escapes project root: {resolved}")
    return resolved


def _resolve_project_file(path_str: str) -> Path:
    """Resolve a project file path under PROJECT_ROOT with traversal guard."""
    return _resolve_path(path_str, "")


def _parse_ext(path: Path) -> str:
    return path.suffix.lower().lstrip(".")


def _validate_action_path(path_str: str) -> Path:
    """
    Validate action paths with allow/block lists and traversal guard.
    Uses SDK validator when available to keep parity with production behavior.
    """
    allowed = DEFAULT_ALLOWED_EXTENSIONS or None
    blocked = DEFAULT_BLOCKED_EXTENSIONS or None
    target = Path(path_str)
    ext = _parse_ext(target)
    if allowed is not None and ext not in allowed:
        raise ValueError(f"Extension '.{ext}' not allowed")
    if blocked is not None and ext in blocked:
        raise ValueError(f"Extension '.{ext}' is blocked")

    try:
        with _redirect_stdout_to_stderr():
            from startd8.execution import actions as exec_actions
            resolved = exec_actions.validate_task_file_path(
                path_str,
                DEFAULT_PROJECT_ROOT,
                allowed_extensions=allowed,
                blocked_extensions=blocked,
            )
        resolved_path = Path(resolved).resolve()
        # Re-check after SDK resolution in case it normalized paths.
        ext2 = _parse_ext(resolved_path)
        if allowed is not None and ext2 not in allowed:
            raise ValueError(f"Extension '.{ext2}' not allowed")
        if blocked is not None and ext2 in blocked:
            raise ValueError(f"Extension '.{ext2}' is blocked")
        return resolved_path
    except Exception:
        target = _resolve_project_file(path_str)
        return target


def _load_tasks(path: Path):
    modules = _get_task_modules()
    TaskListManager = modules["TaskListManager"]
    mgr = TaskListManager(path)
    tasks = mgr.parse()
    task_map = {t.id: t for t in tasks}
    return mgr, tasks, task_map, modules


def _serialize_task(t) -> Dict[str, Any]:
    return {
        "id": t.id,
        "title": getattr(t, "title", ""),
        "priority": getattr(t, "priority", None).value if getattr(t, "priority", None) else None,
        "status": getattr(t, "status", None).value if getattr(t, "status", None) else None,
        "dependencies": getattr(t, "dependencies", []),
    }


def _detect_cycles(task_map: Dict[str, Any]) -> Optional[List[str]]:
    """Return cycle chain if detected, otherwise None."""
    visited: Set[str] = set()
    stack: Set[str] = set()

    def dfs(node: str, path: List[str]) -> Optional[List[str]]:
        visited.add(node)
        stack.add(node)
        for dep in getattr(task_map[node], "dependencies", []):
            if dep not in task_map:
                continue
            if dep not in visited:
                found = dfs(dep, path + [dep])
                if found:
                    return found
            elif dep in stack:
                return path + [dep]
        stack.remove(node)
        return None

    for task_id in task_map:
        if task_id not in visited:
            cycle = dfs(task_id, [task_id])
            if cycle:
                return cycle
    return None


def _validate_dependencies(task, task_map: Dict[str, Any], auto: bool, TaskStatus):
    unknown = [dep for dep in getattr(task, "dependencies", []) if dep not in task_map]
    if unknown:
        raise ValueError(f"Unknown dependencies: {', '.join(unknown)}")
    unmet = [
        dep
        for dep in getattr(task, "dependencies", [])
        if getattr(task_map[dep], "status", None) != TaskStatus.COMPLETED
    ]
    if unmet and not auto:
        raise RuntimeError(f"Dependencies not completed: {', '.join(unmet)}")
    return unmet


def _select_task(tasks: List[Any], task_id: Optional[str], TaskStatus) -> Any:
    if task_id:
        for t in tasks:
            if t.id == task_id:
                return t
        raise ValueError(f"Task {task_id} not found")
    priority_order = [
        getattr(TaskStatus, "CRITICAL", None),
        getattr(TaskStatus, "HIGH", None),
        getattr(TaskStatus, "MEDIUM", None),
        getattr(TaskStatus, "LOW", None),
    ]
    open_tasks = [
        t
        for t in tasks
        if getattr(t, "status", None)
        in {getattr(TaskStatus, "OPEN", None), getattr(TaskStatus, "IN_PROGRESS", None)}
    ]
    if not open_tasks:
        raise RuntimeError("No runnable tasks found")
    open_tasks.sort(
        key=lambda t: priority_order.index(getattr(t, "priority", None))
        if getattr(t, "priority", None) in priority_order
        else len(priority_order)
    )
    return open_tasks[0]


def _status_counts(tasks: List[Any], task_map: Dict[str, Any], TaskStatus) -> Dict[str, int]:
    completed = sum(getattr(t, "status", None) == TaskStatus.COMPLETED for t in tasks)
    blocked = sum(getattr(t, "status", None) == TaskStatus.BLOCKED for t in tasks)
    in_progress = sum(getattr(t, "status", None) == TaskStatus.IN_PROGRESS for t in tasks)
    open_tasks = sum(getattr(t, "status", None) == TaskStatus.OPEN for t in tasks)
    pending = sum(
        getattr(t, "status", None)
        in {TaskStatus.OPEN, TaskStatus.IN_PROGRESS, TaskStatus.BLOCKED}
        for t in tasks
    )
    runnable = 0
    for t in tasks:
        if getattr(t, "status", None) in {TaskStatus.OPEN, TaskStatus.IN_PROGRESS}:
            deps = getattr(t, "dependencies", [])
            unmet = [dep for dep in deps if dep in task_map and getattr(task_map[dep], "status", None) != TaskStatus.COMPLETED]
            if not unmet and getattr(t, "status", None) != TaskStatus.BLOCKED:
                runnable += 1
    return {
        "total": len(tasks),
        "completed": completed,
        "blocked": blocked,
        "in_progress": in_progress,
        "open": open_tasks,
        "pending": pending,
        "runnable": runnable,
    }


def _write_audit_log(entry: Dict[str, Any]) -> None:
    if not TASK_LOG_ENABLED:
        return
    path = Path(DEFAULT_TASK_LOG_PATH).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    entry = dict(entry)
    entry["timestamp"] = datetime.now(timezone.utc).isoformat()

    # Simple rotation: time-based plus optional size cap.
    try:
        if path.exists():
            rotate = False
            if TASK_LOG_ROTATION_DAYS > 0:
                age_days = (datetime.now(timezone.utc) - datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)).days
                rotate = age_days >= TASK_LOG_ROTATION_DAYS
            if not rotate and TASK_LOG_MAX_BYTES > 0:
                rotate = path.stat().st_size >= TASK_LOG_MAX_BYTES
            if rotate:
                suffix = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
                path.rename(path.with_name(f"{path.name}.{suffix}"))
    except Exception:
        # Best-effort logging; failures should not block execution.
        return

    try:
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry) + "\n")
    except Exception:
        return


def _compute_diffs(actions: List[Any]) -> List[Dict[str, Any]]:
    """Create simple unified diffs for dry-run visibility."""
    diffs: List[Dict[str, Any]] = []
    for action in actions:
        try:
            target = _validate_action_path(action.path)
            old_text = ""
            if target.exists():
                try:
                    old_text = target.read_text(encoding="utf-8")
                except Exception:
                    old_text = ""
            new_text = action.content or ""
            from_label = str(target)
            to_label = f"{target} (new)"
            diff_lines = unified_diff(
                old_text.splitlines(),
                new_text.splitlines(),
                fromfile=from_label,
                tofile=to_label,
                lineterm="",
            )
            diffs.append({"path": str(target), "diff": "\n".join(diff_lines)})
        except Exception:
            continue
    return diffs


# ═══════════════════════════════════════════════════════════════
# MCP TOOLS
# ═══════════════════════════════════════════════════════════════

@mcp.tool(
    name="startd8_list_skills",
    annotations={
        "title": "List Startd8 Skills",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False
    }
)
async def startd8_list_skills(params: ListSkillsInput) -> str:
    """
    List all available Claude Skills discoverable by Startd8.
    
    This tool searches configured skill directories for SKILL.md files and returns
    a list of available skills with their metadata. Skills are discovered from:
    - ~/.startd8/skills/
    - ~/Documents/FMLs/dev/version2/
    - ./skills/ (current directory)
    - STARTD8_SKILL_PATH environment variable (colon-separated paths)
    
    Args:
        params (ListSkillsInput): Parameters containing:
            - response_format (ResponseFormat): 'markdown' for human-readable or 'json' for machine-readable
            - include_details (bool): Include full descriptions and metadata (default: False for concise list)
    
    Returns:
        str: Formatted list of skills in requested format
        
        Markdown format:
        # Available Claude Skills
        
        Found N skill(s)
        
        ## skill-name
        - Short description
        
        JSON format:
        {
          "total": N,
          "skills": [
            {
              "name": "skill-name",
              "description": "Description text",
              "metadata": {...},
              "directory": "/path/to/skill",
              "file_path": "/path/to/skill/SKILL.md"
            }
          ]
        }
    
    Examples:
        - Use when: "What skills are available?" -> List all discoverable skills
        - Use when: "Show me the mcp-builder skill" -> First list skills, then use startd8_get_skill_info
        - Don't use when: You need to execute a skill (use startd8_use_skill instead)
    
    Error Handling:
        - Returns empty list if no skills found
        - Provides guidance on where to add skills
        - Handles YAML parsing errors gracefully
    """
    try:
        skills = _find_skills()
        
        if params.response_format == ResponseFormat.MARKDOWN:
            result = _format_skills_markdown(skills, params.include_details)
        else:
            result = _format_skills_json(skills)
        
        # Check character limit
        if len(result) > CHARACTER_LIMIT:
            truncated_skills = skills[:max(1, len(skills) // 2)]
            result = _format_skills_markdown(truncated_skills, False) if params.response_format == ResponseFormat.MARKDOWN else _format_skills_json(truncated_skills)
            result += f"\n\n⚠️ Response truncated. Showing {len(truncated_skills)}/{len(skills)} skills. Use include_details=False for concise output."
        
        return result
    
    except Exception as e:
        return _handle_error(e)


@mcp.tool(
    name="startd8_get_skill_info",
    annotations={
        "title": "Get Skill Information",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False
    }
)
async def startd8_get_skill_info(params: GetSkillInput) -> str:
    """
    Get detailed information about a specific Claude Skill including its full instructions.
    
    This tool retrieves the complete SKILL.md content for a skill, which includes:
    - Skill metadata (name, version, author, tags)
    - Complete system prompt / agent instructions
    - Usage guidelines and examples
    - Implementation patterns and best practices
    
    Args:
        params (GetSkillInput): Parameters containing:
            - skill_name (str): Name or directory name of the skill
            - response_format (ResponseFormat): Output format
    
    Returns:
        str: Full skill information and instructions
        
        Markdown format returns the complete SKILL.md file content.
        JSON format returns structured metadata with instructions field.
    
    Examples:
        - Use when: "Show me the mcp-builder skill instructions"
        - Use when: "What does the html5-game-designer-pro skill do?"
        - Don't use when: Just listing available skills (use startd8_list_skills)
    
    Error Handling:
        - Returns "Skill not found" with suggestions if skill doesn't exist
        - Handles file read errors gracefully
    """
    try:
        skill = _find_skill_by_name(params.skill_name)
        
        if not skill:
            available_skills = _find_skills()
            skill_names = [s["name"] for s in available_skills]
            return f"Error: Skill '{params.skill_name}' not found.\n\nAvailable skills:\n" + "\n".join(f"- {name}" for name in skill_names)
        
        instructions = _load_skill_instructions(skill)
        
        if params.response_format == ResponseFormat.MARKDOWN:
            result = f"# Skill: {skill['name']}\n\n"
            result += f"**Description:** {skill['description']}\n\n"
            result += f"**Location:** `{skill['directory']}`\n\n"
            result += "---\n\n"
            result += instructions
        else:
            result = json.dumps({
                "name": skill["name"],
                "description": skill["description"],
                "metadata": skill["metadata"],
                "directory": skill["directory"],
                "instructions": instructions
            }, indent=2)
        
        # Check character limit
        if len(result) > CHARACTER_LIMIT:
            result = result[:CHARACTER_LIMIT]
            result += f"\n\n⚠️ Response truncated at {CHARACTER_LIMIT} characters. Instructions are very long."
        
        return result
    
    except Exception as e:
        return _handle_error(e)


@mcp.tool(
    name="startd8_use_skill",
    annotations={
        "title": "Use Skill-Based Agent",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True
    }
)
async def startd8_use_skill(params: UseSkillInput) -> str:
    """
    Generate a response using a Claude Skill-based agent.
    
    This tool loads a skill's instructions as the system prompt and generates a response
    using Claude with those instructions. The skill's SKILL.md file defines the agent's
    behavior, capabilities, and response patterns.
    
    The tool returns either JSON (with full metrics) or Markdown (human-readable summary)
    depending on the response_format parameter.
    
    Args:
        params (UseSkillInput): Parameters containing:
            - skill_name (str): Name of the skill to use
            - prompt (str): User prompt to send to the agent
            - model (Optional[str]): Claude model (default: claude-sonnet-4-6)
            - max_tokens (Optional[int]): Maximum response tokens (default: 16384)
            - track_response (bool): Store in Startd8 storage (default: True)
            - response_format (ResponseFormat): 'markdown' or 'json' (default: 'markdown')
    
    Returns:
        str: Agent's response as JSON or Markdown depending on response_format
        
        JSON format includes:
        {
          "skill_name": "...",
          "skill_directory": "...",
          "model": "...",
          "prompt": "...",
          "output": "...",
          "response_format": "json",
          "usage": {"input_tokens": ..., "output_tokens": ..., "total_tokens": ...},
          "timing": {"started_at": "...", "completed_at": "...", "latency_ms": ...},
          "sdk": {"version": null, "run_id": null, "provider": "anthropic"},
          "metadata": {},
          "error": null
        }
        
        Markdown format includes:
        # Response from <skill_name>
        **Model:** <model>
        **Tokens:** <input> in, <output> out (total <total>)
        **Latency:** <ms> ms
        ---
        <output>
    
    Examples:
        - Use when: "Use the mcp-builder skill to create a GitHub MCP server"
        - Use when: "Generate a game using html5-game-designer-pro"
        - Don't use when: Just viewing skill info (use startd8_get_skill_info)
    
    Error Handling:
        - Returns error if skill not found
        - Returns error if ANTHROPIC_API_KEY not set
        - Returns error if Anthropic SDK not installed
        - Provides actionable next steps in error messages
    """
    import time
    from datetime import datetime, timezone
    
    try:
        _log_request(
            "startd8_use_skill",
            {
                "skill_name": params.skill_name,
                "model": params.model,
                "response_format": params.response_format.value,
            },
        )
        # Find the skill
        skill = _find_skill_by_name(params.skill_name)
        
        if not skill:
            return f"Error: Skill '{params.skill_name}' not found. Use startd8_list_skills to see available skills."
        
        # Check for API key
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            return (
                "Error: ANTHROPIC_API_KEY environment variable not set.\n\n"
                "Fix options:\n"
                "- Put `ANTHROPIC_API_KEY=...` in a local `.env` (or `.env.local`) next to `run_mcp.sh`.\n"
                "- Or set it in your Cursor MCP server config env for `user-startd8`.\n\n"
                "Then restart the MCP server and try again."
            )
        
        # Load skill instructions
        instructions = _load_skill_instructions(skill)
        
        # Remove YAML frontmatter from instructions
        if instructions.startswith('---'):
            parts = instructions.split('---', 2)
            if len(parts) >= 3:
                instructions = parts[2].strip()
        
        try:
            agent_cls = _resolve_skill_agent_cls()
            _log(
                f"startd8_use_skill skill={skill['name']} model={params.model} "
                f"format={params.response_format} agent_cls={agent_cls}"
            )
            # Guard: if we resolved only the abstract alias, abort with a clear message.
            try:
                from startd8.skills.agent import SkillAgent as _ConcreteSkillAgent  # noqa: F401
                from startd8.skills.agent import ClaudeSkillAgent as _AliasClaudeAgent  # noqa: F401
            except Exception:
                _ConcreteSkillAgent = None
                _AliasClaudeAgent = None

            if agent_cls is not None and _AliasClaudeAgent is not None:
                if agent_cls is _AliasClaudeAgent and _ConcreteSkillAgent is not None:
                    msg = (
                        "Resolved ClaudeSkillAgent (abstract). Fix PYTHONPATH/STARTD8_SDK_PATH to use the SDK "
                        "that provides concrete SkillAgent. "
                        "Current agent_cls is abstract; refusing to instantiate."
                    )
                    _log(f"guard triggered: {msg}")
                    _log_response("startd8_use_skill", {"error": msg})
                    return _response(
                        error="invalid_params",
                        message=msg,
                        data={"hint": "Use /bin/sh -lc with PYTHONPATH pointing to the SDK source"},
                    )

            if FORCE_ANTHROPIC_FALLBACK:
                _log("STARTD8_FORCE_ANTHROPIC_FALLBACK=1 -> forcing Anthropic client path")
                agent_cls = None

            if agent_cls:
                started_at = datetime.now(timezone.utc)
                start_perf = time.perf_counter()
                try:
                    agent = agent_cls(
                        skill_id=skill["name"],
                        name=skill["name"],
                        model=params.model,
                        max_tokens=params.max_tokens,
                    )
                except Exception as e:
                    _log(f"agent instantiation failed: {e}")
                    raise
                try:
                    response_text, latency_ms, usage = agent.generate(params.prompt)
                except Exception as e:
                    _log(f"agent.generate failed: {e}")
                    raise
                completed_at = datetime.now(timezone.utc)
                _log(f"skill agent class={agent_cls} used SDK path")
            else:
                _log("falling back to anthropic client")
                import anthropic
                # Avoid Anthropic logging collision on 'name' field
                try:
                    import logging
                    # Ensure LogRecord creation drops reserved 'name' in extra before validation
                    _orig_factory = logging.getLogRecordFactory()
                    def _safe_record_factory(*args, **kwargs):
                        extra = kwargs.get("extra")
                        if isinstance(extra, dict) and "name" in extra:
                            extra = dict(extra)
                            extra.pop("name", None)
                            kwargs["extra"] = extra
                        try:
                            return _orig_factory(*args, **kwargs)
                        except Exception:
                            kwargs.pop("extra", None)
                            return _orig_factory(*args, **kwargs)
                    logging.setLogRecordFactory(_safe_record_factory)

                    # Also patch Logger.makeRecord to sanitize before LogRecord is constructed
                    _orig_make_record = logging.Logger.makeRecord
                    def _safe_make_record(self, name, level, fn, lno, msg, args, exc_info, func=None, extra=None, sinfo=None):
                        if isinstance(extra, dict) and "name" in extra:
                            extra = dict(extra)
                            extra.pop("name", None)
                        try:
                            return _orig_make_record(self, name, level, fn, lno, msg, args, exc_info, func, extra, sinfo)
                        except TypeError:
                            return _orig_make_record(self, name, level, fn, lno, msg, args, exc_info, func, None, sinfo)
                    logging.Logger.makeRecord = _safe_make_record  # type: ignore

                    # Patch Logger._log to strip before makeRecord is invoked
                    _orig_log = logging.Logger._log
                    def _safe_log(self, level, msg, args, exc_info=None, extra=None, stack_info=False, stacklevel=1):
                        if isinstance(extra, dict) and "name" in extra:
                            extra = dict(extra)
                            extra.pop("name", None)
                        return _orig_log(self, level, msg, args, exc_info=exc_info, extra=extra, stack_info=stack_info, stacklevel=stacklevel)
                    logging.Logger._log = _safe_log  # type: ignore

                    class _NoNameFilter(logging.Filter):
                        def filter(self, record):
                            record.__dict__.pop("name", None)
                            return True
                    root_logger = logging.getLogger()
                    for handler in root_logger.handlers:
                        if hasattr(handler, "addFilter"):
                            handler.addFilter(_NoNameFilter())
                    # Also clear Anthropic-specific handlers and prevent propagation
                    anth_logger = logging.getLogger("anthropic")
                    anth_logger.handlers.clear()
                    anth_logger.propagate = False
                    # Disable logging during the Anthropic call to bypass any remaining LogRecord validation
                    logging.disable(logging.CRITICAL)
                except Exception:
                    pass
                started_at = datetime.now(timezone.utc)
                start_perf = time.perf_counter()
                client = anthropic.Anthropic(api_key=api_key)
                message = None
                try:
                    logging.disable(logging.CRITICAL)
                    message = client.messages.create(
                        model=params.model,
                        max_tokens=params.max_tokens,
                        system=instructions,
                        messages=[
                            {"role": "user", "content": params.prompt}
                        ]
                    )
                finally:
                    logging.disable(logging.NOTSET)
                completed_at = datetime.now(timezone.utc)
                latency_ms = int((time.perf_counter() - start_perf) * 1000)
                response_text = message.content[0].text if message else ""
                usage = {
                    "input_tokens": getattr(message.usage, "input_tokens", None) if message else None,
                    "output_tokens": getattr(message.usage, "output_tokens", None) if message else None,
                    "total_tokens": None,
                }
                if usage["input_tokens"] is not None and usage["output_tokens"] is not None:
                    usage["total_tokens"] = usage["input_tokens"] + usage["output_tokens"]

            # Normalize usage across SDK/Anthropic return shapes (e.g., TokenUsage objects).
            usage = _normalize_token_usage(usage)

            started_at_iso = started_at.isoformat().replace("+00:00", "Z")
            completed_at_iso = completed_at.isoformat().replace("+00:00", "Z")

            result = {
                "skill_name": skill["name"],
                "skill_directory": skill.get("directory"),
                "model": params.model,
                "prompt": params.prompt,
                "output": response_text,
                "response_format": params.response_format.value,
                "usage": usage,
                "timing": {
                    "started_at": started_at_iso,
                    "completed_at": completed_at_iso,
                    "latency_ms": latency_ms,
                },
                "sdk": {
                    "version": None,
                    "run_id": None,
                    "provider": "anthropic",
                },
                "metadata": {},
                "error": None,
            }
            
            _log_response("startd8_use_skill", result)
            if params.response_format == ResponseFormat.JSON:
                return json.dumps(result, indent=2)
            else:
                lines = [
                    f"# Response from {result['skill_name']}",
                    "",
                    f"**Model:** {result['model']}",
                ]
                
                if result["usage"]["input_tokens"] is not None and result["usage"]["output_tokens"] is not None:
                    lines.append(
                        f"**Tokens:** {result['usage']['input_tokens']} in, "
                        f"{result['usage']['output_tokens']} out (total {result['usage']['total_tokens']})"
                    )
                
                lines.append(f"**Latency:** {result['timing']['latency_ms']} ms")
                lines.append("")
                lines.append("---")
                lines.append("")
                lines.append(result["output"])
                
                return "\n".join(lines)
        
        except ImportError:
            _log_response("startd8_use_skill", {"error": "anthropic not installed"})
            return "Error: Anthropic Python SDK not installed. Install with: pip install anthropic"
        
        except Exception as api_error:
            _log(f"startd8_use_skill exception: {api_error}")
            _log_response("startd8_use_skill", {"error": str(api_error)})
            return f"Error calling Claude API: {str(api_error)}\n\nMake sure your ANTHROPIC_API_KEY is valid."
    
    except Exception as e:
        _log(f"startd8_use_skill outer exception: {e}")
        _log_response("startd8_use_skill", {"error": str(e)})
        return _handle_error(e)


@mcp.tool(
    name="startd8_compare_agents",
    annotations={
        "title": "Compare Multiple Agents",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True
    }
)
async def startd8_compare_agents(params: CompareAgentsInput) -> str:
    """
    Compare responses from multiple agents on the same prompt.
    
    This tool sends the same prompt to multiple configured agents and compares their
    responses, providing metrics like response time, token usage, and output quality.
    
    NOTE: This is a placeholder implementation. Full implementation requires:
    1. Startd8 SDK installed and configured
    2. Agents configured in Startd8 (via startd8 tui)
    3. API keys for each agent provider
    
    Args:
        params (CompareAgentsInput): Parameters containing:
            - prompt (str): Prompt to send to all agents
            - agents (List[str]): Agent names (e.g., ['claude', 'gpt4', 'composer'])
            - response_format (ResponseFormat): Output format
    
    Returns:
        str: Comparison results with metrics
    
    Examples:
        - Use when: "Compare Claude and GPT-4 on this prompt: [prompt]"
        - Use when: "Benchmark different agents on code review task"
        - Don't use when: Only need one agent response (use startd8_use_skill)
    
    Error Handling:
        - Returns error if Startd8 SDK not available
        - Returns error if agents not configured
        - Provides setup instructions
    """
    try:
        return """Error: Agent comparison requires Startd8 SDK installation and configuration.

To set up:
1. Install Startd8: pip install startd8
2. Configure agents: startd8 tui
3. Set API keys for each provider:
   - ANTHROPIC_API_KEY for Claude
   - OPENAI_API_KEY for GPT-4
   - CURSOR_API_KEY for Composer

Then use this tool to compare agent responses on the same prompt.

For now, use startd8_use_skill to generate responses with individual skills."""
    
    except Exception as e:
        return _handle_error(e)


@mcp.tool(
    name="startd8_help",
    annotations={
        "title": "Startd8 MCP Help",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def startd8_help(params: HelpInput) -> str:
    """
    Explain what the Startd8 MCP server can do and how to use it.

    Use this when a user asks:
    - "What can startd8 do?"
    - "How do I use skills in Cursor?"
    - "Why aren't my skills showing up?"
    """
    topic = (params.topic or "").strip().lower()

    capabilities = {
        "skills": {
            "tools": [
                "startd8_list_skills",
                "startd8_get_skill_info",
                "startd8_use_skill",
            ],
            "notes": [
                "Skills are discovered from STARTD8_SKILL_PATH (colon-separated) plus default locations.",
                "You can run a skill by calling startd8_use_skill with skill_name + prompt.",
                "Optionally, this server can register one tool per skill (STARTD8_MCP_REGISTER_SKILL_TOOLS=1).",
            ],
        },
        "tasks": {
            "tools": [
                "tasks.list",
                "tasks.status",
                "tasks.run",
                "startd8_tasks_list",
                "startd8_tasks_status",
                "startd8_tasks_run",
            ],
            "notes": [
                "Tasks integrate with the Startd8 SDK task system and can produce dry-run diffs.",
            ],
        },
        "prompts": {
            "tools": [
                "startd8_create_prompt",
                "startd8_list_prompts",
                "startd8_get_prompt",
                "startd8_distribute_prompt",
                "startd8_compare_responses",
                "startd8_view_statistics",
            ],
            "notes": [
                "Prompts are stored/managed via the Startd8 SDK framework (if available).",
            ],
        },
        "agents": {
            "tools": [
                "startd8_list_agents",
                "startd8_test_agent_connection",
            ],
            "notes": [
                "Agents require Startd8 SDK configuration and provider credentials.",
            ],
        },
        "resources": {
            "resources": [
                "skill://{skill_name}",
                "skill://<skill-name> (concrete resources registered at startup)",
            ],
            "notes": [
                "Resources expose SKILL.md content for browsing.",
            ],
        },
        "diagnostics": {
            "tools": ["startd8_status"],
            "env": [
                "STARTD8_SKILL_PATH (skills discovery)",
                "STARTD8_SDK_PATH (Startd8 SDK import path)",
                "ANTHROPIC_API_KEY (required for startd8_use_skill)",
                "STARTD8_MCP_REGISTER_SKILL_TOOLS=1 (register per-skill convenience tools)",
                "STARTD8_MCP_MAX_SKILL_TOOLS=100 (cap per-skill tools)",
                "STARTD8_MCP_STARTUP_MAX_SKILLS=100 (cap startup indexing/registration)",
                "STARTD8_MCP_SKILL_CACHE_TTL_SECONDS=10 (cache skill discovery results)",
                "STARTD8_MCP_DEBUG=1 (verbose stderr logs)",
                "STARTD8_MCP_QUIET=1 (reduce startup banner/noise)",
            ],
        },
    }

    if params.response_format == ResponseFormat.JSON:
        payload = {
            "server": "startd8_mcp",
            "capabilities": capabilities,
            "quickstart": [
                {
                    "step": "List skills",
                    "tool": "startd8_list_skills",
                    "example_args": {"response_format": "markdown", "include_details": False},
                },
                {
                    "step": "Inspect a skill",
                    "tool": "startd8_get_skill_info",
                    "example_args": {"skill_name": "<skill>", "response_format": "markdown"},
                },
                {
                    "step": "Run a skill",
                    "tool": "startd8_use_skill",
                    "example_args": {
                        "skill_name": "<skill>",
                        "prompt": "<your prompt>",
                        "response_format": "markdown",
                    },
                },
                {
                    "step": "Check server status",
                    "tool": "startd8_status",
                    "example_args": {"response_format": "markdown"},
                },
            ],
        }
        if topic:
            payload["topic"] = topic
        return json.dumps(payload, indent=2)

    # Markdown mode
    sections: list[str] = []
    sections.append("# Startd8 MCP Help")
    sections.append("")
    sections.append("This server exposes Startd8 capabilities to MCP clients (like Cursor) via tools and resources.")
    sections.append("")
    sections.append("## Quickstart")
    sections.append("- Call `startd8_list_skills` to discover skills")
    sections.append("- Call `startd8_get_skill_info` to read a skill’s full instructions")
    sections.append("- Call `startd8_use_skill` to run a skill against your prompt")
    sections.append("- Call `startd8_status` if anything looks misconfigured")
    sections.append("")

    def _emit_topic(name: str) -> None:
        block = capabilities.get(name, {})
        sections.append(f"## {name.capitalize()}")
        if "tools" in block:
            sections.append("**Tools:**")
            for t in block["tools"]:
                sections.append(f"- `{t}`")
        if "resources" in block:
            sections.append("**Resources:**")
            for r in block["resources"]:
                sections.append(f"- `{r}`")
        if "env" in block:
            sections.append("**Environment:**")
            for e in block["env"]:
                sections.append(f"- `{e}`")
        notes = block.get("notes") or []
        if notes:
            sections.append("**Notes:**")
            for n in notes:
                sections.append(f"- {n}")
        sections.append("")

    if topic:
        if topic in capabilities:
            _emit_topic(topic)
        else:
            sections.append(f"Unknown topic: `{topic}`")
            sections.append("Valid topics: " + ", ".join(f"`{k}`" for k in sorted(capabilities.keys())))
            sections.append("")
    else:
        for t in ("skills", "tasks", "prompts", "agents", "resources", "diagnostics"):
            _emit_topic(t)

    return "\n".join(sections).rstrip() + "\n"


@mcp.tool(
    name="startd8_status",
    annotations={
        "title": "Startd8 MCP Status",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def startd8_status(params: StatusInput) -> str:
    """
    Return server diagnostics (skills discovery, SDK availability, startup errors).

    Use this for debugging configuration issues in MCP clients (e.g., Cursor).
    """
    # Best-effort SDK load so we can report accurate agent availability
    try:
        _ensure_sdk_available()
    except Exception:
        pass

    # Skills
    skills = []
    try:
        skills = _find_skills()
    except Exception:
        skills = []
    skill_names = [str(s.get("name", "unknown")) for s in skills]
    try:
        from collections import Counter
        dup_names = sorted([n for n, c in Counter(skill_names).items() if c > 1])
    except Exception:
        dup_names = []

    # SDK + agent
    try:
        import startd8  # noqa: F401
        startd8_loaded = True
        startd8_path = getattr(startd8, "__file__", None)
    except Exception as e:
        startd8_loaded = False
        startd8_path = str(e)

    agent_cls = globals().get("SkillAgentConcrete") or globals().get("ClaudeSkillAgent")

    info: Dict[str, Any] = {
        "server": {"name": "startd8_mcp"},
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "flags": {
            "debug": MCP_DEBUG,
            "quiet": MCP_QUIET,
            "register_skill_tools": MCP_REGISTER_SKILL_TOOLS,
            "max_skill_tools": MCP_MAX_SKILL_TOOLS,
        },
        "env": {
            "PROJECT_ROOT": str(DEFAULT_PROJECT_ROOT),
            "STARTD8_SDK_PATH": os.getenv("STARTD8_SDK_PATH", ""),
            "STARTD8_SKILL_PATH": os.getenv("STARTD8_SKILL_PATH", ""),
            "STARTD8_SKILL_PATH_SECONDARY": os.getenv("STARTD8_SKILL_PATH_SECONDARY", ""),
            "STARTD8_SKILL_PATH_SECONDARY_ENABLED": _env_flag("STARTD8_SKILL_PATH_SECONDARY_ENABLED", default=False),
            "ANTHROPIC_API_KEY_SET": bool(os.getenv("ANTHROPIC_API_KEY")),
            "DEFAULT_AGENT": DEFAULT_AGENT_NAME,
            "ALLOWED_AGENTS": sorted(ALLOWED_AGENTS),
            "ALLOW_AUTO_DEPS": ALLOW_AUTO_DEPS,
            "AUTO_MAX_DEPTH": AUTO_MAX_DEPTH,
            "AUTO_MAX_TASKS": AUTO_MAX_TASKS,
        },
        "sdk": {
            "startd8_loaded": startd8_loaded,
            "startd8_path": startd8_path,
            "sdk_search_paths": [str(p) for p in DEFAULT_SDK_PATHS if p],
            "agent_class": str(agent_cls),
            "force_anthropic_fallback": FORCE_ANTHROPIC_FALLBACK,
        },
        "skills": {
            "count": len(skills),
            "directories": [str(p) for p in _get_skill_directories()],
            "duplicate_names": dup_names,
        },
        "startup": {
            "skills_indexed": STARTUP_SKILLS_INDEXED,
            "skills_index_limit": STARTUP_SKILLS_INDEX_LIMIT,
            "skills_index_skipped": STARTUP_SKILLS_INDEX_SKIPPED,
            "metrics": dict(STARTUP_METRICS),
        },
        "resources": {
            "concrete_skill_resources_registered": len(_CONCRETE_RESOURCE_URIS),
        },
        "startup_errors": list(STARTUP_ERRORS),
    }

    # These sets are populated at startup only (when running as a server).
    if "_CONCRETE_SKILL_TOOL_NAMES" in globals():
        try:
            info["tools"] = {"concrete_skill_tools_registered": len(_CONCRETE_SKILL_TOOL_NAMES)}
        except Exception:
            pass

    if params.include_skill_names:
        info["skills"]["names"] = skill_names

    if params.include_pythonpath:
        info["pythonpath"] = list(sys.path)

    if params.response_format == ResponseFormat.JSON:
        return json.dumps(info, indent=2)

    # Markdown format
    lines: list[str] = []
    lines.append("# Startd8 MCP Status")
    lines.append("")
    lines.append("## Summary")
    lines.append(f"- **Skills discovered:** {info['skills']['count']}")
    lines.append(f"- **Startd8 SDK importable:** {startd8_loaded}")
    lines.append(f"- **Resolved skill agent class:** `{agent_cls}`")
    lines.append(f"- **Startup errors:** {len(STARTUP_ERRORS)}")
    lines.append("")
    lines.append("## Key environment")
    lines.append(f"- **PROJECT_ROOT:** `{info['env']['PROJECT_ROOT']}`")
    lines.append(f"- **STARTD8_SKILL_PATH:** `{info['env']['STARTD8_SKILL_PATH']}`")
    lines.append(f"- **STARTD8_SDK_PATH:** `{info['env']['STARTD8_SDK_PATH']}`")
    lines.append(f"- **DEFAULT_AGENT:** `{info['env']['DEFAULT_AGENT']}`")
    lines.append("")
    lines.append("## Skills")
    if not skills:
        lines.append("- No skills found. Set `STARTD8_SKILL_PATH` to a directory that contains subfolders with `SKILL.md`.")
    else:
        if dup_names:
            lines.append(f"- Duplicate skill names detected: {', '.join(f'`{n}`' for n in dup_names)}")
        if params.include_skill_names:
            preview = skill_names[:50]
            lines.append(f"- Names (first {len(preview)}/{len(skill_names)}): " + ", ".join(f"`{n}`" for n in preview))
    lines.append("")
    lines.append("## Resources / Tools")
    lines.append(f"- Concrete `skill://...` resources registered: {len(_CONCRETE_RESOURCE_URIS)}")
    if "_CONCRETE_SKILL_TOOL_NAMES" in globals():
        try:
            lines.append(f"- Concrete per-skill tools registered: {len(_CONCRETE_SKILL_TOOL_NAMES)}")
        except Exception:
            pass
    lines.append("")
    if STARTUP_ERRORS:
        lines.append("## Startup errors")
        for i, err in enumerate(STARTUP_ERRORS, start=1):
            lines.append(f"{i}. {err}")
        lines.append("")
    lines.append("## Tips")
    lines.append("- Set `STARTD8_MCP_DEBUG=1` to enable verbose stderr logs.")
    lines.append("- Set `STARTD8_MCP_QUIET=1` to reduce startup banner/noise.")
    lines.append("- If skills are missing, verify `STARTD8_SKILL_PATH` and permissions, then restart the server.")
    lines.append("")
    return "\n".join(lines)


@mcp.tool(
    name="startd8_concierge",
    annotations={
        "title": "Startd8 Concierge (onboarding assist)",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def startd8_concierge(params: ConciergeInput) -> str:
    """Project-side SDK-onboarding assist (read-only, $0, no LLM).

    Actions:
      - ``survey``: brownfield triage of a project — requirement/PRD docs (+ extraction-format
        match), Pydantic model files, test-fixture candidates, personal/PII risk flags.
      - ``assess``: onboarding-readiness report — kickoff-input provenance per domain + the
        $0-cascade view (entities/CRUD/readiness), wrapping ``startd8 wireframe``.

    Posture: assists, never operates. It never runs the cascade, records a gate, or writes to
    disk — writes are the CLI's job (``startd8 concierge … --apply``), run at human privilege.
    """
    request_id = _new_request_id()
    started = time.perf_counter()
    action = getattr(params.action, "value", str(params.action))
    project_root = params.project_root or str(DEFAULT_PROJECT_ROOT)
    _emit_event({
        "event": "tool.start", "tool": "startd8_concierge", "request_id": request_id,
        "params": {"action": action, "project_root": project_root},
    })
    extra = {"with_authoring": params.with_authoring}
    for _f in ("posture", "friction", "what_happened", "implication"):
        _v = getattr(params, _f, None)
        if _v is not None:
            extra[_f] = _v
    try:
        with _redirect_stdout_to_stderr():
            _ensure_sdk_available()
            from startd8.concierge import handle_concierge_tool
            result = handle_concierge_tool(action, project_root, **extra)
        _emit_event({
            "event": "tool.end", "tool": "startd8_concierge", "request_id": request_id,
            "duration_ms": int((time.perf_counter() - started) * 1000),
            "status": "ok", "action": action,
        })
        return json.dumps(result, indent=2)
    except Exception as e:
        _emit_event({
            "event": "tool.end", "tool": "startd8_concierge", "request_id": request_id,
            "duration_ms": int((time.perf_counter() - started) * 1000),
            "status": "error", "error_type": type(e).__name__, "error": str(e),
        })
        return _handle_error(e)


@mcp.tool(
    name="startd8_tasks_list",
    annotations={
        "title": "List Tasks (Startd8-prefixed)",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def startd8_tasks_list(params: TaskListInput) -> str:
    """Alias for `tasks.list` (client-friendly prefixed name)."""
    return await tasks_list(params)


@mcp.tool(
    name="startd8_tasks_status",
    annotations={
        "title": "Task Status (Startd8-prefixed)",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def startd8_tasks_status(params: TaskStatusInput) -> str:
    """Alias for `tasks.status` (client-friendly prefixed name)."""
    return await tasks_status(params)


@mcp.tool(
    name="startd8_tasks_run",
    annotations={
        "title": "Execute Task (Startd8-prefixed)",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
async def startd8_tasks_run(params: TaskRunInput) -> str:
    """Alias for `tasks.run` (client-friendly prefixed name)."""
    return await tasks_run(params)


@mcp.tool(
    name="tasks.list",
    annotations={
        "title": "List Tasks",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def tasks_list(params: TaskListInput) -> str:
    """List parsed tasks with metadata."""
    try:
        path = _resolve_path(params.file, DEFAULT_TASK_LIST_PATH)
        mgr, tasks, task_map, modules = _load_tasks(path)
        return json.dumps(
            {"file": str(path), "tasks": [_serialize_task(t) for t in tasks]},
            indent=2,
        )
    except ImportError as e:
        return f"Error: {e}"
    except Exception as e:
        return f"Error listing tasks: {e}"


@mcp.tool(
    name="tasks.status",
    annotations={
        "title": "Task Status Summary",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def tasks_status(params: TaskStatusInput) -> str:
    """Return task status counts, including runnable."""
    try:
        path = _resolve_path(params.file, DEFAULT_TASK_LIST_PATH)
        mgr, tasks, task_map, modules = _load_tasks(path)
        TaskStatus = modules["TaskStatus"]
        counts = _status_counts(tasks, task_map, TaskStatus)
        return json.dumps({"file": str(path), "counts": counts}, indent=2)
    except ImportError as e:
        return f"Error: {e}"
    except Exception as e:
        return f"Error getting task status: {e}"


@mcp.tool(
    name="tasks.run",
    annotations={
        "title": "Execute Task (dry-run/apply)",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
async def tasks_run(params: TaskRunInput) -> str:
    """
    Validate and execute tasks with dry-run/apply and auto-deps.
    """
    try:
        path = _resolve_path(params.file, DEFAULT_TASK_LIST_PATH)
        mgr, tasks, task_map, modules = _load_tasks(path)
        TaskStatus = modules["TaskStatus"]
        ActionParser = modules["ActionParser"]
        ActionApplicator = modules["ActionApplicator"]
        PromptBuilder = modules["PromptBuilder"]
        ProviderRegistry = modules["ProviderRegistry"]

        cycle = _detect_cycles(task_map)
        if cycle:
            return _response(
                error="invalid_params",
                message=f"Dependency cycle detected: {' -> '.join(cycle)}",
                data={"cycle": cycle},
            )

        agent_name = (params.agent or DEFAULT_AGENT_NAME).lower()
        if agent_name not in ALLOWED_AGENTS:
            return _response(
                error="invalid_params",
                message=f"Agent '{agent_name}' not allowed",
                data={"allowed_agents": sorted(ALLOWED_AGENTS)},
            )

        if ProviderRegistry is None:
            return _response(error="internal", message="Provider registry unavailable")

        try:
            ProviderRegistry.discover()
            provider = ProviderRegistry.get_provider(agent_name)
        except Exception as e:
            provider = None
        if provider is None:
            return _response(
                error="invalid_params",
                message=f"Agent/provider '{agent_name}' not available",
            )

        model = provider.supported_models[0] if getattr(provider, "supported_models", None) else None
        if not model:
            return _response(
                error="invalid_params",
                message=f"No models configured for provider '{agent_name}'",
            )

        def build_plan(task, depth=0, order=None, visited=None):
            if order is None:
                order = []
            if visited is None:
                visited = set()
            if len(order) >= AUTO_MAX_TASKS:
                raise RuntimeError("auto_deps_limit")
            if depth > AUTO_MAX_DEPTH:
                raise RuntimeError("auto_depth_limit")
            visited.add(task.id)
            for dep_id in getattr(task, "dependencies", []):
                dep_task = task_map.get(dep_id)
                if not dep_task:
                    raise ValueError(f"Unknown dependency: {dep_id}")
                if getattr(dep_task, "status", None) == TaskStatus.COMPLETED:
                    continue
                if dep_id in visited:
                    raise ValueError(f"Dependency cycle detected at {dep_id}")
                if params.auto:
                    build_plan(dep_task, depth + 1, order, visited)
                else:
                    raise RuntimeError(f"Dependencies not completed: {dep_id}")
            if task.id not in order and getattr(task, "status", None) != TaskStatus.COMPLETED:
                order.append(task.id)
            return order

        try:
            root_task = _select_task(tasks, params.id, TaskStatus)
        except Exception as e:
            return _response(error="invalid_params", message=str(e))

        if getattr(root_task, "status", None) == TaskStatus.BLOCKED:
            return _response(
                error="failed_precondition",
                message=f"Task {root_task.id} is blocked",
                data={"task": root_task.id, "status": getattr(root_task, "status", None).value if getattr(root_task, "status", None) else None},
            )

        try:
            execution_order = build_plan(root_task)
        except RuntimeError as e:
            extra = {}
            if "auto_deps_limit" in str(e):
                extra = {"order": execution_order if "execution_order" in locals() else []}
                msg = f"Auto-dependency limit exceeded ({len(extra.get('order', []))}/{AUTO_MAX_TASKS})"
            elif "auto_depth_limit" in str(e):
                extra = {"order": execution_order if "execution_order" in locals() else []}
                msg = f"Auto-dependency depth exceeded ({AUTO_MAX_DEPTH})"
            else:
                msg = str(e)
            return _response(
                error="failed_precondition",
                message=msg,
                data=extra,
            )
        except ValueError as e:
            return _response(error="invalid_params", message=str(e))

        results = []
        modified_files: List[str] = []
        all_diffs: List[Dict[str, Any]] = []

        for task_id in execution_order:
            current_task = task_map[task_id]
            prompt = PromptBuilder(task_list_path=str(path)).build(current_task)
            try:
                agent = provider.create_agent(model=model, name=agent_name)
            except Exception as e:
                return _response(
                    error="internal",
                    message=f"Agent creation failed: {e}",
                    data={"task": task_id},
                )

            try:
                response, _, usage = agent.generate(prompt)
            except Exception as e:
                return _response(
                    error="internal",
                    message=f"Agent call failed: {e}",
                    data={"task": task_id},
                )

            try:
                actions = ActionParser().parse(response)
            except Exception as e:
                return _response(
                    error="invalid_params",
                    message=f"Parser error: {e}",
                    data={"task": task_id},
                )

            # Validate and normalize action paths before diff/apply.
            try:
                for action in actions:
                    action.path = str(_validate_action_path(action.path))
            except Exception as e:
                return _response(
                    error="invalid_params",
                    message=f"Invalid action path: {e}",
                    data={"task": task_id},
                )

            applicator = ActionApplicator(project_root=DEFAULT_PROJECT_ROOT)
            dry_result = applicator.apply_actions(actions, dry_run=True)
            diffs = _compute_diffs(actions)
            all_diffs.extend(diffs)

            if not dry_result.success:
                _write_audit_log(
                    {
                        "action": "tasks.run",
                        "task_id": task_id,
                        "agent": agent_name,
                        "dry_run": True,
                        "result": "failed",
                        "error": dry_result.message,
                        "files": dry_result.modified_files,
                    }
                )
                return _response(
                    error="failed_precondition",
                    message=f"Dry run failed: {dry_result.message}",
                    data={"files": dry_result.modified_files, "task": task_id},
                )

            if params.dry_run:
                results.append(
                    {
                        "task": _serialize_task(current_task),
                        "dry_run": True,
                        "files": dry_result.modified_files,
                        "diffs": diffs,
                        "agent": {"name": agent_name, "provider": getattr(provider, "name", agent_name), "model": model},
                    }
                )
                modified_files.extend(dry_result.modified_files)
                continue

            apply_result = applicator.apply_actions(actions, dry_run=False)
            if not apply_result.success:
                _write_audit_log(
                    {
                        "action": "tasks.run",
                        "task_id": task_id,
                        "agent": agent_name,
                        "dry_run": False,
                        "result": "failed",
                        "error": apply_result.message,
                        "files": apply_result.modified_files,
                    }
                )
                return _response(
                    error="internal",
                    message=f"Execution failed: {apply_result.message}",
                    data={"files": apply_result.modified_files, "task": task_id},
                )

            try:
                mgr.update_status(task_id, TaskStatus.COMPLETED)
                mgr.add_work_log(task_id, f"Executed via MCP agent '{agent_name}'")
            except Exception:
                pass

            modified_files.extend(apply_result.modified_files)
            results.append(
                {
                    "task": _serialize_task(mgr.get_task(task_id)),
                    "dry_run": False,
                    "files": apply_result.modified_files,
                    "diffs": diffs,
                    "agent": {"name": agent_name, "provider": getattr(provider, "name", agent_name), "model": model},
                }
            )
            _write_audit_log(
                {
                    "action": "tasks.run",
                    "task_id": task_id,
                    "agent": agent_name,
                    "dry_run": False,
                    "result": "completed",
                    "files": apply_result.modified_files,
                }
            )

        return _response(
            error=None,
            message="Dry-run complete" if params.dry_run else "Execution complete",
            dry_run=params.dry_run,
            file=str(path),
            execution_order=execution_order,
            results=results,
            modified_files=modified_files,
            diffs=all_diffs,
        )
    except ImportError as e:
        return _response(error="internal", message=str(e))
    except Exception as e:
        return _response(error="internal", message=f"Error running task: {e}")


# ═══════════════════════════════════════════════════════════════
# MCP RESOURCES
# ═══════════════════════════════════════════════════════════════

@mcp.resource("skill://{skill_name}")
async def get_skill_resource(skill_name: str) -> str:
    """
    Expose Claude Skills as MCP resources.
    
    Resources provide efficient, template-based access to skill definitions.
    Use URI format: skill://skill-name or skill://directory-name
    """
    try:
        _log(f"get_skill_resource called with skill_name='{skill_name}'")
        skill = _find_skill_by_name(skill_name)
        
        if not skill:
            _log(f"Skill '{skill_name}' not found")
            return f"Error: Skill '{skill_name}' not found"
        
        instructions = _load_skill_instructions(skill)
        _log(f"Successfully loaded resource for skill '{skill_name}'")
        return instructions
    
    except Exception as e:
        error_msg = f"Error loading skill resource: {str(e)}"
        _log(f"get_skill_resource error for '{skill_name}': {e}")
        import traceback
        _log(f"Traceback: {traceback.format_exc()}")
        return error_msg


# -----------------------------------------------------------------------------
# Concrete resources (to make list_resources() non-empty in clients like Cursor)
# -----------------------------------------------------------------------------
_CONCRETE_RESOURCE_URIS: set[str] = set()


# -----------------------------------------------------------------------------
# Concrete per-skill tools (so clients can call a skill directly)
# -----------------------------------------------------------------------------
_CONCRETE_SKILL_TOOL_NAMES: set[str] = set()


def _normalize_skill_tool_suffix(name: str) -> str:
    """
    Normalize a skill name/dir for use in a tool name suffix.
    Produces a conservative lowercase identifier (letters/digits/underscore).
    """
    n = (name or "").strip().lower()
    n = n.replace("{", "").replace("}", "")
    n = re.sub(r"[^a-z0-9]+", "_", n)
    n = n.strip("_")
    if not n:
        n = "skill"
    if n[0].isdigit():
        n = f"skill_{n}"
    return n


def _register_concrete_skill_tools(skills: Optional[List[Dict[str, Any]]] = None) -> int:
    """
    Register one tool per skill for easier discovery in clients.

    Each generated tool is a thin wrapper around `startd8_use_skill` with the skill name pre-filled.
    Controlled by:
      - STARTD8_MCP_REGISTER_SKILL_TOOLS (default: true)
      - STARTD8_MCP_MAX_SKILL_TOOLS (default: 100)
    """
    if not MCP_REGISTER_SKILL_TOOLS:
        return 0

    try:
        skills = skills or _find_skills()
        added = 0
        for skill in skills[: max(0, MCP_MAX_SKILL_TOOLS)]:
            try:
                # Prefer directory name for stable identifiers
                base = ""
                try:
                    base = Path(skill.get("directory", "")).name
                except Exception:
                    base = ""
                raw_name = (base or skill.get("name") or "").strip()
                if not raw_name:
                    continue

                suffix = _normalize_skill_tool_suffix(raw_name)
                tool_name = f"startd8_skill_{suffix}"

                # Ensure uniqueness
                final_name = tool_name
                if final_name in _CONCRETE_SKILL_TOOL_NAMES:
                    n = 2
                    while f"{tool_name}_{n}" in _CONCRETE_SKILL_TOOL_NAMES:
                        n += 1
                    final_name = f"{tool_name}_{n}"

                # Use directory name as lookup key when possible
                lookup_name = raw_name
                display_name = str(skill.get("name") or raw_name)
                display_desc = str(skill.get("description") or "Skill")

                async def _tool_fn(params: SkillPromptInput, _lookup: str = lookup_name) -> str:
                    """Run this specific skill against a prompt."""
                    try:
                        inner = UseSkillInput(
                            skill_name=_lookup,
                            prompt=params.prompt,
                            model=params.model,
                            max_tokens=params.max_tokens,
                            track_response=params.track_response,
                            response_format=params.response_format,
                        )
                    except Exception as e:
                        return _handle_error(e)
                    return await startd8_use_skill(inner)

                _tool_fn.__name__ = final_name
                _tool_fn.__doc__ = (
                    f"Run the '{display_name}' skill.\n\n"
                    f"Description: {display_desc}\n\n"
                    "This is a convenience wrapper around `startd8_use_skill` with the skill preselected."
                )

                mcp.tool(
                    name=final_name,
                    annotations={
                        "title": f"Skill: {display_name}",
                        "readOnlyHint": False,
                        "destructiveHint": False,
                        "idempotentHint": False,
                        "openWorldHint": True,
                    },
                )(_tool_fn)

                _CONCRETE_SKILL_TOOL_NAMES.add(final_name)
                added += 1
            except Exception as e:
                _log(f"Failed to register skill tool for {skill}: {e}")
                continue

        if len(skills) > MCP_MAX_SKILL_TOOLS:
            _log(
                f"Skill tool registration capped at {MCP_MAX_SKILL_TOOLS} "
                f"(found {len(skills)} skills). Increase STARTD8_MCP_MAX_SKILL_TOOLS to register more."
            )
        return added
    except Exception as e:
        _record_startup_error(f"Failed to register concrete skill tools: {e}")
        _log(f"Failed to register concrete skill tools: {e}")
        return 0


def _normalize_skill_uri_name(name: str) -> str:
    """
    Normalize a skill name for use in a concrete URI like `skill://<name>`.
    Keep it conservative so clients don't choke on spaces/braces.
    """
    n = (name or "").strip()
    # Avoid template syntax collisions and whitespace.
    n = n.replace("{", "").replace("}", "").replace(" ", "-")
    return n


def _register_concrete_skill_resources(skills: Optional[List[Dict[str, Any]]] = None) -> int:
    """
    Register `skill://<skill>` concrete resources for each discoverable skill.

    Why: some clients only surface list_resources() (not list_resource_templates()).
    """
    try:
        skills = skills or _find_skills()
        added = 0
        for skill in skills:
            # Prefer directory name for stable URIs; fall back to declared name.
            try:
                base = Path(skill.get("directory", "")).name
            except Exception:
                base = ""
            raw_name = (base or skill.get("name") or "").strip()
            if not raw_name:
                continue

            uri_base = _normalize_skill_uri_name(raw_name) or "skill"
            uri = f"skill://{uri_base}"
            # Ensure uniqueness (clients like Cursor expect unique URIs).
            if uri in _CONCRETE_RESOURCE_URIS:
                n = 2
                while f"{uri}-{n}" in _CONCRETE_RESOURCE_URIS:
                    n += 1
                uri = f"{uri}-{n}"

            file_path = str(skill.get("file_path", "")).strip()

            # Give each concrete resource a stable, unique display name/description
            # in `resources/list`. FastMCP uses the function name/docstring for these.
            uri_name = uri.split("://", 1)[-1]
            display_name = str(skill.get("name") or raw_name).strip() or uri_name
            display_desc = str(skill.get("description") or "").strip()
            fn_name = f"skill_{_normalize_skill_tool_suffix(uri_name)}"

            def _make_resource_fn(fp: str, fallback_name: str, *, fn_name: str, display_name: str, display_desc: str):
                async def _resource_fn() -> str:
                    try:
                        if fp:
                            return Path(fp).read_text(encoding="utf-8")
                    except Exception as e:
                        return f"Error loading skill resource: {e}"
                    return await get_skill_resource(fallback_name)

                try:
                    _resource_fn.__name__ = fn_name
                except Exception:
                    pass
                try:
                    _resource_fn.__doc__ = (f"{display_name}\n\n{display_desc}".strip() if display_desc else display_name)
                except Exception:
                    pass
                return _resource_fn

            resource_fn = _make_resource_fn(
                file_path,
                str(skill.get("name") or raw_name),
                fn_name=fn_name,
                display_name=display_name,
                display_desc=display_desc,
            )

            mcp.resource(uri)(resource_fn)
            _CONCRETE_RESOURCE_URIS.add(uri)
            added += 1
        return added
    except Exception as e:
        _record_startup_error(f"Failed to register concrete skill resources: {e}")
        _log(f"Failed to register concrete skill resources: {e}")
        return 0


# Note: FastMCP automatically handles list_resources() by enumerating
# registered resources. The error handling in _find_skills() ensures
# that resource enumeration doesn't fail even if skill discovery encounters errors.


# ═══════════════════════════════════════════════════════════════
# SDK FRAMEWORK HELPERS
# ═══════════════════════════════════════════════════════════════

def _get_framework():
    """Get or create AgentFramework instance."""
    if not _ensure_sdk_available():
        raise ImportError("Startd8 SDK not available. Set STARTD8_SDK_PATH.")
    from startd8 import AgentFramework
    storage_dir = Path(os.getenv("STARTD8_STORAGE_DIR", Path.home() / ".startd8"))
    return AgentFramework(storage_dir)


# ═══════════════════════════════════════════════════════════════
# TUI CAPABILITIES VIA MCP - INPUT MODELS
# ═══════════════════════════════════════════════════════════════

class CreatePromptInput(BaseModel):
    """Input for creating a prompt."""
    model_config = ConfigDict(str_strip_whitespace=True, extra='forbid')
    content: str = Field(..., description="Prompt content", min_length=1, max_length=100000)
    version: str = Field(default="1.0.0", description="Version identifier")
    tags: List[str] = Field(default_factory=list, description="Tags for categorization")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


class ListPromptsInput(BaseModel):
    """Input for listing prompts."""
    model_config = ConfigDict(str_strip_whitespace=True, extra='forbid')
    tags: Optional[List[str]] = Field(default=None, description="Filter by tags")
    page: Optional[int] = Field(default=None, ge=1, description="Page number (1-indexed)")
    page_size: int = Field(default=50, ge=1, le=1000, description="Items per page")
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


class DistributePromptInput(BaseModel):
    """Input for distributing a prompt to agents."""
    model_config = ConfigDict(str_strip_whitespace=True, extra='forbid')
    prompt_id: str = Field(..., description="Prompt ID to distribute", min_length=1)
    agents: Optional[List[str]] = Field(default=None, description="Agent names (None = all available)")
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


class CompareResponsesInput(BaseModel):
    """Input for comparing responses."""
    model_config = ConfigDict(str_strip_whitespace=True, extra='forbid')
    prompt_id: str = Field(..., description="Prompt ID to compare responses for", min_length=1)
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


class RunBenchmarkInput(BaseModel):
    """Input for running a benchmark."""
    model_config = ConfigDict(str_strip_whitespace=True, extra='forbid')
    prompt_id: str = Field(..., description="Prompt ID to benchmark", min_length=1)
    name: str = Field(..., description="Benchmark name", min_length=1)
    agents: List[str] = Field(..., min_length=1, description="Agent names to test")
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


class ViewStatisticsInput(BaseModel):
    """Input for viewing statistics."""
    model_config = ConfigDict(str_strip_whitespace=True, extra='forbid')
    prompt_id: Optional[str] = Field(default=None, description="Filter by prompt ID")
    agent_name: Optional[str] = Field(default=None, description="Filter by agent name")
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


# ═══════════════════════════════════════════════════════════════
# TUI CAPABILITIES VIA MCP - TOOLS
# ═══════════════════════════════════════════════════════════════

@mcp.tool(
    name="startd8_create_prompt",
    annotations={
        "title": "Create Prompt",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
    }
)
async def startd8_create_prompt(params: CreatePromptInput) -> str:
    """Create a new versioned prompt in the Startd8 framework."""
    try:
        framework = _get_framework()
        prompt = framework.create_prompt(
            content=params.content,
            version=params.version,
            tags=params.tags,
            metadata=params.metadata
        )
        
        result = {
            "prompt_id": prompt.id,
            "version": prompt.version,
            "tags": prompt.tags,
            "created": prompt.timestamp.isoformat(),
            "content_preview": prompt.content[:100] + "..." if len(prompt.content) > 100 else prompt.content
        }
        
        if params.response_format == ResponseFormat.JSON:
            return json.dumps(result, indent=2)
        else:
            return f"""# Prompt Created Successfully

**Prompt ID:** `{prompt.id}`
**Version:** {prompt.version}
**Tags:** {', '.join(prompt.tags) if prompt.tags else 'None'}
**Created:** {prompt.timestamp}

**Content Preview:**
{prompt.content[:200]}{'...' if len(prompt.content) > 200 else ''}

Use `startd8_distribute_prompt` to send this prompt to agents.
"""
    except Exception as e:
        return _handle_error(e)


@mcp.tool(
    name="startd8_list_prompts",
    annotations={
        "title": "List Prompts",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
    }
)
async def startd8_list_prompts(params: ListPromptsInput) -> str:
    """List all prompts, optionally filtered by tags."""
    try:
        framework = _get_framework()
        prompts = framework.list_prompts(tags=params.tags, page=params.page, page_size=params.page_size)
        
        if isinstance(prompts, dict):  # PaginatedResult
            prompt_list = prompts.get('items', [])
            total = prompts.get('total', len(prompt_list))
        else:
            prompt_list = prompts
            total = len(prompt_list)
        
        if params.response_format == ResponseFormat.JSON:
            return json.dumps({
                "total": total,
                "prompts": [{
                    "id": p.id,
                    "version": p.version,
                    "tags": p.tags,
                    "created": p.timestamp.isoformat(),
                    "content_preview": p.content[:100] + "..." if len(p.content) > 100 else p.content
                } for p in prompt_list]
            }, indent=2)
        else:
            if not prompt_list:
                return "No prompts found."
            lines = [f"# Prompts ({total} total)", ""]
            for p in prompt_list:
                lines.append(f"## {p.id[:12]}...")
                lines.append(f"- **Version:** {p.version}")
                lines.append(f"- **Tags:** {', '.join(p.tags) if p.tags else 'None'}")
                lines.append(f"- **Created:** {p.timestamp}")
                lines.append(f"- **Preview:** {p.content[:100]}{'...' if len(p.content) > 100 else ''}")
                lines.append("")
            return "\n".join(lines)
    except Exception as e:
        return _handle_error(e)


@mcp.tool(
    name="startd8_distribute_prompt",
    annotations={
        "title": "Distribute Prompt to Agents",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
    }
)
async def startd8_distribute_prompt(params: DistributePromptInput) -> str:
    """Distribute a prompt to one or more agents and get responses."""
    try:
        framework = _get_framework()
        prompt = framework.get_prompt(params.prompt_id)
        
        if not prompt:
            return f"Error: Prompt '{params.prompt_id}' not found."
        
        # Get agents
        try:
            # Startd8 SDK v1+: AgentRegistry lives in job_queue
            from startd8.job_queue import AgentRegistry
        except ImportError:
            try:
                # Older/alternate layouts
                from startd8.agents import AgentRegistry
            except ImportError:
                # Final fallback for alternate package layouts
                from startd8 import AgentRegistry
        registry = AgentRegistry()
        
        agent_names = params.agents if params.agents else registry.list_agents()
        if not agent_names:
            return "Error: No agents available. Configure agents first."
        
        results = []
        for agent_name in agent_names:
            try:
                agent = registry.get_agent(agent_name)
                if not agent:
                    results.append({"agent": agent_name, "status": "not_found", "error": f"Agent '{agent_name}' not found"})
                    continue
                
                # Generate response
                response_text, response_time_ms, token_usage = agent.generate(prompt.content)
                
                # Record response
                response = framework.record_response(
                    prompt_id=prompt.id,
                    agent_name=agent.name,
                    model=agent.model,
                    response=response_text,
                    response_time_ms=response_time_ms,
                    token_usage=token_usage
                )
                
                results.append({
                    "agent": agent_name,
                    "status": "success",
                    "response_id": response.id,
                    "response_time_ms": response_time_ms,
                    "token_usage": {
                        "input": token_usage.input if token_usage else None,
                        "output": token_usage.output if token_usage else None,
                        "total": token_usage.total if token_usage else None
                    }
                })
            except Exception as e:
                results.append({"agent": agent_name, "status": "error", "error": str(e)})
        
        if params.response_format == ResponseFormat.JSON:
            return json.dumps({"prompt_id": prompt.id, "results": results}, indent=2)
        else:
            lines = [f"# Prompt Distribution Results", "", f"**Prompt ID:** `{prompt.id}`", ""]
            for r in results:
                if r["status"] == "success":
                    lines.append(f"## ✅ {r['agent']}")
                    lines.append(f"- Response ID: `{r['response_id']}`")
                    lines.append(f"- Response Time: {r['response_time_ms']}ms")
                    if r.get('token_usage'):
                        lines.append(f"- Tokens: {r['token_usage'].get('total', 'N/A')}")
                else:
                    lines.append(f"## ❌ {r['agent']}")
                    lines.append(f"- Error: {r.get('error', 'Unknown error')}")
                lines.append("")
            return "\n".join(lines)
    except Exception as e:
        return _handle_error(e)


@mcp.tool(
    name="startd8_compare_responses",
    annotations={
        "title": "Compare Prompt Responses",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
    }
)
async def startd8_compare_responses(params: CompareResponsesInput) -> str:
    """Compare all responses for a prompt."""
    try:
        framework = _get_framework()
        comparison = framework.compare_responses(params.prompt_id)
        
        if params.response_format == ResponseFormat.JSON:
            return json.dumps(comparison, indent=2, default=str)
        else:
            lines = [f"# Response Comparison", "", f"**Prompt ID:** `{params.prompt_id}`", ""]
            lines.append(f"**Total Responses:** {comparison.get('total_responses', 0)}")
            lines.append(f"**Average Response Time:** {comparison.get('avg_response_time_ms', 0):.2f}ms")
            lines.append(f"**Total Tokens:** {comparison.get('total_tokens', 0)}")
            lines.append("")
            
            responses = comparison.get('responses', [])
            for r in responses:
                lines.append(f"## {r.agent_name}")
                lines.append(f"- Model: {r.model}")
                lines.append(f"- Response Time: {r.response_time_ms}ms")
                if r.token_usage:
                    lines.append(f"- Tokens: {r.token_usage.total} (in: {r.token_usage.input}, out: {r.token_usage.output})")
                lines.append(f"- Response Preview: {r.response[:200]}{'...' if len(r.response) > 200 else ''}")
                lines.append("")
            
            return "\n".join(lines)
    except Exception as e:
        return _handle_error(e)


@mcp.tool(
    name="startd8_view_statistics",
    annotations={
        "title": "View Statistics",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
    }
)
async def startd8_view_statistics(params: ViewStatisticsInput) -> str:
    """View statistics about prompts and responses."""
    try:
        framework = _get_framework()
        
        # Get basic stats
        prompts = framework.list_prompts()
        total_prompts = len(prompts) if isinstance(prompts, list) else prompts.get('total', 0)
        
        responses = framework.list_responses(
            prompt_id=params.prompt_id,
            agent_name=params.agent_name
        )
        total_responses = len(responses) if isinstance(responses, list) else responses.get('total', 0)
        
        stats = {
            "total_prompts": total_prompts,
            "total_responses": total_responses,
            "filter": {
                "prompt_id": params.prompt_id,
                "agent_name": params.agent_name
            }
        }
        
        if params.response_format == ResponseFormat.JSON:
            return json.dumps(stats, indent=2)
        else:
            lines = ["# Statistics", ""]
            lines.append(f"**Total Prompts:** {stats['total_prompts']}")
            lines.append(f"**Total Responses:** {stats['total_responses']}")
            if params.prompt_id or params.agent_name:
                lines.append("")
                lines.append("**Filters:**")
                if params.prompt_id:
                    lines.append(f"- Prompt ID: `{params.prompt_id}`")
                if params.agent_name:
                    lines.append(f"- Agent: {params.agent_name}")
            return "\n".join(lines)
    except Exception as e:
        return _handle_error(e)


@mcp.tool(
    name="startd8_get_prompt",
    annotations={
        "title": "Get Prompt Details",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
    }
)
async def startd8_get_prompt(
    prompt_id: str = Field(..., description="Prompt ID to retrieve"),
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)
) -> str:
    """Get detailed information about a specific prompt."""
    try:
        framework = _get_framework()
        prompt = framework.get_prompt(prompt_id)
        
        if not prompt:
            return f"Error: Prompt '{prompt_id}' not found."
        
        result = {
            "id": prompt.id,
            "version": prompt.version,
            "tags": prompt.tags,
            "created": prompt.timestamp.isoformat(),
            "content": prompt.content,
            "metadata": prompt.metadata
        }
        
        if response_format == ResponseFormat.JSON:
            return json.dumps(result, indent=2)
        else:
            return f"""# Prompt Details

**ID:** `{prompt.id}`
**Version:** {prompt.version}
**Tags:** {', '.join(prompt.tags) if prompt.tags else 'None'}
**Created:** {prompt.timestamp}

**Content:**
{prompt.content}
"""
    except Exception as e:
        return _handle_error(e)


@mcp.tool(
    name="startd8_list_agents",
    annotations={
        "title": "List Available Agents",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
    }
)
async def startd8_list_agents(
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)
) -> str:
    """List all available agents in the framework."""
    try:
        try:
            # Startd8 SDK v1+: AgentRegistry lives in job_queue
            with _redirect_stdout_to_stderr():
                from startd8.job_queue import AgentRegistry
        except ImportError:
            try:
                # Older/alternate layouts
                with _redirect_stdout_to_stderr():
                    from startd8.agents import AgentRegistry
            except ImportError:
                # Final fallback for alternate package layouts
                with _redirect_stdout_to_stderr():
                    from startd8 import AgentRegistry
        registry = AgentRegistry()
        agents = registry.list_agents()
        
        if response_format == ResponseFormat.JSON:
            return json.dumps({"agents": agents}, indent=2)
        else:
            if not agents:
                return "No agents available. Configure agents first."
            lines = ["# Available Agents", ""]
            for agent_name in agents:
                agent = registry.get_agent(agent_name)
                if agent:
                    lines.append(f"- **{agent_name}** ({agent.model})")
                else:
                    lines.append(f"- **{agent_name}** (not configured)")
            return "\n".join(lines)
    except Exception as e:
        return _handle_error(e)


@mcp.tool(
    name="startd8_test_agent_connection",
    annotations={
        "title": "Test Agent Connection",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
    }
)
async def startd8_test_agent_connection(
    agent_name: str = Field(..., description="Agent name to test"),
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)
) -> str:
    """Test if an agent is properly configured and can be used."""
    try:
        try:
            # Startd8 SDK v1+: AgentRegistry lives in job_queue
            with _redirect_stdout_to_stderr():
                from startd8.job_queue import AgentRegistry
        except ImportError:
            try:
                # Older/alternate layouts
                with _redirect_stdout_to_stderr():
                    from startd8.agents import AgentRegistry
            except ImportError:
                # Final fallback for alternate package layouts
                with _redirect_stdout_to_stderr():
                    from startd8 import AgentRegistry
        registry = AgentRegistry()
        agent = registry.get_agent(agent_name)
        
        if not agent:
            result = {"agent": agent_name, "status": "not_found", "error": "Agent not found"}
        else:
            # Try a simple test generation
            try:
                test_response, response_time_ms, token_usage = agent.generate("Test")
                result = {
                    "agent": agent_name,
                    "status": "success",
                    "model": agent.model,
                    "response_time_ms": response_time_ms,
                    "test_passed": True
                }
            except Exception as e:
                result = {
                    "agent": agent_name,
                    "status": "error",
                    "model": agent.model,
                    "error": str(e),
                    "test_passed": False
                }
        
        if response_format == ResponseFormat.JSON:
            return json.dumps(result, indent=2)
        else:
            if result["status"] == "success":
                return f"""# Agent Connection Test

✅ **{agent_name}** is working correctly.

- **Model:** {result.get('model', 'N/A')}
- **Response Time:** {result.get('response_time_ms', 'N/A')}ms
- **Status:** Ready to use
"""
            else:
                return f"""# Agent Connection Test

❌ **{agent_name}** has issues.

- **Status:** {result['status']}
- **Error:** {result.get('error', 'Unknown error')}
"""
    except Exception as e:
        return _handle_error(e)


# ═══════════════════════════════════════════════════════════════
# MAIN ENTRY POINT
# ═══════════════════════════════════════════════════════════════

def main() -> None:
    """Run the MCP server (stdio transport)."""
    _setup_signal_handlers()
    banner = r"""
   _____ _             _    _     _____ 
  / ____| |           | |  | |   |  __ \
 | (___ | |_ __ _ _ __| | _| |__ | |  | | ___  ___ _ __
  \___ \| __/ _` | '__| |/ / '_ \| |  | |/ _ \/ _ \ '__|
  ____) | || (_| | |  |   <| | | | |__| |  __/  __/ |
 |_____/ \__\__,_|_|  |_|\_\_| |_|_____/ \___|\___|_|
    """
    if not MCP_QUIET and MCP_DEBUG:
        _eprint(banner, flush=True)
    if not MCP_QUIET:
        _eprint("Startd8 MCP server starting... (stdio transport)", flush=True)
        _eprint("", flush=True)

    if not MCP_QUIET and MCP_DEBUG:
        _eprint("== Paths ==", flush=True)
        _eprint(f"PROJECT_ROOT: {DEFAULT_PROJECT_ROOT}", flush=True)
        _eprint(f"TASK_LIST_PATH: {DEFAULT_TASK_LIST_PATH}", flush=True)
        _eprint(f"TASK_LOG_PATH: {DEFAULT_TASK_LOG_PATH}", flush=True)
        _eprint("", flush=True)
        _eprint("== Agents / Auto-deps ==", flush=True)
        _eprint(f"DEFAULT_AGENT: {DEFAULT_AGENT_NAME}", flush=True)
        _eprint(
            f"ALLOW_AUTO_DEPS: {ALLOW_AUTO_DEPS} | AUTO_MAX_DEPTH: {AUTO_MAX_DEPTH} | AUTO_MAX_TASKS: {AUTO_MAX_TASKS}",
            flush=True,
        )
        _eprint("", flush=True)
        _eprint("== Skill paths ==", flush=True)

    if not MCP_QUIET and MCP_DEBUG:
        _ensure_sdk_available()
        sdk_paths = [p for p in DEFAULT_SDK_PATHS if p and p.exists()]
        _eprint(f"SDK search paths: {sdk_paths}", flush=True)
        _eprint(f"STARTD8_SKILL_PATH: {os.getenv('STARTD8_SKILL_PATH', '')}", flush=True)
        skill_path_ok = os.getenv("STARTD8_SKILL_PATH") is not None
        _eprint(f"Skill path configured: {skill_path_ok}", flush=True)
        _eprint(
            "To update skill paths, set STARTD8_SKILL_PATH (colon-separated) and restart.",
            flush=True,
        )
        try:
            import startd8  # noqa: F401
            startd8_loaded = True
            startd8_path = startd8.__file__
        except Exception as e:
            startd8_loaded = False
            startd8_path = str(e)
        _eprint(f"startd8 loaded: {startd8_loaded} | path/info: {startd8_path}", flush=True)
        agent_cls = globals().get("SkillAgentConcrete") or globals().get("ClaudeSkillAgent")
        agent_loaded = agent_cls is not None
        _eprint(f"agent resolved: {agent_loaded} | class: {agent_cls}", flush=True)
        _eprint("", flush=True)
        _eprint("== PYTHONPATH ==", flush=True)
        for p in sys.path:
            _eprint(f"  - {p}", flush=True)
        _eprint("", flush=True)
    # Summarize discoverable skills (and register concrete resources/tools for client discovery)
    try:
        import time
        STARTUP_SKILLS_INDEX_LIMIT = MCP_STARTUP_MAX_SKILLS
        STARTUP_SKILLS_INDEX_SKIPPED = MCP_STARTUP_MAX_SKILLS <= 0
        scan_started = time.perf_counter()
        if MCP_STARTUP_MAX_SKILLS <= 0:
            skills = []
        else:
            skills = _find_skills(max_results=MCP_STARTUP_MAX_SKILLS)
        STARTUP_SKILLS_INDEXED = len(skills)
        STARTUP_METRICS["skill_scan_ms"] = int((time.perf_counter() - scan_started) * 1000)
        # Human-readable skills list to stderr logs (controller/Cursor logs).
        if not MCP_QUIET:
            _eprint("== Skills discovered ==", flush=True)
            _eprint(f"Skills available: {len(skills)}", flush=True)
            if skills:
                for s in skills:
                    name = str(s.get("name", "unknown"))
                    directory = str(s.get("directory", "") or "")
                    if directory:
                        _eprint(f"- {name}  ({directory})", flush=True)
                    else:
                        _eprint(f"- {name}", flush=True)
            else:
                _eprint("No skills found. Check STARTD8_SKILL_PATH and contents.", flush=True)
            _eprint("", flush=True)

        # Also register concrete `skill://<name>` resources so list_resources() is useful.
        reg_started = time.perf_counter()
        added = _register_concrete_skill_resources(skills) if skills else 0
        STARTUP_METRICS["resource_register_ms"] = int((time.perf_counter() - reg_started) * 1000)
        tool_started = time.perf_counter()
        added_tools = _register_concrete_skill_tools(skills) if skills else 0
        STARTUP_METRICS["skill_tool_register_ms"] = int((time.perf_counter() - tool_started) * 1000)
        if not MCP_QUIET and MCP_DEBUG:
            _eprint(f"Concrete skill resources registered: {added}", flush=True)
            _eprint(f"Concrete per-skill tools registered: {added_tools}", flush=True)
    except Exception as e:
        _record_startup_error(f"Skills listing failed during startup: {e}")
        if not MCP_QUIET:
            _eprint(f"Skills available: error listing skills: {e}", flush=True)
    if not MCP_QUIET and MCP_DEBUG:
        _eprint("", flush=True)

    # Startup summary (single place for "did we start cleanly?")
    if not MCP_QUIET:
        _eprint("== Startup summary ==", flush=True)
        if STARTUP_ERRORS:
            _eprint(
                f"Startup completed WITH ERRORS ({len(STARTUP_ERRORS)}). See list below:",
                flush=True,
            )
            for i, err in enumerate(STARTUP_ERRORS, start=1):
                _eprint(f"  {i}. {err}", flush=True)
        else:
            _eprint("Startup completed without errors.", flush=True)
        _eprint("", flush=True)
    else:
        if STARTUP_ERRORS:
            _eprint(
                f"[startup-error] Startd8 MCP startup completed WITH ERRORS ({len(STARTUP_ERRORS)}).",
                flush=True,
            )

    try:
        mcp.run()
    except KeyboardInterrupt:
        _eprint("\nStartd8 MCP server received KeyboardInterrupt. Shutting down cleanly.", flush=True)
        sys.exit(0)


if __name__ == "__main__":
    main()
