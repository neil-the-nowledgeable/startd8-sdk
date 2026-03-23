"""Element deriver — populate ForwardElementSpec from feature metadata (REQ-DFA-108).

Derives elements for non-Python files when no existing source is available
for AST extraction. Uses progressive enrichment tiers:

T0: Filename → primary type name (class/interface/struct)
T1: + Description keywords → base class/interface
T2: + ForwardManifest contracts → method signatures
T3: + LanguageProfile framework_imports → DI constructor params + imports

Idempotent: never overwrites existing elements from AST extraction.
"""

from __future__ import annotations

import re
from pathlib import PurePosixPath
from typing import Any, Dict, List, Optional, Tuple

from startd8.logging_config import get_logger

logger = get_logger(__name__)

# Extension → language_id mapping
_EXT_TO_LANG: Dict[str, str] = {
    ".cs": "csharp",
    ".go": "go",
    ".java": "java",
    ".js": "nodejs",
    ".ts": "nodejs",
    ".tsx": "nodejs",
    ".mjs": "nodejs",
}

# Extensions that should be processed by the deriver
_SOURCE_EXTENSIONS = frozenset(_EXT_TO_LANG.keys())

# C# I-prefix convention for interfaces
_CS_INTERFACE_RE = re.compile(r"^I[A-Z]")

# Common interface/abstract keywords in descriptions
_INTERFACE_KEYWORDS = frozenset({
    "interface", "abstract", "contract", "protocol", "defines methods",
})


