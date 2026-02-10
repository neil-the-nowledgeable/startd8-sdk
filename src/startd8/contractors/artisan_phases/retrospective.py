from __future__ import annotations

import dataclasses
import enum
import logging
import re
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Protocol, Sequence, Tuple

logger = logging.getLogger(__name__)

class LessonCategory(str, Enum):
    """Categories for lessons extracted from retrospectives."""
    PROCESS = 'process'
    TECHNICAL = 'technical'
    COMMUNICATION = 'communication'
    TOOLING = 'tooling'
    ARCHITECTURE = 'architecture'
    TESTING = 'testing'
    DOCUMENTATION = 'documentation'
    PLANNING = 'planning'
    OTHER = 'other'

class Severity(str, Enum):
    """Severity levels for lessons and anti-pattern findings."""
    LOW = 'low'
    MEDIUM = 'medium'
    HIGH = 'high'
    CRITICAL = 'critical'

class SentimentType(str, Enum):
    """Sentiment classification for retrospective entries."""
    POSITIVE = 'positive'
    NEGATIVE = 'negative'
    NEUTRAL = 'neutral'

@dataclasses.dataclass
class RetrospectiveEntry:
    """A single observation from the retrospective.

    Attributes:
        id: UUID string, uniquely identifies this entry.
        content: The actual text of the observation.
        sentiment: Positive, negative, or neutral classification.
        timestamp: ISO 8601 datetime string when the entry was created.
        contributor: Who contributed this entry (can be "system").
        tags: Freeform tags for categorization and search.
        phase_context: Which phase/task this relates to (e.g., "implementation", "review").
    """
    id: str
    content: str
    sentiment: SentimentType
    timestamp: str
    contributor: str
    tags: List[str]
    phase_context: str

@dataclasses.dataclass
class RetrospectiveData:
    """Complete retrospective input data for a single task or sprint.

    Attributes:
        task_id: Unique identifier for the task being reviewed.
        task_summary: Human-readable summary of what was accomplished.
        went_well: Observations about what worked.
        went_poorly: Observations about what didn't work.
        action_items: Concrete next steps identified during the retro.
        metadata: Arbitrary metadata (duration, tools used, team size, etc.).
        timestamp: ISO 8601 datetime string when the retro was conducted.
    """
    task_id: str
    task_summary: str
    went_well: List[RetrospectiveEntry]
    went_poorly: List[RetrospectiveEntry]
    action_items: List[str]
    metadata: Dict[str, Any]
    timestamp: str

@dataclasses.dataclass
class Lesson:
    """A discrete, reusable lesson extracted from retrospective data.

    Attributes:
        id: UUID uniquely identifying this lesson.
        summary: One-sentence summary (max ~100 chars from source).
        detail: Longer explanation or full source text.
        category: Classification of the lesson's domain.
        severity: How impactful this lesson is.
        tags: Freeform tags for retrieval and grouping.
        source_task_id: Which task this lesson originated from.
        source_entry_ids: Which retrospective entries contributed.
        timestamp: ISO 8601 datetime string.
        anti_pattern_ids: Linked anti-pattern finding IDs, if any.
    """
    id: str
    summary: str
    detail: str
    category: LessonCategory
    severity: Severity
    tags: List[str]
    source_task_id: str
    source_entry_ids: List[str]
    timestamp: str
    anti_pattern_ids: List[str]

@dataclasses.dataclass
class AntiPatternDefinition:
    """A known anti-pattern in the detection catalog.

    Attributes:
        id: Stable identifier for the pattern definition.
        name: Human-readable name.
        description: What this anti-pattern is.
        keywords: Detection keywords/phrases (matched case-insensitively).
        regex_patterns: Optional regex patterns for more precise detection.
        remediation: Suggested fix or mitigation.
        category: Which lesson category this maps to.
        default_severity: Severity assigned when this pattern is detected.
    """
    id: str
    name: str
    description: str
    keywords: List[str]
    regex_patterns: List[str]
    remediation: str
    category: LessonCategory
    default_severity: Severity

@dataclasses.dataclass
class AntiPatternFinding:
    """An identified anti-pattern instance in a retrospective.

    Attributes:
        id: UUID for this specific finding.
        anti_pattern_id: References the AntiPatternDefinition.id.
        anti_pattern_name: Human-readable name of the matched pattern.
        evidence: Text snippets from entries that triggered detection.
        source_entry_ids: Which entries contained the evidence.
        remediation: Suggested fix (from the pattern definition).
        severity: Severity level of this finding.
        timestamp: ISO 8601 datetime string.
    """
    id: str
    anti_pattern_id: str
    anti_pattern_name: str
    evidence: List[str]
    source_entry_ids: List[str]
    remediation: str
    severity: Severity
    timestamp: str

@dataclasses.dataclass
class RetrospectiveResult:
    """The complete output of the retrospective phase.

    Attributes:
        task_id: The task that was reviewed.
        lessons: All extracted (and optionally sanitized) lessons.
        anti_pattern_findings: All detected anti-pattern instances.
        sanitized: Whether sanitization was applied.
        ingested: Whether lessons were successfully ingested into the provider.
        summary: Human-readable summary of the retrospective outcome.
        timestamp: ISO 8601 datetime string of completion.
    """
    task_id: str
    lessons: List[Lesson]
    anti_pattern_findings: List[AntiPatternFinding]
    sanitized: bool
    ingested: bool
    summary: str
    timestamp: str

