"""The ``$0`` REQ→HOWTO projector (STANDARD Part 1, SCHEMA §6 — cited, not defined there).

``project_howto(req_text, *, req_path=None)`` is a **pure** function of an authored REQ doc: no
network, no LLM, no ``Date.now()``/``random``. Every output field derives from an authored input
field (STANDARD I-1):

- ``commands[]``  ← the REQ's ``## Contract projection`` rows whose ``Kind`` is ``command``/``option``
  (SCHEMA §2/§0.1), plus any FR that declares a CLI verb.
- ``prerequisites[]`` ← the reuse/phantom audit — each FR ``Touches``/code-``Lives`` ref resolved on
  disk ``LIVE``/``PHANTOM`` (SCHEMA §2).

Part-6 honesty behaviors (STANDARD): the solo-vs-gap gate (a REQ with **no** command surface owes no
HOWTO → ``NotHowtoOwedError``, SCHEMA §5), maturity stamped at ``0.1`` (SCHEMA §4), DIDL naming via
``naming.name_forms(kind="howto")``, and a ``pairsWith`` back-reference to the source REQ (STANDARD
6d). The when/why/troubleshooting narrative is HUMAN-RESIDUE — never invented (SCHEMA §5).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import List, Optional

from ..navigator import naming, req_header
from ..navigator.det_req import parse_fr_lines
from .models import Command, Howto, Prerequisite


class NotHowtoOwedError(Exception):
    """Raised when a REQ declares **no** command surface — a solo-by-design source owes no HOWTO.

    STANDARD 6a (solo-vs-gap gate) / SCHEMA §5: the gate *signal* for this doc-type is the presence
    of ``## Contract projection`` command/option rows (or a CLI-declaring FR). Fire only when a
    companion is owed; never manufacture a usage guide for a feature with no invocation surface.
    """


# The `## Contract projection` table: a markdown pipe table whose first column is the entry name and
# second column is the Kind. We locate the section heading, then read pipe rows until the next
# heading / blank-run boundary. Kinds we project are `command` and `option` (SCHEMA §2/§0.1).
_CONTRACT_HEADING = re.compile(r"^##\s+Contract projection\s*$", re.MULTILINE)
_NEXT_HEADING = re.compile(r"^##\s+", re.MULTILINE)
_PROJECTED_KINDS = ("command", "option")

# A CLI-declaring FR: its behavior/name mentions a `startd8 <verb> …` invocation. We read the FR's
# authored text (title + behavior) for an inline-code `startd8 …` span; that span IS the authored
# surface (never inferred beyond what the FR literally wrote). SCHEMA §0.1 "any FR that declares a
# CLI verb".
_STARTD8_SPAN = re.compile(r"`(startd8\s+[^`]+?)`")
# A `startd8 …` span containing any placeholder from REQ-08's closed set is PROSE, not a runnable
# command (SCHEMA §0.1 CLI-verb rule, pinned by the det-howto independent-replication finding). A
# span like `startd8 navigator …` is not emitted — never-inferred: a placeholder ≠ a real surface.
_PLACEHOLDER = re.compile(
    r"…|\.\.\.|<[^>]*>|\$\{[^}]*\}|\$[A-Z_]+|\{[^}]*\}|\[[^\]]*\]"
)


def _slice_contract_projection(text: str) -> str:
    """Return the body of the ``## Contract projection`` section (empty when absent)."""
    m = _CONTRACT_HEADING.search(text)
    if not m:
        return ""
    body = text[m.end() :]
    nxt = _NEXT_HEADING.search(body)
    return body[: nxt.start()] if nxt else body


def _parse_pipe_row(line: str) -> Optional[List[str]]:
    """Parse one markdown pipe-table row into stripped cells, or ``None`` if not a data row."""
    s = line.strip()
    if not s.startswith("|"):
        return None
    # A separator row (|---|---|) is not data.
    if set(s) <= set("|-: "):
        return None
    cells = [c.strip() for c in s.strip("|").split("|")]
    return cells


