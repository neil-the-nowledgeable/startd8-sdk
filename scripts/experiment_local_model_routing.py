#!/usr/bin/env python3
"""
Experiment: Local Model Routing via Forward Manifest
=====================================================

Tests whether a local Ollama model can reliably fill in function bodies
when given the rich structural context from the Forward Manifest +
deterministic file assembly stubs.

Architecture:
  T1 (Opus)  → Classify each ForwardElementSpec as SIMPLE / MODERATE / COMPLEX
  Local      → Generate bodies for SIMPLE elements (Ollama coding model)
  T2 (Sonnet)→ Assemble + verify coherence of Ollama outputs
  T1/T2      → Final review pass

Usage:
  # Dry-run: classify elements only, no LLM calls
  python3 scripts/experiment_local_model_routing.py \\
      --seed .startd8/seeds/enriched_seed.json \\
      --classify-only

  # Full experiment: classify + generate with Ollama + verify with Sonnet
  python3 scripts/experiment_local_model_routing.py \\
      --seed .startd8/seeds/enriched_seed.json \\
      --ollama-model qwen2.5-coder:7b \\
      --project-root .

  # Use heuristic classifier instead of Opus (zero LLM cost for classification)
  python3 scripts/experiment_local_model_routing.py \\
      --seed .startd8/seeds/enriched_seed.json \\
      --ollama-model codellama \\
      --heuristic-classify

  # Seed has empty forward manifest? Synthesize it from task descriptions first
  python3 scripts/experiment_local_model_routing.py \\
      --seed /path/to/artisan-context-seed-enriched.json \\
      --ollama-model qwen2.5-coder:7b \\
      --synthesize-manifest \\
      --heuristic-classify

  # Skip verification step (Ollama only, no Sonnet review)
  python3 scripts/experiment_local_model_routing.py \\
      --seed .startd8/seeds/enriched_seed.json \\
      --ollama-model qwen2.5-coder:7b \\
      --skip-verify
"""

from __future__ import annotations

import argparse
import ast
import asyncio
import json
import logging
import sys
import textwrap
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional

# ── SDK path setup ──────────────────────────────────────────────────
_src = str(Path(__file__).resolve().parent.parent / "src")
if _src not in sys.path:
    sys.path.insert(0, _src)

from startd8.forward_manifest import (
    ContractCategory,
    ContractConfidence,
    ForwardElementSpec,
    ForwardFileSpec,
    ForwardManifest,
    InterfaceContract,
)
from startd8.logging_config import get_logger
from startd8.seeds.models import ContextSeed, SeedTask
from startd8.utils.agent_resolution import resolve_agent_spec
from startd8.utils.code_manifest import ElementKind, ParamKind, Visibility

logger = get_logger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# Data Models
# ═══════════════════════════════════════════════════════════════════════════


class Complexity(str, Enum):
    """Element complexity classification for model routing."""

    SIMPLE = "simple"
    MODERATE = "moderate"
    COMPLEX = "complex"


@dataclass
class ClassifiedElement:
    """A ForwardElementSpec with its complexity classification and routing."""

    file_path: str
    element: ForwardElementSpec
    complexity: Complexity
    reasoning: str
    # Populated after generation
    generated_code: Optional[str] = None
    generation_time_ms: Optional[float] = None
    generation_tokens: Optional[int] = None
    syntax_valid: Optional[bool] = None
    verification_passed: Optional[bool] = None
    verification_notes: Optional[str] = None
    error: Optional[str] = None

    @property
    def fqn(self) -> str:
        if self.element.parent_class:
            return f"{self.element.parent_class}.{self.element.name}"
        return self.element.name


@dataclass
class ExperimentResult:
    """Aggregate results from the experiment run."""

    total_elements: int = 0
    classified: dict[str, int] = field(
        default_factory=lambda: {"simple": 0, "moderate": 0, "complex": 0}
    )
    ollama_attempted: int = 0
    ollama_succeeded: int = 0
    ollama_syntax_valid: int = 0
    ollama_verified: int = 0
    ollama_failed: int = 0
    total_generation_time_ms: float = 0.0
    total_generation_tokens: int = 0
    verification_cost_usd: float = 0.0
    classification_cost_usd: float = 0.0
    elements: list[ClassifiedElement] = field(default_factory=list)

    @property
    def success_rate(self) -> float:
        if self.ollama_attempted == 0:
            return 0.0
        return self.ollama_syntax_valid / self.ollama_attempted

    @property
    def verified_rate(self) -> float:
        if self.ollama_syntax_valid == 0:
            return 0.0
        return self.ollama_verified / self.ollama_syntax_valid


# ═══════════════════════════════════════════════════════════════════════════
# Heuristic Classifier (zero LLM cost)
# ═══════════════════════════════════════════════════════════════════════════

# Signals that suggest a function is simple enough for a local model.
_SIMPLE_NAME_PREFIXES = ("get_", "is_", "has_", "to_", "from_", "as_")
_SIMPLE_RETURN_TYPES = {
    "str", "int", "float", "bool", "None", "list", "dict",
    "Optional[str]", "Optional[int]", "Optional[float]", "Optional[bool]",
}
_COMPLEX_DECORATORS = {"abstractmethod", "overload", "contextmanager"}

# ── Orchestrator / bootstrap detection ──
# Functions with these names tend to wire together multiple subsystems.
# A local model over-generates (produces entire server setups) on these.
_ORCHESTRATOR_NAMES = {
    "start", "serve", "main", "run", "run_server", "bootstrap",
    "setup", "launch", "initialize", "entrypoint",
}
# Name patterns that suggest multi-step orchestration
_ORCHESTRATOR_SUFFIXES = ("_handler", "_pipeline", "_workflow", "_server")
# Docstring keywords that signal orchestration complexity
_ORCHESTRATOR_DOC_KEYWORDS = (
    "server", "bootstrap", "pipeline", "orchestrat", "initialize",
    "start", "launch", "setup", "wire", "configure all",
)
# Constants that are really app/server instances (Flask, FastAPI, etc.)
_APP_INSTANCE_NAMES = {"app", "application", "server", "api"}


