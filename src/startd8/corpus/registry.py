"""ControlledCorpusRegistry — persistent, cross-run-accumulating term store.

Mirrors ExemplarRegistry's persistence/lifecycle (FR-1) but dedups by the SEMANTIC key
(kind, canonical_key) rather than an opaque id, and accumulates via an idempotent,
order-independent merge (FR-4). Load → merge_run(...) per run → save; intended to run
at the postmortem alongside exemplar extraction.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from startd8.corpus.models import (
    Binding,
    CorpusTerm,
    Determinism,
    MAX_CORPUS_SIZE,
    SCHEMA_VERSION,
    SOURCE_PRECEDENCE,
    CONFIDENCE_PRECEDENCE,
    TermObservation,
    term_id_for,
)
from startd8.logging_config import get_logger

logger = get_logger(__name__)

__all__ = ["ControlledCorpusRegistry"]


class ControlledCorpusRegistry:
    """Searchable, accumulating registry of controlled-vocabulary terms.

    Not thread-safe (single-threaded postmortem flow, like ExemplarRegistry).
    """

    def __init__(self, project_id: str = "") -> None:
        self.schema_version: str = SCHEMA_VERSION  # serialization FORMAT contract
        self.project_id: str = project_id
        self.last_updated: str = ""
        self.corpus_version: int = 0  # R4-F3: monotonic content counter (provenance)
        self._terms: Dict[str, CorpusTerm] = {}  # term_id -> term

    # ------------------------------------------------------------------
    # Merge (idempotent + order-independent — FR-4)
    # ------------------------------------------------------------------
    def merge_run(self, run_id: str, observations: List[TermObservation]) -> None:
        """Merge one run's term observations. Re-merging the same run is a no-op."""
        for obs in observations:
            tid = term_id_for(obs.kind, obs.canonical_key)
            term = self._terms.get(tid)
            if term is None:
                term = CorpusTerm(term_id=tid, kind=obs.kind, canonical_key=obs.canonical_key)
                self._terms[tid] = term

            # set-valued accumulators -> order-independent + idempotent
            if obs.surface_form and obs.surface_form not in term.surface_forms:
                term.surface_forms.append(obs.surface_form)
            if run_id not in term.source_run_ids:
                term.source_run_ids.append(run_id)

            # confidence upgrade by precedence (max — order-independent)
            if CONFIDENCE_PRECEDENCE.get(obs.confidence, 0) > CONFIDENCE_PRECEDENCE.get(term.confidence, 0):
                term.confidence = obs.confidence

            # binding upgrade by SOURCE_PRECEDENCE per (language, construct_kind, construct_ref)
            self._merge_bindings(term, obs.bindings)

            # determinism observation keyed by run_id (overwrite -> idempotent)
            if obs.success is not None or obs.requirement_score is not None:
                term.determinism.observe(run_id, bool(obs.success), obs.requirement_score,
                                         obs.input_scope_id)

            term.recompute_maturity()

        self._evict_if_needed()
        self.corpus_version += 1  # R4-F3: bump on each merge
        self.last_updated = datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _merge_bindings(term: CorpusTerm, incoming: List[Binding]) -> None:
        by_key: Dict[tuple, Binding] = {b.key(): b for b in term.bindings}
        for b in incoming:
            existing = by_key.get(b.key())
            if existing is None:
                by_key[b.key()] = b
            else:
                # keep the higher-precedence source; ties -> deterministic (keep existing)
                if SOURCE_PRECEDENCE.get(b.source_reference, 0) > SOURCE_PRECEDENCE.get(existing.source_reference, 0):
                    by_key[b.key()] = b
        # store sorted for byte-stable serialization (order-independence)
        term.bindings = [by_key[k] for k in sorted(by_key)]

    # ------------------------------------------------------------------
    # Queries (FR-9/10 read interfaces)
    # ------------------------------------------------------------------
    @property
    def terms(self) -> List[CorpusTerm]:
        return [self._terms[k] for k in sorted(self._terms)]

    def __len__(self) -> int:
        return len(self._terms)

    def by_class(self, corpus_class: str) -> List[CorpusTerm]:
        return [t for t in self.terms if t.determinism.corpus_class == corpus_class]

    def find_by_canonical_key(self, kind: str, canonical_key: str) -> Optional[CorpusTerm]:
        return self._terms.get(term_id_for(kind, canonical_key))

    def stability_for(self, target_file: str) -> Optional[float]:
        """SCR-triage primitive (FR-10): structural stability for a target_file binding."""
        term = self.find_by_canonical_key("file", target_file)
        return term.determinism.success_stability if term else None

    # ------------------------------------------------------------------
    # Persistence (FR-1) — mirrors ExemplarRegistry
    # ------------------------------------------------------------------
    def save(self, path: str | Path) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "schema_version": self.schema_version,
            "corpus_version": self.corpus_version,
            "project_id": self.project_id,
            "last_updated": self.last_updated,
            "terms": [t.to_dict() for t in self.terms],  # sorted by term_id
        }
        tmp = p.with_suffix(p.suffix + ".tmp")
        tmp.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
        tmp.replace(p)  # atomic
        logger.info("Controlled corpus saved: %s (%d terms)", p, len(self._terms))

    @classmethod
    def load(cls, path: str | Path) -> "ControlledCorpusRegistry":
        p = Path(path)
        if not p.is_file():
            logger.debug("No controlled corpus at %s, returning empty", p)
            return cls()
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            # R1-F3: schema migration contract. A MAJOR-version mismatch means the
            # on-disk shape may be incompatible — refuse to merge into it (return empty,
            # warn) rather than silently corrupting. Minor/patch differences load as-is.
            disk_ver = str(data.get("schema_version", SCHEMA_VERSION))
            if disk_ver.split(".")[0] != SCHEMA_VERSION.split(".")[0]:
                logger.warning(
                    "Controlled corpus at %s has incompatible major schema %s (code %s); "
                    "starting empty (no migration path defined)", p, disk_ver, SCHEMA_VERSION)
                return cls()
            reg = cls(project_id=data.get("project_id", ""))
            reg.schema_version = data.get("schema_version", SCHEMA_VERSION)
            reg.corpus_version = int(data.get("corpus_version", 0))
            reg.last_updated = data.get("last_updated", "")
            for td in data.get("terms", []):
                try:
                    t = CorpusTerm.from_dict(td)
                    reg._terms[t.term_id] = t
                except (TypeError, KeyError, ValueError) as exc:
                    logger.warning("Skipping malformed corpus term: %s", exc)
            return reg
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Failed to load controlled corpus from %s: %s", p, exc)
            return cls()

    # ------------------------------------------------------------------
    def _evict_if_needed(self) -> None:
        """Evict lowest-maturity, fewest-runs terms over the ceiling.

        R3-F1: NEVER evict a `false_pass_risk` term — the FR-8 "never promote" guarantee
        requires persistent negative evidence. If a re-encountered file lost its history
        it could re-accumulate PASS-only observations and become a false candidate. If
        ALL terms are false_pass_risk the corpus grows past the ceiling (extreme, logged).
        """
        while len(self._terms) > MAX_CORPUS_SIZE:
            candidates = [t for t in self._terms.values()
                          if t.determinism.corpus_class != "false_pass_risk"]
            if not candidates:
                logger.warning("Corpus over ceiling but all terms are false_pass_risk; "
                               "not evicting (FR-8 negative-evidence guarantee)")
                return
            victim = min(candidates, key=lambda t: (t.maturity, len(t.source_run_ids), t.term_id))
            del self._terms[victim.term_id]
            logger.info("Evicted corpus term %s (maturity=%d)", victim.term_id, victim.maturity)
