"""The census aggregator + report (FR-5) — where the LLM is load-bearing per language.

Groups census observations by **finding-class × language**, ranks by **frequency × language-spread**,
and frames each top row as a metabolization-ratchet candidate (a recurring finding-class → a candidate
deterministic render-template). This is the code-side twin of ``dev-os/CRP-INDEX.md``'s recurring-themes
table. Embeds the FR-3 per-language determinism-% scoreboard. An empty census yields an honest empty
report (no rows, no scoreboard measurements — every known lane ``absent``).

FR-1/NR-2: the SARIF view of the census reuses the universal ``coverage_map.findings_sarif`` sink —
:func:`render_sarif` is a thin passthrough (census observations duck-type the finding shape; the
producer is ``startd8-census``; help URIs come from the shared catalog). No new emitter.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Tuple

from startd8.coverage_map.findings_sarif import render_sarif_from_findings

from . import rule_catalog
from .hook import CensusObservation
from .scoreboard import LaneScore, build_scoreboard

#: finding-class → the candidate deterministic render-template it points at (the ratchet's next move).
#: A recurring class here is the evidence that building this template shrinks the gap measurably.
_TEMPLATE_CANDIDATE = {
    "element_render": "a per-language element renderer (struct/class/function scaffold)",
    "body_fill": "a per-language body template for the recurring element shape",
    "signature_render": "a per-language signature renderer from the contract",
    "repair_syntax": "a deterministic syntax-normalizer for this language",
    "repair_import": "a deterministic import-resolver for this language",
    "repair_contract": "a deterministic contract-conformance patcher",
    "repair_lint": "a deterministic lint-fixer step",
    "repair_other": "(triage the unclassified repairs before templating)",
}


@dataclass(frozen=True)
class LanguageLoad:
    """One ranked row: a finding-class × language load, with its ratchet candidate."""

    finding_class: str
    language: str
    domain: str
    frequency: int                 # how many times this class fired in this language
    template_candidate: str        # the deterministic render-template it points at

    @property
    def qualified_id(self) -> str:
        return rule_catalog.qualified_id(self.finding_class)


@dataclass(frozen=True)
class CensusReport:
    """The aggregated census: the ranked load rows + the per-language scoreboard + honest totals."""

    rows: List[LanguageLoad]
    scoreboard: List[LaneScore]
    total_observations: int
    finding_class_spread: Dict[str, int] = field(default_factory=dict)  # class → # of languages it spans

    @property
    def is_empty(self) -> bool:
        return self.total_observations == 0

    def top(self, n: int = 10) -> List[LanguageLoad]:
        return self.rows[:n]


def build_report(
    observations: Iterable[CensusObservation],
    *,
    languages: Iterable[str] | None = None,
) -> CensusReport:
    """Aggregate observations into the ranked census report (FR-5).

    Rows are grouped by (finding-class, language) and ranked by **frequency × language-spread** — a
    class that recurs across many languages outranks an equally frequent single-language one (spread is
    the signal that a deterministic template pays off broadly). An empty census → an empty report with
    every known lane ``absent`` (honest, not a false zero).
    """
    obs_list = list(observations)

    # frequency per (class, language) and the per-class language spread (# distinct languages).
    freq: Dict[Tuple[str, str], int] = defaultdict(int)
    class_langs: Dict[str, set] = defaultdict(set)
    for o in obs_list:
        freq[(o.finding_class, o.language)] += 1
        class_langs[o.finding_class].add(o.language)

    spread = {cls: len(langs) for cls, langs in class_langs.items()}

    rows: List[LanguageLoad] = []
    for (cls, lang), n in freq.items():
        try:
            domain = rule_catalog.rule_domain(cls)
        except KeyError:
            domain = ""
        rows.append(
            LanguageLoad(
                finding_class=cls,
                language=lang,
                domain=domain,
                frequency=n,
                template_candidate=_TEMPLATE_CANDIDATE.get(cls, "(no candidate mapped)"),
            )
        )

    # Rank: frequency × spread desc, then frequency desc, then a stable (class, language) tiebreak.
    rows.sort(
        key=lambda r: (-(r.frequency * spread.get(r.finding_class, 1)), -r.frequency, r.finding_class, r.language)
    )

    sb_langs = languages if languages is not None else None
    scoreboard = (
        build_scoreboard(obs_list, languages=sb_langs)
        if sb_langs is not None
        else build_scoreboard(obs_list)
    )

    return CensusReport(
        rows=rows,
        scoreboard=scoreboard,
        total_observations=len(obs_list),
        finding_class_spread=spread,
    )


def render_sarif(
    observations: Iterable[CensusObservation],
    *,
    tool_version: str = "0.1",
    corpus: str | None = None,
) -> Dict[str, Any]:
    """Render the census observations as SARIF 2.1.0 through the universal sink (FR-1 / NR-2).

    A thin passthrough: census observations duck-type the finding shape (``.check`` / ``.severity`` /
    ``.message`` / ``.file_path``), so no per-producer adapter is needed. Observations with no
    ``file_path`` cannot be located in SARIF and are honestly counted as ``skipped`` by the sink.
    """
    return render_sarif_from_findings(
        observations,
        tool_name=rule_catalog.PRODUCER,
        tool_version=tool_version,
        rule_help_uris=rule_catalog.help_uri_map(),
        corpus=corpus,
    )
