# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""ObservabilitySpec — the single declarative model all o11y artifact generation reads.

The essential model behind the artifact abstraction (the household-o11y design docs,
``SDK_OBSERVABILITY_ARTIFACT_ABSTRACTION_REQUIREMENTS.md`` FR-OAA-1): a *signal* with an optional
*threshold* (or a raw PromQL ``expr`` escape hatch, reconciling ``manifest.AlertTemplate``), in a
service/business *context*, rendered to an artifact.

This is **M0**: the model + a normalizer from ``observability.yaml``. It changes **no generation
behavior** — it is the shared foundation the alert renderer (M1) and the prose parser (M5a) both
consume, built once. The alert-relevant surface (signals + receivers) is modeled explicitly; the
rest of ``observability.yaml`` is carried verbatim in ``context`` so nothing is dropped and the
modeled subset round-trips exactly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union

# The closed comparison-operator vocabulary (must match the alert renderer + the §2.12 grammar).
ALERT_OPS = frozenset({">", "<", ">=", "<=", "=="})
Number = Union[int, float]


@dataclass(frozen=True)
class Threshold:
    """A declarative alert condition: ``<signal> <op> <value>`` held ``for_`` a duration.

    ``for_`` carries the trailing underscore because ``for`` is a Python keyword; it serializes
    back to the ``for`` key. ``value`` preserves its source numeric type (int stays int, float
    stays float) so round-trips are exact.
    """

    op: str
    value: Number
    severity: str = "warning"
    for_: str = "0m"
    unit: str = ""

    def __post_init__(self) -> None:
        if self.op not in ALERT_OPS:
            raise ValueError(f"threshold op {self.op!r} not in {sorted(ALERT_OPS)}")


@dataclass
class Signal:
    """A thing to watch. Carries EITHER a declarative ``threshold`` OR a raw PromQL ``expr`` (the
    AlertTemplate escape hatch), or neither (informational / panel-only). ``origin`` distinguishes
    convention RED signals from project-declared domain signals — a tag, not a separate code path
    (this is what subsumes the old ``convention_metrics`` / ``declared_metrics`` split)."""

    name: str
    threshold: Optional[Threshold] = None
    expr: Optional[str] = None
    origin: str = "declared"  # "declared" | "convention"


@dataclass
class Receiver:
    """An alert destination. ``target`` is expected to be env-indirected (``${VAR}``); literal
    secrets are a parser concern (FR-OTP-7), not enforced by the model."""

    name: str
    type: str = ""
    target: str = ""
    severities: List[str] = field(default_factory=list)


@dataclass
class ObservabilitySpec:
    """The single input to o11y artifact generation."""

    signals: List[Signal] = field(default_factory=list)
    receivers: List[Receiver] = field(default_factory=list)
    # Verbatim carry of the non-alert surface (service_levels, owners, collection, alerting.channels,
    # runbook, …) so downstream renderers lose nothing while M0 stays scoped to the alert path.
    context: Dict[str, Any] = field(default_factory=dict)
    provenance_default: str = ""
    industry_dataset: str = ""
    domain: str = "observability"

    # -- emit helpers: inverse of the normalizer, for the round-trip gate (FR-OAA-10) --

    def metric_thresholds(self) -> Dict[str, Dict[str, Any]]:
        """Re-emit the ``alerting.metric_thresholds`` map (signals carrying a threshold)."""
        out: Dict[str, Dict[str, Any]] = {}
        for s in self.signals:
            if s.threshold is None:
                continue
            t = s.threshold
            row: Dict[str, Any] = {"op": t.op, "value": t.value}
            if t.unit:
                row["unit"] = t.unit
            row["severity"] = t.severity
            row["for"] = t.for_
            out[s.name] = row
        return out

    def receivers_list(self) -> List[Dict[str, Any]]:
        """Re-emit the ``alerting.receivers`` list."""
        return [
            {"name": r.name, "type": r.type, "target": r.target, "severities": list(r.severities)}
            for r in self.receivers
        ]


def from_observability_yaml(data: Dict[str, Any]) -> ObservabilitySpec:
    """Normalize a parsed ``observability.yaml`` mapping into an :class:`ObservabilitySpec`.

    Mapping (FR-OAA-1/12):
      - ``alerting.metric_thresholds`` → ``signals[].threshold`` (``origin='declared'``)
      - ``alerting.receivers`` → ``receivers[]``
      - everything else (``service_levels``, ``owners``, ``collection``, ``alerting.channels``,
        ``runbook``, ``industry_dataset``, ``provenance_default``) → carried verbatim in ``context``.

    Strict (loud-fail like the assembly parsers): a non-mapping root, a malformed threshold (bad
    ``op``, missing ``value``), or a receiver without a ``name`` raises ``ValueError``.
    """
    if not isinstance(data, dict):
        raise ValueError("observability.yaml must be a mapping")

    # Default only on absence (None); a present-but-wrong-type value must loud-fail, so we do NOT
    # use `x or {}` (which would swallow a falsy `[]`/`""` as "absent").
    alerting = data.get("alerting")
    if alerting is None:
        alerting = {}
    if not isinstance(alerting, dict):
        raise ValueError("observability.yaml: `alerting` must be a mapping")

    thresholds = alerting.get("metric_thresholds")
    if thresholds is None:
        thresholds = {}
    if not isinstance(thresholds, dict):
        raise ValueError("observability.yaml: `alerting.metric_thresholds` must be a mapping")

    signals: List[Signal] = []
    for name, row in thresholds.items():
        if not isinstance(row, dict) or "op" not in row or "value" not in row:
            raise ValueError(f"metric_thresholds[{name!r}] needs `op` and `value`")
        value = row["value"]
        # bool is a subclass of int — exclude it; a threshold value must be a real number, else
        # the rendered PromQL expr (`<metric> <op> <value>`) is nonsense.
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"metric_thresholds[{name!r}] `value` must be a number, got {value!r}")
        signals.append(
            Signal(
                name=str(name),
                threshold=Threshold(
                    op=str(row["op"]),
                    value=value,  # preserve numeric type for exact round-trip
                    severity=str(row.get("severity", "warning")),
                    for_=str(row.get("for", "0m")),
                    unit=str(row.get("unit", "")),
                ),
                origin="declared",
            )
        )

    receivers_raw = alerting.get("receivers")
    if receivers_raw is None:
        receivers_raw = []
    if not isinstance(receivers_raw, list):
        raise ValueError("observability.yaml: `alerting.receivers` must be a list")
    receivers: List[Receiver] = []
    for r in receivers_raw:
        if not isinstance(r, dict) or "name" not in r:
            raise ValueError("alerting.receivers[] entries need a `name`")
        receivers.append(
            Receiver(
                name=str(r["name"]),
                type=str(r.get("type", "")),
                target=str(r.get("target", "")),
                severities=[str(s) for s in (r.get("severities") or [])],
            )
        )

    # Carry the rest verbatim (lossless for downstream renderers). alerting.channels is neither a
    # signal nor a receiver, so it rides along under context["alerting"]["channels"].
    context: Dict[str, Any] = {
        k: v for k, v in data.items()
        if k not in {"alerting", "provenance_default", "industry_dataset", "domain"}
    }
    channels = alerting.get("channels")
    if channels is not None:
        context.setdefault("alerting", {})["channels"] = channels

    return ObservabilitySpec(
        signals=signals,
        receivers=receivers,
        context=context,
        provenance_default=str(data.get("provenance_default", "")),
        industry_dataset=str(data.get("industry_dataset", "")),
        domain=str(data.get("domain", "observability")),
    )
