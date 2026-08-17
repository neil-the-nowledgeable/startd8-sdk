"""Byte-identity revise applier (REQ-24) — fills REQ-21's ``auto_apply_revise`` guard seam with a REAL
byte-identity guard that regenerates the deterministic ``$0`` product and hash-compares it.

**Firewall boundary (REQ-19 / FR-6):** this is the APPLIER LAYER — it imports the deterministic codegen
(to regenerate the product), which the navigator *core* (``revise_tier``/``realization*``/``sources_*``)
never does. The core exposes only the construction-free ``auto_apply_revise`` seam; the construction
coupling is quarantined here.

The guard is the arbiter (enforce, don't declare): it applies a revise's concrete edit to the contract,
regenerates the owned product, and returns True only when every owned file's bytes AND the file set are
unchanged. Any diff, an inapplicable edit, or a generation error → False → the revise stays ``human``.

**REQ-24 H2 — deterministic output kinds, and why polyglot fails safe.** The guard is *pluggable* across
the deterministic ``$0`` family (``backend``, ``scaffold``, …) via a regenerator registry — not bound to
the backend renderer alone. It is NOT extended to polyglot / LLM-driven output, and that is the correct
answer, not a gap: an LLM generator is non-deterministic (different bytes each run with no edit), so
"regenerate + compare" proves nothing — byte-identity is *unprovable* there. Such kinds have no
regenerator and their revises fail safe to ``human`` by construction, which IS REQ-21's principle (auto
only when byte-identity is provable).
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Callable, Dict, Iterable, Optional, Tuple

from .models import Node
from .revise_tier import ReviseAudit, ReviseEdit, ReviseEligibility, auto_apply_revise


# Build-time discovery (folded back to REQ-24 §0): every generated file carries a ``# <source>-sha256:``
# provenance header that fingerprints its SOURCE input — so ANY source edit changes the stamp on every
# file, and STRICT byte-identity can never pass. The gate is therefore "the product's real generated
# content is unchanged, MODULO its own source-fingerprint stamp" — a comment/whitespace/description edit
# changes only the stamp (→ identical); a field rename changes real content (→ diff). This is principled,
# not eroded: it excludes provenance metadata (like a build timestamp), not behaviour.
#
# REQ-24 H2: this must cover EVERY source-fingerprint stamp any registered deterministic regenerator emits
# (the whole ``$0`` family), not just the backend's ``schema-sha256`` — else a kind whose stamp isn't
# stripped (e.g. scaffold's ``manifest-sha256``) can NEVER pass the guard. Derived from the codegen:
# ``grep -rhoE '[a-z_]+-sha256:' src/startd8/{backend,scaffold,view,frontend}_codegen``.
_PROVENANCE_MARKERS = (
    "schema-sha256:", "contract-sha256:", "contexts-sha256:", "manifest-sha256:", "views-sha256:",
    "display-sha256:", "pages-sha256:", "forms-sha256:", "imports-sha256:", "inputs-sha256:",
    "api-sha256:", "passes-sha256:",
)


# ── REQ-24 H2 — the byte-identity guard across DETERMINISTIC output kinds (not just backend) ──────────
#
# A ``Regenerator`` regenerates the ``$0`` product from a source-text: ``(source_text, mode) -> (path,
# content) pairs``. Byte-identity is a sound auto-tier gate ONLY for deterministic output — a *polyglot /
# LLM-driven* generator produces different bytes on every run even with NO edit, so "regenerate + compare"
# proves nothing there. Such kinds have **no regenerator** here, and their revises fail safe to ``human``.
Regenerator = Callable[[str, str], Iterable[Tuple[str, str]]]


def _regen_backend(source_text: str, mode: str) -> Iterable[Tuple[str, str]]:
    """The all-Python backend ``$0`` product (schema.prisma → FastAPI/Pydantic/SQLModel/HTMX)."""
    from startd8.backend_codegen import render_backend
    return render_backend(source_text, deployment_mode=mode)


def _regen_scaffold(source_text: str, mode: str) -> Iterable[Tuple[str, str]]:
    """The project-plumbing ``$0`` product (app.yaml manifest → pyproject/logging/alembic/Dockerfile).
    Mode-agnostic — the manifest carries its own deploy flags."""
    from startd8.scaffold_codegen.renderers import render_scaffold
    return render_scaffold(source_text)


# The deterministic ``$0`` output kinds a revise can be byte-identity-guarded against. Each is a
# single-source renderer (edited contract text → owned ``(path, content)`` pairs). Extensible: ``views``
# (needs schema+views_text, a two-source join) and ``frontend`` (zod) are future entries with the same
# shape. ``backend`` is the default (REQ-24 back-compat). Anything NOT here is non-deterministic → human.
DETERMINISTIC_REGENERATORS: Dict[str, Regenerator] = {
    "backend": _regen_backend,
    "scaffold": _regen_scaffold,
}


def resolve_regenerator(kind: Optional[str]) -> Optional[Regenerator]:
    """The deterministic regenerator for ``kind`` (default ``backend``), or ``None`` when the kind is
    unknown / non-deterministic (polyglot / LLM) — in which case byte-identity is unprovable and the
    revise fails safe to ``human``."""
    return DETERMINISTIC_REGENERATORS.get((kind or "backend").strip().lower())


def is_deterministic_kind(kind: Optional[str]) -> bool:
    """Whether ``kind`` has a byte-identity-provable regenerator (so auto-apply is even possible)."""
    return resolve_regenerator(kind) is not None


def _strip_provenance(content: str) -> str:
    """Drop source-fingerprint provenance lines so the comparison sees the product's real content."""
    return "\n".join(
        line for line in content.splitlines()
        if not any(marker in line for marker in _PROVENANCE_MARKERS)
    )


