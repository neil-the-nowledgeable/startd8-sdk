"""Centralized prompt templates for the 8-phase Artisan Contractor system.

Provides draft and validate prompts for each phase, reviewer/arbiter prompts,
and few-shot examples. This module is the single source of truth for all
prompt engineering across the pipeline.

Usage::

    from prompt_templates import Phase, Action, Role
    from prompt_templates import get_phase_prompt, get_role_prompt, get_few_shot_example

    # Get a draft prompt with variables filled in
    prompt = get_phase_prompt(
        Phase.DISCOVER, Action.DRAFT,
        project_name="MyProject",
        project_description="A web app for ...",
        input_artifacts="<stakeholder interviews...>"
    )

    # Get a reviewer prompt
    review = get_role_prompt(
        Role.REVIEWER,
        project_name="MyProject",
        phase_name="discover",
        action_name="draft",
        artifact_content="<the artifact...>",
        original_prompt="<the prompt used...>"
    )

    # Get few-shot examples to prepend to a prompt
    example = get_few_shot_example(Phase.DISCOVER)

Public API:
    - Phase, Action, Role: Enums for type-safe prompt selection.
    - get_phase_prompt(phase, action, **kwargs) -> str
    - get_role_prompt(role, **kwargs) -> str
    - get_few_shot_example(phase) -> str
    - list_available_prompts() -> List[str]
"""

from __future__ import annotations

from enum import Enum
from string import Formatter
from typing import Any, Dict, List, Tuple


# =============================================================================
# ENUMS
# =============================================================================


class Phase(Enum):
    """Generic lifecycle phases for prompt template lookup.

    NOTE: These are a *prompt taxonomy*, not the 9-phase artisan pipeline.
    The actual artisan phases live in ``artisan_phases/`` and are
    orchestrated by ``WorkflowPhase`` in ``artisan_contractor.py``.
    """

    DISCOVER = "discover"
    DEFINE = "define"
    DESIGN = "design"
    DEVELOP = "develop"
    TEST = "test"
    DOCUMENT = "document"
    DEPLOY = "deploy"
    MAINTAIN = "maintain"


class Action(Enum):
    """Draft or Validate action within a phase."""

    DRAFT = "draft"
    VALIDATE = "validate"


class Role(Enum):
    """Roles for review prompts."""

    REVIEWER = "reviewer"
    ARBITER = "arbiter"


# =============================================================================
# SAFE FORMATTER (leaves unresolved placeholders intact)
# =============================================================================


class SafeFormatter(Formatter):
    """A string formatter that leaves unmatched ``{placeholder}`` markers intact.

    This prevents ``KeyError`` when only a subset of template variables are
    supplied, which is common during progressive prompt assembly.
    """

    def get_value(
        self, key: Any, args: tuple[Any, ...], kwargs: dict[str, Any]
    ) -> Any:
        """Return the value for *key*, or the raw placeholder if missing."""
        if isinstance(key, str):
            return kwargs.get(key, "{" + key + "}")
        return super().get_value(key, args, kwargs)

    def format_field(self, value: Any, format_spec: str) -> str:
        """Format a field, preserving unresolved placeholder strings."""
        if isinstance(value, str) and value.startswith("{") and value.endswith("}"):
            return value
        return super().format_field(value, format_spec)


_safe_formatter = SafeFormatter()


# =============================================================================
# PHASE PROMPTS: 8 phases × 2 actions = 16 prompts
# =============================================================================

