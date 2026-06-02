#!/usr/bin/env python3
"""REQ-CKG-530 adherence harness — CLI (SCAFFOLD).

Measures whether the Phase-2 Knowledge Provider's injection actually moves the
*generated code* off the RUN-011 inventions (D1: injection ≠ adherence). Runs each
failure-class case over N≥5 seeds, with and without injection, and reports the
per-Gap adherence rate against the threshold.

The generation backend is pluggable:
  --backend mock      deterministic demo (no API cost); shows the harness mechanics
  --backend startd8   real generation via the SDK (REQUIRES an API key + budget)

The ``startd8`` backend is the run-later boundary: this scaffold wires the call
site but real runs cost tokens, so they are opt-in. Example:

    python scripts/ckg_adherence_harness.py --backend mock
    python scripts/ckg_adherence_harness.py --backend startd8 \\
        --agent anthropic:claude-sonnet-4-20250514 --seeds 5 --threshold 0.9
"""

from __future__ import annotations

import argparse
import sys

from startd8.contractors.project_knowledge.adherence import (
    DEFAULT_SEEDS,
    DEFAULT_THRESHOLD,
    RUN011_CASES,
    MockBackend,
    SuiteReport,
    run_suite,
)


def _mock_backend() -> MockBackend:
    """A demo backend: 'naive' on baseline-style prompts, 'obedient' when injected.

    It keys off whether the prompt contains the provider's authority section, to
    illustrate the expected lift. This is for mechanics only — real measurement
    needs a real model (``--backend startd8``).
    """

    class _DemoBackend:
        def generate(self, *, prompt: str, seed: int) -> str:
            injected = "## Prisma data model" in prompt or "Do NOT use these" in prompt
            if injected:
                # obedient: real fields/paths
                return "import { db } from '@/lib/db'\nconst x = { id, name, summary, score }"
            # naive: reproduces the RUN-011 inventions on most seeds
            if seed % 5 == 0:
                return "import { db } from '@/lib/db'\nconst x = { id, name }"
            return "import { prisma } from '@/lib/prisma'\nconst x = { aiRefId, bio, label }"

    return _DemoBackend()  # type: ignore[return-value]


def _startd8_backend(agent_spec: str):
    """Real generation backend (run-later boundary). Requires an API key + budget."""
    try:
        from startd8.providers import ProviderRegistry
        from startd8.utils.agent_resolution import resolve_agent_spec
    except Exception as exc:  # pragma: no cover - import guard
        raise SystemExit(f"startd8 backend unavailable: {exc}")

    ProviderRegistry.discover()
    agent = resolve_agent_spec(agent_spec)

    class _StartD8Backend:
        def generate(self, *, prompt: str, seed: int) -> str:
            # NOTE: wire seed → temperature/sampling per provider when running for real.
            result = agent.generate(prompt)
            return getattr(result, "text", str(result))

    return _StartD8Backend()


def _print_report(report: SuiteReport, *, inject: bool, label: str) -> None:
    print(f"\n=== {label} (inject={inject}, threshold={report.threshold:.2f}) ===")
    for r in report.results:
        print(f"  {r.case_id:8} GapA/B={r.gap}  adherent {r.adherent}/{r.n}  rate {r.rate:.2f}")
    for gap, rate in report.rate_by_gap().items():
        mark = "PASS" if rate >= report.threshold else "BELOW"
        print(f"  -> Gap {gap}: {rate:.2f}  [{mark}]")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="CKG REQ-530 adherence harness (scaffold)")
    ap.add_argument("--backend", choices=("mock", "startd8"), default="mock")
    ap.add_argument("--agent", default="anthropic:claude-sonnet-4-20250514")
    ap.add_argument("--seeds", type=int, default=DEFAULT_SEEDS)
    ap.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD)
    ap.add_argument(
        "--scoring", choices=("denylist", "structural"), default="structural",
        help="denylist = literal-token check (mechanics); structural = Phase-1 "
             "detectors (uses-only-real-fields/paths, catches novel inventions)",
    )
    args = ap.parse_args(argv)

    backend = _mock_backend() if args.backend == "mock" else _startd8_backend(args.agent)

    # The real gate: baseline (no injection) vs injected, same seeds, per-Gap rate.
    baseline = run_suite(
        RUN011_CASES, backend, inject=False, n_seeds=args.seeds,
        threshold=args.threshold, scoring=args.scoring,
    )
    injected = run_suite(
        RUN011_CASES, backend, inject=True, n_seeds=args.seeds,
        threshold=args.threshold, scoring=args.scoring,
    )
    print(f"(scoring={args.scoring}, agent={args.agent})")
    _print_report(baseline, inject=False, label="BASELINE")
    _print_report(injected, inject=True, label="INJECTED")

    print("\nNote: 'mock' shows mechanics only. Real adherence needs --backend startd8 "
          "(API key + token budget). Below-threshold Gaps → escalate to contract-first (Approach C).")
    # Exit non-zero only if injection failed to reach threshold (the actionable signal).
    return 0 if injected.passes() else 1


if __name__ == "__main__":
    sys.exit(main())
