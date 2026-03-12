"""Micro-Ingest: local-first per-task code example enrichment.

Three-tier pipeline mirroring Micro Prime's routing pattern:
  Tier 0: DFA stub rendering (deterministic, zero LLM)
  Tier 1: Template rendering (deterministic, zero LLM)
  Tier 2: Ollama generation (local LLM, opt-in)

Pipeline position::

    _phase_emit():
      1. ForwardManifest construction
      2. DFA skeleton validation
      3. _derive_tasks_from_features()
      4. enrich_tasks_deterministic()     ← Option A
      5. [MICRO-INGEST]                   ← This module
      6. _build_seed_artifacts()
      7. compute_seed_quality()

See: docs/design/plan-ingestion/MICRO_INGEST_REQUIREMENTS.md
"""

from __future__ import annotations

import ast
import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ...logging_config import get_logger

logger = get_logger(__name__)


# ── Data Models ──────────────────────────────────────────────────────


@dataclass
class EnrichmentRoute:
    """Per-task enrichment routing decision (REQ-MI-100)."""

    task_id: str
    needs_code_example: bool
    tier: int  # 0=DFA, 1=template, 2=ollama, -1=skip
    tier_reason: str
    elements: List[str] = field(default_factory=list)
    estimated_tokens: int = 0
    has_forward_spec: bool = False
    has_api_signatures: bool = False
    template_matches: List[str] = field(default_factory=list)


@dataclass
class EnrichmentRouteReport:
    """Aggregate routing report across all tasks (REQ-MI-102)."""

    total_tasks: int = 0
    already_enriched: int = 0
    tier_0_count: int = 0
    tier_1_count: int = 0
    tier_2_count: int = 0
    skip_count: int = 0
    routes: List[EnrichmentRoute] = field(default_factory=list)
    estimated_ollama_time_s: float = 0.0
    time_ms: int = 0


# Average Ollama inference time per element (from Kaizen run data)
_AVG_OLLAMA_INFERENCE_S = 6.0

# Tokens per line estimate for output budget
_TOKENS_PER_LINE = 8


# ── Signature Parsing (REQ-MI-101) ───────────────────────────────────

# Pattern: "Class ClassName" or "Class ClassName(Base1, Base2)"
_CLASS_PATTERN = re.compile(
    r"^[Cc]lass\s+(\w+)(?:\(([^)]*)\))?\s*(?::\s*pass\s*)?$"
)

# Pattern: dotted method "def ClassName.method_name(...)"
_DOTTED_METHOD_PATTERN = re.compile(
    r"^(async\s+)?def\s+(\w+)\.(\w+)\s*\("
)


def _normalize_signature(sig: str) -> str:
    """Normalize a raw api_signature string for ast.parse().

    Handles:
    - Strip surrounding backticks/quotes
    - Rewrite ``Class Foo(Base)`` → ``class Foo(Base): pass``
    - Rewrite ``def Foo.bar(self, x)`` → ``def bar(self, x): pass``
      (parent_class extracted separately)
    - Ensure bare ``def ...`` ends with ``: pass``
    """
    sig = sig.strip()

    # Strip surrounding backticks or quotes
    if sig.startswith("`") and sig.endswith("`"):
        sig = sig.strip("`").strip()
    if sig.startswith('"') and sig.endswith('"'):
        sig = sig.strip('"').strip()
    if sig.startswith("'") and sig.endswith("'"):
        sig = sig.strip("'").strip()

    # Rewrite "Class Foo(Base)" → "class Foo(Base): pass"
    if sig.startswith("Class "):
        sig = "class " + sig[6:]

    # Ensure class definitions end with ": pass"
    if sig.startswith("class ") and not sig.rstrip().endswith(": pass"):
        sig = sig.rstrip().rstrip(":") + ": pass"

    # Ensure def/async def end with ": pass"
    stripped = sig.rstrip()
    if ("def " in stripped) and not stripped.endswith(": pass"):
        if stripped.endswith(":"):
            sig = stripped + " pass"
        else:
            sig = stripped + ": pass"

    return sig


