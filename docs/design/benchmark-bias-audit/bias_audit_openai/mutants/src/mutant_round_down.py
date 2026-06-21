"""Mutant: round-down-for-half-even — default rounding uses DOWN instead of HALF_EVEN."""

from decimal import ROUND_DOWN

import reference_oracle as _base

DEFAULT_ROUNDING_MODE = ROUND_DOWN

_base.DEFAULT_ROUNDING_MODE = DEFAULT_ROUNDING_MODE

assess_lines = _base.assess_lines
