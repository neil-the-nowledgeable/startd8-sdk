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
    """Initiative id for the canonical ref, from the REQ filename (REQ-01-sdk-node-home → sdk-node-home)."""
    return re.sub(r"^REQ-\d+-", "", Path(path).stem, flags=re.IGNORECASE) or "requirements"


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

    idy = requirement_identity(path, text)
    key = idy["key"]
    title = idy["title"]
    # section_lead names THIS requirement ("What REQ-01 defines"); page title is "{key} — {H1}".
    # Both prefer the key (the stable, self-identifying handle); degrade gracefully when it's absent.
    section_lead = f"What {key} defines" if key else REQUIREMENTS_PROFILE.section_lead
    if key and title:
        doc_title = f"{key} — {title}"
    elif key:
        doc_title = key
    elif title:
        doc_title = title
    else:
        doc_title = REQUIREMENTS_PROFILE.title
    return replace(
        REQUIREMENTS_PROFILE,
        eyebrow=key or REQUIREMENTS_PROFILE.eyebrow,
        headline=title or REQUIREMENTS_PROFILE.headline,
        summary_meta=(idy["semantic_name"],) if idy["semantic_name"] else REQUIREMENTS_PROFILE.summary_meta,
        section_lead=section_lead,
        title=doc_title,
    )


def nodes_from_requirements(path: Path, *, repo: Path | None = None) -> List[Node]:
    """Project a det-req markdown file into FR Nodes."""
    path = Path(path)
    text = path.read_text(encoding="utf-8")
    frs = parse_fr_lines_prefer_kit(text)
    repo_root = Path(repo) if repo else _guess_repo(path)
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
        # Recompute health after prefer_git upgrades soft→strong (EVIDENCE-1).
        health = fr_health(
            {
                **fr,
                "lives": [{"type": e.type, "ref": e.ref} for e in lives],
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
