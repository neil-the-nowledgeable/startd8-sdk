"""Inc 6 — project-convention detection (FR-5).

Detects the `@/` alias from tsconfig, and barrel / CSS-module / types-dir usage from the
file tree. The absence of a convention is a first-class signal (the RUN-012 anti-invention).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from startd8.frontend_codegen import detect_project_conventions

pytestmark = pytest.mark.unit

_TSCONFIG_ALIASED = """{
  // path aliases
  "compilerOptions": {
    "baseUrl": ".",
    "paths": {
      "@/*": ["./*"]
    },
    "noEmit": true,
  }
}
"""

_STRTD8 = Path("/Users/neilyashinsky/Documents/dev/strtd8/strtd8")


def _write(root: Path, rel: str, content: str = "") -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


# --------------------------------------------------------------------------- #
# Alias detection (JSONC-tolerant)
# --------------------------------------------------------------------------- #


def test_detects_alias_from_jsonc_tsconfig(tmp_path):
    _write(tmp_path, "tsconfig.json", _TSCONFIG_ALIASED)
    c = detect_project_conventions(tmp_path)
    assert c.alias == "@/"
    assert c.alias_target == "./"


def test_no_tsconfig_means_no_alias(tmp_path):
    c = detect_project_conventions(tmp_path)
    assert c.alias is None
    assert c.alias_target is None


# --------------------------------------------------------------------------- #
# Absence is first-class (the RUN-012 anti-invention signal)
# --------------------------------------------------------------------------- #


def test_bare_project_uses_no_barrels_or_css(tmp_path):
    _write(tmp_path, "tsconfig.json", _TSCONFIG_ALIASED)
    _write(tmp_path, "lib/value-model.ts", "export const x = 1;")
    c = detect_project_conventions(tmp_path)
    assert c.uses_barrels is False
    assert c.uses_css_modules is False
    assert c.has_types_dir is False


def test_detects_barrel_index_file(tmp_path):
    _write(tmp_path, "components/steps/Step.tsx", "export const Step = () => null;")
    _write(tmp_path, "components/steps/index.ts", "export * from './Step';")
    assert detect_project_conventions(tmp_path).uses_barrels is True


def test_plain_index_without_reexport_is_not_a_barrel(tmp_path):
    # An index.ts that defines, not re-exports, is not a barrel.
    _write(tmp_path, "lib/index.ts", "export const VERSION = '1';")
    assert detect_project_conventions(tmp_path).uses_barrels is False


def test_detects_css_modules(tmp_path):
    _write(tmp_path, "components/Wizard.module.css", ".root { color: red; }")
    assert detect_project_conventions(tmp_path).uses_css_modules is True


def test_detects_types_dir(tmp_path):
    (tmp_path / "types").mkdir()
    assert detect_project_conventions(tmp_path).has_types_dir is True


def test_node_modules_is_pruned(tmp_path):
    # A barrel/CSS inside node_modules must not count as a project convention.
    _write(tmp_path, "node_modules/pkg/index.ts", "export * from './x';")
    _write(tmp_path, "node_modules/pkg/x.module.css", ".a {}")
    c = detect_project_conventions(tmp_path)
    assert c.uses_barrels is False
    assert c.uses_css_modules is False


# --------------------------------------------------------------------------- #
# Real strtd8 project (skipif absent) — the documented RUN-012 reality
# --------------------------------------------------------------------------- #


@pytest.mark.skipif(not _STRTD8.is_dir(), reason="strtd8 project not present")
def test_real_strtd8_conventions():
    c = detect_project_conventions(_STRTD8)
    assert c.alias == "@/"
    assert c.alias_target == "./"
    # strtd8 uses no barrels and no CSS modules — RUN-012's inventions don't fit the
    # project at all; detection makes that an explicit anti-invention signal.
    assert c.uses_barrels is False
    assert c.uses_css_modules is False
    assert c.has_types_dir is False
