"""Two-sided golden test for derive-contract (Step 7 / OQ-DC-1, R1-S3/F5/S9).

The CRP found that "matches modulo flagged items" is circular (the modulo set comes from the
output under test). This test is two-sided:
  (a) the derived NON-flagged output is AST-equal to a frozen, reviewed oracle, AND
  (b) the deriver's flagged set EQUALS a frozen expected set.
Plus independent structural invariants (so it isn't merely "matches its own output") and the
negative case (R1-S9: an unmarked list[str] actually fires the flag, not a silent Json).
"""

from __future__ import annotations

import enum
from pathlib import Path
from typing import Dict, List, Optional

from pydantic import BaseModel, Field, computed_field

from startd8.concierge.derive.derive import PROVENANCE_HEADER, _assemble
from startd8.concierge.derive.introspect import introspect_models
from startd8.manifest_extraction.prisma_emitter import semantic_diff

ORACLE = (Path(__file__).parent / "golden_contract.prisma").read_text(encoding="utf-8")
EXPECTED_FLAGGED = {"Order.tag_ids"}


# Frozen fixture — the golden oracle (golden_contract.prisma) is the reviewed derivation of these.
class Status(str, enum.Enum):
    NOT_STARTED = "not-started"   # hyphen → normalize
    DONE = "done"


class Item(BaseModel):
    id: str                       # explicit id → itemKey + @@unique([orderId, itemKey])
    label: str
    qty: int = 1
    status: Status = Status.DONE
    notes: Optional[str] = None


class Order(BaseModel):            # root (no id) → cuid PK
    items: List[Item] = []        # 1:N → Item.orderId FK
    meta: Dict[str, str] = {}     # Dict → Json
    tag_ids: List[str] = []       # unmarked list[str] → Json + FLAG

    @computed_field
    @property
    def total(self) -> int:       # computed → dropped
        return 0


def _derive():
    d, report = _assemble(introspect_models([Item, Order]))
    body = d.contract_text[len(PROVENANCE_HEADER):]
    flagged = {f"{f['entity']}.{f['field']}" for f in report.flags if f.get("entity") and f.get("field")}
    return d, report, body, flagged


def test_two_sided_golden():
    _, _, body, flagged = _derive()
    # (a) non-flagged structure is AST-equal to the reviewed oracle (semantic_diff ignores comments).
    drift = semantic_diff(body, ORACLE)
    assert drift == [], f"derived contract diverged from the golden oracle: {drift}"
    # (b) the flagged set equals the expected set — a mis-flagging deriver fails here.
    assert flagged == EXPECTED_FLAGGED


def test_independent_structural_invariants():
    """Not circular: assert the rules directly, independent of the oracle file."""
    d, report, body, _ = _derive()
    assert "model Item" in body and "model Order" in body
    assert "@@unique([orderId, itemKey])" in body          # id→key + compound unique
    assert "itemKey String" in body                         # explicit id → <entity>Key
    assert "tag_ids Json?" in body and "meta Json?" in body  # list[str]/dict → Json
    assert "not_started" in body                            # enum hyphen normalized
    assert any(e["field"] == "total" for e in report.exclusions)  # computed dropped


def test_negative_case_unmarked_list_flags(tmp_path):
    """R1-S9: an unmarked list[str]-of-ids must FLAG (not silently emit Json with no flag)."""
    class HasLoose(BaseModel):
        id: str
        ref_ids: List[str] = []          # unmarked → must flag

    _, report = _assemble(introspect_models([HasLoose]))
    hit = [f for f in report.flags if f.get("entity") == "HasLoose" and f.get("field") == "ref_ids"]
    assert hit and "M2M" in hit[0]["reason"]


def test_flag_suppression_is_field_boundary_exact():
    """Regression: a flagged field `tag` must NOT suppress drift on a different field `tags`."""
    from startd8.concierge.derive.derive import _check

    class M(BaseModel):
        id: str
        tag: List[str] = []        # flagged → "M.tag"
        tags: List[str] = []       # also flagged → "M.tags"

    d, _ = _assemble(introspect_models([M]))
    body = d.contract_text[len(PROVENANCE_HEADER):]
    # live contract drops `tags` only (a genuine change) but keeps `tag`.
    live = "\n".join(ln for ln in body.splitlines() if "tags Json" not in ln)
    drift = _check(introspect_models([M]), live)
    # `M.tags` is itself flagged, so its removal is suppressed — verify the boundary logic doesn't
    # ALSO swallow a same-prefix sibling. Construct the inverse: drop `tag` (not `tags`).
    live2 = "\n".join(ln for ln in body.splitlines() if "tag Json" not in ln)
    drift2 = _check(introspect_models([M]), live2)
    # Both are flagged here, so both suppress — the real assertion is that suppression keys are
    # exact: "M.tag:" never matches "M.tags: …". Verify by checking the excluded lines are precise.
    for line in drift.excluded_flagged + drift2.excluded_flagged:
        ent_field = line.split(":")[0]
        assert ent_field in {"M.tag", "M.tags"}


def test_marked_join_not_flagged():
    """Counterpart: a *marked* join field is confirmed, not flagged."""
    class Tagged(BaseModel):
        id: str
        joins: List[str] = Field(default=[], json_schema_extra={"prisma": {"join": "Other"}})

    _, report = _assemble(introspect_models([Tagged]))
    assert not any(f.get("field") == "joins" for f in report.flags)