def derive_elements_for_file(
    file_path: str,
    feature_description: str = "",
    contracts: Optional[List[Dict[str, Any]]] = None,
    framework_imports: Optional[Dict[str, Any]] = None,
    language_id: str = "",
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Derive ForwardElementSpec dicts and ForwardImportSpec dicts from metadata.

    Progressive enrichment:
    - T0: filename → primary type name
    - T1: + description → base classes/interfaces
    - T2: + contracts → method signatures
    - T3: + framework_imports → constructor DI + imports

    Args:
        file_path: Relative file path (e.g., ``src/cartservice/src/CartStore.cs``).
        feature_description: Feature description text for keyword extraction.
        contracts: ForwardManifest contracts (list of InterfaceContract dicts).
        framework_imports: LanguageProfile framework_imports detection results.
        language_id: Language identifier (auto-detected from extension if empty).

    Returns:
        Tuple of (element_dicts, import_dicts) suitable for ForwardFileSpec.
    """
    ext = PurePosixPath(file_path).suffix.lower()
    if ext not in _SOURCE_EXTENSIONS:
        return [], []

    if not language_id:
        language_id = _EXT_TO_LANG.get(ext, "")

    stem = PurePosixPath(file_path).stem
    elements: List[Dict[str, Any]] = []
    imports: List[Dict[str, Any]] = []

    # T0: Derive primary type from filename
    type_name = stem
    is_interface = _detect_interface(stem, language_id, feature_description)

    if is_interface:
        elements.append({
            "kind": "class",  # ElementKind.CLASS — FM uses "class" for all types
            "name": type_name,
            "bases": [],
            "visibility": "public",
            "decorators": ["interface"] if is_interface else [],
            "decomposition_source": "element_deriver_t0",
        })
    else:
        # T1: Check description for base class/interface hints
        bases = _extract_bases_from_description(
            feature_description, type_name, language_id,
        )
        elements.append({
            "kind": "class",
            "name": type_name,
            "bases": bases,
            "visibility": "public",
            "decorators": [],
            "decomposition_source": "element_deriver_t1" if bases else "element_deriver_t0",
        })

    # T2: Derive method elements from contracts
    if contracts:
        method_elements = _derive_methods_from_contracts(
            contracts, type_name, file_path, language_id,
            feature_description=feature_description,
        )
        elements.extend(method_elements)

    # T3: Derive imports and constructor DI from framework detection
    if framework_imports:
        fw_imports, constructor_params = _derive_framework_context(
            framework_imports, feature_description, language_id,
        )
        imports.extend(fw_imports)

        # Add constructor element with DI params if any
        if constructor_params and not is_interface:
            params = [
                {"name": p["name"], "annotation": p["type"]}
                for p in constructor_params
            ]
            elements.append({
                "kind": "method",
                "name": type_name,  # Constructor name = class name
                "parent_class": type_name,
                "signature": {
                    "params": params,
                    "return_annotation": None,
                },
                "visibility": "public",
                "decorators": [],
                "decomposition_source": "element_deriver_t3",
            })

    return elements, imports


def _detect_interface(
    stem: str, language_id: str, description: str,
) -> bool:
    """Detect if a file should contain an interface definition."""
    # C#: I-prefix convention (ICartStore, IRepository)
    if language_id == "csharp" and _CS_INTERFACE_RE.match(stem):
        return True
    # TypeScript: .d.ts files are type definitions
    # (already handled by extension check upstream)
    # Description keywords (word boundary to avoid "AbstractService" matching "abstract")
    desc_lower = description.lower()
    return any(
        re.search(r'\b' + re.escape(kw) + r'\b', desc_lower)
        for kw in _INTERFACE_KEYWORDS
    )


def _extract_bases_from_description(
    description: str, type_name: str, language_id: str,
) -> List[str]:
    """Extract base class/interface names from description text."""
    bases: List[str] = []
    desc_lower = description.lower()

    # Pattern: "implements IFoo" or "extends BaseFoo"
    for pattern in (
        r"implements\s+(\w+)",
        r"extends\s+(\w+)",
        r"inherits\s+(?:from\s+)?(\w+)",
        r":\s+(I\w+)",  # C# `: ICartStore` notation
    ):
        for m in re.finditer(pattern, description, re.IGNORECASE):
            base = m.group(1)
            if base != type_name:
                bases.append(base)

    return list(dict.fromkeys(bases))  # Dedupe preserving order


def _derive_methods_from_contracts(
    contracts: List[Dict[str, Any]],
    type_name: str,
    file_path: str,
    language_id: str,
    feature_description: str = "",
) -> List[Dict[str, Any]]:
    """Extract method elements from FM contracts applicable to this file."""
    methods: List[Dict[str, Any]] = []

    for contract in contracts:
        # Check if contract applies to this file
        applicable_ids = contract.get("applicable_task_ids", [])
        contract_name = contract.get("name", "")
        category = contract.get("category", "")

        # Match by: contract name contains type name, type name in description,
        # file path in applicable_ids, or description mentions contract name
        name_match = type_name.lower() in contract_name.lower()
        path_match = any(file_path in str(aid) for aid in applicable_ids)
        # Also match if the contract is a method (FUNCTION_NAME) and the
        # feature description mentions it — the method belongs to this class
        desc_match = (
            category in ("FUNCTION_NAME", "function_name")
            and contract_name.lower() in feature_description.lower()
        ) if feature_description else False

        if not name_match and not path_match and not desc_match:
            continue
        if category in ("FUNCTION_NAME", "function_name"):
            method_name = contract.get("name", "")
            if not method_name or method_name == type_name:
                continue

            # Determine if async (common patterns)
            is_async = method_name.endswith("Async") or "async" in category.lower()
            kind = "async_method" if is_async else "method"

            params = []
            for p in contract.get("parameters", []):
                if isinstance(p, dict):
                    params.append({
                        "name": p.get("name", ""),
                        "annotation": p.get("type", None),
                    })
                elif isinstance(p, str):
                    params.append({"name": p, "annotation": None})

            return_type = contract.get("return_type")

            methods.append({
                "kind": kind,
                "name": method_name,
                "parent_class": type_name,
                "signature": {
                    "params": params,
                    "return_annotation": return_type,
                },
                "visibility": "public",
                "source_contract_id": contract.get("id"),
                "decomposition_source": "element_deriver_t2",
            })

    return methods


def _derive_framework_context(
    framework_imports: Dict[str, Any],
    description: str,
    language_id: str,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, str]]]:
    """Derive import specs and constructor DI params from framework detection.

    Returns:
        Tuple of (import_dicts, constructor_params).
    """
    import_dicts: List[Dict[str, Any]] = []
    constructor_params: List[Dict[str, str]] = []
    desc_lower = description.lower()

    # Framework detection: check if framework keywords appear in description
    for fw_id, fw_data in framework_imports.items():
        if not isinstance(fw_data, dict):
            continue

        keywords = fw_data.get("detect_keywords", [])
        if not any(kw.lower() in desc_lower for kw in keywords):
            continue

        # Add imports for this framework
        for imp in fw_data.get("imports", []):
            if isinstance(imp, str):
                import_dicts.append({
                    "kind": "import",
                    "module": imp,
                    "names": [],
                })

    # Language-specific DI patterns
    if language_id == "csharp":
        # Always inject ILogger<T> for service classes
        constructor_params.append({
            "name": "logger",
            "type": "ILogger<T>",
        })
        import_dicts.append({
            "kind": "import",
            "module": "Microsoft.Extensions.Logging",
            "names": [],
        })

    return import_dicts, constructor_params


def enrich_forward_manifest(
    manifest_dict: Dict[str, Any],
    tasks: List[Dict[str, Any]],
    framework_imports: Optional[Dict[str, Any]] = None,
) -> int:
    """Enrich ForwardManifest file_specs with derived elements (REQ-DFA-100).

    Iterates file_specs and calls ``derive_elements_for_file()`` for each
    non-Python file with empty elements. Idempotent — never overwrites
    existing elements.

    Args:
        manifest_dict: The ForwardManifest as a dict (mutated in place).
        tasks: Seed tasks (for feature descriptions and metadata).
        framework_imports: LanguageProfile framework_imports dict.

    Returns:
        Number of file_specs enriched.
    """
    file_specs = manifest_dict.get("file_specs", {})
    contracts = manifest_dict.get("contracts", [])
    if not isinstance(file_specs, dict):
        return 0

    # Build task_id → description mapping
    task_descriptions: Dict[str, str] = {}
    for task in tasks:
        tid = task.get("task_id", "")
        desc = task.get("config", {}).get("task_description", "")
        if tid and desc:
            task_descriptions[tid] = desc

    enriched_count = 0

    for file_path, spec in file_specs.items():
        if not isinstance(spec, dict):
            continue

        # Skip if elements already populated (idempotent — REQ-DFA-108)
        existing_elements = spec.get("elements", [])
        if existing_elements:
            continue

        ext = PurePosixPath(file_path).suffix.lower()
        if ext not in _SOURCE_EXTENSIONS:
            continue

        # Find description for this file from tasks
        description = ""
        for tid, desc in task_descriptions.items():
            # Heuristic: task description mentions the filename stem
            stem = PurePosixPath(file_path).stem
            if stem.lower() in desc.lower():
                description = desc
                break
        if not description:
            # Fall back to first task with matching target_files
            for task in tasks:
                tfiles = task.get("config", {}).get("context", {}).get("target_files", [])
                if file_path in tfiles:
                    description = task.get("config", {}).get("task_description", "")
                    break

        elements, imports = derive_elements_for_file(
            file_path,
            feature_description=description,
            contracts=contracts,
            framework_imports=framework_imports,
            language_id=_EXT_TO_LANG.get(ext, ""),
        )

        if elements:
            spec["elements"] = elements
            enriched_count += 1
        if imports and not spec.get("imports"):
            spec["imports"] = imports

    if enriched_count > 0:
        logger.info(
            "Element deriver: enriched %d/%d file_specs with derived elements",
            enriched_count, len(file_specs),
        )

    return enriched_count