_PHASE_PROMPTS: Dict[Tuple[Phase, Action], str] = {
    # -------------------------------------------------------------------------
    # DISCOVER
    # -------------------------------------------------------------------------
    (Phase.DISCOVER, Action.DRAFT): (
        "You are an expert discovery analyst. Your task is to produce a "
        "comprehensive discovery document for the project.\n\n"
        "Project Name: {project_name}\n"
        "Project Description: {project_description}\n\n"
        "Analyze the following inputs and produce a structured discovery report "
        "covering:\n"
        "1. Stakeholder identification and their needs\n"
        "2. Problem domain analysis\n"
        "3. Existing solutions and competitive landscape\n"
        "4. Key assumptions and risks identified early\n"
        "5. Initial scope boundaries and constraints\n"
        "6. Data sources and integration points\n\n"
        "Inputs provided:\n"
        "{input_artifacts}\n\n"
        "Produce a thorough discovery document in Markdown format. Be specific "
        "and actionable. Do not leave sections empty. If information is missing, "
        "state what is unknown and recommend how to resolve it."
    ),
    (Phase.DISCOVER, Action.VALIDATE): (
        "You are an expert discovery validator. Review the following "
        "discovery document and assess its quality.\n\n"
        "Project Name: {project_name}\n\n"
        "Discovery Document to Validate:\n"
        "{draft_content}\n\n"
        "Evaluate the document against these criteria:\n"
        "1. Completeness: Are all key stakeholders, risks, and constraints "
        "identified?\n"
        "2. Accuracy: Are the claims and assumptions reasonable and "
        "well-supported?\n"
        "3. Clarity: Is the document clear, well-organized, and free of "
        "ambiguity?\n"
        "4. Actionability: Does the document provide enough detail to proceed "
        "to Define phase?\n"
        "5. Gaps: Are there any obvious omissions or blind spots?\n\n"
        'Provide your validation result as a JSON object with the following '
        'structure:\n'
        '{{"is_valid": true, "score": 85, "issues": ["issue1"], "suggestions": '
        '["suggestion1"]}}'
    ),
    # -------------------------------------------------------------------------
    # DEFINE
    # -------------------------------------------------------------------------
    (Phase.DEFINE, Action.DRAFT): (
        "You are an expert requirements analyst. Your task is to produce "
        "a detailed requirements specification document.\n\n"
        "Project Name: {project_name}\n"
        "Discovery Artifacts:\n"
        "{input_artifacts}\n\n"
        "Produce a requirements document that includes:\n"
        "1. Functional requirements with unique IDs (e.g., FR-001)\n"
        "2. Non-functional requirements (performance, security, scalability, "
        "usability)\n"
        "3. User stories in the format: As a [role], I want [feature], so that "
        "[benefit]\n"
        "4. Acceptance criteria for each requirement\n"
        "5. Priority classification (Must Have, Should Have, Could Have, "
        "Won't Have)\n"
        "6. Dependencies between requirements\n"
        "7. Traceability to discovery findings\n\n"
        "Format the output in structured Markdown with clear section headings."
    ),
    (Phase.DEFINE, Action.VALIDATE): (
        "You are an expert requirements validator. Review the following "
        "requirements specification for completeness and quality.\n\n"
        "Project Name: {project_name}\n\n"
        "Requirements Document to Validate:\n"
        "{draft_content}\n\n"
        "Evaluate against these criteria:\n"
        "1. Each requirement must be testable and unambiguous\n"
        "2. Requirements must be traceable to stakeholder needs\n"
        "3. No conflicting requirements exist\n"
        "4. Priority assignments are reasonable and justified\n"
        "5. Acceptance criteria are specific and measurable\n"
        "6. Coverage of both functional and non-functional aspects is "
        "adequate\n\n"
        'Provide your validation result as a JSON object:\n'
        '{{"is_valid": true, "score": 90, "issues": [], "suggestions": '
        '["suggestion1"]}}'
    ),
    # -------------------------------------------------------------------------
    # DESIGN
    # -------------------------------------------------------------------------
    (Phase.DESIGN, Action.DRAFT): (
        "You are an expert software architect. Your task is to produce "
        "a comprehensive design document.\n\n"
        "Project Name: {project_name}\n"
        "Requirements Artifacts:\n"
        "{input_artifacts}\n\n"
        "Produce a design document covering:\n"
        "1. High-level architecture diagram description (components, layers, "
        "boundaries)\n"
        "2. Technology stack selection with justification\n"
        "3. Data model and schema design\n"
        "4. API contract definitions (endpoints, request/response schemas)\n"
        "5. Component interaction patterns (sync, async, event-driven)\n"
        "6. Security architecture (authentication, authorization, encryption)\n"
        "7. Scalability and performance design considerations\n"
        "8. Error handling and resilience patterns\n"
        "9. Deployment topology overview\n\n"
        "Use Markdown format with clear sections. Include pseudo-diagrams "
        "using ASCII or Mermaid syntax where helpful."
    ),
    (Phase.DESIGN, Action.VALIDATE): (
        "You are an expert architecture reviewer. Review the following "
        "design document for technical soundness and completeness.\n\n"
        "Project Name: {project_name}\n\n"
        "Design Document to Validate:\n"
        "{draft_content}\n\n"
        "Evaluate against these criteria:\n"
        "1. Architecture supports all defined requirements\n"
        "2. Technology choices are appropriate and well-justified\n"
        "3. Data model is normalized appropriately and handles edge cases\n"
        "4. API design follows RESTful or other stated conventions "
        "consistently\n"
        "5. Security considerations are adequate for the domain\n"
        "6. Design handles scalability requirements\n"
        "7. Error handling and failure modes are addressed\n"
        "8. No single points of failure in critical paths\n\n"
        'Provide your validation result as a JSON object:\n'
        '{{"is_valid": true, "score": 88, "issues": [], "suggestions": '
        '["suggestion1"]}}'
    ),
    # -------------------------------------------------------------------------
    # DEVELOP
    # -------------------------------------------------------------------------
    (Phase.DEVELOP, Action.DRAFT): (
        "You are an expert software developer. Your task is to produce "
        "implementation code based on the provided design specifications.\n\n"
        "Project Name: {project_name}\n"
        "Design Artifacts:\n"
        "{input_artifacts}\n\n"
        "Target Language/Framework: {target_language}\n\n"
        "Produce production-quality code that:\n"
        "1. Implements all components specified in the design document\n"
        "2. Follows established coding conventions and style guides\n"
        "3. Includes proper error handling and input validation\n"
        "4. Uses appropriate design patterns as specified\n"
        "5. Includes inline documentation and docstrings\n"
        "6. Handles edge cases identified in requirements\n"
        "7. Is modular, testable, and maintainable\n\n"
        "Output the code with clear file-path headers indicating where each "
        "file belongs. Include any necessary configuration files."
    ),
    (Phase.DEVELOP, Action.VALIDATE): (
        "You are an expert code reviewer. Review the following "
        "implementation code for quality, correctness, and adherence to the "
        "design specification.\n\n"
        "Project Name: {project_name}\n\n"
        "Code to Validate:\n"
        "{draft_content}\n\n"
        "Design Specification Reference:\n"
        "{design_reference}\n\n"
        "Evaluate against these criteria:\n"
        "1. Code correctly implements the design specification\n"
        "2. Error handling is comprehensive and appropriate\n"
        "3. Code follows language-specific best practices and style guides\n"
        "4. No security vulnerabilities (injection, XSS, CSRF, etc.)\n"
        "5. Performance considerations are addressed (no N+1 queries, proper "
        "indexing)\n"
        "6. Code is DRY, modular, and follows SOLID principles\n"
        "7. Edge cases from requirements are handled\n"
        "8. Dependencies are appropriate and up-to-date\n\n"
        'Provide your validation result as a JSON object:\n'
        '{{"is_valid": true, "score": 87, "issues": [], "suggestions": '
        '["suggestion1"]}}'
    ),
    # -------------------------------------------------------------------------
    # TEST
    # -------------------------------------------------------------------------
    (Phase.TEST, Action.DRAFT): (
        "You are an expert test engineer. Your task is to produce a "
        "comprehensive test suite for the implemented code.\n\n"
        "Project Name: {project_name}\n"
        "Implementation Artifacts:\n"
        "{input_artifacts}\n\n"
        "Requirements Reference:\n"
        "{requirements_reference}\n\n"
        "Produce a test suite that includes:\n"
        "1. Unit tests for all public functions and methods\n"
        "2. Integration tests for component interactions\n"
        "3. Edge case tests derived from requirements\n"
        "4. Error path tests (invalid inputs, network failures, timeouts)\n"
        "5. Performance/load test specifications where applicable\n"
        "6. Test data fixtures and factories\n"
        "7. Mocking strategies for external dependencies\n\n"
        "Use the project's testing framework. Include clear test names that "
        "describe the behavior being tested. Aim for at least 80 percent code "
        "coverage."
    ),
    (Phase.TEST, Action.VALIDATE): (
        "You are an expert test quality analyst. Review the following "
        "test suite for completeness, correctness, and effectiveness.\n\n"
        "Project Name: {project_name}\n\n"
        "Test Suite to Validate:\n"
        "{draft_content}\n\n"
        "Implementation Reference:\n"
        "{implementation_reference}\n\n"
        "Evaluate against these criteria:\n"
        "1. Test coverage is adequate (all public interfaces tested)\n"
        "2. Tests are independent and can run in any order\n"
        "3. Edge cases and error paths are covered\n"
        "4. Test assertions are specific and meaningful (not just "
        '"no exception")\n'
        "5. Test data is representative and includes boundary values\n"
        "6. Mocking is appropriate and does not hide bugs\n"
        "7. Tests are maintainable and clearly named\n"
        "8. No flaky tests or timing-dependent assertions\n\n"
        'Provide your validation result as a JSON object:\n'
        '{{"is_valid": true, "score": 85, "issues": [], "suggestions": '
        '["suggestion1"]}}'
    ),
    # -------------------------------------------------------------------------
    # DOCUMENT
    # -------------------------------------------------------------------------
    (Phase.DOCUMENT, Action.DRAFT): (
        "You are an expert technical writer. Your task is to produce "
        "comprehensive documentation for the project.\n\n"
        "Project Name: {project_name}\n"
        "Implementation Artifacts:\n"
        "{input_artifacts}\n\n"
        "API Specifications:\n"
        "{api_specifications}\n\n"
        "Produce documentation that includes:\n"
        "1. README with project overview, quick start, and installation "
        "instructions\n"
        "2. API reference documentation with examples for each endpoint\n"
        "3. Architecture overview for developers\n"
        "4. Configuration guide with all environment variables and options\n"
        "5. Troubleshooting guide with common issues and solutions\n"
        "6. Contributing guidelines\n"
        "7. Changelog template\n\n"
        "Format all documentation in Markdown. Include code examples that are "
        "correct and runnable. Use clear headings and cross-references between "
        "documents."
    ),
    (Phase.DOCUMENT, Action.VALIDATE): (
        "You are an expert documentation reviewer. Review the "
        "following documentation for accuracy, completeness, and usability.\n\n"
        "Project Name: {project_name}\n\n"
        "Documentation to Validate:\n"
        "{draft_content}\n\n"
        "Implementation Reference:\n"
        "{implementation_reference}\n\n"
        "Evaluate against these criteria:\n"
        "1. All public APIs are documented with correct signatures and "
        "examples\n"
        "2. Installation and setup instructions are complete and accurate\n"
        "3. Code examples compile/run correctly\n"
        "4. Documentation is free of typos and grammatical errors\n"
        "5. Cross-references and links are valid\n"
        "6. Documentation matches the current implementation (no stale "
        "content)\n"
        "7. Audience-appropriate language is used consistently\n"
        "8. All configuration options are documented\n\n"
        'Provide your validation result as a JSON object:\n'
        '{{"is_valid": true, "score": 89, "issues": [], "suggestions": '
        '["suggestion1"]}}'
    ),
    # -------------------------------------------------------------------------
    # DEPLOY
    # -------------------------------------------------------------------------
    (Phase.DEPLOY, Action.DRAFT): (
        "You are an expert DevOps engineer. Your task is to produce "
        "deployment configurations and infrastructure-as-code for the "
        "project.\n\n"
        "Project Name: {project_name}\n"
        "Design and Implementation Artifacts:\n"
        "{input_artifacts}\n\n"
        "Target Environment: {target_environment}\n\n"
        "Produce deployment artifacts that include:\n"
        "1. Dockerfile(s) with multi-stage builds optimized for production\n"
        "2. Docker Compose or Kubernetes manifests for orchestration\n"
        "3. CI/CD pipeline configuration (GitHub Actions, GitLab CI, or "
        "similar)\n"
        "4. Environment-specific configuration management\n"
        "5. Health check and readiness probe definitions\n"
        "6. Logging and monitoring configuration\n"
        "7. Secrets management approach\n"
        "8. Rollback procedures and blue-green or canary deployment strategy\n"
        "9. Infrastructure provisioning scripts if applicable\n\n"
        "Ensure all configurations follow security best practices (non-root "
        "users, minimal base images, secret rotation)."
    ),
    (Phase.DEPLOY, Action.VALIDATE): (
        "You are an expert infrastructure reviewer. Review the "
        "following deployment configurations for correctness, security, and "
        "operational readiness.\n\n"
        "Project Name: {project_name}\n\n"
        "Deployment Configurations to Validate:\n"
        "{draft_content}\n\n"
        "Design Reference:\n"
        "{design_reference}\n\n"
        "Evaluate against these criteria:\n"
        "1. Containers run as non-root users with minimal privileges\n"
        "2. Secrets are not hardcoded; proper secrets management is in place\n"
        "3. Health checks and readiness probes are correctly configured\n"
        "4. Resource limits (CPU, memory) are defined appropriately\n"
        "5. CI/CD pipeline includes build, test, and deploy stages\n"
        "6. Rollback mechanism is defined and tested\n"
        "7. Logging captures sufficient operational information\n"
        "8. Network policies and access controls are appropriate\n\n"
        'Provide your validation result as a JSON object:\n'
        '{{"is_valid": true, "score": 86, "issues": [], "suggestions": '
        '["suggestion1"]}}'
    ),
    # -------------------------------------------------------------------------
    # MAINTAIN
    # -------------------------------------------------------------------------
    (Phase.MAINTAIN, Action.DRAFT): (
        "You are an expert site reliability engineer. Your task is "
        "to produce a maintenance and operations plan for the project.\n\n"
        "Project Name: {project_name}\n"
        "All Prior Phase Artifacts:\n"
        "{input_artifacts}\n\n"
        "Produce a maintenance plan that includes:\n"
        "1. Monitoring and alerting strategy with specific metrics and "
        "thresholds\n"
        "2. Incident response procedures with severity classifications\n"
        "3. Backup and disaster recovery plan with RTO/RPO targets\n"
        "4. Dependency update and security patching schedule\n"
        "5. Performance baseline and capacity planning approach\n"
        "6. On-call rotation and escalation procedures\n"
        "7. Runbook for common operational tasks\n"
        "8. Technical debt tracking and remediation plan\n"
        "9. SLA definitions and compliance reporting approach\n\n"
        "The plan should be actionable and include specific tool "
        "recommendations where appropriate."
    ),
    (Phase.MAINTAIN, Action.VALIDATE): (
        "You are an expert operations reviewer. Review the "
        "following maintenance plan for completeness and operational "
        "readiness.\n\n"
        "Project Name: {project_name}\n\n"
        "Maintenance Plan to Validate:\n"
        "{draft_content}\n\n"
        "Deployment Reference:\n"
        "{deployment_reference}\n\n"
        "Evaluate against these criteria:\n"
        "1. Monitoring covers all critical system components and business "
        "metrics\n"
        "2. Alerting thresholds are reasonable and avoid alert fatigue\n"
        "3. Incident response procedures are clear and complete\n"
        "4. Backup and DR plan meets stated RTO/RPO targets\n"
        "5. Security patching process is defined with acceptable timelines\n"
        "6. Capacity planning accounts for projected growth\n"
        "7. Runbooks are detailed enough for on-call engineers to follow\n"
        "8. SLA targets are realistic and measurable\n\n"
        'Provide your validation result as a JSON object:\n'
        '{{"is_valid": true, "score": 84, "issues": [], "suggestions": '
        '["suggestion1"]}}'
    ),
}


