"""Plan ingestion Mottainai pre-assembly helpers (FR-MPA-001 through FR-MPA-011).

Extracted from plan_ingestion_workflow.py (AC-R2) to reduce file size.
All symbols are re-exported from plan_ingestion_workflow.py for backward compatibility.
"""

from __future__ import annotations

import ast
import re
from hashlib import sha256
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, Optional

from ...logging_config import get_logger

if TYPE_CHECKING:
    from startd8.forward_manifest import ForwardElementSpec, ForwardManifest, InterfaceContract

logger = get_logger(__name__)

# FR-MPA-008: Pre-assembly OTel metrics (optional dependency)
try:
    from opentelemetry import metrics as _otel_metrics
    _mpa_meter = _otel_metrics.get_meter("startd8.mottainai")
    _mpa_elements_classified = _mpa_meter.create_counter(
        "mottainai.elements_classified",
        description="Elements classified at ingestion time",
    )
    _mpa_elements_pre_filled = _mpa_meter.create_counter(
        "mottainai.elements_pre_filled",
        description="Elements filled without LLM (template or registry)",
    )
    _mpa_registry_hits = _mpa_meter.create_counter(
        "mottainai.registry_hits",
        description="Cross-run element reuse hits at ingestion",
    )
    _mpa_registry_misses = _mpa_meter.create_counter(
        "mottainai.registry_misses",
        description="Cross-run element reuse misses at ingestion",
    )
except ImportError:
    _mpa_elements_classified = None
    _mpa_elements_pre_filled = None
    _mpa_registry_hits = None
    _mpa_registry_misses = None

# Observability manifest descriptor — consumed by generate_manifest(), zero runtime
# cost. Declares the FULL mottainai.* meter family: the 4 emitters created here PLUS
# `mottainai.skeleton_sources_forwarded` (context_seed/phases/scaffold.py) and
# `mottainai.implement_prompt_narrowed`/`mottainai.tokens_avoided_estimate`
# (contractors/artisan_phases/development.py). All share the `startd8.mottainai`
# meter; declaring them in one carrier module keeps a single collector registration
# while the parity scanner still verifies every emission site. Module-level taxonomy
# defaults (REQ-OBS-SHARED-001): pre-assembly (Mottainai) metrics are innate
# codegen-pipeline mechanics, system-oriented.
_OTEL_DESCRIPTORS = {
    "category": "pipeline_innate",
    "orientation": "system",
    "metrics": [
        {
            "name": "mottainai.elements_classified",
            "instrument": "counter",
            "unit": "1",
            "description": "Elements classified at ingestion time",
            "meter": "startd8.mottainai",
            "labels": ["tier", "phase"],
        },
        {
            "name": "mottainai.elements_pre_filled",
            "instrument": "counter",
            "unit": "1",
            "description": "Elements filled without LLM (template or registry)",
            "meter": "startd8.mottainai",
            "labels": ["phase"],
        },
        {
            "name": "mottainai.registry_hits",
            "instrument": "counter",
            "unit": "1",
            "description": "Cross-run element reuse hits at ingestion",
            "meter": "startd8.mottainai",
            "labels": ["phase"],
        },
        {
            "name": "mottainai.registry_misses",
            "instrument": "counter",
            "unit": "1",
            "description": "Cross-run element reuse misses at ingestion",
            "meter": "startd8.mottainai",
            "labels": ["phase"],
        },
        {
            "name": "mottainai.skeleton_sources_forwarded",
            "instrument": "counter",
            "unit": "1",
            "description": "Skeletons consumed from seed (vs. recomputed)",
            "meter": "startd8.mottainai",
            "labels": ["phase"],
        },
        {
            "name": "mottainai.implement_prompt_narrowed",
            "instrument": "counter",
            "unit": "1",
            "description": "Tasks receiving edit-mode prompts from pre-assembly",
            "meter": "startd8.mottainai",
            "labels": ["phase"],
        },
        {
            "name": "mottainai.tokens_avoided_estimate",
            "instrument": "counter",
            "unit": "tokens",
            "description": "Estimated input+output tokens saved by pre-assembly",
            "meter": "startd8.mottainai",
            "labels": ["phase"],
        },
    ],
}


