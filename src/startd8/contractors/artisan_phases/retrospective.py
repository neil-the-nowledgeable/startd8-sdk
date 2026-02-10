"""
Retrospective Phase Module for Artisan Contractor System

This module implements a structured retrospective phase that captures lessons learned
from completed work, identifies anti-patterns, sanitizes sensitive information, and
ingests processed lessons into a LessonsProvider for future reference.

All code is self-contained in a single file with no relative imports and complies
with flake8 linting standards (E741 ambiguous variable names strictly avoided).

Usage:
    # Quick start
    context = RetrospectiveContext(
        phase_name="implementation",
        task_description="Build user authentication module",
        artifacts={"auth.py": source_code},
        process_log=["Successfully completed login flow"],
        metadata={"sprint": 42},
    )
    report = run_retrospective(context)

    # Advanced usage with custom provider and sanitization rules
    provider = InMemoryLessonsProvider()
    phase = create_retrospective_phase(
        lessons_provider=provider,
        custom_sanitization_rules=[
            SanitizationRule(
                name="internal_project",
                pattern=re.compile(r"ProjectX", re.IGNORECASE),
                replacement="[REDACTED_PROJECT]",
            )
        ],
    )
    report = phase.run(context)
    lessons = provider.query(category=LessonCategory.SECURITY)
"""

from __future__ import annotations

import abc
import dataclasses
import datetime
import enum
import json
import logging
import re
import uuid
from typing import Any, Dict, List, Optional


# ============================================================================
# Enums
# ============================================================================


class LessonCategory(enum.Enum):
    """Categories for lessons learned."""

    ARCHITECTURE = "architecture"
    IMPLEMENTATION = "implementation"
    TESTING = "testing"
    PROCESS = "process"
    COMMUNICATION = "communication"
    TOOLING = "tooling"
    PERFORMANCE = "performance"
    SECURITY = "security"
    GENERAL = "general"


