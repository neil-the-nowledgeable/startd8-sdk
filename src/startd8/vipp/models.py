# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""Keiyaku-shaped contracts for the VIPP (Very Important Project Person).

The VIPP is the project-side **OBSERVED(project)-authority dual** of the FDE: it ingests the host's
serialized proposal envelope (the in-memory ``ProposalBuffer`` made durable, FR-15), evaluates each
proposal against project ground-truth, and emits a source-labeled disposition (ACCEPT/REJECT/COUNTER)
an applier consumes at *project* human privilege.

Per FR-2/FR-13 the **JSON form is canonical** (``to_dict``/``from_json``/``from_dict``); markdown
(``to_markdown``) is a *derived, lossy* view — there is intentionally **no** ``from_markdown``. Each
contract also exposes ``to_prompt_section`` for bounded prompt/EventBus injection (FDE parity).
``PROTOCOL_VERSION`` tracks the contract *shape*, independent of the SDK version.

Source labels **reuse the FDE's** :class:`~startd8.fde.models.ClaimLabel` /
:class:`~startd8.fde.models.LabeledClaim` (FR-6) so the OBSERVED/MECHANISM/PREDICTION vocabulary is one
shared type across the boundary. The dependency direction is one-way — ``vipp`` → ``fde`` — never the
reverse (FR-8). By contrast :class:`EnvelopedProposal` mirrors ``kickoff_experience``'s
``ProposedAction`` **by dict shape, not by importing the peer type** (FR-8): a shape-pinning test
(``HOST_PROPOSAL_FIELDS``) fails loudly if the host shape drifts, forcing a ``PROTOCOL_VERSION`` bump.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

# Reuse the FDE's source-labeling vocabulary (FR-6). vipp → fde is the sanctioned direction (FR-8).
# Re-exported (see __all__) so consumers import the shared label types from one place.
from startd8.fde.models import ClaimLabel, LabeledClaim

__all__ = [
    "PROTOCOL_VERSION",
    "HOST_PROPOSAL_FIELDS",
    "ClaimLabel",
    "LabeledClaim",
    "Decision",
    "EnvelopedProposal",
    "ProposalEnvelope",
    "VippDisposition",
    "VippReport",
    "protocol_is_future",
]

# Bump on contract *shape* change — independent of the SDK version (FR-13 / FDE R1-F3 parity).
PROTOCOL_VERSION = "1.0"

# The field set EnvelopedProposal mirrors from kickoff_experience.proposals.ProposedAction (FR-8).
# A shape-pinning **test** (test_models_and_labeling) asserts this still equals the live
# ProposedAction field set, so a host-side field addition fails loudly **in SDK CI**. Note: at
# runtime ``from_dict`` silently drops unknown keys within the same protocol major — only a major
# bump is rejected (``protocol_is_future``); the loudness is the CI shape-pin, not a runtime guard.
HOST_PROPOSAL_FIELDS = ("kind", "params", "id", "base_sha")


def oneline(text: Any) -> str:
    """Collapse whitespace/newlines to a single line.

    Host-controlled strings (``value_path``, entity names, oracle evidence) flow into VIPP-authored
    claim text and disposition reasons, which are then rendered as markdown and passed through the
    line-oriented FR-21 label gate (``assert_all_labeled``). A newline in untrusted input would split
    a labeled claim into a second, *untagged* bullet and crash the gate (code-review H1). Collapsing
    to one line at every VIPP-authored-string boundary neutralizes that vector at the source.
    """
    return " ".join(str(text).split())


class Decision(str, Enum):
    """A VIPP disposition decision (FR-4). REJECT is terminal; COUNTER re-opens once in v1."""

    ACCEPT = "ACCEPT"
    REJECT = "REJECT"
    COUNTER = "COUNTER"


def _decision_from_value(value: str) -> "Decision":
    for d in Decision:
        if d.value == value:
            return d
    raise ValueError(f"unrecognized decision: {value!r}")


def protocol_is_future(version: str, *, ours: str = PROTOCOL_VERSION) -> bool:
    """Reject-future guard (FR-15): True iff ``version``'s major exceeds ours.

    A higher major means an envelope written by a newer host the VIPP cannot safely interpret; the
    caller should refuse rather than silently mis-read. Same-major (e.g. 1.1 vs 1.0) is forward
    within v1 and tolerated.
    """

    def _major(v: str) -> int:
        try:
            return int(str(v).split(".", 1)[0])
        except (ValueError, AttributeError):
            return 0

    return _major(version) > _major(ours)


