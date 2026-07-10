# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""Before/after contrast — the demo thesis, made visible.

Generate observability artifacts **twice** from the same manifest and target, and diff
the result:

* **Ungoverned** — the manifest with its governance stripped (no ``metricsProfile``, no
  ``datasources``). This is what naive generation produces: transport-default semantic-
  convention metric names, a ``${datasource}`` variable, guessed everything. It looks
  complete — and binds to almost nothing on a target that doesn't use those conventions.
* **Governed** — the manifest as authored: ``metricsProfile`` binds the PromQL to the
  target's real metric shape, ``datasources`` binds dashboards to the real Grafana UID.

Both are exported, generated, and **replayed against the live backend**, so the contrast
is grounded in fidelity numbers, not claims. The rendered markdown is the artifact: same
query slots, before vs after, with the headline "ungoverned binds X% / governed binds Y%."

Reuses the proven pipeline pieces (``_default_export`` + ``_default_generate`` +
``run_validation``); every external effect is injectable for network-free tests.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import yaml

from .bind_and_verify import _default_export, _default_generate
from .prometheus_query import Auth

logger = logging.getLogger(__name__)

_ONBOARDING_FILENAME = "onboarding-metadata.json"
_ARTIFACTS_SUBDIR = "observability"


# ─────────────────────────────── report model ──────────────────────────────


@dataclass
class VariantResult:
    """One side of the contrast (ungoverned or governed)."""

    label: str
    status: str
    binding_coverage: float = 0.0
    data_coverage: float = 0.0
    queries_replayed: int = 0
    #: Representative datasource binding the dashboards use (UID vs the ${datasource} var).
    datasource: str = ""
    #: {(service, signal): {"expr": str, "verdict": str}} — the per-slot replay outcome.
    samples: Dict[str, Dict[str, str]] = field(default_factory=dict)
    error: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ContrastReport:
    ungoverned: VariantResult
    governed: VariantResult

    def to_dict(self) -> Dict[str, Any]:
        return {"ungoverned": self.ungoverned.to_dict(), "governed": self.governed.to_dict()}


# ─────────────────────────── manifest transforms ───────────────────────────


def strip_governance(src: Path, dst: Path) -> None:
    """Copy *src* manifest to *dst* with all observability governance removed.

    Drops ``spec.observability.metricsProfile`` / ``.datasources`` and every
    ``spec.targets[].metricsProfile`` / ``.metrics`` / ``.datasources`` — leaving the
    naive default the generator falls back to (semconv-{transport}, ``${datasource}``).
    """
    data = yaml.safe_load(Path(src).read_text(encoding="utf-8")) or {}
    spec = data.get("spec") or {}
    obs = spec.get("observability")
    if isinstance(obs, dict):
        obs.pop("metricsProfile", None)
        obs.pop("datasources", None)
    for target in spec.get("targets") or []:
        if isinstance(target, dict):
            target.pop("metricsProfile", None)
            target.pop("metrics", None)
            target.pop("datasources", None)
    Path(dst).write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def _manifest_datasource(manifest_path: Path) -> str:
    """The representative Prometheus datasource a variant's dashboards will bind to."""
    data = yaml.safe_load(Path(manifest_path).read_text(encoding="utf-8")) or {}
    obs = (data.get("spec") or {}).get("observability") or {}
    ds = (obs.get("datasources") or {}).get("prometheus")
    return ds or "${datasource} (unbound variable — defaults to Grafana's default DS)"


def _collect_samples(fidelity: Dict[str, Any], limit: int = 200) -> Dict[str, Dict[str, str]]:
    """Per-(service, signal) replay outcome, for slot-by-slot before/after alignment.

    Collects broadly (not just the first few) so the renderer can pick the *most
    contrasting* slots — the ones where governance actually changed the verdict.
    """
    out: Dict[str, Dict[str, str]] = {}
    for v in fidelity.get("verdicts", []):
        key = f"{v['service']}/{v['signal']}"
        if key in out:
            continue
        out[key] = {"expr": (v.get("replayed_expr") or v.get("expr", "")), "verdict": v.get("verdict", "")}
        if len(out) >= limit:
            break
    return out


# ──────────────────────────── the orchestrator ─────────────────────────────


def _run_variant(
    *,
    label: str,
    manifest_path: Path,
    output_dir: Path,
    prometheus_url: str,
    min_coverage: float,
    allow_prod: bool,
    auth: Auth,
    export_cmd: List[str],
    export_fn: Callable[[Path, Path, List[str]], Dict[str, Any]],
    generate_fn: Callable[[Path, Path, Path], Dict[str, Any]],
    validate_fn: Callable[..., Any],
) -> VariantResult:
    """Export → generate → replay one manifest variant and summarize it."""
    output_dir.mkdir(parents=True, exist_ok=True)
    export = export_fn(manifest_path, output_dir, export_cmd)
    if not export.get("ok"):
        return VariantResult(label=label, status="unknown", error="export failed")

    onboarding = output_dir / _ONBOARDING_FILENAME
    if not onboarding.exists():
        return VariantResult(label=label, status="unknown", error="no onboarding-metadata.json")

    artifacts_dir = output_dir / _ARTIFACTS_SUBDIR
    generation = generate_fn(onboarding, artifacts_dir, manifest_path)
    if not generation.get("ok"):
        return VariantResult(label=label, status="unknown", error="generation errors")

    fidelity = validate_fn(
        artifacts_dir=artifacts_dir,
        onboarding_metadata=onboarding,
        prometheus_url=prometheus_url,
        min_coverage=min_coverage,
        allow_prod=allow_prod,
        auth=auth,
    ).to_dict()

    return VariantResult(
        label=label,
        status=fidelity.get("status", ""),
        binding_coverage=fidelity.get("binding_coverage", 0.0),
        data_coverage=fidelity.get("data_coverage", 0.0),
        queries_replayed=fidelity.get("queries_replayed", 0),
        datasource=_manifest_datasource(manifest_path),
        samples=_collect_samples(fidelity),
    )


