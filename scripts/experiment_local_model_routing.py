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
    indent_recovered: bool = False  # True if indentation fix saved this element
    was_truncated: bool = False  # True if finish_reason="length" (hit token cap)
    had_few_shot: bool = False  # True if few-shot examples were injected into the prompt

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
    ollama_indent_recovered: int = 0  # Elements saved by indentation fix
    ollama_truncated: int = 0  # Elements that hit the token cap
    ollama_few_shot: int = 0  # Elements that had few-shot examples injected
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
    """Render a single element as a Python stub for the LLM to fill in.

    FIX #3: Always renders at top-level indentation (no class wrapper indent).
    Methods are shown un-indented; the prompt header clarifies class context.
    This prevents the model from adding extra leading whitespace.
    """
    lines: list[str] = []

    # FIX #3: Always top-level indent — no class-wrapper indent in the stub.
    # The prompt header tells the model it's a method of a class.
    indent = ""

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
    body_indent = "    "
    if elem.docstring_hint:
        lines.append(f'{body_indent}"""{ elem.docstring_hint}"""')

    # Stub body
    lines.append(f"{body_indent}raise NotImplementedError")

    return "\n".join(lines)


def _estimate_body_lines(elem: ForwardElementSpec) -> str:
    """Estimate expected body length for the length constraint hint."""
    if elem.kind in (ElementKind.CONSTANT, ElementKind.VARIABLE):
        return "1-2"
    if elem.kind == ElementKind.PROPERTY:
        return "1-3"
    param_count = 0
    if elem.signature:
        param_count = len([
            p for p in elem.signature.params if p.name not in ("self", "cls")
        ])
    if param_count == 0:
        return "3-8"
    if param_count <= 2:
        return "5-12"
    return "8-15"


def _find_few_shot_examples(
    elem: ForwardElementSpec,
    file_path: str,
    completed: list[ClassifiedElement],
    max_examples: int = 2,
) -> list[str]:
    """Find 1-2 successfully-generated siblings to use as few-shot examples.

    Priority order:
    1. Same class (matching parent_class) — highest signal for methods
    2. Same file (matching file_path) — anchors output format
    3. Same element kind across files — useful for constants
    """
    examples: list[str] = []

    # Tier 1: Same class
    if elem.parent_class:
        for ce in completed:
            if len(examples) >= max_examples:
                break
            if (
                ce.syntax_valid
                and ce.generated_code
                and ce.element.parent_class == elem.parent_class
                and ce.element.name != elem.name
            ):
                examples.append(ce.generated_code.strip())

    # Tier 2: Same file, different class or standalone
    if len(examples) < max_examples:
        for ce in completed:
            if len(examples) >= max_examples:
                break
            if (
                ce.syntax_valid
                and ce.generated_code
                and ce.file_path == file_path
                and ce.element.name != elem.name
                # Skip if already picked in Tier 1
                and ce.generated_code.strip() not in examples
            ):
                examples.append(ce.generated_code.strip())

    return examples


def _build_constant_prompt(
    elem: ForwardElementSpec,
    file_spec: ForwardFileSpec,
    few_shot_examples: list[str] | None = None,
) -> str:
    """FIX #4: Separate prompt template for constants/variables.

    Constants need an assignment statement, not a function body.
    """
    # Render imports for context
    import_lines = []
    for imp in file_spec.imports:
        if imp.kind == "from":
            names = ", ".join(imp.names)
            import_lines.append(f"from {imp.module} import {names}")
        else:
            alias = f" as {imp.alias}" if imp.alias else ""
            import_lines.append(f"import {imp.module}{alias}")

    # Build type annotation hint
    type_hint = ""
    if elem.signature and elem.signature.return_annotation:
        type_hint = f": {elem.signature.return_annotation}"

    doc_hint = ""
    if elem.docstring_hint:
        doc_hint = f"  # {elem.docstring_hint}"

    sections = [
        "# Task: Define this module-level variable.",
        "# Output ONLY the assignment statement. 1-3 lines maximum.",
        "# Do NOT write functions, classes, decorators, or explanations.",
        "# Do NOT wrap output in markdown code fences.",
        f"# Start your output directly with `{elem.name}`.",
        "",
    ]

    if import_lines:
        sections.append("# Available imports (use only these):")
        sections.extend(import_lines)
        sections.append("")

    # Few-shot: show a successfully-generated constant from the same file
    if few_shot_examples:
        sections.append("# Example (completed):")
        sections.append(few_shot_examples[0])
        sections.append("")

    sections.append("# Define this:")
    sections.append(f"{elem.name}{type_hint} = ...{doc_hint}")

    return "\n".join(sections)


