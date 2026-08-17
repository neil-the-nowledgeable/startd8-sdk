"""Byte-identity revise applier (REQ-24) — fills REQ-21's ``auto_apply_revise`` guard seam with a REAL
byte-identity guard that regenerates the deterministic ``$0`` product and hash-compares it.

**Firewall boundary (REQ-19 / FR-6):** this is the APPLIER LAYER — it imports ``backend_codegen`` (to
regenerate the product), which the navigator *core* (``revise_tier``/``realization*``/``sources_*``) never
does. The core exposes only the construction-free ``auto_apply_revise`` seam; the construction coupling is
quarantined here.

The guard is the arbiter (enforce, don't declare): it applies a revise's concrete edit to the contract,
regenerates via ``render_backend``, and returns True only when every owned file's bytes AND the file set
are unchanged. Any diff, an inapplicable edit, or a generation error → False → the revise stays ``human``.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Callable, Dict, Optional

from .models import Node
from .revise_tier import ReviseAudit, ReviseEdit, ReviseEligibility, auto_apply_revise


# Build-time discovery (folded back to REQ-24 §0): every generated file carries a ``# schema-sha256:``
# provenance header that fingerprints the SOURCE schema — so ANY schema edit changes the stamp on every
# file, and STRICT byte-identity can never pass for a schema edit. The gate is therefore "the product's
# real generated content is unchanged, MODULO its own source-fingerprint stamp" — a comment/whitespace/
# description edit changes only the stamp (→ identical); a field rename changes real content (→ diff).
# This is principled, not eroded: it excludes provenance metadata (like a build timestamp), not behaviour.
_PROVENANCE_MARKERS = ("schema-sha256:", "contract-sha256:", "contexts-sha256:")


def _strip_provenance(content: str) -> str:
    """Drop source-fingerprint provenance lines so the comparison sees the product's real content."""
    return "\n".join(
        line for line in content.splitlines()
        if not any(marker in line for marker in _PROVENANCE_MARKERS)
    )


def _product_hash(schema_text: str, *, mode: str = "installed") -> Dict[str, str]:
    """The ``$0`` product fingerprint: ``{path: sha256(content-minus-provenance-stamp)}`` over every owned
    file ``render_backend`` emits. Comparing two of these proves the product's real content is unchanged
    (file set + every file's behaviour), independent of the source-fingerprint header."""
    from startd8.backend_codegen import render_backend

    return {
        path: hashlib.sha256(_strip_provenance(content).encode("utf-8")).hexdigest()
        for path, content in render_backend(schema_text, deployment_mode=mode)
    }


def apply_edit_to_contract(schema_text: str, edit: ReviseEdit) -> Optional[str]:
    """Apply a revise edit to the contract text: replace the FIRST occurrence of ``edit.before`` with
    ``edit.after``. Returns the revised text, or ``None`` when ``before`` is absent (an inapplicable edit
    — the applier fails safe rather than silently no-op)."""
    if edit.before not in schema_text:
        return None
    return schema_text.replace(edit.before, edit.after, 1)


def byte_identity_guard(schema_text: str, edit: ReviseEdit, *, mode: str = "installed") -> Callable[[], bool]:
    """FR-2 — a REAL byte-identity guard: applies ``edit`` to the contract, regenerates the ``$0`` product,
    and returns ``True`` iff the product is unchanged. An inapplicable edit or any generation error →
    ``False`` (fail-closed). Reuses ``render_backend`` — no parallel generation path (Mottainai)."""

    def guard() -> bool:
        try:
            revised = apply_edit_to_contract(schema_text, edit)
            if revised is None or revised == schema_text:
                return False  # inapplicable / no-op edit can't be proven → fail-closed to human
            return _product_hash(schema_text, mode=mode) == _product_hash(revised, mode=mode)
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
    mode: str = "installed",
) -> Optional[ReviseAudit]:
    """FR-3/FR-4 — run the revise THROUGH REQ-21's ``auto_apply_revise`` with the real FR-2 guard.

    Returns a :class:`ReviseAudit` when the edit is auto-applied (tier ``auto`` AND the guard proves the
    product unchanged); ``None`` when downgraded to ``human`` (wrong tier, or the guard sees a diff/error).
    The contract file is written ONLY on an auto-apply and only when ``dry_run`` is False — so a downgraded
    revise leaves the working tree byte-identical to before (restore-by-never-writing, FR-4)."""
    schema_path = Path(schema_path)
    schema_text = schema_path.read_text(encoding="utf-8")
    guard = byte_identity_guard(schema_text, edit, mode=mode)
    audit = auto_apply_revise(lesson, elig, guard, timestamp=timestamp, revert_ref=revert_ref)
    if audit is None:
        return None                                        # human — contract untouched
    if not dry_run:
        revised = apply_edit_to_contract(schema_text, edit)
        if revised is not None:                            # (guard already proved it applies + is identical)
            schema_path.write_text(revised, encoding="utf-8")
    return audit
