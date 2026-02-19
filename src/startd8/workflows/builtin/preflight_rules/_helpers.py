"""
Shared helper functions used by preflight rules.

Relocated from ``domain_preflight_workflow.py`` for reuse across rule modules.
The original module re-exports these for backward compatibility.
"""

from __future__ import annotations

import ast
import configparser
import re
from pathlib import Path
from typing import Dict, List, Set


# ---------------------------------------------------------------------------
# Stdlib fallback for Python < 3.10
# ---------------------------------------------------------------------------

STDLIB_FALLBACK: Set[str] = {
    "abc", "aifc", "argparse", "array", "ast", "asynchat", "asyncio",
    "asyncore", "atexit", "audioop", "base64", "bdb", "binascii",
    "binhex", "bisect", "builtins", "bz2", "calendar", "cgi", "cgitb",
    "chunk", "cmath", "cmd", "code", "codecs", "codeop", "collections",
    "colorsys", "compileall", "concurrent", "configparser", "contextlib",
    "contextvars", "copy", "copyreg", "cProfile", "crypt", "csv",
    "ctypes", "curses", "dataclasses", "datetime", "dbm", "decimal",
    "difflib", "dis", "distutils", "doctest", "email", "encodings",
    "enum", "errno", "faulthandler", "fcntl", "filecmp", "fileinput",
    "fnmatch", "fractions", "ftplib", "functools", "gc", "getopt",
    "getpass", "gettext", "glob", "graphlib", "grp", "gzip", "hashlib",
    "heapq", "hmac", "html", "http", "idlelib", "imaplib", "imghdr",
    "imp", "importlib", "inspect", "io", "ipaddress", "itertools",
    "json", "keyword", "lib2to3", "linecache", "locale", "logging",
    "lzma", "mailbox", "mailcap", "marshal", "math", "mimetypes",
    "mmap", "modulefinder", "multiprocessing", "netrc", "nis", "nntplib",
    "numbers", "operator", "optparse", "os", "ossaudiodev", "pathlib",
    "pdb", "pickle", "pickletools", "pipes", "pkgutil", "platform",
    "plistlib", "poplib", "posix", "posixpath", "pprint", "profile",
    "pstats", "pty", "pwd", "py_compile", "pyclbr", "pydoc",
    "queue", "quopri", "random", "re", "readline", "reprlib",
    "resource", "rlcompleter", "runpy", "sched", "secrets", "select",
    "selectors", "shelve", "shlex", "shutil", "signal", "site",
    "smtpd", "smtplib", "sndhdr", "socket", "socketserver", "spwd",
    "sqlite3", "sre_compile", "sre_constants", "sre_parse", "ssl",
    "stat", "statistics", "string", "stringprep", "struct", "subprocess",
    "sunau", "symtable", "sys", "sysconfig", "syslog", "tabnanny",
    "tarfile", "telnetlib", "tempfile", "termios", "test", "textwrap",
    "threading", "time", "timeit", "tkinter", "token", "tokenize",
    "tomllib", "trace", "traceback", "tracemalloc", "tty", "turtle",
    "turtledemo", "types", "typing", "unicodedata", "unittest", "urllib",
    "uu", "uuid", "venv", "warnings", "wave", "weakref", "webbrowser",
    "winreg", "winsound", "wsgiref", "xdrlib", "xml", "xmlrpc",
    "zipapp", "zipfile", "zipimport", "zlib", "zoneinfo",
}


# ---------------------------------------------------------------------------
# Conventional standalone-script directories (not packages)
# ---------------------------------------------------------------------------

STANDALONE_SCRIPT_DIRS: Set[str] = {
    "scripts", "bin", "tools", "examples", "benchmarks", "utils_scripts",
}

# ---------------------------------------------------------------------------
# Reserved LogRecord field names (SDK Leg 9 #1)
# ---------------------------------------------------------------------------