def _build_ollama_prompt(
    elem: ForwardElementSpec,
    file_spec: ForwardFileSpec,
    contracts: list[InterfaceContract],
    few_shot_examples: list[str] | None = None,
) -> str:
    """Build a focused prompt for Ollama to fill in a single element body.

    Prompt improvements applied:
    - FIX #1: Length + stop constraints to prevent over-generation
    - FIX #2: API surface restriction to reduce hallucination
    - FIX #3: Top-level indentation (via _build_element_stub)
    - FIX #4: Separate template for constants (via _build_constant_prompt)
    - FIX #5: No-explanation format anchor
    - FIX #6: Few-shot example injection from successfully-generated siblings
    """
    # FIX #4: Route constants/variables to a dedicated prompt
    if elem.kind in (ElementKind.CONSTANT, ElementKind.VARIABLE):
        return _build_constant_prompt(elem, file_spec, few_shot_examples)

    stub = _build_element_stub(elem)
    est_lines = _estimate_body_lines(elem)

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
                    sibling_stubs.append(f"def {sib.name}({params}){ret}: ...")

    # Render binding constraints
    constraint_lines = []
    for c in contracts:
        prefix = "[BINDING]" if c.confidence != ContractConfidence.TENTATIVE else "[ADVISORY]"
        constraint_lines.append(f"{prefix} {c.binding_text}")

    # ── Build prompt ──

    # FIX #3: Method context header (since stub is now un-indented)
    context_header = ""
    if elem.parent_class:
        context_header = f"# This is a method of class `{elem.parent_class}`. Write it at the top level (no class wrapper).\n"

    # FIX #5: Format anchor — use correct def keyword
    def_keyword = "async def" if elem.kind in (
        ElementKind.ASYNC_FUNCTION, ElementKind.ASYNC_METHOD,
    ) else "def"

    sections = [
        "# Task: Implement the function body below.",
        "# Replace `raise NotImplementedError` with a working implementation.",
        # FIX #1: Length + stop constraints
        f"# The body should be approximately {est_lines} lines.",
        "# STOP after the function ends. Do NOT write additional functions, classes, or tests.",
        # FIX #5: Format anchor
        "# Output ONLY Python code. No markdown fences, no explanations, no comments before or after.",
        f"# Start directly with `{def_keyword} {elem.name}(` on the first line.",
        "",
    ]

    if context_header:
        sections.insert(0, context_header)

    if import_lines:
        # FIX #2: API surface restriction
        sections.append("# Available imports (ONLY use these — do NOT invent other APIs):")
        sections.extend(import_lines)
        sections.append("")

    if sibling_stubs:
        sections.append("# Other methods in this class (for context, do not redefine):")
        sections.extend(sibling_stubs)
        sections.append("")

    if constraint_lines:
        sections.append("# Constraints:")
        sections.extend(constraint_lines)
        sections.append("")

    # FIX #6: Few-shot example injection — anchor output format with a proven sibling
    if few_shot_examples:
        for i, ex in enumerate(few_shot_examples[:2]):
            label = "Example (completed)" if i == 0 else "Another example"
            sections.append(f"# {label}:")
            sections.append(ex)
            sections.append("")

    sections.append("# Now implement this:")
    sections.append(stub)

    return "\n".join(sections)


def _try_parse(code: str, is_method: bool = False) -> bool:
    """Try to ast.parse() the code, return True if it succeeds.

    With FIX #3 (top-level indentation), ALL elements — including methods —
    are rendered at the top level in the prompt.  The model returns top-level
    code, so we always parse directly.  If that fails for a method, we also
    try wrapping in a class as a fallback (the model may still indent).
    """
    try:
        ast.parse(code)
        return True
    except SyntaxError:
        pass
    # Fallback for methods: the model might still return indented code
    if is_method:
        try:
            wrapped = f"class _Wrapper:\n" + textwrap.indent(code, "    ")
            ast.parse(wrapped)
            return True
        except SyntaxError:
            pass
    return False


