"""
Forward-Looking Code Manifest (FLCM) — Phase 3 Extractor.

Populates ``ForwardManifest`` from three sources:

1. **Deterministic extraction** — ``ParsedFeature`` fields (api_signatures,
   runtime_dependencies, protocol, shared files).
2. **Human-authored YAML** — explicit ``shared_contracts`` blocks.
3. **Proto files** — service/rpc/message declarations from ``.proto`` files.

A ``ManifestMerger`` deduplicates by ``contract_id`` using source-precedence
rules, and the ``extract_forward_contracts()`` orchestrator ties everything
together.

See docs/design/forward-manifest/Phase_3_Forward_Manifest_Extractor_Requirements.md
"""

from __future__ import annotations

import ast
import logging
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml

from startd8.forward_manifest import (
    ContractCategory,
    ContractConfidence,
    ForwardElementSpec,
    ForwardFileSpec,
    ForwardManifest,
    InterfaceContract,
)
from startd8.logging_config import get_logger
from startd8.utils.code_manifest import ElementKind, Param, ParamKind, Signature
from startd8.workflows.builtin.plan_ingestion_models import ParsedFeature

from .element_id import make_element_id

logger = get_logger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# Constants
# ═══════════════════════════════════════════════════════════════════════════

_CATEGORY_ABBREV: dict[ContractCategory, str] = {
    ContractCategory.FUNCTION_NAME: "fn",
    ContractCategory.CLASS_NAME: "cls",
    ContractCategory.API_ENDPOINT: "ep",
    ContractCategory.CONFIG_KEY: "cfg",
    ContractCategory.IMPORT_PATH: "imp",
    ContractCategory.FORMULA: "fml",
    ContractCategory.RENDER_PATTERN: "pat",
    ContractCategory.INFRASTRUCTURE: "inf",
}

# Higher numeric value = higher precedence (wins on duplicate contract_id).
_SOURCE_PRECEDENCE: dict[str, int] = {
    "source-ast": 0,       # AST-derived from existing files — fills gaps only
    "deterministic": 1,
    "reference-ast": 2,    # Behavioral contracts from reference source files
    "proto": 2,
    "human-yaml": 3,
}

_PROTOCOL_MAP: dict[str, str] = {
    "grpc": "gRPC transport",
    "http": "HTTP transport",
    "amqp": "AMQP message broker",
}

_UTILITY_FILE_PATTERNS: dict[str, tuple[str, ContractCategory]] = {
    "logger.py": ("get_logger", ContractCategory.FUNCTION_NAME),
    "config.py": ("Config", ContractCategory.CLASS_NAME),
}


# ═══════════════════════════════════════════════════════════════════════════
# Private helpers
# ═══════════════════════════════════════════════════════════════════════════


def _unparse(node: Optional[ast.AST]) -> Optional[str]:
    """Safely unparse an AST node to source text.

    Note: mirrors ``code_manifest._unparse`` — kept local because that
    function is private.  Consolidate if it becomes public.
    """
    if node is None:
        return None
    try:
        return ast.unparse(node)
    except Exception:
        return None


def _strip_def_prefix(sig_str: str) -> str:
    """Strip leading keyword prefixes from a signature string.

    Handles ``def ``, ``async def ``, and LLM-generated prefixes like
    ``Method``, ``Function``, ``Property`` that appear in ``api_signatures``
    output.  Matching is case-insensitive to cover ``Async Def``, ``METHOD``,
    etc.
    """
    cleaned = sig_str.strip()
    lower = cleaned.lower()
    # Longest prefixes first to avoid partial matches.
    for prefix in (
        "async def ",
        "async method ",
        "async function ",
        "def ",
        "method ",
        "function ",
        "property ",
    ):
        if lower.startswith(prefix):
            return cleaned[len(prefix):]
    return cleaned


def _detect_async_prefix(sig_str: str) -> bool:
    """Return True if ``sig_str`` has an ``async`` keyword prefix."""
    lower = sig_str.strip().lower()
    return lower.startswith("async ")


def _parse_python_signature(sig_str: str) -> Optional[Signature]:
    """Parse a Python function signature string into a ``Signature`` model.

    Accepts forms like ``def foo(x: int) -> str``, ``async def bar()``,
    or bare ``foo(x: int) -> str``.  Returns ``None`` on any parse failure.
    """
    cleaned = _strip_def_prefix(sig_str)

    # Strip trailing ": pass" body if present so wrapping doesn't produce
    # "def foo(): pass: pass" (invalid syntax).
    if cleaned.rstrip().endswith(": pass"):
        cleaned = cleaned.rstrip()[: -len(": pass")].rstrip()

    # Strip class prefix from dotted method names (e.g.
    # "ClassName.method(self, ...)" → "method(self, ...)") because
    # "def ClassName.method(...): pass" is invalid Python syntax.
    # The parent_class is resolved downstream from the dotted func_name.
    parse_name = cleaned
    paren_idx = cleaned.find("(")
    if paren_idx != -1:
        name_part = cleaned[:paren_idx]
        if "." in name_part:
            last_dot = name_part.rfind(".")
            parse_name = name_part[last_dot + 1:] + cleaned[paren_idx:]

    # Wrap as a valid function so ast.parse can handle it
    source = f"def {parse_name}: pass"
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None

    if not tree.body or not isinstance(tree.body[0], (ast.FunctionDef, ast.AsyncFunctionDef)):
        return None

    node = tree.body[0]
    args = node.args
    params: list[Param] = []

    # positional-only (before /)
    for i, arg in enumerate(args.posonlyargs):
        total_positional = len(args.posonlyargs) + len(args.args)
        default_offset = total_positional - len(args.defaults)
        default = args.defaults[i - default_offset] if i >= default_offset else None
        params.append(
            Param(
                name=arg.arg,
                annotation=_unparse(arg.annotation),
                default=_unparse(default),
                kind=ParamKind.POSITIONAL_ONLY,
            )
        )

    # regular positional/keyword
    for i, arg in enumerate(args.args):
        global_idx = len(args.posonlyargs) + i
        total_positional = len(args.posonlyargs) + len(args.args)
        default_offset = total_positional - len(args.defaults)
        default = (
            args.defaults[global_idx - default_offset]
            if global_idx >= default_offset
            else None
        )
        params.append(
            Param(
                name=arg.arg,
                annotation=_unparse(arg.annotation),
                default=_unparse(default),
                kind=ParamKind.POSITIONAL,
            )
        )

    # *args
    if args.vararg:
        params.append(
            Param(
                name=args.vararg.arg,
                annotation=_unparse(args.vararg.annotation),
                kind=ParamKind.VAR_POSITIONAL,
            )
        )

    # keyword-only (after *)
    for i, arg in enumerate(args.kwonlyargs):
        default = args.kw_defaults[i] if i < len(args.kw_defaults) else None
        params.append(
            Param(
                name=arg.arg,
                annotation=_unparse(arg.annotation),
                default=_unparse(default),
                kind=ParamKind.KEYWORD_ONLY,
            )
        )

    # **kwargs
    if args.kwarg:
        params.append(
            Param(
                name=args.kwarg.arg,
                annotation=_unparse(args.kwarg.annotation),
                kind=ParamKind.VAR_KEYWORD,
            )
        )

    return Signature(params=params, return_annotation=_unparse(node.returns))


def _extract_function_name(sig_str: str) -> Optional[str]:
    """Extract the function name from a signature string."""
    cleaned = _strip_def_prefix(sig_str)
    # Skip class definitions — handled by _parse_class_signature
    if cleaned[:6].lower().startswith("class "):
        return None
    paren_idx = cleaned.find("(")
    if paren_idx < 1:
        return None
    return cleaned[:paren_idx].strip()


# ── REQ-EE-200: Go/Java source element converters ────────────────────────


def _go_elements_to_specs(elements: list, file_path: str) -> list[ForwardElementSpec]:
    """Convert GoElement objects to ForwardElementSpec for MicroPrime.

    Maps Go structural elements (function, method, struct, interface) to
    ForwardElementSpec with ``decomposition_source="source-go-parser"``.
    Constants, variables, and type aliases are skipped (not useful for
    element-level generation).
    """
    specs: list[ForwardElementSpec] = []
    for el in elements:
        go_kind = getattr(el, "kind", "")
        name = getattr(el, "name", "")
        if not name:
            continue

        if go_kind in ("function", "method"):
            kind = ElementKind.METHOD if go_kind == "method" else ElementKind.FUNCTION
            ret = getattr(el, "return_type", None)
            specs.append(ForwardElementSpec(
                kind=kind,
                name=name,
                parent_class=getattr(el, "parent_type", None),
                signature=Signature(params=[], return_annotation=ret),
                decomposition_source="source-go-parser",
            ))
        elif go_kind == "class":
            is_iface = getattr(el, "is_interface", False)
            bases = list(getattr(el, "bases", []))
            specs.append(ForwardElementSpec(
                kind=ElementKind.CLASS,
                name=name,
                bases=bases,
                is_abstract=is_iface,
                decomposition_source="source-go-parser",
            ))
        # Skip constant, variable, type_alias — not useful for element generation

    return specs


