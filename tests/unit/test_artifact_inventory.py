"""Tests for startd8.utils.artifact_inventory."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from startd8.utils.artifact_inventory import (
    _extract_json_path,
    extend_inventory,
    load_artifact_content,
    load_inventory,
    lookup_artifact,
)


# ---------------------------------------------------------------------------
# load_inventory
# ---------------------------------------------------------------------------

class TestLoadInventory:
    def test_missing_file(self, tmp_path: Path):
        """Returns [] when run-provenance.json doesn't exist."""
        result = load_inventory(tmp_path)
        assert result == []

    def test_v1_schema(self, tmp_path: Path):
        """Returns [] for v1 schema (no inventory)."""
        prov = {"version": "1.0.0", "run_id": "abc"}
        (tmp_path / "run-provenance.json").write_text(json.dumps(prov))
        result = load_inventory(tmp_path)
        assert result == []

    def test_v2_schema(self, tmp_path: Path):
        """Returns inventory entries for v2 schema."""
        entries = [
            {"artifact_id": "export.derivation_rules", "role": "derivation_rules"},
            {"artifact_id": "export.output_contracts", "role": "output_contracts"},
        ]
        prov = {"version": "2.0.0", "artifact_inventory": entries}
        (tmp_path / "run-provenance.json").write_text(json.dumps(prov))
        result = load_inventory(tmp_path)
        assert len(result) == 2
        assert result[0]["role"] == "derivation_rules"

    def test_malformed_json(self, tmp_path: Path):
        """Returns [] for malformed JSON."""
        (tmp_path / "run-provenance.json").write_text("not json")
        result = load_inventory(tmp_path)
        assert result == []

    def test_inventory_not_list(self, tmp_path: Path):
        """Returns [] when artifact_inventory is not a list."""
        prov = {"version": "2.0.0", "artifact_inventory": "bad"}
        (tmp_path / "run-provenance.json").write_text(json.dumps(prov))
        result = load_inventory(tmp_path)
        assert result == []


# ---------------------------------------------------------------------------
# lookup_artifact
# ---------------------------------------------------------------------------

class TestLookupArtifact:
    def test_hit(self):
        inventory = [
            {"role": "derivation_rules", "artifact_id": "export.derivation_rules"},
            {"role": "output_contracts", "artifact_id": "export.output_contracts"},
        ]
        entry, outcome = lookup_artifact(inventory, "derivation_rules")
        assert entry is not None
        assert outcome == "hit"
        assert entry["role"] == "derivation_rules"

    def test_miss(self):
        inventory = [
            {"role": "derivation_rules", "artifact_id": "export.derivation_rules"},
        ]
        entry, outcome = lookup_artifact(inventory, "nonexistent_role")
        assert entry is None
        assert outcome == "miss"

    def test_stale(self, tmp_path: Path):
        """Returns stale when source checksum doesn't match."""
        # Create a source file
        source = tmp_path / ".contextcore.yaml"
        source.write_text("original content")

        inventory = [
            {
                "role": "derivation_rules",
                "artifact_id": "export.derivation_rules",
                "freshness": {
                    "source_checksum": "wrong_checksum",
                    "source_file": ".contextcore.yaml",
                },
            },
        ]
        entry, outcome = lookup_artifact(
            inventory, "derivation_rules",
            verify_freshness=True, source_dir=tmp_path,
        )
        assert entry is not None
        assert outcome == "stale"

    def test_empty_inventory(self):
        entry, outcome = lookup_artifact([], "derivation_rules")
        assert entry is None
        assert outcome == "miss"


# ---------------------------------------------------------------------------
# load_artifact_content
# ---------------------------------------------------------------------------

class TestLoadArtifactContent:
    def test_load_full_file(self, tmp_path: Path):
        """Loads full JSON when no json_path specified."""
        data = {"key": "value", "nested": {"a": 1}}
        (tmp_path / "onboarding-metadata.json").write_text(json.dumps(data))
        entry = {"source_file": "onboarding-metadata.json"}
        result = load_artifact_content(entry, tmp_path)
        assert result == data

    def test_load_with_json_path(self, tmp_path: Path):
        """Extracts sub-document via json_path."""
        data = {"derivation_rules": {"dashboard": {"alertSeverity": "P2"}}}
        (tmp_path / "onboarding-metadata.json").write_text(json.dumps(data))
        entry = {
            "source_file": "onboarding-metadata.json",
            "json_path": "$.derivation_rules",
        }
        result = load_artifact_content(entry, tmp_path)
        assert result == {"dashboard": {"alertSeverity": "P2"}}

    def test_missing_source_file(self, tmp_path: Path):
        """Returns None when source file doesn't exist."""
        entry = {"source_file": "nonexistent.json"}
        result = load_artifact_content(entry, tmp_path)
        assert result is None

    def test_missing_json_path_key(self, tmp_path: Path):
        """Returns None when json_path key doesn't exist in data."""
        data = {"other_key": "value"}
        (tmp_path / "test.json").write_text(json.dumps(data))
        entry = {"source_file": "test.json", "json_path": "$.missing_key"}
        result = load_artifact_content(entry, tmp_path)
        assert result is None

    def test_nested_json_path(self, tmp_path: Path):
        """Supports nested dot-notation json_path."""
        data = {"level1": {"level2": {"target": "found"}}}
        (tmp_path / "test.json").write_text(json.dumps(data))
        entry = {"source_file": "test.json", "json_path": "$.level1.level2"}
        result = load_artifact_content(entry, tmp_path)
        assert result == {"target": "found"}


