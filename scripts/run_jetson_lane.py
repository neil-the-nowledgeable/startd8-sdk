#!/usr/bin/env python3
"""Jetson on-prem lane driver — firewall-enforced generation against the self-hosted cluster.

Loops the Online Boutique seeds through one or more `jetson:*` aliases via the in-process
`run_jetson_cell` runner (which enforces the contamination firewall: FR-J5a applied-adapter echo,
FR-J6 neutral prompt, FR-J6b determinism), partitions results into general / in-domain / invalid
tracks, and writes a durable batch (`cells.json` + `report.md`). The Jetson is a SEPARATE on-prem
lane (OQ-J3) — these results never enter the cloud cost ranking.

Usage:
  # plan only ($0, no endpoint) — default
  python3 scripts/run_jetson_lane.py --model jetson:mistral-7b-base

  # real run (needs rosie up + the FR-J6/J5a server fix deployed)
  STARTD8_ALLOW_LAN_ENDPOINT=1 python3 scripts/run_jetson_lane.py \
      --model jetson:mistral-7b-base --run --server-sha 27e714fc

Notes:
- Serial by design: the FastAPI server mutates a shared active-adapter, so concurrent cells could
  cross adapters (plan Step 5 residual). One cell at a time.
- A missing `STARTD8_ALLOW_LAN_ENDPOINT=1` makes `--run` fail fast at agent creation (FR-J12).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO = Path(__file__).resolve().parents[1]
SEEDS_DIR = REPO / "docs" / "design" / "model-benchmark" / "seeds"
if str(REPO / "src") not in sys.path:
    sys.path.insert(0, str(REPO / "src"))

from startd8.benchmark_matrix import jetson_lane as lane  # noqa: E402
from startd8.benchmark_matrix.firewall import TRACK_GENERAL, TRACK_IN_DOMAIN, TRACK_INVALID  # noqa: E402


def load_seed_prompt(seed_path: Path) -> Tuple[str, str, str]:
    """Return (service_name, generation_prompt, language) from a benchmark seed."""
    d = json.loads(seed_path.read_text())
    meta = d.get("service_metadata")
    if isinstance(meta, str):
        meta = json.loads(meta.replace("'", '"')) if meta.strip().startswith("{") else {}
    service = (meta or {}).get("service") or seed_path.stem.replace("seed-", "")
    language = (meta or {}).get("language", "unknown")
    cfg = (d.get("tasks") or [{}])[0].get("config", {})
    desc = cfg.get("task_description", "")
    reqs = cfg.get("requirements_text", "")
    prompt = f"{desc}\n\n{reqs}".strip()
    return service, prompt, language


def discover_seeds(services: Optional[List[str]]) -> List[Tuple[str, Path]]:
    """Resolve seed files for the requested services (or all if None)."""
    out: List[Tuple[str, Path]] = []
    for p in sorted(SEEDS_DIR.glob("seed-*.json")):
        name = p.stem.replace("seed-", "")
        if services and name not in services:
            continue
        out.append((name, p))
    return out


def build_plan(models: List[str], seeds: List[Tuple[str, Path]]) -> Dict[str, Any]:
    return {
        "models": models,
        "services": [s for s, _ in seeds],
        "cells": len(models) * len(seeds),
    }


def _alias_of(model_spec: str) -> str:
    """`jetson:mistral-7b-base` -> `mistral-7b-base` (provider prefix stripped)."""
    return model_spec.split(":", 1)[1] if ":" in model_spec else model_spec


async def run_lane(
    models: List[str],
    seeds: List[Tuple[str, Path]],
    *,
    server_sha: Optional[str],
    max_tokens: int,
    sampling: Dict[str, Any],
) -> List[Tuple[lane.JetsonCellRecord, str]]:
    """Run every (model, service) cell serially; return (record, service) pairs."""
    from startd8.providers import ProviderRegistry

    ProviderRegistry.discover()
    provider = ProviderRegistry.get_provider("jetson")
    if provider is None:
        raise RuntimeError("jetson provider not registered")

    pairs: List[Tuple[lane.JetsonCellRecord, str]] = []
    for model_spec in models:
        alias = _alias_of(model_spec)
        # FR-J12 opt-in is enforced inside create_agent; let it raise with its clear message.
        agent = provider.create_agent(alias, max_tokens=max_tokens)
        for service, seed_path in seeds:
            _svc, prompt, _lang = load_seed_prompt(seed_path)
            try:
                rec = await lane.run_jetson_cell(
                    agent,
                    requested_alias=alias,
                    prompt=prompt,
                    sampling=sampling,
                    server_commit_sha=server_sha,
                )
            except Exception as e:  # endpoint down / transport error mid-batch — don't wedge the run
                rec = lane.JetsonCellRecord(
                    alias=alias, text=None, track=TRACK_INVALID, scored=False,
                    firewall={"invalidated": True, "error": True, "reasons": [f"call failed: {e}"]},
                    server_commit_sha=server_sha, sampling=sampling, quant=lane.DEFAULT_QUANT,
                )
            pairs.append((rec, service))
    return pairs


def write_batch(out_dir: Path, pairs: List[Tuple[lane.JetsonCellRecord, str]], plan: Dict[str, Any],
                server_sha: Optional[str]) -> Tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    cells = []
    for rec, service in pairs:
        row = rec.to_dict()
        row["service"] = service
        cells.append(row)
    cells_path = out_dir / "cells.json"
    cells_path.write_text(json.dumps({"plan": plan, "server_sha": server_sha, "cells": cells}, indent=2))

    parts = lane.partition_by_track([r for r, _ in pairs])
    lines = [
        f"# Jetson on-prem lane — {out_dir.name}",
        "",
        f"- server_sha: `{server_sha or '(unpinned)'}`",
        f"- general (scored): **{len(parts[TRACK_GENERAL])}**",
        f"- in-domain (scored, fenced): **{len(parts[TRACK_IN_DOMAIN])}**",
        f"- invalid (DROPPED): **{len(parts[TRACK_INVALID])}**",
        "",
        "| service | alias | track | scored | reasons |",
        "|---|---|---|---|---|",
    ]
    for rec, service in pairs:
        reasons = "; ".join(rec.firewall.get("reasons", [])) or "—"
        lines.append(f"| {service} | {rec.alias} | {rec.track} | {rec.scored} | {reasons} |")
    report_path = out_dir / "report.md"
    report_path.write_text("\n".join(lines) + "\n")
    return cells_path, report_path


def main() -> int:
    ap = argparse.ArgumentParser(description="Jetson on-prem lane driver (firewall-enforced).")
    ap.add_argument("--model", action="append", dest="models", default=[],
                    help="jetson:<alias> (repeatable; default jetson:mistral-7b-base)")
    ap.add_argument("--service", action="append", dest="services", default=[],
                    help="service name (repeatable; default: paymentservice)")
    ap.add_argument("--run", action="store_true", help="actually hit the endpoint (default: dry-run)")
    ap.add_argument("--server-sha", default=None, help="edge-brains fastapi_serve.py commit SHA (FR-J6 artifact)")
    ap.add_argument("--max-tokens", type=int, default=2048)
    ap.add_argument("--out", default=None, help="batch dir (default .startd8/jetson-lane/<ts>)")
    args = ap.parse_args()

    models = list(dict.fromkeys(args.models)) or ["jetson:mistral-7b-base"]
    services = list(dict.fromkeys(args.services)) or ["paymentservice"]
    seeds = discover_seeds(services)
    if not seeds:
        print(f"No seeds found for {services} in {SEEDS_DIR}", file=sys.stderr)
        return 2

    plan = build_plan(models, seeds)
    print("=== Jetson on-prem lane plan ===")
    print(f"models  : {', '.join(models)}")
    print(f"services: {', '.join(plan['services'])}")
    print(f"cells   : {plan['cells']}  (serial)")
    print("cost    : on-prem lane (≈$0 marginal; never ranked vs cloud — OQ-J3)")

    if not args.run:
        print("\nDRY-RUN — no endpoint contacted, nothing generated. Re-run with --run (needs "
              "STARTD8_ALLOW_LAN_ENDPOINT=1 + rosie up).")
        return 0

    if not args.server_sha:
        print("⚠ no --server-sha given; FR-J6 acceptance wants the verified fastapi_serve.py SHA "
              "(e.g. 27e714fc) recorded in provenance.")

    from startd8.exceptions import ConfigurationError
    sampling = dict(lane.DEFAULT_SAMPLING)
    try:
        pairs = asyncio.run(run_lane(models, seeds, server_sha=args.server_sha,
                                     max_tokens=args.max_tokens, sampling=sampling))
    except ConfigurationError as e:
        print(f"\nERROR: {e}", file=sys.stderr)
        return 2

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = Path(args.out) if args.out else (REPO / ".startd8" / "jetson-lane" / ts)
    cells_path, report_path = write_batch(out_dir, pairs, plan, args.server_sha)

    parts = lane.partition_by_track([r for r, _ in pairs])
    print(f"\nwrote {cells_path}")
    print(f"wrote {report_path}")
    print(f"general={len(parts[TRACK_GENERAL])} in-domain={len(parts[TRACK_IN_DOMAIN])} "
          f"invalid(DROPPED)={len(parts[TRACK_INVALID])}")
    if parts[TRACK_INVALID]:
        print("⚠ some cells were INADMISSIBLE — see report.md reasons (firewall enforced).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
