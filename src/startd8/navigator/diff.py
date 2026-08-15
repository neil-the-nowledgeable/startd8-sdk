"""Navigator diff engine — a pure, renderer-independent two-state Node delta (REQ-07 FR-1/FR-4/FR-10).

Pairs two ``list[Node]`` states (a *before* and an *after*) by :attr:`Node.key` and classifies each
key as **added / removed / changed / unchanged**, extracting per-field :class:`FieldDelta`s for the
changed keys plus two review-critical derived signals: **status transitions** (``spec → built`` …)
and **new dangling refs** (``lives`` refs that appear only in *after* and no longer resolve on the
local filesystem, having NOT already been dangling in *before*).

Design (LOCKED, do not re-litigate):

* **Identity = ``Node.key``.** A renamed key is honestly ``1 removed + 1 added`` (NR-4 — no fuzzy
  rename pairing in v0.1).
* **Flatten first.** Both states are flattened with the same last-write-wins flattener the graph
  renderers use conceptually, so the diff is over the *full* flattened key-set (not just top-level
  nodes). Duplicate keys within one state resolve last-write-wins (documented).
* **``_DIFF_FIELDS``** is the exact compared field set — the spec set **+ ``child_keys``** (a real
  dependency signal), **excluding** the derived ``confidence`` / ``category`` / ``orientation`` /
  ``route_state`` fields, which would false-fire on re-derivation.
* **Order-insensitive** comparison for collection fields (compared as sorted tuples / sorted items),
  so cosmetic reordering is NOT reported as changed; scalar fields compare directly.
* **Deterministic:** buckets are key-sorted, field deltas are in a fixed field order, and shuffling
  the input node order yields an identical :class:`NodeDiff`.

Renderer-independent: this module imports **only** ``.models`` (and stdlib). It NEVER imports
``render_diff`` / ``wireframe_view`` / ``compose`` — FR-9 keeps the app-scaffold path byte-identical.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .models import Node, NodeEvidence

# ---------------------------------------------------------------------------
# The compared field set (LOCKED). The spec set + ``child_keys``, EXCLUDING the
# derived confidence/category/orientation/route_state (re-derivation false-fire).
# ---------------------------------------------------------------------------
_DIFF_FIELDS: Tuple[str, ...] = (
    "does",
    "status",
    "status_facets",
    "children",
    "child_keys",
    "attributes",
    "lives",
    "wont",
    "ships_when",
)

# Collection fields compared order-insensitively (as sorted tuples / sorted items). Everything else
# in ``_DIFF_FIELDS`` (does / status / ships_when) is a scalar compared directly.
_ORDER_INSENSITIVE_FIELDS: frozenset = frozenset(
    {"status_facets", "children", "child_keys", "lives", "wont", "attributes"}
)


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class FieldDelta:
    """A single changed field on a changed key: its ``before`` and ``after`` values."""

    field: str
    before: Any
    after: Any


@dataclass(frozen=True)
class StatusTransition:
    """A ``status`` field change surfaced as a first-class review signal (FR-4)."""

    key: str
    before: str
    after: str

    def as_arrow(self) -> str:
        return f"{self.key}: {self.before} → {self.after}"


@dataclass(frozen=True)
class DanglingRef:
    """An ``after``-only ``lives`` ref that no longer resolves on the local FS and was NOT already
    dangling in ``before`` — a newly-introduced dangling reference (FR-4, local-FS only, NR-9)."""

    key: str
    ref_type: str
    ref: str
    resolved_path: str


@dataclass(frozen=True)
class NodeDiff:
    """The full two-state delta. Buckets are key-sorted; ``changed`` carries per-field deltas."""

    added: Tuple[Node, ...] = ()
    removed: Tuple[Node, ...] = ()
    # changed: list of (key, before_node, after_node, field_deltas) — key-sorted.
    changed: Tuple[Tuple[str, Node, Node, Tuple[FieldDelta, ...]], ...] = ()
    unchanged: Tuple[str, ...] = ()
    status_transitions: Tuple[StatusTransition, ...] = ()
    new_dangling_refs: Tuple[DanglingRef, ...] = ()

    @property
    def rollup(self) -> Dict[str, int]:
        """The header roll-up counts (``+N / -M / ~K``) — always available, single source (FR-7)."""
        return {
            "added": len(self.added),
            "removed": len(self.removed),
            "changed": len(self.changed),
            "unchanged": len(self.unchanged),
        }

    @property
    def is_empty(self) -> bool:
        """True iff there is no delta at all (``added``/``removed``/``changed`` all empty)."""
        return not (self.added or self.removed or self.changed)


# ---------------------------------------------------------------------------
# Flatten + field normalization
# ---------------------------------------------------------------------------
def _flatten_last_write_wins(nodes: Sequence[Node]) -> "Dict[str, Node]":
    """Flatten a Node tree into ``{key: Node}`` with **last-write-wins** on duplicate keys.

    Unlike the projection's ``_flatten`` (which raises on a duplicate key with differing content),
    the diff is tolerant: two states are independent corpora, and within one state a duplicate key
    resolves last-write-wins (the later occurrence in a depth-first walk overwrites the earlier).
    Insertion order is preserved for the *first* time a key is seen so downstream sorting is stable.
    """
    flat: "Dict[str, Node]" = {}

    def visit(node: Node) -> None:
        flat[node.key] = node  # last-write-wins
        for child in node.children:
            visit(child)

    for n in nodes:
        visit(n)
    return flat


def _normalize(field_name: str, value: Any) -> Any:
    """Return a comparable, order-normalized representation of a Node field value.

    Order-insensitive collection fields become sorted tuples (``attributes`` → sorted ``(k, v)``
    items); everything else is returned as-is. ``children`` are compared by their (order-insensitive)
    child keys — nested content changes surface on the *child's own* changed row, not the parent's,
    so a parent isn't spuriously "changed" just because a grandchild's ``does`` moved.
    """
    if field_name == "attributes":
        # dict → sorted (key, value) tuple pairs
        return tuple(sorted((str(k), str(v)) for k, v in (value or {}).items()))
    if field_name == "children":
        # compare by the set of direct child keys (order-insensitive); nested edits land on the
        # child's own changed row (each child is its own flattened key).
        return tuple(sorted(c.key for c in (value or ())))
    if field_name == "lives":
        # NodeEvidence tuple → sorted (type, ref) pairs (note is advisory, excluded from identity)
        return tuple(sorted((e.type, e.ref) for e in (value or ())))
    if field_name == "status_facets":
        return tuple(sorted((f.name, f.value, f.glyph, f.color) for f in (value or ())))
    if field_name in _ORDER_INSENSITIVE_FIELDS:
        # wont / child_keys — plain string tuples compared as sorted tuples
        return tuple(sorted(str(x) for x in (value or ())))
    # scalar (does / status / ships_when)
    return value


def _field_deltas(before: Node, after: Node) -> Tuple[FieldDelta, ...]:
    """Per-field deltas over ``_DIFF_FIELDS`` in fixed order — a field is *changed* iff its normalized
    before/after representations differ. The ``FieldDelta`` carries the RAW before/after values (not
    the normalized ones), so the renderer shows the author's actual content."""
    deltas: List[FieldDelta] = []
    for fname in _DIFF_FIELDS:
        b_raw = getattr(before, fname)
        a_raw = getattr(after, fname)
        if _normalize(fname, b_raw) != _normalize(fname, a_raw):
            deltas.append(FieldDelta(field=fname, before=b_raw, after=a_raw))
    return tuple(deltas)