def _java_elements_to_specs(elements: list, file_path: str) -> list[ForwardElementSpec]:
    """Convert JavaElement objects to ForwardElementSpec for MicroPrime.

    Maps Java structural elements (class, interface, enum, method, constructor)
    to ForwardElementSpec with ``decomposition_source="source-java-parser"``.
    Fields and constants are skipped.
    """
    specs: list[ForwardElementSpec] = []
    for el in elements:
        kind_str = getattr(el, "kind", "")
        name = getattr(el, "name", "")
        if not name:
            continue

        if kind_str in ("class", "interface", "enum", "record"):
            bases: list[str] = []
            extends_val = getattr(el, "extends", None)
            if extends_val:
                if isinstance(extends_val, str):
                    bases.append(extends_val)
                elif isinstance(extends_val, list):
                    bases.extend(extends_val)
            implements_val = getattr(el, "implements", None)
            if implements_val:
                if isinstance(implements_val, list):
                    bases.extend(implements_val)
                elif isinstance(implements_val, str):
                    bases.append(implements_val)
            specs.append(ForwardElementSpec(
                kind=ElementKind.CLASS,
                name=name,
                bases=bases,
                is_abstract=kind_str == "interface",
                decomposition_source="source-java-parser",
            ))
        elif kind_str in ("method", "constructor"):
            ret = getattr(el, "return_type", None)
            modifiers = getattr(el, "modifiers", [])
            specs.append(ForwardElementSpec(
                kind=ElementKind.METHOD,
                name=name,
                parent_class=getattr(el, "parent", None),
                signature=Signature(params=[], return_annotation=ret),
                is_static="static" in modifiers,
                is_abstract="abstract" in modifiers,
                decomposition_source="source-java-parser",
            ))
        # Skip field, constant — not useful for element generation

    return specs


def _parse_class_signature(
    sig_str: str,
) -> Optional[tuple[str, list[str]]]:
    """Parse a class signature like ``Class X(Base1, Base2)`` or ``class X(Base)``.

    Returns ``(class_name, [base_classes])`` or ``None`` on parse failure.
    """
    cleaned = sig_str.strip()
    lower = cleaned.lower()
    if lower.startswith("class "):
        cleaned = cleaned[len("class "):]
    else:
        return None

    paren_idx = cleaned.find("(")
    if paren_idx < 1:
        # Class with no bases: "Class Foo"
        name = cleaned.strip()
        return (name, []) if name else None

    class_name = cleaned[:paren_idx].strip()
    if not class_name:
        return None

    close_paren = cleaned.find(")", paren_idx)
    if close_paren < 0:
        bases_str = cleaned[paren_idx + 1:]
    else:
        bases_str = cleaned[paren_idx + 1: close_paren]

    bases = [b.strip() for b in bases_str.split(",") if b.strip()]
    return (class_name, bases)


# Pattern: "name = value" or "name: type = value"
_VARIABLE_ASSIGN_PATTERN = re.compile(
    r"^([A-Za-z_]\w*)\s*(?::\s*([^=]+?))?\s*=\s*(.+)$",
)


def _parse_variable_pattern(
    sig_str: str,
) -> Optional[tuple[str, Optional[str], Optional[str]]]:
    """Parse a variable/constant assignment pattern.

    Recognises:
    - ``"fake = Faker()"``
    - ``"MAX_RETRIES: int = 3"``
    - ``"PRODUCT_IDS: list[str] = [...]"``

    Returns ``(var_name, type_annotation_or_None, value_repr)`` or ``None``.
    """
    cleaned = sig_str.strip().rstrip(";")
    # Skip function / class definitions — handled by other parsers
    if cleaned.startswith(("def ", "async def ", "class ", "Class ")):
        return None
    m = _VARIABLE_ASSIGN_PATTERN.match(cleaned)
    if not m:
        return None
    var_name = m.group(1)
    type_ann = m.group(2).strip() if m.group(2) else None
    value_repr = m.group(3).strip()
    return (var_name, type_ann, value_repr)


def _format_signature_for_binding(
    func_name: str, sig: Optional[Signature]
) -> str:
    """Format a function name with its parsed signature for binding text.

    Returns e.g. ``getJSONLogger(name: str) -> logging.Logger`` when a
    parsed signature is available, or just ``func_name`` otherwise.
    """
    if sig is None:
        return func_name
    params = []
    for p in sig.params:
        part = p.name
        if p.annotation:
            part = f"{p.name}: {p.annotation}"
        if p.default:
            part = f"{part} = {p.default}"
        params.append(part)
    result = f"{func_name}({', '.join(params)})"
    if sig.return_annotation:
        result = f"{result} -> {sig.return_annotation}"
    return result


def _format_schema_field_parts(
    req_schema: object, resp_schema: object,
) -> list[str]:
    """Format request/response schema fields into binding text parts.

    Defensively accesses field dicts per [O11Y Leg 8 #3] existence→type→access.
    Returns an empty list if neither schema has fields.
    """
    parts: list[str] = []
    for label, schema in (("request_fields", req_schema), ("response_fields", resp_schema)):
        if not isinstance(schema, dict):
            continue
        fields = schema.get("fields", [])
        if not fields or not isinstance(fields, list):
            continue
        field_names = ", ".join(
            f.get("name", "?") for f in fields[:5] if isinstance(f, dict)
        )
        if field_names:
            parts.append(f"{label}=[{field_names}]")
    return parts


def _compute_binding_text_from_kwargs(kwargs: dict[str, object]) -> str:
    """Compute binding_text directly from kwargs without creating a partial model.

    Mirrors ``compute_binding_text()`` logic but reads from the kwargs dict
    instead of an ``InterfaceContract`` instance, avoiding the need for an
    unvalidated ``model_construct()`` call.
    """
    confidence = kwargs.get("confidence")
    prefix = (
        "[BINDING]"
        if confidence in (ContractConfidence.EXPLICIT, ContractConfidence.INFERRED)
        else "[ADVISORY]"
    )

    parts: list[str] = [prefix]

    cat = kwargs.get("category")
    if cat == ContractCategory.FUNCTION_NAME and kwargs.get("function_name"):
        parts.append(f"function={kwargs['function_name']}")
    elif cat == ContractCategory.CLASS_NAME and kwargs.get("class_name"):
        parts.append(f"class={kwargs['class_name']}")
        if kwargs.get("base_class"):
            parts.append(f"base={kwargs['base_class']}")
    elif cat == ContractCategory.API_ENDPOINT and kwargs.get("endpoint"):
        parts.append(f"endpoint={kwargs['endpoint']}")
        parts.extend(_format_schema_field_parts(
            kwargs.get("request_schema"), kwargs.get("response_schema"),
        ))
    elif cat == ContractCategory.CONFIG_KEY and kwargs.get("env_var"):
        parts.append(f"env_var={kwargs['env_var']}")
    elif cat == ContractCategory.IMPORT_PATH and kwargs.get("import_path"):
        parts.append(f"import_path={kwargs['import_path']}")
    elif cat == ContractCategory.FORMULA and kwargs.get("formula"):
        parts.append(f"formula={kwargs['formula']}")
        if kwargs.get("constant_value"):
            parts.append(f"value={kwargs['constant_value']}")
    elif cat == ContractCategory.RENDER_PATTERN and kwargs.get("pattern"):
        parts.append(f"pattern={kwargs['pattern']}")
    elif cat == ContractCategory.INFRASTRUCTURE and kwargs.get("dependency"):
        parts.append(f"dependency={kwargs['dependency']}")

    parts.append(str(kwargs.get("description", "")))
    return " | ".join(parts)


def _make_contract(**kwargs: object) -> InterfaceContract:
    """Build an ``InterfaceContract`` with auto-computed ``binding_text``.

    Computes ``binding_text`` directly from the kwargs dict, then creates
    a single fully-validated ``InterfaceContract`` instance.
    """
    kwargs["binding_text"] = _compute_binding_text_from_kwargs(kwargs)
    return InterfaceContract(**kwargs)  # type: ignore[arg-type]


