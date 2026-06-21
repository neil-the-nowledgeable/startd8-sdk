"""Mutant: fixed-before-percent — applies fixed reductions before percentage reductions."""

import reference_oracle as _base

APPLY_FIXED_BEFORE_PERCENT = True

_base.APPLY_FIXED_BEFORE_PERCENT = APPLY_FIXED_BEFORE_PERCENT

assess_lines = _base.assess_lines
