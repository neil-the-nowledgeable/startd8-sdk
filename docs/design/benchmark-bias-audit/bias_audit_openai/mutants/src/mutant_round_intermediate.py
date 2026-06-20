"""Mutant: round-intermediate — quantizes after each arithmetic operation."""

import reference_oracle as _base

ROUND_INTERMEDIATE = True

_base.ROUND_INTERMEDIATE = ROUND_INTERMEDIATE

assess_lines = _base.assess_lines
