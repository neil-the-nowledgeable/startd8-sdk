"""
Agent health checks.

Checks API key validity, agent connectivity, circuit breaker states,
and retry patterns.
"""

import os
import time
from typing import Any, Dict, Optional

from ..models import CheckCategory, HealthCheck, HealthStatus
from . import register_check


def _get_env_key(key_name: str) -> Optional[str]:
    """Get an environment variable, returning None if empty."""
    value = os.environ.get(key_name, "").strip()
    return value if value else None


@register_check(
    "anthropic_api_key",
    CheckCategory.AGENTS,
    description="Check if ANTHROPIC_API_KEY is set",
)
def check_anthropic_api_key() -> HealthCheck:
    """Check if Anthropic API key is configured."""
    start = time.time()
    key = _get_env_key("ANTHROPIC_API_KEY")

    if key:
        # Validate key format (starts with sk-ant-)
        if key.startswith("sk-ant-"):
            status = HealthStatus.HEALTHY
            message = "ANTHROPIC_API_KEY is configured"
            details = {"key_prefix": key[:12] + "..."}
        else:
            status = HealthStatus.WARNING
            message = "ANTHROPIC_API_KEY has unexpected format"
            details = {"key_prefix": key[:8] + "..."}
    else:
        status = HealthStatus.WARNING
        message = "ANTHROPIC_API_KEY is not set"
        details = None

    return HealthCheck(
        name="anthropic_api_key",
        category=CheckCategory.AGENTS,
        status=status,
        message=message,
        details=details,
        duration_ms=(time.time() - start) * 1000,
        fix_hint="set_anthropic_api_key" if status != HealthStatus.HEALTHY else None,
    )


@register_check(
    "openai_api_key",
    CheckCategory.AGENTS,
    description="Check if OPENAI_API_KEY is set",
)
def check_openai_api_key() -> HealthCheck:
    """Check if OpenAI API key is configured."""
    start = time.time()
    key = _get_env_key("OPENAI_API_KEY")

    if key:
        # Validate key format (starts with sk-)
        if key.startswith("sk-"):
            status = HealthStatus.HEALTHY
            message = "OPENAI_API_KEY is configured"
            details = {"key_prefix": key[:8] + "..."}
        else:
            status = HealthStatus.WARNING
            message = "OPENAI_API_KEY has unexpected format"
            details = {"key_prefix": key[:6] + "..."}
    else:
        status = HealthStatus.SKIPPED
        message = "OPENAI_API_KEY is not set (optional)"
        details = None

    return HealthCheck(
        name="openai_api_key",
        category=CheckCategory.AGENTS,
        status=status,
        message=message,
        details=details,
        duration_ms=(time.time() - start) * 1000,
    )


@register_check(
    "google_api_key",
    CheckCategory.AGENTS,
    description="Check if GOOGLE_API_KEY is set",
)
def check_google_api_key() -> HealthCheck:
    """Check if Google API key is configured."""
    start = time.time()
    key = _get_env_key("GOOGLE_API_KEY")

    if key:
        status = HealthStatus.HEALTHY
        message = "GOOGLE_API_KEY is configured"
        details = {"key_prefix": key[:8] + "..."}
    else:
        status = HealthStatus.SKIPPED
        message = "GOOGLE_API_KEY is not set (optional)"
        details = None

    return HealthCheck(
        name="google_api_key",
        category=CheckCategory.AGENTS,
        status=status,
        message=message,
        details=details,
        duration_ms=(time.time() - start) * 1000,
    )


