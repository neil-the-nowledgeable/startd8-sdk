"""CKG Phase 2 — seeded explicit negatives (REQ-CKG-522, D2).

Positive path tables are not enough to beat the LLM's canonical-name prior: the
same wrong paths recur across runs (``@/lib/prisma`` — 3 recurrences across
RUN-008/009/011). So we render **explicit negatives** as a first-class section.

v1 is a *seeded* list covering the observed recurrences. Deriving negatives from
canonical-name priors is a future refinement (OQ-3). Each seed is gated to the
project: a negative is only injected when its ``correct`` replacement is a real,
resolvable module in the project (so we never assert a negative about a path the
project doesn't actually use).
"""

from __future__ import annotations

from typing import List, Sequence

from .models import Negative

__all__ = ["SEEDED_NEGATIVES", "relevant_negatives"]

# Observed recurring inventions → the real module. (RUN-008/009/011 postmortems.)
SEEDED_NEGATIVES: tuple[Negative, ...] = (
    Negative(invented="@/lib/prisma", correct="@/lib/db", note="the Prisma client"),
    Negative(invented="@/lib/db/", correct="@/lib/db", note="no per-model sub-paths"),
    Negative(invented="@/lib/ai/client", correct="@/lib/ai/service", note="the AI service"),
)


def relevant_negatives(
    canonical_modules: Sequence[str],
    *,
    seeds: Sequence[Negative] = SEEDED_NEGATIVES,
) -> List[Negative]:
    """Keep only seeds whose ``correct`` replacement is a real project module.

    ``canonical_modules`` is the set of canonical import specifiers the project
    actually exposes (e.g. ``@/lib/db``, ``@/lib/ai/service``). A seed survives
    when its replacement matches one of them by prefix — so a project without an
    AI service won't be told "use @/lib/ai/service". With no known modules we
    keep all seeds (the recurrences are well-attested; better to warn than miss).
    """
    if not canonical_modules:
        return list(seeds)
    mods = [m.rstrip("/") for m in canonical_modules]
    out: List[Negative] = []
    for neg in seeds:
        target = neg.correct.rstrip("/")
        if any(m == target or m.startswith(target + "/") or target.startswith(m) for m in mods):
            out.append(neg)
    return out