def _parse_api_signature(sig: str) -> Optional[dict]:
    """Parse a single api_signature string into ForwardElementSpec constructor args.

    Returns a dict of kwargs for ForwardElementSpec, or None on parse failure.
    Does NOT construct ForwardElementSpec directly to avoid import-time coupling;
    the caller builds the spec from the returned dict.

    Supported formats (from plan ingestion PARSE prompt):
    - ``"def function_name(param: type) -> return_type"``
    - ``"async def function_name(param: type) -> return_type"``
    - ``"Class ClassName(BaseClass)"``
    - ``"def ClassName.method_name(self, param: type) -> return_type"``
    """
    if not sig or not sig.strip():
        return None

    # --- Variable/constant assignment pattern (before normalization) ---
    cleaned = sig.strip().rstrip(";")
    # Strip surrounding backticks/quotes
    for ch in ("`", '"', "'"):
        if cleaned.startswith(ch) and cleaned.endswith(ch):
            cleaned = cleaned.strip(ch).strip()
    if not cleaned.startswith(("def ", "async def ", "class ", "Class ")):
        var_match = re.match(
            r"^([A-Za-z_]\w*)\s*(?::\s*([^=]+?))?\s*=\s*(.+)$", cleaned,
        )
        if var_match:
            var_name = var_match.group(1)
            type_ann = var_match.group(2).strip() if var_match.group(2) else None
            value_repr = var_match.group(3).strip()
            is_upper = var_name == var_name.upper() and "_" in var_name
            return {
                "kind": "constant" if is_upper else "variable",
                "name": var_name,
                "type_annotation": type_ann,
                "value_repr": value_repr,
                "params": None,
                "return_annotation": None,
                "parent_class": None,
                "is_async": False,
                "bases": None,
                "signature": None,
            }

    normalized = _normalize_signature(sig)

    # --- Class pattern ---
    class_match = _CLASS_PATTERN.match(normalized)
    if class_match:
        name = class_match.group(1)
        bases_str = class_match.group(2)
        bases = [b.strip() for b in bases_str.split(",") if b.strip()] if bases_str else []
        return {
            "kind": "class",
            "name": name,
            "bases": bases,
            "signature": None,
            "parent_class": None,
            "is_async": False,
        }

    # --- Dotted method: "def Foo.bar(...)" → parent_class=Foo ---
    parent_class = None
    dotted_match = _DOTTED_METHOD_PATTERN.match(normalized)
    if dotted_match:
        is_async_prefix = dotted_match.group(1) or ""
        parent_class = dotted_match.group(2)
        method_name = dotted_match.group(3)
        # Rewrite to plain def for ast.parse
        rest = normalized[dotted_match.end() - 1:]  # from the "(" onwards
        normalized = f"{is_async_prefix}def {method_name}{rest}"

    # --- Function / method via ast.parse ---
    try:
        tree = ast.parse(normalized)
    except SyntaxError:
        logger.debug("micro_ingest: failed to parse signature: %r", sig)
        return None

    if not tree.body:
        return None

    node = tree.body[0]
    if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        logger.debug("micro_ingest: unexpected AST node type: %s", type(node).__name__)
        return None

    is_async = isinstance(node, ast.AsyncFunctionDef)
    name = node.name

    # Extract params
    params = []
    for arg in node.args.args:
        annotation = None
        if arg.annotation:
            try:
                annotation = ast.unparse(arg.annotation)
            except (ValueError, AttributeError):
                pass
        params.append({"name": arg.arg, "annotation": annotation})

    # Extract return annotation
    return_annotation = None
    if node.returns:
        try:
            return_annotation = ast.unparse(node.returns)
        except (ValueError, AttributeError):
            pass

    # Determine kind
    if parent_class:
        kind = "async_method" if is_async else "method"
    else:
        kind = "async_function" if is_async else "function"

    return {
        "kind": kind,
        "name": name,
        "params": params,
        "return_annotation": return_annotation,
        "parent_class": parent_class,
        "is_async": is_async,
        "bases": None,
        "signature": None,  # built by caller from params
    }