# =============================================================================
# ROLE PROMPTS
# =============================================================================

_ROLE_PROMPTS: Dict[Role, str] = {
    Role.REVIEWER: (
        "You are a meticulous peer reviewer with deep expertise in software "
        "engineering. Your role is to review artifacts produced during the "
        "{phase_name} phase.\n\n"
        "Review Context:\n"
        "- Project: {project_name}\n"
        "- Phase: {phase_name}\n"
        "- Action: {action_name}\n\n"
        "Artifact to Review:\n"
        "{artifact_content}\n\n"
        "Original Prompt Used:\n"
        "{original_prompt}\n\n"
        "Your review must:\n"
        "1. Identify factual errors, logical inconsistencies, or missing "
        "elements\n"
        "2. Assess adherence to the original prompt requirements\n"
        "3. Evaluate quality relative to industry best practices\n"
        "4. Provide specific, actionable feedback (not vague observations)\n"
        "5. Rate overall quality on a scale of 1-10\n"
        "6. Recommend APPROVE, REVISE, or REJECT\n\n"
        'Provide your review as a JSON object:\n'
        '{{"decision": "APPROVE", "quality_score": 8, "errors": [], '
        '"suggestions": ["suggestion1"], "summary": "Brief overall '
        'assessment"}}'
    ),
    Role.ARBITER: (
        "You are a senior technical arbiter responsible for making final "
        "decisions when reviewers disagree or when an artifact has been "
        "through multiple revision cycles.\n\n"
        "Arbitration Context:\n"
        "- Project: {project_name}\n"
        "- Phase: {phase_name}\n"
        "- Revision Cycle: {revision_number}\n\n"
        "Original Artifact:\n"
        "{artifact_content}\n\n"
        "Review Feedback Received:\n"
        "{review_feedback}\n\n"
        "Revision History:\n"
        "{revision_history}\n\n"
        "As arbiter, you must:\n"
        "1. Weigh all reviewer feedback objectively\n"
        "2. Determine which feedback items are critical vs. nice-to-have\n"
        "3. Consider the cost of further revisions vs. the benefit\n"
        "4. Make a definitive ACCEPT or REJECT decision\n"
        "5. If accepting with known issues, document them as accepted "
        "technical debt\n"
        "6. Provide clear rationale for your decision\n\n"
        'Provide your arbitration result as a JSON object:\n'
        '{{"final_decision": "ACCEPT", "rationale": "Detailed reasoning", '
        '"critical_issues_resolved": true, "accepted_debt": [], '
        '"mandatory_follow_ups": []}}'
    ),
}


