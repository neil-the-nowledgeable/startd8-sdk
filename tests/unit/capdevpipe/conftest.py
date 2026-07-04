"""Shared fixtures for cap-dev-pipe installer tests."""

import os
import shutil
import stat
from pathlib import Path

import pytest

from startd8.capdevpipe_embed_manifest import DEFAULT_EMBED_PROFILE, resolve_embed_inventory
from startd8.capdevpipe_installer import (
    DEFAULT_SOURCE,
    WRAPPER_TEMPLATE_NAME,
    CapDevPipeInstaller,
    InstallConfig,
    InstallMethod,
    ProfileSpec,
)

FIXTURE_ROOT = Path(__file__).resolve().parent.parent.parent / "fixtures" / "capdevpipe"

# A run.sh that resolves SCRIPT_DIR from $0 (exercising the single-source property, NFR-3)
# and lists the language-profile subdirs it finds locally — a faithful stand-in for the real
# cap-dev-pipe run.sh --list-langs, sufficient for verify() (FR-11) tests.
FAKE_RUN_SH = """#!/usr/bin/env bash
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
if [[ " $* " == *" --list-langs "* ]]; then
    echo "Available language profiles:"
    echo ""
    for d in "$SCRIPT_DIR"/*/; do
        name="$(basename "$d")"
        if ls "$d"/*-plan.md >/dev/null 2>&1 || ls "$d"/*-requirements.md >/dev/null 2>&1; then
            echo "  $name/"
            echo "    plan: $name-plan.md"
        fi
    done
    exit 0
fi
exit 0
"""


def seed_capdevpipe_manifest(src: Path) -> None:
    """Copy embed-manifest.yaml and pipeline/ planner into a fixture checkout."""
    cap_src = Path(os.environ.get("CAP_DEV_PIPE_SOURCE", DEFAULT_SOURCE))
    if (cap_src / "embed-manifest.yaml").is_file():
        shutil.copy2(cap_src / "embed-manifest.yaml", src / "embed-manifest.yaml")
        shutil.copytree(cap_src / "pipeline", src / "pipeline", dirs_exist_ok=True)
    else:
        shutil.copy2(FIXTURE_ROOT / "embed-manifest.yaml", src / "embed-manifest.yaml")
        shutil.copytree(FIXTURE_ROOT / "pipeline", src / "pipeline", dirs_exist_ok=True)


def seed_embed_inventory_files(src: Path, profile: str = DEFAULT_EMBED_PROFILE) -> None:
    """Stub all files/dirs required by *profile* after the manifest is present."""
    seed_capdevpipe_manifest(src)
    inventory = resolve_embed_inventory(src, profile)
    for name in (*inventory.scripts, *inventory.python_aliases):
        path = src / name
        if name == "run.sh":
            path.write_text(FAKE_RUN_SH, encoding="utf-8")
            os.chmod(
                path, path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH
            )
        else:
            path.write_text("# stub\n", encoding="utf-8")
    for pkg in inventory.packages:
        pkg_dir = src / pkg
        pkg_dir.mkdir(parents=True, exist_ok=True)
        init_py = pkg_dir / "__init__.py"
        if not init_py.is_file():
            init_py.write_text("# stub\n", encoding="utf-8")
    for copy_name in inventory.copy_files:
        path = src / copy_name
        if not path.is_file():
            path.write_text("# stub template\n", encoding="utf-8")
    for resource in inventory.resource_trees:
        res_dir = src / resource
        res_dir.mkdir(parents=True, exist_ok=True)
        sample = res_dir / "sample.txt"
        if not sample.is_file():
            sample.write_text("x", encoding="utf-8")


@pytest.fixture
def installer():
    return CapDevPipeInstaller()


@pytest.fixture
def full_source(tmp_path):
    """A complete cap-dev-pipe checkout stand-in: manifest-resolved embed set."""
    src = tmp_path / "cap-dev-pipe"
    src.mkdir()
    seed_embed_inventory_files(src)
    # A functional stand-in for install-cap-dev-pipe.sh: copies scripts + design/prompts
    # into <target>/.cap-dev-pipe and writes a (wrong-paths) pipeline.env for reconcile to
    # fix. Faithful enough to exercise the copy path end-to-end (FR-6).
    installer_sh = src / "install-cap-dev-pipe.sh"
    installer_sh.write_text(
        "#!/usr/bin/env bash\n"
        "set -e\n"
        'SRC="$(cd "$(dirname "$0")" && pwd)"\n'
        'TARGET="${@: -1}"\n'
        'DEST="$TARGET/.cap-dev-pipe"\n'
        'mkdir -p "$DEST"\n'
        'cp "$SRC"/*.sh "$SRC"/*.py "$SRC"/*.yaml "$DEST"/ 2>/dev/null || true\n'
        'cp -R "$SRC/design" "$DEST/" 2>/dev/null || true\n'
        'cp -R "$SRC/prompts" "$DEST/" 2>/dev/null || true\n'
        'cp -R "$SRC/pipeline" "$DEST/" 2>/dev/null || true\n'
        'printf \'CONTEXTCORE_ROOT="/wrong"\\nSDK_ROOT="/wrong"\\n'
        'PROJECT_ROOT="/wrong"\\nPROJECT_NAME="wrong"\\n\' > "$DEST/pipeline.env"\n',
        encoding="utf-8",
    )
    os.chmod(
        installer_sh,
        installer_sh.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH,
    )
    (src / WRAPPER_TEMPLATE_NAME).write_text(
        "#!/usr/bin/env bash\n"
        "# {{PROJECT_NAME}} wrapper, default lang {{DEFAULT_LANG}}\n"
        'SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"\n'
        'exec "$SCRIPT_DIR/run.sh" --lang {{DEFAULT_LANG}} "$@"\n',
        encoding="utf-8",
    )
    return src


@pytest.fixture
def target(tmp_path):
    t = tmp_path / "project"
    t.mkdir()
    return t


FULL_ENV = {
    "CONTEXTCORE_ROOT": "/home/u/ContextCore",
    "SDK_ROOT": "/home/u/startd8-sdk",
    "PROJECT_ROOT": "/home/u/proj",
    "PROJECT_NAME": "proj",
}


def make_cfg(
    source, target, method=InstallMethod.SYMLINK, env=None, profiles=None, **kw
):
    return InstallConfig(
        source_path=source,
        target_root=target,
        method=method,
        pipeline_env=env if env is not None else dict(FULL_ENV),
        default_lang=kw.get("default_lang", "python"),
        profiles=profiles or [],
        profile_method=kw.get("profile_method"),
        rerun_mode=kw.get("rerun_mode"),
        embed_profile=kw.get("embed_profile", DEFAULT_EMBED_PROFILE),
        # Tests use a fixture source dir (not the default checkout); opt into executing its
        # copy installer. The trust check itself is covered in test_hardening.py.
        trust_source=kw.get("trust_source", True),
    )


@pytest.fixture
def cfg_factory(full_source, target):
    def _factory(**kw):
        return make_cfg(kw.pop("source", full_source), kw.pop("target", target), **kw)

    return _factory


__all__ = [
    "installer",
    "full_source",
    "target",
    "cfg_factory",
    "make_cfg",
    "ProfileSpec",
    "FULL_ENV",
    "seed_embed_inventory_files",
    "seed_capdevpipe_manifest",
]
