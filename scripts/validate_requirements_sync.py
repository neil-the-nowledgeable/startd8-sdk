#!/usr/bin/env python3
"""Validate sync between canonical YAML requirements and companion markdown files.

Detects four kinds of drift:
  1. Dashboard count drift — YAML-derived counts vs MD Status Dashboard table
  2. Coverage drift — requirement IDs present in one file but not the other
  3. Version drift — version string mismatch between YAML header and MD header
  4. Status alignment — per-requirement status mismatch between YAML and MD
     (only checks IDs with explicit status in both files)
  5. Status resolution (--resolve) — for each status mismatch, walks git history
     to find when each file's status was last set and reports which is newer

Usage:
    python3 scripts/validate_requirements_sync.py              # Check all pairs
    python3 scripts/validate_requirements_sync.py --pair artisan
    python3 scripts/validate_requirements_sync.py --json       # JSON output for CI
    python3 scripts/validate_requirements_sync.py --verbose    # Per-requirement detail
    python3 scripts/validate_requirements_sync.py --resolve    # Git-based mismatch resolution

Exit code: 0 if all PASS, 1 if any FAIL. Warnings don't cause non-zero exit.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Set, Tuple

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML is required. Install with: pip3 install pyyaml", file=sys.stderr)
    sys.exit(2)

_REPO_ROOT = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# Pair registry
# ---------------------------------------------------------------------------

# Maps YAML layer key → display name used in the MD Status Dashboard table.
_ARTISAN_LAYER_NAMES: Dict[str, str] = {
    "phase_behavior_requirements": "Phase Behavior",
    "orchestration_requirements": "Orchestration",
    "contextcore_data_flow_requirements": "ContextCore Data Flow",
    "cost_model_requirements": "Cost Model",
    "handoff_recovery_requirements": "Handoff and Recovery",
    "observability_requirements": "Observability",
    "configuration_requirements": "Configuration",
    "safety_resilience_requirements": "Safety and Resilience",
    "mottainai_compliance_requirements": "Mottainai Compliance",
}

_ARCH_REVIEW_LAYER_NAMES: Dict[str, str] = {
    "core_review_protocol_requirements": "Core Review Protocol",
    "domain_coverage_requirements": "Domain Coverage",
    "triage_requirements": "Triage and Decision",
    "dual_document_requirements": "Dual-Document Mode",
    "agent_selection_requirements": "Agent Selection and Quality",
    "validation_requirements": "Validation and Safety",
    "state_requirements": "State and Persistence",
    "observability_requirements": "Observability and Cost",
}


@dataclass
class PairConfig:
    name: str
    yaml_path: Path
    md_path: Path
    id_prefix: str  # e.g. "AR", "RV"
    layer_display_names: Dict[str, str]


@dataclass
class PairConfig_MDOnly:
    """Pair where only the markdown file exists (no canonical YAML yet)."""

    name: str
    md_path: Path


PAIR_REGISTRY: List[PairConfig | PairConfig_MDOnly] = [
    PairConfig(
        name="artisan",
        yaml_path=_REPO_ROOT / "docs" / "capability-index" / "startd8.artisan.functional-requirements.yaml",
        md_path=_REPO_ROOT / "docs" / "design" / "artisan" / "ARTISAN_REQUIREMENTS.md",
        id_prefix="AR",
        layer_display_names=_ARTISAN_LAYER_NAMES,
    ),
    PairConfig(
        name="arch-review",
        yaml_path=_REPO_ROOT / "docs" / "capability-index" / "startd8.architectural-review.functional-requirements.yaml",
        md_path=_REPO_ROOT / "docs" / "ARCHITECTURAL_REVIEW_REQUIREMENTS.md",
        id_prefix="RV",
        layer_display_names=_ARCH_REVIEW_LAYER_NAMES,
    ),
    PairConfig_MDOnly(
        name="prime",
        md_path=_REPO_ROOT / "docs" / "design" / "prime" / "PRIME_CONTRACTOR_REQUIREMENTS.md",
    ),
]


# ---------------------------------------------------------------------------
# YAML parsing
# ---------------------------------------------------------------------------

@dataclass
class LayerCounts:
    total: int = 0
    implemented: int = 0
    partial: int = 0
    planned: int = 0


@dataclass
class YAMLParseResult:
    version: Optional[str] = None
    id_to_status: Dict[str, str] = field(default_factory=dict)
    layer_counts: Dict[str, LayerCounts] = field(default_factory=dict)


def parse_yaml_requirements(path: Path, layer_display_names: Dict[str, str]) -> YAMLParseResult:
    """Parse a canonical requirements YAML file."""
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    result = YAMLParseResult(version=data.get("version"))

    for yaml_key, display_name in layer_display_names.items():
        reqs = data.get(yaml_key)
        if not isinstance(reqs, list):
            continue
        counts = LayerCounts()
        for req in reqs:
            req_id = req.get("id", "")
            status = req.get("status", "").lower()
            result.id_to_status[req_id] = status
            counts.total += 1
            if status == "implemented":
                counts.implemented += 1
            elif status == "partial":
                counts.partial += 1
            elif status == "planned":
                counts.planned += 1
        result.layer_counts[display_name] = counts

    return result


# ---------------------------------------------------------------------------
# Markdown parsing
# ---------------------------------------------------------------------------

@dataclass
class MDDashboardResult:
    version: Optional[str] = None
    layer_counts: Dict[str, LayerCounts] = field(default_factory=dict)
    total_counts: Optional[LayerCounts] = None


def parse_md_dashboard(path: Path) -> MDDashboardResult:
    """Parse the Status Dashboard table and version from a companion markdown."""
    text = path.read_text(encoding="utf-8")
    result = MDDashboardResult()

    # Version: look for **Version:** pattern
    ver_match = re.search(r"\*\*Version:\*\*\s*(\S+)", text)
    if ver_match:
        result.version = ver_match.group(1).strip()

    # Find the dashboard table.  Header row starts with "| Layer"
    lines = text.splitlines()
    in_table = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("| Layer"):
            in_table = True
            continue
        if in_table and stripped.startswith("|---"):
            continue  # separator row
        if in_table and stripped.startswith("|"):
            row = _parse_dashboard_row(stripped)
            if row is None:
                continue
            layer_name, counts = row
            if layer_name.lower() == "total":
                result.total_counts = counts
            else:
                result.layer_counts[layer_name] = counts
        elif in_table:
            break  # end of table

    return result


def _parse_dashboard_row(line: str) -> Optional[Tuple[str, LayerCounts]]:
    """Parse a single dashboard table row into (layer_name, counts).

    Expected columns: | Layer | ID Range | Total | Implemented | Partial | Planned |
    or the 5-column variant without Partial.
    """
    cells = [c.strip() for c in line.strip().strip("|").split("|")]

    if len(cells) < 4:
        return None

    layer_name = _strip_bold(cells[0])
    if not layer_name:
        return None

    counts = LayerCounts()
    try:
        if len(cells) >= 6:
            # 6-column: Layer | ID Range | Total | Implemented | Partial | Planned
            counts.total = _parse_bold_int(cells[2])
            counts.implemented = _parse_bold_int(cells[3])
            counts.partial = _parse_bold_int(cells[4])
            counts.planned = _parse_bold_int(cells[5])
        elif len(cells) >= 5:
            # 5-column: Layer | ID Range | Total | Implemented | Planned
            counts.total = _parse_bold_int(cells[2])
            counts.implemented = _parse_bold_int(cells[3])
            counts.planned = _parse_bold_int(cells[4])
    except (ValueError, IndexError):
        return None

    return layer_name, counts


def _strip_bold(text: str) -> str:
    """Remove markdown bold markers (**...**)."""
    return re.sub(r"\*\*", "", text).strip()


def _parse_bold_int(text: str) -> int:
    """Parse an integer that may be wrapped in bold markers."""
    return int(_strip_bold(text))


def parse_md_requirement_ids(path: Path, id_prefix: str) -> Set[str]:
    """Extract all requirement IDs matching {prefix}-\\d{3} from the markdown body.

    Excludes IDs found after an Appendix C heading to avoid counting review-log
    cross-references as requirement definitions.
    """
    text = path.read_text(encoding="utf-8")

    # Truncate at Appendix C if present
    appendix_match = re.search(r"^###?\s+Appendix\s+C\b", text, re.MULTILINE | re.IGNORECASE)
    if appendix_match:
        text = text[: appendix_match.start()]

    pattern = re.compile(rf"\b{re.escape(id_prefix)}-(\d{{3}})\b")
    return {f"{id_prefix}-{m.group(1)}" for m in pattern.finditer(text)}


def _expand_id_cell(cell: str, id_prefix: str) -> List[str]:
    """Expand a table cell into individual requirement IDs.

    Handles:
      - Single IDs: ``AR-127``
      - Comma-separated: ``AR-127, AR-128``
      - Ranges: ``AR-300..AR-309``
      - Mixed: ``AR-805, AR-807..AR-809``
    """
    ids: List[str] = []
    esc = re.escape(id_prefix)
    # Split on commas first, then handle ranges within each part
    for part in cell.split(","):
        part = part.strip()
        range_match = re.match(
            rf"({esc})-(\d{{3}})\.\.({esc})-(\d{{3}})", part
        )
        if range_match:
            start = int(range_match.group(2))
            end = int(range_match.group(4))
            for n in range(start, end + 1):
                ids.append(f"{id_prefix}-{n:03d}")
        else:
            single = re.search(rf"{esc}-(\d{{3}})", part)
            if single:
                ids.append(f"{id_prefix}-{single.group(1)}")
    return ids


def _parse_md_statuses_from_text(text: str, id_prefix: str) -> Dict[str, str]:
    """Extract per-requirement statuses from markdown text.

    Two patterns are recognised:
      1. **Table rows with a Status column** — any markdown table whose header
         contains a cell matching ``Status`` (case-insensitive).  The column
         holding IDs matching *id_prefix* and the Status column are extracted.
      2. **Heading + inline block** — ``### AR-xxx: ...\\n\\n**Status:** planned``.

    IDs after an Appendix C heading are excluded (same as ``parse_md_requirement_ids``).
    Returns ``{requirement_id: lowercase_status}``.
    """
    # Truncate at Appendix C if present
    appendix_match = re.search(r"^###?\s+Appendix\s+C\b", text, re.MULTILINE | re.IGNORECASE)
    if appendix_match:
        text = text[: appendix_match.start()]

    result: Dict[str, str] = {}
    esc = re.escape(id_prefix)

    # --- Pattern 1: tables with a Status column ---
    _PIPE_PLACEHOLDER = "\x00PIPE\x00"
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        # Detect a table header row containing "Status"
        if line.startswith("|") and "|" in line[1:]:
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            status_col: Optional[int] = None
            id_col: Optional[int] = None
            for ci, cell in enumerate(cells):
                if cell.lower() == "status":
                    status_col = ci
                # ID column: prefer "ID" header, fall back to "Requirement"
                cl = cell.lower()
                if cl == "id" or id_prefix in cell:
                    id_col = ci
                elif cl == "requirement" and id_col is None:
                    id_col = ci
            if status_col is not None and id_col is not None:
                # Skip the separator row
                i += 1
                if i < len(lines) and re.match(r"^\s*\|[\s\-:|]+\|\s*$", lines[i]):
                    i += 1
                # Parse data rows
                while i < len(lines) and lines[i].strip().startswith("|"):
                    # Replace escaped pipes before splitting
                    safe_line = lines[i].replace("\\|", _PIPE_PLACEHOLDER)
                    row_cells = [
                        c.strip().replace(_PIPE_PLACEHOLDER, "\\|")
                        for c in safe_line.strip().strip("|").split("|")
                    ]
                    if len(row_cells) > max(status_col, id_col):
                        raw_ids = row_cells[id_col]
                        raw_status = row_cells[status_col].lower()
                        if raw_status:
                            for rid in _expand_id_cell(raw_ids, id_prefix):
                                result[rid] = raw_status
                    i += 1
                continue  # already advanced past the table
        i += 1

    # --- Pattern 2: heading + inline **Status:** block ---
    heading_pattern = re.compile(
        rf"^###\s+({esc}-\d{{3}}):\s+.*$\n\n\*\*Status:\*\*\s+(\S+)",
        re.MULTILINE,
    )
    for m in heading_pattern.finditer(text):
        rid = m.group(1)
        status = m.group(2).lower()
        # Heading-based status only fills in gaps; table status takes precedence
        if rid not in result:
            result[rid] = status

    return result


def parse_md_requirement_statuses(path: Path, id_prefix: str) -> Dict[str, str]:
    """Extract per-requirement statuses from a companion markdown file."""
    text = path.read_text(encoding="utf-8")
    return _parse_md_statuses_from_text(text, id_prefix)


def _parse_yaml_id_to_status(text: str, layer_display_names: Dict[str, str]) -> Dict[str, str]:
    """Extract {req_id: status} from YAML text without building the full YAMLParseResult."""
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError:
        # Historical commits may contain truncated or binary content after renames
        return {}
    if not isinstance(data, dict):
        return {}
    result: Dict[str, str] = {}
    for yaml_key in layer_display_names:
        reqs = data.get(yaml_key)
        if not isinstance(reqs, list):
            continue
        for req in reqs:
            req_id = req.get("id", "")
            status = req.get("status", "").lower()
            if req_id and status:
                result[req_id] = status
    return result


# ---------------------------------------------------------------------------
# Resolution data model
# ---------------------------------------------------------------------------

@dataclass
class StatusResolution:
    req_id: str
    yaml_status: str
    md_status: str
    yaml_commit: Optional[str] = None   # short hash
    yaml_date: Optional[str] = None     # ISO date
    md_commit: Optional[str] = None
    md_date: Optional[str] = None
    likely_correct: Optional[str] = None  # "yaml" | "md" | None
    reason: str = ""


# ---------------------------------------------------------------------------
# Git history helpers
# ---------------------------------------------------------------------------

def _repo_relative_posix(path: Path) -> Optional[str]:
    """Return *path* relative to _REPO_ROOT as a POSIX string for git commands."""
    try:
        return path.resolve().relative_to(_REPO_ROOT.resolve()).as_posix()
    except ValueError:
        return None


def _is_git_repo() -> bool:
    """Return True if _REPO_ROOT is inside a git work tree."""
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            capture_output=True, text=True, cwd=_REPO_ROOT, timeout=30,
        )
        return proc.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _git_file_history(
    path: Path, max_commits: int = 20,
) -> List[Tuple[str, str, str]]:
    """Return up to *max_commits* entries for *path* (newest first).

    Each entry is ``(short_hash, iso_date, subject)``.
    """
    rel = _repo_relative_posix(path)
    if rel is None:
        return []
    try:
        proc = subprocess.run(
            [
                "git", "log", "--follow", f"--max-count={max_commits}",
                "--format=%h\t%aI\t%s", "--", rel,
            ],
            capture_output=True, text=True, cwd=_REPO_ROOT, timeout=30,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []
    if proc.returncode != 0:
        return []
    entries: List[Tuple[str, str, str]] = []
    for line in proc.stdout.strip().splitlines():
        parts = line.split("\t", 2)
        if len(parts) == 3:
            entries.append((parts[0], parts[1], parts[2]))
    return entries


_SAFE_COMMIT_RE = re.compile(r"^[0-9a-f]{4,40}$")


def _git_show_text(commit: str, path: Path) -> Optional[str]:
    """Return the content of *path* at *commit*, or None on failure."""
    if not _SAFE_COMMIT_RE.match(commit):
        return None
    rel = _repo_relative_posix(path)
    if rel is None:
        return None
    try:
        proc = subprocess.run(
            ["git", "show", f"{commit}:{rel}"],
            capture_output=True, text=True, cwd=_REPO_ROOT, timeout=30,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout


def _find_status_introduction(
    history: List[Tuple[str, str, str]],
    file_path: Path,
    req_id: str,
    current_status: str,
    parse_fn: Callable[[str], Dict[str, str]],
) -> Optional[Tuple[str, str, str]]:
    """Walk commits newest→oldest to find when *current_status* was introduced.

    *parse_fn* accepts ``(text) -> dict[req_id, status]``.
    Returns ``(commit, date, subject)`` of the introducing commit, or None.
    """
    introducing: Optional[Tuple[str, str, str]] = None
    for commit, date, subject in history:
        text = _git_show_text(commit, file_path)
        if text is None:
            break
        statuses = parse_fn(text)
        if statuses.get(req_id) == current_status:
            introducing = (commit, date, subject)
        else:
            # Status differs or req doesn't exist — previous match was the intro
            break
    return introducing


def resolve_status_mismatches(
    mismatched_ids: List[Tuple[str, str, str]],
    pair: "PairConfig",
) -> List["StatusResolution"]:
    """For each (req_id, yaml_status, md_status), walk git history to find which is newer.

    Returns a list of StatusResolution objects.
    """
    if not _is_git_repo():
        return [
            StatusResolution(
                req_id=rid, yaml_status=ys, md_status=ms,
                reason="Not a git repository",
            )
            for rid, ys, ms in mismatched_ids
        ]

    yaml_history = _git_file_history(pair.yaml_path)
    md_history = _git_file_history(pair.md_path)

    def yaml_parser(text: str) -> Dict[str, str]:
        return _parse_yaml_id_to_status(text, pair.layer_display_names)

    def md_parser(text: str) -> Dict[str, str]:
        return _parse_md_statuses_from_text(text, pair.id_prefix)

    resolutions: List[StatusResolution] = []
    for req_id, yaml_status, md_status in mismatched_ids:
        res = StatusResolution(
            req_id=req_id, yaml_status=yaml_status, md_status=md_status,
        )

        yaml_intro = _find_status_introduction(
            yaml_history, pair.yaml_path, req_id, yaml_status, yaml_parser,
        )
        md_intro = _find_status_introduction(
            md_history, pair.md_path, req_id, md_status, md_parser,
        )

        if yaml_intro:
            res.yaml_commit, res.yaml_date = yaml_intro[0], yaml_intro[1]
        if md_intro:
            res.md_commit, res.md_date = md_intro[0], md_intro[1]

        if yaml_intro and md_intro:
            # ISO-8601 string comparison is correct when TZ offsets match (same machine).
            # Multi-contributor repos with mixed TZs could compare incorrectly.
            if res.yaml_date > res.md_date:  # type: ignore[operator]
                res.likely_correct = "yaml"
                res.reason = "YAML change is newer"
            elif res.md_date > res.yaml_date:  # type: ignore[operator]
                res.likely_correct = "md"
                res.reason = "MD change is newer"
            else:
                res.likely_correct = "yaml"
                res.reason = "Same date; YAML wins as canonical source"
        elif yaml_intro and not md_intro:
            res.likely_correct = "yaml"
            res.reason = "MD has no trackable history for this status"
        elif md_intro and not yaml_intro:
            res.likely_correct = "md"
            res.reason = "YAML has no trackable history for this status"
        else:
            res.reason = "No trackable history in either file"

        resolutions.append(res)

    return resolutions


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------

@dataclass
class CheckResult:
    name: str  # "dashboard", "coverage", "version"
    status: str  # "PASS", "FAIL", "WARN"
    message: str
    details: List[str] = field(default_factory=list)
    resolutions: List[StatusResolution] = field(default_factory=list)


@dataclass
class PairResult:
    pair_name: str
    checks: List[CheckResult] = field(default_factory=list)
    skipped: Optional[str] = None  # reason if skipped entirely


def check_dashboard_counts(
    yaml_result: YAMLParseResult,
    md_result: MDDashboardResult,
    pair: PairConfig,
) -> CheckResult:
    """Compare YAML-derived layer counts against MD dashboard table."""
    mismatches: List[str] = []

    for display_name, yaml_counts in yaml_result.layer_counts.items():
        md_counts = md_result.layer_counts.get(display_name)
        if md_counts is None:
            mismatches.append(f"  - {display_name}: layer missing from MD dashboard")
            continue
        for field_name in ("total", "implemented", "partial", "planned"):
            yval = getattr(yaml_counts, field_name)
            mval = getattr(md_counts, field_name)
            if yval != mval:
                mismatches.append(
                    f"  - {display_name}.{field_name}: YAML={yval}, MD={mval}"
                )

    # Check for layers in MD but not in YAML
    for md_layer in md_result.layer_counts:
        if md_layer not in yaml_result.layer_counts:
            mismatches.append(f"  - {md_layer}: layer in MD but NOT in YAML")

    # Check totals row
    if md_result.total_counts is not None:
        yaml_totals = LayerCounts()
        for lc in yaml_result.layer_counts.values():
            yaml_totals.total += lc.total
            yaml_totals.implemented += lc.implemented
            yaml_totals.partial += lc.partial
            yaml_totals.planned += lc.planned
        for field_name in ("total", "implemented", "partial", "planned"):
            yval = getattr(yaml_totals, field_name)
            mval = getattr(md_result.total_counts, field_name)
            if yval != mval:
                mismatches.append(
                    f"  - Total.{field_name}: YAML={yval}, MD={mval}"
                )

    if mismatches:
        return CheckResult(
            name="dashboard",
            status="FAIL",
            message="Dashboard count drift detected",
            details=mismatches,
        )
    return CheckResult(
        name="dashboard",
        status="PASS",
        message="Dashboard counts match YAML",
    )


def check_coverage(
    yaml_ids: Set[str],
    md_ids: Set[str],
    pair: PairConfig,
) -> CheckResult:
    """Check for requirement IDs present in one file but not the other."""
    in_md_not_yaml = sorted(md_ids - yaml_ids)
    in_yaml_not_md = sorted(yaml_ids - md_ids)

    details: List[str] = []
    if in_md_not_yaml:
        for rid in in_md_not_yaml:
            details.append(f"  - {rid}: in MD but NOT in YAML")
    if in_yaml_not_md:
        for rid in in_yaml_not_md:
            details.append(f"  - {rid}: in YAML but NOT in MD")

    if details:
        return CheckResult(
            name="coverage",
            status="FAIL",
            message="Coverage drift detected",
            details=details,
        )

    count = len(yaml_ids & md_ids)
    return CheckResult(
        name="coverage",
        status="PASS",
        message=f"Coverage: all {count} requirements present in both",
    )


def check_version(
    yaml_version: Optional[str],
    md_version: Optional[str],
) -> CheckResult:
    """Compare version strings."""
    if yaml_version is None and md_version is None:
        return CheckResult(name="version", status="PASS", message="No version declared in either file")

    if yaml_version == md_version:
        return CheckResult(name="version", status="PASS", message=f"Versions match: {yaml_version}")

    return CheckResult(
        name="version",
        status="WARN",
        message=f"Version mismatch: YAML={yaml_version}, MD={md_version}",
    )


def check_status_alignment(
    yaml_id_to_status: Dict[str, str],
    md_id_to_status: Dict[str, str],
    pair: Optional[PairConfig] = None,
    resolve: bool = False,
) -> CheckResult:
    """Compare per-requirement status between YAML and MD.

    Only checks IDs present in both maps.  IDs without MD status are not
    treated as failures — they are noted as unchecked in the detail output.

    When *resolve* is True and mismatches exist, walks git history to
    determine which file's status was set more recently.
    """
    common_ids = sorted(set(yaml_id_to_status) & set(md_id_to_status))
    total_yaml = len(yaml_id_to_status)
    unchecked = total_yaml - len(common_ids)

    mismatch_tuples: List[Tuple[str, str, str]] = []
    mismatch_lines: List[str] = []
    for rid in common_ids:
        y_status = yaml_id_to_status[rid].lower()
        m_status = md_id_to_status[rid].lower()
        if y_status != m_status:
            mismatch_tuples.append((rid, y_status, m_status))
            mismatch_lines.append(f"  - {rid}: YAML={y_status}, MD={m_status}")

    details: List[str] = list(mismatch_lines)
    resolutions: List[StatusResolution] = []

    if mismatch_tuples and resolve and pair is not None:
        resolutions = resolve_status_mismatches(mismatch_tuples, pair)
        # Append resolution detail lines after each mismatch
        details = []
        for ml, sr in zip(mismatch_lines, resolutions):
            details.append(ml)
            if sr.yaml_commit:
                details.append(f"      -> YAML: \"{sr.yaml_status}\" since {sr.yaml_commit} ({sr.yaml_date})")
            else:
                details.append(f"      -> YAML: no trackable history")
            if sr.md_commit:
                details.append(f"      -> MD:   \"{sr.md_status}\" since {sr.md_commit} ({sr.md_date})")
            else:
                details.append(f"      -> MD:   no trackable history")
            if sr.likely_correct:
                details.append(f"      -> Likely correct: {sr.likely_correct.upper()} ({sr.reason})")
            else:
                details.append(f"      -> Unable to determine ({sr.reason})")

    if unchecked > 0:
        details.append(f"  ({unchecked} IDs have no explicit MD status — not checked)")

    if mismatch_tuples:
        return CheckResult(
            name="status-alignment",
            status="FAIL",
            message=f"Status alignment: {len(mismatch_tuples)} mismatch(es) in {len(common_ids)} checked",
            details=details,
            resolutions=resolutions,
        )

    return CheckResult(
        name="status-alignment",
        status="PASS",
        message=f"Status alignment: {len(common_ids)}/{total_yaml} checked, all match",
        details=details if unchecked > 0 else [],
    )


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def validate_pair(pair: PairConfig, verbose: bool = False, resolve: bool = False) -> PairResult:
    """Run all checks for a single YAML/MD pair."""
    result = PairResult(pair_name=pair.name)

    if not pair.yaml_path.is_file():
        result.skipped = f"YAML not found: {pair.yaml_path.relative_to(_REPO_ROOT)}"
        return result
    if not pair.md_path.is_file():
        result.skipped = f"MD not found: {pair.md_path.relative_to(_REPO_ROOT)}"
        return result

    yaml_result = parse_yaml_requirements(pair.yaml_path, pair.layer_display_names)
    md_result = parse_md_dashboard(pair.md_path)

    result.checks.append(check_dashboard_counts(yaml_result, md_result, pair))
    result.checks.append(
        check_coverage(
            set(yaml_result.id_to_status.keys()),
            parse_md_requirement_ids(pair.md_path, pair.id_prefix),
            pair,
        )
    )
    result.checks.append(check_version(yaml_result.version, md_result.version))

    md_statuses = parse_md_requirement_statuses(pair.md_path, pair.id_prefix)
    result.checks.append(
        check_status_alignment(yaml_result.id_to_status, md_statuses, pair=pair, resolve=resolve)
    )

    return result


def validate_md_only(pair: PairConfig_MDOnly) -> PairResult:
    """Report a markdown-only pair (no canonical YAML)."""
    result = PairResult(pair_name=pair.name)
    if not pair.md_path.is_file():
        result.skipped = f"MD not found: {pair.md_path.relative_to(_REPO_ROOT)}"
    else:
        rel = pair.md_path.relative_to(_REPO_ROOT)
        result.checks.append(
            CheckResult(
                name="yaml-missing",
                status="WARN",
                message=f"{rel} has no canonical YAML",
            )
        )
    return result


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def _status_tag(status: str) -> str:
    return f"[{status}]"


def print_text_report(results: List[PairResult], verbose: bool = False) -> None:
    for pr in results:
        print(f"\n=== {pr.pair_name}: YAML <-> MD Sync Check ===\n")
        if pr.skipped:
            print(f"  [SKIP] {pr.skipped}")
            continue
        for cr in pr.checks:
            print(f"  {_status_tag(cr.status)} {cr.message}")
            if cr.details and (verbose or cr.status == "FAIL"):
                for d in cr.details:
                    print(f"    {d}")

    # Summary
    fail_count = sum(
        1 for pr in results for cr in pr.checks if cr.status == "FAIL"
    )
    warn_count = sum(
        1 for pr in results for cr in pr.checks if cr.status == "WARN"
    )
    skip_count = sum(1 for pr in results if pr.skipped)
    total_pairs = len(results)

    parts: List[str] = []
    if fail_count:
        parts.append(f"{fail_count} FAIL")
    if warn_count:
        parts.append(f"{warn_count} WARN")
    if skip_count:
        parts.append(f"{skip_count} SKIP")
    if not parts:
        parts.append("all PASS")

    print(f"\n=== Summary: {', '.join(parts)} across {total_pairs} pairs ===")


def build_json_report(results: List[PairResult]) -> dict:
    report: dict = {"pairs": []}
    for pr in results:
        entry: dict = {"name": pr.pair_name}
        if pr.skipped:
            entry["skipped"] = pr.skipped
        else:
            entry["checks"] = []
            for cr in pr.checks:
                check: dict = {"name": cr.name, "status": cr.status, "message": cr.message}
                if cr.details:
                    check["details"] = cr.details
                if cr.resolutions:
                    check["resolutions"] = [
                        {
                            "req_id": sr.req_id,
                            "yaml_status": sr.yaml_status,
                            "md_status": sr.md_status,
                            "yaml_commit": sr.yaml_commit,
                            "yaml_date": sr.yaml_date,
                            "md_commit": sr.md_commit,
                            "md_date": sr.md_date,
                            "likely_correct": sr.likely_correct,
                            "reason": sr.reason,
                        }
                        for sr in cr.resolutions
                    ]
                entry["checks"].append(check)
        report["pairs"].append(entry)

    report["has_failures"] = any(
        cr.status == "FAIL" for pr in results for cr in pr.checks
    )
    return report


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate sync between canonical YAML requirements and companion markdown files."
    )
    parser.add_argument(
        "--pair",
        choices=[p.name for p in PAIR_REGISTRY],
        help="Check only the named pair (default: all)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Output results as JSON (for CI integration)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show per-requirement detail for all checks (not just failures)",
    )
    parser.add_argument(
        "--resolve",
        action="store_true",
        help="Walk git history to determine which file is likely correct for status mismatches",
    )
    args = parser.parse_args()

    pairs = PAIR_REGISTRY
    if args.pair:
        pairs = [p for p in PAIR_REGISTRY if p.name == args.pair]

    results: List[PairResult] = []
    for pair in pairs:
        if isinstance(pair, PairConfig_MDOnly):
            results.append(validate_md_only(pair))
        else:
            results.append(validate_pair(pair, verbose=args.verbose, resolve=args.resolve))

    if args.json_output:
        report = build_json_report(results)
        print(json.dumps(report, indent=2))
    else:
        print_text_report(results, verbose=args.verbose)

    has_failures = any(
        cr.status == "FAIL" for pr in results for cr in pr.checks
    )
    return 1 if has_failures else 0


if __name__ == "__main__":
    sys.exit(main())
