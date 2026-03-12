"""Plan ingestion contract extraction and enrichment helpers.

Extracted from plan_ingestion_workflow.py (AC-R2) to reduce file size.
All symbols are re-exported from plan_ingestion_workflow.py for backward compatibility.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from ...logging_config import get_logger
from .plan_ingestion_models import ParsedFeature

logger = get_logger(__name__)

# Requirement ID pattern — shared with plan_ingestion_workflow.py
_REQ_ID_PATTERN = re.compile(r"\b(?:REQ|FR|NFR|R)[-_]?\d+\b", re.IGNORECASE)


def _extract_implementation_contracts(raw_text: str) -> Dict[str, str]:
    """Deterministic extraction of Implementation Contract sections from plan markdown.

    Scans the plan for ``### F-NNN:`` headings and, within each feature section,
    extracts the block between ``**Implementation contract:**`` and the next bold
    field (``**...**``), horizontal rule (``---``), or next feature heading.

    Returns a mapping of ``feature_id → contract_text`` (e.g. ``{"F-001": "..."}``.
    Features without an Implementation Contract section are omitted from the dict.
    """
    # Split plan into per-feature chunks keyed by feature ID.
    _FEATURE_HEADING = re.compile(r"^###\s+(F-\d{3}):", re.MULTILINE)
    splits = _FEATURE_HEADING.split(raw_text)
    # splits alternates: [preamble, "F-001", body1, "F-002", body2, ...]
    contracts: Dict[str, str] = {}
    for i in range(1, len(splits) - 1, 2):
        fid = splits[i]
        body = splits[i + 1]

        # Find the Implementation Contract block within this feature section.
        contract_start = body.find("**Implementation contract:**")
        if contract_start == -1:
            continue

        contract_body = body[contract_start + len("**Implementation contract:**"):]

        # End at the next bold field, horizontal rule, or end of section.
        end_match = re.search(
            r"^(?:\*\*(?:Dependencies|Estimated LOC|Note|Depends on|Satisfies|Output files|Description).*?\*\*|---)",
            contract_body,
            re.MULTILINE,
        )
        if end_match:
            contract_body = contract_body[: end_match.start()]

        contract_text = contract_body.strip()
        if contract_text:
            contracts[fid] = contract_text

    return contracts


def _scope_contract_to_files(
    contract_text: str,
    target_files: List[str],
) -> str:
    """Extract only the sections of a contract relevant to *target_files*.

    Handles three contract formats:

    1. **Backtick filename headers** — e.g. `` `email_server.py` (201 lines): ``
       followed by a body.  Matched by suffix against *target_files*.
    2. **Bold service-name bullets** — e.g. ``- **emailservice:** sets ...``
       found under a "Per-service specifics:" heading.  Matched by extracting
       the service directory from *target_files*.
    3. **Backtick path headers with shared basenames** — e.g.
       `` `emailservice/requirements.in`: `` where all sub-features share the
       same basename.  Matched by path suffix rather than bare basename.

    For a sub-feature targeting only ``email_client.py``, this function
    returns only the ``email_client.py`` section.  If no file-specific
    sections are found, the full contract is returned (safe fallback).

    QP-2 + QP-4 + QP-5: prevents sub-features from inheriting the full
    parent contract, reducing token waste and cross-contamination.
    """
    if not target_files:
        return contract_text

    # --- Strategy 1: backtick-wrapped filename headers ---
    # Pattern matches lines like:  `some_file.py` (NNN lines):
    #                           or: `some_file.py`:
    #                           or: `dir/some_file.ext`:
    _FILE_HEADER = re.compile(
        r"^(`[^`]+\.\w+`)\s*(?:\([^)]*\)\s*)?:\s*$", re.MULTILINE,
    )
    parts = _FILE_HEADER.split(contract_text)
    # parts: [preamble, "`file1.py`", body1, "`file2.py`", body2, ...]

    if len(parts) >= 3:
        scoped_sections: List[str] = []
        preamble = parts[0].strip()

        for i in range(1, len(parts) - 1, 2):
            header_raw = parts[i]             # e.g. "`email_client.py`"
            body = parts[i + 1]
            # Strip backticks for matching.
            header_path = header_raw.strip("`").strip()
            if _path_matches_targets(header_path, target_files):
                scoped_sections.append(f"{header_raw}:{body.rstrip()}")

        if scoped_sections:
            result = (
                preamble + "\n\n" + "\n\n".join(scoped_sections)
                if preamble
                else "\n\n".join(scoped_sections)
            )
            return result.strip()

        # Backtick sections found but none matched — fall through to
        # strategy 2 rather than returning everything.

    # --- Strategy 2: bold service-name bullets ---
    # Handles: "Per-service specifics:\n- **emailservice:** ..."
    scoped = _scope_by_service_bullets(contract_text, target_files)
    if scoped is not None:
        return scoped

    # No scoping matched — return full contract.
    return contract_text


def _path_matches_targets(header_path: str, target_files: List[str]) -> bool:
    """Check if a contract section header path matches any target file.

    Uses suffix matching so ``emailservice/requirements.in`` matches
    ``src/emailservice/requirements.in``.  Falls back to basename matching
    only when the header is a bare filename (no directory component),
    avoiding false positives when multiple sections share the same basename
    (e.g. ``requirements.in``).
    """
    header_norm = header_path.replace("\\", "/")
    header_has_dir = "/" in header_norm
    for tf in target_files:
        tf_norm = tf.replace("\\", "/")
        # Exact match, or header is a suffix of the target path.
        if tf_norm == header_norm or tf_norm.endswith("/" + header_norm):
            return True
        # Basename match only for bare filenames (no directory component).
        if not header_has_dir and os.path.basename(tf_norm) == header_norm:
            return True
    return False


def _scope_by_service_bullets(
    contract_text: str,
    target_files: List[str],
) -> Optional[str]:
    """Scope a contract using bold service-name bullet items.

    Detects the pattern::

        Per-service specifics:
        - **emailservice:** sets ENABLE_PROFILER=1 ...
        - **recommendationservice:** sets PORT=8080 ...

    Extracts the preamble (everything before the bullet block) plus only
    the bullet(s) whose bold name matches a directory component in
    *target_files*.  Returns ``None`` if the pattern is not found.
    """
    # Extract service directory names from target file paths.
    # e.g. "src/emailservice/Dockerfile" → "emailservice"
    service_dirs: Set[str] = set()
    for tf in target_files:
        parts = tf.replace("\\", "/").split("/")
        # Take the directory component just before the filename.
        if len(parts) >= 2:
            service_dirs.add(parts[-2].lower())

    if not service_dirs:
        return None

    # Find bold bullet items: "- **name:** ..."
    _BOLD_BULLET = re.compile(r"^- \*\*(\w+):\*\*\s+", re.MULTILINE)
    bullets = list(_BOLD_BULLET.finditer(contract_text))
    if not bullets:
        return None

    # Split contract into preamble + per-bullet sections.
    preamble = contract_text[: bullets[0].start()].rstrip()
    matched_bullets: List[str] = []
    for idx, m in enumerate(bullets):
        name = m.group(1).lower()
        # End of this bullet is the start of the next, or end of text.
        end = bullets[idx + 1].start() if idx + 1 < len(bullets) else len(contract_text)
        if name in service_dirs:
            matched_bullets.append(contract_text[m.start(): end].rstrip())

    if not matched_bullets:
        return None

    return (preamble + "\n" + "\n".join(matched_bullets)).strip()


def _enrich_features_from_plan(
    features: List[ParsedFeature],
    raw_text: str,
) -> int:
    """Enrich ParsedFeature descriptions with Implementation Contract text from the plan.

    For sub-features (suffixed IDs like F-001a), the contract is scoped to
    only the sections relevant to that sub-feature's ``target_files``,
    preventing token waste from duplicating the full parent contract across
    every sub-feature (QP-2 + QP-4).

    Mutates features in place.  Returns the count of features enriched.
    """
    contracts = _extract_implementation_contracts(raw_text)
    if not contracts:
        return 0

    enriched = 0
    for feat in features:
        # PARSE may split multi-file features into sub-features with
        # suffixed IDs (e.g. F-001a, F-001b).  Strip the suffix to
        # match the plan's F-NNN heading.
        base_id = re.sub(r"[a-z]+$", "", feat.feature_id)
        is_sub = base_id != feat.feature_id
        contract = contracts.get(feat.feature_id) or contracts.get(base_id)
        if not contract:
            continue

        # QP-2+QP-4: scope sub-feature contracts to their target files.
        if is_sub and feat.target_files:
            contract = _scope_contract_to_files(contract, feat.target_files)

        # Only enrich if the contract adds meaningful length beyond the
        # existing summary description.
        if len(contract) > len(feat.description or ""):
            feat.description = (
                f"{feat.description}\n\n"
                f"Implementation contract:\n{contract}"
                if feat.description
                else f"Implementation contract:\n{contract}"
            )
            enriched += 1
    return enriched


def _extract_requirement_ids(requirements_text: str) -> List[str]:
    """Extract likely requirement IDs from requirements corpus."""
    found = [m.group(0).upper() for m in _REQ_ID_PATTERN.finditer(requirements_text)]
    if found:
        return sorted(set(found))

    # Synthetic IDs (REQ-LINE-*) never appear in feature text, guaranteeing
    # unmapped status and inflating quality gate metrics.  Return empty
    # list so coverage is computed only from real requirement IDs.
    return []


def _load_requirements_documents(requirements_files: List[str], base_dir: Path) -> Dict[str, str]:
    """Load requirement document content by resolved path."""
    from .plan_ingestion_workflow import _resolve_path

    docs: Dict[str, str] = {}
    for raw in requirements_files:
        resolved = _resolve_path(raw, base_dir)
        if not resolved.exists() or not resolved.is_file():
            continue
        try:
            docs[str(resolved)] = resolved.read_text(encoding="utf-8")
        except OSError:
            continue
    return docs


def _normalize_requirements_hints(
    onboarding: Optional[Dict[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    """Build requirement-hint index keyed by requirement ID."""
    if not isinstance(onboarding, dict):
        return {}
    raw_hints = onboarding.get("requirements_hints")
    if not isinstance(raw_hints, list):
        return {}
    hints: Dict[str, Dict[str, Any]] = {}
    for item in raw_hints:
        if not isinstance(item, dict):
            continue
        rid = item.get("id")
        if not isinstance(rid, str) or not rid.strip():
            continue
        rid_norm = rid.strip().upper()
        hints[rid_norm] = item
    return hints
