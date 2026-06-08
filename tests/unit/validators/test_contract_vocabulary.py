"""Tests for F-7 — provenance-vocabulary validation against the Prisma contract.

Validator-gate ask from VALIDATION_AND_MANIFEST_DERIVATION.md §8 F-7
(evidence: P3_RUN_010_QUALITY_EVAL.md §3 D2): the generated wizard wrote
``ownerId='default_owner'`` / ``source='wizard'`` — invented literals outside
the contract's declared domains (``local``; ``user|ai``) — making every row
silently invisible to every ``ownerId == 'local'`` filter.
"""

from __future__ import annotations

import ast
import textwrap

from startd8.forward_manifest_validator import validate_disk_compliance
from startd8.languages.prisma_parser import parse_prisma_schema
from startd8.validators.contract_vocabulary import (
    build_field_domains,
    check_contract_vocabulary,
    discover_prisma_schema,
)

# The RUN-010 contract shape: an enum-typed `source` (user|ai) plus a
# provenance String `ownerId` whose @default declares its domain (local).
SCHEMA = """\
enum Source {
  user
  ai
}

model Capability {
  id      String @id @default(cuid())
  ownerId String @default("local")
  source  Source
  title   String @default("Untitled")
}

model Outcome {
  id      String @id @default(cuid())
  ownerId String @default("local")
  source  Source
}
"""


def _schema():
    return parse_prisma_schema(SCHEMA)


def _check(source_code, schema=None):
    tree = ast.parse(textwrap.dedent(source_code))
    return check_contract_vocabulary(tree, schema or _schema())


def _write(tmp_path, rel_path, content):
    full = tmp_path / rel_path
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(textwrap.dedent(content), encoding="utf-8")
    return rel_path


# ---------------------------------------------------------------------------
# Domain extraction
# ---------------------------------------------------------------------------


class TestBuildFieldDomains:
    def test_enum_field_domain(self):
        domains = build_field_domains(_schema())
        allowed, source = domains["Capability"]["source"]
        assert allowed == frozenset({"user", "ai"})
        assert source == "enum:Source"

    def test_provenance_default_domain(self):
        domains = build_field_domains(_schema())
        allowed, source = domains["Capability"]["ownerId"]
        assert allowed == frozenset({"local"})
        assert source == "@default"

    def test_plain_string_default_not_a_domain(self):
        # `title String @default("Untitled")` is NOT provenance vocabulary
        domains = build_field_domains(_schema())
        assert "title" not in domains["Capability"]

    def test_id_default_cuid_not_a_domain(self):
        domains = build_field_domains(_schema())
        assert "id" not in domains.get("Capability", {})


# ---------------------------------------------------------------------------
# The RUN-010 shape — constructor keyword literals
# ---------------------------------------------------------------------------


class TestConstructorKeywords:
    def test_run010_invented_literals_flagged(self):
        issues = _check(
            """\
            def save(db):
                cap = Capability(source='wizard', ownerId='default_owner')
                db.add(cap)
            """
        )
        assert len(issues) == 2
        by_field = {i["field"]: i for i in issues}

        # enum-derived domain → provably-illegal → error severity.
        src = by_field["source"]
        assert src["category"] == "provenance_vocabulary"
        assert src["severity"] == "error"
        assert src["literal"] == "wizard"
        assert src["allowed"] == ["ai", "user"]
        assert src["domain_source"] == "enum:Source"
        assert "wizard" in src["message"]
        assert "source" in src["message"]

        # @default-derived domain → heuristic suspicion → warning severity,
        # still surfaced in the issue list.
        owner = by_field["ownerId"]
        assert owner["severity"] == "warning"
        assert owner["literal"] == "default_owner"
        assert owner["allowed"] == ["local"]
        assert owner["domain_source"] == "@default"

    def test_declared_literals_pass(self):
        issues = _check(
            "cap = Capability(source='user', ownerId='local')\n"
            "out = Outcome(source='ai', ownerId='local')\n"
        )
        assert issues == []

    def test_attribute_qualified_constructor_matched(self):
        # tables.Capability(...) — Attribute callee resolves by .attr
        issues = _check("cap = tables.Capability(source='wizard')\n")
        assert len(issues) == 1
        assert issues[0]["field"] == "source"

    def test_non_model_callable_not_flagged(self):
        issues = _check("svc = SomeService(source='wizard')\n")
        assert issues == []

    def test_non_domain_field_not_flagged(self):
        issues = _check("cap = Capability(title='anything at all')\n")
        assert issues == []

    def test_non_literal_value_not_flagged(self):
        issues = _check("cap = Capability(source=request.source)\n")
        assert issues == []


