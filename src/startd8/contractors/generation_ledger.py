"""Prime-Project Generation Ledger — the cross-project, per-run record (REQ-prime-project-generation-ledger).

The empty cell the ledger family predicted (see
``docs/design/prime-generation-ledger/INSTANTIATION_prime-project-generation-ledger.md``): a durable
record of **every project the Prime Contractor works on and every run per project** — what / where /
when / cost / status / where-the-artifacts-are — plus a **cross-project index**.

It is an *extension* of the seed-centric ``batch_postmortem.py`` (NR-2): each run row is **auto-derived
from the run's real artifacts** (``generation-manifest.json`` joined with the sibling
``batch-ledger.json``), never hand-maintained — the trust-model improvement over the session ledger.
The per-project file (``projects/<project-id>.json``) is authoritative for run history; the
``index.json`` is a thin cross-project roster that *points at* each project file.

Home: ``$STARTD8_HOME/generation-ledger/`` (default ``~/.startd8/generation-ledger/``), beside the
existing cross-project ``costs.db``. Overridable per call (``home=``) and via ``$STARTD8_HOME`` so tests
never touch the real HOME. All writes are atomic (``.tmp`` + rename), mirroring ``save_ledger``.

Scope here is the I1–I3 data spine (record + persist + index). The CLI (FR-4), the liveness oracle
(FR-6), and the postmortem hook (FR-5) build on this module.
"""

from __future__ import annotations

import dataclasses
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from startd8.contractors.batch_postmortem import resolve_project_identity
from startd8.logging_config import get_logger

logger = get_logger(__name__)

SCHEMA = "startd8.prime-generation-ledger/v0.1"
INDEX_SCHEMA = "startd8.prime-generation-ledger.index/v0.1"
TRUST_MODEL = "auto-derived-from-run-artifacts + resolve-check oracle"

# Conventional run-artifact locations, relative to the project root. ``{run}`` = the run id. The map is
# emitted whole (where each artifact *would* live); the FR-6 oracle later checks which actually resolve.
_ARTIFACT_LAYOUT: Dict[str, str] = {
    "generation_manifest": ".startd8/generation-manifest.json",
    "prime_postmortem_report": ".startd8/prime-postmortem-report.json",
    "prime_postmortem_summary": ".startd8/prime-postmortem-summary.md",
    "kaizen_metrics": ".startd8/kaizen-metrics.json",
    "forward_manifest": ".startd8/forward-manifest.json",
    "batch_ledger": ".cap-dev-pipe/pipeline-output/batch-ledger.json",
    "run_dir": ".cap-dev-pipe/pipeline-output/{run}/",
    "run_provenance": ".cap-dev-pipe/pipeline-output/{run}/run-provenance.json",
    "artifact_manifest": ".cap-dev-pipe/pipeline-output/{run}/{run}-artifact-manifest.yaml",
    "project_context": ".cap-dev-pipe/pipeline-output/{run}/project-context.yaml",
}


# ---------------------------------------------------------------------------
# Home / paths
# ---------------------------------------------------------------------------


def ledger_dir(home: Optional[str] = None) -> Path:
    """The generation-ledger directory. ``home`` overrides ``$STARTD8_HOME`` overrides ``~/.startd8``."""
    base = home or os.environ.get("STARTD8_HOME") or str(Path.home() / ".startd8")
    return Path(base) / "generation-ledger"


def project_ledger_path(project_id: str, home: Optional[str] = None) -> Path:
    return ledger_dir(home) / "projects" / f"{project_id}.json"


def index_path(home: Optional[str] = None) -> Path:
    return ledger_dir(home) / "index.json"


