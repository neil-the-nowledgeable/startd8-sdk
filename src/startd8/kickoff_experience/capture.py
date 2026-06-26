"""M6 — Value write-back path (the riskiest surface).

Captures a single field value into ``docs/kickoff/inputs/*.yaml`` and applies it through the
concierge safe-writer (``apply_write_plan``) at human/CLI privilege. Everything here is built
around the load-bearing risks the 6 CRP rounds surfaced:

* **Merge fidelity (R1-S1).** ``ruamel.yaml`` is not a dependency, so we do a **targeted line-range
  splice**: locate the target dotted key and replace only its scalar value, preserving every other
  byte — comments, key ordering, blank lines, inline annotations. A load→dump cycle (which would
  drop comments and reorder keys) is never used.
* **Bounded read exception (FR-NEW-2).** Unlike ``concierge/writes.py`` (which by policy never reads
  consumer content), this writer is *explicitly authorized* to read exactly ONE file — the target
  ``inputs/<domain>.yaml`` — and only to merge a single key. That exception is isolated to this
  module so the concierge read-disclosure bound is not weakened.
* **Allow-list + traversal guard (R1-F6/R1-S8).** A ``value_path`` is honored only if it is in the
  M3 config's ``allowed_value_paths()``; the resolved write target must be a known inputs file with a
  dotted (non-traversing) key. A surface-supplied path can never redirect the write.
* **Per-field round-trip gate (FR-8 / FR-NEW-3).** After splicing, the candidate file must re-parse;
  failure is attributed to the captured ``value_path`` (not a whole-file abort).
* **Concurrency precondition (R1-S6).** The plan records the target file's sha256 at read time;
  ``apply_capture`` refuses if the file changed on disk since (stale-read clobber protection),
  emitting a typed code for the conflict-recovery path (R4-F1).
* **Typed reason codes (R4-F4).** Every refusal carries a stable :class:`CaptureCode` so surfaces,
  tests, and telemetry share one vocabulary.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

import yaml

from .manifest import KickoffExperienceConfig, WriteTarget, default_config


class CaptureCode:
    """Stable typed reason codes for capture outcomes (R4-F4)."""

    OK = "ok"
    VALUE_PATH_NOT_ALLOWED = "value_path_not_allowed"
    UNSAFE_VALUE_PATH = "unsafe_value_path"
    TARGET_FILE_MISSING = "target_file_missing"
    KEY_NOT_FOUND = "key_not_found"
    ROUND_TRIP_FAILED = "round_trip_failed"
    STALE_FILE = "stale_file"
    DEFERRED_VALIDATION = "deferred_validation"
    WRITE_REFUSED = "write_refused"


class CaptureError(ValueError):
    """A capture refusal carrying a stable :class:`CaptureCode` and a user-safe message."""

    def __init__(self, code: str, message: str, *, value_path: Optional[str] = None) -> None:
        super().__init__(message)
        self.code = code
        self.value_path = value_path


# --- targeted YAML line splice (merge fidelity R1-S1) ------------------------------------------


def _leading_spaces(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _is_blank_or_comment(line: str) -> bool:
    s = line.strip()
    return not s or s.startswith("#")


def _key_of(line: str) -> str:
    stripped = line.strip()
    return stripped.split(":", 1)[0].strip() if ":" in stripped else ""


def _block_end(lines: List[str], start: int, parent_indent: int) -> int:
    """Index where the child block of a key at *parent_indent* ends (indent <= parent)."""
    j = start
    while j < len(lines):
        if not _is_blank_or_comment(lines[j]) and _leading_spaces(lines[j]) <= parent_indent:
            break
        j += 1
    return j


def locate_key_line(lines: List[str], dotted_key: str) -> Optional[int]:
    """Return the 0-based index of the line declaring *dotted_key*, or None if absent.

    Walks indentation-nested mapping keys (``a.b.c``). Direct children of a parent share one indent.
    """
    segments = dotted_key.split(".")
    lo, hi = 0, len(lines)
    parent_indent = -1
    idx: Optional[int] = None
    for depth, seg in enumerate(segments):
        idx = None
        target_indent: Optional[int] = None
        j = lo
        while j < hi:
            line = lines[j]
            if _is_blank_or_comment(line):
                j += 1
                continue
            ind = _leading_spaces(line)
            if ind <= parent_indent:
                break
            if target_indent is None:
                target_indent = ind
            if ind == target_indent and _key_of(line) == seg:
                idx = j
                break
            j += 1
        if idx is None or target_indent is None:
            return None
        if depth == len(segments) - 1:
            return idx
        parent_indent = target_indent
        lo = idx + 1
        hi = _block_end(lines, idx + 1, parent_indent)
    return idx


_SCALAR_LINE_RE = re.compile(r"^(?P<head>\s*[^:#]+:)(?P<gap>[ \t]*)(?P<val>.*?)(?P<comment>\s+#.*)?$")


def _format_scalar(value: str) -> str:
    """Render *value* as a YAML scalar, quoting only when needed (preserve plain when safe)."""
    if value == "":
        return '""'
    needs_quote = (
        value != value.strip()
        or value[0] in "#&*!|>%@`\"'{}[],"
        or ":" in value
        or value.lower() in {"true", "false", "null", "yes", "no", "~"}
        or value.startswith("$")
    )
    if needs_quote:
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    return value


@dataclass(frozen=True)
class SpliceResult:
    text: str
    line_index: int
    old_value: str
    new_line: str


def splice_yaml_value(text: str, dotted_key: str, new_value: str) -> SpliceResult:
    """Replace only the scalar value of *dotted_key*, preserving every other byte (R1-S1).

    Raises :class:`CaptureError` (KEY_NOT_FOUND) if the key path is not present.
    """
    # Preserve the original newline shape: operate on lines without the terminators.
    had_trailing_nl = text.endswith("\n")
    lines = text.split("\n")
    idx = locate_key_line(lines, dotted_key)
    if idx is None:
        raise CaptureError(CaptureCode.KEY_NOT_FOUND, f"key {dotted_key!r} not found in target file")
    line = lines[idx]
    m = _SCALAR_LINE_RE.match(line)
    if not m:
        raise CaptureError(
            CaptureCode.KEY_NOT_FOUND, f"key {dotted_key!r} is not a scalar assignment"
        )
    head = m.group("head")
    comment = m.group("comment") or ""
    old_value = (m.group("val") or "").strip()
    # Refuse a mapping/sequence parent (empty inline value followed by an indented child block):
    # splicing a scalar onto it would silently clobber the whole nested block.
    if old_value == "":
        this_indent = _leading_spaces(line)
        for nxt in lines[idx + 1 :]:
            if _is_blank_or_comment(nxt):
                continue
            if _leading_spaces(nxt) > this_indent:
                raise CaptureError(
                    CaptureCode.KEY_NOT_FOUND,
                    f"key {dotted_key!r} is a mapping/block, not a scalar — refusing to clobber it",
                )
            break
    new_line = f"{head} {_format_scalar(new_value)}{comment}"
    new_lines = list(lines)
    new_lines[idx] = new_line
    new_text = "\n".join(new_lines)
    if had_trailing_nl and not new_text.endswith("\n"):
        new_text += "\n"
    return SpliceResult(text=new_text, line_index=idx, old_value=old_value, new_line=new_line)


# --- round-trip gate (FR-8 / FR-NEW-3) ---------------------------------------------------------


def _resolve_dotted(data: object, dotted_key: str) -> Tuple[bool, object]:
    cur = data
    for seg in dotted_key.split("."):
        if not isinstance(cur, dict) or seg not in cur:
            return (False, None)
        cur = cur[seg]
    return (True, cur)


def _round_trip(candidate_text: str, dotted_key: str, value_path: str) -> None:
    """FR-8: the spliced file must re-parse AND the captured key must resolve to the written value.

    For input-domain scalar fields there is no cross-entity interaction (R1-S4 is a no-op here), so a
    failure is unambiguously attributable to *value_path*. The cross-field deferred path is reserved
    for the prose/entity capture surface and is signalled via ``CaptureCode.DEFERRED_VALIDATION``.
    """
    try:
        data = yaml.safe_load(candidate_text)
    except yaml.YAMLError as exc:
        raise CaptureError(
            CaptureCode.ROUND_TRIP_FAILED,
            f"capture would not re-parse: {exc}",
            value_path=value_path,
        )
    found, _ = _resolve_dotted(data or {}, dotted_key)
    if not found:
        raise CaptureError(
            CaptureCode.ROUND_TRIP_FAILED,
            f"captured key {dotted_key!r} did not survive the splice",
            value_path=value_path,
        )


# --- plan + apply ------------------------------------------------------------------------------


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class CapturePlan:
    """A previewable, applyable single-field capture (R2-S1 preview is built from this)."""

    value_path: str
    file: str                      # relative to docs/kickoff/inputs/
    key: str                       # dotted key within the file
    old_value: str
    new_value: str
    line_index: int                # 0-based line touched
    base_sha: str                  # sha256 of the target file at read time (concurrency, R1-S6)
    candidate_text: str            # the full spliced file content
    provenance_default: str        # the field's provenance (NR-2 disclosure)

    def preview(self) -> dict:
        """The field-scoped diff a surface renders before apply (R2-S1)."""
        return {
            "value_path": self.value_path,
            "file": f"docs/kickoff/inputs/{self.file}",
            "key": self.key,
            "old_value": self.old_value,
            "new_value": self.new_value,
            "line_index": self.line_index,
            "provenance_default": self.provenance_default,
        }


def _inputs_path(project_root: Path, file: str) -> Path:
    return Path(project_root) / "docs" / "kickoff" / "inputs" / file


def build_capture_plan(
    project_root: str | Path,
    value_path: str,
    new_value: str,
    *,
    config: Optional[KickoffExperienceConfig] = None,
) -> CapturePlan:
    """Plan a single-field capture (no write). Validates, reads ONE inputs file, splices, gates.

    Raises :class:`CaptureError` with a stable code on any refusal.
    """
    cfg = config or default_config()

    # Allow-list + traversal guard (R1-F6/R1-S8) — before any filesystem touch.
    if value_path not in cfg.allowed_value_paths():
        raise CaptureError(
            CaptureCode.VALUE_PATH_NOT_ALLOWED,
            f"value_path {value_path!r} is not a capturable field",
            value_path=value_path,
        )
    field = cfg.field_by_value_path(value_path)
    # The allow-list guarantees this, but guard explicitly so the invariant holds under `python -O`
    # (which strips asserts) and against any future allow-list/field-lookup skew.
    if field is None or field.write_target is None:
        raise CaptureError(
            CaptureCode.VALUE_PATH_NOT_ALLOWED,
            f"value_path {value_path!r} has no write target",
            value_path=value_path,
        )
    target: WriteTarget = field.write_target
    if (
        ".." in target.key
        or "/" in target.key
        or ".." in target.file
        or "/" in target.file
        or "\\" in target.file
    ):
        raise CaptureError(
            CaptureCode.UNSAFE_VALUE_PATH,
            f"resolved write target {target.as_tuple()} is unsafe",
            value_path=value_path,
        )

    root = Path(project_root).expanduser()
    target_path = _inputs_path(root, target.file)
    if not target_path.is_file():
        raise CaptureError(
            CaptureCode.TARGET_FILE_MISSING,
            f"target inputs file is missing: docs/kickoff/inputs/{target.file}",
            value_path=value_path,
        )

    # The ONE authorized consumer read (FR-NEW-2, bounded to this file).
    original = target_path.read_text(encoding="utf-8")
    base_sha = _sha256(original)

    spliced = splice_yaml_value(original, target.key, new_value)
    _round_trip(spliced.text, target.key, value_path)  # FR-8 gate

    return CapturePlan(
        value_path=value_path,
        file=target.file,
        key=target.key,
        old_value=spliced.old_value,
        new_value=new_value,
        line_index=spliced.line_index,
        base_sha=base_sha,
        candidate_text=spliced.text,
        provenance_default=field.provenance_default,
    )


@dataclass(frozen=True)
class CaptureResult:
    code: str
    value_path: str
    file: str
    applied: bool


def apply_capture(project_root: str | Path, plan: CapturePlan) -> CaptureResult:
    """Apply a previously built plan through the safe-writer, with a concurrency precondition.

    Refuses with ``STALE_FILE`` if the target changed on disk since the plan was built (R1-S6);
    surfaces drive the R4-F1 recovery path (re-read → new preview) from that code.
    """
    from ..concierge.safe_write import (
        ACTION_OVERWRITE,
        PlannedWrite,
        SafeWriteError,
        apply_write_plan,
    )

    root = Path(project_root).expanduser()
    target_path = _inputs_path(root, plan.file)
    if not target_path.is_file():
        raise CaptureError(CaptureCode.TARGET_FILE_MISSING, "target vanished before apply",
                           value_path=plan.value_path)

    # Concurrency precondition (R1-S6): the file must be byte-identical to what we read.
    current_sha = _sha256(target_path.read_text(encoding="utf-8"))
    if current_sha != plan.base_sha:
        raise CaptureError(
            CaptureCode.STALE_FILE,
            "target file changed on disk since the value was previewed; re-read and re-preview",
            value_path=plan.value_path,
        )

    rel_dest = f"docs/kickoff/inputs/{plan.file}"
    write = PlannedWrite(
        path=rel_dest,
        content=plan.candidate_text,
        action=ACTION_OVERWRITE,
    )
    # The safe-writer enforces confinement (rejects symlinked/.. roots) and reports per-file
    # blocks/errors. Surface both as a typed CaptureError so callers never see a raw write error.
    try:
        result = apply_write_plan(root, [write], force=True)
    except SafeWriteError as exc:
        raise CaptureError(CaptureCode.WRITE_REFUSED, f"safe-writer refused the write: {exc}",
                           value_path=plan.value_path)
    if not result.ok:
        detail = (result.blocked or result.errors or [{"reason": "unknown"}])[0]
        raise CaptureError(
            CaptureCode.WRITE_REFUSED,
            f"write did not complete: {detail}",
            value_path=plan.value_path,
        )
    from .telemetry import EV_FIELD_CAPTURED, emit

    emit(EV_FIELD_CAPTURED, value_path=plan.value_path, file=rel_dest, code=CaptureCode.OK)
    return CaptureResult(
        code=CaptureCode.OK, value_path=plan.value_path, file=rel_dest, applied=True
    )
