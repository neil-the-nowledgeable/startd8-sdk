"""Runtime o11y grounding (REQ-28) — route the *territory's* two runtime signals into the loop.

The loop grounds claims in the **map** (docs/code, authoring time). This module adds the **territory**:

* **feature o11y** — ``observability/parity.py`` (declared-vs-emitted) and ``observability/compare_live.py``
  (live fidelity verdicts) answer *"does the deployed feature emit a live signal?"* → the DEEPEST cell of
  the liveness column (REQ-22/23), emitted through the o11y→SARIF bridge
  (``coverage_map.findings_sarif.render_sarif_from_findings``).
* **AI o11y** — observed generation cost (``costs/otel_metrics``-shaped telemetry) is exactly the measured
  provenance source REQ-19's confidence-aware seam was built to accept, so a node's realization regime and
  its planned-vs-realized determinism regression become *measured*, not merely declared.

**Reuse-only (NR-2/NR-5).** Nothing here re-authors ``parity`` / ``compare_live`` / ``costs`` /
``instrumentation_gen`` / ``findings_sarif``: their public outputs are *adapted* into the navigator's
existing ``Finding`` / Lesson / SARIF vocabulary through thin, typed seams.

**Opt-in + advisory (NR-3, charter NR-6).** Every entry point degrades to "no findings" when the runtime
input is absent, so the fixed REQ-06 govern battery and the shipped renders are byte-identical without
runtime telemetry. Runtime cells join the ``liveness`` layer only when a caller passes an observation.

**Absence-vs-error (FR-4, the Harbor ``FIELDSTATE`` guard).** A signal the observation could not see is
*unobserved* (a provenance advisory) — never a real failing ``0``. Only an observation that *did* look and
found no emission is a territory GAP.

**Propose, don't dispose (FR-5/NR-1).** A feature-o11y gap yields a *proposed* ``instrumentation_gen``
patch plus a REQ-stub payload. There is no apply path in this module — by construction, not by policy.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

from .govern import _SEVERITY_ADVISORY, _SEVERITY_FAIL, Finding
from .models import RealizationRegime

# ── the runtime cells' finding refs (FR-1/FR-3/FR-4: absent and real-fail are DISTINCT) ─────────────
#: The territory FACT: the observation looked and the declared signal had NO live emission (a dead SLI).
#: Fail-severity *within the liveness layer* — it joins the ``liveness:`` namespace, so REQ-25's
#: ``lessons_from_liveness_layer`` already routes it, and it is never a 6th REQ-06 charter check.
REF_RUNTIME_DEAD = "liveness:runtime-verify-dead"
#: The PROVENANCE state: the signal could not be observed (scrape failed / probe not yet run). Advisory —
#: an absent metric is NOT a real ``0`` (the Harbor ``FIELDSTATE_EXPLICIT_STATE`` bug this guards).
REF_RUNTIME_UNOBSERVED = "liveness:runtime-verify-unobserved"
#: The MEASURED determinism regression (FR-3) — its own namespace, so it routes to a regression Lesson
#: (``build_lesson_from_regression``) rather than being swept up as a liveness gap.
REF_MEASURED_REGRESSION = "realization:determinism-regression-measured"

RUNTIME_LIVENESS_REFS = (REF_RUNTIME_DEAD, REF_RUNTIME_UNOBSERVED)

TOOL_NAME = "startd8-navigator-runtime-o11y"
TOOL_VERSION = "req-28/0.1"

#: navigator severity → a string ``findings_sarif`` already maps onto the SARIF level vocabulary. Done in
#: the adapter so the shared renderer's contract is untouched (NR-5): fail → error, advisory → note.
_SARIF_SEVERITY = {_SEVERITY_FAIL: "error", _SEVERITY_ADVISORY: "note"}

#: A metric-ish token inside an authored ``Signal:`` handle (a bare metric name or a PromQL expression).
_SIGNAL_TOKEN = re.compile(r"[A-Za-z_:][A-Za-z0-9_:.]*")


def _canonical_signal(name: str) -> str:
    """Canonicalize a metric name for the join, reusing ``parity.exported_name``'s convention (the
    Prometheus-exported form replaces ``.`` with ``_``) — so a descriptor's canonical
    ``startd8.cost.total`` and an operator's exported ``startd8_cost_total`` are the SAME signal."""
    return name.strip().strip("`\"'").replace(".", "_")