class Severity(enum.Enum):
    """Severity levels for findings and lessons."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AntiPatternType(enum.Enum):
    """Types of anti-patterns that can be detected."""

    GOD_CLASS = "god_class"
    SPAGHETTI_CODE = "spaghetti_code"
    COPY_PASTE = "copy_paste"
    MAGIC_NUMBERS = "magic_numbers"
    DEEP_NESTING = "deep_nesting"
    MISSING_ERROR_HANDLING = "missing_error_handling"
    HARDCODED_SECRETS = "hardcoded_secrets"
    INSUFFICIENT_TESTING = "insufficient_testing"
    SCOPE_CREEP = "scope_creep"
    MISSING_DOCUMENTATION = "missing_documentation"
    PREMATURE_OPTIMIZATION = "premature_optimization"
    TIGHT_COUPLING = "tight_coupling"


class RetroItemType(enum.Enum):
    """Types of retrospective items."""

    WENT_WELL = "went_well"
    WENT_POORLY = "went_poorly"
    ACTION_ITEM = "action_item"
    LESSON_LEARNED = "lesson_learned"
    OBSERVATION = "observation"


# ============================================================================
# Dataclasses
# ============================================================================


@dataclasses.dataclass
class RetroItem:
    """A single retrospective item (went well, went poorly, action item, etc.)."""

    item_id: str
    item_type: RetroItemType
    description: str
    tags: List[str]
    created_at: str


@dataclasses.dataclass
class Lesson:
    """A lesson learned from a retrospective."""

    lesson_id: str
    title: str
    description: str
    category: LessonCategory
    severity: Severity
    tags: List[str]
    source_phase: str
    source_context: Dict[str, Any]
    created_at: str
    anti_pattern: Optional[str] = None


@dataclasses.dataclass
class AntiPatternFinding:
    """A detected anti-pattern in code or process."""

    finding_id: str
    pattern_type: AntiPatternType
    description: str
    evidence: str
    location: str
    severity: Severity
    recommendation: str


@dataclasses.dataclass
class RetrospectiveContext:
    """Context information for a retrospective."""

    phase_name: str
    task_description: str
    artifacts: Dict[str, str]
    process_log: List[str]
    metadata: Dict[str, Any]
    start_time: Optional[str] = None
    end_time: Optional[str] = None


@dataclasses.dataclass
class SanitizationRule:
    """A rule for sanitizing sensitive text."""

    name: str
    pattern: re.Pattern
    replacement: str


@dataclasses.dataclass
class RetrospectiveReport:
    """The final report from a retrospective phase."""

    report_id: str
    phase_name: str
    retro_items: List[RetroItem]
    lessons: List[Lesson]
    anti_pattern_findings: List[AntiPatternFinding]
    summary: str
    created_at: str
    sanitized: bool

    def to_dict(self) -> Dict[str, Any]:
        """
        Serialize the report to a plain dictionary.

        Returns:
            Dictionary representation suitable for JSON serialization.
        """
        return {
            "report_id": self.report_id,
            "phase_name": self.phase_name,
            "retro_items": [dataclasses.asdict(item) for item in self.retro_items],
            "lessons": [dataclasses.asdict(lesson) for lesson in self.lessons],
            "anti_pattern_findings": [
                dataclasses.asdict(finding) for finding in self.anti_pattern_findings
            ],
            "summary": self.summary,
            "created_at": self.created_at,
            "sanitized": self.sanitized,
        }

    def to_json(self, indent: int = 2) -> str:
        """
        Serialize the report to a JSON string.

        Args:
            indent: JSON indentation level.

        Returns:
            JSON string representation of the report.
        """
        return json.dumps(self.to_dict(), indent=indent, default=str)


# ============================================================================
# Sanitizer
# ============================================================================


class Sanitizer:
    """Sanitizes sensitive information from retrospective data.

    Applies a configurable set of regex-based rules to strip API keys,
    passwords, PII, file paths, and other sensitive content from text
    before it is stored or shared.
    """

    def __init__(self, custom_rules: Optional[List[SanitizationRule]] = None):
        """
        Initialize Sanitizer with default rules and optional custom rules.

        Args:
            custom_rules: Optional list of additional SanitizationRule objects.
        """
        self.rules: List[SanitizationRule] = self._build_default_rules()
        if custom_rules:
            self.rules.extend(custom_rules)

    def _build_default_rules(self) -> List[SanitizationRule]:
        """
        Build default sanitization rules for common sensitive patterns.

        Returns:
            List of SanitizationRule objects covering API keys, passwords,
            PII, and other sensitive data.
        """
        return [
            SanitizationRule(
                name="api_key_generic",
                pattern=re.compile(
                    r'(?:api[_-]?key|apikey)\s*[=:]\s*["\']?[\w\-\.]{8,}["\']?',
                    re.IGNORECASE,
                ),
                replacement="[REDACTED_API_KEY]",
            ),
            SanitizationRule(
                name="email",
                pattern=re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+"),
                replacement="[REDACTED_EMAIL]",
            ),
            SanitizationRule(
                name="aws_secret_key",
                pattern=re.compile(r"(?:AKIA|sk-)[A-Za-z0-9/+=]{16,}"),
                replacement="[REDACTED_SECRET_KEY]",
            ),
            SanitizationRule(
                name="password_in_config",
                pattern=re.compile(
                    r'(?:password|passwd|pwd)\s*[=:]\s*["\']?[^\s"\']{3,}["\']?',
                    re.IGNORECASE,
                ),
                replacement="[REDACTED_PASSWORD]",
            ),
            SanitizationRule(
                name="unix_home_path",
                pattern=re.compile(r"/(?:home|Users)/[a-zA-Z0-9_.\-]+"),
                replacement="[REDACTED_PATH]",
            ),
            SanitizationRule(
                name="windows_user_path",
                pattern=re.compile(r"C:\\\\Users\\\\[a-zA-Z0-9_.\-]+"),
                replacement="[REDACTED_PATH]",
            ),
            SanitizationRule(
                name="phone_number",
                pattern=re.compile(
                    r"(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}"
                ),
                replacement="[REDACTED_PHONE]",
            ),
            SanitizationRule(
                name="ipv4_address",
                pattern=re.compile(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b"),
                replacement="[REDACTED_IP]",
            ),
            SanitizationRule(
                name="bearer_token",
                pattern=re.compile(r"[Bb]earer\s+[A-Za-z0-9\-._~+/]+=*"),
                replacement="[REDACTED_BEARER_TOKEN]",
            ),
            SanitizationRule(
                name="generic_secret",
                pattern=re.compile(
                    r'(?:secret|token|credential)\s*[=:]\s*["\']?[\w\-\.]{8,}["\']?',
                    re.IGNORECASE,
                ),
                replacement="[REDACTED_SECRET]",
            ),
            SanitizationRule(
                name="ssn",
                pattern=re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
                replacement="[REDACTED_SSN]",
            ),
        ]

    def sanitize_text(self, text: str) -> str:
        """
        Apply all sanitization rules to text.

        Args:
            text: The text to sanitize.

        Returns:
            Sanitized text with sensitive patterns replaced.
        """
        result = text
        for rule in self.rules:
            result = rule.pattern.sub(rule.replacement, result)
        return result

    def sanitize_lesson(self, lesson: Lesson) -> Lesson:
        """
        Create a new Lesson with sanitized fields.

        Args:
            lesson: The lesson to sanitize.

        Returns:
            A new Lesson with sanitized title, description, and source_context.
        """
        sanitized_context: Dict[str, Any] = {}
        for key, value in lesson.source_context.items():
            if isinstance(value, str):
                sanitized_context[key] = self.sanitize_text(value)
            else:
                sanitized_context[key] = value

        return Lesson(
            lesson_id=lesson.lesson_id,
            title=self.sanitize_text(lesson.title),
            description=self.sanitize_text(lesson.description),
            category=lesson.category,
            severity=lesson.severity,
            tags=lesson.tags,
            source_phase=lesson.source_phase,
            source_context=sanitized_context,
            created_at=lesson.created_at,
            anti_pattern=lesson.anti_pattern,
        )

    def sanitize_lessons(self, lessons: List[Lesson]) -> List[Lesson]:
        """
        Sanitize a list of lessons.

        Args:
            lessons: List of lessons to sanitize.

        Returns:
            List of sanitized lessons.
        """
        sanitized: List[Lesson] = []
        for lesson_entry in lessons:
            sanitized.append(self.sanitize_lesson(lesson_entry))
        return sanitized

    def sanitize_retro_item(self, item: RetroItem) -> RetroItem:
        """
        Create a new RetroItem with sanitized description.

        Args:
            item: The retro item to sanitize.

        Returns:
            A new RetroItem with sanitized description.
        """
        return RetroItem(
            item_id=item.item_id,
            item_type=item.item_type,
            description=self.sanitize_text(item.description),
            tags=item.tags,
            created_at=item.created_at,
        )

    def sanitize_finding(self, finding: AntiPatternFinding) -> AntiPatternFinding:
        """
        Create a new AntiPatternFinding with sanitized fields.

        Args:
            finding: The finding to sanitize.

        Returns:
            A new AntiPatternFinding with sanitized sensitive fields.
        """
        return AntiPatternFinding(
            finding_id=finding.finding_id,
            pattern_type=finding.pattern_type,
            description=self.sanitize_text(finding.description),
            evidence=self.sanitize_text(finding.evidence),
            location=self.sanitize_text(finding.location),
            severity=finding.severity,
            recommendation=self.sanitize_text(finding.recommendation),
        )


# ============================================================================
# Anti-Pattern Detector
# ============================================================================


class AntiPatternDetector:
    """Detects common anti-patterns in code and process logs.

    Runs a battery of heuristic checks against source code artifacts and
    process log entries, producing structured findings that can be converted
    into actionable lessons.
    """

    def __init__(self) -> None:
        """Initialize the anti-pattern detector."""
        self.logger = logging.getLogger(__name__)

    def detect(self, context: RetrospectiveContext) -> List[AntiPatternFinding]:
        """
        Run all detection rules against artifacts and process log.

        Args:
            context: RetrospectiveContext with artifacts and process log.

        Returns:
            List of AntiPatternFinding objects.
        """
        findings: List[AntiPatternFinding] = []

        for artifact_name, artifact_content in context.artifacts.items():
            code_findings = self._detect_in_code(artifact_name, artifact_content)
            findings.extend(code_findings)

        process_findings = self._detect_in_process(context.process_log)
        findings.extend(process_findings)

        return findings

    def _detect_in_code(self, filename: str, content: str) -> List[AntiPatternFinding]:
        """
        Run code-level anti-pattern detections.

        Args:
            filename: Name of the artifact file.
            content: Content of the artifact.

        Returns:
            List of findings from code analysis.
        """
        findings: List[AntiPatternFinding] = []

        detectors = [
            self._detect_god_class,
            self._detect_deep_nesting,
            self._detect_magic_numbers,
            self._detect_hardcoded_secrets,
            self._detect_missing_error_handling,
            self._detect_copy_paste,
            self._detect_missing_documentation,
        ]

        for detector_func in detectors:
            result = detector_func(filename, content)
            if result is not None:
                findings.append(result)

        return findings

    def _detect_god_class(
        self, filename: str, content: str
    ) -> Optional[AntiPatternFinding]:
        """
        Detect classes with excessive methods or lines.

        A god class is flagged when it has >15 methods or >300 lines.

        Args:
            filename: Name of the file.
            content: File content.

        Returns:
            AntiPatternFinding if god class detected, None otherwise.
        """
        method_count = len(re.findall(r"^\s+def\s+", content, re.MULTILINE))
        line_count = content.count("\n")

        if method_count > 15 or line_count > 300:
            severity = Severity.CRITICAL if method_count > 25 else Severity.HIGH
            return AntiPatternFinding(
                finding_id=str(uuid.uuid4()),
                pattern_type=AntiPatternType.GOD_CLASS,
                description=(f"Class in '{filename}' has excessive responsibilities"),
                evidence=(f"Method count: {method_count}, Line count: {line_count}"),
                location=filename,
                severity=severity,
                recommendation=(
                    "Consider breaking this class into smaller, focused classes "
                    "with single responsibilities."
                ),
            )
        return None

    def _detect_deep_nesting(
        self, filename: str, content: str
    ) -> Optional[AntiPatternFinding]:
        """
        Detect excessive indentation depth.

        Flags files with consistent indentation deeper than 4 levels.

        Args:
            filename: Name of the file.
            content: File content.

        Returns:
            AntiPatternFinding if deep nesting detected, None otherwise.
        """
        max_indent = 0
        deep_indent_count = 0

        for text_line in content.split("\n"):
            if not text_line.strip():
                continue
            indent = (len(text_line) - len(text_line.lstrip())) // 4
            max_indent = max(max_indent, indent)
            if indent > 4:
                deep_indent_count += 1

        if max_indent > 4 and deep_indent_count > 3:
            return AntiPatternFinding(
                finding_id=str(uuid.uuid4()),
                pattern_type=AntiPatternType.DEEP_NESTING,
                description=f"File '{filename}' has excessive nesting depth",
                evidence=(
                    f"Max indentation level: {max_indent}, "
                    f"Lines with depth > 4: {deep_indent_count}"
                ),
                location=filename,
                severity=Severity.MEDIUM,
                recommendation=(
                    "Refactor to reduce nesting depth. Extract nested logic "
                    "into helper functions."
                ),
            )
        return None

    def _detect_magic_numbers(
        self, filename: str, content: str
    ) -> Optional[AntiPatternFinding]:
        """
        Detect numeric literals not assigned to named constants.

        Ignores 0, 1, and -1 which are conventional.

        Args:
            filename: Name of the file.
            content: File content.

        Returns:
            AntiPatternFinding if magic numbers detected, None otherwise.
        """
        magic_pattern = re.compile(
            r"(?<![a-zA-Z0-9_])[2-9]\d*(?![a-zA-Z0-9_])|"
            r"(?<![a-zA-Z0-9_])-[2-9]\d*(?![a-zA-Z0-9_])"
        )
        matches = magic_pattern.findall(content)

        if len(matches) > 5:
            return AntiPatternFinding(
                finding_id=str(uuid.uuid4()),
                pattern_type=AntiPatternType.MAGIC_NUMBERS,
                description=f"File '{filename}' contains multiple magic numbers",
                evidence=f"Found {len(matches)} potential magic number literals",
                location=filename,
                severity=Severity.LOW,
                recommendation=(
                    "Replace magic numbers with named constants to improve "
                    "code clarity and maintainability."
                ),
            )
        return None

    def _detect_hardcoded_secrets(
        self, filename: str, content: str
    ) -> Optional[AntiPatternFinding]:
        """
        Detect strings that look like API keys or passwords in source code.

        Args:
            filename: Name of the file.
            content: File content.

        Returns:
            AntiPatternFinding if hardcoded secrets detected, None otherwise.
        """
        secret_patterns = [
            re.compile(
                r'(?:api[_-]?key|apikey)\s*[=:]\s*["\']([a-zA-Z0-9\-_.]{8,})',
                re.IGNORECASE,
            ),
            re.compile(
                r'(?:password|passwd|pwd)\s*[=:]\s*["\']([^\s"\']{3,})',
                re.IGNORECASE,
            ),
            re.compile(r"(?:AKIA|sk-)[A-Za-z0-9/+=]{16,}"),
        ]

        for secret_pat in secret_patterns:
            if secret_pat.search(content):
                return AntiPatternFinding(
                    finding_id=str(uuid.uuid4()),
                    pattern_type=AntiPatternType.HARDCODED_SECRETS,
                    description=(f"File '{filename}' contains hardcoded secrets"),
                    evidence=("Detected patterns matching API keys or passwords"),
                    location=filename,
                    severity=Severity.CRITICAL,
                    recommendation=(
                        "Remove all hardcoded secrets. Use environment "
                        "variables or secure vaults instead."
                    ),
                )
        return None

    def _detect_missing_error_handling(
        self, filename: str, content: str
    ) -> Optional[AntiPatternFinding]:
        """
        Detect bare except clauses.

        Args:
            filename: Name of the file.
            content: File content.

        Returns:
            AntiPatternFinding if bare except clauses found, None otherwise.
        """
        if re.search(r"except\s*:", content):
            return AntiPatternFinding(
                finding_id=str(uuid.uuid4()),
                pattern_type=AntiPatternType.MISSING_ERROR_HANDLING,
                description=(f"File '{filename}' contains bare except clause(s)"),
                evidence=("Detected one or more 'except:' without exception type"),
                location=filename,
                severity=Severity.HIGH,
                recommendation=(
                    "Always catch specific exception types. Bare except "
                    "clauses can mask errors."
                ),
            )
        return None

    def _detect_copy_paste(
        self, filename: str, content: str
    ) -> Optional[AntiPatternFinding]:
        """
        Detect duplicate code blocks using a simple heuristic.

        Looks for repeated non-trivial lines appearing 3+ times.

        Args:
            filename: Name of the file.
            content: File content.

        Returns:
            AntiPatternFinding if copy-paste detected, None otherwise.
        """
        lines = content.split("\n")
        line_counts: Dict[str, int] = {}
        for text_line in lines:
            stripped = text_line.strip()
            if stripped and len(stripped) > 10:
                line_counts[stripped] = line_counts.get(stripped, 0) + 1

        duplicated = [dup_line for dup_line, cnt in line_counts.items() if cnt >= 3]
        if len(duplicated) > 2:
            return AntiPatternFinding(
                finding_id=str(uuid.uuid4()),
                pattern_type=AntiPatternType.COPY_PASTE,
                description=f"File '{filename}' has duplicate code blocks",
                evidence=f"Found {len(duplicated)} duplicated code lines",
                location=filename,
                severity=Severity.MEDIUM,
                recommendation=(
                    "Extract duplicate code into reusable functions or methods "
                    "to reduce duplication."
                ),
            )
        return None

    def _detect_missing_documentation(
        self, filename: str, content: str
    ) -> Optional[AntiPatternFinding]:
        """
        Detect public functions/classes without docstrings.

        Args:
            filename: Name of the file.
            content: File content.

        Returns:
            AntiPatternFinding if missing documentation detected, None otherwise.
        """
        func_count = len(re.findall(r"^\s*def\s+(?!_)[a-zA-Z]", content, re.MULTILINE))
        docstring_count = len(re.findall(r'"""', content))

        if func_count > 3 and docstring_count < func_count // 2:
            return AntiPatternFinding(
                finding_id=str(uuid.uuid4()),
                pattern_type=AntiPatternType.MISSING_DOCUMENTATION,
                description=(
                    f"File '{filename}' has public functions lacking docstrings"
                ),
                evidence=(
                    f"Found {func_count} public functions but only "
                    f"{docstring_count} docstrings"
                ),
                location=filename,
                severity=Severity.LOW,
                recommendation=(
                    "Add docstrings to all public functions and classes "
                    "to improve code documentation."
                ),
            )
        return None

    def _detect_in_process(self, process_log: List[str]) -> List[AntiPatternFinding]:
        """
        Detect process-level anti-patterns from log entries.

        Args:
            process_log: List of process log entries.

        Returns:
            List of process-level findings.
        """
        findings: List[AntiPatternFinding] = []

        scope_creep = self._detect_scope_creep(process_log)
        if scope_creep:
            findings.append(scope_creep)

        return findings

    def _detect_scope_creep(
        self, process_log: List[str]
    ) -> Optional[AntiPatternFinding]:
        """
        Detect scope creep in process log.

        Looks for keywords indicating scope expansion or rework.

        Args:
            process_log: List of process log entries.

        Returns:
            AntiPatternFinding if scope creep detected, None otherwise.
        """
        scope_keywords = [
            "additional scope",
            "changed requirements",
            "reworked",
            "scope expanded",
            "extra features",
            "added functionality",
        ]

        creep_count = 0
        for log_entry in process_log:
            for keyword in scope_keywords:
                if keyword.lower() in log_entry.lower():
                    creep_count += 1

        if creep_count >= 2:
            return AntiPatternFinding(
                finding_id=str(uuid.uuid4()),
                pattern_type=AntiPatternType.SCOPE_CREEP,
                description="Process log indicates scope creep",
                evidence=(
                    f"Detected {creep_count} instances of scope expansion "
                    "in process log"
                ),
                location="process_log",
                severity=Severity.HIGH,
                recommendation=(
                    "Implement stricter scope management. Use change control "
                    "process for scope modifications."
                ),
            )
        return None

    def finding_to_lesson(self, finding: AntiPatternFinding, phase_name: str) -> Lesson:
        """
        Convert an AntiPatternFinding to a Lesson.

        Args:
            finding: The finding to convert.
            phase_name: Name of the phase.

        Returns:
            A Lesson object derived from the finding.
        """
        severity_to_category = {
            Severity.CRITICAL: LessonCategory.ARCHITECTURE,
            Severity.HIGH: LessonCategory.IMPLEMENTATION,
            Severity.MEDIUM: LessonCategory.PROCESS,
            Severity.LOW: LessonCategory.GENERAL,
        }

        return Lesson(
            lesson_id=str(uuid.uuid4()),
            title=f"Anti-pattern: {finding.pattern_type.value}",
            description=finding.description,
            category=severity_to_category.get(finding.severity, LessonCategory.GENERAL),
            severity=finding.severity,
            tags=["anti-pattern", finding.pattern_type.value],
            source_phase=phase_name,
            source_context={
                "finding_id": finding.finding_id,
                "location": finding.location,
                "evidence": finding.evidence,
                "recommendation": finding.recommendation,
            },
            created_at=datetime.datetime.utcnow().isoformat(),
            anti_pattern=finding.pattern_type.value,
        )