# ═══════════════════════════════════════════════════════════════════════════
# Extractors
# ═══════════════════════════════════════════════════════════════════════════


class DeterministicExtractor:
    """Extract contracts from ``ParsedFeature`` fields deterministically."""

    def extract(
        self,
        features: list[ParsedFeature],
        prior_file_specs: Optional[dict[str, ForwardFileSpec]] = None,
    ) -> tuple[list[InterfaceContract], dict[str, list[ForwardElementSpec]]]:
        """Return (contracts, file_elements) from parsed features.

        Args:
            features: Parsed features from plan ingestion.
            prior_file_specs: Optional file specs from a prior enriched manifest.
                When provided, plan-derived specs are supplemented with richer
                data (return annotations, decorators, docstrings) from prior specs.
        """
        contracts: list[InterfaceContract] = []
        file_elements: dict[str, list[ForwardElementSpec]] = {}

        for feature in features:
            contracts.extend(self._extract_api_signatures(feature, file_elements))
            contracts.extend(self._extract_runtime_dependencies(feature))
            contracts.extend(self._extract_protocol(feature))

            # FR-DFA-003: Produce file_elements entries for non-Python target
            # files (e.g. Dockerfiles) so they receive a ForwardFileSpec
            # downstream.  Empty elements list signals single-unit file.
            self._register_non_python_targets(feature, file_elements)

        # Shared files across features
        contracts.extend(self._extract_shared_files(features))

        # REQ-3.1.1: Link self/cls-bearing functions to their parent class.
        self._link_methods_to_classes(file_elements)

        # Field-level supplement from prior specs
        if prior_file_specs:
            self._supplement_from_prior(file_elements, prior_file_specs)

        return contracts, file_elements

    def _supplement_from_prior(
        self,
        file_elements: dict[str, list[ForwardElementSpec]],
        prior_file_specs: dict[str, ForwardFileSpec],
    ) -> None:
        """Supplement plan-derived specs with richer data from prior specs."""
        for filepath, specs in file_elements.items():
            prior_spec = prior_file_specs.get(filepath)
            if prior_spec is None:
                continue
            prior_by_key = {
                (e.name, e.parent_class): e for e in prior_spec.elements
            }
            updated: list[ForwardElementSpec] = []
            for spec in specs:
                key = (spec.name, spec.parent_class)
                prior = prior_by_key.get(key)
                if prior is None:
                    updated.append(spec)
                    continue
                updates: dict[str, object] = {}
                if (
                    spec.signature
                    and spec.signature.return_annotation is None
                    and prior.signature
                    and prior.signature.return_annotation is not None
                ):
                    updates["signature"] = spec.signature.model_copy(
                        update={"return_annotation": prior.signature.return_annotation}
                    )
                if not spec.decorators and prior.decorators:
                    updates["decorators"] = list(prior.decorators)
                if spec.docstring_hint is None and prior.docstring_hint is not None:
                    updates["docstring_hint"] = prior.docstring_hint
                if updates:
                    updated.append(spec.model_copy(update=updates))
                else:
                    updated.append(spec)
            file_elements[filepath] = updated

    @staticmethod
    def _link_methods_to_classes(
        file_elements: dict[str, list[ForwardElementSpec]],
    ) -> None:
        """Link self/cls-bearing functions to their parent class (REQ-3.1.1).

        After api_signatures extraction, a method like ``add_fields(self, ...)``
        is stored as ``kind=FUNCTION, parent_class=None`` because the signature
        string has no dotted class prefix.  This pass promotes such elements to
        ``kind=METHOD`` (or ``CLASSMETHOD``) and sets ``parent_class`` to the
        CLASS element in the same file, enabling downstream decomposition
        (REQ-MP-901).

        When the file contains a single class, all self/cls-bearing functions
        are linked to it.  When multiple classes exist, a proximity heuristic
        is used: each function is linked to the nearest preceding CLASS element
        in the list (which preserves ``api_signatures`` ordering).
        """
        for filepath, specs in file_elements.items():
            # Collect class names in this file
            class_names = {
                s.name for s in specs if s.kind == ElementKind.CLASS
            }
            if not class_names:
                continue

            # Build a positional map: for each index, find the nearest
            # preceding CLASS element.  LLMs list methods right after their
            # parent class in api_signatures, so list order is meaningful.
            nearest_class: dict[int, str] = {}
            last_class: Optional[str] = None
            for i, s in enumerate(specs):
                if s.kind == ElementKind.CLASS:
                    last_class = s.name
                nearest_class[i] = last_class  # type: ignore[assignment]

            updated: list[ForwardElementSpec] = []
            for i, spec in enumerate(specs):
                if (
                    spec.kind in (ElementKind.FUNCTION, ElementKind.ASYNC_FUNCTION)
                    and spec.parent_class is None
                    and spec.signature
                    and spec.signature.params
                ):
                    first_param = spec.signature.params[0].name
                    # Resolve parent: single class → trivial; multiple → proximity
                    parent: Optional[str] = None
                    if first_param in ("self", "cls"):
                        if len(class_names) == 1:
                            parent = next(iter(class_names))
                        elif nearest_class.get(i):
                            parent = nearest_class[i]

                    if first_param == "self" and parent:
                        new_kind = (
                            ElementKind.ASYNC_METHOD
                            if spec.kind == ElementKind.ASYNC_FUNCTION
                            else ElementKind.METHOD
                        )
                        spec = spec.model_copy(update={
                            "kind": new_kind,
                            "parent_class": parent,
                        })
                        logger.debug(
                            "REQ-3.1.1: Linked %s to class %s in %s",
                            spec.name, parent, filepath,
                        )
                    elif first_param == "cls" and parent:
                        spec = spec.model_copy(update={
                            "kind": ElementKind.METHOD,
                            "parent_class": parent,
                            "is_classmethod": True,
                        })
                        logger.debug(
                            "REQ-3.1.1: Linked classmethod %s to class %s in %s",
                            spec.name, parent, filepath,
                        )
                updated.append(spec)
            file_elements[filepath] = updated

    @staticmethod
    def _register_non_python_targets(
        feature: ParsedFeature,
        file_elements: dict[str, list[ForwardElementSpec]],
    ) -> None:
        """Register non-Python target files so they receive ForwardFileSpecs.

        Dockerfiles and other non-Python files have no AST-extractable
        elements, but they need a file_elements entry (even empty) so the
        downstream ``ForwardManifest`` builder creates a ``ForwardFileSpec``
        for them.  Without this, ``prime_adapter._generate_skeletons()``
        sees ``file_spec is None`` and bypasses the file entirely.
        """
        from startd8.micro_prime.lang_detect import detect_language

        for target in feature.target_files or []:
            if target in file_elements:
                continue  # already registered (e.g. Python file with elements)
            lang = detect_language(target)
            if lang != "python":
                file_elements[target] = []  # empty elements = single-unit file
                logger.debug(
                    "FR-DFA-003: Registered non-Python target %s (lang=%s) "
                    "with empty element list",
                    target, lang,
                )

    # File extensions that support Python API signature extraction.
    _PYTHON_EXTENSIONS = frozenset((".py", ".pyi"))

    def _extract_api_signatures(
        self,
        feature: ParsedFeature,
        file_elements: dict[str, list[ForwardElementSpec]],
    ) -> list[InterfaceContract]:
        """Parse api_signatures into FUNCTION_NAME contracts + ForwardElementSpecs."""
        # Skip signature extraction for non-Python files (Dockerfile, .in, .yaml, etc.)
        if feature.target_files:
            ext = Path(feature.target_files[0]).suffix.lower()
            # Files with no extension (e.g. "Dockerfile") get ext=""
            if ext not in self._PYTHON_EXTENSIONS:
                if feature.api_signatures:
                    logger.debug(
                        "Feature %s targets non-Python file %s; "
                        "skipping %d api_signature(s)",
                        feature.feature_id,
                        feature.target_files[0],
                        len(feature.api_signatures),
                    )
                return []

        contracts: list[InterfaceContract] = []
        total_signatures = len(feature.api_signatures)
        skipped_signatures = 0
        for sig_str in feature.api_signatures:
            # --- Try class signature first ---
            class_parsed = _parse_class_signature(sig_str)
            if class_parsed:
                class_name, bases = class_parsed
                abbrev = _CATEGORY_ABBREV[ContractCategory.CLASS_NAME]
                # Site 1 (original line 458) — file_path differentiates
                # identically-named classes across different files.
                target_file = feature.target_files[0] if feature.target_files else None
                contract_id = make_element_id(abbrev, class_name, file_path=target_file)
                base_class_str = bases[0] if bases else None

                contract = _make_contract(
                    contract_id=contract_id,
                    category=ContractCategory.CLASS_NAME,
                    confidence=ContractConfidence.INFERRED,
                    description=(
                        f"Class {class_name} extending {', '.join(bases)}"
                        if bases
                        else f"Class {class_name} from API signature"
                    ),
                    class_name=class_name,
                    base_class=base_class_str,
                    source_reference="deterministic",
                    applicable_task_ids=[feature.feature_id],
                )
                contracts.append(contract)

                # Build ForwardElementSpec with kind=CLASS and bases
                if feature.target_files:
                    target_file = feature.target_files[0]
                    spec = ForwardElementSpec(
                        kind=ElementKind.CLASS,
                        name=class_name,
                        bases=bases,
                        source_contract_id=contract_id,
                    )
                    file_elements.setdefault(target_file, []).append(spec)
                continue

            # --- Try variable/constant assignment pattern ---
            var_parsed = _parse_variable_pattern(sig_str)
            if var_parsed and feature.target_files:
                var_name, type_ann, value_repr = var_parsed
                target_file = feature.target_files[0]
                # UPPER_SNAKE_CASE → CONSTANT, else VARIABLE
                is_upper = var_name == var_name.upper() and "_" in var_name
                kind = ElementKind.CONSTANT if is_upper else ElementKind.VARIABLE
                spec = ForwardElementSpec(
                    kind=kind,
                    name=var_name,
                    type_annotation=type_ann,
                    value_repr=value_repr,
                )
                file_elements.setdefault(target_file, []).append(spec)
                logger.debug(
                    "Variable/constant %r (%s) extracted for %s in feature %s",
                    var_name, kind.value, target_file, feature.feature_id,
                )
                continue

            # --- Try function/method signature ---
            func_name = _extract_function_name(sig_str)
            if not func_name:
                skipped_signatures += 1
                logger.debug(
                    "Skipping unparseable signature in feature %s: %r",
                    feature.feature_id,
                    sig_str,
                )
                continue

            abbrev = _CATEGORY_ABBREV[ContractCategory.FUNCTION_NAME]
            # Site 2 (original line 501) — file_path differentiates
            # identically-named functions across different files.
            target_file = feature.target_files[0] if feature.target_files else None
            contract_id = make_element_id(abbrev, func_name, file_path=target_file)

            # Build richer description with signature detail when parseable
            parsed_sig = _parse_python_signature(sig_str)
            sig_text = _format_signature_for_binding(func_name, parsed_sig)

            contract = _make_contract(
                contract_id=contract_id,
                category=ContractCategory.FUNCTION_NAME,
                confidence=ContractConfidence.INFERRED,
                description=f"Function {sig_text} from API signature",
                function_name=func_name,
                source_reference="deterministic",
                applicable_task_ids=[feature.feature_id],
            )
            contracts.append(contract)

            # Build ForwardElementSpec for the target file
            if not parsed_sig and feature.target_files:
                level = (
                    logging.WARNING
                    if "." not in func_name
                    else logging.ERROR
                )
                logger.log(
                    level,
                    "Signature parsed name %r but not params in feature %s: %r "
                    "(contract created, element spec skipped%s)",
                    func_name, feature.feature_id, sig_str,
                    "; dotted method name — class decomposition will fail"
                    if "." in func_name else "",
                )
            if parsed_sig and feature.target_files:
                target_file = feature.target_files[0]

                # Detect async-ness from the original signature before
                # prefix stripping (which removes the "async" keyword).
                is_async = _detect_async_prefix(sig_str)

                # Derive parent_class from dotted name (last-dot split)
                parent_class = None
                element_name = func_name
                element_kind = (
                    ElementKind.ASYNC_FUNCTION if is_async
                    else ElementKind.FUNCTION
                )
                if "." in func_name:
                    last_dot = func_name.rfind(".")
                    parent_class = func_name[:last_dot]
                    element_name = func_name[last_dot + 1:]
                    element_kind = (
                        ElementKind.ASYNC_METHOD if is_async
                        else ElementKind.METHOD
                    )
                    # Warn on deeply nested classes (>2 nesting levels)
                    if parent_class.count(".") > 1:
                        logger.warning(
                            "Deeply nested class path (%d levels) in feature %s: %s",
                            parent_class.count(".") + 1,
                            feature.feature_id,
                            func_name,
                        )

                spec = ForwardElementSpec(
                    kind=element_kind,
                    name=element_name,
                    signature=parsed_sig,
                    parent_class=parent_class,
                    source_contract_id=contract_id,
                )
                file_elements.setdefault(target_file, []).append(spec)

        # Log at INFO if >10% of signatures failed to parse
        if (
            skipped_signatures > 0
            and total_signatures > 0
            and skipped_signatures / total_signatures > 0.10
        ):
            logger.info(
                "Feature %s: %d/%d API signatures failed to parse (%.0f%% skip rate)",
                feature.feature_id,
                skipped_signatures,
                total_signatures,
                100.0 * skipped_signatures / total_signatures,
            )

        return contracts

    def _extract_runtime_dependencies(
        self, feature: ParsedFeature
    ) -> list[InterfaceContract]:
        """Convert runtime_dependencies into IMPORT_PATH contracts."""
        contracts: list[InterfaceContract] = []
        for dep in feature.runtime_dependencies:
            abbrev = _CATEGORY_ABBREV[ContractCategory.IMPORT_PATH]
            # Site 3 (original line 572)
            contract_id = make_element_id(abbrev, dep)

            contract = _make_contract(
                contract_id=contract_id,
                category=ContractCategory.IMPORT_PATH,
                confidence=ContractConfidence.INFERRED,
                description=f"Runtime dependency: {dep}",
                import_path=dep,
                source_reference="deterministic",
                applicable_task_ids=[feature.feature_id],
            )
            contracts.append(contract)
        return contracts

    def _extract_protocol(self, feature: ParsedFeature) -> list[InterfaceContract]:
        """Convert non-empty protocol into an INFRASTRUCTURE contract."""
        if not feature.protocol or feature.protocol == "none":
            return []

        protocol_desc = _PROTOCOL_MAP.get(
            feature.protocol, f"{feature.protocol} transport"
        )
        abbrev = _CATEGORY_ABBREV[ContractCategory.INFRASTRUCTURE]
        # Site 4 (original line 595)
        contract_id = make_element_id(abbrev, feature.protocol)

        contract = _make_contract(
            contract_id=contract_id,
            category=ContractCategory.INFRASTRUCTURE,
            confidence=ContractConfidence.INFERRED,
            description=protocol_desc,
            dependency=feature.protocol,
            source_reference="deterministic",
            applicable_task_ids=[feature.feature_id],
        )
        return [contract]

    def _extract_shared_files(
        self, features: list[ParsedFeature]
    ) -> list[InterfaceContract]:
        """Extract contracts for files shared across multiple features."""
        contracts: list[InterfaceContract] = []

        # Count file occurrences across features
        file_counts: Counter[str] = Counter(
            f for feature in features for f in feature.target_files
        )

        # Files appearing in 2+ features
        for filepath, count in file_counts.items():
            if count < 2:
                continue
            abbrev = _CATEGORY_ABBREV[ContractCategory.IMPORT_PATH]
            # Site 5 (original line 624)
            contract_id = make_element_id(abbrev, f"shared-{Path(filepath).stem}")

            contract = _make_contract(
                contract_id=contract_id,
                category=ContractCategory.IMPORT_PATH,
                confidence=ContractConfidence.INFERRED,
                description=f"Shared file across {count} features: {filepath}",
                import_path=filepath,
                source_reference="deterministic",
                applicable_task_ids=[],  # project-wide
            )
            contracts.append(contract)

        # Known utility file patterns — O(1) dedup via set
        seen_ids: set[str] = {c.contract_id for c in contracts}
        for feature in features:
            for filepath in feature.target_files:
                basename = Path(filepath).name
                if basename in _UTILITY_FILE_PATTERNS:
                    name, category = _UTILITY_FILE_PATTERNS[basename]
                    abbrev = _CATEGORY_ABBREV[category]
                    # Site 6 (original line 645)
                    contract_id = make_element_id(abbrev, f"util-{name}")

                    if contract_id in seen_ids:
                        continue
                    seen_ids.add(contract_id)

                    kwargs: dict[str, object] = {
                        "contract_id": contract_id,
                        "category": category,
                        "confidence": ContractConfidence.INFERRED,
                        "description": f"Utility pattern: {name} in {basename}",
                        "source_reference": "deterministic",
                        "applicable_task_ids": [],
                    }
                    if category == ContractCategory.FUNCTION_NAME:
                        kwargs["function_name"] = name
                    elif category == ContractCategory.CLASS_NAME:
                        kwargs["class_name"] = name

                    contracts.append(_make_contract(**kwargs))

        return contracts