class RetrospectiveSanitizer:
    """Redacts sensitive information from text fields before storage or display.

    Built-in patterns cover:
    - Private keys (PEM blocks)
    - Database connection strings
    - AWS access keys
    - API keys and secrets/tokens/passwords
    - Bearer tokens
    - Email addresses
    - IPv4 addresses
    - Unix and Windows user home paths

    Custom patterns can be added at construction time.
    """

    def __init__(self, additional_patterns: Optional[List[Tuple[str, str, str]]]=None):
        """
        Initialize sanitizer with built-in and optional custom patterns.

        Args:
            additional_patterns: List of (name, regex_string, replacement) tuples
                                 for custom sensitive patterns.
        """
        self._patterns: List[Tuple[str, 're.Pattern[str]', str]] = []
        built_in = [('private_key_block', '-----BEGIN\\s+(?:RSA\\s+)?PRIVATE KEY-----[\\s\\S]*?-----END\\s+(?:RSA\\s+)?PRIVATE KEY-----', '[REDACTED_PRIVATE_KEY]'), ('connection_string', '(?i)(?:mysql|postgres|postgresql|mongodb|redis|amqp):\\/\\/[^\\s]+', '[REDACTED_CONNECTION_STRING]'), ('aws_key', '(?:AKIA|ABIA|ACCA|ASIA)[A-Z0-9]{16}', '[REDACTED_AWS_KEY]'), ('api_key', '(?i)(?:api[_-]?key|apikey)\\s*[:=]\\s*[\'\\"]?[A-Za-z0-9_\\-]{16,}[\'\\"]?', '[REDACTED_API_KEY]'), ('secret_token', '(?i)(?:secret|token|password|passwd|pwd)\\s*[:=]\\s*[\'\\"]?[^\\s\'\\"]{8,}[\'\\"]?', '[REDACTED_SECRET]'), ('bearer_token', '(?i)Bearer\\s+[A-Za-z0-9_\\-\\.]+', '[REDACTED_BEARER_TOKEN]'), ('email', '[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\\.[a-zA-Z0-9-.]+', '[REDACTED_EMAIL]'), ('ipv4', '\\b(?:\\d{1,3}\\.){3}\\d{1,3}\\b', '[REDACTED_IP]'), ('unix_home_path', '/(?:home|Users)/[a-zA-Z0-9_\\-.]+', '[REDACTED_PATH]'), ('windows_user_path', '(?i)[A-Z]:\\\\Users\\\\[a-zA-Z0-9_\\-.]+', '[REDACTED_PATH]')]
        for name, pattern_str, replacement in built_in:
            try:
                compiled = re.compile(pattern_str)
                self._patterns.append((name, compiled, replacement))
            except re.error as exc:
                logger.warning("Failed to compile built-in pattern '%s': %s", name, exc)
        if additional_patterns:
            for name, pattern_str, replacement in additional_patterns:
                try:
                    compiled = re.compile(pattern_str)
                    self._patterns.append((name, compiled, replacement))
                except re.error as exc:
                    logger.warning("Failed to compile custom pattern '%s': %s", name, exc)

    def sanitize_text(self, text: str) -> str:
        """Redact all sensitive patterns from a single string."""
        if not text:
            return text
        result = text
        for name, pattern, replacement in self._patterns:
            try:
                result = pattern.sub(replacement, result)
            except Exception as exc:
                logger.warning("Error applying pattern '%s': %s", name, exc)
        return result

    def sanitize_entry(self, entry: RetrospectiveEntry) -> RetrospectiveEntry:
        """Return a new RetrospectiveEntry with sanitized content and tags."""
        return RetrospectiveEntry(id=entry.id, content=self.sanitize_text(entry.content), sentiment=entry.sentiment, timestamp=entry.timestamp, contributor=entry.contributor, tags=[self.sanitize_text(tag) for tag in entry.tags], phase_context=entry.phase_context)

    def sanitize_retrospective(self, data: RetrospectiveData) -> RetrospectiveData:
        """Return a new RetrospectiveData with all text fields sanitized."""
        return RetrospectiveData(task_id=data.task_id, task_summary=self.sanitize_text(data.task_summary), went_well=[self.sanitize_entry(e) for e in data.went_well], went_poorly=[self.sanitize_entry(e) for e in data.went_poorly], action_items=[self.sanitize_text(item) for item in data.action_items], metadata={k: self.sanitize_text(v) if isinstance(v, str) else v for k, v in data.metadata.items()}, timestamp=data.timestamp)

    def sanitize_lesson(self, lesson: Lesson) -> Lesson:
        """Return a new Lesson with sanitized summary and detail."""
        return Lesson(id=lesson.id, summary=self.sanitize_text(lesson.summary), detail=self.sanitize_text(lesson.detail), category=lesson.category, severity=lesson.severity, tags=[self.sanitize_text(tag) for tag in lesson.tags], source_task_id=lesson.source_task_id, source_entry_ids=list(lesson.source_entry_ids), timestamp=lesson.timestamp, anti_pattern_ids=list(lesson.anti_pattern_ids))

    def sanitize_finding(self, finding: AntiPatternFinding) -> AntiPatternFinding:
        """Return a new AntiPatternFinding with sanitized evidence."""
        return AntiPatternFinding(id=finding.id, anti_pattern_id=finding.anti_pattern_id, anti_pattern_name=finding.anti_pattern_name, evidence=[self.sanitize_text(e) for e in finding.evidence], source_entry_ids=list(finding.source_entry_ids), remediation=self.sanitize_text(finding.remediation), severity=finding.severity, timestamp=finding.timestamp)

class AntiPatternDetector:
    """Detects known anti-patterns from retrospective text using keyword and regex matching.

    The detector scans all entries (both went_well and went_poorly) against a catalog
    of anti-pattern definitions. Each definition specifies keywords and optional regex
    patterns. A finding is produced when at least one piece of evidence is found.
    """

    def __init__(self, catalog: Optional[List[AntiPatternDefinition]]=None):
        """
        Initialize detector with a catalog of anti-patterns.

        Args:
            catalog: Custom anti-pattern catalog. If None, uses the built-in default catalog.
        """
        self.catalog: List[AntiPatternDefinition] = catalog if catalog is not None else self.default_catalog()

    @staticmethod
    def default_catalog() -> List[AntiPatternDefinition]:
        """Returns the built-in catalog of common software development anti-patterns."""
        return [AntiPatternDefinition(id='ap-001', name='Gold Plating', description='Over-engineering or adding unnecessary features beyond requirements', keywords=['gold plating', 'over-engineered', 'overengineered', 'unnecessary feature', 'scope creep', 'nice to have but'], regex_patterns=[], remediation='Focus on core requirements first. Use iterative delivery to add features based on actual demand.', category=LessonCategory.PROCESS, default_severity=Severity.MEDIUM), AntiPatternDefinition(id='ap-002', name='Premature Optimization', description="Optimizing code before it's proven to be a bottleneck", keywords=['premature optimization', 'optimized too early', 'performance before correctness', 'micro-optimization'], regex_patterns=[], remediation='Get it working first, then profile and optimize only proven bottlenecks.', category=LessonCategory.TECHNICAL, default_severity=Severity.MEDIUM), AntiPatternDefinition(id='ap-003', name='Cargo Cult Programming', description='Using code patterns or practices without understanding why', keywords=['cargo cult', 'copied without understanding', "don't know why it works", 'copied from stackoverflow', 'blindly copied'], regex_patterns=[], remediation='Understand the code you write. Review external code thoroughly before adoption.', category=LessonCategory.TECHNICAL, default_severity=Severity.HIGH), AntiPatternDefinition(id='ap-004', name='Copy-Paste Programming', description='Duplicating code instead of creating reusable abstractions', keywords=['copy paste', 'copy-paste', 'duplicated code', 'code duplication', 'copied the same', 'repeated code'], regex_patterns=[], remediation='Extract common code into functions, methods, or modules. Apply the DRY principle.', category=LessonCategory.TECHNICAL, default_severity=Severity.MEDIUM), AntiPatternDefinition(id='ap-005', name='God Object', description='A class or object that does too many things and has too many responsibilities', keywords=['god object', 'god class', 'does everything', 'monolithic class', 'single class handles all', 'too many responsibilities'], regex_patterns=[], remediation='Refactor into smaller, focused classes. Apply the Single Responsibility Principle.', category=LessonCategory.ARCHITECTURE, default_severity=Severity.HIGH), AntiPatternDefinition(id='ap-006', name='Spaghetti Code', description='Code with tangled control flow that is difficult to follow and maintain', keywords=['spaghetti code', 'tangled', 'unmaintainable', 'impossible to follow', 'no clear structure'], regex_patterns=[], remediation='Refactor for clarity. Break into smaller functions. Use consistent patterns.', category=LessonCategory.ARCHITECTURE, default_severity=Severity.HIGH), AntiPatternDefinition(id='ap-007', name='Lava Flow', description='Dead or obsolete code that lingers in the codebase and accumulates over time', keywords=['lava flow', 'dead code', 'unused code', 'legacy code nobody touches', 'afraid to remove'], regex_patterns=[], remediation='Regularly audit and remove dead code. Use version control to preserve history.', category=LessonCategory.TECHNICAL, default_severity=Severity.MEDIUM), AntiPatternDefinition(id='ap-008', name='Magic Numbers/Strings', description='Unexplained literal values embedded directly in code', keywords=['magic number', 'magic string', 'hardcoded value', 'hard-coded', 'unexplained constant'], regex_patterns=[], remediation='Extract magic values into named constants with clear documentation.', category=LessonCategory.TECHNICAL, default_severity=Severity.MEDIUM), AntiPatternDefinition(id='ap-009', name='Not Invented Here', description='Rejecting external libraries or solutions in favor of building from scratch', keywords=['not invented here', 'rewrote from scratch', 'built our own instead', 'refused to use library', 'nih syndrome'], regex_patterns=[], remediation='Evaluate existing solutions objectively. Build custom only when truly necessary or demonstrably superior.', category=LessonCategory.PROCESS, default_severity=Severity.MEDIUM), AntiPatternDefinition(id='ap-010', name='Analysis Paralysis', description='Spending excessive time analyzing and planning without making progress', keywords=['analysis paralysis', 'overthinking', "couldn't decide", 'too many options', 'stuck in planning', 'debated too long'], regex_patterns=[], remediation='Set decision deadlines. Use time-boxing for analysis phases. Prioritize action over perfection.', category=LessonCategory.PLANNING, default_severity=Severity.MEDIUM)]

    def detect(self, data: RetrospectiveData) -> List[AntiPatternFinding]:
        """
        Scan all entries in the retrospective for anti-pattern indicators.

        Both ``went_well`` and ``went_poorly`` entries are scanned because
        anti-patterns can be mentioned in either context (e.g., "we avoided
        spaghetti code this time" in went_well).

        Returns:
            A list of findings, at most one per catalog entry.
        """
        findings: List[AntiPatternFinding] = []
        all_entries = list(data.went_well) + list(data.went_poorly)
        for anti_pattern in self.catalog:
            finding = self._scan_entries(all_entries, anti_pattern)
            if finding is not None:
                findings.append(finding)
        return findings

    def _scan_entries(self, entries: List[RetrospectiveEntry], anti_pattern: AntiPatternDefinition) -> Optional[AntiPatternFinding]:
        """Check entries against a single anti-pattern definition.

        Detection strategy:
        1. For each entry, check if any keyword appears in ``content.lower()``.
        2. If no keyword matched, check regex patterns.
        3. Collect matching snippets as evidence (context window around match).
        4. If at least one piece of evidence is found, produce a finding.

        Returns:
            An ``AntiPatternFinding`` if evidence is found, otherwise ``None``.
        """
        evidence: List[str] = []
        source_entry_ids: List[str] = []
        for entry in entries:
            content_lower = entry.content.lower()
            matched_this_entry = False
            for keyword in anti_pattern.keywords:
                if keyword.lower() in content_lower:
                    idx = content_lower.find(keyword.lower())
                    start = max(0, idx - 40)
                    end = min(len(entry.content), idx + len(keyword) + 40)
                    snippet = entry.content[start:end].strip()
                    if snippet and snippet not in evidence:
                        evidence.append(snippet)
                    if entry.id not in source_entry_ids:
                        source_entry_ids.append(entry.id)
                    matched_this_entry = True
                    break
            if not matched_this_entry:
                for regex_pattern in anti_pattern.regex_patterns:
                    try:
                        match = re.search(regex_pattern, entry.content, re.IGNORECASE)
                        if match:
                            snippet = match.group(0)
                            if snippet and snippet not in evidence:
                                evidence.append(snippet)
                            if entry.id not in source_entry_ids:
                                source_entry_ids.append(entry.id)
                            break
                    except re.error:
                        logger.warning("Invalid regex in anti-pattern '%s': %s", anti_pattern.name, regex_pattern)
        if evidence:
            return AntiPatternFinding(id=str(uuid.uuid4()), anti_pattern_id=anti_pattern.id, anti_pattern_name=anti_pattern.name, evidence=evidence, source_entry_ids=source_entry_ids, remediation=anti_pattern.remediation, severity=anti_pattern.default_severity, timestamp=datetime.utcnow().isoformat() + 'Z')
        return None