def classify_element_heuristic(
    elem: ForwardElementSpec,
    file_spec: ForwardFileSpec,
    contracts: list[InterfaceContract],
) -> tuple[Complexity, str]:
    """Classify element complexity using manifest signals alone (no LLM).

    Returns (complexity, reasoning) tuple.
    """
    reasons: list[str] = []

    # ── Property: almost always simple ──
    if elem.kind == ElementKind.PROPERTY:
        return Complexity.SIMPLE, "property accessor"

    # ── Constants: simple UNLESS they're app/server instances ──
    if elem.kind in (ElementKind.CONSTANT, ElementKind.VARIABLE):
        if elem.name.lower() in _APP_INSTANCE_NAMES:
            return Complexity.MODERATE, f"app/server instance ({elem.name})"
        return Complexity.SIMPLE, "constant/variable declaration"

    # ── Orchestrator / bootstrap early detection ──
    # These produce full server/pipeline setups that overwhelm local models.
    is_orchestrator = False
    orch_reason = ""

    # Name-based detection applies to all elements
    if elem.name.lower() in _ORCHESTRATOR_NAMES:
        is_orchestrator = True
        orch_reason = f"orchestrator name ({elem.name})"
    elif any(elem.name.lower().endswith(s) for s in _ORCHESTRATOR_SUFFIXES):
        is_orchestrator = True
        orch_reason = f"orchestrator suffix ({elem.name})"
    # Docstring-based detection only for standalone functions (not methods).
    # Methods have class context that constrains their scope; __init__ with
    # "initialize" in the docstring is not an orchestrator.
    elif (
        not elem.parent_class
        and elem.docstring_hint
        and any(kw in elem.docstring_hint.lower() for kw in _ORCHESTRATOR_DOC_KEYWORDS)
    ):
        is_orchestrator = True
        orch_reason = f"orchestrator docstring hint"

    if is_orchestrator:
        # 0 params + orchestrator name = almost certainly a bootstrap function
        real_params = []
        if elem.signature:
            real_params = [p for p in elem.signature.params if p.name not in ("self", "cls")]
        if len(real_params) <= 1:
            return Complexity.MODERATE, f"{orch_reason}; {len(real_params)} params (side-effect heavy)"
        # With params it might still be moderate
        reasons.append(orch_reason)

    # ── Count binding contracts for this element ──
    binding_count = sum(
        1 for c in contracts
        if c.confidence in (ContractConfidence.EXPLICIT, ContractConfidence.INFERRED)
    )

    # ── Signature analysis (for callables) ──
    param_count = 0
    has_kwargs = False
    simple_return = False

    if elem.signature:
        # Exclude 'self' and 'cls' from complexity count
        real_params = [
            p for p in elem.signature.params
            if p.name not in ("self", "cls")
        ]
        param_count = len(real_params)
        has_kwargs = any(
            p.kind in (ParamKind.VAR_POSITIONAL, ParamKind.VAR_KEYWORD)
            for p in real_params
        )
        if elem.signature.return_annotation:
            simple_return = elem.signature.return_annotation in _SIMPLE_RETURN_TYPES

    # ── Decorator complexity ──
    has_complex_decorator = bool(
        set(elem.decorators or []) & _COMPLEX_DECORATORS
    )

    # ── Name prefix heuristic ──
    has_simple_name = any(elem.name.startswith(p) for p in _SIMPLE_NAME_PREFIXES)

    # ── Scoring ──
    complexity_score = 0

    # Param count
    if param_count <= 2:
        complexity_score -= 1
        reasons.append(f"{param_count} params")
    elif param_count >= 5:
        complexity_score += 2
        reasons.append(f"{param_count} params (many)")

    # **kwargs / *args
    if has_kwargs:
        complexity_score += 1
        reasons.append("variadic params")

    # Simple return type
    if simple_return:
        complexity_score -= 1
        reasons.append(f"simple return ({elem.signature.return_annotation})")

    # Simple name
    if has_simple_name:
        complexity_score -= 1
        reasons.append(f"simple name prefix")

    # Binding constraints
    if binding_count == 0:
        complexity_score -= 1
        reasons.append("no binding constraints")
    elif binding_count >= 3:
        complexity_score += 2
        reasons.append(f"{binding_count} binding constraints")

    # Complex decorators
    if has_complex_decorator:
        complexity_score += 2
        reasons.append(f"complex decorators: {elem.decorators}")

    # Async adds moderate complexity
    if elem.kind in (ElementKind.ASYNC_FUNCTION, ElementKind.ASYNC_METHOD):
        complexity_score += 1
        reasons.append("async")

    # Class definition: usually complex (needs methods, state)
    if elem.kind == ElementKind.CLASS:
        complexity_score += 2
        reasons.append("class definition")

    # Docstring hint length as proxy for complexity
    if elem.docstring_hint and len(elem.docstring_hint) > 100:
        complexity_score += 1
        reasons.append("long docstring hint (complex intent)")

    # ── Classify ──
    if complexity_score <= -1:
        return Complexity.SIMPLE, "; ".join(reasons)
    elif complexity_score <= 2:
        return Complexity.MODERATE, "; ".join(reasons)
    else:
        return Complexity.COMPLEX, "; ".join(reasons)


# ═══════════════════════════════════════════════════════════════════════════
# Opus Classifier (LLM-based, more accurate)
# ═══════════════════════════════════════════════════════════════════════════