def _build_forward_element_spec(parsed: dict) -> Optional[Any]:
    """Build a ForwardElementSpec from parsed signature dict.

    Deferred import to avoid circular deps and keep the parser testable
    without requiring the full forward_manifest module.
    """
    try:
        from startd8.forward_manifest import ForwardElementSpec
        from startd8.utils.code_manifest import (
            ElementKind,
            Param,
            ParamKind,
            Signature,
        )
    except ImportError:
        logger.debug("micro_ingest: forward_manifest imports unavailable")
        return None

    kind_str = parsed["kind"]
    kind_map = {
        "class": ElementKind.CLASS,
        "function": ElementKind.FUNCTION,
        "async_function": ElementKind.ASYNC_FUNCTION,
        "method": ElementKind.METHOD,
        "async_method": ElementKind.ASYNC_METHOD,
        "variable": ElementKind.VARIABLE,
        "constant": ElementKind.CONSTANT,
    }
    kind = kind_map.get(kind_str)
    if kind is None:
        return None

    # Variable/constant kinds — no signature, use type_annotation + value_repr
    if kind in (ElementKind.VARIABLE, ElementKind.CONSTANT):
        try:
            return ForwardElementSpec(
                kind=kind,
                name=parsed["name"],
                type_annotation=parsed.get("type_annotation"),
                value_repr=parsed.get("value_repr"),
            )
        except (ValueError, TypeError) as exc:
            logger.debug("micro_ingest: ForwardElementSpec validation failed: %s", exc)
            return None

    # Build Signature for callables
    signature = None
    if kind != ElementKind.CLASS:
        param_list = []
        for p in parsed.get("params") or []:
            param_list.append(Param(
                name=p["name"],
                annotation=p.get("annotation"),
                kind=ParamKind.POSITIONAL,
            ))
        signature = Signature(
            params=param_list,
            return_annotation=parsed.get("return_annotation"),
        )

    try:
        return ForwardElementSpec(
            kind=kind,
            name=parsed["name"],
            signature=signature,
            bases=parsed.get("bases") or [],
            parent_class=parsed.get("parent_class"),
        )
    except (ValueError, TypeError) as exc:
        logger.debug("micro_ingest: ForwardElementSpec validation failed: %s", exc)
        return None


def _parse_signatures_to_elements(api_sigs: List[str]) -> List[Any]:
    """Parse a list of API signature strings into ForwardElementSpec objects.

    Skips unparseable signatures silently (logged at DEBUG by callee).
    """
    elements = []
    for s in api_sigs:
        parsed = _parse_api_signature(s)
        if parsed:
            spec = _build_forward_element_spec(parsed)
            if spec:
                elements.append(spec)
    return elements


def _build_synthetic_file_spec(
    target_file: str,
    elements: List[Any],
    runtime_dependencies: Optional[List[str]] = None,
    protocol: str = "",
) -> Optional[Any]:
    """Build a synthetic ForwardFileSpec from parsed elements.

    Returns None if no elements are provided.
    """
    if not elements:
        return None

    try:
        from startd8.forward_manifest import (
            ForwardDependencies,
            ForwardFileSpec,
            ForwardImportSpec,
        )
    except ImportError:
        return None

    # Infer imports from protocol and runtime_dependencies
    imports: List[Any] = []
    if protocol == "grpc":
        imports.append(ForwardImportSpec(kind="import", module="grpc"))
        imports.append(ForwardImportSpec(kind="from", module="concurrent", names=["futures"]))
    if runtime_dependencies:
        for dep in runtime_dependencies:
            if dep not in ("grpc", "grpcio"):  # already handled
                imports.append(ForwardImportSpec(kind="import", module=dep))

    deps = None
    if runtime_dependencies:
        deps = ForwardDependencies(external=list(runtime_dependencies))

    try:
        return ForwardFileSpec(
            file=target_file,
            elements=elements,
            imports=imports,
            dependencies=deps,
        )
    except (ValueError, TypeError) as exc:
        logger.debug("micro_ingest: synthetic ForwardFileSpec failed: %s", exc)
        return None


# ── Classifier (REQ-MI-100) ──────────────────────────────────────────


def _select_target_file(
    target_files: List[str],
    forward_manifest: Optional[Any],
) -> str:
    """Return the first target_file that has a ForwardFileSpec, or empty string."""
    if not target_files or not forward_manifest:
        return ""
    file_specs = getattr(forward_manifest, "file_specs", None) or {}
    for tf in target_files:
        if tf in file_specs:
            return tf
    return ""


def _estimate_tokens(elements: List[Any], tier: int) -> int:
    """Rough token estimate for the code example output."""
    if tier == 0:
        # DFA skeleton: ~5 lines per element + imports/headers
        lines = len(elements) * 5 + 10
    elif tier == 1:
        # Template: ~3 lines per element
        lines = len(elements) * 3
    elif tier == 2:
        # Ollama: ~8 lines per element
        lines = len(elements) * 8
    else:
        return 0
    return lines * _TOKENS_PER_LINE