def _signal_tokens(signal: str) -> frozenset:
    """The canonicalized metric names an authored ``Signal:`` handle mentions. A bare name yields one
    token; a PromQL expression yields every identifier in it (a superset — matching is by membership, so
    an extra token can only add a *named* match, never invent one)."""
    return frozenset(
        _canonical_signal(m.group(0)) for m in _SIGNAL_TOKEN.finditer(signal or "")
    )


def _node_signal(node) -> str:
    """The node's bound live-measurement handle: REQ-23's objective ``target_signal``, or a ``signal``
    attribute on any other node kind. Empty ⇒ the node binds no live signal, so the *static*
    ``target-unmeasured`` cell owns it and the runtime cell stays silent (no double-reporting)."""
    attrs = getattr(node, "attributes", {}) or {}
    return str(attrs.get("target_signal") or attrs.get("signal") or "").strip()


# --------------------------------------------------------------------------- #
# FR-1 / FR-4 — the runtime emission seam + the runtime verify-liveness cell
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class RuntimeEmission:
    """The typed runtime-emission observation — the seam the navigator reads instead of reaching into a
    live Prometheus. Built from ``parity``/``compare_live`` output by the adapters below, or handed in
    directly (fixtures, a cached report), which is what keeps every runtime test o11y-stack-free.

    ``dead`` are signals the observation LOOKED FOR and found no emission of (territory: a real fail).
    ``unobserved`` are signals it could not see at all (provenance: absent — never a real ``0``).
    ``observed=False`` means the observation itself failed (no scrape / ``compare_live`` ``unknown``), so
    EVERY declared signal is unobserved regardless of the sets — the fail-loud-as-absent default.
    """

    dead: frozenset = frozenset()
    unobserved: frozenset = frozenset()
    observed: bool = True
    source: str = ""

    def classify(self, tokens: Iterable[str]) -> Optional[str]:
        """``"dead"`` / ``"unobserved"`` / ``None`` for a node's canonicalized signal tokens. A failed
        observation classifies everything ``unobserved`` — absence is never upgraded to a failure."""
        toks = frozenset(tokens)
        if not toks:
            return None
        if not self.observed:
            return "unobserved"
        if toks & self.dead:
            return "dead"
        if toks & self.unobserved:
            return "unobserved"
        return None


def runtime_emission_from_parity(result, *, source: str = "observability.parity") -> RuntimeEmission:
    """Adapt a ``observability.parity.ParityResult`` (``run_parity`` / ``check_metric_bijection``) into the
    seam. ``declared_not_emitted`` is the dead-SLI class — a declared descriptor with no emitter — so it is
    a territory FACT (``dead``). ``spans_without_site`` is parity's own *best-effort* sub-check (d), so it
    degrades to ``unobserved`` (advisory): a soft miss must not ship as a hard gap."""
    dead = frozenset(_canonical_signal(n) for n in getattr(result, "declared_not_emitted", ()) or ())
    soft = frozenset(_canonical_signal(n) for n in getattr(result, "spans_without_site", ()) or ())
    return RuntimeEmission(dead=dead, unobserved=soft - dead, observed=True, source=source)


