#!/usr/bin/env python3
"""
Run both Artisan and Prime workflows in walkthrough mode on a single seed.

Compares prompt construction across both contractors — no LLM calls are made.
Outputs a unified comparison report (JSON + Markdown) and a flat prompt directory
for easy side-by-side browsing.

Usage:
    # Basic — run both workflows, compare prompts:
    python3 scripts/run_super_walkthrough.py \\
        --seed out/my-run/artisan-context-seed-enriched.json \\
        --project-root /tmp/test-project

    # Filter to a single task:
    python3 scripts/run_super_walkthrough.py \\
        --seed out/my-run/artisan-context-seed-enriched.json \\
        --project-root /tmp/test-project \\
        --task-filter PI-001

    # Skip one workflow for focused comparison:
    python3 scripts/run_super_walkthrough.py \\
        --seed seed.json --project-root /tmp/proj --skip-prime
"""

from __future__ import annotations

import argparse
import json
import logging
import shutil
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# Ensure SDK importable (dev-mode fallback)
_src = str(Path(__file__).resolve().parent.parent / "src")
if _src not in sys.path:
    sys.path.insert(0, _src)

from startd8.logging_config import get_logger  # noqa: E402
from startd8.seeds.schema_versions import SUPPORTED_SEED_SCHEMA_VERSIONS  # noqa: E402

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class PromptFile:
    """A single prompt file with size metrics."""

    name: str
    chars: int
    lines: int
    phase: str


@dataclass
class TaskPrompts:
    """Prompt files collected for a single task from both workflows."""

    task_id: str
    title: str
    artisan: List[PromptFile] = field(default_factory=list)
    prime: List[PromptFile] = field(default_factory=list)

    @property
    def artisan_present(self) -> bool:
        return len(self.artisan) > 0

    @property
    def prime_present(self) -> bool:
        return len(self.prime) > 0

    @property
    def artisan_total_chars(self) -> int:
        return sum(p.chars for p in self.artisan)

    @property
    def prime_total_chars(self) -> int:
        return sum(p.chars for p in self.prime)

    @property
    def artisan_total_lines(self) -> int:
        return sum(p.lines for p in self.artisan)

    @property
    def prime_total_lines(self) -> int:
        return sum(p.lines for p in self.prime)


# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------


