"""Mutant: float-arithmetic — uses binary floating point for arithmetic."""

import reference_oracle as _base

USE_FLOAT_ARITHMETIC = True

_base.USE_FLOAT_ARITHMETIC = USE_FLOAT_ARITHMETIC

assess_lines = _base.assess_lines
