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
    checks.append(
        (
            "name-block",
            name_ok,
            (
                f"handle={handle.group(1).strip() if handle else 'MISSING'}"
                if name_ok
                else "no deterministic name block (Readable handle + Semantic name)"
            ),
        )
    )

    frs = parse_fr_lines(text)
    marker_count = len(_FR_MARKER.findall(text))
    parse_ok = len(frs) > 0 and len(frs) == marker_count
    checks.append(
        (
            "frs-parse",
            parse_ok,
            f"{len(frs)} FR(s) parse, {marker_count} bullet marker(s)"
            + (
                "" if parse_ok else " -- MISMATCH: a hard-wrapped FR is dropping fields"
            ),
        )
    )

    missing_name = [f["id"] for f in frs if not f.get("name")]
    named_ok = bool(frs) and not missing_name
    checks.append(
        (
            "frs-named",
            named_ok,
            (
                "every FR has a deterministic Name:"
                if named_ok
                else f"FRs missing Name: {', '.join(missing_name) or '(no FRs)'}"
            ),
        )
    )

    missing_verify = [f["id"] for f in frs if not f.get("verify")]
    verify_ok = bool(frs) and not missing_verify
    checks.append(
        (
            "frs-verify",
            verify_ok,
            (
                "every FR has an acceptance Verify:"
                if verify_ok
                else f"FRs missing Verify: {', '.join(missing_verify) or '(no FRs)'}"
            ),
        )
    )

    missing_serves = [f["id"] for f in frs if not f.get("serves")]
    serves_ok = bool(frs) and not missing_serves
    checks.append(
        (
            "frs-serves",
            serves_ok,
            (
                "every FR links an objective Serves:"
                if serves_ok
                else f"FRs missing Serves: {', '.join(missing_serves) or '(no FRs)'}"
            ),
        )
    )

    ok = all(c[1] for c in checks)
    return {
        "path": path,
        "ok": ok,
        "checks": checks,
        "frs": len(frs),
        "blocked": [c[0] for c in checks if not c[1]],
    }


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
        d: Dict[str, Any] = {
            "check": self.check,
            "severity": self.severity,
            "doc": self.doc,
            "message": self.message,
        }
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
        findings.append(
            Finding(
                "FR-1",
                _SEVERITY_FAIL,
                path.name,
                f"{path.name}: name block missing {', '.join(missing)} -- "
                "add the deterministic NAME BLOCK (Readable handle + Semantic name) "
                "per NAMING_CONVENTION.md (a doc identified by integer+type alone is the anti-pattern).",
            )
        )
    # Canonical ref is the ADDED check (gate_spec doesn't assert it). Degraded to ADVISORY so it
    # never fails a doc that predates the canonical-ref convention (FR-8 precision gate: a heuristic
    # that cannot reach zero false positives on the current corpus degrades, never fails the build).
    elif not canonical:
        findings.append(
            Finding(
                "FR-1",
                _SEVERITY_ADVISORY,
                path.name,
                f"{path.name}: name block has no `Canonical ref:` -- add "
                "`cc:intent:<initiative>:<kind>:<key>` for a stable, wording-independent machine identity.",
            )
        )
    # every FR bullet must carry an authored Name: (reuse the shared parser, not a new one)
    frs = parse_fr_lines(text)
    unnamed = [f["id"] for f in frs if not f.get("name")]
    for fid in unnamed:
        findings.append(
            Finding(
                "FR-1",
                _SEVERITY_FAIL,
                path.name,
                f"{path.name}: {fid} has no `Name:` field -- add a semantic Name: "
                "(actor.action.object.outcome) so it is not identified by its integer key alone.",
                fr=fid,
            )
        )
    return findings


def _check_single_line_fr(path: Path, text: str) -> List[Finding]:
    """FR-2 -- every FR bullet is one physical line (the same marker-count-vs-parse dogfood the loop
    stage-0 gate uses verbatim: a hard-wrapped bullet drops the fields the per-line parser can't see).
    """
    frs = parse_fr_lines(text)
    marker_count = len(_FR_MARKER.findall(text))
    if marker_count and len(frs) != marker_count:
        return [
            Finding(
                "FR-2",
                _SEVERITY_FAIL,
                path.name,
                f"{path.name}: {marker_count} FR bullet marker(s) but only {len(frs)} parse -- "
                "a hard-wrapped FR is silently dropping Name:/Touches:/Lives:/Verify:; "
                "put each FR on ONE physical line.",
            )
        ]
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
        r"Library seams[^:]*:\s*(.+?)(?:\n\n|Primitives reused|\Z)", text, re.DOTALL
    )
    if seam_block:
        for tok in _PATH_TOKEN.findall(seam_block.group(1)):
            own.add(tok.strip().strip("`").lstrip("./"))
    return {p for p in own if p}


