"""Deterministic structural pattern extraction from exemplar code summaries.

Extracts language-agnostic architectural patterns (lifecycle phases,
middleware points, config keys, error strategy) using regex and keyword
heuristics. No LLM calls — pure string analysis.
"""

from __future__ import annotations

import re
from typing import Optional

from startd8.exemplars.models import StructuralPattern
from startd8.logging_config import get_logger

logger = get_logger(__name__)

__all__ = ["extract_structural_pattern"]


# --- Lifecycle phase detection ---
# Two-tier keyword matching: compound identifiers (e.g. "GracefulStop") use
# plain substring `in`, while common English words (e.g. "health", "shutdown")
# use word-boundary regex to avoid false positives on unrelated code.
# See [SDK Leg 13 #44] — bare `in` on short words matches too broadly.
_LIFECYCLE_KEYWORDS: dict[str, list[str]] = {
    "create": [
        "NewServer", "new_server", "create_server", "Server(",
        "net.Listen", "grpc.NewServer", "http.Server{",
    ],
    "configure": [
        "WithOption", "set_config", "Config{", "options.",
    ],
    "register": [
        "RegisterService", "register_service", "pb.Register", "Handle(",
        "HandleFunc(", "add_service", "register_handler",
    ],
    "middleware": [
        "UnaryInterceptor", "StreamInterceptor",
        "interceptor", "Use(",
    ],
    "health": [
        "grpc_health", "HealthCheck", "healthz",
    ],
    "serve": [
        "Serve(", "serve(", "ListenAndServe",
    ],
    "shutdown": [
        "GracefulStop", "graceful_stop",
        "os.Signal", "signal.Notify", "SIGTERM", "SIGINT",
    ],
}

# Word-boundary patterns for common English words that would false-positive
# with bare substring matching (e.g. "health" in "unhealthy").
_LIFECYCLE_WORD_BOUNDARY: dict[str, re.Pattern[str]] = {
    "configure": re.compile(r"\bconfigure\b", re.IGNORECASE),
    "middleware": re.compile(r"\bmiddleware\b", re.IGNORECASE),
    "health": re.compile(r"\bhealth\b", re.IGNORECASE),
    "serve": re.compile(r"\b(?:listen|start)\(", re.IGNORECASE),
    "shutdown": re.compile(r"\b(?:Shutdown|shutdown)\b"),
}

# --- Middleware/interceptor detection ---
_MIDDLEWARE_KEYWORDS: dict[str, list[str]] = {
    "logging": ["log.", "Log(", "zap.", "logrus."],
    "auth": ["auth", "Auth", "jwt", "JWT", "credentials"],
    "recovery": ["recovery", "Recovery", "recover()", "panic"],
    "tracing": ["otel", "opentelemetry", "jaeger"],
    "metrics": ["prometheus"],
    "ratelimit": ["limiter", "throttle"],
    "cors": ["cors", "CORS", "Access-Control"],
    "compression": ["gzip", "deflate"],
}

# Word-boundary patterns for middleware keywords that are common words.
_MIDDLEWARE_WORD_BOUNDARY: dict[str, re.Pattern[str]] = {
    "logging": re.compile(r"\b(?:logging|logger)\b"),
    "auth": re.compile(r"\b(?:token|Token)\b"),
    "tracing": re.compile(r"\b(?:trace|Trace|span)\b"),
    "metrics": re.compile(r"\b(?:metrics|Metrics|counter|histogram)\b"),
    "ratelimit": re.compile(r"\b(?:rate|Rate)\b"),
    "compression": re.compile(r"\bcompress\b"),
}

# --- Config key detection ---
_CONFIG_PATTERNS = re.compile(
    r"(?:port|host|addr|address|tls[_-]?cert|tls[_-]?key|timeout|max[_-]?connections|"
    r"database[_-]?url|redis[_-]?url|grpc[_-]?port|http[_-]?port|listen[_-]?addr)",
    re.IGNORECASE,
)

