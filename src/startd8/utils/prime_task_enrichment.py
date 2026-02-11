"""
Prime Task Enrichment — Target file extraction from task descriptions
and YAML enrichment via DomainChecklist.

Provides:
- extract_target_files(): Parse file paths from structured task descriptions
- enrich_prime_yaml(): Batch-enrich a prime YAML with domain constraints
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

from ..logging_config import get_logger

logger = get_logger(__name__)


# ============================================================================
# TARGET FILE EXTRACTION
# ============================================================================

# Priority-ordered regex patterns for extracting target file paths from
# task descriptions.  Each pattern targets a specific description format
# used by PlanIngestionWorkflow output.

_TARGET_FILE_PATTERNS = [
    # Tier 1: Code tasks (PI-001..PI-004)
    re.compile(r"Implementation file:\s*(.+\.py)\b"),
    # Tier 2: Config tasks (PI-005)
    re.compile(r"Export as:\s*(.+\.\w+)\b"),
    # Tier 3: Enhancement tasks
    re.compile(r"(?:Update|Modify) file:\s*(.+\.py)\b"),
    # Tier 4: Doc tasks (PI-006, PI-009)
    re.compile(r"Deliverable:\s*(.+\.\w+)\b"),
    re.compile(r"(?:^|(?<=\n))File:\s*(.+\.\w+)\b"),
    # Tier 5: Fallback patterns for inline references
    re.compile(r"Enhancements for (.+\.py)\b"),
    re.compile(r"Add .+ to (.+\.py)\b"),
    re.compile(r"Update (?!file:)(\S+\.py)\b"),
]


def extract_target_files(description: str) -> List[str]:
    """Parse file paths from a task description.

    Uses priority-ordered regex patterns to extract target file paths.
    Returns the primary target first; subsequent matches are appended
    in discovery order.

    Args:
        description: The task description string to parse.

    Returns:
        List of matched file path strings (may be empty).
    """
    found: List[str] = []
    seen: set = set()

    for pattern in _TARGET_FILE_PATTERNS:
        for match in pattern.finditer(description):
            path_str = match.group(1).strip()
            if path_str not in seen:
                seen.add(path_str)
                found.append(path_str)

    return found


# ============================================================================
# YAML ENRICHMENT
# ============================================================================


@dataclass
class EnrichmentReport:
    """Summary of a batch enrichment run."""

    total_tasks: int = 0
    enriched: int = 0
    skipped: int = 0
    failed: int = 0
    errors: List[str] = field(default_factory=list)


def enrich_prime_yaml(
    input_path: Path,
    project_root: Path,
    output_path: Path,
) -> EnrichmentReport:
    """Load a prime YAML, enrich tasks with domain constraints, and write output.

    For each task the function:
    1. Extracts target files from the task description
    2. Calls DomainChecklist.get_enrichment() for the primary target
    3. Attaches an ``_enrichment`` block to the task dict
    4. Populates ``config.context.target_files`` if absent

    The enriched YAML is written atomically (write to tmp then rename).

    Args:
        input_path: Path to the source prime YAML.
        project_root: Project root for DomainChecklist inline computation.
        output_path: Destination for the enriched YAML.

    Returns:
        EnrichmentReport with counts.
    """
    import yaml

    from ..contractors.artisan_phases.domain_checklist import DomainChecklist

    report = EnrichmentReport()

    data = yaml.safe_load(input_path.read_text(encoding="utf-8"))
    tasks = data.get("tasks", [])
    report.total_tasks = len(tasks)

    checklist = DomainChecklist(project_root=project_root)

    for task in tasks:
        task_id = task.get("task_id", task.get("id", ""))
        config = task.get("config", {})
        description = config.get("task_description", task.get("title", ""))

        targets = extract_target_files(description)
        if not targets:
            report.skipped += 1
            logger.debug("No target files found for task %s", task_id)
            continue

        # Populate target_files in context if absent
        context = config.setdefault("context", {})
        if not context.get("target_files"):
            context["target_files"] = targets

        try:
            enrichment = checklist.get_enrichment(task_id, targets)
        except Exception as exc:
            report.failed += 1
            msg = f"Enrichment failed for {task_id}: {exc}"
            report.errors.append(msg)
            logger.warning(msg)
            continue

        if enrichment is None:
            report.skipped += 1
            logger.debug("No enrichment available for task %s", task_id)
            continue

        task["_enrichment"] = enrichment.to_dict()
        report.enriched += 1
        logger.info(
            "Enriched task %s: domain=%s, constraints=%d",
            task_id,
            enrichment.domain.value,
            len(enrichment.prompt_constraints),
        )

    # Atomic write
    tmp_path = output_path.with_suffix(".tmp")
    tmp_path.write_text(yaml.dump(data, default_flow_style=False, sort_keys=False), encoding="utf-8")
    tmp_path.rename(output_path)

    logger.info(
        "Enrichment complete: %d/%d enriched, %d skipped, %d failed",
        report.enriched,
        report.total_tasks,
        report.skipped,
        report.failed,
    )
    return report
