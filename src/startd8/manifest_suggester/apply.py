# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""Accumulation-aware apply seam (FR-MS-5/7 — the R2-S1 finding).

The `manifest` proposal kind's apply is a **whole-file replace** derived from the prose `source` — so
approving a second screen after a first would clobber it (R2-S1). This module implements the accepted
**option (a): a running authoring-prose document** (``docs/kickoff/inputs/screens-authoring.md``) that
**accumulates every approved candidate's prose**; each ``approve`` re-emits the **whole** accumulated
document as the `source`, so ``views.yaml``/``pages.yaml`` always contains the union of approved screens.

Two safety properties:

* **The extractor round-trip is the authoritative gate (FR-MS-5).** Apply goes through
  ``apply_proposal(kind="manifest")`` → ``_apply_manifest`` re-extracts + validates; a prose that fails
  extraction is rejected at apply, never silently written.
* **Hand-authored content is protected.** The **first** suggester apply uses ``replace=False`` — if a
  non-suggester ``views.yaml`` already exists, the apply returns ``would_clobber`` and we refuse rather
  than overwrite. Only once the running authoring doc exists (i.e. we own the manifest) do subsequent
  applies use ``replace=True`` for accumulation. (The YAML→prose *decompiler*, option (b), that would let
  us preserve external edits too, stays deferred per triage.)
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Set, Tuple

from startd8.manifest_extraction.grammar import nfkd_kebab

from startd8.manifest_suggester.models import KIND_PAGE, ScreenCandidate

__all__ = [
    "AUTHORING_REL",
    "ApplyOutcome",
    "read_authoring",
    "authored_slugs",
    "apply_screen",
]

# The running authoring-prose document — the suggester's source of truth for the screens it manages.
AUTHORING_REL = Path("docs") / "kickoff" / "inputs" / "screens-authoring.md"

# A `### view: <Name>` section header (level 2-4), from which the extractor derives a view.
_VIEW_HEADER = re.compile(r"^#{2,4}\s+view:\s*(.+?)\s*$", re.MULTILINE | re.IGNORECASE)
# The `## Pages` section (up to the next heading or EOF) — pages share ONE table (extract_pages reads
# only the first `## Pages`), so accumulation must MERGE rows into it, not append a second section.
_PAGES_SECTION = re.compile(
    r"^##\s+Pages\s*$.*?(?=\n#{1,4}\s|\Z)", re.MULTILINE | re.DOTALL | re.IGNORECASE
)
_TABLE_ROW = re.compile(r"^\|(.+)\|\s*$", re.MULTILINE)


def _page_rows(text: str) -> list:
    """(page-name, content-file) rows from the doc's ``## Pages`` table (header/separator skipped)."""
    m = _PAGES_SECTION.search(text or "")
    if not m:
        return []
    rows = []
    for rm in _TABLE_ROW.finditer(m.group(0)):
        cells = [c.strip() for c in rm.group(1).split("|")]
        if len(cells) < 2:
            continue
        name, content = cells[0], cells[1]
        if not name or name.lower() == "page" or set(name) <= set("- "):
            continue  # header row or `---` separator
        rows.append((name, content))
    return rows


def _render_pages_section(rows: list) -> str:
    lines = ["## Pages", "", "| Page | Content file |", "| ---- | ---- |"]
    lines += [f"| {name} | {content} |" for name, content in rows]
    return "\n".join(lines) + "\n"


@dataclass
class ApplyOutcome:
    applied: bool
    reason: str = ""
    code: str = ""
    authoring: str = ""


def read_authoring(project_root: Path | str) -> str:
    path = Path(project_root).expanduser() / AUTHORING_REL
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def authored_slugs(authoring_text: str) -> Set[str]:
    """Slugs already present in the running authoring doc — view headers **and** page rows (FR-MS-3)."""
    slugs = {
        nfkd_kebab(m.group(1)) for m in _VIEW_HEADER.finditer(authoring_text or "")
    }
    slugs |= {nfkd_kebab(name) for name, _ in _page_rows(authoring_text or "")}
    return slugs


