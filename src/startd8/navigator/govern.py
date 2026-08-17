"""Corpus governance (REQ-06) — the governance counterpart to the corpus INDEX (REQ-03).

Where the corpus index *renders* per-doc health for a human to read, corpus governance *governs*:
it runs a fixed, closed battery of deterministic checks over a DIRECTORY of ``REQ-*.md`` docs and
emits a pass/fail governance report an author (or CI) can fail on.

The five checks (charter-bounded — NR-6 forbids growing this without a demonstrated real drift):

  FR-1  name-block presence   every doc carries the deterministic NAME BLOCK (Readable handle +
                              Semantic name + Canonical ref) and every FR bullet carries a `Name:`.
  FR-2  single-line-FR        every FR bullet is ONE physical line (a hard-wrap silently drops
                              Name:/Touches:/Lives:/Verify: — `parse_fr_lines` is per-line).
  FR-3  dangling cross-ref    intra-corpus `REQ-0N` citations + `Lives`/`Touches` paths resolve
                              (excluding a doc's own to-be-built deliverable paths); orphan docs
                              are a lower-severity advisory.
  FR-4  coverage              every parseable REQ has Objectives, >=1 FR, a `Verify:` per FR, and --
                              when it uses `Serves:` -- every Objective served (reuses the exact
                              `render_index._req_summary` / `ReqView` gap logic).
  FR-5  index-freshness       (advisory) the doc-set on disk equals the link-set the corpus index
                              would render -- structural, not a byte-diff (so it won't flap).

Kagami / Mottainai (FR-9): every check reads through the ONE shared parser + health model
(``det_req.parse_fr_lines``, ``render_a11y.ReqView``, ``render_index._req_summary`` /
``_doc_title``, ``naming.name_forms``). ``govern.py`` owns NO second doc parser, FR parser, or
health model -- a check needing a new signal extends the shared primitive, it does not fork it.

NR-2: govern is READ-ONLY -- report + exit code only; a fix is a human edit or a downstream-skill
hand-off (`/audit-then-metabolize`, `/metabolize-finding`), never an inline rewrite.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List

# --- FR-9: reuse the ONE shared parser + health model. No forked parser/ReqView/name_forms here. ---
from .det_req import parse_fr_lines
from .render_a11y import ReqView, attr
from .render_index import _req_summary
from .sources_requirements import nodes_from_requirements

# The deterministic name-block markers (lifted verbatim from navigator_spec_delivery_loop, so the
# loop's stage-0 gate and this corpus-wide governor read a doc's name block identically -- Kagami).
_HANDLE = re.compile(r"\*\*Readable handle:\*\*\s*`?([^\n`]+)`?")
_SEMNAME = re.compile(r"\*\*Semantic name:\*\*\s*\*?(.+)")
_CANONICAL = re.compile(r"\*\*Canonical ref(?:\s*\([^)]*\))?:\*\*\s*`?([^\n`]+)`?")
_FR_MARKER = re.compile(r"^- \*\*FR-", re.MULTILINE)

# An intra-corpus REQ citation in the *local* numbering scheme: REQ-0N (zero-padded, single non-zero
# unit digit -> REQ-01..REQ-09). REQ-10+/REQ-99/REQ-0 are deliberately NOT this form -- they are
# cross-project refs (e.g. "dev-os REQ-10") or in-prose examples (REQ-06 FR-3 cites REQ-99), so they
# are out-of-scheme and never fail-severity. This is what keeps REQ-01..09 clean (FR-8 precision gate).
_LOCAL_REQ_REF = re.compile(r"\bREQ-0([1-9])\b")
# A repo-relative path token cited inline (in Lives:/Touches:/prose), e.g. `src/startd8/navigator/x.py`.
_PATH_TOKEN = re.compile(r"`([A-Za-z0-9_][\w./-]*\.[A-Za-z0-9_]+)`")

_SEVERITY_FAIL = "fail"
_SEVERITY_ADVISORY = "advisory"


# --------------------------------------------------------------------------- #
# stage-0 build-readiness gate (lifted from navigator_spec_delivery_loop -- Kagami: one home)
# --------------------------------------------------------------------------- #

def gate_spec(path: Path) -> Dict[str, Any]:
    """Run the deterministic build-readiness checks on one det-req spec (Spec Delivery Loop stage 0).

    Returns a verdict dict: {path, ok, checks: [(name, ok, detail)], frs, blocked}.
    A spec passes iff it has a name block, at least one FR that parses, and every parsed FR
    carries Name + Verify + Serves. The single-line integrity check compares the raw ``- **FR-``
    marker count to the parsed count -- a hard-wrapped bullet drops fields the parser can't see.

    This is the single-doc precondition that guards a build; ``govern_corpus`` is its corpus-wide
    generalization. Both live here (one home) so the loop script and the governor read a spec's name
    block + FRs through the identical primitives (FR-9, no mirror drift).
    """
    from typing import Tuple

    text = path.read_text(encoding="utf-8")
    checks: List[Tuple[str, bool, str]] = []

    handle = _HANDLE.search(text)
    semname = _SEMNAME.search(text)
    name_ok = bool(handle and semname)
    checks.append(("name-block", name_ok,
                   f"handle={handle.group(1).strip() if handle else 'MISSING'}"
                   if name_ok else "no deterministic name block (Readable handle + Semantic name)"))

    frs = parse_fr_lines(text)
    marker_count = len(_FR_MARKER.findall(text))
    parse_ok = len(frs) > 0 and len(frs) == marker_count
    checks.append(("frs-parse", parse_ok,
                   f"{len(frs)} FR(s) parse, {marker_count} bullet marker(s)"
                   + ("" if parse_ok else " -- MISMATCH: a hard-wrapped FR is dropping fields")))

    missing_name = [f["id"] for f in frs if not f.get("name")]
    named_ok = bool(frs) and not missing_name
    checks.append(("frs-named", named_ok,
                   "every FR has a deterministic Name:" if named_ok
                   else f"FRs missing Name: {', '.join(missing_name) or '(no FRs)'}"))

    missing_verify = [f["id"] for f in frs if not f.get("verify")]
    verify_ok = bool(frs) and not missing_verify
    checks.append(("frs-verify", verify_ok,
                   "every FR has an acceptance Verify:" if verify_ok
                   else f"FRs missing Verify: {', '.join(missing_verify) or '(no FRs)'}"))

    missing_serves = [f["id"] for f in frs if not f.get("serves")]
    serves_ok = bool(frs) and not missing_serves
    checks.append(("frs-serves", serves_ok,
                   "every FR links an objective Serves:" if serves_ok
                   else f"FRs missing Serves: {', '.join(missing_serves) or '(no FRs)'}"))

    ok = all(c[1] for c in checks)
    return {"path": path, "ok": ok, "checks": checks, "frs": len(frs),
            "blocked": [c[0] for c in checks if not c[1]]}


@dataclass
class Finding:
    """One governance finding: a check firing on a doc, with a severity and a fix-naming message."""

    check: str  # the FR id, e.g. "FR-1"
    severity: str  # "fail" | "advisory"
    doc: str  # the offending doc's filename
    message: str  # names the doc + (fr/line/ref) + fix
    fr: str = ""  # optional FR id the finding is about
    ref: str = ""  # optional dangling ref / path

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {"check": self.check, "severity": self.severity, "doc": self.doc,
                             "message": self.message}
        if self.fr:
            d["fr"] = self.fr
        if self.ref:
            d["ref"] = self.ref
        return d


@dataclass
class GovernReport:
    """The governance verdict over a corpus: findings + per-check roll-up + an overall exit code."""

    corpus: str
    docs: List[str] = field(default_factory=list)
    findings: List[Finding] = field(default_factory=list)

    @property
    def fail_findings(self) -> List[Finding]:
        return [f for f in self.findings if f.severity == _SEVERITY_FAIL]

    @property
    def advisory_findings(self) -> List[Finding]:
        return [f for f in self.findings if f.severity == _SEVERITY_ADVISORY]

    @property
    def clean(self) -> bool:
        """A corpus is clean iff no *fail*-severity finding fired (advisories never fail the build)."""
        return not self.fail_findings

    @property
    def exit_code(self) -> int:
        """FR-6/FR-8: 0=clean / 1=drift (any fail-severity finding). Operational error (2) is raised
        by the CLI before a report exists, not here."""
        return 0 if self.clean else 1

    def checks_summary(self) -> Dict[str, Dict[str, int]]:
        """Per-check fail/advisory counts (the report's per-check pass/fail roll-up)."""
        out: Dict[str, Dict[str, int]] = {}
        for fr in ("FR-1", "FR-2", "FR-3", "FR-4", "FR-5"):
            out[fr] = {"fail": 0, "advisory": 0}
        for f in self.findings:
            out.setdefault(f.check, {"fail": 0, "advisory": 0})
            out[f.check][f.severity] += 1
        return out

    def govern_score(self) -> float:
        """FR-7 moving number: clean checks / total checks (of the 5), per the loop-family convention."""
        summary = self.checks_summary()
        total = len(summary)
        clean = sum(1 for c in summary.values() if c["fail"] == 0)
        return round(clean / total, 4) if total else 1.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "corpus": self.corpus,
            "docs": self.docs,
            "clean": self.clean,
            "exit_code": self.exit_code,
            "govern_score": self.govern_score(),
            "checks": self.checks_summary(),
            "findings": [f.to_dict() for f in self.findings],
        }


