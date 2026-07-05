"""Manifest interop + migration tests (Thread A-3 / A-6).

The SDK's ``.install-manifest.json`` must be readable by canonical ``verify_embed``/
``repair_embed`` (which crash with a raw ``KeyError`` on the pre-A6 schema — spike §0.2),
while remaining backward-compatible for the SDK's own reader. Covers: canonical-superset
serialization, legacy-shape reading (migration), migration-on-write, and a guarded
end-to-end check against the real canonical planner.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from startd8.capdevpipe_installer import (
    EMBED_DIR_NAME,
    MANIFEST_FILENAME,
    InstallMethod,
    Manifest,
    ManifestState,
)

pytestmark = pytest.mark.unit


# Canonical fields required by canonical verify_embed/_manifest_install_context.
_CANONICAL_REQUIRED = {"schema_version", "install_method", "source_path", "embed_profile", "managed_paths", "state"}


class TestSerialization:
    def test_to_dict_has_canonical_fields(self):
        m = Manifest(
            method=InstallMethod.SYMLINK,
            source_path=Path("/src/cap-dev-pipe"),
            created_paths=[Path("/t/.cap-dev-pipe/pipeline")],
            profiles=["python"],
            embed_profile="full",
            managed_paths=["pipeline", "design", "run.sh"],
        )
        d = m.to_dict()
        assert _CANONICAL_REQUIRED <= set(d), f"missing: {_CANONICAL_REQUIRED - set(d)}"
        assert d["install_method"] == "symlink"
        assert d["embed_profile"] == "full"
        assert d["managed_paths"] == sorted({"pipeline", "design", "run.sh"})
        assert d["schema_version"] == d["manifest_version"]
        # SDK-only bookkeeping still present for rollback/uninstall.
        assert "created_paths" in d and "profiles" in d

    def test_roundtrip_preserves_canonical_and_sdk_fields(self):
        m = Manifest(
            method=InstallMethod.COPY,
            source_path=Path("/src/cap-dev-pipe"),
            created_paths=[Path("/t/.cap-dev-pipe")],
            profiles=["go"],
            embed_profile="orchestrator",
            managed_paths=["design", "pipeline"],
        )
        m2 = Manifest.from_dict(m.to_dict())
        assert m2.method is InstallMethod.COPY
        assert m2.embed_profile == "orchestrator"
        assert m2.managed_paths == ["design", "pipeline"]
        assert m2.profiles == ["go"]


class TestLegacyMigration:
    LEGACY = {
        "manifest_version": 1,
        "method": "symlink",
        "source_path": "/src/cap-dev-pipe",
        "created_paths": ["/t/.cap-dev-pipe/pipeline"],
        "profiles": ["python"],
        "state": "complete",
    }

    def test_from_dict_reads_legacy_shape(self):
        """A-6: a pre-A6 manifest (method/created_paths, no managed_paths) still loads."""
        m = Manifest.from_dict(dict(self.LEGACY))
        assert m.method is InstallMethod.SYMLINK
        assert m.embed_profile  # defaulted, not crashed
        assert m.managed_paths == []  # absent in legacy
        assert m.state is ManifestState.COMPLETE

    def test_legacy_upgraded_on_write(self, installer, tmp_path):
        """A-6: reading a legacy manifest then re-writing upgrades it to the canonical superset."""
        embed = tmp_path / EMBED_DIR_NAME
        embed.mkdir()
        (embed / MANIFEST_FILENAME).write_text(json.dumps(self.LEGACY), encoding="utf-8")
        loaded = installer.read_manifest(tmp_path)
        assert loaded is not None
        installer.write_manifest(tmp_path, loaded)
        rewritten = json.loads((embed / MANIFEST_FILENAME).read_text())
        assert _CANONICAL_REQUIRED <= set(rewritten)
        assert rewritten["install_method"] == "symlink"


class TestCanonicalInterop:
    """End-to-end: a real SDK install must be verifiable by the real canonical planner."""

    def _canonical_has_verify(self, source: Path) -> bool:
        planner = source / "pipeline" / "embed_manifest.py"
        return planner.is_file() and "def verify_embed" in planner.read_text(encoding="utf-8")

    def test_canonical_verify_accepts_sdk_install(self, installer, cfg_factory, full_source, target):
        if not self._canonical_has_verify(full_source):
            pytest.skip("canonical pipeline/embed_manifest.py with verify_embed not available")
        result = installer.execute(cfg_factory())
        assert result.success, result.error
        embed = target / EMBED_DIR_NAME

        # Run canonical verify_embed in a subprocess to avoid `pipeline` module-cache contamination.
        script = (
            "import sys; from pathlib import Path; from pipeline import embed_manifest as em; "
            f"r = em.verify_embed(Path(r'{embed}')); "
            "print('PASS' if r.passed else 'FAIL:' + r.message); "
            "sys.exit(0 if r.passed else 1)"
        )
        env = dict(os.environ, PYTHONPATH=str(full_source))
        proc = subprocess.run(
            [sys.executable, "-c", script], capture_output=True, text=True, env=env
        )
        assert proc.returncode == 0, f"canonical verify failed: {proc.stdout}\n{proc.stderr}"
        assert "PASS" in proc.stdout