def classify_enrichment_routes(
    tasks: List[Dict[str, Any]],
    features: list,
    forward_manifest: Optional[Any] = None,
) -> EnrichmentRouteReport:
    """Classify each task into an enrichment tier (REQ-MI-100).

    Args:
        tasks: Post-Option-A task list (dicts with config.context).
        features: List of ParsedFeature objects.
        forward_manifest: ForwardManifest from FLCM extraction (may be None).

    Returns:
        EnrichmentRouteReport with per-task routes and aggregate counts.
    """
    t0 = time.monotonic()
    feature_index = {f.feature_id: f for f in features}
    report = EnrichmentRouteReport(total_tasks=len(tasks))

    for task in tasks:
        task_id = task.get("task_id", "")
        cfg = task.get("config", {})
        desc = cfg.get("task_description", "") or ""
        ctx = cfg.get("context", {})
        target_files = ctx.get("target_files", [])
        feature_id = ctx.get("feature_id", "")
        feat = feature_index.get(feature_id)

        # Rule 1: Already has code example → skip
        if "```" in desc:
            route = EnrichmentRoute(
                task_id=task_id,
                needs_code_example=False,
                tier=-1,
                tier_reason="already has code block",
            )
            report.already_enriched += 1
            report.routes.append(route)
            continue

        # Rule 2: Has ForwardFileSpec with elements → Tier 0
        matched_file = _select_target_file(target_files, forward_manifest)
        fwd_spec = None
        if matched_file and forward_manifest:
            fwd_spec = forward_manifest.file_specs.get(matched_file)
        if fwd_spec and getattr(fwd_spec, "elements", None):
            element_names = [e.name for e in fwd_spec.elements]
            route = EnrichmentRoute(
                task_id=task_id,
                needs_code_example=True,
                tier=0,
                tier_reason="ForwardFileSpec available",
                elements=element_names,
                estimated_tokens=_estimate_tokens(fwd_spec.elements, 0),
                has_forward_spec=True,
                has_api_signatures=bool(feat and feat.api_signatures),
            )
            report.tier_0_count += 1
            report.routes.append(route)
            continue

        # Rule 3-6: Has parseable api_signatures?
        api_sigs = []
        if feat and feat.api_signatures:
            api_sigs = feat.api_signatures
        elif ctx.get("api_signatures"):
            api_sigs = ctx["api_signatures"]

        if api_sigs:
            parsed_elements = _parse_signatures_to_elements(api_sigs)

            if parsed_elements:
                element_names = [e.name for e in parsed_elements]

                # Rule 3: All parse cleanly → synthetic Tier 0
                if len(parsed_elements) == len(api_sigs):
                    target = target_files[0] if target_files else "unknown.py"
                    synthetic = _build_synthetic_file_spec(
                        target,
                        parsed_elements,
                        runtime_dependencies=getattr(feat, "runtime_dependencies", None),
                        protocol=getattr(feat, "protocol", ""),
                    )
                    if synthetic:
                        route = EnrichmentRoute(
                            task_id=task_id,
                            needs_code_example=True,
                            tier=0,
                            tier_reason="synthetic ForwardFileSpec (all sigs parsed)",
                            elements=element_names,
                            estimated_tokens=_estimate_tokens(parsed_elements, 0),
                            has_forward_spec=False,
                            has_api_signatures=True,
                        )
                        report.tier_0_count += 1
                        report.routes.append(route)
                        continue

                # Rule 4: Check template matches → Tier 1
                template_names = _check_template_matches(parsed_elements)
                if template_names:
                    route = EnrichmentRoute(
                        task_id=task_id,
                        needs_code_example=True,
                        tier=1,
                        tier_reason="template matches available",
                        elements=element_names,
                        estimated_tokens=_estimate_tokens(parsed_elements, 1),
                        has_api_signatures=True,
                        template_matches=template_names,
                    )
                    report.tier_1_count += 1
                    report.routes.append(route)
                    continue

                # Rule 5: SIMPLE-viable → Tier 2
                simple_elements = _filter_simple_viable(parsed_elements)
                if simple_elements:
                    simple_names = [e.name for e in simple_elements]
                    route = EnrichmentRoute(
                        task_id=task_id,
                        needs_code_example=True,
                        tier=2,
                        tier_reason="SIMPLE-viable elements",
                        elements=simple_names,
                        estimated_tokens=_estimate_tokens(simple_elements, 2),
                        has_api_signatures=True,
                    )
                    report.tier_2_count += 1
                    report.routes.append(route)
                    continue

                # Rule 6: Partial parse, no viable elements → skip
                route = EnrichmentRoute(
                    task_id=task_id,
                    needs_code_example=True,
                    tier=-1,
                    tier_reason="no viable elements after parsing",
                    elements=element_names,
                    has_api_signatures=True,
                )
                report.skip_count += 1
                report.routes.append(route)
                continue

        # Rule 7: No structural data → skip
        route = EnrichmentRoute(
            task_id=task_id,
            needs_code_example=True,
            tier=-1,
            tier_reason="no structural data",
        )
        report.skip_count += 1
        report.routes.append(route)

    report.estimated_ollama_time_s = report.tier_2_count * _AVG_OLLAMA_INFERENCE_S
    report.time_ms = int((time.monotonic() - t0) * 1000)

    logger.info(
        "micro_ingest.classify: total=%d already=%d tier_0=%d tier_1=%d "
        "tier_2=%d skip=%d (%dms)",
        report.total_tasks,
        report.already_enriched,
        report.tier_0_count,
        report.tier_1_count,
        report.tier_2_count,
        report.skip_count,
        report.time_ms,
    )

    return report