def _build_classification_prompt(
    elements: list[tuple[str, ForwardElementSpec, list[InterfaceContract]]],
) -> str:
    """Build a batch classification prompt for Opus."""
    items = []
    for file_path, elem, contracts in elements:
        sig_str = ""
        if elem.signature:
            params = []
            for p in elem.signature.params:
                s = p.name
                if p.annotation:
                    s += f": {p.annotation}"
                if p.default:
                    s += f" = {p.default}"
                params.append(s)
            sig_str = f"({', '.join(params)})"
            if elem.signature.return_annotation:
                sig_str += f" -> {elem.signature.return_annotation}"

        fqn = f"{elem.parent_class}.{elem.name}" if elem.parent_class else elem.name
        contract_strs = [
            f"  [{c.confidence.value}] {c.category.value}: {c.binding_text[:120]}"
            for c in contracts
        ]

        items.append(
            f"- file: {file_path}\n"
            f"  element: {elem.kind.value} {fqn}{sig_str}\n"
            f"  decorators: {elem.decorators or []}\n"
            f"  docstring_hint: {(elem.docstring_hint or '')[:150]}\n"
            f"  contracts:\n" + "\n".join(contract_strs or ["    (none)"])
        )

    return textwrap.dedent("""\
        You are classifying code elements for model routing. Each element will have
        its function body generated by either a local model (Ollama) or a cloud model.

        Classify each element as:
        - SIMPLE: Pure data transforms, lookups, forwarding, config access, property
          accessors, simple validation, string formatting. A 7B coding model can handle
          these reliably given the full signature and type hints.
        - MODERATE: Requires some logic (conditionals, loops, error handling) but is
          self-contained. A 7B model might succeed but with lower reliability.
        - COMPLEX: Requires understanding of external APIs, complex state management,
          multi-step algorithms, or cross-cutting concerns. Needs a stronger model.

        Elements to classify:

        {elements}

        Respond with a JSON array. Each entry must have:
        - "fqn": the fully-qualified element name
        - "complexity": "simple" | "moderate" | "complex"
        - "reasoning": 1 sentence explaining why

        Return ONLY the JSON array, no markdown fences.
    """).format(elements="\n".join(items))


async def classify_elements_with_opus(
    elements: list[tuple[str, ForwardElementSpec, list[InterfaceContract]]],
    agent_spec: str = "anthropic:claude-opus-4-6",
) -> tuple[dict[str, tuple[Complexity, str]], float]:
    """Classify elements using Opus. Returns (fqn→(complexity,reasoning), cost_usd)."""
    if not elements:
        return {}, 0.0

    agent = resolve_agent_spec(agent_spec, max_tokens=4096)
    prompt = _build_classification_prompt(elements)

    result_text, time_ms, token_usage = await agent.agenerate(prompt)

    # Parse JSON response
    try:
        # Strip markdown fences if present
        text = result_text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0]
        classifications = json.loads(text)
    except (json.JSONDecodeError, IndexError):
        logger.error("Failed to parse Opus classification response")
        return {}, token_usage.cost_estimate if token_usage else 0.0

    result = {}
    for entry in classifications:
        fqn = entry.get("fqn", "")
        complexity = Complexity(entry.get("complexity", "complex"))
        reasoning = entry.get("reasoning", "")
        result[fqn] = (complexity, reasoning)

    cost = token_usage.cost_estimate if token_usage else 0.0
    return result, cost


# ═══════════════════════════════════════════════════════════════════════════
# Phase 0: Manifest Synthesis (when seed has empty file_specs)
# ═══════════════════════════════════════════════════════════════════════════


def _build_synthesis_prompt(tasks: list[SeedTask]) -> str:
    """Build a prompt for Opus to extract ForwardElementSpec entries from
    task descriptions when api_signatures are empty."""
    task_blocks = []
    for t in tasks:
        target_files = ", ".join(t.target_files) if t.target_files else "(none)"
        task_blocks.append(
            f"- task_id: {t.task_id}\n"
            f"  title: {t.title}\n"
            f"  target_files: [{target_files}]\n"
            f"  estimated_loc: {t.estimated_loc}\n"
            f"  description: {t.description[:500]}"
        )

    return textwrap.dedent("""\
        You are extracting a structural code manifest from task descriptions.
        For each task, identify the Python classes, functions, and methods that
        need to be implemented. Extract precise signatures with type hints.

        Tasks:

        {tasks}

        For each task, produce a JSON object with:
        - "task_id": the task ID
        - "file": the primary target file path
        - "elements": array of elements, each with:
          - "kind": "class" | "function" | "async_function" | "method" | "async_method" | "property" | "constant"
          - "name": the element name
          - "parent_class": owning class name (for methods/properties), or null
          - "signature": object with "params" (array of {{"name", "annotation", "default", "kind"}}) and "return_annotation" (string or null). kind is one of: "positional", "keyword", "var_positional", "var_keyword", "positional_only", "keyword_only"
          - "bases": array of base class names (for classes only, else [])
          - "decorators": array of decorator names (e.g. ["staticmethod"])
          - "visibility": "public" | "protected" | "private"
          - "docstring_hint": 1-sentence description of what this element does
        - "imports": array of {{"kind": "import"|"from", "module": str, "names": [str]}}

        Rules:
        - Include `self` as first param for methods (kind="positional")
        - Use realistic Python type annotations based on the description
        - For classes, list all methods that the description implies
        - Prefer specific types over Any
        - Only include elements clearly implied by the description

        Return a JSON array of task objects. No markdown fences.
    """).format(tasks="\n\n".join(task_blocks))