def _atomic_write_json(path: Path, data: Any) -> None:
    """Atomic write (``.tmp`` + rename), mirroring ``batch_postmortem.save_ledger``."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(str(path) + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    tmp.replace(path)


# ---------------------------------------------------------------------------
# Per-project ledger
# ---------------------------------------------------------------------------


@dataclasses.dataclass
class ProjectGenerationLedger:
    """One project's cross-run generation history (persisted at ``projects/<project-id>.json``)."""

    project_id: str
    project_path: str
    first_seen: str = ""
    last_run_at: str = ""
    batches: List[Dict[str, Any]] = dataclasses.field(default_factory=list)
    schema: str = SCHEMA
    trust_model: str = TRUST_MODEL

    # -- run/batch upsert ---------------------------------------------------

    def upsert_run(self, batch_meta: Dict[str, Any], run_row: Dict[str, Any]) -> None:
        """Insert-or-replace a run row within its batch, keyed by ``(batch_id, run_id)`` (F-4)."""
        batch_id = batch_meta.get("batch_id", "")
        batch = next((b for b in self.batches if b.get("batch_id") == batch_id), None)
        if batch is None:
            batch = {**batch_meta, "runs": []}
            self.batches.append(batch)
        else:  # keep batch metadata fresh, preserve the runs list
            runs = batch.get("runs", [])
            batch.update(batch_meta)
            batch["runs"] = runs
        batch["runs"] = [
            r for r in batch.get("runs", []) if r.get("run_id") != run_row.get("run_id")
        ]
        batch["runs"].append(run_row)
        self._refresh_run_bounds()

    def _refresh_run_bounds(self) -> None:
        stamps = [
            r.get("generated_at", "")
            for b in self.batches
            for r in b.get("runs", [])
            if r.get("generated_at")
        ]
        if stamps:
            self.first_seen = min(stamps)
            self.last_run_at = max(stamps)

    # -- rollup -------------------------------------------------------------

    def _all_runs(self) -> List[Dict[str, Any]]:
        return [r for b in self.batches for r in b.get("runs", [])]

    def cumulative(self) -> Dict[str, Any]:
        runs = self._all_runs()
        latest = max(runs, key=lambda r: r.get("generated_at", ""), default=None)
        latest_batch = next(
            (b for b in self.batches if latest in b.get("runs", [])), None
        )
        features_total = (latest_batch or {}).get("total_tasks", 0) if latest else 0
        passed = (latest or {}).get("features_passed", 0)
        return {
            "runs": len(runs),
            "total_cost_usd": sum(r.get("cost_usd", 0.0) for r in runs),
            "total_input_tokens": sum(r.get("input_tokens", 0) for r in runs),
            "total_output_tokens": sum(r.get("output_tokens", 0) for r in runs),
            "features_passed": passed,
            "features_total_in_batch": features_total,
            "status": (
                "COMPLETE"
                if features_total and passed >= features_total
                else "IN_PROGRESS"
            ),
        }

    # -- (de)serialize ------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema": self.schema,
            "trust_model": self.trust_model,
            "project": {
                "project_id": self.project_id,
                "project_path": self.project_path,
                "first_seen": self.first_seen,
                "last_run_at": self.last_run_at,
                "cumulative": self.cumulative(),
            },
            "batches": self.batches,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ProjectGenerationLedger":
        proj = data.get("project", {})
        return cls(
            project_id=proj.get("project_id", ""),
            project_path=proj.get("project_path", ""),
            first_seen=proj.get("first_seen", ""),
            last_run_at=proj.get("last_run_at", ""),
            batches=data.get("batches", []),
            schema=data.get("schema", SCHEMA),
            trust_model=data.get("trust_model", TRUST_MODEL),
        )


def load_project_ledger(
    project_id: str, project_path: str = "", home: Optional[str] = None
) -> ProjectGenerationLedger:
    """Load a project's ledger, or a fresh empty one when none exists yet."""
    path = project_ledger_path(project_id, home)
    if path.is_file():
        try:
            return ProjectGenerationLedger.from_dict(
                json.loads(path.read_text(encoding="utf-8"))
            )
        except (json.JSONDecodeError, OSError):
            logger.warning("Unreadable project ledger %s — starting fresh", path)
    return ProjectGenerationLedger(project_id=project_id, project_path=project_path)


def save_project_ledger(
    ledger: ProjectGenerationLedger, home: Optional[str] = None
) -> Path:
    path = project_ledger_path(ledger.project_id, home)
    _atomic_write_json(path, ledger.to_dict())
    logger.info("Project generation ledger saved: %s", path)
    return path


# ---------------------------------------------------------------------------
# Cross-project index
# ---------------------------------------------------------------------------


@dataclasses.dataclass
class GenerationLedgerIndex:
    """The cross-project roster (``index.json``) — one thin row per project, pointing at its file."""

    projects: List[Dict[str, Any]] = dataclasses.field(default_factory=list)
    schema: str = INDEX_SCHEMA

    def upsert(
        self, ledger: ProjectGenerationLedger, home: Optional[str] = None
    ) -> None:
        cum = ledger.cumulative()
        row = {
            "project_id": ledger.project_id,
            "project_path": ledger.project_path,
            "ledger_ref": str(project_ledger_path(ledger.project_id, home)),
            "runs": cum["runs"],
            "batches": len(ledger.batches),
            "last_run_at": ledger.last_run_at,
            "cumulative_cost_usd": cum["total_cost_usd"],
            "status": cum["status"],
            "features_passed": cum["features_passed"],
            "features_total": cum["features_total_in_batch"],
        }
        self.projects = [
            p for p in self.projects if p.get("project_id") != ledger.project_id
        ]
        self.projects.append(row)
        self.projects.sort(key=lambda p: p.get("project_id", ""))

    def to_dict(self) -> Dict[str, Any]:
        return {"schema": self.schema, "projects": self.projects}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GenerationLedgerIndex":
        return cls(
            projects=data.get("projects", []),
            schema=data.get("schema", INDEX_SCHEMA),
        )