class LessonExtractor:
    """Extracts structured lessons from retrospective data and anti-pattern findings.

    Sources of lessons:
    - Each ``went_poorly`` entry → lesson with severity based on sentiment
    - Each ``went_well`` entry → best-practice lesson (typically LOW severity)
    - Each action item → PROCESS lesson at MEDIUM severity
    - Each anti-pattern finding → lesson linking to the finding

    Deduplication removes lessons with overlapping summaries within the same category.
    """
    _FINDING_CATEGORY_MAP: Dict[str, LessonCategory] = {'Gold Plating': LessonCategory.PROCESS, 'Premature Optimization': LessonCategory.TECHNICAL, 'Cargo Cult Programming': LessonCategory.TECHNICAL, 'Copy-Paste Programming': LessonCategory.TECHNICAL, 'God Object': LessonCategory.ARCHITECTURE, 'Spaghetti Code': LessonCategory.ARCHITECTURE, 'Lava Flow': LessonCategory.TECHNICAL, 'Magic Numbers/Strings': LessonCategory.TECHNICAL, 'Not Invented Here': LessonCategory.PROCESS, 'Analysis Paralysis': LessonCategory.PLANNING}
    _SENTIMENT_SEVERITY: Dict[SentimentType, Severity] = {SentimentType.POSITIVE: Severity.LOW, SentimentType.NEGATIVE: Severity.HIGH, SentimentType.NEUTRAL: Severity.MEDIUM}

    def extract(self, data: RetrospectiveData, findings: List[AntiPatternFinding]) -> List[Lesson]:
        """
        Extract and deduplicate lessons from all sources.

        Args:
            data: The retrospective input data.
            findings: Anti-pattern findings from the detector.

        Returns:
            Deduplicated list of Lesson objects.
        """
        lessons: List[Lesson] = []
        for entry in data.went_poorly:
            lessons.append(self._entry_to_lesson(entry, data.task_id))
        for entry in data.went_well:
            lessons.append(self._entry_to_lesson(entry, data.task_id))
        for action_item in data.action_items:
            if action_item and action_item.strip():
                lessons.append(self._action_item_to_lesson(action_item, data.task_id))
        for finding in findings:
            lessons.append(self._finding_to_lesson(finding, data.task_id))
        return self._deduplicate(lessons)

    def _infer_category(self, entry: RetrospectiveEntry) -> LessonCategory:
        """Infer the most appropriate category from entry context and content."""
        context_lower = entry.phase_context.lower()
        content_lower = entry.content.lower()
        combined = context_lower + ' ' + content_lower
        if 'architecture' in combined or 'design' in combined:
            return LessonCategory.ARCHITECTURE
        if 'test' in combined:
            return LessonCategory.TESTING
        if 'communicat' in combined:
            return LessonCategory.COMMUNICATION
        if 'document' in combined:
            return LessonCategory.DOCUMENTATION
        if 'tool' in combined:
            return LessonCategory.TOOLING
        if 'plan' in combined:
            return LessonCategory.PLANNING
        if entry.sentiment == SentimentType.NEGATIVE:
            return LessonCategory.TECHNICAL
        return LessonCategory.OTHER

    def _entry_to_lesson(self, entry: RetrospectiveEntry, task_id: str) -> Lesson:
        """Convert a retrospective entry to a lesson."""
        severity = self._SENTIMENT_SEVERITY.get(entry.sentiment, Severity.MEDIUM)
        category = self._infer_category(entry)
        summary = entry.content[:100]
        if len(entry.content) > 100:
            summary += '...'
        return Lesson(id=str(uuid.uuid4()), summary=summary, detail=entry.content, category=category, severity=severity, tags=list(entry.tags), source_task_id=task_id, source_entry_ids=[entry.id], timestamp=datetime.utcnow().isoformat() + 'Z', anti_pattern_ids=[])

    def _finding_to_lesson(self, finding: AntiPatternFinding, task_id: str) -> Lesson:
        """Convert an anti-pattern finding to a lesson."""
        category = self._FINDING_CATEGORY_MAP.get(finding.anti_pattern_name, LessonCategory.TECHNICAL)
        return Lesson(id=str(uuid.uuid4()), summary=f'Anti-pattern detected: {finding.anti_pattern_name}', detail=finding.remediation, category=category, severity=finding.severity, tags=[finding.anti_pattern_name.lower().replace(' ', '-'), 'anti-pattern'], source_task_id=task_id, source_entry_ids=list(finding.source_entry_ids), timestamp=datetime.utcnow().isoformat() + 'Z', anti_pattern_ids=[finding.anti_pattern_id])

    def _action_item_to_lesson(self, action_item: str, task_id: str) -> Lesson:
        """Convert an action item string to a lesson."""
        summary = action_item[:100]
        if len(action_item) > 100:
            summary += '...'
        return Lesson(id=str(uuid.uuid4()), summary=summary, detail=action_item, category=LessonCategory.PROCESS, severity=Severity.MEDIUM, tags=['action-item'], source_task_id=task_id, source_entry_ids=[], timestamp=datetime.utcnow().isoformat() + 'Z', anti_pattern_ids=[])

    @staticmethod
    def _deduplicate(lessons: List[Lesson]) -> List[Lesson]:
        """Remove lessons with highly overlapping summaries within the same category.

        Two lessons are considered duplicates if they share the same category and
        at least 3 significant (length > 2) words in their summaries.
        """
        if not lessons:
            return lessons
        by_category: Dict[LessonCategory, List[Lesson]] = {}
        for lesson in lessons:
            by_category.setdefault(lesson.category, []).append(lesson)
        result: List[Lesson] = []
        for _category, group in by_category.items():
            seen_word_sets: List[set] = []
            for lesson in group:
                words = {w for w in lesson.summary.lower().split() if len(w) > 2}
                is_duplicate = False
                for seen_words in seen_word_sets:
                    overlap = seen_words & words
                    if len(overlap) >= 3:
                        is_duplicate = True
                        break
                if not is_duplicate:
                    seen_word_sets.append(words)
                    result.append(lesson)
        return result

