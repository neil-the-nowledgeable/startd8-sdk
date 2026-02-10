"""
Comprehensive unit tests for Artisan design documentation workflow.

This module tests:
1. Design document generation from task descriptions
2. Reviewer critique of design documents
3. Arbiter resolution of conflicting critiques
4. Escalation paths when resolution fails
5. End-to-end workflows

All tests are self-contained with mocked LLM calls (no real API usage).
Target: >85% code coverage of design documentation functionality.
"""

import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock

import pytest


# ═══════════════════════════════════════════════════════════════════════════
# ─── Enums ───
# ═══════════════════════════════════════════════════════════════════════════


class CritiqueSeverity(str, Enum):
    """Severity levels for design critiques."""

    CRITICAL = "critical"
    MAJOR = "major"
    MINOR = "minor"
    SUGGESTION = "suggestion"


class EscalationReason(str, Enum):
    """Reasons for escalating unresolved design issues."""

    UNRESOLVABLE_CONFLICT = "unresolvable_conflict"
    SCOPE_EXCEEDED = "scope_exceeded"
    REPEATED_FAILURE = "repeated_failure"
    TIMEOUT = "timeout"


class ResolutionStatus(str, Enum):
    """Status of a resolved critique."""

    ACCEPTED = "accepted"
    REJECTED = "rejected"
    MODIFIED = "modified"
    ESCALATED = "escalated"


# ═══════════════════════════════════════════════════════════════════════════
# ─── Data Classes ───
# ═══════════════════════════════════════════════════════════════════════════


@dataclass
class CritiqueItem:
    """A single piece of design feedback from a reviewer."""

    section: str
    severity: CritiqueSeverity
    description: str
    suggestion: str
    reviewer_id: str = ""


@dataclass
class Resolution:
    """Resolution of a critique by the arbiter."""

    critique: CritiqueItem
    status: ResolutionStatus
    justification: str


@dataclass
class EscalationRecord:
    """Record of an escalated design review."""

    reason: EscalationReason
    context: Dict[str, Any] = field(default_factory=dict)
    attempts: int = 0
    timestamp: float = 0.0


@dataclass
class DesignDocument:
    """A design document with all required sections."""

    title: str
    overview: str
    approach: str
    data_models: str
    api_contracts: str
    edge_cases: str
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def sections(self) -> List[str]:
        """Return list of section names."""
        return ["overview", "approach", "data_models", "api_contracts", "edge_cases"]

    def to_dict(self) -> Dict[str, Any]:
        """Convert design document to dictionary."""
        return {
            "title": self.title,
            "overview": self.overview,
            "approach": self.approach,
            "data_models": self.data_models,
            "api_contracts": self.api_contracts,
            "edge_cases": self.edge_cases,
            "metadata": self.metadata,
        }


# ═══════════════════════════════════════════════════════════════════════════
# ─── Service Classes ───
# ═══════════════════════════════════════════════════════════════════════════


