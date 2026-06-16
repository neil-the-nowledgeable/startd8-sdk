"""BenchmarkRunSpec — the immutable single source of truth for a benchmark run (FR-36).

The orchestrator reads ONLY this spec, not ad hoc CLI flags / env vars / script defaults,
so two "same" runs cannot silently differ by a hidden default. The spec is frozen
(immutable), validated, JSON-serializable, and carries a content hash (``spec_hash``)
that is the run's identity — used for pre-registration (FR-34), provenance (FR-28), and
the per-cell idempotency key (FR-38, M3).
"""
from __future__ import annotations

import hashlib
import json
from typing import Dict, Iterator, NamedTuple, Optional, Tuple

from pydantic import BaseModel, ConfigDict, Field, field_validator


class MatrixCell(NamedTuple):
    """One coordinate in the service x model x repetition (x leverage x role) matrix.

    ``leverage`` (K2) and ``lead``/``drafter`` (K3) default so legacy construction is unchanged and
    a default cell (leverage off, diagonal lead==drafter==model) is byte-identical to pre-K2/pre-K3
    (FR-1 backward compat). K3: ``lead``/``drafter`` are ``None`` ⇒ both resolve to ``model`` (the
    diagonal); set them to distinct agent specs for an off-diagonal hybrid-team cell.
    """
    service: str
    model: str            # agent spec, e.g. "anthropic:claude-fable-5"
    repetition: int       # 0-based
    leverage: str = "off"  # K2: "off" (LLM-maximal, today's default) | "on" (SDK leverage engaged)
    lead: Optional[str] = None     # K3 (FR-K3-1): lead agent; None ⇒ model (diagonal)
    drafter: Optional[str] = None  # K3 (FR-K3-1): drafter agent; None ⇒ model (diagonal)

    @property
    def resolved_lead(self) -> str:
        return self.lead or self.model

    @property
    def resolved_drafter(self) -> str:
        return self.drafter or self.model

    @property
    def is_diagonal(self) -> bool:
        """True when lead==drafter (the single-model default). The role segment is omitted from
        cell_id/sandbox_dir_name for diagonal cells so they stay byte-identical to pre-K3."""
        return self.resolved_lead == self.resolved_drafter


