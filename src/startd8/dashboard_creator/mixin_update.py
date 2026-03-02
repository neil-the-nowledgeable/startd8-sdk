"""
Mixin auto-update — add dashboard imports to mixin.libsonnet (DC-204).
"""

import re
from pathlib import Path
from typing import Tuple

from startd8.logging_config import get_logger

logger = get_logger(__name__)

_GRAFANA_DASHBOARDS_BLOCK = re.compile(
    r"(grafanaDashboards\+?::\s*\{)(.*?)(\})",
    re.DOTALL,
)


def derive_mixin_entry(uid: str) -> Tuple[str, str]:
    """Derive the JSON filename and libsonnet relative path from a dashboard UID.

    Returns:
        (json_filename, libsonnet_rel_path) e.g.
        ("cc-startd8-overview.json", "dashboards/overview.libsonnet")
    """
    json_filename = f"{uid}.json"
    # Strip cc-startd8- or cc- prefix, then convert hyphens to underscores
    name = uid
    if name.startswith("cc-startd8-"):
        name = name[len("cc-startd8-"):]
    elif name.startswith("cc-"):
        name = name[len("cc-"):]
    name = name.replace("-", "_")
    libsonnet_rel_path = f"dashboards/{name}.libsonnet"
    return json_filename, libsonnet_rel_path


def update_mixin_imports(
    mixin_libsonnet_path: Path,
    dashboard_filename: str,
    libsonnet_rel_path: str,
) -> bool:
    """DC-204: Add a dashboard import to the ``grafanaDashboards+::`` block.

    Inserts::

        '{dashboard_filename}': (import '{libsonnet_rel_path}'),

    into the ``grafanaDashboards+::`` block of ``mixin.libsonnet``.

    Args:
        mixin_libsonnet_path: Path to ``mixin.libsonnet``.
        dashboard_filename: JSON filename, e.g. ``"cc-startd8-overview.json"``.
        libsonnet_rel_path: Relative import path, e.g. ``"dashboards/overview.libsonnet"``.

    Returns:
        True if the file was modified, False if already present or not applicable.
    """
    if not mixin_libsonnet_path.is_file():
        logger.debug("mixin.libsonnet not found at %s", mixin_libsonnet_path)
        return False

    content = mixin_libsonnet_path.read_text(encoding="utf-8")

    # Check if entry already exists
    entry_pattern = re.escape(f"'{dashboard_filename}'")
    if re.search(entry_pattern, content):
        logger.debug("Entry for %s already exists in mixin.libsonnet", dashboard_filename)
        return False

    # Build the new entry line
    new_entry = f"    '{dashboard_filename}': (import '{libsonnet_rel_path}'),"

    # Find the grafanaDashboards block and insert before the closing brace
    match = _GRAFANA_DASHBOARDS_BLOCK.search(content)
    if not match:
        logger.warning("No grafanaDashboards block found in %s", mixin_libsonnet_path)
        return False

    block_start = match.start()
    block_end = match.end()
    block_content = match.group(2)
    closing_brace_pos = match.start(3)

    # Insert before the closing brace, preserving formatting
    # If block has existing content, add after last line; otherwise add on new line
    if block_content.strip():
        # Ensure trailing newline before new entry
        insertion = f"\n{new_entry}\n"
        if block_content.rstrip().endswith(","):
            insertion = f"\n{new_entry}\n"
        new_content = content[:closing_brace_pos] + insertion + content[closing_brace_pos:]
    else:
        new_content = content[:closing_brace_pos] + f"\n{new_entry}\n  " + content[closing_brace_pos:]

    mixin_libsonnet_path.write_text(new_content, encoding="utf-8")
    logger.info("Added %s to mixin.libsonnet", dashboard_filename)
    return True
