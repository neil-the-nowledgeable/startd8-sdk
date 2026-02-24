"""Composable prompt modules for the v2 design phase.

Each module answers one question an implementer asks:
- Identity:     What am I building?
- Constraints:  What rules apply?
- Enrichment:   What are the ground-truth parameter names and conventions?
- PriorArt:     What already exists?
- Scope:        How big should this be?
- Guidance:     Any advisory hints?

Modules extract data from the enriched seed (via seed_mapping), then
render it into a PromptFragment with a token estimate and droppability flag.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from startd8.contractors.prompt_utils import format_constraints


@dataclass(frozen=True)
class PromptFragment:
    """A rendered piece of prompt text with metadata."""

    category: str  # "identity" | "constraints" | "prior_art" | "scope" | "guidance"
    text: str
    token_estimate: int  # len(text) // 4
    droppable: bool


def _estimate_tokens(text: str) -> int:
    return len(text) // 4


# ---------------------------------------------------------------------------
# Identity: What am I building?
# ---------------------------------------------------------------------------


class IdentityModule:
    """Renders task identity: name, description, target files."""

    category = "identity"

    def render(self, data: dict[str, Any]) -> PromptFragment:
        lines = ["## Task"]
        lines.append(f"**{data['task_id']}:** {data['title']}")

        desc = data.get("description", "")
        if desc:
            lines.append(f"\n{desc}")

        target_files = data.get("target_files", [])
        file_scope = data.get("file_scope", {})
        existing_files = set(data.get("existing_files", []))
        if target_files:
            lines.append("\n**Target Files:**")
            for tf in target_files:
                scope_tag = file_scope.get(tf, "")
                if tf in existing_files:
                    annotation = "modify"
                else:
                    annotation = "create"
                scope_note = f", {scope_tag}" if scope_tag and scope_tag != "primary" else ""
                lines.append(f"- `{tf}` ({annotation}{scope_note})")

        text = "\n".join(lines)
        return PromptFragment(
            category=self.category,
            text=text,
            token_estimate=_estimate_tokens(text),
            droppable=False,
        )


# ---------------------------------------------------------------------------
# Constraints: What rules apply?
# ---------------------------------------------------------------------------


class ConstraintsModule:
    """Renders binding constraints, API signatures, protocol, negative scope."""

    category = "constraints"

    def render(self, data: dict[str, Any]) -> PromptFragment:
        parts: list[str] = []

        # API signatures (verbatim from plan -- Mottainai rule 2)
        api_sigs = data.get("api_signatures", [])
        if api_sigs:
            parts.append("**API Signatures (preserve exactly):**")
            for sig in api_sigs:
                parts.append(f"- `{sig}`")

        # Protocol constraint
        protocol = data.get("protocol", "")
        if protocol:
            parts.append(f"**Transport protocol:** {protocol}")

        # Prompt constraints (grouped by tag)
        constraints = data.get("prompt_constraints", [])
        arch_constraints = data.get("arch_constraints", [])
        all_constraints = list(constraints) + [
            f"[BINDING] {c.get('rule', str(c))}" if isinstance(c, dict) else str(c)
            for c in arch_constraints
        ]
        if all_constraints:
            formatted = format_constraints(all_constraints)
            if formatted:
                parts.append(formatted)

        # Negative scope
        negative_scope = data.get("negative_scope", [])
        if negative_scope:
            parts.append("\n**Out of Scope:**")
            for ns in negative_scope:
                parts.append(f"- {ns}")

        if not parts:
            text = ""
        else:
            text = "## Constraints\n" + "\n".join(parts)

        return PromptFragment(
            category=self.category,
            text=text,
            token_estimate=_estimate_tokens(text),
            droppable=False,
        )


# ---------------------------------------------------------------------------
# Enrichment: Ground-truth parameter names and conventions (Mottainai 2, 5)
# ---------------------------------------------------------------------------


class EnrichmentModule:
    """Renders parameter provenance and naming conventions.

    These are deterministic values resolved by the pipeline. Rendering them
    in the design prompt ensures the LLM uses exact names/types rather than
    inventing alternatives (Mottainai rule 5: forward, don't regenerate).
    """

    category = "enrichment"

    def render(self, data: dict[str, Any]) -> PromptFragment:
        parts: list[str] = []

        param_sources = data.get("parameter_sources", {})
        if param_sources:
            parts.append("**Parameter Sources (use these names exactly):**")
            for name, source in list(param_sources.items())[:20]:
                if isinstance(source, dict):
                    origin = source.get("origin", source.get("source", ""))
                    parts.append(f"- `{name}`: {origin}")
                else:
                    parts.append(f"- `{name}`: {source}")

        conventions = data.get("semantic_conventions", {})
        if conventions:
            parts.append("**Semantic Conventions (naming rules):**")
            for key, value in list(conventions.items())[:10]:
                if isinstance(value, dict):
                    rule = value.get("rule", value.get("convention", str(value)))
                    parts.append(f"- {key}: {rule}")
                else:
                    parts.append(f"- {key}: {value}")

        if not parts:
            return PromptFragment(
                category=self.category,
                text="",
                token_estimate=0,
                droppable=False,
            )

        text = "## Parameter Provenance\n" + "\n".join(parts)
        return PromptFragment(
            category=self.category,
            text=text,
            token_estimate=_estimate_tokens(text),
            droppable=False,
        )


# ---------------------------------------------------------------------------
# Prior Art: What already exists?
# ---------------------------------------------------------------------------


class PriorArtModule:
    """Renders prior art: dependency designs, existing files, staleness."""

    category = "prior_art"

    def render(self, data: dict[str, Any]) -> PromptFragment:
        lines = ["## Prior Art"]
        has_content = False

        # Dependency designs (non-droppable part)
        dep_designs = data.get("dependency_designs", {})
        if dep_designs:
            has_content = True
            lines.append("**Depends on:**")
            for dep_id, summary in list(dep_designs.items())[:3]:
                # Truncate summaries to first line
                first_line = summary.split("\n", 1)[0][:200]
                lines.append(f"- {dep_id}: {first_line}")

        # Existing files with staleness
        existing = data.get("existing_files", [])
        staleness = data.get("staleness", {})
        if existing:
            has_content = True
            lines.append("**Existing files:**")
            for f in existing:
                status = staleness.get(f, "unknown")
                lines.append(f"- `{f}` ({status})")

        # Prior design summaries (droppable)
        summaries = data.get("summaries", [])
        if summaries:
            has_content = True
            lines.append("**Other designs:**")
            for s in summaries[-5:]:
                lines.append(f"- {s}")

        if not has_content:
            return PromptFragment(
                category=self.category,
                text="",
                token_estimate=0,
                droppable=True,
            )

        text = "\n".join(lines)
        return PromptFragment(
            category=self.category,
            text=text,
            token_estimate=_estimate_tokens(text),
            droppable=True,
        )


# ---------------------------------------------------------------------------
# Scope: How big should this be?
# ---------------------------------------------------------------------------


class ScopeModule:
    """Renders scope boundaries: LOC, depth, wave context."""

    category = "scope"

    def render(self, data: dict[str, Any]) -> PromptFragment:
        parts: list[str] = []

        loc = data.get("estimated_loc")
        if loc:
            parts.append(f"**Estimated LOC:** {loc}")

        depth = data.get("depth_tier")
        if depth:
            parts.append(f"**Depth:** {depth}")

        wave_index = data.get("wave_index")
        wave_count = data.get("wave_count")
        if wave_index is not None and wave_count:
            parts.append(
                f"**Wave:** {wave_index + 1} of {wave_count} "
                "(parallel tasks -- avoid implicit ordering dependencies)"
            )

        if not parts:
            return PromptFragment(
                category=self.category,
                text="",
                token_estimate=0,
                droppable=False,
            )

        text = "## Scope\n" + "\n".join(parts)
        return PromptFragment(
            category=self.category,
            text=text,
            token_estimate=_estimate_tokens(text),
            droppable=False,
        )


# ---------------------------------------------------------------------------
# Guidance: Any advisory hints?
# ---------------------------------------------------------------------------


class GuidanceModule:
    """Renders advisory guidance: domain, goals, refine suggestions, open questions."""

    category = "guidance"

    def render(self, data: dict[str, Any]) -> PromptFragment:
        parts: list[str] = []

        domain = data.get("domain")
        if domain:
            parts.append(f"**Domain:** {domain}")

        goals = data.get("plan_goals", [])
        if goals:
            goal_list = ", ".join(goals[:3])
            parts.append(f"**Project goals:** {goal_list}")

        suggestions = data.get("refine_suggestions")
        if suggestions:
            if isinstance(suggestions, list):
                items = suggestions[:5]
                formatted = "; ".join(
                    s.get("suggestion", str(s)) if isinstance(s, dict) else str(s)
                    for s in items
                )
                parts.append(f"**Review suggestions:** {formatted}")
            elif isinstance(suggestions, str) and suggestions.strip():
                parts.append(f"**Review suggestions:** {suggestions[:300]}")

        questions = data.get("open_questions", [])
        if questions:
            q_list = [
                q["question"] if isinstance(q, dict) else str(q)
                for q in questions[:3]
            ]
            parts.append("**Open questions:** " + "; ".join(q_list))

        alerts = data.get("complexity_alerts", {})
        if alerts:
            alert_parts = [f"{dim} ({score})" for dim, score in alerts.items()]
            parts.append(f"**Complexity alerts:** {', '.join(alert_parts)}")

        if not parts:
            return PromptFragment(
                category=self.category,
                text="",
                token_estimate=0,
                droppable=True,
            )

        text = "## Guidance (advisory)\n" + "\n".join(parts)
        return PromptFragment(
            category=self.category,
            text=text,
            token_estimate=_estimate_tokens(text),
            droppable=True,
        )