# --------------------------------------------------------------------------- #
# per-doc checks (each reuses a shared primitive -- FR-9)
# --------------------------------------------------------------------------- #

def _check_name_block(path: Path, text: str) -> List[Finding]:
    """FR-1 -- every doc carries the deterministic NAME BLOCK, and every FR bullet carries a `Name:`.

    Reuses the loop gate's name-block markers + ``det_req.parse_fr_lines`` for the per-FR `Name:`
    check (NOT a new name parser); adds the canonical-ref presence check the loop gate doesn't do.
    """
    findings: List[Finding] = []
    handle = _HANDLE.search(text)
    semname = _SEMNAME.search(text)
    canonical = _CANONICAL.search(text)
    # Handle + Semantic name are the gate_spec name-block invariant (FAIL — a doc identified by
    # integer+type alone is the anti-pattern the convention exists to prevent).
    missing = []
    if not handle:
        missing.append("Readable handle")
    if not semname:
        missing.append("Semantic name")
    if missing:
        findings.append(Finding(
            "FR-1", _SEVERITY_FAIL, path.name,
            f"{path.name}: name block missing {', '.join(missing)} -- "
            "add the deterministic NAME BLOCK (Readable handle + Semantic name) "
            "per NAMING_CONVENTION.md (a doc identified by integer+type alone is the anti-pattern).",
        ))
    # Canonical ref is the ADDED check (gate_spec doesn't assert it). Degraded to ADVISORY so it
    # never fails a doc that predates the canonical-ref convention (FR-8 precision gate: a heuristic
    # that cannot reach zero false positives on the current corpus degrades, never fails the build).
    elif not canonical:
        findings.append(Finding(
            "FR-1", _SEVERITY_ADVISORY, path.name,
            f"{path.name}: name block has no `Canonical ref:` -- add "
            "`cc:intent:<initiative>:<kind>:<key>` for a stable, wording-independent machine identity.",
        ))
    # every FR bullet must carry an authored Name: (reuse the shared parser, not a new one)
    frs = parse_fr_lines(text)
    unnamed = [f["id"] for f in frs if not f.get("name")]
    for fid in unnamed:
        findings.append(Finding(
            "FR-1", _SEVERITY_FAIL, path.name,
            f"{path.name}: {fid} has no `Name:` field -- add a semantic Name: "
            "(actor.action.object.outcome) so it is not identified by its integer key alone.",
            fr=fid,
        ))
    return findings