def runtime_emission_from_live_comparison(
    report, *, source: str = "observability.compare_live"
) -> RuntimeEmission:
    """Adapt a ``compare_live.LiveComparisonReport`` (or its ``to_dict()``) into the seam.

    * ``status == "unknown"`` — the standup/scrape failed, so the report is ``observed=False``: every
      signal is *unobserved*, never a fail (compare-live's own fail-loud contract, honored not re-read).
    * ``fail_verdicts`` — the #274/#275 dead-metric / wrong-label class: the query ran and the SLI was
      not there → ``dead``.
    * ``pending_verdicts`` — ``pending_probe`` is severity 0 *by declared invariant* upstream (expected-
      absent until its runner runs), so it maps to ``unobserved``, never to a fail.
    """
    d = report.to_dict() if hasattr(report, "to_dict") else dict(report or {})
    dead = frozenset(
        _canonical_signal(str(v.get("metric", "")))
        for v in (d.get("fail_verdicts") or [])
        if isinstance(v, Mapping) and v.get("metric")
    )
    pending = frozenset(
        _canonical_signal(str(v.get("metric", "")))
        for v in (d.get("pending_verdicts") or [])
        if isinstance(v, Mapping) and v.get("metric")
    )
    observed = str(d.get("status", "")) != "unknown"
    return RuntimeEmission(
        dead=dead if observed else frozenset(),
        unobserved=(pending - dead) if observed else pending,
        observed=observed,
        source=source,
    )


def merge_runtime_emissions(*emissions: Optional[RuntimeEmission]) -> Optional[RuntimeEmission]:
    """Union several observations (e.g. static parity + a live compare-live run). ``None``s are dropped;
    all-``None`` yields ``None`` (the absent default). A signal that is a FACT in one observation stays
    dead even if another could not see it — a grounded fact outranks a missing look; the reverse (an
    absence promoted to a fail) never happens. ``observed`` is the AND: if any input failed to observe,
    the merge reports the union it *did* see and flags the shortfall through that input's own sets."""
    present = [e for e in emissions if e is not None]
    if not present:
        return None
    if len(present) == 1:
        return present[0]
    dead = frozenset().union(*(e.dead for e in present))
    unobserved = frozenset().union(*(e.unobserved for e in present)) - dead
    return RuntimeEmission(
        dead=dead,
        unobserved=unobserved,
        observed=all(e.observed for e in present),
        source=" + ".join(sorted({e.source for e in present if e.source})),
    )


def check_runtime_verify_liveness(
    nodes, emission: Optional[RuntimeEmission] = None, doc: str = ""
) -> List[Finding]:
    """REQ-28 FR-1/FR-4 — the RUNTIME cell of the liveness layer: a node that binds a live signal whose
    emission the territory does not carry.

    A ``dead`` classification is a GAP (``_SEVERITY_FAIL``, ``REF_RUNTIME_DEAD``) — the deployed feature
    does not emit the signal its claim rests on. An ``unobserved`` classification is a precision-safe
    CANDIDATE (``_SEVERITY_ADVISORY``, ``REF_RUNTIME_UNOBSERVED``) — the observation could not look, which
    is a provenance fact about the harness, not a territory failure (FR-4).

    ``emission is None`` → ``[]``: with no runtime telemetry the layer is byte-identical (FR-6). Nodes that
    bind no signal are skipped — the static ``target-unmeasured`` cell already owns that gap.
    """
    if emission is None:
        return []
    findings: List[Finding] = []
    for n in nodes or ():
        signal = _node_signal(n)
        if not signal:
            continue
        verdict = emission.classify(_signal_tokens(signal))
        where = doc or n.key
        if verdict == "dead":
            findings.append(
                Finding(
                    "FR-1",
                    _SEVERITY_FAIL,
                    where,
                    f"{where}: {n.key!r} binds live signal {signal} but the territory emits NO such "
                    f"signal ({emission.source or 'runtime observation'}) — a declared feature with no "
                    f"live emission: runtime present-but-dead, the deepest liveness cell. Generate the "
                    f"instrumentation that makes it emit, or revise the claim.",
                    fr=n.key,
                    ref=REF_RUNTIME_DEAD,
                )
            )
        elif verdict == "unobserved":
            findings.append(
                Finding(
                    "FR-1",
                    _SEVERITY_ADVISORY,
                    where,
                    f"{where}: {n.key!r} binds live signal {signal} whose emission could NOT be observed "
                    f"({emission.source or 'runtime observation'}) — unobserved-here, a provenance state, "
                    f"NOT a real zero. Re-run the observation before reading anything into it.",
                    fr=n.key,
                    ref=REF_RUNTIME_UNOBSERVED,
                )
            )
    return findings