def _check_dangling_xref(
    path: Path, text: str, corpus_keys: set, repo_root: Path
) -> List[Finding]:
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
            findings.append(
                Finding(
                    "FR-3",
                    _SEVERITY_FAIL,
                    path.name,
                    f"{path.name}: cites {key} but no {key}-*.md exists in the corpus -- "
                    "a dangling cross-ref (the doc was renamed away or never existed).",
                    ref=key,
                )
            )

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
        findings.append(
            Finding(
                "FR-3",
                _SEVERITY_ADVISORY,
                path.name,
                f"{path.name}: cites path `{tok}` that does not resolve to a repo file "
                "(and is not this doc's own declared deliverable) -- verify it wasn't moved/renamed.",
                ref=tok,
            )
        )
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
    except (
        Exception
    ):  # pragma: no cover - defensive; the index already degraded it to 'info' above
        return []
    if not v.frs:
        findings.append(
            Finding(
                "FR-4",
                _SEVERITY_FAIL,
                path.name,
                f"{path.name}: declares no FRs -- a REQ needs >=1 functional requirement.",
            )
        )
        return findings
    # High-confidence coverage: every FR needs an acceptance Verify: (the loop gate's frs-verify,
    # asserted through the same parser). This is a FAIL — it never false-fires on the current corpus.
    no_verify = [f.key for f in v.frs if not attr(f, "verify").strip()]
    for fid in no_verify:
        findings.append(
            Finding(
                "FR-4",
                _SEVERITY_FAIL,
                path.name,
                f"{path.name}: {fid} has no `Verify:` -- every FR needs an acceptance test.",
                fr=fid,
            )
        )
    # Serves-based traceability (broken Serves / unserved objective) rides on objective-NODE parsing,
    # which the shared source-projection does not extract reliably across the whole corpus (many docs
    # declare `## Objectives` yet project 0 objective nodes). Serves is itself OPTIONAL (det-req §5),
    # so these degrade to ADVISORY — reported for the author, never a false build-fail (FR-8). This
    # mirrors the corpus index, which shows a health glyph for the same signal but does not gate on it.
    orphans = v.orphan_frs()
    for f in orphans:
        findings.append(
            Finding(
                "FR-4",
                _SEVERITY_ADVISORY,
                path.name,
                f"{path.name}: {f.key} Serves an objective this doc does not declare as a node "
                "(broken Serves, or the objective section did not project) -- verify the objective exists.",
                fr=f.key,
            )
        )
    if v.uses_serves() and v.objectives:
        unserved = [o.key for o in v.objectives if not v.frs_for(o.key)]
        for okey in unserved:
            findings.append(
                Finding(
                    "FR-4",
                    _SEVERITY_ADVISORY,
                    path.name,
                    f"{path.name}: objective {okey} is served by no FR "
                    "(a doc that uses Serves: should serve every objective).",
                    fr=okey,
                )
            )
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
        findings.append(
            Finding(
                "FR-5",
                _SEVERITY_ADVISORY,
                extra,
                f"{extra}: present on disk but the corpus index would not link it -- "
                "regenerate the index (`startd8 navigator index --dir <corpus> --out ...`).",
            )
        )
    for stale in sorted(would_link - on_disk):
        findings.append(
            Finding(
                "FR-5",
                _SEVERITY_ADVISORY,
                stale,
                f"{stale}: the corpus index would link it but it is not in the governed doc set -- "
                "a stale index link (the doc was removed).",
            )
        )
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
            findings.append(
                Finding(
                    "FR-3",
                    _SEVERITY_ADVISORY,
                    p.name,
                    f"{p.name}: orphan doc -- {key} is referenced by no sibling in the corpus.",
                    ref=key,
                )
            )
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
        planned = node_regime(n, None)  # declared = the plan
        measured = node_regime(n, provenance)  # what construction actually did
        if (
            planned == RealizationRegime.DETERMINISTIC
            and measured == RealizationRegime.LLM
        ):
            findings.append(
                Finding(
                    "FR-6",
                    _SEVERITY_FAIL,
                    doc or n.key,
                    f"{doc or n.key}: node {n.key!r} was PLANNED deterministic (`$0`) but MEASURED llm — a "
                    f"determinism regression (its realization drifted from its plan). Investigate the "
                    f"generation path or re-route.",
                    fr=n.key,
                )
            )
    return findings


def check_auto_revise_audit(audits, doc: str = "") -> List[Finding]:
    """REQ-21 FR-6 — autonomy with a trail: every auto-applied revise MUST carry a complete audit record
    (lesson · target · byte-identity guard result · timestamp · revert reference). An incomplete/silent
    record is a named finding — an unaudited autonomous change is exactly what the auto-tier forbids.
    """
    findings: List[Finding] = []
    for a in audits:
        d = a.to_dict() if hasattr(a, "to_dict") else dict(a)
        missing = [
            k
            for k in ("lesson", "target", "guard_result", "timestamp", "revert_ref")
            if not d.get(k) and d.get(k) is not False
        ]
        if not d.get("revert_ref"):
            missing = list(
                dict.fromkeys(missing + ["revert_ref"])
            )  # a revert_ref is mandatory (reversible)
        if missing:
            findings.append(
                Finding(
                    "FR-6",
                    _SEVERITY_FAIL,
                    doc or str(d.get("lesson", "?")),
                    f"auto-applied revise from lesson {d.get('lesson', '?')!r} has an incomplete audit record "
                    f"(missing {', '.join(missing)}) — an auto-apply must never be silent or irreversible.",
                    fr=str(d.get("lesson", "")),
                )
            )
    return findings


def _gate_liveness(node) -> tuple:
    """REQ-22 — resolve a node's verify GATE liveness WITHOUT executing (structural, NR-2/NR-3), reusing
    ``verify_oracle``'s classifier. Returns ``(state, gate, reason)`` where state is ``live`` /
    ``dead-structural`` (gap — doesn't resolve to a runnable command) / ``unrunnable-provenance``
    (candidate — resolves but references a missing input) / ``no-gate``."""
    from .verify_oracle import KIND_COMMAND, _classify_clause, _referenced_missing_path

    gate = str(getattr(node, "verify_gate", "") or "").strip()
    if not gate:
        return ("no-gate", "", "")
    kind, argv, reason = _classify_clause(gate)
    if kind != KIND_COMMAND or argv is None:
        return (
            "dead-structural",
            gate,
            reason,
        )  # present but does not resolve → a FACT (gap)
    missing = _referenced_missing_path(argv)
    if missing:
        return (
            "unrunnable-provenance",
            gate,
            f"missing input {missing}",
        )  # a provenance CANDIDATE
    return ("live", gate, "")


def check_verify_liveness(nodes, doc: str = "") -> List[Finding]:
    """REQ-22 FR-2/3/4 — flag a REALIZED node whose verify GATE is present-but-dead (a durable green
    carrying no truth). Reuses ``verify_oracle`` (no new engine, NR-2). STRUCTURAL death (the gate no
    longer resolves to a runnable command) ships as a **GAP** (a fact, ``_SEVERITY_FAIL``); a gate that
    resolves but can't run for a provenance reason ships as a precision-governed **candidate**
    (``_SEVERITY_ADVISORY``) — the absence-vs-error move (FR-4). Only realized nodes (``lives`` present)
    are checked — an un-built node's liveness is unknown (the invariant-9 activation gate). Advisory (NR-1).
    """
    findings: List[Finding] = []
    for n in nodes:
        if not getattr(n, "lives", None):
            continue
        state, gate, reason = _gate_liveness(n)
        if state == "dead-structural":
            findings.append(
                Finding(
                    "FR-2",
                    _SEVERITY_FAIL,
                    doc or n.key,
                    f"{doc or n.key}: node {n.key!r} claims a verify gate {gate!r} that does NOT resolve to a "
                    f"runnable command ({reason}) — present but DEAD (a durable green carrying no truth). Fix "
                    f"the gate or route to a retrospective revision.",
                    fr=n.key,
                    ref="gap:structural",
                )
            )
        elif state == "unrunnable-provenance":
            findings.append(
                Finding(
                    "FR-2",
                    _SEVERITY_ADVISORY,
                    doc or n.key,
                    f"{doc or n.key}: node {n.key!r} gate {gate!r} resolves but can't run ({reason}) — "
                    f"unrunnable-here for a provenance reason (not a territory failure). A precision candidate.",
                    fr=n.key,
                    ref="candidate:provenance",
                )
            )
    return findings


def recheck_verify_liveness_on_drift(
    nodes, changed_impl_keys, doc: str = ""
) -> List[Finding]:
    """REQ-22 FR-5 (the drift move) — when the implementation a gate depends on changes provenance
    (``changed_impl_keys`` = the impl node keys whose provenance moved), re-check the liveness of gates
    that depend on it (via a derivation edge or a lives ref to that impl), catching a gate-voiding refactor
    at the fracture. Returns the re-check findings for exactly the affected nodes."""
    changed = set(changed_impl_keys or ())

    def _depends_on_changed(n) -> bool:
        if any(e.from_key in changed for e in getattr(n, "derivation", ()) or ()):
            return True
        return any(
            ev.ref in changed or ev.ref.split(":")[-1] in changed
            for ev in getattr(n, "lives", ()) or ()
        )

    return check_verify_liveness([n for n in nodes if _depends_on_changed(n)], doc)