class HumanYamlExtractor:
    """Extract contracts from human-authored YAML."""

    def extract(self, yaml_text: str) -> list[InterfaceContract]:
        """Parse YAML text and return explicit contracts."""
        try:
            data = yaml.safe_load(yaml_text)
        except yaml.YAMLError as exc:
            logger.warning("Failed to parse human YAML: %s", exc)
            return []

        if not isinstance(data, dict):
            return []

        shared = data.get("shared_contracts", [])
        if not isinstance(shared, list):
            return []

        contracts: list[InterfaceContract] = []
        for entry in shared:
            try:
                if not isinstance(entry, dict):
                    continue
                for required in ("contract_id", "category", "description"):
                    if required not in entry:
                        raise KeyError(f"Missing required field: {required}")

                category = ContractCategory(entry["category"])

                # Build kwargs from entry
                kwargs: dict[str, object] = {
                    "contract_id": entry["contract_id"],
                    "category": category,
                    "confidence": ContractConfidence.EXPLICIT,
                    "description": entry["description"],
                    "source_reference": "human-yaml",
                }
                # Forward optional fields
                for field_name in (
                    "function_name", "class_name", "base_class", "endpoint",
                    "env_var", "import_path", "formula", "constant_value",
                    "pattern", "dependency",
                ):
                    if field_name in entry:
                        kwargs[field_name] = entry[field_name]

                if "applicable_task_ids" in entry:
                    kwargs["applicable_task_ids"] = entry["applicable_task_ids"]

                contracts.append(_make_contract(**kwargs))
            except (KeyError, ValueError) as exc:
                logger.warning("Skipping malformed YAML entry: %s", exc)
                continue

        return contracts


