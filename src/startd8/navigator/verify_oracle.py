"""Verify-as-oracle — promote a det-req ``Verify:`` clause to a checkable acceptance oracle (REQ-08).

The det-req ``Verify:`` clause is already the one essential test artifact; today it is parsed as prose
(``det_req.py``). This module promotes it from displayed text to a **checkable acceptance oracle**:
parse (via ``det_req.parse_fr_lines_prefer_kit`` — imported, ``det_req.py`` unedited), **classify** by
*extracting the runnable span* (a real clause mixes a backtick command with a prose assertion — D-3),
and (opt-in, in the CLI) **evaluate** the command-shaped ones to report per-FR pass/fail.

Honesty boundary (D-3): a ``pass`` asserts only that the extracted command exited 0 — NOT that the prose
assertion holds; the ``assertion_text`` rides alongside as the human-checkable residue. Execution is
default-inert and, under ``--run-oracle``, guarded by a **read-only ``startd8 navigator`` subcommand
allow-list + no-shell (argv)** — network-denial for the child is not argv-enforceable and is not claimed
(R1-F6).
"""
from __future__ import annotations

import re
import shlex
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

from .det_req import parse_fr_lines_prefer_kit

# Verdict kinds (FR-4 classification).
KIND_COMMAND = "command"
KIND_ASSERTION = "assertion"
KIND_MANUAL = "manual"

# Verdict outcomes (FR-5 evaluation).
VERDICT_PASS = "pass"
VERDICT_FAIL = "fail"
VERDICT_SKIP = "skip"
VERDICT_ERROR = "error"

# Allow-listed leading verbs for a runnable span (R1-F4). ``$`` is stripped as a shell prompt marker.
_ALLOWED_VERBS = frozenset({"startd8"})

# The closed placeholder grammar (R1-F5): a span carrying any of these is NOT runnable → ``manual``.
_PLACEHOLDER_PATTERNS: Tuple[re.Pattern, ...] = (
    re.compile(r"<[^>]*>"),        # <…> angle
    re.compile(r"\.\.\."),         # ... ellipsis (ascii)
    re.compile(r"…"),         # … ellipsis (unicode)
    re.compile(r"\$\{[^}]*\}"),    # ${…} shell var (braced)
    re.compile(r"\$[A-Za-z_][A-Za-z0-9_]*"),  # $WORD shell var
    re.compile(r"\{[^}]*\}"),      # {…} brace
    re.compile(r"\[[^\]]*\]"),     # […] bracket
)

# Command-joining operators that make a span multi-command (R1-F4).
_JOIN_RE = re.compile(r"(?<!&)&&(?!&)|(?<!\|)\|\|?(?!\|)|;")

# Backtick-quoted spans in a clause (single backtick pairs).
_BACKTICK_RE = re.compile(r"`([^`]+)`")

# Read-only ``startd8 navigator`` subcommands that write nothing (R1-F7 / D-6).
_READONLY_NAV_SUBCOMMANDS = frozenset({"build", "view-definition", "verify", "govern"})
# Flags that make an otherwise read-only navigator invocation side-effecting (write to disk).
_WRITE_FLAGS = frozenset({"--out", "--fix"})
# The self-exec token prefix (R1-S7) — refuse re-entrant ``startd8 navigator verify`` execution.
_SELF_EXEC_ARGV = ("startd8", "navigator", "verify")

_DEFAULT_ORACLE_TIMEOUT = 60


@dataclass(frozen=True)
class OracleDescriptor:
    """A typed per-FR oracle descriptor produced by :func:`classify` (FR-4)."""

    fr_id: str
    kind: str  # command | assertion | manual
    command_argv: Optional[Tuple[str, ...]] = None
    assertion_text: str = ""
    reason: str = ""


@dataclass(frozen=True)
class OracleVerdict:
    """A per-FR verdict produced by :func:`evaluate` (FR-5)."""

    fr_id: str
    kind: str
    verdict: str  # pass | fail | skip | error
    reason: str = ""
    assertion_text: str = ""
    command_argv: Tuple[str, ...] = field(default_factory=tuple)


def _has_placeholder(span: str) -> bool:
    return any(p.search(span) for p in _PLACEHOLDER_PATTERNS)


def _is_multi_command(span: str) -> bool:
    return bool(_JOIN_RE.search(span))


def _argv_of_span(span: str) -> Optional[Tuple[str, ...]]:
    """Tokenise a runnable span to argv, dropping a leading ``$`` prompt; ``None`` if untokenisable."""
    s = span.strip()
    if s.startswith("$"):
        s = s[1:].strip()
    try:
        argv = tuple(shlex.split(s))
    except ValueError:
        return None
    return argv or None


