"""Shared prompt utilities used by both artisan and prime contractor routes."""


def format_constraints(constraints: list[str]) -> str:
    """Group constraints by [BINDING]/[STRUCTURAL]/[ADVISORY] prefix."""
    groups: dict[str, list[str]] = {
        "binding": [],
        "structural": [],
        "advisory": [],
        "other": [],
    }
    for c in constraints:
        if c.startswith("[BINDING] "):
            groups["binding"].append(c[10:])
        elif c.startswith("[STRUCTURAL] "):
            groups["structural"].append(c[13:])
        elif c.startswith("[ADVISORY] "):
            groups["advisory"].append(c[11:])
        else:
            groups["other"].append(c)
    parts: list[str] = []
    if groups["binding"]:
        parts.append("### Binding (must not violate)")
        parts.extend(f"- {c}" for c in groups["binding"])
    if groups["structural"]:
        parts.append("### Structural (code organization)")
        parts.extend(f"- {c}" for c in groups["structural"])
    if groups["advisory"]:
        parts.append("### Advisory (prefer but not blocking)")
        parts.extend(f"- {c}" for c in groups["advisory"])
    if groups["other"]:
        parts.extend(f"- {c}" for c in groups["other"])
    return "\n".join(parts)


def find_missing_parameters(
    text: str,
    resolved_parameters: list[dict],
) -> list[dict]:
    """Return resolved parameters whose key_value is not found in text."""
    missing = []
    for param in resolved_parameters:
        key_value = param.get("key_value", "")
        if key_value and key_value not in text:
            missing.append(param)
    return missing