def load_index(home: Optional[str] = None) -> GenerationLedgerIndex:
    path = index_path(home)
    if path.is_file():
        try:
            return GenerationLedgerIndex.from_dict(
                json.loads(path.read_text(encoding="utf-8"))
            )
        except (json.JSONDecodeError, OSError):
            logger.warning(
                "Unreadable generation-ledger index %s — starting fresh", path
            )
    return GenerationLedgerIndex()


def save_index(index: GenerationLedgerIndex, home: Optional[str] = None) -> Path:
    path = index_path(home)
    _atomic_write_json(path, index.to_dict())
    return path


# ---------------------------------------------------------------------------
# Auto-derive a run row from real artifacts (FR-3)
# ---------------------------------------------------------------------------


def _artifact_map(project_root: Path, run_id: str) -> Dict[str, Optional[str]]:
    """The conventional artifact map for a run (absolute paths). ``delivery_ledger`` is reserved null
    (deferred cell C4)."""
    out: Dict[str, Optional[str]] = {
        role: str(project_root / rel.format(run=run_id))
        for role, rel in _ARTIFACT_LAYOUT.items()
    }
    out["delivery_ledger"] = None  # reserved (NR-3); portal-v2 has none
    return out


def build_run_row(
    project_root: Path,
    manifest: Dict[str, Any],
    run_snapshot: Optional[Dict[str, Any]],
    run_id: str,
) -> Dict[str, Any]:
    """Join a ``generation-manifest.json`` with its batch ``RunSnapshot`` into one run row (I3 core, pure).

    The model-mix / cost-by-provider rollup is the cross-artifact join (F-3) the family previously made
    nobody do: the per-feature ``provider``/``model`` live only in the manifest.
    """
    features_raw = manifest.get("features", {}) or {}
    features: List[Dict[str, Any]] = []
    cost_by_provider: Dict[str, float] = {}
    model_mix: Dict[str, int] = {}
    for fid, f in features_raw.items():
        provider = f.get("provider", "") or ""
        model = f.get("model", "") or ""
        cost = f.get("cost_usd", 0.0) or 0.0
        features.append(
            {
                "id": fid,
                "name": (f.get("name", "") or "").rstrip(" —").rstrip(),
                "success": bool(f.get("success", False)),
                "cost_usd": cost,
                "model": model,
                "provider": provider,
            }
        )
        cost_by_provider[provider] = cost_by_provider.get(provider, 0.0) + cost
        model_mix[model] = model_mix.get(model, 0) + 1

    snap = run_snapshot or {}
    attempted = snap.get("tasks_attempted", len(features))
    passed = snap.get("tasks_passed", sum(1 for f in features if f["success"]))
    failed = snap.get("tasks_failed", attempted - passed)
    verdict = (
        "PASS" if (attempted and failed == 0) else ("PARTIAL" if passed else "FAIL")
    )

    return {
        "run_id": run_id,
        "generated_at": manifest.get("generated_at", ""),
        "verdict": verdict,
        "features_attempted": attempted,
        "features_passed": passed,
        "features_failed": failed,
        "force_regenerated_count": snap.get("force_regenerated_count", 0),
        "remaining_in_batch": snap.get("remaining", 0),
        "cost_usd": manifest.get("total_cost_usd", 0.0),
        "input_tokens": manifest.get("total_input_tokens", 0),
        "output_tokens": manifest.get("total_output_tokens", 0),
        "model_time_ms": manifest.get("total_model_time_ms", 0.0),
        "cost_by_provider": cost_by_provider,
        "model_mix": model_mix,
        "features": features,
        "artifacts": _artifact_map(project_root, run_id),
    }


def find_project_root(start: str) -> Optional[Path]:
    """Walk up from *start* to the nearest ancestor holding ``.startd8/generation-manifest.json`` (I6).

    Lets the postmortem hook resolve the project root robustly from a run/ledger path without fragile
    parent-counting. Returns ``None`` when no generated project is found on the way up.
    """
    p = Path(start).resolve()
    for cand in [p, *p.parents]:
        if (cand / ".startd8" / "generation-manifest.json").is_file():
            return cand
    return None