class LessonsProvider(Protocol):
    """Protocol defining the interface for lesson storage backends.

    Any object implementing these methods can be used as a lessons provider,
    enabling swapping between in-memory, database, or remote storage backends.
    """

    def ingest(self, lessons: List[Lesson]) -> int:
        """Store lessons. Returns count of successfully stored lessons."""
        ...

    def query_by_tags(self, tags: List[str], match_all: bool=False) -> List[Lesson]:
        """Retrieve lessons matching given tags.

        Args:
            tags: Tags to search for.
            match_all: If True, all tags must be present. If False, any tag matches.
        """
        ...

    def query_by_category(self, category: LessonCategory) -> List[Lesson]:
        """Retrieve lessons of a specific category."""
        ...

    def query_recent(self, count: int=10) -> List[Lesson]:
        """Retrieve the N most recent lessons."""
        ...

    def get_all(self) -> List[Lesson]:
        """Retrieve all stored lessons."""
        ...

    def get_by_id(self, lesson_id: str) -> Optional[Lesson]:
        """Retrieve a single lesson by ID."""
        ...

    def get_by_task_id(self, task_id: str) -> List[Lesson]:
        """Retrieve all lessons from a specific task."""
        ...

class InMemoryLessonsProvider:
    """Default in-memory implementation of LessonsProvider.

    Thread-safe via ``threading.Lock``. Suitable for testing, single-process
    usage, and as a reference implementation for the protocol.
    """

    def __init__(self) -> None:
        self._lessons: List[Lesson] = []
        self._index_by_id: Dict[str, Lesson] = {}
        self._lock = threading.Lock()

    def ingest(self, lessons: List[Lesson]) -> int:
        """Store lessons, skipping any with empty/missing IDs or duplicate IDs."""
        count = 0
        with self._lock:
            for lesson in lessons:
                if lesson and lesson.id and (lesson.id not in self._index_by_id):
                    self._lessons.append(lesson)
                    self._index_by_id[lesson.id] = lesson
                    count += 1
        logger.info('Ingested %d lesson(s) into provider', count)
        return count

    def query_by_tags(self, tags: List[str], match_all: bool=False) -> List[Lesson]:
        """Retrieve lessons matching given tags."""
        if not tags:
            return []
        tag_set = set(tags)
        with self._lock:
            if match_all:
                return [ls for ls in self._lessons if tag_set.issubset(ls.tags)]
            return [ls for ls in self._lessons if tag_set & set(ls.tags)]

    def query_by_category(self, category: LessonCategory) -> List[Lesson]:
        """Retrieve lessons of a specific category."""
        with self._lock:
            return [ls for ls in self._lessons if ls.category == category]

    def query_recent(self, count: int=10) -> List[Lesson]:
        """Retrieve the N most recent lessons, sorted by timestamp descending."""
        with self._lock:
            sorted_lessons = sorted(self._lessons, key=lambda ls: ls.timestamp, reverse=True)
            return sorted_lessons[:count]

    def get_all(self) -> List[Lesson]:
        """Retrieve all stored lessons."""
        with self._lock:
            return list(self._lessons)

    def get_by_id(self, lesson_id: str) -> Optional[Lesson]:
        """Retrieve a single lesson by ID. O(1) lookup."""
        with self._lock:
            return self._index_by_id.get(lesson_id)

    def get_by_task_id(self, task_id: str) -> List[Lesson]:
        """Retrieve all lessons from a specific task."""
        with self._lock:
            return [ls for ls in self._lessons if ls.source_task_id == task_id]

class RetrospectivePhase:
    """Top-level orchestrator for the retrospective phase.

    Pipeline stages:
    1. **Validate** – ensure input data meets minimum requirements.
    2. **Detect** – scan for anti-patterns in raw (unsanitized) text.
    3. **Extract** – derive structured lessons from entries, action items, and findings.
    4. **Sanitize** – redact sensitive data from lessons and findings (optional).
    5. **Ingest** – persist sanitized lessons into the LessonsProvider.
    6. **Summarize** – build a human-readable result.

    All dependencies are injectable for testing and customization.
    """

    def __init__(self, lessons_provider: Optional[Any]=None, sanitizer: Optional[RetrospectiveSanitizer]=None, detector: Optional[AntiPatternDetector]=None, extractor: Optional[LessonExtractor]=None, enable_sanitization: bool=True, logger_override: Optional[logging.Logger]=None):
        """
        Initialize the retrospective phase.

        Args:
            lessons_provider: LessonsProvider-compatible object. Defaults to InMemoryLessonsProvider.
            sanitizer: Custom sanitizer. Defaults to a new RetrospectiveSanitizer.
            detector: Custom anti-pattern detector. Defaults to one with the built-in catalog.
            extractor: Custom lesson extractor. Defaults to a new LessonExtractor.
            enable_sanitization: Whether to sanitize data before ingestion (default True).
            logger_override: Custom logger. Defaults to module-level logger.
        """
        self.lessons_provider = lessons_provider or InMemoryLessonsProvider()
        self.sanitizer = sanitizer or RetrospectiveSanitizer()
        self.detector = detector or AntiPatternDetector()
        self.extractor = extractor or LessonExtractor()
        self.enable_sanitization = enable_sanitization
        self._log = logger_override or logger

    def run(self, data: RetrospectiveData) -> RetrospectiveResult:
        """
        Execute the full retrospective pipeline.

        Args:
            data: Complete retrospective input data.

        Returns:
            RetrospectiveResult containing lessons, findings, and summary.

        Raises:
            ValueError: If input data fails validation.
        """
        self._log.info("Starting retrospective phase for task '%s'", data.task_id)
        self._validate(data)
        self._log.info('Detecting anti-patterns...')
        findings = self.detector.detect(data)
        self._log.info('Found %d anti-pattern(s)', len(findings))
        for finding in findings:
            self._log.warning('  Anti-pattern: %s (severity=%s)', finding.anti_pattern_name, finding.severity.value)
        self._log.info('Extracting lessons...')
        lessons = self.extractor.extract(data, findings)
        self._log.info('Extracted %d lesson(s)', len(lessons))
        sanitized = False
        if self.enable_sanitization:
            self._log.info('Sanitizing lessons and findings...')
            lessons = [self.sanitizer.sanitize_lesson(ls) for ls in lessons]
            findings = [self.sanitizer.sanitize_finding(f) for f in findings]
            sanitized = True
        ingested = False
        self._log.info('Ingesting lessons into provider...')
        try:
            count = self.lessons_provider.ingest(lessons)
            ingested = count > 0
            self._log.info('Successfully ingested %d/%d lessons', count, len(lessons))
        except Exception as exc:
            self._log.error('Failed to ingest lessons: %s', exc)
        summary = self._build_summary(data, lessons, findings)
        self._log.info("Retrospective complete for task '%s'", data.task_id)
        return RetrospectiveResult(task_id=data.task_id, lessons=lessons, anti_pattern_findings=findings, sanitized=sanitized, ingested=ingested, summary=summary, timestamp=datetime.utcnow().isoformat() + 'Z')

    def _validate(self, data: RetrospectiveData) -> None:
        """Validate retrospective input data.

        Raises:
            ValueError: If task_id is empty or no entries exist.
        """
        if not data.task_id or not data.task_id.strip():
            raise ValueError('Retrospective data must have a non-empty task_id')
        if not data.went_well and (not data.went_poorly):
            raise ValueError('Retrospective must have at least one observation entry in went_well or went_poorly')

    @staticmethod
    def _build_summary(data: RetrospectiveData, lessons: List[Lesson], findings: List[AntiPatternFinding]) -> str:
        """Build a human-readable summary string."""
        categories = sorted({ls.category.value for ls in lessons})
        category_str = ', '.join(categories) if categories else '(none)'
        top_items = data.action_items[:3] if data.action_items else ['(none)']
        items_str = '; '.join(top_items)
        return f'Retrospective for task {data.task_id}: {len(lessons)} lesson(s) captured, {len(findings)} anti-pattern(s) identified. Categories: {category_str}. Top action items: {items_str}'

