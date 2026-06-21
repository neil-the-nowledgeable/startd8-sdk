"""Mutant: sum-for-cascade — sums percentage levels when strategy is CASCADE."""

import reference_oracle as _base

FORCE_SUM_FOR_CASCADE = True

_base.FORCE_SUM_FOR_CASCADE = FORCE_SUM_FOR_CASCADE

assess_lines = _base.assess_lines