# ---------------------------------------------------------------------------
# Dangling-ref detection (FR-4) — local filesystem only (NR-9)
# ---------------------------------------------------------------------------
def _ref_to_path(ref: str) -> str:
    """Strip a ``lives`` ref down to a bare repo-relative path.

    Handles the three ref shapes the loaders emit: ``git:<40-hex-sha>:<path>``, ``file:<path>[:line]``
    and a plain ``<path>[:line]``. Returns the bare path (no scheme, no trailing ``:line``)."""
    r = (ref or "").strip()
    if not r:
        return ""
    if r.startswith("git:"):
        # git:<sha>:<path>
        parts = r.split(":", 2)
        if len(parts) == 3:
            r = parts[2]
    elif r.startswith("file:"):
        r = r[len("file:"):]
    # strip a trailing :<line> (a bare integer suffix)
    if ":" in r:
        head, _, tail = r.rpartition(":")
        if head and tail.isdigit():
            r = head
    return r.lstrip("./")


def _repo_root(start: Optional[Path]) -> Path:
    """Walk up from *start* (or cwd) to the repo root (the dir containing ``src`` + ``docs``).

    Reuses govern.py's repo-root idiom so dangling detection resolves refs against the same root the
    corpus loaders anchored them to."""
    cur = (start or Path.cwd()).resolve()
    for parent in [cur, *cur.parents]:
        if (parent / "src").is_dir() and (parent / "docs").is_dir():
            return parent
    return cur