async def synthesize_manifest(
    tasks: list[SeedTask],
    existing_manifest: ForwardManifest,
    agent_spec: str = "anthropic:claude-opus-4-6",
    ollama_model: Optional[str] = None,
) -> tuple[ForwardManifest, float]:
    """Synthesize ForwardFileSpec entries from task descriptions using Opus.

    Merges results into the existing manifest (preserving any existing contracts).
    Returns (enriched_manifest, cost_usd).
    """
    if not tasks:
        return existing_manifest, 0.0

    # Only synthesize for tasks with target files but no file_specs coverage
    covered_files = set(existing_manifest.file_specs.keys())
    uncovered_tasks = [
        t for t in tasks
        if t.target_files and not all(f in covered_files for f in t.target_files)
    ]

    if not uncovered_tasks:
        logger.info("All task files already covered by manifest — skipping synthesis")
        return existing_manifest, 0.0

    # Use Ollama if specified, otherwise cloud agent
    if ollama_model:
        spec = f"ollama:{ollama_model}"
        logger.info(f"Synthesizing manifest for {len(uncovered_tasks)} uncovered tasks with {spec}...")
    else:
        spec = agent_spec
        logger.info(f"Synthesizing manifest for {len(uncovered_tasks)} uncovered tasks with {spec}...")

    agent = resolve_agent_spec(spec, max_tokens=8192)
    prompt = _build_synthesis_prompt(uncovered_tasks)

    result_text, _, token_usage = await agent.agenerate(prompt)

    logger.debug(f"Synthesis raw response ({len(result_text)} chars):\n{result_text[:2000]}")

    # Parse response — try multiple strategies for LLM JSON extraction
    task_specs = None
    text = result_text.strip()

    # Strategy 1: Strip markdown fences
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()

    # Strategy 2: Direct JSON parse
    try:
        task_specs = json.loads(text)
    except json.JSONDecodeError:
        pass

    # Strategy 3: Find first [ ... ] or { ... } block
    if task_specs is None:
        import re
        # Try array
        m = re.search(r'\[.*\]', text, re.DOTALL)
        if m:
            try:
                task_specs = json.loads(m.group())
            except json.JSONDecodeError:
                pass
        # Try object (wrap in array)
        if task_specs is None:
            m = re.search(r'\{.*\}', text, re.DOTALL)
            if m:
                try:
                    obj = json.loads(m.group())
                    task_specs = [obj] if isinstance(obj, dict) else obj
                except json.JSONDecodeError:
                    pass

    # Strategy 4: Try line-by-line JSON objects (streaming style)
    if task_specs is None:
        task_specs = []
        for line in text.split("\n"):
            line = line.strip().rstrip(",")
            if line.startswith("{"):
                try:
                    task_specs.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

    if not task_specs:
        logger.error(
            f"Failed to parse manifest synthesis response. "
            f"Raw output ({len(result_text)} chars):\n{result_text[:500]}"
        )
        return existing_manifest, token_usage.cost_estimate if token_usage else 0.0

    # Normalize: if the LLM returned a single dict, wrap it
    if isinstance(task_specs, dict):
        task_specs = [task_specs]

    logger.info(f"Parsed {len(task_specs)} task specs from synthesis response")

    # Build ForwardFileSpec entries from Opus response
    from startd8.utils.code_manifest import Param, Signature

    new_file_specs: dict[str, ForwardFileSpec] = dict(existing_manifest.file_specs)

    for task_spec in task_specs:
        file_path = task_spec.get("file", "")
        if not file_path or file_path in new_file_specs:
            continue

        raw_elements = task_spec.get("elements", [])
        elements: list[ForwardElementSpec] = []

        for raw in raw_elements:
            try:
                # Build Signature if present
                sig = None
                raw_sig = raw.get("signature")
                if raw_sig:
                    params = []
                    for rp in raw_sig.get("params", []):
                        pk = rp.get("kind", "positional")
                        # Validate against ParamKind enum
                        try:
                            param_kind = ParamKind(pk)
                        except ValueError:
                            param_kind = ParamKind.POSITIONAL
                        params.append(Param(
                            name=rp["name"],
                            annotation=rp.get("annotation"),
                            default=rp.get("default"),
                            kind=param_kind,
                        ))
                    sig = Signature(
                        params=params,
                        return_annotation=raw_sig.get("return_annotation"),
                    )

                kind_str = raw.get("kind", "function")
                try:
                    kind = ElementKind(kind_str)
                except ValueError:
                    kind = ElementKind.FUNCTION

                vis_str = raw.get("visibility", "public")
                try:
                    vis = Visibility(vis_str)
                except ValueError:
                    vis = Visibility.PUBLIC

                elements.append(ForwardElementSpec(
                    kind=kind,
                    name=raw["name"],
                    parent_class=raw.get("parent_class"),
                    signature=sig,
                    bases=raw.get("bases", []),
                    decorators=raw.get("decorators", []),
                    visibility=vis,
                    docstring_hint=raw.get("docstring_hint"),
                ))
            except Exception as e:
                logger.warning(f"Skipping malformed element {raw.get('name', '?')}: {e}")
                continue

        # Build imports
        raw_imports = task_spec.get("imports", [])
        from startd8.forward_manifest import ForwardImportSpec, ForwardDependencies
        imports = []
        for ri in raw_imports:
            try:
                imports.append(ForwardImportSpec(
                    kind=ri.get("kind", "import"),
                    module=ri["module"],
                    names=ri.get("names", []),
                ))
            except Exception:
                continue

        if elements:
            new_file_specs[file_path] = ForwardFileSpec(
                file=file_path,
                elements=elements,
                imports=imports,
            )

    # Build enriched manifest
    enriched = ForwardManifest(
        schema_version=existing_manifest.schema_version,
        pipeline_run_id=existing_manifest.pipeline_run_id,
        generated_at=existing_manifest.generated_at,
        contracts=list(existing_manifest.contracts),
        file_specs=new_file_specs,
        stages_completed=list(existing_manifest.stages_completed) + ["experiment_synthesis"],
    )

    cost = token_usage.cost_estimate if token_usage else 0.0
    logger.info(
        f"Synthesized {len(new_file_specs) - len(existing_manifest.file_specs)} new file_specs "
        f"(${cost:.4f})"
    )
    return enriched, cost


# ═══════════════════════════════════════════════════════════════════════════
# Ollama Code Generator
# ═══════════════════════════════════════════════════════════════════════════