class BenchmarkRunSpec(BaseModel):
    """Immutable description of a benchmark run (FR-36).

    Frozen: attempting to mutate a field raises. Build a new spec instead.
    """

    model_config = ConfigDict(frozen=True)

    name: str
    # Roster as provider:model agent specs (FR-5). Order preserved; deduped at validation.
    models: Tuple[str, ...]
    # Service keys (must correspond to seed files), e.g. "cartservice".
    services: Tuple[str, ...]
    repetitions: int = 5  # OQ-2 default floor N>=5

    # LLM-maximize execution mode (FR-1/FR-2/FR-27). Benchmark default: shortcuts off, micro-prime off.
    llm_maximize: bool = True
    micro_prime_enabled: bool = False

    # K2 leverage delta (FR-K2-1). The states this run pairs each coordinate across. Default
    # ("off",) = today's single-state matrix (FR-1 backward compat: byte-identical hash/cells/
    # sandboxes). ("off","on") runs each coordinate twice — leverage OFF (LLM-maximal) and ON
    # (SDK scaffolding engaged) — for a per-model Δquality/Δcost.
    leverage_states: Tuple[str, ...] = ("off",)
    # Which on-path mechanisms a ``leverage="on"`` cell engages (R2-S3). Names *what on-cells run*
    # (``leverage_states`` names *which cells exist*). Validated ⊆ {routing, micro_prime}; the
    # micro_prime+benchmark-mode combo is rejected downstream (run_prime_workflow.py:385).
    leverage_on_config: Dict[str, bool] = Field(
        default_factory=lambda: {"routing": True, "micro_prime": False})

    # Scoring (FR-11): a reference string identifying the composite-quality formula in use.
    scoring_formula: str = "compile_gate+compute_disk_quality_score(0.4/0.2/0.2/0.2)"

    # Budget guardrails (FR-33). budget_ceiling_usd is REQUIRED at run time (fail-closed),
    # but may be None in a spec that is only being sized via --dry-run.
    budget_ceiling_usd: Optional[float] = None
    per_cell_cap_usd: Optional[float] = None

    # Sizing assumptions for the pre-run cost estimate (NOT billing — rough per-cell token
    # counts used only by estimate_run_cost). Real cost is captured per cell at run time.
    est_input_tokens_per_cell: int = 8000
    est_output_tokens_per_cell: int = 6000
    # K2 (R1-S5): leverage=on cells run heavier commands (routing/micro-prime, no benchmark-mode
    # shortcut → more LLM calls), so they cost more than off cells. This rough multiplier lets the
    # preflight model that asymmetry instead of pricing every cell flat (a K2 run could otherwise
    # pass preflight then abort mid-run). Sizing-only (excluded from spec_hash, like the token estimates).
    est_on_cost_multiplier: float = 1.5

    # Provenance / reproducibility: service -> seed file sha256 (FR-19/FR-28).
    seed_hashes: Dict[str, str] = Field(default_factory=dict)
    proto_sha256: Optional[str] = None
    sdk_version: Optional[str] = None

    # --- validators ---------------------------------------------------------

    @field_validator("models", "services")
    @classmethod
    def _non_empty_unique(cls, v: Tuple[str, ...]) -> Tuple[str, ...]:
        if not v:
            raise ValueError("must be non-empty")
        if len(set(v)) != len(v):
            raise ValueError(f"duplicate entries: {[x for x in v if list(v).count(x) > 1]}")
        return v

    @field_validator("repetitions")
    @classmethod
    def _positive_reps(cls, v: int) -> int:
        if v < 1:
            raise ValueError("repetitions must be >= 1")
        return v

    @field_validator("budget_ceiling_usd", "per_cell_cap_usd")
    @classmethod
    def _positive_budget(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and v <= 0:
            raise ValueError("budget values must be > 0 when set")
        return v

    @field_validator("leverage_states")
    @classmethod
    def _valid_leverage_states(cls, v: Tuple[str, ...]) -> Tuple[str, ...]:
        if not v:
            raise ValueError("leverage_states must be non-empty")
        allowed = {"off", "on"}
        bad = [x for x in v if x not in allowed]
        if bad:
            raise ValueError(f"leverage_states must be ⊆ {sorted(allowed)}; got {bad}")
        if len(set(v)) != len(v):
            raise ValueError(f"duplicate leverage states: {v}")
        return v

    @field_validator("leverage_on_config")
    @classmethod
    def _valid_on_config(cls, v: Dict[str, bool]) -> Dict[str, bool]:
        allowed = {"routing", "micro_prime"}
        bad = [k for k in v if k not in allowed]
        if bad:
            raise ValueError(f"leverage_on_config keys must be ⊆ {sorted(allowed)}; got {bad}")
        return v

    # --- derived ------------------------------------------------------------

    @property
    def total_cells(self) -> int:
        return (len(self.services) * len(self.models) * self.repetitions
                * len(self.leverage_states))

    def cells(self) -> Iterator[MatrixCell]:
        """Deterministic iteration order: service, then model, then repetition, then **leverage
        innermost** (R5-S1) — for each (service, model, rep) emit the leverage states back-to-back
        so a coordinate's off/on pair is adjacent (budget-abort leaves paired prefixes, R2-S4).
        With the default ``leverage_states=("off",)`` this yields exactly today's cells."""
        for service in self.services:
            for model in self.models:
                for rep in range(self.repetitions):
                    for leverage in self.leverage_states:
                        yield MatrixCell(service=service, model=model, repetition=rep,
                                         leverage=leverage)

    def spec_hash(self) -> str:
        """SHA-256 of the identity-defining fields (excludes sizing-only token estimates
        and sdk_version, which don't change WHAT is run). This hash is the run identity."""
        identity = {
            "name": self.name,
            "models": list(self.models),
            "services": list(self.services),
            "repetitions": self.repetitions,
            "llm_maximize": self.llm_maximize,
            "micro_prime_enabled": self.micro_prime_enabled,
            "scoring_formula": self.scoring_formula,
            "budget_ceiling_usd": self.budget_ceiling_usd,
            "per_cell_cap_usd": self.per_cell_cap_usd,
            "seed_hashes": dict(sorted(self.seed_hashes.items())),
            "proto_sha256": self.proto_sha256,
        }
        # K2 axis is added to the identity ONLY when it differs from the default single state, so a
        # default off-only spec hashes byte-identically to a pre-K2 spec (FR-1 / R1-F5 backward compat).
        if tuple(self.leverage_states) != ("off",):
            identity["leverage_states"] = list(self.leverage_states)
            identity["leverage_on_config"] = dict(sorted(self.leverage_on_config.items()))
        blob = json.dumps(identity, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()

    def to_json(self) -> str:
        d = self.model_dump()
        d["spec_hash"] = self.spec_hash()
        return json.dumps(d, indent=2, sort_keys=True, default=list) + "\n"

    @classmethod
    def from_dict(cls, data: dict) -> "BenchmarkRunSpec":
        data = {k: v for k, v in data.items() if k != "spec_hash"}
        if isinstance(data.get("models"), list):
            data["models"] = tuple(data["models"])
        if isinstance(data.get("services"), list):
            data["services"] = tuple(data["services"])
        return cls(**data)
