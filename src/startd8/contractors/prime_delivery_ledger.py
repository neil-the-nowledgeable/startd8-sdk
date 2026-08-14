"""Project a dossier-shaped delivery ledger from prime postmortem + traceability.

This is a **projection emitter**, not a sync conductor. It derives
``delivery.work_items`` / ``delivery.evidence`` for the twin-sync reconciler
(``dev-os/scripts/reconcile_lives_evidence.py``) from artifacts the Prime chain
already produces. It never writes FR ``Lives:``, never feeds draft-time PASS into
evidence, and never invents a merge SHA.

Cite: ``docs/design/prime/REQ-PRIME-DELIVERY-LEDGER.md``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

import yaml

_GIT_SHA = re.compile(r"^[0-9a-f]{40}$", re.IGNORECASE)
_AUTO_SATISFIED = "auto-satisfied"


@dataclass(frozen=True)
class EmitSkip:
    """One honest skip — never rounded into a fake locator."""

    reason: str
    path: str | None = None
    task_id: str | None = None


@dataclass
class EmitResult:
    """Outcome of a ledger projection."""

    ledger: dict[str, Any]
    output_path: Path | None
    skips: list[EmitSkip] = field(default_factory=list)
    merge_sha: str | None = None

    @property
    def work_item_count(self) -> int:
        return len((self.ledger.get("delivery") or {}).get("work_items") or [])

    @property
    def evidence_count(self) -> int:
        return len((self.ledger.get("delivery") or {}).get("evidence") or [])


def _load_json(path_or_data: Path | Mapping[str, Any], *, label: str) -> dict[str, Any]:
    if isinstance(path_or_data, Mapping):
        return dict(path_or_data)
    path = Path(path_or_data)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise SystemExit(f"{label}: cannot read {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise SystemExit(f"{label}: invalid JSON in {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise SystemExit(f"{label}: {path} must be a JSON object")
    return raw


def _normalize_repo_relative(
    path: str,
    *,
    project_root: Path,
    target_hint: str | None = None,
) -> str | None:
    """Return a repo-relative posix path under ``project_root``, or None."""
    root = project_root.resolve()
    hint = (target_hint or "").strip().replace("\\", "/")
    if hint and not hint.startswith("/") and ".." not in Path(hint).parts:
        return Path(hint).as_posix()

    raw = (path or "").strip().replace("\\", "/")
    if not raw:
        return None
    candidate = Path(raw)
    if candidate.is_absolute():
        try:
            rel = candidate.resolve().relative_to(root)
        except ValueError:
            # Absolute path outside project_root — try suffix against target_hint or
            # any path segment that looks like a repo-relative file under root.
            if hint:
                return Path(hint).as_posix()
            parts = candidate.parts
            for i, part in enumerate(parts):
                if part in {"generated", "FIXTURE_PROJECT_ROOT"} and i + 1 < len(parts):
                    trial = Path(*parts[i + 1 :])
                    if (root / trial).is_file() or trial.as_posix().startswith("app/"):
                        return trial.as_posix()
            return None
        return rel.as_posix()
    if ".." in candidate.parts:
        return None
    return candidate.as_posix()


def _blob_at(repo: Path, merge_sha: str, relpath: str) -> bytes | None:
    try:
        proc = subprocess.run(
            ["git", "cat-file", "blob", f"{merge_sha}:{relpath}"],
            cwd=repo,
            capture_output=True,
            check=False,
        )
    except OSError:
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout


def _evidence_id(relpath: str) -> str:
    slug = re.sub(r"[^A-Z0-9]+", "-", relpath.upper()).strip("-")
    return f"EVID-{slug}"[:80]


def _mapped_task_satisfies(
    traceability: Mapping[str, Any],
) -> dict[str, set[str]]:
    """task_id → set of requirement_ids (excludes auto-satisfied)."""
    out: dict[str, set[str]] = {}
    for row in traceability.get("requirement_mappings") or []:
        if not isinstance(row, Mapping):
            continue
        if str(row.get("status") or "").lower() == _AUTO_SATISFIED:
            continue
        req_id = str(row.get("requirement_id") or "").strip()
        if not req_id:
            continue
        for task_id in row.get("task_ids") or []:
            tid = str(task_id).strip()
            if not tid or tid.startswith("__pipeline_artifact:"):
                continue
            out.setdefault(tid, set()).add(req_id)
    return out


def emit_delivery_ledger(
    *,
    postmortem: Path | Mapping[str, Any],
    traceability: Path | Mapping[str, Any],
    project_root: Path,
    merge_sha: str | None,
    output_path: Path | None = None,
) -> EmitResult:
    """Emit a dossier-shaped ``delivery:`` fragment (FR-1…FR-5).

    ``merge_sha`` of ``None`` / ``\"unknown\"`` / non-40-hex yields an empty evidence
    list with loud skips (FR-4). Disk-quality / PASS fields are ignored for evidence.
    """
    pm = _load_json(postmortem, label="postmortem")
    tr = _load_json(traceability, label="traceability")
    root = Path(project_root).resolve()
    if not root.is_dir():
        raise SystemExit(f"project_root is not a directory: {root}")

    skips: list[EmitSkip] = []
    sha = (merge_sha or "").strip().lower()
    if sha in {"", "unknown", "none"}:
        effective_sha: str | None = None
        skips.append(EmitSkip(reason="merge_sha missing or unknown — no evidence rows emitted"))
    elif not _GIT_SHA.fullmatch(sha):
        raise SystemExit(f"merge_sha must be 40-hex or unknown, got {merge_sha!r}")
    else:
        effective_sha = sha

    task_satisfies = _mapped_task_satisfies(tr)
    work_items: dict[str, dict[str, Any]] = {
        tid: {
            "id": tid,
            "status": "done",
            "satisfies": sorted(reqs),
            "evidence": [],
        }
        for tid, reqs in sorted(task_satisfies.items())
    }

    evidence_by_id: dict[str, dict[str, Any]] = {}
    # feature_id / task_id → files produced (postmortem features use feature_id = PI-*)
    features = pm.get("features") or []
    if not isinstance(features, list):
        raise SystemExit("postmortem.features must be a list")

    for feat in features:
        if not isinstance(feat, Mapping):
            continue
        task_id = str(feat.get("feature_id") or feat.get("task_id") or "").strip()
        if not task_id:
            skips.append(EmitSkip(reason="feature missing feature_id/task_id"))
            continue
        if task_id not in work_items:
            # Mapped tasks only — unmapped features do not invent WorkItems.
            skips.append(
                EmitSkip(
                    reason="feature task not in non-auto requirement_mappings",
                    task_id=task_id,
                )
            )
            continue

        targets: Sequence[Any] = feat.get("target_files") or ()
        generated: Sequence[Any] = feat.get("generated_files") or ()
        pairs: list[tuple[str | None, str | None]] = []
        if targets:
            for i, tf in enumerate(targets):
                gf = generated[i] if i < len(generated) else None
                pairs.append((str(gf) if gf else None, str(tf) if tf else None))
        elif generated:
            for gf in generated:
                pairs.append((str(gf), None))
        else:
            skips.append(
                EmitSkip(reason="feature has no generated_files/target_files", task_id=task_id)
            )
            continue

        for gen_path, target_hint in pairs:
            rel = _normalize_repo_relative(
                gen_path or "",
                project_root=root,
                target_hint=target_hint,
            )
            if not rel:
                skips.append(
                    EmitSkip(
                        reason="path could not be normalized under project_root",
                        path=gen_path or target_hint,
                        task_id=task_id,
                    )
                )
                continue
            if effective_sha is None:
                skips.append(
                    EmitSkip(
                        reason="skipped evidence — no merge_sha",
                        path=rel,
                        task_id=task_id,
                    )
                )
                continue
            blob = _blob_at(root, effective_sha, rel)
            if blob is None:
                skips.append(
                    EmitSkip(
                        reason="blob missing at merge_sha:path",
                        path=f"{effective_sha}:{rel}",
                        task_id=task_id,
                    )
                )
                continue
            digest = hashlib.sha256(blob).hexdigest()
            evid_id = _evidence_id(rel)
            if evid_id not in evidence_by_id:
                evidence_by_id[evid_id] = {
                    "id": evid_id,
                    "kind": "generated-source",
                    "locator": f"git:{effective_sha}:{rel}",
                    "sha256": digest,
                    "provenance": "prime-delivery-ledger",
                }
            refs: list[str] = work_items[task_id]["evidence"]
            if evid_id not in refs:
                refs.append(evid_id)

    ledger = {
        "schema": "startd8.prime-delivery-ledger/v0.1",
        "delivery": {
            "evidence": sorted(evidence_by_id.values(), key=lambda e: e["id"]),
            "work_items": [work_items[k] for k in sorted(work_items)],
        },
    }

    written: Path | None = None
    if output_path is not None:
        out = Path(output_path)
        if out.name == "dossier.yaml":
            raise SystemExit(
                "refusing to write dossier.yaml — emit a delivery-ledger beside .startd8/ (FR-5)"
            )
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(yaml.safe_dump(ledger, sort_keys=False), encoding="utf-8")
        written = out

    return EmitResult(
        ledger=ledger,
        output_path=written,
        skips=skips,
        merge_sha=effective_sha,
    )


def default_output_path(project_root: Path) -> Path:
    return Path(project_root).resolve() / ".startd8" / "delivery-ledger.yaml"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Emit a dossier-shaped delivery ledger from prime postmortem + traceability."
    )
    parser.add_argument("--postmortem", type=Path, required=True)
    parser.add_argument("--traceability", type=Path, required=True)
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument(
        "--merge-sha",
        default="unknown",
        help="40-hex merge commit of the generated project, or 'unknown' to skip evidence",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output path (default: <project-root>/.startd8/delivery-ledger.yaml)",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)
    out = args.out or default_output_path(args.project_root)
    result = emit_delivery_ledger(
        postmortem=args.postmortem,
        traceability=args.traceability,
        project_root=args.project_root,
        merge_sha=args.merge_sha,
        output_path=out,
    )
    for skip in result.skips:
        parts = [skip.reason]
        if skip.path:
            parts.append(f"path={skip.path}")
        if skip.task_id:
            parts.append(f"task={skip.task_id}")
        print(f"skip: {'; '.join(parts)}", file=sys.stderr)
    print(
        f"wrote {result.output_path} "
        f"({result.work_item_count} work_items, {result.evidence_count} evidence)",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