@dataclass(frozen=True)
class EnvelopedProposal:
    """One host ``ProposedAction``, serialized **by dict shape** (FR-8 — not importing the peer type).

    Mirrors ``kickoff_experience.proposals.ProposedAction`` = (kind, params, id, base_sha). ``params``
    is the one legitimately-dynamic dict (Lesson L13-#16); it is carried **verbatim/unredacted**
    because for ``brief``/``manifest``/``schema`` it *is* the prose the applier writes to disk and
    round-trip-gates (CRP R1: redaction-vs-apply). ``base_sha`` is a host-trusted, propose-time
    capture-only binding and is **never** VIPP-amendable (FR-5/FR-18).
    """

    kind: str
    params: Dict[str, Any] = field(default_factory=dict)
    id: str = ""
    base_sha: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "kind": self.kind,
            "params": dict(self.params),
            "id": self.id,
            "base_sha": self.base_sha,
        }

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "EnvelopedProposal":
        return EnvelopedProposal(
            kind=d["kind"],
            params=dict(d.get("params", {})),
            id=d.get("id", ""),
            base_sha=d.get("base_sha"),
        )


@dataclass(frozen=True)
class ProposalEnvelope:
    """The host-serialized inbox (FR-15): the in-memory ``ProposalBuffer`` made durable for the VIPP.

    ``envelope_seq`` is monotonic per project posting; ``content_checksum`` covers the **proposals
    only** (NOT ``generated_at``/``envelope_seq``) so a re-serialize of unchanged proposals is
    recognizably a no-op for the M2 idempotency fingerprint (FR-18 / Lesson L16-#8). The VIPP pins
    ``envelope_seq`` into every disposition so the applier can refuse a stale disposition (FR-18).
    """

    project_id: str
    envelope_seq: int = 0
    generated_at: str = ""
    proposals: List[EnvelopedProposal] = field(default_factory=list)
    content_checksum: str = ""
    protocol_version: str = PROTOCOL_VERSION

    def checksum_payload(self) -> List[Dict[str, Any]]:
        """The content ``content_checksum`` is computed over (proposals only; seq/ts excluded)."""
        return [p.to_dict() for p in self.proposals]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "kind": "vipp-proposal-envelope",
            "protocol_version": self.protocol_version,
            "project_id": self.project_id,
            "envelope_seq": self.envelope_seq,
            "generated_at": self.generated_at,
            "content_checksum": self.content_checksum,
            "proposals": [p.to_dict() for p in self.proposals],
        }

    @staticmethod
    def from_json(data: Any) -> "ProposalEnvelope":
        d = json.loads(data) if isinstance(data, (str, bytes)) else data
        return ProposalEnvelope(
            project_id=d.get("project_id", ""),
            envelope_seq=int(d.get("envelope_seq", 0)),
            generated_at=d.get("generated_at", ""),
            content_checksum=d.get("content_checksum", ""),
            proposals=[EnvelopedProposal.from_dict(p) for p in d.get("proposals", [])],
            protocol_version=d.get("protocol_version", PROTOCOL_VERSION),
        )

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "ProposalEnvelope":
        return ProposalEnvelope.from_json(d)