# ---------------------------------------------------------------------------
# Attribute assignments + false-positive containment
# ---------------------------------------------------------------------------


class TestAttributeAssignments:
    def test_attribute_assignment_outside_union_flagged(self):
        issues = _check("cap.source = 'wizard'\n")
        assert len(issues) == 1
        assert issues[0]["field"] == "source"
        assert issues[0]["literal"] == "wizard"
        # `source` is enum-derived → error severity.
        assert issues[0]["severity"] == "error"

    def test_attribute_assignment_in_union_passes(self):
        issues = _check("cap.source = 'ai'\ncap.ownerId = 'local'\n")
        assert issues == []

    def test_bare_name_assignment_never_flagged(self):
        # `source = 'wizard'` is a local variable, not a model field
        issues = _check("source = 'wizard'\nownerId = 'default_owner'\n")
        assert issues == []

    def test_dict_keys_never_flagged(self):
        issues = _check("payload = {'source': 'wizard', 'ownerId': 'x'}\n")
        assert issues == []

    def test_annotated_attribute_assignment_flagged(self):
        issues = _check("cap.ownerId: str = 'default_owner'\n")
        assert len(issues) == 1
        assert issues[0]["field"] == "ownerId"
        # `ownerId` is @default-derived → warning severity.
        assert issues[0]["severity"] == "warning"

    def test_unknown_attribute_not_flagged(self):
        issues = _check("cap.status = 'whatever'\n")
        assert issues == []


# ---------------------------------------------------------------------------
# Axis-1 — severity by epistemic confidence (enum=error, @default=warning)
# ---------------------------------------------------------------------------


# Mirrors the real strtd8-v2-cascade contract: `source` is a provenance String
# with a literal @default("user") and NO enum. AI passes legitimately mark
# proposals source='ai' — the @default only names the fallback, so a closed
# domain would false-flag every such write.
STRTD8_SCHEMA = """\
enum Status {
  draft
  published
}

model Capability {
  id      String @id @default(cuid())
  source  String @default("user")
  status  Status @default(draft)
}
"""


def _strtd8_schema():
    return parse_prisma_schema(STRTD8_SCHEMA)


class TestAxis1SeveritySplit:
    def test_enum_violation_is_error(self):
        # `status` is enum-typed (closed set) — a bad literal is provably
        # illegal → error.
        issues = _check(
            "cap = Capability(status='archived')\n", schema=_strtd8_schema()
        )
        assert len(issues) == 1
        assert issues[0]["field"] == "status"
        assert issues[0]["severity"] == "error"
        assert issues[0]["domain_source"] == "enum:Status"

    def test_default_violation_is_warning(self):
        # `source String @default("user")` — `source='ai'` is a legitimate
        # second value the contract under-declared → warning, NOT error.
        issues = _check(
            "cap = Capability(source='ai')\n", schema=_strtd8_schema()
        )
        assert len(issues) == 1
        assert issues[0]["field"] == "source"
        assert issues[0]["severity"] == "warning"
        assert issues[0]["domain_source"] == "@default"

    def test_default_violation_stays_visible_in_issue_list(self):
        # Both an enum error and a @default warning appear in the same scan.
        issues = _check(
            "cap = Capability(source='ai', status='archived')\n",
            schema=_strtd8_schema(),
        )
        by_field = {i["field"]: i for i in issues}
        assert set(by_field) == {"source", "status"}
        assert by_field["source"]["severity"] == "warning"
        assert by_field["status"]["severity"] == "error"

    def test_default_warning_message_recommends_enum(self):
        issues = _check(
            "cap = Capability(source='ai')\n", schema=_strtd8_schema()
        )
        msg = issues[0]["message"]
        assert "enum" in msg.lower()
        assert "suspicious" in msg.lower()
        assert "ai" in msg

    def test_enum_error_message_keeps_invisibility_framing(self):
        issues = _check(
            "cap = Capability(status='archived')\n", schema=_strtd8_schema()
        )
        msg = issues[0]["message"]
        assert "invisible" in msg.lower()

    def test_strtd8_source_ai_does_not_hard_fail(self):
        # The proven false-positive: 5 legitimate `row.source = 'ai'` writes.
        # As an attribute assignment against the @default union → warning, so
        # it leaves the err_count that drives PARTIAL/FAIL.
        issues = _check("row.source = 'ai'\n", schema=_strtd8_schema())
        assert len(issues) == 1
        assert issues[0]["field"] == "source"
        assert issues[0]["severity"] == "warning"
        error_issues = [i for i in issues if i["severity"] == "error"]
        assert error_issues == []


# ---------------------------------------------------------------------------
# Schema discovery
# ---------------------------------------------------------------------------