def _check_single_line_fr(path: Path, text: str) -> List[Finding]:
    """FR-2 -- every FR bullet is one physical line (the same marker-count-vs-parse dogfood the loop
    stage-0 gate uses verbatim: a hard-wrapped bullet drops the fields the per-line parser can't see)."""
    frs = parse_fr_lines(text)
    marker_count = len(_FR_MARKER.findall(text))
    if marker_count and len(frs) != marker_count:
        return [Finding(
            "FR-2", _SEVERITY_FAIL, path.name,
            f"{path.name}: {marker_count} FR bullet marker(s) but only {len(frs)} parse -- "
            "a hard-wrapped FR is silently dropping Name:/Touches:/Lives:/Verify:; "
            "put each FR on ONE physical line.",
        )]
    return []


def _own_deliverable_paths(text: str) -> set:
    """The paths a doc declares as its OWN to-be-built deliverables (Touches:/Lives:/Library seams).

    A spec legitimately cites files it is the deliverable for (they don't exist yet), so FR-3 must
    NOT fail on them. Mines the FR grammar's authored ``Touches:`` (via the shared parser) plus the
    ``Contract projection`` "Library seams (Touches file paths)" block.
    """
    own: set = set()
    for f in parse_fr_lines(text):
        for t in f.get("touches") or []:
            own.add(t.strip().strip("`").lstrip("./"))
        for ev in f.get("lives") or []:
            ref = (ev.get("ref") if isinstance(ev, dict) else "") or ""
            # Lives refs look like "code src/...", "src/...", or a git: anchor -- take the path tail.
            toks = _PATH_TOKEN.findall(ref) or [ref]
            for tok in toks:
                own.add(tok.strip().strip("`").lstrip("./"))
    # The "Library seams (Touches file paths): a, b, c" block names the deliverable files too.
    seam_block = re.search(
        r"Library seams[^:]*:\s*(.+?)(?:\n\n|Primitives reused|\Z)", text, re.DOTALL)
    if seam_block:
        for tok in _PATH_TOKEN.findall(seam_block.group(1)):
            own.add(tok.strip().strip("`").lstrip("./"))
    return {p for p in own if p}


