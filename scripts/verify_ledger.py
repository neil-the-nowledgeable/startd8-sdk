#!/usr/bin/env python3
"""done-census verifier — dogfood the navigator's liveness principle against a work ledger.

The SESSION_LEDGER's ``## ✅ Implemented (built + landed)`` table is a *survivor census*: each row
claims a REQ/deliverable is "built + landed" and cites a commit sha + file/artifact refs. The ledger
itself admits it drifts ("verify by FR-tag commits + tests, never by this list"). This tool does that
verification MECHANICALLY, mirroring the two distinctions the navigator enforces on requirement Nodes:

- **authored ≠ propagated** (LANDED check): a cited sha that is a real git object but NOT an ancestor
  of ``main`` is **UNLANDED** — committed, not on main. The repo's own hard-won drift class.
- **presence ≠ liveness** (LIVENESS check): a cited path token that no longer resolves on disk is a
  **PHANTOM** — claimed-built, artifact gone.

A row with every cited sha landed AND every path live is **LIVE**. A row citing neither a real sha nor
a resolvable path is **UNVERIFIABLE** (honestly counted apart — never a false pass).

Reuses ``startd8.navigator.req_header.repo_root`` for the root (dogfood, don't rebuild). Standalone
script — not a navigator subcommand — because it audits a hand-maintained ledger, not a Node corpus.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

# Dogfood the navigator's repo-root helper (reuse, don't rebuild).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from startd8.navigator.req_header import repo_root  # noqa: E402

DEFAULT_LEDGER = (
    "docs/design/requirements-visualization/SESSION_LEDGER_specs-and-open-tasks.md"
)
IMPLEMENTED_HEADING = "## ✅ Implemented"

# LIVE / PHANTOM / UNLANDED / UNVERIFIABLE — the verdict vocabulary, mirroring the navigator's
# LIVE/PHANTOM (presence≠liveness) taxonomy in govern.py / the liveness-layer modules.
VERDICT_LIVE = "LIVE"
VERDICT_DRIFT = "DRIFT"
VERDICT_UNVERIFIABLE = "UNVERIFIABLE"

# A backtick-wrapped 7..40 hex token — a *candidate* commit sha (validated against git before use).
_SHA_TOKEN = re.compile(r"`([0-9a-f]{7,40})`")
# A backtick-wrapped token — a *candidate* path (classified by classify_path).
_BACKTICK_TOKEN = re.compile(r"`([^`\n]+)`")

# Extensions that mark a bare backtick token as a path even without a "/".
_PATH_EXTS = (".py", ".md", ".json", ".html", ".yaml", ".yml")


# ── pure extraction / classification helpers (unit-tested directly, no git/fs) ──────────────


def extract_shas(text: str) -> List[str]:
    """Backtick-wrapped 7..40-hex *candidate* commit shas in ``text``.

    Conservative on purpose: this only shapes-matches; a candidate becomes a real sha only after
    ``git cat-file -e`` confirms it is an object (see :func:`_is_git_object`). Guards against tokens
    that merely *look* hex-ish:

    - a ``sha256:``-prefixed field (a content digest, not a commit) — the ``:`` breaks the token so it
      is never captured whole; a leading ``sha256:`` word is excluded explicitly.
    - a color hex like ``#3a6a94`` — the ``#`` is outside the backtick-hex and, more decisively, the
      ``#`` is not part of the captured group, but a ``#``-prefixed token inside backticks is dropped.
    - a ``--flag`` — starts with ``-``, never hex-only, never matched.
    """
    out: List[str] = []
    seen = set()
    for m in _SHA_TOKEN.finditer(text):
        tok = m.group(1)
        # Guard: reject if immediately preceded (inside the same backtick span) by a color/sha256 lead.
        start = m.start(1)
        prev = text[start - 1] if start > 0 else ""
        if prev == "#":  # color hex like `#3a6a94`
            continue
        # a `sha256:...` token: the : truncates the capture, but the hex tail could still match; drop
        # any candidate whose preceding chars in the backtick span are "sha256:".
        span_start = text.rfind("`", 0, start)
        if span_start != -1:
            span_prefix = text[span_start + 1 : start]
            if span_prefix.endswith("sha256:") or span_prefix.endswith("sha1:"):
                continue
        if tok not in seen:
            seen.add(tok)
            out.append(tok)
    return out


def extract_paths(text: str) -> List[str]:
    """Backtick-wrapped *candidate* path tokens: contain a ``/`` OR end in a known code/doc ext.

    Skips obvious non-paths: pure hex shas, ``--flags``, ``#colors``, ``sha256:``/``cc:``-style
    scheme-qualified refs, and tokens with whitespace (prose in backticks).
    """
    out: List[str] = []
    seen = set()
    for m in _BACKTICK_TOKEN.finditer(text):
        tok = m.group(1).strip()
        if not tok or tok in seen:
            continue
        if _looks_like_path(tok):
            seen.add(tok)
            out.append(tok)
    return out


def _looks_like_path(tok: str) -> bool:
    """True when ``tok`` is path-shaped (has a ``/`` or a known extension), and not an obvious non-path.

    Conservative — the many *non-path* backtick tokens in a prose ledger are dropped so a real repo
    path isn't drowned in false PHANTOMs: elided branch names (``feature/…-x``), HTML fragments
    (``</head>``), slash-commands (``/code-review``), prose arrows (``proposed→accepted``), version
    tokens (``det-plan/0.1``), and ``module/attr.name`` dotted-attribute refs (not a filesystem path).
    """
    if any(ch.isspace() for ch in tok):
        return False
    if tok.startswith(("-", "#", "$")):
        return False
    # a bare extension-only token (".projected.md", ".py") is a filename SUFFIX written in prose,
    # not a real file — the stem is empty.
    if tok.startswith(".") and "/" not in tok:
        return False
    # an ellipsis (elided token like a truncated branch name) or an HTML angle-bracket → not a path
    if "…" in tok or "<" in tok or ">" in tok:
        return False
    # a prose arrow (proposed→accepted/rejected) is not a path
    if "→" in tok or "->" in tok:
        return False
    # a leading "/" that isn't a real absolute repo path is a slash-command (/code-review) — the repo
    # ledger never cites absolute paths, so treat a leading-slash token as a non-path.
    if tok.startswith("/"):
        return False
    # scheme-qualified refs (sha256:…, cc:intent:…, http:…) are not repo paths
    if ":" in tok and "/" not in tok.split(":", 1)[0]:
        head = tok.split(":", 1)[0]
        if head.isalnum():
            return False
    has_slash = "/" in tok
    has_ext = tok.endswith(_PATH_EXTS)
    if not (has_slash or has_ext):
        return False
    # a "module/attr.name" dotted-attribute reference (e.g. backend_codegen/realization_emit.foo):
    # a slash-token whose final segment's extension is NOT a known code/doc ext is not a file path.
    if has_slash and not has_ext:
        last = tok.rstrip("/").rsplit("/", 1)[-1]
        if "." in last:
            # final segment has a dot but not a real path extension → dotted-attribute ref, not a path
            return False
    # a version-ish token like "det-plan/0.1" — final segment is purely numeric-dotted → not a path
    tail = tok.rstrip("/").rsplit("/", 1)[-1]
    if tail and all(c.isdigit() or c == "." for c in tail):
        return False
    # a pure-hex token that only matched because of no ext/slash won't reach here; but a bare
    # `d416fc38` has no slash/ext → already excluded. Good.
    return True


@dataclass
class PathResult:
    token: str
    live: bool
    resolved: Optional[str] = None


def classify_path(root: Path, token: str) -> PathResult:
    """Resolve a path token under ``root``.

    - a ``/``-containing token → exact path check relative to root (file OR dir).
    - a bare filename (``render_tree.py``) → fast rglob-by-name anywhere under ``src/`` (then the whole
      repo as a fallback) counts as LIVE. (Directory-shaped bare tokens like ``plan_codegen/`` keep the
      trailing slash and are matched as a directory name.)
    """
    token = token.strip()
    if "/" in token.rstrip("/") or token.startswith("/"):
        # path-shaped: check exact location relative to root
        rel = token.rstrip("/")
        candidate = (root / rel).resolve()
        if candidate.exists():
            return PathResult(token, True, str(candidate.relative_to(root)))
        # also allow a trailing-slash dir token like "plan_codegen/" that is actually a nested dir name
        name = rel.split("/")[-1]
        if name:
            hit = _rglob_name(root, name, want_dir=token.endswith("/"))
            if hit is not None:
                return PathResult(token, True, str(hit.relative_to(root)))
        return PathResult(token, False)
    # bare filename or bare dirname
    want_dir = token.endswith("/")
    name = token.rstrip("/")
    hit = _rglob_name(root, name, want_dir=want_dir)
    if hit is not None:
        return PathResult(token, True, str(hit.relative_to(root)))
    return PathResult(token, False)


# A path that legitimately resolves OUTSIDE this repo (a sibling repo) or is produced at RUNTIME is not
# repo drift — classifying these keeps the PHANTOM signal precise (the navigator's own "don't cry wolf"
# principle applied to the auditor itself). Only a genuinely-absent, in-repo, source-expected path is drift.
_CROSS_REPO_PREFIXES = (
    "dev-os/",
    "contextcore/",
    "oss/",
    "craft/",
    "~/",
    "documents/dev/",
)
_RUNTIME_ARTIFACT = re.compile(
    r"(?:^|/)[\w.-]*provenance\.json$|(?:^|/)openapi\.json$", re.IGNORECASE
)


def classify_absence(token: str) -> Optional[str]:
    """For a token that did NOT resolve on disk, is its absence benign? → ``CROSS-REPO`` (lives in a
    sibling repo) / ``RUNTIME`` (a generated artifact, not committed) / ``None`` (genuine PHANTOM drift).
    """
    t = token.strip().rstrip("/").lower()
    if any(t.startswith(p) for p in _CROSS_REPO_PREFIXES):
        return "CROSS-REPO"
    if _RUNTIME_ARTIFACT.search(token.strip()):
        return "RUNTIME"
    return None


def _rglob_name(root: Path, name: str, want_dir: bool) -> Optional[Path]:
    """First filesystem entry named ``name`` under ``src/`` then the repo (skipping heavy dirs)."""
    _SKIP = {".git", ".venv", "node_modules", "__pycache__", ".startd8"}
    search_roots = [root / "src", root]
    for base in search_roots:
        if not base.exists():
            continue
        for p in base.rglob(name):
            if any(part in _SKIP for part in p.parts):
                continue
            if want_dir and not p.is_dir():
                continue
            return p
    return None


# ── git-touching helpers (integration; guarded in tests) ────────────────────────────────────


def _git(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True,
        text=True,
    )


def _is_git_object(root: Path, sha: str) -> bool:
    """True iff ``sha`` names a real git object (``git cat-file -e``)."""
    return _git(root, "cat-file", "-e", f"{sha}^{{commit}}").returncode == 0 or (
        _git(root, "cat-file", "-e", sha).returncode == 0
    )


def _is_ancestor_of_main(root: Path, sha: str, ref: str = "main") -> bool:
    """True iff ``sha`` is an ancestor of ``ref`` (authored → PROPAGATED)."""
    return _git(root, "merge-base", "--is-ancestor", sha, ref).returncode == 0


# ── ledger parsing ──────────────────────────────────────────────────────────────────────────


@dataclass
class LedgerRow:
    label: str
    raw: str  # the full markdown row text (all cells)


def parse_implemented_rows(ledger_text: str) -> List[LedgerRow]:
    """Parse the pipe table under ``## ✅ Implemented``; section ends at the next ``##`` or ``---``."""
    lines = ledger_text.splitlines()
    rows: List[LedgerRow] = []
    in_section = False
    for line in lines:
        if line.startswith(IMPLEMENTED_HEADING):
            in_section = True
            continue
        if in_section:
            stripped = line.strip()
            if stripped.startswith("## ") or stripped == "---":
                break
            if not stripped.startswith("|"):
                continue
            cells = _split_pipe_row(stripped)
            if not cells:
                continue
            # skip the header row and the separator row (---|---)
            joined = "".join(cells)
            if set(joined.replace("|", "").replace(" ", "")) <= {"-", ":"}:
                continue
            first = cells[0].strip()
            if first.lower() in ("artifact", ""):
                # header row (Artifact | What | State) or an empty leading cell
                if first.lower() == "artifact":
                    continue
            rows.append(LedgerRow(label=_row_label(cells), raw=stripped))
    return rows