class TestDiscoverPrismaSchema:
    def test_finds_schema_at_root(self, tmp_path):
        _write(tmp_path, "schema.prisma", SCHEMA)
        _write(tmp_path, "app/wizard.py", "x = 1\n")
        schema = discover_prisma_schema("app/wizard.py", str(tmp_path))
        assert schema is not None
        assert "Capability" in schema.models

    def test_finds_schema_in_prisma_dir(self, tmp_path):
        _write(tmp_path, "prisma/schema.prisma", SCHEMA)
        _write(tmp_path, "app/wizard.py", "x = 1\n")
        schema = discover_prisma_schema("app/wizard.py", str(tmp_path))
        assert schema is not None
        assert schema.enums.get("Source") == ("user", "ai")

    def test_no_schema_returns_none(self, tmp_path):
        _write(tmp_path, "app/wizard.py", "x = 1\n")
        assert discover_prisma_schema("app/wizard.py", str(tmp_path)) is None

    def test_absolute_file_path_absorbed(self, tmp_path):
        _write(tmp_path, "schema.prisma", SCHEMA)
        rel = _write(tmp_path, "app/wizard.py", "x = 1\n")
        schema = discover_prisma_schema(str(tmp_path / rel), str(tmp_path))
        assert schema is not None


# ---------------------------------------------------------------------------
# Wiring — validate_disk_compliance picks the check up (L14)
# ---------------------------------------------------------------------------


WIZARD_RUN010 = """\
from tables import Capability


def save_step(db, data):
    cap = Capability(source='wizard', ownerId='default_owner')
    db.add(cap)
    return cap
"""


class TestDiskComplianceWiring:
    def test_run010_shape_reaches_semantic_issues(self, tmp_path):
        _write(tmp_path, "schema.prisma", SCHEMA)
        _write(tmp_path, "app/tables.py", "class Capability:\n    pass\n")
        rel = _write(tmp_path, "app/wizard.py", WIZARD_RUN010)
        result = validate_disk_compliance(rel, str(tmp_path))
        vocab = [
            i for i in result.semantic_issues
            if isinstance(i, dict)
            and i.get("category") == "provenance_vocabulary"
        ]
        assert len(vocab) == 2
        assert {i["field"] for i in vocab} == {"source", "ownerId"}
        by_field = {i["field"]: i for i in vocab}
        # Axis-1 severity split survives the disk-compliance wiring.
        assert by_field["source"]["severity"] == "error"  # enum-derived
        assert by_field["ownerId"]["severity"] == "warning"  # @default-derived

    def test_no_prisma_contract_is_noop(self, tmp_path):
        _write(tmp_path, "app/tables.py", "class Capability:\n    pass\n")
        rel = _write(tmp_path, "app/wizard.py", WIZARD_RUN010)
        result = validate_disk_compliance(rel, str(tmp_path))
        vocab = [
            i for i in result.semantic_issues
            if isinstance(i, dict)
            and i.get("category") == "provenance_vocabulary"
        ]
        assert vocab == []

    def test_compliant_writes_stay_clean(self, tmp_path):
        _write(tmp_path, "schema.prisma", SCHEMA)
        _write(tmp_path, "app/tables.py", "class Capability:\n    pass\n")
        rel = _write(
            tmp_path, "app/wizard.py",
            "from tables import Capability\n\n\n"
            "def save_step(db):\n"
            "    return Capability(source='user', ownerId='local')\n",
        )
        result = validate_disk_compliance(rel, str(tmp_path))
        vocab = [
            i for i in result.semantic_issues
            if isinstance(i, dict)
            and i.get("category") == "provenance_vocabulary"
        ]
        assert vocab == []


# ---------------------------------------------------------------------------
# Postmortem accounting — same posture as the other semantic checks
# ---------------------------------------------------------------------------


class TestPostmortemAccounting:
    def test_kaizen_suggestion_mapping_exists(self):
        from startd8.contractors.prime_postmortem import (
            CAUSE_TO_SUGGESTION,
            _SEMANTIC_CATEGORY_TO_SUGGESTION,
        )

        key = _SEMANTIC_CATEGORY_TO_SUGGESTION["provenance_vocabulary"]
        assert key in CAUSE_TO_SUGGESTION
        assert CAUSE_TO_SUGGESTION[key]["phase"] == "draft"

    def test_not_a_critical_category(self):
        # Same posture as the other semantic checks: error-severity issues
        # count toward the err_count verdict thresholds (>=2 PARTIAL,
        # >=4 FAIL) rather than single-issue disqualification.
        from startd8.contractors.prime_postmortem import (
            _CRITICAL_SEMANTIC_CATEGORIES,
        )

        assert "provenance_vocabulary" not in _CRITICAL_SEMANTIC_CATEGORIES
