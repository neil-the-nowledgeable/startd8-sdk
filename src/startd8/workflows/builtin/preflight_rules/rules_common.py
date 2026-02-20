"""
Common preflight rules applicable across multiple domains.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from ..domain_preflight_models import CheckStatus, EnvironmentCheck

from ._base import (
    ALL_DOMAINS,
    PYTHON_DOMAINS,
    PreflightRule,
    RuleContext,
    RuleContribution,
)
from ._helpers import LOGGER_RESERVED_FIELDS, file_has_pattern
from ._registry import preflight_rule


@preflight_rule(domains=ALL_DOMAINS, priority=10)
class ParentDirExistsRule(PreflightRule):
    """Check that the parent directory of the target file exists."""

    rule_id = "parent_dir_exists"

    def evaluate(self, ctx: RuleContext) -> Optional[RuleContribution]:
        if ctx.target_dir.exists():
            check = EnvironmentCheck(
                check_name="parent_dir_exists",
                status=CheckStatus.PASS,
                message=f"Parent directory exists: {ctx.target_dir}",
            )
        else:
            check = EnvironmentCheck(
                check_name="parent_dir_exists",
                status=CheckStatus.WARN,
                message=f"Parent directory does not exist: {ctx.target_dir}",
                detail="Directory will need to be created before code generation",
            )
        return RuleContribution(checks=[check])


@preflight_rule(domains=PYTHON_DOMAINS, priority=200)
class LoggerReservedFieldsRule(PreflightRule):
    """Detect logging usage and inject reserved-field constraint."""

    rule_id = "logger_reserved_fields"

    def evaluate(self, ctx: RuleContext) -> Optional[RuleContribution]:
        if not ctx.target_path.exists():
            return None
        if not file_has_pattern(ctx.target_path, r"\blogger\b"):
            return None

        sample_fields = ", ".join(sorted(list(LOGGER_RESERVED_FIELDS))[:8])
        check = EnvironmentCheck(
            check_name="logger_reserved_fields",
            status=CheckStatus.PASS,
            message="File uses logging \u2014 reserved field constraint will be injected",
            detail=f"Reserved fields: {', '.join(sorted(list(LOGGER_RESERVED_FIELDS)[:10]))}...",
        )
        constraint = (
            f"Do not use LogRecord reserved field names as extra= keys: "
            f"{sample_fields}, ..."
        )
        return RuleContribution(checks=[check], constraints=[constraint])


# Service-related filename patterns for AR-810.
_SERVICE_FILE_PATTERNS = (
    "Dockerfile", "dockerfile",
    "_server", "_service", "_pb2", "grpc",
)


@preflight_rule(domains=ALL_DOMAINS, priority=50)
class ServiceMetadataPreflightRule(PreflightRule):
    """AR-810: Warn when service-related files lack service metadata.

    Checks ``onboarding-metadata.json`` at the project root for a
    ``service_metadata`` section.  If absent and the target file looks
    service-related (Dockerfile, *_server*, *_pb2*, *_service*, grpc*),
    emits a WARN so protocol fidelity validators can be effective.
    """

    rule_id = "service_metadata_preflight"

    def evaluate(self, ctx: RuleContext) -> Optional[RuleContribution]:
        fname = ctx.target_path.name
        is_service_file = any(pat in fname for pat in _SERVICE_FILE_PATTERNS)
        if not is_service_file:
            return None

        metadata_path = ctx.project_root / "onboarding-metadata.json"
        if metadata_path.exists():
            try:
                data = json.loads(metadata_path.read_text(encoding="utf-8"))
                if data.get("service_metadata"):
                    return None  # metadata present — no warning needed
            except (json.JSONDecodeError, OSError):
                pass

        check = EnvironmentCheck(
            check_name="service_metadata_preflight",
            status=CheckStatus.WARN,
            message=(
                f"Service-related file '{fname}' but no service_metadata "
                f"in onboarding-metadata.json — protocol fidelity "
                f"validators will be skipped"
            ),
            detail=(
                "Add a service_metadata section with transport_protocol "
                "to onboarding-metadata.json for full validation coverage"
            ),
        )
        return RuleContribution(checks=[check])
