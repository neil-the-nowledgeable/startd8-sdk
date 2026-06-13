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
from typing import Dict, Iterator, List, NamedTuple, Optional, Tuple

from pydantic import BaseModel, ConfigDict, Field, field_validator


class MatrixCell(NamedTuple):
    """One coordinate in the service x model x repetition matrix."""
    service: str
    model: str            # agent spec, e.g. "anthropic:claude-fable-5"
    repetition: int       # 0-based


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

    # --- derived ------------------------------------------------------------

    @property
    def total_cells(self) -> int:
        return len(self.services) * len(self.models) * self.repetitions

    def cells(self) -> Iterator[MatrixCell]:
        """Deterministic iteration order: service, then model, then repetition."""
        for service in self.services:
            for model in self.models:
                for rep in range(self.repetitions):
                    yield MatrixCell(service=service, model=model, repetition=rep)

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