class AntiPatternType(Enum):
    """Enumeration of detectable anti-pattern types."""
    GOD_CLASS = 'god_class'
    PREMATURE_OPTIMIZATION = 'premature_optimization'
    COPY_PASTE = 'copy_paste'
    MISSING_ERROR_HANDLING = 'missing_error_handling'
    TIGHT_COUPLING = 'tight_coupling'
    MAGIC_NUMBERS = 'magic_numbers'
    DEEP_NESTING = 'deep_nesting'
    INSUFFICIENT_TESTING = 'insufficient_testing'
    OVER_ENGINEERING = 'over_engineering'
    NO_DOCUMENTATION = 'no_documentation'

@dataclass
class AntiPattern:
    """Represents a detected anti-pattern.

    Attributes:
        id: Unique identifier (auto-generated UUID).
        pattern_type: The type of anti-pattern detected.
        description: Human-readable description of the detection.
        location: Where the anti-pattern was found (e.g. task/phase reference).
        suggestion: Recommended remediation action.
        severity: Severity level indicating urgency of remediation.
        detected_at: UTC timestamp of detection.
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    pattern_type: AntiPatternType = AntiPatternType.GOD_CLASS
    description: str = ''
    location: str = ''
    suggestion: str = ''
    severity: Severity = Severity.MEDIUM
    detected_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

@dataclass
class RetrospectiveContext:
    """Input context for retrospective analysis.

    Attributes:
        task_id: Identifier for the task being reviewed.
        phase_name: Name of the workflow phase being reviewed.
        outcomes: List of outcome statements from the phase.
        observations: List of observations made during the phase.
        code_snippets: List of relevant code snippets for analysis.
        metadata: Arbitrary key-value metadata.
        duration_seconds: How long the phase took to execute.
        success: Whether the phase completed successfully.
    """
    task_id: str = ''
    phase_name: str = ''
    outcomes: list[str] = field(default_factory=list)
    observations: list[str] = field(default_factory=list)
    code_snippets: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    duration_seconds: float = 0.0
    success: bool = True

@dataclass(frozen=True)
class RetrospectiveReport:
    """Immutable retrospective analysis report.

    Attributes:
        report_id: Unique identifier for this report.
        task_id: Identifier of the reviewed task.
        phase_name: Name of the reviewed phase.
        lessons: Tuple of captured and sanitized lessons.
        anti_patterns: Tuple of detected and sanitized anti-patterns.
        summary: Human-readable summary of the retrospective.
        created_at: UTC timestamp of report creation.
        success: Whether the original phase was successful.
    """
    report_id: str
    task_id: str
    phase_name: str
    lessons: tuple[Lesson, ...]
    anti_patterns: tuple[AntiPattern, ...]
    summary: str
    created_at: datetime
    success: bool

class AntiPatternCategory(enum.Enum):
    """Categories of anti-patterns that can be detected."""
    GOD_CLASS = 'god_class'
    DEEP_NESTING = 'deep_nesting'
    HARDCODED_SECRETS = 'hardcoded_secrets'
    CIRCULAR_DEPENDENCY = 'circular_dependency'
    COPY_PASTE = 'copy_paste'
    MAGIC_NUMBERS = 'magic_numbers'
    LONG_METHOD = 'long_method'
    BROAD_EXCEPTION = 'broad_exception'
    UNUSED_IMPORTS = 'unused_imports'
    MISSING_DOCSTRING = 'missing_docstring'

class Sanitizer:
    """Strips sensitive information from retrospective data.

    Applies a set of regex-based redaction rules to replace secrets, tokens,
    email addresses, IP addresses, and user paths with safe placeholders.

    Custom patterns can be supplied at construction time via *extra_patterns*.
    """
    _PATTERNS: List[tuple[str, str]] = [('(?i)(api[_-]?key|apikey|secret[_-]?key|access[_-]?token|auth[_-]?token)\\s*[=:]\\s*[\\"\']?[\\w\\-\\.]{8,}[\\"\']?', '\\1=<REDACTED>'), ('AKIA[0-9A-Z]{16}', '<REDACTED_AWS_KEY>'), ('(?i)bearer\\s+[\\w\\-\\.]+', 'Bearer <REDACTED>'), ('(?i)(password|passwd|pwd)\\s*[=:]\\s*[\\"\']?[^\\s\\"\']{1,}[\\"\']?', '\\1=<REDACTED>'), ('[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\\.[a-zA-Z0-9-.]+', '<REDACTED_EMAIL>'), ('\\b\\d{1,3}\\.\\d{1,3}\\.\\d{1,3}\\.\\d{1,3}\\b', '<REDACTED_IP>'), ('/home/[a-zA-Z0-9_\\-]+', '/home/<REDACTED_USER>'), ('C:\\\\Users\\\\[a-zA-Z0-9_\\-]+', 'C:\\\\Users\\\\<REDACTED_USER>'), ('\\b[0-9a-fA-F]{32,}\\b', '<REDACTED_TOKEN>')]

    def __init__(self, extra_patterns: Optional[List[tuple[str, str]]]=None) -> None:
        """Initialize sanitizer with compiled regex patterns.

        Args:
            extra_patterns: Additional ``(pattern, replacement)`` tuples.
        """
        self._compiled: List[tuple[re.Pattern[str], str]] = []
        all_patterns = self._PATTERNS + (extra_patterns or [])
        for pattern_str, replacement in all_patterns:
            self._compiled.append((re.compile(pattern_str), replacement))

    def sanitize_string(self, text: str) -> str:
        """Sanitize a single string by applying all redaction patterns.

        Args:
            text: The string to sanitize.

        Returns:
            The sanitized string with sensitive data redacted.
        """
        result = text
        for pattern, replacement in self._compiled:
            result = pattern.sub(replacement, result)
        return result

    def sanitize_list(self, items: List[str]) -> List[str]:
        """Sanitize each string in a list.

        Args:
            items: List of strings to sanitize.

        Returns:
            List of sanitized strings.
        """
        return [self.sanitize_string(item) for item in items]

    def sanitize(self, data: RetrospectiveData) -> RetrospectiveData:
        """Return a sanitized **copy** of the retrospective data.

        The original ``data`` object is not modified.

        Args:
            data: The original retrospective data.

        Returns:
            A new :class:`RetrospectiveData` with all sensitive info redacted.
        """
        sanitized_entry = RetrospectiveEntry(what_went_well=self.sanitize_list(data.entry.what_went_well), what_went_poorly=self.sanitize_list(data.entry.what_went_poorly), action_items=self.sanitize_list(data.entry.action_items), notes=self.sanitize_string(data.entry.notes))
        sanitized_anti_patterns = [AntiPattern(category=ap.category, description=self.sanitize_string(ap.description), severity=ap.severity, location=self.sanitize_string(ap.location) if ap.location else ap.location, suggestion=self.sanitize_string(ap.suggestion)) for ap in data.anti_patterns]
        sanitized_lessons = [Lesson(id=lesson.id, timestamp=lesson.timestamp, title=self.sanitize_string(lesson.title), description=self.sanitize_string(lesson.description), tags=lesson.tags[:], severity=lesson.severity, source_phase=lesson.source_phase, anti_patterns=[AntiPattern(category=ap.category, description=self.sanitize_string(ap.description), severity=ap.severity, location=self.sanitize_string(ap.location) if ap.location else ap.location, suggestion=self.sanitize_string(ap.suggestion)) for ap in lesson.anti_patterns]) for lesson in data.lessons]
        return RetrospectiveData(task_id=data.task_id, task_description=self.sanitize_string(data.task_description), entry=sanitized_entry, anti_patterns=sanitized_anti_patterns, lessons=sanitized_lessons, metadata={k: self.sanitize_string(str(v)) for k, v in data.metadata.items()}, raw_code_artifacts=self.sanitize_list(data.raw_code_artifacts), raw_logs=self.sanitize_list(data.raw_logs))

@dataclass
class RetrospectiveInput:
    """Input data for the retrospective phase."""
    phase_name: str
    task_description: str
    what_went_well: List[str] = field(default_factory=list)
    what_went_poorly: List[str] = field(default_factory=list)
    action_items: List[str] = field(default_factory=list)
    raw_notes: str = ''
    severity: Severity = Severity.MEDIUM
    metadata: Dict[str, Any] = field(default_factory=dict)

class PhaseStatus(Enum):
    """Status of the retrospective phase execution."""
    NOT_STARTED = 'not_started'
    IN_PROGRESS = 'in_progress'
    COMPLETED = 'completed'
    FAILED = 'failed'

@dataclass
class SanitizationReport:
    """Report of sanitization operations performed."""
    original_count: int
    sanitized_count: int
    redactions: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert report to dictionary representation."""
        return {'original_count': self.original_count, 'sanitized_count': self.sanitized_count, 'redactions': self.redactions}

