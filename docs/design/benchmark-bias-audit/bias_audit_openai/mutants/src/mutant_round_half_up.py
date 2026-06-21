"""Mutant: round-half-up-for-half-even — default rounding uses HALF_UP instead of HALF_EVEN."""

from decimal import ROUND_HALF_UP

import reference_oracle as _base

DEFAULT_ROUNDING_MODE = ROUND_HALF_UP

_base.DEFAULT_ROUNDING_MODE = DEFAULT_ROUNDING_MODE

assess_lines = _base.assess_lines