def _element_context_checksum(
    element: ForwardElementSpec,
    contracts: list[InterfaceContract],
) -> str:
    """Hash an element's structural context for staleness detection (FR-MPA-011).

    Changes to signature, bases, decorators, or applicable contracts
    invalidate any cached code in the ElementRegistry.

    Args:
        element: ForwardElementSpec with name, kind, signature, bases, decorators.
        contracts: Applicable InterfaceContract list from the ForwardManifest.

    Returns:
        SHA-256 hex digest of the concatenated structural fields.
    """
    parts = [
        getattr(element, "name", ""),
        getattr(element, "kind", ""),
    ]
    sig = getattr(element, "signature", None)
    parts.append(str(sig) if sig else "")
    parts.append(getattr(element, "parent_class", None) or "")
    bases = getattr(element, "bases", None) or []
    parts.append(",".join(sorted(str(b) for b in bases)))
    decorators = getattr(element, "decorators", None) or []
    parts.append(",".join(sorted(str(d) for d in decorators)))
    # Include checksums from contracts applicable to this element
    elem_name = getattr(element, "name", "")
    parent_cls = getattr(element, "parent_class", None)
    for c in contracts:
        fn = getattr(c, "function_name", None)
        cn = getattr(c, "class_name", None)
        if fn == elem_name or (cn is not None and cn == parent_cls):
            c_id = getattr(c, "contract_id", "")
            parts.append(str(c_id))
    return sha256("|".join(parts).encode()).hexdigest()


