"""
Filesystem-based workflow discovery for token-efficient agent interaction.

This module implements the "progressive disclosure" pattern from Anthropic's
code execution approach, allowing agents to discover workflows on-demand
by exploring a filesystem rather than loading all schemas upfront.

Key benefits:
- Reduced token usage (agents load only needed definitions)
- Data stays in execution environment
- Agents can compose workflows via code

Directory structure:
    workflows/
    ├── _index.yaml          # Lightweight index of all workflows
    ├── pipeline.yaml        # Full definition for pipeline workflow
    ├── doc-enhancement.yaml
    └── iterative-dev.yaml

Usage by agents:
    1. Read _index.yaml to see available workflows (minimal tokens)
    2. Read specific workflow file for full schema when needed
    3. Execute workflow via registry or MCP
"""

import os
import yaml
from pathlib import Path
from typing import Dict, Any, List, Optional
from dataclasses import asdict

from .models import WorkflowMetadata, WorkflowInput, AgentCount


class WorkflowFilesystem:
    """
    Manages workflow definitions on the filesystem for agent discovery.

    Provides export/import functionality and lazy-loading discovery.
    """

    DEFAULT_DIR = ".startd8/workflows"
    INDEX_FILE = "_index.yaml"

    def __init__(self, base_dir: Optional[str] = None):
        """
        Initialize filesystem manager.

        Args:
            base_dir: Base directory for workflow files.
                     Defaults to .startd8/workflows in current directory.
        """
        self.base_dir = Path(base_dir) if base_dir else Path(self.DEFAULT_DIR)

    def ensure_dir(self) -> Path:
        """Ensure the workflow directory exists."""
        self.base_dir.mkdir(parents=True, exist_ok=True)
        return self.base_dir

    # --- Export Methods ---

    def export_workflow(self, metadata: WorkflowMetadata) -> Path:
        """
        Export a single workflow definition to YAML file.

        Args:
            metadata: Workflow metadata to export

        Returns:
            Path to the created file
        """
        self.ensure_dir()

        # Build YAML-friendly dict
        data = self._metadata_to_yaml_dict(metadata)

        # Write to file
        file_path = self.base_dir / f"{metadata.workflow_id}.yaml"
        with open(file_path, 'w') as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)

        return file_path

    def export_all(self, metadata_list: List[WorkflowMetadata]) -> Dict[str, Path]:
        """
        Export all workflow definitions and create index.

        Args:
            metadata_list: List of workflow metadata to export

        Returns:
            Dict mapping workflow_id to file path
        """
        self.ensure_dir()

        exported = {}
        index_entries = []

        for metadata in metadata_list:
            path = self.export_workflow(metadata)
            exported[metadata.workflow_id] = path

            # Build lightweight index entry
            index_entries.append({
                'workflow_id': metadata.workflow_id,
                'name': metadata.name,
                'description': metadata.description[:100] + '...' if len(metadata.description) > 100 else metadata.description,
                'capabilities': metadata.capabilities[:3],  # First 3 only
                'file': f"{metadata.workflow_id}.yaml",
            })

        # Write index file
        index_path = self.base_dir / self.INDEX_FILE
        index_data = {
            'version': '1.0',
            'description': 'StartD8 workflow definitions for agent discovery',
            'usage': 'Read this file first to discover workflows, then read individual files for full schemas',
            'workflows': index_entries,
        }
        with open(index_path, 'w') as f:
            yaml.dump(index_data, f, default_flow_style=False, sort_keys=False)

        exported['_index'] = index_path
        return exported

    def _metadata_to_yaml_dict(self, metadata: WorkflowMetadata) -> Dict[str, Any]:
        """Convert WorkflowMetadata to YAML-friendly dictionary."""
        return {
            'workflow_id': metadata.workflow_id,
            'name': metadata.name,
            'description': metadata.description,
            'version': metadata.version,
            'capabilities': metadata.capabilities,
            'tags': metadata.tags,
            'agent_requirements': {
                'requires_agents': metadata.requires_agents,
                'agent_count': metadata.agent_count.value,
                'min_agents': metadata.min_agents,
                'max_agents': metadata.max_agents,
            },
            'inputs': [
                {
                    'name': inp.name,
                    'type': inp.type,
                    'required': inp.required,
                    'description': inp.description,
                    'default': inp.default,
                }
                for inp in metadata.inputs
            ],
            'input_schema': metadata.get_input_schema(),
            'invocation': {
                'mcp_tool': 'startd8_workflow',
                'action': 'run',
                'example': {
                    'action': 'run',
                    'workflow_id': metadata.workflow_id,
                    'config': {
                        inp.name: f"<{inp.type}>" + (" (required)" if inp.required else "")
                        for inp in metadata.inputs
                    }
                }
            }
        }

    # --- Discovery Methods ---

    def list_workflows(self) -> List[Dict[str, Any]]:
        """
        List available workflows from index file (minimal tokens).

        Returns:
            List of lightweight workflow summaries
        """
        index_path = self.base_dir / self.INDEX_FILE
        if not index_path.exists():
            return []

        with open(index_path, 'r') as f:
            data = yaml.safe_load(f)

        return data.get('workflows', [])

    def get_workflow_definition(self, workflow_id: str) -> Optional[Dict[str, Any]]:
        """
        Get full workflow definition from file.

        Args:
            workflow_id: The workflow to load

        Returns:
            Full workflow definition dict, or None if not found
        """
        file_path = self.base_dir / f"{workflow_id}.yaml"
        if not file_path.exists():
            return None

        with open(file_path, 'r') as f:
            return yaml.safe_load(f)

    def get_input_schema(self, workflow_id: str) -> Optional[Dict[str, Any]]:
        """
        Get just the input schema for a workflow (for validation).

        Args:
            workflow_id: The workflow to get schema for

        Returns:
            JSON Schema dict for inputs, or None if not found
        """
        definition = self.get_workflow_definition(workflow_id)
        if definition:
            return definition.get('input_schema')
        return None

    def workflow_exists(self, workflow_id: str) -> bool:
        """Check if a workflow definition file exists."""
        return (self.base_dir / f"{workflow_id}.yaml").exists()

    # --- Import Methods ---

    def import_workflow(self, workflow_id: str) -> Optional[WorkflowMetadata]:
        """
        Import workflow metadata from YAML file.

        Args:
            workflow_id: The workflow to import

        Returns:
            WorkflowMetadata object, or None if not found
        """
        definition = self.get_workflow_definition(workflow_id)
        if not definition:
            return None

        return self._yaml_dict_to_metadata(definition)

    def import_all(self) -> List[WorkflowMetadata]:
        """
        Import all workflow definitions from filesystem.

        Returns:
            List of WorkflowMetadata objects
        """
        workflows = []
        for entry in self.list_workflows():
            metadata = self.import_workflow(entry['workflow_id'])
            if metadata:
                workflows.append(metadata)
        return workflows

    def _yaml_dict_to_metadata(self, data: Dict[str, Any]) -> WorkflowMetadata:
        """Convert YAML dict back to WorkflowMetadata."""
        agent_req = data.get('agent_requirements', {})

        inputs = [
            WorkflowInput(
                name=inp['name'],
                type=inp['type'],
                required=inp.get('required', True),
                description=inp.get('description', ''),
                default=inp.get('default'),
            )
            for inp in data.get('inputs', [])
        ]

        return WorkflowMetadata(
            workflow_id=data['workflow_id'],
            name=data['name'],
            description=data['description'],
            version=data.get('version', '1.0.0'),
            capabilities=data.get('capabilities', []),
            tags=data.get('tags', []),
            requires_agents=agent_req.get('requires_agents', True),
            agent_count=AgentCount(agent_req.get('agent_count', 'configurable')),
            min_agents=agent_req.get('min_agents', 1),
            max_agents=agent_req.get('max_agents'),
            inputs=inputs,
        )


def export_registry_to_filesystem(
    output_dir: Optional[str] = None,
) -> Dict[str, Path]:
    """
    Export all registered workflows to filesystem.

    Convenience function that discovers workflows via entry points
    and exports them to YAML files for agent discovery.

    Args:
        output_dir: Output directory (default: .startd8/workflows)

    Returns:
        Dict mapping workflow_id to file path
    """
    from .registry import WorkflowRegistry

    # Discover workflows
    WorkflowRegistry.discover()

    # Get all metadata
    metadata_list = WorkflowRegistry.list_workflow_metadata()

    # Export
    fs = WorkflowFilesystem(output_dir)
    return fs.export_all(metadata_list)