def build_contrast(
    *,
    manifest_path: Path,
    prometheus_url: str,
    output_dir: Path,
    min_coverage: float = 0.9,
    allow_prod: bool = False,
    auth: Optional[Auth] = None,
    export_cmd: Optional[List[str]] = None,
    export_fn: Optional[Callable[[Path, Path, List[str]], Dict[str, Any]]] = None,
    generate_fn: Optional[Callable[[Path, Path, Path], Dict[str, Any]]] = None,
    validate_fn: Optional[Callable[..., Any]] = None,
) -> ContrastReport:
    """Generate + replay the ungoverned and governed variants; return the contrast."""
    manifest_path = Path(manifest_path)
    output_dir = Path(output_dir)
    auth = auth or Auth()
    export_cmd = export_cmd or ["contextcore", "manifest", "export", "--no-strict-quality"]
    export_fn = export_fn or _default_export
    generate_fn = generate_fn or _default_generate
    if validate_fn is None:
        from .validate_promql import run_validation as validate_fn  # type: ignore

    output_dir.mkdir(parents=True, exist_ok=True)
    stripped = output_dir / (manifest_path.name + ".ungoverned.tmp")
    strip_governance(manifest_path, stripped)

    common = dict(
        prometheus_url=prometheus_url, min_coverage=min_coverage, allow_prod=allow_prod,
        auth=auth, export_cmd=export_cmd, export_fn=export_fn, generate_fn=generate_fn,
        validate_fn=validate_fn,
    )
    try:
        ungoverned = _run_variant(
            label="ungoverned", manifest_path=stripped,
            output_dir=output_dir / "ungoverned", **common,
        )
        governed = _run_variant(
            label="governed", manifest_path=manifest_path,
            output_dir=output_dir / "governed", **common,
        )
    finally:
        stripped.unlink(missing_ok=True)

    return ContrastReport(ungoverned=ungoverned, governed=governed)


# ────────────────────────────── rendering ──────────────────────────────────


def _pct(x: float) -> str:
    return f"{x * 100:.0f}%"


def render_markdown(report: ContrastReport) -> str:
    """Render the contrast as a human-facing before/after markdown document."""
    u, g = report.ungoverned, report.governed
    lines: List[str] = []
    lines.append("# Observability: ungoverned vs governed\n")
    lines.append(
        "Same manifest, same live backend, generated two ways. **Ungoverned** is what "
        "naive generation emits (semantic-convention defaults, an unbound datasource "
        "variable). **Governed** binds every query to the target's real metric shape and "
        "datasource. Both were replayed against the live Prometheus — the numbers are "
        "fidelity, not claims.\n"
    )

    lines.append("## Headline\n")
    lines.append("| | Ungoverned | Governed |")
    lines.append("|---|---|---|")
    lines.append(f"| Queries that **bind** to live data | **{_pct(u.binding_coverage)}** | **{_pct(g.binding_coverage)}** |")
    lines.append(f"| Have live data right now | {_pct(u.data_coverage)} | {_pct(g.data_coverage)} |")
    lines.append(f"| Queries replayed | {u.queries_replayed} | {g.queries_replayed} |")
    lines.append(f"| Dashboard datasource | `{u.datasource}` | `{g.datasource}` |")
    lines.append(f"| Gate status | {u.status} | {g.status} |\n")
    delta = g.binding_coverage - u.binding_coverage
    lines.append(
        f"> Governance moved binding fidelity from **{_pct(u.binding_coverage)}** to "
        f"**{_pct(g.binding_coverage)}** (+{_pct(delta)}). Ungoverned observability looks "
        "complete but resolves against nothing; governed binds to your reality.\n"
    )

    lines.append("## Query-by-query (same slots, before → after)\n")
    _bound = {"pass", "bound_no_data"}

    def _contrast_rank(key: str) -> int:
        # Highest: governed binds while ungoverned fails (the thesis). Then any slot
        # where the emitted expr differs. Lowest: both identical outcome.
        ug = u.samples.get(key, {})
        gv = g.samples.get(key, {})
        governed_wins = gv.get("verdict") in _bound and ug.get("verdict") not in _bound
        expr_differs = ug.get("expr") != gv.get("expr")
        return (2 if governed_wins else 0) + (1 if expr_differs else 0)

    keys = [k for k in g.samples if k in u.samples] or list(g.samples)
    keys.sort(key=_contrast_rank, reverse=True)
    if not keys:
        lines.append("_No overlapping query slots to show._\n")
    for key in keys[:6]:
        us = u.samples.get(key, {})
        gs = g.samples.get(key, {})
        lines.append(f"### `{key}`\n")
        lines.append(f"- **Ungoverned** ({us.get('verdict', '—')}):")
        lines.append(f"  ```promql\n  {us.get('expr', '(not generated)')}\n  ```")
        lines.append(f"- **Governed** ({gs.get('verdict', '—')}):")
        lines.append(f"  ```promql\n  {gs.get('expr', '(not generated)')}\n  ```\n")

    lines.append("---\n")
    lines.append(
        "_Verdicts_: `pass` = returned live data · `bound_no_data` = binds to the live "
        "metric surface but no data in-window (healthy/idle) · `fail` = does not bind "
        "(wrong metric/label/selector/unit) · `error` = backend rejected the query.\n"
    )
    return "\n".join(lines)