def setup_logging(verbose: bool = False) -> None:
    """Configure logging for the super walkthrough run."""
    level = logging.DEBUG if verbose else logging.INFO
    fmt = "%(asctime)s %(levelname)-8s [%(name)s] %(message)s"
    logging.basicConfig(level=level, format=fmt, datefmt="%H:%M:%S")
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser."""
    parser = argparse.ArgumentParser(
        description=(
            "Super Walkthrough: run both Artisan and Prime in walkthrough "
            "mode on a single seed, then compare the prompts side-by-side."
        ),
    )
    parser.add_argument(
        "--seed", required=True,
        help="Path to contractor-agnostic context seed JSON",
    )
    parser.add_argument(
        "--project-root", default=".",
        help="Target project directory (default: current directory)",
    )
    parser.add_argument(
        "--output-dir", default=None,
        help=(
            "Output directory (default: out/super-walkthrough-{timestamp}). "
            "Contains reports, prompt copies, and synthetic project roots."
        ),
    )
    parser.add_argument(
        "--task-filter", default=None,
        help="Comma-separated task IDs to include (default: all tasks)",
    )
    parser.add_argument(
        "--skip-artisan", action="store_true",
        help="Skip artisan workflow (run prime only)",
    )
    parser.add_argument(
        "--skip-prime", action="store_true",
        help="Skip prime workflow (run artisan only)",
    )
    parser.add_argument(
        "--lead-agent", default=None,
        help="Lead agent spec for both workflows (default: catalog default)",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Enable debug-level logging",
    )
    return parser


# ---------------------------------------------------------------------------
# Seed loading & validation
# ---------------------------------------------------------------------------


def _load_and_validate_seed(seed_path: Path) -> Optional[Dict[str, Any]]:
    """Load and validate the seed file.

    Returns the seed dict on success, None on failure.
    """
    if not seed_path.exists():
        logger.error("Seed file not found: %s", seed_path)
        return None

    try:
        seed_data = json.loads(seed_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.error("Failed to parse seed file %s: %s", seed_path, exc)
        return None

    # Schema version check
    schema_version = seed_data.get("schema_version", seed_data.get("version", ""))
    if schema_version not in SUPPORTED_SEED_SCHEMA_VERSIONS:
        logger.error(
            "Unsupported schema_version %r (supported: %s)",
            schema_version,
            sorted(SUPPORTED_SEED_SCHEMA_VERSIONS),
        )
        return None

    # Task presence check
    tasks = seed_data.get("tasks", [])
    if not tasks:
        logger.error("Seed has no tasks — nothing to walkthrough")
        return None

    # Per-task field check
    for task in tasks:
        if not task.get("task_id"):
            logger.error("Task missing required field 'task_id': %s", task)
            return None
        if not task.get("title"):
            logger.error(
                "Task %s missing required field 'title'",
                task.get("task_id", "?"),
            )
            return None

    return seed_data


def _maybe_warn_route(seed_data: Dict[str, Any]) -> None:
    """Log a warning if the seed has a route set."""
    route = seed_data.get("route")
    if route:
        logger.warning(
            "Seed has route=%r — super walkthrough ignores route and "
            "feeds the same seed to both workflows",
            route,
        )


def _auto_enrich(
    seed_path: Path,
    seed_data: Dict[str, Any],
    project_root: Path,
) -> Path:
    """Auto-enrich the seed if _enrichment is missing.

    Returns the (possibly updated) seed path.
    """
    # Check for existing enriched sibling
    base_stem = seed_path.stem.removesuffix("-enriched")
    all_suffixes = "".join(seed_path.suffixes)
    enriched_candidate = seed_path.with_name(
        base_stem + "-enriched" + all_suffixes
    )
    if enriched_candidate != seed_path and enriched_candidate.exists():
        base_seed = seed_path.with_name(base_stem + all_suffixes)
        if base_seed.exists() and base_seed.stat().st_mtime > enriched_candidate.stat().st_mtime:
            logger.warning(
                "Enriched seed is stale — will re-run DomainPreflightWorkflow. "
                "base=%s enriched=%s",
                base_seed, enriched_candidate,
            )
        else:
            logger.info(
                "Found enriched seed on disk — using %s",
                enriched_candidate,
            )
            return enriched_candidate

    # Check if enrichment is already present
    tasks = seed_data.get("tasks", [])
    has_enrichment = any(t.get("_enrichment") for t in tasks)
    if tasks and not has_enrichment:
        logger.info(
            "Seed lacks _enrichment data — running DomainPreflightWorkflow"
        )
        try:
            from startd8.workflows.builtin.domain_preflight_workflow import (
                DomainPreflightWorkflow,
            )

            preflight = DomainPreflightWorkflow()
            preflight_result = preflight.run({
                "context_seed_path": str(seed_path),
                "project_root": str(project_root),
            })
            if preflight_result.success:
                enriched_path = Path(
                    preflight_result.output["enriched_seed_path"]
                )
                logger.info("Auto-enriched seed: %s", enriched_path)
                return enriched_path
            else:
                logger.warning(
                    "DomainPreflightWorkflow failed: %s — continuing with original seed",
                    preflight_result.error,
                )
        except Exception as exc:
            logger.warning(
                "Auto-enrichment failed: %s — continuing with original seed",
                exc,
            )

    return seed_path


# ---------------------------------------------------------------------------
# Artisan walkthrough
# ---------------------------------------------------------------------------


def _run_artisan_walkthrough(
    enriched_seed_path: Path,
    artisan_root: Path,
    task_filter: Optional[List[str]],
    lead_agent: Optional[str],
) -> Optional[Path]:
    """Run ArtisanContractorWorkflow in walkthrough mode.

    Returns the walkthrough output directory on success, None on failure.
    """
    logger.info("--- Artisan walkthrough ---")
    artisan_root.mkdir(parents=True, exist_ok=True)

    try:
        from startd8.contractors.artisan_contractor import (
            ArtisanContractorWorkflow,
            WorkflowConfig,
        )
        from startd8.contractors.context_seed_handlers import (
            ContextSeedHandlers,
        )

        # Build config with no filesystem checkpoint (in-memory only)
        config = WorkflowConfig(
            project_root=str(artisan_root),
            checkpoint_dir=None,
            dry_run=False,
        )

        workflow = ArtisanContractorWorkflow(
            config=config,
            checkpoint_store=None,
        )

        # Build handlers in walkthrough mode
        handler_kwargs: Dict[str, Any] = {
            "enriched_seed_path": str(enriched_seed_path.resolve()),
            "output_dir": str(artisan_root),
            "walkthrough": True,
        }
        if lead_agent:
            handler_kwargs["lead_agent"] = lead_agent

        handlers = ContextSeedHandlers.create_all(**handler_kwargs)
        for phase, handler in handlers.items():
            workflow.register_handler(phase, handler)

        # Build context
        initial_context: Dict[str, Any] = {
            "enriched_seed_path": str(enriched_seed_path.resolve()),
            "project_root": str(artisan_root),
        }
        if task_filter:
            initial_context["task_filter"] = task_filter

        result = workflow.execute(context=initial_context)

        wt_dir = artisan_root / ".startd8" / "walkthrough"
        if wt_dir.exists():
            logger.info(
                "Artisan walkthrough completed — status=%s, prompts at %s",
                result.status.value, wt_dir,
            )
            return wt_dir
        else:
            logger.warning(
                "Artisan walkthrough completed (status=%s) but no walkthrough "
                "directory found at %s",
                result.status.value, wt_dir,
            )
            return None

    except Exception as exc:
        logger.error("Artisan walkthrough failed: %s", exc, exc_info=True)
        return None


# ---------------------------------------------------------------------------
# Prime walkthrough
# ---------------------------------------------------------------------------


def _run_prime_walkthrough(
    enriched_seed_path: Path,
    prime_root: Path,
    task_filter: Optional[List[str]],
    lead_agent: Optional[str],
) -> Optional[Path]:
    """Run PrimeContractorWorkflow in walkthrough mode.

    Returns the walkthrough output directory on success, None on failure.
    """
    logger.info("--- Prime walkthrough ---")
    prime_root.mkdir(parents=True, exist_ok=True)

    try:
        from startd8.contractors.prime_contractor import (
            PrimeContractorWorkflow,
        )
        from startd8.contractors.generators.lead_contractor import (
            LeadContractorCodeGenerator,
        )
        from startd8.contractors.queue import FeatureStatus

        gen_kwargs: Dict[str, Any] = {
            "output_dir": prime_root / "generated",
        }
        if lead_agent:
            gen_kwargs["lead_agent"] = lead_agent

        code_generator = LeadContractorCodeGenerator(**gen_kwargs)

        workflow = PrimeContractorWorkflow(
            project_root=prime_root,
            walkthrough=True,
            allow_dirty=True,
            code_generator=code_generator,
        )

        # Load features from seed
        added = workflow.queue.add_features_from_seed(enriched_seed_path)
        logger.info("Loaded %d features from seed", len(added))

        # Load seed context
        seed_data = json.loads(
            enriched_seed_path.read_text(encoding="utf-8")
        )
        workflow.load_seed_context(seed_data)

        # Apply task filter
        if task_filter:
            filter_set = set(task_filter)
            for fid, feature in workflow.queue.features.items():
                if fid not in filter_set and feature.status in (
                    FeatureStatus.PENDING, FeatureStatus.GENERATED,
                ):
                    feature.status = FeatureStatus.COMPLETE
            logger.info(
                "Task filter applied: %s (%d task(s))",
                task_filter, len(task_filter),
            )

        result = workflow.run()

        wt_dir = prime_root / ".startd8" / "walkthrough" / "prime"
        if wt_dir.exists():
            logger.info(
                "Prime walkthrough completed — prompts at %s", wt_dir,
            )
            return wt_dir
        else:
            logger.warning(
                "Prime walkthrough completed but no walkthrough directory "
                "found at %s",
                wt_dir,
            )
            return None

    except Exception as exc:
        logger.error("Prime walkthrough failed: %s", exc, exc_info=True)
        return None


# ---------------------------------------------------------------------------
# Prompt collection
# ---------------------------------------------------------------------------

_PROMPT_SUFFIXES = {".md", ".json"}


def _infer_prime_phase(filename: str) -> str:
    """Infer the prime phase from the filename prefix."""
    lower = filename.lower()
    if lower.startswith("spec_"):
        return "spec"
    if lower.startswith("draft_"):
        return "draft"
    if lower.startswith("review_"):
        return "review"
    return "other"


def _collect_files_from_dir(directory: Path, phase: str) -> List[PromptFile]:
    """Collect prompt files from a single directory."""
    files: List[PromptFile] = []
    if not directory.exists():
        return files
    for entry in sorted(directory.iterdir()):
        if entry.is_file() and entry.suffix in _PROMPT_SUFFIXES:
            content = entry.read_text(encoding="utf-8", errors="replace")
            files.append(PromptFile(
                name=entry.name,
                chars=len(content),
                lines=content.count("\n") + (1 if content and not content.endswith("\n") else 0),
                phase=phase,
            ))
    return files


def _collect_and_copy_prompts(
    task_ids: List[str],
    task_titles: Dict[str, str],
    artisan_wt_root: Optional[Path],
    prime_wt_root: Optional[Path],
    output_dir: Path,
) -> List[TaskPrompts]:
    """Collect prompts from both workflows and copy to flat layout.

    Returns a list of TaskPrompts, one per task_id.
    """
    prompts_dir = output_dir / "prompts"
    results: List[TaskPrompts] = []

    for task_id in task_ids:
        tp = TaskPrompts(
            task_id=task_id,
            title=task_titles.get(task_id, "(untitled)"),
        )

        # Artisan: design + implement phase directories
        if artisan_wt_root:
            for phase_name in ("design", "implement"):
                src_dir = artisan_wt_root / phase_name / task_id
                collected = _collect_files_from_dir(src_dir, phase_name)
                tp.artisan.extend(collected)

                # Copy to flat layout
                if collected:
                    dest = prompts_dir / "artisan" / task_id / phase_name
                    dest.mkdir(parents=True, exist_ok=True)
                    for entry in src_dir.iterdir():
                        if entry.is_file() and entry.suffix in _PROMPT_SUFFIXES:
                            shutil.copy2(entry, dest / entry.name)

        # Prime: all files in a single directory
        if prime_wt_root:
            src_dir = prime_wt_root / task_id
            if src_dir.exists():
                for entry in sorted(src_dir.iterdir()):
                    if entry.is_file() and entry.suffix in _PROMPT_SUFFIXES:
                        content = entry.read_text(
                            encoding="utf-8", errors="replace",
                        )
                        tp.prime.append(PromptFile(
                            name=entry.name,
                            chars=len(content),
                            lines=content.count("\n") + (
                                1 if content and not content.endswith("\n") else 0
                            ),
                            phase=_infer_prime_phase(entry.name),
                        ))

                # Copy to flat layout
                dest = prompts_dir / "prime" / task_id
                dest.mkdir(parents=True, exist_ok=True)
                for entry in src_dir.iterdir():
                    if entry.is_file() and entry.suffix in _PROMPT_SUFFIXES:
                        shutil.copy2(entry, dest / entry.name)

        results.append(tp)

    return results


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------


def _safe_avg(values: List[int]) -> Optional[float]:
    """Safe average — returns None if list is empty."""
    if not values:
        return None
    return sum(values) / len(values)


def _fmt_int(value: Optional[int], fallback: str = "n/a") -> str:
    """Format an optional int for display."""
    if value is None:
        return fallback
    return f"{value:,}"


def _fmt_float(value: Optional[float], fallback: str = "n/a") -> str:
    """Format an optional float for display."""
    if value is None:
        return fallback
    return f"{value:,.0f}"


def _phase_breakdown(files: List[PromptFile]) -> Dict[str, Dict[str, int]]:
    """Group prompt files by phase, returning chars/lines per phase."""
    breakdown: Dict[str, Dict[str, int]] = {}
    for f in files:
        if f.phase not in breakdown:
            breakdown[f.phase] = {"chars": 0, "lines": 0, "files": 0}
        breakdown[f.phase]["chars"] += f.chars
        breakdown[f.phase]["lines"] += f.lines
        breakdown[f.phase]["files"] += 1
    return breakdown


def _build_report(
    comparisons: List[TaskPrompts],
    seed_path: str,
    task_filter: Optional[List[str]],
    artisan_status: str,
    prime_status: str,
) -> Dict[str, Any]:
    """Build the JSON report structure."""
    tasks_data: Dict[str, Any] = {}

    for tp in comparisons:
        artisan_breakdown = _phase_breakdown(tp.artisan)
        prime_breakdown = _phase_breakdown(tp.prime)

        tasks_data[tp.task_id] = {
            "title": tp.title,
            "artisan_present": tp.artisan_present,
            "prime_present": tp.prime_present,
            "artisan": {
                "total_chars": tp.artisan_total_chars,
                "total_lines": tp.artisan_total_lines,
                "file_count": len(tp.artisan),
                "phases": artisan_breakdown,
                "files": [
                    {"name": f.name, "chars": f.chars, "lines": f.lines, "phase": f.phase}
                    for f in tp.artisan
                ],
            },
            "prime": {
                "total_chars": tp.prime_total_chars,
                "total_lines": tp.prime_total_lines,
                "file_count": len(tp.prime),
                "phases": prime_breakdown,
                "files": [
                    {"name": f.name, "chars": f.chars, "lines": f.lines, "phase": f.phase}
                    for f in tp.prime
                ],
            },
            "deltas": {
                "total_chars": tp.artisan_total_chars - tp.prime_total_chars,
                "total_lines": tp.artisan_total_lines - tp.prime_total_lines,
            },
        }

    # Aggregate
    artisan_chars = [tp.artisan_total_chars for tp in comparisons if tp.artisan_present]
    prime_chars = [tp.prime_total_chars for tp in comparisons if tp.prime_present]
    artisan_lines = [tp.artisan_total_lines for tp in comparisons if tp.artisan_present]
    prime_lines = [tp.prime_total_lines for tp in comparisons if tp.prime_present]

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "seed_path": seed_path,
        "task_count": len(comparisons),
        "task_filter": task_filter,
        "artisan_status": artisan_status,
        "prime_status": prime_status,
        "tasks": tasks_data,
        "aggregate": {
            "avg_prompt_chars": {
                "artisan": _safe_avg(artisan_chars),
                "prime": _safe_avg(prime_chars),
            },
            "avg_prompt_lines": {
                "artisan": _safe_avg(artisan_lines),
                "prime": _safe_avg(prime_lines),
            },
            "tasks_with_prompts": {
                "artisan": len(artisan_chars),
                "prime": len(prime_chars),
            },
            "tasks_missing_prompts": {
                "artisan": sum(1 for tp in comparisons if not tp.artisan_present),
                "prime": sum(1 for tp in comparisons if not tp.prime_present),
            },
        },
    }


def _render_markdown(report: Dict[str, Any], output_dir: Path) -> str:
    """Render the report as human-readable Markdown."""
    lines: List[str] = []

    lines.append("# Super Walkthrough Comparison Report")
    lines.append("")
    lines.append(f"- **Generated:** {report['generated_at']}")
    lines.append(f"- **Seed:** `{report['seed_path']}`")
    lines.append(f"- **Tasks:** {report['task_count']}")
    if report["task_filter"]:
        lines.append(f"- **Filter:** {', '.join(report['task_filter'])}")
    lines.append(f"- **Artisan status:** {report['artisan_status']}")
    lines.append(f"- **Prime status:** {report['prime_status']}")
    lines.append("")

    # Summary table
    lines.append("## Summary")
    lines.append("")
    lines.append(
        "| Task | Artisan chars | Artisan lines | Prime chars | Prime lines | "
        "Delta chars | Delta lines |"
    )
    lines.append(
        "|------|--------------|--------------|-------------|-------------|"
        "------------|-------------|"
    )

    tasks = report.get("tasks", {})
    for task_id, data in tasks.items():
        a_chars = data["artisan"]["total_chars"] if data["artisan_present"] else None
        a_lines = data["artisan"]["total_lines"] if data["artisan_present"] else None
        p_chars = data["prime"]["total_chars"] if data["prime_present"] else None
        p_lines = data["prime"]["total_lines"] if data["prime_present"] else None
        d_chars = data["deltas"]["total_chars"] if data["artisan_present"] and data["prime_present"] else None
        d_lines = data["deltas"]["total_lines"] if data["artisan_present"] and data["prime_present"] else None

        lines.append(
            f"| {task_id} | {_fmt_int(a_chars)} | {_fmt_int(a_lines)} | "
            f"{_fmt_int(p_chars)} | {_fmt_int(p_lines)} | "
            f"{_fmt_int(d_chars)} | {_fmt_int(d_lines)} |"
        )

    lines.append("")

    # Aggregate
    agg = report.get("aggregate", {})
    lines.append("## Aggregate")
    lines.append("")
    avg_chars = agg.get("avg_prompt_chars", {})
    avg_lines = agg.get("avg_prompt_lines", {})
    lines.append(f"- **Avg chars:** Artisan={_fmt_float(avg_chars.get('artisan'))}, Prime={_fmt_float(avg_chars.get('prime'))}")
    lines.append(f"- **Avg lines:** Artisan={_fmt_float(avg_lines.get('artisan'))}, Prime={_fmt_float(avg_lines.get('prime'))}")
    wp = agg.get("tasks_with_prompts", {})
    mp = agg.get("tasks_missing_prompts", {})
    lines.append(f"- **Tasks with prompts:** Artisan={wp.get('artisan', 0)}, Prime={wp.get('prime', 0)}")
    lines.append(f"- **Tasks missing prompts:** Artisan={mp.get('artisan', 0)}, Prime={mp.get('prime', 0)}")
    lines.append("")

    # Per-task file details
    lines.append("## Per-Task Details")
    lines.append("")

    for task_id, data in tasks.items():
        lines.append(f"### {task_id}: {data.get('title', '')}")
        lines.append("")

        # Artisan files
        if data["artisan_present"]:
            lines.append("**Artisan prompts:**")
            lines.append("")
            lines.append("| File | Phase | Chars | Lines |")
            lines.append("|------|-------|-------|-------|")
            for f in data["artisan"]["files"]:
                lines.append(
                    f"| {f['name']} | {f['phase']} | {f['chars']:,} | {f['lines']:,} |"
                )
            lines.append("")
        else:
            lines.append("**Artisan:** no prompts collected")
            lines.append("")

        # Prime files
        if data["prime_present"]:
            lines.append("**Prime prompts:**")
            lines.append("")
            lines.append("| File | Phase | Chars | Lines |")
            lines.append("|------|-------|-------|-------|")
            for f in data["prime"]["files"]:
                lines.append(
                    f"| {f['name']} | {f['phase']} | {f['chars']:,} | {f['lines']:,} |"
                )
            lines.append("")
        else:
            lines.append("**Prime:** no prompts collected")
            lines.append("")

    # Footer
    lines.append("---")
    lines.append(f"Prompt files: `{output_dir / 'prompts'}`")
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    """Entry point. Returns 0 on success, 1 on failure."""
    parser = build_parser()
    args = parser.parse_args()
    setup_logging(args.verbose)

    if args.skip_artisan and args.skip_prime:
        logger.error("Cannot skip both --skip-artisan and --skip-prime")
        return 1

    seed_path = Path(args.seed).resolve()
    project_root = Path(args.project_root).resolve()

    # Output directory
    if args.output_dir:
        output_dir = Path(args.output_dir).resolve()
    else:
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        output_dir = Path("out") / f"super-walkthrough-{ts}"
        output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    logger.info("Super Walkthrough starting")
    logger.info("  Seed: %s", seed_path)
    logger.info("  Project root: %s", project_root)
    logger.info("  Output dir: %s", output_dir)

    # ------------------------------------------------------------------
    # Step 1: Load and validate seed
    # ------------------------------------------------------------------
    seed_data = _load_and_validate_seed(seed_path)
    if seed_data is None:
        return 1

    _maybe_warn_route(seed_data)

    task_filter: Optional[List[str]] = None
    if args.task_filter:
        task_filter = [t.strip() for t in args.task_filter.split(",") if t.strip()]

    # Build task ID -> title map for report
    task_titles: Dict[str, str] = {}
    all_task_ids: List[str] = []
    for task in seed_data.get("tasks", []):
        tid = task.get("task_id", "")
        task_titles[tid] = task.get("title", "(untitled)")
        if task_filter is None or tid in task_filter:
            all_task_ids.append(tid)

    logger.info(
        "Seed loaded: %d task(s)%s",
        len(all_task_ids),
        f" (filtered from {len(seed_data.get('tasks', []))})" if task_filter else "",
    )

    # ------------------------------------------------------------------
    # Step 2: Auto-enrich
    # ------------------------------------------------------------------
    try:
        enriched_seed_path = _auto_enrich(seed_path, seed_data, project_root)
    except Exception as exc:
        logger.warning("Auto-enrichment failed: %s — continuing with original seed", exc)
        enriched_seed_path = seed_path

    # Copy enriched seed to output for provenance
    provenance_copy = output_dir / "enriched-seed.json"
    shutil.copy2(enriched_seed_path, provenance_copy)
    logger.info("Enriched seed copied to %s", provenance_copy)

    # ------------------------------------------------------------------
    # Step 3: Artisan walkthrough
    # ------------------------------------------------------------------
    artisan_wt_root: Optional[Path] = None
    artisan_status = "skipped"

    if not args.skip_artisan:
        artisan_project_root = output_dir / "artisan_wt_root"
        artisan_wt_root = _run_artisan_walkthrough(
            enriched_seed_path=enriched_seed_path,
            artisan_root=artisan_project_root,
            task_filter=task_filter,
            lead_agent=args.lead_agent,
        )
        artisan_status = "ok" if artisan_wt_root else "failed"

    # ------------------------------------------------------------------
    # Step 4: Prime walkthrough
    # ------------------------------------------------------------------
    prime_wt_root: Optional[Path] = None
    prime_status = "skipped"

    if not args.skip_prime:
        prime_project_root = output_dir / "prime_wt_root"
        prime_wt_root = _run_prime_walkthrough(
            enriched_seed_path=enriched_seed_path,
            prime_root=prime_project_root,
            task_filter=task_filter,
            lead_agent=args.lead_agent,
        )
        prime_status = "ok" if prime_wt_root else "failed"

    # ------------------------------------------------------------------
    # Step 5: Collect prompts
    # ------------------------------------------------------------------
    logger.info("Collecting and copying prompts...")
    comparisons = _collect_and_copy_prompts(
        task_ids=all_task_ids,
        task_titles=task_titles,
        artisan_wt_root=artisan_wt_root,
        prime_wt_root=prime_wt_root,
        output_dir=output_dir,
    )

    # ------------------------------------------------------------------
    # Step 6: Generate reports
    # ------------------------------------------------------------------
    report = _build_report(
        comparisons=comparisons,
        seed_path=str(seed_path),
        task_filter=task_filter,
        artisan_status=artisan_status,
        prime_status=prime_status,
    )

    # Write JSON report
    json_path = output_dir / "super-walkthrough.json"
    json_path.write_text(
        json.dumps(report, indent=2, default=str),
        encoding="utf-8",
    )
    logger.info("JSON report: %s", json_path)

    # Write Markdown report
    md_content = _render_markdown(report, output_dir)
    md_path = output_dir / "super-walkthrough.md"
    md_path.write_text(md_content, encoding="utf-8")
    logger.info("Markdown report: %s", md_path)

    # ------------------------------------------------------------------
    # Step 7: Console summary
    # ------------------------------------------------------------------
    print()
    print("=" * 70)
    print("  SUPER WALKTHROUGH SUMMARY")
    print("=" * 70)
    print(f"  Artisan: {artisan_status}    Prime: {prime_status}")
    print()

    # Quick summary table
    header = f"  {'Task':<16} {'Artisan':>12} {'Prime':>12} {'Delta':>12}"
    print(header)
    print("  " + "-" * (len(header) - 2))
    for tp in comparisons:
        a_str = f"{tp.artisan_total_chars:,}" if tp.artisan_present else "n/a"
        p_str = f"{tp.prime_total_chars:,}" if tp.prime_present else "n/a"
        if tp.artisan_present and tp.prime_present:
            d_str = f"{tp.artisan_total_chars - tp.prime_total_chars:+,}"
        else:
            d_str = "n/a"
        print(f"  {tp.task_id:<16} {a_str:>12} {p_str:>12} {d_str:>12}")

    print()
    print(f"  Output: {output_dir}")
    print(f"  Prompts: {output_dir / 'prompts'}")
    print("=" * 70)
    print()

    # Exit code: 0 if at least one workflow produced prompts
    any_prompts = any(tp.artisan_present or tp.prime_present for tp in comparisons)
    if not any_prompts:
        logger.warning("No prompts collected from either workflow")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