# ── Template / SIMPLE Viability Helpers ──────────────────────────────


def _check_template_matches(elements: List[Any]) -> List[str]:
    """Check if any elements match Micro Prime templates.

    Returns a list of template names that matched.
    """
    try:
        from startd8.micro_prime.templates import try_template_match_with_name
    except ImportError:
        return []

    matched: List[str] = []
    for elem in elements:
        try:
            result = try_template_match_with_name(elem, None, [])
            if result is not None:
                matched.append(result.name)
        except (TypeError, AttributeError, ValueError):
            # Template registry may not accept all element types
            continue
    return matched


def _filter_simple_viable(elements: List[Any]) -> List[Any]:
    """Filter elements that are SIMPLE-tier viable for Ollama generation.

    SIMPLE viability: ≤4 params, ≤8 imports, create-mode (no parent file).
    """
    viable = []
    for elem in elements:
        sig = getattr(elem, "signature", None)
        if sig is None:
            # Classes without signatures are not SIMPLE-viable for generation
            if getattr(elem, "kind", None) and "class" in str(getattr(elem, "kind", "")).lower():
                continue
            viable.append(elem)
            continue

        param_count = len(sig.params) if sig.params else 0
        if param_count <= 4:
            viable.append(elem)

    return viable


# ═══════════════════════════════════════════════════════════════════════
# Phase 2: Deterministic Stub Assembly (REQ-MI-2xx)
# ═══════════════════════════════════════════════════════════════════════

# DFA skeleton sentinel header (stripped from enrichment output)
_SKELETON_SENTINEL_PREFIX = "# [STARTD8-SKELETON]"


def _render_code_example_tier_0(
    file_spec: Any,
    max_lines: int = 80,
) -> Optional[str]:
    """Render a ForwardFileSpec as a fenced code block for task enrichment.

    Uses DeterministicFileAssembler.render_file() and wraps the output
    in markdown.  Returns None if rendering or AST validation fails.
    """
    try:
        from startd8.utils.file_assembler import DeterministicFileAssembler
    except ImportError:
        return None

    assembler = DeterministicFileAssembler()
    try:
        source = assembler.render_file(file_spec)
    except Exception:
        logger.debug("micro_ingest.tier_0: DFA render_file() failed", exc_info=True)
        return None

    # Validate produced source
    try:
        ast.parse(source)
    except SyntaxError:
        logger.debug("micro_ingest.tier_0: DFA output failed AST validation")
        return None

    # Strip sentinel header
    lines = source.splitlines()
    if lines and lines[0].startswith(_SKELETON_SENTINEL_PREFIX):
        lines = lines[1:]

    # Truncate if needed
    truncated = False
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        truncated = True

    body = "\n".join(lines).strip()
    if truncated:
        line_count = len(source.splitlines())
        body += f"\n# ... (truncated after {max_lines} lines of {line_count}; see forward manifest for full spec)"

    return f"## Code Example (from forward manifest)\n```python\n{body}\n```"


