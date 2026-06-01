"""Inc 5 — content-contract name repair in the pre-merge seam (FR-1/FR-7)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from startd8.contractors.checkpoint import CheckpointResult, CheckpointStatus
from startd8.contractors.integration_engine import IntegrationEngine
from startd8.repair.config import RepairConfig

_SCHEMA = """
model Capability {
  id   String  @id @default(cuid())
  name String?
  category String?
  description String?
}
model Differentiator {
  id   String  @id @default(cuid())
  name String?
  category String?
  description String?
  evidence String?
  notes String?
}
model Metric {
  id   String  @id @default(cuid())
  name String?
  value String?
  unit String?
  timeframe String?
  description String?
}
"""


class _StubCheckpoint:
    def pre_validate(self, paths):
        return CheckpointResult(status=CheckpointStatus.PASSED, name="pre", message="ok")


def _project(tmp_path):
    (tmp_path / "prisma").mkdir()
    (tmp_path / "prisma" / "schema.prisma").write_text(_SCHEMA, encoding="utf-8")
    (tmp_path / "lib").mkdir()
    (tmp_path / "lib" / "db.ts").write_text("export const db = {}\n", encoding="utf-8")
    return tmp_path


def _engine(tmp_path, *, enabled=True):
    return IntegrationEngine(
        project_root=tmp_path,
        merge_strategy=object(),
        checkpoint=_StubCheckpoint(),
        repair_config=RepairConfig(pre_checkpoint_repair=enabled),
        element_registry=None,
    )


def _write(tmp_path, name, content):
    p = tmp_path / "lib" / name
    p.write_text(content, encoding="utf-8")
    return p


_UNIT = SimpleNamespace(name="t", id="t")


def test_gate_off_returns_none(tmp_path):
    _project(tmp_path)
    p = _write(tmp_path, "x.ts", "await db.metric.create({ data: { outcomeId: o } })\n")
    eng = _engine(tmp_path, enabled=False)  # pre_checkpoint_repair off
    assert eng._attempt_content_name_repair([p], _UNIT) is None


def test_abstain_is_not_a_silent_pass(tmp_path):
    """R4-S1: a structural invention that passes syntax must FAIL the checkpoint."""
    _project(tmp_path)
    p = _write(tmp_path, "m.ts", "await db.metric.create({ data: { outcomeId: o, name: n } })\n")
    eng = _engine(tmp_path)
    result = eng._attempt_content_name_repair([p], _UNIT)
    assert result is not None
    assert result.status == CheckpointStatus.FAILED
    # File unchanged (abstained, no near-match).
    assert "outcomeId" in p.read_text(encoding="utf-8")


def test_import_invention_repaired_via_seeded_map(tmp_path):
    _project(tmp_path)
    p = _write(
        tmp_path, "c.ts",
        "import { db } from '@/lib/prisma'\nawait db.capability.create({ data: { name: n } })\n",
    )
    eng = _engine(tmp_path)
    result = eng._attempt_content_name_repair([p], _UNIT)
    # Specifier rewritten to the canonical on-disk path; no residual -> not FAILED.
    assert "from '@/lib/db'" in p.read_text(encoding="utf-8")
    assert "@/lib/prisma" not in p.read_text(encoding="utf-8")
    assert result is None or result.status != CheckpointStatus.FAILED


def test_partial_repair_kept_but_checkpoint_fails_on_residual(tmp_path):
    """R4-S2: a near-match field is repaired and kept even though an abstained
    structural invention in the same file keeps the checkpoint FAILED."""
    _project(tmp_path)
    p = _write(
        tmp_path, "mix.ts",
        "await db.differentiator.create({ data: { supportingEvidence: e } });\n"
        "await db.metric.update({ where: { id }, data: { outcomeId: o } });\n",
    )
    eng = _engine(tmp_path)
    result = eng._attempt_content_name_repair([p], _UNIT)
    text = p.read_text(encoding="utf-8")
    # Partial success preserved:
    assert "evidence: e" in text
    assert "supportingEvidence" not in text
    # Residual structural invention -> FAILED (routes to retry):
    assert result is not None and result.status == CheckpointStatus.FAILED
    assert "outcomeId" in text


def test_non_ts_feature_is_skipped(tmp_path):
    _project(tmp_path)
    p = tmp_path / "lib" / "x.py"
    p.write_text("x = 1\n", encoding="utf-8")
    eng = _engine(tmp_path)
    assert eng._attempt_content_name_repair([p], _UNIT) is None