def _build_element_stub(elem: ForwardElementSpec) -> str:
    """Render a single element as a Python stub (what the deterministic assembler
    would produce). This is the code the LLM sees and must fill in."""
    lines: list[str] = []
    indent = "    " if elem.parent_class else ""

    # Decorators
    for dec in (elem.decorators or []):
        lines.append(f"{indent}@{dec}")

    # Definition line
    prefix = "async def" if elem.kind in (
        ElementKind.ASYNC_FUNCTION, ElementKind.ASYNC_METHOD
    ) else "def"

    if elem.kind == ElementKind.PROPERTY:
        prefix = "def"
        if "property" not in (elem.decorators or []):
            lines.append(f"{indent}@property")

    if elem.kind == ElementKind.CLASS:
        bases = f"({', '.join(elem.bases)})" if elem.bases else ""
        lines.append(f"class {elem.name}{bases}:")
    else:
        # Build signature
        params = []
        if elem.signature:
            for p in elem.signature.params:
                s = p.name
                if p.annotation:
                    s += f": {p.annotation}"
                if p.default:
                    s += f" = {p.default}"
                params.append(s)
        sig = ", ".join(params)
        ret = ""
        if elem.signature and elem.signature.return_annotation:
            ret = f" -> {elem.signature.return_annotation}"
        lines.append(f"{indent}{prefix} {elem.name}({sig}){ret}:")

    # Docstring
    body_indent = indent + "    " if elem.kind != ElementKind.CLASS else "    "
    if elem.docstring_hint:
        lines.append(f'{body_indent}"""{ elem.docstring_hint}"""')

    # Stub body
    lines.append(f"{body_indent}raise NotImplementedError")

    return "\n".join(lines)


def _build_ollama_prompt(
    elem: ForwardElementSpec,
    file_spec: ForwardFileSpec,
    contracts: list[InterfaceContract],
) -> str:
    """Build a focused prompt for Ollama to fill in a single element body."""
    stub = _build_element_stub(elem)

    # Render imports for context
    import_lines = []
    for imp in file_spec.imports:
        if imp.kind == "from":
            names = ", ".join(imp.names)
            import_lines.append(f"from {imp.module} import {names}")
        else:
            alias = f" as {imp.alias}" if imp.alias else ""
            import_lines.append(f"import {imp.module}{alias}")

    # Render sibling elements (just signatures, not bodies) for class context
    sibling_stubs = []
    if elem.parent_class:
        for sib in file_spec.elements:
            if sib.parent_class == elem.parent_class and sib.name != elem.name:
                if sib.signature:
                    params = ", ".join(
                        f"{p.name}: {p.annotation}" if p.annotation else p.name
                        for p in sib.signature.params
                    )
                    ret = f" -> {sib.signature.return_annotation}" if sib.signature.return_annotation else ""
                    sibling_stubs.append(f"    def {sib.name}({params}){ret}: ...")

    # Render binding constraints
    constraint_lines = []
    for c in contracts:
        prefix = "[BINDING]" if c.confidence != ContractConfidence.TENTATIVE else "[ADVISORY]"
        constraint_lines.append(f"{prefix} {c.binding_text}")

    sections = [
        "# Task: Implement the function body below.",
        "# Replace `raise NotImplementedError` with a working implementation.",
        "# Return ONLY the complete function (with signature and body), no explanation.",
        "",
    ]

    if import_lines:
        sections.append("# Available imports:")
        sections.extend(import_lines)
        sections.append("")

    if sibling_stubs:
        sections.append("# Other methods in this class (for context):")
        sections.extend(sibling_stubs)
        sections.append("")

    if constraint_lines:
        sections.append("# Constraints:")
        sections.extend(constraint_lines)
        sections.append("")

    sections.append("# Implement this:")
    sections.append(stub)

    return "\n".join(sections)


async def generate_with_ollama(
    elem: ClassifiedElement,
    file_spec: ForwardFileSpec,
    contracts: list[InterfaceContract],
    ollama_model: str,
    max_tokens: int = 2048,
) -> None:
    """Generate a single element body using Ollama. Mutates elem in place."""
    try:
        agent = resolve_agent_spec(
            f"ollama:{ollama_model}",
            max_tokens=max_tokens,
        )
        prompt = _build_ollama_prompt(elem.element, file_spec, contracts)

        start = time.monotonic()
        result_text, time_ms, token_usage = await agent.agenerate(prompt)
        elem.generation_time_ms = time_ms or (time.monotonic() - start) * 1000

        if token_usage:
            elem.generation_tokens = (token_usage.input or 0) + (token_usage.output or 0)

        # Extract just the function/method code
        from startd8.utils.code_extraction import extract_code_from_response
        code = extract_code_from_response(result_text)

        if not code or not code.strip():
            elem.error = "Empty response from Ollama"
            elem.syntax_valid = False
            return

        elem.generated_code = code

        # Validate syntax
        try:
            # Wrap method-level code in a class for valid syntax
            if elem.element.parent_class:
                wrapped = f"class _Wrapper:\n" + textwrap.indent(code, "    ")
                ast.parse(wrapped)
            else:
                ast.parse(code)
            elem.syntax_valid = True
        except SyntaxError as e:
            elem.syntax_valid = False
            elem.error = f"SyntaxError: {e}"

    except Exception as e:
        elem.error = str(e)
        elem.syntax_valid = False


# ═══════════════════════════════════════════════════════════════════════════
# Sonnet Verifier
# ═══════════════════════════════════════════════════════════════════════════


