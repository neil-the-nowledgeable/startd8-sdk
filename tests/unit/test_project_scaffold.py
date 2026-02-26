"""
Unit tests for the Hybrid Project Scaffolder.
"""

import json
from pathlib import Path

import pytest

from startd8.project.scaffolder import ProjectScaffolder, ProjectScaffoldConfig, get_file_hash
from startd8.project.manifest import ProjectScaffoldManifest, SCAFFOLD_MANIFEST_FILE
from startd8.project.scaffold_constants import DEFAULT_TEMPLATE

@pytest.fixture
def run_dir(tmp_path):
    """Temporary directory for running tests."""
    yield tmp_path

@pytest.fixture
def mock_template_dir(tmp_path, monkeypatch):
    """Mock out the global TEMPLATE_DIR to a local tmp directory."""
    templates = tmp_path / "templates"
    basic = templates / "test-python"
    basic.mkdir(parents=True)
    
    # Template 1
    (basic / "pyproject.toml.jinja").write_text("name = \"{{project_name}}\"\n")
    
    # Template 2: Path substition
    src_dir = basic / "src" / "{{module_name}}"
    src_dir.mkdir(parents=True)
    (src_dir / "__init__.py.jinja").write_text("VERSION = \"0.1.0\"\n")
    
    # Non-jinja file
    (basic / "README.md").write_text("Hello World!")
    
    import startd8.project.scaffolder as scaffolder_mod
    monkeypatch.setattr(scaffolder_mod, "TEMPLATE_DIR", templates)
    
    # We must also clear the cached loader otherwise it reads old path
    return templates

def test_initial_scaffold_creates_manifest(mock_template_dir, run_dir):
    scaffolder = ProjectScaffolder()
    config = ProjectScaffoldConfig(
        name="my-app",
        template="test-python",
        output_dir=run_dir / "my_app"
    )
    
    result = scaffolder.scaffold(config)
    assert result.success is True
    assert result.files_created == 3
    assert result.files_updated == 0
    
    # Check manifest
    manifest_path = run_dir / "my_app" / SCAFFOLD_MANIFEST_FILE
    assert manifest_path.exists()
    
    data = json.loads(manifest_path.read_text())
    assert data["template"] == "test-python"
    assert data["context"]["project_name"] == "my-app"
    assert "pyproject.toml" in data["file_hashes"]
    assert "src/my_app/__init__.py" in data["file_hashes"]
    
def test_rescan_scaffold_ignores_modified_files(mock_template_dir, run_dir):
    scaffolder = ProjectScaffolder()
    config = ProjectScaffoldConfig(
        name="my-app",
        template="test-python",
        output_dir=run_dir / "my_app"
    )
    
    # Scaffold 1 
    scaffolder.scaffold(config)
    
    # Emulate user modifying pyproject.toml
    target = run_dir / "my_app" / "pyproject.toml"
    target.write_text("name = \"my-app-modified\"\n")
    
    # Scaffold 2
    result2 = scaffolder.scaffold(config)
    
    assert result2.success is True
    assert result2.files_created == 0
    assert result2.files_updated == 0
    assert result2.files_skipped == 1  # The pyproject should be skipped safely!
    
    # Verify contents survived
    assert target.read_text() == "name = \"my-app-modified\"\n"

def test_force_scaffold_overwrites_modified_files(mock_template_dir, run_dir):
    scaffolder = ProjectScaffolder()
    config = ProjectScaffoldConfig(
        name="my-app",
        template="test-python",
        output_dir=run_dir / "my_app"
    )
    
    # Scaffold 1
    scaffolder.scaffold(config)
    
    # Emulate user modifying pyproject.toml
    target = run_dir / "my_app" / "pyproject.toml"
    target.write_text("name = \"my-app-modified\"\n")
    
    # Update config to force
    config.force = True
    
    # Scaffold 2
    result2 = scaffolder.scaffold(config)
    
    assert result2.success is True
    assert result2.files_created == 0
    assert result2.files_updated == 3  # The pyproject and other files should be forcibly overwritten!
    
    # Verify contents overwritten
    assert target.read_text() == "name = \"my-app\"\n"

def test_template_update_overwrites_unmodified_files(tmp_path, monkeypatch):
    """Test scenario where the base SDK template is updated, and we want to push it downstream."""
    # Setup mock templates
    templates = tmp_path / "templates"
    basic = templates / "test-python"
    basic.mkdir(parents=True)
    
    template_file = basic / "file1.txt.jinja"
    template_file.write_text("original content")
    
    import startd8.project.scaffolder as scaffolder_mod
    monkeypatch.setattr(scaffolder_mod, "TEMPLATE_DIR", templates)
    
    scaffolder = ProjectScaffolder()
    output_dir = tmp_path / "my_app"
    config = ProjectScaffoldConfig(
        name="my-app",
        template="test-python",
        output_dir=output_dir
    )
    
    # Scaffold 1 
    result1 = scaffolder.scaffold(config)
    assert result1.files_created == 1
    
    target_file = output_dir / "file1.txt"
    original_hash = get_file_hash(target_file)
    assert target_file.read_text() == "original content"
    
    # Emulate SDK template update!!!
    template_file.write_text("new updated content in sdk")
    
    # Scaffold 2 (No force needed because target file hasn't been touched)
    result2 = scaffolder.scaffold(config)
    assert result2.success is True
    assert result2.files_created == 0
    assert result2.files_updated == 1
    assert result2.files_skipped == 0
    
    # Verify file was successfully, safely updated!
    assert target_file.read_text() == "new updated content in sdk"
    
    new_hash = get_file_hash(target_file)
    assert new_hash != original_hash
