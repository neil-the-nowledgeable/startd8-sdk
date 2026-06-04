"""Sapper data model — assumptions, verdicts, friction findings, and the report artifact.

Pure data + ranking, zero external dependencies (FR-SAP-1/2/3). Everything else in the
``sapper`` package depends on this module, so it is deliberately self-contained and
exhaustively unit-tested.

The model encodes the two axes the spikes established
(``docs/design/sapper/...REQUIREMENTS.md`` §0.6/§0.7):
- *existence vs conformance* — which validator owns an assumption (bore vs convention authority/FDE);
- *declaration-surface vs body-internal* — what is reachable at plan time at all.

And the keystone the CRP rounds added (§0.8): ``UnresolvedReason`` distinguishes a genuine
escalation from a tooling gap, so gating / observability / degradation can branch on it.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

SCHEMA_VERSION = "1.0.0"


# --------------------------------------------------------------------------- #
# Enums
# --------------------------------------------------------------------------- #


class AssumptionKind(str, Enum):
    """What kind of claim the plan makes about "the other side of the tunnel" (FR-SAP-1)."""

    INTERFACE_SIGNATURE = "interface_signature"
    IMPORT_AVAILABILITY = "import_availability"
    MODULE_SOURCE = "module_source"
    FRAMEWORK_IDIOM = "framework_idiom"
    ORM_IDIOM = "orm_idiom"
    FIELD_AUTHORITY = "field_authority"
    DOMAIN_RULE = "domain_rule"
    IDENTITY_COLLISION = "identity_collision"
    DECOMPOSITION_INTEGRITY = "decomposition_integrity"
    REACHABILITY = "reachability"


class ValidatorClass(str, Enum):
    """Which validator is responsible for an assumption (FR-SAP-1 routing)."""

    DETERMINISTIC = "deterministic"  # per-element preflight rules (FR-SAP-6)
    PILOT_BORE = "pilot_bore"        # skeleton typecheck (FR-SAP-4)
    FDE_QUERY = "fde_query"          # conformance / ground-truth question (FR-SAP-7)


class AssumptionVerdict(str, Enum):
    """The trichotomy (FR-SAP-2) — distinct from preflight ``CheckStatus``."""

    VALIDATED = "validated"
    REFUTED = "refuted"
    UNRESOLVED = "unresolved"


class UnresolvedReason(str, Enum):
    """Why an assumption is UNRESOLVED (FR-SAP-2, the keystone).

    Lets a consumer separate a genuine escalation (``NEEDS_RULING`` / ``OMIT``) from a
    *tooling gap* (the rest). ``AUTHORITY_ABSENT`` (greenfield, no convention authority) is
    split from ``INPUT_ABSENT`` (broken/stale upstream EMIT) per requirements §0.9.
    """

    NEEDS_RULING = "needs_ruling"        # a real question for the FDE / human
    OMIT = "omit"                        # FDE explicitly declined to answer
    BORE_DEGRADED = "bore_degraded"      # mypy absent / timeout / size-bound
    AUTHORITY_ABSENT = "authority_absent"  # no convention authority (e.g. greenfield)
    INPUT_ABSENT = "input_absent"        # missing/stale EMIT manifest/skeletons


class Severity(str, Enum):
    """Finding severity. Ordering used as a ranking tie-break (FR-SAP-3)."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"

    @property
    def order(self) -> int:
        return {Severity.LOW: 0, Severity.MEDIUM: 1, Severity.HIGH: 2}[self]


class AvoidableCostStage(str, Enum):
    """The downstream stage at which an unaddressed assumption would *otherwise* surface.

    Ordered by escalating cost — the report ranks by this descending (FR-SAP-3).
    """

    REPAIR = "repair"
    INTEGRATION = "integration"
    BOOT = "boot"
    CROSS_FEATURE_CASCADE = "cross-feature-cascade"

    @property
    def order(self) -> int:
        return {
            AvoidableCostStage.REPAIR: 0,
            AvoidableCostStage.INTEGRATION: 1,
            AvoidableCostStage.BOOT: 2,
            AvoidableCostStage.CROSS_FEATURE_CASCADE: 3,
        }[self]