class AntiPatternIdentifier:
    """Identifies anti-patterns in task context and code.

    Each detector is a method that receives the full task context dictionary and
    returns an ``AntiPattern`` instance when the pattern is found, or ``None``
    otherwise.  Detectors are executed in registration order and failures in
    individual detectors are logged but do not abort the analysis.
    """

    def __init__(self) -> None:
        """Initialize anti-pattern identifier with registered detectors."""
        self._detectors: dict[AntiPatternType, Callable[[dict], AntiPattern | None]] = {AntiPatternType.GOD_CLASS: self._detect_god_class, AntiPatternType.COPY_PASTE: self._detect_copy_paste, AntiPatternType.MAGIC_NUMBERS: self._detect_hardcoded_secrets, AntiPatternType.MISSING_ERROR_HANDLING: self._detect_missing_error_handling, AntiPatternType.TIGHT_COUPLING: self._detect_tight_coupling, AntiPatternType.DEEP_NESTING: self._detect_deep_nesting, AntiPatternType.INSUFFICIENT_TESTING: self._detect_no_tests}
        self.logger = logging.getLogger(__name__)

    def identify(self, task_context: dict) -> list[AntiPattern]:
        """Run all detectors against task context.

        Args:
            task_context: Context dictionary containing code, files, etc.

        Returns:
            List of identified anti-patterns.
        """
        anti_patterns: list[AntiPattern] = []
        for pattern_type, detector in self._detectors.items():
            try:
                result = detector(task_context)
                if result is not None:
                    anti_patterns.append(result)
            except Exception as err:
                self.logger.debug('Detector %s raised an error: %s', pattern_type.value, err)
        return anti_patterns

    def _detect_god_class(self, context: dict) -> AntiPattern | None:
        """Detect god class pattern (too many methods or lines)."""
        code = context.get('code', '')
        classes = context.get('classes', [])
        for class_info in classes:
            class_name = class_info.get('name', '')
            if not class_name:
                continue
            method_count = _count_methods_in_code(code, class_name)
            if method_count > 10:
                return AntiPattern(pattern_type=AntiPatternType.GOD_CLASS, description=f"Class '{class_name}' has {method_count} methods", location=class_name, severity='high', recommendation='Consider breaking the class into smaller, focused classes following Single Responsibility Principle')
        code_lines = len(code.split('\n'))
        if code_lines > 300:
            return AntiPattern(pattern_type=AntiPatternType.GOD_CLASS, description=f'Code file has {code_lines} lines (exceeds 300)', location='file', severity='medium', recommendation='Consider splitting into multiple files/classes')
        return None

    def _detect_copy_paste(self, context: dict) -> AntiPattern | None:
        """Detect copy-paste code pattern."""
        code = context.get('code', '')
        if _detect_duplicate_blocks(code):
            return AntiPattern(pattern_type=AntiPatternType.COPY_PASTE, description='Duplicate code blocks detected', location='code', severity='medium', recommendation='Extract duplicate blocks into shared functions or use inheritance')
        return None

    def _detect_hardcoded_secrets(self, context: dict) -> AntiPattern | None:
        """Detect hardcoded secrets pattern."""
        code = context.get('code', '')
        secret_patterns = ['(?i)(password|secret|key|token)\\s*=\\s*[\'\\"].*[\'\\"]']
        for pattern in secret_patterns:
            if re.search(pattern, code):
                return AntiPattern(pattern_type=AntiPatternType.HARDCODED_SECRETS, description='Hardcoded secrets or sensitive values detected', location='code', severity='high', recommendation='Use environment variables or secure vaults for sensitive data')
        return None

    def _detect_missing_error_handling(self, context: dict) -> AntiPattern | None:
        """Detect missing error handling pattern."""
        code = context.get('code', '')
        if _has_external_calls(code) and (not _has_try_except(code)):
            return AntiPattern(pattern_type=AntiPatternType.MISSING_ERROR_HANDLING, description='External calls detected without try/except blocks', location='code', severity='high', recommendation='Wrap external calls in try/except blocks with appropriate error handling')
        return None

    def _detect_tight_coupling(self, context: dict) -> AntiPattern | None:
        """Detect tight coupling pattern via excessive imports."""
        code = context.get('code', '')
        import_count = _count_imports(code)
        if import_count > 10:
            return AntiPattern(pattern_type=AntiPatternType.TIGHT_COUPLING, description=f'High number of imports ({import_count}) detected', location='code', severity='medium', recommendation='Refactor to reduce dependencies. Consider using dependency injection or interfaces')
        return None

    def _detect_magic_numbers(self, context: dict) -> AntiPattern | None:
        """Detect magic numbers pattern."""
        code = context.get('code', '')
        if _has_magic_numbers(code):
            return AntiPattern(pattern_type=AntiPatternType.MAGIC_NUMBERS, description='Unexplained numeric literals (magic numbers) detected', location='code', severity='low', recommendation='Replace magic numbers with named constants')
        return None

    def _detect_deep_nesting(self, context: dict) -> AntiPattern | None:
        """Detect deep nesting pattern."""
        code = context.get('code', '')
        max_depth = _count_nesting_depth(code)
        if max_depth > 4:
            return AntiPattern(pattern_type=AntiPatternType.DEEP_NESTING, description=f'Deep nesting detected (depth: {max_depth})', location='code', severity='medium', recommendation='Refactor to reduce nesting depth. Use early returns, extract methods, or guards')
        return None

    def _detect_no_tests(self, context: dict) -> AntiPattern | None:
        """Detect missing tests pattern."""
        test_results = context.get('test_results')
        files = context.get('files', [])
        has_test_files = any(('test' in f.lower() or f.endswith('_test.py') for f in files))
        if test_results is None and (not has_test_files):
            return AntiPattern(pattern_type=AntiPatternType.NO_TESTS, description='No test files or test results found', location='project', severity='high', recommendation='Write unit tests to ensure code quality and prevent regressions')
        return None