# --------------------------------------------------------------------------- #
# FR-2 / FR-3 — AI cost telemetry as the REQ-19 measured-provenance source
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class CostObservation:
    """One AI-o11y cost observation for a generated file — the ``costs/otel_metrics``-shaped datum
    (``startd8.cost.total`` per artifact) the REQ-19 seam consumes.

    ``cost is None`` means the telemetry carried NO value for this file: **absent, not zero** (FR-4). Such
    an observation yields no record, so the seam degrades to the declared regime — it can never assert a
    false ``deterministic``. An *explicit* ``0.0`` is a real measurement ("generated, nothing was spent")
    and does ground ``deterministic``; the distinction is the whole FIELDSTATE guard.
    """

    file: str
    cost: Optional[float] = None
    model: Optional[str] = None
    confidence: float = 1.0

    @property
    def regime(self) -> Optional[str]:
        """The measured regime this observation grounds, or ``None`` when the cost is absent."""
        if self.cost is None:
            return None
        return (
            RealizationRegime.LLM if self.cost > 0 else RealizationRegime.DETERMINISTIC
        )


def load_cost_telemetry(path) -> List[CostObservation]:
    """Read an AI-cost telemetry artifact — a JSON list, or an object with an ``"observations"`` key — into
    :class:`CostObservation` records. A missing file yields ``[]`` (absent telemetry → no findings, the
    byte-identical default). A **missing or null ``cost`` field stays ``None``** (absent), never 0.0."""
    path = Path(path)
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = data.get("observations", data) if isinstance(data, Mapping) else data
    if not isinstance(rows, list):
        raise ValueError(f"{path}: expected a list of observations (or an object with 'observations')")
    out: List[CostObservation] = []
    for row in rows:
        if not isinstance(row, Mapping) or not str(row.get("file", "")).strip():
            continue
        cost = row.get("cost")  # absent key OR explicit null → None (absent), never coerced to 0.0
        out.append(
            CostObservation(
                file=str(row["file"]),
                cost=None if cost is None else float(cost),
                model=None if row.get("model") is None else str(row["model"]),
                confidence=float(row.get("confidence", 1.0)),
            )
        )
    return out


def cost_telemetry_to_provenance(observations: Iterable[CostObservation]):
    """REQ-28 FR-2 — turn AI cost telemetry into a REQ-19 ``MeasuredProvenanceSource``: the measured
    realization regime, grounded in what generation actually cost.

    Observed LLM cost ⇒ ``llm``; an observed ``$0`` ⇒ ``deterministic``; an ABSENT cost contributes no
    record at all, so the seam degrades to the declared regime (or ``unknown``) — never a false
    ``deterministic``. Records go through ``realization_contract.make_record``, so an out-of-contract
    observation fails loud here, and through ``realization_provenance.normalize``, so the confidence
    tie-break stays the one shared deterministic resolution (no second join).
    """
    from .realization import MeasuredProvenanceSource
    from .realization_contract import make_record
    from .realization_provenance import normalize

    records = [
        make_record(
            obs.file,
            obs.regime,
            obs.confidence,
            model=obs.model,
            strategy="ai-o11y-cost-telemetry",
            cost=obs.cost,
        )
        for obs in observations or ()
        if obs.regime is not None
    ]
    return MeasuredProvenanceSource(normalize(records))


def check_measured_determinism_regression(
    nodes,
    observations: Optional[Iterable[CostObservation]] = None,
    doc: str = "",
    *,
    provenance=None,
) -> List[Finding]:
    """REQ-28 FR-3 — a node planned ``deterministic`` (``$0``) whose AI o11y shows real LLM cost, surfaced
    as a MEASURED determinism regression.

    A thin wrapper over REQ-19's ``govern.check_determinism_regression`` (NR-2: the comparison logic is not
    re-implemented) that grounds the *measured* side in cost telemetry and re-tags the finding with
    :data:`REF_MEASURED_REGRESSION`, so the report says the regression came from live telemetry rather than
    a static provenance file. No telemetry and no provenance → ``[]`` (opt-in, byte-identical).
    """
    import dataclasses

    from .govern import check_determinism_regression

    if provenance is None:
        if not observations:
            return []
        provenance = cost_telemetry_to_provenance(observations)
    return [
        dataclasses.replace(f, ref=REF_MEASURED_REGRESSION)
        for f in check_determinism_regression(nodes, provenance, doc)
    ]


