"""Deterministic Alembic revision generation from the Prisma contract — OQ-SCAF-2 fork B (FR-MG-2/3/6).

The $0, on-charter alternative to live `alembic --autogenerate` (which is runtime + DB-stateful):
diff the *previous* contract snapshot against the *current* one and emit a revision with **additive**
ops only (`create_table` for new models, `add_column` for new fields) — never a drop. Each revision
**embeds the schema it migrates to** (a base64 snapshot header), so the next delta auto-discovers its
"previous" from the latest revision — a self-contained chain, no external state (OQ-SCAF-2c).

Scope (MVP): columns (type, nullable, primary key, ``server_default`` from ``@default``) + compound
``@@unique``. Explicit foreign-key constraints and ``@@index`` are noted, not emitted (SQLite FK
enforcement is off by default; indexes are perf, not correctness) — surfaced as plan notes, never
silently dropped. Type changes / removals are reported, never auto-migrated (data-loss class).
"""

from __future__ import annotations

import base64
import re
from dataclasses import dataclass, field as _dc_field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from ..languages.prisma_parser import (
    PrismaField,
    PrismaModel,
    PrismaSchema,
    parse_prisma_schema,
)

# Prisma scalar → SQLAlchemy column type (mirrors backend_codegen's _PY_SCALAR intent for the DB side).
_SA_TYPE: Dict[str, str] = {
    "String": "sa.String()",
    "Boolean": "sa.Boolean()",
    "Int": "sa.Integer()",
    "BigInt": "sa.BigInteger()",
    "Float": "sa.Float()",
    "Decimal": "sa.Numeric()",
    "DateTime": "sa.DateTime()",
    "Json": "sa.JSON()",
    "Bytes": "sa.LargeBinary()",
}

_DEFAULT_RE = re.compile(r"@default\(\s*(.*?)\s*\)")
_SNAPSHOT_RE = re.compile(r"#\s*startd8-schema-snapshot:\s*(\S+)")
_SEQ_RE = re.compile(r"^(\d{4})_")


def _table(model_name: str) -> str:
    """SQLModel's default table name: the class name lowercased (matches the generated tables)."""
    return model_name.lower()


def _sa_type(field: PrismaField, schema: PrismaSchema) -> str:
    if field.is_list:
        return "sa.JSON()"                       # list fields persist as JSON (sqlmodel_renderer parity)
    if field.type in _SA_TYPE:
        return _SA_TYPE[field.type]
    if field.type in schema.enums:
        return "sa.String()"                     # SQLite has no native enum — stored as text
    return "sa.String()"                         # unknown scalar → safe text fallback


def _server_default(field: PrismaField) -> Optional[str]:
    """A DB-side ``server_default=`` expression from a Prisma ``@default(...)``, or None.

    Function defaults handled by the app/ORM (``cuid()``/``uuid()``/``autoincrement()``) are NOT
    column server-defaults — only ``now()`` maps (→ CURRENT_TIMESTAMP). Literals become SQL literals.
    """
    for attr in field.attributes:
        m = _DEFAULT_RE.search(attr)
        if not m:
            continue
        raw = m.group(1).strip()
        if raw.endswith("()"):
            return "sa.text('CURRENT_TIMESTAMP')" if raw == "now()" else None
        if raw.lower() in ("true", "false"):
            return f"sa.text('{1 if raw.lower() == 'true' else 0}')"
        if re.fullmatch(r"-?\d+(\.\d+)?", raw):          # numeric literal
            return f"sa.text('{raw}')"
        lit = raw.strip("\"'").replace("'", "''")         # string/enum literal → quoted SQL literal
        return f"sa.text(\"'{lit}'\")"                     # embedded ' doubled (SQL escaping)
    return None


def _columns(model: PrismaModel, schema: PrismaSchema) -> List[PrismaField]:
    """The persisted (column) fields: scalars + FK-id scalars + list(JSON); object relations excluded."""
    return [f for f in model.fields if not schema.is_relation_field(f)]


def _column_expr(field: PrismaField, schema: PrismaSchema, *, force_nullable: bool = False) -> str:
    parts = [f"'{field.name}'", _sa_type(field, schema)]
    if field.is_id:
        parts.append("primary_key=True")
    parts.append(f"nullable={force_nullable or field.is_optional}")
    sd = _server_default(field)
    if sd is not None:
        parts.append(f"server_default={sd}")
    return f"sa.Column({', '.join(parts)})"


@dataclass
class MigrationPlan:
    """The additive ops + the things deliberately not auto-migrated (notes), for one delta."""

    is_baseline: bool
    upgrade_ops: List[str] = _dc_field(default_factory=list)
    downgrade_ops: List[str] = _dc_field(default_factory=list)
    notes: List[str] = _dc_field(default_factory=list)      # required-no-default adds, drops, type changes

    @property
    def empty(self) -> bool:
        return not self.upgrade_ops