LOGGER_RESERVED_FIELDS: Set[str] = {
    "name", "msg", "message", "args", "levelname", "levelno",
    "pathname", "filename", "module", "exc_info", "exc_text",
    "stack_info", "lineno", "funcName", "created", "msecs",
    "relativeCreated", "thread", "threadName", "process",
    "processName", "asctime", "taskName",
}


# ---------------------------------------------------------------------------
# File-level pattern scanning helpers
# ---------------------------------------------------------------------------

def parse_relative_imports(file_path: Path) -> List[str]:
    """Extract relative import targets from a Python file."""
    if not file_path.exists():
        return []
    try:
        text = file_path.read_text(encoding="utf-8")
    except Exception:
        return []
    return re.findall(r"^\s*from\s+\.(\w+)\s+import", text, re.MULTILINE)


def file_has_pattern(file_path: Path, pattern: str) -> bool:
    """Check if a file contains a regex pattern."""
    if not file_path.exists():
        return False
    try:
        text = file_path.read_text(encoding="utf-8")
        return bool(re.search(pattern, text))
    except Exception:
        return False


def scan_optional_dep_guards(file_path: Path) -> List[str]:
    """Find package names guarded by try/except ImportError in a file."""
    if not file_path.exists():
        return []
    try:
        text = file_path.read_text(encoding="utf-8")
    except Exception:
        return []
    guards = []
    for m in re.finditer(
        r"try:\s*\n\s+(?:import\s+(\w+)|from\s+(\w+))",
        text,
    ):
        pkg = m.group(1) or m.group(2)
        if pkg:
            guards.append(pkg)
    return guards


def scan_patch_paths(file_path: Path) -> List[str]:
    """Extract mock.patch / @patch target strings from a test file."""
    if not file_path.exists():
        return []
    try:
        text = file_path.read_text(encoding="utf-8")
    except Exception:
        return []
    return re.findall(r"""(?:@patch|mock\.patch)\(\s*["']([^"']+)["']""", text)


def normalize_dep_name(name: str) -> str:
    """Normalize a dependency name: strip version specs, lowercase, replace - with _."""
    name = re.split(r"\[", name, maxsplit=1)[0]
    name = re.split(r"[><=!~;]", name, maxsplit=1)[0]
    return name.strip().lower().replace("-", "_")


# ---------------------------------------------------------------------------
# Fallback dependency file parsers (Step 2)
# ---------------------------------------------------------------------------

def parse_requirements_txt(file_path: Path) -> List[str]:
    """Parse dependency names from a requirements.txt file.

    Skips comments, blank lines, flags (-r, -e, --index-url), and
    strips inline comments and environment markers.
    Returns normalized dependency names.
    """
    if not file_path.exists():
        return []
    try:
        text = file_path.read_text(encoding="utf-8")
    except Exception:
        return []

    deps: List[str] = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        # Skip pip flags
        if line.startswith(("-r", "-e", "-c", "--")):
            continue
        # Strip inline comments
        if " #" in line:
            line = line[:line.index(" #")].strip()
        # Strip environment markers (e.g. ; python_version >= "3.8")
        if ";" in line:
            line = line[:line.index(";")].strip()
        if not line:
            continue
        normalized = normalize_dep_name(line)
        if normalized:
            deps.append(normalized)
    return deps


def parse_setup_cfg_deps(file_path: Path) -> List[str]:
    """Parse dependency names from setup.cfg [options] install_requires.

    Uses stdlib configparser. Handles multi-line values.
    Returns normalized dependency names.
    """
    if not file_path.exists():
        return []
    try:
        cfg = configparser.ConfigParser()
        cfg.read(str(file_path), encoding="utf-8")
    except Exception:
        return []

    deps: List[str] = []
    raw = cfg.get("options", "install_requires", fallback="")
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        normalized = normalize_dep_name(line)
        if normalized:
            deps.append(normalized)
    return deps


# ---------------------------------------------------------------------------
# Existing-file import extraction (Step 3)
# ---------------------------------------------------------------------------

