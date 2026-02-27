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
import re
from collections import Counter
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
    compute_binding_text,
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

_SOURCE_PRECEDENCE: dict[str, int] = {
    "llm-refine": 0,
    "deterministic": 1,
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
    paren_idx = cleaned.find("(")
    if paren_idx < 1:
        return None
    return cleaned[:paren_idx].strip()


def _make_contract(**kwargs: object) -> InterfaceContract:
    """Build an ``InterfaceContract`` with auto-computed ``binding_text``.

    Uses ``model_construct`` to create a partial instance for
    ``compute_binding_text()``, then constructs the validated model.
    """
    # Build partial for binding_text computation
    partial = InterfaceContract.model_construct(**kwargs)  # type: ignore[arg-type]
    binding = compute_binding_text(partial)
    kwargs["binding_text"] = binding
    return InterfaceContract(**kwargs)  # type: ignore[arg-type]


# ═══════════════════════════════════════════════════════════════════════════
# Extractors
# ═══════════════════════════════════════════════════════════════════════════


class DeterministicExtractor:
    """Extract contracts from ``ParsedFeature`` fields deterministically."""

    def extract(
        self, features: list[ParsedFeature]
    ) -> tuple[list[InterfaceContract], dict[str, list[ForwardElementSpec]]]:
        """Return (contracts, file_elements) from parsed features."""
        contracts: list[InterfaceContract] = []
        file_elements: dict[str, list[ForwardElementSpec]] = {}

        for feature in features:
            contracts.extend(self._extract_api_signatures(feature, file_elements))
            contracts.extend(self._extract_runtime_dependencies(feature))
            contracts.extend(self._extract_protocol(feature))

        # Shared files across features
        contracts.extend(self._extract_shared_files(features))

        return contracts, file_elements

    def _extract_api_signatures(
        self,
        feature: ParsedFeature,
        file_elements: dict[str, list[ForwardElementSpec]],
    ) -> list[InterfaceContract]:
        """Parse api_signatures into FUNCTION_NAME contracts + ForwardElementSpecs."""
        contracts: list[InterfaceContract] = []
        for sig_str in feature.api_signatures:
            func_name = _extract_function_name(sig_str)
            if not func_name:
                logger.debug(
                    "Skipping unparseable signature in feature %s: %r",
                    feature.feature_id,
                    sig_str,
                )
                continue

            abbrev = _CATEGORY_ABBREV[ContractCategory.FUNCTION_NAME]
            contract_id = f"flcm-{abbrev}-{func_name}"

            contract = _make_contract(
                contract_id=contract_id,
                category=ContractCategory.FUNCTION_NAME,
                confidence=ContractConfidence.INFERRED,
                description=f"Function {func_name} from API signature",
                function_name=func_name,
                source_reference="deterministic",
                applicable_task_ids=[feature.feature_id],
            )
            contracts.append(contract)

            # Build ForwardElementSpec for the target file
            parsed_sig = _parse_python_signature(sig_str)
            if parsed_sig and feature.target_files:
                target_file = feature.target_files[0]
                spec = ForwardElementSpec(
                    kind=ElementKind.FUNCTION,
                    name=func_name,
                    signature=parsed_sig,
                    source_contract_id=contract_id,
                )
                file_elements.setdefault(target_file, []).append(spec)

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
    _RPC_RE = re.compile(r"rpc\s+(\w+)\s*\(")
    _MESSAGE_RE = re.compile(r"message\s+(\w+)\s*\{")

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

            # RPCs → API_ENDPOINT
            for match in self._RPC_RE.finditer(content):
                name = match.group(1)
                abbrev = _CATEGORY_ABBREV[ContractCategory.API_ENDPOINT]
                contracts.append(
                    _make_contract(
                        contract_id=f"flcm-{abbrev}-rpc-{name}",
                        category=ContractCategory.API_ENDPOINT,
                        confidence=ContractConfidence.EXPLICIT,
                        description=f"gRPC RPC method: {name}",
                        endpoint=name,
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
                # Higher precedence overwrites
                seen[cid] = contract
            elif new_prec == existing_prec:
                # Equal precedence — retain first, log warning
                logger.warning(
                    "Duplicate contract_id '%s' at same precedence (%s); "
                    "retaining first",
                    cid,
                    contract.source_reference,
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
    """
    try:
        det = DeterministicExtractor()
        det_contracts, file_elements = det.extract(features)

        yaml_contracts: list[InterfaceContract] = []
        if yaml_text:
            yaml_contracts = HumanYamlExtractor().extract(yaml_text)

        proto_contracts: list[InterfaceContract] = []
        if proto_dir is not None:
            proto_contracts = ProtoExtractor().extract(proto_dir)

        contract_lists: list[list[InterfaceContract]] = [
            det_contracts,
            yaml_contracts,
            proto_contracts,
        ]
        if tentative_contracts:
            contract_lists.append(tentative_contracts)

        merger = ManifestMerger()
        manifest = merger.merge(contract_lists, file_elements)

        # Record stage completion
        manifest.stages_completed.append("EXTRACT")

        return manifest
    except Exception:
        logger.exception(
            "Catastrophic failure in extract_forward_contracts "
            "(features=%d, yaml=%s, proto=%s)",
            len(features),
            yaml_text is not None,
            proto_dir,
        )
        return ForwardManifest()


__all__ = [
    "DeterministicExtractor",
    "HumanYamlExtractor",
    "ProtoExtractor",
    "ManifestMerger",
    "extract_forward_contracts",
]