# =============================================================================
# FEW-SHOT EXAMPLES
# =============================================================================

_FEW_SHOT_EXAMPLES: Dict[Phase, str] = {
    Phase.DISCOVER: (
        "## Few-Shot Example: Discovery Phase\n\n"
        "### Input:\n"
        "Project Name: TaskFlow\n"
        "Project Description: A task management application for small teams\n\n"
        "### Expected Output:\n"
        "# Discovery Report: TaskFlow\n\n"
        "## 1. Stakeholder Identification\n"
        "- **Team Leads**: Need visibility into team workload and progress\n"
        "- **Individual Contributors**: Need a simple interface to manage "
        "daily tasks\n"
        "- **Project Managers**: Need reporting and timeline tracking\n\n"
        "## 2. Problem Domain Analysis\n"
        "The task management space is crowded but most solutions are overly "
        "complex for small teams (under 10 people). Key pain points include "
        "context switching between tools and lack of simple priority "
        "management.\n\n"
        "## 3. Competitive Landscape\n"
        "| Competitor | Strengths | Weaknesses |\n"
        "|-----------|-----------|------------|\n"
        "| Trello | Visual boards | Limited reporting |\n"
        "| Asana | Feature-rich | Complex for small teams |\n"
        "| Todoist | Simple | No team features |\n\n"
        "## 4. Key Assumptions\n"
        "- Teams are co-located or fully remote (not hybrid)\n"
        "- Maximum team size is 10 members\n"
        "- Integration with Slack is a must-have\n\n"
        "## 5. Risks Identified\n"
        "- Market saturation may limit adoption\n"
        "- Small team focus limits revenue per account\n"
        "- Integration complexity may delay launch"
    ),
    Phase.DEFINE: (
        "## Few-Shot Example: Define Phase\n\n"
        "### Input:\n"
        "Discovery report identifying need for task management with team "
        "collaboration\n\n"
        "### Expected Output:\n"
        "# Requirements Specification: TaskFlow\n\n"
        "## Functional Requirements\n\n"
        "### FR-001: Task Creation\n"
        "- **Description**: Users can create tasks with title, description, "
        "due date\n"
        "- **Priority**: Must Have\n"
        "- **Acceptance Criteria**:\n"
        "  - Task title is required, max 200 characters\n"
        "  - Description is optional, supports Markdown\n"
        "  - Due date defaults to none if not set\n"
        "  - Priority levels: Low, Medium, High, Urgent\n\n"
        "### FR-002: Task Assignment\n"
        "- **Description**: Users can assign tasks to team members\n"
        "- **Priority**: Must Have\n"
        "- **User Story**: As a team lead, I want to assign tasks to team "
        "members\n\n"
        "## Non-Functional Requirements\n\n"
        "### NFR-001: Response Time\n"
        "- All API responses must complete within 200ms at p95\n"
        "- Dashboard must render within 1 second on 3G connection\n"
        "- System must support 10 concurrent teams"
    ),
    Phase.DESIGN: (
        "## Few-Shot Example: Design Phase\n\n"
        "### Input:\n"
        "Requirements specification for TaskFlow task management "
        "application\n\n"
        "### Expected Output:\n"
        "# Design Document: TaskFlow\n\n"
        "## 1. High-Level Architecture\n\n"
        "The system uses a layered architecture with separation between "
        "frontend, API gateway, and backend services:\n"
        "- Web frontend communicates with API Gateway via HTTPS\n"
        "- API Gateway routes requests to microservices (Task Service, User "
        "Service)\n"
        "- Services use PostgreSQL for persistence and Redis for caching\n\n"
        "## 2. Technology Stack\n"
        "- **Backend**: Python 3.11 with FastAPI framework\n"
        "- **Database**: PostgreSQL 15 with SQLAlchemy ORM\n"
        "- **Cache**: Redis 7 for session and rate limit management\n"
        "- **Frontend**: React 18 with TypeScript for type safety\n"
        "- **Justification**: FastAPI provides async support, auto-generated "
        "docs\n\n"
        "## 3. Data Model\n"
        "Tables include: tasks (id, title, status, priority), users (id, "
        "email, name), and teams (id, name). Relationships are normalized to "
        "third normal form."
    ),
    Phase.DEVELOP: (
        "## Few-Shot Example: Develop Phase\n\n"
        "### Input:\n"
        "Design document specifying FastAPI task service\n\n"
        "### Expected Output:\n"
        "# Implementation: Task Service\n\n"
        "## File: src/models/task.py\n"
        "Contains SQLAlchemy model definitions for tasks table with proper "
        "indexing on status and priority fields for query performance.\n\n"
        "## File: src/routes/tasks.py\n"
        "Implements REST API endpoints:\n"
        "- POST /tasks: Create task (validates title length, priority "
        "values)\n"
        "- GET /tasks: List tasks with pagination and filtering\n"
        "- PATCH /tasks/{id}: Update task status and priority\n"
        "- DELETE /tasks/{id}: Remove task\n\n"
        "## File: src/validators.py\n"
        "Input validation schemas using Pydantic with proper error "
        "messages.\n\n"
        "All code includes docstrings, type hints, and comprehensive error "
        "handling."
    ),
    Phase.TEST: (
        "## Few-Shot Example: Test Phase\n\n"
        "### Input:\n"
        "Implementation code for task service\n\n"
        "### Expected Output:\n"
        "# Test Suite: Task Service\n\n"
        "## Coverage Strategy\n"
        "- Unit tests for all validation functions\n"
        "- Integration tests for API endpoints with database\n"
        "- Edge case tests for boundary values and null handling\n\n"
        "## Key Test Cases\n\n"
        "Test create_task_with_valid_input: Verify 201 response and correct "
        "fields\n"
        "Test create_task_missing_title: Verify 422 unprocessable entity "
        "response\n"
        "Test create_task_title_exceeds_max: Verify validation rejects 201 "
        "characters\n"
        "Test get_tasks_with_filters: Test pagination offset/limit "
        "parameters\n"
        "Test update_nonexistent_task: Verify 404 not found response\n"
        "Test concurrent_task_creation: Ensure no race conditions\n\n"
        "Targets 85+ percent code coverage with pytest framework."
    ),
    Phase.DOCUMENT: (
        "## Few-Shot Example: Document Phase\n\n"
        "### Input:\n"
        "Implementation and API specifications for TaskFlow\n\n"
        "### Expected Output:\n"
        "# TaskFlow Documentation\n\n"
        "## README.md\n"
        "- Overview: One-paragraph description of TaskFlow\n"
        "- Quick Start: Clone, install, setup database, run server in 5 "
        "steps\n"
        "- Features: Bulleted list of key capabilities\n"
        "- Requirements: Python 3.11+, PostgreSQL 15, Redis 7\n"
        "- Installation: pip install from requirements.txt\n\n"
        "## API Reference\n\n"
        "### Create Task\n"
        "- **POST** /api/v1/tasks/\n"
        "- **Request**: title (string, required), priority (enum)\n"
        "- **Response**: 201 with task object including generated id\n"
        "- **Error**: 422 if title missing or exceeds 200 chars\n\n"
        "### List Tasks\n"
        "- **GET** /api/v1/tasks/?skip=0&limit=10\n"
        "- **Response**: 200 with paginated task array\n"
        "- **Error**: 400 if limit exceeds max of 100\n\n"
        "## Architecture Overview\n"
        "High-level component diagram and API flow description for "
        "developers."
    ),
    Phase.DEPLOY: (
        "## Few-Shot Example: Deploy Phase\n\n"
        "### Input:\n"
        "Implementation and design artifacts for TaskFlow\n\n"
        "### Expected Output:\n"
        "# Deployment Configuration: TaskFlow\n\n"
        "## Dockerfile Multi-stage Build\n"
        "- Builder stage: Installs Python dependencies into wheels\n"
        "- Runtime stage: Uses python:3.11-slim, copies wheels, runs as "
        "non-root user\n"
        "- Exposes port 8000 with HEALTHCHECK using curl on /health "
        "endpoint\n\n"
        "## docker-compose.yml\n"
        "Services: api (FastAPI app), db (PostgreSQL), redis (cache)\n"
        "Environment variables: DATABASE_URL, REDIS_URL, SECRET_KEY from "
        ".env\n"
        "Volume: pgdata persists PostgreSQL data\n\n"
        "## GitHub Actions CI/CD\n"
        "- Trigger: push to main branch\n"
        "- Build: Docker image, run tests, security scan\n"
        "- Deploy: Push to registry, update Kubernetes manifests\n"
        "- Rollback: kubectl rollout undo if health checks fail"
    ),
    Phase.MAINTAIN: (
        "## Few-Shot Example: Maintain Phase\n\n"
        "### Input:\n"
        "All prior phase artifacts for TaskFlow\n\n"
        "### Expected Output:\n"
        "# Maintenance Plan: TaskFlow\n\n"
        "## 1. Monitoring Strategy\n\n"
        "Key Metrics:\n"
        "- API Response Time p95: Alert if > 500ms (Warning), > 1000ms "
        "(Critical)\n"
        "- Error Rate 5xx: Alert if > 1% of requests\n"
        "- CPU Utilization: Alert if > 80%\n"
        "- Database Connection Pool: Alert if > 80% utilized\n\n"
        "Tools: Datadog APM, ELK Stack for logs, Prometheus for metrics\n\n"
        "## 2. Incident Response\n"
        "- SEV-1 (Outage): Response 15 min, escalate to lead\n"
        "- SEV-2 (Degraded): Response 1 hour, coordinate with team\n"
        "- SEV-3 (Minor): Response 4 hours, document issue\n\n"
        "## 3. Backup and Disaster Recovery\n"
        "- RTO: 1 hour max recovery time\n"
        "- RPO: 15 minute data loss acceptable\n"
        "- Strategy: WAL archiving to S3 daily, weekly full backups\n"
        "- Test: Monthly restore drill from backup\n\n"
        "## 4. Dependency Updates\n"
        "- Critical security patches: Within 24 hours\n"
        "- Regular updates: Monthly cycle, test before deploy"
    ),
}