def _classify_clause(verify: str) -> Tuple[str, Optional[Tuple[str, ...]], str]:
    """Classify a raw ``Verify:`` clause → ``(kind, command_argv, reason)`` (FR-4).

    Extracts the runnable span rather than bucketing the whole clause: exactly ONE backtick span whose
    first token is an allow-listed verb and which carries no closed-set placeholder → ``command``. Two
    or more runnable spans (or a ``;``/``&&``/``|``-joined span) → ``manual`` ("multi-command"). A
    placeholder in the span → ``manual`` ("unresolved placeholder"). No runnable span → ``assertion``.
    """
    spans = _BACKTICK_RE.findall(verify)
    # Candidate runnable spans: those whose first token is an allow-listed verb.
    runnable: List[Tuple[str, Tuple[str, ...]]] = []
    for span in spans:
        argv = _argv_of_span(span)
        if not argv:
            continue
        verb = argv[0]
        if verb in _ALLOWED_VERBS:
            runnable.append((span, argv))

    if not runnable:
        return KIND_ASSERTION, None, "prose acceptance (no runnable span)"

    if len(runnable) >= 2:
        return KIND_MANUAL, None, "multi-command"

    span, argv = runnable[0]
    if _is_multi_command(span):
        return KIND_MANUAL, None, "multi-command"
    if _has_placeholder(span):
        return KIND_MANUAL, None, "unresolved placeholder"
    return KIND_COMMAND, argv, "single allow-listed command span"


def classify(requirements: Path) -> List[OracleDescriptor]:
    """Parse a det-req doc and classify each FR's ``Verify:`` clause into an :class:`OracleDescriptor`.

    Reads FRs via ``det_req.parse_fr_lines_prefer_kit`` (imported — ``det_req.py`` unedited). The prose
    ``Verify:`` text is retained in ``assertion_text`` on every descriptor as the human-checkable residue
    (D-3), regardless of ``kind``.
    """
    text = Path(requirements).read_text(encoding="utf-8")
    frs = parse_fr_lines_prefer_kit(text)
    descriptors: List[OracleDescriptor] = []
    for fr in frs:
        fr_id = str(fr.get("id", ""))
        verify = str(fr.get("verify") or "")
        kind, argv, reason = _classify_clause(verify)
        descriptors.append(OracleDescriptor(
            fr_id=fr_id,
            kind=kind,
            command_argv=argv,
            assertion_text=verify.strip(),
            reason=reason,
        ))
    return descriptors


def _flag_name(token: str) -> str:
    """The flag name of a token, normalising the ``--flag=value`` form to ``--flag``.

    Click/Typer accept both ``--out x`` and ``--out=x``; a guard that only matches the bare token form
    is evadable via the ``=`` form (an authored clause could smuggle ``--out=/tmp/x`` past a write-flag
    check). Splitting on the first ``=`` closes that gap.
    """
    return token.split("=", 1)[0]


def _is_self_exec(argv: Sequence[str]) -> bool:
    """R1-S7: refuse a re-entrant ``startd8 navigator verify …`` on an argv-token prefix match."""
    return tuple(argv[:3]) == _SELF_EXEC_ARGV


def _is_readonly_allowlisted(argv: Sequence[str]) -> Tuple[bool, str]:
    """R1-F7 / D-6: gate the *subcommand*, not just the verb.

    Only a read-only ``startd8 navigator <sub>`` invocation that writes nothing runs. A write flag, a
    non-``navigator`` verb (``generate`` / ``deploy`` / …), or a non-``startd8`` command → not allowed.
    Returns ``(allowed, reason)``; ``reason`` is set only when NOT allowed.
    """
    if not argv:
        return False, "non-allowlisted"
    if argv[0] not in _ALLOWED_VERBS:
        return False, "non-allowlisted"
    if _is_self_exec(argv):
        return False, "self-exec"
    if len(argv) < 2 or argv[1] != "navigator":
        return False, "non-allowlisted"
    if len(argv) < 3 or argv[2] not in _READONLY_NAV_SUBCOMMANDS:
        return False, "non-allowlisted"
    # Normalise ``--flag=value`` before matching so the ``=`` form can't smuggle a write flag past this.
    if any(_flag_name(flag) in _WRITE_FLAGS for flag in argv[3:]):
        return False, "side-effecting"
    return True, ""