def check_target_unmeasured(outcome_nodes, doc: str = "") -> List[Finding]:
    """REQ-23 FR-2 — a fact cell of the liveness layer: an outcome (``category=="objective"``) that carries
    a ``target`` (a measurable goal) but has NO bound live signal (``target_signal`` empty) is a structural
    GAP — a claim with no attestation (the authoring-time twin of Feature-Observability's loud-gap-for-a-
    goal-with-no-live-signal). A bound signal → clean. Advisory (NR-1)."""
    findings: List[Finding] = []
    for n in outcome_nodes:
        if getattr(n, "category", "") != "objective":
            continue
        attrs = getattr(n, "attributes", {}) or {}
        if (
            attrs.get("target", "").strip()
            and not attrs.get("target_signal", "").strip()
        ):
            findings.append(
                Finding(
                    "FR-2",
                    _SEVERITY_FAIL,
                    doc or n.key,
                    f"{doc or n.key}: objective {n.key!r} carries a target but NO bound live signal — an "
                    f"unmeasured target is a claim with no attestation. Bind a `Signal:` to a live measurement "
                    f"or route to a retrospective revision.",
                    fr=n.key,
                    ref="liveness:target-unmeasured",
                )
            )
    return findings


def _fr_verify_is_dead(fr) -> bool:
    """An FR fails verify-liveness when its gate is structurally dead (REQ-22). A prose-only FR (no gate)
    is UNAUTOMATED, not dead — it doesn't count against a served outcome's roll-up."""
    return _gate_liveness(fr)[0] == "dead-structural"


def check_served_by_dead_fr(fr_nodes, doc: str = "") -> List[Finding]:
    """REQ-23 FR-3 — verify-liveness (REQ-22) rolled up the serves-edge: an outcome that is SERVED (≥1 FR
    names it in ``Serves:``) but ALL of whose realized serving FRs fail verify-liveness is a GAP — served-
    on-paper while its guarantee is dead. Min-rolls-up: ≥1 live serving FR ⇒ clean. Reuses REQ-22 (NR-2).
    """
    by_objective: Dict[str, List] = {}
    for fr in fr_nodes:
        for served in (
            (getattr(fr, "attributes", {}) or {}).get("serves", "").split(",")
        ):
            served = served.strip()
            if served:
                by_objective.setdefault(served, []).append(fr)
    findings: List[Finding] = []
    for objective, frs in sorted(by_objective.items()):
        realized = [f for f in frs if getattr(f, "lives", None)]
        if realized and all(_fr_verify_is_dead(f) for f in realized):
            findings.append(
                Finding(
                    "FR-3",
                    _SEVERITY_FAIL,
                    doc or objective,
                    f"{doc or objective}: outcome {objective!r} is served by {len(realized)} realized FR(s) but "
                    f"ALL of them fail verify-liveness (dead gates) — served-on-paper while its guarantee is "
                    f"dead. Repair a serving FR's verify or route to a retrospective revision.",
                    fr=objective,
                    ref="liveness:served-by-a-dead-fr",
                )
            )
    return findings


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# REQ-25 — the liveness layer's HYPOTHESIS cells (fact-rungs ship, judgment-rungs park-by-default).
#
# REQ-22/23 shipped the *fact* cells (structural death → GAP). The census left three *hypothesis* cells
# — mitigation-inert / non-goal-violated / touches-dead — that check SEMANTIC death. Each decomposes into
# a deterministic FACT-RUNG (ships as a GAP/trigger, REUSING an existing checker — NR-2) and a semantic
# JUDGMENT-RUNG (parked-by-default behind a precision gate — NR-3/NR-4; a false GAP is a durable-red-
# carrying-no-truth). This module ships the fact-rungs + the parking machinery; the judgment EXECUTION is
# inert until a labeled fixture set un-parks it (NR-6).
# ══════════════════════════════════════════════════════════════════════════════════════════════════

_LANG_BY_EXT = {
    ".py": "python",
    ".go": "go",
    ".js": "javascript",
    ".ts": "typescript",
    ".java": "java",
    ".cs": "csharp",
}


def _first_code_lives(node, repo_root=None) -> "Path | None":
    """The first ``lives`` evidence ref that resolves to an EXISTING code file (the realized artifact the
    fact-rungs inspect). ``ref`` may be ``type:path`` or a bare path; joined under ``repo_root`` when given.
    Returns ``None`` when the node cites no on-disk code (un-realized → its liveness is unknown, not dead).
    """
    root = Path(repo_root) if repo_root else None
    for ev in getattr(node, "lives", ()) or ():
        raw = (getattr(ev, "ref", "") or "").strip()
        cand = (
            raw.split(":", 1)[1]
            if ":" in raw and not raw.split(":", 1)[0].isdigit()
            else raw
        )
        for p in ((root / cand) if root else Path(cand), Path(cand)):
            if p.suffix in _LANG_BY_EXT and p.is_file():
                return p
    return None


def _ast_imports(src: str) -> List[str]:
    """Every imported module name in a Python source (reuse the ``ast`` machinery — NR-2). Records the
    module AND, for ``from X import Y``, both ``X`` and the fully-qualified ``X.Y`` — so a ban on ``Y``
    catches ``from X import Y`` (which records module ``X`` alone). A syntax error → ``[]`` (never crash).
    """
    import ast

    try:
        tree = ast.parse(src)
    except SyntaxError:
        return []
    out: List[str] = []
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            out += [a.name for a in n.names]
        elif isinstance(n, ast.ImportFrom):
            mod = n.module or ""
            out.append(mod)
            out += [f"{mod}.{a.name}" if mod else a.name for a in n.names]
    return out


# FR-1 — the named security mitigations the query_prime/security verifier can attest, keyed by the
# ``security_mitigation`` attribute a node declares.
def _mitigation_check_type(mitig: str):
    from startd8.query_prime.models import SecurityCheckType

    return {
        "injection": SecurityCheckType.INJECTION,
        "credential": SecurityCheckType.CREDENTIAL_LEAKAGE,
        "credentials": SecurityCheckType.CREDENTIAL_LEAKAGE,
        "lifecycle": SecurityCheckType.LIFECYCLE,
    }.get(mitig.strip().lower())


