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
import fnmatch
import re
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml
from pydantic import ValidationError

from startd8.forward_manifest import (
    ContractCategory,
    ContractConfidence,
    ForwardDependencies,
    ForwardElementSpec,
    ForwardFileSpec,
    ForwardImportSpec,
    ForwardManifest,
    InterfaceContract,
    compute_binding_text,
    forward_dependencies_from_deps,
    forward_element_spec_from_element,
    forward_import_spec_from_entry,
)
from startd8.logging_config import get_logger
from startd8.utils.code_manifest import ElementKind, Param, ParamKind, Signature
from startd8.workflows.builtin.plan_ingestion_models import ParsedFeature

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
    """Strip ``def `` or ``async def `` prefix from a signature string."""
    cleaned = sig_str.strip()
    if cleaned.startswith("async def "):
        return cleaned[len("async def "):]
    if cleaned.startswith("def "):
        return cleaned[len("def "):]
    return cleaned


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

    # Wrap as a valid function so ast.parse can handle it
    source = f"def {cleaned}: pass"
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
    if cleaned.startswith("Class ") or cleaned.startswith("class "):
        return None
    paren_idx = cleaned.find("(")
    if paren_idx < 1:
        return None
    return cleaned[:paren_idx].strip()


def _parse_class_signature(
    sig_str: str,
) -> Optional[tuple[str, list[str]]]:
    """Parse a class signature like ``Class X(Base1, Base2)`` or ``class X(Base)``.

    Returns ``(class_name, [base_classes])`` or ``None`` on parse failure.
    """
    cleaned = sig_str.strip()
    for prefix in ("Class ", "class "):
        if cleaned.startswith(prefix):
            cleaned = cleaned[len(prefix):]
            break
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
        # Use the description which now contains the full signature via
        # _format_signature_for_binding (e.g., "Function add_fields(self, ...) -> None from API signature")
        # For the binding key, include the function name
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

        # Shared files across features
        contracts.extend(self._extract_shared_files(features))

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

    def _extract_api_signatures(
        self,
        feature: ParsedFeature,
        file_elements: dict[str, list[ForwardElementSpec]],
    ) -> list[InterfaceContract]:
        """Parse api_signatures into FUNCTION_NAME contracts + ForwardElementSpecs."""
        contracts: list[InterfaceContract] = []
        total_signatures = len(feature.api_signatures)
        skipped_signatures = 0
        for sig_str in feature.api_signatures:
            # --- Try class signature first ---
            class_parsed = _parse_class_signature(sig_str)
            if class_parsed:
                class_name, bases = class_parsed
                abbrev = _CATEGORY_ABBREV[ContractCategory.CLASS_NAME]
                contract_id = f"flcm-{abbrev}-{class_name}"
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
            contract_id = f"flcm-{abbrev}-{func_name}"

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
            if parsed_sig and feature.target_files:
                target_file = feature.target_files[0]

                # Derive parent_class from dotted name (last-dot split)
                parent_class = None
                element_name = func_name
                element_kind = ElementKind.FUNCTION
                if "." in func_name:
                    last_dot = func_name.rfind(".")
                    parent_class = func_name[:last_dot]
                    element_name = func_name[last_dot + 1:]
                    element_kind = ElementKind.METHOD
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
            contract_id = f"flcm-{abbrev}-{dep}"

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
        contract_id = f"flcm-{abbrev}-{feature.protocol}"

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
            contract_id = f"flcm-{abbrev}-shared-{Path(filepath).stem}"

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
                    contract_id = f"flcm-{abbrev}-util-{name}"

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
                for field in (
                    "function_name", "class_name", "base_class", "endpoint",
                    "env_var", "import_path", "formula", "constant_value",
                    "pattern", "dependency",
                ):
                    if field in entry:
                        kwargs[field] = entry[field]

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
                contracts.append(
                    _make_contract(
                        contract_id=f"flcm-{abbrev}-svc-{name}",
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

                contracts.append(
                    _make_contract(
                        contract_id=f"flcm-{abbrev}-rpc-{name}",
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
                contracts.append(
                    _make_contract(
                        contract_id=f"flcm-{abbrev}-msg-{name}",
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
        contract_id = f"flcm-{_CATEGORY_ABBREV[ContractCategory.FORMULA]}-{id_tag}-{stem}-{field_name}"
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
        contract_id = f"flcm-{_CATEGORY_ABBREV[ContractCategory.RENDER_PATTERN]}-{id_tag}-{stem}-{short_name}-{arg_hash}"
        if contract_id in seen_ids:
            continue
        seen_ids.add(contract_id)
        contracts.append(_make_contract(
            contract_id=contract_id,
            category=ContractCategory.RENDER_PATTERN,
            confidence=ContractConfidence.EXPLICIT,
            description=(
                f"{call_name}() must receive '{string_arg}' "
                f"(from {source_label} {relpath})"
            ),
            pattern=string_arg,
            source_reference=source_ref,
            applicable_task_ids=feature_ids,
        ))

    # --- CONFIG_KEY contracts ---
    for env_var, default in visitor.config_keys:
        contract_id = f"flcm-{_CATEGORY_ABBREV[ContractCategory.CONFIG_KEY]}-{id_tag}-{env_var}"
        if contract_id in seen_ids:
            continue
        seen_ids.add(contract_id)
        desc = f"Environment variable {env_var}"
        if default is not None:
            desc += f" (default: {default})"
        desc += f" (from {source_label} {relpath})"
        contracts.append(_make_contract(
            contract_id=contract_id,
            category=ContractCategory.CONFIG_KEY,
            confidence=ContractConfidence.EXPLICIT,
            description=desc,
            env_var=env_var,
            constant_value=default,
            source_reference=source_ref,
            applicable_task_ids=feature_ids,
        ))

    # --- INFRASTRUCTURE contracts ---
    for constructor_name, kwarg_names in visitor.infra_calls:
        short_name = constructor_name.rsplit(".", 1)[-1]
        contract_id = f"flcm-{_CATEGORY_ABBREV[ContractCategory.INFRASTRUCTURE]}-{id_tag}-{short_name}"
        if contract_id in seen_ids:
            continue
        seen_ids.add(contract_id)
        desc = f"Use {constructor_name}"
        if kwarg_names:
            desc += f" with kwargs: {', '.join(kwarg_names)}"
        desc += f" (from {source_label} {relpath})"
        contracts.append(_make_contract(
            contract_id=contract_id,
            category=ContractCategory.INFRASTRUCTURE,
            confidence=ContractConfidence.EXPLICIT,
            description=desc,
            dependency=short_name,
            source_reference=source_ref,
            applicable_task_ids=feature_ids,
        ))

    return contracts


class ReferenceASTExtractor:
    """Extract behavioral contracts from reference source files.

    Layer 2 defense: produces FORMULA, RENDER_PATTERN, CONFIG_KEY, and
    INFRASTRUCTURE contracts from Python AST analysis of reference files.
    These contracts prescribe *how* code should behave, not just *what*
    structural elements exist.

    Requires a ``reference_root`` directory containing Python files at
    the same relative paths as ``ParsedFeature.target_files``.
    """

    def __init__(self, max_file_size: int = 500_000) -> None:
        self._max_file_size = max_file_size

    def extract(
        self,
        features: list[ParsedFeature],
        reference_root: Path,
    ) -> list[InterfaceContract]:
        """Scan reference source files and return behavioral contracts.

        Only Python files (``.py``) are analyzed. Non-Python target files
        and missing files are silently skipped.
        """
        contracts: list[InterfaceContract] = []
        seen_ids: set[str] = set()

        # Collect unique (relpath, feature_ids) pairs
        file_features: dict[str, list[str]] = {}
        for feat in features:
            for tf in feat.target_files:
                if tf.endswith(".py"):
                    file_features.setdefault(tf, []).append(feat.feature_id)

        for relpath, feature_ids in file_features.items():
            filepath = reference_root / relpath
            if not filepath.is_file():
                continue
            try:
                if filepath.stat().st_size > self._max_file_size:
                    continue
                source = filepath.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue

            try:
                tree = ast.parse(source, filename=str(relpath))
            except SyntaxError:
                logger.debug("Reference AST parse failed: %s", relpath)
                continue

            visitor = _ASTPatternVisitor()
            visitor.visit(tree)

            file_contracts = _build_behavioral_contracts(
                relpath, visitor, feature_ids, seen_ids,
                source_ref="reference-ast",
                source_label="reference",
            )
            contracts.extend(file_contracts)

        if contracts:
            logger.info(
                "REFERENCE_AST: %d behavioral contracts from %d files "
                "(formula=%d, pattern=%d, config=%d, infra=%d)",
                len(contracts),
                len(file_features),
                sum(1 for c in contracts if c.category == ContractCategory.FORMULA),
                sum(1 for c in contracts if c.category == ContractCategory.RENDER_PATTERN),
                sum(1 for c in contracts if c.category == ContractCategory.CONFIG_KEY),
                sum(1 for c in contracts if c.category == ContractCategory.INFRASTRUCTURE),
            )

        return contracts


# ═══════════════════════════════════════════════════════════════════════════
# SOURCE_RECONCILE — AST-enriched ForwardManifest
# ═══════════════════════════════════════════════════════════════════════════


@dataclass
class SourceReconcileConfig:
    """Configuration for the SOURCE_RECONCILE stage.

    Attributes:
        enabled: Master switch for reconciliation.
        max_file_size_bytes: Skip files exceeding this byte size (default 1 MB).
        max_line_count: Reserved for future LOC-based filtering.
        exclude_patterns: Glob patterns for paths to skip (matched via fnmatch).
    """

    enabled: bool = True
    max_file_size_bytes: int = 1_000_000  # 1 MB cap
    max_line_count: int = 10_000
    exclude_patterns: list[str] = field(
        default_factory=lambda: [".venv/*", "vendor/*", "node_modules/*"],
    )


@dataclass
class ReconciliationStats:
    """Statistics from a SOURCE_RECONCILE run.

    Attributes:
        files_scanned: Files successfully parsed and merged.
        files_skipped: Files skipped (missing, oversized, symlink, cached, etc.).
        files_with_errors: Files that failed AST parsing.
        elements_added: New elements merged from AST.
        elements_skipped: Elements already present in plan-derived specs.
        specs_invalid: Elements that failed ``ForwardElementSpec`` validation.
        imports_added: New imports merged from AST.
        imports_skipped: Imports already present or dropped (relative normalization).
        dependencies_added: Files whose dependencies were filled from AST.
        wall_clock_ms: Total reconciliation wall-clock time in milliseconds.
        file_fingerprints: SHA-256 digests keyed by relpath for cache-skip on rerun.
    """

    files_scanned: int = 0
    files_skipped: int = 0
    files_with_errors: int = 0
    elements_added: int = 0
    elements_skipped: int = 0
    specs_invalid: int = 0
    imports_added: int = 0
    imports_skipped: int = 0
    dependencies_added: int = 0
    behavioral_contracts_added: int = 0
    wall_clock_ms: float = 0.0
    file_fingerprints: dict[str, str] = field(default_factory=dict)


class SourceReconciler:
    """Enrich ForwardManifest with AST-derived elements from existing source files.

    Mottainai Rule 5: prefer deterministic (AST) over stochastic (LLM).
    Only fills GAPS — plan-derived elements have higher precedence.
    """

    def reconcile(
        self,
        manifest: ForwardManifest,
        project_root: Path,
        target_files: Optional[list[str]] = None,
        config: Optional[SourceReconcileConfig] = None,
        design_doc_sections: Optional[dict[str, list[str]]] = None,
        features: Optional[list[ParsedFeature]] = None,
    ) -> ReconciliationStats:
        """Run SOURCE_RECONCILE on existing target files.

        Args:
            manifest: The ForwardManifest to enrich (mutated in place via
                dict reassignment of file_specs values).
            project_root: Project root directory.
            target_files: Additional file paths to scan beyond manifest keys.
            config: Reconciliation configuration.
            design_doc_sections: Per-file design doc sections for docstring
                enrichment (REQ-DDS-004). Keys are file paths.
            features: Optional parsed features for behavioral contract
                extraction. When provided, Python files in the project are
                also scanned for FORMULA, RENDER_PATTERN, CONFIG_KEY, and
                INFRASTRUCTURE patterns that should be followed by new code.

        Returns:
            ReconciliationStats with counts of added/skipped items.
        """
        config = config or SourceReconcileConfig()
        stats = ReconciliationStats()

        if not config.enabled:
            return stats

        start = time.monotonic()

        # Collect all file paths to scan
        all_paths: set[str] = set(manifest.file_specs.keys())
        if target_files:
            all_paths.update(target_files)

        project_root = Path(project_root).resolve()
        cached_fingerprints: dict[str, str] = (
            manifest.metadata.get("file_fingerprints") or {}  # type: ignore[assignment]
        )
        already_reconciled = "SOURCE_RECONCILE" in manifest.stages_completed

        for relpath in sorted(all_paths):
            self._reconcile_file(
                relpath, project_root, manifest, config, stats,
                cached_fingerprints, already_reconciled, design_doc_sections,
            )

        # Behavioral contract extraction from existing project files
        if features:
            behavioral = self._extract_behavioral_contracts(
                features, project_root, config, stats,
            )
            if behavioral:
                # Append to manifest contracts (merger dedup already happened,
                # so use contract_id set to avoid duplicates with existing contracts)
                existing_ids = {c.contract_id for c in manifest.contracts}
                new_contracts = [c for c in behavioral if c.contract_id not in existing_ids]
                manifest.contracts.extend(new_contracts)
                stats.behavioral_contracts_added = len(new_contracts)

        # [R1-S6] Provenance + [R3-S6] timing
        stats.wall_clock_ms = (time.monotonic() - start) * 1000
        manifest.metadata["reconcile_stats"] = {
            "files_scanned": stats.files_scanned,
            "files_skipped": stats.files_skipped,
            "files_with_errors": stats.files_with_errors,
            "elements_added": stats.elements_added,
            "elements_skipped": stats.elements_skipped,
            "specs_invalid": stats.specs_invalid,
            "imports_added": stats.imports_added,
            "imports_skipped": stats.imports_skipped,
            "dependencies_added": stats.dependencies_added,
            "behavioral_contracts_added": stats.behavioral_contracts_added,
            "wall_clock_ms": stats.wall_clock_ms,
        }
        manifest.metadata["file_fingerprints"] = dict(stats.file_fingerprints)

        if stats.wall_clock_ms > 2000:
            logger.warning(
                "SOURCE_RECONCILE took %.0fms (>2000ms budget)",
                stats.wall_clock_ms,
            )

        return stats

    @staticmethod
    def _extract_behavioral_contracts(
        features: list[ParsedFeature],
        project_root: Path,
        config: SourceReconcileConfig,
        stats: ReconciliationStats,
    ) -> list[InterfaceContract]:
        """Extract behavioral contracts from existing Python files in the project.

        Scans files that are NOT target files of any feature (i.e., existing
        sibling files) to discover patterns that new code should follow.
        Also scans target files that already exist (editing an existing file).
        """
        contracts: list[InterfaceContract] = []
        seen_ids: set[str] = set()

        # Build map of all Python files to their associated feature IDs
        # For behavioral extraction, scan ALL existing .py files in directories
        # that contain target files — sibling files establish patterns
        target_dirs: set[str] = set()
        file_features: dict[str, list[str]] = {}
        for feat in features:
            for tf in feat.target_files:
                if tf.endswith(".py"):
                    file_features.setdefault(tf, []).append(feat.feature_id)
                    parent = str(Path(tf).parent)
                    if parent != ".":
                        target_dirs.add(parent)

        # Scan existing Python files in target directories
        scanned: set[str] = set()
        for target_dir in sorted(target_dirs):
            dir_path = project_root / target_dir
            if not dir_path.is_dir():
                continue
            for py_file in sorted(dir_path.glob("*.py")):
                if py_file.is_symlink():
                    continue
                relpath = str(py_file.relative_to(project_root))
                if relpath in scanned:
                    continue
                scanned.add(relpath)

                # Skip files matching exclude patterns
                if any(fnmatch.fnmatch(relpath, pat) for pat in config.exclude_patterns):
                    continue

                try:
                    if py_file.stat().st_size > config.max_file_size_bytes:
                        continue
                    source = py_file.read_text(encoding="utf-8")
                except (OSError, UnicodeDecodeError):
                    continue

                try:
                    tree = ast.parse(source, filename=relpath)
                except SyntaxError:
                    continue

                visitor = _ASTPatternVisitor()
                visitor.visit(tree)

                # Determine which features these contracts apply to:
                # If the file IS a target file, scope to that feature.
                # If it's a sibling, scope to all features in the same directory.
                if relpath in file_features:
                    applicable_ids = file_features[relpath]
                else:
                    applicable_ids = [
                        fid
                        for tf, fids in file_features.items()
                        if str(Path(tf).parent) == target_dir
                        for fid in fids
                    ]

                file_contracts = _build_behavioral_contracts(
                    relpath, visitor, applicable_ids, seen_ids,
                    source_ref="source-ast",
                    source_label="existing source",
                )
                contracts.extend(file_contracts)

        if contracts:
            logger.info(
                "SOURCE_RECONCILE behavioral: %d contracts from %d files "
                "(formula=%d, pattern=%d, config=%d, infra=%d)",
                len(contracts),
                len(scanned),
                sum(1 for c in contracts if c.category == ContractCategory.FORMULA),
                sum(1 for c in contracts if c.category == ContractCategory.RENDER_PATTERN),
                sum(1 for c in contracts if c.category == ContractCategory.CONFIG_KEY),
                sum(1 for c in contracts if c.category == ContractCategory.INFRASTRUCTURE),
            )

        return contracts

    def _reconcile_file(
        self,
        relpath: str,
        project_root: Path,
        manifest: ForwardManifest,
        config: SourceReconcileConfig,
        stats: ReconciliationStats,
        cached_fingerprints: dict[str, str],
        already_reconciled: bool,
        design_doc_sections: Optional[dict[str, list[str]]],
    ) -> None:
        """Validate, parse, and merge AST data for a single file.

        Mutates *manifest* and *stats* in place.  Returns early if the file
        should be skipped (missing, oversized, symlink, outside root, cached).
        """
        from startd8.utils.code_manifest import generate_file_manifest

        raw_path = project_root / relpath

        # [R1-S7] Safety: reject symlinks before resolving
        if raw_path.is_symlink():
            logger.debug("Skipping symlink: %s", relpath)
            stats.files_skipped += 1
            return

        resolved = raw_path.resolve()
        try:
            if not resolved.is_relative_to(project_root):
                logger.warning("Path outside project root, skipping: %s", relpath)
                stats.files_skipped += 1
                return
        except (TypeError, ValueError):
            stats.files_skipped += 1
            return

        if not resolved.is_file():
            stats.files_skipped += 1
            return

        # [R1-S4] Exclude patterns
        if any(fnmatch.fnmatch(relpath, pat) for pat in config.exclude_patterns):
            stats.files_skipped += 1
            return

        # [R1-S4] Size cap
        try:
            file_size = resolved.stat().st_size
        except OSError as exc:
            logger.debug("Cannot stat %s: %s", relpath, exc)
            stats.files_skipped += 1
            return
        if file_size > config.max_file_size_bytes:
            logger.debug("File too large (%d bytes), skipping: %s", file_size, relpath)
            stats.files_skipped += 1
            return

        # Run AST analysis
        try:
            file_manifest = generate_file_manifest(
                resolved, project_root, mode="ast_only",
            )
        except Exception as exc:
            logger.warning("AST parse failed for %s: %s", relpath, exc)
            stats.files_with_errors += 1
            return

        if file_manifest.errors:
            logger.warning(
                "AST parse errors in %s: %s",
                relpath,
                [e.message for e in file_manifest.errors],
            )
            stats.files_with_errors += 1
            return

        # Store fingerprint
        stats.file_fingerprints[relpath] = file_manifest.digest

        # [R3-S1] Cache check — must be after successful parse to get digest
        if (
            already_reconciled
            and cached_fingerprints.get(relpath) == file_manifest.digest
        ):
            stats.files_skipped += 1
            return

        stats.files_scanned += 1

        # Get or create ForwardFileSpec
        file_spec = manifest.file_specs.get(relpath)
        existing_elements = list(file_spec.elements) if file_spec else []
        existing_imports = list(file_spec.imports) if file_spec else []
        existing_deps = file_spec.dependencies if file_spec else None

        # Build existing key sets
        existing_element_keys: set[tuple[Optional[str], str]] = {
            (spec.parent_class, spec.name) for spec in existing_elements
        }
        existing_import_keys: set[tuple[str, tuple[str, ...]]] = {
            (spec.module, tuple(sorted(spec.names)))
            for spec in existing_imports
        }

        merged_elements = list(existing_elements)
        merged_imports = list(existing_imports)

        # Per-file design doc sections for docstring enrichment
        file_sections = (
            (design_doc_sections or {}).get(relpath) or []
        )

        # Process top-level elements from AST
        for element in file_manifest.elements:

            # Rich provenance ID: flcm-ast-{relpath}:{start_line}:{fqn}
            source_id = (
                f"flcm-ast-{relpath}:{element.span.start_line}:{element.fqn}"
            )

            key = (None, element.name)
            if key not in existing_element_keys:
                try:
                    spec = forward_element_spec_from_element(
                        element, source_contract_id=source_id,
                    )
                    # REQ-DDS-004: Enrich docstring_hint from design sections
                    if spec.docstring_hint is None and file_sections:
                        hint = _match_design_section(element.name, file_sections)
                        if hint:
                            spec = spec.model_copy(update={"docstring_hint": hint})
                    merged_elements.append(spec)
                    existing_element_keys.add(key)
                    stats.elements_added += 1
                except (ValueError, ValidationError) as exc:
                    logger.warning(
                        "Invalid spec for %s in %s: %s",
                        element.name, relpath, exc,
                    )
                    stats.specs_invalid += 1
            else:
                stats.elements_skipped += 1

            # Process class children (methods, constants, variables)
            if element.kind == ElementKind.CLASS:
                for child in element.children:
                    child_key = (element.name, child.name)
                    if child_key not in existing_element_keys:
                        child_source_id = (
                            f"flcm-ast-{relpath}:{child.span.start_line}:{child.fqn}"
                        )
                        try:
                            child_spec = forward_element_spec_from_element(
                                child, source_contract_id=child_source_id,
                            )
                            # Ensure parent_class is set correctly
                            if child_spec.parent_class != element.name:
                                child_spec = child_spec.model_copy(
                                    update={"parent_class": element.name}
                                )
                            # REQ-DDS-004
                            if child_spec.docstring_hint is None and file_sections:
                                hint = _match_design_section(child.name, file_sections)
                                if hint:
                                    child_spec = child_spec.model_copy(
                                        update={"docstring_hint": hint},
                                    )
                            merged_elements.append(child_spec)
                            existing_element_keys.add(child_key)
                            stats.elements_added += 1
                        except (ValueError, ValidationError) as exc:
                            logger.warning(
                                "Invalid spec for %s.%s in %s: %s",
                                element.name, child.name, relpath, exc,
                            )
                            stats.specs_invalid += 1
                    else:
                        stats.elements_skipped += 1

        # Process imports from AST
        for imp_entry in file_manifest.imports:
            imp_key = (imp_entry.module, tuple(sorted(imp_entry.names)))
            if imp_key not in existing_import_keys:
                fwd_imp = forward_import_spec_from_entry(
                    imp_entry, project_root, resolved,
                )
                if fwd_imp is not None:
                    merged_imports.append(fwd_imp)
                    existing_import_keys.add(imp_key)
                    stats.imports_added += 1
                else:
                    stats.imports_skipped += 1
            else:
                stats.imports_skipped += 1

        # Dependencies
        merged_deps = existing_deps
        if existing_deps is None and file_manifest.dependencies:
            merged_deps = forward_dependencies_from_deps(file_manifest.dependencies)
            stats.dependencies_added += 1

        # [R1-S5] Deterministic ordering
        merged_elements.sort(key=lambda e: (e.parent_class or "", e.name))
        merged_imports.sort(key=lambda i: (i.module, tuple(sorted(i.names))))

        # REQ-FLCM-P4: Semantic dedup by bound Python name
        merged_imports = _deduplicate_imports_by_bound_name(merged_imports)

        # [R2-S4] Frozen model — create new ForwardFileSpec
        new_file_spec = ForwardFileSpec(
            file=relpath,
            elements=merged_elements,
            imports=merged_imports,
            dependencies=merged_deps,
        )
        manifest.file_specs[relpath] = new_file_spec


def _compute_bound_names(spec: "ForwardImportSpec") -> set[str]:
    """Compute the Python names an import binds into scope.

    - ``kind="import"`` → ``{alias}`` or ``{module.split(".")[0]}``
    - ``kind="from"`` → ``{alias}`` or ``set(names)``
    """
    if spec.alias:
        return {spec.alias}
    if spec.kind == "import":
        return {spec.module.split(".")[0]}
    # kind == "from"
    return set(spec.names) if spec.names else {spec.module.split(".")[-1]}


def _deduplicate_imports_by_bound_name(
    imports: list["ForwardImportSpec"],
) -> list["ForwardImportSpec"]:
    """Post-pass dedup: remove imports that bind already-claimed Python names.

    When a bare ``import`` and a ``from`` import bind the same name,
    the ``from`` import wins (more specific).  Otherwise first-wins.

    For multi-name ``from`` imports where only *some* names conflict,
    the entire import is kept (novel names still need it).
    """
    # seen: bound_name → index into `result` list
    seen: dict[str, int] = {}
    result: list["ForwardImportSpec"] = []

    for spec in imports:
        bound = _compute_bound_names(spec)

        # Partition bound names into novel vs conflicting
        novel_names = {b for b in bound if b not in seen}
        conflict_names = bound - novel_names

        if not conflict_names:
            # All names are novel — keep as-is
            result_idx = len(result)
            result.append(spec)
            for bname in bound:
                seen[bname] = result_idx
            continue

        if not novel_names:
            # All names conflict — check if from-import should replace bare
            # Only replace when *every* conflicting name points to a bare import
            replace_indices: set[int] = set()
            should_replace = spec.kind == "from"
            if should_replace:
                for bname in conflict_names:
                    prev_idx = seen[bname]
                    if result[prev_idx].kind == "import":
                        replace_indices.add(prev_idx)
                    else:
                        should_replace = False
                        break

            if should_replace and replace_indices:
                # Remove previous bare-import entries (by marking None, compact later)
                for ri in replace_indices:
                    result[ri] = None  # type: ignore[assignment]
                result_idx = len(result)
                result.append(spec)
                for bname in bound:
                    seen[bname] = result_idx
            # else: first-wins — discard current
            continue

        # Mixed: some names conflict, some are novel.
        # Keep the import for its novel names; conflicting names are harmless
        # at the FLCM level (the repair step handles actual code dedup).
        result_idx = len(result)
        result.append(spec)
        for bname in novel_names:
            seen[bname] = result_idx

    # Compact: remove None entries left by replacements
    return [s for s in result if s is not None]


def _match_design_section(
    element_name: str, sections: list[str],
) -> Optional[str]:
    """Best-effort word-boundary match of element name in design sections.

    Returns the first matching section text, or ``None``.
    Uses ``\\b`` word boundaries to avoid partial matches (e.g., ``"get"``
    should not match ``"get_name"``).  Deterministic only — no fuzzy
    matching (Mottainai Rule 5).
    """
    pattern = re.compile(r"\b" + re.escape(element_name) + r"\b")
    for section in sections:
        if pattern.search(section):
            return section
    return None


# ═══════════════════════════════════════════════════════════════════════════
# Merger
# ═══════════════════════════════════════════════════════════════════════════


class ManifestMerger:
    """Merge contracts from multiple extractors with precedence-based dedup."""

    def merge(
        self,
        contract_lists: list[list[InterfaceContract]],
        file_elements: dict[str, list[ForwardElementSpec]],
    ) -> ForwardManifest:
        """Flatten, deduplicate, and assemble into a ``ForwardManifest``."""
        # Flatten all contracts
        all_contracts: list[InterfaceContract] = []
        for clist in contract_lists:
            all_contracts.extend(clist)

        # Deduplicate by contract_id using source precedence
        seen: dict[str, InterfaceContract] = {}
        for contract in all_contracts:
            cid = contract.contract_id
            if cid not in seen:
                seen[cid] = contract
                continue

            existing = seen[cid]
            existing_prec = _SOURCE_PRECEDENCE.get(
                existing.source_reference or "", 99
            )
            new_prec = _SOURCE_PRECEDENCE.get(
                contract.source_reference or "", 99
            )

            if new_prec > existing_prec:
                # Higher precedence overwrites — but preserve task scoping
                # from the lower-precedence contract if the winner has none.
                if not contract.applicable_task_ids and existing.applicable_task_ids:
                    merged_ids = list(existing.applicable_task_ids)
                    seen[cid] = contract.model_copy(
                        update={"applicable_task_ids": merged_ids},
                    )
                else:
                    seen[cid] = contract
            elif new_prec == existing_prec:
                # Equal precedence — retain first, merge task scoping
                merged_ids = list(existing.applicable_task_ids)
                for tid in contract.applicable_task_ids:
                    if tid not in merged_ids:
                        merged_ids.append(tid)
                if merged_ids != list(existing.applicable_task_ids):
                    seen[cid] = existing.model_copy(
                        update={"applicable_task_ids": merged_ids},
                    )
                logger.warning(
                    "Duplicate contract_id '%s' at same precedence (%s); "
                    "retaining first, merged applicable_task_ids=%s",
                    cid,
                    contract.source_reference,
                    merged_ids,
                )
            # else: lower precedence — discard

        # Build file specs from file_elements
        file_specs: dict[str, ForwardFileSpec] = {}
        for filepath, elements in file_elements.items():
            file_specs[filepath] = ForwardFileSpec(file=filepath, elements=elements)

        return ForwardManifest(
            contracts=list(seen.values()),
            file_specs=file_specs,
        )


# ═══════════════════════════════════════════════════════════════════════════
# Orchestrator
# ═══════════════════════════════════════════════════════════════════════════


def extract_forward_contracts(
    features: list[ParsedFeature],
    *,
    yaml_text: Optional[str] = None,
    proto_dir: Optional[Path] = None,
    tentative_contracts: Optional[list[InterfaceContract]] = None,
    project_root: Optional[Path] = None,
    prior_file_specs: Optional[dict[str, ForwardFileSpec]] = None,
    reference_root: Optional[Path] = None,
) -> ForwardManifest:
    """Orchestrate all extractors and merge into a ``ForwardManifest``.

    Parameters
    ----------
    features:
        Parsed features from plan ingestion.
    yaml_text:
        Optional human-authored YAML with ``shared_contracts``.
    proto_dir:
        Optional directory containing ``.proto`` files.
    tentative_contracts:
        Optional pre-existing tentative contracts to include.
    project_root:
        Optional project root. When provided, triggers SOURCE_RECONCILE
        to enrich the manifest with AST-derived elements from existing files.
    prior_file_specs:
        Optional file specs from a prior enriched manifest for field-level
        supplement of plan-derived specs.
    reference_root:
        Optional directory containing reference source files. When provided,
        triggers REFERENCE_AST extraction to produce behavioral contracts
        (FORMULA, RENDER_PATTERN, CONFIG_KEY, INFRASTRUCTURE) from Python
        AST analysis of existing reference implementations.
    """
    try:
        det = DeterministicExtractor()
        det_contracts, file_elements = det.extract(
            features, prior_file_specs=prior_file_specs,
        )

        yaml_contracts: list[InterfaceContract] = []
        if yaml_text:
            yaml_contracts = HumanYamlExtractor().extract(yaml_text)

        proto_contracts: list[InterfaceContract] = []
        if proto_dir is not None:
            proto_contracts = ProtoExtractor().extract(proto_dir)

        ref_contracts: list[InterfaceContract] = []
        if reference_root is not None:
            ref_root = Path(reference_root)
            if ref_root.is_dir():
                ref_contracts = ReferenceASTExtractor().extract(features, ref_root)

        contract_lists: list[list[InterfaceContract]] = [
            det_contracts,
            yaml_contracts,
            proto_contracts,
            ref_contracts,
        ]
        if tentative_contracts:
            contract_lists.append(tentative_contracts)

        merger = ManifestMerger()
        manifest = merger.merge(contract_lists, file_elements)

        # Record stage completion
        manifest.stages_completed.append("EXTRACT")
        if ref_contracts:
            manifest.stages_completed.append("REFERENCE_AST")

        # SOURCE_RECONCILE: enrich with AST-derived elements from existing files
        # Also extracts behavioral contracts when features are provided
        if project_root is not None:
            all_targets = list({
                f for feat in features for f in feat.target_files
            })
            reconciler = SourceReconciler()
            stats = reconciler.reconcile(
                manifest, project_root, all_targets, features=features,
            )
            manifest.stages_completed.append("SOURCE_RECONCILE")
            logger.info(
                "SOURCE_RECONCILE: +%d elements, +%d imports, "
                "+%d behavioral contracts from %d files",
                stats.elements_added,
                stats.imports_added,
                stats.behavioral_contracts_added,
                stats.files_scanned,
            )

        return manifest
    except (OSError, ValueError, KeyError, TypeError) as exc:
        logger.exception(
            "Catastrophic failure in extract_forward_contracts "
            "(features=%d, yaml=%s, proto=%s): %s",
            len(features),
            yaml_text is not None,
            proto_dir,
            exc,
        )
        return ForwardManifest()


__all__ = [
    "DeterministicExtractor",
    "HumanYamlExtractor",
    "ProtoExtractor",
    "ReferenceASTExtractor",
    "ManifestMerger",
    "SourceReconciler",
    "SourceReconcileConfig",
    "ReconciliationStats",
    "extract_forward_contracts",
]