class ProtoExtractor:
    """Extract contracts from ``.proto`` files."""

    _SERVICE_RE = re.compile(r"service\s+(\w+)\s*\{")
    _RPC_RE = re.compile(
        r"rpc\s+(\w+)\s*\(\s*(\w+)\s*\)\s*returns\s*\(\s*(\w+)\s*\)"
    )
    _MESSAGE_RE = re.compile(r"message\s+(\w+)\s*\{")
    _FIELD_RE = re.compile(
        r"^\s*(?:repeated\s+|optional\s+|map<\w+,\s*\w+>\s+)?(\w+)\s+(\w+)\s*=\s*(\d+)",
        re.MULTILINE,
    )

    def extract(self, proto_dir: Optional[Path]) -> list[InterfaceContract]:
        """Scan proto_dir for .proto files and extract contracts."""
        if proto_dir is None or not proto_dir.exists():
            return []

        contracts: list[InterfaceContract] = []
        for proto_file in proto_dir.glob("**/*.proto"):
            try:
                content = proto_file.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as exc:
                logger.warning("Cannot read %s: %s", proto_file, exc)
                continue

            # Parse message field schemas for B4 enrichment
            message_fields = self._parse_message_fields(content)

            # Services → CLASS_NAME
            for match in self._SERVICE_RE.finditer(content):
                name = match.group(1)
                abbrev = _CATEGORY_ABBREV[ContractCategory.CLASS_NAME]
                # Site 7 (original line 761)
                contracts.append(
                    _make_contract(
                        contract_id=make_element_id(abbrev, f"svc-{name}"),
                        category=ContractCategory.CLASS_NAME,
                        confidence=ContractConfidence.EXPLICIT,
                        description=f"gRPC service: {name}",
                        class_name=name,
                        source_reference="proto",
                    )
                )

            # RPCs → API_ENDPOINT with request/response schemas (B4)
            for match in self._RPC_RE.finditer(content):
                name = match.group(1)
                req_type = match.group(2)
                resp_type = match.group(3)
                abbrev = _CATEGORY_ABBREV[ContractCategory.API_ENDPOINT]

                req_schema = message_fields.get(req_type)
                resp_schema = message_fields.get(resp_type)

                description = (
                    f"gRPC RPC method: {name}"
                    f" ({req_type}) returns ({resp_type})"
                )

                # Site 8 (original line 787)
                contracts.append(
                    _make_contract(
                        contract_id=make_element_id(abbrev, f"rpc-{name}"),
                        category=ContractCategory.API_ENDPOINT,
                        confidence=ContractConfidence.EXPLICIT,
                        description=description,
                        endpoint=name,
                        request_schema=req_schema,
                        response_schema=resp_schema,
                        source_reference="proto",
                    )
                )

            # Messages → CLASS_NAME
            for match in self._MESSAGE_RE.finditer(content):
                name = match.group(1)
                abbrev = _CATEGORY_ABBREV[ContractCategory.CLASS_NAME]
                # Site 9 (original line 804)
                contracts.append(
                    _make_contract(
                        contract_id=make_element_id(abbrev, f"msg-{name}"),
                        category=ContractCategory.CLASS_NAME,
                        confidence=ContractConfidence.EXPLICIT,
                        description=f"Protobuf message: {name}",
                        class_name=name,
                        source_reference="proto",
                    )
                )

        return contracts

    def _parse_message_fields(
        self, content: str
    ) -> dict[str, dict[str, list[dict[str, str]]]]:
        """Parse message definitions into field schemas.

        Returns a dict mapping message name to a schema dict with a
        ``fields`` key listing each field's type, name, and number.
        """
        schemas: dict[str, dict[str, list[dict[str, str]]]] = {}
        for msg_match in self._MESSAGE_RE.finditer(content):
            msg_name = msg_match.group(1)
            # Find the message body (from opening brace to matching close)
            start = msg_match.end()
            brace_depth = 1
            pos = start
            while pos < len(content) and brace_depth > 0:
                if content[pos] == "{":
                    brace_depth += 1
                elif content[pos] == "}":
                    brace_depth -= 1
                pos += 1
            body = content[start:pos - 1] if pos > start else ""

            fields: list[dict[str, str]] = []
            for field_match in self._FIELD_RE.finditer(body):
                fields.append({
                    "type": field_match.group(1),
                    "name": field_match.group(2),
                    "number": field_match.group(3),
                })
            if fields:
                schemas[msg_name] = {"fields": fields}
        return schemas


# ═══════════════════════════════════════════════════════════════════════════
# REFERENCE_AST — Behavioral contracts from reference source files
# ═══════════════════════════════════════════════════════════════════════════


