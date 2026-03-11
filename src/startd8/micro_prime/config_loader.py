"""Micro Prime config loader for project-scoped settings.

Loads .startd8/micro_prime.json and maps it onto MicroPrimeConfig,
while also extracting cloud_agent_spec (not part of MicroPrimeConfig).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional, Tuple

from startd8.logging_config import get_logger
from startd8.micro_prime.models import MicroPrimeConfig

logger = get_logger(__name__)


def load_micro_prime_settings(
    project_root: Path,
) -> Tuple[MicroPrimeConfig, Optional[str]]:
    """Load Micro Prime settings from .startd8/micro_prime.json.

    Returns default MicroPrimeConfig and None when the file is missing
    or unreadable.
    """
    config_path = Path(project_root) / ".startd8" / "micro_prime.json"
    if not config_path.is_file():
        return MicroPrimeConfig(), None

    try:
        raw = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning(
            "Micro Prime config load failed (%s): %s", config_path, exc,
        )
        return MicroPrimeConfig(), None

    if not isinstance(raw, dict):
        logger.warning(
            "Micro Prime config must be a JSON object: %s", config_path,
        )
        return MicroPrimeConfig(), None

    return _parse_micro_prime_settings(raw)


def _parse_micro_prime_settings(
    raw: dict[str, Any],
) -> Tuple[MicroPrimeConfig, Optional[str]]:
    """Parse a dict of settings into MicroPrimeConfig + cloud_agent_spec."""
    # Support optional nested "config" block.
    config_block = raw.get("config")
    base: dict[str, Any] = {}
    if isinstance(config_block, dict):
        base.update(config_block)

    # Top-level keys override nested config.
    for key, value in raw.items():
        if key in ("config",):
            continue
        base[key] = value

    cloud_agent_spec = base.pop("cloud_agent_spec", None)

    valid_fields = set(MicroPrimeConfig.model_fields.keys())
    config_data = {k: v for k, v in base.items() if k in valid_fields}
    unknown_keys = sorted(k for k in base.keys() if k not in valid_fields)
    if unknown_keys:
        logger.warning(
            "Micro Prime config ignored unknown keys: %s",
            ", ".join(unknown_keys),
        )

    try:
        return MicroPrimeConfig(**config_data), cloud_agent_spec
    except (ValueError, TypeError) as exc:
        logger.warning(
            "Micro Prime config parse failed: %s", exc,
        )
        return MicroPrimeConfig(), cloud_agent_spec