@register_check(
    "claude_connectivity",
    CheckCategory.AGENTS,
    requires_api_call=True,
    description="Test Claude agent connectivity with real API call",
)
def check_claude_connectivity(framework: Optional[Any] = None) -> HealthCheck:
    """Test Claude agent connectivity with a minimal API call."""
    start = time.time()

    # Check if API key exists first
    if not _get_env_key("ANTHROPIC_API_KEY"):
        return HealthCheck(
            name="claude_connectivity",
            category=CheckCategory.AGENTS,
            status=HealthStatus.SKIPPED,
            message="Skipped: ANTHROPIC_API_KEY not set",
            duration_ms=(time.time() - start) * 1000,
        )

    try:
        from startd8.agents import ClaudeAgent

        # Use a minimal, fast model for connectivity test
        agent = ClaudeAgent(
            name="diagnostic-test",
            model="claude-3-haiku-20240307",  # Fastest/cheapest
        )

        # Minimal prompt to test connectivity
        response, tokens, _ = agent.generate("Say 'OK' and nothing else.")

        if response and "OK" in response.upper():
            status = HealthStatus.HEALTHY
            message = "Claude agent connected successfully"
            details = {"tokens_used": tokens, "response_preview": response[:50]}
        else:
            status = HealthStatus.WARNING
            message = "Claude responded but unexpectedly"
            details = {"response_preview": response[:100] if response else None}

    except ImportError as e:
        status = HealthStatus.CRITICAL
        message = f"Failed to import ClaudeAgent: {e}"
        details = {"error_type": "ImportError"}
    except Exception as e:
        status = HealthStatus.CRITICAL
        message = f"Claude connectivity failed: {type(e).__name__}"
        details = {"error": str(e)[:200]}

    return HealthCheck(
        name="claude_connectivity",
        category=CheckCategory.AGENTS,
        status=status,
        message=message,
        details=details,
        duration_ms=(time.time() - start) * 1000,
    )


@register_check(
    "openai_connectivity",
    CheckCategory.AGENTS,
    requires_api_call=True,
    description="Test OpenAI agent connectivity with real API call",
)
def check_openai_connectivity(framework: Optional[Any] = None) -> HealthCheck:
    """Test OpenAI agent connectivity with a minimal API call."""
    start = time.time()

    # Check if API key exists first
    if not _get_env_key("OPENAI_API_KEY"):
        return HealthCheck(
            name="openai_connectivity",
            category=CheckCategory.AGENTS,
            status=HealthStatus.SKIPPED,
            message="Skipped: OPENAI_API_KEY not set",
            duration_ms=(time.time() - start) * 1000,
        )

    try:
        from startd8.agents import GPT4Agent

        # Use a minimal, fast model for connectivity test
        agent = GPT4Agent(
            name="diagnostic-test",
            model="gpt-4o-mini",  # Fastest/cheapest GPT-4 variant
        )

        # Minimal prompt to test connectivity
        response, tokens, _ = agent.generate("Say 'OK' and nothing else.")

        if response and "OK" in response.upper():
            status = HealthStatus.HEALTHY
            message = "OpenAI agent connected successfully"
            details = {"tokens_used": tokens, "response_preview": response[:50]}
        else:
            status = HealthStatus.WARNING
            message = "OpenAI responded but unexpectedly"
            details = {"response_preview": response[:100] if response else None}

    except ImportError as e:
        status = HealthStatus.CRITICAL
        message = f"Failed to import GPT4Agent: {e}"
        details = {"error_type": "ImportError"}
    except Exception as e:
        status = HealthStatus.CRITICAL
        message = f"OpenAI connectivity failed: {type(e).__name__}"
        details = {"error": str(e)[:200]}

    return HealthCheck(
        name="openai_connectivity",
        category=CheckCategory.AGENTS,
        status=status,
        message=message,
        details=details,
        duration_ms=(time.time() - start) * 1000,
    )


@register_check(
    "gemini_connectivity",
    CheckCategory.AGENTS,
    requires_api_call=True,
    description="Test Gemini agent connectivity with real API call",
)
def check_gemini_connectivity(framework: Optional[Any] = None) -> HealthCheck:
    """Test Gemini agent connectivity with a minimal API call."""
    start = time.time()

    # Check if API key exists first
    if not _get_env_key("GOOGLE_API_KEY"):
        return HealthCheck(
            name="gemini_connectivity",
            category=CheckCategory.AGENTS,
            status=HealthStatus.SKIPPED,
            message="Skipped: GOOGLE_API_KEY not set",
            duration_ms=(time.time() - start) * 1000,
        )

    try:
        from startd8.agents import GeminiAgent

        # Use a fast model for connectivity test
        agent = GeminiAgent(
            name="diagnostic-test",
            model="gemini-2.0-flash",  # Fast/cheap
        )

        # Minimal prompt to test connectivity
        response, tokens, _ = agent.generate("Say 'OK' and nothing else.")

        if response and "OK" in response.upper():
            status = HealthStatus.HEALTHY
            message = "Gemini agent connected successfully"
            details = {"tokens_used": tokens, "response_preview": response[:50]}
        else:
            status = HealthStatus.WARNING
            message = "Gemini responded but unexpectedly"
            details = {"response_preview": response[:100] if response else None}

    except ImportError as e:
        status = HealthStatus.CRITICAL
        message = f"Failed to import GeminiAgent: {e}"
        details = {"error_type": "ImportError"}
    except Exception as e:
        status = HealthStatus.CRITICAL
        message = f"Gemini connectivity failed: {type(e).__name__}"
        details = {"error": str(e)[:200]}

    return HealthCheck(
        name="gemini_connectivity",
        category=CheckCategory.AGENTS,
        status=status,
        message=message,
        details=details,
        duration_ms=(time.time() - start) * 1000,
    )


