"""Mutant: clamp-fixed-overrun — clamps remaining amount to zero instead of rejecting."""

import reference_oracle as _base

CLAMP_FIXED_OVERRUN = True

_base.CLAMP_FIXED_OVERRUN = CLAMP_FIXED_OVERRUN

assess_lines = _base.assess_lines