def _product_hash(source_text: str, regen: Regenerator, *, mode: str = "installed") -> Dict[str, str]:
    """The ``$0`` product fingerprint: ``{path: sha256(content-minus-provenance-stamp)}`` over every owned
    file ``regen`` emits. Comparing two of these proves the product's real content is unchanged (file set
    + every file's behaviour), independent of the source-fingerprint header."""
    return {
        path: hashlib.sha256(_strip_provenance(content).encode("utf-8")).hexdigest()
        for path, content in regen(source_text, mode)
    }


def apply_edit_to_contract(schema_text: str, edit: ReviseEdit) -> Optional[str]:
    """Apply a revise edit to the contract text: replace the FIRST occurrence of ``edit.before`` with
    ``edit.after``. Returns the revised text, or ``None`` when ``before`` is absent (an inapplicable edit
    — the applier fails safe rather than silently no-op)."""
    if edit.before not in schema_text:
        return None
    return schema_text.replace(edit.before, edit.after, 1)


def byte_identity_guard(
    schema_text: str, edit: ReviseEdit, *, kind: str = "backend", mode: str = "installed",
) -> Callable[[], bool]:
    """FR-2 / H2 — a REAL byte-identity guard over the ``kind`` deterministic product: applies ``edit`` to
    the contract, regenerates, and returns ``True`` iff the product is unchanged. A **non-deterministic /
    unknown ``kind``** (no regenerator) → the guard always returns ``False`` (byte-identity unprovable →
    fail-safe to ``human``). An inapplicable edit or any generation error → ``False`` (fail-closed). Reuses
    the deterministic renderer for that kind — no parallel generation path (Mottainai)."""
    regen = resolve_regenerator(kind)

    def guard() -> bool:
        if regen is None:
            return False  # H2: non-deterministic / unknown output kind → byte-identity unprovable → human
        try:
            revised = apply_edit_to_contract(schema_text, edit)
            if revised is None or revised == schema_text:
                return False  # inapplicable / no-op edit can't be proven → fail-closed to human
            return _product_hash(schema_text, regen, mode=mode) == _product_hash(revised, regen, mode=mode)
        except Exception:
            return False  # any regeneration error → fail-closed
    return guard


def apply_revise(
    schema_path,
    edit: ReviseEdit,
    lesson: Node,
    elig: ReviseEligibility,
    *,
    timestamp: str,
    revert_ref: str,
    dry_run: bool = True,
    kind: str = "backend",
    mode: str = "installed",
) -> Optional[ReviseAudit]:
    """FR-3/FR-4 — run the revise THROUGH REQ-21's ``auto_apply_revise`` with the real FR-2/H2 guard over
    the ``kind`` deterministic product.

    Returns a :class:`ReviseAudit` when the edit is auto-applied (tier ``auto`` AND the guard proves the
    product unchanged); ``None`` when downgraded to ``human`` (wrong tier, a non-deterministic ``kind``, or
    the guard sees a diff/error). The contract file is written ONLY on an auto-apply and only when
    ``dry_run`` is False — so a downgraded revise leaves the working tree byte-identical (FR-4)."""
    schema_path = Path(schema_path)
    schema_text = schema_path.read_text(encoding="utf-8")
    guard = byte_identity_guard(schema_text, edit, kind=kind, mode=mode)
    audit = auto_apply_revise(lesson, elig, guard, timestamp=timestamp, revert_ref=revert_ref)
    if audit is None:
        return None                                        # human — contract untouched
    if not dry_run:
        revised = apply_edit_to_contract(schema_text, edit)
        if revised is not None:                            # (guard already proved it applies + is identical)
            schema_path.write_text(revised, encoding="utf-8")
    return audit
