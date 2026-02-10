"""
Shared helper functions used by preflight rules.

Relocated from ``domain_preflight_workflow.py`` for reuse across rule modules.
The original module re-exports these for backward compatibility.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import List, Set


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