async def verify_with_sonnet(
    elements: list[ClassifiedElement],
    agent_spec: str = "anthropic:claude-sonnet-4-6",
) -> float:
    """Verify Ollama-generated code using Sonnet. Returns cost in USD."""
    valid_elements = [e for e in elements if e.syntax_valid and e.generated_code]
    if not valid_elements:
        return 0.0

    agent = resolve_agent_spec(agent_spec, max_tokens=4096)

    # Build batch verification prompt with explicit FQN labels
    items = []
    fqn_list = []
    for i, elem in enumerate(valid_elements, 1):
        fqn_list.append(elem.fqn)
        items.append(
            f"### [{i}] fqn=\"{elem.fqn}\" file=\"{elem.file_path}\"\n"
            f"```python\n{elem.generated_code}\n```"
        )

    prompt = textwrap.dedent("""\
        Review the following function implementations generated by a local coding model.
        For each function, check:
        1. Does it correctly implement what the signature and docstring describe?
        2. Are there obvious bugs, missing edge cases, or incorrect logic?
        3. Does it use the correct return type?

        Rate each as PASS or FAIL with a brief reason.

        {items}

        Respond with a JSON array of exactly {count} entries, one per function above.
        Each entry MUST use the exact fqn string shown in brackets:
        - "fqn": the exact fqn string from the header (e.g. "{example_fqn}")
        - "verdict": "pass" | "fail"
        - "reason": 1 sentence

        Return ONLY the JSON array, no markdown fences.
    """).format(
        items="\n\n".join(items),
        count=len(valid_elements),
        example_fqn=fqn_list[0] if fqn_list else "MyClass.my_method",
    )

    result_text, _, token_usage = await agent.agenerate(prompt)

    try:
        text = result_text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0]
        verdicts = json.loads(text)
    except (json.JSONDecodeError, IndexError):
        logger.error("Failed to parse Sonnet verification response")
        return token_usage.cost_estimate if token_usage else 0.0

    # Build lookup with multiple keys for fuzzy FQN matching
    verdict_map: dict[str, dict] = {}
    for v in verdicts:
        fqn = v.get("fqn", "")
        verdict_map[fqn] = v
        # Also index by short name (e.g. "Check" for "HealthCheck.Check")
        if "." in fqn:
            verdict_map[fqn.split(".")[-1]] = v
        # Also index by lowercase
        verdict_map[fqn.lower()] = v

    for elem in valid_elements:
        # Try exact match, then short name, then lowercase
        v = (
            verdict_map.get(elem.fqn)
            or verdict_map.get(elem.element.name)
            or verdict_map.get(elem.fqn.lower())
            or verdict_map.get(f"{elem.file_path}:{elem.element.name}")
        )
        if v:
            elem.verification_passed = v.get("verdict", "").lower() == "pass"
            elem.verification_notes = v.get("reason", "")
        else:
            elem.verification_passed = None
            elem.verification_notes = "Not in verification response"

    return token_usage.cost_estimate if token_usage else 0.0


# ═══════════════════════════════════════════════════════════════════════════
# Experiment Orchestrator
# ═══════════════════════════════════════════════════════════════════════════


def load_manifest_from_seed(seed_path: Path) -> tuple[ForwardManifest, list[SeedTask]]:
    """Load ForwardManifest and tasks from an enriched seed file."""
    data = json.loads(seed_path.read_text(encoding="utf-8"))

    # Extract forward_manifest directly from raw dict — avoids ContextSeed
    # constructor issues with unexpected keys like _preflight
    fm_data = data.get("forward_manifest", {})

    if not fm_data:
        # Return empty manifest — caller can synthesize if --synthesize-manifest
        manifest = ForwardManifest()
    else:
        manifest = ForwardManifest.model_validate(fm_data)

    # Parse tasks
    tasks = []
    for entry in data.get("tasks", []):
        tasks.append(SeedTask.from_seed_entry(entry))

    return manifest, tasks


def collect_elements(
    manifest: ForwardManifest,
    tasks: list[SeedTask],
) -> list[tuple[str, ForwardFileSpec, ForwardElementSpec, list[InterfaceContract]]]:
    """Collect all classifiable elements from the manifest, scoped to tasks."""
    results = []

    # Build task ID set for contract scoping
    task_ids = {t.task_id for t in tasks}

    for file_path, file_spec in sorted(manifest.file_specs.items()):
        # Get contracts applicable to any of our tasks for this file
        all_contracts: list[InterfaceContract] = []
        for tid in task_ids:
            all_contracts.extend(manifest.contracts_for_task(tid))
        # Deduplicate by contract_id
        seen = set()
        unique_contracts = []
        for c in all_contracts:
            if c.contract_id not in seen:
                seen.add(c.contract_id)
                unique_contracts.append(c)

        for elem in file_spec.elements:
            # Skip class definitions (we classify their methods individually)
            if elem.kind == ElementKind.CLASS:
                continue
            results.append((file_path, file_spec, elem, unique_contracts))

    return results


