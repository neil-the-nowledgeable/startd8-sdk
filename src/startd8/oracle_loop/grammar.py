"""Runnable ``Verify:`` grammar for generated apps (FR-2, grammar id ``a1``).

This module owns its OWN parser, deliberately distinct from
``navigator/verify_oracle.classify()`` — whose ``_classify_clause`` only promotes a ``startd8``-verb
span to ``command`` (``_ALLOWED_VERBS = {"startd8"}``), so a ``pytest``/``probe`` clause classifies
as ``assertion`` there and would yield ZERO runnable descriptors (REQ D-2 / R1-F2). FR-1's runner
extracts through THIS parser, never ``classify()``.

A ``Verify:`` clause resolves to exactly one :class:`ParsedClause` of kind:

  - ``one-shot`` — a backtick span whose first token is a runnable verb (``pytest`` / ``python`` /
    a resolved generated console-script). Runs via ``run_sandboxed``; pass = rc 0.
  - ``service`` — the keyword ``probe`` + a backtick micro-grammar ``METHOD /path [body={json}] ->
    STATUS`` parsed into a DATA-ONLY :class:`ProbeSpec` the runner renders into a FIXED loopback
    httpx call. Clause text is NEVER executed (the ``client(port)`` callback runs host-side —
    ``sandbox.py:334`` — so a clause-derived client would be an un-sandboxed host RCE, R1-F3).
  - ``assertion`` — prose acceptance (no runnable span). Human-gate residue.
  - ``manual`` — a runnable-looking span that is rejected (multi-command / injection / malformed).

The grammar is described for humans in ``docs/design/oracle-generation-loop/VERIFY-GRAMMAR.md``.
"""

from __future__ import annotations

import json
import re
import shlex
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

# Clause kinds (FR-2). ``one-shot``/``service`` are runnable; the rest is residue.
KIND_ONESHOT = "one-shot"
KIND_SERVICE = "service"
KIND_ASSERTION = "assertion"
KIND_MANUAL = "manual"

RUNNABLE_KINDS = frozenset({KIND_ONESHOT, KIND_SERVICE})

# Runnable leading verbs for a one-shot span. A bare token (no ``/`` and no ``.``) that is not one of
# these is treated as a candidate generated console-script; the runner (FR-1) resolves it.
_ONESHOT_VERBS = frozenset({"pytest", "python", "python3"})

# The closed HTTP method set for a service probe.
_PROBE_METHODS = frozenset({"GET", "POST", "PUT", "PATCH", "DELETE"})

# Backtick-quoted spans in a clause (single backtick pairs).
_BACKTICK_RE = re.compile(r"`([^`]+)`")

# Command-joining operators that make a one-shot span multi-command (rejected → manual).
_JOIN_RE = re.compile(r"(?<!&)&&(?!&)|(?<!\|)\|\|?(?!\|)|;")

# ``probe`` keyword immediately preceding a backtick span (case-insensitive keyword).
_PROBE_KEYWORD_RE = re.compile(r"\bprobe\b\s*`([^`]+)`", re.IGNORECASE)

# The probe micro-grammar: METHOD /path [body={json}] -> STATUS
_PROBE_RE = re.compile(
    r"^\s*(?P<method>[A-Z]+)\s+"
    r"(?P<path>/\S*)\s*"
    r"(?:body=(?P<body>\{.*\})\s*)?"
    r"->\s*(?P<status>\d{3})\s*$"
)


@dataclass(frozen=True)
class ProbeSpec:
    """A DATA-ONLY loopback HTTP probe (never executable code lifted from a clause)."""

    method: str
    path: str
    expected_status: int
    body: Optional[dict] = None


@dataclass(frozen=True)
class ParsedClause:
    """The parse of one FR's ``Verify:`` clause (FR-2)."""

    fr_id: str
    kind: str  # one-shot | service | assertion | manual
    assertion_text: str = ""
    reason: str = ""
    # one-shot payload
    command_argv: Tuple[str, ...] = field(default_factory=tuple)
    is_console_script: bool = False
    # service payload
    probe: Optional[ProbeSpec] = None

    @property
    def is_runnable(self) -> bool:
        return self.kind in RUNNABLE_KINDS


def _is_multi_command(span: str) -> bool:
    return bool(_JOIN_RE.search(span))


def _argv_of_span(span: str) -> Optional[Tuple[str, ...]]:
    """Tokenise a span to argv, dropping a leading ``$`` prompt; ``None`` if untokenisable."""
    s = span.strip()
    if s.startswith("$"):
        s = s[1:].strip()
    try:
        argv = tuple(shlex.split(s))
    except ValueError:
        return None
    return argv or None