# ============================================================================
# Lesson Capture
# ============================================================================


class LessonCapture:
    """Captures and extracts lessons from retrospective context.

    Analyzes artifacts and process logs to automatically generate
    retrospective items (observations, what went well / poorly) and
    converts them into structured Lesson objects.
    """

    def __init__(self) -> None:
        """Initialize the lesson capture utility."""
        self.logger = logging.getLogger(__name__)

    def capture(self, context: RetrospectiveContext) -> List[RetroItem]:
        """
        Analyze context and generate RetroItems.

        Args:
            context: RetrospectiveContext with artifacts and process log.

        Returns:
            List of RetroItem objects.
        """
        items: List[RetroItem] = []

        artifact_items = self._analyze_artifacts(context.artifacts)
        items.extend(artifact_items)

        process_items = self._analyze_process_log(context.process_log)
        items.extend(process_items)

        went_poorly = [
            item for item in items if item.item_type == RetroItemType.WENT_POORLY
        ]
        if went_poorly:
            action_items = self._generate_action_items(went_poorly)
            items.extend(action_items)

        return items

    def _analyze_artifacts(self, artifacts: Dict[str, str]) -> List[RetroItem]:
        """
        Generate observations from code artifacts.

        Args:
            artifacts: Dictionary of artifact names to content.

        Returns:
            List of RetroItem observations.
        """
        items: List[RetroItem] = []

        for artifact_name, content in artifacts.items():
            line_count = content.count("\n")
            complexity_score = content.count("if ") + content.count("for ")

            if line_count > 500:
                items.append(
                    RetroItem(
                        item_id=str(uuid.uuid4()),
                        item_type=RetroItemType.OBSERVATION,
                        description=(
                            f"Artifact '{artifact_name}' is quite large "
                            f"({line_count} lines)"
                        ),
                        tags=["size", "complexity"],
                        created_at=datetime.datetime.utcnow().isoformat(),
                    )
                )

            if complexity_score > 20:
                items.append(
                    RetroItem(
                        item_id=str(uuid.uuid4()),
                        item_type=RetroItemType.OBSERVATION,
                        description=(
                            f"Artifact '{artifact_name}' shows high complexity "
                            f"(complexity score: {complexity_score})"
                        ),
                        tags=["complexity"],
                        created_at=datetime.datetime.utcnow().isoformat(),
                    )
                )

        return items

    def _analyze_process_log(self, process_log: List[str]) -> List[RetroItem]:
        """
        Generate items from process log analysis.

        Args:
            process_log: List of process log entries.

        Returns:
            List of RetroItem entries inferred from the log.
        """
        items: List[RetroItem] = []

        if not process_log:
            return items

        positive_keywords = [
            "successfully",
            "completed",
            "passed",
            "resolved",
            "improved",
            "optimized",
            "clean",
            "good",
        ]

        for log_entry in process_log:
            for keyword in positive_keywords:
                if keyword.lower() in log_entry.lower():
                    items.append(
                        RetroItem(
                            item_id=str(uuid.uuid4()),
                            item_type=RetroItemType.WENT_WELL,
                            description=log_entry,
                            tags=["process"],
                            created_at=(datetime.datetime.utcnow().isoformat()),
                        )
                    )
                    break

        return items

    def _generate_action_items(
        self, went_poorly_items: List[RetroItem]
    ) -> List[RetroItem]:
        """
        Generate action items from went-poorly items.

        Args:
            went_poorly_items: List of items describing what went poorly.

        Returns:
            List of generated action items.
        """
        action_items: List[RetroItem] = []

        for item in went_poorly_items:
            action_items.append(
                RetroItem(
                    item_id=str(uuid.uuid4()),
                    item_type=RetroItemType.ACTION_ITEM,
                    description=f"Address: {item.description}",
                    tags=["follow-up"],
                    created_at=datetime.datetime.utcnow().isoformat(),
                )
            )

        return action_items

    def extract_lessons_from_items(
        self, items: List[RetroItem], phase_name: str
    ) -> List[Lesson]:
        """
        Convert RetroItems into Lesson objects.

        Only items of type LESSON_LEARNED or OBSERVATION are promoted.

        Args:
            items: List of RetroItem objects.
            phase_name: Name of the phase.

        Returns:
            List of Lesson objects.
        """
        lessons: List[Lesson] = []

        for item in items:
            if item.item_type in (
                RetroItemType.LESSON_LEARNED,
                RetroItemType.OBSERVATION,
            ):
                lesson = Lesson(
                    lesson_id=str(uuid.uuid4()),
                    title=f"Lesson from {phase_name}",
                    description=item.description,
                    category=LessonCategory.GENERAL,
                    severity=Severity.MEDIUM,
                    tags=item.tags,
                    source_phase=phase_name,
                    source_context={"retro_item_id": item.item_id},
                    created_at=item.created_at,
                )
                lessons.append(lesson)

        return lessons