def check_mitigation_inert(nodes, repo_root=None, doc: str = "") -> List[Finding]:
    """REQ-25 FR-1 — the ``mitigation-inert`` FACT-rung: a node declaring a named security mitigation
    (``attributes['security_mitigation']`` ∈ injection|credentials|lifecycle) whose realized code the
    ``query_prime/security`` verifier reports the mitigation ABSENT for (a finding of that class) → GAP —
    the mitigation is present in the spec but not live in the code. REUSES ``verify_file`` (NR-2, no new
    checker). Only realized nodes (a lives code file). Never crashes (a bad file → skip). Advisory (NR-1).
    """
    findings: List[Finding] = []
    for n in nodes:
        mitig = str(
            (getattr(n, "attributes", {}) or {}).get("security_mitigation", "")
        ).strip()
        check_type = _mitigation_check_type(mitig) if mitig else None
        if check_type is None:
            continue
        path = _first_code_lives(n, repo_root)
        if path is None:
            continue
        try:
            from startd8.query_prime.models import DatabaseType
            from startd8.query_prime.security import verify_file

            result = verify_file(
                path.read_text(encoding="utf-8"),
                str(path),
                DatabaseType.SQLITE,
                _LANG_BY_EXT.get(path.suffix, "python"),
            )
        except (
            Exception
        ):  # pragma: no cover - the verifier is defensive; a bad file never aborts the sweep
            continue
        if any(
            getattr(f, "check_type", None) == check_type
            for f in getattr(result, "findings", ()) or ()
        ):
            findings.append(
                Finding(
                    "FR-1",
                    _SEVERITY_FAIL,
                    doc or n.key,
                    f"{doc or n.key}: node {n.key!r} declares the security mitigation {mitig!r} but the verifier "
                    f"reports it ABSENT in {path} — present in the spec, not live in the code (mitigation-inert). "
                    f"Repair the mitigation or route to a retrospective revision.",
                    fr=n.key,
                    ref="liveness:mitigation-inert",
                )
            )
    return findings


def check_non_goal_violated(nodes, repo_root=None, doc: str = "") -> List[Finding]:
    """REQ-25 FR-2 — the ``non-goal-violated`` FACT-rung: a node whose ``wont`` declares a structural import
    ban (``no-import:<module>``) that its realized Python code VIOLATES (AST imports the banned module) →
    GAP. REUSES the import/AST machinery (NR-2). Non-Python lives are skipped (AST is Python). Advisory.
    """
    findings: List[Finding] = []
    for n in nodes:
        bans = [
            w.split("no-import:", 1)[1].strip()
            for w in (getattr(n, "wont", ()) or ())
            if "no-import:" in w
        ]
        if not bans:
            continue
        path = _first_code_lives(n, repo_root)
        if path is None or path.suffix != ".py":
            continue
        try:
            imported = _ast_imports(path.read_text(encoding="utf-8"))
        except OSError:  # pragma: no cover
            continue
        violated = sorted({b for b in bans if any(b in m for m in imported)})
        if violated:
            findings.append(
                Finding(
                    "FR-2",
                    _SEVERITY_FAIL,
                    doc or n.key,
                    f"{doc or n.key}: node {n.key!r} declares the non-goal 'no-import: {', '.join(violated)}' but "
                    f"{path} imports it — a structural non-goal the code violates. Remove the import or route to "
                    f"a retrospective revision.",
                    fr=n.key,
                    ref="liveness:non-goal-violated",
                )
            )
    return findings


def check_touches_provenance_changed(
    nodes, changed_provenance_keys, doc: str = ""
) -> List[Finding]:
    """REQ-25 FR-3 — the ``touches-dead`` FACT-trigger: a node whose Touches'd/lives file's realization
    provenance CHANGED since its last attestation (``changed_provenance_keys`` = the REQ-19 provenance-
    change signal, reused exactly as ``recheck_verify_liveness_on_drift`` consumes ``changed_impl_keys``)
    raises a re-judge TRIGGER — a fact (the file moved), not yet a judgment (whether the claim still holds).
    An unchanged Touches'd file raises none. REUSES REQ-19 provenance-change (NR-2)."""
    changed = set(changed_provenance_keys or ())
    if not changed:
        return []
    findings: List[Finding] = []
    for n in nodes:
        hit = sorted(
            {
                ev.ref
                for ev in (getattr(n, "lives", ()) or ())
                if ev.ref in changed or ev.ref.split(":")[-1] in changed
            }
        )
        if hit:
            findings.append(
                Finding(
                    "FR-3",
                    _SEVERITY_FAIL,
                    doc or n.key,
                    f"{doc or n.key}: node {n.key!r} Touches file(s) {hit} whose realization provenance CHANGED "
                    f"since last attestation — a re-judge trigger: re-verify whether the claim still holds "
                    f"against the changed code, or route to a retrospective revision.",
                    fr=n.key,
                    ref="liveness:touches-provenance-changed",
                )
            )
    return findings


# ── FR-4/5/6 — the judgment-rung parking machinery (declared, not executed until precision-cleared) ──

# REQ-07 FR-7: a semantic judgment-rung un-parks only above this measured precision on a labeled fixture
# set — below it (or with no baseline) the rung stays parked and executes nothing (NR-3).
PRECISION_THRESHOLD = 0.9


@dataclass(frozen=True)
class JudgmentRung:
    """A cell's SEMANTIC judgment-rung — the residual judgment its fact-rung can't make deterministically.
    Parked by default: it executes ONLY when it clears the precision threshold on a labeled fixture set
    (``precision``) AND its LLM-judge is verify-live (``judge_verify_live``, FR-6 — the judge is itself
    LLM-realized ⇒ invariant 9 ⇒ must carry a live verify, so the checker never trips its own class).
    """

    cell: str
    precision: "float | None" = (
        None  # measured on a labeled fixture set; None → no baseline → parked
    )
    judge_verify_live: bool = (
        False  # FR-6: the judge carries a live verify (invariant 9)
    )


def judgment_rung_for(cell: str, *, precision=None, judge=None) -> JudgmentRung:
    """Build a :class:`JudgmentRung`, deriving ``judge_verify_live`` from the ``judge`` node's own verify
    gate (FR-6 dogfood: reuse ``_gate_liveness`` — the judge un-parks a rung only if the judge itself is
    verify-live). No judge → not live → parked."""
    live = bool(judge is not None and _gate_liveness(judge)[0] == "live")
    return JudgmentRung(cell=cell, precision=precision, judge_verify_live=live)


def is_unparked(rung: JudgmentRung) -> bool:
    """FR-4/FR-6 — a judgment-rung executes ONLY when it clears the precision threshold AND its judge is
    verify-live. Default (no baseline / non-live judge) → parked (``False``)."""
    return (
        rung.precision is not None
        and rung.precision >= PRECISION_THRESHOLD
        and rung.judge_verify_live
    )


