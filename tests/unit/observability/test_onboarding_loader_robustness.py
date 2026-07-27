"""Loader robustness for the cross-repo onboarding-metadata contract (CEP auto-applied tier).

A malformed producer artifact must fail LEGIBLY, not with an opaque crash deep in extraction:
  - R2: invalid JSON → a ValueError naming the file path + position (not a bare JSONDecodeError).
  - R6: a non-object hint value → a warned skip, not an AttributeError from `hint.get(...)`.
"""

import pytest

from startd8.observability.artifact_generator_context import (
    extract_service_hints,
    load_onboarding_metadata,
)


def test_invalid_json_raises_with_path_and_position(tmp_path):
    # R2: bare json.load loses the path — wrap it so the operator learns WHICH file is malformed.
    bad = tmp_path / "onboarding-metadata.json"
    bad.write_text('{"project_id": "p", "instrumentation_hints": {')  # truncated → invalid JSON
    with pytest.raises(ValueError) as ei:
        load_onboarding_metadata(bad)
    msg = str(ei.value)
    assert str(bad) in msg
    assert "not valid JSON" in msg and "line" in msg


def test_non_dict_hint_is_skipped_not_crashed(tmp_path):
    # R6: a non-object hint value must degrade to a legible skip, not an AttributeError at hint.get().
    meta = {
        "project_id": "p",
        "instrumentation_hints": {
            "web": {"service_id": "web", "kind": "http_server", "transport": "http",
                    "metrics": {"convention_based": []}},
            "broken": "not-a-dict",       # the malformed entry
            "also_broken": ["nope"],      # a list, too
        },
    }
    # must not raise
    hints = extract_service_hints(meta)
    ids = {h.service_id for h in hints}
    assert "web" in ids
    assert "broken" not in ids and "also_broken" not in ids
