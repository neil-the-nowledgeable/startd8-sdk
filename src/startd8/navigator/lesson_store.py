"""Lesson persistence store (REQ-20 H3) — give retrospective Lessons memory across runs.

REQ-20 built the Lesson node + human disposition (``accept_lesson``/``reject_lesson``) but the Lessons
were **ephemeral**: a "retained" rejected Lesson lived only in memory, so the next ``retrospective`` run
re-proposed it as if the human had never judged it. This store closes that seam.

The load-bearing behaviour is the **merge**: re-running the retrospective refreshes each Lesson's *derived*
content (its outcome/grounding/confidence) but **preserves the human's disposition** — an ``accepted`` or
``rejected`` Lesson stays that way, keeping its rationale. A Lesson the human already judged is never
silently reset to ``proposed``. Existing Lessons a later run doesn't re-derive are retained (the memory of
*why* a proposal was declined outlives the run that produced it — the cross-run half of Kaizen).

Firewall: this is pure IR persistence — it imports only the Node round-trip (``project``) and the Lesson
vocabulary (``sources_retrospective``); no construction subsystem, same as the navigator core.
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from typing import List

from .models import Node
from .project import nodes_from_json, nodes_to_json
from .sources_retrospective import LessonStatus, lesson_status

# A human disposition is preserved across a re-derive; a still-``proposed`` Lesson is refreshed freely.
_HUMAN_DISPOSED = (LessonStatus.ACCEPTED, LessonStatus.REJECTED)


def load_lessons(path) -> List[Node]:
    """Load persisted Lessons from ``path`` (a ``{"lessons": [...]}`` JSON doc). A missing file → ``[]``
    (an empty store is valid — the first run has nothing to remember)."""
    p = Path(path)
    if not p.exists():
        return []
    data = json.loads(p.read_text(encoding="utf-8"))
    return nodes_from_json(data.get("lessons", data) if isinstance(data, dict) else data)


def save_lessons(path, lessons: List[Node]) -> None:
    """Persist ``lessons`` to ``path`` as a stable, diff-friendly JSON doc (sorted keys)."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = {"store": "navigator-lessons", "lessons": nodes_to_json(lessons)}
    p.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True) + "\n", encoding="utf-8")


def merge_lessons(existing: List[Node], incoming: List[Node]) -> List[Node]:
    """Merge a freshly-derived ``incoming`` Lesson set into the persisted ``existing`` one, preserving
    human dispositions. For a key present in both: refresh the derived content from ``incoming`` but keep
    ``existing``'s ``status`` + ``rationale`` when the human already disposed it (accepted/rejected).
    Existing-only Lessons are retained (cross-run memory). Order: incoming first, then existing-only."""
    by_key = {n.key: n for n in existing}
    seen = set()
    out: List[Node] = []
    for inc in incoming:
        seen.add(inc.key)
        prior = by_key.get(inc.key)
        if prior is not None and lesson_status(prior) in _HUMAN_DISPOSED:
            attrs = {**inc.attributes, "status": prior.attributes.get("status")}
            if "rationale" in prior.attributes:
                attrs["rationale"] = prior.attributes["rationale"]
            out.append(dataclasses.replace(inc, attributes=attrs))
        else:
            out.append(inc)
    for prior in existing:
        if prior.key not in seen:
            out.append(prior)  # a judged Lesson outlives the run that first proposed it
    return out


def find_lesson(lessons: List[Node], key: str) -> Node | None:
    """Locate a Lesson by its ``key`` (accepts the bare requirement key too, matching ``lesson:<key>``)."""
    for n in lessons:
        if n.key == key or n.key == f"lesson:{key}":
            return n
    return None


def upsert_lesson(lessons: List[Node], updated: Node) -> List[Node]:
    """Replace the Lesson sharing ``updated.key`` (append if new), preserving order — the write-back a
    disposition command uses after ``accept_lesson``/``reject_lesson``."""
    out = [updated if n.key == updated.key else n for n in lessons]
    if all(n.key != updated.key for n in lessons):
        out.append(updated)
    return out