# --------------------------------------------------------------------------- #
# FR-5 — the generative fix: PROPOSE (a patch / a REQ-stub), never dispose
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class RuntimeFixProposal:
    """A *proposed* remedy for one runtime-o11y gap. Carries the artifacts a human applies — an
    ``instrumentation_gen`` patch (the ``$0`` generative fix) and/or a REQ-stub payload — and nothing that
    performs an application. ``applied`` is a permanent ``False``: this module has no writer, so the field
    is a contract statement a test can assert, not a flag some path flips.
    """

    finding_ref: str
    subject: str
    req_stub: Dict[str, Any] = field(default_factory=dict)
    patch: Optional[Dict[str, Any]] = None
    note: str = ""
    applied: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "finding_ref": self.finding_ref,
            "subject": self.subject,
            "req_stub": self.req_stub,
            "patch": self.patch,
            "note": self.note,
            "applied": self.applied,
        }


def _req_stub_for(finding) -> Dict[str, Any]:
    """The finding→REQ-stub payload (the ``sarif_to_req_stub`` shape): the fields a reactive requirement
    needs to be authored FROM a runtime gap. Emitted as data for a human (or the det-req-kit stub tool,
    which lives outside this repo) to turn into a doc — this module writes no file."""
    subject = str(getattr(finding, "fr", "") or getattr(finding, "check", "") or "unknown")
    return {
        "kind": "req-stub",
        "seed": "runtime-o11y-gap",
        "ref": str(getattr(finding, "ref", "")),
        "subject": subject,
        "doc": str(getattr(finding, "doc", "")),
        "semantic_name": (
            f"Make the declared signal of {subject} emit in the territory so its claim is runtime-verified"
        ),
        "why": str(getattr(finding, "message", "")),
        "verify": (
            "the signal appears in a live observation (parity declared-vs-emitted clean / compare-live "
            "verdict not `fail`) for the deployed feature"
        ),
        "disposition": "proposed",
    }


def propose_instrumentation_for_gap(
    finding,
    *,
    gap=None,
    source_ctx: Optional[Mapping[str, str]] = None,
    registry=None,
) -> RuntimeFixProposal:
    """REQ-28 FR-5 — offer the ``$0`` generative fix for a feature-o11y gap: **propose, don't dispose.**

    Always returns a REQ-stub payload (the always-available human route). When the caller supplies a
    grounded ``scaffold_codegen.instrumentation_gen.InstrumentationGap``, the Harbor-proven renderer is
    asked for the concrete patch too; the framework's honest boundaries (a runtime-composed subject, an
    unregistered language, an unsupported contract) surface as a ``note`` with ``patch=None`` instead of a
    silent wrong patch — ``close_gap`` already raises there and that verdict is reported, not swallowed.

    ``instrumentation_gen`` is imported HERE, lazily, inside this adapter — the navigator core (govern,
    realization, retrospective) keeps its construction-subsystem firewall.
    """
    subject = str(getattr(finding, "fr", "") or getattr(finding, "check", "") or "unknown")
    stub = _req_stub_for(finding)
    if gap is None:
        return RuntimeFixProposal(
            finding_ref=str(getattr(finding, "ref", "")),
            subject=subject,
            req_stub=stub,
            patch=None,
            note=(
                "no grounded InstrumentationGap supplied — the REQ-stub is the proposed route (a patch "
                "needs the subject's language + mechanism evidence, which must be grounded, not guessed)"
            ),
        )

    import dataclasses as _dc

    from ..scaffold_codegen.instrumentation_gen import close_gap

    try:
        patch = close_gap(gap, dict(source_ctx or {}), registry)
    except NotImplementedError as exc:
        return RuntimeFixProposal(
            finding_ref=str(getattr(finding, "ref", "")),
            subject=subject,
            req_stub=stub,
            patch=None,
            note=f"instrumentation-gen declined (its honest boundary): {exc}",
        )
    return RuntimeFixProposal(
        finding_ref=str(getattr(finding, "ref", "")),
        subject=subject,
        req_stub=stub,
        patch=_dc.asdict(patch),
        note=(
            f"proposed {patch.tier} patch for {gap.language} ({len(patch.edits)} edit(s)) — apply it "
            f"yourself on a fork and verify emission; nothing here writes to the subject tree"
        ),
    )


