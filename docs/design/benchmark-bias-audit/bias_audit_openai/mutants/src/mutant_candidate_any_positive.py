"""Mutant: candidate-any-positive — selects any positive candidate even when not lower."""

import reference_oracle as _base

CANDIDATE_REQUIRES_STRICTLY_LOWER = False

_base.CANDIDATE_REQUIRES_STRICTLY_LOWER = CANDIDATE_REQUIRES_STRICTLY_LOWER

assess_lines = _base.assess_lines
