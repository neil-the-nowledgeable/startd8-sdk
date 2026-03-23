"""
PlanIngestionWorkflow — Parse a generic plan, assess complexity,
transform into SDK-native format, refine via architectural review,
and emit the plan doc + review-config.json.

Pipeline:  parse → assess → transform → refine → emit
"""

from __future__ import annotations

import ast
import json
import os
import re
import time
from hashlib import sha256
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from dataclasses import replace as _dataclass_replace
from typing import TYPE_CHECKING, Any, Dict, List, NamedTuple, Optional, Set, Tuple, Union

import yaml

if TYPE_CHECKING:
    from startd8.forward_manifest import ForwardElementSpec, ForwardManifest, InterfaceContract

from ..base import WorkflowBase, ProgressCallback
from ..models import (
    AgentCount,
    StepResult,
    WorkflowInput,
    WorkflowMetadata,
    WorkflowMetrics,
    WorkflowResult,
)
from ...agents import BaseAgent
from ...agents.pool import TimeoutConfig
from ...model_catalog import Models
from ...utils.agent_resolution import resolve_agent_spec
from ...utils.code_extraction import extract_code_from_response
from ...utils.file_operations import atomic_write, atomic_write_json
from ...utils.retry import RetryConfig
from ...utils.token_usage import token_usage_input, token_usage_output, token_usage_cost

from .plan_ingestion_diagnostics import (
    EnrichmentDiagnostic,
    PhaseDiagnostic,
    PlanIngestionKaizenConfig,
    build_diagnostic,
    compute_assess_quality,
    compute_density_warnings,
    compute_parse_quality,
    compute_refine_quality,
    compute_seed_quality,
    compute_task_density,
    load_kaizen_config,
    persist_diagnostic,
    persist_prompt_response,
)
from .plan_ingestion_enrichment import enrich_tasks_deterministic
from .plan_ingestion_models import (
    ComplexityScore,
    ContractorRoute,
    IngestionPhase,
    IngestionState,
    ParsedFeature,
    ParsedPlan,
    PlanIngestionConfig,
)
from ...contractors.artisan_contractor import _SAFE_TASK_ID_PATTERN, _NoOpSpan, _NoOpTracer
from ...languages.registry import LanguageRegistry
from ...logging_config import get_logger
from ...seeds.utils import is_omitted

# OTel graceful degradation (follows artisan_contractor.py pattern)
try:
    from opentelemetry import trace as _trace
    from opentelemetry.trace import StatusCode as _StatusCode
    _HAS_OTEL = True
    _tracer = _trace.get_tracer("startd8.plan_ingestion")
except ImportError:
    _HAS_OTEL = False
    _tracer = _NoOpTracer()
    _StatusCode = None

logger = get_logger(__name__)

# REQ-GPC-300: profiles that require parameter resolvability in preflight
_RESOLVABILITY_PROFILES = frozenset({"full", "observability", "monitoring", "operator"})


def _infer_language_from_files(target_files: List[str]) -> str:
    """Infer language_id from target file extensions (C1: deduplicated helper).

    Returns the first matching language or ``"csharp"`` as default
    (most common non-Python target in the pipeline).
    """
    for f in target_files:
        if f.endswith(".go"):
            return "go"
        if f.endswith(".java"):
            return "java"
        if f.endswith((".js", ".ts")):
            return "nodejs"
        if f.endswith(".py"):
            return "python"
        if f.endswith(".cs"):
            return "csharp"
    return "csharp"

# QP-1: Declarative set of PARSE fields that are threaded into task context.
# Adding a new field here automatically wires it through seed assembly —
# no manual ``if feat.X: ctx["X"] = ...`` block required.
_CONTEXT_THREADABLE_FIELDS: frozenset = frozenset({
    "negative_scope",
    "api_signatures",
    "protocol",
    "runtime_dependencies",
    "design_doc_sections",
    "artifact_types_addressed",
    "requirements_refs",
    "refinement_suggestions",
    "module_path",
    "service_name",
    "mode",
    "java_package",
    "build_system",
    "java_version",
    "module_system",
    "node_version",
    "spring_boot",
    "csharp_namespace",
    "target_framework",
    "security_sensitive",
    "detected_database",
})

# JSON Schema for ContextSeed (Item 6 — validation before write)
_CONTEXT_SEED_SCHEMA: Dict[str, Any] = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "required": ["version", "tasks", "artifacts", "ingestion_metrics"],
    "properties": {
        "version": {"type": "string"},
        "schema_version": {"type": "string"},
        "source_checksum": {"type": ["string", "null"]},
        "generated_at": {"type": "string"},
        "generator": {"type": "string"},
        "plan": {"type": ["object", "null"]},
        "complexity": {"type": ["object", "null"]},
        "tasks": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["task_id", "title", "config"],
                "properties": {
                    "task_id": {"type": "string"},
                    "title": {"type": "string"},
                    "config": {"type": "object"},
                },
            },
        },
        "artifacts": {"type": "object"},
        "ingestion_metrics": {"type": "object"},
        "onboarding": {"type": ["object", "null"]},
        "architectural_context": {"type": ["object", "null"]},
        "design_calibration": {"type": ["object", "null"]},
        "context_files": {"type": ["array", "null"]},
        "service_metadata": {"type": ["object", "null"]},
        "wave_metadata": {"type": ["object", "null"]},
        "lane_assignments": {"type": ["object", "null"]},
        "project_metadata": {"type": ["object", "null"]},
    },
    "additionalProperties": True,
}


def _sha256_file_hex(path: Path) -> str:
    """Compute SHA-256 hex digest of a file."""
    hasher = sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(8192), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _validate_context_seed(data: Dict[str, Any]) -> bool:
    """Validate context seed against JSON schema before write (Item 6).

    Uses jsonschema if installed; no-op otherwise.
    Returns True if valid (or jsonschema not installed), False if validation failed.
    """
    try:
        import jsonschema

        jsonschema.validate(data, _CONTEXT_SEED_SCHEMA)
        logger.debug("Context seed validated against schema")
        return True
    except ImportError:
        return True  # Graceful fallback — jsonschema not installed
    except Exception as e:
        logger.warning(
            "Context seed schema validation failed: %s — writing anyway",
            str(e),
        )
        return False




def _validate_seed_field_coverage(seed_dict: Dict[str, Any]) -> List[str]:
    """Advisory validation: check field coverage for seed quality (Task 12).

    Distinct from _validate_context_seed() which validates JSON schema.
    This checks whether important optional fields are populated to ensure
    downstream phases have sufficient context.

    Returns:
        List of advisory warning strings (empty = all fields well-populated).
    """
    warnings: List[str] = []

    # Check tasks have sufficient detail
    tasks = seed_dict.get("tasks", [])
    if not tasks:
        warnings.append("seed has no tasks")
        return warnings

    tasks_missing_targets = sum(
        1 for t in tasks if not t.get("config", {}).get("context", {}).get("target_files")
    )
    if tasks_missing_targets > 0:
        warnings.append(
            f"{tasks_missing_targets}/{len(tasks)} task(s) missing target_files"
        )

    tasks_missing_description = sum(
        1 for t in tasks if not t.get("config", {}).get("task_description")
    )
    if tasks_missing_description > 0:
        warnings.append(
            f"{tasks_missing_description}/{len(tasks)} task(s) missing description"
        )

    # Check optional enrichment fields
    if not seed_dict.get("architectural_context"):
        warnings.append("no architectural_context — design phase may lack shared context")

    if not seed_dict.get("design_calibration"):
        warnings.append("no design_calibration — design depth tiers unavailable")

    if not seed_dict.get("service_metadata"):
        warnings.append("no service_metadata — protocol fidelity validators will be skipped")

    if not seed_dict.get("onboarding"):
        warnings.append("no onboarding metadata — parameter sources unavailable")

    if not seed_dict.get("context_files"):
        warnings.append("no context_files — provenance tracking limited")

    if not seed_dict.get("project_metadata"):
        warnings.append(
            "no project_metadata — criticality/SLO-aware generation unavailable"
        )

    return warnings


def _log_seed_coverage(seed_dict: Dict[str, Any], label: str = "") -> None:
    """Run advisory field-coverage check and log any warnings."""
    warnings = _validate_seed_field_coverage(seed_dict)
    if warnings:
        tag = f" [{label}]" if label else ""
        logger.warning(
            "Seed field-coverage advisory%s (%d warning(s)): %s",
            tag, len(warnings), "; ".join(warnings),
        )


def _ensure_onboarding_in_context_files(
    context_files_list: Optional[List[Dict[str, Any]]],
    onboarding: Optional[Dict[str, Any]],
    output_dir: Path,
) -> None:
    """REQ-PI-014: Append onboarding-metadata.json to context_files if missing."""
    if not context_files_list or not onboarding:
        return
    existing_names = {
        entry.get("path", "").rsplit("/", 1)[-1] for entry in context_files_list
    }
    if "onboarding-metadata.json" not in existing_names:
        ob_path = output_dir / "onboarding-metadata.json"
        if ob_path.exists():
            context_files_list.append({
                "path": str(ob_path),
                "checksum": _sha256_file_hex(ob_path),
            })
            logger.info("REQ-PI-014: added onboarding-metadata.json to context_files")


# ---------------------------------------------------------------------------
# LLM prompt templates
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Prompt templates — loaded from YAML with inline fallbacks
# ---------------------------------------------------------------------------
# Primary source: prompts/plan_ingestion.yaml (externalized, editable).
# Fallback: inline strings below ensure the engine works even if the YAML
# file is missing (e.g. during packaging or minimal installs).

def _fmt_prompt(prompt_name: str, **kwargs: Any) -> str:
    """Format a plan-ingestion prompt from YAML, falling back to inline strings."""
    try:
        from .prompts import format_prompt
        return format_prompt("plan_ingestion", prompt_name, **kwargs)
    except (FileNotFoundError, KeyError):
        _logger.debug("YAML template plan_ingestion.%s unavailable, using inline fallback", prompt_name)
        return _FALLBACK_PROMPTS[prompt_name].format(**kwargs)


_FALLBACK_PROMPTS: Dict[str, str] = {}

# ---------------------------------------------------------------------------
# REQ-PLI-201: Language-specific PARSE schema fields and guidance.
# Keyed by language — assembled into the PARSE prompt dynamically.
# ---------------------------------------------------------------------------
_PARSE_LANG_SCHEMA: Dict[str, str] = {
    "go": (
        '      "module_path": "optional Go module path e.g. github.com/org/repo/src/svc",\n'
        '      "service_name": "optional service directory name e.g. shippingservice"'
    ),
    "java": (
        '      "java_package": "optional Java package e.g. com.example.service",\n'
        '      "build_system": "optional: gradle or maven",\n'
        '      "java_version": "optional Java version e.g. 21"'
    ),
    "nodejs": (
        '      "module_system": "optional Node.js module system: commonjs or esm",\n'
        '      "node_version": "optional Node.js version e.g. 20"'
    ),
    "csharp": (
        '      "csharp_namespace": "optional C# root namespace e.g. MyApp.Services",\n'
        '      "target_framework": "optional .NET target framework e.g. net8.0"'
    ),
}

_PARSE_LANG_GUIDANCE: Dict[str, str] = {
    "go": (
        'module_path: (Go projects only) the Go module path for this service, typically found in go.mod or the plan\'s module structure section (e.g. "github.com/GoogleCloudPlatform/microservices-demo/src/shippingservice"). Omit or empty for non-Go projects.\n'
        'service_name: (Go projects only) the service directory name (e.g. "shippingservice", "frontend"). For Go, this determines the directory where go.mod and source files live. Infer from the target_files path (e.g. "src/shippingservice/main.go" → "shippingservice"). Omit or empty for non-Go projects.'
    ),
    "java": (
        'java_package: (Java projects only) the root Java package, inferred from target_files (e.g. "src/main/java/com/example/service/OrderService.java" → "com.example.service"). Omit or empty for non-Java projects.\n'
        'build_system: (Java projects only) "gradle" if build.gradle present, "maven" if pom.xml present. Default to "gradle" if unclear. Omit or empty for non-Java projects.\n'
        'java_version: (Java projects only) Java version from the plan or build file. Default "21". Omit or empty for non-Java projects.'
    ),
    "nodejs": (
        'module_system: (Node.js projects only) "esm" if the project uses ES modules (import/export, "type": "module" in package.json, .mjs files), "commonjs" if the project uses require()/module.exports (.cjs files, no "type" field). Default "commonjs" if unclear. Omit or empty for non-Node.js projects.\n'
        'node_version: (Node.js projects only) Node.js version from the plan. Default "20". Omit or empty for non-Node.js projects.'
    ),
    "csharp": (
        'csharp_namespace: (C# projects only) the root namespace, inferred from target file paths (e.g. "src/MyApp/Services/OrderService.cs" → "MyApp.Services"). Omit or empty for non-C# projects.\n'
        'target_framework: (C# projects only) .NET target framework from the plan. Default "net8.0". Omit or empty for non-C# projects.'
    ),
}

# REQ-PLI-601: Language-aware dependency ordering guidance.
_PARSE_DEP_ORDERING_GUIDANCE: Dict[str, str] = {
    "go": (
        "\n## Go dependency ordering\n"
        "Order features so that shared libraries and proto definitions come before "
        "services that import them. Place go.mod before Dockerfile. "
        "Place main.go after utility packages it imports."
    ),
    "java": (
        "\n## Java dependency ordering\n"
        "Order features so that shared libraries and interfaces come before "
        "implementations. Place build.gradle before source files. "
        "Place configuration files (application.yml, application.properties) before "
        "application code that reads them. Place entity/model classes before "
        "repositories/services that use them."
    ),
    "nodejs": (
        "\n## Node.js dependency ordering\n"
        "Order features so that shared utility modules come before services. "
        "Place package.json before source files. "
        "Place configuration/environment files before application code."
    ),
    "csharp": (
        "\n## C# dependency ordering\n"
        "Order features so that shared libraries and interfaces come before "
        "implementations. Place .csproj before source files. "
        "Place model/entity classes before services that use them. "
        "Place configuration (appsettings.json) before application code."
    ),
}


# REQ-PLI-202: Pre-PARSE language detection from plan text.
_LANG_DETECT_SIGNALS: Dict[str, List[str]] = {
    "go": [
        "go.mod", "go.sum", ".go", "Go ", "Golang", "golang",
        "goroutine", "gRPC", "package main", "func main()",
    ],
    "java": [
        "build.gradle", "pom.xml", ".java", "Java ", "Spring Boot",
        "SpringBoot", "@SpringBootApplication", "JPA", "Maven", "Gradle",
        "jakarta.", "javax.", "public class", "public interface",
    ],
    "nodejs": [
        "package.json", ".js", ".ts", ".tsx", "Node.js", "Node ",
        "Express", "express", "React", "Next.js", "npm ", "yarn ",
        "require(", "module.exports",
    ],
    "python": [
        "requirements.txt", "pyproject.toml", ".py", "Python ",
        "pip ", "pytest", "django", "flask", "FastAPI",
    ],
    "csharp": [
        ".csproj", ".sln", ".cs", "C# ", "C#", ".NET", "dotnet",
        "ASP.NET", "Entity Framework", "namespace ", "using ",
        "NuGet", "Blazor", "MAUI",
    ],
}


def _detect_plan_language(plan_text: str) -> Optional[str]:
    """Detect the primary language of a plan from text signals (REQ-PLI-202).

    Scans plan text for language-specific keywords, file extensions, and
    framework mentions. Returns the dominant language or ``None`` when
    ambiguous (winner must score at least 2x the runner-up).

    Python is the default language, so it is never returned as a detection
    result — the hint is only useful for non-Python languages.
    """
    if not plan_text:
        return None

    scores: Dict[str, int] = {}
    plan_lower = plan_text.lower()
    for lang, signals in _LANG_DETECT_SIGNALS.items():
        count = 0
        for signal in signals:
            if not signal:
                continue  # R1: guard against empty signals
            # Case-sensitive signals (e.g. "Go ", "Java ") check original text
            if signal[0].isupper():
                count += plan_text.count(signal)
            else:
                count += plan_lower.count(signal)
        if count > 0:
            scores[lang] = count

    if not scores:
        return None

    # Require the winner to have at least 2x the runner-up score
    ranked = sorted(scores.items(), key=lambda x: -x[1])
    winner, winner_score = ranked[0]
    if len(ranked) >= 2:
        runner_up_score = ranked[1][1]
        if winner_score < 2 * runner_up_score:
            return None  # Ambiguous — don't guess
    return winner


def _build_parse_prompt(plan_text: str) -> str:
    """Build the PARSE prompt with language-specific extensions (REQ-PLI-201).

    Detects the plan's language and injects relevant schema fields and guidance.
    Always includes all language extensions (the LLM ignores irrelevant ones),
    but when a language is detected, adds a hint and dependency ordering guidance.
    """
    detected_lang = _detect_plan_language(plan_text)

    # Build language-specific schema fields and guidance — always include all
    _LANG_ORDER = ("go", "java", "nodejs", "csharp")
    lang_schema_lines = []
    lang_guidance_lines = []
    for lang in _LANG_ORDER:
        lang_schema_lines.append(_PARSE_LANG_SCHEMA[lang])
        lang_guidance_lines.append(_PARSE_LANG_GUIDANCE[lang])
    lang_schema_block = ",\n".join(lang_schema_lines)
    lang_guidance_block = "\n".join(lang_guidance_lines)

    # Language hint for the LLM (REQ-PLI-202)
    lang_hint = ""
    if detected_lang and detected_lang != "python":
        lang_hint = (
            f"\n**Detected language: {detected_lang}** — pay special attention to "
            f"{detected_lang}-specific fields in the schema below.\n"
        )

    # Dependency ordering guidance (REQ-PLI-601)
    dep_ordering = ""
    if detected_lang and detected_lang in _PARSE_DEP_ORDERING_GUIDANCE:
        dep_ordering = _PARSE_DEP_ORDERING_GUIDANCE[detected_lang]

    return _PARSE_PROMPT_TEMPLATE.format(
        plan_text=plan_text,
        lang_hint=lang_hint,
        lang_schema_fields=lang_schema_block,
        lang_guidance=lang_guidance_block,
        dep_ordering_guidance=dep_ordering,
    )


_PARSE_PROMPT_TEMPLATE = """\
You are an expert software architect. Analyze the following implementation plan \
and extract structured information.
{lang_hint}
<plan>
{plan_text}
</plan>

Return a JSON object wrapped in ```json code fences with exactly these keys:
{{
  "title": "string — plan title",
  "intent": "Why this plan exists — the problem being solved (1-2 sentences)",
  "scope_boundary": "What is explicitly OUT of scope or excluded from this plan",
  "approach": "High-level technical strategy (1-2 sentences)",
  "goals": ["string — each high-level goal"],
  "features": [
    {{
      "feature_id": "F-001",
      "name": "short name",
      "description": "what this feature does",
      "target_files": ["path/to/file.py"],
      "dependencies": ["F-002"],
      "estimated_loc": 100,
      "labels": ["label"],
      "mode": "create or edit",
      "design_doc_sections": ["optional task-specific design hints e.g. Parameter validation", "Error handling"],
      "artifact_types_addressed": ["optional artifact types e.g. servicemonitor", "prometheus_rule"],
      "api_signatures": ["Class MyClass(BaseClass)", "def my_function(arg: str) -> bool", "def MyService.serve(request, context) -> Response"],
      "protocol": "grpc or http or cli or library or none",
      "runtime_dependencies": ["grpcio==1.60.0", "flask>=3.0"],
      "negative_scope": ["things explicitly excluded from this feature"],
{lang_schema_fields}
    }}
  ],
  "mentioned_files": ["every file path mentioned in the plan"],
  "dependency_graph": {{"F-001": ["F-002"]}}
}}

## target_files guidance

Each feature becomes ONE implementation task sent to a code-generation LLM.
Multi-file tasks reliably fail — the LLM drops files or produces partial output.

Rules for target_files:
1. ALWAYS assign exactly ONE file per feature. If a change spans multiple
   files, create separate features with dependencies between them.
2. Do NOT create features targeting test `__init__.py` files
   (e.g. `tests/__init__.py`, `tests/unit/__init__.py`). Python 3 + pytest
   do not require them — they are wasted implementation slots.

mode: "create" for new files (plan says implement, add, new, create) or "edit" for modifying existing files (plan says update, modify, change, refactor, fix). Default to "create" if unclear.
design_doc_sections: optional list of content hints to emphasize in the design doc (e.g. parameter validation, error handling). Omit or empty if not applicable.
artifact_types_addressed: optional list of artifact types this feature generates (e.g. servicemonitor, prometheus_rule, dashboard). Omit or empty if not applicable.
api_signatures: list of class, function, and method signatures defined or implemented by this feature. Extract these from "Implementation contract", "API", "Interface", or signature sections in the plan. Use the format "Class ClassName(BaseClass)", "def function_name(param: type) -> return_type", or "def ClassName.method_name(param: type) -> return_type" (dotted notation for methods). For gRPC services, model RPC handlers as methods of their Servicer class (e.g. "def EmailService.SendOrderConfirmation(request, context)" not bare "def SendOrderConfirmation(request, context)"). Include ALL signatures mentioned for the feature.
protocol: transport protocol — one of "grpc", "http", "cli", "library", or "none". Infer from the plan (e.g. gRPC service → "grpc", Flask/REST → "http", CLI tool → "cli", utility module → "library").
runtime_dependencies: list of third-party packages with version constraints mentioned in the plan for this feature (e.g. "grpcio==1.60.0", "flask>=3.0"). Only include explicit dependencies, not stdlib.
negative_scope: list of things explicitly excluded or out-of-scope for this feature, if mentioned in the plan.
{lang_guidance}
{dep_ordering_guidance}
Be thorough. Extract every feature, file reference, and dependency.
"""

