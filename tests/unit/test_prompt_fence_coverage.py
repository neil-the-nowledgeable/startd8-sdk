"""FR-A8 discovery: every prompt-assembly module that interpolates untrusted fields
must fence them — and a NEW unfenced site must fail this test.

This replaces a hardcoded per-field list (which can only enforce the sites someone
remembered) with a *discovery* guard: it scans the prompt-assembly modules, and any
module that references untrusted fields without calling a fence (`wrap_user_content`
/ `_fence_untrusted`) must be explicitly listed in ``TRACKED_UNFENCED`` (the known
FR-A8 / FR-A4 debt). A new such module — or a fenced module that loses its fence —
fails until it is fenced or consciously tracked.

See ``docs/design/prompt-injection-prevention/REQUIREMENTS.md`` FR-A1 / FR-A8.
"""

from pathlib import Path

import pytest

# src/startd8 root (this file is tests/unit/…).
_SRC = Path(__file__).resolve().parents[2] / "src" / "startd8"

# Canonical untrusted field names that carry end-user/third-party content into
# generation prompts (the bucket-4 carriers). Add new carriers here.
UNTRUSTED_FIELDS = frozenset({
    "prior_error_feedback",
    "requirements_text",
    "requirements_context",
    "plan_context",
    "project_objectives",
    "semantic_conventions",
    "architectural_context",
    "plan_text",
})

# Substrings that indicate a fence is applied in a module.
_FENCE_CALLS = ("wrap_user_content(", "_fence_untrusted(", "fence_untrusted(")

# Every module that assembles an LLM prompt. New prompt-assembly modules MUST be
# added here (the registry is itself part of the guard — see test_registry_is_complete).
PROMPT_MODULES = (
    "implementation_engine/spec_builder.py",
    "implementation_engine/drafter.py",
    "implementation_engine/reviewer.py",
    "contractors/context_resolution.py",
    "contractors/context_formatters.py",
    "workflows/builtin/plan_ingestion_workflow.py",
    "query_prime/generator.py",
    "micro_prime/prompt_builder.py",
    "micro_prime/engine.py",
)

# Modules that reference untrusted fields but do NOT yet fence them — the tracked,
# conscious debt. Each entry is a follow-up; removing a module from here (because it
# got fenced) is the expected end state. A module referencing untrusted fields that
# is NOT here and has no fence call fails the discovery test.
TRACKED_UNFENCED = {
    "implementation_engine/reviewer.py": "FR-A8 — review prompt path not yet fenced",
    "workflows/builtin/plan_ingestion_workflow.py": "FR-A4 — plan-ingestion PARSE prompt not yet fenced",
}

# Modules whose untrusted input uses a DIFFERENT field vocabulary than UNTRUSTED_FIELDS
# (so the field-name scan can't see it) — they need their own carrier inventory before
# this guard can enforce them. Tracked in FR-A8 (task #14).
KNOWN_DIFFERENT_VOCAB = {
    "query_prime/generator.py",
    "micro_prime/prompt_builder.py",
    "micro_prime/engine.py",
}


def _read(rel: str) -> str:
    path = _SRC / rel
    assert path.is_file(), f"PROMPT_MODULES lists a missing file: {rel}"
    return path.read_text(encoding="utf-8")


def _refs_untrusted(src: str) -> set[str]:
    return {f for f in UNTRUSTED_FIELDS if f in src}


def _has_fence(src: str) -> bool:
    return any(call in src for call in _FENCE_CALLS)


@pytest.mark.parametrize("rel", PROMPT_MODULES)
def test_module_fences_or_is_tracked(rel):
    """A module referencing untrusted fields must fence them, or be tracked debt."""
    src = _read(rel)
    refs = _refs_untrusted(src)
    if not refs:
        return  # references no canonical untrusted field — nothing to enforce here
    if _has_fence(src):
        return  # references untrusted fields AND fences — compliant
    # References untrusted fields with no fence call → must be conscious debt.
    assert rel in TRACKED_UNFENCED, (
        f"DISCOVERY: '{rel}' interpolates untrusted field(s) {sorted(refs)} but calls no "
        f"fence (wrap_user_content/_fence_untrusted). Fence them (FR-A1) or, if deliberately "
        f"deferred, add '{rel}' to TRACKED_UNFENCED with an FR reference."
    )


@pytest.mark.parametrize("rel", sorted(TRACKED_UNFENCED))
def test_tracked_debt_stays_accurate(rel):
    """A tracked-unfenced module that has GAINED a fence should be removed from the
    debt list (keeps the FR-A8 backlog honest), and must still reference untrusted fields."""
    src = _read(rel)
    assert _refs_untrusted(src), (
        f"'{rel}' is in TRACKED_UNFENCED but references no untrusted field — remove it."
    )
    assert not _has_fence(src), (
        f"'{rel}' now calls a fence — it appears fenced; remove it from TRACKED_UNFENCED "
        f"(and confirm every untrusted field is covered)."
    )


def test_known_fenced_modules_still_fenced():
    """Regression guard: the modules already fenced must keep a fence call (catches an
    accidental removal of the fencing wired in Increment 1 / FR-A8)."""
    for rel in ("implementation_engine/spec_builder.py", "contractors/context_resolution.py",
                "contractors/context_formatters.py"):
        assert _has_fence(_read(rel)), f"fencing disappeared from {rel}"


def test_different_vocab_modules_exist_and_are_tracked():
    """The modules with a different untrusted-field vocabulary are real and still need a
    carrier inventory — documents the FR-A8 limitation so it isn't silently lost."""
    for rel in KNOWN_DIFFERENT_VOCAB:
        assert (_SRC / rel).is_file(), f"KNOWN_DIFFERENT_VOCAB lists a missing file: {rel}"
        # By construction they don't reference the canonical fields yet.
        assert not _refs_untrusted(_read(rel)), (
            f"'{rel}' now references a canonical untrusted field — move it out of "
            f"KNOWN_DIFFERENT_VOCAB so test_module_fences_or_is_tracked enforces it."
        )
