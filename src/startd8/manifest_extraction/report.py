"""Extraction report emission (FR-WPI-3) — JSON + markdown review form (FR-J2).

Identity + canonical form (CRP R1): entries sorted by ``(manifest, value_path)``; structured
source locators; **byte-stable** across identical-input runs (no timestamps in the JSON body —
audit metadata is the consumer's concern, mirroring the wireframe's ``_meta`` rule).
"""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import Dict, List

from .models import ExtractionRecord, ExtractionResult, Status


def report_to_json(result: ExtractionResult) -> str:
    body = {
        "grammar_version": result.grammar_version,
        "source_docs": dict(sorted(result.source_docs.items())),
        "counts": {
            Status.EXTRACTED: len(result.by_status(Status.EXTRACTED)),
            Status.DEFAULTED: len(result.by_status(Status.DEFAULTED)),
            Status.NOT_EXTRACTED: len(result.by_status(Status.NOT_EXTRACTED)),
        },
        "manifests_emitted": sorted(result.manifests),
        "records": [_record_dict(r) for r in result.sorted_records()],
        "contract_diff": list(result.contract_diff),
    }
    return json.dumps(body, sort_keys=True, indent=2, ensure_ascii=False) + "\n"


def _record_dict(record: ExtractionRecord) -> dict:
    d = {k: v for k, v in asdict(record).items() if v is not None}
    if "source" in d:
        d["source"] = {k: list(v) if isinstance(v, tuple) else v
                       for k, v in d["source"].items() if v is not None}
    return d


def report_to_markdown(result: ExtractionResult) -> str:
    """The human review form the business walkthrough reads (FR-J2)."""
    lines: List[str] = ["# Manifest Extraction Report", ""]
    counts = {s: len(result.by_status(s)) for s in
              (Status.EXTRACTED, Status.DEFAULTED, Status.NOT_EXTRACTED)}
    lines.append(
        f"**{counts[Status.EXTRACTED]} extracted · {counts[Status.DEFAULTED]} defaulted · "
        f"{counts[Status.NOT_EXTRACTED]} not extracted** — grammar `{result.grammar_version}`"
    )
    lines.append("")
    by_manifest: Dict[str, List[ExtractionRecord]] = {}
    for r in result.sorted_records():
        by_manifest.setdefault(r.manifest, []).append(r)
    for manifest in sorted(by_manifest):
        emitted = " (emitted)" if manifest in result.manifests else ""
        lines.append(f"## {manifest}{emitted}")
        lines.append("")
        lines.append("| Value | Status | Detail | Source |")
        lines.append("|---|---|---|---|")
        for r in by_manifest[manifest]:
            detail = r.value or r.reason or ""
            src = ""
            if r.source:
                src = " › ".join(r.source.heading_path) or r.source.doc
                if r.source.row_index is not None:
                    src += f" (row {r.source.row_index})"
            lines.append(f"| `{r.value_path}` | {r.status} | {detail} | {src} |")
        lines.append("")
    if result.contract_diff:
        lines.append("## Contract diff (docs vs live schema.prisma — FR-WPI-8 DIFF mode)")
        lines.append("")
        for d in result.contract_diff:
            lines.append(f"- {d}")
        lines.append("")
    else:
        lines.append("*Contract diff: clean (docs ↔ live schema agree).*")
        lines.append("")
    return "\n".join(lines)
