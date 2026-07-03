# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

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

from startd8.manifest_suggester.models import ScreenCandidate

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
    """The view slugs already present in the running authoring doc (dedupe input, FR-MS-3)."""
    return {nfkd_kebab(m.group(1)) for m in _VIEW_HEADER.finditer(authoring_text or "")}


def accumulate(existing: str, candidate: ScreenCandidate) -> Tuple[str, bool]:
    """Append *candidate*'s prose to *existing* iff its slug is new. Returns (doc, added).

    The candidate's prose is **structural** (its ``### view:`` heading is intentional and must survive
    round-trip) — sanitization (FR-MS-6) is applied to the persona *free-text fields* at draft time
    (``suggest._build_candidate``), NEVER to the whole prose here, which would demote the real heading.
    """
    if candidate.slug in authored_slugs(existing):
        return existing, False
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
    outcome = apply_proposal(root, action, config=config)

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
            name = item.get("name") if isinstance(item, dict) else None
            if name:
                slugs.add(nfkd_kebab(str(name)))
    return slugs


def all_existing_slugs(project_root: Path | str) -> Set[str]:
    """Dedupe target (FR-MS-3): everything already authored — the running doc + the live manifests."""
    return authored_slugs(read_authoring(project_root)) | existing_manifest_slugs(
        project_root
    )


# re-export for the store's dedupe helper convenience
__all__ += ["accumulate", "existing_manifest_slugs", "all_existing_slugs"]
