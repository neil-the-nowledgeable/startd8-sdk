"""
Spec builder for the implementation engine.

Produces an 8-section implementation specification from a task description
and context.
"""

import ast
import json
import os
import re
import uuid
from typing import Any, Dict, List, Optional

from ..logging_config import get_logger
from ..costs.pricing import PricingService
from .budget import (
    ARCH_CONTEXT_MAX_CHARS,
    PLAN_CONTEXT_MAX_CHARS,
    SPEC_CONTEXT_BUDGET_CHARS,
    TOTAL_SPEC_BUDGET_TOKENS,
    TRUNCATION_MARKER,
    enforce_prompt_budget,
    estimate_tokens,
    truncate_arch_context,
    truncate_with_marker,
)
from .models import SpecResult
from .parsers import parse_list_section, parse_section_content
from .prompts import format_prompt, get_template


__all__ = [
    "build_spec",
    "build_spec_prompt",
    "build_spec_context_section",
    "build_spec_plan_section",
    "build_spec_arch_section",
    "build_spec_objectives_section",
    "build_spec_conventions_section",
    "build_constraint_block",
    "extract_spec_constraints",
    "format_context_value",
    "extract_prompt_security_features",
    "_sanitize_csharp_code_examples",
    "_detect_sql_interpolation_in_examples",
]

logger = get_logger(__name__)

# CR-M3: Lazy initialization — avoids import-time side effects
_pricing: Optional["PricingService"] = None


def _get_pricing() -> "PricingService":
    """Return the module-level PricingService, creating it lazily."""
    global _pricing
    if _pricing is None:
        _pricing = PricingService()
    return _pricing


# ---------------------------------------------------------------------------
# Section builders (composable, independently callable)
# ---------------------------------------------------------------------------


def safe_json_dumps(obj: Any, indent: int = 2) -> str:
    """JSON dumps that handles non-serializable objects gracefully."""
    def default(o: Any) -> Any:
        # CR-M1: Check model_dump() (Pydantic v2) before dict() (v1 legacy).
        # hasattr(o, "dict") is True on all objects in Python 3, so checking
        # it first would shadow the Pydantic v2 method.
        if hasattr(o, "model_dump"):
            return o.model_dump()
        if hasattr(o, "dict") and callable(o.dict):
            return o.dict()
        return str(o)
    return json.dumps(obj, indent=indent, default=default)


def format_context_value(value: Any) -> str:
    """Format a context value as a bullet list or string."""
    if isinstance(value, list):
        return "\n".join(f"- {item}" for item in value)
    if isinstance(value, dict):
        return "\n".join(f"- **{k}**: {v}" for k, v in value.items())
    return str(value)



def build_spec_context_section(
    context: Dict[str, Any],
    output_format: Optional[str],
    target_files: Optional[List[str]],
) -> str:
    """Build general context section. File manifest + remaining keys."""
    parts: List[str] = []
    if target_files and len(target_files) > 1:
        file_manifest = "\n".join(f"  - `{f}`" for f in target_files)
        try:
            parts.append(format_prompt(
                "required_output_files", file_manifest=file_manifest,
            ))
        except KeyError:
            parts.append(
                f"## Required Output Files\n{file_manifest}\n"
            )

    # REQ-SPEC-102: Context budget management.
    # If context is massive, we should avoid dumping everything.
    # However, for now, we just ensure it doesn't crash.
    context_str = (
        safe_json_dumps(context) if context else "No additional context provided."
    )
    if output_format:
        context_str += f"\n\nExpected Output Format:\n{output_format}"

    parts.append(f"## Context\n{context_str}")
    return "\n\n".join(parts)


def _format_lead_prompt(template_name: str, fallback: str, **kwargs: Any) -> str:
    """Format prompt from consolidated YAML; use fallback when YAML missing."""
    try:
        template = get_template(template_name)
        return template.format(**kwargs)
    except (FileNotFoundError, KeyError, ImportError):
        try:
            return fallback.format(**kwargs)
        except KeyError:
            return fallback


# Legacy fallback constants — kept as empty strings for backward compatibility.
# All fallbacks are now in prompts/__init__.py:_FALLBACK_TEMPLATES (R0-3).
# _format_lead_prompt() calls get_template() first, which loads from YAML
# or _FALLBACK_TEMPLATES. These constants are never reached.
_PLAN_CONTEXT_EDIT_FRAMING_FALLBACK = ""
_PLAN_CONTEXT_CREATE_FRAMING_FALLBACK = ""
_ARCH_CONTEXT_EDIT_FRAMING_FALLBACK = ""
_SPEC_EDIT_PREAMBLE_BASE_FALLBACK = ""
_SPEC_EDIT_QUANTITATIVE_FALLBACK = ""
_SPEC_CREATE_PREAMBLE_FALLBACK = ""


def _fence_untrusted(content: str, content_type: str) -> str:
    """Wrap untrusted prompt content in a DATA-not-instructions fence (FR-A1/A1a).

    Lazy import of ``wrap_user_content`` keeps the ``implementation_engine →
    contractors`` layering one-directional (contractors depends on
    implementation_engine, not vice versa) and avoids an import cycle.

    The fence is idempotent: content already wrapped on the PIPELINE-mode path
    (``context_resolution`` wraps before injection) is returned unchanged, so
    fencing here only adds the boundary for the STANDALONE path where it was
    previously missing — without double-wrapping.
    """
    if not content or not content.strip():
        return content
    from ..contractors.context_formatters import wrap_user_content
    from ..security import normalize_untrusted_text

    # Normalize (strip null/control chars, repair UTF-8, bound size) before
    # fencing (FR-A2) — removes a fence-evasion vector and hands the fence clean,
    # bounded text. Idempotent for already-fenced PIPELINE content.
    return wrap_user_content(normalize_untrusted_text(content), content_type)


def build_spec_plan_section(
    plan_ctx: Optional[str],
    is_edit: bool = False,
) -> str:
    """Build plan context section with truncation and framing."""
    if not plan_ctx or not plan_ctx.strip():
        return ""
    if is_edit:
        framing = _format_lead_prompt(
            "plan_context_edit_framing",
            _PLAN_CONTEXT_EDIT_FRAMING_FALLBACK,
        ).rstrip() + "\n\n"
    else:
        framing = _format_lead_prompt(
            "plan_context_create_framing",
            _PLAN_CONTEXT_CREATE_FRAMING_FALLBACK,
        ).rstrip() + "\n\n"
    plan_budget = PLAN_CONTEXT_MAX_CHARS - len(framing)
    truncated = truncate_with_marker(plan_ctx.strip(), plan_budget, TRUNCATION_MARKER)
    if len(truncated) < len(plan_ctx.strip()):
        logger.info(
            "Spec prompt: plan context truncated from %d to %d chars",
            len(plan_ctx), len(truncated),
        )
    return f"## Plan Context\n{framing}{_fence_untrusted(truncated, 'plan_context')}"


def build_spec_arch_section(arch_ctx: Any, is_edit: bool = False) -> str:
    """Build architectural context section with truncation and framing."""
    if not arch_ctx:
        return ""
    truncated = truncate_arch_context(arch_ctx, ARCH_CONTEXT_MAX_CHARS)
    orig_len = len(safe_json_dumps(arch_ctx) if isinstance(arch_ctx, (dict, list)) else str(arch_ctx))
    if len(truncated) < orig_len:
        logger.info(
            "Spec prompt: arch context truncated from %d to %d chars",
            orig_len, len(truncated),
        )
    fenced = _fence_untrusted(truncated, "architectural_context")
    if is_edit:
        framing = _format_lead_prompt(
            "arch_context_edit_framing",
            _ARCH_CONTEXT_EDIT_FRAMING_FALLBACK,
        ).rstrip() + "\n\n"
        return f"## Project Architecture\n{framing}{fenced}"
    return f"## Project Architecture\n{fenced}"


def build_spec_objectives_section(project_obj: Any) -> str:
    """Build project objectives section."""
    if not project_obj:
        return ""
    fenced = _fence_untrusted(format_context_value(project_obj), "project_objectives")
    return f"## Project Objectives\n{fenced}"


def build_spec_conventions_section(sem_conv: Any) -> str:
    """Build semantic conventions section."""
    if not sem_conv:
        return ""
    fenced = _fence_untrusted(format_context_value(sem_conv), "semantic_conventions")
    return f"## Semantic Conventions\n{fenced}"


