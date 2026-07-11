# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""Keiyaku-shaped contracts for the Forward Deployed Engineer (FDE).

These are the typed boundary between the project's deployed posting (``.startd8/fde/``)
and the SDK's mechanism-authority brain. Per FR-12/FR-20 the **JSON form is canonical**
(``to_dict``/``from_json``); the markdown (``to_markdown``) is a *derived, lossy* human
view — there is intentionally no ``from_markdown`` round-trip promise. Each contract also
exposes ``to_prompt_section`` for bounded prompt/EventBus injection (Keiyaku K-6…K-10 parity).

The source-labeling guarantee (FR-6/FR-21) is structural: every load-bearing claim is a
:class:`LabeledClaim` carrying one of three labels — ``OBSERVED`` (project evidence),
``MECHANISM`` (SDK recorded fact), or ``PREDICTION`` (SDK live classification). The
deterministic composer fills these slots from ``sources.py``; an LLM narrator may only
reference already-emitted claim ids (it cannot mint new load-bearing claims).
"""

from __future__ import annotations

import dataclasses
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

# Bump when the contract *shape* changes — distinct from the SDK version (FR-20 / R1-F3).
PROTOCOL_VERSION = "1.0"


class FdeMode(str, Enum):
    EXPLAIN = "explain"
    PREFLIGHT = "preflight"


class ClaimLabel(str, Enum):
    """The three source labels (FR-6 / FR-21).

    OBSERVED   — project evidence (what happened on disk; from the SA triage).
    MECHANISM  — SDK recorded fact (read from an artifact the run produced).
    PREDICTION — SDK live classification (computed now; the task has not run).
    """

    OBSERVED = "OBSERVED (project)"
    MECHANISM = "MECHANISM (sdk)"
    PREDICTION = "PREDICTION (sdk, live)"


# Recognized tag prefixes the labeling lint accepts (FR-21). A "conflict"/"unavailable"
# qualifier may be appended in parentheses, e.g. "MECHANISM (sdk, conflict)".
RECOGNIZED_LABEL_PREFIXES = ("OBSERVED (project", "MECHANISM (sdk", "PREDICTION (sdk")


@dataclass(frozen=True)
class LabeledClaim:
    """A single load-bearing claim with its source label and authority citation."""

    label: ClaimLabel
    text: str
    source: str = ""  # the §6 symbol/artifact that adjudicates this claim
    claim_id: str = ""  # stable id a narrator may reference (no new claims)
    qualifier: str = (
        ""  # optional: "conflict" | "unavailable" | "low-confidence — file not materialized"
    )

    def tag(self) -> str:
        base = self.label.value
        if self.qualifier:
            # turn "MECHANISM (sdk)" + "conflict" -> "MECHANISM (sdk, conflict)"
            return base[:-1] + f", {self.qualifier})"
        return base

    def to_markdown(self) -> str:
        cite = f" — _{self.source}_" if self.source else ""
        return f"- **{self.tag()}** {self.text}{cite}"

    def to_dict(self) -> Dict[str, Any]:
        d = dataclasses.asdict(self)
        d["label"] = self.label.value
        return d

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "LabeledClaim":
        return LabeledClaim(
            label=_label_from_value(d["label"]),
            text=d.get("text", ""),
            source=d.get("source", ""),
            claim_id=d.get("claim_id", ""),
            qualifier=d.get("qualifier", ""),
        )


def _label_from_value(value: str) -> ClaimLabel:
    for lbl in ClaimLabel:
        if lbl.value == value:
            return lbl
    # tolerate a qualified tag like "MECHANISM (sdk, conflict)"
    for lbl in ClaimLabel:
        if value.startswith(lbl.value[: lbl.value.index("(") + 4]):
            return lbl
    raise ValueError(f"unrecognized claim label: {value!r}")


@dataclass(frozen=True)
class FdeRequest:
    """Inbound request (``fde-request.md`` serialized; FR-11 / FR-27 inbound schema)."""

    mode: FdeMode
    run_output_dir: Optional[str] = None  # required for explain
    plan_path: Optional[str] = None  # preflight
    requirements_path: Optional[str] = None  # preflight
    feature_ids: List[str] = field(default_factory=list)  # explain --feature-id (R5-S4)
    sdk_version: Optional[str] = None
    protocol_version: str = PROTOCOL_VERSION

    def validate(self) -> None:
        if self.mode == FdeMode.EXPLAIN and not self.run_output_dir:
            raise ValueError("explain request requires run_output_dir")
        if self.mode == FdeMode.PREFLIGHT and not (
            self.plan_path or self.requirements_path
        ):
            raise ValueError(
                "preflight request requires plan_path or requirements_path"
            )

    def to_dict(self) -> Dict[str, Any]:
        d = dataclasses.asdict(self)
        d["mode"] = self.mode.value
        return d

    @staticmethod
    def from_json(data: Any) -> "FdeRequest":
        d = json.loads(data) if isinstance(data, (str, bytes)) else data
        req = FdeRequest(
            mode=FdeMode(d["mode"]),
            run_output_dir=d.get("run_output_dir"),
            plan_path=d.get("plan_path"),
            requirements_path=d.get("requirements_path"),
            feature_ids=list(d.get("feature_ids", [])),
            sdk_version=d.get("sdk_version"),
            protocol_version=d.get("protocol_version", PROTOCOL_VERSION),
        )
        return req

    def to_markdown(self) -> str:
        lines = [
            "# FDE Request",
            "",
            f"- mode: `{self.mode.value}`",
        ]
        if self.run_output_dir:
            lines.append(f"- run_output_dir: `{self.run_output_dir}`")
        if self.plan_path:
            lines.append(f"- plan_path: `{self.plan_path}`")
        if self.requirements_path:
            lines.append(f"- requirements_path: `{self.requirements_path}`")
        if self.feature_ids:
            lines.append(f"- feature_ids: {', '.join(self.feature_ids)}")
        lines.append(f"- sdk_version: `{self.sdk_version or ''}`")
        lines.append(f"- protocol_version: `{self.protocol_version}`")
        return "\n".join(lines) + "\n"


@dataclass
class FailureExplanation:
    """One failure's composed explanation: SA evidence + SDK mechanism, source-labeled."""

    feature_id: str
    element_id: Optional[str] = None
    claims: List[LabeledClaim] = field(default_factory=list)
    correction: Optional[str] = (
        None  # FR-7: where the FDE corrects an SA mechanism misattribution
    )
    disagreement: bool = False  # FR-25: both halves valid but divergent

    def to_dict(self) -> Dict[str, Any]:
        return {
            "feature_id": self.feature_id,
            "element_id": self.element_id,
            "claims": [c.to_dict() for c in self.claims],
            "correction": self.correction,
            "disagreement": self.disagreement,
        }

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "FailureExplanation":
        return FailureExplanation(
            feature_id=d["feature_id"],
            element_id=d.get("element_id"),
            claims=[LabeledClaim.from_dict(c) for c in d.get("claims", [])],
            correction=d.get("correction"),
            disagreement=bool(d.get("disagreement", False)),
        )