def _normalize_indentation(
    code: str,
    is_method: bool,
) -> tuple[Optional[str], str]:
    """Try multiple strategies to fix indentation issues in LLM-generated code.

    Returns (fixed_code, strategy_name) if any strategy works, or (None, "") if
    all strategies fail.

    Strategies tried in order:
    1. textwrap.dedent — strips common leading whitespace, re-indents for methods
    2. Strip first line (often explanation text) + dedent
    3. Strip last line (often trailing comment/explanation) + dedent
    4. Strip both first and last lines + dedent
    5. Tab-to-spaces conversion + dedent
    """
    strategies: list[tuple[str, str]] = []

    # Strategy 1: Straight dedent (+ re-indent for methods)
    dedented = textwrap.dedent(code).strip()
    strategies.append(("dedent", dedented))

    # Strategy 2: Strip first line + dedent
    # codellama often emits an explanation line before the actual code
    lines = code.split("\n")
    if len(lines) > 2:
        without_first = "\n".join(lines[1:])
        strategies.append(("strip_first_line+dedent", textwrap.dedent(without_first).strip()))

    # Strategy 3: Strip last line + dedent
    # Sometimes trailing explanation or truncated line
    if len(lines) > 2:
        without_last = "\n".join(lines[:-1])
        strategies.append(("strip_last_line+dedent", textwrap.dedent(without_last).strip()))

    # Strategy 4: Strip both first and last + dedent
    if len(lines) > 3:
        middle = "\n".join(lines[1:-1])
        strategies.append(("strip_first_last+dedent", textwrap.dedent(middle).strip()))

    # Strategy 5: Tabs → 4 spaces + dedent
    if "\t" in code:
        tab_fixed = code.expandtabs(4)
        strategies.append(("tabs_to_spaces+dedent", textwrap.dedent(tab_fixed).strip()))

    for name, candidate in strategies:
        if not candidate:
            continue
        if _try_parse(candidate, is_method):
            return candidate, name

    return None, ""


def _extract_syntax_error(code: str) -> str:
    """Try ast.parse to get the SyntaxError message for reporting."""
    try:
        ast.parse(code)
        return ""
    except SyntaxError as e:
        return f"SyntaxError: {e}"


async def generate_with_ollama(
    elem: ClassifiedElement,
    file_spec: ForwardFileSpec,
    contracts: list[InterfaceContract],
    ollama_model: str,
    max_tokens: int = 512,
    normalize_indent: bool = False,
    completed: list[ClassifiedElement] | None = None,
) -> None:
    """Generate a single element body using Ollama. Mutates elem in place."""
    try:
        agent = resolve_agent_spec(
            f"ollama:{ollama_model}",
            max_tokens=max_tokens,
        )
        # FIX #6: Find few-shot examples from already-generated siblings
        few_shot = _find_few_shot_examples(
            elem.element, elem.file_path, completed or [],
        )
        if few_shot:
            elem.had_few_shot = True
        prompt = _build_ollama_prompt(
            elem.element, file_spec, contracts, few_shot or None,
        )

        start = time.monotonic()
        result_text, time_ms, token_usage = await agent.agenerate(prompt)
        elem.generation_time_ms = time_ms or (time.monotonic() - start) * 1000

        if token_usage:
            elem.generation_tokens = (token_usage.input or 0) + (token_usage.output or 0)
            # Detect truncation: finish_reason="length" means the model hit the token cap
            if getattr(token_usage, 'was_truncated', False):
                elem.was_truncated = True
                logger.warning(
                    f"    {elem.fqn}: TRUNCATED (hit token cap, "
                    f"output={token_usage.output} tokens)"
                )

        # Extract just the function/method code
        from startd8.utils.code_extraction import extract_code_from_response
        code = extract_code_from_response(result_text)

        if not code or not code.strip():
            elem.error = "Empty response from Ollama"
            elem.syntax_valid = False
            return

        elem.generated_code = code
        is_method = bool(elem.element.parent_class)

        # Validate syntax
        if _try_parse(code, is_method):
            elem.syntax_valid = True
        elif normalize_indent:
            # Try indentation normalization strategies before giving up
            fixed, strategy = _normalize_indentation(code, is_method)
            if fixed is not None:
                elem.generated_code = fixed
                elem.syntax_valid = True
                elem.indent_recovered = True
                logger.info(
                    f"    Indentation fix recovered {elem.fqn} via '{strategy}'"
                )
            else:
                elem.syntax_valid = False
                elem.error = _extract_syntax_error(code)
        else:
            elem.syntax_valid = False
            elem.error = _extract_syntax_error(code)

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