@register_check(
    "agent_imports",
    CheckCategory.AGENTS,
    description="Verify all agent modules can be imported",
)
def check_agent_imports() -> HealthCheck:
    """Check that all agent modules can be imported successfully."""
    start = time.time()
    import_results: Dict[str, str] = {}
    all_success = True

    agents_to_check = [
        ("ClaudeAgent", "startd8.agents"),
        ("GPT4Agent", "startd8.agents"),
        ("GeminiAgent", "startd8.agents"),
        ("OpenAICompatibleAgent", "startd8.agents"),
        ("MockAgent", "startd8.agents"),
    ]

    for agent_name, module_path in agents_to_check:
        try:
            module = __import__(module_path, fromlist=[agent_name])
            getattr(module, agent_name)
            import_results[agent_name] = "OK"
        except ImportError as e:
            import_results[agent_name] = f"ImportError: {e}"
            all_success = False
        except AttributeError as e:
            import_results[agent_name] = f"AttributeError: {e}"
            all_success = False

    if all_success:
        status = HealthStatus.HEALTHY
        message = f"All {len(agents_to_check)} agent modules imported successfully"
    else:
        failed = sum(1 for v in import_results.values() if v != "OK")
        status = HealthStatus.CRITICAL
        message = f"{failed}/{len(agents_to_check)} agent imports failed"

    return HealthCheck(
        name="agent_imports",
        category=CheckCategory.AGENTS,
        status=status,
        message=message,
        details=import_results,
        duration_ms=(time.time() - start) * 1000,
    )


@register_check(
    "circuit_breaker_states",
    CheckCategory.AGENTS,
    requires_framework=True,
    description="Check circuit breaker states for all registered agents",
)
def check_circuit_breaker_states(framework: Optional[Any] = None) -> HealthCheck:
    """Check if any agents have tripped circuit breakers."""
    start = time.time()

    if framework is None:
        return HealthCheck(
            name="circuit_breaker_states",
            category=CheckCategory.AGENTS,
            status=HealthStatus.SKIPPED,
            message="Skipped: No framework provided",
            duration_ms=(time.time() - start) * 1000,
        )

    try:
        # Check if framework has agents with circuit breakers
        if not hasattr(framework, "agents"):
            return HealthCheck(
                name="circuit_breaker_states",
                category=CheckCategory.AGENTS,
                status=HealthStatus.SKIPPED,
                message="Framework has no registered agents",
                duration_ms=(time.time() - start) * 1000,
            )

        open_breakers = []
        half_open = []
        closed = []

        for name, agent in framework.agents.items():
            if hasattr(agent, "circuit_breaker"):
                cb = agent.circuit_breaker
                if hasattr(cb, "state"):
                    state = cb.state
                    if state == "open":
                        open_breakers.append(name)
                    elif state == "half_open":
                        half_open.append(name)
                    else:
                        closed.append(name)

        if open_breakers:
            status = HealthStatus.CRITICAL
            message = f"{len(open_breakers)} agents have open circuit breakers"
        elif half_open:
            status = HealthStatus.WARNING
            message = f"{len(half_open)} agents recovering from circuit break"
        else:
            status = HealthStatus.HEALTHY
            message = f"All {len(closed)} circuit breakers closed"

        return HealthCheck(
            name="circuit_breaker_states",
            category=CheckCategory.AGENTS,
            status=status,
            message=message,
            details={
                "open": open_breakers,
                "half_open": half_open,
                "closed": closed,
            },
            duration_ms=(time.time() - start) * 1000,
        )

    except Exception as e:
        return HealthCheck(
            name="circuit_breaker_states",
            category=CheckCategory.AGENTS,
            status=HealthStatus.UNKNOWN,
            message=f"Failed to check circuit breakers: {e}",
            duration_ms=(time.time() - start) * 1000,
        )
