"""Shared fixtures for cap-dev-pipe installer tests."""

import os
import stat

import pytest

from startd8.capdevpipe_installer import (
    EMBED_ALIASES,
    EMBED_RESOURCE_DIRS,
    EMBED_SCRIPTS,
    WRAPPER_TEMPLATE_NAME,
    CapDevPipeInstaller,
    InstallConfig,
    InstallMethod,
    ProfileSpec,
)

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


@pytest.fixture
def installer():
    return CapDevPipeInstaller()


@pytest.fixture
def full_source(tmp_path):
    """A complete cap-dev-pipe checkout stand-in: all embed files, a working run.sh,
    design/+prompts/, the wrapper template, and install-cap-dev-pipe.sh."""
    src = tmp_path / "cap-dev-pipe"
    src.mkdir()
    for name in (*EMBED_SCRIPTS, *EMBED_ALIASES):
        path = src / name
        if name == "run.sh":
            path.write_text(FAKE_RUN_SH, encoding="utf-8")
            os.chmod(
                path, path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH
            )
        else:
            path.write_text("# stub\n", encoding="utf-8")
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
    for d in EMBED_RESOURCE_DIRS:
        (src / d).mkdir()
        (src / d / "sample.txt").write_text("x", encoding="utf-8")
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
]
