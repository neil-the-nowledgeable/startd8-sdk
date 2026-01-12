"""
Framework health checks.

Checks framework initialization state, event bus health, and configuration.
"""

import os
import sys
import time
from typing import Any, Dict, Optional

from ..models import CheckCategory, HealthCheck, HealthStatus
from . import register_check


@register_check(
    "python_environment",
    CheckCategory.FRAMEWORK,
    description="Check Python version and environment",
)
def check_python_environment() -> HealthCheck:
    """Check Python version and environment."""
    start = time.time()

    version_info = sys.version_info
    version_str = f"{version_info.major}.{version_info.minor}.{version_info.micro}"

    # Startd8 requires Python 3.9+
    if version_info.major == 3 and version_info.minor >= 9:
        status = HealthStatus.HEALTHY
        message = f"Python {version_str} (compatible)"
    elif version_info.major == 3 and version_info.minor >= 8:
        status = HealthStatus.WARNING
        message = f"Python {version_str} (3.9+ recommended)"
    else:
        status = HealthStatus.CRITICAL
        message = f"Python {version_str} (requires 3.9+)"

    details = {
        "version": version_str,
        "executable": sys.executable,
        "platform": sys.platform,
    }

    return HealthCheck(
        name="python_environment",
        category=CheckCategory.FRAMEWORK,
        status=status,
        message=message,
        details=details,
        duration_ms=(time.time() - start) * 1000,
    )


@register_check(
    "startd8_import",
    CheckCategory.FRAMEWORK,
    description="Check if startd8 package can be imported",
)
def check_startd8_import() -> HealthCheck:
    """Check if startd8 package can be imported."""
    start = time.time()

    try:
        import startd8
        version = getattr(startd8, "__version__", "unknown")
        status = HealthStatus.HEALTHY
        message = f"Startd8 SDK v{version} imported successfully"
        details = {"version": version}
    except ImportError as e:
        status = HealthStatus.CRITICAL
        message = f"Failed to import startd8: {e}"
        details = {"error": str(e)}
    except Exception as e:
        status = HealthStatus.CRITICAL
        message = f"Error importing startd8: {e}"
        details = {"error": str(e)}

    return HealthCheck(
        name="startd8_import",
        category=CheckCategory.FRAMEWORK,
        status=status,
        message=message,
        details=details,
        duration_ms=(time.time() - start) * 1000,
    )


@register_check(
    "framework_initialized",
    CheckCategory.FRAMEWORK,
    requires_framework=True,
    description="Check if AgentFramework is properly initialized",
)
def check_framework_initialized(framework: Optional[Any] = None) -> HealthCheck:
    """Check if AgentFramework is properly initialized."""
    start = time.time()

    if framework is None:
        return HealthCheck(
            name="framework_initialized",
            category=CheckCategory.FRAMEWORK,
            status=HealthStatus.SKIPPED,
            message="Skipped: No framework provided",
            duration_ms=(time.time() - start) * 1000,
        )

    try:
        # Check key framework attributes
        checks_passed = []
        checks_failed = []

        # Check agents
        if hasattr(framework, "agents"):
            agent_count = len(framework.agents) if framework.agents else 0
            checks_passed.append(f"agents: {agent_count}")
        else:
            checks_failed.append("agents: not found")

        # Check config
        if hasattr(framework, "config"):
            checks_passed.append("config: present")
        else:
            checks_failed.append("config: not found")

        # Check event bus
        if hasattr(framework, "event_bus"):
            checks_passed.append("event_bus: present")
        else:
            checks_failed.append("event_bus: not found")

        if not checks_failed:
            status = HealthStatus.HEALTHY
            message = f"Framework initialized: {', '.join(checks_passed)}"
        else:
            status = HealthStatus.WARNING
            message = f"Framework partial: {', '.join(checks_failed)}"

        details = {
            "passed": checks_passed,
            "failed": checks_failed,
        }

    except Exception as e:
        status = HealthStatus.UNKNOWN
        message = f"Error checking framework: {e}"
        details = {"error": str(e)}

    return HealthCheck(
        name="framework_initialized",
        category=CheckCategory.FRAMEWORK,
        status=status,
        message=message,
        details=details,
        duration_ms=(time.time() - start) * 1000,
    )


