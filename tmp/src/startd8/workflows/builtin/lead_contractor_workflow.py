"""
Lead Contractor Workflow with Spec Completeness Check

A workflow orchestration module that implements a pipeline pattern for creating
and validating specifications before generating drafts. The workflow enforces
spec completeness as a quality gate between spec creation and draft generation.

Pipeline Steps:
    1. _create_spec()              — Build the specification dictionary
    2. _check_spec_completeness()  — Validate all required fields (quality gate)
    3. _create_draft()             — Generate a draft from the validated spec

If the spec is incomplete at step 2, a ``SpecIncompleteError`` is raised and
the pipeline halts before draft generation.
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Module-level constant: fields every spec must include with non-empty values
# ---------------------------------------------------------------------------
REQUIRED_SPEC_FIELDS: List[str] = [
    "title",
    "description",
    "requirements",
    "acceptance_criteria",
]


# ---------------------------------------------------------------------------
# Utility function (defined before classes that reference it)
# ---------------------------------------------------------------------------
def validate_spec_completeness(spec: Dict[str, Any]) -> Dict[str, Any]:
    """Validate that a spec dictionary contains all required fields with non-empty values.

    Args:
        spec: The specification dictionary to validate.  ``None`` is treated as
              an empty dictionary.

    Returns:
        A dictionary with the following keys:

        * ``"is_complete"`` (*bool*) – ``True`` when every required field is
          present **and** non-empty.
        * ``"missing_fields"`` (*List[str]*) – Fields absent from *spec*.
        * ``"empty_fields"`` (*List[str]*) – Fields present but with falsy
          values (``None``, ``""``, ``[]``, etc.).
    """
    spec = spec or {}

    missing_fields: List[str] = [
        field_name for field_name in REQUIRED_SPEC_FIELDS if field_name not in spec
    ]

    empty_fields: List[str] = [
        field_name
        for field_name in REQUIRED_SPEC_FIELDS
        if field_name in spec and not spec[field_name]
    ]

    is_complete: bool = len(missing_fields) == 0 and len(empty_fields) == 0

    return {
        "is_complete": is_complete,
        "missing_fields": missing_fields,
        "empty_fields": empty_fields,
    }


# ---------------------------------------------------------------------------
# Custom exception
# ---------------------------------------------------------------------------
class SpecIncompleteError(Exception):
    """Raised when a specification fails the completeness quality gate.

    Attributes:
        missing_fields: Required fields not present in the spec.
        empty_fields: Required fields present but with empty/falsy values.
    """

    def __init__(self, missing_fields: List[str], empty_fields: List[str]) -> None:
        self.missing_fields = missing_fields
        self.empty_fields = empty_fields
        message = (
            f"Spec is incomplete. Missing fields: {missing_fields}. "
            f"Empty fields: {empty_fields}."
        )
        super().__init__(message)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------
@dataclass
class CompletenessReport:
    """Report produced by the spec completeness validation step.

    Attributes:
        is_complete: Whether the spec satisfies all completeness criteria.
        missing_fields: Required fields not present in the spec.
        empty_fields: Required fields present but with empty/falsy values.
    """

    is_complete: bool
    missing_fields: List[str] = field(default_factory=list)
    empty_fields: List[str] = field(default_factory=list)


@dataclass
class WorkflowResult:
    """Result produced by a successful pipeline execution.

    Attributes:
        spec: The specification dictionary created by ``_create_spec()``.
        completeness_report: Validation report from ``_check_spec_completeness()``.
        draft: The draft dictionary created by ``_create_draft()``.
    """

    spec: Dict[str, Any]
    completeness_report: CompletenessReport
    draft: Dict[str, Any]


# ---------------------------------------------------------------------------
# Main workflow class
# ---------------------------------------------------------------------------
class LeadContractorWorkflow:
    """Orchestrate a pipeline for lead-contractor spec creation and validation.

    The pipeline executes three sequential steps:

    1. **Create specification** (``_create_spec``)
    2. **Validate spec completeness** (``_check_spec_completeness``) — quality gate
    3. **Create draft** (``_create_draft``)

    If the spec is incomplete the pipeline stops at step 2 and raises
    :class:`SpecIncompleteError` before draft creation begins.

    Each step method can be overridden in subclasses for custom behaviour.

    Args:
        config: Optional configuration dictionary used to populate spec fields.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        self.config: Dict[str, Any] = config or {}
        self._spec: Optional[Dict[str, Any]] = None
        self._completeness_report: Optional[CompletenessReport] = None
        self._draft: Optional[Dict[str, Any]] = None
        self.logger: logging.Logger = logging.getLogger(self.__class__.__name__)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def run_pipeline(self) -> WorkflowResult:
        """Execute the full workflow pipeline.

        Returns:
            :class:`WorkflowResult` containing the spec, completeness report,
            and generated draft.

        Raises:
            SpecIncompleteError: If the spec fails the completeness quality
                gate (step 3 is **not** executed).
        """
        self.logger.info("Pipeline execution started")

        # Step 1: Create specification
        self.logger.info("Executing _create_spec step")
        self._create_spec()

        # Step 2: Validate spec completeness (quality gate)
        self.logger.info("Executing _check_spec_completeness step")
        self._check_spec_completeness()
        # SpecIncompleteError is raised above when validation fails;
        # execution will never reach step 3 in that case.

        # Step 3: Create draft from validated spec
        self.logger.info("Executing _create_draft step")
        self._create_draft()

        self.logger.info("Pipeline execution completed successfully")

        return WorkflowResult(
            spec=self._spec,
            completeness_report=self._completeness_report,
            draft=self._draft,
        )

    # ------------------------------------------------------------------
    # Pipeline steps (override in subclasses for custom logic)
    # ------------------------------------------------------------------
    def _create_spec(self) -> Dict[str, Any]:
        """Build a specification dictionary from the workflow configuration.

        The default implementation maps ``self.config`` keys to spec fields,
        falling back to empty strings / lists for any missing keys.

        Returns:
            The newly created specification dictionary.
        """
        spec: Dict[str, Any] = {
            "title": self.config.get("title", ""),
            "description": self.config.get("description", ""),
            "requirements": self.config.get("requirements", []),
            "acceptance_criteria": self.config.get("acceptance_criteria", []),
        }
        self._spec = spec
        return spec

    def _check_spec_completeness(self) -> CompletenessReport:
        """Validate the current spec against required-field rules.

        Acts as the **quality gate** between spec creation and draft generation.

        Returns:
            :class:`CompletenessReport` with validation results.

        Raises:
            SpecIncompleteError: When any required fields are missing or empty.
        """
        validation_result = validate_spec_completeness(self._spec)

        report = CompletenessReport(
            is_complete=validation_result["is_complete"],
            missing_fields=validation_result["missing_fields"],
            empty_fields=validation_result["empty_fields"],
        )
        self._completeness_report = report

        if not report.is_complete:
            raise SpecIncompleteError(
                missing_fields=report.missing_fields,
                empty_fields=report.empty_fields,
            )

        return report

    def _create_draft(self) -> Dict[str, Any]:
        """Generate a draft based on the validated specification.

        Only invoked when ``_check_spec_completeness()`` succeeds.

        Returns:
            A draft dictionary referencing the spec.
        """
        draft: Dict[str, Any] = {
            "spec_title": self._spec.get("title", ""),
            "content": f"Draft based on: {self._spec.get('title', 'Untitled')}",
            "status": "draft",
        }
        self._draft = draft
        return draft