@dataclass
class FdeExplanation:
    """Outbound explain artifact (``fde-explanation.json`` canonical, ``.md`` derived)."""

    run_id: str
    generated_at: str
    sdk_version: str
    failures: List[FailureExplanation] = field(default_factory=list)
    batch_claims: List[LabeledClaim] = field(
        default_factory=list
    )  # FR-25 batch patterns
    evidence_available: bool = True  # False ⇒ degraded MECHANISM-only report (FR-25)
    cost_usd: float = 0.0
    llm_used: bool = False
    protocol_version: str = PROTOCOL_VERSION

    def all_claims(self) -> List[LabeledClaim]:
        out: List[LabeledClaim] = list(self.batch_claims)
        for f in self.failures:
            out.extend(f.claims)
        return out

    def to_dict(self) -> Dict[str, Any]:
        return {
            "kind": "fde-explanation",
            "protocol_version": self.protocol_version,
            "run_id": self.run_id,
            "generated_at": self.generated_at,
            "sdk_version": self.sdk_version,
            "evidence_available": self.evidence_available,
            "cost_usd": self.cost_usd,
            "llm_used": self.llm_used,
            "batch_claims": [c.to_dict() for c in self.batch_claims],
            "failures": [f.to_dict() for f in self.failures],
        }

    @staticmethod
    def from_json(data: Any) -> "FdeExplanation":
        d = json.loads(data) if isinstance(data, (str, bytes)) else data
        return FdeExplanation(
            run_id=d["run_id"],
            generated_at=d["generated_at"],
            sdk_version=d.get("sdk_version", ""),
            failures=[FailureExplanation.from_dict(f) for f in d.get("failures", [])],
            batch_claims=[LabeledClaim.from_dict(c) for c in d.get("batch_claims", [])],
            evidence_available=bool(d.get("evidence_available", True)),
            cost_usd=float(d.get("cost_usd", 0.0)),
            llm_used=bool(d.get("llm_used", False)),
            protocol_version=d.get("protocol_version", PROTOCOL_VERSION),
        )

    def to_prompt_section(self) -> str:
        """Bounded, label-preserving view for prompt/EventBus injection (Keiyaku parity)."""
        lines = [f"## FDE Explanation (sdk mechanism authority) — run {self.run_id}"]
        if not self.evidence_available:
            lines.append(
                "> OBSERVED (project): unavailable — degraded MECHANISM-only report."
            )
        for f in self.failures:
            lines.append(
                f"### {f.feature_id}{f'/{f.element_id}' if f.element_id else ''}"
            )
            lines.extend(c.to_markdown() for c in f.claims)
        return "\n".join(lines) + "\n"

    def to_markdown(self) -> str:
        return _render_explanation_markdown(self)