@dataclasses.dataclass
class LedgerFinding:
    """One advisory finding from the liveness oracle (FR-6)."""

    project_id: str
    run_id: str
    kind: str  # "PHANTOM" (a cited artifact path is gone) | "DRIFT" (recorded cost != source)
    detail: str


def verify_project(ledger: ProjectGenerationLedger) -> List[LedgerFinding]:
    """Re-check a project's recorded runs against reality (FR-6, advisory, never mutating).

    PHANTOM: a non-null ``artifacts{}`` path no longer resolves on disk.
    DRIFT: the recorded ``cost_usd`` no longer matches the run's ``generation-manifest.json``.
    """
    findings: List[LedgerFinding] = []
    for batch in ledger.batches:
        for run in batch.get("runs", []):
            rid = run.get("run_id", "")
            artifacts = run.get("artifacts", {}) or {}
            for role, path in artifacts.items():
                if path is None:
                    continue
                if not Path(path).exists():
                    findings.append(
                        LedgerFinding(
                            ledger.project_id, rid, "PHANTOM", f"{role}: {path}"
                        )
                    )
            gm = artifacts.get("generation_manifest")
            if gm and Path(gm).is_file():
                try:
                    manifest = json.loads(Path(gm).read_text(encoding="utf-8"))
                except (json.JSONDecodeError, OSError):
                    continue
                recorded = run.get("cost_usd")
                source = manifest.get("total_cost_usd")
                if recorded != source:
                    findings.append(
                        LedgerFinding(
                            ledger.project_id,
                            rid,
                            "DRIFT",
                            f"cost_usd recorded={recorded} != manifest={source}",
                        )
                    )
    return findings


def verify_all(home: Optional[str] = None) -> List[LedgerFinding]:
    """Verify every project in the cross-project index (FR-6)."""
    findings: List[LedgerFinding] = []
    for row in load_index(home).projects:
        findings.extend(
            verify_project(load_project_ledger(row.get("project_id", ""), home=home))
        )
    return findings


def record_run(
    project_root: str, *, home: Optional[str] = None
) -> ProjectGenerationLedger:
    """Auto-derive this project's latest run from its artifacts and record it (FR-3).

    Reads ``.startd8/generation-manifest.json`` (required) and the sibling
    ``.cap-dev-pipe/pipeline-output/batch-ledger.json`` (for batch id + run counts; degrades if absent),
    joins them into a run row, upserts the per-project ledger and the cross-project index, and persists
    both atomically. Returns the updated per-project ledger.
    """
    root = Path(project_root).resolve()
    manifest_path = root / ".startd8" / "generation-manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(
            f"no generation-manifest.json under {root} (nothing to record)"
        )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    batch_path = root / ".cap-dev-pipe" / "pipeline-output" / "batch-ledger.json"
    batch_data: Dict[str, Any] = {}
    run_snapshot: Optional[Dict[str, Any]] = None
    if batch_path.is_file():
        try:
            batch_data = json.loads(batch_path.read_text(encoding="utf-8"))
            runs = batch_data.get("runs", [])
            if runs:  # the snapshot for this generation = the latest recorded run
                run_snapshot = max(runs, key=lambda r: r.get("timestamp", ""))
        except (json.JSONDecodeError, OSError):
            logger.warning(
                "Unreadable batch-ledger %s — recording from manifest alone", batch_path
            )

    run_id = (run_snapshot or {}).get("run_id") or root.name
    batch_meta = {
        "batch_id": batch_data.get("batch_id", ""),
        "seed_checksum": batch_data.get("seed_checksum", ""),
        "seed_path": batch_data.get("seed_path", ""),
        "total_tasks": batch_data.get("total_tasks", 0),
        "batch_ledger_ref": str(batch_path) if batch_path.is_file() else "",
    }
    run_row = build_run_row(root, manifest, run_snapshot, run_id)

    project_id, project_path = resolve_project_identity(str(root))
    ledger = load_project_ledger(project_id, project_path, home)
    ledger.project_path = project_path  # keep the path fresh
    ledger.upsert_run(batch_meta, run_row)
    save_project_ledger(ledger, home)

    index = load_index(home)
    index.upsert(ledger, home)
    save_index(index, home)

    logger.info(
        "Recorded run %s for project %s (%s runs total)",
        run_id,
        project_id,
        ledger.cumulative()["runs"],
    )
    return ledger
