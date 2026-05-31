"""RUN-007 regression lock (Step 7 / FR-8).

Two independent guards against re-regression of the partial-delivery incident
(16/16 reported PASS but 9/16 files were empty-class stubs at $0.00):

1. **Generation side** — every run-007 target shape is suppressed at the Step-2
   gate (no unfilled stem-stub skeleton is ever emitted; the file routes to
   escalation/refusal).
2. **Detection side (R5-S5)** — every run-007 stub shape, fed *directly* to the
   disk validator, FAILs (ast_valid=False, disk-quality score ≤ ceiling),
   independent of the generation path. So if a stub ever slips through, the
   postmortem sees it instead of scoring it ~0.94.
"""

from types import SimpleNamespace

import pytest

from startd8.forward_manifest_validator import (
    validate_disk_compliance,
    compute_disk_quality_score,
)
from startd8.micro_prime.prime_adapter import MicroPrimeCodeGenerator


# The exact 9 stub shapes from run-007 (path, stem-as-emitted).
RUN007_SHAPES = [
    ("lib/env.ts", "env"),
    ("lib/db.ts", "db"),
    ("lib/value-model.ts", "value-model"),          # invalid JS id (hyphen)
    ("app/layout.tsx", "layout"),
    ("app/page.tsx", "page"),
    ("app/profile/page.tsx", "page"),
    ("app/api/profile/route.ts", "route"),
    ("app/api/proof-points/route.ts", "route"),
    ("app/api/proof-points/[id]/route.ts", "route"),
]


def _stub(stem: str) -> str:
    return f"\nexport class {stem} {{\n\n}}\n"


def _write(tmp_path, rel, content):
    full = tmp_path / rel
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(content, encoding="utf-8")
    return rel


# ---------------------------------------------------------------------------
# Detection side — R5-S5 detector-regression lock
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestDetectorRegressionLock:
    @pytest.mark.parametrize("path,stem", RUN007_SHAPES)
    def test_each_run007_stub_fails_disk_validation(self, tmp_path, path, stem):
        rel = _write(tmp_path, path, _stub(stem))
        result = validate_disk_compliance(rel, str(tmp_path))
        assert result.ast_valid is False, f"{path} stub must FAIL disk validation"
        assert compute_disk_quality_score(result) <= 0.3, (
            f"{path} stub must score at/below the low ceiling (run-007 was ~0.94)"
        )

    def test_go_package_main_silent_empty_or_stub_not_healthy(self, tmp_path):
        # Go non-main empty-struct stub also fails the detector.
        rel = _write(tmp_path, "pkg/widget/widget.go",
                     "package widget\n\ntype Widget struct {\n}\n")
        result = validate_disk_compliance(rel, str(tmp_path))
        assert result.ast_valid is False


# ---------------------------------------------------------------------------
# Generation side — Step-2 gate suppresses every shape (never ships a stub)
# ---------------------------------------------------------------------------

def _spec(path, stem):
    return SimpleNamespace(
        file=path, elements=[{"kind": "class", "name": stem}],
        language=None, imports=[], metadata={}, bases=[],
    )


@pytest.mark.unit
class TestGateRegressionLock:
    @pytest.mark.parametrize("path,stem", RUN007_SHAPES)
    def test_each_run007_shape_is_suppressed_not_stubbed(self, path, stem):
        gen = MicroPrimeCodeGenerator()
        manifest = SimpleNamespace(file_specs={path: _spec(path, stem)})
        ctx = {}
        skeletons = gen._generate_skeletons(manifest, [path], ctx)
        # never emits a stem-stub skeleton; routes to escalation/refusal
        assert path not in skeletons
        assert path in ctx.get("_empty_spec_files", set())

    def test_go_main_empty_spec_is_suppressed(self):
        gen = MicroPrimeCodeGenerator()
        manifest = SimpleNamespace(
            file_specs={"cmd/main.go": _spec("cmd/main.go", "main")}
        )
        ctx = {}
        gen._generate_skeletons(manifest, ["cmd/main.go"], ctx)
        assert "cmd/main.go" in ctx.get("_empty_spec_files", set())

    def test_real_content_spec_is_not_suppressed(self):
        # control: a feature WITH a fillable element is not gated
        gen = MicroPrimeCodeGenerator()
        m = SimpleNamespace(file_specs={
            "lib/db.ts": SimpleNamespace(
                file="lib/db.ts",
                elements=[{"kind": "function", "name": "getClient"}],
                language=None, imports=[], metadata={}, bases=[],
            )
        })
        ctx = {}
        gen._generate_skeletons(m, ["lib/db.ts"], ctx)
        assert "lib/db.ts" not in ctx.get("_empty_spec_files", set())
