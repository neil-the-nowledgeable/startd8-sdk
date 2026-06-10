"""Extraction orchestrator (FR-WPI-1/2/4) — docs in, manifests + traceability out.

Ordering is a constraint (CRP R2): entities/relationships → simple manifests → views →
completeness. Every emitted manifest round-trips through its generator's own parser BEFORE
being returned (FR-WPI-4) — a failure raises :class:`RoundTripError` (a bug, never a flag).
"""

from __future__ import annotations

from typing import Dict, List, Mapping, Optional

import yaml

from ..backend_codegen.ai_layer import parse_ai_passes, parse_human_inputs
from ..backend_codegen.derived import load_completeness_manifest
from ..backend_codegen.pages_generator import parse_pages
from ..logging_config import get_logger
from ..scaffold_codegen.manifest import parse_app_manifest
from ..backend_codegen.forms_manifest import parse_forms
from ..view_codegen.manifest import parse_views
from .entities import EntityGraph, diff_against_live, extract_entities, extract_enums
from .extractors import (
    extract_ai_passes,
    extract_app,
    extract_completeness,
    extract_human_inputs,
    extract_pages,
    extract_views,
)
from .grammar import find_section, parse_sections
from .models import ExtractionRecord, ExtractionResult, RoundTripError

logger = get_logger(__name__)


def _emit_yaml(data: dict) -> str:
    return yaml.safe_dump(data, sort_keys=False, allow_unicode=True)


def _build_graph(
    docs: Mapping[str, str], records: List[ExtractionRecord]
) -> tuple:
    """Parse every doc → merged :class:`EntityGraph`, recording per-value traceability.

    The entities pass merges across docs (plan + requirements may split the catalog); later docs
    never silently override earlier entity blocks (``setdefault`` / dedup). Returns
    ``(graph, per_doc_sections)`` — the sections are reused by the manifest passes downstream.
    """
    graph = EntityGraph()
    per_doc_sections: List[tuple] = []

    # Pass 0 — named enums (FR-PE-8). Extracted across ALL docs BEFORE entities, so an
    # `enum: <Name>` field reference (FR-PE-9) can be validated against the declared set. Enums have
    # no reverse dependency on entities; later docs never override an earlier declaration.
    for label, text in docs.items():
        sections = parse_sections(text)
        per_doc_sections.append((label, text, sections))
        enums_root = find_section(sections, "Enums")
        if enums_root is not None:
            enum_blocks = [
                s for s in sections
                if s.level == enums_root.level + 1
                and len(s.heading_path) >= 2
                and s.heading_path[-2] == enums_root.title
            ]
            for name, values in extract_enums(label, enum_blocks, records).items():
                graph.enums.setdefault(name, values)

    known_enums = frozenset(graph.enums)
    for label, text, sections in per_doc_sections:
        entities_root = find_section(sections, "Entities")
        if entities_root is not None:
            blocks = [
                s for s in sections
                if s.level == entities_root.level + 1
                and len(s.heading_path) >= 2
                and s.heading_path[-2] == entities_root.title
            ]
            sub = extract_entities(label, blocks, records, known_enums=known_enums)
            for name, ent in sub.entities.items():
                graph.entities.setdefault(name, ent)
            for join in sub.joins:
                if graph.join_between(join.left, join.right) is None:
                    graph.joins.append(join)
            for child, parents in sub.fk_parents.items():
                dst = graph.fk_parents.setdefault(child, [])
                for p in parents:
                    if p not in dst:
                        dst.append(p)
            # FR-PE-5(b/c): these per-entity constructs were dropped here, so the CLI emit path
            # silently lost @@index / @@unique / loose-ref FKs (only direct extract_entities, used
            # by unit tests, saw them). Merge them like the rest — first declaration wins.
            for child, parents in sub.loose_refs.items():
                dst = graph.loose_refs.setdefault(child, [])
                for p in parents:
                    if p not in dst:
                        dst.append(p)
            for entity, specs in sub.indexes.items():
                graph.indexes.setdefault(entity, []).extend(specs)
            for entity, specs in sub.uniques.items():
                graph.uniques.setdefault(entity, []).extend(specs)
            for key, name in sub.reverse_names.items():     # FR-PE-13: custom reverse names
                graph.reverse_names.setdefault(key, name)
    return graph, per_doc_sections


