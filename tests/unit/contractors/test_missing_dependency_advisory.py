"""Advisory missing-dependency surfacing in integration (RUN-014/015/016 invented-dep class).

`IntegrationEngine._warn_external_dependencies` flags bare imports of packages absent from
`package.json` during a run (not just in the postmortem). Advisory — it returns warnings and
never blocks. Tested via a stub self (the method only needs project_root + _rel_to_root).
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

ie = pytest.importorskip("startd8.contractors.integration_engine")
IntegrationEngine = ie.IntegrationEngine

pytestmark = pytest.mark.unit


def _stub(tmp_path):
    return SimpleNamespace(
        project_root=tmp_path,
        _rel_to_root=lambda p: Path(p).relative_to(tmp_path).as_posix(),
    )


def _write(tmp_path, rel, text):
    p = tmp_path / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


def _warn(tmp_path, paths):
    return IntegrationEngine._warn_external_dependencies(_stub(tmp_path), paths)


def test_flags_invented_external_dependency(tmp_path):
    _write(tmp_path, "package.json", '{"dependencies": {"zod": "^3.0.0"}}')
    ts = _write(
        tmp_path,
        "app/route.ts",
        'import { z } from "zod";\nimport { generateObject } from "ai";\n',
    )
    warns = _warn(tmp_path, [ts])
    assert any("ai" in w for w in warns)  # the invented dep is surfaced
    assert not any("zod" in w for w in warns)  # the declared dep is not


def test_no_warning_when_all_deps_declared(tmp_path):
    _write(tmp_path, "package.json", '{"dependencies": {"zod": "^3.0.0"}}')
    ts = _write(tmp_path, "app/route.ts", 'import { z } from "zod";\n')
    assert _warn(tmp_path, [ts]) == []


def test_no_package_json_yields_no_findings(tmp_path):
    # Cannot verify without package.json → no false positives.
    ts = _write(tmp_path, "app/route.ts", 'import { generateObject } from "ai";\n')
    assert _warn(tmp_path, [ts]) == []


def test_node_builtins_and_relative_not_flagged(tmp_path):
    _write(tmp_path, "package.json", '{"dependencies": {}}')
    ts = _write(
        tmp_path,
        "app/route.ts",
        'import path from "node:path";\nimport { x } from "./local";\n',
    )
    assert _warn(tmp_path, [ts]) == []


def test_non_ts_paths_are_skipped(tmp_path):
    py = _write(tmp_path, "x.py", "import os\n")
    assert _warn(tmp_path, [py]) == []
