"""Constants, utility functions, agent detection, and dataclasses for the architectural review workflow.

This is the **leaf** module in the dependency DAG — it has no local imports
from other ``architectural_review_log_*`` modules.
"""

from __future__ import annotations

import re
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Generator, List, Optional, Sequence, Set, Tuple

from ...agents import BaseAgent
from ...logging_config import get_logger
from ...model_catalog import Models, list_models_by_tier
from ...utils.token_usage import token_usage_input, token_usage_output, token_usage_cost
from ..models import StepResult

_logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Relaxed safety settings for technical document review.
# Architectural plans mention "risks", "vulnerabilities", "attack surfaces", etc.
# which can trip Gemini's DANGEROUS_CONTENT filter on benign content.
RELAXED_SAFETY_SETTINGS = [
    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_ONLY_HIGH"},
    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_ONLY_HIGH"},
    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_ONLY_HIGH"},
    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
]


APPENDIX_HEADING = "## Appendix: Iterative Review Log (Applied / Rejected Suggestions)"

# This matches the appendix scaffold we already introduced in target docs.
APPENDIX_TEMPLATE = """---

## Appendix: Iterative Review Log (Applied / Rejected Suggestions)

This appendix is intentionally **append-only**. New reviewers (human or model) should add suggestions to Appendix C, and then once validated, record the final disposition in Appendix A (applied) or Appendix B (rejected with rationale).

### Reviewer Instructions (for humans + models)

- **Before suggesting changes**: Scan Appendix A and Appendix B first. Do **not** re-suggest items already applied or explicitly rejected.
- **When proposing changes**: Append them to Appendix C using a unique suggestion ID (`R{round}-S{n}`).
- **When endorsing prior suggestions**: If you agree with an untriaged suggestion from a prior round, list it in an **Endorsements** section after your suggestion table. This builds consensus signal — suggestions endorsed by multiple reviewers should be prioritized during triage.
- **When validating**: For each suggestion, append a row to Appendix A (if applied) or Appendix B (if rejected) referencing the suggestion ID. Endorsement counts inform priority but do not auto-apply suggestions.
- **If rejecting**: Record **why** (specific rationale) so future models don't re-propose the same idea.

### Appendix A: Applied Suggestions

| ID | Suggestion | Source | Implementation / Validation Notes | Date |
|----|------------|--------|----------------------------------|------|
| (none yet) |  |  |  |  |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none yet) |  |  |  |

### Appendix C: Incoming Suggestions (Untriaged, append-only)
"""


ALLOWED_AREAS = {
    "architecture",
    "interfaces",
    "data",
    "risks",
    "validation",
    "ops",
    "security",
}

# Map common LLM-generated area synonyms to canonical ALLOWED_AREAS values.
# When a reviewer outputs a non-canonical area name, normalize it before
# validation or coverage computation.
_AREA_ALIASES: Dict[str, str] = {
    # architecture synonyms
    "design": "architecture",
    "structure": "architecture",
    "modularity": "architecture",
    "scalability": "architecture",
    "maintainability": "architecture",
    "extensibility": "architecture",
    # interfaces synonyms
    "api": "interfaces",
    "apis": "interfaces",
    "contracts": "interfaces",
    "integration": "interfaces",
    # data synonyms
    "data model": "data",
    "data models": "data",
    "storage": "data",
    "database": "data",
    "persistence": "data",
    # risks synonyms
    "risk": "risks",
    "reliability": "risks",
    "resilience": "risks",
    "fault tolerance": "risks",
    "error handling": "risks",
    # validation synonyms
    "testing": "validation",
    "testability": "validation",
    "test": "validation",
    "quality": "validation",
    "completeness": "validation",
    # ops synonyms
    "operations": "ops",
    "deployment": "ops",
    "observability": "ops",
    "monitoring": "ops",
    "performance": "ops",
    "infrastructure": "ops",
    # security synonyms (already canonical, but add common variants)
    "auth": "security",
    "authentication": "security",
    "authorization": "security",
    # clarity — maps to architecture (document/design clarity)
    "clarity": "architecture",
    "readability": "architecture",
    "documentation": "architecture",
}


def _normalize_area(area: str, allowed: Optional[Set[str]] = None) -> str:
    """Normalize an area name to a canonical ALLOWED_AREAS value."""
    key = area.strip().lower()
    areas = allowed or ALLOWED_AREAS
    if key in areas:
        return key
    return _AREA_ALIASES.get(key, key)


