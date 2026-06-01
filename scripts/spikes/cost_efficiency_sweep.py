#!/usr/bin/env python3
"""Live cost-efficiency sweep across cheap/mid/flagship tiers of the 3 live providers.

Sends ONE representative code-generation prompt to every agent, records latency +
token usage, derives per-model USD cost via the SDK PricingService, and prints a
report ranked by cost (cheapest first) plus a cost-per-1k-output efficiency column.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Optional

from startd8.providers import ProviderRegistry
from startd8.benchmark import BenchmarkRunner
from startd8.framework import AgentFramework

# 3 tiers x 3 live providers (Anthropic / OpenAI / Gemini).
TIERS = {
    "cheap": [
        "anthropic:claude-haiku-4-5-20251001",
        "openai:gpt-5.4-nano",
        "gemini:gemini-2.5-flash-lite",
    ],
    "mid": [
        "anthropic:claude-sonnet-4-6",
        "openai:gpt-5.4-mini",
        "gemini:gemini-2.5-flash",
    ],
    "flagship": [
        "anthropic:claude-opus-4-8",
        "openai:gpt-5.5",
        "gemini:gemini-2.5-pro",
    ],
}

# Representative moderate code-gen task (this SDK's core workload).
PROMPT = """Implement a Python class `TokenBucketRateLimiter` with these requirements:

1. Constructor takes `capacity: int` (max tokens) and `refill_rate: float` (tokens per second).
2. Method `allow(cost: int = 1) -> bool`: returns True and consumes `cost` tokens if
   enough are available, else returns False. Refill is time-based and lazy (compute on call).
3. Thread-safe using a lock.
4. Method `available() -> float` returning current token count.
5. Include type hints, a concise docstring on the class, and 3 pytest unit tests covering
   exhaustion, refill-over-time, and the cost parameter.

Return only the code in a single fenced block."""


@dataclass
class Row:
    spec: str
    tier: str
    in_tok: int
    out_tok: int
    cost: float
    time_ms: int
    ok: bool
    note: str = ""

    @property
    def cost_per_1k_out(self) -> float:
        return (self.cost / self.out_tok * 1000) if self.out_tok else 0.0


def resolve_agent(spec: str):
    provider_name, model = spec.split(":", 1)
    provider = ProviderRegistry.get_provider(provider_name)
    provider.validate_config({})
    return provider.create_agent(model)


def main() -> int:
    ProviderRegistry.discover()
    framework = AgentFramework()
    runner = BenchmarkRunner(framework)

    agents = []
    spec_to_tier = {}
    for tier, specs in TIERS.items():
        for spec in specs:
            spec_to_tier[spec] = tier
            try:
                agents.append((spec, resolve_agent(spec)))
            except Exception as e:  # noqa: BLE001
                print(f"  skip {spec}: {e}", file=sys.stderr)

    print(f"Running sweep across {len(agents)} agents...\n")

    results = runner.run_benchmark(
        prompt_content=PROMPT,
        agents=[a for _, a in agents],
        benchmark_name="cost-efficiency-sweep",
        version="1.0.0",
        tags=["cost-efficiency", "code-gen"],
    )

    # Map responses back to specs via model name.
    rows: list[Row] = []
    responses = {r["model"]: r for r in results["responses"]}
    for spec, agent in agents:
        model = spec.split(":", 1)[1]
        resp = responses.get(model) or responses.get(agent.model)
        tier = spec_to_tier[spec]
        if not resp:
            rows.append(Row(spec, tier, 0, 0, 0.0, 0, ok=False, note="no response (API error/unknown model)"))
            continue
        tu = resp.get("token_usage") or {}
        in_tok = tu.get("input", 0)
        out_tok = tu.get("output", 0)
        # Recompute cost via TokenUsage.cost_estimate for accuracy.
        from startd8.models import TokenUsage
        cost = TokenUsage(input=in_tok, output=out_tok, total=in_tok + out_tok, model_name=model).cost_estimate
        rows.append(Row(spec, tier, in_tok, out_tok, cost, resp.get("response_time_ms", 0), ok=True))

    ok_rows = [r for r in rows if r.ok]
    ok_rows.sort(key=lambda r: r.cost)
    failed = [r for r in rows if not r.ok]

    print("\n# Cost-Efficiency Sweep — ranked by total cost (cheapest first)\n")
    hdr = f"{'#':>2}  {'agent':40} {'tier':9} {'in':>6} {'out':>6} {'cost$':>10} {'$/1k out':>10} {'ms':>7}"
    print(hdr)
    print("-" * len(hdr))
    for i, r in enumerate(ok_rows, 1):
        print(f"{i:>2}  {r.spec:40} {r.tier:9} {r.in_tok:>6} {r.out_tok:>6} "
              f"{r.cost:>10.6f} {r.cost_per_1k_out:>10.6f} {r.time_ms:>7}")

    if failed:
        print("\n## Did not return (excluded from ranking)")
        for r in failed:
            print(f"  - {r.spec} ({r.tier}): {r.note}")

    if ok_rows:
        cheapest = ok_rows[0]
        best_eff = min(ok_rows, key=lambda r: r.cost_per_1k_out)
        fastest = min(ok_rows, key=lambda r: r.time_ms)
        print("\n## Verdict")
        print(f"  Cheapest total run : {cheapest.spec} (${cheapest.cost:.6f})")
        print(f"  Best $/1k output   : {best_eff.spec} (${best_eff.cost_per_1k_out:.6f}/1k)")
        print(f"  Fastest            : {fastest.spec} ({fastest.time_ms} ms)")
        print(f"\n  Benchmark ID: {results['benchmark']['id']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
