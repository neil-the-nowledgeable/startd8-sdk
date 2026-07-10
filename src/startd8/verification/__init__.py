# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""Shared verification core.

Both the observability-**fidelity** harness and the SDK **benchmark matrix** are the
same paradigm — *generate an artifact → establish ground truth → verify → emit a
degrade-honest verdict + coverage → render a scorecard*. Rather than let each grow its
own divergent verdict enum / coverage math / scorecard renderer (the three-generator-
divergence lesson), those primitives live here, consumed by both.

See ``ContextCore/docs/design/FIDELITY_BENCHMARK_CONVERGENCE.md`` §C.
"""

from .coverage import Coverage, compute_coverage
from .scorecard import Section, table, render_scorecard
from .verdict import BINDING, DATA_ONLY, EXCLUDED_SET, Verdict, is_binding

__all__ = [
    "Verdict",
    "BINDING",
    "DATA_ONLY",
    "EXCLUDED_SET",
    "is_binding",
    "Coverage",
    "compute_coverage",
    "Section",
    "table",
    "render_scorecard",
]