async def _run_sdk_engine_experiment(
    manifest: ForwardManifest,
    args: argparse.Namespace,
) -> ExperimentResult:
    """Run experiment using the SDK MicroPrimeEngine (--use-sdk-engine).

    Maps SDK engine results back to the script's ExperimentResult format
    for unified reporting and A/B comparison with the inline pipeline.
    """
    from startd8.micro_prime.engine import MicroPrimeEngine
    from startd8.micro_prime.metrics import generate_cost_report
    from startd8.micro_prime.models import (
        MicroPrimeConfig,
        TierClassification as SdkTier,
    )

    result = ExperimentResult()
    result.total_elements = sum(
        len([e for e in fs.elements if e.kind != ElementKind.CLASS])
        for fs in manifest.file_specs.values()
    )

    # Configure engine from CLI args
    config = MicroPrimeConfig(
        model=args.ollama_model,
        max_tokens=args.max_tokens,
        templates_enabled=True,
        repair_enabled=True,
    )
    if hasattr(args, "normalize_indent") and args.normalize_indent:
        config = config.model_copy()

    engine = MicroPrimeEngine(config=config)

    # We don't have real skeletons in the experiment — build stubs with
    # raise NotImplementedError for each element so splicing can work.
    skeletons: dict[str, str] = {}
    for file_path, file_spec in manifest.file_specs.items():
        stub_lines: list[str] = []
        for elem in file_spec.elements:
            stub = _build_element_stub(elem)
            stub_lines.append(stub)
            stub_lines.append("")
        skeletons[file_path] = "\n".join(stub_lines)

    # Run the SDK engine
    seed_result = engine.process_seed(manifest, skeletons)

    # Map SDK results to ExperimentResult
    tier_map = {
        SdkTier.TRIVIAL: "simple",  # TRIVIAL maps to simple for reporting
        SdkTier.SIMPLE: "simple",
        SdkTier.MODERATE: "moderate",
        SdkTier.COMPLEX: "complex",
    }

    for file_result in seed_result.file_results:
        for er in file_result.element_results:
            tier_str = tier_map.get(er.tier, "complex")
            result.classified[tier_str] = result.classified.get(tier_str, 0) + 1

            # Map to ClassifiedElement for reporting
            # Find the original element spec
            file_spec = manifest.file_specs.get(er.file_path)
            elem = None
            if file_spec:
                for e in file_spec.elements:
                    if e.name == er.element_name:
                        elem = e
                        break

            if elem is None:
                continue

            complexity = Complexity.SIMPLE if tier_str == "simple" else (
                Complexity.MODERATE if tier_str == "moderate" else Complexity.COMPLEX
            )
            ce = ClassifiedElement(
                file_path=er.file_path,
                element=elem,
                complexity=complexity,
                reasoning=f"SDK engine tier: {er.tier.value}",
                generated_code=er.code,
                generation_time_ms=er.generation_time_ms,
                generation_tokens=er.output_tokens,
                syntax_valid=er.success,
            )
            result.elements.append(ce)

            if er.tier in (SdkTier.TRIVIAL, SdkTier.SIMPLE):
                result.ollama_attempted += 1
                if er.success:
                    result.ollama_syntax_valid += 1
                    result.ollama_succeeded += 1
                    if er.template_used:
                        ce.reasoning += " (template)"
                else:
                    result.ollama_failed += 1
                    ce.error = er.escalation.detail if er.escalation else "Unknown"
                if er.generation_time_ms:
                    result.total_generation_time_ms += er.generation_time_ms
                if er.output_tokens:
                    result.total_generation_tokens += er.output_tokens

    logger.info(
        "SDK Engine: %d/%d syntax-valid (%.0f%%)",
        result.ollama_syntax_valid,
        result.ollama_attempted,
        result.success_rate * 100,
    )

    return result


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

    # ── Phase 0: Load cached manifest or synthesize if needed ──
    if args.manifest_cache and len(manifest.file_specs) == 0:
        cache_path = Path(args.manifest_cache)
        if cache_path.exists():
            logger.info(f"Loading cached manifest from {cache_path}")
            manifest = ForwardManifest.model_validate_json(cache_path.read_text(encoding="utf-8"))
            logger.info(
                f"Cached manifest: {len(manifest.file_specs)} files, "
                f"{len(manifest.contracts)} contracts"
            )
        else:
            logger.warning(f"Manifest cache not found: {cache_path}")

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

    # ── SDK Engine path ──
    if getattr(args, "use_sdk_engine", False):
        logger.info("Using SDK MicroPrimeEngine (--use-sdk-engine)")
        return await _run_sdk_engine_experiment(manifest, args)

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

    completed: list[ClassifiedElement] = []  # FIX #6: accumulate for few-shot examples

    for ce in simple_elements:
        file_spec = file_spec_map.get(ce.file_path)
        if not file_spec:
            ce.error = f"No file_spec for {ce.file_path}"
            completed.append(ce)
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
            normalize_indent=args.normalize_indent,
            completed=completed,
        )

        completed.append(ce)

        status = "OK" if ce.syntax_valid else f"FAIL ({ce.error})"
        if ce.indent_recovered:
            status = "OK (indent-fixed)"
        if ce.had_few_shot:
            status += " [few-shot]"
        logger.info(
            f"  {ce.fqn}: {status} "
            f"({ce.generation_time_ms:.0f}ms, {ce.generation_tokens or 0} tokens)"
        )

    # Tally generation results
    for ce in simple_elements:
        if ce.syntax_valid:
            result.ollama_syntax_valid += 1
            result.ollama_succeeded += 1
            if ce.indent_recovered:
                result.ollama_indent_recovered += 1
        elif ce.error:
            result.ollama_failed += 1
        if ce.was_truncated:
            result.ollama_truncated += 1
        if ce.had_few_shot:
            result.ollama_few_shot += 1
        if ce.generation_time_ms:
            result.total_generation_time_ms += ce.generation_time_ms
        if ce.generation_tokens:
            result.total_generation_tokens += ce.generation_tokens

    indent_msg = ""
    if result.ollama_indent_recovered > 0:
        indent_msg = f" ({result.ollama_indent_recovered} recovered via indent fix)"
    logger.info(
        f"Generation: {result.ollama_syntax_valid}/{result.ollama_attempted} syntax-valid "
        f"({result.success_rate:.0%}){indent_msg}"
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
    if getattr(args, "use_sdk_engine", False):
        print(f"  Engine: SDK MicroPrimeEngine")
    else:
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
        if result.ollama_indent_recovered > 0:
            native = result.ollama_syntax_valid - result.ollama_indent_recovered
            print(f"    ├─ Native:     {native}")
            print(f"    └─ Recovered:  {result.ollama_indent_recovered} (indent normalization)")
        print(f"  Failed:          {result.ollama_failed}")
        if result.ollama_truncated > 0:
            print(f"  Truncated:       {result.ollama_truncated} (hit token cap → escalation candidate)")
        if result.ollama_few_shot > 0:
            print(f"  Few-shot aided:  {result.ollama_few_shot} (had sibling examples injected)")
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
            if ce.indent_recovered:
                syn = "FIXED"
            elif ce.syntax_valid:
                syn = "OK"
            else:
                syn = "FAIL"
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
            "engine": "sdk" if getattr(args, "use_sdk_engine", False) else "inline",
            "classifier": "heuristic" if args.heuristic_classify else "opus",
            "total_elements": result.total_elements,
            "classified": result.classified,
            "ollama_attempted": result.ollama_attempted,
            "ollama_syntax_valid": result.ollama_syntax_valid,
            "ollama_indent_recovered": result.ollama_indent_recovered,
            "ollama_verified": result.ollama_verified,
            "ollama_truncated": result.ollama_truncated,
            "ollama_few_shot": result.ollama_few_shot,
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
                    "indent_recovered": ce.indent_recovered,
                    "was_truncated": ce.was_truncated,
                    "had_few_shot": ce.had_few_shot,
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
        "--ollama-model", default="startd8-coder",
        help="Ollama model to use for SIMPLE element generation (default: startd8-coder)",
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
        "--normalize-indent", action="store_true",
        help="Try indentation normalization strategies to recover syntax-invalid code",
    )
    parser.add_argument(
        "--manifest-cache", default=None,
        help="Path to a pre-synthesized manifest JSON file (avoids re-running Opus synthesis)",
    )
    parser.add_argument(
        "--max-tokens", type=int, default=512,
        help="Max tokens for Ollama generation per element (default: 512). "
             "Lower cap reduces over-generation from local models.",
    )
    parser.add_argument(
        "--output", default=None,
        help="Path to write JSON results (default: no file output)",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Enable debug logging",
    )
    parser.add_argument(
        "--use-sdk-engine", action="store_true",
        help="Use MicroPrimeEngine from the SDK instead of inline logic. "
             "Enables A/B comparison during transition.",
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
