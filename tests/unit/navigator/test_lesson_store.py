"""Retrospective loop seams (harvest-backlog closure over REQ-20 / REQ-24):

- **REQ-20 H3** — Lessons persist across runs, and a re-derive PRESERVES the human's disposition
  (an accepted/rejected Lesson never silently resets to `proposed`).
- **REQ-20 H2** — a Lesson is disposed only through an explicit call (accept/reject), which persists.
- **REQ-24 H1** — an honest Lesson→ReviseEdit producer: a description-clarification Lesson carries a
  concrete edit; a determinism-regression Lesson does NOT (its fix is a plan re-examination) → `None`.
"""

from __future__ import annotations

from startd8.navigator.govern import Finding
from startd8.navigator.lesson_store import (
    find_lesson,
    load_lessons,
    merge_lessons,
    save_lessons,
    upsert_lesson,
)
from startd8.navigator.revise_tier import ReviseEdit, revise_edit_from_lesson
from startd8.navigator.sources_retrospective import (
    LessonStatus,
    accept_lesson,
    build_lesson_from_description_clarification,
    build_lesson_from_regression,
    is_grounded,
    lesson_status,
    reject_lesson,
    revises_edges,
)


def _regression(fr="FR-1"):
    return Finding("FR-6", "fail", "REQ-x.md",
                   f"node {fr!r} PLANNED deterministic but MEASURED llm — a determinism regression.", fr=fr)


def _clarification(req="FR-2"):
    return build_lesson_from_description_clarification(
        req, path="schema.prisma", before="// old", after="// clarified", confidence=0.95)


# ── REQ-24 H1 — the honest Lesson→ReviseEdit producer ───────────────────────────────────────────────

def test_description_clarification_lesson_yields_a_concrete_edit():
    lesson = _clarification("FR-2")
    edit = revise_edit_from_lesson(lesson)
    assert isinstance(edit, ReviseEdit)
    assert edit.target == "FR-2"
    assert edit.path == "schema.prisma"
    assert (edit.before, edit.after) == ("// old", "// clarified")


def test_regression_lesson_yields_no_edit_none_is_invented():
    # a determinism-regression Lesson proposes a plan re-examination, not a mechanical text edit
    lesson = build_lesson_from_regression(_regression("FR-1"))
    assert revise_edit_from_lesson(lesson) is None


def test_clarification_lesson_is_grounded_and_proposes_a_revise():
    lesson = _clarification("FR-2")
    assert is_grounded(lesson)                       # derived-from edge + lives evidence
    assert [e.from_key for e in revises_edges(lesson)] == ["FR-2"]
    assert lesson_status(lesson) == LessonStatus.PROPOSED


# ── REQ-20 H3 — persistence + disposition-preserving merge ───────────────────────────────────────────

def test_store_round_trip(tmp_path):
    store = tmp_path / "lessons.json"
    lessons = [build_lesson_from_regression(_regression("FR-1")), _clarification("FR-2")]
    save_lessons(store, lessons)
    back = load_lessons(store)
    assert [n.key for n in back] == [n.key for n in lessons]
    # the concrete edit survives the round-trip (attributes preserved)
    assert revise_edit_from_lesson(find_lesson(back, "FR-2")) is not None


def test_load_missing_store_is_empty(tmp_path):
    assert load_lessons(tmp_path / "nope.json") == []


def test_merge_preserves_human_acceptance_across_a_rerun(tmp_path):
    store = tmp_path / "lessons.json"
    first = [build_lesson_from_regression(_regression("FR-1"))]
    save_lessons(store, first)

    # human accepts it, persists
    disposed = upsert_lesson(load_lessons(store), accept_lesson(find_lesson(load_lessons(store), "FR-1")))
    save_lessons(store, disposed)
    assert lesson_status(find_lesson(load_lessons(store), "FR-1")) == LessonStatus.ACCEPTED

    # a fresh retrospective re-derives the SAME regression as `proposed` — merge must NOT reset it
    rerun = [build_lesson_from_regression(_regression("FR-1"))]
    merged = merge_lessons(load_lessons(store), rerun)
    assert lesson_status(find_lesson(merged, "FR-1")) == LessonStatus.ACCEPTED


def test_merge_preserves_rejection_and_rationale(tmp_path):
    prior = [reject_lesson(build_lesson_from_regression(_regression("FR-1")), "wrong root cause")]
    rerun = [build_lesson_from_regression(_regression("FR-1"))]
    merged = merge_lessons(prior, rerun)
    got = find_lesson(merged, "FR-1")
    assert lesson_status(got) == LessonStatus.REJECTED
    assert got.attributes.get("rationale") == "wrong root cause"


def test_merge_retains_existing_only_lessons_as_cross_run_memory():
    prior = [reject_lesson(build_lesson_from_regression(_regression("FR-9")), "obsolete")]
    rerun = [build_lesson_from_regression(_regression("FR-1"))]        # a different regression this run
    merged = merge_lessons(prior, rerun)
    keys = {n.key for n in merged}
    assert "lesson:FR-9" in keys and "lesson:FR-1" in keys            # the judged FR-9 outlives its run


def test_merge_refreshes_derived_content_of_a_proposed_lesson():
    prior = [build_lesson_from_regression(_regression("FR-1"))]        # still proposed
    rerun = [build_lesson_from_description_clarification(
        "FR-1", path="schema.prisma", before="a", after="b")]         # same key, now carries an edit
    merged = merge_lessons(prior, rerun)
    # a proposed lesson is freely refreshed → it now carries the concrete edit
    assert revise_edit_from_lesson(find_lesson(merged, "FR-1")) is not None