def _resolves_on_fs(ref: str, repo_root: Path) -> bool:
    """True iff the ref's bare path resolves to an existing file/dir under ``repo_root`` (local-FS
    only — no network, NR-9). An empty / non-path ref (no ``/``, e.g. ``navigator-build``) is treated
    as resolving (it is not a filesystem path, so it can't be a *dangling* file ref)."""
    path = _ref_to_path(ref)
    if not path:
        return True
    if "/" not in path and "." not in path:
        # a non-path token (e.g. a build-kind marker) — not a file ref, never "dangling"
        return True
    return (repo_root / path).exists()


def _dangling_refs_for(node: Node, repo_root: Path) -> set:
    """The set of ``(type, ref)`` on *node* whose path does not resolve on the local FS."""
    out = set()
    for ev in node.lives or ():
        if not _resolves_on_fs(ev.ref, repo_root):
            out.add((ev.type, ev.ref))
    return out


def _new_dangling_refs(
    before: Optional[Node], after: Node, repo_root: Path
) -> List[DanglingRef]:
    """New dangling refs = ``after`` dangling refs that were NOT already dangling in ``before``.

    We diff the *dangling-ness*, not the raw ref list: a ref that was already dangling in ``before``
    is not re-flagged as *new*. For an added node (``before is None``) every dangling ref is new."""
    after_dangling = _dangling_refs_for(after, repo_root)
    if not after_dangling:
        return []
    before_dangling = _dangling_refs_for(before, repo_root) if before is not None else set()
    novel = after_dangling - before_dangling
    out: List[DanglingRef] = []
    for etype, ref in sorted(novel):
        out.append(
            DanglingRef(
                key=after.key,
                ref_type=etype,
                ref=ref,
                resolved_path=_ref_to_path(ref),
            )
        )
    return out


