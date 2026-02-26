"""
Code Review Skill with Call Graph Context (Phase 6, CG-CR-1..CG-CR-5).

This module provides a structured code review helper that surfaces ManifestRegistry
call graph data to the reviewer LLM, enabling impact-proportional review focus.
"""

from __future__ import annotations

from typing import Any, Optional

from startd8.logging_config import get_logger

logger = get_logger(__name__)


def build_call_graph_review_context(
    file_paths: list[str],
    registry: Any,  # ManifestRegistry | None
    budget_chars: int = 3000,
) -> str:
    """Build a '## Call Graph Context' section for use in a code review prompt.

    CG-CR-1: Accepts an optional manifest_registry. When provided, loads call
    graph data for the reviewed files using callers_of() and blast_radius().

    CG-CR-5: When registry is None or elements lack call graph data, returns
    empty string (graceful degradation — reviewer operates without call graph).

    Args:
        file_paths: Relative paths of files being reviewed.
        registry: ManifestRegistry instance or None.
        budget_chars: Maximum character budget for the section.

    Returns:
        Formatted '## Call Graph Context' section string, or '' when no data.
    """
    if registry is None:
        return ""

    try:
        from startd8.utils.manifest_registry import _flatten_elements

        all_entries: list[dict[str, Any]] = []
        dead_fqns: set[str] = set()
        dynamic_fqns: set[str] = set()

        try:
            dead_fqns = set(registry.dead_candidates())
        except Exception:
            pass

        for file_path in file_paths:
            manifest = registry.get(file_path)
            if manifest is None:
                continue

            elements = _flatten_elements(manifest.elements)
            reverse = registry.reverse_call_graph()
            forward = registry.call_graph()

            for elem in elements:
                if not elem.fqn:
                    continue
                callers = list(registry.callers_of(elem.fqn))
                blast = registry.blast_radius(elem.fqn, max_depth=3)
                has_dynamic = (
                    elem.call_graph is not None
                    and getattr(elem.call_graph, "has_dynamic_dispatch", False)
                )
                if has_dynamic:
                    dynamic_fqns.add(elem.fqn)

                all_entries.append({
                    "fqn": elem.fqn,
                    "file": file_path,
                    "direct_callers": len(callers),
                    "blast_radius": len(blast),
                    "is_dead": elem.fqn in dead_fqns,
                    "has_dynamic": has_dynamic,
                })

        if not all_entries:
            return ""

        parts: list[str] = []
        used = 0

        # CG-CR-2: Impact-proportional table header
        table_header = (
            "\n## Call Graph Context\n\n"
            "Apply review scrutiny proportional to blast radius. "
            "Functions with radius > 10 carry higher refactoring risk.\n\n"
            "| Function | Direct Callers | Blast Radius (depth=3) |\n"
            "|----------|---------------|------------------------|\n"
        )
        parts.append(table_header)
        used += len(table_header)

        # Sort by blast radius descending for truncation priority
        all_entries.sort(key=lambda e: e["blast_radius"], reverse=True)

        for entry in all_entries:
            short_name = entry["fqn"].split(".")[-1]
            row = f"| {short_name}() | {entry['direct_callers']} | {entry['blast_radius']} |\n"
            if used + len(row) > budget_chars:
                parts.append(f"| ... | ({len(all_entries)} total functions) | |\n")
                break
            parts.append(row)
            used += len(row)

        # CG-CR-3: Dead code candidates
        dead_in_review = [e["fqn"] for e in all_entries if e["is_dead"]]
        if dead_in_review:
            dead_section = (
                "\n### 🔍 Dead Code Candidates\n"
                "The following functions have no known callers. "
                "Verify they are intentionally public:\n"
                + "".join(f"- `{fqn}` — 0 callers, no references found\n" for fqn in dead_in_review[:10])
            )
            if used + len(dead_section) <= budget_chars:
                parts.append(dead_section)
                used += len(dead_section)

        # CG-CR-4: Dynamic dispatch warnings
        dynamic_in_review = [e["fqn"] for e in all_entries if e["has_dynamic"]]
        if dynamic_in_review:
            dyn_section = (
                "\n### ⚠ Dynamic Dispatch Warning\n"
                + "".join(
                    f"`{fqn}` uses `getattr()` / dynamic dispatch. "
                    "The call graph is a lower bound — additional runtime calls "
                    "may not be captured. Manual review of dynamic call targets is needed.\n"
                    for fqn in dynamic_in_review[:5]
                )
            )
            if used + len(dyn_section) <= budget_chars:
                parts.append(dyn_section)

        return "".join(parts)

    except Exception as exc:
        logger.debug("build_call_graph_review_context failed: %s", exc)
        return ""


def enrich_review_prompt_with_call_graph(
    prompt: str,
    file_paths: list[str],
    registry: Any,
    budget_chars: int = 3000,
    *,
    insertion_marker: str = "## Review Instructions",
) -> str:
    """Inject call graph context into an existing review prompt string.

    Inserts the '## Call Graph Context' section before *insertion_marker*.
    If the marker is not found, appends the section at the end.

    CG-CR-5: When registry is None or produces no data, the prompt is returned
    unchanged (graceful degradation).

    Args:
        prompt: The base review prompt string.
        file_paths: Relative paths of files being reviewed.
        registry: ManifestRegistry instance or None.
        budget_chars: Maximum character budget for the injected section.
        insertion_marker: Heading to insert before (default: '## Review Instructions').

    Returns:
        Modified prompt string, or the original prompt if no data to inject.
    """
    cg_section = build_call_graph_review_context(file_paths, registry, budget_chars)
    if not cg_section:
        return prompt

    if insertion_marker in prompt:
        return prompt.replace(insertion_marker, cg_section + "\n" + insertion_marker)

    logger.debug(
        "enrich_review_prompt_with_call_graph: insertion marker '%s' not found — appending",
        insertion_marker,
    )
    return prompt + "\n" + cg_section