def _build_exemplar_section(context: Dict[str, Any]) -> str:
    """Build the exemplar reference section (REQ-PEP-101).

    Injects a verified reference from a prior successful run when available.
    The exemplar is provided in ``context["exemplar"]`` by the Prime Contractor
    after calling ``ExemplarRegistry.find_best_match()``.

    Returns empty string if no exemplar is available.
    """
    from startd8.implementation_engine.budget import EXEMPLAR_BUDGET_CHARS

    exemplar = context.get("exemplar")
    if not exemplar or not isinstance(exemplar, dict):
        return ""

    run_id = exemplar.get("source_run_id", "unknown")
    score = exemplar.get("scores", {})
    if isinstance(score, dict):
        dq = score.get("disk_quality_score", 1.0)
    else:
        dq = getattr(score, "disk_quality_score", 1.0)
    fingerprint = exemplar.get("fingerprint", "")
    match_type = exemplar.get("match_type", "exact")

    spec_excerpt = exemplar.get("spec_excerpt", "")
    code_excerpt = exemplar.get("code_excerpt", "")

    if not spec_excerpt and not code_excerpt:
        code_summary = exemplar.get("code_summary", "")
        if code_summary:
            code_excerpt = code_summary

    if not spec_excerpt and not code_excerpt:
        return ""

    try:
        _header = format_prompt(
            "exemplar_reference",
            run_id=run_id, score=f"{dq:.2f}", fingerprint=fingerprint,
        )
    except KeyError:
        _header = f"## Verified Reference (from {run_id}, score: {dq:.2f})\n"
    parts = [_header]

    if match_type == "partial":
        parts.append(
            "\n**Note:** This is a partial match (same language/type/archetype, "
            "different transport). Adapt transport-specific patterns."
        )

    # Budget: truncate code before spec (spec is more valuable as pattern guide)
    remaining = max(0, EXEMPLAR_BUDGET_CHARS - sum(len(p) for p in parts) - 50)
    spec_budget = min(len(spec_excerpt), remaining // 2)
    code_budget = max(0, remaining - spec_budget)

    if spec_excerpt:
        truncated_spec = spec_excerpt[:spec_budget]
        if len(spec_excerpt) > spec_budget:
            truncated_spec = truncated_spec.rsplit("\n", 1)[0] + "\n... [truncated]"
        parts.append(f"\n### Spec that produced it:\n{truncated_spec}")

    if code_excerpt:
        truncated_code = code_excerpt[:code_budget]
        if len(code_excerpt) > code_budget:
            truncated_code = truncated_code.rsplit("\n", 1)[0] + "\n... [truncated]"
        parts.append(f"\n### Code that was validated:\n```\n{truncated_code}\n```")

    return "\n".join(parts)


def _build_available_imports_section(context: Dict[str, Any]) -> str:
    """Build the available imports section from task dependencies.

    Strips version pins and formats as a bullet list.  Handles both Python
    (``grpcio==1.76.0``) and Go (``github.com/grpc/grpc-go v1.56.0``)
    dependency formats.  Returns empty string when no dependencies are present.
    """
    deps = context.get("runtime_dependencies", [])
    if not deps:
        return ""

    lang_profile = context.get("language_profile")

    package_lines = []
    for dep in sorted(deps):
        if lang_profile is not None and hasattr(lang_profile, "strip_dependency_version"):
            pkg = lang_profile.strip_dependency_version(dep)
        else:
            # Fallback: Python-style version stripping
            pkg = dep
            for sep in ("==", ">=", "<=", "~=", "!=", "<", ">"):
                pkg = pkg.split(sep)[0]
            pkg = pkg.strip()
        if pkg:
            package_lines.append(f"- {pkg}")
    if not package_lines:
        return ""
    packages_str = "\n".join(package_lines)

    if lang_profile is not None and hasattr(lang_profile, "get_import_syntax_guidance"):
        import_syntax = lang_profile.get_import_syntax_guidance()
    else:
        import_syntax = (
            "Use ONLY these packages plus Python stdlib. Every non-stdlib symbol you\n"
            "reference MUST have a corresponding import statement at the top of the file.\n"
            "Do NOT import packages not listed above.\n"
        )

    # REQ-PE-300: Pass import_syntax from language profile into YAML template
    return format_prompt(
        "available_imports",
        available_packages=packages_str,
        import_syntax=import_syntax,
    )



def _build_framework_imports_section(
    context: Dict[str, Any],
    task_description: str = "",
) -> str:
    """Build framework-specific import template section.

    Uses ``framework_imports.detect_frameworks()`` to identify frameworks
    from runtime_dependencies and task description, then renders canonical
    import patterns via ``get_import_preamble()``.

    Returns empty string when no frameworks are detected.
    """
    deps = context.get("runtime_dependencies", [])
    target_files = context.get("target_files", [])

    try:
        from .framework_imports import detect_frameworks, get_import_preamble
    except ImportError:
        return ""

    lang_profile = context.get("language_profile")
    frameworks = detect_frameworks(
        task_description=task_description,
        target_files=target_files,
        dependencies=deps,
        language_profile=lang_profile,
    )
    if not frameworks:
        return ""
    return get_import_preamble(frameworks, dependencies=deps, language_profile=lang_profile)


def _build_sibling_imports_section(context: Dict[str, Any]) -> str:
    """Extract imports from existing sibling files in the same directory.

    When generating a new file, knowing what its neighbors import
    provides project-specific framework context that no hardcoded
    template can match (e.g. the exact proto module names, the
    project's logging pattern, the OTel setup convention).

    REQ-PE-201: Supports non-Python languages via regex-based extraction
    when a language profile is available. Falls back to Python AST parsing.

    Returns empty string if no siblings with imports are found.
    """
    existing_files = context.get("existing_files_content") or context.get("existing_files", {})
    if not existing_files:
        return ""

    target_files = context.get("target_files", [])
    if not target_files:
        return ""

    target_dir = os.path.dirname(target_files[0]) if target_files else ""

    # REQ-PE-201: Resolve language profile for extension filtering and fence label
    lang_profile = context.get("language_profile")
    if lang_profile is not None:
        source_exts = set(getattr(lang_profile, "source_extensions", [".py"]))
        fence_lang = getattr(lang_profile, "language_id", "python")
    else:
        source_exts = {".py"}
        fence_lang = "python"

    sibling_imports: set[str] = set()
    for path, content in existing_files.items():
        if not isinstance(content, str):
            continue
        ext = os.path.splitext(path)[1].lower()
        if ext not in source_exts:
            continue
        if os.path.dirname(path) != target_dir:
            continue

        if ext == ".py":
            # Python: AST-based extraction (existing behavior)
            try:
                tree = ast.parse(content)
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    try:
                        sibling_imports.add(ast.unparse(node))
                    except (AttributeError, ValueError):
                        pass
        else:
            # Non-Python: regex-based import line extraction
            if lang_profile is not None and hasattr(lang_profile, "extract_import_lines"):
                sibling_imports.update(lang_profile.extract_import_lines(content))
            else:
                # Generic fallback: grab lines that look like imports
                for line in content.splitlines():
                    stripped = line.strip()
                    if stripped.startswith("import ") or stripped.startswith("from "):
                        sibling_imports.add(stripped)

    if not sibling_imports:
        return ""

    import_list = "\n".join(sorted(sibling_imports))
    try:
        return format_prompt(
            "sibling_imports",
            fence_lang=fence_lang,
            import_list=import_list,
        )
    except KeyError:
        return f"## Sibling Imports\n```{fence_lang}\n{import_list}\n```"


def _build_local_modules_section(context: Dict[str, Any]) -> str:
    """List sibling module names the LLM can import from.

    Unlike ``_build_sibling_imports_section`` which shows *what* siblings
    import, this section tells the LLM *which local modules exist* so it
    can write ``from logger import getJSONLogger`` instead of hallucinating
    a qualified cross-service import like ``from emailservice.logger import X``.

    Returns empty string if no sibling source files are found.
    """
    existing_files = context.get("existing_files_content") or context.get("existing_files", {})
    if not existing_files:
        return ""

    target_files = context.get("target_files", [])
    if not target_files:
        return ""

    target_dir = os.path.dirname(target_files[0]) if target_files else ""

    # Resolve source extensions from language profile
    lang_profile = context.get("language_profile")
    if lang_profile is not None:
        source_exts = set(getattr(lang_profile, "source_extensions", [".py"]))
    else:
        source_exts = {".py"}

    # Collect sibling file stems (module names) in the same directory,
    # excluding the target file itself
    target_stems = {os.path.splitext(os.path.basename(t))[0] for t in target_files}
    local_modules: dict[str, str] = {}  # stem → basename
    for path in existing_files:
        ext = os.path.splitext(path)[1].lower()
        if ext not in source_exts:
            continue
        if os.path.dirname(path) != target_dir:
            continue
        stem = os.path.splitext(os.path.basename(path))[0]
        if stem in target_stems or stem == "__init__":
            continue
        local_modules[stem] = os.path.basename(path)

    if not local_modules:
        return ""

    module_list = "\n".join(
        f"  - `{basename}` → import as `from {stem} import ...`"
        for stem, basename in sorted(local_modules.items())
    )
    try:
        return format_prompt("local_modules", module_list=module_list)
    except KeyError:
        return f"## Available Local Modules\n{module_list}"


def _build_dependency_imports_section(context: Dict[str, Any]) -> str:
    """Build a section listing importable modules from dependency tasks.

    Reads ``dependency_imports`` from *context* (populated by
    ``PrimeContractorWorkflow._collect_dependency_imports``) and renders
    a Markdown section so the LLM knows which modules to import from
    its upstream dependencies.

    Returns empty string when no dependency imports are present.
    """
    dep_imports = context.pop("dependency_imports", None)
    if not dep_imports:
        return ""

    lines = [
        "## Dependency Task Imports",
        "",
        "Your dependency tasks produce these modules — import them as needed:",
        "",
    ]
    for dep_id, info in dep_imports.items():
        target_desc = ", ".join(info.get("target_files", [])) or "unknown"
        lines.append(f"From {dep_id} ({target_desc}):")
        for mod in info.get("modules", []):
            lines.append(f"  - `{mod}`")
        lines.append("")

    return "\n".join(lines)


def _build_import_conventions_section(context: Dict[str, Any]) -> str:
    """REQ-SV2-1300: Import conventions for flat module layouts.

    When the target directory has sibling ``.py`` files but no ``__init__.py``,
    the project uses flat imports (``import demo_pb2``) not package-style
    imports (``from emailservice import demo_pb2``). Injecting this guidance
    eliminates the L1.2 namespace-as-package defect (60% of runs).

    REQ-PE-401: Returns empty string for non-Python tasks (Go/Java/Node.js
    have different module systems covered by their coding_standards).

    Returns empty string when the layout is package-style or unknown.
    """
    # REQ-PE-401: Python-only — non-Python import conventions are covered
    # by the language profile's coding_standards and get_import_syntax_guidance()
    lang_profile = context.get("language_profile")
    if lang_profile is not None and getattr(lang_profile, "language_id", "python") != "python":
        return ""

    existing_files = context.get("existing_files_content") or context.get("existing_files", {})
    target_files = context.get("target_files", [])
    if not existing_files or not target_files:
        return ""

    target_dir = os.path.dirname(target_files[0]) if target_files else ""

    # Check for sibling .py files and __init__.py presence
    has_sibling_py = False
    has_init = False
    for path in existing_files:
        if os.path.dirname(path) != target_dir:
            continue
        basename = os.path.basename(path)
        if basename == "__init__.py":
            has_init = True
            break
        if basename.endswith(".py"):
            has_sibling_py = True

    if has_init or not has_sibling_py:
        return ""

    # Collect sibling module names for the example
    sibling_names = sorted({
        os.path.splitext(os.path.basename(p))[0]
        for p in existing_files
        if os.path.dirname(p) == target_dir
        and p.endswith(".py")
        and os.path.basename(p) != "__init__.py"
    })
    dir_name = os.path.basename(target_dir) if target_dir else "this directory"

    examples = "\n".join(f"  import {name}" for name in sibling_names[:4])
    bad_examples = "\n".join(
        f"  from {dir_name} import {name}" for name in sibling_names[:2]
    )

    return (
        "## Import Conventions (flat module layout)\n\n"
        f"This project uses flat module layout — `{dir_name}/` has NO `__init__.py`.\n"
        "Import sibling files directly:\n\n"
        "```python\n"
        "# Correct:\n"
        f"{examples}\n"
        "# WRONG — will fail at runtime:\n"
        f"{bad_examples}\n"
        "```\n"
    )


def _build_security_guidance_section(context: Dict[str, Any]) -> str:
    """Build database security guidance with language-specific parameterized query examples.

    When the context includes a security_contract with client_libraries matching
    known database libraries (Npgsql, Spanner, SqlClient), inject concrete
    parameterized query examples for the target language.

    Returns empty string when no database client libraries are detected.
    """
    security_contract = context.get("security_contract") or {}
    client_libraries = security_contract.get("client_libraries", [])

    if client_libraries:
        lines: List[str] = ["## Database Security Guidance — MANDATORY OVERRIDE\n"]
        lines.append(
            "Use ONLY parameterized queries. NEVER use string interpolation for SQL.\n"
            "This overrides any reference implementation patterns — always parameterize.\n"
        )

        matched = False
        for cl in client_libraries:
            if not isinstance(cl, str):
                continue
            cl_lower = cl.lower()
            if "npgsql" in cl_lower:
                lines.append(
                    "  - Use `NpgsqlCommand` with `@param` syntax: "
                    '`cmd.Parameters.AddWithValue("@id", id)`'
                )
                matched = True
            elif "spanner" in cl_lower:
                lines.append(
                    "  - Use `SpannerCommand` with `SpannerDbType` params: "
                    '`{ "id", SpannerDbType.String, id }`'
                )
                matched = True
            elif "sqlclient" in cl_lower or "microsoft.data" in cl_lower:
                lines.append(
                    "  - Use `SqlCommand` with `@param` syntax: "
                    '`cmd.Parameters.AddWithValue("@id", id)`'
                )
                matched = True

        if matched:
            return "\n".join(lines)

    # REQ-PI-CS-201: detected_databases fallback with database-specific examples
    detected_databases = context.get("detected_databases")
    if detected_databases and isinstance(detected_databases, list):
        db_lines: List[str] = [
            "## Database Security Guidance (from detected databases)\n",
            "Use ONLY parameterized queries. NEVER use string interpolation "
            "(`$\"...\"`) or string concatenation to build SQL.\n",
        ]
        _DB_EXAMPLES: Dict[str, str] = {
            "postgresql": (
                "  - **PostgreSQL/AlloyDB (Npgsql)**: "
                '`cmd.Parameters.AddWithValue("@id", id)`'
            ),
            "alloydb": (
                "  - **AlloyDB (Npgsql)**: "
                '`cmd.Parameters.AddWithValue("@id", id)`'
            ),
            "spanner": (
                "  - **Cloud Spanner**: Use `SpannerParameterCollection` — "
                '`new SpannerParameter("id", SpannerDbType.String, id)`'
            ),
            "sqlserver": (
                "  - **SQL Server**: "
                '`cmd.Parameters.AddWithValue("@id", id)`'
            ),
        }
        added = False
        for db in detected_databases:
            db_lower = db.lower()
            for key, example in _DB_EXAMPLES.items():
                if key in db_lower:
                    db_lines.append(example)
                    added = True
                    break
        if added:
            return "\n".join(db_lines)

    # Fallback: detect database surface from task description and target files
    # even without explicit security_contract (pre-generation Anzen gate).
    # Prevents design-doc-poisoned SQL patterns from reaching code generation.
    task_desc = context.get("task_description", "")
    feature_name = context.get("feature_name", "")
    target_files = context.get("target_files", [])
    target_file = context.get("target_file", "")
    combined = f"{task_desc} {feature_name} {target_file} {' '.join(target_files)}".lower()
    _DB_KEYWORDS = (
        "alloydb", "postgres", "npgsql", "spanner", "mysql", "sqlite",
        "database", "sql", "query", "cart_store", "cartstore",
        "repository", "dal", "data_access",
    )
    if any(kw in combined for kw in _DB_KEYWORDS):
        return "\n".join([
            "## Database Security Guidance (auto-detected) — MANDATORY OVERRIDE\n",
            "CRITICAL: Use ONLY parameterized queries for ALL database access.",
            "NEVER use string interpolation ($\"...\"), string concatenation, "
            "or String.Format() to build SQL queries.",
            "",
            "**This overrides any reference implementation patterns.** Even if the",
            "reference code uses string interpolation for SQL, you MUST use",
            "parameterized queries instead. Do NOT document SQL injection as",
            "\"intentional\" or \"matching reference\" — always parameterize.",
            "",
            "  - C#/Npgsql: `cmd.Parameters.AddWithValue(\"@id\", id)`",
            "  - C#/Spanner: `new SpannerParameterCollection { { \"id\", SpannerDbType.String, id } }`",
            "  - Java: `PreparedStatement` with `?` placeholders",
            "  - Go: `spanner.Statement{SQL: \"...@param...\", Params: map}`",
            "  - Python: `cursor.execute(\"...%s...\", (param,))`",
            "  - Node.js: `client.query(\"...$1...\", [param])`",
        ])

    return ""


def _build_anti_pattern_section(context: Dict[str, Any], task_description: str) -> str:
    """REQ-SV2-1400: Anti-pattern guidance for environment variable handling.

    When a task involves environment configuration, inject guidance to prevent
    the L6 discarded-return pattern (``os.getenv("KEY")`` as a bare expression
    statement). This defect appears in 50% of runs and never self-corrects.

    REQ-PE-202: Returns empty string for non-Python tasks (Go compiler catches
    unused values, Java has no ``os.getenv`` bare expression pattern).

    Returns empty string when the task doesn't involve env vars.
    """
    # REQ-PE-202: Skip for non-Python — anti-pattern examples are Python-specific
    lang_profile = context.get("language_profile")
    if lang_profile is not None and getattr(lang_profile, "language_id", "python") != "python":
        return ""

    # Detect env-var relevance from task description and dependencies
    desc_lower = task_description.lower()
    env_signals = (
        "environment variable", "env var", "os.getenv", "os.environ",
        ".env", "config", "configuration", "GCP_PROJECT",
        "ALLOYDB", "SECRET_MANAGER",
    )
    deps = context.get("runtime_dependencies", [])
    deps_str = " ".join(deps).lower() if deps else ""

    has_env_signal = any(sig.lower() in desc_lower or sig.lower() in deps_str for sig in env_signals)
    if not has_env_signal:
        # Also check existing files for os.getenv/os.environ usage
        existing_files = context.get("existing_files_content") or context.get("existing_files", {})
        for content in existing_files.values():
            if isinstance(content, str) and ("os.getenv" in content or "os.environ" in content):
                has_env_signal = True
                break

    if not has_env_signal:
        return ""

    return (
        "## Anti-Patterns to Avoid\n\n"
        "- Do NOT write `os.getenv(\"KEY\")` as a bare expression statement. "
        "Always assign the result:\n"
        "  ```python\n"
        "  # Correct:\n"
        "  project_id = os.getenv(\"GCP_PROJECT_ID\", \"\")\n"
        "  # WRONG — computes a value and silently discards it:\n"
        "  os.getenv(\"GCP_PROJECT_ID\")\n"
        "  ```\n"
        "- Do NOT write `os.environ.get(\"KEY\")` as a bare statement.\n"
        "- Do NOT write `os.path.join(...)` or `os.path.exists(...)` without using the return value.\n"
    )


def _sanitize_csharp_code_examples(text: str) -> str:
    """REQ-PI-CS-100: Transform Console.WriteLine → ILogger in C# code examples.

    The LLM follows code examples more strongly than structural rules.
    Transforming problematic patterns before the LLM sees them prevents
    Console.WriteLine from propagating into generated code.
    """
    # Console.Error.WriteLine(...) → _logger.LogError(...)
    text = re.sub(
        r'Console\.Error\.WriteLine\s*\(([^)]*)\)',
        r'_logger.LogError(\1)',
        text,
    )
    # Console.WriteLine(...) → _logger.LogInformation(...)
    text = re.sub(
        r'Console\.WriteLine\s*\(([^)]*)\)',
        r'_logger.LogInformation(\1)',
        text,
    )
    return text


def _detect_sql_interpolation_in_examples(text: str) -> str:
    """REQ-PI-CS-200: Detect SQL string interpolation in design doc examples.

    Scans for SQL keywords combined with C# string interpolation ($"...").
    Returns a WARNING block to append to design_document, or empty string.
    """
    _SQL_KW = re.compile(
        r'\b(SELECT|INSERT|UPDATE|DELETE|CREATE|ALTER|DROP|MERGE)\b',
        re.IGNORECASE,
    )
    # C# interpolated string: $"..."
    _INTERPOLATION = re.compile(r'\$"[^"]*\{[^}]+\}[^"]*"')

    flagged_lines: list[str] = []
    for line in text.splitlines():
        if _SQL_KW.search(line) and _INTERPOLATION.search(line):
            flagged_lines.append(line.strip())

    if not flagged_lines:
        return ""

    return (
        "\n\n## ⚠ WARNING: SQL Injection Risk in Design Examples\n\n"
        "The design document above contains string-interpolated SQL.\n"
        "**DO NOT copy these patterns.** Use parameterized queries instead.\n\n"
        "Flagged lines:\n"
        + "\n".join(f"  - `{line}`" for line in flagged_lines[:5])
        + "\n"
    )


def extract_spec_constraints(spec_text: str) -> List[Dict[str, str]]:
    """Extract MUST and MUST NOT assertions from a spec document.

    Scans for patterns like:
    - ``MUST ...`` / ``must ...``
    - ``MUST NOT ...`` / ``Do NOT ...`` / ``MUST not ...``
    - ``Required: ...``
    - ``Constraint: ...``

    Returns:
        List of dicts: ``[{"type": "MUST"|"MUST_NOT", "text": "...", "source": "spec"}]``
    """
    import re

    constraints: List[Dict[str, str]] = []
    seen_texts: set = set()

    # Pattern 1: MUST NOT / must not / MUST not / Do NOT
    for match in re.finditer(
        r"(?:MUST\s+NOT|must\s+not|Do\s+NOT|do\s+not|SHOULD\s+NOT)\s+(.+?)(?:\.|$)",
        spec_text,
        re.MULTILINE,
    ):
        text = match.group(1).strip()
        if text and text not in seen_texts:
            seen_texts.add(text)
            constraints.append({"type": "MUST_NOT", "text": text, "source": "spec"})

    # Pattern 2: MUST / Required
    for match in re.finditer(
        r"(?:MUST|must|Required:?|REQUIRED:?)\s+(.+?)(?:\.|$)",
        spec_text,
        re.MULTILINE,
    ):
        text = match.group(1).strip()
        # Skip if already captured as MUST_NOT
        if text and text not in seen_texts and not text.upper().startswith("NOT"):
            seen_texts.add(text)
            constraints.append({"type": "MUST", "text": text, "source": "spec"})

    # Pattern 3: Constraint: ... (explicit constraint labels)
    for match in re.finditer(
        r"Constraint:?\s+(.+?)(?:\.|$)",
        spec_text,
        re.MULTILINE | re.IGNORECASE,
    ):
        text = match.group(1).strip()
        if text and text not in seen_texts:
            seen_texts.add(text)
            ctype = "MUST_NOT" if "not" in text.lower()[:10] else "MUST"
            constraints.append({"type": ctype, "text": text, "source": "spec"})

    return constraints


def build_constraint_block(context: Dict[str, Any]) -> tuple[str, List[Dict[str, str]]]:
    """Build a structured constraint block for the spec AND a machine-readable
    list for the review phase.

    Returns ``(spec_section_text, constraint_list)`` where
    ``constraint_list`` is stored in the task context for review.

    Sources checked (in order):
    - ``critical_parameters``: always MUST constraints
    - ``domain_constraints``: MUST_NOT if starts with "Do not"/"Never"
    - ``prompt_constraints``: MUST_NOT if starts with "Do not"/"Never"
    """
    constraints: List[Dict[str, str]] = []

    for param in context.get("critical_parameters", []):
        if isinstance(param, str) and param.strip():
            constraints.append({
                "type": "MUST",
                "text": param.strip(),
                "source": "critical_parameters",
            })

    for dc in context.get("domain_constraints", []):
        if isinstance(dc, str) and dc.strip():
            text = dc.strip()
            ctype = "MUST_NOT" if text.lower().startswith(("do not", "never")) else "MUST"
            constraints.append({"type": ctype, "text": text, "source": "domain_constraints"})

    for pc in context.get("prompt_constraints", []):
        if isinstance(pc, str) and pc.strip():
            text = pc.strip()
            ctype = "MUST_NOT" if text.lower().startswith(("do not", "never")) else "MUST"
            constraints.append({"type": ctype, "text": text, "source": "prompt_constraints"})

    if not constraints:
        return "", []

    lines = ["## Constraints\n"]
    for i, c in enumerate(constraints, 1):
        lines.append(f"{i}. **[{c['type']}]** {c['text']}")
    spec_text = "\n".join(lines)

    return spec_text, constraints


def _select_template_key(context: Dict[str, Any], override: Optional[str] = None) -> str:
    """Auto-select spec template: ``spec_from_design`` when design doc present.

    Args:
        context: Engine request context.
        override: Explicit template key (bypasses auto-selection).

    Returns:
        Template key string.
    """
    if override:
        return override
    if context.get("design_document"):
        return "spec_from_design"
    return "spec"


def _build_corpus_authorities_section(context: Dict[str, Any]) -> str:
    """Inject mature Controlled Corpus terms as canonical-vocabulary authority (R4-S2).

    Surfaces the accumulated corpus's stable terms ("use these canonical names exactly")
    into the spec prompt to reduce title/name drift in generation. Gated: off when
    ``corpus_authorities_enabled`` is False or ``STARTD8_CORPUS_AUTHORITIES`` is falsy;
    otherwise on when a corpus file exists. Tests may inject ``_corpus_registry`` directly.
    Pops its own context keys so they don't leak into the JSON general-context dump.
    """
    import os
    from pathlib import Path

    enabled = context.pop("corpus_authorities_enabled", None)
    corpus_path = context.pop("corpus_path", None)
    registry = context.pop("_corpus_registry", None)
    if enabled is False:
        return ""
    if os.getenv("STARTD8_CORPUS_AUTHORITIES", "1") not in ("1", "true", "yes", "on"):
        return ""
    try:
        from startd8.corpus.registry import ControlledCorpusRegistry
        from startd8.corpus.view import render_authorities_md
        from startd8.paths import controlled_corpus_path
    except ImportError:
        return ""
    if registry is None:
        if corpus_path:
            path = Path(corpus_path)
        else:
            project_root = context.get("project_root")
            path = controlled_corpus_path(Path(project_root) if project_root else None)
        if not path.exists():
            return ""
        registry = ControlledCorpusRegistry.load(path)
    return render_authorities_md(registry, min_maturity=2)


def build_spec_prompt(
    task_description: str,
    context: Dict[str, Any],
    output_format: Optional[str],
    template_key: Optional[str] = None,
    edit_min_pct: int = 80,
) -> str:
    """Build the full spec prompt from context.

    Pops structured keys from *context* so the remainder can be JSON-serialized
    as general context. Callers should pass a **copy** of the original context.

    Args:
        task_description: Task description for the spec.
        context: Dict with plan_context, architectural_context, etc.
            Structured keys are popped.
        output_format: Optional output format string.
        template_key: Override template selection (``spec`` or ``spec_from_design``).
        edit_min_pct: Minimum % of existing lines in edit output.

    Returns:
        Formatted spec prompt string.
    """
    from ..contractors.prompt_utils import format_constraints

    selected_key = _select_template_key(context, template_key)
    logger.info("Spec builder: using template '%s'", selected_key)

    # --- Kaizen quality hints (Phase C — Kaizen feedback loop) ---
    kaizen_hints = context.pop("kaizen_hints", None)

    # --- Design document forwarding (Mottainai Rule 2) ---
    design_document = context.pop("design_document", None) or ""

    # --- REQ-TDE-205: Language-aware design document + task description sanitization ---
    # Delegates to LanguageProfile.sanitize_code_examples() (REQ-TDE-202).
    # Defense-in-depth: enrichment handles primary sanitization at seed time;
    # this catches tasks that bypass enrichment or spec LLM hallucinations.
    lang_profile = context.get("language_profile")
    _lang_id = getattr(lang_profile, "language_id", "") if lang_profile else ""
    # If no profile object, try to re-hydrate from language_id (set by enrichment)
    if lang_profile is None and context.get("language_id"):
        from ..languages.registry import LanguageRegistry
        LanguageRegistry.discover()
        lang_profile = LanguageRegistry.get(context["language_id"])
        _lang_id = getattr(lang_profile, "language_id", "") if lang_profile else ""
    if lang_profile is not None and hasattr(lang_profile, "sanitize_code_examples"):
        if design_document:
            design_document = lang_profile.sanitize_code_examples(design_document)
        task_description = lang_profile.sanitize_code_examples(task_description)
    if _lang_id == "csharp" and design_document:
        sql_warning = _detect_sql_interpolation_in_examples(design_document)
        if sql_warning:
            design_document = design_document + sql_warning

    # REQ-QPI-204: Also scan design_doc_sections for SQL interpolation.
    # These carry reference examples independently of the design document.
    _dds = context.get("design_doc_sections")
    if _dds and isinstance(_dds, list):
        for _i, _section in enumerate(_dds):
            if isinstance(_section, str):
                _sql_warn = _detect_sql_interpolation_in_examples(_section)
                if _sql_warn:
                    _dds[_i] = _section + _sql_warn

    # --- FR-MPA-005: Pre-assembly scope narrowing ---
    # When element tiers are available, narrow the spec to unfilled elements only.
    # This reduces W-3 waste (30-50% input token reduction).
    element_tiers = context.pop("element_tiers", None)
    if not element_tiers:
        artifacts = context.get("artifacts")
        if isinstance(artifacts, dict):
            element_tiers = artifacts.pop("element_tiers", None)

    pre_assembly_preamble = ""
    if element_tiers and isinstance(element_tiers, dict):
        pre_filled_names: list = []
        unfilled_names: list = []
        for file_path, file_tiers in element_tiers.items():
            if not isinstance(file_tiers, dict):
                continue
            for elem_name, info in file_tiers.items():
                if not isinstance(info, dict):
                    continue
                is_filled = info.get("pre_filled", False) or (
                    info.get("fill_source", "none") != "none"
                )
                if is_filled:
                    fill_src = info.get("fill_source", "pre-filled")
                    pre_filled_names.append(f"  - `{elem_name}` ({fill_src})")
                else:
                    tier = info.get("tier", "UNKNOWN")
                    unfilled_names.append(f"  - `{elem_name}` (tier: {tier})")

        if pre_filled_names:
            preamble_parts = [
                "## Pre-Assembly Scope (Mottainai)\n",
                "The following elements are already implemented deterministically "
                "and do NOT need specification:\n",
                "\n".join(pre_filled_names),
                "",
            ]
            if unfilled_names:
                preamble_parts.extend([
                    "Scope your specification to ONLY these unfilled elements:\n",
                    "\n".join(unfilled_names),
                    "",
                ])
            pre_assembly_preamble = "\n".join(preamble_parts) + "\n"
            logger.info(
                "Spec builder: pre-assembly narrowing — %d pre-filled, %d unfilled elements",
                len(pre_filled_names), len(unfilled_names),
            )

    if pre_assembly_preamble:
        task_description = pre_assembly_preamble + task_description

    # --- Edit-aware spec framing ---
    existing_files = context.pop("existing_files", None)
    edit_mode = context.pop("edit_mode", None)
    is_edit = bool(existing_files) or (
        isinstance(edit_mode, dict) and edit_mode.get("mode") == "edit"
    )

    if is_edit:
        task_verb = "update"
        edit_preamble = _format_lead_prompt(
            "spec_edit_preamble_base",
            _SPEC_EDIT_PREAMBLE_BASE_FALLBACK,
            task_verb=task_verb.capitalize(),
        )
        if existing_files:
            # Option B: compute line count from target files only (not all
            # sibling context files) to avoid inflated constraints on small
            # config files.
            from .drafter import _target_file_lines, _all_files_non_python
            target_files_list = context.get("target_files") or []
            total_lines = _target_file_lines(target_files_list, existing_files)
            min_pct = edit_min_pct or 80
            min_lines = int(total_lines * min_pct / 100)
            # Option A: skip quantitative constraint for non-Python targets
            # where Python line-count heuristics are meaningless.
            skip_constraint = _all_files_non_python(target_files_list)
            if not skip_constraint and total_lines > 0:
                edit_preamble += _format_lead_prompt(
                    "spec_edit_quantitative_constraint",
                    _SPEC_EDIT_QUANTITATIVE_FALLBACK,
                    total_lines=total_lines,
                    min_lines=min_lines,
                    edit_min_pct=min_pct,
                )
        edit_preamble += "\n"
        task_description = edit_preamble + task_description
    else:
        # PC-F3: Create mode — use "implement" task verb in preamble
        create_preamble = _format_lead_prompt(
            "spec_create_preamble",
            _SPEC_CREATE_PREAMBLE_FALLBACK,
        )
        task_description = create_preamble + task_description

    # --- Constraint categorization ---
    raw_constraints = context.pop("domain_constraints", None)
    if raw_constraints and isinstance(raw_constraints, list):
        domain_constraints_str = format_constraints(raw_constraints)
    elif raw_constraints and isinstance(raw_constraints, str):
        domain_constraints_str = raw_constraints
    else:
        domain_constraints_str = "(No domain-specific constraints)"

    # --- Requirements text passthrough ---
    requirements_text = context.pop("requirements_text", "")
    requirements_section = ""
    if requirements_text:
        # FR-A1: STANDALONE path delivers this raw; fence it as data. The
        # "verbatim — authoritative" framing makes an un-fenced injection here
        # especially potent, so the DATA-not-instructions boundary is essential.
        requirements_section = (
            "\n## Requirements (verbatim — authoritative for parameter details)\n"
            f"{_fence_untrusted(requirements_text, 'requirements_text')}\n"
        )

    # --- Forward contracts ---
    forward_contracts = context.pop("forward_contracts", None)
    forward_element_specs = context.pop("forward_element_specs", None)

    # --- Design doc sections (A5: parity with Micro Prime REQ-DDS-001) ---
    design_doc_sections = context.pop("design_doc_sections", None)
    design_doc_section = ""
    if design_doc_sections and isinstance(design_doc_sections, list):
        dds_items = "\n".join(f"- {s}" for s in design_doc_sections)
        design_doc_section = (
            "\n## Implementation Context (design emphasis)\n"
            f"{dds_items}\n"
        )

    forward_contracts_section = ""
    if forward_contracts and isinstance(forward_contracts, str) and forward_contracts.strip():
        forward_contracts_section = (
            "\n## Interface Contract Bindings (must enforce)\n"
            f"{forward_contracts.strip()}\n"
        )
    if forward_element_specs and isinstance(forward_element_specs, str) and forward_element_specs.strip():
        forward_contracts_section += (
            "\n## Expected Code Elements (signatures, classes, bases)\n"
            f"{forward_element_specs.strip()}\n"
        )
    if design_doc_section:
        forward_contracts_section += design_doc_section

    # --- Critical parameters ---
    critical_parameters = context.pop("critical_parameters", None)
    critical_parameters_section = ""
    if critical_parameters:
        if isinstance(critical_parameters, list):
            cp_str = "\n".join(f"- {p}" for p in critical_parameters)
        elif isinstance(critical_parameters, str):
            cp_str = critical_parameters
        else:
            cp_str = safe_json_dumps(critical_parameters, indent=2)
        critical_parameters_section = (
            "\n## Critical Parameters (from requirements — include verbatim in spec)\n"
            f"{cp_str}\n"
        )

    # REQ-MP-1003: Reference implementation from copy-and-modify predecessor.
    reference_implementation = context.pop("reference_implementation", None)

    arch_ctx = context.pop("architectural_context", None)
    plan_ctx = context.pop("plan_context", None)
    project_obj = context.pop("project_objectives", None)
    sem_conv = context.pop("semantic_conventions", None)
    requirements_context = context.pop("requirements_context", None)
    protocol_guidance = context.pop("protocol_guidance", None)
    scope_boundary = context.pop("scope_boundary", None)
    # FR-A8: prior_error_feedback is a *second-order* untrusted carrier — its error
    # text can echo untrusted source content from a prior run. Pop it so it does NOT
    # land JSON-escaped-but-unfenced in the generic `## Context` dump, and render it
    # as a dedicated DATA-not-instructions fenced section below (the spec embeds into
    # the draft prompt, so fencing here covers both paths). [R1-S5]
    prior_error_feedback = context.pop("prior_error_feedback", None)
    # RUN-036: the field-set + entity-name + module-path authority (real entities, their
    # canonical module, and the "do not invent" negatives) the lead path builds into
    # `upstream_interfaces`. POP it here so it does NOT get JSON-escaped into the generic
    # `## Context` dump (build_spec_context_section), where the spec ignored it and invented a
    # non-existent `Match`. It is rendered as a dedicated section below — like the drafter does.
    upstream_interfaces = context.pop("upstream_interfaces", None)
    context_integration = context.pop("context_integration", None)
    # RUN-036 (convention half): the Python house-style authority (FastAPI/SQLModel idiom +
    # `app.tables` module-source) the lead path threads for Python targets. Pop so it renders as a
    # dedicated section, not JSON-escaped into the `## Context` dump.
    convention_guidance = context.pop("convention_guidance", None)

    # --- Build prioritized sections (P0=never drop, P3=drop first) ---
    target_files = context.get("target_files")

    # P0: Core context (always kept)
    ctx_section = build_spec_context_section(context, output_format, target_files)
    prioritized: List[tuple] = [(0, "context", ctx_section)]
    # FR-1 / FR-1a (forward-manifest at draft time): inject the forward-manifest
    # contract section at P0 so it is (a) governed by enforce_prompt_budget and
    # protected from eviction, and (b) rendered ahead of lower-priority context
    # (P0 sorts first within context_sections). Previously this text was passed
    # only as a standalone, un-budgeted format kwarg rendered AFTER all context
    # (RUN_003 postmortem Gap A: the drafter never reliably saw the contract).
    if forward_contracts_section.strip():
        prioritized.append((0, "forward_manifest", forward_contracts_section))
    else:
        # FR-2 (forward-manifest draft-time): the prompt still builds when a target file
        # has no ForwardFileSpec entry or an empty spec — but emit a structured INFO event
        # so the postmortem/Kaizen classifier (Fix 3) can attribute a downstream failure to
        # a missing/empty contract rather than "root cause: unknown". INFO (not WARN: this is
        # expected for many feature/file combos and must not page; not DEBUG: the classifier
        # must see it). Fields: {target_files, reason}.
        if not target_files:
            _fm_empty_reason = "no_target_files"
        elif forward_contracts is None and forward_element_specs is None:
            _fm_empty_reason = "missing_entry"
        else:
            _fm_empty_reason = "empty_elements"
        logger.info(
            "forward_manifest.section.empty",
            extra={
                "event": "forward_manifest.section.empty",
                "target_files": list(target_files) if target_files else [],
                "reason": _fm_empty_reason,
            },
        )

    # P0: Field-set / entity-name / module-path authority (RUN-036). Surfaced prominently in
    # the SPEC prompt (not just the draft) so the spec uses the project's REAL entities + their
    # canonical module instead of inventing one (the `from app.models import Match` boot-cascade).
    # P0 — same "contract you'll be validated against" class as the forward manifest; small,
    # referenced-entity-scoped upstream, so it survives budget without crowding the prompt.
    if isinstance(upstream_interfaces, str) and upstream_interfaces.strip():
        prioritized.append((0, "upstream_interfaces", upstream_interfaces))
    if isinstance(context_integration, str) and context_integration.strip():
        prioritized.append((0, "context_integration", context_integration))

    # P0: Python house-style convention authority (RUN-036 convention half) — module-source
    # (`app.tables`) + ORM idiom (SQLModel `session.exec`, not SQLAlchemy `session.query`) + FastAPI.
    # The lead/cloud path (test features, 0-element features) was inventing the wrong module/ORM;
    # this is the 8b authority micro-prime already receives, now surfaced in the spec too.
    if isinstance(convention_guidance, str) and convention_guidance.strip():
        prioritized.append((0, "python_conventions", convention_guidance))

    # P0: Language-specific project context (REQ-LA-1003)
    lang_profile = context.get("language_profile")
    if lang_profile is not None and hasattr(lang_profile, "build_project_context_section"):
        project_section = lang_profile.build_project_context_section(context)
        if project_section:
            prioritized.append((0, "project_context", project_section))

    # Kaizen quality hints from prior run analysis.
    # Security-related hints (sql_injection, parameterized queries) are escalated
    # to P0 so they survive budget enforcement; other hints remain P1.
    if kaizen_hints and isinstance(kaizen_hints, str) and kaizen_hints.strip():
        security_hints: List[str] = []
        quality_hints: List[str] = []
        for hint_line in kaizen_hints.strip().splitlines():
            stripped = hint_line.strip()
            if not stripped:
                continue
            if "sql_injection" in stripped.lower() or "parameterized" in stripped.lower():
                security_hints.append(stripped)
            else:
                quality_hints.append(stripped)

        if security_hints:
            sec_section = (
                "## Security Constraints (from prior run — P0)\n\n"
                + "\n".join(security_hints)
            )
            prioritized.append((0, "kaizen_security", sec_section))
        if quality_hints:
            qual_section = (
                "## Quality Hints (from prior run analysis)\n\n"
                + "\n".join(quality_hints)
            )
            prioritized.append((1, "kaizen_hints", qual_section))

    # P0: Sapper pre-execution alignment (FR-SAP-12 finding injection) — REFUTED/UNRESOLVED
    # misalignments the survey found against the real codebase for THIS file. P0 (like
    # kaizen_security) so they survive budget enforcement: a wrong framework/invented entity
    # fails the build, so the warning must reach the generator.
    sapper_alignment = context.get("sapper_alignment")
    if sapper_alignment and isinstance(sapper_alignment, str) and sapper_alignment.strip():
        prioritized.append((0, "sapper_alignment", sapper_alignment.strip()))

    # P1: Proven exemplar reference (REQ-PEP-101)
    exemplar_section = _build_exemplar_section(context)
    if exemplar_section:
        prioritized.append((1, "exemplar", exemplar_section))

    # P1: Available imports (L1 — reduces import repair rate)
    available_imports_section = _build_available_imports_section(context)
    if available_imports_section:
        prioritized.append((1, "available_imports", available_imports_section))

    # P1: Framework import templates (canonical import patterns for detected frameworks)
    fw_section = _build_framework_imports_section(context, task_description)
    if fw_section:
        prioritized.append((1, "framework_imports", fw_section))

    # P1: Sibling-file imports (L5+ — project-specific, preferred)
    sibling_section = _build_sibling_imports_section(context)
    if sibling_section:
        prioritized.append((1, "sibling_imports", sibling_section))

    # P1: Available local modules (file stems the LLM can import from)
    local_modules_section = _build_local_modules_section(context)
    if local_modules_section:
        prioritized.append((1, "local_modules", local_modules_section))

    # P1: Dependency task imports (upstream modules for correct proto/gRPC imports)
    dep_imports_section = _build_dependency_imports_section(context)
    if dep_imports_section:
        prioritized.append((1, "dependency_imports", dep_imports_section))

    # P1: Import conventions for flat module layouts (REQ-SV2-1300)
    import_conv_section = _build_import_conventions_section(context)
    if import_conv_section:
        prioritized.append((1, "import_conventions", import_conv_section))

    # P1: Requirements and protocol guidance
    if requirements_context:
        prioritized.append((1, "requirements_ctx", f"## Requirements Context\n{requirements_context}"))
    if protocol_guidance:
        prioritized.append((1, "protocol", f"## Protocol Guidance\n{protocol_guidance}"))
    # FR-A8: prior error feedback fenced as data (second-order untrusted carrier).
    if prior_error_feedback:
        _pef = _fence_untrusted(format_context_value(prior_error_feedback), "prior_error_feedback")
        prioritized.append((1, "prior_error_feedback", f"## Prior Error Feedback\n{_pef}"))

    # P0: Database security guidance with language-specific parameterized query examples
    # Inject task_description into context for auto-detection (it's a separate
    # function argument, not in the context dict by default).
    _sec_ctx = dict(context)
    _sec_ctx.setdefault("task_description", task_description)
    security_section = _build_security_guidance_section(_sec_ctx)
    if security_section:
        prioritized.append((0, "security_guidance", security_section))

    # P0: Language coding standards (REQ-KZ-005 — first-run quality injection)
    _coding_standards = context.get("coding_standards")
    if _coding_standards and isinstance(_coding_standards, str) and _coding_standards.strip():
        _cs_text = _coding_standards.strip()
        if len(_cs_text) > 3000:
            _cs_text = _cs_text[:3000] + "\n\n[truncated]"
        prioritized.append((
            0,
            "coding_standards",
            f"## Coding Standards (Target Language)\n\n{_cs_text}\n\n"
            f"**IMPORTANT:** These coding standards take precedence over reference "
            f"implementation patterns. If the task description or negative scope says "
            f"\"do not use\" something that the coding standards above REQUIRE "
            f"(e.g., \"do not use ILogger\" when standards say \"use ILogger<T>\"), "
            f"follow the coding standard. The goal is to generate code that meets "
            f"modern language best practices, not to replicate reference limitations.",
        ))

    # P2: Anti-pattern guidance for env var handling (REQ-SV2-1400)
    anti_pattern_section = _build_anti_pattern_section(context, task_description)
    if anti_pattern_section:
        prioritized.append((2, "anti_patterns", anti_pattern_section))

    # P2: Controlled Corpus canonical-vocabulary authorities (R4-S2 / FR-9 wiring)
    corpus_authorities_section = _build_corpus_authorities_section(context)
    if corpus_authorities_section:
        prioritized.append((2, "corpus_authorities", corpus_authorities_section))

    # P2: Within-run quality findings from accumulator (REQ-RFL-250)
    run_hints = context.pop("run_quality_hints", None)
    if run_hints and isinstance(run_hints, str) and run_hints.strip():
        prioritized.append((
            2,
            "run_quality_hints",
            f"## Prior Integration Findings (This Run)\n\n{run_hints.strip()}",
        ))

    # P1: Quality trend warning (REQ-RFL-260)
    trend_warning = context.pop("quality_trend_warning", None)
    if trend_warning and isinstance(trend_warning, str):
        prioritized.append((1, "quality_trend", trend_warning))

    # P1: Repair effectiveness calibration (REQ-RFL-270)
    # Warn about error categories that auto-repair can't reliably fix.
    try:
        from startd8.repair.orchestrator import get_step_effectiveness_summary
        _effectiveness = get_step_effectiveness_summary()
        _low_eff = [
            name for name, data in _effectiveness.items()
            if data.get("attempts", 0) >= 5 and data.get("success_rate", 1.0) < 0.2
        ]
        if _low_eff:
            prioritized.append((
                1,
                "repair_calibration",
                "## Repair Reliability Warning\n\n"
                "Auto-repair is unreliable for: "
                + ", ".join(_low_eff)
                + ". Ensure generated code avoids these error categories.",
            ))
    except ImportError as exc:
        logger.debug("Repair calibration skipped: %s", exc)

    # P1.5: Quality guidance from previous runs (REQ-RFL-330)
    seed_quality_hints = context.pop("quality_hints", None)
    if seed_quality_hints and isinstance(seed_quality_hints, list):
        hints_text = "\n".join(f"- {h}" for h in seed_quality_hints if h)
        if hints_text:
            prioritized.append((
                2,
                "quality_hints",
                f"## Quality Guidance (From Previous Runs)\n\n{hints_text}",
            ))

    # REQ-RFL-500: OTel attributes for spec quality hints
    try:
        from opentelemetry import trace as _spec_trace
        _spec_span = _spec_trace.get_current_span()
        if _spec_span and _spec_span.is_recording():
            _spec_span.set_attribute(
                "spec.run_quality_hints.present", run_hints is not None,
            )
            _spec_span.set_attribute(
                "spec.quality_hints.count",
                len(seed_quality_hints) if seed_quality_hints else 0,
            )
    except Exception:
        pass  # OTel is advisory

    # P2: Architecture and plan context
    obj_section = build_spec_objectives_section(project_obj)
    if obj_section:
        prioritized.append((2, "objectives", obj_section))
    conv_section = build_spec_conventions_section(sem_conv)
    if conv_section:
        prioritized.append((2, "conventions", conv_section))
    arch_section = build_spec_arch_section(arch_ctx, is_edit=is_edit)
    if arch_section:
        prioritized.append((2, "arch", arch_section))
    plan_section = build_spec_plan_section(plan_ctx, is_edit=is_edit)
    if plan_section:
        prioritized.append((2, "plan", plan_section))

    # P1: Scope boundary — tells LLM what NOT to implement (OI-003d)
    if scope_boundary:
        prioritized.append((1, "scope", f"## Scope Boundary (do NOT implement)\n{scope_boundary}"))

    # P3: Reference implementation (drop first)
    if reference_implementation:
        # REQ-PE-200: Use target language for code fence, not hardcoded python
        _lang_profile = context.get("language_profile")
        _fence_lang = getattr(_lang_profile, "language_id", "") if _lang_profile else ""
        # REQ-TDE-205: Sanitize reference implementation via protocol method.
        if lang_profile is not None and hasattr(lang_profile, "sanitize_code_examples"):
            reference_implementation = lang_profile.sanitize_code_examples(reference_implementation)
        prioritized.append((3, "reference", (
            "## Reference Implementation (predecessor — adapt, do not copy verbatim)\n"
            f"```{_fence_lang}\n"
            f"{reference_implementation}\n"
            "```"
        )))

    _budget_result = enforce_prompt_budget(
        prioritized, TOTAL_SPEC_BUDGET_TOKENS, logger=logger,
    )
    # REQ-MSR-110: Unpack budget decision for downstream analysis
    if isinstance(_budget_result, tuple):
        context_sections, _budget_decision = _budget_result
        context["_budget_decision"] = _budget_decision
    else:
        context_sections = _budget_result

    template = get_template(selected_key)

    format_kwargs = {
        "task_description": task_description,
        "requirements_section": requirements_section,
        "context_sections": context_sections,
        "critical_parameters_section": critical_parameters_section,
        # FR-1: forward-manifest content now flows through context_sections at P0
        # (see the prioritized.append above). Keep the placeholder bound to an
        # empty string to avoid duplicate rendering and preserve template shape.
        "forward_contracts_section": "",
        "domain_constraints": domain_constraints_str,
    }
    if selected_key == "spec_from_design":
        format_kwargs["design_document"] = design_document

    prompt = template.format(**format_kwargs)

    tokens = estimate_tokens(prompt)
    if tokens > TOTAL_SPEC_BUDGET_TOKENS:
        logger.info(
            "Spec prompt: %d tokens exceeds budget %d (template chrome + P0)",
            tokens, TOTAL_SPEC_BUDGET_TOKENS,
        )

    return prompt


def build_spec(
    agent: Any,
    task_description: str,
    context: Dict[str, Any],
    output_format: Optional[str] = None,
    template_key: Optional[str] = None,
    edit_min_pct: Optional[int] = 80,
) -> SpecResult:
    """Create an 8-section implementation specification.

    This is the primary entry point for spec creation, equivalent to
    ``PrimaryContractorWorkflow._create_spec()``.

    Args:
        agent: Agent to use for spec generation (must have ``.generate()``).
        task_description: What to implement.
        context: Additional context dict. Structured keys are consumed.
        output_format: Optional output format guidance.
        template_key: Override template selection.
        edit_min_pct: Minimum % of existing lines in edit output.

    Returns:
        SpecResult with parsed sections and telemetry.
    """
    spec_id = f"spec-{uuid.uuid4().hex[:8]}"

    # Copy to avoid mutating caller's dict
    context = dict(context)

    prompt = build_spec_prompt(
        task_description, context, output_format,
        template_key=template_key,
        edit_min_pct=edit_min_pct,
    )

    response_text, response_time_ms, token_usage = agent.generate(prompt)

    # REQ-TDE-205: Sanitize spec LLM output via protocol method — defense-in-depth.
    # Even with clean inputs, the spec LLM can hallucinate anti-patterns.
    _spec_lang_profile = context.get("language_profile")
    if _spec_lang_profile is None and context.get("language_id"):
        from ..languages.registry import LanguageRegistry
        LanguageRegistry.discover()
        _spec_lang_profile = LanguageRegistry.get(context["language_id"])
    if _spec_lang_profile is not None and hasattr(_spec_lang_profile, "sanitize_code_examples"):
        response_text = _spec_lang_profile.sanitize_code_examples(response_text)

    # Parse structured sections
    requirements = parse_list_section(response_text, "Requirements")
    acceptance_criteria = parse_list_section(response_text, "Acceptance Criteria")
    edge_cases = parse_list_section(response_text, "Edge Cases")
    constraints = parse_list_section(response_text, "Constraints")
    technical_approach = parse_section_content(response_text, "Technical Approach")
    code_structure = parse_section_content(response_text, "Code Structure")

    # CR-C2: Extract machine-readable MUST/MUST_NOT constraints from the
    # spec text for downstream review-phase enforcement.
    machine_constraints = extract_spec_constraints(response_text)

    spec = SpecResult(
        spec_id=spec_id,
        task_summary=task_description,
        requirements=requirements,
        technical_approach=technical_approach,
        acceptance_criteria=acceptance_criteria,
        code_structure=code_structure if code_structure else None,
        edge_cases=edge_cases,
        constraints=constraints,
        spec_constraints=machine_constraints,
        raw_spec=response_text,
        input_tokens=token_usage.input if token_usage else 0,
        output_tokens=token_usage.output if token_usage else 0,
        time_ms=response_time_ms,
    )

    spec.cost = _get_pricing().calculate_total_cost(
        getattr(agent, "model", "unknown"),
        spec.input_tokens,
        spec.output_tokens,
    )

    return spec


def extract_prompt_security_features(context: Dict[str, Any]) -> Dict[str, Any]:
    """Extract prompt security feature metadata for gate correlation (REQ-KSP-499).

    Returns a dict describing which security features were injected into
    the spec/draft prompts for this task. This metadata flows through
    result_metadata to the gate metrics builder for L5 measurement.

    Args:
        context: The gen_context dict used for prompt building.

    Returns:
        Dict with p0_injected, p1_databases, kaizen_hint_level,
        security_sensitive, and detected_database.
    """
    security_sensitive = bool(context.get("security_sensitive"))
    detected_database = context.get("detected_database") or ""
    security_contract = context.get("security_contract") or {}
    client_libraries = security_contract.get("client_libraries", [])

    # P0 detection: same heuristic as _build_security_guidance_section
    _DB_KEYWORDS = (
        "alloydb", "postgres", "npgsql", "spanner", "mysql", "sqlite",
        "database", "sql", "query", "cart_store", "cartstore",
    )
    desc = str(context.get("task_description", "")).lower()
    fname = str(context.get("feature_name", "")).lower()
    tfile = str(context.get("target_file", "")).lower()
    files_str = " ".join(str(f) for f in (context.get("target_files") or [])).lower()
    combined = f"{desc} {fname} {tfile} {files_str}"
    p0_from_keywords = any(kw in combined for kw in _DB_KEYWORDS)
    p0_injected = bool(client_libraries) or p0_from_keywords or security_sensitive

    # P1 databases from security contract
    p1_databases = []
    contract_dbs = security_contract.get("databases", [])
    for db in contract_dbs:
        db_val = db.value if hasattr(db, "value") else str(db)
        if db_val not in p1_databases:
            p1_databases.append(db_val)
    if detected_database and detected_database not in p1_databases:
        p1_databases.append(detected_database)

    # Kaizen hint level from kaizen hints content
    kaizen_hints = context.get("kaizen_hints", "") or ""
    kaizen_hint_level = "none"
    if kaizen_hints:
        lower_hints = kaizen_hints.lower()
        if "critical" in lower_hints:
            kaizen_hint_level = "critical"
        elif "must" in lower_hints or "requirement" in lower_hints:
            kaizen_hint_level = "requirement"
        else:
            kaizen_hint_level = "guidance"

    return {
        "p0_injected": p0_injected,
        "p1_databases": p1_databases,
        "kaizen_hint_level": kaizen_hint_level,
        "security_sensitive": security_sensitive,
        "detected_database": detected_database,
    }