@dataclasses.dataclass
class RawRetrospectiveData:
    """
    Raw data gathered during retrospective.

    Attributes:
        what_went_well: Items that went well.
        what_went_poorly: Items that need improvement.
        action_items: Action items identified.
        artifacts: Code or document artifacts examined.
        metadata: Additional metadata about the retrospective.
    """
    what_went_well: List[str] = dataclasses.field(default_factory=list)
    what_went_poorly: List[str] = dataclasses.field(default_factory=list)
    action_items: List[str] = dataclasses.field(default_factory=list)
    artifacts: List[str] = dataclasses.field(default_factory=list)
    metadata: Dict[str, str] = dataclasses.field(default_factory=dict)

@dataclasses.dataclass
class IngestionResult:
    """
    Result of lesson ingestion into the provider.

    Attributes:
        total_lessons: Total number of lessons to ingest.
        ingested_count: Number successfully ingested.
        failed_count: Number that failed to ingest.
        errors: List of error messages.
    """
    total_lessons: int = 0
    ingested_count: int = 0
    failed_count: int = 0
    errors: List[str] = dataclasses.field(default_factory=list)

def run_retrospective(task_id: str, task_summary: str, went_well: List[Dict[str, Any]], went_poorly: List[Dict[str, Any]], action_items: Optional[List[str]]=None, metadata: Optional[Dict[str, Any]]=None, lessons_provider: Optional[Any]=None, enable_sanitization: bool=True) -> RetrospectiveResult:
    """
    Convenience function that constructs RetrospectiveData from raw dicts
    and runs the full retrospective pipeline.

    Each dict in ``went_well`` / ``went_poorly`` supports:
    - ``content`` (str, required): The observation text.
    - ``sentiment`` (str, optional): "positive", "negative", or "neutral".
    - ``tags`` (List[str], optional): Freeform tags.
    - ``contributor`` (str, optional): Defaults to "system".
    - ``phase_context`` (str, optional): Defaults to "general".

    Args:
        task_id: The task or sprint identifier.
        task_summary: Human-readable summary of the task.
        went_well: Observations about what worked.
        went_poorly: Observations about what didn't work.
        action_items: Concrete next steps.
        metadata: Arbitrary metadata dict.
        lessons_provider: Optional LessonsProvider. Defaults to InMemoryLessonsProvider.
        enable_sanitization: Whether to sanitize output (default True).

    Returns:
        RetrospectiveResult from the completed pipeline.
    """

    def _dict_to_entry(d: Dict[str, Any], default_sentiment: SentimentType) -> RetrospectiveEntry:
        """Convert a dict to a RetrospectiveEntry with sensible defaults."""
        raw_sentiment = d.get('sentiment', default_sentiment.value)
        try:
            sentiment = SentimentType(raw_sentiment)
        except ValueError:
            sentiment = default_sentiment
        return RetrospectiveEntry(id=d.get('id', str(uuid.uuid4())), content=d.get('content', ''), sentiment=sentiment, timestamp=d.get('timestamp', datetime.utcnow().isoformat() + 'Z'), contributor=d.get('contributor', 'system'), tags=list(d.get('tags', [])), phase_context=d.get('phase_context', 'general'))
    went_well_entries = [_dict_to_entry(d, SentimentType.POSITIVE) for d in went_well]
    went_poorly_entries = [_dict_to_entry(d, SentimentType.NEGATIVE) for d in went_poorly]
    data = RetrospectiveData(task_id=task_id, task_summary=task_summary, went_well=went_well_entries, went_poorly=went_poorly_entries, action_items=action_items or [], metadata=metadata or {}, timestamp=datetime.utcnow().isoformat() + 'Z')
    phase = RetrospectivePhase(lessons_provider=lessons_provider, enable_sanitization=enable_sanitization)
    return phase.run(data)

ANTI_PATTERN_SUGGESTIONS: Dict[AntiPatternType, str] = {
    AntiPatternType.GOD_CLASS: 'Break the class into smaller, single-responsibility classes.',
    AntiPatternType.COPY_PASTE: 'Extract common logic into shared functions or base classes.',
    AntiPatternType.PREMATURE_OPTIMIZATION: 'Focus on correctness first; optimize only after profiling.',
    AntiPatternType.INSUFFICIENT_TESTING: 'Add unit and integration tests before merging.',
    AntiPatternType.MAGIC_NUMBERS: 'Replace magic numbers with named constants.',
    AntiPatternType.TIGHT_COUPLING: 'Introduce interfaces or dependency injection.',
    AntiPatternType.MISSING_ERROR_HANDLING: 'Add proper try/except blocks with specific exception types.',
    AntiPatternType.DEEP_NESTING: 'Refactor into smaller functions; reduce nesting depth.',
    AntiPatternType.OVER_ENGINEERING: 'Simplify the design; focus on current requirements.',
    AntiPatternType.NO_DOCUMENTATION: 'Add docstrings and inline comments for complex logic.',
}

ANTI_PATTERN_KEYWORDS: Dict[AntiPatternType, List[str]] = {
    AntiPatternType.GOD_CLASS: ['god object', 'god class', 'does everything', 'monolithic class', 'single class handles all'],
    AntiPatternType.COPY_PASTE: ['copy paste', 'copy-paste', 'duplicated code', 'code duplication', 'copied from'],
    AntiPatternType.PREMATURE_OPTIMIZATION: ['premature optimization', 'optimized too early', 'over-optimized', 'unnecessary optimization'],
    AntiPatternType.INSUFFICIENT_TESTING: ['no tests', 'missing tests', 'untested', 'no unit test', 'skipped testing', 'without tests'],
    AntiPatternType.MAGIC_NUMBERS: ['magic number', 'magic numbers', 'unexplained constant', 'unnamed constant', 'hardcoded', 'hard-coded'],
    AntiPatternType.TIGHT_COUPLING: ['tight coupling', 'tightly coupled', 'direct dependency', 'cannot be tested independently'],
    AntiPatternType.MISSING_ERROR_HANDLING: ['no error handling', 'no exception', 'bare except', 'swallowed exception', 'missing error handling', 'no try'],
    AntiPatternType.DEEP_NESTING: ['deeply nested', 'too many levels', 'excessive nesting'],
    AntiPatternType.OVER_ENGINEERING: ['too complex', 'overly complex', 'cyclomatic complexity', 'spaghetti', 'over-engineered'],
    AntiPatternType.NO_DOCUMENTATION: ['no documentation', 'missing docs', 'undocumented', 'no docstring', 'missing documentation'],
}