def extract_top_level_imports(file_path: Path) -> Set[str]:
    """Extract top-level package names from import statements in a Python file.

    Uses ast.parse to find Import and ImportFrom nodes.
    Returns the first component of each dotted import path.
    Skips relative imports. Returns empty set on missing file or syntax error.
    """
    if not file_path.exists():
        return set()
    try:
        text = file_path.read_text(encoding="utf-8")
    except Exception:
        return set()
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return set()

    packages: Set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                packages.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            # Skip relative imports
            if node.level and node.level > 0:
                continue
            if node.module:
                packages.add(node.module.split(".")[0])
    return packages


# ---------------------------------------------------------------------------
# Task description package scanning (Step 4)
# ---------------------------------------------------------------------------

# Curated mapping of common PyPI/colloquial names to their import names.
# Covers data science, web frameworks, HTTP, CLI, testing, AWS, observability.
_COMMON_PACKAGES: Dict[str, str] = {
    # Data science / ML
    "scikit-learn": "sklearn",
    "scikit_learn": "sklearn",
    "sklearn": "sklearn",
    "numpy": "numpy",
    "pandas": "pandas",
    "scipy": "scipy",
    "matplotlib": "matplotlib",
    "seaborn": "seaborn",
    "tensorflow": "tensorflow",
    "pytorch": "torch",
    "torch": "torch",
    "keras": "keras",
    "xgboost": "xgboost",
    "lightgbm": "lightgbm",
    "pillow": "PIL",
    "opencv": "cv2",
    "opencv-python": "cv2",
    # Web frameworks
    "flask": "flask",
    "django": "django",
    "fastapi": "fastapi",
    "starlette": "starlette",
    "sanic": "sanic",
    "bottle": "bottle",
    "tornado": "tornado",
    # HTTP / networking
    "requests": "requests",
    "httpx": "httpx",
    "aiohttp": "aiohttp",
    "urllib3": "urllib3",
    "websockets": "websockets",
    "grpcio": "grpc",
    # Data / serialization
    "pyyaml": "yaml",
    "ruamel.yaml": "ruamel",
    "toml": "toml",
    "tomli": "tomli",
    "msgpack": "msgpack",
    "protobuf": "google",
    "orjson": "orjson",
    # CLI / terminal
    "typer": "typer",
    "click": "click",
    "rich": "rich",
    "colorama": "colorama",
    "tqdm": "tqdm",
    # Testing
    "pytest": "pytest",
    "mock": "mock",
    "hypothesis": "hypothesis",
    "factory-boy": "factory",
    # Database
    "sqlalchemy": "sqlalchemy",
    "psycopg2": "psycopg2",
    "pymongo": "pymongo",
    "redis": "redis",
    "celery": "celery",
    # AWS / Cloud
    "boto3": "boto3",
    "botocore": "botocore",
    # Observability
    "opentelemetry": "opentelemetry",
    "prometheus-client": "prometheus_client",
    "sentry-sdk": "sentry_sdk",
    # Pydantic / validation
    "pydantic": "pydantic",
    "marshmallow": "marshmallow",
    "attrs": "attr",
    # Async
    "trio": "trio",
    "anyio": "anyio",
    "uvicorn": "uvicorn",
    # Misc
    "jinja2": "jinja2",
    "beautifulsoup4": "bs4",
    "lxml": "lxml",
    "cryptography": "cryptography",
    "paramiko": "paramiko",
    "arrow": "arrow",
    "pendulum": "pendulum",
    "dateutil": "dateutil",
    "python-dateutil": "dateutil",
}


def scan_task_description_packages(description: str) -> Set[str]:
    """Scan a task description for mentions of common Python packages.

    Uses word-boundary regex matching (case-insensitive) against
    ``_COMMON_PACKAGES`` keys. Returns the corresponding import names
    (not PyPI names).
    """
    if not description:
        return set()
    result: Set[str] = set()
    desc_lower = description.lower()
    for pkg_name, import_name in _COMMON_PACKAGES.items():
        # Word-boundary match to avoid substring false positives
        if re.search(r"\b" + re.escape(pkg_name) + r"\b", desc_lower):
            result.add(import_name)
    return result