# --------------------------------------------------------------------------- #
# Avoidable-cost mapping (FR-SAP-3 table) — every kind maps to exactly one stage.
# --------------------------------------------------------------------------- #

AVOIDABLE_COST_STAGE: Dict[AssumptionKind, AvoidableCostStage] = {
    AssumptionKind.IMPORT_AVAILABILITY: AvoidableCostStage.REPAIR,
    AssumptionKind.IDENTITY_COLLISION: AvoidableCostStage.REPAIR,
    AssumptionKind.INTERFACE_SIGNATURE: AvoidableCostStage.INTEGRATION,
    AssumptionKind.MODULE_SOURCE: AvoidableCostStage.INTEGRATION,
    AssumptionKind.DECOMPOSITION_INTEGRITY: AvoidableCostStage.INTEGRATION,
    AssumptionKind.REACHABILITY: AvoidableCostStage.INTEGRATION,
    AssumptionKind.FRAMEWORK_IDIOM: AvoidableCostStage.BOOT,
    AssumptionKind.ORM_IDIOM: AvoidableCostStage.BOOT,
    AssumptionKind.FIELD_AUTHORITY: AvoidableCostStage.BOOT,
    AssumptionKind.DOMAIN_RULE: AvoidableCostStage.CROSS_FEATURE_CASCADE,
}

# An unmapped kind defaults here and never raises (FR-SAP-3 / R1-F2).
_DEFAULT_COST_STAGE = AvoidableCostStage.INTEGRATION


def avoidable_cost_stage(
    kind: AssumptionKind,
    *,
    shared_file: bool = False,
) -> AvoidableCostStage:
    """Map an assumption ``kind`` to its avoidable-cost stage.

    ``shared_file=True`` escalates any finding on a file imported by ≥2 features to
    ``CROSS_FEATURE_CASCADE`` (the RUN-032 boot-cascade evidence — one wrong shared file
    zeroes multiple features).
    """
    if shared_file:
        return AvoidableCostStage.CROSS_FEATURE_CASCADE
    return AVOIDABLE_COST_STAGE.get(kind, _DEFAULT_COST_STAGE)


# --------------------------------------------------------------------------- #
# Assumption + FrictionFinding + FrictionReport
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Assumption:
    """A claim the plan makes about the existing codebase (FR-SAP-1).

    Extracted from the *structured* ForwardManifest (§0.9): the rendered skeleton text is
    consumed only by the pilot bore, never re-parsed here.
    """

    id: str
    kind: AssumptionKind
    claim: str
    validator_class: ValidatorClass
    source_ref: str = ""          # e.g. "file_spec:app/jobs.py#import:app.tables"
    file: str = ""                # target file the assumption lives in
    symbol: str = ""              # the referenced name/module, when applicable

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind.value,
            "claim": self.claim,
            "validator_class": self.validator_class.value,
            "source_ref": self.source_ref,
            "file": self.file,
            "symbol": self.symbol,
        }


def finding_fingerprint(kind: AssumptionKind, file: str, symbol: str) -> str:
    """Stable, deterministic hash for cross-run dedup / Kaizen time-to-resolve (R3-F3).

    Intentionally independent of line number / message text so the *same* misalignment
    fingerprints identically across runs even as surrounding code shifts.
    """
    raw = f"{kind.value}\x1f{file}\x1f{symbol}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]


@dataclass
class FrictionFinding:
    """One non-VALIDATED assumption, with the canonical payload (FR-SAP-3).

    ``suggested_fix`` is advisory data only — never auto-applied (NR-8).
    """

    id: str
    kind: AssumptionKind
    verdict: AssumptionVerdict
    severity: Severity
    avoidable_cost_stage: AvoidableCostStage
    fingerprint: str
    file: str = ""
    line: int = 0
    expected: str = ""
    found: str = ""
    reason: Optional[UnresolvedReason] = None   # set iff verdict == UNRESOLVED
    suggested_fix: Optional[str] = None         # advisory only (NR-8)
    context_snippet: Optional[str] = None
    validator_class: Optional[ValidatorClass] = None

    def __post_init__(self) -> None:
        # Invariant: a reason is present iff the verdict is UNRESOLVED.
        if self.verdict == AssumptionVerdict.UNRESOLVED and self.reason is None:
            raise ValueError("UNRESOLVED finding must carry a reason (FR-SAP-2)")
        if self.verdict != AssumptionVerdict.UNRESOLVED and self.reason is not None:
            raise ValueError("only UNRESOLVED findings may carry a reason (FR-SAP-2)")

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "id": self.id,
            "kind": self.kind.value,
            "verdict": self.verdict.value,
            "severity": self.severity.value,
            "avoidable_cost_stage": self.avoidable_cost_stage.value,
            "fingerprint": self.fingerprint,
            "file": self.file,
            "line": self.line,
            "expected": self.expected,
            "found": self.found,
        }
        if self.reason is not None:
            d["reason"] = self.reason.value
        if self.suggested_fix is not None:
            d["suggested_fix"] = self.suggested_fix
        if self.context_snippet is not None:
            d["context_snippet"] = self.context_snippet
        if self.validator_class is not None:
            d["validator_class"] = self.validator_class.value
        return d