# Keep the old key for _fmt_prompt fallback compatibility — populated lazily
_FALLBACK_PROMPTS["parse"] = ""  # Replaced by _build_parse_prompt()

_FALLBACK_PROMPTS["assess"] = """\
You are a complexity assessor for software plans.

<plan_summary>
Title: {title}
Goals: {goals}
Feature count: {feature_count}
Features: {feature_summary}
Files mentioned: {file_count}
</plan_summary>

Score the plan on these 7 dimensions (each 0–100):
1. feature_count — number and granularity of features
2. cross_file_deps — how many features touch multiple files
3. api_surface — breadth of public API changes
4. test_complexity — difficulty of testing
5. integration_depth — how deeply it integrates with existing code
6. domain_novelty — how novel the domain concepts are
7. ambiguity — how ambiguous or under-specified the plan is

Then compute a composite score (weighted average, 0–100).

Routing rule: composite ≤ {threshold} → "prime", else → "artisan".

Return JSON wrapped in ```json code fences:
{{
  "feature_count": 0,
  "cross_file_deps": 0,
  "api_surface": 0,
  "test_complexity": 0,
  "integration_depth": 0,
  "domain_novelty": 0,
  "ambiguity": 0,
  "composite": 0,
  "reasoning": "one paragraph explaining the score and routing decision",
  "route": "prime or artisan"
}}
"""

_FALLBACK_PROMPTS["transform_prime"] = """\
You are a task YAML generator for the PrimeContractor workflow.

Convert the following parsed plan into a task YAML file matching this schema:

```yaml
project:
  id: <project-id>
  name: <project-name>
  sprint_id: <sprint-id>

tasks:
  - task_id: <ID>
    title: "short title"
    task_type: task
    story_points: <1-8>
    priority: <high|medium|low>
    labels: [label1, label2]
    depends_on: [<other-task-id>]
    config:
      task_description: |
        Detailed implementation instructions...
      context:
        existing_code: ""
```

<plan>
Title: {title}
Goals: {goals}
Features:
{features}
Dependency graph: {dependency_graph}
</plan>

Generate valid YAML. Use task IDs like PI-001, PI-002, etc.
Include dependency edges from the dependency graph.

Each task_description MUST be a multi-line block (5+ lines minimum) containing:
1. **Implementation steps** — numbered steps describing what to build
2. **Key function signatures** — the primary functions/methods with parameters and return types
3. **Code example** — a fenced code block showing the core API call, constructor, or pattern
4. **Error handling** — what errors to handle and how
5. **Negative scope** — "This task should NOT: ..." listing explicit exclusions

Do NOT produce single-line descriptions. A one-sentence summary is insufficient for code generation.
"""

_FALLBACK_PROMPTS["transform_artisan"] = """\
You are a plan document generator for the ArtisanContractor workflow.

Convert the following parsed plan into a structured markdown plan document.

The document must have these sections:
1. **Overview** — title, goals, scope
2. **Data Models** — key data structures
3. **Architecture** — component diagram, file layout
4. **Phase Breakdown** — implementation phases with deliverables
5. **Cost Model** — estimated token usage per phase
6. **Risk Register** — risks and mitigations
7. **Verification** — test strategy, acceptance criteria
8. **Dependencies** — external deps, inter-feature deps

<plan>
Title: {title}
Goals: {goals}
Features:
{features}
Mentioned files: {mentioned_files}
Dependency graph: {dependency_graph}
</plan>

Generate a complete, well-structured markdown document.
Use ## for top-level sections, ### for subsections.
"""


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_INPUT_TRUNCATION = 200   # Max chars of prompt stored in StepResult.input
_OUTPUT_TRUNCATION = 500  # Max chars of response stored in StepResult.output
# Matches simple (REQ-001) and multi-segment (REQ-PMS-001) requirement IDs.
_REQ_ID_PATTERN = re.compile(
    r"\b(?:REQ|FR|NFR|R)(?:[-_][A-Za-z0-9]+)+\b", re.IGNORECASE,
)

