"""The census run-driver — turns the library-only census into a runnable profiling pass.

``run_prime_workflow.py --census-out <dir>`` calls :func:`begin_census` before generation (so the
observe-only hooks record into a process-scoped collector) and :func:`write_census` after (dumps the
ranked report + SARIF + raw observations). Honors the ``STARTD8_CENSUS_DISABLED`` benchmark opt-out:
when the census is hard-disabled, :func:`begin_census` installs nothing and returns ``None`` (generation
byte-identical).

See ``docs/design/deterministic-generation/REQ-determinism-gap-census.md``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional, Union

from startd8.logging_config import get_logger

from .hook import CensusCollector, get_collector, set_collector
from .report import CensusReport, build_report, render_sarif
from .scoreboard import KNOWN_LANGUAGES

logger = get_logger(__name__)


def begin_census() -> Optional[CensusCollector]:
    """Install a fresh process-scoped collector so the observe-only hooks record into it, and return it.

    Returns ``None`` when the census is hard-disabled via ``STARTD8_CENSUS_DISABLED`` (the benchmark
    opt-out): ``set_collector`` refuses to install, so ``get_collector()`` stays ``None`` and the
    generation is byte-identical. Reusing the guard (rather than re-reading the env) keeps the one
    off-switch authoritative.
    """
    collector = CensusCollector()
    set_collector(collector)
    if get_collector() is None:  # hard-disabled → set_collector refused; nothing installed
        logger.info("census hard-disabled (STARTD8_CENSUS_DISABLED) — not profiling this run")
        return None
    return collector


def write_census(collector: CensusCollector, out_dir: Union[str, Path]) -> Path:
    """Write the census artifacts for a completed run into *out_dir* and return it.

    Emits three files: ``census-report.md`` (the human scoreboard + ranked ratchet candidates),
    ``census.sarif`` (the observations through the universal findings sink), and
    ``census-observations.json`` (the raw observations). An empty census still writes a report (every
    known lane ``absent``) — honest, not a silent no-file.
    """
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    observations = collector.observations
    report = build_report(observations, languages=KNOWN_LANGUAGES)

    (out / "census-report.md").write_text(_render_markdown(report), encoding="utf-8")

    sarif = render_sarif(observations)
    sarif_text = sarif if isinstance(sarif, str) else json.dumps(sarif, indent=2, ensure_ascii=False) + "\n"
    (out / "census.sarif").write_text(sarif_text, encoding="utf-8")

    (out / "census-observations.json").write_text(
        json.dumps([_obs_dict(o) for o in observations], indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    logger.info("census: %d observations → %s", report.total_observations, out)
    return out


def _obs_dict(o) -> dict:
    return {
        "finding_class": o.finding_class,
        "language": o.language,
        "element_kind": o.element_kind,
        "file_path": o.file_path,
        "line": o.line,
        "message": o.message,
    }


def _render_markdown(report: CensusReport) -> str:
    lines = ["# Determinism-gap census", "", f"**Total observations:** {report.total_observations}"]
    if report.is_empty:
        lines += ["", "_No LLM/repair interventions recorded — an empty run, or the census was off._"]
    lines += [
        "",
        "## Per-language determinism scoreboard",
        "",
        "| Language | Status | Determinism | Interventions |",
        "|---|---|---|---:|",
    ]
    for lane in report.scoreboard:
        lines.append(f"| {lane.language} | {lane.status} | {lane.format_pct()} | {lane.interventions} |")
    lines += [
        "",
        "## Where the LLM is load-bearing — ranked ratchet candidates",
        "",
        "| # | Finding-class | Language | Domain | Freq | Template candidate |",
        "|---:|---|---|---|---:|---|",
    ]
    for i, row in enumerate(report.top(20), 1):
        lines.append(
            f"| {i} | {row.finding_class} | {row.language} | {row.domain} | {row.frequency} | {row.template_candidate} |"
        )
    lines.append("")
    return "\n".join(lines)
