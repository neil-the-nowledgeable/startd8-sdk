"""Tests for L3+: bidirectional package alias map."""

from startd8.implementation_engine.package_aliases import (
    _IMPORT_TO_PYPI,
    _PYPI_TO_IMPORT,
    import_to_pypi,
    pypi_to_import,
)


class TestPypiToImport:
    def test_known_mapping(self):
        assert pypi_to_import("grpcio") == "grpc"

    def test_known_mapping_case_insensitive(self):
        assert pypi_to_import("PyYAML") == "yaml"

    def test_unknown_passthrough(self):
        assert pypi_to_import("flask") == "flask"

    def test_pillow(self):
        assert pypi_to_import("pillow") == "PIL"

    def test_beautifulsoup(self):
        assert pypi_to_import("beautifulsoup4") == "bs4"

    def test_scikit_learn(self):
        assert pypi_to_import("scikit-learn") == "sklearn"


class TestImportToPypi:
    def test_known_mapping(self):
        assert import_to_pypi("grpc") == "grpcio"

    def test_nested_prefix_match(self):
        result = import_to_pypi("google.api_core.retry")
        assert result == "google-api-core"

    def test_unknown_passthrough(self):
        assert import_to_pypi("flask") == "flask"

    def test_yaml(self):
        assert import_to_pypi("yaml") == "pyyaml"

    def test_PIL(self):
        assert import_to_pypi("PIL") == "pillow"


class TestBidirectionalConsistency:
    def test_all_pypi_entries_round_trip(self):
        """Every entry in _PYPI_TO_IMPORT should have a reverse entry."""
        for pypi_name, import_name in _PYPI_TO_IMPORT.items():
            # The reverse map may pick a different PyPI name (shortest),
            # but the forward of that reverse should match.
            reverse_pypi = import_to_pypi(import_name)
            re_imported = pypi_to_import(reverse_pypi)
            # The re-imported name should match the original import name
            # (they may resolve through different PyPI packages but to
            # the same import).
            assert re_imported == import_name or re_imported.split(".")[0] == import_name.split(".")[0], (
                f"Round-trip failed: {pypi_name} -> {import_name} -> "
                f"{reverse_pypi} -> {re_imported}"
            )

    def test_reverse_map_populated(self):
        """The reverse map should have entries."""
        assert len(_IMPORT_TO_PYPI) > 0