@dataclass(frozen=True)
class VippDisposition:
    """One proposal's source-labeled disposition (FR-4).

    ``envelope_seq`` is pinned from the envelope the VIPP read (FR-18 stale-refusal). For an ACCEPT the
    disposition carries **no params** — the applier takes ``kind``/``params``/``base_sha`` from the
    *trusted* inbox entry matched by ``proposal_id`` (FR-5); only a COUNTER's ``counter_params``
    override, and a COUNTER may never change ``kind`` or ``base_sha`` (FR-4/FR-5).
    """

    proposal_id: str
    decision: Decision
    envelope_seq: int = 0
    reason: str = ""
    counter_params: Optional[Dict[str, Any]] = None
    claims: List[LabeledClaim] = field(default_factory=list)
    # FR-9b (stakeholder-panel M2): the unanswered (all-OMIT) questions' routing context —
    # each {"symbol": value_path, "claim": text}. Strictly ADDITIVE/optional: empty (and omitted
    # from ``to_dict``) for every disposition except an OMIT-default ACCEPT, so existing
    # ``evaluate_envelope`` output is byte-identical (R2-S1).
    unresolved: List[Dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        out = {
            "proposal_id": self.proposal_id,
            "decision": self.decision.value,
            "envelope_seq": self.envelope_seq,
            "reason": self.reason,
            "counter_params": (
                dict(self.counter_params) if self.counter_params is not None else None
            ),
            "claims": [c.to_dict() for c in self.claims],
        }
        if (
            self.unresolved
        ):  # additive: absent when there is nothing to route (back-compat)
            out["unresolved"] = [dict(u) for u in self.unresolved]
        return out

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "VippDisposition":
        cp = d.get("counter_params")
        return VippDisposition(
            proposal_id=d["proposal_id"],
            decision=_decision_from_value(d["decision"]),
            envelope_seq=int(d.get("envelope_seq", 0)),
            reason=d.get("reason", ""),
            counter_params=(dict(cp) if cp is not None else None),
            claims=[LabeledClaim.from_dict(c) for c in d.get("claims", [])],
            unresolved=[dict(u) for u in (d.get("unresolved") or [])],
        )

    def to_markdown(self) -> str:
        # The decision is a SECTION HEADER (not a "- " bullet) so the FR-21 label gate
        # (``fde.deterministic_compose.assert_all_labeled``) checks only the labeled claim
        # bullets beneath it — the unlabeled "ACCEPT/REJECT/COUNTER" decision is not mistaken
        # for an untagged load-bearing claim.
        head = f"### {self.decision.value} `{self.proposal_id}`"
        if self.reason:
            head += (
                f" — {oneline(self.reason)}"  # collapse newlines (H1 defense-in-depth)
            )
        lines = [head]
        lines.extend(c.to_markdown() for c in self.claims)
        return "\n".join(lines)


@dataclass
class VippReport:
    """Outbound disposition artifact (``dispositions.json`` canonical, ``.md`` derived).

    Identity = ``project_id`` + ``protocol_version`` (FR-2). ``sdk_version`` is **provenance-only**
    ("the SDK build that ran the VIPP brain"), **never authority** — this is a *project*-authority
    artifact, so a reader must not treat a disposition as SDK-blessed (FR-2 / CRP R1 A-F7).
    """

    project_id: str
    generated_at: str = ""
    envelope_seq: int = 0
    dispositions: List[VippDisposition] = field(default_factory=list)
    evidence_available: bool = (
        True  # False ⇒ degraded (no Sapper ground truth) — narrative only
    )
    sdk_version: str = ""  # provenance-only (FR-2) — NOT authority
    cost_usd: float = 0.0
    llm_used: bool = False
    protocol_version: str = PROTOCOL_VERSION
    # FR-9/FR-19 (stakeholder-panel M2): synthetic, unratified advisories from the panel pass — each
    # a plain dict (see ``_render_advisories``). ADDITIVE/optional and rendered in a *separate*
    # section: they never enter ``dispositions`` and never mutate a verdict (FR-9). Empty ⇒ omitted.
    panel_advisories: List[Dict[str, Any]] = field(default_factory=list)

    def counts(self) -> Dict[str, int]:
        out = {d.value: 0 for d in Decision}
        for disp in self.dispositions:
            out[disp.decision.value] = out.get(disp.decision.value, 0) + 1
        return out

    def to_dict(self) -> Dict[str, Any]:
        out = {
            "kind": "vipp-dispositions",
            "protocol_version": self.protocol_version,
            "project_id": self.project_id,
            "generated_at": self.generated_at,
            "envelope_seq": self.envelope_seq,
            "evidence_available": self.evidence_available,
            "sdk_version": self.sdk_version,
            "cost_usd": self.cost_usd,
            "llm_used": self.llm_used,
            "dispositions": [d.to_dict() for d in self.dispositions],
        }
        if (
            self.panel_advisories
        ):  # additive: absent when the panel pass did not run (back-compat)
            out["panel_advisories"] = [dict(a) for a in self.panel_advisories]
        return out

    @staticmethod
    def from_json(data: Any) -> "VippReport":
        d = json.loads(data) if isinstance(data, (str, bytes)) else data
        return VippReport(
            project_id=d.get("project_id", ""),
            generated_at=d.get("generated_at", ""),
            envelope_seq=int(d.get("envelope_seq", 0)),
            dispositions=[
                VippDisposition.from_dict(x) for x in d.get("dispositions", [])
            ],
            evidence_available=bool(d.get("evidence_available", True)),
            sdk_version=d.get("sdk_version", ""),
            cost_usd=float(d.get("cost_usd", 0.0)),
            llm_used=bool(d.get("llm_used", False)),
            protocol_version=d.get("protocol_version", PROTOCOL_VERSION),
            panel_advisories=[dict(a) for a in (d.get("panel_advisories") or [])],
        )

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "VippReport":
        return VippReport.from_json(d)

    def to_prompt_section(self) -> str:
        """Bounded, label-preserving view for prompt/EventBus injection (Keiyaku parity)."""
        lines = [
            f"## VIPP Dispositions (project authority) — {self.project_id} "
            f"(envelope_seq {self.envelope_seq})"
        ]
        if not self.evidence_available:
            lines.append(
                "> OBSERVED (project): ground truth unavailable — dispositions default to ACCEPT "
                "with a labeled 'no ground truth' qualifier (FR-4)."
            )
        for disp in self.dispositions:
            lines.append(disp.to_markdown())
        return "\n".join(lines) + "\n"

    def to_markdown(self) -> str:
        c = self.counts()
        # Metadata is rendered as plain lines (NOT "- " bullets) so the FR-21 label gate only
        # inspects the labeled claim bullets under each "### {decision}" header.
        lines = [
            "# VIPP Dispositions",
            "",
            f"project_id: `{self.project_id}` · envelope_seq: `{self.envelope_seq}`",
            f"generated_at: {self.generated_at}",
            f"protocol_version: `{self.protocol_version}` · sdk_version (provenance-only): "
            f"`{self.sdk_version}`",
            f"counts: ACCEPT {c['ACCEPT']} · REJECT {c['REJECT']} · COUNTER {c['COUNTER']} · "
            f"cost_usd {self.cost_usd:.4f} · llm_used {self.llm_used}",
            "",
            "> Derived view — `dispositions.json` is canonical. Each claim is labeled OBSERVED "
            "(project) / MECHANISM (sdk) / PREDICTION. `sdk_version` is provenance, not authority.",
        ]
        if not self.evidence_available:
            lines += [
                "",
                "> **OBSERVED (project): no ground-truth authority** — the oracle was absent or "
                "returned OMIT for every proposal; dispositions default to ACCEPT with a labeled "
                "qualifier (FR-4).",
            ]
        for disp in self.dispositions:
            lines += ["", disp.to_markdown()]
        lines += _render_advisories(self.panel_advisories)
        return "\n".join(lines) + "\n"


def _render_advisories(advisories: List[Dict[str, Any]]) -> List[str]:
    """Render the synthetic stakeholder-panel advisory section (FR-9/FR-19).

    Anti-anchoring (FR-19): a persistent "synthetic, unratified" banner, the persona brief adjacent,
    and the **original OMIT question** — so a human ratifies against the gap, not the persuasive
    fill. Only the answer is a labeled ``- **OBSERVED (project, synthetic)**`` bullet (so the FR-21
    gate passes); the banner / question / brief are plain or block-quoted lines (never claim bullets).
    """
    if not advisories:
        return []
    out: List[str] = [
        "",
        "## Stakeholder panel — synthetic, unratified advisories",
        "",
        "> ⚠ SYNTHETIC, UNRATIFIED — role-played stand-ins, not real stakeholders. The verdicts "
        "above are UNCHANGED (FR-9); confirm any advisory with a human before ratifying (FR-18).",
    ]
    for a in advisories:
        symbol = oneline(a.get("symbol", ""))
        out += ["", f"### `{a.get('proposal_id', '')}` — OMIT `{symbol}`", ""]
        out.append(f"original question: {oneline(a.get('claim', ''))}")
        status = a.get("status", "")
        if status == "answered":
            role_id = a.get("role_id", "")
            goals = "; ".join(a.get("brief_goals", []) or []) or "(none stated)"
            grounding = a.get("grounding", "")
            out.append(f"persona brief ({role_id}): {goals}")
            out.append("")
            out.append(
                f"- **OBSERVED (project, synthetic)** {oneline(a.get('answer', ''))} "
                f"— _panel:{role_id} ({grounding})_"
            )
        elif status == "unavailable":
            out += [
                "",
                f"> stakeholder {a.get('role_id', '')!r} unavailable — stays OMIT (FR-16)",
            ]
        elif status == "deferred":
            out += ["", "> deferred — panel query cap reached (FR-17); stays OMIT"]
        else:  # no-stakeholder
            out += ["", "> no stakeholder available to answer — stays OMIT (FR-9c)"]
    return out
