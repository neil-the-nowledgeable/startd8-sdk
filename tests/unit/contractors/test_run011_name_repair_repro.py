"""Inc 6 — run-011 reproduction harness for manifest-driven name repair (FR-8).

Reproduces the run-011 M4 invention classes through the live pre-merge seam and
asserts the **honest** outcome the implementation produces:

* **Import inventions** (`@/lib/prisma`, `@/lib/ai/client`, `@/lib/db/<model>`)
  are repaired deterministically via the seeded negatives map + sub-path collapse.
* **Field inventions** split (Inc 3 finding): the substring near-match
  `supportingEvidence → evidence` is repaired; the pure synonyms
  (`title`, `aiRefId`, `label`) and the structural FK (`outcomeId`) have no
  string near-match and correctly **abstain** — leaving the checkpoint FAILED so
  the feature routes to LLM-retry (never a silent merge).
* A baseline with the gate disabled preserves existing behavior.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from startd8.contractors.checkpoint import CheckpointResult, CheckpointStatus
from startd8.contractors.integration_engine import IntegrationEngine
from startd8.repair.config import RepairConfig

# NB: deterministic (no LLM / no network) despite living under tests/integration/,
# so it is intentionally NOT marked `integration` (that marker is reserved for
# billable live-API tests and is skipped by default — see tests/conftest.py).

_SCHEMA = """
model Capability {
  id          String  @id
  name        String?
  category    String?
  description String?
}
model Differentiator {
  id          String  @id
  name        String?
  category    String?
  description String?
  evidence    String?
  notes       String?
}
model Metric {
  id          String  @id
  name        String?
  value       String?
  unit        String?
  timeframe   String?
  description String?
}
"""


class _StubCheckpoint:
    def pre_validate(self, paths):
        return CheckpointResult(status=CheckpointStatus.PASSED, name="pre", message="ok")


def _project(tmp_path):
    (tmp_path / "prisma").mkdir()
    (tmp_path / "prisma" / "schema.prisma").write_text(_SCHEMA, encoding="utf-8")
    (tmp_path / "lib" / "ai").mkdir(parents=True)
    (tmp_path / "lib" / "db.ts").write_text("export const db = {}\n", encoding="utf-8")
    (tmp_path / "lib" / "ai" / "service.ts").write_text("export const aiService = {}\n", encoding="utf-8")
    return tmp_path


def _engine(tmp_path, *, enabled=True):
    return IntegrationEngine(
        project_root=tmp_path, merge_strategy=object(), checkpoint=_StubCheckpoint(),
        repair_config=RepairConfig(pre_checkpoint_repair=enabled), element_registry=None,
    )


_UNIT = SimpleNamespace(name="m4", id="m4")


def test_pi002_import_subpath_collapse_repaired(tmp_path):
    _project(tmp_path)
    p = tmp_path / "lib" / "route.ts"
    p.write_text(
        "import { caps } from '@/lib/db/capabilities'\n"
        "await db.capability.create({ data: { name: n } })\n",
        encoding="utf-8",
    )
    result = _engine(tmp_path)._attempt_content_name_repair([p], _UNIT)
    text = p.read_text(encoding="utf-8")
    assert "from '@/lib/db'" in text and "@/lib/db/capabilities" not in text
    assert result is None or result.status != CheckpointStatus.FAILED


def test_pi007_mixed_inventions_partial_repair(tmp_path):
    """PI-007: two invented imports + a near-match field + a synonym field."""
    _project(tmp_path)
    p = tmp_path / "lib" / "differentiators.ts"
    p.write_text(
        "import { db } from '@/lib/prisma'\n"
        "import { ai } from '@/lib/ai/client'\n"
        "await db.differentiator.create({ data: { title: t, supportingEvidence: e } })\n",
        encoding="utf-8",
    )
    result = _engine(tmp_path)._attempt_content_name_repair([p], _UNIT)
    text = p.read_text(encoding="utf-8")
    # Imports repaired via seeded negatives:
    assert "from '@/lib/db'" in text and "@/lib/prisma" not in text
    assert "from '@/lib/ai/service'" in text and "@/lib/ai/client" not in text
    # Near-match field repaired:
    assert "evidence: e" in text and "supportingEvidence" not in text
    # Synonym abstained (no string near-match) — still present, checkpoint FAILED:
    assert "title: t" in text
    assert result is not None and result.status == CheckpointStatus.FAILED


def test_synonym_only_field_abstains_to_failed(tmp_path):
    """PI-001/004 synonym class: aiRefId/label have no near-match -> FAILED, unchanged."""
    _project(tmp_path)
    p = tmp_path / "lib" / "enrich.ts"
    p.write_text(
        "await db.capability.create({ data: { aiRefId: r, label: l, name: n } })\n",
        encoding="utf-8",
    )
    result = _engine(tmp_path)._attempt_content_name_repair([p], _UNIT)
    text = p.read_text(encoding="utf-8")
    assert "aiRefId" in text and "label" in text  # unchanged (abstained)
    assert result is not None and result.status == CheckpointStatus.FAILED


def test_baseline_gate_disabled_no_change(tmp_path):
    _project(tmp_path)
    p = tmp_path / "lib" / "x.ts"
    original = "import { db } from '@/lib/prisma'\n"
    p.write_text(original, encoding="utf-8")
    result = _engine(tmp_path, enabled=False)._attempt_content_name_repair([p], _UNIT)
    assert result is None
    assert p.read_text(encoding="utf-8") == original  # untouched


def test_repair_is_a_fixpoint(tmp_path):
    """R1-S7: re-running over the repaired tree makes no further edits."""
    _project(tmp_path)
    p = tmp_path / "lib" / "differentiators.ts"
    p.write_text(
        "import { db } from '@/lib/prisma'\n"
        "await db.differentiator.create({ data: { supportingEvidence: e, title: t } })\n",
        encoding="utf-8",
    )
    eng = _engine(tmp_path)
    eng._attempt_content_name_repair([p], _UNIT)
    after_first = p.read_text(encoding="utf-8")
    eng._attempt_content_name_repair([p], _UNIT)
    after_second = p.read_text(encoding="utf-8")
    assert after_first == after_second  # idempotent — no oscillation
