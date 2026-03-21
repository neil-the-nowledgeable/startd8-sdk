"""Prime Contractor CodeGenerator Adapter (REQ-MP-504).

Implements the ``CodeGenerator`` protocol, wrapping the Micro Prime engine
for use in PrimeContractorWorkflow. Elements that can't be handled locally
are delegated to a fallback ``CodeGenerator``.
"""

from __future__ import annotations

import ast
import dataclasses
import json
import os
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.error import URLError
from urllib.request import urlopen

from startd8.agents.base import BaseAgent
from startd8.contractors.protocols import (
    CodeGenerator,
    DRAFT_MODEL_CLAUDE_HAIKU,
    GenerationResult,
)
from startd8.element_id import make_element_id
from startd8.element_registry import (
    ElementEntry,
    ElementRegistry,
    compute_element_context_checksum,
)
from startd8.forward_manifest import (
    ForwardElementSpec,
    ForwardFileSpec,
    ForwardManifest,
    InterfaceContract,
)
from startd8.logging_config import get_logger
from startd8.micro_prime.classifier import classify_element
from startd8.micro_prime.context import MicroPrimeContext
from startd8.micro_prime.engine import MicroPrimeEngine, _CODE_GEN_SYSTEM_PROMPT, _is_stub_only_body
from startd8.micro_prime.models import (
    EscalationReason,
    FileResult,
    MicroPrimeConfig,
    TierClassification,
)
from startd8.utils.code_manifest import ElementKind

logger = get_logger(__name__)

# OTel metrics (REQ-MP-705) — optional dependency
try:
    from opentelemetry import metrics as otel_metrics
    _meter = otel_metrics.get_meter("startd8.micro_prime")
    _elements_local_counter = _meter.create_counter(
        "micro_prime.elements_local",
        description="Elements processed locally by Micro Prime",
    )
    _elements_escalated_counter = _meter.create_counter(
        "micro_prime.elements_escalated",
        description="Elements escalated to fallback generator",
    )
    _template_hits_counter = _meter.create_counter(
        "micro_prime.template_hits",
        description="Elements resolved by template registry",
    )
except ImportError:
    _elements_local_counter = None
    _elements_escalated_counter = None
    _template_hits_counter = None


# Size-regression threshold: if filled skeleton is below this ratio of the
# existing target file (by semantic line count), escalate to the fallback
# generator.  Uses semantic lines (non-blank, non-comment, non-docstring)
# to avoid penalising lean Ollama output against verbose cloud-generated
# files that have rich docstrings and inline comments.
_SIZE_REGRESSION_THRESHOLD = 0.55
_MIN_EXISTING_LINES = 50

# ElementKind values that map to ast.FunctionDef / ast.AsyncFunctionDef
# rather than ast.ClassDef.  Used by _extract_element_from_generated and
# _escalate_elements_to_cloud to translate manifest kinds to AST node types.
_FUNCTION_LIKE_KINDS = frozenset({
    "function", "async_function", "method", "async_method", "property",
})


def _serialize_file_result(fr: Any) -> dict:
    """Serialize a FileResult dataclass to dict, truncating code to avoid bloat."""
    from enum import Enum as _Enum

    result = dataclasses.asdict(fr)
    for er in result.get("element_results", []):
        code = er.get("code")
        if code and len(code) > 500:
            er["code"] = code[:500] + "... [truncated]"
        # Normalize enum values (dataclasses.asdict uses str() on str(Enum))
        for key in ("tier", "reason"):
            val = er.get(key)
            if val and isinstance(val, str) and "." in val:
                er[key] = val.rsplit(".", 1)[-1].lower()
        esc = er.get("escalation")
        if isinstance(esc, dict):
            reason = esc.get("reason", "")
            if isinstance(reason, str) and "." in reason:
                esc["reason"] = reason.rsplit(".", 1)[-1].lower()
            ctx = esc.get("context")
            if isinstance(ctx, dict):
                raw_output = ctx.get("raw_output")
                if raw_output and len(raw_output) > 500:
                    ctx["raw_output"] = raw_output[:500] + "... [truncated]"
                repaired = ctx.get("repaired_code")
                if repaired and len(repaired) > 500:
                    ctx["repaired_code"] = repaired[:500] + "... [truncated]"
    # Drop filled_skeleton from serialization — too large for metadata
    result.pop("filled_skeleton", None)
    return result