# --- Error strategy detection ---
_ERROR_STRATEGIES: dict[str, list[str]] = {
    "graceful_shutdown": [
        "GracefulStop", "graceful_stop", "os.Signal", "SIGTERM",
    ],
    "panic_recover": ["recover()", "panic", "Recovery"],
    "retry": ["retry", "Retry", "backoff", "Backoff"],
    "circuit_breaker": ["CircuitBreaker"],
    "fallback": ["Fallback"],
}

_ERROR_STRATEGY_WORD_BOUNDARY: dict[str, re.Pattern[str]] = {
    "graceful_shutdown": re.compile(r"\b(?:graceful|Shutdown\(|shutdown\()"),
    "circuit_breaker": re.compile(r"\b(?:circuit|breaker)\b", re.IGNORECASE),
    "fallback": re.compile(r"\b(?:fallback|default)\b", re.IGNORECASE),
}


def extract_structural_pattern(
    code_summary: str,
    archetype: str,
    source_language: str,
    source_fingerprint: str,
) -> Optional[StructuralPattern]:
    """Extract a structural pattern from exemplar code summary text.

    Uses keyword matching and regex — no LLM calls. Returns None if
    insufficient structural signal is detected (fewer than 2 lifecycle
    phases).

    Args:
        code_summary: First ~50 lines of the exemplar's generated code.
        archetype: The exemplar's archetype (e.g. "grpc_server").
        source_language: Language the code was written in.
        source_fingerprint: Full fingerprint string.

    Returns:
        StructuralPattern if sufficient signal, None otherwise.
    """
    if not code_summary or len(code_summary.strip()) < 20:
        return None

    # Detect lifecycle phases (two-tier: compound substring + word-boundary regex)
    phases = []
    for phase, keywords in _LIFECYCLE_KEYWORDS.items():
        if any(kw in code_summary for kw in keywords):
            phases.append(phase)
        elif phase in _LIFECYCLE_WORD_BOUNDARY and _LIFECYCLE_WORD_BOUNDARY[phase].search(code_summary):
            phases.append(phase)

    if len(phases) < 2:
        logger.debug(
            "Insufficient lifecycle phases for %s (found %d): %s",
            archetype, len(phases), phases,
        )
        return None

    # Detect middleware points (two-tier: compound substring + word-boundary regex)
    middleware = []
    for mw_name, keywords in _MIDDLEWARE_KEYWORDS.items():
        if any(kw in code_summary for kw in keywords):
            middleware.append(mw_name)
        elif mw_name in _MIDDLEWARE_WORD_BOUNDARY and _MIDDLEWARE_WORD_BOUNDARY[mw_name].search(code_summary):
            middleware.append(mw_name)

    # Detect config keys
    config_keys = list(dict.fromkeys(  # preserve order, deduplicate
        m.group(0).lower().replace("-", "_")
        for m in _CONFIG_PATTERNS.finditer(code_summary)
    ))

    # Detect error strategy (two-tier matching)
    error_strategy = "unknown"
    for strategy, keywords in _ERROR_STRATEGIES.items():
        if any(kw in code_summary for kw in keywords):
            error_strategy = strategy
            break
        if strategy in _ERROR_STRATEGY_WORD_BOUNDARY and _ERROR_STRATEGY_WORD_BOUNDARY[strategy].search(code_summary):
            error_strategy = strategy
            break

    pattern = StructuralPattern(
        archetype=archetype,
        lifecycle_phases=tuple(phases),
        middleware_points=tuple(middleware),
        config_keys=tuple(config_keys),
        error_strategy=error_strategy,
        source_language=source_language,
        source_fingerprint=source_fingerprint,
    )

    logger.info(
        "Extracted structural pattern for %s: %d phases, %d middleware, %d config keys",
        archetype, len(phases), len(middleware), len(config_keys),
    )
    return pattern
