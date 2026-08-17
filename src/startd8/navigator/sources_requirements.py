"""Minimal det-req/0.1 → Nodes (FR-6). Full V-1..V-5 plan-DAG parity is out of scope.

Uses vendored thin Lives/`fr_health` (``det_req.py``); does not require det-req-kit
on ``sys.path``.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import List, Optional

from startd8.wireframe.profile import RenderProfile

from .det_req import fr_health, parse_fr_lines_prefer_kit
from .git_lives import prefer_git_ref
from .models import Node, NodeEvidence, NodeStatus, default_confidence, derive_status
from .naming import name_forms
from .view_definition import (
    DEFINITION_REGISTRY,
    REQUIREMENTS_DEFINITION,
    resolve,
    to_render_profile,
)

# A Touches path is test evidence when it lives under a tests/ tree or is a test_/_test file.
_TEST_PATH = re.compile(r"(?:^|/)tests?(?:/|_)|(?:^|/)test_|_test\.")


def _initiative_slug(path: Path) -> str:
    """Initiative id for the canonical ref, from the REQ filename — the semantic slug with the ``REQ-``/
    ``PLAN-`` content-type brand stripped (integer-led ``REQ-01-sdk-node-home`` → ``sdk-node-home`` AND
    DIDL semantic ``REQ-seat-authoring`` → ``seat-authoring``; a bare brand must not leak into the
    canonical initiative — the filename-as-identity anti-pattern)."""
    return re.sub(r"^(?:REQ|PLAN)-(?:\d+-)?", "", Path(path).stem, flags=re.IGNORECASE) or "requirements"


_OBJECTIVE_RE = re.compile(r"^- \*\*(O-\d+):\*\*\s*(.+?)\s*$", re.MULTILINE)


def _parse_objectives(text: str) -> dict:
    """Map each objective id (``O-1``) → its text, so an FR's ``Serves: O-1`` can carry the objective's
    value statement (the 'why / system benefit' a reader otherwise can't see on the card)."""
    return {m.group(1): m.group(2).strip() for m in _OBJECTIVE_RE.finditer(text)}


# REQ-23 FR-1: an objective often carries a measurable ``target:`` goal; an optional ``Signal:`` binds it
# to a LIVE measurement handle (a metric name / live query). Both parsed off the objective's own line.
_TARGET_RE = re.compile(r"(?:—|-|:)?\s*target:\s*(?P<t>.+?)(?:\.\s*Signal:|$)", re.IGNORECASE)
_SIGNAL_RE = re.compile(r"\bSignal:\s*(?P<s>.+?)\s*$", re.IGNORECASE)


def outcome_nodes_from_requirements(path: Path, *, text: Optional[str] = None) -> List[Node]:
    """REQ-23 FR-1 — project each objective (``O-N``) as an **outcome** Node (``category="objective"``)
    carrying its ``target`` (the measurable goal) and an optional ``target_signal`` (the live-measurement
    binding) in ``attributes``. A plain projection, NOT a metric framework (NR-4). Empty target_signal →
    the target is unmeasured (a fact the ``target-unmeasured`` check surfaces)."""
    path = Path(path)
    text = text if text is not None else path.read_text(encoding="utf-8")
    out: List[Node] = []
    for key, body in _parse_objectives(text).items():
        tm = _TARGET_RE.search(body)
        target = (tm.group("t").strip().rstrip(".") if tm else "")
        sm = _SIGNAL_RE.search(body)
        signal = (sm.group("s").strip().rstrip(".") if sm else "")
        attrs = {"kind": "objective", "title": key, "target": target, "target_signal": signal,
                 "section_order": "10", "provenance": "authored"}
        out.append(Node(key=key, does=body, category="objective", orientation="outcome",
                        lives=(NodeEvidence(type="doc", ref=f"{path.name}#{key}"),), attributes=attrs))
    return out


# Functional archetype — the 'what kind of requirement' a reader grasps at a glance. DERIVED lexically
# for now (a hint, provenance=derived); an authored ``Type:`` FR field can override it later (the writer
# spec already reserves the seam). Each → (plain label for the broadest audience, one-line gloss).
_ARCHETYPE_RULES = [
    (("guard", "byte-ident", "byte-identical", "invariant", "additive", "unchanged", "no regression",
      "preserve", "must not", "never "), ("safeguard", "protects an invariant / no-regression")),
    (("fix ", "crash", "broke", "defect", "incorrect"), ("fix", "corrects a defect")),   # not 'bug' (deBUG)
    (("migrate", "consolidat", "refactor", "move ", "unify", "reshape", "collapse", "retire"),
     ("refactor", "restructures without changing behaviour")),
    (("toggle", "switch", "picker", "panel", "paging", "on/off", "checkbox", "control ", "button"),
     ("control", "a reader-facing control")),
    (("show", "render", "display", "surface", "card", "template", "legend", "readout", "view "),
     ("display", "renders / shows something")),
]


def _archetype(*parts: str) -> tuple:
    """Best-effort functional archetype from an FR's wording. Returns (label, gloss)."""
    hay = " ".join(p for p in parts if p).lower()
    for keys, out in _ARCHETYPE_RULES:
        if any(k in hay for k in keys):
            return out
    return ("capability", "adds a capability")


def _lives_from_touches(
    touches: List[str],
    existing_refs: set,
    repo_root: Path,
) -> List[NodeEvidence]:
    """FR-6 fidelity: mine an FR's authored ``Touches:`` for typed evidence.

    An FR often cites only one ``Lives:`` type (code *or* test) even though its ``Touches:`` names
    both its implementation and its test — so ``default_confidence`` never sees code+test and every
    node flatlines at 0.6. Each Touches path that **resolves to a real file on disk** becomes
    git-anchored evidence (test-path → ``test``, else ``code``), deduped against explicit Lives.
    Existence-gated so planned/not-yet-created files (and non-path kinds like ``navigator-build``)
    never count — the enrichment is source-bound (Touches is authored), not invented.
    """
    out: List[NodeEvidence] = []
    seen = set(existing_refs)
    for raw in touches or []:
        p = raw.strip().strip("`").lstrip("./")
        if not p or "/" not in p:
            continue
        if not (repo_root / p).is_file():
            continue
        ref = prefer_git_ref(p, repo=repo_root)
        if ref in seen:
            continue
        seen.add(ref)
        etype = "test" if _TEST_PATH.search(p) else "code"
        out.append(NodeEvidence(type=etype, ref=ref, note="from Touches"))
    return out

# FR-4/FR-7: the requirements masthead vocabulary/chrome is now OWNED by ``REQUIREMENTS_DEFINITION``
# (``extends: base`` + a thin delta) and PROJECTED to the existing ``RenderProfile``. The projection
# reproduces the former standalone literal byte-for-byte, so renderers and the app-scaffold path are
# unchanged (guarded by ``test_no_profile_is_byte_identical`` + the equality test). Per-doc masthead
# derivation (``requirements_profile_for``) still layers on top of this base via ``dataclasses.replace``.
REQUIREMENTS_PROFILE = to_render_profile(resolve(REQUIREMENTS_DEFINITION, DEFINITION_REGISTRY))


_H1_RE = re.compile(r"^#\s+(.+?)(?:\s+—\s+Requirements)?\s*$")
_SEMNAME_RE = re.compile(r"^>\s*\*\*Semantic name:\*\*\s*\*(.+?)\*\s*$", re.M)
_KEY_RE = re.compile(r"(REQ-\d+)")
_CANON_INIT_RE = re.compile(r"cc:intent:([a-z0-9-]+):")


def requirement_identity(path: Path, text: Optional[str] = None) -> dict:
    """THIS requirement's own identity, for deterministic masthead generation (FR-17): its key (from
    the filename), its H1 title, its DIDL semantic name, and its initiative (from the canonical ref).
    All authored-deterministic — read from the doc, never machine-invented; each field falls back
    gracefully when absent."""
    path = Path(path)
    text = text if text is not None else path.read_text(encoding="utf-8")
    first = text.splitlines()[0].strip() if text.strip() else ""
    m = _H1_RE.match(first)
    title = m.group(1).strip() if m else path.stem
    km = _KEY_RE.search(path.name)
    sm = _SEMNAME_RE.search(text)
    im = _CANON_INIT_RE.search(text)
    return {
        "key": km.group(1) if km else "",
        "title": title,
        "semantic_name": sm.group(1).strip() if sm else "",
        "initiative": im.group(1) if im else path.parent.name,
    }


def requirements_profile_for(path: Path, text: Optional[str] = None) -> RenderProfile:
    """A per-doc RenderProfile whose masthead + descriptive chrome is DERIVED from the requirement
    itself, replacing ``REQUIREMENTS_PROFILE``'s static domain copy so the view speaks about *this*
    requirement. Two derivation layers:

    - FR-17 masthead identity: eyebrow = key, headline = H1 title, sub-headline = the DIDL semantic
      name (was the static 'This spec' / 'A first look at this spec').
    - FR-18 descriptive chrome: ``section_lead`` = "What {key} defines" (was static
      "What this spec defines") and the page ``title`` (the browser tab / OG title, read by
      ``view.py`` into ``<title>``) = "{key} — {H1 title}" (was static "This spec — a first look").

    Every field falls back to the static base when its identity input can't be extracted (byte-safe:
    the base profile is unchanged; only the CLI's per-render copy differs). The remaining base strings
    — ``why`` / ``do`` (reading guidance about the renderer, not this requirement's content) and
    ``gap_noun`` (domain vocabulary) — are intentionally NOT derived and ride through unchanged."""
    from dataclasses import replace

    # REQ-12: the FR-17/18 single-field derivations (eyebrow/headline/section_lead/summary_meta) now
    # live as declarative bindings on REQUIREMENTS_DEFINITION.chrome and resolve here against the doc's
    # identity context (each degrades to the static base value when its field is empty — the projection
    # enforces that). Only the compound page-title stays imperative (NR-2 — the single-field grammar
    # can't express its 3-way degradation).
    idy = requirement_identity(path, text)
    key = idy["key"]
    title = idy["title"]
    prof = to_render_profile(resolve(REQUIREMENTS_DEFINITION, DEFINITION_REGISTRY), context=idy)
    if key and title:
        doc_title = f"{key} — {title}"
    elif key:
        doc_title = key
    elif title:
        doc_title = title
    else:
        doc_title = prof.title
    return replace(prof, title=doc_title)


def nodes_from_requirements(path: Path, *, repo: Path | None = None) -> List[Node]:
    """Project a det-req markdown file into FR Nodes."""
    path = Path(path)
    text = path.read_text(encoding="utf-8")
    frs = parse_fr_lines_prefer_kit(text)
    repo_root = Path(repo) if repo else _guess_repo(path)
    objectives = _parse_objectives(text)   # O-N → its value statement, for the Serves join (the 'why')
    nodes: List[Node] = []
    for fr in frs:
        explicit = tuple(
            NodeEvidence(
                type=str(e.get("type", "")),
                ref=prefer_git_ref(str(e.get("ref", "")), repo=repo_root),
                note=str(e.get("note", "")),
            )
            for e in (fr.get("lives") or [])
        )
        # FR-6 fidelity: complete typed evidence from the FR's own authored Touches (existence-
        # gated, deduped) so a code+test FR grounds to both without hand-citing every Lives.
        from_touches = _lives_from_touches(
            fr.get("touches") or [], {e.ref for e in explicit}, repo_root
        )
        lives = explicit + tuple(from_touches)
        # Seat-req FR-4 (R1-F1): the evidence-gate HEALTH class must be computed from AUTHORED ``Lives:``
        # ONLY — a mined ``Touches:`` ref is ``provenance: derived`` (note "from Touches") and MUST NOT
        # clear the done-claim gate, or the SDK twin silently disagrees with ``req-health.mjs`` /
        # ``extract.py`` (which see only authored lives). Recompute after prefer_git upgrades (EVIDENCE-1).
        health = fr_health(
            {
                **fr,
                "lives": [{"type": e.type, "ref": e.ref} for e in explicit],
            }
        )
        # A code Lives grounds the FR only if it RESOLVES — a git-anchored ref (exists at a commit)
        # or a plain path that exists on disk. A `code` Lives to a not-yet-created file (an unbuilt
        # spec, e.g. a new module named in Touches) must NOT read as grounded/green: honest status is
        # spec ("written, not built"), not built. Fixes the false-GROUNDED on pre-build specs.
        has_code = any(
            ev.type == "code" and (ev.ref.startswith("git:") or (repo_root / ev.ref).exists())
            for ev in lives
        )
        # Done-claim without strong lives stays SPEC / awaiting — never grounded green.
        if health == "unknown":
            status = NodeStatus.SPEC
            status_key = "unknown"
            route = ""
        elif health == "skipped":
            status = NodeStatus.SPEC
            status_key = "excluded"
            route = "declared_unimplemented"
        elif has_code:
            status = derive_status(has_code_evidence=True, maturity="stable")
            status_key = "grounded"
            route = "sdk_emitted"
        else:
            status = NodeStatus.SPEC
            status_key = "spec"
            route = "declared_unimplemented" if not lives else ""

        ships_when = ""
        if not lives:
            ships_when = "evidence authored (Lives:)"

        conf = default_confidence(lives)
        does = (fr.get("behavior") or fr.get("title") or "").strip()
        prompts = tuple(fr.get("approve_prompts") or ())
        was = tuple(fr.get("was") or ())
        attrs: dict = {
            "kind": "fr",
            "title": str(fr.get("title", "")),
            "verify": str(fr.get("verify", "")),
            "serves": ", ".join(fr.get("serves") or []),
            "touches": ", ".join(fr.get("touches") or []),
            "fr_health": health,
            "status_key": status_key,
            "section_order": "30",
            "provenance": "authored",
        }
        # Join the served objective's text so the card can show the 'why / system benefit' (the FR only
        # names Serves: O-N; the objective's value statement lives in the Objectives section).
        served = [objectives[s] for s in (fr.get("serves") or []) if s in objectives]
        if served:
            attrs["serves_objective"] = " · ".join(served)
        # Functional archetype (derive-now, author-later): an authored ``Type:`` wins if present.
        # Classify from the TITLE (+ semantic name) — NOT verify/does, whose recurring byte-identity
        # boilerplate would mislabel most FRs as "safeguard".
        arch = (str(fr.get("type") or "").strip().lower(), "")
        if not arch[0]:
            arch = _archetype(str(fr.get("title", "")), str(fr.get("name", "")))
        attrs["archetype"], attrs["archetype_gloss"] = arch[0], arch[1]
        # Scope: how many files the FR touches (its blast-radius) — a plain at-a-glance size.
        tcount = len([t for t in (fr.get("touches") or []) if str(t).strip()])
        if tcount:
            attrs["touches_count"] = str(tcount)
        if prompts:
            attrs["approve_prompts"] = " · ".join(prompts)
        if was:
            attrs["was"] = " · ".join(was)
        # Deterministic semantic name (anti-pattern guard: a requirement must be identifiable by
        # MEANING, not the integer+content-type key alone). Authored `Name:` → name + derived handle
        # + canonical ref. Absent → only the local key (surfaced as a content gap by the loop).
        name = str(fr.get("name") or "").strip()
        if name:
            attrs.update(name_forms(name, str(fr["id"]),
                                    initiative=_initiative_slug(path), kind="requirement"))
        nodes.append(
            Node(
                key=str(fr["id"]),
                does=does,
                status=status,
                lives=lives,
                ships_when=ships_when if not lives else "",
                confidence=conf,
                category="functional-requirements",
                orientation="bridge",
                route_state=route,
                attributes=attrs,
                # REQ-17 FR-2: carry the reliability semantics onto first-class Node fields instead of
                # dropping them at the det_req→Node boundary. The ``attrs`` entries above remain the
                # render channel (byte-identity); these fields are the structured carriers REQ-08 reads.
                # An FR lacking a clause projects the empty default (str "" / empty tuple).
                verify=str(fr.get("verify") or ""),
                approve=prompts,
                was=was,
                verify_gate=str(fr.get("gate") or ""),   # REQ-22 FR-1: the runnable gate handle (liveness)
            )
        )
    return nodes


def _guess_repo(path: Path) -> Path:
    cur = path.resolve().parent
    for _ in range(8):
        if (cur / ".git").exists():
            return cur
        if cur.parent == cur:
            break
        cur = cur.parent
    return Path.cwd()