REVIEW_PROFILES = {
    "architecture": {
        "areas": ALLOWED_AREAS,
        "persona": "expert enterprise architect",
        "focus": "architecture clarity, execution safety, risk management, validation completeness, and operational readiness",
    },
    "requirements": {
        "areas": {
            "ambiguity", "completeness", "consistency", "testability", "traceability", "feasibility"
        },
        "persona": "expert requirements analyst",
        "focus": "clarity, completeness, testability, consistency, and feasibility",
    },
    "design": {
        "areas": {
            "architecture", "clarity", "completeness", "maintainability", "scalability", "security", "testability"
        },
        "persona": "expert software designer",
        "focus": "clarity, completeness, maintainability, scalability, and testability",
    }
}

ALLOWED_SEVERITIES = {"critical", "high", "medium", "low"}

CORE_COLUMNS = [
    "ID",
    "Area",
    "Severity",
    "Suggestion",
    "Rationale",
]

OPTIONAL_COLUMNS = [
    "Proposed Placement",
    "Validation Approach",
]

# Full column list — used for prompt generation and display formatting.
# Validation only enforces CORE_COLUMNS; OPTIONAL_COLUMNS default to
# _OPTIONAL_COLUMN_DEFAULT when missing from LLM output.
REQUIRED_COLUMNS = CORE_COLUMNS + OPTIONAL_COLUMNS
_OPTIONAL_COLUMN_DEFAULT = "N/A"


# ---------------------------------------------------------------------------
# Agent detection helpers
# ---------------------------------------------------------------------------

def _is_agent_type(agent: BaseAgent, module_suffix: str) -> bool:
    """Check if *agent* belongs to a specific provider by module path suffix."""
    mod = getattr(agent.__class__, "__module__", "") or ""
    return f".agents.{module_suffix}" in mod or mod.endswith(f"agents.{module_suffix}")


def _is_openai_agent(agent: BaseAgent) -> bool:
    return _is_agent_type(agent, "openai")


def _is_gemini_agent(agent: BaseAgent) -> bool:
    return _is_agent_type(agent, "gemini")


def _is_anthropic_agent(agent: BaseAgent) -> bool:
    return _is_agent_type(agent, "claude")


def _looks_like_model_not_found_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    return ("model" in msg and ("not found" in msg or "not available" in msg or "does not exist" in msg))


# ---------------------------------------------------------------------------
# Safety / token / selection helpers
# ---------------------------------------------------------------------------

@contextmanager
def _relaxed_safety(agent: BaseAgent) -> Generator[None, None, None]:
    """Temporarily apply relaxed safety settings to a Gemini agent, restoring on exit."""
    original_safety = getattr(agent, "safety_settings", None)
    try:
        if _is_gemini_agent(agent):
            agent.safety_settings = RELAXED_SAFETY_SETTINGS
        yield
    finally:
        if _is_gemini_agent(agent):
            agent.safety_settings = original_safety


def _extract_token_metrics(token_usage: Any) -> Tuple[int, int, float]:
    """Extract (input_tokens, output_tokens, cost) from a token_usage object, defaulting to zero."""
    if not token_usage:
        return 0, 0, 0.0
    return (
        token_usage_input(token_usage),
        token_usage_output(token_usage),
        token_usage_cost(token_usage),
    )


def _select_default_agents(
    quality_tier: str,
    reviewer_count: int,
    providers: Optional[Sequence[str]] = None,
) -> List[str]:
    """
    Select default models by tier from the model catalog.

    Returns a list of agent specs in provider:model format.
    """
    tier = (quality_tier or "flagship").strip().lower()

    # For strategic architectural review, default to Opus + Gemini Pro.
    # OpenAI o3 removed from defaults due to org TPM limits vs large prompts.
    # Users can add other models (e.g. mistral:mistral-large-latest) via
    # the "agents" config or the "providers" allowlist.
    _KNOWN_TIERS = {"flagship", "balanced", "fast", "mini"}
    if tier not in _KNOWN_TIERS:
        _logger.warning(
            "Unknown quality_tier '%s' (expected one of %s); "
            "falling back to tier-registry lookup",
            tier, sorted(_KNOWN_TIERS),
        )

    preferred: List[str] = []
    if tier == "flagship":
        preferred = [
            Models.CLAUDE_OPUS_LATEST,
            Models.GEMINI_PRO_LATEST,
        ]

    # Apply provider allowlist to preferred first (preserving order)
    allowed: Optional[set[str]] = None
    if providers:
        allowed = {p.strip().lower() for p in providers if p and p.strip()}
        preferred = [m for m in preferred if m.split(":", 1)[0].lower() in allowed]

    if len(preferred) >= reviewer_count:
        return preferred[:reviewer_count]

    # Fill remaining slots from tier registry (stable, provider-prioritized)
    remainder = [m for m in list_models_by_tier(tier) if m not in preferred]
    if allowed is not None:
        remainder = [m for m in remainder if m.split(":", 1)[0].lower() in allowed]

    priority = {"anthropic": 0, "gemini": 1, "mistral": 2, "openai": 3}
    remainder.sort(key=lambda full: (priority.get(full.split(":", 1)[0].lower(), 99), full))

    return (preferred + remainder)[:reviewer_count]


