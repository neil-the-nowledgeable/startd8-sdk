# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""The shared verdict vocabulary.

One taxonomy across fidelity (does the generated PromQL bind?) and the benchmark (does
the generated code work?), so coverage math and scorecards read consistently. The
degrade-honest split is the load-bearing distinction (FR-32 / A1): a verdict either
counts toward coverage, is *excluded* from the denominator (not the artifact's fault —
inapplicable / infra / harness gap), or *fails* (the artifact is genuinely wrong).
"""

from __future__ import annotations

from enum import Enum


class Verdict(str, Enum):
    """A single artifact/query verification outcome."""

    PASS = "pass"                    # verified against ground truth
    BOUND_NO_DATA = "bound_no_data"  # binds/works, but no live data in-window (degrade-honest)
    PARTIAL = "partial"              # some sub-checks bind, some don't (static fidelity)
    FAIL = "fail"                    # genuinely does not bind / does not work
    ERROR = "error"                  # rejected / broken (a distinct kind of fail)
    EXCLUDED = "excluded"            # not applicable — NOT counted in the denominator
    UNKNOWN = "unknown"              # inconclusive (infra unreachable / nothing to judge)


#: Verdicts that count as "the artifact binds / works" for *binding* coverage.
BINDING = frozenset({Verdict.PASS, Verdict.BOUND_NO_DATA})
#: Verdicts that count as fully-verified-with-live-data (strict / *data* coverage).
DATA_ONLY = frozenset({Verdict.PASS})
#: Verdicts removed from the coverage denominator entirely (degrade-honest).
EXCLUDED_SET = frozenset({Verdict.EXCLUDED})


def is_binding(verdict: str) -> bool:
    """True if *verdict* counts toward binding coverage (accepts str or Verdict)."""
    return verdict in {v.value for v in BINDING}
