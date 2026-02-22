#!/usr/bin/env python3
"""
Dump fully-assembled IMPLEMENT-phase prompts to disk for inspection.

Exercises the real prompt-assembly code paths (task description, generation
context, spec prompt, draft prompt, edit-mode classification) without making
any LLM calls.  Useful for validating that PCA-600..604 edit-mode directives,
existing-file sections, and output-format selection look correct.

Accepts EITHER an enriched context seed (--seed) OR a raw plan file (--plan).
When a plan file is given, it is parsed with the deterministic heuristic parser
so no LLM tokens are spent.

Usage:
    # From enriched seed (preferred — contains enrichment metadata)
    python3 scripts/dump_edit_mode_prompts.py \\
        --seed out/artisan-context-seed-enriched.json \\
        --project-root .

    # From raw plan markdown (lightweight — heuristic parse, no enrichment)
    python3 scripts/dump_edit_mode_prompts.py \\
        --plan docs/plans/my-plan.md \\
        --project-root .

Output goes to .startd8/prompt-dumps/<timestamp>/.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# Ensure SDK is importable in dev mode
_src = str(Path(__file__).resolve().parent.parent / "src")
if _src not in sys.path:
    sys.path.insert(0, _src)

from startd8.contractors.context_seed_handlers import (
    EditModeClassification,
    ImplementPhaseHandler,
    PerFileMode,
    SeedTask,
    _load_enriched_seed,
    _parse_tasks,
)
from startd8.workflows.builtin.lead_contractor_workflow import (
    DRAFT_EDIT_PROMPT_TEMPLATE,
    DRAFT_PROMPT_TEMPLATE,
    LeadContractorWorkflow,
    _build_existing_files_section,
    _build_output_format,
)
from startd8.workflows.builtin.plan_ingestion_workflow import (
    _heuristic_parse_plan,
)
from startd8.workflows.builtin.plan_ingestion_models import ParsedFeature

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _features_to_seed_tasks(
    features: List[ParsedFeature],
    project_root: Path,
) -> List[SeedTask]:
    """Convert heuristic-parsed features into minimal SeedTask objects.

    Reads existing file content hashes from disk so that edit-mode
    classification has real Tier-1 signals to work with.
    """
    tasks: List[SeedTask] = []
    for feat in features:
        # Compute existing_content_hash if any target file exists on disk
        existing_hash: Optional[str] = None
        for tf in feat.target_files:
            full = project_root / tf
            if full.is_file():
                import hashlib
                try:
                    content = full.read_bytes()
                    existing_hash = hashlib.sha256(content).hexdigest()
                except OSError:
                    pass
                break  # One existing file is enough for Tier-1 signal

        task = SeedTask(
            task_id=feat.feature_id,
            title=feat.name,
            task_type="task",
            story_points=3,
            priority="medium",
            labels=feat.labels,
            depends_on=feat.dependencies,
            description=feat.description,
            target_files=feat.target_files,
            estimated_loc=feat.estimated_loc,
            feature_id=feat.feature_id,
            domain="unknown",
            domain_reasoning="",
            environment_checks=[],
            prompt_constraints=[],
            post_generation_validators=[],
            available_siblings=[],
            existing_content_hash=existing_hash,
            design_doc_sections=feat.design_doc_sections,
            artifact_types_addressed=feat.artifact_types_addressed,
            file_scope={},
        )
        tasks.append(task)
    return tasks


def _build_scaffold_from_disk(
    tasks: List[SeedTask],
    project_root: Path,
) -> Dict[str, Any]:
    """Build a minimal scaffold dict by probing the filesystem.

    Populates ``existing_target_files`` and ``staleness_classification``
    so that ``_classify_edit_mode`` has Tier-1 and Tier-2 signals.
    """
    existing_targets: List[str] = []
    staleness: Dict[str, str] = {}

    all_target_files: set[str] = set()
    for t in tasks:
        all_target_files.update(t.target_files)

    for fpath in sorted(all_target_files):
        full = project_root / fpath
        if full.is_file():
            existing_targets.append(fpath)
            # Simple freshness heuristic: modified in last 7 days = "fresh"
            try:
                mtime = full.stat().st_mtime
                age_days = (time.time() - mtime) / 86400
                staleness[fpath] = "fresh" if age_days < 7 else "stale"
            except OSError:
                staleness[fpath] = ""

    return {
        "existing_target_files": existing_targets,
        "staleness_classification": staleness,
    }


def _read_existing_files(
    target_files: List[str],
    project_root: Path,
    max_bytes: int = 120_000,
) -> Dict[str, str]:
    """Read existing file contents from disk (same as DevelopmentPhase does)."""
    result: Dict[str, str] = {}
    for fpath in target_files:
        full = project_root / fpath
        if full.is_file():
            try:
                content = full.read_text(encoding="utf-8")
                if len(content) > max_bytes:
                    content = content[:max_bytes] + f"\n\n# ... truncated ({len(content)} bytes total)"
                result[fpath] = content
            except (UnicodeDecodeError, OSError):
                pass
    return result


def _dump_task_prompts(
    task: SeedTask,
    scaffold: Dict[str, Any],
    project_root: Path,
    output_dir: Path,
) -> Dict[str, Any]:
    """Assemble and dump all prompts for a single task.

    Returns a summary dict for the task.
    """
    task_dir = output_dir / f"task-{task.task_id}"
    task_dir.mkdir(parents=True, exist_ok=True)

    # Step 1: Edit-mode classification
    design_mode_summary: Dict[str, str] = {}  # No design phase in dump mode
    edit_class = ImplementPhaseHandler._classify_edit_mode(
        task, scaffold, design_mode_summary,
    )
    edit_dict = edit_class.to_dict()

    (task_dir / "edit_mode.json").write_text(
        json.dumps(edit_dict, indent=2), encoding="utf-8",
    )

    # Step 2: Read existing files from disk
    existing_files = _read_existing_files(task.target_files, project_root)

    # Step 3: Build task description (mirrors DevelopmentPhase._build_task_description)
    td_parts: List[str] = []

    # Project identity
    td_parts.append("## Project Identity\n")
    td_parts.append(f"**Project:** {project_root.name}")
    td_parts.append(f"**Root:** `{project_root}`\n")
    td_parts.append("---\n")

    # Target files
    if task.target_files:
        td_parts.append("## Target Files\n")
        td_parts.append(
            "You MUST generate the following file(s). Focus on implementing "
            "the PRIMARY artifact — do NOT generate test code.\n"
        )
        for target in task.target_files:
            ext = target.rsplit(".", 1)[-1] if "." in target else ""
            fmt_hint = {
                "yaml": "Valid YAML configuration",
                "yml": "Valid YAML configuration",
                "json": "Valid JSON",
                "md": "Markdown document",
                "py": "Python module",
            }.get(ext, "")
            td_parts.append(f"- `{target}`" + (f" ({fmt_hint})" if fmt_hint else ""))
        td_parts.append("\n---\n")

    # Existing files (PCA-503)
    if existing_files:
        td_parts.append("## Existing Files\n")
        td_parts.append(
            "The following target files ALREADY EXIST in the project. "
            "Your output MUST preserve existing functionality and only "
            "add or modify what is specified in the design document.\n"
        )
        import uuid as _uuid
        for ef_path, ef_content in existing_files.items():
            _nonce = _uuid.uuid4().hex[:8]
            td_parts.append(f"\n### `{ef_path}` ({len(ef_content):,} bytes)")
            td_parts.append(f"```source-{_nonce}\n{ef_content}\n```")
        td_parts.append("\n---\n")

        td_parts.append("## Edit-First Directive\n")
        td_parts.append(
            "**CRITICAL:** The target files shown above already exist in the project. "
            "You MUST:\n"
            "1. PRESERVE all existing functions, classes, imports, and logic "
            "that are not explicitly being changed\n"
            "2. ADD or MODIFY only what the design document specifies\n"
            "3. NEVER remove existing code unless the design explicitly requires it\n"
            "4. MAINTAIN backward compatibility — existing callers must continue to work\n"
            "5. Keep existing docstrings, type hints, and error handling intact\n"
            "\nTreat this as an EDIT to production code, not a greenfield implementation. "
            "If the design document describes new functionality, integrate it alongside "
            "the existing code.\n"
        )
        # PCA-605b Change A: Quantitative line-count constraint
        _ef_total_lines = sum(
            len(content.splitlines())
            for content in existing_files.values()
        )
        _ef_min_lines = int(_ef_total_lines * 0.80)
        td_parts.append(
            f"\n**SIZE CONSTRAINT:** The existing file(s) total {_ef_total_lines} lines. "
            f"Your output MUST be AT LEAST {_ef_min_lines} lines (80% of original). "
            f"Outputs significantly shorter than the original will be REJECTED.\n"
        )
        td_parts.append("\n---\n")

    # Edit mode classification section (PCA-600)
    if edit_class.mode == "edit":
        td_parts.append("## Edit Mode Classification\n")
        td_parts.append(
            f"**Task mode:** EDIT (confidence: {edit_class.confidence})\n"
        )
        per_file = edit_class.per_file
        edit_files = [f for f, info in per_file.items() if info.mode == "edit"]
        create_files = [f for f, info in per_file.items() if info.mode == "create"]
        if edit_files:
            td_parts.append("**Files being EDITED:** " + ", ".join(f"`{f}`" for f in edit_files))
        if create_files:
            td_parts.append("**Files being CREATED:** " + ", ".join(f"`{f}`" for f in create_files))
        for fpath, info in per_file.items():
            if info.staleness:
                td_parts.append(f"- `{fpath}`: staleness={info.staleness}")
        if edit_class.signal_conflicts:
            td_parts.append("\n**Signal conflicts detected:**")
            for c in edit_class.signal_conflicts[:3]:
                td_parts.append(f"- {c}")
        # PCA-605b Change B: Quantitative constraint replaces passive warning
        td_parts.append(
            "\n**MINIMUM OUTPUT:** Your output must be AT LEAST 80% of the existing file size. "
            "Outputs that drop below this threshold will be REJECTED by automated guards. "
            "Do NOT rewrite from scratch — EDIT the existing code."
        )
        td_parts.append("\n---\n")

    # Task description body
    td_parts.append("## Task Description\n")
    td_parts.append(task.description)

    task_description = "\n".join(td_parts)
    (task_dir / "task_description.md").write_text(task_description, encoding="utf-8")

    # Step 4: Build generation context (mirrors DevelopmentPhase._build_generation_context)
    gen_ctx: Dict[str, Any] = {
        "task_id": task.task_id,
        "feature_id": task.feature_id,
        "domain": task.domain,
        "target_files": task.target_files,
        "estimated_loc": task.estimated_loc,
        "prompt_constraints": task.prompt_constraints,
        "environment_checks": task.environment_checks,
        "project_root": str(project_root),
    }
    if existing_files:
        gen_ctx["existing_files"] = {k: f"<{len(v):,} bytes>" for k, v in existing_files.items()}
    if edit_class.mode == "edit":
        gen_ctx["edit_mode"] = edit_dict

    (task_dir / "generation_context.json").write_text(
        json.dumps(gen_ctx, indent=2), encoding="utf-8",
    )

    # Step 5: Build output format (PCA-602)
    output_format = _build_output_format(
        target_files=task.target_files,
        existing_files=existing_files if existing_files else None,
    )
    (task_dir / "output_format.md").write_text(output_format, encoding="utf-8")

    # Step 6: Build spec prompt
    spec_ctx = dict(gen_ctx)
    # Remove non-serializable or large fields before _build_spec_prompt
    spec_ctx.pop("existing_files", None)
    spec_prompt = LeadContractorWorkflow._build_spec_prompt(
        task_description=task_description,
        context=spec_ctx,
        output_format=output_format,
    )
    (task_dir / "spec_prompt.md").write_text(spec_prompt, encoding="utf-8")

    # Step 7: Build draft prompt (with existing files section)
    # PCA-605: Select edit template when existing files are present
    existing_files_section = _build_existing_files_section(
        existing_files=existing_files if existing_files else None,
        edit_mode=edit_dict if edit_class.mode == "edit" else None,
    )
    draft_template = DRAFT_EDIT_PROMPT_TEMPLATE if existing_files else DRAFT_PROMPT_TEMPLATE
    draft_prompt = draft_template.format(
        spec="[SPEC WOULD BE LLM-GENERATED — showing template placeholder]",
        feedback="This is the initial implementation attempt.",
        output_format=output_format,
        existing_files_section=existing_files_section,
    )
    (task_dir / "draft_prompt.md").write_text(draft_prompt, encoding="utf-8")

    # Build summary for this task
    summary = {
        "task_id": task.task_id,
        "title": task.title,
        "target_files": task.target_files,
        "edit_mode": edit_class.mode,
        "edit_confidence": edit_class.confidence,
        "per_file_modes": {
            f: info.mode for f, info in edit_class.per_file.items()
        },
        "signal_conflicts": edit_class.signal_conflicts,
        "existing_file_count": len(existing_files),
        "existing_file_sizes": {k: len(v) for k, v in existing_files.items()},
        "prompt_sizes": {
            "task_description": len(task_description),
            "spec_prompt": len(spec_prompt),
            "draft_prompt": len(draft_prompt),
            "output_format": len(output_format),
            "existing_files_section": len(existing_files_section),
        },
    }
    return summary


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Dump fully-assembled IMPLEMENT-phase prompts without LLM calls.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python3 scripts/dump_edit_mode_prompts.py --seed out/enriched-seed.json\n"
            "  python3 scripts/dump_edit_mode_prompts.py --plan docs/plans/my-plan.md\n"
        ),
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument(
        "--seed",
        help="Path to enriched context seed JSON (from plan ingestion pipeline)",
    )
    source.add_argument(
        "--plan",
        help="Path to raw plan markdown (parsed with deterministic heuristic parser)",
    )
    parser.add_argument(
        "--project-root", default=".",
        help="Project root directory for reading existing files (default: .)",
    )
    parser.add_argument(
        "--output-dir",
        help="Override output directory (default: .startd8/prompt-dumps/<timestamp>)",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true",
        help="Enable debug logging",
    )
    args = parser.parse_args()

    # Logging
    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)-8s %(message)s",
        datefmt="%H:%M:%S",
    )

    project_root = Path(args.project_root).resolve()
    if not project_root.is_dir():
        print(f"ERROR: project-root is not a directory: {project_root}", file=sys.stderr)
        return 1

    # ── Parse tasks ──────────────────────────────────────────────────
    if args.seed:
        seed_path = Path(args.seed)
        if not seed_path.exists():
            print(f"ERROR: seed file not found: {seed_path}", file=sys.stderr)
            return 1
        logger.info("Loading enriched seed: %s", seed_path)
        seed_data = _load_enriched_seed(str(seed_path))
        tasks = _parse_tasks(seed_data)
        source_label = f"seed:{seed_path.name}"
    else:
        plan_path = Path(args.plan)
        if not plan_path.exists():
            print(f"ERROR: plan file not found: {plan_path}", file=sys.stderr)
            return 1
        logger.info("Parsing plan with heuristic parser: %s", plan_path)
        plan_text = plan_path.read_text(encoding="utf-8")
        parsed = _heuristic_parse_plan(plan_text)
        tasks = _features_to_seed_tasks(parsed.features, project_root)
        source_label = f"plan:{plan_path.name}"
        logger.info(
            "Parsed %d feature(s) from plan: %s",
            len(parsed.features),
            ", ".join(f.feature_id for f in parsed.features),
        )

    if not tasks:
        print("ERROR: no tasks found in input", file=sys.stderr)
        return 1

    logger.info("Found %d task(s) to dump prompts for", len(tasks))

    # ── Build scaffold context from disk ─────────────────────────────
    scaffold = _build_scaffold_from_disk(tasks, project_root)
    logger.info(
        "Scaffold: %d existing target file(s)",
        len(scaffold["existing_target_files"]),
    )

    # ── Output directory ─────────────────────────────────────────────
    if args.output_dir:
        output_dir = Path(args.output_dir)
    else:
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        output_dir = project_root / ".startd8" / "prompt-dumps" / ts
    output_dir.mkdir(parents=True, exist_ok=True)

    # ── Dump prompts per task ────────────────────────────────────────
    task_summaries: List[Dict[str, Any]] = []
    edit_count = 0
    create_count = 0

    for task in tasks:
        logger.info("Dumping prompts for task %s: %s", task.task_id, task.title)
        summary = _dump_task_prompts(task, scaffold, project_root, output_dir)
        task_summaries.append(summary)
        if summary["edit_mode"] == "edit":
            edit_count += 1
        else:
            create_count += 1

    # ── Write summary ────────────────────────────────────────────────
    overall_summary = {
        "source": source_label,
        "project_root": str(project_root),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "task_count": len(tasks),
        "edit_tasks": edit_count,
        "create_tasks": create_count,
        "existing_target_files": scaffold["existing_target_files"],
        "tasks": task_summaries,
    }
    summary_path = output_dir / "summary.json"
    summary_path.write_text(json.dumps(overall_summary, indent=2), encoding="utf-8")

    # ── Print report ─────────────────────────────────────────────────
    print(f"\nPrompt dump complete: {output_dir}")
    print(f"  Source: {source_label}")
    print(f"  Tasks:  {len(tasks)} ({edit_count} edit, {create_count} create)")
    print(f"  Existing target files on disk: {len(scaffold['existing_target_files'])}")
    print()

    for s in task_summaries:
        mode_tag = "EDIT" if s["edit_mode"] == "edit" else "CREATE"
        conf = s.get("edit_confidence", "n/a")
        sizes = s["prompt_sizes"]
        print(f"  [{mode_tag}] {s['task_id']}: {s['title']}")
        print(f"    confidence={conf}  files={len(s['target_files'])}  existing={s['existing_file_count']}")
        print(f"    prompt sizes: task_desc={sizes['task_description']:,}  "
              f"spec={sizes['spec_prompt']:,}  draft={sizes['draft_prompt']:,}  "
              f"existing_section={sizes['existing_files_section']:,}")
        if s["signal_conflicts"]:
            for c in s["signal_conflicts"]:
                print(f"    CONFLICT: {c}")
        print()

    print(f"Full output: {output_dir}")
    print(f"Summary:     {summary_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