@dataclass
class Landmine:
    """A preflight landmine (FR-8/FR-10): an SDK-behavior assumption the plan gets wrong."""

    landmine_id: str
    track: int  # 1 = prose-assumption, 2 = mechanism-prediction
    severity: str  # critical | high | medium | low (FR-26 rubric)
    title: str
    assumption: str  # what the plan assumes
    mechanism: LabeledClaim  # the authoritative reality it contradicts
    feature_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "landmine_id": self.landmine_id,
            "track": self.track,
            "severity": self.severity,
            "title": self.title,
            "assumption": self.assumption,
            "mechanism": self.mechanism.to_dict(),
            "feature_id": self.feature_id,
        }

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "Landmine":
        return Landmine(
            landmine_id=d["landmine_id"],
            track=int(d["track"]),
            severity=d["severity"],
            title=d["title"],
            assumption=d["assumption"],
            mechanism=LabeledClaim.from_dict(d["mechanism"]),
            feature_id=d.get("feature_id"),
        )


SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}


@dataclass
class FdePreflightReport:
    """Outbound preflight artifact (``fde-preflight.json`` canonical, ``.md`` derived)."""

    generated_at: str
    sdk_version: str
    plan_path: Optional[str] = None
    requirements_path: Optional[str] = None
    landmines: List[Landmine] = field(default_factory=list)
    redaction_manifest: List[str] = field(default_factory=list)  # FR-23
    skipped_track2: List[str] = field(
        default_factory=list
    )  # e.g. "feature X: file_not_materialized"
    track2_ran: bool = False
    cost_usd: float = 0.0
    llm_used: bool = False
    protocol_version: str = PROTOCOL_VERSION

    def sorted_landmines(self) -> List[Landmine]:
        return sorted(self.landmines, key=lambda m: SEVERITY_ORDER.get(m.severity, 9))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "kind": "fde-preflight",
            "protocol_version": self.protocol_version,
            "generated_at": self.generated_at,
            "sdk_version": self.sdk_version,
            "plan_path": self.plan_path,
            "requirements_path": self.requirements_path,
            "track2_ran": self.track2_ran,
            "cost_usd": self.cost_usd,
            "llm_used": self.llm_used,
            "redaction_manifest": list(self.redaction_manifest),
            "skipped_track2": list(self.skipped_track2),
            "landmines": [m.to_dict() for m in self.landmines],
        }

    @staticmethod
    def from_json(data: Any) -> "FdePreflightReport":
        d = json.loads(data) if isinstance(data, (str, bytes)) else data
        return FdePreflightReport(
            generated_at=d["generated_at"],
            sdk_version=d.get("sdk_version", ""),
            plan_path=d.get("plan_path"),
            requirements_path=d.get("requirements_path"),
            landmines=[Landmine.from_dict(m) for m in d.get("landmines", [])],
            redaction_manifest=list(d.get("redaction_manifest", [])),
            skipped_track2=list(d.get("skipped_track2", [])),
            track2_ran=bool(d.get("track2_ran", False)),
            cost_usd=float(d.get("cost_usd", 0.0)),
            llm_used=bool(d.get("llm_used", False)),
            protocol_version=d.get("protocol_version", PROTOCOL_VERSION),
        )

    def to_prompt_section(self) -> str:
        lines = ["## FDE Preflight (sdk-mechanism landmines)"]
        for m in self.sorted_landmines():
            lines.append(
                f"- [{m.severity}] (track {m.track}) {m.title}: {m.assumption}"
            )
            lines.append(f"    {m.mechanism.to_markdown()}")
        return "\n".join(lines) + "\n"

    def to_markdown(self) -> str:
        return _render_preflight_markdown(self)