def _split_pipe_row(line: str) -> List[str]:
    """Split a markdown pipe-table row into cells (drop leading/trailing empty from border pipes)."""
    parts = line.split("|")
    # a well-formed row is "| a | b | c |" → ['', ' a ', ' b ', ' c ', '']
    if parts and parts[0].strip() == "":
        parts = parts[1:]
    if parts and parts[-1].strip() == "":
        parts = parts[:-1]
    return parts


def _row_label(cells: List[str]) -> str:
    """The row label = the first cell, stripped of markdown bold/backticks/parenthetical noise."""
    raw = cells[0].strip() if cells else ""
    label = raw.replace("**", "").strip()
    # collapse a trailing "(`feature/…`)" or "(…)" for a cleaner label but keep the head
    return label


# ── verification ────────────────────────────────────────────────────────────────────────────


@dataclass
class RowReport:
    label: str
    verdict: str
    findings: List[str] = field(default_factory=list)
    checked_shas: List[str] = field(default_factory=list)
    checked_paths: List[str] = field(default_factory=list)
    unverifiable_reason: Optional[str] = None


def verify_row(root: Path, row: LedgerRow, ref: str = "main") -> RowReport:
    """Run the LANDED + LIVENESS checks over one row → a :class:`RowReport`."""
    sha_candidates = extract_shas(row.raw)
    path_candidates = extract_paths(row.raw)

    findings: List[str] = []
    real_shas: List[str] = []
    for sha in sha_candidates:
        if not _is_git_object(root, sha):
            continue  # a hex token that is not a real object — probably not a sha; ignore.
        real_shas.append(sha)
        if not _is_ancestor_of_main(root, sha, ref):
            findings.append(f"UNLANDED:{sha}")

    live_paths: List[str] = []
    for tok in path_candidates:
        pr = classify_path(root, tok)
        live_paths.append(tok)
        if pr.live:
            continue
        reason = classify_absence(tok)
        # CROSS-REPO / RUNTIME absences are informational (not drift); only a genuinely-absent
        # in-repo source path is a PHANTOM.
        findings.append(f"{reason}:{tok}" if reason else f"PHANTOM:{tok}")

    # UNVERIFIABLE: no real sha AND no path candidate → nothing mechanical to check.
    if not real_shas and not path_candidates:
        return RowReport(
            label=row.label,
            verdict=VERDICT_UNVERIFIABLE,
            findings=[],
            checked_shas=[],
            checked_paths=[],
            unverifiable_reason="no cited commit sha and no path/artifact reference",
        )

    # A row is DRIFT only on a GENUINE finding (PHANTOM/UNLANDED); benign notes don't trip it.
    genuine = [f for f in findings if f.split(":", 1)[0] in ("PHANTOM", "UNLANDED")]
    verdict = VERDICT_LIVE if not genuine else VERDICT_DRIFT
    return RowReport(
        label=row.label,
        verdict=verdict,
        findings=findings,
        checked_shas=real_shas,
        checked_paths=live_paths,
    )