class _ASTPatternVisitor(ast.NodeVisitor):
    """Walk a Python AST and collect behavioral patterns.

    Extracts:
    - FORMULA: ``dict_obj[key] = expr`` assignments (behavioral field assignments)
    - RENDER_PATTERN: calls with string literal arguments (format strings, templates)
    - CONFIG_KEY: ``os.environ[key]``, ``os.environ.get(key)``, ``os.getenv(key)``
    - INFRASTRUCTURE: calls to known infrastructure constructors
    """

    # Constructor names that indicate infrastructure setup
    _INFRA_CONSTRUCTORS: frozenset[str] = frozenset({
        "TracerProvider", "OTLPSpanExporter", "BatchSpanProcessor",
        "ConsoleSpanExporter", "OTLPMetricExporter",
        "GrpcInstrumentorServer", "GrpcInstrumentorClient",
        "select_autoescape", "FileSystemLoader",
        "Environment",  # Jinja2
    })

    def __init__(self) -> None:
        self.formulas: list[tuple[str, str, str]] = []  # (target, field, value_repr)
        self.render_patterns: list[tuple[str, str]] = []  # (call_name, string_arg)
        self.config_keys: list[tuple[str, Optional[str]]] = []  # (env_var, default)
        self.infra_calls: list[tuple[str, list[str]]] = []  # (constructor, [kwarg_names])

    def visit_Assign(self, node: ast.Assign) -> None:
        """Detect ``dict_obj[key] = value`` patterns (FORMULA)."""
        for target in node.targets:
            if isinstance(target, ast.Subscript) and isinstance(target.slice, ast.Constant):
                key = target.slice.value
                if isinstance(key, str):
                    # Target name: unparse the object being subscripted
                    try:
                        target_name = ast.unparse(target.value)
                    except Exception:
                        target_name = "?"
                    try:
                        value_repr = ast.unparse(node.value)
                    except Exception:
                        value_repr = "?"
                    self.formulas.append((target_name, str(key), value_repr))
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        """Detect string-arg calls (RENDER_PATTERN), env var access (CONFIG_KEY),
        and infrastructure constructors (INFRASTRUCTURE)."""
        call_name = self._call_name(node)
        if not call_name:
            self.generic_visit(node)
            return

        # --- CONFIG_KEY: os.environ["X"], os.environ.get("X"), os.getenv("X") ---
        if call_name in ("os.environ.get", "os.getenv"):
            if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                default = None
                if len(node.args) > 1 and isinstance(node.args[1], ast.Constant):
                    default = str(node.args[1].value)
                self.config_keys.append((node.args[0].value, default))

        # --- INFRASTRUCTURE: known constructor calls ---
        short_name = call_name.rsplit(".", 1)[-1]
        if short_name in self._INFRA_CONSTRUCTORS:
            kwarg_names = [kw.arg for kw in node.keywords if kw.arg]
            # Also capture positional string args as render patterns
            for arg in node.args:
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str) and len(arg.value) > 3:
                    self.render_patterns.append((call_name, arg.value))
            self.infra_calls.append((call_name, kwarg_names))

        # --- RENDER_PATTERN: any call with a string literal arg containing % or { ---
        elif node.args:
            for arg in node.args:
                if (
                    isinstance(arg, ast.Constant)
                    and isinstance(arg.value, str)
                    and len(arg.value) > 3
                    and ("%" in arg.value or "{" in arg.value)
                ):
                    self.render_patterns.append((call_name, arg.value))

        self.generic_visit(node)

    def visit_Subscript(self, node: ast.Subscript) -> None:
        """Detect ``os.environ["X"]`` (CONFIG_KEY)."""
        if isinstance(node.slice, ast.Constant) and isinstance(node.slice.value, str):
            try:
                obj_name = ast.unparse(node.value)
            except Exception:
                obj_name = ""
            if obj_name == "os.environ":
                self.config_keys.append((node.slice.value, None))
        self.generic_visit(node)

    @staticmethod
    def _call_name(node: ast.Call) -> Optional[str]:
        """Extract the dotted call name from a Call node."""
        if isinstance(node.func, ast.Name):
            return node.func.id
        if isinstance(node.func, ast.Attribute):
            try:
                return ast.unparse(node.func)
            except Exception:
                return None
        return None


def _build_behavioral_contracts(
    relpath: str,
    visitor: _ASTPatternVisitor,
    feature_ids: list[str],
    seen_ids: set[str],
    source_ref: str,
    source_label: str,
) -> list[InterfaceContract]:
    """Convert ``_ASTPatternVisitor`` findings into behavioral contracts.

    Shared by ``ReferenceASTExtractor`` (scans external reference files) and
    ``SourceReconciler`` (scans the project's own existing files).

    Args:
        relpath: Relative file path for provenance.
        visitor: Populated ``_ASTPatternVisitor`` instance.
        feature_ids: Task IDs to scope the contracts to.
        seen_ids: Mutable set of already-emitted contract IDs (dedup).
        source_ref: Value for ``source_reference`` (e.g. ``"reference-ast"``
            or ``"source-ast"``).
        source_label: Human-readable label for descriptions (e.g.
            ``"reference"`` or ``"existing source"``).
    """
    contracts: list[InterfaceContract] = []
    stem = Path(relpath).stem
    # Prefix for contract IDs — distinguish reference-ast from source-ast
    id_tag = "ref" if source_ref == "reference-ast" else "src"

    # --- FORMULA contracts ---
    for target_name, field_name, value_repr in visitor.formulas:
        # Site 10 (original line 991)
        contract_id = make_element_id(
            _CATEGORY_ABBREV[ContractCategory.FORMULA],
            f"{id_tag}-{stem}-{field_name}",
        )
        if contract_id in seen_ids:
            continue
        seen_ids.add(contract_id)
        contracts.append(_make_contract(
            contract_id=contract_id,
            category=ContractCategory.FORMULA,
            confidence=ContractConfidence.EXPLICIT,
            description=(
                f"{target_name}['{field_name}'] must use {value_repr} "
                f"(from {source_label} {relpath})"
            ),
            formula=f"{target_name}['{field_name}'] = {value_repr}",
            source_reference=source_ref,
            applicable_task_ids=feature_ids,
        ))

    # --- RENDER_PATTERN contracts ---
    for call_name, string_arg in visitor.render_patterns:
        short_name = call_name.rsplit(".", 1)[-1]
        arg_hash = hex(hash(string_arg) & 0xFFFF)[2:]
        # Site 11 (original line 1012)
        contract_id = make_element_id(
            _CATEGORY_ABBREV[ContractCategory.RENDER_PATTERN],
            f"{id_tag}-{stem}-{short_name}-{arg_hash}",
        )
        if contract_id in seen_ids:
            continue
        seen_ids.add(contract_id)
        contracts.append(_make_contract(
            contract_id=contract_id,
            category=ContractCategory.RENDER_PATTERN,
            confidence=ContractConfidence.EXPLICIT,
            description=(
                f"{call_name}(...) renders with template {string_arg!r} "
                f"(from {source_label} {relpath})"
            ),
            pattern=string_arg,
            source_reference=source_ref,
            applicable_task_ids=feature_ids,
        ))

    # --- CONFIG_KEY contracts ---
    for env_var, default_val in visitor.config_keys:
        # Site 12 (original line 1031)
        contract_id = make_element_id(
            _CATEGORY_ABBREV[ContractCategory.CONFIG_KEY],
            f"{id_tag}-{stem}-{env_var}",
        )
        if contract_id in seen_ids:
            continue
        seen_ids.add(contract_id)
        contracts.append(_make_contract(
            contract_id=contract_id,
            category=ContractCategory.CONFIG_KEY,
            confidence=ContractConfidence.EXPLICIT,
            description=(
                f"Environment variable {env_var}"
                + (f" (default: {default_val})" if default_val else "")
                + f" used in {source_label} {relpath}"
            ),
            env_var=env_var,
            source_reference=source_ref,
            applicable_task_ids=feature_ids,
        ))

    # --- INFRASTRUCTURE contracts ---
    for constructor, kwarg_names in visitor.infra_calls:
        short_name = constructor.rsplit(".", 1)[-1]
        # Site 13 (original line 1053)
        contract_id = make_element_id(
            _CATEGORY_ABBREV[ContractCategory.INFRASTRUCTURE],
            f"{id_tag}-{stem}-{short_name}",
        )
        if contract_id in seen_ids:
            continue
        seen_ids.add(contract_id)
        contracts.append(_make_contract(
            contract_id=contract_id,
            category=ContractCategory.INFRASTRUCTURE,
            confidence=ContractConfidence.EXPLICIT,
            description=(
                f"{constructor}"
                + (f" with kwargs={kwarg_names}" if kwarg_names else "")
                + f" in {source_label} {relpath}"
            ),
            dependency=short_name,
            source_reference=source_ref,
            applicable_task_ids=feature_ids,
        ))

    return contracts


# ═══════════════════════════════════════════════════════════════════════════
# Source Reconciler
# ═══════════════════════════════════════════════════════════════════════════


@dataclass
class SourceReconcileConfig:
    """Configuration for source reconciliation.

    Attributes:
        enabled: Master switch for reconciliation.
        max_file_size_bytes: Skip files exceeding this byte size (default 1 MB).
        exclude_files: Exact relative file paths to skip entirely.
    """

    enabled: bool = True
    max_file_size_bytes: int = 1_000_000
    exclude_files: set[str] = field(default_factory=set)


