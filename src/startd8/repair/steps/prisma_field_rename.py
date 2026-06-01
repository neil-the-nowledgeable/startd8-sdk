"""Repair step: rename invented Prisma field keys (Inc 4, FR-5).

Consumes ``MisnamedFieldDiagnostic``s and rewrites an invented field key to its
nearest real counterpart on the model — **only** when the nearest-match decision
core (FR-3) yields a single high-confidence target, and **only** at the top level
of a ``db.<model>.{create,update,where,upsert,...}({ <payload>: { … } })`` call
site. Anything nested/spread/computed, or with no near-match, is abstained
(left for the LLM-retry path). TS-text-based (brace-matched), not Python AST.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import List, Optional, Tuple

from ...logging_config import get_logger
from ..models import (
    ElementContext,
    MisnamedFieldDiagnostic,
    RepairContext,
    RepairStepResult,
)
from ..name_resolution import best_match
from ._name_repair_common import diagnostic_targets_file, resolve_truth_source
from ._ts_object import find_object_close, top_level_key_spans

logger = get_logger(__name__)

# Prisma payload sub-objects whose top-level keys are model fields.
_PAYLOAD_KEYS = ("where", "data", "create", "update")


class PrismaFieldRenameStep:
    """Rewrite invented Prisma field names to their nearest real counterpart."""

    name: str = "prisma_field_rename"

    def __init__(self, truth_source=None):
        self._truth_source = truth_source

    def __call__(
        self,
        code: str,
        context: RepairContext,
        file_path: Path,
        element_context: Optional[ElementContext] = None,
    ) -> RepairStepResult:
        diags = [
            d
            for d in context.diagnostics
            if isinstance(d, MisnamedFieldDiagnostic)
            and diagnostic_targets_file(d, file_path)
        ]
        if not diags:
            return RepairStepResult(
                self.name, False, code, {"rewrites": [], "abstains": []}
            )

        truth = resolve_truth_source(self._truth_source, context.project_root)
        modified = code
        rewrites: List[dict] = []
        abstains: List[dict] = []

        for d in diags:
            candidates = truth.prisma_fields(d.model)
            decision = best_match(d.field, candidates)
            if not decision.is_rewrite:
                abstains.append(
                    {"field": d.field, "model": d.model, "reason": decision.reason}
                )
                continue
            new_code, changed = _rewrite_field_key(
                modified, d.model, d.field, decision.target
            )
            if changed:
                modified = new_code
                rewrites.append(
                    {
                        "from": d.field,
                        "to": decision.target,
                        "model": d.model,
                        "similarity": round(decision.similarity, 3),
                    }
                )
            else:
                # best_match wanted a rewrite but the key is only nested/spread —
                # bounded matcher could not locate it at top level: abstain.
                abstains.append(
                    {
                        "field": d.field,
                        "model": d.model,
                        "reason": "unbounded_construct",
                    }
                )

        if rewrites:
            logger.info(
                "prisma_field_rename: %d rewrite(s) in %s: %s",
                len(rewrites),
                file_path.name,
                "; ".join(f"{r['from']}->{r['to']}" for r in rewrites),
            )

        return RepairStepResult(
            self.name,
            modified != code,
            modified,
            {"rewrites": rewrites, "abstains": abstains},
        )


def _rewrite_field_key(
    code: str, model: str, field: str, target: str
) -> Tuple[str, bool]:
    """Replace top-level payload key *field* → *target* in ``db.<model>`` calls.

    Only rewrites keys at depth 1 of a ``where``/``data``/``create``/``update``
    payload object. Returns ``(code, False)`` when the field is only present in a
    nested/spread/computed position (the bounded matcher refuses to guess).
    """
    if not field or not target:
        return code, False
    model_lower = model[:1].lower() + model[1:] if model else model
    # Mirror the detector's call-site shape exactly (validators/prisma_usage._CALL_RE):
    # both `db.` and `prisma.` client prefixes, with whitespace tolerated around the
    # dots. A narrower pattern would silently abstain on call sites the scan flagged.
    call_re = re.compile(
        r"\b(?:db|prisma)\s*\.\s*" + re.escape(model_lower) + r"\s*\.\s*\w+\s*\("
    )

    edits: List[Tuple[int, int]] = []  # (start, end) of key identifiers to replace
    for m in call_re.finditer(code):
        paren = code.find("(", m.end() - 1)
        if paren == -1:
            continue
        br = code.find("{", paren)
        if br == -1 or code[paren + 1 : br].strip():
            continue  # arg is not an inline object literal
        arg_close = find_object_close(code, br)
        if arg_close == -1:
            continue
        for pkey, _ps, pe in top_level_key_spans(code, br, arg_close):
            if pkey not in _PAYLOAD_KEYS:
                continue
            vbr = code.find("{", pe)
            if vbr == -1 or vbr > arg_close:
                continue
            vclose = find_object_close(code, vbr)
            if vclose == -1:
                continue
            for fkey, fs, fe in top_level_key_spans(code, vbr, vclose):
                if fkey == field:
                    edits.append((fs, fe))

    if not edits:
        return code, False
    out = code
    for fs, fe in sorted(edits, reverse=True):
        out = out[:fs] + target + out[fe:]
    return out, True