@dataclass
class LedgerReport:
    ledger: str
    ref: str
    rows: List[RowReport]

    @property
    def clean(self) -> int:
        return sum(1 for r in self.rows if r.verdict == VERDICT_LIVE)

    @property
    def drift(self) -> int:
        return sum(1 for r in self.rows if r.verdict == VERDICT_DRIFT)

    @property
    def unverifiable(self) -> int:
        return sum(1 for r in self.rows if r.verdict == VERDICT_UNVERIFIABLE)

    @property
    def has_drift(self) -> bool:
        return self.drift > 0


def verify_ledger(ledger_path: Path, root: Path, ref: str = "main") -> LedgerReport:
    text = ledger_path.read_text(encoding="utf-8")
    rows = parse_implemented_rows(text)
    reports = [verify_row(root, r, ref) for r in rows]
    return LedgerReport(ledger=str(ledger_path), ref=ref, rows=reports)


# ── rendering ────────────────────────────────────────────────────────────────────────────────


def render_text(report: LedgerReport) -> str:
    lines: List[str] = []
    for r in report.rows:
        if r.verdict == VERDICT_LIVE:
            lines.append(f"  LIVE          {r.label}")
        elif r.verdict == VERDICT_UNVERIFIABLE:
            lines.append(f"  UNVERIFIABLE  {r.label}  ({r.unverifiable_reason})")
        else:
            lines.append(f"  DRIFT         {r.label}")
            for f in r.findings:
                lines.append(f"                  └─ {f}")
    total = len(report.rows)
    summary = (
        f"{total} rows, {report.clean} clean, {report.drift} with drift"
        f" ({report.unverifiable} unverifiable)"
    )
    lines.append("")
    lines.append(summary)
    return "\n".join(lines)