def _check_dangling_xref(path: Path, text: str, corpus_keys: set, repo_root: Path) -> List[Finding]:
    """FR-3 -- intra-corpus cross-references resolve.

    - A local-scheme ``REQ-0N`` citation (REQ-01..09) that names no ``REQ-0N-*.md`` in the corpus is
      a FAIL (the renamed/missing-doc case). REQ-10+/REQ-99/REQ-0 are out-of-scheme (cross-project /
      in-prose) -> never fail (this is what keeps the current corpus clean -- FR-8).
    - A cited repo-relative ``path`` that does not resolve to a repo file is an ADVISORY, EXCEPT the
      doc's own declared deliverable paths (a spec cites files it is the deliverable for -- no
      self-fail); path drift is lower-confidence than a REQ rename, so it degrades (FR-8).
    """
    findings: List[Finding] = []
    own = _own_deliverable_paths(text)

    # (a) local-scheme REQ-0N citations -- deduped by key
    seen_keys: set = set()
    for m in _LOCAL_REQ_REF.finditer(text):
        key = f"REQ-0{m.group(1)}"
        if key in seen_keys:
            continue
        seen_keys.add(key)
        if key not in corpus_keys:
            findings.append(Finding(
                "FR-3", _SEVERITY_FAIL, path.name,
                f"{path.name}: cites {key} but no {key}-*.md exists in the corpus -- "
                "a dangling cross-ref (the doc was renamed away or never existed).",
                ref=key,
            ))

    # (b) cited repo-relative paths (in `backticks`) resolve to a repo file, excluding own deliverables
    path_seen: set = set()
    for m in _PATH_TOKEN.finditer(text):
        tok = m.group(1).strip().lstrip("./")
        if tok in path_seen:
            continue
        path_seen.add(tok)
        if "/" not in tok:
            continue
        root = tok.split("/", 1)[0]
        if root not in ("src", "tests", "docs", "scripts"):
            continue
        if tok in own:
            continue  # the doc's own to-be-built deliverable -- no self-fail
        if (repo_root / tok).exists():
            continue
        findings.append(Finding(
            "FR-3", _SEVERITY_ADVISORY, path.name,
            f"{path.name}: cites path `{tok}` that does not resolve to a repo file "
            "(and is not this doc's own declared deliverable) -- verify it wasn't moved/renamed.",
            ref=tok,
        ))
    return findings


