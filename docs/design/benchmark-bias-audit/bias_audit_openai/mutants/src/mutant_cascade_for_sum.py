"""Mutant: cascade-for-sum — cascades percentage levels when strategy is SUM."""

import reference_oracle as _base

FORCE_CASCADE_FOR_SUM = True

_base.FORCE_CASCADE_FOR_SUM = FORCE_CASCADE_FOR_SUM

assess_lines = _base.assess_lines