def _parse_probe(span: str) -> Optional[ProbeSpec]:
    """Parse a probe micro-grammar span into a DATA-ONLY :class:`ProbeSpec`, or ``None``.

    Accepts ONLY the fixed token shape ``METHOD /path [body={json}] -> STATUS``. Any injection
    (a lambda, a ``client=``, backticked python, shell text) fails the regex and returns ``None`` →
    the clause becomes ``manual``. There is no path from clause text to an executable object.
    """
    m = _PROBE_RE.match(span)
    if not m:
        return None
    method = m.group("method")
    if method not in _PROBE_METHODS:
        return None
    status = int(m.group("status"))
    if not (100 <= status <= 599):
        return None
    body_raw = m.group("body")
    body: Optional[dict] = None
    if body_raw is not None:
        try:
            parsed = json.loads(body_raw)
        except (ValueError, TypeError):
            return None
        if not isinstance(parsed, dict):
            return None
        body = parsed
    return ProbeSpec(
        method=method,
        path=m.group("path"),
        expected_status=status,
        body=body,
    )


def parse_verify_clause(fr_id: str, verify: str) -> ParsedClause:
    """Parse a raw ``Verify:`` clause into a typed :class:`ParsedClause` (FR-2).

    Precedence: a ``probe`` service clause is checked first (it also contains a backtick span), then
    the one-shot form, else prose ``assertion``. A runnable-looking clause that violates the closed
    convention (multi-command, injection, malformed probe) becomes ``manual`` residue — never
    silently executed.
    """
    text = (verify or "").strip()

    # --- service probe: keyword ``probe`` immediately before a backtick micro-grammar span ---
    pm = _PROBE_KEYWORD_RE.search(text)
    if pm is not None:
        span = pm.group(1)
        probe = _parse_probe(span)
        if probe is not None:
            return ParsedClause(
                fr_id=fr_id,
                kind=KIND_SERVICE,
                assertion_text=text,
                reason="service probe",
                probe=probe,
            )
        # ``probe`` present but the span is not a valid micro-grammar → rejected residue.
        return ParsedClause(
            fr_id=fr_id,
            kind=KIND_MANUAL,
            assertion_text=text,
            reason="malformed probe (not METHOD /path [body={json}] -> STATUS)",
        )

    # --- one-shot: exactly one backtick span whose first token is a runnable verb/console-script ---
    spans = _BACKTICK_RE.findall(text)
    candidates: List[Tuple[str, Tuple[str, ...], bool]] = []
    for span in spans:
        argv = _argv_of_span(span)
        if not argv:
            continue
        verb = argv[0]
        if verb in _ONESHOT_VERBS:
            candidates.append((span, argv, False))
        elif "/" not in verb and "." not in verb:
            # A bare token → candidate generated console-script (resolved by the runner, FR-1).
            candidates.append((span, argv, True))

    if not candidates:
        return ParsedClause(
            fr_id=fr_id,
            kind=KIND_ASSERTION,
            assertion_text=text,
            reason="prose acceptance (no runnable span)",
        )
    if len(candidates) >= 2:
        return ParsedClause(
            fr_id=fr_id,
            kind=KIND_MANUAL,
            assertion_text=text,
            reason="multi-command (more than one runnable span)",
        )
    span, argv, is_console = candidates[0]
    if _is_multi_command(span):
        return ParsedClause(
            fr_id=fr_id,
            kind=KIND_MANUAL,
            assertion_text=text,
            reason="multi-command (joined span)",
        )
    return ParsedClause(
        fr_id=fr_id,
        kind=KIND_ONESHOT,
        assertion_text=text,
        reason="single runnable console-script span"
        if is_console
        else "single runnable one-shot span",
        command_argv=argv,
        is_console_script=is_console,
    )


def parse_spec(requirements_path) -> List[ParsedClause]:
    """Parse every FR's ``Verify:`` clause in a det-req doc into :class:`ParsedClause` list.

    Reuses the navigator's ``det_req.parse_fr_lines_prefer_kit`` for FR extraction (the parsing of
    the doc itself is shared; only the *clause classification* is owned here — R1-F2).
    """
    from pathlib import Path

    from ..navigator.det_req import parse_fr_lines_prefer_kit

    text = Path(requirements_path).read_text(encoding="utf-8")
    frs = parse_fr_lines_prefer_kit(text)
    out: List[ParsedClause] = []
    for fr in frs:
        fr_id = str(fr.get("id", ""))
        verify = str(fr.get("verify") or "")
        out.append(parse_verify_clause(fr_id, verify))
    return out