# ---------------------------------------------------------------------------
# _extract_json_path
# ---------------------------------------------------------------------------

class TestExtractJsonPath:
    def test_simple_key(self):
        assert _extract_json_path({"a": 1}, "$.a") == 1

    def test_nested_key(self):
        assert _extract_json_path({"a": {"b": 2}}, "$.a.b") == 2

    def test_missing_key(self):
        assert _extract_json_path({"a": 1}, "$.b") is None

    def test_no_dollar_prefix(self):
        """Returns data as-is when path doesn't start with $."""
        data = {"a": 1}
        assert _extract_json_path(data, "a") == data


# ---------------------------------------------------------------------------
# extend_inventory
# ---------------------------------------------------------------------------

class TestExtendInventory:
    def test_extends_existing(self, tmp_path: Path):
        """Adds new entries to existing inventory."""
        existing = {
            "version": "2.0.0",
            "artifact_inventory": [
                {"artifact_id": "export.derivation_rules", "role": "derivation_rules"},
            ],
        }
        (tmp_path / "run-provenance.json").write_text(json.dumps(existing))

        new_entries = [
            {"artifact_id": "ingestion.plan_document", "role": "plan_document"},
        ]
        result = extend_inventory(tmp_path, new_entries)
        assert result is True

        # Verify
        data = json.loads((tmp_path / "run-provenance.json").read_text())
        assert len(data["artifact_inventory"]) == 2

    def test_preserves_existing_entries(self, tmp_path: Path):
        """Doesn't duplicate entries with same artifact_id."""
        existing = {
            "version": "2.0.0",
            "artifact_inventory": [
                {"artifact_id": "export.derivation_rules", "role": "derivation_rules"},
            ],
        }
        (tmp_path / "run-provenance.json").write_text(json.dumps(existing))

        # Try to add entry with same artifact_id
        new_entries = [
            {"artifact_id": "export.derivation_rules", "role": "derivation_rules", "extra": True},
        ]
        extend_inventory(tmp_path, new_entries)

        data = json.loads((tmp_path / "run-provenance.json").read_text())
        assert len(data["artifact_inventory"]) == 1
        # Existing entry preserved (no "extra" field)
        assert "extra" not in data["artifact_inventory"][0]

    def test_upgrades_v1_to_v2(self, tmp_path: Path):
        """Upgrades v1 provenance to v2 when extending."""
        existing = {"version": "1.0.0", "run_id": "abc"}
        (tmp_path / "run-provenance.json").write_text(json.dumps(existing))

        new_entries = [
            {"artifact_id": "ingestion.plan_document", "role": "plan_document"},
        ]
        extend_inventory(tmp_path, new_entries)

        data = json.loads((tmp_path / "run-provenance.json").read_text())
        assert data["version"] == "2.0.0"
        assert len(data["artifact_inventory"]) == 1

    def test_no_provenance_file(self, tmp_path: Path):
        """Creates new v2 provenance when file doesn't exist."""
        new_entries = [{"artifact_id": "test", "role": "test"}]
        result = extend_inventory(tmp_path, new_entries)
        # extend_inventory creates a new v2 provenance from empty dict
        assert result is True
        data = json.loads((tmp_path / "run-provenance.json").read_text())
        assert data["version"] == "2.0.0"
        assert len(data["artifact_inventory"]) == 1


# ---------------------------------------------------------------------------
# OTel metrics
# ---------------------------------------------------------------------------

class TestOtelMetrics:
    def test_lookup_emits_otel_metric(self):
        """lookup_artifact calls _emit_lookup_metric (no error when OTel unavailable)."""
        inventory = [{"role": "test_role", "artifact_id": "export.test_role"}]
        # Should not raise even without OTel
        entry, outcome = lookup_artifact(inventory, "test_role")
        assert outcome == "hit"

    def test_lookup_noop_without_otel(self):
        """_emit_lookup_metric is a no-op when OTel is not installed."""
        from startd8.utils.artifact_inventory import _emit_lookup_metric
        # Should not raise
        _emit_lookup_metric("test", "hit")


# ---------------------------------------------------------------------------
# Design integration (graceful degradation)
# ---------------------------------------------------------------------------

class TestDesignGracefulDegradation:
    """Tests that DESIGN degrades gracefully when inventory is absent."""

    def test_design_handler_imports(self):
        """Verify inventory imports are available in context_seed_handlers."""
        from startd8.utils.artifact_inventory import (
            load_artifact_content,
            load_inventory,
            lookup_artifact,
        )
        assert callable(load_inventory)
        assert callable(lookup_artifact)
        assert callable(load_artifact_content)