def _render_signature_line(elem: Any) -> str:
    """Render a ForwardElementSpec into its def/class signature line."""
    kind_str = str(getattr(elem, "kind", "")).lower()
    name = getattr(elem, "name", "unknown")

    if "class" in kind_str:
        bases = getattr(elem, "bases", [])
        bases_str = f"({', '.join(bases)})" if bases else ""
        return f"class {name}{bases_str}:"

    sig = getattr(elem, "signature", None)
    params_str = ""
    if sig and sig.params:
        parts = []
        for p in sig.params:
            if p.annotation:
                parts.append(f"{p.name}: {p.annotation}")
            else:
                parts.append(p.name)
        params_str = ", ".join(parts)

    ret = ""
    if sig and sig.return_annotation:
        ret = f" -> {sig.return_annotation}"

    prefix = "async def" if "async" in kind_str else "def"
    return f"{prefix} {name}({params_str}){ret}:"


def _render_code_example_tier_1(
    elements: List[Any],
    template_matches: Dict[str, Any],
) -> Optional[str]:
    """Render template-matched elements as a fenced code block.

    Each template body is wrapped in its full signature for context.
    Returns None if no elements produce output.
    """
    import textwrap

    parts: List[str] = []
    match_names: List[str] = []
    for elem in elements:
        match = template_matches.get(getattr(elem, "name", ""))
        if not match:
            continue
        sig_line = _render_signature_line(elem)
        body = textwrap.indent(match.code, "    ")
        parts.append(f"{sig_line}\n{body}")
        match_names.append(match.name)

    if not parts:
        return None

    body = "\n\n".join(parts)
    names_str = ", ".join(dict.fromkeys(match_names))  # dedupe, preserve order
    return f"## Code Example (from template: {names_str})\n```python\n{body}\n```"


def _get_or_build_file_spec(
    task: Dict[str, Any],
    route: EnrichmentRoute,
    feature_index: Dict[str, Any],
    forward_manifest: Optional[Any],
) -> Optional[Any]:
    """Get ForwardFileSpec from manifest or build synthetic from signatures."""
    ctx = task.get("config", {}).get("context", {})
    target_files = ctx.get("target_files", [])

    # Try real manifest first
    if forward_manifest and route.has_forward_spec:
        matched = _select_target_file(target_files, forward_manifest)
        if matched:
            return forward_manifest.file_specs.get(matched)

    # Build synthetic from api_signatures
    feature_id = ctx.get("feature_id", "")
    feat = feature_index.get(feature_id)
    if not feat:
        return None

    api_sigs = getattr(feat, "api_signatures", []) or []
    if not api_sigs:
        return None

    parsed_elements = _parse_signatures_to_elements(api_sigs)
    if not parsed_elements:
        return None

    target = target_files[0] if target_files else "unknown.py"
    return _build_synthetic_file_spec(
        target,
        parsed_elements,
        runtime_dependencies=getattr(feat, "runtime_dependencies", None),
        protocol=getattr(feat, "protocol", ""),
    )


def _get_template_matches_for_elements(
    elements: List[Any],
) -> Dict[str, Any]:
    """Run template matching on a list of ForwardElementSpec, return name→TemplateMatch."""
    try:
        from startd8.micro_prime.templates import try_template_match_with_name
    except ImportError:
        return {}

    matches: Dict[str, Any] = {}
    for elem in elements:
        try:
            result = try_template_match_with_name(elem, None, [])
            if result is not None:
                matches[elem.name] = result
        except (TypeError, AttributeError, ValueError):
            continue
    return matches


# ═══════════════════════════════════════════════════════════════════════
# Phase 3: Ollama Code Example Generation (REQ-MI-3xx)
# ═══════════════════════════════════════════════════════════════════════


_TIER_2_SKIP_SIGNALS = frozenset({"external_api", "orchestrator", "app_server_instance"})


def _t2_budget_exhausted(t0: float, budget_s: int) -> bool:
    """Check if the Tier 2 time budget has been exceeded."""
    return (time.monotonic() - t0) > budget_s


def _pick_generation_target(elements: List[Any], route: "EnrichmentRoute") -> Optional[Any]:
    """Pick the best element for Ollama generation.

    Prefers functions/methods over classes, and elements whose name
    appears in the route's element list.
    """
    if not elements:
        return None

    route_names = set(route.elements) if route.elements else set()

    # Prefer elements named in the route
    if route_names:
        candidates = [e for e in elements if getattr(e, "name", "") in route_names]
    else:
        candidates = list(elements)
    if not candidates:
        candidates = list(elements)

    # Prefer callable elements (function/method) over classes
    for elem in candidates:
        kind_str = str(getattr(elem, "kind", "")).lower()
        if "function" in kind_str or "method" in kind_str:
            return elem

    return candidates[0]