# =============================================================================
# PUBLIC API FUNCTIONS
# =============================================================================


def get_phase_prompt(phase: Phase, action: Action, **kwargs: Any) -> str:
    """Retrieve and optionally format a phase prompt template.

    Args:
        phase: The pipeline phase (one of the 8 ``Phase`` enum members).
        action: ``Action.DRAFT`` or ``Action.VALIDATE``.
        **kwargs: Format parameters to substitute into the template.
            Common keys include ``project_name``, ``project_description``,
            ``input_artifacts``, ``draft_content``, and phase-specific keys
            like ``target_language`` or ``design_reference``.

    Returns:
        The prompt string with supplied placeholders resolved.  Placeholders
        for which no value was given are left as literal ``{name}`` markers
        so the caller can fill them later.

    Raises:
        TypeError: If *phase* is not a ``Phase`` or *action* is not an
            ``Action``.
        KeyError: If no prompt exists for the combination.

    Examples:
        >>> prompt = get_phase_prompt(
        ...     Phase.DISCOVER, Action.DRAFT,
        ...     project_name="Acme", project_description="A SaaS tool",
        ...     input_artifacts="<interviews>",
        ... )
        >>> "Acme" in prompt
        True
    """
    if not isinstance(phase, Phase):
        raise TypeError(
            f"phase must be a Phase enum, got {type(phase).__name__}"
        )
    if not isinstance(action, Action):
        raise TypeError(
            f"action must be an Action enum, got {type(action).__name__}"
        )

    key = (phase, action)
    if key not in _PHASE_PROMPTS:
        raise KeyError(
            f"No prompt found for phase={phase.value!r}, "
            f"action={action.value!r}"
        )

    template = _PHASE_PROMPTS[key]
    if kwargs:
        return _safe_formatter.format(template, **kwargs)
    return template