async def run_experiment(args: argparse.Namespace) -> ExperimentResult:
    """Main experiment loop."""
    result = ExperimentResult()

    # ── Load data ──
    seed_path = Path(args.seed)
    logger.info(f"Loading seed: {seed_path}")
    manifest, tasks = load_manifest_from_seed(seed_path)

    logger.info(
        f"Manifest: {len(manifest.file_specs)} files, "
        f"{len(manifest.contracts)} contracts"
    )

    # ── Phase 0: Synthesize manifest if needed ──
    if args.synthesize_manifest and len(manifest.file_specs) == 0:
        synth_model = args.synthesis_model  # None = use Opus (default)
        if synth_model:
            logger.info(f"Phase 0: Synthesizing manifest from task descriptions (ollama:{synth_model})...")
            manifest, synthesis_cost = await synthesize_manifest(
                tasks, manifest, ollama_model=synth_model,
            )
        else:
            logger.info("Phase 0: Synthesizing manifest from task descriptions (Opus)...")
            manifest, synthesis_cost = await synthesize_manifest(tasks, manifest)
        result.classification_cost_usd += synthesis_cost
        logger.info(
            f"After synthesis: {len(manifest.file_specs)} files, "
            f"{len(manifest.contracts)} contracts"
        )

        # Optionally save the synthesized manifest for reuse
        if args.output:
            synth_path = Path(args.output).parent / "synthesized-manifest.json"
            synth_path.parent.mkdir(parents=True, exist_ok=True)
            synth_path.write_text(
                manifest.model_dump_json(indent=2), encoding="utf-8"
            )
            logger.info(f"Saved synthesized manifest to {synth_path}")
    elif len(manifest.file_specs) == 0:
        logger.warning(
            "Manifest has 0 file_specs. Use --synthesize-manifest to have Opus "
            "extract structural elements from task descriptions."
        )
        return result

    # ── Collect elements ──
    elements = collect_elements(manifest, tasks)
    result.total_elements = len(elements)
    logger.info(f"Collected {len(elements)} classifiable elements")

    if not elements:
        logger.warning("No elements to classify. Check seed has forward_manifest with file_specs.")
        return result

    # ── Phase 1: Classify ──
    logger.info("Phase 1: Classifying elements...")

    classified: list[ClassifiedElement] = []

    if args.heuristic_classify:
        # Zero-cost heuristic classification
        for file_path, file_spec, elem, contracts in elements:
            complexity, reasoning = classify_element_heuristic(elem, file_spec, contracts)
            classified.append(ClassifiedElement(
                file_path=file_path,
                element=elem,
                complexity=complexity,
                reasoning=reasoning,
            ))
    else:
        # Opus-based classification (batched)
        batch = [(fp, elem, contracts) for fp, _, elem, contracts in elements]
        classifications, cost = await classify_elements_with_opus(batch)
        result.classification_cost_usd = cost

        for file_path, file_spec, elem, contracts in elements:
            fqn = f"{elem.parent_class}.{elem.name}" if elem.parent_class else elem.name
            if fqn in classifications:
                complexity, reasoning = classifications[fqn]
            else:
                # Fallback to heuristic if Opus missed this element
                complexity, reasoning = classify_element_heuristic(elem, file_spec, contracts)
                reasoning = f"(heuristic fallback) {reasoning}"

            classified.append(ClassifiedElement(
                file_path=file_path,
                element=elem,
                complexity=complexity,
                reasoning=reasoning,
            ))

    # Tally classifications
    for ce in classified:
        result.classified[ce.complexity.value] += 1
    result.elements = classified

    logger.info(
        f"Classification: "
        f"{result.classified['simple']} simple, "
        f"{result.classified['moderate']} moderate, "
        f"{result.classified['complex']} complex"
    )

    if args.classify_only:
        return result

    # ── Phase 2: Generate with Ollama ──
    simple_elements = [ce for ce in classified if ce.complexity == Complexity.SIMPLE]
    result.ollama_attempted = len(simple_elements)

    if not simple_elements:
        logger.info("No SIMPLE elements to generate. Done.")
        return result

    logger.info(f"Phase 2: Generating {len(simple_elements)} SIMPLE elements with ollama:{args.ollama_model}")

    # Build file_spec and contracts lookup
    file_spec_map = manifest.file_specs
    task_ids = {t.task_id for t in tasks}

    for ce in simple_elements:
        file_spec = file_spec_map.get(ce.file_path)
        if not file_spec:
            ce.error = f"No file_spec for {ce.file_path}"
            continue

        # Get applicable contracts
        all_contracts: list[InterfaceContract] = []
        for tid in task_ids:
            all_contracts.extend(manifest.contracts_for_task(tid))
        seen = set()
        contracts = []
        for c in all_contracts:
            if c.contract_id not in seen:
                seen.add(c.contract_id)
                contracts.append(c)

        await generate_with_ollama(
            ce, file_spec, contracts,
            ollama_model=args.ollama_model,
            max_tokens=args.max_tokens,
        )

        status = "OK" if ce.syntax_valid else f"FAIL ({ce.error})"
        logger.info(
            f"  {ce.fqn}: {status} "
            f"({ce.generation_time_ms:.0f}ms, {ce.generation_tokens or 0} tokens)"
        )

    # Tally generation results
    for ce in simple_elements:
        if ce.syntax_valid:
            result.ollama_syntax_valid += 1
            result.ollama_succeeded += 1
        elif ce.error:
            result.ollama_failed += 1
        if ce.generation_time_ms:
            result.total_generation_time_ms += ce.generation_time_ms
        if ce.generation_tokens:
            result.total_generation_tokens += ce.generation_tokens

    logger.info(
        f"Generation: {result.ollama_syntax_valid}/{result.ollama_attempted} syntax-valid "
        f"({result.success_rate:.0%})"
    )

    # ── Phase 3: Verify with Sonnet ──
    if not args.skip_verify:
        valid_elements = [ce for ce in simple_elements if ce.syntax_valid]
        if valid_elements:
            logger.info(f"Phase 3: Verifying {len(valid_elements)} elements with Sonnet...")
            result.verification_cost_usd = await verify_with_sonnet(valid_elements)

            result.ollama_verified = sum(
                1 for ce in valid_elements if ce.verification_passed
            )
            logger.info(
                f"Verification: {result.ollama_verified}/{len(valid_elements)} passed "
                f"({result.verified_rate:.0%})"
            )

    return result


# ═══════════════════════════════════════════════════════════════════════════
# Report
# ═══════════════════════════════════════════════════════════════════════════