def _referenced_missing_path(argv: Sequence[str]) -> Optional[str]:
    """Return a referenced input path that is absent on disk (R1-S5) → an ``error`` verdict.

    Inspects the value following ``--requirements`` / ``--nodes-json`` / ``--capability-index`` /
    ``--dir`` / ``--from`` — the read-only navigator subcommands' input-path flags. A relative path is
    resolved against the current working directory. A flag whose value is present is fine.
    """
    input_flags = {"--requirements", "--nodes-json", "--capability-index", "--dir", "--from"}
    tokens = list(argv)
    for i, tok in enumerate(tokens):
        # Support both ``--flag value`` (value in the next token) and ``--flag=value`` (same token).
        if "=" in tok and _flag_name(tok) in input_flags:
            value = tok.split("=", 1)[1]
            if value and not Path(value).exists():
                return value
        elif tok in input_flags and i + 1 < len(tokens):
            if not Path(tokens[i + 1]).exists():
                return tokens[i + 1]
    return None


def evaluate(
    descriptors: Sequence[OracleDescriptor],
    *,
    run_oracle: bool = False,
    timeout: int = _DEFAULT_ORACLE_TIMEOUT,
) -> List[OracleVerdict]:
    """Evaluate oracle descriptors into per-FR verdicts (FR-5).

    Default inert (``run_oracle=False``): every descriptor → ``skip``, **no subprocess** is spawned.
    Under ``run_oracle=True`` only ``command``-kind descriptors whose argv passes the read-only
    navigator-subcommand allow-list are executed via ``subprocess.run(argv, shell=False, timeout=…)``;
    ``pass`` = the extracted command exited 0, ``fail`` = non-zero. A timeout → a distinct ``fail``
    ("timeout"); a missing referenced input path → a distinct ``error`` ("missing input"); a
    non-allowlisted / side-effecting / self-exec command → ``skip``. ``assertion``/``manual``
    descriptors are never executed (``skip``).
    """
    verdicts: List[OracleVerdict] = []
    for d in descriptors:
        argv = tuple(d.command_argv or ())
        base_kwargs = dict(
            fr_id=d.fr_id, kind=d.kind, assertion_text=d.assertion_text, command_argv=argv,
        )
        if not run_oracle:
            verdicts.append(OracleVerdict(verdict=VERDICT_SKIP, reason="inert (no --run-oracle)", **base_kwargs))
            continue
        if d.kind != KIND_COMMAND or not argv:
            verdicts.append(OracleVerdict(verdict=VERDICT_SKIP, reason=d.reason or "not a command", **base_kwargs))
            continue
        allowed, deny_reason = _is_readonly_allowlisted(argv)
        if not allowed:
            verdicts.append(OracleVerdict(verdict=VERDICT_SKIP, reason=deny_reason, **base_kwargs))
            continue
        missing = _referenced_missing_path(argv)
        if missing is not None:
            verdicts.append(OracleVerdict(
                verdict=VERDICT_ERROR, reason=f"missing input: {missing}", **base_kwargs))
            continue
        try:
            proc = subprocess.run(  # noqa: S603 — argv, shell=False, allow-listed read-only subcommand
                list(argv),
                shell=False,
                capture_output=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            verdicts.append(OracleVerdict(verdict=VERDICT_FAIL, reason="timeout", **base_kwargs))
            continue
        except OSError as exc:
            verdicts.append(OracleVerdict(verdict=VERDICT_ERROR, reason=f"exec error: {exc}", **base_kwargs))
            continue
        if proc.returncode == 0:
            verdicts.append(OracleVerdict(verdict=VERDICT_PASS, reason="exit 0", **base_kwargs))
        else:
            verdicts.append(OracleVerdict(
                verdict=VERDICT_FAIL, reason=f"exit {proc.returncode}", **base_kwargs))
    return verdicts


def aggregate_exit_code(verdicts: Sequence[OracleVerdict]) -> int:
    """FR-5 CI gate: 0 iff no ``fail``/``error`` verdict, non-zero otherwise."""
    return 1 if any(v.verdict in (VERDICT_FAIL, VERDICT_ERROR) for v in verdicts) else 0


def verdict_to_dict(v: OracleVerdict) -> dict:
    """A JSON-safe per-FR verdict row (FR-7 ``--format json``)."""
    return {
        "fr_id": v.fr_id,
        "kind": v.kind,
        "verdict": v.verdict,
        "reason": v.reason,
        "assertion_text": v.assertion_text,
        "command_argv": list(v.command_argv),
    }