# ============================================================================
# LessonsProvider (Abstract + Concrete)
# ============================================================================


class LessonsProvider(abc.ABC):
    """Abstract base class for lesson storage and retrieval.

    Implementations may back onto any durable store (database, file,
    cloud service).  The in-memory implementation provided here is
    suitable for testing and single-process use.
    """

    @abc.abstractmethod
    def ingest(self, lessons: List[Lesson]) -> int:
        """
        Store lessons in the provider.

        Args:
            lessons: List of Lesson objects to ingest.

        Returns:
            Count of successfully ingested lessons.
        """

    @abc.abstractmethod
    def get_all(self) -> List[Lesson]:
        """
        Retrieve all stored lessons.

        Returns:
            List of all stored lessons.
        """

    @abc.abstractmethod
    def query(
        self,
        category: Optional[LessonCategory] = None,
        severity: Optional[Severity] = None,
        tags: Optional[List[str]] = None,
        phase: Optional[str] = None,
        search_text: Optional[str] = None,
    ) -> List[Lesson]:
        """
        Query lessons by filters.

        Args:
            category: Filter by lesson category.
            severity: Filter by severity level.
            tags: Filter by tags (all must match).
            phase: Filter by source phase.
            search_text: Full-text search in title and description.

        Returns:
            List of matching lessons.
        """

    @abc.abstractmethod
    def get_by_id(self, lesson_id: str) -> Optional[Lesson]:
        """
        Get a specific lesson by ID.

        Args:
            lesson_id: The ID of the lesson.

        Returns:
            The lesson if found, None otherwise.
        """

    @abc.abstractmethod
    def count(self) -> int:
        """
        Return total number of stored lessons.

        Returns:
            Total count of lessons.
        """

    @abc.abstractmethod
    def clear(self) -> None:
        """Remove all stored lessons."""