def accumulate(existing: str, candidate: ScreenCandidate) -> Tuple[str, bool]:
    """Merge *candidate*'s prose into *existing* iff its slug is new. Returns (doc, added).

    The candidate's prose is **structural** (its ``### view:`` heading / ``## Pages`` table are intentional
    and must survive round-trip) — sanitization (FR-MS-6) is applied to the persona *free-text fields* at
    draft time (``suggest._build_candidate``), NEVER to the whole prose here.

    * **View** → appended as its own ``### view:`` section (views are independent sections).
    * **Page** → its row is merged into the single shared ``## Pages`` table (``extract_pages`` reads only
      the first such section, so a second ``## Pages`` block would be silently dropped — R2-S1 for pages).
    """
    if candidate.slug in authored_slugs(existing):
        return existing, False

    if candidate.kind == KIND_PAGE:
        rows = _page_rows(existing)
        # the candidate's own prose carries its (name, content-file) row — take it, or default the file.
        own = _page_rows(candidate.prose)
        rows.append(own[0] if own else (candidate.name, f"{candidate.slug}.md"))
        body = _PAGES_SECTION.sub("", existing).rstrip("\n")
        section = _render_pages_section(rows)
        doc = (body + "\n\n" + section) if body.strip() else section
        return doc, True

    block = candidate.prose.rstrip("\n") + "\n"
    if existing.strip():
        return existing.rstrip("\n") + "\n\n" + block, True
    return block, True


def apply_screen(
    project_root: Path | str, candidate: ScreenCandidate, *, config=None
) -> ApplyOutcome:
    """Accumulate + apply *candidate* through the `manifest` proposal kind (FR-MS-5/7).

    Never writes the running authoring doc unless the manifest apply succeeded (a round-trip failure
    must not corrupt the source of truth).
    """
    from startd8.kickoff_experience.proposals import ProposedAction, apply_proposal

    root = Path(project_root).expanduser()
    existing = read_authoring(root)
    whole, added = accumulate(existing, candidate)
    if not added:
        return ApplyOutcome(
            applied=False,
            reason=f"{candidate.name!r} already in the authoring doc",
            code="duplicate",
        )

    # First apply (no running doc yet) is no-clobber; accumulation applies replace over our own doc.
    first_apply = not existing.strip()
    action = ProposedAction(
        kind="manifest",
        params={
            "source": whole,
            "replace": not first_apply,
            "source_label": "screens-authoring.md",
        },
        id=uuid.uuid4().hex,
    )
    # apply_proposal returns typed outcomes for the expected paths, but the safe-write layer can raise
    # (e.g. a symlinked/`..` project root → SafeWriteError). Convert any raise into a clean failed
    # outcome so the CLI never shows a traceback and the running authoring doc is never persisted.
    try:
        outcome = apply_proposal(root, action, config=config)
    except (
        Exception
    ) as exc:  # noqa: BLE001 - a hard failure must degrade to a typed refusal, not a crash
        return ApplyOutcome(applied=False, code="apply_error", reason=str(exc))

    if not outcome.ok:
        if outcome.code == "would_clobber":
            return ApplyOutcome(
                applied=False,
                code="would_clobber",
                reason=(
                    "views.yaml/pages.yaml already exists and is not suggester-managed — refusing to "
                    "overwrite hand-authored screens (the decompiler that would merge them is deferred)"
                ),
            )
        return ApplyOutcome(
            applied=False, code=outcome.code, reason=outcome.detail or outcome.code
        )

    # Success — persist the running authoring doc (source of truth) only now.
    path = root / AUTHORING_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(whole, encoding="utf-8")
    return ApplyOutcome(
        applied=True, code=outcome.code, reason=outcome.detail, authoring=whole
    )


def existing_manifest_slugs(project_root: Path | str) -> Set[str]:
    """View/page slugs already in the live ``views.yaml``/``pages.yaml`` (dedupe against them, FR-MS-3)."""
    import yaml

    from startd8.wireframe.inputs import CONVENTION_PATHS

    root = Path(project_root).expanduser()
    slugs: Set[str] = set()
    for key in ("views", "pages"):
        path = root / CONVENTION_PATHS[key]
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError):
            continue
        items = data.get(key) if isinstance(data, dict) else None
        for item in items or []:
            if not isinstance(item, dict):
                continue
            # views key on `name`; pages may key on `slug` — tolerate either so dedupe never misses.
            ident = item.get("name") or item.get("slug")
            if ident:
                slugs.add(nfkd_kebab(str(ident)))
    return slugs


def all_existing_slugs(project_root: Path | str) -> Set[str]:
    """Dedupe target (FR-MS-3): everything already authored — the running doc + the live manifests."""
    return authored_slugs(read_authoring(project_root)) | existing_manifest_slugs(
        project_root
    )


# re-export for the store's dedupe helper convenience
__all__ += ["accumulate", "existing_manifest_slugs", "all_existing_slugs"]