def _commands_from_contract(text: str) -> List[Command]:
    """Derive ``commands[]`` from the ``## Contract projection`` command/option rows (SCHEMA §2)."""
    body = _slice_contract_projection(text)
    commands: List[Command] = []
    header_seen = False
    for raw in body.splitlines():
        cells = _parse_pipe_row(raw)
        if cells is None:
            continue
        # The first data-shaped row is the header (Entry | Kind | … ). Skip it once.
        if not header_seen:
            header_seen = True
            continue
        if len(cells) < 2:
            continue
        entry, kind = cells[0], cells[1].lower()
        note = cells[3] if len(cells) >= 4 else (cells[2] if len(cells) >= 3 else "")
        # Strip markdown emphasis/backticks from the entry name.
        entry = entry.strip("`* ")
        if kind in _PROJECTED_KINDS and entry:
            commands.append(
                Command(name=entry, kind=kind, note=note, source="contract-projection")
            )
    return commands


def _commands_from_frs(text: str) -> List[Command]:
    """Derive additional ``commands[]`` from any FR that declares a ``startd8 …`` CLI verb.

    The authored surface is the literal inline-code ``startd8 …`` span in the FR text; we never
    infer a command beyond what the FR wrote (SCHEMA §5 never-inferred).
    """
    commands: List[Command] = []
    seen: set[str] = set()
    for fr in parse_fr_lines(text):
        haystack = f"{fr.get('title', '')} {fr.get('behavior', '')}"
        for m in _STARTD8_SPAN.finditer(haystack):
            span = re.sub(r"\s+", " ", m.group(1)).strip()
            if span and span not in seen and not _PLACEHOLDER.search(span):
                seen.add(span)
                commands.append(
                    Command(
                        name=span, kind="command", note="", source=fr.get("id", "FR")
                    )
                )
    return commands


def _dedup_commands(commands: List[Command]) -> List[Command]:
    """First-seen dedup by ``(name, kind)`` (a contract row + an FR may name the same verb)."""
    out: List[Command] = []
    seen: set[tuple[str, str]] = set()
    for c in commands:
        key = (c.name, c.kind)
        if key not in seen:
            seen.add(key)
            out.append(c)
    return out


# A Lives ref may arrive as a single-line multi-entry body the thin parser collapses into one string
# (e.g. ``code a.py, test b.py, test c.py`` — det_req.parse_lives_body's non-`- type:` branch). Split
# on commas and strip a leading type word so each real path is audited on its own (SCHEMA §2), rather
# than one compound ref falsely resolving PHANTOM.
_LIVES_TYPE_PREFIX = re.compile(r"^(?:code|test|doc|config|schema)\s+", re.IGNORECASE)


def _split_ref(raw: str) -> List[str]:
    """Split a possibly-compound Lives/Touches ref into individual path-shaped tokens."""
    out: List[str] = []
    for part in raw.split(","):
        token = _LIVES_TYPE_PREFIX.sub("", part.strip()).strip()
        if token:
            out.append(token)
    return out


def _refs_from_frs(text: str) -> List[tuple[str, str]]:
    """Collect authored ``Touches`` + code-``Lives`` refs as ``(ref, declared_by_fr_id)`` pairs.

    These are the reuse-audit inputs (SCHEMA §2). Compound refs (a comma-joined multi-entry Lives
    body) are split so each real path is audited independently.
    """
    refs: List[tuple[str, str]] = []
    seen: set[str] = set()

    def add(raw: str, fid: str) -> None:
        for r in _split_ref(raw):
            if r and r != "-" and r not in seen:
                seen.add(r)
                refs.append((r, fid))

    for fr in parse_fr_lines(text):
        fid = fr.get("id", "FR")
        for t in fr.get("touches", []):
            add(t, fid)
        for live in fr.get("lives", []):
            add(str(live.get("ref", "")), fid)
    return refs


