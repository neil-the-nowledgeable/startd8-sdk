"""Prime Contractor configuration model and loader (F-AC-02).

Consolidates subsystem configuration (Micro Prime, complexity routing,
repair, validation) into a single `.startd8/prime-contractor.json` file,
reducing the 16+ compensatory/defensive CLI arguments to a single --config.

Config file schema:
    {
      "micro_prime": { ... MicroPrimeConfig fields ... },
      "complexity_routing": { ... ComplexityRoutingConfig fields ... },
      "repair": { "enabled": true, ... RepairConfig fields ... },
      "validation": { "enabled": null, "strict": false },
      "agents": {
        "lead": "anthropic:claude-sonnet-4-5-20250514",
        "drafter": null,
        "tier3": null
      }
    }

All sections are optional. Missing sections use defaults.
CLI arguments override config file values.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from startd8.logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class ValidationConfig:
    """Validation behavior for post-generation checks."""

    enabled: Optional[bool] = None  # None = mode-default
    strict: bool = False


@dataclass
class AgentConfig:
    """Agent specifications for code generation tiers."""

    lead: Optional[str] = None
    drafter: Optional[str] = None
    tier3: Optional[str] = None  # COMPLEX tier agent


@dataclass
class PrimeContractorConfig:
    """Consolidated configuration for the Prime Contractor workflow.

    Wraps subsystem configs into a single structure loadable from
    .startd8/prime-contractor.json or passed via --config CLI arg.
    """

    # Subsystem configs stored as raw dicts — instantiated lazily by the
    # workflow so that subsystem imports are deferred.
    micro_prime: dict[str, Any] = field(default_factory=dict)
    complexity_routing: dict[str, Any] = field(default_factory=dict)
    repair: dict[str, Any] = field(default_factory=dict)

    validation: ValidationConfig = field(default_factory=ValidationConfig)
    agents: AgentConfig = field(default_factory=AgentConfig)

    # Top-level flags
    micro_prime_enabled: bool = False
    complexity_routing_enabled: bool = False
    repair_enabled: bool = True


def load_prime_contractor_config(
    config_path: str | Path | None = None,
    project_root: str | Path | None = None,
) -> PrimeContractorConfig:
    """Load PrimeContractorConfig from a JSON file.

    Resolution order:
    1. Explicit config_path (from --config CLI arg)
    2. .startd8/prime-contractor.json in project_root
    3. Default config (all defaults)

    Args:
        config_path: Explicit path to a config JSON file.
        project_root: Project root for default config discovery.

    Returns:
        PrimeContractorConfig with values from file or defaults.
    """
    raw: dict[str, Any] = {}

    path: Path | None = None
    if config_path:
        path = Path(config_path)
    elif project_root:
        candidate = Path(project_root) / ".startd8" / "prime-contractor.json"
        if candidate.is_file():
            path = candidate

    if path and path.is_file():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            logger.info("Loaded prime contractor config: %s", path)
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Config load failed (%s): %s", path, exc)

    if not isinstance(raw, dict):
        logger.warning("Config must be a JSON object, got %s", type(raw).__name__)
        raw = {}

    return _parse_config(raw)


def _parse_config(raw: dict[str, Any]) -> PrimeContractorConfig:
    """Parse raw dict into PrimeContractorConfig."""
    config = PrimeContractorConfig()

    # Micro Prime section
    mp = raw.get("micro_prime", {})
    if isinstance(mp, dict):
        config.micro_prime = mp
        config.micro_prime_enabled = mp.pop("enabled", False)

    # Complexity routing section
    cr = raw.get("complexity_routing", {})
    if isinstance(cr, dict):
        config.complexity_routing = cr
        config.complexity_routing_enabled = cr.pop("enabled", False)

    # Repair section
    rp = raw.get("repair", {})
    if isinstance(rp, dict):
        config.repair = rp
        config.repair_enabled = rp.pop("enabled", True)

    # Validation section
    val = raw.get("validation", {})
    if isinstance(val, dict):
        config.validation = ValidationConfig(
            enabled=val.get("enabled"),
            strict=val.get("strict", False),
        )

    # Agents section
    ag = raw.get("agents", {})
    if isinstance(ag, dict):
        config.agents = AgentConfig(
            lead=ag.get("lead"),
            drafter=ag.get("drafter"),
            tier3=ag.get("tier3"),
        )

    return config


def apply_cli_overrides(
    config: PrimeContractorConfig,
    args: Any,
) -> PrimeContractorConfig:
    """Apply CLI argument overrides onto a loaded config.

    CLI args take precedence over config file values. Only non-None
    CLI values override.

    Args:
        config: Base config from file.
        args: argparse Namespace with CLI args.

    Returns:
        The same config object, mutated with overrides.
    """
    # Micro Prime overrides
    if getattr(args, "micro_prime", False):
        config.micro_prime_enabled = True
    if getattr(args, "no_micro_prime", False):
        config.micro_prime_enabled = False
    if getattr(args, "micro_prime_dry_run", False):
        config.micro_prime_enabled = True
        config.micro_prime["dry_run"] = True

    for cli_key, config_key in [
        ("micro_prime_model", "model"),
        ("micro_prime_max_tokens", "max_tokens"),
        ("micro_prime_cloud_retry_attempts", "cloud_escalation_max_attempts"),
        ("micro_prime_cloud_retry_strategy", "cloud_escalation_retry_strategy"),
        ("micro_prime_cloud_retry_max_chars", "cloud_escalation_retry_max_chars"),
    ]:
        val = getattr(args, cli_key, None)
        if val is not None:
            config.micro_prime[config_key] = val

    if getattr(args, "micro_prime_no_templates", False):
        config.micro_prime["templates_enabled"] = False
    if getattr(args, "micro_prime_no_repair", False):
        config.micro_prime["repair_enabled"] = False

    # Complexity routing overrides
    if getattr(args, "complexity_routing", False):
        config.complexity_routing_enabled = True
    if getattr(args, "complexity_loc_simple_max", None) is not None:
        config.complexity_routing["loc_simple_max"] = args.complexity_loc_simple_max
    if getattr(args, "tier3_agent", None):
        config.agents.tier3 = args.tier3_agent

    # Repair overrides
    if getattr(args, "no_repair", False):
        config.repair_enabled = False

    # Validation overrides
    if getattr(args, "strict_validation", False):
        config.validation.enabled = True
        config.validation.strict = True
    elif getattr(args, "validate", False):
        config.validation.enabled = True
    elif getattr(args, "no_validate", False):
        config.validation.enabled = False

    # Agent overrides
    if getattr(args, "lead_agent", None):
        config.agents.lead = args.lead_agent
    if getattr(args, "drafter_agent", None):
        config.agents.drafter = args.drafter_agent

    return config
