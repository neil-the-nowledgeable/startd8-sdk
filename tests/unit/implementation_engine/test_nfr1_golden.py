"""NFR-1 golden-file regression: spec prompts for features WITHOUT
forward_manifest data must remain byte-identical to the pre-Fix-1 baseline.

Fixtures live in ``tests/regression/no_forward_manifest/*.yaml``; committed
``*.sha256`` goldens were captured from the PRE-Fix-1 code (HEAD~2) so a passing
check proves the draft-time injection (Fix 1) did not change the no-forward path.

Re-record goldens with::

    STARTD8_RECORD_GOLDEN=1 pytest tests/unit/implementation_engine/test_nfr1_golden.py
"""

import hashlib
import os
from pathlib import Path

import pytest
import yaml

from startd8.implementation_engine.spec_builder import build_spec_prompt

_REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURE_DIR = _REPO_ROOT / "tests" / "regression" / "no_forward_manifest"
_FIXTURES = sorted(FIXTURE_DIR.glob("*.yaml"))
_RECORD = os.environ.get("STARTD8_RECORD_GOLDEN") == "1"

# Keys that would route through the forward-manifest section; banned in fixtures.
_FORWARD_KEYS = ("forward_contracts", "forward_element_specs")


def _render(fixture_path: Path) -> str:
    data = yaml.safe_load(fixture_path.read_text())
    ctx = dict(data.get("context") or {})
    for key in _FORWARD_KEYS:
        assert key not in ctx, f"{fixture_path.name} must contain no forward-manifest data ({key})"
    return build_spec_prompt(
        data["task_description"],
        ctx,
        data.get("output_format"),
        template_key=data.get("template_key"),
    )


def test_fixture_dir_has_at_least_three_fixtures():
    assert FIXTURE_DIR.is_dir(), f"missing fixture dir {FIXTURE_DIR}"
    assert len(_FIXTURES) >= 3, f"NFR-1 requires N>=3 fixtures, found {len(_FIXTURES)}"


@pytest.mark.parametrize("fixture_path", _FIXTURES, ids=[p.stem for p in _FIXTURES])
def test_no_forward_manifest_byte_identical(fixture_path: Path):
    rendered = _render(fixture_path)
    # NFR-3: same input -> same output within a run.
    assert _render(fixture_path) == rendered, f"non-deterministic render for {fixture_path.name}"

    digest = hashlib.sha256(rendered.encode("utf-8")).hexdigest()
    golden = fixture_path.with_suffix(".sha256")

    if _RECORD:
        golden.write_text(f"{digest}  {fixture_path.name}\n")
        pytest.skip(f"recorded golden for {fixture_path.name}")

    assert golden.exists(), (
        f"missing golden {golden.name}; capture with STARTD8_RECORD_GOLDEN=1"
    )
    expected = golden.read_text().split()[0].strip()
    assert digest == expected, (
        f"NFR-1 byte-identical drift for {fixture_path.name}: {digest} != {expected}"
    )
