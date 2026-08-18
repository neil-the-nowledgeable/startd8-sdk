"""The passive census collector + the observe-only ``record_intervention`` hook.

FR-1: a passive hook at every LLM-call boundary and every repair-intervention emits a census
OBSERVATION tagged by **finding-class × language × element-kind**. This module owns:

* :class:`CensusObservation` — one immutable observation. Duck-types the SARIF sink's finding shape
  (``.check`` = the finding-class, ``.severity``, ``.message``, ``.file_path``, ``.line``), so it flows
  through ``coverage_map.findings_sarif.render_sarif_from_findings`` with NO per-producer adapter (NR-2).
* :class:`CensusCollector` — a lightweight append-only sink. NO global generation state; instrumentation
  reads an OPTIONAL process-scoped collector via :func:`get_collector`.
* :func:`record_intervention` — the observe-only hook the construction path calls. It is a **no-op when
  no collector is installed** (the default), so the census-off render path is byte-identical (FR-6 /
  NR-3): threading an observation never touches generation output and never raises into the caller.

The empty-default-is-the-guard: :func:`set_collector` is opt-in; until called, ``get_collector()`` is
``None`` and every hook returns immediately. There is NO feature flag to forget — absence *is* the off
switch.
"""

from __future__ import annotations

import os
import threading
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional

from startd8.logging_config import get_logger

from . import rule_catalog

logger = get_logger(__name__)

#: Config-level HARD kill-switch (benchmark opt-out). When this env var is truthy the census is forced
#: fully off — ``record_intervention`` no-ops and ``set_collector`` refuses to install — REGARDLESS of any
#: installed collector, so benchmark-related SDK behavior is guaranteed opt-in. ``run_prime_workflow.py
#: --benchmark-mode`` sets it (belt-and-suspenders atop the empty-default guard + per-cell subprocess
#: isolation), so a benchmark run can never be perturbed even if a future caller installs a global collector.
_ENV_DISABLE = "STARTD8_CENSUS_DISABLED"


def _hard_disabled() -> bool:
    """True when the census is force-disabled via the :data:`_ENV_DISABLE` env kill-switch (benchmark opt-out)."""
    return os.environ.get(_ENV_DISABLE, "").strip().lower() not in ("", "0", "false", "no")


class FindingClass(str, Enum):
    """The census finding-classes (mirrors :data:`census.rule_catalog.RULE_CATALOG` keys — the enumerable
    vocabulary). ``.value`` is the bare on-the-wire rule-id the SARIF sink reads off ``.check``."""

    # llm-intervention
    ELEMENT_RENDER = "element_render"
    BODY_FILL = "body_fill"
    SIGNATURE_RENDER = "signature_render"
    # repair-intervention
    REPAIR_SYNTAX = "repair_syntax"
    REPAIR_IMPORT = "repair_import"
    REPAIR_CONTRACT = "repair_contract"
    REPAIR_LINT = "repair_lint"
    REPAIR_OTHER = "repair_other"


@dataclass(frozen=True)
class CensusObservation:
    """One census observation — an LLM-call or repair-intervention, tagged by finding-class × language ×
    element-kind. Duck-types the SARIF finding shape (``.check`` / ``.severity`` / ``.message`` /
    ``.file_path`` / ``.line``) so ``render_sarif_from_findings`` consumes it directly."""

    finding_class: str          # a FindingClass value (the bare rule-id)
    language: str               # a LanguageProfile id: python | go | nodejs | java | csharp
    element_kind: str           # a code_manifest.ElementKind value (class | function | method | struct …)
    file_path: str = ""         # where the intervention landed (SARIF artifactLocation.uri)
    line: Optional[int] = None
    message: str = ""

    # --- SARIF finding duck-type (consumed by render_sarif_from_findings; no adapter) ---
    @property
    def check(self) -> str:
        """The rule-id the SARIF sink reads (``.check``) — the finding-class."""
        return self.finding_class

    @property
    def severity(self) -> str:
        """The default severity from the shared catalog (``info`` for every census class)."""
        try:
            return rule_catalog.rule_severity(self.finding_class)
        except KeyError:
            return "info"

    @property
    def domain(self) -> str:
        try:
            return rule_catalog.rule_domain(self.finding_class)
        except KeyError:
            return ""

    def sarif_message(self) -> str:
        """A stable message even when none was supplied — carries the tags so the finding self-describes."""
        if self.message:
            return self.message
        return f"{self.finding_class} · {self.language} · {self.element_kind}"

    # render_sarif_from_findings reads `.message` (attr) before `.file_path`; expose the derived text.
    @property
    def message_text(self) -> str:  # pragma: no cover - convenience alias
        return self.sarif_message()


class CensusCollector:
    """A thread-safe append-only sink for :class:`CensusObservation`. Deliberately dumb — it holds
    observations; the aggregator (:mod:`census.report`) does all the joining/ranking. Passive: recording
    an observation cannot alter generation because the collector is never read by the construction path."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._observations: List[CensusObservation] = []

    def record(self, obs: CensusObservation) -> None:
        with self._lock:
            self._observations.append(obs)

    @property
    def observations(self) -> List[CensusObservation]:
        with self._lock:
            return list(self._observations)

    def __len__(self) -> int:
        with self._lock:
            return len(self._observations)


# The OPTIONAL process-scoped collector. Absent by default — the census-off guard (FR-6).
_collector: Optional[CensusCollector] = None
_collector_lock = threading.Lock()


def set_collector(collector: Optional[CensusCollector]) -> None:
    """Install (or clear, with ``None``) the process-scoped census collector. Opt-in: until this is
    called the hook is a no-op and every generated artifact is byte-identical."""
    global _collector
    if _hard_disabled() and collector is not None:
        logger.debug("census hard-disabled (%s) — refusing to install a collector", _ENV_DISABLE)
        return
    with _collector_lock:
        _collector = collector


def get_collector() -> Optional[CensusCollector]:
    """The installed collector, or ``None`` (the default — census off)."""
    with _collector_lock:
        return _collector


def record_intervention(
    finding_class: "str | FindingClass",
    language: str,
    element_kind: str,
    *,
    file_path: str = "",
    line: Optional[int] = None,
    message: str = "",
    collector: Optional[CensusCollector] = None,
) -> None:
    """OBSERVE-ONLY hook — record one LLM-call / repair-intervention as a census observation.

    A **no-op when no collector is installed** (the default), so the census-off render path is
    byte-identical: this hook never changes generation output and never raises into its caller (any
    error is swallowed and logged at debug — the census must never perturb what it measures). Pass an
    explicit *collector* to record into a specific sink (tests, per-run scoping); else the process-scoped
    one is used.
    """
    if _hard_disabled():
        return  # census force-disabled (benchmark opt-out) — byte-identical regardless of any collector
    sink = collector if collector is not None else get_collector()
    if sink is None:
        return  # census off — the empty-default guard; byte-identical
    try:
        fc = finding_class.value if isinstance(finding_class, FindingClass) else str(finding_class)
        lang = str(language or "unknown")
        ekind = str(element_kind or "unknown")
        # Populate a self-describing message so the SARIF sink (which reads the `.message` field) always
        # carries the finding-class × language × element-kind tags, even when the caller supplied none.
        text = str(message) if message else f"{fc} · {lang} · {ekind}"
        sink.record(
            CensusObservation(
                finding_class=fc,
                language=lang,
                element_kind=ekind,
                file_path=str(file_path or ""),
                line=line,
                message=text,
            )
        )
    except Exception:  # noqa: BLE001 — the hook must never break generation
        logger.debug("census record_intervention swallowed an error", exc_info=True)