# ---------------------------------------------------------------------------
# Text utilities
# ---------------------------------------------------------------------------

def _now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _strip_code_fences(text: str) -> str:
    """Strip markdown code-block fences (```markdown ... ```) from LLM output."""
    stripped = text.strip()
    # Match ```markdown, ```md, or bare ``` at start
    if re.match(r"^```(?:markdown|md)?\s*\n", stripped, re.IGNORECASE):
        stripped = re.sub(r"^```(?:markdown|md)?\s*\n", "", stripped, count=1, flags=re.IGNORECASE)
        # Remove trailing ``` (possibly with trailing whitespace)
        stripped = re.sub(r"\n```\s*$", "", stripped)
    return stripped


def _strip_json_fences(text: str) -> str:
    """Strip ```json ``` fences from LLM output."""
    stripped = text.strip()
    if re.match(r"^```(?:json)?\s*\n", stripped, re.IGNORECASE):
        stripped = re.sub(r"^```(?:json)?\s*\n", "", stripped, count=1, flags=re.IGNORECASE)
        stripped = re.sub(r"\n```\s*$", "", stripped)
    return stripped


def _split_cells(row: str) -> List[str]:
    return [c.strip() for c in row.strip().strip("|").split("|")]


def _is_separator_row(stripped: str) -> bool:
    """Detect markdown table separator rows like ``| --- | --- |`` or ``|---|---|``."""
    if not stripped.startswith("|"):
        return False
    cells = _split_cells(stripped)
    return bool(cells) and all(re.fullmatch(r":?-+:?", c) for c in cells if c)


def _normalize_header(cell: str) -> str:
    """Strip markdown bold/italic markers (e.g. **Area**, _Area_) for header comparison."""
    return re.sub(r'^[*_]+|[*_]+$', '', cell.strip()).strip()


def _ensure_appendix_exists(doc: str) -> str:
    if APPENDIX_HEADING in doc:
        return doc
    return doc.rstrip() + "\n\n" + APPENDIX_TEMPLATE


def _strip_appendix_for_prompt(doc: str) -> str:
    idx = doc.find(APPENDIX_HEADING)
    if idx == -1:
        return doc
    return doc[:idx].rstrip() + "\n"


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def _agent_label(agent: BaseAgent) -> str:
    """Format a consistent agent name label for StepResult and logging."""
    return f"{agent.name}:{getattr(agent, 'model', '')}"


def _make_error_step(
    step_name: str,
    agent: BaseAgent,
    error: str,
    *,
    output: str = "",
    time_ms: int = 0,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cost: float = 0.0,
) -> StepResult:
    """Create a StepResult representing a failed step."""
    return StepResult(
        step_name=step_name,
        agent_name=_agent_label(agent),
        output=output,
        time_ms=time_ms,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost=cost,
        error=error,
    )


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class _MetricsAccumulator:
    """Running totals for token usage, cost, and wall-clock time across rounds.

    Used sequentially under ``FileLock`` — not thread-safe.
    """

    input_tokens: int = 0
    output_tokens: int = 0
    cost: float = 0.0
    time_ms: int = 0

    def add(self, input_tokens: int, output_tokens: int, cost: float, time_ms: int) -> None:
        self.input_tokens += input_tokens
        self.output_tokens += output_tokens
        self.cost += cost
        self.time_ms += time_ms


@dataclass
class _RoundRecord:
    """Record of a single completed review round for state persistence."""

    round_number: int
    agent: str
    model: str
    ids: List[str]
    appended_at_utc: str
    cost: float