@register_check(
    "event_bus_health",
    CheckCategory.FRAMEWORK,
    requires_framework=True,
    description="Check event bus subscription and handler health",
)
def check_event_bus_health(framework: Optional[Any] = None) -> HealthCheck:
    """Check event bus health."""
    start = time.time()

    if framework is None or not hasattr(framework, "event_bus"):
        return HealthCheck(
            name="event_bus_health",
            category=CheckCategory.FRAMEWORK,
            status=HealthStatus.SKIPPED,
            message="Skipped: No event bus available",
            duration_ms=(time.time() - start) * 1000,
        )

    try:
        event_bus = framework.event_bus

        # Count subscriptions
        subscription_count = 0
        if hasattr(event_bus, "_subscriptions"):
            subscription_count = len(event_bus._subscriptions)
        elif hasattr(event_bus, "subscriptions"):
            subscription_count = len(event_bus.subscriptions)

        status = HealthStatus.HEALTHY
        message = f"Event bus healthy: {subscription_count} subscriptions"
        details = {"subscription_count": subscription_count}

    except Exception as e:
        status = HealthStatus.UNKNOWN
        message = f"Failed to check event bus: {e}"
        details = {"error": str(e)}

    return HealthCheck(
        name="event_bus_health",
        category=CheckCategory.FRAMEWORK,
        status=status,
        message=message,
        details=details,
        duration_ms=(time.time() - start) * 1000,
    )


@register_check(
    "environment_variables",
    CheckCategory.FRAMEWORK,
    description="Check critical environment variables",
)
def check_environment_variables() -> HealthCheck:
    """Check that critical environment variables are configured."""
    start = time.time()

    # Required variables
    required = {
        "ANTHROPIC_API_KEY": os.environ.get("ANTHROPIC_API_KEY", ""),
    }

    # Optional but recommended
    optional = {
        "OPENAI_API_KEY": os.environ.get("OPENAI_API_KEY", ""),
        "GOOGLE_API_KEY": os.environ.get("GOOGLE_API_KEY", ""),
    }

    missing_required = [k for k, v in required.items() if not v]
    present_optional = [k for k, v in optional.items() if v]

    if missing_required:
        status = HealthStatus.WARNING
        message = f"Missing: {', '.join(missing_required)}"
    else:
        status = HealthStatus.HEALTHY
        if present_optional:
            message = f"All required set, optional: {', '.join(present_optional)}"
        else:
            message = "All required environment variables set"

    details = {
        "required_set": [k for k, v in required.items() if v],
        "required_missing": missing_required,
        "optional_set": present_optional,
    }

    return HealthCheck(
        name="environment_variables",
        category=CheckCategory.FRAMEWORK,
        status=status,
        message=message,
        details=details,
        duration_ms=(time.time() - start) * 1000,
    )


@register_check(
    "dependency_versions",
    CheckCategory.FRAMEWORK,
    description="Check versions of key dependencies",
)
def check_dependency_versions() -> HealthCheck:
    """Check versions of key dependencies."""
    start = time.time()
    versions: Dict[str, str] = {}
    issues: list = []

    dependencies = [
        ("anthropic", None),  # No version check
        ("openai", None),
        ("httpx", None),
        ("rich", None),
        ("questionary", None),
    ]

    for dep_name, min_version in dependencies:
        try:
            module = __import__(dep_name)
            version = getattr(module, "__version__", "unknown")
            versions[dep_name] = version
        except ImportError:
            versions[dep_name] = "not installed"
            if dep_name == "anthropic":
                issues.append(f"{dep_name} not installed (required)")

    if issues:
        status = HealthStatus.CRITICAL
        message = f"Dependency issues: {', '.join(issues)}"
    else:
        installed = [k for k, v in versions.items() if v != "not installed"]
        status = HealthStatus.HEALTHY
        message = f"{len(installed)} key dependencies available"

    return HealthCheck(
        name="dependency_versions",
        category=CheckCategory.FRAMEWORK,
        status=status,
        message=message,
        details=versions,
        duration_ms=(time.time() - start) * 1000,
    )
