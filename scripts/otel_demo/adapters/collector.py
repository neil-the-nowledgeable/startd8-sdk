"""Static OTel Collector config parser for §4.1 OTLP receiver checks."""
from __future__ import annotations

from pathlib import Path
from typing import Any


def _find_collector_config(workdir: Path) -> Path | None:
    candidates = (
        workdir / "src" / "otel-collector" / "otelcol-config.yaml",
        workdir / "src" / "otel-collector" / "otelcol-config.yml",
        workdir / "otel-collector-config.yaml",
        workdir / "otel-config.yml",
        workdir / "otel-config.yaml",
    )
    for path in candidates:
        if path.is_file():
            return path
    return None


def _parse_yaml_receivers(text: str) -> dict[str, Any]:
    """Minimal YAML parse for receivers.otlp.protocols — stdlib only, no PyYAML."""
    receivers: dict[str, Any] = {}
    in_receivers = False
    in_otlp = False
    in_protocols = False
    indent_receivers = 0
    indent_otlp = 0
    indent_protocols = 0

    for raw in text.splitlines():
        line = raw.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        stripped = line.lstrip()
        indent = len(line) - len(stripped)

        if stripped == "receivers:":
            in_receivers = True
            in_otlp = False
            in_protocols = False
            indent_receivers = indent
            continue
        if in_receivers and indent <= indent_receivers and stripped != "receivers:":
            in_receivers = False
            in_otlp = False
            in_protocols = False

        if in_receivers and stripped.startswith("otlp:"):
            in_otlp = True
            in_protocols = False
            indent_otlp = indent
            continue
        if in_otlp and indent <= indent_otlp and not stripped.startswith("otlp:"):
            in_otlp = False
            in_protocols = False

        if in_otlp and stripped == "protocols:":
            in_protocols = True
            indent_protocols = indent
            continue
        if in_protocols and indent <= indent_protocols and stripped != "protocols:":
            in_protocols = False

        if in_protocols and stripped.endswith(":"):
            proto = stripped[:-1].strip()
            if proto:
                receivers[proto] = True

    return receivers


def check_otlp_receivers(workdir: Path, *, required: list[str]) -> dict[str, Any]:
    cfg = _find_collector_config(workdir)
    if cfg is None:
        return {
            "observed": 0,
            "passed": False,
            "detail": f"no collector config found under {workdir}",
            "observed_names": [],
        }
    text = cfg.read_text(encoding="utf-8")
    found = _parse_yaml_receivers(text)
    present = [p for p in required if p in found]
    return {
        "observed": len(present),
        "passed": len(present) >= len(required),
        "detail": f"{cfg.name}: otlp.protocols present={sorted(found)} required={required}",
        "observed_names": sorted(found),
    }
