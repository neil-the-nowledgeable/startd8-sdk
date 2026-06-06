"""Shared grammar primitives (P0) — stdlib only, spike-pinned rules F1/F2.

- Markdown tables segment as **maximal consecutive-``|`` runs** (F1): the Pages section
  legitimately holds two adjacent tables (Pages + Nav); flattening them produced 21 phantom
  pages in spike v1. Encoded here once, regression-tested.
- Route/slug derivation applies **NFKD normalization** (F2): ``Résumé`` → ``resume``, never
  ``r-sum``.
- Cell/heading annotations (``*(not written yet)*``) and trailing ``#`` comments are display
  prose — stripped before value use, tolerated everywhere.

Local section parser (not ``document_chunking._parse_sections``): the FR-WPI-3 report needs
``heading_path`` tuples per value, which that private helper doesn't carry — and we don't
import privates cross-module (wireframe §3 Risks rule).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

_HEADING_RE = re.compile(r"^(#{2,4})\s+(.*?)\s*$")
_TABLE_SEP_RE = re.compile(r"^\|[\s\-:|]+\|?\s*$")
_ANNOTATION_RE = re.compile(r"\*\([^)]*\)\*")
_KEY_LINE_RE = re.compile(r"^- ([A-Z][\w ]*?):\s*(.*)$")


@dataclass(frozen=True)
class Section:
    """One heading-delimited section with its full heading path."""

    title: str                       # annotation-stripped heading text
    level: int                       # 2 for ##, 3 for ###, 4 for ####
    heading_path: Tuple[str, ...]    # ancestors + self, e.g. ("Entities", "ProofPoint")
    body: str                        # lines until the next heading of any level


@dataclass(frozen=True)
class Table:
    headers: Tuple[str, ...]         # lower-cased
    rows: Tuple[Tuple[str, ...], ...]

    def dicts(self) -> List[Dict[str, str]]:
        return [dict(zip(self.headers, row)) for row in self.rows]


def strip_annotations(text: str) -> str:
    """Drop ``*(…)*`` asides and trailing ``#`` comments: display prose, never values."""
    text = _ANNOTATION_RE.sub("", text)
    text = re.sub(r"\s+#\s.*$", "", text)
    return text.strip()


def nfkd_kebab(name: str) -> str:
    """F2: unicode-safe kebab — ``Résumé`` → ``resume``, ``How it works`` → ``how-it-works``."""
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "-", ascii_name.lower()).strip("-")


def parse_sections(text: str) -> List[Section]:
    """Flat list of ##/###/#### sections, each carrying its ancestor heading path."""
    out: List[Section] = []
    stack: List[Tuple[int, str]] = []            # (level, title)
    cur_title: Optional[str] = None
    cur_level = 0
    cur_path: Tuple[str, ...] = ()
    cur_body: List[str] = []

    def flush() -> None:
        if cur_title is not None:
            out.append(Section(cur_title, cur_level, cur_path, "\n".join(cur_body)))

    for line in text.splitlines():
        m = _HEADING_RE.match(line)
        if m:
            flush()
            level = len(m.group(1))
            title = strip_annotations(m.group(2))
            while stack and stack[-1][0] >= level:
                stack.pop()
            stack.append((level, title))
            cur_title, cur_level = title, level
            cur_path = tuple(t for _, t in stack)
            cur_body = []
        elif cur_title is not None:
            cur_body.append(line)
    flush()
    return out


def find_section(sections: List[Section], title_prefix: str) -> Optional[Section]:
    """First section whose title starts with *title_prefix* (case-insensitive)."""
    prefix = title_prefix.lower()
    for s in sections:
        if s.title.lower().startswith(prefix):
            return s
    return None


def md_tables(body: str) -> List[Table]:
    """ALL tables in *body*, segmented as maximal consecutive-``|`` runs (F1)."""
    def cells(line: str) -> Tuple[str, ...]:
        return tuple(c.strip() for c in line.strip().strip("|").split("|"))

    tables: List[Table] = []
    run: List[str] = []
    for line in body.splitlines() + [""]:
        if line.strip().startswith("|"):
            run.append(line)
        elif run:
            if len(run) >= 2 and _TABLE_SEP_RE.match(run[1].strip()):
                headers = tuple(h.lower() for h in cells(run[0]))
                rows = tuple(
                    cells(line) for line in run[2:] if not _TABLE_SEP_RE.match(line.strip())
                )
                tables.append(Table(headers, tuple(r for r in rows if any(r))))
            run = []
    return tables


def key_lines(body: str) -> Tuple[Dict[str, str], List[str]]:
    """``- Key: value`` lines from a Views-style block (CRP block-termination rule: the block
    ends at the first non-``- Key:`` line). Returns (ordered mapping, surplus-keys-in-order)."""
    out: Dict[str, str] = {}
    order: List[str] = []
    started = False
    for line in body.splitlines():
        if not line.strip():
            if started:
                break
            continue
        m = _KEY_LINE_RE.match(line.strip())
        if m:
            started = True
            key, val = m.group(1).strip(), strip_annotations(m.group(2))
            if key not in out:
                out[key] = val
                order.append(key)
        elif started:
            break  # first non-key line terminates the block
        else:
            continue  # leading prose before the key block is tolerated
    return out, order


def plural_candidates(word: str) -> List[str]:
    """Candidate singulars for an English plural surface form (``Capabilities`` →
    ``Capability``; ``ProofPoints`` → ``ProofPoint``). Deterministic, no guessing beyond the
    closed rules: -ies→y, -es→e/'' , -s→''."""
    out = [word]
    if word.endswith("ies"):
        out.append(word[:-3] + "y")
    if word.endswith("es"):
        out.append(word[:-2])
    if word.endswith("s"):
        out.append(word[:-1])
    return out
