"""TODO scanner with A/B/C classification (REQ-TCW-100–103).

Scans generated files for TODO markers, commented-out code blocks, and empty
method stubs.  Each TODO is classified:

- **Category A**: Adjacent commented-out code block (3+ contiguous commented
  lines with code-like content) — can be resolved by uncommenting.
- **Category B**: TODO in empty method stub AND instrumentation vocabulary
  match — can be resolved from an instrumentation contract.
- **Category C**: Default — insufficient context for automated resolution.

See docs/design/prime/TODO_COMPLETION_WORKFLOW_REQUIREMENTS.md for requirements.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from startd8.logging_config import get_logger

logger = get_logger(__name__)

__all__ = [
    "TodoEntry",
    "TodoInventory",
    "scan_todos",
    "classify_todo",
    "scan_file",
    "normalize_instrumentation_data",
]


# ---------------------------------------------------------------------------
# Patterns
# ---------------------------------------------------------------------------

# TODO/FIXME markers (case-insensitive)
_TODO_PATTERN = re.compile(
    r"(?://|#|/\*|\*)\s*(?:@?TODO|@?FIXME|@?HACK)\b",
    re.IGNORECASE,
)

# Instrumentation vocabulary — words that indicate observability stubs
_INSTRUMENTATION_VOCAB = frozenset({
    "metrics", "tracing", "stats", "profiler", "otel", "opentelemetry",
    "telemetry", "instrumentation", "meter", "tracer", "exporter",
    "interceptor", "middleware", "prometheus", "jaeger", "zipkin",
    "initstats", "inittracing", "initmetrics", "initprofiler",
    "setuptelemetry", "setupmetrics", "setuptracing",
})

# Security vocabulary — words that indicate database/query security context
_SECURITY_VOCAB = frozenset({
    "sql", "query", "select", "insert", "update", "delete",
    "database", "connection", "credential", "password",
    "parameterized", "injection", "npgsql", "spanner",
    "redis", "mysql", "sqlite",
})

# Comment prefixes by language family
_SINGLE_LINE_COMMENT = re.compile(r"^\s*(?://|#)\s?")
_BLOCK_COMMENT_START = re.compile(r"^\s*/\*")
_BLOCK_COMMENT_END = re.compile(r"\*/\s*$")

# Code-like content heuristics (when found in comments, suggests commented-out code)
_CODE_LIKE = re.compile(
    r"(?:"
    r"import\s|from\s|require\s|include\s"  # imports
    r"|[a-zA-Z_]\w*\s*\(.*\)"               # function calls
    r"|[a-zA-Z_]\w*\s*=\s*"                  # assignments
    r"|if\s*\(|for\s*\(|while\s*\("          # control flow
    r"|new\s+[A-Z]"                          # object creation
    r"|return\s"                             # return statements
    r"|\.add\(|\.set\(|\.get\("              # method calls
    r"|wget\s|curl\s|apt-get\s|RUN\s"        # shell commands (Dockerfile)
    r"|ENV\s|COPY\s|FROM\s"                  # Dockerfile directives
    r")",
)

# Empty stub body patterns
_STUB_BODY_JAVA = re.compile(
    r"^\s*(?://\s*TODO.*|throw\s+new\s+(?:Unsupported|Runtime).*|return;?\s*|}\s*)$",
    re.IGNORECASE,
)
_STUB_BODY_GO = re.compile(
    r"^\s*(?://\s*TODO.*|panic\s*\(|return\s*$|}\s*)$",
    re.IGNORECASE,
)
_STUB_BODY_PYTHON = re.compile(
    r"^\s*(?:#\s*TODO.*|pass\s*|raise\s+NotImplementedError.*|\.\.\.)$",
    re.IGNORECASE,
)

# Method/function definition patterns for context extraction
_METHOD_DEF_JAVA = re.compile(
    r"(?:public|private|protected|static|\s)+\s+\w+\s+(\w+)\s*\(",
)
_METHOD_DEF_GO = re.compile(r"func\s+(?:\(\w+\s+\*?\w+\)\s+)?(\w+)\s*\(")
_METHOD_DEF_PYTHON = re.compile(r"def\s+(\w+)\s*\(")


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class TodoEntry:
    """A single detected TODO in generated code."""

    file_path: str
    line: int
    language: str
    raw_text: str
    category: str  # "A" | "B" | "C"
    context_lines: str  # 5 lines before + after
    containing_function: str
    matched_requirements: Tuple[str, ...] = ()
    confidence: float = 1.0
    rationale: str = ""
    contract_fields: Tuple[str, ...] = ()
    security_sensitive: bool = False
    security_contract_ref: Optional[str] = None

    @property
    def id(self) -> str:
        """Stable ID: hash of file_path + line."""
        return hashlib.sha256(
            f"{self.file_path}:{self.line}".encode()
        ).hexdigest()[:12]

    def to_dict(self) -> Dict[str, Any]:
        d = dataclasses.asdict(self)
        d["id"] = self.id
        return d


@dataclass
class TodoInventory:
    """Collection of all TODOs found in a scan."""

    entries: List[TodoEntry] = field(default_factory=list)
    summary: Dict[str, int] = field(default_factory=dict)

    def compute_summary(self) -> None:
        self.summary = {"A": 0, "B": 0, "C": 0, "total": 0, "security_todos": 0}
        for e in self.entries:
            self.summary[e.category] = self.summary.get(e.category, 0) + 1
            self.summary["total"] += 1
            if e.security_sensitive:
                self.summary["security_todos"] += 1

    def to_dict(self) -> Dict[str, Any]:
        self.compute_summary()
        return {
            "entries": [e.to_dict() for e in self.entries],
            "summary": self.summary,
        }

    def save(self, path: str | Path) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(
            json.dumps(self.to_dict(), indent=2, default=str),
            encoding="utf-8",
        )
        logger.info("TODO inventory saved: %s (%d entries)", p, len(self.entries))


# ---------------------------------------------------------------------------
# Language Detection
# ---------------------------------------------------------------------------

def _detect_language(file_path: str) -> str:
    """Detect language from file extension."""
    ext = Path(file_path).suffix.lower()
    _map = {
        ".java": "java", ".kt": "java",
        ".go": "go",
        ".py": "python",
        ".js": "nodejs", ".ts": "nodejs",
        ".cs": "csharp",
        ".gradle": "groovy",
        ".xml": "xml",
        ".yaml": "yaml", ".yml": "yaml",
        ".json": "json",
        ".properties": "properties",
    }
    name = Path(file_path).name
    if name.startswith("Dockerfile"):
        return "dockerfile"
    return _map.get(ext, "unknown")


# ---------------------------------------------------------------------------
# Core Scanning
# ---------------------------------------------------------------------------

def scan_todos(
    file_path: str,
    content: str,
    language: str = "",
) -> List[TodoEntry]:
    """Scan a single file's content for TODO markers and stubs.

    Returns unclassified entries (category="C" by default).
    Use ``classify_todo()`` to assign A/B/C categories.
    """
    if not language:
        language = _detect_language(file_path)

    lines = content.splitlines()
    entries: List[TodoEntry] = []

    for i, line in enumerate(lines):
        if not _TODO_PATTERN.search(line):
            continue

        # Extract context (5 lines before/after)
        start = max(0, i - 5)
        end = min(len(lines), i + 6)
        context = "\n".join(lines[start:end])

        # Find containing function
        containing_fn = _find_containing_function(lines, i, language)

        entries.append(TodoEntry(
            file_path=file_path,
            line=i + 1,  # 1-indexed
            language=language,
            raw_text=line.strip(),
            category="C",  # default, reclassified by classify_todo
            context_lines=context,
            containing_function=containing_fn,
        ))

    return entries


def classify_todo(
    entry: TodoEntry,
    lines: List[str],
    instrumentation_contract: Optional[Dict[str, Any]] = None,
) -> TodoEntry:
    """Classify a TodoEntry as Category A, B, or C.

    Args:
        entry: The TodoEntry to classify (immutable — returns new instance).
        lines: All lines of the source file.
        instrumentation_contract: Optional instrumentation contract for
            Category B matching.

    Returns:
        New TodoEntry with updated category, rationale, and contract_fields.
    """
    idx = entry.line - 1  # 0-indexed

    # --- Category A: adjacent commented-out code block ---
    cat_a_result = _check_category_a(lines, idx, entry.language)
    if cat_a_result:
        return dataclasses.replace(
            entry,
            category="A",
            rationale=cat_a_result,
            confidence=0.9,
        )

    # --- Category B: empty stub + instrumentation vocabulary ---
    cat_b_result = _check_category_b(
        lines, idx, entry.language, entry.containing_function,
        instrumentation_contract,
    )
    if cat_b_result:
        contract_fields = tuple(cat_b_result.get("contract_fields", []))
        return dataclasses.replace(
            entry,
            category="B",
            rationale=cat_b_result["rationale"],
            confidence=cat_b_result.get("confidence", 0.8),
            contract_fields=contract_fields,
            matched_requirements=tuple(cat_b_result.get("matched_requirements", [])),
        )

    # --- Category S annotation: security-sensitive TODO ---
    # Check if the surrounding context contains security vocabulary
    context_start = max(0, idx - 5)
    context_end = min(len(lines), idx + 6)
    context_text = " ".join(lines[context_start:context_end]).lower()
    is_security = any(word in context_text for word in _SECURITY_VOCAB)
    if is_security:
        entry = dataclasses.replace(entry, security_sensitive=True)

    # --- Category C: default ---
    return entry


def _check_category_a(lines: List[str], idx: int, language: str) -> str:
    """Check if TODO is adjacent to a commented-out code block.

    Returns rationale string if Category A, empty string otherwise.
    """
    # Search within 3 lines of the TODO for a contiguous commented block
    search_range = range(max(0, idx - 3), min(len(lines), idx + 4))

    for start in search_range:
        if start == idx:
            continue
        # Check if this starts a contiguous commented block
        block_lines = _find_comment_block(lines, start, language)
        if len(block_lines) >= 3:
            # Verify the block contains code-like content
            code_like_count = sum(
                1 for _, bl in block_lines if _CODE_LIKE.search(bl)
            )
            if code_like_count >= 2:
                return (
                    f"Adjacent commented-out code block at lines "
                    f"{block_lines[0][0]+1}-{block_lines[-1][0]+1} "
                    f"({code_like_count} code-like lines)"
                )
    return ""


def _find_comment_block(
    lines: List[str],
    start_idx: int,
    language: str,
) -> List[Tuple[int, str]]:
    """Find a contiguous block of commented lines starting at start_idx.

    Returns list of (line_index, line_text) tuples.
    """
    if start_idx >= len(lines):
        return []

    block: List[Tuple[int, str]] = []
    comment_prefix = _SINGLE_LINE_COMMENT

    for i in range(start_idx, min(len(lines), start_idx + 30)):
        line = lines[i]
        if comment_prefix.match(line) and line.strip():
            block.append((i, line))
        elif not line.strip():
            # Allow single blank lines within a block
            if block and i + 1 < len(lines) and comment_prefix.match(lines[i + 1]):
                continue
            break
        else:
            break

    return block


def _check_category_b(
    lines: List[str],
    idx: int,
    language: str,
    containing_function: str,
    instrumentation_contract: Optional[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """Check if TODO is in an empty stub with instrumentation vocabulary.

    Returns dict with rationale, contract_fields, confidence if Category B.
    """
    # Must be inside a function
    if not containing_function:
        return None

    # Check instrumentation vocabulary in function name or TODO text
    fn_lower = containing_function.lower()
    todo_line = lines[idx].lower() if idx < len(lines) else ""
    combined = fn_lower + " " + todo_line

    vocab_matches = [
        v for v in _INSTRUMENTATION_VOCAB
        if v in combined
    ]
    if not vocab_matches:
        return None

    # Check if containing function is a stub (mostly empty body)
    is_stub = _is_stub_body(lines, idx, language, containing_function)
    if not is_stub:
        return None

    result: Dict[str, Any] = {
        "rationale": (
            f"Stub method '{containing_function}' matches instrumentation "
            f"vocabulary: {', '.join(vocab_matches)}"
        ),
        "confidence": 0.8,
        "contract_fields": [],
        "matched_requirements": [],
    }

    # If we have an instrumentation contract, match specific fields
    if instrumentation_contract:
        contract_fields = _match_contract_fields(
            containing_function, instrumentation_contract,
        )
        if contract_fields:
            result["contract_fields"] = contract_fields
            result["confidence"] = 0.95
            result["matched_requirements"] = [
                f"instrumentation_contract.{f}" for f in contract_fields
            ]

    return result


def _is_stub_body(
    lines: List[str],
    todo_idx: int,
    language: str,
    function_name: str,
) -> bool:
    """Check if the function containing the TODO has a stub-like body."""
    # Find the function definition line
    fn_start = None
    for i in range(todo_idx, -1, -1):
        if function_name in lines[i]:
            fn_start = i
            break
    if fn_start is None:
        return False

    # Count non-trivial body lines between fn_start and the end of the block
    body_lines = 0
    stub_lines = 0
    stub_pattern = {
        "java": _STUB_BODY_JAVA,
        "go": _STUB_BODY_GO,
        "python": _STUB_BODY_PYTHON,
    }.get(language, _STUB_BODY_JAVA)

    # Simple heuristic: check lines after the function definition
    brace_depth = 0
    for i in range(fn_start, min(len(lines), fn_start + 20)):
        line = lines[i].strip()
        if not line:
            continue
        brace_depth += line.count("{") - line.count("}")
        if i > fn_start:  # skip the definition line itself
            body_lines += 1
            if stub_pattern.match(lines[i]):
                stub_lines += 1
        if brace_depth == 0 and i > fn_start and "{" in lines[fn_start]:
            break

    # Stub if most body lines match stub patterns
    if body_lines == 0:
        return True
    return stub_lines / body_lines >= 0.5


def _match_contract_fields(
    function_name: str,
    contract: Dict[str, Any],
) -> List[str]:
    """Match a function name to instrumentation contract fields.

    Handles both StartD8's ``instrumentation_contract`` schema
    (``metrics.required``) and ContextCore's ``instrumentation_hints``
    schema (``metrics.convention_based`` / ``metrics.manifest_declared``).
    """
    fn_lower = function_name.lower()
    fields: List[str] = []

    if "stat" in fn_lower or "metric" in fn_lower or "meter" in fn_lower:
        metrics = contract.get("metrics", {})
        # Check both schemas: callers using scan_file() get auto-normalization,
        # but direct classify_todo() callers may pass either schema raw.
        has_metrics = (
            metrics.get("required")
            or metrics.get("convention_based")
            or metrics.get("manifest_declared")
        )
        if has_metrics:
            fields.append("metrics.required")
    if "trac" in fn_lower or "span" in fn_lower:
        if contract.get("traces", {}).get("required"):
            fields.append("traces.required")
    if "log" in fn_lower:
        if contract.get("logging", {}).get("trace_context_fields"):
            fields.append("logging.trace_context_fields")
    if "profil" in fn_lower:
        fields.append("profiler")

    return fields


def normalize_instrumentation_data(
    data: Optional[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """Normalize ContextCore ``instrumentation_hints`` to ``instrumentation_contract`` schema.

    ContextCore's ``derive_instrumentation_hints()`` emits per-service dicts with
    ``metrics.convention_based`` and ``metrics.manifest_declared`` arrays.  StartD8's
    TODO scanner expects ``metrics.required``.  This function bridges the two by
    merging both arrays into ``metrics.required`` without losing the originals.

    Accepts either schema unchanged — if ``metrics.required`` already exists, returns as-is.
    """
    if not data or not isinstance(data, dict):
        return data

    metrics = data.get("metrics")
    if not isinstance(metrics, dict):
        return data

    # Already normalized (has metrics.required — even if empty list)
    if "required" in metrics:
        return data

    # Merge convention_based + manifest_declared into required
    required: List[Dict[str, Any]] = []
    for key in ("convention_based", "manifest_declared"):
        entries = metrics.get(key, [])
        if isinstance(entries, list):
            required.extend(entries)

    if required:
        # Don't mutate the original — shallow-copy metrics
        normalized = dict(data)
        normalized["metrics"] = dict(metrics)
        normalized["metrics"]["required"] = required
        return normalized

    return data


# ---------------------------------------------------------------------------
# Containing Function Extraction
# ---------------------------------------------------------------------------

def _find_containing_function(
    lines: List[str],
    idx: int,
    language: str,
) -> str:
    """Walk backward from idx to find the enclosing function/method name."""
    pattern = {
        "java": _METHOD_DEF_JAVA,
        "groovy": _METHOD_DEF_JAVA,
        "go": _METHOD_DEF_GO,
        "python": _METHOD_DEF_PYTHON,
    }.get(language)

    if not pattern:
        # Generic: try all patterns
        patterns = [_METHOD_DEF_JAVA, _METHOD_DEF_GO, _METHOD_DEF_PYTHON]
    else:
        patterns = [pattern]

    for i in range(idx, max(idx - 50, -1), -1):
        for pat in patterns:
            m = pat.search(lines[i])
            if m:
                return m.group(1)
    return ""


# ---------------------------------------------------------------------------
# High-Level File Scanner
# ---------------------------------------------------------------------------

def scan_file(
    file_path: str | Path,
    instrumentation_contract: Optional[Dict[str, Any]] = None,
) -> List[TodoEntry]:
    """Scan a file on disk, returning classified TodoEntries.

    Accepts both ContextCore's ``instrumentation_hints`` schema and
    StartD8's ``instrumentation_contract`` schema — automatically
    normalizes via :func:`normalize_instrumentation_data`.
    """
    p = Path(file_path)
    if not p.is_file():
        return []

    try:
        content = p.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        logger.warning("Failed to read %s: %s", file_path, exc)
        return []

    # Normalize ContextCore hints → contract schema
    normalized = normalize_instrumentation_data(instrumentation_contract)

    language = _detect_language(str(file_path))
    raw_entries = scan_todos(str(file_path), content, language)
    lines = content.splitlines()

    return [classify_todo(entry, lines, normalized) for entry in raw_entries]


def scan_directory(
    directory: str | Path,
    *,
    instrumentation_contract: Optional[Dict[str, Any]] = None,
    extensions: Optional[Sequence[str]] = None,
) -> TodoInventory:
    """Scan all files in a directory, returning a TodoInventory."""
    d = Path(directory)
    if not d.is_dir():
        return TodoInventory()

    if extensions is None:
        extensions = (".java", ".go", ".py", ".js", ".ts", ".cs", ".gradle", ".xml")

    inventory = TodoInventory()
    for ext in extensions:
        for f in d.rglob(f"*{ext}"):
            entries = scan_file(f, instrumentation_contract)
            inventory.entries.extend(entries)

    inventory.compute_summary()
    return inventory