def _extract_classification_signals(task: Dict[str, Any], feature_index: Dict[str, Any]) -> set:
    """Extract classification signal tags from task context.

    Checks for patterns that indicate the task involves external APIs,
    orchestration, or server setup — elements that Ollama can't meaningfully
    generate stubs for.
    """
    signals: set = set()
    cfg = task.get("config", {})
    ctx = cfg.get("context", {})
    feature_id = ctx.get("feature_id", "")
    feat = feature_index.get(feature_id)

    # Check runtime dependencies
    deps = set()
    if feat:
        deps = set(getattr(feat, "runtime_dependencies", []) or [])

    desc = (cfg.get("task_description", "") or "").lower()

    # External API indicators
    if deps & {"httpx", "requests", "aiohttp", "grpcio-tools"} or "external api" in desc:
        signals.add("external_api")

    # Orchestrator/app-server indicators
    if "orchestrat" in desc or "main loop" in desc:
        signals.add("orchestrator")
    if deps & {"uvicorn", "gunicorn", "hypercorn"} or "app server" in desc:
        signals.add("app_server_instance")

    return signals


def _try_tier_2(
    task: Dict[str, Any],
    route: "EnrichmentRoute",
    feature_index: Dict[str, Any],
    forward_manifest: Optional[Any],
    max_lines: int,
    micro_prime_engine: Optional[Any] = None,
) -> Optional[str]:
    """Generate a code example via Ollama SIMPLE pipeline.

    Returns a fenced code block, or None on failure/skip.
    """
    if micro_prime_engine is None:
        return None

    # Check skip signals
    signals = _extract_classification_signals(task, feature_index)
    if signals & _TIER_2_SKIP_SIGNALS:
        logger.debug("micro_ingest.tier_2: skip signals %s for %s", signals, route.task_id)
        return None

    # Build context: file spec + DFA skeleton
    file_spec = _get_or_build_file_spec(task, route, feature_index, forward_manifest)
    if not file_spec or not getattr(file_spec, "elements", None):
        return None

    # Render DFA skeleton for context (optional — generation proceeds without it)
    skeleton = ""
    try:
        from startd8.utils.file_assembler import DeterministicFileAssembler
        assembler = DeterministicFileAssembler()
        skeleton = assembler.render_file(file_spec)
    except Exception:
        logger.debug("micro_ingest.tier_2: skeleton rendering failed for %s", route.task_id, exc_info=True)

    target_element = _pick_generation_target(file_spec.elements, route)
    if not target_element:
        return None

    try:
        result = micro_prime_engine._handle_simple(
            element=target_element,
            file_spec=file_spec,
            skeleton=skeleton,
            contracts=[],
            file_path=file_spec.file,
            reasoning="micro_ingest_tier_2",
            task_description=task.get("config", {}).get("task_description", ""),
        )
    except (RuntimeError, ValueError, TypeError, OSError) as exc:
        logger.debug(
            "micro_ingest.tier_2: _handle_simple() failed for %s element=%s: %s",
            route.task_id, getattr(target_element, "name", "?"), exc,
            exc_info=True,
        )
        return None

    if not result.success or not result.code:
        return None

    # Format as code block
    code = result.code.strip()
    lines = code.splitlines()
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        code = "\n".join(lines) + "\n# ... (truncated)"
    else:
        code = "\n".join(lines)

    return f"## Code Example (generated by Ollama)\n```python\n{code}\n```"


# ── Enrichment Executor (REQ-MI-200–205, REQ-MI-300–305) ─────────────