def get_role_prompt(role: Role, **kwargs: Any) -> str:
    """Retrieve and optionally format a role prompt template.

    Args:
        role: ``Role.REVIEWER`` or ``Role.ARBITER``.
        **kwargs: Format parameters.  Common keys include ``project_name``,
            ``phase_name``, ``action_name``, ``artifact_content``,
            ``original_prompt``, ``review_feedback``, ``revision_history``,
            and ``revision_number``.

    Returns:
        The prompt string with supplied placeholders resolved.

    Raises:
        TypeError: If *role* is not a ``Role``.
        KeyError: If no prompt exists for the role.

    Examples:
        >>> prompt = get_role_prompt(
        ...     Role.REVIEWER,
        ...     project_name="Acme",
        ...     phase_name="design",
        ...     action_name="draft",
        ...     artifact_content="<artifact>",
        ...     original_prompt="<prompt>",
        ... )
        >>> "Acme" in prompt
        True
    """
    if not isinstance(role, Role):
        raise TypeError(
            f"role must be a Role enum, got {type(role).__name__}"
        )

    if role not in _ROLE_PROMPTS:
        raise KeyError(f"No prompt found for role={role.value!r}")

    template = _ROLE_PROMPTS[role]
    if kwargs:
        return _safe_formatter.format(template, **kwargs)
    return template


