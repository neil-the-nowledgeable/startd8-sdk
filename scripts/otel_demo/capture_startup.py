#!/usr/bin/env python3
"""Tier 0 — S7 startup capture for Tier 1 seed generation (FR-7).

Extracts command, port env, and readiness hints for the seven covered gRPC services
from the pinned OTel Demo compose tree. Writes ``startup-capture.json``.

Exit codes:
  0  capture written (partial rows allowed with warnings)
  2  workdir missing / compose unreadable

Usage:
  python3 scripts/otel_demo/capture_startup.py \\
      --workdir .otel-demo \\
      --out docs/design/otel-demo-corpus/startup-capture.json
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from scripts.gen_otel_benchmark_seeds import SERVICES, behavioral_eligible  # noqa: E402

SCHEMA_VERSION = "1.0"
CORPUS_DIR = _REPO / "docs" / "design" / "otel-demo-corpus"

# Map compose service name -> seed metadata (aligned with gen_otel_benchmark_seeds.SERVICES).
COVERED_BY_KEY = {s["key"]: s for s in SERVICES}

PORT_ENV_CANDIDATES = ("PORT", "GRPC_PORT", "SERVICE_PORT", "APP_PORT")


def _compose_config_json(workdir: Path) -> Optional[dict[str, Any]]:
    files = [workdir / "compose.yaml"]
    obs = workdir / "compose.observability.yaml"
    if obs.is_file():
        files.append(obs)
    args = ["docker", "compose"]
    for f in files:
        if f.is_file():
            args.extend(["-f", str(f)])
    args.extend(["config", "--format", "json"])
    try:
        proc = subprocess.run(args, cwd=workdir, capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return None


def _parse_compose_yaml_fallback(workdir: Path, service: str) -> dict[str, Any]:
    """Minimal block parser when docker compose is unavailable."""
    text = (workdir / "compose.yaml").read_text(encoding="utf-8")
    pattern = rf"^\s{{2}}{re.escape(service)}:\s*$"
    match = re.search(pattern, text, re.MULTILINE)
    if not match:
        return {}
    start = match.end()
    block_lines: list[str] = []
    for line in text[start:].splitlines():
        if line and not line.startswith("  "):
            break
        block_lines.append(line)
    block = "\n".join(block_lines)
    out: dict[str, Any] = {}
    env: dict[str, str] = {}
    for m in re.finditer(r"^\s+-?\s*([A-Z0-9_]+)=([^\n#]+)", block, re.MULTILINE):
        env[m.group(1)] = m.group(2).strip().strip('"').strip("'")
    for m in re.finditer(r"^\s+([A-Z0-9_]+):\s*([^\n#]+)", block, re.MULTILINE):
        if m.group(1) in PORT_ENV_CANDIDATES:
            env.setdefault(m.group(1), m.group(2).strip().strip('"').strip("'"))
    out["environment"] = env
    cmd_m = re.search(r"^\s+command:\s*(.+)$", block, re.MULTILINE)
    if cmd_m:
        out["command"] = cmd_m.group(1).strip()
    return out


def _extract_startup(svc_def: dict[str, Any]) -> dict[str, Any]:
    """Return seed-compatible startup block (cmd/port_env/readiness only)."""
    env_list = svc_def.get("environment") or {}
    if isinstance(env_list, list):
        env: dict[str, str] = {}
        for item in env_list:
            if isinstance(item, str) and "=" in item:
                k, v = item.split("=", 1)
                env[k] = v
            elif isinstance(item, dict):
                env.update({str(k): str(v) for k, v in item.items()})
    else:
        env = {str(k): str(v) for k, v in (env_list or {}).items()}

    port_env = next((k for k in PORT_ENV_CANDIDATES if k in env), "PORT")
    port = env.get(port_env) or env.get("PORT")

    command = svc_def.get("command")
    if isinstance(command, list):
        cmd = command
    elif isinstance(command, str):
        cmd = command.split()
    else:
        entrypoint = svc_def.get("entrypoint")
        if isinstance(entrypoint, list):
            cmd = entrypoint
        elif isinstance(entrypoint, str):
            cmd = entrypoint.split()
        else:
            cmd = []

    readiness = "tcp"
    if port:
        readiness = f"tcp:{port}"

    return {
        "cmd": cmd,
        "port_env": port_env,
        "readiness": readiness,
    }


def capture(workdir: Path) -> dict[str, Any]:
    cfg = _compose_config_json(workdir)
    services_cfg: dict[str, Any] = (cfg.get("services") or {}) if cfg else {}

    rows: list[dict[str, Any]] = []
    warnings: list[str] = []
    for compose_name, svc in COVERED_BY_KEY.items():
        svc_def = services_cfg.get(compose_name)
        if not svc_def:
            svc_def = _parse_compose_yaml_fallback(workdir, compose_name)
            if not svc_def:
                warnings.append(f"{compose_name}: not found in compose")
                svc_def = {}
        startup = _extract_startup(svc_def)
        rows.append(
            {
                "compose_service": compose_name,
                "proto_service": svc["proto_service"],
                "language": svc["language"],
                "target_file_hint": svc["target_file"],
                "startup": startup,
                "behavioral_eligible": behavioral_eligible(svc),
                "capture_status": "ok" if startup.get("cmd") or port_ok(startup) else "partial",
            }
        )

    manifest_path = CORPUS_DIR / "bringup-manifest.json"
    demo_ref = "unknown"
    git_sha = "unknown"
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        demo_ref = manifest.get("demo_ref", demo_ref)
        git_sha = manifest.get("git_sha", git_sha)

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "demo_ref": demo_ref,
        "git_sha": git_sha,
        "workdir": str(workdir),
        "services": rows,
        "warnings": warnings,
        "note": "Consumed by Tier 1 gen_otel_benchmark_seeds.py (FR-7). behavioral_eligible mirrors Track-2 sandbox.",
    }


def port_ok(startup: dict[str, Any]) -> bool:
    readiness = startup.get("readiness", "")
    return readiness.startswith("tcp:") and readiness != "tcp:"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--workdir", default=str(_REPO / ".otel-demo"))
    ap.add_argument("--out", default=str(CORPUS_DIR / "startup-capture.json"))
    args = ap.parse_args(argv)

    workdir = Path(args.workdir).resolve()
    if not (workdir / "compose.yaml").is_file():
        print(f"ERROR: {workdir}/compose.yaml not found", file=sys.stderr)
        return 2

    doc = capture(workdir)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=2, sort_keys=True)
        fh.write("\n")

    ok = sum(1 for s in doc["services"] if s["capture_status"] == "ok")
    print(f"wrote {out_path}  captured={ok}/{len(doc['services'])}")
    for w in doc["warnings"]:
        print(f"  WARN: {w}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