def build_entity_graph(docs: Mapping[str, str]) -> EntityGraph:
    """Public doc(s) → :class:`EntityGraph` — the schema-emit input (FR-EMIT-1).

    Shared with :func:`extract_manifests` so the CLI emit path and the manifest path derive the
    graph identically. Traceability records are computed but discarded here; callers that need them
    (the report) go through :func:`extract_manifests`.
    """
    return _build_graph(docs, [])[0]


def extract_manifests(
    docs: Mapping[str, str],
    *,
    live_schema_text: Optional[str] = None,
) -> ExtractionResult:
    """Extract the assembly manifests from *docs* (label/path → markdown text).

    *live_schema_text* — when the project already has an authored contract, the entities pass
    runs in DIFF mode (FR-WPI-8): the doc-derived graph is compared, never emitted.
    """
    import hashlib

    result = ExtractionResult()
    records: List[ExtractionRecord] = result.records
    # FR-WPI-7: the report carries the kickoff-doc checksums, so downstream consumers (the
    # wireframe's run_linkage) never need to read the seed (no-seed-coupling non-requirement).
    result.source_docs = {
        label: hashlib.sha256(text.encode("utf-8")).hexdigest() for label, text in docs.items()
    }

    # One section index per doc; the entities pass merges across docs (plan + requirements
    # may split the catalog), later docs never silently override earlier entity blocks.
    graph, per_doc_sections = _build_graph(docs, records)

    if live_schema_text:
        result.contract_diff = diff_against_live(graph, live_schema_text)

    candidates: Dict[str, Optional[dict]] = {}
    for label, text, sections in per_doc_sections:
        if "pages.yaml" not in candidates or candidates["pages.yaml"] is None:
            candidates["pages.yaml"] = extract_pages(label, sections, records)
        if "app.yaml" not in candidates or candidates["app.yaml"] is None:
            candidates["app.yaml"] = extract_app(label, sections, records)
        if "ai_passes.yaml" not in candidates or candidates["ai_passes.yaml"] is None:
            candidates["ai_passes.yaml"] = extract_ai_passes(label, sections, graph, records)
        if "human_inputs.yaml" not in candidates or candidates["human_inputs.yaml"] is None:
            candidates["human_inputs.yaml"] = extract_human_inputs(label, text, graph, records)
        if "views.yaml" not in candidates or candidates["views.yaml"] is None:
            candidates["views.yaml"] = extract_views(label, sections, graph, records)
        if "completeness.yaml" not in candidates or candidates["completeness.yaml"] is None:
            candidates["completeness.yaml"] = extract_completeness(label, sections, graph, records)

    # FR-WPI-4: round-trip through the generators' OWN parsers before returning.
    known = frozenset(graph.all_model_names())
    round_trips = {
        "pages.yaml": lambda t: parse_pages(t),
        "app.yaml": lambda t: parse_app_manifest(t),
        "ai_passes.yaml": lambda t: parse_ai_passes(t),
        "human_inputs.yaml": lambda t: parse_human_inputs(t),
        # Both strict parsers over views.yaml's disjoint sections: composite views (`views:`)
        # AND per-entity post-create behavior (`forms:`, FORM_SUBMIT_BEHAVIOR FR-4) — a bad
        # forms: section fails the gate at ingestion, not at `generate backend` time.
        "views.yaml": lambda t: (
            parse_views(t, known_entities=known),
            parse_forms(t, known_entities=known),
        ),
        "completeness.yaml": lambda t: _check_completeness(t),
    }
    for filename, data in candidates.items():
        if data is None:
            continue
        text = _emit_yaml(data)
        try:
            round_trips[filename](text)
        except Exception as exc:
            logger.error("manifest extraction round-trip failed for %s", filename, exc_info=True)
            raise RoundTripError(
                f"{filename}: emitted manifest failed its generator parser — extraction bug: {exc}"
            ) from exc
        result.manifests[filename] = text
    return result


def _check_completeness(text: str) -> dict:
    data = load_completeness_manifest(text)
    if data is None:
        raise ValueError("completeness.yaml did not load as a mapping")
    return data