def enrich_tasks_micro_ingest(
    tasks: List[Dict[str, Any]],
    routes: List[EnrichmentRoute],
    features: list,
    forward_manifest: Optional[Any] = None,
    *,
    tier_0_enabled: bool = True,
    tier_1_enabled: bool = True,
    tier_2_enabled: bool = False,
    max_lines: int = 80,
    ollama_timeout_s: int = 30,
    ollama_per_element_s: int = 10,
    micro_prime_engine: Optional[Any] = None,
) -> Dict[str, Any]:
    """Run Micro-Ingest enrichment on tasks (in-place).

    Tier 0: DFA skeleton rendering (deterministic, zero LLM).
    Tier 1: Template-matched stubs (deterministic, zero LLM).
    Tier 2: Ollama generation via MicroPrimeEngine (opt-in, local LLM).

    Returns a dict of diagnostic counters for MicroIngestDiagnostic.
    """
    t0 = time.monotonic()
    task_index = {t.get("task_id", ""): t for t in tasks}
    feature_index = {f.feature_id: f for f in features}

    counters = {
        "enabled": True,
        "total_tasks": len(tasks),
        "already_enriched": 0,
        "tier_0_count": 0,
        "tier_1_count": 0,
        "tier_2_count": 0,
        "tier_2_skipped_timeout": 0,
        "tier_2_skipped_circuit_breaker": 0,
        "skip_count": 0,
        "code_examples_added": 0,
    }

    # R1-S6: Check circuit breaker before entering Tier 2 loop
    _t2_circuit_open = False
    if tier_2_enabled and micro_prime_engine is not None:
        if getattr(micro_prime_engine, "_circuit_open", False):
            _t2_circuit_open = True
            logger.warning("micro_ingest.tier_2: circuit breaker open — will skip all Tier 2")
    elif tier_2_enabled and micro_prime_engine is None:
        # No engine → can't run Tier 2
        _t2_circuit_open = True

    for route_idx, route in enumerate(routes):
        if route.tier == -1:
            if not route.needs_code_example:
                counters["already_enriched"] += 1
            else:
                counters["skip_count"] += 1
            continue

        task = task_index.get(route.task_id)
        if not task:
            continue

        code_block = None

        if route.tier == 0 and tier_0_enabled:
            counters["tier_0_count"] += 1
            file_spec = _get_or_build_file_spec(
                task, route, feature_index, forward_manifest,
            )
            if file_spec:
                code_block = _render_code_example_tier_0(file_spec, max_lines)

        elif route.tier == 1 and tier_1_enabled:
            counters["tier_1_count"] += 1
            file_spec = _get_or_build_file_spec(
                task, route, feature_index, forward_manifest,
            )
            if file_spec and getattr(file_spec, "elements", None):
                template_matches = _get_template_matches_for_elements(
                    file_spec.elements,
                )
                if template_matches:
                    code_block = _render_code_example_tier_1(
                        file_spec.elements, template_matches,
                    )

        elif route.tier == 2 and tier_2_enabled:
            counters["tier_2_count"] += 1
            if _t2_circuit_open:
                counters["tier_2_skipped_circuit_breaker"] += 1
            elif _t2_budget_exhausted(t0, ollama_timeout_s):
                tier_2_remaining = sum(1 for r in routes[route_idx:] if r.tier == 2)
                counters["tier_2_skipped_timeout"] += tier_2_remaining
                logger.warning(
                    "micro_ingest.tier_2: time budget exhausted (%.1fs > %ds) — skipping %d",
                    time.monotonic() - t0, ollama_timeout_s, tier_2_remaining,
                )
                # Stop processing further Tier 2 (but continue other tiers)
                _t2_circuit_open = True  # reuse flag to skip remaining
            else:
                code_block = _try_tier_2(
                    task, route, feature_index, forward_manifest,
                    max_lines,
                    micro_prime_engine=micro_prime_engine,
                )

        elif route.tier == 2:
            counters["tier_2_count"] += 1
            # tier_2_enabled=False — counted but not executed

        if code_block:
            # Append to task description (TDE-106 no-clobber: classifier
            # already verified no existing code block)
            cfg = task.get("config", {})
            desc = cfg.get("task_description", "") or ""
            cfg["task_description"] = f"{desc}\n\n{code_block}"
            counters["code_examples_added"] += 1
            logger.debug(
                "micro_ingest: appended code example to %s (tier %d)",
                route.task_id, route.tier,
            )

    counters["time_ms"] = int((time.monotonic() - t0) * 1000)

    logger.info(
        "micro_ingest.enrich: %d code examples added "
        "(tier_0=%d tier_1=%d tier_2=%d skip=%d) in %dms",
        counters["code_examples_added"],
        counters["tier_0_count"],
        counters["tier_1_count"],
        counters["tier_2_count"],
        counters["skip_count"],
        counters["time_ms"],
    )

    return counters