class InMemoryLessonsProvider(LessonsProvider):
    """In-memory implementation of LessonsProvider.

    Lessons are stored in a dictionary keyed by ``lesson_id``.
    Ingesting a lesson whose ID already exists will overwrite the
    previous entry.
    """

    def __init__(self) -> None:
        """Initialize the in-memory provider."""
        self._lessons: Dict[str, Lesson] = {}

    def ingest(self, lessons: List[Lesson]) -> int:
        """
        Store lessons in memory.

        Lessons with duplicate IDs overwrite existing ones.

        Args:
            lessons: List of Lesson objects to ingest.

        Returns:
            Count of ingested lessons.
        """
        for lesson_entry in lessons:
            self._lessons[lesson_entry.lesson_id] = lesson_entry
        return len(lessons)

    def get_all(self) -> List[Lesson]:
        """
        Retrieve all stored lessons.

        Returns:
            List of all lessons.
        """
        return list(self._lessons.values())

    def query(
        self,
        category: Optional[LessonCategory] = None,
        severity: Optional[Severity] = None,
        tags: Optional[List[str]] = None,
        phase: Optional[str] = None,
        search_text: Optional[str] = None,
    ) -> List[Lesson]:
        """
        Query lessons by filters.

        All supplied filters are combined with AND logic.

        Args:
            category: Filter by lesson category.
            severity: Filter by severity level.
            tags: Filter by tags (all must match).
            phase: Filter by source phase.
            search_text: Full-text search in title and description.

        Returns:
            List of matching lessons.
        """
        results: List[Lesson] = []

        for lesson_entry in self._lessons.values():
            if category and lesson_entry.category != category:
                continue
            if severity and lesson_entry.severity != severity:
                continue
            if tags:
                if not all(tag in lesson_entry.tags for tag in tags):
                    continue
            if phase and lesson_entry.source_phase != phase:
                continue
            if search_text:
                search_lower = search_text.lower()
                title_match = search_lower in lesson_entry.title.lower()
                desc_match = search_lower in lesson_entry.description.lower()
                if not (title_match or desc_match):
                    continue

            results.append(lesson_entry)

        return results

    def get_by_id(self, lesson_id: str) -> Optional[Lesson]:
        """
        Get a specific lesson by ID.

        Args:
            lesson_id: The ID of the lesson.

        Returns:
            The lesson if found, None otherwise.
        """
        return self._lessons.get(lesson_id)

    def count(self) -> int:
        """
        Return total number of stored lessons.

        Returns:
            Total count of lessons.
        """
        return len(self._lessons)

    def clear(self) -> None:
        """Remove all stored lessons."""
        self._lessons.clear()