class DesignDocGenerator:
    """Generates design documents from task descriptions.

    Uses an LLM client to produce structured design documents from
    natural-language task descriptions. Validates inputs and parses
    JSON responses into DesignDocument instances.
    """

    def __init__(self, llm_client: Any = None) -> None:
        """Initialize generator with optional LLM client.

        Args:
            llm_client: Client with a ``generate(prompt)`` method.
                        A ``MagicMock`` is used when *None*.
        """
        self.llm_client = llm_client or MagicMock()

    def generate(
        self,
        task_description: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> DesignDocument:
        """Generate a design document from a task description.

        Args:
            task_description: Description of the task to design for.
            context: Optional additional context (prior docs, constraints, etc.).

        Returns:
            Generated design document.

        Raises:
            ValueError: If *task_description* is empty, blank, or ``None``.
            RuntimeError: If the LLM returns an empty or malformed response.
        """
        if not task_description or not task_description.strip():
            raise ValueError("Task description cannot be empty")

        prompt = self._build_prompt(task_description, context)
        response = self.llm_client.generate(prompt)

        if not response or not response.strip():
            raise RuntimeError("LLM returned empty response")

        return self._parse_response(response)

    def _build_prompt(
        self,
        task_description: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Build the prompt for the LLM.

        Args:
            task_description: Task to design for.
            context: Optional context dict.

        Returns:
            Formatted prompt string.
        """
        base = f"Generate a design document for: {task_description}"
        if context:
            base += f"\nContext: {json.dumps(context)}"
        return base

    def _parse_response(self, response: str) -> DesignDocument:
        """Parse LLM response into a *DesignDocument*.

        Args:
            response: JSON string from LLM.

        Returns:
            Parsed design document.

        Raises:
            RuntimeError: If JSON is malformed.
        """
        try:
            data = json.loads(response)
        except json.JSONDecodeError as exc:
            raise RuntimeError("LLM returned malformed JSON") from exc

        return DesignDocument(
            title=data.get("title", ""),
            overview=data.get("overview", ""),
            approach=data.get("approach", ""),
            data_models=data.get("data_models", ""),
            api_contracts=data.get("api_contracts", ""),
            edge_cases=data.get("edge_cases", ""),
            metadata=data.get("metadata", {}),
        )


class DesignReviewer:
    """Reviews design documents and produces structured critiques.

    Each reviewer instance carries a unique *reviewer_id* so that
    downstream consumers can attribute feedback to specific agents.
    """

    def __init__(
        self,
        llm_client: Any = None,
        reviewer_id: str = "reviewer-1",
    ) -> None:
        """Initialize reviewer with optional LLM client.

        Args:
            llm_client: Client with a ``generate(prompt)`` method.
            reviewer_id: Identifier for this reviewer.
        """
        self.llm_client = llm_client or MagicMock()
        self.reviewer_id = reviewer_id

    def critique(self, design_doc: DesignDocument) -> List[CritiqueItem]:
        """Generate a critique of a design document.

        If the document is missing both *overview* and *approach* it is
        treated as essentially empty and a ``CRITICAL`` critique is
        returned immediately without an LLM call.

        Args:
            design_doc: Design document to critique.

        Returns:
            List of critique items.

        Raises:
            RuntimeError: If the LLM returns an empty or malformed response.
        """
        if not design_doc.overview and not design_doc.approach:
            return [
                CritiqueItem(
                    section="overview",
                    severity=CritiqueSeverity.CRITICAL,
                    description="Design document is empty or missing critical sections",
                    suggestion="Provide a complete design document with all required sections",
                    reviewer_id=self.reviewer_id,
                )
            ]

        prompt = f"Review this design document: {json.dumps(design_doc.to_dict())}"
        response = self.llm_client.generate(prompt)

        if not response or not response.strip():
            raise RuntimeError("LLM returned empty response during review")

        return self._parse_critiques(response)

    def _parse_critiques(self, response: str) -> List[CritiqueItem]:
        """Parse LLM response into a list of *CritiqueItem* objects.

        Handles both list and single-object JSON payloads gracefully.

        Args:
            response: JSON string from LLM.

        Returns:
            Parsed critiques.

        Raises:
            RuntimeError: If JSON is malformed.
        """
        try:
            items = json.loads(response)
        except json.JSONDecodeError as exc:
            raise RuntimeError("LLM returned malformed critique JSON") from exc

        if not isinstance(items, list):
            items = [items]

        return [
            CritiqueItem(
                section=item.get("section", "general"),
                severity=CritiqueSeverity(item.get("severity", "minor")),
                description=item.get("description", ""),
                suggestion=item.get("suggestion", ""),
                reviewer_id=self.reviewer_id,
            )
            for item in items
        ]


class ArbiterResolver:
    """Resolves conflicting critiques from multiple reviewers.

    The arbiter attempts LLM-based resolution up to *MAX_ATTEMPTS* times.
    If all attempts fail the issue is escalated and further calls to
    :meth:`resolve` raise ``RuntimeError``.

    Unanimous critiques (identical descriptions) are auto-accepted
    without consulting the LLM.
    """

    MAX_ATTEMPTS: int = 3

    def __init__(
        self,
        llm_client: Any = None,
        notification_service: Any = None,
    ) -> None:
        """Initialize arbiter with optional LLM and notification clients.

        Args:
            llm_client: Client with a ``generate(prompt)`` method.
            notification_service: Optional service with a ``notify(record)`` method.
        """
        self.llm_client = llm_client or MagicMock()
        self.notification_service = notification_service
        self._escalated: bool = False
        self._attempts: int = 0

    def resolve(
        self,
        critiques: List[CritiqueItem],
        design_doc: DesignDocument,
    ) -> List[Resolution]:
        """Resolve conflicting critiques.

        Args:
            critiques: Critiques to resolve.
            design_doc: The design document being reviewed.

        Returns:
            Resolved critiques with status and justification.

        Raises:
            RuntimeError: If called after escalation or on LLM errors
                          before *MAX_ATTEMPTS* is reached.
        """
        if self._escalated:
            raise RuntimeError("Cannot resolve after escalation")

        if not critiques:
            return []

        self._attempts += 1

        # Unanimous agreement — auto-accept without LLM call.
        descriptions = [c.description for c in critiques]
        if len(set(descriptions)) == 1:
            return [
                Resolution(
                    critique=critiques[0],
                    status=ResolutionStatus.ACCEPTED,
                    justification="All reviewers agree on this critique",
                )
            ]

        prompt = self._build_resolution_prompt(critiques, design_doc)

        try:
            response = self.llm_client.generate(prompt)
        except Exception:
            if self._attempts >= self.MAX_ATTEMPTS:
                return self._escalate(
                    EscalationReason.REPEATED_FAILURE, critiques, design_doc
                )
            raise

        if not response or not response.strip():
            if self._attempts >= self.MAX_ATTEMPTS:
                return self._escalate(
                    EscalationReason.REPEATED_FAILURE, critiques, design_doc
                )
            raise RuntimeError("LLM returned empty resolution")

        resolutions = self._parse_resolutions(response, critiques)

        # Detect unresolvable conflicts surfaced by the LLM itself.
        if any(r.status == ResolutionStatus.ESCALATED for r in resolutions):
            return self._escalate(
                EscalationReason.UNRESOLVABLE_CONFLICT, critiques, design_doc
            )

        return resolutions

    def _build_resolution_prompt(
        self,
        critiques: List[CritiqueItem],
        design_doc: DesignDocument,
    ) -> str:
        """Build prompt for arbiter to resolve conflicts.

        Args:
            critiques: Critiques to resolve.
            design_doc: Design being reviewed.

        Returns:
            Formatted resolution prompt.
        """
        critique_data = [
            {
                "section": c.section,
                "severity": c.severity.value,
                "description": c.description,
            }
            for c in critiques
        ]
        return (
            f"Resolve conflicts in critiques: {json.dumps(critique_data)}\n"
            f"Design title: {design_doc.title}"
        )

    def _parse_resolutions(
        self,
        response: str,
        critiques: List[CritiqueItem],
    ) -> List[Resolution]:
        """Parse LLM response into a list of *Resolution* objects.

        Args:
            response: JSON string from LLM.
            critiques: Original critiques for back-reference.

        Returns:
            Parsed resolutions.

        Raises:
            RuntimeError: If JSON is malformed.
        """
        try:
            items = json.loads(response)
        except json.JSONDecodeError as exc:
            raise RuntimeError("LLM returned malformed resolution JSON") from exc

        if not isinstance(items, list):
            items = [items]

        resolutions: List[Resolution] = []
        for idx, item in enumerate(items):
            critique = critiques[idx] if idx < len(critiques) else critiques[-1]
            resolutions.append(
                Resolution(
                    critique=critique,
                    status=ResolutionStatus(item.get("status", "accepted")),
                    justification=item.get("justification", ""),
                )
            )
        return resolutions

    def _escalate(
        self,
        reason: EscalationReason,
        critiques: List[CritiqueItem],
        design_doc: DesignDocument,
    ) -> List[Resolution]:
        """Escalate unresolvable review to higher authority.

        Sets the internal escalation flag, builds an :class:`EscalationRecord`,
        and optionally notifies via the *notification_service*.

        Args:
            reason: Reason for escalation.
            critiques: Original critiques.
            design_doc: Design being reviewed.

        Returns:
            Single-element list with an ``ESCALATED`` resolution.
        """
        self._escalated = True
        record = EscalationRecord(
            reason=reason,
            context={
                "critiques": [c.description for c in critiques],
                "design_title": design_doc.title,
            },
            attempts=self._attempts,
            timestamp=time.time(),
        )

        if self.notification_service:
            try:
                self.notification_service.notify(record)
            except Exception:
                # Notification failure is secondary; escalation still occurs.
                pass

        return [
            Resolution(
                critique=(
                    critiques[0]
                    if critiques
                    else CritiqueItem(
                        section="general",
                        severity=CritiqueSeverity.CRITICAL,
                        description="Escalated",
                        suggestion="",
                    )
                ),
                status=ResolutionStatus.ESCALATED,
                justification=f"Escalated due to: {reason.value}",
            )
        ]

    @property
    def is_escalated(self) -> bool:
        """Return whether this arbiter has entered the escalated state."""
        return self._escalated


# ═══════════════════════════════════════════════════════════════════════════
# ─── Pytest Fixtures ───
# ═══════════════════════════════════════════════════════════════════════════


@pytest.fixture
def mock_llm_client() -> MagicMock:
    """Provide a mocked LLM client."""
    return MagicMock()


@pytest.fixture
def mock_notification_service() -> MagicMock:
    """Provide a mocked notification service."""
    return MagicMock()


@pytest.fixture
def sample_task_description() -> str:
    """Provide a sample task description."""
    return (
        "Build a REST API for user authentication with JWT tokens, "
        "supporting login, logout, and token refresh."
    )


@pytest.fixture
def sample_llm_design_response() -> str:
    """Provide a sample LLM response for design generation."""
    return json.dumps(
        {
            "title": "User Auth API Design",
            "overview": "REST API for JWT-based authentication",
            "approach": "Use FastAPI with pyjwt for token management",
            "data_models": "User model with email, hashed_password, created_at",
            "api_contracts": "POST /login, POST /logout, POST /refresh",
            "edge_cases": "Expired tokens, concurrent sessions, brute force",
            "metadata": {
                "author": "architect",
                "version": "1.0",
                "timestamp": "2024-01-01T00:00:00Z",
            },
        }
    )


@pytest.fixture
def sample_design_document() -> DesignDocument:
    """Provide a sample design document."""
    return DesignDocument(
        title="User Auth API Design",
        overview="REST API for JWT-based authentication",
        approach="Use FastAPI with pyjwt for token management",
        data_models="User model with email, hashed_password, created_at",
        api_contracts="POST /login, POST /logout, POST /refresh",
        edge_cases="Expired tokens, concurrent sessions, brute force",
        metadata={"author": "architect", "version": "1.0"},
    )


@pytest.fixture
def sample_critique_response() -> str:
    """Provide a sample LLM response for critique generation."""
    return json.dumps(
        [
            {
                "section": "data_models",
                "severity": "major",
                "description": "Missing role-based access control in user model",
                "suggestion": "Add a roles field to the User model",
            },
            {
                "section": "edge_cases",
                "severity": "minor",
                "description": "Should consider rate limiting",
                "suggestion": "Add rate limiting section",
            },
        ]
    )


@pytest.fixture
def sample_critiques() -> List[CritiqueItem]:
    """Provide sample critique items."""
    return [
        CritiqueItem(
            section="data_models",
            severity=CritiqueSeverity.MAJOR,
            description="Missing role-based access control",
            suggestion="Add roles field",
            reviewer_id="reviewer-1",
        ),
        CritiqueItem(
            section="edge_cases",
            severity=CritiqueSeverity.MINOR,
            description="Should consider rate limiting",
            suggestion="Add rate limiting section",
            reviewer_id="reviewer-1",
        ),
    ]


@pytest.fixture
def conflicting_critiques() -> List[CritiqueItem]:
    """Provide critiques that conflict with each other."""
    return [
        CritiqueItem(
            section="approach",
            severity=CritiqueSeverity.CRITICAL,
            description="Should use OAuth2 instead of custom JWT",
            suggestion="Switch to OAuth2 provider",
            reviewer_id="reviewer-1",
        ),
        CritiqueItem(
            section="approach",
            severity=CritiqueSeverity.MINOR,
            description="Custom JWT is fine but add refresh token rotation",
            suggestion="Implement refresh token rotation",
            reviewer_id="reviewer-2",
        ),
    ]


@pytest.fixture
def sample_resolution_response() -> str:
    """Provide a sample LLM response for resolution."""
    return json.dumps(
        [
            {"status": "accepted", "justification": "RBAC is essential for auth systems"},
            {
                "status": "modified",
                "justification": "Rate limiting should be in API contracts, not edge cases",
            },
        ]
    )


# ═══════════════════════════════════════════════════════════════════════════
# ─── Test Classes: Design Document Generation ───
# ═══════════════════════════════════════════════════════════════════════════


class TestDesignDocumentGeneration:
    """Tests for design document generation."""

    def test_generate_design_doc_from_task_description(
        self, mock_llm_client, sample_task_description, sample_llm_design_response
    ):
        """Test basic design doc generation from task string."""
        mock_llm_client.generate.return_value = sample_llm_design_response
        generator = DesignDocGenerator(llm_client=mock_llm_client)

        doc = generator.generate(sample_task_description)

        assert isinstance(doc, DesignDocument)
        assert doc.title == "User Auth API Design"
        mock_llm_client.generate.assert_called_once()

    def test_generate_design_doc_contains_required_sections(
        self, mock_llm_client, sample_task_description, sample_llm_design_response
    ):
        """Verify all required sections are present in generated doc."""
        mock_llm_client.generate.return_value = sample_llm_design_response
        generator = DesignDocGenerator(llm_client=mock_llm_client)

        doc = generator.generate(sample_task_description)

        required_sections = [
            "overview",
            "approach",
            "data_models",
            "api_contracts",
            "edge_cases",
        ]
        for section in required_sections:
            assert section in doc.sections
            assert getattr(doc, section, None) is not None
            assert len(getattr(doc, section)) > 0

    def test_generate_design_doc_with_context(
        self, mock_llm_client, sample_task_description, sample_llm_design_response
    ):
        """Test generation with additional context."""
        mock_llm_client.generate.return_value = sample_llm_design_response
        generator = DesignDocGenerator(llm_client=mock_llm_client)
        context = {"existing_services": ["user-service", "notification-service"]}

        doc = generator.generate(sample_task_description, context=context)

        assert isinstance(doc, DesignDocument)
        call_args = mock_llm_client.generate.call_args[0][0]
        assert "existing_services" in call_args

    def test_generate_design_doc_with_empty_input(self, mock_llm_client):
        """Edge case: empty string should raise ValueError."""
        generator = DesignDocGenerator(llm_client=mock_llm_client)

        with pytest.raises(ValueError, match="empty"):
            generator.generate("")

        with pytest.raises(ValueError, match="empty"):
            generator.generate("   ")

    def test_generate_design_doc_with_none_input(self, mock_llm_client):
        """Edge case: None input should raise error."""
        generator = DesignDocGenerator(llm_client=mock_llm_client)

        with pytest.raises((ValueError, TypeError)):
            generator.generate(None)

    def test_generate_design_doc_llm_returns_empty(
        self, mock_llm_client, sample_task_description
    ):
        """Edge case: LLM returns empty string."""
        mock_llm_client.generate.return_value = ""
        generator = DesignDocGenerator(llm_client=mock_llm_client)

        with pytest.raises(RuntimeError, match="empty"):
            generator.generate(sample_task_description)

    def test_generate_design_doc_llm_returns_malformed_json(
        self, mock_llm_client, sample_task_description
    ):
        """Edge case: LLM returns invalid JSON."""
        mock_llm_client.generate.return_value = "not valid json {{"
        generator = DesignDocGenerator(llm_client=mock_llm_client)

        with pytest.raises(RuntimeError, match="malformed"):
            generator.generate(sample_task_description)

    def test_generate_design_doc_llm_raises_exception(
        self, mock_llm_client, sample_task_description
    ):
        """Edge case: LLM raises connection error."""
        mock_llm_client.generate.side_effect = ConnectionError("API unreachable")
        generator = DesignDocGenerator(llm_client=mock_llm_client)

        with pytest.raises(ConnectionError):
            generator.generate(sample_task_description)

    def test_generate_design_doc_includes_metadata(
        self, mock_llm_client, sample_task_description, sample_llm_design_response
    ):
        """Verify metadata is included in generated document."""
        mock_llm_client.generate.return_value = sample_llm_design_response
        generator = DesignDocGenerator(llm_client=mock_llm_client)

        doc = generator.generate(sample_task_description)

        assert doc.metadata is not None
        assert isinstance(doc.metadata, dict)
        assert "author" in doc.metadata

    def test_generate_design_doc_output_format(
        self, mock_llm_client, sample_task_description, sample_llm_design_response
    ):
        """Verify output is properly structured."""
        mock_llm_client.generate.return_value = sample_llm_design_response
        generator = DesignDocGenerator(llm_client=mock_llm_client)

        doc = generator.generate(sample_task_description)
        doc_dict = doc.to_dict()

        assert isinstance(doc_dict, dict)
        assert "title" in doc_dict
        assert "overview" in doc_dict

    def test_generate_design_doc_with_complex_requirements(
        self, mock_llm_client, sample_llm_design_response
    ):
        """Test with complex multi-requirement task."""
        mock_llm_client.generate.return_value = sample_llm_design_response
        generator = DesignDocGenerator(llm_client=mock_llm_client)

        complex_task = (
            "Build a microservice that handles real-time event processing, "
            "supports WebSocket connections, integrates with Kafka for event streaming, "
            "provides REST endpoints for configuration, and includes comprehensive monitoring."
        )

        doc = generator.generate(complex_task)
        assert isinstance(doc, DesignDocument)
        assert doc.title

    def test_generate_design_doc_llm_returns_none(
        self, mock_llm_client, sample_task_description
    ):
        """Edge case: LLM returns None instead of a string."""
        mock_llm_client.generate.return_value = None
        generator = DesignDocGenerator(llm_client=mock_llm_client)

        with pytest.raises(RuntimeError, match="empty"):
            generator.generate(sample_task_description)

    def test_generate_design_doc_missing_optional_fields(
        self, mock_llm_client, sample_task_description
    ):
        """LLM response omitting optional keys still produces a valid document."""
        mock_llm_client.generate.return_value = json.dumps({"title": "Minimal"})
        generator = DesignDocGenerator(llm_client=mock_llm_client)

        doc = generator.generate(sample_task_description)

        assert doc.title == "Minimal"
        assert doc.overview == ""
        assert doc.metadata == {}


# ═══════════════════════════════════════════════════════════════════════════
# ─── Test Classes: Reviewer Critique ───
# ═══════════════════════════════════════════════════════════════════════════


class TestReviewerCritique:
    """Tests for design review and critique generation."""

    def test_reviewer_produces_critique(
        self, mock_llm_client, sample_design_document, sample_critique_response
    ):
        """Test basic critique generation."""
        mock_llm_client.generate.return_value = sample_critique_response
        reviewer = DesignReviewer(llm_client=mock_llm_client)

        critiques = reviewer.critique(sample_design_document)

        assert isinstance(critiques, list)
        assert len(critiques) > 0
        assert all(isinstance(c, CritiqueItem) for c in critiques)

    def test_critique_has_severity_levels(
        self, mock_llm_client, sample_design_document, sample_critique_response
    ):
        """Verify each critique has a severity level."""
        mock_llm_client.generate.return_value = sample_critique_response
        reviewer = DesignReviewer(llm_client=mock_llm_client)

        critiques = reviewer.critique(sample_design_document)

        for critique in critiques:
            assert isinstance(critique.severity, CritiqueSeverity)
            assert critique.severity in list(CritiqueSeverity)

    def test_critique_references_sections(
        self, mock_llm_client, sample_design_document, sample_critique_response
    ):
        """Verify each critique references a document section."""
        mock_llm_client.generate.return_value = sample_critique_response
        reviewer = DesignReviewer(llm_client=mock_llm_client)

        critiques = reviewer.critique(sample_design_document)

        for critique in critiques:
            assert critique.section is not None
            assert len(critique.section) > 0

    def test_critique_contains_suggestions(
        self, mock_llm_client, sample_design_document, sample_critique_response
    ):
        """Verify each critique contains actionable suggestions."""
        mock_llm_client.generate.return_value = sample_critique_response
        reviewer = DesignReviewer(llm_client=mock_llm_client)

        critiques = reviewer.critique(sample_design_document)

        for critique in critiques:
            assert critique.suggestion is not None
            assert len(critique.suggestion) > 0

    def test_multiple_reviewers_produce_different_critiques(
        self, sample_design_document
    ):
        """Test that different reviewers produce different feedback."""
        response_1 = json.dumps(
            [
                {
                    "section": "approach",
                    "severity": "major",
                    "description": "Use GraphQL",
                    "suggestion": "Switch to GraphQL",
                }
            ]
        )
        response_2 = json.dumps(
            [
                {
                    "section": "data_models",
                    "severity": "minor",
                    "description": "Add indexes",
                    "suggestion": "Add DB indexes",
                }
            ]
        )

        mock_llm_1 = MagicMock()
        mock_llm_1.generate.return_value = response_1
        mock_llm_2 = MagicMock()
        mock_llm_2.generate.return_value = response_2

        reviewer_1 = DesignReviewer(llm_client=mock_llm_1, reviewer_id="reviewer-1")
        reviewer_2 = DesignReviewer(llm_client=mock_llm_2, reviewer_id="reviewer-2")

        critiques_1 = reviewer_1.critique(sample_design_document)
        critiques_2 = reviewer_2.critique(sample_design_document)

        assert critiques_1[0].description != critiques_2[0].description
        assert critiques_1[0].reviewer_id != critiques_2[0].reviewer_id

    def test_reviewer_with_empty_doc(self, mock_llm_client):
        """Edge case: reviewing an empty design document."""
        empty_doc = DesignDocument(
            title="",
            overview="",
            approach="",
            data_models="",
            api_contracts="",
            edge_cases="",
        )
        reviewer = DesignReviewer(llm_client=mock_llm_client)

        critiques = reviewer.critique(empty_doc)

        assert len(critiques) > 0
        assert critiques[0].severity == CritiqueSeverity.CRITICAL

    def test_reviewer_with_perfect_doc(
        self, mock_llm_client, sample_design_document
    ):
        """Test review of a perfect document (no critiques)."""
        mock_llm_client.generate.return_value = json.dumps([])
        reviewer = DesignReviewer(llm_client=mock_llm_client)

        critiques = reviewer.critique(sample_design_document)

        assert isinstance(critiques, list)
        assert len(critiques) == 0

    def test_reviewer_llm_failure(self, mock_llm_client, sample_design_document):
        """Edge case: LLM returns empty string during review."""
        mock_llm_client.generate.return_value = ""
        reviewer = DesignReviewer(llm_client=mock_llm_client)

        with pytest.raises(RuntimeError, match="empty"):
            reviewer.critique(sample_design_document)

    def test_reviewer_llm_malformed_response(
        self, mock_llm_client, sample_design_document
    ):
        """Edge case: LLM returns invalid JSON."""
        mock_llm_client.generate.return_value = "not json"
        reviewer = DesignReviewer(llm_client=mock_llm_client)

        with pytest.raises(RuntimeError, match="malformed"):
            reviewer.critique(sample_design_document)

    def test_critique_serialization(
        self, mock_llm_client, sample_design_document, sample_critique_response
    ):
        """Verify critiques can be serialized to JSON."""
        mock_llm_client.generate.return_value = sample_critique_response
        reviewer = DesignReviewer(llm_client=mock_llm_client)

        critiques = reviewer.critique(sample_design_document)

        for critique in critiques:
            serialized = {
                "section": critique.section,
                "severity": critique.severity.value,
                "description": critique.description,
                "suggestion": critique.suggestion,
                "reviewer_id": critique.reviewer_id,
            }
            json_str = json.dumps(serialized)
            deserialized = json.loads(json_str)
            assert deserialized["section"] == critique.section
            assert deserialized["severity"] == critique.severity.value

    def test_reviewer_single_critique_as_dict(
        self, mock_llm_client, sample_design_document
    ):
        """Edge case: LLM returns single object instead of list."""
        mock_llm_client.generate.return_value = json.dumps(
            {
                "section": "approach",
                "severity": "minor",
                "description": "Consider caching",
                "suggestion": "Add Redis",
            }
        )
        reviewer = DesignReviewer(llm_client=mock_llm_client)

        critiques = reviewer.critique(sample_design_document)

        assert len(critiques) == 1
        assert critiques[0].section == "approach"

    def test_reviewer_default_section_and_severity(
        self, mock_llm_client, sample_design_document
    ):
        """Critiques missing 'section' or 'severity' get sensible defaults."""
        mock_llm_client.generate.return_value = json.dumps(
            [{"description": "Vague concern", "suggestion": "Clarify"}]
        )
        reviewer = DesignReviewer(llm_client=mock_llm_client)

        critiques = reviewer.critique(sample_design_document)

        assert critiques[0].section == "general"
        assert critiques[0].severity == CritiqueSeverity.MINOR


# ═══════════════════════════════════════════════════════════════════════════
# ─── Test Classes: Arbiter Resolution ───
# ═══════════════════════════════════════════════════════════════════════════


class TestArbiterResolution:
    """Tests for arbiter conflict resolution."""

    def test_arbiter_resolves_conflicting_critiques(
        self,
        mock_llm_client,
        conflicting_critiques,
        sample_design_document,
        mock_notification_service,
    ):
        """Test resolution of conflicting critiques."""
        mock_llm_client.generate.return_value = json.dumps(
            [
                {
                    "status": "rejected",
                    "justification": "Custom JWT is acceptable for this scope",
                },
                {
                    "status": "accepted",
                    "justification": "Refresh token rotation is a good practice",
                },
            ]
        )
        arbiter = ArbiterResolver(
            llm_client=mock_llm_client, notification_service=mock_notification_service
        )

        resolutions = arbiter.resolve(conflicting_critiques, sample_design_document)

        assert len(resolutions) == 2
        statuses = {r.status for r in resolutions}
        assert ResolutionStatus.REJECTED in statuses
        assert ResolutionStatus.ACCEPTED in statuses

    def test_arbiter_accepts_unanimous_critiques(
        self, mock_llm_client, sample_design_document, mock_notification_service
    ):
        """Test that unanimous critiques are auto-accepted."""
        identical_critiques = [
            CritiqueItem(
                section="data_models",
                severity=CritiqueSeverity.MAJOR,
                description="Missing indexes",
                suggestion="Add indexes",
                reviewer_id="r1",
            ),
            CritiqueItem(
                section="data_models",
                severity=CritiqueSeverity.MAJOR,
                description="Missing indexes",
                suggestion="Add indexes",
                reviewer_id="r2",
            ),
        ]
        arbiter = ArbiterResolver(
            llm_client=mock_llm_client, notification_service=mock_notification_service
        )

        resolutions = arbiter.resolve(identical_critiques, sample_design_document)

        assert len(resolutions) == 1
        assert resolutions[0].status == ResolutionStatus.ACCEPTED
        # LLM should NOT have been called for unanimous critiques.
        mock_llm_client.generate.assert_not_called()

    def test_arbiter_rejects_invalid_critiques(
        self, mock_llm_client, sample_design_document, mock_notification_service
    ):
        """Test rejection of clearly invalid critiques."""
        critiques = [
            CritiqueItem(
                section="approach",
                severity=CritiqueSeverity.MINOR,
                description="Use COBOL",
                suggestion="Rewrite in COBOL",
                reviewer_id="r1",
            ),
            CritiqueItem(
                section="approach",
                severity=CritiqueSeverity.MINOR,
                description="Python is fine",
                suggestion="Keep Python",
                reviewer_id="r2",
            ),
        ]
        mock_llm_client.generate.return_value = json.dumps(
            [
                {"status": "rejected", "justification": "COBOL is not appropriate"},
                {"status": "accepted", "justification": "Python is the correct choice"},
            ]
        )
        arbiter = ArbiterResolver(
            llm_client=mock_llm_client, notification_service=mock_notification_service
        )

        resolutions = arbiter.resolve(critiques, sample_design_document)

        rejected = [r for r in resolutions if r.status == ResolutionStatus.REJECTED]
        assert len(rejected) >= 1

    def test_arbiter_modifies_partial_critiques(
        self,
        mock_llm_client,
        sample_critiques,
        sample_design_document,
        sample_resolution_response,
        mock_notification_service,
    ):
        """Test modification of partially valid critiques."""
        mock_llm_client.generate.return_value = sample_resolution_response
        arbiter = ArbiterResolver(
            llm_client=mock_llm_client, notification_service=mock_notification_service
        )

        resolutions = arbiter.resolve(sample_critiques, sample_design_document)

        modified = [r for r in resolutions if r.status == ResolutionStatus.MODIFIED]
        assert len(modified) >= 1

    def test_arbiter_resolution_contains_justification(
        self,
        mock_llm_client,
        sample_critiques,
        sample_design_document,
        sample_resolution_response,
        mock_notification_service,
    ):
        """Verify each resolution includes justification."""
        mock_llm_client.generate.return_value = sample_resolution_response
        arbiter = ArbiterResolver(
            llm_client=mock_llm_client, notification_service=mock_notification_service
        )

        resolutions = arbiter.resolve(sample_critiques, sample_design_document)

        for resolution in resolutions:
            assert resolution.justification is not None
            assert len(resolution.justification) > 0

    def test_arbiter_with_single_critique(
        self, mock_llm_client, sample_design_document, mock_notification_service
    ):
        """Test resolution with only one critique (no conflict possible)."""
        single = [
            CritiqueItem(
                section="overview",
                severity=CritiqueSeverity.MINOR,
                description="Add diagram",
                suggestion="Include architecture diagram",
                reviewer_id="r1",
            )
        ]
        mock_llm_client.generate.return_value = json.dumps(
            [
                {"status": "accepted", "justification": "Diagrams improve clarity"},
            ]
        )
        arbiter = ArbiterResolver(
            llm_client=mock_llm_client, notification_service=mock_notification_service
        )

        resolutions = arbiter.resolve(single, sample_design_document)

        assert len(resolutions) == 1

    def test_arbiter_with_no_critiques(
        self, mock_llm_client, sample_design_document, mock_notification_service
    ):
        """Edge case: no critiques to resolve."""
        arbiter = ArbiterResolver(
            llm_client=mock_llm_client, notification_service=mock_notification_service
        )

        resolutions = arbiter.resolve([], sample_design_document)

        assert resolutions == []
        mock_llm_client.generate.assert_not_called()

    def test_arbiter_llm_failure(
        self,
        mock_llm_client,
        sample_critiques,
        sample_design_document,
        mock_notification_service,
    ):
        """Edge case: LLM fails during resolution."""
        mock_llm_client.generate.side_effect = ConnectionError("API down")
        arbiter = ArbiterResolver(
            llm_client=mock_llm_client, notification_service=mock_notification_service
        )

        with pytest.raises(ConnectionError):
            arbiter.resolve(sample_critiques, sample_design_document)

    def test_arbiter_resolution_status_values(self):
        """Verify all resolution status values are correct."""
        assert ResolutionStatus.ACCEPTED.value == "accepted"
        assert ResolutionStatus.REJECTED.value == "rejected"
        assert ResolutionStatus.MODIFIED.value == "modified"
        assert ResolutionStatus.ESCALATED.value == "escalated"

    def test_arbiter_preserves_critique_metadata(
        self,
        mock_llm_client,
        sample_critiques,
        sample_design_document,
        sample_resolution_response,
        mock_notification_service,
    ):
        """Verify original critique data is preserved in resolutions."""
        mock_llm_client.generate.return_value = sample_resolution_response
        arbiter = ArbiterResolver(
            llm_client=mock_llm_client, notification_service=mock_notification_service
        )

        resolutions = arbiter.resolve(sample_critiques, sample_design_document)

        for resolution in resolutions:
            assert resolution.critique is not None
            assert isinstance(resolution.critique, CritiqueItem)
            assert resolution.critique.section in ["data_models", "edge_cases"]

    def test_arbiter_malformed_response(
        self,
        mock_llm_client,
        sample_critiques,
        sample_design_document,
        mock_notification_service,
    ):
        """Edge case: arbiter LLM returns malformed JSON."""
        mock_llm_client.generate.return_value = "not json at all"
        arbiter = ArbiterResolver(
            llm_client=mock_llm_client, notification_service=mock_notification_service
        )

        with pytest.raises(RuntimeError, match="malformed"):
            arbiter.resolve(sample_critiques, sample_design_document)

    def test_arbiter_fewer_resolutions_than_critiques(
        self,
        mock_llm_client,
        sample_critiques,
        sample_design_document,
        mock_notification_service,
    ):
        """LLM returns fewer resolution items than critiques submitted."""
        mock_llm_client.generate.return_value = json.dumps(
            [{"status": "accepted", "justification": "Only one resolved"}]
        )
        arbiter = ArbiterResolver(
            llm_client=mock_llm_client, notification_service=mock_notification_service
        )

        resolutions = arbiter.resolve(sample_critiques, sample_design_document)

        # Should still produce at least 1 resolution without error.
        assert len(resolutions) == 1

    def test_arbiter_more_resolutions_than_critiques(
        self,
        mock_llm_client,
        sample_design_document,
        mock_notification_service,
    ):
        """LLM returns more resolution items than critiques — uses last critique."""
        single_critique = [
            CritiqueItem(
                section="overview",
                severity=CritiqueSeverity.MINOR,
                description="Unique desc",
                suggestion="Fix",
                reviewer_id="r1",
            ),
        ]
        mock_llm_client.generate.return_value = json.dumps(
            [
                {"status": "accepted", "justification": "First"},
                {"status": "rejected", "justification": "Second (extra)"},
            ]
        )
        arbiter = ArbiterResolver(
            llm_client=mock_llm_client, notification_service=mock_notification_service
        )

        resolutions = arbiter.resolve(single_critique, sample_design_document)

        assert len(resolutions) == 2
        # The extra resolution should reference the last (only) critique.
        assert resolutions[1].critique.section == "overview"


# ═══════════════════════════════════════════════════════════════════════════
# ─── Test Classes: Escalation ───
# ═══════════════════════════════════════════════════════════════════════════


class TestEscalation:
    """Tests for escalation when resolution fails."""

    def test_escalation_on_unresolvable_conflict(
        self,
        mock_llm_client,
        conflicting_critiques,
        sample_design_document,
        mock_notification_service,
    ):
        """Test escalation due to unresolvable conflict."""
        mock_llm_client.generate.return_value = json.dumps(
            [
                {
                    "status": "escalated",
                    "justification": "Fundamental disagreement on architecture",
                },
            ]
        )
        arbiter = ArbiterResolver(
            llm_client=mock_llm_client, notification_service=mock_notification_service
        )

        resolutions = arbiter.resolve(conflicting_critiques, sample_design_document)

        assert any(r.status == ResolutionStatus.ESCALATED for r in resolutions)
        assert arbiter.is_escalated

    def test_escalation_on_repeated_failure(
        self,
        mock_llm_client,
        sample_critiques,
        sample_design_document,
        mock_notification_service,
    ):
        """Test escalation after max retry attempts."""
        mock_llm_client.generate.side_effect = ConnectionError("API failure")
        arbiter = ArbiterResolver(
            llm_client=mock_llm_client, notification_service=mock_notification_service
        )

        # Exhaust retry attempts.
        for _idx in range(ArbiterResolver.MAX_ATTEMPTS - 1):
            with pytest.raises(ConnectionError):
                arbiter.resolve(sample_critiques, sample_design_document)

        # On the final attempt, should escalate instead of raising.
        resolutions = arbiter.resolve(sample_critiques, sample_design_document)

        assert any(r.status == ResolutionStatus.ESCALATED for r in resolutions)
        assert arbiter.is_escalated

    def test_escalation_on_empty_response_repeated(
        self,
        mock_llm_client,
        sample_critiques,
        sample_design_document,
        mock_notification_service,
    ):
        """Test escalation when LLM returns empty response repeatedly."""
        mock_llm_client.generate.return_value = ""
        arbiter = ArbiterResolver(
            llm_client=mock_llm_client, notification_service=mock_notification_service
        )

        for _idx in range(ArbiterResolver.MAX_ATTEMPTS - 1):
            with pytest.raises(RuntimeError):
                arbiter.resolve(sample_critiques, sample_design_document)

        resolutions = arbiter.resolve(sample_critiques, sample_design_document)
        assert any(r.status == ResolutionStatus.ESCALATED for r in resolutions)

    def test_escalation_contains_reason(
        self,
        mock_llm_client,
        conflicting_critiques,
        sample_design_document,
        mock_notification_service,
    ):
        """Verify escalation includes reason information."""
        mock_llm_client.generate.return_value = json.dumps(
            [
                {"status": "escalated", "justification": "Cannot resolve"},
            ]
        )
        arbiter = ArbiterResolver(
            llm_client=mock_llm_client, notification_service=mock_notification_service
        )

        resolutions = arbiter.resolve(conflicting_critiques, sample_design_document)

        escalated = [r for r in resolutions if r.status == ResolutionStatus.ESCALATED]
        assert len(escalated) > 0
        assert "unresolvable_conflict" in escalated[0].justification

    def test_escalation_triggers_notification(
        self,
        mock_llm_client,
        conflicting_critiques,
        sample_design_document,
        mock_notification_service,
    ):
        """Verify notification service is called on escalation."""
        mock_llm_client.generate.return_value = json.dumps(
            [
                {"status": "escalated", "justification": "Cannot resolve"},
            ]
        )
        arbiter = ArbiterResolver(
            llm_client=mock_llm_client, notification_service=mock_notification_service
        )

        arbiter.resolve(conflicting_critiques, sample_design_document)

        mock_notification_service.notify.assert_called_once()
        call_args = mock_notification_service.notify.call_args[0][0]
        assert isinstance(call_args, EscalationRecord)
        assert call_args.reason == EscalationReason.UNRESOLVABLE_CONFLICT

    def test_escalation_notification_failure_still_escalates(
        self,
        mock_llm_client,
        conflicting_critiques,
        sample_design_document,
        mock_notification_service,
    ):
        """Test that notification failure doesn't prevent escalation."""
        mock_llm_client.generate.return_value = json.dumps(
            [
                {"status": "escalated", "justification": "Cannot resolve"},
            ]
        )
        mock_notification_service.notify.side_effect = ConnectionError(
            "Notification service down"
        )
        arbiter = ArbiterResolver(
            llm_client=mock_llm_client, notification_service=mock_notification_service
        )

        resolutions = arbiter.resolve(conflicting_critiques, sample_design_document)

        assert any(r.status == ResolutionStatus.ESCALATED for r in resolutions)
        assert arbiter.is_escalated

    def test_escalation_halts_further_processing(
        self,
        mock_llm_client,
        conflicting_critiques,
        sample_design_document,
        mock_notification_service,
    ):
        """Verify that escalation prevents further resolution attempts."""
        mock_llm_client.generate.return_value = json.dumps(
            [
                {"status": "escalated", "justification": "Cannot resolve"},
            ]
        )
        arbiter = ArbiterResolver(
            llm_client=mock_llm_client, notification_service=mock_notification_service
        )

        arbiter.resolve(conflicting_critiques, sample_design_document)
        assert arbiter.is_escalated

        with pytest.raises(RuntimeError, match="Cannot resolve after escalation"):
            arbiter.resolve(conflicting_critiques, sample_design_document)

    def test_no_escalation_on_successful_resolution(
        self,
        mock_llm_client,
        sample_critiques,
        sample_design_document,
        sample_resolution_response,
        mock_notification_service,
    ):
        """Verify happy path doesn't escalate."""
        mock_llm_client.generate.return_value = sample_resolution_response
        arbiter = ArbiterResolver(
            llm_client=mock_llm_client, notification_service=mock_notification_service
        )

        resolutions = arbiter.resolve(sample_critiques, sample_design_document)

        assert not arbiter.is_escalated
        assert not any(r.status == ResolutionStatus.ESCALATED for r in resolutions)
        mock_notification_service.notify.assert_not_called()

    def test_escalation_without_notification_service(
        self, mock_llm_client, conflicting_critiques, sample_design_document
    ):
        """Test escalation works without notification service."""
        mock_llm_client.generate.return_value = json.dumps(
            [
                {"status": "escalated", "justification": "Cannot resolve"},
            ]
        )
        arbiter = ArbiterResolver(llm_client=mock_llm_client, notification_service=None)

        resolutions = arbiter.resolve(conflicting_critiques, sample_design_document)

        assert any(r.status == ResolutionStatus.ESCALATED for r in resolutions)
        assert arbiter.is_escalated

    def test_escalation_record_contains_context(
        self,
        mock_llm_client,
        conflicting_critiques,
        sample_design_document,
        mock_notification_service,
    ):
        """Verify escalation record includes full context."""
        mock_llm_client.generate.return_value = json.dumps(
            [
                {"status": "escalated", "justification": "Cannot resolve"},
            ]
        )
        arbiter = ArbiterResolver(
            llm_client=mock_llm_client, notification_service=mock_notification_service
        )

        arbiter.resolve(conflicting_critiques, sample_design_document)

        record = mock_notification_service.notify.call_args[0][0]
        assert "critiques" in record.context
        assert "design_title" in record.context
        assert record.attempts >= 1
        assert record.timestamp > 0


# ═══════════════════════════════════════════════════════════════════════════
# ─── Test Classes: End-to-End Workflows ───
# ═══════════════════════════════════════════════════════════════════════════


class TestEndToEndWorkflow:
    """Integration tests of the full design documentation workflow."""

    def test_full_workflow_happy_path(self, mock_notification_service):
        """Test complete workflow: generate → review → resolve → done."""
        llm = MagicMock()

        design_response = json.dumps(
            {
                "title": "Auth API",
                "overview": "JWT auth",
                "approach": "FastAPI + JWT",
                "data_models": "User model",
                "api_contracts": "POST /login",
                "edge_cases": "Token expiry",
                "metadata": {"version": "1.0"},
            }
        )
        critique_response = json.dumps(
            [
                {
                    "section": "data_models",
                    "severity": "minor",
                    "description": "Add timestamps",
                    "suggestion": "Add created_at",
                },
            ]
        )
        resolution_response = json.dumps(
            [
                {
                    "status": "accepted",
                    "justification": "Timestamps are best practice",
                },
            ]
        )

        llm.generate.side_effect = [
            design_response,
            critique_response,
            resolution_response,
        ]

        # Execute workflow.
        generator = DesignDocGenerator(llm_client=llm)
        doc = generator.generate("Build auth API")
        assert isinstance(doc, DesignDocument)

        reviewer = DesignReviewer(llm_client=llm)
        critiques = reviewer.critique(doc)
        assert len(critiques) == 1

        arbiter = ArbiterResolver(
            llm_client=llm, notification_service=mock_notification_service
        )
        resolutions = arbiter.resolve(critiques, doc)
        assert len(resolutions) == 1
        assert resolutions[0].status == ResolutionStatus.ACCEPTED
        assert not arbiter.is_escalated
        mock_notification_service.notify.assert_not_called()

    def test_full_workflow_with_escalation(self, mock_notification_service):
        """Test workflow with escalation: generate → review → fail → escalate."""
        llm = MagicMock()

        design_response = json.dumps(
            {
                "title": "Auth API",
                "overview": "JWT auth",
                "approach": "FastAPI + JWT",
                "data_models": "User model",
                "api_contracts": "POST /login",
                "edge_cases": "Token expiry",
                "metadata": {},
            }
        )
        critique_response = json.dumps(
            [
                {
                    "section": "approach",
                    "severity": "critical",
                    "description": "Use OAuth2",
                    "suggestion": "Switch",
                },
                {
                    "section": "approach",
                    "severity": "critical",
                    "description": "Keep JWT",
                    "suggestion": "Stay",
                },
            ]
        )
        resolution_response = json.dumps(
            [
                {"status": "escalated", "justification": "Fundamental disagreement"},
            ]
        )

        llm.generate.side_effect = [
            design_response,
            critique_response,
            resolution_response,
        ]

        generator = DesignDocGenerator(llm_client=llm)
        doc = generator.generate("Build auth API")

        reviewer = DesignReviewer(llm_client=llm)
        critiques = reviewer.critique(doc)

        arbiter = ArbiterResolver(
            llm_client=llm, notification_service=mock_notification_service
        )
        resolutions = arbiter.resolve(critiques, doc)

        assert any(r.status == ResolutionStatus.ESCALATED for r in resolutions)
        assert arbiter.is_escalated
        mock_notification_service.notify.assert_called_once()

    def test_full_workflow_retry_then_success(self, mock_notification_service):
        """Test workflow with retry: generate → review → fail → retry → success."""
        llm = MagicMock()

        design_response = json.dumps(
            {
                "title": "Auth API",
                "overview": "JWT auth",
                "approach": "FastAPI + JWT",
                "data_models": "User model",
                "api_contracts": "POST /login",
                "edge_cases": "Token expiry",
                "metadata": {},
            }
        )
        critique_response = json.dumps(
            [
                {
                    "section": "data_models",
                    "severity": "major",
                    "description": "Add roles",
                    "suggestion": "Add RBAC",
                },
            ]
        )
        resolution_response = json.dumps(
            [
                {"status": "accepted", "justification": "RBAC is important"},
            ]
        )

        # First call generates, second reviews, third fails, fourth succeeds.
        llm.generate.side_effect = [
            design_response,
            critique_response,
            ConnectionError("Transient failure"),
            resolution_response,
        ]

        generator = DesignDocGenerator(llm_client=llm)
        doc = generator.generate("Build auth API")

        reviewer = DesignReviewer(llm_client=llm)
        critiques = reviewer.critique(doc)

        arbiter = ArbiterResolver(
            llm_client=llm, notification_service=mock_notification_service
        )

        # First attempt fails.
        with pytest.raises(ConnectionError):
            arbiter.resolve(critiques, doc)

        # Second attempt succeeds.
        resolutions = arbiter.resolve(critiques, doc)
        assert len(resolutions) == 1
        assert resolutions[0].status == ResolutionStatus.ACCEPTED
        assert not arbiter.is_escalated

    def test_full_workflow_multiple_reviewers(self, mock_notification_service):
        """End-to-end with two reviewers producing conflicting critiques."""
        gen_llm = MagicMock()
        gen_llm.generate.return_value = json.dumps(
            {
                "title": "Payments API",
                "overview": "Handle payments",
                "approach": "Stripe integration",
                "data_models": "Payment model",
                "api_contracts": "POST /charge",
                "edge_cases": "Double charge",
                "metadata": {},
            }
        )
        generator = DesignDocGenerator(llm_client=gen_llm)
        doc = generator.generate("Build payments API")

        rev_llm_1 = MagicMock()
        rev_llm_1.generate.return_value = json.dumps(
            [{"section": "approach", "severity": "major",
              "description": "Use PayPal", "suggestion": "Switch"}]
        )
        rev_llm_2 = MagicMock()
        rev_llm_2.generate.return_value = json.dumps(
            [{"section": "approach", "severity": "minor",
              "description": "Stripe is fine", "suggestion": "Keep"}]
        )

        r1 = DesignReviewer(llm_client=rev_llm_1, reviewer_id="r1")
        r2 = DesignReviewer(llm_client=rev_llm_2, reviewer_id="r2")

        all_critiques = r1.critique(doc) + r2.critique(doc)
        assert len(all_critiques) == 2

        arb_llm = MagicMock()
        arb_llm.generate.return_value = json.dumps([
            {"status": "rejected", "justification": "PayPal not needed"},
            {"status": "accepted", "justification": "Stripe works"},
        ])
        arbiter = ArbiterResolver(
            llm_client=arb_llm, notification_service=mock_notification_service
        )
        resolutions = arbiter.resolve(all_critiques, doc)

        assert len(resolutions) == 2
        assert not arbiter.is_escalated


# ═══════════════════════════════════════════════════════════════════════════
# ─── Test Classes: Data Models ───
# ═══════════════════════════════════════════════════════════════════════════


class TestDataModels:
    """Tests of data model classes and their behavior."""

    def test_design_document_to_dict(self, sample_design_document):
        """Verify DesignDocument can be converted to dict."""
        doc_dict = sample_design_document.to_dict()
        assert doc_dict["title"] == "User Auth API Design"
        assert doc_dict["overview"] == "REST API for JWT-based authentication"
        assert "metadata" in doc_dict

    def test_design_document_sections_property(self, sample_design_document):
        """Verify sections property includes all required sections."""
        sections = sample_design_document.sections
        assert "overview" in sections
        assert "approach" in sections
        assert "data_models" in sections
        assert "api_contracts" in sections
        assert "edge_cases" in sections

    def test_design_document_default_metadata(self):
        """DesignDocument created without metadata gets empty dict."""
        doc = DesignDocument(
            title="T", overview="O", approach="A",
            data_models="D", api_contracts="C", edge_cases="E",
        )
        assert doc.metadata == {}

    def test_critique_severity_enum_values(self):
        """Verify CritiqueSeverity enum values are correct."""
        assert CritiqueSeverity.CRITICAL.value == "critical"
        assert CritiqueSeverity.MAJOR.value == "major"
        assert CritiqueSeverity.MINOR.value == "minor"
        assert CritiqueSeverity.SUGGESTION.value == "suggestion"

    def test_escalation_reason_enum_values(self):
        """Verify EscalationReason enum values are correct."""
        assert EscalationReason.UNRESOLVABLE_CONFLICT.value == "unresolvable_conflict"
        assert EscalationReason.SCOPE_EXCEEDED.value == "scope_exceeded"
        assert EscalationReason.REPEATED_FAILURE.value == "repeated_failure"
        assert EscalationReason.TIMEOUT.value == "timeout"

    def test_resolution_status_enum_values(self):
        """Verify ResolutionStatus enum values are correct."""
        assert ResolutionStatus.ACCEPTED.value == "accepted"
        assert ResolutionStatus.REJECTED.value == "rejected"
        assert ResolutionStatus.MODIFIED.value == "modified"
        assert ResolutionStatus.ESCALATED.value == "escalated"

    def test_critique_item_creation(self):
        """Verify CritiqueItem can be created with all fields."""
        item = CritiqueItem(
            section="overview",
            severity=CritiqueSeverity.MAJOR,
            description="Missing diagram",
            suggestion="Add architecture diagram",
            reviewer_id="test-reviewer",
        )
        assert item.section == "overview"
        assert item.severity == CritiqueSeverity.MAJOR
        assert item.reviewer_id == "test-reviewer"

    def test_critique_item_default_reviewer_id(self):
        """CritiqueItem without explicit reviewer_id defaults to empty string."""
        item = CritiqueItem(
            section="overview",
            severity=CritiqueSeverity.MINOR,
            description="test",
            suggestion="test",
        )
        assert item.reviewer_id == ""

    def test_resolution_creation(self):
        """Verify Resolution can be created with critique reference."""
        critique = CritiqueItem(
            section="approach",
            severity=CritiqueSeverity.MINOR,
            description="test",
            suggestion="test",
        )
        resolution = Resolution(
            critique=critique,
            status=ResolutionStatus.ACCEPTED,
            justification="Looks good",
        )
        assert resolution.status == ResolutionStatus.ACCEPTED
        assert resolution.critique.section == "approach"

    def test_escalation_record_creation(self):
        """Verify EscalationRecord can be created with context."""
        record = EscalationRecord(
            reason=EscalationReason.TIMEOUT,
            context={"key": "value"},
            attempts=3,
            timestamp=1234567890.0,
        )
        assert record.reason == EscalationReason.TIMEOUT
        assert record.attempts == 3
        assert record.context["key"] == "value"

    def test_escalation_record_defaults(self):
        """Verify EscalationRecord has sensible defaults."""
        record = EscalationRecord(reason=EscalationReason.SCOPE_EXCEEDED)
        assert record.context == {}
        assert record.attempts == 0
        assert record.timestamp == 0.0


# ═══════════════════════════════════════════════════════════════════════════
# ─── Test Classes: Internal Prompts and Parsing ───
# ═══════════════════════════════════════════════════════════════════════════


class TestPromptBuilding:
    """Tests for internal prompt building methods."""

    def test_generator_build_prompt_without_context(self, mock_llm_client):
        """Verify prompt building works without context."""
        generator = DesignDocGenerator(llm_client=mock_llm_client)
        prompt = generator._build_prompt("Build an API")
        assert "Build an API" in prompt

    def test_generator_build_prompt_with_context(self, mock_llm_client):
        """Verify prompt building includes context."""
        generator = DesignDocGenerator(llm_client=mock_llm_client)
        prompt = generator._build_prompt(
            "Build an API", context={"env": "production"}
        )
        assert "Build an API" in prompt
        assert "production" in prompt

    def test_generator_build_prompt_with_empty_context(self, mock_llm_client):
        """Empty context dict is falsy — should not appear in prompt."""
        generator = DesignDocGenerator(llm_client=mock_llm_client)
        prompt = generator._build_prompt("Build an API", context={})
        assert "Context" not in prompt

    def test_arbiter_build_resolution_prompt(
        self, mock_llm_client, sample_critiques, sample_design_document
    ):
        """Verify arbiter builds resolution prompt correctly."""
        arbiter = ArbiterResolver(llm_client=mock_llm_client)
        prompt = arbiter._build_resolution_prompt(
            sample_critiques, sample_design_document
        )
        assert "data_models" in prompt
        assert "major" in prompt

    def test_generator_parse_response_valid(self, mock_llm_client):
        """_parse_response produces correct DesignDocument from valid JSON."""
        generator = DesignDocGenerator(llm_client=mock_llm_client)
        doc = generator._parse_response(json.dumps({
            "title": "T", "overview": "O", "approach": "A",
            "data_models": "D", "api_contracts": "C", "edge_cases": "E",
        }))
        assert doc.title == "T"
        assert doc.overview == "O"

    def test_generator_parse_response_invalid(self, mock_llm_client):
        """_parse_response raises RuntimeError on invalid JSON."""
        generator = DesignDocGenerator(llm_client=mock_llm_client)
        with pytest.raises(RuntimeError, match="malformed"):
            generator._parse_response("{bad json")


# ═══════════════════════════════════════════════════════════════════════════
# ─── Parametrized Tests ───
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize(
    "severity_value,expected_enum",
    [
        ("critical", CritiqueSeverity.CRITICAL),
        ("major", CritiqueSeverity.MAJOR),
        ("minor", CritiqueSeverity.MINOR),
        ("suggestion", CritiqueSeverity.SUGGESTION),
    ],
)
def test_critique_severity_from_string(severity_value, expected_enum):
    """Verify all severity strings can be parsed to enums."""
    assert CritiqueSeverity(severity_value) == expected_enum


@pytest.mark.parametrize(
    "status_value,expected_enum",
    [
        ("accepted", ResolutionStatus.ACCEPTED),
        ("rejected", ResolutionStatus.REJECTED),
        ("modified", ResolutionStatus.MODIFIED),
        ("escalated", ResolutionStatus.ESCALATED),
    ],
)
def test_resolution_status_from_string(status_value, expected_enum):
    """Verify all status strings can be parsed to enums."""
    assert ResolutionStatus(status_value) == expected_enum


@pytest.mark.parametrize("invalid_input", ["", "   ", "\n", "\t"])
def test_generator_rejects_whitespace_inputs(mock_llm_client, invalid_input):
    """Verify generator rejects whitespace-only inputs."""
    generator = DesignDocGenerator(llm_client=mock_llm_client)
    with pytest.raises(ValueError):
        generator.generate(invalid_input)


@pytest.mark.parametrize(
    "section",
    ["overview", "approach", "data_models", "api_contracts", "edge_cases"],
)
def test_critique_references_valid_sections(mock_llm_client, section):
    """Verify critiques can reference all valid sections."""
    critique = CritiqueItem(
        section=section,
        severity=CritiqueSeverity.MINOR,
        description="Test critique",
        suggestion="Test suggestion",
    )
    assert critique.section == section


@pytest.mark.parametrize(
    "severity",
    [
        CritiqueSeverity.CRITICAL,
        CritiqueSeverity.MAJOR,
        CritiqueSeverity.MINOR,
        CritiqueSeverity.SUGGESTION,
    ],
)
def test_all_severity_levels_in_critiques(severity):
    """Verify all severity levels can appear in critiques."""
    critique = CritiqueItem(
        section="approach",
        severity=severity,
        description="Test",
        suggestion="Test suggestion",
    )
    assert critique.severity == severity


@pytest.mark.parametrize(
    "status",
    [
        ResolutionStatus.ACCEPTED,
        ResolutionStatus.REJECTED,
        ResolutionStatus.MODIFIED,
        ResolutionStatus.ESCALATED,
    ],
)
def test_all_resolution_statuses_valid(status):
    """Verify all resolution statuses can appear in resolutions."""
    critique = CritiqueItem(
        section="approach",
        severity=CritiqueSeverity.MINOR,
        description="Test",
        suggestion="Test",
    )
    resolution = Resolution(
        critique=critique, status=status, justification="Test justification"
    )
    assert resolution.status == status


@pytest.mark.parametrize(
    "reason",
    [
        EscalationReason.UNRESOLVABLE_CONFLICT,
        EscalationReason.SCOPE_EXCEEDED,
        EscalationReason.REPEATED_FAILURE,
        EscalationReason.TIMEOUT,
    ],
)
def test_all_escalation_reasons_valid(reason):
    """Verify all escalation reasons can be used in records."""
    record = EscalationRecord(reason=reason)
    assert record.reason == reason