def _mottainai_pre_assembly(
    forward_manifest: ForwardManifest,
    skeleton_sources: Optional[Dict[str, str]],
    output_dir: Path,
) -> Dict[str, Dict[str, Any]]:
    """Run element registry population, classification, and template pre-fill.

    Performs FR-MPA-009 (registry population), FR-MPA-010 (cross-run lookup),
    FR-MPA-011 (context checksums), FR-MPA-002 (classification), and
    FR-MPA-003 (template matching) in a single pass over all elements.

    Args:
        forward_manifest: Deserialized ForwardManifest with file_specs and contracts.
        skeleton_sources: Pre-rendered skeleton source texts keyed by file path,
            or ``None`` if DFA rendering was skipped.
        output_dir: Pipeline output directory; used to locate the ElementRegistry
            state store at ``output_dir / ".startd8" / "state"``.

    Returns:
        Element tier map: ``{file_path: {qualified_name: tier_info_dict}}``.
    """
    element_tiers: Dict[str, Dict[str, Any]] = {}

    if not hasattr(forward_manifest, "file_specs") or not forward_manifest.file_specs:
        return element_tiers

    # Lazy imports — these modules are always available in the SDK but
    # importing at module level would create circular dependencies.
    try:
        from startd8.element_id import make_element_id
        from startd8.element_registry import (
            ElementEntry,
            ElementRegistry,
            compute_element_context_checksum,
        )
        from startd8.complexity.classifier import classify_tier
        from startd8.complexity.signals import extract_signals_from_element
    except ImportError:
        logger.debug("Pre-assembly imports unavailable — skipping")
        return element_tiers

    # FR-MPA-009a: Initialize element registry (shared per-project store)
    registry: Optional[ElementRegistry] = None
    state_dir = output_dir / ".startd8" / "state"
    try:
        registry = ElementRegistry(state_dir=state_dir)
    except (OSError, ValueError) as exc:
        logger.warning(
            "EMIT: ElementRegistry init failed (%s) — pre-assembly continues without registry",
            exc,
        )

    # FR-MPA-009b: Build manifest element index (O(1) lookups)
    try:
        forward_manifest.get_element_by_id("")  # triggers lazy index build
    except (AttributeError, TypeError, ValueError):
        logger.debug("EMIT: manifest element index build skipped (advisory)")

    contracts = getattr(forward_manifest, "contracts", None) or []

    registry_hits = 0
    registry_misses = 0
    elements_classified = 0
    template_fills = 0

    # Hoist TemplateRegistry outside the element loop (FR-MPA-003)
    tmpl_registry = None
    try:
        from startd8.micro_prime.templates import TemplateRegistry
        tmpl_registry = TemplateRegistry()
    except ImportError:
        pass

    for file_path, file_spec in forward_manifest.file_specs.items():
        file_tiers: Dict[str, Any] = {}
        elements = getattr(file_spec, "elements", None) or []

        for element in elements:
            elem_name = getattr(element, "name", "")
            parent_cls = getattr(element, "parent_class", None)
            kind_val = getattr(element, "kind", "")
            kind_str = kind_val.value if hasattr(kind_val, "value") else str(kind_val)

            # Qualified name for the tier map
            qualified = f"{parent_cls}.{elem_name}" if parent_cls else elem_name

            # FR-MPA-011: Compute context checksum via shared function
            # (ensures EMIT and IMPLEMENT produce identical checksums)
            elem_sig = getattr(element, "signature", None)
            elem_bases = [str(b) for b in (getattr(element, "bases", None) or [])]
            elem_decs = [str(d) for d in (getattr(element, "decorators", None) or [])]
            elem_contract_ids = []
            elem_name_local = getattr(element, "name", "")
            parent_cls_local = getattr(element, "parent_class", None)
            for c in contracts:
                fn = getattr(c, "function_name", None)
                cn = getattr(c, "class_name", None)
                if fn == elem_name_local or (cn is not None and cn == parent_cls_local):
                    elem_contract_ids.append(str(getattr(c, "contract_id", "")))
            ctx_checksum = compute_element_context_checksum(
                element_name=elem_name_local,
                element_kind=kind_str,
                signature=str(elem_sig) if elem_sig else "",
                parent_class=parent_cls or "",
                contract_checksums=elem_contract_ids or None,
                bases=elem_bases or None,
                decorators=elem_decs or None,
            )

            # Generate deterministic element ID
            element_id = getattr(element, "source_contract_id", None) or ""
            if not element_id:
                try:
                    element_id = make_element_id(
                        kind=kind_str,
                        name=elem_name,
                        file_path=file_path,
                        parent_class=parent_cls,
                    )
                except (ValueError, TypeError):
                    element_id = f"{kind_str}/{file_path}:{elem_name}"

            # FR-MPA-009a: Populate registry with element spec
            fill_source = "none"
            if registry is not None:
                try:
                    existing = registry.get(element_id)
                    if existing is None:
                        # New element — register as "specified"
                        entry = ElementEntry(
                            element_id=element_id,
                            kind=kind_str,
                            name=elem_name,
                            file_path=file_path,
                            parent_class=parent_cls,
                            source_contract_id=element_id,
                            context_checksum=ctx_checksum,
                        )
                        registry.put(entry)
                        registry.set_phase_status(
                            element_id, "plan_ingestion", "specified",
                        )
                        registry_misses += 1
                    else:
                        # FR-MPA-010a: Cross-run lookup — check staleness
                        if (
                            existing.context_checksum
                            and existing.context_checksum == ctx_checksum
                            and existing.extra.get("code")
                        ):
                            # Valid cache hit — code from prior run is compatible
                            fill_source = f"registry:{existing.extra.get('source_task', '?')}"
                            registry_hits += 1
                        elif existing.extra.get("code"):
                            # Stale — signature or contracts changed
                            logger.info(
                                "EMIT: element %s checksum stale — invalidating cached code",
                                element_id,
                            )
                            # Update entry with new checksum, clear cached code
                            existing.context_checksum = ctx_checksum
                            existing.extra.pop("code", None)
                            registry.put(existing)
                            registry.set_phase_status(
                                element_id, "plan_ingestion", "invalidated",
                            )
                            registry_misses += 1
                        else:
                            # Entry exists but has no code — update checksum
                            existing.context_checksum = ctx_checksum
                            registry.put(existing)
                            registry_misses += 1
                except (OSError, ValueError, RuntimeError) as exc:
                    logger.debug(
                        "EMIT: registry operation failed for %s: %s",
                        element_id, exc,
                    )
                    registry_misses += 1

            # FR-MPA-002: Per-element complexity classification
            tier_str = "MODERATE"  # safe default
            tier_reason = ""
            try:
                signals = extract_signals_from_element(
                    element, file_spec, contracts,
                )
                tier, tier_reason = classify_tier(signals)
                tier_str = tier.value
                elements_classified += 1
            except Exception as exc:
                logger.debug(
                    "EMIT: element classification failed for %s: %s",
                    qualified, exc,
                )

            # FR-MPA-003: Template matching for TRIVIAL elements
            # (only if not already filled by registry)
            template_name: Optional[str] = None
            if fill_source == "none" and tier_str == "TRIVIAL" and tmpl_registry is not None:
                try:
                    match = tmpl_registry.match(element, file_spec, contracts)
                    if match is not None:
                        template_name = match.name
                        fill_source = f"template:{template_name}"
                        template_fills += 1
                except Exception as exc:
                    logger.debug(
                        "EMIT: template match failed for %s: %s",
                        qualified, exc,
                    )

            tier_info: Dict[str, Any] = {
                "tier": tier_str,
                "element_id": element_id,
                "context_checksum": ctx_checksum,
            }
            if fill_source != "none":
                tier_info["pre_filled"] = True
                tier_info["fill_source"] = fill_source
            if template_name:
                tier_info["template"] = template_name

            file_tiers[qualified] = tier_info

        if file_tiers:
            element_tiers[file_path] = file_tiers

    # Summary logging
    total_elements = sum(len(ft) for ft in element_tiers.values())
    pre_filled = registry_hits + template_fills
    logger.info(
        "EMIT: pre-assembly classified %d elements (%d pre-filled: "
        "%d registry hits, %d template fills, %d registry misses)",
        total_elements, pre_filled, registry_hits, template_fills,
        registry_misses,
    )

    # FR-MPA-008: Emit OTel metrics
    if _mpa_elements_classified is not None:
        # Per-tier classification counts
        tier_counts: Dict[str, int] = {}
        for ft in element_tiers.values():
            for info in ft.values():
                t = info.get("tier", "UNKNOWN")
                tier_counts[t] = tier_counts.get(t, 0) + 1
        for tier_name, count in tier_counts.items():
            _mpa_elements_classified.add(count, {"tier": tier_name, "phase": "ingestion"})
    if _mpa_elements_pre_filled is not None:
        if template_fills:
            _mpa_elements_pre_filled.add(
                template_fills, {"fill_source": "template", "phase": "ingestion"},
            )
        if registry_hits:
            _mpa_elements_pre_filled.add(
                registry_hits, {"fill_source": "registry", "phase": "ingestion"},
            )
    if _mpa_registry_hits is not None and registry_hits:
        _mpa_registry_hits.add(registry_hits, {"phase": "ingestion"})
    if _mpa_registry_misses is not None and registry_misses:
        _mpa_registry_misses.add(registry_misses, {"phase": "ingestion"})

    return element_tiers