def lessons_from_runtime_grounding(findings, *, confidence=None) -> List[Any]:
    """REQ-28 FR-5 → REQ-20 — route each runtime FACT to a human-gated, ``proposed`` retrospective Lesson.

    A runtime emission GAP becomes a runtime-emission Lesson; a MEASURED determinism regression reuses
    REQ-19's regression Lesson. Advisory *unobserved* candidates are NOT routed — only facts become
    proposed revisions (the same rule as ``govern.lessons_from_liveness_layer``). Every Lesson is
    ``proposed``: the loop holds the proposal, the human disposes.
    """
    from .sources_retrospective import (
        build_lesson_from_regression,
        build_lesson_from_runtime_emission_gap,
    )

    lessons: List[Any] = []
    for f in findings or ():
        if getattr(f, "severity", "") != _SEVERITY_FAIL:
            continue
        ref = str(getattr(f, "ref", ""))
        if ref == REF_RUNTIME_DEAD:
            lessons.append(build_lesson_from_runtime_emission_gap(f, confidence=confidence))
        elif ref == REF_MEASURED_REGRESSION:
            lessons.append(build_lesson_from_regression(f, confidence=confidence))
    return lessons


# --------------------------------------------------------------------------- #
# FR-1/FR-3 — out through the o11y→SARIF bridge (the shared findings sink)
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class _SarifRow:
    """Duck-typed row for ``findings_sarif`` (``check``/``severity``/``message``/``file_path``), so a
    navigator ``Finding`` — whose location is a *doc*, not a source file — renders through the ONE shared
    renderer with no change to its contract (NR-5). The rule id is the runtime cell's ``ref`` (that is the
    stable rule identity a consumer dedupes on), falling back to the FR id."""

    check: str
    severity: str
    message: str
    file_path: str


def runtime_findings_to_sarif(findings, *, corpus: Optional[str] = None) -> Dict[str, Any]:
    """Render runtime-grounding findings as SARIF 2.1.0 through
    ``coverage_map.findings_sarif.render_sarif_from_findings`` — the same sink census / crp-lint / repair
    use, so a runtime gap lands in the findings IR beside every other producer (charter §6, no new sink).
    """
    from ..coverage_map.findings_sarif import render_sarif_from_findings

    rows = [
        _SarifRow(
            check=str(getattr(f, "ref", "") or getattr(f, "check", "") or "runtime-o11y"),
            severity=_SARIF_SEVERITY.get(str(getattr(f, "severity", "")), "warning"),
            message=str(getattr(f, "message", "")),
            file_path=str(getattr(f, "doc", "") or getattr(f, "fr", "") or "(corpus)"),
        )
        for f in findings or ()
    ]
    return render_sarif_from_findings(
        rows, tool_name=TOOL_NAME, tool_version=TOOL_VERSION, corpus=corpus
    )


def ground_corpus_in_runtime(
    nodes: Sequence[Any],
    *,
    emission: Optional[RuntimeEmission] = None,
    observations: Optional[Iterable[CostObservation]] = None,
    doc: str = "",
) -> List[Finding]:
    """The one opt-in entry point that runs BOTH runtime cells over a node set: the feature-o11y runtime
    verify-liveness cell (FR-1/FR-4) and the AI-o11y measured determinism regression (FR-3).

    Absent runtime inputs → ``[]``. Never blocks (NR-3) and is never part of the fixed REQ-06 battery
    (charter NR-6): a caller opts in by handing over an observation.
    """
    nodes = list(nodes or ())
    findings = check_runtime_verify_liveness(nodes, emission, doc)
    findings += check_measured_determinism_regression(nodes, observations, doc)
    return findings