SANITIZATION_PATTERNS: List[Tuple[str, str]] = [
    (r'(?i)(api[_-]?key|apikey|api[_-]?secret)\s*[:=]\s*\S+', r'\1=***REDACTED***'),
    (r'(?i)(bearer\s+)\S+', r'\1***REDACTED***'),
    (r'(?i)(password|passwd|pwd)\s*[:=]\s*\S+', r'\1=***REDACTED***'),
    (r'(?i)(token|secret|credential)\s*[:=]\s*\S+', r'\1=***REDACTED***'),
    (r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+', '***EMAIL_REDACTED***'),
    (r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b', '***IP_REDACTED***'),
    (r'/(?:home|Users)/[a-zA-Z0-9_.+-]+', '/***PATH_REDACTED***'),
    (r'(?i)C:\\Users\\[a-zA-Z0-9_.+-]+', r'C:\***PATH_REDACTED***'),
    (r'(?<![a-zA-Z0-9])[a-fA-F0-9]{32,}(?![a-zA-Z0-9])', '***TOKEN_REDACTED***'),
]

def identify_anti_patterns(texts: Sequence[str]) -> List[AntiPattern]:
    """
    Scan a sequence of text strings for known anti-pattern keywords.

    Returns a deduplicated list of ``AntiPattern`` instances (one per pattern type).

    Args:
        texts: Sequence of strings to scan (notes, descriptions, action items, etc.).

    Returns:
        List of detected ``AntiPattern`` instances.
    """
    found_patterns: Dict[AntiPatternType, AntiPattern] = {}
    for text in texts:
        if not text:
            continue
        lowered_text = text.lower()
        for pattern_type, keywords in ANTI_PATTERN_KEYWORDS.items():
            if pattern_type in found_patterns:
                continue
            for keyword in keywords:
                if keyword in lowered_text:
                    description = f"Detected '{keyword}' indicating potential {pattern_type.value} anti-pattern"
                    suggestion = ANTI_PATTERN_SUGGESTIONS.get(pattern_type, 'Address this anti-pattern.')
                    found_patterns[pattern_type] = AntiPattern(pattern_type=pattern_type, description=description, suggestion=suggestion)
                    break
    return list(found_patterns.values())

def sanitize_text(text: str) -> str:
    """
    Apply all sanitization patterns to the given text.

    Returns the redacted version with sensitive information replaced.

    Args:
        text: Raw text that may contain sensitive data.

    Returns:
        Sanitized copy of the text.
    """
    sanitized = text
    for pattern, replacement in SANITIZATION_PATTERNS:
        sanitized = re.sub(pattern, replacement, sanitized)
    return sanitized

def sanitize_lesson(lesson: Lesson) -> Lesson:
    """
    Return a new ``Lesson`` with all text fields sanitized.

    Does **not** mutate the original lesson instance.

    Args:
        lesson: The lesson to sanitize.

    Returns:
        A new ``Lesson`` with redacted text fields.
    """
    sanitized_anti_patterns = [AntiPattern(pattern_type=ap.pattern_type, description=sanitize_text(ap.description), location=sanitize_text(ap.location) if ap.location else None, suggestion=sanitize_text(ap.suggestion)) for ap in lesson.anti_patterns]
    return Lesson(id=lesson.id, timestamp=lesson.timestamp, phase_name=sanitize_text(lesson.phase_name), task_description=sanitize_text(lesson.task_description), what_went_well=[sanitize_text(item) for item in lesson.what_went_well], what_went_poorly=[sanitize_text(item) for item in lesson.what_went_poorly], action_items=[sanitize_text(item) for item in lesson.action_items], anti_patterns=sanitized_anti_patterns, severity=lesson.severity, metadata=lesson.metadata)

def create_retrospective_input(phase_name: str, task_description: str, what_went_well: Optional[List[str]]=None, what_went_poorly: Optional[List[str]]=None, action_items: Optional[List[str]]=None, raw_notes: str='', severity: Severity=Severity.MEDIUM, metadata: Optional[Dict[str, Any]]=None) -> RetrospectiveInput:
    """
    Factory function to create a ``RetrospectiveInput`` with sensible defaults.

    Args:
        phase_name: Name of the phase being retrospected.
        task_description: Description of the task that was completed.
        what_went_well: List of things that went well (default: empty).
        what_went_poorly: List of things that went poorly (default: empty).
        action_items: List of action items for improvement (default: empty).
        raw_notes: Free-form notes from the retrospective (default: empty).
        severity: Severity level of findings (default: ``MEDIUM``).
        metadata: Additional metadata (default: empty dict).

    Returns:
        A fully-populated ``RetrospectiveInput`` instance.
    """
    return RetrospectiveInput(phase_name=phase_name, task_description=task_description, what_went_well=what_went_well or [], what_went_poorly=what_went_poorly or [], action_items=action_items or [], raw_notes=raw_notes, severity=severity, metadata=metadata or {})

def _get_iso_timestamp() -> str:
    """Get current UTC time in ISO format."""
    return datetime.now(timezone.utc).isoformat()

def _count_methods_in_code(code_str: str, class_name: str) -> int:
    """Count the number of method definitions in a class code block.

    Args:
        code_str: Full source code string.
        class_name: Name of the class to inspect.

    Returns:
        Number of ``def`` statements found within the class body.
    """
    lines = code_str.split('\n')
    in_class = False
    indent_level = 0
    method_count = 0
    for line in lines:
        stripped = line.lstrip()
        if f'class {class_name}' in line:
            in_class = True
            indent_level = len(line) - len(stripped)
            continue
        if in_class:
            current_indent = len(line) - len(stripped)
            if stripped and current_indent <= indent_level:
                break
            if stripped.startswith('def '):
                method_count += 1
    return method_count

def _detect_duplicate_blocks(code_str: str, min_lines: int=4) -> bool:
    """Detect if code has duplicate blocks (simple heuristic).

    Args:
        code_str: Source code to analyse.
        min_lines: Minimum consecutive lines to consider a block.

    Returns:
        ``True`` if a duplicated block is found.
    """
    lines = code_str.split('\n')
    if len(lines) < min_lines * 2:
        return False
    seen_blocks: dict[str, int] = {}
    for idx in range(len(lines) - min_lines + 1):
        block = '\n'.join(lines[idx:idx + min_lines])
        if block.strip():
            seen_blocks[block] = seen_blocks.get(block, 0) + 1
            if seen_blocks[block] > 1:
                return True
    return False

def _has_try_except(code_str: str) -> bool:
    """Check if code contains try/except blocks."""
    return 'try:' in code_str and 'except' in code_str

def _count_imports(code_str: str) -> int:
    """Count import statements in code."""
    count = 0
    for line in code_str.split('\n'):
        stripped = line.strip()
        if stripped.startswith('import ') or stripped.startswith('from '):
            count += 1
    return count

def _has_external_calls(code_str: str) -> bool:
    """Check if code has external function/API calls."""
    patterns = ['\\brequests\\.', '\\bsocket\\.', '\\bdb\\.', '\\bAPI\\(', '\\bhttp\\.', '\\b\\.get\\(', '\\b\\.post\\(', '\\b\\.fetch\\(']
    for pattern in patterns:
        if re.search(pattern, code_str):
            return True
    return False

def _count_nesting_depth(code_str: str) -> int:
    """Count maximum nesting depth in code (assuming 4-space indentation)."""
    max_depth = 0
    for line in code_str.split('\n'):
        if line.strip():
            indent = len(line) - len(line.lstrip())
            depth = indent // 4
            if depth > max_depth:
                max_depth = depth
    return max_depth

def _has_magic_numbers(code_str: str) -> bool:
    """Check if code contains magic numbers (numeric literals outside constants).

    Numbers ``0``, ``1``, and ``-1`` are excluded as they are conventionally
    acceptable.
    """
    pattern = '\\b(?<![\\w_])(?<![A-Z_])\\d+(?![\\w_])\\b'
    matches = re.findall(pattern, code_str)
    exclude = {'0', '1', '-1'}
    for match in matches:
        if match not in exclude and (not match.startswith('0x')):
            return True
    return False
