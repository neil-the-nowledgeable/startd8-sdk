# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""Coverage math with degrade-honest exclusions.

`binding_coverage = bound / (total − excluded)` and `data_coverage = data / (total −
excluded)`. Excluded outcomes leave the denominator (they aren't the artifact's fault),
so a run's coverage reflects only *applicable* checks. One place, so fidelity and the
benchmark can't drift on how the denominator is formed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .verdict import BINDING, DATA_ONLY, EXCLUDED_SET, Verdict


@dataclass(frozen=True)
class Coverage:
    total: int             # every verdict considered
    excluded: int          # removed from the denominator (degrade-honest)
    denominator: int       # total − excluded
    bound: int             # count in BINDING
    data: int              # count in DATA_ONLY
    binding_coverage: float
    data_coverage: float


def _as_value(v) -> str:
    return v.value if isinstance(v, Verdict) else str(v)


def compute_coverage(verdicts: Iterable, *, extra_excluded: int = 0) -> Coverage:
    """Fold an iterable of verdicts (str or :class:`Verdict`) into a :class:`Coverage`.

    ``extra_excluded`` accounts for artifacts excluded *before* they became verdicts
    (e.g. template-var skips / kind-excluded queries that never entered the verdict
    list) — they enlarge neither the numerator nor the denominator, but are surfaced.
    """
    excluded_values = {v.value for v in EXCLUDED_SET}
    binding_values = {v.value for v in BINDING}
    data_values = {v.value for v in DATA_ONLY}

    total = 0
    excluded = extra_excluded
    bound = 0
    data = 0
    for raw in verdicts:
        v = _as_value(raw)
        total += 1
        if v in excluded_values:
            excluded += 1
            continue
        if v in binding_values:
            bound += 1
        if v in data_values:
            data += 1

    total += extra_excluded
    denominator = total - excluded
    binding_cov = bound / denominator if denominator else 0.0
    data_cov = data / denominator if denominator else 0.0
    return Coverage(
        total=total,
        excluded=excluded,
        denominator=denominator,
        bound=bound,
        data=data,
        binding_coverage=binding_cov,
        data_coverage=data_cov,
    )