def run_judgment_rung(
    rung: JudgmentRung, candidates=(), doc: str = ""
) -> List[Finding]:
    """FR-4/FR-5 — a PARKED rung executes nothing (returns ``[]``, NR-3). An UN-PARKED rung emits precision-
    governed CANDIDATES (``_SEVERITY_ADVISORY``, evidence-citing, dismissible-in-one-glance) — NEVER a GAP
    (NR-4: a false judgment is dismissible, not trusted as a fact). Each ``candidate`` is a mapping with
    ``key`` (the node) + ``evidence`` (the cited bytes)."""
    if not is_unparked(rung):
        return []  # FR-4 parked → executes nothing
    out: List[Finding] = []
    for c in candidates:
        key = str(c.get("key", ""))
        out.append(
            Finding(
                "FR-5",
                _SEVERITY_ADVISORY,
                doc or key,
                f"{doc or key}: candidate ({rung.cell}) — {c.get('evidence', '')}. A precision-governed "
                f"judgment (precision {rung.precision}), dismissible in one glance; NOT a fact.",
                fr=key,
                ref=f"candidate:{rung.cell}",
            )
        )
    return out


# ── REQ-25 FR-4 — the LABELED FIXTURE SET that grounds the precision gate ────────────────────────────
#
# A judgment-rung's ``precision`` is not a hand-passed magic float — it is MEASURED by running a candidate
# judge over a labeled fixture set and computing precision (the NR-4 metric: a false GAP is the enemy, so
# precision, not recall). Only a measured precision at/above the threshold — AND a verify-live judge (FR-6)
# — un-parks the rung. The fixtures are the residual SEMANTIC cases the deterministic fact-rung can't catch.


@dataclass(frozen=True)
class JudgmentFixture:
    """One labeled evaluation case for a hypothesis cell's judgment-rung. ``label`` is the ground truth for
    the POSITIVE class (``True`` = inert / violated / dead). ``input`` is the case a candidate judge sees.
    """

    cell: str
    id: str
    label: bool
    input: Dict[str, Any] = field(default_factory=dict)
    name: str = ""
    rationale: str = ""


