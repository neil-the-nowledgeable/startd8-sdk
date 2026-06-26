"""FR-VIP-1/3/5/9 — the value-input fan-out: build-preferences (§2.11) + business-targets (§2.10).

Project-agnostic prose → the value YAMLs, round-tripped through the kickoff_inputs parsers (the
candidate would raise if it failed). Pins: scalar-group / table-per-group extraction, the bool
coercion + int-vs-string target literal, the `not-applicable` monetization expansion, and flag-don't-
guess on an unknown group / a non-bool flag. No project identifiers (FR-VIP-9).
"""

from __future__ import annotations

import yaml

from startd8.manifest_extraction import Status, extract_manifests

_BP_DOC = """
## Build preferences

- Provenance default: config-default

### Budgets
- Per pipeline run: $5.00
- LLM monthly: $25

### Model routing
- Lead tier: anthropic-flagship
- Note: prefer re-route over invention

### Generation
- Profile: full
- Language: python

### Unattended
- Question answers: q.yaml
- Non interactive: false
""".strip()

_BT_DOC = """
## Business targets

- Provenance default: estimate
- Monetization: not-applicable

### Outcomes
| Metric | Target | Why |
|--------|--------|-----|
| on time rate | 95% | core outcome |
| missed events | 0 | zero tolerance |

### Usage
| Metric | Target | Why |
|--------|--------|-----|
| weekly active loggers | 3 | who logs in |

### Per-role goals
| Role | Goal |
|------|------|
| member | I log in under 10 seconds. |

### Mystery group
| Metric | Target | Why |
|--------|--------|-----|
| x | 1 | y |
""".strip()


def _emit(doc, name):
    res = extract_manifests({"reqs.md": doc})
    raw = res.manifests.get(name)
    return (yaml.safe_load(raw) if raw else None), res


# --------------------------------------------------------------------------- build-preferences


def test_build_preferences_extracts():
    got, _ = _emit(_BP_DOC, "build-preferences.yaml")
    assert got["domain"] == "build-preferences"
    assert got["provenance_default"] == "config-default"
    assert got["budgets"] == {"per_pipeline_run": "$5.00", "llm_monthly": "$25"}
    assert got["model_routing"] == {"lead_tier": "anthropic-flagship", "note": "prefer re-route over invention"}
    assert got["generation"] == {"profile": "full", "language": "python"}
    assert got["unattended"]["non_interactive"] is False  # coerced to bool
    assert got["unattended"]["question_answers"] == "q.yaml"


def test_build_preferences_flags_non_bool_flag():
    doc = _BP_DOC.replace("- Non interactive: false", "- Non interactive: maybe")
    got, res = _emit(doc, "build-preferences.yaml")
    assert "non_interactive" not in got.get("unattended", {})
    flagged = [r for r in res.records if r.manifest == "build-preferences.yaml"
               and r.status == Status.NOT_EXTRACTED and r.value_path.endswith("/non_interactive")]
    assert flagged and "boolean" in flagged[0].reason


# --------------------------------------------------------------------------- business-targets


def test_business_targets_extracts():
    got, _ = _emit(_BT_DOC, "business-targets.yaml")
    assert got["domain"] == "business-targets"
    assert got["product_funnel"]["on_time_rate"] == {"target": "95%", "why": "core outcome"}
    assert got["product_funnel"]["missed_events"]["target"] == 0       # bare int kept numeric
    assert got["traction"]["weekly_active_loggers"]["target"] == 3
    assert got["per_role_top_goals"] == {"member": "I log in under 10 seconds."}


def test_monetization_not_applicable_expands():
    got, _ = _emit(_BT_DOC, "business-targets.yaml")
    assert got["monetization"] == {
        "mode_now": "not-applicable",
        "conversion_rate": {"target": "N/A", "status": "not-applicable"},
        "price_point": {"target": "N/A", "status": "not-applicable"},
    }


def test_unknown_group_is_flagged_not_guessed():
    _, res = _emit(_BT_DOC, "business-targets.yaml")
    flagged = [r for r in res.records if r.manifest == "business-targets.yaml"
               and r.status == Status.NOT_EXTRACTED and "mystery" in r.value_path]
    assert flagged and "unknown business-targets group" in flagged[0].reason


def test_unsupported_monetization_value_flagged():
    doc = _BT_DOC.replace("- Monetization: not-applicable", "- Monetization: enabled")
    got, res = _emit(doc, "business-targets.yaml")
    assert "monetization" not in got
    assert any(r.manifest == "business-targets.yaml" and r.status == Status.NOT_EXTRACTED
               and r.value_path == "/monetization" for r in res.records)


def test_absent_sections_emit_nothing():
    got_bp, res = _emit("## Overview\n\nnothing here\n", "build-preferences.yaml")
    assert got_bp is None and "build-preferences.yaml" not in res.manifests
    assert "business-targets.yaml" not in res.manifests