def _check_coverage(path: Path, summary: Dict[str, Any]) -> List[Finding]:
    """FR-4 -- Objectives + >=1 FR + a Verify: per FR + every Objective served (when Serves used).

    Reuses the EXACT gap computation ``render_index._req_summary`` already produces (health='risk'
    when there is a gap) via a fresh ``ReqView`` for the specific gap message -- no second health model.
    """
    findings: List[Finding] = []
    # An unparseable / foreign-format doc (health 'info') is not a coverage fail -- it simply carries
    # no det-req sections; that is the index's own 'info' verdict, mirrored here (never a false fail).
    if summary.get("health") == "info":
        return []
    try:
        v = ReqView(nodes_from_requirements(path))
    except Exception:  # pragma: no cover - defensive; the index already degraded it to 'info' above
        return []
    if not v.frs:
        findings.append(Finding(
            "FR-4", _SEVERITY_FAIL, path.name,
            f"{path.name}: declares no FRs -- a REQ needs >=1 functional requirement.",
        ))
        return findings
    # High-confidence coverage: every FR needs an acceptance Verify: (the loop gate's frs-verify,
    # asserted through the same parser). This is a FAIL — it never false-fires on the current corpus.
    no_verify = [f.key for f in v.frs if not attr(f, "verify").strip()]
    for fid in no_verify:
        findings.append(Finding(
            "FR-4", _SEVERITY_FAIL, path.name,
            f"{path.name}: {fid} has no `Verify:` -- every FR needs an acceptance test.",
            fr=fid,
        ))
    # Serves-based traceability (broken Serves / unserved objective) rides on objective-NODE parsing,
    # which the shared source-projection does not extract reliably across the whole corpus (many docs
    # declare `## Objectives` yet project 0 objective nodes). Serves is itself OPTIONAL (det-req §5),
    # so these degrade to ADVISORY — reported for the author, never a false build-fail (FR-8). This
    # mirrors the corpus index, which shows a health glyph for the same signal but does not gate on it.
    orphans = v.orphan_frs()
    for f in orphans:
        findings.append(Finding(
            "FR-4", _SEVERITY_ADVISORY, path.name,
            f"{path.name}: {f.key} Serves an objective this doc does not declare as a node "
            "(broken Serves, or the objective section did not project) -- verify the objective exists.",
            fr=f.key,
        ))
    if v.uses_serves() and v.objectives:
        unserved = [o.key for o in v.objectives if not v.frs_for(o.key)]
        for okey in unserved:
            findings.append(Finding(
                "FR-4", _SEVERITY_ADVISORY, path.name,
                f"{path.name}: objective {okey} is served by no FR "
                "(a doc that uses Serves: should serve every objective).",
                fr=okey,
            ))
    return findings