# ---------------------------------------------------------------------------
# The public engine
# ---------------------------------------------------------------------------
def diff_nodes(
    before: Sequence[Node],
    after: Sequence[Node],
    *,
    repo_root: Optional[Path] = None,
) -> NodeDiff:
    """Compute the deterministic, renderer-independent delta between two Node states.

    Pairs the two (flattened) states by :attr:`Node.key`. A key present only in *after* is **added**;
    only in *before* is **removed**; in both with a differing ``_DIFF_FIELDS`` projection is
    **changed** (carrying per-field :class:`FieldDelta`s); in both and identical is **unchanged**.
    Also extracts **status transitions** (from the ``status`` FieldDelta) and **new dangling refs**
    (``after``-only ``lives`` refs that don't resolve locally and weren't already dangling in
    ``before``). Buckets are key-sorted and the result is stable under input reordering (FR-10).

    ``repo_root`` roots the dangling-ref filesystem check; defaults to walking up from cwd to the
    repo root (the ``src`` + ``docs`` dir), matching the corpus loaders.
    """
    root = repo_root if repo_root is not None else _repo_root(None)

    before_map = _flatten_last_write_wins(before)
    after_map = _flatten_last_write_wins(after)

    before_keys = set(before_map)
    after_keys = set(after_map)

    added_keys = sorted(after_keys - before_keys)
    removed_keys = sorted(before_keys - after_keys)
    common_keys = sorted(before_keys & after_keys)

    added = tuple(after_map[k] for k in added_keys)
    removed = tuple(before_map[k] for k in removed_keys)

    changed: List[Tuple[str, Node, Node, Tuple[FieldDelta, ...]]] = []
    unchanged: List[str] = []
    transitions: List[StatusTransition] = []
    dangling: List[DanglingRef] = []

    for k in common_keys:
        b = before_map[k]
        a = after_map[k]
        deltas = _field_deltas(b, a)
        if deltas:
            changed.append((k, b, a, deltas))
            for d in deltas:
                if d.field == "status" and d.before != d.after:
                    transitions.append(
                        StatusTransition(key=k, before=str(d.before), after=str(d.after))
                    )
        else:
            unchanged.append(k)
        # dangling refs surface for any common key whose after-state introduces a new dangling ref
        dangling.extend(_new_dangling_refs(b, a, root))

    # added nodes: every dangling ref is new
    for k in added_keys:
        dangling.extend(_new_dangling_refs(None, after_map[k], root))

    return NodeDiff(
        added=added,
        removed=removed,
        changed=tuple(changed),
        unchanged=tuple(unchanged),
        status_transitions=tuple(transitions),
        new_dangling_refs=tuple(dangling),
    )


# ---------------------------------------------------------------------------
# JSON projection (for the CLI ``--json`` machine-readable output)
# ---------------------------------------------------------------------------
def _field_value_to_json(value: Any) -> Any:
    """Render a raw field value JSON-safely for the ``--json`` NodeDiff (evidence → dicts, etc.)."""
    if isinstance(value, tuple):
        return [_field_value_to_json(v) for v in value]
    if isinstance(value, NodeEvidence):
        return {"type": value.type, "ref": value.ref, "note": value.note}
    if isinstance(value, Node):
        return value.key  # children rendered by key (nested content is its own row)
    if isinstance(value, dict):
        return {str(k): _field_value_to_json(v) for k, v in value.items()}
    # StatusFacet or other frozen dataclass — best-effort dict
    if hasattr(value, "__dataclass_fields__"):
        return {f: _field_value_to_json(getattr(value, f)) for f in value.__dataclass_fields__}
    return value


def node_diff_to_json(diff: NodeDiff) -> Dict[str, Any]:
    """A deterministic, JSON-safe projection of a :class:`NodeDiff` (for ``--json`` / CI)."""
    return {
        "rollup": diff.rollup,
        "added": [n.key for n in diff.added],
        "removed": [n.key for n in diff.removed],
        "changed": [
            {
                "key": key,
                "fields": [
                    {
                        "field": d.field,
                        "before": _field_value_to_json(d.before),
                        "after": _field_value_to_json(d.after),
                    }
                    for d in deltas
                ],
            }
            for (key, _b, _a, deltas) in diff.changed
        ],
        "unchanged": list(diff.unchanged),
        "status_transitions": [
            {"key": t.key, "before": t.before, "after": t.after}
            for t in diff.status_transitions
        ],
        "new_dangling_refs": [
            {"key": r.key, "type": r.ref_type, "ref": r.ref, "path": r.resolved_path}
            for r in diff.new_dangling_refs
        ],
    }


__all__ = [
    "FieldDelta",
    "StatusTransition",
    "DanglingRef",
    "NodeDiff",
    "diff_nodes",
    "node_diff_to_json",
    "_DIFF_FIELDS",
]