def rank_findings(findings: List[FrictionFinding]) -> List[FrictionFinding]:
    """Rank by avoidable cost **descending**, tie-broken by severity then id (FR-SAP-3).

    Deterministic and stable: equal (stage, severity, id) inputs keep input order.
    """
    return sorted(
        findings,
        key=lambda f: (
            -f.avoidable_cost_stage.order,
            -f.severity.order,
            f.id,
        ),
    )


@dataclass
class FrictionReport:
    """The versioned report artifact (``sapper-friction-report.json``) — FR-SAP-3/12."""

    findings: List[FrictionFinding] = field(default_factory=list)
    schema_version: str = SCHEMA_VERSION
    bore_status: str = "checked"        # checked | unavailable (loud degradation, FR-SAP-4)
    notes: List[str] = field(default_factory=list)

    @property
    def ranked(self) -> List[FrictionFinding]:
        return rank_findings(self.findings)

    @property
    def refuted(self) -> List[FrictionFinding]:
        return [f for f in self.findings if f.verdict == AssumptionVerdict.REFUTED]

    @property
    def unresolved(self) -> List[FrictionFinding]:
        return [f for f in self.findings if f.verdict == AssumptionVerdict.UNRESOLVED]

    def counts(self) -> Dict[str, int]:
        c = {v.value: 0 for v in AssumptionVerdict}
        for f in self.findings:
            c[f.verdict.value] += 1
        return c

    def unresolved_rate(self) -> float:
        """Fraction of findings that are UNRESOLVED — the "dumping ground" signal (R1-F6)."""
        if not self.findings:
            return 0.0
        return round(len(self.unresolved) / len(self.findings), 4)

    def reason_breakdown(self) -> Dict[str, int]:
        out: Dict[str, int] = {}
        for f in self.unresolved:
            if f.reason is not None:
                out[f.reason.value] = out.get(f.reason.value, 0) + 1
        return out

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "bore_status": self.bore_status,
            "counts": self.counts(),
            "unresolved_rate": self.unresolved_rate(),
            "reason_breakdown": self.reason_breakdown(),
            "findings": [f.to_dict() for f in self.ranked],
            "notes": list(self.notes),
        }

    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, sort_keys=False)

    def to_markdown(self) -> str:
        lines = [
            "# Sapper friction report",
            "",
            f"- schema_version: `{self.schema_version}`",
            f"- bore_status: `{self.bore_status}`",
            f"- counts: {self.counts()}",
            f"- unresolved_rate: {self.unresolved_rate()}",
            "",
        ]
        if not self.findings:
            lines.append("_No friction findings — plan is aligned (within validated scope)._")
            return "\n".join(lines)
        lines.append("| rank | stage | sev | verdict | kind | file:line | expected → found |")
        lines.append("|---|---|---|---|---|---|---|")
        for i, f in enumerate(self.ranked, 1):
            verdict = f.verdict.value + (f" ({f.reason.value})" if f.reason else "")
            arrow = f"{f.expected} → {f.found}" if (f.expected or f.found) else ""
            lines.append(
                f"| {i} | {f.avoidable_cost_stage.value} | {f.severity.value} | {verdict} "
                f"| {f.kind.value} | `{f.file}:{f.line}` | {arrow} |"
            )
        return "\n".join(lines)