@dataclass
class SourceReconciler:
    """Reconcile the project's existing source files against detected features.

    When called with a project root directory, scans all Python files and
    extracts behavioral contracts (FORMULA, RENDER_PATTERN, CONFIG_KEY,
    INFRASTRUCTURE) plus basic function/class signatures.

    Used to populate contracts from "source-ast" (existing project code),
    which has lower precedence than "deterministic" and "human-yaml".
    """

    project_root: Path
    encoding: str = "utf-8"

    def reconcile(
        self,
        features: list[ParsedFeature],
        file_elements: Optional[dict[str, list[ForwardElementSpec]]] = None,
    ) -> list[InterfaceContract]:
        """Scan project source files and return source-derived contracts.

        Supports Python (AST-based), Go (regex-based), and Java files.

        When *file_elements* is provided, Go/Java reconciliation also populates
        element specs (REQ-EE-200).  Source-derived elements take precedence
        over ``parse-llm`` elements for the same file.
        """
        if not self.project_root.is_dir():
            logger.warning("project_root does not exist: %s", self.project_root)
            return []

        contracts: list[InterfaceContract] = []
        seen_ids: set[str] = set()

        # Map each feature to its target files
        feature_by_file: dict[str, list[ParsedFeature]] = {}
        for feature in features:
            for target_file in feature.target_files:
                feature_by_file.setdefault(target_file, []).append(feature)

        # Determine which file extensions to scan
        scan_globs = ["**/*.py"]
        try:
            from startd8.languages import LanguageRegistry
            LanguageRegistry.discover()
            for lang_id in LanguageRegistry.list_languages():
                profile = LanguageRegistry.get(lang_id)
                if profile and lang_id != "python":
                    for ext in profile.source_extensions:
                        scan_globs.append(f"**/*{ext}")
        except (ImportError, AttributeError):
            pass

        # Scan source files
        for glob_pattern in scan_globs:
            for src_file in self.project_root.glob(glob_pattern):
                try:
                    relpath = src_file.relative_to(self.project_root).as_posix()
                except ValueError:
                    continue

                matching_features = feature_by_file.get(relpath, [])
                feature_ids = [f.feature_id for f in matching_features]

                if src_file.suffix == ".py":
                    contracts.extend(self._reconcile_file(
                        src_file, relpath, feature_ids, seen_ids
                    ))
                elif src_file.suffix == ".go":
                    contracts.extend(self._reconcile_go_file(
                        src_file, relpath, feature_ids, seen_ids,
                        file_elements=file_elements,
                    ))
                elif src_file.suffix == ".java":
                    contracts.extend(self._reconcile_java_file(
                        src_file, relpath, feature_ids, seen_ids,
                        file_elements=file_elements,
                    ))

        return contracts

    def _reconcile_file(
        self,
        py_file: Path,
        relpath: str,
        feature_ids: list[str],
        seen_ids: set[str],
    ) -> list[InterfaceContract]:
        """Reconcile a single Python file."""
        try:
            source = py_file.read_text(encoding=self.encoding)
        except (OSError, UnicodeDecodeError) as exc:
            logger.debug("Cannot read %s: %s", py_file, exc)
            return []

        # Parse AST
        try:
            tree = ast.parse(source)
        except SyntaxError as exc:
            logger.debug("Cannot parse %s: %s", py_file, exc)
            return []

        contracts: list[InterfaceContract] = []

        # Walk top-level for function/class definitions
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                func_name = node.name
                abbrev = _CATEGORY_ABBREV[ContractCategory.FUNCTION_NAME]
                # Site 14 (original line 1533)
                contract_id = make_element_id(
                    abbrev,
                    f"src-{Path(relpath).stem}-{func_name}",
                    file_path=relpath,
                )
                if contract_id not in seen_ids:
                    seen_ids.add(contract_id)
                    contracts.append(_make_contract(
                        contract_id=contract_id,
                        category=ContractCategory.FUNCTION_NAME,
                        confidence=ContractConfidence.INFERRED,
                        description=f"Function {func_name} in {relpath}",
                        function_name=func_name,
                        source_reference="source-ast",
                        applicable_task_ids=feature_ids,
                    ))
            elif isinstance(node, ast.ClassDef):
                class_name = node.name
                abbrev = _CATEGORY_ABBREV[ContractCategory.CLASS_NAME]
                # Site 15 (original line 1565)
                contract_id = make_element_id(
                    abbrev,
                    f"src-{Path(relpath).stem}-{class_name}",
                    file_path=relpath,
                )
                if contract_id not in seen_ids:
                    seen_ids.add(contract_id)
                    contracts.append(_make_contract(
                        contract_id=contract_id,
                        category=ContractCategory.CLASS_NAME,
                        confidence=ContractConfidence.INFERRED,
                        description=f"Class {class_name} in {relpath}",
                        class_name=class_name,
                        source_reference="source-ast",
                        applicable_task_ids=feature_ids,
                    ))

        # Walk AST for behavioral patterns
        visitor = _ASTPatternVisitor()
        visitor.visit(tree)

        contracts.extend(_build_behavioral_contracts(
            relpath, visitor, feature_ids, seen_ids,
            source_ref="source-ast",
            source_label="existing source",
        ))

        return contracts

    def _reconcile_go_file(
        self,
        go_file: Path,
        relpath: str,
        feature_ids: list[str],
        seen_ids: set[str],
        file_elements: Optional[dict[str, list[ForwardElementSpec]]] = None,
    ) -> list[InterfaceContract]:
        """Reconcile a single Go file using regex-based parsing."""
        try:
            from startd8.languages.go_parser import parse_go_source
        except ImportError:
            return []

        try:
            source = go_file.read_text(encoding=self.encoding)
        except (OSError, UnicodeDecodeError) as exc:
            logger.debug("Cannot read %s: %s", go_file, exc)
            return []

        elements = parse_go_source(source)
        contracts: list[InterfaceContract] = []

        for elem in elements:
            if elem.kind == "function" or elem.kind == "method":
                abbrev = _CATEGORY_ABBREV[ContractCategory.FUNCTION_NAME]
                name_key = elem.name
                if elem.parent_type:
                    name_key = f"{elem.parent_type}.{elem.name}"
                contract_id = make_element_id(
                    abbrev,
                    f"src-{Path(relpath).stem}-{name_key}",
                    file_path=relpath,
                )
                if contract_id not in seen_ids:
                    seen_ids.add(contract_id)
                    desc = f"{'Method' if elem.kind == 'method' else 'Function'} {name_key} in {relpath}"
                    contracts.append(_make_contract(
                        contract_id=contract_id,
                        category=ContractCategory.FUNCTION_NAME,
                        confidence=ContractConfidence.INFERRED,
                        description=desc,
                        function_name=name_key,
                        source_reference="source-go-parser",
                        applicable_task_ids=feature_ids,
                    ))
            elif elem.kind == "class":
                abbrev = _CATEGORY_ABBREV[ContractCategory.CLASS_NAME]
                contract_id = make_element_id(
                    abbrev,
                    f"src-{Path(relpath).stem}-{elem.name}",
                    file_path=relpath,
                )
                if contract_id not in seen_ids:
                    seen_ids.add(contract_id)
                    kind_label = "interface" if elem.is_interface else "struct"
                    contracts.append(_make_contract(
                        contract_id=contract_id,
                        category=ContractCategory.CLASS_NAME,
                        confidence=ContractConfidence.INFERRED,
                        description=f"Go {kind_label} {elem.name} in {relpath}",
                        class_name=elem.name,
                        source_reference="source-go-parser",
                        applicable_task_ids=feature_ids,
                    ))

        # REQ-EE-200: Populate file_elements from Go parser output
        if file_elements is not None:
            go_specs = _go_elements_to_specs(elements, relpath)
            if go_specs:
                # Source elements take precedence over parse-llm elements
                existing = file_elements.get(relpath, [])
                non_parse = [e for e in existing if e.decomposition_source != "parse-llm"]
                file_elements[relpath] = non_parse + go_specs
                logger.info(
                    "REQ-EE-200: Extracted %d Go element specs from %s",
                    len(go_specs), relpath,
                )

        return contracts

    def _reconcile_java_file(
        self,
        java_file: Path,
        relpath: str,
        feature_ids: list[str],
        seen_ids: set[str],
        file_elements: Optional[dict[str, list[ForwardElementSpec]]] = None,
    ) -> list[InterfaceContract]:
        """Reconcile a single Java file using javalang-based parsing."""
        try:
            from startd8.languages.java_parser import parse_java_source
        except ImportError:
            return []

        try:
            source = java_file.read_text(encoding=self.encoding)
        except (OSError, UnicodeDecodeError) as exc:
            logger.debug("Cannot read %s: %s", java_file, exc)
            return []

        elements = parse_java_source(source)
        contracts: list[InterfaceContract] = []

        for elem in elements:
            if elem.kind in ("method", "constructor"):
                abbrev = _CATEGORY_ABBREV[ContractCategory.FUNCTION_NAME]
                name_key = elem.name
                if elem.parent:
                    name_key = f"{elem.parent}.{elem.name}"
                contract_id = make_element_id(
                    abbrev,
                    f"src-{Path(relpath).stem}-{name_key}",
                    file_path=relpath,
                )
                if contract_id not in seen_ids:
                    seen_ids.add(contract_id)
                    desc = (
                        f"{'Constructor' if elem.kind == 'constructor' else 'Method'}"
                        f" {name_key} in {relpath}"
                    )
                    contracts.append(_make_contract(
                        contract_id=contract_id,
                        category=ContractCategory.FUNCTION_NAME,
                        confidence=ContractConfidence.INFERRED,
                        description=desc,
                        function_name=name_key,
                        source_reference="source-java-parser",
                        applicable_task_ids=feature_ids,
                    ))
            elif elem.kind in ("class", "interface", "enum"):
                abbrev = _CATEGORY_ABBREV[ContractCategory.CLASS_NAME]
                contract_id = make_element_id(
                    abbrev,
                    f"src-{Path(relpath).stem}-{elem.name}",
                    file_path=relpath,
                )
                if contract_id not in seen_ids:
                    seen_ids.add(contract_id)
                    contracts.append(_make_contract(
                        contract_id=contract_id,
                        category=ContractCategory.CLASS_NAME,
                        confidence=ContractConfidence.INFERRED,
                        description=f"Java {elem.kind} {elem.name} in {relpath}",
                        class_name=elem.name,
                        source_reference="source-java-parser",
                        applicable_task_ids=feature_ids,
                    ))

        # REQ-EE-200: Populate file_elements from Java parser output
        if file_elements is not None:
            java_specs = _java_elements_to_specs(elements, relpath)
            if java_specs:
                # Source elements take precedence over parse-llm elements
                existing = file_elements.get(relpath, [])
                non_parse = [e for e in existing if e.decomposition_source != "parse-llm"]
                file_elements[relpath] = non_parse + java_specs
                logger.info(
                    "REQ-EE-200: Extracted %d Java element specs from %s",
                    len(java_specs), relpath,
                )

        return contracts


