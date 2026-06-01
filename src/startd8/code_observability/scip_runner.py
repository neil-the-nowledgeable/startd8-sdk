"""scip-typescript runner (CKG Phase 1, REQ-CKG-200/230).

Runs ``scip-typescript index`` over the target project as a per-batch subprocess and
returns the path to the produced index, or ``None`` (advisory degrade, never raises)
when the tool is missing, the project is unindexable, or config is corrupt.

Safety (R2-S6/R4-S3): ``cwd=project_root``, no ``shell=True``, wall-clock timeout,
``project_root`` must resolve under ``workspace_root`` when given, and
``package.json``/``tsconfig.json`` are pre-validated as parseable (JSONC-tolerant)
before invoking — a batch that corrupts them degrades to advisory rather than crashing
the indexer.

NFR-2: this is invoked once per **batch** (at the postmortem hook), not per feature.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import List, Optional

from startd8.logging_config import get_logger
from startd8.utils.jsonc import loads_jsonc

logger = get_logger(__name__)

DEFAULT_TIMEOUT_S = 300
_TOOL = "scip-typescript"


def _config_parses(path: Path) -> bool:
    """True if the JSON/JSONC config parses (or is absent). False only on corruption.

    JSONC-tolerant (comments + trailing commas) so a valid tsconfig — which contains
    ``/*`` inside path globs and may carry comments — is never mis-judged as corrupt.
    """
    if not path.is_file():
        return True
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return True  # unreadable is not "corrupt content"; let the tool decide
    try:
        loads_jsonc(text)
        return True
    except ValueError:  # json.JSONDecodeError is a ValueError
        return False


def _resolve_tool_cmd(tool_cmd: Optional[List[str]]) -> Optional[List[str]]:
    """Resolve the indexer command, or None if unavailable."""
    if tool_cmd:
        return tool_cmd
    if shutil.which(_TOOL):
        return [_TOOL]
    if shutil.which("npx"):
        # --no-install: do not auto-download in a pipeline run; absence -> graceful None.
        return ["npx", "--no-install", "@sourcegraph/scip-typescript"]
    return None


def run_index(
    project_root: str | Path,
    *,
    output: Optional[str | Path] = None,
    timeout_s: int = DEFAULT_TIMEOUT_S,
    workspace_root: Optional[str | Path] = None,
    tool_cmd: Optional[List[str]] = None,
) -> Optional[Path]:
    """Index ``project_root`` with scip-typescript; return the index path or ``None``.

    Never raises: any failure (missing tool, corrupt config, path escape, timeout,
    non-zero exit) logs a warning and returns ``None`` so SCIP-backed checks degrade
    to advisory (REQ-CKG-230).
    """
    root = Path(project_root).resolve()
    if not root.is_dir():
        logger.warning("scip: project_root %s is not a directory — skipping index", root)
        return None

    if workspace_root is not None:
        ws = Path(workspace_root).resolve()
        if not (root == ws or ws in root.parents):
            logger.warning("scip: project_root %s escapes workspace %s — refusing", root, ws)
            return None

    if not _config_parses(root / "package.json"):
        logger.warning("scip: package.json in %s is not parseable — degrading to advisory", root)
        return None
    if not _config_parses(root / "tsconfig.json"):
        logger.warning("scip: tsconfig.json in %s is not parseable — degrading to advisory", root)
        return None

    cmd = _resolve_tool_cmd(tool_cmd)
    if cmd is None:
        logger.warning("scip: scip-typescript not available (PATH/npx) — SCIP checks advisory")
        return None

    out_path = Path(output).resolve() if output else (root / "index.scip")
    full = [*cmd, "index", "--output", str(out_path)]
    try:
        proc = subprocess.run(  # noqa: S603 — fixed argv, no shell
            full,
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
        )
    except subprocess.TimeoutExpired:
        logger.warning("scip: index timed out after %ss in %s — advisory", timeout_s, root)
        return None
    except OSError as exc:
        logger.warning("scip: failed to launch %s (%s) — advisory", cmd, exc)
        return None

    if proc.returncode != 0 or not out_path.is_file():
        logger.warning(
            "scip: index exit=%s, output_present=%s in %s — advisory. stderr: %s",
            proc.returncode, out_path.is_file(), root, (proc.stderr or "")[-500:],
        )
        return None
    return out_path
