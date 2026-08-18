"""Per-language determinism-% scoreboard, derived from the realization seam (FR-3 / FR-4).

The headline number reuses ``navigator/realization.py``'s ``determinism_pct`` over a regime distribution
built from the census's per-file regime observations — NOT a new % calculator (NR-6). We turn each
observed file into a :class:`Node` carrying a declared-regime ``DerivationEdge`` (``llm`` for a file the
LLM touched, ``deterministic`` for one only rendered deterministically), feed a language's nodes to
``corpus_realization``, and read ``determinism_pct`` on the resulting distribution.

FR-4 (absence-vs-error, Harbor Honesty-Verdict): a language with ZERO census observations was never
instrumented — it renders :data:`ABSENT`, never a false ``100% deterministic`` / ``0% llm``. A language
that WAS observed and happened to be all-deterministic renders a *measured* 100%. The two are distinct
rows; an absent lane is never scored as a real determinism number.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional

from startd8.navigator.models import (
    DerivationEdge,
    Node,
    NodeEvidence,
    RealizationRegime,
)
from startd8.navigator.realization import corpus_realization, determinism_pct

from .hook import CensusObservation

#: The 5 LanguageProfile ids the polyglot path supports. A lane in this set with no observations reads
#: ABSENT (FR-4 / NR-5 — Java is in the set but absent from the Round-3 fleet until a Java corpus runs).
KNOWN_LANGUAGES = ("python", "go", "nodejs", "java", "csharp")

#: The absence sentinel — an un-instrumented lane (never a real 0% / 100%).
ABSENT = "absent"


@dataclass(frozen=True)
class LaneScore:
    """One language row of the scoreboard. ``determinism_pct`` is ``None`` iff the lane is ``absent``."""

    language: str
    observed: bool                     # False → the lane was never instrumented (absent)
    determinism_pct: Optional[float]   # deterministic / total, or None when absent
    llm_files: int = 0                 # files the LLM touched (regime=llm)
    deterministic_files: int = 0       # files only rendered deterministically
    interventions: int = 0             # total census observations in this lane

    @property
    def status(self) -> str:
        return ABSENT if not self.observed else "measured"

    def format_pct(self) -> str:
        """Speakable cell: ``absent`` for an un-instrumented lane, else ``NN% deterministic``."""
        if not self.observed or self.determinism_pct is None:
            return ABSENT
        return f"{round(self.determinism_pct * 100)}% deterministic"


def _files_by_language(
    observations: Iterable[CensusObservation],
) -> Dict[str, Dict[str, bool]]:
    """Collapse observations to per-language {file → llm_touched}. A file with ANY llm-intervention
    observation is ``llm``; a file seen only via deterministic-regime observations is ``deterministic``.
    (In this census every observation is an intervention on the LLM path, so an observed file is ``llm``;
    the ``deterministic`` branch is exercised when a caller records a deterministic-regime observation.)"""
    llm_touched: Dict[str, Dict[str, bool]] = defaultdict(dict)
    for obs in observations:
        lang = obs.language or "unknown"
        # Key files by (finding-class domain). A repair or render intervention means the LLM path ran on
        # that file → llm regime. Use file_path when present, else a synthetic per-observation key so two
        # distinct interventions on unnamed files still count as LLM work (never collapse to one file).
        fkey = obs.file_path or f"<{lang}:{len(llm_touched[lang])}>"
        # Any intervention marks the file llm (True). A file already marked stays llm.
        llm_touched[lang][fkey] = True
    return llm_touched


def _nodes_for_files(files: Dict[str, bool]) -> List[Node]:
    """One :class:`Node` per file, carrying a declared-regime ``DerivationEdge`` so the realization seam
    derives its regime exactly as it does for a real corpus (no bespoke % arithmetic — NR-6)."""
    nodes: List[Node] = []
    for fkey, llm in sorted(files.items()):
        regime = RealizationRegime.LLM if llm else RealizationRegime.DETERMINISTIC
        nodes.append(
            Node(
                key=fkey,
                does=f"census file {fkey}",
                lives=(NodeEvidence(type="code", ref=fkey),),
                derivation=(DerivationEdge(from_key="census:corpus", regime=regime),),
            )
        )
    return nodes


def build_scoreboard(
    observations: Iterable[CensusObservation],
    *,
    languages: Iterable[str] = KNOWN_LANGUAGES,
) -> List[LaneScore]:
    """The per-language determinism-% scoreboard (FR-3/FR-4).

    Every language in *languages* gets a row. A lane with observations derives its determinism-% from
    the realization seam (``corpus_realization`` → ``determinism_pct``); a lane with none renders
    ``absent`` (``observed=False``, ``determinism_pct=None``) — never a false measured number.
    """
    obs_list = list(observations)
    per_lang_files = _files_by_language(obs_list)
    counts: Dict[str, int] = defaultdict(int)
    for o in obs_list:
        counts[o.language or "unknown"] += 1

    # Include any observed language not in the known set (honest — don't silently drop unknown lanes).
    lane_ids = list(dict.fromkeys(list(languages) + sorted(per_lang_files)))

    scoreboard: List[LaneScore] = []
    for lang in lane_ids:
        files = per_lang_files.get(lang)
        if not files:
            scoreboard.append(
                LaneScore(language=lang, observed=False, determinism_pct=None)
            )
            continue
        nodes = _nodes_for_files(files)
        dist, _grounded = corpus_realization(nodes)  # the realization seam owns the distribution
        pct = determinism_pct(dist)                  # …and the % — reused, not re-derived
        scoreboard.append(
            LaneScore(
                language=lang,
                observed=True,
                determinism_pct=pct,
                llm_files=dist.get(RealizationRegime.LLM, 0),
                deterministic_files=dist.get(RealizationRegime.DETERMINISTIC, 0),
                interventions=counts.get(lang, 0),
            )
        )
    return scoreboard
