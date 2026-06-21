"""Mutant: price-on-request-total — includes price-on-request quantity in numeric totals."""

import reference_oracle as _base

INCLUDE_POR_IN_TOTALS = True

_base.INCLUDE_POR_IN_TOTALS = INCLUDE_POR_IN_TOTALS

assess_lines = _base.assess_lines