def render_json(report: LedgerReport) -> str:
    return json.dumps(
        {
            "ledger": report.ledger,
            "ref": report.ref,
            "summary": {
                "rows": len(report.rows),
                "clean": report.clean,
                "drift": report.drift,
                "unverifiable": report.unverifiable,
            },
            "rows": [
                {
                    "label": r.label,
                    "verdict": r.verdict,
                    "findings": r.findings,
                    "checked_shas": r.checked_shas,
                    "checked_paths": r.checked_paths,
                    "unverifiable_reason": r.unverifiable_reason,
                }
                for r in report.rows
            ],
        },
        indent=2,
    )


# ── CLI ──────────────────────────────────────────────────────────────────────────────────────


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="done-census verifier: mechanically check a work ledger's "
        "'built + landed' claims (authored≠propagated, presence≠liveness)."
    )
    parser.add_argument(
        "--ledger",
        type=Path,
        default=None,
        help=f"path to the ledger markdown (default: {DEFAULT_LEDGER})",
    )
    parser.add_argument(
        "--ref",
        default="main",
        help="the ref a landed sha must be an ancestor of (default: main)",
    )
    parser.add_argument(
        "--json", action="store_true", help="emit the structured report as JSON"
    )
    args = parser.parse_args(argv)

    root = repo_root(Path(__file__).resolve())
    if root is None:
        # fallback: walk up from this script
        root = Path(__file__).resolve().parent.parent

    ledger_path = args.ledger if args.ledger is not None else root / DEFAULT_LEDGER
    if not ledger_path.exists():
        print(f"error: ledger not found: {ledger_path}", file=sys.stderr)
        return 2

    report = verify_ledger(ledger_path, root, ref=args.ref)
    if args.json:
        print(render_json(report))
    else:
        print(render_text(report))
    return 1 if report.has_drift else 0


if __name__ == "__main__":
    raise SystemExit(main())