def _check_index_freshness(spec_dir: Path, docs: List[Path]) -> List[Finding]:
    """FR-5 -- (advisory) the index link-set equals the doc-set on disk, structurally (not a byte-diff).

    Re-derives, in-memory, the set of ``REQ-*.md`` the corpus index (``render_index``) would link
    (``sorted(dir.glob("REQ-*.md"))``) and compares it to the docs on disk. Advisory: a freshly-added
    doc or a removed one is drift to report, not a build-fail (the index is a generated artifact,
    regenerated on demand). Degraded to advisory per FR-8 precision.
    """
    findings: List[Finding] = []
    would_link = {p.name for p in sorted(spec_dir.glob("REQ-*.md"))}
    on_disk = {p.name for p in docs}
    for extra in sorted(on_disk - would_link):
        findings.append(Finding(
            "FR-5", _SEVERITY_ADVISORY, extra,
            f"{extra}: present on disk but the corpus index would not link it -- "
            "regenerate the index (`startd8 navigator index --dir <corpus> --out ...`).",
        ))
    for stale in sorted(would_link - on_disk):
        findings.append(Finding(
            "FR-5", _SEVERITY_ADVISORY, stale,
            f"{stale}: the corpus index would link it but it is not in the governed doc set -- "
            "a stale index link (the doc was removed).",
        ))
    return findings


def _check_orphans(spec_dir: Path, docs: List[Path]) -> List[Finding]:
    """FR-3 (advisory tail) -- a REQ-*.md that no sibling references.

    Orphan = a doc whose local key (REQ-0N) appears in no OTHER doc's text. Lower-severity advisory.
    """
    findings: List[Finding] = []
    # Guard each read (robustness parity with govern_corpus) — an unreadable doc must not abort the
    # orphan scan; govern_corpus already flags it, so skipping it here for the reference-scan is safe.
    texts: Dict[str, str] = {}
    for p in docs:
        try:
            texts[p.name] = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
    for p in docs:
        m = re.match(r"(REQ-0[1-9])\b", p.stem)
        if not m:
            continue
        key = m.group(1)
        referenced = any(key in body for name, body in texts.items() if name != p.name)
        if not referenced:
            findings.append(Finding(
                "FR-3", _SEVERITY_ADVISORY, p.name,
                f"{p.name}: orphan doc -- {key} is referenced by no sibling in the corpus.",
                ref=key,
            ))
    return findings


# --------------------------------------------------------------------------- #
# the governor
# --------------------------------------------------------------------------- #

def check_determinism_regression(nodes, provenance, doc: str = "") -> List[Finding]:
    """REQ-19 FR-6 — planned-vs-realized self-monitoring: a node whose *planned* regime (the declared
    regime — the router's encoded intent, ``node_regime`` with no provenance) is ``deterministic`` but
    whose *measured* regime (``node_regime`` through the provenance source) is ``llm`` is a **determinism
    regression** — a named finding. Bounded to SURFACING (NR-1) — never remediates. Firewall-clean: reads
    only the realization module + the provenance contract, never a construction subsystem.
    """
    from .models import RealizationRegime
    from .realization import node_regime

    findings: List[Finding] = []
    for n in nodes:
        planned = node_regime(n, None)              # declared = the plan
        measured = node_regime(n, provenance)       # what construction actually did
        if planned == RealizationRegime.DETERMINISTIC and measured == RealizationRegime.LLM:
            findings.append(Finding(
                "FR-6", _SEVERITY_FAIL, doc or n.key,
                f"{doc or n.key}: node {n.key!r} was PLANNED deterministic (`$0`) but MEASURED llm — a "
                f"determinism regression (its realization drifted from its plan). Investigate the "
                f"generation path or re-route.",
                fr=n.key,
            ))
    return findings