def _apply_pre_fill_to_skeletons(
    skeleton_sources: Dict[str, str],
    element_tiers: Dict[str, Dict[str, Any]],
    forward_manifest: ForwardManifest,
) -> Dict[str, str]:
    """Replace ``raise NotImplementedError`` stubs with pre-filled bodies.

    For elements marked as pre-filled (template or registry), splice the
    generated body into the skeleton source text.  Re-validates via
    ``ast.parse()`` after each file modification; reverts on failure.

    Args:
        skeleton_sources: File path → Python source text mapping from DFA.
        element_tiers: Per-file element tier map from ``_mottainai_pre_assembly``.
        forward_manifest: ForwardManifest for element lookup during template rendering.

    Returns:
        Updated skeleton_sources dict (shallow copy; originals are not mutated).
    """
    updated = dict(skeleton_sources)
    files_modified = 0

    for file_path, file_tiers in element_tiers.items():
        source = updated.get(file_path)
        if source is None:
            continue

        modified = False
        working = source

        for qualified, tier_info in file_tiers.items():
            if not tier_info.get("pre_filled"):
                continue

            fill_source = tier_info.get("fill_source", "")

            # Get the template-rendered body for template fills
            rendered_body: Optional[str] = None
            if fill_source.startswith("template:"):
                try:
                    from startd8.micro_prime.templates import TemplateRegistry

                    # Locate the element in the manifest
                    elem_name = qualified.split(".")[-1]
                    parent_cls = qualified.split(".")[0] if "." in qualified else None
                    file_spec = forward_manifest.file_specs.get(file_path)
                    if file_spec is None:
                        continue
                    target_elem = None
                    for elem in file_spec.elements:
                        if elem.name == elem_name and getattr(elem, "parent_class", None) == parent_cls:
                            target_elem = elem
                            break
                    if target_elem is None:
                        continue

                    contracts = getattr(forward_manifest, "contracts", None) or []
                    tmpl_registry = TemplateRegistry()
                    match = tmpl_registry.match(target_elem, file_spec, contracts)
                    if match is not None:
                        rendered_body = match.render_fn(target_elem, file_spec, contracts)
                except Exception as exc:
                    logger.debug(
                        "EMIT: template render failed for %s in %s: %s",
                        qualified, file_path, exc,
                    )
                    continue

            elif fill_source.startswith("registry:"):
                # TODO: Extract cached code from registry entry
                # This will be wired when ElementEntry.extra["code"] is populated
                # by the IMPLEMENT phase (ER-007).
                continue

            if rendered_body is None:
                continue

            # Splice: replace "raise NotImplementedError" with rendered body
            # Find the stub for this element and replace it
            elem_name = qualified.split(".")[-1]

            # Pattern: match "raise NotImplementedError" following a def/async def line
            # for this element name.  The stub is always on the line after the def.
            lines = working.split("\n")
            new_lines = []
            i = 0
            replaced = False
            while i < len(lines):
                line = lines[i]
                stripped = line.lstrip()

                # Check if this is a def line for our element
                if not replaced and (
                    stripped.startswith(f"def {elem_name}(")
                    or stripped.startswith(f"async def {elem_name}(")
                ):
                    # Found the def line — emit it
                    new_lines.append(line)
                    i += 1

                    # Skip docstring if present
                    while i < len(lines):
                        next_stripped = lines[i].lstrip()
                        if next_stripped.startswith('"""') or next_stripped.startswith("'''"):
                            # Emit docstring lines
                            quote = next_stripped[:3]
                            new_lines.append(lines[i])
                            # Check if single-line docstring
                            if next_stripped.count(quote) >= 2 and len(next_stripped) > 3:
                                i += 1
                                break
                            i += 1
                            # Multi-line docstring — find closing quotes
                            while i < len(lines):
                                new_lines.append(lines[i])
                                if quote in lines[i].lstrip():
                                    i += 1
                                    break
                                i += 1
                            break
                        else:
                            break

                    # Now check for raise NotImplementedError
                    if i < len(lines) and lines[i].lstrip() == "raise NotImplementedError":
                        # Determine indentation from the stub line
                        indent = lines[i][: len(lines[i]) - len(lines[i].lstrip())]
                        # Replace with rendered body (re-indent each line)
                        for body_line in rendered_body.split("\n"):
                            if body_line.strip():
                                new_lines.append(f"{indent}{body_line}")
                            else:
                                new_lines.append("")
                        replaced = True
                        i += 1  # skip the raise line
                    else:
                        # No stub found — don't modify
                        continue
                else:
                    new_lines.append(line)
                    i += 1

            if replaced:
                candidate = "\n".join(new_lines)
                # Validate AST before accepting
                try:
                    ast.parse(candidate, filename=file_path)
                    working = candidate
                    modified = True
                except SyntaxError as syn_err:
                    logger.debug(
                        "EMIT: pre-fill AST validation failed for %s in %s: %s — reverting",
                        qualified, file_path, syn_err,
                    )

        if modified:
            updated[file_path] = working
            files_modified += 1

    if files_modified:
        logger.info(
            "EMIT: pre-filled template bodies in %d skeleton file(s)", files_modified,
        )

    return updated