# ============================================================================
# Retrospective Phase Orchestrator
# ============================================================================


class RetrospectivePhase:
    """Orchestrates the complete retrospective phase.

    Flow:
        1. Capture retro items from context
        2. Extract lessons from retro items
        3. Detect anti-patterns
        4. Convert findings to lessons
        5. Merge all lessons
        6. Sanitize all data
        7. Ingest into LessonsProvider
        8. Generate and return report
    """

    def __init__(
        self,
        lessons_provider: Optional[LessonsProvider] = None,
        sanitizer: Optional[Sanitizer] = None,
        anti_pattern_detector: Optional[AntiPatternDetector] = None,
    ) -> None:
        """
        Initialize the retrospective phase.

        Args:
            lessons_provider: Optional LessonsProvider instance.
                Defaults to InMemoryLessonsProvider.
            sanitizer: Optional Sanitizer instance.
                Defaults to Sanitizer with built-in rules.
            anti_pattern_detector: Optional AntiPatternDetector instance.
        """
        self.lessons_provider: LessonsProvider = (
            lessons_provider or InMemoryLessonsProvider()
        )
        self.sanitizer: Sanitizer = sanitizer or Sanitizer()
        self.detector: AntiPatternDetector = (
            anti_pattern_detector or AntiPatternDetector()
        )
        self.capture: LessonCapture = LessonCapture()
        self.logger: logging.Logger = logging.getLogger(__name__)

    def run(self, context: RetrospectiveContext) -> RetrospectiveReport:
        """
        Execute the full retrospective flow.

        Args:
            context: RetrospectiveContext with phase information and artifacts.

        Returns:
            RetrospectiveReport with all findings, lessons, and summary.
        """
        self.logger.info("Starting retrospective for phase: %s", context.phase_name)

        # Step 1: Capture retro items
        retro_items = self.capture.capture(context)
        self.logger.debug("Captured %d retro items", len(retro_items))

        # Step 2: Extract lessons from items
        items_lessons = self.capture.extract_lessons_from_items(
            retro_items, context.phase_name
        )
        self.logger.debug("Extracted %d lessons from items", len(items_lessons))

        # Step 3: Detect anti-patterns
        findings = self.detector.detect(context)
        self.logger.debug("Detected %d anti-patterns", len(findings))

        # Step 4: Convert findings to lessons
        finding_lessons = [
            self.detector.finding_to_lesson(finding, context.phase_name)
            for finding in findings
        ]
        self.logger.debug("Converted %d findings to lessons", len(finding_lessons))

        # Step 5: Merge all lessons
        all_lessons = items_lessons + finding_lessons
        self.logger.debug("Total lessons before sanitization: %d", len(all_lessons))

        # Step 6: Sanitize all data
        sanitized_retro_items = [
            self.sanitizer.sanitize_retro_item(item) for item in retro_items
        ]
        sanitized_lessons = self.sanitizer.sanitize_lessons(all_lessons)
        sanitized_findings = [
            self.sanitizer.sanitize_finding(finding) for finding in findings
        ]
        self.logger.debug("Data sanitization complete")

        # Step 7: Ingest sanitized lessons
        ingested_count = self.lessons_provider.ingest(sanitized_lessons)
        self.logger.info("Ingested %d lessons into provider", ingested_count)

        # Step 8: Generate report
        summary = self._generate_summary(
            sanitized_retro_items, sanitized_lessons, sanitized_findings
        )
        report = RetrospectiveReport(
            report_id=str(uuid.uuid4()),
            phase_name=context.phase_name,
            retro_items=sanitized_retro_items,
            lessons=sanitized_lessons,
            anti_pattern_findings=sanitized_findings,
            summary=summary,
            created_at=datetime.datetime.utcnow().isoformat(),
            sanitized=True,
        )

        self.logger.info("Retrospective complete for phase: %s", context.phase_name)
        return report

    def _generate_summary(
        self,
        retro_items: List[RetroItem],
        lessons: List[Lesson],
        findings: List[AntiPatternFinding],
    ) -> str:
        """
        Generate a human-readable summary of the retrospective.

        Args:
            retro_items: List of retrospective items.
            lessons: List of lessons.
            findings: List of anti-pattern findings.

        Returns:
            Multi-line summary text.
        """
        went_well_count = sum(
            1 for item in retro_items if item.item_type == RetroItemType.WENT_WELL
        )
        went_poorly_count = sum(
            1 for item in retro_items if item.item_type == RetroItemType.WENT_POORLY
        )

        critical_findings = sum(
            1 for finding in findings if finding.severity == Severity.CRITICAL
        )
        high_findings = sum(
            1 for finding in findings if finding.severity == Severity.HIGH
        )

        summary_parts = [
            "Retrospective Summary:",
            f"  Went Well: {went_well_count}",
            f"  Went Poorly: {went_poorly_count}",
            f"  Lessons Captured: {len(lessons)}",
            f"  Critical Findings: {critical_findings}",
            f"  High Severity Findings: {high_findings}",
        ]

        if critical_findings > 0:
            summary_parts.append(
                "  \u26a0\ufe0f  Critical issues found - immediate action required"
            )
        if went_poorly_count > went_well_count:
            summary_parts.append(
                "  \u26a0\ufe0f  More issues than successes - consider process review"
            )
        if len(lessons) == 0:
            summary_parts.append(
                "  \u2139\ufe0f  No lessons captured - consider more detailed analysis"
            )

        return "\n".join(summary_parts)

    def get_lessons_provider(self) -> LessonsProvider:
        """
        Get the LessonsProvider for external querying.

        Returns:
            The configured LessonsProvider instance.
        """
        return self.lessons_provider


# ============================================================================
# Module-Level Factory Functions
# ============================================================================


def create_retrospective_phase(
    lessons_provider: Optional[LessonsProvider] = None,
    custom_sanitization_rules: Optional[List[SanitizationRule]] = None,
) -> RetrospectivePhase:
    """
    Factory function to create a configured RetrospectivePhase.

    Args:
        lessons_provider: Optional custom LessonsProvider.
        custom_sanitization_rules: Optional list of custom sanitization rules.

    Returns:
        A configured RetrospectivePhase instance.
    """
    sanitizer = (
        Sanitizer(custom_rules=custom_sanitization_rules)
        if custom_sanitization_rules
        else Sanitizer()
    )

    return RetrospectivePhase(
        lessons_provider=lessons_provider,
        sanitizer=sanitizer,
        anti_pattern_detector=AntiPatternDetector(),
    )


def run_retrospective(context: RetrospectiveContext) -> RetrospectiveReport:
    """
    Convenience function: create a phase and run it in one call.

    Args:
        context: RetrospectiveContext with phase information.

    Returns:
        RetrospectiveReport from the retrospective phase.
    """
    phase = create_retrospective_phase()
    return phase.run(context)