# --- derived markdown renderers (lossy human view; JSON is canonical) ----------------


def _render_explanation_markdown(exp: FdeExplanation) -> str:
    lines = [
        "# FDE Explanation",
        "",
        f"- run_id: `{exp.run_id}`",
        f"- generated_at: {exp.generated_at}",
        f"- sdk_version: `{exp.sdk_version}` · protocol_version: `{exp.protocol_version}`",
        f"- fde.cost_usd: {exp.cost_usd:.4f} · llm_used: {exp.llm_used}",
        "",
        "> Derived view — `fde-explanation.json` is canonical. Every load-bearing claim is "
        "labeled OBSERVED (project) / MECHANISM (sdk) / PREDICTION (sdk, live).",
    ]
    if not exp.evidence_available:
        lines += [
            "",
            "> **OBSERVED (project): unavailable** — no `service-assistant-triage.json` found. "
            "This is a degraded MECHANISM-only report; run `startd8 assist` first for the full "
            "composition.",
        ]
    if exp.batch_claims:
        lines += ["", "## Batch patterns"]
        lines += [c.to_markdown() for c in exp.batch_claims]
    for f in exp.failures:
        title = f.feature_id + (f"/{f.element_id}" if f.element_id else "")
        lines += ["", f"## {title}"]
        if f.disagreement:
            lines.append(
                "> Evidence and mechanism are both valid but diverge — both halves are "
                "presented below; no solo verdict (FR-6/NR-7)."
            )
        lines += [c.to_markdown() for c in f.claims]
        if f.correction:
            lines += ["", f"**FDE correction (home-authority):** {f.correction}"]
    return "\n".join(lines) + "\n"


def _render_preflight_markdown(rep: FdePreflightReport) -> str:
    lines = [
        "# FDE Preflight — SDK-mechanism landmines",
        "",
        f"- generated_at: {rep.generated_at}",
        f"- sdk_version: `{rep.sdk_version}` · protocol_version: `{rep.protocol_version}`",
        f"- plan: `{rep.plan_path or ''}` · requirements: `{rep.requirements_path or ''}`",
        f"- track2_ran: {rep.track2_ran} · fde.cost_usd: {rep.cost_usd:.4f} · llm_used: {rep.llm_used}",
        "",
        "> Track-2 tier claims are **predictions** (`PREDICTION (sdk, live)`), not observations, "
        "and may diverge from the operator's real `plan-ingestion` run.",
    ]
    if not rep.landmines:
        lines += ["", "_No SDK-mechanism landmines detected._"]
    for m in rep.sorted_landmines():
        lines += [
            "",
            f"## [{m.severity}] {m.title}  _(track {m.track}{f', {m.feature_id}' if m.feature_id else ''})_",
            f"- **Assumption:** {m.assumption}",
            m.mechanism.to_markdown(),  # already a "- **TAG** …" bullet
        ]
    if rep.skipped_track2:
        lines += ["", "## Track-2 skipped", *[f"- {s}" for s in rep.skipped_track2]]
    if rep.redaction_manifest:
        lines += [
            "",
            "## Redaction manifest",
            *[f"- {r}" for r in rep.redaction_manifest],
        ]
    return "\n".join(lines) + "\n"
