import json
from pathlib import Path
from typer.testing import CliRunner
from startd8.cli import manifest_app

runner = CliRunner()


def test_manifest_validate_forward_missing_manifest(tmp_path: Path):
    """Test validation fails if manifest file is missing."""
    result = runner.invoke(manifest_app, ["validate-forward", str(tmp_path / "missing.json")])
    assert result.exit_code == 1
    assert "Manifest file not found" in result.stdout


def test_manifest_validate_forward_invalid_json(tmp_path: Path):
    """Test validation fails if manifest file is invalid JSON."""
    manifest_file = tmp_path / "manifest.json"
    manifest_file.write_text("{ invalid json }")
    
    result = runner.invoke(manifest_app, ["validate-forward", str(manifest_file)])
    assert result.exit_code == 1
    assert "Failed to parse ForwardManifest" in result.stdout


def test_manifest_validate_forward_missing_registry(tmp_path: Path):
    """Test validation fails if registry does not exist yet."""
    manifest_file = tmp_path / "manifest.json"
    manifest_file.write_text('{"contracts": [], "file_specs": {}}')
    
    # Run with source_path pointing to a completely empty temp dir
    result = runner.invoke(manifest_app, ["validate-forward", str(manifest_file), "--source-path", str(tmp_path)])
    
    assert result.exit_code == 1
    assert "No codebase manifest cache found" in result.stdout