def plan_migration(current_text: str, previous_text: Optional[str]) -> MigrationPlan:
    """Compute the additive migration from *previous_text* → *current_text* (baseline if no previous)."""
    cur = parse_prisma_schema(current_text)
    prev = parse_prisma_schema(previous_text) if previous_text else None
    is_baseline = prev is None
    plan = MigrationPlan(is_baseline=is_baseline)

    prev_models = set(prev.models) if prev else set()
    # New tables (baseline ⇒ all): create_table; downgrade drops them (a fresh-DB inverse, safe).
    for name in cur.models:
        if name in prev_models:
            continue
        model = cur.models[name]
        cols = ",\n        ".join(_column_expr(f, cur) for f in _columns(model, cur))
        uniques = "".join(
            f"\n        sa.UniqueConstraint({', '.join(repr(c) for c in cols_)}),"
            for cols_ in model.compound_unique_keys
        )
        plan.upgrade_ops.append(f"op.create_table(\n        '{_table(name)}',\n        {cols},{uniques}\n    )")
        plan.downgrade_ops.insert(0, f"op.drop_table('{_table(name)}')")

    # New columns on existing tables: add_column; downgrade drops the added column.
    if prev:
        for name in cur.models:
            if name not in prev_models:
                continue
            prev_fields = {f.name for f in _columns(prev.models[name], prev)}
            for f in _columns(cur.models[name], cur):
                if f.name in prev_fields:
                    continue
                force_nullable = False
                if not f.is_optional and not f.is_id and _server_default(f) is None:
                    # A NOT NULL add with no @default would fail on existing rows — soften + note.
                    force_nullable = True
                    plan.notes.append(
                        f"{name}.{f.name}: required field added as NULLABLE (no @default to backfill "
                        f"existing rows) — populate values then tighten to NOT NULL manually"
                    )
                col = _column_expr(f, cur, force_nullable=force_nullable)
                plan.upgrade_ops.append(f"op.add_column('{_table(name)}', {col})")
                plan.downgrade_ops.insert(0, f"op.drop_column('{_table(name)}', '{f.name}')")

        # Removals + type changes are reported, never auto-migrated (data-loss / risky).
        for name in sorted(prev_models - set(cur.models)):
            plan.notes.append(f"model {name}: removed from contract — NOT dropped (manual, data-loss)")
        for name in sorted(set(cur.models) & prev_models):
            cur_f = {f.name: f for f in _columns(cur.models[name], cur)}
            prev_f = {f.name: f for f in _columns(prev.models[name], prev)}
            for fn in sorted(set(prev_f) - set(cur_f)):
                plan.notes.append(f"{name}.{fn}: removed from contract — NOT dropped (manual, data-loss)")
            for fn in sorted(set(cur_f) & set(prev_f)):
                if _sa_type(cur_f[fn], cur) != _sa_type(prev_f[fn], prev):
                    plan.notes.append(
                        f"{name}.{fn}: type changed — NOT auto-migrated "
                        f"(run `alembic revision --autogenerate` for type changes)"
                    )
    return plan


# --------------------------------------------------------------------------- #
# Revision file rendering + self-contained snapshot chain (OQ-SCAF-2c)         #
# --------------------------------------------------------------------------- #

def _encode_snapshot(schema_text: str) -> str:
    return base64.b64encode(schema_text.encode("utf-8")).decode("ascii")


def _decode_snapshot(b64: str) -> str:
    return base64.b64decode(b64.encode("ascii")).decode("utf-8")


def latest_snapshot(versions_dir: Path) -> Tuple[Optional[str], int]:
    """The schema embedded in the highest-numbered revision (the chain's 'previous'), and its seq.

    Returns (schema_text or None, max_seq). Seq 0 ⇒ no revisions yet → caller emits the baseline.
    """
    best_seq = 0
    best_text: Optional[str] = None
    if not versions_dir.is_dir():
        return None, 0
    for p in versions_dir.glob("*.py"):
        m = _SEQ_RE.match(p.name)
        if not m:
            continue
        seq = int(m.group(1))
        if seq <= best_seq:
            continue
        snap = _SNAPSHOT_RE.search(p.read_text(encoding="utf-8"))
        if snap:
            best_seq, best_text = seq, _decode_snapshot(snap.group(1))
    return best_text, best_seq


def _ops_block(ops: List[str]) -> str:
    return "\n".join(f"    {op}" for op in ops) if ops else "    pass"


def render_revision(
    *, revision_id: str, down_revision: Optional[str], message: str,
    plan: MigrationPlan, current_text: str,
) -> str:
    """Render one Alembic revision .py — additive ops + the embedded schema snapshot (chain anchor)."""
    notes_block = "".join(f"# NOTE: {n}\n" for n in plan.notes)
    down = repr(down_revision)
    return (
        f'"""{message}\n\n'
        f"Revision ID: {revision_id}\n"
        f"Revises: {down_revision or ''}\n"
        '"""\n'
        "from __future__ import annotations\n\n"
        "from alembic import op\n"
        "import sqlalchemy as sa\n\n"
        f"# startd8-artifact: alembic-revision\n"
        f"# startd8-schema-snapshot: {_encode_snapshot(current_text)}\n"
        f"{notes_block}"
        f"revision = {revision_id!r}\n"
        f"down_revision = {down}\n"
        "branch_labels = None\n"
        "depends_on = None\n\n\n"
        "def upgrade() -> None:\n"
        f"{_ops_block(plan.upgrade_ops)}\n\n\n"
        "def downgrade() -> None:\n"
        f"{_ops_block(plan.downgrade_ops)}\n"
    )


def _slug(message: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", message.lower()).strip("_")
    return s or "migration"


def next_revision(
    versions_dir: Path, current_text: str, message: str
) -> Optional[Tuple[str, str, MigrationPlan]]:
    """Plan + render the next revision (filename, text, plan), or None if there is nothing to migrate.

    Auto-discovers the previous schema from the latest revision's snapshot (OQ-SCAF-2c).
    """
    previous_text, max_seq = latest_snapshot(versions_dir)
    plan = plan_migration(current_text, previous_text)
    if plan.empty:
        return None
    seq = max_seq + 1
    revision_id = f"{seq:04d}"
    down_revision = f"{max_seq:04d}" if max_seq else None
    text = render_revision(
        revision_id=revision_id, down_revision=down_revision,
        message=message, plan=plan, current_text=current_text,
    )
    return f"{seq:04d}_{_slug(message)}.py", text, plan