def load_judgment_fixtures(path) -> List["JudgmentFixture"]:
    """Load the labeled fixture set (a ``{"fixtures": [...]}`` JSON doc). Each entry → a
    :class:`JudgmentFixture`. A missing/malformed file raises (the caller decides — an absent fixture set
    keeps every rung parked, which is the safe default)."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    rows = data.get("fixtures", data) if isinstance(data, dict) else data
    return [
        JudgmentFixture(
            cell=str(d["cell"]),
            id=str(d["id"]),
            label=bool(d["label"]),
            input=dict(d.get("input", {})),
            name=str(d.get("name", "")),
            rationale=str(d.get("rationale", "")),
        )
        for d in rows
    ]


def measure_precision(fixtures, judge) -> "float | None":
    """Precision — ``TP / (TP + FP)`` — of a candidate ``judge`` (``input -> bool``, ``True`` = predicts the
    positive class) over labeled ``fixtures``. NR-4 gates on PRECISION, not recall: a false positive is a
    durable-red-carrying-no-truth, so a judge that cries wolf scores low and stays parked. Returns ``None``
    when the judge predicts NO positives (precision undefined → un-provable → parked).
    """
    tp = fp = 0
    for fx in fixtures:
        if judge(getattr(fx, "input", {})):
            if fx.label:
                tp += 1
            else:
                fp += 1
    return (tp / (tp + fp)) if (tp + fp) else None


def measured_judgment_rung(
    cell: str, fixtures, judge, *, judge_node=None
) -> "JudgmentRung":
    """FR-4 grounding — build a :class:`JudgmentRung` whose ``precision`` is MEASURED over the ``cell``'s
    labeled fixtures (not a hand-passed float), with ``judge_verify_live`` derived from ``judge_node``'s own
    verify gate (FR-6 dogfood). The rung un-parks (via :func:`is_unparked`) iff that measured precision
    clears :data:`PRECISION_THRESHOLD` AND the judge is verify-live — so un-parking is grounded in data.
    """
    cell_fx = [f for f in fixtures if f.cell == cell]
    precision = measure_precision(cell_fx, judge)
    live = bool(judge_node is not None and _gate_liveness(judge_node)[0] == "live")
    return JudgmentRung(cell=cell, precision=precision, judge_verify_live=live)


def check_liveness_layer(
    fr_nodes,
    outcome_nodes=(),
    doc: str = "",
    *,
    repo_root=None,
    changed_provenance_keys=(),
    judgment_rungs=(),
    runtime_emission=None,
) -> List[Finding]:
    """REQ-23 FR-5 + REQ-25 FR-7 — the single ``liveness`` govern layer: run every present-but-dead cell
    (REQ-22 verify-liveness + REQ-23 target-unmeasured/served-by-a-dead-FR + REQ-25 mitigation-inert/
    non-goal-violated/touches-provenance-changed) and report them under ONE heading — each finding's
    ``ref`` carries a ``liveness:<cell>`` tag. The REQ-25 fact-rungs are Tier-1 (always run); the semantic
    judgment-rungs are Tier-2 (``judgment_rungs``) — parked by default, executing nothing until a labeled
    fixture set un-parks them (FR-4), and even then emitting candidates, never GAPs (FR-5). A clean corpus
    with the default (no security_mitigation / no-import wont / no changed provenance / no rungs) → the new
    cells add nothing (byte-identical, FR-8).

    REQ-28 adds the DEEPEST cell above the static ones: ``runtime_emission`` (a
    ``runtime_grounding.RuntimeEmission`` observation of the territory) surfaces a declared feature that
    emits no live signal. It is strictly opt-in — absent, the layer is byte-identical, so the fixed REQ-06
    battery never gains a runtime dependency (charter NR-6)."""
    layer: List[Finding] = [
        Finding(
            f.check, f.severity, f.doc, f.message, f.fr, ref="liveness:verify-liveness"
        )
        for f in check_verify_liveness(fr_nodes, doc)
    ]
    layer += check_target_unmeasured(outcome_nodes, doc)
    layer += check_served_by_dead_fr(fr_nodes, doc)
    # REQ-25 Tier-1 fact-rungs (reuse; ship as GAP/trigger)
    layer += check_mitigation_inert(fr_nodes, repo_root, doc)
    layer += check_non_goal_violated(fr_nodes, repo_root, doc)
    layer += check_touches_provenance_changed(fr_nodes, changed_provenance_keys, doc)
    # REQ-25 Tier-2 judgment-rungs (parked-by-default; candidates, never GAPs)
    for rung in judgment_rungs or ():
        layer += run_judgment_rung(rung, doc=doc)
    # REQ-28 — the RUNTIME cell (opt-in): the territory's answer to "does the declared feature emit?".
    # Imported lazily so the layer's default path carries no runtime-o11y dependency at all.
    if runtime_emission is not None:
        from .runtime_grounding import check_runtime_verify_liveness

        layer += check_runtime_verify_liveness(
            list(fr_nodes or ()) + list(outcome_nodes or ()), runtime_emission, doc
        )
    return layer


def lessons_from_liveness_layer(findings, *, confidence=None) -> List["Any"]:
    """REQ-25 FR-7 — route each CONFIRMED-dead liveness GAP (a ``_SEVERITY_FAIL`` ``liveness:*`` finding) to
    a human-gated retrospective ``Lesson`` (REQ-20, propose-don't-dispose). Advisory CANDIDATES (a parked/
    precision judgment) are NOT routed — only facts become proposed revisions. Reuses REQ-22's
    ``build_lesson_from_liveness_gap`` (NR-2)."""
    from .sources_retrospective import build_lesson_from_liveness_gap

    return [
        build_lesson_from_liveness_gap(f, confidence=confidence)
        for f in findings
        if f.severity == _SEVERITY_FAIL and str(f.ref).startswith("liveness:")
    ]


# --------------------------------------------------------------------------- #
# REQ-27 — the self-dogfood gate: the built liveness layer turned on our OWN corpus
# --------------------------------------------------------------------------- #

# The self-gate's finding refs (its own namespace — these never join the fixed REQ-06 battery, NR-6).
_SELF_DOGFOOD_GAP = "self-dogfood:mechanical-gateless"
_SELF_DOGFOOD_DEAD = "self-dogfood:dead-gate"
_SELF_DOGFOOD_OVERRIDE = "self-dogfood:manual-override"
_SELF_DOGFOOD_ADOPTION = "self-dogfood:adoption"


@dataclass(frozen=True)
class SelfDogfoodRow:
    """REQ-27 FR-1 — one corpus FR's honesty split: what its verify CLAIMS vs what it CARRIES.

    ``kind`` is ``verify_oracle``'s classification of the prose verify (``command`` = it names a runnable
    span, so it claims mechanical attestation; ``assertion``/``manual`` = human acceptance). ``gate_state``
    is ``_gate_liveness``'s structural resolution of the authored ``Gate:`` handle (REQ-22). ``mechanical``
    is the split itself: the verify claims a runnable check AND the author did not override it ``Manual:``.
    """

    doc: str
    fr: str
    kind: str  # verify_oracle: command | assertion | manual
    mechanical: bool  # kind == command AND no explicit `Manual:` override
    gate: str = ""
    gate_state: str = "no-gate"  # live | dead-structural | unrunnable-provenance | no-gate
    manual_marker: str = ""  # the `Manual:` rationale ("" = unmarked)

    @property
    def marked_manual(self) -> bool:
        """True iff the author EXPLICITLY marked the verify manual (REQ-27 FR-3)."""
        return bool(self.manual_marker.strip())

    @property
    def honest_manual(self) -> bool:
        """Legitimately human-checked: explicitly marked, or prose-by-kind (``assertion``/``manual``) —
        honest-by-kind needs no marker; the marker is the OVERRIDE for a command-shaped verify (FR-3)."""
        return not self.mechanical

    @property
    def gateless(self) -> bool:
        return not self.gate.strip()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "doc": self.doc,
            "fr": self.fr,
            "kind": self.kind,
            "mechanical": self.mechanical,
            "gate": self.gate,
            "gate_state": self.gate_state,
            "manual_marker": self.manual_marker,
        }


@dataclass
class SelfDogfoodReport:
    """REQ-27 FR-1/FR-4 — the corpus's own verify-honesty report: the single misleading "N% dead" figure
    resolved into a REAL gap (mechanically-attestable but gateless) plus an HONEST-manual count."""

    corpus: str
    docs: List[str] = field(default_factory=list)
    rows: List[SelfDogfoodRow] = field(default_factory=list)

    @property
    def mechanical(self) -> List[SelfDogfoodRow]:
        return [r for r in self.rows if r.mechanical]

    @property
    def mechanical_with_gate(self) -> List[SelfDogfoodRow]:
        return [r for r in self.mechanical if not r.gateless]

    @property
    def mechanical_gateless(self) -> List[SelfDogfoodRow]:
        """The REAL gap — a verify that claims a runnable check but carries no gate to run."""
        return [r for r in self.mechanical if r.gateless]

    @property
    def honest_manual(self) -> List[SelfDogfoodRow]:
        return [r for r in self.rows if r.honest_manual]

    @property
    def marked_manual(self) -> List[SelfDogfoodRow]:
        return [r for r in self.rows if r.marked_manual]

    @property
    def gated(self) -> List[SelfDogfoodRow]:
        return [r for r in self.rows if not r.gateless]

    @property
    def dead_gates(self) -> List[SelfDogfoodRow]:
        """An ADOPTED gate that does not resolve to a runnable command — adoption that attests nothing."""
        return [r for r in self.rows if r.gate_state == "dead-structural"]

    @property
    def adoption_rate(self) -> float:
        """FR-2's moving number: gated / mechanically-attestable. 1.0 when nothing is mechanical (there is
        no gap to close), so an empty corpus reads clean rather than divided-by-zero."""
        mech = self.mechanical
        return round(len(self.mechanical_with_gate) / len(mech), 4) if mech else 1.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "corpus": self.corpus,
            "docs": self.docs,
            "frs": len(self.rows),
            "mechanical": len(self.mechanical),
            "mechanical_with_gate": len(self.mechanical_with_gate),
            "mechanical_gateless": [r.fr for r in self.mechanical_gateless],
            "honest_manual": len(self.honest_manual),
            "marked_manual": len(self.marked_manual),
            "dead_gates": [r.fr for r in self.dead_gates],
            "adoption_rate": self.adoption_rate,
            "rows": [r.to_dict() for r in self.rows],
        }


@dataclass(frozen=True)
class _GateProbe:
    """The minimal duck-typed carrier ``_gate_liveness`` reads (``verify_gate``) — so the self-gate reuses
    REQ-22's resolver verbatim without paying for a full ``nodes_from_requirements`` projection (whose git
    evidence resolution costs ~1s/doc; the self-gate must stay cheap enough to run in the delivery loop)."""

    verify_gate: str


def classify_corpus_verifies(spec_dir) -> SelfDogfoodReport:
    """REQ-27 FR-1/FR-3 — split every corpus FR's verify into mechanically-attestable vs legitimately-manual.

    Reuse, not a new checker (NR-3): the kind comes from ``verify_oracle.classify`` (the ONE classifier —
    the same one ``_gate_liveness`` resolves gates with) and the gate's liveness from REQ-22's
    ``_gate_liveness``. Read-only; a doc that can't be read or parsed is skipped, never fatal.
    """
    from .verify_oracle import KIND_COMMAND, classify

    spec_dir = Path(spec_dir)
    docs = sorted(
        p for p in spec_dir.glob("REQ-*.md") if not _is_generated_projection(p)
    )
    report = SelfDogfoodReport(corpus=str(spec_dir), docs=[p.name for p in docs])
    for p in docs:
        try:
            descriptors = classify(p)
            frs = parse_fr_lines(p.read_text(encoding="utf-8"))
        except Exception:  # pragma: no cover - one bad doc never aborts the sweep (govern's convention)
            continue
        by_id = {str(fr.get("id", "")): fr for fr in frs}
        for d in descriptors:
            fr = by_id.get(d.fr_id, {})
            gate = str(fr.get("gate") or "").strip()
            manual = str(fr.get("manual") or "").strip()
            report.rows.append(
                SelfDogfoodRow(
                    doc=p.name,
                    fr=d.fr_id,
                    kind=d.kind,
                    mechanical=(d.kind == KIND_COMMAND and not manual),
                    gate=gate,
                    gate_state=_gate_liveness(_GateProbe(gate))[0],
                    manual_marker=manual,
                )
            )
    return report


def check_self_dogfood_verify_gates(spec_dir) -> List[Finding]:
    """REQ-27 FR-4/FR-5 — the standing self-liveness gate over our OWN requirements corpus.

    Emits, for a corpus: one adoption headline, one finding per mechanically-attestable-but-GATELESS FR
    (the real gap — routed to a human triage by :func:`lessons_from_self_dogfood`), one per ADOPTED gate
    that doesn't resolve, and one per ``command``-shaped verify an author overrode ``Manual:`` (visible,
    not silent). Deliberately NOT a sixth check in ``govern_corpus``'s fixed battery (REQ-06 NR-6): it is
    called from the Spec Delivery Loop (``--self-dogfood``) or directly.

    EVERY finding is ``_SEVERITY_ADVISORY`` (NR-2) — the self-gate reports and routes; it never fails the
    pipeline on the existing backlog. That includes a dead adopted gate, which the REQ-22 corpus check
    ships as a GAP: here the corpus is the *subject*, and a subject that can't block is the whole point.
    """
    report = classify_corpus_verifies(spec_dir)
    corpus_name = Path(report.corpus).name or report.corpus
    findings: List[Finding] = [
        Finding(
            "FR-4",
            _SEVERITY_ADVISORY,
            corpus_name,
            f"{corpus_name}: verify-gate adoption {len(report.mechanical_with_gate)}/"
            f"{len(report.mechanical)} mechanically-attestable FRs ({report.adoption_rate}) — "
            f"{len(report.mechanical_gateless)} mechanical-but-gateless (the real gap), "
            f"{len(report.honest_manual)} honest-manual of {len(report.rows)} FRs "
            f"({len(report.marked_manual)} explicitly marked). Advisory: this gate never blocks.",
            ref=_SELF_DOGFOOD_ADOPTION,
        )
    ]
    for r in report.mechanical_gateless:
        findings.append(
            Finding(
                "FR-2",
                _SEVERITY_ADVISORY,
                r.doc,
                f"{r.doc}: {r.fr} claims a MECHANICAL verify (a runnable `startd8 …` span) but carries no "
                f"`Gate:` — it reads verified while nothing attests it. Triage: adopt a `Gate:` naming the "
                f"check the verify already names, or mark it `Manual:` if a human is the real checker.",
                fr=r.fr,
                ref=_SELF_DOGFOOD_GAP,
            )
        )
    for r in report.dead_gates:
        findings.append(
            Finding(
                "FR-2",
                _SEVERITY_ADVISORY,
                r.doc,
                f"{r.doc}: {r.fr} adopted a `Gate:` {r.gate!r} that does NOT resolve to a runnable command "
                f"— adoption that attests nothing (the failure in reverse). Repair the handle or mark the "
                f"verify `Manual:`.",
                fr=r.fr,
                ref=_SELF_DOGFOOD_DEAD,
            )
        )
    for r in report.rows:
        if r.kind == "command" and r.marked_manual:
            findings.append(
                Finding(
                    "FR-3",
                    _SEVERITY_ADVISORY,
                    r.doc,
                    f"{r.doc}: {r.fr} names a runnable span yet is explicitly `Manual:` "
                    f"({r.manual_marker!r}) — the override is honoured and counted honest-manual, but it is "
                    f"reported so a manual marker can never quietly absorb a mechanical claim.",
                    fr=r.fr,
                    ref=_SELF_DOGFOOD_OVERRIDE,
                )
            )
    return findings


def lessons_from_self_dogfood(findings, *, confidence=None) -> List["Any"]:
    """REQ-27 FR-5 — route each mechanical-but-gateless FR to a human triage decision as a ``proposed``
    retrospective ``Lesson`` (REQ-20, propose-don't-dispose): adopt-a-gate or mark-it-manual. Filters on the
    finding's ``ref`` (not its severity) because the self-gate is advisory by construction (NR-2) — the
    adoption headline, the dead-gate and the manual-override notes are reports, not proposals."""
    from .sources_retrospective import build_lesson_from_mechanical_gateless

    return [
        build_lesson_from_mechanical_gateless(f, confidence=confidence)
        for f in findings
        if str(f.ref) == _SELF_DOGFOOD_GAP
    ]


def render_self_dogfood_text(report: SelfDogfoodReport) -> str:
    """REQ-27 FR-4 — the human-readable self-dogfood report: the adoption rate, the real gap (named FRs),
    and the honest-manual count, so "N% dead" is never printed as one misleading number again."""
    L: List[str] = [
        f"=== self-dogfood verify-gate adoption — {len(report.rows)} FRs across "
        f"{len(report.docs)} docs ===",
        f"corpus: {report.corpus}",
        "",
        f"  mechanically-attestable : {len(report.mechanical):4}  "
        f"(gated {len(report.mechanical_with_gate)}, gateless {len(report.mechanical_gateless)})",
        f"  honest-manual           : {len(report.honest_manual):4}  "
        f"(explicitly marked {len(report.marked_manual)})",
        f"  verify.gate adoption    : {report.adoption_rate}",
        "",
    ]
    if report.mechanical_gateless:
        L.append(f"MECHANICAL-BUT-GATELESS ({len(report.mechanical_gateless)}) — adopt a gate or mark manual:")
        for r in report.mechanical_gateless:
            L.append(f"  - {r.doc}  {r.fr}")
    else:
        L.append("no mechanical-but-gateless FR — every runnable claim carries a gate.")
    if report.dead_gates:
        L.append(f"DEAD ADOPTED GATES ({len(report.dead_gates)}) — present but attesting nothing:")
        for r in report.dead_gates:
            L.append(f"  - {r.doc}  {r.fr}  {r.gate}")
    L.append("")
    L.append("-> advisory only: the self-gate reports + routes to a human triage; it never blocks.")
    return "\n".join(L)


def check_lesson_grounding(nodes, doc: str = "") -> List[Finding]:
    """REQ-20 FR-2 — a Lesson (``category=="lesson"``) that is not grounded (no ``derived-from`` edge or
    no ``lives`` evidence citing its outcome) is an **ungrounded belief** (cruft, invariant 4) — a named
    finding. A grounded Lesson yields none. Never a crash."""
    from .sources_retrospective import LESSON_CATEGORY, is_grounded

    findings: List[Finding] = []
    for n in nodes:
        if getattr(n, "category", "") == LESSON_CATEGORY and not is_grounded(n):
            findings.append(
                Finding(
                    "FR-2",
                    _SEVERITY_FAIL,
                    doc or n.key,
                    f"{doc or n.key}: Lesson {n.key!r} is ungrounded — it proposes a revision without a "
                    f"`derived-from` edge + `lives` citing its outcome. A belief is cruft until grounded; "
                    f"add its grounding or drop it.",
                    fr=n.key,
                )
            )
    return findings


def check_realization_invariant(nodes, doc: str = "") -> List[Finding]:
    """REQ-18 FR-5 — invariant 9: an ``llm``-regime derivation edge obligates its target node's ``verify``
    (the acceptance oracle) — **strengthened by REQ-22 FR-7 from *presence* to *liveness***: an obligated
    node whose verify is EMPTY *or* whose gate is present-but-**dead** (doesn't resolve to a runnable
    command) both violate. Fires only once ``lives`` is present (activation gate) so unbuilt nodes never
    fail. A ``deterministic``/``human`` edge imposes no obligation. Each violation is a named finding.
    """
    from .models import RealizationRegime
    from .realization import resolve_edge_regime

    findings: List[Finding] = []
    for n in nodes:
        if not getattr(n, "lives", None):
            continue  # un-realized → not obligated (activation gate)
        verify = getattr(n, "verify", "")
        # REQ-22 FR-7 — a verify is *satisfied* only when present AND its gate is not structurally dead;
        # a present-but-dead verify (a durable green carrying no truth) no longer passes invariant 9.
        satisfied = bool(verify) and _gate_liveness(n)[0] != "dead-structural"
        if satisfied:
            continue
        for e in getattr(n, "derivation", ()):
            if resolve_edge_regime(n, e) == RealizationRegime.LLM:
                why = (
                    "is empty"
                    if not verify
                    else "is present but DEAD (its gate does not resolve to a runnable command)"
                )
                findings.append(
                    Finding(
                        "FR-5",
                        _SEVERITY_FAIL,
                        doc or n.key,
                        f"{doc or n.key}: node {n.key!r} is realized by an llm-regime edge "
                        f"(from {e.from_key!r}) but its verify (acceptance oracle) {why} — invariant 9 "
                        f"(REQ-22-strengthened) requires a stochastic edge's target to carry a LIVE verify.",
                        fr=n.key,
                    )
                )
                break  # one finding per node
    return findings


def _is_generated_projection(path: Path) -> bool:
    """True iff *path* is a det-doc-kit `$0` GENERATED projection (not an authored REQ).

    Fast-path on the ``.projected.md`` suffix; otherwise the machine marker ``<!-- GENERATED det-`` in
    the head (a det-plan/det-handoff/det-howto render carries it). A generated projection is exempt from
    the authoring-convention checks its source REQ owns.
    """
    if path.name.endswith(".projected.md"):
        return True
    try:
        head = path.read_text(encoding="utf-8")[:400]
    except (OSError, UnicodeDecodeError):
        return False
    return "<!-- GENERATED det-" in head


def govern_corpus(spec_dir: Path, *, realization_provenance=None) -> GovernReport:
    """Run the full governance battery over a directory of ``REQ-*.md`` docs (read-only).

    Returns a :class:`GovernReport`; ``report.exit_code`` is 0 (clean) / 1 (any fail-severity drift).
    Operational errors (missing dir) are the CLI's concern (exit 2), not this function's.

    ``realization_provenance`` (REQ-19 FR-6, optional): a measured :class:`ProvenanceSource`; when supplied,
    each doc's nodes are checked for planned-vs-realized determinism regressions. Absent → skipped (no
    measured signal to compare against), so the default battery is unchanged.
    """
    spec_dir = Path(spec_dir)
    # Govern audits AUTHORED requirement docs. A det-doc-kit `$0` GENERATED projection (a det-plan /
    # det-handoff / det-howto output, e.g. `REQ-01-…​.projected.md`) matches the `REQ-*.md` glob but is
    # not an authored REQ — it carries the machine marker `<!-- GENERATED det-` and is exempt (a
    # generated projection can't be held to the authoring conventions its source REQ owns).
    docs = sorted(
        p for p in spec_dir.glob("REQ-*.md") if not _is_generated_projection(p)
    )
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
            report.findings.append(
                Finding(
                    "FR-1", _SEVERITY_ADVISORY, p.name, f"{p.name}: unreadable ({exc})."
                )
            )
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
            # REQ-25 FR-1/FR-2 fact-rungs (reuse the security verifier + import/AST checks). Opt-in:
            # they fire only on a node that DECLARES a `security_mitigation` attribute or a `no-import:`
            # non-goal — a signal the requirement corpus doesn't carry today, so this is byte-identical
            # on the current corpus (FR-8) while making the cells reachable from `navigator govern` (no
            # seam-fuel). The verify-liveness / target-unmeasured / served-by-dead cells stay OUT of the
            # default sweep (a REQ-22/23-scope wiring — the corpus isn't authored with Signals/gates yet).
            report.findings.extend(
                check_mitigation_inert(_req_nodes, repo_root, p.name)
            )
            report.findings.extend(
                check_non_goal_violated(_req_nodes, repo_root, p.name)
            )
            # REQ-19 FR-6: planned-vs-realized regression, only when a measured provenance source is given.
            if realization_provenance is not None:
                report.findings.extend(
                    check_determinism_regression(
                        _req_nodes, realization_provenance, p.name
                    )
                )
        except (
            Exception
        ):  # pragma: no cover - projection is itself defensive; never abort the sweep
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
    L.append(
        f"=== corpus governance -- {banner} "
        f"({len(report.docs)} docs, govern_score {report.govern_score()}) ==="
    )
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
        L.append(
            f"  [{glyph}] {fr:5} {labels.get(fr, ''):22} " f"{counts['fail']} fail{adv}"
        )
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
    L.append(
        f"-> exit {report.exit_code} "
        + ("(clean)" if report.exit_code == 0 else "(drift -- see FAIL above)")
    )
    return "\n".join(L)


def render_govern_json(report: GovernReport) -> str:
    """Machine-readable governance report (stable key order, ascii-safe)."""
    return (
        json.dumps(report.to_dict(), indent=2, sort_keys=True, ensure_ascii=True) + "\n"
    )


def recurring_finding_classes(
    report: GovernReport, *, threshold: int = 2
) -> Dict[str, int]:
    """FR-7 -- finding-classes recurring across >=``threshold`` docs, routable to ``/metabolize-finding``.

    A check firing on many docs is a class to metabolize into a structural guard, not to re-file
    forever; the CLI surfaces the ``/metabolize-finding`` invocation for any such class.
    """
    per_check_docs: Dict[str, set] = {}
    for f in report.fail_findings:
        per_check_docs.setdefault(f.check, set()).add(f.doc)
    return {
        check: len(docs)
        for check, docs in per_check_docs.items()
        if len(docs) >= threshold
    }
