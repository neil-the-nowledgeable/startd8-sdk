"""Java wildcard import expansion step (REQ-KZ-JV-402e Phase 2).

Expands ``import java.util.*;`` to explicit imports based on which classes
from the package are actually used in the source file.  Uses an embedded
map of common JDK packages to their public class names.

Only fires for ``.java`` files.  Static wildcard imports
(``import static ...``) are left untouched — they are standard practice
in test code.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from ..models import ElementContext, RepairContext, RepairStepResult

# Regex matching a wildcard import line:
#   import java.util.*;
#   import  org.slf4j.*;
_WILDCARD_IMPORT_RE = re.compile(
    r"^(\s*)import\s+([\w.]+)\.\*\s*;\s*$",
    re.MULTILINE,
)

# Common JDK and framework packages → known public class names.
# Only packages where wildcard expansion is safe and useful are included.
_KNOWN_PACKAGES: dict[str, frozenset[str]] = {
    "java.util": frozenset({
        "AbstractCollection", "AbstractList", "AbstractMap", "AbstractQueue",
        "AbstractSequentialList", "AbstractSet", "ArrayDeque", "ArrayList",
        "Arrays", "Base64", "BitSet", "Calendar", "Collection", "Collections",
        "Comparator", "Currency", "Date", "Deque", "DoubleSummaryStatistics",
        "EnumMap", "EnumSet", "EventObject", "FormattableFlags", "Formatter",
        "GregorianCalendar", "HashMap", "HashSet", "Hashtable", "IdentityHashMap",
        "IntSummaryStatistics", "Iterator", "LinkedHashMap", "LinkedHashSet",
        "LinkedList", "List", "ListIterator", "Locale", "LongSummaryStatistics",
        "Map", "NavigableMap", "NavigableSet", "NoSuchElementException",
        "Objects", "Observable", "Optional", "OptionalDouble", "OptionalInt",
        "OptionalLong", "PriorityQueue", "Properties", "Queue", "Random",
        "Scanner", "ServiceLoader", "Set", "SimpleTimeZone", "SortedMap",
        "SortedSet", "Spliterator", "Stack", "StringJoiner", "StringTokenizer",
        "TimeZone", "Timer", "TimerTask", "TreeMap", "TreeSet", "UUID", "Vector",
    }),
    "java.util.stream": frozenset({
        "Collector", "Collectors", "DoubleStream", "IntStream", "LongStream",
        "Stream", "StreamSupport",
    }),
    "java.util.concurrent": frozenset({
        "Callable", "CompletableFuture", "CompletionStage", "ConcurrentHashMap",
        "ConcurrentLinkedDeque", "ConcurrentLinkedQueue", "ConcurrentMap",
        "ConcurrentSkipListMap", "ConcurrentSkipListSet", "CopyOnWriteArrayList",
        "CopyOnWriteArraySet", "CountDownLatch", "CyclicBarrier",
        "ExecutionException", "Executor", "ExecutorService", "Executors",
        "Future", "FutureTask", "LinkedBlockingDeque", "LinkedBlockingQueue",
        "Phaser", "RejectedExecutionException", "ScheduledExecutorService",
        "ScheduledFuture", "Semaphore", "ThreadFactory", "ThreadPoolExecutor",
        "TimeUnit", "TimeoutException",
    }),
    "java.io": frozenset({
        "BufferedInputStream", "BufferedOutputStream", "BufferedReader",
        "BufferedWriter", "ByteArrayInputStream", "ByteArrayOutputStream",
        "Closeable", "DataInputStream", "DataOutputStream", "File",
        "FileInputStream", "FileNotFoundException", "FileOutputStream",
        "FileReader", "FileWriter", "Flushable", "IOException",
        "InputStream", "InputStreamReader", "ObjectInputStream",
        "ObjectOutputStream", "OutputStream", "OutputStreamWriter",
        "PrintStream", "PrintWriter", "RandomAccessFile", "Reader",
        "Serializable", "StringReader", "StringWriter", "Writer",
    }),
    "java.nio.file": frozenset({
        "DirectoryStream", "FileSystem", "FileSystems", "FileVisitOption",
        "FileVisitResult", "FileVisitor", "Files", "LinkOption", "Path",
        "PathMatcher", "Paths", "SimpleFileVisitor", "StandardCopyOption",
        "StandardOpenOption", "StandardWatchEventKinds", "WatchEvent",
        "WatchKey", "WatchService",
    }),
    "java.nio": frozenset({
        "Buffer", "ByteBuffer", "ByteOrder", "CharBuffer", "DoubleBuffer",
        "FloatBuffer", "IntBuffer", "LongBuffer", "MappedByteBuffer",
        "ShortBuffer",
    }),
    "java.net": frozenset({
        "HttpURLConnection", "InetAddress", "InetSocketAddress", "MalformedURLException",
        "ServerSocket", "Socket", "SocketException", "SocketTimeoutException",
        "URI", "URISyntaxException", "URL", "URLConnection", "URLDecoder",
        "URLEncoder",
    }),
    "java.time": frozenset({
        "Clock", "DayOfWeek", "Duration", "Instant", "LocalDate", "LocalDateTime",
        "LocalTime", "Month", "MonthDay", "OffsetDateTime", "OffsetTime",
        "Period", "Year", "YearMonth", "ZoneId", "ZoneOffset", "ZonedDateTime",
    }),
    "java.time.format": frozenset({
        "DateTimeFormatter", "DateTimeFormatterBuilder", "DateTimeParseException",
        "FormatStyle", "ResolverStyle", "SignStyle", "TextStyle",
    }),
    "java.math": frozenset({
        "BigDecimal", "BigInteger", "MathContext", "RoundingMode",
    }),
    "java.sql": frozenset({
        "Connection", "DriverManager", "PreparedStatement", "ResultSet",
        "SQLException", "SQLTimeoutException", "Statement", "Timestamp",
        "Types",
    }),
    "java.util.function": frozenset({
        "BiConsumer", "BiFunction", "BiPredicate", "BinaryOperator",
        "BooleanSupplier", "Consumer", "DoubleBinaryOperator", "DoubleConsumer",
        "DoubleFunction", "DoublePredicate", "DoubleSupplier",
        "DoubleToIntFunction", "DoubleToLongFunction", "DoubleUnaryOperator",
        "Function", "IntBinaryOperator", "IntConsumer", "IntFunction",
        "IntPredicate", "IntSupplier", "IntToDoubleFunction",
        "IntToLongFunction", "IntUnaryOperator", "LongBinaryOperator",
        "LongConsumer", "LongFunction", "LongPredicate", "LongSupplier",
        "LongToDoubleFunction", "LongToIntFunction", "LongUnaryOperator",
        "ObjDoubleConsumer", "ObjIntConsumer", "ObjLongConsumer", "Predicate",
        "Supplier", "ToDoubleBiFunction", "ToDoubleFunction",
        "ToIntBiFunction", "ToIntFunction", "ToLongBiFunction",
        "ToLongFunction", "UnaryOperator",
    }),
    "java.util.regex": frozenset({
        "Matcher", "MatchResult", "Pattern", "PatternSyntaxException",
    }),
    "javax.sql": frozenset({
        "DataSource", "PooledConnection", "RowSet",
    }),
    "jakarta.persistence": frozenset({
        "Column", "Entity", "EntityManager", "EntityManagerFactory",
        "GeneratedValue", "GenerationType", "Id", "JoinColumn",
        "ManyToMany", "ManyToOne", "MappedSuperclass", "OneToMany",
        "OneToOne", "PersistenceContext", "Query", "Table", "TypedQuery",
    }),
}

# Template for a Java identifier boundary check.
# Used to check if a class name appears as a standalone token in the source.
_IDENT_BOUNDARY_TEMPLATE = r"(?<![.\w]){}(?![.\w])"


class JavaImportSortStep:
    """Expand wildcard Java imports to explicit imports (REQ-KZ-JV-402e Phase 2).

    For each ``import pkg.*;`` line, determines which classes from the package
    are actually referenced in the source and replaces the wildcard with
    explicit imports.  Unknown packages (not in ``_KNOWN_PACKAGES``) are
    left untouched to avoid data loss.
    """

    name: str = "java_import_sort"

    def __call__(
        self,
        code: str,
        context: RepairContext,
        file_path: Path,
        element_context: Optional[ElementContext] = None,
    ) -> RepairStepResult:
        if file_path.suffix.lower() != ".java":
            return RepairStepResult(step_name=self.name, modified=False, code=code)

        result, count = _expand_wildcard_imports(code)
        return RepairStepResult(
            step_name=self.name,
            modified=count > 0,
            code=result,
            metrics={"wildcards_expanded": count},
        )


def _expand_wildcard_imports(code: str) -> tuple[str, int]:
    """Replace wildcard imports with explicit imports for used classes.

    Returns ``(modified_code, number_of_wildcards_expanded)``.
    """
    count = 0
    # Work line-by-line to preserve formatting and ordering.
    lines = code.splitlines(keepends=True)
    result_lines: list[str] = []

    for line in lines:
        m = _WILDCARD_IMPORT_RE.match(line)
        if m is None:
            result_lines.append(line)
            continue

        indent = m.group(1)
        package = m.group(2)

        # Skip static wildcard imports (common in test code).
        stripped = line.strip()
        if stripped.startswith("import static "):
            result_lines.append(line)
            continue

        known_classes = _KNOWN_PACKAGES.get(package)
        if known_classes is None:
            # Unknown package — leave wildcard to avoid data loss.
            result_lines.append(line)
            continue

        # Find which classes from this package are actually used.
        used_classes = _find_used_classes(code, known_classes)
        if not used_classes:
            # Can't determine usage — keep wildcard as a safe fallback.
            result_lines.append(line)
            continue

        # Replace with sorted explicit imports.
        newline = "\n" if line.endswith("\n") else ""
        for cls in sorted(used_classes):
            result_lines.append(f"{indent}import {package}.{cls};{newline}")
        count += 1

    return "".join(result_lines), count


def _find_used_classes(code: str, known_classes: frozenset[str]) -> list[str]:
    """Return the subset of *known_classes* that appear as identifiers in *code*."""
    used: list[str] = []
    for cls in known_classes:
        pattern = _IDENT_BOUNDARY_TEMPLATE.format(re.escape(cls))
        # Check that the class name appears outside of import statements.
        # We search the whole code — the import line itself will match,
        # but we also need at least one *usage* site.  A class that only
        # appears in its own import is not "used".
        matches = list(re.finditer(pattern, code))
        # Need at least 2 occurrences: one in the import, one in usage.
        # But since we're replacing the wildcard, 1 occurrence (usage) suffices
        # because the wildcard import itself won't match the class name.
        if matches:
            used.append(cls)
    return used
