"""Vue SFC parity (NP1: FR-N1 semantic checks, FR-N2 compile gate, FR-N3 disk-compliance)."""

import shutil
from unittest.mock import MagicMock

import pytest

from startd8.contractors.integration_engine import IntegrationEngine
from startd8.repair.config import RepairConfig

_HAS_NODE = shutil.which("node") is not None

_DEFECTIVE_VUE = """<template><div>{{ count }}</div></template>
<script>
const grpc = require('@grpc/grpc-js')
export default {
  data() { var count = 0; return { count } },
  methods: { log(x) { console.log(x) } }
}
</script>
<style scoped>.x{}</style>
"""

_BROKEN_VUE = """<template><div/></template>
<script>
const a = 1
const a = 2
</script>
"""

_SCRIPTLESS_VUE = "<template><div>hi</div></template>\n<style>.x{}</style>\n"


# ── FR-N1: _run_semantic_checks runs nodejs checks on the extracted <script> ──

def test_fr_n1_vue_semantic_checks_populate_compliance(tmp_path):
    vue = tmp_path / "Cart.vue"
    vue.write_text(_DEFECTIVE_VUE)
    eng = IntegrationEngine(
        project_root=tmp_path, merge_strategy=MagicMock(),
        checkpoint=MagicMock(), repair_config=RepairConfig(expose_defects=True),
    )
    unit = MagicMock()
    unit.id = "u"
    unit.name = "Cart"
    cr = eng._run_semantic_checks([vue], unit)
    assert "Cart.vue" in cr
    cats = {si["category"] for si in cr["Cart.vue"]["semantic_issues"]}
    # regex-based nodejs checks run on the extracted <script> — no node binary needed
    assert "console_log_in_service" in cats
    assert "module_system_mixing" in cats


def test_fr_n1_template_style_not_scanned(tmp_path):
    # A var inside <template>/<style> must NOT be flagged — only the <script> is scanned.
    vue = tmp_path / "Plain.vue"
    vue.write_text("<template><div>var x</div></template>\n<script>const ok = 1\nexport default {}</script>\n")
    eng = IntegrationEngine(
        project_root=tmp_path, merge_strategy=MagicMock(),
        checkpoint=MagicMock(), repair_config=RepairConfig(),
    )
    unit = MagicMock()
    unit.id = "u"
    unit.name = "Plain"
    cr = eng._run_semantic_checks([vue], unit)
    # clean script → no compliance entry (or no var_usage)
    cats = {si["category"] for v in cr.values() for si in v.get("semantic_issues", [])}
    assert "var_usage" not in cats


# ── FR-N3: validate_disk_compliance routes .vue ──

def test_fr_n3_scriptless_vue_is_valid(tmp_path):
    from startd8.forward_manifest_validator import validate_disk_compliance
    vue = tmp_path / "View.vue"
    vue.write_text(_SCRIPTLESS_VUE)
    r = validate_disk_compliance(str(vue), str(tmp_path))
    assert r.ast_valid is True  # no <script> → nothing to compile → valid


@pytest.mark.skipif(not _HAS_NODE, reason="node not installed")
def test_fr_n3_broken_vue_script_is_invalid(tmp_path):
    from startd8.forward_manifest_validator import validate_disk_compliance
    vue = tmp_path / "Broken.vue"
    vue.write_text(_BROKEN_VUE)  # duplicate const → real syntax error in the script
    r = validate_disk_compliance(str(vue), str(tmp_path))
    assert r.ast_valid is False


# ── FR-N2: compile gate extracts <script> → node --check ──

@pytest.mark.skipif(not _HAS_NODE, reason="node not installed")
class TestVueCompileGate:
    def _vue_profile(self):
        from startd8.languages import LanguageRegistry, resolve_language
        LanguageRegistry.discover()
        return resolve_language(["x.vue"])

    def test_clean_vue_script_passes(self, tmp_path):
        from startd8.benchmark_matrix.scoring import score_file
        vue = tmp_path / "Clean.vue"
        vue.write_text("<template><div/></template>\n<script>\nimport x from 'y'\nexport default { name: 'C' }\n</script>\n")
        sc = score_file(vue, self._vue_profile(), structural=1.0, run_lint=False)
        assert sc.compile_ok is True
        assert sc.value == pytest.approx(1.0)

    def test_broken_vue_script_floors(self, tmp_path):
        from startd8.benchmark_matrix.scoring import score_file, COMPILE_FLOOR
        vue = tmp_path / "Broken.vue"
        vue.write_text(_BROKEN_VUE)
        sc = score_file(vue, self._vue_profile(), structural=1.0, run_lint=False)
        assert sc.compile_ok is False
        assert sc.value == COMPILE_FLOOR

    def test_scriptless_vue_degrades_not_floors(self, tmp_path):
        from startd8.benchmark_matrix.scoring import score_file
        vue = tmp_path / "View.vue"
        vue.write_text(_SCRIPTLESS_VUE)
        sc = score_file(vue, self._vue_profile(), structural=0.9, run_lint=False)
        assert sc.compile_ok is None      # no <script> → degraded, not floored
        assert sc.value == pytest.approx(0.9)
