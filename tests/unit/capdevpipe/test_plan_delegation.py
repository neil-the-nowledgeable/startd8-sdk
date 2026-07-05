"""Tests for canonical plan delegation + namespace guard (Thread A-4 / A-5).

A-4: ``embed_symlink`` translates the canonical ``resolve_install_plan`` output rather than
re-deriving the kind->action mapping — but the *result* must stay equivalent (scripts/aliases/
packages symlinked; resource_trees copied). A-5: ``plan_actions`` refuses to embed when a
generic ``pipeline`` module in the project root would shadow the embed package.
"""

import pytest

from startd8.capdevpipe_embed_manifest import (
    DEFAULT_EMBED_PROFILE,
    resolve_embed_inventory,
)
from startd8.capdevpipe_installer import ActionType, EMBED_DIR_NAME
from startd8.exceptions import ConfigurationError

pytestmark = pytest.mark.unit


class TestSymlinkDelegation:
    def test_plan_classification_matches_inventory(self, installer, cfg_factory, full_source):
        """A-4: the delegated plan symlinks scripts/aliases/packages and copies resource trees."""
        cfg = cfg_factory()
        inv = resolve_embed_inventory(full_source, DEFAULT_EMBED_PROFILE)
        actions = installer.embed_symlink(cfg)

        by_name = {a.target.name: a for a in actions}
        for name in (*inv.scripts, *inv.python_aliases, *inv.packages):
            assert by_name[name].type is ActionType.SYMLINK, name
            # NFR-3: absolute source so dirname "$0" resolves to the embed dir.
            assert by_name[name].source is not None and by_name[name].source.is_absolute()
        for resource in inv.resource_trees:
            assert by_name[resource].type is ActionType.COPY_TREE, resource

    def test_symlink_targets_under_embed_dir(self, installer, cfg_factory, target):
        cfg = cfg_factory()
        for a in installer.embed_symlink(cfg):
            # every action writes inside the target's .cap-dev-pipe/
            assert EMBED_DIR_NAME in a.target.parts


class TestNamespaceGuard:
    def test_shadowing_pipeline_dir_is_refused(self, installer, cfg_factory, target):
        """A-5: a project-root ``pipeline/`` that would shadow the embed package is rejected."""
        (target / "pipeline").mkdir()
        with pytest.raises(ConfigurationError, match="namespace"):
            installer.plan_actions(cfg_factory())

    def test_shadowing_pipeline_file_is_refused(self, installer, cfg_factory, target):
        (target / "pipeline.py").write_text("x = 1\n", encoding="utf-8")
        with pytest.raises(ConfigurationError, match="namespace"):
            installer.plan_actions(cfg_factory())

    def test_clean_project_is_allowed(self, installer, cfg_factory, target):
        # No sibling pipeline module → plan builds without raising.
        actions = installer.plan_actions(cfg_factory())
        assert actions