# Depth tier calibration — channel adaptation pattern
# (brief/standard/comprehensive map to feature complexity)
# Design docs can hit limits with multiple sections + code blocks + reviewer iterations.
# Claude 4.5 supports up to 64K output; these values avoid truncation (stop_reason=max_tokens).
DEPTH_TIERS: Dict[str, Dict[str, Any]] = {
    "brief": {
        "sections": ["Overview", "Architecture", "Testing Strategy"],
        "max_tokens": 4096,
        "guidance": (
            "Concise design sketch. Focus on the interface contract and "
            "key test cases. This is a small feature — avoid over-engineering."
        ),
    },
    "standard": {
        "sections": [
            "Overview", "Architecture", "Data Model",
            "Error Handling", "Testing Strategy",
        ],
        "max_tokens": 8192,
        "guidance": (
            "Standard design doc. Include data model and error handling "
            "but keep depth proportional to the feature's scope."
        ),
    },
    "comprehensive": {
        "sections": [
            "Overview", "Architecture", "Data Model",
            "API Contracts", "Error Handling",
            "Security Considerations", "Testing Strategy",
        ],
        "max_tokens": 16384,
        "guidance": (
            "Comprehensive design. All sections are warranted for this "
            "complex feature — address security and API contracts thoroughly."
        ),
    },
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Compat re-exports — preserve existing import paths (AC-R2).
# Follows the context_seed_handlers.py compat wrapper precedent.
# ---------------------------------------------------------------------------
from .plan_ingestion_parsing import (  # noqa: F401
    _extract_json_from_response,
    _extract_imports_from_existing,
    _as_bool,
    _safe_int,
    _HEURISTIC_FALLBACK_DESCRIPTION,
    _heuristic_parse_plan,
    _heuristic_assess_complexity,
    _heuristic_transform_content,
    _parse_context_files,
    _parse_file_list,
    _safe_json_load,
)
from .plan_ingestion_contracts import (  # noqa: F401
    _extract_implementation_contracts,
    _scope_contract_to_files,
    _path_matches_targets,
    _scope_by_service_bullets,
    _enrich_features_from_plan,
    _extract_requirement_ids,
    _load_requirements_documents,
    _normalize_requirements_hints,
)
from .plan_ingestion_mottainai import (  # noqa: F401
    _element_context_checksum,
    _mottainai_pre_assembly,
    _apply_pre_fill_to_skeletons,
)
from .plan_ingestion_emitter import PhaseEmitter  # noqa: F401  (AC-R4)


def _checksum_file(path: Path) -> Optional[str]:
    """Return SHA-256 checksum for file content, or None if unreadable."""
    try:
        return sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def _resolve_path(path_str: str, base_dir: Path) -> Path:
    """Resolve absolute or relative path against base directory."""
    p = Path(path_str).expanduser()
    if p.is_absolute():
        return p
    return (base_dir / p).resolve()


def _normalize_artifact_type(raw: str) -> str:
    """Normalize artifact type labels to underscore format."""
    return raw.strip().lower().replace("-", "_")


def _artifact_type_from_id(artifact_id: str) -> Optional[str]:
    """Derive artifact type from artifact ID suffix when possible."""
    aid = artifact_id.strip().lower()
    explicit_suffix_map = {
        "-dashboard": "dashboard",
        "_dashboard": "dashboard",
        "-loki-rules": "loki_rule",
        "_loki_rules": "loki_rule",
        "-notification": "notification_policy",
        "_notification": "notification_policy",
        "-prometheus-rules": "prometheus_rule",
        "_prometheus_rules": "prometheus_rule",
        "-runbook": "runbook",
        "_runbook": "runbook",
        "-service-monitor": "service_monitor",
        "_service_monitor": "service_monitor",
        "-slo": "slo_definition",
        "_slo": "slo_definition",
    }
    for suffix, artifact_type in explicit_suffix_map.items():
        if aid.endswith(suffix):
            return artifact_type
    # Unrecognized pattern — return None rather than guessing from
    # arbitrary ID structure (e.g., "api-gateway-v2" → "gateway_v2" is wrong).
    return None


def _artifact_target_from_id(artifact_id: str, artifact_type: str) -> Optional[str]:
    """Extract target slug from artifact id using known type suffix patterns."""
    aid = artifact_id.strip()
    type_patterns = {
        "dashboard": ["-dashboard", "_dashboard"],
        "loki_rule": ["-loki-rules", "_loki_rules"],
        "notification_policy": ["-notification", "_notification"],
        "prometheus_rule": ["-prometheus-rules", "_prometheus_rules"],
        "runbook": ["-runbook", "_runbook"],
        "service_monitor": ["-service-monitor", "_service_monitor"],
        "slo_definition": ["-slo", "_slo"],
    }
    for suffix in type_patterns.get(artifact_type, []):
        if aid.lower().endswith(suffix):
            raw_target = aid[: -len(suffix)]
            target = raw_target.replace("_", "-").strip("-_")
            return target or None
    return None


def _infer_artifact_types_from_files(files: List[str]) -> List[str]:
    """Infer artifact types from target file names (Mottainai Phase 2.2).

    Returns a deduplicated list of artifact type strings.  Only applies
    deterministic, zero-cost heuristics — no LLM involved.
    """
    types: list[str] = []
    seen: set[str] = set()
    for f in files:
        path_lower = f.lower()
        name = path_lower.rsplit("/", 1)[-1] if "/" in path_lower else path_lower
        inferred: Optional[str] = None
        if name.startswith("dockerfile") or name.endswith(".dockerfile"):
            inferred = "dockerfile"
        elif name in (
            "requirements.txt", "requirements.in", "go.mod", "go.sum",
            "package.json", "package-lock.json", "pyproject.toml",
            "setup.py", "setup.cfg", "Pipfile", "Pipfile.lock",
            "yarn.lock", "pnpm-lock.yaml", "Cargo.toml", "Cargo.lock",
            "pom.xml",
        ):
            inferred = "dependency_manifest"
        elif name.endswith(".csproj"):
            inferred = "dependency_manifest"
        elif name.endswith(".proto"):
            inferred = "proto_contract"
        elif any(name.endswith(ext) for ext in (
            ".py", ".go", ".js", ".ts", ".rs", ".java", ".rb", ".cs",
        )):
            inferred = "source_module"
        if inferred and inferred not in seen:
            types.append(inferred)
            seen.add(inferred)
    return types


def _infer_service_metadata(
    features: List[ParsedFeature],
    onboarding: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Infer service-level metadata from features and onboarding data.

    Extracts language-agnostic metadata (transport protocol, runtime
    dependencies, API surface, primary language) from ParsedFeature fields,
    then delegates to the resolved LanguageProfile's
    ``derive_service_metadata()`` for language-specific fields (e.g.
    Go module_path, Java java_package, Node.js module_system).

    Returns:
        Dict with keys: transport_protocol, runtime_dependencies,
        primary_language, api_signatures, negative_scope, plus
        language-specific keys from the profile.
    """
    _ext_map = LanguageRegistry.get_extension_map()

    protocols: list[str] = []
    all_runtime_deps: list[str] = []
    all_api_sigs: list[str] = []
    all_negative_scope: list[str] = []
    languages: list[str] = []

    for f in features:
        if f.protocol:
            protocols.append(f.protocol)
        all_runtime_deps.extend(f.runtime_dependencies)
        all_api_sigs.extend(f.api_signatures)
        all_negative_scope.extend(f.negative_scope)
        # Infer language from target files
        for tf in f.target_files:
            # Extract extension after last dot, or empty string if no dot
            ext = tf.rsplit(".", 1)[-1].lower() if "." in tf else ""
            lang = _ext_map.get("." + ext) if ext else None
            if lang and lang not in languages:
                languages.append(lang)

    # Determine dominant protocol
    transport = ""
    if protocols:
        transport = Counter(protocols).most_common(1)[0][0]
    elif onboarding:
        # REQ-GPC-600: guard against marker dicts in raw onboarding
        _raw_tp = onboarding.get("transport_protocol", "")
        transport = _raw_tp if isinstance(_raw_tp, str) else ""

    # Deduplicate
    runtime_deps = sorted(set(all_runtime_deps))
    api_sigs = list(dict.fromkeys(all_api_sigs))  # preserve order, dedup
    negative_scope = list(dict.fromkeys(all_negative_scope))

    metadata: Dict[str, Any] = {}
    if transport:
        metadata["transport_protocol"] = transport
    if runtime_deps:
        metadata["runtime_dependencies"] = runtime_deps
    if languages:
        metadata["primary_language"] = languages[0] if len(languages) == 1 else languages
    if api_sigs:
        metadata["api_signatures"] = api_sigs
    if negative_scope:
        metadata["negative_scope"] = negative_scope

    # Language-specific metadata derivation — delegate to LanguageProfile
    # (REQ-LA-201). Each profile's derive_service_metadata() handles
    # Go module_path/service_name, Java java_package/build_system,
    # Node.js module_system, etc.
    primary_lang = metadata.get("primary_language", "")
    lang_id = primary_lang if isinstance(primary_lang, str) else (
        primary_lang[0] if primary_lang else ""
    )
    profile = LanguageRegistry.get(lang_id)
    if profile is not None and hasattr(profile, "derive_service_metadata"):
        lang_metadata = profile.derive_service_metadata(
            features,
            onboarding=onboarding,
            api_signatures=api_sigs,
            runtime_dependencies=runtime_deps,
        )
        metadata.update(lang_metadata)

    return metadata


def _break_dependency_cycles(
    dep_graph: Dict[str, List[str]],
) -> List[tuple]:
    """Detect and break cycles in a dependency graph (OI-002).

    Uses iterative DFS to find back-edges, then removes them.
    Mutates *dep_graph* in place. Returns list of broken (src, dst) edges.
    """
    WHITE, GRAY, BLACK = 0, 1, 2
    color: Dict[str, int] = {n: WHITE for n in dep_graph}
    # Ensure all targets are in color map
    for deps in dep_graph.values():
        for d in deps:
            if d not in color:
                color[d] = WHITE
    broken: List[tuple] = []

    for start in list(dep_graph):
        if color[start] != WHITE:
            continue
        stack = [(start, 0)]
        while stack:
            node, idx = stack.pop()
            children = dep_graph.get(node, [])
            if idx == 0:
                color[node] = GRAY
            if idx < len(children):
                stack.append((node, idx + 1))
                child = children[idx]
                if color.get(child, WHITE) == GRAY:
                    # Back-edge → cycle. Remove it.
                    broken.append((node, child))
                    children.remove(child)
                    # Re-adjust index since list shrunk
                    stack[-1] = (node, idx)
                elif color.get(child, WHITE) == WHITE:
                    stack.append((child, 0))
            else:
                color[node] = BLACK
    return broken


def _derive_target_files_from_artifact_ids(
    artifact_ids: List[str],
    output_path_conventions: Dict[str, Any],
) -> List[str]:
    """Derive target file paths from artifact IDs and output templates."""
    targets: List[str] = []
    for artifact_id in artifact_ids:
        artifact_type = _artifact_type_from_id(artifact_id)
        if not artifact_type:
            continue
        template_entry = output_path_conventions.get(artifact_type)
        if not isinstance(template_entry, dict):
            continue
        output_template = template_entry.get("output_path")
        if not isinstance(output_template, str) or "{target}" not in output_template:
            continue
        target_slug = _artifact_target_from_id(artifact_id, artifact_type)
        if not target_slug:
            continue
        targets.append(output_template.replace("{target}", target_slug))
    return sorted(set(targets))


def _context_files_with_checksums(
    context_files: Optional[List[str]],
    base_dir: Optional[Path] = None,
) -> List[Dict[str, Any]]:
    """Build context_files list with optional checksums for seed/handoff.

    Args:
        context_files: List of file paths.
        base_dir: Base directory for resolving relative paths (default: cwd).

    Returns:
        List of {"path": str, "checksum": str | None} dicts.
    """
    if not context_files:
        return []
    import hashlib
    result: List[Dict[str, Any]] = []
    base = base_dir or Path.cwd()
    for p in context_files:
        entry: Dict[str, Any] = {"path": p}
        try:
            resolved = Path(p) if Path(p).is_absolute() else base / p
            if resolved.exists() and resolved.is_file():
                content = resolved.read_bytes()
                entry["checksum"] = hashlib.sha256(content).hexdigest()
            else:
                entry["checksum"] = None
        except (OSError, PermissionError):
            entry["checksum"] = None
        result.append(entry)
    return result





# ---------------------------------------------------------------------------
# Emit result type
# ---------------------------------------------------------------------------


class EmitResult(NamedTuple):
    """Typed return value from ``_phase_emit``."""
    config_path: Path
    review_config: dict
    context_seed_path: Optional[Path]
    tracking_result: Optional[Dict[str, Any]]
    tasks: List[Dict[str, Any]]
    enrichment_diagnostic: Optional[EnrichmentDiagnostic] = None


# ---------------------------------------------------------------------------
# Workflow
# ---------------------------------------------------------------------------

class PlanIngestionWorkflow(WorkflowBase):
    """
    Automates the pipeline: parse a generic plan → LLM-assess complexity →
    transform into SDK-native format → auto-refine via architectural review →
    emit the plan doc + review config JSON.
    """

    @property
    def metadata(self) -> WorkflowMetadata:
        return WorkflowMetadata(
            workflow_id="plan-ingestion",
            name="Plan Ingestion Workflow",
            description=(
                "Parse a generic implementation plan, assess its complexity, "
                "transform it into PrimeContractor task YAML or ArtisanContractor "
                "plan markdown, refine via architectural review rounds, and emit "
                "a review-config.json."
            ),
            version="1.0.0",
            capabilities=[
                "plan-transformation",
                "complexity-assessment",
                "document-generation",
            ],
            tags=["plan", "ingestion", "prime", "artisan"],
            requires_agents=False,
            agent_count=AgentCount.NONE,
            min_agents=0,
            max_agents=None,
            inputs=[
                WorkflowInput(
                    name="plan_path",
                    type="file",
                    required=True,
                    description="Path to the input plan markdown file",
                ),
                WorkflowInput(
                    name="output_dir",
                    type="string",
                    required=False,
                    default=".",
                    description="Directory to write output files",
                ),
                WorkflowInput(
                    name="assessor_agent",
                    type="agent_spec",
                    required=False,
                    description="Agent spec for parse + assess phases (default: balanced tier)",
                ),
                WorkflowInput(
                    name="transformer_agent",
                    type="agent_spec",
                    required=False,
                    description="Agent spec for transformation phase (default: balanced tier)",
                ),
                WorkflowInput(
                    name="review_rounds",
                    type="number",
                    required=False,
                    default=2,
                    description="Number of architectural review rounds (0 = skip refinement)",
                ),
                WorkflowInput(
                    name="skip_arc_review",
                    type="boolean",
                    required=False,
                    default=False,
                    description="Skip the architectural review workflow in the REFINE phase",
                ),
                WorkflowInput(
                    name="review_quality_tier",
                    type="string",
                    required=False,
                    default="flagship",
                    description="Quality tier for review agents",
                ),
                WorkflowInput(
                    name="complexity_threshold",
                    type="number",
                    required=False,
                    default=40,
                    description="Complexity score threshold: ≤ threshold → Prime, > threshold → Artisan",
                ),
                WorkflowInput(
                    name="force_route",
                    type="string",
                    required=False,
                    description="Force routing to 'prime' or 'artisan' (bypasses assessment)",
                ),
                WorkflowInput(
                    name="context_files",
                    type="text",
                    required=False,
                    description="Comma-separated file paths for review context",
                ),
                WorkflowInput(
                    name="contextcore_export_dir",
                    type="string",
                    required=False,
                    description="Directory containing ContextCore export artifacts (onboarding-metadata.json, manifest, CRD)",
                ),
                WorkflowInput(
                    name="requirements_path",
                    type="file",
                    required=False,
                    description="Path to the primary requirements document used for traceability checks",
                ),
                WorkflowInput(
                    name="requirements_files",
                    type="text",
                    required=False,
                    description="Comma-separated requirements file paths for dual-document refine and coverage analysis",
                ),
                WorkflowInput(
                    name="min_export_coverage",
                    type="number",
                    required=False,
                    default=0,
                    description="Minimum export coverage percent required in preflight (0-100)",
                ),
                WorkflowInput(
                    name="low_quality_policy",
                    type="string",
                    required=False,
                    default="bias_artisan",
                    description="Action when translation quality is low: bias_artisan or fail",
                ),
                WorkflowInput(
                    name="min_requirements_coverage",
                    type="number",
                    required=False,
                    default=70,
                    description="Minimum requirement mapping coverage percent before low-quality policy applies",
                ),
                WorkflowInput(
                    name="min_artifact_mapping_coverage",
                    type="number",
                    required=False,
                    default=70,
                    description="Minimum artifact mapping completeness percent before low-quality policy applies",
                ),
                WorkflowInput(
                    name="max_contract_conflicts",
                    type="number",
                    required=False,
                    default=2,
                    description="Maximum allowed unresolved mapping conflicts before low-quality policy applies",
                ),
                WorkflowInput(
                    name="scope",
                    type="string",
                    required=False,
                    description="Review scope statement",
                ),
                WorkflowInput(
                    name="warn_cost_usd",
                    type="number",
                    required=False,
                    description="Cost warning threshold in USD",
                ),
                WorkflowInput(
                    name="max_cost_usd",
                    type="number",
                    required=False,
                    description="Cost hard limit in USD — workflow fails if exceeded",
                ),
                WorkflowInput(
                    name="project_root",
                    type="string",
                    required=False,
                    description="Target project root directory (used for .contextcore.yaml auto-discovery)",
                ),
                WorkflowInput(
                    name="contextcore_yaml",
                    type="file",
                    required=False,
                    description="Explicit path to .contextcore.yaml (overrides auto-discovery)",
                ),
                WorkflowInput(
                    name="llm_read_timeout_seconds",
                    type="number",
                    required=False,
                    default=300,
                    description="LLM HTTP read timeout in seconds",
                ),
                WorkflowInput(
                    name="llm_max_attempts",
                    type="number",
                    required=False,
                    default=1,
                    description="Maximum LLM call attempts (including initial request)",
                ),
                WorkflowInput(
                    name="enable_heuristic_parse_fallback",
                    type="boolean",
                    required=False,
                    default=True,
                    description="Fallback to deterministic parse/assess/transform when LLM output is invalid",
                ),
                WorkflowInput(
                    name="force_regenerate",
                    type="boolean",
                    required=False,
                    default=False,
                    description="Exclude target files from SOURCE_RECONCILE AST parsing (INV-12). "
                    "Prevents prior-run output from inflating the ForwardManifest.",
                ),
                WorkflowInput(
                    name="kaizen",
                    type="boolean",
                    required=False,
                    default=False,
                    description="Enable Kaizen prompt capture — writes full prompts and responses to kaizen-prompts/",
                ),
                WorkflowInput(
                    name="kaizen_config_path",
                    type="file",
                    required=False,
                    description="Path to Kaizen config JSON with prompt suffixes and threshold overrides",
                ),
            ],
        )

    def _custom_validate(self, config: Dict[str, Any]) -> List[str]:
        errors: List[str] = []
        plan_path = config.get("plan_path")
        if plan_path:
            p = Path(str(plan_path)).expanduser()
            if not p.exists() or not p.is_file():
                errors.append(f"plan_path does not exist or is not a file: {p}")

        force_route = config.get("force_route")
        if force_route and force_route not in ("prime", "artisan"):
            errors.append(f"force_route must be 'prime' or 'artisan', got '{force_route}'")

        low_quality_policy = str(
            config.get("low_quality_policy", "bias_artisan")
        ).strip().lower()
        if low_quality_policy not in {"bias_artisan", "fail"}:
            errors.append(
                "low_quality_policy must be 'bias_artisan' or 'fail'"
            )

        for key in (
            "min_export_coverage",
            "min_requirements_coverage",
            "min_artifact_mapping_coverage",
        ):
            val = config.get(key)
            if val is None:
                continue
            try:
                fval = float(val)
            except (TypeError, ValueError):
                errors.append(f"{key} must be a number between 0 and 100")
                continue
            if fval < 0 or fval > 100:
                errors.append(f"{key} must be between 0 and 100")

        for path_key in ("requirements_path", "contextcore_export_dir"):
            raw = config.get(path_key)
            if not raw:
                continue
            p = Path(str(raw)).expanduser()
            if path_key == "requirements_path" and (not p.exists() or not p.is_file()):
                errors.append(f"{path_key} does not exist or is not a file: {p}")
            if path_key == "contextcore_export_dir" and (not p.exists() or not p.is_dir()):
                errors.append(f"{path_key} does not exist or is not a directory: {p}")

        timeout_raw = config.get("llm_read_timeout_seconds")
        if timeout_raw is not None:
            try:
                timeout_val = float(timeout_raw)
            except (TypeError, ValueError):
                errors.append("llm_read_timeout_seconds must be a positive number")
            else:
                if timeout_val <= 0:
                    errors.append("llm_read_timeout_seconds must be > 0")

        attempts_raw = config.get("llm_max_attempts")
        if attempts_raw is not None:
            try:
                attempts_val = int(float(attempts_raw))
            except (TypeError, ValueError):
                errors.append("llm_max_attempts must be an integer >= 1")
            else:
                if attempts_val < 1:
                    errors.append("llm_max_attempts must be >= 1")

        return errors

    # ------------------------------------------------------------------
    # Agent resolution
    # ------------------------------------------------------------------

    def _resolve_assessor_agent(
        self,
        config: Dict[str, Any],
        timeout_config: Optional[TimeoutConfig] = None,
        retry_config: Optional[RetryConfig] = None,
    ) -> BaseAgent:
        spec = config.get("assessor_agent") or Models.CLAUDE_SONNET_LATEST
        return resolve_agent_spec(
            str(spec),
            name="plan-assessor",
            timeout_config=timeout_config,
            retry_config=retry_config,
        )

    def _resolve_transformer_agent(
        self,
        config: Dict[str, Any],
        timeout_config: Optional[TimeoutConfig] = None,
        retry_config: Optional[RetryConfig] = None,
    ) -> BaseAgent:
        spec = config.get("transformer_agent") or Models.CLAUDE_SONNET_LATEST
        agent = resolve_agent_spec(
            str(spec),
            name="plan-transformer",
            timeout_config=timeout_config,
            retry_config=retry_config,
        )
        # Transform phase generates large YAML/markdown; bump token limit
        if hasattr(agent, "max_tokens") and agent.max_tokens < 64000:
            try:
                agent.max_tokens = 64000
            except (AttributeError, TypeError, ValueError) as exc:
                logger.debug(
                    "Could not set max_tokens on %s: %s",
                    type(agent).__name__, exc,
                )
        return agent

    # ------------------------------------------------------------------
    # Phase: PARSE
    # ------------------------------------------------------------------

    def _phase_parse(
        self, plan_text: str, agent: BaseAgent
    ) -> Tuple[Optional[ParsedPlan], StepResult]:
        t0 = time.time()
        prompt = _build_parse_prompt(plan_text)
        if getattr(self, "_kaizen_config", None) and self._kaizen_config.parse_prompt_suffix:
            prompt += self._kaizen_config.parse_prompt_suffix

        _llm_ctx = _tracer.start_as_current_span("llm.plan_ingestion.parse")
        _llm_span = _llm_ctx.__enter__()
        try:
            response_text, time_ms, token_usage = agent.generate(prompt)
        except Exception as exc:
            if _HAS_OTEL and not isinstance(_llm_span, _NoOpSpan):
                _llm_span.record_exception(exc)
                _llm_span.set_status(_StatusCode.ERROR, str(exc))
            _llm_ctx.__exit__(None, None, None)
            elapsed_ms = int((time.time() - t0) * 1000)
            return None, StepResult(
                step_name="parse",
                agent_name=agent.name,
                input=prompt[:_INPUT_TRUNCATION],
                output="",
                time_ms=elapsed_ms,
                error=f"Parse LLM call failed: {exc}",
            )
        elapsed_ms = int((time.time() - t0) * 1000)

        in_tok = token_usage_input(token_usage) if token_usage else 0
        out_tok = token_usage_output(token_usage) if token_usage else 0
        cost = token_usage_cost(token_usage) if token_usage else 0.0

        if _HAS_OTEL and not isinstance(_llm_span, _NoOpSpan):
            _llm_span.set_attribute("llm.response_time_ms", time_ms)
            _llm_span.set_attribute("llm.tokens_input", in_tok)
            _llm_span.set_attribute("llm.tokens_output", out_tok)
            _llm_span.set_attribute("llm.cost_usd", cost)
        _llm_ctx.__exit__(None, None, None)

        if getattr(self, "_kaizen_capture", False):
            persist_prompt_response(self._kaizen_output_dir, "parse", prompt, response_text)

        try:
            data = _extract_json_from_response(response_text)
        except (json.JSONDecodeError, ValueError) as exc:
            return None, StepResult(
                step_name="parse",
                agent_name=agent.name,
                input=prompt[:_INPUT_TRUNCATION],
                output=response_text[:_OUTPUT_TRUNCATION],
                time_ms=elapsed_ms,
                input_tokens=in_tok,
                output_tokens=out_tok,
                cost=cost,
                error=f"Failed to parse JSON from LLM response: {exc}",
            )

        features = []
        for f in data.get("features", []):
            features.append(ParsedFeature(
                feature_id=f.get("feature_id", ""),
                name=f.get("name", ""),
                description=f.get("description", ""),
                target_files=f.get("target_files", []),
                dependencies=f.get("dependencies", []),
                estimated_loc=f.get("estimated_loc", 0),
                labels=f.get("labels", []),
                design_doc_sections=f.get("design_doc_sections", []),
                artifact_types_addressed=f.get("artifact_types_addressed", []),
                api_signatures=f.get("api_signatures", []),
                protocol=f.get("protocol", ""),
                runtime_dependencies=f.get("runtime_dependencies", []),
                negative_scope=f.get("negative_scope", []),
                mode=f.get("mode", "create"),
                module_path=f.get("module_path", ""),
                service_name=f.get("service_name", ""),
                java_package=f.get("java_package", ""),
                build_system=f.get("build_system", ""),
                java_version=f.get("java_version", ""),
                spring_boot=bool(f.get("spring_boot", False)),
                module_system=f.get("module_system", ""),
                node_version=f.get("node_version", ""),
                csharp_namespace=f.get("csharp_namespace", ""),
                target_framework=f.get("target_framework", ""),
            ))

        parsed = ParsedPlan(
            title=data.get("title", "Untitled Plan"),
            goals=data.get("goals", []),
            features=features,
            dependency_graph=data.get("dependency_graph", {}),
            mentioned_files=data.get("mentioned_files", []),
            raw_text=plan_text,
            intent=data.get("intent", ""),
            scope_boundary=data.get("scope_boundary", ""),
            approach=data.get("approach", ""),
            input_tokens=in_tok,
            output_tokens=out_tok,
            cost=cost,
        )

        _code_fallback = "```" not in response_text
        step = StepResult(
            step_name="parse",
            agent_name=agent.name,
            input=prompt[:_INPUT_TRUNCATION],
            output=response_text[:_OUTPUT_TRUNCATION],
            time_ms=elapsed_ms,
            input_tokens=in_tok,
            output_tokens=out_tok,
            cost=cost,
            metadata={"code_extraction_fallback": _code_fallback},
        )

        return parsed, step

    # ------------------------------------------------------------------
    # Phase: ASSESS
    # ------------------------------------------------------------------

    def _phase_assess(
        self,
        parsed_plan: ParsedPlan,
        agent: BaseAgent,
        threshold: int,
        force_route: Optional[str],
    ) -> Tuple[Optional[ComplexityScore], StepResult]:
        t0 = time.time()

        # Build feature summary for the ASSESS prompt.
        # Flag multi-file features so the complexity scorer can account
        # for split risk in its cross_file_deps dimension.
        _feat_lines = []
        multi_file_count = 0
        for f in parsed_plan.features:
            has_init = any(
                tf.endswith("__init__.py") for tf in f.target_files
            )
            suffix = ""
            if len(f.target_files) > 1:
                multi_file_count += 1
                suffix = " ⚠ MULTI-FILE"
                if has_init:
                    suffix += "+__init__.py"
            _feat_lines.append(
                f"  - {f.feature_id}: {f.name} "
                f"(files: {len(f.target_files)}, "
                f"deps: {len(f.dependencies)}){suffix}"
            )
        feature_summary = "\n".join(_feat_lines)
        if multi_file_count:
            feature_summary += (
                f"\n\n  NOTE: {multi_file_count} feature(s) target multiple "
                f"files. Multi-file tasks have higher implementation risk — "
                f"factor this into cross_file_deps scoring."
            )

        prompt = _fmt_prompt(
            "assess",
            title=parsed_plan.title,
            goals=", ".join(parsed_plan.goals),
            feature_count=len(parsed_plan.features),
            feature_summary=feature_summary,
            file_count=len(parsed_plan.mentioned_files),
            threshold=threshold,
        )
        if getattr(self, "_kaizen_config", None) and self._kaizen_config.assess_prompt_suffix:
            prompt += self._kaizen_config.assess_prompt_suffix

        _llm_ctx = _tracer.start_as_current_span("llm.plan_ingestion.assess")
        _llm_span = _llm_ctx.__enter__()
        try:
            response_text, time_ms, token_usage = agent.generate(prompt)
        except Exception as exc:
            if _HAS_OTEL and not isinstance(_llm_span, _NoOpSpan):
                _llm_span.record_exception(exc)
                _llm_span.set_status(_StatusCode.ERROR, str(exc))
            _llm_ctx.__exit__(None, None, None)
            elapsed_ms = int((time.time() - t0) * 1000)
            return None, StepResult(
                step_name="assess",
                agent_name=agent.name,
                input=prompt[:_INPUT_TRUNCATION],
                output="",
                time_ms=elapsed_ms,
                error=f"Assess LLM call failed: {exc}",
            )
        elapsed_ms = int((time.time() - t0) * 1000)

        in_tok = token_usage_input(token_usage) if token_usage else 0
        out_tok = token_usage_output(token_usage) if token_usage else 0
        cost = token_usage_cost(token_usage) if token_usage else 0.0

        if _HAS_OTEL and not isinstance(_llm_span, _NoOpSpan):
            _llm_span.set_attribute("llm.response_time_ms", time_ms)
            _llm_span.set_attribute("llm.tokens_input", in_tok)
            _llm_span.set_attribute("llm.tokens_output", out_tok)
            _llm_span.set_attribute("llm.cost_usd", cost)
        _llm_ctx.__exit__(None, None, None)

        if getattr(self, "_kaizen_capture", False):
            persist_prompt_response(self._kaizen_output_dir, "assess", prompt, response_text)

        try:
            data = _extract_json_from_response(response_text)
        except (json.JSONDecodeError, ValueError) as exc:
            return None, StepResult(
                step_name="assess",
                agent_name=agent.name,
                input=prompt[:_INPUT_TRUNCATION],
                output=response_text[:_OUTPUT_TRUNCATION],
                time_ms=elapsed_ms,
                input_tokens=in_tok,
                output_tokens=out_tok,
                cost=cost,
                error=f"Failed to parse assessment JSON: {exc}",
            )

        # Composite score retained for quality telemetry (Kaizen seed
        # fitness scoring). Route is always PRIME (REQ-SU-102).
        composite = _safe_int(data.get("composite"), 50)
        route = ContractorRoute.PRIME

        score = ComplexityScore(
            feature_count=_safe_int(data.get("feature_count"), 0),
            cross_file_deps=_safe_int(data.get("cross_file_deps"), 0),
            api_surface=_safe_int(data.get("api_surface"), 0),
            test_complexity=_safe_int(data.get("test_complexity"), 0),
            integration_depth=_safe_int(data.get("integration_depth"), 0),
            domain_novelty=_safe_int(data.get("domain_novelty"), 0),
            ambiguity=_safe_int(data.get("ambiguity"), 0),
            composite=composite,
            reasoning=data.get("reasoning", ""),
            route=route,
            input_tokens=in_tok,
            output_tokens=out_tok,
            cost=cost,
        )

        _code_fallback = "```" not in response_text
        step = StepResult(
            step_name="assess",
            agent_name=agent.name,
            input=prompt[:_INPUT_TRUNCATION],
            output=response_text[:_OUTPUT_TRUNCATION],
            time_ms=elapsed_ms,
            input_tokens=in_tok,
            output_tokens=out_tok,
            cost=cost,
            metadata={"code_extraction_fallback": _code_fallback},
        )

        return score, step

    # ------------------------------------------------------------------
    # Phase: TRANSFORM
    # ------------------------------------------------------------------

    def _phase_transform(
        self,
        parsed_plan: ParsedPlan,
        route: ContractorRoute,
        agent: BaseAgent,
        output_dir: Path,
    ) -> Tuple[Optional[Path], StepResult]:
        t0 = time.time()

        features_text = "\n".join(
            f"  - {f.feature_id}: {f.name}\n"
            f"    Description: {f.description}\n"
            f"    Files: {', '.join(f.target_files)}\n"
            f"    Dependencies: {', '.join(f.dependencies)}\n"
            f"    Estimated LOC: {f.estimated_loc}"
            for f in parsed_plan.features
        )

        prompt = _fmt_prompt(
            "transform_prime",
            title=parsed_plan.title,
            goals=", ".join(parsed_plan.goals),
            features=features_text,
            dependency_graph=json.dumps(parsed_plan.dependency_graph),
        )
        out_filename = "plan-ingestion-tasks.yaml"

        # Import guidance: downstream code generators benefit from explicit
        # import requirements in task descriptions.  This default suffix is
        # always appended; kaizen overrides may extend it further.
        prompt += (
            "\n\nIMPORTANT — for each task, include an `imports` field listing "
            "the specific Python imports (standard library, third-party, and "
            "intra-project) that the implementation will need.  Use fully-"
            "qualified module paths (e.g. `from pathlib import Path`, "
            "`import typing`).  This enables the code generator to produce "
            "correct import blocks without guessing."
        )

        if getattr(self, "_kaizen_config", None) and self._kaizen_config.transform_prompt_suffix:
            prompt += self._kaizen_config.transform_prompt_suffix

        _llm_ctx = _tracer.start_as_current_span("llm.plan_ingestion.transform")
        _llm_span = _llm_ctx.__enter__()
        try:
            response_text, time_ms, token_usage = agent.generate(prompt)
        except Exception as exc:
            if _HAS_OTEL and not isinstance(_llm_span, _NoOpSpan):
                _llm_span.record_exception(exc)
                _llm_span.set_status(_StatusCode.ERROR, str(exc))
            _llm_ctx.__exit__(None, None, None)
            elapsed_ms = int((time.time() - t0) * 1000)
            return None, StepResult(
                step_name="transform",
                agent_name=agent.name,
                input=prompt[:_INPUT_TRUNCATION],
                output="",
                time_ms=elapsed_ms,
                error=f"Transform LLM call failed: {exc}",
            )
        elapsed_ms = int((time.time() - t0) * 1000)

        in_tok = token_usage_input(token_usage) if token_usage else 0
        out_tok = token_usage_output(token_usage) if token_usage else 0
        cost = token_usage_cost(token_usage) if token_usage else 0.0

        if _HAS_OTEL and not isinstance(_llm_span, _NoOpSpan):
            _llm_span.set_attribute("llm.response_time_ms", time_ms)
            _llm_span.set_attribute("llm.tokens_input", in_tok)
            _llm_span.set_attribute("llm.tokens_output", out_tok)
            _llm_span.set_attribute("llm.cost_usd", cost)
        _llm_ctx.__exit__(None, None, None)

        if getattr(self, "_kaizen_capture", False):
            persist_prompt_response(self._kaizen_output_dir, "transform", prompt, response_text)

        # Extract content from potential code fences
        content = extract_code_from_response(
            response_text,
            language="yaml" if route == ContractorRoute.PRIME else "markdown",
        )

        # Validate output
        _md_quality_warning = None
        if route == ContractorRoute.PRIME:
            try:
                yaml.safe_load(content)
            except yaml.YAMLError as exc:
                return None, StepResult(
                    step_name="transform",
                    agent_name=agent.name,
                    input=prompt[:_INPUT_TRUNCATION],
                    output=content[:_OUTPUT_TRUNCATION],
                    time_ms=elapsed_ms,
                    input_tokens=in_tok,
                    output_tokens=out_tok,
                    cost=cost,
                    error=f"Generated YAML is invalid: {exc}",
                )
        else:
            # Markdown: check for at least one heading
            if not re.search(r'^#{1,6}\s', content, re.MULTILINE):
                _md_quality_warning = "Generated markdown has no headings — may be low quality"
                logger.warning(_md_quality_warning)

        # Write output
        output_dir.mkdir(parents=True, exist_ok=True)
        out_path = output_dir / out_filename
        atomic_write(out_path, content)

        _code_fallback = "```" not in response_text
        _output_msg = f"Wrote {out_path}"
        if _md_quality_warning:
            _output_msg += f" [warning: {_md_quality_warning}]"
        step = StepResult(
            step_name="transform",
            agent_name=agent.name,
            input=prompt[:_INPUT_TRUNCATION],
            output=_output_msg,
            time_ms=elapsed_ms,
            input_tokens=in_tok,
            output_tokens=out_tok,
            cost=cost,
            metadata={"code_extraction_fallback": _code_fallback},
        )

        return out_path, step

    # ------------------------------------------------------------------
    # Preflight / quality helpers
    # ------------------------------------------------------------------

    def _preflight_export_contract(
        self,
        contextcore_export_dir: Optional[str],
        context_files: Optional[List[str]],
        output_dir: Path,
        min_export_coverage: float,
        contextcore_yaml_path: Optional[Path] = None,
    ) -> Tuple[Optional[Dict[str, Any]], Dict[str, Any], List[str], List[str]]:
        """Validate ContextCore export artifacts before PARSE."""
        warnings: List[str] = []
        errors: List[str] = []
        evidence: Dict[str, Any] = {"checksums": {}, "paths": {}, "coverage": {}}

        onboarding_path: Optional[Path] = None
        if contextcore_export_dir:
            export_dir = _resolve_path(contextcore_export_dir, output_dir)
            onboarding_path = export_dir / "onboarding-metadata.json"
            if not onboarding_path.exists():
                errors.append(
                    f"Preflight: missing onboarding-metadata.json in contextcore_export_dir: {export_dir}"
                )
                return None, evidence, warnings, errors
        elif context_files:
            for raw in context_files:
                p = _resolve_path(raw, output_dir)
                if p.name == "onboarding-metadata.json":
                    onboarding_path = p
                    break

        if onboarding_path is None:
            warnings.append(
                "Preflight: onboarding metadata not provided; skipping export contract checks"
            )
            return None, evidence, warnings, errors
        if not onboarding_path.exists():
            errors.append(f"Preflight: onboarding metadata not found: {onboarding_path}")
            return None, evidence, warnings, errors

        onboarding = _safe_json_load(onboarding_path)
        if onboarding is None:
            errors.append(f"Preflight: onboarding metadata is invalid JSON: {onboarding_path}")
            return None, evidence, warnings, errors

        evidence["paths"]["onboarding_metadata"] = str(onboarding_path)
        base_dir = onboarding_path.parent

        # REQ-GPC-300/301: detect and log generation profile
        generation_profile = onboarding.get("generation_profile", "full")
        logger.info("Preflight: detected generation_profile=%s", generation_profile)
        evidence["generation_profile"] = generation_profile

        amp = onboarding.get("artifact_manifest_path")
        pcp = onboarding.get("project_context_path")
        if not isinstance(amp, str):
            errors.append("Preflight: onboarding missing artifact_manifest_path")
        if not isinstance(pcp, str):
            errors.append("Preflight: onboarding missing project_context_path")
        if errors:
            return onboarding, evidence, warnings, errors

        artifact_manifest_path = _resolve_path(amp, base_dir)
        project_context_path = _resolve_path(pcp, base_dir)
        evidence["paths"]["artifact_manifest"] = str(artifact_manifest_path)
        evidence["paths"]["project_context"] = str(project_context_path)

        if not artifact_manifest_path.exists():
            errors.append(f"Preflight: expected artifact manifest missing: {artifact_manifest_path}")
        if not project_context_path.exists():
            errors.append(f"Preflight: expected project context missing: {project_context_path}")
        if errors:
            return onboarding, evidence, warnings, errors

        # Check checksum integrity when checksums are present.
        expected_manifest_checksum = onboarding.get("artifact_manifest_checksum")
        expected_project_checksum = onboarding.get("project_context_checksum")
        actual_manifest_checksum = _checksum_file(artifact_manifest_path)
        actual_project_checksum = _checksum_file(project_context_path)
        evidence["checksums"]["artifact_manifest_actual"] = actual_manifest_checksum
        evidence["checksums"]["project_context_actual"] = actual_project_checksum

        if isinstance(expected_manifest_checksum, str):
            evidence["checksums"]["artifact_manifest_expected"] = expected_manifest_checksum
            if actual_manifest_checksum != expected_manifest_checksum:
                errors.append(
                    "Preflight: artifact_manifest_checksum mismatch between onboarding and artifact manifest"
                )
        if isinstance(expected_project_checksum, str):
            evidence["checksums"]["project_context_expected"] = expected_project_checksum
            if actual_project_checksum != expected_project_checksum:
                errors.append(
                    "Preflight: project_context_checksum mismatch between onboarding and project context"
                )

        # Parameter source resolvability summary guardrail.
        # REQ-GPC-300: skip for profiles that intentionally omit these fields
        if generation_profile in _RESOLVABILITY_PROFILES:
            _rap = onboarding.get("resolved_artifact_parameters")
            _pr = onboarding.get("parameter_resolvability")
            has_resolvability_summary = (
                (isinstance(_rap, dict) and not is_omitted(_rap))
                or (isinstance(_pr, dict) and not is_omitted(_pr))
            )
            if not has_resolvability_summary:
                errors.append(
                    "Preflight: onboarding lacks parameter resolvability summary "
                    "(expected resolved_artifact_parameters or parameter_resolvability)"
                )

        coverage = onboarding.get("coverage")
        if not isinstance(coverage, dict):
            errors.append("Preflight: onboarding missing coverage block")
            return onboarding, evidence, warnings, errors
        evidence["coverage"] = coverage

        gaps = coverage.get("gaps")
        if not isinstance(gaps, list):
            errors.append("Preflight: coverage.gaps must be present as a list")

        overall = coverage.get("overallCoverage", coverage.get("overall_coverage"))
        try:
            overall_pct = float(overall) if overall is not None else 0.0
        except (TypeError, ValueError):
            overall_pct = 0.0
        evidence["coverage"]["overall_coverage_evaluated"] = overall_pct

        if overall_pct < min_export_coverage:
            errors.append(
                f"Preflight: export coverage {overall_pct:.1f}% below minimum {min_export_coverage:.1f}%"
            )

        # source_checksum verification against .contextcore.yaml
        expected_source_checksum = onboarding.get("source_checksum")
        if not isinstance(expected_source_checksum, str):
            warnings.append("Preflight: source_checksum missing in onboarding metadata")
            evidence["checksums"]["source_checksum_verified"] = None
        elif contextcore_yaml_path is None:
            warnings.append(
                "Preflight: .contextcore.yaml not available for verification"
            )
            evidence["checksums"]["source_checksum_verified"] = None
        elif not contextcore_yaml_path.exists():
            warnings.append(
                "Preflight: .contextcore.yaml not available for verification"
            )
            evidence["checksums"]["source_checksum_verified"] = None
        else:
            actual_checksum = _checksum_file(contextcore_yaml_path)
            evidence["checksums"]["source_checksum_expected"] = expected_source_checksum
            evidence["checksums"]["source_checksum_actual"] = actual_checksum
            evidence["paths"]["contextcore_yaml"] = str(contextcore_yaml_path)
            if actual_checksum == expected_source_checksum:
                evidence["checksums"]["source_checksum_verified"] = True
            else:
                evidence["checksums"]["source_checksum_verified"] = False
                errors.append(
                    f"Preflight: source_checksum mismatch "
                    f"(expected={expected_source_checksum}, actual={actual_checksum})"
                )

        return onboarding, evidence, warnings, errors

    @staticmethod
    def _evaluate_translation_quality(
        parsed_plan: ParsedPlan,
        requirements_docs: Dict[str, str],
        onboarding: Optional[Dict[str, Any]],
        requirements_hints: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Compute translation-quality metrics used for routing safeguards."""
        requirement_hints = requirements_hints or {}
        # Always extract IDs from requirements docs AND merge with hints —
        # hints may only contain pipeline-innate IDs, missing plan-specific
        # ones like REQ-PMS-*.  (Bug fix: hints were treated as exhaustive.)
        hint_ids = set(requirement_hints.keys())
        requirements_corpus = "\n\n".join(requirements_docs.values())
        extracted_ids = set(_extract_requirement_ids(requirements_corpus))
        requirement_ids = sorted(hint_ids | extracted_ids)

        # ── Classify pipeline-innate vs project-specific requirements ──
        pipeline_innate_ids: List[str] = []
        project_specific_ids: List[str] = []
        for rid in requirement_ids:
            hint = requirement_hints.get(rid, {})
            labels = hint.get("labels", [])
            if isinstance(labels, list) and "pipeline-innate" in labels:
                pipeline_innate_ids.append(rid)
            else:
                project_specific_ids.append(rid)

        req_to_feature: Dict[str, List[str]] = {}

        # Auto-satisfy pipeline-innate requirements with synthetic mapping
        for rid in pipeline_innate_ids:
            hint = requirement_hints.get(rid, {})
            artifact_type = hint.get("satisfied_by_artifact", "artifact")
            req_to_feature[rid] = [f"__pipeline_artifact:{artifact_type}"]

        # Match project-specific requirements against plan text.
        # Strategy 1: search parsed feature fields (id, name, description).
        # Strategy 2 (fallback): search the raw plan text for co-occurrence of
        # the requirement ID and feature IDs — catches traceability tables like
        # "| REQ-PMS-001 | F-002 |" and "**Satisfies:** REQ-PMS-001" lines that
        # PARSE strips from feature descriptions.
        feature_ids_set = {f.feature_id for f in parsed_plan.features}
        raw_text = getattr(parsed_plan, "raw_text", "") or ""

        for rid in project_specific_ids:
            rid_pattern = re.compile(r'\b' + re.escape(rid) + r'\b', re.IGNORECASE)
            # Strategy 1: feature field search
            matched_features = [
                f.feature_id for f in parsed_plan.features
                if rid_pattern.search(f"{f.feature_id} {f.name} {f.description}")
            ]
            # Strategy 2: raw plan text proximity search
            if not matched_features and raw_text:
                for m in rid_pattern.finditer(raw_text):
                    # Look in a ±500 char window around the requirement mention
                    start = max(0, m.start() - 500)
                    end = min(len(raw_text), m.end() + 500)
                    window = raw_text[start:end]
                    for fid in feature_ids_set:
                        if re.search(r'\b' + re.escape(fid) + r'\b', window):
                            matched_features.append(fid)
                matched_features = sorted(set(matched_features))
            req_to_feature[rid] = matched_features

        req_acceptance: Dict[str, List[str]] = {}
        req_sources: Dict[str, List[str]] = {}
        for rid in requirement_ids:
            hint = requirement_hints.get(rid, {})
            anchors = hint.get("acceptance_anchors", [])
            if isinstance(anchors, list):
                req_acceptance[rid] = [a for a in anchors if isinstance(a, str)]
            else:
                req_acceptance[rid] = []
            src_refs = hint.get("source_references", [])
            if isinstance(src_refs, list):
                req_sources[rid] = [s for s in src_refs if isinstance(s, str)]
            else:
                req_sources[rid] = []

        # Coverage computed from project-specific requirements only
        mapped_project_specific = sum(
            1 for rid in project_specific_ids if req_to_feature.get(rid)
        )
        total_project_specific = len(project_specific_ids)
        requirements_coverage = (
            (mapped_project_specific / total_project_specific) * 100.0
            if total_project_specific
            else 100.0
        )

        coverage = onboarding.get("coverage", {}) if isinstance(onboarding, dict) else {}
        gaps = coverage.get("gaps", []) if isinstance(coverage, dict) else []
        # Filter to entries that look like artifact IDs (not plain-text gap descriptions).
        # Artifact IDs contain hyphens/underscores and no spaces; prose descriptions have spaces
        # or are single bare words without structural separators.
        artifact_ids = [
            a for a in gaps
            if isinstance(a, str) and a.strip() and " " not in a.strip()
            and ("-" in a or "_" in a)
            and re.match(r'^[a-zA-Z][\w-]{2,}$', a.strip())
        ]
        artifact_to_feature: Dict[str, List[str]] = {}

        for aid in artifact_ids:
            expected_type = _artifact_type_from_id(aid)
            matched: List[str] = []
            for feat in parsed_plan.features:
                feat_types = {_normalize_artifact_type(t) for t in feat.artifact_types_addressed}
                if expected_type and expected_type in feat_types:
                    matched.append(feat.feature_id)
                elif aid.lower() in f"{feat.feature_id} {feat.name} {feat.description}".lower():
                    matched.append(feat.feature_id)
            artifact_to_feature[aid] = sorted(set(matched))

        mapped_artifacts = sum(1 for fids in artifact_to_feature.values() if fids)
        total_artifacts = len(artifact_ids)
        artifact_completeness = (
            (mapped_artifacts / total_artifacts) * 100.0
            if total_artifacts
            else 100.0
        )

        # Only project-specific requirements count toward unmet/conflict
        unmet_requirements = [
            rid for rid in project_specific_ids
            if not req_to_feature.get(rid)
        ]
        unmet_artifacts = [aid for aid, fids in artifact_to_feature.items() if not fids]
        conflict_count = len(unmet_requirements) + len(unmet_artifacts)

        return {
            "requirements_total": len(requirement_ids),
            "requirements_mapped": mapped_project_specific + len(pipeline_innate_ids),
            "requirements_project_specific_total": total_project_specific,
            "requirements_pipeline_innate_total": len(pipeline_innate_ids),
            "requirements_coverage_percent": round(requirements_coverage, 2),
            "artifact_total": total_artifacts,
            "artifact_mapped": mapped_artifacts,
            "artifact_mapping_percent": round(artifact_completeness, 2),
            "conflict_count": conflict_count,
            "unmet_requirement_count": len(unmet_requirements),
            "unmet_artifact_count": len(unmet_artifacts),
            "unmapped_requirements": unmet_requirements,
            "unmapped_artifacts": unmet_artifacts,
            "requirement_to_feature": req_to_feature,
            "artifact_to_feature": artifact_to_feature,
            "requirement_acceptance_anchors": req_acceptance,
            "requirement_source_references": req_sources,
        }

    @staticmethod
    def _build_traceability_artifact(
        route: ContractorRoute,
        parsed_plan: ParsedPlan,
        tasks: List[Dict[str, Any]],
        quality: Dict[str, Any],
        checksum_evidence: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Build deterministic traceability artifact payload."""
        feature_to_task: Dict[str, List[str]] = {}
        for t in tasks:
            ctx = t.get("config", {}).get("context", {})
            fid = ctx.get("feature_id")
            if not isinstance(fid, str) or not fid:
                continue
            feature_to_task.setdefault(fid, []).append(t.get("task_id", ""))

        req_mappings: List[Dict[str, Any]] = []
        for rid, fids in quality.get("requirement_to_feature", {}).items():
            # Detect pipeline-innate entries by __pipeline_artifact: prefix
            is_auto = any(
                isinstance(f, str) and f.startswith("__pipeline_artifact:")
                for f in fids
            )
            if is_auto:
                req_mappings.append(
                    {
                        "requirement_id": rid,
                        "feature_ids": fids,
                        "task_ids": [],
                        "status": "auto-satisfied",
                        "acceptance_obligations": quality.get(
                            "requirement_acceptance_anchors", {}
                        ).get(rid, []),
                        "source_references": quality.get(
                            "requirement_source_references", {}
                        ).get(rid, []),
                        "mapping_rationale": [
                            "pipeline-innate: satisfied by artifact generation"
                        ],
                    }
                )
            else:
                task_ids: List[str] = []
                for fid in fids:
                    task_ids.extend(feature_to_task.get(fid, []))
                req_mappings.append(
                    {
                        "requirement_id": rid,
                        "feature_ids": fids,
                        "task_ids": sorted(set(tid for tid in task_ids if tid)),
                        "status": "mapped" if fids else "unresolved",
                        "acceptance_obligations": quality.get(
                            "requirement_acceptance_anchors", {}
                        ).get(rid, []),
                        "source_references": quality.get(
                            "requirement_source_references", {}
                        ).get(rid, []),
                        "mapping_rationale": (
                            ["matched by requirement hint id against parsed feature text"]
                            if fids
                            else ["no parsed feature contained requirement identifier"]
                        ),
                    }
                )

        artifact_mappings: List[Dict[str, Any]] = []
        for aid, fids in quality.get("artifact_to_feature", {}).items():
            task_ids: List[str] = []
            for fid in fids:
                task_ids.extend(feature_to_task.get(fid, []))
            artifact_mappings.append(
                {
                    "artifact_id": aid,
                    "artifact_type": _artifact_type_from_id(aid),
                    "feature_ids": fids,
                    "task_ids": sorted(set(tid for tid in task_ids if tid)),
                    "status": "mapped" if fids else "unresolved",
                }
            )

        unresolved: List[Dict[str, Any]] = []
        for rid in quality.get("unmapped_requirements", []):
            unresolved.append(
                {
                    "type": "requirement",
                    "id": rid,
                    "severity": "high",
                    "message": "No plan feature/task mapping found",
                }
            )
        for aid in quality.get("unmapped_artifacts", []):
            unresolved.append(
                {
                    "type": "artifact",
                    "id": aid,
                    "severity": "medium",
                    "message": "No plan feature/task mapping found",
                }
            )

        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "route": route.value,
            "plan_title": parsed_plan.title,
            "requirement_mappings": req_mappings,
            "artifact_mappings": artifact_mappings,
            "unresolved": unresolved,
            "translation_quality": {
                "requirements_coverage_percent": quality.get("requirements_coverage_percent", 100.0),
                "artifact_mapping_percent": quality.get("artifact_mapping_percent", 100.0),
                "conflict_count": quality.get("conflict_count", 0),
            },
            "checksum_evidence": checksum_evidence,
        }

    @staticmethod
    def _write_traceability_artifact(output_dir: Path, payload: Dict[str, Any]) -> Path:
        """Write ingestion-traceability.json and return the path."""
        output_dir.mkdir(parents=True, exist_ok=True)
        path = output_dir / "ingestion-traceability.json"
        atomic_write_json(path, payload, indent=2)
        return path

    @staticmethod
    def _write_preflight_report(
        output_dir: Path,
        *,
        passed: bool,
        evidence: Dict[str, Any],
        warnings: List[str],
        errors: List[str],
    ) -> Path:
        """Write preflight-report.json and return the path."""
        from datetime import datetime, timezone

        output_dir.mkdir(parents=True, exist_ok=True)
        path = output_dir / "preflight-report.json"
        payload = {
            "passed": passed,
            "source_checksum_verified": evidence.get("checksums", {}).get(
                "source_checksum_verified"
            ),
            "evidence": evidence,
            "warnings": warnings,
            "errors": errors,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
        atomic_write_json(path, payload, indent=2)
        return path

    # ------------------------------------------------------------------
    # Phase: REFINE
    # ------------------------------------------------------------------

    def _phase_refine(
        self,
        doc_path: Path,
        review_rounds: int,
        review_quality_tier: str,
        scope: Optional[str],
        context_files: Optional[List[str]],
        feature_requirements: Optional[List[str]],
        warn_cost_usd: Optional[float],
        max_cost_usd: Optional[float],
        enable_apply: Optional[bool] = None,
        enable_prompt_caching: Optional[bool] = None,
        enable_triage: Optional[bool] = None,
        providers: Optional[List[str]] = None,
        custom_review_profile: Optional[Dict[str, Any]] = None,
    ) -> Tuple[int, List[StepResult], float, Dict[str, Any]]:
        if review_rounds <= 0:
            return 0, [], 0.0, {}

        # Local import to avoid circular dependencies
        from .architectural_review_log_workflow import ArchitecturalReviewLogWorkflow

        review_wf = ArchitecturalReviewLogWorkflow()
        review_config: Dict[str, Any] = {
            "document_path": str(doc_path),
            "quality_tier": review_quality_tier,
            # Arc-review maps 1 agent = 1 round; reviewer_count controls round count.
            # Cap at 5 (arc-review's validated max).
            "reviewer_count": min(review_rounds, 5),
            "max_suggestions": 10,
            "init_if_missing": True,
        }
        if custom_review_profile:
            review_config["custom_review_profile"] = custom_review_profile
        if providers:
            review_config["providers"] = providers
        if scope:
            review_config["scope"] = scope
        if context_files:
            review_config["context_files"] = context_files
        if feature_requirements:
            review_config["feature_requirements"] = feature_requirements
        if warn_cost_usd is not None:
            review_config["warn_cost_usd"] = warn_cost_usd
        if max_cost_usd is not None:
            review_config["max_cost_usd"] = max_cost_usd
        if enable_apply is not None:
            review_config["enable_apply"] = enable_apply
        if enable_prompt_caching is not None:
            review_config["enable_prompt_caching"] = enable_prompt_caching
        if enable_triage is not None:
            review_config["enable_triage"] = enable_triage

        with _tracer.start_as_current_span("ingestion.refine.review") as _review_span:
            result = review_wf.run(review_config)

        review_cost = result.metrics.total_cost if result.metrics else 0.0
        rounds_completed = (
            result.output.get("rounds_completed", len(result.steps))
            if isinstance(result.output, dict) else len(result.steps)
        )

        refine_steps = []
        for s in result.steps:
            refine_steps.append(StepResult(
                step_name=f"refine:{s.step_name}",
                agent_name=s.agent_name,
                input=s.input,
                output=s.output,
                time_ms=s.time_ms,
                input_tokens=s.input_tokens,
                output_tokens=s.output_tokens,
                cost=s.cost,
                error=s.error,
            ))

        if not result.success and result.error:
            refine_steps.append(StepResult(
                step_name="refine:error",
                error=result.error,
            ))

        review_output = result.output or {}
        return rounds_completed, refine_steps, review_cost, review_output

    # ------------------------------------------------------------------
    # Artisan context seed helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_refine_suggestions_for_seed(
        review_output: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """Extract accepted triage suggestions for seed injection."""
        triage = review_output.get("triage")
        if not triage or not isinstance(triage, dict):
            return []

        decisions = triage.get("decisions", [])
        if not decisions:
            # Fallback: return aggregate summary when decisions not available
            accepted = _safe_int(triage.get("accepted"), 0)
            if accepted == 0:
                return []
            return [{
                "decision": "ACCEPT",
                "source": "triage_summary",
                "triage_accepted_count": accepted,
                "triage_rejected_count": triage.get("rejected", 0),
                "substantially_addressed_areas": triage.get(
                    "substantially_addressed_areas", [],
                ),
                "areas_needing_review": triage.get("areas_needing_review", []),
            }]

        # Return individual ACCEPT decisions with full detail
        return [
            {
                "id": d.get("id", ""),
                "decision": d.get("decision", ""),
                "rationale": d.get("rationale", ""),
                "area": d.get("area", ""),
                "severity": d.get("severity", ""),
            }
            for d in decisions
            if d.get("decision") == "ACCEPT"
        ]

    @staticmethod
    def _estimate_story_points(estimated_loc: int) -> int:
        """Map estimated LOC to story points."""
        if estimated_loc <= 20:
            return 1
        if estimated_loc <= 50:
            return 2
        if estimated_loc <= 100:
            return 3
        if estimated_loc <= 200:
            return 5
        return 8

    @staticmethod
    def _is_trivial_test_init(file_path: str) -> bool:
        """Return True if *file_path* is a ``__init__.py`` inside a test directory.

        Python 3 + pytest do not require ``tests/__init__.py`` (or
        ``tests/unit/__init__.py``, etc.).  These files are wasted
        implementation slots when generated by the pipeline.
        """
        if not file_path.endswith("__init__.py"):
            return False
        parts = file_path.replace("\\", "/").split("/")
        return any(p in ("tests", "test") for p in parts[:-1])

    @staticmethod
    def _derive_tasks_from_features(
        features: List[ParsedFeature],
        dependency_graph: Dict[str, List[str]],
        requirement_to_feature: Optional[Dict[str, List[str]]] = None,
        artifact_to_feature: Optional[Dict[str, List[str]]] = None,
        requirement_hints: Optional[Dict[str, Dict[str, Any]]] = None,
        output_path_conventions: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Convert ParsedFeatures into task dicts matching prime-route schema.

        Args:
            features: Parsed features from the PARSE phase.
            dependency_graph: Feature dependency graph.
        """
        # Build a mapping from feature_id to task_id
        fid_to_tid: Dict[str, str] = {}
        for idx, feat in enumerate(features, start=1):
            fid_to_tid[feat.feature_id] = f"PI-{idx:03d}"

        feature_to_requirements: Dict[str, List[str]] = {}
        for rid, fids in (requirement_to_feature or {}).items():
            if not isinstance(rid, str):
                continue
            if not isinstance(fids, list):
                continue
            for fid in fids:
                if not isinstance(fid, str):
                    continue
                feature_to_requirements.setdefault(fid, []).append(rid)
        for fid in feature_to_requirements:
            feature_to_requirements[fid] = sorted(set(feature_to_requirements[fid]))

        feature_to_artifacts: Dict[str, List[str]] = {}
        for aid, fids in (artifact_to_feature or {}).items():
            if not isinstance(aid, str):
                continue
            if not isinstance(fids, list):
                continue
            for fid in fids:
                if not isinstance(fid, str):
                    continue
                feature_to_artifacts.setdefault(fid, []).append(aid)
        for fid in feature_to_artifacts:
            feature_to_artifacts[fid] = sorted(set(feature_to_artifacts[fid]))

        tasks: List[Dict[str, Any]] = []
        for idx, feat in enumerate(features, start=1):
            tid = fid_to_tid[feat.feature_id]
            sp = PlanIngestionWorkflow._estimate_story_points(feat.estimated_loc)

            # Resolve dependency feature IDs → task IDs
            deps = []
            for dep_fid in feat.dependencies:
                dep_tid = fid_to_tid.get(dep_fid)
                if dep_tid:
                    deps.append(dep_tid)

            # Also include edges from the dependency graph
            for dep_fid in dependency_graph.get(feat.feature_id, []):
                dep_tid = fid_to_tid.get(dep_fid)
                if dep_tid and dep_tid not in deps:
                    deps.append(dep_tid)

            # Priority: features with more dependents are higher priority
            # (they block more downstream work).
            dependent_count = sum(
                1 for f in features
                if feat.feature_id in dependency_graph.get(f.feature_id, [])
                or feat.feature_id in f.dependencies
            )
            if dependent_count >= 2:
                priority = "high"
            elif dependent_count == 1:
                priority = "medium"
            else:
                priority = "low"

            # ── Normalize target_files ordering ────────────────────────
            # __init__.py first: it's the package root that other files
            # import from.  Consistent ordering improves LLM output format
            # compliance and matches the MULTI_FILE_OUTPUT_FORMAT contract
            # in lead_contractor_workflow.py.
            mapped_artifacts = feature_to_artifacts.get(feat.feature_id, [])
            resolved_target_files = list(feat.target_files)
            if (
                not resolved_target_files
                and mapped_artifacts
                and isinstance(output_path_conventions, dict)
            ):
                resolved_target_files = _derive_target_files_from_artifact_ids(
                    mapped_artifacts,
                    output_path_conventions,
                )

            # ── Strip trivial test __init__.py files ──────────────────
            # Python 3 + pytest don't require them; they are wasted slots.
            pre_filter_count = len(resolved_target_files)
            resolved_target_files = [
                f for f in resolved_target_files
                if not PlanIngestionWorkflow._is_trivial_test_init(f)
            ]
            if not resolved_target_files and pre_filter_count > 0:
                logger.info(
                    "Skipping feature %s (%s): all target files are trivial "
                    "test __init__.py",
                    feat.feature_id,
                    feat.name,
                )
                continue

            ordered_files = sorted(
                resolved_target_files,
                key=lambda f: (0 if f.endswith("__init__.py") else 1, f),
            )

            ctx: Dict[str, Any] = {
                "feature_id": feat.feature_id,
                "target_files": ordered_files,
                "estimated_loc": feat.estimated_loc,
            }
            # QP-1: Declarative context threading — every field in
            # _CONTEXT_THREADABLE_FIELDS is forwarded from PARSE into the
            # task context automatically.  Adding a new PARSE field to the
            # frozenset is all that's needed; no manual ``if`` block required.
            for _field_name in _CONTEXT_THREADABLE_FIELDS:
                _val = getattr(feat, _field_name, None)
                if _val:
                    ctx[_field_name] = (
                        list(_val) if isinstance(_val, (list, tuple, set, frozenset))
                        else _val
                    )

            # Anzen: tag security-sensitive tasks at ingestion time so the
            # seed file is self-describing and prime_contractor gets
            # security_sensitive + detected_database in gen_context.
            if "security_sensitive" not in ctx:
                try:
                    from startd8.security_prime.enrichment import enrich_security_fields
                    _sec = enrich_security_fields(
                        feat.description or "", ordered_files,
                        getattr(feat, "metadata", None),
                    )
                    if _sec["security_sensitive"]:
                        ctx["security_sensitive"] = True
                        ctx["detected_database"] = _sec["detected_database"]
                except ImportError:
                    pass  # security_prime not available

            # Mottainai Phase 2.2: infer artifact types from target file
            # patterns when the PARSE phase didn't produce them, so
            # downstream injections keyed on artifact_types have something
            # to match against.
            if "artifact_types_addressed" not in ctx and ordered_files:
                inferred = _infer_artifact_types_from_files(ordered_files)
                if inferred:
                    ctx["artifact_types_addressed"] = inferred

            mapped_requirements = feature_to_requirements.get(feat.feature_id, [])
            if mapped_requirements:
                ctx["requirement_ids"] = mapped_requirements
                acceptance_obligations: List[str] = []
                source_references: List[str] = []
                for rid in mapped_requirements:
                    hint = (requirement_hints or {}).get(rid, {})
                    anchors = hint.get("acceptance_anchors", [])
                    if isinstance(anchors, list):
                        acceptance_obligations.extend(
                            a for a in anchors if isinstance(a, str)
                        )
                    refs = hint.get("source_references", [])
                    if isinstance(refs, list):
                        source_references.extend(
                            r for r in refs if isinstance(r, str)
                        )
                if acceptance_obligations:
                    ctx["acceptance_obligations"] = sorted(set(acceptance_obligations))
                if source_references:
                    ctx["source_references"] = sorted(set(source_references))

                # REQ-QPI-200/201: Sanitize acceptance anchors + negative_scope
                # when a database surface is detected. Runs AFTER threadable
                # field propagation (line 2543) to catch both feature-level
                # and anchor-level anti-patterns.
                if ctx.get("detected_database") and (
                    ctx.get("acceptance_obligations") or ctx.get("negative_scope")
                ):
                    try:
                        from startd8.workflows.builtin.plan_ingestion_anchor_sanitizer import (
                            sanitize_acceptance_obligations,
                            strip_conflicting_negative_scope,
                        )
                        _db = ctx["detected_database"]
                        _lang = _infer_language_from_files(ordered_files)
                        if ctx.get("acceptance_obligations"):
                            ctx["acceptance_obligations"], _anch_audit = (
                                sanitize_acceptance_obligations(
                                    ctx["acceptance_obligations"], _db, _lang,
                                )
                            )
                            if _anch_audit:
                                ctx["replaced_anchors"] = _anch_audit
                        if ctx.get("negative_scope"):
                            ctx["negative_scope"], _stripped = (
                                strip_conflicting_negative_scope(
                                    ctx["negative_scope"], _db,
                                )
                            )
                            if _stripped:
                                ctx.setdefault("replaced_anchors", []).extend(
                                    {"original": s, "reason": "negative_scope_conflict"}
                                    for s in _stripped
                                )
                    except ImportError:
                        logger.debug("Anchor sanitizer not available (plan_ingestion_anchor_sanitizer)")

                rationale: List[str] = [
                    "feature selected via requirement identifier match"
                ]
                if mapped_artifacts:
                    rationale.append(
                        "feature also mapped to coverage gaps: "
                        + ", ".join(mapped_artifacts)
                    )
                ctx["mapping_rationale"] = rationale

            # REQ-QPI-201: Sanitize negative_scope for SQL anti-patterns.
            # This runs OUTSIDE the mapped_requirements block because
            # negative_scope comes from _CONTEXT_THREADABLE_FIELDS (line 2543),
            # not from acceptance anchors. Tasks without mapped requirements
            # still need their negative_scope cleaned.
            if ctx.get("detected_database") and ctx.get("negative_scope"):
                try:
                    from startd8.workflows.builtin.plan_ingestion_anchor_sanitizer import (
                        strip_conflicting_negative_scope,
                    )
                    ctx["negative_scope"], _stripped = (
                        strip_conflicting_negative_scope(
                            ctx["negative_scope"], ctx["detected_database"],
                        )
                    )
                    if _stripped:
                        ctx.setdefault("replaced_anchors", []).extend(
                            {"original": s, "reason": "negative_scope_conflict"}
                            for s in _stripped
                        )
                except ImportError:
                    pass

            # REQ-PD-003: Build requirements_text from description +
            # acceptance_obligations + source_references so DESIGN has
            # authoritative parameter details without re-deriving.
            _req_parts: List[str] = []
            if feat.description:
                _req_parts.append(feat.description)
            if ctx.get("acceptance_obligations"):
                _req_parts.append(
                    "Acceptance criteria:\n"
                    + "\n".join(f"- {a}" for a in ctx["acceptance_obligations"])
                )
            if ctx.get("source_references"):
                _req_parts.append(
                    "Source references:\n"
                    + "\n".join(f"- {r}" for r in ctx["source_references"])
                )
            _requirements_text = "\n\n".join(_req_parts)
            # Avoid duplicating task_description when no additional
            # acceptance/source context was appended.
            if _requirements_text == feat.description:
                _requirements_text = ""
            elif len(_requirements_text) > 2000:
                _requirements_text = _requirements_text[:2000] + " [truncated]"

            tasks.append({
                "task_id": tid,
                "title": feat.name,
                "task_type": "task",
                "story_points": sp,
                "priority": priority,
                "labels": list(feat.labels),
                "depends_on": deps,
                "config": {
                    "task_description": feat.description,
                    "requirements_text": _requirements_text,
                    "context": ctx,
                },
            })

            # REQ-QPI-203: Sanitize task_description for SQL anti-patterns.
            # Done after task assembly because feat may be frozen.
            if ctx.get("detected_database") and tasks:
                try:
                    from startd8.workflows.builtin.plan_ingestion_anchor_sanitizer import (
                        sanitize_task_description,
                    )
                    _task = tasks[-1]
                    _orig_desc = _task["config"]["task_description"]
                    if _orig_desc:
                        _lang = _infer_language_from_files(ordered_files)
                        _clean_desc, _desc_audit = sanitize_task_description(
                            _orig_desc, ctx["detected_database"], _lang,
                        )
                        if _clean_desc != _orig_desc:
                            _task["config"]["task_description"] = _clean_desc
                            ctx.setdefault("replaced_anchors", []).extend(_desc_audit)
                except ImportError:
                    pass

        # ── Clean up dangling dependency references from skipped features ──
        emitted_ids = {t["task_id"] for t in tasks}
        for t in tasks:
            original_deps = t.get("depends_on", [])
            cleaned_deps = [d for d in original_deps if d in emitted_ids]
            if len(cleaned_deps) < len(original_deps):
                dangling = set(original_deps) - emitted_ids
                logger.warning(
                    "Task %s: removed %d dangling dependency reference(s): %s",
                    t["task_id"], len(dangling), sorted(dangling),
                )
                t["depends_on"] = cleaned_deps

        # ── Gate 2a: single-file enforcement ─────────────────────────
        # Per defense-in-depth Principle 2 (adversarial thinking): even if
        # the PARSE prompt says "one file per feature," the LLM may ignore
        # it.  Structurally split any multi-file tasks so downstream
        # phases always receive single-file work items.
        tasks = PlanIngestionWorkflow._split_oversized_tasks(
            tasks, max_files=1,
        )

        # ── Validate task IDs against safe pattern ──────────────────
        for t in tasks:
            tid = t.get("task_id", "")
            if not _SAFE_TASK_ID_PATTERN.match(tid):
                logger.warning(
                    "Task ID %r does not match safe pattern — may cause "
                    "checkpoint path issues downstream",
                    tid,
                )

        # ── Gate 2b: filter trivial test __init__.py after split ─────
        # A multi-file feature like ["tests/__init__.py", "tests/test_auth.py"]
        # becomes two sub-tasks after Gate 2a.  Filter the __init__.py one.
        tasks = PlanIngestionWorkflow._filter_trivial_test_init_tasks(tasks)

        # ── Gate 2c: deduplicate tasks by normalized target file ────────
        # The LLM may emit the same file with different path formats
        # (e.g., "Program.cs" and "src/cartservice/src/Program.cs").
        # Gate 2a splits both into sub-tasks, creating duplicates.
        # Dedup by filename (basename), keeping the longer (more specific) path.
        tasks = PlanIngestionWorkflow._dedup_tasks_by_target_file(tasks)

        if not tasks and features:
            logger.warning(
                "Zero tasks derived from %d features — all features may have been "
                "filtered (trivial __init__.py, empty target_files). "
                "Downstream seed will contain no work items.",
                len(features),
            )

        return tasks

    @staticmethod
    def _split_oversized_tasks(
        tasks: List[Dict[str, Any]],
        max_files: int = 1,
    ) -> List[Dict[str, Any]]:
        """Gate 2a: Split tasks with more than *max_files* target files.

        Default is ``max_files=1`` (single-file enforcement).  The PARSE
        prompt instructs the LLM to emit one file per feature, but this
        gate structurally enforces it (defense-in-depth Principle 2:
        treat upstream as potentially adversarial).

        Each multi-file task is replaced by single-file sub-tasks:
        - ``__init__.py`` (if present) becomes the first sub-task so
          other sub-tasks can depend on it.
        - Sub-tasks are lettered (PI-001a, PI-001b, …) for traceability.
        - Estimated LOC is divided proportionally.

        Single-file tasks (≤ *max_files*) pass through unchanged.
        """
        result: List[Dict[str, Any]] = []

        for task in tasks:
            ctx = task.get("config", {}).get("context", {})
            target_files = ctx.get("target_files", [])

            if len(target_files) <= max_files:
                result.append(task)
                continue

            # This task needs splitting.
            parent_id = task["task_id"]
            parent_deps = list(task.get("depends_on", []))
            parent_desc = task.get("config", {}).get("task_description", "")
            estimated_loc = ctx.get("estimated_loc", 0)
            loc_per_file = max(estimated_loc // len(target_files), 10)

            # Cap sub-tasks at 26 (a-z) to stay within
            # _SAFE_TASK_ID_PATTERN.  Extra files are grouped into the
            # last sub-task.
            _MAX_SUB_TASKS = 26

            # Separate __init__.py (if any) — it becomes sub-task 'a'
            # so other sub-tasks can depend on it.
            init_files = [f for f in target_files if f.endswith("__init__.py")]
            non_init_files = [f for f in target_files if not f.endswith("__init__.py")]
            ordered = init_files + non_init_files

            if len(ordered) > _MAX_SUB_TASKS:
                logger.warning(
                    "Gate 2a: task %s has %d files — capping at %d "
                    "sub-tasks; last sub-task will contain %d files",
                    parent_id,
                    len(ordered),
                    _MAX_SUB_TASKS,
                    len(ordered) - _MAX_SUB_TASKS + 1,
                )

            # Build groups: first _MAX_SUB_TASKS groups each get one file;
            # additional files accumulate in the last group.
            groups: List[List[str]] = []
            for f in ordered:
                if len(groups) < _MAX_SUB_TASKS:
                    groups.append([f])
                else:
                    groups[-1].append(f)

            num_sub = len(groups)

            logger.info(
                "Gate 2a: splitting task %s (%d files > max %d) into %d "
                "sub-tasks",
                parent_id,
                len(target_files),
                max_files,
                num_sub,
            )

            # Pre-compute init sub-task ID for dependency wiring
            # (before the loop so it is available on the first
            # non-init iteration).
            init_sub_id: Optional[str] = None
            for pre_idx, pre_group in enumerate(groups):
                if any(gf.endswith("__init__.py") for gf in pre_group):
                    pre_suffix = chr(ord("a") + pre_idx)
                    init_sub_id = f"{parent_id}{pre_suffix}"
                    break

            for idx, file_group in enumerate(groups):
                suffix = chr(ord("a") + idx)
                sub_id = f"{parent_id}{suffix}"

                # Sub-task deps: parent's deps + init sub-task (if this
                # isn't the init sub-task itself).
                sub_deps = list(parent_deps)
                if init_sub_id and sub_id != init_sub_id:
                    sub_deps.append(init_sub_id)

                group_loc = loc_per_file * len(file_group)

                sub_ctx: Dict[str, Any] = {
                    "feature_id": ctx.get("feature_id", ""),
                    "target_files": file_group,
                    "estimated_loc": group_loc,
                    "_split_from": parent_id,
                    "_split_index": idx,
                }
                # Carry forward optional context fields
                for key in (
                    "design_doc_sections",
                    "artifact_types_addressed",
                    "requirement_ids",
                    "acceptance_obligations",
                    "source_references",
                    "mapping_rationale",
                ):
                    if key in ctx:
                        sub_ctx[key] = ctx[key]

                if len(file_group) == 1:
                    file_name = file_group[0].rsplit("/", 1)[-1]
                    sub_title = f"{task['title']} — {file_name}"
                    desc_detail = f"implement `{file_group[0]}` only."
                else:
                    sub_title = (
                        f"{task['title']} — {len(file_group)} files "
                        f"(group {suffix})"
                    )
                    file_list = ", ".join(
                        f"`{gf}`" for gf in file_group
                    )
                    desc_detail = (
                        f"implement {len(file_group)} files: "
                        f"{file_list}."
                    )

                result.append({
                    "task_id": sub_id,
                    "title": sub_title,
                    "task_type": task.get("task_type", "task"),
                    "story_points": PlanIngestionWorkflow._estimate_story_points(
                        group_loc
                    ),
                    "priority": task.get("priority", "medium"),
                    "labels": list(task.get("labels", [])),
                    "depends_on": sub_deps,
                    "config": {
                        "task_description": (
                            f"{parent_desc}\n\n"
                            f"[Auto-split from {parent_id}: {desc_detail}]"
                        ),
                        "requirements_text": task.get("config", {}).get("requirements_text", ""),
                        "context": sub_ctx,
                    },
                })

        return result

    @staticmethod
    def _filter_trivial_test_init_tasks(
        tasks: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Gate 2b: Remove tasks whose sole target file is a test ``__init__.py``.

        After Gate 2a splits multi-file features into single-file sub-tasks,
        some sub-tasks may target ``tests/__init__.py`` or similar.  These are
        wasted implementation slots (Python 3 + pytest don't require them).

        Dangling dependency references to filtered task IDs are cleaned up so
        downstream wave/lane assignment sees a consistent graph.
        """
        filtered_ids: set[str] = set()
        result: List[Dict[str, Any]] = []
        for task in tasks:
            tf = task.get("config", {}).get("context", {}).get("target_files", [])
            if (
                len(tf) == 1
                and PlanIngestionWorkflow._is_trivial_test_init(tf[0])
            ):
                filtered_ids.add(task["task_id"])
                logger.info(
                    "Gate 2b: filtering trivial test init task %s (%s)",
                    task["task_id"],
                    tf[0],
                )
            else:
                result.append(task)
        # Clean up dangling dependency references
        if filtered_ids:
            for task in result:
                task["depends_on"] = [
                    d for d in task.get("depends_on", [])
                    if d not in filtered_ids
                ]
        return result

    @staticmethod
    def _dedup_tasks_by_target_file(
        tasks: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Gate 2c: Deduplicate tasks targeting the same file (different paths).

        The LLM may emit the same file with different path formats (e.g.,
        ``Program.cs`` and ``src/cartservice/src/Program.cs``).  Gate 2a
        splits both into sub-tasks, creating duplicates that generate the
        same output file twice.

        Dedup strategy: group tasks by (parent_feature_base, basename),
        keep the task with the longest (most specific) path.  This
        preserves the path that includes directory structure.
        """
        from pathlib import PurePosixPath

        # Build a map: (feature_base, basename) → list of (task, path_len)
        seen: Dict[tuple, List[tuple]] = {}
        for task in tasks:
            tid = task["task_id"]
            tf = task.get("config", {}).get("context", {}).get("target_files", [])
            if not tf:
                # Tasks without target_files pass through (e.g., Dockerfile)
                title = task.get("title", "")
                basename = PurePosixPath(title.rsplit("—", 1)[-1].strip()).name if "—" in title else ""
                key = (tid[:6], basename or tid)  # approximate grouping
            else:
                basename = PurePosixPath(tf[0]).name
                # Extract parent feature base (PI-001 from PI-001a)
                import re
                base_match = re.match(r"(PI-\d+)", tid)
                feature_base = base_match.group(1) if base_match else tid
                key = (feature_base, basename)

            path_len = len(tf[0]) if tf else 0
            seen.setdefault(key, []).append((task, path_len))

        result: List[Dict[str, Any]] = []
        filtered_ids: set[str] = set()
        for key, candidates in seen.items():
            if len(candidates) == 1:
                result.append(candidates[0][0])
            else:
                # Keep the candidate with the longest path (most specific)
                candidates.sort(key=lambda x: x[1], reverse=True)
                result.append(candidates[0][0])
                for dup_task, _ in candidates[1:]:
                    filtered_ids.add(dup_task["task_id"])
                    logger.info(
                        "Gate 2c: dedup — removing %s (duplicate of %s targeting %s)",
                        dup_task["task_id"],
                        candidates[0][0]["task_id"],
                        key[1],
                    )

        # Clean up dangling dependency references
        if filtered_ids:
            for task in result:
                task["depends_on"] = [
                    d for d in task.get("depends_on", [])
                    if d not in filtered_ids
                ]
            logger.info(
                "Gate 2c: removed %d duplicate tasks (%d → %d)",
                len(filtered_ids), len(tasks), len(result),
            )

        return result

    # ------------------------------------------------------------------
    # Manifest + context helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_manifest_context(manifest: Any) -> Dict[str, Any]:
        """Extract architectural context from a ContextCore manifest."""
        ctx: Dict[str, Any] = {}

        # Objectives → project goals for prompt injection
        if hasattr(manifest, "strategy") and manifest.strategy:
            objectives = getattr(manifest.strategy, "objectives", [])
            if objectives:
                ctx["objectives"] = []
                for obj in objectives:
                    # v2 ObjectiveV2 has .description, v1 has .name
                    desc = getattr(obj, "description", None)
                    name_val = getattr(obj, "name", None)
                    label = desc if isinstance(desc, str) else (name_val if isinstance(name_val, str) else str(obj))
                    # Convert KeyResult models to dicts for JSON serialization
                    key_results = getattr(obj, "key_results", [])
                    kr_list = [
                        kr.model_dump() if hasattr(kr, "model_dump") else kr.dict()
                        if hasattr(kr, "dict") else kr
                        for kr in key_results
                    ]
                    ctx["objectives"].append({"name": label, "key_results": kr_list})

        # Guidance → constraints, preferences, focus
        guidance = getattr(manifest, "guidance", None)
        if guidance:
            constraints = getattr(guidance, "constraints", [])
            if constraints:
                ctx["constraints"] = [
                    {
                        "rule": getattr(c, "rule", str(c)),
                        "severity": getattr(c, "severity", "info"),
                        # v2 Constraint has .applies_to, v1 has .scope
                        "scope": getattr(c, "applies_to", None)
                        or getattr(c, "scope", "*"),
                    }
                    for c in constraints
                ]
            preferences = getattr(guidance, "preferences", [])
            if preferences:
                prefs = []
                for p in preferences:
                    # v2 Preference has .description, v1 has .preference
                    desc = getattr(p, "description", None)
                    pref_val = getattr(p, "preference", None)
                    prefs.append(
                        desc if isinstance(desc, str) else (pref_val if isinstance(pref_val, str) else str(p))
                    )
                ctx["preferences"] = prefs
            focus = getattr(guidance, "focus", None)
            if focus:
                areas = getattr(focus, "areas", [])
                if areas:
                    ctx["focus_areas"] = list(areas)

        return ctx

    @staticmethod
    def _extract_project_metadata(manifest: Any) -> Dict[str, Any]:
        """Extract operational project metadata from a ContextCore manifest.

        Pulls business criticality, SLO requirements, risk inventory, and
        observability config from ``manifest.spec``.  These are *operational*
        concerns (distinct from the *strategic* data in
        ``_extract_manifest_context``).
        """
        meta: Dict[str, Any] = {}
        spec = getattr(manifest, "spec", None)
        if spec is None:
            return meta

        # --- business criticality ---
        business = getattr(spec, "business", None)
        if business:
            criticality = getattr(business, "criticality", None)
            if criticality is not None:
                meta["criticality"] = (
                    criticality.value
                    if hasattr(criticality, "value")
                    else str(criticality)
                )
            # v2 BusinessSpec has .business_owner, v1 has .owner
            owner = getattr(business, "business_owner", None) or getattr(
                business, "owner", None
            )
            if owner:
                meta["business_owner"] = str(owner)
            # v2 BusinessSpec has .business_value, v1 has .value
            value = getattr(business, "business_value", None) or getattr(
                business, "value", None
            )
            if value:
                meta["business_value"] = str(value)

        # --- SLO / requirements ---
        requirements = getattr(spec, "requirements", None)
        if requirements:
            reqs: Dict[str, Any] = {}
            for attr in (
                "availability",
                "latency_p99",
                "throughput",
                "error_budget",
            ):
                val = getattr(requirements, attr, None)
                if val is not None:
                    reqs[attr] = (
                        val.value if hasattr(val, "value") else val
                    )
            if reqs:
                meta["requirements"] = reqs

        # --- risk inventory ---
        # Risk fields are all string-semantic (type, priority, description,
        # etc.), so non-enum values are coerced with str() — unlike
        # requirements/observability where numeric values are preserved.
        risks_raw = getattr(spec, "risks", None)
        if risks_raw:
            risks_list = []
            for risk in risks_raw:
                entry: Dict[str, Any] = {}
                for attr in (
                    "type",
                    "priority",
                    "description",
                    "scope",
                    "mitigation",
                    "component",
                ):
                    val = getattr(risk, attr, None)
                    if val is not None:
                        entry[attr] = (
                            val.value if hasattr(val, "value") else str(val)
                        )
                if entry:
                    risks_list.append(entry)
            if risks_list:
                meta["risks"] = risks_list

        # --- observability config ---
        observability = getattr(spec, "observability", None)
        if observability:
            obs: Dict[str, Any] = {}
            for attr in (
                "trace_sampling",
                "metrics_interval",
                "log_level",
            ):
                val = getattr(observability, attr, None)
                if val is not None:
                    obs[attr] = (
                        val.value if hasattr(val, "value") else val
                    )
            if obs:
                meta["observability"] = obs

        # --- REQ-ICD-106: security spec from manifest ---
        _security = getattr(spec, "security", None)
        if _security:
            sensitivity = getattr(_security, "sensitivity", "medium")
            data_stores = getattr(_security, "data_stores", [])
            databases: Dict[str, Any] = {}
            for store in data_stores:
                store_id = getattr(store, "id", None)
                if store_id:
                    databases[store_id] = {
                        "type": getattr(store, "type", ""),
                        "sensitivity": getattr(store, "sensitivity", "medium"),
                    }
                    cl = getattr(store, "client_library", None)
                    if cl:
                        databases[store_id]["client_library"] = cl
                    cs = getattr(store, "credential_source", None)
                    if cs:
                        databases[store_id]["credential_source"] = cs
            if databases:
                meta["security_contract"] = {
                    "databases": databases,
                    "sensitivity": str(sensitivity.value) if hasattr(sensitivity, "value") else str(sensitivity),
                    "source": "manifest",
                }
                logger.info(
                    "Manifest security: %d database(s), sensitivity=%s",
                    len(databases), sensitivity,
                )

        return meta

    @staticmethod
    def _extend_inventory_with_ingestion(
        output_dir: Path,
        doc_path: Path,
        context_seed_path: Path,
        design_calibration: Optional[Dict[str, Any]],
        context_files: Optional[List[str]],
        source_checksum_val: Optional[str],
        review_output: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Extend the artifact inventory with ingestion-stage entries.

        Finds run-provenance.json in the export output directory (derived
        from context_files) and extends it with plan_document,
        refine_suggestions, design_calibration, and task_decomposition entries.
        """
        from startd8.utils.artifact_inventory import extend_inventory

        # Derive export output directory from context_files
        export_dir: Optional[Path] = None
        if context_files:
            for raw_path in context_files:
                p = Path(raw_path.strip()).expanduser()
                if p.name == "onboarding-metadata.json":
                    export_dir = p.resolve().parent if p.is_absolute() else (output_dir / p).resolve().parent
                    break
                if p.name == "run-provenance.json":
                    export_dir = p.resolve().parent if p.is_absolute() else (output_dir / p).resolve().parent
                    break

        # Fall back to output_dir itself
        if not export_dir:
            export_dir = output_dir

        # Also check output_dir for run-provenance.json (common when export
        # and ingestion share the same output directory)
        if not (export_dir / "run-provenance.json").exists():
            if (output_dir / "run-provenance.json").exists():
                export_dir = output_dir
            else:
                logger.debug(
                    "artifact_inventory: no run-provenance.json found — "
                    "skipping inventory extension"
                )
                return

        now_iso = datetime.now(timezone.utc).isoformat()
        freshness = {}
        if source_checksum_val:
            freshness["source_checksum"] = source_checksum_val
            freshness["source_file"] = ".contextcore.yaml"

        entries: List[Dict[str, Any]] = []

        # plan_document
        if doc_path.exists():
            entries.append({
                "artifact_id": "ingestion.plan_document",
                "role": "plan_document",
                "description": "Structured plan with architecture, risk register, phase breakdown",
                "produced_by": "startd8.workflow.plan_ingestion",
                "stage": "ingestion",
                "source_file": doc_path.name,
                "sha256": _sha256_file_hex(doc_path),
                "produced_at": now_iso,
                "freshness": freshness,
                "consumers": ["artisan.design"],
                "consumption_hint": (
                    "Load architecture and risk sections as additional context "
                    "for design prompt."
                ),
            })

        # refine_suggestions — stored in the plan document appendix
        if doc_path.exists():
            plan_text = doc_path.read_text(encoding="utf-8")
            if review_output or "Appendix C" in plan_text or "## Architectural Review" in plan_text:
                entries.append({
                    "artifact_id": "ingestion.refine_suggestions",
                    "role": "refine_suggestions",
                    "description": "Architectural review suggestions from REFINE phase",
                    "produced_by": "startd8.workflow.plan_ingestion.refine",
                    "stage": "ingestion",
                    "source_file": doc_path.name,
                    "json_path": "Appendix C",
                    "sha256": _sha256_file_hex(doc_path),
                    "produced_at": now_iso,
                    "freshness": freshness,
                    "consumers": ["artisan.design"],
                    "consumption_hint": (
                        "Extract per-task suggestions and inject into FeatureContext. "
                        "Eliminates redundant architectural review in DESIGN."
                    ),
                })

        # refine_apply_provenance — structured triage/apply metadata
        if review_output:
            apply_data = review_output.get("apply", {})
            if apply_data.get("applied_count", 0) > 0:
                entries.append({
                    "artifact_id": "ingestion.refine_apply_provenance",
                    "role": "refine_apply_provenance",
                    "description": "Apply-step integration metadata from REFINE architectural review",
                    "produced_by": "startd8.workflow.plan_ingestion.refine",
                    "stage": "ingestion",
                    "applied_count": apply_data.get("applied_count", 0),
                    "applied_ids": apply_data.get("applied_ids", []),
                    "produced_at": now_iso,
                    "freshness": freshness,
                    "consumers": ["artisan.design", "artisan.implement"],
                    "consumption_hint": (
                        "Check applied_ids to avoid re-implementing suggestions "
                        "already integrated into the document body."
                    ),
                })

            # Enrich existing refine_suggestions entry with triage counts
            triage_data = review_output.get("triage", {})
            for entry in entries:
                if entry.get("artifact_id") == "ingestion.refine_suggestions":
                    entry["triage_accepted_count"] = triage_data.get("accepted", 0)
                    entry["triage_rejected_count"] = triage_data.get("rejected", 0)
                    break

        # design_calibration
        if design_calibration and context_seed_path.exists():
            cal_json = json.dumps(design_calibration, sort_keys=True, default=str)
            entries.append({
                "artifact_id": "ingestion.design_calibration",
                "role": "design_calibration",
                "description": "Per-task depth tier, calibrated section list, max output tokens",
                "produced_by": "startd8.workflow.plan_ingestion.emit",
                "stage": "ingestion",
                "source_file": context_seed_path.name,
                "json_path": "$.design_calibration",
                "sha256": sha256(cal_json.encode()).hexdigest(),
                "checksum_scope": "calibration_data_json",
                "produced_at": now_iso,
                "freshness": freshness,
                "consumers": ["artisan.design"],
                "consumption_hint": (
                    "Already consumed via seed. Listed for inventory completeness."
                ),
            })

        # task_decomposition
        if context_seed_path.exists():
            entries.append({
                "artifact_id": "ingestion.task_decomposition",
                "role": "task_decomposition",
                "description": "Per-task descriptions, file targets, complexity assessment",
                "produced_by": "startd8.workflow.plan_ingestion.emit",
                "stage": "ingestion",
                "source_file": context_seed_path.name,
                "json_path": "$.tasks",
                "sha256": _sha256_file_hex(context_seed_path),
                "produced_at": now_iso,
                "freshness": freshness,
                "consumers": ["artisan.plan", "artisan.design"],
                "consumption_hint": "Use for task ordering and feature context.",
            })

        if entries:
            extend_inventory(export_dir, entries)

    @staticmethod
    def _load_onboarding_metadata(
        context_files: Optional[List[str]],
        output_dir: Path,
    ) -> Optional[Dict[str, Any]]:
        """Load onboarding-metadata.json if present among context files.

        When context_files includes a path ending with 'onboarding-metadata.json',
        load and return its contents. Used for Items 5, 7 (merge into seed,
        artifact_manifest_path, project_context_path).
        """
        if not context_files:
            return None
        for raw_path in context_files:
            path = Path(raw_path.strip()).expanduser()
            if path.name != "onboarding-metadata.json":
                continue
            if not path.is_absolute():
                # Resolve relative to output_dir (common for plan ingestion)
                path = (output_dir / path).resolve()
            if not path.exists():
                logger.debug(
                    "onboarding-metadata.json referenced but not found: %s",
                    path,
                )
                continue
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    logger.debug(
                        "Loaded onboarding metadata from %s (%d keys)",
                        path,
                        len(data),
                    )
                    return data
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning(
                    "Failed to load onboarding-metadata.json %s: %s",
                    path,
                    exc,
                )
        return None

    @staticmethod
    def _derive_architectural_context(
        parsed_plan: ParsedPlan,
        manifest_context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Combine manifest data with deterministic cross-feature analysis."""
        ctx: Dict[str, Any] = {
            "project_goals": list(parsed_plan.goals),
            "objectives": manifest_context.get("objectives", []),
            "constraints": manifest_context.get("constraints", []),
            "preferences": manifest_context.get("preferences", []),
            "focus_areas": manifest_context.get("focus_areas", []),
        }

        # shared_modules: files targeted by 2+ features
        file_counter: Counter[str] = Counter()
        file_features: Dict[str, List[str]] = {}
        for feat in parsed_plan.features:
            for tf in feat.target_files:
                file_counter[tf] += 1
                file_features.setdefault(tf, []).append(feat.feature_id)
        ctx["shared_modules"] = [
            {"path": path, "features": file_features[path]}
            for path, count in file_counter.items()
            if count >= 2
        ]

        # REQ-SIG-200: merge service communication graph shared modules
        _graph = manifest_context.get("service_communication_graph", {})
        _graph_shared = _graph.get("shared_modules", {})
        if _graph_shared and isinstance(_graph_shared, dict):
            for mod_name, mod_info in _graph_shared.items():
                if isinstance(mod_info, dict):
                    ctx["shared_modules"].append({
                        "name": mod_name,
                        "type": mod_info.get("type", "unknown"),
                        "used_by": mod_info.get("used_by", []),
                    })
            logger.info(
                "Architectural context: merged %d shared modules from communication graph",
                len(_graph_shared),
            )

        # import_conventions: most common parent directories
        dir_counter: Counter[str] = Counter()
        for feat in parsed_plan.features:
            for tf in feat.target_files:
                parent = str(Path(tf).parent)
                if parent != ".":
                    dir_counter[parent] += 1
        ctx["import_conventions"] = [
            d for d, _ in dir_counter.most_common(5)
        ]

        # domain_concepts: capitalized terms from goals
        concepts: list[str] = []
        for goal in parsed_plan.goals:
            # Parenthetical lists
            for m in re.findall(r"\(([^)]+)\)", goal):
                concepts.extend(
                    t.strip() for t in m.split(",") if t.strip()
                )
            # CamelCase / PascalCase terms
            concepts.extend(re.findall(r"\b[A-Z][a-z]+(?:[A-Z][a-z]+)+\b", goal))
        ctx["domain_concepts"] = list(dict.fromkeys(concepts))[:20]

        # dependency_clusters: root features (depended upon, no deps of their own)
        dep_graph = parsed_plan.dependency_graph
        # Features that are depended upon by others (from both dep_graph and feat.dependencies)
        depended_upon: set[str] = set()
        for deps in dep_graph.values():
            depended_upon.update(deps)
        for feat in parsed_plan.features:
            depended_upon.update(feat.dependencies)
        # Features that have their own dependencies (from either source)
        has_deps: set[str] = set(dep_graph.keys()) | {
            f.feature_id for f in parsed_plan.features if f.dependencies
        }
        # Roots = depended upon but have no deps of their own
        # Filter against known feature IDs to exclude hallucinated/typo'd IDs
        known_fids = {f.feature_id for f in parsed_plan.features}
        root_ids = [
            fid for fid in depended_upon
            if fid in known_fids
            and fid not in has_deps
        ]

        clusters: list[Dict[str, Any]] = []
        for root_id in root_ids[:10]:
            dependents: list[str] = []
            for fid, deps in dep_graph.items():
                if root_id in deps:
                    dependents.append(fid)
            # Also check feat.dependencies (may not be in dep_graph)
            for feat in parsed_plan.features:
                if root_id in feat.dependencies and feat.feature_id not in dependents:
                    dependents.append(feat.feature_id)
            if dependents:
                clusters.append({"root": root_id, "dependents": dependents})
        ctx["dependency_clusters"] = clusters

        return ctx

    @staticmethod
    def _derive_design_calibration(
        tasks: List[Dict[str, Any]],
    ) -> Dict[str, Dict[str, Any]]:
        """Derive per-task design depth calibration.

        Uses ContextCore SizeEstimator when available, falls back to
        LOC-based heuristics.
        """
        estimator = None
        try:
            from contextcore.agent.size_estimation import SizeEstimator
            estimator = SizeEstimator()
        except ImportError:
            pass

        calibration: Dict[str, Dict[str, Any]] = {}
        for task in tasks:
            ctx = task.get("config", {}).get("context", {})
            loc = ctx.get("estimated_loc", 100)
            desc = task.get("config", {}).get("task_description", "")

            if estimator:
                try:
                    estimate = estimator.estimate(
                        task=desc,
                        inputs={"context_files": ctx.get("target_files", [])},
                    )
                    complexity = estimate.complexity
                except Exception:
                    complexity = (
                        "low" if loc <= 50
                        else ("medium" if loc <= 150 else "high")
                    )
            else:
                complexity = (
                    "low" if loc <= 50
                    else ("medium" if loc <= 150 else "high")
                )

            tier_name = {
                "low": "brief",
                "medium": "standard",
                "high": "comprehensive",
            }.get(complexity, "standard")
            tier = DEPTH_TIERS[tier_name]

            # Implement phase token caps: code gen needs more than design.
            # Claude models support 64K output; previous 16K default caused
            # truncation on medium-complexity tasks (PI-003/PI-005 post-mortem).
            implement_tokens = {
                "brief": 16384,
                "standard": 32768,
                "comprehensive": 49152,
            }.get(tier_name, 32768)

            # --- WCP-005: Domain-aware token adjustment ---
            # Prefer _enrichment from domain preflight if available;
            # otherwise infer domain from target file extensions.
            enrichment = task.get("_enrichment", {})
            domain = enrichment.get("domain")
            if not domain:
                target_files = ctx.get("target_files", [])
                if target_files:
                    exts = {
                        tf.rsplit(".", 1)[-1].lower()
                        for tf in target_files if "." in tf
                    }
                    has_python = "py" in exts
                    config_exts = {"toml", "yaml", "yml", "json", "ini", "cfg"}
                    has_config = bool(exts & config_exts)

                    if has_python:
                        if any(
                            os.path.basename(tf).startswith("test_")
                            or os.path.basename(tf).endswith("_test.py")
                            or "/tests/" in tf
                            or "/test/" in tf
                            for tf in target_files
                        ):
                            domain = "python-test"
                        else:
                            domain = "python-single-module"
                    elif has_config:
                        # Use the first config ext for the domain label
                        config_ext = next(
                            e for e in sorted(exts) if e in config_exts
                        )
                        domain = f"config-{config_ext.replace('yml', 'yaml')}"
                    elif exts:
                        domain = "non-python"
                if not domain:
                    domain = "unknown"
            domain_token_multipliers = {
                "config-toml": 0.5,
                "config-yaml": 0.5,
                "config-json": 0.5,
                "config-ini": 0.5,
                "config-cfg": 0.5,
                "non-python": 0.6,
                "python-test": 0.8,
                "python-single-module": 1.0,
                "python-package-module": 1.0,
                "unknown": 1.0,
            }
            domain_multiplier = domain_token_multipliers.get(domain, 1.0)
            if domain_multiplier != 1.0:
                implement_tokens = int(implement_tokens * domain_multiplier)

            calibration[task["task_id"]] = {
                "depth_tier": tier_name,
                "sections": tier["sections"],
                "max_output_tokens": tier["max_tokens"],
                "implement_max_output_tokens": implement_tokens,
                "depth_guidance": tier["guidance"],
                "complexity": complexity,
            }
        return calibration

    # ------------------------------------------------------------------
    # Phase: EMIT
    # ------------------------------------------------------------------

    def _phase_emit(
        self,
        doc_path: Path,
        route: ContractorRoute,
        complexity: ComplexityScore,
        output_dir: Path,
        review_rounds: int,
        review_quality_tier: str,
        scope: Optional[str],
        context_files: Optional[List[str]],
        warn_cost_usd: Optional[float],
        max_cost_usd: Optional[float],
        parsed_plan: Optional[ParsedPlan] = None,
        step_costs: Optional[Dict[str, float]] = None,
        tracking_config: Optional["TaskTrackingConfig"] = None,
        manifest_context: Optional[Dict[str, Any]] = None,
        translation_quality: Optional[Dict[str, Any]] = None,
        requirement_hints: Optional[Dict[str, Dict[str, Any]]] = None,
        onboarding_metadata: Optional[Dict[str, Any]] = None,
        review_output: Optional[Dict[str, Any]] = None,
        project_metadata: Optional[Dict[str, Any]] = None,
        project_root: Optional[Path] = None,
        force_regenerate: bool = False,
    ) -> EmitResult:
        """Compat wrapper — delegates to PhaseEmitter (AC-R4)."""
        from .plan_ingestion_emitter import PhaseEmitter

        # Build a PlanIngestionConfig with the caller's positional args.
        # When called from _execute(), self._cfg exists; when called
        # directly from tests, we fall back to a fresh default.
        _base_cfg = getattr(self, "_cfg", None) or PlanIngestionConfig()
        cfg_overlay = _dataclass_replace(
            _base_cfg,
            review_rounds=review_rounds,
            review_quality_tier=review_quality_tier,
            scope=scope,
            context_files=context_files,
            warn_cost_usd=warn_cost_usd,
            max_cost_usd=max_cost_usd,
            force_regenerate=force_regenerate,
        )

        emitter = PhaseEmitter(
            workflow=self,
            cfg=cfg_overlay,
            parsed_plan=parsed_plan,
            complexity=complexity,
            route=route,
            output_dir=output_dir,
            doc_path=doc_path,
        )
        return emitter.emit(
            step_costs=step_costs,
            manifest_context=manifest_context,
            translation_quality=translation_quality,
            review_output=review_output,
            requirement_hints=requirement_hints,
            onboarding_metadata=onboarding_metadata,
            project_metadata=project_metadata,
            project_root=project_root,
            tracking_config=tracking_config,
        )

    # ------------------------------------------------------------------
    # Main execution
    # ------------------------------------------------------------------

    def _execute(
        self,
        config: Dict[str, Any],
        agents: Optional[List[BaseAgent]],
        on_progress: Optional[ProgressCallback],
    ) -> WorkflowResult:
        started_at = datetime.now(timezone.utc)
        steps: List[StepResult] = []
        state = IngestionState()

        # AC-R1: Typed config replaces 30+ config.get() calls.
        cfg = PlanIngestionConfig.from_dict(config)
        self._cfg = cfg  # Store for _phase_emit compat wrapper

        # Local aliases for the most-referenced fields (used dozens of times
        # across phase methods that receive them as parameters).
        plan_path = cfg.plan_path
        output_dir = cfg.output_dir
        threshold = cfg.complexity_threshold
        force_route = cfg.force_route
        review_rounds = cfg.review_rounds
        skip_arc_review = cfg.skip_arc_review
        review_quality_tier = cfg.review_quality_tier
        review_providers = cfg.review_providers
        contextcore_export_dir = cfg.contextcore_export_dir
        min_export_coverage = cfg.min_export_coverage
        scope = cfg.scope
        warn_cost_usd = cfg.warn_cost_usd
        max_cost_usd = cfg.max_cost_usd
        context_files = cfg.context_files
        enable_heuristic_parse_fallback = cfg.enable_heuristic_parse_fallback
        requirements_files = cfg.requirements_files
        low_quality_policy = cfg.low_quality_policy
        min_requirements_coverage = cfg.min_requirements_coverage
        min_artifact_mapping_coverage = cfg.min_artifact_mapping_coverage
        max_contract_conflicts = cfg.max_contract_conflicts
        timeout_config = TimeoutConfig(read=cfg.llm_read_timeout_seconds)
        retry_config = RetryConfig(max_attempts=cfg.llm_max_attempts)
        self._kaizen_capture = cfg.kaizen_capture
        self._kaizen_output_dir = output_dir

        # Kaizen config: prompt suffixes + threshold override (REQ-KPI-500)
        self._kaizen_config: Optional[PlanIngestionKaizenConfig] = None
        _kaizen_config_path = cfg.kaizen_config_path
        if not _kaizen_config_path:
            # Auto-discover kaizen-config.json in output or ancestor dirs
            # (mirrors run-atomic.sh which places it at pipeline-output/$NAME/)
            for _candidate in [output_dir, output_dir.parent, output_dir.parent.parent]:
                _auto = _candidate / "kaizen-config.json"
                if _auto.is_file():
                    _kaizen_config_path = str(_auto)
                    logger.info("Kaizen config auto-discovered at %s", _auto)
                    break
        if _kaizen_config_path:
            _kp = Path(str(_kaizen_config_path)).expanduser()
            if _kp.is_file():
                try:
                    self._kaizen_config = load_kaizen_config(_kp)
                    logger.info("Kaizen config loaded from %s", _kp)
                except (OSError, json.JSONDecodeError, TypeError) as _kc_err:
                    logger.warning("Kaizen config load failed: %s", _kc_err)

        if self._kaizen_config and self._kaizen_config.complexity_threshold_override is not None:
            threshold = self._kaizen_config.complexity_threshold_override
            logger.info("Kaizen: complexity threshold overridden to %d", threshold)
        self._complexity_threshold = threshold

        # Mottainai (Layer 1): Attempt to load onboarding from inventory to prevent waste
        try:
            from startd8.utils import artifact_inventory
            inventory = artifact_inventory.load_inventory(output_dir)
            onboarding_entry, outcome = artifact_inventory.lookup_artifact(inventory, "onboarding")
            
            if outcome == "hit" and onboarding_entry:
                onboarding_raw = artifact_inventory.load_artifact_content(onboarding_entry, output_dir)
                if isinstance(onboarding_raw, dict) and "_cc_capabilities" in onboarding_raw:
                    config["_cc_capabilities"] = onboarding_raw["_cc_capabilities"]
                    logger.info("Mottainai: loaded _cc_capabilities from artifact_inventory")
        except ImportError:
            pass
        except Exception as exc:
            logger.warning(
                "Mottainai Layer 1: inventory lookup failed (non-fatal): %s",
                exc,
            )

        # Capability Propagation (Layer 5)
        _cap_validation_error: Optional[str] = None
        try:
            from contextcore.contracts.capability.validator import CapabilityValidator
            from contextcore.contracts.propagation.loader import ContractLoader
            
            contract_path = Path(__file__).parent.parent.parent / "contractors" / "contracts" / "plan-ingestion.contract.yaml"
            if contract_path.exists():
                logger.info("Loading CapabilityContract from %s", contract_path)
                # We load the contract and initiate the CapabilityValidator
                contract = ContractLoader.load_contract(str(contract_path))
                validator = CapabilityValidator(contract)

                # We validate entry capabilities
                cap_result = validator.validate_entry("plan-ingestion", config)
                if hasattr(cap_result, 'has_blocking_violations') and cap_result.has_blocking_violations():
                    _cap_validation_error = (
                        f"Capability validation failed (Layer 5): {cap_result}"
                    )
        except ImportError as e:
            logger.warning("ContextCore Layer 5 validation unavailable: %s", e)
        except Exception as e:
            logger.warning(
                "Capability validation unavailable (Layer 5 internal error, non-fatal): %s",
                e,
                exc_info=True,
            )

        # Task tracking (opt-in)
        tracking_config = None
        if cfg.generate_task_tracking:
            from .plan_ingestion_models import TaskTrackingConfig
            tracking_config = TaskTrackingConfig(
                project_id=cfg.project_id,
                project_name=cfg.project_name,
                sprint_id=cfg.sprint_id,
                install_to_contextcore=cfg.install_to_contextcore,
                emit_ndjson_events=cfg.emit_ndjson_events,
            )

        total_steps = 6  # preflight, parse, assess, transform, refine, emit
        current_step = 0

        def progress(msg: str):
            nonlocal current_step
            current_step += 1
            if on_progress:
                on_progress(current_step, total_steps, msg)

        def _check_cost(label: str) -> Optional[WorkflowResult]:
            """Check cost thresholds, return error result if exceeded."""
            if warn_cost_usd is not None and state.total_cost > warn_cost_usd:
                logger.warning(
                    "Cost warning: $%.4f exceeds warn threshold $%.2f after %s",
                    state.total_cost, warn_cost_usd, label,
                )
            if max_cost_usd is not None and state.total_cost > max_cost_usd:
                return _fail(
                    f"Cost limit exceeded: ${state.total_cost:.4f} > "
                    f"${max_cost_usd:.2f} after {label}"
                )
            return None

        # Save state for debugging
        state_dir = output_dir / ".startd8"
        state_dir.mkdir(parents=True, exist_ok=True)

        def _save_state():
            """Persist current state for post-mortem debugging."""
            try:
                with _tracer.start_as_current_span("io.state.write") as _io_span:
                    atomic_write_json(
                        state_dir / "plan_ingestion_state.json",
                        state.to_dict(),
                        indent=2,
                    )
                    if _HAS_OTEL and not isinstance(_io_span, _NoOpSpan):
                        _io_span.set_attribute(
                            "io.path", str(state_dir / "plan_ingestion_state.json"),
                        )
            except Exception as exc:
                logger.debug("Failed to save ingestion state: %s", exc)

        def _fail(error_msg: str) -> WorkflowResult:
            """Record failure in state and return error result."""
            state.current_phase = IngestionPhase.FAILED
            state.error = error_msg
            _save_state()
            return WorkflowResult.from_error(
                self.metadata.workflow_id, error_msg, steps=steps,
            )

        # Deferred Layer 5 capability validation failure (set before _fail was defined)
        if _cap_validation_error:
            return _fail(_cap_validation_error)

        # OTel root span (manual lifecycle to avoid re-indenting 400 lines)
        _root_span_ctx = _tracer.start_as_current_span(
            "workflow.plan-ingestion",
            attributes={"workflow.id": self.metadata.workflow_id},
        )
        root_span = _root_span_ctx.__enter__()
        _active_phase_ctx = None  # Track open phase span for cleanup on early return

        try:
            # Read plan
            plan_text = plan_path.read_text(encoding="utf-8")
            step_costs: Dict[str, float] = {}
            onboarding_metadata: Optional[Dict[str, Any]] = None
            preflight_evidence: Dict[str, Any] = {"checksums": {}, "paths": {}, "coverage": {}}
            requirements_hints_index: Dict[str, Dict[str, Any]] = {}

            # --- DISCOVER .contextcore.yaml (needed by both PREFLIGHT and MANIFEST) ---
            contextcore_yaml: Optional[Path] = None
            _raw_cc_yaml = cfg.contextcore_yaml
            if _raw_cc_yaml is not None:
                contextcore_yaml = Path(str(_raw_cc_yaml)).expanduser()
            else:
                # Auto-discover: project_root (most specific), output_dir, cwd
                candidates = [output_dir / ".contextcore.yaml", Path.cwd() / ".contextcore.yaml"]
                if cfg.project_root:
                    candidates.insert(0, Path(cfg.project_root) / ".contextcore.yaml")
                for candidate in candidates:
                    if candidate.exists():
                        contextcore_yaml = candidate
                        break

            # --- PREFLIGHT ---
            _active_phase_ctx = _tracer.start_as_current_span("ingestion.preflight")
            _pf_span = _active_phase_ctx.__enter__()
            root_span.add_event("state.transition", {"phase": "preflight"})

            progress("Preflight")
            preflight_step = StepResult(step_name="preflight", output="Running export contract checks")
            onboarding_metadata, preflight_evidence, preflight_warnings, preflight_errors = (
                self._preflight_export_contract(
                    contextcore_export_dir=contextcore_export_dir,
                    context_files=context_files,
                    output_dir=output_dir,
                    min_export_coverage=min_export_coverage,
                    contextcore_yaml_path=contextcore_yaml,
                )
            )
            if preflight_warnings:
                preflight_step.output = (
                    preflight_step.output
                    + "; warnings: "
                    + " | ".join(preflight_warnings[:5])
                )
            if preflight_errors:
                preflight_step.error = " ; ".join(preflight_errors)
            steps.append(preflight_step)

            if _HAS_OTEL and not isinstance(_pf_span, _NoOpSpan):
                _pf_span.set_attribute("phase.warnings_count", len(preflight_warnings))
                _pf_span.set_attribute("phase.errors_count", len(preflight_errors))
            _active_phase_ctx.__exit__(None, None, None)
            _active_phase_ctx = None

            if preflight_step.error:
                return _fail(preflight_step.error)
            requirements_hints_index = _normalize_requirements_hints(onboarding_metadata)

            # Load requirements corpus for routing quality + dual-document refine
            requirements_docs = _load_requirements_documents(requirements_files, output_dir)
            if requirements_files and not requirements_docs:
                return _fail(
                    "Requirements files were provided but none could be loaded. "
                    "Check requirements_path/requirements_files paths."
                )

            # --- MANIFEST LOADING (optional) ---
            manifest_context: Dict[str, Any] = {}
            project_metadata: Dict[str, Any] = {}
            if contextcore_yaml:
                try:
                    from contextcore.models import load_manifest
                    manifest = load_manifest(str(contextcore_yaml))
                    manifest_context = self._extract_manifest_context(manifest)
                    project_metadata = self._extract_project_metadata(manifest)
                    logger.debug(
                        "Loaded manifest from %s: %d context keys, %d metadata keys",
                        contextcore_yaml, len(manifest_context), len(project_metadata),
                    )
                except ImportError:
                    logger.debug("contextcore not installed — skipping manifest loading")
                except Exception as exc:
                    logger.warning("Failed to load manifest %s: %s", contextcore_yaml, exc)

            # --- PARSE ---
            _active_phase_ctx = _tracer.start_as_current_span("ingestion.parse")
            _parse_span = _active_phase_ctx.__enter__()
            root_span.add_event("state.transition", {"phase": "parse"})

            progress("Parse")
            state.current_phase = IngestionPhase.PARSE
            assessor = self._resolve_assessor_agent(
                config,
                timeout_config=timeout_config,
                retry_config=retry_config,
            )

            parsed_plan, parse_step = self._phase_parse(plan_text, assessor)
            _used_heuristic_parse = False
            if parse_step.error and enable_heuristic_parse_fallback:
                parsed_plan = _heuristic_parse_plan(plan_text)
                _used_heuristic_parse = True
                parse_step.error = None
                parse_step.output = (
                    parse_step.output + "\n[heuristic fallback] parse succeeded without LLM JSON"
                )[:_OUTPUT_TRUNCATION]
                parse_step.metadata["heuristic_fallback"] = True
                if _HAS_OTEL and not isinstance(_parse_span, _NoOpSpan):
                    _parse_span.add_event("decision.heuristic_fallback", {
                        "phase": "parse",
                        "reason": "LLM parse failed, heuristic enabled",
                    })
            steps.append(parse_step)
            state.total_cost += parse_step.cost
            step_costs["parse"] = parse_step.cost
            if parse_step.error:
                return _fail(parse_step.error)
            # ── Deterministic enrichment: inject Implementation Contract
            # text from the plan markdown into feature descriptions so
            # downstream phases (TRANSFORM, EMIT) have full detail
            # without relying on LLM summarization.  $0.00 per run.
            _enriched_count = _enrich_features_from_plan(
                parsed_plan.features, parsed_plan.raw_text,
            )
            if _enriched_count:
                logger.info(
                    "Enriched %d/%d feature descriptions with implementation "
                    "contracts from plan markdown",
                    _enriched_count, len(parsed_plan.features),
                )
                if _HAS_OTEL and not isinstance(_parse_span, _NoOpSpan):
                    _parse_span.add_event("enrichment.implementation_contracts", {
                        "enriched_count": _enriched_count,
                        "total_features": len(parsed_plan.features),
                    })

            # OI-002: Acyclicity gate — detect and break cycles in the
            # dependency graph BEFORE ASSESS to avoid wasting LLM calls on
            # plans that would deadlock the FeatureQueue at runtime.
            _dep_graph = parsed_plan.dependency_graph
            if _dep_graph:
                _broken = _break_dependency_cycles(_dep_graph)
                if _broken:
                    logger.warning(
                        "Dependency graph had %d cycle(s) — broke back-edges: %s",
                        len(_broken),
                        ", ".join(f"{a}→{b}" for a, b in _broken),
                    )
                    # Propagate broken edges to per-feature dependencies
                    # (the cycle breaker mutates dep_graph but features have
                    # their own dependencies list that gets threaded to tasks)
                    _broken_set = {(src, dst) for src, dst in _broken}
                    for _feat in parsed_plan.features:
                        _fid = _feat.feature_id
                        _orig_deps = list(getattr(_feat, "dependencies", []))
                        _cleaned = [
                            d for d in _orig_deps
                            if (_fid, d) not in _broken_set
                        ]
                        if len(_cleaned) < len(_orig_deps):
                            _feat.dependencies = _cleaned
                            logger.debug(
                                "Feature %s: removed %d circular dep(s)",
                                _fid, len(_orig_deps) - len(_cleaned),
                            )
                    if _HAS_OTEL and not isinstance(_parse_span, _NoOpSpan):
                        _parse_span.add_event("acyclicity_gate.cycles_broken", {
                            "cycles_broken": len(_broken),
                            "edges": [f"{a}->{b}" for a, b in _broken],
                        })

            state.parsed_plan = parsed_plan
            logger.debug(
                "Parsed plan: '%s' with %d features (heuristic=%s, enriched=%d)",
                parsed_plan.title, len(parsed_plan.features),
                _used_heuristic_parse, _enriched_count,
            )

            # When heuristic parse collapses all features into a single
            # fallback entry, translation quality metrics are unreliable
            # (everything maps to the one feature → inflated coverage).
            # Track this so downstream routing can compensate.
            _heuristic_degraded = (
                _used_heuristic_parse
                and len(parsed_plan.features) == 1
                and parsed_plan.features[0].feature_id == "F-001"
                and not parsed_plan.features[0].target_files
                and parsed_plan.features[0].description
                == _HEURISTIC_FALLBACK_DESCRIPTION
            )
            if _heuristic_degraded:
                logger.warning(
                    "Heuristic parse collapsed plan to single fallback feature — "
                    "translation quality metrics are unreliable; biasing toward artisan"
                )

            translation_quality = self._evaluate_translation_quality(
                parsed_plan=parsed_plan,
                requirements_docs=requirements_docs,
                onboarding=onboarding_metadata,
                requirements_hints=requirements_hints_index,
            )
            # Mark quality as degraded so traceability report is honest
            if _heuristic_degraded:
                translation_quality["_heuristic_degraded"] = True

            cost_err = _check_cost("parse")

            if _HAS_OTEL and not isinstance(_parse_span, _NoOpSpan):
                _parse_span.set_attribute("phase.cost", parse_step.cost)
                _parse_span.set_attribute("phase.heuristic_fallback", _used_heuristic_parse)
                _parse_span.set_attribute(
                    "phase.features_count",
                    len(parsed_plan.features) if parsed_plan else 0,
                )
            _active_phase_ctx.__exit__(None, None, None)
            _active_phase_ctx = None

            if cost_err:
                return cost_err

            # --- ASSESS ---
            _active_phase_ctx = _tracer.start_as_current_span("ingestion.assess")
            _assess_span = _active_phase_ctx.__enter__()
            root_span.add_event("state.transition", {"phase": "assess"})

            progress("Assess")
            state.current_phase = IngestionPhase.ASSESS

            _used_heuristic_assess = False
            complexity, assess_step = self._phase_assess(
                parsed_plan, assessor, threshold, force_route,
            )
            if assess_step.error and enable_heuristic_parse_fallback:
                _used_heuristic_assess = True
                complexity = _heuristic_assess_complexity(
                    parsed_plan,
                    threshold=threshold,
                    force_route=force_route,
                )
                assess_step.error = None
                assess_step.output = (
                    assess_step.output + "\n[heuristic fallback] assess succeeded deterministically"
                )[:_OUTPUT_TRUNCATION]
                assess_step.metadata["heuristic_fallback"] = True
                if _HAS_OTEL and not isinstance(_assess_span, _NoOpSpan):
                    _assess_span.add_event("decision.heuristic_fallback", {
                        "phase": "assess",
                        "reason": "LLM assess failed, heuristic enabled",
                    })
            steps.append(assess_step)
            state.total_cost += assess_step.cost
            step_costs["assess"] = assess_step.cost
            if assess_step.error:
                return _fail(assess_step.error)
            state.complexity = complexity
            state.route = complexity.route

            # When heuristic parse produced a degraded single-feature plan,
            # the composite score is artificially low and quality metrics
            # are inflated.  Override routing to artisan unless the user
            # explicitly forced a route.
            low_quality_reasons: List[str] = []
            if (
                translation_quality["requirements_coverage_percent"]
                < min_requirements_coverage
            ):
                low_quality_reasons.append(
                    f"requirements_coverage={translation_quality['requirements_coverage_percent']:.1f}%"
                )
            if (
                translation_quality["artifact_mapping_percent"]
                < min_artifact_mapping_coverage
            ):
                low_quality_reasons.append(
                    f"artifact_mapping={translation_quality['artifact_mapping_percent']:.1f}%"
                )
            if translation_quality["conflict_count"] > max_contract_conflicts:
                low_quality_reasons.append(
                    f"conflict_count={translation_quality['conflict_count']}"
                )

            if low_quality_reasons:
                details = ", ".join(low_quality_reasons)
                if low_quality_policy == "fail":
                    if _HAS_OTEL and not isinstance(_assess_span, _NoOpSpan):
                        _assess_span.add_event("decision.quality_gate_failed", {
                            "policy": "fail",
                            "details": details,
                        })
                    return _fail(
                        "Translation quality gate failed: "
                        + details
                        + ". Improve mappings or set low_quality_policy to 'warn'."
                    )
                logger.warning(
                    "Low translation quality detected (advisory): %s", details,
                )

            logger.debug(
                "Complexity: %d → route=%s (threshold=%d)",
                complexity.composite,
                complexity.route.value if complexity.route else "?",
                threshold,
            )

            cost_err = _check_cost("assess")

            if _HAS_OTEL and not isinstance(_assess_span, _NoOpSpan):
                _assess_span.set_attribute("phase.cost", assess_step.cost)
                _assess_span.set_attribute(
                    "phase.route",
                    complexity.route.value if complexity.route else "unknown",
                )
                _assess_span.set_attribute("phase.composite_score", complexity.composite)
                _assess_span.set_attribute("phase.heuristic_fallback", _used_heuristic_assess)
            _active_phase_ctx.__exit__(None, None, None)
            _active_phase_ctx = None

            if cost_err:
                return cost_err

            route = complexity.route
            if route is None:
                return _fail("Assessment did not produce a route")

            # --- TRANSFORM ---
            _active_phase_ctx = _tracer.start_as_current_span("ingestion.transform")
            _transform_span = _active_phase_ctx.__enter__()
            root_span.add_event("state.transition", {"phase": "transform"})

            progress("Transform")
            state.current_phase = IngestionPhase.TRANSFORM
            transformer = self._resolve_transformer_agent(
                config,
                timeout_config=timeout_config,
                retry_config=retry_config,
            )

            doc_path, transform_step = self._phase_transform(
                parsed_plan, route, transformer, output_dir,
            )
            if transform_step.error and enable_heuristic_parse_fallback:
                out_filename = "plan-ingestion-tasks.yaml"
                doc_path = output_dir / out_filename
                output_dir.mkdir(parents=True, exist_ok=True)
                atomic_write(doc_path, _heuristic_transform_content(parsed_plan, route))
                transform_step.error = None
                transform_step.output = f"Wrote {doc_path} via heuristic fallback"
            steps.append(transform_step)
            state.total_cost += transform_step.cost
            step_costs["transform"] = transform_step.cost
            if transform_step.error:
                return _fail(transform_step.error)
            state.plan_document_path = str(doc_path)

            cost_err = _check_cost("transform")

            if _HAS_OTEL and not isinstance(_transform_span, _NoOpSpan):
                _transform_span.set_attribute("phase.cost", transform_step.cost)
            _active_phase_ctx.__exit__(None, None, None)
            _active_phase_ctx = None

            if cost_err:
                return cost_err

            # --- REFINE ---
            _active_phase_ctx = _tracer.start_as_current_span("ingestion.refine")
            _refine_span = _active_phase_ctx.__enter__()
            root_span.add_event("state.transition", {"phase": "refine"})

            progress("Refine")
            state.current_phase = IngestionPhase.REFINE

            if skip_arc_review:
                rounds_completed, refine_steps, refine_cost, review_output = (
                    0, [], 0.0, {},
                )
            else:
                # ── Enrichment-aware REFINE configuration ──
                # For prime route: include the plan markdown as a context
                # file so the reviewer can cross-reference implementation
                # contracts, and set a scope that directs the reviewer to
                # enrich task descriptions for code generation.
                _refine_context = list(context_files or [])
                _refine_scope = scope
                _refine_apply = config.get("enable_apply")   # not in cfg — refine-only
                _refine_triage = config.get("enable_triage")  # not in cfg — refine-only

                _refine_profile: Optional[Dict[str, Any]] = None

                # Kaizen overrides for REFINE (REQ-KPI-500 extension)
                _kz = getattr(self, "_kaizen_config", None)
                if _kz and _kz.refine_rounds_override is not None:
                    review_rounds = _kz.refine_rounds_override

                # Give the reviewer the plan markdown as context
                _plan_str = str(plan_path)
                if _plan_str not in _refine_context:
                    _refine_context.append(_plan_str)

                if not _refine_scope:
                    _refine_scope = (
                        "Enrich task descriptions for code generation. "
                        "For each task, cross-reference the plan markdown "
                        "and requirements to add: (1) a fenced code example "
                        "showing the primary class/function signature, "
                        "(2) negative scope — what the task should NOT do "
                        "(extract exclusions from the plan's Dependencies, "
                        "Notes, and Out-of-Scope sections; also infer "
                        "boundaries from sibling tasks to prevent overlap), "
                        "(3) error handling patterns from the implementation "
                        "contract, (4) requirements references (REQ-xxx IDs). "
                        "Prioritize tasks with thin descriptions."
                    )

                # Custom review profile focused on enrichment rather
                # than architectural critique.
                _refine_profile = {
                    "persona": (
                        "senior software engineer preparing task specifications "
                        "for an AI code generator"
                    ),
                    "focus": (
                        "enriching task descriptions with concrete code examples, "
                        "explicit negative scope boundaries, error handling "
                        "patterns, and requirements traceability references"
                    ),
                    "areas": [
                        "completeness", "clarity", "testability",
                        "architecture", "security", "maintainability",
                        "scalability",
                    ],
                }

                # Default to triage+apply so enrichment suggestions
                # are integrated into the YAML before EMIT reads it.
                if _refine_apply is None:
                    _refine_apply = True
                if _refine_triage is None:
                    _refine_triage = True

                # Apply kaizen overrides after defaults are set
                if _kz:
                    if _kz.refine_scope_override:
                        _refine_scope = _kz.refine_scope_override
                    if _kz.refine_review_profile:
                        _refine_profile = _kz.refine_review_profile

                rounds_completed, refine_steps, refine_cost, review_output = self._phase_refine(
                    doc_path,
                    review_rounds,
                    review_quality_tier,
                    _refine_scope,
                    _refine_context or None,
                    list(requirements_docs.keys()) if requirements_docs else None,
                    warn_cost_usd,
                    max_cost_usd,
                    enable_apply=_refine_apply,
                    enable_prompt_caching=config.get("enable_prompt_caching", cfg.enable_prompt_caching),
                    enable_triage=_refine_triage,
                    providers=review_providers,
                    custom_review_profile=_refine_profile,
                )
            steps.extend(refine_steps)
            state.total_cost += refine_cost
            step_costs["refine"] = refine_cost

            # Guard: if REFINE was attempted but produced zero rounds,
            # the review workflow failed silently — warn and clear output
            # so EMIT doesn't consume invalid/empty review data.
            if not skip_arc_review and rounds_completed == 0 and refine_cost > 0:
                logger.warning(
                    "REFINE produced 0 rounds but cost $%.4f — review may have "
                    "failed silently; clearing review_output to prevent downstream "
                    "consumption of invalid data",
                    refine_cost,
                )
                review_output = {}

            # Kaizen prompt/response capture for REFINE rounds
            if self._kaizen_output_dir and refine_steps:
                for _rs_idx, _rs in enumerate(refine_steps):
                    _rs_prompt = _rs.input or ""
                    _rs_response = _rs.output or ""
                    if _rs_prompt or _rs_response:
                        persist_prompt_response(
                            self._kaizen_output_dir,
                            f"refine_round{_rs_idx}",
                            str(_rs_prompt),
                            str(_rs_response),
                        )

            # OI-004: Capture design snapshot from last REFINE round
            design_snapshot = None
            if refine_steps and not skip_arc_review:
                # Last review round's output is the most refined design context
                _last_refine = refine_steps[-1]
                if _last_refine.output:
                    design_snapshot = str(_last_refine.output)[:8000]
                    logger.info(
                        "Design snapshot captured from REFINE round %d (%d chars)",
                        len(refine_steps), len(design_snapshot),
                    )

            cost_err = _check_cost("refine")

            if _HAS_OTEL and not isinstance(_refine_span, _NoOpSpan):
                _refine_span.set_attribute("phase.cost", refine_cost)
                _refine_span.set_attribute("phase.rounds_completed", rounds_completed)
                _refine_span.set_attribute("phase.skipped", skip_arc_review)
            _active_phase_ctx.__exit__(None, None, None)
            _active_phase_ctx = None

            if cost_err:
                return cost_err

            # --- EMIT ---
            _active_phase_ctx = _tracer.start_as_current_span("ingestion.emit")
            _emit_span = _active_phase_ctx.__enter__()
            root_span.add_event("state.transition", {"phase": "emit"})

            progress("Emit")
            state.current_phase = IngestionPhase.EMIT

            _emit_project_root = Path(cfg.project_root) if cfg.project_root else None

            # OI-004: Attach design snapshot to parsed_plan so to_seed_dict() includes it
            if design_snapshot and parsed_plan is not None:
                parsed_plan.design_snapshot = design_snapshot

            emit_result = self._phase_emit(
                doc_path, route, complexity, output_dir,
                review_rounds, review_quality_tier, scope, context_files,
                warn_cost_usd, max_cost_usd,
                parsed_plan=parsed_plan,
                step_costs=step_costs,
                tracking_config=tracking_config,
                manifest_context=manifest_context,
                translation_quality=translation_quality,
                requirement_hints=requirements_hints_index,
                onboarding_metadata=onboarding_metadata,
                review_output=review_output,
                project_metadata=project_metadata,
                project_root=_emit_project_root,
                force_regenerate=cfg.force_regenerate,
            )

            # Emit deterministic traceability report for downstream auditing.
            # Reuse the same tasks derived in _phase_emit to ensure seed,
            # tracking, and traceability all agree on task decomposition.
            trace_payload = self._build_traceability_artifact(
                route=route,
                parsed_plan=parsed_plan,
                tasks=emit_result.tasks,
                quality=translation_quality,
                checksum_evidence=preflight_evidence.get("checksums", {}),
            )
            with _tracer.start_as_current_span("io.traceability.write") as _io_span:
                traceability_path = self._write_traceability_artifact(output_dir, trace_payload)
                if _HAS_OTEL and not isinstance(_io_span, _NoOpSpan):
                    _io_span.set_attribute("io.path", str(traceability_path))
            state.review_config_path = str(emit_result.config_path)
            if emit_result.context_seed_path is not None:
                state.context_seed_path = str(emit_result.context_seed_path)

            emit_output = f"Wrote {emit_result.config_path}"
            if emit_result.context_seed_path is not None:
                emit_output += f", {emit_result.context_seed_path}"
            emit_output += f", {traceability_path}"
            if emit_result.tracking_result:
                emit_output += f", {emit_result.tracking_result.get('state_file_count', 0)} tracking files"
            emit_step = StepResult(
                step_name="emit",
                output=emit_output,
            )
            steps.append(emit_step)

            if _HAS_OTEL and not isinstance(_emit_span, _NoOpSpan):
                _emit_span.set_attribute(
                    "phase.seed_path",
                    str(emit_result.context_seed_path) if emit_result.context_seed_path else "",
                )
                _emit_span.set_attribute("phase.config_path", str(emit_result.config_path))
            _active_phase_ctx.__exit__(None, None, None)
            _active_phase_ctx = None

            # --- DONE ---
            state.current_phase = IngestionPhase.COMPLETED

            # Save final state
            _save_state()

            # --- Kaizen diagnostic report (REQ-KPI-1xx, 3xx) ---
            _diag_phase_map: Dict[str, PhaseDiagnostic] = {}
            for _s in steps:
                _phase_name = _s.step_name.split(":")[0]  # strip sub-tags like "assess:quality-override"
                if _phase_name in _diag_phase_map:
                    # Accumulate cost/tokens for multi-step phases (e.g. refine)
                    existing = _diag_phase_map[_phase_name]
                    existing.time_ms += _s.time_ms
                    existing.input_tokens += _s.input_tokens
                    existing.output_tokens += _s.output_tokens
                    existing.cost_usd += _s.cost
                    if _s.error:
                        existing.success = False
                else:
                    _diag_phase_map[_phase_name] = PhaseDiagnostic(
                        phase=_phase_name,
                        success=_s.error is None,
                        time_ms=_s.time_ms,
                        input_tokens=_s.input_tokens,
                        output_tokens=_s.output_tokens,
                        cost_usd=_s.cost,
                        code_extraction_fallback=_s.metadata.get(
                            "code_extraction_fallback", False,
                        ),
                    )

            # Attach quality signals to phase diagnostics
            if "parse" in _diag_phase_map and parsed_plan is not None:
                _diag_phase_map["parse"].quality_signals = compute_parse_quality(
                    parsed_plan.features,
                    parsed_plan.dependency_graph,
                    parsed_plan.mentioned_files,
                )
            if "assess" in _diag_phase_map and complexity is not None:
                _dims = [
                    complexity.feature_count, complexity.cross_file_deps,
                    complexity.api_surface, complexity.test_complexity,
                    complexity.integration_depth, complexity.domain_novelty,
                    complexity.ambiguity,
                ]
                _diag_phase_map["assess"].quality_signals = compute_assess_quality(
                    complexity.composite, route.value, threshold, _dims,
                )
            if "refine" in _diag_phase_map:
                _diag_phase_map["refine"].quality_signals = compute_refine_quality(
                    review_output,
                )

            # Seed quality (artisan only — read seed JSON back)
            _seed_score = 0.0
            _seed_warnings: List[str] = []
            if emit_result.context_seed_path and emit_result.context_seed_path.exists():
                try:
                    _seed_dict = json.loads(
                        emit_result.context_seed_path.read_text(encoding="utf-8")
                    )
                    _density = compute_task_density(_seed_dict.get("tasks", []))
                    _seed_score, _seed_warnings = compute_seed_quality(
                        _seed_dict, task_density=_density,
                    )
                except (OSError, json.JSONDecodeError) as _seed_err:
                    logger.debug("Kaizen: seed quality read failed: %s", _seed_err)

            # Task density
            _task_density = compute_task_density(emit_result.tasks)

            _plan_checksum = sha256(plan_text.encode()).hexdigest()[:16]
            _diag = build_diagnostic(
                run_timestamp=started_at.isoformat(),
                plan_source=str(plan_path),
                plan_checksum=_plan_checksum,
                route=route.value,
                overall_success=True,
                phase_diagnostics=_diag_phase_map,
                seed_quality_score=_seed_score,
                quality_warnings=_seed_warnings,
                task_density=_task_density,
                enrichment=emit_result.enrichment_diagnostic,
            )
            persist_diagnostic(_diag, output_dir)

            completed_at = datetime.now(timezone.utc)
            total_ms = int((completed_at - started_at).total_seconds() * 1000)

            output: Dict[str, Any] = {
                "route": route.value,
                "plan_document_path": str(doc_path),
                "review_config_path": str(emit_result.config_path),
                "complexity_score": complexity.composite,
                "refine_rounds_completed": rounds_completed,
                "traceability_path": str(traceability_path),
                "translation_quality": {
                    "requirements_coverage_percent": translation_quality.get(
                        "requirements_coverage_percent", 100.0
                    ),
                    "artifact_mapping_percent": translation_quality.get(
                        "artifact_mapping_percent", 100.0
                    ),
                    "conflict_count": translation_quality.get("conflict_count", 0),
                },
            }
            if emit_result.context_seed_path is not None:
                output["context_seed_path"] = str(emit_result.context_seed_path)
            if emit_result.tracking_result:
                output["task_tracking"] = emit_result.tracking_result

            # OTel: finalize root span on success
            if _HAS_OTEL and not isinstance(root_span, _NoOpSpan):
                root_span.set_attribute("workflow.route", route.value)
                root_span.set_attribute("workflow.total_cost", state.total_cost)
                root_span.set_status(_StatusCode.OK)

            return WorkflowResult(
                workflow_id=self.metadata.workflow_id,
                success=True,
                output=output,
                metrics=WorkflowMetrics(
                    total_time_ms=total_ms,
                    input_tokens=sum(s.input_tokens for s in steps),
                    output_tokens=sum(s.output_tokens for s in steps),
                    total_cost=state.total_cost,
                    step_count=len(steps),
                ),
                steps=steps,
                started_at=started_at,
                completed_at=completed_at,
            )

        except Exception as exc:
            if _HAS_OTEL and not isinstance(root_span, _NoOpSpan):
                root_span.record_exception(exc)
                root_span.set_status(_StatusCode.ERROR, str(exc))
            logger.error("Plan ingestion failed: %s", exc, exc_info=True)
            return _fail(str(exc))
        finally:
            if _active_phase_ctx is not None:
                _active_phase_ctx.__exit__(None, None, None)
            _root_span_ctx.__exit__(None, None, None)
