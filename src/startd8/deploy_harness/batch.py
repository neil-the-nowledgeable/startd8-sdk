"""Batch deploy over a model-comparison batch root + join to comparison-report.json (FR-12).

Globs ``batch_root/*/workdir`` (the per-model app roots that ``model_comparison.py`` materializes),
deploys each **serially** (v1 — avoids ephemeral port races), and writes an aggregate
``deploy-report.{json,md}`` with per-app rows + a rung roll-up.

The authoritative join key is the **verbatim model id** read from an explicit ``.model`` /
``deploy-manifest.json`` sidecar the writer drops next to each workdir (CRP R1-F6/S3). Reverse-slugging
the directory name is a **fallback only** — ``slug(model)`` is non-invertible, so a reverse-slug join
to ``comparison-report.json`` is flagged as potentially ambiguous rather than trusted silently.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from startd8.logging_config import get_logger

from .deploy import deploy_app_local
from .ladder import LadderResult, Stage, StageStatus

logger = get_logger("startd8.deploy_harness.batch")

_SIDECAR_JSON = "deploy-manifest.json"
_SIDECAR_TEXT = ".model"


@dataclass
class AppRoot:
    path: Path
    model: str
    model_source: str  # "sidecar" | "reverse-slug"


def _read_model_id(model_dir: Path, app_root: Path) -> Tuple[str, str]:
    """Resolve the verbatim model id from a sidecar, else fall back to the (lossy) dir slug."""
    for base in (model_dir, app_root):
        text = base / _SIDECAR_TEXT
        if text.is_file():
            val = text.read_text(encoding="utf-8").strip()
            if val:
                return val, "sidecar"
        manifest = base / _SIDECAR_JSON
        if manifest.is_file():
            try:
                val = (json.loads(manifest.read_text(encoding="utf-8")) or {}).get(
                    "model"
                )
            except (ValueError, OSError):
                val = None
            if val:
                return str(val), "sidecar"
    return model_dir.name, "reverse-slug"


def discover_app_roots(batch_root: Path) -> List[AppRoot]:
    """Find per-model app roots under ``batch_root`` (``*/workdir``, else the model dir itself)."""
    roots: List[AppRoot] = []
    for model_dir in sorted(p for p in batch_root.iterdir() if p.is_dir()):
        app_root = (
            model_dir / "workdir" if (model_dir / "workdir").is_dir() else model_dir
        )
        model, source = _read_model_id(model_dir, app_root)
        roots.append(AppRoot(path=app_root, model=model, model_source=source))
    return roots


def deploy_batch(
    batch_root: Path | str,
    *,
    install_timeout_s: float = 600.0,
    boot_timeout_s: float = 60.0,
    do_smoke: bool = True,
    keep: bool = False,
    limits: Any = None,
    runner_python: Optional[str] = None,
    join: bool = True,
) -> Dict[str, Any]:
    """Deploy every app root under ``batch_root`` serially and write the aggregate report."""
    root = Path(batch_root).resolve()
    app_roots = discover_app_roots(root)
    warnings: List[str] = []

    # Collision guard (CRP R1-F6): two reverse-slug roots mapping to one label can't be told apart.
    seen: Dict[str, int] = {}
    for ar in app_roots:
        seen[ar.model] = seen.get(ar.model, 0) + 1
    for ar in app_roots:
        if ar.model_source == "reverse-slug":
            warnings.append(
                f"{ar.model}: model id reverse-slugged (no sidecar) — join may be lossy"
            )
        if seen[ar.model] > 1:
            warnings.append(
                f"{ar.model}: model id collides across {seen[ar.model]} app roots"
            )

    results: List[Tuple[AppRoot, LadderResult]] = []
    for ar in app_roots:
        logger.info("deploy-batch: %s (%s) [%s]", ar.model, ar.path, ar.model_source)
        res = deploy_app_local(
            ar.path,
            model=ar.model,
            install_timeout_s=install_timeout_s,
            boot_timeout_s=boot_timeout_s,
            do_smoke=do_smoke,
            keep=keep,
            limits=limits,
            runner_python=runner_python,
        )
        results.append((ar, res))

    report = _build_report(root, results, warnings, join=join)
    (root / "deploy-report.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    (root / "deploy-report.md").write_text(_build_markdown(report), encoding="utf-8")
    return report


# --------------------------------------------------------------------------- report assembly


def _build_report(
    batch_root: Path,
    results: List[Tuple[AppRoot, LadderResult]],
    warnings: List[str],
    *,
    join: bool,
) -> Dict[str, Any]:
    comparison_index = _load_comparison_index(batch_root) if join else {}

    rows: List[Dict[str, Any]] = []
    for ar, res in results:
        row = res.model_dump()
        row["model_source"] = ar.model_source
        if comparison_index:
            row["comparison"], row["join_basis"] = _join_one(ar, comparison_index)
        rows.append(row)

    return {
        "batch_root": str(batch_root),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "app_count": len(rows),
        "rollup": _rollup(results),
        "warnings": warnings,
        "joined_to_comparison": bool(comparison_index),
        "apps": rows,
    }


def _rollup(results: List[Tuple[AppRoot, LadderResult]]) -> Dict[str, Any]:
    """How many apps reached vs passed each rung, plus the highest-stage distribution."""
    reached = {s.value: 0 for s in Stage}
    passed = {s.value: 0 for s in Stage}
    highest: Dict[str, int] = {}
    for _ar, res in results:
        highest[res.highest_stage] = highest.get(res.highest_stage, 0) + 1
        for name, sr in res.stages.items():
            reached[name] = reached.get(name, 0) + 1
            if sr.status == StageStatus.PASS:
                passed[name] = passed.get(name, 0) + 1
    return {"reached": reached, "passed": passed, "highest_stage": highest}


def _load_comparison_index(batch_root: Path) -> Dict[str, Any]:
    """Index ``comparison-report.json`` ranked rows by verbatim model (authoritative join key)."""
    path = batch_root / "comparison-report.json"
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return {}
    index: Dict[str, Any] = {}
    for entry in payload.get("ranked", []):
        model = entry.get("model")
        if model:
            index[model] = entry.get("metrics", entry)
    return index


def _join_one(ar: AppRoot, index: Dict[str, Any]) -> Tuple[Optional[Any], str]:
    """Exact verbatim-model join; reverse-slug rows only match if unambiguous, else flagged."""
    if ar.model in index:
        return index[ar.model], "exact"
    if ar.model_source == "reverse-slug":
        # the dir slug won't equal a verbatim model id; try a slug-of-key match, ambiguity-aware
        from startd8.model_comparison import slug

        candidates = [k for k in index if slug(k) == ar.model]
        if len(candidates) == 1:
            return index[candidates[0]], "reverse-slug"
        if len(candidates) > 1:
            return None, "ambiguous"
    return None, "no-match"


def _build_markdown(report: Dict[str, Any]) -> str:
    lines = [
        f"# Deploy Report — {report['batch_root']}",
        "",
        f"Generated {report['generated_at']} · {report['app_count']} app(s)"
        + (" · joined to comparison-report" if report["joined_to_comparison"] else ""),
        "",
    ]
    if report["warnings"]:
        lines += ["## Warnings", *[f"- {w}" for w in report["warnings"]], ""]

    ru = report["rollup"]
    lines += [
        "## Roll-up (passed / reached)",
        "",
        "| Rung | Passed | Reached |",
        "| --- | --- | --- |",
        *[
            f"| {s} | {ru['passed'].get(s, 0)} | {ru['reached'].get(s, 0)} |"
            for s in ("discover", "install", "boot", "health", "smoke")
        ],
        "",
        "## Per-model",
        "",
        "| Model | Highest | install | boot | health | smoke | Source |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for app in report["apps"]:
        st = app.get("stages", {})

        def _c(name: str) -> str:
            return st.get(name, {}).get("status", "—") if name in st else "—"

        lines.append(
            f"| {app.get('model', '?')} | {app.get('highest_stage', '?')} "
            f"| {_c('install')} | {_c('boot')} | {_c('health')} | {_c('smoke')} "
            f"| {app.get('model_source', '?')} |"
        )
    return "\n".join(lines) + "\n"