def _sanitize_for_json(value: Any) -> Any:
    """Recursively convert Pydantic models to dicts for JSON compatibility."""
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if isinstance(value, dict):
        return {k: _sanitize_for_json(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_sanitize_for_json(v) for v in value]
    return value


def _extract_element_from_generated(
    source: str, element_name: str, element_kind: str,
) -> Optional[str]:
    """Extract a named function/class from *source* using AST.

    Returns the source lines for the matching element (including the def/class
    line), suitable for feeding into ``splice_body_into_skeleton()``.  Returns
    ``None`` if the element cannot be found or *source* fails to parse.

    Args:
        source: Complete Python source text (e.g. fallback-generated file).
        element_name: Name of the function or class to extract.
        element_kind: ``"class"`` for ClassDef, or any value in
            ``_FUNCTION_LIKE_KINDS`` for FunctionDef/AsyncFunctionDef.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None

    target_types: tuple[type, ...] = (
        (ast.ClassDef,) if element_kind == "class"
        else (ast.FunctionDef, ast.AsyncFunctionDef)
    )

    # ast.walk visits in no guaranteed order.  This is acceptable because
    # fallback-generated files are typically flat (no duplicate names).
    source_lines = source.splitlines()
    for node in ast.walk(tree):
        if isinstance(node, target_types) and node.name == element_name:
            start = node.lineno - 1
            end = node.end_lineno or len(source_lines)
            return "\n".join(source_lines[start:end])

    return None


_SKELETON_MARKER = "# [STARTD8-SKELETON]"


def _semantic_line_count(source: str) -> int:
    """Count semantic lines in Python source (non-blank, non-comment, non-docstring).

    Normalises the comparison between lean Ollama-assembled code and verbose
    cloud-generated code by ignoring differences in docstring/comment density.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        # Fallback to raw non-blank lines if source doesn't parse
        return sum(1 for line in source.splitlines() if line.strip())

    # Collect line ranges occupied by docstrings (module, class, function)
    docstring_lines: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            if (
                node.body
                and isinstance(node.body[0], ast.Expr)
                and isinstance(getattr(node.body[0], "value", None), ast.Constant)
                and isinstance(node.body[0].value.value, str)
            ):
                ds = node.body[0]
                for ln in range(ds.lineno, (ds.end_lineno or ds.lineno) + 1):
                    docstring_lines.add(ln)

    count = 0
    for i, line in enumerate(source.splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            continue
        if i in docstring_lines:
            continue
        count += 1
    return count


def _detect_assembly_defect(content: str, file_path: str) -> Optional[str]:
    """Return a human-readable defect description, or ``None`` if clean.

    Checks for three classes of assembly defect:
    1. Remaining ``raise NotImplementedError`` stub-only functions/methods
    2. ``[STARTD8-SKELETON]`` markers (skeleton was never fully assembled)
    3. Nested duplicate function definitions (Ollama over-generation artifact)
    """
    if _SKELETON_MARKER in content:
        return "`[STARTD8-SKELETON]` marker still present"
    if file_path.endswith(".py"):
        try:
            tree = ast.parse(content)
        except SyntaxError:
            return "file does not parse (SyntaxError)"
        # Check 1: stub-only function/method bodies (AST-precise)
        stub_names: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if _is_stub_only_body(node.body):
                    stub_names.append(node.name)
        if stub_names:
            names = ", ".join(f"`{n}`" for n in stub_names)
            return f"remaining `raise NotImplementedError` stubs in {names}"
        # Check 3: nested duplicate function/class definitions
        _def_class_types = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
        for node in ast.walk(tree):
            if isinstance(node, _def_class_types):
                for child in ast.walk(node):
                    if (
                        child is not node
                        and isinstance(child, _def_class_types)
                        and child.name == node.name
                    ):
                        kind = "class" if isinstance(node, ast.ClassDef) else "function"
                        return (
                            f"nested duplicate {kind} `{node.name}` "
                            f"(Ollama over-generation)"
                        )
    elif "raise NotImplementedError" in content:
        # Non-Python files: fall back to string check
        return "remaining `raise NotImplementedError` stubs"
    return None


def _check_structural_integrity(
    content: str,
    element_results: list,
    file_path: str,
) -> Optional[str]:
    """Verify that successfully generated elements exist in the final AST.

    For each element result with ``success=True``, confirm the corresponding
    AST node exists in the output: ClassDef for classes, FunctionDef for
    functions, and methods nested inside their parent class.  Returns a
    human-readable defect string on the first structural mismatch, or
    ``None`` if all elements are present.
    """
    if not file_path.endswith(".py"):
        return None
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return None  # Already caught by ast.parse gate; don't double-report

    # Build lookup: top-level names and class→method sets
    top_classes: dict[str, ast.ClassDef] = {}
    top_functions: set[str] = set()
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.ClassDef):
            top_classes[node.name] = node
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            top_functions.add(node.name)

    class_methods: dict[str, set[str]] = {}
    for cls_name, cls_node in top_classes.items():
        methods: set[str] = set()
        for child in cls_node.body:
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                methods.add(child.name)
        class_methods[cls_name] = methods

    missing: list[str] = []
    for er in element_results:
        if not er.success:
            continue
        kind = getattr(er, "element_kind", None) or ""
        name = er.element_name
        parent = getattr(er, "parent_class", None)

        if kind == "class":
            if name not in top_classes:
                missing.append(f"class `{name}`")
        elif parent:
            # Method/property/nested constant — must be inside parent class
            if parent not in top_classes:
                missing.append(f"class `{parent}` (parent of `{name}`)")
            elif name not in class_methods.get(parent, set()):
                missing.append(f"`{parent}.{name}`")
        elif kind in ("function", "async_function"):
            if name not in top_functions:
                missing.append(f"function `{name}`")

    if missing:
        return "structural integrity: missing " + ", ".join(missing)
    return None


def _enrich_file_spec_imports(
    file_spec: "ForwardFileSpec",
    dependency_imports: Dict[str, Dict[str, Any]],
) -> "ForwardFileSpec":
    """Enrich file_spec.imports with modules from dependency tasks.

    When the forward manifest has empty imports for a file (common for test
    clients), this injects proto module names from the service communication
    graph via dependency_imports.  Prevents the LLM from hallucinating proto
    module names (run-055 F-1/F-2: email_service_pb2, recommendationservicestub).
    """
    from startd8.forward_manifest import ForwardImportSpec

    existing_modules = {imp.module for imp in file_spec.imports}
    new_imports = list(file_spec.imports)
    added = False

    for dep_id, info in dependency_imports.items():
        for mod in info.get("modules", []):
            if mod not in existing_modules and not mod.startswith("_"):
                new_imports.append(ForwardImportSpec(kind="import", module=mod))
                existing_modules.add(mod)
                added = True

    if not added:
        return file_spec

    logger.info(
        "Enriched file_spec imports with %d dependency modules: %s",
        len(new_imports) - len(file_spec.imports),
        sorted(existing_modules - {imp.module for imp in file_spec.imports}),
    )
    return file_spec.model_copy(update={"imports": new_imports})


@dataclasses.dataclass
class _FileProcessingState:
    """Mutable state carrier for generate() sub-steps."""

    all_file_results: list = dataclasses.field(default_factory=list)
    file_results_by_path: Dict[str, Any] = dataclasses.field(default_factory=dict)
    generated_files: list = dataclasses.field(default_factory=list)  # list[Path]
    written_file_paths: set = dataclasses.field(default_factory=set)  # set[str]
    total_input: int = 0
    total_output: int = 0
    escalated_files: list = dataclasses.field(default_factory=list)  # list[str]
    bypass_files: list = dataclasses.field(default_factory=list)  # FR-DFA-001: files MP can't process
    local_element_count: int = 0
    template_count: int = 0
    ollama_count: int = 0
    escalated_element_count: int = 0
    decomposed_count: int = 0
    decomposition_failure_count: int = 0
    element_escalation_cost: float = 0.0
    element_escalation_count: int = 0
    element_escalation_attempt_cost: float = 0.0
    element_escalation_attempt_count: int = 0
    effective_file_count: int = 0
    incomplete_files: list = dataclasses.field(default_factory=list)  # list[str]
    stub_escalated: list = dataclasses.field(default_factory=list)  # list[str]
    reg_hits: int = 0
    reg_misses: int = 0


class MicroPrimeCodeGenerator:
    """``CodeGenerator`` implementation using the Micro Prime engine.

    Processes TRIVIAL and SIMPLE elements locally, delegating MODERATE and
    COMPLEX elements to a fallback ``CodeGenerator`` (typically the
    LeadContractor pattern).

    Args:
        config: Micro Prime engine configuration.
        fallback: Fallback code generator for elements beyond local capability.
        manifest: Forward manifest for element metadata.
        skeletons: Dict of file path -> skeleton content.
        output_dir: Directory for writing generated files.  Defaults to cwd.
        cloud_agent_spec: Optional agent spec (e.g. ``"anthropic:claude-haiku-4-5-20251001"``)
            for direct per-element cloud escalation.  When set, escalated elements
            use a single LLM call instead of the full fallback pipeline.  Falls back
            to ``fallback.drafter_agent`` or ``DRAFT_MODEL_CLAUDE_HAIKU``.
    """

    def __init__(
        self,
        config: Optional[MicroPrimeConfig] = None,
        fallback: Optional[CodeGenerator] = None,
        manifest: Optional[ForwardManifest] = None,
        skeletons: Optional[dict[str, str]] = None,
        output_dir: Optional[Path] = None,
        cloud_agent_spec: Optional[str] = None,
        element_registry: Optional[ElementRegistry] = None,
        project_root: Optional[Path] = None,
        language_profile: Optional[Any] = None,
    ) -> None:
        self._config = config or MicroPrimeConfig()
        self._fallback = fallback
        self._manifest = manifest
        self._skeletons = skeletons or {}
        self._output_dir = output_dir or Path(".")
        # Public alias — PrimeContractor._resolve_output_dir() reads
        # self.code_generator.output_dir to determine where files land.
        self.output_dir = self._output_dir
        self._project_root = project_root
        self._element_registry = element_registry
        self._registry_hits = 0
        self._registry_misses = 0
        self._language_profile = language_profile
        self._engine = MicroPrimeEngine(
            config=self._config,
            element_registry=element_registry,
            language_profile=language_profile,
        )
        self._ollama_available: Optional[bool] = None
        self._cloud_agent_spec = cloud_agent_spec
        self._tier_agent_spec: Optional[str] = None
        self._cloud_agent: Optional[BaseAgent] = None
        # Expose fallback agent specs for Kaizen metadata capture
        self.lead_agent = getattr(fallback, "lead_agent", None)
        self.drafter_agent = getattr(fallback, "drafter_agent", None)

    def generate(
        self,
        task: str,
        context: Dict[str, Any],
        target_files: List[str],
    ) -> GenerationResult:
        """Generate code for the given task.

        Attempts local generation first. For elements that require cloud
        processing, delegates to the fallback generator if available.

        Args:
            task: Description of what to implement.
            context: Additional context (existing code, requirements, etc.).
            target_files: Expected output file paths.

        Returns:
            GenerationResult with success status and generated file paths.
        """
        # D3: Capture tier-specific agent spec from complexity routing
        self._tier_agent_spec = context.get("_tier_agent_spec")

        manifest = context.get("manifest") or self._manifest
        skeletons = context.get("skeletons") or self._skeletons

        # REQ-MP-702: Auto-generate skeletons from manifest when missing.
        # Prime Contractor has no SCAFFOLD phase, so stubs are produced on
        # demand using DeterministicFileAssembler.
        if manifest is not None and not skeletons:
            skeletons = self._generate_skeletons(manifest, target_files, context)

        if manifest is None:
            logger.warning(
                "MicroPrimeCodeGenerator: no manifest in context — "
                "delegating %d file(s) to fallback: %s",
                len(target_files),
                ", ".join(target_files) if target_files else "(none)",
            )
            return self._delegate_to_fallback(task, context, target_files)

        # REQ-MP-711: Ollama availability guard — check once per instance
        ollama_ok = self._check_ollama_available()

        if self._config.dry_run:
            return self._dry_run_classify(manifest, skeletons, target_files, ollama_ok)

        if not ollama_ok:
            logger.info(
                "Ollama unavailable — SIMPLE elements will be escalated to fallback",
            )

        mp_context = MicroPrimeContext.from_prime(
            context, manifest, target_files, ollama_ok,
        )

        st = _FileProcessingState()

        # Phase 1: Process target files through the engine
        self._process_target_files(
            st, target_files, manifest, skeletons, mp_context, task, context,
        )

        local_file_count = len(st.generated_files)

        partial_files = sum(
            1 for fp in target_files
            if fp not in st.escalated_files
            and fp not in st.bypass_files
            and fp not in st.written_file_paths
        )
        logger.info(
            "Micro Prime: %d elements local (%d files), %d escalated "
            "(%d files to fallback, %d bypass, %d partial kept)",
            st.local_element_count,
            local_file_count,
            st.escalated_element_count,
            len(st.escalated_files),
            len(st.bypass_files),
            partial_files,
        )

        # Phase 2: Element-level escalation for partial files
        self._handle_partial_escalations(
            st, target_files, task, context, manifest, ollama_ok,
        )

        # Phase 3: Post-generation file-level repair (lint + import completion)
        if st.generated_files:
            self._run_post_generation_repair(st.generated_files)

        # Phase 4: Post-assembly validation + effective file count
        self._validate_and_finalize_files(st)

        # REQ-MP-1103: Count element registry hits/misses for metadata
        st.reg_hits, st.reg_misses = self._count_registry_hits_misses(
            st.all_file_results,
        )
        logger.info(
            "Element registry: %d hits, %d misses",
            st.reg_hits, st.reg_misses,
        )

        # Phase 5a-pre: Deterministic generation for requirements.in files.
        # Extract third-party imports from already-generated Python files in
        # the same service directory and write requirements.in directly —
        # zero LLM cost, zero hallucination risk.
        remaining_bypass: list[str] = []
        for bp_file in st.bypass_files:
            if bp_file.endswith(".in") and "requirements" in bp_file.rsplit("/", 1)[-1]:
                generated_content = self._generate_requirements_in(
                    bp_file, st, target_files,
                )
                if generated_content is not None:
                    output_path = self._output_dir / bp_file
                    output_path.parent.mkdir(parents=True, exist_ok=True)
                    output_path.write_text(generated_content, encoding="utf-8")
                    st.generated_files.append(output_path)
                    st.written_file_paths.add(bp_file)
                    st.effective_file_count += 1
                    logger.info(
                        "Deterministic requirements.in: %s (%d packages)",
                        bp_file, len(generated_content.strip().splitlines()),
                    )
                    continue
            remaining_bypass.append(bp_file)
        st.bypass_files = remaining_bypass

        # Phase 5a: FR-DFA-001 — Bypass files always delegate to fallback
        # (regardless of escalation_enabled).  These are files MP fundamentally
        # cannot process (no ForwardFileSpec / no skeleton), NOT files where
        # element-level generation failed.
        if st.bypass_files and self._fallback is not None:
            logger.info(
                "Delegating %d bypass file(s) to fallback (unsupported "
                "locally): %s",
                len(st.bypass_files),
                ", ".join(st.bypass_files),
            )
            bypass_result = self._delegate_to_fallback(
                task, context, st.bypass_files,
            )
            if bypass_result.success:
                st.generated_files.extend(bypass_result.generated_files)
                st.effective_file_count += len(bypass_result.generated_files)
                st.total_input += bypass_result.input_tokens
                st.total_output += bypass_result.output_tokens
            else:
                # Propagate fallback error so it surfaces in postmortem
                # instead of the generic "Code generation failed".
                logger.error(
                    "Fallback generator failed for bypass files %s: %s",
                    st.bypass_files,
                    bypass_result.error or "unknown error",
                )
                return GenerationResult(
                    success=False,
                    generated_files=st.generated_files,
                    input_tokens=st.total_input + bypass_result.input_tokens,
                    output_tokens=st.total_output + bypass_result.output_tokens,
                    cost_usd=st.element_escalation_attempt_cost + bypass_result.cost_usd,
                    model=f"{self._config.provider}:{self._config.model}",
                    error=bypass_result.error or (
                        f"Fallback generation failed for bypass files: "
                        f"{', '.join(st.bypass_files)}"
                    ),
                )
        elif st.bypass_files:
            logger.warning(
                "No fallback generator available — %d file(s) cannot be "
                "processed locally and will be skipped: %s",
                len(st.bypass_files),
                ", ".join(st.bypass_files),
            )

        # Phase 5b: Element-escalated files respect escalation_enabled
        if st.escalated_files and not self._config.escalation_enabled:
            logger.warning(
                "Cloud escalation disabled (escalation_enabled=False) — "
                "keeping %d file(s) as partial local output: %s",
                len(st.escalated_files),
                ", ".join(st.escalated_files),
            )
        elif st.escalated_files and self._fallback is not None and self._config.escalation_enabled:
            return self._generate_with_fallback(
                st, target_files, task, context, local_file_count,
            )

        # Build per-file responses for Kaizen capture (REQ-KZ-201).
        # Keys use "draft_{file_path}" convention so _persist_kaizen_prompts
        # writes them as response files alongside prompts.
        gen_responses: Dict[str, str] = {}
        for fr in st.all_file_results:
            skeleton = getattr(fr, "filled_skeleton", None)
            if skeleton:
                fp = getattr(fr, "file_path", None) or "unknown"
                safe_key = str(fp).replace("/", "_").replace(".", "_")
                gen_responses[f"draft_{safe_key}"] = skeleton

        return GenerationResult(
            success=st.effective_file_count > 0,
            generated_files=st.generated_files,
            input_tokens=st.total_input,
            output_tokens=st.total_output,
            cost_usd=st.element_escalation_attempt_cost,
            model=f"{self._config.provider}:{self._config.model}",
            metadata=self._build_generation_metadata(
                st, local_file_count,
                micro_prime_only=st.element_escalation_attempt_count == 0,
                lead_agent_spec=getattr(self, "lead_agent", None),
                drafter_agent_spec=getattr(self, "drafter_agent", None),
            ),
            responses=gen_responses,
        )

    # ── generate() sub-steps ──────────────────────────────────────────

    def _process_target_files(
        self,
        st: _FileProcessingState,
        target_files: List[str],
        manifest: ForwardManifest,
        skeletons: dict[str, str],
        mp_context: MicroPrimeContext,
        task: str,
        context: Dict[str, Any],
    ) -> None:
        """Process each target file through the engine, writing results to disk."""
        existing_files: Dict[str, str] = mp_context.existing_file_contents

        for file_path in target_files:
            file_spec = manifest.file_specs.get(file_path)
            skeleton = skeletons.get(file_path, "")

            # Fallback: try basename match when exact path fails.
            # Covers cases where target_files has a bare filename (e.g., "logger.py")
            # but the manifest key is the full relative path ("src/emailservice/logger.py").
            if file_spec is None:
                basename = Path(file_path).name
                for mkey, mspec in manifest.file_specs.items():
                    if Path(mkey).name == basename:
                        file_spec = mspec
                        logger.info(
                            "Micro Prime: resolved %s → %s via basename fallback",
                            file_path, mkey,
                        )
                        if not skeleton:
                            skeleton = skeletons.get(mkey, "")
                        break

            # REQ-MLT-100: Non-Python file-level bypass — must come BEFORE
            # the skeleton/file_spec check so that Dockerfiles, HTML, go.mod,
            # etc. are caught early regardless of whether they have a skeleton.
            # Without this, non-Python files without skeletons fall into the
            # generic "no skeleton" bypass and get routed to the LLM fallback
            # via MicroPrime's bypass path instead of being handled directly.
            from startd8.micro_prime.engine import _is_non_python_file

            if _is_non_python_file(file_path):
                # FR-DFA-003: Dockerfile passthrough (skeleton available)
                lang = getattr(file_spec, "language", None) if file_spec else None
                if lang == "dockerfile" and skeleton:
                    output_path = self._output_dir / file_path
                    output_path.parent.mkdir(parents=True, exist_ok=True)
                    output_path.write_text(skeleton, encoding="utf-8")
                    st.generated_files.append(output_path)
                    st.written_file_paths.add(file_path)
                    st.effective_file_count += 1
                    logger.info(
                        "Micro Prime wrote Dockerfile %s (%d lines, passthrough)",
                        file_path,
                        skeleton.count("\n") + 1,
                    )
                    continue

                # REQ-MLT-103: Deterministic go.mod generation
                go_mod_content = self._try_generate_go_mod(
                    file_path, file_spec, context,
                )
                if go_mod_content is not None:
                    output_path = self._output_dir / file_path
                    output_path.parent.mkdir(parents=True, exist_ok=True)
                    output_path.write_text(go_mod_content, encoding="utf-8")
                    st.generated_files.append(output_path)
                    st.written_file_paths.add(file_path)
                    st.effective_file_count += 1
                    logger.info(
                        "Micro Prime wrote go.mod %s (deterministic, %d lines)",
                        file_path,
                        go_mod_content.count("\n") + 1,
                    )
                    continue

                # Deterministic build.gradle generation
                gradle_content = self._try_generate_build_gradle(
                    file_path, file_spec, context,
                )
                if gradle_content is not None:
                    output_path = self._output_dir / file_path
                    output_path.parent.mkdir(parents=True, exist_ok=True)
                    output_path.write_text(gradle_content, encoding="utf-8")
                    st.generated_files.append(output_path)
                    st.written_file_paths.add(file_path)
                    st.effective_file_count += 1
                    logger.info(
                        "Micro Prime wrote build.gradle %s (deterministic, %d lines)",
                        file_path,
                        gradle_content.count("\n") + 1,
                    )
                    continue

                # REQ-NODE-103: Deterministic package.json generation
                pkg_json_content = self._try_generate_package_json(
                    file_path, file_spec, context,
                )
                if pkg_json_content is not None:
                    output_path = self._output_dir / file_path
                    output_path.parent.mkdir(parents=True, exist_ok=True)
                    output_path.write_text(pkg_json_content, encoding="utf-8")
                    st.generated_files.append(output_path)
                    st.written_file_paths.add(file_path)
                    st.effective_file_count += 1
                    logger.info(
                        "Micro Prime wrote package.json %s (deterministic, %d lines)",
                        file_path,
                        pkg_json_content.count("\n") + 1,
                    )
                    continue

                # REQ-CS-103: Deterministic .csproj generation
                csproj_content = self._try_generate_csproj(
                    file_path, file_spec, context,
                )
                if csproj_content is not None:
                    output_path = self._output_dir / file_path
                    output_path.parent.mkdir(parents=True, exist_ok=True)
                    output_path.write_text(csproj_content, encoding="utf-8")
                    st.generated_files.append(output_path)
                    st.written_file_paths.add(file_path)
                    st.effective_file_count += 1
                    logger.info(
                        "Micro Prime wrote .csproj %s (deterministic, %d lines)",
                        file_path,
                        csproj_content.count("\n") + 1,
                    )
                    continue

                # REQ-CS-104: Deterministic .sln generation
                sln_content = self._try_generate_sln(
                    file_path, file_spec, context,
                )
                if sln_content is not None:
                    output_path = self._output_dir / file_path
                    output_path.parent.mkdir(parents=True, exist_ok=True)
                    output_path.write_text(sln_content, encoding="utf-8")
                    st.generated_files.append(output_path)
                    st.written_file_paths.add(file_path)
                    st.effective_file_count += 1
                    logger.info(
                        "Micro Prime wrote .sln %s (deterministic, %d lines)",
                        file_path,
                        sln_content.count("\n") + 1,
                    )
                    continue

                # Deterministic appsettings.json generation
                appsettings_content = self._try_generate_appsettings(
                    file_path, context,
                )
                if appsettings_content is not None:
                    output_path = self._output_dir / file_path
                    output_path.parent.mkdir(parents=True, exist_ok=True)
                    output_path.write_text(appsettings_content, encoding="utf-8")
                    st.generated_files.append(output_path)
                    st.written_file_paths.add(file_path)
                    st.effective_file_count += 1
                    logger.info(
                        "Micro Prime wrote appsettings.json %s (deterministic, %d lines)",
                        file_path,
                        appsettings_content.count("\n") + 1,
                    )
                    continue

                # All other non-Python files: delegate to fallback (LLM)
                logger.info(
                    "Micro Prime: non-Python file %s — "
                    "delegating to fallback for file-whole generation",
                    file_path,
                )
                st.bypass_files.append(file_path)
                continue

            if file_spec is None or not skeleton:
                # FR-DFA-001: Python file-level bypass — MP can't process this
                # Python file (no manifest entry or no skeleton).  Distinct
                # from element-level escalation where MP tried but elements
                # were too complex.
                reason = (
                    "no ForwardFileSpec in manifest"
                    if file_spec is None
                    else "no skeleton source available"
                )
                logger.info(
                    "Micro Prime bypass: %s (%s) — delegating to fallback",
                    file_path, reason,
                )
                st.bypass_files.append(file_path)
                continue

            # REQ-SIG-201: Enrich file_spec imports with dependency modules
            # from service communication graph. This ensures MicroPrime element
            # prompts include correct proto module names (e.g., demo_pb2) even
            # when the forward manifest has no prescribed imports for this file.
            if mp_context.dependency_imports and file_spec is not None:
                file_spec = _enrich_file_spec_imports(
                    file_spec, mp_context.dependency_imports,
                )

            # REQ-DDS-002: Thread design_doc_sections to engine
            _dds = context.get("design_doc_sections") or []
            # Mottainai Rule 2: Forward task description to element prompts
            _task_desc = task or None
            file_result = self._engine.process_file_with_context(
                file_spec, skeleton, mp_context,
                design_doc_sections=_dds if _dds else None,
                task_description=_task_desc,
            )
            st.all_file_results.append(file_result)
            st.file_results_by_path[file_path] = file_result

            if file_result.filled_skeleton:
                # Size-regression escalation guard.
                # Pipeline-poisoning guard: skip comparison when the file is
                # manifest-covered — the existing content is from a prior run
                # (possibly a different generation strategy like cloud), not a
                # meaningful baseline for the current skeleton-based generation.
                existing_content = existing_files.get(file_path, "")
                manifest_covers_file = (
                    file_path in (manifest.file_specs or {})
                    if manifest is not None else False
                )
                if existing_content and not manifest_covers_file:
                    filled_sem = _semantic_line_count(file_result.filled_skeleton)
                    existing_sem = _semantic_line_count(existing_content)
                    existing_raw = existing_content.count("\n") + 1
                    # Scale threshold by element fill rate: a partially-filled
                    # skeleton (unfilled stubs = 1 line each) should not be
                    # compared against the full existing file at the same bar.
                    total_el = len(file_result.element_results)
                    filled_el = sum(
                        1 for er in file_result.element_results if er.success
                    )
                    fill_rate = filled_el / total_el if total_el > 0 else 1.0
                    effective_threshold = _SIZE_REGRESSION_THRESHOLD * fill_rate
                    ratio = filled_sem / existing_sem if existing_sem > 0 else 1.0
                    if ratio < effective_threshold and existing_raw >= _MIN_EXISTING_LINES:
                        logger.warning(
                            "Micro Prime size-regression guard: %s has %d semantic "
                            "lines vs %d existing (%.0f%%, fill rate %.0f%%) "
                            "— escalating to fallback",
                            file_path, filled_sem, existing_sem,
                            ratio * 100, fill_rate * 100,
                        )
                        st.escalated_files.append(file_path)
                        continue

                # REQ-MP-703: Write filled skeleton to disk
                final_content = file_result.filled_skeleton.replace(
                    _SKELETON_MARKER + "\n", "",
                ).replace(_SKELETON_MARKER, "")

                # Phase 1, Step 9: ast.parse syntax gate AFTER sentinel strip
                try:
                    ast.parse(final_content)
                except SyntaxError as syn_err:
                    logger.warning(
                        "Micro Prime ast.parse gate failed for %s: %s — skipping write",
                        file_path, syn_err,
                    )
                    st.escalated_files.append(file_path)
                    continue
                output_path = self._output_dir / file_path
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_text(final_content, encoding="utf-8")
                st.generated_files.append(output_path)
                st.written_file_paths.add(file_path)
                logger.info(
                    "Micro Prime wrote %s (%d lines, %d elements filled)",
                    file_path,
                    final_content.count("\n") + 1,
                    sum(1 for er in file_result.element_results if er.success),
                )

            # Track tokens and element counts
            for er in file_result.element_results:
                st.total_input += er.input_tokens
                st.total_output += er.output_tokens
                if er.success:
                    st.local_element_count += 1
                    if er.template_used:
                        st.template_count += 1
                    else:
                        st.ollama_count += 1
                if er.escalation is not None:
                    st.escalated_element_count += 1
                    if er.escalation.reason == EscalationReason.DECOMPOSITION_FAILED:
                        st.decomposition_failure_count += 1
                if er.decomposition_metadata is not None:
                    st.decomposed_count += 1

            # OTel metrics (REQ-MP-705)
            if _elements_local_counter is not None:
                for er in file_result.element_results:
                    if er.success:
                        _elements_local_counter.add(
                            1, {"tier": er.tier.value, "file_path": file_path},
                        )
                        if er.template_used and _template_hits_counter is not None:
                            _template_hits_counter.add(
                                1, {"file_path": file_path},
                            )
                    if er.escalation is not None and _elements_escalated_counter is not None:
                        _elements_escalated_counter.add(
                            1,
                            {"reason": er.escalation.reason.value, "file_path": file_path},
                        )

            # Element-level escalation: only delegate the whole file to
            # fallback when ZERO elements succeeded locally (Mottainai).
            if file_result.escalated_count > 0 and file_result.success_count == 0:
                st.escalated_files.append(file_path)

    def _handle_partial_escalations(
        self,
        st: _FileProcessingState,
        target_files: List[str],
        task: str,
        context: Dict[str, Any],
        manifest: ForwardManifest,
        ollama_ok: bool,
    ) -> None:
        """Handle element-level escalation for partially-filled files."""
        partial_escalation_candidates = [
            fp for fp in target_files
            if fp not in st.escalated_files
            and (fr := st.file_results_by_path.get(fp))
            and fr.escalated_count > 0 and fr.success_count > 0
        ]
        cloud_escalation_available = (
            self._cloud_agent_spec is not None
            and self._config.escalation_enabled
        )
        ollama_available = bool(ollama_ok)

        # T2-1+T2-2: Exclusive decision tree for partial escalation candidates.
        # Priority: cloud element escalation > file-level fallback > keep partial.
        if partial_escalation_candidates and cloud_escalation_available:
            # Tier 2: element-level cloud escalation (works even if Ollama is down)
            for fp in partial_escalation_candidates:
                fr = st.file_results_by_path[fp]
                try:
                    esc_result = self._escalate_elements_to_cloud(
                        fp, fr, task, context, manifest,
                    )
                    if esc_result:
                        st.total_input += esc_result.input_tokens
                        st.total_output += esc_result.output_tokens
                        st.element_escalation_attempt_cost += esc_result.cost_usd
                        st.element_escalation_attempt_count += 1
                        if esc_result.success:
                            st.element_escalation_cost += esc_result.cost_usd
                            st.element_escalation_count += 1
                except (OSError, ValueError, RuntimeError, TypeError):
                    # Narrow catch per [SDK Leg 11 #28]
                    logger.warning(
                        "Element-level cloud escalation failed for %s, "
                        "keeping partial skeleton",
                        fp, exc_info=True,
                    )
        elif partial_escalation_candidates and self._fallback is not None and self._config.escalation_enabled:
            # Tier 3: no cloud agent — delegate entire file(s) to fallback
            self._demote_to_fallback(st, partial_escalation_candidates)
            logger.info(
                "No cloud agent for per-element retry — delegating %d file(s) to fallback",
                len(partial_escalation_candidates),
            )
        elif partial_escalation_candidates and not ollama_available and self._fallback is not None:
            # Ollama down + no cloud agent — delegate to fallback
            self._demote_to_fallback(st, partial_escalation_candidates)
            logger.info(
                "Ollama unavailable, no cloud agent — delegating %d file(s) to fallback",
                len(partial_escalation_candidates),
            )
        elif partial_escalation_candidates:
            logger.debug(
                "No escalation path available for %d file(s) — keeping partial output",
                len(partial_escalation_candidates),
            )

    def _demote_to_fallback(
        self,
        st: _FileProcessingState,
        candidates: list[str],
    ) -> None:
        """Move candidate files from written/generated to escalated."""
        for fp in candidates:
            if fp not in st.escalated_files:
                st.escalated_files.append(fp)
                st.written_file_paths.discard(fp)
                _out = self._output_dir / fp
                st.generated_files[:] = [p for p in st.generated_files if p != _out]
                try:
                    _out.unlink()
                except OSError:
                    pass

    def _validate_and_finalize_files(
        self,
        st: _FileProcessingState,
    ) -> None:
        """Detect assembly defects and compute effective file count."""
        # Post-assembly file-level validation
        for file_path in list(st.written_file_paths):
            if file_path in st.escalated_files:
                continue
            fr = st.file_results_by_path.get(file_path)
            if fr is None or not fr.filled_skeleton or not fr.element_results:
                continue
            output_path = self._output_dir / file_path
            try:
                content = output_path.read_text(encoding="utf-8")
            except OSError:
                continue

            defect = _detect_assembly_defect(content, file_path)
            if defect is None:
                defect = _check_structural_integrity(
                    content, fr.element_results, file_path,
                )
            if defect is not None:
                if self._fallback is not None and self._config.escalation_enabled:
                    logger.warning(
                        "Micro Prime file %s has assembly defect: %s "
                        "— escalating to fallback",
                        file_path, defect,
                    )
                    st.stub_escalated.append(file_path)
                    st.written_file_paths.discard(file_path)
                    st.generated_files[:] = [
                        p for p in st.generated_files if p != output_path
                    ]
                    st.escalated_files.append(file_path)
                    try:
                        output_path.unlink()
                    except OSError:
                        pass
                else:
                    logger.warning(
                        "Micro Prime file %s has assembly defect: %s "
                        "(escalation disabled — keeping partial output)",
                        file_path, defect,
                    )
                    st.stub_escalated.append(file_path)
            else:
                # REQ-MP-1103: Register validated elements in the registry
                self._register_validated_elements(file_path, fr)

        # Compute effective file count based on element fill rate
        for file_path in st.written_file_paths:
            if file_path in st.stub_escalated:
                # When escalation is disabled the partial file is the best
                # output we can produce — count it as effective so the
                # caller doesn't treat the entire generation as a failure.
                if not self._config.escalation_enabled:
                    st.effective_file_count += 1
                else:
                    st.incomplete_files.append(file_path)
                continue
            fr = st.file_results_by_path.get(file_path)
            if fr is None:
                st.effective_file_count += 1
                continue
            total = len(fr.element_results)
            filled = sum(1 for er in fr.element_results if er.success)
            rate = filled / total if total > 0 else 1.0
            if rate >= self._config.min_element_fill_rate:
                st.effective_file_count += 1
            else:
                st.incomplete_files.append(file_path)
                logger.warning(
                    "File %s has low element fill rate: %d/%d (%.0f%%) — marking as incomplete",
                    file_path, filled, total, rate * 100,
                )

    def _build_generation_metadata(
        self,
        st: _FileProcessingState,
        local_file_count: int,
        **extra: Any,
    ) -> dict:
        """Build the shared metadata dict for GenerationResult."""
        meta: dict = {
            "micro_prime_files_written": local_file_count,
            "effective_file_count": st.effective_file_count,
            "bypass_file_count": len(st.bypass_files),
            "incomplete_files": st.incomplete_files,
            "micro_prime_elements": st.local_element_count,
            "micro_prime_template_hits": st.template_count,
            "micro_prime_ollama_generations": st.ollama_count,
            "micro_prime_decomposed_count": st.decomposed_count,
            "micro_prime_decomposition_failures": st.decomposition_failure_count,
            "micro_prime_cost_usd": 0.0,
            "element_escalation_cost_usd": st.element_escalation_cost,
            "element_escalation_count": st.element_escalation_count,
            "element_escalation_attempt_cost_usd": st.element_escalation_attempt_cost,
            "element_escalation_attempt_count": st.element_escalation_attempt_count,
            "prime.element_registry_hit": st.reg_hits,
            "prime.element_registry_miss": st.reg_misses,
            "micro_prime_file_results": [
                _serialize_file_result(fr) for fr in st.all_file_results
            ],
        }
        meta.update(extra)
        return meta

    def _generate_with_fallback(
        self,
        st: _FileProcessingState,
        target_files: List[str],
        task: str,
        context: Dict[str, Any],
        local_file_count: int,
    ) -> GenerationResult:
        """Delegate escalated files to cloud fallback and return combined result."""
        logger.warning(
            "Escalating %d file(s) to cloud fallback: %s",
            len(st.escalated_files),
            ", ".join(st.escalated_files),
        )
        fallback_context = self._with_escalation_context(
            context, st.all_file_results,
        )
        fallback_result = self._delegate_to_fallback(
            task, fallback_context, st.escalated_files,
        )
        st.generated_files.extend(fallback_result.generated_files)
        st.total_input += fallback_result.input_tokens

        # L6: Backfill registry from cloud output for future run reuse
        if fallback_result.success and self._element_registry is not None:
            backfill_count = self._backfill_registry_from_cloud(
                fallback_result.generated_files,
                feature_id=context.get("feature_id", "unknown"),
            )
            if backfill_count > 0:
                logger.info(
                    "Backfilled %d elements from cloud fallback into registry",
                    backfill_count,
                )

        local_files_kept = sum(1 for fp in target_files if fp not in st.escalated_files)
        local_success = True if local_files_kept == 0 else (st.effective_file_count > 0)

        return GenerationResult(
            success=fallback_result.success and local_success,
            generated_files=st.generated_files,
            input_tokens=st.total_input,
            output_tokens=st.total_output,
            cost_usd=fallback_result.cost_usd + st.element_escalation_attempt_cost,
            model=f"micro-prime+{fallback_result.model}",
            metadata={
                **self._build_generation_metadata(
                    st, local_file_count,
                    fallback_files_delegated=len(st.escalated_files),
                    fallback_files_written=len(fallback_result.generated_files),
                    fallback_elements=st.escalated_element_count,
                    fallback_cost_usd=fallback_result.cost_usd,
                ),
                # Forward raw LLM responses and cost breakdown from fallback
                **{k: v for k, v in (fallback_result.metadata or {}).items()
                   if k in ("spec_raw_response", "draft_raw_response",
                            "review_raw_response", "lead_agent_spec",
                            "drafter_agent_spec", "lead_cost",
                            "drafter_cost", "cost_efficiency_ratio")},
            },
        )

    def _with_escalation_context(
        self,
        context: Dict[str, Any],
        file_results: list[FileResult],
    ) -> Dict[str, Any]:
        """Attach micro-prime escalation context for fallback prompts."""
        feedback = self._format_escalation_feedback(file_results)
        if not feedback:
            return context
        merged = dict(context)
        existing = merged.get("last_error") or ""
        if existing:
            merged["last_error"] = f"{existing}\n\n{feedback}"
        else:
            merged["last_error"] = feedback
        return merged

    def _format_escalation_feedback(
        self,
        file_results: list[FileResult],
        max_chars: int = 4000,
    ) -> str:
        """Summarize local failures for cloud fallback (REQ-MP-502)."""
        lines: list[str] = ["Micro Prime local attempt failed for:"]
        count = 0
        for fr in file_results:
            for er in fr.element_results:
                if er.escalation is None:
                    continue
                count += 1
                reason = er.escalation.reason.value
                err = er.escalation.last_error or er.escalation.detail
                lines.append(
                    f"- {er.file_path}:{er.element_name} "
                    f"({reason}) — {err}"
                )
        if count == 0:
            return ""
        text = "\n".join(lines)
        if len(text) > max_chars:
            text = text[:max_chars] + "\n... [truncated]"
        return text

    def _run_post_generation_repair(self, generated_files: list[Path]) -> int:
        """Run lint + syntax checks and auto-repair generated files.

        Uses the shared repair pipeline (``IntegrationCheckpoint`` +
        ``run_file_repair``) to fix F821/import/syntax errors in generated
        output.  Returns the number of files repaired, or 0 if checks pass
        or repair is unavailable.
        """
        if not generated_files:
            return 0

        try:
            from startd8.contractors.checkpoint import IntegrationCheckpoint
            from startd8.repair.config import RepairConfig
            from startd8.repair.diagnostics import parse_checkpoint_diagnostics
            from startd8.repair.orchestrator import run_file_repair
        except ImportError:
            logger.debug(
                "Repair infrastructure not available, skipping post-generation repair",
            )
            return 0

        try:
            checkpoint = IntegrationCheckpoint(project_root=self._output_dir)
            results = []
            results.append(checkpoint.check_syntax(generated_files))
            results.append(checkpoint.check_lint(generated_files))
        except (OSError, subprocess.TimeoutExpired) as exc:
            logger.warning(
                "Post-generation checkpoint failed, skipping repair: %s", exc,
            )
            return 0

        diagnostics = parse_checkpoint_diagnostics(results)
        if not diagnostics:
            logger.debug("Post-generation checks passed — no repair needed")
            return 0

        logger.info(
            "Post-generation repair: %d diagnostic(s) found in %d file(s)",
            len(diagnostics), len(generated_files),
        )

        files_dict = {}
        for fp in generated_files:
            try:
                files_dict[fp] = fp.read_text(encoding="utf-8")
            except OSError:
                logger.warning("Cannot read %s for repair, skipping", fp)

        if not files_dict:
            return 0

        try:
            outcome = run_file_repair(
                files_dict, diagnostics, RepairConfig(), self._output_dir,
            )
        except (OSError, ValueError, RuntimeError) as exc:
            logger.warning("Post-generation repair failed: %s", exc)
            return 0

        repaired_count = 0
        for fp, content in outcome.repaired_files.items():
            try:
                fp.write_text(content, encoding="utf-8")
                repaired_count += 1
            except OSError:
                logger.warning("Cannot write repaired file %s", fp)

        if repaired_count:
            logger.info("Post-generation repair: %d file(s) repaired", repaired_count)
        return repaired_count

    def _register_validated_elements(
        self,
        file_path: str,
        file_result: FileResult,
    ) -> None:
        """Register successfully generated elements in the element registry.

        Called after a file passes post-assembly validation
        (``_detect_assembly_defect`` returns ``None``).  Each element that was
        successfully generated is stored in the registry with its code,
        tier, and generator metadata.

        Non-fatal: any registry error is logged as a warning and does not
        abort generation (REQ-MP-1103).
        """
        if self._element_registry is None:
            return

        for er in file_result.element_results:
            if not er.success or not er.code:
                continue

            kind_str = er.element_kind or "unknown"
            element_id = make_element_id(
                kind=kind_str,
                name=er.element_name,
                file_path=file_path,
                parent_class=er.parent_class,
            )

            try:
                existing = self._element_registry.get(element_id)
                if existing is not None:
                    existing.extra["code"] = er.code
                    existing.extra["generator"] = (
                        er.model or self._config.model or "micro-prime"
                    )
                    existing.extra["tier"] = er.tier.value if er.tier else "unknown"
                    self._element_registry.put(existing)
                else:
                    entry = ElementEntry(
                        element_id=element_id,
                        kind=kind_str,
                        name=er.element_name,
                        file_path=file_path,
                        parent_class=er.parent_class,
                        extra={
                            "code": er.code,
                            "generator": (
                                er.model or self._config.model or "micro-prime"
                            ),
                            "tier": er.tier.value if er.tier else "unknown",
                        },
                    )
                    self._element_registry.put(entry)
                self._element_registry.set_phase_status(
                    element_id, "post_assembly", "validated",
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Element registry write failed for %s in %s: %s",
                    er.element_name,
                    file_path,
                    exc,
                )

    def _backfill_registry_from_cloud(
        self,
        generated_files: list[str],
        feature_id: str,
    ) -> int:
        """Decompose cloud-generated files into registry entries.

        After cloud fallback produces files that pass validation,
        AST-decompose each Python file into individual function/class
        elements and ``registry.put()`` each one.  This populates the
        registry for future runs on the same project.

        Returns the number of elements backfilled.
        """
        if self._element_registry is None:
            return 0

        backfilled = 0
        for file_path in generated_files:
            file_path = Path(file_path)
            if file_path.suffix != ".py":
                continue
            try:
                source = file_path.read_text(encoding="utf-8")
                tree = ast.parse(source)
            except (OSError, SyntaxError):
                continue

            rel_path = file_path
            try:
                rel_path = os.path.relpath(file_path, self._output_dir)
            except ValueError:
                pass

            # Build parent map for method detection
            parent_map: dict[int, str | None] = {}
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    for child in ast.walk(node):
                        if child is not node and isinstance(
                            child, (ast.FunctionDef, ast.AsyncFunctionDef)
                        ):
                            parent_map[id(child)] = node.name

            for node in ast.walk(tree):
                if not isinstance(
                    node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
                ):
                    continue

                start = node.lineno - 1
                end = node.end_lineno or start + 1
                code_lines = source.splitlines()[start:end]
                code = "\n".join(code_lines)

                parent_class = parent_map.get(id(node))
                kind = "class" if isinstance(node, ast.ClassDef) else "function"

                element_id = make_element_id(
                    kind=kind,
                    name=node.name,
                    file_path=rel_path,
                    parent_class=parent_class,
                )

                try:
                    # Compute context checksum so staleness detection works
                    # on future runs (same shared function as engine + EMIT).
                    ctx_checksum = compute_element_context_checksum(
                        element_name=node.name,
                        element_kind=kind,
                        parent_class=parent_class or "",
                    )
                    entry = ElementEntry(
                        element_id=element_id,
                        kind=kind,
                        name=node.name,
                        file_path=rel_path,
                        parent_class=parent_class,
                        context_checksum=ctx_checksum,
                        extra={
                            "code": code,
                            "generator": "cloud-backfill",
                            "feature_id": feature_id,
                        },
                    )
                    self._element_registry.put(entry)
                    self._element_registry.set_phase_status(
                        element_id, "cloud_backfill", "validated",
                    )
                    backfilled += 1
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "Registry backfill failed for %s in %s: %s",
                        node.name, rel_path, exc,
                    )

        return backfilled

    def _count_registry_hits_misses(
        self,
        all_file_results: list[FileResult],
    ) -> tuple[int, int]:
        """Count element registry hits and misses across all file results.

        A *hit* is an element whose ``decomposition_metadata`` has
        ``source == "element_registry"`` (served from the cache).  A *miss*
        is any successfully generated element that was NOT a registry hit.

        Returns (hits, misses).
        """
        hits = 0
        misses = 0
        for fr in all_file_results:
            for er in fr.element_results:
                if not er.success:
                    continue
                dm = er.decomposition_metadata
                if isinstance(dm, dict) and dm.get("source") == "element_registry":
                    hits += 1
                else:
                    misses += 1
        return hits, misses

    def _dry_run_classify(
        self,
        manifest: ForwardManifest,
        skeletons: dict[str, str],
        target_files: List[str],
        ollama_available: bool,
    ) -> GenerationResult:
        """Run classification on all elements and print a report without generating code.

        Iterates every target file's elements through ``classify_element()`` and
        the template registry, collecting tier counts and per-file summaries.
        Prints a formatted console report and returns a zero-cost result with
        classification metadata.
        """
        base_url = os.environ.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
        model_name = self._config.model
        templates = self._engine._templates if self._config.templates_enabled else None

        per_file: list[dict[str, Any]] = []
        tier_totals = {t: 0 for t in TierClassification}
        total_elements = 0
        total_local = 0
        total_escalated = 0

        for file_path in target_files:
            file_spec = manifest.file_specs.get(file_path)
            skeleton = skeletons.get(file_path, "")
            if file_spec is None:
                per_file.append({
                    "file": file_path,
                    "skipped": True,
                    "reason": "no file_spec in manifest",
                })
                continue
            if not skeleton:
                per_file.append({
                    "file": file_path,
                    "skipped": True,
                    "reason": "no skeleton generated",
                })
                continue

            skeleton_lines = skeleton.count("\n") + 1
            elements_info: list[dict[str, str]] = []
            file_local = 0
            file_escalated = 0

            for element in file_spec.elements:
                contracts = self._engine._get_element_contracts(
                    element, file_spec, manifest,
                )
                tier, reason = classify_element(
                    element, file_spec, contracts,
                    template_registry=templates,
                    config=self._config,
                )
                tier_totals[tier] += 1
                total_elements += 1

                template_hit = (
                    templates.match(element, file_spec, contracts) is not None
                    if templates else False
                )

                # Decomposition viability for MODERATE elements (REQ-MP-906a, REQ-MP-909)
                decomposable = False
                decompose_strategy = None
                if tier == TierClassification.MODERATE and self._config.decomposition_enabled:
                    decomposable = self._engine._decomposer.can_decompose(
                        element, file_spec, manifest, reason,
                    )
                    if decomposable:
                        # Identify which strategy would handle it
                        for s in self._engine._decomposer._strategies:
                            if s.can_handle(element, file_spec, manifest, reason):
                                decompose_strategy = s.name
                                break

                # Routing: TRIVIAL with template works without Ollama;
                # SIMPLE requires Ollama; MODERATE/COMPLEX always escalate.
                if tier == TierClassification.TRIVIAL and template_hit:
                    file_local += 1
                    total_local += 1
                elif tier in (TierClassification.TRIVIAL, TierClassification.SIMPLE) and ollama_available:
                    file_local += 1
                    total_local += 1
                elif tier == TierClassification.MODERATE and decomposable and ollama_available:
                    file_local += 1
                    total_local += 1
                else:
                    file_escalated += 1
                    total_escalated += 1

                elem_entry: dict[str, Any] = {
                    "name": element.name,
                    "tier": tier.value.upper(),
                    "reason": reason,
                    "template_hit": template_hit,
                }
                if decomposable:
                    elem_entry["decomposable"] = True
                    elem_entry["decompose_strategy"] = decompose_strategy
                elements_info.append(elem_entry)

            per_file.append({
                "file": file_path,
                "element_count": len(file_spec.elements),
                "skeleton_lines": skeleton_lines,
                "elements": elements_info,
                "local": file_local,
                "escalated": file_escalated,
            })

        # Print bypasses log-level filtering — this is a user-facing report.
        report = self._format_dry_run_report(
            per_file, tier_totals, total_elements, total_local,
            ollama_available, model_name, base_url,
        )
        print(report)

        return GenerationResult(
            success=True,
            generated_files=[],
            input_tokens=0,
            output_tokens=0,
            cost_usd=0.0,
            model="micro-prime-dry-run",
            metadata={
                "dry_run": True,
                "ollama_available": ollama_available,
                "total_elements": total_elements,
                "total_local": total_local,
                "total_escalated": total_escalated,
                "tier_totals": {t.value: c for t, c in tier_totals.items()},
                "per_file": per_file,
            },
        )

    @staticmethod
    def _format_dry_run_report(
        per_file: list[dict[str, Any]],
        tier_totals: dict[TierClassification, int],
        total_elements: int,
        total_local: int,
        ollama_available: bool,
        model_name: str,
        base_url: str,
    ) -> str:
        """Format the dry-run classification report as a box-drawing string."""
        local_pct = (total_local / total_elements * 100) if total_elements else 0
        ollama_status = (
            f"available ({model_name} @ {base_url})"
            if ollama_available
            else f"unavailable ({base_url})"
        )

        lines = [
            "",
            "\u2554" + "\u2550" * 62 + "\u2557",
            "\u2551  Micro Prime \u2014 Dry Run Classification Report" + " " * 17 + "\u2551",
            "\u255a" + "\u2550" * 62 + "\u255d",
            "",
            f"  Ollama: {ollama_status}",
            "",
        ]

        for pf in per_file:
            if pf.get("skipped"):
                lines.append(f"  {pf['file']}  [SKIPPED: {pf['reason']}]")
                lines.append("")
                continue

            lines.append(
                f"  {pf['file']} ({pf['element_count']} elements, "
                f"skeleton: {pf['skeleton_lines']} lines)"
            )
            for el in pf.get("elements", []):
                line = f"    {el['tier']:<10} {el['name']:<35} {el['reason']}"
                if el["template_hit"]:
                    line += "  [template]"
                if el.get("decomposable"):
                    line += f"  [decomposable: {el.get('decompose_strategy', '?')}]"
                lines.append(line)

            decomposable_count = sum(
                1 for el in pf.get("elements", []) if el.get("decomposable")
            )
            summary = f"    -> {pf['local']} local, {pf['escalated']} escalated"
            if decomposable_count:
                summary += f", {decomposable_count} decomposable"
            lines.append(summary)
            lines.append("")

        file_count = sum(1 for p in per_file if not p.get("skipped"))
        lines.append("  " + "-" * 60)
        lines.append(f"  Summary: {file_count} files, {total_elements} elements")
        lines.append(
            f"    TRIVIAL:  {tier_totals[TierClassification.TRIVIAL]:>3}  (template match)"
        )
        lines.append(
            f"    SIMPLE:   {tier_totals[TierClassification.SIMPLE]:>3}  (Ollama local)"
        )
        total_decomposable = sum(
            1 for pf in per_file
            for el in pf.get("elements", [])
            if el.get("decomposable")
        )
        mod_label = "(cloud fallback)"
        if total_decomposable:
            mod_label = f"({total_decomposable} decomposable -> local, rest cloud)"
        lines.append(
            f"    MODERATE: {tier_totals[TierClassification.MODERATE]:>3}  {mod_label}"
        )
        lines.append(
            f"    COMPLEX:  {tier_totals[TierClassification.COMPLEX]:>3}  (cloud fallback)"
        )
        lines.append("")
        lines.append(
            f"  Local generation: {total_local}/{total_elements} elements "
            f"({local_pct:.0f}%)"
        )
        lines.append("")
        return "\n".join(lines)

    def _generate_skeletons(
        self,
        manifest: ForwardManifest,
        target_files: List[str],
        context: Optional[Dict[str, Any]] = None,
    ) -> dict[str, str]:
        """Generate stub skeletons from manifest for target files only.

        Uses ``DeterministicFileAssembler`` to render ``ForwardFileSpec``
        elements into Python source with ``raise NotImplementedError`` stubs.
        For Dockerfiles, uses existing file content as the skeleton (MVP
        passthrough — FR-DFA-003).

        Only the current feature's target files are rendered (not the entire
        manifest).  Per-file failures are logged and skipped — they do not
        block other files.

        Returns:
            Dict mapping file path to skeleton source text.
        """
        from startd8.utils.file_assembler import DeterministicFileAssembler

        assembler = DeterministicFileAssembler(
            element_registry=self._element_registry,
        )
        skeletons: dict[str, str] = {}
        existing_files: Dict[str, str] = (
            dict((context or {}).get("existing_files") or {})
        )

        from startd8.micro_prime.engine import _is_non_python_file

        for file_path in target_files:
            file_spec = manifest.file_specs.get(file_path)
            if file_spec is None:
                logger.debug("No file_spec for %s, skipping skeleton", file_path)
                continue

            # FR-DFA-003: Dockerfile skeleton = existing content (passthrough)
            lang = getattr(file_spec, "language", None)
            if lang == "dockerfile":
                existing = existing_files.get(file_path, "")
                if existing:
                    skeletons[file_path] = existing
                    logger.debug(
                        "Dockerfile skeleton for %s: passthrough existing "
                        "content (%d lines)",
                        file_path,
                        existing.count("\n") + 1,
                    )
                else:
                    logger.debug(
                        "No existing content for Dockerfile %s, skipping "
                        "skeleton (create-mode deferred)",
                        file_path,
                    )
                continue

            # --- Language-specific skeleton generators (before generic bypass) ---
            # These must run BEFORE _is_non_python_file() because they have
            # dedicated DFA assemblers that produce real skeletons, not passthrough.
            from pathlib import PurePosixPath
            _suffix = PurePosixPath(file_path).suffix.lower()

            # .java source files: use JavaDeterministicFileAssembler for
            # skeleton generation (real Java skeletons with package statement,
            # 2-tier imports, and UnsupportedOperationException stubs).
            if _suffix == ".java":
                try:
                    from startd8.utils.java_file_assembler import (
                        JavaDeterministicFileAssembler,
                    )

                    java_assembler = JavaDeterministicFileAssembler()
                    java_source = java_assembler.render_file(file_spec)
                    if java_source:
                        skeletons[file_path] = java_source
                        logger.debug(
                            "Generated Java skeleton for %s (%d lines)",
                            file_path,
                            java_source.count("\n") + 1,
                        )
                    else:
                        logger.debug(
                            "Java DFA returned None for %s, skipping skeleton",
                            file_path,
                        )
                except (ImportError, ValueError, TypeError, AttributeError) as exc:
                    logger.warning(
                        "Java skeleton generation failed for %s: %s",
                        file_path, exc,
                    )
                continue

            # .go source files: use existing content if available, otherwise
            # skip — the file-whole generation path handles Go without needing
            # a Python-style skeleton.  Go skeletons with panic("not implemented")
            # stubs would require a Go-aware assembler (future enhancement).
            if _suffix == ".go":
                existing = existing_files.get(file_path, "")
                if existing:
                    skeletons[file_path] = existing
                    logger.debug(
                        "Go skeleton for %s: passthrough existing content "
                        "(%d lines)",
                        file_path,
                        existing.count("\n") + 1,
                    )
                else:
                    logger.debug(
                        "Go file %s has no existing content, skipping "
                        "skeleton (file-whole generation)",
                        file_path,
                    )
                continue

            # --- Generic non-Python bypass (after language-specific checks) ---
            # Non-Python files (go.mod, YAML, HTML, etc.) must not go through
            # the Python DeterministicFileAssembler — it emits `from __future__
            # import annotations` stubs.  Use existing content or skip so the
            # cloud/file-whole generation path handles them.
            if _is_non_python_file(file_path):
                existing = existing_files.get(file_path, "")
                if existing:
                    skeletons[file_path] = existing
                    logger.debug(
                        "Non-Python skeleton for %s: passthrough existing "
                        "content (%d lines)",
                        file_path,
                        existing.count("\n") + 1,
                    )
                else:
                    logger.debug(
                        "Non-Python file %s has no existing content, "
                        "skipping skeleton (cloud/file-whole generation)",
                        file_path,
                    )
                continue

            try:
                source = assembler.render_file(file_spec)
                skeletons[file_path] = source
                logger.debug(
                    "Generated skeleton for %s (%d lines)",
                    file_path,
                    source.count("\n") + 1,
                )
            except (ValueError, TypeError, AttributeError, OSError) as exc:
                logger.warning(
                    "Failed to generate skeleton for %s: %s", file_path, exc,
                )

        return skeletons

    def _check_ollama_available(self) -> bool:
        """Check if Ollama is reachable and the configured model is pulled.

        Result is cached on ``self._ollama_available`` so the HTTP check
        only fires once per adapter instance.  Uses a 5-second timeout to
        avoid blocking generation (REQ-MP-711).
        """
        if self._ollama_available is not None:
            return self._ollama_available

        base_url = os.environ.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
        url = f"{base_url}/api/tags"
        model_name = self._config.model

        try:
            with urlopen(url, timeout=5) as response:
                data = json.loads(response.read().decode())

            model_names: list[str] = []
            for m in data.get("models", []):
                if not isinstance(m, dict):
                    continue
                name = m.get("name", "")
                model_names.append(name)
                if ":" in name:
                    model_names.append(name.split(":")[0])

            model_base = model_name.split(":")[0]
            if model_name in model_names or model_base in model_names:
                self._ollama_available = True
                return True

            logger.warning(
                "Ollama model '%s' not found (available: %s)",
                model_name,
                sorted(set(model_names)),
            )
            self._ollama_available = False
            return False

        except (ConnectionRefusedError, TimeoutError, URLError, OSError) as exc:
            logger.warning("Ollama not reachable at %s: %s", base_url, exc)
            self._ollama_available = False
            return False

    def _try_generate_go_mod(
        self,
        file_path: str,
        file_spec: Any,
        context: Dict[str, Any],
    ) -> Optional[str]:
        """Try deterministic go.mod generation from seed metadata (REQ-MLT-103).

        Returns go.mod content string, or None if the file is not a go.mod
        or if generation cannot proceed (missing metadata).
        """
        if Path(file_path).name != "go.mod":
            return None

        try:
            from startd8.languages.registry import LanguageRegistry

            LanguageRegistry.discover()
            profile = LanguageRegistry.get("go")
            if profile is None:
                return None
        except (ImportError, AttributeError):
            return None

        # Extract module path from file_spec or infer from directory
        module_path = ""
        if file_spec is not None:
            # Check for module_path in file_spec metadata
            meta = getattr(file_spec, "metadata", None) or {}
            if isinstance(meta, dict):
                module_path = meta.get("module_path", "")

        if not module_path:
            # Infer from directory structure: src/shippingservice/go.mod
            # → github.com/GoogleCloudPlatform/microservices-demo/src/shippingservice
            parts = Path(file_path).parent.parts
            if parts:
                module_path = "/".join(parts)

        # Extract dependencies from context
        dependencies: List[str] = []
        seed_deps = context.get("dependencies") or []
        if isinstance(seed_deps, list):
            dependencies = [str(d) for d in seed_deps if d]

        # Extract go version from context
        metadata = {}
        go_version = context.get("go_version")
        if go_version:
            metadata["go_version"] = go_version

        content = profile.generate_dependency_file(
            project_root=self._output_dir,
            service_name=Path(file_path).parent.name or "service",
            module_path=module_path,
            dependencies=dependencies,
            metadata=metadata or None,
        )
        return content

    def _try_generate_build_gradle(
        self,
        file_path: str,
        file_spec: Any,
        context: Dict[str, Any],
    ) -> Optional[str]:
        """Try deterministic build.gradle generation from seed metadata.

        Returns build.gradle content string, or None if the file is not a
        build.gradle or if generation cannot proceed (missing metadata).
        """
        name = Path(file_path).name
        if name not in ("build.gradle", "build.gradle.kts"):
            return None

        try:
            from startd8.languages.registry import LanguageRegistry

            LanguageRegistry.discover()
            profile = LanguageRegistry.get("java")
            if profile is None:
                return None
        except (ImportError, AttributeError):
            return None

        # Extract module path / main class from file_spec or context
        module_path = ""
        if file_spec is not None:
            meta = getattr(file_spec, "metadata", None) or {}
            if isinstance(meta, dict):
                module_path = meta.get("main_class", "")

        if not module_path:
            # Infer main class from sibling Application.java or directory name
            parent = Path(file_path).parent
            if parent.name:
                module_path = f"com.example.{parent.name}.Application"

        # Extract dependencies from context
        dependencies: List[str] = []
        seed_deps = context.get("dependencies") or []
        if isinstance(seed_deps, list):
            dependencies = [str(d) for d in seed_deps if d]

        # Extract java version from context
        metadata = {}
        java_version = context.get("java_version")
        if java_version:
            metadata["java_version"] = java_version

        content = profile.generate_dependency_file(
            project_root=self._output_dir,
            service_name=Path(file_path).parent.name or "service",
            module_path=module_path,
            dependencies=dependencies,
            metadata=metadata or None,
        )
        return content

    def _try_generate_package_json(
        self,
        file_path: str,
        file_spec: Any,
        context: Dict[str, Any],
    ) -> Optional[str]:
        """Try deterministic package.json generation from seed metadata (REQ-NODE-103).

        Returns package.json content string, or None if the file is not a
        package.json or if the dependency list is empty (fall through to LLM
        for richer output).
        """
        if Path(file_path).name != "package.json":
            return None

        # Only generate when dependencies are available — an empty package.json
        # is less useful than what the LLM produces with full prompt context.
        dependencies: List[str] = []
        seed_deps = context.get("dependencies") or context.get("runtime_dependencies") or []
        if isinstance(seed_deps, list):
            dependencies = [str(d) for d in seed_deps if d]
        if not dependencies:
            return None

        try:
            from startd8.languages.registry import LanguageRegistry

            LanguageRegistry.discover()
            profile = LanguageRegistry.get("nodejs")
            if profile is None:
                return None
        except (ImportError, AttributeError):
            return None

        service_name = Path(file_path).parent.name or "service"
        content = profile.generate_dependency_file(
            project_root=self._output_dir,
            service_name=service_name,
            module_path="",
            dependencies=dependencies,
        )
        return content

    def _try_generate_csproj(
        self,
        file_path: str,
        file_spec: Any,
        context: Dict[str, Any],
    ) -> Optional[str]:
        """Try deterministic .csproj generation from seed metadata (REQ-CS-103).

        Returns .csproj XML content string, or None if the file is not a
        .csproj or if generation cannot proceed.
        """
        if not file_path.endswith(".csproj"):
            return None

        try:
            from startd8.languages.registry import LanguageRegistry

            LanguageRegistry.discover()
            profile = LanguageRegistry.get("csharp")
            if profile is None:
                return None
        except (ImportError, AttributeError):
            return None

        # Extract dependencies from context
        dependencies: List[str] = []
        seed_deps = (
            context.get("dependencies")
            or context.get("runtime_dependencies")
            or []
        )
        if isinstance(seed_deps, list):
            dependencies = [str(d) for d in seed_deps if d]

        # Extract metadata (target_framework, sdk_type, protobuf_items)
        metadata: Dict[str, Any] = {}
        svc_meta = context.get("service_metadata")
        if isinstance(svc_meta, dict):
            for key in ("target_framework", "sdk_type", "protobuf_items"):
                if key in svc_meta:
                    metadata[key] = svc_meta[key]

        if file_spec is not None:
            spec_meta = getattr(file_spec, "metadata", None) or {}
            if isinstance(spec_meta, dict):
                for key in ("target_framework", "sdk_type", "protobuf_items"):
                    if key in spec_meta and key not in metadata:
                        metadata[key] = spec_meta[key]

        content = profile.generate_dependency_file(
            project_root=self._output_dir,
            service_name=Path(file_path).stem or "service",
            module_path="",
            dependencies=dependencies,
            metadata=metadata or None,
        )
        return content

    def _try_generate_sln(
        self,
        file_path: str,
        file_spec: Any,
        context: Dict[str, Any],
    ) -> Optional[str]:
        """Try deterministic .sln generation from seed metadata (REQ-CS-104).

        Returns .sln file content string, or None if the file is not a .sln
        or if generation cannot proceed.
        """
        if not file_path.endswith(".sln"):
            return None

        try:
            from startd8.languages.registry import LanguageRegistry

            LanguageRegistry.discover()
            profile = LanguageRegistry.get("csharp")
            if profile is None:
                return None
        except (ImportError, AttributeError):
            return None

        # Build project list from context
        import uuid

        projects: List[Dict[str, str]] = []
        all_target = context.get("all_target_files") or []
        for tf in all_target:
            if tf.endswith(".csproj"):
                proj_name = Path(tf).stem
                proj_guid = "{" + str(uuid.uuid5(uuid.NAMESPACE_DNS, tf)).upper() + "}"
                projects.append({
                    "name": proj_name,
                    "path": tf,
                    "guid": proj_guid,
                })

        if not projects:
            return None

        solution_name = Path(file_path).stem
        content = profile.generate_solution_file(
            solution_name=solution_name,
            projects=projects,
        )
        return content

    def _try_generate_appsettings(
        self,
        file_path: str,
        context: Dict[str, Any],
    ) -> Optional[str]:
        """Generate appsettings.json for ASP.NET Core projects.

        Returns JSON config string, or None if the file is not appsettings.json.
        """
        if Path(file_path).name != "appsettings.json":
            return None

        config: Dict[str, Any] = {
            "Logging": {
                "LogLevel": {
                    "Default": "Information",
                    "Microsoft.AspNetCore": "Warning",
                }
            },
            "AllowedHosts": "*",
        }

        # Add database-specific config from context
        security_contract = context.get("security_contract")
        if isinstance(security_contract, dict):
            databases = security_contract.get("databases")
            if isinstance(databases, dict):
                for _db_id, db_info in databases.items():
                    if not isinstance(db_info, dict):
                        continue
                    db_type = str(db_info.get("type", "")).lower()
                    if "redis" in db_type:
                        config["Redis"] = {
                            "ConfigurationString": "redis-cart:6379",
                        }
                    elif "spanner" in db_type:
                        config["Spanner"] = {
                            "Project": "",
                            "Instance": "",
                            "Database": "",
                        }

        return json.dumps(config, indent=2) + "\n"

    def _generate_requirements_in(
        self,
        requirements_file: str,
        st: _GenerationState,
        all_target_files: List[str],
    ) -> Optional[str]:
        """Generate requirements.in deterministically from sibling Python imports.

        Scans already-generated Python files in the same directory as the
        requirements.in target, extracts third-party imports, and maps them
        to PyPI package names.  Returns None if no Python files found.
        """
        from startd8.utils.requirements_generator import generate_requirements_in

        # Find sibling Python files from three sources:
        # 1. Files generated in this run (st.generated_files)
        # 2. Files generated in prior runs (on disk under output_dir)
        # 3. Existing source files from the project root
        req_dir = requirements_file.rsplit("/", 1)[0] if "/" in requirements_file else ""

        python_files: Dict[str, str] = {}

        # 1. Already-generated files from this run
        for gen_path in st.generated_files:
            try:
                rel = str(gen_path.relative_to(self._output_dir))
            except (ValueError, TypeError):
                rel = str(gen_path)
            if rel.endswith(".py") and rel.startswith(req_dir):
                try:
                    python_files[rel] = gen_path.read_text(encoding="utf-8")
                except OSError:
                    pass

        # 2. Files generated in prior runs (on disk under output_dir)
        sibling_dir = self._output_dir / req_dir
        if sibling_dir.is_dir():
            try:
                for py_file in sorted(sibling_dir.glob("*.py")):
                    rel = str(py_file.relative_to(self._output_dir))
                    if rel not in python_files:
                        try:
                            python_files[rel] = py_file.read_text(encoding="utf-8")
                        except OSError:
                            pass
            except OSError:
                pass

        # 2b. Sibling files at project root (catches files deployed by
        #     earlier tasks, e.g., logger.py for recommendationservice)
        pre_2b_count = len(python_files)
        if self._project_root:
            proj_sibling_dir = self._project_root / req_dir
            if proj_sibling_dir.is_dir():
                try:
                    for py_file in sorted(proj_sibling_dir.glob("*.py")):
                        rel = str(py_file.relative_to(self._project_root))
                        if rel not in python_files:
                            try:
                                python_files[rel] = py_file.read_text(
                                    encoding="utf-8"
                                )
                            except OSError:
                                pass
                except OSError:
                    pass
        added_2b = len(python_files) - pre_2b_count
        if added_2b:
            logger.debug(
                "requirements.in scan 2b: %d sibling .py files from project_root/%s",
                added_2b, req_dir,
            )

        # 3. Existing source files from the project root
        if self._manifest:
            for file_path, file_spec in self._manifest.file_specs.items():
                if file_path.endswith(".py") and file_path.startswith(req_dir):
                    if file_path not in python_files:
                        # Try output_dir first (generated), then project root
                        for base in (self._output_dir, Path(".")):
                            full = base / file_path
                            if full.is_file():
                                try:
                                    python_files[file_path] = full.read_text(encoding="utf-8")
                                except OSError:
                                    pass
                                break

        if not python_files:
            logger.info(
                "No sibling Python files found for %s — cannot generate deterministically",
                requirements_file,
            )
            return None

        logger.info(
            "requirements.in scan for %s: %d Python files: %s",
            requirements_file,
            len(python_files),
            ", ".join(sorted(python_files.keys())),
        )

        # Extract manifest-declared external deps as extras (catches deps
        # that aren't visible through import analysis alone)
        extra_packages: list[str] = []
        if self._manifest:
            for fp, fs in self._manifest.file_specs.items():
                if fp.startswith(req_dir) and fs.dependencies:
                    extra_packages.extend(fs.dependencies.external)

        content = generate_requirements_in(
            python_files,
            extra_packages=extra_packages or None,
        )
        return content if content else None

    def _delegate_to_fallback(
        self,
        task: str,
        context: Dict[str, Any],
        target_files: List[str],
    ) -> GenerationResult:
        """Delegate to the fallback code generator.

        Sanitizes the context dict before delegation: Pydantic models
        (e.g. ForwardManifest) are converted to dicts so downstream
        ``json.dumps(context)`` calls in the spec builder don't crash.
        """
        if self._fallback is None:
            return GenerationResult(
                success=False,
                error="No fallback generator configured and elements need cloud processing",
            )
        # Sanitize: recursively convert Pydantic models to dicts for JSON compatibility
        clean_context = _sanitize_for_json(context)
        return self._fallback.generate(task, clean_context, target_files)

    def _resolve_cloud_agent_spec(self) -> str:
        """Resolve the cloud agent spec string for element-level escalation.

        Priority: tier-specific spec from complexity routing →
        explicit ``cloud_agent_spec`` → fallback's ``drafter_agent``
        → ``DRAFT_MODEL_CLAUDE_HAIKU.agent_spec``.
        """
        # D3: Tier-specific agent spec from complexity routing
        if self._tier_agent_spec is not None:
            return self._tier_agent_spec
        if self._cloud_agent_spec is not None:
            return self._cloud_agent_spec
        drafter = getattr(self._fallback, "drafter_agent", None)
        if drafter is not None:
            # drafter_agent may be a string spec or an agent object with a spec
            if isinstance(drafter, str):
                return drafter
            spec = getattr(drafter, "agent_spec", None)
            if isinstance(spec, str):
                return spec
        return DRAFT_MODEL_CLAUDE_HAIKU.agent_spec

    @staticmethod
    def _resolve_cloud_agent_max_tokens(spec: str) -> Optional[int]:
        """Resolve max_tokens for the cloud agent from user config.

        Uses ~/.startd8/config.json model presets when available.
        """
        try:
            from startd8.config import get_config_manager
        except ImportError:
            return None

        config_mgr = get_config_manager()
        provider = ""
        model = spec
        if ":" in spec:
            provider, model = spec.split(":", 1)
        model_lower = model.lower()

        # Map model name to config key.
        key = None
        if "haiku" in model_lower:
            key = "haiku"
        elif "sonnet" in model_lower or "opus" in model_lower:
            key = "claude"
        elif provider == "anthropic":
            key = "claude"
        elif "gpt-4" in model_lower or "gpt4" in model_lower:
            key = "gpt4"

        if not key:
            return None

        cfg = config_mgr.get_model_config(key)
        max_tokens = cfg.get("max_tokens")
        if isinstance(max_tokens, int) and max_tokens > 0:
            return max_tokens
        return None

    def _get_cloud_agent(self) -> BaseAgent:
        """Lazily create a cloud agent for element-level escalation.

        Mirrors ``engine.py:_generate_ollama()`` lazy agent pattern.
        """
        if self._cloud_agent is None:
            from startd8.utils.agent_resolution import resolve_agent_spec

            spec = self._resolve_cloud_agent_spec()
            max_tokens = self._resolve_cloud_agent_max_tokens(spec) or 4096
            self._cloud_agent = resolve_agent_spec(spec, max_tokens=max_tokens)
            logger.debug("Cloud agent created: %s", spec)

        return self._cloud_agent

    def _direct_cloud_generate(
        self,
        element_name: str,
        element_spec: ForwardElementSpec,
        file_spec: ForwardFileSpec,
        contracts: list[InterfaceContract],
        skeleton: str,
        escalation_reason: str = "",
        last_error: str = "",
        retry_context: str = "",
        last_code: str = "",
        raw_output: str = "",
        repaired_code: str = "",
        repair_steps: Optional[list[str]] = None,
        escalation_handoff: Optional["EscalationHandoff"] = None,
    ) -> Optional[tuple[str, int, int]]:
        """Single direct LLM call for one escalated element.

        Returns ``(code, input_tokens, output_tokens)`` or ``None`` on failure.
        """
        from startd8.micro_prime.prompt_builder import build_body_prompt
        from startd8.utils.code_extraction import extract_code_from_response

        prompt = build_body_prompt(
            element_spec, file_spec, contracts,
            skeleton=skeleton, token_budget=4096,
        )

        # Keiyaku (K-6): Use structured handoff when available,
        # falling back to prose injection for backward compatibility.
        if escalation_handoff is not None:
            prompt += "\n\n" + escalation_handoff.to_prompt_section()
            if retry_context:
                prompt += f"\n\n# Retry context: {retry_context}"
        else:
            # Legacy prose injection path — preserved for call sites
            # that don't yet produce an EscalationHandoff.
            if escalation_reason:
                prompt += f"\n\n# Escalation context: {escalation_reason}"
            if last_error:
                prompt += f"\n# Previous error: {last_error}"
            if retry_context:
                prompt += f"\n\n# Retry context: {retry_context}"
            if raw_output or repaired_code or last_code:
                truncated = raw_output or last_code
                if len(truncated) > 2000:
                    truncated = truncated[:2000] + "\n# ... [truncated]"
                prompt += "\n\n# Prior local model attempt:"
                prompt += "\n# Repair steps attempted: "
                prompt += ", ".join(repair_steps or []) or "none"
                prompt += "\n```python\n" + truncated + "\n```"
                if repaired_code and repaired_code != truncated:
                    repaired = repaired_code
                    if len(repaired) > 2000:
                        repaired = repaired[:2000] + "\n# ... [truncated]"
                    prompt += "\n\n# Repaired output:"
                    prompt += "\n```python\n" + repaired + "\n```"

        agent = self._get_cloud_agent()
        result_text, _time_ms, token_usage = agent.generate(
            prompt,
            system_prompt=_CODE_GEN_SYSTEM_PROMPT,
            temperature=0.2,
        )

        code = extract_code_from_response(result_text)
        if not code or not code.strip():
            logger.debug(
                "Cloud agent returned empty code for element %s", element_name,
            )
            return None

        input_tokens = 0
        output_tokens = 0
        if token_usage:
            input_tokens = getattr(token_usage, "input", 0) or 0
            output_tokens = getattr(token_usage, "output", 0) or 0

        return code, input_tokens, output_tokens

    def _escalate_elements_to_cloud(
        self,
        file_path: str,
        file_result: FileResult,
        task: str,
        context: Dict[str, Any],
        manifest: ForwardManifest,
    ) -> Optional[GenerationResult]:
        """Delegate escalated elements via direct per-element cloud LLM calls.

        For each escalated element, builds a prompt using the same
        ``build_body_prompt()`` used by the local engine, makes a single
        cloud LLM call, and splices the result back into the partial skeleton.

        Returns:
            A ``GenerationResult`` for cost/token tracking, or ``None`` if
            there are no elements to escalate or splicing produces no changes.
        """
        from startd8.micro_prime.splicer import splice_body_into_skeleton

        if not file_result.filled_skeleton:
            return None

        file_spec = manifest.file_specs.get(file_path)
        if file_spec is None:
            logger.warning(
                "No file spec in manifest for %s — cannot escalate elements",
                file_path,
            )
            return None

        # Collect escalated element results and their specs.
        # Key by (name, parent_class) to avoid collisions when multiple
        # classes define methods with the same name (e.g. SendOrderConfirmation).
        escalated_elements = []
        spec_by_key: dict[tuple[str, Optional[str]], ForwardElementSpec] = {
            (e.name, e.parent_class): e for e in file_spec.elements
        }
        for er in file_result.element_results:
            if er.escalation is None:
                continue
            key = (er.element_name, er.parent_class)
            spec = spec_by_key.get(key)
            if spec is None:
                # Fallback: match by name only (backward compat)
                spec = next(
                    (e for e in file_spec.elements if e.name == er.element_name),
                    None,
                )
            if spec is not None:
                escalated_elements.append((er, spec))

        if not escalated_elements:
            return None

        element_names = [er.element_name for er, _ in escalated_elements]
        names_str = ", ".join(element_names)
        logger.info(
            "Element-level direct cloud escalation for %s: %d elements (%s)",
            file_path, len(element_names), names_str,
        )

        updated_skeleton = file_result.filled_skeleton
        total_input = 0
        total_output = 0
        spliced_count = 0

        max_attempts = max(1, int(self._config.cloud_escalation_max_attempts))
        strategy = (self._config.cloud_escalation_retry_strategy or "same_prompt").lower()
        if strategy not in ("same_prompt", "append_error"):
            logger.warning(
                "Unknown cloud escalation retry strategy '%s' — defaulting to same_prompt",
                strategy,
            )
            strategy = "same_prompt"
        retry_max_chars = max(0, int(self._config.cloud_escalation_retry_max_chars))

        for er, spec in escalated_elements:
            # Class elements don't have raise NotImplementedError stubs —
            # their methods are handled as separate elements.  Splicing a
            # class body would overwrite locally-filled methods.
            if spec.kind == ElementKind.CLASS:
                logger.debug(
                    "Skipping class element %s — methods handled individually",
                    er.element_name,
                )
                continue

            try:
                contracts = self._engine._get_element_contracts(
                    spec, file_spec, manifest,
                )
                # er.escalation is guaranteed non-None by the filter on L848-850
                escalation_reason = er.escalation.reason.value
                prompt_error = er.escalation.last_error or ""
                last_error = prompt_error
                last_code = er.code or (er.escalation.last_code or "")
                repair_steps = er.repair_steps_applied or []
                raw_output = ""
                repaired_code = ""
                esc_ctx = er.escalation.context if er.escalation else None
                handoff = None
                if esc_ctx:
                    raw_output = esc_ctx.raw_output or ""
                    repaired_code = esc_ctx.repaired_code or ""
                    if esc_ctx.repair_steps_applied:
                        repair_steps = list(esc_ctx.repair_steps_applied)
                    if esc_ctx.error:
                        prompt_error = esc_ctx.error
                        last_error = esc_ctx.error
                    # Keiyaku (K-6): prefer structured handoff when available
                    handoff = esc_ctx.escalation_handoff

                attempts = 0
                success = False
                while attempts < max_attempts and not success:
                    attempts += 1

                    retry_context = ""
                    if attempts > 1 and strategy == "append_error":
                        retry_context = (
                            f"Retry attempt {attempts}/{max_attempts}. "
                            f"Previous failure: {last_error or 'unknown'}"
                        )
                        if retry_max_chars and len(retry_context) > retry_max_chars:
                            retry_context = retry_context[:retry_max_chars]
                    if attempts > 1:
                        logger.info(
                            "Cloud escalation retry for %s in %s (attempt %d/%d, strategy=%s)",
                            er.element_name,
                            file_path,
                            attempts,
                            max_attempts,
                            strategy,
                        )

                    gen_result = self._direct_cloud_generate(
                        er.element_name, spec, file_spec, contracts,
                        updated_skeleton,
                        escalation_reason=escalation_reason,
                        last_error=prompt_error or "",
                        retry_context=retry_context,
                        last_code=last_code,
                        raw_output=raw_output,
                        repaired_code=repaired_code,
                        repair_steps=repair_steps,
                        escalation_handoff=handoff,
                    )
                    if gen_result is None:
                        last_error = "empty_response"
                        if attempts < max_attempts:
                            continue
                        break

                    code, inp_tokens, out_tokens = gen_result

                    # Try AST extraction first (in case cloud returned full def)
                    kind_str = spec.kind.value
                    if kind_str in _FUNCTION_LIKE_KINDS:
                        kind_str = "function"
                    extracted = _extract_element_from_generated(
                        code, er.element_name, kind_str,
                    )
                    extraction_failed = extracted is None
                    splice_source = extracted if extracted is not None else code

                    splice_result = splice_body_into_skeleton(
                        splice_source, spec, updated_skeleton,
                    )
                    if splice_result.code is not None:
                        updated_skeleton = splice_result.code
                        spliced_count += 1
                        success = True
                        total_input += inp_tokens
                        total_output += out_tokens
                        break

                    last_error = "extraction_failed" if extraction_failed else "splice_failed"

                er.cloud_retry_attempts = attempts
                er.cloud_retry_success = success
                er.cloud_retry_strategy = strategy
                er.cloud_retry_last_error = last_error or None

                if not success:
                    logger.debug(
                        "Cloud escalation failed for %s after %d/%d attempts",
                        er.element_name,
                        attempts,
                        max_attempts,
                    )
            except (OSError, ValueError, RuntimeError, TypeError):
                logger.warning(
                    "Cloud escalation failed for element %s in %s, continuing",
                    er.element_name, file_path, exc_info=True,
                )

        if spliced_count > 0:
            output_path = self._output_dir / file_path
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(updated_skeleton, encoding="utf-8")
            logger.info(
                "Spliced %d/%d escalated elements into %s",
                spliced_count, len(escalated_elements), file_path,
            )

        # Compute cost via PricingService
        cost_usd = 0.0
        if total_input > 0 or total_output > 0:
            try:
                from startd8.costs.pricing import PricingService
                pricing = PricingService()
                agent_spec = self._resolve_cloud_agent_spec()
                # Extract model name from provider:model spec
                model_name = agent_spec.split(":")[-1] if ":" in agent_spec else agent_spec
                cost_usd = pricing.calculate_total_cost(
                    model_name, total_input, total_output,
                )
            except ImportError:
                logger.debug("PricingService not available, skipping cost computation")
            except (KeyError, ValueError):
                logger.warning(
                    "Could not compute cost for cloud model %s — pricing data may be missing",
                    model_name, exc_info=True,
                )

        return GenerationResult(
            success=spliced_count > 0,
            generated_files=[self._output_dir / file_path] if spliced_count > 0 else [],
            input_tokens=total_input,
            output_tokens=total_output,
            cost_usd=cost_usd,
            model=self._resolve_cloud_agent_spec(),
        )