def print_report(result: ExperimentResult, args: argparse.Namespace) -> None:
    """Print a summary report of the experiment."""
    print("\n" + "=" * 70)
    print("  LOCAL MODEL ROUTING EXPERIMENT — RESULTS")
    print("=" * 70)

    print(f"\n  Seed: {args.seed}")
    if hasattr(args, "ollama_model") and args.ollama_model:
        print(f"  Ollama model: {args.ollama_model}")
    print(f"  Classifier: {'heuristic' if args.heuristic_classify else 'opus'}")

    print(f"\n  --- Classification ---")
    print(f"  Total elements:  {result.total_elements}")
    print(f"  SIMPLE:          {result.classified['simple']}")
    print(f"  MODERATE:        {result.classified['moderate']}")
    print(f"  COMPLEX:         {result.classified['complex']}")

    if result.classification_cost_usd > 0:
        print(f"  Classification cost: ${result.classification_cost_usd:.4f}")

    if result.ollama_attempted > 0:
        print(f"\n  --- Ollama Generation ---")
        print(f"  Attempted:       {result.ollama_attempted}")
        print(f"  Syntax valid:    {result.ollama_syntax_valid} ({result.success_rate:.0%})")
        print(f"  Failed:          {result.ollama_failed}")
        print(f"  Total time:      {result.total_generation_time_ms:.0f}ms")
        print(f"  Total tokens:    {result.total_generation_tokens}")
        if result.ollama_attempted > 0:
            avg_ms = result.total_generation_time_ms / result.ollama_attempted
            print(f"  Avg time/elem:   {avg_ms:.0f}ms")

    if result.ollama_verified > 0 or result.verification_cost_usd > 0:
        print(f"\n  --- Sonnet Verification ---")
        print(f"  Verified:        {result.ollama_verified}/{result.ollama_syntax_valid} ({result.verified_rate:.0%})")
        print(f"  Verification cost: ${result.verification_cost_usd:.4f}")

    total_cost = result.classification_cost_usd + result.verification_cost_usd
    if total_cost > 0:
        print(f"\n  --- Cost Summary ---")
        print(f"  Total cloud cost: ${total_cost:.4f}")
        print(f"  Ollama cost:      $0.0000 (local)")

    # Detail table
    print(f"\n  --- Element Details ---")
    print(f"  {'Element':<40} {'Class':<10} {'Syntax':<8} {'Verify':<8} {'ms':<8}")
    print(f"  {'-'*40} {'-'*10} {'-'*8} {'-'*8} {'-'*8}")

    for ce in result.elements:
        fqn = ce.fqn[:39]
        comp = ce.complexity.value
        syn = ""
        ver = ""
        ms = ""
        if ce.syntax_valid is not None:
            syn = "OK" if ce.syntax_valid else "FAIL"
        if ce.verification_passed is not None:
            ver = "PASS" if ce.verification_passed else "FAIL"
        if ce.generation_time_ms is not None:
            ms = f"{ce.generation_time_ms:.0f}"

        print(f"  {fqn:<40} {comp:<10} {syn:<8} {ver:<8} {ms:<8}")

    # Failed elements detail
    failed = [ce for ce in result.elements if ce.error]
    if failed:
        print(f"\n  --- Failures ---")
        for ce in failed:
            print(f"  {ce.fqn}: {ce.error}")

    # Verification failures detail
    ver_failed = [ce for ce in result.elements if ce.verification_passed is False]
    if ver_failed:
        print(f"\n  --- Verification Failures ---")
        for ce in ver_failed:
            print(f"  {ce.fqn}: {ce.verification_notes}")

    print("\n" + "=" * 70)

    # Write JSON results
    output_path = Path(args.output) if args.output else None
    if output_path:
        report = {
            "seed": str(args.seed),
            "ollama_model": getattr(args, "ollama_model", None),
            "classifier": "heuristic" if args.heuristic_classify else "opus",
            "total_elements": result.total_elements,
            "classified": result.classified,
            "ollama_attempted": result.ollama_attempted,
            "ollama_syntax_valid": result.ollama_syntax_valid,
            "ollama_verified": result.ollama_verified,
            "success_rate": result.success_rate,
            "verified_rate": result.verified_rate,
            "total_generation_time_ms": result.total_generation_time_ms,
            "total_generation_tokens": result.total_generation_tokens,
            "classification_cost_usd": result.classification_cost_usd,
            "verification_cost_usd": result.verification_cost_usd,
            "elements": [
                {
                    "fqn": ce.fqn,
                    "file_path": ce.file_path,
                    "kind": ce.element.kind.value,
                    "complexity": ce.complexity.value,
                    "reasoning": ce.reasoning,
                    "syntax_valid": ce.syntax_valid,
                    "verification_passed": ce.verification_passed,
                    "verification_notes": ce.verification_notes,
                    "generation_time_ms": ce.generation_time_ms,
                    "generation_tokens": ce.generation_tokens,
                    "error": ce.error,
                }
                for ce in result.elements
            ],
        }
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"\n  Results written to: {output_path}")


# ═══════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Experiment: Local model routing via Forward Manifest",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--seed", required=True,
        help="Path to enriched seed JSON (must contain forward_manifest)",
    )
    parser.add_argument(
        "--ollama-model", default="qwen2.5-coder:7b",
        help="Ollama model to use for SIMPLE element generation (default: qwen2.5-coder:7b)",
    )
    parser.add_argument(
        "--project-root", default=".",
        help="Project root directory (default: current directory)",
    )
    parser.add_argument(
        "--classify-only", action="store_true",
        help="Only classify elements, don't generate code",
    )
    parser.add_argument(
        "--synthesize-manifest", action="store_true",
        help="Synthesize ForwardFileSpec entries from task descriptions "
             "(needed when seed has empty file_specs)",
    )
    parser.add_argument(
        "--synthesis-model", default=None,
        help="Ollama model for manifest synthesis (default: same as --ollama-model). "
             "Uses local Ollama instead of cloud API.",
    )
    parser.add_argument(
        "--heuristic-classify", action="store_true",
        help="Use zero-cost heuristic classifier instead of Opus",
    )
    parser.add_argument(
        "--skip-verify", action="store_true",
        help="Skip Sonnet verification step",
    )
    parser.add_argument(
        "--max-tokens", type=int, default=2048,
        help="Max tokens for Ollama generation per element (default: 2048)",
    )
    parser.add_argument(
        "--output", default=None,
        help="Path to write JSON results (default: no file output)",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Enable debug logging",
    )
    return parser.parse_args()


def setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    fmt = "%(asctime)s %(levelname)-8s [%(name)s] %(message)s"
    logging.basicConfig(level=level, format=fmt, datefmt="%H:%M:%S")
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)


def main() -> None:
    args = parse_args()
    setup_logging(args.verbose)

    result = asyncio.run(run_experiment(args))
    print_report(result, args)


if __name__ == "__main__":
    main()