def get_few_shot_example(phase: Phase) -> str:
    """Retrieve the few-shot example for a given phase.

    The returned string contains an illustrative input/output pair that can
    be prepended to a draft prompt to improve LLM output quality.

    Args:
        phase: The pipeline phase.

    Returns:
        A Markdown-formatted few-shot example string.

    Raises:
        TypeError: If *phase* is not a ``Phase``.
        KeyError: If no example exists for the phase.

    Examples:
        >>> example = get_few_shot_example(Phase.DISCOVER)
        >>> "TaskFlow" in example
        True
    """
    if not isinstance(phase, Phase):
        raise TypeError(
            f"phase must be a Phase enum, got {type(phase).__name__}"
        )

    if phase not in _FEW_SHOT_EXAMPLES:
        raise KeyError(
            f"No few-shot example found for phase={phase.value!r}"
        )

    return _FEW_SHOT_EXAMPLES[phase]


def list_available_prompts() -> List[str]:
    """List all available prompt identifiers.

    Returns:
        A sorted list of 18 string identifiers:

        - 16 phase prompts: ``"phase:<name>:action:<action>"``
        - 2 role prompts:   ``"role:<name>"``

    Examples:
        >>> ids = list_available_prompts()
        >>> len(ids)
        18
        >>> "phase:discover:action:draft" in ids
        True
        >>> "role:reviewer" in ids
        True
    """
    result: List[str] = []

    for phase, action in _PHASE_PROMPTS:
        result.append(f"phase:{phase.value}:action:{action.value}")

    for role in _ROLE_PROMPTS:
        result.append(f"role:{role.value}")

    return result