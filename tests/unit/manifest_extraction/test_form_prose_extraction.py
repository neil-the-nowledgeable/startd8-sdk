"""FR-FH-8 — form help in a requirements doc is deterministically compiled to form_prose.yaml.

Closes the kickoff→manifest loop for the form Words layer: the consumer (`parse_form_prose`) shipped
with E4; this adds the producer (`extract_form_prose`). Pins:
- a `### Form: <Entity>` block's `Intro:` + a `Field | Help | Placeholder` table extract (FR-FH-8);
- entity/field targets resolve against the entity graph — an unknown entity or field is recorded
  NOT_EXTRACTED (sourced, advisory) and dropped, never guessed (FR-FH-5);
- the emitted manifest round-trips through `parse_form_prose` keyed by entity names, so a help block on
  a non-existent entity fails ingestion.
"""

from __future__ import annotations

import yaml

from startd8.manifest_extraction import Status, extract_manifests

_DOC = """
## Entities

### Bill

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| amountCents | int | yes | |
| memo | text | no | |
| weekday | int | no | |

## Form Help

### Form: Bill

- Intro: Amounts are entered in dollars.

| Field       | Help                                         | Placeholder |
|-------------|----------------------------------------------|-------------|
| amountCents | Amount in dollars, e.g. 42.00.               | 42.00       |
| weekday     | 0 = Monday … 6 = Sunday.                     |             |
| ghostField  | This field does not exist on the entity.     |             |

### Form: Ghost

- Intro: This entity is undeclared.
""".strip()


def _result():
    return extract_manifests({"reqs.md": _DOC})


def test_form_prose_manifest_is_emitted_and_round_trips():
    # If the emitted form_prose.yaml failed parse_form_prose, extract_manifests would raise.
    res = _result()
    assert "form_prose.yaml" in res.manifests
    fp = yaml.safe_load(res.manifests["form_prose.yaml"])
    assert set(fp["forms"]) == {"Bill"}  # Ghost (undeclared) is dropped


def test_intro_and_field_help_extract():
    fp = yaml.safe_load(_result().manifests["form_prose.yaml"])["forms"]
    assert fp["Bill"]["intro"] == "Amounts are entered in dollars."
    assert fp["Bill"]["fields"]["amountCents"] == {
        "help": "Amount in dollars, e.g. 42.00.",
        "placeholder": "42.00",
    }
    # a help-only field (blank placeholder cell) carries just help
    assert fp["Bill"]["fields"]["weekday"] == {"help": "0 = Monday … 6 = Sunday."}


def test_unknown_field_is_recorded_dropped_not_guessed():
    res = _result()
    fp = yaml.safe_load(res.manifests["form_prose.yaml"])["forms"]
    assert "ghostField" not in fp["Bill"]["fields"]
    dropped = [
        r for r in res.records
        if r.manifest == "form_prose.yaml" and r.status == Status.NOT_EXTRACTED
        and "ghostField" in r.value_path
    ]
    assert dropped and "no field" in dropped[0].reason


def test_unknown_entity_block_is_recorded_dropped():
    res = _result()
    dropped = [
        r for r in res.records
        if r.manifest == "form_prose.yaml" and r.status == Status.NOT_EXTRACTED
        and "ghost" in r.value_path.lower()
    ]
    assert any("no declared entity" in r.reason for r in dropped)


def test_case_drift_in_field_name_resolves_to_canonical():
    doc = _DOC.replace("| amountCents | Amount", "| AMOUNTCENTS | Amount")
    fp = yaml.safe_load(extract_manifests({"r.md": doc}).manifests["form_prose.yaml"])["forms"]
    # the prose said AMOUNTCENTS; the emitted key is the canonical schema field name
    assert "amountCents" in fp["Bill"]["fields"]


def test_no_form_help_section_emits_nothing():
    doc = "## Entities\n\n### Bill\n\n| Field | Type | Required | Notes |\n|--|--|--|--|\n| memo | text | no | |\n"
    res = extract_manifests({"r.md": doc})
    assert "form_prose.yaml" not in res.manifests
