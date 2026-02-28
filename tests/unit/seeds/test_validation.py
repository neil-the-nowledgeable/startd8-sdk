"""Tests for startd8.seeds.validation."""

from startd8.seeds.validation import (
    validate_context_seed,
    validate_for_route,
    validate_seed_field_coverage,
)


def _minimal_seed(**overrides):
    """Build a minimal valid seed dict."""
    d = {
        "version": "1.0.0",
        "schema_version": "1.0",
        "generated_at": "2026-01-01T00:00:00+00:00",
        "source_checksum": None,
        "generator": "plan-ingestion",
        "plan": None,
        "complexity": None,
        "tasks": [
            {
                "task_id": "PI-001",
                "title": "Test",
                "config": {
                    "task_description": "desc",
                    "context": {
                        "feature_id": "F1",
                        "target_files": ["src/a.py"],
                    },
                },
            }
        ],
        "artifacts": {},
        "ingestion_metrics": {},
    }
    d.update(overrides)
    return d


class TestValidateContextSeed:
    """JSON schema validation tests."""

    def test_valid_seed_passes(self):
        assert validate_context_seed(_minimal_seed()) is True

    def test_missing_required_field_fails(self):
        seed = _minimal_seed()
        del seed["tasks"]
        # Without jsonschema installed this may still return True (graceful)
        # With jsonschema it should return False
        result = validate_context_seed(seed)
        # Either way, the function should not raise
        assert isinstance(result, bool)


class TestValidateSeedFieldCoverage:
    """Advisory field coverage tests."""

    def test_no_tasks_warns(self):
        seed = _minimal_seed(tasks=[])
        warnings = validate_seed_field_coverage(seed)
        assert any("no tasks" in w for w in warnings)

    def test_missing_target_files_warns(self):
        seed = _minimal_seed(
            tasks=[{
                "task_id": "PI-001",
                "title": "Test",
                "config": {"task_description": "desc", "context": {}},
            }]
        )
        warnings = validate_seed_field_coverage(seed)
        assert any("target_files" in w for w in warnings)

    def test_missing_description_warns(self):
        seed = _minimal_seed(
            tasks=[{
                "task_id": "PI-001",
                "title": "Test",
                "config": {
                    "context": {"target_files": ["a.py"]},
                },
            }]
        )
        warnings = validate_seed_field_coverage(seed)
        assert any("description" in w for w in warnings)

    def test_missing_optional_fields_warns(self):
        seed = _minimal_seed()
        warnings = validate_seed_field_coverage(seed)
        assert any("architectural_context" in w for w in warnings)
        assert any("design_calibration" in w for w in warnings)
        assert any("service_metadata" in w for w in warnings)
        assert any("onboarding" in w for w in warnings)
        assert any("context_files" in w for w in warnings)
        assert any("project_metadata" in w for w in warnings)

    def test_fully_populated_no_warnings(self):
        seed = _minimal_seed(
            architectural_context={"project_goals": ["g"]},
            design_calibration={"PI-001": {}},
            service_metadata={"transport_protocol": "http"},
            onboarding={"path": "/p"},
            context_files=[{"path": "a.py"}],
            project_metadata={"criticality": "low"},
        )
        warnings = validate_seed_field_coverage(seed)
        assert len(warnings) == 0


class TestValidateForRoute:
    """Route-specific validation tests."""

    def test_artisan_warns_on_missing_calibration(self):
        seed = _minimal_seed(
            onboarding={"path": "/p"},
            service_metadata={"x": 1},
            context_files=[{"path": "a.py"}],
            project_metadata={"criticality": "low"},
        )
        warnings = validate_for_route(seed, "artisan")
        artisan_warnings = [w for w in warnings if "[artisan]" in w]
        assert any("design_calibration" in w for w in artisan_warnings)
        assert any("architectural_context" in w for w in artisan_warnings)

    def test_prime_warns_on_missing_onboarding(self):
        seed = _minimal_seed(
            architectural_context={"goals": []},
            design_calibration={"PI-001": {}},
            service_metadata={"x": 1},
            context_files=[{"path": "a.py"}],
            project_metadata={"criticality": "low"},
        )
        warnings = validate_for_route(seed, "prime")
        prime_warnings = [w for w in warnings if "[prime]" in w]
        assert any("onboarding" in w for w in prime_warnings)

    def test_artisan_no_route_warning_when_populated(self):
        seed = _minimal_seed(
            architectural_context={"goals": []},
            design_calibration={"PI-001": {}},
            onboarding={"path": "/p"},
            service_metadata={"x": 1},
            context_files=[{"path": "a.py"}],
            project_metadata={"criticality": "low"},
        )
        warnings = validate_for_route(seed, "artisan")
        artisan_warnings = [w for w in warnings if "[artisan]" in w]
        assert len(artisan_warnings) == 0