# ═══════════════════════════════════════════════════════════════════════════
# Reference AST Extractor
# ═══════════════════════════════════════════════════════════════════════════


class ReferenceASTExtractor:
    """Extract behavioral contracts from external reference source files.

    When provided with paths to reference files (e.g., vendored libraries,
    external contract specifications), scans them for behavioral patterns
    (FORMULA, RENDER_PATTERN, CONFIG_KEY, INFRASTRUCTURE) plus function/class
    signatures.

    Contracts from reference files have ``source_reference="reference-ast"``
    and higher precedence than source-ast but lower than human-yaml.
    """

    encoding: str = "utf-8"

    def extract(self, reference_files: Optional[list[Path]]) -> list[InterfaceContract]:
        """Extract contracts from a list of reference source files."""
        if not reference_files:
            return []

        contracts: list[InterfaceContract] = []
        seen_ids: set[str] = set()

        for ref_file in reference_files:
            if not ref_file.is_file():
                logger.debug("Reference file does not exist: %s", ref_file)
                continue

            contracts.extend(self._extract_from_file(ref_file, seen_ids))

        return contracts

    def _extract_from_file(
        self, ref_file: Path, seen_ids: set[str]
    ) -> list[InterfaceContract]:
        """Extract contracts from a single reference file."""
        try:
            source = ref_file.read_text(encoding=self.encoding)
        except (OSError, UnicodeDecodeError) as exc:
            logger.debug("Cannot read reference file %s: %s", ref_file, exc)
            return []

        # Parse AST
        try:
            tree = ast.parse(source)
        except SyntaxError as exc:
            logger.debug("Cannot parse reference file %s: %s", ref_file, exc)
            return []

        contracts: list[InterfaceContract] = []
        relpath = ref_file.as_posix()

        # Walk for function/class definitions
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                func_name = node.name
                abbrev = _CATEGORY_ABBREV[ContractCategory.FUNCTION_NAME]
                contract_id = make_element_id(
                    abbrev,
                    f"ref-{Path(relpath).stem}-{func_name}",
                    file_path=relpath,
                )
                if contract_id not in seen_ids:
                    seen_ids.add(contract_id)
                    contracts.append(_make_contract(
                        contract_id=contract_id,
                        category=ContractCategory.FUNCTION_NAME,
                        confidence=ContractConfidence.EXPLICIT,
                        description=f"Function {func_name} in reference {relpath}",
                        function_name=func_name,
                        source_reference="reference-ast",
                    ))
            elif isinstance(node, ast.ClassDef):
                class_name = node.name
                abbrev = _CATEGORY_ABBREV[ContractCategory.CLASS_NAME]
                contract_id = make_element_id(
                    abbrev,
                    f"ref-{Path(relpath).stem}-{class_name}",
                    file_path=relpath,
                )
                if contract_id not in seen_ids:
                    seen_ids.add(contract_id)
                    contracts.append(_make_contract(
                        contract_id=contract_id,
                        category=ContractCategory.CLASS_NAME,
                        confidence=ContractConfidence.EXPLICIT,
                        description=f"Class {class_name} in reference {relpath}",
                        class_name=class_name,
                        source_reference="reference-ast",
                    ))

        # Walk for behavioral patterns
        visitor = _ASTPatternVisitor()
        visitor.visit(tree)

        contracts.extend(_build_behavioral_contracts(
            relpath, visitor, [], seen_ids,
            source_ref="reference-ast",
            source_label="reference",
        ))

        return contracts


# ═══════════════════════════════════════════════════════════════════════════
# Merger
# ═══════════════════════════════════════════════════════════════════════════


class ManifestMerger:
    """Deduplicate contracts by ``contract_id`` using source precedence.

    Higher-precedence sources (e.g., "human-yaml") override lower ones
    (e.g., "source-ast") when multiple contracts have the same ``contract_id``.
    """

    def merge(self, contract_lists: list[list[InterfaceContract]]) -> list[InterfaceContract]:
        """Merge multiple contract lists, keeping only the highest-precedence
        copy of each contract_id."""
        merged: dict[str, InterfaceContract] = {}

        for contracts in contract_lists:
            for contract in contracts:
                existing = merged.get(contract.contract_id)
                if existing is None:
                    merged[contract.contract_id] = contract
                else:
                    # Keep the higher-precedence (higher numeric value) source
                    existing_prec = _SOURCE_PRECEDENCE.get(existing.source_reference, 0)
                    new_prec = _SOURCE_PRECEDENCE.get(contract.source_reference, 0)
                    if new_prec > existing_prec:
                        merged[contract.contract_id] = contract

        return list(merged.values())


# ═══════════════════════════════════════════════════════════════════════════
# Orchestrator
# ═══════════════════════════════════════════════════════════════════════════


def extract_forward_contracts(
    features: list[ParsedFeature],
    yaml_text: Optional[str] = None,
    proto_dir: Optional[Path] = None,
    reference_files: Optional[list[Path]] = None,
    project_root: Optional[Path] = None,
    prior_manifest: Optional[ForwardManifest] = None,
) -> tuple[list[InterfaceContract], dict[str, list[ForwardElementSpec]]]:
    """Extract forward contracts from multiple sources.

    Orchestrates the three extractors (Deterministic, HumanYaml, Proto) plus
    ReferenceASTExtractor and SourceReconciler, merges by contract_id using
    source precedence, and optionally supplements element specs from a prior
    manifest.

    Args:
        features: Parsed features from plan ingestion.
        yaml_text: Human-authored YAML with shared_contracts blocks.
        proto_dir: Directory containing .proto files.
        reference_files: External reference source files (high precedence).
        project_root: Project root for source reconciliation (low precedence).
        prior_manifest: Optional prior enriched manifest for supplementing
            element specs with richer data (return annotations, decorators).

    Returns:
        (contracts, file_elements) tuple — the merged contract list and the
        map of files to their element specifications.
    """
    # Extract from all sources
    det = DeterministicExtractor()
    prior_file_specs = (
        prior_manifest.file_specs if prior_manifest else None
    )
    det_contracts, file_elements = det.extract(features, prior_file_specs)

    yaml_contracts = []
    if yaml_text:
        yaml_extractor = HumanYamlExtractor()
        yaml_contracts = yaml_extractor.extract(yaml_text)

    proto_contracts = []
    if proto_dir:
        proto_extractor = ProtoExtractor()
        proto_contracts = proto_extractor.extract(proto_dir)

    ref_contracts = []
    if reference_files:
        ref_extractor = ReferenceASTExtractor()
        ref_contracts = ref_extractor.extract(reference_files)

    src_contracts = []
    if project_root:
        src_reconciler = SourceReconciler(project_root)
        src_contracts = src_reconciler.reconcile(features, file_elements=file_elements)

    # Merge all contract lists
    merger = ManifestMerger()
    merged_contracts = merger.merge([
        det_contracts,
        yaml_contracts,
        proto_contracts,
        ref_contracts,
        src_contracts,
    ])

    return merged_contracts, file_elements