def _resolve_liveness(ref: str, repo_root: Optional[Path]) -> str:
    """Resolve one ref on disk: ``LIVE`` if the path exists, else ``PHANTOM`` (SCHEMA §2/§3).

    A git ref (``git:<sha>:path``) or an external ``~/…`` doc path can't be resolved against the
    repo tree deterministically, so it is classed ``LEGACY`` (present-but-unverifiable), never
    silently ``LIVE``. STANDARD I-1: never invent the edge.
    """
    r = ref.strip()
    if r.startswith("git:") or r.startswith("~") or r.startswith("http"):
        return "LEGACY"
    if repo_root is None:
        # No anchor to resolve against — honestly unverifiable, not a false LIVE.
        return "LEGACY"
    candidate = (repo_root / r).resolve()
    return "LIVE" if candidate.exists() else "PHANTOM"


def _prerequisites(text: str, req_path: Optional[Path]) -> List[Prerequisite]:
    """Build the reuse/phantom-audit ``prerequisites[]`` (SCHEMA §2)."""
    root = req_header.repo_root(req_path)
    prereqs: List[Prerequisite] = []
    for ref, fid in _refs_from_frs(text):
        prereqs.append(
            Prerequisite(
                ref=ref,
                liveness=_resolve_liveness(ref, root),  # type: ignore[arg-type]
                declared_by=fid,
            )
        )
    return prereqs


def _pairs_with(text: str, req_path: Optional[Path]) -> str:
    """The back-reference to the source REQ (STANDARD 6d).

    Prefer an explicit path; else the REQ file's own path (the projection's source *is* that file).
    """
    if req_path is not None:
        # The source doc IS the req_path — the resolvable back-reference the provider re-projects.
        return req_path.as_posix()
    # No path given: fall back to the header's `**Pairs with:**` companion declaration.
    return req_header.pairs_with_line(text)


def project_howto(req_text: str, *, req_path: Optional[Path] = None) -> Howto:
    """Project a det-howto/0.1 model from an authored REQ (pure, ``$0``, no network/LLM).

    Raises ``NotHowtoOwedError`` when the REQ declares no command surface (STANDARD 6a / SCHEMA §5).
    """
    commands = _dedup_commands(
        _commands_from_contract(req_text) + _commands_from_frs(req_text)
    )

    # STANDARD 6a — solo-vs-gap gate. The signal for det-howto is the presence of command/option
    # rows or a CLI-declaring FR (SCHEMA §5). No surface → no HOWTO owed.
    if not commands:
        raise NotHowtoOwedError(
            "REQ declares no command surface (no `## Contract projection` command/option rows and "
            "no CLI-declaring FR) — a solo-by-design feature owes no HOWTO (SCHEMA §5)."
        )

    prerequisites = _prerequisites(req_text, req_path)

    # DIDL naming (STANDARD 6c) — kind="howto".
    sem_name = (
        req_header.semantic_name(req_text) or req_header.title(req_text) or "howto"
    )
    key = req_header.req_key(req_text, req_path)
    forms = naming.name_forms(
        sem_name, key, initiative="requirements-visualization", kind="howto"
    )

    # `version` is an authored header field (SCHEMA §1). We do not invent it; a projected doc's own
    # lineage starts at the initial maturity, so version tracks that unless the REQ carries one.
    version = _authored_version(req_text) or "0.1.0"

    return Howto(
        version=version,
        pairs_with=_pairs_with(req_text, req_path),
        title=req_header.title(req_text) or sem_name,
        name=sem_name,
        handle=forms["handle"],
        ref=forms["canonical"],
        commands=commands,
        prerequisites=prerequisites,
    )


_VERSION_LINE = re.compile(
    r"^\*\*Version:\*\*\s*(?P<v>[0-9]+(?:\.[0-9]+)*)", re.MULTILINE
)


def _authored_version(text: str) -> str:
    """The REQ's authored ``**Version:**`` semver prefix (empty when absent). Never invented."""
    m = _VERSION_LINE.search(text)
    return m.group("v").strip() if m else ""
