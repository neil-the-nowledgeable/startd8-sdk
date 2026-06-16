"""Cost estimation + budget guardrails for the benchmark matrix (FR-33 / M2.5).

Three controls, all reading the immutable :class:`BenchmarkRunSpec` (FR-36):
  1. Pre-run cost estimate over (services x models x repetitions) x per-model pricing,
     surfaced via ``estimate_run_cost`` and a ``--dry-run`` sizing table (``format_estimate``).
  2. Per-cell USD cap — a single cell whose actual cost exceeds the cap is flagged.
  3. Cumulative abort-on-budget — the run stops once total actual spend hits the ceiling.

Fail-closed: a run refuses to start without a configured budget ceiling (resolves OQ-8).

Pricing is delegated to ``costs.pricing.PricingService`` (no new pricing tables).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from ..costs.pricing import PricingService
from .run_spec import BenchmarkRunSpec


class BudgetError(RuntimeError):
    """Raised when a benchmark run violates a budget guardrail."""


def _model_id(agent_spec: str) -> str:
    """Strip the provider prefix: 'anthropic:claude-fable-5' -> 'claude-fable-5'."""
    return agent_spec.split(":", 1)[1] if ":" in agent_spec else agent_spec


@dataclass(frozen=True)
class BenchmarkCostEstimate:
    """Pre-run cost estimate (sizing only — not billing)."""
    total_usd: float
    total_cells: int
    per_model_usd: Dict[str, float]          # agent_spec -> estimated USD
    cost_per_cell_usd: Dict[str, float]      # agent_spec -> per-cell USD
    missing_pricing: Tuple[str, ...]         # agent specs with no pricing entry
    cells_per_model: int                     # services x repetitions

    @property
    def has_missing_pricing(self) -> bool:
        return bool(self.missing_pricing)


def estimate_run_cost(
    spec: BenchmarkRunSpec,
    pricing: Optional[PricingService] = None,
) -> BenchmarkCostEstimate:
    """Estimate total spend for a run spec using flat per-cell token assumptions.

    Cost is computed from ``spec.est_input_tokens_per_cell`` / ``est_output_tokens_per_cell``
    via the real per-model pricing table. Models with no pricing entry are reported in
    ``missing_pricing`` (callers fail-closed on these for a benchmark — see BudgetGuard).
    """
    pricing = pricing or PricingService()
    coords_per_model = len(spec.services) * spec.repetitions  # per leverage state
    cells_per_model = coords_per_model * len(spec.leverage_states)
    # K2 asymmetry (R1-S5): on-cells run heavier than off-cells. Weight each model's cell budget
    # by off-count + on-count×multiplier so a tight ceiling can't pass preflight then abort mid-run.
    states = spec.leverage_states or ("off",)
    off_n = coords_per_model if "off" in states else 0
    on_n = coords_per_model if "on" in states else 0
    on_mult = getattr(spec, "est_on_cost_multiplier", 1.5)
    weighted_coords = off_n + on_n * on_mult  # == coords_per_model for the default off-only run
    per_model_usd: Dict[str, float] = {}
    cost_per_cell_usd: Dict[str, float] = {}
    missing: List[str] = []
    total = 0.0

    for agent_spec in spec.models:
        model = _model_id(agent_spec)
        if pricing.get_pricing(model) is None:
            missing.append(agent_spec)
            cost_per_cell_usd[agent_spec] = 0.0
            per_model_usd[agent_spec] = 0.0
            continue
        cell_cost = pricing.calculate_total_cost(
            model,
            input_tokens=spec.est_input_tokens_per_cell,
            output_tokens=spec.est_output_tokens_per_cell,
        )
        cost_per_cell_usd[agent_spec] = cell_cost
        model_total = cell_cost * weighted_coords
        per_model_usd[agent_spec] = model_total
        total += model_total

    return BenchmarkCostEstimate(
        total_usd=total,
        total_cells=spec.total_cells,
        per_model_usd=per_model_usd,
        cost_per_cell_usd=cost_per_cell_usd,
        missing_pricing=tuple(missing),
        cells_per_model=cells_per_model,
    )


def format_estimate(spec: BenchmarkRunSpec, estimate: BenchmarkCostEstimate) -> str:
    """Human-readable dry-run sizing table (FR-33)."""
    lines = [
        f"Benchmark cost estimate — run '{spec.name}'  (spec {spec.spec_hash()[:12]})",
        f"  matrix: {len(spec.services)} services x {len(spec.models)} models "
        f"x {spec.repetitions} reps"
        + (f" x {len(spec.leverage_states)} leverage ({','.join(spec.leverage_states)})"
           if len(spec.leverage_states) > 1 else "")
        + f" = {estimate.total_cells} cells",
        f"  sizing: ~{spec.est_input_tokens_per_cell} in / "
        f"{spec.est_output_tokens_per_cell} out tokens per cell (estimate, not billing)",
        "  budget ceiling: "
        + (f"${spec.budget_ceiling_usd:,.2f}" if spec.budget_ceiling_usd is not None else "(UNSET — run will refuse to start)"),
        "",
        f"  {'model':<32} {'$/cell':>9} {'cells':>6} {'est $':>10}",
        f"  {'-'*32} {'-'*9} {'-'*6} {'-'*10}",
    ]
    for agent_spec in spec.models:
        cc = estimate.cost_per_cell_usd.get(agent_spec, 0.0)
        mt = estimate.per_model_usd.get(agent_spec, 0.0)
        flag = "  ⚠ NO PRICING" if agent_spec in estimate.missing_pricing else ""
        lines.append(f"  {agent_spec:<32} {cc:>9.4f} {estimate.cells_per_model:>6} {mt:>10.2f}{flag}")
    lines.append(f"  {'-'*32} {'-'*9} {'-'*6} {'-'*10}")
    lines.append(f"  {'TOTAL':<32} {'':>9} {estimate.total_cells:>6} {estimate.total_usd:>10.2f}")
    if estimate.has_missing_pricing:
        lines.append("")
        lines.append(f"  ⚠ missing pricing for: {', '.join(estimate.missing_pricing)} "
                     f"(add to costs/pricing.py before running)")
    return "\n".join(lines)


class BudgetGuard:
    """Enforces the three budget controls during a run (FR-33).

    Usage:
        guard = BudgetGuard(spec)
        guard.preflight(estimate)            # raises BudgetError if unsafe to start
        ...
        for cell in spec.cells():
            if guard.would_exceed():         # cumulative abort
                break
            cost = run_cell(cell)
            verdict = guard.record(cell, cost)   # per-cell cap check + accumulate
    """

    def __init__(self, spec: BenchmarkRunSpec):
        self.spec = spec
        self.spent_usd: float = 0.0
        self.over_cap_cells: List[Tuple[str, float]] = []  # (cell-id, cost) over per-cell cap

    def preflight(self, estimate: BenchmarkCostEstimate) -> None:
        """Fail-closed pre-run checks. Raises BudgetError when unsafe to start."""
        if self.spec.budget_ceiling_usd is None:
            raise BudgetError(
                "fail-closed: no budget_ceiling_usd set — refusing to start a benchmark run "
                "(FR-33). Set a ceiling (--budget) or use --dry-run for sizing only."
            )
        if estimate.has_missing_pricing:
            raise BudgetError(
                "refusing to start: missing pricing for "
                f"{', '.join(estimate.missing_pricing)} — cost cannot be bounded. "
                "Add these to costs/pricing.py first."
            )
        if estimate.total_usd > self.spec.budget_ceiling_usd:
            raise BudgetError(
                f"pre-run estimate ${estimate.total_usd:,.2f} exceeds ceiling "
                f"${self.spec.budget_ceiling_usd:,.2f}. Lower N/roster/services or raise --budget."
            )

    def would_exceed(self, next_cost_usd: float = 0.0) -> bool:
        """True if spending ``next_cost_usd`` more would breach the ceiling (cumulative abort)."""
        if self.spec.budget_ceiling_usd is None:
            return True  # fail-closed
        return (self.spent_usd + next_cost_usd) > self.spec.budget_ceiling_usd

    def record(self, cell_id: str, actual_cost_usd: float) -> Dict[str, object]:
        """Accumulate an actual cell cost; flag per-cell cap breaches. Returns a verdict dict."""
        self.spent_usd += actual_cost_usd
        over_cap = (
            self.spec.per_cell_cap_usd is not None
            and actual_cost_usd > self.spec.per_cell_cap_usd
        )
        if over_cap:
            self.over_cap_cells.append((cell_id, actual_cost_usd))
        return {
            "cell_id": cell_id,
            "cost_usd": actual_cost_usd,
            "over_per_cell_cap": over_cap,
            "cumulative_usd": self.spent_usd,
            "budget_exhausted": self.would_exceed(),
        }
