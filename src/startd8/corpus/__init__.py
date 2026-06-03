"""Controlled Corpus — persistent, cross-run-accumulating controlled vocabulary.

A first-class store of domain terms (services, RPCs, entities, metrics, ...) →
per-language code-construct bindings → confidence → two-axis determinism, accumulated
across pipeline runs. Mirrors the ExemplarRegistry accumulation pattern applied to
*terms* instead of code exemplars.

See docs/design/controlled-corpus/CONTROLLED_CORPUS_REQUIREMENTS.md.
"""
from __future__ import annotations

from startd8.corpus.models import (
    Binding,
    CorpusTerm,
    Determinism,
    MAX_CORPUS_SIZE,
    SCHEMA_VERSION,
    TermObservation,
)
from startd8.corpus.registry import ControlledCorpusRegistry
from startd8.corpus.view import (
    as_project_knowledge,
    render_authorities_md,
    should_escalate,
    stable_authorities,
    triage_signal,
)

__all__ = [
    "Binding",
    "CorpusTerm",
    "Determinism",
    "TermObservation",
    "ControlledCorpusRegistry",
    "MAX_CORPUS_SIZE",
    "SCHEMA_VERSION",
    # read views (FR-9/10)
    "triage_signal",
    "should_escalate",
    "stable_authorities",
    "render_authorities_md",
    "as_project_knowledge",
]