def check_lesson_grounding(nodes, doc: str = "") -> List[Finding]:
    """REQ-20 FR-2 — a Lesson (``category=="lesson"``) that is not grounded (no ``derived-from`` edge or
    no ``lives`` evidence citing its outcome) is an **ungrounded belief** (cruft, invariant 4) — a named
    finding. A grounded Lesson yields none. Never a crash."""
    from .sources_retrospective import LESSON_CATEGORY, is_grounded

    findings: List[Finding] = []
    for n in nodes:
        if getattr(n, "category", "") == LESSON_CATEGORY and not is_grounded(n):
            findings.append(Finding(
                "FR-2", _SEVERITY_FAIL, doc or n.key,
                f"{doc or n.key}: Lesson {n.key!r} is ungrounded — it proposes a revision without a "
                f"`derived-from` edge + `lives` citing its outcome. A belief is cruft until grounded; "
                f"add its grounding or drop it.",
                fr=n.key,
            ))
    return findings


def check_realization_invariant(nodes, doc: str = "") -> List[Finding]:
    """REQ-18 FR-5 — invariant 9: an ``llm``-regime derivation edge obligates its target node's
    ``verify`` (the acceptance oracle) to be non-empty, firing **only once the node's ``lives`` evidence
    is present** (mirroring the ships_when⟺lives gate) so unbuilt/spec nodes never fail. A ``deterministic``
    or ``human`` edge imposes no such obligation. Each violation is a named finding — never a crash.
    """
    from .models import RealizationRegime
    from .realization import resolve_edge_regime

    findings: List[Finding] = []
    for n in nodes:
        # activation gate: an un-realized node (no lives) is never obligated; a satisfied one (verify set)
        # passes. Only a REALIZED node with an empty oracle can violate.
        if not getattr(n, "lives", None) or getattr(n, "verify", ""):
            continue
        for e in getattr(n, "derivation", ()):
            if resolve_edge_regime(n, e) == RealizationRegime.LLM:
                findings.append(Finding(
                    "FR-5", _SEVERITY_FAIL, doc or n.key,
                    f"{doc or n.key}: node {n.key!r} is realized by an llm-regime edge "
                    f"(from {e.from_key!r}) but its verify (acceptance oracle) is empty — invariant 9 "
                    f"requires a stochastic edge's target to carry a verify. Add a Verify: clause.",
                    fr=n.key,
                ))
                break  # one finding per node
    return findings


def govern_corpus(spec_dir: Path, *, realization_provenance=None) -> GovernReport:
    """Run the full governance battery over a directory of ``REQ-*.md`` docs (read-only).

    Returns a :class:`GovernReport`; ``report.exit_code`` is 0 (clean) / 1 (any fail-severity drift).
    Operational errors (missing dir) are the CLI's concern (exit 2), not this function's.

    ``realization_provenance`` (REQ-19 FR-6, optional): a measured :class:`ProvenanceSource`; when supplied,
    each doc's nodes are checked for planned-vs-realized determinism regressions. Absent → skipped (no
    measured signal to compare against), so the default battery is unchanged.
    """
    spec_dir = Path(spec_dir)
    docs = sorted(spec_dir.glob("REQ-*.md"))
    corpus_keys = set()
    for p in docs:
        m = re.match(r"(REQ-0[1-9])", p.stem)
        if m:
            corpus_keys.add(m.group(1))
    repo_root = _repo_root(spec_dir)

    report = GovernReport(corpus=str(spec_dir), docs=[p.name for p in docs])

    for p in docs:
        try:
            text = p.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            # one unreadable doc degrades to a single advisory, never aborts the sweep
            report.findings.append(Finding(
                "FR-1", _SEVERITY_ADVISORY, p.name, f"{p.name}: unreadable ({exc})."))
            continue
        report.findings.extend(_check_name_block(p, text))
        report.findings.extend(_check_single_line_fr(p, text))
        report.findings.extend(_check_dangling_xref(p, text, corpus_keys, repo_root))
        try:
            summary = _req_summary(p)
        except Exception:  # pragma: no cover - _req_summary is itself defensive
            summary = {"health": "info"}
        report.findings.extend(_check_coverage(p, summary))
        # REQ-18 FR-5: invariant 9 over the doc's projected requirement nodes. In approach (a) no
        # requirement edge declares an `llm` regime, so this never fires yet — it is wired + proven on
        # fixtures (test_govern) and ready for REQ-19 (b), when measured llm regimes appear.
        try:
            _req_nodes = nodes_from_requirements(p)
            report.findings.extend(check_realization_invariant(_req_nodes, p.name))
            # REQ-19 FR-6: planned-vs-realized regression, only when a measured provenance source is given.
            if realization_provenance is not None:
                report.findings.extend(
                    check_determinism_regression(_req_nodes, realization_provenance, p.name))
        except Exception:  # pragma: no cover - projection is itself defensive; never abort the sweep
            pass

    report.findings.extend(_check_orphans(spec_dir, docs))
    report.findings.extend(_check_index_freshness(spec_dir, docs))
    return report


