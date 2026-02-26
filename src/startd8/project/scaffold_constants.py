# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""
Constants and error messages for project scaffolding.
"""

from pathlib import Path

# Tracking 
SCAFFOLD_MANIFEST_FILE = ".startd8-scaffold.json"
SCHEMA_VERSION = "1.0.0"

# Defaults
DEFAULT_TEMPLATE = "basic-python"
DEFAULT_DESCRIPTION = "A customized python package"
DEFAULT_VERSION = "0.1.0"

# Paths
TEMPLATE_DIR = Path(__file__).parent / "templates"

# Messages
MSG_PROJECT_CREATED = "Successfully scaffolded project: {name}"
MSG_FILE_OVERWRITTEN = "Overwrote file safely (hash matched): {path}"
MSG_FILE_SKIPPED = "Skipped overwriting customized file (hash mismatch): {path}"
MSG_FILE_FORCED = "Forcibly overwrote file: {path}"
MSG_MANIFEST_UPDATED = "Updated scaffolding manifest: {path}"

# Errors
ERR_TEMPLATE_NOT_FOUND = "Template '{template}' not found in {templates_dir}"
ERR_INVALID_NAME = "Invalid project name '{name}'. Must contain only alphanumeric characters, hyphens, and underscores."
ERR_INVALID_OUTPUT_DIR = "Output directory must be empty or contain a valid startd8 scaffold manifest."
ERR_JINJA2_NOT_INSTALLED = (
    "Jinja2 is required for project scaffolding. "
    "Install with: pip install jinja2"
)