def _repo_root(spec_dir: Path) -> Path:
    """Walk up from the spec dir to the repo root (the dir containing ``src`` + ``docs``)."""
    cur = spec_dir.resolve()
    for parent in [cur, *cur.parents]:
        if (parent / "src").is_dir() and (parent / "docs").is_dir():
            return parent
    return cur


# --------------------------------------------------------------------------- #
# renderers (text + json) -- no CSS/HTML (NR-7)
# --------------------------------------------------------------------------- #

def render_govern_text(report: GovernReport) -> str:
    """Human-readable governance report: per-check verdict + per-finding doc/fr/ref/fix."""
    L: List[str] = []
    banner = "CLEAN" if report.clean else "DRIFT"
    L.append(f"=== corpus governance -- {banner} "
             f"({len(report.docs)} docs, govern_score {report.govern_score()}) ===")
    L.append(f"corpus: {report.corpus}")
    L.append("")
    summary = report.checks_summary()
    labels = {
        "FR-1": "name-block presence",
        "FR-2": "single-line-FR",
        "FR-3": "dangling cross-ref",
        "FR-4": "coverage",
        "FR-5": "index-freshness",
    }
    for fr, counts in summary.items():
        ok = counts["fail"] == 0
        glyph = "PASS" if ok else "FAIL"
        adv = f", {counts['advisory']} advisory" if counts["advisory"] else ""
        L.append(f"  [{glyph}] {fr:5} {labels.get(fr, ''):22} "
                 f"{counts['fail']} fail{adv}")
    L.append("")
    if report.fail_findings:
        L.append(f"FAIL ({len(report.fail_findings)}):")
        for f in report.fail_findings:
            L.append(f"  x [{f.check}] {f.message}")
    if report.advisory_findings:
        L.append(f"ADVISORY ({len(report.advisory_findings)}):")
        for f in report.advisory_findings:
            L.append(f"  - [{f.check}] {f.message}")
    if report.clean and not report.advisory_findings:
        L.append("no findings -- the corpus obeys its discipline.")
    L.append("")
    L.append(f"-> exit {report.exit_code} "
             + ("(clean)" if report.exit_code == 0 else "(drift -- see FAIL above)"))
    return "\n".join(L)


def render_govern_json(report: GovernReport) -> str:
    """Machine-readable governance report (stable key order, ascii-safe)."""
    return json.dumps(report.to_dict(), indent=2, sort_keys=True, ensure_ascii=True) + "\n"


def recurring_finding_classes(report: GovernReport, *, threshold: int = 2) -> Dict[str, int]:
    """FR-7 -- finding-classes recurring across >=``threshold`` docs, routable to ``/metabolize-finding``.

    A check firing on many docs is a class to metabolize into a structural guard, not to re-file
    forever; the CLI surfaces the ``/metabolize-finding`` invocation for any such class.
    """
    per_check_docs: Dict[str, set] = {}
    for f in report.fail_findings:
        per_check_docs.setdefault(f.check, set()).add(f.doc)
    return {check: len(docs) for check, docs in per_check_docs.items() if len(docs) >= threshold}
